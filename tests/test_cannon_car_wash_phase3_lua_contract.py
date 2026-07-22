from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = PROJECT_ROOT / "examples" / "cannon_car_wash"
MOD_ROOT = EXAMPLE_ROOT / "mod"
MOD_ID = "ericrolph_cannon_car_wash"
LAUNCH_TRIGGER_NAME = f"{MOD_ID}_launch_trigger"
WASH_TRIGGER_NAME = f"{MOD_ID}_wash_activation_trigger"
REPAIR_TRIGGER_NAME = f"{MOD_ID}_repair_trigger"
TRUCK_NAME = f"{MOD_ID}_truck"
SCENARIO_VISUAL_NAME = f"{MOD_ID}_scenario_visual"
CRASH_WALL_NAME = f"{MOD_ID}_crash_wall"
EXTENSION_REGISTRY_NAME = f"scenario_{MOD_ID}"
SCENARIO_DIRECTORY = MOD_ROOT / "levels" / "gridmap_v2" / "scenarios" / MOD_ID
SCENARIO = SCENARIO_DIRECTORY / f"{MOD_ID}.json"
EXTENSION = SCENARIO_DIRECTORY / f"{MOD_ID}.lua"
PHASE3_MANIFEST = EXAMPLE_ROOT / "validation" / "manifests" / "phase3.json"
PREFAB = SCENARIO_DIRECTORY / f"{MOD_ID}.prefab.json"


def extension_source() -> str:
    return EXTENSION.read_text(encoding="utf-8")


def _lua_string(source: str, name: str) -> str:
    match = re.search(
        rf"\blocal\s+{re.escape(name)}\s*=\s*([\"'])(?P<value>.*?)\1",
        source,
    )
    assert match is not None, f"missing local Lua string constant {name}"
    return match.group("value")


def _lua_number(source: str, name: str) -> float:
    match = re.search(
        rf"\blocal\s+{re.escape(name)}\s*=\s*(?P<value>\d+(?:\.\d+)?)\b",
        source,
    )
    assert match is not None, f"missing local Lua numeric constant {name}"
    return float(match.group("value"))


def _function_tail(source: str, name: str) -> str:
    """Return source from a named local/exported Lua function onward.

    This deliberately does not pretend to be a Lua parser.  Contract assertions
    use the tail only for ordering; exact engine calls are matched against the
    complete source so nested helpers remain an implementation choice.
    """

    match = re.search(
        rf"(?:(?:local\s+function|function\s+M\.)\s*{name}\s*\(|"
        rf"\b{name}\s*=\s*function\s*\()",
        source,
    )
    assert match is not None, f"missing Lua function {name}"
    return source[match.start() :]


def _function_section(source: str, name: str) -> str:
    """Return one named top-level Lua function without later functions."""

    match = re.search(
        rf"(?:(?:local\s+function|function\s+M\.)\s*{name}\s*\(|"
        rf"\b{name}\s*=\s*function\s*\()",
        source,
    )
    assert match is not None, f"missing Lua function {name}"
    next_function = re.search(
        r"\n(?:(?:local\s+function|function\s+M\.)\s+[A-Za-z_]\w*\s*\(|"
        r"[A-Za-z_]\w*\s*=\s*function\s*\()",
        source[match.end() :],
    )
    if next_function is None:
        return source[match.start() :]
    return source[match.start() : match.end() + next_function.start()]


