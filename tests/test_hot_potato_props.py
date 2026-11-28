"""Static gates for build round B4: the props, the bench log and the road decal stacks.

Every gate reads the BUILT tree (``examples/hot_potato_arena/mod/levels/<id>/``) or the
exported DAEs, never the design document alone -- the design is the contract, the tree is the
claim, and these tests are where the two are compared.

The bench log is the load-bearing element (design §7.2: a multi-tier deck with a one-way drop
on three sides and a ramp on the fourth), so it gets four gates of its own: the ramp's grade
against the 12 % law, the deck's height, the built surface against its own authored profile,
and the runoff past all four exits measured against the forest and hearth AS BUILT.

Skipped as a whole when the B4 manifests are absent (the shapes have not been cut yet).
"""

from __future__ import annotations

import itertools
import json
import math
import re
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from examples.hot_potato_arena.level import forest_spec as fs
from examples.hot_potato_arena.level import props_build
from examples.hot_potato_arena.level import props_spec as ps
from examples.hot_potato_arena.level import terrain_io as terrain

pytestmark = pytest.mark.skipif(
    not props_build.available(), reason="B4 manifests absent; run the prop build scripts first"
)

LEVEL_ROOT = ps.EXAMPLE_ROOT / "mod" / "levels" / ps.LEVEL_ID
COLLADA = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
GROUP = ps.PROPS_GROUP
RUNOFF_MIN_M = 50.0
GRADE_LAW = 0.12
RELIEF_LAW_M = 0.020
SWEEP_HALF_W = 3.5
#: the brief's drop band is 3-5 m; a station whose flank offers less is not a flank DROP, so
#: it is measured and published but does not set the flank exit's runoff (the crown's own
#: lip, 1.0 m over the ground at x_local +50, is the station this excludes).
FLANK_DROP_MIN_M = 3.0
#: the west descent is not a ramp a car has to CLIMB, so the 12 % law is not its law.  r2's
#: was gentle enough to satisfy a release-speed bar of 8 m/s and critic pass 2 then drove an
#: etk800 UP it at 45 % throttle -- an exit anyone can climb is not the design's one-way
#: drop-off.  r3's law is the other way round: the crown must be STEEP enough that no road
#: car climbs it, so its release speed is BELOW every speed the deck can produce and a car
#: leaving it is flying, not pole-vaulting.
CROWN_RELEASE_MAX_MS = 7.0
#: what a road car will not climb.  The critic's own climb was 26 %; stock BeamNG's steepest
#: signed grades are ~ 25 %, and 45 deg (100 %) is the domain of a rock crawler.  72 % is
#: 35.8 deg -- past the point where an etk800's front wheels can hold on grass or timber.
CROWN_CLIMB_MIN_GRADE = 0.60
#: the drivable band's arris: high enough to turn a drifting car back, low enough to be a
#: rolled shoulder rather than a kerb that trips one.
ARRIS_MIN_M = 0.25
#: the SNAPPED crown, built at two break-face heights and refuted at both (r3):
#:   1.05 m -- one-way (etk800 WOT and 45 %, and the pickup, all failed to climb it) but the
#:             4 m/s drive hung up across it at pitch -77 deg, 1.8 m above the meadow;
#:   0.75 m -- the 8 m/s drive POLE-VAULTED (pitch -85.9, rest up.z -0.9808) and all three
#:             climbs cleared it.
#: The crown therefore ends tangent to the ground and the west end is honestly two-way.
#: Kept as the band the experiment used; ``west_break_face_m`` is 0.0 in what ships.
BREAK_FACE_BAND = (0.60, 1.10)


# --------------------------------------------------------------------------- helpers
def _jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _props_records() -> list[dict]:
    return _jsonl(LEVEL_ROOT / f"main/MissionGroup/{GROUP}/items.level.json")


def _dae_vertices(path: Path) -> dict[str, np.ndarray]:
    root = ET.parse(path).getroot()
    out: dict[str, np.ndarray] = {}
    for geometry in root.findall("c:library_geometries/c:geometry", COLLADA):
        name = geometry.get("name") or geometry.get("id") or ""
        source = geometry.find("c:mesh/c:source/c:float_array", COLLADA)
        if source is None or not source.text:
            continue
        out[name] = np.asarray([float(v) for v in source.text.split()], dtype=np.float64).reshape(
            -1, 3
        )
    return out


def _bench_geometry() -> dict:
    return props_build.shapes_manifest()["shapes"]["bench_log"]["bench"]


def _bench_profile(geom: dict):
    """The authored drivable centre line: eased ramp, flat plateau, then the west crown."""

    profile = ps.ramp_profile(geom["run"], geom["ease"], geom["rise"], 3300)
    stations = np.asarray([s for s, _ in profile])
    heights = np.asarray([z for _, z in profile])
    # measured back from the crown's FOOT, so the profile's near ease is the foot's and its
    # far ease is the crest's -- r3's crown is asymmetric (4.6 m crest / 2.0 m foot)
    west = ps.ramp_profile(
        geom["crown_run"],
        geom["crown_ease_foot"],
        geom["crown_fall"],
        3200,
        ease_end=geom["crown_ease"],
    )
    west_s = np.asarray([s for s, _ in west])
    west_z = np.asarray([z for _, z in west])

    def at(x: float) -> float:
        if x >= geom["crown_x"]:
            # the log SNAPS at ``break_x``; past it there is no drivable surface at all
            back = min(max(geom["half"] - min(x, geom["break_x"]), 0.0), geom["crown_run"])
            return geom["crown_foot_z"] + float(np.interp(back, west_s, west_z))
        if x >= geom["join_x"] - 1e-9:
            return geom["deck_z"]
        u = min(max(x - geom["toe_x"], 0.0), geom["run"])
        return geom["toe_z"] + float(np.interp(u, stations, heights))

    return at


def _bench_half_width(geom: dict, x: float) -> float:
    return ps.crown_half_width(
        geom["radius"],
        x,
        geom["crown_x"],
        geom["break_x"] - geom["crown_x"],
        geom["crown_taper"],
    )


def _ray_top(verts: np.ndarray, tris: np.ndarray, xs, y: float = 0.0) -> dict[float, float]:
    """Highest surface under a vertical ray at each (x, ``y``): a mesh cast, not a vertex read.

    r1 read the drivable surface by taking the maximum z of the vertices ON the centre line.
    That is only the surface while every station happens to KEEP its centre vertex: the LOD
    decimator drops coplanar and near-coplanar ones, and where it does, the reading falls
    through to the belly vertex 3.8 m below and the gate measures a hole that is not there.
    Casting a ray at the triangles is what the live gate does with ``castRayStatic``, and it
    is decimation-proof.
    """

    tri = verts[tris]
    ax, ay = tri[:, 0, 0], tri[:, 0, 1]
    bx, by = tri[:, 1, 0], tri[:, 1, 1]
    cx, cy = tri[:, 2, 0], tri[:, 2, 1]
    det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    det = np.where(np.abs(det) < 1e-12, np.nan, det)
    out: dict[float, float] = {}
    for x in xs:
        u = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / det
        v = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / det
        w = 1.0 - u - v
        inside = (u >= -1e-9) & (v >= -1e-9) & (w >= -1e-9)
        if not inside.any():
            continue
        z = u * tri[:, 0, 2] + v * tri[:, 1, 2] + w * tri[:, 2, 2]
        out[round(float(x), 4)] = float(np.nanmax(np.where(inside, z, -np.inf)))
    return out


def _bench_surface(name_filter=lambda n: "a250" not in n and "a80" not in n):
    """``{mesh name: cast(xs) -> {x: top z}}`` for the bench log's non-LOD meshes."""

    meshes = _dae_triangles(LEVEL_ROOT / ps.shape_relative("bench_log"))
    return {
        name: (lambda xs, v=verts, t=tris: _ray_top(v, t, xs))
        for name, (verts, tris) in meshes.items()
        if name_filter(name)
    }


def _origin_z() -> float:
    """World z of the bench log's own datum: every local height is measured from here."""

    row = ps.log_row("bench_log")
    return float(row["z_ground"])


def _bench_frame():
    """(origin, along, across) of the placed bench log in world coordinates."""

    row = ps.log_row("bench_log")
    origin = np.asarray([float(row["x"]), float(row["y"])])
    along = np.asarray(ps.heading_vector(float(row["heading_along_decreasing_bearing"])))
    across = np.asarray([-along[1], along[0]])
    return origin, along, across


# --------------------------------------------------------------------------- G-B4-1/2/3
def test_bench_ramp_grade_and_deck_height_from_the_exported_mesh() -> None:
    """G-B4-1/2: the ramp climbs at <= 12 % and the deck sits exactly +3.5 m over the ground."""

    geom = _bench_geometry()
    row = ps.log_row("bench_log")
    ground = float(terrain.surface_z(float(row["x"]), float(row["y"])))
    assert geom["deck_z"] == pytest.approx(ps.BENCH["deck_lift_m"], abs=1e-6)
    assert ground + geom["deck_z"] == pytest.approx(105.006, abs=0.002)
    # the 12 % law is the RAMP's law; the west crown is a deliberate convex roll-off with a
    # release-speed law of its own (see the crown gate), so the grade sweep stops where the
    # plateau does.
    step = 0.15
    # floor, not round: the sweep must STOP at the crown, or its last station lands inside
    # the descent and the plateau reads 0.26 mm out of plane (r3's crown starts at +42.0,
    # which is not a whole number of 0.15 m steps from the toe -- r2's +34.0 was).
    count = math.floor((geom["crown_x"] - geom["toe_x"]) / step + 1e-9)
    xs = [geom["toe_x"] + step * k for k in range(count + 1)]
    for name, cast in _bench_surface().items():
        tops = cast(xs)
        keys = sorted(tops)
        assert len(keys) >= count - 2, (name, len(keys))
        grades = [
            (tops[keys[i + 1]] - tops[keys[i]]) / (keys[i + 1] - keys[i])
            for i in range(len(keys) - 1)
        ]
        assert max(abs(g) for g in grades) <= GRADE_LAW, (name, max(abs(g) for g in grades))
        deck = [tops[x] for x in keys if x >= geom["join_x"] + 1e-6]
        assert max(deck) - min(deck) < 1e-6, (name, "the plateau is not one plane")
        assert deck[0] == pytest.approx(geom["deck_z"], abs=1e-6)


