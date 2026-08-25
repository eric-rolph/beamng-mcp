"""Live gate: runtime part placement survives sloped and yawed spawns.

Every other Giant Props live gate boots on ``smallgrid``, which is dead flat.
Flat, unyawed ground is the one condition where a prop's object transform
(``vehicle:getPosition()``/``getRotation()``) agrees with its live node cloud,
so it hides an entire class of placement bug:

- ``getRotation()`` only refreshes on spawn/teleport/reset. A prop that settles
  onto a slope reports its SPAWN attitude forever while the flexbody renders at
  the real nodes.
- A hand-built quaternion has to be conjugated before the engine's ``q * vec3``
  applies it the intended way round.
- ``modelRotation`` has to compose as ``FLIP * vehicleRotation``; the reverse
  order flips about the world axis instead of the model's own.

All three are exactly identity on a level, unyawed spawn. All three shipped.
Boot of Doom's console instruments ended up 11.5 m from their own control panel
on a 7 m-per-12 m slope and a metre off on a gentle one, which is how a player
found it in a published mod (2026-08-24). The errors also COMPOSE, so a partial
fix reads as a different wrong answer rather than as progress.

The core assertion is deliberately mod-agnostic and non-circular: a prop is a
RIGID body, so the distance from each runtime-created part to each cage node
must be the SAME whatever attitude the prop spawned at. Ground truth is the
node cloud, because that is what the flexbody renders at -- the test never
reuses the frame math it is checking.

Two things back that up:

- ``frame_source`` must read ``node_cloud``. The runtime falls back to the
  stale object transform whenever the node data is not ready, and on flat
  ground the two paths agree to 0.000 m -- so without this assertion a prop
  stuck on the fallback forever passes every positional check ever written.
- an absolute check against the authored handoff, for mods that declare which
  parts their idle behaviour leaves unposed. Rigid-body invariance alone would
  not notice a systematic offset that happens to be attitude-invariant.

Opt in with the sentinel-isolated profile, exactly like the other live gates::

    $env:BEAMNG_MCP_TEST_BEAMNG_HOME = '<BeamNG.drive installation>'
    $env:BEAMNG_MCP_TEST_BEAMNG_BINARY = '<...>\\Bin64\\BeamNG.drive.x64.exe'
    $env:BEAMNG_MCP_TEST_BEAMNG_USER = '<...>\\test-users\\<id>\\current'
    pytest -q -s tests/test_giant_props_slope_live.py
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import uuid
import zipfile
from contextlib import ExitStack
from dataclasses import dataclass, field
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
LIVE_TEST_TAG = "GIANT_PROPS_SLOPE_LIVE_TEST"

# A terrain map, unlike every other gate in this pack.
LEVEL = "utah"

# Spots probed on utah 2026-08-24, stable across repeated boots. The drops are
# ASSERTED rather than assumed: if the level ever changes under us this gate
# must fail loudly instead of quietly re-testing flat ground.
FLAT_SPOT = (300.0, -200.0)
SLOPE_SPOT = (0.0, 400.0)
FLAT_MAX_DROP = 0.25
SLOPE_MIN_DROP = 3.0
# Props run tens of metres from their datum, so sample the drop across a span
# rather than at a point.
DROP_SPAN = 12.0

IDENTITY = (0.0, 0.0, 0.0, 1.0)
YAW40 = (0.0, 0.0, math.sin(math.radians(20.0)), math.cos(math.radians(20.0)))

# Rigid-body invariance tolerance. The fixed runtime holds every distance to
# ~1 mm; the bug this gate exists for moved parts by 1.0 m on a GENTLE slope
# and 11.5 m on a steep one, and left a 0.208 m systematic error even on flat
# ground. 5 cm is loose enough for float noise and 20x tighter than the mildest
# real failure.
TOLERANCE_M = 0.05

# Two consecutive probes must agree to this before a sample is trusted, so a
# behaviour that animates within one phase cannot be compared against a
# different point in its own cycle.
QUIESCENT_M = 0.002

# The gate compares attitudes, so the SET of attitudes it sampled has to span a
# real rotation -- otherwise the invariance check compares a thing to itself.
# Requiring it per-spawn would be wrong: BeamNG does not reliably conform a
# YAWED spawn to a steep slope, and measured 53.19 deg for `slope` but
# 0.00003 deg for `slope_yaw40` on the same spot. That spawn is still a
# perfectly good rigid-body sample; it just is not the tilted one. So require
# the SPREAD, require at least one genuinely tilted attitude, and require the
# flat baseline to be level.
SLOPE_MIN_TILT_DEG = 8.0
MIN_TILT_SPREAD_DEG = 8.0
FLAT_MAX_TILT_DEG = 3.0


@dataclass(frozen=True)
class PropGate:
    """One mod to drive across the four attitudes."""

    key: str
    mod_id: str
    zip_basename: str
    extension: str
    log_tag: str
    # Parts the idle behaviour leaves at their authored pivot, so their
    # ABSOLUTE placement can be checked against the handoff. Empty is allowed:
    # the rigid-body check still runs, and it is the actual regression guard.
    unposed_at_idle: tuple[str, ...] = field(default=())


GATES = (
    # Boot of Doom is the mod the player bug was reported against: its console
    # instruments sit ~11.7 m from the ref node. At the default power level the
    # ladder retracts segments 2..10 into the cabinet and the needle only
    # ROTATES about its hub, so needle/boot/seg1 stay on their authored pivots.
    PropGate(
        key="boot_of_doom",
        mod_id="ericrolph_boot_of_doom",
        zip_basename="boot_of_doom_ericrolph.zip",
        extension="ericrolph__boot__of__doom_runtime",
        log_tag="ERICROLPH_BOOT_OF_DOOM_RUNTIME",
        unposed_at_idle=("angle_needle", "boot", "pow_seg1"),
    ),
    # Pachinko Tower has the pack's worst angular amplification: 1.40 m datum
    # baselines carrying a 60 m lever arm out to the sheave, so it is the most
    # sensitive prop in the pack to any basis error. Its parts all animate, so
    # it runs the rigid-body check only.
    PropGate(
        key="pachinko_tower",
        mod_id="ericrolph_pachinko_tower",
        zip_basename="pachinko_tower_ericrolph.zip",
        extension="ericrolph__pachinko__tower_runtime",
        log_tag="ERICROLPH_PACHINKO_TOWER_RUNTIME",
    ),
)


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the Giant Props slope gate"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the Giant Props slope gate requires a sentinel-isolated profile")
    return home, user, binary


def _lua_json(bng: BeamNGpy, command: str) -> Any:
    return json.loads(bng.control.queue_lua_command(command, response=True))


def _namespace_conflicts(profile: Path, mod_id: str, allowed: Path) -> list[str]:
    """Archives that would shadow this mod's vehicle or GE-extension namespace.

    BeamNG mounts EVERY zip below ``mods/`` recursively, so a second archive
    carrying the same namespace shadows the installed runtime nondeterministic-
    ally. Matching on filename is not enough -- the profile really did hold a
    ``pachinko_tower_ericrolph.zip`` shipping ``ericrolph_pachinko_tower``,
    which no substring check on the mod id would ever have caught. Look at what
    each archive actually CONTAINS.
    """

    mods_root = profile / "mods"
    if not mods_root.is_dir():
        return []
    prefixes = (f"vehicles/{mod_id}/", f"lua/ge/extensions/{mod_id}/")
    conflicts = []
    for candidate in sorted(mods_root.rglob("*.zip")):
        if candidate == allowed:
            continue
        try:
            with zipfile.ZipFile(candidate) as archive:
                names = archive.namelist()
        except (zipfile.BadZipFile, OSError):
            continue
        if any(name.startswith(prefixes) for name in names):
            conflicts.append(str(candidate))
    return conflicts


def _terrain_z(bng: BeamNGpy, x: float, y: float) -> float:
    probe = _lua_json(
        bng,
        f"local start = vec3({x}, {y}, 400); "
        "local distance = castRayStatic(start, vec3(0, 0, -1), 800); "
        "return jsonEncode({z = start.z - distance, distance = distance})",
    )
    distance = float(probe["distance"])
    assert 0.0 < distance < 800.0, {"x": x, "y": y, "probe": probe}
    return float(probe["z"])


def _authored(gate: PropGate) -> dict[str, Any]:
    """Node positions, part pivots and reference nodes, from the handoff.

    Part pivots are authored-frame; the mesh frame differs by the same 180
    degree Z flip the runtime applies, i.e. ``(x, y, z) -> (-x, -y, z)``.
    """

    handoff = json.loads(
        (PACK_ROOT / gate.key / "authoring" / f"{gate.mod_id}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    nodes = {node["id"]: tuple(float(v) for v in node["position"]) for node in handoff["nodes"]}
    parts = {}
    for part in handoff.get("parts", []):
        pivot = [float(v) for v in part["pivot_world"]]
        parts[part["name"]] = (-pivot[0], -pivot[1], pivot[2])

    refnodes = handoff["refnodes"]
    ref_id = refnodes["ref"]
    ref_position = nodes[ref_id]
    # The four refNodes pin the base; the farthest nodes make the check
    # sensitive to rotation, not just translation. Chosen deterministically so
    # a rerun compares like with like.
    reference = [refnodes[role] for role in ("ref", "back", "left", "up")]
    farthest = sorted(
        nodes,
        key=lambda node_id: (-math.dist(nodes[node_id], ref_position), node_id),
    )
    for node_id in farthest:
        if len(reference) >= 7:
            break
        if node_id not in reference:
            reference.append(node_id)
    return {
        "nodes": nodes,
        "parts": parts,
        "reference": reference,
        "refnodes": refnodes,
        "part_count": len(parts),
        "max_reach": max((math.dist(pivot, ref_position) for pivot in parts.values()), default=0.0),
    }


def _probe_source(gate: PropGate, prop_name: str, node_names: list[str], parts: list[str]) -> str:
    """Read every runtime part position plus the requested cage node positions.

    Node world positions come from the LIVE node cloud -- what the flexbody
    renders at -- so they are independent ground truth for the frame the
    runtime derives.
    """

    wanted_nodes = ", ".join(repr(name) for name in node_names)
    wanted_parts = ", ".join(repr(name) for name in parts)
    return f"""
