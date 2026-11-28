"""Live PROOF for the Giant's Hearth forest (build round B3) on the sentinel profile.

One owned BeamNG boot that installs the LOCKED level zip into the sentinel-isolated profile,
loads the level at the design's golden-hour clock (T 0.30) and proves:

- **F1 census** -- ``core_forest.getForestObject():getData():getItems()`` returns exactly the
  number of rows the shipped ``forest/<item>.forest4.json`` files carry (154,686), and every
  one of the 54 ``TSForestItemData`` datablocks registered with its authored ``shapeFile``,
  ``annotation`` and wind fields.
- **F2 imposter harvest** -- ``Engine.Render.updateImposters(true)``, then every
  ``<shape>.dae.imposter.dds`` + ``.imposter_normals.dds`` the engine wrote into the profile's
  ``temp/`` is copied BESIDE ITS DAE in the mod tree and its DDS header read.  B0 measured the
  law this checks: ``BB::DIM=128`` on the ``bb_autobillboard25`` node yields 512 x 256
  (the default ``dim 64`` yields 256 x 128).
- **F3 ray census** -- 20 instances drawn deterministically from the shipped forest4 files.  A
  generated conifer must be hit inside the ANALYTIC window of its Colmesh cone
  (``forest_spec.colmesh_hit_window``, inscribed-to-circumscribed for the facets); a decimated
  model inside its bounding window; and the nine drive-through species (cards and debris) must
  let the ray through to the terrain.
- **F4 lane keep-out by ray** -- the four 89 m lanes swept from r 262 to r 430 at three lateral
  offsets: nothing stands above the terrain anywhere inside ``LANE_CLEAR_R`` (420 m), and the
  S1 sightline corridor to the lake is equally clear.
- **F5 frames** -- S7 (forest floor), S3 (crest to basin) and S8 (trail switchback) at their
  design clocks with the B0-measured FOV call, plus a frame taken 150 m off the tree line where
  imposters and meshes stand side by side.
- **F6 log** -- zero E-level lines attributable to the level; every E line dumped.
- **F7 footprint** -- what the boot left in ``temp/levels/<id>`` is censused and purged by the
  shared teardown; only the atlases copied out during the session survive.

A second, OPTIONAL boot (``test_forest_imposter_atlas_knobs``) installs a PROBE archive -- the
same level with three species re-annotated ``BB::DIM=256`` / ``BB::EQUATOR_STEPS=8`` /
``BB::DIM=128 + BB::POLAR_STEPS=2`` -- purely to answer design §4.3's open question about a
1024 x 512 atlas (QB-9b).  It never ships and it is skipped unless
``HOT_POTATO_FOREST_BB_PROBE=1``.

Evidence lands in ``HOT_POTATO_LEVEL_EVIDENCE_DIR`` (default: tmp_path).
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import random
import re
import shutil
import statistics
import struct
import threading
import time
import uuid
import zipfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

import pytest
from beamngpy import BeamNGpy, Scenario, Vehicle

from examples.hot_potato_arena.level import build_level_zip as dist
from examples.hot_potato_arena.level import forest_build
from examples.hot_potato_arena.level import forest_spec as fs
from examples.hot_potato_arena.level import level_writer as writer
from examples.hot_potato_arena.level import terrain_io as terrain
from examples.hot_potato_arena.level import terrain_model as tm
from tests import test_hot_potato_arena_live as smoke
from tests.live_support import (
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    require_confined_profile_target,
    reserve_loopback_ports,
)
from tests.test_hot_potato_level_scaffold_live import (
    CAMERA_FOV_DEG,
    LEVEL_ID,
    Session,
    _evidence_dir,
    _level_log_issues,
    _purge_level_profile_footprint,
    _purge_terrain_material_cache,
)

LEVEL_ROOT = writer.LEVEL_ROOT
GOLDEN_CLOCK = 0.30
RAY_START_LIFT = 60.0
RAY_LENGTH = 400.0
LANE_STEP_M = 3.0
LANE_OFFSETS_M = (-3.0, 0.0, 3.0)
LANE_CLEAR_TOLERANCE_M = 0.06  # the ray is bilinear, getTerrainHeight is the diagonal split
RAY_CENSUS_N = 20
CENSUS_SEED = 0x52415943  # "RAYC"
BB_PROBE_ENV = "HOT_POTATO_FOREST_BB_PROBE"

#: The three truth frames design §8 assigns to B3, plus the LOD-seam frame the brief asks for.
FRAMES = (
    (
        "s7_forest_floor",
        (997.1, 124.1, 108.7),
        (1041.2, 149.4, 119.2),
        GOLDEN_CLOCK,
        "S7: needle litter, ferns, deadfall and backlit twig cards at 2-20 m",
    ),
    (
        "s3_crest_to_basin",
        (804.3, -200.84, 107.5),
        (407.3, 486.79, 220.01),
        GOLDEN_CLOCK,
        "S3: the forest climbing the NW wall to the rounded crest",
    ),
    (
        "s8_trail_switchback",
        (1225.2, -917.8, 127.3),
        (850.0, -280.0, 108.0),
        GOLDEN_CLOCK,
        "S8: the whole hearth 600 m below with the forest as imposters",
    ),
)

#: Species that are drive-through BY DESIGN (cards and debris ship no Colmesh).
DRIVE_THROUGH = {s["key"] for s in fs.SPECIES if not s["colmesh"]}


def dds_header(payload: bytes) -> dict[str, Any]:
    """Width/height/mips/fourcc of a DDS, the way B0's probe read them."""
    if payload[:4] != b"DDS ":
        return {"error": "not a DDS", "bytes": len(payload)}
    _size, _flags, height, width, _pitch, _depth, mips = struct.unpack_from("<7I", payload, 4)
    _pf_flags, fourcc = struct.unpack_from("<I4s", payload, 4 + 72 + 4)
    return {
        "width": width,
        "height": height,
        "mip_count": mips,
        "fourcc": fourcc.decode("latin1"),
        "bytes": len(payload),
    }


def _instances(name: str) -> list[dict[str, Any]]:
    path = LEVEL_ROOT / f"forest/{name}.forest4.json"
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


#: How wide a canopy/boulder is, as a fraction of its authored size -- used ONLY to decide
#: whether a neighbour could stand over a census target's ray.  Generous on purpose.
CANOPY_FRACTION = {"conifer": 0.35, "snag": 0.20, "card": 0.45, "deadwood": 0.60, "rock": 0.60}
INDEX_CELL_M = 26.0


