"""BeamNG ``.ter`` v9 terrain I/O and the Giant's Hearth heightmap for the standalone level.

Binary format (little-endian), verified against the stock ``template.zip``
(3,145,775 B = 5 + 1024**2 * 3 + 42) and ``johnson_valley.zip`` (size 4096,
14 materials, 153 B tail, 0 B left over)::

    u8  version (9)
    u32 size N
    u16 heights[N * N]
    u8  layer ids[N * N]          (index into the material name table)
    u32 material count
    count x (u8 length, ASCII material internalName)

The sidecar ``<stem>.terrain.json`` string says ``layerTextureMap`` follows the
layer map; the byte counts above prove no such block exists in v9 files.

Height mapping, MEASURED live on the sentinel profile (report_B §3.1): the
engine divides by 65536, not 65535::

    z_world = TerrainBlock.position.z + u16 * TerrainBlock.maxHeight / 65536

Constants for the Giant's Hearth level (design v4 §1, `terrain_model`)::

    N = 2048, squareSize = 1.0 m  -> 2,047 m usable (half-open), 1 km of basin
                                    in every direction around the anchor
    position = (-174, -1304, 0)   -> C = (850, -280) is the centre node
    maxHeight = 320.0 m           -> one u16 unit is EXACTLY 5/1024 m
                                    (4.8828125 mm, binary-exact), z = 100.000 is
                                    u = 20480 exactly, ceiling 319.995 m

The HEIGHT AND PAINT LAW itself is not authored here: it is
``examples/hot_potato_arena/level/terrain_model.py``, vendored byte-for-byte
from the frozen design spec (sha256 ``36f275eeb9c292c0...``, recorded in
``authoring/level_design_v4.lock.json``). This module only quantises what that
model produces into the engine's file format, so the shipped ``.ter`` and the
design's verification table (``authoring/…terrain_summary.json``) are the same
numbers by construction. ``terrain_model``'s on-disk grid cache is redirected
to the OS temp directory so the repository tree never carries a build artefact.

Measured edge behaviour (report_B §3.3): ``getTerrainHeight`` at the min-edge
node reads the authored height, at the max-edge node (index N-1) it reads 0 ->
the covered area is the half-open ``[position, position + (N-1) * squareSize)``
on each axis. A ``castRayStatic`` exactly on a min-edge plane returns
``position.z``; half a cell inward every ray reads the terrain. Never sample on
the terrain's edge planes.

Grid convention (hypothesis H0, PROVEN live: ``xfast``): ``heights[j, i]`` with
``i`` the x index (fastest in the file) and ``j`` the y index, node ``(i, j)``
at world ``(position.x + i * squareSize, position.y + j * squareSize)``.

Off-node interpolation, MEASURED (report_B §3.4): ``castRayStatic`` reads the
BILINEAR value across the cell, ``core_terrain.getTerrainHeight`` triangulates
each cell along its (0,0)-(1,1) diagonal. Everything that must sit ON the
surface is authored from ``surface_z`` (= the bilinear collision surface).
"""

from __future__ import annotations

import json
import math
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from examples.hot_potato_arena.level import brink, terrain_model

TER_VERSION = 9
HEIGHT_UNITS = 65535  # largest u16 the file can hold
HEIGHT_DIVISOR = 65536  # the engine's height divisor (measured, see module docstring)
MAX_MATERIAL_NAME = 255

LEVEL_ID = "ericrolph_hot_potato_arena"
#: The arena's world anchor; every authored coordinate hangs off it.
CENTER = (terrain_model.CX, terrain_model.CY, terrain_model.Z_FLOOR)
TERRAIN_SIZE = terrain_model.N  # 2048
SQUARE_SIZE = terrain_model.SQUARE  # 1.0
TERRAIN_POSITION = terrain_model.POSITION  # (-174, -1304, 0)
MAX_HEIGHT = terrain_model.MAX_HEIGHT  # 320.0
HEIGHT_UNIT_M = terrain_model.UNIT_M  # 5/1024 m exactly
U_FLOOR = terrain_model.U_FLOOR  # 20480 == z 100.000
FLAT_RADIUS_M = terrain_model.FLAT_R  # 210.0: exactly 100.000 inside
APRON_RADIUS_M = 113.0  # the arena's glacis toe (ASPHALT-class apron inside)
CLEAR_RADIUS_M = terrain_model.CLEAR_R  # 350.0
TRACK_R = terrain_model.TRACK_R  # 248.0
LAKE_LEVEL = terrain_model.LAKE_LEVEL  # 98.0 (the WaterPlane's z)
RELIEF_LAW_M = terrain_model.RELIEF_LAW_M  # 0.020 m second-difference law