def test_bench_drivable_surface_matches_its_authored_profile() -> None:
    """G-B4-3: the built deck and ramp deviate from the authored profile by << 20 mm.

    This is the relief law applied to a MESH: the surface's departure from what it says it
    is.  The ramp's intended CURVATURE is a separate number and is reported, not gated --
    the arena's Handle ships 3.0 m eases at 11.98 % (DESIGN.md §2.4), whose grade changes by
    60 mm per metre inside the ease by construction, so gating an ease against the terrain's
    +-0.02 m second-difference law would fail every ramp the repo has ever shipped.
    """

    geom = _bench_geometry()
    profile = _bench_profile(geom)
    step = 0.15
    count = math.floor((geom["break_x"] - geom["toe_x"]) / step + 1e-9)
    xs = [geom["toe_x"] + step * k for k in range(count + 1)]
    worst: dict[str, float] = {}
    crown_worst: dict[str, float] = {}
    for name, cast in _bench_surface().items():
        tops = cast(xs)
        assert len(tops) >= count - 2, (name, len(tops))
        assert max(abs(tops[x] - profile(x)) for x in tops) <= RELIEF_LAW_M, name
        flat = {x: z for x, z in tops.items() if x <= geom["crown_x"]}
        crown = {x: z for x, z in tops.items() if x > geom["crown_x"]}
        worst[name] = max(abs(z - profile(x)) for x, z in flat.items())
        # the west descent is an eased S -- convex at the crest, concave at the foot -- so
        # its chords sag BELOW the curve at the top and ride ABOVE it at the bottom, by
        # construction.  The bound is what matters, not the sign; it is 45x inside the law.
        crown_worst[name] = max(abs(z - profile(x)) for x, z in crown.items())
        assert crown_worst[name] <= 0.010, (name, crown_worst[name])
    # Ramp and plateau by RAY: inside 5 mm.  r1 published 0.0052 MM for this, which is the
    # error at the authored stations only -- the vertices sit on the profile to a fraction of
    # a micrometre, but between them the surface is a chord, and through the two 3.0 m eases
    # a 0.75 m chord on a curve sags millimetres.  Both numbers are true and only the second
    # is the surface a wheel rides, so both are asserted here.
    assert max(worst.values()) < 0.005, worst
    # and the same measurement at the stations that KEEP a centre vertex after export
    # (the exporter merges the plateau's coplanar interior, so this covers the ramp's two
    # eases and the whole west descent -- the parts that are curved and could be wrong).
    at_stations = {}
    for name, verts in _dae_vertices(LEVEL_ROOT / ps.shape_relative("bench_log")).items():
        if "a250" in name or "a80" in name:
            continue
        centre = verts[(np.abs(verts[:, 1]) < 1e-6) & (verts[:, 2] > 0.0)]
        on = [(float(x), float(z)) for x, _y, z in centre if abs(z - profile(float(x))) < 0.05]
        assert len(on) >= 10, (name, len(on))
        at_stations[name] = max(abs(z - profile(x)) for x, z in on)
    assert max(at_stations.values()) < 1e-5, at_stations


def test_the_west_crown_rolls_off_instead_of_ending_in_a_square_lip() -> None:
    """G-B4-9 (r3): the west end is a convex crown, tangent, with no lip -- and ONE-WAY.

    B4 r1 ended the deck in a 3.40 m vertical face.  Driven off it at ~4 m/s the car's nose
    dropped into the void, the bumper caught the 90 deg lip and the vehicle pole-vaulted and
    came to rest INVERTED on the deck at x_local +49.49 (`bench_exit_drops` in every r1 boot,
    up.z -0.9735).  A convex crown cannot do that: below the release speed the wheels stay
    loaded all the way down, and above it the car leaves the crest already level.

    r2 fixed the pole-vault with a 16 m descent at 26 % and lost the exit doing it -- critic
    pass 2 drove an etk800 back UP it at 45 % throttle, so the log had two entrances and the
    design's third one-way drop was simply gone.

    r3 shortened and steepened the crown to try to make it unclimbable, then measured that
    NO grade a level can afford beats a run-up (an etk800 arrives at the foot with 36 J/kg
    against a 33 J/kg hill) and that both break faces built to force the issue -- 1.05 m and
    0.75 m -- were refuted, one by hanging a car up at pitch -77 deg and the other by
    pole-vaulting it.  So what SHIPS is a two-way ramp: **10.0 m of run, a 4.6 m convex
    crest, a 5.4 m concave foot, 67.8 % through the middle**, ending tangent to the ground
    with ``west_break_face_m == 0.0``, and deviation 7 declares it.

    r4 corrects this docstring, which is critic pass 3's N3: it had survived from the
    abandoned attempt, describing "8.0 m of run, a 2.0 m foot, 72 %", calling the crown
    "unclimbable" and listing as this gate's purpose "so it is a drop and not a ramp" --
    against a shipped 10.0 / 5.4 / 67.83 that the round had itself proved climbable, and
    four lines below its own code asserting the opposite.  It is the one docstring B5 reads
    to learn what the west end is, and it said the wrong thing about all three numbers.

    Gated, on the visual AND the collider:

    1.  the crown's own surface follows the authored profile to << the 20 mm relief law;
    2.  the grade at the top of the crown is 0 -- tangency, i.e. no grade STEP where the
        plateau ends (AGENTS.md L1285) -- and 0 at the foot, where it meets the terrain;
    3.  the profile is MONOTONE DOWN at every station: no lip anywhere for a nose to catch
        (level_facts law 6), which is the property r2 paid a diagnostic boot for;
    4.  the max grade is steep -- ``CROWN_CLIMB_MIN_GRADE`` -- so the descent is a genuine
        drop-off to drive OFF, even though a car with a run-up can also come back UP it;
    5.  the release speed ``sqrt(g R)`` is BELOW every approach speed the deck produces, so
        a car leaving it is airborne and level rather than pivoting on an edge;
    6.  the crest radius is large enough that a 2.8 m wheelbase does not ground on it.
    """

    geom = _bench_geometry()
    at = _bench_profile(geom)
    assert geom["crown_run"] == pytest.approx(ps.BENCH["west_ramp_m"], abs=1e-9)
    assert geom["crown_release_v"] <= CROWN_RELEASE_MAX_MS, geom
    assert geom["crown_grade"] >= CROWN_CLIMB_MIN_GRADE, geom
    # The crown ends TANGENT TO THE GROUND.  r3 tried to make the west end one-way with a
    # break face -- twice, at 1.05 m and 0.75 m -- and measured both refuted (see
    # BREAK_FACE_BAND).  A step at the foot of a nose-down slope ploughs whether the step
    # goes up or down, so the foot is on the ground and the west end is honestly two-way.
    assert ps.BENCH["west_break_face_m"] == 0.0, ps.BENCH
    assert geom["break_x"] == pytest.approx(geom["half"], abs=1e-9), geom
    assert abs(geom["crown_foot_z"] - _terrain_local(geom["half"])) <= 0.02, geom
    # a car bridging the crest on a 2.8 m wheelbase sags L^2 / 8R; 0.30 m keeps its belly
    # off the timber while it tips, which is why the crest ease is 4.6 m and not 1.5
    assert geom["crown_crest_radius"] >= 2.8**2 / (8 * 0.30), geom
    step = 0.25
    count = math.floor((geom["break_x"] - geom["crown_x"]) / step + 1e-9)
    xs = [geom["crown_x"] + step * k for k in range(count + 1)]
    vertices = _dae_vertices(LEVEL_ROOT / ps.shape_relative("bench_log"))
    checked = 0
    for name, cast in _bench_surface().items():
        tops = cast(xs)
        crown = sorted(tops)
        assert len(crown) >= count - 1, (name, len(crown))
        assert max(abs(tops[x] - at(x)) for x in crown) <= RELIEF_LAW_M, name
        grades = [
            (tops[crown[i + 1]] - tops[crown[i]]) / (crown[i + 1] - crown[i])
            for i in range(len(crown) - 1)
        ]
        # tangent to the deck plane at the top AND to the terrain at the foot: no grade step
        # at either end, which is the whole reason the descent is eased and not a chamfer.
        assert abs(grades[0]) <= 0.05, (name, "the crown leaves the plateau with a step")
        assert abs(grades[-1]) <= 0.06, (name, "the crown meets the ground with a step")
        assert max(abs(g) for g in grades) <= geom["crown_grade"] + 0.02, (name, max(grades))
        assert tops[crown[-1]] == pytest.approx(at(crown[-1]), abs=0.01), name
        # law 6, gated on the built surface: NOTHING on the descent rises in the direction of
        # travel.  A lip is a positive grade, however small, and one 1.00 m lip took a car
        # from -25.6 deg at 7.17 m/s to -59.5 deg at 0.65 m/s in a single 33 ms tick.
        assert max(grades) <= 1e-6, (name, "the crown rises somewhere: that is a plough")
        # and the section really does narrow, so the end reads as a log and not a wedge
        verts = vertices[name]
        end = verts[verts[:, 0] > geom["break_x"] - 0.2]
        body = verts[np.abs(verts[:, 0]) < 5.0]
        assert end[:, 1].max() < body[:, 1].max() * (geom["crown_taper"] + 0.02), name
        checked += 1
    assert checked >= 2, sorted(vertices)


