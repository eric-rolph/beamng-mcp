r"""B7b: the Shafer Bench -- a native MeshRoad cut along the canyon wall.

The user, on the canyon walls: *"let's make it drivable, extend the road up into the side
wall mountains (if possible)."*  B7a put a real Canyonlands rim on the skyline (amendment
A4).  This is the road up it.

Then, while it was being built: *"Let's make sure we're using BeamNG.drive native tools (if
it makes sense) ... Decal & Mesh Road Editors: lay down drivable asphalt, dirt paths ... with
customizable widths, bank angles, and edge falloffs."*  It makes exact sense here.  A road
over a 200 m drop is what the engine's ``MeshRoad`` class is FOR: a spline of nodes, each with
its own position, width, depth and normal, with top / bottom / side materials and collision
the engine builds itself.  So the road ships as one ``MeshRoad`` object -- editable afterwards
in the World Editor's Mesh Road Editor like any hand-laid road -- and the approach from the
trail ships as one ``DecalRoad``, which is what the Decal Road Editor lays on terrain.  A
first draft of this module generated the bench as a Blender DAE with a hand-built Colmesh;
it built clean and passed its gates, and it was retired for the native object before it was
ever cut into a release.

What this module owns is the SURVEY: where the road can go.  Everything the engine can do
for itself -- tessellation, collision, LOD, texturing along the spline -- it is left to do.


WHY IT IS A TRAVERSE AND NOT SWITCHBACKS
----------------------------------------
Seven alignment probes went into this (``authoring/round_records/b7b/``) and six designed
switchbacks, because that is what a road up a cliff looks like.  They cannot be built here,
and the reason is arithmetic.  A bench is a CUT: its floor runs back into the rock and the cut
does not daylight until ``cut x tan(face angle)`` higher up.  The near ring's front face is
**83 to 88.4 degrees**, so a 9 m bench needs **73 m of height at 83 degrees and more than
200 m near 88**.  Two legs stacked even 96 m apart still overhang by 12 m.  A traverse crosses
each column of the wall ONCE, so the question never arises -- and it is the shape the real
Shafer Trail takes across these same benches.


THE SURVEY
----------
Laid out from the pass DOWNWARD, the way a mountain road is surveyed, and checked every 5 m:

* **crest** -- at least ``CREST_CLEARANCE_M`` of wall above the deck, once past the pass;
* **face**  -- the deck is between the ring's foot and its crest, so there is rock beside it;
* **ground** -- the deck is above any terrain it crosses; where the hillside rises to meet
  it is the landing, and the road runs out onto the ground from there;
* **block** -- the landing is inside the terrain block, tested explicitly (``np.interp``
  clamps, and an early probe "landed" a road 74 m outside the world).

A sweep over every 2 degrees of crest, both directions and three grades left two alignments
standing; this is the one with more rise.


THE MESHROAD
------------
One node every ``NODE_SPACING_M``.  Each node's position is the centre of the deck surface,
set so the wall-side edge sits ``EDGE_INTO_FACE_M`` INSIDE the ring's face: the rock is the
road's cut wall, and no seam can open between them however the ring's columns fall.  Width
is the drivable deck, widening into a turning pad at the pass.  Depth is the slab under it.
The normal is BANKED ``BANK_TOWARD_WALL`` toward the rock -- the Mesh Road Editor's bank angle
-- so a car that slides, slides into the wall and not off the edge.
"""

from __future__ import annotations

import itertools
import json
import math

from examples.hot_potato_arena.level import blender_backdrop as bd
from examples.hot_potato_arena.level import terrain_model as tm

LEVEL_ID = bd.LEVEL_ID
ROAD_NAME = f"{LEVEL_ID}_shelf_road"
APPROACH_NAME = f"{LEVEL_ID}_shelf_approach"
#: The SimGroup the MeshRoad lives in. Namespaced like every name this level adds -- the
#: level's own gate refuses a bare `shelf_road` -- and NOT the road's own name, because a group
#: is one more object in the same global name space the deck material collided in.
GROUP_NAME = f"{LEVEL_ID}_canyon_road"
#: NOT the road's own name. Materials and scene objects share ONE global name and
#: persistentId space in the engine: the first boot of this road shipped a material called
#: exactly what the MeshRoad is called, and the loader refused the road outright ("There is
#: another object ... with either an identical name ... or identical persistentId (object
#: has classname: 'material', expected classname: 'MeshRoad')"). The level loaded clean
#: apart from that one E line, with no road in it.
ROAD_MATERIAL = f"{LEVEL_ID}_shelf_road_deck"
ROAD_SIDE_MATERIAL = f"{LEVEL_ID}_shelf_road_side"

#: The ring the road is cut along: the near one, the only one a player can reach.
RING = bd.RINGS[0]

# --- the survey (round_records/b7b/choose_spiral.py) ---------------------------------------
PASS_BEARING = 251.015625  # a column bearing, so the pass is a mesh column exactly
DESCEND_DIRECTION = -1.0  # anticlockwise from the pass: the direction that closed
GRADE = 0.10
STEP_M = 5.0
CREST_CLEARANCE_M = 10.0
PASS_APPROACH_M = 120.0
LANDING_TOLERANCE_M = 2.0
ABOVE_GROUND_M = 1.0
MAX_SWEEP_DEG = 330.0
#: The bottom end runs out onto the hillside instead of stopping 1.5 m above it.
TOUCHDOWN_RUNOUT_M = 30.0
TOUCHDOWN_CROWN_M = 0.18

