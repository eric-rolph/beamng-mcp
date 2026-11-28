"""B2's hearth shapes, built headless in Blender 4.5.4.

Six stone sources (five hearth giants + the chock) and one ember-crust sector
plate.  Run::

    C:\\Users\\ericr\\Applications\\Blender\\4.5.4\\blender.exe --factory-startup \\
        --background --python examples/hot_potato_arena/level/blender_hearth.py -- \\
        --out mod/levels/ericrolph_hot_potato_arena/art/shapes/hearth

Every geometry helper is imported from B3's ``blender_forest`` -- the shell seal,
the collapse-then-weld decimator, the post-decimation relief re-application and the
quantised COLLADA writer are laws that round already paid for, and re-implementing
them would be re-paying for them.  What is new here:

* **the soot bake.**  Design §3.1 wants the fire side of every stone blackened.  The
  bake is a per-vertex multiplier in the mesh's ``COLOR`` channel, ``SOOT_FLOOR``
  (0.45) at the ash line rising to 1.0 over ``SOOT_TOP_M`` (6 m of WORLD height,
  converted through each stone's own scale), and the material declares
  ``vertColor: true`` inside ``Stages[0]`` -- stock ``italy_rocksface``'s recipe.
  r2: the value is PRE-COMPENSATED through ``srgb_to_linear`` before it is stored,
  because a Blender ``BYTE_COLOR`` attribute holds an sRGB byte and the COLLADA
  exporter writes that byte -- r1 asked for 0.45 and shipped 0.70196.  ``FLOAT_COLOR``
  is not the way out: the exporter drops it entirely (``bake_soot``).
  DEVIATION: the design says "from the inner face upward"; this bake is a function
  of height only, so ONE DAE per source serves all four clusters at their four
  design yaws.  Soot from a bed of coals rises; it does not pick a compass bearing.
* **the crust plate.**  A 20 x 24 displaced grid (960 triangles) over one 15 degree
  sector of r 176-199, authored about its own centroid so the instance carries a
  tight bounding box instead of a 199 m one.

The manifest lands in ``authoring/<id>_hearth_shapes.json``: every DAE's sha256,
size, per-node triangle count, materials, and the soot range that was baked.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from examples.hot_potato_arena.level import blender_forest as bf  # noqa: E402
from examples.hot_potato_arena.level import hearth_spec as hs  # noqa: E402

CACHE = REPO / "examples" / "hot_potato_arena" / "cc0_cache"
OUT_DEFAULT = REPO / "examples" / "hot_potato_arena" / "mod" / "levels" / hs.LEVEL_ID / hs.SHAPE_DIR
#: How many times the crust maps tile across one plate's TANGENTIAL span.  Two, not
#: r2's four, and the radial factor is no longer derived from it -- see
#: :data:`CRUST_RADIAL_TILES`.
CRUST_UV_TILES = 2.0
#: **The map's u axis IS the radius.**  r2 tiled radially as well (1.874 tiles), which
#: made the crust a wallpaper: 96 identical 12.3 m patches around a 200 m ring, with no
#: way for the texture to know where the edge of the bed was.  At exactly one radial
#: tile, column x of every crust map is a fixed radius between 176 and 199 m, so
#: :func:`hearth_textures.cook_crust` can bank the bed -- ash and cold at both rims,
#: hot in the middle -- and the hard cut line critic r2 saw at r 199 feathers itself.
#: The cost is texel density: 23.0 m / 2048 = 11.2 mm radially and 24.5 m / 2048 =
#: 12.0 mm tangentially against r2's 6.0 mm, both still inside design section 8's
#: <= 15 mm/texel.  Texels stay square to within 7 %.
CRUST_RADIAL_TILES = 1.0

MANIFEST = hs.AUTHORING / f"{hs.LEVEL_ID}_hearth_shapes.json"


def _bpy():
    import bpy

    return bpy


def stone_world(asset: str) -> dict[str, float]:
    """The design's world size and sink for the one stone row family this source draws."""

    rows = [s for s in hs.layout()["stones"] if s["asset"] == asset]
    if not rows:
        raise SystemExit(f"{asset}: no stone row in the frozen layout uses it")
    diam = {float(r["diam"]) for r in rows}
    height = {float(r["height"]) for r in rows}
    sink = {abs(float(r["z_offset"])) for r in rows}
    if len(diam) != 1 or len(height) != 1 or len(sink) != 1:
        raise SystemExit(
            f"{asset}: the layout uses it at more than one size {diam} {height} {sink}"
        )
    return {"diam": diam.pop(), "height": height.pop(), "sink": sink.pop(), "count": len(rows)}


