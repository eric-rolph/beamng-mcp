r"""Capture whole-frame, player-eye screenshots of a packaged Giant Prop, live.

The critic loop judges Blender renders; the player judges the game. This
instrument closes that gap for AESTHETIC review: it boots the sentinel rig,
installs the mod's locked dist ZIP, spawns the prop plus a parked subject
vehicle for scale, waits for the runtime to build its parts and effects, and
then photographs the machine the way a player sees it — normal-exposure
in-game screenshots (the full-stack instrument from AGENTS.md; renderViews'
fixed exposure cannot adjudicate look), from cameras SOLVED off the spawned
prop's measured world box rather than authored by hope.

    $env:BEAMNG_MCP_TEST_BEAMNG_HOME = '...'
    $env:BEAMNG_MCP_TEST_BEAMNG_USER = '...'   # sentinel-isolated profile
    $env:BEAMNG_MCP_TEST_BEAMNG_BINARY = '...'
    .\.venv\Scripts\python.exe .\examples\giant_props\playtest_eye.py high_five

Output lands in ``<mod>/authoring/playtest_eye/`` (gitignored evidence, like
``authoring/verify/``): the frames, a ``manifest.json`` of every camera pose,
and a labeled ``contact_sheet.jpg`` sized for a vision-language reviewer to
read the whole set at once. Shot families:

- ``orbit``    — the prop framed whole from eight azimuths at low elevation.
- ``approach`` — walk-up views from player eye height (1.6 m), oblique.
- ``detail``   — closer low obliques where material response actually reads.

Event-aligned action bursts (frames snapped at telemetry events during the
behavior) are the designed next step; this v1 photographs the standing
machine, which is what most aesthetic findings have historically been about.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import threading
import time
import uuid
from contextlib import ExitStack
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
PACK_ROOT = Path(__file__).resolve().parent

from beamngpy import BeamNGpy, Scenario, Vehicle  # noqa: E402

from tests.live_support import (  # noqa: E402
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    require_confined_profile_target,
    reserve_loopback_ports,
)

EYE_HEIGHT = 1.6
ASPECT = 16.0 / 9.0
SETTLE_STEPS = 30
CAPTURE_TIMEOUT_SECONDS = 20.0


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        raise SystemExit(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY (sentinel profile) to run the playtest eye"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved = binary if binary.is_absolute() else home / binary
    if not resolved.is_file():
        raise SystemExit(f"configured BeamNG binary does not exist: {resolved}")
    if not (user / ".beamng-mcp-test-user").is_file():
        raise SystemExit("the playtest eye requires the sentinel-isolated profile")
    return home, user, binary


def _lua_json(bng: BeamNGpy, command: str) -> dict[str, Any]:
    payload = bng.control.queue_lua_command(command, response=True)
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise RuntimeError(f"unexpected Lua payload: {decoded!r}")
    return decoded


def _solve_shots(
    center: tuple[float, float, float],
    half: tuple[float, float, float],
    ground_z: float,
    fov_deg: float,
    azimuths: int,
) -> list[dict[str, Any]]:
    radius = math.sqrt(half[0] ** 2 + half[1] ** 2 + half[2] ** 2)
    horizontal_radius = math.hypot(half[0], half[1])
    vertical_half = math.radians(fov_deg) / 2.0
    horizontal_half = math.atan(math.tan(vertical_half) * ASPECT)
    limiting_half = min(vertical_half, horizontal_half)
    frame_distance = radius / math.tan(limiting_half)

    shots: list[dict[str, Any]] = []

    def add(
        name: str,
        family: str,
        distance: float,
        elevation_deg: float,
        azimuth_deg: float,
        target: tuple[float, float, float],
        eye_z: float | None = None,
    ) -> None:
        azimuth = math.radians(azimuth_deg)
        elevation = math.radians(elevation_deg)
        position = [
            center[0] + distance * math.cos(elevation) * math.cos(azimuth),
            center[1] + distance * math.cos(elevation) * math.sin(azimuth),
            (eye_z if eye_z is not None else target[2] + distance * math.sin(elevation)),
        ]
        # A camera below the terrain photographs dirt.
        position[2] = max(position[2], ground_z + 0.7)
        shots.append(
            {
                "name": name,
                "family": family,
                "position": [round(v, 3) for v in position],
                "target": [round(v, 3) for v in target],
                "azimuth_deg": azimuth_deg,
            }
        )

    for index in range(azimuths):
        azimuth_deg = index * (360.0 / azimuths)
        add(
            f"orbit_{index:02d}",
            "orbit",
            frame_distance * 1.30,
            11.0,
            azimuth_deg,
            center,
        )
    walk_target = (center[0], center[1], ground_z + 0.55 * (2.0 * half[2]) * 0.6)
    for index in range(4):
        azimuth_deg = 45.0 + index * 90.0
        add(
            f"approach_{index:02d}",
            "approach",
            max(horizontal_radius * 1.7, frame_distance * 0.55),
            0.0,
            azimuth_deg,
            walk_target,
            eye_z=ground_z + EYE_HEIGHT,
        )
    for index in range(4):
        azimuth_deg = 20.0 + index * 90.0
        add(
            f"detail_{index:02d}",
            "detail",
            frame_distance * 0.55,
            22.0,
            azimuth_deg,
            (center[0], center[1], center[2] * 0.9 + ground_z * 0.1),
        )
    return shots


def _capture(bng: BeamNGpy, user: Path, relative: str, shot: dict[str, Any]) -> Path:
    position = shot["position"]
    target = shot["target"]
    status = _lua_json(
        bng,
        f"local pos = vec3({position[0]}, {position[1]}, {position[2]}); "
        f"local target = vec3({target[0]}, {target[1]}, {target[2]}); "
        "local rot = quatFromDir((target - pos):normalized(), vec3(0, 0, 1)); "
        "commands.setFreeCamera(); "
        "core_camera.setPosRot(0, pos.x, pos.y, pos.z, rot.x, rot.y, rot.z, rot.w); "
        "return jsonEncode({ok = true})",
    )
    if status != {"ok": True}:
        raise RuntimeError(f"camera placement failed: {status}")
    bng.control.step(SETTLE_STEPS, wait=True)
    shot_relative = f"{relative}/{shot['name']}"
    status = _lua_json(
        bng,
        f"screenshot.doScreenshot(nil, nil, '{shot_relative}', 'png'); "
        "return jsonEncode({ok = true})",
    )
    if status != {"ok": True}:
        raise RuntimeError(f"doScreenshot dispatch failed: {status}")
    expected = user / f"{shot_relative}.png"
    deadline = time.monotonic() + CAPTURE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if expected.is_file() and expected.stat().st_size > 0:
            return expected
        bng.control.step(5, wait=True)
        time.sleep(0.1)
    raise RuntimeError(f"screenshot never appeared: {expected}")


def _contact_sheet(frames: list[tuple[str, Path]], destination: Path) -> None:
    from PIL import Image, ImageDraw

    columns = 4
    thumb_width = 480
    cells: list[tuple[str, Any]] = []
    for name, path in frames:
        image = Image.open(path)
        scale = thumb_width / image.width
        cells.append((name, image.resize((thumb_width, int(image.height * scale)))))
    if not cells:
        return
    cell_height = max(image.height for _, image in cells) + 26
    rows = (len(cells) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_width, rows * cell_height), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for index, (name, image) in enumerate(cells):
        x = (index % columns) * thumb_width
        y = (index // columns) * cell_height
        sheet.paste(image, (x, y))
        draw.text((x + 6, y + image.height + 5), name, fill=(235, 235, 235))
    sheet.save(destination, quality=88)


def _frame_is_blank(path: Path) -> bool:
    import numpy as np
    from PIL import Image

    pixels = np.asarray(Image.open(path).convert("L"), dtype=np.float32)
    return float(pixels.std()) < 2.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mod_key")
    parser.add_argument("--azimuths", type=int, default=8)
    parser.add_argument(
        "--no-subject", action="store_true", help="skip the parked scale-reference vehicle"
    )
    arguments = parser.parse_args()

    mod_key = arguments.mod_key
    mod_id = f"ericrolph_{mod_key}"
    runtime_extension = mod_id.replace("_", "__") + "_runtime"
    example_root = PACK_ROOT / mod_key
    dist_root = example_root / "dist"
    archive = dist_root / f"{mod_key}_ericrolph.zip"
    lock = json.loads((dist_root / f"{mod_id}.lock.json").read_text(encoding="utf-8"))
    payload = archive.read_bytes()
    if hashlib.sha256(payload).hexdigest() != lock["sha256"]:
        raise SystemExit(f"{mod_key}: dist zip does not match its lock; re-cut before shooting")

    home, user, binary = _configured_runtime()
    suffix = uuid.uuid4().hex[:10]
    installed_zip = require_confined_profile_target(
        user, Path("mods") / f"{mod_key}_playtest_eye_{suffix}.zip"
    )
    scenario_name = f"{mod_key}_playtest_eye_{suffix}"
    scenario_directory = require_confined_profile_target(
        user, Path("levels") / "smallgrid" / "scenarios" / scenario_name
    )
    capture_relative = f"screenshots/playtest_eye/{mod_key}_{suffix}"
    capture_root = require_confined_profile_target(user, Path(capture_relative))

    output_root = example_root / "authoring" / "playtest_eye"
    output_root.mkdir(parents=True, exist_ok=True)

    prop_name = f"{mod_id}_eye_prop"
    subject_name = f"{mod_id}_eye_subject"

    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(1))
        (tcom_port,) = reservation.ports
        conflicts = (
            [
                str(path)
                for path in (user / "mods").glob("*.zip")
                if mod_id in path.name and path != installed_zip
            ]
            if (user / "mods").is_dir()
            else []
        )
        if conflicts:
            raise SystemExit(f"competing {mod_id} archives in the isolated profile: {conflicts}")
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
        manifest: dict[str, Any] = {
            "mod_key": mod_key,
            "mod_id": mod_id,
            "zip_sha256": lock["sha256"],
            "build_serial": lock.get("build_serial"),
            "level": "smallgrid",
            "exposure": "normal (screenshot.doScreenshot)",
            "frames": [],
        }
        try:

            def watchdog() -> None:
                process = bng.process
                if process is not None and process.poll() is None:
                    process.terminate()

            timer = threading.Timer(420.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)

            scenario = Scenario(
                "smallgrid", scenario_name, description="Disposable playtest-eye fixture"
            )
            subject = Vehicle(subject_name, "pigeon", license="EYE")
            scenario.add_vehicle(
                subject, pos=(60.0, 60.0, 20.0), rot_quat=(0, 0, 0, 1), cling=False
            )
            scenario.make(bng)
            bng.control.pause()
            bng.scenario.load(scenario, precompile_shaders=False)
            bng.scenario.start()
            bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
            bng.control.pause()
            bng.control.step(3, wait=True)

            surface = _lua_json(
                bng,
                "local rayStart = vec3(0, 0, 200); "
                "local rayDistance = castRayStatic(rayStart, vec3(0, 0, -1), 300); "
                "return jsonEncode({surface_z = rayStart.z - rayDistance})",
            )
            ground_z = float(surface["surface_z"])

            prop = Vehicle(prop_name, mod_id, license="EYE")
            spawned = bng.vehicles.spawn(prop, (0.0, 0.0, ground_z), (0, 0, 0, 1), False, True)
            if spawned is not True:
                raise RuntimeError(f"prop spawn failed: {spawned!r}")

            registered = False
            for _ in range(24):
                bng.control.step(15, wait=True)
                state = _lua_json(
                    bng,
                    f"local extension = extensions[{runtime_extension!r}]; "
                    f"local prop = scenetree.findObject({prop_name!r}); "
                    "if not (extension and prop) then return jsonEncode({registered = false}) end; "
                    "local state = extension.getSystemState(prop:getID()); "
                    "return jsonEncode({registered = state.registered == true or "
                    "state.part_count ~= nil})",
                )
                if state.get("registered"):
                    registered = True
                    break
            manifest["runtime_registered"] = registered
            # The machine breathes for a moment so effects and settle finish.
            bng.control.step(120, wait=True)

            box = _lua_json(
                bng,
                f"local prop = scenetree.findObject({prop_name!r}); "
                "local worldBox = prop:getWorldBox(); "
                "local boxCenter = worldBox:getCenter(); "
                "return jsonEncode({center = {boxCenter.x, boxCenter.y, boxCenter.z}, "
                "min = {worldBox.minExtents.x, worldBox.minExtents.y, worldBox.minExtents.z}, "
                "max = {worldBox.maxExtents.x, worldBox.maxExtents.y, worldBox.maxExtents.z}})",
            )
            center = tuple(float(v) for v in box["center"])
            half = tuple(
                (float(box["max"][axis]) - float(box["min"][axis])) / 2.0 for axis in range(3)
            )
            manifest["world_box"] = box

            fov = _lua_json(bng, "return jsonEncode({fov = core_camera.getFovDeg() or 65})")
            fov_deg = float(fov.get("fov") or 65.0)

            if not arguments.no_subject:
                horizontal_radius = math.hypot(half[0], half[1])
                park = (
                    center[0] + (horizontal_radius + 4.0) * math.cos(math.radians(30.0)),
                    center[1] + (horizontal_radius + 4.0) * math.sin(math.radians(30.0)),
                    ground_z + 0.5,
                )
                subject.teleport(pos=park, rot_quat=(0, 0, 0.966, -0.259), reset=True)
                bng.control.step(60, wait=True)

            shots = _solve_shots(center, half, ground_z, fov_deg, arguments.azimuths)
            captured: list[tuple[str, Path]] = []
            for shot in shots:
                frame = _capture(bng, user, capture_relative, shot)
                shot["blank"] = _frame_is_blank(frame)
                manifest["frames"].append(shot)
                captured.append((shot["name"], frame))
                print(f"captured {shot['name']}" + ("  [BLANK?]" if shot["blank"] else ""))

            for name, frame in captured:
                shutil.copyfile(frame, output_root / f"{name}.png")
            _contact_sheet(captured, output_root / "contact_sheet.jpg")
            (output_root / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
            )
            blanks = sum(1 for shot in manifest["frames"] if shot.get("blank"))
            print(
                f"wrote {len(captured)} frames + contact_sheet.jpg + manifest.json -> "
                f"{output_root}" + (f"  ({blanks} frames look blank!)" if blanks else "")
            )
        finally:
            try:
                cleanup_owned_beamng_session(bng, owned_process=owned_process, scenario=scenario)
            finally:
                if timer is not None:
                    timer.cancel()
                shutil.rmtree(capture_root, ignore_errors=True)
                cleanup_exact_live_artifacts(
                    profile=user,
                    files=(installed_zip,),
                    empty_directories=(scenario_directory,),
                )


if __name__ == "__main__":
    main()
