"""Plant the Giant's Hearth forest: datablocks, forest4 instances, covers, wind (design §4.4-4.5).

    .\\.venv\\Scripts\\python.exe examples/hot_potato_arena/level/plant_forest.py \\
        --out examples/hot_potato_arena/mod/levels/ericrolph_hot_potato_arena \\
        --manifest examples/hot_potato_arena/authoring/ericrolph_hot_potato_arena_forest_plant.json

Writes, all under the level root:

* ``art/forest/managedItemData.json``   -- 54 ``TSForestItemData`` with the italy
  ``cypress_tree`` field set (study §7.2) scaled by height, annotation NATURE / ROCK,
* ``forest/<datablock>.forest4.json``   -- the JSONL the engine actually reads (level_facts:
  "Forest instances load from forest/<item>.forest4.json ONLY"),
* ``art/shapes/<family>/ericrolph_hot_potato_arena_<family>.materials.json`` -- 31 materials,
* the vegetation group records (17 ``GroundCover`` -- design 4.5's ten with its five billboard
  covers split into twelve on the same layers and the same 1.41 M element budget, DEV-12 --
  1 ``ForestWindEmitter`` and ``theForest``), handed to ``level_writer`` through ``forest_build``.

Placement is a seeded Poisson-disc per category over the MEASURED zone masks of the frozen
terrain model, with the design's keep-outs enforced before a candidate is ever offered:

  * ``terrain_model.clear_radius(theta)`` -- 350 m, 420 m inside the four lane sectors,
  * the S1 sightline cone to the lake (``terrain_model.sightline_cone``),
  * the road corridor +- 9 m on ``terrain_model.road_distance_field`` (track ring AND trail),
  * the lake at ``lake_e < 1.05``,
  * 12 m around every spawn sphere and 6 m around every truth-frame camera eye,
  * a per-category slope ceiling.

Heights come from ``terrain_io.surface_z`` -- the BILINEAR sample, which report_B §3.4 measured
to BE the collision surface, so an instance's authored z is the z a ray finds.  B1 owns the
``.ter``; this module never touches it and reads the design model instead, so the two agree by
construction (``terrain_io`` vendors that model byte-for-byte).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from examples.hot_potato_arena.level import forest_spec as fs
from examples.hot_potato_arena.level import terrain_io as terrain
from examples.hot_potato_arena.level import terrain_model as tm

NAMESPACE_UUID = uuid.UUID("0f7b6c1e-2a4d-4f9b-9d3e-8b1a5c7e2d40")
LEVEL_ID = fs.LEVEL_ID
LEVEL_RELATIVE = f"levels/{LEVEL_ID}"

#: Truth-frame eyes (design §8 / layout.json cameras) and spawn spheres (§2.7) -- nothing may
#: stand in a camera's lap or on a spawn pad.
CAMERA_EYES = (
    (750.50, -107.66),
    (981.00, -506.90),
    (804.30, -200.84),
    (1033.17, -312.30),
    (1061.19, -115.00),
    (850.00, -342.00),
    (997.10, 124.10),
    (1225.20, -917.80),
    (461.00, -153.60),
    (1452.10, 437.60),
    (850.00, -280.00),
)
SPAWNS = ((978.00, -501.70), (466.72, -155.47), (1281.64, -1110.48), (850.00, -280.00))

FAMILY_DIRS = {
    "trees": fs.TREES_DIR,
    "deadwood": fs.DEADWOOD_DIR,
    "undergrowth": fs.CARDS_DIR,
    "rocks": fs.ROCKS_DIR,
    "groundcover": fs.COVER_DIR,
}


def persistent_id(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE_UUID, name))


# ``allow_nan=False`` is load-bearing, not decoration.  CPython's encoder emits the bare tokens
# ``NaN`` / ``Infinity`` by default and its decoder reads them back, so a non-finite number
# round-trips through ``json`` while being invalid JSON (RFC 8259 has no such literal).  195
# instances shipped with ``pos.z = NaN`` before this flag went in; with it the encoder raises.
def _json_bytes(document: Any) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _jsonl_bytes(records: list[dict]) -> bytes:
    return "".join(
        json.dumps(r, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        for r in records
    ).encode("utf-8")


def _r4(value: float) -> float:
    return round(float(value), 4)


# ------------------------------------------------------------------------------- zone masks
def build_masks() -> dict[str, Any]:
    """Zone masks, the keep-out mask and the slope field, on the frozen model's 2048 grid."""
    grid = terrain.grid()  # r17: the painted grid, never the frozen model's directly
    xs, ys, layers, zq, road_d = grid["xs"], grid["ys"], grid["layers"], grid["zq"], grid["road_d"]
    X, Y = np.meshgrid(xs, ys)
    r, theta = tm.polar(X, Y)
    grade = tm.grade_field(zq)
    layer_id = tm.LAYER_ID

    # --- the design's keep-outs, as one boolean field ----------------------------------
    allowed = r >= tm.clear_radius(theta)  # clearing + the four lane runouts
    allowed &= r >= fs.EVERYTHING_KEEPOUT_R  # "r < 262 for everything"
    allowed &= road_d > fs.ROAD_KEEPOUT_M  # track ring and trail, +- 9 m
    allowed &= tm.lake_e(X, Y) >= fs.LAKE_KEEPOUT_E  # the lake
    eye, tip_a, tip_b = tm.sightline_cone()  # the S1 view of the lake
    allowed &= ~_in_triangle(X, Y, eye, tip_a, tip_b)
    for px, py in SPAWNS:
        allowed &= np.hypot(X - px, Y - py) > fs.SPAWN_KEEPOUT_M
    for px, py in CAMERA_EYES:
        allowed &= np.hypot(X - px, Y - py) > fs.CAMERA_KEEPOUT_M

    forest_floor = layers == layer_id["forest_floor"]
    meadow = layers == layer_id["meadow"]
    zones = {
        "forest_core": forest_floor & (r >= 400.0),
        "forest_edge": (r >= 350.0)
        & (r < 400.0)
        & (forest_floor | meadow | (layers == layer_id["scree"])),
        "meadow": meadow & (r >= 400.0),
        "scree_rock": (layers == layer_id["scree"]) | (layers == layer_id["rock"]),
        "alpine": layers == layer_id["alpine"],
        "shore": layers == layer_id["shore"],
    }
    # a cell belongs to exactly one zone: the first that claims it, in table order
    claimed = np.zeros_like(allowed)
    for key in [z["key"] for z in fs.ZONES]:
        zones[key] = zones[key] & allowed & ~claimed
        claimed |= zones[key]
    return {
        "xs": xs,
        "ys": ys,
        "zones": zones,
        "grade": grade,
        "allowed": allowed,
        "r": r,
        "theta": theta,
        "road_d": road_d,
        "lake_e": tm.lake_e(X, Y),
    }


def _shipped_z_extents() -> dict[str, float]:
    """{species key: the shipped DAE's own vertical extent}, from the shapes manifest.

    Two height conventions are in play and r3's report quoted one of them under the other's
    name.  `forest_spec.height_m` is the DESIGN's stated size, which `blender_forest`'s
    importer applies to the model's LONGEST axis; the shape that ships is 21 m across and
    15.07 m tall.  The Colmesh bbox the shapes manifest already records is the second
    convention, and it costs nothing to report both.
    """
    from examples.hot_potato_arena.level import forest_build

    if not forest_build.SHAPES_MANIFEST.is_file():
        return {}
    out: dict[str, float] = {}
    for key, row in forest_build.shapes_manifest()["species"].items():
        box = row.get("shape_bbox") or row.get("colmesh_bbox")
        if box:
            out[key] = float(box["max"][2]) - float(box["min"][2])
    return out


def _in_triangle(X, Y, a, b, c) -> np.ndarray:
    def side(px, py, p1, p2):
        return (px - p2[0]) * (p1[1] - p2[1]) - (p1[0] - p2[0]) * (py - p2[1])

    d1, d2, d3 = side(X, Y, a, b), side(X, Y, b, c), side(X, Y, c, a)
    negative = (d1 < 0) | (d2 < 0) | (d3 < 0)
    positive = (d1 > 0) | (d2 > 0) | (d3 > 0)
    return ~(negative & positive)


