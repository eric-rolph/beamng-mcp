"""Is the collider the shape the player SEES?  Volume ratio and the phantom gap, by ray.

``mesh_audit`` answers "is every shell closed?".  Critic B2 pass 5 then proved that closed is
not enough: ``h_rock_face_01`` is a watertight shell a median 0.75 m thick enclosing 2-5 % of
its own Colmesh, and that Colmesh -- the shell's convex hull -- puts an invisible wall a median
3.5 m (max 14.7 m) in front of the visible rock.  The law admitted from it (``level_facts``,
2026-09-07): *a photogrammetry "face" scan wrapped on a proxy is a facade even when watertight*,
and the gate adopted with it, for every rock-class shape:

* **visual volume / Colmesh volume >= 0.5** (the five solid hearth stones read 0.52-0.89);
* **LOD parity** -- every detail level tells the same story as the finest one;
* **a phantom-gap statistic**: the ray distance from the Colmesh hit to the visual hit,
  p50 / p90 / max, which for a solid should be about zero.

B4 was told to prove its props pass it.  This module is that instrument, and the static gate
in ``tests/test_hot_potato_props.py`` imports it, so the two cannot disagree.

Two things a volume ratio alone gets wrong on props, and how the ray statistic handles them:

* a HOLLOW shape (the enamel pot: an open vessel whose visual encloses only its wall
  material) reads a low ratio against the solid cylinder that stops a car at its rim, yet has
  no phantom wall anywhere a car can reach.  The ray band below is cast horizontally at CAR
  heights from outside, which is the only geometry a player meets;
* a THIN shape (a fence post against a box collider) reads a low ratio for the honest reason
  that a box is not an octagon; its phantom gap is centimetres.  A ray that hits the collider
  and then finds NO visual behind it ("collider-only") is charged the distance from the
  collider hit to the nearest visual surface, so an invisible wall with nothing behind it is
  measured and not excused.

Rays are Moller-Trumbore in numpy, batched; the meshes come from ``mesh_audit.geometries``.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from examples.hot_potato_arena.level import mesh_audit

#: heights above the collider's base at which the car band is cast: a road car's bumper,
#: sill, bonnet and roof line
CAR_BAND_HEIGHTS_M = (0.30, 0.60, 1.00, 1.50)
#: azimuth step of the horizontal fan, degrees
CAR_BAND_AZIMUTH_STEP_DEG = 5.0
#: aim points spread along the shape's long horizontal axis, so a 100 m log is probed along
#: its whole length and not only at its middle
CAR_BAND_TARGETS = 9
#: directions of the all-round fan (a Fibonacci sphere), information only -- it includes the
#: top of an open pot and the underside a car never sees
SPHERE_RAYS = 600


def _arrays(positions: list[tuple[float, float, float]], tris: list[tuple[int, int, int]]):
    verts = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
    faces = np.asarray(tris, dtype=np.int64).reshape(-1, 3)
    return verts, faces


def signed_volume(verts: np.ndarray, faces: np.ndarray) -> float:
    """Divergence-theorem volume; positive for an outward-wound closed shell."""

    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def first_hit(
    origins: np.ndarray, directions: np.ndarray, verts: np.ndarray, faces: np.ndarray
) -> np.ndarray:
    """Distance along each ray to its first triangle, ``inf`` where it misses."""

    v0 = verts[faces[:, 0]]
    e1 = verts[faces[:, 1]] - v0
    e2 = verts[faces[:, 2]] - v0
    out = np.full(len(origins), np.inf)
    # batch rays so the (rays x triangles x 3) intermediates stay a few tens of MB
    chunk = max(1, int(6_000_000 // max(1, len(faces))))
    for start in range(0, len(origins), chunk):
        o = origins[start : start + chunk]
        d = directions[start : start + chunk]
        p = np.cross(d[:, None, :], e2[None, :, :])
        det = np.einsum("tj,rtj->rt", e1, p)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = o[:, None, :] - v0[None, :, :]
        u = np.einsum("rtj,rtj->rt", s, p) * inv
        q = np.cross(s, e1[None, :, :])
        v = np.einsum("rj,rtj->rt", d, q) * inv
        t = np.einsum("tj,rtj->rt", e2, q) * inv
        hit = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1.0 + 1e-9) & (t > 1e-6)
        t = np.where(hit, t, np.inf)
        out[start : start + chunk] = t.min(axis=1)
    return out


def car_band_rays(verts: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """A horizontal fan at car heights, from outside, aimed along the shape's long axis."""

    lo = verts.min(axis=0)
    hi = verts.max(axis=0)
    extent = hi - lo
    centre = (lo + hi) / 2.0
    along = 0 if extent[0] >= extent[1] else 1
    reach = 0.75 * float(max(extent[0], extent[1])) + 3.0
    span = 0.9 * float(extent[along])
    targets = np.linspace(-span / 2.0, span / 2.0, CAR_BAND_TARGETS) if span > 0.5 else [0.0]
    height = float(extent[2])
    heights = [h for h in CAR_BAND_HEIGHTS_M if h < height - 0.02] or [height / 2.0]
    azimuths = np.radians(np.arange(0.0, 360.0, CAR_BAND_AZIMUTH_STEP_DEG))
    origins = []
    directions = []
    for h in heights:
        z = float(lo[2]) + h
        for offset in targets:
            target = centre.copy()
            target[along] += offset
            target[2] = z
            for a in azimuths:
                direction = np.array([-math.cos(a), -math.sin(a), 0.0])
                origins.append(target - direction * reach)
                directions.append(direction)
    meta = {
        "heights_above_base_m": heights,
        "aim_points": len(targets),
        "azimuth_step_deg": CAR_BAND_AZIMUTH_STEP_DEG,
        "reach_m": round(reach, 3),
        "bbox_m": [round(float(e), 3) for e in extent],
    }
    return np.asarray(origins), np.asarray(directions), meta


