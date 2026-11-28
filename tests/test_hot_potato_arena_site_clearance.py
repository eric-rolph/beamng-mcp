"""Site-clearance gate for the Gateway Skillet arena (design v3 §8, critique erratum 3).

The arena needs r <= 155 m around C = (850, -280) on gridmap_v2 free of stock
geometry (glacis toe 113 m + 42 m runoff). Two design rounds asserted "clear
to 170 m" from record ORIGINS and were wrong twice; this gate does what the
critic demanded, forever:

- parse every ``items.level.json`` record of every class in the stock level,
- expand each ``Prefab`` record's ``.prefab`` children (TorqueScript object
  blocks, recursively) to world space THROUGH the record's rotationMatrix and
  scale, then through each child's own transform,
- add each child shape's real extents (the DAE's visual-scene bounding box,
  node transforms and units applied) as a world-space AABB,
- walk every DecalRoad / River node list as segments with their half-widths,
- and assert nothing enters r <= 155 m.

The groundplane tiles ARE the site's drive surface (probe P4: castRayStatic
gives z = 100.000 at C); they are excluded from the clearance sweep and
separately asserted to sit at z = 100 wherever they touch the arena.

Needs the stock ``gridmap_v2.zip``; skips when no BeamNG install is configured.
"""

from __future__ import annotations

import functools
import json
import math
import os
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pytest

SITE = (850.0, -280.0)
CLEARANCE_M = 155.0
#: How the engine reads a record's 9-float ``rotationMatrix``. Two readings are
#: possible and they disagree by ~50 m on this site (p_gm_interzone_structure10
#: is a 90-degree-rotated cube stack): "standard" = row-major, world = R*local
#: (beamngpy's compute_rotation_matrix); "transposed" = the rows are the local
#: axes expressed in world (Torque MatrixF column convention, CCW's spotlight
#: basis). Pinned by the live smoke's ray probes (tests/test_hot_potato_arena_live.py,
#: ``rotation_convention``) and shared with the generator; the sweep computes
#: BOTH and reports both so a wrong pin is visible, not silent.
from examples.hot_potato_arena.sync_scenario_outputs import (  # noqa: E402
    ENGINE_ROTATION_CONVENTION as ENGINE_CONVENTION,
)

GLACIS_TOE_M = 113.0
GROUNDPLANE_PATTERN = re.compile(r"s_gm_groundplane_\d+m", re.IGNORECASE)
COLLADA = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
DEFAULT_HOMES = (
    r"E:\SteamLibrary\steamapps\common\BeamNG.drive",
    r"C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive",
)

Matrix = tuple[float, ...]


def _level_zip() -> Path:
    candidates = []
    for key in ("BEAMNG_MCP_TEST_BEAMNG_HOME", "BEAMNG_HOME"):
        value = os.getenv(key)
        if value:
            candidates.append(Path(value))
    candidates.extend(Path(home) for home in DEFAULT_HOMES)
    for home in candidates:
        archive = home / "content" / "levels" / "gridmap_v2.zip"
        if archive.is_file():
            return archive
    pytest.skip("stock gridmap_v2.zip not found; set BEAMNG_MCP_TEST_BEAMNG_HOME")


# --- linear algebra (row-major 3x3, world = R * local) ----------------------


def _mat_vec(m: Matrix, v: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
        m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
        m[6] * v[0] + m[7] * v[1] + m[8] * v[2],
    )


def _mat_mul(a: Matrix, b: Matrix) -> Matrix:
    return tuple(
        sum(a[row * 3 + k] * b[k * 3 + col] for k in range(3))
        for row in range(3)
        for col in range(3)
    )


def _parse_vec(text: str | list[Any] | None, default: tuple[float, ...]) -> tuple[float, ...]:
    if text is None:
        return default
    if isinstance(text, list):
        values = tuple(float(v) for v in text)
    else:
        values = tuple(float(v) for v in str(text).split())
    return values if len(values) == len(default) else default


def _point_to_aabb_xy(lo: tuple[float, float], hi: tuple[float, float]) -> float:
    dx = max(lo[0] - SITE[0], 0.0, SITE[0] - hi[0])
    dy = max(lo[1] - SITE[1], 0.0, SITE[1] - hi[1])
    return math.hypot(dx, dy)


