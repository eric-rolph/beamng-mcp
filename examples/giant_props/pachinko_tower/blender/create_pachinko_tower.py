"""Deterministic Blender generator for the Vertical Vehicle Pachinko Tower.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/pachinko_tower/blender/create_pachinko_tower.py

Design notes that belong next to the code rather than in spec.py:

* Every closed solid whose cross-section matters (pegs, bin dividers, chute
  slabs, the gate flap) is built by ``extruded_profile`` from
  the SAME (x, z) section list the collision cage uses, so mesh and cage
  cannot drift apart. ``recalc_face_normals`` orients each solid outward -
  Blender does not backface-cull and would happily render an inside-out mesh
  that is invisible in game (AGENTS.md defence #1).
* Cage nodes go through ``NodeStore``, which snaps every request to a 1 cm
  grid and returns the existing id for a repeat position. That makes shared
  edges automatic (walls meet at their corner columns) and makes coincident
  nodes - the degenerate flexbody skinning triad that produced the
  centrifuge's invisible deck band - impossible by construction. The final
  assert re-proves it by brute force.
* Collision completeness and VISUAL completeness are different questions and
  need different probes. Every raycast audit on this prop had been run over
  the cage triangles, and they were always complete - which is precisely why
  a 2.35 m strip of the drive-out lane shipped with collision and no drawn
  floor at all (the plinth stopped at -(DY + WT) while the bin floor's cage
  ran on to the divider front line). The instrument that catches that class
  is a top-down first-drawn-surface sweep over the BUILT visual; the
  ``bin_apron`` box below is its fix.
"""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Callable
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
EXAMPLE_ROOT = SCRIPT_PATH.parents[1]
PACK_ROOT = EXAMPLE_ROOT.parent
sys.path.insert(0, str(PACK_ROOT))
sys.path.insert(0, str(EXAMPLE_ROOT))

import bmesh  # noqa: E402
import bpy  # noqa: E402
import mathutils  # noqa: E402

import spec  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"

HW = spec.FIELD_HW
DY = spec.DEPTH_HALF
WT = spec.WALL_T
RIDGE = spec.RIDGE_Z
BIN_Z = spec.BIN_FLOOR_Z
TOP = spec.WALL_TOP_Z

# Peg row heights ascending; the walls carry a node station at every one so a
# row's outermost peg can tie straight into the wall it ends against.
PEG_ROW_ASC = sorted(spec.PEG_ROW_Z)
WALL_Z = sorted(
    {0.35, 2.70, 5.00, 6.00, 11.60, 38.50, 41.50, spec.WALL_TOP_Z} | set(PEG_ROW_ASC)
)
# The right wall stops where the crown chute slab crosses it. 0.2 m of
# deliberate overlap into the slab: an overlap is invisible, a gap is a hole.
RIGHT_WALL_TOP = round(spec.APRON_Z_HI - (spec.APRON_X_HI - HW) * math.tan(
    math.radians(spec.APRON_DEG)) - spec.APRON_T + 0.20, 3)

BACK_X = [-HW, -4.0, 4.0, HW, 17.5, spec.SHAFT_X1]
FRONT_X = [-HW, -4.0, 4.0, HW]
SHAFT_FRONT_X = [HW, 17.5, spec.SHAFT_X1]
BIN_X = sorted(set(spec.BIN_EDGES) | set(spec.BIN_CENTERS))
BIN_Y = [spec.DIVIDER_Y_FRONT, -DY, 0.0, DY]
DOCK_X = [HW, 14.3, 16.6, spec.DOCK_X1]
DIVIDER_X = spec.BIN_EDGES[1:-1]


def in_fall_volume(point: tuple[float, float, float]) -> bool:
    """Is this authored point inside the volume a released car falls through?

    The box the whole anti-hang argument is written against: from the bin
    floor (spec.FALL_VOLUME_Z_LO) to the wall top, inboard of both side walls
    and inside the board's depth. It used to stop at the bin MOUTH, one metre
    above where every surviving hang turned out to live. See THE FALL VOLUME
    IS FRICTIONLESS TO ITS WALLS in spec.py for why membership of this box
    decides a triangle's groundModel, and for the one exemption inside it.

    Boundary faces COUNT AS INSIDE ON ALL THREE AXES - the side walls sit
    exactly at +/-FIELD_HW, the board faces exactly at +/-DEPTH_HALF, and the
    bin floor exactly at FALL_VOLUME_Z_LO, and they are the surfaces this is
    about. z was STRICT until serial 79 and that was the defect: the wall
    grids carry a node station at the old z floor, so the lowest band of every
    board face had its bottom corners exactly on the excluded plane and kept
    its grip. Every surviving hang was resting on that band.

    Drive-on floors are NOT excluded here any more. They are excluded by
    ``is_drive_on_plane`` (the bin floor) or by x/y (the dock, the aprons, the
    island, the guard, the shaft). See THE FALL VOLUME IS FRICTIONLESS TO ITS
    WALLS in spec.py for the full list and why each one is safe.
    """

    x, y, z = point
    return (
        z >= spec.FALL_VOLUME_Z_LO - 1e-6
        and abs(x) <= HW + 1e-6
        and abs(y) <= DY + 1e-6
    )


def is_drive_on_plane(points: list[tuple[float, float, float]]) -> bool:
    """Does this face lie flat in the bin-floor plane, i.e. is it drive-on?

    The ONE exemption from the frictionless rule inside the fall volume, and
    it is deliberately a geometric test rather than a surface-name whitelist:
    a face qualifies only by lying horizontally at exactly the height a scored
    car parks at. `binfloor` is its only member today. A future horizontal
    surface added anywhere else in the pocket does not inherit the exemption -
    it has to be frictionless like every other face in the box.
    """

    return all(abs(point[2] - spec.FALL_VOLUME_DRIVE_ON_Z) <= 1e-6 for point in points)


def fall_volume_ground_model(corners: list[tuple[float, float, float]]) -> str:
    """Per-quad groundModel selector for the surfaces that bound the fall volume.

    A quad goes frictionless only when ALL its corners are in the volume, which
    is exactly the condition that makes every triangle cut from it satisfy
    ``assert_fall_volume_frictionless``. That equivalence is not a coincidence
    and it is not luck either: these grids are products (x or y) x z, and the
    membership test is a product of per-axis tests, so a quad has 0, 2 or 4
    corners outside - never exactly 1. A triangle can therefore never be fully
    inside while its parent quad is not.

    The drive-on exemption is applied at the QUAD too, and it composes with the
    same argument: a quad lies in the bin-floor plane only if all four corners
    do, so every triangle cut from it lies in the plane as well.
    """

    if not all(in_fall_volume(point) for point in corners):
        return "metal"
    if is_drive_on_plane(corners):
        return "metal"
    return spec.FALL_VOLUME_GROUNDMODEL


def apron_z(x: float) -> float:
    """Top surface of the crown chute at authored x (its only height datum)."""

    return spec.APRON_Z_HI - (spec.APRON_X_HI - x) * math.tan(math.radians(spec.APRON_DEG))


def peg_row_xs(row: int) -> list[float]:
    """Peg centres for a row, centred on the board.

    Both row types are centred, so dropping one column on the odd rows IS the
    half-pitch stagger: 4 pegs land on -11.4 .. +11.4 and 3 land on
    -7.6 .. +7.6, which is exactly PEG_OFFSET_X (3.80 m) apart. Adding the
    offset on top of that shifted the odd rows off-centre and opened a free
    lane against the left wall - caught by assert_no_clean_column.

    The even rows' outermost pegs reach x +/-12.50, i.e. 0.50 m PAST the
    board's 12.00 m collision wall and into the wall slab. That is deliberate
    and is what closes the side channels now that the wall stubs are gone -
    see the WHY THE WALL STUBS ARE GONE block in spec.py.

    THE ARITHMETIC MOVED TO spec.py 2026-08-18 (P0.2/P0.3) and this delegates,
    because the aperture table has to enumerate the openings a row has and a
    row layout retyped into a second file is this project's leading defect
    class. The docstring stays here, next to the mesh it shapes.
    """

    return spec.peg_row_xs(row)


def scallop_stations() -> list[float]:
    """Depth stations the peg is built from, front to back."""

    n = spec.PEG_SCALLOP_STATIONS
    stations = [-DY + (2 * DY) * i / (n - 1) for i in range(n)]
    # F-7: the copper head/shank break is a REAL station and must be in the one
    # shared list. build_peg used to insert it itself, so the visual carried a
    # vertex at y = -2.90 that the cage did not - a 27 mm mesh/cage disagreement
    # at the peg head, and exactly the drift the single-section rule exists to
    # prevent.
    head_break = -DY + PEG_HEAD_LEN
    if not any(abs(y - head_break) < 1e-6 for y in stations):
        stations.append(head_break)
        stations.sort()
    return stations


def scallop_up(y: float) -> float:
    """Crown reach at depth y. THE ONLY THING THE SCALLOP TOUCHES.

    A cosine over the board depth, crest at both faces so the wave is
    symmetric and the visible ends are high points rather than half-cut
    troughs. x is not a term in this function, which is the whole reason the
    scallop is safe: every lattice invariant in spec.py keys off PEG_R and the
    column positions, and neither appears here.

    Since the circular section (2026-08-14h) the return value is the crown
    reach that peg_section SCALES the upper half of the ring by, so the peg is
    a barrel waisted along its own length rather than a cone with a wandering
    tip. The equator is untouched at every station either way.
    """

    phase = (y + DY) / (2 * DY)
    return (
        spec.PEG_R_Z_UP
        + spec.PEG_SCALLOP_AMPLITUDE
        * math.cos(2.0 * math.pi * spec.PEG_SCALLOP_PERIODS * phase)
        + spec.PEG_SCALLOP_TILT * (phase - 0.5)
    )


def peg_section(cx: float, cz: float, y: float = 0.0) -> list[tuple[float, float]]:
    """THE peg cross-section. One function, both consumers.

    TWO SHAPES, ONE FUNCTION, selected by spec.PEG_SECTION_SHAPE: the KITE that
    ships, and the CIRCLE that was built for the player's "make the geometry of
    the pins smaller in diameter and circular" and then measured at 5 of 15
    against the kite's 11 of 14. spec.py carries that A/B and the reason.

    Both start at the CROWN and run clockwise, so the winding and the meaning of
    index 0 match every section this file has ever emitted and nothing
    downstream can tell which one is live.

    The circle's facet count is a multiple of four, which is what puts a vertex
    at 0/180 degrees (so the widest half-width is exactly PEG_R, the number
    every lattice assert in spec.py is written against) and a vertex at 90 (so
    the crown is an EDGE and not a level face).

    THE SCALLOP IS A SCALE ON THE UPPER HALF ONLY. At depth ``y`` the crown
    reach is ``scallop_up(y)``, so every vertex above the equator is scaled by
    ``scallop_up(y) / PEG_R`` and every vertex on or below it is left alone.
    The result is a barrel waisted along its own length; the equator - and
    therefore the section's x footprint - is identical at every station, which
    is the property the whole lattice depends on.

    ``build_peg`` (visual) and ``build_prism`` (cage) both call this, so mesh
    and collision cannot disagree about what a peg is - which was the single
    biggest risk reducer of the 2026-08-14 round and is not being given up for
    a more interesting shape.
    """

    up = scallop_up(y)
    if spec.PEG_SECTION_SHAPE == "circle":
        count = spec.PEG_FACETS
        scale = up / spec.PEG_R
        ring: list[tuple[float, float]] = []
        for index in range(count):
            # Clockwise from the crown: index 0 is the apex, count//4 is +x.
            angle = math.pi / 2.0 - 2.0 * math.pi * index / count
            px = spec.PEG_R * math.cos(angle)
            pz = spec.PEG_R * math.sin(angle)
            if pz > 1e-12:
                pz *= scale
            ring.append((cx + px, cz + pz))
    elif spec.PEG_SECTION_SHAPE == "dee":
        # THE D, and what ships. A true semicircle above the equator - which is
        # the entire silhouette from the front, the drive-in apron and every
        # frame of a car falling past - joined to the KITE's shallow 0.40 m
        # shed below it. The circle lost 5 of 15 on its BELLY, not its crown
        # (spec.PEG_SECTION_SHAPE carries that A/B), so this keeps the belly
        # and spends only the crown.
        #
        # PEG_FACETS is a multiple of four, so `half` is even and there is a
        # real vertex AT the crown - the same reason the circle needs it, and
        # the same failure if it is dropped: an even split would put a wide
        # DEAD LEVEL face on top, which the two-contact law says holds a car at
        # any friction.
        half = spec.PEG_FACETS // 2
        mid = half // 2
        arc = []
        for k in range(half + 1):
            angle = math.pi * k / half  # +x round the top to -x
            # z uses `up`, not PEG_R_Z_UP, so the scallop scales the whole arc
            # and the equator (sin = 0) is untouched at every station. That is
            # the invariant the entire lattice is written against.
            arc.append((cx + spec.PEG_R * math.cos(angle), cz + up * math.sin(angle)))
        # Clockwise from the crown: crown -> +x, the belly vertex, then -x back
        # up to the crown. Same winding and the same index-0-is-the-crown
        # convention as the other two, so everything downstream is blind to
        # which section is live.
        ring = (
            [arc[i] for i in range(mid, -1, -1)]
            + [(cx, cz - spec.PEG_R_Z_DN)]
            + [arc[i] for i in range(half, mid, -1)]
        )
    else:
        # THE KITE. Same winding and the same index-0-is-the-crown convention,
        # so everything downstream is blind to which one is live. The tall
        # crown and the SHALLOW belly are the whole point - see
        # PEG_SECTION_SHAPE in spec.py for the live A/B history.
        ring = [
            (cx, cz + up),
            (cx + spec.PEG_R, cz),
            (cx, cz - spec.PEG_R_Z_DN),
            (cx - spec.PEG_R, cz),
        ]
    if abs(cx) < HW - spec.PEG_R:
        return ring

    # F6, THE WALL-CORNER GUSSET (2026-08-14c, re-derived for the circle).
    #
    # The comment that justified embedding the outer peg in the wall claimed a
    # crown TANGENT to a wall is safe, because the wall contact lands below the
    # crown so its moment adds to tipping the car off. That is true of the
    # INBOARD flank and backwards for the outboard one, and the built geometry
    # was never tangent anyway: the peg centre is 0.60 m inboard of the wall
    # plane on the kite lattice (0.75 on the circle's),
    # plane, so the outboard flank descends from the crown to meet the wall and
    # leaves a re-entrant notch opening UPWARD, running the full 6.90 m board
    # depth, on both sides of every even row. Live build 36 duly parked a car
    # in one at (-10.94, 8.96), and the 2-D wrench-cone scan reproduces it: 15
    # stable poses with contacts on `peg_bottom_outer + wall`, and halving the
    # wall friction only takes that to 13, which is the signature of a THROAT
    # carried by normal forces rather than a SHELF carried by friction.
    #
    # The gusset fills the notch so wall and peg present one continuous
    # obstacle. It deliberately does NOT do so with a horizontal ledge: a level
    # surface is the one thing the two-contact law says holds a car outright at
    # any friction, and a scan of four wall-fillet geometries showed every one
    # of them TRADING the strut for a larger family of new stable poses
    # (190 -> 226-232). So the fill sheds INBOARD from a high point on the wall
    # plane, and the two circle vertices it swallows are dropped rather than
    # left as reflex corners.
    wall_x = math.copysign(HW, cx)
    shed = abs(wall_x - cx)  # 0.60 on the kite lattice, 0.75 on the circle
    wall_hi = (wall_x, cz + up + shed)
    # The crown (index 0) and the 45 deg vertex on the wall side are both
    # INSIDE the hull once wall_hi exists - proven below rather than assumed,
    # because a section with a reflex vertex would silently break
    # extruded_profile's fan caps and build_prism's per-edge bands.
    count = len(ring)
    if spec.PEG_SECTION_SHAPE in ("circle", "dee"):
        # The 45-deg shed from the wall swallows the crown and every vertex
        # between it and the equator on the wall side, so those are DROPPED
        # rather than left as reflex corners. The equator vertex is at ring
        # index PEG_FACETS // 4 for both round sections - the circle has
        # PEG_FACETS/4 arc steps from crown to +x, and the D's semicircle has
        # (PEG_FACETS/2)/2, which is the same number. Deriving it from
        # len(ring) instead was wrong and silently left the D non-convex.
        equator = spec.PEG_FACETS // 4
        if cx > 0:
            drop = {0} | {index for index in range(1, equator)}
            section = [wall_hi] + [ring[i] for i in range(count) if i not in drop]
        else:
            drop = {0} | {index for index in range(count - equator + 1, count)}
            section = [ring[i] for i in range(count) if i not in drop] + [wall_hi]
    else:
        # The kite's crown is a sharp apex, so the 45 deg shed meets it without
        # a reflex corner and NOTHING is dropped: wall_hi is simply inserted on
        # the wall side. Original winding preserved (apex, +x, bottom, -x).
        drop = set()
        if cx > 0:
            section = [wall_hi, ring[1], ring[2], ring[3], ring[0]]
        else:
            section = [ring[0], ring[1], ring[2], ring[3], wall_hi]
    _assert_convex(section, cx)
    for index in sorted(drop):
        if not _strictly_inside(section, ring[index]):
            raise AssertionError(
                f"the wall-gusset peg section at x={cx} drops vertex {index} "
                f"at {ring[index]} but it is not inside the remaining hull"
            )
    return section


def _assert_convex(section: list[tuple[float, float]], cx: float) -> None:
    """extruded_profile fans its end caps from vertex 0 and build_prism emits
    one collision band per edge, so a non-convex section would silently make
    both wrong. The plain ring is convex by construction; the gusseted one is
    not, so prove it."""

    count = len(section)
    signs = set()
    for i in range(count):
        ax, az = section[i]
        bx, bz = section[(i + 1) % count]
        ccx, ccz = section[(i + 2) % count]
        cross = (bx - ax) * (ccz - az) - (bz - az) * (ccx - ax)
        if abs(cross) > 1e-9:
            signs.add(cross > 0)
    if len(signs) != 1:
        raise AssertionError(
            f"the wall-gusset peg section at x={cx} is not convex: "
            f"{[(round(a, 3), round(b, 3)) for a, b in section]}"
        )


def _strictly_inside(section: list[tuple[float, float]], point: tuple[float, float]) -> bool:
    """Is ``point`` strictly inside the convex polygon ``section``?"""

    count = len(section)
    px, pz = point
    signs = set()
    for i in range(count):
        ax, az = section[i]
        bx, bz = section[(i + 1) % count]
        cross = (bx - ax) * (pz - az) - (bz - az) * (px - ax)
        if abs(cross) <= 1e-9:
            return False
        signs.add(cross > 0)
    return len(signs) == 1


def divider_section(center_x: float, ridge_x: float) -> list[tuple[float, float]]:
    """Bin divider cross-section, bottom-left round to bottom-right."""

    left = [(center_x - hw, z) for hw, z in spec.DIVIDER_PROFILE]
    right = [(center_x + hw, z) for hw, z in reversed(spec.DIVIDER_PROFILE)]
    return left + [(ridge_x, spec.DIVIDER_RIDGE_Z)] + right


def rank_runs(rank: int) -> list[tuple[float, float]]:
    """The PROJECTED x-span of every collision run in a rank.

    P0.2's seam. Today a rank is a peg row and a run is one peg's span; after
    Phase 1 a rank is a set of inclined prisms and a run is one prism's
    projection onto x. Everything below is written against this signature so
    the proof does not have to be rewritten when the board is.
    """

    return spec.peg_row_runs(rank)


def rank_runs_lower_edge(rank: int) -> list[tuple[float, float]]:
    """The x-span of a rank's runs AT THEIR LOWER EDGE.

    An inclined run's ``[x0, x1]`` is a PROJECTION. That is conservative for
    the gate width - the projection is the widest the run ever is - and it is
    NOT conservative for the overlap test against the rank below, because a
    run's lower end sits closer to that rank than its projection suggests. So
    the interval algebra has to be run on both and the worse taken.

    On the shipped lattice a peg is a vertical prism, so the two spans are
    identical by construction and the second pass is a no-op that proves the
    plumbing rather than a new fact. That is deliberate: the machinery lands
    now, exercised, and Phase 1 only has to supply different numbers.
    """

    return spec.peg_row_runs(rank)


