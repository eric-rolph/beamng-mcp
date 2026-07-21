from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = PROJECT_ROOT / "examples" / "cannon_car_wash"
MOD_ROOT = EXAMPLE_ROOT / "mod"
MOD_ID = "ericrolph_cannon_car_wash"
LAUNCH_TRIGGER_NAME = f"{MOD_ID}_launch_trigger"
WASH_TRIGGER_NAME = f"{MOD_ID}_wash_activation_trigger"
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
        "onExtensionLoaded",
        "onExtensionUnloaded",
    ):
        _function_tail(source, callback)
        assert f"M.{callback}" in source


def test_trigger_callback_requires_exact_live_trigger_and_exact_pickup() -> None:
    source = extension_source()
    dispatch = _function_section(source, "onBeamNGTrigger")
    launch_callback = _function_section(source, "handleLaunchTrigger")
    trigger_resolver = _function_section(source, "exactTriggerFromEvent")
    vehicle_resolver = _function_section(source, "exactVehicleFromEvent")
    truck_resolver = _function_section(source, "exactTruckFromEvent")

    assert _lua_string(source, "LAUNCH_TRIGGER_NAME") == LAUNCH_TRIGGER_NAME
    assert _lua_string(source, "WASH_TRIGGER_NAME") == WASH_TRIGGER_NAME
    assert _lua_string(source, "TRUCK_NAME") == TRUCK_NAME
    assert _lua_string(source, "TRUCK_MODEL") == "pickup"

    assert "handleWashTrigger(data)" in dispatch
    assert "handleLaunchTrigger(data)" in dispatch
    assert "data.triggerName == WASH_TRIGGER_NAME" in dispatch
    assert "data.triggerName == LAUNCH_TRIGGER_NAME" in dispatch

    # Do not accept an event solely because its user-controlled names happen to
    # match.  Resolve both live objects and bind the event to their numeric IDs.
    assert "data.triggerName" in launch_callback
    assert "data.triggerID" in launch_callback
    assert "data.subjectID" in launch_callback
    assert 'exactTriggerFromEvent(data, LAUNCH_TRIGGER_NAME, "Contains")' in launch_callback
    assert 'exactTriggerFromEvent(data, WASH_TRIGGER_NAME, "Overlaps")' in source
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
    assert re.search(r"\w+:getName\(\)\s*~=\s*TRUCK_NAME", truck_resolver)
    assert re.search(r"\w+:getJBeamFilename\(\)\s*~=\s*TRUCK_MODEL", truck_resolver)

    enter_guard = re.search(r"data\.event\s*~=\s*[\"']enter[\"']", launch_callback)
    assert enter_guard is not None
    assert launch_callback.index("data.triggerName") < launch_callback.index("hold_start")


def test_wash_trigger_controls_all_rollers_and_stock_sprinkler_misters() -> None:
    source = extension_source()
    wash_callback = _function_section(source, "handleWashTrigger")
    wash_systems = _function_section(source, "setWashSystemsEnabled")
    wash_resolver = _function_section(source, "resolveWashObjects")
    wash_rollback = _function_section(source, "forceWashSystemsOff")

    assert _lua_string(source, "VISUAL_NAME") == SCENARIO_VISUAL_NAME
    assert _lua_string(source, "VISUAL_CLASS") == "TSStatic"
    assert _lua_string(source, "MISTER_CLASS") == "ParticleEmitterNode"

    mister_table = re.search(
        r"local\s+MISTER_NAMES\s*=\s*{(?P<body>.*?)}",
        source,
        flags=re.DOTALL,
    )
    assert mister_table is not None
    mister_names = re.findall(r"[\"']([^\"']+)[\"']", mister_table.group("body"))
    assert mister_names == [
        f"{MOD_ID}_mister_{arch}_{side}_{height}"
        for arch in ("PreSoak", "Rinse")
        for side in ("L", "R")
        for height in range(1, 4)
    ]

    assert 'visual:setField("playAmbient", 0, expectedField)' in wash_systems
    assert "exactSceneObject(name, MISTER_CLASS)" in wash_resolver
    assert "mister:setActive(enabled)" in wash_systems
    assert "resolveWashObjects()" in wash_systems
    assert wash_systems.count("forceWashSystemsOff(visual, misters)") >= 2
    assert 'visual:setField("playAmbient", 0, "0")' in wash_rollback
    assert "mister:setActive(false)" in wash_rollback
    assert "washSystemsActive = false" in wash_rollback
    assert 'mister_emitter = "BNGP_sprinkler"' in wash_systems
    assert "mister_count = #MISTER_NAMES" in wash_systems

    assert re.search(r"washSubjects\[data\.subjectID\]\s*=\s*true", wash_callback)
    assert re.search(r"washSubjects\[data\.subjectID\]\s*=\s*nil", wash_callback)
    assert 'setWashSystemsEnabled(true, "vehicle_enter", true)' in wash_callback
    assert re.search(
        r"washSubjectCount\(\)\s*==\s*0\s+and\s+washSystemsActive",
        wash_callback,
    )
    assert 'setWashSystemsEnabled(false, "last_vehicle_exit", true)' in wash_callback
    for event in (
        "wash_trigger_enter",
        "wash_systems_start",
        "wash_trigger_exit",
        "wash_systems_stop",
    ):
        assert f'"{event}"' in source or f"'{event}'" in source

    assert re.search(r"M\.getSystemState\s*=\s*washSystemState", source)


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
        "vehicle_name": TRUCK_NAME,
        "vehicle_model": "pickup",
    }
    assert manifest["wash_cycle"] == {
        "scope": "full_bay",
        "enter": {
            "roller_visual": SCENARIO_VISUAL_NAME,
            "roller_sequence": "ambient",
            "roller_play_ambient": True,
            "mister_emitter": "BNGP_sprinkler",
            "mister_count": 12,
            "misters_active": True,
        },
        "exit": {
            "roller_play_ambient": False,
            "misters_active": False,
        },
        "mission_initial_state": "off",
        "subject_tracking": "vehicle_id_set",
    }
    assert manifest["containment_gate"] == {
        "required_trigger": LAUNCH_TRIGGER_NAME,
        "required_mode": "Contains",
        "required_test_type": "Bounding box",
        "required_vehicle_state": f"previously_entered_{WASH_TRIGGER_NAME}",
        "required_wash_system_state": "active",
        "out_of_order_policy": "defer_until_wash_active",
        "action": "begin_countdown",
    }
    assert manifest["telemetry"]["wash_events"] == [
        "wash_trigger_enter",
        "wash_systems_start",
        "wash_trigger_exit",
        "wash_systems_stop",
    ]
    assert manifest["telemetry"]["launch_gate_event"] == "containment_verified"
    assert manifest["telemetry"]["launch_deferred_event"] == "launch_deferred"


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
        < launch_callback.index("HOLD_VEHICLE_COMMAND")
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
    assert "launchVehicle(vehicle)" in countdown
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
        "containment_verified",
        "trigger_enter",
        "hold_start",
        "countdown_timer_start",
        "countdown_3",
        "countdown_2",
        "countdown_1",
        "go",
        "release",
        "launch",
        "wash_trigger_exit",
        "wash_systems_stop",
        "launch_deferred",
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