# --- the road -------------------------------------------------------------------------------
#: The drivable lane: from the drop edge to the MOST protruding rock nearby, never less.
DECK_WIDTH_M = 8.0
SUMMIT_PAD_M = 35.0
#: The pass widens to this much drivable width, so a car can turn round at the top.
SUMMIT_WIDTH_M = 18.0
#: The wall-side edge sits this far inside the FURTHEST-back rock nearby, so there is never a
#: slot between the road and the wall for a wheel to drop into.
EDGE_INTO_FACE_M = 1.5
#: THE EDGES FOLLOW AN ENVELOPE OF THE ROCK, NOT THE NEAREST COLUMN.
#:
#: r1 put each node's wall edge 1.5 m into the face of the nearest mesh column. The ring's
#: face moves by a median 0.37 m and up to 3.94 m from one column (4.7 m) to the next, so the
#: first boot's road jogged visibly at bends, and rays cast across the deck met rock
#: 7.5-14.3 m ABOVE the lane 4 m from its centre -- the wall standing in the road. So each
#: station reads the face over +-`ENVELOPE_COLUMNS` columns and takes both ends of it: the
#: drop edge is `DECK_WIDTH_M` inside the most protruding rock, the wall edge is
#: `EDGE_INTO_FACE_M` behind the most receding rock, and both are smoothed along the road over
#: +-`EDGE_SMOOTH_STATIONS` before any node samples them.
ENVELOPE_COLUMNS = 2
EDGE_SMOOTH_STATIONS = 4
DEPTH_M = 3.0
#: Cross-fall toward the wall, as a slope (3 %). The Mesh Road Editor's bank angle. Measured
#: as built (`round_records/b7b/`): the deck falls 2.5-5.3 % toward the rock, never the drop.
BANK_TOWARD_WALL = 0.03
#: One node per this many metres of centreline, sampling the SMOOTHED edges.
NODE_SPACING_M = 20.0
#: About one base-colour repeat per road width, so the macro dirt reads square.
TEXTURE_LENGTH_M = 12.0
BREAK_ANGLE_DEG = 3.0

# --- the approach (a DecalRoad on terrain) ----------------------------------------------------
#: The turnaround loop (see `approach_path`): its apex this far anticlockwise of the road's
#: first node, this radius, and the inner leg starting this far clockwise of the foot.
APPROACH_LOOP_APEX_OFFSET_DEG = 2.5
APPROACH_LOOP_RADIUS_M = 17.0
APPROACH_INNER_LEG_START_DEG = 3.0
#: Close enough that a 17 m loop is a curve, not a polygon.
APPROACH_NODE_SPACING_M = 4.0
APPROACH_WIDTH_M = 7.0
#: The approach's grades, judged over a window so terrain micro-relief is not mistaken for
#: slope: the trail's own 12 % everywhere except the last pitch onto the road's foot, where
#: the hillside falls toward the wall and a car facing uphill has to come down onto it.
APPROACH_GRADE_WINDOW_M = 25.0
APPROACH_GRADE_MAX = 0.20

_ALIGNMENT: list[dict] | None = None


def _column_of(bearing: float) -> int:
    return round((bearing % 360.0) / 360.0 * bd.COLUMN_SEGMENTS) % bd.COLUMN_SEGMENTS


def crest_z(bearing: float) -> float:
    """The near ring's crest at this bearing, from the shipped profile."""

    return bd.ring_profile(RING, bearing % 360.0)[0]


def face_rows(bearing: float) -> list[tuple[float, float]]:
    """The seven authored front rows (radius, z) of the column nearest this bearing."""

    return bd._front_column(RING, _column_of(bearing))


def face_radius(bearing: float, z: float) -> float:
    """Where the front face stands at height ``z``, between the authored rows."""

    rows = face_rows(bearing)
    if z <= rows[0][1]:
        return rows[0][0]
    if z >= rows[-1][1]:
        return rows[-1][0]
    for (r0, z0), (r1, z1) in itertools.pairwise(rows):
        if z0 <= z <= z1:
            t = 0.0 if z1 == z0 else (z - z0) / (z1 - z0)
            return r0 + t * (r1 - r0)
    return rows[-1][0]


def ground_z(x: float, y: float) -> float:
    """Terrain height at world (x, y); NaN outside the block. The shipped reader."""

    return float(bd.terrain_z_world(x, y))


def polar(bearing: float, radius: float) -> tuple[float, float]:
    theta = math.radians(bearing)
    return bd.CENTER_XY[0] + radius * math.sin(theta), bd.CENTER_XY[1] + radius * math.cos(theta)


