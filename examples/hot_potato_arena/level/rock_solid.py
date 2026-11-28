"""A photogrammetry FACE scan rebuilt as a closed solid: front-view heightfield + body (r9).

The three biggest B3 rocks -- ``rock_face_01`` / ``_02`` (the cliff outcrops) and
``mountainside`` (the crag) -- are scans of a cliff FACE: a sheet with an open boundary that
runs through 14-49 islands and thousands of open edges.  r3-r8 capped the sheet
(``blender_forest.close_shell``) and got a watertight shell 0.75 m thick with a convex-hull
Colmesh around it, which critic B2 pass 5 named for what it is: a facade with an invisible
wall metres in front of the visible rock (``level_facts`` 2026-09-07).  Measured with B4's
``collider_probe`` on the r8 tree: visual / Colmesh volume -0.17 / 0.05 / 0.06 on
``cliff_outcrop_a`` with a 1.54 m p90 phantom gap, -0.28 / -0.21 / -0.21 on ``_b``,
-0.45 / -0.45 / +0.39 on the crag with a 1.77 m gap (``b3/r9/rock_probe_r8.json``).

This module makes the rock a BODY.  Everything is plain numpy so it runs inside Blender's own
interpreter (no scipy there) and is a pure function of the input:

1. the scan is turned so that it faces -Y (its area-weighted normal), and rasterised from the
   front into an (x, z) grid: every cell keeps the front-most surface sample (min y);
2. the footprint is closed, its holes filled from the nearest sample, and its largest
   connected piece kept;
3. behind the front a wedge of rock: full depth at the ground, closing on the front near the
   top -- the profile of an outcrop with the mountain behind it -- with a deterministic
   integer-hash relief so the back decimates into rock, not into a plate;
4. the skirt between the front's boundary and the back's -- the walls and the underside -- is
   cut into rows and bulged outward on the same relief, and the underside is sunk below the
   scan's foot.  The first cut of this shipped the skirt as ONE ruled strip per boundary edge
   and the decimator did what a decimator does with a ruled strip: ``cliff_outcrop_a``'s top
   LOD carried 17 m2 faces at 210x its median and the crag's underside was 178 m2 in one
   plane -- exactly the plate the static gate exists to catch.  ``level_facts``: relief
   survives decimation only if it is coarser than the grain the detail ships at;
5. front grid, back grid and skirt are one closed manifold, front faces first so the caller
   can hand ONLY those the scan's own UVs.

``blender_forest.import_model`` calls :func:`solid_from_face_scan` for the species whose row
says ``solid="face"`` and then transfers the scan's UVs onto the front (nearest face,
interpolated), so the photograph stays on the rock it was taken of.
"""

from __future__ import annotations

import math

import numpy as np

