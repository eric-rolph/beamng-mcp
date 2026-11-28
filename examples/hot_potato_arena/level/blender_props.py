"""Build the B4 prop DAEs in headless Blender: the logs, the bench deck, tripod and dressing.

    blender.exe --factory-startup --background --python blender_props.py -- \\
        --out <level root> --cache <cc0 cache> --ground <ground.json> \\
        --manifest <out.json> [--only bench_log]

Reuses B3's proven Collada machinery rather than a second copy of it: ``blender_forest``'s
pure-python ``Mesh``, its quantised exporter (AGENTS.md L710 -- Blender's Collada writer is
not deterministic, quantisation is the fix), its node-tree assertion, its decimation helpers
and ``forest_spec.BB_PROPERTY`` (``BB::DIM=128`` + ``EQUATOR_STEPS=32`` +
``INCLUDE_POLES=0``, the recipe B3 r5 measured against stock's own atlases).

No terrain module is imported here.  Every ground height the geometry needs was sampled by
``build_prop_shapes.py`` with ``terrain_io.surface_z`` -- the bilinear read of the shipped
quantised grid, which IS the collision surface -- and arrives in ``--ground``.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from examples.hot_potato_arena.level import blender_forest as bf  # noqa: E402
from examples.hot_potato_arena.level import forest_spec as fs  # noqa: E402
from examples.hot_potato_arena.level import props_spec as ps  # noqa: E402

Mesh = bf.Mesh


# ------------------------------------------------------------------------ deterministic noise
class Lattice:
    """A seeded value-noise lattice with bilinear reads -- reproducible across processes."""

    def __init__(self, seed: int, nu: int, nv: int) -> None:
        rng = random.Random(seed)  # noqa: S311 - deterministic geometry jitter, not crypto
        self.nu, self.nv = nu, nv
        self.cells = [[rng.random() for _ in range(nv)] for _ in range(nu)]

    def at(self, u: float, v: float) -> float:
        fu, fv = (u % 1.0) * self.nu, (v % 1.0) * self.nv
        i0, j0 = int(fu) % self.nu, int(fv) % self.nv
        i1, j1 = (i0 + 1) % self.nu, (j0 + 1) % self.nv
        tu, tv = fu - int(fu), fv - int(fv)
        tu = tu * tu * (3.0 - 2.0 * tu)
        tv = tv * tv * (3.0 - 2.0 * tv)
        a = self.cells[i0][j0] * (1 - tv) + self.cells[i0][j1] * tv
        b = self.cells[i1][j0] * (1 - tv) + self.cells[i1][j1] * tv
        return a * (1 - tu) + b * tu


def bark_field(seed: int) -> Any:
    coarse, fine = Lattice(seed, 9, 24), Lattice(seed ^ 0x9E37, 23, 61)

    def field(u: float, v: float) -> float:
        return (coarse.at(u, v) - 0.5) * 1.4 + (fine.at(u, v) - 0.5) * 0.6

    return field


# ------------------------------------------------------------------------ mesh primitives
def add_loft(
    mesh: Mesh,
    rings: list[list[tuple[float, float, float]]],
    slot,
    uv_scale=(1.0, 1.0),
    u_map: list[float] | None = None,
) -> list[list[int]]:
    """Stitch equal-length closed rings into a tube.

    ``slot`` may be one id, one id per band, or a callable ``(band, column) -> id`` -- the
    last form is what lets the bench log wear hewn timber on its flat deck and BARK on the
    round belly and flanks from the same loft, instead of one material over the whole body.

    ``u_map`` (r3) gives the u coordinate of each column, ``n + 1`` values with the wrap
    at the end.  Columns stopped being uniform in arc length when the bench log's deck grew
    its two shoulders (three narrow columns where the flat band has eight wide ones), and
    ``k / n`` would stretch the bark on the arris 2x against the bark 0.3 m away.
    """

    su, sv = uv_scale
    grid = [[mesh.add_vert(*p) for p in ring] for ring in rings]
    n = len(rings[0])
    bands = max(1, len(rings) - 1)
    us = [su * k / n for k in range(n + 1)] if u_map is None else [su * u for u in u_map]
    for s in range(len(rings) - 1):
        row = slot[s] if isinstance(slot, (list, tuple)) else slot
        v0, v1 = sv * s / bands, sv * (s + 1) / bands
        for k in range(n):
            m = (k + 1) % n
            band = row(s, k) if callable(row) else row
            u0, u1 = us[k], us[k + 1]
            mesh.add_tri(
                grid[s][k], grid[s][m], grid[s + 1][m], [(u0, v0), (u1, v0), (u1, v1)], band
            )
            mesh.add_tri(
                grid[s][k], grid[s + 1][m], grid[s + 1][k], [(u0, v0), (u1, v1), (u0, v1)], band
            )
    return grid


def cap_ring(
    mesh: Mesh, ring: list[int], centre: tuple[float, float, float], slot: int, flip: bool
):
    """A fan from ``centre`` over ``ring``.  THE WINDING RULE, because it was wrong for
    three revisions on the one shape that matters:

    :func:`add_loft` walks ring ``s`` in the direction ``k -> k+1`` inside its first triangle
    and the LAST ring in the direction ``k+1 -> k``.  A cap must walk its shared edges the
    OTHER way round or the two faces disagree about which side is out -- closed by every
    edge count, and still not a solid.  So the cap on ``grid[0]`` takes ``flip=True`` and
    the cap on ``grid[-1]`` takes ``flip=False``, whichever way the rings themselves were
    laid down (:func:`add_prism` has always done this; the bench log, whose section is
    reversed after it is built, had the two swapped -- 60 misoriented edges on its
    collider, all of them on the two end rings, ``b4/r4/manifold_r4.json``).
    """

    hub = mesh.add_vert(*centre)
    n = len(ring)
    for k in range(n):
        m = (k + 1) % n
        a = 2.0 * math.pi * k / n
        b = 2.0 * math.pi * (k + 1) / n
        uv_a = (0.5 + 0.5 * math.cos(a), 0.5 + 0.5 * math.sin(a))
        uv_b = (0.5 + 0.5 * math.cos(b), 0.5 + 0.5 * math.sin(b))
        if flip:
            mesh.add_tri(hub, ring[m], ring[k], [(0.5, 0.5), uv_b, uv_a], slot)
        else:
            mesh.add_tri(hub, ring[k], ring[m], [(0.5, 0.5), uv_a, uv_b], slot)


def add_box(mesh: Mesh, lo, hi, slot: int, uv_scale: float = 1.0) -> None:
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    corners = [
        (x0, y0, z0),
        (x1, y0, z0),
        (x1, y1, z0),
        (x0, y1, z0),
        (x0, y0, z1),
        (x1, y0, z1),
        (x1, y1, z1),
        (x0, y1, z1),
    ]
    index = [mesh.add_vert(*c) for c in corners]
    faces = (
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    )
    s = uv_scale
    uv = [(0.0, 0.0), (s, 0.0), (s, s), (0.0, s)]
    for face in faces:
        mesh.add_tri(index[face[0]], index[face[1]], index[face[2]], [uv[0], uv[1], uv[2]], slot)
        mesh.add_tri(index[face[0]], index[face[2]], index[face[3]], [uv[0], uv[2], uv[3]], slot)


def add_prism(
    mesh: Mesh, path: list[tuple[float, float, float]], radius, sides: int, slot: int, uv=(4.0, 1.0)
) -> None:
    """A closed tube along ``path`` with a per-station radius (float or list)."""

    radii = [radius] * len(path) if isinstance(radius, (int, float)) else list(radius)
    rings = []
    for i, centre in enumerate(path):
        if i == 0:
            axis = _sub(path[1], path[0])
        elif i == len(path) - 1:
            axis = _sub(path[-1], path[-2])
        else:
            axis = _sub(path[i + 1], path[i - 1])
        right, up = _frame(axis)
        ring = []
        for k in range(sides):
            a = 2.0 * math.pi * k / sides
            c, s = math.cos(a) * radii[i], math.sin(a) * radii[i]
            ring.append(
                (
                    centre[0] + right[0] * c + up[0] * s,
                    centre[1] + right[1] * c + up[1] * s,
                    centre[2] + right[2] * c + up[2] * s,
                )
            )
        rings.append(ring)
    grid = add_loft(mesh, rings, slot, uv)
    cap_ring(mesh, grid[0], path[0], slot, flip=True)
    cap_ring(mesh, grid[-1], path[-1], slot, flip=False)


def add_ring_tube(
    mesh: Mesh, loop: list[tuple[float, float, float]], radius: float, sides: int, slot: int, uv
) -> None:
    """A closed tube around a closed ``loop`` -- a TORUS, with no caps and no seam (r4).

    The lashing bands on the lantern tripod were ``add_prism`` over ``[*ring, ring[0]]``:
    an open tube whose two ends sit on the same point, each closed by its own cap.  The
    Collada exporter welds coincident vertices, so the two cap hubs became ONE vertex shared
    by both fans -- a closed shell pinched at a point (Euler characteristic 1, three of them
    per detail in ``b4/r4/manifold_r4.json``).  A torus has no ends to cap: the last band is
    stitched back to the first ring, the characteristic is 0, and nothing is welded.
    """

    n = len(loop)
    rings = []
    for i, centre in enumerate(loop):
        axis = _sub(loop[(i + 1) % n], loop[(i - 1) % n])
        right, up = _frame(axis)
        ring = []
        for k in range(sides):
            a = 2.0 * math.pi * k / sides
            c, s = math.cos(a) * radius, math.sin(a) * radius
            ring.append(
                (
                    centre[0] + right[0] * c + up[0] * s,
                    centre[1] + right[1] * c + up[1] * s,
                    centre[2] + right[2] * c + up[2] * s,
                )
            )
        rings.append(ring)
    su, sv = uv
    grid = [[mesh.add_vert(*p) for p in ring] for ring in rings]
    for s in range(n):
        t = (s + 1) % n
        v0, v1 = sv * s / n, sv * (s + 1) / n
        for k in range(sides):
            m = (k + 1) % sides
            u0, u1 = su * k / sides, su * (k + 1) / sides
            mesh.add_tri(grid[s][k], grid[s][m], grid[t][m], [(u0, v0), (u1, v0), (u1, v1)], slot)
            mesh.add_tri(grid[s][k], grid[t][m], grid[t][k], [(u0, v0), (u1, v1), (u0, v1)], slot)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(v):
    length = math.sqrt(sum(c * c for c in v)) or 1.0
    return (v[0] / length, v[1] / length, v[2] / length)


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _frame(axis):
    axis = _norm(axis)
    helper = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (1.0, 0.0, 0.0)
    right = _norm(_cross(axis, helper))
    up = _norm(_cross(axis, right))
    return right, up


# ------------------------------------------------------------------------ ground helper
class Ground:
    """Bilinear reads of the terrain samples the driver took under one shape."""

    def __init__(self, entry: dict[str, Any]) -> None:
        self.origin = entry["origin"]
        self.xs = entry["xs"]
        self.offsets = entry["offsets"]
        self.z = entry["z"]

    def at(self, x: float, a: float) -> float:
        xs, offs = self.xs, self.offsets
        i = max(0, min(len(xs) - 2, _bracket(xs, x)))
        j = max(0, min(len(offs) - 2, _bracket(offs, a)))
        tx = (x - xs[i]) / (xs[i + 1] - xs[i]) if xs[i + 1] != xs[i] else 0.0
        ta = (a - offs[j]) / (offs[j + 1] - offs[j]) if offs[j + 1] != offs[j] else 0.0
        tx = min(1.0, max(0.0, tx))
        ta = min(1.0, max(0.0, ta))
        z0 = self.z[i][j] * (1 - ta) + self.z[i][j + 1] * ta
        z1 = self.z[i + 1][j] * (1 - ta) + self.z[i + 1][j + 1] * ta
        return z0 * (1 - tx) + z1 * tx

    def local(self, x: float, a: float) -> float:
        return self.at(x, a) - self.origin[2]


def _bracket(values: list[float], target: float) -> int:
    low = 0
    for i in range(len(values) - 1):
        if values[i] <= target:
            low = i
    return low


# ------------------------------------------------------------------------ the bench log
def bench_geometry(ground: Ground) -> dict[str, Any]:
    """Every number the deck, the wedge and the Colmesh are built from, in local metres."""

    b = ps.BENCH
    half = b["length_m"] / 2.0
    radius = b["diam_m"] / 2.0
    run = ps.BENCH_RAMP_RUN_M
    toe_x = -half - b["ramp_toe_apron_m"]
    join_x = -half + b["ramp_on_log_m"]
    toe_local = ground.local(toe_x, 0.0) + b["toe_proud_m"]
    rise = b["deck_lift_m"] - toe_local
    grade = rise / (run - b["ease_m"])
    crown_run = float(b["west_ramp_m"])
    crown_ease = float(b["west_ease_m"])
    crown_ease_foot = float(b.get("west_ease_foot_m", crown_ease))
    crown_x = half - crown_run
    foot_z = ground.local(half, 0.0) + b["toe_proud_m"]
    crown_fall = b["deck_lift_m"] - foot_z
    crown_grade = crown_fall / ps.ramp_rise_factor(crown_run, crown_ease, crown_ease_foot)
    break_face = float(b["west_break_face_m"])
    # where the log SNAPS: the largest station whose drivable surface still stands
    # ``west_break_face_m`` above the terrain beside it.  Solved by bisection on the same
    # eased profile the crown is built from, so it moves with the crown rather than being a
    # second number that can drift away from it.
    profile = ps.ramp_profile(crown_run, crown_ease_foot, crown_fall, 3200, ease_end=crown_ease)

    def _crown_z(x: float) -> float:
        back = min(max(half - x, 0.0), crown_run)
        lo, hi = 0, len(profile) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if profile[mid][0] <= back:
                lo = mid
            else:
                hi = mid
        s0, z0 = profile[lo]
        s1, z1 = profile[hi]
        span = z0 if s1 == s0 else z0 + (z1 - z0) * (back - s0) / (s1 - s0)
        return foot_z + span

    if break_face <= 0.0:
        break_x = half  # the crown runs to the ground; there is no break face
    else:
        lo_x, hi_x = crown_x, half
        for _ in range(60):
            mid_x = 0.5 * (lo_x + hi_x)
            if _crown_z(mid_x) - ground.local(mid_x, 0.0) > break_face:
                lo_x = mid_x
            else:
                hi_x = mid_x
        break_x = round(0.5 * (lo_x + hi_x), 6)
    return {
        "half": half,
        "radius": radius,
        "run": run,
        "ease": b["ease_m"],
        "toe_x": toe_x,
        "join_x": join_x,
        "deck_z": b["deck_lift_m"],
        "toe_z": toe_local,
        "rise": rise,
        "grade": grade,
        "deck_len": b["deck_len_m"],
        # the broken crown at the west end (r2); see ps.BENCH's comment for why it exists
        "crown_x": crown_x,
        "crown_run": crown_run,
        "crown_ease": crown_ease,
        "crown_ease_foot": crown_ease_foot,
        "crown_fall": crown_fall,
        "crown_foot_z": foot_z,
        "crown_grade": crown_grade,
        "crown_crest_radius": ps.ease_crest_radius(crown_grade, crown_ease),
        "crown_foot_radius": ps.ease_crest_radius(crown_grade, crown_ease_foot),
        "crown_release_v": ps.crest_release_speed(crown_grade, crown_ease),
        "crown_taper": float(b["west_taper"]),
        "break_face_m": break_face,
        "break_x": break_x,
        "break_z": round(_crown_z(break_x), 6),
        "break_terrain_z": round(ground.local(break_x, 0.0), 6),
        "break_face_measured_m": round(_crown_z(break_x) - ground.local(break_x, 0.0), 6),
        "plateau_len": crown_x - join_x,
        # r4: the two flanks' edge treatments, each with its own three numbers
        "deck_flat_half": float(b["deck_flat_half_m"]),
        "deck_ridge_half": float(b["deck_ridge_half_m"]),
        "arris_h": float(b["arris_h_m"]),
        "arris_lift_fade": float(b["arris_lift_fade_m"]),
        "flank": {side: ps.flank_section(side, b) for side in ps.FLANK_SIDES},
        "flank_kind": {
            side: ps.flank_kind(ps.flank_section(side, b)["height"]) for side in ps.FLANK_SIDES
        },
        "splitouts": [dict(w) for w in b["flank_splitouts"]],
    }


def bench_top(geom: dict[str, Any], x: float) -> float:
    """Deck / ramp / crown top height above the shape's ground datum at local ``x``."""

    if x >= geom["crown_x"]:
        profile = _crown_profile(geom)
        return geom["crown_foot_z"] + _interp(
            profile, max(0.0, min(geom["crown_run"], geom["half"] - x))
        )
    if x >= geom["join_x"] - 1e-9:
        return geom["deck_z"]
    u = x - geom["toe_x"]
    profile = _bench_profile(geom)
    return geom["toe_z"] + _interp(profile, max(0.0, min(geom["run"], u)))