def alignment() -> list[dict]:
    """The surveyed centreline, landing first. Cached; reads the terrain."""

    global _ALIGNMENT
    if _ALIGNMENT is not None:
        return _ALIGNMENT
    bearing, z, travelled = PASS_BEARING, crest_z(PASS_BEARING), 0.0
    stations: list[dict] = []
    limit = math.radians(MAX_SWEEP_DEG) * 1200.0
    while travelled < limit:
        radius = face_radius(bearing, z)
        x, y = polar(bearing, radius)
        stations.append(
            {"s": travelled, "bearing": bearing % 360.0, "radius": radius, "z": z, "x": x, "y": y}
        )
        here = ground_z(x, y)
        if not math.isnan(here) and z - here <= LANDING_TOLERANCE_M:
            break
        bearing += DESCEND_DIRECTION * math.degrees(STEP_M / max(radius, 1.0))
        z -= STEP_M * GRADE
        travelled += STEP_M
    # THE RUNOUT: past the landing the deck is laid on the ground itself, so the bench
    # becomes a track and a car from the approach drives straight on instead of meeting a
    # 1.5 m step. It holds the radial line the DECK CENTRE landed on -- not the survey line,
    # which is the face: r1 read the ground there and left the deck's middle 0.25 m under the
    # hillside it was meant to lie on.
    inner, outer = rock_envelope(stations[-1])
    landed_radius = ((inner - DECK_WIDTH_M) + (outer + EDGE_INTO_FACE_M)) / 2.0
    for _ in range(int(TOUCHDOWN_RUNOUT_M / STEP_M)):
        bearing += DESCEND_DIRECTION * math.degrees(STEP_M / max(landed_radius, 1.0))
        travelled += STEP_M
        x, y = polar(bearing, landed_radius)
        here = ground_z(x, y)
        if math.isnan(here):
            break
        stations.append(
            {
                "s": travelled,
                "bearing": bearing % 360.0,
                "radius": landed_radius,
                "z": here + TOUCHDOWN_CROWN_M,
                "x": x,
                "y": y,
                "on_the_ground": True,
            }
        )
    stations.reverse()  # driven from the landing up to the pass
    top = stations[-1]["s"]
    bottom = stations[0]["s"]
    for index, station in enumerate(stations):
        station["index"] = index
        station["from_bottom_m"] = abs(station["s"] - bottom)
        station["from_top_m"] = abs(top - station["s"])
    _ALIGNMENT = stations
    return _ALIGNMENT


