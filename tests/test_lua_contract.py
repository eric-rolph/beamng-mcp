from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOD_ROOT = PROJECT_ROOT / "src" / "beamng_mcp" / "assets" / "beamng_mod"
BRIDGE = MOD_ROOT / "lua" / "ge" / "extensions" / "beamng_mcp" / "bridge.lua"
BOOTSTRAP = MOD_ROOT / "scripts" / "beamng_mcp" / "modScript.lua"
CONFIG = MOD_ROOT / "settings" / "beamng_mcp.json"
MOD_INFO = MOD_ROOT / "mod_info" / "beamng_mcp" / "info.json"


def bridge_source() -> str:
    return BRIDGE.read_text(encoding="utf-8")


def test_mod_payload_contains_expected_entry_points() -> None:
    assert BRIDGE.is_file()
    assert BOOTSTRAP.is_file()
    assert not (BOOTSTRAP.parent / "bootstrap.lua").exists()
    assert CONFIG.is_file()
    assert MOD_INFO.is_file()

    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    assert 'EXTENSION_NAME = "beamng__mcp_bridge"' in bootstrap
    assert 'EXTENSION_PATH = "beamng_mcp/bridge"' in bootstrap
    assert "extensions.load(EXTENSION_PATH)" in bootstrap


def test_placeholder_config_is_safe_and_bounded() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))

    assert config["port"] == 8765
    assert config["token"] == "__BEAMNG_MCP_TOKEN__"
    assert 4096 <= config["max_payload_bytes"] <= 1_048_576
    assert config["telemetry_interval_seconds"] >= 0.2
    assert config["heartbeat_timeout_seconds"] > config["heartbeat_interval_seconds"]
    assert 0.25 <= config["safety_lease_seconds"] <= 5.0
    assert 0.25 <= config["safety_startup_grace_seconds"] <= 5.0
    assert config["allow_persistent_map_edits"] is False
    assert config["allow_existing_map_object_edits"] is False


def test_installer_marker_is_an_exact_strict_config_value() -> None:
    source = bridge_source()

    assert 'local CONFIG_MARKER = "beamng-mcp-bridge"' in source
    assert "marker = CONFIG_MARKER" in source
    assert "resolved.marker ~= CONFIG_MARKER" in source
    assert 'return nil, "configuration marker is invalid"' in source
    assert "if DEFAULT_CONFIG[key] == nil then" in source
    assert 'return nil, "unsupported configuration key: "' in source


def test_mod_metadata_is_valid_json() -> None:
    metadata = json.loads(MOD_INFO.read_text(encoding="utf-8"))

    assert metadata["title"] == "BeamNG MCP Bridge"
    assert metadata["version_string"]
    assert metadata["author"]


def test_bridge_uses_native_loopback_websocket_lifecycle() -> None:
    source = bridge_source()

    assert 'require("utils/wsUtils")' in source
    assert "wsUtils.createOrGetWS" in source
    assert 'LOOPBACK_ADDRESS = "127.0.0.1"' in source
    assert "BNGWebWSServer.destroy" in source
    assert "server:getPeerEvents()" in source
    assert "server:update()" in source
    assert "M.onExtensionLoaded" in source
    assert "M.onExtensionUnloaded" in source
    assert "M.onUpdate" in source
    assert not re.search(r"createOrGetWS\s*\(\s*[\"']any[\"']", source)


def test_protocol_has_strict_v1_envelope_and_authentication() -> None:
    source = bridge_source()

    assert "SCHEMA_VERSION = 1" in source
    for field in ("schema", "id", "type", "method", "params", "token"):
        assert re.search(rf"\b{field}\s*=", source)
    assert "REQUEST_KEYS" in source
    assert "constantTimeEquals(request.token, config.token)" in source
    assert "peer.authenticated = true" in source
    assert "peer.authenticated = false" in source
    assert "heartbeat_timeout_seconds" in source
    assert 'local BRIDGE_VERSION = "0.3.0"' in source
    assert "bridge_version = BRIDGE_VERSION" in source
    assert "game_version = tostring" in source


