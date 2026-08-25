"""Headless state-machine gates for The Giant Fan.

These run the REAL shipped Lua - the generated GE runtime's behaviour chunk
and the built vehicle controller - under lupa against stubbed engine globals.
Cheap, and they see mechanics no static gate can: that the dial really steps
0 - 3 - 2 - 1, that the rotor really converges on its authored tip speeds
against its own aerodynamic drag, that OFF really takes ~25 s rather than
stopping like it hit a wall, and that the stop pad's dwell gate cannot be
tripped by a car crossing the bay at speed.

The pack's precedent is tests/test_spin_launch_sequence.py.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_KEY = "giant_fan"


def load_spec():
    if str(PACK_ROOT) not in sys.path:
        sys.path.insert(0, str(PACK_ROOT))
    loader = importlib.util.spec_from_file_location(
        "giant_fan_seq_spec", PACK_ROOT / MOD_KEY / "spec.py"
    )
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


S = load_spec()


def controller_source() -> str:
    """The SHIPPED controller, not the spec's template."""

    path = (
        PACK_ROOT
        / MOD_KEY
        / "mod"
        / "vehicles"
        / S.MOD_ID
        / "lua"
        / "controller"
        / "giantFan.lua"
    )
    if not path.is_file():
        pytest.skip("giant_fan is not built; run build.py giant_fan prop")
    return path.read_text(encoding="utf-8")


def new_controller(brake_torque: float | None = None):
    """Load the shipped controller against a stubbed vehicle VM."""

    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        f"""
        nop = function() end
        electrics = {{values = {{}}}}
        MOTOR = {{maxAV = {S.MOTOR_MAX_AV}, outputAV1 = 0.0,
                  setIgnition = function() end, sendTorqueData = function() end}}
        ROT = {{name = "fan_rotor", wheelDir = -1,
                brakeTorque = {brake_torque if brake_torque else S.BRAKE_TORQUE},
                desiredBrakingTorque = 0}}
        powertrain = {{getDevice = function() return MOTOR end}}
        wheels = {{wheelRotatorCount = 1, wheelRotators = {{[0] = ROT}}}}
        playerInfo = {{firstPlayerSeated = true}}
        function _throttle() return electrics.values.throttle or 0.0 end
        function _brake() return ROT.desiredBrakingTorque or 0.0 end
        function _sweep() return electrics.values.fanSweep or 0.0 end
        function _tilt() return electrics.values.fanTilt or 0.0 end
        function _setav(v) MOTOR.outputAV1 = v end
        """
    )
    module = lua.eval("function(src) return load(src, 'giantFan') end")(
        controller_source()
    )
    assert module, "the shipped controller does not compile"
    controller = module()
    controller.init(lua.table())
    return lua, controller


# ---------------------------------------------------------------------------
# A physical model of the rotor, so the controller is tested against the
# machine it actually drives rather than against a free-spinning shaft.
# ---------------------------------------------------------------------------
CURVE = S.JBEAM_SECTIONS["motor"]["torque"][1:]


def motor_torque(rpm: float) -> float:
    rpm = min(max(rpm, CURVE[0][0]), CURVE[-1][0])
    for (r0, t0), (r1, t1) in zip(CURVE, CURVE[1:]):
        if r0 <= rpm <= r1:
            f = 0.0 if r1 == r0 else (rpm - r0) / (r1 - r0)
            return t0 + f * (t1 - t0)
    return CURVE[-1][1]


def aero_torque(omega: float, segments: int = 48) -> float:
    """The blades' own drag, at the dragCoef the jbeam actually ships."""

    rho, cd = 1.225, 0.07
    total = 0.0
    for i in range(segments):
        s = (i + 0.5) / segments
        radius = S.HUB_R + s * S.BLADE_SPAN
        dr = S.BLADE_SPAN / segments
        chord_eff = S.blade_chord(s) * math.sin(S.blade_pitch(s))
        total += 0.5 * rho * cd * (omega * radius) ** 2 * chord_eff * dr * radius
    return S.BLADE_COUNT * total


WHEEL_DIR = -1.0  # the rotators row the jbeam really ships