def normalise_horizontal(obj, target: float = 1.0, *, keep_floor: bool = False) -> dict[str, float]:
    """Scale so the longest HORIZONTAL axis is ``target`` and the foot sits at z 0.

    ``blender_forest.import_model`` normalises the longest axis of all three, which
    for a tall scan would make the TSStatic's uniform ``scale`` mean something other
    than the design's footprint diameter.  The design's table is a footprint
    diameter x height, so the horizontal span is the control and the height is a
    CHECK printed into the manifest.

    r6, ``keep_floor``: a face-solid's underside is sunk BELOW the scan's foot on
    purpose (``rock_solid.UNDERSIDE_SINK``) and ``import_model`` already put that
    scan foot at z = 0.  Re-seating the mesh on its lowest vertex would lift the
    whole rock out of the ground by the sink, so for those sources the scale (which
    is about the origin, and therefore maps z = 0 to z = 0) is applied and the z
    offset is left alone.
    """

    bpy = _bpy()
    span = max(obj.dimensions[0], obj.dimensions[1])
    if span <= 0:
        raise SystemExit(f"{obj.name}: degenerate footprint")
    factor = target / span
    obj.scale = (factor, factor, factor)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    low = [min(v.co[i] for v in obj.data.vertices) for i in range(3)]
    high = [max(v.co[i] for v in obj.data.vertices) for i in range(3)]
    offset = (-(low[0] + high[0]) / 2.0, -(low[1] + high[1]) / 2.0, 0.0 if keep_floor else -low[2])
    for vertex in obj.data.vertices:
        vertex.co = (vertex.co[0] + offset[0], vertex.co[1] + offset[1], vertex.co[2] + offset[2])
    obj.data.update()
    return {
        "x": round(float(obj.dimensions[0]), 6),
        "y": round(float(obj.dimensions[1]), 6),
        "z": round(float(obj.dimensions[2]), 6),
    }


def stretch_to_design_height(
    obj, world: dict[str, float], *, keep_floor: bool = False
) -> dict[str, float]:
    """Scale z so the unit shape's height x its world diameter IS the design's height.

    The design's §3.1 table is a footprint diameter AND a height, and the scans do
    not come in that ratio (``namaqualand_boulder_02`` is a 2:1 slab and would stand
    7 m where the table says 14).  A non-uniform TSStatic ``scale`` would carry the
    distortion into the Colmesh at runtime, so the stretch is baked into the MESH
    and the record keeps a uniform scale -- footprint and height both true, one
    number in the record.
    """

    bpy = _bpy()
    # r6: for a face solid the design's height is the height a PLAYER sees -- foot
    # (z = 0) to summit -- not the bounding box, which also carries the buried
    # underside; and the mesh must not be re-seated afterwards (see normalise_horizontal)
    above = max(v.co[2] for v in obj.data.vertices)
    span = above if keep_floor else float(obj.dimensions[2])
    current = span * world["diam"]
    if current <= 0:
        raise SystemExit(f"{obj.name}: zero height")
    factor = world["height"] / current
    obj.scale = (1.0, 1.0, factor)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if not keep_floor:
        low = min(v.co[2] for v in obj.data.vertices)
        for vertex in obj.data.vertices:
            vertex.co = (vertex.co[0], vertex.co[1], vertex.co[2] - low)
    obj.data.update()
    return {
        "factor": round(factor, 6),
        "before_m": round(current, 3),
        "after_m": world["height"],
        "measured_from": "scan foot (z=0)" if keep_floor else "bounding box",
        "buried_below_foot_m": round(-min(v.co[2] for v in obj.data.vertices) * world["diam"], 4),
    }


