"""Live gate for COLOSSUS 10350/80R457, in the sentinel-isolated profile.

The static gates prove the evidence chain, the cage arithmetic and the runtime
logic. There are four claims this mod rests on that NONE of them can reach,
because each is a property of the engine actually running the thing:

1. IT STANDS UP. 1,072 free nodes in a 28 m ring carrying 10.5 t with its
   centre of mass 14 m off the ground. The headless static solver says it
   settles onto an 8.3 x 3.7 m footprint, but a static solver cannot see
   integrator drift, contact chatter, or a carcass that slowly ovalises over
   a thousand frames. Here it has to be upright, round and at the right
   height after real physics has had it for several seconds.

2. THE FLOORS ARE SOLID FROM THE RIGHT SIDE. jbeam collision triangles are
   one-sided, and the whole first round of this mod shipped with its dock
   facing down and its cavity floor wound inside out. A car parked on each
   surface, in-engine, is the only test that actually settles that.

3. THE DOORWAY IS OPEN. Nine sidewall nodes stood inside the opening with
   collision on; the skin was gone, so nothing static could see them.

4. IT ROLLS BECAUSE SOMETHING PUSHED IT. The premise of the mod. The test
   pushes the SUBJECT (not the tire) and then reads the tire's own axle fit
   to see whether it moved. Nothing in the shipped runtime applies a force to
   anything - `ALLOW_SUBJECT_MUTATION = False` means the generated Lua does
   not even contain a function that could.

Configure with BEAMNG_MCP_TEST_BEAMNG_HOME / _USER / _BINARY; the profile must
carry the `.beamng-mcp-test-user` sentinel. Opt-in, like every live gate here.

    .venv\\Scripts\\python.exe -m pytest -q -s tests\\test_colossus_tire_live.py
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import uuid
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

MOD_KEY = "colossus_tire"
MOD_ID = "ericrolph_colossus_tire"
ZIP_BASENAME = "colossus_tire_ericrolph.zip"
RUNTIME_EXTENSION = "ericrolph__colossus__tire_runtime"
LOG_TAG = "ERICROLPH_COLOSSUS_TIRE_RUNTIME"
LIVE_TEST_TAG = "GIANT_PROPS_LIVE_TEST"
PROP_NAME = f"{MOD_ID}_live_prop"
SUBJECT_NAME = f"{MOD_ID}_live_subject"
PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
EXPECTED_TRIGGERS = {"dock": "Overlaps", "cabin": "Overlaps"}


def load_spec():
    import importlib.util

    spec_path = PACK_ROOT / MOD_KEY / "spec.py"
    loader = importlib.util.spec_from_file_location("colossus_live_spec", spec_path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


SPEC = load_spec()


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the Colossus live gate"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the Colossus live gate requires a sentinel-isolated profile")
    return home, user, binary


def _lua_json(bng: BeamNGpy, command: str) -> dict[str, Any]:
    payload = bng.control.queue_lua_command(command, response=True)
    decoded = json.loads(payload)
    assert isinstance(decoded, dict), decoded
    return decoded


def _runtime_state(bng: BeamNGpy) -> dict[str, Any]:
    return _lua_json(
        bng,
        f"local extension = extensions[{RUNTIME_EXTENSION!r}]; "
        f"local prop = scenetree.findObject({PROP_NAME!r}); "
        "if not extension then return jsonEncode({loaded = false}) end; "
        "if not prop then return jsonEncode({loaded = true, registered = false}) end; "
        "local state = extension.getSystemState(prop:getID()); "
        "state.loaded = true; "
        "return jsonEncode(state)",
    )


def _marker_points(bng: BeamNGpy) -> list[tuple[float, float, float]] | None:
    """World positions of the three crown-centre markers the runtime fits to.

    Read independently of the runtime, from the same cage nodes, so a failure
    here is the TIRE's and not the measurement layer's.
    """

    names = ", ".join(repr(name) for name in SPEC.BEHAVIOR["marker_nodes"])
    payload = _lua_json(
        bng,
        f"local prop = scenetree.findObject({PROP_NAME!r}); "
        "if not prop then return jsonEncode({ok = false}) end; "
        "local data = core_vehicle_manager.getVehicleData(prop:getID()); "
        "local nodes = data and data.vdata and data.vdata.nodes; "
        "if not nodes then return jsonEncode({ok = false}) end; "
        f"local wanted = {{{names}}}; "
        "local out = {}; "
        "local base = prop:getPosition(); "
        "for index, name in ipairs(wanted) do "
        "  for _, node in pairs(nodes) do "
        "    if node.name == name then "
        "      local rel = prop:getNodePosition(node.cid); "
        "      out[index] = {base.x + rel.x, base.y + rel.y, base.z + rel.z}; "
        "    end "
        "  end "
        "end; "
        "if #out < 3 then return jsonEncode({ok = false, found = #out}) end; "
        "return jsonEncode({ok = true, points = out})",
    )
    if not payload.get("ok"):
        return None
    return [tuple(float(value) for value in point) for point in payload["points"]]


def _fit_axle(points):
    """Centre, unit axis and radius of the circle through three points."""

    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points
    v1 = (bx - ax, by - ay, bz - az)
    v2 = (cx - ax, cy - ay, cz - az)
    normal = (
        v1[1] * v2[2] - v1[2] * v2[1],
        v1[2] * v2[0] - v1[0] * v2[2],
        v1[0] * v2[1] - v1[1] * v2[0],
    )
    nn = sum(component * component for component in normal)
    if nn < 1e-9:
        return None
    v1v1 = sum(value * value for value in v1)
    v2v2 = sum(value * value for value in v2)
    v1mv2 = tuple(v1[i] - v2[i] for i in range(3))
    alpha = v2v2 * sum(v1[i] * v1mv2[i] for i in range(3)) / (2 * nn)
    beta = v1v1 * sum(v2[i] * -v1mv2[i] for i in range(3)) / (2 * nn)
    centre = tuple(
        (ax, ay, az)[i] + v1[i] * alpha + v2[i] * beta for i in range(3)
    )
    length = math.sqrt(nn)
    axis = tuple(component / length for component in normal)
    radius = math.dist(centre, (ax, ay, az))
    return centre, axis, radius


def _subject_probe(bng: BeamNGpy) -> dict[str, Any]:
    return _lua_json(
        bng,
        f"local subject = scenetree.findObject({SUBJECT_NAME!r}); "
        "if not subject then return jsonEncode({ok = false}) end; "
        "local position = subject:getPosition(); "
        "return jsonEncode({ok = true, x = position.x, y = position.y, z = position.z})",
    )


def _runtime_log_records(log_path: Path, start_marker: str) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    issues: list[str] = []
    started = False
    payload = log_path.read_text(encoding="utf-8", errors="replace")
    for line in payload.splitlines():
        if start_marker in line:
            started = True
            continue
        if not started or LOG_TAG not in line:
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
            records.append(record)
    return records, issues


def _authored_to_world(origin, authored) -> tuple[float, float, float]:
    """The prop renders at world (-x, -y, z) from its origin.

    MODEL_ALIGNMENT_ROTATION is a proper 180-degree Z flip, which is the same
    rotation the cage coordinates went through, so an authored point maps by
    negating x and y.
    """

    return (
        float(origin[0]) - authored[0],
        float(origin[1]) - authored[1],
        float(origin[2]) + authored[2],
    )


@pytest.mark.beamng_live
def test_the_colossus_stands_up_holds_its_floors_and_rolls(tmp_path: Path) -> None:
    home, user, binary = _configured_runtime()
    dist_root = PACK_ROOT / MOD_KEY / "dist"
    archive = dist_root / ZIP_BASENAME
    lock = json.loads((dist_root / f"{MOD_ID}.lock.json").read_text(encoding="utf-8"))
    payload = archive.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == lock["sha256"], (
        "the packaged ZIP does not match its lock; run build.py <mod> all"
    )

    suffix = uuid.uuid4().hex[:10]
    installed_zip = require_confined_profile_target(
        user, Path("mods") / f"colossus_tire_live_{suffix}.zip"
    )
    scenario_name = f"colossus_tire_live_{suffix}"
    scenario_directory = require_confined_profile_target(
        user, Path("levels") / "smallgrid" / "scenarios" / scenario_name
    )
    log_path = user / "beamng.log"
    log_start = f"colossus_live_start_{suffix}"
    report: dict[str, Any] = {}

    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(1))
        (tcom_port,) = reservation.ports
        existing_conflicts = (
            [
                str(path)
                for path in (user / "mods").glob("*.zip")
                if MOD_ID in path.name and path != installed_zip
            ]
            if (user / "mods").is_dir()
            else []
        )
        if existing_conflicts:
            pytest.fail(
                f"competing {MOD_ID} archives in the isolated profile: {existing_conflicts}"
            )
        if installed_zip.exists():
            pytest.fail(f"refusing to overwrite isolated-profile artifact: {installed_zip}")
        installed_zip.parent.mkdir(parents=True, exist_ok=True)
        with installed_zip.open("xb") as handle:
            handle.write(payload)
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

            # A 1,090-node softbody takes longer to settle than the pack's
            # other props, so the watchdog is longer than the toaster's 300 s.
            timer = threading.Timer(600.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)

            scenario = Scenario(
                "smallgrid",
                scenario_name,
                description="Disposable Colossus live smoke fixture",
            )
            subject = Vehicle(SUBJECT_NAME, "pigeon", license="ROLL")
            scenario.add_vehicle(
                subject, pos=(40.0, 40.0, 20.0), rot_quat=(0, 0, 0, 1), cling=False
            )
            scenario.make(bng)
            bng.control.pause()
            bng.scenario.load(scenario, precompile_shaders=False)
            bng.scenario.start()
            bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
            bng.control.pause()
            bng.control.step(3, wait=True)
            marker = _lua_json(
                bng,
                f"log('I', {LIVE_TEST_TAG!r}, {log_start!r}); return jsonEncode({{ok = true}})",
            )
            assert marker == {"ok": True}

            surface = _lua_json(
                bng,
                "local rayStart = vec3(0, 0, 200); "
                "local rayDistance = castRayStatic(rayStart, vec3(0, 0, -1), 300); "
                "return jsonEncode({distance = rayDistance, "
                "surface_z = rayStart.z - rayDistance})",
            )
            assert 0.0 < float(surface["distance"]) < 300.0, surface
            surface_z = float(surface["surface_z"])

            prop = Vehicle(PROP_NAME, MOD_ID, license="COLOSSUS")
            spawned = bng.vehicles.spawn(
                prop, (0.0, 0.0, surface_z), (0, 0, 0, 1), False, True
            )
            assert spawned is True

            state: dict[str, Any] = {}
            for _ in range(40):
                bng.control.step(15, wait=True)
                state = _runtime_state(bng)
                if state.get("registered"):
                    break
            assert state.get("loaded") is True, state
            assert state.get("registered") is True, state
            assert state["trigger_count"] == len(EXPECTED_TRIGGERS), state
            for zone, mode in EXPECTED_TRIGGERS.items():
                trigger = state["triggers"][zone]
                assert trigger["mode"] == mode, (zone, trigger)
                assert trigger["test_type"] == "Bounding box", (zone, trigger)
            origin = state["origin"]

            # ---- CLAIM 1: it stands up, stays round, and does not sink.
            bng.control.step(300, wait=True)          # five seconds of settling
            points = None
            for _ in range(20):
                points = _marker_points(bng)
                if points:
                    break
                bng.control.step(15, wait=True)
            assert points, "the crown marker nodes never resolved"
            fit = _fit_axle(points)
            assert fit, f"the three markers are collinear: {points}"
            centre, axis, radius = fit
            for value in (*centre, *axis, radius):
                assert math.isfinite(value), (centre, axis, radius)

            axle_height = centre[2] - surface_z
            lean = abs(axis[2])
            report["settled"] = {
                "axle_height": round(axle_height, 3),
                "fitted_radius": round(radius, 3),
                "lean_dot": round(lean, 4),
            }
            # A carcass that collapsed, ovalised or exploded fails one of
            # these three; a carcass that fell over fails the lean.
            assert abs(radius - SPEC.OUTER_RADIUS) < 0.60, report["settled"]
            assert abs(axle_height - SPEC.OUTER_RADIUS) < 0.80, report["settled"]
            assert lean < SPEC.BEHAVIOR["leaning_dot"], report["settled"]

            # ---- CLAIM 2a: the loading dock is solid FROM ABOVE.
            dock_target = _authored_to_world(
                origin, (11.5, 0.0, SPEC.DOCK_LANDING_Z + 1.2)
            )
            subject.teleport(pos=dock_target, rot_quat=(0, 0, 0, 1), reset=True)
            bng.control.step(180, wait=True)
            on_dock = _subject_probe(bng)
            assert on_dock["ok"] is True, on_dock
            dock_rest = float(on_dock["z"]) - surface_z
            report["on_dock_z"] = round(dock_rest, 3)
            assert dock_rest > SPEC.DOCK_LANDING_Z - 0.35, (
                "the subject fell through the loading dock: "
                f"rested at {dock_rest:.3f} against a deck at {SPEC.DOCK_LANDING_Z:.3f}"
            )

            # ---- CLAIM 2b + 3: the cavity floor is solid and the doorway is
            # clear enough to sit in.
            cabin_target = _authored_to_world(
                origin, (0.0, 0.0, SPEC.CAVITY_FLOOR_Z + 1.4)
            )
            subject.teleport(pos=cabin_target, rot_quat=(0, 0, 0, 1), reset=True)
            bng.control.step(240, wait=True)
            in_cabin = _subject_probe(bng)
            assert in_cabin["ok"] is True, in_cabin
            cabin_rest = float(in_cabin["z"]) - surface_z
            report["in_cabin_z"] = round(cabin_rest, 3)
            assert cabin_rest > SPEC.CAVITY_FLOOR_Z - 0.40, (
                "the subject fell through the inner liner: "
                f"rested at {cabin_rest:.3f} against a floor at {SPEC.CAVITY_FLOOR_Z:.3f}"
            )

            # Boarding should have fired and cut the tie-downs.
            boarded = False
            for _ in range(40):
                bng.control.step(15, wait=True)
                state = _runtime_state(bng)
                if state.get("zone_counts", {}).get("cabin", 0) >= 1:
                    boarded = True
                    break
            report["boarded"] = boarded
            assert boarded, state

            # ---- CLAIM 4: pushing the SUBJECT rolls the tire.
            before = _fit_axle(_marker_points(bng) or points)
            assert before
            # Roll direction is the tire's own axle-perpendicular horizontal.
            roll = (-axis[1], axis[0], 0.0)
            norm = math.hypot(roll[0], roll[1]) or 1.0
            roll = (roll[0] / norm, roll[1] / norm, 0.0)
            for _ in range(14):
                subject.set_velocity(12.0, dt=0.12)
                bng.control.step(45, wait=True)
            after = _fit_axle(_marker_points(bng) or points)
            assert after
            travelled = math.dist(before[0], after[0])
            report["axle_travel_m"] = round(travelled, 3)
            report["roll_hint"] = [round(value, 3) for value in roll]
            assert travelled > 0.25, (
                "the Colossus did not move when the subject drove inside it: "
                f"axle travelled {travelled:.3f} m"
            )
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
                    files=(installed_zip,),
                    empty_directories=(scenario_directory,),
                )

    records, issues = _runtime_log_records(log_path, log_start)
    events = [str(record["event"]) for record in records]
    report["events"] = events
    report["log_issues"] = issues
    for required in ("prop_registered", "zone_enter", "colossus_boarded"):
        assert required in events, report
    assert not issues, report
    print(json.dumps(report, sort_keys=True))