def test_every_authentication_failure_revokes_peer_trigger_ownership() -> None:
    source = bridge_source()
    revoke = source.split("local function revokePeerAuthentication", maxsplit=1)[1]
    revoke = revoke.split("local function validateRequest", maxsplit=1)[0]
    precheck = source.split('if not decodedOk or type(request) ~= "table" then', maxsplit=1)[
        1
    ].split("local requestError = validateRequest(request)", maxsplit=1)[0]
    request_error = source.split("local requestError = validateRequest(request)", maxsplit=1)[1]
    request_error = request_error.split("peer.authenticated = true", maxsplit=1)[0]

    assert "cleanupTriggersForPeer(peerId, reason)" in revoke
    assert "peer.authenticated = false" in revoke
    assert revoke.index("cleanupTriggersForPeer") < revoke.index("peer.authenticated = false")
    assert 'type(request.token) ~= "string"' in precheck
    assert "constantTimeEquals(request.token, config.token)" in precheck
    assert 'revokePeerAuthentication(peerId, peer, "authentication_failed")' in precheck
    assert "boundedAuthenticationRequest(request)" in precheck
    assert 'requestError.code == "authentication_failed"' in request_error
    assert 'revokePeerAuthentication(peerId, peer, "authentication_failed")' in request_error
    handle_message = source.split("local function handleMessage", maxsplit=1)[1]
    assert handle_message.index('type(request.token) ~= "string"') < handle_message.index(
        "local requestError = validateRequest(request)"
    )


def test_command_surface_is_an_explicit_allowlist() -> None:
    source = bridge_source()
    required_methods = {
        "ping",
        "capabilities",
        "telemetry.snapshot",
        "world.list_objects",
        "world.get_object",
        "world.create_object",
        "world.update_object",
        "world.delete_object",
        "world.save_level",
        "extension.reload",
        "emergency_stop",
    }

    for method in required_methods:
        assert f'HANDLERS["{method}"]' in source
    assert "HANDLERS[request.method]" in source
    assert "RELOADABLE_EXTENSIONS[extensionName]" in source
    assert '["beamng_mcp/bridge"] = "beamng__mcp_bridge"' in source


def test_bridge_rejects_code_execution_primitives() -> None:
    source = bridge_source().lower()

    for forbidden in ("loadstring", "dostring", "eval"):
        assert re.search(rf"\b{forbidden}\b", source) is None
    assert "queueLuaCommand(request" not in source
    assert "queueLuaCommand(params" not in source


def test_payload_and_frame_work_are_bounded() -> None:
    source = bridge_source()

    assert "HARD_MAX_PAYLOAD_BYTES = 1048576" in source
    assert "MAX_EVENTS_PER_UPDATE" in source
    assert "MAX_DATA_BYTES_PER_UPDATE" in source
    assert "MAX_OBJECT_RESULTS" in source
    assert "#message > config.max_payload_bytes" in source
    assert "#encoded > config.max_payload_bytes" in source


def test_saturated_native_event_batch_resets_instead_of_discarding_tail_events() -> None:
    source = bridge_source()
    update = source.split("local function onUpdate", maxsplit=1)[1]
    update = update.split("M.onExtensionLoaded = onExtensionLoaded", maxsplit=1)[0]
    peer_events = update.split('if eventsOk and type(events) == "table" then', maxsplit=1)[1].split(
        "if telemetryElapsed", maxsplit=1
    )[0]
    server_reset = source.split("local function resetWebSocketServer", maxsplit=1)[1].split(
        "local function resetOverloadedServer", maxsplit=1
    )[0]
    overload_reset = source.split("local function resetOverloadedServer", maxsplit=1)[1].split(
        "local function onClientStartMission", maxsplit=1
    )[0]
    mission_start = source.split("local function onClientStartMission", maxsplit=1)[1].split(
        "local function onClientEndMission", maxsplit=1
    )[0]
    mission_end = source.split("local function onClientEndMission", maxsplit=1)[1].split(
        "local function onUpdate", maxsplit=1
    )[0]

    # getPeerEvents drains its native queue. A batch beyond the count/byte work
    # budget must therefore close every peer and restart the listener; breaking
    # or deferring a tail could preserve stale peer state or cross a mission.
    assert "break" not in peer_events
    assert "if #events > MAX_EVENTS_PER_UPDATE then" in peer_events
    assert "dataBytes > byteLimit" in peer_events
    assert "resetOverloadedServer(#events, dataBytes)" in peer_events
    assert 'event.type == "C"' in peer_events
    assert 'event.type == "DC"' in peer_events
    assert 'event.type == "D"' in peer_events

    assert 'resetWebSocketServer("bridge_event_overload")' in overload_reset
    assert "expireSafetyLease(reason)" in server_reset
    assert "cleanupAllTriggers(reason)" in server_reset
    assert "pcall(BNGWebWSServer.destroy, server)" in server_reset
    assert "peers = {}" in server_reset
    assert "restartServerRequested = true" in server_reset
    assert "pendingDataEvents" not in source
    assert 'resetWebSocketServer("mission_started")' in mission_start
    assert 'resetWebSocketServer("mission_ended")' in mission_end


def test_world_mutations_validate_classes_fields_and_transforms() -> None:
    source = bridge_source()

    assert "CREATABLE_CLASSES" in source
    assert "FIELD_RULES" in source
    assert "validIdentifier" in source
    assert "validateFields" in source
    assert "parseVector3" in source
    assert "parseQuaternion" in source
    assert "rotation quaternion has an invalid magnitude" in source
    assert "shapeName must reference a .dae asset" in source


