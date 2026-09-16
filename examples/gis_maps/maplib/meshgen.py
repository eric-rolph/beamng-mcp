"""Procedural rock, tree and shrub meshes written as Collada 1.4.1 for BeamNG.

No Blender in the loop: every vertex is computed here from a seed, and the DAE is laid
out the way Blender's exporter lays out the shapes this repository already ships
(``examples/cannon_car_wash``): Z-up metres, one ``<geometry>`` per mesh with
POSITION/NORMAL/TEXCOORD sources, ``<node type="NODE">`` instances with a
``<matrix sid="transform">``, ``<bind_material>`` on visible meshes, and collision-only
meshes as nodes named exactly ``Colmesh-N`` (the only name the engine treats as
invisible collision; see AGENTS.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np


@dataclass
class Mesh:
    name: str
    positions: np.ndarray  # (N, 3)
    normals: np.ndarray  # (N, 3)
    uvs: np.ndarray  # (N, 2)
    triangles: np.ndarray  # (M, 3) int
    material: str | None = None  # None => collision-only (node must be Colmesh-N)
    node_name: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def triangle_count(self) -> int:
        return int(self.triangles.shape[0])


# ---------------------------------------------------------------------------
# Noise
# ---------------------------------------------------------------------------


def _hash3(ix: np.ndarray, iy: np.ndarray, iz: np.ndarray, seed: int) -> np.ndarray:
    """Deterministic 0..1 hash of integer lattice coordinates."""

    h = (
        ix.astype(np.int64) * 374761393
        + iy.astype(np.int64) * 668265263
        + iz.astype(np.int64) * 2147483647
        + int(seed) * 982451653
    ) & 0x7FFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0x7FFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF) / float(0xFFFFFF)


def value_noise3(p: np.ndarray, seed: int) -> np.ndarray:
    """Smooth value noise in -1..1 at points ``p`` (N, 3)."""

    i = np.floor(p)
    f = p - i
    f = f * f * (3.0 - 2.0 * f)
    ix, iy, iz = i[:, 0].astype(np.int64), i[:, 1].astype(np.int64), i[:, 2].astype(np.int64)
    out = np.zeros(p.shape[0])
    for dx in (0, 1):
        wx = f[:, 0] if dx else 1.0 - f[:, 0]
        for dy in (0, 1):
            wy = f[:, 1] if dy else 1.0 - f[:, 1]
            for dz in (0, 1):
                wz = f[:, 2] if dz else 1.0 - f[:, 2]
                out += wx * wy * wz * _hash3(ix + dx, iy + dy, iz + dz, seed)
    return out * 2.0 - 1.0


def fbm3(p: np.ndarray, seed: int, octaves: int = 4, lacunarity: float = 2.0, gain: float = 0.5):
    total = np.zeros(p.shape[0])
    amp = 1.0
    norm = 0.0
    q = p.copy()
    for octave in range(octaves):
        total += amp * value_noise3(q, seed + 17 * octave)
        norm += amp
        amp *= gain
        q = q * lacunarity + 11.7
    return total / norm


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def icosphere(subdivisions: int) -> tuple[np.ndarray, np.ndarray]:
    t = (1.0 + math.sqrt(5.0)) / 2.0
    verts = np.array(
        [
            [-1, t, 0],
            [1, t, 0],
            [-1, -t, 0],
            [1, -t, 0],
            [0, -1, t],
            [0, 1, t],
            [0, -1, -t],
            [0, 1, -t],
            [t, 0, -1],
            [t, 0, 1],
            [-t, 0, -1],
            [-t, 0, 1],
        ],
        dtype="float64",
    )
    verts /= np.linalg.norm(verts, axis=1, keepdims=True)
    faces = np.array(
        [
            [0, 11, 5],
            [0, 5, 1],
            [0, 1, 7],
            [0, 7, 10],
            [0, 10, 11],
            [1, 5, 9],
            [5, 11, 4],
            [11, 10, 2],
            [10, 7, 6],
            [7, 1, 8],
            [3, 9, 4],
            [3, 4, 2],
            [3, 2, 6],
            [3, 6, 8],
            [3, 8, 9],
            [4, 9, 5],
            [2, 4, 11],
            [6, 2, 10],
            [8, 6, 7],
            [9, 8, 1],
        ],
        dtype="int64",
    )
    for _ in range(subdivisions):
        verts, faces = _subdivide(verts, faces)
    return verts, faces


def _subdivide(verts: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    cache: dict[tuple[int, int], int] = {}
    verts_list = list(verts)

    def midpoint(a: int, b: int) -> int:
        key = (min(a, b), max(a, b))
        if key in cache:
            return cache[key]
        m = (verts_list[a] + verts_list[b]) / 2.0
        m /= np.linalg.norm(m)
        verts_list.append(m)
        cache[key] = len(verts_list) - 1
        return cache[key]

    new_faces = []
    for a, b, c in faces:
        ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
        new_faces += [[a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]]
    return np.asarray(verts_list), np.asarray(new_faces, dtype="int64")


def vertex_normals(positions: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    a = positions[triangles[:, 0]]
    b = positions[triangles[:, 1]]
    c = positions[triangles[:, 2]]
    face_n = np.cross(b - a, c - a)
    normals = np.zeros_like(positions)
    for k in range(3):
        np.add.at(normals, triangles[:, k], face_n)
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    length[length == 0] = 1.0
    return normals / length


def spherical_uv(positions: np.ndarray, repeat: float = 2.0) -> np.ndarray:
    p = positions - positions.mean(axis=0)
    r = np.linalg.norm(p, axis=1)
    r[r == 0] = 1.0
    u = (np.arctan2(p[:, 1], p[:, 0]) / (2 * math.pi) + 0.5) * repeat
    v = (np.arccos(np.clip(p[:, 2] / r, -1, 1)) / math.pi) * repeat
    return np.stack([u, v], axis=1)


def _quad(p0, p1, p2, p3, uv0=(0, 0), uv1=(1, 0), uv2=(1, 1), uv3=(0, 1)):
    """Two triangles for a quad given counter-clockwise corners."""

    positions = np.array([p0, p1, p2, p3], dtype="float64")
    uvs = np.array([uv0, uv1, uv2, uv3], dtype="float64")
    tris = np.array([[0, 1, 2], [0, 2, 3]], dtype="int64")
    return positions, uvs, tris


def _concat(parts: list[tuple[np.ndarray, np.ndarray, np.ndarray]]):
    positions, uvs, tris = [], [], []
    offset = 0
    for p, u, t in parts:
        positions.append(p)
        uvs.append(u)
        tris.append(t + offset)
        offset += p.shape[0]
    return np.concatenate(positions), np.concatenate(uvs), np.concatenate(tris)


# ---------------------------------------------------------------------------
# Rocks
# ---------------------------------------------------------------------------


def _clip_planes(rng: np.random.Generator, count: int) -> list[tuple[np.ndarray, float]]:
    planes = []
    for _ in range(count):
        normal = rng.normal(size=3)
        normal /= np.linalg.norm(normal)
        planes.append((normal, float(rng.uniform(0.62, 0.92))))
    return planes


def _clip(points: np.ndarray, planes: list[tuple[np.ndarray, float]]) -> np.ndarray:
    out = points.copy()
    for normal, offset in planes:
        distance = out @ normal - offset
        outside = distance > 0
        out[outside] -= distance[outside, None] * normal[None, :]
    return out


def rock_meshes(
    seed: int,
    size_xyz: tuple[float, float, float],
    *,
    subdivisions: int = 3,
    angular: float = 0.5,
    material: str = "rock",
    name: str = "rock",
) -> list[Mesh]:
    """A boulder ``size_xyz`` metres across (full extents), plus its Colmesh.

    The shape is an icosphere displaced by 3-D fbm (large lobes) and a ridged
    component (facets, weighted by ``angular``), then squashed to the requested
    extents and given a slightly flattened base so it sits in the ground instead of
    balancing on a point.
    """

    verts, faces = icosphere(subdivisions)
    rng = np.random.default_rng(seed)
    offset = rng.uniform(-50, 50, size=3)
    q = verts * 1.6 + offset
    lobes = fbm3(q, seed, octaves=3)
    ridged = 1.0 - np.abs(fbm3(q * 2.7 + 3.1, seed + 101, octaves=3))
    fine = fbm3(q * 6.0, seed + 202, octaves=2)
    radius = 1.0 + 0.18 * lobes + angular * 0.22 * (ridged - 0.5) + 0.05 * fine
    p = verts * radius[:, None]
    # Talus is broken rock: clip with a few random planes so the block has facets and
    # edges, then a flat base plane so it sits in the ground.
    planes = _clip_planes(rng, int(5 + angular * 3))
    p = _clip(p, planes)
    # A flat base: everything below the cut plane lands on it, so the block sits on the
    # ground on a face (a third of its vertices) instead of balancing on a point.
    p[:, 2] = np.maximum(p[:, 2], -0.5)
    extent = p.max(axis=0) - p.min(axis=0)
    p = (p - (p.max(axis=0) + p.min(axis=0)) / 2.0) / extent * np.asarray(size_xyz)
    p[:, 2] -= p[:, 2].min()  # base on z = 0
    uvs = spherical_uv(p, repeat=2.0)
    # Flat shading: every triangle owns its vertices so the facets read as facets.
    flat_p = p[faces].reshape(-1, 3)
    flat_uv = uvs[faces].reshape(-1, 2)
    flat_faces = np.arange(flat_p.shape[0], dtype="int64").reshape(-1, 3)
    face_n = np.cross(p[faces[:, 1]] - p[faces[:, 0]], p[faces[:, 2]] - p[faces[:, 0]])
    face_n /= np.maximum(np.linalg.norm(face_n, axis=1, keepdims=True), 1e-9)
    flat_n = np.repeat(face_n, 3, axis=0)
    # The top of a block is a bedding plane: faces within 30 degrees of level take
    # a planar map inside one bed (u across the block, v held near one row), so
    # the texture's beds never close into rings on a domed top.
    top = np.repeat(face_n[:, 2] > math.cos(math.radians(30.0)), 3)
    if top.any():
        ext = np.maximum(p.max(axis=0) - p.min(axis=0), 1e-6)
        rel = (flat_p - p.min(axis=0)) / ext
        flat_uv[top, 0] = rel[top, 0] * 2.0
        flat_uv[top, 1] = 0.5 + 0.06 * rel[top, 1]
    visible = Mesh(
        f"{name}_mesh", flat_p, flat_n, flat_uv, flat_faces, material=material, node_name=name
    )
    cverts, cfaces = icosphere(max(1, subdivisions - 2))
    # Reuse the same displacement field at the coarser resolution for the collider.
    cq = cverts * 1.6 + offset
    cr = (
        1.0
        + 0.28 * fbm3(cq, seed, octaves=3)
        + angular * 0.22 * (1.0 - np.abs(fbm3(cq * 2.7 + 3.1, seed + 101, octaves=3)) - 0.5)
    )
    cp = cverts * cr[:, None]
    cp = _clip(cp, planes)
    cp[:, 2] = np.where(cp[:, 2] < -0.55, -0.55 + (cp[:, 2] + 0.55) * 0.15, cp[:, 2])
    cp = (cp - (cp.max(axis=0) + cp.min(axis=0)) / 2.0) / (cp.max(axis=0) - cp.min(axis=0))
    cp = cp * np.asarray(size_xyz) * 0.97
    cp[:, 2] -= cp[:, 2].min()
    collider = Mesh(
        "Colmesh-1_mesh",
        cp,
        vertex_normals(cp, cfaces),
        np.zeros((cp.shape[0], 2)),
        cfaces,
        material=None,
        node_name="Colmesh-1",
    )
    return [visible, collider]


# ---------------------------------------------------------------------------
# Trees and shrubs (card foliage on a real trunk)
# ---------------------------------------------------------------------------


BARK_TILE_M = 0.5  # one bark tile covers 0.5 m of trunk: spruce plates at 3-5 cm


def _bark_repeats(length: float, base_radius: float) -> tuple[float, float]:
    """(v, u) tile repeats so the bark tile is BARK_TILE_M on the trunk at mid-height."""

    girth = 2.0 * math.pi * base_radius * 0.6
    return max(1.0, length / BARK_TILE_M), max(1.0, round(girth / BARK_TILE_M))


def _trunk(
    height: float,
    base_radius: float,
    top_radius: float,
    sides: int,
    uv_repeat_v: float,
    uv_repeat_u: float = 1.0,
):
    """A three-ring tapered trunk; the bark tile repeats ``uv_repeat_u`` times round it
    and ``uv_repeat_v`` times up it (the same u repeat at every ring keeps the seam
    straight, so the caller sizes it for the mean girth)."""

    angles = np.linspace(0, 2 * math.pi, sides, endpoint=False)
    rings = []
    uvs = []
    levels = [
        (0.0, base_radius),
        (height * 0.5, (base_radius + top_radius) / 2),
        (height, top_radius),
    ]
    for z, r in levels:
        ring = np.stack([r * np.cos(angles), r * np.sin(angles), np.full(sides, z)], axis=1)
        rings.append(ring)
        uvs.append(
            np.stack(
                [
                    np.linspace(0, uv_repeat_u, sides, endpoint=False),
                    np.full(sides, z / height * uv_repeat_v),
                ],
                axis=1,
            )
        )
    positions = np.concatenate(rings)
    uv = np.concatenate(uvs)
    tris = []
    for level in range(len(levels) - 1):
        for i in range(sides):
            a = level * sides + i
            b = level * sides + (i + 1) % sides
            c = (level + 1) * sides + (i + 1) % sides
            d = (level + 1) * sides + i
            tris += [[a, b, c], [a, c, d]]
    return positions, uv, np.asarray(tris, dtype="int64")


def _vertical_cards(
    z0: float, z1: float, half_width: float, planes: int, twist: float, uv_span=(0.0, 1.0)
):
    parts = []
    u0, u1 = uv_span
    for k in range(planes):
        angle = twist + k * math.pi / planes
        dx, dy = math.cos(angle) * half_width, math.sin(angle) * half_width
        parts.append(
            _quad(
                (-dx, -dy, z0),
                (dx, dy, z0),
                (dx, dy, z1),
                (-dx, -dy, z1),
                (u0, 0),
                (u1, 0),
                (u1, 1),
                (u0, 1),
            )
        )
    return parts


def _tier_disc(z: float, radius: float, droop: float, uv_rect=(0.0, 0.0, 1.0, 1.0)):
    """A drooping square card (foliage seen from above/below), centred on the trunk."""

    u0, v0, u1, v1 = uv_rect
    return _quad(
        (-radius, -radius, z - droop),
        (radius, -radius, z - droop),
        (radius, radius, z - droop),
        (-radius, radius, z - droop),
        (u0, v0),
        (u1, v0),
        (u1, v1),
        (u0, v1),
    )


def conifer_meshes(
    seed: int,
    height: float,
    crown_width: float,
    *,
    kind: str = "spruce",
    card_material: str = "spruce_cards",
    bark_material: str = "spruce_bark",
    name: str = "spruce",
    tier_material: str | None = None,
) -> list[Mesh]:
    """Spire-shaped conifer: 3 crossed vertical cards + 3 drooping tier cards + trunk.

    The tier cards carry ``tier_material`` (a top-view whorl atlas whose alpha dies at
    the rim) when given, so their corners never show as a skirt around the crown.

    ``kind``: ``spruce`` (narrow spire), ``fir`` (fuller), ``krummholz`` (stunted, wide,
    leaning). Foliage UVs cover the whole card atlas (the atlas is one spire).
    """

    rng = np.random.default_rng(seed)
    lean = {"spruce": 0.02, "fir": 0.015, "krummholz": 0.12, "sapling": 0.03}[kind]
    crown_base = {"spruce": 0.18, "fir": 0.12, "krummholz": 0.05, "sapling": 0.06}[kind] * height
    trunk_r = max(0.06, 0.018 * height) if kind != "sapling" else max(0.05, 0.03 * height)
    parts = []
    repeats = _bark_repeats(height * 0.92, trunk_r)
    trunk = _trunk(height * 0.92, trunk_r, trunk_r * 0.15, 8, *repeats)
    parts_bark = [trunk]
    twist = rng.uniform(0, math.pi)
    parts += _vertical_cards(crown_base, height, crown_width / 2.0, 3, twist)
    tiers = {
        "spruce": (0.30, 0.55, 0.78),
        "fir": (0.25, 0.50, 0.75),
        "krummholz": (0.35, 0.65),
        "sapling": (0.35, 0.65),
    }[kind]
    parts_tier = []
    for frac in tiers:
        z = crown_base + (height - crown_base) * frac
        radius = crown_width / 2.0 * (1.0 - frac) * 0.6 + 0.15
        parts_tier.append(_tier_disc(z, radius, droop=0.3 * radius, uv_rect=(0, 0, 1, 1)))
    positions, uvs, tris = _concat(parts)
    tier_positions, tier_uvs, tier_tris = _concat(parts_tier)
    bark_positions, bark_uvs, bark_tris = _concat(parts_bark)
    # Lean the whole tree slightly.
    shear = np.array([lean * rng.uniform(-1, 1), lean * rng.uniform(-1, 1)])
    for arr in (positions, tier_positions, bark_positions):
        arr[:, 0] += arr[:, 2] * shear[0]
        arr[:, 1] += arr[:, 2] * shear[1]
    card_normals = np.tile(np.array([0.0, 0.0, 1.0]), (positions.shape[0], 1))
    foliage = Mesh(
        f"{name}_foliage_mesh",
        positions,
        card_normals,
        uvs,
        tris,
        material=card_material,
        node_name=f"{name}_foliage",
    )
    tier_mesh = Mesh(
        f"{name}_tiers_mesh",
        tier_positions,
        np.tile(np.array([0.0, 0.0, 1.0]), (tier_positions.shape[0], 1)),
        tier_uvs,
        tier_tris,
        material=tier_material or card_material,
        node_name=f"{name}_tiers",
    )
    bark = Mesh(
        f"{name}_trunk_mesh",
        bark_positions,
        vertex_normals(bark_positions, bark_tris),
        bark_uvs,
        bark_tris,
        material=bark_material,
        node_name=f"{name}_trunk",
    )
    cp, cu, ct = _trunk(height * 0.6, trunk_r * 1.3, trunk_r * 0.8, 6, 1.0)
    collider = Mesh(
        "Colmesh-1_mesh", cp, vertex_normals(cp, ct), cu, ct, material=None, node_name="Colmesh-1"
    )
    return [foliage, tier_mesh, bark, collider]


def broadleaf_meshes(
    seed: int,
    height: float,
    crown_width: float,
    *,
    card_material: str = "aspen_cards",
    bark_material: str = "aspen_bark",
    name: str = "aspen",
    stems: int = 1,
) -> list[Mesh]:
    """Aspen-style broadleaf: slender pale trunk, a rounded crown of 3 crossed cards.

    ``stems`` > 1 makes a sucker clump: that many thin stems leaning out from one
    root, the crown starting low and made of four cards, bushy rather than tall.
    """

    rng = np.random.default_rng(seed)
    clump = stems > 1
    crown_base = (0.2 if clump else 0.35) * height
    trunk_r = max(0.05, 0.014 * height) if not clump else max(0.03, 0.01 * height)
    trunks = []
    for k in range(max(1, stems)):
        trunk_p, trunk_u, trunk_t = _trunk(
            height * (0.85 if not clump else rng.uniform(0.6, 0.85)),
            trunk_r,
            trunk_r * 0.35,
            8 if not clump else 6,
            *_bark_repeats(height * 0.85, trunk_r),
        )
        if clump:
            # Each stem leans out from the shared root at its own heading.
            heading = 2 * math.pi * k / stems + rng.uniform(-0.4, 0.4)
            lean_out = rng.uniform(0.06, 0.14)
            trunk_p = trunk_p.copy()
            trunk_p[:, 0] += trunk_p[:, 2] * lean_out * math.cos(heading) + 0.05 * math.cos(heading)
            trunk_p[:, 1] += trunk_p[:, 2] * lean_out * math.sin(heading) + 0.05 * math.sin(heading)
        trunks.append((trunk_p, trunk_u, trunk_t))
    twist = rng.uniform(0, math.pi)
    parts = _vertical_cards(crown_base, height, crown_width / 2.0, 4 if clump else 3, twist)
    parts.append(
        _tier_disc(crown_base + (height - crown_base) * 0.6, crown_width * 0.45, droop=0.1)
    )
    positions, uvs, tris = _concat(parts)
    bark_positions, bark_uvs, bark_tris = _concat(trunks)
    lean = 0.03
    shear = np.array([lean * rng.uniform(-1, 1), lean * rng.uniform(-1, 1)])
    for arr in (positions, bark_positions):
        arr[:, 0] += arr[:, 2] * shear[0]
        arr[:, 1] += arr[:, 2] * shear[1]
    foliage = Mesh(
        f"{name}_foliage_mesh",
        positions,
        np.tile([0.0, 0.0, 1.0], (positions.shape[0], 1)),
        uvs,
        tris,
        material=card_material,
        node_name=f"{name}_foliage",
    )
    bark = Mesh(
        f"{name}_trunk_mesh",
        bark_positions,
        vertex_normals(bark_positions, bark_tris),
        bark_uvs,
        bark_tris,
        material=bark_material,
        node_name=f"{name}_trunk",
    )
    cp, cu, ct = _trunk(height * 0.5, trunk_r * 1.3, trunk_r * 0.9, 6, 1.0)
    collider = Mesh(
        "Colmesh-1_mesh", cp, vertex_normals(cp, ct), cu, ct, material=None, node_name="Colmesh-1"
    )
    return [foliage, bark, collider]


def shrub_meshes(
    seed: int,
    height: float,
    width: float,
    *,
    card_material: str = "shrub_cards",
    name: str = "shrub",
) -> list[Mesh]:
    """Low shrub (juniper / saltbush): three crossed cards and a top card, no collision."""

    rng = np.random.default_rng(seed)
    twist = rng.uniform(0, math.pi)
    parts = _vertical_cards(0.0, height, width / 2.0, 3, twist)
    parts.append(_tier_disc(height * 0.7, width * 0.42, droop=0.05))
    positions, uvs, tris = _concat(parts)
    return [
        Mesh(
            f"{name}_mesh",
            positions,
            np.tile([0.0, 0.0, 1.0], (positions.shape[0], 1)),
            uvs,
            tris,
            material=card_material,
            node_name=name,
        )
    ]


# ---------------------------------------------------------------------------
# Collada writer
# ---------------------------------------------------------------------------


def _floats(array: np.ndarray, decimals: int = 5) -> str:
    flat = np.asarray(array, dtype="float64").ravel()
    return " ".join(f"{v:.{decimals}f}".rstrip("0").rstrip(".") if v != 0 else "0" for v in flat)


def write_dae(
    path: Path, meshes: list[Mesh], shape_name: str, *, created: str = "2026-01-01T00:00:00"
) -> dict:
    """Write ``meshes`` as one Collada shape. Returns a summary (counts) for the handoff."""

    materials = sorted({m.material for m in meshes if m.material})
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
        "  <asset>",
        "    <contributor>",
        "      <author>beamng-mcp gis_maps meshgen</author>",
        "      <authoring_tool>examples/gis_maps/maplib/meshgen.py</authoring_tool>",
        "    </contributor>",
        f"    <created>{created}</created>",
        f"    <modified>{created}</modified>",
        '    <unit name="meter" meter="1"/>',
        "    <up_axis>Z_UP</up_axis>",
        "  </asset>",
        "  <library_effects>",
    ]
    for material in materials:
        lines += [
            f'    <effect id="{material}-effect">',
            "      <profile_COMMON>",
            '        <technique sid="common">',
            "          <lambert>",
            '            <emission><color sid="emission">0 0 0 1</color></emission>',
            '            <diffuse><color sid="diffuse">0.6 0.6 0.6 1</color></diffuse>',
            '            <index_of_refraction><float sid="ior">1.45</float></index_of_refraction>',
            "          </lambert>",
            "        </technique>",
            "      </profile_COMMON>",
            "    </effect>",
        ]
    lines += ["  </library_effects>", "  <library_images/>", "  <library_materials>"]
    for material in materials:
        lines.append(
            f'    <material id="{material}-material" name="{material}">'
            f'<instance_effect url="#{material}-effect"/></material>'
        )
    lines += ["  </library_materials>", "  <library_geometries>"]
    total_triangles = 0
    for mesh in meshes:
        gid = f"{shape_name}_{mesh.name}"
        n = mesh.positions.shape[0]
        tri = mesh.triangles
        total_triangles += tri.shape[0]
        lines += [
            f'    <geometry id="{gid}-mesh" name="{escape(mesh.name)}">',
            "      <mesh>",
            f'        <source id="{gid}-mesh-positions">',
            f'          <float_array id="{gid}-mesh-positions-array" count="{n * 3}">'
            f"{_floats(mesh.positions)}</float_array>",
            "          <technique_common>",
            f'            <accessor source="#{gid}-mesh-positions-array" count="{n}" stride="3">',
            '              <param name="X" type="float"/><param name="Y" type="float"/>'
            '<param name="Z" type="float"/>',
            "            </accessor>",
            "          </technique_common>",
            "        </source>",
            f'        <source id="{gid}-mesh-normals">',
            f'          <float_array id="{gid}-mesh-normals-array" count="{n * 3}">'
            f"{_floats(mesh.normals)}</float_array>",
            "          <technique_common>",
            f'            <accessor source="#{gid}-mesh-normals-array" count="{n}" stride="3">',
            '              <param name="X" type="float"/><param name="Y" type="float"/>'
            '<param name="Z" type="float"/>',
            "            </accessor>",
            "          </technique_common>",
            "        </source>",
            f'        <source id="{gid}-mesh-map-0">',
            f'          <float_array id="{gid}-mesh-map-0-array" count="{n * 2}">'
            f"{_floats(mesh.uvs)}</float_array>",
            "          <technique_common>",
            f'            <accessor source="#{gid}-mesh-map-0-array" count="{n}" stride="2">',
            '              <param name="S" type="float"/><param name="T" type="float"/>',
            "            </accessor>",
            "          </technique_common>",
            "        </source>",
            f'        <vertices id="{gid}-mesh-vertices">',
            f'          <input semantic="POSITION" source="#{gid}-mesh-positions"/>',
            "        </vertices>",
        ]
        material_attr = f' material="{mesh.material}-material"' if mesh.material else ""
        p = " ".join(f"{i} {i} {i}" for i in tri.ravel())
        lines += [
            f'        <triangles{material_attr} count="{tri.shape[0]}">',
            f'          <input semantic="VERTEX" source="#{gid}-mesh-vertices" offset="0"/>',
            f'          <input semantic="NORMAL" source="#{gid}-mesh-normals" offset="1"/>',
            f'          <input semantic="TEXCOORD" source="#{gid}-mesh-map-0" offset="2" set="0"/>',
            f"          <p>{p}</p>",
            "        </triangles>",
            "      </mesh>",
            "    </geometry>",
        ]
    lines += [
        "  </library_geometries>",
        "  <library_visual_scenes>",
        f'    <visual_scene id="{shape_name}_scene" name="{shape_name}_scene">',
    ]
    for mesh in meshes:
        gid = f"{shape_name}_{mesh.name}"
        node = mesh.node_name or mesh.name
        lines += [
            f'      <node id="{escape(node)}" name="{escape(node)}" type="NODE">',
            '        <matrix sid="transform">1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</matrix>',
        ]
        if mesh.material:
            lines += [
                f'        <instance_geometry url="#{gid}-mesh" name="{escape(node)}">',
                "          <bind_material>",
                "            <technique_common>",
                f'              <instance_material symbol="{mesh.material}-material" '
                f'target="#{mesh.material}-material">',
                '                <bind_vertex_input semantic="UVMap" input_semantic="TEXCOORD" '
                'input_set="0"/>',
                "              </instance_material>",
                "            </technique_common>",
                "          </bind_material>",
                "        </instance_geometry>",
            ]
        else:
            lines.append(f'        <instance_geometry url="#{gid}-mesh" name="{escape(node)}"/>')
        lines.append("      </node>")
    lines += [
        "    </visual_scene>",
        "  </library_visual_scenes>",
        "  <scene>",
        f'    <instance_visual_scene url="#{shape_name}_scene"/>',
        "  </scene>",
        "</COLLADA>",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    bounds = np.concatenate([m.positions for m in meshes if m.material])
    return {
        "file": path.name,
        "meshes": [m.node_name or m.name for m in meshes],
        "materials": materials,
        "triangles": int(total_triangles),
        "extent_m": [round(float(v), 3) for v in (bounds.max(axis=0) - bounds.min(axis=0))],
    }