def _srgb_to_linear(value: float) -> float:
    """The inverse of what a ``BYTE_COLOR`` attribute does on write (see below)."""

    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def dae_colour_range(text: str) -> dict[str, Any]:
    """What the exported DAE's ``COLOR`` arrays actually carry, read from the bytes.

    The soot bake is only worth what the file says, so the manifest records the range
    the exporter WROTE (r2; r1's manifest recorded only the range that was intended,
    which is how a 0.45 floor shipped as 0.70196 without a gate noticing).
    """

    values: list[float] = []
    for match in re.finditer(r'id="[^"]*colors-soot-array"[^>]*>([^<]*)<', text):
        numbers = [float(v) for v in match.group(1).split()]
        # RGBA stride 4: the multiplier is the R channel, alpha is always 1
        values.extend(numbers[0::4])
    if not values:
        return {"arrays": 0, "min": None, "max": None}
    return {
        "arrays": text.count("colors-soot-array"),
        "values": len(values),
        "min": round(min(values), 7),
        "max": round(max(values), 7),
    }


def bake_soot(obj, world_scale: float, sink_m: float) -> dict[str, float]:
    """Write the soot multiplier into a CORNER ``BYTE_COLOR`` layer named ``soot``.

    Local units are metres-of-world / ``world_scale``.  The ash line is the sink
    depth, and the gradient runs ``SOOT_FLOOR -> 1`` over ``SOOT_TOP_M`` of world
    height above it, smoothstepped so no band edge shows.

    **r2, and the round paid for it twice.**  r1 assigned the multiplier straight to
    ``layer.data[i].color`` and shipped a DAE carrying **0.70196**, not 0.45 -- and the
    critic measured the result as a 9 % dimming nobody could see.  Blender's
    ``BYTE_COLOR`` attribute stores an **sRGB byte** and its Python setter takes a
    LINEAR float, so writing 0.45 stores byte 179 (= sRGB of linear 0.45); Blender's
    COLLADA exporter then writes the stored byte / 255 = 0.70196, and the engine reads
    that number as the multiplier.  Probed head-on
    (``b2/r2/vc_probe2.py``, Blender 4.5.4, three cases, one cube each):

    ========================  ==============================  ================
    attribute                 written                         DAE ``COLOR``
    ========================  ==============================  ================
    ``BYTE_COLOR``            0.45                            **0.7019608**
    ``FLOAT_COLOR``           0.45                            **no COLOR at all**
    ``BYTE_COLOR``            ``srgb_to_linear(0.45)``        **0.4509804**
    ========================  ==============================  ================

    The obvious repair -- move to ``FLOAT_COLOR``, which stores linear -- is a TRAP:
    Blender 4.5.4's COLLADA exporter emits **no ``semantic="COLOR"`` input at all** for
    a float colour attribute, so the stones would have shipped with the soot channel
    silently gone and every "the channel reaches the shader" gate still passing on the
    material flag.  The fix is to pre-compensate: write ``srgb_to_linear(v)`` so the
    byte that lands is ``round(v * 255)`` and the DAE carries ``v`` itself, to within
    the 1/255 the byte attribute can express (0.45 -> 115/255 = 0.45098).
    """

    mesh = obj.data
    if "soot" in {layer.name for layer in mesh.color_attributes}:
        mesh.color_attributes.remove(mesh.color_attributes["soot"])
    layer = mesh.color_attributes.new(name="soot", type="BYTE_COLOR", domain="CORNER")
    ash = sink_m / world_scale
    top = hs.SOOT_TOP_M / world_scale
    low = 1.0
    high = 0.0
    for loop_index, loop in enumerate(mesh.loops):
        z = mesh.vertices[loop.vertex_index].co[2]
        t = 0.0 if top <= 0 else min(max((z - ash) / top, 0.0), 1.0)
        smooth = t * t * (3.0 - 2.0 * t)
        value = hs.SOOT_FLOOR + (1.0 - hs.SOOT_FLOOR) * smooth
        low = min(low, value)
        high = max(high, value)
        stored = _srgb_to_linear(value)
        layer.data[loop_index].color = (stored, stored, stored, 1.0)
    mesh.update()
    return {
        "min": round(low, 4),
        "max": round(high, 4),
        "ash_local_z": round(ash, 5),
        # what the DAE will actually carry: the byte the attribute quantises to
        "dae_min": round(round(low * 255.0) / 255.0, 7),
        "dae_max": round(round(high * 255.0) / 255.0, 7),
        "encoding": "BYTE_COLOR pre-compensated with srgb_to_linear (r2)",
    }