def test_the_deck_is_a_trough_between_two_containment_walls() -> None:
    """G-B4-13 (r4): the long edge is a continuous WALL with no window in it, and the band
    between the two walls is dead flat.

    History, because this gate has asserted four different shapes and the reason matters.
    r3 built critic pass 2's suggested fix twice -- an arris 0.34 m ON the log's widest line
    and a ridge 0.30 m set inboard -- drove a 43-cell heading x speed grid at each, and both
    came out WORSE than the flat deck (14 and 25 cells rolled past 90 deg against 11).  r3
    concluded that no edge treatment can work and shipped the deck flat.

    Critic pass 3 then drove the headings r3's 10 deg step never sampled, on r3's own
    certified cut, and refuted the flat deck too: at 8 m/s every off-axis heading from -30 to
    +25 deg rolls the car past 90 deg except 0 itself, and +-5 deg -- a drift, not a
    manoeuvre -- puts it on its roof 0.96 m above the meadow, 86 m outside the ring, with the
    carrier's fuse at 3x.  Both r3 sections were 0.30-0.34 m: KERB height, which trips a
    wheel without containing the car, so the whole class had been sampled in one regime.

    r4's first cut walled the flank at 0.90 m and kept the design's two 6 m split-out windows
    as aimed flank exits.  Its own 59-cell boot (``b4/r4/e1_flank_ab.json``) refuted the
    WINDOWS, not the wall: every rolled bolster cell crossed the edge inside the outer window
    or on its fade, and every cell that met the wall itself was turned back upright.  A
    window is a ledge, and a 3.5 m ledge anywhere on the long edge is the defect.

    So what ships, and what this gate asserts, is the shape that makes the containment claim
    true with NO exception along the whole edge:

    #. the section: a wall of ``arris_h_m`` >= 0.80 m (ships 1.20, above a road car's belt
       line) rising over the 0.30 m from ``deck_flat_half_m`` to ``deck_ridge_half_m``, then
       a FLAT crest from there to the log's widest line (``wall_flat_top``), symmetric, and
       ``flank_splitouts`` EMPTY -- ``splitout_window`` returns ``None`` for both sides;
    #. at every walled station the drivable band is dead flat at the deck plane; the wall
       climbs MONOTONICALLY to full height by the crest half-width; the crest holds full
       height out to the widest line; and a ray just outboard of the widest line finds NO
       shelf at deck height -- there is nothing outboard of the crest to leave from;
    #. all of that in the visual AND in the collider (a collider that stops short of the
       wall is a wall a car drives through);
    #. nothing anywhere stands above deck + wall, so no second lip hides above it;
    #. CONTINUITY: sampled every metre from the ramp's join to the crown's start, the wall
       is at full height on both flanks -- no window, no gap, no fade in the middle;
    #. the ramp's toe and the crown's foot carry no kerb (level_facts law 6: never a raised
       edge lying on the grass), and the SAME instrument reads the full wall on the deck,
       so it is measuring the thing it claims to.
    """

    geom = _bench_geometry()
    tris = _dae_triangles(LEVEL_ROOT / ps.shape_relative("bench_log"))
    surfaces = {k: v for k, v in tris.items() if "a250" not in k and "a80" not in k}
    assert len(surfaces) >= 2, sorted(tris)
    wall = float(geom["arris_h"])
    flat_half = float(geom["deck_flat_half"])
    crest_half = float(geom["deck_ridge_half"])
    radius = 0.5 * float(ps.BENCH["diam_m"])
    assert wall >= 0.80, geom  # containment height, not kerb height
    assert flat_half < crest_half < radius, geom  # a face, then a flat crest, then the edge
    assert ps.BENCH["wall_flat_top"] is True, ps.BENCH
    assert 2.0 * flat_half >= 5.0, geom  # still a wide deck: 6.0 m of dead flat
    for side in ps.FLANK_SIDES:  # what ships is symmetric, and it is a wall
        assert ps.flank_section(side) == ps.flank_section("outer"), side
        assert ps.flank_section(side)["flat_top"] is True, side
        assert ps.flank_kind(ps.flank_section(side)["height"]) == "bolster", side
        assert ps.splitout_window(side) is None, side  # NO window on either flank
    assert ps.BENCH["flank_splitouts"] == (), ps.BENCH["flank_splitouts"]
    assert geom["splitouts"] == [], geom["splitouts"]

    walled = (geom["join_x"] + 1.0, -18.0, -16.0, 0.0, 20.0, 30.0, 40.0, geom["crown_x"] - 0.5)
    flat_ys = [round(y, 3) for y in np.arange(-flat_half + 0.05, flat_half - 0.049, 0.05)]
    face_ys = [round(y, 3) for y in np.arange(flat_half, crest_half + 1e-9, 0.05)]
    crest_ys = [round(y, 3) for y in np.arange(crest_half, radius - 0.02, 0.05)] + [
        round(radius - 0.005, 3)
    ]
    for name, (verts, faces) in surfaces.items():
        for x in walled:
            band = {}
            for y in flat_ys:
                hit = _ray_top(verts, faces, [x], y)
                if hit:
                    band[y] = next(iter(hit.values()))
            assert len(band) >= len(flat_ys) - 2, (name, x, len(band))
            assert max(band.values()) - min(band.values()) <= 1e-6, (name, x, "not flat")
            assert max(band.values()) == pytest.approx(geom["deck_z"], abs=1e-6), (name, x)
            for sign in (-1.0, +1.0):
                # the face: monotone up, full height by the crest half-width
                climb = []
                for y in face_ys:
                    hit = _ray_top(verts, faces, [x], sign * y)
                    if hit:
                        climb.append(next(iter(hit.values())) - geom["deck_z"])
                assert len(climb) >= len(face_ys) - 1, (name, x, sign, len(climb))
                assert all(b >= a - 1e-6 for a, b in itertools.pairwise(climb)), (name, x, sign)
                assert climb[-1] >= wall - 0.02, (name, x, sign, climb[-1])
                # the crest: FLAT at full height all the way out to the widest line
                top = []
                for y in crest_ys:
                    hit = _ray_top(verts, faces, [x], sign * y)
                    if hit:
                        top.append(next(iter(hit.values())) - geom["deck_z"])
                assert len(top) >= len(crest_ys) - 1, (name, x, sign, len(top))
                assert min(top) >= wall - 0.02, (name, x, sign, min(top))
                assert max(top) <= wall + 0.02, (name, x, sign, max(top))
                # and NO shelf outboard of the widest line: the ray either misses the log
                # or finds the belly / a knot well below the deck plane
                beyond = _ray_top(verts, faces, [x], sign * (radius + 0.02))
                assert not beyond or next(iter(beyond.values())) < geom["deck_z"] - 0.5, (
                    name,
                    x,
                    sign,
                    beyond,
                )
    # nothing on the whole log stands above the wall's own crest -- no second lip.
    # The a700 and the Colmesh are authored, so they are held to the exporter's own
    # quantisation (1e-5 m); the two far LODs are DECIMATED, and an edge collapse moves a
    # vertex a millimetre or two, so they get 5 mm.  Neither is a surface a car touches.
    for name, verts in _dae_vertices(LEVEL_ROOT / ps.shape_relative("bench_log")).items():
        slack = 5e-3 if ("a250" in name or "a80" in name) else 1e-4
        assert verts[:, 2].max() <= geom["deck_z"] + wall + slack, (
            name,
            float(verts[:, 2].max()),
        )
    # CONTINUITY along the whole plateau, both flanks, both surfaces: the wall never dips.
    # r4's first cut opened two 6 m windows here and its own boot rolled cars through them.
    a700 = next(v for k, v in surfaces.items() if k.endswith("_a700"))
    for name, (verts, faces) in surfaces.items():
        for sign in (-1.0, +1.0):
            xs = [
                geom["join_x"] + 1.0 + k for k in range(int(geom["crown_x"] - geom["join_x"] - 1.5))
            ]
            tops = _ray_top(verts, faces, xs, sign * (radius - 0.005))
            assert len(tops) >= len(xs) - 1, (name, sign, len(tops), len(xs))
            low = min(tops.values()) - geom["deck_z"]
            assert low >= wall - 0.02, (name, sign, "the wall dips to", round(low, 3))

    # the ramp's toe and the crown's foot carry no kerb.  Measured as the RISE ACROSS the
    # outer band -- z at the edge minus z just inboard of where the wall would start --
    # because both the toe and the crown's foot conform to the terrain's own cross-slope,
    # and a 57 mm cross-slope is the ground, not a kerb.
    def _across(x: float, side: float, out: float = 0.985) -> float:
        half_w = ps.crown_half_width(
            radius, x, geom["crown_x"], geom["break_x"] - geom["crown_x"], geom["crown_taper"]
        )
        edge = _ray_top(a700[0], a700[1], [x], side * out * half_w)
        inboard = _ray_top(a700[0], a700[1], [x], side * (flat_half / radius) * 0.90 * half_w)
        assert edge and inboard, (x, side)
        return next(iter(edge.values())) - next(iter(inboard.values()))

    for x, side in (
        (geom["toe_x"] + 1.0, +1.0),
        (geom["toe_x"] + 1.0, -1.0),
        (geom["half"] - 0.5, +1.0),
        (geom["half"] - 0.5, -1.0),
    ):
        assert _across(x, side) <= 0.02, (x, side, "a kerb where there must be none")
    # ... and the SAME reading on a walled station is the full wall, so the instrument
    # above is measuring the thing it claims to measure rather than always reading zero.
    for x in (-18.0, 0.0, 30.0):
        for side in (-1.0, +1.0):
            assert _across(x, side, out=0.999) >= wall - 0.01, (x, side, "no wall")