#: columns across the footprint's longest axis
GRID = 180
#: body depth at the ground behind the rearmost front sample, as a share of the height.
#: r10: 0.35 -> 0.65.  At 0.35 the body is a veneer on a concave scan and the husk gate reads
#: `cliff_outcrop_a` fill 0.189 / solidity 0.567 on the shipped bytes.  Swept offline in
#: `b3/r10/face_solid_lab.py` (the builder is pure numpy, so no Blender is needed to choose),
#: then BUILT and measured on the real bytes, which is what the published numbers are:
#:      share/floor   cliff_outcrop_a      cliff_outcrop_b       crag
#:      0.35 / 0.00   0.189 / 0.567 FAIL   0.211 / 0.661 FAIL    0.367 / 0.812
#:      0.55 / 0.55   0.325 / 0.619        0.228 / 0.718         0.399 / 0.835
#:      0.65 / 0.55   0.363 / 0.634        0.255 / 0.728         0.421 / 0.849  <- shipped
DEPTH_SHARE = 0.65
#: how the depth closes toward the top: depth(z) = D x (FLOOR + (1 - FLOOR) x (1 - u^POWER)),
#: u = height share
DEPTH_POWER = 2.2
#: r10: the share of the full depth the CREST still carries.  r9 shipped no floor, so
#: depth(1) = 0 and the top of the body closed to ``MIN_THICKNESS_STEPS`` -- a knife edge.
#: `b3/r10/void_probe.py` on the r9/r10 bytes: for `cliff_outcrop_a` 93 % of the void inside
#: the convex hull lies IN FRONT of the body, and the body's share of its own hull falls from
#: 0.87 in the second tenth to **0.18 in the top tenth** -- the wedge, measured.  A floor is
#: what a real outcrop has: a crest with rock behind it.  Sweep in `b3/r10/face_solid_lab.py`.
DEPTH_FLOOR = 0.55
#: relief on the back: wavelength and amplitude as shares of the span (four octaves under
#: it, so a 21 m cliff carries 0.6 m bumps at 4 m down to 4 cm ones at 0.4 m)
BACK_RELIEF_WAVELENGTH = 0.20
BACK_RELIEF_AMPLITUDE = 0.030
#: the skirt is cut into rows about this share of the span deep...
#:
#: B7 / amendment A5 (2026-09-16, the user: "slices of bacon stacked on top of each other").
#: THE SHIPPED VALUE STANDS -- four fixes were tried and every one traded the blades for a
#: defect this level's own gates catch.  The diagnosis, kept because the next round needs it:
#: the blades are an ASPECT RATIO.  A skirt quad is one boundary edge wide
#: by one row deep.  The front grid is ``GRID`` = 180 columns across the footprint, so on a
#: 26 m rock a boundary edge is about 0.15 m, while a row at 0.05 of the span was 1.05 m --
#: a 7:1 blade, and the decimator turns a sheet of blades into longer ones still.  MEASURED
#: on the shipped bytes (`round_records/slab_probe.py`): 47.4 / 30.8 / 21.2 % of the surface
#: AREA of the three cliffs sat in triangles with an aspect over 8, their 99th-percentile
#: normal jump between neighbouring faces was 157-170 deg (a surface folding back on itself,
#: which is what reads as a dark slot), against 0.1-1.3 % and 67-111 deg for every
#: voxel-remeshed rock in the same tree.
#:
#: **D7 / amendment A7 (2026-09-17): 0.05 -> 0.008, AND the three cliffs now finish through
#: the voxel remesher (`solid="face_voxel"`).  Neither half works alone; the pair does.**
#: The user reported the same rocks a second time, from their own drive, with a screenshot:
#: "they're not water tight and they have very strange slices through them".  A5 had already
#: measured that finer rows alone are not enough (0.018 moved `cliff_outcrop_a` only 47.4 ->
#: 43.1 %, and this round reproduces 47.7 -> 30.9 % at 0.008), and that remeshing the finished
#: body alone leaves `cliff_outcrop_a` at genus 3 while a closing sweep chasing those handles
#: inflates the rock by 2.1 m.  What neither attempt saw is that THE HANDLES ARE THE ROWS: the
#: skirt's ledges sit about a metre apart, a voxel at span / 200 is 0.13 m on a 21 m rock, and
#: the remesher unions two neighbouring ledges into a tunnel.  Cut the rows to 0.008 -- about
#: 0.17 m, roughly one boundary edge, so a skirt quad is square rather than a 7:1 blade -- and
#: the remesher has almost nothing left to bridge.  MEASURED per shape at its shipped LOD
#: budgets, worst detail (`round_records/d7/`):
#:
#:      shape             sliver>8        genus  solidity  fill    bbox growth
#:      cliff_outcrop_a   0.477 -> 0.014    1     0.678    0.289    +1.15 m
#:      cliff_outcrop_b   0.326 -> 0.019    0     0.777    0.246    +0.18 m
#:      crag              0.228 -> 0.010    0     0.903    0.295    -0.44 m
#:
#: All three clear the husk gate (0.54 hard, and 0.67 solidity / 0.28 fill soft), and the
#: growth is under a metre where A5's rejected attempt moved 2.1 m -- so the re-plant this
#: revision owes the forest is a small one, not the 456-instance failure that killed it.
#: `cliff_outcrop_a` keeps ONE handle, the scan's own arch (`rock_face_01` reads genus 4 at
#: source), declared on its row as `solid_genus` -- it survives the remesher's whole closing
#: ladder, so the opening is wider than 2 x 16 voxels, about 4 m, and is real rock.
#:
#: WHAT WAS TRIED AND IS NOT WHAT SHIPS.  Routing these three through plain ``solid="voxel"``
#: cleans the blades completely but a bare face scan has no body: husk solidity 0.229 / 0.266
#: and the remesher cannot close the scan's arches (genus 4 and 15, re-measured this round).
#: RE-SOURCING them onto closed 360-degree scans -- the way B2 fixed this same defect on the
#: hearth in its r7 -- measures beautifully (`rock_07`, `rock_09`, `stone_01` all come out
#: closed, solid and in the clean band) and was REFUSED ON THE RENDERS: every one of them is a
#: squat rounded BOULDER, and at 21-41 m that is a giant pebble, not a cliff outcrop.  B2
#: could re-source because a hearth stone IS a boulder.  The scan's face is what makes these
#: read as cliffs, so the face stays and the body behind it is what changed.
SKIRT_ROW_SHARE = 0.008
#: ...and bulged OUTWARD (walls) or DOWN (underside) on relief of this wavelength and up to
#: this amplitude, both as shares of the span (four octaves under it), fading to zero at the
#: front and back edges so neither grid moves.  MEASURED: at 0.12 / 0.02 the crag's 150 px
#: detail (590 triangles on 41 m) still carried 177 m2 of its underside in one plane -- an
#: 0.8 m bump at 5 m averages out across 6 m triangles -- so the relief was made a third of
#: the span long and a twentieth of it deep.
#:
#: r10, and this is the LESSON: a relief wavelength that is a share of the SPAN is the wrong
#: unit.  `DEPTH_SHARE` 0.35 -> 0.65 (the husk fix) roughly doubled the underside without
#: changing a single LOD budget, and at 0.35 the fundamental hump on the crag is 21 m long
#: while its 150 px detail can afford 15 m2 (about 4 m) per triangle -- so a 227 m2 patch of
#: underside sat on ONE hump and decimated into TWO triangles in one plane
#: (`b3/r10/cap_probe.json`: normal (0.19, 0.02, -0.98) at 5 % of the body's height, the
#: underside).  `cliff_outcrop_a`'s 100 px detail was at 99.47 m2 against the gate's 100.
#: The fundamental must be SHORTER than the coarsest LOD's own triangles, not a share of the
#: whole body, so that no affordable triangle can straddle one hump: 0.14 of the span puts
#: the crag's fundamental at 8.4 m and its coarsest triangle at 4 m.
SKIRT_RELIEF_WAVELENGTH = 0.14
SKIRT_RELIEF_AMPLITUDE = 0.050
#: the underside is sunk below the scan's foot by this share of the span.  It is buried (the
#: planter puts the shape's z = 0 on the terrain and the front's foot IS z = 0), so nothing
#: shows; what it buys is a bottom that is a surface and not one plane.
UNDERSIDE_SINK = 0.020
#: smallest thickness kept, in grid steps (thinner cells leave the footprint)
MIN_THICKNESS_STEPS = 0.75


