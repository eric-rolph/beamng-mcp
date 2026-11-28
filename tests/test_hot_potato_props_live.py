"""Live gates for build round B4 on the sentinel profile: the bench log, the props, the roads.

Runs ONLY against the sentinel-isolated profile, under ``isolated_profile_lock``, through
B1's ``_boot`` context manager -- the same install, the same terrain-material-cache purge,
the same footprint sweep and the same E-line census, so the two rounds' evidence is
comparable line for line.  Point it at a cut with ``HOT_POTATO_LEVEL_DIST_DIR`` and at an
evidence directory with ``HOT_POTATO_LEVEL_EVIDENCE_DIR``.

What it proves, in the order it proves it:

1.  the props are IN the world (a scenetree census by class and by shape);
2.  the bench log's ramp grade and deck height BY RAY, not from the mesh;
3.  a car DRIVEN up the wedge at speed and at a crawl (AGENTS.md L1291's stall
    discriminator), then off both ends -- the crown at four speeds, the ramp's foot -- resting
    upright each time, then INTO both containment walls on a 5 deg heading grid at five speeds
    (r4: the long edge is a wall, there are no flank exits), and a runaway diagnostic that
    reads the gearbox while r2's and r3's stop policies run (C5-3);
4.  an ``ai span`` drive on the trail with ``map.findClosestRoad`` distances;
5.  the design §8 frames B4 owns (S5 at clock 0.50, S8 at 0.30) plus the bench's own;
6.  the props' RENDER COST with an A/B/A off-control at one fixed camera, with the physics
    realtime factor beside every frame-time reading;
7.  the decal-batcher E line: the shipped cut's count, then a positive control that
    RE-CREATES the closed visible loop on a road B4 does not ship that way.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import statistics
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import tests.test_hot_potato_level_scaffold_live as scaffold
from examples.hot_potato_arena.level import props_build
from examples.hot_potato_arena.level import props_spec as ps
from examples.hot_potato_arena.level import terrain_io as terrain
from examples.hot_potato_arena.level import terrain_model as tm

LEVEL_ID = ps.LEVEL_ID
LEVEL_ROOT = ps.EXAMPLE_ROOT / "mod" / "levels" / LEVEL_ID
GROUP = ps.PROPS_GROUP
VEH = f"{LEVEL_ID}_b4_probe"
HEAVY = f"{LEVEL_ID}_b4_heavy"
STEP = scaffold.STEP_TICK
GRADE_LAW = 0.12
RUNOFF_MIN_M = 50.0
#: r5: a grid cell only means something if its car actually went somewhere AND arrived at the
#: thing under test.  B3 r11's law, both halves -- "score a launch by measured DISPLACEMENT
#: over a stated threshold" and "score 'reached' by CONTACT, never by a ray".  4.0 m is B3's
#: own displacement threshold, kept as a published statistic; 1.0 m is the bar for "it moved".
GRID_LAUNCH_MIN_M = 4.0
GRID_MOVED_MIN_M = 1.0
#: how close a body's OWN outboard reach may sit to the flat deck's edge on both sides before
#: the car is wedged where it stands.  r5 boot 1 measured the case it exists for: a pickup
#: placed square across the 6.0 m trough reaches within 0.11 m of both 1.20 m walls and then
#: travels 0.04 m under throttle.  Stated as a slack rather than tuned to that number.
GRID_WEDGE_SLACK_M = 0.25
#: r6, N1: ``e2_score``'s own bar for "at rest ON the deck rather than off it" -- more than
#: this above the meadow.  The A/B used it to refute the chamfer and to price the bolster and
#: the shipped section then published no column for it.
GRID_ON_THE_LOG_M = 3.0
#: r6, N3: the C5-3 bounds, quoted from the exit-drop gate so the grid can be MEASURED against
#: them and the asymmetry stated.  They are NOT applied as a gate on the grid: a departure over
#: the designed crown is meant to run out across the meadow.
EXIT_TRAVEL_BOUND_M = 40.0
EXIT_SPEED_BOUND_OVER_TARGET_MS = 2.0
#: r6, C6-4: the fraction of a ladder frame's own centre ROW that must land on the bench log
#: before the frame may be PRICED as a reading of the log -- alongside the centre RAY, which
#: must hit it outright.  ``b4_bench_broadside_100m`` -- a photograph of the inside of B3's
#: forest -- was measured as the 100 m rung of a ladder about the log, so this is the bar
#: that stops a reading of something else being published.  The whole box is NOT gated: at
#: 100 m the centre box spans about +-41 m of a 7 m subject, so most of it is sky and meadow
#: by geometry and a bar on it would fail a correct frame.
FRAME_SUBJECT_MIN = 0.50
PERF_SECONDS = float(os.getenv("HOT_POTATO_B4_PERF_SECONDS", "22"))
#: the cap B4's boot 2 was pinned at -- three legs at exactly 16.667 ms, realtime factor
#: 1.000.  A leg sitting within 1 fps of this is clamped and cannot price anything.
PERF_CAP_FPS = 60.0

#: Frame-time probe with NO shipped file: wrap a loaded module's onPreRender/onUpdate.  The
#: arena's G12 gate ships a probe zip for this; a level round must not leave a second archive
#: in the sentinel's mods folder, so the counters live in _G for the session and die with it.
PERF_INSTALL = """
if rawget(_G, 'hp_b4_perf') == nil then
  local clock = os.clockhp or os.clock
  local S = {frames = 0, wall = 0, maxdt = 0, over33 = 0, over66 = 0,
             simsum = 0, realsum = 0, updates = 0, last = nil, hist = {}}
  rawset(_G, 'hp_b4_perf', S)
  local host = extensions.core_camera
  local pre, upd = host.onPreRender, host.onUpdate
  host.onPreRender = function(...)
    local now = clock()
    if S.last ~= nil then
      local dt = now - S.last
      S.frames = S.frames + 1
      S.wall = S.wall + dt
      if dt > S.maxdt then S.maxdt = dt end
      if dt > 0.0333 then S.over33 = S.over33 + 1 end
      if dt > 0.0667 then S.over66 = S.over66 + 1 end
      local b = math.min(21, math.floor(dt * 200) + 1)
      S.hist[b] = (S.hist[b] or 0) + 1
    end
    S.last = now
    if pre then return pre(...) end
  end
  host.onUpdate = function(dtReal, dtSim, dtRaw)
    S.updates = S.updates + 1
    if type(dtSim) == 'number' then S.simsum = S.simsum + dtSim end
    if type(dtReal) == 'number' then S.realsum = S.realsum + dtReal end
    if upd then return upd(dtReal, dtSim, dtRaw) end
  end
  -- common/extensions.lua L784-790 CACHES the hook's function list per name, so patching a
  -- module's callback after load is invisible until the cache is dropped.  B4 boot 1 counted
  -- ZERO frames for exactly this reason.
  extensions.hookUpdate('onPreRender')
  extensions.hookUpdate('onUpdate')