def test_the_bench_log_reads_as_a_log_in_the_shipped_bytes() -> None:
    """G-B4-14 (r3): the bark / hewn / end-grain partition, READ OFF THE SHIPPED DAE.

    r2's report published "4,968 bark / 1,265 hewn / 71 end-grain, measured on the shipped
    a700".  The shipped a700 said 5,208 / 1,024 / 72.  The totals matched, so it was the
    same mesh -- but six published numbers were wrong, the strings never appeared in either
    evidence file, and NOTHING gated the split, which is critic pass 2's C4-2.  The claim
    "it now reads as a log" is the most player-visible thing in the revision, so it is now
    asserted here, against the ``count`` attributes the DAE states about itself.

    What matters is not an exact number (a decimator may move it) but the SHAPE of the
    partition: bark dominant, hewn confined to the drivable face, end grain on the two caps
    only -- and the geometric claim behind it, that every triangle below the deck plane on
    either flank wears bark.
    """

    path = LEVEL_ROOT / ps.shape_relative("bench_log")
    root = ET.parse(path).getroot()
    geom = _bench_geometry()
    split: dict[str, dict[str, int]] = {}
    for geometry in root.findall("c:library_geometries/c:geometry", COLLADA):
        name = geometry.get("name") or geometry.get("id") or ""
        rows = {}
        for tset in geometry.findall("c:mesh/c:triangles", COLLADA):
            material = (tset.get("material") or "").rsplit("p_bench_", 1)[-1]
            rows[material.replace("-material", "")] = int(tset.get("count") or 0)
        split[name] = rows
    a700 = next(v for k, v in split.items() if k.endswith("_a700"))
    assert set(a700) == {"bark", "hewn", "endgrain"}, a700
    total = sum(a700.values())
    # r1 shipped 2.2 % bark on this mesh.  The bar is a coarse net -- the load-bearing
    # assertion is the geometric one below, that no hewn triangle lies outside the drivable
    # band -- so it is set where it separates "a log" from "a sawn wedge" and no finer.
    assert a700["bark"] / total >= 0.60, a700
    assert a700["hewn"] >= 200, a700
    assert 40 <= a700["endgrain"] <= 200, a700
    # r1 shipped 128 bark / 5,688 hewn: the belly and both flanks wore sawn timber, which is
    # why the r1 critic saw "a grey ridged wedge with no bark flank" from 27-130 m.
    assert a700["hewn"] / total <= 0.40, a700
    # every LOD carries all three, or the log changes species as you drive away from it
    for name, rows in split.items():
        if name.startswith("Colmesh_"):
            continue
        assert set(rows) == {"bark", "hewn", "endgrain"}, (name, rows)
        assert rows["bark"] > rows["hewn"], (name, rows)

    # and the geometry behind the claim: no HEWN triangle lies outside the drivable band or
    # below the deck plane, so the belly, both flanks and the descent's taper are all bark
    meshes = _dae_triangles(path)
    verts, _faces = meshes[next(k for k in meshes if k.endswith("_a700"))]
    hewn = _material_triangles(root, "hewn")
    corners = verts[hewn]
    assert len(hewn) == a700["hewn"], (len(hewn), a700)
    assert np.abs(corners[:, :, 1]).max() <= geom["deck_flat_half"] + 1e-6, (
        float(np.abs(corners[:, :, 1]).max()),
        "hewn timber is on the flank",
    )
    # every hewn vertex sits ON the drivable surface, so none of it is on the belly, the
    # arrises or the descent's taper.  0.15 m of slack is the terrain's own cross-slope,
    # which the ramp's toe and the crown's foot conform to over their eases.
    at = _bench_profile(geom)
    flat = corners.reshape(-1, 3)
    off = np.asarray([abs(float(z) - at(float(x))) for x, _y, z in flat])
    assert off.max() <= 0.15, (float(off.max()), "hewn timber is off the drivable surface")


def _material_triangles(root: ET.Element, material: str) -> np.ndarray:
    """Vertex indices of the a700's triangles bound to the named bench material."""

    for geometry in root.findall("c:library_geometries/c:geometry", COLLADA):
        if not (geometry.get("name") or "").endswith("_a700"):
            continue
        for tset in geometry.findall("c:mesh/c:triangles", COLLADA):
            if material not in (tset.get("material") or ""):
                continue
            inputs = tset.findall("c:input", COLLADA)
            stride = max(int(i.get("offset") or 0) for i in inputs) + 1
            vertex = next(i for i in inputs if i.get("semantic") == "VERTEX")
            offset = int(vertex.get("offset") or 0)
            payload = tset.find("c:p", COLLADA)
            index = np.asarray([int(v) for v in (payload.text or "").split()], dtype=np.int64)
            return index.reshape(-1, 3, stride)[:, :, offset]
    raise AssertionError(material)


def _terrain_local(x_local: float) -> float:
    """Terrain height at a centre-line station, in the bench log's own datum."""

    origin, along, _ = _bench_frame()
    point = origin + along * x_local
    return float(terrain.surface_z(*point)) - _origin_z()


def test_bench_collider_never_outreaches_its_visual() -> None:
    """AGENTS.md: a collision plate that outreaches its visual is an invisible shelf.

    r2 gated this on the two bounding boxes, and critic pass 2 (N6) then found the collider
    riding **+8.02 mm above** the visual through the descent's foot -- a bounding box cannot
    see that.  r3 casts a grid of rays at BOTH meshes and compares the surfaces themselves,
    which is the measurement the claim was always making.  The collider is now the visual's
    own stations at 6 points a side instead of 12, and it is not decimated at all.
    """

    meshes = _dae_vertices(LEVEL_ROOT / ps.shape_relative("bench_log"))
    visual = next(v for k, v in meshes.items() if k.endswith("_a700"))
    collider = next(v for k, v in meshes.items() if k.startswith("Colmesh_"))
    assert collider[:, 1].min() >= visual[:, 1].min() - 1e-6
    assert collider[:, 1].max() <= visual[:, 1].max() + 1e-6
    assert collider[:, 0].min() >= visual[:, 0].min() - 1e-6
    assert collider[:, 0].max() <= visual[:, 0].max() + 1e-6
    assert collider[:, 2].max() <= visual[:, 2].max() + 1e-6

    tris = _dae_triangles(LEVEL_ROOT / ps.shape_relative("bench_log"))
    vis = next(v for k, v in tris.items() if k.endswith("_a700"))
    col = next(v for k, v in tris.items() if k.startswith("Colmesh_"))
    geom = _bench_geometry()
    worst, where = -9.9, None
    for x in np.arange(geom["toe_x"] + 0.2, geom["break_x"], 0.4):
        for y in np.arange(-3.45, 3.46, 0.15):
            a = _ray_top(*vis, [float(x)], float(y))
            c = _ray_top(*col, [float(x)], float(y))
            if not a or not c:
                continue
            delta = next(iter(c.values())) - next(iter(a.values()))
            if delta > worst:
                worst, where = delta, (round(float(x), 2), round(float(y), 2))
    # 1 mm: the exporter quantises to 1e-5 m and the two meshes differ only ACROSS the
    # section, where the terrain's cross-slope through the crown is chorded 4 ways vs 8.
    assert worst <= 0.001, (worst, where)


def _dae_triangles(path: Path) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """(vertices, triangle vertex indices) per geometry, so face WINDING can be judged."""

    root = ET.parse(path).getroot()
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for geometry in root.findall("c:library_geometries/c:geometry", COLLADA):
        name = geometry.get("name") or geometry.get("id") or ""
        mesh = geometry.find("c:mesh", COLLADA)
        if mesh is None:
            continue
        source = mesh.find("c:source/c:float_array", COLLADA)
        if source is None or not source.text:
            continue
        verts = np.asarray([float(v) for v in source.text.split()], dtype=np.float64).reshape(-1, 3)
        blocks = []
        for tset in mesh.findall("c:triangles", COLLADA):
            inputs = tset.findall("c:input", COLLADA)
            stride = max(int(i.get("offset") or 0) for i in inputs) + 1
            vertex = [i for i in inputs if i.get("semantic") == "VERTEX"]
            payload = tset.find("c:p", COLLADA)
            if not vertex or payload is None or not payload.text:
                continue
            offset = int(vertex[0].get("offset") or 0)
            index = np.asarray([int(v) for v in payload.text.split()], dtype=np.int64)
            blocks.append(index.reshape(-1, 3, stride)[:, :, offset])
        if blocks:
            out[name] = (verts, np.concatenate(blocks))
    return out


def _signed_volume(verts: np.ndarray, tris: np.ndarray) -> tuple[float, np.ndarray]:
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    normals = np.cross(b - a, c - a)
    return float(np.einsum("ij,ij->i", a, normals).sum() / 6.0), normals


def test_every_prop_shape_has_outward_faces_and_the_deck_points_up() -> None:
    """The inside-out law, gated.

    B3 r5 paid a boot for a Colmesh cone wound inside out; B4 boot 1 paid another for the
    bench log's cross-section written as ``top - depth * (1 - sqrt(1 - a^2))`` instead of
    ``top - depth * sqrt(1 - a^2)``.  That single sign turned the belly into a ridge 0.30 m
    under the deck AND left every deck face back-facing, so ``castRayStatic`` passed straight
    through the deck (104.706 read against 105.006 authored) and a car put on the deck rested
    inside the shell.  Neither the tri budget, the node tree, the material set nor the profile
    check saw it -- the vertices were all in the right place.  Signed volume and the deck's
    own face normals do see it.
    """

    deck_total: dict[str, int] = {}
    for key in ps.SHAPES:
        for name, (verts, tris) in _dae_triangles(LEVEL_ROOT / ps.shape_relative(key)).items():
            volume, normals = _signed_volume(verts, tris)
            assert volume > 0.0, (key, name, volume)
            if key != "bench_log":
                continue
            deck = np.all(verts[tris][:, :, 2] > ps.BENCH["deck_lift_m"] - 0.01, axis=1)
            # the plateau is 54.8 m now that the last 16 m descend, and the a80 LOD spans it
            # in three 18 m bands, so the guard is per-LOD rather than one number for all six.
            floor = 3 if "a80" in name else (6 if "a250" in name else 20)
            assert deck.sum() >= floor, (name, int(deck.sum()))
            assert (normals[deck][:, 2] > 0).all(), (name, int((normals[deck][:, 2] <= 0).sum()))
            deck_total[name] = int(deck.sum())
    assert sum(deck_total.values()) > 100, deck_total