def _gates(runs: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return spec.runs_to_gates(runs, -HW, HW)


def _erode(gates: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Centres c whose [c - w/2, c + w/2] fits inside a gate."""

    half = spec.CAR_WIDTH / 2.0
    return [(a + half, b - half) for a, b in gates if b - a > spec.CAR_WIDTH]


def _intersect(
    first: list[tuple[float, float]], second: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    out = []
    for a, b in first:
        for c, d in second:
            lo, hi = max(a, c), min(b, d)
            if hi - lo > 1e-9:
                out.append((lo, hi))
    return out


# The recorded per-pair diagonal count, and THE RATCHET on it.
#
# The per-pair counts below are PRINTED because the whole-board invariant is
# the one that has to hold. Printing them and asserting nothing, though, meant
# a change could take a pair from 5398 to 6001 - the board getting strictly
# easier to thread diagonally - and the build would pass while the log said so
# in a line nobody reads. DESIGN.md calls the equivalent number on the
# replacement gauge "the one number that carries the argument".
#
# So a pair may only get TIGHTER than the value recorded here. Raising this
# constant is allowed and is the point: it must be a decision someone writes
# down, not a number that drifts. One place, not seven literals in a report.
DIAGONAL_PAIR_CEILING = 5398

# vz0 steps in the ballistic sweep. vx is exact, so this is the only grid
# left in it; 2000 either side gives 4001 exact vx solves per launch site.
BALLISTIC_VZ_STEPS = 2000


def assert_no_clean_column() -> None:
    """No 2.0 m wide lane may clear TWO CONSECUTIVE ranks - vertical OR drifting.

    A single rank's gates are deliberately WIDER than a car since 2026-08-13
    (the player: "make the space between the plinko rollers so cars can more
    easily roll through the system and fall to the bottom") - threading one
    rank and caroming on is the whole point of a plinko board, and since
    2026-08-14 the gates are wider still, sized against the car's 5.148 m body
    CHORD rather than its 2.0 m width. What must never exist is a lane that
    clears a rank AND the staggered rank beneath it: that is a free chute from
    the crown to the bins.

    WHAT THIS PROVES, EXACTLY, so no prose downstream can inflate it: that a
    car cannot cross the field without touching at least ONE peg. A single
    glancing corner contact satisfies it. "No free chute" is fair; "the board
    randomises the car" is a different claim and nothing here supports it.

    WHY ``CAR_WIDTH`` HERE AND ``CAR_CHORD`` NEXT DOOR. The two asserts model
    the same car as two different objects, on purpose.
    ``assert_no_two_contact_rest`` uses the 5.148 m CHORD because a wedge does
    not care which way the car is pointing, so its worst case is the longest
    diameter. This one uses the 2.0 m WIDTH because a chute is something a car
    falls THROUGH, and the narrowest silhouette a falling car can present is
    its width - using the chord here would let a 2.5 m lane count as blocked
    when a car on its wheels would drop straight down it. Each assert takes
    the extreme that is conservative FOR ITS OWN question; neither is "the"
    car, and until this round only one of them said so.

    P0.2 (2026-08-18) replaced the 5 cm march with EXACT INTERVAL ALGEBRA and
    added the two things the march never covered:

    * **The vertical proof is now exact.** Erode each rank's gate set by the
      car's half-width, intersect the eroded sets of two consecutive ranks, and
      the invariant holds iff the intersection is EMPTY. O(ranks x gates^2)
      against the march's O(ranks x 441), and no quantisation to be wrong at.
    * **The diagonal.** The march proved nothing about a car drifting sideways
      as it falls, and with gates wider than the car a diagonal is EASIER than
      a vertical. The chute delivers the car at ~11 m/s with |vx| > |vz|, so
      the drift is real. Generalised: a straight path of slope s clears ranks k
      and k+1 iff ``S_{k+1} n (S_k + s*dz)`` is non-empty. Swept over
      |s| <= 3.000 m/m in 1 mm steps.
    * **The lower-edge span.** An inclined run's projection is not where its
      bottom is; both spans are tested and the worse taken. On the shipped
      lattice a peg is a vertical prism, so ``rank_runs`` and
      ``rank_runs_lower_edge`` have IDENTICAL BODIES and the second pass proves
      the plumbing, not a second fact. Two lines in the report are not two
      independent confirmations, and the report now says which is which.

    WHAT IS EXACT AND WHAT IS STILL A GRID, because the first cut of this
    docstring said "a grid scan can step over a lane narrower than its own
    step, and this cannot", and that was half true. What was removed is the
    grid in the ENTRY COORDINATE: the sweep intersects intervals in x, so no
    lane can be stepped over in x, at any width. The SLOPE s is still a 1 mm
    grid and the identical objection applies to it; the ballistic block below
    still steps ``vz0``, though it is now exact in ``vx``. The prefix ladder
    printed below is the honest answer to how much that matters - it shows the
    board closing with a whole rank in hand rather than by a hair.

    **THE DIAGONAL INVARIANT IS A WHOLE-BOARD ONE, NOT A PAIR ONE, AND SAYING
    SO IS THE POINT.** A 3 m/m drift crosses 12 m in one 4 m row pitch, so of
    course it can walk from one gate to the next - EVERY consecutive pair on
    this board admits diagonals, and on the replacement gauge too (the design's
    own sweep reports 5152 of 6001 slopes for its pair 1/2). What must not
    exist is a straight line that threads the board END TO END, and that is
    what is asserted. The per-pair and per-family counts are PRINTED, and
    RATCHETED against ``DIAGONAL_PAIR_CEILING`` so that a silent loosening is
    a build failure rather than a line in a log.
    * **And the achievable family, which is the one that decides it.** Slopes
      the board permits are not slopes the machine can produce. The release
      ejects the car over the deck lip and it slides a FRICTIONLESS 40 deg
      apron from APRON_Z_HI to APRON_Z_LO, so its exit speed is DERIVED - from
      the eject clamp AND the kicker that fires at that exact point - and
      swept ballistically against every rank below the exit, over BOTH signs
      of the vertical component, and from the deck lip in free flight as well
      as from the apron exit, because the kicker's whole job is to make the
      car miss the apron.

    THE 441-STEP MARCH IS KEPT, rebuilt as a pointwise cross-check of the
    interval primitives rather than as a second verdict - see the comment at
    it for why the old form could not fire.

    There are no wall-stub spans any more. The side channel is closed by the
    even rows' outermost peg reaching into the wall slab, which shows up here
    as an ordinary run span running past +/-HW. The ODD rows do have a 3.30 m
    opening against each wall, which is not a free chute (the even rows above
    and below close it, which is what this function proves) but IS a FORBIDDEN
    aperture - see FORBIDDEN_EXEMPTIONS in spec.py.
    """

    ranks = list(range(spec.PEG_ROWS))
    slopes = [milli / 1000.0 for milli in range(-3000, 3001)]
    report: list[str] = []
    for label, provider in (
        ("projected span", rank_runs),
        ("lower-edge span", rank_runs_lower_edge),
    ):
        eroded = [_erode(_gates(provider(rank))) for rank in ranks]

        # ---- exact vertical proof, at PAIR strength ----------------------
        for index in range(len(ranks) - 1):
            overlap = _intersect(eroded[index], eroded[index + 1])
            if overlap:
                raise AssertionError(
                    f"clean vertical column through ranks {index}/{index + 1} "
                    f"({label}) over centres {[(round(a, 3), round(b, 3)) for a, b in overlap]}: "
                    "the half-pitch stagger no longer blocks a car-wide lane "
                    "through consecutive ranks"
                )

        # ---- the drift sweep ---------------------------------------------
        # Each family is anchored at ITS OWN first rank. Anchoring a lower
        # family at the top of the board asks a different and much smaller
        # question ("...having already threaded everything above"), and it
        # returns a wrong answer that reads as a stronger pass.
        #
        # Returns (slope, widest window) for each admitted slope, because the
        # WIDTH is the margin and a count on its own hides it.
        def admits(
            family: list[int], bands: list[list[tuple[float, float]]] = eroded
        ) -> list[tuple[float, float]]:
            z0 = spec.PEG_ROW_Z[family[0]]
            out = []
            for slope in slopes:
                window = None
                for rank in family:
                    shift = slope * (z0 - spec.PEG_ROW_Z[rank])
                    band = [(a - shift, b - shift) for a, b in bands[rank]]
                    window = band if window is None else _intersect(window, band)
                    if not window:
                        break
                if window:
                    out.append((slope, max(b - a for a, b in window)))
            return out

        whole = admits(ranks)
        if whole:
            raise AssertionError(
                f"a straight diagonal of slope {whole[0][0]:+.3f} m/m threads all "
                f"{len(ranks)} ranks ({label}): a drifting car has an end-to-end "
                "free chute the vertical proof cannot see"
            )
        # MEASURED, not typed. This line used to carry a literal 0, correct
        # only because the raise above precedes it - the build log's headline
        # figure was a constant, and it would have gone on printing 0 for as
        # long as the raise kept firing first.
        report.append(
            f"    {label:16s} all {len(ranks)} ranks: "
            f"{len(whole)} of {len(slopes)} slopes"
        )

        # ---- THE MARGIN, not just the verdict ----------------------------
        # Only the pairs and the whole board were reported, so a change that
        # cost one rank of closure would jump straight from "0 of 6001" to a
        # firing assert with no warning in between. The prefix ladder is that
        # warning: how deep a diagonal gets before the board stops it, and how
        # wide the last surviving lane is.
        closes_at, widest, surviving = len(ranks) + 1, 0.0, 0
        for count in range(1, len(ranks) + 1):
            admitted = admits(ranks[:count])
            if not admitted:
                closes_at = count
                break
            widest = max(width for _, width in admitted)
            surviving = len(admitted)
        report.append(
            f"    {label:16s} margin: a diagonal survives the first "
            f"{closes_at - 1} of {len(ranks)} ranks and rank index "
            f"{closes_at - 1} closes it ({surviving} of {len(slopes)} slopes "
            f"still admitted there, widest lane {widest:.3f} m) - ONE RANK "
            f"of headroom is what this line exists to show"
        )

        for index in range(len(ranks) - 1):
            admitted = admits([index, index + 1])
            bound = (
                "none"
                if not admitted
                else f"|s| <= {max(abs(admitted[0][0]), abs(admitted[-1][0])):.3f}"
            )
            if len(admitted) > DIAGONAL_PAIR_CEILING:
                raise AssertionError(
                    f"pair {index}/{index + 1} ({label}) admits {len(admitted)} "
                    f"of {len(slopes)} diagonal slopes, above the recorded "
                    f"ceiling {DIAGONAL_PAIR_CEILING}: the board just got "
                    "EASIER to thread diagonally. The whole-board invariant "
                    "above still holds, so this is the ratchet refusing a "
                    "silent loosening, not a free chute - raise the ceiling "
                    "deliberately if the loosening is intended"
                )
            report.append(
                f"    {label:16s} pair {index}/{index + 1}: "
                f"{len(admitted):5d} of {len(slopes)} ({bound})"
            )

        # ---- the ACHIEVABLE family: a ballistic launch off the chute -----
        # Derived end to end, and derived from THE KICKER, which is the thing
        # that actually sets the speed.
        #
        # CORRECTED TWICE, and the second correction was still wrong. The
        # first cut built ONE exit speed out of eject_speed_max_mps and called
        # the result "the whole physical launch family"; D5 widened it to the
        # eject CLAMP band [10.74, 11.35] over nine speeds. Both missed the
        # same thing: the eject field is not the last thing that touches the
        # car. THE KICKER fires at exactly this point (BEHAVIOR's lip_kick_*,
        # and spec.py's opening paragraph: it "throws it airborne over the
        # convex hinge lip") and it ADDS to whatever the field has already
        # built - up to lip_kick_scale_max x (4.0 inboard, 2.6 up) on top of
        # the clamped 4.5. So the lip bound is hypot(4.5 + 1.6*4.0, 1.6*2.6)
        # = 11.667 m/s and the apron exit reaches 15.645, 37.8% above the band
        # that was being swept.
        #
        # The unstick hop is deliberately NOT summed in: updateReleasing
        # suppresses it inside the lip zone precisely so the two vertical
        # impulses cannot add, and 2.0 < 1.6 * 2.6 in any case.
        #
        # And vz0 used to be forced NEGATIVE, so the one launch the kicker
        # exists to produce - the car going airborne, UPWARD, over the convex
        # break - was the one launch never swept. Both signs now.
        #
        # TWO LAUNCH SITES, because "the car slides the apron" is an
        # assumption the kicker was built to break. The apron exit is the
        # sliding case; the deck lip at (APRON_X_HI, APRON_Z_HI) is the case
        # where the car clears the chute entirely and flies at every rank.
        #
        # THE GRID IS GONE FROM vx TOO. x at rank r is x0 + vx * t_r(vz0) and
        # t_r does not depend on vx, so for a fixed vz0 the admissible vx set
        # is an exact intersection of intervals, and the speed band enters as
        # an interval in vx rather than as a sampled ring. 225 sampled
        # velocities became 4001 exact solves. vz0 is still stepped.
        #
        # It changes no verdict - 0 clean over the widened band, both spans,
        # both sites - which is the cheapest possible moment to close a hole,
        # not a reason to leave it open.
        v_clamp = spec.BEHAVIOR["eject_speed_max_mps"]
        assert spec.BEHAVIOR["eject_speed_mps"] <= v_clamp, (
            "the nominal eject speed exceeds its own clamp"
        )
        kick = spec.BEHAVIOR["lip_kick_scale_max"]
        v_lip = math.hypot(
            v_clamp + kick * spec.BEHAVIOR["lip_kick_x_mps"],
            kick * spec.BEHAVIOR["lip_kick_z_mps"],
        )
        assert v_lip > v_clamp, (
            "the kicker no longer adds to the eject field; if it has been "
            "deleted or re-derived, this bound is no longer the right one"
        )
        drop_to_exit = spec.APRON_Z_HI - spec.APRON_Z_LO
        v_exit_lo = math.sqrt(2 * 9.81 * drop_to_exit)
        v_exit_hi = math.sqrt(v_lip**2 + 2 * 9.81 * drop_to_exit)

        def ballistic(
            x0: float,
            z0: float,
            v_lo: float,
            v_hi: float,
            family: list[int],
            bands: list[list[tuple[float, float]]] = eroded,
            steps: int = BALLISTIC_VZ_STEPS,
        ) -> tuple[int, int, float]:
            """(clean launches, deepest rank reached, widest vx window there)."""

            clean, best = 0, (0, 0.0)
            for index in range(-steps, steps + 1):
                vz0 = v_hi * index / steps
                outer = math.sqrt(max(v_hi**2 - vz0**2, 0.0))
                inner = math.sqrt(max(v_lo**2 - vz0**2, 0.0))
                if outer <= inner:
                    continue
                window = (
                    [(-outer, outer)]
                    if inner <= 1e-12
                    else [(-outer, -inner), (inner, outer)]
                )
                held, depth = window, 0
                for rank in family:
                    fall = z0 - spec.PEG_ROW_Z[rank]
                    flight = (vz0 + math.sqrt(vz0**2 + 2 * 9.81 * fall)) / 9.81
                    window = _intersect(
                        window,
                        [((a - x0) / flight, (b - x0) / flight) for a, b in bands[rank]],
                    )
                    if not window:
                        break
                    held, depth = window, depth + 1
                if depth == len(family):
                    clean += 1
                width = max((b - a for a, b in held), default=0.0)
                if (depth, width) > best:
                    best = (depth, width)
            return clean, best[0], best[1]

        below = [rank for rank in ranks if spec.PEG_ROW_Z[rank] < spec.APRON_Z_LO]
        for site, x0, z0, v_lo, v_hi, family in (
            ("apron exit", spec.APRON_X_LO, spec.APRON_Z_LO, v_exit_lo, v_exit_hi, below),
            ("deck lip  ", spec.APRON_X_HI, spec.APRON_Z_HI, 0.0, v_lip, ranks),
        ):
            clean, deepest, widest_v = ballistic(x0, z0, v_lo, v_hi, family)
            if clean:
                raise AssertionError(
                    f"{clean} of {2 * BALLISTIC_VZ_STEPS + 1} physically achievable "
                    f"launches from the {site.strip()} ({label}) fall clean "
                    f"through every one of the {len(family)} ranks below it: "
                    "the release itself can produce a free chute"
                )
            report.append(
                f"    {label:16s} ballistic from the {site} "
                f"(x {x0:5.2f}, z {z0:5.2f}, |v| {v_lo:.3f}-{v_hi:.3f} m/s, "
                f"both signs of vz0, {len(family)} ranks below it): 0 clean of "
                f"{2 * BALLISTIC_VZ_STEPS + 1} exact vx solves; deepest {deepest} of "
                f"{len(family)} ranks (widest vx window {widest_v:.3f} m/s)"
            )
    print("[free chute] no vertical lane over any consecutive pair; and")
    for line in report:
        print(line)

    # ---- the march, rebuilt as a REAL cross-check ------------------------
    #
    # AS SHIPPED IT COULD NOT FIRE. It asserted that no 441-step CAR_WIDTH
    # window clears two consecutive ranks - which, on a lattice whose gates
    # are 5.4 m and 3.3 m wide, needs a gate of width EXACTLY CAR_WIDTH with a
    # run boundary landing exactly on a 0.05 m node. It was dead code carrying
    # a message about an unreachable state, and what it cross-checked was only
    # the VERTICAL path: the oldest part of this function, and the one part
    # P0.2 did not add.
    #
    # It is now a POINTWISE agreement check on the primitives everything else
    # is built from. At every march node the marching test ("does a CAR_WIDTH
    # window starting here miss every run in BOTH ranks?") and the interval
    # test ("is that window's centre in the eroded intersection?") must return
    # the same answer. They share no code - one walks raw runs, the other
    # walks _gates/_erode/_intersect - so a disagreement is an off-by-one in
    # exactly one of them, which is the whole reason to keep two.
    #
    # AND THE DIAGONAL GETS ONE TOO, in the only direction that is sound: a
    # grid scan over entry x can MISS a lane the interval algebra finds, but
    # it can never invent one. So grid-admits must IMPLY interval-admits, and
    # a violation means the interval sweep is dropping lanes. That is exactly
    # the failure mode found in the design document's own script, where a
    # 10 mm entry-x grid undercounted two of its published pair figures.
    ranks = list(range(spec.PEG_ROWS))
    rows = [rank_runs(rank) for rank in ranks]
    eroded = [_erode(_gates(rank_runs(rank))) for rank in ranks]
    steps = int((2 * HW - spec.CAR_WIDTH) / 0.05) + 1
    assert steps == 441, f"the march is {steps} steps, not the recorded 441"
    nodes = 0
    for row in range(spec.PEG_ROWS - 1):
        overlap = _intersect(eroded[row], eroded[row + 1])
        for step in range(steps):
            left = -HW + step * 0.05
            right = left + spec.CAR_WIDTH
            centre = left + spec.CAR_WIDTH / 2.0
            marched = all(
                not any(not (b <= left or a >= right) for a, b in spans)
                for spans in (rows[row], rows[row + 1])
            )
            algebraic = any(a - 1e-9 <= centre <= b + 1e-9 for a, b in overlap)
            nodes += 1
            if marched != algebraic:
                raise AssertionError(
                    f"THE MARCH AND THE INTERVAL ALGEBRA DISAGREE at peg rows "
                    f"{row}/{row + 1}, x={left:.2f}: the 0.05 m march says "
                    f"{'clear' if marched else 'blocked'} and the eroded "
                    f"intersection says {'clear' if algebraic else 'blocked'}. "
                    "One of _gates, _erode or _intersect has an off-by-one"
                )
    slopes = [milli / 1000.0 for milli in range(-3000, 3001)]
    z0 = spec.PEG_ROW_Z[0]
    sampled = 0
    for slope in slopes[::100]:
        sampled += 1
        window = None
        for rank in ranks:
            shift = slope * (z0 - spec.PEG_ROW_Z[rank])
            band = [(a - shift, b - shift) for a, b in eroded[rank]]
            window = band if window is None else _intersect(window, band)
            if not window:
                break
        by_algebra = bool(window)
        by_grid = any(
            all(
                any(
                    a <= milli / 1000.0 + slope * (z0 - spec.PEG_ROW_Z[rank]) <= b
                    for a, b in eroded[rank]
                )
                for rank in ranks
            )
            for milli in range(-13000, 13001, 10)
        )
        if by_grid and not by_algebra:
            raise AssertionError(
                f"a 10 mm entry-x grid finds a whole-board diagonal at slope "
                f"{slope:+.3f} m/m that the interval sweep does not: the "
                "interval sweep is DROPPING lanes, which is the one direction "
                "this cross-check cannot forgive"
            )
    print(
        f"    cross-checks: the 0.05 m march and the interval algebra agree at "
        f"all {nodes} nodes (VERTICAL path only - the diagonal and ballistic "
        f"paths have no second implementation); and over {sampled} sampled "
        f"slopes a 10 mm entry-x grid finds no whole-board diagonal the "
        f"interval sweep missed"
    )


def assert_no_two_contact_rest() -> None:
    """No neighbouring peg pair may offer a car a TWO-CONTACT rest.

    The sibling of ``assert_no_clean_column``, and the other half of the same
    decision: that one proves the field is not a free chute, this one proves
    it is not a trap. Both have to be walked over the REAL row layout, because
    the defect they guard is reopened by a COLUMN COUNT change - which changes
    neither PEG_PITCH_X nor PEG_R, so spec.py's own asserts would not notice.

    THE TWO-CONTACT LAW (spec.py carries the derivation): with no torque
    available, and since 2026-08-14h with the pegs on FRICTIONLESS so no face
    of any slope is a rest at all, a lone crown rolls out and the only rests
    the field can offer a car are

      * a flat car face TABLING across two crowns - killed by crown spacing
        exceeding the car's body chord, and
      * a converging THROAT pinching the car between two adjacent flanks -
        killed by (spacing - 2 R) exceeding the same chord.

    Both are measured against CAR_CHORD rather than CAR_WIDTH, because a wedge
    does not care which way the car is pointing.
    """

    # The lattice asserts in spec.py are all written against PEG_R, which is
    # only legitimate while PEG_R really is the section's widest half-width.
    # A shaped section makes that an assumption rather than a definition, so
    # prove it here against the SECTION ITSELF: if someone reshapes the peg so
    # its widest point is not at +/-PEG_R, every throat number in spec.py
    # silently starts measuring the wrong thing.
    #
    # Probed at EVERY STATION, not just the middle one, because the scallop is
    # a scale on the upper half and the whole safety argument for it is that it
    # never touches x. One station could not catch a leak; all of them can.
    for station in scallop_stations():
        probe = peg_section(0.0, 0.0, station)
        widest = max(abs(px) for px, _ in probe)
        if abs(widest - spec.PEG_R) > 1e-9:
            raise AssertionError(
                f"the peg section is {widest:.3f} m half-wide at depth "
                f"{station:.3f} but spec.PEG_R is {spec.PEG_R}: every "
                "throat/lane/embedment assert is measuring a width the peg "
                "does not have"
            )
        _assert_convex(probe, 0.0)
        # ...and when the circle is live it really IS a circle: every vertex on
        # or below the equator sits exactly PEG_R from the centre. The upper
        # half is deliberately scaled by the scallop, so only the lower half
        # can be checked this way - which is also the half that carries the
        # widest point.
        if spec.PEG_SECTION_SHAPE == "circle":
            for px, pz in probe:
                if pz <= 1e-12 and abs(math.hypot(px, pz) - spec.PEG_R) > 1e-9:
                    raise AssertionError(
                        f"peg section vertex {(round(px, 4), round(pz, 4))} is "
                        f"{math.hypot(px, pz):.4f} m from the axis, not the "
                        f"{spec.PEG_R} m radius the section is supposed to be"
                    )

    for row in range(spec.PEG_ROWS):
        xs = peg_row_xs(row)
        for index in range(len(xs) - 1):
            crown = xs[index + 1] - xs[index]
            throat = crown - 2 * spec.PEG_R
            if crown <= spec.CAR_CHORD:
                raise AssertionError(
                    f"peg row {row} crowns at x={xs[index]:.2f}/"
                    f"{xs[index + 1]:.2f} are {crown:.2f} m apart, within the "
                    f"{spec.CAR_CHORD:.3f} m car chord: a car can table across "
                    "them"
                )
            if throat <= spec.CAR_CHORD:
                raise AssertionError(
                    f"peg row {row} throat between x={xs[index]:.2f} and "
                    f"x={xs[index + 1]:.2f} is {throat:.2f} m, within the "
                    f"{spec.CAR_CHORD:.3f} m car chord: the pair can wedge a car"
                )


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def extruded_profile(
    name: str,
    section: list[tuple[float, float]],
    y0: float,
    y1: float,
    material,
    *,
    uv_meters: float = 1.8,
    section_b: list[tuple[float, float]] | None = None,
) -> bpy.types.Object:
    """Closed prism from an (x, z) section swept along y, normals outward.

    ``section_b`` makes it a LOFT rather than an extrusion - the two ends may
    differ - which is what lets a peg's crown follow the scallop while its x
    footprint stays identical at every station.
    """

    far = section_b if section_b is not None else section
    assert len(far) == len(section), "loft ends must share a vertex count"
    count = len(section)
    verts = [(x, y0, z) for x, z in section] + [(x, y1, z) for x, z in far]
    faces = []
    for i in range(count):
        j = (i + 1) % count
        faces.append((i, j, j + count, i + count))
    faces.append(tuple(range(count - 1, -1, -1)))
    faces.append(tuple(range(count, 2 * count)))
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    working = bmesh.new()
    working.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(working, faces=working.faces)
    working.to_mesh(mesh)
    working.free()
    bk.add_metric_box_uvs(obj, meters_per_tile=(uv_meters, uv_meters))
    bk.assign_material(obj, material)
    return obj


def revolved_solid(
    name: str,
    loop: list[tuple[float, float]],
    material,
    *,
    origin: tuple[float, float, float],
    axis: tuple[float, float, float],
    segments: int = 20,
    uv_meters: float = 0.9,
    smooth: bool = True,
) -> bpy.types.Object:
    """Solid of revolution: a CLOSED ``(t, r)`` loop swept about ``axis``.

    ``t`` runs along +axis from ``origin`` and ``r`` is the distance off it.
    The loop is CLOSED, which is the whole reason this exists rather than a
    stack of ``bk.add_cone``s: a PA horn bell is a SHELL - outer flare, throat,
    inner flare, rolled lip - and the reference photo's badge is only visible
    because you can see down the inside of the bell. A capped cone can never
    show that, and four cones stacked to fake a flare shade with visible steps
    because they are four separate objects under the 38 deg auto-smooth.

    A station with ``r == 0`` collapses to one pole vertex and its neighbouring
    ring fans to it, so a capped cylinder and a dome are the same call.
    ``segments=6`` makes a hex nut out of the same machinery.
    """

    ax = mathutils.Vector(axis).normalized()
    seed = mathutils.Vector((0.0, 0.0, 1.0))
    if abs(ax.dot(seed)) > 0.9:
        seed = mathutils.Vector((1.0, 0.0, 0.0))
    u = ax.cross(seed).normalized()
    v = ax.cross(u)
    base = mathutils.Vector(origin)

    verts: list[tuple[float, float, float]] = []
    rings: list[list[int]] = []
    for t, r in loop:
        centre = base + ax * t
        if abs(r) < 1e-6:
            rings.append([len(verts)])
            verts.append(tuple(centre))
            continue
        ring = []
        for k in range(segments):
            angle = 2.0 * math.pi * k / segments
            point = centre + u * (r * math.cos(angle)) + v * (r * math.sin(angle))
            ring.append(len(verts))
            verts.append(tuple(point))
        rings.append(ring)

    faces = []
    count = len(rings)
    for index in range(count):
        a_ring, b_ring = rings[index], rings[(index + 1) % count]
        if len(a_ring) == 1 and len(b_ring) == 1:
            continue
        if len(a_ring) == 1:
            apex = a_ring[0]
            for k in range(segments):
                faces.append((apex, b_ring[k], b_ring[(k + 1) % segments]))
        elif len(b_ring) == 1:
            apex = b_ring[0]
            for k in range(segments):
                faces.append((a_ring[k], a_ring[(k + 1) % segments], apex))
        else:
            for k in range(segments):
                j = (k + 1) % segments
                faces.append((a_ring[k], a_ring[j], b_ring[j], b_ring[k]))

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    working = bmesh.new()
    working.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(working, faces=working.faces)
    working.to_mesh(mesh)
    working.free()
    bk.add_metric_box_uvs(obj, meters_per_tile=(uv_meters, uv_meters))
    bk.assign_material(obj, material)
    if smooth:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        try:
            bpy.ops.object.shade_auto_smooth(angle=math.radians(38.0))
        except Exception:
            bpy.ops.object.shade_smooth()
        obj.select_set(False)
    return obj


def sign_plate(name: str, center, width: float, height: float, material):
    """A -Y facing plate whose display face carries authored 0..1 UVs.

    ``bk.add_box`` leaves Blender's default cube UVs, which are a CROSS
    unwrap - measured 0.125..0.875 in u - so a marquee texture mapped through
    them samples a sub-rectangle and the lettering is cropped. The display
    face therefore gets hand-authored UVs: u grows with authored +x and v
    with +z. Both conventions were checked rather than guessed: the world
    transform is a 180 deg rotation about Z, so a viewer facing the prop's
    front sees authored +x to their right exactly as the Blender preview
    camera does, and BeamNG samples v = 0 from the image bottom, which is
    also where Blender puts it. Every other face is pinned to a background
    texel so it shows plain panel colour instead of sliced type.
    """

    obj = bk.add_box(name, center, (width, 0.06, height), material, bevel=0.0)
    mesh = obj.data
    layer = mesh.uv_layers.active or mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        display = polygon.normal[1] < -0.9
        for loop_index in polygon.loop_indices:
            if not display:
                layer.data[loop_index].uv = (0.5, 0.02)
                continue
            # Mesh vertices are OBJECT-LOCAL (add_box applies scale but not
            # location), so they are already centred on the plate.
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            layer.data[loop_index].uv = (
                co[0] / width + 0.5,
                co[2] / height + 0.5,
            )
    return obj


# Every peg is drawn as TWO prisms sharing one section: a copper head at the
# viewer's end and a dark steel shank behind it. That is what a pachinko pin
# looks like, and it is also the cheapest fix for the review's finding that
# the peg field was invisible - two dark bands on a cream board instead of one
# near-white smear. The head length is 0.55 m of the 6.90 m depth, so from
# straight on the copper end cap (2.15 m2 of kite) dominates and from an
# oblique eye the dark shank does.
# ---------------------------------------------------------------------------
# Payout marker geometry. The rail hangs in front of the value plates (whose
# front face is at DIVIDER_Y_FRONT - 0.75) so the pointer never occludes the
# numbers it points at, and high enough that the drive-out apron passes 5 m
# underneath it.
# ---------------------------------------------------------------------------
MARKER_RAIL_Y = spec.DIVIDER_Y_FRONT - 0.95  # -7.45
MARKER_RAIL_Z = RIDGE + 3.00  # 8.00, clear of the fascia's 6.10 top
MARKER_BODY_Y = MARKER_RAIL_Y - 0.30  # flush against the rail's front face
# The pointer's tip stops 7 cm above the value plaques' copper frames (the
# round-4 plaques grow DOWNWARD from a fixed top line, so every frame top
# still sits at RIDGE + 0.78 = 5.78), so it indicates the number instead of
# covering it.
MARKER_TIP_Z = RIDGE + 0.85

# ---------------------------------------------------------------------------
# Tip ratchet. Both halves live in the 0.15 m gap between the deck's +Y edge
# (DECK_HALF_Y = 3.30) and the shaft's back collision plane (DY = 3.45): the
# -Y side is the drive-in lane and nothing may stand in it.
# ---------------------------------------------------------------------------
RATCHET_R_ROOT = 1.25
RATCHET_R_OUT = 1.62
RATCHET_RACK_Y = spec.DECK_HALF_Y + 0.035  # 3.335 -> spans 3.30 .. 3.37
RATCHET_PAWL_Y = spec.DECK_HALF_Y + 0.11  # 3.41 -> spans 3.38 .. 3.44


def ratchet_section(
    hinge_x: float,
    hinge_z: float,
    detents,
    *,
    start_deg: float = -12.0,
    end_deg: float | None = None,
    tooth_half_deg: float = 3.2,
    step_deg: float = 1.0,
) -> list[tuple[float, float]]:
    """Toothed sector about the tipper hinge, one tooth per detent angle.

    Star-shaped about the hinge point, which is vertex 0, so
    ``extruded_profile``'s fan cap is valid by construction.

    ``end_deg`` is DERIVED from the detent ladder, never hardcoded. It used to
    be a bare ``60.0`` while the ladder ended at 68 deg, so the last tooth -
    the one the deck actually stops on at full tip, i.e. the pawl's position
    at the climax of the release - was simply never cut and the pawl pointed
    at air. ``spec``'s own ``tip_full_deg == tip_detents[-1]`` assert cannot
    see this number, which is exactly why it needs its own.
    """

    if end_deg is None:
        end_deg = max(detents) + tooth_half_deg + 4.0
    assert end_deg >= max(detents) + tooth_half_deg, (
        f"ratchet rack ends at {end_deg} deg but the last detent tooth is at "
        f"{max(detents)} deg (+/-{tooth_half_deg}): the final tooth would not be cut"
    )
    points = [(hinge_x, hinge_z)]
    steps = int(round((end_deg - start_deg) / step_deg))
    for index in range(steps + 1):
        angle = start_deg + index * step_deg
        radius = RATCHET_R_ROOT
        for tooth in detents:
            if abs(angle - tooth) <= tooth_half_deg:
                radius = RATCHET_R_OUT
                break
        theta = math.radians(angle)
        points.append(
            (hinge_x + radius * math.cos(theta), hinge_z + radius * math.sin(theta))
        )
    return points

PEG_HEAD_LEN = 0.55
# The two prisms OVERLAP by 1 cm instead of meeting on a shared plane: two
# coplanar double-sided caps z-fight, an overlap is invisible.
PEG_HEAD_LAP = 0.01


def build_peg(name: str, cx: float, cz: float, materials, objects: list) -> None:
    """Copper head + dark steel shank, as a chain of SCALLOPED segments.

    The peg used to be two prisms of constant section, which is what made its
    crown a 6.9 m knife-edge. It is now built station to station so the crown
    follows scallop_up(). Segment ends are shared depths, so the cage twin
    welds at exactly the same y values via NodeStore's grid snap.

    The copper head keeps the front-most segment(s) so the cap still reads as a
    forged head rather than a stripe part-way down a wave.
    """

    stations = scallop_stations()
    head_back = -DY + PEG_HEAD_LEN
    for index in range(len(stations) - 1):
        y0, y1 = stations[index], stations[index + 1]
        copper = y1 <= head_back + 1e-6
        # The head/shank break is a real depth, so split whichever segment
        # straddles it rather than letting the material jump a station.
        # The head break is a station now (see scallop_stations), so a segment
        # never straddles it.
        for k, (a, b) in enumerate([(y0, y1)]):
            is_head = b <= head_back + 1e-6
            objects.append(
                extruded_profile(
                    f"{name}_{'head' if is_head else 'shank'}_{index}_{k}",
                    # Sections are taken at the SEGMENT ENDS, so consecutive
                    # segments share a face and the wave is continuous.
                    peg_section(cx, cz, a),
                    a,
                    b,
                    materials[f"{MOD_ID}_copper"] if is_head
                    else materials[f"{MOD_ID}_peg_steel"],
                    uv_meters=0.9 if is_head else 1.2,
                    section_b=peg_section(cx, cz, b),
                )
            )
        del copper


def build_horn_pole(materials) -> list:
    """The PA horn pole: a street-light-height steel standard beside the
    scoreboard carrying four re-entrant horns at 90 degrees.

    Everything here is VISUAL and carries no cage node - like the marker rail,
    it is theatre. Unlike the marker rail it stands on the ground, so the whole
    assembly is kept outboard of every drivable surface by spec's own
    HORN_ENVELOPE_X assert rather than by eye (a drawn-but-non-collidable thing
    a car can stand in is the hazard-backstop defect this machine already had
    to take back once).

    The hardware vocabulary is the reference photo's, item for item: a flared
    bell whose INSIDE you can see (so the driver badge reads through the
    mouth), a cylindrical driver body with a clamp seam, a U-bracket with a row
    of bolt holes and a wing bolt at the pivot, and - because a real pole is
    mostly fixings - a bolted base flange, a hand-hole cover, a junction box
    and a clipped conduit riser feeding the cluster.
    """

    steel = materials[f"{MOD_ID}_steel"]
    nickel = materials[f"{MOD_ID}_nickel"]
    copper = materials[f"{MOD_ID}_copper"]
    olive = materials[f"{MOD_ID}_horn_olive"]
    dark = materials[f"{MOD_ID}_lacquer_black"]

    px, py = spec.HORN_POLE_X, spec.HORN_POLE_Y
    base_z = spec.HORN_POLE_BASE_Z
    top_z = spec.HORN_POLE_TOP_Z
    axis_z = spec.HORN_AXIS_Z
    r0, r1 = spec.HORN_POLE_R0, spec.HORN_POLE_R1
    objects: list = []

    def shaft_r(z: float) -> float:
        """Radius of the tapered shaft at height z (above the swage)."""
        t = (z - 0.75) / (top_z - 0.10 - 0.75)
        return r0 + (r1 - r0) * min(max(t, 0.0), 1.0)

    # ---- shaft: one tapered tube, base swage included -------------------
    swell = r0 + 0.030
    shaft_loop = [(0.0, 0.0), (0.0, swell)]
    shaft_loop += [(0.55 - base_z, swell), (0.75 - base_z, r0)]
    for z in (2.6, 5.0, 7.4, top_z - 0.10):
        shaft_loop.append((z - base_z, shaft_r(z)))
    shaft_loop += [(top_z - base_z, r1 - 0.020), (top_z - base_z, 0.0)]
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_pole_shaft", shaft_loop, steel,
        origin=(px, py, base_z), axis=(0.0, 0.0, 1.0), segments=18, uv_meters=1.1))

    # ---- pole cap: a real standard is capped, not left open --------------
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_pole_cap",
        [(0.0, 0.0), (0.0, r1 + 0.018), (0.045, r1 + 0.030),
         (0.115, r1 - 0.010), (0.150, 0.0)],
        steel, origin=(px, py, top_z - 0.02), axis=(0.0, 0.0, 1.0),
        segments=18, uv_meters=0.5))

    # ---- base flange and its four anchor bolts ---------------------------
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_base_flange",
        [(0.0, 0.0), (0.0, spec.HORN_FLANGE_R), (0.030, spec.HORN_FLANGE_R + 0.012),
         (0.075, spec.HORN_FLANGE_R - 0.010), (0.075, 0.0)],
        steel, origin=(px, py, 0.0), axis=(0.0, 0.0, 1.0), segments=18,
        uv_meters=0.6))
    for index, (dx, dy) in enumerate(spec.HORN_DIRS):
        bx, by = px + dx * 0.325, py + dy * 0.325
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_base_stud_{index}",
            [(0.0, 0.0), (0.0, 0.030), (0.145, 0.030), (0.145, 0.0)],
            steel, origin=(bx, by, 0.070), axis=(0.0, 0.0, 1.0), segments=10,
            uv_meters=0.25))
        # A six-segment revolve IS a hex nut; no separate primitive needed.
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_base_nut_{index}",
            [(0.0, 0.0), (0.0, 0.055), (0.055, 0.055), (0.055, 0.0)],
            nickel, origin=(bx, by, 0.075), axis=(0.0, 0.0, 1.0), segments=6,
            uv_meters=0.25))

    # ---- hand-hole cover: the detail that says "this pole is wired" ------
    cover_y = py - shaft_r(1.05) - 0.020
    objects.append(bk.add_box(
        f"{MOD_ID}_horn_handhole", (px, cover_y, 1.05), (0.17, 0.045, 0.34),
        steel, bevel=0.012, metric_uv=(0.5, 0.5)))
    for index, sz in enumerate((-0.115, 0.115)):
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_handhole_screw_{index}",
            [(0.0, 0.0), (0.0, 0.026), (0.020, 0.022), (0.020, 0.0)],
            nickel, origin=(px, cover_y - 0.022, 1.05 + sz), axis=(0.0, -1.0, 0.0),
            segments=8, uv_meters=0.2))

    # ---- junction box, lid, gland ---------------------------------------
    box_y = py - shaft_r(1.90) - 0.140
    objects.append(bk.add_box(
        f"{MOD_ID}_horn_jbox", (px, box_y, 1.90), (0.34, 0.26, 0.46),
        olive, bevel=0.02, metric_uv=(0.7, 0.7)))
    lid_y = box_y - 0.130 - 0.018
    objects.append(bk.add_box(
        f"{MOD_ID}_horn_jbox_lid", (px, lid_y, 1.90), (0.30, 0.036, 0.42),
        olive, bevel=0.012, metric_uv=(0.7, 0.7)))
    for index, (sx, sz) in enumerate(((-0.125, -0.175), (0.125, -0.175),
                                      (-0.125, 0.175), (0.125, 0.175))):
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_jbox_screw_{index}",
            [(0.0, 0.0), (0.0, 0.024), (0.018, 0.020), (0.018, 0.0)],
            nickel, origin=(px + sx, lid_y - 0.020, 1.90 + sz), axis=(0.0, -1.0, 0.0),
            segments=8, uv_meters=0.2))
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_jbox_gland",
        [(0.0, 0.0), (0.0, 0.052), (0.055, 0.052), (0.075, 0.038), (0.075, 0.0)],
        nickel, origin=(px, box_y, 1.60), axis=(0.0, 0.0, -1.0), segments=10,
        uv_meters=0.25))

    # ---- conduit riser, stood off on P-clips -----------------------------
    riser_y = py - 0.245
    riser_z0, riser_z1 = 2.10, axis_z - 0.80
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_conduit",
        [(0.0, 0.0), (0.0, 0.046), (riser_z1 - riser_z0, 0.046),
         (riser_z1 - riser_z0, 0.0)],
        steel, origin=(px, riser_y, riser_z0), axis=(0.0, 0.0, 1.0), segments=12,
        uv_meters=0.5))
    # ... and the elbow that takes it into the yoke collar.
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_conduit_elbow",
        [(0.0, 0.0), (0.0, 0.046), (0.245, 0.046), (0.245, 0.0)],
        steel, origin=(px, riser_y, riser_z1 - 0.005), axis=(0.0, 1.0, 0.0),
        segments=12, uv_meters=0.5))
    for index, cz in enumerate((3.20, 4.90, 6.60)):
        # A P-clip bridges the standoff: from the shaft's own (tapering)
        # surface out to the far side of the pipe.
        y_out = riser_y - 0.046
        y_in = py - shaft_r(cz)
        objects.append(bk.add_box(
            f"{MOD_ID}_horn_conduit_clip_{index}",
            (px, (y_out + y_in) / 2.0, cz),
            (0.075, y_in - y_out, 0.055),
            steel, bevel=0.008, metric_uv=(0.35, 0.35)))

    # ---- yoke collar: what the four arms hang off ------------------------
    collar_lo, collar_hi = axis_z - 0.86, axis_z + 0.34
    collar_r = shaft_r(axis_z) + 0.075
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_yoke_collar",
        [(0.0, 0.0), (0.0, collar_r - 0.030), (0.045, collar_r),
         (collar_hi - collar_lo - 0.045, collar_r),
         (collar_hi - collar_lo, collar_r - 0.030), (collar_hi - collar_lo, 0.0)],
        steel, origin=(px, py, collar_lo), axis=(0.0, 0.0, 1.0), segments=16,
        uv_meters=0.6))

    # ---- the four horns --------------------------------------------------
    bell_d = spec.HORN_BELL_D
    bell_len = spec.HORN_BELL_LEN
    drv_len = spec.HORN_DRIVER_LEN
    drv_r = spec.HORN_DRIVER_R
    throat_r = spec.HORN_THROAT_R
    mouth_r = bell_d / 2.0
    rear_r = spec.HORN_REAR_R
    wall = 0.020

    # Exponential flare, sampled at eight stations. An exponential horn is what
    # a re-entrant PA driver actually loads into and it is also the profile
    # whose silhouette reads as "horn" rather than "traffic cone".
    flare = []
    for k in range(8):
        s = k / 7.0
        flare.append((bell_len * s, throat_r * (mouth_r / throat_r) ** s))

    for index, (dx, dy) in enumerate(spec.HORN_DIRS):
        axis = (dx, dy, 0.0)
        yaw = math.atan2(dy, dx)
        wx, wy = -dy, dx                       # the across-the-horn direction

        def at(radial: float, across: float = 0.0, dz: float = 0.0):
            return (px + dx * radial + wx * across,
                    py + dy * radial + wy * across,
                    axis_z + dz)

        # yoke arm + diagonal brace back to the collar
        objects.append(bk.add_box(
            f"{MOD_ID}_horn_arm_{index}", at(0.30, 0.0, -0.62),
            (0.44, 0.17, 0.15), steel, bevel=0.02,
            rotation=(0.0, 0.0, yaw), metric_uv=(0.5, 0.5)))
        objects.append(bk.add_box(
            f"{MOD_ID}_horn_brace_{index}", at(0.30, 0.0, -0.90),
            (0.46, 0.075, 0.055), steel, bevel=0.0,
            rotation=(0.0, math.radians(-52.0), yaw), metric_uv=(0.4, 0.4)))

        # U-bracket: base strap, two arms straddling the driver body
        objects.append(bk.add_box(
            f"{MOD_ID}_horn_ubase_{index}", at(0.54, 0.0, -0.545),
            (0.42, 0.64, 0.055), steel, bevel=0.012,
            rotation=(0.0, 0.0, yaw), metric_uv=(0.45, 0.45)))
        for side, across in enumerate((-0.292, 0.292)):
            objects.append(bk.add_box(
                f"{MOD_ID}_horn_uarm_{index}_{side}", at(0.54, across, -0.245),
                (0.40, 0.055, 0.605), steel, bevel=0.010,
                rotation=(0.0, 0.0, yaw), metric_uv=(0.45, 0.45)))
            # The reference's row of adjuster holes. Drawn as recessed dark
            # discs rather than booleaned holes: at any camera distance this
            # prop is ever seen from, a dark disc IS a hole, and a boolean
            # through a 55 mm strap costs geometry and a shading seam.
            # The plug spans the whole 55 mm strap and stands 2.5 mm proud on
            # both faces, so it reads as a hole THROUGH the arm from either
            # side rather than as a sticker on one of them.
            for hole in range(4):
                objects.append(revolved_solid(
                    f"{MOD_ID}_horn_uhole_{index}_{side}_{hole}",
                    [(0.0, 0.0), (0.0, 0.034), (0.060, 0.034), (0.060, 0.0)],
                    dark,
                    origin=at(0.40 + 0.093 * hole,
                              across - 0.030 if side == 0 else across + 0.030,
                              -0.395),
                    axis=(wx, wy, 0.0) if side == 0 else (-wx, -wy, 0.0),
                    segments=10, uv_meters=0.2))

        # pivot bolt through both arms, with a wing nut on one side
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_pivot_{index}",
            [(0.0, 0.0), (0.0, 0.042), (0.74, 0.042), (0.74, 0.0)],
            nickel, origin=at(0.54, -0.37, 0.0), axis=(wx, wy, 0.0),
            segments=10, uv_meters=0.25))
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_wingnut_hub_{index}",
            [(0.0, 0.0), (0.0, 0.070), (0.075, 0.070), (0.075, 0.0)],
            nickel, origin=at(0.54, 0.360, 0.0), axis=(wx, wy, 0.0),
            segments=8, uv_meters=0.2))
        for ear, dzz in enumerate((-0.115, 0.115)):
            objects.append(bk.add_box(
                f"{MOD_ID}_horn_wingear_{index}_{ear}", at(0.54, 0.395, dzz),
                (0.075, 0.070, 0.135), nickel, bevel=0.010,
                rotation=(0.0, 0.0, yaw), metric_uv=(0.25, 0.25)))

        # driver body: cylinder with a domed rear and a clamp seam
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_driver_{index}",
            [(0.0, 0.0), (0.0, 0.185), (0.048, 0.240), (0.080, drv_r),
             (drv_len - 0.075, drv_r), (drv_len - 0.030, drv_r - 0.020),
             (drv_len, throat_r + 0.010), (drv_len, 0.0)],
            olive, origin=at(rear_r), axis=axis, segments=20, uv_meters=0.55))
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_seam_{index}",
            [(0.0, 0.0), (0.0, drv_r + 0.022), (0.042, drv_r + 0.022), (0.042, 0.0)],
            olive, origin=at(rear_r + 0.24), axis=axis, segments=20, uv_meters=0.3))

        # the bell: a real SHELL, so the badge shows through the mouth
        bell_loop: list[tuple[float, float]] = list(flare)
        bell_loop += [(bell_len + 0.032, mouth_r + 0.014),
                      (bell_len + 0.052, mouth_r),
                      (bell_len + 0.032, mouth_r - 0.016)]
        bell_loop += [(t, max(r - wall, 0.006)) for t, r in reversed(flare)]
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_bell_{index}", bell_loop, olive,
            origin=at(rear_r + drv_len), axis=axis, segments=24, uv_meters=0.65))
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_throat_band_{index}",
            [(0.0, 0.0), (0.0, throat_r + 0.028), (0.055, throat_r + 0.028),
             (0.055, 0.0)],
            nickel, origin=at(rear_r + drv_len - 0.028), axis=axis, segments=20,
            uv_meters=0.25))
        # the badge on the driver throat, seen down the bell
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_badge_{index}",
            [(0.0, 0.0), (0.0, 0.122), (0.024, 0.118), (0.024, 0.0)],
            copper, origin=at(rear_r + drv_len + 0.012), axis=axis, segments=16,
            uv_meters=0.2))

    return objects


def build_visual(materials) -> list:
    steel = materials[f"{MOD_ID}_steel"]
    hazard = materials[f"{MOD_ID}_hazard"]
    board_red = materials[f"{MOD_ID}_board_red"]
    board_cream = materials[f"{MOD_ID}_board_cream"]
    screen = materials[f"{MOD_ID}_screen"]
    concrete = materials[f"{MOD_ID}_concrete"]
    asphalt = materials[f"{MOD_ID}_asphalt"]
    copper = materials[f"{MOD_ID}_copper"]
    bin_gunmetal = materials[f"{MOD_ID}_bin_gunmetal"]
    gold = materials[f"{MOD_ID}_jackpot_gold"]
    marquee_wood = materials[f"{MOD_ID}_marquee_wood"]
    # Round 5, the wooden-cabinet x modern-parlour pass (see spec.PALETTE).
    nickel = materials[f"{MOD_ID}_nickel"]
    ply = materials[f"{MOD_ID}_cabinet_ply"]
    board_field = materials[f"{MOD_ID}_board_field"]
    lacquer_black = materials[f"{MOD_ID}_lacquer_black"]
    lacquer_orange = materials[f"{MOD_ID}_lacquer_orange"]
    accent_yellow = materials[f"{MOD_ID}_accent_yellow"]
    accent_teal = materials[f"{MOD_ID}_accent_teal"]
    accent_pink = materials[f"{MOD_ID}_accent_pink"]
    accent_blue = materials[f"{MOD_ID}_accent_blue"]
    accent_mint = materials[f"{MOD_ID}_accent_mint"]
    lamp_warm = materials[f"{MOD_ID}_lamp_warm"]
    lamp_rainbow = materials[f"{MOD_ID}_lamp_rainbow"]

    objects: list = []

    # ---- plinth ---------------------------------------------------------
    objects.append(
        bk.add_box(
            f"{MOD_ID}_plinth",
            ((-HW - WT + spec.SHAFT_X1) / 2.0, 0.0, BIN_Z / 2.0),
            (spec.SHAFT_X1 + HW + WT, 2 * (DY + WT), BIN_Z),
            concrete,
            bevel=0.0,
            metric_uv=(3.0, 3.0),
        )
    )
    # Bin apron. The plinth only draws out to -(DY + WT) = -4.15, but the bin
    # floor's COLLISION (the "binfloor" cage surface) runs to the divider front
    # line at -6.50 and the exit apron starts there. That left a 2.35 m strip
    # spanning the whole 25.4 m frontage with collision and no geometry: a car
    # driving out of a bin crossed a hole in the floor it was standing on.
    # Found by a top-down first-drawn-surface sweep over the BUILT visual - the
    # earlier audits raycast the cage triangles, which were always complete, so
    # this class of defect is invisible to a collision-side probe.
    # 5 cm of overlap into the exit apron at the front and a flush butt against
    # the plinth at the back: an overlap is invisible, a gap is a hole.
    apron_y0 = spec.DIVIDER_Y_FRONT - 0.05  # -6.55, inside the exit apron
    apron_y1 = -(DY + WT)  # -4.15, the plinth's front face
    objects.append(
        bk.add_box(
            f"{MOD_ID}_bin_apron",
            (0.0, (apron_y0 + apron_y1) / 2.0, BIN_Z / 2.0),
            (2 * (HW + WT), apron_y1 - apron_y0, BIN_Z),
            concrete,
            bevel=0.0,
            metric_uv=(3.0, 3.0),
        )
    )
    # Front-left datum pier: the cage's reference frame lives inside it, so it
    # is real geometry rather than a floating set of nodes.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_datum_pier",
            (-HW - 0.7, -5.3, 0.6),
            (1.4, 1.4, 1.2),
            concrete,
            bevel=0.06,
            metric_uv=(1.4, 1.4),
        )
    )

    # ---- backboard, side walls, screens ---------------------------------
    objects.append(
        bk.add_box(
            f"{MOD_ID}_backboard",
            ((-HW + spec.SHAFT_X1) / 2.0, DY + WT / 2.0, (BIN_Z + TOP) / 2.0),
            (spec.SHAFT_X1 + HW, WT, TOP - BIN_Z),
            ply,
            bevel=0.0,
            metric_uv=(4.5, 4.5),
        )
    )
    # Playfield face on the backboard, 2 cm proud so it does not z-fight the
    # panel behind it. The collision plane stays at y = DY, i.e. flush
    # with the carcass panel's front face, so nothing stops more than 2 cm
    # short. Round 5: the flat cream enamel becomes the screen-printed
    # PLAYFIELD - ivory ground, pale mint foliage, mustard and teal confetti.
    # 6 m per tile, not the old 3: at 3 m a leaf came out 0.8 m and the
    # 24 x 39 m board tiled 8 x 13 times, which reads as wallpaper. 6 m puts
    # a leaf at 1.6-2.5 m and the field at 4 x 6.5 repeats, which reads as a
    # printed board seen from the far side of a car park.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_board_face",
            (0.0, DY + 0.02, (RIDGE + spec.APRON_Z_HI) / 2.0),
            (2 * HW - 0.1, 0.08, spec.APRON_Z_HI - RIDGE),
            board_field,
            bevel=0.0,
            metric_uv=(6.0, 6.0),
        )
    )
    # ---- the sunburst medallion ------------------------------------------
    # Round 5 rework, NOT a deletion. The round-3 burst fanned +/-70 degrees
    # UPWARD from just over the jackpot mouth in cabinet red and jackpot
    # gold, and on the new ivory playfield that read as two enormous painted
    # arrows nailed over the artwork - the modern half winning outright.
    # Three changes make it a medallion instead of an arrow:
    #   * it is CENTRED on the board (x 0, z 24.5 is the exact middle of the
    #     RIDGE..APRON_Z_HI face) and radiates through 360 degrees, which is
    #     the composition the vintage cabinet actually uses: a lacquered
    #     ornament in the middle of a circular field with the art around it;
    #   * the rays are half as wide (2.4 deg half-angle against 3.2) and
    #     there are twice as many, so the field shows THROUGH the burst;
    #   * they wear the lacquer palette - red-orange and mustard - so the
    #     burst belongs to the ornament at its centre rather than to the
    #     cabinet paint.
    # Established visual-only pattern, unchanged: front faces 1 cm proud of
    # the playfield face (y = DY - 0.03 vs its DY - 0.02), backs buried 4 cm
    # inside it so the joint is an invisible same-space overlap, and the
    # collision plane at y = DY is untouched. Pegs pierce the plates exactly
    # like pins driven through a printed board.
    #
    # WHERE THE CENTRE CAN BE is a fact about the peg lattice, not a taste
    # call. Even rows stand at x +/-3.8 and +/-11.4, odd rows at 0 and
    # +/-7.6, so x = 0 is EMPTY on every even row; z = 24 is one (row 4).
    # The nearest pegs are (+/-3.8, 24) with a 1.1 m x half-width - 2.7 m of
    # clear x - and (0, 20)/(0, 28) whose crowns reach z 21.55 and whose
    # roots reach 27.6. A 2.3 m medallion therefore has 0.15 m of air below
    # and 1.2 m above. Nothing here is collidable, but a decoration that
    # visibly grows out of a peg is a defect all the same.
    # ROUND 5b: A CORONA, NOT A MANDALA. The first cut of this rework ran 24
    # full-length rays from the centre to the edges of the board, and in game
    # it was a 24 x 39 m dartboard: the pastel field it was supposed to sit
    # ON was invisible, and the lacquer ornament at the middle - the actual
    # focal point - was one more thing in a pattern. Rays now STOP at 7.2 m,
    # so the ornament plus its corona is a 14 m rosette in the centre of an
    # otherwise printed board, and everything outside it (foliage, confetti,
    # ring targets, the inscribed circle) is legible again. This is the
    # round's clearest instance of the pack's own law: it measured fine
    # (every ray inside the field, no peg fouled) and it looked wrong.
    burst_cx = 0.0
    burst_cz = 24.5
    burst_half_deg = 3.0
    burst_half_tan = math.tan(math.radians(burst_half_deg))
    burst_r_in = 2.55
    burst_r_out = 7.20

    for ray_index in range(20):
        ray_deg = ray_index * 18.0
        sin_d = math.sin(math.radians(ray_deg))
        cos_d = math.cos(math.radians(ray_deg))
        r_out = burst_r_out
        section = []
        for radius, side in (
            (burst_r_in, 1.0),
            (r_out, 1.0),
            (r_out, -1.0),
            (burst_r_in, -1.0),
        ):
            width = radius * burst_half_tan * side
            section.append(
                (
                    burst_cx + radius * sin_d + width * cos_d,
                    burst_cz + radius * cos_d - width * sin_d,
                )
            )
        objects.append(
            extruded_profile(
                f"{MOD_ID}_burst_ray_{ray_index:02d}",
                section,
                DY - 0.03,
                DY + 0.02,
                accent_yellow if ray_index % 2 == 1 else lacquer_orange,
                uv_meters=2.4,
            )
        )
    # THE INSCRIBED CIRCLE. The single most distinctive thing about the
    # reference playfield is that it is a CIRCLE set into a square cream
    # field, and nothing on this board said so. One teal hoop centred on the
    # medallion at 10.4 m does it: it crosses the outermost peg columns in
    # projection, but the hoop lies on the backboard 6.9 m behind the peg
    # plane, so what a player sees is a circle passing BEHIND the pins -
    # which is exactly how the real board is printed.
    objects.append(
        bk.add_torus(
            f"{MOD_ID}_playfield_circle",
            (burst_cx, DY - 0.02, burst_cz),
            10.40,
            0.22,
            accent_teal,
            rotation=(math.pi / 2.0, 0.0, 0.0),
            major_segments=72,
            minor_segments=8,
        )
    )
    # The medallion itself: the vintage cabinet's central lacquer ornament -
    # a red-orange disc, a mustard ring, a yellow lattice grille over a green
    # ground. Stacked flat discs rather than a modelled mask, because the
    # thing sits 6.9 m BEHIND the peg plane and every millimetre of relief is
    # invisible from the apron; what reads at that distance is the ring
    # hierarchy. Each layer stands 3 cm proud of the one behind it, and the
    # whole stack lives inside the burst's 2.55 m inner radius.
    #
    # RELIEF IS RATIONED. The board's collision plane is the backboard face
    # at y = DY, so every millimetre a decoration stands proud of it is a
    # millimetre a car pressed against the back wall passes THROUGH. The
    # burst rays' 3 cm is the established budget; this stack spends 10.5 cm
    # across four layers in 2.5 cm steps - enough separation that nothing
    # z-fights at 60 m, small enough that a car clipping it is a
    # centimetre-scale artifact rather than a hole in the artwork.
    def board_disc(name, cx, cz, radius, proud, material, vertices=32, uv=1.2):
        """Flat disc on the playfield: front face ``proud`` of y = DY."""

        return bk.add_cylinder(
            name,
            (cx, DY + (0.06 - proud) / 2.0, cz),
            radius,
            proud + 0.06,
            material,
            vertices=vertices,
            axis="Y",
            metric_uv=(uv, uv),
        )

    for tag, radius, proud, ornament in (
        ("disc", 2.30, 0.030, lacquer_orange),
        ("ring", 1.86, 0.055, accent_yellow),
        ("ground", 1.55, 0.080, accent_teal),
        ("pupil", 0.62, 0.105, accent_mint),
    ):
        objects.append(
            board_disc(f"{MOD_ID}_ornament_{tag}", burst_cx, burst_cz,
                       radius, proud, ornament)
        )
    # Lattice grille over the ornament's green ground: three bars each way,
    # mustard, standing 2 cm in front of the ground disc and stopping short
    # of the ring so the grille reads as an inset panel.
    for bar in range(3):
        offset = (bar - 1) * 0.86
        span = 2.0 * math.sqrt(max(1.50**2 - offset**2, 0.04))
        objects.append(
            bk.add_box(
                f"{MOD_ID}_ornament_bar_v_{bar}",
                (burst_cx + offset, DY - 0.070, burst_cz),
                (0.20, 0.12, span),
                accent_yellow,
                bevel=0.02,
                metric_uv=(0.8, 0.8),
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_ornament_bar_h_{bar}",
                (burst_cx, DY - 0.095, burst_cz + offset),
                (span, 0.12, 0.20),
                accent_yellow,
                bevel=0.02,
                metric_uv=(0.8, 0.8),
            )
        )
    # ---- ring targets ("eyes") -------------------------------------------
    # The 1970s board's scattered pink concentric rings with blue centres.
    # They sit on the OTHER sublattice: a peg row's own columns are taken, so
    # every target stands at a position the lattice deliberately leaves
    # empty - x 0 and +/-7.6 on even rows, +/-3.8 and +/-11.4 on odd ones.
    # That is 3.8 m of clear x (2.7 m past a peg's 1.1 m half-width) and 4 m
    # of clear z, so a 1.5 m target never grows out of a pin. Three flat
    # discs, 3 cm apart in depth, exactly like the ornament.
    # Two positions the sublattice offers and this list refuses: x = +/-11.4
    # (a 1.5 m target there reaches x 12.9, past the playfield plate's 11.95
    # edge and into the side wall's solid, so it would draw as a target
    # sliced by the cabinet) and x = +/-7.6 at z = 40 (inside the crown
    # chute's prism, which spans the full board depth - it would simply
    # vanish). Clearance is not the only test; the decoration also has to be
    # somewhere a player can see all of it.
    for target_index, (tx, tz) in enumerate(
        ((0.0, 40.0),
         (-7.6, 32.0), (0.0, 32.0), (7.6, 32.0),
         (-3.8, 28.0), (3.8, 28.0),
         (-7.6, 24.0), (7.6, 24.0),
         (-3.8, 20.0), (3.8, 20.0),
         (0.0, 16.0))
    ):
        for tag, radius, proud, ink in (
            ("ring", 1.50, 0.030, accent_pink),
            ("field", 1.02, 0.055, board_cream),
            ("eye", 0.58, 0.080, accent_blue),
        ):
            objects.append(
                board_disc(f"{MOD_ID}_target_{target_index:02d}_{tag}",
                           tx, tz, radius, proud, ink, vertices=24, uv=1.0)
            )
    # Backboard framing on the rear face: a 46 x 35 m blank panel is not a
    # weldment. Horizontal stringers plus vertical stiles at the peg columns.
    # Round 5: nickel rails with a deep-red band every fourth course. The
    # hazard chevrons that used to mark those courses were the last plant
    # livery on a face that is now a plywood cabinet - hazard tape belongs on
    # the things that can actually hurt you (the doorway header, the guard
    # wall, the traffic island, the chute lips, the mast head), and a rail
    # 30 m up a cabinet flank is not one of them.
    for index in range(9):
        z = 3.0 + index * 5.0
        objects.append(
            bk.add_box(
                f"{MOD_ID}_board_stringer_{index}",
                ((-HW + spec.SHAFT_X1) / 2.0, DY + WT + 0.16, z),
                (spec.SHAFT_X1 + HW, 0.32, 0.55),
                board_red if index % 4 == 0 else nickel,
                bevel=0.03,
                metric_uv=(2.0, 2.0),
            )
        )
    for index, x in enumerate((-10.2, -3.4, 3.4, 10.2, 17.0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_board_stile_{index}",
                (x, DY + WT + 0.14, (BIN_Z + TOP) / 2.0),
                (0.6, 0.28, TOP - BIN_Z),
                nickel,
                bevel=0.03,
                metric_uv=(2.0, 2.0),
            )
        )
    # The side walls are the CABINET, not the structure. Round 4 painted them
    # the parlour's deep red to stop the tower reading as an industrial
    # elevator; round 5 goes the whole way and makes them what the reference
    # cabinet is actually built of - blonde birch PLY, sheet-jointed, with
    # nickel rails and cast corner brackets on it. Red survives as the accent
    # both halves of the fusion share (marquee field, stringer bands, ridge
    # caps, chute hood). Structural members (mast, chain, machine deck) stay
    # steel; trim and hardware go nickel.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_wall_left",
            (-HW - WT / 2.0, 0.0, (BIN_Z + TOP) / 2.0),
            (WT, 2 * DY, TOP - BIN_Z),
            ply,
            bevel=0.0,
            metric_uv=(4.5, 4.5),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_wall_right",
            (HW + WT / 2.0, 0.0, (BIN_Z + RIGHT_WALL_TOP) / 2.0),
            (WT, 2 * DY, RIGHT_WALL_TOP - BIN_Z),
            ply,
            bevel=0.0,
            metric_uv=(4.5, 4.5),
        )
    )
    # Hazard bands where the side walls flank the drive-out lane.
    for side, sx in (("l", -HW - WT / 2.0), ("r", HW + WT / 2.0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_wall_hazard_{side}",
                (sx, -DY + 0.9, BIN_Z + 1.1),
                (WT + 0.02, 1.6, 1.4),
                hazard,
                bevel=0.0,
                metric_uv=(1.6, 1.6),
            )
        )
    # Front screen: horizontal slats on vertical mullions - the pachinko
    # machine's glass. Two numbers here are load-bearing and both were wrong
    # in the first cut, so they are derived rather than eyeballed.
    #
    # OCCLUSION. The board face is the whole point of the machine, so the
    # screen may not eat it. Orthographic coverage is
    #   1 - (1 - SLAT_H / SLAT_PITCH) * (1 - 5 * MULLION_W / (2 * HW))
    #     = 1 - (1 - 0.34/1.70) * (1 - 5*0.40/24) = 26.7%,
    # against 47.5% for the 0.55 m slats on a 1.35 m pitch that shipped first.
    # Depth matters just as much from a real eye: a slat occludes
    # h*cos(theta) + d*sin(theta), so dropping the depth 0.55 -> 0.30 removes
    # most of the oblique penalty as well.
    #
    # DIVERGENCE. The collision plane is a single flat plane at y = -DY. That
    # is DELIBERATELY more conservative than the drawing: per-slat collision
    # would put knife-edged gaps at wheel height in the path of a car that has
    # just fallen 30 m, exactly the tire-slicer class AGENTS.md warns about.
    # The honest cost is that a wheel can appear to have somewhere to go that
    # it does not - so the slats are pulled back until the visual invitation is
    # exactly SLAT_DEPTH: back face flush with the collision plane at -3.45,
    # front face 0.30 m proud of it. (The first cut sat at -4.005..-3.455 and
    # invited 0.555 m while its notes claimed 0.3.)
    slat_pitch = 1.70
    slat_height = 0.34
    slat_depth = 0.30
    mullion_width = 0.40
    slat_count = int((TOP - RIDGE - 0.4) / slat_pitch)
    # ROUND 6 tried ONE TRANSLUCENT PANE here instead of the slats and reverted
    # it the same hour - see BOARD_GLASS in spec.py for the two captures that
    # killed it. The flag survives so the experiment is repeatable, not so it
    # is switchable: it must stay False in anything that ships.
    assert not spec.BOARD_GLASS, (
        "BOARD_GLASS is a reverted experiment; see spec.py before shipping it"
    )
    for index in range(slat_count):
        z = RIDGE + 0.4 + index * slat_pitch
        objects.append(
            bk.add_box(
                f"{MOD_ID}_slat_{index:02d}",
                (0.0, -DY - slat_depth / 2.0, z),
                (2 * HW, slat_depth, slat_height),
                screen,
                bevel=0.03,
                metric_uv=(1.6, 1.6),
            )
        )
    # Mullions sit 2 cm proud of the slats so the frame reads in front of the
    # louvres instead of z-fighting them at every crossing. They wear copper,
    # not steel: they are the sash around the machine's glass, and the brass
    # rail is the one material a vintage pachinko front actually has - it also
    # ties the front frame to the copper peg heads behind it.
    for index, x in enumerate((-HW + 0.4, -6.0, 0.0, 6.0, HW - 0.4)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_mullion_{index}",
                (x, -DY - slat_depth / 2.0 - 0.02, (RIDGE + TOP) / 2.0),
                (mullion_width, slat_depth, TOP - RIDGE),
                copper,
                bevel=0.03,
                metric_uv=(2.0, 2.0),
            )
        )
    # Shaft front above the drive-in doorway: the same slat-screen treatment
    # as the board face, NOT a plate. The solid wall that shipped first was a
    # 468 m2 sheet of steel over the single most animated thing the machine
    # does - the carriage climbing 43 m with its counterweight falling past
    # it - so no player ever saw the hoist work. Orthographic coverage with
    # the four mullions kept below:
    #   1 - (1 - 0.34/1.70) * (1 - 4 * 0.5 / 11.3) = 34.2%,
    # and the cage's sfront collision plane at y = -DY is untouched, so cars
    # stay walled out of the shaft exactly as before. Same divergence rule as
    # the board screen: slat back faces flush with the collision plane, front
    # faces exactly slat_depth proud.
    shaft_mid_x = (HW + spec.SHAFT_X1) / 2.0
    shaft_span_x = spec.SHAFT_X1 - HW
    shaft_slat_count = int((TOP - spec.DOORWAY_HEAD_Z - 0.75 - 0.4) / slat_pitch)
    for index in range(shaft_slat_count):
        z = spec.DOORWAY_HEAD_Z + 0.75 + index * slat_pitch
        objects.append(
            bk.add_box(
                f"{MOD_ID}_shaft_slat_{index:02d}",
                (shaft_mid_x, -DY - slat_depth / 2.0, z),
                (shaft_span_x, slat_depth, slat_height),
                screen,
                bevel=0.03,
                metric_uv=(1.6, 1.6),
            )
        )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_doorway_header",
            # Sits ON the header line, never below it: the cage's shaft wall
            # starts at DOORWAY_HEAD_Z, so a header hung underneath would draw
            # a lintel 0.35 m lower than the collision opening.
            ((HW + spec.SHAFT_X1) / 2.0, -DY - WT / 2.0, spec.DOORWAY_HEAD_Z + 0.35),
            (spec.SHAFT_X1 - HW, WT + 0.06, 0.70),
            hazard,
            bevel=0.0,
            metric_uv=(1.6, 1.6),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_shaft_outer",
            (spec.SHAFT_X1 + WT / 2.0, 0.0, (BIN_Z + TOP) / 2.0),
            (WT, 2 * (DY + WT), TOP - BIN_Z),
            ply,
            bevel=0.0,
            metric_uv=(4.5, 4.5),
        )
    )
    # Cabinet flank dressing. The tower's two biggest faces (the shaft's
    # outer wall and the left wall, ~46 m tall) shipped as bare monoliths -
    # from the side nothing said pachinko, or even said "panelled machine".
    # Same stringer + stile rhythm the rear face already wears, so every
    # elevation reads as a built cabinet. Pure decor at the rear stringers'
    # own 0.32 m standoff; no cage geometry anywhere near it.
    for face, face_x, half_y in (
        ("r", spec.SHAFT_X1 + WT, DY + WT),
        ("l", -HW - WT, DY),
    ):
        outward = 1.0 if face_x > 0 else -1.0
        for index in range(9):
            z = 3.0 + index * 5.0
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_flank_stringer_{face}_{index}",
                    (face_x + outward * 0.16, 0.0, z),
                    (0.32, 2 * half_y, 0.55),
                    board_red if index % 4 == 0 else nickel,
                    bevel=0.03,
                    metric_uv=(2.0, 2.0),
                )
            )
        for sub, y in enumerate((-(half_y - 0.45), half_y - 0.45)):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_flank_stile_{face}_{sub}",
                    (face_x + outward * 0.14, y, (BIN_Z + TOP) / 2.0),
                    (0.28, 0.6, TOP - BIN_Z),
                    nickel,
                    bevel=0.03,
                    metric_uv=(2.0, 2.0),
                )
            )
    # Mullions carry the shaft screen the way the board screen's do: 2 cm
    # proud of the slats so the frame reads in front of the louvres. The old
    # ribs-and-stiles dressing belonged to the solid plate and went with it.
    for index, x in enumerate((13.6, 16.4, 19.2, 22.0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_shaft_stile_{index}",
                (x, -DY - slat_depth / 2.0 - 0.02, (spec.DOORWAY_HEAD_Z + TOP) / 2.0),
                (0.5, slat_depth, TOP - spec.DOORWAY_HEAD_Z),
                # Round 5b: back to plate. Gloss black stiles on the
                # near-black slat screen turned the whole hoist flank into
                # one unreadable slab from any distance - the modern half's
                # lacquer earns its place on the OUTBOARD shrouds, the
                # marquee bezel and the jackpot, where it has something to
                # contrast against.
                nickel,
                bevel=0.03,
                metric_uv=(1.8, 1.8),
            )
        )

    # ---- the cabinet door: nickel bezel, hardware, lamp tubes -----------
    # THE single most vintage thing in the reference photographs is not a
    # colour, it is a NICKEL-PLATED BEZEL around a square glass door, with
    # visible hinge barrels down one edge and a barrel lock on the other.
    # The tower already had the glass (the slat screen) and the sash (the
    # copper mullions) and no frame at all, so from the apron it read as
    # louvres bolted to a box. This is the frame.
    #
    # Depth ladder, front-most last, every layer a clear 2 cm apart so
    # nothing z-fights and every joint is a same-space overlap:
    #   slats      y -3.75    mullions  y -3.77    bezel   y -4.17
    #   grilles    y -4.29    tubes     y -4.40    lock    y -4.97
    # All of it is at least 0.28 m OUTBOARD of the screen's collision plane
    # at y = -DY, which is the plane a fallen car stops against, so none of
    # it is reachable and none of it carries a cage node.
    bezel_y = -DY - 0.72          # centre; 0.44 deep -> front face -4.17
    bezel_x = HW + WT / 2.0       # 12.35, over the cabinet's own side walls
    bezel_z0 = RIDGE + 1.45       # 6.45, clear of the fascia's 6.10 top
    bezel_z1 = TOP - 0.45         # 45.55
    for side, sx in (("l", -bezel_x), ("r", bezel_x)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_bezel_stile_{side}",
                (sx, bezel_y, (bezel_z0 + bezel_z1) / 2.0),
                (0.70, 0.44, bezel_z1 - bezel_z0 + 0.90),
                nickel,
                bevel=0.05,
                metric_uv=(1.6, 1.6),
            )
        )
    for tag, bz in (("head", bezel_z1), ("sill", bezel_z0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_bezel_rail_{tag}",
                (0.0, bezel_y, bz),
                (2 * (HW + WT), 0.44, 0.90),
                nickel,
                bevel=0.05,
                metric_uv=(1.6, 1.6),
            )
        )
    # Hinge barrels down the left stile and a barrel lock on the right: the
    # two pieces of hardware that say "this is a door that opens", which is
    # the whole reason the reference cabinet reads as a cabinet and not as a
    # panel. Sized to be seen - a true-scale hinge on a 39 m door is a pin.
    for index, hinge_z in enumerate((11.0, 26.0, 41.0)):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_bezel_hinge_{index}",
                (-bezel_x - 0.16, bezel_y - 0.30, hinge_z),
                0.34,
                2.10,
                nickel,
                vertices=20,
                axis="Z",
                metric_uv=(1.0, 1.0),
            )
        )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_bezel_lock",
            (bezel_x, bezel_y - 0.52, 25.0),
            0.44,
            1.10,
            nickel,
            vertices=20,
            axis="Y",
            metric_uv=(1.0, 1.0),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_bezel_keyway",
            (bezel_x, bezel_y - 0.98, 25.0),
            0.17,
            0.16,
            lacquer_black,
            vertices=14,
            axis="Y",
            metric_uv=(0.5, 0.5),
        )
    )
    # Segmented lamp tubes: a vertical orange/red/yellow run up each edge of
    # the glass and a rainbow rail across its head, exactly the reference
    # cabinet's layout, with a red-orange dome lamp capping each top corner.
    # ROUND 6 TOOK THE PROPOSAL. The lacquer stays - lamp_bands' baked lit-cell
    # falloff is still what makes a tube read as a tube in daylight - but the
    # four numbers below now ALSO place the GE-side PointLights that make it a
    # lamp after dark (spec.LAMP_TUBE_*, consumed by LUA_BEHAVIOR's light rig).
    # They live in spec.py precisely because two consumers read them: a light at
    # a retyped coordinate is a light hanging in mid-air beside its own tube.
    tube_y = spec.LAMP_TUBE_Y
    tube_x = spec.LAMP_TUBE_X
    tube_r = 0.38
    tube_z0 = spec.LAMP_TUBE_Z0
    tube_z1 = spec.LAMP_TUBE_Z1
    assert abs(tube_z0 - (bezel_z0 + 0.85)) < 1e-9, "lamp tube base drifted from the bezel"
    assert abs(tube_z1 - (bezel_z1 - 0.85)) < 1e-9, "lamp tube head drifted from the bezel"
    for side, sx in (("l", -tube_x), ("r", tube_x)):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_lamp_tube_{side}",
                (sx, tube_y, (tube_z0 + tube_z1) / 2.0),
                tube_r,
                tube_z1 - tube_z0,
                lamp_warm,
                vertices=16,
                axis="Z",
                metric_uv=(2.4, 6.0),
            )
        )
        objects.append(
            bk.add_sphere(
                f"{MOD_ID}_lamp_dome_{side}",
                (sx, tube_y, tube_z1),
                0.62,
                lacquer_orange,
                segments=20,
            )
        )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_lamp_rail",
            (0.0, tube_y, tube_z1),
            tube_r,
            2 * tube_x,
            lamp_rainbow,
            vertices=16,
            axis="X",
            metric_uv=(2.4, 6.0),
        )
    )
    # Speaker grilles in the top corners: the modern parlour's own furniture,
    # and the one place the two languages sit on the same panel - a woven
    # grille in a nickel surround, hung on the vintage door. Held inboard of
    # the lamp tubes (x 7.50-10.50 against the tube's 10.92) so nothing
    # crosses anything.
    for side, sx in (("l", -9.0), ("r", 9.0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_speaker_frame_{side}",
                (sx, -DY - 0.68, 42.60),
                (3.34, 0.26, 2.74),
                nickel,
                bevel=0.06,
                metric_uv=(1.2, 1.2),
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_speaker_grille_{side}",
                (sx, -DY - 0.86, 42.60),
                (3.00, 0.16, 2.40),
                screen,
                bevel=0.0,
                metric_uv=(0.6, 0.6),
            )
        )
    # Cast corner brackets: the wooden cabinet's other signature hardware.
    # Two arms wrapping the front arris, at the four heights that fall
    # MIDWAY between the flank stringers (which stand at z = 3 + 5k and
    # 0.32 m proud of the same face) so a bracket never lands on a rail.
    for tag, arris_x, arris_y, arm_x, outward in (
        ("l", -HW - WT, -DY, -HW - WT / 2.0, -1.0),
        ("r", spec.SHAFT_X1 + WT, -(DY + WT), spec.SHAFT_X1 + WT / 2.0, 1.0),
    ):
        for index, bracket_z in enumerate((10.5, 20.5, 30.5, 40.5)):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_corner_bracket_{tag}_{index}_flank",
                    (arris_x + outward * 0.13, arris_y + 0.72, bracket_z),
                    (0.26, 1.44, 1.10),
                    nickel,
                    bevel=0.05,
                    metric_uv=(1.0, 1.0),
                )
            )
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_corner_bracket_{tag}_{index}_front",
                    (arm_x, arris_y - 0.11, bracket_z),
                    (WT, 0.22, 1.10),
                    nickel,
                    bevel=0.05,
                    metric_uv=(1.0, 1.0),
                )
            )
    # Faceted body-kit shrouds on the machinery flank. The modern reference's
    # shrouds are canted, glossy and stacked, and the honest place for them
    # on this machine is the outboard face of the HOIST shaft - the side that
    # is all counterweight and chain - flanking the P-A-C-H-I-N-K-O stack.
    # They are deliberately NOT put over the shaft's front screen: that
    # screen exists so a player can watch the carriage climb, and round 3
    # already paid for learning that a solid panel there hides the only
    # animated thing the machine does.
    for index, chevron_z in enumerate((10.5, 20.5, 30.5, 40.5)):
        for side, sy, tilt in (("l", -2.90, 20.0), ("r", 2.90, -20.0)):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_shroud_{side}_{index}",
                    (spec.SHAFT_X1 + WT + 0.22, sy, chevron_z),
                    (0.34, 2.30, 1.05),
                    lacquer_black,
                    bevel=0.05,
                    rotation=(math.radians(tilt), 0.0, 0.0),
                    metric_uv=(1.2, 1.2),
                )
            )
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_shroud_edge_{side}_{index}",
                    (spec.SHAFT_X1 + WT + 0.40, sy, chevron_z),
                    (0.10, 2.30, 0.22),
                    accent_yellow,
                    bevel=0.03,
                    rotation=(math.radians(tilt), 0.0, 0.0),
                    metric_uv=(0.8, 0.8),
                )
            )

    # ---- peg field ------------------------------------------------------
    # 25 pegs, no wall stubs: the even rows' outermost peg is driven INTO the
    # wall slab instead (see spec.py, WHY THE WALL STUBS ARE GONE - a stub
    # crown standing level with the outermost odd peg was an 11.3 deg shelf,
    # shallower than ICE's 21.8 deg friction angle, so it held cars outright).
    for row, z in enumerate(spec.PEG_ROW_Z):
        for column, x in enumerate(peg_row_xs(row)):
            build_peg(
                f"{MOD_ID}_peg_{row:02d}_{column:02d}",
                x,
                z,
                materials,
                objects,
            )

    # ---- bins -----------------------------------------------------------
    # Round-4 bin band: the payoff zone wears the machine's own colours.
    # Divider bodies are the cabinet's cream enamel, ridge caps its deep
    # red, and the pockets themselves are dark gunmetal trays - so from the
    # crown the player looks down cream/red teeth into dark mouths, and the
    # ONE gilded pocket (gold back panel, gold horn faces, gold ridge caps,
    # kept from round 3) reads as the prize against them.
    for index, center in enumerate(spec.BIN_CENTERS):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_bin_back_{index}",
                (center, DY - 0.05, (BIN_Z + RIDGE) / 2.0),
                (spec.BIN_PITCH - 2.1, 0.10, RIDGE - BIN_Z),
                gold if index == 2 else bin_gunmetal,
                bevel=0.0,
                metric_uv=(2.0, 2.0),
            )
        )
    for index, center_x in enumerate(DIVIDER_X):
        lean = 0.0
        if abs(center_x + spec.BIN_PITCH / 2.0) < 0.01:
            lean = spec.CENTER_HORN_LEAN
        elif abs(center_x - spec.BIN_PITCH / 2.0) < 0.01:
            lean = -spec.CENTER_HORN_LEAN
        divider = extruded_profile(
            f"{MOD_ID}_divider_{index}",
            divider_section(center_x, center_x + lean),
            spec.DIVIDER_Y_FRONT,
            DY,
            board_cream,
            uv_meters=2.0,
        )
        if lean != 0.0:
            # Horned divider: the faces looking INTO the jackpot pocket go
            # gold (ridge-to-shoulder slope, inner wall, inner fillet); the
            # outer faces and the end caps stay cream enamel. Material slot
            # 1 is appended after extruded_profile's own assign, so slot 0
            # stays cream and only the picked faces re-index. Face picking
            # is by outward normal: the inner side of the left horn faces
            # +x (lean > 0), the right horn -x, and |normal.y| > 0.5 skips
            # the extrusion end caps.
            divider.data.materials.append(gold)
            inward = 1.0 if lean > 0.0 else -1.0
            for polygon in divider.data.polygons:
                if abs(polygon.normal[1]) > 0.5:
                    continue
                if polygon.normal[0] * inward > 0.35:
                    polygon.material_index = 1
        objects.append(divider)
        # Cap on each ridge: the deflector the car actually bounces off.
        # The two horns flanking the jackpot carry the crown's gold; the
        # outer dividers cap their cream bodies in the cabinet's red
        # (round 4 - the old hazard chevrons were the last industrial
        # livery inside the payoff band).
        objects.append(
            bk.add_box(
                f"{MOD_ID}_ridge_cap_{index}",
                (center_x + lean, (spec.DIVIDER_Y_FRONT + DY) / 2.0, RIDGE - 0.12),
                (0.5, DY - spec.DIVIDER_Y_FRONT, 0.24),
                gold if lean != 0.0 else board_red,
                bevel=0.05,
                metric_uv=(1.2, 1.2),
            )
        )
    # Value plates on a fascia beam across the front of the bins.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_fascia",
            (0.0, spec.DIVIDER_Y_FRONT - 0.35, RIDGE + 0.55),
            (2 * HW + 2 * WT, 0.70, 1.10),
            # The reference's ball tray is CREAM plastic with chrome trim,
            # not chrome. A 25 m nickel beam under a nickel bezel under a
            # nickel marker rail put three plates of the same grey in one
            # column and the payout band went cold; cream ties it to the
            # divider bodies instead and lets the brass frames read.
            board_cream,
            bevel=0.04,
            metric_uv=(2.4, 2.4),
        )
    )
    # Round-4 plaques: sized to be READ from the front elevation, not only
    # from the apron. Every plaque hangs from one fixed top line (plate tops
    # at RIDGE + 0.60, frame tops at RIDGE + 0.78 = 5.78) and grows DOWN, so
    # the module-level marker rule holds untouched: the pointer's tip
    # (z 5.85) still stops 7 cm above the tallest frame. The marquee family
    # draws text centred into a fixed 9.55:1 strip, so each display face
    # samples a measured WINDOW around the ink. Windows are measured, not
    # guessed (scratch ink-bbox pass over the shipped sign textures, round
    # 3; re-run for round 4 to split the jackpot texture into its words):
    #   3000 ink u 0.4160-0.5820   1500 u 0.4199-0.5820  digits v 0.2285-0.7715
    #   800  ink u 0.4375-0.5605   400  u 0.4355-0.5605
    #   JACKPOT word u 0.1973-0.5645    10000 word u 0.5918-0.7988
    # Round 3 held every plaque at its window's exact strip-space aspect;
    # round 4 trades that purity for legibility. Undistorted digits tall
    # enough for the front shot would need plates wider than the 4.80 m bin
    # pitch can seat side by side, so the four digit plaques share a 1.55 m
    # height and draw their numerals 1.13-1.22x taller than true - a
    # deliberate condensed-poster stretch, mild enough to read as type.
    # Widths taper with the money (4.10/3.80 four-digit, 3.40/3.20 three-
    # digit) and were chosen so adjacent copper frames never touch (worst
    # gap 0.09 m, 1500-to-jackpot; outermost frame edge 11.83 < 12.70).
    value_plate_specs = [
        # (width, height, u_center, u_window, v_center, v_window)
        (4.10, 1.55, 0.4990, 0.2136, 0.5000, 0.680),  # 3000
        (3.80, 1.55, 0.5010, 0.2136, 0.5000, 0.680),  # 1500
        (4.90, 2.80, None, None, None, None),  # JACKPOT: assembled below
        (3.40, 1.55, 0.4990, 0.1780, 0.5000, 0.680),  # 800
        (3.20, 1.55, 0.4980, 0.1780, 0.5000, 0.680),  # 400
    ]
    plate_top_z = RIDGE + 0.60

    def window_display_face(plate, width, height, u_center, u_window, v_center, v_window):
        """Re-aim a sign_plate's -Y display face at a measured ink window."""

        mesh = plate.data
        layer = mesh.uv_layers.active
        for polygon in mesh.polygons:
            if polygon.normal[1] >= -0.9:
                continue  # edge faces keep sign_plate's background pin
            for loop_index in polygon.loop_indices:
                co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
                layer.data[loop_index].uv = (
                    u_center + (co[0] / width) * u_window,
                    v_center + (co[2] / height) * v_window,
                )

    for index, center in enumerate(spec.BIN_CENTERS):
        width, height, u_center, u_window, v_center, v_window = value_plate_specs[index]
        plate_z = plate_top_z - height / 2.0
        # Thin copper surround, the crown sign frame's treatment: front face
        # 0.14 proud of the fascia, back face buried 2 cm inside it so the
        # butt joint can never z-fight.
        objects.append(
            bk.add_box(
                f"{MOD_ID}_value_frame_{index}",
                (center, spec.DIVIDER_Y_FRONT - 0.76, plate_z),
                (width + 0.36, 0.16, height + 0.36),
                # Round 5: four brass frames and one CHROME one. The frame is
                # the cheapest way to say which plaque belongs to which half
                # of the fusion, and the jackpot is the modern one.
                nickel if index == 2 else copper,
                bevel=0.04,
                metric_uv=(1.2, 1.2),
            )
        )
        plate = sign_plate(
            f"{MOD_ID}_value_plate_{index}",
            # Plate spans y -7.39..-7.33: its back face is buried 1 cm inside
            # the frame's front face (-7.34) - an overlap is invisible, a
            # coincident plane is a z-fight.
            (center, spec.DIVIDER_Y_FRONT - 0.86, plate_z),
            width,
            height,
            materials[f"{MOD_ID}_sign_bin_{index}"],
        )
        if index == 2:
            # THE HOLOGRAPHIC JACKPOT: one oversized plate - 4.90 x 2.80,
            # ~2.6x a digit plaque's area, in a chrome frame. Every face of
            # the backing plate pins to the texture's field texel, so it is a
            # solid panel of the plaque's own violet-black. Pinned marquee
            # field rather than paint, because the word strips in front
            # sample the SAME texture - plate field and strip field then
            # cannot mismatch by a hue.
            layer = plate.data.uv_layers.active
            for polygon in plate.data.polygons:
                for loop_index in polygon.loop_indices:
                    layer.data[loop_index].uv = (0.5, 0.02)
            objects.append(plate)
            # Two cream lines sampled from the one JACKPOT 10000 texture by
            # the measured word windows above: stacked type on the big red
            # field, the classic payout-plaque composition. Strip backs sit
            # 1 cm inside the red plate's front face (-7.39) - an overlap
            # is invisible, a coincident plane is a z-fight. Vertical
            # stretch matches the digit plaques' regime: JACKPOT 1.33x,
            # 10000 1.18x.
            # ROUND-5 WINDOWS, RE-MEASURED. The holo path draws a chrome
            # outline and a drop shadow OUTSIDE the glyph, so this texture's
            # ink is wider and taller than the flat round-4 texture's and
            # every one of these six numbers moved. Measured off the built
            # PNG (scratch ink-bbox pass, the same instrument as round 3/4):
            #   JACKPOT ink u 0.1953-0.5723   10000 ink u 0.5898-0.8066
            #   ink v band 0.1465-0.8086 (asymmetric: the shadow falls down)
            # The u margins are 0.008 a side, not round 4's 0.022: the two
            # words are only 0.0175 apart in u now, and the wider margin
            # pulled a slice of the neighbouring word into each window.
            # Strip sizes are then DERIVED so the glyphs keep their round-4
            # size on the plate - the outline and shadow are what grew, not
            # the type.
            for tag, word_w, word_h, word_z, wu_c, wu_w in (
                ("jackpot_word", 4.18, 1.14, plate_top_z - 0.12 - 0.57, 0.3838, 0.3930),
                ("jackpot_value", 3.07, 1.28, plate_top_z - height + 0.12 + 0.64, 0.6982, 0.2328),
            ):
                strip = sign_plate(
                    f"{MOD_ID}_{tag}",
                    (center, spec.DIVIDER_Y_FRONT - 0.91, word_z),
                    word_w,
                    word_h,
                    materials[f"{MOD_ID}_sign_bin_{index}"],
                )
                window_display_face(strip, word_w, word_h, wu_c, wu_w, 0.4775, 0.7521)
                objects.append(strip)
        else:
            window_display_face(plate, width, height, u_center, u_window, v_center, v_window)
            objects.append(plate)
    # ---- payout marker rail ---------------------------------------------
    # The fixed half of the scoreboard. The moving half is the "marker" part:
    # a pointer trolley that drives to the bin the car actually landed in.
    # Everything here lives 5 m above the drive-out apron and carries no cage
    # nodes - it is pure theatre and no car can reach it.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_marker_rail",
            (0.0, MARKER_RAIL_Y, MARKER_RAIL_Z),
            (2 * (HW + WT), 0.32, 0.34),
            nickel,
            bevel=0.03,
            metric_uv=(1.6, 1.6),
        )
    )
    for index, x in enumerate((-HW - WT + 0.30, HW + WT - 0.30)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_marker_post_{index}",
                (x, MARKER_RAIL_Y, (RIDGE + 1.10 + MARKER_RAIL_Z) / 2.0),
                (0.40, 0.40, MARKER_RAIL_Z - RIDGE - 1.10),
                nickel,
                bevel=0.03,
                metric_uv=(1.6, 1.6),
            )
        )
    # One index tick per bin, on the rail's top face and dead over the bin
    # centre, so the trolley's park position is readable as a value and not
    # just as a position.
    for index, center in enumerate(spec.BIN_CENTERS):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_marker_tick_{index}",
                (center, MARKER_RAIL_Y, MARKER_RAIL_Z + 0.23),
                (0.20, 0.34, 0.14),
                copper,
                bevel=0.02,
                metric_uv=(0.6, 0.6),
            )
        )

    # ---- floors, aprons and the traffic island --------------------------
    # Both aprons are embankments, not planks: the slab is thick enough that
    # its underside is at or below grade everywhere (AGENTS.md - a constant
    # thickness ramp leaves a hole under its high end that cars drop into).
    def sloped_slab(name, width, y_low, z_low, y_high, z_high, thickness, material):
        run = y_high - y_low
        rise = z_high - z_low
        angle = math.atan2(rise, run)
        length = math.hypot(run, rise)
        mid_y = (y_low + y_high) / 2.0
        mid_z = (z_low + z_high) / 2.0
        return bk.add_box(
            name,
            (
                0.0 if name.endswith("exit_apron") else (HW + spec.DOCK_X1) / 2.0,
                mid_y + math.sin(angle) * thickness / 2.0,
                mid_z - math.cos(angle) * thickness / 2.0,
            ),
            (width, length, thickness),
            material,
            bevel=0.0,
            rotation=(angle, 0.0, 0.0),
            metric_uv=(3.0, 3.0),
        )

    objects.append(
        sloped_slab(
            f"{MOD_ID}_exit_apron",
            2 * HW,
            spec.EXIT_GROUND_Y,
            0.0,
            spec.DIVIDER_Y_FRONT,
            BIN_Z,
            1.0,
            asphalt,
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_dock_floor",
            ((HW + spec.DOCK_X1) / 2.0, 0.0, (BIN_Z + spec.DOCK_FLOOR_Z) / 2.0),
            (spec.DOCK_X1 - HW, 2 * DY, spec.DOCK_FLOOR_Z - BIN_Z),
            steel,
            bevel=0.0,
            metric_uv=(2.0, 2.0),
        )
    )
    ramp_run = -DY - spec.LOAD_GROUND_Y
    objects.append(
        sloped_slab(
            f"{MOD_ID}_load_ramp",
            spec.DOCK_X1 - HW,
            spec.LOAD_GROUND_Y,
            0.0,
            -DY,
            spec.DOCK_FLOOR_Z,
            1.4,
            asphalt,
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_traffic_island",
            (HW + 0.25, (-DY + spec.LOAD_GROUND_Y) / 2.0, 0.85),
            (0.5, ramp_run, 1.6),
            hazard,
            bevel=0.05,
            metric_uv=(1.4, 1.4),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_guard_wall",
            (spec.DOCK_X1 + 0.2, 0.0, (BIN_Z + spec.GUARD_TOP_Z) / 2.0),
            (0.4, 2 * DY, spec.GUARD_TOP_Z - BIN_Z),
            hazard,
            bevel=0.03,
            metric_uv=(1.8, 1.8),
        )
    )

    # ---- crown chute and hood -------------------------------------------
    chute_section = [
        (spec.APRON_X_LO, apron_z(spec.APRON_X_LO)),
        (spec.APRON_X_HI, apron_z(spec.APRON_X_HI)),
        (spec.APRON_X_HI, apron_z(spec.APRON_X_HI) - spec.APRON_T),
        (spec.APRON_X_LO, apron_z(spec.APRON_X_LO) - spec.APRON_T),
    ]
    objects.append(
        extruded_profile(
            f"{MOD_ID}_chute", chute_section, -DY, DY, steel, uv_meters=2.0
        )
    )
    # The hood is the same slab lifted by the throat clearance: its UNDERSIDE
    # sits at apron_z + HOOD_CLEAR, which is exactly what the cage samples.
    hood_section = [
        (spec.APRON_X_LO, apron_z(spec.APRON_X_LO) + spec.HOOD_CLEAR + spec.APRON_T),
        (spec.APRON_X_HI, apron_z(spec.APRON_X_HI) + spec.HOOD_CLEAR + spec.APRON_T),
        (spec.APRON_X_HI, apron_z(spec.APRON_X_HI) + spec.HOOD_CLEAR),
        (spec.APRON_X_LO, apron_z(spec.APRON_X_LO) + spec.HOOD_CLEAR),
    ]
    # The hood wears the cabinet's deep red, not raw duct steel: it is the
    # machine's upper lip, and the drop should read as the parlor swallowing
    # the car rather than as HVAC.
    objects.append(
        extruded_profile(
            f"{MOD_ID}_chute_hood", hood_section, -DY, DY, board_red, uv_meters=2.0
        )
    )
    # Hazard edge rails down both chute sides: the throat's flanks, marked
    # like the working edges they are, so the crown mouth reads as a mouth.
    # Pure decor - the cage's chute surfaces are untouched. Bottom edge sinks
    # 6 cm into the slab and the ends stop clear of both the chute's own
    # x = APRON_X_LO cap plane (the gate leaf swings there; low end starts
    # 10 cm up-slope, inside the chute_lip's hazard band) and the tipper
    # hinge line at APRON_X_HI, so no face is coplanar with slab, lip or
    # deck. Outboard faces run 2 cm past the wall planes into the backboard
    # and the screen band - an overlap is invisible, a gap is a hole.
    rail_h = 0.42
    rail_x_lo = spec.APRON_X_LO + 0.10
    rail_x_hi = spec.APRON_X_HI - 0.30
    rail_section = [
        (rail_x_lo, apron_z(rail_x_lo) + rail_h),
        (rail_x_hi, apron_z(rail_x_hi) + rail_h),
        (rail_x_hi, apron_z(rail_x_hi) - 0.06),
        (rail_x_lo, apron_z(rail_x_lo) - 0.06),
    ]
    for side, rail_y0, rail_y1 in (
        ("l", -DY - 0.02, -DY + 0.40),
        ("r", DY - 0.40, DY + 0.02),
    ):
        objects.append(
            extruded_profile(
                f"{MOD_ID}_chute_rail_{side}",
                rail_section,
                rail_y0,
                rail_y1,
                hazard,
                uv_meters=1.2,
            )
        )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_chute_lip",
            (spec.APRON_X_LO + 0.2, 0.0, apron_z(spec.APRON_X_LO) + 0.18),
            (0.6, 2 * DY, 0.36),
            hazard,
            bevel=0.05,
            metric_uv=(1.2, 1.2),
        )
    )

    # ---- mast, sheaves, static chain loop --------------------------------
    for side, sy in (("l", -spec.MAST_HALF_Y), ("r", spec.MAST_HALF_Y)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_mast_{side}",
                (spec.MAST_X, sy, spec.MAST_TOP_Z / 2.0 + BIN_Z / 2.0),
                (0.9, 0.9, spec.MAST_TOP_Z - BIN_Z),
                steel,
                bevel=0.05,
                metric_uv=(2.2, 2.2),
            )
        )
    for index in range(12):
        z = 3.0 + index * 4.0
        objects.append(
            bk.add_box(
                f"{MOD_ID}_mast_brace_{index:02d}",
                (spec.MAST_X, 0.0, z),
                (0.45, 2 * spec.MAST_HALF_Y, 0.45),
                steel,
                bevel=0.03,
                metric_uv=(1.8, 1.8),
            )
        )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_mast_head",
            (spec.MAST_X, 0.0, spec.MAST_TOP_Z - 0.6),
            (2 * spec.SHEAVE_R + 1.4, 2 * spec.MAST_HALF_Y + 0.9, 1.2),
            steel,
            bevel=0.06,
            metric_uv=(2.0, 2.0),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_mast_head_hazard",
            (spec.MAST_X, 0.0, spec.MAST_TOP_Z - 0.05),
            (2 * spec.SHEAVE_R + 1.44, 2 * spec.MAST_HALF_Y + 0.94, 0.30),
            hazard,
            bevel=0.0,
            metric_uv=(1.4, 1.4),
        )
    )
    # Foot sheave and the closed chain loop: constant geometry, so nothing has
    # to be stretched at runtime (only the head sheave turns).
    for side, sy in (("l", -1.35), ("r", 1.35)):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_foot_sheave_{side}",
                (spec.MAST_X, sy, spec.BOTTOM_SHEAVE_Z),
                spec.SHEAVE_R,
                0.35,
                copper,
                vertices=28,
                axis="Y",
                metric_uv=(1.0, 1.0),
            )
        )
    for run, rx in (("front", spec.CHAIN_FRONT_X), ("back", spec.CHAIN_BACK_X)):
        for side, sy in (("l", -1.35), ("r", 1.35)):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_chain_{run}_{side}",
                    (rx, sy, (spec.BOTTOM_SHEAVE_Z + spec.SHEAVE_Z) / 2.0),
                    (0.22, 0.22, spec.SHEAVE_Z - spec.BOTTOM_SHEAVE_Z),
                    steel,
                    bevel=0.02,
                    metric_uv=(0.35, 0.35),
                )
            )

    # ---- hoistway realism: rails, machine deck, buffer, ladder ----------
    # The service-lift dressing a real chain hoist carries. Everything here
    # is VISUAL: collision comes from the cage, which this block never
    # touches, and every piece lives outside the deck's swept volume and the
    # car's reachable envelope (x > DECK_X1 or above the crown platform).
    #
    # Carriage guide rails: the vertical steel the yoke's guide rollers
    # visibly run on, faces tangent to the rollers at x = MAST_X - 0.35.
    # They land on the existing mast braces, which read as their supports.
    rail_z0 = BIN_Z + 0.45
    rail_z1 = spec.DECK_DOCK_Z + spec.YOKE_HEIGHT + 0.2  # 48.8, under the deck
    for side, sy in (("l", -spec.MAST_HALF_Y), ("r", spec.MAST_HALF_Y)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_guide_rail_{side}",
                (spec.MAST_X - 0.34, sy, (rail_z0 + rail_z1) / 2.0),
                (0.16, 0.70, rail_z1 - rail_z0),
                steel,
                bevel=0.02,
                metric_uv=(1.2, 1.2),
            )
        )
    # Counterweight guide rails, flush against the x = SHAFT_X1 back wall;
    # the counterweight part carries matching shoes that ride them.
    for side, sy in (("l", -0.9), ("r", 0.9)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_cw_rail_{side}",
                (spec.SHAFT_X1 - 0.15, sy, (BIN_Z + 0.8 + 48.5) / 2.0),
                (0.30, 0.40, 48.5 - BIN_Z - 0.8),
                steel,
                bevel=0.02,
                metric_uv=(1.2, 1.2),
            )
        )
    # Machine deck at the crown: a grated platform under the head sheave with
    # a chain slot down the middle, cross girders carrying the axle's bearing
    # pedestals, and the drive (gear housing, brake disc) on the right slab.
    # Platform underside (48.975) clears the docked trolley arm's top (48.875)
    # and the rollers (48.95); the chain grab pokes up through the slot the
    # way a real overslung grab does.
    platform_z = spec.DECK_DOCK_Z + spec.YOKE_HEIGHT + 0.55  # 49.15 centre
    for side, sy in (("l", -2.72), ("r", 2.72)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_machine_slab_{side}",
                (spec.MAST_X, sy, platform_z),
                (5.0, 1.44, 0.35),
                steel,
                bevel=0.03,
                metric_uv=(1.6, 1.6),
            )
        )
    for tag, ex in (("front", spec.MAST_X - 2.3), ("back", spec.MAST_X + 2.3)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_machine_beam_{tag}",
                (ex, 0.0, platform_z),
                (0.4, 6.86, 0.4),
                steel,
                bevel=0.03,
                metric_uv=(1.6, 1.6),
            )
        )
    for tag, gx in (("a", spec.MAST_X - 0.7), ("b", spec.MAST_X)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_machine_girder_{tag}",
                (gx, 0.0, platform_z),
                (0.5, 4.2, 0.3),
                steel,
                bevel=0.02,
                metric_uv=(1.4, 1.4),
            )
        )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_machine_nosing",
            (spec.MAST_X - 2.3, 0.0, platform_z + 0.26),
            (0.42, 6.9, 0.12),
            hazard,
            bevel=0.0,
            metric_uv=(1.2, 1.2),
        )
    )
    # Bearing pedestals capture the sheave axle's ends; the axle spins inside
    # them, which is exactly what a bearing looks like doing.
    for side, sy in (("l", -1.7), ("r", 1.7)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_bearing_pedestal_{side}",
                (spec.MAST_X, sy, spec.SHEAVE_Z - 0.5),
                (0.8, 0.35, 1.35),
                steel,
                bevel=0.03,
                metric_uv=(1.0, 1.0),
            )
        )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hoist_gearbox",
            (spec.MAST_X, 2.7, platform_z + 0.71),
            (1.2, 1.05, 1.05),
            copper,
            bevel=0.05,
            metric_uv=(1.0, 1.0),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hoist_drive_housing",
            (spec.MAST_X, 2.15, spec.SHEAVE_Z - 0.5),
            (0.45, 0.5, 1.1),
            steel,
            bevel=0.03,
            metric_uv=(0.8, 0.8),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_brake_disc",
            (spec.MAST_X, 1.98, spec.SHEAVE_Z),
            0.5,
            0.14,
            steel,
            vertices=24,
            axis="Y",
            metric_uv=(0.8, 0.8),
        )
    )
    # Counterweight buffer in the pit: pad, plinth and coil, topping out
    # 0.25 m under the counterweight's lowest point of travel (3.115).
    objects.append(
        bk.add_box(
            f"{MOD_ID}_buffer_pad",
            (spec.CW_X, 0.0, BIN_Z + 0.18),
            (1.6, 1.6, 0.18),
            concrete,
            bevel=0.0,
            metric_uv=(1.2, 1.2),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_buffer_plinth",
            (spec.CW_X, 0.0, BIN_Z + 0.52),
            (1.1, 1.1, 0.5),
            steel,
            bevel=0.03,
            metric_uv=(1.0, 1.0),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_buffer_coil",
            (spec.CW_X, 0.0, BIN_Z + 1.6),
            0.30,
            1.65,
            copper,
            vertices=20,
            axis="Z",
            metric_uv=(0.8, 0.8),
        )
    )
    # Oil pan under the foot sheaves - the chain wheels run wet in it.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_foot_oil_pan",
            (spec.MAST_X, 0.0, BIN_Z + 0.09),
            (3.2, 3.4, 0.18),
            steel,
            bevel=0.02,
            metric_uv=(1.4, 1.4),
        )
    )
    # Service ladder up the mast's -Y column and the electrical riser conduit
    # up its +Y face: the two things every real hoistway wall grows.
    for tag, ly in (("a", -spec.MAST_HALF_Y - 0.12), ("b", -spec.MAST_HALF_Y + 0.32)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_ladder_stringer_{tag}",
                (spec.MAST_X + 0.62, ly, (BIN_Z + 0.6 + 46.0) / 2.0),
                (0.09, 0.09, 46.0 - BIN_Z - 0.6),
                steel,
                bevel=0.0,
                metric_uv=(0.8, 0.8),
            )
        )
    for index in range(29):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_ladder_rung_{index:02d}",
                (spec.MAST_X + 0.62, -spec.MAST_HALF_Y + 0.1, 1.4 + index * 1.5),
                (0.06, 0.50, 0.06),
                steel,
                bevel=0.0,
                metric_uv=(0.5, 0.5),
            )
        )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_riser_conduit",
            (spec.MAST_X, spec.MAST_HALF_Y - 0.54, (BIN_Z + 0.5 + 46.0) / 2.0),
            0.08,
            46.0 - BIN_Z - 0.5,
            steel,
            vertices=12,
            axis="Z",
            metric_uv=(0.5, 0.5),
        )
    )
    for index, jz in enumerate((8.0, 24.0, 40.0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_riser_jbox_{index}",
                (spec.MAST_X, spec.MAST_HALF_Y - 0.58, jz),
                (0.35, 0.22, 0.5),
                copper,
                bevel=0.02,
                metric_uv=(0.5, 0.5),
            )
        )

    # ---- signage --------------------------------------------------------
    # Lacquered hardwood backer board behind the red marquee (round 4; it
    # was the copper family, and at a 23.6 m spread the patina mottle
    # stopped reading as metal - it read as mud-brown rust-streaked
    # planking. Now it IS planking, on purpose: warm red-brown French-
    # polished boards, the thing a real parlor marquee hangs on, in a hue
    # deeper and redder than the copper so backer and brass never blur).
    # 23.6 wide, not 2*HW+1.4: the old 25.4 span reached x -13.7, straight
    # through the left flank marquee that now stands at the same crown band
    # (x -13.27..-12.72), and it also framed the 20.06 m plate asymmetrically.
    # 23.6 centred at -1.0 gives the plate an even 1.77 m border both sides
    # and ends 8 cm inside the flank frame's backer, where the butt joint is
    # an invisible same-material overlap.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_sign_frame",
            (-1.0, -DY - 0.55, spec.SIGN_Z0 + spec.SIGN_H / 2.0),
            (23.6, 0.5, spec.SIGN_H + 0.8),
            marquee_wood,
            bevel=0.06,
            metric_uv=(2.0, 2.0),
        )
    )
    objects.append(
        sign_plate(
            f"{MOD_ID}_sign_title",
            (-1.0, -DY - 0.82, spec.SIGN_Z0 + spec.SIGN_H / 2.0),
            spec.SIGN_H * 9.55,
            spec.SIGN_H,
            materials[f"{MOD_ID}_sign_title"],
        )
    )
    # Round 5: the marquee gets its MODERN half. A nickel bezel frames the
    # lacquered backer (deco lettering in a chrome surround is the exact
    # hinge between the two languages), and a segmented rainbow lamp bar runs
    # the full width above and below the title - the lit rail every
    # contemporary parlour machine wears over its marquee. Same honest
    # limitation as the board tubes: lacquer, not light.
    for tag, rail_z in (
        ("over", spec.SIGN_Z0 + spec.SIGN_H + 0.52),
        ("under", spec.SIGN_Z0 - 0.52),
    ):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_marquee_lamp_{tag}",
                (-1.0, -DY - 0.92, rail_z),
                0.30,
                23.0,
                lamp_rainbow,
                vertices=16,
                axis="X",
                metric_uv=(1.9, 6.0),
            )
        )
    # Rails only, no stiles: the backer is 23.6 wide precisely so its ends
    # butt 8 cm inside the FLANK marquee frames (see the backer note above),
    # and a vertical bezel bar there would drive straight through them. The
    # crown band's corners are already closed by the flank signs.
    for tag, cx, cz, bw, bh in (
        ("top", -1.0, spec.SIGN_Z0 + spec.SIGN_H + 0.86, 23.6, 0.44),
        ("bottom", -1.0, spec.SIGN_Z0 - 0.86, 23.6, 0.44),
    ):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_marquee_bezel_{tag}",
                (cx, -DY - 0.72, cz),
                (bw, 0.40, bh),
                nickel,
                bevel=0.05,
                metric_uv=(1.6, 1.6),
            )
        )
    for index, x in enumerate((-HW + 1.0, HW - 1.0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_sign_post_{index}",
                (x, -DY - 0.55, (TOP + spec.SIGN_Z0) / 2.0),
                (0.7, 0.5, spec.SIGN_Z0 - TOP + 0.8),
                nickel,
                bevel=0.04,
                metric_uv=(1.8, 1.8),
            )
        )
    # Fictional maker's plate and inspection tag, on the doorway lintel where
    # the driver stops under them. FICTIONAL AND DELIBERATELY SO: the
    # reference photographs carry a real manufacturer's mark and real
    # certification stickers and none of it is reproduced - "Kogane-Do
    # Amusement Works" and the "Parlour Machine Inspection Board" are
    # invented, and the model/serial/certificate numbers are this mod's own
    # build numbers. Small on purpose: a data plate legible from 40 m is a
    # billboard, and the pack's own finding (goal post, boot) is that what
    # makes a plate read as real is the FORMAT, plus the fact that it is
    # small enough that you have to go and look.
    for tag, plate_x, plate_w, plate_h, plate_material in (
        ("maker", 13.60, 1.65, 0.55, f"{MOD_ID}_plate_maker"),
        ("cert", 21.40, 1.32, 0.55, f"{MOD_ID}_plate_cert"),
    ):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_data_bezel_{tag}",
                (plate_x, -DY - WT - 0.07, spec.DOORWAY_HEAD_Z + 0.35),
                (plate_w + 0.20, 0.10, plate_h + 0.17),
                nickel,
                bevel=0.03,
                metric_uv=(0.8, 0.8),
            )
        )
        objects.append(
            sign_plate(
                f"{MOD_ID}_data_plate_{tag}",
                (plate_x, -DY - WT - 0.13, spec.DOORWAY_HEAD_Z + 0.35),
                plate_w,
                plate_h,
                materials[plate_material],
            )
        )
    objects.append(
        sign_plate(
            f"{MOD_ID}_sign_load",
            ((HW + spec.DOCK_X1) / 2.0, -DY - WT - 0.03, spec.DOORWAY_HEAD_Z + 0.9),
            6.0,
            6.0 / 9.55,
            materials[f"{MOD_ID}_sign_load"],
        )
    )

    # Flank title plates: from either side the tower used to be an unlabeled
    # slab. Same marquee texture as the crown sign, on an X-facing plate.
    # UV conventions derived the way sign_plate's were, not guessed: the
    # world transform is a 180 deg yaw, so for a display face with authored
    # normal +outward*X, a viewer facing that flank (in game AND in the
    # preview camera) has authored outward*+Y to their right - hence
    # u = outward * y. v grows with +z in both frames.
    def flank_sign(name, face_x, outward, z_center, width, material):
        height = width / 9.55
        obj = bk.add_box(
            name,
            (face_x + outward * 0.03, 0.0, z_center),
            (0.06, width, height),
            material,
            bevel=0.0,
        )
        mesh = obj.data
        layer = mesh.uv_layers.active or mesh.uv_layers.new(name="UVMap")
        for polygon in mesh.polygons:
            display = polygon.normal[0] * outward > 0.9
            for loop_index in polygon.loop_indices:
                if not display:
                    layer.data[loop_index].uv = (0.5, 0.02)
                    continue
                co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
                layer.data[loop_index].uv = (
                    outward * co[1] / width + 0.5,
                    co[2] / height + 0.5,
                )
        return obj

    # The flank marquees live at the CROWN BAND, not lost at mid-wall: a
    # 6.6 m plate at z 40 on 46 m of red panelling was unreadable and left
    # the side elevation anonymous. 11 m plates centred on the front
    # marquee's own band (SIGN_Z0 + SIGN_H/2), each backed by the crown
    # backer's lacquered wood and a pair of steel posts off the wall top, so
    # the title band wraps the cabinet and the tower says PACHINKO TOWER
    # from every elevation. Purely decorative: everything here floats above
    # z 46.8, unreachable, no cage geometry.
    flank_w = 11.0
    flank_h = flank_w / 9.55
    flank_z = spec.SIGN_Z0 + spec.SIGN_H / 2.0
    flank_frame_z0 = flank_z - (flank_h + 0.8) / 2.0
    for tag, wall_x, outward in (
        ("r", spec.SHAFT_X1 + WT, 1.0),
        ("l", -HW - WT, -1.0),
    ):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_sign_flank_frame_{tag}",
                (wall_x + outward * 0.27, 0.0, flank_z),
                (0.5, flank_w + 1.4, flank_h + 0.8),
                marquee_wood,
                bevel=0.06,
                metric_uv=(2.0, 2.0),
            )
        )
        # Posts straddle the wall's own top course (10 cm buried in the
        # face, 40 cm proud) and run up into the frame, the crown posts'
        # own mounting idiom.
        for sub, post_y in enumerate((-2.9, 2.9)):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_sign_flank_post_{tag}_{sub}",
                    (
                        wall_x + outward * 0.15,
                        post_y,
                        (TOP - 0.4 + flank_frame_z0 + 0.4) / 2.0,
                    ),
                    (0.5, 0.7, flank_frame_z0 + 0.8 - TOP),
                    nickel,
                    bevel=0.04,
                    metric_uv=(1.8, 1.8),
                )
            )
        objects.append(
            flank_sign(
                f"{MOD_ID}_sign_flank_{tag}",
                # Plate back lands 1 cm inside the frame's front face.
                wall_x + outward * 0.51,
                outward,
                flank_z,
                flank_w,
                materials[f"{MOD_ID}_sign_title"],
            )
        )

    # Vertical parlor sign down the outboard shaft face: the side elevation
    # used to present eight identical red panels; now it presents the
    # machine. Stacked per-letter marquee plaques spelling P-A-C-H-I-N-K-O,
    # upright letters on white fields in the payout plaques' red ink, each
    # in the value plaques' copper frame idiom, all hung from a steel spine
    # buried 10 cm into the wall the way the flank sign posts are. Pure
    # decor on an unreachable face - no cage geometry anywhere near it.
    # Standoffs: spine spans -0.10..0.30 proud (clears the 0.32 stringers'
    # band only where frames cover it), frames 0.02..0.52, plate faces at
    # 0.54, so the stack reads in front of the panelling from every angle.
    #
    # Window math is the value plates' own: each square plaque samples a
    # measured window around the letter's ink so the letter fills the
    # plaque undistorted. A square plate at the marquee strip's 9.55:1
    # aspect means u_window = v_window / 9.55; ink bboxes measured off the
    # shipped letter textures (scratch ink-bbox pass, same instrument as
    # the value plates'): u widths 0.012 ("I") to 0.055 ("A"/"O") centred
    # at the u_centers below, ink v band 0.229-0.775 centred at 0.502, so
    # the 0.70 window leaves every letter 7% of clear field top and bottom.
    letter_u_centers = (0.5010, 0.5000, 0.5000, 0.5000, 0.5000, 0.5000, 0.5029, 0.5000)
    letter_v_center = 0.502
    letter_v_window = 0.70
    letter_u_window = letter_v_window / 9.55
    # ROUND 2: these were local numbers here and are spec data now, because
    # the eight letter floods are positioned off the plates and the capture
    # harness aims a camera at the plate face. A dimension used in three files
    # cannot live in one of them.
    letter_plate = spec.LETTER_PLATE
    letter_gap = spec.LETTER_GAP
    letter_step = spec.LETTER_STEP
    letter_face_x = spec.LETTER_FACE_X  # 23.70, the outboard wall face
    letter_top_z = spec.LETTER_TOP_Z  # top frame edge 43.26, clear of the crown
    assert letter_face_x == spec.SHAFT_X1 + WT, "letter face drifted from the wall"
    spine_top = letter_top_z + 0.50
    spine_bottom = letter_top_z - 7 * letter_step - letter_plate - 0.50
    objects.append(
        bk.add_box(
            f"{MOD_ID}_letter_spine",
            (letter_face_x + 0.10, 0.0, (spine_top + spine_bottom) / 2.0),
            (0.40, 0.80, spine_top - spine_bottom),
            nickel,
            bevel=0.03,
            metric_uv=(1.8, 1.8),
        )
    )
    for index in range(8):
        plate_z = spec.LETTER_PLATE_Z[index]
        objects.append(
            bk.add_box(
                f"{MOD_ID}_letter_frame_{index}",
                (letter_face_x + 0.27, 0.0, plate_z),
                (0.50, letter_plate + 0.36, letter_plate + 0.36),
                copper,
                bevel=0.06,
                metric_uv=(1.2, 1.2),
            )
        )
        plate = bk.add_box(
            f"{MOD_ID}_letter_plate_{index}",
            (spec.LETTER_PLATE_X, 0.0, plate_z),
            (0.06, letter_plate, letter_plate),
            materials[f"{MOD_ID}_sign_letter_{index}"],
            bevel=0.0,
        )
        mesh = plate.data
        layer = mesh.uv_layers.active or mesh.uv_layers.new(name="UVMap")
        for polygon in mesh.polygons:
            # Display face looks outboard (+x); flank_sign's derivation
            # gives u = outward * y with outward = +1 here. Every other
            # face pins to a background texel.
            display = polygon.normal[0] > 0.9
            for loop_index in polygon.loop_indices:
                if not display:
                    layer.data[loop_index].uv = (0.5, 0.02)
                    continue
                co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
                layer.data[loop_index].uv = (
                    letter_u_centers[index] + (co[1] / letter_plate) * letter_u_window,
                    letter_v_center + (co[2] / letter_plate) * letter_v_window,
                )
        objects.append(plate)

    # ---- the PA horn pole ------------------------------------------------
    objects.extend(build_horn_pole(materials))
    return objects