def _instance_index() -> dict[tuple[int, int], list[tuple[float, float, float, float]]]:
    """Every instance as (x, y, absolute top z, canopy radius) in a 26 m spatial hash."""
    grid: dict[tuple[int, int], list[tuple[float, float, float, float]]] = {}
    for species in fs.SPECIES:
        fraction = CANOPY_FRACTION[species["family"]]
        for row in _instances(fs.datablock_name(species)):
            x, y, z = row["pos"]
            size = species["height_m"] * float(row["scale"])
            grid.setdefault((int(x // INDEX_CELL_M), int(y // INDEX_CELL_M)), []).append(
                (x, y, z + size, size * fraction)
            )
    return grid


def _interceptor(grid: dict, x: float, y: float, ray_start_z: float) -> float | None:
    """The horizontal distance to the nearest OTHER instance that could stand over the ray.

    A neighbour intercepts when its canopy covers this (x, y) AND its top is above where the
    ray starts.  ``None`` means the column is the target's alone -- which is what the census
    needs before it can call a reading a miss.
    """
    cx, cy = int(x // INDEX_CELL_M), int(y // INDEX_CELL_M)
    worst = None
    for i in range(cx - 1, cx + 2):
        for j in range(cy - 1, cy + 2):
            for px, py, top, radius in grid.get((i, j), ()):
                distance = math.hypot(px - x, py - y)
                if distance <= 1e-6:
                    continue
                if distance < radius and top > ray_start_z:
                    if worst is None or distance < worst:
                        worst = distance
    return worst


def _local_grade(x: float, y: float, step: float = 0.5) -> float:
    """|grad z| of the design surface at (x, y), from the frozen model's own bilinear sample."""
    zx = (terrain.surface_z(x + step, y) - terrain.surface_z(x - step, y)) / (2.0 * step)
    zy = (terrain.surface_z(x, y + step) - terrain.surface_z(x, y - step)) / (2.0 * step)
    return float(math.hypot(zx, zy))


def _shape_row(species: dict) -> dict:
    return forest_build.shapes_manifest()["species"][species["key"]]


def _colmesh_extent(species: dict) -> tuple[float, float] | None:
    """(top z, horizontal half-extent) of a shape's OWN Colmesh, in local metres at scale 1.

    r1's model window was ``[0.02, height_m * 1.05 + 0.2]`` on a ray dropped at
    ``lateral_offset_m = 0.0``.  For ``fallen_log_a`` -- a 10.7 m log LYING DOWN -- that is
    [0.02, 13.12] m over a collider about a metre tall, and the reading was 0.97 m: a window
    13 times wider than the thing it measures, which cannot fail.  The Colmesh's own bounding
    box, exported by ``blender_forest._bbox``, is the number that makes the window testable.
    """
    box = _shape_row(species).get("colmesh_bbox")
    if not box:
        return None
    # The SMALLEST horizontal half-extent, because the instance is planted at a random yaw
    # and the census offsets the ray in world +x: on `fallen_log_a` -- a 10.6 m log 0.95 m
    # wide -- 35 % of the LONG half-extent is 1.84 m, which is off the side of the log for
    # most yaws, and the first r2 run duly read 0.000 m through three of them.  Using the
    # short half-extent makes the off-axis ray hit for every yaw, which is what the gate is
    # supposed to assert.
    half = min(
        max(abs(box["max"][0]), abs(box["min"][0])),
        max(abs(box["max"][1]), abs(box["min"][1])),
    )
    return float(box["max"][2]), float(half)


def _shape_top(species: dict) -> float:
    box = _shape_row(species).get("shape_bbox")
    return float(box["max"][2]) if box else float(species["height_m"])


def _ray_census_plan() -> list[dict[str, Any]]:
    """20 instances whose column is THEIR OWN: a spread over conifers, models and cards.

    The forest is planted at 0.8-3.5 m spacing per category, so a ray dropped over an instance
    can be intercepted by a taller NEIGHBOUR -- the first live run read 9.3 m over a 2.2 m
    ``scree_rock_b`` and 11.6 m over a 2.2 m ``shrub_04``, both true readings of the wrong
    plant.  Each census target is therefore chosen so that no other instance's canopy covers
    its column above the ray's start, and the ray starts two metres over the target's OWN top.
    """
    rng = random.Random(CENSUS_SEED)  # noqa: S311 - a seeded sample, not a key
    grid = _instance_index()
    conifers = [s for s in fs.SPECIES if fs.colmesh_profile(s) is not None]
    models = [s for s in fs.SPECIES if s["colmesh"] and fs.colmesh_profile(s) is None]
    cards = [s for s in fs.SPECIES if not s["colmesh"]]
    chosen = rng.sample(conifers, 8) + rng.sample(models, 8) + rng.sample(cards, 4)
    plan = []
    for species in chosen:
        rows = _instances(fs.datablock_name(species))
        order = list(range(len(rows)))
        rng.shuffle(order)
        picked = None
        for index in order[:6000]:
            row = rows[index]
            x, y, z = row["pos"]
            lift = species["height_m"] * float(row["scale"]) + 2.0
            if _interceptor(grid, x, y, z + lift) is None:
                picked = row
                break
        assert picked is not None, f"no clear column for {species['key']}"
        x, y, z = picked["pos"]
        scale = float(picked["scale"])
        grade = _local_grade(x, y)
        profile = fs.colmesh_profile(species)
        top = species["height_m"] * scale
        if species["key"] in DRIVE_THROUGH:
            kind, offset, window = "drive_through", 0.0, None
        elif species["family"] == "snag":
            # MEASURED: a snag's broken stubs collide too.  The cone predicted 8.4-10.7 m for
            # snag_a and the engine hit 13.1 m -- the height of its upper stub, which stands
            # outside the collision cone.  The other seven conifers land inside their analytic
            # window to a few centimetres, so the cone IS the collider; a snag simply has more
            # than the cone.  Its window is the shape's own envelope, and the near-axis ray
            # below still reads the cone's apex.
            kind = "snag"
            offset = 0.4 * profile["r_base"] * scale
            envelope = _shape_top(species) * scale
            window = (0.45 * envelope, envelope + 0.20)
        elif profile is not None:
            kind = "conifer"
            offset = 0.4 * profile["r_base"] * scale
            window = fs.colmesh_hit_window(species, offset, scale)
        else:
            kind = "model"
            extent = _colmesh_extent(species)
            assert extent is not None, f"{species['key']} has a Colmesh but no exported bbox"
            colmesh_top, half = extent
            ceiling = colmesh_top * scale + 0.25
            # ON-AXIS: the hull is thickest over its own centre, so the hit must be in the top
            # 45 % of the collider.  Both bounds bite.
            offset = 0.0
            window = (0.45 * colmesh_top * scale, ceiling)
        plan.append(
            {
                "species": species["key"],
                "kind": kind,
                "x": x,
                "y": y,
                "authored_z": z,
                "scale": scale,
                "lateral_offset_m": round(offset, 4),
                "window": list(window) if window else None,
                "height_m": species["height_m"],
                "lift": round(top + 2.0, 3),
                "column_is_clear": True,
                "local_grade": round(grade, 4),
                "slope_allowance_m": round(offset * grade + 0.005, 4),
                "apex_offset_m": round(0.06 * profile["r_base"] * scale, 4) if profile else None,
                "apex_z_m": round(profile["apex_z"] * scale, 3) if profile else None,
            }
        )
        if kind == "model":
            # OFF-AXIS: r1 dropped every model ray at lateral_offset 0.0 -- the easiest place
            # to hit anything.  A second ray at 35 % of the hull's own half-extent has to
            # find the collider too, and still under its own top.
            plan.append(
                {
                    "species": species["key"],
                    "kind": "model_off_axis",
                    "x": x,
                    "y": y,
                    "authored_z": z,
                    "scale": scale,
                    "lateral_offset_m": round(0.35 * half * scale, 4),
                    # r3 (critic r2 M3): r2's off-axis window was [0.02, ceiling] -- a floor
                    # of two centimetres over a collider metres tall, which can only fail if
                    # the ray misses the shape entirely, and that is the exact complaint r1
                    # made about r1's own windows.  The Colmesh is a CONVEX hull, so its upper
                    # surface at 35 % of its own SHORT half-extent cannot be near the ground:
                    # for any convex body the height there is a large fraction of its peak.
                    # The floor is 30 % of the collider's top, which is conservative for a
                    # convex hull and still bites from below.
                    "window": [0.30 * colmesh_top * scale, ceiling],
                    "height_m": species["height_m"],
                    "lift": round(top + 2.0, 3),
                    "column_is_clear": True,
                    "local_grade": round(grade, 4),
                    "slope_allowance_m": round(0.35 * half * scale * grade + 0.005, 4),
                    "apex_offset_m": None,
                    "apex_z_m": None,
                }
            )
    return plan


def _lane_plan() -> list[dict[str, Any]]:
    """Every lane sector swept from r 262 to r 430 at three lateral offsets."""
    points = []
    for lane in tm.LANE_CENTRES:
        radius = fs.EVERYTHING_KEEPOUT_R
        while radius <= tm.LANE_CLEAR_R + 10.0:
            cx, cy = tm.bearing_point(lane, radius)
            normal = math.radians(lane + 90.0)
            for offset in LANE_OFFSETS_M:
                points.append(
                    {
                        "lane": lane,
                        "r": round(radius, 1),
                        "offset": offset,
                        "x": round(cx + offset * math.sin(normal), 3),
                        "y": round(cy + offset * math.cos(normal), 3),
                    }
                )
            radius += LANE_STEP_M
    return points


def _sightline_plan() -> list[dict[str, Any]]:
    """A ladder up the S1 sightline cone: nothing may stand between the eye and the lake."""
    eye, tip_a, tip_b = tm.sightline_cone()
    points = []
    for step in range(1, 61):
        t = step / 61.0
        for mix in (0.15, 0.5, 0.85):
            ax = tip_a[0] * mix + tip_b[0] * (1.0 - mix)
            ay = tip_a[1] * mix + tip_b[1] * (1.0 - mix)
            x = eye[0] + (ax - eye[0]) * t
            y = eye[1] + (ay - eye[1]) * t
            if tm.lake_e(x, y) < 1.02:
                continue
            points.append({"t": round(t, 3), "mix": mix, "x": round(x, 3), "y": round(y, 3)})
    return points


def _surface_rows(session: Session, points: list[dict[str, Any]], lift: float) -> list[dict]:
    """castRayStatic straight down from ``lift`` metres over the terrain, plus getTerrainHeight."""
    rows: list[dict[str, Any]] = []
    chunk = 220
    for start in range(0, len(points), chunk):
        block = points[start : start + chunk]
        body = " ".join(
            f"do local th = core_terrain.getTerrainHeight(vec3({p['x']}, {p['y']}, 0)); "
            f"local s = vec3({p['x']}, {p['y']}, th + {p.get('lift', lift)}); "
            f"local d = castRayStatic(s, vec3(0, 0, -1), {RAY_LENGTH}); "
            f"out[#out + 1] = {{ray_z = s.z - d, terrain_z = th, "
            f"hit = d < {RAY_LENGTH - 1.0}}} end "
            for p in block
        )
        answer = session.lua("local out = {}; " + body + "return jsonEncode({rows = out})")
        rows.extend(dict(r) for r in answer["rows"])
    return rows


# --------------------------------------------------- r4 (critic r3 M15): the frame-time probe
#: B3 raised the instance-weighted distance-mesh load 4.89x on the conifers over two rounds
#: and never timed a frame.  Design 9 defers the "0 frames over 33 ms" gate to B6, so this is
#: NOT a gate -- it is the baseline number B6 inherits, taken at the two cameras that matter:
#: the arena crest, where design 4.3 says the whole forest is imposters, and the forest floor,
#: where it is all near mesh.  The extension ships in a THROWAWAY probe archive that carries
#: nothing but this file, is never part of the release, and is deleted with the level zip.
# NB: `extensions.load('<dir>/<file>')` registers the module as `<dir>_<file>` with every
# underscore in <dir> DOUBLED, so the directory carries none.
B3_PERF_ID = "b3forestperf"
B3_PERF_EXTENSION = f"{B3_PERF_ID}_frames"
B3_PERF_LUA = """-- B3 r4 frame-time probe. A measurement, never a release.
local M = {}
local clock = os.clockhp or os.clock
local S
local function fresh()
  return {frames = 0, wall = 0, maxdt = 0, over16 = 0, over33 = 0,
          over66 = 0, last = nil, hist = {}}
end
S = fresh()
function M.b3Reset() S = fresh() end
function M.b3Snapshot()
  return {frames = S.frames, wall = S.wall, maxdt = S.maxdt, over16 = S.over16,
          over33 = S.over33, over66 = S.over66, hist = S.hist}
end
function M.onPreRender()
  local now = clock()
  if S.last ~= nil then
    local dt = now - S.last
    S.frames = S.frames + 1
    S.wall = S.wall + dt
    if dt > S.maxdt then S.maxdt = dt end
    if dt > 0.0167 then S.over16 = S.over16 + 1 end
    if dt > 0.0333 then S.over33 = S.over33 + 1 end
    if dt > 0.0667 then S.over66 = S.over66 + 1 end
    local bucket = math.min(21, math.floor(dt * 200) + 1)
    S.hist[bucket] = (S.hist[bucket] or 0) + 1
  end
  S.last = now
end
return M
"""


def _perf_probe_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        name = f"lua/ge/extensions/{B3_PERF_ID}/frames.lua"
        info = zipfile.ZipInfo(name, date_time=dist.ZIP_EPOCH)
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, B3_PERF_LUA)
    return buffer.getvalue()


def _time_the_frame(
    session: Session, label: str, eye, aim, seconds: float = 20.0
) -> dict[str, Any]:
    """Park the free camera and log every frame interval for `seconds` of real time."""
    session.lua(
        "commands.setFreeCamera(); "
        f"core_camera.setFOV(nil, {CAMERA_FOV_DEG}); "
        f"local eye = vec3({eye[0]}, {eye[1]}, {eye[2]}); "
        f"local aim = vec3({aim[0]}, {aim[1]}, {aim[2]}); "
        "local rotation = quatFromDir((aim - eye):normalized(), vec3(0, 0, 1)); "
        "core_camera.setPosRot(0, eye.x, eye.y, eye.z, rotation.x, rotation.y, rotation.z, "
        "rotation.w); return jsonEncode({ok = true})"
    )
    session.step(20)
    session.bng.control.resume()
    time.sleep(3.0)
    session.lua(f"extensions[{B3_PERF_EXTENSION!r}].b3Reset(); return jsonEncode({{ok = true}})")
    started = time.monotonic()
    time.sleep(seconds)
    snapshot = session.lua(f"return jsonEncode(extensions[{B3_PERF_EXTENSION!r}].b3Snapshot())")
    wall = time.monotonic() - started
    session.bng.control.pause()
    frames = int(snapshot.get("frames") or 0)
    return {
        "camera": label,
        "eye": [round(v, 2) for v in eye],
        "aim": [round(v, 2) for v in aim],
        "sampled_s": round(wall, 1),
        "frames": frames,
        "mean_frame_ms": round(1000.0 * float(snapshot.get("wall") or 0.0) / frames, 2)
        if frames
        else None,
        "fps": round(frames / wall, 1) if wall else None,
        "worst_frame_ms": round(1000.0 * float(snapshot.get("maxdt") or 0.0), 2),
        "frames_over_16_7ms": int(snapshot.get("over16") or 0),
        "frames_over_33ms": int(snapshot.get("over33") or 0),
        "frames_over_66ms": int(snapshot.get("over66") or 0),
        "histogram_5ms_buckets": snapshot.get("hist"),
    }


#: r5 (critic r4 M16).  Design §9's target is "60 fps AT THE 23-VEHICLE CENSUS" and r4's
#: baseline had no vehicles in it at all -- on a BeamNG level the vehicles are the dominant CPU
#: term, so a forest-only reading is a floor and not the number B6 compares against.  These are
#: parked, engine off, no AI and no arena under them (B5 has not built it), so this is still
#: not the census: it is the forest AND the vehicle physics, which is as close as B3 can get
#: from inside its own column.  Both readings are published; neither is a gate.
FRAME_TIME_VEHICLES = 23
FRAME_TIME_VEHICLE_MODEL = "pickup"


def _spawn_vehicles(session: Session, eye, count: int = FRAME_TIME_VEHICLES) -> dict[str, Any]:
    """Park `count` vehicles in a grid in front of the camera and report what spawned."""
    started = time.monotonic()
    result = session.lua(
        f"local n = {count}; local ok, err = pcall(function() "
        f"local base = vec3({eye[0]}, {eye[1]}, {eye[2]}); "
        "for i = 0, n - 1 do "
        "  local x = base.x + 6 * (i % 5) - 12; local y = base.y + 6 * math.floor(i / 5) + 14; "
        "  local z = base.z + 2; "
        f"  core_vehicles.spawnNewVehicle('{FRAME_TIME_VEHICLE_MODEL}', "
        "    {pos = vec3(x, y, z), rot = quat(0, 0, 0, 1), autoEnterVehicle = false, "
        "     cling = true}) "
        "end end); "
        "return jsonEncode({ok = ok, err = ok and '' or tostring(err)})"
    )
    for _ in range(40):
        session.step(30)
        time.sleep(0.5)
        alive = session.lua("return jsonEncode({n = be:getObjectCount()})")
        if int(alive.get("n") or 0) >= count:
            break
    return {
        "requested": count,
        "model": FRAME_TIME_VEHICLE_MODEL,
        "spawn_call": result,
        "objects_in_the_scene": int((alive or {}).get("n") or 0),
        "seconds": round(time.monotonic() - started, 1),
        "note": "parked, engine off, no AI, no arena geometry -- see FRAME_TIME_VEHICLES",
    }


@contextmanager
def _forest_boot(
    boot: str,
    tmp_path: Path,
    watchdog_seconds: float = 3000.0,
    archive: Path | None = None,
    payload: bytes | None = None,
    lock_sha: str | None = None,
    probe_zip: bytes | None = None,
) -> Iterator[Session]:
    """The scaffold's boot contract, with the archive parameterised for the BB:: probe."""
    home, user, binary = smoke._configured_runtime()
    # r2: B1 revision 2 re-cuts `dist_level/` in this same round, so B3 verifies against a zip
    # it cut to its OWN path and never claims that shared artifact.  The override is read-only
    # and defaults to the shared directory, so nothing else changes.
    dist_dir = Path(os.environ.get("B3_LEVEL_DIST_DIR") or dist.DEFAULT_OUTPUT_DIR)
    default_archive = dist_dir / dist.ZIP_NAME
    lock_path = dist_dir / dist.LOCK_NAME
    if not default_archive.is_file() or not lock_path.is_file():
        pytest.skip(
            "build the level dist first: python -m examples.hot_potato_arena.level.build_level_zip"
        )
    if payload is None:
        payload = smoke._locked_payload(default_archive, lock_path)
        lock_sha = json.loads(lock_path.read_text(encoding="utf-8"))["sha256"]
    # PREFLIGHT.  B1, B2, B4, B5 and B6 all re-cut the same dist_level archive in the same
    # round.  An archive built from a tree that predates the forest installs cleanly and then
    # logs "no forest files loaded" with 0 items -- which reads like a forest defect and is
    # not one (it cost this round one boot).  Refuse to launch unless the bytes about to be
    # installed actually carry B3's forest.
    with zipfile.ZipFile(io.BytesIO(payload)) as inspect:
        members = set(inspect.namelist())
    wanted = {
        f"levels/{LEVEL_ID}/{relative}"
        for relative in (
            *forest_build.forest4_members(),
            *forest_build.dae_members(),
            "art/forest/managedItemData.json",
        )
    }
    stale = sorted(wanted - members)
    if stale:
        pytest.fail(
            f"the level archive is missing {len(stale)} B3 forest members (e.g. {stale[:3]}): "
            "re-cut it with `python -m examples.hot_potato_arena.level.build_level_zip "
            "--overwrite` after the three forest build scripts"
        )
    evidence = _evidence_dir(tmp_path)
    shot_dir = evidence / "shots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:10]
    installed = require_confined_profile_target(user, Path("mods") / f"level_scaffold_{suffix}.zip")
    probe = (
        require_confined_profile_target(user, Path("mods") / f"{B3_PERF_ID}_{suffix}.zip")
        if probe_zip
        else None
    )
    log_path = user / "beamng.log"
    marker = f"forest_{boot}_{suffix}"
    started = time.monotonic()

    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(1))
        (tcom_port,) = reservation.ports
        mods_root = user / "mods"
        conflicts, stale = [], []
        if mods_root.is_dir():
            for candidate in sorted(mods_root.rglob("*.zip")):
                if candidate == installed:
                    continue
                if candidate.name.startswith("level_scaffold_"):
                    stale.append(str(candidate))
                    continue
                try:
                    with zipfile.ZipFile(candidate) as other:
                        if any(n.startswith(f"levels/{LEVEL_ID}/") for n in other.namelist()):
                            conflicts.append(str(candidate))
                except (zipfile.BadZipFile, OSError):
                    continue
        if conflicts or stale:
            pytest.fail(f"competing or stale level archives in the profile: {conflicts + stale}")
        # r3 (critic r2 H1): r2 left 46 files / 106.3 MB of cooked terrain DDS in the
        # sentinel's GLOBAL cache while a parallel round booted the same profile.  B3 purges
        # it BEFORE the boot as well as after, and records both, so the round cannot read
        # another cook's DDS and cannot leave its own behind.
        session_cache_before = _purge_terrain_material_cache(user)
        installed.parent.mkdir(parents=True, exist_ok=True)
        with installed.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if probe is not None and probe_zip is not None:
            with probe.open("xb") as handle:
                handle.write(probe_zip)
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
        owned_process: Any | None = None
        timer: threading.Timer | None = None
        session = Session(boot, bng, user, suffix, shot_dir)
        session.report["installed_zip"] = {
            "name": installed.name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "lock_sha256": lock_sha,
            "size": len(payload),
            "source": str(archive or default_archive),
        }
        session.report["profile"] = str(user)
        session.report["terrain_material_cache_before"] = session_cache_before
        session.scenario = None
        session.scenario_dir = None
        try:

            def watchdog() -> None:
                process = bng.process
                if process is not None and process.poll() is None:
                    process.terminate()

            timer = threading.Timer(watchdog_seconds, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            boot_started = time.monotonic()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)
            session.report["boot_to_menu_s"] = round(time.monotonic() - boot_started, 1)
            session.log_marker = marker
            yield session
            session.report["completed"] = True
        finally:
            try:
                cleanup_owned_beamng_session(
                    bng, owned_process=owned_process, scenario=session.scenario
                )
            finally:
                if timer is not None:
                    timer.cancel()
                for name in session.shot_names:
                    source = user / "screenshots" / f"{name}.png"
                    if source.is_file() and not (shot_dir / f"{name}.png").is_file():
                        shutil.copyfile(source, shot_dir / f"{name}.png")
                profile_shots = tuple(
                    user / "screenshots" / f"{name}.png" for name in session.shot_names
                )
                leftovers = (
                    (installed, *profile_shots)
                    if probe is None
                    else (
                        installed,
                        probe,
                        *profile_shots,
                    )
                )
                try:
                    cleanup_exact_live_artifacts(profile=user, files=leftovers)
                finally:
                    try:
                        session.report["profile_footprint"] = _purge_level_profile_footprint(user)
                    finally:
                        session.report["log_file"] = _settled_log(log_path)
                        session.report["log"] = _route_log_issues(log_path, marker)
                        session.report["wall_time_s"] = round(time.monotonic() - started, 1)
                        (evidence / f"evidence_{boot}.json").write_text(
                            json.dumps(session.report, indent=1, default=str, sort_keys=True),
                            encoding="utf-8",
                            newline="\n",
                        )


def _settled_log(log_path: Path, timeout_s: float = 25.0) -> dict[str, Any]:
    """Wait until BeamNG's log stops growing, then describe how complete it is.

    r2 certified a boot whose ``beamng.log`` cuts off mid-line at t = 223.35 s against a
    recorded ``wall_time_s`` of 273.9 -- roughly the last 50 s of the run is simply not in the
    file -- so every E and W count it reported was a LOWER BOUND asserted as a fact (critic r2
    M6).  The engine flushes asynchronously and the harness read the file the moment the
    process was told to quit.  This waits for the size to stop changing and then records
    whether the last line is terminated, so a truncated log is visible in the evidence instead
    of being invisible in it.
    """
    started = time.monotonic()
    last, stable = -1, 0.0
    while time.monotonic() - started < timeout_s:
        size = log_path.stat().st_size if log_path.is_file() else 0
        if size == last:
            stable += 0.25
            if stable >= 2.0:
                break
        else:
            stable, last = 0.0, size
        time.sleep(0.25)
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    lines = text.splitlines()
    return {
        "bytes": len(text),
        "lines": len(lines),
        "ends_with_newline": text.endswith("\n"),
        "last_line": lines[-1][:300] if lines else "",
        "settle_wait_s": round(time.monotonic() - started, 2),
    }


#: An |E| line that names one of these is NOT B3's to fix.  r2 declared "0 level-attributable
#: E lines" over a shipped DecalRoad carrying `inf` -- B1/B4's road, but B3's zero (critic r2
#: M5).  r3 keeps the count honest by ROUTING instead of filtering: every level-attributable
#: line is bucketed by owner and the other owners' lines are named in the evidence.
OTHER_OWNER_HINTS = {
    "B1/B4 (roads)": (
        "decalroad",
        "sceneStaticDecalRoadManager".casefold(),
        "track_surface",
        "m_dirt_variation",
    ),
    "B1 (terrain)": ("terrainblock", "_terrain.ter"),
    "B1 (backdrop/sky)": ("backdrop", "scatter_sky", "cloudlayer"),
}


def _route_log_issues(log_path: Path, marker: str) -> dict[str, Any]:
    """`_level_log_issues` plus the r3 routing, the non-finite scan and the GridMap count."""
    issues = dict(_level_log_issues(log_path, marker))
    text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    lines = text.splitlines()
    routed: dict[str, list[str]] = {}
    mine: list[str] = []
    for line in issues.get("level_attributable_errors", []):
        folded = line.casefold()
        owner = next(
            (who for who, hints in OTHER_OWNER_HINTS.items() if any(h in folded for h in hints)),
            None,
        )
        if owner:
            routed.setdefault(owner, []).append(line)
        else:
            mine.append(line)
    # a non-finite number reaching the engine from our own level is D1's bug class, wherever
    # it comes from: scan for it explicitly rather than hoping a hint list catches it
    nonfinite = [
        line
        for line in lines
        if "|e|" in line.casefold()
        and re.search(r"(?<![A-Za-z0-9_])(?:-?inf|nan)(?![A-Za-z0-9_])", line, re.IGNORECASE)
    ]
    issues["level_attributable_errors_mine"] = mine
    issues["level_attributable_errors_routed_to_other_builders"] = routed
    issues["non_finite_error_lines"] = nonfinite[:20]
    issues["non_finite_error_count"] = len(nonfinite)
    issues["non_finite_is_b3s"] = [
        line
        for line in nonfinite
        if not any(h in line.casefold() for hints in OTHER_OWNER_HINTS.values() for h in hints)
    ]
    # critic r2 M4: the engine's actual string, counted on THIS boot rather than corrected to
    # a constant -- it varies with how often the level list is scanned.
    issues["gridmap_no_entry_point_lines"] = sum(
        1 for line in lines if "No entry point for level found: /levels/GridMap" in line
    )
    return issues


def _settle_textures(session: Session, timeout_s: float = 240.0) -> dict[str, Any]:
    """Wait until the engine's TextureCooker stops writing DDS into ``temp/levels/<id>``.

    THE LAW THIS PAYS FOR: BeamNG cooks a level's PNGs to DDS lazily, on the frame that first
    needs them, and until a map is resident the surface wears the engine's checkered
    "IMPORTANT" placeholder.  B3 ships 146 maps totalling 300 MB, so a screenshot taken at the
    end of a 37 s boot photographs a half-cooked forest -- which is exactly what the first two
    frame sets showed, and it is not a material defect.  Every frame below waits for the count
    to stand still first.
    """
    temp_root = session.user / "temp" / "levels" / LEVEL_ID
    started = time.monotonic()
    counts: list[int] = []
    while time.monotonic() - started < timeout_s:
        session.step(30)
        current = sum(1 for _ in temp_root.rglob("*.dds")) if temp_root.is_dir() else 0
        counts.append(current)
        if len(counts) >= 4 and len(set(counts[-4:])) == 1 and current > 0:
            break
        time.sleep(0.75)
    return {
        "cooked_dds_in_temp": counts[-1] if counts else 0,
        "polls": len(counts),
        "seconds": round(time.monotonic() - started, 1),
        "stable": len(counts) >= 4 and len(set(counts[-4:])) == 1,
        "poll_counts": counts,
    }


def _cooked_dds_census(session: Session) -> dict[str, Any]:
    """Every DDS the engine cooked for this level, by size and mip count.

    Diagnoses M3, the one unexplained level-attributable warning of r1:
    ``dds mip chain (12) does not match texture (11) for ... F_PINE_TWIG_B_B.COLOR.DDS,
    skipping stream-in``.  12 mips is a 2048 chain and 11 is a 1024 chain, so the engine's
    streamable-texture OBJECT was built for a 1024 texture while the file on disk had grown to
    the full 2048 chain -- i.e. the object was created from a partly-cooked file.  If that is
    right then (a) the file's own header says 2048/12 once the cooker is quiet, and (b) which
    file loses the race varies from boot to boot.  Both are recorded here.
    """
    temp_root = session.user / "temp" / "levels" / LEVEL_ID
    rows: list[dict[str, Any]] = []
    if temp_root.is_dir():
        for path in sorted(temp_root.rglob("*.dds")):
            try:
                header = dds_header(path.read_bytes()[:148])
            except Exception as error:
                rows.append({"file": path.name, "error": str(error)})
                continue
            rows.append(
                {
                    "file": path.name,
                    "width": header["width"],
                    "height": header["height"],
                    "mips": header["mip_count"],
                    "bytes": path.stat().st_size,
                }
            )
    by_size: dict[str, int] = {}
    mismatched = []
    for row in rows:
        if "width" not in row:
            continue
        key = f"{row['width']}x{row['height']}:{row['mips']}mips"
        by_size[key] = by_size.get(key, 0) + 1
        expected = max(1, int(math.log2(max(row["width"], row["height"]))) + 1)
        if row["mips"] != expected:
            mismatched.append(row)
    # r4 (critic r3 M12): the r3 boot logged the warning TWICE, on `f_pine_bark_b.color` and
    # `f_fir_bark_b.color`, where critic r2 verified zero occurrences naming a B3 asset in the
    # r2 boot.  So the diagnosis is re-checked here against the log itself, not against a
    # hand-picked file: every name the mip-chain warning mentions is looked up in the cooked
    # tree AFTER the cooker went quiet, and its own header is recorded beside the warning.
    named = sorted(
        {
            match.group(1).rsplit("/", 1)[-1].rsplit("\\", 1)[-1].upper()
            for line in _mip_chain_warning_lines(session)
            for match in [re.search(r"for\s+(\S+\.DDS)", line, re.I)]
            if match
        }
    )
    return {
        "files": len(rows),
        "by_size_and_mips": dict(sorted(by_size.items())),
        "files_whose_own_chain_is_short": mismatched[:10],
        "twig_b": [r for r in rows if "PINE_TWIG_B" in r["file"].upper()],
        "warned_about_by_the_log": named,
        "headers_of_the_files_the_log_warned_about": [
            r for r in rows if r.get("file", "").upper() in named
        ],
        "bark_b": [r for r in rows if "_BARK_B.COLOR" in r["file"].upper()],
    }


def _mip_chain_warning_lines(session: Session) -> list[str]:
    """Every `dds mip chain ... skipping stream-in` line in the log so far."""
    log = session.user / "beamng.log"
    if not log.is_file():
        return []
    text = log.read_text(encoding="utf-8", errors="replace")
    return [line for line in text.splitlines() if "dds mip chain" in line.lower()]


def _load_level(session: Session, tag: str) -> None:
    bng = session.bng
    levels = bng.scenario.get_levels()
    assert LEVEL_ID in levels, sorted(levels)
    scenario = Scenario(LEVEL_ID, f"{LEVEL_ID}_{tag}")
    vehicle = Vehicle(f"{LEVEL_ID}_forest_probe", model="etk800", licence="B3")
    spawn = writer.spawn_position()
    scenario.add_vehicle(vehicle, pos=(spawn[0], spawn[1], spawn[2]), rot_quat=(0, 0, 0, 1))
    started = time.monotonic()
    bng.control.pause()
    scenario.make(bng)
    session.scenario = scenario
    bng.scenario.load(scenario, precompile_shaders=False)
    bng.scenario.start()
    bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
    bng.control.pause()
    session.register(vehicle)
    session.step(4)
    session.report["level_load_s"] = round(time.monotonic() - started, 1)
    session.lua(
        f"core_environment.setTimeOfDay({{time = {GOLDEN_CLOCK}}}); "
        "return jsonEncode({ok = true})"
    )
    session.step(12)
    session.marker(session.log_marker)


#: How long the `updateImposters` experiment polls for a write that never comes.
UPDATE_IMPOSTERS_POLLS = 120
UPDATE_IMPOSTERS_SLEEP_S = 0.75


def _update_imposters_write_set(session: Session, delete: int = 6) -> dict[str, Any]:
    """THE experiment behind engine law (a), preserved as a measurement (critic r4 B1).

    r4 asserted "``Engine.Render.updateImposters(true)`` does not rebuild: with the cache
    deleted it wrote nothing at all across 400 polls / 7 minutes" and preserved it as
    ``{"err": "", "ok": true}`` -- the return of one Lua call, with no poll count, no elapsed
    time and no write-set.  A law nobody can re-read is a law the next round re-pays for.

    So: delete `delete` atlases out of the engine's own cache, call ``updateImposters(true)``,
    and record exactly which files come back over a bounded poll -- the deleted list, the
    polls, the seconds and the write-set.  The expected answer is that the write-set is EMPTY
    and the atlases only return at the next level LOAD, which is why the bake is
    load-cook-delete-load.
    """
    user = session.user
    temp_root = user / "temp" / "levels" / LEVEL_ID
    before = sorted(str(p.relative_to(user)) for p in temp_root.rglob("*.imposter*.dds"))
    removed = []
    for name in before[:delete]:
        try:
            (user / name).unlink()
            removed.append(name)
        except OSError:
            pass
    started = time.monotonic()
    call = session.lua(
        "local ok, err = pcall(function() Engine.Render.updateImposters(true) end); "
        "return jsonEncode({ok = ok, err = ok and '' or tostring(err)})"
    )
    polls, returned = 0, []
    for attempt in range(1, UPDATE_IMPOSTERS_POLLS + 1):
        polls = attempt
        session.step(30)
        time.sleep(UPDATE_IMPOSTERS_SLEEP_S)
        now = {str(p.relative_to(user)) for p in temp_root.rglob("*.imposter*.dds")}
        returned = sorted(name for name in removed if name in now)
        if returned:
            break
    return {
        "deleted_from_the_engine_cache": removed,
        "updateImposters": call,
        "polls": polls,
        "seconds": round(time.monotonic() - started, 1),
        "atlases_it_wrote_back": returned,
        "atlases_in_the_cache_before": len(before),
        "atlases_in_the_cache_after": sum(1 for _ in temp_root.rglob("*.imposter*.dds")),
        "verdict": (
            "updateImposters(true) rebuilt nothing; the engine only bakes at level LOAD"
            if not returned
            else "updateImposters(true) DID rebuild -- engine law (a) is wrong"
        ),
    }


def _imposter_manifest_rows(harvested: list[dict[str, Any]]) -> dict[str, Any]:
    """r4 (critic r3 D8): record, per baked atlas, the DAE it was baked FROM.

    All 54 shipped ``*.dae.imposter.dds`` were byte-identical across r1, r2 and r3 while the
    conifers under them were rebuilt twice -- so the billboard the forest is drawn with past
    262 m still depicted r1's geometry.  Nothing could catch that, because nothing recorded
    what the bake was a bake OF.  This manifest is what the static freshness gate reads.
    """
    rows: dict[str, Any] = {}
    for entry in harvested:
        relative = entry["level_path"]
        dae = relative.rsplit(".imposter", 1)[0]
        source = LEVEL_ROOT / dae
        row = {k: v for k, v in entry.items() if k != "profile_path"}
        row["dae"] = dae
        row["dae_sha256"] = (
            hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else None
        )
        if relative.endswith(".dae.imposter.dds"):
            try:
                row["reading"] = forest_build.imposter_reading((LEVEL_ROOT / relative).read_bytes())
            except Exception as exc:  # recorded, never fatal in a boot
                row["reading"] = {"error": str(exc)}
        rows[relative] = row
    return rows


def _harvest_imposters(
    session: Session, expected_pairs: int, force: bool = False
) -> dict[str, Any]:
    """Generate the atlases, copy every one BESIDE ITS DAE, and read its DDS header.

    ``force`` deletes what the engine already cached in ``temp/`` before asking for the bake.
    THE LAW THAT COSTS: the engine rebuilds an imposter AT LEVEL LOAD whenever the DAE is
    newer than the cached atlas -- MEASURED, at 28-71 s into a 174 s load, which is long
    before the texture cooker has produced the 146 maps.  Every alphaTest conifer therefore
    baked as a completely EMPTY billboard (alpha max 0) while the opaque rocks came out fine,
    and ``updateImposters(true)`` afterwards did nothing because the file it would write was
    already newer than the shape.  Deleting the cache first is what makes the re-bake real.
    """
    user = session.user
    temp_root = user / "temp" / "levels" / LEVEL_ID
    before = sorted(str(p.relative_to(user)) for p in user.rglob("*.imposter*.dds"))
    dropped = []
    if force and temp_root.is_dir():
        for stale_atlas in sorted(temp_root.rglob("*.imposter*.dds")):
            try:
                stale_atlas.unlink()
                dropped.append(str(stale_atlas.relative_to(user)))
            except OSError:
                pass
        session.step(10)
    call = session.lua(
        "local ok, err = pcall(function() Engine.Render.updateImposters(true) end); "
        "return jsonEncode({ok = ok, err = ok and '' or tostring(err)})"
    )
    found: list[Path] = []
    polls, stable = 0, False
    for attempt in range(1, 401):
        polls = attempt
        session.step(30)
        time.sleep(0.5)
        current = sorted(p for p in user.rglob("*.imposter*.dds"))
        if len(current) >= 2 * expected_pairs:
            sizes = {p: p.stat().st_size for p in current}
            time.sleep(1.5)
            if all(
                p.is_file() and p.stat().st_size == size and size > 0 for p, size in sizes.items()
            ):
                found, stable = current, True
                break
        found = current
    harvested: list[dict[str, Any]] = []
    for path in found:
        try:
            relative = path.relative_to(temp_root)
        except ValueError:
            continue
        target = LEVEL_ROOT / relative
        if not target.parent.is_dir():
            continue
        blob = path.read_bytes()
        target.write_bytes(blob)
        harvested.append(
            {
                "profile_path": str(path.relative_to(user)),
                "level_path": str(relative).replace("\\", "/"),
                "sha256": hashlib.sha256(blob).hexdigest(),
                **dds_header(blob),
            }
        )
    listing = (
        sorted(str(p.relative_to(user)) for p in temp_root.rglob("*") if p.is_file())
        if temp_root.is_dir()
        else []
    )
    # An atlas the level already SHIPS is never regenerated (stock ships them; that is the end
    # state B6 packages).  The gate is the UNION: every billboarded shape must own a 512 x 256
    # pair, whether it came out of temp/ this boot or was already beside its DAE.
    shipped = []
    for relative in forest_build.dae_members():
        for suffix in (".imposter.dds", ".imposter_normals.dds"):
            atlas = LEVEL_ROOT / (relative + suffix)
            if atlas.is_file():
                blob = atlas.read_bytes()
                shipped.append(
                    {
                        "level_path": relative + suffix,
                        "sha256": hashlib.sha256(blob).hexdigest(),
                        "source": "shipped",
                        **dds_header(blob),
                    }
                )
    for row in shipped:
        if row["level_path"].endswith(".dae.imposter.dds"):
            try:
                row["reading"] = forest_build.imposter_reading(
                    (LEVEL_ROOT / row["level_path"]).read_bytes()
                )
            except Exception as exc:  # recorded, never fatal in a boot
                row["reading"] = {"error": str(exc)}
    return {
        "atlases_in_the_level_tree_after_the_copy": shipped,
        "updateImposters": call,
        "polls": polls,
        "stable": stable,
        "profile_atlases_when_the_harvest_began": before,
        "cached_atlases_deleted_before_the_bake": dropped,
        "harvested": harvested,
        "pairs": len([h for h in harvested if h["level_path"].endswith(".dae.imposter.dds")]),
        "temp_listing_count": len(listing),
        "temp_listing_suffixes": sorted({Path(n).suffix for n in listing}),
    }


@pytest.mark.beamng_live
def test_forest_live_proofs(tmp_path: Path) -> None:
    plan = _ray_census_plan()
    lane_points = _lane_plan()
    sightline_points = _sightline_plan()
    expected_total = sum(forest_build.plant_manifest()["per_species"].values())
    billboarded = [s for s in fs.SPECIES if s["bb"]]

    with _forest_boot("forest", tmp_path, probe_zip=_perf_probe_bytes()) as s:
        _load_level(s, "b3_forest")

        # --- F1 the forest the engine loaded is the forest the JSON ships ---------------
        names = [fs.datablock_name(species) for species in fs.SPECIES]
        body = " ".join(
            f"do local d = scenetree.findObject({name!r}); out[{name!r}] = d and "
            "{class = d:getClassName(), shapeFile = d:getField('shapeFile', 0), "
            "annotation = d:getField('annotation', 0), radius = d:getField('radius', 0), "
            "windScale = d:getField('windScale', 0)} or false end "
            for name in names
        )
        cover_names = [f"{LEVEL_ID}_{cover['name']}" for cover in fs.GROUND_COVERS]
        cover_names.append(fs.WIND_EMITTER["name"])
        cover_body = " ".join(
            f"do local o = scenetree.findObject({name!r}); covers[{name!r}] = o and "
            "{class = o:getClassName(), maxElements = o:getField('maxElements', 0), "
            "radius = o:getField('radius', 0)} or false end "
            for name in cover_names
        )
        census = s.lua(
            "local out = {}; local covers = {}; "
            + body
            + cover_body
            + "local f = core_forest.getForestObject(); "
            "local n = f and #(f:getData():getItems()) or -1; "
            "local veg = scenetree.findObject('theForest'); "
            "return jsonEncode({items = out, forest_count = n, covers = covers, "
            "forest_object = veg and veg:getClassName() or false})"
        )
        s.report["f1_forest_census"] = {
            "live_instances": census["forest_count"],
            "json_instances": expected_total,
            "forest_object": census["forest_object"],
            "ground_covers": sum(
                1 for row in census["covers"].values() if row and row["class"] == "GroundCover"
            ),
            "wind_emitters": sum(
                1
                for row in census["covers"].values()
                if row and row["class"] == "ForestWindEmitter"
            ),
            "covers": census["covers"],
            "datablocks_found": sum(1 for row in census["items"].values() if row),
            "datablocks": census["items"],
        }
        s.check(census["forest_object"] == "Forest", "theForest is not a Forest", census)
        s.check(
            int(census["forest_count"]) == expected_total,
            "live forest count != the shipped forest4 row count",
            {"live": census["forest_count"], "json": expected_total},
        )
        s.check(
            s.report["f1_forest_census"]["ground_covers"] == len(fs.GROUND_COVERS),
            "GroundCover count",
            census["covers"],
        )
        s.check(
            s.report["f1_forest_census"]["wind_emitters"] == 1,
            "ForestWindEmitter count",
            census["covers"],
        )
        for name, row in census["items"].items():
            # the engine's own class name for a TSForestItemData record is "forestItemData"
            # (measured: getClassName() on all 54 in the first forest boot)
            s.check(
                bool(row) and row["class"] in ("forestItemData", "TSForestItemData"),
                f"datablock missing or wrong class: {name}",
                row,
            )

        # --- F2 imposter harvest --------------------------------------------------------
        harvest = _harvest_imposters(s, len(billboarded))
        s.report["f2_imposters"] = harvest
        atlases = {
            row["level_path"]: row
            for row in (*harvest["atlases_in_the_level_tree_after_the_copy"], *harvest["harvested"])
        }
        colour = [h for h in atlases.values() if h["level_path"].endswith(".dae.imposter.dds")]
        normals = [
            h for h in atlases.values() if h["level_path"].endswith(".dae.imposter_normals.dds")
        ]
        s.report["f2_summary"] = {
            "colour_atlases": len(colour),
            "normal_atlases": len(normals),
            "expected_pairs": len(billboarded),
            "harvested_this_boot": len(harvest["harvested"]),
            "in_the_level_tree_after_the_copy": len(
                harvest["atlases_in_the_level_tree_after_the_copy"]
            ),
            "sizes": sorted({f"{h['width']}x{h['height']}" for h in atlases.values()}),
            "fourcc": sorted({h["fourcc"] for h in atlases.values()}),
            "mips": sorted({h["mip_count"] for h in atlases.values()}),
        }
        s.check(
            len(colour) == len(billboarded),
            "not every bb_autobillboard shape got its atlas",
            {"got": len(colour), "want": len(billboarded)},
        )
        # r4 (critic r3 D8): the size is now MEASURED rather than asserted at r1's 512 x 256 --
        # `BB::EQUATOR_STEPS=8` + `BB::POLAR_STEPS=1` asks the engine for 26 views instead of
        # 6, and how it packs them is the engine's call.  What IS asserted is that every atlas
        # agrees with every other, that its smaller side clears QB-9b's 512, and that the
        # billboard actually carries the views the shape declares.
        s.check(
            len(s.report["f2_summary"]["sizes"]) == 1,
            "the atlases are not all the same size",
            s.report["f2_summary"]["sizes"],
        )
        s.check(
            bool(atlases) and all(min(h["width"], h["height"]) >= 512 for h in atlases.values()),
            "QB-9b: an atlas is under 512 px on its smaller side",
            s.report["f2_summary"]["sizes"],
        )
        readings = {
            row["level_path"]: row["reading"]
            for row in colour
            if isinstance(row.get("reading"), dict) and "cells_used" in row["reading"]
        }
        # r5 (critic r4 B4-iii): these two fields were BUILT from `cells_touched` and WRITTEN
        # OUT as `cells_used_min/_max`, so the evidence read 32/32 while the manifest's own
        # per-atlas `cells_used` ranged 26-32.  Both numbers are now reported under their own
        # names -- `touched` is the weak question the gate asks (did the view render at all?)
        # and `used` is critic r3's stricter convention (more than 0.2 % of the cell opaque).
        touched = sorted(r["cells_touched"] for r in readings.values())
        used = sorted(r["cells_used"] for r in readings.values())
        fills = sorted(r["bbox_fill_median"] for r in readings.values())
        equator = sorted(r["bbox_fill_equator_median"] for r in readings.values())
        poles = sorted({len(r["polar_cells"]) for r in readings.values()})
        s.report["f2_billboard_look"] = {
            "measured": len(readings),
            "views_declared": fs.BB_VIEWS,
            "cells_touched_min": touched[0] if touched else 0,
            "cells_touched_max": touched[-1] if touched else 0,
            "cells_used_min": used[0] if used else 0,
            "cells_used_max": used[-1] if used else 0,
            "grid": sorted({f"{r['cells']} cells of {r['cell']} px" for r in readings.values()}),
            "bbox_fill_median_min": fills[0] if fills else 0.0,
            # r9: true medians (B1 r9's CORRECTION_forest_medians.md), not upper medians
            "bbox_fill_median_p50": statistics.median(fills) if fills else 0.0,
            "bbox_fill_median_max": fills[-1] if fills else 0.0,
            # ...and the same three over the EQUATOR RING only, which is the number a ground
            # camera meets: a polar cell is a plan view of a spire and is correctly a small
            # disc, so a whole-atlas minimum understates the billboard (critic r4 B2).
            "bbox_fill_equator_median_min": equator[0] if equator else 0.0,
            "bbox_fill_equator_median_p50": statistics.median(equator) if equator else 0.0,
            "bbox_fill_equator_median_max": equator[-1] if equator else 0.0,
            "polar_cells_per_atlas": poles,
            "note": "critic r3 D8: r1's bake read 4-6 of 8 cells and 0.054-0.138 bbox fill",
        }
        s.check(
            bool(touched) and touched[0] >= fs.BB_VIEWS,
            "an atlas carries fewer view cells than the shape declares",
            s.report["f2_billboard_look"],
        )

        # --- F3 ray census on 20 instances ---------------------------------------------
        rows = _surface_rows(
            s,
            [{"x": p["x"] + p["lateral_offset_m"], "y": p["y"], "lift": p["lift"]} for p in plan],
            RAY_START_LIFT,
        )
        for entry, row in zip(plan, rows, strict=True):
            entry["ray_z"] = round(float(row["ray_z"]), 4)
            entry["terrain_z"] = round(float(row["terrain_z"]), 4)
            entry["hit"] = bool(row["hit"])
            entry["above_terrain_m"] = round(entry["ray_z"] - entry["terrain_z"], 4)
            if entry["kind"] == "drive_through":
                entry["ok"] = abs(entry["above_terrain_m"]) <= LANE_CLEAR_TOLERANCE_M
            else:
                low, high = entry["window"]
                value = entry["above_terrain_m"]
                # Report how far INSIDE the window the reading is, signed and in metres, so
                # "20/20 inside their window" cannot hide a row that is only inside by the
                # declared tolerance (r1's `dwarf_pine_alpine` was 0.6 mm below its bound).
                #
                # And MODEL the tolerance instead of picking one: `above_terrain_m` is the
                # ray's hit minus the terrain UNDER THE RAY, while the window is about the
                # shape standing on the terrain under its own ORIGIN.  On a slope those two
                # ground heights differ by `lateral_offset x grade`, which is the whole of the
                # few-millimetre shortfall r1 papered over with a flat 0.05 m.
                allowance = round(entry["slope_allowance_m"], 4)
                entry["window_margin_m"] = round(min(value - low, high - value), 4)
                entry["window_width_m"] = round(high - low, 4)
                entry["ok"] = low - allowance <= value <= high + allowance
                entry["ok_without_tolerance"] = low <= value <= high
        # a second, NEAR-AXIS ray on every generated conifer: does the Colmesh cone's apex sit
        # where forest_spec.colmesh_profile says?  Recorded, not gated.
        cone = [p for p in plan if p["apex_offset_m"] is not None]
        apex_rows = _surface_rows(
            s,
            [{"x": p["x"] + p["apex_offset_m"], "y": p["y"], "lift": p["lift"]} for p in cone],
            RAY_START_LIFT,
        )
        for entry, row in zip(cone, apex_rows, strict=True):
            entry["apex_ray_above_terrain_m"] = round(
                float(row["ray_z"]) - float(row["terrain_z"]), 4
            )
            entry["apex_ray_error_m"] = round(
                entry["apex_ray_above_terrain_m"] - entry["apex_z_m"], 4
            )
        s.report["f3_ray_census"] = {
            "instances": plan,
            "hits_in_window": sum(1 for p in plan if p["ok"]),
            "n": len(plan),
            "apex_rays": len(cone),
            "worst_apex_error_m": max((abs(p["apex_ray_error_m"]) for p in cone), default=None),
            "hits_inside_without_the_modelled_slope_allowance": sum(
                1 for p in plan if p.get("ok_without_tolerance")
            ),
            "gated_rays": sum(1 for p in plan if p["kind"] != "drive_through"),
            "narrowest_window_m": min(
                (p["window_width_m"] for p in plan if "window_width_m" in p), default=None
            ),
            "widest_window_m": max(
                (p["window_width_m"] for p in plan if "window_width_m" in p), default=None
            ),
            "tightest_margin_m": min(
                (p["window_margin_m"] for p in plan if "window_margin_m" in p), default=None
            ),
            "largest_slope_allowance_m": max(
                (p["slope_allowance_m"] for p in plan if "slope_allowance_m" in p), default=None
            ),
        }
        for entry in plan:
            s.check(entry["ok"], f"ray census miss on {entry['species']}", entry)

        # --- F4 lane keep-out and the S1 sightline corridor ------------------------------
        lane_rows = _surface_rows(s, lane_points, 30.0)
        worst_lane = None
        breaches = []
        for point, row in zip(lane_points, lane_rows, strict=True):
            above = float(row["ray_z"]) - float(row["terrain_z"])
            point["above_terrain_m"] = round(above, 4)
            if worst_lane is None or above > worst_lane["above_terrain_m"]:
                worst_lane = point
            if point["r"] <= tm.LANE_CLEAR_R and above > LANE_CLEAR_TOLERANCE_M:
                breaches.append(point)
        s.report["f4_lane_keepout"] = {
            "points": len(lane_points),
            "lanes": list(tm.LANE_CENTRES),
            "r_from": fs.EVERYTHING_KEEPOUT_R,
            "r_to": tm.LANE_CLEAR_R + 10.0,
            "tolerance_m": LANE_CLEAR_TOLERANCE_M,
            "worst_inside_the_clearing": worst_lane,
            "breaches": breaches[:20],
            "breach_count": len(breaches),
            "lane_240_points": sum(1 for p in lane_points if p["lane"] == 240.0),
        }
        s.check(
            not breaches, "something stands above the terrain inside a lane runout", breaches[:5]
        )

        cone_rows = _surface_rows(s, sightline_points, 30.0)
        cone_breaches = []
        for point, row in zip(sightline_points, cone_rows, strict=True):
            above = float(row["ray_z"]) - float(row["terrain_z"])
            point["above_terrain_m"] = round(above, 4)
            if above > LANE_CLEAR_TOLERANCE_M:
                cone_breaches.append(point)
        s.report["f4_sightline_cone"] = {
            "points": len(sightline_points),
            "breaches": cone_breaches[:20],
            "breach_count": len(cone_breaches),
        }
        s.check(not cone_breaches, "something stands in the S1 sightline cone", cone_breaches[:5])

        # --- F5 the truth frames --------------------------------------------------------
        # look at the forest first so the cooker is asked for the foliage maps, then wait for
        # it to finish: a frame taken mid-cook photographs the engine's placeholder material
        s.lua(
            "commands.setFreeCamera(); "
            f"core_camera.setFOV(nil, {CAMERA_FOV_DEG}); "
            "local eye = vec3(997.1, 124.1, 108.7); local aim = vec3(1041.2, 149.4, 119.2); "
            "local rotation = quatFromDir((aim - eye):normalized(), vec3(0, 0, 1)); "
            "core_camera.setPosRot(0, eye.x, eye.y, eye.z, rotation.x, rotation.y, rotation.z, "
            "rotation.w); return jsonEncode({ok = true})"
        )
        s.report["f5_texture_settle"] = _settle_textures(s)
        s.check(
            s.report["f5_texture_settle"]["stable"],
            "the texture cooker never went quiet; the frames may show placeholders",
            s.report["f5_texture_settle"],
        )
        # M3: what the cooker actually produced, so the "mip chain does not match texture"
        # warning has a measurement beside it rather than a shrug.
        s.report["f8_cooked_dds"] = _cooked_dds_census(s)
        for name, eye, aim, clock, note in FRAMES:
            s.lua(
                f"core_environment.setTimeOfDay({{time = {clock}}}); "
                "return jsonEncode({ok = true})"
            )
            s.step(20)
            s.shot(name, eye, aim, note)
            _settle_textures(s, timeout_s=60.0)
            s.shot(name, eye, aim, note)

        # a frame 150 m off the tree line: near trees are _a100 meshes, far ones imposters
        # stand on the meadow inside the clearing and look ALONG the tree line, so the same
        # wall of trees runs from ~60 m (an _a600/_a300 mesh) out past 262 m (the bb25 imposter)
        seam_eye_xy = tm.bearing_point(285.0, 300.0)
        seam_aim_xy = tm.bearing_point(337.0, 780.0)
        seam_eye_z = terrain.surface_z(*seam_eye_xy) + 2.5
        seam_aim_z = terrain.surface_z(*seam_aim_xy) + 25.0
        nearest = min(
            math.hypot(row["pos"][0] - seam_eye_xy[0], row["pos"][1] - seam_eye_xy[1])
            for name in list(forest_build.plant_manifest()["per_species"])[:8]
            for row in _instances(name)[::37]
        )
        s.report["f5_lod_seam"] = {
            "eye": [round(v, 2) for v in (*seam_eye_xy, seam_eye_z)],
            "aim": [round(v, 2) for v in (*seam_aim_xy, seam_aim_z)],
            "nearest_sampled_instance_m": round(nearest, 1),
            "imposter_engages_beyond_m": 262,
            "note": "design §4.3: _a100 holds to 262 m, the bb25 imposter from there to 1,047 m",
        }
        s.lua(
            f"core_environment.setTimeOfDay({{time = {GOLDEN_CLOCK}}}); "
            "return jsonEncode({ok = true})"
        )
        s.step(20)
        s.shot(
            "s7b_lod_seam",
            (*seam_eye_xy, seam_eye_z),
            (*seam_aim_xy, seam_aim_z),
            "150 m off the tree line: _a100 meshes in front, bb25 imposters behind",
        )
        line_eye_xy = tm.bearing_point(300.0, 248.0)
        line_aim_xy = tm.bearing_point(300.0, 760.0)
        s.shot(
            "tree_line_from_the_track",
            (*line_eye_xy, terrain.surface_z(*line_eye_xy) + 1.6),
            (*line_aim_xy, terrain.surface_z(*line_aim_xy) + 45.0),
            "from the campsite track at r 248: the meadow, the tree line at r 350 and the "
            "forest climbing the NW wall",
        )
        s.shot(
            "forest_from_the_crest",
            (1452.1, 437.6, 284.4),
            (850.0, -280.0, 100.0),
            "the whole forest from the ridge crest at the golden-hour clock",
        )
        # r4 (critic r3 D8): the frame the round had never taken.  Design §4.3 -- "from the
        # arena every tree is >= 260 m away, so the whole forest renders as imposters" -- so
        # this eye stands on the arena's own crest at r 91 and looks straight out across the
        # tree line.  EVERYTHING in it past the meadow is billboard: it is the read the game
        # is played against, and the only frame that shows the bake rather than the mesh.
        band_eye_xy = tm.bearing_point(300.0, 91.0)
        band_aim_xy = tm.bearing_point(300.0, 620.0)
        band_eye = (*band_eye_xy, terrain.surface_z(*band_eye_xy) + 2.0)
        band_aim = (*band_aim_xy, terrain.surface_z(*band_aim_xy) + 22.0)
        s.report["f5_imposter_band"] = {
            "eye": [round(v, 2) for v in band_eye],
            "aim": [round(v, 2) for v in band_aim],
            "tree_line_at_m": round(math.dist(band_eye_xy, tm.bearing_point(300.0, 350.0)), 1),
            "imposter_engages_beyond_m": 262,
            "note": "design §4.3: from the arena every tree is an imposter or an _a100 mesh",
        }
        s.shot(
            "arena_imposter_band",
            band_eye,
            band_aim,
            "from the arena crest at r 91: every tree in the frame is a bb25 imposter",
        )

        # --- r4 (critic r3 M15): the frame the round had never timed --------------------
        loaded = s.lua(
            f"local ok, err = pcall(extensions.load, '{B3_PERF_ID}/frames'); "
            "return jsonEncode({ok = ok == true, err = tostring(err)})"
        )
        s.report["f9_frame_time"] = {"probe_loaded": loaded}
        try:
            s.report["f9_frame_time"]["cameras"] = [
                _time_the_frame(s, "arena crest, the forest as imposters", band_eye, band_aim),
                _time_the_frame(
                    s,
                    "S7 forest floor, the forest as near mesh",
                    FRAMES[0][1],
                    FRAMES[0][2],
                ),
                _time_the_frame(
                    s, "S8 trail switchback, 600 m above the hearth", FRAMES[2][1], FRAMES[2][2]
                ),
            ]
            s.report["f9_frame_time"]["note"] = (
                "NOT a gate -- design §9 defers the 0-frames-over-33 ms rule to B6.  These "
                "three are a NO-VEHICLE, vsync-locked FLOOR at 1920 x 1080 headless with the "
                "forest loaded and nothing else: no arena, no hearth, no night lights and no "
                "vehicles.  16.67 ms IS the 60 Hz cap, so what they say is that the forest "
                "does not break the cap, not how much headroom is left.  Design §9's target "
                "is stated at the 23-VEHICLE census; `with_vehicles` below is as close to it "
                "as B3 can get, and the census number itself is B6's to measure."
            )
            # r5 (critic r4 M16): the same camera again, with vehicles in the scene.
            s.report["f9_frame_time"]["vehicles"] = _spawn_vehicles(s, band_eye)
            s.report["f9_frame_time"]["with_vehicles"] = [
                _time_the_frame(
                    s, f"arena crest + {FRAME_TIME_VEHICLES} parked vehicles", band_eye, band_aim
                ),
                _time_the_frame(
                    s,
                    f"S7 forest floor + {FRAME_TIME_VEHICLES} parked vehicles",
                    FRAMES[0][1],
                    FRAMES[0][2],
                ),
            ]
        except Exception as error:  # a measurement, never a reason to fail the certification
            s.report["f9_frame_time"]["error"] = repr(error)
            s.bng.control.pause()

    evidence = json.loads(
        (_evidence_dir(tmp_path) / "evidence_forest.json").read_text(encoding="utf-8")
    )
    assert evidence.get("completed") is True, evidence.get("problems")
    # r3 (critic r2 M5): the gate is on the lines B3 OWNS.  Lines that name another builder's
    # object are routed and named in the evidence rather than filtered into a zero -- r2
    # asserted "0 level-attributable E lines" while a shipped DecalRoad was handing the engine
    # `inf`, one round after D1 was exactly that bug class.
    assert not evidence["log"]["level_attributable_errors_mine"], evidence["log"]
    assert not evidence["log"]["non_finite_is_b3s"], evidence["log"]["non_finite_error_lines"]
    assert not evidence["problems"], evidence["problems"]


# ------------------------------------------------------------- r4: the imposter RE-BAKE boot
REBAKE_ENV = "HOT_POTATO_FOREST_REBAKE"


def _archive_without_atlases(destination: Path) -> bytes:
    """The certified zip with every ``*.imposter*.dds`` member DROPPED.

    An atlas the level already ships is never regenerated -- the engine finds it beside the
    DAE and uses it, which is why ``updateImposters(true)`` harvested 0 in r2 and r3 and the
    forest past 262 m was still drawn with r1's bake two rebuilds later.  The only way to
    re-bake is to install a cut that does not carry one.  This archive is a BAKE FIXTURE, not
    a release: the atlases it produces are copied beside their DAEs and the certified zip is
    re-cut from them.
    """
    source = Path(os.environ.get("B3_LEVEL_DIST_DIR") or dist.DEFAULT_OUTPUT_DIR) / dist.ZIP_NAME
    dropped = 0
    with (
        zipfile.ZipFile(source) as original,
        zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as fixture,
    ):
        for info in original.infolist():
            if ".imposter" in info.filename and info.filename.endswith(".dds"):
                dropped += 1
                continue
            new = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            new.compress_type = zipfile.ZIP_STORED
            new.create_system = info.create_system
            new.external_attr = info.external_attr
            fixture.writestr(new, original.read(info.filename), compress_type=zipfile.ZIP_STORED)
    assert dropped, "the certified zip carried no imposter atlas to drop"
    return destination.read_bytes()


@pytest.mark.beamng_live
@pytest.mark.skipif(
    os.environ.get(REBAKE_ENV) != "1",
    reason=f"set {REBAKE_ENV}=1 to re-bake the imposter atlases from the shipped geometry",
)
def test_forest_imposter_rebake(tmp_path: Path) -> None:
    """r4 (critic r3 D8): bake every atlas from the CURRENT geometry and record what it is of.

    Writes ``authoring/<level>_forest_imposters.json``: per atlas, its sha256, its DDS header,
    the sha256 of the DAE it was baked from, and the billboard reading (view cells used and
    bbox fill).  ``tests/test_hot_potato_forest.py`` then refuses to certify a cut whose
    atlas does not match the DAE beside it.
    """
    billboarded = [s for s in fs.SPECIES if s["bb"]]
    fixture = tmp_path / "imposter_bake.zip"
    payload = _archive_without_atlases(fixture)
    for relative in forest_build.imposter_members(LEVEL_ROOT):
        (LEVEL_ROOT / relative).unlink()
    started = time.monotonic()
    with _forest_boot(
        "rebake",
        tmp_path,
        archive=fixture,
        payload=payload,
        lock_sha="bake fixture (not a release)",
    ) as s:
        _load_level(s, "b3_rebake")
        # MEASURED the hard way in r4's first bake: `updateImposters` renders the shapes AS
        # THEY ARE LOADED, and on a cold profile the texture cooker is still working through
        # 146 maps 180 s into the boot -- so every alphaTest conifer baked as an EMPTY
        # billboard while the opaque rocks came out fine.  Settle the cooker first.
        # ...and stand IN the forest first, because the cooker is lazy: a map is cooked on
        # the frame that first needs it, so a camera that never looked at a conifer leaves the
        # twig atlases uncooked however long the count stands still.
        eye, aim = FRAMES[0][1], FRAMES[0][2]
        s.lua(
            "commands.setFreeCamera(); "
            f"core_camera.setFOV(nil, {CAMERA_FOV_DEG}); "
            f"local eye = vec3({eye[0]}, {eye[1]}, {eye[2]}); "
            f"local aim = vec3({aim[0]}, {aim[1]}, {aim[2]}); "
            "local rotation = quatFromDir((aim - eye):normalized(), vec3(0, 0, 1)); "
            "core_camera.setPosRot(0, eye.x, eye.y, eye.z, rotation.x, rotation.y, rotation.z, "
            "rotation.w); return jsonEncode({ok = true})"
        )
        s.step(60)
        s.report["f2_texture_settle_before_the_bake"] = _settle_textures(s, timeout_s=600.0)
        assert s.report["f2_texture_settle_before_the_bake"]["stable"], (
            "the texture cooker never went quiet; a bake now would blank the alphaTest shapes"
        )
        # THE LAW, measured three bakes in a row: the engine rebuilds an imposter ONLY at
        # level load, and only when the DAE is newer than the cached atlas.  On a cold profile
        # that happens 28-71 s into a 174 s load -- long before the cooker has produced the
        # foliage maps -- so every alphaTest conifer bakes as an EMPTY billboard while the
        # opaque rocks come out fine.  `Engine.Render.updateImposters(true)` does not rebuild:
        # with the cache deleted it wrote nothing at all across 400 polls / 7 minutes.
        # So the bake is: cook everything, DELETE the cache, and load the level AGAIN.
        temp_root = s.user / "temp" / "levels" / LEVEL_ID
        dropped = []
        for stale_atlas in sorted(temp_root.rglob("*.imposter*.dds")):
            stale_atlas.unlink()
            dropped.append(stale_atlas.name)
        s.report["f2_blank_atlases_dropped_before_the_reload"] = len(dropped)
        _load_level(s, "b3_rebake_pass2")
        s.report["f2_texture_settle_after_the_reload"] = _settle_textures(s, timeout_s=600.0)
        harvest = _harvest_imposters(s, len(billboarded))
        s.report["f2_imposters"] = harvest
        rows = _imposter_manifest_rows(harvest["harvested"])
        s.report["f2_rebake"] = {
            "harvested_this_boot": len(harvest["harvested"]),
            "expected": 2 * len(billboarded),
            "sizes": sorted({f"{r['width']}x{r['height']}" for r in rows.values()}),
            "views_declared": fs.BB_VIEWS,
            "cells_used": sorted(
                {r["reading"]["cells_used"] for r in rows.values() if "reading" in r}
            ),
            "cells_touched": sorted(
                {r["reading"]["cells_touched"] for r in rows.values() if "reading" in r}
            ),
            "bbox_fill_median": sorted(
                round(r["reading"]["bbox_fill_median"], 3) for r in rows.values() if "reading" in r
            ),
        }
        assert len(harvest["harvested"]) == 2 * len(billboarded), s.report["f2_rebake"]
        blank = sorted(
            relative
            for relative, row in rows.items()
            if "reading" in row and row["reading"].get("cells_touched", 0) < fs.BB_VIEWS
        )
        s.report["f2_rebake"]["atlases_short_of_their_declared_views"] = blank
        assert not blank, blank[:6]
        s.report["f2_update_imposters_writes_nothing"] = _update_imposters_write_set(s)
        manifest = {
            "level_id": LEVEL_ID,
            "bb_property": fs.BB_PROPERTY,
            "views_declared": fs.BB_VIEWS,
            "bb_dim": fs.BB_DIM,
            "baked_by": "tests/test_hot_potato_forest_live.py::test_forest_imposter_rebake",
            "seconds": round(time.monotonic() - started, 1),
            "atlases": rows,
        }
        forest_build.IMPOSTERS_MANIFEST.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )


