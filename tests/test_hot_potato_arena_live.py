"""Live SMOKE for the Gateway Skillet arena on the sentinel-isolated profile.

Not G1-G6 (those are the integration round). This installs the exact locked
arena dist zip AND the exact locked Hot Potato dist zip, loads the SHIPPED
scenario from inside the zip through the game's own scenario list, and asserts:

- the runtime registers the prefab Dispenser (part_count 7),
- the scenario-owned extension booted and the four boot options read back
  through hotPotatoGetOptions,
- obstacle registration status (registered when the runtime hook exists),
- every prefab static + every vehicle of the census + every emitter node is
  present (counts derive from the generator, never typed in),
- every arena material resolves as a Material (the NO MATERIAL regression),
- the drive surface reads right: spout throats at grade, the crest at +6.5 m,
  a butter pool +0.02 m - which also pins the rotationMatrix convention,
- a pad pickup starts a live round,
- one gate geyser ON window pops a car (vertical velocity delta),
- the runtime and the arena log no errors,

and captures normal-exposure screenshots into HOT_POTATO_ARENA_SHOT_DIR.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import pytest
from beamngpy import BeamNGpy

from examples.hot_potato_arena import build_distribution as arena_dist
from examples.hot_potato_arena import sync_scenario_outputs as sync
from tests.live_support import (
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    namespace_conflicts,
    require_confined_profile_target,
    reserve_loopback_ports,
)

MOD_ID = sync.MOD_ID
HOT_POTATO_ID = "ericrolph_hot_potato"
HOT_POTATO_ZIP = "hot_potato_ericrolph.zip"
RUNTIME_EXTENSION = "ericrolph__hot__potato_runtime"
ARENA_EXTENSION = f"scenario_{MOD_ID}"
RUNTIME_LOG_TAG = "ERICROLPH_HOT_POTATO_RUNTIME"
ARENA_LOG_TAG = "ERICROLPH_HOT_POTATO_ARENA"
LIVE_TEST_TAG = "GIANT_PROPS_LIVE_TEST"
PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MATERIALS = tuple(
    f"{MOD_ID}_{family}"
    for family in ("cast_iron", "butter", "salt", "skillet_steel", "handle_wood")
)
STEPS_PER_CALL = 15
C = sync.CENTER


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the arena live smoke"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the arena live smoke requires a sentinel-isolated profile")
    return home, user, resolved_binary


def _locked_payload(archive: Path, lock_path: Path) -> bytes:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    payload = archive.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == lock["sha256"], (
        f"{archive.name} does not match its lock; rebuild before testing it"
    )
    return payload


def _lua_json(bng: BeamNGpy, command: str) -> dict[str, Any]:
    payload = bng.control.queue_lua_command(command, response=True)
    decoded = json.loads(payload)
    assert isinstance(decoded, dict), decoded
    return decoded


def _arena_state(bng: BeamNGpy) -> dict[str, Any]:
    return _lua_json(
        bng,
        f"local ext = rawget(extensions, {ARENA_EXTENSION!r}); "
        "if not ext then return jsonEncode({loaded = false}) end; "
        "local s = ext.getSystemState(); s.loaded = true; return jsonEncode(s)",
    )


def _runtime_state(bng: BeamNGpy) -> dict[str, Any]:
    return _lua_json(
        bng,
        f"local extension = rawget(extensions, {RUNTIME_EXTENSION!r}); "
        f"local prop = scenetree.findObject({sync.DISPENSER_NAME!r}); "
        "if not extension then return jsonEncode({loaded = false}) end; "
        "if not prop then return jsonEncode({loaded = true, registered = false}) end; "
        "local state = extension.getSystemState(prop:getID()); "
        "state.loaded = true; return jsonEncode(state)",
    )


def _stats(bng: BeamNGpy) -> dict[str, Any]:
    return _lua_json(
        bng, f"return jsonEncode(extensions[{RUNTIME_EXTENSION!r}].hotPotatoGetStats())"
    )


def _vehicle_probe(bng: BeamNGpy, scene_name: str) -> dict[str, Any]:
    return _lua_json(
        bng,
        f"local subject = scenetree.findObject({scene_name!r}); "
        "if not subject then return jsonEncode({ok = false}) end; "
        "local position = subject:getPosition(); local velocity = subject:getVelocity(); "
        "return jsonEncode({ok = true, id = subject:getID(), x = position.x, y = position.y, "
        "z = position.z, vz = velocity.z, speed = velocity:length()})",
    )


def _surface_z(bng: BeamNGpy, x: float, y: float) -> float:
    answer = _lua_json(
        bng,
        f"local rayStart = vec3({x}, {y}, 200); "
        "local d = castRayStatic(rayStart, vec3(0, 0, -1), 400); "
        "return jsonEncode({surface_z = rayStart.z - d, distance = d})",
    )
    assert 0.0 < float(answer["distance"]) < 400.0, answer
    return float(answer["surface_z"])


def _screenshot(bng: BeamNGpy, position, target, name: str) -> None:
    """Normal-exposure in-game screenshot from the free camera."""

    px, py, pz = position
    tx, ty, tz = target
    _lua_json(
        bng,
        "commands.setFreeCamera(); "
        f"local eye = vec3({px}, {py}, {pz}); local aim = vec3({tx}, {ty}, {tz}); "
        "local rotation = quatFromDir((aim - eye):normalized(), vec3(0, 0, 1)); "
        "core_camera.setPosRot(0, eye.x, eye.y, eye.z, rotation.x, rotation.y, rotation.z, rotation.w); "
        "return jsonEncode({ok = true})",
    )
    bng.control.step(30, wait=True)
    _lua_json(
        bng,
        f"screenshot.doScreenshot(nil, nil, 'screenshots/{name}', 'png'); return jsonEncode({{ok = true}})",
    )
    bng.control.step(15, wait=True)


def _count_events(
    log_path: Path, tag: str, event: str, field: str | None = None, value: str | None = None
) -> int:
    """How many JSON records of `tag` carry `event` (and optionally field == value) in this process's log."""

    total = 0
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if tag not in line or f'"event":"{event}"' not in line:
            continue
        if (
            field is not None
            and f'"{field}":"{value}"' not in line
            and f'"{field}":{value}' not in line
        ):
            continue
        total += 1
    return total