def build_stone(asset: str, out_root: Path) -> dict:
    bpy = _bpy()
    bf.clear_scene()
    world = stone_world(asset)
    stem = hs.stone_stem(asset)
    material = bf.make_material(hs.stone_material(asset))
    # r6 (critic B2 pass 5, C5-2; level_facts 2026-09-07).  `rock_face_01` is a
    # photogrammetry scan of a cliff FACE.  Imported with no `solid=` it took
    # `import_model`'s cap-the-sheet branch and shipped a watertight shell a median
    # 0.75 m thick inside a convex hull it filled 2-5 % of -- a facade with an
    # invisible wall in front of it on four of the ring's 36 m stones.  `solid="face"`
    # routes it through `rock_solid.solid_from_face_scan` instead: front heightfield,
    # wedge body, relieved skirt, one closed manifold, the scan's own UVs kept on the
    # front.  That is B3 r9's route, whose gate reproduced 27/27 on shipped bytes.
    solid = hs.stone_solid(asset)
    folder = hs.stone_source_folder(asset)
    source = bf.import_model(
        CACHE,
        folder,
        hs.STONE_SOURCES[asset]["part"],
        False,
        10.0,
        solid=solid,
        seed=hs.STONE_SOLID_SEED,
    )
    import_solid = dict(bf.IMPORT_REPORT)
    keep_floor = solid == "face"
    dimensions = normalise_horizontal(source, keep_floor=keep_floor)
    stretch = stretch_to_design_height(source, world, keep_floor=keep_floor)
    dimensions = {
        "x": round(float(source.dimensions[0]), 6),
        "y": round(float(source.dimensions[1]), 6),
        "z": round(float(source.dimensions[2]), 6),
    }
    above_foot = max(v.co[2] for v in source.data.vertices)
    bf.rebind_material(source, material)

    base = bf.empty(bf.BASE_NODE, None)
    start = bf.empty(bf.START_NODE, base)
    bf.empty(bf.fs.BB_NODE, base)
    bf.empty(f"nulldetail{hs.STONE_NULLDETAIL}", base)

    nodes = [base, start]
    node_soot: dict[str, dict[str, float]] = {}
    node_solid: dict[str, dict[str, Any]] = {}
    finest = None
    for pixel, budget in hs.STONE_DETAILS:
        name = bf.detail_node(stem, pixel)
        detail = bf.duplicate(source, name, start)
        # r6: `seal_to`, not `decimate_to`.  A cap does not survive decimation on its
        # own -- `decimate_to`'s escape hatch is a progressive WELD of up to 25 % of the
        # span, which tears a closed shell open again -- so the budget is lowered
        # instead until closure and budget both hold (B3's law).  For the five stones
        # that already close, `seal_to` returns after its first `decimate_to`, so their
        # visual nodes take the identical path they took in r5.
        bf.seal_to(detail, budget)
        # B3 r5's law: re-apply the relief AFTER the last decimation, from each
        # vertex's own entry position and normal, or a capped shell collapses back
        # into one plane.  The soot bake then runs on the FINAL vertices.
        bf.roughen_flat_planes(detail)
        # r6: outward, closed, and SAID so per detail -- this is what clears
        # `rock_face_01`'s 17 sliver flaps (38 boundary / 19 non-manifold edges) and
        # its 55 bow-tie vertices, and it is the build's own account of the three
        # numbers `mesh_audit` reads back off the shipped file.
        node_solid[name] = bf.ensure_solid(detail, budget)
        bf.assert_positive_volume(detail, name)
        node_soot[name] = bake_soot(detail, world["diam"], world["sink"])
        nodes.append(detail)
        if finest is None:
            finest = detail
    # r6 (C5-2, the hull finding).  `convex_hull_of(source, ...)` is what put the
    # invisible wall there: the collider was the visual's own convex hull to 0.7 %, so
    # every concavity in every stone became phantom collision.  `solid_colmesh_of`
    # returns a DECIMATED COPY of the finest visual instead and falls back to the hull
    # only if that copy will not close -- so this can improve a stone and cannot make
    # one worse.  The budget is per source now (hearth_spec.STONE_COLMESH_BUDGET): a
    # copy is only worth its collapse error, and 240 triangles on a 36 m stone would
    # re-create the wall the hull was removed to kill.
    colmesh, colmesh_info = bf.solid_colmesh_of(
        finest, bf.colmesh_node(stem), hs.stone_colmesh_budget(asset), start
    )
    bf.rebind_material(colmesh, material)
    # a collider carries no soot: the copy inherits the finest detail's COLOR attribute,
    # which would put a fourth `semantic="COLOR"` input in the DAE (the soot gate counts
    # exactly one per DETAIL) and pay for a channel nothing samples
    for layer in list(colmesh.data.color_attributes):
        colmesh.data.color_attributes.remove(layer)
    colmesh.data.update()
    nodes.append(colmesh)
    bpy.data.objects.remove(source, do_unlink=True)
    bf.purge_unused_materials({hs.stone_material(asset)})

    tree = bf.expected_tree(
        stem,
        tuple(pixel for pixel, _ in hs.STONE_DETAILS),
        bb=True,
        null=hs.STONE_NULLDETAIL,
        colmesh=True,
    )
    # the bb node is an EMPTY here (the engine bakes the atlas at level load), so it
    # carries no geometry and every other node is a mesh; export the whole tree.
    info = bf.export_dae(nodes, out_root / f"{stem}.dae", tree, {hs.stone_material(asset)}, bb=True)
    text = (out_root / f"{stem}.dae").read_text(encoding="utf-8")
    info.update(
        {
            "asset": asset,
            "relative": f"{hs.SHAPE_DIR}/{stem}.dae",
            "material": hs.stone_material(asset),
            "world": world,
            "unit_dimensions": dimensions,
            "height_stretch": stretch,
            # r6: a face solid's bounding box also holds its buried underside, and the
            # design's table is the height a PLAYER sees.  `world_height_m` is therefore
            # the height above the foot (z = 0) for every source; the full box is beside it.
            "world_height_m": round(above_foot * world["diam"], 3),
            "world_bbox_height_m": round(dimensions["z"] * world["diam"], 3),
            "design_height_m": world["height"],
            "soot": node_soot,
            "soot_in_the_dae": dae_colour_range(text),
            "vertex_colour_semantic": text.count('semantic="COLOR"'),
            "colmesh_budget": hs.stone_colmesh_budget(asset),
            # --- r6 provenance: how this DAE was derived from its CC0 source ---------
            "cc0_source": f"cc0_cache/{folder}/{folder}_2k.gltf",
            "cc0_source_folder": folder,
            "derivation": (
                "solid_from_face_scan (front heightfield + wedge body + relieved "
                "skirt), scan UVs kept on the front, box projection at the front's own "
                "texel density on the body; collider = decimated copy of the finest "
                "visual"
                if solid == "face"
                else "weld_islands + seal_shell (closed scan); collider = decimated "
                "copy of the finest visual, convex hull only as a fallback"
            ),
            "import_solid_route": solid,
            "import_solid": import_solid,
            "detail_solid": node_solid,
            "colmesh_kind": colmesh_info.get("kind"),
            "colmesh_solid": colmesh_info,
        }
    )
    return info