def sphere_rays(verts: np.ndarray, count: int = SPHERE_RAYS) -> tuple[np.ndarray, np.ndarray]:
    """Rays from a sphere around the shape, aimed at its centre, all directions."""

    lo = verts.min(axis=0)
    hi = verts.max(axis=0)
    centre = (lo + hi) / 2.0
    radius = 0.6 * float(np.linalg.norm(hi - lo)) + 3.0
    golden = math.pi * (3.0 - math.sqrt(5.0))
    directions = []
    for i in range(count):
        y = 1.0 - 2.0 * (i + 0.5) / count
        r = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden * i
        directions.append([r * math.cos(theta), y, r * math.sin(theta)])
    d = np.asarray(directions)
    return centre[None, :] + d * radius, -d


def nearest_surface_distance(
    points: np.ndarray, verts: np.ndarray, faces: np.ndarray
) -> np.ndarray:
    """Distance from each point to the closest point on the mesh's SURFACE.

    Ericson's closest-point-on-triangle (Real-Time Collision Detection 5.1.5), vectorised
    over triangles per block of points; the Voronoi regions are exclusive, so the seven
    ``where`` passes may run in any order.  A vertex-only proxy is wrong on exactly the
    shapes that matter here: a 2-ring post has vertices only at its ends, so a collider hit
    1 cm from its side read "1.0 m from the nearest vertex".
    """

    if len(points) == 0:
        return np.zeros(0)
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    ab, ac, bc = b - a, c - a, c - b
    out = np.empty(len(points))
    block = max(1, int(400_000 // max(1, len(faces))))

    def safe(x: np.ndarray) -> np.ndarray:
        return np.where(np.abs(x) < 1e-30, 1e-30, x)

    for i in range(0, len(points), block):
        p = points[i : i + block][:, None, :]
        ap, bp, cp = p - a[None], p - b[None], p - c[None]
        d1 = np.einsum("ptj,tj->pt", ap, ab)
        d2 = np.einsum("ptj,tj->pt", ap, ac)
        d3 = np.einsum("ptj,tj->pt", bp, ab)
        d4 = np.einsum("ptj,tj->pt", bp, ac)
        d5 = np.einsum("ptj,tj->pt", cp, ab)
        d6 = np.einsum("ptj,tj->pt", cp, ac)
        vc, vb, va = d1 * d4 - d3 * d2, d5 * d2 - d1 * d6, d3 * d6 - d5 * d4
        denom = safe(va + vb + vc)
        v, w = vb / denom, vc / denom
        q = a[None] + ab[None] * v[..., None] + ac[None] * w[..., None]  # inside the face
        t = np.clip((d4 - d3) / safe((d4 - d3) + (d5 - d6)), 0.0, 1.0)
        m = (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0)  # edge bc
        q = np.where(m[..., None], b[None] + bc[None] * t[..., None], q)
        t = np.clip(d2 / safe(d2 - d6), 0.0, 1.0)
        m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)  # edge ac
        q = np.where(m[..., None], a[None] + ac[None] * t[..., None], q)
        t = np.clip(d1 / safe(d1 - d3), 0.0, 1.0)
        m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)  # edge ab
        q = np.where(m[..., None], a[None] + ab[None] * t[..., None], q)
        m = (d6 >= 0) & (d5 <= d6)  # vertex c
        q = np.where(m[..., None], np.broadcast_to(c[None], q.shape), q)
        m = (d3 >= 0) & (d4 <= d3)  # vertex b
        q = np.where(m[..., None], np.broadcast_to(b[None], q.shape), q)
        m = (d1 <= 0) & (d2 <= 0)  # vertex a
        q = np.where(m[..., None], np.broadcast_to(a[None], q.shape), q)
        out[i : i + block] = np.sqrt(((p - q) ** 2).sum(axis=2)).min(axis=1)
    return out


