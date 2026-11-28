"""Campfire Basin terrain model for the standalone Hot Potato level (design v4).

Executable specification of the heightmap and the terrain-layer painting rule.
Everything is a pure function of world (x, y) about the anchor C = (850, -280, 100.000),
compass bearings (0 = +Y, 90 = +X), so `terrain_io.authored_height/authored_layer`
can be replaced by `height_field` / `layer_field` verbatim.

    python terrain_model.py            # builds the 2048^2 grid (cached in _terrain_cache.npz,
                                       # keyed by this file's hash), prints the verification
                                       # tables (markdown) and writes terrain_preview.png
                                       # + terrain_summary.json beside this file.

v2 changes (critic C r1): CLEAR_R 330 -> 350; the lake sector descends on a linear-with-fillets
profile to a 98.5 shelf and the WaterPlane rises to 98.0 (true ray test, not a profile);
the crest is a C1 cubic-Hermite ridge over 80 m instead of a fold; the noise-free / tree-free
/ meadow radius extends to 420 m inside the four lane sectors; every drivable line is checked
by second differences (|z[i-1] - 2 z[i] + z[i+1]| <= 0.020 m); every spawn is derived here.
v3 changes (critic C r2) - the SHIPPED law, with the rejected variants named as rejected:
(a) the road distance field (trail paint, noise-free band, relief mask) follows the SAME
corner-rounded centreline the profile instrument measures (v2 used the raw 7-point polyline,
4.87 m off it at the 57.15 deg wp4 corner). (b) The trail DecalRoad node list is pinned
(`trail_nodes` / `trail_nodes_xy`): the rounded centreline sampled at a UNIFORM
TRAIL_NODE_SPACING_M = 12.5 m = 71 nodes (2 ends, 9 on the R 40 arcs, 60 on straights), and a
uniform Catmull-Rom through it is measured against the rounded path (<= 0.17 m; a linear road
<= 0.49 m). REJECTED (first cut): nodes at every arc tangent point (<= 10 m on the arcs and
<= 25 m on the straights) - a uniform-parameter Catmull-Rom, which is what improvedSpline draws,
cusps through unevenly spaced nodes, and both tangent points of the 2.9 m wp5 arc between
20-25 m straights read a 102 mm per-metre grade spike, 5x the 20 mm relief law. (c) The
noise-free band starts 3 m outside the 6 m paint (9 -> 17 m) so the corridor about the
centreline is clean to +-6 m, not only +-3. (d) The wall's onset fillet is a QUARTIC in t
(ONSET_FILLET_KIND "quartic", ONSET_FILLET_M = 100.0 m): C2 at the onset - zero height, slope
AND curvature - with value and slope matched to t^1.45 at t0 = 100/span; the 1 deg analytic
sweep reads 15.6 mm at 319 deg with 0 of 366 bearings over the 20 mm law, and the lake's flank
banks stay at 11.6 %. REJECTED: v2's multiplicative smootherstep window (kind "window"), whose
2 f' g' cross term the 30 deg table missed - re-swept at 1 deg it is 24.9 mm at 319 deg with 18
bearings over the law. REJECTED: a C1 cubic in t over an 80 m fillet (kind "cubic", the first
fix tried) - 15.6 -> 16.6 mm, and because its curvature is largest AT the onset it steepened the
lake's flank banks from 15 % to 32 %. Both rejected laws stay executable: switch
ONSET_FILLET_KIND (and ONSET_FILLET_M / LAKE_ONSET_SIGMA) and re-run `analytic_sweep`.
(e) The lane runouts' heights and grades are printed per lane.
v4 changes (critic C r3): the four `trail corridor` rows of `relief_report` measure a TRAIL-ONLY
distance field (`trail_distance_field`); through v3 they masked on `road_d` = min(track circle,
trail centreline) with only an r > 252 filter, so the +-6 m and +-9 m rows also swept an annulus
of the TRACK's outer verge (r 252-254 and r 252-257) and overstated the trail corridor's cell
count by 30 % and 50 % - the maxima and the violation counts were unaffected and are unchanged.
`trail_spline_check` now samples its reference centreline at 0.1 m instead of 1 m: 1 m chords cut
the R 40 arcs by a c^2/(8 R) = 3.1 mm sagitta, which understated the Catmull-Rom's deviation as
0.16 m; measured against a 0.1 m reference it is 0.167 m (the critic's 0.05 m instrument reads
0.1672 on this centreline and 0.1683 on its own reconstruction of it).
Constants are the design's numbers; change them here, not in prose.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

# --- grid --------------------------------------------------------------------------
N = 2048  # nodes per side (2,047 m usable, half-open)
SQUARE = 1.0
CX, CY, Z_FLOOR = 850.0, -280.0, 100.0
POSITION = (CX - N * SQUARE / 2.0, CY - N * SQUARE / 2.0, 0.0)  # (-174, -1304, 0) = SW node
MAX_HEIGHT = 320.0  # unit = 320/65536 = 5/1024 m = 4.8828125 mm; 100.000 = u 20480 exactly
UNIT_M = MAX_HEIGHT / 65536.0
U_FLOOR = 20480
Z_CEIL = 65535 * UNIT_M  # 319.9951171875
RELIEF_LAW_M = 0.020  # max second difference across 1 m cells on a drivable line

# --- radial zones (metres from C) --------------------------------------------------
FLAT_R = 210.0  # exactly 100.000 everywhere inside (arena, hearth, ash bed, fire-ring feet)
CLEAR_R = 350.0  # v2: end of the clearing rise / start of the forest (was 330)
RISE_M = 2.4  # the meadow reaches +2.4 m at CLEAR_R outside the lake sector
LAKE_SHELF_Z = 98.5  # v2: the meadow floor at the lake's ellipse edge on LAKE_BEARING
LAKE_DESCENT_FILLET = 0.06  # the linear descent's fillets, as a fraction of the 140 m run
RISE_LAKE_SIGMA = 35.0  # angular width (deg) of the lake sector's descent
RIM_INSET = 90.0  # ridge crest sits >= 90 m inside the block edge; the back-slope hides the edge

# --- lanes (the arena's spout bearings and their perpendiculars) --------------------------
LANE_CENTRES = (60.0, 150.0, 240.0, 330.0)
LANE_HALF = 15.0  # full clearing inside +-15 deg
LANE_FEATHER = 22.0  # feathered to the plain CLEAR_R by +-22 deg
LANE_CLEAR_R = 420.0  # v2: noise-free, tree-free, meadow out to 420 m in the lane sectors

# --- lake ---------------------------------------------------------------------------------------
# B0 measured the sunset azimuth: 294.0 deg at clock 0.30 (sun 9.77 deg), compass convention
# (feasibility/b0/evidence.json, b0_summary.constants_for_the_design). The rule: the lake lies under
# the sun AND at the end of a lane -> LAKE_BEARING = sunset azimuth + 12 deg (from C the sun stands
# 12 deg left of the lake's centre, over the left third of its +-25.7 deg span; from the S1 eye the
# water spans 260-330 deg and the sun at 294 sits at 48 % of that span - over the middle of the
# water), and SUNSET_LANE = the lane nearest it (330, 24 deg off; a lane must be within +-30 deg of
# the lake or the ring would have to turn). v1/v2-draft carried 250.
SUNSET_AZIMUTH_MEASURED = 294.0
LAKE_BEARING = SUNSET_AZIMUTH_MEASURED + 12.0  # 306
LAKE_R = 540.0  # centre distance from C
LAKE_A = 260.0  # tangential semi-axis
LAKE_B = 190.0  # radial semi-axis
LAKE_LEVEL = 98.0  # v2: WaterPlane z (was 94.0) - raised so the water is seen from the apron
LAKE_FLOOR = 86.0  # flat bed inside e < 0.45 (12 m deep)
LAKE_ONSET_EXTRA = 420.0  # the basin wall starts beyond the far shore in the lake sector
LAKE_ONSET_SIGMA = 42.0  # v3: 40 -> 42 deg so the wall's foot clears the e <= 1.1 shore band on the lake's flanks (at +-20 deg the onset was 21 m inside it); with the v3 quartic fillet the shore-bank grade built here is max 11.6 % (v2's window read 15.0 %; the rejected C1 cubic at fillet 80 / sigma 40 read 32.2 %)


def _angdiff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


# the sunset lane is the lane nearest the lake bearing; every S1/R6/keep-out number derives from it
SUNSET_LANE = min(LANE_CENTRES, key=lambda c: _angdiff(LAKE_BEARING, c))  # 330 for LAKE_BEARING 306 (24 deg off; v1/v2-draft's 250 bearing gave 240)

# --- basin wall ------------------------------------------------------------------------
WALL_BASE = 150.0
WALL_SWING = 25.0
WALL_PEAK_BEARING = 40.0
NOTCH_LAKE = (LAKE_BEARING, 32.0, 70.3)  # (bearing, sigma deg, depth m): the outlet notch (sunset view)
NOTCH_TRAIL = (150.0, 30.0, 98.0)  # the SE saddle the trail leaves over (v2: 96.5 -> 98.0, trail grade <= 12 %)
WALL_EXPONENT = 1.45
# v3 (critic C r2 defect 3): the wall's first ONSET_FILLET_M metres are a QUARTIC in
# t = (r - onset)/span, A t^3 + B t^4 with A = (4 - p) t0^(p-3), B = (p - 3) t0^(p-4): zero height,
# slope AND curvature at the onset (C2, the gentle foot the lake banks and the forest edge rely on)
# and value + slope matched to H t^p at t0 = ONSET_FILLET_M / span. Its curvature peaks at 0.41 t0
# at 3.14 t0^(p-2) H / span^2 = 3.14 H fillet^-0.55 span^-1.45, i.e. bounded by the span, not by
# the fillet's slope: the 1 deg analytic sweep reads 15.6 mm where the lake sector's span is
# shortest (319 deg, H 94 m over ~150 m) and < 8 mm everywhere a line drives. v2's multiplicative
# smootherstep window H t^p S2((r - onset)/80) carried a 2 f' g' cross term (the power law's slope
# times the window's) that the 30 deg table missed: 23.9 mm at 315 deg (critic) and 18 bearings over
# 20 mm on the fine sweep. A cubic (A t^2 + B t^3, C1) was tried first: 16.6 mm, but its curvature
# is largest AT the onset and steepened the lake's flank banks from 15 % to 32 % - rejected.
ONSET_FILLET_M = 100.0  # v3: 80 -> 100 (the quartic's peak curvature falls as fillet^-0.55; the shortest lake-sector span, 153 m, still holds fillet + crest half-window = 140)
ONSET_FILLET_KIND = "quartic"  # "quartic" (v3) | "cubic" (tried, rejected) | "window" (v2); wall_profile implements all three so the sweep can be re-run on each
CREST_HALF_W = 40.0  # v2: C1 cubic-Hermite crest over [rim - 40, rim + 40]
TRAIL_CORNER_R = 40.0  # v2: the profile instrument follows the corner-rounded path a DecalRoad spline takes; v3: so do the paint, the noise band and the relief mask
BACKSLOPE = 0.12  # m per m beyond the crest
RIM_BASE_R = 930.0
RIM_HARMONICS = ((2, 60.0, 30.0), (5, 40.0, 100.0), (9, 18.0, 210.0))  # (order, amplitude m, phase deg)
RIM_LAKE_EXTRA = (60.0, 30.0)  # (m, sigma deg): the crest steps back behind the lake so the wall between the far shore and the notch is a slope, not a 60 % cliff (its onset is beyond the far shore)

# --- track / trail -----------------------------------------------------------------------
TRACK_R = 248.0  # visible dirt track centreline
TRACK_HALF_W = 4.0
TRAIL_BEARING = 150.0
# trail waypoints as (bearing, r) about C; the script converts to world xy
TRAIL_WAYPOINTS = ((150.0, 248.0), (150.0, 420.0), (143.0, 560.0), (147.0, 700.0), (155.0, 850.0), (151.0, 1000.0), (150.0, 1060.0))
TRAIL_WIDTH = 6.0  # the trail_surface DecalRoad width (the drivable +-3 m)
ROAD_PAINT_HALF_W = 6.0  # trail layer paint half-width (verges included)
ROAD_NOISE_FREE_START = 9.0  # v3: no noise within 9 m of a road centreline (v2: 6 = the paint edge, so the +-6 m corridor's neighbours already carried noise)
ROAD_NOISE_FREE_HALF_W = 17.0  # noise amplitude ramps 0 -> full between 9 and 17 m off the centreline (smoothstep, zero slope at both ends)
TRAIL_NODE_SPACING_M = 12.5  # v3: the pinned DecalRoad node list - the rounded centreline sampled every 12.5 m (uniform; see trail_nodes_xy)
SPLINE_REF_STEP_M = 0.1  # v4: the step the rounded centreline is sampled at as the REFERENCE polyline in trail_spline_check (1 m chords cut the R 40 arcs by a 3.1 mm sagitta and read the CR deviation 7 mm short)

# --- noise -------------------------------------------------------------------------------
SEED = 0x43414D50  # "CAMP"

LAYERS = (
    "hearth",  # 0 ASPHALT-class flagstone hearth, r <= 175 (incl. under the arena)
    "ash",  # 1 ember/ash bed 175-200 (+ drifts to 222)
    "scorch",  # 2 scorched earth 200-~258
    "trail",  # 3 packed dirt track + trail
    "meadow",  # 4 clearing grass / lake shelf / lane runouts
    "forest_floor",  # 5 needles, litter, roots
    "scree",  # 6 talus / gravel fans
    "rock",  # 7 cliff, > 62 % grade or ridged
    "shore",  # 8 lakeshore sand and pebbles
    "lakebed",  # 9 under water
    "alpine",  # 10 high turf / lichen above z 230
)
LAYER_ID = {name: i for i, name in enumerate(LAYERS)}


# --- helpers ---------------------------------------------------------------------------------
def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def smootherstep(t):
    """C2 at both ends (6t^5 - 15t^4 + 10t^3): the onset window of the wall."""
    t = np.clip(t, 0.0, 1.0)
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def trapezoid(u, a):
    """Linear ramp 0 -> 1 over u in [0, 1] with parabolic fillets of width a at both ends
    (C1 everywhere; curvature 1/(a (1 - a)) in u units). Normalised so f(1) = 1."""
    u = np.clip(u, 0.0, 1.0)
    f = np.where(u < a, u * u / (2.0 * a), np.where(u <= 1.0 - a, u - a / 2.0, (1.0 - a) - (1.0 - u) ** 2 / (2.0 * a)))
    return f / (1.0 - a)


def bearing_point(bearing_deg: float, r: float) -> tuple[float, float]:
    b = math.radians(bearing_deg)
    return (CX + r * math.sin(b), CY + r * math.cos(b))


def polar(x, y):
    dx, dy = x - CX, y - CY
    r = np.hypot(dx, dy)
    theta = np.degrees(np.arctan2(dx, dy)) % 360.0  # compass
    return r, theta


def ang_delta(theta, centre):
    return (theta - centre + 180.0) % 360.0 - 180.0


def value_noise(shape: tuple[int, int], cells: int, seed: int, octaves: int = 4, gain: float = 0.5) -> np.ndarray:
    """fBm value noise in [-1, 1] on the grid (bilinear upsampled random lattices)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(shape, dtype=np.float32)
    amp, total = 1.0, 0.0
    c = cells
    for _ in range(octaves):
        lattice = rng.random((c + 1, c + 1), dtype=np.float32) * 2.0 - 1.0
        ys = np.linspace(0, c, shape[0], endpoint=False, dtype=np.float32)
        xs = np.linspace(0, c, shape[1], endpoint=False, dtype=np.float32)
        y0 = np.floor(ys).astype(np.int32)
        x0 = np.floor(xs).astype(np.int32)
        fy = (ys - y0)[:, None]
        fx = (xs - x0)[None, :]
        fy = fy * fy * (3 - 2 * fy)
        fx = fx * fx * (3 - 2 * fx)
        a = lattice[y0][:, x0]
        b = lattice[y0][:, x0 + 1]
        cc = lattice[y0 + 1][:, x0]
        d = lattice[y0 + 1][:, x0 + 1]
        out += amp * ((a * (1 - fx) + b * fx) * (1 - fy) + (cc * (1 - fx) + d * fx) * fy)
        total += amp
        amp *= gain
        c *= 2
    return out / total