def _point_to_segment_xy(a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    px, py = SITE
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# --- stock DAE extents --------------------------------------------------------


def _collada_matrix(node: ET.Element) -> list[list[float]]:
    matrix = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]

    def multiply(other: list[list[float]]) -> None:
        nonlocal matrix
        matrix = [
            [sum(matrix[r][k] * other[k][c] for k in range(4)) for c in range(4)] for r in range(4)
        ]

    for child in node:
        tag = child.tag.split("}")[-1]
        if tag == "matrix":
            values = [float(v) for v in (child.text or "").split()]
            if len(values) == 16:
                multiply([values[i * 4 : i * 4 + 4] for i in range(4)])
        elif tag == "translate":
            t = [float(v) for v in (child.text or "").split()]
            if len(t) == 3:
                multiply([[1, 0, 0, t[0]], [0, 1, 0, t[1]], [0, 0, 1, t[2]], [0, 0, 0, 1]])
        elif tag == "scale":
            s = [float(v) for v in (child.text or "").split()]
            if len(s) == 3:
                multiply([[s[0], 0, 0, 0], [0, s[1], 0, 0], [0, 0, s[2], 0], [0, 0, 0, 1]])
        elif tag == "rotate":
            r = [float(v) for v in (child.text or "").split()]
            if len(r) == 4 and abs(r[3]) > 1e-9:
                x, y, z = r[:3]
                norm = math.sqrt(x * x + y * y + z * z) or 1.0
                x, y, z = x / norm, y / norm, z / norm
                angle = math.radians(r[3])
                c, s = math.cos(angle), math.sin(angle)
                multiply(
                    [
                        [c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s, 0],
                        [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s, 0],
                        [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c), 0],
                        [0, 0, 0, 1],
                    ]
                )
    return matrix


def _geometry_meshes(
    root: ET.Element,
) -> dict[str, tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]]:
    """geometry id -> (positions, triangle index triples) from the COLLADA mesh."""

    meshes: dict[str, tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]] = {}
    for geometry in root.findall(".//c:library_geometries/c:geometry", COLLADA):
        mesh = geometry.find("c:mesh", COLLADA)
        if mesh is None:
            continue
        vertices = mesh.find("c:vertices", COLLADA)
        source_id = None
        vertices_id = vertices.attrib.get("id", "") if vertices is not None else ""
        if vertices is not None:
            for input_node in vertices.findall("c:input", COLLADA):
                if input_node.attrib.get("semantic") == "POSITION":
                    source_id = input_node.attrib.get("source", "").lstrip("#")
        array_text = None
        for source in mesh.findall("c:source", COLLADA):
            if source_id is None or source.attrib.get("id") == source_id:
                array = source.find("c:float_array", COLLADA)
                if array is not None and array.text:
                    array_text = array.text
                    break
        if array_text is None:
            continue
        values = [float(v) for v in array_text.split()]
        positions = list(zip(values[0::3], values[1::3], values[2::3]))
        if not positions:
            continue
        triangles: list[tuple[int, int, int]] = []
        for primitive in (
            *mesh.findall("c:triangles", COLLADA),
            *mesh.findall("c:polylist", COLLADA),
        ):
            inputs = primitive.findall("c:input", COLLADA)
            stride = max((int(i.attrib.get("offset", "0")) for i in inputs), default=0) + 1
            vertex_offset = next(
                (
                    int(i.attrib.get("offset", "0"))
                    for i in inputs
                    if i.attrib.get("semantic") == "VERTEX"
                    and i.attrib.get("source", "").lstrip("#") == vertices_id
                ),
                None,
            )
            p_node = primitive.find("c:p", COLLADA)
            if vertex_offset is None or p_node is None or not p_node.text:
                continue
            p = [int(v) for v in p_node.text.split()]
            indices = p[vertex_offset::stride]
            vcount_node = primitive.find("c:vcount", COLLADA)
            if vcount_node is not None and vcount_node.text:
                cursor = 0
                for count in (int(v) for v in vcount_node.text.split()):
                    polygon = indices[cursor : cursor + count]
                    cursor += count
                    for k in range(1, len(polygon) - 1):
                        triangles.append((polygon[0], polygon[k], polygon[k + 1]))
            else:
                for k in range(0, len(indices) - 2, 3):
                    triangles.append((indices[k], indices[k + 1], indices[k + 2]))
        meshes[geometry.attrib["id"]] = (positions, triangles)
    return meshes