#: Terrain material internalNames in layer-id order (index = u8 layer id).
#: Design v4 §2.4 pins these BARE names: the ``.ter`` layer table, every
#: ``GroundCover.layer`` and every ``TerrainMaterial.internalName`` must agree,
#: and B3's ground covers are authored against this exact list. The MATERIAL
#: OBJECT names (the document keys in ``art/terrains/main.materials.json``) are
#: namespaced ``ericrolph_hot_potato_arena_t_<layer>``.
MATERIALS: tuple[str, ...] = tuple(terrain_model.LAYERS)
LAYER_ID = dict(terrain_model.LAYER_ID)

#: Ground model per layer (design v4 §2.4); ERHP_* are level-scoped (groundModels/).
LAYER_GROUNDMODEL = {
    "hearth": "ASPHALT",
    "ash": "ERHP_ASH",
    "scorch": "ERHP_SCORCH",
    "trail": "ERHP_TRAIL",
    "meadow": "GRASS",
    "forest_floor": "ERHP_FOREST_FLOOR",
    "scree": "GRAVEL",
    "rock": "ROCK",
    "shore": "SAND",
    "lakebed": "MUD",
    "alpine": "GRASS",
}

#: The terrain-model grid cache never lands in the repository tree.
GRID_CACHE_DIR = Path(tempfile.gettempdir()) / "beamng_mcp_hot_potato_arena_terrain"


class TerrainError(RuntimeError):
    """A .ter payload or the authored spec violates the format contract."""


@dataclass(frozen=True)
class TerrainSpec:
    size: int = TERRAIN_SIZE
    square_size: float = SQUARE_SIZE
    position: tuple[float, float, float] = TERRAIN_POSITION
    max_height: float = MAX_HEIGHT
    materials: tuple[str, ...] = MATERIALS

    @property
    def unit_m(self) -> float:
        return self.max_height / HEIGHT_DIVISOR

    @property
    def extent_m(self) -> float:
        return self.size * self.square_size

    def units_to_height(self, units: int | np.ndarray) -> Any:
        """The measured engine law: z = position.z + u * maxHeight / 65536."""

        return (
            self.position[2]
            + np.asarray(units, dtype=np.float64) * self.max_height / HEIGHT_DIVISOR
        )

    def height_to_units(self, z: float | np.ndarray) -> Any:
        raw = np.rint(
            (np.asarray(z, dtype=np.float64) - self.position[2]) * HEIGHT_DIVISOR / self.max_height
        )
        return np.clip(raw, 0, HEIGHT_UNITS).astype(np.uint16)

    def node_world(self, i: int, j: int) -> tuple[float, float]:
        """World XY of grid node (i = x index, j = y index) under hypothesis H0."""

        return (self.position[0] + i * self.square_size, self.position[1] + j * self.square_size)

    def world_to_index(self, x: float, y: float) -> tuple[float, float]:
        return (
            (x - self.position[0]) / self.square_size,
            (y - self.position[1]) / self.square_size,
        )

    def corners(self) -> dict[str, tuple[float, float]]:
        """World XY of the four corner NODES (index 0 and N-1; the N-1 edge reads 0 live)."""

        last = self.size - 1
        return {
            "sw": self.node_world(0, 0),
            "se": self.node_world(last, 0),
            "nw": self.node_world(0, last),
            "ne": self.node_world(last, last),
        }