def motor_output_av(omega: float) -> float:
    """`motor.outputAV1` for a rotor turning forwards at ``omega``.

    The engine's own chain, and it is applied ONCE, in shaft.lua:

        wheel.propulsionTorque = outputTorque * device.wheelDirection
        device.outputAV1       = wheel.angularVelocity * device.wheelDirection
        device.inputAV         = device.outputAV1 * device.gearRatio
        motor.outputAV1        = device.inputAV

    With wheelDir -1 a positive motor torque drives the wheel's RAW angular
    velocity negative, so the raw value is -omega and what the motor reports is
    -omega * -1 * gearRatio: POSITIVE. This harness used to feed the raw value
    straight in, which cancelled the controller's own second wheelDir and hid a
    sign-inverted speed loop that ran flat out at every dial setting.
    """

    return (-omega) * WHEEL_DIR * S.GEAR_RATIO


def spin(lua, controller, seconds: float, omega: float = 0.0, dt: float = 1 / 60.0):
    """Integrate the rotor while the controller drives it."""

    g = lua.globals()
    history = []
    for _ in range(int(seconds / dt)):
        g._setav(motor_output_av(omega))
        controller.updateGFX(dt)
        controller.updateWheelsIntermediate(dt)
        rpm = abs(omega) * S.GEAR_RATIO * S.AV_TO_RPM
        drive = motor_torque(rpm) * g._throttle() * S.GEAR_RATIO
        brake = g._brake() if omega > 1e-6 else 0.0
        net = drive - aero_torque(omega) - S.SHAFT_FRICTION - brake
        omega = max(0.0, omega + net / S.ROTOR_INERTIA * dt)
        history.append(omega * S.TIP_R)
    return omega, history


# ---------------------------------------------------------------------------
# The dial.
# ---------------------------------------------------------------------------
def test_the_first_click_from_off_is_full_power() -> None:
    """The real Lasko detent order, and the best joke on the machine."""

    lua, controller = new_controller()
    assert controller.status().dial == 0
    controller.stepDial()
    assert controller.status().dial == 3
    assert controller.status().tip_target == pytest.approx(S.TIP_MPS[3])


def test_the_dial_cycles_0_3_2_1_and_wraps() -> None:
    lua, controller = new_controller()
    seen = []
    for _ in range(len(S.DIAL_ORDER) * 2):
        controller.stepDial()
        seen.append(controller.status().dial)
    assert seen == [3, 2, 1, 0, 3, 2, 1, 0]


def test_off_goes_straight_to_zero_from_any_setting() -> None:
    lua, controller = new_controller()
    controller.stepDial()
    controller.dialOff()
    assert controller.status().dial == 0


@pytest.mark.parametrize("clicks,setting", [(1, 3), (2, 2), (3, 1)])
def test_every_setting_reaches_the_tip_speed_printed_on_it(
    clicks: int, setting: int
) -> None:
    """The pack's discipline: the number on the machine is the number it does.

    Run against the rotor's REAL inertia and its own blade drag, not a free
    shaft - a fan's load is its blades.
    """

    lua, controller = new_controller()
    for _ in range(clicks):
        controller.stepDial()
    omega, _ = spin(lua, controller, 90.0)
    assert omega * S.TIP_R == pytest.approx(S.TIP_MPS[setting], rel=0.02)


def test_the_top_setting_takes_long_enough_to_be_a_beat() -> None:
    """A 33 t rotor must not snap to speed; the pause IS the anticipation."""

    lua, controller = new_controller()
    controller.stepDial()  # -> 3
    _, history = spin(lua, controller, 40.0)
    target = S.TIP_MPS[3]
    reached = next(i for i, v in enumerate(history) if v >= 0.9 * target) / 60.0
    assert 3.0 < reached < 12.0, reached


def test_off_winds_the_rotor_down_rather_than_stopping_it_dead() -> None:
    """Stock's spinner controller slams a full brake on every down-step.

    On 2.6e6 kg.m^2 that reads as the rotor hitting a wall. BRAKE_TORQUE was
    solved for COASTDOWN_S against this exact model.
    """

    lua, controller = new_controller()
    controller.stepDial()
    omega, _ = spin(lua, controller, 40.0)
    controller.dialOff()
    dt, elapsed = 1 / 60.0, 0.0
    g = lua.globals()
    while omega * S.TIP_R > 0.5 and elapsed < 200.0:
        g._setav(motor_output_av(omega))
        controller.updateGFX(dt)
        controller.updateWheelsIntermediate(dt)
        net = -aero_torque(omega) - S.SHAFT_FRICTION - g._brake()
        omega = max(0.0, omega + net / S.ROTOR_INERTIA * dt)
        elapsed += dt
    assert elapsed == pytest.approx(S.COASTDOWN_S, rel=0.20), elapsed
    assert elapsed > 8.0, "a 33 t rotor stopping faster than this is a wall"