@functools.cache
def _shape_mesh(
    archive_path: str, shape_name: str
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]] | None:
    """Every visual-scene triangle of a stock shape in local metres (node transforms applied)."""

    member = shape_name.lstrip("/")
    with zipfile.ZipFile(archive_path) as archive:
        if member not in archive.namelist():
            return None
        root = ET.fromstring(archive.read(member))
    unit = root.find("c:asset/c:unit", COLLADA)
    scale = float(unit.attrib.get("meter", "1")) if unit is not None else 1.0
    meshes = _geometry_meshes(root)
    positions: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []

    def visit(node: ET.Element, parent: list[list[float]]) -> None:
        local = _collada_matrix(node)
        world = [
            [sum(parent[r][k] * local[k][c] for k in range(4)) for c in range(4)] for r in range(4)
        ]
        for instance in node.findall("c:instance_geometry", COLLADA):
            mesh = meshes.get(instance.attrib.get("url", "").lstrip("#"))
            if mesh is None:
                continue
            base = len(positions)
            for vertex in mesh[0]:
                positions.append(
                    tuple(
                        (
                            world[r][0] * vertex[0]
                            + world[r][1] * vertex[1]
                            + world[r][2] * vertex[2]
                            + world[r][3]
                        )
                        * scale
                        for r in range(3)
                    )
                )
            triangles.extend((base + a, base + b, base + c) for a, b, c in mesh[1])
        for child in node.findall("c:node", COLLADA):
            visit(child, world)

    identity = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    for scene in root.findall(".//c:library_visual_scenes/c:visual_scene", COLLADA):
        for node in scene.findall("c:node", COLLADA):
            visit(node, identity)
    if not positions:
        return None
    return positions, triangles