local vehicle = scenetree.findObject({prop_name!r})
if not vehicle then return jsonEncode({{ok = false, why = "vehicle missing"}}) end
local id = vehicle:getID()
local extension = extensions[{gate.extension!r}]
if not extension then return jsonEncode({{ok = false, why = "extension missing"}}) end
local state = extension.getSystemState(id)
if not state or not state.registered then
  return jsonEncode({{ok = false, why = "not registered"}})
end

local position = vehicle:getPosition()
local wanted = {{}}
for _, name in ipairs({{{wanted_nodes}}}) do wanted[name] = true end
local nodes = {{}}
local decoded, data = pcall(function() return core_vehicle_manager.getVehicleData(id) end)
local vdataNodes = decoded and data and data.vdata and data.vdata.nodes or nil
if not vdataNodes then return jsonEncode({{ok = false, why = "vdata missing"}}) end
for _, node in pairs(vdataNodes) do
  if node.name and wanted[node.name] then
    local relative = vehicle:getNodePosition(node.cid)
    nodes[node.name] = {{
      x = position.x + relative.x,
      y = position.y + relative.y,
      z = position.z + relative.z,
    }}
  end
end

local parts = {{}}
for _, part in ipairs({{{wanted_parts}}}) do
  local object = scenetree.findObject(
    string.format("%s_p%d_part_%s", {gate.mod_id!r}, id, part))
  if object then
    local p = object:getPosition()
    parts[part] = {{x = p.x, y = p.y, z = p.z}}
  end