def bench_half_width(geom: dict[str, Any], x: float) -> float:
    """Half width of the log's section at ``x``: full until the crown, then tapering.

    The crown narrows on a smoothstep so the taper's own derivative is 0 where it meets the
    parallel body -- the same reason the ramp's eases exist, applied across instead of along.
    """

    # r3: the taper runs to the BREAK, not to the log's virtual end, so the snapped snout
    # really is crown_taper of the body at the face you can see.
    return ps.crown_half_width(
        geom["radius"],
        x,
        geom["crown_x"],
        geom["break_x"] - geom["crown_x"],
        geom["crown_taper"],
    )


_PROFILE_CACHE: dict[tuple[float, float, float], list[tuple[float, float]]] = {}


def _bench_profile(geom: dict[str, Any]) -> list[tuple[float, float]]:
    key = (geom["run"], geom["ease"], round(geom["rise"], 9))
    if key not in _PROFILE_CACHE:
        _PROFILE_CACHE[key] = ps.ramp_profile(geom["run"], geom["ease"], geom["rise"], 660)
    return _PROFILE_CACHE[key]


def _crown_profile(geom: dict[str, Any]) -> list[tuple[float, float]]:
    """The west descent, measured in metres back from the log's own end (its foot).

    Measured back from the FOOT, so the profile's own "ease" is the one at the foot and its
    "ease_end" is the crest's -- the reverse of how the descent is driven.
    """

    key = (geom["crown_run"], geom["crown_ease_foot"], round(geom["crown_fall"], 9))
    if key not in _PROFILE_CACHE:
        _PROFILE_CACHE[key] = ps.ramp_profile(
            geom["crown_run"],
            geom["crown_ease_foot"],
            geom["crown_fall"],
            3200,
            ease_end=geom["crown_ease"],
        )
    return _PROFILE_CACHE[key]