def _smoothstep(value: float, span: float) -> float:
    t = min(max(value / span, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def deck_width(station: dict) -> float:
    """The drivable width, widening into a turning pad over the last metres to the pass."""

    t = _smoothstep(station["from_top_m"], SUMMIT_PAD_M)
    return DECK_WIDTH_M + (SUMMIT_WIDTH_M - DECK_WIDTH_M) * (1.0 - t)


def face_radius_at_column(column: int, z: float) -> float:
    rows = bd._front_column(RING, column % bd.COLUMN_SEGMENTS)
    if z <= rows[0][1]:
        return rows[0][0]
    if z >= rows[-1][1]:
        return rows[-1][0]
    for (r0, z0), (r1, z1) in itertools.pairwise(rows):
        if z0 <= z <= z1:
            t = 0.0 if z1 == z0 else (z - z0) / (z1 - z0)
            return r0 + t * (r1 - r0)
    return rows[-1][0]


def rock_envelope(station: dict) -> tuple[float, float]:
    """(most protruding, most receding) face radius at deck height over the nearby columns.

    Only columns that HAVE rock at deck height count. A neighbour whose crest is below the
    deck is a notch, and its clamped top-row radius is not a wall; counting it widened the
    road to 32.7 m near the pass, where the deck climbs level with the rim.
    """

    exact = (station["bearing"] % 360.0) / 360.0 * bd.COLUMN_SEGMENTS
    base = math.floor(exact)
    radii = []
    for column in range(base - ENVELOPE_COLUMNS, base + ENVELOPE_COLUMNS + 2):
        rows = bd._front_column(RING, column % bd.COLUMN_SEGMENTS)
        if rows[-1][1] < station["z"]:
            continue
        radii.append(face_radius_at_column(column, station["z"]))
    if not radii:
        return station["radius"], station["radius"]
    return min(radii), max(radii)


_EDGES: list[tuple[float, float]] | None = None


def deck_edges() -> list[tuple[float, float]]:
    """(drop edge radius, wall edge radius) per station, smoothed along the road. Cached.

    On the bench: the drop edge is the drivable width inside the most protruding rock, the
    wall edge is `EDGE_INTO_FACE_M` behind the most receding rock, each a moving mean over
    +-`EDGE_SMOOTH_STATIONS`. The smoothing may pull either edge back toward the rock by a
    fraction of a metre, so the drop edge is then re-asserted against the raw envelope: the
    lane is never narrower than it was surveyed to be. On the runout, which has left the wall,
    both edges freeze at the landing's.
    """

    global _EDGES
    if _EDGES is not None:
        return _EDGES
    stations = alignment()
    count = len(stations)
    bench = [i for i, s in enumerate(stations) if not s.get("on_the_ground")]
    envelope = {i: rock_envelope(stations[i]) for i in bench}

    def in_reach(i: int, half: int) -> list[int]:
        return [j for j in range(i - half, i + half + 1) if 0 <= j < count and j in envelope]

    # ROLLING min / max over a whole node span either side: the spline runs STRAIGHT between
    # nodes, so a guarantee that holds only at node stations holds nowhere in between.
    required: dict[int, tuple[float, float]] = {}
    for i in bench:
        reach = in_reach(i, EDGE_SMOOTH_STATIONS)
        inner = min(envelope[j][0] for j in reach)
        outer = max(envelope[j][1] for j in reach)
        required[i] = (inner - deck_width(stations[i]), outer + EDGE_INTO_FACE_M)
    edges: list[tuple[float, float] | None] = [None] * count
    for i in bench:
        reach = in_reach(i, 2)
        drop = sum(required[j][0] for j in reach) / len(reach)
        wall = sum(required[j][1] for j in reach) / len(reach)
        # a smooth line, but never narrower or shorter of the wall than required
        edges[i] = (min(drop, required[i][0]), max(wall, required[i][1]))
    landing = edges[bench[0]]
    _EDGES = [row if row is not None else landing for row in edges]
    return _EDGES


def edges_as_built() -> list[tuple[float, float]]:
    """(drop, wall) edge radii at EVERY station, the way the MeshRoad spline lays them.

    Between two nodes the engine interpolates the road's centre and width; this interpolates
    the two edges linearly between the bracketing nodes, which is what a gate has to check --
    the node stations alone are one in four.
    """

    stations = alignment()
    nodes = meshroad_nodes()
    anchors = []
    for node in nodes:
        station = stations[node["station"]]
        dx = node["position"][0] - bd.CENTER_XY[0]
        dy = node["position"][1] - bd.CENTER_XY[1]
        centre = math.hypot(dx, dy)
        anchors.append((station["s"], centre - node["width"] / 2.0, centre + node["width"] / 2.0))
    anchors.sort()
    out = []
    for station in stations:
        s = station["s"]
        for (s0, d0, w0), (s1, d1, w1) in itertools.pairwise(anchors):
            lo, hi = min(s0, s1), max(s0, s1)
            if lo <= s <= hi:
                t = 0.0 if s1 == s0 else (s - s0) / (s1 - s0)
                out.append((d0 + t * (d1 - d0), w0 + t * (w1 - w0)))
                break
        else:
            nearest = min(anchors, key=lambda a: abs(a[0] - s))
            out.append((nearest[1], nearest[2]))
    return out


# --- the MeshRoad -----------------------------------------------------------------------------


def node_stations() -> list[dict]:
    """The survey stations a node sits on: every `NODE_SPACING_M`, both ends always."""

    stations = alignment()
    every = max(1, round(NODE_SPACING_M / STEP_M))
    picked = stations[::every]
    if picked[-1] is not stations[-1]:
        picked.append(stations[-1])
    # never let a node straddle the runout / bench boundary without a node ON it
    boundary = next(
        (s for s in stations if not s.get("on_the_ground")),
        None,
    )
    if boundary is not None and boundary not in picked:
        picked.append(boundary)
        picked.sort(key=lambda s: s["index"])
    return picked


def meshroad_nodes() -> list[dict]:
    """Each node: deck-centre position, width, depth, and a normal banked toward the wall."""

    nodes: list[dict] = []
    edges = deck_edges()
    for station in node_stations():
        theta = math.radians(station["bearing"])
        radial = (math.sin(theta), math.cos(theta))
        drop_r, wall_r = edges[station["index"]]
        width = wall_r - drop_r
        centre_r = (wall_r + drop_r) / 2.0
        if station.get("on_the_ground"):
            normal = (0.0, 0.0, 1.0)  # on the hillside there is no wall to bank toward
        else:
            nx, ny, nz = BANK_TOWARD_WALL * radial[0], BANK_TOWARD_WALL * radial[1], 1.0
            length = math.sqrt(nx * nx + ny * ny + nz * nz)
            normal = (nx / length, ny / length, nz / length)
        x, y = polar(station["bearing"], centre_r)
        nodes.append(
            {
                "station": station["index"],
                "position": (x, y, station["z"]),
                "width": width,
                "depth": DEPTH_M,
                "normal": normal,
            }
        )
    return nodes


def meshroad_record() -> dict:
    """The scene record, in the field layout the engine's own ``serialize()`` writes.

    The layout was captured from the engine rather than guessed: a MeshRoad built with the
    Mesh Road Editor's own API (``createObject("MeshRoad")`` + ``insertNode``) and written out
    with ``obj:serialize()`` -- the serializer the World Editor's Save Level uses -- in the B7b
    boot (``round_records/b7b/meshroad_native.json``). No stock level ships a MeshRoad, so
    there was no file to copy the layout from.
    """

    nodes = meshroad_nodes()
    return {
        "name": ROAD_NAME,
        "class": "MeshRoad",
        "persistentId": _persistent_id(ROAD_NAME),
        "__parent": GROUP_NAME,
        "position": [round(v, 4) for v in nodes[0]["position"]],
        "topMaterial": ROAD_MATERIAL,
        "bottomMaterial": ROAD_SIDE_MATERIAL,
        "sideMaterial": ROAD_SIDE_MATERIAL,
        "textureLength": TEXTURE_LENGTH_M,
        "breakAngle": BREAK_ANGLE_DEG,
        "widthSubdivisions": 0,
        "nodes": [
            [
                round(node["position"][0], 4),
                round(node["position"][1], 4),
                round(node["position"][2], 4),
                round(node["width"], 4),
                round(node["depth"], 4),
                round(node["normal"][0], 6),
                round(node["normal"][1], 6),
                round(node["normal"][2], 6),
            ]
            for node in nodes
        ],
    }


def _persistent_id(name: str) -> str:
    import uuid

    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"beamng-mcp:{LEVEL_ID}:{name}"))


