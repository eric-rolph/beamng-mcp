from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOD_ROOT = PROJECT_ROOT / "examples" / "cannon_car_wash" / "mod"
MOD_ID = "ericrolph_cannon_car_wash"
VEHICLE_BOOTSTRAP = MOD_ROOT / "vehicles" / MOD_ID / "lua" / f"{MOD_ID}_vehicle.lua"
GE_RUNTIME = MOD_ROOT / "lua" / "ge" / "extensions" / MOD_ID / "runtime.lua"
LIGHTING_RUNTIME = MOD_ROOT / "lua" / "common" / MOD_ID / "lighting.lua"
GE_EXTENSION_PATH = f"{MOD_ID}/runtime"
GE_EXTENSION_NAME = "ericrolph__cannon__car__wash_runtime"
REPAIR_TRIGGER_LOCAL_POSITION = (0.0, 0.0, 2.1)
REPAIR_TRIGGER_SCALE = (5.4, 2.2, 4.2)
LAUNCH_TRIGGER_LOCAL_POSITION = (0.0, 0.0, 2.1)
LAUNCH_TRIGGER_SCALE = (5.8, 17.5, 4.6)


def _function_section(source: str, name: str) -> str:
    match = re.search(
        rf"(?:(?:local\s+function|function\s+M\.)\s*{re.escape(name)}\s*\(|"
        rf"\b{re.escape(name)}\s*=\s*function\s*\()",
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


def _lua_number(source: str, name: str) -> float:
    match = re.search(
        rf"\blocal\s+{re.escape(name)}\s*=\s*(?P<value>\d+(?:\.\d+)?)\b",
        source,
    )
    assert match is not None, f"missing local Lua numeric constant {name}"
    return float(match.group("value"))


def _lua_string(source: str, name: str) -> str:
    match = re.search(
        rf"\blocal\s+{re.escape(name)}\s*=\s*([\"'])(?P<value>.*?)\1",
        source,
    )
    assert match is not None, f"missing local Lua string constant {name}"
    return match.group("value")


def _lua_vec3(source: str, name: str) -> tuple[float, float, float]:
    match = re.search(
        rf"\blocal\s+{re.escape(name)}\s*=\s*vec3\s*\(\s*"
        r"(?P<x>-?\d+(?:\.\d+)?)\s*,\s*"
        r"(?P<y>-?\d+(?:\.\d+)?)\s*,\s*"
        r"(?P<z>-?\d+(?:\.\d+)?)\s*\)",
        source,
    )
    assert match is not None, f"missing local Lua vec3 constant {name}"
    return (
        float(match.group("x")),
        float(match.group("y")),
        float(match.group("z")),
    )


def _assert_exported(source: str, name: str) -> None:
    assert re.search(
        rf"(?:\bM\.{re.escape(name)}\s*=|"
        rf"\bfunction\s+M\.{re.escape(name)}\s*\()",
        source,
    ), f"Lua module does not export {name}"


def _assert_creates_class(source: str, class_name: str) -> None:
    direct = re.search(
        rf"\bcreateObject\s*\(\s*([\"']){re.escape(class_name)}\1\s*\)",
        source,
    )
    constants = re.findall(
        rf"\blocal\s+([A-Z][A-Z0-9_]*)\s*=\s*([\"']){re.escape(class_name)}\2",
        source,
    )
    indirect = any(
        re.search(rf"\bcreateObject\s*\(\s*{re.escape(name)}\s*\)", source)
        for name, _quote in constants
    )
    assert direct or indirect, f"runtime does not create a {class_name}"


def test_vehicle_selector_prop_bootstraps_a_self_contained_runtime() -> None:
    assert VEHICLE_BOOTSTRAP.is_file(), (
        "the selector prop needs a vehicle-local Lua bootstrap: "
        f"{VEHICLE_BOOTSTRAP.relative_to(PROJECT_ROOT)}"
    )
    assert GE_RUNTIME.is_file(), (
        f"the selector prop needs a namespaced GE runtime: {GE_RUNTIME.relative_to(PROJECT_ROOT)}"
    )
    assert LIGHTING_RUNTIME.is_file()
    assert not any(MOD_ROOT.rglob("modScript.lua")), (
        "the selector runtime must be loaded by its vehicle, not globally at mod activation"
    )

    bootstrap = VEHICLE_BOOTSTRAP.read_text(encoding="utf-8")
    runtime = GE_RUNTIME.read_text(encoding="utf-8")
    folded_bootstrap = bootstrap.casefold()
    folded_runtime = runtime.casefold()

    for unsafe_loader in ("loadstring", "dofile"):
        assert unsafe_loader not in folded_bootstrap
        assert unsafe_loader not in folded_runtime

    # BeamNG automatically loads Lua modules in a vehicle's own lua directory.
    # The bootstrap must use fixed, auditable GE code and re-register after reset.
    assert "obj:queueGameEngineLua" in bootstrap
    assert _lua_string(bootstrap, "GE_EXTENSION_PATH") == GE_EXTENSION_PATH
    assert _lua_string(bootstrap, "GE_EXTENSION_NAME") == GE_EXTENSION_NAME
    assert re.search(r"\bextensions\.load\s*\(", bootstrap)
    assert len(re.findall(r"\bextensions\.load\s*\(", bootstrap)) == 1
    assert "registerProp" in bootstrap
    assert "unregisterProp" in bootstrap
    for callback in ("onVehicleLoaded", "onReset"):
        _function_section(bootstrap, callback)
        _assert_exported(bootstrap, callback)

    # Every spawned wash is an independent runtime instance. Nothing created by
    # it may be persisted into the user's level when the map is saved.
    for function_name in ("registerProp", "unregisterProp", "getSystemState"):
        _function_section(runtime, function_name)
        _assert_exported(runtime, function_name)
    assert re.search(r"\b(?:instances|installations)\s*\[\s*propId\s*\]", runtime)
    for class_name in ("TSStatic", "BeamNGTrigger", "ParticleEmitterNode"):
        _assert_creates_class(runtime, class_name)
    assert re.search(
        r"(?:\.canSave\s*=\s*false|"
        r":setField\s*\(\s*([\"'])canSave\1\s*,\s*0\s*,\s*([\"'])0\2\s*\))",
        runtime,
    )
    assert "propId" in _function_section(runtime, "registerProp")

    # The GE companion objects must use the exact vehicle pose. The generated
    # JBeam now places its reference node on Blender's measured floor underside,
    # so the asset origin and the map-surface spawn datum are identical.
    assert re.search(
        r"\blocal\s+PROP_REF_OFFSET\s*=\s*vec3\s*\(\s*0(?:\.0+)?\s*,"
        r"\s*0(?:\.0+)?\s*,\s*0(?:\.0+)?\s*\)",
        runtime,
    )
    assert re.search(r"\w+:getPosition\s*\(\s*\)", runtime)
    assert re.search(r"\w+:getRotation\s*\(\s*\)", runtime)
    compact_runtime = re.sub(r"\s+", "", runtime)
    assert re.search(
        r"origin=\w+-\w+\*PROP_REF_OFFSET",
        compact_runtime,
    ), "mesh origin must subtract the rotated JBeam reference-node offset"
    assert re.search(
        r"frame\.origin\+frame\.modelRotation\*"
        r"(?:[A-Z][A-Z0-9_]*_POSITION|spec\.position)",
        compact_runtime,
    ), "local trigger/effect offsets must be rotated into world space"
    assert "setPosRot" in runtime or ("setPosition" in runtime and "setRotation" in runtime)

    # BeamNGTrigger calls the engine's global onBeamNGTrigger, which broadcasts
    # to loaded GE extensions. All three zones therefore keep that exact callback.
    assert runtime.count("BeamNGTrigger") >= 1
    assert re.search(r"triggerMode[^\n]*(?:mode|([\"'])Overlaps\1)", runtime)
    assert re.search(r"createTrigger\([^\n]*([\"'])Overlaps\1", runtime)
    assert re.search(r"createTrigger\([^\n]*([\"'])Contains\1", runtime)
    assert _lua_vec3(runtime, "REPAIR_TRIGGER_LOCAL_POSITION") == REPAIR_TRIGGER_LOCAL_POSITION
    assert _lua_vec3(runtime, "REPAIR_TRIGGER_SCALE") == REPAIR_TRIGGER_SCALE
    assert _lua_vec3(runtime, "LAUNCH_TRIGGER_LOCAL_POSITION") == LAUNCH_TRIGGER_LOCAL_POSITION
    assert _lua_vec3(runtime, "LAUNCH_TRIGGER_SCALE") == LAUNCH_TRIGGER_SCALE
    assert runtime.count("Bounding box") >= 1
    assert re.search(r"luaFunction[^\n]*([\"'])onBeamNGTrigger\1", runtime)
    _function_section(runtime, "onBeamNGTrigger")
    _assert_exported(runtime, "onBeamNGTrigger")


def test_selector_runtime_creates_tracks_and_cleans_authored_scene_lights() -> None:
    runtime = GE_RUNTIME.read_text(encoding="utf-8")
    lighting = LIGHTING_RUNTIME.read_text(encoding="utf-8")
    assert 'require("common/ericrolph_cannon_car_wash/lighting")' in runtime
    assert lighting.count('class = "PointLight"') == 9
    assert lighting.count('class = "SpotLight"') == 4
    assert lighting.count(f'name = "{MOD_ID}_light_anchor_') == 13
    create_light = _function_section(runtime, "createLight")
    synchronize = _function_section(runtime, "synchronizeTransforms")
    cleanup = _function_section(runtime, "cleanupInstallation")
    state = _function_section(runtime, "installationState")
    assert "createObject(spec.class)" in create_light
    for field in (
        "isEnabled",
        "color",
        "brightness",
        "castShadows",
        "attenuationRatio",
        "radius",
        "range",
        "innerAngle",
        "outerAngle",
    ):
        assert f'"{field}"' in create_light
    assert "state.lights" in synchronize
    assert "frame.modelRotation * spec.position" in synchronize
    assert "quatFromDir(worldDirection, worldUp)" in synchronize
    assert "state.lights or {}" in cleanup
    assert "light_present_count" in state
    assert "light_expected_count" in state


def test_selector_runtime_loads_common_visual_materials_before_creating_the_tsstatic() -> None:
    runtime = GE_RUNTIME.read_text(encoding="utf-8")
    ensure = _function_section(runtime, "ensureVisualMaterials")
    register = _function_section(runtime, "registerProp")
    assert '"vehicles/ericrolph_cannon_car_wash/main.materials.json"' in runtime
    assert (
        '"/vehicles/ericrolph_cannon_car_wash/'
        'ericrolph_cannon_car_wash_runtime_visual.dae"' in runtime
    )
    assert "REQUIRED_VISUAL_MATERIALS" in ensure
    assert "loadJsonMaterialsFile" in ensure
    assert "string.lower(tostring(material:getClassName()))" in ensure
    assert 'className ~= "material"' in ensure
    assert '"visual_materials_unavailable"' in register
    assert register.index("ensureVisualMaterials()") < register.index("createVisual(")

    # Six wash jets and ten layered dryer nodes are instantiated per prop and
    # start inactive; rollers share the same full-bay occupancy state.
    mister_offsets = re.search(
        r"\blocal\s+(?:EFFECT|MISTER)_OFFSETS\s*=\s*\{(?P<body>.*?)\n\}",
        runtime,
        re.DOTALL,
    )
    assert mister_offsets is not None, "missing effect offset table"
    offsets_body = mister_offsets.group("body")
    assert len(re.findall(r"\bposition\s*=\s*vec3\s*\(", offsets_body)) == 16
    assert len(re.findall(r"\binward\s*=\s*vec3\s*\(", offsets_body)) == 16
    assert Counter(re.findall(r"\bemitter\s*=\s*[\"']([^\"']+)[\"']", offsets_body)) == {
        "BNGP_sprinkler": 6,
        "BNGP_waterfallsteam": 6,
        "BNGP_34": 2,
        "BNGP_2": 2,
    }
    assert "frame.modelRotation * spec.inward" in runtime
    assert "vec3(0, 0, 1):getRotationTo(worldDirection)" in runtime
    assert re.search(r"\w+:setActive\s*\(", runtime)
    assert "playAmbient" in runtime

    # The wash vehicle itself occupies its own trigger volume and must never be
    # treated as a customer. Any other live subject ID is valid; model/name
    # allowlists would silently break Vehicle Selector replacements.
    trigger_handler = _function_section(runtime, "onBeamNGTrigger")
    assert "data.subjectID" in runtime
    assert re.search(
        r"(?:instances|installations)\s*\[\s*data\.subjectID\s*\]",
        trigger_handler,
    ), "registered wash prop IDs must be excluded from their own triggers"
    assert re.search(r"eligibleSubject\s*\(\s*data\.subjectID\s*\)", runtime)
    assert re.search(
        r"(?:be:getObjectByID|scenetree\.findObjectById)\s*\(\s*vehicleId\s*\)",
        runtime,
    )
    for forbidden_identity in ("TRUCK_NAME", "TRUCK_MODEL", '"pickup"', "'pickup'"):
        assert forbidden_identity not in runtime

    assert _lua_number(runtime, "LAUNCH_SPEED_MPS") == 100.0
    assert _lua_number(runtime, "COUNTDOWN_INTERVAL_SECONDS") == 1.0
    for message in ("3...", "2...", "1...", "GO!"):
        assert message in runtime
    assert "extensions.core_jobsystem.create" in runtime
    assert "guihooks.message" in runtime
    assert "controller.setFreeze(1)" in runtime
    assert "controller.setFreeze(previousFrozen and 1 or 0)" in runtime
    assert "ericrolphCannonCarWashHoldState" in runtime
    assert "existing and existing.frozen or currentFrozen" not in runtime
    assert "matched and existing.frozen" not in runtime
    assert "if existing then previousFrozen = existing.frozen == true end" in runtime
    assert "if matched then previousFrozen = existing.frozen == true end" in runtime
    hold_ack = _function_section(runtime, "onEricrolphCannonCarWashHoldAcknowledged")
    assert hold_ack.index("run.holding = accepted") < hold_ack.index(
        "if not accepted or not actualFrozen"
    )
    assert "input.event" not in runtime
    assert "input.state" not in runtime
    assert re.search(
        r"vehicle:applyClusterVelocityScaleAdd\(\s*"
        r"vehicle:getRefNodeId\(\)\s*,\s*0\s*,\s*0\s*,\s*0\s*,\s*0\s*\)",
        hold_ack,
    )
    assert runtime.count("applyClusterVelocityScaleAdd") == 2
    assert "applyClusterVelocityScaleAdd" not in _function_section(runtime, "onPreRender")
    assert _lua_number(runtime, "RELEASE_GRACE_SIM_FRAMES") == 2.0
    assert "hold_pending" in runtime
    assert "release_pending" in runtime
    assert "release_grace" in runtime
    for callback in (
        "onEricrolphCannonCarWashHoldAcknowledged",
        "onEricrolphCannonCarWashReleaseAcknowledged",
    ):
        _function_section(runtime, callback)
        _assert_exported(runtime, callback)

    # All transient objects and held vehicles must be released on unregister,
    # vehicle destruction, mission end, and extension unload.
    unregister = _function_section(runtime, "unregisterProp")
    assert re.search(r"\w+:delete\s*\(\s*\)", runtime)
    assert "cleanupInstallation" in unregister
    assert re.search(
        r"(?:instances|installations)\s*\[\s*state\.propId\s*\]\s*=\s*nil",
        runtime,
    )
    for callback in (
        "onVehicleDestroyed",
        "onClientPreStartMission",
        "onClientEndMission",
        "onExtensionUnloaded",
    ):
        _function_section(runtime, callback)
        _assert_exported(runtime, callback)
    assert "cleanupAll" not in _function_section(runtime, "onClientStartMission")
    assert "extensions.unload" in runtime
    assert _lua_string(runtime, "RUNTIME_EXTENSION_NAME") == GE_EXTENSION_NAME

    # A prop reset must cancel any held run and replace all three trigger objects.
    # Rebuilding clears BeamNG's overlap cache so a vehicle still inside gets
    # fresh enter events instead of a stale launch after the prop moved.
    reset_handler = _function_section(runtime, "onVehicleResetted")
    prop_reset_branch = reset_handler.split("local state = installations[vehicleId]", maxsplit=1)[
        1
    ].split("local affected", maxsplit=1)[0]
    assert "finishActiveRunOnExit" in prop_reset_branch
    assert "state.washSubjects = {}" in prop_reset_branch
    assert "forceWashSystemsOff(state)" in prop_reset_branch
    assert "state.pendingLaunchEntries = {}" in prop_reset_branch
    assert "state.armed = true" in prop_reset_branch
    assert "rebuildTriggersAfterReset" in prop_reset_branch
    assert '"prop_reset"' in prop_reset_branch
    subject_reset_branch = reset_handler.split("local affected", maxsplit=1)[1]
    assert "removeWashSubject(installation, vehicleId" in subject_reset_branch
    assert "installation.washSubjects = {}" not in subject_reset_branch
    assert "installation.pendingLaunchEntries = {}" not in subject_reset_branch
    assert "forceWashSystemsOff(installation)" not in subject_reset_branch
    assert "remaining_subject_count = washSubjectCount(installation)" in subject_reset_branch
    assert "wash_systems_active = installation.washSystemsActive" in subject_reset_branch
    assert "rebuildTriggersAfterReset(installation)" in subject_reset_branch
    assert '"subject_reset"' in subject_reset_branch
    assert ":autoplace(" not in runtime
    assert 'ai.setMode("disabled")' not in runtime


def test_selector_runtime_owns_repair_trigger_through_full_lifecycle() -> None:
    runtime = GE_RUNTIME.read_text(encoding="utf-8")
    synchronize = _function_section(runtime, "synchronizeTransforms")
    rebuild = _function_section(runtime, "rebuildTriggersAfterReset")
    register = _function_section(runtime, "registerProp")
    cleanup = _function_section(runtime, "cleanupInstallation")
    state_query = _function_section(runtime, "installationState")
    dispatch = _function_section(runtime, "onBeamNGTrigger")
    validator = _function_section(runtime, "validateTriggerEvent")

    assert "state.repairTrigger" in synchronize
    assert "REPAIR_TRIGGER_LOCAL_POSITION" in synchronize
    assert "REPAIR_TRIGGER_SCALE" in synchronize

    for section in (rebuild, cleanup):
        assert "state.repairTrigger" in section
    assert "forgetTriggerOwner(state.repairTrigger)" in rebuild
    assert "deleteSceneObject(state.repairTrigger)" in rebuild
    assert 'createTrigger(state.repairTriggerName, "Overlaps")' in rebuild
    assert re.search(
        r"triggerOwners\[[^]]+\]\s*=\s*\{\s*propId\s*=\s*state\.propId\s*,\s*"
        r"kind\s*=\s*[\"']repair[\"']\s*}",
        rebuild,
    )

    assert "repairTriggerName" in register
    assert "repairOccupants" in register
    assert 'createTrigger(state.repairTriggerName, "Overlaps")' in register
    assert re.search(
        r"triggerOwners\[[^]]+\]\s*=\s*\{\s*propId\s*=\s*propId\s*,\s*"
        r"kind\s*=\s*[\"']repair[\"']\s*}",
        register,
    )
    assert "deleteSceneObject(state.repairTrigger)" in cleanup

    assert "repair_trigger" in state_query
    assert "state.repairTriggerName" in state_query
    assert "owner.kind" in dispatch and '"repair"' in dispatch
    assert "handleRepairTrigger(state, data)" in dispatch
    assert "state.repairTrigger" in validator
    assert "state.repairTriggerName" in validator
    assert '"Overlaps"' in validator


def test_selector_runtime_repairs_once_and_waits_for_integrity_ack() -> None:
    runtime = GE_RUNTIME.read_text(encoding="utf-8")
    repair_callback = _function_section(runtime, "handleRepairTrigger")
    remove_subject = _function_section(runtime, "removeWashSubject")
    cleanup = _function_section(runtime, "cleanupInstallation")
    fail_repair = _function_section(runtime, "failRepair")
    reset_callback = _function_section(runtime, "onVehicleResetted")
    update = _function_section(runtime, "onPreRender")
    wash_callback = _function_section(runtime, "handleWashTrigger")
    pending_launch = _function_section(runtime, "processPendingLaunch")
    integrity_ack_name = "onEricrolphCannonCarWashRepairIntegrityAcknowledged"
    integrity_ack = _function_section(runtime, integrity_ack_name)
    release_ack_name = "onEricrolphCannonCarWashRepairReleaseAcknowledged"
    release_ack = _function_section(runtime, release_ack_name)
    launch_callback = _function_section(runtime, "handleLaunchTrigger")
    target_pose = _function_section(runtime, "repairTargetPose")
    pose_metrics = _function_section(runtime, "repairedPoseMetrics")

    release_start = runtime.index("local function releaseVehicleCommand")
    release_string_end = runtime.index("]]", release_start)
    integrity_helper_start = runtime.index("local function repairIntegrityCommand")
    assert integrity_helper_start > release_string_end
    assert "repairIntegrityCommand" not in runtime[release_start:release_string_end]
    integrity_helper = _function_section(runtime, "repairIntegrityCommand")
    assert "'%s'" in integrity_helper
    assert "%q" not in integrity_helper
    repair_release_helper = _function_section(runtime, "repairReleaseCommand")
    best_effort_release = _function_section(runtime, "bestEffortReleaseRepair")

    assert "repairOccupants" in runtime
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
        assert f'"{phase}"' in runtime or f"'{phase}'" in runtime

    assert 'validateTriggerEvent(state, data, "repair")' in repair_callback
    assert "state.repairOccupants[data.subjectID]" in repair_callback
    assert re.search(r"data\.event\s*==\s*[\"']exit[\"']", repair_callback)
    assert "exitObserved = true" in repair_callback
    assert re.search(
        r"if\s+state\.repairOccupants\[data\.subjectID\]\s+then\s+return\s+end",
        repair_callback,
    )
    assert re.search(r"state\.repairOccupants\[vehicleId\]\s*=\s*nil", remove_subject)

    assert re.search(r"(?:obj|vehicle):requestReset\(\s*RESET_PHYSICS\s*\)", runtime)
    assert "resetBrokenFlexMesh" in runtime
    assert "beamstate.damage" in runtime
    assert "beamstate.getPartDamageData" in runtime
    assert "obj:beamIsBroken" in runtime

    # Runtime placement is based on the live prop-owned repair trigger and the
    # measured vehicle basis. It must center the aligned OOBB and must not
    # encode a model-specific 180-degree vehicle correction.
    assert "trigger:getPosition()" in target_pose
    assert "quat(trigger:getRotation())" in target_pose
    assert "triggerRotation * vec3(0, 1, 0)" in target_pose
    assert "triggerRotation * vec3(0, 0, 1)" in target_pose
    assert "vehicle:getSpawnWorldOOBB()" in target_pose
    assert "boundingBox:getCenter()" in target_pose
    assert "direction:dot(corridorForward) < 0" in target_pose
    assert "corridorForward = -corridorForward" in target_pose
    assert "vehicleUp - direction * vehicleUp:dot(direction)" in target_pose
    assert "direction:getRotationTo(corridorForward)" in target_pose
    assert "alignedUp:getRotationTo(corridorUp)" in target_pose
    assert "upAlignment * forwardAlignment" in target_pose
    assert "alignmentRotation * (boundingCenter - position)" in target_pose
    assert "targetPosition = position - corridorRight * centerlineOffset" in target_pose
    assert "quat(0, 0, 1, 0)" not in target_pose
    for metric in (
        "centerlineError",
        "corridorDirectionDot",
        "uprightDot",
        "travelDirectionDot",
        "travelSignPreserved",
    ):
        assert metric in pose_metrics

    # Repair owns a separate token/prop-scoped Vehicle Lua hold. The precheck
    # snapshots the prior controller state, freezes first, and reports both the
    # freeze acknowledgement and integrity in one callback. After the two reset
    # callbacks, the same helper reasserts the matching hold while it performs
    # post-settlement verification.
    assert "ericrolphCannonCarWashRepairHoldState" in integrity_helper
    assert "controller.setFreeze(1)" in integrity_helper
    assert "previousFrozen" in integrity_helper
    assert "holdAccepted" in integrity_helper
    assert "actualFrozen" in integrity_helper
    assert "existing.propId" in integrity_helper
    assert "existing.token" in integrity_helper
    assert "holdMayExist" in repair_callback

    assert "ericrolphCannonCarWashRepairHoldState" in repair_release_helper
    assert "existing.propId" in repair_release_helper
    assert "existing.token" in repair_release_helper
    assert "controller.setFreeze(previousFrozen and 1 or 0)" in repair_release_helper
    assert "actualFrozen == previousFrozen" in repair_release_helper
    assert "expectedPreviousFrozen" in repair_release_helper
    assert "existing == nil" in repair_release_helper
    assert "repairReleaseCommand" in best_effort_release
    assert "bestEffortReleaseRepair" in fail_repair
    assert "bestEffortReleaseRepair" in remove_subject
    assert "bestEffortReleaseRepair" in cleanup

    # The intentional reset is acknowledged before the existing generic reset
    # path clears occupants, aborts the run, and rebuilds from scratch.
    assert reset_callback.index("reset_pending") < reset_callback.index(
        "local state = installations[vehicleId]"
    )
    intentional_reset = reset_callback[
        : reset_callback.index("local state = installations[vehicleId]")
    ]
    assert "repairOccupants" in intentional_reset
    assert '"repair_reset_ack"' in intentional_reset
    assert "pose_restore_pending" in intentional_reset
    assert "vehicle:setPositionRotation(" in intentional_reset
    assert "repair.targetPosition" in intentional_reset
    assert "repair.targetRotation" in intentional_reset
    assert intentional_reset.index('repair.phase = "pose_restore_pending"') < (
        intentional_reset.index("vehicle:setPositionRotation(")
    )
    assert 'pose_policy = "center_oobb_on_trigger_axis_align_upright_preserve_travel_sign"' in (
        intentional_reset
    )
    assert '"repair_pose_restore_ack"' in intentional_reset
    assert intentional_reset.index('repair.phase == "pose_restore_pending"') < (
        intentional_reset.index('repair.phase = "settling"')
    )
    assert "repair.settleFrames = REPAIR_SETTLE_SIM_FRAMES" in intentional_reset
    assert "return" in intentional_reset

    assert "settling" in update
    assert "verify_pending" in update
    assert "repairOccupants" in integrity_ack
    assert "holdAccepted" in integrity_ack
    assert "actualFrozen" in integrity_ack
    assert "repair_hold_ack" in integrity_ack
    assert integrity_ack.index("not holdAccepted") < integrity_ack.index(
        "requestReset(RESET_PHYSICS)"
    )
    assert "verify_pending" in integrity_ack
    assert "failed" in integrity_ack
    assert '"repair_pose_verification_failed"' in integrity_ack
    assert "REPAIR_MAX_CENTERLINE_ERROR_METERS" in integrity_ack
    assert "REPAIR_MIN_CORRIDOR_DOT" in integrity_ack
    assert "REPAIR_MIN_UPRIGHT_DOT" in integrity_ack
    assert "release_pending" in integrity_ack
    assert "repairReleaseCommand" in integrity_ack
    assert '"repair_release_requested"' in integrity_ack
    assert '"repair_complete"' not in integrity_ack
    assert "processPendingLaunch" not in integrity_ack
    _assert_exported(runtime, integrity_ack_name)

    # Completion and launcher handoff happen only after Vehicle Lua confirms it
    # restored the controller's exact pre-repair freeze state.
    assert "release_pending" in release_ack
    assert "repair.previousFrozen" in release_ack
    assert "actualFrozen ~= previousFrozen" in release_ack
    assert "holdMayExist = false" in release_ack
    assert '"repair_release_ack"' in release_ack
    assert '"repair_complete"' in release_ack
    for telemetry_field in (
        "centerline_error_before_m",
        "centerline_error_m",
        "alignment_translation_m",
        "corridor_direction_dot",
        "upright_dot",
        "travel_direction_dot",
        "travel_sign_preserved",
        "travel_sign",
    ):
        assert telemetry_field in release_ack
    assert release_ack.index('"repair_release_ack"') < release_ack.index('"repair_complete"')
    assert release_ack.index('"repair_complete"') < release_ack.index("processPendingLaunch")
    _assert_exported(runtime, release_ack_name)

    assert "resetEdgeGuard" in wash_callback
    assert "washExitDeferred = true" in wash_callback
    assert 'repair.phase ~= "complete"' not in wash_callback
    assert wash_callback.index("washExitDeferred = false") < wash_callback.index(
        "state.washSubjects[data.subjectID] then return"
    )
    assert "deferredWashExit" in update
    assert 'removeWashSubject(state, vehicleId, "deferred_exit_after_repair")' in update
    assert "processPendingLaunch(state, vehicleId)" in update
    assert re.search(
        r"repair\.phase\s*==\s*[\"']release_pending[\"']",
        update,
    )
    assert re.search(
        r"if\s+not\s+queued\s+then\s+failRepair\(state,\s*vehicleId,\s*"
        r'["\']repair_verification_command_failed["\']',
        update,
    )

    assert re.search(
        r"repair[A-Za-z_]*\s*\(\s*state\s*,\s*data\.subjectID\s*\)|"
        r"state\.repairOccupants\[data\.subjectID\]",
        launch_callback,
    )
    assert "resetEdgeGuard" in pending_launch
    assert "washExitDeferred" in pending_launch
    assert re.search(
        r"if\s+not\s+repair\s+or\s+repair\.phase\s*~=\s*[\"']complete[\"']",
        pending_launch,
    )
    assert "resetEdgeGuard" in launch_callback
    assert "washExitDeferred" in launch_callback
    assert '"containment_exit_suppressed"' in launch_callback
    assert "state.washSubjects[data.subjectID]" in launch_callback
    assert "state.washSystemsActive" in launch_callback
    assert re.search(
        r"if\s+not\s+repair\s+or\s+repair\.phase\s*~=\s*[\"']complete[\"']",
        launch_callback,
    )
    assert '"repair_not_started"' in launch_callback
    assert '"launch_deferred"' in launch_callback
    for event in (
        "repair_trigger_enter",
        "repair_snapshot",
        "repair_requested",
        "repair_reset_ack",
        "repair_pose_restore_ack",
        "repair_release_requested",
        "repair_release_ack",
        "repair_complete",
    ):
        assert f'"{event}"' in runtime or f"'{event}'" in runtime

    # Repair must not stop drift by injecting impulses or broad recovery
    # placement. Up to two bounded, freshly measured pose corrections are
    # allowed when the renewed OOBB differs from the damaged pre-reset OOBB;
    # the following integrity pass must still satisfy every geometric gate.
    repair_sections = "\n".join(
        (
            integrity_helper,
            repair_release_helper,
            best_effort_release,
            fail_repair,
            integrity_ack,
            release_ack,
            repair_callback,
        )
    )
    assert "applyClusterVelocityScaleAdd" not in repair_sections
    assert "setPosition(" not in repair_sections
    assert repair_sections.count("setPositionRotation(") == 1
    assert "REPAIR_MAX_POSE_CORRECTION_ATTEMPTS" in integrity_ack
    assert '"repair_pose_correction_requested"' in integrity_ack
    assert "repairTargetPose(" in integrity_ack
    assert "state.repairTrigger" in integrity_ack
    assert "repair.targetPosition = correctionTarget.targetPosition" in integrity_ack
    assert "repair.targetRotation = correctionTarget.targetRotation" in integrity_ack
    assert '"repair_pose_correction_travel_sign_changed"' in integrity_ack
    assert "safeTeleport" not in repair_sections
    assert "safeTeleport" not in intentional_reset