def test_persistent_save_requires_gate_and_confirmation() -> None:
    source = bridge_source()
    save_handler = source.split('HANDLERS["world.save_level"]', maxsplit=1)[1]
    save_handler = save_handler.split('HANDLERS["extension.reload"]', maxsplit=1)[0]

    assert "config.allow_persistent_map_edits" in save_handler
    assert "params.confirm ~= true" in save_handler
    assert 'type(params.level) ~= "string"' in save_handler
    assert "params.level ~= level" in save_handler
    assert "editor.saveLevel" in save_handler
    assert "pcall(editor.saveLevel)" in save_handler
    assert "save_requested = true" in save_handler
    assert "verified = false" in save_handler
    assert "saved = true" not in save_handler
    assert "saveResult == false" in save_handler


def test_existing_map_object_mutations_require_explicit_operator_gate() -> None:
    source = bridge_source()
    descriptor = source.split("local function objectDescriptor", maxsplit=1)[1]
    descriptor = descriptor.split("local function ensureWritableObject", maxsplit=1)[0]
    evidence = source.split("local function storeManagedObjectEvidence", maxsplit=1)[1]
    evidence = evidence.split("local function objectDescriptor", maxsplit=1)[0]
    create_handler = source.split('HANDLERS["world.create_object"]', maxsplit=1)[1]
    create_handler = create_handler.split("local function ensureManagedMutation", maxsplit=1)[0]
    update_handler = source.split('HANDLERS["world.update_object"]', maxsplit=1)[1]
    update_handler = update_handler.split('HANDLERS["world.delete_object"]', maxsplit=1)[0]
    delete_handler = source.split('HANDLERS["world.delete_object"]', maxsplit=1)[1]
    delete_handler = delete_handler.split('HANDLERS["world.save_level"]', maxsplit=1)[0]

    assert "allow_existing_map_object_edits = false" in source
    assert "ensureManagedMutation" in update_handler
    assert "ensureManagedMutation" in delete_handler
    assert "storeManagedObjectEvidence(object)" in create_handler
    assert "exactManagedObjectEvidence(object)" in descriptor
    assert "evidence.object ~= object" in evidence
    assert "evidence.id ~= objectId" in evidence
    assert "evidence.name ~= objectName" in evidence
    assert "evidence.class ~= className" in evidence
    assert "scenetree.findObjectById(objectId)" in evidence
    assert "byId ~= object" in evidence
    assert "byName ~= object" in evidence
    assert "managedObjects[objectId] = nil" not in evidence
    assert "managed object ID is already retained" in evidence
    assert "managedObjectEvidenceSceneAbsent" in source
    assert "managedEvidence" in update_handler
    assert "storeManagedObjectEvidence(object)" in update_handler
    assert update_handler.index("object:setName(params.new_name)") < update_handler.index(
        "storeManagedObjectEvidence(object)"
    )
    assert "retained evidence blocks bridge reload" in update_handler
    assert "managedObjects[managedEvidence.id] = nil" not in update_handler
    assert "managedObjects[objectId] == managedEvidence" in delete_handler
    assert "managedObjectEvidenceSceneAbsent(managedEvidence)" in delete_handler
    assert delete_handler.index("managedObjectEvidenceSceneAbsent(managedEvidence)") < (
        delete_handler.index("managedObjects[objectId] = nil")
    )
    assert "config.allow_existing_map_object_edits" in source
    start_mission = source.split("local function onClientStartMission", maxsplit=1)[1]
    start_mission = start_mission.split("local function onClientEndMission", maxsplit=1)[0]
    end_mission = source.split("local function onClientEndMission", maxsplit=1)[1]
    end_mission = end_mission.split("local function onUpdate", maxsplit=1)[0]
    assert "managedObjects = {}" in start_mission
    assert "managedObjects = {}" in end_mission


def test_emergency_stop_uses_only_fixed_vehicle_commands() -> None:
    source = bridge_source()
    stop_function = source.split("local function stopVehicle", maxsplit=1)[1]
    stop_function = stop_function.split("local function findVehicleById", maxsplit=1)[0]
    stop_handler = source.split('HANDLERS["emergency_stop"]', maxsplit=1)[1]
    stop_handler = stop_handler.split("local function validateRequest", maxsplit=1)[0]

    assert "input.event('throttle', 0, 1)" in stop_function
    assert "input.event('brake', 1, 1)" in stop_function
    assert "input.event('parkingbrake', 1, 1)" in stop_function
    assert "params" not in stop_function
    assert "params.vehicle_name" in stop_handler
    assert "findVehicleByName" in stop_handler
    assert "provide vehicle_id or vehicle_name, not both" in stop_handler