def _interp(profile: list[tuple[float, float]], u: float) -> float:
    lo, hi = 0, len(profile) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if profile[mid][0] <= u:
            lo = mid
        else:
            hi = mid
    s0, z0 = profile[lo]
    s1, z1 = profile[hi]
    if s1 == s0:
        return z0
    return z0 + (z1 - z0) * (u - s0) / (s1 - s0)


#: (flat-band segments, wall-face segments, crest segments) per side, by ``sides``.
#: The collider uses the SAME face and crest counts as the a700 so the two are equal across
#: the edge treatment rather than merely close -- a chorded smoothstep with fewer samples
#: rides ABOVE the curve, and a collider above its visual is the invisible shelf AGENTS.md
#: forbids.  r4's shipped wall puts its crest 0.20 m inboard of the widest line and holds
#: its height from there, so the "shelf" segments ARE the flat crest; the a700 row is 13
#: vertices wide as it was for the bolster.  The a250's face count is 2 rather than 3 for
#: the same reason -- it keeps that LOD's row at 9 columns and its triangle budget untouched.
_TOP_ROWS = {12: (6, 3, 3), 8: (4, 2, 2), 6: (4, 3, 3), 5: (2, 1, 1)}


def _side_of(a: float) -> str:
    """Which flank an across-fraction belongs to.  ``+a`` is ``+y``, toward the hearth."""

    return "inner" if a > 0.0 else "outer"


def _top_a_values(geom: dict[str, Any], sides: int) -> list[float]:
    """Across-fractions of the deck's own vertices, -1 to +1, per flank (r4).

    Each half is built from ITS OWN section, so the two flanks may carry different
    treatments in the same mesh -- which is what let r4 drive a containment bolster and a
    downward chamfer against each other on one boot.
    """

    if all(geom["flank"][s]["height"] == 0.0 for s in ps.FLANK_SIDES):
        # a flat deck: one uniform row, exactly as r2 and r3 had it
        return [-1.0 + 2.0 * k / sides for k in range(sides + 1)]
    n_flat, n_ridge, n_shelf = _TOP_ROWS[sides]
    radius = geom["radius"]
    flat_half = min(geom["flank"][s]["flat_half"] for s in ps.FLANK_SIDES)
    edge = flat_half / radius
    flat = [edge * (2.0 * k / n_flat - 1.0) for k in range(n_flat + 1)]

    def wing(side: str) -> list[float]:
        section = geom["flank"][side]
        own_edge = section["flat_half"] / radius
        crest = section["ridge_half"] / radius
        out = [own_edge + (crest - own_edge) * (k / n_ridge) for k in range(1, n_ridge + 1)]
        if crest < 1.0 - 1e-9:
            out += [crest + (1.0 - crest) * (k / n_shelf) for k in range(1, n_shelf + 1)]
        # a flank whose own flat band is wider than the narrowest one needs its extra
        # flat metres as vertices too, or the shared flat row would chord across its ridge
        if own_edge > edge + 1e-9:
            out = [edge + (own_edge - edge) * (k / n_ridge) for k in range(1, n_ridge)] + out
        return out

    return [-s for s in reversed(wing("outer"))] + flat + wing("inner")


def _bench_arris(geom: dict[str, Any], ground, x: float) -> tuple[float, float]:
    """(outer, inner) section height at station ``x``: ``-y`` first, then ``+y``.

    Faded by the log's CLEARANCE over the ground rather than by station, and opened to zero
    inside each flank's split-out window -- so the two windows really are the only places a
    car can leave over a long edge, and neither the ramp's toe nor the crown's foot ever
    grows a kerb lying on the grass (level_facts law 6).
    """

    clearance = bench_top(geom, x) - ground.local(x, 0.0)
    lift = ps.arris_lift_factor(clearance, geom["arris_lift_fade"])
    return (
        geom["flank"]["outer"]["height"] * lift * ps.splitout_factor(x, "outer", geom["splitouts"]),
        geom["flank"]["inner"]["height"] * lift * ps.splitout_factor(x, "inner", geom["splitouts"]),
    )