# ---------------------------------------------------------------------------
# Sweep and tilt.
# ---------------------------------------------------------------------------
def test_the_sweep_arms_before_it_moves() -> None:
    """The dog clutch engaging: push the plunger and NOTHING happens yet."""

    lua, controller = new_controller()
    g = lua.globals()
    controller.toggleSweep()
    assert controller.status().sweeping is True
    dt = 1 / 60.0
    for _ in range(int((S.SWEEP_ARM_S - 0.1) / dt)):
        controller.updateGFX(dt)
    assert g._sweep() == pytest.approx(0.0, abs=1e-9), "the head moved too early"
    for _ in range(int(1.2 / dt)):
        controller.updateGFX(dt)
    assert abs(g._sweep()) > 0.05, "the head never started sweeping"


def test_the_sweep_is_bounded_and_returns_to_centre_when_switched_off() -> None:
    lua, controller = new_controller()
    g = lua.globals()
    controller.toggleSweep()
    dt = 1 / 60.0
    extremes = []
    for _ in range(int((S.SWEEP_ARM_S + 2 * S.SWEEP_PERIOD_S) / dt)):
        controller.updateGFX(dt)
        extremes.append(g._sweep())
    assert max(extremes) == pytest.approx(1.0, abs=0.02)
    assert min(extremes) == pytest.approx(-1.0, abs=0.02)
    controller.toggleSweep()
    controller.updateGFX(dt)
    assert g._sweep() == pytest.approx(0.0, abs=1e-9), "the head parked off-centre"


def test_tilt_rungs_clamp_at_both_ends_and_drive_the_hydro() -> None:
    lua, controller = new_controller()
    g = lua.globals()
    controller.updateGFX(1 / 60.0)
    assert g._tilt() == pytest.approx(S.TILT_INPUT[0], abs=1e-9)
    for _ in range(20):
        controller.stepTilt(1)
    controller.updateGFX(1 / 60.0)
    assert controller.status().tilt_rung == len(S.TILT_CLEAR_M)
    assert g._tilt() == pytest.approx(S.TILT_INPUT[-1], abs=1e-9)
    for _ in range(20):
        controller.stepTilt(-1)
    controller.updateGFX(1 / 60.0)
    assert controller.status().tilt_rung == 1
    assert g._tilt() == pytest.approx(S.TILT_INPUT[0], abs=1e-9), (
        "the lowest rung must be reachable again - this is the autoCenterRate trap"
    )


def test_every_tilt_rung_reports_its_own_strike_height() -> None:
    lua, controller = new_controller()
    for rung in range(1, len(S.TILT_CLEAR_M) + 1):
        controller.setTiltRung(rung)
        assert controller.status().tilt_clear == pytest.approx(
            S.TILT_CLEAR_M[rung - 1]
        )


# ---------------------------------------------------------------------------
# Reset.
# ---------------------------------------------------------------------------
def test_reset_returns_the_machine_to_its_authored_pose() -> None:
    lua, controller = new_controller()
    g = lua.globals()
    controller.stepDial()
    controller.toggleSweep()
    controller.stepTilt(3)
    spin(lua, controller, 20.0)
    controller.reset()
    controller.updateGFX(1 / 60.0)
    status = controller.status()
    assert status.dial == 0
    assert status.sweeping is False
    assert status.tilt_rung == 1
    assert g._sweep() == pytest.approx(0.0, abs=1e-9)
    assert g._tilt() == pytest.approx(S.TILT_INPUT[0], abs=1e-9)


# ---------------------------------------------------------------------------
# The GE behaviour chunk.
# ---------------------------------------------------------------------------
def runtime_source() -> str:
    path = (
        PACK_ROOT
        / MOD_KEY
        / "mod"
        / "lua"
        / "ge"
        / "extensions"
        / S.MOD_ID
        / "runtime.lua"
    )
    if not path.is_file():
        pytest.skip("giant_fan is not built")
    return path.read_text(encoding="utf-8")


def test_the_generated_runtime_compiles() -> None:
    lua = lupa.LuaRuntime()
    chunk = lua.eval("function(src) return load(src, 'runtime') end")(runtime_source())
    assert chunk, "the shipped GE runtime does not compile"