def build_parts(materials) -> dict[str, dict[str, object]]:
    steel = materials[f"{MOD_ID}_steel"]
    hazard = materials[f"{MOD_ID}_hazard"]
    copper = materials[f"{MOD_ID}_copper"]
    grip = materials[f"{MOD_ID}_deck_grip"]

    parts: dict[str, dict[str, object]] = {}
    deck_top = spec.DECK_HOME_Z
    deck_mid_x = (spec.DECK_X0 + spec.DECK_X1) / 2.0

    # ---- tipper: the deck plate that both carries and releases the car ---
    # Its pivot is the crown chute's hinge line, so a tipped deck and the
    # fixed chute meet exactly, by construction rather than by tuning.
    tipper_objects = [
        bk.add_box(
            f"{MOD_ID}_deck_plate",
            (deck_mid_x, 0.0, deck_top - 0.125),
            (spec.DECK_X1 - spec.DECK_X0, 2 * spec.DECK_HALF_Y, 0.25),
            grip,
            bevel=0.03,
            metric_uv=(1.2, 1.2),
        ),
    ]
    for index, sy in enumerate((-spec.DECK_HALF_Y + 0.3, spec.DECK_HALF_Y - 0.3)):
        tipper_objects.append(
            bk.add_box(
                f"{MOD_ID}_deck_rib_{index}",
                (deck_mid_x, sy, deck_top - 0.42),
                (spec.DECK_X1 - spec.DECK_X0, 0.36, 0.42),
                steel,
                bevel=0.03,
                metric_uv=(1.4, 1.4),
            )
        )
    # Ratchet pawl. It is authored lying along +x from the hinge, so it swings
    # with the deck and therefore always points at whichever tooth of the
    # carriage-mounted rack the current detent corresponds to - no per-detent
    # placement, the mechanism is correct by construction.
    #
    # It lives at +Y ONLY, in the 0.15 m gap between the deck edge (3.30) and
    # the back wall (3.45). The -Y side is the drive-in lane: a 0.18 m bar
    # lying across the threshold there would be a wheel-height obstacle on a
    # surface AGENTS.md caps relief at 0.02 m, and the tipper is a collision
    # part, so it really would be one.
    tipper_objects.append(
        bk.add_box(
            f"{MOD_ID}_ratchet_pawl",
            (spec.APRON_X_HI + RATCHET_R_OUT - 0.27, RATCHET_PAWL_Y, deck_top),
            (0.66, 0.06, 0.18),
            steel,
            bevel=0.02,
            metric_uv=(0.7, 0.7),
        )
    )
    parts["tipper"] = {
        "objects": tipper_objects,
        "pivot": (spec.APRON_X_HI, 0.0, deck_top),
        "collision": True,
    }

    # ---- deck edging: hazard-striped KERBS, flush enough to drive over.
    #
    # These carry no collision, and for a long time they were drawn as a
    # 0.5 m wall across the deck's outboard edge plus a 0.4 m bar along its
    # far end. That made the player's very first interaction with the whole
    # machine driving straight THROUGH a striped steel backstop, which is the
    # one thing a prop must never do: a surface that is drawn as an obstacle
    # has promised to behave like one. Giving them collision is not the fix
    # either - the part's own stale home bake would then stand a phantom rail
    # in the loading bay for the whole 60 s the carriage is away, which is
    # exactly why they were moved off the tipper and stripped of collision in
    # the first place.
    #
    # So they are drawn as what they can honestly be: KERB_H-tall painted
    # edging, the marking a real lift platform actually has. Nothing about
    # the machine needs them to stop a car any more - the release became an
    # EJECT off a LEVEL deck, so the tip is an empty-deck flourish and there
    # is no longer a car aboard to be backstopped when it plays. The drive-in
    # end (-Y) was always open, and "car leaves the deck mid-hoist" is the
    # slip-abort's job.
    KERB_H = 0.06
    rails_objects = [
        # Outboard edge marking.
        bk.add_box(
            f"{MOD_ID}_deck_kick",
            (spec.DECK_X1 - 0.2, 0.0, deck_top + KERB_H / 2.0),
            (0.4, 2 * spec.DECK_HALF_Y, KERB_H),
            hazard,
            bevel=0.02,
            metric_uv=(1.2, 1.2),
        ),
        # Far-end edge marking; the near end (-Y) and the release end (-X)
        # stay unmarked so the drive-in and the ejection line read as open.
        bk.add_box(
            f"{MOD_ID}_deck_stop",
            (deck_mid_x, spec.DECK_HALF_Y - 0.2, deck_top + KERB_H / 2.0),
            (spec.DECK_X1 - spec.DECK_X0, 0.4, KERB_H),
            hazard,
            bevel=0.02,
            metric_uv=(1.2, 1.2),
        ),
    ]
    parts["deck_rails"] = {
        "objects": rails_objects,
        "pivot": (spec.APRON_X_HI, 0.0, deck_top),
    }

    # ---- carriage: trolley, yoke and chain grab (translates only) --------
    yoke_top = deck_top + spec.YOKE_HEIGHT
    carriage_objects = [
        bk.add_box(
            f"{MOD_ID}_yoke_beam",
            (spec.DECK_X1 + 0.3, 0.0, yoke_top),
            (0.6, 2 * spec.DECK_HALF_Y + 0.6, 0.5),
            steel,
            bevel=0.05,
            metric_uv=(1.6, 1.6),
        ),
        bk.add_box(
            f"{MOD_ID}_trolley_arm",
            ((spec.DECK_X1 + 0.3 + spec.MAST_X) / 2.0, 0.0, yoke_top),
            (spec.MAST_X - spec.DECK_X1 - 0.3, 1.3, 0.55),
            steel,
            bevel=0.05,
            metric_uv=(1.6, 1.6),
        ),
        bk.add_box(
            f"{MOD_ID}_chain_grab",
            (spec.CHAIN_FRONT_X, 0.0, yoke_top + 0.5),
            (0.55, 1.1, 0.7),
            copper,
            bevel=0.05,
            metric_uv=(1.0, 1.0),
        ),
    ]
    for index, sy in enumerate((-spec.DECK_HALF_Y - 0.05, spec.DECK_HALF_Y + 0.05)):
        carriage_objects.append(
            bk.add_box(
                f"{MOD_ID}_yoke_post_{index}",
                (spec.DECK_X1 + 0.3, sy, deck_top + spec.YOKE_HEIGHT / 2.0),
                (0.5, 0.5, spec.YOKE_HEIGHT),
                steel,
                bevel=0.04,
                metric_uv=(1.6, 1.6),
            )
        )
    for index, (sy, sz) in enumerate(
        ((-spec.MAST_HALF_Y, 0.0), (spec.MAST_HALF_Y, 0.0))
    ):
        del sz
        carriage_objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_guide_roller_{index}",
                (spec.MAST_X, sy, yoke_top),
                0.35,
                0.5,
                copper,
                vertices=16,
                axis="Y",
                metric_uv=(0.8, 0.8),
            )
        )
    # Ratchet rack: a toothed sector centred on the tipper's hinge line, with
    # one tooth per entry of spec.BEHAVIOR["tip_detents"]. The detent ladder is
    # therefore visible as geometry rather than only as timing, and the rack
    # rides the carriage so it stays registered with the hinge at every height.
    carriage_objects.append(
        extruded_profile(
            f"{MOD_ID}_ratchet_rack",
            ratchet_section(spec.APRON_X_HI, deck_top, spec.BEHAVIOR["tip_detents"]),
            RATCHET_RACK_Y - 0.035,
            RATCHET_RACK_Y + 0.035,
            steel,
            uv_meters=0.8,
        )
    )
    # Cab cage: the open steel car a real service lift wraps its platform in.
    # The -Y edge stays fully open (it is the drive-in doorway); the +Y face
    # gets posts and an X-brace, both sides get a top rail tying into the
    # yoke, and one slim corner rod marks the -Y hinge-side corner. Every
    # member sits OUTSIDE the deck's y half-extent (3.30) so the tipping deck
    # sweeps past without touching, inboard of the wall plane at 3.45, and
    # clear of the rack (x <= 14.22) and the pawl's swing.
    cab_top = deck_top + 4.2
    for index, px in enumerate((14.6, 17.0)):
        carriage_objects.append(
            bk.add_box(
                f"{MOD_ID}_cab_post_{index}",
                (px, spec.DECK_HALF_Y + 0.08, (deck_top + 0.1 + cab_top) / 2.0),
                (0.22, 0.14, cab_top - deck_top - 0.1),
                steel,
                bevel=0.02,
                metric_uv=(1.0, 1.0),
            )
        )
    for index, sy in enumerate((-spec.DECK_HALF_Y - 0.08, spec.DECK_HALF_Y + 0.08)):
        carriage_objects.append(
            bk.add_box(
                f"{MOD_ID}_cab_rail_{index}",
                (15.2, sy, cab_top + 0.15),
                (4.4, 0.14, 0.26),
                steel,
                bevel=0.02,
                metric_uv=(1.0, 1.0),
            )
        )
    carriage_objects.append(
        bk.add_box(
            f"{MOD_ID}_cab_corner_rod",
            (13.2, -spec.DECK_HALF_Y - 0.08, (deck_top + 0.1 + cab_top) / 2.0),
            (0.14, 0.14, cab_top - deck_top - 0.1),
            steel,
            bevel=0.02,
            metric_uv=(0.8, 0.8),
        )
    )
    brace_angle = math.atan2(3.6, 2.4)
    for index, sign in enumerate((-1.0, 1.0)):
        carriage_objects.append(
            bk.add_box(
                f"{MOD_ID}_cab_brace_{index}",
                (15.8, spec.DECK_HALF_Y + 0.08, deck_top + 2.15),
                (4.3, 0.12, 0.18),
                steel,
                bevel=0.0,
                rotation=(0.0, sign * brace_angle, 0.0),
            )
        )
    parts["carriage"] = {
        "objects": carriage_objects,
        "pivot": (deck_mid_x, 0.0, deck_top),
    }

    # ---- counterweight ---------------------------------------------------
    cw_objects = [
        bk.add_box(
            f"{MOD_ID}_cw_block",
            (spec.CW_X, 0.0, spec.CW_TOP_Z - spec.CW_H / 2.0),
            (spec.CW_W, 2.2, spec.CW_H),
            materials[f"{MOD_ID}_concrete"],
            bevel=0.08,
            metric_uv=(1.4, 1.4),
        ),
        bk.add_box(
            f"{MOD_ID}_cw_band",
            (spec.CW_X, 0.0, spec.CW_TOP_Z - 0.35),
            (spec.CW_W + 0.05, 2.25, 0.5),
            hazard,
            bevel=0.0,
            metric_uv=(1.2, 1.2),
        ),
        bk.add_box(
            f"{MOD_ID}_cw_shoe",
            ((spec.CW_X + spec.MAST_X) / 2.0, 0.0, spec.CW_TOP_Z - 0.4),
            (spec.CW_X - spec.MAST_X, 1.4, 0.45),
            steel,
            bevel=0.04,
            metric_uv=(1.2, 1.2),
        ),
    ]
    # Guide shoes riding the static cw_rail pair at the x = SHAFT_X1 wall.
    for index, (sy, sz) in enumerate(
        ((-0.9, spec.CW_TOP_Z - 0.5), (0.9, spec.CW_TOP_Z - 0.5),
         (-0.9, spec.CW_TOP_Z - 2.0), (0.9, spec.CW_TOP_Z - 2.0))
    ):
        cw_objects.append(
            bk.add_box(
                f"{MOD_ID}_cw_guide_shoe_{index}",
                (spec.SHAFT_X1 - 0.53, sy, sz),
                (0.55, 0.5, 0.35),
                steel,
                bevel=0.03,
                metric_uv=(0.8, 0.8),
            )
        )
    parts["counterweight"] = {
        "objects": cw_objects,
        "pivot": (spec.CW_X, 0.0, spec.CW_TOP_Z),
    }

    # ---- head sheave (rotates with travel) --------------------------------
    sheave_objects = []
    for index, sy in enumerate((-1.35, 1.35)):
        sheave_objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_sheave_{index}",
                (spec.MAST_X, sy, spec.SHEAVE_Z),
                spec.SHEAVE_R,
                0.35,
                copper,
                vertices=28,
                axis="Y",
                metric_uv=(1.0, 1.0),
            )
        )
        for spoke in range(4):
            angle = spoke * math.pi / 4.0
            sheave_objects.append(
                bk.add_box(
                    f"{MOD_ID}_sheave_spoke_{index}_{spoke}",
                    (spec.MAST_X, sy, spec.SHEAVE_Z),
                    (2 * spec.SHEAVE_R - 0.18, 0.14, 0.22),
                    steel,
                    bevel=0.0,
                    rotation=(0.0, angle, 0.0),
                )
            )
    sheave_objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_sheave_axle",
            (spec.MAST_X, 0.0, spec.SHEAVE_Z),
            0.22,
            3.4,
            steel,
            vertices=14,
            axis="Y",
            metric_uv=(0.8, 0.8),
        )
    )
    parts["sheave"] = {
        "objects": sheave_objects,
        "pivot": (spec.MAST_X, 0.0, spec.SHEAVE_Z),
    }

    # ---- release gate flap ------------------------------------------------
    # Hangs across the chute throat when shut; folds flat against the hood at
    # GATE_OPEN_DEG. Both endpoints are safe places to leave a stale collision
    # bake (nothing drives on the chute), which is what lets it be a real
    # collision part instead of theatre.
    gate_section = [
        (spec.GATE_HINGE_X - 0.15, spec.GATE_HINGE_Z),
        (spec.GATE_HINGE_X + 0.15, spec.GATE_HINGE_Z),
        (spec.GATE_HINGE_X + 0.15, spec.GATE_HINGE_Z - spec.GATE_LEN),
        (spec.GATE_HINGE_X - 0.15, spec.GATE_HINGE_Z - spec.GATE_LEN),
    ]
    gate_objects = [
        extruded_profile(
            f"{MOD_ID}_gate_leaf", gate_section, -DY, DY, hazard, uv_meters=1.4
        ),
        bk.add_cylinder(
            f"{MOD_ID}_gate_hinge",
            (spec.GATE_HINGE_X, 0.0, spec.GATE_HINGE_Z),
            0.22,
            2 * DY + 0.3,
            steel,
            vertices=14,
            axis="Y",
            metric_uv=(0.9, 0.9),
        ),
    ]
    parts["gate"] = {
        "objects": gate_objects,
        "pivot": (spec.GATE_HINGE_X, 0.0, spec.GATE_HINGE_Z),
        "collision": True,
    }

    # ---- payout marker: the scoreboard, as a machine ----------------------
    # Textures cannot change at runtime, so the only honest readout a prop
    # can have is a part that MOVES to the answer. (This used to add "and
    # emissives are inert on this pipeline (AGENTS.md)" - RETIRED 2026-08-15,
    # round 17: a three-element `emissiveFactor` emits, and `emissiveMap`
    # multiplies per texel. The baked-texture half stands, and the moving
    # trolley is still the right readout for a machine that shows its working;
    # see THE EMISSIVE VERDICT in spec.py.) This trolley drives to the centre of the
    # bin the car really landed in, parks past the end of the scale when the
    # play scored nothing, and sweeps the fascia while the tower is idle.
    # No collision: it hangs 5 m above the drive-out apron and nothing can
    # reach it, so both pose endpoints are trivially safe.
    point_depth = 1.05
    point_center_z = MARKER_TIP_Z + point_depth / 2.0
    marker_objects = [
        bk.add_box(
            f"{MOD_ID}_marker_trolley",
            (0.0, MARKER_BODY_Y, MARKER_RAIL_Z),
            (1.70, 0.32, 0.62),
            steel,
            bevel=0.04,
            metric_uv=(0.8, 0.8),
        ),
        bk.add_box(
            f"{MOD_ID}_marker_stem",
            (0.0, MARKER_BODY_Y, (MARKER_RAIL_Z + point_center_z) / 2.0),
            (0.30, 0.26, MARKER_RAIL_Z - point_center_z),
            steel,
            bevel=0.02,
            metric_uv=(0.6, 0.6),
        ),
        bk.add_cylinder(
            f"{MOD_ID}_marker_collar",
            (0.0, MARKER_BODY_Y, point_center_z + point_depth / 2.0),
            0.38,
            0.20,
            copper,
            vertices=18,
            axis="Z",
            metric_uv=(0.5, 0.5),
        ),
        # Apex DOWN: radius_bottom 0 puts the point at the bottom of the cone.
        bk.add_cone(
            f"{MOD_ID}_marker_point",
            (0.0, MARKER_BODY_Y, point_center_z),
            0.0,
            0.62,
            point_depth,
            hazard,
            vertices=18,
        ),
    ]
    for index, sx in enumerate((-0.55, 0.55)):
        marker_objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_marker_roller_{index}",
                (sx, MARKER_RAIL_Y - 0.16, MARKER_RAIL_Z + 0.22),
                0.20,
                0.24,
                copper,
                vertices=16,
                axis="Y",
                metric_uv=(0.4, 0.4),
            )
        )
    parts["marker"] = {
        "objects": marker_objects,
        "pivot": (0.0, MARKER_BODY_Y, MARKER_RAIL_Z),
    }
    return parts