def crust_mesh() -> bf.Mesh:
    """One 15 degree sector of the ember bed, authored about its own centroid.

    ``CRUST_GRID`` = (20 radial, 24 tangential) quads -> 960 triangles.  The lump
    field is a sum of three cosine octaves keyed by ``CRUST_SEED`` -- deterministic,
    seamless across the sector's tangential edges (the period divides 15 degrees) so
    the 24 instances tile without a visible joint, and clamped into the design's
    0.02-0.35 m band.
    """

    mesh = bf.Mesh()
    nr, nt = hs.CRUST_GRID
    radial_tiles = CRUST_RADIAL_TILES
    half = hs.CRUST_SECTOR_DEG / 2.0
    cx, cy = hs.bearing_point(0.0, hs.CRUST_R_MID)

    def lump(r: float, theta_deg: float) -> float:
        phase = math.radians(theta_deg * (360.0 / hs.CRUST_SECTOR_DEG))
        seed = (hs.CRUST_SEED % 997) / 997.0
        value = (
            0.55 * math.sin(phase * 4.0 + seed * 6.283) * math.cos(r * 0.65 + seed * 3.1)
            + 0.30 * math.sin(phase * 9.0 + 1.7) * math.cos(r * 1.31 + 0.9)
            + 0.15 * math.sin(phase * 17.0 + 2.9) * math.cos(r * 2.77 + 2.2)
        )
        unit = (value + 1.0) / 2.0
        return hs.CRUST_LUMP_MIN + (hs.CRUST_LUMP_MAX - hs.CRUST_LUMP_MIN) * unit

    grid: list[list[int]] = []
    for i in range(nr + 1):
        row = []
        r = hs.CRUST_R_INNER + (hs.CRUST_R_OUTER - hs.CRUST_R_INNER) * i / nr
        for j in range(nt + 1):
            theta = -half + hs.CRUST_SECTOR_DEG * j / nt
            x, y = hs.bearing_point(theta, r)
            z = lump(r, theta)
            # the rim of the plate settles into the ash so no lip shows at the seam
            edge = min(i, nr - i) / max(nr / 6.0, 1.0)
            z *= min(edge, 1.0) if nr else 1.0
            row.append(mesh.add_vert(x - cx, y - cy, max(z, 0.0)))
        grid.append(row)
    for i in range(nr):
        for j in range(nt):
            a, b, c, d = grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]
            # u is the RADIUS, once across the plate (CRUST_RADIAL_TILES = 1); v is
            # tangential and tiles CRUST_UV_TILES times per sector.  23.0 x 24.5 m per
            # tile: texels square to within 7 %, lumps 0.30-1.28 m, and the cook gets a
            # radial axis to bank the bed on.  The maps are periodic in v, so the two
            # tiles inside a sector and the 24 sectors around the ring are seamless; u
            # never wraps, and both u ends are ash, so the plate rim feathers.
            u0, u1 = i / nr * radial_tiles, (i + 1) / nr * radial_tiles
            v0, v1 = j / nt * CRUST_UV_TILES, (j + 1) / nt * CRUST_UV_TILES
            mesh.add_tri(a, b, c, ((u0, v0), (u0, v1), (u1, v1)), 0)
            mesh.add_tri(a, c, d, ((u0, v0), (u1, v1), (u1, v0)), 0)
    return mesh