def _hash01(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    """A deterministic 0..1 value per integer lattice point (integer arithmetic only)."""
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (seed * 83492791)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float64) / float(0xFFFFFF)


def value_noise(x: np.ndarray, y: np.ndarray, seed: int, octaves: int = 4) -> np.ndarray:
    """Fractal value noise in -1..1 over lattice units, smoothstep-interpolated."""
    total = np.zeros_like(x, dtype=np.float64)
    amplitude, frequency, norm = 1.0, 1.0, 0.0
    for octave in range(octaves):
        px, py = x * frequency, y * frequency
        ix, iy = np.floor(px).astype(np.int64), np.floor(py).astype(np.int64)
        fx, fy = px - ix, py - iy
        sx, sy = fx * fx * (3.0 - 2.0 * fx), fy * fy * (3.0 - 2.0 * fy)
        s = seed + 977 * octave
        a = _hash01(ix, iy, s)
        b = _hash01(ix + 1, iy, s)
        c = _hash01(ix, iy + 1, s)
        d = _hash01(ix + 1, iy + 1, s)
        top = a + (b - a) * sx
        bottom = c + (d - c) * sx
        total += amplitude * ((top + (bottom - top) * sy) * 2.0 - 1.0)
        norm += amplitude
        amplitude *= 0.5
        frequency *= 2.1
    return total / norm