# ------------------------------------------------------------------------- Poisson sampling
class Sampler:
    """Dart-throwing with a spatial hash: one instance of a category per ``spacing`` metres."""

    def __init__(self, spacing: float) -> None:
        self.spacing = spacing
        self.cell = spacing / math.sqrt(2.0)
        self.grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
        self.squared = spacing * spacing

    def accept(self, x: float, y: float) -> bool:
        cx, cy = int(x // self.cell), int(y // self.cell)
        for i in range(cx - 2, cx + 3):
            for j in range(cy - 2, cy + 3):
                for px, py in self.grid.get((i, j), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < self.squared:
                        return False
        self.grid.setdefault((cx, cy), []).append((x, y))
        return True


_TRAIL_SAMPLES: np.ndarray | None = None


def samplable(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Is ``terrain_io.surface_z_arr`` DEFINED at (x, y)?  (the coverage law, executable)

    ``terrain_model.z_at_arr`` bilinearly interpolates the quantised grid over the cell
    ``[i, i+1] x [j, j+1]``, so it needs BOTH neighbours: the usable domain is the HALF-OPEN
    block ``[xs[0], xs[-1]) x [ys[0], ys[-1])``.  Outside it the model returns NaN -- and the
    first cut of this module wrote 195 of those NaNs straight into ``forest4.json`` as the
    bare token ``NaN``, which is not JSON at all (RFC 8259 has no such literal; ``json.loads``
    accepts it only because CPython's decoder is lenient by default).  Every one of the 195
    sat in the <= 1 m strip just outside the block, put there by ``place()``'s sub-cell
    jitter on the LAST row / column of the grid: ``xs[-1] + jitter`` is off the block, and
    ``xs[-1]`` itself is the edge plane, which is not samplable either.

    This is the analytic statement of that law, and it is re-tested on the FINAL jittered
    coordinate beside the design's own keep-outs.  ``plan_instances`` then ASSERTS that
    every authored z is finite, so the class cannot come back through another door.
    """
    grid = terrain.grid()  # r17: the painted grid, never the frozen model's directly
    xs, ys = grid["xs"], grid["ys"]
    return (x >= xs[0]) & (x < xs[-1]) & (y >= ys[0]) & (y < ys[-1])


def exact_keepout_ok(x: np.ndarray, y: np.ndarray, road_field: np.ndarray) -> np.ndarray:
    """Re-test JITTERED candidates against the analytic keep-outs, not the node mask.

    The zone masks are boolean fields on the 1 m grid and a candidate is jittered up to 1 m in
    x and y inside its cell, so a point can drift as much as sqrt(2) m across a boundary the
    node satisfied -- the first planting put 82 instances up to 2.1 m inside ``clear_radius``
    and 27 inside the trail's 9 m corridor.  Every rule of design §4.4 is therefore re-checked
    on the FINAL coordinate, with the trail's distance measured exactly (0.5 m samples) for
    the candidates the grid says are anywhere near it.
    """
    global _TRAIL_SAMPLES
    r, theta = tm.polar(x, y)
    ok = samplable(x, y)  # the coverage law -- see samplable(); nothing else may write NaN
    ok &= r >= tm.clear_radius(theta)
    ok &= r >= fs.EVERYTHING_KEEPOUT_R
    ok &= tm.lake_e(x, y) >= fs.LAKE_KEEPOUT_E
    ok &= np.abs(r - tm.TRACK_R) > fs.ROAD_KEEPOUT_M
    eye, tip_a, tip_b = tm.sightline_cone()
    ok &= ~_in_triangle(x, y, eye, tip_a, tip_b)
    for px, py in SPAWNS:
        ok &= np.hypot(x - px, y - py) > fs.SPAWN_KEEPOUT_M
    for px, py in CAMERA_EYES:
        ok &= np.hypot(x - px, y - py) > fs.CAMERA_KEEPOUT_M
    near = np.nonzero(ok & (road_field < 30.0))[0]
    if len(near):
        if _TRAIL_SAMPLES is None:
            _TRAIL_SAMPLES = np.asarray(tm.trail_samples(0.5))
        exact = np.min(
            np.hypot(
                x[near, None] - _TRAIL_SAMPLES[None, :, 0],
                y[near, None] - _TRAIL_SAMPLES[None, :, 1],
            ),
            axis=1,
        )
        ok[near] = exact > fs.ROAD_KEEPOUT_M
    return ok


def clump_priority(
    x: np.ndarray, y: np.ndarray, wavelength: float, seed: int, rng: np.random.Generator
) -> np.ndarray:
    """r9 (DEV-25): the order candidates are offered in -- stands first, glades last.

    A low-frequency value-noise field (``rock_solid.value_noise``, pure numpy, a function of
    the position and the seed) weighted ``CLUMP_WEIGHT`` against a uniform draw, so the dense
    patches fill first and the count still lands.  The uniform share keeps the glades from
    being empty of everything.
    """
    from examples.hot_potato_arena.level.rock_solid import value_noise

    field = 0.5 * (1.0 + value_noise(x / wavelength, y / wavelength, seed, octaves=3))
    return fs.CLUMP_WEIGHT * field + (1.0 - fs.CLUMP_WEIGHT) * rng.random(len(x))


def place(
    masks: dict,
    rng: np.random.Generator,
    mask: np.ndarray,
    count: int,
    sampler: Sampler,
    oversample: int = 6,
    clump: tuple[float, int] | None = None,
):
    """``count`` accepted (x, y) inside ``mask``, or as many as the mask can hold.

    ``clump`` is ``(wavelength_m, seed)``: with it the candidates are offered in the order of
    :func:`clump_priority` instead of the permutation's own, which is the whole of DEV-25.
    """
    xs, ys = masks["xs"], masks["ys"]
    rows, cols = np.nonzero(mask)
    if not len(rows):
        return np.empty(0), np.empty(0), 0
    order = rng.permutation(len(rows))
    limit = min(len(order), max(count * oversample, count + 1024))
    order = order[:limit]
    jitter_x = rng.random(len(order))
    jitter_y = rng.random(len(order))
    cand_x = xs[cols[order]] + jitter_x
    cand_y = ys[rows[order]] + jitter_y
    keep = exact_keepout_ok(cand_x, cand_y, masks["road_d"][rows[order], cols[order]])
    cand_x, cand_y = cand_x[keep], cand_y[keep]
    if clump is not None and len(cand_x):
        priority = clump_priority(cand_x, cand_y, clump[0], clump[1], rng)
        ranked = np.argsort(-priority, kind="stable")
        cand_x, cand_y = cand_x[ranked], cand_y[ranked]
    out_x, out_y = [], []
    for x, y in zip(cand_x.tolist(), cand_y.tolist(), strict=True):
        if sampler.accept(x, y):
            out_x.append(x)
            out_y.append(y)
            if len(out_x) == count:
                break
    return np.asarray(out_x), np.asarray(out_y), len(rows)


def camera_clearance_swap(xs: np.ndarray, ys: np.ndarray, mix, parts) -> np.ndarray:
    """Re-order one (zone, category) block so no shape stands inside its own footprint of an eye.

    Species are assigned AFTER the Poisson pass, as contiguous slices of the accepted points,
    so a size-aware camera keep-out looks at first like it needs a re-fill loop -- which is
    the argument r2 used to defer the fix.  It does not.  ``exact_keepout_ok`` has already
    guaranteed that EVERY accepted point clears ``CAMERA_KEEPOUT_M`` of every eye, so a point
    that is too close for a 21 m cliff is still perfectly legal for a fern.  Trading the two
    positions therefore satisfies both rules and changes no species' instance count by one.

    Returns a permutation of ``range(len(xs))``: position i of the block takes point ``perm[i]``.
    The choice is deterministic -- the violating position takes the ELIGIBLE point that is
    farthest from any eye, ties broken by index.
    """
    n = len(xs)
    perm = np.arange(n)
    if not n:
        return perm
    eye = np.min([np.hypot(xs - px, ys - py) for px, py in CAMERA_EYES], axis=0)
    need = np.empty(n)
    cursor = 0
    for (key, _), part in zip(mix, parts, strict=True):
        need[cursor : cursor + part] = fs.camera_clear_radius(fs.SPECIES_BY_KEY[key])
        cursor += part
    if not (need > fs.CAMERA_KEEPOUT_M).any():
        return perm
    for position in np.nonzero(eye[perm] < need)[0]:
        want = need[position]
        held = perm[position]
        eligible = np.nonzero((eye[perm] >= want) & (need <= eye[held]))[0]
        if not len(eligible):
            raise ValueError(
                f"camera clearance: no point in this block clears {want:.2f} m of every "
                f"truth-frame eye for the shape at position {position}"
            )
        pick = int(eligible[int(np.argmax(eye[perm[eligible]]))])
        perm[position], perm[pick] = perm[pick], perm[position]
    return perm


# ==========================================================================================
# r10 (critic B9-1): the SOLID-BODY keep-out
# ==========================================================================================
# r9 filled `cliff_outcrop_a/b` and `crag` from thin shells into closed solids -- which is what
# the user asked for -- and nothing re-ran the planter against the new bodies.  The critic
# measured the consequence on the shipped cut: 40,452 of 154,686 instances (26.2 %) rooted
# INSIDE an outcrop or crag, including 1,251 full-size firs and pines, 1,880 saplings, 1,938
# shrubs and ferns and 1,093 snags, plus ~33 k of rock inside rock.  The planter's keep-outs
# are all 2-D fields (radius, road, lake, spawn, camera); a rock body is a 3-D volume, so it
# needed a new kind of test and it did not have one.
#
# Every one of the 27 species that ships as a closed solid is now a KEEP-OUT VOLUME.  Each
# shape's finest visual mesh is rasterised once into a small local occupancy grid; each
# instance carries that grid through its own forest4 transform; and a planted point (lifted
# `SOLID_LIFT_M`, the critic's own convention so litter resting under an overhang does not
# count) that lands inside one is re-planted somewhere legal.  Counts do not change.
SOLID_LIFT_M = 0.30
#: cells per axis of a body's local occupancy grid.  40 on a 41 m crag is a 1.0 m cell and on
#: a 1.1 m pebble cluster a 2.8 cm one -- the test is conservative for the big bodies (a cell
#: counts as solid only when its CENTRE is inside), which is the right way round: it never
#: invents an interpenetration it cannot show.
OCCUPANCY_N = 48
#: side of the placement hash, metres.  The largest body is the 41 m crag.
SOLID_CELL_M = 24.0


def _mesh_occupancy(vertices: np.ndarray, faces: np.ndarray, n: int = OCCUPANCY_N) -> dict:
    """Rasterise a closed mesh into an ``n^3`` occupancy grid over its own bounding box.

    Column scanline + ray parity: for each grid column the +z ray's crossings with the mesh
    are found once, and a cell is inside when an odd number of them lie above its centre.
    """
    lo = vertices.min(axis=0)
    hi = vertices.max(axis=0)
    span = np.maximum(hi - lo, 1e-6)
    centres = (np.arange(n) + 0.5) / n
    gx, gy, gz = (lo[a] + span[a] * centres for a in (0, 1, 2))
    qx, qy = (v.ravel() for v in np.meshgrid(gx, gy, indexing="ij"))
    v0, v1, v2 = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    det = (v1[:, 1] - v2[:, 1]) * (v0[:, 0] - v2[:, 0]) + (v2[:, 0] - v1[:, 0]) * (
        v0[:, 1] - v2[:, 1]
    )
    usable = np.abs(det) > 1e-12
    diff = np.zeros((n * n, n + 1), dtype=np.int32)
    chunk = max(1, 2_000_000 // max(n * n, 1))
    for start in range(0, len(faces), chunk):
        stop = min(start + chunk, len(faces))
        keep = usable[start:stop]
        if not keep.any():
            continue
        a0, a1, a2 = v0[start:stop][keep], v1[start:stop][keep], v2[start:stop][keep]
        d = det[start:stop][keep][None, :]
        px, py = qx[:, None], qy[:, None]
        l1 = (
            (a1[:, 1] - a2[:, 1]) * (px - a2[:, 0]) + (a2[:, 0] - a1[:, 0]) * (py - a2[:, 1])
        ) / d
        l2 = (
            (a2[:, 1] - a0[:, 1]) * (px - a2[:, 0]) + (a0[:, 0] - a2[:, 0]) * (py - a2[:, 1])
        ) / d
        l3 = 1.0 - l1 - l2
        hit = (l1 >= 0.0) & (l2 >= 0.0) & (l3 >= 0.0)
        if not hit.any():
            continue
        rows, cols = np.nonzero(hit)
        z_hit = (
            l1[rows, cols] * a0[cols, 2]
            + l2[rows, cols] * a1[cols, 2]
            + l3[rows, cols] * a2[cols, 2]
        )
        bins = np.searchsorted(gz, z_hit)
        np.add.at(diff, (rows, np.zeros(len(rows), dtype=np.int64)), 1)
        np.add.at(diff, (rows, bins), -1)
    counts = np.cumsum(diff[:, :n], axis=1)
    strict = ((counts % 2) == 1).reshape(n, n, n)
    # One cell of margin, so the keep-out VOLUME contains the solid rather than approximating
    # it: a cell counts as solid when its centre is inside, which leaves a half-cell shell the
    # parity test would still call interior.  Measured against the critic's own instrument on
    # the r9 rows the strict grid reproduces 40,434 of their 40,452 point-body pairs (0.04 %,
    # an AABB edge case); the dilated one can only be larger.
    grid = strict.copy()
    grid[1:, :, :] |= strict[:-1, :, :]
    grid[:-1, :, :] |= strict[1:, :, :]
    grid[:, 1:, :] |= strict[:, :-1, :]
    grid[:, :-1, :] |= strict[:, 1:, :]
    grid[:, :, 1:] |= strict[:, :, :-1]
    grid[:, :, :-1] |= strict[:, :, 1:]
    return {"lo": lo, "span": span, "grid": grid, "strict": strict, "n": n}


def _finest_visual(dae_bytes: bytes) -> tuple[np.ndarray, np.ndarray]:
    from examples.hot_potato_arena.level import mesh_audit

    geometries = mesh_audit.geometries(dae_bytes)
    visual = [g for g in geometries if not g.startswith("Colmesh")] or list(geometries)
    name = max(visual, key=lambda g: len(geometries[g][1]))
    vertices = np.asarray(geometries[name][0], dtype=np.float64).reshape(-1, 3)
    faces = np.asarray(geometries[name][1], dtype=np.int64).reshape(-1, 3)
    return vertices, faces


def is_keep_out_body(species: dict) -> bool:
    """Is this species a CLOSED BODY WITH COLLISION, whatever built it?

    r11 (critic N-2).  Until this round the keep-out was scoped by ``species.get("solid")`` --
    a flag the CC0 model-import path sets -- so ``snag_a`` and ``snag_b`` fell through it:
    closed, manifold, SOLID by ``mesh_audit``, carrying a Colmesh, and holding **22 of the 25
    instances the critic's own widened instrument still found rooted inside a body**, six of
    them living plants growing out of a dead standing trunk.  The scope is now what it should
    always have been: a shape that is a VOLUME the car can hit.

    Conifers and card shapes are excluded by the same rule rather than by name -- their finest
    visual mesh carries foliage cards, so it is not a closed manifold and they are not volumes.
    """
    return bool(species.get("solid")) or (
        species["build"] == "snag" and bool(species.get("colmesh"))
    )


def solid_shapes(level_root: Path) -> dict[str, dict]:
    """The occupancy grid of every species that ships as a closed solid body."""
    out: dict[str, dict] = {}
    for species in fs.SPECIES:
        if not is_keep_out_body(species):
            continue
        path = level_root / fs.species_dae_relative(species)
        if not path.is_file():
            raise FileNotFoundError(
                f"{species['key']}: {path} is missing -- build the shapes before planting; "
                "the solid-body keep-out (B9-1) is measured on the shipped geometry"
            )
        vertices, faces = _finest_visual(path.read_bytes())
        out[fs.datablock_name(species)] = _mesh_occupancy(vertices, faces, OCCUPANCY_N)
    return out


class SolidField:
    """Every planted solid body as a keep-out volume, with a placement hash over the level."""

    def __init__(self, instances: dict[str, list[dict]], shapes: dict[str, dict]) -> None:
        self.bodies: list[dict] = []
        self.buckets: dict[tuple[int, int], list[int]] = {}
        self.roots: list[tuple[float, float, float]] = []
        self.root_buckets: dict[tuple[int, int], list[int]] = {}
        self._corners: dict[str, np.ndarray] = {}
        for name, shape in shapes.items():
            for order, row in enumerate(instances.get(name, ())):
                self.admit(name, order, row, shape)

    def _local_corners(self, name: str, shape: dict) -> np.ndarray:
        if name not in self._corners:
            lo, span = shape["lo"], shape["span"]
            self._corners[name] = np.array(
                [
                    [lo[0] + span[0] * i, lo[1] + span[1] * j, lo[2] + span[2] * k]
                    for i in (0, 1)
                    for j in (0, 1)
                    for k in (0, 1)
                ]
            )
        return self._corners[name]

    def _body(self, name: str, order: int, row: dict, shape: dict) -> dict:
        rotation = np.asarray(
            lean_matrix(row["yaw"], row.get("lean", 0.0), row.get("lean_az", 0.0)),
            dtype=np.float64,
        ).reshape(3, 3)
        position = np.array([row["x"], row["y"], row["z"]], dtype=np.float64)
        scale = float(row["scale"])
        world = (self._local_corners(name, shape) * scale) @ rotation + position
        return {
            "name": name,
            "index": order,
            "position": position,
            "rotation": rotation,
            "scale": scale,
            "shape": shape,
            "min": world.min(axis=0),
            "max": world.max(axis=0),
        }

    def admit(self, name: str, order: int, row: dict, shape: dict) -> None:
        """Add one placed body to the field, and remember its own root point."""
        body = self._body(name, order, row, shape)
        tag = len(self.bodies)
        self.bodies.append(body)
        for cx in range(
            int(body["min"][0] // SOLID_CELL_M), int(body["max"][0] // SOLID_CELL_M) + 1
        ):
            for cy in range(
                int(body["min"][1] // SOLID_CELL_M), int(body["max"][1] // SOLID_CELL_M) + 1
            ):
                self.buckets.setdefault((cx, cy), []).append(tag)
        root = (float(row["x"]), float(row["y"]), float(row["z"]) + SOLID_LIFT_M)
        self.roots.append(root)
        key = (int(root[0] // SOLID_CELL_M), int(root[1] // SOLID_CELL_M))
        self.root_buckets.setdefault(key, []).append(tag)

    def swallows(self, name: str, shape: dict, row: dict, skip: int) -> bool:
        """Would a body placed here contain another accepted body's own root point?

        The keep-out has to be SYMMETRIC or it is not monotone.  A rock's root sits on the
        ground at its own base, so admitting a small rock beside a big one can put the big
        one's root INSIDE the small one even though the small one's root is outside the big
        one -- measured, that left 11,905 bodies rooted inside a body after a pass that only
        looked one way, 1,400 of them the two cliff outcrops.
        """
        body = self._body(name, -1, row, shape)
        picks: list[int] = []
        for cx in range(
            int(body["min"][0] // SOLID_CELL_M), int(body["max"][0] // SOLID_CELL_M) + 1
        ):
            for cy in range(
                int(body["min"][1] // SOLID_CELL_M), int(body["max"][1] // SOLID_CELL_M) + 1
            ):
                picks.extend(self.root_buckets.get((cx, cy), ()))
        picks = [t for t in picks if t != skip]
        if not picks:
            return False
        points = np.asarray([self.roots[t] for t in picks], dtype=np.float64)
        return bool(self._hit(body, points).any())

    def _hit(self, body: dict, points: np.ndarray) -> np.ndarray:
        low, high = body["min"], body["max"]
        near = np.ones(len(points), dtype=bool)
        for axis in (0, 1, 2):
            near &= (points[:, axis] >= low[axis]) & (points[:, axis] <= high[axis])
        out = np.zeros(len(points), dtype=bool)
        if not near.any():
            return out
        local = ((points[near] - body["position"]) @ body["rotation"].T) / body["scale"]
        shape = body["shape"]
        n = shape["n"]
        cell = np.floor((local - shape["lo"]) / shape["span"] * n).astype(np.int64)
        good = np.all((cell >= 0) & (cell < n), axis=1)
        picked = np.zeros(len(local), dtype=bool)
        if good.any():
            valid = cell[good]
            picked[good] = shape["grid"][valid[:, 0], valid[:, 1], valid[:, 2]]
        out[near] = picked
        return out

    def inside(self, points: np.ndarray, owners: list[tuple[str, int]] | None = None):
        """Which lifted root points lie inside a body, and which body took each one."""
        hits = np.zeros(len(points), dtype=bool)
        host = [None] * len(points)
        if not len(points):
            return hits, host
        cells = np.stack(
            [
                np.floor(points[:, 0] / SOLID_CELL_M).astype(np.int64),
                np.floor(points[:, 1] / SOLID_CELL_M).astype(np.int64),
            ],
            axis=1,
        )
        order = np.lexsort((cells[:, 1], cells[:, 0]))
        keys = cells[order]
        starts = np.flatnonzero(
            np.r_[True, (keys[1:] != keys[:-1]).any(axis=1)] if len(keys) > 1 else [True]
        )
        stops = np.r_[starts[1:], len(keys)]
        for lo, hi in zip(starts.tolist(), stops.tolist(), strict=True):
            members = order[lo:hi]
            bucket = self.buckets.get((int(keys[lo][0]), int(keys[lo][1])))
            if not bucket:
                continue
            block = points[members]
            for tag in bucket:
                body = self.bodies[tag]
                got = self._hit(body, block)
                if not got.any():
                    continue
                for position in np.nonzero(got)[0]:
                    target = int(members[position])
                    if owners is not None and owners[target] == (body["name"], body["index"]):
                        continue  # a body is not inside itself
                    if not hits[target]:
                        hits[target] = True
                        host[target] = (body["name"], body["index"])
        return hits, host


def _flatten(instances: dict[str, list[dict]]):
    points, owners, rows = [], [], []
    for name in sorted(instances):
        for order, row in enumerate(instances[name]):
            points.append((row["x"], row["y"], row["z"] + SOLID_LIFT_M))
            owners.append((name, order))
            rows.append(row)
    return np.asarray(points, dtype=np.float64).reshape(-1, 3), owners, rows


def enforce_solid_keepout(
    instances: dict[str, list[dict]], masks: dict, level_root: Path, samplers: dict
) -> dict:
    """Move every instance that is rooted inside a solid body.  Counts are preserved.

    TWO passes, and the order is the whole of why this terminates.

    *Pass A, bodies, largest first.*  A solid body is itself a keep-out volume, so moving one
    creates keep-outs somewhere else; an unordered evict-and-replant loop chases its own tail
    (measured: 22,677 offenders in round 0 and no sign of converging after 27 minutes, because
    2,827 of the movers were the two cliff outcrops and each one buries about fourteen things
    wherever it lands).  Sorting the bodies by size and testing each only against the bodies
    ALREADY accepted makes the pass monotone: a body that has been placed is never invalidated
    by anything placed after it, because everything after it is smaller and is tested against
    it.  One pass, no iteration.

    *Pass B, everything else.*  A tree, a fern, a snag has no volume of its own, so moving one
    cannot make any other instance illegal.  One pass over the settled field finishes it.
    """
    started = time.time()
    shapes = solid_shapes(level_root)
    # Work on the numbers that will SHIP.  `forest4_records` rounds pos to 4 decimals, scale
    # to 4 and yaw/lean to 3 before `lean_matrix` sees them, so a keep-out computed at full
    # precision is not quite the keep-out a reader re-measures on the rows: measured, seven of
    # 154,686 points flipped across a body's surface on that rounding alone.  Round first and
    # the proof, the shipped file and any independent re-measure are the same arithmetic.
    for rows_of in instances.values():
        for row in rows_of:
            row["x"], row["y"], row["z"] = (round(row[k], 4) for k in ("x", "y", "z"))
            row["scale"] = round(row["scale"], 4)
            row["yaw"] = round(row["yaw"], 3)
            row["lean"] = round(row.get("lean", 0.0), 3)
            row["lean_az"] = round(row.get("lean_az", 0.0), 3)
    by_name = {fs.datablock_name(s): s for s in fs.SPECIES}
    category_of: dict[str, str] = {}
    for (_, category), mix in fs.SPECIES_MIX.items():
        for key, _weight in mix:
            category_of[fs.datablock_name(fs.SPECIES_BY_KEY[key])] = category
    zone_masks = masks["zones"]
    mask_cells: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}

    def cells_for(row: dict, name: str) -> tuple[np.ndarray, np.ndarray]:
        category = category_of[name]
        key = (row["zone"], category)
        if key not in mask_cells:
            rule = fs.PLACEMENT[category]
            mask = zone_masks[row["zone"]] & (masks["grade"] <= rule["max_grade"])
            mask_cells[key] = np.nonzero(mask)
        return mask_cells[key]

    def move(row: dict, name: str, field: SolidField, tag: str, order: int) -> bool:
        seed = hashlib.sha256(f"{fs.FOREST_SEED}:solid:{tag}:{name}:{order}".encode()).digest()
        rng = np.random.default_rng(int.from_bytes(seed[:8], "little"))
        spot = _replacement_point(
            masks,
            cells_for(row, name),
            rng,
            samplers[category_of[name]],
            field,
            by_name[name],
        )
        if spot is None:
            return False
        row["x"], row["y"], row["z"] = (round(v, 4) for v in spot)
        return True

    # ------------------------------------------------------------------ pass A: the bodies
    ranked: list[tuple[float, str, int]] = []
    for name, shape in shapes.items():
        size = float(np.linalg.norm(shape["span"]))
        for order, row in enumerate(instances.get(name, ())):
            ranked.append((-size * float(row["scale"]), name, order))
    ranked.sort()
    field = SolidField({}, shapes)  # empty; bodies are admitted one at a time
    moved_bodies, stuck_bodies = 0, 0
    inside_bodies = 0
    for _, name, order in ranked:
        row = instances[name][order]
        shape = shapes[name]

        def clear_both(spot, row=row, name=name, shape=shape) -> bool:
            trial = dict(
                row, x=round(spot[0], 4), y=round(spot[1], 4), z=round(spot[2], 4)
            )
            return not field.swallows(name, shape, trial, -1)

        probe = np.array([[row["x"], row["y"], row["z"] + SOLID_LIFT_M]])
        hit, _ = field.inside(probe)
        if hit[0] or field.swallows(name, shape, row, -1):
            inside_bodies += 1
            spot = _replacement_point(
                masks,
                cells_for(row, name),
                np.random.default_rng(
                    int.from_bytes(
                        hashlib.sha256(
                            f"{fs.FOREST_SEED}:solid:bodyA:{name}:{order}".encode()
                        ).digest()[:8],
                        "little",
                    )
                ),
                samplers[category_of[name]],
                field,
                by_name[name],
                accept=clear_both,
            )
            if spot is None:
                stuck_bodies += 1
            else:
                row["x"], row["y"], row["z"] = (round(v, 4) for v in spot)
                moved_bodies += 1
        field.admit(name, order, row, shape)
    pass_a = round(time.time() - started, 1)

    # ------------------------------------------------- pass B: everything that is not a body
    field = SolidField(instances, shapes)
    points, owners, rows = _flatten(instances)
    hits, hosts = field.inside(points, owners)
    offenders = [i for i in np.nonzero(hits)[0].tolist() if owners[i][0] not in shapes]
    before_by_species: dict[str, int] = {}
    before_by_host: dict[str, int] = {}
    for index in np.nonzero(hits)[0].tolist():
        before_by_species[owners[index][0]] = before_by_species.get(owners[index][0], 0) + 1
        host = hosts[index]
        if host is not None:
            before_by_host[host[0]] = before_by_host.get(host[0], 0) + 1
    # A body accepted early is tested only against the bodies before it, so in principle a
    # LATER, smaller body could be re-seated on top of an earlier one's root.  It has never
    # happened, but the gate would catch it, so re-seat those first and then do the plants.
    late = [i for i in np.nonzero(hits)[0].tolist() if owners[i][0] in shapes]
    for index in late:
        name, order = owners[index]
        move(rows[index], name, field, "lateB", order)
    if late:
        field = SolidField(instances, shapes)
        points, owners, rows = _flatten(instances)
        hits, hosts = field.inside(points, owners)
        offenders = [i for i in np.nonzero(hits)[0].tolist() if owners[i][0] not in shapes]
    moved_rest, stuck_rest = 0, 0
    for index in offenders:
        name, order = owners[index]
        if move(rows[index], name, field, "restB", order):
            moved_rest += 1
        else:
            stuck_rest += 1

    field = SolidField(instances, shapes)
    points, owners, _ = _flatten(instances)
    hits, hosts = field.inside(points, owners)
    left: dict[str, int] = {}
    for index in np.nonzero(hits)[0].tolist():
        left[owners[index][0]] = left.get(owners[index][0], 0) + 1
    proof = {
        "occupancy_cells": OCCUPANCY_N,
        "occupancy_margin_cells": 1,
        "lift_m": SOLID_LIFT_M,
        "solid_species": len(shapes),
        "solid_bodies": len(field.bodies),
        "pass_a_bodies_inside_a_bigger_body": inside_bodies,
        "pass_a_moved": moved_bodies,
        "pass_a_could_not_move": stuck_bodies,
        "pass_a_seconds": pass_a,
        "pass_b_inside_after_the_bodies_settled": int(hits.sum()) + moved_rest + stuck_rest,
        "pass_b_moved": moved_rest,
        "pass_b_could_not_move": stuck_rest,
        "pass_b_bodies_re_seated_late": len(late),
        "before_by_species": dict(sorted(before_by_species.items(), key=lambda kv: -kv[1])[:24]),
        "before_by_host": dict(sorted(before_by_host.items(), key=lambda kv: -kv[1])),
        "moved_total": moved_bodies + moved_rest,
        "rooted_inside_after": int(hits.sum()),
        "seconds": round(time.time() - started, 1),
    }
    if left:
        proof["after_by_species"] = dict(sorted(left.items(), key=lambda kv: -kv[1]))
    print(
        f"[forest] solid keep-out: {inside_bodies} bodies re-seated in {pass_a}s, "
        f"{len(offenders)} other instances moved, {int(hits.sum())} left inside "
        f"({proof['seconds']}s)"
    )
    return proof


def _replacement_point(masks, cells, rng, sampler, field, species, accept=None):
    """A legal new (x, y, z) for one evicted instance, or ``None``.

    Same rules as `place()` -- the analytic keep-outs, the size-aware camera clearance and the
    category's Poisson spacing -- plus the new one: the point may not be inside a solid body.
    """
    rows_idx, cols_idx = cells
    if not len(rows_idx):
        return None
    xs, ys = masks["xs"], masks["ys"]
    need = fs.camera_clear_radius(species)
    draw = 96
    for _ in range(20):
        pick = rng.integers(0, len(rows_idx), draw)
        cand_x = xs[cols_idx[pick]] + rng.random(draw)
        cand_y = ys[rows_idx[pick]] + rng.random(draw)
        keep = exact_keepout_ok(cand_x, cand_y, masks["road_d"][rows_idx[pick], cols_idx[pick]])
        cand_x, cand_y = cand_x[keep], cand_y[keep]
        if not len(cand_x):
            continue
        if need > fs.CAMERA_KEEPOUT_M:
            eye = np.min(
                [np.hypot(cand_x - px, cand_y - py) for px, py in CAMERA_EYES], axis=0
            )
            cand_x, cand_y = cand_x[eye >= need], cand_y[eye >= need]
            if not len(cand_x):
                continue
        z = np.asarray(terrain.surface_z_arr(cand_x, cand_y), dtype=np.float64)
        good = np.isfinite(z)
        cand_x, cand_y, z = cand_x[good], cand_y[good], z[good]
        if not len(cand_x):
            continue
        probe = np.stack([cand_x, cand_y, z + SOLID_LIFT_M], axis=1)
        clear, _ = field.inside(probe)
        for order in np.nonzero(~clear)[0].tolist():
            spot = (float(cand_x[order]), float(cand_y[order]), float(z[order]))
            if accept is not None and not accept(spot):
                continue
            if sampler.accept(spot[0], spot[1]):
                return spot
    return None


#: the last :func:`enforce_solid_keepout` proof, picked up by :func:`keep_out_proof`
SOLID_PROOF: dict[str, Any] = {}


def plan_instances(masks: dict, level_root: Path | None = None) -> dict[str, list[dict]]:
    """Every instance of every species, keyed by datablock name."""
    instances: dict[str, list[dict]] = {fs.datablock_name(s): [] for s in fs.SPECIES}
    samplers = {c: Sampler(fs.PLACEMENT[c]["min_spacing_m"]) for c in fs.CATEGORIES}
    report: list[dict] = []
    zone_counts = fs.zone_category_counts()
    for zone in fs.ZONES:
        for category in fs.CATEGORIES:
            wanted = zone_counts.get((zone["key"], category), 0)
            if not wanted:
                continue
            rule = fs.PLACEMENT[category]
            mask = masks["zones"][zone["key"]] & (masks["grade"] <= rule["max_grade"])
            rng = np.random.default_rng(
                int.from_bytes(
                    hashlib.sha256(f"{fs.FOREST_SEED}:{zone['key']}:{category}".encode()).digest()[
                        :8
                    ],
                    "little",
                )
            )
            clump_seed = int.from_bytes(
                hashlib.sha256(f"{fs.FOREST_SEED}:clump:{category}".encode()).digest()[:4],
                "little",
            )
            xs, ys, cells = place(
                masks,
                rng,
                mask,
                wanted,
                samplers[category],
                clump=(fs.CLUMP_WAVELENGTH_M[category], clump_seed),
            )
            mix = fs.SPECIES_MIX[(zone["key"], category)]
            parts = fs.largest_remainder(len(xs), [w for _, w in mix])
            # r3 (D7): the size-aware camera clearance, as a permutation of this block's own
            # points.  Exact counts in, exact counts out.
            perm = camera_clearance_swap(xs, ys, mix, parts)
            xs, ys = xs[perm], ys[perm]
            cursor = 0
            for (key, _), part in zip(mix, parts, strict=True):
                species = fs.SPECIES_BY_KEY[key]
                block_x = xs[cursor : cursor + part]
                block_y = ys[cursor : cursor + part]
                cursor += part
                if not len(block_x):
                    continue
                # r9 (DEV-23): the band is the family's, inside the SCALE_MIN..SCALE_MAX envelope
                band = fs.scale_band(species)
                scale = np.clip(
                    np.exp(rng.normal(0.0, fs.scale_sigma(band), len(block_x))),
                    band[0],
                    band[1],
                )
                yaw = rng.uniform(0.0, 360.0, len(block_x))
                # r9 (DEV-24): conifers and snags lean a little; everything else stays plumb
                if species["family"] in fs.LEAN_FAMILIES:
                    lean = np.minimum(
                        np.abs(rng.normal(0.0, fs.LEAN_SIGMA_DEG, len(block_x))), fs.LEAN_MAX_DEG
                    )
                    lean_az = rng.uniform(0.0, 360.0, len(block_x))
                else:
                    lean = np.zeros(len(block_x))
                    lean_az = np.zeros(len(block_x))
                z = np.asarray(terrain.surface_z_arr(block_x, block_y), dtype=np.float64)
                if not np.all(np.isfinite(z)):
                    bad = int((~np.isfinite(z)).sum())
                    raise ValueError(
                        f"{species['key']}: {bad} candidate(s) landed off the samplable block "
                        "-- surface_z is NaN there and a bare NaN is not JSON (see samplable())"
                    )
                name = fs.datablock_name(species)
                for bx, by, bz, bs, by_deg, bl, bl_az in zip(
                    block_x.tolist(),
                    block_y.tolist(),
                    z.tolist(),
                    scale.tolist(),
                    yaw.tolist(),
                    lean.tolist(),
                    lean_az.tolist(),
                    strict=True,
                ):
                    instances[name].append(
                        {
                            "x": bx,
                            "y": by,
                            "z": bz,
                            "scale": bs,
                            "yaw": by_deg,
                            "lean": bl,
                            "lean_az": bl_az,
                            "zone": zone["key"],
                        }
                    )
            report.append(
                {
                    "zone": zone["key"],
                    "category": category,
                    "wanted": wanted,
                    "placed": len(xs),
                    "mask_cells": int(cells),
                    "mask_ha": round(cells / 1e4, 2),
                    "min_spacing_m": rule["min_spacing_m"],
                    "max_grade": rule["max_grade"],
                }
            )
    if level_root is not None:
        # r10 (B9-1): the volume keep-out, after every 2-D rule has been satisfied
        SOLID_PROOF.clear()
        SOLID_PROOF.update(enforce_solid_keepout(instances, masks, level_root, samplers))
    return instances, report


def lean_matrix(yaw_deg: float, lean_deg: float, azimuth_deg: float) -> list[float]:
    """The forest4 rotationMatrix (rows = local axes in world) for a yawed, LEANING shape.

    The local up axis is tilted ``lean_deg`` toward compass ``azimuth_deg``; the local X is
    the yawed X re-projected perpendicular to it, and Y closes the right-handed frame.  At
    zero lean this is ``engine_yaw_matrix`` exactly.
    """
    from examples.hot_potato_arena.sync_scenario_outputs import engine_yaw_matrix

    if lean_deg <= 0.0:
        return engine_yaw_matrix(yaw_deg)
    theta, phi, yaw = math.radians(lean_deg), math.radians(azimuth_deg), math.radians(yaw_deg)
    z = np.array(
        [math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta)]
    )
    x = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    x = x - float(x @ z) * z
    x = x / np.linalg.norm(x)
    y = np.cross(z, x)
    return [round(float(v), 9) + 0.0 for v in (*x, *y, *z)]


def forest4_records(name: str, rows: list[dict]) -> list[dict]:
    return [
        {
            "ctxid": 0,
            "pos": [_r4(r["x"]), _r4(r["y"]), _r4(r["z"])],
            "rotationMatrix": lean_matrix(
                round(r["yaw"], 3), round(r.get("lean", 0.0), 3), round(r.get("lean_az", 0.0), 3)
            ),
            "scale": round(r["scale"], 4),
            "type": name,
        }
        for r in rows
    ]


# ------------------------------------------------------------------------------- datablocks
def forest_item_data() -> dict[str, Any]:
    document: dict[str, Any] = {}
    for species in fs.SPECIES:
        name = fs.datablock_name(species)
        record = {
            "name": name,
            "internalName": name,
            "class": "TSForestItemData",
            "persistentId": persistent_id(f"forest_item:{name}"),
            "annotation": "ROCK" if species["family"] == "rock" else "NATURE",
            "shapeFile": fs.species_shape_file(species),
            "radius": species["radius"],
            "mass": species["mass"],
            "rigidity": species["rigidity"],
            "dampingCoefficient": fs.DAMPING_COEFFICIENT,
            "tightnessCoefficient": fs.TIGHTNESS_COEFFICIENT,
            "shadowNullDetailSize": fs.SHADOW_NULL_DETAIL_SIZE,
        }
        record.update(fs.wind_fields(species))
        if species.get("snap"):
            record["snapRotationToTerrain"] = True
        document[name] = record
    return document


# -------------------------------------------------------------------------------- materials
def _stages(maps: dict[str, str]) -> list[dict]:
    return [maps, {}, {}, {}]


def foliage_material(material: dict) -> dict[str, Any]:
    name = fs.material_name(material["key"])
    kind = material.get("kind", "rock")
    maps = {
        fs.ROLE_FIELD[role]: f"/{LEVEL_RELATIVE}/{fs.texture_relative(material['key'], role)}"
        for role in fs.MATERIAL_ROLES[kind]
    }
    return {
        "name": name,
        "mapTo": name,
        "class": "Material",
        "persistentId": persistent_id(f"material:{name}"),
        "Stages": _stages(maps),
        "alphaRef": material["alphaRef"],
        "alphaTest": True,
        "annotation": "NATURE",
        "doubleSided": True,
        "groundType": material["groundType"],
        "invertBackFaceNormals": True,
        "materialTag0": "beamng",
        "materialTag1": "vegetation",
        "materialTag2": "Natural",
        "subSurface": True,
        "subSurfaceIntensity": 1,
        "translucentBlendOp": "None",
        "translucentZWrite": True,
        "version": 1.5,
    }


def rock_material(material: dict) -> dict[str, Any]:
    name = fs.material_name(material["key"])
    maps = {
        fs.ROLE_FIELD[role]: f"/{LEVEL_RELATIVE}/{fs.texture_relative(material['key'], role)}"
        for role in fs.MATERIAL_ROLES["rock"]
    }
    return {
        "name": name,
        "mapTo": name,
        "class": "Material",
        "persistentId": persistent_id(f"material:{name}"),
        "Stages": _stages(maps),
        "annotation": material["annotation"],
        "groundType": "ROCK",
        "materialTag0": "beamng",
        "materialTag1": "Natural",
        "castShadows": True,
        # r3 (D7): `doubleSided` was tried here as belt-and-braces on the shell fix and
        # REJECTED on the frame it was supposed to help.  A photogrammetry rock has interior
        # surface everywhere, and rendering both sides of it turns a crag into a pile of
        # splintered plates from ten metres.  The shell is closed in the geometry instead
        # (`blender_forest.seal_shell`) and back-face culling stays on, which is what the r2
        # crest frame's crags -- the part of it critic r2 called "good, chunky" -- already had.
        "version": 1.5,
    }


def material_documents() -> dict[str, dict[str, Any]]:
    """One ``*.materials.json`` per shape family (a material binds ``groundtype`` only where it
    lives under ``levels/<id>/art/shapes/...`` -- AGENTS.md)."""
    documents: dict[str, dict[str, Any]] = {family: {} for family in FAMILY_DIRS}
    by_dir = {directory: family for family, directory in FAMILY_DIRS.items()}
    for material in fs.MATERIALS:
        key = material["key"]
        relative = fs.texture_relative(key, "base")
        family = by_dir[relative.rsplit("/", 1)[0]]
        record = (
            rock_material(material) if material in fs.ROCK_MATERIALS else foliage_material(material)
        )
        documents[family][record["name"]] = record
    return documents


# ------------------------------------------------------------------------------ scene records
def ground_cover_records() -> list[dict[str, Any]]:
    records = []
    for index, cover in enumerate(fs.GROUND_COVERS):
        name = f"{LEVEL_ID}_{cover['name']}"
        size_min, size_max = cover["size"]
        types: list[dict[str, Any]] = []
        for slot in range(cover["types"]):
            layer = cover["layers"][slot % len(cover["layers"])]
            entry: dict[str, Any] = {
                "layer": layer,
                "probability": round(1.0 - 0.08 * slot, 3),
                "sizeMin": round(size_min * (1.0 + 0.12 * slot), 3),
                "sizeMax": round(size_max * (1.0 - 0.06 * slot), 3),
                "windScale": 0.2 if cover["kind"] == "billboard" else 0.0,
            }
            if cover["kind"] == "billboard":
                material = next(m for m in fs.MATERIALS if m["key"] == cover["material"])
                entry["billboardUVs"] = fs.billboard_uvs(
                    material["grid"], cover.get("cell_base", 0) + slot
                )
                entry["clumpRadius"] = round(0.4 + 0.35 * slot, 3)
                entry["sizeExponent"] = 1.5
                entry["minClumpCount"] = 2
                entry["maxClumpCount"] = 6
            else:
                entry["shapeFilename"] = fs.cover_shape_path(cover["shapes"][slot])
                entry["minClumpCount"] = 1
                entry["maxClumpCount"] = 5
            types.append(entry)
        record: dict[str, Any] = {
            "name": name,
            "class": "GroundCover",
            "__parent": "vegetation",
            "persistentId": persistent_id(f"cover:{name}"),
            "Types": types,
            "maxElements": cover["maxElements"],
            "radius": cover["radius"],
            "gridSize": 3 if cover["kind"] == "shape" else 6,
            "seed": fs.COVER_SEED % 1000 + index,
            "shapesCastShadows": False,
        }
        record.update(fs.COVER_WIND)
        if cover["kind"] == "billboard":
            record["material"] = fs.material_name(cover["material"])
            record["dissolveRadius"] = cover["dissolve"]
        else:
            record["shapeCullRadius"] = cover["cull"]
        records.append(record)
    return records


def wind_emitter_record() -> dict[str, Any]:
    spec = fs.WIND_EMITTER
    x, y = terrain.bearing_point(spec["bearing_deg"], spec["radius_m"])
    z = terrain.surface_z(x, y) + spec["z_offset"]
    return {
        "name": spec["name"],
        "class": "ForestWindEmitter",
        "__parent": "vegetation",
        "persistentId": persistent_id("wind"),
        "position": [_r4(x), _r4(y), _r4(z)],
        "strength": spec["strength"],
        "gustFrequency": spec["gustFrequency"],
        "gustStrength": spec["gustStrength"],
        "gustWobbleStrength": spec["gustWobbleStrength"],
        "gustYawAngle": spec["gustYawAngle"],
        "turbulenceStrength": spec["turbulenceStrength"],
        "hasMount": "0",
        "radius": spec["radius_m"],
    }


def vegetation_records() -> list[dict[str, Any]]:
    return [
        *ground_cover_records(),
        wind_emitter_record(),
        {
            "name": "theForest",
            "class": "Forest",
            "__parent": "vegetation",
            "persistentId": persistent_id("theForest"),
            "lodReflectScalar": 0,
        },
    ]


# ------------------------------------------------------------------------------------ write
def render(masks: dict | None = None, instances=None, report=None) -> tuple[dict[str, bytes], dict]:
    started = time.time()
    masks = masks or build_masks()
    if instances is None:
        instances, report = plan_instances(masks)
    outputs: dict[str, bytes] = {
        "art/forest/managedItemData.json": _json_bytes(forest_item_data()),
        "main/MissionGroup/level_objects/vegetation/items.level.json": _jsonl_bytes(
            vegetation_records()
        ),
    }
    for family, document in material_documents().items():
        outputs[f"{FAMILY_DIRS[family]}/{LEVEL_ID}_{family}.materials.json"] = _json_bytes(document)
    for name, rows in sorted(instances.items()):
        outputs[f"forest/{name}.forest4.json"] = _jsonl_bytes(forest4_records(name, rows))
    census = build_census(instances, report, masks)
    census["seconds"] = round(time.time() - started, 1)
    return outputs, census


def build_census(instances: dict[str, list[dict]], report: list[dict], masks: dict) -> dict:
    per_species = {name: len(rows) for name, rows in sorted(instances.items())}
    total = sum(per_species.values())
    by_zone: dict[str, int] = {}
    for rows in instances.values():
        for row in rows:
            by_zone[row["zone"]] = by_zone.get(row["zone"], 0) + 1
    zone_area = {z["key"]: float(masks["zones"][z["key"]].sum()) / 1e4 for z in fs.ZONES}
    return {
        "level_id": LEVEL_ID,
        "forest_seed": fs.FOREST_SEED,
        "datablocks": len(per_species),
        "instances_total": total,
        "design_total": fs.TOTAL_INSTANCES,
        "per_species": per_species,
        "per_zone": {
            k: {
                "instances": v,
                "measured_ha": round(zone_area[k], 2),
                "design_ha": next(z["design_ha"] for z in fs.ZONES if z["key"] == k),
                "per_ha_measured": round(v / zone_area[k], 1) if zone_area[k] else None,
                "per_ha_design": sum(next(z for z in fs.ZONES if z["key"] == k)["per_ha"].values()),
            }
            for k, v in sorted(by_zone.items())
        },
        "placement": report,
        "ground_covers": len(fs.GROUND_COVERS),
        "cover_elements": fs.TOTAL_COVER_ELEMENTS,
        "wind_emitters": 1,
    }


def keep_out_proof(instances: dict[str, list[dict]]) -> dict:
    """Minimum distance from ANY instance to each keep-out region -- the design's own gate.

    The track is a circle (exact in closed form) and the trail is a 875 m corner-rounded
    polyline: its distance is read from the frozen model's own ``road_distance_field`` at the
    nearest node (exact to half a cell) and then re-measured EXACTLY, against the 0.5 m-sampled
    centreline, for the 400 instances the field says are closest -- so the reported minimum is
    a true minimum, not a grid artefact.
    """
    points = np.array([[row["x"], row["y"]] for rows in instances.values() for row in rows])
    # r3 (D7): the per-instance size-aware camera clearance, in the SAME row order
    by_name = {fs.datablock_name(s): s for s in fs.SPECIES}
    need = np.array(
        [fs.camera_clear_radius(by_name[name]) for name, rows in instances.items() for _ in rows]
    )
    solid = np.array(
        [
            by_name[name]["height_m"]
            if fs.camera_clear_radius(by_name[name]) > fs.CAMERA_KEEPOUT_M
            else 0.0
            for name, rows in instances.items()
            for _ in rows
        ]
    )
    # ...and the same radius under the OTHER height convention, for the record (see below)
    z_extent = _shipped_z_extents()

    def _need_z(species: dict) -> float:
        if species["build"] != "model" or species["family"] not in fs.CAMERA_CLEAR_FAMILIES:
            return fs.CAMERA_KEEPOUT_M
        height = z_extent.get(species["key"], species["height_m"])
        return max(
            fs.CAMERA_KEEPOUT_M, fs.CAMERA_CLEAR_HEIGHT_K * height * fs.scale_band(species)[1]
        )

    need_z = np.array([_need_z(by_name[name]) for name, rows in instances.items() for _ in rows])
    x, y = points[:, 0], points[:, 1]
    r, theta = tm.polar(x, y)
    clear = tm.clear_radius(theta)
    eye, tip_a, tip_b = tm.sightline_cone()
    inside_cone = _in_triangle(x, y, eye, tip_a, tip_b)
    grid = terrain.grid()  # r17: the painted grid, never the frozen model's directly
    i = np.clip(np.rint((x - grid["xs"][0]) / tm.SQUARE).astype(int), 0, tm.N - 1)
    j = np.clip(np.rint((y - grid["ys"][0]) / tm.SQUARE).astype(int), 0, tm.N - 1)
    road_field = grid["road_d"][j, i]
    track = np.abs(r - tm.TRACK_R)
    # the grid field is a NODE reading and an instance sits up to a metre off its node, so the
    # trail distance is re-measured exactly for everything the field puts within 30 m
    near = np.nonzero(road_field < 30.0)[0]
    samples = np.asarray(tm.trail_samples(0.5))
    trail_exact = np.min(
        np.hypot(x[near, None] - samples[None, :, 0], y[near, None] - samples[None, :, 1]), axis=1
    )
    trail_all = np.full(len(x), np.inf)
    trail_all[near] = trail_exact
    road_exact = np.minimum(track, trail_all)
    lake = tm.lake_e(x, y)
    spawn = np.min([np.hypot(x - px, y - py) for px, py in SPAWNS], axis=0)
    camera = np.min([np.hypot(x - px, y - py) for px, py in CAMERA_EYES], axis=0)
    lane = np.min([np.abs(((theta - c + 180.0) % 360.0) - 180.0) for c in tm.LANE_CENTRES], axis=0)
    in_lane = lane <= tm.LANE_HALF
    grade = tm.grade_field(grid["zq"])[j, i]
    return {
        "instances": len(x),
        "min_radius_from_C_m": round(float(r.min()), 2),
        "rule_r_262_everything": {
            "limit": fs.EVERYTHING_KEEPOUT_R,
            "violations": int((r < fs.EVERYTHING_KEEPOUT_R).sum()),
        },
        "rule_clear_radius": {
            "min_margin_m": round(float((r - clear).min()), 3),
            "violations": int((r < clear).sum()),
        },
        "rule_lane_sectors_420m": {
            "violations": int((in_lane & (r < tm.LANE_CLEAR_R)).sum()),
            "min_radius_inside_a_lane_sector_m": round(float(r[in_lane].min()), 2)
            if in_lane.any()
            else None,
        },
        "rule_s1_sightline_cone": {"violations": int(inside_cone.sum())},
        "rule_road_corridor_9m": {
            "limit_m": fs.ROAD_KEEPOUT_M,
            "min_distance_to_track_centreline_m": round(float(track.min()), 3),
            "min_distance_to_trail_centreline_m": round(float(trail_exact.min()), 3),
            "min_distance_to_either_m": round(float(road_exact.min()), 3),
            "violations": int((road_exact <= fs.ROAD_KEEPOUT_M).sum()),
        },
        "rule_lake_e_1p05": {
            "min_lake_e": round(float(lake.min()), 4),
            "violations": int((lake < fs.LAKE_KEEPOUT_E).sum()),
        },
        "rule_spawn_12m": {
            "min_distance_m": round(float(spawn.min()), 2),
            "violations": int((spawn <= fs.SPAWN_KEEPOUT_M).sum()),
        },
        "rule_camera_eye_6m": {
            "min_distance_m": round(float(camera.min()), 2),
            "violations": int((camera <= fs.CAMERA_KEEPOUT_M).sum()),
        },
        "rule_camera_clearance_size_aware": {
            "k": fs.CAMERA_CLEAR_HEIGHT_K,
            "families": list(fs.CAMERA_CLEAR_FAMILIES),
            # r4 (critic r3): `height_m` is the DESIGN's stated size, and `import_model`
            # applies it to the model's LONGEST axis -- so f_cliff_outcrop_a's "21 m" is 21 m
            # across and 15.07 m tall.  The RULE keeps the larger convention (it is the
            # conservative one), but the population it touches was reported under it without
            # saying so: 24,773 by the design size, 7,537 by the shipped DAE's own z extent.
            # Both are recorded here so the number a report quotes is unambiguous.
            "height_convention": "forest_spec height_m = the design's size on the model's "
            "longest axis; z_extent = the shipped DAE's own vertical extent",
            "instances_with_a_radius_over_6m": int((need > fs.CAMERA_KEEPOUT_M).sum()),
            "instances_with_a_radius_over_6m_by_dae_z_extent": int(
                (need_z > fs.CAMERA_KEEPOUT_M).sum()
            ),
            "largest_radius_m": round(float(need.max()), 2),
            "min_margin_m": round(float((camera - need).min()), 3),
            "violations": int((camera < need).sum()),
            "worst_solid_height_over_distance": round(float((solid / camera).max()), 3),
        },
        "max_grade_at_an_instance": round(float(grade.max()), 3),
        # r10 (critic B9-1): the 3-D rule.  Empty when `plan_instances` was called without a
        # level root (no shapes to measure against) -- the gate refuses that case.
        "rule_no_instance_inside_a_solid_body": dict(SOLID_PROOF),
    }


def write(out_root: Path, manifest_path: Path) -> dict:
    outputs, census = render()
    written = []
    for relative, payload in sorted(outputs.items()):
        target = out_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != payload:
            target.write_bytes(payload)
            written.append(relative)
    census["files"] = {
        relative: {"sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}
        for relative, payload in sorted(outputs.items())
    }
    census["bytes"] = sum(len(p) for p in outputs.values())
    census["written"] = written
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(census, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return census


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--proof", type=Path, default=None, help="write the keep-out proof JSON")
    arguments = parser.parse_args(argv)
    masks = build_masks()
    instances, report = plan_instances(masks, arguments.out)
    outputs, census = render(masks, instances, report)
    proof = keep_out_proof(instances)
    census["keep_out_proof"] = proof
    for relative, payload in sorted(outputs.items()):
        target = arguments.out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    census["files"] = {
        relative: {"sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}
        for relative, payload in sorted(outputs.items())
    }
    census["bytes"] = sum(len(p) for p in outputs.values())
    arguments.manifest.parent.mkdir(parents=True, exist_ok=True)
    arguments.manifest.write_text(
        json.dumps(census, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(
        f"[forest] {census['instances_total']:,} instances of {census['datablocks']} "
        f"datablocks ({census['design_total']:,} by the design table)"
    )
    print(f"[forest] {len(outputs)} files, {census['bytes'] / 1e6:.1f} MB, {census['seconds']}s")
    print("\n  zone            instances   measured ha   per ha   design per ha")
    for key, row in census["per_zone"].items():
        print(
            f"  {key:14s} {row['instances']:>9,} {row['measured_ha']:>13.2f} "
            f"{row['per_ha_measured']:>8.1f} {row['per_ha_design']:>15}"
        )
    print("\n  zone / category      wanted   placed   mask ha")
    for row in census["placement"]:
        flag = "" if row["placed"] == row["wanted"] else "   <-- SHORT"
        print(
            f"  {row['zone']:14s} {row['category']:14s} {row['wanted']:>7,} "
            f"{row['placed']:>8,} {row['mask_ha']:>9.2f}{flag}"
        )
    print("\n  keep-out proof (min distance of any instance to each region)")
    for rule, value in proof.items():
        print(f"    {rule:28s} {value}")
    if arguments.proof is not None:
        arguments.proof.parent.mkdir(parents=True, exist_ok=True)
        arguments.proof.write_text(
            json.dumps(proof, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