def test_safety_lease_is_bounded_by_real_time_and_fails_closed() -> None:
    source = bridge_source()

    for method in ("safety.lease_arm", "safety.lease_renew", "safety.lease_disarm"):
        assert f'HANDLERS["{method}"]' in source
        assert f'"{method}"' in source
    assert "safety_lease_seconds = 1.0" in source
    assert "safety_startup_grace_seconds = 5.0" in source
    assert "resolved.safety_lease_seconds < 0.25" in source
    assert "resolved.safety_lease_seconds > 5" in source
    assert "realElapsedSeconds = realElapsedSeconds + realDelta" in source
    assert 'expireSafetyLease("lease_expired")' in source
    assert 'expireSafetyLease("extension_unloaded")' in source
    assert 'eventEnvelope("safety.lease_expired"' in source
    assert "stopVehicle" in source
    assert "params.vehicle_name" in source
    assert "vehicle:getName() == vehicleName" in source
    assert "safety_lease_available = true" in source


def test_handlers_and_json_operations_are_protected() -> None:
    source = bridge_source()

    assert "pcall(jsonDecode, message)" in source
    assert "pcall(jsonEncode, envelope)" in source
    assert "pcall(handler, request.params" in source
    assert "pcall(BNGWebWSServer.destroy, server)" in source


def test_typed_triggers_are_isolated_from_generic_world_mutations() -> None:
    source = bridge_source()
    creatable = source.split("local CREATABLE_CLASSES = {", maxsplit=1)[1]
    creatable = creatable.split("local READ_ONLY_CLASSES", maxsplit=1)[0]
    fields = source.split("local FIELD_RULES = {", maxsplit=1)[1]
    fields = fields.split("local READ_ONLY_FIELD_RULES", maxsplit=1)[0]

    assert "BeamNGTrigger" not in creatable
    assert "BeamNGTrigger" not in fields
    for method in (
        "trigger.create",
        "trigger.get",
        "trigger.update",
        "trigger.list",
        "trigger.delete",
    ):
        assert f'HANDLERS["{method}"]' in source
        assert (
            f'"{method}"'
            in source.split('HANDLERS["capabilities"]', maxsplit=1)[1].split(
                'HANDLERS["telemetry.snapshot"]', maxsplit=1
            )[0]
        )


def test_packaged_trigger_and_particle_nodes_are_inspectable_but_not_mutable() -> None:
    source = bridge_source()
    creatable_classes = source.split("local CREATABLE_CLASSES = {", maxsplit=1)[1]
    creatable_classes = creatable_classes.split("local READ_ONLY_CLASSES", maxsplit=1)[0]
    read_only_classes = source.split("local READ_ONLY_CLASSES = {", maxsplit=1)[1]
    read_only_classes = read_only_classes.split("local COLLISION_TYPES", maxsplit=1)[0]
    writable_fields = source.split("local FIELD_RULES = {", maxsplit=1)[1]
    writable_fields = writable_fields.split("local READ_ONLY_FIELD_RULES", maxsplit=1)[0]
    read_only_fields = source.split("local READ_ONLY_FIELD_RULES = {", maxsplit=1)[1]
    read_only_fields = read_only_fields.split("local RELOADABLE_EXTENSIONS", maxsplit=1)[0]
    readable_guard = source.split("local function ensureReadableObject", maxsplit=1)[1]
    readable_guard = readable_guard.split("local function ensureWritableObject", maxsplit=1)[0]
    descriptor = source.split("local function objectDescriptor", maxsplit=1)[1]
    descriptor = descriptor.split("local function ensureReadableObject", maxsplit=1)[0]
    get_handler = source.split('HANDLERS["world.get_object"]', maxsplit=1)[1]
    get_handler = get_handler.split('HANDLERS["world.create_object"]', maxsplit=1)[0]
    list_handler = source.split('HANDLERS["world.list_objects"]', maxsplit=1)[1]
    list_handler = list_handler.split('HANDLERS["world.get_object"]', maxsplit=1)[0]
    update_handler = source.split('HANDLERS["world.update_object"]', maxsplit=1)[1]
    update_handler = update_handler.split('HANDLERS["world.delete_object"]', maxsplit=1)[0]
    delete_handler = source.split('HANDLERS["world.delete_object"]', maxsplit=1)[1]
    delete_handler = delete_handler.split('HANDLERS["world.save_level"]', maxsplit=1)[0]

    assert set(
        re.findall(
            r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*true,?$",
            read_only_classes,
            re.MULTILINE,
        )
    ) == {
        "BeamNGTrigger",
        "ParticleEmitterNode",
    }
    for class_name in ("BeamNGTrigger", "ParticleEmitterNode"):
        assert class_name not in creatable_classes
        assert class_name not in writable_fields
    assert re.search(
        r"BeamNGTrigger\s*=\s*\{\s*triggerMode\s*=\s*true,\s*"
        r"triggerTestType\s*=\s*true\s*\}",
        read_only_fields,
    )
    assert re.search(
        r"ParticleEmitterNode\s*=\s*\{\s*dataBlock\s*=\s*true,\s*"
        r"emitter\s*=\s*true\s*\}",
        read_only_fields,
    )
    assert "CREATABLE_CLASSES[className] or READ_ONLY_CLASSES[className]" in readable_guard
    assert "FIELD_RULES[className] or READ_ONLY_FIELD_RULES[className]" in descriptor
    assert "CREATABLE_CLASSES[requestedClass] or READ_ONLY_CLASSES[requestedClass]" in list_handler
    assert "CREATABLE_CLASSES[className] or READ_ONLY_CLASSES[className]" in list_handler
    assert "ensureReadableObject(object)" in get_handler
    assert "ensureWritableObject(object)" not in get_handler
    assert "ensureWritableObject(object)" in update_handler
    assert "ensureWritableObject(object)" in delete_handler