def _point_to_triangle_xy(a, b, c) -> float:
    px, py = SITE
    # Inside test via signed areas.
    d1 = (px - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (py - b[1])
    d2 = (px - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (py - c[1])
    d3 = (px - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (py - a[1])
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    if not (has_neg and has_pos):
        return 0.0
    return min(_point_to_segment_xy(a, b), _point_to_segment_xy(b, c), _point_to_segment_xy(c, a))


def _exact_mesh_distance(transform, mesh) -> float:
    position, rotation, scale = transform
    world_points = []
    for vertex in mesh[0]:
        scaled = (vertex[0] * scale[0], vertex[1] * scale[1], vertex[2] * scale[2])
        rotated = _mat_vec(rotation, scaled)
        world_points.append((position[0] + rotated[0], position[1] + rotated[1]))
    best = math.inf
    if mesh[1]:
        for a, b, c in mesh[1]:
            best = min(
                best, _point_to_triangle_xy(world_points[a], world_points[b], world_points[c])
            )
            if best == 0.0:
                break
    else:
        for point in world_points:
            best = min(best, math.hypot(point[0] - SITE[0], point[1] - SITE[1]))
    return best


def _geometry_bboxes(root: ET.Element) -> dict[str, tuple[list[float], list[float]]]:
    boxes: dict[str, tuple[list[float], list[float]]] = {}
    for geometry_id, (positions, _triangles) in _geometry_meshes(root).items():
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        zs = [p[2] for p in positions]
        boxes[geometry_id] = ([min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)])
    return boxes


@functools.cache
def _shape_extents(
    archive_path: str, shape_name: str
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    """Local-space AABB of a stock shape (units + visual-scene node transforms applied)."""

    member = shape_name.lstrip("/")
    with zipfile.ZipFile(archive_path) as archive:
        if member not in archive.namelist():
            return None
        root = ET.fromstring(archive.read(member))
    unit = root.find("c:asset/c:unit", COLLADA)
    scale = float(unit.attrib.get("meter", "1")) if unit is not None else 1.0
    boxes = _geometry_bboxes(root)
    lo = [math.inf] * 3
    hi = [-math.inf] * 3

    def visit(node: ET.Element, parent: list[list[float]]) -> None:
        local = _collada_matrix(node)
        world = [
            [sum(parent[r][k] * local[k][c] for k in range(4)) for c in range(4)] for r in range(4)
        ]
        for instance in node.findall("c:instance_geometry", COLLADA):
            box = boxes.get(instance.attrib.get("url", "").lstrip("#"))
            if box is None:
                continue
            for corner in (
                (x, y, z)
                for x in (box[0][0], box[1][0])
                for y in (box[0][1], box[1][1])
                for z in (box[0][2], box[1][2])
            ):
                point = [
                    world[r][0] * corner[0]
                    + world[r][1] * corner[1]
                    + world[r][2] * corner[2]
                    + world[r][3]
                    for r in range(3)
                ]
                for axis in range(3):
                    lo[axis] = min(lo[axis], point[axis] * scale)
                    hi[axis] = max(hi[axis], point[axis] * scale)
        for child in node.findall("c:node", COLLADA):
            visit(child, world)

    identity = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    for scene in root.findall(".//c:library_visual_scenes/c:visual_scene", COLLADA):
        for node in scene.findall("c:node", COLLADA):
            visit(node, identity)
    if any(math.isinf(v) for v in lo + hi):
        return None
    return (tuple(lo), tuple(hi))  # type: ignore[return-value]


# --- TorqueScript .prefab parsing ---------------------------------------------


_OBJECT_OPEN = re.compile(r"new\s+(\w+)\s*\(\s*\)\s*\{")
_FIELD = re.compile(r'^\s*([A-Za-z_][\w\[\]]*)\s*=\s*"((?:[^"\\]|\\.)*)"\s*;\s*$', re.MULTILINE)


def _parse_prefab_objects(text: str) -> list[dict[str, Any]]:
    """Every ``new Class() { ... }`` block as {class, fields, children}."""

    objects: list[dict[str, Any]] = []
    stack: list[tuple[dict[str, Any], int]] = []
    index = 0
    while index < len(text):
        match = _OBJECT_OPEN.search(text, index)
        if match is None:
            break
        entry = {"class": match.group(1), "fields": {}, "children": [], "_start": match.end()}
        depth = 1
        cursor = match.end()
        while cursor < len(text) and depth > 0:
            char = text[cursor]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            cursor += 1
        body = text[match.end() : cursor - 1]
        # Own fields: strip nested object bodies first.
        own = _strip_nested(body)
        entry["fields"] = {k: v for k, v in _FIELD.findall(own)}
        entry["children"] = _parse_prefab_objects(body)
        objects.append(entry)
        index = cursor
    return objects


def _strip_nested(body: str) -> str:
    out = []
    depth = 0
    index = 0
    while index < len(body):
        match = _OBJECT_OPEN.search(body, index)
        if match is None:
            out.append(body[index:])
            break
        out.append(body[index : match.start()])
        depth = 1
        cursor = match.end()
        while cursor < len(body) and depth > 0:
            if body[cursor] == "{":
                depth += 1
            elif body[cursor] == "}":
                depth -= 1
            cursor += 1
        index = cursor
    return "".join(out)


def _transpose(m: Matrix) -> Matrix:
    return (m[0], m[3], m[6], m[1], m[4], m[7], m[2], m[5], m[8])


def _record_transform(
    record: dict[str, Any], convention: str
) -> tuple[tuple[float, float, float], Matrix, tuple[float, float, float]]:
    position = _parse_vec(record.get("position"), (0.0, 0.0, 0.0))
    rotation = _parse_vec(record.get("rotationMatrix"), IDENTITY)
    if convention == "transposed":
        rotation = _transpose(rotation)
    scale = _parse_vec(record.get("scale"), (1.0, 1.0, 1.0))
    return position, rotation, scale  # type: ignore[return-value]


def _compose(
    parent: tuple[tuple[float, float, float], Matrix, tuple[float, float, float]],
    child: tuple[tuple[float, float, float], Matrix, tuple[float, float, float]],
) -> tuple[tuple[float, float, float], Matrix, tuple[float, float, float]]:
    p_pos, p_rot, p_scale = parent
    c_pos, c_rot, c_scale = child
    scaled = (c_pos[0] * p_scale[0], c_pos[1] * p_scale[1], c_pos[2] * p_scale[2])
    offset = _mat_vec(p_rot, scaled)
    position = (p_pos[0] + offset[0], p_pos[1] + offset[1], p_pos[2] + offset[2])
    rotation = _mat_mul(p_rot, c_rot)
    scale = (p_scale[0] * c_scale[0], p_scale[1] * c_scale[1], p_scale[2] * c_scale[2])
    return position, rotation, scale


def _world_aabb(
    transform: tuple[tuple[float, float, float], Matrix, tuple[float, float, float]],
    extents: tuple[tuple[float, float, float], tuple[float, float, float]],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    position, rotation, scale = transform
    lo_l, hi_l = extents
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for corner in (
        (x, y, z)
        for x in (lo_l[0], hi_l[0])
        for y in (lo_l[1], hi_l[1])
        for z in (lo_l[2], hi_l[2])
    ):
        scaled = (corner[0] * scale[0], corner[1] * scale[1], corner[2] * scale[2])
        rotated = _mat_vec(rotation, scaled)
        for axis in range(3):
            value = position[axis] + rotated[axis]
            lo[axis] = min(lo[axis], value)
            hi[axis] = max(hi[axis], value)
    return tuple(lo), tuple(hi)  # type: ignore[return-value]


# --- the sweep ----------------------------------------------------------------


def _sweep(archive_path: Path, convention: str) -> dict[str, Any]:
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        items = [n for n in names if n.endswith("items.level.json")]
        prefab_files = {
            "/" + n: archive.read(n).decode("utf-8", "replace")
            for n in names
            if n.endswith(".prefab")
        }
        records: list[tuple[str, dict[str, Any]]] = []
        for member in items:
            for line in archive.read(member).decode("utf-8", "replace").splitlines():
                if line.strip():
                    records.append((member, json.loads(line)))

    hits: list[dict[str, Any]] = []
    groundplane_touching: list[dict[str, Any]] = []
    render_disabled_children = 0
    scan_radius = CLEARANCE_M + 400.0

    def consider_shape(label: str, shape_name: str, transform, source: str) -> None:
        nonlocal render_disabled_children
        centre_distance = math.hypot(transform[0][0] - SITE[0], transform[0][1] - SITE[1])
        if centre_distance > scan_radius:
            return
        extents = _shape_extents(str(archive_path), shape_name)
        if extents is None:
            hits.append(
                {
                    "label": label,
                    "shape": shape_name,
                    "distance": centre_distance,
                    "extents": "unknown",
                    "source": source,
                }
            )
            return
        lo, hi = _world_aabb(transform, extents)
        distance = _point_to_aabb_xy((lo[0], lo[1]), (hi[0], hi[1]))
        entry = {
            "label": label,
            "shape": shape_name,
            "distance": distance,
            "aabb": [list(lo), list(hi)],
            "source": source,
            "bound": "aabb",
        }
        if GROUNDPLANE_PATTERN.search(shape_name):
            if distance <= GLACIS_TOE_M:
                groundplane_touching.append(entry)
            return
        # The box is a lower bound. Anything whose box comes near the line
        # gets the exact XY point-to-triangle distance over its real mesh (a
        # 350 x 540 m curved motorway turn's box reaches 130 m; its asphalt
        # does not).
        if distance < CLEARANCE_M + 30.0:
            mesh = _shape_mesh(str(archive_path), shape_name)
            if mesh is not None:
                entry["aabb_distance"] = distance
                entry["distance"] = _exact_mesh_distance(transform, mesh)
                entry["bound"] = "mesh"
                entry["triangles"] = len(mesh[1])
        hits.append(entry)

    def expand_prefab(record_name: str, filename: str, transform, depth: int, source: str) -> None:
        text = prefab_files.get(filename)
        if text is None or depth > 4:
            hits.append(
                {
                    "label": record_name,
                    "shape": filename,
                    "distance": 0.0,
                    "extents": "prefab file missing",
                    "source": source,
                }
            )
            return

        def walk(objects: list[dict[str, Any]], parent_transform) -> None:
            nonlocal render_disabled_children
            for obj in objects:
                fields = obj["fields"]
                cls = obj["class"]
                own = _record_transform(fields, convention)
                if cls == "SimGroup":
                    walk(obj["children"], parent_transform)
                    continue
                world = _compose(parent_transform, own)
                if cls == "TSStatic" and fields.get("shapeName"):
                    if fields.get("isRenderEnabled", "true").lower() == "false":
                        render_disabled_children += 1
                    consider_shape(
                        f"{record_name}/{fields.get('shapeName').split('/')[-1]}",
                        fields["shapeName"],
                        world,
                        source,
                    )
                elif cls == "Prefab" and fields.get("filename"):
                    expand_prefab(
                        f"{record_name}/{fields.get('filename')}",
                        fields["filename"],
                        world,
                        depth + 1,
                        source,
                    )
                elif cls in {"DecalRoad", "River"}:
                    pass  # nested roads inside prefabs do not occur in gridmap_v2
                if obj["children"]:
                    walk(obj["children"], world)

        walk(_parse_prefab_objects(text), transform)

    for member, record in records:
        cls = record.get("class")
        name = str(record.get("name") or record.get("persistentId"))
        if cls == "TSStatic" and record.get("shapeName"):
            consider_shape(
                name, str(record["shapeName"]), _record_transform(record, convention), member
            )
        elif cls == "Prefab" and record.get("filename"):
            expand_prefab(
                name, str(record["filename"]), _record_transform(record, convention), 0, member
            )
        elif cls in {"DecalRoad", "River", "MeshRoad"} and isinstance(record.get("nodes"), list):
            nodes = [
                tuple(float(v) for v in node[:4]) for node in record["nodes"] if len(node) >= 3
            ]
            best = math.inf
            for index in range(len(nodes)):
                a = nodes[index]
                b = nodes[index + 1] if index + 1 < len(nodes) else a
                half_width = max(a[3] if len(a) > 3 else 0.0, b[3] if len(b) > 3 else 0.0) / 2.0
                best = min(best, _point_to_segment_xy((a[0], a[1]), (b[0], b[1])) - half_width)
            if best < scan_radius:
                hits.append(
                    {
                        "label": name,
                        "shape": f"{cls}:{record.get('material', '')}",
                        "distance": best,
                        "source": member,
                    }
                )
        elif cls in {
            "TerrainBlock",
            "WaterBlock",
            "GroundCover",
            "ForestBrushElement",
            "SpawnSphere",
            "PointLight",
            "CameraBookmark",
            "BeamNGWaypoint",
            "SimGroup",
            "LevelInfo",
            "TimeOfDay",
            "ScatterSky",
            "CloudLayer",
            "ForestWindEmitter",
            "BeamNGGameplayArea",
            "BeamNGPointOfInterest",
        }:
            continue
        else:
            position = record.get("position")
            if isinstance(position, list) and len(position) >= 2:
                distance = math.hypot(float(position[0]) - SITE[0], float(position[1]) - SITE[1])
                if distance < scan_radius:
                    hits.append(
                        {"label": name, "shape": f"{cls}", "distance": distance, "source": member}
                    )

    hits.sort(key=lambda entry: entry["distance"])
    return {
        "convention": convention,
        "nearest": hits[:12],
        "groundplane_touching": groundplane_touching,
        "render_disabled_children": render_disabled_children,
        "record_count": len(records),
    }


@pytest.fixture(scope="module")
def sweeps() -> dict[str, dict[str, Any]]:
    archive = _level_zip()
    return {name: _sweep(archive, name) for name in ("standard", "transposed")}


@pytest.fixture(scope="module")
def sweep(sweeps: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return sweeps[ENGINE_CONVENTION]


def test_both_matrix_conventions_are_reported_and_disagree_on_this_site(
    sweeps: dict[str, dict[str, Any]],
) -> None:
    # The two readings must be materially different here, or the pin above is
    # not load-bearing and the live witness probe is not testing anything.
    standard = sweeps["standard"]["nearest"][0]["distance"]
    transposed = sweeps["transposed"]["nearest"][0]["distance"]
    assert abs(standard - transposed) > 10.0, {"standard": standard, "transposed": transposed}
    assert sweeps["standard"]["record_count"] == sweeps["transposed"]["record_count"]


def test_nothing_stock_enters_the_155m_clearance_radius(sweep: dict[str, Any]) -> None:
    nearest = sweep["nearest"]
    assert nearest, "the sweep saw no stock geometry at all - parser broken"
    assert all(entry.get("extents") is None for entry in nearest), nearest
    closest = nearest[0]
    assert closest["distance"] > CLEARANCE_M, {
        "detail": "stock geometry inside the arena clearance radius",
        "convention": sweep["convention"],
        "nearest": nearest[:5],
    }


def test_nearest_stock_geometry_is_a_known_interzone_stack(sweep: dict[str, Any]) -> None:
    closest = sweep["nearest"][0]
    # Design F6 / critique Fix C named p_gm_interzone_structure4's cube stack
    # (~160 m) from identity-rotation expansion; composing the rotated
    # neighbours (structures 10/11) is what erratum 3 demanded. Whichever
    # stack is nearest, it must be one of the interzone cube structures and
    # sit between the clearance line and the design's 170 m claim.
    assert "p_gm_interzone_structure" in closest["label"], closest
    assert closest["shape"].endswith("s_gm_cube_4m.dae"), closest
    assert CLEARANCE_M < closest["distance"] < 175.0, closest


def test_groundplane_tiles_under_the_arena_sit_at_grade(sweep: dict[str, Any]) -> None:
    tiles = sweep["groundplane_touching"]
    assert tiles, "no groundplane tile reaches the arena footprint"
    for tile in tiles:
        lo, hi = tile["aabb"]
        assert abs(hi[2] - 100.0) < 0.05, tile