def rim_radius(theta_deg):
    """Distance from C to the ridge crest: an organic near-circle (930 +- ~110 m by angular
    harmonics), clipped by the square ring RIM_INSET inside the block edge so the crest never
    leaves the block."""
    t = np.radians(theta_deg)
    organic = RIM_BASE_R + sum(a * np.sin(k * t + np.radians(ph)) for k, a, ph in RIM_HARMONICS)
    organic = organic + RIM_LAKE_EXTRA[0] * np.exp(-((ang_delta(theta_deg, LAKE_BEARING) / RIM_LAKE_EXTRA[1]) ** 2))
    half = N * SQUARE / 2.0 - RIM_INSET  # 934
    square = half / np.maximum(np.abs(np.sin(t)), np.abs(np.cos(t)))
    return np.minimum(organic, square)


def wall_height(theta_deg):
    h = WALL_BASE + WALL_SWING * np.cos(np.radians(theta_deg - WALL_PEAK_BEARING))
    for centre, sigma, depth in (NOTCH_LAKE, NOTCH_TRAIL):
        h = h - depth * np.exp(-((ang_delta(theta_deg, centre) / sigma) ** 2))
    return h


def wall_onset(theta_deg):
    return CLEAR_R + LAKE_ONSET_EXTRA * np.exp(-((ang_delta(theta_deg, LAKE_BEARING) / LAKE_ONSET_SIGMA) ** 2))


def lane_weight(theta_deg):
    """1 inside +-LANE_HALF of a lane centre, feathered (smoothstep) to 0 at +-LANE_FEATHER."""
    w = np.zeros_like(np.asarray(theta_deg, dtype=np.float64))
    for lc in LANE_CENTRES:
        d = np.abs(ang_delta(theta_deg, lc))
        w = np.maximum(w, 1.0 - smoothstep((d - LANE_HALF) / (LANE_FEATHER - LANE_HALF)))
    return w


def clear_radius(theta_deg):
    """Radius of the noise-free / tree-free / meadow clearing: CLEAR_R, extended to LANE_CLEAR_R
    inside the four lane sectors (the lane runouts)."""
    return CLEAR_R + (LANE_CLEAR_R - CLEAR_R) * lane_weight(theta_deg)


S1_EYE_R = 199.0  # the S1 camera: a car's roof at the sunset lane's mouth, 3 m inside the ring's r 202 faces (layout.py R6 prints the radius from which the whole lake clears every stone along the lane - 194 in v2/v3 - and asserts S1_EYE_R is outside it)


def sightline_cone():
    """The tree-free view cone: from the S1 eye (SUNSET_LANE, S1_EYE_R) to the lake's two tangential
    tips (+-LAKE_A about the centre) - the triangle nothing taller than 0.5 m may stand in."""
    ex, ey = bearing_point(SUNSET_LANE, S1_EYE_R)
    lx, ly = bearing_point(LAKE_BEARING, LAKE_R)
    b = math.radians(LAKE_BEARING)
    tx, ty = math.cos(b), -math.sin(b)
    return (ex, ey), (lx + LAKE_A * tx, ly + LAKE_A * ty), (lx - LAKE_A * tx, ly - LAKE_A * ty)


