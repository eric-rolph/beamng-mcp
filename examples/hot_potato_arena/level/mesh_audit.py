"""Is a shipped mesh a CLOSED SOLID, or a facade?  One reader, one verdict, three callers.

The user's requirement for this round (2026-09-07): *"make sure the rocks, boulder and
mountain aren't just facade, but have complete 3D geometry."*  The orchestrator's
``geometry_audit/manifold_probe.py`` answers it with an edge-ownership count; this module is
the same count plus the four things a closed edge count cannot see, so that the static gate
in ``tests/test_hot_potato_props.py``, the round's ``static_evidence.py`` and the report's
instrument all read ONE implementation and cannot disagree with each other:

``boundary``
    edges owned by exactly one triangle.  A solid has 0; a sheet, a billboard or a curtain
    has many (B1's backdrop ring: 9,216).
``nonmanifold``
    edges owned by three or more triangles (0).
``misoriented``
    directed edges that occur twice, i.e. two faces that disagree about which way is out.
    A closed shell whose caps are wound against its loft passes both counts above and
    fails this one -- which is what the bench log did for three revisions.
``bowtie_verts``
    vertices whose incident faces do not form ONE closed fan.  The Collada exporter welds
    coincident vertices, so two shells that share a hub point become one shell pinched at a
    vertex: closed by every edge count, and not a manifold.
``volume_m3``
    signed volume by the divergence theorem; > 0 means wound outward.
``underside_m2``
    area of the faces whose normal points down; > 0 means the shape has a bottom.
``shells``
    connected components with their Euler characteristic ``V - E + F``.  A closed
    ORIENTABLE surface has an EVEN characteristic, ``2 - 2g``: 2 for a boulder, 0 for a
    torus (a rope band), -2 for a pot body with two handle holes.  An ODD value is a pinch.

A mesh is ``SOLID`` when every count is what a solid gives.  Pure standard library, so the
gate runs anywhere the tree does.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any
from xml.etree import ElementTree as ET

COLLADA_NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}

Vec = tuple[float, float, float]
Tri = tuple[int, int, int]


def geometries(payload: bytes) -> dict[str, tuple[list[Vec], list[Tri]]]:
    """``{geometry name: (positions, triangles)}`` for every ``<geometry>`` in a DAE."""

    root = ET.fromstring(payload)  # noqa: S314 - our own exporter's output
    out: dict[str, tuple[list[Vec], list[Tri]]] = {}
    for geometry in root.findall(".//c:library_geometries/c:geometry", COLLADA_NS):
        name = geometry.get("name") or geometry.get("id") or "?"
        mesh = geometry.find("c:mesh", COLLADA_NS)
        if mesh is None:
            continue
        sources = {s.get("id"): s for s in mesh.findall("c:source", COLLADA_NS)}
        vertices = mesh.find("c:vertices", COLLADA_NS)
        position = None
        for entry in vertices.findall("c:input", COLLADA_NS) if vertices is not None else []:
            if entry.get("semantic") == "POSITION":
                position = sources.get(entry.get("source", "").lstrip("#"))
        if position is None:
            continue
        array = position.find("c:float_array", COLLADA_NS)
        if array is None or not array.text:
            continue
        floats = [float(t) for t in array.text.split()]
        positions = [
            (floats[i], floats[i + 1], floats[i + 2]) for i in range(0, len(floats) - 2, 3)
        ]
        tris: list[Tri] = []
        primitives = list(mesh.findall("c:triangles", COLLADA_NS))
        primitives += list(mesh.findall("c:polylist", COLLADA_NS))
        for primitive in primitives:
            inputs = primitive.findall("c:input", COLLADA_NS)
            stride = 1 + max((int(i.get("offset", "0")) for i in inputs), default=0)
            offset = next(
                (int(i.get("offset", "0")) for i in inputs if i.get("semantic") == "VERTEX"), 0
            )
            p = primitive.find("c:p", COLLADA_NS)
            if p is None or not p.text:
                continue
            index = [int(t) for t in p.text.split()][offset::stride]
            if primitive.tag.endswith("polylist"):
                vcount = primitive.find("c:vcount", COLLADA_NS)
                counts = [int(t) for t in vcount.text.split()] if vcount is not None else []
                cursor = 0
                for n in counts:
                    poly = index[cursor : cursor + n]
                    cursor += n
                    for k in range(1, n - 1):
                        tris.append((poly[0], poly[k], poly[k + 1]))
            else:
                tris.extend(
                    (index[k], index[k + 1], index[k + 2]) for k in range(0, len(index) - 2, 3)
                )
        out[name] = (positions, tris)
    return out


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def audit(positions: list[Vec], tris: list[Tri]) -> dict[str, Any]:
    """Every count in the module docstring, plus the ``SOLID`` / ``OPEN`` verdict."""

    edges: Counter[tuple[int, int]] = Counter()
    directed: Counter[tuple[int, int]] = Counter()
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            edges[(u, v) if u < v else (v, u)] += 1
            directed[(u, v)] += 1
    histogram = Counter(edges.values())
    boundary = histogram.get(1, 0)
    nonmanifold = sum(n for k, n in histogram.items() if k >= 3)
    misoriented = sum(1 for n in directed.values() if n > 1)
    volume = 0.0
    underside = 0.0
    total = 0.0
    for a, b, c in tris:
        pa, pb, pc = positions[a], positions[b], positions[c]
        normal = _cross(
            (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]),
            (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]),
        )
        volume += (pa[0] * normal[0] + pa[1] * normal[1] + pa[2] * normal[2]) / 6.0
        area2 = (normal[0] ** 2 + normal[1] ** 2 + normal[2] ** 2) ** 0.5
        total += 0.5 * area2
        if area2 > 0 and normal[2] / area2 < -0.3:
            underside += 0.5 * area2
    parent = list(range(len(positions)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b, c in tris:
        ra = find(a)
        parent[find(b)] = ra
        parent[find(c)] = find(ra)
    shell_v: Counter[int] = Counter()
    shell_f: Counter[int] = Counter()
    shell_e: Counter[int] = Counter()
    used: set[int] = set()
    for a, b, c in tris:
        root = find(a)
        shell_f[root] += 1
        for v in (a, b, c):
            if v not in used:
                used.add(v)
                shell_v[root] += 1
    for u, _v in edges:
        shell_e[find(u)] += 1
    shells = [
        {
            "verts": shell_v[r],
            "edges": shell_e[r],
            "faces": shell_f[r],
            "chi": shell_v[r] - shell_e[r] + shell_f[r],
        }
        for r in sorted(shell_f)
    ]
    # a bow-tie / pinch vertex: the faces around it do not form exactly one closed fan
    around: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for a, b, c in tris:
        around[a].append((b, c))
        around[b].append((c, a))
        around[c].append((a, b))
    bowtie = 0
    for fan in around.values():
        nxt = {p: q for p, q in fan}
        if len(nxt) != len(fan):
            bowtie += 1
            continue
        start = fan[0][0]
        cursor = nxt.get(start)
        seen = 1
        while cursor is not None and cursor != start and seen <= len(fan):
            cursor = nxt.get(cursor)
            seen += 1
        if cursor != start or seen != len(fan):
            bowtie += 1
    if positions:
        xs, ys, zs = zip(*positions, strict=True)
        bbox = [round(max(c) - min(c), 3) for c in (xs, ys, zs)]
    else:
        bbox = [0.0, 0.0, 0.0]
    solid = (
        bool(tris)
        and boundary == 0
        and nonmanifold == 0
        and misoriented == 0
        and bowtie == 0
        and volume > 0.0
        and underside > 0.0
        and all(s["chi"] % 2 == 0 and s["chi"] <= 2 for s in shells)
    )
    return {
        "tris": len(tris),
        "verts": len(positions),
        "boundary": boundary,
        "nonmanifold": nonmanifold,
        "misoriented": misoriented,
        "bowtie_verts": bowtie,
        "volume_m3": round(volume, 4),
        "area_m2": round(total, 3),
        "underside_m2": round(underside, 3),
        "underside_share": round(underside / total, 4) if total else None,
        "bbox": bbox,
        "shells": shells,
        "shell_count": len(shells),
        "genus_by_shell": [(2 - s["chi"]) // 2 if s["chi"] % 2 == 0 else None for s in shells],
        "verdict": "SOLID" if solid else "OPEN",
    }


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def convex_hull(points: list[Vec]) -> list[Tri]:
    """The convex hull of a point cloud, as triangles, in pure standard library (r10).

    The husk gate (``level_facts`` 2026-09-09) is stated in terms of ``V / V(hull)``, so the
    gate needs a hull -- and this module's promise is that it runs anywhere the tree does, with
    no scipy.  Incremental (gift-wrap-free) construction with an exact interior pre-filter:

    1. take the extreme point along each of 26 lattice directions and hull THOSE (a handful of
       points, so the incremental step is cheap);
    2. every point strictly inside that seed polytope can never be a hull vertex, so discard it
       -- this is exact, not a heuristic, and it typically leaves a few hundred of thousands;
    3. add the survivors one at a time: delete every face the point can see, and cone the
       resulting horizon to it.

    Degenerate input (fewer than 4 points, or a flat cloud) returns an empty hull, and
    :func:`hull_volume` then reports 0.0 -- the caller decides what that means.
    """

    unique = sorted({(float(p[0]), float(p[1]), float(p[2])) for p in points})
    if len(unique) < 4:
        return []
    scale = max(
        max(p[i] for p in unique) - min(p[i] for p in unique) for i in range(3)
    )
    if scale <= 0:
        return []
    # visibility is tested as a DISTANCE to the face plane, not as the raw triple product:
    # a scan cloud carries thousands of near-coplanar and near-duplicate points, and an
    # unnormalised threshold made faces of very different area answer "can this point see me?"
    # on very different scales.  That is what put five of the CC0 scans' hulls 15-450 % over
    # their true volume in the first cut of this function.
    eps = 1e-9 * scale

    def build(cloud: list[Vec]) -> list[Tri]:
        # an initial tetrahedron: two far-apart points, the point farthest from that line, and
        # the point farthest from that plane
        a = min(cloud)
        b = max(cloud, key=lambda p: _dot(_sub(p, a), _sub(p, a)))
        ab = _sub(b, a)
        c = max(cloud, key=lambda p: _dot(_cross(ab, _sub(p, a)), _cross(ab, _sub(p, a))))
        normal = _cross(ab, _sub(c, a))
        d = max(cloud, key=lambda p: abs(_dot(normal, _sub(p, a))))
        span = math.sqrt(_dot(normal, normal))
        if span <= 0 or abs(_dot(normal, _sub(d, a))) / span <= eps:
            return []
        quad = [a, b, c, d]
        index = {p: i for i, p in enumerate(quad)}
        faces = [(0, 1, 2), (0, 2, 3), (0, 3, 1), (1, 3, 2)]
        verts = list(quad)
        centre = tuple(sum(p[i] for p in quad) / 4.0 for i in range(3))
        faces = [
            f if _dot(_cross(_sub(verts[f[1]], verts[f[0]]), _sub(verts[f[2]], verts[f[0]])),
                      _sub(verts[f[0]], centre)) > 0 else (f[0], f[2], f[1])
            for f in faces
        ]
        for point in cloud:
            if point in index:
                continue
            visible, horizon = [], Counter()
            for f in faces:
                p0, p1, p2 = verts[f[0]], verts[f[1]], verts[f[2]]
                n = _cross(_sub(p1, p0), _sub(p2, p0))
                area = math.sqrt(_dot(n, n))
                if area <= 0.0:
                    visible.append(f)  # a degenerate face is never part of the answer
                    for edge in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                        horizon[edge] += 1
                    continue
                if _dot(n, _sub(point, p0)) / area > eps:
                    visible.append(f)
                    for edge in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                        horizon[edge] += 1
            if not visible:
                continue
            faces = [f for f in faces if f not in visible]
            index[point] = len(verts)
            verts.append(point)
            new = index[point]
            for (u, v), count in horizon.items():
                if count == 1 and horizon.get((v, u), 0) == 0:
                    faces.append((u, v, new))
        return [(verts[f[0]], verts[f[1]], verts[f[2]]) for f in faces]  # type: ignore[misc]

    directions = [
        (x, y, z)
        for x in (-1, 0, 1)
        for y in (-1, 0, 1)
        for z in (-1, 0, 1)
        if (x, y, z) != (0, 0, 0)
    ]
    seed = {max(unique, key=lambda p: _dot(p, d)) for d in directions}
    survivors = unique
    if len(seed) >= 4:
        seed_faces = build(sorted(seed))
        if seed_faces:
            planes = []
            centre = tuple(sum(p[i] for p in seed) / len(seed) for i in range(3))
            for p0, p1, p2 in seed_faces:
                n = _cross(_sub(p1, p0), _sub(p2, p0))
                if _dot(n, _sub(p0, centre)) < 0:
                    n = (-n[0], -n[1], -n[2])
                planes.append((n, _dot(n, p0)))
            survivors = [
                p for p in unique if any(_dot(n, p) > offset - eps for n, offset in planes)
            ]
    return build(survivors)


def hull_volume(points: list[Vec]) -> float:
    """Volume of the convex hull of a point cloud (0.0 for degenerate input)."""

    faces = convex_hull(points)
    total = 0.0
    for a, b, c in faces:
        total += _dot(a, _cross(b, c))
    return abs(total) / 6.0


def audit_dae(name: str, payload: bytes) -> dict[str, Any]:
    """Every geometry in one DAE, and whether the whole file is solid at every detail."""

    rows = {gid: audit(positions, tris) for gid, (positions, tris) in geometries(payload).items()}
    return {
        "file": name,
        "meshes": rows,
        "all_solid": bool(rows) and all(r["verdict"] == "SOLID" for r in rows.values()),
        "has_colmesh": any(g.startswith("Colmesh_") for g in rows),
        "open": sorted(g for g, r in rows.items() if r["verdict"] != "SOLID"),
    }
