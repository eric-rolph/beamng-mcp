"""Low VRAM edition live gate.

One sentinel session proves the derived mod is a real, working car wash:
the selector prop registers under its own renamed GE extension (the escaped
``ericrolph__cannon__car__wash__lowvram_runtime`` identifier answers
getSystemState, which is also the panel buttons' call path), the 22 wash
emitters exist but stay INACTIVE by default while a car takes the service,
the mini panel's spray-effects toggle turns all 22 on and off again
mid-wash, the scene carries exactly the five planned lights, and the parked
car still gets the full countdown and cannon launch.
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
MOD_ID = "ericrolph_cannon_car_wash_lowvram"
EXTENSION_NAME = "ericrolph__cannon__car__wash__lowvram_runtime"

SERVICE_TIMEOUT_SECONDS = 200.0
LAUNCH_MIN_SPEED_MPS = 40.0


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the low VRAM live gate"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the low VRAM live gate requires a sentinel-isolated profile")
    return home, user, resolved_binary


def test_low_vram_service_launch_without_effects(tmp_path: Path) -> None:
    home, user, binary = _configured_runtime()

    from beamngpy import BeamNGpy, Scenario, Vehicle

    dist_zip = WASH_ROOT / "dist" / "cannon_car_wash_lowvram_ericrolph.zip"
    assert dist_zip.is_file(), "run build_low_vram_variant.py first"
    suffix = uuid.uuid4().hex[:8]
    staged = user / "mods" / "unpacked" / f"low_vram_{suffix}"
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

    def scene_census() -> dict:
        return lua(
            "local function ours(class) "
            "  local names = scenetree.findClassObjects(class) or {}; "
            "  local count = 0; "
            "  for _, name in ipairs(names) do "
            f"    if string.find(tostring(name), '{MOD_ID}', 1, true) then "
            "      count = count + 1 "
            "    end "
            "  end "
            "  return count "
            "end; "
            "return jsonEncode({emitters = ours('ParticleEmitterNode'), "
            "points = ours('PointLight'), spots = ours('SpotLight')})"
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

    def creep_to_rear_zone() -> None:
        deadline = time.time() + SERVICE_TIMEOUT_SECONDS
        while time.time() < deadline:
            step(0.5)
            snapshot = wash_state()
            if snapshot.get("repair_pending_count", 0) == 0 and snapshot.get("wash_active"):
                break
        while time.time() < deadline + 20:
            snapshot = wash_state()
            if snapshot.get("active_phase") == "countdown":
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
        scenario = Scenario("smallgrid", f"low_vram_{suffix}", description="low VRAM gate")
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
        assert registered, {"detail": "low VRAM wash never registered", "state": wash_state()}

        # ---- Variant contract: 22 emitters present (opt-in, so they exist
        # but must be inactive), exactly the 5-light plan. ----
        census = scene_census()
        assert census["emitters"] == 22, {
            "detail": "the low VRAM wash should define all 22 wash emitters",
            "census": census,
        }
        assert census["points"] == 3 and census["spots"] == 2, {
            "detail": "light roster differs from the 3-point + 2-spot plan",
            "census": census,
        }
        snapshot = wash_state()
        assert snapshot.get("effect_present_count") == 22, snapshot
        assert snapshot.get("effect_active_count") == 0, {
            "detail": "wash emitters active before any car or toggle",
            "state": snapshot,
        }

        subject = Vehicle("drive_subject", "etk800")
        assert bng.vehicles.spawn(subject, (0.0, 30.0, 0.2), (0, 0, 0, 1), False, True)
        step(1.5)
        lua(
            "local subject = scenetree.findObject('drive_subject'); "
            "subject:queueLuaCommand('input.event(\"parkingbrake\", 0, FILTER_DIRECT)'); "
            "return jsonEncode({ok = true})"
        )
        step(0.5)

        # ---- Park in the bay, take the service, stay for the cannon. ----
        lua(
            "local subject = scenetree.findObject('drive_subject'); "
            "subject:setPositionRotation(0.6, 0.0, 0.35, 0, 0, 0, 1); "
            "return jsonEncode({ok = true})"
        )

        # ---- Spray-effects toggle: default off while the wash runs, all 22
        # on after one press, all off again after the next. ----
        def press_effects_toggle() -> None:
            lua(
                f"local ext = extensions['{EXTENSION_NAME}']; "
                "local prop = scenetree.findObject('wash_prop'); "
                "ext.pressPanelButtonByVehicle(prop:getID(), 'btn_effects'); "
                "return jsonEncode({ok = true})"
            )

        washing = False
        deadline = time.time() + SERVICE_TIMEOUT_SECONDS
        while time.time() < deadline:
            step(0.5)
            snapshot = wash_state()
            if snapshot.get("repair_pending_count", 0) == 0 and snapshot.get("wash_active"):
                washing = True
                break
        assert washing, {"detail": "wash never serviced the parked car", "state": wash_state()}
        snapshot = wash_state()
        assert snapshot.get("effect_active_count") == 0, {
            "detail": "spray effects ran without the toggle (default must be OFF)",
            "state": snapshot,
        }
        press_effects_toggle()
        step(1.0)
        snapshot = wash_state()
        assert snapshot.get("effect_active_count") == 22, {
            "detail": "toggle ON did not activate the wash emitters",
            "state": snapshot,
        }
        assert snapshot.get("control_panel", {}).get("effects_enabled") is True, snapshot
        press_effects_toggle()
        step(1.0)
        snapshot = wash_state()
        assert snapshot.get("effect_active_count") == 0, {
            "detail": "toggle OFF did not deactivate the wash emitters",
            "state": snapshot,
        }
        assert snapshot.get("control_panel", {}).get("effects_enabled") is False, snapshot

        creep_to_rear_zone()
        assert wait_for_phase("countdown", SERVICE_TIMEOUT_SECONDS), {
            "detail": "countdown never started for a parked car",
            "state": wash_state(),
        }
        mid_snapshot = wash_state()
        assert mid_snapshot.get("effect_active_count") == 0, {
            "detail": "spray effects re-armed themselves during the countdown",
            "state": mid_snapshot,
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