def _band_ratio(frame: Path, cx: int, cy: int, radius: int) -> float:
    """Row/column gradient ratio inside a disc (the round-3 critic's metric)."""

    import numpy as np
    from PIL import Image
    from scipy.ndimage import binary_erosion

    rgb = np.asarray(Image.open(frame).convert("RGB"), dtype=np.float32)
    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    yy, xx = np.mgrid[0 : luma.shape[0], 0 : luma.shape[1]]
    mask = binary_erosion((xx - cx) ** 2 + (yy - cy) ** 2 <= radius * radius, iterations=2)
    dy = np.abs(luma[1:, :] - luma[:-1, :])
    my = mask[1:, :] & mask[:-1, :]
    dx = np.abs(luma[:, 1:] - luma[:, :-1])
    mx = mask[:, 1:] & mask[:, :-1]
    return float(dy[my].mean() / max(dx[mx].mean(), 1e-6))


def _step_until(bng: BeamNGpy, predicate, *, calls: int, note: str) -> int:
    for index in range(calls):
        if predicate():
            return index
        bng.control.step(STEPS_PER_CALL, wait=True)
    raise AssertionError(f"condition never held within {calls} step calls: {note}")


def _log_records(log_path: Path, start_marker: str) -> tuple[list[dict], list[str]]:
    """Every runtime/arena record of THIS process's log.

    BeamNG starts a fresh beamng.log per process, and the arena boots inside
    scenario load - before any marker the test can place - so the whole file
    is parsed; the marker must still be present, which proves the file belongs
    to this run and not to a previous session.
    """

    records: list[dict] = []
    issues: list[str] = []
    marker_seen = False
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if start_marker in line:
            marker_seen = True
            continue
        if RUNTIME_LOG_TAG not in line and ARENA_LOG_TAG not in line:
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
            record["_tag"] = ARENA_LOG_TAG if ARENA_LOG_TAG in line else RUNTIME_LOG_TAG
            records.append(record)
    if not marker_seen:
        issues.append(f"start marker {start_marker} not found in {log_path}")
    return records, issues


