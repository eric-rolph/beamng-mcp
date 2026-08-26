"""Functional live gauntlet for the Giant Props pack.

One owned BeamNG session, all ten pack ZIPs installed into the sentinel
profile, each contraption spawned at its own station on smallgrid and driven
through its *intended interaction* with a subject vehicle:

- flyswatter: arm via the lane, camp the kill zone, get swatted sideways,
- bouncy castle: drop onto the soft floor, verify it holds and rebounds,
- vacuum: get dragged toward the nozzle, gulped, and spat out the exhaust,
- dino egg: wobble then hatch-launch,
- seesaw: park three counted seconds, weight drop, fling,
- washer: door close, spin-up tumble, mid-spin eject,
- whale: inhale then ride the geyser column and complete the ride,
- boot: alert, wind-up, punt downrange,
- pendulum gauntlet: the soft deck holds the car and a swinging wrecking
  ball physically knocks it.

Each scenario is isolated with try/except so one misbehaving contraption
still yields results for the rest; the test fails at the end with the full
per-mod report. The Giant Toaster has its own dedicated release-style gate
in ``test_giant_props_live.py`` and is installed here only to prove pack
coexistence.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import uuid
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from statistics import median
from typing import Any

import pytest
from beamngpy import BeamNGpy, Scenario, Vehicle

from tests.live_support import (
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    require_confined_profile_target,
    reserve_loopback_ports,
)

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
SUBJECT_NAME = "giant_props_gauntlet_subject"
CATAPULT_SUBJECT_NAME = "giant_props_catapult_subject"
CATAPULT_SUBJECT_MODEL = os.getenv("GIANT_PROPS_CATAPULT_MODEL", "bastion")
CATAPULT_SUBJECT_CONFIG = os.getenv("GIANT_PROPS_CATAPULT_CONFIG", "vehicles/bastion/base_v6_A.pc")
# World-space projection of the plank-local -10.8 m target at the authored
# 30-degree rest angle. Keeping the test car on the painted X also validates
# that static trigger coordinates and moving-plank coordinates are not mixed.
CATAPULT_PARK_WORLD_Y = -9.440574360871938
LIVE_TEST_TAG = "GIANT_PROPS_GAUNTLET"
STATION_SPACING = 250.0
STEPS_PER_SECOND = 60

ALL_MOD_KEYS = (
    "giant_toaster",
    "monster_flyswatter",
    "bouncy_castle",
    "vacuum_of_doom",
    "dino_egg_hatcher",
    "catapult_seesaw",
    "spin_cycle_washer",
    "whale_geyser",
    "boot_of_doom",
    "pendulum_gauntlet",
)
TESTED_MOD_KEYS = ALL_MOD_KEYS[1:]


def mod_id_for(key: str) -> str:
    return f"ericrolph_{key}"


def extension_for(mod_id: str) -> str:
    return f"{mod_id}/runtime".replace("_", "__").replace("/", "_")


def log_tag_for(mod_id: str) -> str:
    return mod_id.upper() + "_RUNTIME"


def zip_basename_for(key: str) -> str:
    return f"{key}_ericrolph.zip"


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the Giant Props functional gauntlet"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the functional gauntlet requires a sentinel-isolated profile")
    return home, user, binary


class Gauntlet:
    """One live session shared by every contraption scenario."""

    def __init__(self, bng: BeamNGpy, subject: Vehicle, surface_z: float) -> None:
        self.bng = bng
        self.subject = subject
        self.subject_name = SUBJECT_NAME
        self.surface_z = surface_z
        self.prop_names: dict[str, str] = {}
        self.prop_origins: dict[str, tuple[float, float, float]] = {}

    def lua(self, command: str) -> dict[str, Any]:
        payload = self.bng.control.queue_lua_command(command, response=True)
        decoded = json.loads(payload)
        assert isinstance(decoded, dict), decoded
        return decoded

    def step(self, seconds: float) -> None:
        steps = max(1, int(seconds * STEPS_PER_SECOND))
        while steps > 0:
            chunk = min(steps, 30)
            self.bng.control.step(chunk, wait=True)
            steps -= chunk

    def runtime_state(self, key: str) -> dict[str, Any]:
        mod_id = mod_id_for(key)
        prop_name = self.prop_names[key]
        return self.lua(
            f"local extension = extensions[{extension_for(mod_id)!r}]; "
            f"local prop = scenetree.findObject({prop_name!r}); "
            "if not extension then return jsonEncode({loaded = false}) end; "
            "if not prop then return jsonEncode({loaded = true, registered = false}) end; "
            "local state = extension.getSystemState(prop:getID()); "
            "state.loaded = true; "
            "return jsonEncode(state)",
        )

    def subject_probe(self) -> dict[str, Any]:
        probe = self.lua(
            f"local subject = scenetree.findObject({self.subject_name!r}); "
            "if not subject then return jsonEncode({ok = false}) end; "
            "local position = subject:getPosition(); "
            "local velocity = subject:getVelocity(); "
            "return jsonEncode({ok = true, x = position.x, y = position.y, z = position.z, "
            "vx = velocity.x, vy = velocity.y, vz = velocity.z, speed = velocity:length()})"
        )
        assert probe.get("ok") is True, probe
        return probe

    def use_subject(self, subject: Vehicle, name: str) -> None:
        self.subject = subject
        self.subject_name = name

    def spawn_prop(self, key: str, station_index: int) -> None:
        mod_id = mod_id_for(key)
        prop_name = f"{mod_id}_gauntlet_prop"
        station_x = station_index * STATION_SPACING
        surface = self.lua(
            f"local rayStart = vec3({station_x}, 0, 200); "
            "local rayDistance = castRayStatic(rayStart, vec3(0, 0, -1), 300); "
            "return jsonEncode({distance = rayDistance, surface_z = 200 - rayDistance})"
        )
        assert 0.0 < float(surface["distance"]) < 300.0, surface
        surface_z = float(surface["surface_z"])
        prop = Vehicle(prop_name, mod_id)
        spawned = self.bng.vehicles.spawn(
            prop, (station_x, 0.0, surface_z), (0, 0, 0, 1), False, True
        )
        assert spawned is True, f"prop spawn failed: {mod_id}"
        self.prop_names[key] = prop_name
        state: dict[str, Any] = {}
        for _ in range(24):
            self.step(0.25)
            state = self.runtime_state(key)
            if state.get("registered"):
                break
        assert state.get("registered") is True, {"mod": mod_id, "state": state}
        origin = state["origin"]
        self.prop_origins[key] = (float(origin[0]), float(origin[1]), float(origin[2]))

    def world_point(
        self, key: str, authored_x: float, authored_y: float, authored_z: float
    ) -> tuple[float, float, float]:
        """Authored prop frame -> world (identity spawn = 180-degree Z flip)."""

        origin = self.prop_origins[key]
        return (
            origin[0] - authored_x,
            origin[1] - authored_y,
            origin[2] + authored_z,
        )

    def rel_authored(self, key: str, probe: dict[str, Any]) -> tuple[float, float, float]:
        """World probe -> authored prop frame coordinates."""

        origin = self.prop_origins[key]
        return (
            -(float(probe["x"]) - origin[0]),
            -(float(probe["y"]) - origin[1]),
            float(probe["z"]) - origin[2],
        )

    def place_subject(
        self,
        key: str,
        authored_x: float,
        authored_y: float,
        authored_z: float,
        *,
        parkingbrake: float,
        settle_seconds: float = 0.5,
        rot_quat: tuple[float, float, float, float] = (0, 0, 0, 1),
    ) -> None:
        position = self.world_point(key, authored_x, authored_y, authored_z)
        self.subject.teleport(pos=position, rot_quat=rot_quat, reset=True)
        self.step(0.2)
        self.subject.control(parkingbrake=parkingbrake, throttle=0.0, brake=0.0)
        self.step(settle_seconds)

    def wait_for(
        self,
        predicate: Callable[[], bool],
        *,
        timeout_seconds: float,
        poll_seconds: float = 0.25,
        detail: str = "",
    ) -> bool:
        elapsed = 0.0
        while elapsed < timeout_seconds:
            self.step(poll_seconds)
            elapsed += poll_seconds
            if predicate():
                return True
        return False


def scenario_monster_flyswatter(g: Gauntlet) -> dict[str, Any]:
    key = "monster_flyswatter"
    # Arm the swatter from the lane, then camp the slam point.
    g.place_subject(key, 0.0, -7.0, 0.8, parkingbrake=1.0, settle_seconds=0.3)
    g.step(0.2)
    g.place_subject(key, -0.7, 0.0, 0.8, parkingbrake=1.0, settle_seconds=0.1)
    start = g.subject_probe()
    swatted = g.wait_for(
        lambda: _horizontal_distance(g.subject_probe(), start) > 8.0,
        timeout_seconds=8.0,
    )
    assert swatted, {"detail": "subject was not displaced by the swat", "start": start}
    return {"displacement_m": _horizontal_distance(g.subject_probe(), start)}


def scenario_bouncy_castle(g: Gauntlet) -> dict[str, Any]:
    key = "bouncy_castle"
    origin_z = g.prop_origins[key][2]
    g.place_subject(key, 0.0, 0.0, 9.0, parkingbrake=0.0, settle_seconds=0.0)
    samples: list[float] = []
    for _ in range(32):
        g.step(0.2)
        samples.append(float(g.subject_probe()["z"]) - origin_z)
    minimum = min(samples)
    trough_index = samples.index(minimum)
    rebound = max(samples[trough_index:]) - minimum
    resting = samples[-1]
    assert minimum > 0.05, {"detail": "subject clipped through the soft floor", "min": minimum}
    assert rebound > 0.5, {"detail": "no rebound measured", "samples": samples}
    # Random super-jumps (1-5 s cadence) may punt the subject clean out of
    # the castle mid-test: a high peak proves the jump system instead.
    peak = max(samples)
    assert resting > 0.7 or peak > 4.0, {
        "detail": "subject neither rested on the floor nor got super-jumped",
        "resting": resting,
        "peak": peak,
    }
    return {"min_z": minimum, "rebound_m": rebound, "resting_z": resting, "peak_z": peak}


def scenario_vacuum_of_doom(g: Gauntlet) -> dict[str, Any]:
    key = "vacuum_of_doom"
    g.place_subject(key, 0.0, -14.0, 0.6, parkingbrake=0.0, settle_seconds=0.3)
    start_rel = g.rel_authored(key, g.subject_probe())
    pulled = g.wait_for(
        lambda: g.rel_authored(key, g.subject_probe())[1] > start_rel[1] + 4.0,
        timeout_seconds=10.0,
    )
    assert pulled, {
        "detail": "subject was not pulled toward the nozzle",
        "rel": g.rel_authored(key, g.subject_probe()),
    }
    ejected = (
        g.wait_for(
            lambda: (
                g.rel_authored(key, g.subject_probe())[1] > 8.0
                and g.rel_authored(key, g.subject_probe())[2] > 2.0
            ),
            timeout_seconds=25.0,
        )
        or g.rel_authored(key, g.subject_probe())[1] > 8.0
    )
    assert ejected, {
        "detail": "subject never exited via the exhaust side",
        "rel": g.rel_authored(key, g.subject_probe()),
    }
    return {"final_rel": g.rel_authored(key, g.subject_probe())}


def scenario_dino_egg_hatcher(g: Gauntlet) -> dict[str, Any]:
    key = "dino_egg_hatcher"
    g.place_subject(key, 0.0, 0.3, 1.2, parkingbrake=1.0, settle_seconds=0.4)
    baseline = float(g.subject_probe()["z"])
    launched = g.wait_for(
        lambda: float(g.subject_probe()["z"]) - baseline > 5.0,
        timeout_seconds=8.0,
    )
    assert launched, {"detail": "egg never hatched/launched", "baseline": baseline}
    return {"height_gain_m": float(g.subject_probe()["z"]) - baseline}


def scenario_catapult_seesaw(g: Gauntlet) -> dict[str, Any]:
    key = "catapult_seesaw"
    # Keep the configured full-size car's parking brake engaged through the
    # countdown, then release it when the physical latch opens just as a player
    # would. No velocity, teleport, or other motion is applied after the
    # initial fixture placement.
    g.place_subject(
        key,
        0.0,
        CATAPULT_PARK_WORLD_Y,
        2.4,
        parkingbrake=1.0,
        settle_seconds=0.2,
        # Face downhill with the front axle near the launch end and the rear
        # over the throwing arm. This is the intended catapult loading: the
        # rear/midsection strike pitches the car forward off the board.
        rot_quat=(
            0.0,
            math.sin(math.radians(15.0)),
            math.cos(math.radians(15.0)),
            0.0,
        ),
    )
    subject_start = g.subject_probe()
    initial_state = g.runtime_state(key)
    initial_status = initial_state.get("behavior_status") or {}
    initial_angle = float(initial_status.get("plank_angle_deg", 30.0))
    pre_release_trace: list[dict[str, float]] = []
    released_trace: list[dict[str, Any]] = []
    post_impact_drops: list[float] = []
    peak_rise = 0.0
    peak_forward = 0.0
    first_flight_peak_forward = 0.0
    first_landing_downrange: float | None = None
    first_landing_elapsed: float | None = None
    first_landing_detection_reason: str | None = None
    peak_speed = 0.0
    peak_velocity = (0.0, 0.0, 0.0)
    maximum_drop = 0.0
    minimum_released_angle = initial_angle
    max_weight_down_speed = 0.0
    released_min_rod_length: float | None = None
    released_max_compression = 0.0
    max_park_timer = 0.0
    max_idle_subject_speed = 0.0
    final_relative = g.rel_authored(key, subject_start)
    observed_fling = False
    released = False
    parking_brake_released = False
    impacted_at: float | None = None
    rising = False
    apex_reached = False
    descending_after_apex = False
    previous_released_vertical_velocity: float | None = None
    sample_seconds = 0.10
    # Use the runtime's countdown clock rather than harness wall/sim time.
    # The extension currently advances its park timer roughly three times per
    # 0.1 s harness sample, so an elapsed-time cut left only two steady samples.
    steady_state_start_park_timer_s = 1.0
    for sample_index in range(int(12.0 / sample_seconds)):
        g.step(sample_seconds)
        subject = g.subject_probe()
        state = g.runtime_state(key)
        status = state.get("behavior_status") or {}
        elapsed = (sample_index + 1) * sample_seconds
        phase = state.get("behavior_phase")
        if phase == "released" and not parking_brake_released:
            g.subject.control(parkingbrake=0.0, throttle=0.0, brake=0.0)
            parking_brake_released = True
        is_pre_release = not released and phase == "idle"
        max_park_timer = max(max_park_timer, float(status.get("park_timer_s") or 0.0))
        released = released or phase == "released"
        rise = float(subject["z"]) - float(subject_start["z"])
        relative = g.rel_authored(key, subject)
        final_relative = relative
        start_relative = g.rel_authored(key, subject_start)
        # The counterweight occupies +Y, so the car-end launch direction is
        # naturally away from the tower along authored -Y.
        forward = start_relative[1] - relative[1]
        peak_rise = max(peak_rise, rise)
        peak_forward = max(
            peak_forward,
            forward,
        )
        drop_value = status.get("weight_drop_m")
        angle_value = status.get("plank_angle_deg")
        if drop_value is not None:
            drop = float(drop_value)
            maximum_drop = max(maximum_drop, drop)
            if status.get("impacted") and impacted_at is None:
                impacted_at = elapsed
            if impacted_at is not None and elapsed - impacted_at <= 2.5 and phase == "released":
                post_impact_drops.append(drop)
        if angle_value is not None and phase == "released":
            minimum_released_angle = min(minimum_released_angle, float(angle_value))
        if is_pre_release and angle_value is not None and drop_value is not None:
            pre_release_trace.append(
                {
                    "time_s": round(elapsed, 3),
                    "angle_deg": float(angle_value),
                    "body_angle_deg": float(status.get("impact_body_angle_deg") or angle_value),
                    "weight_drop_m": float(drop_value),
                    "subject_speed_mps": float(subject.get("speed") or 0.0),
                    "park_timer_s": float(status.get("park_timer_s") or 0.0),
                }
            )
        max_weight_down_speed = max(
            max_weight_down_speed, float(status.get("max_weight_down_mps") or 0.0)
        )
        accumulated_min_rod_length = status.get("impact_released_min_rod_length_m")
        if accumulated_min_rod_length is not None:
            observed_min_rod_length = float(accumulated_min_rod_length)
            released_min_rod_length = (
                observed_min_rod_length
                if released_min_rod_length is None
                else min(released_min_rod_length, observed_min_rod_length)
            )
        released_max_compression = max(
            released_max_compression,
            float(status.get("impact_released_max_compression_m") or 0.0),
        )
        observed_fling = observed_fling or bool(status.get("flung"))

        if released:
            # World X/Y are both reversed by the prop's identity spawn.  Report
            # lateral, physical downrange (-authored Y), and up components.
            velocity = (
                -float(subject["vx"]),
                float(subject["vy"]),
                float(subject["vz"]),
            )
            speed = math.sqrt(sum(component * component for component in velocity))
            rising = rising or velocity[2] > 0.5
            if rising and velocity[2] < 0.0:
                apex_reached = True
            if apex_reached and velocity[2] <= -0.5:
                descending_after_apex = True
            if not apex_reached and speed > peak_speed:
                peak_speed = speed
                peak_velocity = velocity

            # A ballistic COM keeps accelerating downward until an external
            # contact impulse arrests it. Detect the first such impulse only
            # after ascent and descent have both been observed, and only once
            # the car is back near its launch height. This rejects plank-contact
            # transients during launch and keeps post-landing rolling out of the
            # first-flight distance.
            landed_this_sample = False
            vertical_reversal = (
                previous_released_vertical_velocity is not None
                and previous_released_vertical_velocity <= -0.5
                and velocity[2] >= 0.25
            )
            sharp_vertical_arrest = (
                previous_released_vertical_velocity is not None
                and previous_released_vertical_velocity <= -1.0
                and velocity[2] - previous_released_vertical_velocity >= 2.0
            )
            if first_landing_downrange is None:
                first_flight_peak_forward = max(first_flight_peak_forward, forward)
                if (
                    descending_after_apex
                    and rise <= 1.5
                    and (vertical_reversal or sharp_vertical_arrest)
                ):
                    first_landing_downrange = forward
                    first_landing_elapsed = elapsed
                    first_landing_detection_reason = (
                        "vertical_reversal" if vertical_reversal else "sharp_vertical_arrest"
                    )
                    landed_this_sample = True

            if landed_this_sample:
                flight_phase = "first_landing"
            elif first_landing_downrange is not None:
                flight_phase = "post_landing"
            elif descending_after_apex:
                flight_phase = "descending"
            elif apex_reached:
                flight_phase = "apex"
            elif rising:
                flight_phase = "ascending"
            else:
                flight_phase = "awaiting_liftoff"
            if phase == "released":
                released_trace.append(
                    {
                        "time_s": round(elapsed, 3),
                        "plank_angle_deg": (
                            round(float(angle_value), 4) if angle_value is not None else None
                        ),
                        "weight_drop_m": (
                            round(float(drop_value), 4) if drop_value is not None else None
                        ),
                        "impact_min_rod_length_m": (
                            round(float(status["impact_min_rod_length_m"]), 4)
                            if status.get("impact_min_rod_length_m") is not None
                            else None
                        ),
                        "impact_max_compression_m": (
                            round(float(status["impact_max_compression_m"]), 4)
                            if status.get("impact_max_compression_m") is not None
                            else None
                        ),
                        "impact_released_min_rod_length_m": (
                            round(
                                float(status["impact_released_min_rod_length_m"]),
                                4,
                            )
                            if status.get("impact_released_min_rod_length_m") is not None
                            else None
                        ),
                        "impact_released_max_compression_m": round(
                            float(status.get("impact_released_max_compression_m") or 0.0),
                            4,
                        ),
                        "impact_receiver_phase_deg": (
                            round(float(status["impact_receiver_phase_deg"]), 4)
                            if status.get("impact_receiver_phase_deg") is not None
                            else None
                        ),
                        "impact_body_angle_deg": (
                            round(float(status["impact_body_angle_deg"]), 4)
                            if status.get("impact_body_angle_deg") is not None
                            else None
                        ),
                        "impact_receiver_phase_error_deg": (
                            round(float(status["impact_receiver_phase_error_deg"]), 4)
                            if status.get("impact_receiver_phase_error_deg") is not None
                            else None
                        ),
                        "car_speed_mps": round(speed, 4),
                        "car_velocity_authored_mps": [
                            round(component, 4) for component in velocity
                        ],
                        "car_displacement_authored_m": [
                            round(relative[0] - start_relative[0], 4),
                            round(forward, 4),
                            round(rise, 4),
                        ],
                        "car_flight_phase": flight_phase,
                        "car_previous_vertical_velocity_mps": (
                            round(previous_released_vertical_velocity, 4)
                            if previous_released_vertical_velocity is not None
                            else None
                        ),
                        "car_first_landing_this_sample": landed_this_sample,
                        "car_first_landing_downrange_m": (
                            round(first_landing_downrange, 4)
                            if first_landing_downrange is not None
                            else None
                        ),
                        "impacted": bool(status.get("impacted")),
                        "flung": bool(status.get("flung")),
                    }
                )
            previous_released_vertical_velocity = velocity[2]
        else:
            max_idle_subject_speed = max(max_idle_subject_speed, float(subject.get("speed") or 0.0))

    release_diagnostic = {
        "detail": "the three-second physical release never occurred",
        "max_park_timer_s": max_park_timer,
        "max_idle_subject_speed_mps": max_idle_subject_speed,
        "final_subject_relative": final_relative,
        "initial_plank_angle_deg": initial_angle,
        "minimum_released_plank_angle_deg": minimum_released_angle,
        "pre_release_trace": pre_release_trace,
    }
    if not released:
        print(json.dumps({"catapult_release_diagnostic": release_diagnostic}))
    assert released, release_diagnostic
    # Only the final uninterrupted arming interval describes the state that
    # actually led to release. Earlier samples may belong to a partial
    # countdown that was reset when fixture settling briefly exceeded the
    # parking-speed threshold.
    final_arming_start = 0
    park_timer_reset_indices: list[int] = []
    for index in range(1, len(pre_release_trace)):
        previous_timer = pre_release_trace[index - 1]["park_timer_s"]
        current_timer = pre_release_trace[index]["park_timer_s"]
        if current_timer < previous_timer - 1e-4:
            park_timer_reset_indices.append(index)
            final_arming_start = index
    final_arming_trace = pre_release_trace[final_arming_start:]
    initial_settling_trace = [
        sample
        for sample in final_arming_trace
        if sample["park_timer_s"] < steady_state_start_park_timer_s
    ]
    steady_state_trace = [
        sample
        for sample in final_arming_trace
        if sample["park_timer_s"] >= steady_state_start_park_timer_s
    ]
    full_angles = [sample["angle_deg"] for sample in pre_release_trace]
    settling_angles = [sample["angle_deg"] for sample in initial_settling_trace]
    steady_angles = [sample["angle_deg"] for sample in steady_state_trace]
    steady_body_angles = [sample["body_angle_deg"] for sample in steady_state_trace]
    steady_drops = [sample["weight_drop_m"] for sample in steady_state_trace]
    steady_subject_speeds = [sample["subject_speed_mps"] for sample in steady_state_trace]
    idle_weight_bob = max(steady_drops) - min(steady_drops) if steady_drops else math.inf
    idle_plank_jitter = max(steady_angles) - min(steady_angles) if steady_angles else math.inf
    release_baseline_angle = float(median(steady_angles[-10:])) if steady_angles else initial_angle
    full_angle_min = min(full_angles) if full_angles else math.inf
    full_angle_max = max(full_angles) if full_angles else -math.inf
    settling_angle_min = min(settling_angles) if settling_angles else math.inf
    settling_angle_max = max(settling_angles) if settling_angles else -math.inf
    steady_angle_min = min(steady_angles) if steady_angles else math.inf
    steady_angle_max = max(steady_angles) if steady_angles else -math.inf
    steady_body_angle_min = min(steady_body_angles) if steady_body_angles else math.inf
    steady_body_angle_max = max(steady_body_angles) if steady_body_angles else -math.inf
    steady_duration = (
        steady_state_trace[-1]["park_timer_s"] - steady_state_trace[0]["park_timer_s"]
        if len(steady_state_trace) >= 2
        else 0.0
    )
    steady_harness_duration = (
        steady_state_trace[-1]["time_s"] - steady_state_trace[0]["time_s"]
        if len(steady_state_trace) >= 2
        else 0.0
    )
    pre_release_diagnostic = {
        "steady_state_start_park_timer_s": steady_state_start_park_timer_s,
        "sample_period_s": sample_seconds,
        "sample_count": len(pre_release_trace),
        "park_timer_reset_count": len(park_timer_reset_indices),
        "park_timer_reset_indices": park_timer_reset_indices,
        "final_arming_start_index": final_arming_start,
        "discarded_pre_arming_sample_count": final_arming_start,
        "final_arming_sample_count": len(final_arming_trace),
        "final_arming_trace": final_arming_trace,
        "settling_sample_count": len(initial_settling_trace),
        "steady_sample_count": len(steady_state_trace),
        "steady_park_timer_duration_s": steady_duration,
        "steady_harness_duration_s": steady_harness_duration,
        "initial_angle_deg": initial_angle,
        "release_baseline_angle_deg": release_baseline_angle,
        "full_angle_min_deg": full_angle_min,
        "full_angle_max_deg": full_angle_max,
        "full_angle_range_deg": full_angle_max - full_angle_min,
        "settling_angle_min_deg": settling_angle_min,
        "settling_angle_max_deg": settling_angle_max,
        "settling_angle_range_deg": settling_angle_max - settling_angle_min,
        "steady_angle_min_deg": steady_angle_min,
        "steady_angle_max_deg": steady_angle_max,
        "steady_angle_range_deg": idle_plank_jitter,
        "steady_body_angle_min_deg": steady_body_angle_min,
        "steady_body_angle_max_deg": steady_body_angle_max,
        "steady_body_angle_range_deg": (steady_body_angle_max - steady_body_angle_min),
        "steady_weight_bob_m": idle_weight_bob,
        "steady_subject_peak_speed_mps": (
            max(steady_subject_speeds) if steady_subject_speeds else math.inf
        ),
        "trace": pre_release_trace,
    }
    rebound = 0.0
    if post_impact_drops:
        deepest_index = max(range(len(post_impact_drops)), key=post_impact_drops.__getitem__)
        rebound = max(post_impact_drops) - min(post_impact_drops[deepest_index:])
    horizontal_peak = math.hypot(peak_velocity[0], peak_velocity[1])
    elevation = math.degrees(math.atan2(peak_velocity[2], horizontal_peak))
    measurements = {
        "subject_model": CATAPULT_SUBJECT_MODEL,
        "subject_config": CATAPULT_SUBJECT_CONFIG,
        "weight_drop_m": maximum_drop,
        "weight_impact_speed_mps": max_weight_down_speed,
        "weight_rebound_m": rebound,
        "impact_released_min_rod_length_m": released_min_rod_length,
        "impact_released_max_compression_m": released_max_compression,
        "pre_release_weight_bob_m": idle_weight_bob,
        "pre_release_plank_jitter_deg": idle_plank_jitter,
        "plank_swing_deg": release_baseline_angle - minimum_released_angle,
        "car_peak_speed_mps": peak_speed,
        "car_peak_velocity_authored_mps": peak_velocity,
        "car_launch_elevation_deg": elevation,
        "car_apex_gain_m": peak_rise,
        "car_first_landing_downrange_m": first_landing_downrange,
        "car_first_landing_elapsed_s": first_landing_elapsed,
        "car_first_landing_detection_reason": first_landing_detection_reason,
        "car_first_flight_peak_downrange_m": first_flight_peak_forward,
        "car_max_downrange_m": peak_forward,
        "observed_physical_fling": observed_fling,
        "pre_release_diagnostic": pre_release_diagnostic,
        "released_trace": released_trace,
    }
    print(json.dumps({"catapult_measurements": measurements}, sort_keys=True))

    assert len(steady_state_trace) >= 6 and steady_duration >= 1.50, {
        "detail": "release occurred before a meaningful steady-state window was sampled",
        "pre_release_diagnostic": pre_release_diagnostic,
    }
    assert idle_weight_bob <= 0.15, {
        "detail": "latched counterweight visibly bobbed before release",
        "pre_release_weight_bob_m": idle_weight_bob,
        "pre_release_diagnostic": pre_release_diagnostic,
    }
    assert idle_plank_jitter <= 0.25, {
        "detail": "parked plank kept oscillating after initial fixture settling",
        "pre_release_plank_jitter_deg": idle_plank_jitter,
        "pre_release_diagnostic": pre_release_diagnostic,
    }
    assert maximum_drop >= 5.5, {
        "detail": "the physical counterweight did not free-fall",
        "maximum_drop_m": maximum_drop,
    }
    assert max_weight_down_speed >= 8.5, {
        "detail": "counterweight did not approach six-metre free-fall impact speed",
        "max_weight_down_mps": max_weight_down_speed,
    }
    assert release_baseline_angle - minimum_released_angle >= 35.0, {
        "detail": "the hinged plank did not rotate under counterweight impact",
        "release_baseline_angle_deg": release_baseline_angle,
        "minimum_released_angle_deg": minimum_released_angle,
    }
    assert observed_fling, {
        "detail": "runtime never observed a contact-driven fling",
        "peak_rise_m": peak_rise,
        "peak_forward_m": peak_forward,
    }
    assert peak_speed >= 8.0, {
        "detail": "physical plank contact did not accelerate the parked full-size car",
        "peak_speed_mps": peak_speed,
        "peak_velocity_authored_mps": peak_velocity,
    }
    assert 35.0 <= elevation <= 75.0, {
        "detail": "launch vector was not a useful catapult trajectory",
        "elevation_deg": elevation,
        "peak_velocity_authored_mps": peak_velocity,
    }
    assert peak_rise >= 7.0, {
        "detail": "physical plank contact did not produce the required apex",
        "peak_rise_m": peak_rise,
        "first_landing_downrange_m": first_landing_downrange,
        "max_downrange_m": peak_forward,
    }
    assert first_landing_downrange is not None, {
        "detail": "no first ballistic landing was detected after the apex",
        "apex_reached": apex_reached,
        "descending_after_apex": descending_after_apex,
        "first_flight_peak_downrange_m": first_flight_peak_forward,
        "max_downrange_m": peak_forward,
        "released_trace": released_trace,
    }
    assert first_landing_downrange >= 15.0, {
        "detail": "the first ballistic flight did not travel usefully downrange",
        "peak_rise_m": peak_rise,
        "first_landing_downrange_m": first_landing_downrange,
        "first_flight_peak_downrange_m": first_flight_peak_forward,
        "max_downrange_m": peak_forward,
    }
    assert rebound <= 1.5, {
        "detail": "counterweight rebounded excessively after impact",
        "counterweight_rebound_m": rebound,
        "post_impact_drops_m": post_impact_drops,
    }
    return measurements


def scenario_spin_cycle_washer(g: Gauntlet) -> dict[str, Any]:
    key = "spin_cycle_washer"
    g.place_subject(key, 0.0, -1.0, 1.2, parkingbrake=0.0, settle_seconds=0.4)
    # Door close (1 s) + spin-up (4 s) + spin (6 s): sample motion during the
    # tumble window, then wait for the eject.
    g.step(2.0)
    previous = g.subject_probe()
    max_speed = 0.0
    z_low, z_high = float(previous["z"]), float(previous["z"])
    for _ in range(int(8.0 / 0.25)):
        g.step(0.25)
        probe = g.subject_probe()
        distance = math.dist(
            (float(previous["x"]), float(previous["y"]), float(previous["z"])),
            (float(probe["x"]), float(probe["y"]), float(probe["z"])),
        )
        max_speed = max(max_speed, distance / 0.25)
        z_low = min(z_low, float(probe["z"]))
        z_high = max(z_high, float(probe["z"]))
        previous = probe
    tumbled = max_speed > 4.0 or (z_high - z_low) > 1.5
    ejected = g.wait_for(
        lambda: g.rel_authored(key, g.subject_probe())[1] < -8.0,
        timeout_seconds=10.0,
    )
    assert tumbled, {
        "detail": "no tumbling motion measured inside the drum",
        "max_speed": max_speed,
        "z_range": z_high - z_low,
    }
    assert ejected, {
        "detail": "subject was not hurled out the door",
        "rel": g.rel_authored(key, g.subject_probe()),
    }
    return {"tumble_peak_speed_mps": max_speed, "final_rel": g.rel_authored(key, g.subject_probe())}


def scenario_whale_geyser(g: Gauntlet) -> dict[str, Any]:
    key = "whale_geyser"
    g.place_subject(key, 0.0, 6.5, 6.4, parkingbrake=1.0, settle_seconds=0.5)
    pad_z = g.prop_origins[key][2] + 5.5
    # The blowhole is a ballistic blast now: expect serious altitude fast.
    blasted = g.wait_for(
        lambda: float(g.subject_probe()["z"]) > pad_z + 40.0,
        timeout_seconds=8.0,
    )
    assert blasted, {"detail": "geyser never blasted the subject", "pad_z": pad_z}
    peak = float(g.subject_probe()["z"]) - pad_z
    for _ in range(12):
        g.step(0.25)
        peak = max(peak, float(g.subject_probe()["z"]) - pad_z)
    return {"blast_height_over_pad_m": peak}


def scenario_boot_of_doom(g: Gauntlet) -> dict[str, Any]:
    key = "boot_of_doom"
    g.place_subject(key, 0.0, 1.2, 0.8, parkingbrake=1.0, settle_seconds=0.4)
    start_rel = g.rel_authored(key, g.subject_probe())
    punted = g.wait_for(
        lambda: g.rel_authored(key, g.subject_probe())[1] - start_rel[1] > 12.0,
        timeout_seconds=8.0,
    )
    assert punted, {
        "detail": "boot never punted the subject downrange",
        "rel": g.rel_authored(key, g.subject_probe()),
    }
    return {"downrange_rel": g.rel_authored(key, g.subject_probe())}


def scenario_pendulum_gauntlet(g: Gauntlet) -> dict[str, Any]:
    key = "pendulum_gauntlet"
    # Park mid-bridge in the second gantry's swing plane. Record the drop
    # point immediately: a wrecking ball may strike during the settle.
    # Deck integrity FIRST, midway between gantries so no ball can touch
    # the subject (the old early-knock bypass masked a collapsed-pendulum
    # session where the deck reading was ground level).
    g.place_subject(key, 0.0, -10.0, 4.2, parkingbrake=1.0, settle_seconds=1.0)
    origin_z = g.prop_origins[key][2]
    deck_probe = g.subject_probe()
    deck_height = float(deck_probe["z"]) - origin_z
    assert deck_height > 2.4, {
        "detail": "subject fell through the soft deck",
        "deck_height": deck_height,
    }
    # Now park in the second gantry's swing plane for the knock test.
    g.place_subject(key, 0.0, -5.0, 4.2, parkingbrake=1.0, settle_seconds=0.2)
    start = g.subject_probe()
    g.step(0.8)
    settled = g.subject_probe()
    early_knock = _horizontal_distance(settled, start) > 1.5
    struck = early_knock or g.wait_for(
        lambda: _horizontal_distance(g.subject_probe(), start) > 1.5,
        timeout_seconds=14.0,
    )
    assert struck, {
        "detail": "no wrecking ball ever displaced the parked subject",
        "deck_height": deck_height,
    }
    return {
        "deck_height_m": deck_height,
        "early_knock": early_knock,
        "knock_displacement_m": _horizontal_distance(g.subject_probe(), start),
    }


def _horizontal_distance(probe: dict[str, Any], start: dict[str, Any]) -> float:
    return math.hypot(
        float(probe["x"]) - float(start["x"]),
        float(probe["y"]) - float(start["y"]),
    )


SCENARIOS: dict[str, Callable[[Gauntlet], dict[str, Any]]] = {
    "monster_flyswatter": scenario_monster_flyswatter,
    "bouncy_castle": scenario_bouncy_castle,
    "vacuum_of_doom": scenario_vacuum_of_doom,
    "dino_egg_hatcher": scenario_dino_egg_hatcher,
    "catapult_seesaw": scenario_catapult_seesaw,
    "spin_cycle_washer": scenario_spin_cycle_washer,
    "whale_geyser": scenario_whale_geyser,
    "boot_of_doom": scenario_boot_of_doom,
    "pendulum_gauntlet": scenario_pendulum_gauntlet,
}

REQUIRED_EVENTS: dict[str, tuple[str, ...]] = {
    "monster_flyswatter": ("prop_registered", "swatter_armed", "subject_swatted"),
    "bouncy_castle": ("prop_registered", "bouncer_entered"),
    "vacuum_of_doom": (
        "prop_registered",
        "vacuum_spooling",
        "vacuum_active",
        "vacuum_gulp",
        "vacuum_eject",
    ),
    "dino_egg_hatcher": ("prop_registered", "egg_wobbling", "egg_hatched"),
    "catapult_seesaw": (
        "prop_registered",
        "weight_released",
        "counterweight_impact",
        "seesaw_flung",
    ),
    "spin_cycle_washer": (
        "prop_registered",
        "washer_loaded",
        "washer_spinup",
        "washer_ejected",
    ),
    "whale_geyser": ("prop_registered", "whale_inhaling", "whale_erupted"),
    "boot_of_doom": ("prop_registered", "boot_alerted", "boot_punted"),
    "pendulum_gauntlet": ("prop_registered",),
}


def _pack_log_records(log_path: Path, start_marker: str) -> tuple[dict[str, list], list[str]]:
    per_mod: dict[str, list] = {}
    issues: list[str] = []
    started = False
    payload = log_path.read_text(encoding="utf-8", errors="replace")
    tags = {log_tag_for(mod_id_for(key)): key for key in ALL_MOD_KEYS}
    for line in payload.splitlines():
        if start_marker in line:
            started = True
            continue
        if not started:
            continue
        matched_key = next((key for tag, key in tags.items() if tag in line), None)
        if matched_key is None:
            continue
        if "|E|" in line:
            issues.append(line)
        json_start = line.find("{")
        if json_start < 0:
            continue
        try:
            record = json.loads(line[json_start:])
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and isinstance(record.get("event"), str):
            per_mod.setdefault(matched_key, []).append(record)
    return per_mod, issues


@pytest.mark.beamng_live
def test_giant_props_functional_gauntlet(tmp_path: Path) -> None:
    home, user, binary = _configured_runtime()
    requested = os.getenv("GIANT_PROPS_LIVE_KEYS")
    selected_keys = TESTED_MOD_KEYS
    if requested:
        selected_keys = tuple(key.strip() for key in requested.split(",") if key.strip())
        unknown = sorted(set(selected_keys) - set(TESTED_MOD_KEYS))
        assert selected_keys and not unknown, {
            "detail": "invalid GIANT_PROPS_LIVE_KEYS selection",
            "unknown": unknown,
        }
    payloads: dict[str, bytes] = {}
    install_keys = ALL_MOD_KEYS if not requested else selected_keys
    for key in install_keys:
        dist_root = PACK_ROOT / key / "dist"
        archive = dist_root / zip_basename_for(key)
        lock = json.loads((dist_root / f"{mod_id_for(key)}.lock.json").read_text(encoding="utf-8"))
        payload = archive.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == lock["sha256"], key
        payloads[key] = payload

    suffix = uuid.uuid4().hex[:10]
    installed_zips = {
        key: require_confined_profile_target(
            user, Path("mods") / f"giant_props_gauntlet_{key}_{suffix}.zip"
        )
        for key in install_keys
    }
    scenario_name = f"giant_props_gauntlet_{suffix}"
    scenario_directory = require_confined_profile_target(
        user, Path("levels") / "smallgrid" / "scenarios" / scenario_name
    )
    log_path = user / "beamng.log"
    log_start = f"giant_props_gauntlet_start_{suffix}"
    results: dict[str, dict[str, Any]] = {}

    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(1))
        (tcom_port,) = reservation.ports
        mods_dir = user / "mods"
        if mods_dir.is_dir():
            conflicts = [
                str(path)
                for path in mods_dir.glob("*.zip")
                if any(mod_id_for(key) in path.name or key in path.name for key in install_keys)
            ]
            if conflicts:
                pytest.fail(f"competing pack archives in the isolated profile: {conflicts}")
        mods_dir.mkdir(parents=True, exist_ok=True)
        for key, target in installed_zips.items():
            with target.open("xb") as handle:
                handle.write(payloads[key])
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
        try:

            def watchdog() -> None:
                process = bng.process
                if process is not None and process.poll() is None:
                    process.terminate()

            timer = threading.Timer(1500.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)

            scenario = Scenario(
                "smallgrid",
                scenario_name,
                description="Disposable Giant Props functional gauntlet fixture",
            )
            subject = Vehicle(SUBJECT_NAME, "pigeon", license="GAUNTLT")
            catapult_subject = Vehicle(
                CATAPULT_SUBJECT_NAME,
                CATAPULT_SUBJECT_MODEL,
                license="10TON",
                part_config=CATAPULT_SUBJECT_CONFIG,
            )
            scenario.add_vehicle(
                subject, pos=(-60.0, -60.0, 20.0), rot_quat=(0, 0, 0, 1), cling=False
            )
            scenario.add_vehicle(
                catapult_subject,
                pos=(-70.0, -70.0, 20.0),
                rot_quat=(0, 0, 0, 1),
                cling=False,
            )
            scenario.make(bng)
            bng.control.pause()
            bng.scenario.load(scenario, precompile_shaders=False)
            bng.scenario.start()
            bng.settings.set_deterministic(steps_per_second=STEPS_PER_SECOND, speed_factor=1)
            bng.control.pause()
            bng.control.step(3, wait=True)

            gauntlet = Gauntlet(bng, subject, 0.0)
            marker = gauntlet.lua(
                f"log('I', {LIVE_TEST_TAG!r}, {log_start!r}); return jsonEncode({{ok = true}})"
            )
            assert marker == {"ok": True}

            for index, key in enumerate(selected_keys, start=1):
                try:
                    if key == "catapult_seesaw":
                        gauntlet.use_subject(catapult_subject, CATAPULT_SUBJECT_NAME)
                        subject.teleport(
                            pos=(-60.0, -60.0, 1.0),
                            rot_quat=(0, 0, 0, 1),
                            reset=True,
                        )
                    else:
                        gauntlet.use_subject(subject, SUBJECT_NAME)
                        catapult_subject.teleport(
                            pos=(-70.0, -70.0, 1.0),
                            rot_quat=(0, 0, 0, 1),
                            reset=True,
                        )
                    gauntlet.spawn_prop(key, index)
                    detail = SCENARIOS[key](gauntlet)
                    results[key] = {"ok": True, "detail": detail}
                except Exception as error:
                    results[key] = {"ok": False, "detail": repr(error)}
                # Park the subject clear of everything before the next station.
                try:
                    gauntlet.subject.teleport(
                        pos=(-60.0, -60.0, 1.0), rot_quat=(0, 0, 0, 1), reset=True
                    )
                    gauntlet.step(0.3)
                except Exception as error:
                    results.setdefault("session", {"ok": False, "detail": repr(error)})
                    break
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
                    files=tuple(installed_zips.values()),
                    empty_directories=(scenario_directory,),
                )

    per_mod_records, issues = _pack_log_records(log_path, log_start)
    event_failures: dict[str, Any] = {}
    for key in selected_keys:
        events = [record["event"] for record in per_mod_records.get(key, [])]
        missing = [required for required in REQUIRED_EVENTS[key] if required not in events]
        if missing:
            event_failures[key] = {"missing": missing, "events": events}
        if key == "catapult_seesaw" and "subject_launched" in events:
            event_failures[key] = {
                "forbidden": ["subject_launched"],
                "events": events,
            }
    report = {
        "results": results,
        "event_failures": event_failures,
        "log_issues": issues,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    failures = {key: value for key, value in results.items() if not value["ok"]}
    assert not failures and not event_failures and not issues, report