def _bench_ring(geom, ground, x, sides, bark=None):
    """One cross-section of the adzed log: the flat deck, its two flank sections, the belly.

    r4 gives each flank its OWN section (``geom["flank"][side]``).  The drivable band is dead
    flat out to that side's ``flat_half``; beyond it the surface follows
    :func:`props_spec.arris_rise`, which RISES for a containment bolster and FALLS for a
    downward chamfer.  The shipped section is a 0.90 m bolster on both flanks with its crest
    at the log's widest line, so the deck is a trough and the long edge is a wall.  Either
    treatment is opened to nothing inside that flank's split-out window and faded out
    wherever the log's clearance over the ground drops below ``arris_lift_fade``, so the two
    windows are the only places a car can leave over a long edge and no kerb ever lies on
    the grass at the ramp's toe or the crown's foot.

    The belly is a circular arc measured DOWN from the ARRIS,
    ``anchor - (depth + bury) * sqrt(1 - a^2)``: deepest on the centre line (a = 0) and
    level with the arris at the flanks (a = +-1).  B4's first live boot proved why the sign
    matters -- the first version wrote ``top - depth * (1 - sqrt(1 - a^2))``, the same arc
    turned inside out.  That put the belly's RIDGE 0.30 m under the deck plane and left the
    deck's own faces back-facing, so a downward ray passed through the deck and read
    **104.706 instead of 105.006**, a car teleported onto the deck came to rest INSIDE the
    shell and never moved, and both ramp climbs stopped dead at the toe (B4 boot 1).
    ``side`` is the vertical sawn face at the flank; it eases from 0 at the wedge's toe to
    ``min_side_height_m`` over the ramp's ease length, so the toe is a feather, not a kerb.

    Through the west crown ``top`` follows the roll-off arc and the section's half width
    follows :func:`bench_half_width`, while the belly's own bottom stays pinned at
    ``-bury_m`` by construction (``top - side - (depth + bury)`` with ``depth = top - side``)
    -- so the end tapers to a splintered snout that is still buried in the terrain.
    """

    b = ps.BENCH
    radius = geom["radius"]
    top = bench_top(geom, x)
    half_w = bench_half_width(geom, x)
    if geom["break_face_m"] <= 0.0 and x >= geom["half"] - geom["crown_ease_foot"]:
        # mirror of the east toe: the crown runs out INTO the terrain, so its sawn side eases
        # to zero and its top conforms to the terrain's cross-slope over the last ease.
        # Without this the log would end in a 0.10 m kerb lying on the grass -- and a kerb
        # under a descending nose is the plough law 6 is about.
        u = (geom["half"] - x) / geom["crown_ease_foot"]
        warp = 1.0 - min(1.0, max(0.0, u))
        side = b["min_side_height_m"] * ps.smoothstep(u)
    elif x >= geom["join_x"]:
        warp, side = 0.0, b["min_side_height_m"]
    else:
        u = (x - geom["toe_x"]) / geom["ease"]
        warp = 1.0 - min(1.0, max(0.0, u))
        side = b["min_side_height_m"] * ps.smoothstep(u)
    h_outer, h_inner = _bench_arris(geom, ground, x)

    heights = {"outer": h_outer, "inner": h_inner}

    def section_rise(a: float) -> float:
        """This across-fraction's own flank section, evaluated at ``a``.

        ``+a`` is toward the hearth (the inner flank).  On the centre line both sections
        read zero by construction, so the average is exact rather than a convention.
        """

        if a == 0.0:
            return 0.0
        side = _side_of(a)
        s = geom["flank"][side]
        return ps.arris_rise(
            a, s["flat_half"], radius, heights[side], s["ridge_half"], s.get("flat_top", False)
        )

    def widest(a: float) -> tuple[float, float, float]:
        """The log's widest line at the deck plane, on flank ``a`` = +-1 (r4).

        Two extra ring points so the wall has a VERTICAL outer face from its crest down to
        the deck plane and the belly's round begins at the widest line, instead of the crest
        chording straight to the first belly vertex 1.5 m below.  ``side`` is the sawn side
        the toe feathers to zero; the 4 mm floor keeps this point distinct from the top row's
        end where the wall and the sawn side are both zero, so no ring ever carries two
        coincident vertices and the loft never writes a zero-area triangle.
        """

        cross = warp * (ground.local(x, a) - ground.local(x, 0.0))
        return (x, a * half_w, top + cross - max(side, 0.004))

    ring: list[tuple[float, float, float]] = []
    for a in _top_a_values(geom, sides):
        cross = warp * (ground.local(x, a) - ground.local(x, 0.0))
        ring.append((x, a * half_w, top + section_rise(a) + cross))
    ring.append(widest(1.0))
    for k in range(1, 2 * sides):
        a = 1.0 - k / sides
        # the belly is the log's own round.  r3's ridge returns to the deck plane at the
        # log's widest line, so the belly hangs from ``top - side`` exactly as it did in r2
        # and the log's SILHOUETTE is unchanged -- only its top surface is dished.
        anchor = top - side
        depth = min(radius, max(0.0, anchor))
        base = anchor - (depth + b["bury_m"]) * math.sqrt(max(0.0, 1.0 - min(1.0, a * a)))
        if bark is not None and x >= geom["join_x"]:
            base += bark((x + geom["half"]) / 9.0, (a + 1.0) / 2.0) * 0.12
        ring.append((x, a * half_w, base))
    ring.append(widest(-1.0))
    # REVERSED: traversed top-left -> top-right -> belly the loft's faces come out
    # back-facing (measured: signed volume -1854 m3, 600 of 600 deck faces with nz < 0),
    # which is what let a downward ray pass through the deck in B4 boot 1.  Reversing the
    # section turns every face outward; the static gate asserts the volume and the deck
    # normals so this cannot regress silently.
    return ring[::-1]


def _bench_hewn_flags(geom: dict[str, Any], sides: int) -> list[bool]:
    """Which columns of the reversed ring are the HEWN drivable band (r4).

    :func:`_bench_ring` lays down the top row and then ``2 * sides - 1`` belly vertices and
    returns the list REVERSED, so the columns are computed here from the same two lists the
    ring is built from rather than from index arithmetic that a change to either row would
    silently invalidate.  r1 gave the whole body slot 1, which is why the log read as "a grey
    ridged wedge with no bark flank" from the meadow; r2 put hewn on the whole 7.0 m top.

    r4: hewn is the timber the adze actually reached -- the flat band and any DOWNWARD
    chamfer cut into it -- while a raised bolster is the log's own bark, left standing.  So
    the rule is the sign of the section, not the width of the band: a column wears bark iff
    its own flank's treatment rises above the deck plane there.
    """

    radius = geom["radius"]
    top: list[bool] = []
    for a in _top_a_values(geom, sides):
        if a == 0.0:
            top.append(True)
            continue
        s = geom["flank"][_side_of(a)]
        rise = ps.arris_rise(
            a, s["flat_half"], radius, s["height"], s["ridge_half"], s.get("flat_top", False)
        )
        top.append(rise <= 1e-9)
    # r4: the two widest-line points bracket the belly (see ``_bench_ring.widest``)
    belly = [False] * (2 * sides + 1)
    return list(reversed(top + belly))


def _bench_slot(flags: list[bool]):
    """``(band, column) -> material slot``: 1 hewn where a quad has both ends on the band."""

    n = len(flags)

    def pick(_band: int, column: int) -> int:
        return 1 if flags[column] and flags[(column + 1) % n] else 0

    return pick


def _ring_u_map(ring: list[tuple[float, float, float]]) -> list[float]:
    """Per-column u from the ring's own perimeter, so bark is not stretched on the arris."""

    lengths = [0.0]
    for k in range(len(ring)):
        m = (k + 1) % len(ring)
        lengths.append(lengths[-1] + math.dist(ring[k][1:], ring[m][1:]))
    total = lengths[-1] or 1.0
    return [v / total for v in lengths]


def build_bench(spec: dict[str, Any], ground: Ground, detail: int) -> Mesh:
    """The split log: flat face up at +3.5 m, round bark belly, hewn wedge E, crown W."""

    geom = bench_geometry(ground)
    mesh = Mesh()
    sides = 12 if detail >= 700 else (8 if detail >= 250 else 5)
    stations = _bench_stations(geom, detail)
    bark = bark_field(ps.SHAPE_SEED ^ 0xBE0C)
    radius = geom["radius"]
    rings: list[list[tuple[float, float, float]]] = []
    for x in stations:
        rings.append(_bench_ring(geom, ground, x, sides, bark))
    middle = _bench_ring(geom, ground, 0.0, sides)
    grid = add_loft(
        mesh,
        rings,
        _bench_slot(_bench_hewn_flags(geom, sides)),
        uv_scale=(4.0, geom["half"] / 3.0),
        u_map=_ring_u_map(middle),
    )
    # r4: the caps follow :func:`cap_ring`'s winding rule (grid[0] flipped, grid[-1] not).
    # r2 reversed the section to turn the loft outward and left the caps as they were, so
    # both end-grain fans faced INWARD for two revisions -- invisible at ground level where
    # the rings are slivers, but 44 misoriented edges on the a700 and 60 on the collider.
    cap_ring(mesh, grid[0], (stations[0], 0.0, bench_top(geom, stations[0]) - 0.2), 2, flip=True)
    # the crown's end cap is END GRAIN and its hub follows the crown down, so the splintered
    # lip closes on the section's own middle instead of on the r1 deck plane's hub.
    end_hub = (bench_top(geom, stations[-1]) - ps.BENCH["bury_m"]) * 0.5
    cap_ring(mesh, grid[-1], (stations[-1], 0.0, end_hub), 2, flip=False)
    # the two hewn knots the design gives every generated log
    for centre in (-geom["half"] + 62.0, geom["half"] - 18.0):
        _add_knot(mesh, centre, radius, geom, slot=0)
    return mesh