#: Shared default spec (a frozen dataclass, so it is safe as a default argument).
DEFAULT_SPEC = TerrainSpec()


# --- binary format -------------------------------------------------------------


def write_ter_bytes(
    heights: np.ndarray, layers: np.ndarray, materials: tuple[str, ...] | list[str]
) -> bytes:
    """Serialise a v9 terrain. ``heights`` is uint16 [N, N], ``layers`` uint8 [N, N]."""

    if heights.ndim != 2 or heights.shape[0] != heights.shape[1]:
        raise TerrainError(f"heights must be square, got {heights.shape}")
    size = int(heights.shape[0])
    if layers.shape != heights.shape:
        raise TerrainError("layers must have the heightmap's shape")
    if heights.dtype != np.uint16 or layers.dtype != np.uint8:
        raise TerrainError("heights must be uint16 and layers uint8")
    if not materials or len(materials) > 255:
        raise TerrainError("1..255 material names are required")
    if int(layers.max()) >= len(materials):
        raise TerrainError("a layer id exceeds the material table")
    parts = [struct.pack("<BI", TER_VERSION, size)]
    parts.append(np.ascontiguousarray(heights).astype("<u2").tobytes(order="C"))
    parts.append(np.ascontiguousarray(layers).tobytes(order="C"))
    parts.append(struct.pack("<I", len(materials)))
    for name in materials:
        encoded = name.encode("ascii")
        if not encoded or len(encoded) > MAX_MATERIAL_NAME:
            raise TerrainError(f"material name must be 1..255 ASCII bytes: {name!r}")
        parts.append(struct.pack("<B", len(encoded)) + encoded)
    return b"".join(parts)


def read_ter_bytes(payload: bytes) -> tuple[int, np.ndarray, np.ndarray, list[str]]:
    """Parse a v9 terrain; refuses trailing bytes so a format drift is loud."""

    if len(payload) < 9:
        raise TerrainError("payload too short for a .ter header")
    version, size = struct.unpack_from("<BI", payload, 0)
    if version != TER_VERSION:
        raise TerrainError(f"unsupported .ter version {version}")
    offset = 5
    count = size * size
    heights = (
        np.frombuffer(payload, dtype="<u2", count=count, offset=offset)
        .reshape(size, size)
        .astype(np.uint16)
    )
    offset += count * 2
    layers = (
        np.frombuffer(payload, dtype=np.uint8, count=count, offset=offset)
        .reshape(size, size)
        .copy()
    )
    offset += count
    (material_count,) = struct.unpack_from("<I", payload, offset)
    offset += 4
    materials: list[str] = []
    for _ in range(material_count):
        (length,) = struct.unpack_from("<B", payload, offset)
        offset += 1
        materials.append(payload[offset : offset + length].decode("ascii"))
        offset += length
    if offset != len(payload):
        raise TerrainError(f"{len(payload) - offset} unexpected trailing bytes in .ter payload")
    return int(size), heights, layers, materials


def write_ter(
    path: Path, heights: np.ndarray, layers: np.ndarray, materials: tuple[str, ...]
) -> bytes:
    payload = write_ter_bytes(heights, layers, materials)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def read_ter(path: Path) -> tuple[int, np.ndarray, np.ndarray, list[str]]:
    return read_ter_bytes(path.read_bytes())


def ter_member_size(spec: TerrainSpec = DEFAULT_SPEC) -> int:
    """Exact .ter byte count: 5 + 3 * N^2 + 4 + sum(1 + len(name))."""

    return 5 + 3 * spec.size * spec.size + 4 + sum(1 + len(n) for n in spec.materials)


def terrain_sidecar(spec: TerrainSpec, ter_relative_path: str) -> dict[str, Any]:
    """The ``<stem>.terrain.json`` sidecar (stock keys; heightmapImage is informational)."""

    count = spec.size * spec.size
    return {
        "binaryFormat": (
            "version(char), size(unsigned int), heightMap(heightMapSize * heightMapItemSize), "
            "layerMap(layerMapSize * layerMapItemSize), materialNames"
        ),
        "datafile": ter_relative_path,
        "heightMapItemSize": 2,
        "heightMapSize": count,
        "layerMapItemSize": 1,
        "layerMapSize": count,
        "materials": list(spec.materials),
        "size": spec.size,
        "version": TER_VERSION,
    }


