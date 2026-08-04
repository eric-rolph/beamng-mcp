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
            f"local subject = scenetree.findObject({SUBJECT_NAME!r}); "
            "if not subject then return jsonEncode({ok = false}) end; "
            "local position = subject:getPosition(); "
            "return jsonEncode({ok = true, x = position.x, y = position.y, z = position.z})"
        )
        assert probe.get("ok") is True, probe
        return probe

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
    ) -> None:
        position = self.world_point(key, authored_x, authored_y, authored_z)
        self.subject.teleport(pos=position, rot_quat=(0, 0, 0, 1), reset=True)
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
    g.place_subject(key, 0.0, -7.5, 1.8, parkingbrake=1.0, settle_seconds=0.6)
    baseline = float(g.subject_probe()["z"])
    peak = baseline
    flung = False
    for _ in range(int(9.0 / 0.25)):
        g.step(0.25)
        z = float(g.subject_probe()["z"])
        peak = max(peak, z)
        if peak - baseline > 6.0:
            flung = True
            break
    assert flung, {"detail": "seesaw never flung the parked subject", "gain": peak - baseline}
    return {"height_gain_m": peak - baseline}


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
    "catapult_seesaw": ("prop_registered", "weight_released", "seesaw_flung"),
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
    payloads: dict[str, bytes] = {}
    for key in ALL_MOD_KEYS:
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
        for key in ALL_MOD_KEYS
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
                if any(mod_id_for(key) in path.name or key in path.name for key in ALL_MOD_KEYS)
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
            scenario.add_vehicle(
                subject, pos=(-60.0, -60.0, 20.0), rot_quat=(0, 0, 0, 1), cling=False
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

            for index, key in enumerate(TESTED_MOD_KEYS, start=1):
                try:
                    gauntlet.spawn_prop(key, index)
                    detail = SCENARIOS[key](gauntlet)
                    results[key] = {"ok": True, "detail": detail}
                except Exception as error:
                    results[key] = {"ok": False, "detail": repr(error)}
                # Park the subject clear of everything before the next station.
                try:
                    subject.teleport(pos=(-60.0, -60.0, 1.0), rot_quat=(0, 0, 0, 1), reset=True)
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
    for key in TESTED_MOD_KEYS:
        events = [record["event"] for record in per_mod_records.get(key, [])]
        missing = [required for required in REQUIRED_EVENTS[key] if required not in events]
        if missing:
            event_failures[key] = {"missing": missing, "events": events}
    report = {
        "results": results,
        "event_failures": event_failures,
        "log_issues": issues,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    failures = {key: value for key, value in results.items() if not value["ok"]}
    assert not failures and not event_failures and not issues, report