#: fractions of a split-out's fade that get a station of their own
_FADE_MARKS = (0.0, 0.25, 0.5, 0.75, 1.0)


def _split_stations(geom: dict[str, Any]) -> list[float]:
    """The stations a split-out's arris fade needs, so the window has square shoulders."""

    out: list[float] = []
    for window in geom["splitouts"]:
        half = 0.5 * float(window["length_m"])
        fade = float(window["fade_m"])
        centre = float(window["centre_x"])
        for mark in _FADE_MARKS:
            out.append(round(centre - half - mark * fade, 6))
            out.append(round(centre + half + mark * fade, 6))
    return out


def _bench_apply_splits(stations: list[float], geom: dict[str, Any]) -> list[float]:
    """Put the split-out fades' own stations in, and take every other station OUT of them.

    Both the visual and the collider run this, so through a fade -- the one place on the
    deck where the arris height changes ALONG the log -- the two meshes are chorded at
    exactly the same stations and the collider cannot ride above the visual.  Without it a
    7.35 m collider step against a 6.0 m visual step put the collider 24 mm proud inside
    the inner split-out's fade, which is the invisible shelf AGENTS.md forbids.
    """

    marks = {s for s in _split_stations(geom) if geom["join_x"] < s < geom["crown_x"] - 1e-6}
    bands = []
    for window in geom["splitouts"]:
        half = 0.5 * float(window["length_m"])
        fade = float(window["fade_m"])
        centre = float(window["centre_x"])
        bands.append((centre - half - fade, centre - half))
        bands.append((centre + half, centre + half + fade))
    keep = [
        s for s in stations if not any(lo + 1e-9 < s < hi - 1e-9 for lo, hi in bands) or s in marks
    ]
    return sorted(set(keep) | marks)


def _bench_stations(geom: dict[str, Any], detail: int) -> list[float]:
    step_deck, step_ramp = {700: (7.0, 0.6), 250: (12.0, 2.0), 80: (18.0, 4.0)}[detail]
    step_crown = {700: 0.4, 250: 1.3, 80: 2.7}[detail]
    # r3: the ramp's middle 27 m is CONSTANT grade -- a straight line needs no stations, and
    # the rings it does not spend are what pay for the dished deck's two extra columns and
    # the crown's 0.2 m foot chords inside the same triangle budget.  The coarse run is
    # bounded by the two eases EXACTLY, or a 2.4 m chord straddles the top ease's start and
    # the ramp reads 24 mm off its own profile there.
    ease_top = geom["toe_x"] + geom["ease"]
    ease_bot = geom["toe_x"] + geom["run"] - geom["ease"]
    stations = [geom["toe_x"]]
    x = geom["toe_x"]
    schedule = ((ease_top, step_ramp), (ease_bot, 4.0 * step_ramp), (geom["join_x"], step_ramp))
    for limit, step in schedule:
        while x < limit - 1e-6:
            x = min(limit, x + step)
            stations.append(x)
    while x < geom["crown_x"] - 1e-6:
        x = min(geom["crown_x"], x + step_deck)
        stations.append(x)
    # the crown is a curve, not a plane; its chords stay well inside the 20 mm relief law
    # and the arc is convex-then-concave, so neither sign runs away.  r3's crown is short
    # and steep, so its concave FOOT is a 1.85 m radius against the crest's 4.25 m -- the
    # foot gets half the step, or a 0.4 m chord across it sags 10.8 mm on its own.
    foot_x = geom["half"] - geom["crown_ease_foot"]
    end_x = geom["break_x"]
    while x < end_x - 1e-6:
        x = min(end_x, x + (step_crown if x < foot_x - 1e-9 else 0.5 * step_crown))
        stations.append(x)
    if detail >= 250:
        # a split-out that opens between two stations is a diagonal gash rather than a
        # window, so its fade stations are inserted whatever the deck's own step is.
        stations = _bench_apply_splits(stations, geom)
    return stations


def _add_knot(mesh: Mesh, x: float, radius: float, geom: dict[str, Any], slot: int) -> None:
    """A 2.5 m sawn-off knot on the belly, at the log's widest line."""

    ring_count, sides = 4, 8
    path = []
    for i in range(ring_count):
        t = i / (ring_count - 1)
        path.append((x, -radius * 0.94 - t * 1.25, geom["deck_z"] - radius * 0.62 - t * 0.28))
    add_prism(mesh, path, [1.25, 1.05, 0.82, 0.6], sides, slot, uv=(2.0, 1.0))


def build_bench_colmesh(ground: Ground) -> Mesh:
    """The COLLIDER: the same cross-section the visual has, at 6 points a side.

    A box would have been cheaper and wrong: the belly is undercut, so a rectangular
    collider puts an invisible vertical shelf under both deck edges, and AGENTS.md's
    "collision plates must never outreach their visual" is exactly that defect.  The rings
    below are :func:`build_bench`'s rings with the bark displacement and the knots left off,
    so the collider is inside the visual everywhere and equal to it on the drivable face.
    """

    geom = bench_geometry(ground)
    mesh = Mesh()
    sides = 6
    # r3: the collider uses the a700's OWN stations, not a coarser set of its own.  The two
    # meshes then chord every curve the log has -- the ramp's eases, the arris lift as the
    # log rises out of the ground, both split-out fades and the crown's convex crest and
    # concave foot -- at exactly the same x, so the collider cannot ride above the visual
    # anywhere along the log.  r2's independent 0.75 / 2.5 / 7.35 / 0.75 schedule is what
    # put it +8.02 mm proud at the descent's foot (critic pass 2, N6).  It differs from the
    # visual only ACROSS the section (6 points a side instead of 12) and by leaving the bark
    # displacement and the knots off -- both of which only ever move the surface DOWN.
    stations = _bench_stations(geom, 700)
    rings = [_bench_ring(geom, ground, sx, sides) for sx in stations]
    grid = add_loft(
        mesh,
        rings,
        0,
        uv_scale=(1.0, 1.0),
        u_map=_ring_u_map(_bench_ring(geom, ground, 0.0, sides)),
    )
    # r4: same winding rule as the visual (see cap_ring) -- the collider's two end rings
    # carried all 60 of its misoriented edges
    cap_ring(mesh, grid[0], (stations[0], 0.0, bench_top(geom, stations[0]) - 0.1), 0, True)
    end_hub = (bench_top(geom, stations[-1]) - ps.BENCH["bury_m"]) * 0.5
    cap_ring(mesh, grid[-1], (stations[-1], 0.0, end_hub), 0, False)
    return mesh


# ------------------------------------------------------------------------ the round logs
def build_round_log(spec: dict[str, Any], ground: Ground, detail: int) -> Mesh:
    row = ps.log_row(spec["layout"])
    length, diam = float(row["length"]), float(row["diam"])
    sink = -float(row["z_offset"])
    axis_z = diam / 2.0 - sink
    sides = 24 if detail >= 700 else (12 if detail >= 250 else 7)
    steps = max(6, int(length / {700: 2.0, 250: 8.0, 80: 20.0}[detail]))
    bark = bark_field(ps.SHAPE_SEED ^ (0xA0 + len(spec["key"])))
    mesh = Mesh()
    rings = []
    char = spec.get("char_ends", False)
    char_len = 7.0
    slots = []
    for s in range(steps + 1):
        t = s / steps
        x = -length / 2.0 + t * length
        taper = 1.0 - 0.16 * abs(2.0 * t - 1.0) ** 1.6
        r0 = diam / 2.0 * taper
        ring = []
        for k in range(sides):
            a = 2.0 * math.pi * k / sides
            r = r0
            if detail >= 250:
                r += bark(x / 11.0, k / sides) * 0.12
            for knot_x, knot_r in ((-length * 0.22, 1.4), (length * 0.28, 1.1)):
                d = math.hypot(x - knot_x, (a - 1.2) * r0 * 0.8)
                if d < knot_r:
                    r += (1.0 - d / knot_r) ** 2 * 0.55
            ring.append((x, r * math.cos(a), axis_z + r * math.sin(a)))
        rings.append(ring)
        near_end = min(x + length / 2.0, length / 2.0 - x)
        slots.append(1 if (char and near_end < char_len) else 0)
    bands = [1 if (slots[s] or slots[s + 1]) else 0 for s in range(len(rings) - 1)]
    grid = add_loft(mesh, rings, bands, uv_scale=(4.0, length / 12.0))
    cap_ring(mesh, grid[0], (-length / 2.0, 0.0, axis_z), 2, flip=True)
    cap_ring(mesh, grid[-1], (length / 2.0, 0.0, axis_z), 2, flip=False)
    return mesh


