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
    assert 'local BRIDGE_VERSION = "0.2.0"' in source
    assert "bridge_version = BRIDGE_VERSION" in source
    assert "game_version = tostring" in source


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
    assert "MAX_OBJECT_RESULTS" in source
    assert "#message > config.max_payload_bytes" in source
    assert "#encoded > config.max_payload_bytes" in source


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
    update_handler = source.split('HANDLERS["world.update_object"]', maxsplit=1)[1]
    update_handler = update_handler.split('HANDLERS["world.delete_object"]', maxsplit=1)[0]
    delete_handler = source.split('HANDLERS["world.delete_object"]', maxsplit=1)[1]
    delete_handler = delete_handler.split('HANDLERS["world.save_level"]', maxsplit=1)[0]

    assert "allow_existing_map_object_edits = false" in source
    assert "ensureManagedMutation" in update_handler
    assert "ensureManagedMutation" in delete_handler
    assert "managedObjects[object:getId()]" in source
    assert "config.allow_existing_map_object_edits" in source


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
