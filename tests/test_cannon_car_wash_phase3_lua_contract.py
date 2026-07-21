from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOD_ROOT = PROJECT_ROOT / "examples" / "cannon_car_wash" / "mod"
EXTENSION = MOD_ROOT / "lua" / "ge" / "extensions" / "cannon_car_wash" / "main.lua"
BOOTSTRAP = MOD_ROOT / "scripts" / "cannon_car_wash" / "modScript.lua"
PREFAB = (
    MOD_ROOT
    / "levels"
    / "gridmap_v2"
    / "scenarios"
    / "cannon_car_wash"
    / "cannon_car_wash.prefab.json"
)


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

    match = re.search(rf"(?:local\s+function|function\s+M\.)\s*{name}\s*\(", source)
    assert match is not None, f"missing Lua function {name}"
    return source[match.start() :]


def test_phase3_payload_has_the_beamng_entry_points_and_exact_bootstrap() -> None:
    assert EXTENSION.is_file()
    assert BOOTSTRAP.is_file()
    assert PREFAB.is_file()

    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    assert _lua_string(bootstrap, "EXTENSION_PATH") == "cannon_car_wash/main"
    assert "extensions.load(EXTENSION_PATH)" in bootstrap
    assert "loadstring" not in bootstrap.lower()
    assert "dofile" not in bootstrap.lower()

    prefab = [
        json.loads(line) for line in PREFAB.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    trigger = next(record for record in prefab if record["name"] == "LaunchTrigger_Mesh")
    assert trigger["class"] == "BeamNGTrigger"
    assert trigger["luaFunction"] == "onBeamNGTrigger"

    source = extension_source()
    for callback in (
        "onBeamNGTrigger",
        "onPreRender",
        "onClientStartMission",
        "onClientEndMission",
        "onExtensionLoaded",
        "onExtensionUnloaded",
    ):
        _function_tail(source, callback)
        assert f"M.{callback}" in source


def test_trigger_callback_requires_exact_live_trigger_and_exact_pickup() -> None:
    source = extension_source()
    callback = _function_tail(source, "onBeamNGTrigger")

    assert _lua_string(source, "TRIGGER_NAME") == "LaunchTrigger_Mesh"
    assert _lua_string(source, "TRUCK_NAME") == "cannon_car_wash_truck"
    assert _lua_string(source, "TRUCK_MODEL") == "pickup"

    # Do not accept an event solely because its user-controlled names happen to
    # match.  Resolve both live objects and bind the event to their numeric IDs.
    assert "data.triggerName" in callback
    assert "data.triggerID" in callback
    assert "data.subjectID" in callback
    assert re.search(r"scenetree\.findObject\s*\(\s*TRIGGER_NAME\s*\)", source)
    assert re.search(
        r"\w+:getClassName\(\)\s*~=\s*(?:TRIGGER_CLASS|[\"']BeamNGTrigger[\"'])",
        source,
    )
    assert re.search(r"\w+:getId\(\)\s*~=\s*data\.triggerID", source)
    assert re.search(
        r"(?:be:getObjectByID|scenetree\.findObjectById)\s*\(\s*data\.subjectID\s*\)",
        source,
    )
    assert re.search(r"\w+:getId\(\)\s*~=\s*data\.subjectID", source)
    assert re.search(r"\w+:getName\(\)\s*~=\s*TRUCK_NAME", source)
    assert re.search(r"\w+:getJBeamFilename\(\)\s*~=\s*TRUCK_MODEL", source)

    enter_guard = re.search(r"data\.event\s*~=\s*[\"']enter[\"']", callback)
    assert enter_guard is not None
    assert callback.index("data.triggerName") < callback.index("hold_start")


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
    assert "launchVehicle(vehicle)" in countdown
    assert "activeRun.number ~= runNumber" in countdown


def test_countdown_uses_stable_ui_messages_and_observable_event_names() -> None:
    source = extension_source()

    assert _lua_string(source, "UI_CATEGORY") == "cannon_car_wash_countdown"
    assert "guihooks.message" in source
    assert re.search(
        r"guihooks\.message\s*\(\s*{\s*txt\s*=\s*[^}]+}\s*,\s*[^,]+,\s*UI_CATEGORY\s*\)",
        source,
        flags=re.DOTALL,
    )

    for event in (
        "trigger_enter",
        "hold_start",
        "countdown_timer_start",
        "countdown_3",
        "countdown_2",
        "countdown_1",
        "go",
        "release",
        "launch",
        "abort",
        "error",
    ):
        assert f'"{event}"' in source or f"'{event}'" in source


def test_hold_uses_vehicle_input_freeze_plus_per_frame_physics_zeroing() -> None:
    source = extension_source()
    update = _function_tail(source, "onPreRender")
    normalized_quotes = source.replace('"', "'")

    for command in (
        "ai.setMode('disabled')",
        "input.event('throttle', 0, 1)",
        "input.event('brake', 1, 1)",
        "input.event('parkingbrake', 1, 1)",
        "controller.setFreeze(1)",
    ):
        assert command in normalized_quotes
    assert "queueLuaCommand" in source

    zero_velocity = re.compile(
        r"(?P<vehicle>[A-Za-z_]\w*):applyClusterVelocityScaleAdd\(\s*"
        r"(?P=vehicle):getRefNodeId\(\)\s*,\s*0\s*,\s*0\s*,\s*0\s*,\s*0\s*\)",
        flags=re.DOTALL,
    )
    assert zero_velocity.search(update)
    assert re.search(r"if\s+[^\n]*hold", update, flags=re.IGNORECASE)


def test_release_precedes_an_exact_100_mps_forward_velocity_replacement() -> None:
    source = extension_source()
    normalized_quotes = source.replace('"', "'")

    assert _lua_number(source, "LAUNCH_SPEED_MPS") == 100.0
    for command in (
        "controller.setFreeze(0)",
        "input.event('parkingbrake', 0, 1)",
        "input.event('brake', 0, 1)",
        "input.event('throttle', 0, 1)",
    ):
        assert command in normalized_quotes

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

    release_position = source.index("controller.setFreeze(0)")
    launch_position = launch_call.start()
    assert release_position < launch_position
    assert source.count("applyClusterVelocityScaleAdd") >= 2


def test_active_run_is_single_shot_but_exit_reset_and_lifecycle_rearm_it() -> None:
    source = extension_source()
    callback = _function_tail(source, "onBeamNGTrigger")

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
        tail = _function_tail(source, callback_name)
        assert "abortActiveRun" in tail
        assert "resetState" in tail

    assert "M.onVehicleResetted" in source
    assert "M.onVehicleDestroyed" in source
    assert source.count("abortActiveRun") >= 4
    assert source.count("resetState") >= 4


def test_logs_are_tagged_versioned_json_records_not_human_only_messages() -> None:
    source = extension_source()

    assert _lua_string(source, "LOG_TAG") == "CANNON_CAR_WASH"
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