# --------------------------------------------------------------- the QB-9b BB:: knob probe
#: r5 (critic r4 B1).  Two ENGINE LAWS are going into the constitution off this probe and
#: neither survived r4 as anything a successor could re-read, so the variants are now the
#: experiments themselves rather than the atlas-size sweep r1 needed:
#:
#: * ``pine_tall_a`` reproduces law (b)'s decisive reading -- ``EQUATOR_STEPS=10 +
#:   POLAR_STEPS=1`` allocates the 32-cell 1024 x 512 the arithmetic predicts and FILLS
#:   twelve, because ``BB::POLAR_ANGLE`` defaults to 0 and every polar row lands back on the
#:   equator.  r4 asserted this in a source comment; here it lands in ``evidence.json`` with
#:   the atlas size, the cells used and the per-cell fills.
#: * ``fir_tall_a`` asks whether ``BB::INCLUDE_POLES`` is a token the engine parses at all.
#:   critic r4 disproved r4's "the two poles the engine ALWAYS adds" -- stock's tree atlases
#:   carry none -- and level_facts now says to turn them off to match stock.  Nobody has ever
#:   checked that the knob exists: the constructor readout ``1 <equator> <polar> <angle>
#:   <dim> <poles> <shadow>`` is the evidence, and a `poles` flag that does not move means
#:   the recommendation is unactionable and must be recorded as such.
#: * ``pine_mid_a`` raises the equator count on its own, to show what the grid does when the
#:   poles push the view count past a power-of-two cell grid.
#: * ``fir_tall_b`` is the recipe r5 SHIPS, measured end to end before it was adopted rather
#:   than composed out of two separate readings: 32 equator views and no poles.
#: * ``pine_tall_b`` carries r4's SHIPPED recipe unchanged, as the control the others are read
#:   against in the same boot -- and, incidentally, as a second bake of identical geometry, so
#:   the round's "the bake is not deterministic run to run" disclosure has a second number.
BB_PROBE_VARIANTS = {
    "pine_tall_a": "BB::DIM=128\nBB::EQUATOR_STEPS=10\nBB::POLAR_STEPS=1",
    "fir_tall_a": "BB::DIM=128\nBB::EQUATOR_STEPS=30\nBB::INCLUDE_POLES=0",
    "pine_mid_a": "BB::DIM=128\nBB::EQUATOR_STEPS=32",
    "fir_tall_b": "BB::DIM=128\nBB::EQUATOR_STEPS=32\nBB::INCLUDE_POLES=0",
    "pine_tall_b": "BB::DIM=128\nBB::EQUATOR_STEPS=30",
}