end

return jsonEncode({{
  ok = true,
  frame_source = state.frame_source,
  behavior_phase = state.behavior_phase,
  part_count = state.part_count,
  nodes = nodes,
  parts = parts,
}})
"""


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    return math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))


def _tilt_degrees(sample: dict[str, Any], refnodes: dict[str, str]) -> float:
    """How far the prop's base plane is tipped off horizontal, from the node cloud.

    A sloped SPOT does not guarantee a tilted PROP -- the spawn may not have
    taken the terrain's attitude yet when it was sampled, and a level prop makes
    every rotation bug in this file invisible. So measure the attitude and
    assert it, rather than assuming the terrain conferred it.

    The base plane is spanned by the ref->back and ref->left baselines, whose
    normal is authored vertical for every prop in the pack. Acute angle, so the
    normal's sign does not matter.
    """

    nodes = sample["nodes"]
    origin = nodes[refnodes["ref"]]
    edges = []
    for role in ("back", "left"):
        far = nodes[refnodes[role]]
        edges.append((far["x"] - origin["x"], far["y"] - origin["y"], far["z"] - origin["z"]))
    (ax, ay, az), (bx, by, bz) = edges
    normal = (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)
    length = math.dist((0.0, 0.0, 0.0), normal)
    if length == 0.0:
        return 0.0
    return math.degrees(math.acos(min(1.0, abs(normal[2]) / length)))


def _distance_table(sample: dict[str, Any]) -> dict[str, float]:
    """Every part-to-node distance, keyed ``part|node``.

    On a rigid body this table is invariant under any spawn attitude.
    """

    return {
        f"{part_name}|{node_name}": _distance(part, node)
        for part_name, part in sorted(sample["parts"].items())
        for node_name, node in sorted(sample["nodes"].items())
    }


def _runtime_log_records(
    log_path: Path, start_marker: str, log_tag: str
) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    issues: list[str] = []
    started = False
    payload = log_path.read_text(encoding="utf-8", errors="replace")
    for line in payload.splitlines():
        if start_marker in line:
            started = True
            continue
        if not started or log_tag not in line:
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


@pytest.mark.beamng_live
@pytest.mark.parametrize("gate", GATES, ids=lambda gate: gate.key)
def test_runtime_parts_stay_glued_to_the_cage_on_slopes_and_yaws(gate: PropGate) -> None:
    home, user, binary = _configured_runtime()
    dist_root = PACK_ROOT / gate.key / "dist"
    archive = dist_root / gate.zip_basename
    lock = json.loads((dist_root / f"{gate.mod_id}.lock.json").read_text(encoding="utf-8"))
    payload = archive.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == lock["sha256"], (
        "the dist zip does not match its lock - rebuild before gating"
    )

    authored = _authored(gate)
    reference_nodes = authored["reference"]
    part_names = sorted(authored["parts"])
    assert len(reference_nodes) >= 5, reference_nodes
    assert part_names, "mod declares no runtime parts"

    suffix = uuid.uuid4().hex[:10]
    installed_zip = require_confined_profile_target(
        user, Path("mods") / f"{gate.key}_slope_{suffix}.zip"
    )
    scenario_name = f"{gate.key}_slope_{suffix}"
    scenario_directory = require_confined_profile_target(
        user, Path("levels") / LEVEL / "scenarios" / scenario_name
    )
    log_path = user / "beamng.log"
    log_start = f"giant_props_slope_start_{suffix}"

    samples: dict[str, dict[str, Any]] = {}

    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(1))
        (tcom_port,) = reservation.ports
        existing_conflicts = _namespace_conflicts(user, gate.mod_id, installed_zip)
        if existing_conflicts:
            pytest.fail(
                f"another archive in the isolated profile ships the {gate.mod_id} "
                f"namespace and would shadow this runtime nondeterministically: "
                f"{existing_conflicts}. Move it to a profile-root sibling directory "
                f"(never under mods/) before running this gate."
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

            timer = threading.Timer(900.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)

            scenario = Scenario(
                LEVEL,
                scenario_name,
                description="Disposable Giant Props sloped-terrain placement fixture",
            )
            # A stock vehicle keeps the scenario valid; the prop itself is
            # spawned per attitude below so each spawn gets a clean settle.
            anchor = Vehicle(f"{gate.mod_id}_slope_anchor", "pigeon", license="SLOPE")
            scenario.add_vehicle(anchor, pos=(0.0, 0.0, 200.0), rot_quat=IDENTITY, cling=True)
            scenario.make(bng)
            bng.control.pause()
            bng.scenario.load(scenario, precompile_shaders=False)
            bng.scenario.start()
            bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
            bng.control.pause()
            bng.control.step(5, wait=True)
            marker = _lua_json(
                bng,
                f"log('I', {LIVE_TEST_TAG!r}, {log_start!r}); return jsonEncode({{ok = true}})",
            )
            assert marker == {"ok": True}

            # Prove the two spots really are flat and steep before trusting
            # anything measured on them.
            terrain: dict[str, dict[str, float]] = {}
            for tag, (spot_x, spot_y) in (("flat", FLAT_SPOT), ("slope", SLOPE_SPOT)):
                near = _terrain_z(bng, spot_x, spot_y)
                far = _terrain_z(bng, spot_x, spot_y + DROP_SPAN)
                terrain[tag] = {"z": near, "drop": abs(far - near)}
            assert terrain["flat"]["drop"] <= FLAT_MAX_DROP, terrain
            assert terrain["slope"]["drop"] >= SLOPE_MIN_DROP, terrain

            attitudes = (
                ("flat", FLAT_SPOT, terrain["flat"]["z"], IDENTITY),
                ("flat_yaw40", FLAT_SPOT, terrain["flat"]["z"], YAW40),
                ("slope", SLOPE_SPOT, terrain["slope"]["z"], IDENTITY),
                ("slope_yaw40", SLOPE_SPOT, terrain["slope"]["z"], YAW40),
            )
            probe = _probe_source(gate, "", reference_nodes, part_names)
            for tag, (spot_x, spot_y), spot_z, rotation in attitudes:
                prop_name = f"{gate.mod_id}_slope_{tag}_{suffix}"
                prop = Vehicle(prop_name, gate.mod_id, license="PROP")
                spawned = bng.vehicles.spawn(prop, (spot_x, spot_y, spot_z), rotation, False, True)
                assert spawned is True, tag

                probe = _probe_source(gate, prop_name, reference_nodes, part_names)
                sample: dict[str, Any] = {}
                previous: dict[str, Any] | None = None
                settled = False
                for _ in range(40):
                    bng.control.step(15, wait=True)
                    sample = _lua_json(bng, probe)
                    # The runtime starts on the object-transform fallback while
                    # vdata warms up, so wait for the real frame rather than
                    # measuring the path this gate exists to reject.
                    if not (
                        sample.get("ok")
                        and sample.get("frame_source") == "node_cloud"
                        and len(sample.get("parts") or {}) == authored["part_count"]
                        and len(sample.get("nodes") or {}) == len(reference_nodes)
                    ):
                        previous = None
                        continue
                    # QUIESCENCE, not a phase label. Distances are only
                    # comparable between attitudes if the pose is the same, and
                    # a behaviour can animate WITHIN one phase -- on elapsed
                    # time, not just on state -- so a matching `behavior_phase`
                    # proves nothing. Require the geometry itself to hold still
                    # across two consecutive probes instead.
                    if previous is not None:
                        table, before = _distance_table(sample), _distance_table(previous)
                        if max(abs(table[k] - before[k]) for k in table) <= QUIESCENT_M:
                            settled = True
                            break
                    previous = sample
                assert sample.get("ok") is True, {"attitude": tag, "sample": sample}
                assert settled, {
                    "attitude": tag,
                    "message": (
                        "the prop never held still: its parts were still moving "
                        "between consecutive probes, so distances measured here "
                        "are not comparable with the other attitudes"
                    ),
                    "frame_source": sample.get("frame_source"),
                    "behavior_phase": sample.get("behavior_phase"),
                }
                # THE ANTI-VACUOUS ASSERTION. On flat ground the fallback and
                # the node-cloud frame agree to 0.000 m, so without this every
                # positional check below would pass on the broken path too.
                assert sample.get("frame_source") == "node_cloud", {
                    "attitude": tag,
                    "frame_source": sample.get("frame_source"),
                    "message": (
                        "the runtime never acquired its node-cloud frame and is "
                        "still dead reckoning from the stale object transform"
                    ),
                }
                assert sample["part_count"] == authored["part_count"], {
                    "attitude": tag,
                    "sample": sample,
                }
                assert sorted(sample["parts"]) == part_names, {
                    "attitude": tag,
                    "parts": sorted(sample["parts"]),
                }
                assert sorted(sample["nodes"]) == sorted(reference_nodes), {
                    "attitude": tag,
                    "nodes": sorted(sample["nodes"]),
                }
                samples[tag] = sample

                bng.vehicles.despawn(prop)
                bng.control.step(10, wait=True)
        finally:
            try:
                cleanup_owned_beamng_session(bng, owned_process=owned_process, scenario=scenario)
            finally:
                if timer is not None:
                    timer.cancel()
                cleanup_exact_live_artifacts(
                    profile=user,
                    files=(installed_zip,),
                    empty_directories=(scenario_directory,),
                )

    # --- the gate proper -------------------------------------------------
    # WITHOUT THIS THE WHOLE FILE IS DECORATION. Every bug it hunts is exactly
    # identity on a level prop, so if the "slope" spawns did not actually take
    # the terrain's attitude, all four samples are the same attitude and the
    # invariance check below compares a thing to itself. A sloped SPOT does not
    # guarantee a tilted PROP -- one of the original probe spawns read level on
    # the steep spot -- so measure it from the node cloud and require it.
    tilts = {tag: _tilt_degrees(sample, authored["refnodes"]) for tag, sample in samples.items()}
    assert tilts["flat"] <= FLAT_MAX_TILT_DEG, {
        "message": "the flat baseline spawn was not level, so it is not a baseline",
        "tilt_deg": tilts["flat"],
        "tilts": tilts,
    }
    assert max(tilts.values()) >= SLOPE_MIN_TILT_DEG, {
        "message": (
            "no spawn took a sloped attitude, so this run cannot distinguish any "
            "rotation bug from a correct frame - every bug this gate hunts is "
            "exactly identity on a level prop"
        ),
        "tilts": tilts,
    }
    assert max(tilts.values()) - min(tilts.values()) >= MIN_TILT_SPREAD_DEG, {
        "message": "the sampled attitudes do not span a real rotation",
        "tilts": tilts,
    }

    # A rigid body's internal distances do not depend on how it is oriented, so
    # every part-to-node distance measured on flat ground must survive a slope
    # and a yaw untouched. Ground truth is the node cloud, never the frame math
    # under test.
    baseline = _distance_table(samples["flat"])
    worst: dict[str, Any] = {"pair": None, "drift": 0.0, "attitude": None}
    drift_by_attitude: dict[str, float] = {}
    for tag, sample in samples.items():
        if tag == "flat":
            continue
        table = _distance_table(sample)
        assert sorted(table) == sorted(baseline), tag
        attitude_worst = 0.0
        for pair, value in table.items():
            drift = abs(value - baseline[pair])
            attitude_worst = max(attitude_worst, drift)
            if drift > worst["drift"]:
                worst = {
                    "pair": pair,
                    "drift": drift,
                    "attitude": tag,
                    "flat_m": baseline[pair],
                    "measured_m": value,
                }
        drift_by_attitude[tag] = attitude_worst

    assert worst["drift"] <= TOLERANCE_M, {
        "message": (
            "a runtime part moved relative to the cage when the prop changed "
            "attitude - the placement frame is not tracking the node cloud"
        ),
        "worst": worst,
        "drift_by_attitude": drift_by_attitude,
        "max_reach_m": authored["max_reach"],
    }

    # An attitude-invariant systematic offset would sail through the check
    # above, so pin the unposed parts against the authored handoff too.
    absolute: dict[str, dict[str, float]] = {}
    for part_name in gate.unposed_at_idle:
        assert part_name in authored["parts"], part_name
        for node_name in reference_nodes:
            expected = math.dist(authored["parts"][part_name], authored["nodes"][node_name])
            measured = baseline[f"{part_name}|{node_name}"]
            absolute[f"{part_name}|{node_name}"] = {
                "expected_m": expected,
                "measured_m": measured,
                "error_m": abs(measured - expected),
            }
    worst_absolute = (
        max(absolute.items(), key=lambda item: item[1]["error_m"]) if absolute else None
    )
    if worst_absolute is not None:
        assert worst_absolute[1]["error_m"] <= TOLERANCE_M, {
            "message": (
                "an unposed part does not sit where the authored geometry says "
                "it should, even on flat ground"
            ),
            "pair": worst_absolute[0],
            "detail": worst_absolute[1],
        }

    records, issues = _runtime_log_records(log_path, log_start, gate.log_tag)
    events = [str(record["event"]) for record in records]
    assert events.count("prop_registered") == len(samples), {
        "events": events,
        "issues": issues,
    }
    # The runtime warns when a working node-cloud frame is LOST. Acquiring one
    # at startup is logged at info and is expected once per spawn.
    regressions = [
        record
        for record in records
        if record.get("event") == "prop_frame_source"
        and record.get("frame_source") != "node_cloud"
        and record.get("previous") == "node_cloud"
    ]
    assert not regressions, {"message": "a prop lost its node-cloud frame", "records": regressions}
    assert not issues, issues

    print(
        json.dumps(
            {
                "mod": gate.mod_id,
                "level": LEVEL,
                "attitudes": sorted(samples),
                "max_reach_m": round(authored["max_reach"], 3),
                "tilt_deg": {k: round(v, 3) for k, v in sorted(tilts.items())},
                "worst_rigidity_drift_m": round(worst["drift"], 6),
                "worst_rigidity_pair": worst["pair"],
                "drift_by_attitude_m": {
                    key: round(value, 6) for key, value in sorted(drift_by_attitude.items())
                },
                "worst_absolute_error_m": (
                    round(worst_absolute[1]["error_m"], 6) if worst_absolute else None
                ),
                "worst_absolute_pair": worst_absolute[0] if worst_absolute else None,
            },
            sort_keys=True,
        )
    )