def test_every_b4_shape_is_a_closed_solid_at_every_detail_and_in_its_collider() -> None:
    """G-B4-16 (r4): complete 3D geometry -- no B4 shape is a facade, at any detail.

    USER REQUIREMENT, 2026-09-07, binding on every round: *"the rocks, boulder and mountain
    aren't just facade, but have complete 3D geometry."*  The orchestrator's probe found the
    backdrop ring to be an open shell with 9,216 boundary edges and, among B4's shapes, the
    giant lantern carrying two non-manifold edges (two bail shells welded onto one hub).
    This gate runs ``mesh_audit`` -- the same module the round's instrument
    (``b4/r4/instruments/manifold_r4.py``) writes its table from -- over every geometry in
    every B4 DAE: the three details AND the Colmesh.  Each must be SOLID: zero boundary
    edges, zero non-manifold edges, zero misoriented edges (every edge walked once each way,
    so the shell is consistently wound), zero pinch vertices (the exporter welds coincident
    vertices, so two shells sharing a hub point become one shell pinched at a vertex),
    positive signed volume (wound outward), an underside, and every shell an orientable
    closed surface (Euler characteristic even and <= 2: 2 for a boulder, 0 for a rope band,
    -2 for the pot body with its two handle holes).

    What that caught in r4, all fixed in ``blender_props.py``: the bench log's two end caps
    wound against its reversed loft (60 misoriented edges on the collider, invisible at
    ground level), the tripod's three lashing bands each pinched at a welded cap hub, the
    tripod collider's three poles welded into one shell at the apex, and the lantern post's
    bracket sharing a hub with the post.  The last block proves the instrument can FAIL:
    one deleted triangle and one flipped triangle are each caught on the smallest collider.
    """

    from examples.hot_potato_arena.level import mesh_audit

    report = {}
    for key in ps.SHAPES:
        path = LEVEL_ROOT / ps.shape_relative(key)
        row = mesh_audit.audit_dae(path.name, path.read_bytes())
        assert row["has_colmesh"], key
        names = set(row["meshes"])
        for pixel in ps.DETAILS:
            assert any(n.endswith(f"_a{pixel}") or n.startswith("Cube") for n in names), (
                key,
                pixel,
            )
        assert len(row["meshes"]) == len(ps.DETAILS) + 1, (key, sorted(names))
        for gid, mesh in row["meshes"].items():
            assert mesh["verdict"] == "SOLID", (
                key,
                gid,
                {k: mesh[k] for k in ("boundary", "nonmanifold", "misoriented", "bowtie_verts")},
                mesh["shells"],
            )
        report[key] = row["all_solid"]
    assert all(report.values()), report
    # the instrument can fail: take the smallest collider and break it two ways
    rail = mesh_audit.geometries((LEVEL_ROOT / ps.shape_relative("fence_rail")).read_bytes())
    positions, tris = next(v for k, v in rail.items() if k.startswith("Colmesh_"))
    assert mesh_audit.audit(positions, tris)["verdict"] == "SOLID"
    holed = mesh_audit.audit(positions, tris[1:])
    assert holed["verdict"] == "OPEN" and holed["boundary"] == 3, holed
    a, b, c = tris[0]
    flipped = mesh_audit.audit(positions, [(a, c, b), *tris[1:]])
    assert flipped["verdict"] == "OPEN" and flipped["misoriented"] == 3, flipped


#: the one prop a car cannot reach: the hurricane lantern hangs from the tripod's hook at
#: +46 m, so its base is 30 m above the meadow.  Its collider is an 8-sided prism round a
#: waisted body (fount, globe cage, cap) and reads 0.27 m p90 -- gated loosely, and named.
HUNG_PROPS = frozenset({"giant_lantern"})
#: the shapes the adopted volume-ratio bar applies to: the rock-class prop (the cairn) and the
#: four logs, every one a solid body.  A hollow pot or a box round a post reads a low ratio
#: for an honest reason and is held to the phantom-gap bar instead.
SOLID_BODY_PROPS = frozenset({"trail_cairn", "bench_log", "log_north", "log_south", "leaner_log"})
COLLIDER_PHANTOM_BARS_M = {"p50": 0.06, "p90": 0.12, "max": 0.25}


def test_no_b4_collider_stands_proud_of_its_visual_where_a_car_can_reach() -> None:
    """G-B4-17 (r4): the thin-shell gate critic B2 pass 5 adopted, run over every B4 shape.

    ``level_facts`` (2026-09-07): a watertight shell can still be a facade if its collision
    mesh stands metres in front of it -- ``h_rock_face_01``'s convex-hull Colmesh put an
    invisible wall a median 3.5 m (max 14.7 m) before the visible rock.  GATE, adopted for
    every rock-class shape: visual / Colmesh volume >= 0.5, LOD parity, and a phantom-gap
    statistic (p50 / p90 / max).  B4 was told to prove its props pass it.

    ``collider_probe`` (the module this gate imports, and the module the round's instrument
    writes ``b4/r4/collider_probe_r4.json`` from) casts a horizontal fan at car heights from
    outside each shape and, for every ray the collider stops before anything visible, reads
    the PERPENDICULAR distance from that collider hit to the visual surface.  The bars are
    0.06 / 0.12 / 0.25 m: a quarter of a metre is under the 0.30-0.34 m kerb height this
    round proved trips a car, and an order of magnitude under the hearth's 3.5 m median.

    What it caught in r4, all fixed in ``blender_props.py`` before the certified cut: the
    pot's collider was a cylinder 4.4 m TALLER than the pot round a belly that curves in
    (p90 1.01 m, max 2.10 m at the foot); the trail sign's and the lantern post's were
    full-height boxes round 0.075-0.10 m posts (p90 1.00 m); the three round logs' were
    straight full-radius prisms on logs that taper 16-18 % (0.5 m proud at every end).
    The last block proves the instrument can FAIL: a collider pushed 1 m out reads 1 m.
    """

    from examples.hot_potato_arena.level import collider_probe

    report = {}
    for key in ps.SHAPES:
        path = LEVEL_ROOT / ps.shape_relative(key)
        row = collider_probe.probe_dae(path.name, path.read_bytes())
        assert row["has_colmesh"], key
        assert len(row["details"]) == len(ps.DETAILS), (key, sorted(row["details"]))
        # LOD parity: every detail encloses about the same volume against the one collider
        assert row["lod_parity_ratio_spread"] <= 0.30, (key, row["lod_parity_ratio_spread"])
        if key in SOLID_BODY_PROPS:
            assert row["volume_ratio_min"] >= 0.5, (key, row["volume_ratio_min"])
        finest = row["details"][row["finest_detail"]]["car_band"]
        thin = {k: v for k, v in finest.items() if k != "worst_rays"}
        report[key] = thin
        if key in HUNG_PROPS:
            assert row["volume_ratio_min"] >= 0.5, (key, row["volume_ratio_min"])
            assert finest["phantom_max_m"] <= 0.50, (key, thin)
            continue
        assert finest["collider_first"] > 0, (key, thin)
        assert finest["phantom_p50_m"] <= COLLIDER_PHANTOM_BARS_M["p50"], (key, thin)
        assert finest["phantom_p90_m"] <= COLLIDER_PHANTOM_BARS_M["p90"], (key, thin)
        assert finest["phantom_max_m"] <= COLLIDER_PHANTOM_BARS_M["max"], (
            key,
            thin,
            finest["worst_rays"],
        )
    assert len(report) == len(ps.SHAPES), sorted(report)
    # the instrument can fail: push the fence post's own box collider 1.0 m out on every
    # side and the phantom must read a metre, not zero
    from examples.hot_potato_arena.level import mesh_audit

    geoms = mesh_audit.geometries((LEVEL_ROOT / ps.shape_relative("fence_post")).read_bytes())
    col_name = next(g for g in geoms if g.startswith("Colmesh_"))
    vis_name = max((g for g in geoms if g != col_name), key=lambda g: len(geoms[g][1]))
    col_verts, col_faces = collider_probe._arrays(*geoms[col_name])
    vis_verts, vis_faces = collider_probe._arrays(*geoms[vis_name])
    proud = col_verts.copy()
    proud[:, :2] += np.sign(proud[:, :2]) * 1.0
    origins, directions, _meta = collider_probe.car_band_rays(proud)
    broken = collider_probe.gap_statistics(
        origins, directions, (vis_verts, vis_faces), (proud, col_faces)
    )
    assert broken["phantom_p50_m"] >= 0.9, broken
    assert broken["phantom_max_m"] > COLLIDER_PHANTOM_BARS_M["max"], broken
    honest = collider_probe.gap_statistics(
        *collider_probe.car_band_rays(col_verts)[:2], (vis_verts, vis_faces), (col_verts, col_faces)
    )
    assert honest["phantom_max_m"] <= COLLIDER_PHANTOM_BARS_M["max"], honest