def test_typed_trigger_inputs_have_a_closed_non_executable_schema() -> None:
    source = bridge_source()
    trigger_surface = source.split("local TRIGGER_CREATE_KEYS", maxsplit=1)[1]
    trigger_surface = trigger_surface.split("local function stopLeaseVehicles", maxsplit=1)[0]

    assert "validateExactObject" in trigger_surface
    assert 'handle:sub(1, 4) ~= "trg_"' in trigger_surface
    assert "#handle ~= 36" in trigger_surface
    assert 'handle:sub(5):match("^[0-9a-f]+$")' in trigger_surface
    assert 'params.shape ~= "box"' in trigger_surface
    assert 'value.type ~= "emit_bridge_event"' in trigger_surface
    assert "TRIGGER_ACTION_EVENTS" in source
    assert 'return nil, "action.events entries must be unique"' in trigger_surface
    assert "parseExactVector3" in trigger_surface
    assert "parseExactQuaternion" in trigger_surface
    assert "params.luaFunction" not in trigger_surface
    assert "params.command" not in trigger_surface
    assert "params.name" not in trigger_surface


def test_trigger_create_is_a_peer_owned_disabled_draft() -> None:
    source = bridge_source()
    create_handler = source.split('HANDLERS["trigger.create"]', maxsplit=1)[1]
    create_handler = create_handler.split('HANDLERS["trigger.get"]', maxsplit=1)[0]
    create_helper = source.split("local function parseTriggerCreate", maxsplit=1)[1]
    create_helper = create_helper.split("local function applyTriggerPatch", maxsplit=1)[0]
    global_count = source.split("local function countManagedTriggers", maxsplit=1)[1]
    global_count = global_count.split("local function ownedTrigger", maxsplit=1)[0]

    assert "owner = peerId" in create_helper
    assert "object = nil" in create_helper
    assert "managedTriggers[record.handle] = record" in create_handler
    assert "MAX_MANAGED_TRIGGERS_PER_PEER" in create_handler
    assert "MAX_MANAGED_TRIGGERS_TOTAL" in create_handler
    assert "countManagedTriggers()" in create_handler
    assert "pairs(managedTriggers)" in global_count
    assert "record.owner" not in global_count
    assert "scenetree.findObject(record.name)" in create_handler
    assert 'createObject("BeamNGTrigger")' not in create_handler


def test_trigger_enable_uses_only_fixed_engine_fields_and_exact_identity() -> None:
    source = bridge_source()
    instantiate = source.split("local function instantiateTrigger", maxsplit=1)[1]
    instantiate = instantiate.split("local function disableTrigger", maxsplit=1)[0]
    disable = source.split("local function disableTrigger", maxsplit=1)[1]
    disable = disable.split("local function cleanupTriggerRecord", maxsplit=1)[0]
    exact_identity = source.split("local function exactLiveTrigger", maxsplit=1)[1]
    exact_identity = exact_identity.split("local function instantiateTrigger", maxsplit=1)[0]

    assert 'createObject("BeamNGTrigger")' in instantiate
    assert 'object:setField("canSave", 0, "0")' in instantiate
    assert "object.canSave = false" in instantiate
    assert 'object:setField("luaFunction", 0, "onBeamNGTrigger")' in instantiate
    assert 'object:setField("triggerType", 0, "Box")' in instantiate
    assert 'object:setField("triggerMode", 0, TRIGGER_MODE_FIELDS[record.mode])' in instantiate
    assert (
        'object:setField("triggerTestType", 0, TRIGGER_TEST_TYPE_FIELDS[record.test_type])'
    ) in instantiate
    assert 'object:setField("ticking", 0, "0")' in instantiate
    assert "object:registerObject(record.name)" in instantiate
    assert "managedTriggerIds[objectId]" in instantiate
    assert "generation = record.generation" in instantiate
    assert "managedTriggerIds[record.object_id] = nil" in disable
    assert '"beamng_mcp_trigger_" .. handle:sub(5)' in source
    assert "scenetree.findObjectById(objectId)" in exact_identity
    assert "byId ~= record.object or byName ~= record.object" in exact_identity
    assert "managedTriggerIds[objectId]" in exact_identity
    assert "nameRegistration.generation ~= record.generation" in exact_identity
    assert "idRegistration.generation ~= record.generation" in exact_identity
    assert 'className ~= "BeamNGTrigger"' in exact_identity