def gap_statistics(
    origins: np.ndarray,
    directions: np.ndarray,
    visual: tuple[np.ndarray, np.ndarray],
    collider: tuple[np.ndarray, np.ndarray],
) -> dict[str, Any]:
    """How far in front of the visible surface the collider stops a ray, over a ray set.

    For every ray the COLLIDER stops before anything visible (the visual hit is further
    along, or there is none), the phantom is the PERPENDICULAR distance from that collider
    hit to the nearest point of the visual surface -- how far out the invisible wall stands.
    The along-ray difference is kept beside it for information only: on a grazing ray a
    3 cm radial step reads as metres along the ray, which is a fact about the ray, not the
    wall.  Where the visual is hit first, the collider is INSIDE it (bark a wheel drives into)
    and that depth is reported as relief.
    """

    t_vis = first_hit(origins, directions, *visual)
    t_col = first_hit(origins, directions, *collider)
    col_hit = np.isfinite(t_col)
    vis_hit = np.isfinite(t_vis)
    proud = col_hit & (t_col < t_vis)  # t_vis is inf where the visual is never hit
    hits = origins[proud] + directions[proud] * t_col[proud][:, None]
    phantom = nearest_surface_distance(hits, *visual)
    along = (t_vis - t_col)[proud & vis_hit]
    relief = (t_col - t_vis)[vis_hit & col_hit & (t_vis < t_col)]

    def q(values: np.ndarray, pct: float) -> float | None:
        return round(float(np.percentile(values, pct)), 4) if len(values) else None

    # the worst rays, so a reader can find WHERE a collider stands proud, not only how far
    worst: list[dict[str, Any]] = []
    if proud.any():
        idx = np.flatnonzero(proud)
        for k in np.argsort(phantom)[::-1][:5]:
            if phantom[k] <= 0.01:
                break
            i = idx[k]
            worst.append(
                {
                    "phantom_m": round(float(phantom[k]), 3),
                    "collider_hit": [round(float(c), 2) for c in hits[k]],
                    "direction": [round(float(c), 3) for c in directions[i]],
                    "visual_behind_it": bool(vis_hit[i]),
                }
            )

    return {
        "worst_rays": worst,
        "rays": len(origins),
        "hit_both": int((col_hit & vis_hit).sum()),
        "collider_first": int(proud.sum()),
        "collider_only": int((col_hit & ~vis_hit).sum()),
        "visual_only": int((vis_hit & ~col_hit).sum()),
        "missed_both": int((~col_hit & ~vis_hit).sum()),
        "phantom_p50_m": q(phantom, 50),
        "phantom_p90_m": q(phantom, 90),
        "phantom_max_m": round(float(phantom.max()), 4) if len(phantom) else None,
        "phantom_over_10cm": int((phantom > 0.10).sum()),
        "phantom_over_25cm": int((phantom > 0.25).sum()),
        "along_ray_p90_m": q(along, 90),
        "along_ray_max_m": round(float(along.max()), 4) if len(along) else None,
        "relief_p90_m": q(relief, 90),
        "relief_max_m": round(float(relief.max()), 4) if len(relief) else None,
    }


def probe_dae(name: str, payload: bytes) -> dict[str, Any]:
    """Every visual detail of one DAE against its Colmesh: volumes, ratios, phantom gaps."""

    geoms = mesh_audit.geometries(payload)
    collider_name = next((g for g in geoms if g.startswith("Colmesh_")), None)
    if collider_name is None:
        return {"file": name, "has_colmesh": False, "details": {}, "verdict": "NO COLMESH"}
    col_verts, col_faces = _arrays(*geoms[collider_name])
    col_volume = signed_volume(col_verts, col_faces)
    origins, directions, band_meta = car_band_rays(col_verts)
    sphere_o, sphere_d = sphere_rays(col_verts)
    details: dict[str, Any] = {}
    finest = max((g for g in geoms if g != collider_name), key=lambda g: len(geoms[g][1]))
    for gid, (positions, tris) in geoms.items():
        if gid == collider_name:
            continue
        verts, faces = _arrays(positions, tris)
        volume = signed_volume(verts, faces)
        row: dict[str, Any] = {
            "tris": len(faces),
            "visual_volume_m3": round(volume, 4),
            "volume_ratio_visual_over_colmesh": round(volume / col_volume, 4)
            if col_volume
            else None,
            "car_band": gap_statistics(origins, directions, (verts, faces), (col_verts, col_faces)),
        }
        if gid == finest:
            row["all_round"] = gap_statistics(
                sphere_o, sphere_d, (verts, faces), (col_verts, col_faces)
            )
        details[gid] = row
    ratios = [d["volume_ratio_visual_over_colmesh"] for d in details.values()]
    return {
        "file": name,
        "has_colmesh": True,
        "colmesh": collider_name,
        "colmesh_tris": len(col_faces),
        "colmesh_volume_m3": round(col_volume, 4),
        "finest_detail": finest,
        "car_band": band_meta,
        "details": details,
        "volume_ratio_min": round(min(ratios), 4) if ratios else None,
        "volume_ratio_max": round(max(ratios), 4) if ratios else None,
        "lod_parity_ratio_spread": round(max(ratios) - min(ratios), 4) if ratios else None,
        "car_band_phantom_p90_max_over_details_m": max(
            (d["car_band"]["phantom_p90_m"] or 0.0) for d in details.values()
        )
        if details
        else None,
        "car_band_phantom_max_over_details_m": max(
            (d["car_band"]["phantom_max_m"] or 0.0) for d in details.values()
        )
        if details
        else None,
    }