#: A regular ``n``-gon of circumradius ``R`` has inradius ``R cos(pi/n)``.  Scaling ``R`` by
#: this puts the visual's circle midway between the polygon's corners and its flats, so a
#: 12-sided collider straddles a round log by +-1.7 % of its radius instead of standing wholly
#: outside it (corners on the circle: flats 3.4 % inside) or wholly inside it.
def _straddle(sides: int) -> float:
    return 1.0 / math.sqrt(math.cos(math.pi / sides))


def build_round_colmesh(spec: dict[str, Any]) -> Mesh:
    """The round log's collider on the VISUAL'S OWN TAPER (r4, the thin-shell gate).

    r3's collider was a straight 12-sided prism at the full radius over three rings, while
    :func:`build_round_log` tapers the log 16 % towards each end -- so the collider stood
    0.5 m proud of the bark at both ends, an invisible wall of the class critic B2 pass 5
    ruled on, and ``collider_probe`` read a car-band phantom gap p90 of 1.26 m on log_north
    and 1.24 m on log_south.  Nine stations on the same taper; the bark's own relief is
    +-0.12 m about that radius and the knots stand 0.55 m proud of it, both visual.
    """

    row = ps.log_row(spec["layout"])
    length, diam = float(row["length"]), float(row["diam"])
    axis_z = diam / 2.0 + float(row["z_offset"])
    sides = 12
    path, radii = [], []
    for s in range(9):
        t = s / 8.0
        path.append((-length / 2.0 + t * length, 0.0, axis_z))
        taper = 1.0 - 0.16 * abs(2.0 * t - 1.0) ** 1.6
        radii.append(diam / 2.0 * taper * _straddle(sides))
    mesh = Mesh()
    add_prism(mesh, path, radii, sides, 0, uv=(1.0, 1.0))
    return mesh


def build_leaner(spec: dict[str, Any], ground: Ground, detail: int) -> Mesh:
    row = ps.log_row("leaner_log")
    length, diam = float(row["length"]), float(row["diam"])
    sides = 24 if detail >= 700 else (12 if detail >= 250 else 7)
    steps = max(6, int(length / {700: 2.0, 250: 8.0, 80: 20.0}[detail]))
    bark = bark_field(ps.SHAPE_SEED ^ 0x1EA5)
    mesh = Mesh()
    rings = []
    for s in range(steps + 1):
        t = s / steps
        x = t * length
        taper = 1.0 - 0.18 * t
        r0 = diam / 2.0 * taper
        ring = []
        for k in range(sides):
            a = 2.0 * math.pi * k / sides
            r = r0 + (bark(x / 11.0, k / sides) * 0.12 if detail >= 250 else 0.0)
            ring.append((x, r * math.cos(a), r * math.sin(a)))
        rings.append(ring)
    grid = add_loft(mesh, rings, 0, uv_scale=(4.0, length / 12.0))
    cap_ring(mesh, grid[0], (0.0, 0.0, 0.0), 2, flip=True)
    cap_ring(mesh, grid[-1], (length, 0.0, 0.0), 2, flip=False)
    return mesh


def build_leaner_colmesh(spec: dict[str, Any]) -> Mesh:
    """The leaner's collider on its own 18 % taper (r4): r3's constant-radius prism stood
    0.46 m proud of the bark at the far end (car-band phantom gap p90 1.50 m by ray)."""

    row = ps.log_row("leaner_log")
    length, diam = float(row["length"]), float(row["diam"])
    sides = 12
    path, radii = [], []
    for s in range(7):
        t = s / 6.0
        path.append((t * length, 0.0, 0.0))
        radii.append(diam / 2.0 * (1.0 - 0.18 * t) * _straddle(sides))
    mesh = Mesh()
    add_prism(mesh, path, radii, sides, 0, uv=(1.0, 1.0))
    return mesh


# ------------------------------------------------------------------------ the giant props
def build_tripod(spec: dict[str, Any], ground: Ground, detail: int) -> Mesh:
    row = ps.prop_row("lantern_tripod")
    origin_z = float(row["z_ground"])
    apex = (0.0, 0.0, 62.0)
    sides = 12 if detail >= 700 else (8 if detail >= 250 else 5)
    mesh = Mesh()
    for foot in row["feet"]:
        fx = float(foot["x"]) - float(row["x"])
        fy = float(foot["y"]) - float(row["y"])
        fz = float(foot["terrain_z"]) - origin_z - 0.9  # the foot is dug in
        direction = _norm((apex[0] - fx, apex[1] - fy, apex[2] - fz))
        length = math.dist((fx, fy, fz), apex) + 4.9  # the poles cross above the lashing
        path = [
            (
                fx + direction[0] * length * t,
                fy + direction[1] * length * t,
                fz + direction[2] * length * t,
            )
            for t in (0.0, 0.35, 0.7, 1.0)
        ]
        add_prism(mesh, path, [1.35, 1.25, 1.15, 1.02], sides, 0, uv=(2.0, 6.0))
    # the lashing: three rope bands just under the crossing.  r4: each band is a TORUS
    # (``add_ring_tube``), not an open tube bent round on itself -- the old form's two cap
    # hubs sat on one point, the exporter welded them, and every band was a shell pinched
    # at a vertex (Euler characteristic 1 instead of 0).
    for k, z in enumerate((57.5, 58.6, 59.7)):
        ring = []
        radius = 3.4 - k * 0.35
        for i in range(sides * 2):
            a = 2.0 * math.pi * i / (sides * 2)
            ring.append((radius * math.cos(a), radius * math.sin(a), z))
        add_ring_tube(mesh, ring, 0.34, 5, 1, uv=(8.0, 1.0))
    # the hook the lantern hangs from
    add_prism(mesh, [(0.0, 0.0, 58.0), (0.0, 0.0, 47.0)], 0.28, 6, 1, uv=(1.0, 4.0))
    return mesh


def build_tripod_colmesh(spec: dict[str, Any]) -> Mesh:
    row = ps.prop_row("lantern_tripod")
    origin_z = float(row["z_ground"])
    mesh = Mesh()
    apex = (0.0, 0.0, 62.0)
    for foot in row["feet"]:
        fx = float(foot["x"]) - float(row["x"])
        fy = float(foot["y"]) - float(row["y"])
        fz = float(foot["terrain_z"]) - origin_z - 0.9
        # r4: each pole runs 1.5 m PAST the apex along its own line, as the visual's do,
        # so the three top caps end on three different points.  Ending all three ON the
        # apex put three cap hubs on one point, the exporter welded them, and the collider
        # was one shell pinched at a vertex (Euler characteristic 4 = three spheres sharing
        # a point) instead of three closed poles.
        direction = _norm((apex[0] - fx, apex[1] - fy, apex[2] - fz))
        length = math.dist((fx, fy, fz), apex) + 1.5
        top = (fx + direction[0] * length, fy + direction[1] * length, fz + direction[2] * length)
        add_prism(mesh, [(fx, fy, fz), top], 1.3, 6, 0, uv=(1.0, 1.0))
    return mesh