class NodeStore:
    """Position-keyed cage nodes on a 1 cm grid.

    Snapping guarantees two things at once: repeat requests for the same point
    return the SAME node (so panels share their corner columns instead of
    stacking duplicates), and no two nodes can ever land closer than 1 cm -
    the degenerate flexbody skinning triad that made the centrifuge's outer
    deck invisible for three days.
    """

    GRID = 0.01

    def __init__(self, cage: bk.CageBuilder) -> None:
        self.cage = cage
        self.by_key: dict[tuple[int, int, int], str] = {}

    def at(self, prefix: str, position, **options) -> str:
        key = tuple(int(round(value / self.GRID)) for value in position)
        existing = self.by_key.get(key)
        if existing is not None:
            return existing
        snapped = tuple(index * self.GRID for index in key)
        identifier = self.cage.add_node(
            f"{prefix}_{len(self.by_key):04d}", snapped, **options
        )
        self.by_key[key] = identifier
        return identifier

    def surface(
        self,
        prefix: str,
        grid: list[list[tuple[float, float, float]]],
        *,
        ground_model: str | Callable[[list[tuple[float, float, float]]], str] = "metal",
        collision: bool = True,
        quads: bool = True,
        weight: float = 90.0,
        friction: float = 0.9,
    ) -> list[list[str]]:
        """Node grid + full bracing + double-sided collision quads.

        ``quads=False`` really does disarm the surface: a node's collision
        flag alone does NOT (AGENTS.md - collision triangles are emitted
        independently of node flags), so the quads have to be skipped.

        ``ground_model`` may be a CALLABLE taking the quad's four authored
        corner points and returning the model name for that quad. This exists
        because the fall volume's board faces need mu = 0 above the bin mouths
        and the same node grids run down past them into the bins and the
        shaft - and splitting a surface in two to say so is not allowed: the
        vehicle-side audio binds to literal node id 0, so any change to the
        node ORDER moves it. A per-quad selector touches nothing but the
        groundModel string on triangles that already existed.
        """

        ids = [
            [
                self.at(prefix, point, fixed=True, collision=collision,
                        weight=weight, friction=friction)
                for point in column
            ]
            for column in grid
        ]
        for i, column in enumerate(ids):
            for j, identifier in enumerate(column):
                if j + 1 < len(column):
                    self.cage.add_beam(identifier, column[j + 1])
                if i + 1 < len(ids):
                    self.cage.add_beam(identifier, ids[i + 1][j])
                    if j + 1 < len(column):
                        self.cage.add_beam(identifier, ids[i + 1][j + 1])
                        self.cage.add_beam(column[j + 1], ids[i + 1][j])
                        if quads:
                            corners = [
                                grid[i][j],
                                grid[i + 1][j],
                                grid[i + 1][j + 1],
                                grid[i][j + 1],
                            ]
                            self.cage.add_quad_both(
                                [
                                    identifier,
                                    ids[i + 1][j],
                                    ids[i + 1][j + 1],
                                    column[j + 1],
                                ],
                                ground_model=(
                                    ground_model(corners)
                                    if callable(ground_model)
                                    else ground_model
                                ),
                            )
        return ids