#: Pixel size of the whole-terrain base maps (design §2.5: 4096^2 = 0.5 m/texel
#: on a 2,048 m block, the WCUSA/small_island class). JV's TerrainBlock carries
#: the same number for the same reason: it is the base map's resolution.
BASE_MAP_PX = 4096


def terrain_block_record(
    spec: TerrainSpec, ter_relative_path: str, texture_set: str, persistent_id: str
) -> dict[str, Any]:
    return {
        "name": "theTerrain",
        "class": "TerrainBlock",
        "persistentId": persistent_id,
        "__parent": "terrain",
        "position": [float(v) for v in spec.position],
        "baseTexSize": BASE_MAP_PX,
        "materialTextureSet": texture_set,
        "maxHeight": float(spec.max_height),
        "squareSize": float(spec.square_size),
        "terrainFile": ter_relative_path,
    }


# --- the authored terrain (delegated to the frozen design model) ---------------------


def _model() -> Any:
    """``terrain_model`` with its grid cache redirected out of the repository tree."""

    GRID_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    terrain_model.HERE = GRID_CACHE_DIR
    return terrain_model


_PAINTED: dict[str, Any] | None = None


def grid() -> dict[str, Any]:
    """The design model's 2048^2 grid (xs, ys, u, zq, layers, road_d, trail_d), PAINTED.

    r17: the frozen model is vendored byte-for-byte, so B1's brink band (``brink.py``) is
    applied here, once, on a COPY of the model's memoised grid. This is the only door to
    the layers - ``build_heightmap``, the cook, the planter and :func:`layer_at` all read
    this dict. A reader that calls ``terrain_model.get_grid()`` directly sees the world
    WITHOUT the band, and critic pass 16 named the three that did.
    """

    global _PAINTED
    if _PAINTED is None:
        _PAINTED = brink.painted_grid(_model().get_grid())
    return _PAINTED


def bearing_point(bearing_deg: float, r: float) -> tuple[float, float]:
    """World XY at a compass bearing (0 = +Y, 90 = +X) and radius from C."""

    theta = math.radians(bearing_deg)
    return (CENTER[0] + r * math.sin(theta), CENTER[1] + r * math.cos(theta))


def polar(x: float | np.ndarray, y: float | np.ndarray) -> tuple[Any, Any]:
    dx = np.asarray(x, dtype=np.float64) - CENTER[0]
    dy = np.asarray(y, dtype=np.float64) - CENTER[1]
    return np.hypot(dx, dy), np.degrees(np.arctan2(dx, dy)) % 360.0


def surface_z(x: float, y: float) -> float:
    """The collision surface at (x, y): bilinear over the QUANTISED grid (report_B §3.4)."""

    return float(_model().z_at(x, y))


def surface_z_arr(x: Any, y: Any) -> Any:
    return _model().z_at_arr(x, y)


def layer_at(x: float, y: float) -> str:
    """The PAINTED layer under (x, y), by the model's own nearest-node rule."""

    g = grid()
    i = round((x - g["xs"][0]) / terrain_model.SQUARE)
    j = round((y - g["ys"][0]) / terrain_model.SQUARE)
    return str(terrain_model.LAYERS[int(g["layers"][j, i])])


def build_heightmap(spec: TerrainSpec = DEFAULT_SPEC) -> tuple[np.ndarray, np.ndarray]:
    """Quantised heights (uint16 [j, i]) and layer ids (uint8 [j, i]) for the spec."""

    if (spec.size, spec.square_size, spec.max_height) != (
        TERRAIN_SIZE,
        SQUARE_SIZE,
        MAX_HEIGHT,
    ):
        raise TerrainError("the design model only builds the shipped 2048 / 1.0 m / 320 m grid")
    g = grid()
    return np.ascontiguousarray(g["u"], dtype=np.uint16), np.ascontiguousarray(
        g["layers"], dtype=np.uint8
    )