def _in_triangle(p, a, b, c):
    def s(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

    d1, d2, d3 = s(p, a, b), s(p, b, c), s(p, c, a)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def tree_free(x, y) -> bool:
    """Hard version of the tree keep-out used by the runoff checks (feathering ignored): no tree
    inside CLEAR_R anywhere, nor inside LANE_CLEAR_R within +-LANE_HALF of a lane centre, nor inside
    the S1 sightline cone to the lake."""
    r = math.hypot(x - CX, y - CY)
    th = math.degrees(math.atan2(x - CX, y - CY)) % 360.0
    if r < CLEAR_R:
        return True
    if any(_angdiff(th, lc) <= LANE_HALF for lc in LANE_CENTRES) and r < LANE_CLEAR_R:
        return True
    return _in_triangle((x, y), *sightline_cone())


def lake_e(x, y):
    """Normalised elliptical radius about the lake centre (0 centre, 1 shoreline ellipse)."""
    lx, ly = bearing_point(LAKE_BEARING, LAKE_R)
    b = math.radians(LAKE_BEARING)
    rx, ry = math.sin(b), math.cos(b)  # radial unit (from C outward)
    tx, ty = math.cos(b), -math.sin(b)  # tangential unit
    dx, dy = x - lx, y - ly
    u = dx * tx + dy * ty
    v = dx * rx + dy * ry
    return np.sqrt((u / LAKE_A) ** 2 + (v / LAKE_B) ** 2)


def edge_distance(x, y):
    x0, y0 = POSITION[0], POSITION[1]
    x1, y1 = x0 + N * SQUARE, y0 + N * SQUARE
    return np.minimum(np.minimum(x - x0, x1 - x), np.minimum(y - y0, y1 - y))


def trail_polyline() -> list[tuple[float, float]]:
    return [bearing_point(b, r) for b, r in TRAIL_WAYPOINTS]


def trail_corner_deviations(corner_r: float = TRAIL_CORNER_R) -> list[tuple[int, float, float]]:
    """(waypoint index, deflection deg, distance the R arc leaves the corner = r (1/cos(phi/2) - 1))
    for every interior waypoint: 26.7 / 39.1 / 24.4 / 57.2 / 4.1 deg -> 1.11 / 2.45 / 0.92 / 5.55 /
    0.03 m. Two corners leave the polyline by more than 1 m and wp4 by 5.55 m, which is why every
    field that describes the road (paint, noise band, relief mask) is built from the rounded path."""
    pts = trail_polyline()
    out = []
    for k in range(1, len(pts) - 1):
        (ax, ay), (bx, by), (cx, cy) = pts[k - 1], pts[k], pts[k + 1]
        u1 = np.array([bx - ax, by - ay]) / math.hypot(bx - ax, by - ay)
        u2 = np.array([cx - bx, cy - by]) / math.hypot(cx - bx, cy - by)
        phi = math.acos(float(np.clip(np.dot(u1, u2), -1.0, 1.0)))
        out.append((k, math.degrees(phi), corner_r * (1.0 / math.cos(phi / 2.0) - 1.0)))
    return out


def rounded_trail_segments(corner_r: float = TRAIL_CORNER_R) -> list[tuple]:
    """The trail centreline as ("line", (x0, y0), (x1, y1)) and ("arc", centre, r, a0, da)
    pieces: every interior polyline corner replaced by a tangent circular arc of radius
    `corner_r` (the geometry a DecalRoad spline draws through the pinned node list). The arcs
    leave the polyline corners by 0.03-5.55 m (`trail_corner_deviations`)."""
    pts = trail_polyline()
    segs = []
    cur = pts[0]
    for k in range(1, len(pts) - 1):
        (ax, ay), (bx, by), (cx, cy) = pts[k - 1], pts[k], pts[k + 1]
        u1 = np.array([bx - ax, by - ay]) / math.hypot(bx - ax, by - ay)
        u2 = np.array([cx - bx, cy - by]) / math.hypot(cx - bx, cy - by)
        cosphi = float(np.clip(np.dot(u1, u2), -1.0, 1.0))
        phi = math.acos(cosphi)
        if phi < 1e-6:
            segs.append(("line", cur, (bx, by)))
            cur = (bx, by)
            continue
        tlen = corner_r * math.tan(phi / 2.0)  # tangent length from the corner
        p_in = np.array([bx, by]) - u1 * tlen
        p_out = np.array([bx, by]) + u2 * tlen
        nrm = np.array([-u1[1], u1[0]])  # arc centre: offset from p_in along the inward normal
        if (u1[0] * u2[1] - u1[1] * u2[0]) < 0:
            nrm = -nrm
        centre = p_in + nrm * corner_r
        a0 = math.atan2(p_in[1] - centre[1], p_in[0] - centre[0])
        a1 = math.atan2(p_out[1] - centre[1], p_out[0] - centre[0])
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        segs.append(("line", cur, (float(p_in[0]), float(p_in[1]))))
        segs.append(("arc", (float(centre[0]), float(centre[1])), corner_r, a0, da))
        cur = (float(p_out[0]), float(p_out[1]))
    segs.append(("line", cur, pts[-1]))
    return segs


def rounded_trail(corner_r: float = TRAIL_CORNER_R) -> list[tuple[float, float]]:
    """The corner-rounded trail centreline as a dense point list (arcs at ~1 m chords)."""
    out = []
    for seg in rounded_trail_segments(corner_r):
        if seg[0] == "line":
            _, p0, p1 = seg
            if not out:
                out.append(p0)
            out.append(p1)
        else:
            _, (cx_, cy_), rr, a0, da = seg
            n = max(2, int(abs(da) * rr / 1.0))
            for j in range(1, n + 1):
                a = a0 + da * j / n
                out.append((float(cx_ + rr * math.cos(a)), float(cy_ + rr * math.sin(a))))
    return out


def trail_nodes_xy(spacing_m: float = TRAIL_NODE_SPACING_M) -> list[dict]:
    """The PINNED trail DecalRoad node list (v3): the corner-rounded centreline sampled at a UNIFORM
    `spacing_m` along its length from the track outward, plus the far end. Uniform spacing is the
    point: a uniform-parameter Catmull-Rom (what `improvedSpline` draws) through unevenly spaced
    nodes cusps - a first cut that put both tangent points of the 2.9 m wp5 arc between 20-25 m
    straights read a 102 mm grade spike there. At 12.5 m the spline stays within 0.17 m of the
    rounded centreline and a linear road within 0.49 m (`trail_spline_check`); the arcs are R 40,
    which is why the spacing is denser than the track's 32 m. Every trail layer (surface, flows,
    gravel, ruts, verges, cracks, puddles, dust, litter) is authored on this list (the ruts and
    verges laterally offset); widths per layer are in tables.ROAD_MATERIALS. Each node carries its
    kind: end / arc (on an R 40 corner) / straight."""
    segs = rounded_trail_segments()
    pts = trail_samples(spacing_m)
    end = trail_polyline()[-1]
    if math.hypot(pts[-1][0] - end[0], pts[-1][1] - end[1]) > 0.5 * spacing_m:
        pts.append(end)
    else:
        pts[-1] = end
    arcs = [s for s in segs if s[0] == "arc"]
    nodes = []
    for k, (x, y) in enumerate(pts):
        on_arc = any(abs(math.hypot(x - c[0], y - c[1]) - rr) < 0.05 and abs(((math.atan2(y - c[1], x - c[0]) - a0 + math.pi) % (2 * math.pi) - math.pi)) <= abs(da) + 1e-6 and (((math.atan2(y - c[1], x - c[0]) - a0 + math.pi) % (2 * math.pi) - math.pi) * da >= -1e-6) for _, c, rr, a0, da in arcs)
        nodes.append({"index": k, "x": float(x), "y": float(y), "kind": "end" if k in (0, len(pts) - 1) else ("arc" if on_arc else "straight"), "width": TRAIL_WIDTH})
    return nodes


def trail_nodes(grid=None) -> list[dict]:
    """`trail_nodes_xy` with z from the bilinear terrain (the DecalRoad conforms to the terrain;
    z is carried for the record and for the R8 table) and the running metre along the road."""
    g = grid or get_grid()
    nodes = trail_nodes_xy()
    m = 0.0
    for k, nd in enumerate(nodes):
        if k:
            m += math.hypot(nd["x"] - nodes[k - 1]["x"], nd["y"] - nodes[k - 1]["y"])
        nd["m_along"] = round(m, 1)
        nd["z"] = round(float(z_at_arr(np.array([nd["x"]]), np.array([nd["y"]]), g)[0]), 3)
        nd["x"], nd["y"] = round(nd["x"], 3), round(nd["y"], 3)
    return nodes


def catmull_rom(P: np.ndarray, n: int = 40) -> np.ndarray:
    """Uniform Catmull-Rom through the points P (n samples per span, end points doubled)."""
    P = np.vstack([P[0], P, P[-1]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, n, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-2])
    return np.array(out)


def dist_to_polyline(P: np.ndarray, Q: np.ndarray) -> np.ndarray:
    """Min distance from every point of P (n, 2) to the polyline Q (m, 2)."""
    best = np.full(len(P), np.inf)
    for (ax, ay), (bx, by) in zip(Q[:-1], Q[1:]):
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        if L2 == 0:
            continue
        t = np.clip(((P[:, 0] - ax) * vx + (P[:, 1] - ay) * vy) / L2, 0, 1)
        best = np.minimum(best, np.hypot(P[:, 0] - (ax + vx * t), P[:, 1] - (ay + vy * t)))
    return best


def trail_spline_check(grid=None) -> dict:
    """How far the road a DecalRoad draws through the pinned nodes leaves the rounded centreline
    the terrain is built on, and the profile along that drawn road: (a) the node polyline itself
    (a linear road), (b) a uniform Catmull-Rom spline through the nodes (improvedSpline through
    dense nodes). Both must stay well inside the 3 m the relief corridor is measured over.

    v4 (critic C r3 defect 3), two instrument fixes to `spline_dev_max_m`, which read 0.16 m where
    the true figure is 0.167: (a) the reference centreline is sampled at SPLINE_REF_STEP_M = 0.1 m,
    not 1 m - the reference is a POLYLINE through those samples, so its chords cut the R 40 arcs by
    a c^2/(8 R) sagitta, 3.1 mm at 1 m and 0.03 mm at 0.1 m; (b) the deviation is the SYMMETRIC
    (Hausdorff) max of the two curves, not just the spline's distance to the reference - the spline
    is sampled at 12.5/40 = 0.31 m, which is too coarse in the one direction (0.1660 m) and the
    other direction catches 0.1673 m. Together they read 0.1673 m against the critic's independent
    0.05 m two-way instrument at 0.1672 m (0.1683 m on his own reconstruction of the centreline):
    the document states <= 0.17 m, which is true on every instrument. The grade and per-metre-change
    columns are unaffected: they are sampled along the spline at 1 m, the terrain's own cell size
    and the step the relief law is written in."""
    g = grid or get_grid()
    nodes = np.array([(nd["x"], nd["y"]) for nd in trail_nodes_xy()])
    path = np.array(trail_samples(SPLINE_REF_STEP_M) + [trail_polyline()[-1]])  # + the true end (the fixed steps stop short of it)
    poly = np.array(trail_polyline())
    cr = catmull_rom(nodes, 40)
    seg = np.hypot(np.diff(cr[:, 0]), np.diff(cr[:, 1]))
    cum = np.concatenate([[0], np.cumsum(seg)])
    m_ = np.arange(0, cum[-1], 1.0)
    px, py = np.interp(m_, cum, cr[:, 0]), np.interp(m_, cum, cr[:, 1])
    zs = z_at_arr(px, py, g)
    gr = np.diff(zs)
    return {
        "nodes": int(len(nodes)),
        "reference_step_m": SPLINE_REF_STEP_M,  # v4: the sampling of the reference centreline (was 1.0)
        "node_spacing_max_m": float(np.hypot(np.diff(nodes[:, 0]), np.diff(nodes[:, 1])).max()),
        "node_polyline_dev_max_m": float(dist_to_polyline(path, nodes).max()),  # the nodes lie ON the centreline, so the other direction is 0 and this is the Hausdorff distance
        # v4: the SYMMETRIC (Hausdorff) max of the two curves - max(sup over the spline of the
        # distance to the centreline, sup over the centreline of the distance to the spline).
        # The one-sided CR -> reference reads 0.1660 m because the spline is sampled at 12.5/40 =
        # 0.31 m; the other direction, with the reference at 0.1 m, catches the true 0.1673.
        "spline_dev_max_m": float(max(dist_to_polyline(cr, path).max(), dist_to_polyline(path, cr).max())),
        "spline_dev_cr_to_ref_m": float(dist_to_polyline(cr, path).max()),
        "spline_dev_ref_to_cr_m": float(dist_to_polyline(path, cr).max()),
        "spline_vs_polyline_dev_max_m": float(dist_to_polyline(cr, poly).max()),
        "spline_len_m": float(cum[-1]),
        "spline_grade_max_pct": float(np.nanmax(np.abs(gr)) * 100),
        "spline_dgrade_max_mm": float(np.nanmax(np.abs(np.diff(gr))) * 1000),
        "spline_cells_over_law": int((np.abs(np.diff(gr)) > RELIEF_LAW_M).sum()),
        "rounded_vs_polyline_dev_max_m": float(dist_to_polyline(path, poly).max()),
        # v4: the same quantity in closed form, so it does not depend on the sampling at all. The
        # max sits at an arc's APEX, where the nearest polyline feature switches from one segment
        # to the other - a kink, so a sampled path converges to it only linearly in the step
        # (1 m read 4.74, 0.1 m reads 4.87). At a corner of turn d the apex stands
        # R (sec(d/2) - 1) off the vertex and R (sec(d/2) - 1) cos(d/2) off the segments:
        # 4.873 m at wp4's 57.15 deg turn.
        "rounded_vs_polyline_apex_max_m": float(dist_to_polyline(np.array([[s[1][0] + s[2] * math.cos(s[3] + s[4] / 2), s[1][1] + s[2] * math.sin(s[3] + s[4] / 2)] for s in rounded_trail_segments() if s[0] == "arc"]), poly).max()),
    }


def trail_samples(step: float = 1.0) -> list[tuple[float, float]]:
    """The (corner-rounded) trail centreline sampled every `step` m from its start (m 0 at the track)."""
    pts = rounded_trail()
    samples = []
    carry = 0.0
    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        seg = math.hypot(bx - ax, by - ay)
        if seg == 0:
            continue
        d = carry
        while d < seg:
            samples.append((ax + (bx - ax) * d / seg, ay + (by - ay) * d / seg))
            d += step
        carry = d - seg
    return samples  # exact steps only (a trailing partial step would fake a grade change)


ROAD_FIELD_WINDOW = 40.0  # the trail's distance field is exact within this many metres of the centreline (> the 17 m noise band)


TRAIL_FIELD_FAR = 1.0e6  # what `trail_distance_field` reports outside ROAD_FIELD_WINDOW (never < any corridor)


def trail_distance_field(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Min distance (m) from every node to the TRAIL's CORNER-ROUNDED centreline ALONE (v3; v2
    measured the raw 7-point polyline, which the rounded road leaves by up to 4.87 m at wp4:
    R (sec(d/2) - 1) cos(d/2) at that corner's 57.15 deg turn, exactly 4.873 m; v3 quoted 4.74,
    which is what a 1 m-sampled path reads at a max that sits on a kink - see trail_spline_check).
    The centreline is sampled every 0.5 m, so the field is exact to < 0.01 m at 3 m off the road
    and < 0.03 m at 1 m; beyond ROAD_FIELD_WINDOW it reports TRAIL_FIELD_FAR.

    v4 (critic C r3 defect 2): this is split out of `road_distance_field` so `relief_report`'s
    trail-corridor rows can mask on the trail alone. The combined field is min(track, trail), and
    masking |d| <= 6 or 9 m on it with only an r > 252 filter also swept an annulus of the TRACK's
    outer verge (r 252-254 and r 252-257: pi (254^2 - 252^2) = 3,179 m^2 and pi (257^2 - 252^2) =
    7,995 m^2, doubled for the x and y second differences), which inflated the corridor's cell
    count by 30 % and 50 %. Paint, noise band and relief mask still use the combined field - both
    roads are painted and both are noise-free - only the REPORTING rows are trail-only."""
    X, Y = np.meshgrid(xs, ys)
    d = np.full(X.shape, TRAIL_FIELD_FAR, dtype=np.float32)
    W = ROAD_FIELD_WINDOW
    for px, py in trail_samples(0.5):
        i0 = int(max(0, (px - W - xs[0]) / SQUARE))
        i1 = int(min(len(xs), (px + W - xs[0]) / SQUARE + 1))
        j0 = int(max(0, (py - W - ys[0]) / SQUARE))
        j1 = int(min(len(ys), (py + W - ys[0]) / SQUARE + 1))
        if i1 <= i0 or j1 <= j0:
            continue
        sub = np.hypot(X[j0:j1, i0:i1] - px, Y[j0:j1, i0:i1] - py)
        d[j0:j1, i0:i1] = np.minimum(d[j0:j1, i0:i1], sub)
    return d


def road_distance_field(xs: np.ndarray, ys: np.ndarray, trail_d: np.ndarray | None = None) -> np.ndarray:
    """Min distance (m) from every node to the track circle OR the trail's corner-rounded
    centreline (`trail_distance_field`). This is the field the paint (+-6 m), the noise-free band
    (9 -> 17 m) and the relief mask are built from; the trail-corridor REPORT rows use the
    trail-only field."""
    X, Y = np.meshgrid(xs, ys)
    r, _ = polar(X, Y)
    track_d = np.abs(r - TRACK_R).astype(np.float32)
    if trail_d is None:
        trail_d = trail_distance_field(xs, ys)
    return np.minimum(track_d, trail_d)


# --- the wall with a rounded crest ---------------------------------------------------------------
def wall_profile(r, theta):
    """Height added by the basin wall at (r, theta): H(theta) t^1.45 rising from the onset to the
    crest, -12 % beyond it, with (v3) the first ONSET_FILLET_M metres a quartic in t that starts
    flat with zero curvature and meets t^1.45 in value and slope (bounded curvature, peak at
    0.41 of the fillet), and the fold replaced by a C1 cubic Hermite over
    [rim - CREST_HALF_W, rim + CREST_HALF_W] (position and slope continuous at both ends)."""
    onset = wall_onset(theta)
    rim = rim_radius(theta)
    H = wall_height(theta)
    span = np.maximum(rim - onset, 1.0)
    p = WALL_EXPONENT
    t0 = np.clip(ONSET_FILLET_M / span, 1e-6, 1.0)
    if ONSET_FILLET_KIND == "cubic":  # C1 at the onset: A t^2 + B t^3, curvature max at the onset (2 A)
        A = (3.0 - p) * t0 ** (p - 2.0)
        B = (p - 2.0) * t0 ** (p - 3.0)

        def fillet(tt):
            return A * tt * tt + B * tt * tt * tt

    elif ONSET_FILLET_KIND == "quartic":  # C2 at the onset (zero curvature): A t^3 + B t^4, curvature max 3.14 t0^(p-2) at 0.41 t0
        A = (4.0 - p) * t0 ** (p - 3.0)
        B = (p - 3.0) * t0 ** (p - 4.0)

        def fillet(tt):
            return A * tt**3 + B * tt**4

    elif ONSET_FILLET_KIND == "window":
        fillet = None
    else:
        raise ValueError(ONSET_FILLET_KIND)

    def rise(rr):
        tt = np.clip((rr - onset) / span, 0.0, 1.0)
        if ONSET_FILLET_KIND == "window":  # v2: H t^p S2((r - onset)/80): a 2 f' g' cross term (23.9 mm at 315 deg)
            return H * tt**p * smootherstep((rr - onset) / ONSET_FILLET_M)
        return H * np.where(tt < t0, fillet(tt), tt**p)

    t = np.clip((r - onset) / span, 0.0, 1.0)
    raw = rise(r) - BACKSLOPE * np.clip(r - rim, 0.0, None)
    w = CREST_HALF_W
    r0 = rim - w
    z0 = rise(r0)
    m0 = rise(r0 + 0.5) - rise(r0 - 0.5)  # dz/dr at r0 (central difference over 1 m)
    z1 = H - BACKSLOPE * w
    m1 = -BACKSLOPE
    s = np.clip((r - r0) / (2.0 * w), 0.0, 1.0)
    h00 = 2 * s**3 - 3 * s**2 + 1
    h10 = s**3 - 2 * s**2 + s
    h01 = -2 * s**3 + 3 * s**2
    h11 = s**3 - s**2
    herm = h00 * z0 + h10 * (2.0 * w) * m0 + h01 * z1 + h11 * (2.0 * w) * m1
    inside = (r > r0) & (r < rim + w)
    return np.where(inside, herm, raw), t


# --- the height law --------------------------------------------------------------------------
def height_field(xs: np.ndarray, ys: np.ndarray, road_d: np.ndarray, noises: dict[str, np.ndarray]) -> np.ndarray:
    X, Y = np.meshgrid(xs, ys)
    r, theta = polar(X, Y)
    z = np.full(X.shape, Z_FLOOR, dtype=np.float64)

    # 1. clearing rise 210 -> 350 (+2.4 m, smoothstep) blended by a Gaussian of the bearing into the
    #    lake sector's DESCENT to the 98.5 shelf (linear with 8.4 m fillets: max grade 1.14 %)
    u = np.clip((r - FLAT_R) / (CLEAR_R - FLAT_R), 0.0, 1.0)
    g = np.exp(-((ang_delta(theta, LAKE_BEARING) / RISE_LAKE_SIGMA) ** 2))
    z += (1.0 - g) * RISE_M * smoothstep(u) - g * (Z_FLOOR - LAKE_SHELF_Z) * trapezoid(u, LAKE_DESCENT_FILLET)

    # 2 + 3. basin wall with the rounded crest and the back-slope
    wall, t = wall_profile(r, theta)
    z += wall

    # 4. lake depression (flat bed at 86 inside e < 0.45)
    e = lake_e(X, Y)
    s_lake = smoothstep((1.0 - e) / 0.55)
    z = z - (z - LAKE_FLOOR) * s_lake

    # 5. noise: none inside the clearing (350, or 420 in the lane sectors), forest-floor 0.6 m,
    #    wall 2.5 m + ridged 1.5 m, none within 9 m of a road centreline (v3; ramping to full by
    #    17 m), 15 % on the lake bed
    zone = smoothstep((r - clear_radius(theta)) / 50.0)
    road_w = smoothstep((road_d - ROAD_NOISE_FREE_START) / (ROAD_NOISE_FREE_HALF_W - ROAD_NOISE_FREE_START))
    lake_w = 1.0 - 0.85 * smoothstep((1.05 - e) / 0.4)
    wall_w = np.clip(t, 0, 1)
    amp = 0.6 + 2.5 * wall_w
    ridged = (1.0 - np.abs(noises["ridge"])) * 1.5 * wall_w
    z += (noises["fbm"] * amp + ridged) * zone * road_w * lake_w

    # 6. exact floor inside FLAT_R and ceiling clip
    z = np.where(r <= FLAT_R, Z_FLOOR, z)
    return np.clip(z, 0.0, Z_CEIL)


def grade_field(z: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(z, SQUARE)
    return np.hypot(gx, gy)


def layer_field(xs, ys, z, road_d, noises) -> np.ndarray:
    X, Y = np.meshgrid(xs, ys)
    r, theta = polar(X, Y)
    e = lake_e(X, Y)
    s = grade_field(z)
    n3 = (noises["paint"] + 1.0) * 0.5  # [0,1]
    rim_z = Z_FLOOR + RISE_M + wall_height(theta) - 3.0  # the rounded crest sits ~3 m under H
    L = np.full(X.shape, LAYER_ID["forest_floor"], dtype=np.uint8)
    meadow = (r <= 470) & (s < 0.18) & (n3 > 0.6)
    meadow |= (e < 1.6) & (z < 110.0) & (s < 0.25)
    meadow |= r <= clear_radius(theta)
    L[meadow] = LAYER_ID["meadow"]
    alpine = (z >= 230.0) & (s <= 0.40) & (r <= rim_radius(theta))
    L[alpine] = LAYER_ID["alpine"]
    scree = ((s > 0.45) & (s <= 0.62)) | ((s > 0.33) & (n3 < 0.22) & (r > 500))
    L[scree] = LAYER_ID["scree"]
    rock = (s > 0.62) | ((z > rim_z - 30.0) & ((1.0 - np.abs(noises["ridge"])) > 0.7) & (s > 0.2))
    L[rock] = LAYER_ID["rock"]
    scorch_edge = 258.0 + (n3 - 0.5) * 40.0
    L[(r > 200.0) & (r <= scorch_edge)] = LAYER_ID["scorch"]
    L[road_d <= ROAD_PAINT_HALF_W] = LAYER_ID["trail"]
    ash = ((r > 175.0) & (r <= 200.0)) | ((r > 200.0) & (r <= 222.0) & (n3 > 0.55))
    L[ash] = LAYER_ID["ash"]
    L[r <= 175.0] = LAYER_ID["hearth"]
    shore = (e < 1.3) & (z < LAKE_LEVEL + 1.0)
    L[shore] = LAYER_ID["shore"]
    L[(e < 1.0) & (z < LAKE_LEVEL)] = LAYER_ID["lakebed"]
    return L


def build():
    xs = POSITION[0] + np.arange(N) * SQUARE
    ys = POSITION[1] + np.arange(N) * SQUARE
    noises = {
        "fbm": value_noise((N, N), 13, SEED + 1, octaves=5),  # base period ~157 m
        "ridge": value_noise((N, N), 34, SEED + 2, octaves=3),  # ~60 m
        "paint": value_noise((N, N), 23, SEED + 3, octaves=3),  # ~89 m
    }
    trail_d = trail_distance_field(xs, ys)
    road_d = road_distance_field(xs, ys, trail_d)
    z = height_field(xs, ys, road_d, noises)
    u = np.clip(np.rint(z / UNIT_M), 0, 65535).astype(np.uint16)
    zq = u.astype(np.float64) * UNIT_M
    layers = layer_field(xs, ys, zq, road_d, noises)
    return xs, ys, zq, u, layers, road_d, trail_d


_GRID = None


def source_hash() -> str:
    return hashlib.sha1(Path(__file__).read_bytes()).hexdigest()[:16]


def get_grid():
    """The built grid as a dict (xs, ys, zq, u, layers, road_d, trail_d), cached on disk keyed by
    this file's hash so layout.py / verify scripts do not rebuild the noise every run."""
    global _GRID
    if _GRID is not None:
        return _GRID
    cache = HERE / "_terrain_cache.npz"
    key = source_hash()
    if cache.exists():
        d = np.load(cache)
        if str(d["key"]) == key:
            u = d["u"]
            _GRID = {"xs": d["xs"], "ys": d["ys"], "u": u, "zq": u.astype(np.float64) * UNIT_M, "layers": d["layers"], "road_d": d["road_d"], "trail_d": d["trail_d"]}
            return _GRID
    xs, ys, zq, u, layers, road_d, trail_d = build()
    np.savez(cache, key=key, xs=xs, ys=ys, u=u, layers=layers, road_d=road_d.astype(np.float32), trail_d=trail_d.astype(np.float32))
    _GRID = {"xs": xs, "ys": ys, "u": u, "zq": zq, "layers": layers, "road_d": road_d, "trail_d": trail_d}
    return _GRID


def z_at_arr(x, y, grid=None):
    """Bilinear sample of the quantised heightmap (= the collision surface, report_B 3.4) for
    arrays of world x, y. NaN outside the usable block."""
    g = grid or get_grid()
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    fi = (x - g["xs"][0]) / SQUARE
    fj = (y - g["ys"][0]) / SQUARE
    i0 = np.floor(fi).astype(np.int64)
    j0 = np.floor(fj).astype(np.int64)
    ok = (i0 >= 0) & (j0 >= 0) & (i0 + 1 < N) & (j0 + 1 < N)
    i0c = np.clip(i0, 0, N - 2)
    j0c = np.clip(j0, 0, N - 2)
    a = fi - i0c
    b = fj - j0c
    zq = g["zq"]
    z = (1 - a) * (1 - b) * zq[j0c, i0c] + a * (1 - b) * zq[j0c, i0c + 1] + (1 - a) * b * zq[j0c + 1, i0c] + a * b * zq[j0c + 1, i0c + 1]
    return np.where(ok, z, np.nan)


def z_at(x: float, y: float) -> float:
    return float(z_at_arr(np.array([x]), np.array([y]))[0])


def layer_at(x: float, y: float) -> str:
    g = get_grid()
    i = int(round((x - g["xs"][0]) / SQUARE))
    j = int(round((y - g["ys"][0]) / SQUARE))
    return LAYERS[int(g["layers"][j, i])]


def road_profile(grid=None, ys_=None, zq_=None):
    """Sample the (corner-rounded) trail centreline every 1 m: z, grade, and the samples.
    Also accepts the v1 call form road_profile(xs, ys, zq) and then returns (zs, grade) only,
    so the critic's r1 scripts run unchanged."""
    old_form = ys_ is not None
    if old_form:
        grid = {"xs": grid, "ys": ys_, "zq": zq_}
    samples = trail_samples(1.0)
    xs = np.array([p[0] for p in samples])
    ys = np.array([p[1] for p in samples])
    zs = z_at_arr(xs, ys, grid)
    g = np.diff(zs)
    return (zs, g) if old_form else (zs, g, samples)


def radial_profile(bearing: float, r0: float, r1: float, grid=None, step: float = 1.0):
    rs = np.arange(r0, r1 + step, step)
    b = math.radians(bearing)
    return rs, z_at_arr(CX + rs * math.sin(b), CY + rs * math.cos(b), grid)


def relief_report(grid=None):
    """Second differences over 1 m cells (x and y) per drivable zone; the law is <= 20 mm."""
    g = grid or get_grid()
    zq, road_d, trail_d = g["zq"], g["road_d"], g["trail_d"]
    X, Y = np.meshgrid(g["xs"], g["ys"])
    R, TH = polar(X, Y)
    d2x = np.abs(zq[:, 2:] - 2 * zq[:, 1:-1] + zq[:, :-2])
    d2y = np.abs(zq[2:, :] - 2 * zq[1:-1, :] + zq[:-2, :])
    twist = np.abs(zq[:-1, :-1] - zq[:-1, 1:] - zq[1:, :-1] + zq[1:, 1:])
    lane_w = lane_weight(TH)
    in_lane = lane_w >= 0.999

    def masks(cond):
        return cond[:, 1:-1], cond[1:-1, :], cond[:-1, :-1]

    # v3: road_d IS the distance to the corner-rounded centreline (the road the pinned DecalRoad
    # nodes draw), so the corridor rows below are corridors about the road that is built.
    # v4 (critic C r3 defect 2): they mask on trail_d, the TRAIL-ONLY field - road_d is
    # min(track circle, trail), so with only an r > 252 filter the +-6 and +-9 m rows also swept
    # the track's outer verge (r 252-254 / 252-257) and overstated the corridor by 30 % / 50 %.
    # The track's own band is the row above; the maxima and violation counts are unchanged.
    zones = {
        "graded apron r 210-350 (all bearings)": masks((R > FLAT_R) & (R <= CLEAR_R)),
        "track band |r - 248| <= 4": masks(np.abs(R - TRACK_R) <= TRACK_HALF_W),
        "trail corridor |d| <= 3 m about the ROUNDED centreline, r > 252, TRAIL ONLY (the drivable width; whole length incl. the crest)": masks((trail_d <= 3.0) & (R > 252.0)),
        "trail corridor |d| <= 4 m (covers any spline within 1 m of the centreline)": masks((trail_d <= 4.0) & (R > 252.0)),
        "trail corridor |d| <= 6 m (the painted verges)": masks((trail_d <= 6.0) & (R > 252.0)),
        "trail corridor |d| <= 9 m (the noise-free margin; off-road)": masks((trail_d <= 9.0) & (R > 252.0)),
        "lane runouts r 350-420 within +-15 deg of a lane": masks((R > CLEAR_R) & (R <= LANE_CLEAR_R) & in_lane),
        "lane runouts r 350-420 incl. the +-22 deg feathers": masks((R > CLEAR_R) & (R <= LANE_CLEAR_R) & (lane_w > 0.0)),
        "sunset-lane sightline band r 210-350, +-15 deg": masks((R > FLAT_R) & (R <= CLEAR_R) & (np.abs(ang_delta(TH, SUNSET_LANE)) <= 15.0)),
        "everything r <= 350": masks(R <= CLEAR_R),
        "forest floor r 350-850 (not drivable by contract)": masks((R > CLEAR_R) & (R <= 850)),
        "crest band |r - rim| <= 60 (not drivable except the trail)": masks(np.abs(R - rim_radius(TH)) <= 60.0),
    }
    rows = []
    for name, (mx, my, mt) in zones.items():
        ax, ay = d2x[mx], d2y[my]
        allv = np.concatenate([ax, ay])
        rows.append({"zone": name, "cells": int(allv.size), "max_mm": float(allv.max() * 1000), "p99_mm": float(np.percentile(allv, 99) * 1000), "violations": int((allv > RELIEF_LAW_M).sum()), "twist_max_mm": float(twist[mt].max() * 1000)})
    return rows


def crest_table(grid=None):
    """Per bearing: the crest as built (with the wall noise) and the analytic law without noise
    (the crest transition itself). The analytic column is the one the relief law judges; the
    built column includes the 2.5 m + 1.5 m wall noise, which is off-road by contract."""
    rows = []
    for b in list(range(0, 360, 30)) + [150.0 + 2.5]:
        rim = float(rim_radius(b))
        H = float(wall_height(b))
        onset = float(wall_onset(b))
        rs, zs = radial_profile(b, rim - 90, rim + 60, grid)
        gr = np.diff(zs)
        d2 = np.abs(np.diff(gr))
        k = int(np.nanargmax(zs))
        ra = np.arange(onset - 5.0, rim + 60.0, 1.0)
        wa, _ = wall_profile(ra, np.full_like(ra, float(b)))
        d2a = np.abs(np.diff(wa, 2))
        ka = int(np.argmax(wa))
        rows.append({"bearing": float(b), "rim_r": rim, "H": H, "crest_r": float(rs[k]), "crest_z": float(zs[k]), "grade_in_pct": float(gr[max(0, k - 45)] * 100), "grade_out_pct": float(gr[min(len(gr) - 1, k + 45)] * 100), "built_max_grade_change_per_m_mm": float(np.nanmax(d2) * 1000), "analytic_crest_r": float(ra[ka]), "analytic_crest_z_rel": float(wa[ka]), "analytic_max_d2_mm": float(d2a.max() * 1000), "analytic_onset_max_d2_mm": float(d2a[: int(ONSET_FILLET_M) + 10].max() * 1000)})
    return rows


def analytic_sweep(step_deg: float = 1.0):
    """v3 (critic C r2 defect 3): the analytic wall law (no noise, no quantisation) swept every
    `step_deg` from the onset to 80 m past the crest, plus the trail's bearings; per bearing the
    max second difference over 1 m cells and where it sits. Returns (rows, worst, trail_worst)."""
    bearings = [float(b) for b in np.arange(0.0, 360.0, step_deg)] + [143.0, 147.0, 150.0, 151.0, 152.5, 155.0]
    rows = []
    for b in bearings:
        onset = float(wall_onset(b))
        rim = float(rim_radius(b))
        ra = np.arange(onset - 5.0, rim + 80.0, 1.0)
        wa, _ = wall_profile(ra, np.full_like(ra, b))
        d2 = np.abs(np.diff(wa, 2))
        k = int(np.argmax(d2))
        rows.append({"bearing": b, "max_mm": float(d2[k] * 1000), "r": float(ra[k + 1]), "onset": onset, "rim": rim, "H": float(wall_height(b)), "span": rim - onset, "where": "onset fillet" if ra[k + 1] < onset + ONSET_FILLET_M + 2 else ("crest" if abs(ra[k + 1] - rim) <= CREST_HALF_W + 1 else "rise")})
    worst = max(rows, key=lambda r_: r_["max_mm"])
    trail_worst = max((r_ for r_ in rows if r_["bearing"] in (143.0, 147.0, 150.0, 151.0, 152.5, 155.0)), key=lambda r_: r_["max_mm"])
    return rows, worst, trail_worst


LANE_RUNOUT_V0 = 30.0  # m/s: the arena's orbit speed, the speed a car leaves a lane at
GRASS_DECEL_MEASURED = 6.223  # m/s^2: B0's GRASS control line (b0_findings.md ground-model row)
FOREST_DECEL_MEASURED = 5.572  # m/s^2: B0's ERHP_FOREST_FLOOR line (beyond the tree line)


def lane_runouts(grid=None):
    """v3 (critic C r2 defect 4): the four lane runouts r 350-420 on their centre bearings: z at
    350 / 420, mean and max grade over 1 m steps, and the stopping distance from LANE_RUNOUT_V0
    on measured GRASS friction plus the grade (a runout is a brake, not a ramp)."""
    g = grid or get_grid()
    rows = []
    for lc in LANE_CENTRES:
        rs, zs = radial_profile(lc, CLEAR_R, LANE_CLEAR_R, g)
        gr = np.diff(zs)
        rs2, zs2 = radial_profile(lc, CLEAR_R, CLEAR_R + 300.0, g)  # the brake integrated past the tree line too (forest floor 5.572 beyond it)
        gr2 = np.diff(zs2)
        v2 = LANE_RUNOUT_V0**2
        stop = float("inf")
        v_at_trees = None
        for k, gk in enumerate(gr2):
            mu = GRASS_DECEL_MEASURED if rs2[k] < LANE_CLEAR_R else FOREST_DECEL_MEASURED
            v2 -= 2.0 * (mu + 9.81 * gk)
            if rs2[k + 1] >= LANE_CLEAR_R and v_at_trees is None:
                v_at_trees = math.sqrt(max(v2, 0.0))
            if v2 <= 0:
                stop = k + 1
                break
        first_tree_r = next((float(rr) for rr in np.arange(CLEAR_R, 1100.0, 1.0) if not tree_free(*bearing_point(lc, float(rr)))), float("inf"))
        rows.append({"lane": float(lc), "z_350": float(zs[0]), "z_420": float(zs[-1]), "rise_m": float(zs[-1] - zs[0]), "grade_mean_pct": float((zs[-1] - zs[0]) / (LANE_CLEAR_R - CLEAR_R) * 100), "grade_max_pct": float(np.abs(gr).max() * 100), "grade_at_420_pct": float(gr[-1] * 100), "stop_m_from_30": stop, "tree_line_m": float(LANE_CLEAR_R - CLEAR_R), "first_tree_r": first_tree_r, "stops_before_trees": bool(CLEAR_R + stop <= first_tree_r), "speed_at_tree_line_kmh": float(v_at_trees * 3.6) if v_at_trees else 0.0})
    return rows


def los_visible_fraction(eye, water_xy, grid=None, step=4.0, clearance=0.0):
    """Fraction of water surface points visible from `eye` (x, y, z): the segment to each point
    (at LAKE_LEVEL) stays above the bilinear terrain at every `step` m."""
    ex, ey, ez = eye
    wx, wy = water_xy[:, 0], water_xy[:, 1]
    L = np.hypot(wx - ex, wy - ey)
    K = int(np.ceil(L.max() / step))
    vis = np.ones(len(wx), dtype=bool)
    near = np.full(len(wx), np.inf)
    for k in range(1, K):
        t = k / K
        x = ex + (wx - ex) * t
        y = ey + (wy - ey) * t
        z = ez + (LAKE_LEVEL - ez) * t
        tz = z_at_arr(x, y, grid)
        blocked = (z - clearance) < np.nan_to_num(tz, nan=-1e9)
        # a segment sample beyond the point itself does not count (t < 1 always here)
        vis &= ~blocked
    frac = float(vis.mean()) if len(vis) else 0.0
    nearest = float(L[vis].min()) if vis.any() else float("nan")
    return frac, nearest


def water_points(grid=None, spacing=8):
    g = grid or get_grid()
    X, Y = np.meshgrid(g["xs"], g["ys"])
    e = lake_e(X, Y)
    m = (g["zq"] < LAKE_LEVEL) & (e < 1.3)
    sel = np.zeros_like(m)
    sel[::spacing, ::spacing] = True
    m &= sel
    return np.column_stack([X[m], Y[m]])


def lake_visibility(grid=None):
    """The v2 instrument for 'the lake is seen from the apron': true ray tests from driver's eyes
    along the sunset lane (r 113 -> 202, every 3 m, three bearings) and from the S1 camera."""
    g = grid or get_grid()
    W = water_points(g)
    eyes = []
    for r in np.arange(113.0, 203.0, 3.0):
        for db in (-5.0, 0.0, 5.0):
            x, y = bearing_point(SUNSET_LANE + db, r)
            eyes.append((f"driver r {r:.0f} lane{db:+.0f}", (x, y, z_at(x, y) + 1.2), r))
    x, y = bearing_point(SUNSET_LANE, S1_EYE_R)
    cam = (f"S1 camera (lane mouth r {S1_EYE_R:.0f}, roof +2.4)", (x, y, z_at(x, y) + 2.4), S1_EYE_R)
    x, y = bearing_point(SUNSET_LANE, 113.0)
    toe = ("driver at the glacis toe r 113", (x, y, z_at(x, y) + 1.2), 113.0)
    x, y = bearing_point(SUNSET_LANE, 91.4)
    crest = ("driver on the pan crest r 91.4 (z 105.5 + 1.2)", (x, y, 106.7), 91.4)
    rows = []
    fr = []
    for name, eye, r in eyes:
        f, near = los_visible_fraction(eye, W, g)
        fr.append(f)
    sees = [f >= 0.25 for f in fr]
    summary = {"water_points": int(len(W)), "eye_positions": len(eyes), "eyes_seeing_ge_25pct": float(np.mean(sees)), "median_visible_fraction": float(np.median(fr)), "min_visible_fraction": float(np.min(fr))}
    for name, eye, r in (cam, toe, crest) + tuple(e for e in eyes if abs(e[2] - 150.0) < 0.1 and "lane+0" in e[0]) + tuple(e for e in eyes if abs(e[2] - 200.0) < 0.1 and "lane+0" in e[0]):
        f, near = los_visible_fraction(eye, W, g)
        rows.append({"eye": name, "x": round(eye[0], 1), "y": round(eye[1], 1), "z": round(eye[2], 2), "visible_fraction": f, "nearest_visible_m": near})
    return summary, rows


def spawn_points(grid=None):
    """Every spawn derived from the model (facing = compass bearing of the +Y axis of the sphere)."""
    g = grid or get_grid()
    rows = []
    # trailhead: on the trail centreline 8 m from the track's outer edge, facing the pan
    x, y = trail_samples(1.0)[8]
    rows.append({"name": "_spawn_trailhead", "x": round(x, 2), "y": round(y, 2), "z": round(z_at(x, y), 3), "facing_deg": (TRAIL_BEARING + 180.0) % 360.0, "layer": layer_at(x, y), "note": "trail m 8 (r ~256), facing the pan"})
    # lakeshore: along LAKE_BEARING - 18 deg, the first point (from C outward) on the shore layer, pulled back 8 m
    b = LAKE_BEARING - 18.0
    r = 300.0
    while r < 700 and z_at(*bearing_point(b, r)) > LAKE_LEVEL + 0.8:
        r += 1.0
    r -= 3.0
    x, y = bearing_point(b, r)
    rows.append({"name": "_spawn_lakeshore", "x": round(x, 2), "y": round(y, 2), "z": round(z_at(x, y), 3), "facing_deg": b, "layer": layer_at(x, y), "note": f"bearing {b:.0f}, r {r:.0f}, on the shore band 3 m back from where the ground is 0.8 m over the water, facing the water"})
    # firewood gap: the trail's crest (its highest metre), facing back down toward the pan
    zs, gr, samples = road_profile(g)
    k = int(np.nanargmax(zs))
    x, y = samples[k]
    rows.append({"name": "_spawn_firewood_gap", "x": round(x, 2), "y": round(y, 2), "z": round(float(zs[k]), 3), "facing_deg": (TRAIL_BEARING + 180.0) % 360.0, "layer": layer_at(x, y), "note": f"trail m {k} = the saddle crest (z {zs[k]:.1f}), facing the pan; inside the basin by construction"})
    return rows


def write_preview(z, layers, path: Path):
    from PIL import Image

    step = N // 1024
    zs = z[::step, ::step]
    ls = layers[::step, ::step]
    gy, gx = np.gradient(zs, SQUARE * step)
    az, el = math.radians(315.0), math.radians(35.0)
    nx, ny, nz = -gx, -gy, np.ones_like(gx)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    lx, ly, lz = math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)
    shade = np.clip((nx * lx + ny * ly + nz * lz) / norm, 0.0, 1.0) * 0.75 + 0.25
    palette = np.array(
        [[58, 52, 50], [96, 74, 62], [70, 60, 48], [150, 118, 82], [116, 150, 70], [72, 92, 46], [138, 134, 126], [112, 110, 108], [196, 178, 140], [60, 96, 120], [150, 160, 118]],
        dtype=np.float32,
    )
    rgb = palette[ls] * shade[..., None]
    rgb[ls == LAYER_ID["lakebed"]] = np.array([48, 84, 112]) * 0.9
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)[::-1])  # north up
    img.save(path)