def build_prism(
    store: NodeStore,
    prefix: str,
    section: list[tuple[float, float]],
    y0: float,
    y1: float,
    *,
    ground_model: str = "metal",
    weight: float = 70.0,
    skip_bands: tuple[int, ...] = (),
    cap_front: bool = False,
    section_b: list[tuple[float, float]] | None = None,
) -> list[list[str]]:
    """Cage twin of ``extruded_profile``: same sections, same numbers."""

    far = section_b if section_b is not None else section
    assert len(far) == len(section), "loft ends must share a vertex count"
    ids = [
        [
            store.at(prefix, (x, y0, z), fixed=True, collision=True, weight=weight)
            for x, z in section
        ],
        [
            store.at(prefix, (x, y1, z), fixed=True, collision=True, weight=weight)
            for x, z in far
        ],
    ]
    count = len(section)
    for station in ids:
        for index in range(count):
            store.cage.add_beam(station[index], station[(index + 1) % count])
        for index in range(2, count):
            store.cage.add_beam(station[0], station[index])
    for index in range(count):
        store.cage.add_beam(ids[0][index], ids[1][index])
        store.cage.add_beam(ids[0][index], ids[1][(index + 1) % count])
    for index in range(count):
        if index in skip_bands:
            continue
        nxt = (index + 1) % count
        store.cage.add_quad_both(
            [ids[0][index], ids[0][nxt], ids[1][nxt], ids[1][index]],
            ground_model=ground_model,
        )
    if cap_front:
        # Fan the front face so a car cannot enter the prism's open end.
        for index in range(1, count - 1):
            store.cage.add_triangle(
                ids[0][0], ids[0][index], ids[0][index + 1], ground_model=ground_model
            )
            store.cage.add_triangle(
                ids[0][index + 1], ids[0][index], ids[0][0], ground_model=ground_model
            )
    return ids