def build_crust(out_root: Path) -> dict:
    bf.clear_scene()
    stem = hs.crust_stem()
    material = bf.make_material(hs.crust_material())
    base = bf.empty(bf.BASE_NODE, None)
    start = bf.empty(bf.START_NODE, base)
    bf.empty("nulldetail1", base)
    detail_name = bf.detail_node(stem, 1)
    detail = bf.object_from_mesh(detail_name, crust_mesh(), [material], start)
    bf.triangulate(detail)
    tree = {
        bf.BASE_NODE: None,
        "nulldetail1": bf.BASE_NODE,
        bf.START_NODE: bf.BASE_NODE,
        detail_name: bf.START_NODE,
    }
    info = bf.export_dae(
        [base, start, detail], out_root / f"{stem}.dae", tree, {hs.crust_material()}, bb=False
    )
    info.update(
        {
            "relative": f"{hs.SHAPE_DIR}/{stem}.dae",
            "material": hs.crust_material(),
            "grid": list(hs.CRUST_GRID),
            "sector_deg": hs.CRUST_SECTOR_DEG,
            "r": [hs.CRUST_R_INNER, hs.CRUST_R_OUTER],
            "lump_band_m": [hs.CRUST_LUMP_MIN, hs.CRUST_LUMP_MAX],
            "uv_tiles": {
                "tangential": CRUST_UV_TILES,
                "radial": CRUST_RADIAL_TILES,
                "tile_m": [
                    round(hs.CRUST_R_OUTER - hs.CRUST_R_INNER, 4),
                    round(math.radians(hs.CRUST_SECTOR_DEG) * hs.CRUST_R_MID / CRUST_UV_TILES, 4),
                ],
                "mm_per_texel": [
                    round((hs.CRUST_R_OUTER - hs.CRUST_R_INNER) * 1000.0 / hs.CRUST_MAP_PX, 4),
                    round(
                        math.radians(hs.CRUST_SECTOR_DEG)
                        * hs.CRUST_R_MID
                        * 1000.0
                        / CRUST_UV_TILES
                        / hs.CRUST_MAP_PX,
                        4,
                    ),
                ],
            },
            "instances": hs.CRUST_COUNT,
        }
    )
    return info