def main():
    t0 = time.time()
    g = get_grid()
    xs, ys, zq, u, layers, road_d = g["xs"], g["ys"], g["zq"], g["u"], g["layers"], g["road_d"]
    X, Y = np.meshgrid(xs, ys)
    r, theta = polar(X, Y)
    total = N * N
    out = {"source_hash": source_hash(), "constants": {"N": N, "SQUARE": SQUARE, "POSITION": POSITION, "MAX_HEIGHT": MAX_HEIGHT, "FLAT_R": FLAT_R, "CLEAR_R": CLEAR_R, "LANE_CLEAR_R": LANE_CLEAR_R, "LAKE_BEARING": LAKE_BEARING, "SUNSET_LANE": SUNSET_LANE, "LAKE_LEVEL": LAKE_LEVEL, "LAKE_SHELF_Z": LAKE_SHELF_Z, "LAKE_FLOOR": LAKE_FLOOR, "CREST_HALF_W": CREST_HALF_W, "BACKSLOPE": BACKSLOPE, "TRACK_R": TRACK_R}}
    print(f"grid N={N} square={SQUARE} position={POSITION} maxHeight={MAX_HEIGHT} unit_mm={UNIT_M * 1000:.7f} ceiling_z={Z_CEIL:.4f}  (source hash {source_hash()}; cache keyed by it)")
    disc = r <= FLAT_R
    uniq = np.unique(u[disc])
    print(f"flat disc r<={FLAT_R}: {int(disc.sum())} nodes, unique u = {uniq.tolist()} (expect [{U_FLOOR}])")
    out["flat_disc_nodes"] = int(disc.sum())
    out["flat_disc_unique_u"] = uniq.tolist()
    print(f"u range {int(u.min())}..{int(u.max())}  z range {zq.min():.3f}..{zq.max():.3f} (ceiling {Z_CEIL:.3f}); nodes at u 65535: {int((u == 65535).sum())}")
    out["z_min"], out["z_max"], out["u_max"] = float(zq.min()), float(zq.max()), int(u.max())
    print("\n| id | layer | nodes | % of block | ha |")
    print("|---|---|---|---|---|")
    cov = {}
    for i, name in enumerate(LAYERS):
        n = int((layers == i).sum())
        cov[name] = n / total * 100.0
        print(f"| {i} | {name} | {n:,} | {n / total * 100:.2f} | {n * SQUARE * SQUARE / 10000:.1f} |")
    out["coverage_pct"] = cov
    # crest
    print("\n| bearing | rim r | wall H | crest r (built) | crest z (built) | grade 45 m inside | grade 45 m outside | built max grade change per m (mm, incl. wall noise) | analytic crest z rel | analytic max second difference (mm) | analytic onset max (mm) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    ct = crest_table(g)
    for c in ct:
        print(f"| {c['bearing']:.1f} | {c['rim_r']:.0f} | {c['H']:.1f} | {c['crest_r']:.0f} | {c['crest_z']:.1f} | {c['grade_in_pct']:.1f} % | {c['grade_out_pct']:.1f} % | {c['built_max_grade_change_per_m_mm']:.1f} | {c['analytic_crest_z_rel']:.1f} | {c['analytic_max_d2_mm']:.2f} | {c['analytic_onset_max_d2_mm']:.2f} |")
    print(f"crest law (analytic, no noise): max second difference over all listed bearings = {max(c['analytic_max_d2_mm'] for c in ct):.2f} mm (law 20 mm); at the onset {max(c['analytic_onset_max_d2_mm'] for c in ct):.2f} mm")
    out["crest"] = ct
    sw, worst, tw = analytic_sweep(1.0)
    top5 = sorted(sw, key=lambda r_: -r_["max_mm"])[:5]
    print(f"analytic law, FINE sweep every 1 deg (v3): global max {worst['max_mm']:.1f} mm at {worst['bearing']:.0f} deg, r {worst['r']:.0f} ({worst['where']}; onset {worst['onset']:.0f}, rim {worst['rim']:.0f}, H {worst['H']:.1f} over {worst['span']:.0f} m); bearings over 20 mm: {sum(1 for r_ in sw if r_['max_mm'] > 20.0)} of {len(sw)}; worst five: " + "; ".join(f"{r_['bearing']:.0f}: {r_['max_mm']:.1f} mm at r {r_['r']:.0f} ({r_['where']})" for r_ in top5))
    nearest_lane = min(LANE_CENTRES, key=lambda lc: abs(ang_delta(worst["bearing"], lc)))
    print(f"   where the global max sits: {abs(float(ang_delta(worst['bearing'], nearest_lane))):.0f} deg from the {nearest_lane:.0f} lane, r {worst['r']:.0f} > the runout end {LANE_CLEAR_R:.0f} -> {'off every drivable line (forest)' if worst['r'] > LANE_CLEAR_R and (abs(float(ang_delta(worst['bearing'], TRAIL_BEARING))) > 8.0) else 'ON A DRIVABLE LINE'}; on the trail's bearings (143-155) the max is {tw['max_mm']:.1f} mm at {tw['bearing']:.1f} deg, r {tw['r']:.0f}")
    out["analytic_sweep"] = {"step_deg": 1.0, "global_max_mm": worst["max_mm"], "at_bearing": worst["bearing"], "at_r": worst["r"], "where": worst["where"], "bearings_over_20mm": sum(1 for r_ in sw if r_["max_mm"] > 20.0), "trail_bearings_max_mm": tw["max_mm"], "worst5": top5}
    print("\n| lane | z at r 350 | z at r 420 | rise | mean grade | max grade (1 m) | grade at 420 | first tree on the lane's centre (tree_free) | stops from 30 m/s in (grass 6.22 m/s^2 + grade; forest floor 5.57 past the trees) | speed at r 420 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    lr = lane_runouts(g)
    for row in lr:
        print(f"| {row['lane']:.0f} | {row['z_350']:.2f} | {row['z_420']:.2f} | {row['rise_m']:+.2f} | {row['grade_mean_pct']:.1f} % | {row['grade_max_pct']:.1f} % | {row['grade_at_420_pct']:.1f} % | r {row['first_tree_r']:.0f} | {row['stop_m_from_30']:.0f} m ({'before' if row['stops_before_trees'] else 'PAST'} the first tree) | {row['speed_at_tree_line_kmh']:.0f} km/h |")
    out["lane_runouts"] = lr
    # grades
    gfield = grade_field(zq)
    for lo, hi in ((210, 350), (350, 500), (500, 934)):
        band = (r > lo) & (r <= hi)
        print(f"grade r {lo}-{hi}: p50 {np.percentile(gfield[band], 50) * 100:.1f} %  p95 {np.percentile(gfield[band], 95) * 100:.1f} %  max {gfield[band].max() * 100:.1f} %")
    track = np.abs(r - TRACK_R) <= TRACK_HALF_W
    print(f"track r {TRACK_R}+-{TRACK_HALF_W}: grade max {gfield[track].max() * 100:.2f} %, z {zq[track].min():.3f}..{zq[track].max():.3f}")
    out["track_z"] = [float(zq[track].min()), float(zq[track].max())]
    out["track_grade_max_pct"] = float(gfield[track].max() * 100)
    zs, gg, samples = road_profile(g)
    k = int(np.nanargmax(np.abs(gg)))
    kk = int(np.nanargmax(np.abs(np.diff(gg))))
    print(f"trail profile: {len(zs) - 1} m long, z {zs[0]:.2f} -> {np.nanmax(zs):.2f} (crest at m {int(np.nanargmax(zs))}), grade max {np.abs(gg).max() * 100:.2f} % at m {k}, p95 {np.percentile(np.abs(gg), 95) * 100:.2f} %, |d grade| per m max {np.abs(np.diff(gg)).max() * 1000:.1f} mm at m {kk}")
    kc = int(np.nanargmax(zs))
    print(f"trail grades m {kc - 45}..{kc + 45} every 15 m: {[round(float(gg[j]) * 100, 2) for j in range(kc - 45, kc + 46, 15)]} %")
    out["trail_len_m"] = int(len(zs) - 1)
    out["trail_z_top"] = float(np.nanmax(zs))
    out["trail_crest_m"] = kc
    out["trail_grade_max_pct"] = float(np.abs(gg).max() * 100)
    out["trail_grade_change_max_mm"] = float(np.abs(np.diff(gg)).max() * 1000)
    # v3: the road the DecalRoad draws vs the centreline the terrain is built on
    devs = trail_corner_deviations()
    print("trail corners: " + ", ".join(f"wp{k}: {d:.1f} deg -> the R 40 arc leaves the corner by {dev:.2f} m" for k, d, dev in devs))
    sc = trail_spline_check(g)
    nodes = trail_nodes(g)
    kinds = {}
    for nd in nodes:
        kinds[nd["kind"]] = kinds.get(nd["kind"], 0) + 1
    print(f"trail DecalRoad nodes (pinned, v3): {sc['nodes']} nodes {kinds}, max spacing {sc['node_spacing_max_m']:.1f} m, width {TRAIL_WIDTH:.0f}; the node polyline leaves the rounded centreline by <= {sc['node_polyline_dev_max_m']:.2f} m; a uniform Catmull-Rom spline through the nodes leaves it by <= {sc['spline_dev_max_m']:.2f} m (v4: Hausdorff, both directions, against a {SPLINE_REF_STEP_M} m reference; {sc['spline_dev_max_m']:.4f} m) (and the raw 7-point polyline by {sc['spline_vs_polyline_dev_max_m']:.2f} m; the rounded centreline itself is {sc['rounded_vs_polyline_apex_max_m']:.2f} m off the polyline at wp4, exactly {sc['rounded_vs_polyline_apex_max_m']:.3f} m at the arc's apex); profile along that spline: {sc['spline_len_m']:.0f} m, grade max {sc['spline_grade_max_pct']:.2f} %, |d grade| per m max {sc['spline_dgrade_max_mm']:.1f} mm, cells over 20 mm: {sc['spline_cells_over_law']}")
    print("   first nodes: " + "; ".join(f"{nd['index']} ({nd['x']:.1f}, {nd['y']:.1f}, {nd['z']:.2f}) {nd['kind']} m {nd['m_along']}" for nd in nodes[:4]) + " ...")
    out["trail_nodes"] = nodes
    out["trail_spline_check"] = sc
    out["trail_corner_deviations"] = [{"wp": k, "deflection_deg": d, "arc_off_corner_m": dev} for k, d, dev in devs]
    # relief law by zone
    print("\n| zone | cells | max second difference (mm) | p99 (mm) | cells > 20 mm | bilinear twist max (mm) |")
    print("|---|---|---|---|---|---|")
    rel = relief_report(g)
    for row in rel:
        print(f"| {row['zone']} | {row['cells']:,} | {row['max_mm']:.1f} | {row['p99_mm']:.1f} | {row['violations']} | {row['twist_max_mm']:.1f} |")
    out["relief"] = rel
    # lake
    e = lake_e(X, Y)
    wet = (e < 1.3) & (zq < LAKE_LEVEL)
    print(f"\nlake: centre {bearing_point(LAKE_BEARING, LAKE_R)}, WaterPlane {LAKE_LEVEL}, wet nodes {int(wet.sum()):,} = {wet.sum() * 1e-4:.1f} ha, depth max {LAKE_LEVEL - zq[wet].min():.2f} m, waterline e max {e[wet].max():.3f}")
    shore_band = (e > 0.9) & (e < 1.1)
    print(f"shore bank grade (e 0.9-1.1): p50 {np.percentile(gfield[shore_band], 50) * 100:.1f} % max {gfield[shore_band].max() * 100:.1f} %")
    outside = e > 1.25
    print(f"WaterPlane safety: min terrain z where e > 1.25 = {zq[outside].min():.3f}; where e > 1.0 = {zq[e > 1.0].min():.3f} (plane at {LAKE_LEVEL}); on the outermost usable ring (edge distance <= 2 m) {zq[edge_distance(X, Y) <= 2].min():.2f}")
    out["min_z_outside_lake_e1_25"] = float(zq[outside].min())
    out["min_z_outside_lake_e1_0"] = float(zq[e > 1.0].min())
    out["lake_ha"] = float(wet.sum() * 1e-4)
    out["lake_depth_max"] = float(LAKE_LEVEL - zq[wet].min())
    out["lake_centre"] = bearing_point(LAKE_BEARING, LAKE_R)
    out["waterline_e"] = float(e[wet].max())
    # lake visibility (true rays)
    summ, rows = lake_visibility(g)
    print(f"\nlake visibility, true rays to {summ['water_points']} water points (8 m grid): {summ['eyes_seeing_ge_25pct'] * 100:.0f} % of {summ['eye_positions']} driver's-eye positions along the {SUNSET_LANE:.0f} lane (r 113-202, bearings {SUNSET_LANE - 5:.0f}/{SUNSET_LANE:.0f}/{SUNSET_LANE + 5:.0f}) see >= 25 % of the water; median visible fraction {summ['median_visible_fraction'] * 100:.0f} %, min {summ['min_visible_fraction'] * 100:.0f} %")
    print("\n| eye | x | y | z | visible water | nearest visible water (m) |")
    print("|---|---|---|---|---|---|")
    for row in rows:
        print(f"| {row['eye']} | {row['x']} | {row['y']} | {row['z']} | {row['visible_fraction'] * 100:.1f} % | {row['nearest_visible_m']:.0f} |")
    out["lake_visibility"] = {"summary": summ, "eyes": rows}
    # spawns
    sp = spawn_points(g)
    print("\n| spawn | x | y | z | facing | layer | note |")
    print("|---|---|---|---|---|---|---|")
    for s in sp:
        print(f"| {s['name']} | {s['x']} | {s['y']} | {s['z']} | {s['facing_deg']:.0f} | {s['layer']} | {s['note']} |")
    out["spawns"] = sp
    forest_mask = np.isin(layers, [LAYER_ID["forest_floor"], LAYER_ID["meadow"]]) & (r > CLEAR_R) & (gfield < 0.55)
    print(f"\nplantable area (forest_floor/meadow, r > {CLEAR_R:.0f}, grade < 55 %): {forest_mask.sum() * 1e-4:.0f} ha")
    out["plantable_ha"] = float(forest_mask.sum() * 1e-4)
    write_preview(zq, layers, HERE / "terrain_preview.png")
    (HERE / "terrain_summary.json").write_text(json.dumps(out, indent=2, default=float), encoding="utf-8", newline="\n")
    print(f"\nwrote terrain_preview.png + terrain_summary.json in {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