# --------------------------------------------------------------------------- G-B4-4
def _built_solids() -> tuple[np.ndarray, list[str], np.ndarray]:
    """Every object a car can meet outside the pan, AS BUILT: hearth, forest, props.

    r1 gave EVERY forest instance a flat 1.0 m radius, which is wrong in both directions --
    a ``pebble_cluster`` is not a 1 m obstacle and a ``cliff_outcrop`` is 8 m of one.  The
    radii here are B3's own ``forest_spec.SPECIES`` values times each instance's own
    ``scale``, and the ``stops_a_car`` flag is B3's own ``colmesh``: a species with
    ``colmesh == 0`` is drive-through BY DESIGN (every shrub, fern, reed, bark-debris and
    branch-pile row), so it is counted in the census and excluded from the runoff bar.
    """

    circles: list[tuple[float, float, float]] = []
    labels: list[str] = []
    solid: list[bool] = []
    stones = {row["name"]: row for row in ps.design_layout()["stones"]}
    for group in (
        f"{ps.LEVEL_ID}_hearth",
        f"{ps.LEVEL_ID}_props",
    ):
        for record in _jsonl(LEVEL_ROOT / f"main/MissionGroup/{group}/items.level.json"):
            if record.get("class") not in ("TSStatic", "Prefab"):
                continue
            x, y = float(record["position"][0]), float(record["position"][1])
            name = record.get("name", "")
            stem = name.replace(f"{ps.LEVEL_ID}_", "")
            radius = 2.0
            if stem in stones:
                radius = float(stones[stem]["diam"]) / 2.0
            elif "crust" in stem:
                continue  # a flat decal plate on the slab, not a solid
            elif "fence" in stem or "cairn" in stem or "sign" in stem or "post" in stem:
                radius = 1.0
            elif record.get("class") == "Prefab":
                radius = 3.0
            circles.append((x, y, radius))
            labels.append(name)
            solid.append(True)
    prefix = f"{ps.LEVEL_ID}_f_"
    forest_dir = LEVEL_ROOT / "forest"
    for path in sorted(forest_dir.glob("*.forest4.json")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            species = fs.SPECIES_BY_KEY.get(str(row["type"]).removeprefix(prefix))
            scale = float(row.get("scale", 1.0))
            radius = float(species["radius"]) * scale if species else 1.0
            circles.append((float(row["pos"][0]), float(row["pos"][1]), radius))
            labels.append(row["type"])
            solid.append(bool(species is None or int(species["colmesh"]) > 0))
    return (
        np.asarray(circles, dtype=np.float64),
        labels,
        np.asarray(solid, dtype=bool),
    )


def _runoff(origin, heading_xy, circles, labels, mask=None, max_d=400.0):
    """Distance from ``origin`` along ``heading_xy`` to the first object's FACE.

    r1 returned ``along[index]`` -- the distance to the blocker's CENTRE -- and called the
    result "runoff to the first solid".  A 3.8 m boulder's face is 3.8 m nearer than that.
    The corridor is |perp| <= SWEEP_HALF_W; an object of radius r at (a, p) first enters it
    at ``a - sqrt(r^2 - d^2)`` with ``d = max(0, |p| - SWEEP_HALF_W)``, which is the number
    a driver actually has.  ``mask`` selects which objects count (see ``_built_solids``).
    """

    ox, oy = origin
    hx, hy = heading_xy
    dx = circles[:, 0] - ox
    dy = circles[:, 1] - oy
    along = dx * hx + dy * hy
    perp = np.abs(-dx * hy + dy * hx)
    gap = np.maximum(0.0, perp - SWEEP_HALF_W)
    reach = np.sqrt(np.maximum(0.0, circles[:, 2] ** 2 - gap**2))
    face = along - reach
    hit = (face > 1.0) & (face < max_d) & (gap < circles[:, 2])
    if mask is not None:
        hit &= mask
    if not hit.any():
        return max_d, None
    index = int(np.argmin(np.where(hit, face, np.inf)))
    return float(face[index]), labels[index]


def bench_exit_runoffs() -> dict[str, dict]:
    """Face-to-face runoff off all four bench exits, solids-only and any-object."""

    circles, labels, solid = _built_solids()
    geom = _bench_geometry()
    origin, along, across = _bench_frame()
    centre = np.asarray(ps.CENTER[:2])
    at = _bench_profile(geom)
    exits = {}
    # r3: the log SNAPS at ``break_x``, so the west exit's launch point is the break face,
    # 2.44 m closer to the ring than r2's virtual foot at x_local +50
    west = origin + along * geom["break_x"]
    exits["west_crown_exit"] = (west, along, "off the snapped crown's break face")
    toe = origin + along * geom["toe_x"]
    exits["ramp_foot"] = (toe, -along, "off the wedge's toe, outward")
    tables: dict[str, list[dict]] = {}
    for side, name in ((1.0, "inner_flank_drop"), (-1.0, "outer_flank_drop")):
        worst = None
        rows = []
        for k in range(41):
            x = geom["join_x"] + (geom["break_x"] - geom["join_x"]) * k / 40.0
            half_w = _bench_half_width(geom, x)
            point = origin + along * x + across * side * (half_w + 0.5)
            direction = centre - point
            norm = float(np.hypot(*direction)) or 1.0
            direction = direction / norm
            if side < 0:
                direction = -direction
            distance, blocker = _runoff(point, direction, circles, labels, solid)
            # the drop the flank actually offers at this station, over the terrain beside it
            drop = at(x) + _origin_z() - float(terrain.surface_z(*point))
            row = {
                "x_local": round(x, 2),
                "drop_m": round(drop, 3),
                "runoff_m": round(distance, 1),
                "blocker": blocker,
                "is_a_drop": bool(drop >= FLANK_DROP_MIN_M),
            }
            rows.append(row)
            if row["is_a_drop"] and (worst is None or distance < worst[0]):
                worst = (distance, blocker, point, direction, x)
        tables[name] = rows
        exits[name] = (
            worst[2],
            worst[3],
            f"worst of the stations whose flank drop is >= {FLANK_DROP_MIN_M} m "
            f"(x_local {worst[4]:.2f}, {worst[1]})",
        )
    report: dict[str, dict] = {}
    for name, (point, direction, note) in exits.items():
        solid_m, solid_hit = _runoff(point, direction, circles, labels, solid)
        any_m, any_hit = _runoff(point, direction, circles, labels, None)
        centre_along = _runoff_to_centre(point, direction, circles, labels, solid)
        report[name] = {
            "face_to_first_solid_m": round(solid_m, 1),
            "first_solid": solid_hit,
            "face_to_first_object_m": round(any_m, 1),
            "first_object": any_hit,
            "centre_of_first_solid_m": round(centre_along[0], 1),
            "note": note,
            "heading_deg": round(math.degrees(math.atan2(direction[0], direction[1])) % 360.0, 1),
        }
        if name in tables:
            report[name]["stations"] = tables[name]
            report[name]["worst_over_every_station_m"] = round(
                min(r["runoff_m"] for r in tables[name]), 1
            )
    return report


def _runoff_to_centre(origin, heading_xy, circles, labels, mask=None, max_d=400.0):
    """r1's convention, kept so the two readings can be published side by side."""

    ox, oy = origin
    hx, hy = heading_xy
    dx = circles[:, 0] - ox
    dy = circles[:, 1] - oy
    along = dx * hx + dy * hy
    perp = np.abs(-dx * hy + dy * hx)
    hit = (along > 1.0) & (along < max_d) & (perp <= SWEEP_HALF_W + circles[:, 2])
    if mask is not None:
        hit &= mask
    if not hit.any():
        return max_d, None
    index = int(np.argmin(np.where(hit, along, np.inf)))
    return float(along[index]), labels[index]


def test_bench_four_exits_have_fifty_metres_of_runoff_against_the_built_world() -> None:
    """G-B4-4: the ramp, the crown and BOTH flanks, each >= 50 m to the first solid's FACE.

    The bar is measured FACE to face against B3's own per-species radii and only against
    objects B3 gives a Colmesh -- see ``_built_solids`` and ``_runoff`` for why r1's
    centre-distance-against-a-flat-1-m-radius reading was two different mistakes.

    r4: the two flanks are WALLED (G-B4-13) and are no longer exits.  Their rows are kept
    and still gated, because the runoff beyond a flank is what a car has if it ever does
    clear the wall -- the world around the log did not change when the log did, and a bar
    that quietly stops being measured is how a later placement round would put a boulder
    5 m off the flank without anything failing.
    """

    report = bench_exit_runoffs()
    assert len(report) == 4, report
    assert all(row["face_to_first_solid_m"] >= RUNOFF_MIN_M for row in report.values()), report
    # and the bar holds at EVERY flank station, not only the ones classed as drops
    for name, row in report.items():
        if "worst_over_every_station_m" in row:
            assert row["worst_over_every_station_m"] >= RUNOFF_MIN_M, (name, row)


def test_the_shared_scene_files_still_carry_every_round_s_content() -> None:
    """G-B4-11 (r2): a shared file that is PRESENT but EMPTIED is the defect r1 shipped.

    ``level_writer.render_level`` used to emit ``main.decals.json`` with ``instances: {}``,
    which deletes B2's 619 hearth-dressing rows on every re-render; B4 r1 cut and booted a
    tree three minutes after another round's render had done exactly that, and the certified
    zip shipped ZERO static decals while every gate passed -- ``cut_b4.py`` asserts membership
    at FILE level and cannot see a file that is there and empty.  level_facts' remedy is
    "every round must assert its own groups are present in the tree it cuts"; this is B4's
    share of it, and it covers the neighbours too, because the failure was never B4's own
    file.
    """

    decals = json.loads((LEVEL_ROOT / "main.decals.json").read_text(encoding="utf-8"))
    instances = decals.get("instances") or {}
    rows = {key: len(value) for key, value in instances.items()}
    assert sum(rows.values()) >= 600, rows
    assert len(rows) >= 12, rows
    forest = sorted((LEVEL_ROOT / "forest").glob("*.forest4.json"))
    planted = sum(
        1 for path in forest for line in path.read_text(encoding="utf-8").splitlines() if line
    )
    assert planted > 100_000, planted
    hearth = _jsonl(LEVEL_ROOT / f"main/MissionGroup/{ps.LEVEL_ID}_hearth/items.level.json")
    assert len(hearth) >= 50, len(hearth)
    assert len(_props_records()) >= 100, len(_props_records())


def test_the_inner_and_outer_flanks_are_named_the_way_the_hearth_lies() -> None:
    """G-B4-10 (r2): the flank labels, and the headings the live gate drives, are not swapped.

    ``ps.heading_vector(h) = (sin h, cos h)``, so the compass heading that drives along the
    bench's local +y axis (``across = [-along.y, along.x]``) is ``along_heading - 90``.  B4 r1's
    live gate wrote the INNER flank as ``30 + 90 * inner_sign`` = 120 deg, which is -across --
    away from the hearth -- so for the whole round the two flank rows were published against
    each other's runoff and drop numbers.  This pins the convention in a static gate so a
    future edit cannot swap them again silently.
    """

    origin, _along, across = _bench_frame()
    row = ps.log_row("bench_log")
    along_heading = float(row["heading_along_decreasing_bearing"])
    assert np.allclose(ps.heading_vector((along_heading - 90.0) % 360.0), across, atol=1e-9)
    inner = np.asarray(ps.CENTER[:2]) - origin
    inner = inner / float(np.hypot(*inner))
    inner_sign = 1.0 if float(np.dot(inner, across)) > 0 else -1.0
    inner_heading = ((along_heading - 90.0) + (0.0 if inner_sign > 0 else 180.0)) % 360.0
    outer_heading = (inner_heading + 180.0) % 360.0
    assert float(np.dot(np.asarray(ps.heading_vector(inner_heading)), inner)) > 0.9
    assert float(np.dot(np.asarray(ps.heading_vector(outer_heading)), inner)) < -0.9
    # and the static runoff table agrees with those headings.  r2 allowed 12 deg, which
    # catches the 180 deg swap it was written for but would let a 10 deg drift through
    # silently (critic pass 2, N5).  The runoff sweep aims each flank station at the ring's
    # CENTRE, not along the across axis, so the two differ by the angle the station subtends
    # -- bounded by atan(half the log's length / the distance to the centre) = atan(50 / 447)
    # = 6.4 deg at the very ends.  8 deg is that bound plus a degree, and it is derived
    # rather than chosen.
    report = bench_exit_runoffs()
    subtended = math.degrees(math.atan2(ps.BENCH["length_m"] / 2.0, 447.0))
    assert subtended < 7.0, subtended
    assert abs(report["inner_flank_drop"]["heading_deg"] - inner_heading) < 8.0, report
    assert abs(report["outer_flank_drop"]["heading_deg"] - outer_heading) < 8.0, report


# --------------------------------------------------------------------------- G-B4-5
def test_every_placed_prop_sits_at_its_authored_height_over_the_shipped_terrain() -> None:
    """G-B4-5: statics carry their authored offset; nothing floats or is buried by accident."""

    expected = {
        f"{ps.LEVEL_ID}_giant_lantern": 46.0,
        f"{ps.LEVEL_ID}_trail_cairn_0": -0.12,
        f"{ps.LEVEL_ID}_trail_cairn_1": -0.12,
    }
    bad = []
    for record in _props_records():
        if record.get("class") != "TSStatic":
            continue
        x, y, z = (float(c) for c in record["position"])
        ground = float(terrain.surface_z(x, y))
        offset = expected.get(record["name"], 0.0)
        if record["name"].startswith(f"{ps.LEVEL_ID}_fence_rail_"):
            continue  # rails hang between two posts, not on the ground under their midpoint
        if abs((z - ground) - offset) > 0.02:
            bad.append((record["name"], round(z - ground, 3), offset))
    assert not bad, bad


def test_prefab_instances_sit_on_the_terrain_and_are_tilted_to_it() -> None:
    manifest = props_build.place_manifest()
    bad = []
    for record in _props_records():
        if record.get("class") != "Prefab":
            continue
        x, y, z = (float(c) for c in record["position"])
        if abs(z - float(terrain.surface_z(x, y))) > 0.02:
            bad.append((record["name"], z))
        rows = np.asarray(record["rotationMatrix"], dtype=np.float64).reshape(3, 3)
        assert np.allclose(rows @ rows.T, np.eye(3), atol=1e-5), record["name"]
        assert rows[2, 2] >= math.cos(math.radians(20.5)), record["name"]
    assert not bad, bad[:5]
    assert manifest["prefab_instances"] == sum(
        1 for r in _props_records() if r.get("class") == "Prefab"
    )


# --------------------------------------------------------------------------- G-B4-6/7
def _road_records() -> list[dict]:
    return _jsonl(LEVEL_ROOT / "main/MissionGroup/decal_road/items.level.json") + _jsonl(
        LEVEL_ROOT / "main/MissionGroup/AIDecalWaypointsGroup/items.level.json"
    )


def test_the_decal_stack_carries_the_studys_measured_per_family_values() -> None:
    """G-B4-6: every visible layer's fields equal ``props_spec.ROAD_STACK``.

    ROAD_STACK is design §2.3.1 transcribed, with ONE measured deviation recorded there and
    in §9: the SURFACE layer's ``textureLength`` is 32, not 128, because 128 stretches a
    2048 square 16:1 along the 8 m track and 21:1 along the 6 m trail, and a census of
    39,251 visible stock DecalRoads puts the surface-class median at 4:1 and the 95th
    percentile at 15:1.  The gate compares the shipped records against the table, so the
    table and the tree cannot drift apart.
    """

    counts: Counter[str] = Counter()
    bad = []
    for record in _road_records():
        material = str(record["material"]).replace(f"{ps.LEVEL_ID}_", "")
        counts[material] += 1
        if material not in ps.ROAD_STACK:
            continue
        row = ps.ROAD_STACK[material]
        if record["textureLength"] != row["textureLength"]:
            bad.append((record["name"], "textureLength", record["textureLength"]))
        if list(record["distanceFade"]) != list(row["distanceFade"]):
            bad.append((record["name"], "distanceFade", record["distanceFade"]))
        if record["renderPriority"] != row["renderPriority"]:
            bad.append((record["name"], "renderPriority", record["renderPriority"]))
        want_fade = list(row["startEndFade"])
        if re.search(r"_track_.*_[ab]$", record["name"]):
            want_fade = [0.0, 0.0]  # the split arcs butt into each other; see level_writer
        if list(record["startEndFade"]) != want_fade:
            bad.append((record["name"], "startEndFade", record["startEndFade"]))
        driv = row["drivability"]
        if isinstance(driv, dict):
            driv = driv["track"] if "track" in record["name"] else driv["trail"]
        if record["drivability"] != driv:
            bad.append((record["name"], "drivability", record["drivability"]))
    assert not bad, bad[:8]
    # +1 record for every track layer that used to be one closed loop and now ships as two
    # open arcs (level_writer._split_closed_loop): surface, both ruts, both verges, the dust.
    split_extra = {
        # +1 for the track's split, +1 for the approach to the road up the canyon wall (A6)
        "m_dirt_variation": 2,
        "m_dirt_tiretracks": 1,
        "m_bank_erosion": 2,
        "m_track_dust_overlay": 1,
    }
    for material, row in ps.ROAD_STACK.items():
        want = row["records"] + split_extra.get(material, 0)
        assert counts[material] == want, (material, counts[material], want)


def test_no_visible_road_is_closed_by_repeating_its_first_node() -> None:
    """B4's fix for the decal-batcher E line, gated so it cannot come back.

    A census of the 44,521 DecalRoads in the shipped stock levels found seven whose first
    node equals their last, and every one of them is a degenerate 2-node record: no stock
    level closes a loop by repeating node 0, while johnson_valley ships a 3,610.8 m open
    VISIBLE road (scratchpad/level_round/b4/census_stock_roads.py).  The
    engine's ``SceneStaticDecalRoadManager`` reported an INFINITE node AABB for exactly the
    closed, visible road (``leaf origin=(-inf, -inf, -inf)``).  Invisible AI roads are not in
    that batcher and are exempt.
    """

    offenders = []
    for record in _road_records():
        nodes = record["nodes"]
        if nodes[0][:3] != nodes[-1][:3]:
            continue
        if str(record["material"]).endswith("road_invisible"):
            continue
        offenders.append(record["name"])
    assert not offenders, offenders


def test_the_two_dirt_surface_families_are_drawn_linear() -> None:
    """The decal-batcher E line, closed by measurement and gated so it cannot come back.

    Two cuts of the SAME tree, differing only in ``improvedSpline`` on the three
    ``m_dirt_variation`` roads, booted back to back on the sentinel:

      * ``improvedSpline true``  -> known_decal_batcher_errors 1, 18 E lines (cut 3d956607)
      * ``improvedSpline false`` -> known_decal_batcher_errors 0, 16 E lines (cut cb4e807d)

    Every other visible road keeps the improved spline and none of them logs the line, so the
    gate is deliberately narrow: it pins the two families the A/B actually covered.
    """

    linear, spline = [], []
    for record in _road_records():
        if str(record["material"]).endswith("m_dirt_variation"):
            (linear if not record["improvedSpline"] else spline).append(record["name"])
    # the track's two halves, the trail, and (amendment A6) the approach to the canyon road
    assert len(linear) == 4, (linear, spline)
    assert not spline, spline
    others = [
        r["name"]
        for r in _road_records()
        if not str(r["material"]).endswith(("m_dirt_variation", "road_invisible"))
        and not r["improvedSpline"]
    ]
    assert not others, others


def test_no_road_has_a_zero_length_segment() -> None:
    """Two identical nodes in a row are a degenerate segment: normalise(0) is not a direction.

    This is the gate B4 boot 2 bought.  Splitting the closed loops removed ``first == last``
    but left arc b ending on a repeat of node 0, so the engine's static decal batcher still
    built an INFINITE node AABB and still logged
    ``packed position exceeded supported local range ... by inf m`` -- now naming
    ``track_surface_b`` at the identical world vertex.  Closure was never the disease; a
    zero-length segment was, and a first == last road makes one through the engine's own wrap.
    """

    worst = None
    for record in _road_records():
        nodes = record["nodes"]
        for index in range(len(nodes) - 1):
            gap = math.dist(nodes[index][:3], nodes[index + 1][:3])
            if worst is None or gap < worst[0]:
                worst = (gap, record["name"], index)
    assert worst is not None
    assert worst[0] > 0.01, worst


def test_every_road_node_lies_on_the_shipped_terrain() -> None:
    """G-B4-7: the drawn road follows the ground it was measured against.

    r4 (critic pass 3, N8): the bar was **0.60 m** against a published reading of **0.5 mm**,
    i.e. a hundred times looser than the thing it protects -- it would have passed a road
    floating 0.59 m off the ground, which is a road you can see daylight under.  B1's own
    copy of this gate carries 0.006; B4's should not have been the loose one.  The bar is now
    6 mm, which is one terrain height unit (4.88 mm) plus the placer's own rounding, so it
    fails on a real detachment and cannot fail on quantisation.
    """

    worst = 0.0
    where = None
    for record in _road_records():
        if str(record["material"]).endswith("road_invisible"):
            continue
        for node in record["nodes"]:
            x, y, z = float(node[0]), float(node[1]), float(node[2])
            ground = float(terrain.surface_z(x, y))
            if not np.isfinite(ground):
                continue
            if abs(z - ground) > worst:
                worst, where = abs(z - ground), (record["name"], x, y, round(z - ground, 3))
    assert worst <= 0.006, where


# --------------------------------------------------------------------------- G-B4-8
def test_prefab_clusters_have_the_designed_shape_and_every_member_resolves() -> None:
    manifest = props_build.place_manifest()
    assert set(manifest["clusters"]) == {c["key"] for c in ps.PREFAB_CLUSTERS}
    total = 0
    for cluster in ps.PREFAB_CLUSTERS:
        row = manifest["clusters"][cluster["key"]]
        assert row["members"] == cluster["members"], cluster["key"]
        assert row["instances"] <= cluster["instances"]
        total += row["statics"]
        prefab = LEVEL_ROOT / f"{ps.PREFAB_DIR}/{ps.LEVEL_ID}_{cluster['key']}.prefab"
        document = prefab.read_text(encoding="utf-8")
        assert document.count("new TSStatic()") == cluster["members"]
        assert 'groupPosition = "0.000000 0.000000 0.000000"' in document
        for shape in re.findall(r'shapeName = "([^"]+)"', document):
            assert (LEVEL_ROOT.parents[1] / shape).is_file(), shape
    assert total == manifest["prefab_statics"]
    assert total >= 4000, total


def test_every_prop_shape_reference_resolves_and_carries_a_colmesh() -> None:
    shapes = props_build.shapes_manifest()["shapes"]
    for key, row in shapes.items():
        path = LEVEL_ROOT / row["relative"]
        assert path.is_file(), key
        nodes = _dae_vertices(path)
        assert any(n.startswith("Colmesh_") for n in nodes), key
        assert row["tris"]["colmesh"] > 0, key
        for pixel in ps.DETAILS:
            assert row["tris"][f"a{pixel}"] <= ps.SHAPES[key]["budget"][pixel], (key, pixel)
        text = path.read_bytes()
        assert b"\r" not in text, key
        if ps.SHAPES[key].get("bb"):
            assert b"BB::DIM=128" in text, key
    for record in _props_records():
        if record.get("class") != "TSStatic":
            continue
        assert (LEVEL_ROOT.parents[1] / record["shapeName"].lstrip("/")).is_file(), record["name"]


# --------------------------------------------------------------------------- G-B4-9/10
def test_no_b4_name_collides_with_any_other_object_material_or_datablock() -> None:
    """SimObject names are global across classes (level_facts): one collision hides a set."""

    seen: dict[str, str] = {}
    collisions = []
    for path in sorted(LEVEL_ROOT.rglob("*.json")):
        if path.name.endswith(".forest4.json"):
            continue
        text = path.read_text(encoding="utf-8")
        records: list[dict] = []
        if path.name == "items.level.json":
            records = [json.loads(line) for line in text.splitlines() if line]
        else:
            try:
                document = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(document, dict):
                records = [v for v in document.values() if isinstance(v, dict) and "class" in v]
        for record in records:
            name = record.get("name")
            if not name:
                continue
            key = f"{record.get('class')}::{path.name}"
            if name in seen and seen[name] != key:
                collisions.append((name, seen[name], key))
            seen[name] = key
    assert not collisions, collisions[:6]


def test_b4_outputs_are_strict_json_lf_and_uuid5() -> None:
    from examples.hot_potato_arena.level import place_props as placer

    namespace = uuid.NAMESPACE_URL
    for record in _props_records():
        expected = str(uuid.uuid5(namespace, f"beamng-mcp/{ps.LEVEL_ID}/{record['name']}"))
        assert record["persistentId"] == expected, record["name"]
        assert record["name"].startswith(ps.LEVEL_ID), record["name"]
    for relative, payload in placer.rendered_outputs().items():
        assert b"\r" not in payload, relative
        on_disk = (LEVEL_ROOT / relative).read_bytes()
        assert on_disk == payload, relative


# --------------------------------------------------------------------------- G-B4-11
def test_prop_textures_are_powers_of_two_and_their_materials_agree_with_their_slots() -> None:
    from PIL import Image

    from examples.hot_potato_arena.level import prop_textures as pt

    manifest = props_build.textures_manifest()
    assert len(manifest["files"]) == 5 * len(ps.MATERIALS)
    for relative, row in manifest["files"].items():
        path = LEVEL_ROOT / relative
        assert path.is_file(), relative
        with Image.open(path) as image:
            width, height = image.size
        assert width == height == row["px"], relative
        assert width & (width - 1) == 0, (relative, width)
    document = json.loads(
        (LEVEL_ROOT / f"{ps.SHAPE_DIR}/{ps.LEVEL_ID}_props.materials.json").read_text(
            encoding="utf-8"
        )
    )
    assert document == pt.material_document()
    for name, material in document.items():
        # B1 r4's law: 1.5 is the PBR path, so every map must be in a v1.5 slot
        assert material["version"] == 1.5, name
        stage = material["Stages"][0]
        maps = {
            "baseColorMap",
            "normalMap",
            "roughnessMap",
            "ambientOcclusionMap",
            "opacityMap",
        }
        assert maps <= set(stage), (name, sorted(maps - set(stage)))
        extra = set(stage) - maps
        if extra:
            # only the stock v1.5 emissive block may add keys, and it must add ALL of them:
            # glow_city's powerglow_gridmap_a / ECUSA's trafficLight are the reference
            assert stage.get("emissive") is True, (name, sorted(extra))
            assert extra == {
                "emissive",
                "emissiveFactor",
                "emissiveIntensityNits",
                "emissiveMap",
                "pixelSpecular",
            }, (name, sorted(extra))
            assert stage["emissiveMap"] == stage["baseColorMap"], name
            assert material["castShadows"] is False, name
        for key, value in stage.items():
            if not key.endswith("Map"):
                continue
            assert (LEVEL_ROOT.parents[1] / value.lstrip("/")).is_file(), value


def test_cc0_provenance_covers_every_source_the_props_use() -> None:
    ledger = json.loads(
        (ps.EXAMPLE_ROOT / "authoring" / "cc0_provenance.json").read_text(encoding="utf-8")
    )
    assets = {row["asset"] for row in ledger["files"].values()}
    wanted = {recipe["source"] for recipe in ps.MATERIALS.values()}
    wanted |= {recipe["overlay"] for recipe in ps.MATERIALS.values() if recipe.get("overlay")}
    missing = wanted - assets
    assert not missing, missing
    assert "CC0" in ledger["license"]


# --------------------------------------------------------------------------- G-B4-12
def test_the_b4_tree_matches_its_manifests_byte_for_byte() -> None:
    problems = props_build.verify(LEVEL_ROOT)
    assert not problems["missing"], problems["missing"][:5]
    assert not problems["changed"], problems["changed"][:5]
    # r3: and every harvested engine bake still matches the DAE it was baked FROM.  The
    # engine prefers a `.cdae` over the `.dae` beside it, so a bake that went stale because
    # another round re-cooked its shape would silently ship the OLD mesh -- B3 r5's stale
    # imposter law, one layer down.  63 of the 75 are B1's and B3's shapes.
    assert not problems["stale_harvest"], problems["stale_harvest"][:5]


def test_the_engine_bake_harvest_covers_every_shipped_dae() -> None:
    """G-B4-15 (r3): QB-8, closed.  Every `.dae` in the tree ships its `.cdae` sibling.

    r2 measured QB-8 at 0.096 and handed it to B6 as "new information the round produced".
    Critic pass 2 then opened B4's own certified boot: `profile_footprint.removed` listed
    **75** `.cdae` -- exactly the 75 missing siblings, 12 of them B4's own props -- cooked by
    the engine at level load and swept unread by the round's own purge, while the same boot
    was already harvesting 14 imposter atlases out of the same directory.  The round held
    the fix and deleted it.  This gate is the fix, asserted.
    """

    # B5 (2026-09-10) moved the Gateway Skillet arena's 14 DAEs under the level's own
    # `art/shapes/hot_potato_arena/`. They ship in the ARENA zip (build_distribution.py, its
    # own manifest and lock), not in the level zip, and that zip has never carried `.cdae`
    # siblings - the engine cooks them at load. Recorded debt for B6: harvest them in the
    # packaging boot and pin them like the level's own. This gate is the LEVEL's QB-8.
    arena_shapes = LEVEL_ROOT / "art" / "shapes" / "hot_potato_arena"
    daes = {p.stem for p in LEVEL_ROOT.rglob("*.dae") if arena_shapes not in p.parents}
    cooked = {p.stem for p in LEVEL_ROOT.rglob("*.cdae") if arena_shapes not in p.parents}
    assert daes, LEVEL_ROOT
    assert not (daes - cooked), sorted(daes - cooked)[:8]
    manifest = props_build.harvest_manifest()
    staged = set(props_build.harvest_members(LEVEL_ROOT))
    assert staged == set(manifest.get("files", {})), sorted(staged ^ set(manifest["files"]))
    # every staged bake names a source that is really in the tree, with its hash
    for name, row in manifest["files"].items():
        assert (LEVEL_ROOT / row["source"]).is_file(), (name, row["source"])
        assert len(str(row["source_sha256"])) == 64, (name, row)


def test_the_props_group_holds_the_designed_census() -> None:
    records = _props_records()
    statics = [r for r in records if r["class"] == "TSStatic"]
    prefabs = [r for r in records if r["class"] == "Prefab"]
    kinds = Counter()
    for record in statics:
        kinds[Path(record["shapeName"]).stem.replace(f"{ps.LEVEL_ID}_p_", "")] += 1
    # 2026-09-15/16, the user's call (place_props.py, amendment A2): the two kindling logs,
    # the enamel pot, the lantern tripod and the lantern that hung from it, then the leaner
    # log, the half-log bench deck and the four lantern posts are OFF the map. Their shapes
    # still ship (members and manifests untouched); nothing places them.
    for key in (
        "bench_log",
        "leaner_log",
        "log_north",
        "log_south",
        "lantern_tripod",
        "giant_lantern",
        "enamel_pot",
        "lantern_post",
    ):
        assert kinds[key] == 0, (key, kinds[key])
    assert kinds["trail_sign"] == 1
    assert kinds["trail_cairn"] == 2
    assert kinds["fence_post"] == ps.FENCE["posts"] + 1
    assert kinds["fence_rail"] == ps.FENCE["posts"] * ps.FENCE["rails_per_bay"]
    assert len(prefabs) >= 400