def _dilate(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, 1)
    out = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= padded[1 + dy : 1 + dy + mask.shape[0], 1 + dx : 1 + dx + mask.shape[1]]
    return out


def _erode(mask: np.ndarray) -> np.ndarray:
    return ~_dilate(~mask)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """Everything not reachable from the border through the complement is inside."""
    outside = np.zeros_like(mask)
    outside[0, :] = ~mask[0, :]
    outside[-1, :] = ~mask[-1, :]
    outside[:, 0] = ~mask[:, 0]
    outside[:, -1] = ~mask[:, -1]
    complement = ~mask
    for _ in range(mask.size):
        grown = _dilate(outside) & complement
        if np.array_equal(grown, outside):
            break
        outside = grown
    return ~outside


def _largest_component(mask: np.ndarray) -> np.ndarray:
    """The largest 4-connected piece of ``mask``, by min-label propagation."""
    labels = np.where(mask, np.arange(mask.size, dtype=np.int64).reshape(mask.shape) + 1, 0)
    for _ in range(mask.size):
        padded = np.pad(labels, 1, constant_values=np.iinfo(np.int64).max)
        best = labels.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            shifted = padded[1 + dy : 1 + dy + mask.shape[0], 1 + dx : 1 + dx + mask.shape[1]]
            best = np.where(mask & (shifted > 0) & (shifted < best), shifted, best)
        if np.array_equal(best, labels):
            break
        labels = best
    values, counts = np.unique(labels[mask], return_counts=True)
    if not len(values):
        return mask
    return labels == values[np.argmax(counts)]


def _fill_nearest(field: np.ndarray, known: np.ndarray, wanted: np.ndarray) -> np.ndarray:
    """Give every ``wanted`` cell without a value the mean of its nearest known neighbours."""
    out = field.copy()
    have = known.copy()
    for _ in range(field.size):
        need = wanted & ~have
        if not need.any():
            break
        padded_v = np.pad(np.where(have, out, 0.0), 1)
        padded_w = np.pad(have.astype(np.float64), 1)
        total = np.zeros_like(out)
        weight = np.zeros_like(out)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                total += padded_v[1 + dy : 1 + dy + out.shape[0], 1 + dx : 1 + dx + out.shape[1]]
                weight += padded_w[1 + dy : 1 + dy + out.shape[0], 1 + dx : 1 + dx + out.shape[1]]
        grow = need & (weight > 0)
        out[grow] = total[grow] / weight[grow]
        have |= grow
    return out


def _median3(field: np.ndarray) -> np.ndarray:
    padded = np.pad(field, 1, mode="edge")
    stack = np.stack(
        [
            padded[1 + dy : 1 + dy + field.shape[0], 1 + dx : 1 + dx + field.shape[1]]
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
        ]
    )
    return np.median(stack, axis=0)