def test_trigger_enable_preserves_provisional_evidence_until_rollback_is_proven() -> None:
    source = bridge_source()
    instantiate = source.split("local function instantiateTrigger", maxsplit=1)[1]
    instantiate = instantiate.split("local function disableTrigger", maxsplit=1)[0]
    rollback = source.split("local function rollbackTriggerInstantiation", maxsplit=1)[1]
    rollback = rollback.split("local function instantiateTrigger", maxsplit=1)[0]

    provisional = "managedTriggers[record.handle] = record"
    object_evidence = "record.object = object"
    create = 'createObject("BeamNGTrigger")'
    assert provisional in instantiate
    assert object_evidence in instantiate
    assert instantiate.index(provisional) < instantiate.index(create)
    assert instantiate.index(object_evidence) < instantiate.index("object:registerObject")
    assert re.search(r"rollbackTriggerInstantiation\(\s*record,\s*previousRecord", instantiate)
    assert "pcall(function() object:delete() end)" not in instantiate

    assert "deleteTriggerObjectAndProveAbsent(record)" in rollback
    assert "managedTriggers[record.handle] = previousRecord" in rollback
    assert re.search(r"quarantineTrigger\(\s*record", rollback)
    assert "managedTriggers[record.handle] = record" in rollback


def test_trigger_deletion_requires_exact_post_delete_scene_absence() -> None:
    source = bridge_source()
    delete_exact = source.split("local function deleteTriggerObjectAndProveAbsent", maxsplit=1)[1]
    delete_exact = delete_exact.split("local function rollbackTriggerInstantiation", maxsplit=1)[0]
    instantiate = source.split("local function instantiateTrigger", maxsplit=1)[1]
    instantiate = instantiate.split("local function disableTrigger", maxsplit=1)[0]
    disable = source.split("local function disableTrigger", maxsplit=1)[1]
    disable = disable.split("local function cleanupTriggerRecord", maxsplit=1)[0]

    assert "local identityOk = captureTriggerObjectEvidence(record)" in delete_exact
    assert "if not identityOk then" in delete_exact
    assert "deleteResult == false" in delete_exact
    assert "lookupTriggerSceneEvidence(record)" in delete_exact
    assert "byId ~= nil or byName ~= nil or byObjectName ~= nil" in delete_exact
    assert "deleteTriggerObjectAndProveAbsent(record)" in disable
    assert disable.index("deleteTriggerObjectAndProveAbsent(record)") < disable.index(
        "clearTriggerObjectEvidence(record)"
    )
    assert "lookupTriggerSceneEvidence(record)" in instantiate
    assert "byId ~= object or byName ~= object" in instantiate
    assert instantiate.index("byId ~= object or byName ~= object") < instantiate.rindex(
        "managedTriggerNames[record.name]"
    )


def test_trigger_enable_rejects_nonthrowing_transform_noops_before_commit() -> None:
    source = bridge_source()
    scalar_near = source.split("local function triggerScalarNear", maxsplit=1)[1]
    scalar_near = scalar_near.split("local function triggerVectorNear", maxsplit=1)[0]
    quaternion_near = source.split("local function triggerQuaternionNear", maxsplit=1)[1]
    quaternion_near = quaternion_near.split(
        "local function verifyTriggerTransformReadback", maxsplit=1
    )[0]
    readback = source.split("local function verifyTriggerTransformReadback", maxsplit=1)[1]
    readback = readback.split("local function deleteTriggerObjectAndProveAbsent", maxsplit=1)[0]
    instantiate = source.split("local function instantiateTrigger", maxsplit=1)[1]
    instantiate = instantiate.split("local function disableTrigger", maxsplit=1)[0]

    assert "isFiniteNumber(actual)" in scalar_near
    assert "isFiniteNumber(expected)" in scalar_near
    assert "math.abs(actual - expected)" in scalar_near
    assert "relativeTolerance" in scalar_near
    assert "object:getPosition()" in readback
    assert "quat(object:getRotation())" in readback
    assert "object:getScale()" in readback
    assert re.search(r"triggerVectorNear\(\s*position,\s*record\.position", readback)
    assert re.search(r"triggerVectorNear\(\s*scale,\s*record\.scale", readback)
    assert "triggerQuaternionNear(rotation, record.rotation)" in readback
    assert "-expected.x" in quaternion_near
    assert "-expected.y" in quaternion_near
    assert "-expected.z" in quaternion_near
    assert "-expected.w" in quaternion_near

    verify = "verifyTriggerTransformReadback(record, object)"
    assert verify in instantiate
    after_verify = instantiate.split(verify, maxsplit=1)[1]
    assert "rollbackTriggerInstantiation" in after_verify
    assert instantiate.index(verify) < instantiate.rindex("managedTriggerNames[record.name]")