def build_lantern(spec: dict[str, Any], detail: int) -> Mesh:
    """A 16 m hurricane lantern hung by its bail: origin at the hang point, body below."""

    sides = 16 if detail >= 700 else (10 if detail >= 250 else 6)
    mesh = Mesh()
    # bail: a steel arc from the hang point down to the cap's two ears.  r4: the two arcs
    # start 0.24 m apart rather than at one shared point -- sharing it put two closed shells
    # on the same hub vertex and the same two ring vertices, which read as two edges owned
    # by FOUR triangles at every LOD (the orchestrator's manifold probe, 2026-09-07).
    for sign in (-1.0, 1.0):
        path = [
            (sign * 0.12, 0.0, -0.05),
            (sign * 0.9, 0.0, -0.35),
            (sign * 1.5, 0.0, -0.95),
            (sign * 1.65, 0.0, -1.55),
        ]
        add_prism(mesh, path, 0.16, 6, 0, uv=(1.0, 3.0))
    # ventilated cap
    add_prism(
        mesh,
        [(0.0, 0.0, -1.35), (0.0, 0.0, -1.95), (0.0, 0.0, -2.25)],
        [1.05, 2.15, 1.75],
        sides,
        0,
        uv=(3.0, 1.0),
    )
    # globe (emissive slot 1), a barrelled cylinder
    globe = []
    for s in range(9):
        t = s / 8.0
        globe.append((0.0, 0.0, -2.3 - t * 7.7))
    radii = [1.6 + 0.55 * math.sin(math.pi * (i / 8.0)) for i in range(9)]
    add_prism(mesh, globe, radii, sides, 1, uv=(3.0, 2.0))
    # guard wires
    for k in range(6):
        a = 2.0 * math.pi * k / 6
        add_prism(
            mesh,
            [
                (2.15 * math.cos(a), 2.15 * math.sin(a), -2.4),
                (2.35 * math.cos(a), 2.35 * math.sin(a), -6.2),
                (2.15 * math.cos(a), 2.15 * math.sin(a), -9.9),
            ],
            0.12,
            5,
            0,
            uv=(1.0, 4.0),
        )
    # fount and base ring
    add_prism(
        mesh,
        [(0.0, 0.0, -9.9), (0.0, 0.0, -12.4), (0.0, 0.0, -14.1), (0.0, 0.0, -16.0)],
        [1.75, 2.35, 2.3, 1.9],
        sides,
        0,
        uv=(3.0, 1.5),
    )
    return mesh


def build_lantern_colmesh(spec: dict[str, Any]) -> Mesh:
    mesh = Mesh()
    add_prism(mesh, [(0.0, 0.0, -1.2), (0.0, 0.0, -16.0)], 2.3, 8, 0, uv=(1.0, 1.0))
    return mesh


def build_pot(spec: dict[str, Any], cache: Path, detail: int) -> Any:
    """pot_enamel_01 (CC0) at x54: imported, welded, decimated, dropped to its own base."""

    bpy = bf._bpy()
    obj = bf.import_model(cache, "pot_enamel_01", None, False, 14.0)
    obj.name = "pot_import"
    lowest = min((obj.matrix_world @ v.co).z for v in obj.data.vertices)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    obj.location.z -= lowest
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def build_sign(spec: dict[str, Any], detail: int) -> Mesh:
    """A 2.40 m trail sign (design §11: human scale beside 100 m logs).

    The board face stays 1.70 x 0.70 m because ``prop_textures._sign_letters`` pre-distorts
    the routed text for exactly that aspect; the height comes from the posts, not the board.
    """

    mesh = Mesh()
    for sign in (-1.0, 1.0):
        add_prism(
            mesh,
            [(sign * 0.62, 0.0, -0.45), (sign * 0.62, 0.0, 2.16)],
            0.075,
            8 if detail >= 250 else 4,
            0,
            uv=(1.0, 4.0),
        )
    # the routed face, slot 1: 1.70 x 0.70 m, its top rail at 2.25 m
    add_box(mesh, (-0.85, -0.035, 1.55), (0.85, 0.035, 2.25), 1, uv_scale=1.0)
    add_box(mesh, (-0.92, -0.05, 2.25), (0.92, 0.05, 2.40), 0)
    for sign in (-1.0, 1.0):
        add_prism(
            mesh, [(sign * 0.62, -0.06, 1.90), (sign * 0.62, 0.06, 1.90)], 0.05, 6, 2, uv=(1.0, 1.0)
        )
    return mesh


def build_cairn(spec: dict[str, Any], detail: int) -> Mesh:
    rng = random.Random(ps.SHAPE_SEED ^ 0xCA12)  # noqa: S311 - deterministic cairn stack
    mesh = Mesh()
    z = 0.0
    for k in range(7):
        t = k / 6.0
        w = 0.62 * (1.0 - 0.55 * t)
        h = 0.335 * (1.0 - 0.35 * t)  # seven slabs stack to the design's 1.80 m
        yaw = rng.uniform(-0.5, 0.5)
        dx, dy = rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05)
        sides = 7 if detail >= 250 else 5
        ring_lo, ring_hi = [], []
        for i in range(sides):
            a = 2.0 * math.pi * i / sides + yaw
            r = w * (0.82 + 0.25 * rng.random())
            ring_lo.append((dx + r * math.cos(a), dy + r * math.sin(a), z))
            ring_hi.append((dx + r * 0.92 * math.cos(a), dy + r * 0.92 * math.sin(a), z + h))
        grid = add_loft(mesh, [ring_lo, ring_hi], 0, uv_scale=(2.0, 1.0))
        cap_ring(mesh, grid[0], (dx, dy, z), 0, flip=True)
        cap_ring(mesh, grid[-1], (dx, dy, z + h), 0, flip=False)
        z += h * 0.92
    return mesh


def build_fence_post(spec: dict[str, Any], detail: int) -> Mesh:
    mesh = Mesh()
    sides = 6 if detail >= 250 else 4
    add_prism(mesh, [(0.0, 0.0, -0.45), (0.0, 0.0, 1.35)], [0.085, 0.072], sides, 0, uv=(1.0, 4.0))
    for z in (0.55, 1.05):
        add_box(mesh, (-0.10, -0.05, z - 0.055), (0.10, 0.05, z + 0.055), 1)
    return mesh


def build_fence_rail(spec: dict[str, Any], detail: int) -> Mesh:
    mesh = Mesh()
    sides = 5 if detail >= 250 else 3
    path = [(-3.9, 0.0, 0.0), (0.0, 0.0, -0.05), (3.9, 0.0, 0.0)]
    add_prism(mesh, path, 0.065, sides, 0, uv=(1.0, 10.0))
    return mesh


def build_lantern_post(spec: dict[str, Any], detail: int) -> Mesh:
    mesh = Mesh()
    sides = 8 if detail >= 250 else 4
    # r4: no two parts may END on the same point.  The exporter welds coincident vertices,
    # so a bracket that started exactly where the post ended shared its cap hub with it and
    # the two closed shells became one shell pinched at a vertex (Euler characteristic 3).
    # Each joint now starts 2 cm INSIDE the part before it: the parts overlap as solids do
    # and every one stays a closed shell of its own.
    add_prism(mesh, [(0.0, 0.0, -0.5), (0.0, 0.0, 2.35)], [0.10, 0.085], sides, 0, uv=(1.0, 5.0))
    add_prism(mesh, [(0.0, 0.0, 2.33), (0.0, 0.30, 2.42)], 0.05, 5, 1, uv=(1.0, 2.0))
    add_prism(mesh, [(0.0, 0.30, 2.38), (0.0, 0.30, 2.10)], [0.15, 0.13], sides, 2, uv=(1.0, 1.0))
    add_prism(mesh, [(0.0, 0.30, 2.12), (0.0, 0.30, 1.94)], 0.16, sides, 1, uv=(1.0, 1.0))
    return mesh


#: The enamel pot's BODY profile, (z, r) in metres, read off the shipped ``Cube.001`` (the
#: a700 of pot_enamel_01 at x54): per 0.4 m band, the median over 36 angular bins of each
#: bin's largest radius, which the two side handles (12 of 36 bins, z 4.4-5.9) cannot move.
#: The handles hang 4.5 m up and are left to the visual; the lid dome above 7.4 m is one cone.
#: r3's collider was a 10-sided cylinder r 4.75 -> 3.90 from z 0.05 to **13.9** on a pot
#: 9.49 m tall whose belly curves in to r 3.6 at the base: 4.4 m of invisible post above the
#: lid and a car-band phantom gap p90 of 1.01 m (max 2.10 m) at the foot -- exactly the
#: invisible-wall class critic B2 pass 5 ruled on (``b4/r4/collider_probe_r4.json``).
POT_PROFILE = (
    (0.02, 3.45),
    (0.45, 3.72),
    (1.05, 4.10),
    (1.75, 4.42),
    (3.00, 4.72),
    (5.50, 4.79),
    (7.40, 4.80),
    (9.45, 0.90),
)