def build(out_root: Path, only: set[str] | None = None) -> dict:
    out_root.mkdir(parents=True, exist_ok=True)
    stones: dict[str, dict] = {}
    for asset in hs.STONE_SOURCES:
        if only and asset not in only:
            continue
        stones[asset] = build_stone(asset, out_root)
    crust = build_crust(out_root) if not only or "crust" in only else None
    manifest = {
        "level_id": hs.LEVEL_ID,
        "shape_dir": hs.SHAPE_DIR,
        "details": [list(pair) for pair in hs.STONE_DETAILS],
        "nulldetail": hs.STONE_NULLDETAIL,
        "colmesh_tris": hs.STONE_COLMESH_TRIS,
        "colmesh_budget_by_source": dict(hs.STONE_COLMESH_BUDGET),
        "solid_route_by_source": dict(hs.STONE_SOLID),
        "solid_seed": hs.STONE_SOLID_SEED,
        "soot": {
            "floor": hs.SOOT_FLOOR,
            "top_m": hs.SOOT_TOP_M,
            "method": "vertex colour (COLOR), material vertColor true",
            "encoding": (
                "BYTE_COLOR pre-compensated with srgb_to_linear so the DAE carries the "
                "DESIGN multiplier itself (r2). FLOAT_COLOR exports NO colour input at all "
                "in Blender 4.5.4 -- see bake_soot's docstring and b2/r2/vc_probe2.py."
            ),
            "dae_floor": round(round(hs.SOOT_FLOOR * 255.0) / 255.0, 7),
        },
        "bb_property": bf.fs.BB_PROPERTY,
        "stones": stones,
        "crust": crust,
    }
    return manifest


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--only", default="")
    arguments = parser.parse_args(argv)
    only = {s for s in arguments.only.split(",") if s} or None
    manifest = build(arguments.out, only)
    if only is None:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(
            json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    summary = {
        key: {
            "tris": info["node_tris"],
            "sha256": info["sha256"][:12],
            "colour": info.get("vertex_colour_semantic"),
        }
        for key, info in manifest["stones"].items()
    }
    if manifest["crust"]:
        summary["crust"] = {
            "tris": manifest["crust"]["node_tris"],
            "sha256": manifest["crust"]["sha256"][:12],
        }
    print(json.dumps(summary, indent=1, sort_keys=True))
    print("MANIFEST", MANIFEST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