def test_enabled_triggers_are_immutable_and_delete_requires_confirmation() -> None:
    source = bridge_source()
    update_handler = source.split('HANDLERS["trigger.update"]', maxsplit=1)[1]
    update_handler = update_handler.split('HANDLERS["trigger.delete"]', maxsplit=1)[0]
    delete_handler = source.split('HANDLERS["trigger.delete"]', maxsplit=1)[1]
    delete_handler = delete_handler.split("local function onBeamNGTrigger", maxsplit=1)[0]

    assert "if record.object then" in update_handler
    assert "if hasPatch then" in update_handler
    assert "enabled triggers are immutable" in update_handler
    assert "params.enabled == false" in update_handler
    assert "disableTrigger(record)" in update_handler
    assert 'quarantineTrigger(record, "owner_disable_failed", disableError)' in update_handler
    assert "params.confirm ~= true" in delete_handler
    assert "ownedTrigger(params.handle, peerId)" in delete_handler
    assert "disableTrigger(record)" in delete_handler
    assert 'quarantineTrigger(record, "owner_delete_failed", disableError)' in delete_handler


def test_trigger_events_are_exact_vehicle_only_owner_only_and_bounded() -> None:
    source = bridge_source()
    callback = source.split("local function onBeamNGTrigger", maxsplit=1)[1]
    callback = callback.split("local function stopLeaseVehicles", maxsplit=1)[0]

    assert 'data.event ~= "enter" and data.event ~= "exit"' in callback
    assert "record.object_id ~= data.triggerID" in callback
    assert "record.name ~= data.triggerName" in callback
    assert "managedTriggerIds[data.triggerID]" in callback
    assert "nameRegistration.generation ~= idRegistration.generation" in callback
    assert "record.generation ~= nameRegistration.generation" in callback
    assert "exactLiveTrigger(record)" in callback
    assert "findVehicleById(data.subjectID)" in callback
    assert "record.action.event_set[data.event]" in callback
    assert "record.occupancy[vehicleId]" in callback
    assert "MAX_TRIGGER_EVENTS_PER_SECOND" in callback
    assert 'sendEnvelope(record.owner, eventEnvelope("trigger.event"' in callback
    assert "broadcastAuthenticated" not in callback
    assert "data.subjectName" not in callback

    occupancy_update = 'record.occupancy[vehicleId] = data.event == "enter" or nil'
    action_filter = "if not record.action.event_set[data.event] then return end"
    rate_filter = "if record.rate_count >= MAX_TRIGGER_EVENTS_PER_SECOND then return end"
    assert callback.index(occupancy_update) < callback.index(action_filter)
    assert callback.index(occupancy_update) < callback.index(rate_filter)


def test_trigger_registry_is_cleaned_at_every_ownership_boundary() -> None:
    source = bridge_source()

    assert 'revokePeerAuthentication(peerId, peer, "authentication_failed")' in source
    assert 'cleanupTriggersForPeer(peerId, "authentication_expired")' in source
    assert 'cleanupTriggersForPeer(event.peerId, "peer_reconnected")' in source
    assert 'cleanupTriggersForPeer(event.peerId, "peer_disconnected")' in source
    assert 'resetWebSocketServer("mission_started")' in source
    assert 'resetWebSocketServer("mission_ended")' in source
    assert 'cleanupAllTriggers("extension_unloaded")' in source
    assert "M.onClientStartMission" in source
    assert "M.onClientEndMission" in source
    assert "M.onBeamNGTrigger" in source