def assert_fall_volume_frictionless(cage: bk.CageBuilder) -> None:
    """No collision triangle inside the fall volume may have grip.

    Run against the BUILT cage, not against the list of ``store.surface``
    calls, and that distinction is the whole point: the source list says what
    someone MEANT, the triangle list says what a car will actually hit. A quad
    that straddles the volume boundary, a gusset, a fan cap, a surface added
    two years from now for some unrelated reason - all of them land here.

    The argument this defends is in spec.py (THE FALL VOLUME IS FRICTIONLESS
    TO ITS WALLS): at mu = 0 a two-contact rest is arithmetically impossible,
    so every gripping face inside this box is a way for the machine to hold a
    car up. One is enough to bring the hang back.

    ONE EXEMPTION, and it is geometric: a triangle lying flat in the bin-floor
    plane is the surface a scored car parks on and drives out over, and it
    keeps its asphalt. It is counted and reported rather than skipped
    silently, because the number of drive-on triangles in the pocket is
    itself a thing that should not change by accident.
    """

    offenders: list[str] = []
    exempt = 0
    for triangle in cage.triangles:
        points = [
            cage.nodes[cage.node_index[node]]["source_world_position"]
            for node in triangle["nodes"]
        ]
        if not all(in_fall_volume(point) for point in points):
            continue
        if is_drive_on_plane(points):
            exempt += 1
            continue
        if triangle["ground_model"] != spec.FALL_VOLUME_GROUNDMODEL:
            offenders.append(
                f"{triangle['nodes'][0]} ({triangle['ground_model']}) at "
                f"z {min(point[2] for point in points):.2f}"
                f"..{max(point[2] for point in points):.2f}"
            )
    if offenders:
        raise AssertionError(
            f"{len(offenders)} collision triangle(s) inside the fall volume "
            f"(z >= {spec.FALL_VOLUME_Z_LO}, |x| <= {HW}, |y| <= {DY}) are not "
            f"{spec.FALL_VOLUME_GROUNDMODEL}: a gripping face in the drop "
            "volume is a second contact, and a second contact is a hang. "
            f"First few: {offenders[:6]}"
        )
    # The drive-on exemption must exist and must stay small. Zero would mean
    # the bin floor had left the box (so the exemption is dead code and the
    # rule is not being tested); a big number would mean something horizontal
    # had been added at the park height without anyone deciding it should be
    # drive-on.
    assert exempt > 0, (
        "no collision triangle lies in the bin-floor plane inside the fall "
        "volume: the drive-on exemption is unreachable, which means a scored "
        "car has nothing gripping to park on"
    )
    print(
        f"[fall volume] frictionless from z {spec.FALL_VOLUME_Z_LO} to "
        f"{spec.WALL_TOP_Z}; {exempt} drive-on triangle(s) exempt at the "
        f"bin-floor plane z = {spec.FALL_VOLUME_DRIVE_ON_Z}"
    )


