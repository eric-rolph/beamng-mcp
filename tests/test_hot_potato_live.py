"""Live gate for Hot Potato: the multi-vehicle round, played for real.

DESIGN.md §8 called this the genuinely new work: every other prop is a fixed
machine tested with one subject, and the pack's single-subject gates cannot
see this mod's mechanic at all. `test_hot_potato_logic.py` proves the state
machine against synthetic positions; this boots BeamNG in the sentinel
profile and plays an actual round with two cars:

- the prop registers, its six visual materials resolve as Materials (the
  2026-08-29 player recording showed the whole arch on NO MATERIAL orange —
  a stale .cdae served over date-pinned zip members, see packaging.py's
  STALE-CACHE TRAP),
- the game's own UI app scanner discovers the shipped hotPotatoTuner HUD
  app, AND the Add-App browser's cached backend (ui_appSelector_general —
  the layer that actually feeds the grid, and the one whose stale cache hid
  the app from the player, v2.4) lists it, AND the HUD Layouts list itself
  carries the shipped "Hot Potato" layout (v2.4.2 — the player was
  scrolling the layouts list, where an app can never appear, so the mod now
  ships a whole layout there); hotPotatoGetStats gates the numeric
  countdown behind show_countdown,
- the boom throws the mash chunks above grade, then the potato takes the
  v2.4 return flight home instead of teleporting onto the nearest car,
- the tick loop is DEAD in the victim's VM after detonation (the
  2026-08-29 audio-persistence report, pinned at the source),
- driving onto the medallion starts the round,
- a real ram at over impact_kmh transfers the potato (reason "impact"),
- the tag-back rules hold the potato through the immunity window,
- the fuse tick LOOP exists in the carrier's own VM, moves on transfer, and
  the passer's VM goes silent — audio mechanism v3, replacing the leaked
  Engine.Audio.playOnce loop instances the player filmed still beeping
  after the mod was deleted,
- the fuse (shortened via the mod's own live options surface) detonates the
  CURRENT carrier and the physics agrees,
- after the round settles, the DETONATED car drives back onto the pad and
  gets the potato — the single-player lockout from the 2026-08-28 log,
  where four pad crossings after a boom armed nothing,
- deleting the prop mid-round silences the carrier's tick through the
  behavior.cleanup hook (sound must not outlive the mod),
- and the runtime logs no errors doing any of it.

It also captures normal-exposure in-game screenshots (the arch, the carried
potato) — the constitution's full-stack visual instrument — into
HOT_POTATO_LIVE_SHOT_DIR (or the pytest tmp dir) for aesthetic review.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
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

MOD_KEY = "hot_potato"
MOD_ID = "ericrolph_hot_potato"
ZIP_BASENAME = "hot_potato_ericrolph.zip"
RUNTIME_EXTENSION = "ericrolph__hot__potato_runtime"
LOG_TAG = "ERICROLPH_HOT_POTATO_RUNTIME"
LIVE_TEST_TAG = "GIANT_PROPS_LIVE_TEST"
PROP_NAME = f"{MOD_ID}_live_prop"
CARRIER_NAME = f"{MOD_ID}_live_carrier"
RAMMER_NAME = f"{MOD_ID}_live_rammer"
PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"

VISUAL_MATERIALS = (
    f"{MOD_ID}_arch_steel",
    f"{MOD_ID}_copper",
    f"{MOD_ID}_mash",
    f"{MOD_ID}_pad_steel",
    f"{MOD_ID}_plinth_concrete",
    f"{MOD_ID}_potato",
)

#: Options pushed through the mod's own live surface so the gate plays a
#: SHORT round. Every value is inside its OPTION_RANGE clamp; the settings
#: file this writes in the sentinel profile is removed in cleanup.
FAST_ROUND_OPTIONS = {
    "fuse_base_seconds": 18,
    "fuse_sigma_seconds": 0,
    "fuse_min_seconds": 15,
    "fuse_max_seconds": 20,
    "cue_window_seconds": 12,
}

STEPS_PER_CALL = 15
#: Ram speed: comfortably over impact_kmh (15 km/h = 4.17 m/s closing).
RAM_MPS = 10.0


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the Hot Potato live gate"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the Hot Potato live gate requires a sentinel-isolated profile")
    return home, user, resolved_binary


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


def _stats(bng: BeamNGpy) -> dict[str, Any]:
    state = _runtime_state(bng)
    stats = state.get("behavior_stats") or {}
    stats["phase"] = state.get("behavior_phase")
    return stats


def _vehicle_probe(bng: BeamNGpy, scene_name: str) -> dict[str, Any]:
    return _lua_json(
        bng,
        f"local subject = scenetree.findObject({scene_name!r}); "
        "if not subject then return jsonEncode({ok = false}) end; "
        "local position = subject:getPosition(); "
        "local velocity = subject:getVelocity(); "
        "return jsonEncode({ok = true, id = subject:getID(), "
        "x = position.x, y = position.y, z = position.z, "
        "speed = velocity:length()})",
    )


def _tick_probe(bng: BeamNGpy, scene_name: str, slot: str) -> bool | None:
    """Whether the tick loop is playing INSIDE that vehicle's VM.

    Nothing on the vehicle side of the VM boundary is observable from GE, so
    the probe round-trips: queue a command into the vehicle VM that reads
    the tick table and echoes it back into a GE global, step, read it.
    """

    # Three VMs, three quoting levels: the GE command carries the vehicle
    # command as a [[long string]]; the vehicle command builds the echo in
    # double quotes; the echoed GE chunk uses single quotes.
    _lua_json(
        bng,
        f"rawset(_G, 'hp_probe_{slot}', nil); "
        f"local subject = scenetree.findObject({scene_name!r}); "
        "if subject then subject:queueLuaCommand("
        '[[local S = rawget(_G, "ericrolph_hot_potato_tick") '
        'obj:queueGameEngineLua("rawset(_G, \'hp_probe_' + slot + '\', " '
        '.. tostring(S ~= nil and S.on == true) .. ")")]]) end; '
        "return jsonEncode({ok = true})",
    )
    bng.control.step(STEPS_PER_CALL, wait=True)
    answer = _lua_json(
        bng,
        f"return jsonEncode({{value = rawget(_G, 'hp_probe_{slot}')}})",
    )
    return answer.get("value")


def _screenshot(bng: BeamNGpy, position, target, name: str) -> None:
    """Normal-exposure in-game screenshot: the full-stack visual instrument."""

    px, py, pz = position
    tx, ty, tz = target
    _lua_json(
        bng,
        "commands.setFreeCamera(); "
        f"local eye = vec3({px}, {py}, {pz}); "
        f"local aim = vec3({tx}, {ty}, {tz}); "
        "local rotation = quatFromDir((aim - eye):normalized(), vec3(0, 0, 1)); "
        "core_camera.setPosRot(0, eye.x, eye.y, eye.z, "
        "rotation.x, rotation.y, rotation.z, rotation.w); "
        "return jsonEncode({ok = true})",
    )
    bng.control.step(30, wait=True)
    _lua_json(
        bng,
        f"screenshot.doScreenshot(nil, nil, 'screenshots/{name}', 'png'); "
        "return jsonEncode({ok = true})",
    )
    bng.control.step(15, wait=True)


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


def _step_until(bng: BeamNGpy, predicate, *, calls: int, note: str) -> int:
    for index in range(calls):
        if predicate():
            return index
        bng.control.step(STEPS_PER_CALL, wait=True)
    raise AssertionError(f"condition never held within {calls} step calls: {note}")


@pytest.mark.beamng_live
def test_hot_potato_round_transfer_detonation_and_teardown(tmp_path: Path) -> None:
    home, user, binary = _configured_runtime()
    dist_root = PACK_ROOT / MOD_KEY / "dist"
    archive = dist_root / ZIP_BASENAME
    lock = json.loads((dist_root / f"{MOD_ID}.lock.json").read_text(encoding="utf-8"))
    payload = archive.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == lock["sha256"], (
        "the packaged zip does not match its lock; rebuild before testing it"
    )

    shot_dir = Path(os.getenv("HOT_POTATO_LIVE_SHOT_DIR", str(tmp_path / "shots")))
    shot_dir.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:10]
    installed_zip = require_confined_profile_target(
        user, Path("mods") / f"hot_potato_live_{suffix}.zip"
    )
    scenario_name = f"hot_potato_live_{suffix}"
    scenario_directory = require_confined_profile_target(
        user, Path("levels") / "smallgrid" / "scenarios" / scenario_name
    )
    settings_file = user / "settings" / f"{MOD_ID}.json"
    shot_names = [
        f"hp_arch_{suffix}",
        f"hp_medallion_{suffix}",
        f"hp_copper_{suffix}",
        f"hp_plinth_{suffix}",
        f"hp_carry_{suffix}",
        f"hp_ram_{suffix}",
        f"hp_boom_{suffix}",
        f"hp_mash_{suffix}",
    ]
    profile_shots = tuple((user / "screenshots" / f"{name}.png") for name in shot_names)
    log_path = user / "beamng.log"
    log_start = f"hot_potato_live_start_{suffix}"

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

            timer = threading.Timer(560.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)

            scenario = Scenario(
                "smallgrid",
                scenario_name,
                description="Disposable Hot Potato live round fixture",
            )
            carrier = Vehicle(CARRIER_NAME, "etk800", license="TUBER")
            rammer = Vehicle(RAMMER_NAME, "etk800", license="TAGGER")
            scenario.add_vehicle(
                carrier, pos=(60.0, 60.0, 20.0), rot_quat=(0, 0, 0, 1), cling=True
            )
            scenario.add_vehicle(
                rammer, pos=(60.0, 80.0, 20.0), rot_quat=(0, 0, 0, 1), cling=True
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

            # Spawn OFF the map origin: smallgrid paints +X/+Y axis decals
            # and an origin glyph there, and they photobomb every medallion
            # beauty shot (critic round, 2026-08-29).
            prop = Vehicle(PROP_NAME, MOD_ID, license="POTATO")
            spawned = bng.vehicles.spawn(
                prop, (90.0, -90.0, surface_z), (0, 0, 0, 1), False, True
            )
            assert spawned is True

            state: dict[str, Any] = {}
            for _ in range(24):
                bng.control.step(STEPS_PER_CALL, wait=True)
                state = _runtime_state(bng)
                if state.get("registered"):
                    break
            assert state.get("loaded") is True, state
            assert state.get("registered") is True, state
            # v2.4: the tuber plus its six mash chunks parked under the plaza.
            assert state["part_count"] == 7, state
            assert state["triggers"]["pad"]["mode"] == "Overlaps", state
            origin_raw = state["origin"]
            origin = (float(origin_raw[0]), float(origin_raw[1]), float(origin_raw[2]))

            # --- THE VISUAL REGRESSION: materials must resolve live --------
            # The player's recording showed the whole structure on NO
            # MATERIAL orange because a stale cache served the v1 mesh whose
            # materials v2 no longer ships. With the cut-wallclock member
            # stamps the engine must re-import and every material must be a
            # real Material object.
            materials = _lua_json(
                bng,
                "local out = {}; "
                + " ".join(
                    f"local m{i} = scenetree.findObject({name!r}); "
                    f"out[{name!r}] = m{i} and m{i}:getClassName() or 'MISSING'; "
                    for i, name in enumerate(VISUAL_MATERIALS)
                )
                + "return jsonEncode(out)",
            )
            # The engine reports the class lowercase ("material") — the same
            # reason ensureVisualMaterials lowercases before comparing.
            for name in VISUAL_MATERIALS:
                assert str(materials.get(name)).lower() == "material", {
                    "detail": "a shipped visual material did not resolve — "
                    "the NO MATERIAL regression",
                    "materials": materials,
                }

            # --- fast round via the mod's own live options surface ---------
            for key, value in FAST_ROUND_OPTIONS.items():
                answer = _lua_json(
                    bng,
                    f"local ok = extensions[{RUNTIME_EXTENSION!r}]"
                    f".hotPotatoSetOption({key!r}, {value}); "
                    "return jsonEncode({ok = ok == true})",
                )
                assert answer == {"ok": True}, (key, value, answer)

            # The arch, photographed before anything happens to it — and the
            # medallion from a worm's-eye close-up with the idle potato
            # bobbing over it and the arch soaring behind.
            _screenshot(
                bng,
                # Pulled back for the quarter-scale monument (47.6 m tall).
                (origin[0] + 42.0, origin[1] + 54.0, origin[2] + 16.0),
                (origin[0], origin[1], origin[2] + 22.0),
                shot_names[0],
            )
            _screenshot(
                bng,
                (origin[0] + 9.0, origin[1] - 9.0, origin[2] + 1.6),
                (origin[0], origin[1], origin[2] + 6.5),
                shot_names[1],
            )
            # Reading-distance close-ups of the hyper-real surfaces: the
            # copper inlay band in the pad plate and the west leg's concrete
            # plinth. The aesthetic instrument at the range a player actually
            # parks at. (v2.3 retired the modelled wick and its close-up; the
            # idle smoke shows in the medallion worm's-eye above.)
            _screenshot(
                bng,
                (origin[0] + 4.6, origin[1] + 1.6, origin[2] + 1.3),
                (origin[0] + 3.4, origin[1] + 0.6, origin[2] + 0.05),
                shot_names[2],
            )
            _screenshot(
                bng,
                (origin[0] - 17.5, origin[1] - 5.5, origin[2] + 1.8),
                (origin[0] - 22.8, origin[1], origin[2] + 1.2),
                shot_names[3],
            )

            # --- the HUD app is discoverable by the game's own scanner ------
            # ui/apps.lua requires domElement + directive (+ appName) and
            # files the app by category; a mod app failing any of that is
            # logged and IGNORED. Asking the scanner itself is the only
            # static-free proof the panel can be added to a HUD layout.
            apps = _lua_json(
                bng,
                "pcall(function() extensions.load('ui_apps') end); "
                "local data = extensions.ui_apps "
                "and extensions.ui_apps.getUIAppsData "
                "and extensions.ui_apps.getUIAppsData() or {}; "
                "local entry = data['hotPotatoTuner']; "
                "return jsonEncode({found = entry ~= nil, "
                "name = entry and entry.name or '', "
                "category = entry and entry.types and entry.types[1] or ''})",
            )
            assert apps.get("found") is True, {
                "detail": "the game's UI app scanner does not see hotPotatoTuner",
                "apps": apps,
            }
            assert apps.get("category") == "ui.apps.categories.utility", apps

            # --- the Add-App browser's OWN cached backend sees it -----------
            # v2.4, the player's report: the app passed the raw scanner but
            # never appeared in the Add App grid. The grid is built from
            # ui_appSelector_general's CACHED appData (invalidated only by
            # mod activate/deactivate/manager-ready — a file drop or Ctrl+R
            # never refreshes it), so THIS is the layer that has to agree.
            tile = _lua_json(
                bng,
                "pcall(function() extensions.load('ui_appSelector_general') end); "
                "local backend = extensions.ui_appSelector_general; "
                "local bundle = backend and backend.getAppData "
                "and backend.getAppData() or {}; "
                "local data = bundle.apps or {}; "
                "local hit = nil; "
                "for _, app in pairs(data) do "
                "if app and (app.appName == 'hotPotatoTuner' "
                "or app.directive == 'hotPotatoTuner') then hit = app end end; "
                "return jsonEncode({found = hit ~= nil, "
                "category = hit and hit.category or '', "
                "aux = hit and hit.isAuxiliary or false})",
            )
            assert tile.get("found") is True, {
                "detail": "the Add-App browser backend's cache does not list "
                "hotPotatoTuner — the grid the player scrolls would not "
                "show it",
                "tile": tile,
            }
            assert tile.get("aux") is not True, tile

            # --- the HUD Layouts list carries the shipped layout ------------
            # v2.4.2, the player's second report: they were scrolling the
            # HUD LAYOUTS list, where an app can never appear. The fix is a
            # whole shipped layout: ui/appLayouts.lua's getAvailableLayouts()
            # re-scans /settings/ui_apps/originalLayouts/ on every call (no
            # cache) and the mod zip overlays that VFS root, so the entry
            # "Hot Potato" must be in the exact list the player scrolls.
            layouts = _lua_json(
                bng,
                "pcall(function() extensions.load('ui_appLayouts') end); "
                "local backend = extensions.ui_appLayouts; "
                "local rows = backend and backend.getAvailableLayouts "
                "and backend.getAvailableLayouts() or {}; "
                "local hit = nil; "
                "for _, row in ipairs(rows) do "
                "if row and row.title == 'Hot Potato' then hit = row end end; "
                "local has_tuner = false; "
                "if hit and hit.apps then for _, app in ipairs(hit.apps) do "
                "if app.appName == 'hotPotatoTuner' then has_tuner = true end "
                "end end; "
                "return jsonEncode({found = hit ~= nil, "
                "layout_type = hit and hit.type or '', "
                "has_tuner = has_tuner, "
                "filename = hit and hit.filename or ''})",
            )
            assert layouts.get("found") is True, {
                "detail": "the HUD Layouts list does not carry the shipped "
                "'Hot Potato' layout — the player's one-click path is dead",
                "layouts": layouts,
            }
            assert layouts.get("layout_type") == "freeroam", layouts
            assert layouts.get("has_tuner") is True, layouts


            # --- pickup: drive onto the medallion ---------------------------
            pad_world = (origin[0], origin[1], origin[2] + 0.6)
            carrier.teleport(pos=pad_world, rot_quat=(0, 0, 0, 1), reset=True)

            # Wait for a STABLE live round: same carrier on two consecutive
            # polls, and capture the stats from the winning poll. The
            # teleport's reset event can land AFTER the position sweep has
            # already given the potato away, so the runtime legitimately
            # plays round_started -> carrier_lost(subject_reset) ->
            # pad_trigger re-pickup within ~25 ms (measured across runs 3-4,
            # 2026-08-29); any single poll — and any read AFTER a successful
            # single poll — can land inside that gap and see carrier == -1.
            stable: dict[str, Any] = {}

            def _live_with_stable_carrier() -> bool:
                stats = _stats(bng)
                live = (
                    stats.get("phase") == "live"
                    and int(stats.get("carrier") or -1) >= 0
                )
                if live and stable.get("carrier") == stats.get("carrier"):
                    stable["stats"] = stats
                    return True
                stable["carrier"] = stats.get("carrier") if live else None
                return False

            _step_until(
                bng,
                _live_with_stable_carrier,
                calls=40,
                note="pad pickup never settled into a live round with a carrier",
            )
            first_stats = stable["stats"]
            carrier_probe = _vehicle_probe(bng, CARRIER_NAME)
            assert carrier_probe.get("ok") is True, carrier_probe
            assert int(first_stats.get("carrier", -1)) == int(carrier_probe["id"]), first_stats

            # The tick loop must be alive in the carrier's VM.
            assert _tick_probe(bng, CARRIER_NAME, "a") is True, (
                "the carrier's VM has no running tick loop"
            )

            # The HUD stats hook: live phase, the right carrier, and the
            # numeric countdown GATED off by default (the hidden fuse is the
            # design; show_countdown is the party-host override).
            hud = _lua_json(
                bng,
                f"return jsonEncode(extensions[{RUNTIME_EXTENSION!r}]"
                ".hotPotatoGetStats())",
            )
            assert hud.get("phase") == "live", hud
            assert int(hud.get("carrier", -1)) == int(first_stats.get("carrier")), hud
            assert float(hud.get("countdown", 0)) == -1, {
                "detail": "the hidden fuse leaked to the HUD", "hud": hud,
            }
            answer = _lua_json(
                bng,
                f"local ok = extensions[{RUNTIME_EXTENSION!r}]"
                ".hotPotatoSetOption('show_countdown', true); "
                "return jsonEncode({ok = ok == true})",
            )
            assert answer == {"ok": True}
            bng.control.step(STEPS_PER_CALL, wait=True)
            hud = _lua_json(
                bng,
                f"return jsonEncode(extensions[{RUNTIME_EXTENSION!r}]"
                ".hotPotatoGetStats())",
            )
            assert float(hud.get("countdown", -1)) > 0, {
                "detail": "show_countdown=true published no fuse seconds",
                "hud": hud,
            }

            # The carried potato, photographed.
            _screenshot(
                bng,
                (float(carrier_probe["x"]) + 9.0, float(carrier_probe["y"]) + 9.0,
                 float(carrier_probe["z"]) + 4.0),
                (float(carrier_probe["x"]), float(carrier_probe["y"]),
                 float(carrier_probe["z"]) + 2.0),
                shot_names[4],
            )

            # --- transfer: a real ram over the impact threshold -------------
            carrier_probe = _vehicle_probe(bng, CARRIER_NAME)
            ram_start = (
                float(carrier_probe["x"]),
                float(carrier_probe["y"]) + 24.0,
                float(carrier_probe["z"]) + 0.4,
            )
            rammer.teleport(pos=ram_start, rot_quat=(0, 0, 0, 1), reset=True)
            bng.control.step(STEPS_PER_CALL, wait=True)
            rammer.control(parkingbrake=0.0, brake=0.0, throttle=1.0)
            rammer.set_velocity(RAM_MPS, 1.0)
            rammer_probe = _vehicle_probe(bng, RAMMER_NAME)
            rammer_id = int(rammer_probe["id"])
            _step_until(
                bng,
                lambda: int(_stats(bng).get("carrier", -1)) == rammer_id,
                calls=60,
                note="the ram never transferred the potato",
            )
            _screenshot(
                bng,
                (float(carrier_probe["x"]) + 15.0, float(carrier_probe["y"]) + 20.0,
                 float(carrier_probe["z"]) + 6.0),
                (float(carrier_probe["x"]), float(carrier_probe["y"]) + 8.0,
                 float(carrier_probe["z"]) + 1.5),
                shot_names[5],
            )

            # Tag-back: the pair is still bumper to bumper, and the potato
            # must STAY with the rammer through the immunity window.
            for _ in range(8):
                bng.control.step(STEPS_PER_CALL, wait=True)
                assert int(_stats(bng).get("carrier", -1)) == rammer_id, (
                    "the potato bounced straight back through the tag-back rules"
                )

            # The tick must have MOVED: alive on the rammer, silent on the
            # passer.
            assert _tick_probe(bng, RAMMER_NAME, "b") is True, (
                "the new carrier's VM has no running tick loop"
            )
            assert _tick_probe(bng, CARRIER_NAME, "c") is not True, (
                "the passer's VM is still ticking after the handoff"
            )

            # --- fuse to zero: the CURRENT carrier detonates ----------------
            _step_until(
                bng,
                lambda: _stats(bng).get("phase") == "boom",
                calls=220,
                note="the shortened fuse never detonated",
            )
            boom_stats = _stats(bng)
            assert int(boom_stats.get("carrier", -1)) == rammer_id, boom_stats

            # The physics has to agree that something violent happened — and
            # it has to be sampled FIRST: the 16 m/s launch is ballistic, so
            # a second of probes and screenshots before this loop measures
            # the wreck near its apex instead (measured: peak 4.9 on the
            # first v2.3 run with the audio probe queued ahead of it).
            peak_speed = 0.0
            blast_anchor: tuple[float, float, float] | None = None
            for _ in range(10):
                bng.control.step(6, wait=True)
                sample = _vehicle_probe(bng, RAMMER_NAME)
                if sample.get("ok"):
                    peak_speed = max(peak_speed, float(sample["speed"]))
                    if blast_anchor is None:
                        # The launch is vertical, so the FIRST sample after
                        # the boom is still over the blast anchor — where the
                        # mash rains down (v2.4 money shot).
                        blast_anchor = (
                            float(sample["x"]), float(sample["y"]),
                            float(sample["z"]),
                        )
            assert peak_speed > 6.0, {
                "detail": "the runtime detonated but the physics never moved the wreck",
                "peak_speed": peak_speed,
            }

            # THE 2026-08-29 AUDIO REPORT, pinned live: the tick loop must be
            # DEAD in the victim's VM once the boom lands. The stop is now
            # mute+stop+cut and the boom phase re-sends it, so by the first
            # post-boom poll the VM has to agree it is off.
            assert _tick_probe(bng, RAMMER_NAME, "boom") is not True, (
                "the fuse audio survived the detonation in the victim's VM"
            )

            # --- the mash flies (v2.4) --------------------------------------
            # The chunks park at authored z -30 under the plaza; during the
            # boom at least one must be posed above grade.
            mash = _lua_json(
                bng,
                f"local prop = scenetree.findObject({PROP_NAME!r}); "
                "local z = -999; "
                "if prop then "
                "for i = 1, 6 do "
                f"local chunk = scenetree.findObject('{MOD_ID}_p' "
                ".. prop:getID() .. '_part_mash_' .. i); "
                "if chunk and chunk.getPosition then "
                "local p = chunk:getPosition(); "
                "if p and p.z > z then z = p.z end end end end; "
                "return jsonEncode({peak = z})",
            )
            assert float(mash.get("peak", -999)) > -1.0, {
                "detail": "no mash chunk rose above grade during the boom",
                "mash": mash,
            }

            # The detonation, photographed while the blast is still burning
            # (fire_seconds gives it a six-second window).
            boom_probe = _vehicle_probe(bng, RAMMER_NAME)
            if boom_probe.get("ok"):
                _screenshot(
                    bng,
                    (float(boom_probe["x"]) + 11.0, float(boom_probe["y"]) - 11.0,
                     float(boom_probe["z"]) + 5.0),
                    (float(boom_probe["x"]), float(boom_probe["y"]),
                     float(boom_probe["z"]) + 2.0),
                    shot_names[6],
                )

            # The splatter, photographed AT the blast anchor once the chunks
            # have rained down and settled proud of the tiles (v2.4 critic:
            # the first cut's fountain flew over the boom camera and the
            # money shot showed only shadow smudges).
            if blast_anchor is not None:
                bng.control.step(STEPS_PER_CALL * 4, wait=True)
                _screenshot(
                    bng,
                    (blast_anchor[0] + 9.0, blast_anchor[1] - 9.0,
                     blast_anchor[2] + 4.5),
                    (blast_anchor[0], blast_anchor[1], blast_anchor[2] + 0.5),
                    shot_names[7],
                )

            # --- the fire dies into the RETURN FLIGHT, then idle ------------
            # v2.4: the boom no longer teleports the potato onto the nearest
            # car — it flies home (up, across, down onto the perch) and the
            # next round arms only at the medallion.
            _step_until(
                bng,
                lambda: _stats(bng).get("phase") in ("return", "idle"),
                calls=160,
                note="the boom never handed over to the return flight",
            )
            _step_until(
                bng,
                lambda: _stats(bng).get("phase") == "idle",
                calls=200,
                note="the return flight never settled back to idle",
            )
            rammer.teleport(pos=pad_world, rot_quat=(0, 0, 0, 1), reset=True)
            _step_until(
                bng,
                lambda: _stats(bng).get("phase") == "live"
                and int(_stats(bng).get("carrier", -1)) == rammer_id,
                calls=40,
                note="a detonated car could not start the next round — the "
                "single-player lockout is back",
            )

            # --- delete the prop mid-round: the tick must die with it -------
            assert _tick_probe(bng, RAMMER_NAME, "d") is True
            _lua_json(
                bng,
                f"local prop = scenetree.findObject({PROP_NAME!r}); "
                "if prop then prop:delete() end; "
                "return jsonEncode({ok = true})",
            )
            bng.control.step(STEPS_PER_CALL * 2, wait=True)
            assert _tick_probe(bng, RAMMER_NAME, "e") is not True, (
                "the tick outlived the prop — the exact bug the player filmed"
            )

            # Restore the shipped options for whoever uses this profile next.
            _lua_json(
                bng,
                f"local extension = extensions[{RUNTIME_EXTENSION!r}]; "
                "if extension then extension.hotPotatoResetOptions() end; "
                "return jsonEncode({ok = true})",
            )

            # Pull the screenshots out of the profile before cleanup.
            for name in shot_names:
                source = user / "screenshots" / f"{name}.png"
                if source.is_file():
                    shutil.copyfile(source, shot_dir / f"{name}.png")
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
                    files=(installed_zip, settings_file, *profile_shots),
                    empty_directories=(scenario_directory,),
                )

    records, issues = _runtime_log_records(log_path, log_start)
    events = [str(record["event"]) for record in records]
    passes = [record for record in records if record.get("event") == "potato_passed"]
    reasons = [str(record.get("reason")) for record in passes]
    summary = {
        "events": events,
        "pass_reasons": reasons,
        "log_issues": issues,
        "shots": sorted(path.name for path in shot_dir.glob("*.png")),
    }
    (tmp_path / "runtime_records.json").write_text(json.dumps(records, indent=1), encoding="utf-8")

    for required in ("prop_registered", "round_started", "detonation", "subject_launched"):
        assert required in events, {"missing": required, **summary}
    assert "impact" in reasons, {
        "detail": "no impact transfer was recorded — the ram did not pass the potato",
        **summary,
    }
    # The sweep ("pad") and the secondary trigger path ("pad_trigger") race
    # by design — the live run has recorded both winning. Either is a real
    # medallion pickup.
    assert sum(1 for reason in reasons if reason in ("pad", "pad_trigger")) >= 2, {
        "detail": "the post-boom pad pickup is missing from the log",
        **summary,
    }
    assert "prop_unregistered" in events, {"detail": "prop deletion never tore down", **summary}
    assert not issues, {"detail": "runtime logged errors", **summary}
