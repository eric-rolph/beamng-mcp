"""Free-roam live gate for the selector prop's self-contained wash runtime."""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import uuid
import zipfile
from contextlib import ExitStack
from pathlib import Path
from time import monotonic, sleep
from typing import Any

import pytest
from beamngpy import BeamNGpy, Scenario, Vehicle
from PIL import Image, ImageChops, ImageStat

from examples.cannon_car_wash.build_distribution import build_distribution, verify_archive
from tests.live_support import (
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    require_confined_profile_target,
    reserve_loopback_ports,
)
from tests.test_cannon_car_wash_phase3_live import _configured_runtime

MOD_ID = "ericrolph_cannon_car_wash"
PROP_NAME = f"{MOD_ID}_freeroam_prop"
SUBJECT_NAME = f"{MOD_ID}_freeroam_subject"
OCCUPANT_A_NAME = f"{MOD_ID}_occupant_a"
OCCUPANT_B_NAME = f"{MOD_ID}_occupant_b"
RUNTIME_EXTENSION = "ericrolph__cannon__car__wash_runtime"
LOG_TAG = "ERICROLPH_CANNON_CAR_WASH_RUNTIME"
RUNTIME_NAMESPACE_PREFIXES = (
    f"art/shapes/{MOD_ID}/",
    f"vehicles/{MOD_ID}/",
    f"lua/ge/extensions/{MOD_ID}/",
)
ANIMATED_VISUAL_SHAPE = (
    "/vehicles/ericrolph_cannon_car_wash/ericrolph_cannon_car_wash_runtime_visual.dae"
)
ANIMATED_MATERIALS_PATH = "vehicles/ericrolph_cannon_car_wash/main.materials.json"
EXPECTED_MATERIALS = (
    "ericrolph_cannon_car_wash_selector_concrete",
    "ericrolph_cannon_car_wash_selector_deep_blue",
    "ericrolph_cannon_car_wash_selector_cyan_trim",
    "ericrolph_cannon_car_wash_selector_stainless",
    "ericrolph_cannon_car_wash_selector_glass",
    "ericrolph_cannon_car_wash_selector_brush_blue",
    "ericrolph_cannon_car_wash_selector_brush_aqua",
    "ericrolph_cannon_car_wash_selector_safety_orange",
    "ericrolph_cannon_car_wash_selector_hazard_yellow",
    "ericrolph_cannon_car_wash_selector_rubber",
    "ericrolph_cannon_car_wash_selector_screen",
    "ericrolph_cannon_car_wash_selector_led",
    "ericrolph_cannon_car_wash_selector_brush_cards",
    "ericrolph_cannon_car_wash_selector_corrugated_blue",
    "ericrolph_cannon_car_wash_selector_exterior_cmu",
    "ericrolph_cannon_car_wash_selector_interior_brick",
    "ericrolph_cannon_car_wash_selector_sign_face",
    "ericrolph_cannon_car_wash_selector_wet_concrete",
)
PROP_XY = (0.0, 0.0)
SUBJECT_APPROACH_LATERAL_OFFSET = -0.65
SUBJECT_APPROACH_YAW_RADIANS = math.radians(2.0)
SUBJECT_MEASUREMENT_POSITION = (SUBJECT_APPROACH_LATERAL_OFFSET, 20.0, 20.0)
SUBJECT_ROTATION = (
    0,
    0,
    math.sin(SUBJECT_APPROACH_YAW_RADIANS / 2.0),
    math.cos(SUBJECT_APPROACH_YAW_RADIANS / 2.0),
)
PROP_ROTATED_QUATERNION = (0, 0, math.sqrt(0.5), math.sqrt(0.5))
PROP_DEFAULT_QUATERNION = (0, 0, 0, 1)
APPROACH_SPEED_MPS = 2.0
CAPTURE_RESOLUTION = (640, 360)
EXPECTED_EMITTER_COUNTS = {
    "BNGP_sprinkler": 6,
    "BNGP_waterfallsteam": 6,
    "BNGP_34": 2,
    "BNGP_2": 2,
}
EFFECT_PAIRS = (
    ("mister_PreSoak_L_1", "mister_PreSoak_R_1", "BNGP_sprinkler"),
    ("mister_PreSoak_L_2", "mister_PreSoak_R_2", "BNGP_sprinkler"),
    ("mister_PreSoak_L_3", "mister_PreSoak_R_3", "BNGP_sprinkler"),
    ("dryer_Mist_L_1", "dryer_Mist_R_1", "BNGP_waterfallsteam"),
    ("dryer_Mist_L_2", "dryer_Mist_R_2", "BNGP_waterfallsteam"),
    ("dryer_Mist_L_3", "dryer_Mist_R_3", "BNGP_waterfallsteam"),
    ("dryer_Steam_L", "dryer_Steam_R", "BNGP_34"),
    ("dryer_Dust_L", "dryer_Dust_R", "BNGP_2"),
)


def _lua_json(bng: BeamNGpy, command: str) -> dict[str, Any]:
    payload = bng.control.queue_lua_command(command, response=True)
    decoded = json.loads(payload)
    assert isinstance(decoded, dict)
    return decoded


def _runtime_state(bng: BeamNGpy) -> dict[str, Any]:
    return _lua_json(
        bng,
        f"local extension = extensions[{RUNTIME_EXTENSION!r}]; "
        f"local prop = scenetree.findObject({PROP_NAME!r}); "
        "if not extension then return jsonEncode({loaded = false}) end; "
        "if not prop then return jsonEncode({loaded = true, registered = false}) end; "
        "local state = extension.getSystemState(prop:getID()); "
        "state.loaded = true; "
        "local visual = state.visual_name and scenetree.findObject(state.visual_name) or nil; "
        "state.visual_exists = visual ~= nil; "
        "state.visual_play_ambient = visual and visual:getField('playAmbient', 0) or nil; "
        "return jsonEncode(state)",
    )


def _material_loader_diagnostics(bng: BeamNGpy) -> dict[str, Any]:
    material_names = json.dumps(EXPECTED_MATERIALS, separators=(",", ":"))
    return _lua_json(
        bng,
        f"local path = {ANIMATED_MATERIALS_PATH!r}; "
        f"local names = jsonDecode({material_names!r}); "
        "local function countMaterials() local count = 0; local classes = {}; "
        "for _, name in ipairs(names) do local object = scenetree.findObject(name); "
        "if object then count = count + 1; classes[name] = object:getClassName() end; end; "
        "return count, classes end; "
        "local beforeCount, beforeClasses = countMaterials(); "
        "local exists = FS:fileExists(path); "
        "local contents = exists and readFile(path) or nil; "
        "local ok, result = pcall(loadJsonMaterialsFile, path); "
        "local afterCount, afterClasses = countMaterials(); "
        "return jsonEncode({file_exists = exists, byte_count = contents and #contents or -1, "
        "load_ok = ok, load_result = tostring(result), before_count = beforeCount, "
        "after_count = afterCount, before_classes = beforeClasses, "
        "after_classes = afterClasses})",
    )


def _vehicle_origin_clearance(bng: BeamNGpy, vehicle_name: str) -> float:
    state = _lua_json(
        bng,
        f"local vehicle = scenetree.findObject({vehicle_name!r}); "
        "if not vehicle then return jsonEncode({ok = false}) end; "
        "local box = vehicle:getSpawnWorldOOBB(); "
        "local minimumZ = math.huge; "
        "for index = 0, 7 do minimumZ = math.min(minimumZ, box:getPoint(index).z) end; "
        "local position = vehicle:getPosition(); "
        "return jsonEncode({ok = true, clearance = position.z - minimumZ})",
    )
    assert state["ok"] is True, state
    return float(state["clearance"])


def _wait_for_occupancy(
    bng: BeamNGpy,
    *,
    count: int,
    active: bool,
    attempts: int = 120,
) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for _ in range(attempts):
        bng.control.step(3, wait=True)
        state = _runtime_state(bng)
        if int(state.get("wash_subject_count", -1)) == count and state.get("wash_active") is active:
            return state
    pytest.fail({"expected_count": count, "expected_active": active, "state": state})


def _launch_containment_state(bng: BeamNGpy) -> dict[str, Any]:
    return _lua_json(
        bng,
        f"local extension = extensions[{RUNTIME_EXTENSION!r}]; "
        f"local prop = scenetree.findObject({PROP_NAME!r}); "
        f"local subject = scenetree.findObject({SUBJECT_NAME!r}); "
        "if not extension or not prop or not subject then "
        "return jsonEncode({ok = false}) end; "
        "local state = extension.getSystemState(prop:getID()); "
        "local trigger = state.launch_trigger and "
        "scenetree.findObject(state.launch_trigger.name) or nil; "
        "if not trigger then return jsonEncode({ok = false}) end; "
        "local center = trigger:getPosition(); local scale = trigger:getScale(); "
        "local box = subject:getSpawnWorldOOBB(); "
        "local minimum = vec3(math.huge, math.huge, math.huge); "
        "local maximum = vec3(-math.huge, -math.huge, -math.huge); "
        "for index = 0, 7 do local point = box:getPoint(index); "
        "minimum.x = math.min(minimum.x, point.x); "
        "minimum.y = math.min(minimum.y, point.y); "
        "minimum.z = math.min(minimum.z, point.z); "
        "maximum.x = math.max(maximum.x, point.x); "
        "maximum.y = math.max(maximum.y, point.y); "
        "maximum.z = math.max(maximum.z, point.z); end; "
        "return jsonEncode({ok = true, center = {center.x, center.y, center.z}, "
        "scale = {scale.x, scale.y, scale.z}, "
        "vehicle_min = {minimum.x, minimum.y, minimum.z}, "
        "vehicle_max = {maximum.x, maximum.y, maximum.z}})",
    )