def test_extension_reload_refuses_to_discard_any_managed_scene_evidence() -> None:
    source = bridge_source()
    reload_handler = source.split('HANDLERS["extension.reload"]', maxsplit=1)[1]
    reload_handler = reload_handler.split("local function stopVehicle", maxsplit=1)[0]

    trigger_guard = "if next(managedTriggers) ~= nil then"
    object_guard = "if next(managedObjects) ~= nil then"
    schedule = "pendingReload = canonicalName"
    assert "pendingReloadMutationError()" in reload_handler
    assert trigger_guard in reload_handler
    assert object_guard in reload_handler
    assert re.search(r'protocolError\(\s*"managed_triggers_active"', reload_handler)
    assert re.search(r'protocolError\(\s*"managed_objects_active"', reload_handler)
    assert reload_handler.index(trigger_guard) < reload_handler.index(schedule)
    assert reload_handler.index(object_guard) < reload_handler.index(schedule)
    assert "pruneInvalidManagedObjectEvidence" not in source


def test_pending_reload_closes_the_same_event_batch_mutation_window() -> None:
    source = bridge_source()
    handler_boundaries = [
        ("world.create_object", 'HANDLERS["world.update_object"]'),
        ("world.update_object", 'HANDLERS["world.delete_object"]'),
        ("world.delete_object", 'HANDLERS["world.save_level"]'),
        ("world.save_level", 'HANDLERS["extension.reload"]'),
        ("trigger.create", 'HANDLERS["trigger.get"]'),
        ("trigger.update", 'HANDLERS["trigger.delete"]'),
        ("trigger.delete", "local function onBeamNGTrigger"),
    ]
    for method, boundary in handler_boundaries:
        handler = source.split(f'HANDLERS["{method}"]', maxsplit=1)[1]
        handler = handler.split(boundary, maxsplit=1)[0]
        assert "pendingReloadMutationError()" in handler, method

    reload_execution = source.split("if pendingReload then", maxsplit=1)[-1]
    reload_execution = reload_execution.split("end\nend\n\nM.onExtensionLoaded", maxsplit=1)[0]
    final_guard = "if next(managedTriggers) ~= nil or next(managedObjects) ~= nil then"
    assert final_guard in reload_execution
    assert "Cancelled bridge extension reload" in reload_execution
    assert reload_execution.index(final_guard) < reload_execution.index(
        "extensions.reload(extensionName)"
    )


def test_failed_trigger_cleanup_preserves_an_event_silent_quarantine() -> None:
    source = bridge_source()
    quarantine = source.split("local function quarantineTrigger", maxsplit=1)[1]
    quarantine = quarantine.split("local function clearExactTriggerRegistrations", maxsplit=1)[0]
    cleanup_record = source.split("local function cleanupTriggerRecord", maxsplit=1)[1]
    cleanup_record = cleanup_record.split("local function cleanupTriggersForPeer", maxsplit=1)[0]
    cleanup_failure = cleanup_record.split("if not disabled then", maxsplit=1)[1]
    cleanup_failure = cleanup_failure.split("end", maxsplit=1)[0]
    cleanup_all = source.split("local function cleanupAllTriggers", maxsplit=1)[1]
    cleanup_all = cleanup_all.split("local function releaseGoneQuarantinedTriggers", maxsplit=1)[0]
    callback = source.split("local function onBeamNGTrigger", maxsplit=1)[1]
    callback = callback.split("local function stopLeaseVehicles", maxsplit=1)[0]

    assert "record.quarantined = true" in quarantine
    assert "record.owner = nil" in quarantine
    assert "record.occupancy = {}" in quarantine
    assert "record.object = nil" not in quarantine
    assert "record.object_id = nil" not in quarantine
    assert "quarantineTrigger(record, reason, disableError)" in cleanup_failure
    assert "return nil, disableError" in cleanup_failure
    assert "managedTriggerNames[record.name] = nil" not in cleanup_failure
    assert "managedTriggerIds[record.object_id] = nil" not in cleanup_failure
    assert "managedTriggers = {}" not in cleanup_all
    assert "managedTriggerNames = {}" not in cleanup_all
    assert "managedTriggerIds = {}" not in cleanup_all
    assert "if record.quarantined then return end" in callback
    assert callback.index("if record.quarantined then return end") < callback.index(
        "exactLiveTrigger(record)"
    )


def test_quarantine_evidence_is_released_only_after_verified_mission_absence() -> None:
    source = bridge_source()
    release = source.split("local function releaseGoneQuarantinedTriggers", maxsplit=1)[1]
    release = release.split("local function parseTriggerCreate", maxsplit=1)[0]

    assert "if record.quarantined then" in release
    assert "lookupTriggerSceneEvidence(record)" in release
    assert "lookupOk and byId == nil and byName == nil and byObjectName == nil" in release
    assert "clearExactTriggerRegistrations(record)" in release
    assert "managedTriggers[handle] = nil" in release
    assert 'releaseGoneQuarantinedTriggers("mission_started")' in source
    assert 'releaseGoneQuarantinedTriggers("mission_ended")' in source