def simple_colmesh(spec: dict[str, Any], key: str) -> Mesh:
    """The dressing props' colliders.  r4: no box may stand where the visual is air.

    A full-height box around a thin post is an invisible wall for everything the box covers
    and the post does not: the trail sign's box read a car-band phantom gap p90 of 1.01 m
    (1,656 of 2,592 rays hit the box and nothing behind it), the lantern post's the same.
    Each is now the post's own prism plus a box around the part it carries, sized inside the
    shape's declared ``colmesh`` budget so :func:`blender_forest.decimate_to` never runs.
    """

    mesh = Mesh()
    if key == "trail_sign":
        # two 6-sided posts on the visual's 0.075 m posts, and ONE box for the board and its
        # top rail (1.55 .. 2.40 m): 2 x 24 + 12 = 60 = the budget
        for sign in (-1.0, 1.0):
            add_prism(
                mesh,
                [(sign * 0.62, 0.0, -0.45), (sign * 0.62, 0.0, 2.16)],
                0.075 * _straddle(6),
                6,
                0,
                uv=(1.0, 1.0),
            )
        add_box(mesh, (-0.92, -0.05, 1.55), (0.92, 0.05, 2.40), 0)
    elif key == "trail_cairn":
        add_prism(mesh, [(0.0, 0.0, 0.0), (0.0, 0.0, 1.82)], [0.62, 0.30], 8, 0, uv=(1.0, 1.0))
    elif key == "fence_post":
        add_box(mesh, (-0.10, -0.10, -0.45), (0.10, 0.10, 1.35), 0)
    elif key == "fence_rail":
        add_box(mesh, (-3.9, -0.075, -0.14), (3.9, 0.075, 0.075), 0)
    elif key == "lantern_post":
        # the post's own 8-sided prism, and a box round the bracket and the lantern it
        # carries at 1.9-2.4 m: 32 + 12 = 44 of a 56 budget
        add_prism(
            mesh,
            [(0.0, 0.0, -0.5), (0.0, 0.0, 2.35)],
            [0.10 * _straddle(8), 0.085 * _straddle(8)],
            8,
            0,
            uv=(1.0, 1.0),
        )
        add_box(mesh, (-0.17, 0.13, 1.92), (0.17, 0.47, 2.44), 0)
    elif key == "enamel_pot":
        # 12 sides x 8 stations = 192 of a 200 budget, on the body's own measured profile
        path = [(0.0, 0.0, z) for z, _r in POT_PROFILE]
        radii = [r * _straddle(12) for _z, r in POT_PROFILE]
        add_prism(mesh, path, radii, 12, 0, uv=(1.0, 1.0))
    else:
        raise SystemExit(f"no colmesh recipe for {key}")
    return mesh


# ------------------------------------------------------------------------ build one shape
def build_shape(
    key: str, out_root: Path, cache: Path, ground_doc: dict[str, Any]
) -> dict[str, Any]:
    bpy = bf._bpy()
    spec = ps.SHAPES[key]
    bf.clear_scene()
    stem = ps.shape_stem(key)
    names = [ps.material_name(m) for m in spec["materials"]]
    materials = [bf.make_material(n) for n in names]
    base = bf.empty(bf.BASE_NODE)
    start = bf.empty(bf.START_NODE, base)
    bf.empty(f"nulldetail{ps.NULL_DETAIL}", base)
    if spec.get("bb"):
        bf.empty(fs.BB_NODE, base)
    ground = Ground(ground_doc[key]) if key in ground_doc else None
    report: dict[str, Any] = {}
    objects = []
    for pixel in ps.DETAILS:
        if spec["kind"] == "pot":
            obj = build_pot(spec, cache, pixel)
            obj.name = bf.detail_node(stem, pixel)
            bf.rebind_material(obj, materials[0])
            obj.parent = start
        else:
            mesh = _mesh_for(spec, key, ground, pixel)
            obj = bf.object_from_mesh(bf.detail_node(stem, pixel), mesh, materials, start)
        bf.triangulate(obj, weld=False)
        tris = bf.decimate_to(obj, spec["budget"][pixel])
        report[f"a{pixel}"] = tris
        objects.append(obj)
    col_mesh = _colmesh_for(spec, key, ground)
    col = bf.object_from_mesh(bf.colmesh_node(stem), col_mesh, [materials[0]], start)
    bf.triangulate(col, weld=False)
    report["colmesh"] = bf.decimate_to(col, spec["colmesh"])
    objects.append(col)
    bf.purge_unused_materials(set(names))
    path = out_root / ps.shape_relative(key)
    tree = bf.expected_tree(
        stem, ps.DETAILS, bb=bool(spec.get("bb")), null=ps.NULL_DETAIL, colmesh=True
    )
    used = set()
    for obj in objects:
        for slot in obj.data.materials:
            if slot is not None:
                used.add(slot.name)
    result = bf.export_dae([base, start, *objects], path, tree, used, bool(spec.get("bb")))
    result.update(
        {
            "key": key,
            "relative": ps.shape_relative(key),
            "tris": report,
            "collision": spec["collision"],
            "bb": bool(spec.get("bb")),
        }
    )
    if key == "bench_log" and ground is not None:
        geom = bench_geometry(ground)
        result["bench"] = {
            k: round(float(v), 6) for k, v in geom.items() if isinstance(v, (int, float))
        }
        result["bench"]["grade_pct"] = round(geom["grade"] * 100.0, 4)
        result["bench"]["splitouts"] = geom["splitouts"]
        result["bench"]["deck_flat_width_m"] = round(2.0 * geom["deck_flat_half"], 6)
        result["bench"]["flank"] = geom["flank"]
        result["bench"]["flank_kind"] = geom["flank_kind"]
        result["bench"]["wall_flat_top"] = bool(ps.BENCH.get("wall_flat_top", False))
    _ = bpy
    return result


def _mesh_for(spec, key, ground, pixel):
    kind = spec["kind"]
    if kind == "bench":
        return build_bench(spec, ground, pixel)
    if kind == "round_log":
        return build_round_log(spec, ground, pixel)
    if kind == "leaner":
        return build_leaner(spec, ground, pixel)
    if kind == "tripod":
        return build_tripod(spec, ground, pixel)
    if kind == "lantern":
        return build_lantern(spec, pixel)
    if kind == "sign":
        return build_sign(spec, pixel)
    if kind == "cairn":
        return build_cairn(spec, pixel)
    if kind == "fence_post":
        return build_fence_post(spec, pixel)
    if kind == "fence_rail":
        return build_fence_rail(spec, pixel)
    if kind == "lantern_post":
        return build_lantern_post(spec, pixel)
    raise SystemExit(f"no builder for {kind}")


def _colmesh_for(spec, key, ground):
    kind = spec["kind"]
    if kind == "bench":
        return build_bench_colmesh(ground)
    if kind == "round_log":
        return build_round_colmesh(spec)
    if kind == "leaner":
        return build_leaner_colmesh(spec)
    if kind == "tripod":
        return build_tripod_colmesh(spec)
    if kind == "lantern":
        return build_lantern_colmesh(spec)
    return simple_colmesh(spec, key)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--ground", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--only", default=None)
    arguments = parser.parse_args(argv)
    ground_doc = json.loads(arguments.ground.read_text(encoding="utf-8"))
    only = set(arguments.only.split(",")) if arguments.only else set(ps.SHAPES)
    started = time.time()
    shapes = {}
    for key in ps.SHAPES:
        if key not in only:
            continue
        shapes[key] = build_shape(key, arguments.out, arguments.cache, ground_doc)
    manifest = {
        "level_id": ps.LEVEL_ID,
        "shapes": shapes,
        "blender": bf._bpy().app.version_string,
        "collada_decimals": bf.COLLADA_DECIMALS,
        "bb_property": fs.BB_PROPERTY,
        "shape_seed": ps.SHAPE_SEED,
        "seconds": round(time.time() - started, 1),
    }
    arguments.manifest.parent.mkdir(parents=True, exist_ok=True)
    arguments.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