def test_the_runtime_reaches_the_controller_per_vehicle() -> None:
    """Two fans on one map must not act as a single machine."""

    source = runtime_source()
    assert "queueLuaCommand" in source
    assert "getController('giantFan')" in source
    assert "onGameplayEvent" not in source


def test_the_wind_never_replaces_a_cluster_velocity() -> None:
    """A SET is a teleport. The pack's law is ADD, and only ADD."""

    source = runtime_source()
    assert "addSubjectVelocity" in source
    # scale 0 is the REPLACE form; the fan must never use it.
    assert "launchSubject" not in S.LUA_BEHAVIOR
    assert "teleportSubject" not in S.LUA_BEHAVIOR


def test_the_stop_pad_needs_a_dwell_not_a_crossing() -> None:
    """A crossing can never trip the pad, at ANY speed and ANY box length.

    Making the box longer would not do this: a fast car simply spends longer
    inside a longer box. What does it is the SPEED gate - the dwell only
    accumulates while the car is also slower than STOP_PAD_SPEED_MAX, and the
    accumulator is reset the moment it is not. This test pins that reset,
    because a dwell that merely accumulated would be satisfiable by driving
    slowly through, which is not the same verb as parking.
    """

    assert S.STOP_PAD_DWELL_S >= 0.3
    assert S.STOP_PAD_SPEED_MAX <= 1.5

    source = runtime_source()
    # The behaviour's update, not the TRIGGER_SPECS table that also mentions
    # the pad by name near the top of the file.
    start = source.index("function behavior.update")
    body = source[start : source.index("function behavior.onPanelButton", start)]
    assert "stop_pad_speed_max" in body, "the pad has no speed gate at all"
    # Two resets: one when the car is inside but moving, one when it leaves.
    assert body.count("padDwell = 0.0") >= 2, body.count("padDwell = 0.0")
    # And the dwell is compared against the tunable, not a literal.
    assert "B.stop_pad_dwell" in body


# ---------------------------------------------------------------------------
# The powertrain graph.
#
# Found by the artifact critic panel, 2026-08-25, after every static gate and
# every headless gate passed: the built jbeam declared the SHAFT and the
# motor's PARAMETERS but never the motor DEVICE, so `powertrain.getDevice`
# returned nil, the controller's `motor` stayed nil, and `updateGFX`
# early-returned every frame. The fan never turned - and nothing failed.
#
# Stock hides this because it splits the machine across two parts:
# `large_motor.jbeam` contributes the `electricMotor` row and
# `large_spinner_quad.jbeam` contributes the `shaft` row, and JBeam merges
# them. A single-part prop has to declare BOTH.
# ---------------------------------------------------------------------------
def test_every_powertrain_input_names_a_device_that_exists() -> None:
    import json

    path = (
        PACK_ROOT / MOD_KEY / "mod" / "vehicles" / S.MOD_ID / f"{S.MOD_ID}.jbeam"
    )
    if not path.is_file():
        pytest.skip("giant_fan is not built")
    part = json.loads(path.read_text(encoding="utf-8"))[S.MOD_ID]
    rows = part["powertrain"]
    header = rows[0]
    name_at, input_at, type_at = (
        header.index("name"),
        header.index("inputName"),
        header.index("type"),
    )
    devices = {row[name_at]: row[type_at] for row in rows[1:]}
    for row in rows[1:]:
        source = row[input_at]
        if source in ("", None):
            continue  # a root device: it is driven by nothing
        assert source in devices, (
            f"{row[name_at]} is driven by '{source}', which no powertrain row "
            f"declares. Declared: {sorted(devices)}"
        )
    # And the machine must actually have a prime mover.
    assert any(t == "electricMotor" for t in devices.values()), devices


def test_the_motor_block_belongs_to_a_declared_device() -> None:
    """A `motor` section with no `motor` device is inert configuration."""

    import json

    path = (
        PACK_ROOT / MOD_KEY / "mod" / "vehicles" / S.MOD_ID / f"{S.MOD_ID}.jbeam"
    )
    if not path.is_file():
        pytest.skip("giant_fan is not built")
    part = json.loads(path.read_text(encoding="utf-8"))[S.MOD_ID]
    rows = part["powertrain"]
    names = {row[rows[0].index("name")] for row in rows[1:]}
    assert "motor" in names, (
        "the jbeam carries a `motor` parameter block, but no powertrain device "
        "is named `motor`, so the block configures nothing"
    )
