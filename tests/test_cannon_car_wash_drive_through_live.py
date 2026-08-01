"""v1.14 creator-report regression gate (youtu.be/OFEZ1Hjffno?t=748).

Three scenarios with one session, all verified by querying the runtime's
getSystemState export and the subject's kinematics (the sentinel's
beamng.log buffers and cannot be tailed reliably mid-session):

1. Rolling traffic passes straight through the wash untouched — no grab,
   no repair reset, speed retained.
2. A parked car that changes its mind ESCAPES: drive out of the bay during
   the free countdown and the shot aborts (v1.14 removed the controller
   freeze that used to lock players in).
3. A parked car that stays gets the full service and the cannon launch.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.beamng_live

REPO_ROOT = Path(__file__).resolve().parents[1]
WASH_ROOT = REPO_ROOT / "examples" / "cannon_car_wash"
MOD_ID = "ericrolph_cannon_car_wash"
EXTENSION_NAME = "ericrolph__cannon__car__wash_runtime"

DRIVE_THROUGH_SPEED_MPS = 12.0
EXIT_MIN_Y_TRAVEL = 38.0
ESCAPE_SPEED_MPS = 12.0
SERVICE_TIMEOUT_SECONDS = 200.0
LAUNCH_MIN_SPEED_MPS = 40.0


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the drive-through live gate"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the drive-through live gate requires a sentinel-isolated profile")
    return home, user, resolved_binary


def test_cannon_car_wash_pass_escape_and_launch(tmp_path: Path) -> None:
    home, user, binary = _configured_runtime()

    from beamngpy import BeamNGpy, Scenario, Vehicle

    dist_zip = WASH_ROOT / "dist" / "cannon_car_wash_ericrolph.zip"
    assert dist_zip.is_file(), "run build_distribution.py first"
    suffix = uuid.uuid4().hex[:8]
    # Stage UNPACKED: the wash zip ships fixed-epoch member timestamps and
    # the long-lived sentinel's mod cache wins over them; unpacked mods
    # bypass the zip cache entirely.
    staged = user / "mods" / "unpacked" / f"drive_through_{suffix}"
    with zipfile.ZipFile(dist_zip) as archive:
        archive.extractall(staged)

    bng = BeamNGpy(
        "127.0.0.1",
        25264,
        home=str(home),
        binary=str(binary),
        user=str(user.parent),
        quit_on_close=False,
        headless=True,
    )

    def lua(cmd: str):
        return json.loads(bng.control.queue_lua_command(cmd, response=True))

    def step(seconds: float) -> None:
        steps = max(1, int(seconds * 60))
        while steps > 0:
            chunk = min(steps, 30)
            bng.control.step(chunk, wait=True)
            steps -= chunk

    def wash_state() -> dict:
        return lua(
            f"local ext = extensions['{EXTENSION_NAME}']; "
            "local prop = scenetree.findObject('wash_prop'); "
            "if not ext or not prop then return jsonEncode({registered = false}) end; "
            "return jsonEncode(ext.getSystemState(prop:getID()))"
        )

    def subject_state() -> dict:
        return lua(
            "local subject = scenetree.findObject('drive_subject'); "
            "if not subject then return jsonEncode({ok = false}) end; "
            "local position = subject:getPosition(); "
            "local velocity = subject:getVelocity(); "
            "return jsonEncode({ok = true, x = position.x, y = position.y, z = position.z, "
            "speed = velocity:length()})"
        )

    def push_subject(speed_mps: float) -> None:
        lua(
            "local subject = scenetree.findObject('drive_subject'); "
            f"subject:applyClusterVelocityScaleAdd(subject:getRefNodeId(), 0, 0, "
            f"-{speed_mps}, 0); "
            "return jsonEncode({ok = true})"
        )

    def teleport_to_bay() -> None:
        lua(
            "local subject = scenetree.findObject('drive_subject'); "
            "subject:setPositionRotation(0.6, 0.0, 0.35, 0, 0, 0, 1); "
            "return jsonEncode({ok = true})"
        )

    def creep_to_rear_zone() -> None:
        # v1.18: the countdown arms only in the REAR wax/dry section
        # (local y > 2.05 = world y < -2.05 at identity). Take the service
        # where the car lands, then roll gently rearward into the zone.
        deadline = time.time() + SERVICE_TIMEOUT_SECONDS
        while time.time() < deadline:
            step(0.5)
            snapshot = wash_state()
            if snapshot.get("repair_pending_count", 0) == 0 and snapshot.get("wash_active"):
                break
        while time.time() < deadline + 20:
            snapshot = wash_state()
            if snapshot.get("active_phase") == "countdown":
                # Entering the rear zone can start the countdown mid-creep;
                # stop immediately so the caller observes it.
                push_subject(0.0)
                return
            if subject_state()["y"] <= -2.8:
                break
            push_subject(2.2)
            step(0.7)
        push_subject(0.0)
        step(1.0)

    def wait_for_phase(target: str, timeout_seconds: float) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            step(0.5)
            if wash_state().get("active_phase") == target:
                return True
        return False

    try:
        bng.open(launch=True, listen_ip="127.0.0.1")
        scenario = Scenario("smallgrid", f"drive_through_{suffix}", description="v1.14 gate")
        anchor = Vehicle("gate_anchor", "pigeon")
        scenario.add_vehicle(anchor, pos=(-120, -120, 20), rot_quat=(0, 0, 0, 1), cling=False)
        scenario.make(bng)
        bng.control.pause()
        bng.scenario.load(scenario, precompile_shaders=False)
        bng.scenario.start()
        bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
        bng.control.pause()
        bng.control.step(3, wait=True)

        wash = Vehicle("wash_prop", MOD_ID)
        assert bng.vehicles.spawn(wash, (0.0, 0.0, 0.0), (0, 0, 0, 1), False, True)
        registered = False
        deadline = time.time() + 90
        while time.time() < deadline:
            step(0.5)
            if wash_state().get("registered"):
                registered = True
                break
        assert registered, {"detail": "wash prop never registered", "state": wash_state()}

        subject = Vehicle("drive_subject", "etk800")
        assert bng.vehicles.spawn(subject, (0.0, 30.0, 0.2), (0, 0, 0, 1), False, True)
        step(1.5)
        # Fresh spawns hold their parking brake: a single velocity push
        # coasts to a stop in ~10 m (first run of this gate proved it).
        lua(
            "local subject = scenetree.findObject('drive_subject'); "
            "subject:queueLuaCommand('input.event(\"parkingbrake\", 0, FILTER_DIRECT)'); "
            "return jsonEncode({ok = true})"
        )
        step(0.5)

        # ---- Part 1: cruise straight through at speed; hands off. ----
        start = subject_state()
        assert start["ok"]
        push_subject(DRIVE_THROUGH_SPEED_MPS)
        grabbed_phases: list[str] = []
        for _ in range(24):
            step(0.5)
            phase = wash_state().get("active_phase")
            if phase:
                grabbed_phases.append(phase)
            state = subject_state()
            if state["ok"] and start["y"] - state["y"] >= EXIT_MIN_Y_TRAVEL:
                break
            # Sustain cruising speed through the tunnel: rolling drag and
            # the wash's floor lip bleed a coasting car below test speed.
            if state["ok"] and state["speed"] < DRIVE_THROUGH_SPEED_MPS - 2.0:
                push_subject(DRIVE_THROUGH_SPEED_MPS)
        state = subject_state()
        assert start["y"] - state["y"] >= EXIT_MIN_Y_TRAVEL, {
            "detail": "subject never cleared the far side of the wash",
            "travel": start["y"] - state["y"],
        }
        assert state["speed"] > 3.5, {
            "detail": "rolling traffic was slowed/held by the wash",
            "speed": state["speed"],
        }
        assert grabbed_phases == [], {
            "detail": "the wash started a run on a rolling car",
            "phases": grabbed_phases,
        }
        snapshot = wash_state()
        assert snapshot.get("repair_pending_count", 0) == 0, snapshot

        # ---- Part 2: park, take the service, then ESCAPE the countdown. ----
        teleport_to_bay()
        creep_to_rear_zone()
        assert wait_for_phase("countdown", SERVICE_TIMEOUT_SECONDS), {
            "detail": "countdown never started for a parked car",
            "state": wash_state(),
        }
        push_subject(ESCAPE_SPEED_MPS)
        escaped = False
        peak_speed = 0.0
        pushes = 0
        deadline = time.time() + 20
        while time.time() < deadline:
            step(0.5)
            state = subject_state()
            peak_speed = max(peak_speed, state.get("speed", 0.0))
            snapshot = wash_state()
            if snapshot.get("active_phase") is None and snapshot.get("armed"):
                escaped = True
                break
            if pushes < 3 and state.get("speed", 0.0) < ESCAPE_SPEED_MPS - 2.0:
                push_subject(ESCAPE_SPEED_MPS)
                pushes += 1
        assert escaped, {
            "detail": "driving out of the bay did not abort the countdown",
            "state": wash_state(),
        }
        for _ in range(8):
            step(0.5)
            state = subject_state()
            peak_speed = max(peak_speed, state.get("speed", 0.0))
        assert peak_speed < 30.0, {
            "detail": "the cannon fired at an escaping car",
            "peak_speed": peak_speed,
        }

        # ---- Part 3: park again, stay put, take the cannon. ----
        teleport_to_bay()
        creep_to_rear_zone()
        assert wait_for_phase("countdown", SERVICE_TIMEOUT_SECONDS), {
            "detail": "countdown never re-armed after the escape",
            "state": wash_state(),
        }
        launched = False
        launch_speed = 0.0
        deadline = time.time() + 30
        while time.time() < deadline:
            step(0.5)
            state = subject_state()
            launch_speed = max(launch_speed, state.get("speed", 0.0))
            if wash_state().get("active_phase") == "launched" or (
                launch_speed >= LAUNCH_MIN_SPEED_MPS
            ):
                launched = True
                break
        assert launched, {
            "detail": "the cannon never fired for a car that stayed",
            "state": wash_state(),
            "peak_speed": launch_speed,
        }
        for _ in range(6):
            step(0.5)
            state = subject_state()
            launch_speed = max(launch_speed, state.get("speed", 0.0))
        assert launch_speed >= LAUNCH_MIN_SPEED_MPS, {
            "detail": "launch phase reached but the car never got cannon velocity",
            "peak_speed": launch_speed,
        }
    finally:
        try:
            if bng.process is not None:
                bng.close()
                if bng.process is not None and bng.process.poll() is None:
                    bng.process.terminate()
        finally:
            shutil.rmtree(staged, ignore_errors=True)


def test_cannon_car_wash_rotated_service_and_launch(tmp_path: Path) -> None:
    """v1.19 belt-and-suspenders: the full service-to-cannon chain at a
    35-degree placement. BeamNGTrigger volumes silently drop driven entries
    at non-cardinal yaws, so this exercises the v1.15 positional zone
    detection end to end. Frame-independence comes from the runtime's own
    last_sweep_local report rather than any hand-derived axis math (the
    hand-derived kind parked three probe cars beside the building)."""

    import math

    home, user, binary = _configured_runtime()

    from beamngpy import BeamNGpy, Scenario, Vehicle

    dist_zip = WASH_ROOT / "dist" / "cannon_car_wash_ericrolph.zip"
    assert dist_zip.is_file(), "run build_distribution.py first"
    suffix = uuid.uuid4().hex[:8]
    staged = user / "mods" / "unpacked" / f"rotated_gate_{suffix}"
    with zipfile.ZipFile(dist_zip) as archive:
        archive.extractall(staged)

    yaw = math.radians(35.0)
    rot = (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))
    bng = BeamNGpy(
        "127.0.0.1",
        25265,
        home=str(home),
        binary=str(binary),
        user=str(user.parent),
        quit_on_close=False,
        headless=True,
    )

    def lua(cmd: str):
        return json.loads(bng.control.queue_lua_command(cmd, response=True))

    def step(seconds: float) -> None:
        steps = max(1, int(seconds * 60))
        while steps > 0:
            chunk = min(steps, 30)
            bng.control.step(chunk, wait=True)
            steps -= chunk

    def wash_state() -> dict:
        return lua(
            f"local ext = extensions['{EXTENSION_NAME}']; "
            "local prop = scenetree.findObject('wash_prop'); "
            "if not ext or not prop then return jsonEncode({registered = false}) end; "
            "return jsonEncode(ext.getSystemState(prop:getID()))"
        )

    def subject_local_y() -> float:
        # Direct trigger-frame projection of THIS subject: last_sweep_local
        # reports whichever vehicle the sweep touched last (the scenario
        # anchor masked the car in the first run of this gate).
        result = lua(
            "local st = extensions['" + EXTENSION_NAME + "'].getSystemState("
            "scenetree.findObject('wash_prop'):getID()); "
            "local trigger = scenetree.findObject(st.wash_trigger.name); "
            "local subject = scenetree.findObject('rot_subject'); "
            "if not trigger or not subject then return jsonEncode({y = -99}) end; "
            "local delta = subject:getPosition() - trigger:getPosition(); "
            "local column = trigger:getTransform():getColumn(1); "
            "return jsonEncode({y = delta.x * column.x + delta.y * column.y})"
        )
        return result["y"]

    def push_local_forward(speed_mps: float) -> None:
        # Drive direction is prop-local -Y; convert through the wash trigger
        # frame measured from the live object (never hand-derived).
        lua(
            "local st = extensions['" + EXTENSION_NAME + "'].getSystemState("
            "scenetree.findObject('wash_prop'):getID()); "
            "local trigger = scenetree.findObject(st.wash_trigger.name); "
            "local column = trigger:getTransform():getColumn(1); "
            "local subject = scenetree.findObject('rot_subject'); "
            f"subject:applyClusterVelocityScaleAdd(subject:getRefNodeId(), 0, "
            f"column.x * {speed_mps}, column.y * {speed_mps}, 0); "
            "return jsonEncode({ok = true})"
        )

    try:
        bng.open(launch=True, listen_ip="127.0.0.1")
        scenario = Scenario("smallgrid", f"rotated_gate_{suffix}", description="rotated gate")
        anchor = Vehicle("gate_anchor", "pigeon")
        scenario.add_vehicle(anchor, pos=(-120, -120, 20), rot_quat=(0, 0, 0, 1), cling=False)
        scenario.make(bng)
        bng.control.pause()
        bng.scenario.load(scenario, precompile_shaders=False)
        bng.scenario.start()
        bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
        bng.control.pause()
        bng.control.step(3, wait=True)

        wash = Vehicle("wash_prop", MOD_ID)
        assert bng.vehicles.spawn(wash, (0.0, 0.0, 0.0), rot, False, True)
        registered = False
        deadline = time.time() + 90
        while time.time() < deadline:
            step(0.5)
            if wash_state().get("registered"):
                registered = True
                break
        assert registered, {"detail": "rotated wash never registered"}

        # Spawn the subject at the WASH TRIGGER's measured world centre —
        # NOT the prop origin, which sits ~12 m outside the tunnel (a probe
        # discovered every earlier attempt had parked the car beside the
        # building).
        bay = lua(
            "local st = extensions['" + EXTENSION_NAME + "'].getSystemState("
            "scenetree.findObject('wash_prop'):getID()); "
            "local trigger = scenetree.findObject(st.wash_trigger.name); "
            "local p = trigger:getPosition(); "
            "return jsonEncode({x = p.x, y = p.y})"
        )
        # Spawn CLEAR of the prop (BeamNG safe-placement silently
        # relocates a vehicle spawned inside another vehicle's bounds —
        # probed: every spawn-at-bay attempt landed 12.5 m outside), then
        # teleport in exactly, matching how players actually arrive.
        subject = Vehicle("rot_subject", "etk800")
        assert bng.vehicles.spawn(
            subject, (bay["x"] + 40.0, bay["y"] + 40.0, 0.3), rot, False, True
        )
        step(1.5)
        lua(
            "local s = scenetree.findObject('rot_subject'); "
            f"s:setPositionRotation({bay['x']}, {bay['y']}, 0.35, "
            f"{rot[0]}, {rot[1]}, {rot[2]}, {rot[3]}); "
            "return jsonEncode({ok = true})"
        )
        lua(
            "local s = scenetree.findObject('rot_subject'); "
            "s:queueLuaCommand('input.event(\"parkingbrake\", 0, FILTER_DIRECT)'); "
            "return jsonEncode({ok = true})"
        )
        serviced = False
        deadline = time.time() + SERVICE_TIMEOUT_SECONDS
        while time.time() < deadline:
            step(0.5)
            snapshot = wash_state()
            if snapshot.get("wash_active") and snapshot.get("repair_pending_count", 0) == 0:
                serviced = True
                break
        assert serviced, {"detail": "rotated wash never serviced the car", "state": wash_state()}

        # Creep rearward in the PROP frame until the rear launch zone.
        launched = False
        peak = [0.0]

        def observe() -> None:
            speed = lua(
                "local s = scenetree.findObject('rot_subject'); "
                "return jsonEncode({speed = s:getVelocity():length()})"
            )["speed"]
            peak[0] = max(peak[0], speed)

        deadline = time.time() + SERVICE_TIMEOUT_SECONDS
        while time.time() < deadline:
            snapshot = wash_state()
            if snapshot.get("active_phase") == "countdown":
                break
            if subject_local_y() < 2.4:
                push_local_forward(2.2)
            step(0.7)
        deadline = time.time() + 45
        while time.time() < deadline:
            step(0.5)
            observe()
            if wash_state().get("active_phase") == "launched" or peak[0] >= LAUNCH_MIN_SPEED_MPS:
                launched = True
                break
        assert launched, {
            "detail": "rotated cannon never fired",
            "state": wash_state(),
            "peak_speed": peak[0],
        }
    finally:
        try:
            if bng.process is not None:
                bng.close()
                if bng.process is not None and bng.process.poll() is None:
                    bng.process.terminate()
        finally:
            shutil.rmtree(staged, ignore_errors=True)