def facing_rotation(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """A rotation about Z that turns the scan's area-weighted normal to face -Y."""
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    normals = np.cross(b - a, c - a)
    mean = normals.sum(axis=0)
    horizontal = np.array([mean[0], mean[1]])
    if np.linalg.norm(horizontal) < 1e-9:
        horizontal = np.array([0.0, -1.0])
    horizontal = horizontal / np.linalg.norm(horizontal)
    # rotate so that `horizontal` -> (0, -1)
    angle = math.atan2(-1.0, 0.0) - math.atan2(horizontal[1], horizontal[0])
    c_, s_ = math.cos(angle), math.sin(angle)
    return np.array([[c_, -s_, 0.0], [s_, c_, 0.0], [0.0, 0.0, 1.0]])


def front_depth(
    verts: np.ndarray, faces: np.ndarray, step: float, x0: float, z0: float, nx: int, nz: int
) -> tuple[np.ndarray, np.ndarray]:
    """(min y per (z, x) cell, sampled mask): the scan seen from -Y, front-most sample wins."""
    depth = np.full((nz, nx), np.inf)
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    # samples per triangle: enough that no cell inside a triangle is missed
    wanted = np.ceil(np.sqrt(np.maximum(area, 1e-12) / (step * step)) * 2.0).astype(np.int64) + 1
    wanted = np.clip(wanted, 1, 64)
    for k in np.unique(wanted):
        select = wanted == k
        ta, tb, tc = a[select], b[select], c[select]
        n = int(k)
        # a regular barycentric lattice of (n+1)(n+2)/2 points, corners included
        i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij")
        keep = i + j <= n
        u = i[keep] / n
        v = j[keep] / n
        w = 1.0 - u - v
        points = (
            ta[:, None, :] * w[None, :, None]
            + tb[:, None, :] * u[None, :, None]
            + tc[:, None, :] * v[None, :, None]
        ).reshape(-1, 3)
        ix = np.clip(np.round((points[:, 0] - x0) / step).astype(np.int64), 0, nx - 1)
        iz = np.clip(np.round((points[:, 2] - z0) / step).astype(np.int64), 0, nz - 1)
        np.minimum.at(depth, (iz, ix), points[:, 1])
    sampled = np.isfinite(depth)
    return depth, sampled


def _outward(used: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per grid vertex, the (x, z) direction pointing AWAY from the used cells around it."""
    nz, nx = used.shape
    padded = np.pad(used, 1)
    out_x = np.zeros((nz, nx))
    out_z = np.zeros((nz, nx))
    for dz in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dz == 0:
                continue
            neighbour = padded[1 + dz : 1 + dz + nz, 1 + dx : 1 + dx + nx].astype(np.float64)
            out_x -= dx * neighbour
            out_z -= dz * neighbour
    return out_x, out_z


def solid_from_face_scan(
    verts: np.ndarray,
    faces: np.ndarray,
    seed: int,
    grid: int = GRID,
    skirt_row_share: float | None = None,
    body_depth_share: float | None = None,
) -> dict:
    """Rebuild ``(verts, faces)`` -- an open face scan -- as a closed solid.

    Returns ``verts`` (V, 3), ``faces`` (F, 3) with the FRONT faces first (``front_faces``
    of them), ``rotation`` (the yaw applied to the scan, so the caller can turn its UV
    source the same way) and a few measurements for the build manifest.
    """
    rotation = facing_rotation(verts, faces)
    turned = verts @ rotation.T
    lo, hi = turned.min(axis=0), turned.max(axis=0)
    width, height = float(hi[0] - lo[0]), float(hi[2] - lo[2])
    span = max(width, height)
    step = span / float(grid)
    nx = math.ceil(width / step) + 1
    nz = math.ceil(height / step) + 1
    x0, z0 = float(lo[0]), float(lo[2])
    depth, sampled = front_depth(turned, faces, step, x0, z0, nx, nz)
    footprint = _largest_component(_fill_holes(_dilate(_dilate(sampled))))
    footprint = _erode(footprint) & _dilate(sampled)
    footprint = _largest_component(_fill_holes(footprint))
    front = _fill_nearest(np.where(sampled, depth, 0.0), sampled, footprint)
    front = np.where(footprint, front, 0.0)
    front = np.where(footprint, _median3(np.where(footprint, front, np.nan)), 0.0)
    front = np.where(np.isnan(front), 0.0, front)
    # the body: full depth at the ground, closing on the front toward the top
    rear = float(np.max(front[footprint])) if footprint.any() else float(hi[1])
    z_share = np.clip((np.arange(nz) * step) / max(height, 1e-6), 0.0, 1.0)
    # D7: a species may set its own body depth.  The husk gate reads the SHIPPED finest
    # visual LOD, and the voxel remesh that now follows this builder rounds the body off,
    # which costs fill: `cliff_outcrop_a` came out 0.649 / 0.252 against the 0.67 / 0.28
    # soft bar.  Depth is the lever that statistic is actually about -- r10 raised this
    # constant 0.35 -> 0.65 for exactly the same gate -- where the row share is not.
    depth_share = DEPTH_SHARE if body_depth_share is None else body_depth_share
    profile = (
        depth_share * height * (DEPTH_FLOOR + (1.0 - DEPTH_FLOOR) * (1.0 - z_share**DEPTH_POWER))
    )
    back = rear + profile[:, None] * np.ones((1, nx))
    gx, gz = np.meshgrid(np.arange(nx, dtype=np.float64), np.arange(nz, dtype=np.float64))
    wavelength = BACK_RELIEF_WAVELENGTH * span
    relief = value_noise(gx * step / wavelength, gz * step / wavelength, seed)
    back = back + relief * BACK_RELIEF_AMPLITUDE * span
    thickness = back - front
    thin = footprint & (thickness < MIN_THICKNESS_STEPS * step)
    footprint = footprint & ~thin
    footprint = _largest_component(footprint)
    back = np.maximum(back, front + MIN_THICKNESS_STEPS * step)
    # vertex mask -> quad faces whose four corners are inside
    inside = footprint
    quad = inside[:-1, :-1] & inside[1:, :-1] & inside[:-1, 1:] & inside[1:, 1:]
    # drop pinch quads: a quad that touches the rest only at a corner is non-manifold
    for _ in range(4):
        neighbours = np.zeros_like(quad, dtype=np.int64)
        padded = np.pad(quad, 1)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbours += padded[1 + dy : 1 + dy + quad.shape[0], 1 + dx : 1 + dx + quad.shape[1]]
        lonely = quad & (neighbours <= 1)
        if not lonely.any():
            break
        quad &= ~lonely
    used = np.zeros_like(inside)
    used[:-1, :-1] |= quad
    used[1:, :-1] |= quad
    used[:-1, 1:] |= quad
    used[1:, 1:] |= quad
    index = -np.ones((nz, nx), dtype=np.int64)
    order = np.nonzero(used)
    count = len(order[0])
    index[order] = np.arange(count)
    xs = x0 + order[1] * step
    zs = z0 + order[0] * step
    front_verts = np.stack([xs, front[order], zs], axis=1)
    back_verts = np.stack([xs, back[order], zs], axis=1)
    qz, qx = np.nonzero(quad)
    v00 = index[qz, qx]
    v10 = index[qz, qx + 1]
    v01 = index[qz + 1, qx]
    v11 = index[qz + 1, qx + 1]
    # front faces wound toward -Y (outward), back faces toward +Y
    front_faces = np.concatenate(
        [np.stack([v00, v01, v11], axis=1), np.stack([v00, v11, v10], axis=1)]
    )
    back_faces = np.concatenate(
        [
            np.stack([v00 + count, v11 + count, v01 + count], axis=1),
            np.stack([v00 + count, v10 + count, v11 + count], axis=1),
        ]
    )
    # skirt: every quad edge used by exactly one quad, cut into rows front -> back
    edges: dict[tuple[int, int], int] = {}
    walked: dict[tuple[int, int], tuple[int, int]] = {}
    for qa, qb in ((v00, v10), (v10, v11), (v11, v01), (v01, v00)):
        for ea, eb in zip(qa.tolist(), qb.tolist(), strict=True):
            key = (ea, eb) if ea < eb else (eb, ea)
            edges[key] = edges.get(key, 0) + 1
            walked.setdefault(key, (ea, eb))
    # in the quad walk's own direction, so the skirt is wound the way the grids are (both
    # inward here; the caller flips the whole solid outward once)
    boundary = [walked[key] for key, n in edges.items() if n == 1]
    # D7: a species may set its own row share.  The three cliffs are three different rocks and
    # the remesher that follows does not treat them alike -- which ledges it bridges into a
    # handle depends on the scan AND on the per-species relief seed, so the value that lands
    # `crag` and `cliff_outcrop_b` on chi 2 is not automatically the one that lands
    # `cliff_outcrop_a` there.  Measured per shape, `round_records/d7/`.
    share = SKIRT_ROW_SHARE if skirt_row_share is None else skirt_row_share
    rows = max(2, round(depth_share * height / (share * span)))
    ring = np.array(sorted({v for edge in boundary for v in edge}), dtype=np.int64)
    out_x, out_z = _outward(used)
    ox = out_x[order[0][ring], order[1][ring]]
    oz = out_z[order[0][ring], order[1][ring]]
    norm = np.hypot(ox, oz)
    centre_x, centre_z = float(xs.mean()), float(zs.mean())
    fallback_x, fallback_z = xs[ring] - centre_x, zs[ring] - centre_z
    fallback_norm = np.maximum(np.hypot(fallback_x, fallback_z), 1e-9)
    ox = np.where(norm > 1e-9, ox / np.maximum(norm, 1e-9), fallback_x / fallback_norm)
    oz = np.where(norm > 1e-9, oz / np.maximum(norm, 1e-9), fallback_z / fallback_norm)
    f = front_verts[ring]
    b = back_verts[ring]
    local_depth = b[:, 1] - f[:, 1]
    amplitude = np.minimum(SKIRT_RELIEF_AMPLITUDE * span, 0.5 * local_depth)
    underside = oz < -0.7
    sink = np.where(underside, UNDERSIDE_SINK * span, 0.0)
    t = (np.arange(1, rows, dtype=np.float64) / rows)[None, :]  # (1, rows - 1)
    fade = np.sin(math.pi * t)
    points = f[:, None, :] + (b - f)[:, None, :] * t[:, :, None]
    skirt_wavelength = SKIRT_RELIEF_WAVELENGTH * span
    u = (points[:, :, 0] + points[:, :, 2]) / skirt_wavelength
    v = (points[:, :, 1] + 0.37 * (points[:, :, 0] - points[:, :, 2])) / skirt_wavelength
    bump = 0.5 * (1.0 + value_noise(u, v, seed + 4241)) * amplitude[:, None] * fade
    points[:, :, 0] += ox[:, None] * bump
    points[:, :, 2] += oz[:, None] * bump - sink[:, None] * fade
    chain_start = 2 * count + np.arange(len(ring)) * (rows - 1)
    chain_of = {int(vertex): int(start) for vertex, start in zip(ring, chain_start, strict=True)}

    def chain(vertex: int) -> list[int]:
        start = chain_of[vertex]
        return [vertex, *range(start, start + rows - 1), vertex + count]

    skirt = []
    for ea, eb in boundary:
        ca, cb = chain(ea), chain(eb)
        for k in range(rows):
            skirt.append([ca[k], cb[k], cb[k + 1]])
            skirt.append([ca[k], cb[k + 1], ca[k + 1]])
    skirt_faces = np.asarray(skirt, dtype=np.int64).reshape(-1, 3)
    all_verts = np.concatenate([front_verts, back_verts, points.reshape(-1, 3)])
    all_faces = np.concatenate([front_faces, back_faces, skirt_faces])
    # turn back into the scan's frame
    all_verts = all_verts @ rotation
    return {
        "verts": all_verts,
        "faces": all_faces,
        "front_faces": len(front_faces),
        "rotation": rotation,
        "step_m": step,
        "grid": [int(nx), int(nz)],
        "footprint_cells": int(footprint.sum()),
        "sampled_cells": int(sampled.sum()),
        "depth_m": float(depth_share * height),
        "boundary_edges": len(boundary),
        "skirt_rows": rows,
        "underside_sink_m": round(float(UNDERSIDE_SINK * span), 4),
        "scan_foot_z": z0,
    }


def signed_volume(verts: np.ndarray, faces: np.ndarray) -> float:
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def edge_census(faces: np.ndarray) -> tuple[int, int]:
    """(boundary edges, non-manifold edges) of a triangle list."""
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e = np.sort(e, axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return int((counts == 1).sum()), int((counts > 2).sum())