@pytest.mark.beamng_live
def test_arena_scenario_smoke(tmp_path: Path) -> None:
    home, user, binary = _configured_runtime()
    handoff = sync.read_handoff()
    static_names = [str(instance["name"]) for instance in handoff["instances"]]
    vehicle_names = [entry["name"] for entry in sync.vehicle_layout()]
    emitter_names = [e["name"] for site in sync.geyser_layout(handoff) for e in site["emitters"]]
    gate = sync.geyser_layout(handoff)[0]

    arena_dir = arena_dist.DEFAULT_OUTPUT_DIR
    arena_payload = _locked_payload(
        arena_dir / arena_dist.ZIP_NAME, arena_dir / arena_dist.LOCK_NAME
    )
    hp_dir = PACK_ROOT / "hot_potato" / "dist"
    hp_payload = _locked_payload(hp_dir / HOT_POTATO_ZIP, hp_dir / f"{HOT_POTATO_ID}.lock.json")

    shot_dir = Path(os.getenv("HOT_POTATO_ARENA_SHOT_DIR", str(tmp_path / "shots")))
    shot_dir.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:10]
    installed_hp = require_confined_profile_target(
        user, Path("mods") / f"arena_smoke_hp_{suffix}.zip"
    )
    installed_arena = require_confined_profile_target(
        user, Path("mods") / f"arena_smoke_arena_{suffix}.zip"
    )
    settings_file = user / "settings" / f"{HOT_POTATO_ID}.json"
    snapshot_file = user / "settings" / f"{MOD_ID}.snapshot.json"
    # A previous visit that DIED (Alt-F4) leaves the arena's snapshot file and
    # its values persisted in the runtime's settings. The planted state: the
    # player had ai_enabled ON and arena_magnet_enabled OFF; the dead visit
    # left the magnet ON (the arena's dirt) and ai ON (== the player's own
    # value). The boot must hand the magnet back before it writes anything and
    # leave ai alone. Later the smoke flips ai_enabled OFF mid-mission through
    # hotPotatoSetOption exactly as the HUD tuner does: that value is the
    # player's and must survive restart and exit (critic r3 fix 2).
    # Serial 53 added a fifth boot key, oob_burn_multiplier: the runtime ships
    # it at 1.0 = OFF and the arena switches it to 3.0, so it is always a write
    # and always a hand-back. The planted crash leaves it at the arena's 3.0
    # (the dead visit's dirt) with the player's 1.0 in the snapshot file.
    crash_player_values = {
        "arena_radius_m": 91.4,
        "arena_enabled": True,
        "ai_enabled": True,
        "arena_magnet_enabled": False,
        "oob_burn_multiplier": 1.0,
    }
    crash_dirty_settings = {
        "ai_enabled": True,
        "arena_magnet_enabled": True,
        "arena_enabled": True,
        "oob_burn_multiplier": 3.0,
    }
    arena_values = {
        "arena_radius_m": 91.4,
        "arena_enabled": True,
        "ai_enabled": True,
        "arena_magnet_enabled": True,
        "oob_burn_multiplier": 3.0,
    }

    def _handback_keys(current: dict[str, Any], snap: dict[str, Any]) -> list[str]:
        """The shipped rule: current != snapshot AND current == the arena's value."""

        return [
            k
            for k in sync.BOOT_OPTION_KEYS
            if current.get(k) != snap.get(k) and current.get(k) == arena_values[k]
        ]

    shot_names = [
        f"arena_overview_{suffix}",
        f"arena_bowl_{suffix}",
        f"arena_spout_{suffix}",
        f"arena_handle_{suffix}",
        f"arena_round_{suffix}",
        f"arena_geyser_{suffix}",
        f"arena_butter_{suffix}",
        f"arena_farfield_{suffix}",
        *(f"arena_farfield_{suffix}_{i}" for i in range(2, 7)),
    ]
    profile_shots = tuple(user / "screenshots" / f"{name}.png" for name in shot_names)
    # B5 (2026-09-10): the arena lives ON the level now, so the engine's mesh cache for its
    # shapes sits under the level id, not under stock gridmap_v2.
    mesh_cache = user / "temp" / Path(sync.SHAPES_RELATIVE)
    log_path = user / "beamng.log"
    log_start = f"arena_smoke_start_{suffix}"
    report: dict[str, Any] = {"suffix": suffix}

    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(1))
        (tcom_port,) = reservation.ports
        conflicts = [
            c
            for c in namespace_conflicts(user, HOT_POTATO_ID, installed_hp)
            if Path(c) != installed_arena
        ]
        if conflicts:
            pytest.fail(f"competing {HOT_POTATO_ID} archives in the isolated profile: {conflicts}")
        stale = (
            [
                str(p)
                for p in (user / "mods").glob("*.zip")
                if "arena" in p.name.casefold() and p not in (installed_hp, installed_arena)
            ]
            if (user / "mods").is_dir()
            else []
        )
        if stale:
            pytest.fail(f"stale arena archives in the isolated profile: {stale}")
        installed_hp.parent.mkdir(parents=True, exist_ok=True)
        for target, payload in ((installed_hp, hp_payload), (installed_arena, arena_payload)):
            with target.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        # Plant the crash leftovers (both confined to the sentinel profile and
        # removed at cleanup). A pre-existing settings file would mean a dirty
        # profile: refuse rather than overwrite.
        if settings_file.exists() or snapshot_file.exists():
            pytest.fail(
                f"stale Hot Potato settings in the isolated profile: {settings_file}, {snapshot_file}"
            )
        require_confined_profile_target(user, Path("settings") / settings_file.name)
        require_confined_profile_target(user, Path("settings") / snapshot_file.name)
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(
            json.dumps(crash_dirty_settings) + "\n", encoding="utf-8", newline="\n"
        )
        snapshot_file.write_text(
            json.dumps({"schema": 1, "mod": MOD_ID, "options": crash_player_values}) + "\n",
            encoding="utf-8",
            newline="\n",
        )

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
        owned_process: Any | None = None
        timer: threading.Timer | None = None
        scenario = None
        try:

            def watchdog() -> None:
                process = bng.process
                if process is not None and process.poll() is None:
                    process.terminate()

            timer = threading.Timer(900.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)

            # --- the SHIPPED scenario, found through the game's own list ---
            listed = bng.scenario.get_scenarios([sync.LEVEL_ID])  # B5: listed under the level
            candidates = [
                s for level in listed.values() for s in level if s.path and MOD_ID in str(s.path)
            ]
            assert len(candidates) == 1, {
                "detail": "the zipped scenario is not in the game's scenario list",
                "paths": [str(s.path) for level in listed.values() for s in level],
            }
            scenario = candidates[0]
            report["scenario_path"] = str(scenario.path)
            bng.control.pause()
            bng.scenario.load(
                scenario,
                precompile_shaders=False,
                connect_player_vehicle=False,
                connect_existing_vehicles=False,
            )
            bng.scenario.start()
            bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
            bng.control.pause()
            bng.control.step(3, wait=True)
            marker = _lua_json(
                bng, f"log('I', {LIVE_TEST_TAG!r}, {log_start!r}); return jsonEncode({{ok = true}})"
            )
            assert marker == {"ok": True}

            # --- runtime registers the prefab Dispenser -------------------
            state: dict[str, Any] = {}
            for _ in range(40):
                state = _runtime_state(bng)
                if state.get("registered"):
                    break
                bng.control.step(STEPS_PER_CALL, wait=True)
            assert state.get("loaded") is True and state.get("registered") is True, state
            assert state["part_count"] == 7, state
            report["runtime"] = {"registered": True, "part_count": state["part_count"]}

            # --- the scenario extension booted ----------------------------
            arena: dict[str, Any] = {}
            for _ in range(40):
                arena = _arena_state(bng)
                if arena.get("loaded") and arena.get("booted"):
                    break
                bng.control.step(STEPS_PER_CALL, wait=True)
            assert arena.get("loaded") is True, {
                "detail": "scenario extension not loaded",
                "arena": arena,
            }
            assert arena.get("booted") is True, arena
            assert arena.get("mp") is False, arena
            boot = arena.get("boot") or []
            assert [row["key"] for row in boot] == [
                "arena_radius_m",
                "arena_enabled",
                "ai_enabled",
                "arena_magnet_enabled",
                "oob_burn_multiplier",
            ], boot
            assert [row["key"] for row in boot] == list(sync.BOOT_OPTION_KEYS), boot
            assert all(row["ok"] is True for row in boot), boot
            assert arena["obstacles"] in ("registered", "unavailable"), arena
            report["arena_boot"] = {
                "boot": boot,
                "obstacles": arena["obstacles"],
                "obstacle_count": arena.get("obstacle_count"),
                "wait": arena.get("boot_wait"),
            }
            hook = _lua_json(
                bng,
                f"local ext = extensions[{RUNTIME_EXTENSION!r}]; "
                "local has = type(ext.hotPotatoRegisterObstacles) == 'function'; "
                "local got = has and type(ext.hotPotatoGetObstacles) == 'function' "
                "and ext.hotPotatoGetObstacles() or nil; "
                "return jsonEncode({hook = has, obstacles = got})",
            )
            report["obstacle_hook"] = hook
            if hook.get("hook"):
                assert arena["obstacles"] == "registered", arena
                got = hook.get("obstacles") or {}
                if isinstance(got, dict) and "count" in got:
                    assert int(got["count"]) == int(arena["obstacle_count"]), got
                # Two-radius contract (serial 55): the echo carries rp, so
                # assert what LANDED, not just what was sent. The runtime
                # refuses the whole call on a bad rp, so a registered set that
                # echoes 42 sane entries is the proof the contract was met.
                entries = got.get("entries") if isinstance(got, dict) else None
                if entries:
                    rows = list(entries.values()) if isinstance(entries, dict) else list(entries)
                    handoff_rp = {
                        (round(float(o["x"]), 3), round(float(o["y"]), 3)): float(o["rp"])
                        for o in handoff["obstacles"]
                    }
                    report["obstacle_rp"] = {
                        "count": len(rows),
                        "posts": sorted({float(r["rp"]) for r in rows if float(r["rp"]) > 0.1}),
                        "at_floor": sum(1 for r in rows if float(r["rp"]) == 0.1),
                    }
                    assert len(rows) == len(handoff["obstacles"]) == 46, report["obstacle_rp"]
                    assert all(0.1 <= float(r["rp"]) <= float(r["r"]) for r in rows), report[
                        "obstacle_rp"
                    ]
                    assert report["obstacle_rp"]["posts"] == [1.2, 1.5, 2.121, 2.321], report[
                        "obstacle_rp"
                    ]
                    # Every echoed rp is the handoff's measured value.
                    for row in rows:
                        key = (round(float(row["x"]), 3), round(float(row["y"]), 3))
                        assert float(row["rp"]) == pytest.approx(handoff_rp[key]), (key, row)

            # --- the four options read back -------------------------------
            options = _lua_json(
                bng, f"return jsonEncode(extensions[{RUNTIME_EXTENSION!r}].hotPotatoGetOptions())"
            )
            assert float(options["arena_radius_m"]) == pytest.approx(91.4), options
            assert options["arena_enabled"] is True, options
            assert options["ai_enabled"] is True, options
            assert options["arena_magnet_enabled"] is True, options
            # Serial 53: the OOB burn penalty, switched on by the arena.
            assert float(options["oob_burn_multiplier"]) == pytest.approx(3.0), options
            report["options"] = {k: options[k] for k in sync.BOOT_OPTION_KEYS}
            # The player's values BEFORE the boot wrote them (critique fix 3):
            # a fresh sentinel profile carries the shipped defaults, so the
            # arena changed exactly ai_enabled (false -> true).
            snapshot = {k: arena["snapshot"].get(k) for k in sync.BOOT_OPTION_KEYS}
            report["snapshot"] = snapshot
            report["crash_recovery"] = {
                "recovered_calls": arena.get("recovered_calls"),
                "snapshot_file_written": arena.get("snapshot_file_written"),
                "snapshot_file_exists": snapshot_file.is_file(),
            }
            # Crash recovery (critique r2, fix 2 / r3 fix 2): the planted
            # file's magnet AND oob values were handed back FIRST (two calls:
            # both were the arena's dirt), ai was left alone (== the player's),
            # then the player's values were snapshotted afresh.
            assert int(arena.get("recovered_calls", -1)) == 2, report["crash_recovery"]
            assert snapshot == crash_player_values, snapshot
            assert arena.get("snapshot_file_written") is True and snapshot_file.is_file(), report[
                "crash_recovery"
            ]
            on_disk = json.loads(snapshot_file.read_text(encoding="utf-8"))
            assert on_disk.get("options") == crash_player_values, on_disk
            changed_keys = _handback_keys(options, snapshot)
            report["changed_keys"] = changed_keys
            assert changed_keys == ["arena_magnet_enabled", "oob_burn_multiplier"], changed_keys

            # --- forceDetail read-back on every static (critic r3 fix 1) ---
            # The records carry no forceDetail; the class default must read
            # -1 (auto) on all of them - not the uninitialised garbage the
            # string-typed field produced.
            force_detail = _lua_json(
                bng,
                "local out = {}; "
                + " ".join(
                    f"do local o = scenetree.findObject({name!r}); "
                    f"out[{name!r}] = o and tostring(o:getField('forceDetail', 0)) or 'MISSING' end "
                    for name in static_names
                )
                + "return jsonEncode(out)",
            )
            report["force_detail_readback"] = force_detail
            assert all(v == "-1" for v in force_detail.values()), {
                k: v for k, v in force_detail.items() if v != "-1"
            }

            # --- census: statics, vehicles, emitters ------------------------
            def _classes(names: list[str]) -> dict[str, str]:
                return _lua_json(
                    bng,
                    "local out = {}; "
                    + " ".join(
                        f"do local o = scenetree.findObject({name!r}); "
                        f"out[{name!r}] = o and o:getClassName() or 'MISSING' end "
                        for name in names
                    )
                    + "return jsonEncode(out)",
                )

            statics = _classes(static_names)
            assert all(v == "TSStatic" for v in statics.values()), {
                k: v for k, v in statics.items() if v != "TSStatic"
            }
            emitters = _classes(emitter_names)
            assert all(v == "ParticleEmitterNode" for v in emitters.values()), emitters
            # Wisps are the always-on OFF tell (fix 5); the curtain waits for
            # its window. Read once the extension has resolved every site.
            _step_until(
                bng,
                lambda: all(
                    int(g["emitters_found"]) == int(g["emitters_expected"])
                    for g in _arena_state(bng)["geysers"]
                ),
                calls=20,
                note="the extension never resolved every emitter node",
            )
            wisp_names = [e["name"] for site in sync.geyser_layout(handoff) for e in site["wisp"]]
            active = _lua_json(
                bng,
                "local out = {}; "
                + " ".join(
                    f"do local o = scenetree.findObject({name!r}); "
                    f"out[{name!r}] = o and tostring(o:getField('active', 0)) or 'MISSING' end "
                    for name in wisp_names
                )
                + "return jsonEncode(out)",
            )
            report["wisps_active"] = active
            assert all(str(v).lower() in ("1", "true") for v in active.values()), active
            vehicles = _classes(vehicle_names)
            assert all(v == "BeamNGVehicle" for v in vehicles.values()), {
                k: v for k, v in vehicles.items() if v != "BeamNGVehicle"
            }
            roster = _lua_json(
                bng,
                "local all = getAllVehicles(); return jsonEncode({count = #all})",
            )
            assert int(roster["count"]) == len(vehicle_names) == 23, roster
            report["census"] = {
                "statics": len(statics),
                "emitters": len(emitters),
                "vehicles": int(roster["count"]),
            }

            # --- materials resolve (the NO MATERIAL regression) -----------
            materials = _lua_json(
                bng,
                "local out = {}; "
                + " ".join(
                    f"do local m = scenetree.findObject({name!r}); "
                    f"out[{name!r}] = m and m:getClassName() or 'MISSING' end "
                    for name in MATERIALS
                )
                + "return jsonEncode(out)",
            )
            for name in MATERIALS:
                assert str(materials.get(name)).lower() == "material", {
                    "detail": "an arena material did not resolve - orange",
                    "materials": materials,
                }
            report["materials"] = materials

            # --- surface truth (pins the rotationMatrix convention) -------
            # Bearings sit 1.5 degrees off the trim ring's 7.5-degree rivet
            # pitch so a ray never lands on an 18 mm dome (run 1 did, and the
            # identity-placed trim ring's rivets sat OVER a mirrored spout).
            spout_e = sync.bearing_point(61.5, sync.ARENA_RADIUS_M)
            spout_w = sync.bearing_point(241.5, sync.ARENA_RADIUS_M)
            mirror = sync.bearing_point(298.5, sync.ARENA_RADIUS_M)
            north = sync.bearing_point(1.5, sync.ARENA_RADIUS_M)
            pool_1 = (883.0, -222.842)
            plaza = sync.bearing_point(90.0, 40.0)
            surfaces = {
                "spout_e_throat": _surface_z(bng, *spout_e),
                "spout_w_throat": _surface_z(bng, *spout_w),
                "crest_300": _surface_z(bng, *mirror),
                "crest_0": _surface_z(bng, *north),
                "butter_pool_1": _surface_z(bng, *pool_1),
                "plaza_r40": _surface_z(bng, *plaza),
                # Stock convention witnesses (site-clearance gate, erratum 3):
                # p_gm_interzone_structure10 is a 90-degree-rotated cube stack
                # at (668, -244). Row-major world = R*local puts its cubes at
                # x 668..724 / y -244..-228 (132 m from C); the transposed
                # convention puts them at x 616..668 / y -260..-244 (182 m).
                "structure10_standard_footprint": _surface_z(bng, 700.0, -236.0),
                "structure10_transposed_footprint": _surface_z(bng, 640.0, -252.0),
            }
            report["surfaces"] = surfaces
            report["rotation_convention"] = (
                "row-major world = R*local"
                if surfaces["structure10_standard_footprint"] > 101.0
                else "transposed (rows are local axes)"
                if surfaces["structure10_transposed_footprint"] > 101.0
                else "undetermined"
            )
            # Player heading: the vehicle's forward vector must point at the
            # pad (the same convention places every car and every wall arc).
            heading = _lua_json(
                bng,
                f"local v = scenetree.findObject({sync.PLAYER_NAME!r}); "
                "local d = v:getDirectionVector(); local p = v:getPosition(); "
                "return jsonEncode({dx = d.x, dy = d.y, px = p.x, py = p.y})",
            )
            to_pad = (C[0] - float(heading["px"]), C[1] - float(heading["py"]))
            norm = (to_pad[0] ** 2 + to_pad[1] ** 2) ** 0.5
            heading_dot = (
                float(heading["dx"]) * to_pad[0] + float(heading["dy"]) * to_pad[1]
            ) / norm
            report["player_heading_dot_to_pad"] = heading_dot
            assert report["rotation_convention"] == "transposed (rows are local axes)", report
            crest_z = float(handoff["center_world"][2]) + float(handoff["crest_z_m"])
            report["crest_z_expected"] = crest_z
            assert surfaces["spout_e_throat"] < 100.6, surfaces
            assert surfaces["spout_w_throat"] < 100.6, surfaces
            assert abs(surfaces["crest_300"] - crest_z) < 0.3, surfaces
            assert abs(surfaces["crest_0"] - crest_z) < 0.3, surfaces
            # Geometry v3.2: the floor skin is a driven, colliding surface at
            # +50 mm (feathered to the 12 mm datum at r 76); the hazard plates
            # ride on it (+20 mm on the lift). Both come from the handoff.
            skin_lift = float((handoff.get("floor_skin") or {}).get("plate_instance_lift_m", 0.0))
            report["floor_skin_lift_m"] = skin_lift
            assert abs(surfaces["plaza_r40"] - (100.0 + skin_lift)) < 0.02, surfaces
            assert 100.0 + skin_lift <= surfaces["butter_pool_1"] < 100.0 + skin_lift + 0.05, (
                surfaces
            )
            assert heading_dot > 0.98, heading

            # --- screenshots ----------------------------------------------
            _screenshot(
                bng,
                (C[0] + 150.0, C[1] - 170.0, C[2] + 95.0),
                (C[0], C[1], C[2] + 8.0),
                shot_names[0],
            )
            _screenshot(
                bng,
                (C[0] + 52.0, C[1] - 30.0, C[2] + 1.7),
                (C[0], C[1], C[2] + 14.0),
                shot_names[1],
            )
            throat_eye = sync.bearing_point(60.0, 130.0)
            throat_aim = sync.bearing_point(60.0, 70.0)
            _screenshot(bng, (*throat_eye, C[2] + 2.5), (*throat_aim, C[2] + 2.0), shot_names[2])
            _screenshot(
                bng,
                (C[0] + 70.0, C[1] - 95.0, C[2] + 24.0),
                (C[0], C[1] - 45.0, C[2] + 4.0),
                shot_names[3],
            )
            _screenshot(
                bng,
                (883.0 + 14.0, -222.842 - 10.0, C[2] + 4.0),
                (883.0, -222.842, C[2] + 0.5),
                shot_names[6],
            )
            # The streak measurement (geometry v3 floor LOD): the bowl from
            # ~300 m up, past the floor skin's nominal far-detail switch
            # (~126 m at the smoke's 1280x720 / 65 deg; 188.9 m at 1080p).
            # Six consecutive frames go through the critic's band metric
            # below and are RECORDED (min/max), not gated: whether the far
            # detail actually engages is an open G1/G6 item (see the test's
            # tail and the report).
            far_eye = (C[0], C[1] - 60.0, C[2] + 300.0)
            far_aim = (C[0], C[1], C[2])
            far_names = [f"arena_farfield_{suffix}"] + [
                f"arena_farfield_{suffix}_{i}" for i in range(2, 7)
            ]
            for name in far_names:
                _screenshot(bng, far_eye, far_aim, name)
            report["floor_lod"] = handoff["shapes"]["floor_skin_quadrant"].get("lod")

            # --- pad pickup starts a round --------------------------------
            # AI off for determinism from here (the boot already proved it on).
            answer = _lua_json(
                bng,
                f"return jsonEncode({{ok = extensions[{RUNTIME_EXTENSION!r}]"
                ".hotPotatoSetOption('ai_enabled', false) == true})",
            )
            assert answer == {"ok": True}
            origin = state["origin"]
            pad = (float(origin[0]), float(origin[1]), float(origin[2]) + 0.6)
            assert bng.vehicles.teleport(sync.PLAYER_NAME, pad, (0, 0, 0, 1), reset=True) is True
            player = _vehicle_probe(bng, sync.PLAYER_NAME)
            assert player.get("ok") is True, player
            stable: dict[str, Any] = {}

            def _live_with_stable_carrier() -> bool:
                stats = _stats(bng)
                live = stats.get("phase") == "live" and int(stats.get("carrier") or -1) >= 0
                if live and stable.get("carrier") == stats.get("carrier"):
                    stable["stats"] = stats
                    return True
                stable["carrier"] = stats.get("carrier") if live else None
                return False

            _step_until(
                bng, _live_with_stable_carrier, calls=40, note="pad pickup never started a round"
            )
            round_stats = stable["stats"]
            assert int(round_stats["carrier"]) == int(player["id"]), round_stats
            # R-1 (critique fix 4): the runtime's subject filter (serial >= 45)
            # must count the six cars and exclude every breakable prop.
            prop_count = sum(1 for e in sync.vehicle_layout(handoff) if e["role"] == "prop")
            car_count = sum(
                1 for e in sync.vehicle_layout(handoff) if e["role"] in ("player", "ai")
            )
            report["round"] = {
                "phase": round_stats["phase"],
                "carrier_is_player": True,
                "field": round_stats.get("field"),
                "props_excluded": round_stats.get("props_excluded"),
            }
            assert int(round_stats.get("field", -1)) == car_count == 6, report["round"]
            assert int(round_stats.get("props_excluded", -1)) == prop_count == 16, report["round"]
            arena = _arena_state(bng)
            assert arena["valve"]["in_round"] is True, arena["valve"]
            _screenshot(
                bng,
                (pad[0] + 16.0, pad[1] - 14.0, pad[2] + 6.0),
                (pad[0], pad[1], pad[2] + 2.0),
                shot_names[4],
            )

            # --- one geyser ON window pops a MOVING car (critique fix 1) ---
            # The pop is a velocity ADD (scale 1): a car rolling through the
            # gate at ~8 m/s must keep its horizontal speed across the pop
            # frame within 10 % and gain vertical speed in the same frame.
            strip = (float(gate["cx"]), float(gate["cy"]), C[2] + 0.5)
            run_up = (strip[0], strip[1] - 12.0, strip[2])

            def _gate_on() -> bool:
                return bool(_arena_state(bng)["geysers"][0]["on"])

            _step_until(bng, lambda: not _gate_on(), calls=40, note="gate never went OFF")
            # Facing +Y (nose = local -Y, so yaw 180 degrees), brakes released.
            assert bng.vehicles.teleport(sync.PLAYER_NAME, run_up, (0, 0, 1, 0), reset=True) is True
            player_vehicle = bng.vehicles.get_current()[sync.PLAYER_NAME]
            player_vehicle.connect(bng)
            bng.control.step(STEPS_PER_CALL, wait=True)
            player_vehicle.control(parkingbrake=0.0, brake=0.0, throttle=0.0)
            before = _arena_state(bng)["geysers"][0]
            _step_until(bng, _gate_on, calls=60, note="gate never went ON")
            player_vehicle.set_velocity(8.0, 0.5)
            samples: list[dict[str, float]] = []
            pop_index = None
            for index in range(150):
                bng.control.step(1, wait=True)
                probe = _vehicle_probe(bng, sync.PLAYER_NAME)
                if not probe.get("ok"):
                    continue
                horizontal = (float(probe["speed"]) ** 2 - float(probe["vz"]) ** 2) ** 0.5
                samples.append(
                    {
                        "h": horizontal,
                        "vz": float(probe["vz"]),
                        "y": float(probe["y"]),
                        "z": float(probe["z"]),
                    }
                )
                if (
                    pop_index is None
                    and len(samples) >= 2
                    and samples[-1]["vz"] - samples[-2]["vz"] > 3.0
                ):
                    pop_index = len(samples) - 1
                if pop_index is not None and len(samples) > pop_index + 12:
                    break
            _screenshot(
                bng,
                (strip[0] + 13.0, strip[1] - 16.0, strip[2] + 5.0),
                (strip[0], strip[1], strip[2] + 2.5),
                shot_names[5],
            )
            after = _arena_state(bng)["geysers"][0]
            assert int(after["pops"]) > int(before["pops"]), {
                "before": before,
                "after": after,
                "samples": samples[-5:],
            }
            assert pop_index is not None and pop_index >= 1, {
                "detail": "no vertical jump seen",
                "samples": samples[:20],
            }
            h_before = samples[pop_index - 1]["h"]
            h_after = samples[pop_index]["h"]
            vz_jump = samples[pop_index]["vz"] - samples[pop_index - 1]["vz"]
            report["geyser"] = {
                "pops_before": before["pops"],
                "pops_after": after["pops"],
                "h_before": h_before,
                "h_after": h_after,
                "vz_jump": vz_jump,
                "h_change_fraction": abs(h_after - h_before) / max(h_before, 1e-6),
                "peak_z_rise": max(s["z"] for s in samples) - samples[0]["z"],
            }
            assert h_before > 3.0, report["geyser"]
            assert abs(h_after - h_before) / h_before < 0.10, report["geyser"]
            assert vz_jump > 3.0, report["geyser"]
            player_vehicle.control(parkingbrake=1.0, brake=1.0, throttle=0.0)
            player_vehicle.disconnect()

            # --- restart costs exactly the engine's own reload (fix 2) -----
            bng.control.step(STEPS_PER_CALL * 2, wait=True)
            set_before = _count_events(log_path, ARENA_LOG_TAG, "set_option")
            boot_before = _count_events(log_path, ARENA_LOG_TAG, "boot")
            # The hand-back is idempotent against the CURRENT values (this
            # smoke already flipped ai_enabled back off for the pickup), so the
            # unload's cost is the keys that still differ from the snapshot.
            pre_restart = _lua_json(
                bng, f"return jsonEncode(extensions[{RUNTIME_EXTENSION!r}].hotPotatoGetOptions())"
            )
            restart_changed = _handback_keys(pre_restart, snapshot)
            _lua_json(bng, "scenario_scenarios.restartScenario(); return jsonEncode({ok = true})")
            deadline = time.monotonic() + 120.0
            fresh: dict[str, Any] = {}
            while time.monotonic() < deadline:
                time.sleep(1.0)
                try:
                    fresh = _arena_state(bng)
                except Exception:  # the engine is mid-reload; the socket answers again shortly
                    continue
                if fresh.get("loaded") and fresh.get("booted"):
                    break
            assert fresh.get("booted") is True, {
                "detail": "no fresh boot after restart",
                "arena": fresh,
            }
            bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
            bng.control.pause()
            bng.control.step(STEPS_PER_CALL * 4, wait=True)
            # The log flushes lazily; give the fresh boot's records time to land.
            for _ in range(30):
                if _count_events(log_path, ARENA_LOG_TAG, "boot") > boot_before:
                    break
                time.sleep(1.0)
            set_after = _count_events(log_path, ARENA_LOG_TAG, "set_option")
            boot_after = _count_events(log_path, ARENA_LOG_TAG, "boot")
            report["restart"] = {
                "set_option_before": set_before,
                "set_option_after": set_after,
                "boot_before": boot_before,
                "boot_after": boot_after,
                "snapshot_after": {k: fresh["snapshot"].get(k) for k in sync.BOOT_OPTION_KEYS},
                "obstacles": fresh.get("obstacles"),
            }
            # The old instance's unload hands back the keys that are still the
            # arena's values, then the fresh instance boots (4): 4 + those,
            # never 8. ai_enabled (the smoke's tuner flip) is preserved.
            report["restart"]["changed_at_restart"] = restart_changed
            assert "ai_enabled" not in restart_changed, report["restart"]
            assert bool(fresh["snapshot"].get("ai_enabled")) is False, {
                "detail": "the tuner's ai_enabled=false was not the fresh snapshot's value",
                **report["restart"],
            }
            report["restart"]["expected_set_option_delta"] = 4 + len(restart_changed)
            assert boot_after - boot_before == 1, report["restart"]
            assert set_after - set_before == 4 + len(restart_changed), report["restart"]
            # The fresh snapshot is the player's CURRENT values: the planted
            # ones with the tuner's ai_enabled=false on top.
            expected_after = dict(crash_player_values, ai_enabled=False)
            assert report["restart"]["snapshot_after"] == expected_after, report["restart"]
            assert fresh.get("obstacles") == "registered", report["restart"]
            assert fresh.get("recovered_calls") == 0, report["restart"]
            snapshot = expected_after
            changed_keys = _handback_keys(arena_values, snapshot)

            # --- "Exit scenario" hands the player's options back (r2 fix 1) -
            # The pause menu's button (homeRail.lua) calls
            # scenario_scenarios.stop(), which unloads the scenario extension
            # BEFORE clientEndMission - the path round 2 missed.
            unload_before = _count_events(
                log_path, ARENA_LOG_TAG, "set_option", "reason", "extension_unloaded"
            )
            _lua_json(bng, "scenario_scenarios.stop(); return jsonEncode({ok = true})")
            # The witness is the PERSISTED settings file every
            # hotPotatoSetOption writes (spec SETTINGS_PATH): the player's saved
            # values must be byte-equal to the snapshot for every touched key.
            restored: dict[str, Any] = {}
            deadline = time.monotonic() + 60.0
            while time.monotonic() < deadline:
                time.sleep(1.0)
                if not settings_file.is_file():
                    continue
                try:
                    restored = json.loads(settings_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if restored and restored.get("ai_enabled") == snapshot["ai_enabled"]:
                    break
            report["options_after_mission"] = {k: restored.get(k) for k in sync.BOOT_OPTION_KEYS}
            for key in sync.BOOT_OPTION_KEYS:
                assert restored.get(key) == snapshot[key], {
                    "detail": f"{key} not handed back byte-equal",
                    **report["options_after_mission"],
                    "snapshot": snapshot,
                }
            # The tuner flip survived every exit path: ai_enabled is OFF on
            # disk although the arena's own value was ON.
            assert restored.get("ai_enabled") is False, report["options_after_mission"]
            # The log's tail flushes only after the game settles in the menu:
            # the unload hand-back count is asserted from the post-cleanup
            # parse below (restart unload + exit unload).
            report["exit_restore_expected"] = len(restart_changed) + len(changed_keys)
            report["snapshot_file_after_exit"] = snapshot_file.is_file()
            assert not snapshot_file.is_file(), "the snapshot file must be deleted on hand-back"

            # The settings file is the arena's own footprint on this profile
            # and cleanup removes it; nothing else was left behind.
            report["completed"] = True
            scenario = None  # already stopped; cleanup only closes the process
        finally:
            try:
                # scenario.stop() fires onClientEndMission (the arena's teardown
                # event) before the process is asked to quit; the delete step
                # is a no-op for a scenario shipped inside a zip.
                cleanup_owned_beamng_session(bng, owned_process=owned_process, scenario=scenario)
            finally:
                if timer is not None:
                    timer.cancel()
                for name in shot_names:
                    source = user / "screenshots" / f"{name}.png"
                    if source.is_file() and not (shot_dir / f"{name}.png").is_file():
                        shutil.copyfile(source, shot_dir / f"{name}.png")
                # The engine compiles the shipped DAEs (.cdae) AND cooks the
                # PNG textures (.dds) under temp/; both are keyed by path and
                # would shadow a re-cut, so both go.
                cached = (
                    tuple(p for p in mesh_cache.rglob("*") if p.is_file())
                    if mesh_cache.is_dir()
                    else ()
                )
                cache_dirs = (
                    (
                        tuple(
                            sorted(
                                (p for p in mesh_cache.rglob("*") if p.is_dir()),
                                key=lambda p: -len(p.parts),
                            )
                        )
                        + (mesh_cache,)
                    )
                    if mesh_cache.is_dir()
                    else ()
                )
                try:
                    cleanup_exact_live_artifacts(
                        profile=user,
                        files=(
                            installed_hp,
                            installed_arena,
                            settings_file,
                            snapshot_file,
                            *profile_shots,
                            *cached,
                        ),
                        empty_directories=cache_dirs,
                    )
                finally:
                    records, issues = _log_records(log_path, log_start)
                    report["arena_events"] = [
                        r["event"] for r in records if r["_tag"] == ARENA_LOG_TAG
                    ]
                    report["runtime_events"] = [
                        r["event"] for r in records if r["_tag"] == RUNTIME_LOG_TAG
                    ]
                    report["log_issues"] = issues
                    report["shots"] = sorted(p.name for p in shot_dir.glob("*.png"))
                    (shot_dir / f"arena_smoke_{suffix}.json").write_text(
                        json.dumps(report, indent=1, default=str), encoding="utf-8"
                    )

    arena_events = report["arena_events"]
    runtime_events = report["runtime_events"]
    issues = report["log_issues"]
    assert "boot" in arena_events, report
    assert "geyser_pop" in arena_events, report
    assert "scenario_restarted" in arena_events, report
    unload_restores = [
        r
        for r in records
        if r["_tag"] == ARENA_LOG_TAG
        and r["event"] == "set_option"
        and r.get("reason") == "extension_unloaded"
    ]
    report["exit_restore_calls"] = len(unload_restores)
    report["exit_restore_keys"] = [r.get("key") for r in unload_restores]
    # The persisted settings file (asserted byte-equal above) is the
    # authoritative witness for the exit hand-back: the runtime writes it on
    # every accepted setOption. The log is best-effort - BeamNG drops its
    # unflushed tail on process close - so it bounds the count rather than
    # pinning it: the restart's unload must be there, and nothing may exceed
    # the changed-key budget.
    assert len(unload_restores) >= 1, report
    assert len(unload_restores) <= report.get("exit_restore_expected"), report
    assert "snapshot_recovered" in arena_events, report
    # --- far-field band metric: RECORDED, not asserted ---------------------
    # The critic's exposure-independent metric: inside a plaza disc, the mean
    # absolute ROW gradient over the mean absolute COLUMN gradient. Unbanded
    # floors sit at 1.2-1.8; the 12 mm skin depth-fighting the groundplane
    # scores 3-5.7. Six clean frames are NOT a witness that the floor's far
    # detail engages: the round-4 critic's negative control (the shipped
    # package with the floor's _a70 node removed) still rendered the near
    # mesh at 300 m, and 4 of 5 boots produce clean frames with or without
    # any LOD. The flicker is an open G1/G6 item; here the min/max over the
    # frames is measured and reported, and only the frame count is gated.
    far_ratios = []
    for name in (n for n in shot_names if "farfield" in n):
        frame = shot_dir / f"{name}.png"
        if frame.is_file():
            far_ratios.append(_band_ratio(frame, 640, 372, 140))
    report["farfield_band_ratio"] = {
        "frames": len(far_ratios),
        "min": min(far_ratios) if far_ratios else None,
        "max": max(far_ratios) if far_ratios else None,
        "values": far_ratios,
    }
    (shot_dir / f"arena_smoke_{suffix}.json").write_text(
        json.dumps(report, indent=1, default=str), encoding="utf-8"
    )
    assert len(far_ratios) >= 6, report["farfield_band_ratio"]
    assert "prop_registered" in runtime_events and "round_started" in runtime_events, report
    assert not issues, {"detail": "the runtime or the arena logged errors", **report}