def _bb_probe_archive(destination: Path) -> bytes:
    """The shipped zip with three DAEs re-annotated -- a PROBE, never a release."""
    source = Path(os.environ.get("B3_LEVEL_DIST_DIR") or dist.DEFAULT_OUTPUT_DIR) / dist.ZIP_NAME
    replacements = {}
    for key, prop in BB_PROBE_VARIANTS.items():
        relative = fs.species_dae_relative(fs.SPECIES_BY_KEY[key])
        member = f"levels/{LEVEL_ID}/{relative}"
        text = (LEVEL_ROOT / relative).read_text("utf-8")
        replacements[member] = re.sub(
            r"<user_properties>.*?</user_properties>",
            lambda _match, value=prop: f"<user_properties>{value}</user_properties>",
            text,
            count=2,
            flags=re.S,
        ).encode("utf-8")
    with (
        zipfile.ZipFile(source) as original,
        zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as probe,
    ):
        skip = {
            f"levels/{LEVEL_ID}/{fs.species_dae_relative(fs.SPECIES_BY_KEY[key])}{suffix}"
            for key in BB_PROBE_VARIANTS
            for suffix in (".imposter.dds", ".imposter_normals.dds")
        }
        for info in original.infolist():
            if info.filename in skip:
                continue  # drop the shipped atlas so the engine regenerates it at BB::DIM=N
            payload = replacements.get(info.filename) or original.read(info.filename)
            new = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            new.compress_type = zipfile.ZIP_STORED
            new.create_system = info.create_system
            new.external_attr = info.external_attr
            probe.writestr(new, payload, compress_type=zipfile.ZIP_STORED)
    return destination.read_bytes()