def _hull_margin(
    points: list[tuple[float, float]], probe: tuple[float, float]
) -> float:
    """Signed distance from ``probe`` to the boundary of conv(points).

    Positive means strictly inside, which is the only answer that makes the
    peg collapse a subset map. Monotone chain, because a peg section is four
    to a couple of dozen points and pulling in a hull library for that would
    be a dependency this generator does not otherwise need.
    """

    pts = sorted(set((round(x, 9), round(z, 9)) for x, z in points))
    if len(pts) < 3:
        return -float("inf")

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return -float("inf")
    # Counter-clockwise by construction, so the inward normal of edge (a, b)
    # points left of a->b and the signed distance is the 2D cross product over
    # the edge length.
    margin = float("inf")
    for i, a in enumerate(hull):
        b = hull[(i + 1) % len(hull)]
        ex, ez = b[0] - a[0], b[1] - a[1]
        length = math.hypot(ex, ez)
        if length <= 1e-12:
            continue
        d = (ex * (probe[1] - a[1]) - ez * (probe[0] - a[0])) / length
        margin = min(margin, d)
    return margin


def assert_peg_retract_is_subset_map(cage: bk.CageBuilder) -> None:
    """The peg collapse may never move a point OUTSIDE the peg it collapses.

    THIS INVARIANT EXISTS BECAUSE THE OLD ONE WAS A COMMENT (2026-08-15).
    spec.py asserted ``0 < PEG_WALL_INSET < PEG_R`` (0.6 < 1.1) and prose
    claimed the outer pegs' contraction point lands "on the wall plane" at
    x = 12.0. Neither statement is the safety condition and the second is not
    even true. The shift is applied by the VEHICLE Lua to the measured node
    CENTROID, not to the nominal peg x - and the centroid is pulled outboard
    by the F6 gusset, so the true contraction point is not where the prose
    says and its margin is whatever the lattice happens to leave. It was never
    computed. A gusset or lattice edit could have deleted the safety argument
    without failing anything.

    THE ACTUAL CONDITION. pegApply maps p -> c + (p - c) * s with s in [0, 1]
    and leaves y alone, so the image of a cross-section is a scaled copy of it
    about c. For a CONVEX section that image lies inside the original if and
    only if c lies inside the original - so the condition is exactly "the
    contraction point is inside the section", and it has to hold AT EVERY
    y-STATION, not merely for the peg as a whole. The scallop varies the
    section along the peg's length, so a centroid comfortably inside the
    widest station can still fall outside the narrowest one; and because the
    solid between two stations is their loft, c inside both endpoints implies
    c inside every section between them.

    This recomputes the contraction point the way the runtime does - group by
    the same ``_peg_RR_CC_`` node-name match, average the same node positions,
    apply the same outboard PEG_WALL_INSET shift to the same structurally
    identified outer columns - and fails the build if any station's section
    does not contain it.

    ON THE FRAME. The runtime reads positions in the vehicle frame and this
    reads authored positions, which differ by the model's 180 deg flip
    (x, y -> -x, -y). The shift is self-consistent under that flip: the
    runtime's `cx >= fieldX` test and the sign it selects BOTH invert, so the
    shift is outboard in either frame. The field centroid is asserted to sit
    on x = 0 so the `>=` tie-break cannot be what decides a peg's direction.
    """

    groups: dict[tuple[str, str], list[tuple[float, float, float]]] = {}
    for node in cage.nodes:
        match = re.search(r"_peg_(\d+)_(\d+)_", node["id"])
        if not match:
            continue
        groups.setdefault(match.groups(), []).append(node["source_world_position"])
    assert groups, "no peg nodes found: the subset-map invariant is not running"

    centroid = {
        key: (
            sum(p[0] for p in pts) / len(pts),
            sum(p[2] for p in pts) / len(pts),
        )
        for key, pts in groups.items()
    }
    field_x = sum(cx for cx, _ in centroid.values()) / len(centroid)
    assert abs(field_x) < 1e-6, (
        f"the peg field's centroid is at x = {field_x:.6f}, not 0: the outer "
        "peg shift's >= tie-break is no longer decided by symmetry and the "
        "two frames may disagree about which way is outboard"
    )

    # The outer columns, identified STRUCTURALLY exactly as the runtime does:
    # in a four-column row, the lowest and highest column index.
    outer: set[tuple[str, str]] = set()
    rows: dict[str, list[tuple[str, str]]] = {}
    for key in groups:
        rows.setdefault(key[0], []).append(key)
    for row_keys in rows.values():
        if len(row_keys) == 4:
            ordered = sorted(row_keys, key=lambda k: int(k[1]))
            outer.add(ordered[0])
            outer.add(ordered[-1])

    worst = None
    reported: list[str] = []
    for key, points in sorted(groups.items()):
        cx, cz = centroid[key]
        if key in outer:
            cx += spec.PEG_WALL_INSET if cx >= field_x else -spec.PEG_WALL_INSET
        stations: dict[float, list[tuple[float, float]]] = {}
        for px, py, pz in points:
            stations.setdefault(round(py, 6), []).append((px, pz))
        for station_y, section in sorted(stations.items()):
            margin = _hull_margin(section, (cx, cz))
            if worst is None or margin < worst[0]:
                worst = (margin, key, station_y, cx, cz)
            if margin <= 0.0:
                reported.append(
                    f"peg {key[0]}:{key[1]} station y={station_y:.3f} - "
                    f"contraction point ({cx:.4f}, {cz:.4f}) is "
                    f"{-margin:.4f} m OUTSIDE its own section"
                )
    if reported:
        raise AssertionError(
            "the peg collapse is not a subset map for "
            f"{len(reported)} peg station(s): a contraction point outside the "
            "section means the collapse SWEEPS STEEL OUTWARD through whatever "
            "is next to the peg, which is the one thing the retract is not "
            f"allowed to do. First few: {reported[:6]}"
        )
    assert worst is not None
    margin, key, station_y, cx, cz = worst
    print(
        f"[peg subset map] tightest station {key[0]}:{key[1]} at y={station_y:.3f}: "
        f"contraction point ({cx:.4f}, {cz:.4f}) is {margin:.4f} m inside its "
        f"section (PEG_WALL_INSET = {spec.PEG_WALL_INSET})"
    )