end
return jsonEncode({ok = true})
"""

PERF_RESET = """
local S = rawget(_G, 'hp_b4_perf')
S.frames = 0 S.wall = 0 S.maxdt = 0 S.over33 = 0 S.over66 = 0
S.simsum = 0 S.realsum = 0 S.updates = 0 S.last = nil S.hist = {}
return jsonEncode({ok = true})
"""

PERF_SNAP = "return jsonEncode(rawget(_G, 'hp_b4_perf'))"


def _bench_frame():
    row = ps.log_row("bench_log")
    origin = np.asarray([float(row["x"]), float(row["y"])])
    along = np.asarray(ps.heading_vector(float(row["heading_along_decreasing_bearing"])))
    across = np.asarray([-along[1], along[0]])
    return origin, along, across


def _bench_point(x_local: float, y_local: float = 0.0):
    origin, along, across = _bench_frame()
    point = origin + along * x_local + across * y_local
    return float(point[0]), float(point[1])


def _fence_camera(place: dict[str, Any]):
    """Eye across the trail from the fence, looking ALONG it.

    B4 boot 1 offset the eye by raw world (+16, -14) from one post and aimed at another; on a
    trail running roughly south-east that put the camera in the ground cover looking at bare
    hillside, and the fence never appeared.  The offset is now taken in the FENCE's own frame:
    9 m to its far side, 2.3 m up, aimed 60 m down the line at rail height.
    """

    stations = place["fence_stations"]
    near, far = stations[4], stations[12]
    dx = float(far["x"]) - float(near["x"])
    dy = float(far["y"]) - float(near["y"])
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    # the trail is on the fence's LEFT (place_props offsets the posts by +lateral), so step
    # to the right of the run to look back across the fence at the road stack behind it
    eye = (
        float(near["x"]) - uy * 9.0 - ux * 12.0,
        float(near["y"]) + ux * 9.0 - uy * 12.0,
        float(near["z"]) + 2.3,
    )
    aim = (float(far["x"]), float(far["y"]), float(far["z"]) + 0.9)
    return (eye, aim, "B4: the split-rail fence along the trail with the road stack beside it")


def _rut_camera():
    """A low eye ON the trail, looking along it -- the frame that shows a wheel path or not.

    Critic pass 2: "still no ruts, either: the tyre-track overlay records exist in the stack
    but nothing in either trail frame reads as a worn wheel path".  Both r2 trail frames were
    shot across or above the road; this one is a driver's eye at 1.25 m, 40 m of trail ahead.
    """

    samples = tm.trail_samples(1.0)
    near = samples[300]
    far = samples[340]
    eye = (float(near[0]), float(near[1]), float(terrain.surface_z(near[0], near[1])) + 1.25)
    aim = (float(far[0]), float(far[1]), float(terrain.surface_z(far[0], far[1])) + 0.45)
    return (eye, aim, "B4: a driver's eye on the trail -- the wheel path, the verge, the stack")


def _perf_leg(session: scaffold.Session, label: str, seconds: float) -> dict[str, Any]:
    session.lua(PERF_RESET)
    started = time.monotonic()
    time.sleep(seconds)
    snap = session.lua(PERF_SNAP)
    wall = time.monotonic() - started
    frames = float(snap["frames"])
    probe_wall = float(snap["wall"]) or 1e-9
    real = float(snap["realsum"])
    factor = (float(snap["simsum"]) / real) if real > 0 else None
    return {
        "leg": label,
        "frames": frames,
        "probe_wall_s": round(probe_wall, 2),
        "python_wall_s": round(wall, 2),
        "avg_fps": round(frames / probe_wall, 2),
        "avg_frame_ms": round(1000.0 * probe_wall / frames, 3) if frames else None,
        "worst_frame_ms": round(float(snap["maxdt"]) * 1000.0, 2),
        "frames_over_33ms": int(snap["over33"]),
        "frames_over_66ms": int(snap["over66"]),
        # the brief's rule: a frame-time reading without its realtime factor is not a reading
        "physics_realtime_factor": round(factor, 3) if factor else None,
        "histogram_5ms_buckets": snap.get("hist"),
    }


def _crown_by_ray(rows: list[dict[str, Any]], geom: dict[str, Any]) -> dict[str, Any]:
    """The west descent as the engine's own rays see it, against what it was authored as.

    The whole defect r2 fixes is a LIP at the foot of a nose-down slope, so the foot's height
    over the terrain is measured live and not taken from the mesh.
    """

    # measured back from the crown's FOOT, so the profile's near ease is the foot's and its
    # far ease is the crest's.  r3's crown is ASYMMETRIC (4.6 m crest / 2.0 m foot) and this
    # helper kept comparing the built surface against a symmetric one, which is why the first
    # r3 boot reported "0.5846 m from the authored descent" while the static gate, reading
    # the same mesh against the right curve, read 4.68 mm.  An instrument that disagrees with
    # the geometry it measures is worth more than the reading it produced.
    profile = ps.ramp_profile(
        geom["crown_run"],
        geom["crown_ease_foot"],
        geom["crown_fall"],
        3200,
        ease_end=geom["crown_ease"],
    )
    stations = np.asarray([s for s, _ in profile])
    heights = np.asarray([z for _, z in profile])
    datum = float(ps.log_row("bench_log")["z_ground"])

    def authored(x_local: float) -> float:
        back = min(max(geom["half"] - min(x_local, geom["break_x"]), 0.0), geom["crown_run"])
        return datum + geom["crown_foot_z"] + float(np.interp(back, stations, heights))

    error = [abs(r["z"] - authored(r["x_local"])) for r in rows]
    grades = [
        (rows[i + 1]["z"] - rows[i]["z"]) / (rows[i + 1]["x_local"] - rows[i]["x_local"])
        for i in range(len(rows) - 1)
    ]
    foot = rows[-1]
    terrain_at_foot = float(terrain.surface_z(foot["x"], foot["y"]))
    return {
        "stations": len(rows),
        "run_m": geom["crown_run"],
        "max_dz_from_the_authored_descent_m": round(max(error), 4) if error else None,
        "max_grade_pct": round(max(abs(g) for g in grades) * 100.0, 3) if grades else None,
        "authored_max_grade_pct": round(geom["crown_grade"] * 100.0, 3),
        "grade_at_the_top_pct": round(grades[0] * 100.0, 3) if grades else None,
        "grade_at_the_foot_pct": round(grades[-1] * 100.0, 3) if grades else None,
        "break_z": round(foot["z"], 4),
        "terrain_z_at_the_break": round(terrain_at_foot, 4),
        "break_face_measured_m": round(foot["z"] - terrain_at_foot, 4),
        "break_face_authored_m": geom["break_face_measured_m"],
        "crest_release_speed_ms": round(geom["crown_release_v"], 3),
    }


@pytest.mark.beamng_live
def test_b4_props_live(tmp_path: Path) -> None:
    if not props_build.available():
        pytest.skip("B4 manifests absent; run the prop build scripts first")
    place = props_build.place_manifest()
    shapes = props_build.shapes_manifest()
    geom = shapes["shapes"]["bench_log"]["bench"]
    with scaffold._boot("boot1", tmp_path, watchdog_seconds=3600.0) as s:
        bng = s.bng
        levels = bng.scenario.get_levels()
        assert LEVEL_ID in levels, sorted(levels)
        from beamngpy import Scenario, Vehicle

        scenario = Scenario(LEVEL_ID, "b4_bngpy_probe")
        vehicle = Vehicle(VEH, model="etk800", licence="B4")
        toe = _bench_point(geom["toe_x"] - 16.0)
        spawn_z = float(terrain.surface_z(*toe)) + 0.6
        scenario.add_vehicle(vehicle, pos=(toe[0], toe[1], spawn_z), rot_quat=(0, 0, 0, 1))
        # r3, critic pass 2's N8: a heavier class finds a collider's limits, and the pickup is
        # the one that could NOT climb r2's 26 % descent -- so it is also the second opinion
        # on whether r3's 72 % crown is really one-way.
        heavy = Vehicle(HEAVY, model="pickup", licence="B4H")
        heavy_at = _bench_point(geom["toe_x"] - 16.0, -14.0)
        scenario.add_vehicle(
            heavy,
            pos=(heavy_at[0], heavy_at[1], float(terrain.surface_z(*heavy_at)) + 0.6),
            rot_quat=(0, 0, 0, 1),
        )
        load_started = time.monotonic()
        bng.control.pause()
        scenario.make(bng)
        s.scenario = scenario
        s.scenario_dir = None
        bng.scenario.load(scenario, precompile_shaders=False)
        bng.scenario.start()
        bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
        bng.control.pause()
        s.register(vehicle)
        s.register(heavy)
        s.step(6)
        s.report["level_load_s"] = round(time.monotonic() - load_started, 1)
        s.marker(s.log_marker)

        # --- 1. the props are in the world -------------------------------------------
        census = s.lua(
            "local out = {statics = 0, prefabs = 0, by_shape = {}, groups = {}}; "
            "for _, id in ipairs(scenetree.findClassObjects('TSStatic')) do "
            "local o = scenetree.findObject(id); if o then "
            "local shape = tostring(o:getField('shapeName', 0)); "
            "out.by_shape[shape] = (out.by_shape[shape] or 0) + 1; "
            "out.statics = out.statics + 1; end end "
            "for _, id in ipairs(scenetree.findClassObjects('Prefab')) do out.prefabs = "
            "out.prefabs + 1 end "
            "for _, id in ipairs(scenetree.findClassObjects('SimGroup')) do "
            "out.groups[#out.groups + 1] = tostring(id) end "
            "return jsonEncode(out)"
        )
        props_shapes = {
            k: v for k, v in census["by_shape"].items() if "/art/shapes/props/" in str(k)
        }
        # r1 reported "4,450 + 128 placed = 4,578, and the boot read 4,589" and left the 11
        # unexplained.  The census now splits EVERY TSStatic in the world by its shapeName, so
        # anything the level did not author is named rather than left as a difference.
        authored_dirs = ("/art/shapes/props/", "/art/shapes/deadwood/", "/art/shapes/rocks/")
        level_prefix = f"/levels/{LEVEL_ID}/"
        outside = {
            k: v
            for k, v in census["by_shape"].items()
            if not str(k).startswith(level_prefix) or "/art/prefabs/" in str(k)
        }
        s.report["b4_census"] = {
            "tsstatic_total": census["statics"],
            "prefab_objects": census["prefabs"],
            "props_shapes": props_shapes,
            "props_statics": int(sum(props_shapes.values())),
            "expected_props_statics": place["placed_statics"],
            "expected_prefab_instances": place["prefab_instances"],
            "tsstatics_by_shape": census["by_shape"],
            "tsstatics_not_from_this_level": outside,
            "tsstatics_not_from_this_level_total": int(sum(outside.values())),
            "authored_dirs_seen": sorted(
                {d for d in authored_dirs if any(d in str(k) for k in census["by_shape"])}
            ),
        }
        s.check(
            int(sum(props_shapes.values())) == place["placed_statics"],
            "the props group did not instantiate every TSStatic",
            s.report["b4_census"],
        )
        s.check(
            int(census["prefabs"]) >= place["prefab_instances"],
            "the four prefab cluster files did not instantiate",
            s.report["b4_census"],
        )
        # the prefab CHILDREN: a prefab whose transform is ignored piles every child at the
        # origin, so read back a sample of the instantiated statics' world positions
        sample = place["cluster_sites"]["pf_deadfall_cluster"][:3]
        near = s.lua(
            "local out = {} "
            + " ".join(
                f"do local n = 0; local far = 0; for _, id in ipairs("
                f"scenetree.findClassObjects('TSStatic')) do local o = scenetree.findObject(id); "
                f"if o then local p = o:getPosition(); local d = math.sqrt((p.x - {row['x']})^2 + "
                f"(p.y - {row['y']})^2); if d < 30 then n = n + 1 end end end "
                f"out[{index}] = {{x = {row['x']}, y = {row['y']}, within_30m = n}} end "
                for index, row in enumerate(sample)
            )
            + " return jsonEncode({rows = out})"
        )
        s.report["prefab_children_near_sites"] = near
        s.check(
            all(int(row["within_30m"]) >= 6 for row in near["rows"].values()),
            "prefab children did not land near their instance positions",
            near,
        )

        # --- 1c. the decal-batcher E line: a mutation ladder on the road that fires it ----
        # Run EARLY: B4 boot 1 lost this section to an exception in the perf block.
        # The shipped cut splits every closed visible loop into two open arcs, and the line
        # STILL fires -- naming ``track_surface_b`` at the same world vertex.  So "closed by a
        # repeated node" is REFUTED as the trigger and the ladder below tests the three fixes
        # B1 named as untried, one field at a time, reading the log's delta after each.
        def _batcher_count() -> int:
            issues = scaffold._level_log_issues(s.user / "beamng.log", s.log_marker)
            return len(issues["known_decal_batcher_errors"])

        offender = f"{LEVEL_ID}_track_surface_b"
        batcher: dict[str, Any] = {
            "offender": offender,
            "scenetree_roads": s.lua(
                "local out = {roads = 0, by_material = {}, closed = {}}; "
                "for _, id in ipairs(scenetree.findClassObjects('DecalRoad')) do "
                "local r = scenetree.findObject(id); if r then out.roads = out.roads + 1; "
                "local m = tostring(r:getField('material', 0)); "
                "out.by_material[m] = (out.by_material[m] or 0) + 1; "
                "local n = r:getNodeCount(); if n > 4 then "
                "local a = r:getNodePosition(0); local b = r:getNodePosition(n - 1); "
                "if (a - b):length() < 0.001 then out.closed[#out.closed + 1] = r:getName() end "
                "end end end return jsonEncode(out)"
            ),
            "fields_at_load": s.lua(
                f"local r = scenetree.findObject({offender!r}); if not r then "
                "return jsonEncode({ok = false}) end "
                "return jsonEncode({ok = true, nodes = r:getNodeCount(), "
                "improvedSpline = tostring(r:getField('improvedSpline', 0)), "
                "useSubdivisions = tostring(r:getField('useSubdivisions', 0)), "
                "breakAngle = tostring(r:getField('breakAngle', 0)), "
                "detail = tostring(r:getField('detail', 0)), "
                "drivability = tostring(r:getField('drivability', 0)), "
                "textureLength = tostring(r:getField('textureLength', 0))})"
            ),
            "steps": [],
        }
        rungs = (
            ("improvedSpline false", "r:setField('improvedSpline', 0, '0')"),
            ("useSubdivisions false", "r:setField('useSubdivisions', 0, '0')"),
            ("breakAngle 45", "r:setField('breakAngle', 0, '45')"),
            ("detail 1.0", "r:setField('detail', 0, '1')"),
            ("drivability -1", "r:setField('drivability', 0, '-1')"),
            ("delete the last node", "r:deleteNode(r:getNodeCount() - 1)"),
        )
        before = _batcher_count()
        batcher["count_at_load"] = before
        for label, mutation in rungs:
            applied = s.lua(
                f"local r = scenetree.findObject({offender!r}); if not r then "
                "return jsonEncode({ok = false}) end "
                f"{mutation}; r:postApply(); "
                "return jsonEncode({ok = true, nodes = r:getNodeCount()})"
            )
            s.step(90)
            time.sleep(2.5)
            after = _batcher_count()
            batcher["steps"].append(
                {
                    "rung": label,
                    "applied": applied,
                    "lines_before": before,
                    "lines_after": after,
                    "new_lines": after - before,
                }
            )
            before = after
        # B4 boot 2 measured the ladder's own limit: EVERY rung produced zero new lines,
        # including the ones that changed nothing about the suspected cause, because the
        # batcher logs once at LEVEL LOAD and no in-session setField/postApply re-triggers
        # ``_rebuildNodeBatchesThread``.  The ladder therefore reports what it can see -- that
        # a live mutation cannot reproduce or silence the line -- and each candidate fix needs
        # its own load to test.  It is kept because that null result is itself the finding.
        batcher["verdict"] = (
            "no rung produced a NEW line; the batcher logs once at level load and no live "
            "mutation re-triggers it, so a candidate fix can only be tested by re-loading"
            if all(step["new_lines"] == 0 for step in batcher["steps"])
            else "at least one rung re-triggered the batcher in-session"
        )

        # --- 1b. harvest the imposter atlases the engine baked at level load ----------
        # B3 r5's law: the engine bakes an imposter ONLY at level load and only when the DAE
        # is newer than the cached atlas, and a stale atlas is invisible to any close-range
        # gate -- so the harvest records each atlas's SOURCE-DAE sha256 beside it.
        temp_root = s.user / "temp" / "levels" / LEVEL_ID / ps.SHAPE_DIR
        harvest_dir = scaffold._evidence_dir(tmp_path) / "imposters"
        harvest_dir.mkdir(parents=True, exist_ok=True)
        harvested = {}
        for source in sorted(temp_root.glob("*.imposter*.dds")) if temp_root.is_dir() else []:
            payload = source.read_bytes()
            (harvest_dir / source.name).write_bytes(payload)
            stem = source.name.split(".dae.")[0]
            dae = shapes["shapes"].get(stem.replace(f"{LEVEL_ID}_p_", ""), {})
            harvested[source.name] = {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "source_dae": dae.get("file"),
                "source_dae_sha256": dae.get("sha256"),
            }
        s.report["imposter_harvest"] = {
            "temp_dir": str(temp_root),
            "temp_dir_present": temp_root.is_dir(),
            "atlases": harvested,
            "count": len(harvested),
            "bb_shapes_expected": sorted(k for k, v in ps.SHAPES.items() if v.get("bb")),
            "note": (
                "harvested into the evidence directory only; this cut does NOT ship them, "
                "so B6 folds them in with the DDS pre-cook and the lock"
            ),
        }

        # --- 1c. harvest the engine's own .cdae bakes (QB-8) --------------------------
        # r2 measured QB-8 at 0.096 and handed it to B6 as "new information".  Critic pass 2
        # opened this very boot's `profile_footprint.removed` and found 75 `.cdae` -- exactly
        # the 75 missing siblings, 12 of them B4's own props -- cooked by the engine at level
        # load and then SWEPT UNREAD by the round's own purge, while the block above was
        # already copying atlases out of the same tree.  The round held the fix and deleted
        # it.  This copies every one of them out before the purge; `b4/r3/stage_cdae.py`
        # stages them beside their source DAE with both hashes pinned, and they ship.
        cdae_dir = scaffold._evidence_dir(tmp_path) / "harvest"
        cdae_dir.mkdir(parents=True, exist_ok=True)
        level_temp = s.user / "temp" / "levels" / LEVEL_ID
        cooked_cdae: dict[str, dict[str, Any]] = {}
        for source in sorted(level_temp.rglob("*.cdae")) if level_temp.is_dir() else []:
            payload = source.read_bytes()
            (cdae_dir / source.name).write_bytes(payload)
            cooked_cdae[source.name] = {
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "temp_relative": source.relative_to(level_temp).as_posix(),
            }
        shipped_cdae = sorted(
            p.relative_to(LEVEL_ROOT).as_posix() for p in LEVEL_ROOT.rglob("*.cdae")
        )
        shipped_dae = sorted(
            p.relative_to(LEVEL_ROOT).as_posix() for p in LEVEL_ROOT.rglob("*.dae")
        )
        missing = sorted(
            {Path(p).name[:-4] for p in shipped_dae} - {Path(p).name[:-5] for p in shipped_cdae}
        )
        s.report["engine_bake_harvest"] = {
            "temp_root": str(level_temp),
            "cdae_cooked_by_the_engine": len(cooked_cdae),
            "cdae_already_shipped": len(shipped_cdae),
            "dae_shipped": len(shipped_dae),
            "dae_without_a_shipped_cdae": len(missing),
            "cooked_covers_the_missing_set": sorted({Path(n).stem for n in cooked_cdae}) == missing
            or None,
            "files": cooked_cdae,
            "harvest_dir": str(cdae_dir),
            "note": (
                "B2 r2 ran this pattern and took its QB-8 from 0.125 to 1.0 in one boot; "
                "its NEXT boot then read `cdae 0` here, which is the proof that the shipped "
                "bakes satisfied the engine and it stopped cooking them"
            ),
        }

        # --- 2. the bench BY RAY ------------------------------------------------------
        span = geom["break_x"] - geom["toe_x"]
        stations = [geom["toe_x"] + span * k / 240.0 for k in range(241)]
        points = [_bench_point(x) for x in stations]
        rows = s.surface_profile(points)
        ray = []
        for x, (px, py), row in zip(stations, points, rows, strict=True):
            ray.append(
                {
                    "x_local": round(x, 3),
                    "x": round(px, 3),
                    "y": round(py, 3),
                    "z": round(float(row["ray_z"]), 4),
                    "hit": bool(row["hit"]),
                }
            )
        # the PLATEAU is join_x .. crown_x; past crown_x the log descends, and r2's first
        # attempt at this gate read the descent as part of the deck and reported the deck
        # "not flat" with a 2.4 m spread.  Three regions, three questions.
        deck_rows = [
            r for r in ray if geom["join_x"] + 0.5 <= r["x_local"] <= geom["crown_x"] - 0.1
        ]
        ramp_rows = [r for r in ray if r["x_local"] <= geom["join_x"] - 0.5]
        crown_rows = [r for r in ray if r["x_local"] >= geom["crown_x"]]
        deck_z = [r["z"] for r in deck_rows]
        grades = [
            (ramp_rows[i + 1]["z"] - ramp_rows[i]["z"])
            / (ramp_rows[i + 1]["x_local"] - ramp_rows[i]["x_local"])
            for i in range(len(ramp_rows) - 1)
        ]
        # a ray station whose neighbours differ by more than a ramp can is a step, not a grade
        s.report["bench_by_ray"] = {
            "stations": len(ray),
            "hits": sum(1 for r in ray if r["hit"]),
            "deck_z_mean": round(float(np.mean(deck_z)), 4),
            "deck_z_min": round(min(deck_z), 4),
            "deck_z_max": round(max(deck_z), 4),
            "deck_z_authored": round(
                float(terrain.surface_z(*_bench_point(0.0))) + geom["deck_z"], 4
            ),
            "ramp_max_grade_pct": round(max(abs(g) for g in grades) * 100.0, 3),
            "ramp_p95_grade_pct": round(
                float(np.percentile([abs(g) for g in grades], 95)) * 100.0, 3
            ),
            "plateau_len_m": round(geom["crown_x"] - geom["join_x"], 2),
            "crown": _crown_by_ray(crown_rows, geom),
            "profile": ray,
        }
        report = s.report["bench_by_ray"]
        s.check(report["hits"] == len(ray), "a ray missed the bench log", report["hits"])
        s.check(
            abs(report["deck_z_max"] - report["deck_z_min"]) <= 0.02,
            "the deck is not flat by ray",
            report,
        )
        s.check(
            abs(report["deck_z_mean"] - report["deck_z_authored"]) <= 0.05,
            "the deck's measured height differs from the authored one",
            report,
        )
        s.check(
            report["ramp_max_grade_pct"] <= GRADE_LAW * 100.0 + 0.5,
            "the ramp is steeper than the 12 % law by ray",
            {k: v for k, v in report.items() if k != "profile"},
        )
        crown = report["crown"]
        s.check(
            crown["max_dz_from_the_authored_descent_m"] <= 0.05,
            "the west descent by ray is not the descent that was authored",
            crown,
        )
        s.check(
            abs(crown["grade_at_the_top_pct"]) <= 6.0,
            "the west descent leaves the plateau with a grade STEP",
            crown,
        )
        # r3 tried to make the west end one-way with a snapped break face, at 1.05 m and at
        # 0.75 m, and measured both refuted (report section 2.1b): a step at the foot of a
        # nose-down slope ploughs whether the step goes UP or DOWN.  The crown therefore ends
        # TANGENT TO THE GROUND, and this is the check that says so.
        s.check(
            crown["break_face_measured_m"] <= 0.05,
            "the west crown does not end ON the ground -- there is a step to plough into",
            crown,
        )

        # --- 3. drive the wedge, at speed and at a crawl ------------------------------
        def _drive_up(label: str, throttle: float, target_v: float) -> dict[str, Any]:
            start = _bench_point(geom["toe_x"] - 22.0)
            s.teleport(VEH, start, 30.0)
            s.control(VEH, throttle=0.0, brake=0.0, parkingbrake=0.0, steering=0.0)
            s.step(10)
            samples = []
            stalled_at = None
            escaped = None
            local_y = 0.0
            for tick in range(460):
                probe = s.probe(VEH)
                origin, along, across_v = _bench_frame()
                local_x = float(
                    (probe["x"] - origin[0]) * along[0] + (probe["y"] - origin[1]) * along[1]
                )
                local_y = float(
                    (probe["x"] - origin[0]) * across_v[0] + (probe["y"] - origin[1]) * across_v[1]
                )
                samples.append(
                    {
                        "t": round(tick * STEP / 60.0, 2),
                        "x_local": round(local_x, 2),
                        "y_local": round(local_y, 2),
                        "z": round(probe["z"], 3),
                        "v": round(probe["hspeed"], 3),
                    }
                )
                on_ramp = geom["toe_x"] - 2.0 <= local_x <= geom["join_x"]
                if on_ramp and probe["hspeed"] < 0.20 and stalled_at is None and tick > 40:
                    stalled_at = local_x
                    # AGENTS.md L1291: floor the throttle for 4 s and see which class it is
                    s.control(VEH, throttle=1.0, brake=0.0)
                    for _ in range(120):
                        s.step(STEP)
                    escaped = s.probe(VEH)["hspeed"] > 0.5
                    break
                drive = throttle if probe["hspeed"] < target_v else 0.0
                s.control(VEH, throttle=drive, brake=0.0)
                s.step(STEP)
                if local_x > geom["join_x"] + 12.0:
                    break
            probe = s.probe(VEH)
            origin, along, across_v = _bench_frame()
            local_y = float(
                (probe["x"] - origin[0]) * across_v[0] + (probe["y"] - origin[1]) * across_v[1]
            )
            return {
                "leg": label,
                "throttle": throttle,
                "target_v": target_v,
                # r4 (the N1 audit): "reached the deck" is a fact about WHERE the car is, not
                # only about how high it is.  r3's version read z alone, which is the same
                # shape as the crown-climb predicate the critic caught publishing `true` for
                # a pickup lying beside the log -- and a car that climbs the wedge and falls
                # off its side is not on the deck however high its best sample was.
                "reached_deck": bool(
                    probe["z"] > report["deck_z_mean"] - 0.6
                    and abs(local_y) <= geom["deck_flat_half"] + 0.5
                ),
                "final_z": round(probe["z"], 3),
                "final_y_local": round(local_y, 2),
                "final_v": round(probe["hspeed"], 3),
                "max_v": round(max(row["v"] for row in samples), 3),
                "stalled_on_ramp_at_x_local": stalled_at,
                "escaped_at_wot": escaped,
                "samples": samples,
            }

        climbs = [_drive_up("speed", 0.35, 8.0), _drive_up("crawl", 0.12, 1.4)]
        s.report["bench_climbs"] = climbs
        for climb in climbs:
            s.check(
                climb["reached_deck"], f"the {climb['leg']} climb never reached the deck", climb
            )
            s.check(
                climb["stalled_on_ramp_at_x_local"] is None,
                f"the {climb['leg']} climb stalled on the ramp",
                {k: v for k, v in climb.items() if k != "samples"},
            )

        # --- 4. off every exit, with the TRAJECTORY, not just the rest -----------------
        # r1 kept only `launch` and `rest` for the exits, so the one gate that failed was the
        # only one with no diagnostic data and no fix could be designed from it.  Every exit
        # now records per-step x_local / y_local / z / up.z / speed / wheels-on-ground, and
        # the west crown is driven at FOUR speeds instead of at whatever 0.30 throttle over
        # 8 m happened to give (about 4 m/s).
        origin, along, across = _bench_frame()
        centre = np.asarray(ps.CENTER[:2])
        inner = centre - origin
        inner = inner / float(np.hypot(*inner))
        # ps.heading_vector(h) = (sin h, cos h), so the compass heading that drives along the
        # local +y axis (`across`) is (along_heading - 90).  r1 wrote the INNER flank as
        # `30 + 90 * inner_sign`, which is -across when across points at the hearth: the two
        # flank rows were published against each other's runoff and drop numbers all round.
        along_heading = float(ps.log_row("bench_log")["heading_along_decreasing_bearing"])
        across_heading = (along_heading - 90.0) % 360.0
        inner_sign = 1.0 if float(np.dot(inner, across)) > 0 else -1.0
        inner_heading = (across_heading + (0.0 if inner_sign > 0 else 180.0)) % 360.0
        outer_heading = (inner_heading + 180.0) % 360.0
        s.report["bench_exit_frame"] = {
            "along_heading": along_heading,
            "across_heading_is_local_plus_y": across_heading,
            "across_points_at_the_hearth": bool(inner_sign > 0),
            "inner_flank_heading": round(inner_heading, 3),
            "outer_flank_heading": round(outer_heading, 3),
        }

        _origin_z = float(ps.log_row("bench_log")["z_ground"])

        def _pose(name: str = VEH) -> dict[str, Any]:
            row = s.lua(
                f"local v = scenetree.findObject({name!r}); local p = v:getPosition(); "
                "local u = v:getDirectionVectorUp(); local d = v:getDirectionVector(); "
                "local w = v:getVelocity(); "
                "return jsonEncode({x = p.x, y = p.y, z = p.z, ux = u.x, uy = u.y, uz = u.z, "
                "dx = d.x, dy = d.y, dz = d.z, vx = w.x, vy = w.y, vz = w.z})"
            )
            ox, oy = origin
            row["x_local"] = (row["x"] - ox) * along[0] + (row["y"] - oy) * along[1]
            row["y_local"] = (row["x"] - ox) * across[0] + (row["y"] - oy) * across[1]
            row["hspeed"] = math.hypot(float(row["vx"]), float(row["vy"]))
            return row

        def _sample(steps: int, pose: dict[str, Any], wheels: int | None) -> dict[str, Any]:
            row = {
                "t": round(steps / 60.0, 3),
                "x_local": round(float(pose["x_local"]), 3),
                "y_local": round(float(pose["y_local"]), 3),
                "z": round(float(pose["z"]), 3),
                "up_z": round(float(pose["uz"]), 4),
                "pitch_deg": round(
                    math.degrees(math.asin(max(-1.0, min(1.0, float(pose["dz"]))))), 2
                ),
                "v": round(float(pose["hspeed"]), 3),
                "vz": round(float(pose["vz"]), 3),
            }
            if wheels is not None:
                row["wheels_on_ground"] = wheels
            return row

        #: `Session.wheel_contacts` steps the sim 4 ticks of its own to get the answer back
        #: out of the vehicle VM, so every call is counted into the trajectory's own clock.
        WHEEL_QUERY_STEPS = 4

        _boxes: dict[str, tuple[float, float]] = {}

        def _model_box(model: str) -> tuple[float, float]:
            """``(half_length, half_width)`` of a vehicle, READ OUT OF THE RUNNING SIM.

            The grid's contact clause is a statement about where the BODY reaches, so the body
            has to be measured rather than assumed -- r5 boot 1's clause used the centreline
            and fired on 23 cells whose cars were hard against the wall.  One lua call per
            model, cached, and published in the grid summary so the clause can be re-derived.
            """

            if model in _boxes:
                return _boxes[model]
            answer = s.lua(
                f"local v = scenetree.findObject({model!r}) "
                "if not v then return jsonEncode({hx = 0, hy = 0}) end "
                "local ok, b = pcall(function() return v:getSpawnWorldOOBB() end) "
                "if ok and b then local h = b:getHalfExtents() "
                "return jsonEncode({how = 'getSpawnWorldOOBB', hx = h.x, hy = h.y}) end "
                "local w = v:getWorldBox() "
                "return jsonEncode({how = 'getWorldBox', "
                "hx = (w.maxExtents.x - w.minExtents.x) / 2, "
                "hy = (w.maxExtents.y - w.minExtents.y) / 2})"
            )
            pair = sorted(
                (float(answer.get("hx", 0.0)), float(answer.get("hy", 0.0))), reverse=True
            )
            # a read that failed must not silently become a permissive clause
            box = (pair[0], pair[1]) if pair[0] > 1.0 else (0.0, 0.0)
            _boxes[model] = box
            s.report.setdefault("vehicle_boxes", {})[model] = {
                "read_by": answer.get("how"),
                "half_length_m": round(box[0], 3),
                "half_width_m": round(box[1], 3),
            }
            return box

        def _wheels() -> int:
            return sum(1 for m in s.wheel_contacts(VEH) if m and m != "none")

        def _body_across_reach(model: str, pose: dict[str, Any] | None = None) -> dict[str, Any]:
            """How far the body ACTUALLY reaches across the deck, from its own node cloud.

            r6 (critic pass 5, C6-1) reads the SAME node cloud on three axes in the one call:
            the world across axis (what the treatment test needs), and the vehicle's OWN
            forward and right axes (what the PLACEMENT needs).  The vehicle-frame box is a
            property of the model, not of the pose, so once it is read the body's across-axis
            centre and half-extent can be re-derived at every sample of the trajectory
            without another lua round trip -- which is what closes N7 as well.

            r5 boot 2 failed one cell, `heavy_heading_+90deg_8ms`, and the reason is a third
            revision of the same mistake.  Boot 1 scored contact from the CENTRELINE; boot 2
            scored it from the body, but built the body out of ``getSpawnWorldOOBB``'s half
            extents added to the vehicle's REFERENCE point -- and for the pickup those are not
            the same point.  Measured live (`b4/r5/wedge_probe_r5.py`, 791 nodes) the truck
            placed square across the trough reaches ``y_local`` **-1.414 to +3.471** about a
            reference at 0.041: **3.430 m to one side**, not the 2.480 the half-extent gives.
            The box is centred on the body; the sum assumes it is centred on the reference.

            The 0.95 m that error hides is the whole cell: at +3.471 the truck's tail is past
            the deck's 3.0 m edge and past the bolster's 3.3 m crest half-width, its two rear
            wheels hang **0.78 m above the deck reading contact material ``none``**, and it
            sits at pitch -10.8 deg and travels 0.06 m under throttle.  It is not laterally
            wedged between two walls -- it is BEACHED ON ONE, and the launch clause could not
            see it because it was measuring a body 0.95 m smaller than the one on the deck.

            So the reach is read, per cell, at the launch pose: every node projected onto the
            deck's across axis, the wheels' contact materials with it.  A failed read falls
            back to the half-extent sum and SAYS SO -- it must never be the lenient branch.
            """

            ax, ay = float(across[0]), float(across[1])
            pose = pose or _pose(model)
            # the vehicle's own axes in the world's XY plane, from the pose it is standing in
            fx, fy = float(pose["dx"]), float(pose["dy"])
            plan = math.hypot(fx, fy) or 1.0
            fx, fy = fx / plan, fy / plan
            rx, ry = fy, -fx
            slot = f"hp_b4_reach_{uuid.uuid4().hex[:6]}"
            chunk = (
                "local lo, hi, n = 1e9, -1e9, 0 "
                "local flo, fhi, rlo, rhi = 1e9, -1e9, 1e9, -1e9 "
                "local ok = pcall(function() "
                "for i = 0, obj:getNodeCount() - 1 do local p = obj:getNodePosition(i) "
                f"local a = p.x * {ax} + p.y * {ay} "
                f"local f = p.x * {fx} + p.y * {fy} "
                f"local r = p.x * {rx} + p.y * {ry} "
                "if a < lo then lo = a end if a > hi then hi = a end "
                "if f < flo then flo = f end if f > fhi then fhi = f end "
                "if r < rlo then rlo = r end if r > rhi then rhi = r end "
                "n = n + 1 end end) "
                "local w = {} local t = particles.getMaterialsParticlesTable() "
                "for _, wh in pairs(wheels.wheels) do local m = t[wh.contactMaterialID1] "
                "w[#w + 1] = (m and m.name or 'none') end "
                f'obj:queueGameEngineLua("rawset(_G, \'{slot}\', \'" .. tostring(ok) .. "|" .. '
                'tostring(n) .. "|" .. tostring(lo) .. "|" .. tostring(hi) .. "|" .. '
                'tostring(flo) .. "|" .. tostring(fhi) .. "|" .. tostring(rlo) .. "|" .. '
                'tostring(rhi) .. "|" .. table.concat(w, ",") .. "\')")'
            )
            s.lua(
                f"rawset(_G, '{slot}', nil); local v = scenetree.findObject({model!r}); "
                f"if v then v:queueLuaCommand([[{chunk}]]) end; return jsonEncode({{ok = true}})"
            )
            s.step(WHEEL_QUERY_STEPS)
            answer = s.lua(f"return jsonEncode({{value = rawget(_G, '{slot}') or ''}})")
            parts = str(answer.get("value", "")).split("|")
            if len(parts) < 9 or parts[0] != "true":
                return {"read_by": "FAILED", "reach_m": None, "nodes": 0, "wheels": []}
            lo, hi = float(parts[2]), float(parts[3])
            flo, fhi, rlo, rhi = (float(parts[k]) for k in (4, 5, 6, 7))
            if not (-20.0 < lo < 20.0 and -20.0 < hi < 20.0) or hi - lo < 1.0:
                return {"read_by": "OUT OF RANGE", "reach_m": None, "nodes": 0, "wheels": []}
            wheels = [w for w in parts[8].split(",") if w]
            return {
                "read_by": "node cloud",
                "nodes": int(float(parts[1])),
                # offsets from the vehicle's own reference point, so the caller adds its y_local
                "reach_m": round(max(abs(lo), abs(hi)), 3),
                "reach_both_sides_m": [round(lo, 3), round(hi, 3)],
                "across_extent_m": round(hi - lo, 3),
                # THE PLACEMENT NUMBER (C6-1): where the body's centre sits relative to the
                # point the harness teleports.  Positive means the body is offset toward +y.
                "centre_offset_from_the_reference_m": round((lo + hi) / 2.0, 4),
                "half_extent_across_m": round((hi - lo) / 2.0, 4),
                # the model's own box, in ITS frame: pose-independent, so the across-axis
                # geometry can be re-derived at any heading without another read
                "body_centre_in_vehicle_frame_m": [
                    round((flo + fhi) / 2.0, 4),
                    round((rlo + rhi) / 2.0, 4),
                ],
                "body_half_extents_in_vehicle_frame_m": [
                    round((fhi - flo) / 2.0, 4),
                    round((rhi - rlo) / 2.0, 4),
                ],
                "vehicle_axes_used": {
                    "forward_xy": [round(fx, 6), round(fy, 6)],
                    "right_xy": [round(rx, 6), round(ry, 6)],
                    "across_xy": [round(ax, 6), round(ay, 6)],
                },
                "wheels": wheels,
                "wheels_on_the_ground": sum(1 for m in wheels if m and m != "none"),
            }

        def _body_across_at(body: dict[str, Any], pose: dict[str, Any]) -> dict[str, float] | None:
            """Re-derive the body's across-axis centre and half-extent AT ANOTHER POSE.

            N7: r5's grid took the reach at the LAUNCH pose and added it to the widest
            excursion of the whole run, which for every steering cell and every cell that
            spins against the wall are two different bodies.  The node cloud read gives a box
            in the VEHICLE's own frame, and that box does not change as the car turns -- so
            rotating it into the deck's across axis at each sample costs no sim ticks and
            gives the body's real outboard extent tick by tick.

            It is a box approximation of a rounded body and it is stated as one: at oblique
            headings a box overstates by up to ~0.3 m (critic pass 5, C6-3), so the extent it
            reports is an upper bound on the body and the DIRECTION of that error is known.
            """

            centre = body.get("body_centre_in_vehicle_frame_m")
            half = body.get("body_half_extents_in_vehicle_frame_m")
            if not centre or not half:
                return None
            fx, fy = float(pose["dx"]), float(pose["dy"])
            plan = math.hypot(fx, fy)
            if plan < 1e-6:
                return None
            fx, fy = fx / plan, fy / plan
            rx, ry = fy, -fx
            f_across = fx * float(across[0]) + fy * float(across[1])
            r_across = rx * float(across[0]) + ry * float(across[1])
            offset = centre[0] * f_across + centre[1] * r_across
            reach = abs(half[0] * f_across) + abs(half[1] * r_across)
            body_y = float(pose["y_local"]) + offset
            return {
                "body_centre_y_local": body_y,
                "half_extent_across_m": reach,
                "outboard_extent_m": abs(body_y) + reach,
            }

        def _drive_exit(
            name: str,
            x_local: float,
            heading: float,
            target_v: float,
            kind: str,
            ticks: int = 340,
        ) -> dict[str, Any]:
            """Drive off one exit and sample the whole trajectory through to rest.

            Three phases, and which one the car is in is decided by WHERE it is, not by how
            far below the deck plane it has fallen.  A single "brake once z < deck - 1 m"
            rule brakes a crown run 1.5 m before the lip and a ramp run halfway down the
            wedge, and then the speed the exit was driven at is not the speed it was left
            at.  ``run_to`` for the crown is 3 m short of the roll-off, so the car is
            COASTING through the whole arc.
            """

            # settle on the HANDBRAKE, then release: r2's second certification run started
            # three of seven drives with 1.4-1.6 m/s still on the clock from the teleport,
            # and one of them never went anywhere because it was still rolling backwards.
            s.teleport(VEH, _bench_point(x_local, 0.0), heading, z=report["deck_z_mean"] + 1.05)
            s.control(VEH, throttle=0.0, brake=0.0, parkingbrake=1.0, steering=0.0)
            s.step(60)
            s.control(VEH, throttle=0.0, brake=0.0, parkingbrake=0.0, steering=0.0)
            s.step(8)
            launch = _pose()
            steps = 0
            samples = [_sample(steps, launch, _wheels())]
            steps += WHEEL_QUERY_STEPS
            airborne = 0
            settle = 0
            rest_tick = None
            released_at = None
            braking = False
            landed_at: int | None = None
            deck = report["deck_z_mean"]
            for tick in range(1, ticks + 1):
                pose = _pose()
                wheels = None
                if tick % 16 == 0 or tick < 3:
                    wheels = _wheels()
                    steps += WHEEL_QUERY_STEPS
                samples.append(_sample(steps, pose, wheels))
                if wheels == 0:
                    airborne += 1
                # ON THE GROUND?  A car that is airborne must not have its wheels locked --
                # r2's second certification run braked from the moment the flank drop began
                # and the car landed on locked wheels and went over onto its roof, where the
                # identical drop with free wheels had rolled to 60 deg and come back.
                ground = float(terrain.surface_z(pose["x"], pose["y"]))
                landed = pose["z"] - ground < 1.6
                drive = 0.0  # every tick decides its own throttle; coasting means coasting
                stop = braking
                if kind == "crown":
                    if pose["x_local"] < geom["crown_x"] - 3.0:
                        gap = target_v - pose["hspeed"]
                        drive = 0.0 if gap <= 0.0 else min(1.0, 0.25 + 0.20 * gap)
                    elif pose["x_local"] < geom["break_x"] + 4.0:
                        if released_at is None:
                            released_at = round(float(pose["x_local"]), 2)
                    elif landed:
                        stop = True
                elif kind == "flank":
                    if pose["z"] > deck - 1.0:
                        drive = 0.30 if pose["hspeed"] < target_v else 0.0
                    elif landed:
                        stop = True
                elif pose["x_local"] > geom["toe_x"] + 2.0:
                    drive = 0.30 if pose["hspeed"] < target_v else 0.0
                elif landed:
                    stop = True
                if stop and not braking:
                    landed_at = len(samples) - 1
                braking = braking or stop
                if braking:
                    # THE FOOT BRAKE IS NEVER TOUCHED AFTER THE LANDING (r4).
                    #
                    # r2 saw cars leave the descent's foot at rest and arrive 300 m away at
                    # 20 m/s and could not explain it; r3 diagnosed "a sustained brake at a
                    # standstill is reverse" and split the input -- brake above 0.5 m/s,
                    # handbrake below.  The runaway SURVIVED that fix and is in r3's own
                    # certified boot: ``inner_flank_drop`` travels 306.5 m at a governed
                    # 20.216 m/s, deterministically (``r3_flat_deck_prestage`` repeats it to
                    # the millimetre).  r4 root-caused it off that trajectory (report
                    # section 2.6): the split is a LATCH.  The car dips under 0.5 m/s, the
                    # foot brake is released and the handbrake goes on; the handbrake does
                    # not hold a car still rolling on a cross-slope; the speed comes back
                    # over 0.5 and the foot brake goes on again -- but by then the automatic
                    # has selected R, and from that tick the brake input IS the reverse
                    # throttle.  The car accelerates at ~8 m/s^2 to 20.16 m/s, which is the
                    # etk800's reverse gear against its own rev limiter, and holds it up a
                    # 2.3 m rise for 200 m: not gravity, not a glitch, the harness's own
                    # input.  The trajectory says so directly -- speed rises MONOTONICALLY
                    # while `brake` is 1.0, and z rises with it.
                    #
                    # So: the parking brake alone, applied once and never released.  It
                    # decelerates and holds without touching the gearbox, and there is no
                    # input left that a gear selection can turn into a throttle.
                    drive = 0.0
                    s.control(VEH, throttle=0.0, brake=0.0, parkingbrake=1.0)
                else:
                    s.control(VEH, throttle=drive, brake=0.0, parkingbrake=0.0)
                # "at rest" is 1.0 s under 0.5 m/s, not one instantaneous reading under
                # 1.0 m/s: a car that has just dropped 3.4 m is still oscillating on its
                # springs, and r1's single sample is what produced `rest_speed 1.739` on a
                # car that had stopped.
                settle = settle + 1 if pose["hspeed"] < 0.5 else 0
                if settle * STEP >= 60 and tick > 40:
                    rest_tick = tick
                    break
                s.step(STEP)
                steps += STEP
            # The rest state is the LAST SAMPLED pose, and nothing is stepped after it.
            # r2's first certification run applied `brake + parkingbrake` and stepped a
            # further 3 s before reading the rest, and every one of those reads came back
            # tens of metres away at 10-20 m/s -- a reading with no trajectory behind it,
            # exactly the class of number this round exists to stop publishing.  The settle
            # criterion (1.0 s under 0.5 m/s) already IS the proof that the car has stopped.
            rest = _pose()
            samples.append(_sample(steps, rest, _wheels()))
            ground = float(terrain.surface_z(rest["x"], rest["y"]))
            lip = [r for r in samples if r["x_local"] >= geom["break_x"] - 0.05]
            # r4 (critic C5-3): what the car does AFTER it has landed and the harness has
            # begun stopping it.  ``upright`` / ``rest_speed`` / ``min_up_z`` all pass on a
            # car that drove itself 306 m at 20 m/s and then parked, so none of them can see
            # a runaway; these two can, and they are gated below.
            after = samples[landed_at:] if landed_at is not None else []
            post = {
                "post_landing_samples": len(after),
                "post_landing_max_v": round(max((r["v"] for r in after), default=0.0), 3),
                "post_landing_travel_m": (
                    round(
                        math.dist(
                            (after[0]["x_local"], after[0]["y_local"]),
                            (samples[-1]["x_local"], samples[-1]["y_local"]),
                        ),
                        2,
                    )
                    if after
                    else 0.0
                ),
                "landed_at_x_local": after[0]["x_local"] if after else None,
                "landed_at_v": after[0]["v"] if after else None,
                "stopped_with": "parkingbrake only, never the foot brake (r4)",
            }
            return {
                **post,
                "exit": name,
                "heading": round(heading, 2),
                "target_v": target_v,
                "launch": [round(launch["x"], 2), round(launch["y"], 2), round(launch["z"], 2)],
                "launch_x_local": round(float(launch["x_local"]), 2),
                "released_at_x_local": released_at,
                "rest": [round(rest["x"], 2), round(rest["y"], 2), round(rest["z"], 2)],
                "rest_x_local": round(float(rest["x_local"]), 2),
                "rest_y_local": round(float(rest["y_local"]), 2),
                "rest_terrain_z": round(ground, 3),
                "rest_above_terrain_m": round(rest["z"] - ground, 3),
                "up_z": round(float(rest["uz"]), 4),
                "upright": bool(float(rest["uz"]) > 0.70),
                "min_up_z": round(min(r["up_z"] for r in samples), 4),
                "travelled_m": round(
                    math.dist((launch["x"], launch["y"]), (rest["x"], rest["y"])), 2
                ),
                "displacement_local": [
                    round(float(rest["x_local"] - launch["x_local"]), 2),
                    round(float(rest["y_local"] - launch["y_local"]), 2),
                ],
                "rest_speed": round(float(rest["hspeed"]), 3),
                "came_to_rest_after_s": None if rest_tick is None else samples[-2]["t"],
                "ticks_used": rest_tick or ticks,
                "max_v": round(max(r["v"] for r in samples), 3),
                "v_at_the_lip": round(lip[0]["v"], 3) if lip else None,
                "airborne_samples": airborne,
                "samples": samples,
            }

        def _drive_grid(
            name: str,
            x_local: float,
            heading: float,
            target_v: float,
            ticks: int = 520,
            steer: float = 0.0,
            model: str = VEH,
        ) -> dict[str, Any]:
            """One cell of the r3 exit grid: reach ``target_v`` on the deck, then COAST.

            NO BRAKE AT ANY POINT.  Critic pass 2's first boot braked at
            ``z - ground < 1.6 m`` and could not attribute the resulting inversion to the
            map, so it re-ran with the brake wired out; this harness starts there, and the
            handbrake goes on only once the car has already stopped.  Whatever the grid
            reports is the map's doing.

            ``steer`` holds a constant steering input from the moment the target speed is
            reached, which is the case the design actually has to survive: a carrier fleeing
            the arena does not leave on a surveyed heading, it leaves on the heading its
            last correction gave it.
            """

            # --- r6, C6-1: PLACE THE BODY, NOT THE REFERENCE POINT ------------------------
            #
            # ``s.teleport`` puts the vehicle's REFERENCE POINT where it is told.  The body is
            # not centred on the reference: measured over the pickup's own 791 nodes its body
            # centre sits up to 1.17 m to one side of it, and the sign follows the heading.
            # So r5's ``_bench_point(x_local, 0.0)`` never put a car square on the 6.0 m
            # trough -- at +90 deg it stood the truck's body 0.99 m off the centreline, put
            # its tail on top of the wall, and the cell then travelled 4 cm and was scored as
            # a departure.  Critic pass 5 measured it at every pose of both vehicles and both
            # probes: a CENTRED body fits the trough with 0.45 m to spare everywhere.
            #
            # This is the third instance of one confusion in three places (boot 1's centreline
            # contact test, boot 2's half-extents on the reference point, boot 3's placement),
            # and ``level_facts`` now carries it as a law: every placement, extent and contact
            # test must say WHICH point it uses and prove it from the node cloud at the pose.
            # So: place nominally, READ the body, shift by minus its centre offset, READ IT
            # AGAIN, and publish the residual.  Both reads are node-cloud reads at the pose
            # they describe; the nominal one is exactly the number r5 and the critic recorded,
            # kept so the two revisions can be compared cell for cell.
            z_launch = report["deck_z_mean"] + 1.05

            def _settle(y_place: float) -> dict[str, Any]:
                s.teleport(model, _bench_point(x_local, y_place), heading, z=z_launch)
                s.control(model, throttle=0.0, brake=0.0, parkingbrake=1.0, steering=0.0)
                s.step(60)
                s.control(model, throttle=0.0, brake=0.0, parkingbrake=0.0, steering=0.0)
                s.step(8)
                return _pose(model)

            nominal_pose = _settle(0.0)
            nominal = _body_across_reach(model, nominal_pose)
            nominal_offset = nominal.get("centre_offset_from_the_reference_m")
            placed_at_y = 0.0
            placement = "the REFERENCE point on the centreline (the read failed)"
            launch, body = nominal_pose, nominal
            if nominal_offset is not None:
                placed_at_y = -float(nominal_offset)
                placement = "the BODY CENTRE on the centreline, from the node cloud at the pose"
                launch = _settle(placed_at_y)
                body = _body_across_reach(model, launch)
                if body.get("centre_offset_from_the_reference_m") is None:
                    # never let a failed second read silently un-do the correction: keep the
                    # centred placement, keep the FIRST read's geometry, and name it
                    body = dict(nominal)
                    placement = "the BODY CENTRE on the centreline (second read failed)"
            body_at_launch = _body_across_at(body, launch)
            nominal_body_y = (
                float(nominal_pose["y_local"]) + float(nominal_offset)
                if nominal_offset is not None
                else None
            )
            steps = 0
            samples = [_sample(steps, launch, None)]
            deck = report["deck_z_mean"]
            settle = 0
            rest_tick = None
            left_deck = None
            over_edge = False
            widest = 0.0
            widest_body = 0.0
            widest_body_at = None
            at_speed = False
            for tick in range(1, ticks + 1):
                pose = _pose(model)
                row = _sample(steps, pose, None)
                here = _body_across_at(body, pose)
                if here is not None:
                    row["body_y_local"] = round(here["body_centre_y_local"], 3)
                    row["body_outboard_m"] = round(here["outboard_extent_m"], 3)
                samples.append(row)
                on_deck = pose["z"] > deck - 0.40
                if left_deck is None and not on_deck:
                    left_deck = [row["t"], row["x_local"], row["y_local"], row["up_z"], row["v"]]
                    # r4: WHERE it left decides what the cell means.  A car that reaches the
                    # crown and drives off the end has used the designed exit; a car that
                    # goes over a long edge between the ramp's join and the crown has left
                    # over the 3.5 m ledge, which is the departure this element's three
                    # revisions of rollovers are about.  The two were indistinguishable in
                    # r3's grid, and a containment bolster turns the first into the ONLY
                    # outcome, so the grid has to be able to say which happened.
                    over_edge = bool(
                        abs(row["y_local"]) > geom["deck_flat_half"]
                        and geom["join_x"] < row["x_local"] < geom["crown_x"]
                    )
                if on_deck and geom["join_x"] < row["x_local"] < geom["crown_x"]:
                    widest = max(widest, abs(row["y_local"]))
                    # N7 / C6-1 consequence 2: ``widest_y_local`` is the REFERENCE point, and
                    # putting it in a column beside ``deck_flat_half`` reads as a clearance
                    # that it is not.  This is the BODY's own outboard extent, re-derived from
                    # the vehicle-frame box at THIS pose, so the two numbers are comparable.
                    if here is not None and here["outboard_extent_m"] > widest_body:
                        widest_body = here["outboard_extent_m"]
                        widest_body_at = [row["t"], row["x_local"], row["y_local"]]
                at_speed = at_speed or pose["hspeed"] >= target_v
                drive = 0.0
                if on_deck and pose["hspeed"] < target_v:
                    drive = min(1.0, 0.25 + 0.20 * (target_v - pose["hspeed"]))
                s.control(
                    model,
                    throttle=drive,
                    brake=0.0,
                    parkingbrake=0.0,
                    steering=steer if at_speed else 0.0,
                )
                settle = settle + 1 if pose["hspeed"] < 0.5 else 0
                if settle * STEP >= 60 and tick > 60:
                    rest_tick = tick
                    break
                s.step(STEP)
                steps += STEP
            rest = _pose(model)
            samples.append(_sample(steps, rest, None))
            s.control(model, throttle=0.0, brake=0.0, parkingbrake=1.0, steering=0.0)
            s.step(20)
            ground = float(terrain.surface_z(rest["x"], rest["y"]))
            worst = min(r["up_z"] for r in samples)
            # r5: SCORE THE LAUNCH BY DISPLACEMENT BEFORE SCORING THE OUTCOME.
            #
            # ``contained_by_the_bolster`` is ``not over_edge``, and ``over_edge`` is only
            # ever set at the moment the car first leaves the deck -- so a cell whose car
            # never moved reports "contained" and passes the gate while testing nothing.
            # That is B3's law twice over ("a live 'blocked' result can be a launch that
            # never happened"; "score a launch by measured displacement over a stated
            # threshold"), and this grid is the round's central instrument.  Path length,
            # not intent, and the target speed reached, not requested.
            path = round(
                sum(
                    math.dist((a["x_local"], a["y_local"]), (b["x_local"], b["y_local"]))
                    for a, b in itertools.pairwise(samples)
                ),
                2,
            )
            peak_v = round(max(r["v"] for r in samples), 3)
            # ... but the bar cannot be DISPLACEMENT ALONE on this grid, and pretending it can
            # would be the same mistake in the other direction.  A cell driven square into the
            # wall has 3.0 m of deck between the centreline and the treatment, so it CANNOT
            # travel 4 m before it arrives -- E2's own +-90 cells travelled 2-3 m and would
            # have been scored "no launch" while testing the hardest impact the deck can be
            # given.  So the bar is B3 r11's OTHER half: score "reached" by CONTACT.
            #
            # AND CONTACT IS A PROPERTY OF THE BODY, NOT OF THE CENTRELINE.  r5's first boot
            # scored it as ``|widest y| >= deck_flat_half - 1.2`` and fired on 23 of 115 cells
            # -- every one of them a steep heading whose car was hard against the wall, two of
            # them pushed 27 m ALONG it, with a centreline that never passed 1.8 m.  A
            # 4.67 x 2.02 m body at 45 deg reaches 1.65 m further outboard than its centre and
            # at 90 deg 2.34 m further, so the centreline is simply the wrong point on the car.
            # The half-extents are READ OUT OF THE RUNNING SIM per model (``_model_box``), not
            # assumed, and the replay over that boot's own recorded cells
            # (``b4/r5/clause_check.json``) takes the clause from 23 firings to 1.
            half_len, half_wid = _model_box(model)
            lean = math.radians(float((heading - along_heading + 540.0) % 360.0 - 180.0))
            derived_reach = half_len * abs(math.sin(lean)) + half_wid * abs(math.cos(lean))
            # r5 boot 2, the THIRD revision of this same clause: the half-extent sum is a body
            # centred on the vehicle's REFERENCE point, and the pickup's is not.  Measured over
            # 791 nodes the truck square across the deck reaches 3.430 m to one side against the
            # 2.480 the sum gives -- 0.95 m of body the clause could not see, and exactly the
            # 0.95 m that puts its tail on top of the wall.  Prefer the measurement; keep the
            # derivation beside it so the two can be compared; a FAILED read falls back to the
            # derivation and is named, never silently made lenient.
            measured_reach = body.get("reach_m")
            reach = float(measured_reach) if measured_reach else derived_reach
            # r6: with the body CENTRED the reach that matters is the half-extent about the
            # body's own centre, not the largest offset from a reference point that is no
            # longer where the body is.  Both are published; the treatment test uses the
            # body's outboard extent tracked over the trajectory (``widest_body``) and falls
            # back to r5's ``widest + reach`` only if the vehicle-frame read failed.
            half_extent = body.get("half_extent_across_m")
            outboard_r5 = widest + reach
            outboard = widest_body if widest_body > 0.0 else outboard_r5
            outboard_read_by = (
                "the body box rotated into the across axis at EACH pose"
                if widest_body > 0.0
                else "r5's formula: max|y_ref| + reach(t=0)"
            )
            met_the_treatment = bool(outboard >= geom["deck_flat_half"] or left_deck is not None)
            reached_speed = bool(peak_v >= 0.85 * target_v)
            # ...and the ONE cell boot 2 fired on is a fact about the deck rather than a
            # departure, but not the fact the previous revision named.  A pickup placed square
            # across the 6.0 m trough is not WEDGED between the two walls -- it is BEACHED ON
            # ONE: its tail reaches y_local +3.471, past the deck's 3.0 m edge and past the
            # bolster's 3.3 m crest half-width, its two rear wheels hang 0.78 m above the deck
            # reading contact material ``none``, and it travels 0.06 m under throttle at pitch
            # -10.8 deg.  Both halves are measured at the LAUNCH pose -- the body's reach, and
            # the wheels that are not on the ground -- and a held cell is STILL gated on
            # rolling, containment and uprightness; only the "it measured a departure" clause
            # is relaxed, and the hold is published rather than excluded.
            on_the_ground = body.get("wheels_on_the_ground")
            wheels_read = body.get("wheels") or []
            off_the_ground = bool(
                wheels_read and on_the_ground is not None and on_the_ground < len(wheels_read)
            )
            over_the_treatment = bool(reach >= geom["deck_flat_half"] - GRID_WEDGE_SLACK_M)
            # --- r6, C6-1 part one: ``held`` IS NOT ``launched`` --------------------------
            #
            # r5's bar read "a cell counts as a measured departure either because it
            # travelled, or because it did not": ``launched = wedged or (path >= 1.0 and
            # ...)``, where ``wedged`` is true precisely when the car did not move.  On the
            # critic's boot that passed THREE of four heavy cells at 4-6 cm of travel, each
            # of which would then have been counted in a "115 contained" headline.  A car
            # that moved 4 cm has not been contained by anything.
            #
            # So a held cell is now its OWN outcome.  It is published with its full
            # diagnosis, it is excluded from the containment tally, and it is NOT a
            # departure -- ``launched`` is displacement plus arrival, with no disjunct.  With
            # the body centred there is no geometric reason for a hold to occur at all, so a
            # hold is a finding rather than an exemption.
            held = bool(over_the_treatment and path < GRID_MOVED_MIN_M)
            launched = bool(path >= GRID_MOVED_MIN_M and (met_the_treatment or reached_speed))
            return {
                "probe": name,
                "model": model,
                "heading": round(heading, 2),
                "path_length_m": path,
                "moved": bool(path >= GRID_MOVED_MIN_M),
                # --- WHICH POINT WAS PLACED, and what the node cloud says about it --------
                "placement_point": placement,
                "placed_reference_at_y_local": round(placed_at_y, 4),
                "body_centre_offset_from_the_reference_m": body.get(
                    "centre_offset_from_the_reference_m"
                ),
                "body_centre_y_local_at_launch": (
                    round(body_at_launch["body_centre_y_local"], 4) if body_at_launch else None
                ),
                "body_centre_y_local_if_r5_had_placed_it": (
                    round(nominal_body_y, 4) if nominal_body_y is not None else None
                ),
                "body_reach_at_the_NOMINAL_pose_m": nominal.get("reach_m"),
                "body_reach_both_sides_at_the_NOMINAL_pose_m": nominal.get("reach_both_sides_m"),
                "body_half_extents_m": [round(half_len, 3), round(half_wid, 3)],
                "body_across_reach_m": round(reach, 3),
                "body_across_half_extent_m": half_extent,
                "body_across_reach_read_by": body.get("read_by"),
                "body_across_reach_derived_m": round(derived_reach, 3),
                "body_reach_both_sides_m": body.get("reach_both_sides_m"),
                "body_box_in_vehicle_frame_m": body.get("body_half_extents_in_vehicle_frame_m"),
                "body_centre_in_vehicle_frame_m": body.get("body_centre_in_vehicle_frame_m"),
                "body_nodes_read": body.get("nodes"),
                "wheel_materials_at_launch": wheels_read,
                "wheels_on_the_ground_at_launch": on_the_ground,
                "wheels_off_the_ground_at_launch": bool(off_the_ground),
                "beached_on_the_wall_at_launch": bool(
                    off_the_ground and reach >= geom["deck_flat_half"] and path < GRID_MOVED_MIN_M
                ),
                "body_outboard_extent_m": round(outboard, 3),
                "body_outboard_extent_read_by": outboard_read_by,
                "body_outboard_extent_r5_formula_m": round(outboard_r5, 3),
                "widest_body_outboard_at": widest_body_at,
                "met_the_treatment": met_the_treatment,
                "held_at_launch": held,
                # kept under its r5 name so the two boots' rows line up, but it no longer
                # feeds ``launched`` -- see the block above
                "wedged_at_launch": held,
                "reached_target_speed": reached_speed,
                "launched": launched,
                "counts_toward_containment": bool(launched and not held),
                "travelled_4m": bool(path >= GRID_LAUNCH_MIN_M),
                "off_axis_deg": round((heading - along_heading + 540.0) % 360.0 - 180.0, 1),
                "steering": steer,
                "target_v": target_v,
                "max_v": round(max(r["v"] for r in samples), 3),
                "left_the_deck_at": left_deck,
                "left_over_a_long_edge": bool(over_edge),
                "contained_by_the_bolster": bool(not over_edge),
                # the REFERENCE point's widest excursion, named as such (C6-1 consequence 2)
                "widest_y_local_on_the_deck": round(widest, 3),
                "widest_y_local_is_the": "REFERENCE point, not the body",
                "widest_body_outboard_on_the_deck_m": round(widest_body, 3),
                "rest_x_local": round(float(rest["x_local"]), 2),
                "rest_y_local": round(float(rest["y_local"]), 2),
                "rest_above_terrain_m": round(rest["z"] - ground, 3),
                "up_z": round(float(rest["uz"]), 4),
                "min_up_z": round(worst, 4),
                # the sharp criterion.  up.z < 0 is PAST 90 degrees: the car is on its side
                # going over, and every r1/r2 failure this round exists to stop crossed it.
                "rolled_past_90": bool(worst < 0.0),
                "upright": bool(float(rest["uz"]) > 0.70),
                "rest_speed": round(float(rest["hspeed"]), 3),
                "came_to_rest": rest_tick is not None,
                # --- N1: the outcome the section ships and does not count --------------
                # ``e2_score`` calls this BEACHED and used it to refute the chamfer (28 of
                # 30) and to price the bolster (10 of 29).  That statistic decided the A/B
                # and was then not carried across to the section that shipped, where the
                # critic counts it at 43 of 115.  It is a column now.
                "at_rest_still_on_the_log": bool((rest["z"] - ground) > GRID_ON_THE_LOG_M),
                # --- N2: "rest" is not rest for a car idling in D -----------------------
                # the grid applies no stopping input at all and an automatic creeps at about
                # 1.9 m/s, so 54 of r5's 115 cells never met ``hspeed < 0.5`` and their
                # ``rest_*`` fields are "wherever the 520-tick budget ran out".
                "rest_is_where_the_budget_ran_out": rest_tick is None,
                "rest_tick": rest_tick,
                # --- N3: the C5-3 bounds, MEASURED on the grid, never gated here --------
                # ``post_landing_travel_m <= 40`` and ``post_landing_max_v <= target + 2``
                # gate the five exit drops.  Applied to the grid they fail dozens of cells,
                # which is legitimate -- a crown departure is meant to run out across the
                # meadow -- but a reader of the section will believe every departure in this
                # round is bounded unless the asymmetry is stated with its own number.
                "travel_after_leaving_the_deck_m": (
                    round(
                        sum(
                            math.dist((a["x_local"], a["y_local"]), (b["x_local"], b["y_local"]))
                            for a, b in itertools.pairwise(
                                [r for r in samples if r["t"] >= left_deck[0]]
                            )
                        ),
                        2,
                    )
                    if left_deck
                    else None
                ),
                "max_v_after_leaving_the_deck": (
                    round(max(r["v"] for r in samples if r["t"] >= left_deck[0]), 3)
                    if left_deck
                    else None
                ),
                "samples": samples,
            }

        def _climb(name: str, throttle: float, model: str = VEH) -> dict[str, Any]:
            """Try to drive UP the west crown from the meadow -- the one-way test.

            Critic pass 2 climbed r2's 16 m / 26 % descent in an etk800 at 45 % throttle and
            at full throttle, so the log had two entrances and the design's third one-way
            drop was gone without the report saying so.  The shipped crown is 10.0 m at
            67.8 % and it IS climbable by a road car (deviation 7 declares the west end
            two-way); this measures who climbs it, reading the car's WHOLE TRAJECTORY (r5).
            """

            start = _bench_point(geom["break_x"] + 14.0, 0.0)
            s.teleport(model, start, (along_heading + 180.0) % 360.0, z=None)
            s.control(model, throttle=0.0, brake=0.0, parkingbrake=1.0, steering=0.0)
            s.step(60)
            s.control(model, throttle=0.0, brake=0.0, parkingbrake=0.0, steering=0.0)
            highest = -1e9
            rows = []
            # r5: the conjunction is evaluated on EVERY tick, not only on the 1-in-8 ticks the
            # report keeps.  The pose is already read each tick, so this costs zero sim ticks
            # (§5.2's pose-read control: 21 reads, 0.000 m of drift) and it cannot miss an
            # arrival that fell between two recorded rows.
            arrival_ticks = 0
            first_arrival: dict[str, Any] | None = None
            pose = _pose(model)
            for tick in range(1, 400):
                pose = _pose(model)
                z_local = float(pose["z"]) - _origin_z
                highest = max(highest, z_local)
                if (
                    z_local >= geom["deck_z"] - 0.35
                    and abs(float(pose["y_local"])) <= geom["deck_flat_half"] + 0.5
                    and float(pose["x_local"]) <= geom["crown_x"] + 0.5
                ):
                    arrival_ticks += 1
                    if first_arrival is None:
                        first_arrival = {
                            "t": round(tick * STEP / 60.0, 2),
                            "x_local": round(float(pose["x_local"]), 2),
                            "y_local": round(float(pose["y_local"]), 2),
                            "z_local": round(z_local, 3),
                            "v": round(float(pose["hspeed"]), 2),
                        }
                if tick % 8 == 0:
                    rows.append(
                        {
                            "t": round(tick * STEP / 60.0, 2),
                            "x_local": round(float(pose["x_local"]), 2),
                            "y_local": round(float(pose["y_local"]), 2),
                            "z_local": round(z_local, 3),
                            "v": round(float(pose["hspeed"]), 2),
                        }
                    )
                s.control(model, throttle=throttle, brake=0.0, parkingbrake=0.0, steering=0.0)
                s.step(STEP)
            final = _pose(model)
            s.control(model, throttle=0.0, brake=0.0, parkingbrake=1.0)
            s.step(20)
            final_z = float(final["z"]) - _origin_z
            final_y = float(final["y_local"])
            final_x = float(final["x_local"])
            # r4 (critic N1): READ THE FINAL POSE, NOT THE TRAJECTORY'S MAXIMUM.
            #
            # r3's predicate was ``max_z_local >= deck_z - 0.35`` over the whole run, and the
            # certified boot published ``crown_climb_pickup_wot: reached_the_plateau true``
            # for a pickup whose own samples then show it at z_local 1.336, v 0.00, for
            # eleven consecutive seconds at throttle 1.0.  The critic re-drove it recording
            # the lateral coordinate the round did not and found it at y_local -8.53 -- 8.5 m
            # off a log whose deck is 3.5 m half width.  It had pitched its nose up on the
            # crown's taper, fallen off the SIDE, and sat there.  A transient maximum reached
            # while a car is falling off a log is not an arrival.
            #
            # So the predicate needs three facts at once: high enough, over the deck rather
            # than beside it, and back on the parallel body past the crown's taper.  Every one
            # of the three is necessary; r3's was none of them.
            #
            # r5 (adopted from the SECOND B4 r5 worker's `crown_rescore_r5.py`, and re-derived
            # here off boot 1's own 49-sample trajectories before this predicate was changed):
            # r4 was right about the conjunction and WRONG about WHEN to evaluate it.  Reading
            # it at the LAST sample fails a car that climbs the crown and then keeps driving --
            # which is exactly what both road-car legs did.  The 45 % leg is on the deck at
            # t 1.87 s (x_local 37.64, y_local 0.23, z_local 3.722, v 7.14) and ends 242 m
            # away thirteen seconds later, and r4's rule reports that as "did not climb".
            #
            # So r3's rule and r4's are wrong in OPPOSITE directions -- a transient max of one
            # variable passes a car falling off the side; a conjunction at one instant fails a
            # car that arrives and leaves.  Deviation 7 asks "can a road car get UP", which is
            # a conjunction ANYWHERE on the trajectory.  All three readings are published so a
            # later round can see the predicate change rather than infer it from a verdict.
            on_the_deck = abs(final_y) <= geom["deck_flat_half"] + 0.5
            past_the_taper = final_x <= geom["crown_x"] + 0.5
            high_enough = final_z >= geom["deck_z"] - 0.35
            return {
                "probe": name,
                "model": model,
                "throttle": throttle,
                "max_z_local": round(highest, 3),
                "final_z_local": round(final_z, 3),
                "final_x_local": round(final_x, 2),
                "final_y_local": round(final_y, 2),
                "final_v": round(float(final["hspeed"]), 3),
                "deck_z_local": geom["deck_z"],
                "final_pose_is_high_enough": bool(high_enough),
                "final_pose_is_over_the_deck": bool(on_the_deck),
                "final_pose_is_past_the_taper": bool(past_the_taper),
                "reached_the_plateau": bool(first_arrival is not None),
                "arrival_ticks": arrival_ticks,
                "first_arrival": first_arrival,
                "reached_the_plateau_by_r4s_final_pose_rule": bool(
                    high_enough and on_the_deck and past_the_taper
                ),
                "reached_the_plateau_by_r3s_transient_max_rule": bool(
                    highest >= geom["deck_z"] - 0.35
                ),
                "fraction_of_the_fall_climbed": round(
                    max(0.0, final_z - geom["crown_foot_z"]) / geom["crown_fall"], 3
                ),
                "samples": rows,
            }

        # 52 m of plateau to reach 12 m/s, but never start on the ramp itself
        start_x = max(geom["join_x"] + 1.5, geom["crown_x"] - 55.0)
        drops = [
            _drive_exit(f"west_crown_exit_{int(v)}ms", start_x, along_heading, v, "crown", 420)
            for v in (4.0, 8.0, 10.0, 12.0)
        ]
        # r4: there are NO flank drops any more.  r3 launched two flank drives inside their
        # split-out windows; r4's first cut kept those windows open in a 0.90 m wall and its
        # own 59-cell boot rolled cars through them (a window is a ledge, and the straddle
        # formula says a ledge cannot be made safe at a shallow heading by any shape of
        # opening), so the second cut walled the whole long edge.  Driving square at a wall
        # is a grid cell now (the +-90 deg rows at 4, 8 and 12 m/s below), not an exit.
        assert ps.splitout_window("inner") is None, ps.BENCH["flank_splitouts"]
        assert ps.splitout_window("outer") is None, ps.BENCH["flank_splitouts"]
        drops.append(_drive_exit("ramp_foot", geom["join_x"] + 6.0, 210.0, 6.0, "ramp", 420))
        s.report["bench_exit_drops"] = drops
        #: r4: how far a car may travel, and how fast it may go, AFTER it has landed and the
        #: harness has begun stopping it.  The parking brake alone (the only input the r4
        #: policy uses) works on the rear axle only, so a 12 m/s crown landing on grass
        #: legitimately coasts 20-30 m before it holds; 40 m is that with margin, and the
        #: 306 m runaway r3 shipped is still eight times it.  The speed bound is the
        #: sharper one: a car that gains speed after landing is driving itself.
        POST_LANDING_TRAVEL_MAX_M = 40.0
        POST_LANDING_OVERSPEED_MAX = 2.0
        for drop in drops:
            thin = {k: v for k, v in drop.items() if k != "samples"}
            s.check(drop["upright"], f"the car did not rest upright off {drop['exit']}", thin)
            s.check(
                drop["rest_speed"] < 1.0, f"the car never came to rest off {drop['exit']}", thin
            )
            s.check(
                drop["min_up_z"] > 0.10,
                f"the car rolled past 84 deg off {drop['exit']}",
                thin,
            )
            # C5-3: the three checks above ALL pass on a runaway, so these two exist.  A car
            # that gains speed after it has landed is not being read by any pose gate; it is
            # either driving itself (the reverse-gear latch r4 root-caused) or the ground is
            # doing something the report has not described.  Either way the round must see it.
            s.check(
                drop["post_landing_travel_m"] <= POST_LANDING_TRAVEL_MAX_M,
                f"the car travelled {drop['post_landing_travel_m']} m after landing off "
                f"{drop['exit']} -- a runaway, not a drop",
                thin,
            )
            s.check(
                drop["post_landing_max_v"] <= drop["target_v"] + POST_LANDING_OVERSPEED_MAX,
                f"the car reached {drop['post_landing_max_v']} m/s after landing off "
                f"{drop['exit']}, against a {drop['target_v']} m/s target",
                thin,
            )

        # --- 4a. C5-3: THE RUNAWAY, REPRODUCED ON PURPOSE AND READ FROM THE GEARBOX -----
        # r3's certified boot recorded `inner_flank_drop` landing upright on the meadow at
        # 0.43 m/s and then driving 306.5 m at a governed 20.216 m/s, deterministically
        # (`r3_flat_deck_prestage` repeats it to the millimetre), while the harness was
        # applying r3's stop policy -- foot brake above 0.5 m/s, handbrake below -- and r2
        # before it "applied brake + parkingbrake and stepped a further 3 s" and read every
        # rest tens of metres away at 10-20 m/s.  The r4 reading of both is a LATCH INTO
        # REVERSE: BeamNG's default automatic behaviour (`gearboxBehavior` = arcade) shifts
        # into R when the brake is held at a standstill and from then on treats the brake
        # pedal AS the reverse throttle; 20.2 m/s is an etk800's reverse gear on its rev
        # limiter, which is why the runaway is "governed" and why it climbs a 2.3 m rise
        # without slowing.  A reading of a trajectory is not a proof, so this leg lands the
        # same car on the same meadow off the crown three times and reads the vehicle VM's
        # `electrics.values.gear / gearIndex / reverse` every quarter second beside the
        # speed, under three stop policies: r2's (hold the foot brake), r3's (the 0.5 m/s
        # split) and r4's (parking brake only, never the foot brake).  If the runaway is
        # the reverse latch, a leg that runs away shows R before its speed climbs, and the
        # r4 control never leaves the forward gears and never moves.
        def _vm_state(name: str = VEH) -> dict[str, Any]:
            """Gear, reverse flag and pedal values as the vehicle VM itself holds them."""

            slot = uuid.uuid4().hex[:6]
            chunk = (
                "local e = electrics.values "
                "local s = table.concat({tostring(e.gear), tostring(e.gearIndex), "
                "tostring(e.reverse), string.format('%.3f', e.throttle or -1), "
                "string.format('%.3f', e.brake or -1), "
                "string.format('%.3f', e.wheelspeed or -1), "
                "string.format('%.3f', e.parkingbrake or -1)}, ',') "
                f"obj:queueGameEngineLua(\"rawset(_G, 'hp_b4_vm_{slot}', '\" .. s .. \"')\")"
            )
            s.lua(
                f"rawset(_G, 'hp_b4_vm_{slot}', nil); "
                f"local v = scenetree.findObject({name!r}); "
                f"if v then v:queueLuaCommand([[{chunk}]]) end; "
                "return jsonEncode({ok = true})"
            )
            s.step(WHEEL_QUERY_STEPS)
            answer = s.lua(f"return jsonEncode({{value = rawget(_G, 'hp_b4_vm_{slot}') or ''}})")
            parts = str(answer.get("value", "")).split(",")
            keys = (
                "gear",
                "gearIndex",
                "reverse",
                "throttle",
                "brake",
                "wheelspeed",
                "parkingbrake",
            )
            if len(parts) != len(keys):
                return {"raw": answer.get("value")}
            return dict(zip(keys, parts, strict=True))

        def _land_and_stop(policy: str, hold_s: float = 8.0) -> dict[str, Any]:
            s.teleport(
                VEH, _bench_point(start_x, 0.0), along_heading, z=report["deck_z_mean"] + 1.05
            )
            s.control(VEH, throttle=0.0, brake=0.0, parkingbrake=1.0, steering=0.0)
            s.step(60)
            s.control(VEH, throttle=0.0, brake=0.0, parkingbrake=0.0, steering=0.0)
            s.step(8)
            rows: list[dict[str, Any]] = []
            landed_tick: int | None = None
            steps = 0
            for tick in range(1, 900):
                pose = _pose()
                ground = float(terrain.surface_z(pose["x"], pose["y"]))
                on_the_meadow = pose["x_local"] > geom["break_x"] + 4.0 and pose["z"] - ground < 1.6
                if landed_tick is None:
                    if on_the_meadow:
                        landed_tick = tick
                    elif pose["x_local"] < geom["crown_x"] - 3.0:
                        gap = 8.0 - pose["hspeed"]
                        drive = 0.0 if gap <= 0.0 else min(1.0, 0.25 + 0.20 * gap)
                        s.control(VEH, throttle=drive, brake=0.0, parkingbrake=0.0)
                    else:
                        s.control(VEH, throttle=0.0, brake=0.0, parkingbrake=0.0)
                if landed_tick is not None:
                    if policy == "r2_hold_the_foot_brake":
                        s.control(VEH, throttle=0.0, brake=1.0, parkingbrake=1.0)
                    elif policy == "r3_brake_above_half_a_metre_per_second":
                        if pose["hspeed"] > 0.5:
                            s.control(VEH, throttle=0.0, brake=1.0, parkingbrake=0.0)
                        else:
                            s.control(VEH, throttle=0.0, brake=0.0, parkingbrake=1.0)
                    else:
                        s.control(VEH, throttle=0.0, brake=0.0, parkingbrake=1.0)
                    if (tick - landed_tick) % 8 == 0:
                        vm = _vm_state()
                        steps += WHEEL_QUERY_STEPS
                        rows.append(
                            {**_sample(steps, pose, None), **{f"vm_{k}": v for k, v in vm.items()}}
                        )
                    if (tick - landed_tick) * STEP >= hold_s * 60.0:
                        break
                s.step(STEP)
                steps += STEP
            rest = _pose()
            s.control(VEH, throttle=0.0, brake=0.0, parkingbrake=1.0)
            s.step(20)
            first = rows[0] if rows else None
            reverse_rows = [
                r for r in rows if str(r.get("vm_reverse")) in ("1", "1.0", "true", "True")
            ]
            return {
                "policy": policy,
                "held_for_s": hold_s,
                "landed": landed_tick is not None,
                "landed_at_x_local": first["x_local"] if first else None,
                "landed_at_v": first["v"] if first else None,
                "post_landing_max_v": round(max((r["v"] for r in rows), default=0.0), 3),
                "post_landing_travel_m": (
                    round(
                        math.dist(
                            (first["x_local"], first["y_local"]),
                            (float(rest["x_local"]), float(rest["y_local"])),
                        ),
                        2,
                    )
                    if first
                    else None
                ),
                "rest_v": round(float(rest["hspeed"]), 3),
                "gears_seen": sorted({str(r.get("vm_gear")) for r in rows}),
                "gear_indices_seen": sorted({str(r.get("vm_gearIndex")) for r in rows}),
                "reverse_seen": bool(reverse_rows),
                "first_reverse_at_s": reverse_rows[0]["t"] if reverse_rows else None,
                "v_when_reverse_first_read": reverse_rows[0]["v"] if reverse_rows else None,
                "samples": rows,
            }

        gearbox = s.lua(
            "return jsonEncode({gearboxBehavior = tostring(settings.getValue('gearboxBehavior')), "
            "absBehavior = tostring(settings.getValue('absBehavior'))})"
        )
        runaway = {
            "what": (
                "the same crown landing three times; only the STOP POLICY after the landing "
                "differs, and the gearbox is read from the vehicle VM every 0.27 s"
            ),
            "settings": gearbox,
            "legs": [
                _land_and_stop("r2_hold_the_foot_brake"),
                _land_and_stop("r3_brake_above_half_a_metre_per_second"),
                _land_and_stop("r4_parkingbrake_only"),
            ],
        }
        for leg in runaway["legs"]:
            leg["accelerated_after_landing"] = bool(
                leg["landed"] and leg["post_landing_max_v"] > float(leg["landed_at_v"] or 0.0) + 3.0
            )
        runaway["verdict"] = {
            "legs_that_ran_away": [
                leg["policy"] for leg in runaway["legs"] if leg["accelerated_after_landing"]
            ],
            "every_runaway_read_reverse": all(
                leg["reverse_seen"] for leg in runaway["legs"] if leg["accelerated_after_landing"]
            ),
            "the_r4_policy_ran_away": any(
                leg["accelerated_after_landing"]
                for leg in runaway["legs"]
                if leg["policy"] == "r4_parkingbrake_only"
            ),
        }
        s.report["runaway_root_cause"] = runaway
        for leg in runaway["legs"]:
            thin = {k: v for k, v in leg.items() if k != "samples"}
            s.check(leg["landed"], f"the {leg['policy']} leg never landed on the meadow", thin)
            # a runaway that is NOT in reverse is a runaway this round has not explained
            s.check(
                not leg["accelerated_after_landing"] or leg["reverse_seen"],
                f"the {leg['policy']} leg gained speed after landing WITHOUT reading reverse",
                thin,
            )
            if leg["policy"] == "r4_parkingbrake_only":
                s.check(
                    not leg["accelerated_after_landing"] and not leg["reverse_seen"],
                    "the shipped r4 stop policy ran away or selected reverse",
                    thin,
                )
                s.check(
                    (leg["post_landing_travel_m"] or 0.0) <= POST_LANDING_TRAVEL_MAX_M,
                    "the shipped r4 stop policy did not hold the car",
                    thin,
                )

        # --- 4b. THE EXIT GRID (r3) ---------------------------------------------------
        # r2 drove the crown at 4 / 8 / 10 / 12 m/s on heading 30.0 EXACTLY and the flanks at
        # 3.4 m/s on exactly 90 deg across, and generalised seven drives on two axes to "off
        # every exit, rests upright -- 7 of 7 -- PROVEN".  Critic pass 2 drove the axes in
        # between with no brake input: 25 deg off-axis at 8 m/s came to rest INVERTED
        # (up.z -0.9790) 0.95 m above the meadow, and at 5 m/s on its side.  A grid is the
        # only honest answer to a claim about "every exit".
        #
        # Two families, and neither of them brakes:
        #   HEADING  -- nine headings x three speeds, teleported onto the deck already
        #               pointing off-axis, which is the critic's own instrument;
        #   STEERING -- launched ALONG the log, brought to speed, then a constant steering
        #               input held to the end, which is what a fleeing player actually does.
        #
        # --- r4: NEVER SAMPLE HEADING AT A 10 DEG STEP (level_facts, admitted this pass) ---
        # r3 sampled 0, +-10, +-25, +-45, +-90, reported ``problems: []`` and published a safe
        # band of "10 to 25 deg, 4 to 12 m/s".  Critic pass 3 drove the gaps on r3's own
        # certified cut and every one of +-5, -30, +15 and +25-at-2-and-16 rolled the car onto
        # its roof: at 8 m/s EVERY off-axis heading from -30 to +25 failed except 0 itself.
        # The clean sheet was an artefact of the step, and the gate's exclusion list was
        # exactly the four cells the band named -- so the gate could not see its own failure.
        #
        # r4 steps the heading axis at 5 deg from 0 to +-45 and runs EVERY heading at five
        # speeds from 2 to 16 m/s -- a full 19 x 5 grid, not a grid with the speeds the last
        # revision happened to drive -- and the exclusion list is GONE: every cell is gated.
        HEADING_STEP_DEG = 5.0
        HEADING_MAX_DEG = 45.0
        SPEEDS_MS = (2.0, 4.0, 8.0, 12.0, 16.0)
        offsets = sorted(
            {
                round(HEADING_STEP_DEG * k, 1)
                for k in range(
                    -int(HEADING_MAX_DEG / HEADING_STEP_DEG),
                    int(HEADING_MAX_DEG / HEADING_STEP_DEG) + 1,
                )
            }
        )
        grid: list[dict[str, Any]] = []
        for off in offsets:
            for target in SPEEDS_MS:
                grid.append(
                    _drive_grid(
                        f"heading_{off:+.0f}deg_{target:.0f}ms",
                        -18.0,
                        (along_heading + off) % 360.0,
                        target,
                    )
                )
        # square INTO each wall, both ways, at three speeds: the hardest impact the deck can
        # be given, which with a 1.20 m wall is the case that decides whether the wall holds
        for off in (90.0, -90.0):
            for target in (4.0, 8.0, 12.0):
                grid.append(
                    _drive_grid(
                        f"heading_{off:+.0f}deg_{target:.0f}ms",
                        -18.0,
                        (along_heading + off) % 360.0,
                        target,
                    )
                )
        for steer in (0.35, -0.35, 0.70, -0.70):
            for target in (8.0, 12.0):
                grid.append(
                    _drive_grid(
                        f"steer_{steer:+.2f}_{target:.0f}ms",
                        -18.0,
                        along_heading,
                        target,
                        steer=steer,
                    )
                )
        # park the light car far away first, or the heavy one is teleported onto it
        s.teleport(VEH, _bench_point(geom["toe_x"] - 40.0, -40.0), 0.0)
        s.control(VEH, throttle=0.0, brake=0.0, parkingbrake=1.0, steering=0.0)
        s.step(30)
        # the heavier class (critic pass 2, N8): the drift, the band r3 published, and square
        # into the wall -- a pickup's higher centre of mass is the second opinion on 1.20 m.
        #
        # r6: critic pass 5 drove the truck at +60, +75 and +90 and THREE OF THE FOUR never
        # moved, because the harness stood the body 1.0-1.2 m off the centreline.  Its
        # summary is exact: "until the placement is centred, the round has no measurement of
        # a pickup meeting the wall at speed at any heading past 25 deg."  With the body
        # centred, the steep half of the heavy class is driven for the first time: +-45,
        # +-60, +-75 and +-90 join the six r5 drove.
        heavy_offsets = (0.0, 5.0, -5.0, 25.0, -25.0, 45.0, -45.0, 60.0, -60.0, 75.0, -75.0)
        for off in (*heavy_offsets, 90.0, -90.0):
            grid.append(
                _drive_grid(
                    f"heavy_heading_{off:+.0f}deg_8ms",
                    -18.0,
                    (along_heading + off) % 360.0,
                    8.0,
                    model=HEAVY,
                )
            )
        s.report["bench_exit_grid"] = grid
        rolled = [g for g in grid if g["rolled_past_90"]]
        headings = [g for g in grid if g["probe"].startswith("heading_")]
        s.report["bench_exit_grid_summary"] = {
            "cells": len(grid),
            "heading_step_deg": HEADING_STEP_DEG,
            "heading_range_deg": [-HEADING_MAX_DEG, HEADING_MAX_DEG],
            "headings_sampled": [*offsets, -90.0, 90.0],
            "speeds_ms": sorted({g["target_v"] for g in headings}),
            "cells_per_heading_and_speed": 1,
            "rolled_past_90": [g["probe"] for g in rolled],
            "worst_min_up_z": min(g["min_up_z"] for g in grid),
            "worst_cell": min(grid, key=lambda g: g["min_up_z"])["probe"],
            "came_to_rest": sum(1 for g in grid if g["came_to_rest"]),
            "upright_at_the_last_sample": sum(1 for g in grid if g["upright"]),
            "brake_applied": "never, in any cell",
            # what the wall is FOR: the count of cells that never got over a long edge
            "left_over_a_long_edge": [g["probe"] for g in grid if g["left_over_a_long_edge"]],
            # r6, C6-1: a held cell is not contained by anything -- it is excluded from the
            # tally and listed instead, so this count is cells that were actually driven
            "contained_cells": sum(1 for g in grid if g["counts_toward_containment"]),
            "contained_cells_counts": "cells that LAUNCHED and did not leave over a long edge",
            "cells_not_over_a_long_edge_including_held": sum(
                1 for g in grid if g["contained_by_the_bolster"]
            ),
            "widest_y_local_reached": round(max(g["widest_y_local_on_the_deck"] for g in grid), 3),
            "widest_y_local_reached_is_the": (
                "REFERENCE point's widest excursion -- NOT a clearance against "
                "deck_flat_half_m, because the body's centre is up to 1.17 m from the "
                "reference (critic pass 5, C6-1)"
            ),
            "widest_body_outboard_reached_m": round(
                max(g["widest_body_outboard_on_the_deck_m"] for g in grid), 3
            ),
            "widest_body_outboard_cell": max(
                grid, key=lambda g: g["widest_body_outboard_on_the_deck_m"]
            )["probe"],
            "deck_flat_half_m": geom["deck_flat_half"],
            "wall_height_m": geom["arris_h"],
            "wall_crest_half_width_m": geom["deck_ridge_half"],
            "windows_in_the_wall": "none",
            "excluded_cells": "none -- r5 gates every cell (critic pass 3, C5-1)",
            # r5: what the launch bar itself found, published rather than assumed
            "cells_that_moved": sum(1 for g in grid if g["moved"]),
            "cells_that_met_the_treatment": sum(1 for g in grid if g["met_the_treatment"]),
            # --- r6, C6-1: the placement, published per model and per cell ----------------
            "placement_point": "the BODY CENTRE on the deck centreline, read from the "
            "node cloud at the pose and corrected before the car is released",
            "cells_placed_by_the_body_centre": sum(
                1 for g in grid if g["placement_point"].startswith("the BODY CENTRE on")
            ),
            "worst_body_centre_residual_m": round(
                max(
                    abs(g["body_centre_y_local_at_launch"] or 0.0)
                    for g in grid
                    if g["body_centre_y_local_at_launch"] is not None
                ),
                4,
            ),
            "worst_body_centre_offset_r5_would_have_placed_m": round(
                max(
                    abs(g["body_centre_y_local_if_r5_had_placed_it"] or 0.0)
                    for g in grid
                    if g["body_centre_y_local_if_r5_had_placed_it"] is not None
                ),
                4,
            ),
            "body_centre_offset_by_model": {
                model: sorted(
                    {
                        round(float(g["body_centre_offset_from_the_reference_m"]), 3)
                        for g in grid
                        if g["model"] == model
                        and g["body_centre_offset_from_the_reference_m"] is not None
                    }
                )
                for model in sorted({g["model"] for g in grid})
            },
            "body_box_in_vehicle_frame_by_model": {
                model: next(
                    (g["body_box_in_vehicle_frame_m"] for g in grid if g["model"] == model), None
                )
                for model in sorted({g["model"] for g in grid})
            },
            "body_centre_in_vehicle_frame_by_model": {
                model: next(
                    (g["body_centre_in_vehicle_frame_m"] for g in grid if g["model"] == model),
                    None,
                )
                for model in sorted({g["model"] for g in grid})
            },
            # a held cell is its OWN outcome now: reported, and out of the containment tally
            "cells_held_at_launch": [g["probe"] for g in grid if g["held_at_launch"]],
            "cells_wedged_at_launch": [g["probe"] for g in grid if g["wedged_at_launch"]],
            "cells_beached_on_the_wall_at_launch": [
                g["probe"] for g in grid if g["beached_on_the_wall_at_launch"]
            ],
            "cells_with_a_wheel_off_the_ground_at_launch": [
                g["probe"] for g in grid if g["wheels_off_the_ground_at_launch"]
            ],
            "body_reach_reads_that_failed": [
                g["probe"] for g in grid if g["body_across_reach_read_by"] != "node cloud"
            ],
            "widest_body_reach_m": max(g["body_across_reach_m"] for g in grid),
            "vehicle_boxes": s.report.get("vehicle_boxes", {}),
            "wedge_slack_m": GRID_WEDGE_SLACK_M,
            "cells_that_reached_target_speed": sum(1 for g in grid if g["reached_target_speed"]),
            "cells_that_travelled_4m": sum(1 for g in grid if g["travelled_4m"]),
            "cells_that_measured_nothing": [g["probe"] for g in grid if not g["launched"]],
            # --- r6, N1: the outcome the section ships and never counted -------------------
            "at_rest_still_on_the_log": sum(1 for g in grid if g["at_rest_still_on_the_log"]),
            "at_rest_still_on_the_log_cells": [
                g["probe"] for g in grid if g["at_rest_still_on_the_log"]
            ],
            "on_the_log_bar_m": GRID_ON_THE_LOG_M,
            "median_path_of_the_cells_still_on_the_log_m": (
                round(
                    statistics.median(
                        [g["path_length_m"] for g in grid if g["at_rest_still_on_the_log"]]
                    ),
                    2,
                )
                if any(g["at_rest_still_on_the_log"] for g in grid)
                else None
            ),
            # --- r6, N2: "rest" is the budget running out for a car idling in D ------------
            "cells_where_rest_is_the_budget_running_out": sum(
                1 for g in grid if g["rest_is_where_the_budget_ran_out"]
            ),
            "median_final_speed_of_those_cells_ms": (
                round(
                    statistics.median(
                        [g["rest_speed"] for g in grid if g["rest_is_where_the_budget_ran_out"]]
                    ),
                    3,
                )
                if any(g["rest_is_where_the_budget_ran_out"] for g in grid)
                else None
            ),
            "max_final_speed_of_those_cells_ms": (
                max(
                    (g["rest_speed"] for g in grid if g["rest_is_where_the_budget_ran_out"]),
                    default=None,
                )
            ),
            "no_stopping_input_is_applied": (
                "by design: r5 proved that holding the foot brake makes an automatic select "
                "reverse and drive away (C5-3), so the grid applies nothing -- and a car "
                "coasting in D then creeps rather than stopping.  Both halves are published."
            ),
            # --- r6, N3: the exit-drop bounds MEASURED on the grid, never gated on it -------
            "c5_3_bounds_measured_on_the_grid_not_gated": {
                "travel_bound_m": EXIT_TRAVEL_BOUND_M,
                "speed_bound_over_target_ms": EXIT_SPEED_BOUND_OVER_TARGET_MS,
                "cells_that_left_the_deck": sum(
                    1 for g in grid if g["travel_after_leaving_the_deck_m"] is not None
                ),
                "cells_over_the_travel_bound": sum(
                    1
                    for g in grid
                    if (g["travel_after_leaving_the_deck_m"] or 0.0) > EXIT_TRAVEL_BOUND_M
                ),
                "worst_travel_m": max(
                    (g["travel_after_leaving_the_deck_m"] or 0.0 for g in grid), default=0.0
                ),
                "cells_over_the_speed_bound": sum(
                    1
                    for g in grid
                    if (g["max_v_after_leaving_the_deck"] or 0.0)
                    > g["target_v"] + EXIT_SPEED_BOUND_OVER_TARGET_MS
                ),
                "why_not_gated": (
                    "the five exit drops are aimed departures with a stated landing; a grid "
                    "cell that leaves over the DESIGNED crown is meant to run out across the "
                    "meadow, so bounding it would gate the feature rather than a defect.  "
                    "The asymmetry is stated with its own number instead of implied away."
                ),
            },
        }
        # EVERY CELL IS GATED.  r3 excluded exactly the four heading cells its own published
        # band named, so its clean sheet was a property of the exclusion list rather than of
        # the map; at a 5 deg step its certified boot would have failed its own gate.  There
        # is no band any more: with a continuous 1.20 m wall on both flanks a departure over
        # a long edge does not happen at all, so a rollover anywhere in the grid is a defect.
        # ... but FIRST, every cell must have been a drive.  ``contained_by_the_bolster`` is
        # true of a car that never moved, so without this the containment sheet could be
        # clean because the stimulus was never applied (B3 r10/r11's law, and the same
        # family as r3's exclusion list: a gate that cannot see its own blind spot).
        #
        # r6: and "it was held against the wall" is NO LONGER an answer to that.  r5's bar
        # read ``launched = wedged or (path >= 1.0 and ...)`` -- a cell counted as a measured
        # departure either because it travelled or because it did not -- and on the critic's
        # boot that passed three heavy cells at 4-6 cm.  A hold is now its own published
        # outcome, out of the containment tally, and it fails this gate like any other cell
        # that measured nothing.  With the body centred there is no geometry that forces one.
        for cell in grid:
            s.check(
                cell["launched"],
                f"grid cell {cell['probe']} measured nothing -- it travelled "
                f"{cell['path_length_m']} m, reached {cell['max_v']} of {cell['target_v']} m/s, "
                f"its body ({cell['body_across_reach_read_by']}) reached "
                f"{cell['body_outboard_extent_m']} m outboard against a "
                f"{geom['deck_flat_half']} m flat deck with "
                f"{cell['wheels_on_the_ground_at_launch']} wheels on the ground; it was placed "
                f"by {cell['placement_point']} with its body centre at "
                f"{cell['body_centre_y_local_at_launch']} m "
                f"(r5's placement would have put it at "
                f"{cell['body_centre_y_local_if_r5_had_placed_it']} m), and "
                f"held_at_launch={cell['held_at_launch']}",
                {k: v for k, v in cell.items() if k != "samples"},
            )
        # the placement itself is gated, because a correction nobody checks is a comment.
        # 0.05 m is a tenth of the 0.45 m of spare room the critic measured at the worst pose.
        for cell in grid:
            residual = cell["body_centre_y_local_at_launch"]
            s.check(
                residual is not None and abs(residual) <= 0.05,
                f"grid cell {cell['probe']} was not placed on the centreline: its BODY centre "
                f"sits at y_local {residual} after the correction "
                f"(reference placed at {cell['placed_reference_at_y_local']}, "
                f"body offset {cell['body_centre_offset_from_the_reference_m']})",
                {k: v for k, v in cell.items() if k != "samples"},
            )
        for cell in grid:
            s.check(
                not cell["rolled_past_90"],
                f"the car rolled past 90 deg in grid cell {cell['probe']}",
                {k: v for k, v in cell.items() if k != "samples"},
            )
        # ... and the containment claim itself, on EVERY cell: the wall has no window, so no
        # heading, no speed, no steering input and neither vehicle class may reach a long
        # edge.  A cell that leaves over the crown has used the designed exit and passes.
        for cell in grid:
            s.check(
                cell["contained_by_the_bolster"],
                f"a departure left over a long edge in grid cell {cell['probe']}",
                {k: v for k, v in cell.items() if k != "samples"},
            )
        # r6, C6-1: and the containment HEADLINE may never include a cell that was held.
        # This is the arithmetic the critic's three 4 cm cells would have walked past,
        # asserted rather than left to a reader -- and it is what stops a future edit
        # quietly re-introducing the ``wedged => launched`` disjunct.
        s.check(
            not [g for g in grid if g["held_at_launch"] and g["counts_toward_containment"]],
            "a cell that was HELD at launch is being counted toward containment",
            [g["probe"] for g in grid if g["held_at_launch"] and g["counts_toward_containment"]],
        )
        s.check(
            s.report["bench_exit_grid_summary"]["contained_cells"]
            <= sum(1 for g in grid if g["launched"]),
            "the containment tally is larger than the number of cells that launched",
            s.report["bench_exit_grid_summary"],
        )

        # --- 4c. the west crown is TWO-WAY, and this measures it rather than assuming it ---
        # A gradient cannot make an exit one-way: a car arrives with MOMENTUM (an etk800
        # reaches the foot at 8.53 m/s off a 14 m run-up, which is 36 J/kg against a 33 J/kg
        # hill), and the two break faces that WOULD have stopped it were refuted by the
        # drives going the other way.  So the log has two ways in, it is declared in
        # deviation 7, and the check asserts the DECLARED behaviour so that a later round
        # cannot quietly change it in either direction without this failing.
        climb_probes = [
            _climb("crown_climb_etk800_wot", 1.0),
            _climb("crown_climb_etk800_45pct", 0.45),
            _climb("crown_climb_pickup_wot", 1.0, model=HEAVY),
        ]
        s.report["crown_climb"] = climb_probes
        # r4: two-way FOR A ROAD CAR, which is what deviation 7 actually claims and what the
        # two etk800 legs actually show.  r3 asserted it of all three probes and only passed
        # because its predicate read a transient maximum: the pickup does NOT climb it (r3's
        # own BENCH comment says so -- "it stalled 1.3 m up and slid back"), so asserting
        # ``all`` was asserting something the round had already measured to be false.
        road_car = [p for p in climb_probes if p["model"] == VEH]
        heavy = [p for p in climb_probes if p["model"] == HEAVY]
        s.report["west_crown_is_two_way"] = all(p["reached_the_plateau"] for p in road_car)
        s.report["west_crown_climbed_by_the_heavy_class"] = all(
            p["reached_the_plateau"] for p in heavy
        )
        s.report["crown_climb_predicate"] = (
            "conjunction ANYWHERE on the trajectory, evaluated every tick: high enough AND "
            "over the deck AND past the crown's taper, all three at the same sample (r5). "
            "r3's transient max of one variable and r4's final-pose conjunction are both "
            "published beside it -- they are wrong in opposite directions and boot 1 showed it."
        )
        s.check(
            s.report["west_crown_is_two_way"],
            "the west crown stopped being the two-way ramp deviation 7 declares",
            [{k: v for k, v in p.items() if k != "samples"} for p in road_car],
        )
        # and the finding r3's predicate hid: where the heavy class actually ends up.  It is
        # not a gate -- the crown is not required to admit a pickup -- but it must be in the
        # evidence, because "a heavy vehicle sitting motionless at wide-open throttle on the
        # shipped west end" is a live fact about the map and the round published its opposite.
        s.report["crown_climb_heavy_final_pose"] = [
            {
                k: v
                for k, v in p.items()
                if k
                in (
                    "probe",
                    "final_x_local",
                    "final_y_local",
                    "final_z_local",
                    "final_v",
                    "reached_the_plateau",
                    "reached_the_plateau_by_r3s_transient_max_rule",
                )
            }
            for p in heavy
        ]

        # --- 5. an ai span drive on the trail ----------------------------------------
        # start well OUT on the trail: boot 1's span, launched at the trailhead, spent all
        # 48 samples on the ring and the track (r 169-314) and never reached the trail
        trail_at = tm.trail_samples(1.0)[320]
        s.teleport(VEH, (float(trail_at[0]), float(trail_at[1])), 150.0)
        s.control(VEH, throttle=0.0, brake=0.0, parkingbrake=0.0)
        s.step(20)
        s.lua(
            f"local v = scenetree.findObject({VEH!r}); "
            'v:queueLuaCommand(\'ai.setSpeedMode("limit") ai.setSpeed(11) ai.setMode("span")\'); '
            "return jsonEncode({ok = true})"
        )
        span = []
        for _ in range(90):
            for _ in range(30):
                s.step(STEP)
            probe = s.probe(VEH)
            road = s.road_distance(probe["x"], probe["y"], probe["z"])
            span.append(
                {
                    "x": round(probe["x"], 2),
                    "y": round(probe["y"], 2),
                    "z": round(probe["z"], 3),
                    "r": round(probe["r"], 1),
                    "v": round(probe["hspeed"], 2),
                    "road_d": round(float(road["d"]), 3),
                    "road_a": road.get("a"),
                }
            )
        distances = [row["road_d"] for row in span]
        moved = [
            math.dist((span[i]["x"], span[i]["y"]), (span[i + 1]["x"], span[i + 1]["y"]))
            for i in range(len(span) - 1)
        ]
        grades_driven = [
            abs(span[i + 1]["z"] - span[i]["z"]) / moved[i]
            for i in range(len(moved))
            if moved[i] > 2.0
        ]
        s.report["span_drive"] = {
            "samples": len(span),
            "road_d_max": round(max(distances), 3),
            "road_d_median": round(float(np.median(distances)), 3),
            "road_d_over_4m": int(sum(1 for d in distances if d > 4.0)),
            "distance_m": round(sum(moved), 1),
            "r_min": round(min(row["r"] for row in span), 1),
            "r_max": round(max(row["r"] for row in span), 1),
            "driven_grade_max_pct": round(max(grades_driven) * 100.0, 2) if grades_driven else None,
            "rows": span,
        }
        s.lua(
            f"local v = scenetree.findObject({VEH!r}); "
            "v:queueLuaCommand('ai.setMode(\"stop\")'); return jsonEncode({ok = true})"
        )
        s.step(60)

        # --- 6. the frames ------------------------------------------------------------
        cameras = {row["name"]: row for row in ps.design_layout()["cameras"]}

        def _set_clock(value: float) -> dict[str, Any]:
            s.lua(
                "local tod = core_environment.getTimeOfDay(); "
                f"tod.time = {value}; core_environment.setTimeOfDay(tod); "
                "return jsonEncode({ok = true})"
            )
            s.step(40)
            return s.lua(
                "local tod = core_environment.getTimeOfDay(); local sky = nil; "
                "for _, id in ipairs(scenetree.findClassObjects('ScatterSky')) do "
                "sky = scenetree.findObject(id) end "
                "local lit = 0; for _, id in ipairs(scenetree.findClassObjects('PointLight')) do "
                "local o = scenetree.findObject(id); if o and tostring(o:getField('isEnabled', 0))"
                " ~= '0' then lit = lit + 1 end end "
                "return jsonEncode({clock = tod.time, lights_enabled = lit, "
                "elevation = tostring(sky and sky.elevation or ''), "
                "azimuth = tostring(sky and sky.azimuth or '')})"
            )

        s.teleport(VEH, _bench_point(geom["half"] + 40.0, 40.0), 210.0)
        s.step(30)
        day = _set_clock(0.30)
        s.report["day_clock"] = day
        deck_z = report["deck_z_mean"]
        day_frames = {
            "S8_trail_switchback": (
                tuple(float(v) for v in cameras["S8_trail_switchback"]["position"]),
                tuple(float(v) for v in cameras["S8_trail_switchback"]["look_at"]),
                "S8: the decal stack, the split-rail fence, scree, the hearth 600 m below",
            ),
            "B4_bench_approach": (
                (
                    *_bench_point(geom["toe_x"] - 13.0, 5.0),
                    float(terrain.surface_z(*_bench_point(geom["toe_x"] - 13.0, 5.0))) + 2.0,
                ),
                (*_bench_point(geom["join_x"] + 4.0), deck_z + 0.5),
                "B4: a driver's eye at the wedge's toe, looking up the ramp onto the deck",
            ),
            "B4_bench_deck": (
                (*_bench_point(geom["half"] - 16.0), deck_z + 1.4),
                (*_bench_point(geom["toe_x"] + 6.0), deck_z - 2.0),
                "B4: standing on the deck, looking down its 60.8 m plateau and over the wedge",
            ),
            # r1 shipped no view of the log FROM THE SIDE -- the only view in which its
            # log-ness, the bark shoulder, the flank drop and the crown all read.  Two now:
            # a broadside from the meadow at eye height, and a low three-quarter at the crown.
            "B4_bench_broadside": (
                (
                    *_bench_point(-24.0, -30.0),
                    float(terrain.surface_z(*_bench_point(-24.0, -30.0))) + 6.0,
                ),
                (*_bench_point(26.0, 0.0), deck_z - 1.0),
                "B4: the log's whole flank from the meadow -- wedge, plateau, west descent",
            ),
            "B4_bench_flank": (
                (
                    *_bench_point(4.0, -14.0),
                    float(terrain.surface_z(*_bench_point(4.0, -14.0))) + 2.8,
                ),
                (*_bench_point(8.0, 0.0), deck_z - 1.5),
                "B4: the bark belly and the hewn deck line at 14 m, the flank drop in section",
            ),
            "B4_bench_crown": (
                (
                    *_bench_point(geom["break_x"] + 13.0, -7.5),
                    float(terrain.surface_z(*_bench_point(geom["break_x"] + 13.0, -7.5))) + 3.2,
                ),
                (*_bench_point(geom["break_x"] - 5.0, 0.0), deck_z - 1.6),
                "B4: the west descent from below -- it runs out into the grass, no lip",
            ),
            # r4: critic pass 3's taste note, taken.  "At full frame the snout reads as a grey
            # wedge with regular vertical ribbing ... zoomed it is fine ... it is a camera-
            # distance problem, not a mesh problem.  Shoot it from 25 m."  The r3 pose is kept
            # UNCHANGED above so the two revisions' crown frames stay comparable, and this is
            # the same subject from the distance the critic asked for.
            "B4_bench_crown_25m": (
                (
                    *_bench_point(geom["break_x"] + 22.0, -12.0),
                    float(terrain.surface_z(*_bench_point(geom["break_x"] + 22.0, -12.0))) + 4.2,
                ),
                (*_bench_point(geom["break_x"] - 9.0, 0.0), deck_z - 1.2),
                "B4: the west crown at 25 m -- the whole taper, not the ribbing",
            ),
            # r4: the new geometry, from the one place it decides the element -- a low eye ON
            # the deck looking down the trough between the two containment walls.  This is
            # what a player sees when the wall turns them back instead of letting them off.
            "B4_bench_bolster": (
                (
                    *_bench_point(geom["crown_x"] - 8.0, 2.2),
                    deck_z + 1.15,
                ),
                (*_bench_point(geom["join_x"] + 4.0, -1.0), deck_z + 0.35),
                "B4: down the trough -- 6.0 m of hewn deck between two 1.20 m standing bark walls",
            ),
            "B4_trail_fence": _fence_camera(place),
            # r3: a low eye ON the trail so a wheel path either reads or does not.
            "B4_trail_ruts": _rut_camera(),
            # r4: the wall from the meadow, three-quarter along the OUTER flank at 13 m: the
            # standing rind above the sawn line, its shadow on the hewn deck, and the round
            # belly below -- the frame that says whether a 1.20 m wall reads as the log's
            # own bark left standing or as a fence bolted onto a plank.
            "B4_bench_wall": (
                (
                    *_bench_point(8.0, -inner_sign * 13.0),
                    float(terrain.surface_z(*_bench_point(8.0, -inner_sign * 13.0))) + 2.6,
                ),
                (*_bench_point(-14.0, -inner_sign * 3.3), deck_z + 0.9),
                "B4: the outer containment wall from the meadow -- bark rind, sawn line, belly",
            ),
            "AERIAL_300m": (
                tuple(float(v) for v in cameras["AERIAL_300m"]["position"]),
                tuple(float(v) for v in cameras["AERIAL_300m"]["look_at"]),
                "AERIAL: the layout check against layout.json",
            ),
        }
        # --- r5: THE DISTANCE LADDER --------------------------------------------------
        # Critic pass 3's player judgement is a statement about DISTANCE -- "at 60-130 m it
        # flattens into pale timber slabs" -- and r3 answered it with one frame per subject,
        # so nobody could see where the illusion goes.  B1 r14 paid for the same lesson on a
        # texture ("measure at several distances; a graft that wins at authoring scale can
        # read as a brick wall in the mid field") and the same rule applies to a frame.
        #
        # Two subjects, four ranges each, one bearing per subject, everything else held: the
        # eye walks straight back along the line from the aim point, and the height rises
        # with range so the subject keeps the same place in the frame.

        def _frame_subject_rays(
            name: str, eye: tuple[float, float, float], aim: tuple[float, float, float]
        ) -> dict[str, Any]:
            """Is the bench log actually in this frame's centre box?  Cast the box and see.

            The camera is reconstructed exactly as ``Session.shot`` sets it -- free camera,
            VERTICAL FOV ``CAMERA_FOV_DEG``, 16:9 -- and a fan of rays is fired through the
            same centre box ``frame_ladder`` measures in (0.30..0.70 of the frame, i.e.
            +-0.4 in normalised device coordinates).  Every hit is converted into the LOG's
            own frame and scored against the log's own footprint, so "contains its subject"
            is a geometric fact about the shipped level rather than a judgement about a PNG.
            One lua call for the whole fan.
            """

            ox, oy = origin
            ex, ey, ez = (float(v) for v in eye)
            ax, ay, az = (float(v) for v in aim)
            fx, fy, fz = ax - ex, ay - ey, az - ez
            flen = math.sqrt(fx * fx + fy * fy + fz * fz) or 1.0
            fx, fy, fz = fx / flen, fy / flen, fz / flen
            # right = forward x world_up, then up = right x forward (shot() uses world +z up)
            rx, ry, rz = fy * 1.0 - fz * 0.0, fz * 0.0 - fx * 1.0, 0.0
            rlen = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
            rx, ry, rz = rx / rlen, ry / rlen, rz / rlen
            ux, uy, uz = ry * fz - rz * fy, rz * fx - rx * fz, rx * fy - ry * fx
            ty = math.tan(math.radians(scaffold.CAMERA_FOV_DEG) / 2.0)
            tx = ty * (scaffold.SHOT_SIZE[0] / scaffold.SHOT_SIZE[1])
            steps = [(-0.4 + 0.1 * k) for k in range(9)]
            dirs = []
            centre_row: list[int] = []
            centre_ray = 0
            for v in steps:
                for u in steps:
                    dx = fx + u * tx * rx + v * ty * ux
                    dy = fy + u * tx * ry + v * ty * uy
                    dz = fz + u * tx * rz + v * ty * uz
                    dlen = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
                    if abs(v) < 1e-9:
                        centre_row.append(len(dirs))
                        if abs(u) < 1e-9:
                            centre_ray = len(dirs)
                    dirs.append((dx / dlen, dy / dlen, dz / dlen))
            far = flen * 3.0 + 60.0
            fan = ", ".join(f"{{{d[0]:.9f}, {d[1]:.9f}, {d[2]:.9f}}}" for d in dirs)
            # one string, not a table: a nil anywhere in a lua array leaves a HOLE, and a
            # hole would shift every subsequent ray onto the wrong direction on the way back
            answer = s.lua(
                f"local o = vec3({ex}, {ey}, {ez}) local dirs = {{{fan}}} local out = {{}} "
                "for i = 1, #dirs do local d = dirs[i] "
                f"local hit = castRayStatic(o, vec3(d[1], d[2], d[3]), {far}) "
                "out[#out + 1] = tostring(hit or -1) end "
                'return jsonEncode({d = table.concat(out, ",")})'
            )
            distances = [float(v) for v in str(answer.get("d", "")).split(",") if v]
            if len(distances) != len(dirs):
                return {
                    "frame": name.lower(),
                    "eye": list(eye),
                    "aim": list(aim),
                    "rays": len(dirs),
                    "read_by": "FAILED",
                    "rays_that_hit_something": 0,
                    "rays_on_the_log": 0,
                    "fraction_on_the_log": 0.0,
                    "centre_row_rays": len(centre_row),
                    "centre_row_on_the_log": 0,
                    "centre_row_fraction": 0.0,
                    "centre_ray_hits_the_log": False,
                    "nearest_hit_that_is_NOT_the_log_m": None,
                    "nearest_hit_m": None,
                    "how": f"the ray fan returned {len(distances)} of {len(dirs)} distances",
                    "hits": [],
                }
            on_log = 0
            hits: list[dict[str, float]] = []
            nearest = None
            log_flags: list[bool] = []
            for (dx, dy, dz), distance in zip(dirs, distances, strict=False):
                if not distance or distance >= far - 1.0:
                    log_flags.append(False)
                    continue
                hx, hy, hz = ex + dx * distance, ey + dy * distance, ez + dz * distance
                local_x = (hx - ox) * along[0] + (hy - oy) * along[1]
                local_y = (hx - ox) * across[0] + (hy - oy) * across[1]
                above = hz - float(terrain.surface_z(hx, hy))
                is_log = bool(
                    geom["toe_x"] - 2.0 <= local_x <= geom["break_x"] + 1.0
                    and abs(local_y) <= 5.0
                    and above >= 0.6
                )
                log_flags.append(is_log)
                on_log += 1 if is_log else 0
                if not is_log and (nearest is None or distance < nearest):
                    nearest = distance
                hits.append(
                    {
                        "d": round(distance, 2),
                        "x_local": round(local_x, 2),
                        "y_local": round(local_y, 2),
                        "above_terrain_m": round(above, 2),
                        "log": is_log,
                    }
                )
            row_hits = sum(1 for i in centre_row if i < len(log_flags) and log_flags[i])
            return {
                "frame": name.lower(),
                "eye": list(eye),
                "aim": list(aim),
                "distance_to_the_aim_point_m": round(flen, 2),
                "rays": len(dirs),
                "rays_that_hit_something": len(hits),
                "rays_on_the_log": on_log,
                # the WHOLE box: published, never gated.  A far rung's box is mostly sky and
                # meadow by geometry -- at 100 m the box spans +-41 m of a 7 m subject -- so
                # a bar on it would fail a correct frame and reward a badly framed near one.
                "fraction_on_the_log": round(on_log / max(len(dirs), 1), 4),
                # the CENTRE ROW and the CENTRE RAY: these are what the camera is aimed at,
                # and they are what a photograph of B3's forest fails.  Gated.
                "centre_row_rays": len(centre_row),
                "centre_row_on_the_log": row_hits,
                "centre_row_fraction": round(row_hits / max(len(centre_row), 1), 4),
                "centre_ray_hits_the_log": bool(
                    centre_ray < len(log_flags) and log_flags[centre_ray]
                ),
                "nearest_hit_that_is_NOT_the_log_m": round(nearest, 2) if nearest else None,
                "nearest_hit_m": round(min((h["d"] for h in hits), default=0.0), 2),
                "box_fraction_of_the_frame": [0.30, 0.30, 0.70, 0.70],
                "fov_vertical_deg": scaffold.CAMERA_FOV_DEG,
                "read_by": "ray fan",
                "how": (
                    "a 9x9 fan through the frame's own centre box, hits converted into the "
                    "log's frame and scored against the log's own footprint (x from toe-2 to "
                    "break+1, |y| <= 5.0, and 0.6 m clear of the terrain beneath the hit)"
                ),
                "hits": hits,
            }

        #
        # --- r6, C6-4: A FRAME IN A LADDER MUST CONTAIN ITS SUBJECT -----------------------
        #
        # r5 did not choose these stations, it extrapolated them, and nothing looked at what
        # was there.  Critic pass 5 opened all eight and found `b4_bench_broadside_100m` is a
        # photograph of the inside of B3's forest -- no bench log in it at all -- and it had
        # been PRICED as the 100 m rung of a ladder about the log.  Read off the shipped cut's
        # own 56,762 occluding forest instances (`b4/r6/instruments/frame_station_r6.py`)
        # THREE of the eight rungs stand in or against the tree line at bearing -1.0 / -0.55:
        # broadside at 60 m (eye 4.55 m from a trunk) and at 100 m (2.13 m, four trunks across
        # the sight line), and crown at 100 m (eye INSIDE a trunk, -0.20 m).
        #
        # AND r5's rung LABELS were wrong for one of the two subjects.  Its eye walks out as
        # (aim_x + m*0.45, bearing_y * m * 0.9), whose length is m * hypot(0.45, 0.9*bearing)
        # -- 1.006 m at bearing -1.0, so the broadside rungs really were at 10 / 20 / 60 /
        # 100 m, but only 0.669 m at bearing -0.55, so the crown's "100 m" rung stood at
        # 66.9 m and its "60 m" rung at 40.1 m.  A distance ladder whose rungs are not at
        # their own distances cannot answer a question about distance.
        #
        # Three repairs, and the last one is the one that generalises:
        #   (a) the eye is placed at exactly ``metres`` from the aim point on a bearing
        #       measured from the log's own +x axis, so every rung is AT its label;
        #   (b) that bearing is chosen off the cut by a published rule -- stay on r5's flank,
        #       keep |sin theta| >= 0.35 so the subject stays broad, keep 10 m of open ground
        #       at every eye, then take the MOST BROADSIDE station that survives.  It lands
        #       on -155 deg for the crown and -140 deg for the broadside, worst eye clearance
        #       12.75 / 13.41 m and NOTHING on any of the eight sight lines.  The +y flank is
        #       open meadow to 70 m and was deliberately NOT taken: the defect is a station,
        #       not a side, and the frame critic pass 5 praised is on this one.
        #   (c) every ladder frame is VERIFIED LIVE before it is priced: a fan of rays through
        #       the frame's own centre box, hits converted into the log's frame, and the
        #       fraction that land on the log published beside the frame.  A reading of a
        #       frame that does not contain its subject is a reading of something else.
        LADDER_THETA_DEG = {"crown": -155.0, "broadside": -140.0}
        ladder_frames: dict[str, tuple[Any, Any, str]] = {}
        for subject, (aim_x, aim_y, aim_dz) in {
            "crown": (geom["break_x"] - 5.0, 0.0, -1.6),
            "broadside": (0.0, 0.0, -1.0),
        }.items():
            theta = math.radians(LADDER_THETA_DEG[subject])
            for metres in (10.0, 20.0, 60.0, 100.0):
                eye_x = aim_x + metres * math.cos(theta)
                eye_y = metres * math.sin(theta)
                ground = float(terrain.surface_z(*_bench_point(eye_x, eye_y)))
                ladder_frames[f"B4_bench_{subject}_{int(metres):03d}m"] = (
                    (*_bench_point(eye_x, eye_y), ground + 2.0 + 0.05 * metres),
                    (*_bench_point(aim_x, aim_y), deck_z + aim_dz),
                    f"B4: the {subject} at {metres:.0f} m -- the distance ladder critic pass 3 "
                    f"asked the question on, station chosen off the cut (r6)",
                )
        day_frames.update(ladder_frames)
        s.report["bench_frame_ladder_stations"] = {
            "theta_deg": LADDER_THETA_DEG,
            "chosen_by": "b4/r6/instruments/frame_station_r6.py, off the shipped cut's forest",
            "rungs_m": [10.0, 20.0, 60.0, 100.0],
            "every_rung_is_at_its_label": True,
            "r5_bearings": {"crown": -0.55, "broadside": -1.0},
            "r5_true_ranges_m": {
                "crown": [6.7, 13.4, 40.1, 66.9],
                "broadside": [10.1, 20.1, 60.4, 100.6],
            },
        }
        # and NOTHING may be parked in the picture.  Two of r5's rungs are photographs of a
        # blue pickup: at 10 m the crown_climb truck fills more than half the centre box.
        for parked, spot in ((VEH, -60.0), (HEAVY, -75.0)):
            s.teleport(parked, _bench_point(geom["toe_x"] - 60.0, spot), 0.0)
            s.control(parked, throttle=0.0, brake=0.0, parkingbrake=1.0, steering=0.0)
        s.step(30)
        s.report["bench_frame_vehicles_parked_at"] = {
            VEH: list(_bench_point(geom["toe_x"] - 60.0, -60.0)),
            HEAVY: list(_bench_point(geom["toe_x"] - 60.0, -75.0)),
            "why": (
                "critic pass 5: two rungs of r5's ladder are pictures of a blue pickup "
                "standing against the crown, not measurements of timber at distance"
            ),
        }
        subject_checks = {
            name: _frame_subject_rays(name, eye, aim)
            for name, (eye, aim, _note) in ladder_frames.items()
        }
        s.report["bench_frame_subject"] = subject_checks
        for name, check in subject_checks.items():
            s.check(
                check["centre_ray_hits_the_log"]
                and check["centre_row_fraction"] >= FRAME_SUBJECT_MIN,
                f"ladder frame {name.lower()} does not contain its subject: its centre ray "
                f"{'hits' if check['centre_ray_hits_the_log'] else 'MISSES'} the bench log and "
                f"{check['centre_row_fraction']:.3f} of its centre row lands on it "
                f"(bar {FRAME_SUBJECT_MIN}); {check['fraction_on_the_log']:.3f} of the whole "
                f"centre box is log, nearest non-log hit at "
                f"{check['nearest_hit_that_is_NOT_the_log_m']} m",
                check,
            )
        for name, (eye, aim, note) in day_frames.items():
            s.shot(name.lower(), eye, aim, note)

        # --- 6b. WHICH WAY DOES renderPriority ORDER? (r3) ----------------------------
        # Study A r2 and r3 both list this as an open unknown ("renderPriority ordering
        # semantics beyond the observed per-map tiers").  It stopped being academic when
        # critic pass 2 reported "sharp, but pale, and still no ruts": B4's own stack put the
        # SURFACE at 8, above the flows (2), the gravel (3), the dust (4), the ruts (5) and
        # the bank erosion (7) -- so if higher draws later, five of eight detail families
        # were painted and buried, and the pale base was all that reached the screen.
        #
        # It can be settled in one boot without a second cut, because renderPriority is a
        # live field: shoot the same trail camera three times, flipping the two records that
        # matter between shots and reading the field back each time.  r3 SHIPS the surface
        # at 1 and the ruts at 12; if that is the wrong way round the flipped frame is the
        # one with the ruts in it, and the law is recorded either way.
        rut_eye, rut_aim, _note = _rut_camera()

        def _set_priority(material: str, value: int) -> int:
            return int(
                s.lua(
                    "local n = 0 "
                    "for _, id in ipairs(scenetree.findClassObjects('DecalRoad')) do "
                    "local o = scenetree.findObject(id) "
                    f"if o and tostring(o:getField('material', 0)) == '{material}' then "
                    f"o:setField('renderPriority', 0, '{value}') o:postApply() n = n + 1 end end "
                    "return jsonEncode({n = n})"
                )["n"]
            )

        def _read_priorities() -> dict[str, list[int]]:
            rows = s.lua(
                "local out = {} "
                "for _, id in ipairs(scenetree.findClassObjects('DecalRoad')) do "
                "local o = scenetree.findObject(id) if o then "
                "local m = tostring(o:getField('material', 0)) "
                "out[m] = out[m] or {} "
                "out[m][#out[m] + 1] = tonumber(o:getField('renderPriority', 0)) end end "
                "return jsonEncode(out)"
            )
            return {k: sorted(set(int(v) for v in vals)) for k, vals in rows.items()}

        # r2's ENTIRE stack, so the flipped state is literally the revision the critic saw
        r2_stack = {
            "m_dirt_variation": 8,
            "m_dirt_flows": 2,
            "m_dirt_gravel": 3,
            "m_dirt_tiretracks": 5,
            "m_bank_erosion": 7,
            "m_mud_cracks": 9,
            "m_puddle_wet": 10,
            "m_track_dust_overlay": 4,
            "m_skid_arc": 5,
            "m_needle_litter": 25,
        }
        ab: dict[str, Any] = {
            "what": (
                "the same trail camera, three states, changing ONLY renderPriority fields; "
                "nothing is re-cut, no geometry moves and no texture changes. State "
                "`r2_order` restores the exact stack critic pass 2 photographed."
            ),
            "convention_from_the_engines_own_authoring": {
                "roadArchitect/decals.lua": (
                    "base drivable road = #layers + 3; every overlay layer = i (1..#layers)"
                ),
                "procTrack.lua L878-882": "tread_marks_clean 4, road_orange_markings 3",
                "reading": "a LOWER renderPriority draws ON TOP",
            },
            "camera": {
                "eye": [round(v, 3) for v in rut_eye],
                "aim": [round(v, 3) for v in rut_aim],
            },
            "states": [],
        }
        for label, stack in (
            ("as_shipped", None),
            ("r2_order", r2_stack),
            ("restored", {k: int(v["renderPriority"]) for k, v in ps.ROAD_STACK.items()}),
        ):
            touched = {}
            if stack is not None:
                for key, value in stack.items():
                    touched[key] = _set_priority(f"{LEVEL_ID}_{key}", value)
                s.step(30)
            shot = s.shot(
                f"b4_ab_priority_{label}",
                rut_eye,
                rut_aim,
                f"B4 renderPriority A/B, state {label}",
            )
            ab["states"].append(
                {
                    "state": label,
                    "records_touched": touched,
                    "priorities": _read_priorities(),
                    "frame": shot.name,
                }
            )
        s.report["render_priority_ab"] = ab

        night = _set_clock(0.50)
        s.report["night_clock"] = night
        s5 = cameras["S5_lantern_night"]
        s.shot(
            "s5_lantern_night",
            tuple(float(v) for v in s5["position"]),
            tuple(float(v) for v in s5["look_at"]),
            "S5: the lantern tripod, its pool and log_north's east fire at clock 0.50",
        )
        s.shot(
            "b4_bench_night",
            (
                *_bench_point(geom["toe_x"] - 26.0, 7.0),
                float(terrain.surface_z(*_bench_point(geom["toe_x"] - 26.0, 7.0))) + 1.6,
            ),
            (*_bench_point(geom["join_x"] + 10.0), deck_z + 1.0),
            "B4: the same bench approach at clock 0.50, for the night control",
        )
        _set_clock(0.30)

        # --- 7. the props' render cost, A/B/A at one camera ---------------------------
        # r4: SKIPPED when HOT_POTATO_B4_PERF_SECONDS is 0.  level_facts: a frame-time
        # measurement is invalid if another worker is on the machine, and critics B1 p11 and
        # B2 p5 ran alongside r4's boot.  A skipped leg is recorded as skipped, with the
        # reason, rather than measured and then declared unattributable (r2, r3).
        if PERF_SECONDS <= 0.0:
            s.report["props_render_cost"] = {
                "skipped": True,
                "reason": (
                    "HOT_POTATO_B4_PERF_SECONDS=0: other build agents were active on the "
                    "machine during this boot, so no frame-time leg was run (level_facts, "
                    "harness law 1).  The whole-level figure stands: 17.37 / 17.09 ms, "
                    "RTF 1.000, measured on an idle machine by the orchestrator."
                ),
                "legs": [],
            }
        else:
            s.lua(PERF_INSTALL)
            perf_eye = (*_bench_point(geom["half"] + 55.0, 26.0), deck_z + 9.0)
            perf_aim = (*_bench_point(geom["toe_x"] + 10.0), deck_z - 1.0)
            s.lua(
                "commands.setFreeCamera(); "
                f"core_camera.setFOV(nil, {scaffold.CAMERA_FOV_DEG}); "
                f"local eye = vec3({perf_eye[0]}, {perf_eye[1]}, {perf_eye[2]}); "
                f"local aim = vec3({perf_aim[0]}, {perf_aim[1]}, {perf_aim[2]}); "
                "local rotation = quatFromDir((aim - eye):normalized(), vec3(0, 0, 1)); "
                "core_camera.setPosRot(0, eye.x, eye.y, eye.z, rotation.x, rotation.y, rotation.z, "
                "rotation.w); return jsonEncode({ok = true})"
            )
            s.step(60)

            def _visibility(hidden: bool) -> dict[str, Any]:
                flag = "true" if hidden else "false"
                return s.lua(
                    f"local g = scenetree.findObject({GROUP!r}); local n = 0; local miss = 0; "
                    "if g then for i = 0, g:getCount() - 1 do local o = g:getObject(i); "
                    # busRouteManager.lua L46-48: a SimGroup child comes back as the C++ object
                    # and needs Sim.upcast before its Lua methods are there
                    "if o then o = Sim.upcast(o) end; "
                    f"if o and o.setHidden then o:setHidden({flag}); n = n + 1 "
                    "else miss = miss + 1 end end end "
                    "return jsonEncode({touched = n, without_setHidden = miss, "
                    "group_present = g ~= nil})"
                )

            bng.settings.set_nondeterministic()
            bng.control.resume()
            # UNCAP the frame rate first.  B4 boot 2's three legs each read exactly 16.667 ms,
            # 0 frames over 33 ms and realtime factor 1.000: the engine was holding 60 fps, so the
            # A/B/A subtracted two capped numbers and "measured" a cost of 0.000 ms.  A capped
            # frame cannot price a subsystem; the limiter has to come off before the legs run.
            limiter = s.lua(
                "local before = {fpsLimitEnabled = tostring(settings.getValue('fpsLimitEnabled')), "
                "fpsLimit = tostring(settings.getValue('fpsLimit')), "
                "vsync = tostring(settings.getValue('vsync'))}; "
                "settings.setValue('fpsLimitEnabled', false); settings.setValue('vsync', false); "
                "settings.setValue('fpsLimit', 0); "
                "return jsonEncode({before = before, after = {"
                "fpsLimitEnabled = tostring(settings.getValue('fpsLimitEnabled')), "
                "fpsLimit = tostring(settings.getValue('fpsLimit')), "
                "vsync = tostring(settings.getValue('vsync'))}})"
            )
            time.sleep(4.0)
            legs = []
            legs.append(_perf_leg(s, "A props visible", PERF_SECONDS))
            hide = _visibility(True)
            time.sleep(2.0)
            legs.append(_perf_leg(s, "B props hidden (the off control)", PERF_SECONDS))
            show = _visibility(False)
            time.sleep(2.0)
            legs.append(_perf_leg(s, "A' props visible again", PERF_SECONDS))
            bng.control.pause()
            bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
            bng.control.pause()
            measured = [leg["avg_frame_ms"] for leg in legs if leg["avg_frame_ms"] is not None]
            on_ms = (
                (legs[0]["avg_frame_ms"] + legs[2]["avg_frame_ms"]) / 2.0
                if legs[0]["avg_frame_ms"] is not None and legs[2]["avg_frame_ms"] is not None
                else None
            )
            s.report["props_render_cost"] = {
                "camera": {"eye": list(perf_eye), "aim": list(perf_aim), "clock": 0.30},
                "frame_limiter": limiter,
                "hide_call": hide,
                "show_call": show,
                "legs": legs,
                "props_cost_ms_per_frame": (
                    round(on_ms - legs[1]["avg_frame_ms"], 3)
                    if on_ms is not None and legs[1]["avg_frame_ms"] is not None
                    else None
                ),
                "a_to_a_prime_drift_ms": (
                    round(abs(legs[0]["avg_frame_ms"] - legs[2]["avg_frame_ms"]), 3)
                    if on_ms is not None
                    else None
                ),
                "legs_with_frames": len(measured),
                "note": (
                    "A/B/A at one fixed camera and clock: the cost is the mean of the two visible "
                    "legs minus the hidden leg, and the A-to-A' drift is published beside it so a "
                    "reader can see how much of the difference is noise."
                ),
            }
            s.check(
                int(hide.get("touched", 0)) > 400,
                "the off-control did not reach the props group",
                hide,
            )
            s.check(
                len(measured) == 3,
                "the frame-time probe counted no frames on at least one leg",
                [leg["frames"] for leg in legs],
            )
            # r5 (the G1 gate-shape audit): this was ``max(avg_fps for leg in legs) > 62``,
            # which passes when ONE leg is uncapped and the leg the arithmetic actually
            # subtracts is pinned at the limiter -- the same transient-maximum shape as r3's
            # ``reached_the_plateau``.  Ask the question the gate means: is any leg sitting
            # ON the limiter?  Each leg is priced individually and none may be clamped.
            clamped = [
                leg["leg"]
                for leg in legs
                if leg["avg_fps"] is not None and abs(float(leg["avg_fps"]) - PERF_CAP_FPS) < 1.0
            ]
            s.check(
                not clamped,
                "a frame-time leg is pinned at the limiter, so the off-control cannot "
                "price the props",
                {"limiter": limiter, "clamped": clamped, "fps": [leg["avg_fps"] for leg in legs]},
            )

        s.report["decal_batcher_experiment"] = batcher

        s.report["b4_manifests"] = {
            "shapes_sha": shapes["shapes"]["bench_log"]["sha256"],
            "placed_statics": place["placed_statics"],
            "prefab_instances": place["prefab_instances"],
            "prefab_statics": place["prefab_statics"],
        }

    boot = s.report
    assert boot["log"]["marker_seen"], boot["log"]
    assert not boot["problems"], boot["problems"]
    (Path(scaffold._evidence_dir(tmp_path)) / "b4_summary.json").write_text(
        json.dumps(
            {
                "bench_by_ray": {k: v for k, v in boot["bench_by_ray"].items() if k != "profile"},
                "bench_exit_frame": boot["bench_exit_frame"],
                "bench_exit_drops": [
                    {k: v for k, v in drop.items() if k != "samples"}
                    for drop in boot["bench_exit_drops"]
                ],
                "span_drive": {k: v for k, v in boot["span_drive"].items() if k != "rows"},
                "props_render_cost": boot["props_render_cost"],
                "decal_batcher_experiment": boot["decal_batcher_experiment"],
                "b4_census": boot["b4_census"],
                "log": boot["log"],
            },
            indent=1,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
        newline="\n",
    )


# --------------------------------------------------------------------------- the spline A/B
#: r2.  B4 r1 closed ``KNOWN_DECAL_BATCHER_LINE`` with a single-variable A/B whose A leg did
#: not survive: ``run_ab_linear.ps1`` wrote both legs into ONE evidence directory and ONE cut
#: directory, so the second run overwrote the first and every artefact on disk was the B leg.
#: The r1 critic could not re-open the headline row, and was right not to accept it.
#:
#: This is the same experiment with both legs kept.  Each leg is built from the CERTIFIED zip
#: by rewriting exactly one member -- ``main/MissionGroup/decal_road/items.level.json``,
#: rendered with and without ``level_writer.SPLINE_SURFACE_ENV`` -- so the two archives differ
#: by the three ``improvedSpline`` fields on the three ``m_dirt_variation`` surface roads and
#: by nothing else, and the payload delta is asserted to be exactly 3 bytes before either
#: boots.  Each leg writes its own zip, its own lock and its own evidence file, all hashed:
#:
#:     $env:HOT_POTATO_B4_SPLINE_AB = "linear"   # the shipped form: improvedSpline false
#:     $env:HOT_POTATO_B4_SPLINE_AB = "spline"   # the A leg:        improvedSpline true
SPLINE_AB_ENV = "HOT_POTATO_B4_SPLINE_AB"
SPLINE_AB_MEMBER = "main/MissionGroup/decal_road/items.level.json"
SPLINE_AB_ROADS = ("track_surface_a", "track_surface_b", "trail_surface")


def _render_road_member(spline: bool) -> bytes:
    """``visible_road_records()`` as the archive member, with the lever on or off."""

    from examples.hot_potato_arena.level import level_writer as writer

    previous = os.environ.get(writer.SPLINE_SURFACE_ENV)
    if spline:
        os.environ[writer.SPLINE_SURFACE_ENV] = "1"
    else:
        os.environ.pop(writer.SPLINE_SURFACE_ENV, None)
    try:
        return b"".join(
            json.dumps(record, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
            for record in writer.visible_road_records()
        )
    finally:
        if previous is None:
            os.environ.pop(writer.SPLINE_SURFACE_ENV, None)
        else:
            os.environ[writer.SPLINE_SURFACE_ENV] = previous


def _build_spline_ab_leg(destination: Path, spline: bool) -> dict[str, Any]:
    """The certified cut with ONE member re-rendered; every other byte copied verbatim."""

    import zipfile

    from examples.hot_potato_arena.level import build_level_zip as bdist

    source_dir = Path(os.getenv(scaffold.DIST_DIR_ENV) or bdist.DEFAULT_OUTPUT_DIR)
    lock = json.loads((source_dir / bdist.LOCK_NAME).read_text(encoding="utf-8"))
    member = f"{bdist.LEVEL_RELATIVE}/{SPLINE_AB_MEMBER}"
    destination.mkdir(parents=True, exist_ok=True)
    out_zip = destination / bdist.ZIP_NAME
    payload = _render_road_member(spline)
    before = after = ""
    shipped = b""
    with zipfile.ZipFile(source_dir / bdist.ZIP_NAME) as src:
        with zipfile.ZipFile(out_zip, "w") as out:
            for info in src.infolist():
                body = src.read(info.filename)
                if info.filename == member:
                    shipped = body
                    before = hashlib.sha256(body).hexdigest()
                    body = payload
                    after = hashlib.sha256(body).hexdigest()
                copy = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                copy.compress_type = info.compress_type
                copy.external_attr = info.external_attr
                out.writestr(copy, body)
    body = out_zip.read_bytes()
    lock["sha256"] = hashlib.sha256(body).hexdigest()
    lock["size"] = len(body)
    lock["member_sha256"][member] = after
    (destination / bdist.LOCK_NAME).write_text(
        json.dumps(lock, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    # the single-variable claim, computed HERE and asserted before either leg boots: render
    # the member both ways and diff it record by record.
    other = _render_road_member(not spline)
    mine = payload.decode("utf-8").splitlines()
    theirs = other.decode("utf-8").splitlines()
    differing = [json.loads(a)["name"] for a, b in zip(mine, theirs, strict=True) if a != b]
    return {
        "records_in_the_member": len(mine),
        "records_differing_between_the_legs": sorted(differing),
        "payload_delta_between_the_legs_bytes": len(payload) - len(other),
        "leg": "spline" if spline else "linear",
        "member": member,
        "member_sha256_in_the_certified_cut": before,
        "member_sha256_in_this_leg": after,
        "member_bytes_certified": len(shipped),
        "member_bytes_this_leg": len(payload),
        "member_delta_bytes": len(payload) - len(shipped),
        "zip_sha256": lock["sha256"],
        "zip_size": lock["size"],
        "members": len(lock["members"]),
        "certified_zip_sha256": hashlib.sha256(
            (source_dir / bdist.ZIP_NAME).read_bytes()
        ).hexdigest(),
    }


@pytest.mark.beamng_live
def test_the_decal_batcher_line_single_variable_ab(tmp_path: Path) -> None:
    """One boot per leg: does ``improvedSpline`` alone decide the decal-batcher E line?

    Both legs are built here from the same certified zip and both are KEPT -- their own
    directory, their own lock, their own ``evidence_splineab_<leg>.json`` -- so the pair can
    be re-opened by anyone.  Run both legs and compare
    ``known_decal_batcher_errors``: the shipped form (linear) must read 0 and the spline leg
    must read >= 1 for the closure to stand.
    """

    leg = (os.getenv(SPLINE_AB_ENV) or "").strip().casefold()
    if leg not in {"linear", "spline"}:
        pytest.skip(f"set {SPLINE_AB_ENV}=linear|spline to spend a boot on the spline A/B")
    stage = scaffold._evidence_dir(tmp_path) / "spline_ab" / leg
    variant = _build_spline_ab_leg(stage, spline=leg == "spline")
    # single-variable, asserted BEFORE the boot: three records, one field, three bytes.
    # `"improvedSpline":false` is exactly 3 bytes longer than `"improvedSpline":true`.
    assert variant["records_differing_between_the_legs"] == sorted(
        f"{LEVEL_ID}_{name}" for name in SPLINE_AB_ROADS
    ), variant
    assert abs(variant["payload_delta_between_the_legs_bytes"]) == 3, variant
    # and the SHIPPED member is the linear leg, byte for byte
    assert abs(variant["member_delta_bytes"]) == (0 if leg == "linear" else 3), variant
    previous = os.environ.get(scaffold.DIST_DIR_ENV)
    os.environ[scaffold.DIST_DIR_ENV] = str(stage)
    try:
        with scaffold._boot(f"b4splineab_{leg}", tmp_path) as s:
            s.report["spline_ab"] = variant
            bng = s.bng
            from beamngpy import Scenario, Vehicle

            scenario = Scenario(LEVEL_ID, scaffold.BNGPY_SCENARIO_NAME)
            scenario.add_vehicle(
                Vehicle(VEH, model="etk800", licence="B4AB"),
                pos=(ps.CENTER[0] + 40.0, ps.CENTER[1], ps.CENTER[2] + 0.6),
                rot_quat=(0, 0, 0, 1),
            )
            scenario.make(bng)
            s.scenario = scenario
            s.scenario_dir = None
            bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
            bng.scenario.load(scenario, precompile_shaders=False)
            bng.scenario.start()
            bng.control.pause()
            s.step(180)
            s.marker(s.log_marker)
            s.report["roads_at_load"] = {
                name: s.lua(
                    f"local r = scenetree.findObject('{LEVEL_ID}_{name}'); "
                    "if not r then return jsonEncode({ok = false}) end "
                    "return jsonEncode({ok = true, nodes = r:getNodeCount(), "
                    "improvedSpline = tostring(r:getField('improvedSpline', 0))})"
                )
                for name in SPLINE_AB_ROADS
            }
            # the same TSStatic census the main gate takes, on a DIFFERENT scenario: any
            # object that shows up in both and is not this level's is the harness's or the
            # engine's, which is what r1's unexplained "4,589 against 4,578" needs.
            census = s.lua(
                "local out = {statics = 0, by_shape = {}}; "
                "for _, id in ipairs(scenetree.findClassObjects('TSStatic')) do "
                "local o = scenetree.findObject(id); if o then "
                "local shape = tostring(o:getField('shapeName', 0)); "
                "out.by_shape[shape] = (out.by_shape[shape] or 0) + 1; "
                "out.statics = out.statics + 1; end end return jsonEncode(out)"
            )
            prefix = f"/levels/{LEVEL_ID}/"
            s.report["tsstatic_census"] = {
                "total": census["statics"],
                "not_from_this_level": {
                    k: v for k, v in census["by_shape"].items() if not str(k).startswith(prefix)
                },
            }
            issues = scaffold._level_log_issues(s.user / "beamng.log", s.log_marker)
            s.report["batcher"] = {
                "known_decal_batcher_errors": len(issues["known_decal_batcher_errors"]),
                "lines": issues["known_decal_batcher_errors"][:6],
                "error_lines": issues["error_lines"],
                "level_attributable_errors": len(issues["level_attributable_errors"]),
                "level_attributable_errors_including_known": issues[
                    "level_attributable_errors_including_known"
                ],
            }
    finally:
        if previous is None:
            os.environ.pop(scaffold.DIST_DIR_ENV, None)
        else:
            os.environ[scaffold.DIST_DIR_ENV] = previous
    boot = s.report
    assert boot["log"]["marker_seen"], boot["log"]
    read_back = {k: v.get("improvedSpline") for k, v in boot["roads_at_load"].items()}
    assert set(read_back.values()) == {"1" if leg == "spline" else "0"}, read_back
    out = Path(scaffold._evidence_dir(tmp_path)) / f"evidence_splineab_{leg}.json"
    out.write_text(
        json.dumps(
            {
                "leg": leg,
                "cut": variant,
                "roads_at_load": boot["roads_at_load"],
                "batcher": boot["batcher"],
                "tsstatic_census": boot["tsstatic_census"],
                "log": boot["log"],
            },
            indent=1,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
        newline="\n",
    )