# --- the approach -----------------------------------------------------------------------------


def _first_node_polar() -> tuple[float, float]:
    first = meshroad_nodes()[0]["position"]
    dx, dy = first[0] - bd.CENTER_XY[0], first[1] - bd.CENTER_XY[1]
    return math.degrees(math.atan2(dx, dy)) % 360.0, math.hypot(dx, dy)


def approach_path() -> list[tuple[float, float]]:
    """(x, y) every `APPROACH_NODE_SPACING_M`: trail's end, an inner leg, a loop, the road.

    THE TURNAROUND IS PART OF THE APPROACH. r2's AI car stopped dead where the approach met the
    road, and not because of the AI: the trail ends at bearing 150, the road's foot is at 133.7,
    and the road climbs CLOCKWISE. A straight approach reaches the foot travelling the other
    way and meets the road head-on. So the approach runs anticlockwise along an inner radius
    past the foot, swings outward round a loop of `APPROACH_LOOP_RADIUS_M`, and comes back
    clockwise along the road's own radius into its first node, already pointing uphill.

    The loop sits where the hillside is gentlest to cross (`round_records/b7b/
    probe_turnaround.py`). The last leg is the steep one -- the ground falls toward the wall
    and clockwise at about 16 % there -- and that is inherent: any approach that arrives facing
    uphill comes down onto the foot.
    """

    foot_b, foot_r = _first_node_polar()
    out_r = foot_r
    in_r = out_r - 2.0 * APPROACH_LOOP_RADIUS_M
    apex = foot_b - APPROACH_LOOP_APEX_OFFSET_DEG
    trail_b, trail_r = float(tm.TRAIL_BEARING), float(tm.TRAIL_WAYPOINTS[-1][1])
    points: list[tuple[float, float]] = []

    def line(b0: float, r0: float, b1: float, r1: float) -> None:
        x0, y0 = polar(b0, r0)
        x1, y1 = polar(b1, r1)
        steps = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / APPROACH_NODE_SPACING_M))
        for k in range(steps + 1):
            if k == 0 and points:
                continue
            t = k / steps
            points.append(polar(b0 + t * (b1 - b0), r0 + t * (r1 - r0)))

    line(trail_b, trail_r, foot_b + APPROACH_INNER_LEG_START_DEG, in_r)
    line(foot_b + APPROACH_INNER_LEG_START_DEG, in_r, apex, in_r)
    cx, cy = polar(apex, (in_r + out_r) / 2.0)
    theta = math.radians(apex)
    radial = (math.sin(theta), math.cos(theta))
    clockwise = (math.cos(theta), -math.sin(theta))
    arc_steps = max(8, math.ceil(math.pi * APPROACH_LOOP_RADIUS_M / APPROACH_NODE_SPACING_M))
    for k in range(1, arc_steps + 1):
        a = math.pi * k / arc_steps
        points.append(
            (
                cx
                + APPROACH_LOOP_RADIUS_M * (-math.cos(a) * radial[0] - math.sin(a) * clockwise[0]),
                cy
                + APPROACH_LOOP_RADIUS_M * (-math.cos(a) * radial[1] - math.sin(a) * clockwise[1]),
            )
        )
    ax, ay = points[-1]
    loop_end_b = math.degrees(math.atan2(ax - bd.CENTER_XY[0], ay - bd.CENTER_XY[1])) % 360.0
    line(loop_end_b, out_r, foot_b, out_r)
    first = meshroad_nodes()[0]["position"]
    points[-1] = (first[0], first[1])
    return points


def approach_nodes() -> list[list[float]]:
    """DecalRoad nodes ``[x, y, z, width]`` draped on the shipped terrain."""

    return [
        [round(x, 3), round(y, 3), round(ground_z(x, y), 3), APPROACH_WIDTH_M]
        for x, y in approach_path()
    ]