def _runtime_trigger_transform(bng: BeamNGpy, state_key: str) -> dict[str, Any]:
    assert state_key in {"wash_trigger", "repair_trigger", "launch_trigger"}
    return _lua_json(
        bng,
        f"local extension = extensions[{RUNTIME_EXTENSION!r}]; "
        f"local prop = scenetree.findObject({PROP_NAME!r}); "
        "if not extension or not prop then return jsonEncode({ok = false}) end; "
        "local state = extension.getSystemState(prop:getID()); "
        f"local description = state[{state_key!r}]; "
        "local trigger = description and scenetree.findObject(description.name) or nil; "
        "if not trigger then return jsonEncode({ok = false}) end; "
        "local position = trigger:getPosition(); local scale = trigger:getScale(); "
        "local rotation = quat(trigger:getRotation()); "
        "local forward = rotation * vec3(0, 1, 0); forward:normalize(); "
        "local up = rotation * vec3(0, 0, 1); up:normalize(); "
        "return jsonEncode({ok = true, "
        "position = {position.x, position.y, position.z}, "
        "scale = {scale.x, scale.y, scale.z}, "
        "forward = {forward.x, forward.y, forward.z}, "
        "up = {up.x, up.y, up.z}, "
        "mode = trigger:getField('triggerMode', 0), "
        "test_type = trigger:getField('triggerTestType', 0)})",
    )


def _subject_state(subject: Vehicle) -> dict[str, Any]:
    subject.sensors.poll("state")
    state = subject.sensors.data["state"]
    return {
        "position": [float(value) for value in state["pos"]],
        "velocity": [float(value) for value in state["vel"]],
    }


def _set_subject_frozen(subject: Vehicle, frozen: bool) -> None:
    freeze_value = 1 if frozen else 0
    result = json.loads(
        subject.queue_lua_command(
            "if not controller or not controller.setFreeze then "
            "return jsonEncode({ok = false}) end; "
            f"controller.setFreeze({freeze_value}); "
            "return jsonEncode({ok = true})",
            response=True,
        )
    )
    assert result == {"ok": True}


def _subject_integrity_state(subject: Vehicle) -> dict[str, Any]:
    result = json.loads(
        subject.queue_lua_command(
            "local partDamage = beamstate and beamstate.getPartDamageData "
            "and beamstate.getPartDamageData() or {}; "
            "local partDamageSnapshot = {}; "
            "for partName, data in pairs(partDamage) do "
            "partDamageSnapshot[#partDamageSnapshot + 1] = {"
            "part_name = tostring(partName), name = tostring(data.name or ''), "
            "damage = tonumber(data.damage) or 0}; end; "
            "table.sort(partDamageSnapshot, function(left, right) "
            "return left.part_name < right.part_name end); "
            "local brokenBeamCount = 0; "
            "for _, beam in pairs((v and v.data and v.data.beams) or {}) do "
            "if beam.cid ~= nil and obj:beamIsBroken(beam.cid) then "
            "brokenBeamCount = brokenBeamCount + 1 end; end; "
            "local deflatedTireCount = 0; "
            "for _, wheel in pairs((wheels and wheels.wheels) or {}) do "
            "if wheel.isTireDeflated then deflatedTireCount = deflatedTireCount + 1 end; end; "
            "return jsonEncode({"
            "damage = beamstate and beamstate.damage or 0, "
            "part_damage = partDamageSnapshot, "
            "part_damage_count = #partDamageSnapshot, "
            "broken_beam_count = brokenBeamCount, "
            "deflated_tire_count = deflatedTireCount, "
            "controller_frozen = controller and controller.isFrozen == true or false})",
            response=True,
        )
    )
    assert isinstance(result, dict)
    part_damage = result.get("part_damage")
    # BeamNG's jsonEncode serializes an empty sequence table as `{}` because
    # Lua does not retain an explicit array type once the last entry is gone.
    if part_damage == {}:
        part_damage = []
    assert isinstance(part_damage, list)
    return {
        "damage": float(result["damage"]),
        "part_damage": part_damage,
        "part_damage_count": int(result["part_damage_count"]),
        "broken_beam_count": int(result["broken_beam_count"]),
        "deflated_tire_count": int(result["deflated_tire_count"]),
        "controller_frozen": result["controller_frozen"] is True,
    }


def _damage_subject_for_repair(subject: Vehicle) -> dict[str, Any]:
    result = json.loads(
        subject.queue_lua_command(
            "local broken = {}; "
            "for _, beam in pairs((v and v.data and v.data.beams) or {}) do "
            "if #broken < 3 and beam.cid ~= nil and beam.partPath "
            "and not beam.wheelID and not beam.breakGroup "
            "and not obj:beamIsBroken(beam.cid) then "
            "obj:breakBeam(beam.cid); "
            "broken[#broken + 1] = {cid = beam.cid, part = tostring(beam.partPath)}; "
            "end; end; "
            "if beamstate and beamstate.deflateRandomTire then "
            "beamstate.deflateRandomTire() end; "
            "if beamstate and beamstate.addDamage then beamstate.addDamage(100) end; "
            "return jsonEncode({ok = #broken > 0, broken = broken})",
            response=True,
        )
    )
    assert isinstance(result, dict)
    assert result.get("ok") is True, result
    assert len(result["broken"]) == 3, result
    return result


def _runtime_effect_orientation_state(bng: BeamNGpy) -> dict[str, Any]:
    pairs = json.dumps(EFFECT_PAIRS, separators=(",", ":"))
    return _lua_json(
        bng,
        f"local prop = scenetree.findObject({PROP_NAME!r}); "
        "if not prop then return jsonEncode({ok = false, error = 'prop missing'}) end; "
        "local prefix = string.format('ericrolph_cannon_car_wash_runtime_%d', "
        "prop:getID()); "
        f"local pairSuffixes = jsonDecode({pairs!r}); "
        "local samples = {}; local presentCount = 0; "
        "for _, suffixes in ipairs(pairSuffixes) do "
        "local left = scenetree.findObject(prefix .. '_' .. suffixes[1]); "
        "local right = scenetree.findObject(prefix .. '_' .. suffixes[2]); "
        "if left then presentCount = presentCount + 1 end; "
        "if right then presentCount = presentCount + 1 end; "
        "if not left or not right then "
        "return jsonEncode({ok = false, error = 'effect missing', "
        "left = suffixes[1], right = suffixes[2], present_count = presentCount}) end; "
        "local expectedEmitter = suffixes[3]; "
        "local leftEmitter = left:getField('emitter', 0); "
        "local rightEmitter = right:getField('emitter', 0); "
        "if leftEmitter ~= expectedEmitter or rightEmitter ~= expectedEmitter then "
        "return jsonEncode({ok = false, error = 'emitter mismatch', "
        "left = suffixes[1], right = suffixes[2], expected_emitter = expectedEmitter, "
        "left_emitter = leftEmitter, right_emitter = rightEmitter, "
        "present_count = presentCount}) end; "
        "local leftPosition = left:getPosition(); "
        "local rightPosition = right:getPosition(); "
        "local inwardFromLeft = rightPosition - leftPosition; inwardFromLeft:normalize(); "
        "local leftAxis = quat(left:getRotation()) * vec3(0, 0, 1); leftAxis:normalize(); "
        "local rightAxis = quat(right:getRotation()) * vec3(0, 0, 1); "
        "rightAxis:normalize(); "
        "samples[#samples + 1] = {"
        "left = suffixes[1], right = suffixes[2], "
        "expected_emitter = expectedEmitter, "
        "left_emitter = leftEmitter, right_emitter = rightEmitter, "
        "left_inward_dot = leftAxis:dot(inwardFromLeft), "
        "right_inward_dot = rightAxis:dot(-inwardFromLeft), "
        "left_axis = {leftAxis.x, leftAxis.y, leftAxis.z}, "
        "right_axis = {rightAxis.x, rightAxis.y, rightAxis.z}, "
        "left_to_right = {inwardFromLeft.x, inwardFromLeft.y, inwardFromLeft.z}}; "
        "end; "
        "return jsonEncode({ok = true, present_count = presentCount, samples = samples})",
    )


def _subject_pose(bng: BeamNGpy) -> dict[str, Any]:
    return _lua_json(
        bng,
        f"local vehicle = scenetree.findObject({SUBJECT_NAME!r}); "
        "if not vehicle then return jsonEncode({ok = false}) end; "
        "local position = vehicle:getPosition(); "
        "local direction = vehicle:getDirectionVector(); direction:normalize(); "
        "local up = vehicle:getDirectionVectorUp(); up:normalize(); "
        "local box = vehicle:getSpawnWorldOOBB(); "
        "local center = box:getCenter(); "
        "local minimumZ = math.huge; local maximumZ = -math.huge; "
        "for index = 0, 7 do "
        "local point = box:getPoint(index); "
        "minimumZ = math.min(minimumZ, point.z); "
        "maximumZ = math.max(maximumZ, point.z); "
        "end; "
        "return jsonEncode({ok = true, "
        "position = {position.x, position.y, position.z}, "
        "direction = {direction.x, direction.y, direction.z}, "
        "up = {up.x, up.y, up.z}, "
        "bounding_center = {center.x, center.y, center.z}, "
        "minimum_z = minimumZ, maximum_z = maximumZ})",
    )