@pytest.mark.beamng_live
@pytest.mark.skipif(
    os.environ.get(BB_PROBE_ENV) != "1",
    reason=f"set {BB_PROBE_ENV}=1 to run the QB-9b BB:: knob probe boot",
)
def test_forest_imposter_atlas_knobs(tmp_path: Path) -> None:
    """Design §4.3 leaves 1024 x 512 open: try the other BB:: knobs and RECORD the answer."""
    probe_zip = tmp_path / "bb_probe.zip"
    payload = _bb_probe_archive(probe_zip)
    with _forest_boot(
        "bbknob", tmp_path, archive=probe_zip, payload=payload, lock_sha="probe (not a release)"
    ) as s:
        _load_level(s, "b3_bbknob")
        user = s.user
        temp_root = user / "temp" / "levels" / LEVEL_ID
        s.lua(
            "local ok = pcall(function() Engine.Render.updateImposters(true) end); "
            "return jsonEncode({ok = ok})"
        )
        measured: dict[str, Any] = {}
        for _ in range(80):
            s.step(30)
            time.sleep(0.5)
            measured = {}
            for key, prop in BB_PROBE_VARIANTS.items():
                relative = fs.species_dae_relative(fs.SPECIES_BY_KEY[key])
                atlas = temp_root / f"{relative}.imposter.dds"
                if atlas.is_file() and atlas.stat().st_size > 0:
                    blob = atlas.read_bytes()
                    measured[key] = {"property": prop, **dds_header(blob)}
                    # r5: the SIZE the recipe allocates was never the interesting half -- what
                    # law (b) rests on is how many of those cells the engine actually renders
                    # into, and which of them are poles.  Both come out of the bytes.
                    try:
                        measured[key]["reading"] = forest_build.imposter_reading(
                            blob, cell=fs.BB_DIM, detail=True
                        )
                    except Exception as exc:  # recorded, never fatal in a probe boot
                        measured[key]["reading"] = {"error": str(exc)}
            if len(measured) == len(BB_PROBE_VARIANTS):
                break
        constructor = s.lua(
            "local out = {}; "
            + " ".join(
                f"do local c = createObject('TSShapeConstructor'); "
                f"c:setField('baseShape', 0, '/levels/{LEVEL_ID}/"
                f"{fs.species_dae_relative(fs.SPECIES_BY_KEY[key])}'); "
                f"c:registerObject('{LEVEL_ID}_bbprobe_{index}'); "
                "local dl = c:getImposterDetailLevel(); "
                f"out[{key!r}] = {{detail_level = dl, settings = dl and dl >= 0 and "
                "c:getImposterSettings(dl) or nil} end "
                for index, key in enumerate(BB_PROBE_VARIANTS)
            )
            + "return jsonEncode(out)"
        )
        s.report["qb9b_bb_knobs"] = {
            "variants": BB_PROBE_VARIANTS,
            "atlases": measured,
            "shape_constructor": constructor,
            "baseline": "BB::DIM=128 -> 512 x 256 (B0 A4, re-measured in the forest boot)",
        }
        for key, row in measured.items():
            s.report.setdefault("qb9b_result", {})[key] = f"{row['width']}x{row['height']}"