def sustained_grade(points: list[tuple[float, float, float]], window_m: float) -> float:
    """The steepest grade over any `window_m` of path -- what a driver feels, not the noise."""

    s = [0.0]
    for a, b in itertools.pairwise(points):
        s.append(s[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    worst, j = 0.0, 0
    for i in range(len(points)):
        while j < len(points) and s[j] - s[i] < window_m:
            j += 1
        if j >= len(points):
            break
        worst = max(worst, abs(points[j][2] - points[i][2]) / (s[j] - s[i]))
    return worst


# --- materials --------------------------------------------------------------------------------


#: The deck's ground model: the level's own packed-dirt trail (static 0.72 / sliding 0.74),
#: so the road up the wall grips and sounds like the trail that leads to it. Without one the
#: wheels read the engine's default ASPHALT (measured in the surface diagnostic).
#: MEASURED: A MESHROAD IGNORES THIS. r2 set the level's own `ERHP_TRAIL` and r3 the stock
#: `DIRT`, and on both the wheels on the deck read ASPHALT -- while a stock name in this same
#: field resolves on a TSStatic's material everywhere else in this level (the arena's butter
#: pools read ICE through it). So the deck drives with the engine's default asphalt grip and
#: sound whatever is written here. It stays, stock and truthful about the surface it draws, so a
#: later engine that does honour it gets the right answer; nothing may rely on it today
#: (`authoring/round_records/level_facts.md`).
DECK_GROUND_TYPE = "DIRT"


def materials_document() -> dict:
    """The deck wears the trail's own dirt; the slab's sides wear the ring's rock.

    r1 put the ring's CLIFF maps on the deck too, and a cliff texture laid flat and run along a
    road reads as orange and black stripes across the lane (`b7b` frames). The trail terrain
    layer ships a macro and a detail set for exactly this surface; MeshRoad stretches one
    repeat of the base map across the road's width, so the MACRO carries the colour and the
    detail map carries the grain. Every map is already a level member: nothing new is cooked.
    """

    terrains = f"/levels/{LEVEL_ID}/art/terrains"
    rock = f"/levels/{LEVEL_ID}/art/shapes/hot_potato_arena_backdrop"

    def material(name: str, stage: dict, pid: str, ground: str | None = None) -> dict:
        record = {
            "name": name,
            "mapTo": name,
            "class": "Material",
            "persistentId": pid,
            "Stages": [stage, {}, {}, {}],
            "materialTag0": "beamng",
            "materialTag1": "Natural",
            "translucent": False,
            "castShadows": True,
            "version": 1.5,
        }
        if ground:
            record["groundType"] = ground
        return record

    deck = {
        "baseColorMap": f"{terrains}/{LEVEL_ID}_t_trail_macro_b.png",
        "normalMap": f"{terrains}/{LEVEL_ID}_t_trail_macro_nm.png",
        "roughnessMap": f"{terrains}/{LEVEL_ID}_t_trail_macro_r.png",
        "ambientOcclusionMap": f"{terrains}/{LEVEL_ID}_t_trail_macro_ao.png",
        "detailMap": f"{terrains}/{LEVEL_ID}_t_trail_detail_b.png",
        "detailNormalMap": f"{terrains}/{LEVEL_ID}_t_trail_detail_nm.png",
        "detailScale": [6.0, 6.0],
        "detailNormalMapStrength": 0.8,
    }
    sides = {
        "baseColorMap": f"{rock}/{LEVEL_ID}_backdrop.color.png",
        "normalMap": f"{rock}/{LEVEL_ID}_backdrop.normal.png",
        "roughnessMap": f"{rock}/{LEVEL_ID}_backdrop_roughness.data.png",
        "detailMap": f"{rock}/{LEVEL_ID}_backdrop_detail_b.png",
        "detailNormalMap": f"{rock}/{LEVEL_ID}_backdrop_detail_nm.png",
        "detailScale": [8.0, 8.0],
        "detailNormalMapStrength": 0.6,
    }
    return {
        ROAD_MATERIAL: material(
            ROAD_MATERIAL, deck, _persistent_id(ROAD_MATERIAL), ground=DECK_GROUND_TYPE
        ),
        ROAD_SIDE_MATERIAL: material(ROAD_SIDE_MATERIAL, sides, _persistent_id(ROAD_SIDE_MATERIAL)),
    }


# --- the audit -------------------------------------------------------------------------------


def audit() -> dict:
    """Every number a gate could want, measured on the survey and the nodes that ship."""

    stations = alignment()
    bench = [s for s in stations if not s.get("on_the_ground")]
    runout = [s for s in stations if s.get("on_the_ground")]

    def grades(rows: list[dict]) -> list[float]:
        out = []
        for a, b in itertools.pairwise(rows):
            run = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
            if run > 1e-6:
                out.append(abs(b["z"] - a["z"]) / run)
        return out

    bench_grades = grades(bench)
    runout_grades = grades([bench[0], *runout[::-1]]) if runout else []
    off_face = buried = 0
    steepest = 0.0
    crest_gaps = []
    for station in bench:
        rows = face_rows(station["bearing"])
        if not (rows[0][1] - 0.01 <= station["z"] <= rows[-1][1] + 0.01):
            off_face += 1
        dz = rows[-1][1] - rows[0][1]
        dr = abs(rows[-1][0] - rows[0][0])
        steepest = max(steepest, math.degrees(math.atan2(dz, max(dr, 1e-9))))
        if station["from_top_m"] > PASS_APPROACH_M:
            crest_gaps.append(crest_z(station["bearing"]) - station["z"])
        here = ground_z(station["x"], station["y"])
        if (
            not math.isnan(here)
            and station is not bench[0]
            and station["z"] - here < ABOVE_GROUND_M
        ):
            buried += 1
    nodes = meshroad_nodes()
    node_gaps = [math.dist(a["position"], b["position"]) for a, b in itertools.pairwise(nodes)]
    approach = approach_nodes()
    approach_grades = []
    approach_len = 0.0
    for a, b in itertools.pairwise(approach):
        run = math.hypot(b[0] - a[0], b[1] - a[1])
        approach_len += run
        if run > 1e-6:
            approach_grades.append(abs(b[2] - a[2]) / run)
    first_node = nodes[0]["position"]
    built = edges_as_built()
    lane_min, wall_gap_max = 1e9, -1e9
    for station in bench:
        # the rock exactly at this station: the two columns that bracket its bearing
        exact = (station["bearing"] % 360.0) / 360.0 * bd.COLUMN_SEGMENTS
        base = math.floor(exact)
        t = exact - base
        here = (1.0 - t) * face_radius_at_column(base, station["z"]) + t * face_radius_at_column(
            base + 1, station["z"]
        )
        drop_r, wall_r = built[station["index"]]
        lane_min = min(lane_min, here - drop_r)
        wall_gap_max = max(wall_gap_max, here - wall_r)
    return {
        "survey_stations": len(stations),
        "bench_stations": len(bench),
        "runout_stations": len(runout),
        "length_m": round(abs(stations[-1]["s"] - stations[0]["s"]), 1),
        "pass_bearing": PASS_BEARING,
        "pass_z": round(crest_z(PASS_BEARING), 3),
        "rise_m": round(stations[-1]["z"] - stations[0]["z"], 2),
        "grade_max_on_the_bench": round(max(bench_grades), 4),
        "grade_mean_on_the_bench": round(sum(bench_grades) / len(bench_grades), 4),
        "grade_max_on_the_runout": round(max(runout_grades), 4) if runout_grades else None,
        "worst_crest_gap_m": round(min(crest_gaps), 2),
        "samples_off_the_face": off_face,
        "samples_buried_in_terrain": buried,
        "columns_used_twice": len(_stacked_columns(bench)),
        "steepest_face_deg": round(steepest, 2),
        "meshroad": {
            "nodes": len(nodes),
            "node_spacing_max_m": round(max(node_gaps), 2),
            "width_min_m": round(min(n["width"] for n in nodes), 2),
            "width_max_m": round(max(n["width"] for n in nodes), 2),
            "depth_m": DEPTH_M,
            "bank_toward_wall": BANK_TOWARD_WALL,
            # the drivable lane, measured to the MOST protruding rock over the envelope
            "lane_width_min_m": round(lane_min, 3),
            # > 0 would be a slot between the deck and the furthest-back rock
            "wall_gap_max_m": round(wall_gap_max, 3),
        },
        "approach": {
            "nodes": len(approach),
            "length_m": round(approach_len, 1),
            # point to point on 4 m nodes: terrain micro-relief, reported, not gated
            "grade_max_node_to_node": round(max(approach_grades), 4),
            # what a driver feels: the steepest grade over any 25 m
            "grade_max_sustained": round(
                sustained_grade([tuple(n[:3]) for n in approach], APPROACH_GRADE_WINDOW_M), 4
            ),
            "grade_window_m": APPROACH_GRADE_WINDOW_M,
            "arrival_heading_off_the_road_deg": round(_arrival_misalignment(approach, nodes), 2),
            "nodes_off_the_terrain_block": sum(1 for n in approach if math.isnan(n[2])),
            "joins_the_road_within_m": round(
                math.hypot(approach[-1][0] - first_node[0], approach[-1][1] - first_node[1]), 3
            ),
            "step_up_to_the_road_m": round(first_node[2] - approach[-1][2], 3),
        },
        "terrain_ter_sha256": bd.terrain_grid()["sha256"],
    }


# --- clearing the forest off the road --------------------------------------------------------
#: The forest was planted before the road existed; the first road boot drove a car 18 m up the
#: runout and into a pine, and the frame from the road's foot shows trunks on the deck. An
#: instance goes if its base stands within the road's half-width plus this margin of the road
#: centreline, somewhere the deck is no more than `FOREST_REACH_M` above that base -- a tree
#: at the foot of a 200 m cliff does not block a bench at the top of it.
FOREST_MARGIN_M = 3.0
FOREST_REACH_M = 45.0
FOREST_BELOW_M = 3.0


def forest_corridor() -> list[tuple[float, float, float, float]]:
    """(x, y, deck z, half width) along the approach and at every station of the MeshRoad."""

    points: list[tuple[float, float, float, float]] = []
    approach = approach_nodes()
    for a, b in itertools.pairwise(approach):
        steps = max(1, math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / 2.5))
        for k in range(steps):
            t = k / steps
            points.append(
                (
                    a[0] + t * (b[0] - a[0]),
                    a[1] + t * (b[1] - a[1]),
                    a[2] + t * (b[2] - a[2]),
                    a[3] / 2.0,
                )
            )
    for station, (drop_r, wall_r) in zip(alignment(), edges_as_built(), strict=True):
        x, y = polar(station["bearing"], (drop_r + wall_r) / 2.0)
        points.append((x, y, station["z"], (wall_r - drop_r) / 2.0))
    return points


def forest_clearance_plan(level_root) -> dict:
    """Which instance lines each forest4 file loses. Reads the tree; writes nothing.

    Idempotent by construction: run on a cleared tree it removes nothing more.
    """

    import numpy as np

    corridor = forest_corridor()
    cx = np.array([p[0] for p in corridor])
    cy = np.array([p[1] for p in corridor])
    cz = np.array([p[2] for p in corridor])
    reach = np.array([p[3] for p in corridor]) + FOREST_MARGIN_M
    plan: dict[str, dict] = {}
    for path in sorted((level_root / "forest").glob("*.forest4.json")):
        lines = path.read_text(encoding="utf-8").splitlines()
        keep, gone = [], []
        for line in lines:
            if not line.strip():
                continue
            x, y, z = json.loads(line)["pos"]
            near = np.hypot(cx - x, cy - y) < reach
            if near.any():
                above = cz[near] - z
                if np.any((above > -FOREST_BELOW_M) & (above < FOREST_REACH_M)):
                    gone.append(line)
                    continue
            keep.append(line)
        plan[path.name] = {"path": path, "keep": keep, "removed": gone}
    return plan


def apply_forest_clearance(level_root, plant_manifest_path, keepout_proof_path) -> dict:
    """Remove the corridor's instances and bring B3's two authoring records into line.

    Every kept line is written back byte for byte in its original order, so every instance
    outside the corridor is exactly where B3 planted it -- which is why this is a filter and
    not a re-plant: the planter is a sequential seeded Poisson disc, and a new keep-out would
    have moved trees across the whole map.
    """

    import hashlib

    plan = forest_clearance_plan(level_root)
    manifest = json.loads(plant_manifest_path.read_text(encoding="utf-8"))
    proof = json.loads(keepout_proof_path.read_text(encoding="utf-8"))
    removed_by_species: dict[str, int] = {}
    for name, entry in plan.items():
        species = name.removesuffix(".forest4.json")
        if not entry["removed"]:
            continue
        payload = ("\n".join(entry["keep"]) + "\n").encode("utf-8") if entry["keep"] else b""
        entry["path"].write_bytes(payload)
        relative = f"forest/{name}"
        manifest["files"][relative] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }
        manifest["per_species"][species] = len(entry["keep"])
        removed_by_species[species] = len(entry["removed"])
    total = sum(manifest["per_species"].values())
    this_run = sum(removed_by_species.values())
    record = manifest.get("shelf_road_clearance") or {"removed_total": 0, "by_species": {}}
    record["removed_total"] += this_run
    for species, count in removed_by_species.items():
        record["by_species"][species] = record["by_species"].get(species, 0) + count
    record["rule"] = {
        "margin_m": FOREST_MARGIN_M,
        "reach_above_base_m": FOREST_REACH_M,
        "below_base_m": FOREST_BELOW_M,
        "corridor": "approach DecalRoad + the MeshRoad at every survey station, as built",
        "module": "examples/hot_potato_arena/level/shelf_road.py",
        "amendment": "A6",
    }
    manifest["shelf_road_clearance"] = record
    manifest["instances_total"] = total
    manifest["bytes"] = sum(
        row["size"] for key, row in manifest["files"].items() if key.startswith("forest/")
    ) + sum(row["size"] for key, row in manifest["files"].items() if not key.startswith("forest/"))
    plant_manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    proof["instances"] = total
    proof["shelf_road_clearance_removed"] = record["removed_total"]
    keepout_proof_path.write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return {
        "removed_this_run": this_run,
        "removed_total": record["removed_total"],
        "instances_total": total,
    }