def _inject_forward_velocity(bng: BeamNGpy, speed_mps: float) -> list[float]:
    result = _lua_json(
        bng,
        f"local vehicle = scenetree.findObject({SUBJECT_NAME!r}); "
        "if not vehicle then return jsonEncode({ok = false}) end; "
        # Translate along the authored corridor without steering the vehicle.
        # Its deliberately offset 2-degree heading must survive until the repair
        # zone so the alignment policy, rather than the test driver, corrects it.
        "local direction = vec3(0, -1, 0); "
        f"local velocity = direction * {speed_mps:.6f}; "
        "vehicle:applyClusterVelocityScaleAdd(vehicle:getRefNodeId(), 0, "
        "velocity.x, velocity.y, velocity.z); "
        "return jsonEncode({ok = true, direction = {direction.x, direction.y, direction.z}})",
    )
    assert result["ok"] is True
    return [float(value) for value in result["direction"]]


def _archive_carries_runtime_namespace(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                normalized = member.replace("\\", "/").lstrip("/").casefold()
                if any(
                    normalized.startswith(prefix.casefold())
                    for prefix in RUNTIME_NAMESPACE_PREFIXES
                ):
                    return True
    except (OSError, zipfile.BadZipFile) as exc:
        if MOD_ID in path.name.casefold() or "cannon_car_wash" in path.name.casefold():
            pytest.fail(f"cannot inventory possible competing archive {path}: {exc}")
    return False


def _competing_runtime_mods(user: Path, installed_zip: Path) -> list[str]:
    mods_root = require_confined_profile_target(user, Path("mods"))
    conflicts: list[str] = []
    for directory in (mods_root, mods_root / "repo"):
        directory = require_confined_profile_target(user, directory)
        if not directory.is_dir():
            continue
        for candidate in directory.iterdir():
            candidate = require_confined_profile_target(user, candidate)
            if (
                candidate != installed_zip
                and candidate.is_file()
                and candidate.suffix.casefold() == ".zip"
                and _archive_carries_runtime_namespace(candidate)
            ):
                conflicts.append(candidate.relative_to(mods_root).as_posix())

    unpacked_root = require_confined_profile_target(user, mods_root / "unpacked")
    if unpacked_root.is_dir():
        for candidate in unpacked_root.iterdir():
            candidate = require_confined_profile_target(user, candidate)
            if not candidate.is_dir():
                continue
            carries_namespace = any(
                require_confined_profile_target(user, candidate / prefix).exists()
                for prefix in RUNTIME_NAMESPACE_PREFIXES
            )
            if carries_namespace:
                conflicts.append(candidate.relative_to(mods_root).as_posix() + "/")
    return sorted(set(conflicts))


def _trajectory_sample(
    bng: BeamNGpy,
    subject: Vehicle,
    runtime_state: dict[str, Any],
    phase: str,
) -> dict[str, Any]:
    subject_state = _subject_state(subject)
    pose = _subject_pose(bng)
    assert pose["ok"] is True
    return {
        "phase": phase,
        "position": subject_state["position"],
        "velocity": subject_state["velocity"],
        "direction": pose["direction"],
        "wash_active": runtime_state.get("wash_active"),
        "wash_subject_count": runtime_state.get("wash_subject_count"),
        "effect_active_count": runtime_state.get("effect_active_count"),
        "light_present_count": runtime_state.get("light_present_count"),
        "light_expected_count": runtime_state.get("light_expected_count"),
        "repair_pending_count": runtime_state.get("repair_pending_count"),
        "repaired_subject_count": runtime_state.get("repaired_subject_count"),
        "active_phase": runtime_state.get("active_phase"),
    }


def _remember_trajectory(
    samples: list[dict[str, Any]], sample: dict[str, Any], *, limit: int = 16
) -> None:
    samples.append(sample)
    del samples[:-limit]


def _asset_resolution_state(bng: BeamNGpy, visual_name: str) -> dict[str, Any]:
    material_names = json.dumps(EXPECTED_MATERIALS, separators=(",", ":"))
    return _lua_json(
        bng,
        f"local names = jsonDecode({material_names!r}); "
        f"local visual = scenetree.findObject({visual_name!r}); "
        "local materials = {}; "
        "for _, name in ipairs(names) do "
        "local material = scenetree.findObject(name); "
        "materials[#materials + 1] = {"
        "name = name, exists = material ~= nil, "
        "class = material and material:getClassName() or nil, "
        "resolved_name = material and material:getName() or nil, "
        "map_to = material and material:getField('mapTo', 0) or nil}; "
        "end; "
        "local sequenceNames = {}; "
        "local preview = ShapePreview(); "
        f"preview:setObjectModel({ANIMATED_VISUAL_SHAPE!r}); "
        "local shapeInfo = preview:getTSShapeInfo(); "
        "for _, sequence in pairs((shapeInfo and shapeInfo.sequences) or {}) do "
        "sequenceNames[#sequenceNames + 1] = sequence.name; end; "
        "table.sort(sequenceNames); preview = nil; "
        "return jsonEncode({"
        "visual_exists = visual ~= nil, "
        "visual_class = visual and visual:getClassName() or nil, "
        "shape_name = visual and visual:getField('shapeName', 0) or nil, "
        f"shape_exists = FS:fileExists({ANIMATED_VISUAL_SHAPE!r}), "
        f"materials_file_exists = FS:fileExists({ANIMATED_MATERIALS_PATH!r}), "
        "materials = materials, sequence_names = sequenceNames})",
    )


def _request_fixed_camera_capture(
    bng: BeamNGpy,
    *,
    relative_path: Path,
    render_view_name: str,
    surface_z: float,
) -> None:
    filename = relative_path.as_posix()
    directory = relative_path.parent.as_posix()
    result = _lua_json(
        bng,
        f"local directory = {directory!r}; "
        f"local filename = {filename!r}; "
        "if not FS:directoryExists(directory) then "
        "FS:directoryCreate(directory, true) end; "
        "if not render_renderViews then extensions.load('render/renderViews') end; "
        "if not render_renderViews or not render_renderViews.takeScreenshot then "
        "return jsonEncode({ok = false, error = 'render_renderViews unavailable'}) end; "
        f"local cameraPosition = vec3(0.9, -11.5, {surface_z + 3.4:.6f}); "
        f"local cameraTarget = vec3(0.0, 0.0, {surface_z + 2.2:.6f}); "
        "local cameraRotation = quatFromDir("
        "cameraTarget - cameraPosition, vec3(0, 0, 1)); "
        "local ok, captureError = pcall(function() "
        "render_renderViews.takeScreenshot({"
        f"renderViewName = {render_view_name!r}, "
        "filename = filename, resolution = vec3(640, 360, 0), "
        "pos = cameraPosition, rot = cameraRotation, fov = 55, "
        "nearPlane = 0.1, screenshotDelay = 0.1}); "
        "end); "
        "return jsonEncode({ok = ok, error = ok and nil or tostring(captureError)})",
    )
    assert result.get("ok") is True, result


def _read_nonblank_capture(path: Path) -> Image.Image | None:
    if not path.is_file():
        return None
    try:
        with Image.open(path) as captured:
            image = captured.convert("RGB")
            image.load()
    except OSError:
        return None
    if image.size != CAPTURE_RESOLUTION or max(ImageStat.Stat(image).stddev) <= 1.0:
        return None
    return image


def _wait_for_capture(bng: BeamNGpy, path: Path) -> Image.Image:
    deadline = monotonic() + 30.0
    while monotonic() < deadline:
        bng.control.step(3, wait=True)
        image = _read_nonblank_capture(path)
        if image is not None:
            return image
        sleep(0.05)
    pytest.fail(
        "BeamNG retail RenderView did not produce a non-blank fixed-camera "
        f"{CAPTURE_RESOLUTION[0]}x{CAPTURE_RESOLUTION[1]} frame within 30 seconds: {path}"
    )


def _assert_temporal_pixel_difference(first: Image.Image, second: Image.Image) -> dict[str, Any]:
    difference = ImageChops.difference(first, second)
    channel_means = ImageStat.Stat(difference).mean
    materially_changed = difference.convert("L").point(lambda value: 255 if value >= 8 else 0)
    changed_pixels = materially_changed.histogram()[255]
    pixel_count = first.width * first.height
    assert max(channel_means) > 0.10, channel_means
    assert changed_pixels / pixel_count > 0.001, {
        "changed_pixels": changed_pixels,
        "pixel_count": pixel_count,
        "channel_means": channel_means,
    }
    return {
        "channel_means": channel_means,
        "changed_pixels": changed_pixels,
        "pixel_count": pixel_count,
        "changed_pixel_ratio": changed_pixels / pixel_count,
    }


def _runtime_log_records(
    log_path: Path, start_marker: str
) -> tuple[list[dict[str, Any]], list[str]]:
    if not log_path.is_file():
        return [], []
    raw_payload = log_path.read_bytes()
    encoded_marker = start_marker.encode("utf-8")
    marker_index = raw_payload.rfind(encoded_marker)
    if marker_index < 0:
        return [], []
    payload = raw_payload[marker_index + len(encoded_marker) :].decode("utf-8", errors="replace")
    records: list[dict[str, Any]] = []
    issues: list[str] = []
    for line in payload.splitlines():
        folded = line.casefold()
        test_cleanup_notice = (
            "|w|" in folded
            and "core_modmanager.initdb| mod vanished:" in folded
            and "/mods/cannon_car_wash_runtime_live_" in folded
        )
        relevant = any(
            token in folded
            for token in (
                LOG_TAG.casefold(),
                MOD_ID.casefold(),
                RUNTIME_EXTENSION.casefold(),
                "ericrolph_cannon_car_wash_runtime_",
            )
        )
        if relevant and not test_cleanup_notice and ("|e|" in folded or "|w|" in folded):
            issues.append(line)
        if LOG_TAG not in line:
            continue
        json_start = line.find("{")
        if json_start < 0:
            continue
        try:
            record = json.loads(line[json_start:])
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or not isinstance(record.get("event"), str):
            continue
        timestamp_text = line.split("|", 1)[0].strip()
        try:
            record["log_time_seconds"] = float(timestamp_text)
        except ValueError:
            continue
        records.append(record)
    return records, issues


def _runtime_log_events(log_path: Path, start_marker: str) -> tuple[list[str], list[str]]:
    records, issues = _runtime_log_records(log_path, start_marker)
    return [str(record["event"]) for record in records], issues


def _mark_runtime_log_start(bng: BeamNGpy, marker: str) -> str:
    result = _lua_json(
        bng,
        f"log('I', 'ERICROLPH_CANNON_CAR_WASH_LIVE_TEST', {marker!r}); "
        "return jsonEncode({ok = true})",
    )
    assert result == {"ok": True}
    return marker


@pytest.mark.beamng_live
def test_selector_prop_runs_wash_countdown_and_launch_in_clean_freeroam(
    tmp_path: Path,
) -> None:
    home, user, binary = _configured_runtime()
    release = build_distribution(tmp_path / "release")
    archive = Path(str(release["archive"]))
    verify_archive(archive)
    release_payload = archive.read_bytes()
    assert hashlib.sha256(release_payload).hexdigest() == release["sha256"]

    suffix = uuid.uuid4().hex[:10]
    installed_zip = require_confined_profile_target(
        user, Path("mods") / f"cannon_car_wash_runtime_live_{suffix}.zip"
    )
    scenario_name = f"cannon_wash_freeroam_{suffix}"
    scenario_directory = require_confined_profile_target(
        user, Path("levels") / "smallgrid" / "scenarios" / scenario_name
    )
    capture_relative_directory = (
        Path("screenshots") / "beamng-mcp" / f"cannon-runtime-live-{suffix}"
    )
    capture_directory = require_confined_profile_target(user, capture_relative_directory)
    first_capture_path = require_confined_profile_target(
        user, capture_relative_directory / "01-wash-active.png"
    )
    second_capture_path = require_confined_profile_target(
        user, capture_relative_directory / "02-wash-active-later.png"
    )
    log_path = user / "beamng.log"

    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(1))
        (tcom_port,) = reservation.ports
        conflicts = _competing_runtime_mods(user, installed_zip)
        if conflicts:
            pytest.fail(
                "isolated profile contains competing Cannon Car Wash namespaces; "
                f"left untouched: {conflicts}"
            )
        if installed_zip.exists():
            pytest.fail(f"refusing to overwrite isolated-profile artifact: {installed_zip}")
        installed_zip.parent.mkdir(parents=True, exist_ok=True)
        with installed_zip.open("xb") as handle:
            handle.write(release_payload)
            handle.flush()
            os.fsync(handle.fileno())

        launch_user = user.parent if user.name.casefold() == "current" else user
        bng = BeamNGpy(
            "127.0.0.1",
            tcom_port,
            home=str(home),
            binary=str(binary),
            user=str(launch_user),
            quit_on_close=False,
            headless=True,
            nogpu=False,
        )
        scenario: Scenario | None = None
        owned_process: Any | None = None
        timer: threading.Timer | None = None
        log_start = f"cannon_car_wash_runtime_start_{suffix}"
        try:

            def watchdog() -> None:
                process = bng.process
                if process is not None and process.poll() is None:
                    process.terminate()

            timer = threading.Timer(240.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)

            scenario = Scenario(
                "smallgrid",
                scenario_name,
                description="Disposable selector-prop free-roam acceptance fixture",
            )
            subject = Vehicle(
                SUBJECT_NAME,
                "citybus",
                part_config="vehicles/citybus/city.pc",
                license="BUSWASH",
                color="White",
            )
            occupant_a = Vehicle(OCCUPANT_A_NAME, "pigeon", license="WASH-A")
            occupant_b = Vehicle(OCCUPANT_B_NAME, "pigeon", license="WASH-B")
            # Start clear of all geometry solely to measure this model/config's
            # exact origin-to-OOBB clearance before placing it on the raycast map
            # surface. This avoids both guessed Z offsets and BeamNGpy cling.
            scenario.add_vehicle(
                subject,
                pos=SUBJECT_MEASUREMENT_POSITION,
                rot_quat=SUBJECT_ROTATION,
                cling=False,
            )
            scenario.add_vehicle(
                occupant_a,
                pos=(-10.0, 25.0, 20.0),
                rot_quat=SUBJECT_ROTATION,
                cling=False,
            )
            scenario.add_vehicle(
                occupant_b,
                pos=(10.0, 25.0, 20.0),
                rot_quat=SUBJECT_ROTATION,
                cling=False,
            )
            scenario.make(bng)
            bng.control.pause()
            bng.scenario.load(scenario, precompile_shaders=False)
            bng.scenario.start()
            bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
            bng.control.pause()
            bng.control.step(3, wait=True)
            log_start = _mark_runtime_log_start(
                bng,
                log_start,
            )

            assert _lua_json(
                bng,
                "return jsonEncode({loaded = extensions.isExtensionLoaded("
                f"{RUNTIME_EXTENSION!r})}})",
            ) == {"loaded": False}

            surface = _lua_json(
                bng,
                "local rayStart = vec3(0, 0, 200); "
                "local rayDistance = castRayStatic(rayStart, vec3(0, 0, -1), 300); "
                "return jsonEncode({distance = rayDistance, "
                "surface_z = rayStart.z - rayDistance})",
            )
            assert 0.0 < float(surface["distance"]) < 300.0, surface
            surface_z = float(surface["surface_z"])
            assert -10.0 <= surface_z <= 10.0, surface
            prop_position = (PROP_XY[0], PROP_XY[1], surface_z)

            prop = Vehicle(PROP_NAME, MOD_ID, license="WASH")
            spawned = bng.vehicles.spawn(
                prop,
                prop_position,
                PROP_DEFAULT_QUATERNION,
                False,
                True,
            )
            assert spawned is True

            runtime_state: dict[str, Any] = {}
            for _ in range(24):
                bng.control.step(15, wait=True)
                runtime_state = _runtime_state(bng)
                if runtime_state.get("registered"):
                    break
            assert runtime_state["loaded"] is True
            if runtime_state.get("registered") is not True:
                runtime_state["material_loader_diagnostics"] = _material_loader_diagnostics(bng)
            assert runtime_state["registered"] is True, runtime_state
            assert runtime_state["arbitrary_vehicle_support"] is True
            assert runtime_state["visual_exists"] is True
            assert runtime_state["effect_present_count"] == 16
            assert runtime_state["effect_expected_count"] == 16
            assert runtime_state["effect_active_count"] == 0
            assert runtime_state["light_present_count"] == 13
            assert runtime_state["light_expected_count"] == 13
            assert runtime_state["emitter_present_counts"] == EXPECTED_EMITTER_COUNTS
            assert runtime_state.get("emitter_active_counts") in ({}, None)
            assert runtime_state["wash_trigger"] == {
                "name": runtime_state["wash_trigger"]["name"],
                "id": runtime_state["wash_trigger"]["id"],
                "mode": "Overlaps",
                "test_type": "Bounding box",
            }
            assert runtime_state["repair_trigger"] == {
                "name": runtime_state["repair_trigger"]["name"],
                "id": runtime_state["repair_trigger"]["id"],
                "mode": "Overlaps",
                "test_type": "Bounding box",
            }
            assert runtime_state["launch_trigger"]["mode"] == "Contains"
            assert runtime_state["launch_trigger"]["test_type"] == "Bounding box"
            assert (
                len(
                    {
                        runtime_state["wash_trigger"]["id"],
                        runtime_state["repair_trigger"]["id"],
                        runtime_state["launch_trigger"]["id"],
                    }
                )
                == 3
            )
            assert runtime_state["ground_origin"][2] == pytest.approx(surface_z, abs=0.03)

            asset_state = _asset_resolution_state(bng, runtime_state["visual_name"])
            assert asset_state["visual_exists"] is True
            assert asset_state["visual_class"] == "TSStatic"
            assert asset_state["shape_name"] == ANIMATED_VISUAL_SHAPE
            assert asset_state["shape_exists"] is True
            assert asset_state["materials_file_exists"] is True
            assert "ambient" in asset_state["sequence_names"], asset_state
            assert [material["name"] for material in asset_state["materials"]] == list(
                EXPECTED_MATERIALS
            )
            for material in asset_state["materials"]:
                assert material["exists"] is True
                assert str(material["class"]).casefold() == "material"
                assert material["resolved_name"] == material["name"]
                assert material["map_to"] == material["name"]

            prop_state = json.loads(
                prop.queue_lua_command(
                    "local p = obj:getPosition(); return jsonEncode({position = {p.x, p.y, p.z}})",
                    response=True,
                )
            )
            assert prop_state["position"][2] == pytest.approx(surface_z, abs=0.03)

            initial_wash_trigger_id = runtime_state["wash_trigger"]["id"]
            initial_repair_trigger_id = runtime_state["repair_trigger"]["id"]
            initial_launch_trigger_id = runtime_state["launch_trigger"]["id"]
            assert (
                bng.vehicles.teleport(
                    prop,
                    prop_position,
                    PROP_ROTATED_QUATERNION,
                    True,
                )
                is True
            )
            rotated_runtime_state: dict[str, Any] | None = None
            for _ in range(120):
                bng.control.step(3, wait=True)
                runtime_state = _runtime_state(bng)
                if (
                    runtime_state.get("registered") is True
                    and runtime_state.get("wash_trigger", {}).get("id") != initial_wash_trigger_id
                    and runtime_state.get("repair_trigger", {}).get("id")
                    != initial_repair_trigger_id
                    and runtime_state.get("launch_trigger", {}).get("id")
                    != initial_launch_trigger_id
                ):
                    rotated_runtime_state = runtime_state
                    break
            assert rotated_runtime_state is not None, runtime_state
            assert rotated_runtime_state["light_present_count"] == 13
            assert rotated_runtime_state["light_expected_count"] == 13

            effect_orientation = _runtime_effect_orientation_state(bng)
            assert effect_orientation["ok"] is True, effect_orientation
            assert effect_orientation["present_count"] == 16
            assert len(effect_orientation["samples"]) == 8
            assert {sample["expected_emitter"] for sample in effect_orientation["samples"]} == set(
                EXPECTED_EMITTER_COUNTS
            )
            for sample in effect_orientation["samples"]:
                # The left-to-right span must itself have rotated off the world X
                # axis, proving this is not an identity-orientation-only check.
                assert abs(float(sample["left_to_right"][0])) <= 0.02, sample
                assert abs(float(sample["left_to_right"][1])) >= 0.999, sample
                assert abs(float(sample["left_to_right"][2])) <= 0.02, sample
                assert float(sample["left_inward_dot"]) >= 0.999, sample
                assert float(sample["right_inward_dot"]) >= 0.999, sample
                assert sample["left_emitter"] == sample["expected_emitter"]
                assert sample["right_emitter"] == sample["expected_emitter"]

            rotated_wash_trigger_id = rotated_runtime_state["wash_trigger"]["id"]
            rotated_repair_trigger_id = rotated_runtime_state["repair_trigger"]["id"]
            rotated_launch_trigger_id = rotated_runtime_state["launch_trigger"]["id"]
            assert (
                bng.vehicles.teleport(
                    prop,
                    prop_position,
                    PROP_DEFAULT_QUATERNION,
                    True,
                )
                is True
            )
            restored_runtime_state: dict[str, Any] | None = None
            for _ in range(120):
                bng.control.step(3, wait=True)
                runtime_state = _runtime_state(bng)
                if (
                    runtime_state.get("registered") is True
                    and runtime_state.get("wash_trigger", {}).get("id") != rotated_wash_trigger_id
                    and runtime_state.get("repair_trigger", {}).get("id")
                    != rotated_repair_trigger_id
                    and runtime_state.get("launch_trigger", {}).get("id")
                    != rotated_launch_trigger_id
                ):
                    restored_runtime_state = runtime_state
                    break
            assert restored_runtime_state is not None, runtime_state
            assert restored_runtime_state["light_present_count"] == 13
            assert restored_runtime_state["ground_origin"][2] == pytest.approx(surface_z, abs=0.03)
            repair_transform = _runtime_trigger_transform(bng, "repair_trigger")
            assert repair_transform == {
                "ok": True,
                "position": pytest.approx([0.0, 0.0, surface_z + 2.1], abs=0.03),
                "scale": pytest.approx([5.4, 2.2, 4.2], abs=0.001),
                "forward": pytest.approx([0.0, -1.0, 0.0], abs=0.001),
                "up": pytest.approx([0.0, 0.0, 1.0], abs=0.001),
                "mode": "Overlaps",
                "test_type": "Bounding box",
            }
            launch_transform = _runtime_trigger_transform(bng, "launch_trigger")
            assert launch_transform == {
                "ok": True,
                "position": pytest.approx([0.0, 0.0, surface_z + 2.1], abs=0.03),
                "scale": pytest.approx([5.8, 17.5, 4.6], abs=0.001),
                "forward": pytest.approx([0.0, -1.0, 0.0], abs=0.001),
                "up": pytest.approx([0.0, 0.0, 1.0], abs=0.001),
                "mode": "Contains",
                "test_type": "Bounding box",
            }

            # Exercise the wash as a true occupancy set. Two compact vehicles
            # overlap the entrance end without reaching the launch or repair
            # zones. Removing either one must leave every roller and particle
            # layer active for the remaining occupant.
            occupant_positions = (
                (
                    occupant_a,
                    OCCUPANT_A_NAME,
                    (
                        -1.65,
                        7.6,
                        surface_z + _vehicle_origin_clearance(bng, OCCUPANT_A_NAME) + 0.02,
                    ),
                ),
                (
                    occupant_b,
                    OCCUPANT_B_NAME,
                    (1.65, 7.6, surface_z + _vehicle_origin_clearance(bng, OCCUPANT_B_NAME) + 0.02),
                ),
            )
            for occupant, _name, position in occupant_positions:
                assert (
                    bng.vehicles.teleport(
                        occupant,
                        position,
                        SUBJECT_ROTATION,
                        True,
                    )
                    is True
                )
                _set_subject_frozen(occupant, True)
            occupancy_two = _wait_for_occupancy(bng, count=2, active=True)
            assert occupancy_two["effect_active_count"] == 16
            assert occupancy_two["emitter_active_counts"] == EXPECTED_EMITTER_COUNTS
            assert str(occupancy_two["visual_play_ambient"]).casefold() in {"1", "true"}

            assert (
                bng.vehicles.teleport(
                    occupant_a,
                    (-10.0, 25.0, occupant_positions[0][2][2]),
                    SUBJECT_ROTATION,
                    True,
                )
                is True
            )
            occupancy_one = _wait_for_occupancy(bng, count=1, active=True)
            assert occupancy_one["effect_active_count"] == 16
            assert occupancy_one["emitter_active_counts"] == EXPECTED_EMITTER_COUNTS
            assert str(occupancy_one["visual_play_ambient"]).casefold() in {"1", "true"}

            assert (
                bng.vehicles.teleport(
                    occupant_b,
                    (10.0, 25.0, occupant_positions[1][2][2]),
                    SUBJECT_ROTATION,
                    True,
                )
                is True
            )
            occupancy_zero = _wait_for_occupancy(bng, count=0, active=False)
            assert occupancy_zero["effect_active_count"] == 0
            assert str(occupancy_zero["visual_play_ambient"]).casefold() in {"0", "false"}
            bng.vehicles.despawn(occupant_a)
            bng.vehicles.despawn(occupant_b)

            placement = _lua_json(
                bng,
                f"local subject = scenetree.findObject({SUBJECT_NAME!r}); "
                "local rayStart = vec3(0, 12.5, 200); "
                "local rayDistance = castRayStatic(rayStart, vec3(0, 0, -1), 300); "
                "local surfaceZ = rayStart.z - rayDistance; "
                "local box = subject:getSpawnWorldOOBB(); local minimumZ = math.huge; "
                "for index = 0, 7 do minimumZ = math.min(minimumZ, box:getPoint(index).z) end; "
                "local position = subject:getPosition(); "
                "return jsonEncode({surface_z = surfaceZ, "
                "origin_clearance = position.z - minimumZ})",
            )
            assert placement["surface_z"] == pytest.approx(surface_z, abs=0.03)
            origin_clearance = float(placement["origin_clearance"])
            assert 0.2 <= origin_clearance <= 2.0
            grounded_subject_position = (
                SUBJECT_MEASUREMENT_POSITION[0],
                SUBJECT_MEASUREMENT_POSITION[1],
                float(placement["surface_z"]) + origin_clearance + 0.02,
            )
            teleported = bng.vehicles.teleport(
                subject,
                grounded_subject_position,
                SUBJECT_ROTATION,
                True,
            )
            assert teleported is True
            bng.control.step(30, wait=True)
            grounded = _subject_pose(bng)
            assert grounded["ok"] is True
            assert grounded["minimum_z"] == pytest.approx(surface_z, abs=0.08)
            assert 0.02 <= abs(float(grounded["direction"][0])) <= 0.08, grounded
            assert grounded["direction"][1] <= -0.99, grounded
            assert grounded["direction"][2] == pytest.approx(0.0, abs=0.02)

            clean_integrity = _subject_integrity_state(subject)
            assert clean_integrity["damage"] == pytest.approx(0.0, abs=0.01)
            assert clean_integrity["part_damage_count"] == 0
            assert clean_integrity["broken_beam_count"] == 0
            assert clean_integrity["deflated_tire_count"] == 0
            induced_damage = _damage_subject_for_repair(subject)
            bng.control.step(12, wait=True)
            damaged_integrity = _subject_integrity_state(subject)
            assert damaged_integrity["damage"] > 0.01, damaged_integrity
            assert damaged_integrity["part_damage_count"] > 0, damaged_integrity
            assert damaged_integrity["broken_beam_count"] >= 3, damaged_integrity
            assert damaged_integrity["deflated_tire_count"] > 0, damaged_integrity

            subject.control(
                throttle=0.0,
                brake=0.0,
                parkingbrake=0.0,
                steering=0.0,
                is_adas=True,
            )
            trajectory: list[dict[str, Any]] = []
            active_snapshot: dict[str, Any] | None = None
            for _ in range(300):
                direction = _inject_forward_velocity(bng, APPROACH_SPEED_MPS)
                assert direction[0] == pytest.approx(0.0, abs=0.05)
                assert direction[1] <= -0.98, direction
                assert direction[2] == pytest.approx(0.0, abs=0.05)
                bng.control.step(3, wait=True)
                runtime_state = _runtime_state(bng)
                _remember_trajectory(
                    trajectory,
                    _trajectory_sample(bng, subject, runtime_state, "wash_approach"),
                )
                if runtime_state.get("wash_active"):
                    active_snapshot = runtime_state
                    break

            assert active_snapshot is not None, {
                "runtime_state": runtime_state,
                "trajectory": trajectory,
                "events": _runtime_log_events(log_path, log_start)[0],
            }
            _inject_forward_velocity(bng, 0.0)
            bng.control.step(6, wait=True)
            active_snapshot = _runtime_state(bng)
            _remember_trajectory(
                trajectory,
                _trajectory_sample(bng, subject, active_snapshot, "wash_hold"),
            )
            assert active_snapshot["wash_active"] is True, {
                "runtime_state": active_snapshot,
                "trajectory": trajectory,
            }
            assert active_snapshot["effect_active_count"] == 16
            assert active_snapshot["emitter_active_counts"] == EXPECTED_EMITTER_COUNTS
            assert str(active_snapshot["visual_play_ambient"]).casefold() in {"1", "true"}

            subject.control(
                throttle=0.0,
                brake=1.0,
                parkingbrake=1.0,
                steering=0.0,
                is_adas=True,
            )
            _inject_forward_velocity(bng, 0.0)
            _set_subject_frozen(subject, True)
            bng.control.step(12, wait=True)
            stopped_before = _subject_state(subject)
            assert math.sqrt(sum(value * value for value in stopped_before["velocity"])) <= 0.15, (
                stopped_before
            )
            _request_fixed_camera_capture(
                bng,
                relative_path=capture_relative_directory / first_capture_path.name,
                render_view_name=f"cannonRuntimeActiveFirst{suffix}",
                surface_z=surface_z,
            )
            first_capture = _wait_for_capture(bng, first_capture_path)
            bng.control.step(30, wait=True)
            _inject_forward_velocity(bng, 0.0)
            _request_fixed_camera_capture(
                bng,
                relative_path=capture_relative_directory / second_capture_path.name,
                render_view_name=f"cannonRuntimeActiveSecond{suffix}",
                surface_z=surface_z,
            )
            second_capture = _wait_for_capture(bng, second_capture_path)
            first_capture.save(tmp_path / "cannon-runtime-active-first.png")
            second_capture.save(tmp_path / "cannon-runtime-active-second.png")
            stopped_after = _subject_state(subject)
            assert math.sqrt(sum(value * value for value in stopped_after["velocity"])) <= 0.15, (
                stopped_after
            )
            capture_runtime_state = _runtime_state(bng)
            assert capture_runtime_state["wash_active"] is True
            assert capture_runtime_state["effect_active_count"] == 16
            assert capture_runtime_state["emitter_active_counts"] == EXPECTED_EMITTER_COUNTS
            assert str(capture_runtime_state["visual_play_ambient"]).casefold() in {
                "1",
                "true",
            }
            render_difference = _assert_temporal_pixel_difference(first_capture, second_capture)
            pre_midpoint_integrity = _subject_integrity_state(subject)
            pre_midpoint_pose = _subject_pose(bng)
            assert pre_midpoint_integrity["damage"] > 0.01
            assert pre_midpoint_integrity["broken_beam_count"] >= 3
            assert pre_midpoint_integrity["deflated_tire_count"] > 0
            assert pre_midpoint_pose["position"][1] > 1.1, pre_midpoint_pose
            trigger_forward = [float(value) for value in repair_transform["forward"]]
            trigger_up = [float(value) for value in repair_transform["up"]]
            incoming_direction = [float(value) for value in pre_midpoint_pose["direction"]]
            incoming_trigger_dot = sum(
                incoming_direction[axis] * trigger_forward[axis] for axis in range(3)
            )
            expected_corridor_direction = [
                value if incoming_trigger_dot >= 0 else -value for value in trigger_forward
            ]
            corridor_right = [
                expected_corridor_direction[1] * trigger_up[2]
                - expected_corridor_direction[2] * trigger_up[1],
                expected_corridor_direction[2] * trigger_up[0]
                - expected_corridor_direction[0] * trigger_up[2],
                expected_corridor_direction[0] * trigger_up[1]
                - expected_corridor_direction[1] * trigger_up[0],
            ]
            right_length = math.sqrt(sum(value * value for value in corridor_right))
            corridor_right = [value / right_length for value in corridor_right]
            repair_center = [float(value) for value in repair_transform["position"]]
            # Reference-cluster position, not the OOBB center: heavy body
            # deformation moves the bounding box while the restored reference
            # position is what the pose policy preserves.
            centerline_error_before = abs(
                sum(
                    (float(pre_midpoint_pose["position"][axis]) - repair_center[axis])
                    * corridor_right[axis]
                    for axis in range(3)
                )
            )
            assert centerline_error_before >= 0.05, pre_midpoint_pose
            assert (
                sum(
                    incoming_direction[axis] * expected_corridor_direction[axis]
                    for axis in range(3)
                )
                > 0
            )
            _set_subject_frozen(subject, False)
            subject.control(
                throttle=0.0,
                brake=0.0,
                parkingbrake=0.0,
                steering=0.0,
                is_adas=True,
            )

            repair_pending_observed = False
            repair_complete_snapshot: dict[str, Any] | None = None
            repaired_integrity: dict[str, Any] | None = None
            repaired_pose: dict[str, Any] | None = None
            repair_pose_samples: list[dict[str, Any]] = []
            countdown_snapshot: dict[str, Any] | None = None
            for _ in range(900):
                # Once the runtime has acknowledged the repair trigger, stop
                # applying external cluster velocity until its reset/pose/verify
                # handshake completes. Controller freeze cannot cancel a direct
                # test-side physics injection, and doing so would fight the very
                # alignment policy this gate is intended to measure.
                repair_is_settling = repair_pending_observed and repair_complete_snapshot is None
                if not repair_is_settling:
                    _inject_forward_velocity(bng, APPROACH_SPEED_MPS)
                # Sample every simulation frame so the two-frame repair settle
                # window and its acknowledgement boundary cannot be skipped.
                bng.control.step(1, wait=True)
                runtime_state = _runtime_state(bng)
                repair_pending_observed = repair_pending_observed or (
                    int(runtime_state.get("repair_pending_count", 0)) > 0
                )
                pose_sample = _trajectory_sample(bng, subject, runtime_state, "launch_approach")
                _remember_trajectory(trajectory, pose_sample)
                if int(runtime_state.get("repair_pending_count", 0)) > 0 or (
                    repair_pending_observed and repair_complete_snapshot is None
                ):
                    repair_pose_samples.append(pose_sample)
                if (
                    runtime_state.get("repaired_subject_count") == 1
                    and runtime_state.get("repair_pending_count") == 0
                    and repair_complete_snapshot is None
                ):
                    repair_complete_snapshot = runtime_state
                    repaired_integrity = _subject_integrity_state(subject)
                    repaired_pose = _subject_pose(bng)
                if (
                    repair_complete_snapshot is not None
                    and runtime_state.get("active_phase") == "countdown"
                ):
                    countdown_snapshot = runtime_state
                    break

            assert repair_complete_snapshot is not None, {
                "runtime_state": runtime_state,
                "trajectory": trajectory,
                "events": _runtime_log_events(log_path, log_start)[0],
            }
            assert repair_pending_observed is True
            assert repair_complete_snapshot["repair_pending_count"] == 0
            assert repair_complete_snapshot["repaired_subject_count"] == 1
            assert repair_complete_snapshot["wash_active"] is True
            assert repair_complete_snapshot["effect_active_count"] == 16
            assert repair_complete_snapshot["emitter_active_counts"] == EXPECTED_EMITTER_COUNTS
            assert repaired_integrity is not None
            assert repaired_integrity["damage"] == pytest.approx(0.0, abs=0.01)
            assert repaired_integrity["part_damage"] == []
            assert repaired_integrity["part_damage_count"] == 0
            assert repaired_integrity["broken_beam_count"] == 0
            assert repaired_integrity["deflated_tire_count"] == 0
            assert repaired_pose is not None and repaired_pose["ok"] is True
            repaired_direction = [float(value) for value in repaired_pose["direction"]]
            repaired_up = [float(value) for value in repaired_pose["up"]]
            repaired_centerline_error = abs(
                sum(
                    (float(repaired_pose["position"][axis]) - repair_center[axis])
                    * corridor_right[axis]
                    for axis in range(3)
                )
            )
            repaired_upright_dot = sum(repaired_up[axis] * trigger_up[axis] for axis in range(3))
            repaired_travel_dot = sum(
                repaired_direction[axis] * incoming_direction[axis] for axis in range(3)
            )
            # Pose preservation: the pre-midpoint sample is taken while the
            # bus is still driving at a slight angle, so exact lateral
            # equality cannot be asserted from here (the runtime's own
            # position-drift metric, asserted below, is the precise
            # instrument). This independent check refutes the old centering
            # behavior: the deliberate off-center offset must survive instead
            # of collapsing toward zero.
            assert repaired_centerline_error >= 0.5 * centerline_error_before, repaired_pose
            assert repaired_centerline_error <= centerline_error_before + 0.5, repaired_pose
            # Horizontal headings only: reinflating tires legitimately changes
            # pitch, so the full 3D travel dot cannot bind the repaired pose.
            flat_repaired = [repaired_direction[0], repaired_direction[1]]
            flat_incoming = [incoming_direction[0], incoming_direction[1]]
            flat_norm = math.sqrt(sum(v * v for v in flat_repaired)) * math.sqrt(
                sum(v * v for v in flat_incoming)
            )
            repaired_heading_dot = (
                flat_repaired[0] * flat_incoming[0] + flat_repaired[1] * flat_incoming[1]
            ) / flat_norm
            assert repaired_upright_dot >= 0.98, repaired_pose
            assert repaired_heading_dot >= 0.995, repaired_pose
            assert repair_pose_samples
            assert all(
                sum(
                    float(sample["direction"][axis]) * incoming_direction[axis] for axis in range(3)
                )
                > 0
                for sample in repair_pose_samples
            ), repair_pose_samples

            assert countdown_snapshot is not None, {
                "runtime_state": runtime_state,
                "trajectory": trajectory,
                "events": _runtime_log_events(log_path, log_start)[0],
            }
            assert countdown_snapshot["active_phase"] == "countdown"
            assert countdown_snapshot["repaired_subject_count"] == 1
            assert countdown_snapshot["repair_pending_count"] == 0
            launch_containment = _launch_containment_state(bng)
            assert launch_containment["ok"] is True, launch_containment
            containment_tolerance = 0.06
            for axis in range(3):
                trigger_minimum = (
                    float(launch_containment["center"][axis])
                    - float(launch_containment["scale"][axis]) / 2.0
                )
                trigger_maximum = (
                    float(launch_containment["center"][axis])
                    + float(launch_containment["scale"][axis]) / 2.0
                )
                assert float(launch_containment["vehicle_min"][axis]) >= (
                    trigger_minimum - containment_tolerance
                ), launch_containment
                assert float(launch_containment["vehicle_max"][axis]) <= (
                    trigger_maximum + containment_tolerance
                ), launch_containment

            pre_go_integrity_baseline = _subject_integrity_state(subject)
            assert pre_go_integrity_baseline["controller_frozen"] is True
            pre_go_integrity_samples: list[dict[str, Any]] = [
                {
                    "phase": str(countdown_snapshot["active_phase"]),
                    **pre_go_integrity_baseline,
                }
            ]
            peak_speed = 0.0
            peak_velocity = [0.0, 0.0, 0.0]
            for _ in range(900):
                # A one-frame cadence is deliberate: release_grace is only two
                # simulation frames and is the critical boundary where the
                # controller must already be unfrozen but launch is not applied.
                bng.control.step(1, wait=True)
                runtime_state = _runtime_state(bng)
                active_phase = runtime_state.get("active_phase")
                integrity_state = _subject_integrity_state(subject)
                if active_phase in {
                    "hold_pending",
                    "countdown",
                    "release_pending",
                    "release_grace",
                }:
                    pre_go_integrity_samples.append({"phase": str(active_phase), **integrity_state})
                subject_state = _subject_state(subject)
                speed = math.sqrt(sum(value * value for value in subject_state["velocity"]))
                if speed > peak_speed:
                    peak_speed = speed
                    peak_velocity = subject_state["velocity"]
                _remember_trajectory(
                    trajectory,
                    _trajectory_sample(bng, subject, runtime_state, "countdown_launch"),
                )
                if peak_speed >= 83.33:
                    break

            assert any(sample["phase"] == "release_grace" for sample in pre_go_integrity_samples), (
                pre_go_integrity_samples
            )
            countdown_integrity_samples = [
                sample for sample in pre_go_integrity_samples if sample["phase"] == "countdown"
            ]
            release_grace_integrity_samples = [
                sample for sample in pre_go_integrity_samples if sample["phase"] == "release_grace"
            ]
            assert countdown_integrity_samples
            assert all(
                sample["controller_frozen"] is True for sample in countdown_integrity_samples
            ), countdown_integrity_samples
            assert all(
                sample["controller_frozen"] is False for sample in release_grace_integrity_samples
            ), release_grace_integrity_samples

            pre_go_damage_delta = max(
                abs(float(sample["damage"]) - pre_go_integrity_baseline["damage"])
                for sample in pre_go_integrity_samples
            )
            assert pre_go_damage_delta <= 0.01, pre_go_integrity_samples
            assert all(
                sample["part_damage"] == pre_go_integrity_baseline["part_damage"]
                and sample["part_damage_count"] == pre_go_integrity_baseline["part_damage_count"]
                and sample["broken_beam_count"] == 0
                and sample["deflated_tire_count"] == 0
                for sample in pre_go_integrity_samples
            ), pre_go_integrity_samples

            assert peak_speed >= 83.33, {
                "peak_speed_mps": peak_speed,
                "runtime_state": runtime_state,
                "trajectory": trajectory,
                "events": _runtime_log_events(log_path, log_start)[0],
            }
            assert peak_velocity[1] <= -83.0
            assert abs(peak_velocity[0]) <= 5.0

            bng.control.step(120, wait=True)
            bng.vehicles.despawn(prop)
            bng.control.step(60, wait=True)
            cleanup_state = _lua_json(
                bng,
                "local count = 0; "
                "for _, className in ipairs({'TSStatic', 'BeamNGTrigger', "
                "'ParticleEmitterNode'}) do "
                "for _, name in ipairs(scenetree.findClassObjects(className) or {}) do "
                "if string.find(name, 'ericrolph_cannon_car_wash_runtime_', 1, true) == 1 "
                "then count = count + 1 end; "
                "end; end; "
                "return jsonEncode({loaded = extensions.isExtensionLoaded("
                f"{RUNTIME_EXTENSION!r}), "
                "runtime_object_count = count})",
            )
            assert cleanup_state == {"loaded": False, "runtime_object_count": 0}

        finally:
            try:
                cleanup_owned_beamng_session(
                    bng,
                    owned_process=owned_process,
                    scenario=scenario,
                )
            finally:
                if timer is not None:
                    timer.cancel()
                cleanup_exact_live_artifacts(
                    profile=user,
                    files=(installed_zip, first_capture_path, second_capture_path),
                    empty_directories=(capture_directory, scenario_directory),
                )

    # BeamNG buffers its file logger. Parse only after the owned process has
    # closed so the unique marker and final lifecycle events are guaranteed to
    # be flushed to disk.
    records, issues = _runtime_log_records(log_path, log_start)
    events = [str(record["event"]) for record in records]
    for required in (
        "prop_registered",
        "wash_trigger_enter",
        "wash_systems_start",
        "repair_trigger_enter",
        "repair_snapshot",
        "repair_requested",
        "repair_reset_ack",
        "repair_complete",
        "containment_verified",
        "containment_exit_suppressed",
        "hold_requested",
        "hold_ack",
        "countdown_3",
        "countdown_2",
        "countdown_1",
        "release_requested",
        "release_ack",
        "go",
        "launch",
        "launch_complete",
        "release",
        "prop_reset",
        "prop_unregistered",
    ):
        assert required in events, {"missing": required, "events": events}

    subject_reset_records = [record for record in records if record["event"] == "subject_reset"]
    assert len(subject_reset_records) == 2, subject_reset_records
    assert [int(record["remaining_subject_count"]) for record in subject_reset_records] == [1, 0]
    assert subject_reset_records[0]["wash_systems_active"] is True
    assert subject_reset_records[1]["wash_systems_active"] is False
    vehicle_reset_aborts = [
        record
        for record in records
        if record["event"] == "abort" and record.get("reason") == "vehicle_reset"
    ]
    assert vehicle_reset_aborts == [], records
    assert "abort" not in events, records

    repair_event_names = (
        "repair_trigger_enter",
        "repair_snapshot",
        "repair_requested",
        "repair_reset_ack",
        "repair_complete",
    )
    repair_records: dict[str, dict[str, Any]] = {}
    repair_indices: list[int] = []
    for event_name in repair_event_names:
        matches = [
            (index, record) for index, record in enumerate(records) if record["event"] == event_name
        ]
        assert len(matches) == 1, {"event": event_name, "records": records}
        repair_indices.append(matches[0][0])
        repair_records[event_name] = matches[0][1]
    assert repair_indices == sorted(repair_indices)
    repair_token = repair_records["repair_trigger_enter"]["repair_token"]
    assert all(record["repair_token"] == repair_token for record in repair_records.values())
    assert repair_records["repair_requested"]["strategy"] == "RESET_PHYSICS"
    before_repair = repair_records["repair_snapshot"]
    after_repair = repair_records["repair_complete"]
    assert float(before_repair["damage_before"]) > 0.01
    assert int(before_repair["part_damage_before"]) > 0
    assert int(before_repair["broken_beams_before"]) >= 3
    assert int(before_repair["deflated_tires_before"]) > 0
    assert float(after_repair["damage_after"]) == pytest.approx(0.0, abs=0.01)
    assert int(after_repair["part_damage_after"]) == 0
    assert int(after_repair["broken_beams_after"]) == 0
    assert int(after_repair["deflated_tires_after"]) == 0
    assert after_repair["pose_policy"] == "restore_exact_pre_repair_pose"
    assert float(after_repair["position_drift_m"]) <= 0.15
    assert float(after_repair["heading_dot"]) >= 0.995
    assert float(after_repair["upright_dot"]) >= 0.98
    assert after_repair["travel_sign_preserved"] is True

    prop_reset_records = [record for record in records if record["event"] == "prop_reset"]
    assert len(prop_reset_records) >= 2, records
    assert all(record["armed"] is True for record in prop_reset_records)

    containment_indices = [
        index for index, record in enumerate(records) if record["event"] == "containment_verified"
    ]
    assert len(containment_indices) == 1, records
    assert repair_indices[-1] < containment_indices[0]
    final_start = repair_indices[0]
    final_records = records[final_start:]
    final_events = [str(record["event"]) for record in final_records]
    assert "abort" not in final_events, final_records

    timed_event_names = ("countdown_3", "countdown_2", "countdown_1", "go")
    timed_records: list[dict[str, Any]] = []
    timed_indices: list[int] = []
    for event_name in timed_event_names:
        matches = [
            (index, record)
            for index, record in enumerate(final_records)
            if record["event"] == event_name
        ]
        assert len(matches) == 1, {"event": event_name, "records": final_records}
        timed_indices.append(matches[0][0])
        timed_records.append(matches[0][1])
    assert timed_indices == sorted(timed_indices)
    countdown_start_time = float(timed_records[0]["log_time_seconds"])
    elapsed_log_times = [
        float(record["log_time_seconds"]) - countdown_start_time for record in timed_records
    ]
    assert elapsed_log_times == pytest.approx((0.0, 1.0, 2.0, 3.0), abs=0.35)
    assert [float(record["elapsed_time_seconds"]) for record in timed_records[:3]] == pytest.approx(
        (0.0, 1.0, 2.0), abs=0.25
    )

    launch_index = next(
        index for index, record in enumerate(final_records) if record["event"] == "launch"
    )
    launch_complete_index = next(
        index for index, record in enumerate(final_records) if record["event"] == "launch_complete"
    )
    cleanup_index = next(
        index
        for index, record in enumerate(final_records)
        if record["event"] == "prop_unregistered"
    )
    ordered_launch_events = (
        "hold_requested",
        "hold_ack",
        "countdown_3",
        "countdown_2",
        "countdown_1",
        "release_requested",
        "release_ack",
        "go",
        "launch",
    )
    ordered_launch_indices: list[int] = []
    for event_name in ordered_launch_events:
        matches = [
            index for index, record in enumerate(final_records) if record["event"] == event_name
        ]
        assert len(matches) == 1, {"event": event_name, "records": final_records}
        ordered_launch_indices.append(matches[0])
    assert ordered_launch_indices == sorted(ordered_launch_indices)
    assert timed_indices[-1] < launch_index < launch_complete_index < cleanup_index
    assert float(final_records[launch_index]["target_speed_mps"]) >= 100.0
    assert issues == []
    print(
        "CANNON_SELECTOR_RUNTIME_TELEMETRY "
        + json.dumps(
            {
                "level": "smallgrid",
                "surface_z": surface_z,
                "subject_model": "citybus",
                "subject_configuration": "city",
                "sequence_names": asset_state["sequence_names"],
                "material_count": len(asset_state["materials"]),
                "effect_active_count": countdown_snapshot["effect_active_count"],
                "emitter_active_counts": countdown_snapshot["emitter_active_counts"],
                "rotated_effect_orientation": {
                    "rotation_quaternion": PROP_ROTATED_QUATERNION,
                    "present_count": effect_orientation["present_count"],
                    "minimum_inward_dot": min(
                        min(
                            float(sample["left_inward_dot"]),
                            float(sample["right_inward_dot"]),
                        )
                        for sample in effect_orientation["samples"]
                    ),
                    "samples": effect_orientation["samples"],
                },
                "render_difference": render_difference,
                "occupancy_reference_count": {
                    "two": {
                        "subject_count": occupancy_two["wash_subject_count"],
                        "wash_active": occupancy_two["wash_active"],
                        "effect_active_count": occupancy_two["effect_active_count"],
                    },
                    "one": {
                        "subject_count": occupancy_one["wash_subject_count"],
                        "wash_active": occupancy_one["wash_active"],
                        "effect_active_count": occupancy_one["effect_active_count"],
                    },
                    "zero": {
                        "subject_count": occupancy_zero["wash_subject_count"],
                        "wash_active": occupancy_zero["wash_active"],
                        "effect_active_count": occupancy_zero["effect_active_count"],
                    },
                },
                "launch_containment": launch_containment,
                "repair": {
                    "token": repair_token,
                    "pending_observed": repair_pending_observed,
                    "induced_beams": induced_damage["broken"],
                    "before": {
                        "damage": float(before_repair["damage_before"]),
                        "part_damage_count": int(before_repair["part_damage_before"]),
                        "broken_beam_count": int(before_repair["broken_beams_before"]),
                        "deflated_tire_count": int(before_repair["deflated_tires_before"]),
                    },
                    "after": {
                        "damage": float(after_repair["damage_after"]),
                        "part_damage_count": int(after_repair["part_damage_after"]),
                        "broken_beam_count": int(after_repair["broken_beams_after"]),
                        "deflated_tire_count": int(after_repair["deflated_tires_after"]),
                        "position_drift_m": float(after_repair["position_drift_m"]),
                        "direction_dot": float(after_repair["direction_dot"]),
                        "upright_dot": float(after_repair["upright_dot"]),
                        "independent_lateral_offset_delta_m": abs(
                            repaired_centerline_error - centerline_error_before
                        ),
                        "travel_sign_preserved": after_repair["travel_sign_preserved"],
                    },
                    "independent_pose_readback": {
                        "lateral_offset_before_m": centerline_error_before,
                        "lateral_offset_after_m": repaired_centerline_error,
                        "upright_dot": repaired_upright_dot,
                        "travel_direction_dot": repaired_travel_dot,
                        "repair_frame_sample_count": len(repair_pose_samples),
                    },
                    "external_after": repaired_integrity,
                    "pre_midpoint_integrity": pre_midpoint_integrity,
                    "pre_midpoint_pose": pre_midpoint_pose,
                    "ordered_events": list(repair_event_names),
                },
                "prop_reset_count": max(
                    int(record["reset_count"]) for record in prop_reset_records
                ),
                "countdown_log_elapsed_seconds": elapsed_log_times,
                "countdown_structured_elapsed_seconds": [
                    float(record["elapsed_time_seconds"]) for record in timed_records[:3]
                ],
                "pre_go_integrity": {
                    "baseline_damage": pre_go_integrity_baseline["damage"],
                    "maximum_damage_delta": pre_go_damage_delta,
                    "part_damage_count": pre_go_integrity_baseline["part_damage_count"],
                    "broken_beam_count": pre_go_integrity_baseline["broken_beam_count"],
                    "deflated_tire_count": pre_go_integrity_baseline["deflated_tire_count"],
                    "sample_count": len(pre_go_integrity_samples),
                    "observed_phases": sorted(
                        {sample["phase"] for sample in pre_go_integrity_samples}
                    ),
                    "countdown_controller_frozen": all(
                        sample["controller_frozen"] is True
                        for sample in countdown_integrity_samples
                    ),
                    "release_grace_controller_unfrozen": all(
                        sample["controller_frozen"] is False
                        for sample in release_grace_integrity_samples
                    ),
                },
                "ordered_launch_events": list(ordered_launch_events),
                "peak_speed_mps": peak_speed,
                "peak_velocity_mps": peak_velocity,
                "target_speed_mps": float(final_records[launch_index]["target_speed_mps"]),
                "final_events": final_events,
                "cleanup": cleanup_state,
                "log_issues": issues,
            },
            sort_keys=True,
        )
    )