def build_cage() -> bk.CageBuilder:
    assert_no_clean_column()
    assert_no_two_contact_rest()
    cage = bk.CageBuilder(MOD_ID)
    store = NodeStore(cage)

    # ---- shell ----------------------------------------------------------
    right_z = [z for z in WALL_Z if z <= 41.5] + [RIGHT_WALL_TOP]
    front_z = [z for z in WALL_Z if z >= RIDGE]
    shaft_front_z = [z for z in WALL_Z if z >= spec.DOORWAY_HEAD_Z]

    # THE FOUR BOARD FACES. Their quads inside the fall volume are
    # FRICTIONLESS and everything else about them is untouched - see
    # FALL_VOLUME_GROUNDMODEL in spec.py for the wrench-count argument, and
    # assert_fall_volume_frictionless below for the invariant this has to
    # satisfy. Each of these is still ONE surface: the selector was built
    # precisely so none of them has to be split.
    back = store.surface(
        "back",
        [[(x, DY, z) for z in WALL_Z] for x in BACK_X],
        ground_model=fall_volume_ground_model,
    )
    front = store.surface(
        "front",
        [[(x, -DY, z) for z in front_z] for x in FRONT_X],
        ground_model=fall_volume_ground_model,
    )
    left = store.surface(
        "wleft",
        [[(-HW, y, z) for z in WALL_Z] for y in (-DY, 0.0, DY)],
        ground_model=fall_volume_ground_model,
    )
    right = store.surface(
        "wright",
        [[(HW, y, z) for z in right_z] for y in (-DY, 0.0, DY)],
        ground_model=fall_volume_ground_model,
    )
    store.surface(
        "sfront",
        [[(x, -DY, z) for z in shaft_front_z] for x in SHAFT_FRONT_X],
        ground_model="metal",
    )
    outer = store.surface(
        "wouter",
        [[(spec.SHAFT_X1, y, z) for z in WALL_Z] for y in (-DY, 0.0, DY)],
        ground_model="metal",
    )
    # Machinery guard: keeps every car out of the mast / chain / counterweight
    # volume. It runs parallel to the drive-in lane, never across it.
    store.surface(
        "guard",
        [[(spec.DOCK_X1, y, z) for z in (BIN_Z, 2.40, spec.GUARD_TOP_Z)]
         for y in (-DY, 0.0, DY)],
        ground_model="metal",
    )

    # ---- floors ---------------------------------------------------------
    store.surface(
        "binfloor",
        [[(x, y, BIN_Z) for y in BIN_Y] for x in BIN_X],
        ground_model="asphalt",
        friction=1.0,
    )
    exit_grid = [
        [
            (x, spec.DIVIDER_Y_FRONT, BIN_Z),
            (x, spec.EXIT_GROUND_Y, 0.0),
        ]
        for x in BIN_X
    ]
    store.surface("exitramp", exit_grid, ground_model="asphalt", friction=1.0)
    store.surface(
        "dockfloor",
        [[(x, y, spec.DOCK_FLOOR_Z) for y in (-DY, 0.0, DY)] for x in DOCK_X],
        ground_model="metal",
        friction=1.0,
    )
    store.surface(
        "loadramp",
        [[(x, -DY, spec.DOCK_FLOOR_Z), (x, spec.LOAD_GROUND_Y, 0.0)] for x in DOCK_X],
        ground_model="asphalt",
        friction=1.0,
    )
    store.surface(
        "pitfloor",
        [[(x, y, BIN_Z) for y in (-DY, 0.0, DY)]
         for x in (spec.DOCK_X1, spec.MAST_X, spec.SHAFT_X1)],
        ground_model="metal",
    )
    # Traffic island between the drive-in and drive-out lanes: without it the
    # two aprons meet at x = 12 with a 0.5 m lateral step.
    store.surface(
        "island",
        [
            [(HW, spec.LOAD_GROUND_Y, 0.0), (HW, spec.LOAD_GROUND_Y, 1.60)],
            [(HW, -DY, BIN_Z), (HW, -DY, 1.60)],
        ],
        ground_model="metal",
    )

    # ---- peg field ------------------------------------------------------
    peg_rows: list[list[list[list[str]]]] = []
    for row, z in enumerate(spec.PEG_ROW_Z):
        row_prisms = []
        xs = peg_row_xs(row)
        for column, x in enumerate(xs):
            # Chained station to station so the collision crown follows the
            # same wave the mesh does. NodeStore's grid snap welds the shared
            # faces, so this is one continuous solid, not N floating boxes.
            segs = scallop_stations()
            chain = None
            for si in range(len(segs) - 1):
                seg = build_prism(
                    store,
                    f"peg_{row:02d}_{column:02d}_{si:02d}",
                    peg_section(x, z, segs[si]),
                    segs[si],
                    segs[si + 1],
                    section_b=peg_section(x, z, segs[si + 1]),
                    # "frictionless" (2026-08-14h, player: "make sure they
                    # have the most slippery surface"). A pachinko ball never
                    # GRIPS a pin and neither should a tyre - grippy pegs let
                    # a wheel bite mid-carom and hang the car where slick
                    # steel would deflect it.
                    #
                    # THIS IS A REAL CHANGE, NOT A RE-LABEL. The pegs were on
                    # "ice" since 2026-08-13, and vanilla ICE is NOT
                    # frictionless: staticFrictionCoefficient 0.4, i.e. a
                    # 21.8 deg friction angle, so any face shallower than
                    # that held a car outright and "make the pegs slippery"
                    # never cured a hang. FRICTIONLESS is a separate vanilla
                    # entry in gameengine.zip art/groundmodels.json with
                    # staticFrictionCoefficient AND slidingFrictionCoefficient
                    # both exactly 0 - read out of the shipped file, not
                    # assumed - so there is no friction angle at all and no
                    # face of any slope can hold anything.
                    #
                    # IT IS ALSO WHAT MAKES THE CIRCULAR SECTION SAFE. An
                    # octagon's crown facets run 22.5 deg, which on ICE would
                    # have been a brand new resting shelf 0.73 m wide; on
                    # FRICTIONLESS it is not a shelf at all. The two player
                    # requests are coupled and must be reverted together.
                    #
                    # BE HONEST ABOUT ITS LIMITS. It cannot touch either
                    # STRUCTURAL failure mode: a flat car face bridging two
                    # crowns is a LEVEL TABLE, which needs no friction to hold
                    # a car, and a car wedged in a converging throat is
                    # carried by normal forces at any face angle. Only the
                    # lattice geometry above reaches those. What this does
                    # reach is the CRADLE (a floorpan draped over one crown)
                    # and the FLANK rest, which are the modes that live
                    # telemetry actually keeps finding.
                    ground_model="frictionless",
                    # Node weight is what the shipped mass is summed from, so
                    # it has to track the vertex count or the manifest tonnage
                    # follows the tessellation instead of the steel. The
                    # 8-vertex circle would otherwise have doubled the peg
                    # field's contribution (67 t of 105 t) for a section that
                    # grew only 19% in area: 70 * (4/8) * (2.553/2.145) = 42.
                    # The kite keeps the original 70. These nodes are all
                    # fixed=True, so this is a manifest number, not a physics
                    # one.
                    weight={"circle": 42.0, "dee": 47.0}.get(
                        spec.PEG_SECTION_SHAPE, 70.0
                    ),
                )
                # The row lacing below wants ONE pair of stations per peg: the
                # front face of the first segment and the back face of the last.
                # Anything in between is interior and must not be laced to a
                # neighbour, or the field stitches itself into a mesh of long
                # diagonal beams.
                if chain is None:
                    chain = [seg[0], seg[1]]
                else:
                    chain[1] = seg[1]
            row_prisms.append(chain)
        peg_rows.append(row_prisms)

    # Lace the field together: neighbours in a row, rows to each other, and
    # each row's ends into the side walls.
    for row, prisms in enumerate(peg_rows):
        for index in range(len(prisms) - 1):
            for station in range(2):
                cage.add_beam(prisms[index][station][1], prisms[index + 1][station][3])
        if row % 2 == 0:
            z = spec.PEG_ROW_Z[row]
            for station, wall_y in enumerate((-DY, DY)):
                cage.add_beam(
                    prisms[0][station][3],
                    store.at("wanchor", (-HW, wall_y, z), fixed=True, collision=False),
                )
                cage.add_beam(
                    prisms[-1][station][1],
                    store.at("wanchor", (HW, wall_y, z), fixed=True, collision=False),
                )
        if row > 0:
            upper = peg_rows[row - 1]
            for prism in prisms:
                target = min(
                    upper,
                    key=lambda other, p=prism: abs(
                        cage.nodes[cage.node_index[other[0][2]]]["source_world_position"][0]
                        - cage.nodes[cage.node_index[p[0][0]]]["source_world_position"][0]
                    ),
                )
                for station in range(2):
                    cage.add_beam(prism[station][0], target[station][2])

    # ---- bin dividers ---------------------------------------------------
    for index, center_x in enumerate(DIVIDER_X):
        lean = 0.0
        if abs(center_x + spec.BIN_PITCH / 2.0) < 0.01:
            lean = spec.CENTER_HORN_LEAN
        elif abs(center_x - spec.BIN_PITCH / 2.0) < 0.01:
            lean = -spec.CENTER_HORN_LEAN
        section = divider_section(center_x, center_x + lean)
        # Band index len(section) - 1 is the base line at the bin floor: it is
        # already floor, so emitting it would stack a second surface there.
        build_prism(
            store,
            f"divider_{index}",
            section,
            spec.DIVIDER_Y_FRONT,
            DY,
            # Slick like the pegs, and FRICTIONLESS with them since
            # 2026-08-14h: the 2026-08-13 live round wedged a car nose-down
            # between two divider horns and grip is half of what holds a wedge
            # together (the knocker escalation is the other half of that fix).
            # A divider is never a surface a car is meant to REST on - the bin
            # FLOOR it funnels into keeps its asphalt/1.0, because cars park
            # there and drive out of it - so there is nothing to trade away
            # here.
            ground_model="frictionless",
            skip_bands=(len(section) - 1,),
            cap_front=True,
        )

    # ---- crown chute and hood -------------------------------------------
    chute_top = [
        [(x, y, apron_z(x)) for y in (-DY, 0.0, DY)]
        for x in (spec.APRON_X_LO, 8.20, 10.40, spec.APRON_X_HI)
    ]
    # Slippery chute (2026-08-13, player: "make the ramp a slippery
    # surface"; FRICTIONLESS since 2026-08-14h, player: "make sure they have
    # the most slippery surface"): the release PUSHES the car over the level
    # deck's lip onto this 40 deg apron, so the apron must never let a braked
    # wheel bite and stall the drop. The chute has never relied on friction
    # for anything - it is a slope whose whole job is that gravity beats grip -
    # so taking mu from ICE's 0.4 to 0 removes the last way a locked wheel
    # could stall a release, and removes nothing. Triangle groundModel carries
    # car-vs-prop contact; the node frictionCoef rides along for completeness.
    store.surface("chute", chute_top, ground_model="frictionless", friction=0.0)
    hood_bottom = [
        [(x, y, apron_z(x) + spec.HOOD_CLEAR) for y in (-DY, 0.0, DY)]
        for x in (spec.APRON_X_LO, 8.20, 10.40, spec.APRON_X_HI)
    ]
    # The hood is a CEILING inside the fall volume, so it takes the same
    # selector as the board faces. Its geometry - and HOOD_CLEAR, the throat
    # height, which is a known latent cliff banked as its own round with its
    # own n - is deliberately NOT touched here. A metal ceiling left standing
    # inside a frictionless box is the same two-contact rest the walls were,
    # only upside down, and it would have forced the invariant below to be
    # weakened to accommodate it.
    store.surface("hood", hood_bottom, ground_model=fall_volume_ground_model)

    # ---- mast anchors (no collision: they live inside the guarded pit) ---
    mast_column: dict[str, list[str]] = {"l": [], "r": []}
    for side, sy in (("l", -spec.MAST_HALF_Y), ("r", spec.MAST_HALF_Y)):
        for z in (BIN_Z, 12.0, 24.0, 36.0, 46.0, spec.MAST_TOP_Z):
            mast_column[side].append(
                store.at(
                    "mast", (spec.MAST_X, sy, z), fixed=True, collision=False, weight=140.0
                )
            )
    for side in ("l", "r"):
        column = mast_column[side]
        for index in range(len(column) - 1):
            cage.add_beam(column[index], column[index + 1])
    for index in range(len(mast_column["l"])):
        cage.add_beam(mast_column["l"][index], mast_column["r"][index])
    cage.add_beam(mast_column["l"][0], outer[0][0])
    cage.add_beam(mast_column["r"][0], outer[2][0])
    cage.add_beam(mast_column["l"][1], outer[0][WALL_Z.index(11.60)])
    cage.add_beam(mast_column["r"][1], outer[2][WALL_Z.index(11.60)])
    cage.add_beam(mast_column["l"][4], outer[0][WALL_Z.index(spec.WALL_TOP_Z)])
    cage.add_beam(mast_column["r"][4], outer[2][WALL_Z.index(spec.WALL_TOP_Z)])

    # ---- header sign truss ----------------------------------------------
    header = store.surface(
        "header",
        [[(x, -DY, z) for z in (spec.SIGN_Z0, spec.SIGN_Z0 + spec.SIGN_H)]
         for x in (-HW, -4.0, 4.0, HW)],
        collision=False,
        quads=False,
        ground_model="metal",
    )
    for index, x in enumerate((-HW, -4.0, 4.0, HW)):
        cage.add_beam(header[index][0], front[index][-1])

    # ---- datum pier and reference frame ---------------------------------
    pier = cage.add_box_lattice(
        "datum",
        (-HW - 1.4, -6.0, 0.0),
        (-HW, -4.6, 1.2),
        subdivisions=(1, 1, 1),
        fixed=True,
        collision=False,
        collision_faces=("top", "south", "west", "east", "north"),
        face_ground_models={"top": "concrete"},
    )
    cage.add_beam(pier[(1, 1, 1)], left[0][0])
    cage.add_beam(pier[(1, 1, 0)], left[0][0])
    cage.add_beam(pier[(1, 0, 1)], left[0][0])
    cage.add_beam(pier[(1, 1, 1)], front[0][0])

    # Tie the exit apron / bin floor into the left and right walls so the
    # graph is one piece and the floor cannot be an island.
    for y_index, y in enumerate(BIN_Y):
        del y_index
        cage.add_beam(
            store.at("binfloor", (-HW, y, BIN_Z)),
            store.at("wleft", (-HW, -DY if y < 0 else DY, BIN_Z)),
        )
        cage.add_beam(
            store.at("binfloor", (HW, y, BIN_Z)),
            store.at("wright", (HW, -DY if y < 0 else DY, BIN_Z)),
        )
    cage.add_beam(
        store.at("dockfloor", (HW, 0.0, spec.DOCK_FLOOR_Z)),
        store.at("wright", (HW, 0.0, WALL_Z[1])),
    )
    cage.add_beam(
        store.at("pitfloor", (spec.SHAFT_X1, 0.0, BIN_Z)),
        store.at("wouter", (spec.SHAFT_X1, 0.0, BIN_Z)),
    )
    cage.add_beam(
        store.at("chute", (spec.APRON_X_HI, 0.0, apron_z(spec.APRON_X_HI))),
        store.at("wright", (HW, 0.0, RIGHT_WALL_TOP)),
    )
    for y in (-DY, DY):
        cage.add_beam(
            store.at("chute", (spec.APRON_X_HI, y, apron_z(spec.APRON_X_HI))),
            store.at("wright", (HW, y, RIGHT_WALL_TOP)),
        )
    # The hood hangs off the front and back walls at their 41.5 m station.
    cage.add_beam(
        store.at("hood", (spec.APRON_X_LO, DY, apron_z(spec.APRON_X_LO) + spec.HOOD_CLEAR)),
        store.at("back", (-4.0, DY, 41.5)),
    )
    cage.add_beam(
        store.at("hood", (spec.APRON_X_LO, -DY, apron_z(spec.APRON_X_LO) + spec.HOOD_CLEAR)),
        store.at("front", (4.0, -DY, 41.5)),
    )
    cage.add_beam(
        store.at("hood", (spec.APRON_X_HI, DY, apron_z(spec.APRON_X_HI) + spec.HOOD_CLEAR)),
        store.at("back", (HW, DY, 41.5)),
    )
    cage.add_beam(
        store.at("hood", (spec.APRON_X_HI, -DY, apron_z(spec.APRON_X_HI) + spec.HOOD_CLEAR)),
        store.at("front", (HW, -DY, 41.5)),
    )
    # Bin dividers into the bin floor they stand on.
    for center_x in DIVIDER_X:
        section = divider_section(center_x, center_x)
        for y in (spec.DIVIDER_Y_FRONT, DY):
            floor_node = store.at("binfloor", (center_x, y, BIN_Z))
            for x, z in (section[0], section[-1]):
                cage.add_beam(store.at("divider", (x, y, z)), floor_node)

    cage.set_refnodes_existing(
        ref=pier[(1, 1, 0)],
        back=pier[(1, 0, 0)],
        left=pier[(0, 1, 0)],
        up=pier[(1, 1, 1)],
    )
    cage.set_spawn_envelope(
        [
            left[0][0],
            left[2][0],
            left[0][WALL_Z.index(spec.WALL_TOP_Z)],
            left[2][WALL_Z.index(spec.WALL_TOP_Z)],
            outer[0][0],
            outer[2][0],
            outer[0][WALL_Z.index(spec.WALL_TOP_Z)],
            outer[2][WALL_Z.index(spec.WALL_TOP_Z)],
        ]
    )
    cage.auto_base_nodes()

    # Brute-force proof of the property NodeStore is supposed to guarantee.
    positions = [node["source_world_position"] for node in cage.nodes]
    buckets: dict[tuple[int, int, int], list[int]] = {}
    for index, position in enumerate(positions):
        key = tuple(int(math.floor(value / 0.05)) for value in position)
        buckets.setdefault(key, []).append(index)
    for key, members in buckets.items():
        neighbours = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    neighbours.extend(
                        buckets.get((key[0] + dx, key[1] + dy, key[2] + dz), [])
                    )
        for first in members:
            for second in neighbours:
                if second <= first:
                    continue
                a, b = positions[first], positions[second]
                distance = math.dist(a, b)
                if distance < 0.0099:
                    raise AssertionError(
                        f"coincident cage nodes {cage.nodes[first]['id']} / "
                        f"{cage.nodes[second]['id']} at {distance:.4f} m"
                    )
    assert_fall_volume_frictionless(cage)
    assert_peg_retract_is_subset_map(cage)
    return cage


def main() -> None:
    bk.reset_scene()
    materials = build_materials()
    visual_objects = build_visual(materials)
    part_builds = build_parts(materials)

    parts = []
    for name, build in sorted(part_builds.items()):
        dae_path = VEHICLE_DIR / f"{MOD_ID}_{name}.dae"
        info = bk.export_part_shape(
            MOD_ID, name, dae_path, build["objects"], build["pivot"]
        )
        info["path"] = f"vehicles/{MOD_ID}/{MOD_ID}_{name}.dae"
        if build.get("collision"):
            info["collision"] = True
        parts.append(info)

    visual = bk.export_flexbody_visual(
        MOD_ID,
        VEHICLE_DIR / f"{MOD_ID}.dae",
        visual_objects,
        f"{MOD_ID}_visual",
    )

    cage = build_cage()
    structure = cage.structure()
    behavior = dict(spec.BEHAVIOR)
    bk.write_handoff(
        AUTHORING_ROOT / f"{MOD_ID}.handoff.json",
        mod_id=MOD_ID,
        display_name=spec.DISPLAY_NAME,
        cage=cage,
        visual=visual,
        visual_dae_relative=f"vehicles/{MOD_ID}/{MOD_ID}.dae",
        visual_mesh_name=f"{MOD_ID}_visual",
        parts=parts,
        palette=spec.PALETTE,
        behavior={
            "tunables": behavior,
            "triggers": spec.TRIGGERS,
            "effects": spec.EFFECTS,
            "camera_distance": behavior.get("camera_distance", 30.0),
        },
    )
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        # 81 m out on a 32 mm lens covers 51 m of height: the whole board,
        # the bins, the drive-in doorway and the mast head all fit.
        camera_location=(54.0, -64.0, 32.0),
        look_at=(3.0, -1.0, 25.0),
    )
    print(
        f"PACHINKO_TOWER generator complete: {len(parts)} parts, "
        f"{len(structure['nodes'])} nodes, {len(structure['beams'])} beams, "
        f"{len(structure['triangles'])} triangles"
    )


if __name__ == "__main__":
    main()