def _arrival_misalignment(approach: list[list[float]], nodes: list[dict]) -> float:
    """Degrees between the approach's last 12 m and the road's first span."""

    n0, n1 = nodes[0]["position"], nodes[1]["position"]
    road = math.atan2(n1[0] - n0[0], n1[1] - n0[1])
    end = approach[-1]
    back = next(
        (p for p in reversed(approach[:-1]) if math.hypot(p[0] - end[0], p[1] - end[1]) > 12.0),
        approach[0],
    )
    last = math.atan2(end[0] - back[0], end[1] - back[1])
    return abs((math.degrees(last - road) + 180.0) % 360.0 - 180.0)


def _stacked_columns(bench: list[dict]) -> list[int]:
    """Columns the bench visits on two separate passes (not two neighbouring stations)."""

    seen: dict[int, list[int]] = {}
    for station in bench:
        seen.setdefault(_column_of(station["bearing"]), []).append(station["index"])
    stacked = []
    for column, indices in seen.items():
        indices.sort()
        if indices[-1] - indices[0] > 4:  # more than ~20 m of road apart: a second pass
            stacked.append(column)
    return stacked


def main(argv: list[str] | None = None) -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Audit the shelf road, or clear its corridor")
    parser.add_argument(
        "--clear-forest",
        action="store_true",
        help="remove the forest instances standing in the road's corridor (idempotent)",
    )
    args = parser.parse_args(argv)
    if args.clear_forest:
        example = Path(__file__).resolve().parents[1]
        result = apply_forest_clearance(
            example / "mod" / "levels" / LEVEL_ID,
            example / "authoring" / f"{LEVEL_ID}_forest_plant.json",
            example / "authoring" / f"{LEVEL_ID}_forest_keepout.json",
        )
        print(json.dumps(result, indent=1, sort_keys=True))
        return 0
    print(json.dumps(audit(), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