def test_phase3_payload_uses_the_scenario_owned_extension_lifecycle() -> None:
    assert EXTENSION.is_file()
    assert SCENARIO.is_file()
    assert PREFAB.is_file()

    scenarios = json.loads(SCENARIO.read_text(encoding="utf-8"))
    assert len(scenarios) == 1
    assert scenarios[0]["extensions"] == [{"name": MOD_ID}]
    assert not (MOD_ROOT / "lua" / "ge" / "extensions" / MOD_ID / "main.lua").exists()
    assert not (MOD_ROOT / "scripts" / MOD_ID / "modScript.lua").exists()

    prefab = [
        json.loads(line) for line in PREFAB.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    prefab_by_name = {record["name"]: record for record in prefab}
    assert prefab_by_name[SCENARIO_VISUAL_NAME]["class"] == "TSStatic"
    assert prefab_by_name[CRASH_WALL_NAME]["class"] == "TSStatic"
    launch_trigger = prefab_by_name[LAUNCH_TRIGGER_NAME]
    assert launch_trigger["class"] == "BeamNGTrigger"
    assert launch_trigger["luaFunction"] == "onBeamNGTrigger"
    assert launch_trigger["triggerMode"] == "Contains"
    assert launch_trigger["triggerTestType"] == "Bounding box"

    wash_trigger = prefab_by_name[WASH_TRIGGER_NAME]
    assert wash_trigger["class"] == "BeamNGTrigger"
    assert wash_trigger["luaFunction"] == "onBeamNGTrigger"
    assert wash_trigger["triggerMode"] == "Overlaps"
    assert wash_trigger["triggerTestType"] == "Bounding box"

    repair_trigger = prefab_by_name[REPAIR_TRIGGER_NAME]
    assert repair_trigger["class"] == "BeamNGTrigger"
    assert repair_trigger["position"] == [-122.011475, -170.0, 102.1]
    assert repair_trigger["scale"] == [5.4, 2.2, 4.2]
    assert repair_trigger["luaFunction"] == "onBeamNGTrigger"
    assert repair_trigger["triggerMode"] == "Overlaps"
    assert repair_trigger["triggerTestType"] == "Bounding box"

    # ParticleEmitterNode emits along the third (local +Z) matrix column.
    # Each left/right nozzle must point toward the wash centerline.
    effects = [record for record in prefab if record["class"] == "ParticleEmitterNode"]
    assert len(effects) == 16
    assert Counter(effect["emitter"] for effect in effects) == {
        "BNGP_sprinkler": 6,
        "BNGP_waterfallsteam": 6,
        "BNGP_34": 2,
        "BNGP_2": 2,
    }
    for effect in effects:
        local_x = float(effect["position"][0]) - float(
            prefab_by_name[SCENARIO_VISUAL_NAME]["position"][0]
        )
        emission_axis = [float(value) for value in effect["rotationMatrix"][6:9]]
        inward_x = -1.0 if local_x > 0 else 1.0
        magnitude = sum(value * value for value in emission_axis) ** 0.5
        inward_dot = emission_axis[0] * inward_x / magnitude
        assert inward_dot > 0.999, effect

    source = extension_source()
    assert "setExtensionUnloadMode" not in source
    assert "extensions.load" not in source
    assert "loadstring" not in source.lower()
    assert "dofile" not in source.lower()
    for callback in (
        "onBeamNGTrigger",
        "onPreRender",
        "onClientStartMission",
        "onClientEndMission",
        "onVehicleResetted",
        "onExtensionLoaded",
        "onExtensionUnloaded",
        "onEricrolphCannonCarWashScenarioRepairIntegrityAcknowledged",
    ):
        _function_tail(source, callback)
        assert f"M.{callback}" in source


def test_trigger_callback_requires_exact_live_triggers_and_accepts_any_live_vehicle() -> None:
    source = extension_source()
    dispatch = _function_section(source, "onBeamNGTrigger")
    launch_callback = _function_section(source, "handleLaunchTrigger")
    repair_callback = _function_section(source, "handleRepairTrigger")
    trigger_resolver = _function_section(source, "exactTriggerFromEvent")
    vehicle_resolver = _function_section(source, "exactVehicleFromEvent")

    assert _lua_string(source, "LAUNCH_TRIGGER_NAME") == LAUNCH_TRIGGER_NAME
    assert _lua_string(source, "WASH_TRIGGER_NAME") == WASH_TRIGGER_NAME
    assert _lua_string(source, "REPAIR_TRIGGER_NAME") == REPAIR_TRIGGER_NAME

    assert "handleWashTrigger(data)" in dispatch
    assert "handleRepairTrigger(data)" in dispatch
    assert "handleLaunchTrigger(data)" in dispatch
    assert "data.triggerName == WASH_TRIGGER_NAME" in dispatch
    assert "data.triggerName == REPAIR_TRIGGER_NAME" in dispatch
    assert "data.triggerName == LAUNCH_TRIGGER_NAME" in dispatch

    # Do not accept an event solely because its user-controlled names happen to
    # match.  Resolve both live objects and bind the event to their numeric IDs.
    assert "data.triggerName" in launch_callback
    assert "data.triggerID" in launch_callback
    assert "data.subjectID" in launch_callback
    assert 'exactTriggerFromEvent(data, LAUNCH_TRIGGER_NAME, "Contains")' in launch_callback
    assert 'exactTriggerFromEvent(data, WASH_TRIGGER_NAME, "Overlaps")' in source
    assert 'exactTriggerFromEvent(data, REPAIR_TRIGGER_NAME, "Overlaps")' in repair_callback
    assert re.search(r"scenetree\.findObject\s*\(\s*expectedName\s*\)", trigger_resolver)
    assert re.search(r"scenetree\.findObjectById\s*\(\s*data\.triggerID\s*\)", trigger_resolver)
    assert re.search(
        r"\w+:getClassName\(\)\s*~=\s*(?:TRIGGER_CLASS|[\"']BeamNGTrigger[\"'])",
        trigger_resolver,
    )
    assert re.search(r"\w+:getId\(\)\s*~=\s*data\.triggerID", trigger_resolver)
    assert 'getField("triggerMode", 0) ~= expectedMode' in trigger_resolver
    assert 'getField("triggerTestType", 0) ~= "Bounding box"' in trigger_resolver
    assert re.search(
        r"(?:be:getObjectByID|scenetree\.findObjectById)\s*\(\s*data\.subjectID\s*\)",
        vehicle_resolver,
    )
    assert re.search(r"\w+:getId\(\)\s*~=\s*data\.subjectID", vehicle_resolver)
    assert "exactVehicleFromEvent(data)" in launch_callback
    assert "exactVehicleFromEvent(data)" in repair_callback
    for forbidden_identity in ("TRUCK_NAME", "TRUCK_MODEL", "exactTruckFromEvent"):
        assert forbidden_identity not in source

    enter_guard = re.search(r"data\.event\s*~=\s*[\"']enter[\"']", launch_callback)
    assert enter_guard is not None
    assert '"containment_exit_suppressed"' in launch_callback
    assert "washSubjects[data.subjectID]" in launch_callback
    assert "washSystemsActive" in launch_callback
    assert launch_callback.index("data.triggerName") < launch_callback.index("hold_requested")


def test_wash_trigger_controls_rollers_water_and_layered_dryer_effects() -> None:
    source = extension_source()
    wash_callback = _function_section(source, "handleWashTrigger")
    wash_systems = _function_section(source, "setWashSystemsEnabled")
    wash_resolver = _function_section(source, "resolveWashObjects")
    wash_rollback = _function_section(source, "forceWashSystemsOff")
    ambient_control = _function_section(source, "setVisualAmbient")
    remove_subject = _function_section(source, "removeWashSubject")

    assert _lua_string(source, "VISUAL_NAME") == SCENARIO_VISUAL_NAME
    assert _lua_string(source, "VISUAL_CLASS") == "TSStatic"
    emitter_class = re.search(
        r"local\s+(?:EFFECT|MISTER)_CLASS\s*=\s*([\"'])ParticleEmitterNode\1",
        source,
    )
    assert emitter_class is not None

    effect_table = re.search(
        r"local\s+EFFECT_SPECS\s*=\s*\{(?P<body>.*?)\n\}",
        source,
        flags=re.DOTALL,
    )
    assert effect_table is not None
    effect_names = re.findall(r"\bname\s*=\s*[\"']([^\"']+)[\"']", effect_table.group("body"))
    assert len(effect_names) == 16
    assert set(effect_names) == (
        {
            f"{MOD_ID}_mister_PreSoak_{side}_{height}"
            for side in ("L", "R")
            for height in range(1, 4)
        }
        | {f"{MOD_ID}_dryer_Mist_{side}_{height}" for side in ("L", "R") for height in range(1, 4)}
        | {f"{MOD_ID}_dryer_{layer}_{side}" for layer in ("Steam", "Dust") for side in ("L", "R")}
    )
    assert Counter(
        re.findall(r"\bemitter\s*=\s*[\"']([^\"']+)[\"']", effect_table.group("body"))
    ) == {
        "BNGP_sprinkler": 6,
        "BNGP_waterfallsteam": 6,
        "BNGP_34": 2,
        "BNGP_2": 2,
    }

    assert "setVisualAmbient(visual, enabled)" in wash_systems
    assert 'visual:setField("playAmbient", 0, enabled and "1" or "0")' in ambient_control
    assert "visual:preApply()" in ambient_control
    assert "visual:postApply()" in ambient_control
    assert "exactSceneObject(spec.name, EFFECT_CLASS)" in wash_resolver
    assert 'effect:getField("emitter", 0) == spec.emitter' in wash_resolver
    assert "effect:setActive(enabled)" in wash_systems
    assert "resolveWashObjects()" in wash_systems
    assert wash_systems.count("forceWashSystemsOff(visual, effects)") >= 2
    assert "setVisualAmbient(visual, false)" in wash_rollback
    assert "effect:setActive(false)" in wash_rollback
    assert "washSystemsActive = false" in wash_rollback
    for emitter in ("BNGP_sprinkler", "BNGP_waterfallsteam", "BNGP_34", "BNGP_2"):
        assert emitter in source
    assert re.search(r"effect_count\s*=\s*#EFFECT_SPECS", wash_systems)

    assert re.search(r"washSubjects\[data\.subjectID\]\s*=\s*true", wash_callback)
    assert 'removeWashSubject(data.subjectID, "last_vehicle_exit")' in wash_callback
    assert re.search(r"washSubjects\[vehicleId\]\s*=\s*nil", remove_subject)
    assert 'setWashSystemsEnabled(true, "vehicle_enter", true)' in wash_callback
    assert re.search(
        r"washSubjectCount\(\)\s*==\s*0\s+and\s+washSystemsActive",
        remove_subject,
    )
    assert "setWashSystemsEnabled(false, reason, true)" in remove_subject
    for event in (
        "wash_trigger_enter",
        "wash_systems_start",
        "wash_trigger_exit",
        "wash_systems_stop",
    ):
        assert f'"{event}"' in source or f"'{event}'" in source

    assert re.search(r"M\.getSystemState\s*=\s*washSystemState", source)


def test_repair_trigger_resets_once_and_waits_for_post_reset_integrity_ack() -> None:
    source = extension_source()
    repair_callback = _function_section(source, "handleRepairTrigger")
    wash_callback = _function_section(source, "handleWashTrigger")
    reset_callback = _function_section(source, "onVehicleResetted")
    update = _function_section(source, "onPreRender")
    pending_launch = _function_section(source, "processPendingLaunch")
    remove_subject = _function_section(source, "removeWashSubject")
    integrity_ack_name = "onEricrolphCannonCarWashScenarioRepairIntegrityAcknowledged"
    integrity_ack = _function_section(source, integrity_ack_name)
    release_ack_name = "onEricrolphCannonCarWashScenarioRepairReleaseAcknowledged"
    release_ack = _function_section(source, release_ack_name)
    launch_callback = _function_section(source, "handleLaunchTrigger")
    target_pose = _function_section(source, "repairTargetPose")
    pose_metrics = _function_section(source, "repairedPoseMetrics")

    release_start = source.index("local function releaseVehicleCommand")
    release_string_end = source.index("]]", release_start)
    integrity_helper_start = source.index("local function repairIntegrityCommand")
    assert integrity_helper_start > release_string_end
    assert "repairIntegrityCommand" not in source[release_start:release_string_end]
    integrity_helper = _function_section(source, "repairIntegrityCommand")
    assert "'%s'" in integrity_helper
    assert "%q" not in integrity_helper
    assert "ericrolphCannonCarWashScenarioRepairHoldState" in integrity_helper
    assert "controller.setFreeze(1)" in integrity_helper
    repair_release = _function_section(source, "repairReleaseCommand")
    assert "controller.setFreeze(previousFrozen and 1 or 0)" in repair_release
    assert release_ack_name in repair_release

    assert "repairOccupants" in source
    for phase in (
        "precheck_pending",
        "reset_pending",
        "pose_restore_pending",
        "settling",
        "verify_pending",
        "release_pending",
        "complete",
        "failed",
    ):
        assert f'"{phase}"' in source or f"'{phase}'" in source

    # A damaged OOBB only has to overlap the entry arch. Duplicate enter events
    # from the intentional physics reset remain latched until the vehicle leaves
    # the full wash bay; a repair-trigger exit alone only records observation.
    assert 'exactTriggerFromEvent(data, REPAIR_TRIGGER_NAME, "Overlaps")' in repair_callback
    assert "repairOccupants[data.subjectID]" in repair_callback
    assert re.search(r"data\.event\s*==\s*[\"']exit[\"']", repair_callback)
    assert "exitObserved = true" in repair_callback
    assert re.search(
        r"data\.event\s*~=\s*[\"']enter[\"']\s+or\s+repairOccupants\[data\.subjectID\]",
        repair_callback,
    )
    assert re.search(r"repairOccupants\[vehicleId\]\s*=\s*nil", remove_subject)

    assert re.search(r"(?:obj|vehicle):requestReset\(\s*RESET_PHYSICS\s*\)", source)
    assert "resetBrokenFlexMesh" in source
    assert "beamstate.damage" in source
    assert "beamstate.getPartDamageData" in source
    assert "obj:beamIsBroken" in source

    # The target is the vehicle's exact live pose snapshot: repair must put
    # the vehicle back precisely where and how it stood, independent of the
    # wash's placed orientation, so the follow camera never jumps.
    assert "vehicle:getPosition()" in target_pose
    assert "quat(vehicle:getRotation())" in target_pose
    assert "targetPosition = vec3(position.x, position.y, position.z)" in target_pose
    assert "targetRotation = quat(rotation.x, rotation.y, rotation.z, rotation.w)" in (target_pose)
    assert "corridor" not in target_pose
    assert "trigger" not in target_pose
    assert "getSpawnWorldOOBB" not in target_pose
    assert "quat(0, 0, 1, 0)" not in target_pose
    for metric in (
        "positionDrift",
        "directionDot",
        "uprightDot",
        "travelSignPreserved",
    ):
        assert metric in pose_metrics

    # onVehicleResetted is the acknowledgement of the intentional reset. It
    # must recognize reset_pending before the generic path removes/aborts the
    # subject, then advance to a settling/verification phase and return.
    assert reset_callback.index("reset_pending") < reset_callback.index("removeWashSubject")
    reset_pending_branch = reset_callback[: reset_callback.index("removeWashSubject")]
    assert "repairOccupants" in reset_pending_branch
    assert '"repair_reset_ack"' in reset_pending_branch
    assert "vehicle:setPositionRotation" in reset_pending_branch
    assert "repair.targetPosition" in reset_pending_branch
    assert "repair.targetRotation" in reset_pending_branch
    assert "pose_restore_requested = true" in reset_pending_branch
    assert 'pose_policy = "restore_exact_pre_repair_pose"' in (reset_pending_branch)
    assert '"repair_pose_restore_ack"' in reset_pending_branch
    assert "return" in reset_pending_branch

    assert "repairOccupants" in integrity_ack
    assert "verify_pending" in integrity_ack
    assert "failed" in integrity_ack
    assert f"M.{integrity_ack_name}" in source
    assert "release_pending" in integrity_ack
    assert "repair_release_requested" in integrity_ack
    assert '"repair_pose_verification_failed"' in integrity_ack
    assert "REPAIR_MAX_POSITION_DRIFT_METERS" in integrity_ack
    assert "REPAIR_MIN_DIRECTION_DOT" in integrity_ack
    assert "REPAIR_MIN_UPRIGHT_DOT" in integrity_ack
    assert "repair.targetPosition" in integrity_ack
    assert "repair.targetRotation" in integrity_ack
    assert "repairTargetPose(vehicle)" in integrity_ack
    assert "repair_release_ack" in release_ack
    assert "repair_complete" in release_ack
    for telemetry_field in (
        "position_drift_m",
        "direction_dot",
        "upright_dot",
        "travel_sign_preserved",
        "pose_correction_attempts",
    ):
        assert telemetry_field in release_ack
    assert "processPendingLaunch" in release_ack
    assert f"M.{release_ack_name}" in source

    # Only trigger churn caused by the intentional reset may defer a wash
    # exit. A reset-generated re-entry cancels that deferred exit; otherwise
    # guard expiry removes the subject instead of leaking occupancy/effects.
    assert "resetEdgeGuard" in wash_callback
    assert "washExitDeferred = true" in wash_callback
    assert 'repair.phase ~= "complete"' not in wash_callback
    assert "washExitDeferred = false" in wash_callback
    assert "deferredWashExit" in update
    assert 'removeWashSubject(vehicleId, "deferred_exit_after_repair")' in update
    assert "processPendingLaunch(vehicleId)" in update
    assert re.search(
        r"if\s+not\s+queued\s+then\s+failRepair\(vehicleId,\s*"
        r'["\']repair_verification_command_failed["\']',
        update,
    )

    # If full launch containment races the reset verification, keep the entry
    # pending until this occupant reaches the complete phase.
    assert re.search(
        r"repair[A-Za-z_]*\s*\(\s*data\.subjectID\s*\)|"
        r"repairOccupants\[data\.subjectID\]",
        launch_callback,
    )
    assert "complete" in source
    assert "resetEdgeGuard" in pending_launch
    assert "washExitDeferred" in pending_launch
    assert re.search(
        r"if\s+not\s+repair\s+or\s+repair\.phase\s*~=\s*[\"']complete[\"']",
        pending_launch,
    )
    assert "resetEdgeGuard" in launch_callback
    assert "washExitDeferred" in launch_callback
    assert re.search(
        r"if\s+not\s+repair\s+or\s+repair\.phase\s*~=\s*[\"']complete[\"']",
        launch_callback,
    )
    assert '"repair_not_started"' in launch_callback
    assert '"launch_deferred"' in launch_callback


def test_phase3_manifest_describes_wash_cycle_and_containment_gate() -> None:
    manifest = json.loads(PHASE3_MANIFEST.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["phase"] == 3
    assert manifest["extension"] == {
        "registry_name": EXTENSION_REGISTRY_NAME,
        "file": f"levels/gridmap_v2/scenarios/{MOD_ID}/{MOD_ID}.lua",
        "scenario_entry": {"name": MOD_ID},
        "lifecycle": "scenario_owned",
    }
    assert manifest["identity"] == {
        "trigger_name": LAUNCH_TRIGGER_NAME,
        "trigger_class": "BeamNGTrigger",
        "trigger_mode": "Contains",
        "trigger_test_type": "Bounding box",
        "wash_trigger_name": WASH_TRIGGER_NAME,
        "wash_trigger_class": "BeamNGTrigger",
        "wash_trigger_mode": "Overlaps",
        "repair_trigger_name": REPAIR_TRIGGER_NAME,
        "repair_trigger_class": "BeamNGTrigger",
        "repair_trigger_mode": "Overlaps",
        "default_vehicle_name": TRUCK_NAME,
        "default_vehicle_model": "pickup",
        "launcher_vehicle_scope": "any_live_vehicle",
    }
    assert manifest["wash_cycle"] == {
        "scope": "full_bay",
        "enter": {
            "roller_visual": SCENARIO_VISUAL_NAME,
            "roller_sequence": "ambient",
            "roller_play_ambient": True,
            "emitter_counts": {
                "BNGP_sprinkler": 6,
                "BNGP_waterfallsteam": 6,
                "BNGP_34": 2,
                "BNGP_2": 2,
            },
            "effect_count": 16,
            "effects_active": True,
        },
        "exit": {
            "stop_condition": "last_tracked_vehicle_removed",
            "roller_play_ambient": False,
            "effects_active": False,
        },
        "mission_initial_state": "off",
        "subject_tracking": "vehicle_id_set",
    }
    assert manifest["repair_cycle"] == {
        "trigger_name": REPAIR_TRIGGER_NAME,
        "trigger_mode": "Overlaps",
        "trigger_test_type": "Bounding box",
        "vehicle_scope": "any_live_vehicle",
        "reset_strategy": "RESET_PHYSICS",
        "pre_reset_hold": "acknowledged_controller_freeze_preserving_previous_state",
        "pose_policy": "restore_exact_pre_repair_pose",
        "center_reference": "vehicle_spawn_world_oobb",
        "position_policy": "remove_lateral_error_preserve_longitudinal_progress_and_height",
        "orientation_policy": "restore_exact_pre_repair_pose_heading_preserved",
        "pose_verification": {
            "maximum_position_drift_m": 0.15,
            "minimum_heading_dot": 0.995,
            "minimum_upright_dot": 0.98,
            "require_travel_sign_preserved": True,
        },
        "reset_callback_sequence": [
            "physics_reset_acknowledgement",
            "pose_restore_acknowledgement",
        ],
        "settle_sim_frames": 2,
        "completion": "post_reset_integrity_and_freeze_release_acknowledgements",
        "duplicate_enter_policy": "ignore_until_wash_exit",
        "deferred_exit_policy": "reconcile_after_reset_edge_guard",
        "launch_policy": "defer_until_complete_and_reset_edge_guard_clear_when_occupied",
    }
    assert manifest["containment_gate"] == {
        "required_trigger": LAUNCH_TRIGGER_NAME,
        "required_mode": "Contains",
        "required_test_type": "Bounding box",
        "required_vehicle_state": f"previously_entered_{WASH_TRIGGER_NAME}",
        "required_wash_system_state": "active",
        "required_repair_state": "complete",
        "launch_trigger_local_center": [0.0, 0.0, 2.1],
        "launch_trigger_dimensions": [5.8, 17.5, 4.6],
        "validated_large_vehicle": {
            "model": "citybus",
            "configuration": "city",
            "metadata_dimensions_m": [3.11, 12.63, 2.994],
        },
        "out_of_order_policy": "defer_until_wash_active_and_repair_complete",
        "prelaunch_exit_policy": (
            "suppress_only_while_same_subject_remains_an_active_wash_occupant"
        ),
        "action": "begin_countdown",
    }
    assert manifest["telemetry"]["wash_events"] == [
        "wash_trigger_enter",
        "wash_systems_start",
        "wash_trigger_exit",
        "wash_systems_stop",
    ]
    assert manifest["telemetry"]["repair_events"] == [
        "repair_trigger_enter",
        "repair_snapshot",
        "repair_requested",
        "repair_reset_ack",
        "repair_pose_restore_ack",
        "repair_release_requested",
        "repair_release_ack",
        "repair_complete",
    ]
    assert manifest["telemetry"]["launch_gate_event"] == "containment_verified"
    assert manifest["telemetry"]["launch_deferred_event"] == "launch_deferred"
    assert (
        manifest["telemetry"]["containment_exit_suppressed_event"] == "containment_exit_suppressed"
    )


def test_launch_requires_prior_wash_entry_and_engine_contains_event() -> None:
    source = extension_source()
    launch_callback = _function_section(source, "handleLaunchTrigger")

    wash_guard = re.search(
        r"if\s+not\s+washSubjects\[data\.subjectID\]\s+or\s+not\s+washSystemsActive\s+then",
        launch_callback,
    )
    assert wash_guard is not None
    assert '"launch_deferred"' in launch_callback
    assert 'reason = "wash_not_active"' in launch_callback
    assert "pendingLaunchEntries[data.subjectID]" in launch_callback
    pending = _function_section(source, "processPendingLaunch")
    assert "washSubjects[subjectId]" in pending
    assert "washSystemsActive" in pending
    assert "repairOccupants" in source
    assert "complete" in pending or re.search(r"repair[A-Za-z_]*\(\s*subjectId\s*\)", pending)
    assert "handleLaunchTrigger(pending)" in pending
    wash_callback = _function_section(source, "handleWashTrigger")
    assert "processPendingLaunch(data.subjectID)" in wash_callback
    assert '"containment_verified"' in launch_callback
    assert 'trigger:getField("triggerMode", 0)' in launch_callback
    assert 'trigger:getField("triggerTestType", 0)' in launch_callback
    assert (
        wash_guard.start()
        < launch_callback.index("armed = false")
        < launch_callback.index('"containment_verified"')
        < launch_callback.index('"trigger_enter"')
        < launch_callback.index("holdVehicleCommand")
    )


def test_countdown_is_a_jobsystem_three_two_one_go_state_machine() -> None:
    source = extension_source()
    countdown = _function_tail(source, "countdownJob")

    interval_match = re.search(
        r"local\s+(?P<name>COUNTDOWN_(?:INTERVAL|STEP)_SECONDS)\s*=\s*1(?:\.0+)?\b",
        source,
    )
    assert interval_match is not None
    interval_name = interval_match.group("name")

    messages_match = re.search(
        r"local\s+COUNTDOWN_MESSAGES\s*=\s*{(?P<body>.*?)}",
        source,
        flags=re.DOTALL,
    )
    assert messages_match is not None
    messages = re.findall(r"[\"']([^\"']+)[\"']", messages_match.group("body"))
    assert messages == ["3...", "2...", "1..."]
    assert '"GO!"' in source or "'GO!'" in source

    assert "extensions.core_jobsystem.create(countdownJob" in source
    assert re.search(rf"job\.sleep\(\s*{re.escape(interval_name)}\s*\)", countdown)
    assert "hptimer()" in countdown
    assert "COUNTDOWN_MESSAGES" in countdown
    assert re.search(r"countdownIndex\s*=\s*nextIndex", countdown)
    assert "requestReleaseForLaunch(vehicle)" in countdown
    assert "activeRun.number ~= runNumber" in countdown


def test_countdown_uses_stable_ui_messages_and_observable_event_names() -> None:
    source = extension_source()

    assert _lua_string(source, "UI_CATEGORY") == f"{MOD_ID}_countdown"
    assert "guihooks.message" in source
    assert re.search(
        r"guihooks\.message\s*\(\s*{\s*txt\s*=\s*[^}]+}\s*,\s*[^,]+,\s*UI_CATEGORY\s*\)",
        source,
        flags=re.DOTALL,
    )

    for event in (
        "wash_trigger_enter",
        "wash_systems_start",
        "repair_trigger_enter",
        "repair_snapshot",
        "repair_requested",
        "repair_reset_ack",
        "repair_complete",
        "containment_verified",
        "trigger_enter",
        "hold_requested",
        "hold_ack",
        "hold_start",
        "countdown_timer_start",
        "countdown_3",
        "countdown_2",
        "countdown_1",
        "go",
        "release_requested",
        "release_ack",
        "release",
        "launch",
        "launch_complete",
        "wash_trigger_exit",
        "wash_systems_stop",
        "launch_deferred",
        "abort",
        "error",
    ):
        assert f'"{event}"' in source or f"'{event}'" in source


def test_hold_uses_acknowledged_freeze_and_one_uniform_cluster_stop() -> None:
    source = extension_source()
    update = _function_tail(source, "onPreRender")
    assert "controller.setFreeze(1)" in source
    assert "controller.setFreeze(previousFrozen and 1 or 0)" in source
    assert "ericrolphCannonCarWashScenarioHoldState" in source
    # Lua's ``condition and false_value or fallback`` idiom loses a stored
    # false value. The release path must preserve the pre-hold unfrozen state
    # explicitly or it restores the truck to frozen and the launch deadlocks.
    assert "existing and existing.frozen or currentFrozen" not in source
    assert "matched and existing.frozen" not in source
    assert "if existing then previousFrozen = existing.frozen == true end" in source
    assert "if matched then previousFrozen = existing.frozen == true end" in source
    hold_ack = _function_section(source, "onEricrolphCannonCarWashScenarioHoldAcknowledged")
    assert hold_ack.index("activeRun.holding = accepted") < hold_ack.index(
        "if not accepted or not actualFrozen"
    )
    assert "input.event" not in source
    assert "input.state" not in source
    assert "queueLuaCommand" in source
    assert "onEricrolphCannonCarWashScenarioHoldAcknowledged" in source
    assert "onEricrolphCannonCarWashScenarioReleaseAcknowledged" in source
    assert "hold_pending" in source
    assert "release_pending" in source
    assert "release_grace" in source
    assert "RELEASE_GRACE_SIM_FRAMES" in source
    assert "applyClusterVelocityScaleAdd" not in update
    assert re.search(
        r"vehicle:applyClusterVelocityScaleAdd\(\s*"
        r"vehicle:getRefNodeId\(\)\s*,\s*0\s*,\s*0\s*,\s*0\s*,\s*0\s*\)",
        hold_ack,
    )
    assert source.count("applyClusterVelocityScaleAdd") == 2


def test_acknowledged_release_and_grace_precede_exact_100_mps_launch() -> None:
    source = extension_source()

    assert _lua_number(source, "LAUNCH_SPEED_MPS") == 100.0
    assert _lua_number(source, "RELEASE_GRACE_SIM_FRAMES") == 2.0
    release_ack = _function_section(source, "onEricrolphCannonCarWashScenarioReleaseAcknowledged")
    update = _function_section(source, "onPreRender")
    launch = _function_section(source, "launchVehicle")
    assert 'activeRun.phase = "release_grace"' in release_ack
    assert "activeRun.releaseGraceFrames = RELEASE_GRACE_SIM_FRAMES" in release_ack
    assert 'activeRun.phase == "release_grace"' in update
    assert "launchVehicle(vehicle)" in update
    assert "releaseVehicle(" not in launch

    direction = re.search(
        r"local\s+(?P<direction>[A-Za-z_]\w*)\s*=\s*"
        r"(?P<vehicle>[A-Za-z_]\w*):getDirectionVector\(\)",
        source,
    )
    assert direction is not None
    direction_name = direction.group("direction")
    assert re.search(rf"{re.escape(direction_name)}:normalize\(\)", source)

    velocity = re.search(
        rf"local\s+(?P<velocity>[A-Za-z_]\w*)\s*=\s*"
        rf"{re.escape(direction_name)}\s*\*\s*LAUNCH_SPEED_MPS",
        source,
    )
    assert velocity is not None
    velocity_name = velocity.group("velocity")
    launch_call = re.search(
        rf"(?P<vehicle>[A-Za-z_]\w*):applyClusterVelocityScaleAdd\(\s*"
        rf"(?P=vehicle):getRefNodeId\(\)\s*,\s*0\s*,\s*"
        rf"{re.escape(velocity_name)}\.x\s*,\s*{re.escape(velocity_name)}\.y\s*,\s*"
        rf"{re.escape(velocity_name)}\.z\s*\)",
        source,
        flags=re.DOTALL,
    )
    assert launch_call is not None

    assert launch_call.start() >= source.index("local function launchVehicle")
    assert source.count("applyClusterVelocityScaleAdd") == 2


def test_active_run_is_single_shot_but_exit_reset_and_lifecycle_rearm_it() -> None:
    source = extension_source()
    callback = _function_section(source, "handleLaunchTrigger")

    assert re.search(r"\barmed\s*=\s*true", source)
    assert re.search(r"\barmed\s*=\s*false", callback)
    assert re.search(r"data\.event\s*==\s*[\"']exit[\"']", callback)
    assert re.search(r"\barmed\s*=\s*true", callback)
    assert re.search(r"if\s+not\s+armed\s+or\s+activeRun", callback)

    for callback_name in (
        "onClientStartMission",
        "onClientEndMission",
        "onExtensionUnloaded",
    ):
        section = _function_section(source, callback_name)
        assert "abortActiveRun" in section
        assert "resetState" in section
        assert "resetWashState" in section

    assert "M.onVehicleResetted" in source
    assert "M.onVehicleDestroyed" in source
    assert source.count("abortActiveRun") >= 4
    assert source.count("resetState") >= 4

    remove_subject = _function_section(source, "removeWashSubject")
    assert re.search(r"washSubjects\[vehicleId\]\s*=\s*nil", remove_subject)
    assert "washSubjectCount()" in remove_subject
    assert "setWashSystemsEnabled(false" in remove_subject
    for callback_name in ("onVehicleResetted", "onVehicleDestroyed"):
        section = _function_section(source, callback_name)
        assert "removeWashSubject(vehicleId" in section


def test_logs_are_tagged_versioned_json_records_not_human_only_messages() -> None:
    source = extension_source()

    assert _lua_string(source, "LOG_TAG") == "ERICROLPH_CANNON_CAR_WASH"
    assert re.search(r"schema_version\s*=\s*1", source)
    assert re.search(r"event\s*=\s*event", source)
    assert "vehicle_id" in source
    assert "elapsed_time_seconds" in source
    assert "jsonEncode" in source
    assert re.search(
        r"log\s*\(\s*level\s*,\s*LOG_TAG\s*,\s*(?:jsonEncode\s*\(|encoded\b)",
        source,
    )
    assert re.search(r"emitEvent\s*\(\s*[\"']E[\"']\s*,\s*[\"']error[\"']", source)