def depth_map_png_array(spec: TerrainSpec = DEFAULT_SPEC) -> np.ndarray:
    """``<stem>.ter.depth.png`` payload (design §2.5): 8-bit L, 255 dry.

    B0 measured that a value-255 depth PNG removes the engine's
    ``depth image map not existing ... all fluids will be disabled`` D line with
    the tires unaffected. The lake bed carries JV's 220..255 range so the shipped
    map is a real one rather than a flat placeholder: ``255 - clip((98 - z)/12 * 60)``.
    """

    g = grid()
    z = np.asarray(g["zq"], dtype=np.float64)
    depth = np.clip((LAKE_LEVEL - z) / 12.0, 0.0, 1.0) * 60.0
    return np.clip(255.0 - depth, 0.0, 255.0).astype(np.uint8)[::-1, :]


# --- interpolation predictors (the measured live laws) ------------------------------


def _triangle(
    u: float,
    v: float,
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> float:
    """Barycentric height at cell-local (u, v) on the triangle a, b, c = (u, v, z)."""

    (ua, va, za), (ub, vb, zb), (uc, vc, zc) = a, b, c
    det = (vb - vc) * (ua - uc) + (uc - ub) * (va - vc)
    lam_a = ((vb - vc) * (u - uc) + (uc - ub) * (v - vc)) / det
    lam_b = ((vc - va) * (u - uc) + (ua - uc) * (v - vc)) / det
    lam_c = 1.0 - lam_a - lam_b
    return lam_a * za + lam_b * zb + lam_c * zc


def sample_heights(spec: TerrainSpec, heights: np.ndarray, x: float, y: float) -> dict[str, float]:
    """Predicted engine height at world (x, y) under H0 for five interpolations.

    ``node``: nearest node (exact when x, y sit on the grid); ``bilinear``; ``fan``
    (four triangles meeting at a centre vertex whose height is the four-corner
    mean); and the two 2-triangle splits a terrain cell can use: ``tri_main``
    splits along the (0,0)-(1,1) diagonal (south-west to north-east), so at the
    cell centre it reads (h00 + h11) / 2; ``tri_anti`` splits along the
    (1,0)-(0,1) diagonal and reads (h10 + h01) / 2 there. Measured live:
    ``castRayStatic`` = ``bilinear``, ``core_terrain.getTerrainHeight`` =
    ``tri_main``. Corner naming: h<i><j> with i along x and j along y.
    """

    fi, fj = spec.world_to_index(x, y)
    i0 = math.floor(fi)
    j0 = math.floor(fj)
    last = spec.size - 1
    i0 = min(max(i0, 0), last - 1)
    j0 = min(max(j0, 0), last - 1)
    u = fi - i0
    v = fj - j0
    h = spec.units_to_height(heights[j0 : j0 + 2, i0 : i0 + 2].astype(np.int64))
    h00, h10, h01, h11 = float(h[0, 0]), float(h[0, 1]), float(h[1, 0]), float(h[1, 1])
    c00, c10, c01, c11 = (0.0, 0.0, h00), (1.0, 0.0, h10), (0.0, 1.0, h01), (1.0, 1.0, h11)
    bilinear = (1 - u) * (1 - v) * h00 + u * (1 - v) * h10 + (1 - u) * v * h01 + u * v * h11
    # (0,0)-(1,1) diagonal is the line u == v: below it the (0,0),(1,0),(1,1) triangle.
    if u >= v:
        tri_main = _triangle(u, v, c00, c10, c11)
    else:
        tri_main = _triangle(u, v, c00, c01, c11)
    # (1,0)-(0,1) diagonal is the line u + v == 1: below it the (0,0),(1,0),(0,1) triangle.
    if u + v <= 1.0:
        tri_anti = _triangle(u, v, c00, c10, c01)
    else:
        tri_anti = _triangle(u, v, c10, c01, c11)
    centre = (0.5, 0.5, (h00 + h10 + h01 + h11) / 4.0)
    if v <= u and v <= 1.0 - u:
        fan = _triangle(u, v, c00, c10, centre)  # south
    elif u >= v:
        fan = _triangle(u, v, c10, c11, centre)  # east
    elif v >= 1.0 - u:
        fan = _triangle(u, v, c01, c11, centre)  # north
    else:
        fan = _triangle(u, v, c00, c01, centre)  # west
    ni = round(fi)
    nj = round(fj)
    node = float(spec.units_to_height(int(heights[min(max(nj, 0), last), min(max(ni, 0), last)])))
    return {
        "node": node,
        "bilinear": float(bilinear),
        "fan": float(fan),
        "tri_main": float(tri_main),
        "tri_anti": float(tri_anti),
    }


INTERPOLATIONS = ("bilinear", "fan", "tri_main", "tri_anti")


MAPPING_CANDIDATES: tuple[dict[str, Any], ...] = tuple(
    {
        "name": f"{'transpose' if t else 'xfast'}{'_flipx' if fx else ''}{'_flipy' if fy else ''}",
        "transpose": t,
        "flip_x": fx,
        "flip_y": fy,
    }
    for t in (False, True)
    for fx in (False, True)
    for fy in (False, True)
)


def height_under_mapping(
    spec: TerrainSpec, heights: np.ndarray, x: float, y: float, mapping: dict[str, Any]
) -> float:
    """Height the engine would report at grid node (x, y) if it read the file under ``mapping``.

    ``heights`` is the array as WRITTEN (row = file row j, col = file column i).
    A mapping says how the engine turns a file cell into a world node: flips
    reverse an axis (origin at the opposite corner), transpose swaps which file
    index runs along world x.
    """

    fi, fj = spec.world_to_index(x, y)
    a = round(fi)
    b = round(fj)
    last = spec.size - 1
    if not (0 <= a <= last and 0 <= b <= last):
        raise TerrainError(f"({x}, {y}) is off the terrain")
    if mapping["flip_x"]:
        a = last - a
    if mapping["flip_y"]:
        b = last - b
    row, col = (a, b) if mapping["transpose"] else (b, a)
    return float(spec.units_to_height(int(heights[row, col])))


# --- measurement helpers the gates share --------------------------------------------


def second_differences(z: np.ndarray) -> np.ndarray:
    """|z[i-1] - 2 z[i] + z[i+1]| over both axes, as the relief law is stated (design §2.7).

    The returned array is [2, N, N]: axis 0 = the x direction, axis 1 = y; the
    outermost row/column of each direction is NaN (no centred stencil there).
    """

    out = np.full((2, *z.shape), np.nan, dtype=np.float64)
    out[0, :, 1:-1] = np.abs(z[:, :-2] - 2.0 * z[:, 1:-1] + z[:, 2:])
    out[1, 1:-1, :] = np.abs(z[:-2, :] - 2.0 * z[1:-1, :] + z[2:, :])
    return out


def heightmap_summary(spec: TerrainSpec, heights: np.ndarray, layers: np.ndarray) -> dict[str, Any]:
    counts = np.bincount(layers.ravel(), minlength=len(spec.materials))
    total = int(layers.size)
    return {
        "size": spec.size,
        "square_size": spec.square_size,
        "position": list(spec.position),
        "max_height": spec.max_height,
        "unit_m": spec.unit_m,
        "flat_units": int(spec.height_to_units(CENTER[2])),
        "min_units": int(heights.min()),
        "max_units": int(heights.max()),
        "min_z": float(spec.units_to_height(int(heights.min()))),
        "max_z": float(spec.units_to_height(int(heights.max()))),
        "layer_counts": {name: int(counts[index]) for index, name in enumerate(spec.materials)},
        "layer_percent": {
            name: round(float(counts[index]) / total * 100.0, 4)
            for index, name in enumerate(spec.materials)
        },
        "corners_xy": {k: list(v) for k, v in spec.corners().items()},
        "terrain_model_source_hash": terrain_model.source_hash(),
    }


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
