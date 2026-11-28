"""Blender 4.5.4 headless generator for the Giant's Hearth forest (design v4 §4.1-§4.3).

Run (the validated runtime; ``--factory-startup`` so no user add-on can change a byte)::

    $blender = 'C:\\Users\\ericr\\Applications\\Blender\\4.5.4\\blender.exe'
    $script  = 'examples/hot_potato_arena/level/blender_forest.py'
    & $blender --factory-startup --background --python $script -- `
        --out examples/hot_potato_arena/mod/levels/ericrolph_hot_potato_arena `
        --cache examples/hot_potato_arena/cc0_cache `
        --manifest examples/hot_potato_arena/authoring/ericrolph_hot_potato_arena_forest_shapes.json

What it emits, one DAE per row of ``forest_spec.SPECIES`` (54) and
``forest_spec.COVER_SHAPES`` (9), in the stock node tree read from
``levels/italy/art/shapes/trees/trees_italy/cypress_tree.dae`` and
``levels/east_coast_usa/art/shapes/buildings/bussign.dae``::

    base00
      bb_autobillboard25          <- carries <extra><technique profile="OpenCOLLADA">
      nulldetail<N>                  <user_properties>BB::DIM=128 (B0-measured: 512 x 256)
      start01
        <stem>_a<px>  ...          <- N is the SCREEN SIZE IN PIXELS (study §5.1), larger = closer
        Colmesh_<stem>-1

Two geometry paths:

* **generated conifers and snags** (18 DAEs, the ones QB-6 measures).  A tapered trunk tube
  swept along a 3-point spline (3 % lean + 0.4 m of noise on the mid control point), whorled
  branches (pines 8-12 whorls x 5-7 branches, firs 14-18 x 6-8 with a downward droop), and
  twig CARDS UV-mapped into one cell of the cooked twig atlas.  The tube primitive has
  exactly ``2 x radial x rings`` triangles and a card exactly 2, so every authored budget of
  design §4.2 is met **to the triangle** -- QB-6's p50s are the design's numbers by
  construction, not by luck.
* **CC0 models** (36 DAEs).  The Poly Haven glTF is imported, optionally split into loose
  parts, scaled so its longest dimension equals the design's stated size (the rule that
  reproduces the design's own size column: boulder_01 1.83 m x 2.5 = 4.6 m, rock_face_01
  7.11 x 3 = 21 m, dead_tree_trunk 3.05 x 3.5 = 10.7 m ...), decimated per detail and given
  a decimated convex hull as its Colmesh (rocks: the design's "convex-ish hull").

Determinism (AGENTS.md "the Collada exporter is not deterministic, and the fix is
quantisation", L710): every export is passed through ``normalise_collada`` -- pinned
``<created>``/``<modified>``/``<author>`` and every ``<float_array>`` re-emitted at five
decimals -- and the module asserts the node tree, the material set and the triangle count of
every file before it records its sha256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
import time
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from examples.hot_potato_arena.level import (  # noqa: E402
    forest_spec as fs,
)
from examples.hot_potato_arena.level import (  # noqa: E402
    mesh_audit,
    rock_solid,
)

COLLADA_NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
COLLADA_DECIMALS = 5
COLLADA_EPOCH = "2026-09-05T12:00:00"
COLLADA_AUTHOR = "Eric Rolph"

START_NODE = "start01"
BASE_NODE = "base00"


# ---------------------------------------------------------------------------- pure helpers
def dae_stem(key: str, cover: bool = False) -> str:
    return f"{fs.LEVEL_ID}_{key}" if cover else f"{fs.LEVEL_ID}_f_{key}"


def detail_node(stem: str, pixel: int) -> str:
    return f"{stem}_a{pixel}"


def colmesh_node(stem: str) -> str:
    return f"Colmesh_{stem}-1"


def expected_tree(stem: str, details: tuple[int, ...], *, bb: bool, null: int, colmesh: bool):
    tree = {BASE_NODE: None}
    if bb:
        tree[fs.BB_NODE] = BASE_NODE
    tree[f"nulldetail{null}"] = BASE_NODE
    tree[START_NODE] = BASE_NODE
    for pixel in details:
        tree[detail_node(stem, pixel)] = START_NODE
    if colmesh:
        tree[colmesh_node(stem)] = START_NODE
    return tree


def quantise_collada(text: str) -> str:
    """AGENTS.md L710: pin the stamps, re-emit every float_array at five decimals."""

    def number(match: re.Match[str]) -> str:
        return f"{float(match.group(0)):.{COLLADA_DECIMALS}f}"

    def array(match: re.Match[str]) -> str:
        head, body, tail = match.group(1), match.group(2), match.group(3)
        return head + re.sub(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", number, body) + tail

    text = re.sub(r"<created>[^<]*</created>", f"<created>{COLLADA_EPOCH}</created>", text)
    text = re.sub(r"<modified>[^<]*</modified>", f"<modified>{COLLADA_EPOCH}</modified>", text)
    text = re.sub(r"<author>[^<]*</author>", f"<author>{COLLADA_AUTHOR}</author>", text)
    return re.sub(r"(<float_array\b[^>]*>)(.*?)(</float_array>)", array, text, flags=re.S)


def dae_node_parents(path: Path) -> dict[str, str | None]:
    import xml.etree.ElementTree as ET

    root = ET.parse(path).getroot()  # noqa: S314 - a DAE this module wrote itself
    scene = root.find("c:library_visual_scenes/c:visual_scene", COLLADA_NS)
    out: dict[str, str | None] = {}

    def walk(node, parent):
        for child in node.findall("c:node", COLLADA_NS):
            name = child.get("name") or child.get("id")
            out[name] = parent
            walk(child, name)

    walk(scene, None)
    return out


def dae_material_names(path: Path) -> set[str]:
    import xml.etree.ElementTree as ET

    root = ET.parse(path).getroot()  # noqa: S314
    return {m.get("name") for m in root.iter(f"{{{COLLADA_NS['c']}}}material")}


def dae_detail_triangles(path: Path) -> dict[str, int]:
    """Triangles per LOD node, attributed the way ``study/census_lib.parse_dae`` does."""
    import xml.etree.ElementTree as ET

    ns = COLLADA_NS["c"]
    root = ET.parse(path).getroot()  # noqa: S314
    geometry: dict[str, int] = {}
    for geom in root.iter(f"{{{ns}}}geometry"):
        total = 0
        for tag in ("triangles", "polylist", "polygons"):
            for prim in geom.iter(f"{{{ns}}}{tag}"):
                total += int(prim.get("count", 0) or 0)
        geometry[geom.get("id")] = total
    scene = root.find("c:library_visual_scenes/c:visual_scene", COLLADA_NS)
    out: dict[str, int] = {}

    def walk(node) -> int:
        total = 0
        for inst in node.findall("c:instance_geometry", COLLADA_NS):
            total += geometry.get(inst.get("url", "").lstrip("#"), 0)
        for child in node.findall("c:node", COLLADA_NS):
            total += walk(child)
        name = node.get("name") or node.get("id")
        out[name] = total
        return total

    for child in scene.findall("c:node", COLLADA_NS):
        walk(child)
    return out


# ---------------------------------------------------------------- procedural mesh assembly
class Mesh:
    """A triangle soup with per-loop UVs and per-face material slots, built in pure python."""

    def __init__(self) -> None:
        self.verts: list[tuple[float, float, float]] = []
        self.faces: list[tuple[int, int, int]] = []
        self.uvs: list[tuple[float, float]] = []  # 3 per face
        self.slots: list[int] = []

    def add_vert(self, x: float, y: float, z: float) -> int:
        self.verts.append((x, y, z))
        return len(self.verts) - 1

    def add_tri(self, a: int, b: int, c: int, uv, slot: int) -> None:
        self.faces.append((a, b, c))
        self.uvs.extend(uv)
        self.slots.append(slot)

    @property
    def tris(self) -> int:
        return len(self.faces)


def add_tube(
    mesh: Mesh, axis, radii, radial: int, slot: int, apex_point, uv_scale=(1.0, 1.0)
) -> None:
    """Capped tapered tube: ``2 * radial * len(axis)`` triangles (bottom fan + bands + apex).

    ``axis`` is the ring-centre list (len == rings), ``radii`` the matching radii, and
    ``apex_point`` the single vertex that closes the cone -- passed in rather than guessed so
    the shipped Colmesh and ``forest_spec.colmesh_profile``'s predictor describe one cone.
    """
    rings = len(axis)
    ring_index: list[list[int]] = []
    for centre, radius in zip(axis, radii, strict=True):
        row = []
        for k in range(radial):
            angle = 2.0 * math.pi * k / radial
            row.append(
                mesh.add_vert(
                    centre[0] + radius * math.cos(angle),
                    centre[1] + radius * math.sin(angle),
                    centre[2],
                )
            )
        ring_index.append(row)
    bottom = mesh.add_vert(axis[0][0], axis[0][1], axis[0][2])
    apex = mesh.add_vert(*apex_point)
    su, sv = uv_scale
    for k in range(radial):
        n = (k + 1) % radial
        u0, u1 = su * k / radial, su * (k + 1) / radial
        mesh.add_tri(
            bottom, ring_index[0][n], ring_index[0][k], [(0.5, 0.0), (u1, 0.0), (u0, 0.0)], slot
        )
        for s in range(rings - 1):
            v0, v1 = sv * s / rings, sv * (s + 1) / rings
            mesh.add_tri(
                ring_index[s][k],
                ring_index[s][n],
                ring_index[s + 1][n],
                [(u0, v0), (u1, v0), (u1, v1)],
                slot,
            )
            mesh.add_tri(
                ring_index[s][k],
                ring_index[s + 1][n],
                ring_index[s + 1][k],
                [(u0, v0), (u1, v1), (u0, v1)],
                slot,
            )
        # k -> n -> apex, not k -> apex -> n: the second winding puts the cone's tip faces
        # INSIDE-OUT.  It cost a live boot: a downward ray at 0.2 m off a pine's axis entered
        # the Colmesh cone through a back-face and passed straight through to the terrain, so
        # eight of the twenty ray-census instances read "no tree here".
        mesh.add_tri(
            ring_index[-1][k], ring_index[-1][n], apex, [(u0, sv), (u1, sv), (0.5, sv)], slot
        )


def add_card(
    mesh: Mesh, centre, right, up, half_w: float, half_h: float, uv_rect, slot: int
) -> None:
    """One quad = 2 triangles, UV-mapped into ``uv_rect`` = (u, v, w, h) of the atlas."""
    cx, cy, cz = centre
    rx, ry, rz = right
    ux, uy, uz = up
    corners = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        corners.append(
            mesh.add_vert(
                cx + sx * half_w * rx + sy * half_h * ux,
                cy + sx * half_w * ry + sy * half_h * uy,
                cz + sx * half_w * rz + sy * half_h * uz,
            )
        )
    u, v, w, h = uv_rect
    uv = [(u, v), (u + w, v), (u + w, v + h), (u, v + h)]
    mesh.add_tri(corners[0], corners[1], corners[2], [uv[0], uv[1], uv[2]], slot)
    mesh.add_tri(corners[0], corners[2], corners[3], [uv[0], uv[2], uv[3]], slot)


def _normalise(vector):
    length = math.sqrt(sum(c * c for c in vector)) or 1.0
    return tuple(c / length for c in vector)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def trunk_spline(top_z: float, rng: random.Random):
    """3-point spline: base, a mid control point with 3 % lean + 0.4 m noise, and the tip.

    Returns ``at(t)`` -> the trunk centre at ``z = top_z * t``; the same z convention
    ``forest_spec.colmesh_profile`` predicts.
    """
    lean = 0.03 * top_z
    bearing = rng.uniform(0.0, 2.0 * math.pi)
    tip = (lean * math.cos(bearing), lean * math.sin(bearing))
    mid = (0.5 * tip[0] + rng.uniform(-0.4, 0.4), 0.5 * tip[1] + rng.uniform(-0.4, 0.4))

    def at(t: float):
        one = 1.0 - t
        return (
            2.0 * one * t * mid[0] + t * t * tip[0],
            2.0 * one * t * mid[1] + t * t * tip[1],
            top_z * t,
        )

    return at


def trunk_axis(top_z: float, rings: int, rng: random.Random):
    """``rings`` ring centres at z = top_z * s / rings plus the apex point at ``top_z``."""
    at = trunk_spline(top_z, rng)
    return [at(s / rings) for s in range(rings)], at(1.0)


def atlas_cell(grid, rng: random.Random):
    cols, rows = grid
    col, row = rng.randrange(cols), rng.randrange(rows)
    inset = 0.004
    return (col / cols + inset, row / rows + inset, 1.0 / cols - 2 * inset, 1.0 / rows - 2 * inset)


def _frame(direction):
    """(right, up) perpendicular to ``direction``, up as close to world +z as it can be."""
    d = _normalise(direction)
    reference = (0.0, 0.0, 1.0) if abs(d[2]) < 0.98 else (1.0, 0.0, 0.0)
    right = _normalise(_cross(d, reference))
    up = _normalise(_cross(right, d))
    return right, up


def add_branch_tube(
    mesh: Mesh, points, radii, radial: int, slot: int, apex, v_repeat: float = 1.0
) -> None:
    """A tapered tube along an ARBITRARY polyline: rings perpendicular to the local axis.

    ``add_tube`` builds horizontal rings, which is right for a trunk and degenerate for a
    branch that runs sideways.  Same triangle count -- ``2 * radial * len(points)`` -- and the
    same winding (bottom fan facing back along the axis, apex fan facing forward), so a
    branch is closed and wound outward like the trunk it grows from.

    r11 (critic B10-1): ``v_repeat`` tiles the material ALONG the branch.  Until this round
    the v coordinate ran 0 -> 1 over the whole tube, so a 1024 px bark tile was stretched once
    over an eight-metre limb and once around its 0.4 m girth -- 8 mm per texel along against
    0.3 mm around.  That anisotropy, not the silhouette, is why the armature read as a
    flat-shaded plank at arm's length; the trunk never had it because ``add_tube`` has always
    taken a ``uv_scale``.
    """
    count = len(points)
    ring_index: list[list[int]] = []
    for index, (centre, radius) in enumerate(zip(points, radii, strict=True)):
        ahead = points[index + 1] if index + 1 < count else apex
        behind = points[index - 1] if index > 0 else None
        direction = tuple(ahead[i] - centre[i] for i in range(3))
        if behind is not None:
            direction = tuple(direction[i] + centre[i] - behind[i] for i in range(3))
        right, up = _frame(direction)
        row = []
        for k in range(radial):
            angle = 2.0 * math.pi * k / radial
            c, s = radius * math.cos(angle), radius * math.sin(angle)
            row.append(
                mesh.add_vert(
                    centre[0] + c * right[0] + s * up[0],
                    centre[1] + c * right[1] + s * up[1],
                    centre[2] + c * right[2] + s * up[2],
                )
            )
        ring_index.append(row)
    bottom = mesh.add_vert(*points[0])
    top = mesh.add_vert(*apex)
    for k in range(radial):
        n = (k + 1) % radial
        u0, u1 = k / radial, (k + 1) / radial
        mesh.add_tri(
            bottom, ring_index[0][n], ring_index[0][k], [(0.5, 0.0), (u1, 0.0), (u0, 0.0)], slot
        )
        for s in range(count - 1):
            v0, v1 = v_repeat * s / count, v_repeat * (s + 1) / count
            mesh.add_tri(
                ring_index[s][k],
                ring_index[s][n],
                ring_index[s + 1][n],
                [(u0, v0), (u1, v0), (u1, v1)],
                slot,
            )
            mesh.add_tri(
                ring_index[s][k],
                ring_index[s + 1][n],
                ring_index[s + 1][k],
                [(u0, v0), (u1, v1), (u0, v1)],
                slot,
            )
        mesh.add_tri(
            ring_index[-1][k],
            ring_index[-1][n],
            top,
            [(u0, v_repeat), (u1, v_repeat), (0.5, v_repeat)],
            slot,
        )


def _bezier(p0, p1, p2, t: float):
    one = 1.0 - t
    return tuple(one * one * p0[i] + 2.0 * one * t * p1[i] + t * t * p2[i] for i in range(3))


def _branch_curve(root, azimuth: float, elevation: float, length: float, sag: float, lift: float):
    """(P0, P1, P2) of one branch: root on the trunk, a sagging mid point, a lifted tip."""
    direction = (
        math.cos(azimuth) * math.cos(elevation),
        math.sin(azimuth) * math.cos(elevation),
        math.sin(elevation),
    )
    tip = tuple(root[i] + length * direction[i] for i in range(3))
    tip = (tip[0], tip[1], tip[2] + lift * length)
    mid = tuple(root[i] + 0.5 * length * direction[i] for i in range(3))
    mid = (mid[0], mid[1], mid[2] - sag * length)
    return root, mid, tip


def _branch_segments(species: dict, plan: dict, trunk_at) -> list[dict]:
    """Every branch of the skeleton as a curve in the shape's frame: mains, then their subs.

    Order is the plan's order, so the card distribution is the same at every LOD.
    """
    height = species["height_m"]
    r0 = height * fs.TRUNK_RADIUS_FRACTION
    out: list[dict] = []
    for whorl in plan["whorls"]:
        for branch in whorl["branches"]:
            z = min(max(whorl["z"] + branch.get("dz", 0.0), plan["base"]), plan["tip"])
            centre = trunk_at(min(z / height, 1.0))
            trunk_r = r0 * (1.0 - fs.TRUNK_TAPER * min(z / height, 1.0))
            az, el, length = branch["azimuth"], branch["elevation"], branch["length"]
            root = (
                centre[0] + 0.85 * trunk_r * math.cos(az),
                centre[1] + 0.85 * trunk_r * math.sin(az),
                centre[2],
            )
            p0, p1, p2 = _branch_curve(root, az, el, length, branch["sag"], branch["lift"])
            radius = 0.012 * length + 0.02
            out.append(
                dict(kind="main", curve=(p0, p1, p2), length=length, radius=radius, u=whorl["u"])
            )
            for sub in branch["subs"]:
                fork = _bezier(p0, p1, p2, sub["at"])
                sub_p0, sub_p1, sub_p2 = _branch_curve(
                    fork,
                    az + sub["yaw"],
                    el + sub["pitch"],
                    sub["length"],
                    0.5 * branch["sag"],
                    branch["lift"],
                )
                out.append(
                    dict(
                        kind="sub",
                        curve=(sub_p0, sub_p1, sub_p2),
                        length=sub["length"],
                        radius=0.55 * radius,
                        u=whorl["u"],
                    )
                )
    return out


def _spray_card(
    mesh: Mesh,
    point,
    tangent,
    side_angle: float,
    roll: float,
    droop: float,
    half: float,
    uv,
    rng: random.Random,
) -> None:
    """One spray card whose BASE sits on the branch axis at ``point``.

    The spray's axis (the card's ``up``, v = 0 -> 1 in the atlas cell) leaves the branch at
    ``side_angle`` from the tangent, drooped by ``droop``; the card plane is rolled about that
    axis so most sprays lie near-flat like a real conifer's and a share stand on edge, which is
    what makes a branch read from below and from the side.
    """
    t = _normalise(tangent)
    right0, _up0 = _frame(t)
    # the shoot direction: rotate the tangent about the local up by side_angle, then droop
    c, s = math.cos(side_angle), math.sin(side_angle)
    shoot = tuple(c * t[i] + s * right0[i] for i in range(3))
    shoot = _normalise((shoot[0], shoot[1], shoot[2] - droop))
    axis_right, axis_up = _frame(shoot)
    cr, sr = math.cos(roll), math.sin(roll)
    right = _normalise(tuple(cr * axis_right[i] + sr * axis_up[i] for i in range(3)))
    centre = tuple(point[i] + shoot[i] * half * 0.92 for i in range(3))
    add_card(mesh, centre, right, shoot, half, half, uv, slot=2)


def conifer_mesh(
    species: dict,
    layout: dict,
    grid,
    rng: random.Random,
    card_scale: float = 1.0,
) -> Mesh:
    """Trunk + branch skeleton + spray cards, exactly ``layout['budget']`` triangles (r9).

    ``layout`` is one row of ``forest_spec.conifer_layout``; ``card_scale`` is
    ``forest_spec.lod_card_scale``'s entry for the detail (fewer, bigger cards down the
    ladder so the crown keeps its area, D4).  The skeleton is ``forest_spec.crown_plan``,
    shared by every LOD.
    """
    height = species["height_m"]
    r0 = height * fs.TRUNK_RADIUS_FRACTION
    radial, rings = layout["radial"], layout["rings"]
    mesh = Mesh()
    trunk_at = trunk_spline(height, rng)
    axis = [trunk_at(s / rings) for s in range(rings)]
    apex = trunk_at(1.0)
    radii = [r0 * (1.0 - fs.TRUNK_TAPER * s / rings) for s in range(rings)]
    add_tube(mesh, axis, radii, radial, 0, apex, uv_scale=(1.0, max(1.0, height / 3.0)))
    plan = fs.crown_plan(species)
    segments = _branch_segments(species, plan, trunk_at)
    family = fs.CROWN_FAMILIES[plan["family"]]
    # --- the skeleton -----------------------------------------------------------------
    # r11 (critic B10-1): the wood stops at `wood_reach` along the curve, INSIDE the needle
    # mass, and the cards below run all the way to the tip.  The curve itself is unchanged --
    # the sprays still hang on the full branch -- so this costs nothing in triangles and
    # nothing in crown reach; it only takes the bark out of the outline.
    wood_reach = float(family["wood_reach"])
    for segment in segments:
        tube_rings = layout["branch_rings"] if segment["kind"] == "main" else layout["sub_rings"]
        if not tube_rings:
            continue
        p0, p1, p2 = segment["curve"]
        r = segment["radius"]
        reach = max(
            fs.BRANCH_WOOD_MIN,
            min(wood_reach, 1.0 - fs.BRANCH_TIP_MARGIN_M / max(segment["length"], 1e-6)),
        )
        wood_tip = _bezier(p0, p1, p2, reach)
        # the tile repeats once per girth, so the texel is square on a branch of any length
        girth = 2.0 * math.pi * r
        wood_len = math.dist(p0, wood_tip)
        v_repeat = max(1.0, fs.BRANCH_UV_GIRTHS * wood_len / max(girth, 1e-6))
        # The rings sit ON the curve, not at the bezier's control point: the control polygon
        # overshoots the curve by half the sag, and the sprays are hung on the curve, so a
        # tube through p1 left a 0.2 m gap under every mid-branch spray.  r11: any ring count,
        # spread evenly over the WOOD, with the radius falling as (1-t)^p so a limb loses most
        # of its girth in its first third the way a real one does.
        points, radii = [], []
        for index in range(tube_rings):
            t = index / tube_rings
            points.append(_bezier(p0, p1, p2, t * reach) if index else p0)
            radii.append(r * (fs.BRANCH_MID_RADIUS ** (2.0 * t)))
        add_branch_tube(mesh, points, radii, fs.BRANCH_RADIAL, 1, wood_tip, v_repeat)
    # --- the cards: the leader first, then every branch by its length -----------------
    cards = layout["cards"]
    leader = min(fs.LEADER_CARDS[min(len(fs.LEADER_CARDS) - 1, layout.get("index", 0))], cards)
    foliage_from = family["foliage_from"]
    # a pine's needles sit on the last years of growth: weight by the FOLIAGED length
    weights = [max(segment["length"] * (1.0 - foliage_from), 0.2) for segment in segments]
    per_segment = fs.largest_remainder(cards - leader, weights) if segments else []
    half_lo, half_hi = fs.TWIG_CARD_HALF_M
    for _ in range(leader):
        # vertical sprays on the leader, base at the spire top: the tip is foliage, not a pole
        z = plan["spire_top"] + rng.uniform(0.0, 0.6) * (plan["tip"] - plan["spire_top"])
        point = trunk_at(min(z / height, 1.0))
        half = card_scale * min(
            rng.uniform(half_lo, half_hi), 0.5 * (plan["tip"] - plan["spire_top"])
        )
        yaw = rng.uniform(0.0, math.pi)
        right = (math.cos(yaw), math.sin(yaw), 0.0)
        centre = (point[0], point[1], point[2] + 0.92 * half)
        add_card(mesh, centre, right, (0.0, 0.0, 1.0), half, half, atlas_cell(grid, rng), slot=2)
    tuft = plan["family"] == "pine"
    for segment, count in zip(segments, per_segment, strict=True):
        p0, p1, p2 = segment["curve"]
        length = segment["length"]
        for index in range(count):
            # r11 (critic B10-1): the run is CLOSED at the tip.  r9-r10 put the outermost
            # spray's base at `1 - (1-foliage_from)*0.5/count` and let the wood carry on past
            # it; the branch's last card now sits ON the tip, so the outermost thing on every
            # branch is foliage at every LOD.
            s = foliage_from + (1.0 - foliage_from) * (index / max(count - 1, 1))
            s = min(1.0, max(0.05, s + rng.uniform(-0.04, 0.04)))
            point = _bezier(p0, p1, p2, s)
            ahead = _bezier(p0, p1, p2, min(1.0, s + 0.05))
            behind = _bezier(p0, p1, p2, max(0.0, s - 0.05))
            tangent = tuple(ahead[i] - behind[i] for i in range(3))
            side = (1.0 if index % 2 else -1.0) * math.radians(rng.uniform(18.0, 62.0))
            droop = rng.uniform(0.05, 0.25)
            if s > 0.9:
                side *= 0.3  # the terminal spray runs on along the branch
            if tuft and index == count - 1 and count > 2:
                # a pine's shoot tips turn UP: the LAST spray of every branch stands off the
                # tip like a candle, which is the tuft a scots pine reads by.  r11: r10 stood
                # the last TWO up, which took the horizontal front off the branch end and left
                # the wood as the outermost thing at that height band.  One candle keeps the
                # look; the spray before it stays lateral and covers the tip.
                side *= 0.5
                droop = -rng.uniform(0.35, 0.75)
            roll = (
                math.radians(rng.uniform(-30.0, 30.0))
                if rng.random() < 0.65
                else math.radians(rng.choice((-1.0, 1.0)) * rng.uniform(55.0, 90.0))
            )
            half = card_scale * min(rng.uniform(half_lo, half_hi), fs.TWIG_CARD_REACH_CAP * length)
            _spray_card(mesh, point, tangent, side, roll, droop, half, atlas_cell(grid, rng), rng)
    if mesh.tris != layout["budget"]:
        raise ValueError(
            f"{species['key']} _a{layout['px']}: {mesh.tris} triangles, budget {layout['budget']}"
        )
    return mesh


def snag_mesh(species: dict, tubes, rng: random.Random) -> Mesh:
    """A broken standing trunk: the main tube plus two stubs, no cards."""
    height = species["height_m"]
    r0 = height * fs.TRUNK_RADIUS_FRACTION * 1.4
    mesh = Mesh()
    radial, rings = tubes[0]
    axis, apex = trunk_axis(height * 0.92, rings, rng)
    radii = [r0 * (1.0 - 0.55 * s / rings) for s in range(rings)]
    add_tube(mesh, axis, radii, radial, 0, apex, uv_scale=(1.0, max(1.0, height / 2.5)))
    for stub_index, (stub_radial, stub_rings) in enumerate(tubes[1:]):
        fraction = 0.45 + 0.28 * stub_index + rng.uniform(-0.04, 0.04)
        base = axis[min(int(fraction * rings), rings - 1)]
        angle = rng.uniform(0.0, 2.0 * math.pi)
        reach = height * rng.uniform(0.10, 0.18)
        stub_axis, stub_radii = [], []
        for s in range(stub_rings):
            t = s / stub_rings
            stub_axis.append(
                (
                    base[0] + reach * t * math.cos(angle),
                    base[1] + reach * t * math.sin(angle),
                    base[2] + reach * t * 0.35,
                )
            )
            stub_radii.append(r0 * 0.30 * (1.0 - 0.7 * t))
        stub_apex = (
            base[0] + reach * math.cos(angle),
            base[1] + reach * math.sin(angle),
            base[2] + reach * 0.35,
        )
        add_tube(mesh, stub_axis, stub_radii, stub_radial, 0, stub_apex)
    return mesh


def card_cluster_mesh(
    species: dict,
    cards: int,
    grid,
    rng: random.Random,
    card_scale: float = 1.0,
    stem_rings: int = 0,
) -> Mesh:
    """A shrub / fern / reed clump: a woody stem if the row asks for one, then leaf cards.

    D7: ``stem_rings`` builds the tube first, on material slot 0, and the cards then take slot 1
    (a stemless shape keeps its cards on slot 0, so every fern and reed DAE stays byte-identical).
    """
    height = species["height_m"]
    shape = species.get("card_shape", "bush")
    mesh = Mesh()
    card_slot = 0
    if stem_rings:
        card_slot = 1
        _add_shrub_stem(mesh, species, stem_rings, rng)
    for index in range(cards):
        t = (index + 0.5) / cards
        if shape == "bush":
            z = height * (0.12 + 0.80 * (rng.random() ** 0.7))
            spread = height * 0.42 * (1.0 - (z / height) ** 1.5)
            tilt = rng.uniform(-0.35, 0.35)
        elif shape == "rosette":
            z = height * (0.08 + 0.55 * rng.random() ** 1.4)
            spread = height * 0.55 * (0.35 + 0.65 * rng.random())
            tilt = rng.uniform(-0.7, -0.1)
        elif shape == "dome":
            # r12 (critic B11-5): a broadleaf shrub is a DOME, not a cone.  Cards sit on (and
            # a little inside) an ellipsoid -- semi-axes 0.42 h across and 0.44 h up, centred
            # at 0.52 h -- so the silhouette is widest at half height, rounded on top and
            # narrower at the stems; `tilt` follows the ellipsoid's own surface normal
            # (clamped so the crown's cards still show from the side), and the card's FRONT
            # faces outward (`card_up` below), where "bush" faced it at the centre.
            # r13 (the user, 2026-09-16: "half circles"): a regular ellipsoid of dense
            # cards reads as a smooth ball from the road.  The crown is now three LOBES -
            # each card belongs to one, sits at that lobe's bearing (+- a gaussian spread),
            # on a radius jittered per card, and the lobes ride at different heights - so
            # the silhouette is lumpy with gaps between the lobes, the way a broadleaf
            # shrub branches, while the ellipsoid still bounds the whole crown.
            # D7 (the user, again, on the SAME complaint): r13's lobes were real in the
            # numbers and invisible on the plant, because the crown still ran all the way to
            # the ground -- cards from 0.08 h with a half-metre half-height reach the soil, so
            # the shrub is a ball sitting on grass and there is nowhere for a stem to show.
            # The crown now STARTS at 0.30 h, which is what makes the woody stem underneath it
            # visible at all (`_add_shrub_stem` reaches 0.55 h, well into the foliage), and the
            # lobes are lifted twice as far apart and clustered half as wide, so the gaps
            # between them survive the card density that swallowed them before.
            lobe = index % 3
            lobe_bearing = lobe * 2.0943951 + rng.uniform(-0.2, 0.2)
            lobe_lift = (0.14, -0.10, 0.04)[lobe] * height
            # D7, third pass: the lobes are now three separate BODIES, not three bearings
            # inside one ellipsoid.  r13 put each card on a lobe's bearing but still placed it
            # on the single crown ellipsoid, so the silhouette stayed an ellipsoid and the
            # lobes were invisible -- which is why the user reported the same spherical shrub
            # twice.  Each lobe is its own squashed ball, offset from the axis and lifted to
            # its own height, and the crown is their UNION: three bumps with real dips
            # between them, and no bound that is a sphere.
            lobe_centre = (
                LOBE_OFFSET_SHARE * height * math.cos(lobe_bearing),
                LOBE_OFFSET_SHARE * height * math.sin(lobe_bearing),
                LOBE_CENTRE_Z_SHARE * height + lobe_lift,
            )
            # a direction on the unit sphere, biased off the underside so the crown does not
            # spend cards where nobody sees them
            azimuth = rng.uniform(0.0, 2.0 * math.pi)
            cosine = rng.uniform(-0.70, 1.0)
            sine = math.sqrt(max(0.0, 1.0 - cosine * cosine))
            reach = rng.uniform(0.58, 1.04)
            offset = (
                reach * LOBE_SEMI_XY_SHARE * height * sine * math.cos(azimuth),
                reach * LOBE_SEMI_XY_SHARE * height * sine * math.sin(azimuth),
                reach * LOBE_SEMI_Z_SHARE * height * cosine,
            )
            dome_point = (
                lobe_centre[0] + offset[0],
                lobe_centre[1] + offset[1],
                min(max(lobe_centre[2] + offset[2], 0.30 * height), 0.98 * height),
            )
            dome_outward = _normalise(
                (
                    dome_point[0] - lobe_centre[0],
                    dome_point[1] - lobe_centre[1],
                    dome_point[2] - lobe_centre[2],
                )
            )
        else:  # tuft: near-vertical blades
            z = height * (0.30 + 0.55 * rng.random())
            spread = height * 0.16 * rng.random()
            tilt = rng.uniform(-0.1, 0.1)
        if shape == "dome":
            # the dome places in full 3D around its own lobe's centre, so it brings its own
            # point and its own outward direction rather than a (spread, angle, tilt) triple
            cx, cy, z = dome_point
            outward = dome_outward
        else:
            angle = 2.0 * math.pi * (t * 0.6180339887 % 1.0) + rng.uniform(-0.3, 0.3)
            cx, cy = spread * math.cos(angle), spread * math.sin(angle)
            outward = _normalise((math.cos(angle), math.sin(angle), tilt))
        side = _normalise(_cross(outward, (0.0, 0.0, 1.0)))
        up = _normalise(_cross(side, outward))
        roll = rng.uniform(0.0, math.pi)
        right = _normalise(
            tuple(math.cos(roll) * side[i] + math.sin(roll) * up[i] for i in range(3))
        )
        # `add_card` winds its quad so the face normal is `right x card_up`.  With
        # `card_up = right x outward` that normal is -outward: the front of every "bush" card
        # faces the plant's centre, and the bake writes that normal into the imposter's
        # normal atlas (r12, b3/r12/normals_eyes_r12_before.json).  The dome puts the front
        # outward; the three older shapes keep their winding so their DAEs do not move.
        if shape == "dome":
            card_up = _normalise(_cross(outward, right))
        else:
            card_up = _normalise(_cross(right, outward))
        # r2: a leaf card is sized in METRES, capped by the plant's own height, for the same
        # reason a twig card is (see conifer_mesh).  `height * 0.22..0.40` gave `shrub_02` --
        # a 5.3 m shrub -- cards 2.3-4.2 m WIDE, and a 4 m flat quad of leaf texture crossing
        # a hero frame is what that looks like from six metres.  A real leaf card is a hand
        # to a forearm across.
        # r12: a species may size its own cards (`card_half_m`, shrub_02); the cap stands
        half_range = species.get("card_half_m", fs.LEAF_CARD_HALF_M)
        half = card_scale * min(rng.uniform(*half_range), height * fs.LEAF_CARD_HEIGHT_CAP)
        add_card(
            mesh,
            (cx, cy, z),
            right,
            card_up,
            half,
            half * 0.9,
            atlas_cell(grid, rng),
            slot=card_slot,
        )
    return mesh


#: D7: how far up the plant the woody stem reaches, and its radius at the foot and at the top,
#: as shares of the height.  A broadleaf shrub's stem disappears into its own crown well before
#: the crown's top -- the dome's cards start at 0.10 h and its widest ring is at 0.52 h -- so a
#: stem to 0.55 h is seen at the base, where the user saw nothing, and is hidden above.
STEM_TOP_SHARE = 0.55
STEM_FOOT_RADIUS_SHARE = 0.030
STEM_TIP_RADIUS_SHARE = 0.011
#: how far the stem leans off vertical over its length, as a share of the height.  A dead
#: straight pole under a lumpy crown reads as a lamp post.
STEM_LEAN_SHARE = 0.07


#: D7: the crown's three lobes, each its own squashed ball.  ``LOBE_OFFSET_SHARE`` is how far a
#: lobe's centre stands off the plant's axis and ``LOBE_SEMI_*_SHARE`` are its semi-axes, all as
#: shares of the plant's height.  Offset 0.20 against a 0.30 semi-axis means neighbouring lobes
#: overlap by about a third -- joined into one crown, with a dip where they meet.
LOBE_OFFSET_SHARE = 0.20
LOBE_CENTRE_Z_SHARE = 0.62
LOBE_SEMI_XY_SHARE = 0.30
LOBE_SEMI_Z_SHARE = 0.25
#: D7: how far each stem's tip leans out from the foot, as a share of the height -- enough to
#: put it under its own lobe.
STEM_SPLAY_SHARE = 0.17
#: how far apart the stems stand at the ground.
STEM_FOOT_SPREAD_SHARE = 0.035


def _add_shrub_stem(mesh: Mesh, species: dict, rings: int, rng: random.Random) -> None:
    """The shrub's woody stems on slot 0: ``2 * STEM_RADIAL * rings`` triangles in total.

    D7, second pass.  ONE stem gave the plant a trunk and turned it into a lollipop -- a pole
    with a ball on it, which is not what a broadleaf shrub looks like either.  A shrub rises as
    SEVERAL stems from one root plate and each carries part of the crown, so the budget is split
    across three, one per crown lobe, splayed onto their lobes' bearings.  The ring budget is
    shared out as evenly as it divides (the leftover goes to the first stem), so the triangle
    count is exactly what `stem_layout` promised however the details are sized.
    """
    height = species["height_m"]
    top = STEM_TOP_SHARE * height
    splay = STEM_SPLAY_SHARE * height
    foot_spread = STEM_FOOT_SPREAD_SHARE * height
    stems = 3
    per_stem = [rings // stems] * stems
    for extra in range(rings - sum(per_stem)):
        per_stem[extra] += 1

    for index, stem_rings in enumerate(per_stem):
        if stem_rings < 1:
            continue
        bearing = index * 2.0943951 + rng.uniform(-0.25, 0.25)
        lean_x, lean_y = splay * math.cos(bearing), splay * math.sin(bearing)
        foot_x, foot_y = foot_spread * math.cos(bearing), foot_spread * math.sin(bearing)
        # the splay grows with the square of the height share, so the feet stand upright in
        # the ground and the spread happens up where the crown takes over
        axis, radii = [], []
        for ring in range(stem_rings):
            share = ring / stem_rings
            axis.append(
                (
                    foot_x + lean_x * share * share,
                    foot_y + lean_y * share * share,
                    top * share,
                )
            )
            radii.append(
                height
                * (
                    STEM_FOOT_RADIUS_SHARE
                    + (STEM_TIP_RADIUS_SHARE - STEM_FOOT_RADIUS_SHARE) * share
                )
            )
        apex = (foot_x + lean_x, foot_y + lean_y, top)
        add_tube(mesh, axis, radii, fs.STEM_RADIAL, 0, apex, uv_scale=(1.0, max(1.0, top)))


def _tube_split(budget: int, preferred_radial: int) -> tuple[int, int, int]:
    """(radial, rings, leftover cards) with ``2 * radial * rings + 2 * cards == budget``."""
    for radial in (preferred_radial, preferred_radial - 1, preferred_radial + 1, 4, 3):
        if radial < 3:
            continue
        rings = budget // (2 * radial)
        if rings >= 1:
            return radial, rings, (budget - 2 * radial * rings) // 2
    raise ValueError(f"cannot split a budget of {budget} triangles")


def cover_mesh(cover: dict, rng: random.Random) -> Mesh:
    """A 0.1-0.6 m scatter shape: a jittered lump / flake / cone / twig / chip."""
    mesh = Mesh()
    kind, budget = cover["kind"], cover["tris"]
    if kind in ("lump", "flake", "cone"):
        radial, rings, cards = _tube_split(budget, 6 if kind == "cone" else 5)
        top = 0.5 if kind == "flake" else (1.4 if kind == "cone" else 1.0)
        base_radius = 0.32 if kind == "cone" else 0.5
        axis, radii = [], []
        for s in range(rings):
            t = s / rings
            axis.append((rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05), top * t))
            radii.append(base_radius * (1.0 - 0.75 * t) * rng.uniform(0.8, 1.15))
        add_tube(mesh, axis, radii, radial, 0, (0.0, 0.0, top))
        for index in range(cards):
            angle = 2.0 * math.pi * (index * 0.6180339887 % 1.0)
            add_card(
                mesh,
                (0.3 * math.cos(angle), 0.3 * math.sin(angle), 0.15 * top),
                (math.cos(angle), math.sin(angle), 0.0),
                (0.0, 0.0, 1.0),
                0.14,
                0.10,
                (0.0, 0.0, 1.0, 1.0),
                slot=0,
            )
    else:  # twig / chip: flat cards
        for index in range(budget // 2):
            angle = 2.0 * math.pi * (index * 0.6180339887 % 1.0)
            add_card(
                mesh,
                (rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2), 0.02 + 0.01 * index),
                (math.cos(angle), math.sin(angle), 0.0),
                (-math.sin(angle) * 0.1, math.cos(angle) * 0.1, 1.0),
                0.5,
                0.09,
                (0.0, 0.0, 1.0, 1.0),
                slot=0,
            )
    return mesh


def assert_positive_volume(obj, label: str) -> None:
    """A DECIMATED CONVEX HULL must enclose a positive signed volume (divergence theorem).

    r1 reported that ``assert_outward()`` "now runs on every collision mesh".  It did not: it
    is a per-face radial test that only makes sense on the 18 procedural cones, so the 36
    Colmeshes that come out of ``convex_hull_of`` -- two thirds of them -- were unchecked.
    The general statement of "wound outward" for an arbitrary closed hull is
    ``sum a . (b x c) / 6 > 0``, which is exactly what the critic used to audit the shipped
    meshes, so that is what runs here.  It also catches a hull the decimator has torn open.
    """
    mesh = obj.data
    mesh.calc_loop_triangles()
    verts = [tuple(v.co) for v in mesh.vertices]
    volume = 0.0
    faces = 0
    for tri in mesh.loop_triangles:
        a, b, c = (verts[i] for i in tri.vertices)
        volume += (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            + a[1] * (b[2] * c[0] - b[0] * c[2])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        ) / 6.0
        faces += 1
    if faces and volume <= 0.0:
        raise SystemExit(f"{label}: collision hull has signed volume {volume:.6f} (inside-out)")


def assert_outward(mesh: Mesh, label: str) -> None:
    """Every face of a collision cone must face OUT (the bottom cap faces down).

    A back-facing collision triangle is invisible to ``castRayStatic``, so this is the gate
    that would have caught the inverted apex fan before it reached the sentinel.  It applies
    to the 18 procedural cones; :func:`assert_positive_volume` covers the 36 decimated hulls.
    """
    for index, (a, b, c) in enumerate(mesh.faces):
        pa, pb, pc = mesh.verts[a], mesh.verts[b], mesh.verts[c]
        u = tuple(pb[i] - pa[i] for i in range(3))
        v = tuple(pc[i] - pb[i] for i in range(3))
        normal = _cross(u, v)
        centre = tuple((pa[i] + pb[i] + pc[i]) / 3.0 for i in range(3))
        radial = math.hypot(centre[0], centre[1])
        outward = (normal[0] * centre[0] + normal[1] * centre[1]) / radial if radial > 1e-9 else 0.0
        if outward < -1e-9 or (radial <= 1e-9 and normal[2] > 1e-9):
            raise SystemExit(
                f"{label}: collision face {index} at z {centre[2]:.3f}, r {radial:.3f} is "
                f"inside-out (normal {normal})"
            )


def colmesh_tube_mesh(species: dict) -> Mesh:
    """The analytic Colmesh cone the live ray census predicts (``fs.colmesh_profile``).

    Straight (no lean) on purpose: the predictor is a closed form in (radius, height), and a
    leaning cone would make the live window a lie.
    """
    profile = fs.colmesh_profile(species)
    mesh = Mesh()
    axis = [(0.0, 0.0, z) for z, _ in profile["rings"]]
    radii = [r for _, r in profile["rings"]]
    add_tube(mesh, axis, radii, profile["radial"], 0, (0.0, 0.0, profile["apex_z"]))
    assert_outward(mesh, f"{species['key']} Colmesh")
    return mesh


def cover_colmesh_mesh(cover: dict) -> Mesh:
    radial, rings = fs.COVER_COLMESH_TUBE
    mesh = Mesh()
    add_tube(mesh, [(0.0, 0.0, 0.0)] * rings, [0.45] * rings, radial, 0, (0.0, 0.0, 0.5))
    assert_outward(mesh, f"{cover['key']} Colmesh")
    return mesh


# -------------------------------------------------------------------------- Blender plumbing
def _bpy():
    import bpy

    return bpy


def _bmesh():
    import bmesh

    return bmesh


def clear_scene() -> None:
    bpy = _bpy()
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_material(name: str):
    bpy = _bpy()
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    return material


def empty(name: str, parent=None):
    bpy = _bpy()
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    return obj


def object_from_mesh(name: str, mesh: Mesh, materials, parent):
    bpy = _bpy()
    data = bpy.data.meshes.new(name)
    data.from_pydata(mesh.verts, [], mesh.faces)
    data.update()
    for material in materials:
        data.materials.append(material)
    uv_layer = data.uv_layers.new(name="UVMap")
    for index, polygon in enumerate(data.polygons):
        polygon.material_index = min(mesh.slots[index], len(materials) - 1)
        for k, loop in enumerate(polygon.loop_indices):
            uv_layer.data[loop].uv = mesh.uvs[index * 3 + k]
    data.validate(verbose=False)
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    return obj


#: directions of the SUPPORT HULL used for the source-scan reading.  `mesh_audit.convex_hull`
#: is exact and stdlib -- which is what the static gate needs on our decimated shipped meshes
#: (<= 5k vertices, 0.16 s) -- but a raw CC0 scan is 50-120k vertices and NEARLY CONVEX, so
#: almost every vertex survives the interior pre-filter and the incremental step degenerates to
#: O(n x faces).  Here the cloud is first reduced to the extreme point along each of these
#: directions, which for a convex body converges to the hull from BELOW.  The error is
#: measured, not assumed: `b3/r10/support_hull_check.py` reports it against an exact hull on
#: every rock and deadwood scan in the cache.
SUPPORT_DIRECTIONS = 1024


def support_directions(count: int = SUPPORT_DIRECTIONS):
    """`count` roughly uniform directions on the sphere (Fibonacci lattice, deterministic)."""

    import numpy as np

    k = np.arange(count, dtype=np.float64) + 0.5
    z = 1.0 - 2.0 * k / count
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    phi = k * math.pi * (3.0 - math.sqrt(5.0))
    return np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)


def support_hull_volume(verts) -> float:
    """Hull volume of a big cloud through its support points (see SUPPORT_DIRECTIONS)."""

    import numpy as np

    if len(verts) < 4:
        return 0.0
    if len(verts) <= SUPPORT_DIRECTIONS:
        return mesh_audit.hull_volume([tuple(p) for p in np.asarray(verts).tolist()])
    picks = np.unique(np.argmax(np.asarray(verts) @ support_directions().T, axis=0))
    return mesh_audit.hull_volume([tuple(p) for p in np.asarray(verts)[picks].tolist()])


def scan_reading(obj, largest_part: bool, asset: str) -> dict:
    """fill / solidity of the CC0 scan AS IT ARRIVES, before this module touches it.

    The husk gate's DEADWOOD clause compares the shipped body with this, so it is measured
    here -- before the weld, the seal and the remesh, every one of which only ever FILLS -- and
    written into the build manifest, where a static gate can read it without the git-ignored
    ``cc0_cache``.  Statistics are scale-invariant, so it does not matter that the caller has
    already scaled the object to its design size.

    The reference is the WHOLE thing the importer was handed, `largest_part` or not.  The first
    cut took the largest loose part wherever a default crumb share would drop the other shells,
    and that was wrong twice over: `voxel_solid`'s CLOSING widens until every kept shell is a
    ball, so two plates a few centimetres apart come out as ONE shell and nothing is dropped
    (`windthrow_roots`, measured); and where a shell really is dropped, our body loses a distant
    piece and its solidity goes UP, so the joined figure is the conservative bar either way.
    It also matters that this runs in Blender rather than off the glTF: the raw POSITION
    accessors ignore the NODE TRANSFORMS that place a multi-piece asset, which stacks
    `bark_debris_01`'s four pieces at the origin and reads its solidity 0.78 where the placed
    assembly reads 0.13.
    """

    import numpy as np

    verts, faces = mesh_arrays(obj)
    if largest_part and len(faces):  # kept for the record; the caller passes False (see above)
        # loose parts, by union-find over the welded lattice (a glTF splits at every UV seam,
        # so raw connectivity would see charts; 1e-5 m closes those and nothing else)
        keys = np.round(verts / 1e-5).astype(np.int64)
        _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
        welded, tris = verts[first], inverse[faces]
        parent = np.arange(len(welded), dtype=np.int64)

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = int(parent[x])
            return x

        for a, b, c in tris:
            for u, v in ((int(a), int(b)), (int(b), int(c))):
                ru, rv = find(u), find(v)
                if ru != rv:
                    parent[ru] = rv
        roots = np.array([find(int(v)) for v in tris[:, 0]])
        labels, counts = np.unique(roots, return_counts=True)
        keep = tris[roots == labels[int(np.argmax(counts))]]
        used = np.unique(keep)
        remap = -np.ones(len(welded), dtype=np.int64)
        remap[used] = np.arange(len(used))
        verts, faces = welded[used], remap[keep]
    if not len(faces):
        return {"asset": asset, "reference": "empty", "fill": 0.0, "solidity": 0.0}
    centred = verts - verts.mean(axis=0)
    _, _, vh = np.linalg.svd(centred, full_matrices=False)
    local = centred @ vh.T
    e = np.sort(local.max(axis=0) - local.min(axis=0))[::-1]
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    volume = float(abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)
    box = float(e[0] * e[1] * e[2])
    hull = support_hull_volume(verts)
    return {
        "asset": asset,
        "reference": "largest_part" if largest_part else "joined",
        "tris": len(faces),
        "verts": len(verts),
        "hull": "exact" if len(verts) <= SUPPORT_DIRECTIONS else f"support_{SUPPORT_DIRECTIONS}",
        "fill": round(volume / box, 4) if box else 0.0,
        "solidity": round(volume / hull, 4) if hull else 0.0,
    }


def import_model(
    cache: Path,
    asset: str,
    part: int | None,
    mirror: bool,
    target_size: float,
    solid: str | None = None,
    seed: int = 0,
    solid_shells: float | None = None,
    skirt_rows: float | None = None,
    body_depth: float | None = None,
):
    """Import one CC0 glTF, keep one loose part, scale its longest axis to ``target_size``.

    ``solid="face"`` (r9) rebuilds a cliff-FACE scan as a body through
    ``rock_solid.solid_from_face_scan`` instead of capping the sheet; ``"face_voxel"`` (D7)
    is that body put through the voxel remesher afterwards, which is what the three cliffs
    ship; everything else is welded across its photogrammetry islands and sealed as before.
    """
    bpy = _bpy()
    path = cache / asset / f"{asset}_2k.gltf"
    if not path.is_file():
        raise SystemExit(f"missing CC0 model {path}")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    if not imported:
        raise SystemExit(f"{asset}: the glTF carried no mesh")
    bpy.ops.object.select_all(action="DESELECT")
    # r10: `part` MUST index the glTF's own meshes -- one scanned rock each -- and NOT loose
    # geometry.  A glTF splits its vertex buffer at every UV/normal seam and Blender's importer
    # does not weld, so joining first and then `separate(type="LOOSE")` cuts the file into UV
    # CHARTS: `rock_moss_set_01` has 6 meshes and **71 loose pieces**, `_02` has 7 and 26
    # (`b3/r10/blender_part_probe.py`, and `b3/r10/scan_probe.py` welds them back to 6 and 7).
    # r9 shipped the loose ordering, so `part=2` of `rock_moss_set_01` was a 4,044-poly chart
    # fragment of the 10,996-poly rock -- which is why `mossy_rock_c` came out genus 2, "24
    # components at 2 cm", fill 0.188 / solidity 0.489, and why the user called the rocks
    # flakes.  Every part of both sets measures solidity 0.763-0.890 AT SOURCE.
    part_source = "loose"
    if part is not None and len(imported) > 1:
        part_source = "objects"
        objects = sorted(imported, key=lambda o: -len(o.data.polygons))
        keep = objects[min(part, len(objects) - 1)]
        for obj in objects:
            if obj is not keep:
                bpy.data.objects.remove(obj, do_unlink=True)
        merged = keep
        bpy.ops.object.select_all(action="DESELECT")
        merged.select_set(True)
        bpy.context.view_layer.objects.active = merged
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    else:
        # every imported object must be SELECTED for `join()` to take it -- the r9 route
        for obj in imported:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = imported[0]
        if len(imported) > 1:
            bpy.ops.object.join()
        merged = bpy.context.view_layer.objects.active
        merged.select_set(True)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        if part is not None:
            # a single-mesh file: loose parts are the only decomposition there is
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.separate(type="LOOSE")
            bpy.ops.object.mode_set(mode="OBJECT")
            pieces = sorted(
                (o for o in bpy.context.selected_objects if o.type == "MESH"),
                key=lambda o: -len(o.data.polygons),
            )
            keep = pieces[min(part, len(pieces) - 1)]
            for obj in pieces:
                if obj is not keep:
                    bpy.data.objects.remove(obj, do_unlink=True)
            merged = keep
    PART_REPORT.clear()
    PART_REPORT.update(
        part_index=part,
        part_source=part_source,
        imported_objects=len(imported),
        kept_polys=len(merged.data.polygons),
        # r10: what the SCAN reads before this module touches it, so the husk gate has a
        # reference for the DEADWOOD class (the rock bars are a category error on branched
        # wood: a pile of sticks has a hull the size of the pile).  Measured on the piece the
        # pipeline will KEEP -- the largest loose part when a default crumb share will drop
        # every other shell, the join otherwise -- because a multi-piece asset's joined figure
        # is a packing artefact of how its author laid the pieces out in the file.
        source_reading=scan_reading(merged, largest_part=False, asset=asset),
    )
    bpy.ops.object.select_all(action="DESELECT")
    merged.select_set(True)
    bpy.context.view_layer.objects.active = merged
    # centre on the ground at the origin, then scale the longest axis to the design's size
    dimensions = list(merged.dimensions)
    factor = target_size / max(dimensions) if max(dimensions) else 1.0
    merged.scale = (-factor if mirror else factor, factor, factor)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if mirror:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")
    # r3 (D7): close the shell BEFORE any LOD is cut from it.  `rock_face_01` and
    # `mountainside` are scans of a cliff FACE, not closed solids, and an open shell seen from
    # behind is what the r2 crest frame shows as a third of a sky full of tan ribbons.
    # Closing it first also unblocks the decimator, which will not collapse across a boundary
    # and was falling back to a weld of up to 25 % of the model's span -- which tore it open
    # again.
    # r9: a face scan CAPPED is still a facade (a 0.75 m shell in a convex hull, critic B2
    # pass 5).  Those three become bodies; the closed-ish scans are first welded across
    # their islands, which is where the mossy rocks' and the lichen boulder's 4 boundary /
    # 2 non-manifold edges per LOD came from.
    scan_foot = min(v.co[2] for v in merged.data.vertices)
    IMPORT_REPORT.clear()
    if solid in ("face", "face_voxel"):
        IMPORT_REPORT.update(
            face_scan_solid(merged, seed, skirt_row_share=skirt_rows, body_depth_share=body_depth)
        )
        if solid == "face_voxel":
            # D7 / amendment A7 (2026-09-17, the user on their own drive: the cliffs are "not
            # water tight and they have very strange slices through them").  The face solid's
            # SKIRT -- the invented walls and underside behind the scan -- is cut into rows,
            # and a row is a ledge: the shipped bytes put 47.7 / 32.6 / 22.8 % of their surface
            # AREA into blade triangles folding back through 160-171 deg.  A5 tried finer rows
            # alone (sliver 47.7 -> 30.9 %, not enough) and remeshing the finished body alone
            # ("face_voxel", which is this route without the row change: `cliff_outcrop_a` came
            # out at genus 3 and the closing sweep chasing those handles inflated the rocks by
            # 2.1 m, swallowing 456 forest instances).  NEITHER WAS EVER COMBINED, and the
            # combination is what works, because the handles ARE the rows: near-parallel
            # ledges about a metre apart, and a voxel at span / VOXEL_CELLS (0.13 m on a 21 m
            # rock) unions two of them into a tunnel.  Take the ledges out first
            # (`rock_solid.SKIRT_ROW_SHARE` 0.05 -> 0.008) and the remesher has almost nothing
            # left to bridge.  MEASURED, `round_records/d7/body/`, worst LOD of each shape:
            #
            #   shape             sliver>8   genus  solidity  fill   bbox growth
            #   cliff_outcrop_a   0.477 -> 0.014   1   0.678   0.289   +1.15 m
            #   cliff_outcrop_b   0.326 -> 0.019   0   0.777   0.246   +0.18 m
            #   crag              0.228 -> 0.010   0   0.903   0.295   -0.44 m
            #
            # A FINER voxel is worse, not better (cells 320 -> genus 10, 440 -> genus 2): a
            # fine voxel RESOLVES the scan's own arches where a coarse one fills them, which
            # is A5's finding on the bare scan and holds here too.  `VOXEL_CELLS` stays 200.
            # `cliff_outcrop_a`'s remaining handle is the scan's own arch (the source reads
            # genus 4) and is DECLARED on its row as `solid_genus`; it survives the full
            # closing ladder, so it is a real ~4 m opening, not a crumb.
            IMPORT_REPORT.update(
                voxel_solid(merged, VOXEL_CRUMB_SHARE if solid_shells is None else solid_shells)
            )
    elif solid == "voxel":
        # r9: the closed-ish scans.  Welding closed most islands but not the seams that run
        # through a non-manifold junction (mossy_rock_b: 2 boundary / 1 non-manifold edge at
        # every LOD after the weld, lichen_boulder 4 / 2), and the logs came out of the
        # decimator as bow-tie soup.  The voxel remesher rebuilds the surface with clean
        # topology whatever the scan's was; the cap first gives it a bottom to fill from.
        weld_islands(merged)
        seal_shell(merged)
        IMPORT_REPORT.update(
            voxel_solid(merged, VOXEL_CRUMB_SHARE if solid_shells is None else solid_shells)
        )
    else:
        weld_islands(merged)
        seal_shell(merged)
    low = [min(v.co[i] for v in merged.data.vertices) for i in range(3)]
    high = [max(v.co[i] for v in merged.data.vertices) for i in range(3)]
    # r9: a face solid's underside is sunk BELOW the scan's foot on purpose (rock_solid), and
    # the foot the player sees must stay at z = 0 on the terrain -- so the floor is the SCAN's
    # lowest point, not the body's
    floor = scan_foot if solid in ("face", "face_voxel") else low[2]
    offset = (-(low[0] + high[0]) / 2.0, -(low[1] + high[1]) / 2.0, -floor)
    for vertex in merged.data.vertices:
        vertex.co = (vertex.co[0] + offset[0], vertex.co[1] + offset[1], vertex.co[2] + offset[2])
    merged.data.update()
    return merged


#: r9: photogrammetry islands whose borders sit within this share of the shape's span are
#: ONE surface (0.06 m on the 41 m crag, 1.2 cm on the 8 m lichen boulder)
ISLAND_WELD_FRACTION = 0.0015
#: r9: what the last `import_model` did to its scan (the face-solid or voxel report), for
#: the build manifest -- filled per shape, one Blender process per shape
IMPORT_REPORT: dict = {}
#: r10: WHICH piece of a multi-rock scan the row's ``part`` index selected, and by which
#: decomposition.  ``part_source="objects"`` is the glTF's own meshes (one rock each);
#: ``"loose"`` is the r9 route and is only correct for a single-mesh file.  Published in the
#: build manifest and gated in `tests/test_hot_potato_forest.py`.
PART_REPORT: dict = {}


def mesh_arrays(obj):
    """(verts (V, 3), triangles (F, 3)) of a mesh object, as numpy, via foreach_get."""
    import numpy as np

    mesh = obj.data
    mesh.calc_loop_triangles()
    verts = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", verts)
    tris = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get("vertices", tris)
    return verts.reshape(-1, 3), tris.reshape(-1, 3)


def replace_mesh(obj, verts, faces) -> None:
    """Swap the object's mesh for ``(verts, faces)`` built with ``from_pydata``."""
    bpy = _bpy()
    fresh = bpy.data.meshes.new(obj.data.name + ".solid")
    fresh.from_pydata([tuple(v) for v in verts.tolist()], [], [tuple(f) for f in faces.tolist()])
    fresh.validate(verbose=False)
    fresh.update()
    old = obj.data
    obj.data = fresh
    bpy.data.meshes.remove(old)


def _edit(obj, operation) -> None:
    bpy = _bpy()
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    operation()
    bpy.ops.object.mode_set(mode="OBJECT")


def weld_islands(obj) -> int:
    """Merge island borders that sit within ISLAND_WELD_FRACTION of the span; return the count."""
    bpy = _bpy()
    span = max(obj.dimensions) or 1.0
    _edit(obj, lambda: bpy.ops.mesh.remove_doubles(threshold=span * ISLAND_WELD_FRACTION))
    return len(obj.data.polygons)


def solidity(obj) -> dict:
    """Signed volume, boundary and non-manifold edge counts of the mesh as it stands."""
    import numpy as np

    verts, faces = mesh_arrays(obj)
    boundary, nonmanifold = rock_solid.edge_census(faces)
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    used = np.unique(faces)
    return {
        "volume_m3": round(rock_solid.signed_volume(verts, faces), 4),
        "boundary": boundary,
        "nonmanifold": nonmanifold,
        "tris": len(faces),
        # V - E + F: 2 for a ball, 2 - 2g with g handles (mesh_audit reads the same number)
        "chi": int(len(used) - len(np.unique(edges, axis=0)) + len(faces)),
    }


def ensure_solid(obj, budget: int | None = None) -> dict:
    """Make the shell outward and closed where it can be, and REPORT what it is (r9).

    ``mesh_audit`` (B4) and ``collider_probe`` read the shipped file; this is the build's own
    account of the same three numbers per detail.  Two of the r8 cliffs and one crag LOD had
    NEGATIVE volume -- wound inward -- which is what a convex hull around them turned into
    a phantom wall; a negative volume is flipped, an open boundary is capped once more, and
    the count is decimated back under the budget if the cap pushed it over.
    """
    bpy = _bpy()
    _edit(obj, lambda: bpy.ops.mesh.normals_make_consistent(inside=False))
    report = solidity(obj)
    if report["volume_m3"] < 0:
        _edit(obj, lambda: bpy.ops.mesh.flip_normals())
        report = solidity(obj)
        report["flipped"] = True
    if report["boundary"] or report["nonmanifold"]:
        close_shell(obj)
        if budget is not None and len(obj.data.polygons) > budget:
            decimate_to(obj, budget)
        _edit(obj, lambda: bpy.ops.mesh.normals_make_consistent(inside=False))
        report = dict(solidity(obj), recapped=True)
        if report["volume_m3"] < 0:
            _edit(obj, lambda: bpy.ops.mesh.flip_normals())
            report = dict(solidity(obj), recapped=True, flipped=True)
    report["solid"] = bool(
        report["boundary"] == 0 and report["nonmanifold"] == 0 and report["volume_m3"] > 0
    )
    return report


def face_scan_solid(
    obj, seed: int, skirt_row_share: float | None = None, body_depth_share: float | None = None
) -> dict:
    """Rebuild a cliff-face scan as a body and give its front the scan's own UVs (r9)."""

    bpy = _bpy()
    verts, faces = mesh_arrays(obj)
    built = rock_solid.solid_from_face_scan(
        verts, faces, seed, skirt_row_share=skirt_row_share, body_depth_share=body_depth_share
    )
    new_verts, new_faces = built["verts"], built["faces"]
    if rock_solid.signed_volume(new_verts, new_faces) < 0:
        new_faces = new_faces[:, ::-1].copy()
    # keep the scan as the UV source until the front has its UVs
    source = obj.copy()
    source.data = obj.data.copy()
    source.name = obj.name + ".uvsource"
    bpy.context.collection.objects.link(source)
    replace_mesh(obj, new_verts, new_faces)
    mesh = obj.data
    transfer_scan_uvs(obj, source)
    bpy.data.objects.remove(source, do_unlink=True)
    # the body (back and skirts) gets a box projection at the front's own texel density
    uv_layer = mesh.uv_layers.active
    front = built["front_faces"]
    density = []
    for index in range(0, front, max(1, front // 3000)):
        polygon = mesh.polygons[index]
        if len(polygon.loop_indices) < 3 or polygon.area <= 1e-9:
            continue
        a, b, c = (uv_layer.data[i].uv for i in polygon.loop_indices[:3])
        texel = abs((b - a).cross(c - a)) * 0.5
        if texel > 0:
            density.append(texel / polygon.area)
    scale = math.sqrt(sorted(density)[len(density) // 2]) if density else 0.1
    for index in range(front, len(mesh.polygons)):
        polygon = mesh.polygons[index]
        axis = max(range(3), key=lambda i: abs(polygon.normal[i]))
        u_axis, v_axis = [i for i in range(3) if i != axis]
        for loop_index in polygon.loop_indices:
            point = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            uv_layer.data[loop_index].uv = (point[u_axis] * scale, point[v_axis] * scale)
    mesh.update()
    _edit(obj, lambda: bpy.ops.mesh.normals_make_consistent(inside=False))
    if rock_solid.signed_volume(*mesh_arrays(obj)) < 0:
        _edit(obj, lambda: bpy.ops.mesh.flip_normals())
    report = solidity(obj)
    report.update({k: v for k, v in built.items() if k not in ("verts", "faces", "rotation")})
    return report


#: r9: the voxel remesher's cells across the shape's span.  At 200 an 8 m boulder is 4 cm
#: voxels, an order under the 0.3 m edges its finest detail ships with, so nothing a player
#: sees moves; what changes is the TOPOLOGY, which comes back closed and manifold whatever the
#: scan's was -- the mossy rocks' and the lichen boulder's seams (2-4 boundary / 1-2
#: non-manifold edges at every LOD, which `remove_doubles` could not close), the logs' and
#: stumps' bow-ties, mossy_rock_b's inverted LOD.
VOXEL_CELLS = 200
#: a morphological CLOSING around the remesh, in voxels.  The mossy scans carry their moss as
#: a sheet a few centimetres off the rock, and a level set meshes that gap as a TUNNEL: the
#: first voxel cut gave lichen_boulder genus 11 and mossy_rock_b genus 6 (mesh_audit chi -20
#: and -10 at every LOD) whose handles the decimator cannot remove, so they collapsed into a
#: cluster of 88 slivers at 80 px.  Fatten the surface by this many voxels, remesh (a gap
#: narrower than twice it unions shut), shrink back, remesh once more for the topology --
#: and widen the closing until every kept shell IS a ball (chi = 2), because two voxels
#: took the lichen boulder only from genus 11 to genus 3.
VOXEL_CLOSING_STEPS = (0.0, 2.0, 4.0, 6.0, 9.0, 12.0, 16.0)
#: a remeshed shell under this share of the total volume is dropped.  The default keeps the
#: LARGEST shell only: a boulder is one body, and a moss patch the scan carried as its own
#: skin comes out of the remesher as a second closed shell whose tiny triangles then own the
#: detail's median (lichen_boulder's 80 px detail: 5.3 m2 faces at 133x a moss-patch median).
#: A cluster species says otherwise on its row (``solid_shells``).
VOXEL_CRUMB_SHARE = 1.0


def voxel_solid(obj, crumb_share: float = VOXEL_CRUMB_SHARE) -> dict:
    """Re-mesh the (welded, capped) scan through the voxel remesher and keep its UVs (r9).

    OpenVDB's mesh-to-level-set fills the inside of a closed-enough surface and meshes the
    zero level, so the result is a closed manifold by construction.  The scan's UVs are then
    transferred back per corner from the nearest scan polygon, the way ``face_scan_solid``
    gives a rebuilt front its photograph.  Returns the build's own solidity reading.
    """
    bpy = _bpy()
    span = max(obj.dimensions) or 1.0
    before = solidity(obj)
    source = obj.copy()
    source.data = obj.data.copy()
    source.name = obj.name + ".uvsource"
    bpy.context.collection.objects.link(source)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    voxel = span / VOXEL_CELLS

    def remesh() -> None:
        modifier = obj.modifiers.new(name="voxel", type="REMESH")
        modifier.mode = "VOXEL"
        modifier.voxel_size = voxel
        modifier.adaptivity = 0.0
        modifier.use_smooth_shade = False
        bpy.ops.object.modifier_apply(modifier=modifier.name)

    def displace(distance: float) -> None:
        modifier = obj.modifiers.new(name="closing", type="DISPLACE")
        modifier.direction = "NORMAL"
        modifier.mid_level = 0.0
        modifier.strength = distance
        bpy.ops.object.modifier_apply(modifier=modifier.name)

    def drop_crumbs() -> tuple[int, int]:
        """Separate the shells, weigh them, join the ones that are rock back: (kept, dropped)."""
        _edit(obj, lambda: bpy.ops.mesh.separate(type="LOOSE"))
        pieces = [o for o in bpy.context.selected_objects if o.type == "MESH"]
        if obj not in pieces:
            pieces.append(obj)
        volumes = {o.name: abs(solidity(o)["volume_m3"]) for o in pieces}
        total = sum(volumes.values()) or 1.0
        biggest = max(pieces, key=lambda o: volumes[o.name])
        crumbs = [o for o in pieces if o is not biggest and volumes[o.name] < crumb_share * total]
        survivors = [o for o in pieces if o not in crumbs or o is obj]
        kept = len([o for o in pieces if o not in crumbs])
        for crumb in crumbs:
            if crumb is obj:
                _edit(obj, lambda: bpy.ops.mesh.delete(type="VERT"))
            else:
                bpy.data.objects.remove(crumb, do_unlink=True)
        bpy.ops.object.select_all(action="DESELECT")
        for piece in survivors:
            piece.select_set(True)
        bpy.context.view_layer.objects.active = obj
        if len(survivors) > 1:
            bpy.ops.object.join()
        return kept, len(crumbs)

    remesh()
    closing_used, shells, dropped, chi = 0.0, 1, 0, 0
    for closing in VOXEL_CLOSING_STEPS:
        if closing:
            displace(closing * voxel)
            remesh()
            displace(-closing * voxel)
            remesh()
        shells, dropped = drop_crumbs()
        chi = solidity(obj)["chi"]
        closing_used = closing
        if chi == 2 * shells:
            break
    triangulate(obj)
    transfer_scan_uvs(obj, source)
    bpy.data.objects.remove(source, do_unlink=True)
    _edit(obj, lambda: bpy.ops.mesh.normals_make_consistent(inside=False))
    if rock_solid.signed_volume(*mesh_arrays(obj)) < 0:
        _edit(obj, lambda: bpy.ops.mesh.flip_normals())
    report = solidity(obj)
    report.update(
        {
            "kind": "voxel",
            "voxel_m": round(voxel, 4),
            "scan": before,
            "shells_kept": shells,
            "crumbs_dropped": dropped,
            "closing_voxels": closing_used,
            "chi_after_closing": chi,
        }
    )
    return report


def transfer_scan_uvs(obj, source) -> None:
    """Give every face of ``obj`` the UVs of ONE nearest scan triangle of ``source`` (r9).

    Per FACE, not per corner.  The first cut used the Data Transfer modifier's
    nearest-polygon-interpolated loop mapping, and a rebuilt face that straddles one of the
    scan's UV islands then had corners on two islands -- a discontinuity INSIDE the face,
    which the decimator blended across every collapse until 48-96 % of a mossy rock's or a
    log's area was 3x off its own texel density (``b3/r9/uv_probe_r8.json`` against the
    first r9 cut; r8's own decimation of the scan read 2-16 %).  Choosing one scan triangle
    per face and extrapolating its barycentric UVs to the three corners puts every
    discontinuity ON an edge, which is a seam the decimator keeps.  Everything but the
    nearest-triangle query is numpy; the query is Blender's BVH.
    """
    import numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    scan = source.data
    scan.calc_loop_triangles()
    scan_uv = scan.uv_layers.active
    if scan_uv is None or not len(scan.loop_triangles):
        return
    scan_verts = np.empty(len(scan.vertices) * 3, dtype=np.float64)
    scan.vertices.foreach_get("co", scan_verts)
    scan_verts = scan_verts.reshape(-1, 3)
    tri_loops = np.empty(len(scan.loop_triangles) * 3, dtype=np.int64)
    scan.loop_triangles.foreach_get("loops", tri_loops)
    tri_verts = np.empty(len(scan.loop_triangles) * 3, dtype=np.int64)
    scan.loop_triangles.foreach_get("vertices", tri_verts)
    tri_loops, tri_verts = tri_loops.reshape(-1, 3), tri_verts.reshape(-1, 3)
    uv_all = np.empty(len(scan_uv.data) * 2, dtype=np.float64)
    scan_uv.data.foreach_get("uv", uv_all)
    tri_uv = uv_all.reshape(-1, 2)[tri_loops]  # (T, 3, 2)
    tri_p = scan_verts[tri_verts]  # (T, 3, 3)
    bvh = BVHTree.FromPolygons(
        [tuple(v) for v in scan_verts.tolist()],
        [tuple(t) for t in tri_verts.tolist()],
        all_triangles=True,
    )
    mesh = obj.data
    centres = np.empty(len(mesh.polygons) * 3, dtype=np.float64)
    mesh.polygons.foreach_get("center", centres)
    centres = centres.reshape(-1, 3)
    nearest = np.fromiter(
        (bvh.find_nearest(Vector(c))[2] for c in centres.tolist()),
        dtype=np.int64,
        count=len(centres),
    )
    loop_start = np.empty(len(mesh.polygons), dtype=np.int64)
    mesh.polygons.foreach_get("loop_start", loop_start)
    loop_total = np.empty(len(mesh.polygons), dtype=np.int64)
    mesh.polygons.foreach_get("loop_total", loop_total)
    face_of_loop = np.empty(len(mesh.loops), dtype=np.int64)
    if np.array_equal(loop_start, np.cumsum(loop_total) - loop_total):
        face_of_loop = np.repeat(np.arange(len(mesh.polygons)), loop_total)
    else:
        for index, (start, total) in enumerate(
            zip(loop_start.tolist(), loop_total.tolist(), strict=True)
        ):
            face_of_loop[start : start + total] = index
    loop_vertex = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", loop_vertex)
    verts = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", verts)
    verts = verts.reshape(-1, 3)
    k = nearest[face_of_loop]
    a, b, c = tri_p[k, 0], tri_p[k, 1], tri_p[k, 2]
    e1, e2, d = b - a, c - a, verts[loop_vertex] - a
    a11, a12, a22 = (e1 * e1).sum(1), (e1 * e2).sum(1), (e2 * e2).sum(1)
    b1, b2 = (d * e1).sum(1), (d * e2).sum(1)
    det = a11 * a22 - a12 * a12
    det = np.where(np.abs(det) < 1e-18, 1e-18, det)
    u = (b1 * a22 - b2 * a12) / det
    v = (a11 * b2 - a12 * b1) / det
    w = 1.0 - u - v
    uv = w[:, None] * tri_uv[k, 0] + u[:, None] * tri_uv[k, 1] + v[:, None] * tri_uv[k, 2]
    layer = mesh.uv_layers.active or mesh.uv_layers.new(name="UVMap")
    layer.data.foreach_set("uv", uv.ravel())
    mesh.update()


def uv_stretch(obj) -> dict | None:
    """Area share of faces whose texel density is 3x off the median either way (r9).

    The voxel route hands a rebuilt surface the scan's UVs corner by corner, and a face that
    straddles one of the scan's UV islands gets a stretched patch.  This is the size of that
    cost, per detail, in the build manifest -- so it is a number and not an impression.
    """
    import numpy as np

    mesh = obj.data
    uv_layer = mesh.uv_layers.active
    if uv_layer is None or not len(mesh.polygons):
        return None
    mesh.calc_loop_triangles()
    corners = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get("loops", corners)
    corners = corners.reshape(-1, 3)
    uvs = np.empty(len(uv_layer.data) * 2, dtype=np.float64)
    uv_layer.data.foreach_get("uv", uvs)
    uvs = uvs.reshape(-1, 2)
    vertex_of = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", vertex_of)
    verts = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", verts)
    verts = verts.reshape(-1, 3)
    p = verts[vertex_of[corners]]
    world = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    t = uvs[corners]
    texel = 0.5 * np.abs(
        (t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1])
        - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1])
    )
    real = world > 1e-9
    if not real.any():
        return None
    density = np.zeros_like(world)
    density[real] = texel[real] / world[real]
    median = float(np.median(density[real])) or 1e-12
    off = real & ((density > 3.0 * median) | (density < median / 3.0))
    return {
        "share_off_3x": round(float(world[off].sum() / world[real].sum()), 4),
        "median_uv_per_m2": round(median, 6),
    }


def solid_colmesh_of(obj, name: str, budget: int, parent) -> tuple:
    """A decimated copy of the visual as the collider (r9), or the convex hull if it opens.

    The hull was the phantom wall: a concave rock's collider stood 0.2-0.5 m proud of its
    surface on every boulder and 1.5-1.8 m on the cliffs.  A decimated copy of the finest
    detail follows the visual to the collapse error.  Returns ``(object, info)``.
    """
    bpy = _bpy()
    copy = duplicate(obj, name, parent)
    decimate_to(copy, budget)
    info = ensure_solid(copy, budget)
    info["kind"] = "decimated_solid"
    if not info["solid"]:
        bpy.data.objects.remove(copy, do_unlink=True)
        copy = convex_hull_of(obj, name, budget, parent)
        info = dict(solidity(copy), kind="convex_hull_fallback", solid=True)
    return copy, info


def boundary_edges(obj) -> tuple[int, float]:
    """(edges used by exactly one face, their total length in metres).

    A photogrammetry scan of a cliff FACE is an open shell.  Stood 10.8 m from a 21 m one --
    which is where design §8's crest eye stands -- you look THROUGH it and its back faces
    silhouette against the sky as long tan ribbons.  That is the r2 crest frame: measured
    here as 535 boundary edges and 90.6 m of open perimeter on `f_cliff_outcrop_a`'s top LOD.
    """
    import collections

    counts: collections.Counter = collections.Counter()
    mesh = obj.data
    for polygon in mesh.polygons:
        keys = list(polygon.vertices)
        for i in range(len(keys)):
            a, b = keys[i], keys[(i + 1) % len(keys)]
            counts[(a, b) if a <= b else (b, a)] += 1
    open_edges = [e for e, n in counts.items() if n == 1]
    verts = mesh.vertices
    length = 0.0
    for a, b in open_edges:
        pa, pb = verts[a].co, verts[b].co
        length += math.dist((pa[0], pa[1], pa[2]), (pb[0], pb[1], pb[2]))
    return len(open_edges), length


#: A cap face's edge, as a fraction of the shape's own longest dimension, and the ceiling on
#: the resulting face area in square metres.  MEASURED (r4, `b3/r4/probe_cap*.py`): a 21 m
#: `rock_face_01` wants 0.15 m2 cap faces -- its top LOD then carries 0.9 % of its area in
#: faces over 1 m2 and a largest face of 1.33 m2, where r3's flat fan left 40.2 % and
#: 106.15 m2 -- while a 6.2 m `root_cluster` wants 0.03 m2, because the same absolute grain
#: that is fine on a cliff is a slab between two roots.  Scaling the cap's grain to the shape
#: gets both: 60.3x -> 20x on the root cluster with the cliff unchanged.
CAP_FACE_EDGE_FRACTION = 0.0276
CAP_FACE_AREA_M2 = 0.15
CAP_FACE_AREA_MIN_M2 = 0.01
#: Relief displaced onto the cap, as a multiple of the cap triangle's own edge length -- NOT
#: of the shape's span.  The point is that every cap triangle sits on a bump its own size, so
#: collapse decimation cannot flatten the cap back into a plate: `f_crag`'s largest face
#: stays 6.47 m2 through a 153,472 -> 5,910 decimation.
CAP_RELIEF_EDGE = 0.40
#: ...at this many noise periods per cap edge, and this many passes of 1 -> 4 subdivision.
CAP_RELIEF_FREQUENCY = 1.2
CAP_SUBDIVIDE_PASSES = 9


def close_shell(obj) -> int:
    """Cap every boundary with geometry that reads as ROCK, and return the triangle count.

    r3 capped with ``fill_holes(sides=0)``, which hangs ONE n-gon fan on each boundary loop.
    It closed the shell and it was measurably wrong: `f_cliff_outcrop_a`'s largest triangle
    went 1.22 -> 106.15 m2, its surface 504 -> 907 m2 with 40.2 % of that in faces over 1 m2,
    and from the crest eye 39.9 % of the near rock the player sees was flat smeared cap.  The
    open perimeter was paid for with a plate.

    So the cap is built as rock instead, in three steps:

    1. the SAME ``bpy.ops.mesh.fill_holes`` r3 used -- see the determinism note below -- with
       the cap faces identified afterwards by their vertex keys rather than by a bmesh handle;
    2. subdivide the cap until no cap face is larger than the shape's own grain, ``(span x
       CAP_FACE_EDGE_FRACTION)**2`` clamped, so a 21 m cliff gets 0.15 m2 faces and a 6.2 m
       root tangle 0.029 m2;
    3. displace every interior cap vertex onto fractal noise at ``CAP_RELIEF_EDGE`` of the cap
       triangle's own edge.  This is the part that survives: a flat cap decimates straight
       back into a plate, a displaced one cannot collapse without changing shape.  MEASURED,
       `f_cliff_outcrop_a`'s top LOD goes from a 106.15 m2 largest face (3,092x its own
       median) to 1.33 m2 (17x), and the crest frame from 39.9 % of its near rock in faces
       over 1 m2 to 5.1 % against r2's 4.2 %.

    Finally the cap is given the ROCK's own texel density by planar projection instead of
    inheriting the boundary's stretched UVs.

    DETERMINISM.  A first cut of this did the whole thing in ``bmesh``, and the A/B leg caught
    it: six rocks came out with different bytes in two processes.  Sorting every set that
    reaches a bmesh op did not fix it -- ``bmesh.ops.remove_doubles``/``holes_fill`` are
    themselves unstable across processes here, where the ``bpy.ops.mesh`` operators r3 used
    are not (63/63 DAEs reproduced for three rounds).  So the mesh edits stay on the operator
    path and everything this function decides is plain Python over vertex INDICES.
    ``mathutils.noise.fractal`` is a pure function of the position.
    """
    bpy = _bpy()

    def _edit(operation) -> None:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        operation()
        bpy.ops.object.mode_set(mode="OBJECT")

    def _all(*ops) -> None:
        def run() -> None:
            for op in ops:
                bpy.ops.mesh.select_all(action="SELECT")
                op()

        _edit(run)

    mesh = obj.data
    _all(lambda: bpy.ops.mesh.remove_doubles(threshold=1e-5))
    triangulate(obj)
    ring = {v for edge in _open_edge_keys(mesh) for v in edge}
    before = {tuple(sorted(polygon.vertices)) for polygon in mesh.polygons}
    _all(lambda: bpy.ops.mesh.fill_holes(sides=0))
    if _open_edge_keys(mesh):
        # `fill_holes` refuses a boundary that runs through a non-manifold junction, which is
        # most of a raw photogrammetry scan: `f_crag` sits at 1,028 open edges and
        # `f_mossy_rock_b` at 262 however many times it runs.  `mesh.fill` triangulates an
        # arbitrary edge NET rather than a loop, and MEASURED it takes crag to 0.23 m of open
        # perimeter and mossy_rock_b to 0.10 -- without the Solidify rim r3 needed for them,
        # which doubles the surface and is what put 50.5 % of the crag into faces over 1 m2.

        def _fill_the_rest() -> None:
            bpy.ops.mesh.select_all(action="DESELECT")
            bpy.ops.mesh.select_mode(type="EDGE")
            bpy.ops.mesh.select_non_manifold(
                extend=False,
                use_wire=False,
                use_boundary=True,
                use_multi_face=False,
                use_non_contiguous=False,
                use_verts=False,
            )
            bpy.ops.mesh.fill(use_beauty=True)

        _edit(_fill_the_rest)
    _all(
        lambda: bpy.ops.mesh.quads_convert_to_tris(quad_method="BEAUTY", ngon_method="BEAUTY"),
        lambda: bpy.ops.mesh.normals_make_consistent(inside=False),
    )
    caps = {
        polygon.index for polygon in mesh.polygons if tuple(sorted(polygon.vertices)) not in before
    }
    if not caps:
        return len(mesh.polygons)
    span = max(obj.dimensions) or 1.0
    grain = (span * CAP_FACE_EDGE_FRACTION) ** 2
    cap_area = min(CAP_FACE_AREA_M2, max(CAP_FACE_AREA_MIN_M2, grain))
    _tessellate_cap(obj, caps, ring, cap_area)
    _all(lambda: bpy.ops.mesh.normals_make_consistent(inside=False))
    return len(mesh.polygons)


def _tessellate_cap(obj, caps: set[int], ring: set[int], cap_area: float) -> None:
    """Subdivide the cap to `cap_area`, displace it onto noise, and re-project its UVs.

    The FILL stays on the operator path (see `close_shell`); this part is bmesh because the
    operator `mesh.subdivide` re-enters edit mode per pass and is minutes slower on a
    225,000-triangle scan.  Everything that reaches a bmesh op here is sorted by INDEX and the
    displacement snapshots every normal before it moves anything, so the result is a pure
    function of the input mesh -- proven by the A/B leg, 270/270.
    """
    bmesh = _bmesh()
    from mathutils import Vector
    from mathutils import noise as bnoise

    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bm.edges.index_update()
    bm.verts.index_update()
    tag = bm.faces.layers.float.get("captag") or bm.faces.layers.float.new("captag")
    for face in bm.faces:
        face[tag] = 1.0 if face.index in caps else 0.0
    for _ in range(CAP_SUBDIVIDE_PASSES):
        big = [f for f in bm.faces if f[tag] > 0.5 and f.calc_area() > cap_area]
        if not big:
            break
        edges = sorted({e for f in big for e in f.edges}, key=lambda e: e.index)
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True)
        bm.faces.ensure_lookup_table()
        bm.edges.index_update()
        bm.verts.index_update()
    cap_faces = [f for f in bm.faces if f[tag] > 0.5]
    edge = 1.52 * math.sqrt(cap_area)
    amplitude, frequency = CAP_RELIEF_EDGE * edge, CAP_RELIEF_FREQUENCY / edge
    inner = sorted(
        {v for f in cap_faces for v in f.verts if v.index not in ring}, key=lambda v: v.index
    )
    frozen = [(v, v.co.copy(), v.normal.copy()) for v in inner]
    for vertex, point, normal in frozen:
        if normal.length < 1e-6:
            continue
        sample = Vector((point.x * frequency, point.y * frequency, point.z * frequency))
        vertex.co = point + normal * (amplitude * (bnoise.fractal(sample, 0.55, 2.1, 4) - 0.3))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is not None:
        density = []
        for face in [f for f in bm.faces if f[tag] <= 0.5][:4000]:
            world = face.calc_area()
            if world <= 1e-9 or len(face.loops) < 3:
                continue
            a, b, c = (loop[uv_layer].uv for loop in face.loops[:3])
            texel = abs((b - a).cross(c - a)) * 0.5
            if texel > 0:
                density.append(texel / world)
        scale = math.sqrt(sorted(density)[len(density) // 2]) if density else 1.0
        for face in cap_faces:
            axis = max(range(3), key=lambda i: abs(face.normal[i]))
            u_axis, v_axis = [i for i in range(3) if i != axis]
            for loop in face.loops:
                point = loop.vert.co
                loop[uv_layer].uv = (point[u_axis] * scale, point[v_axis] * scale)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    triangulate(obj)


def _open_edge_keys(mesh) -> list[tuple[int, int]]:
    """Every edge used by exactly one face, as a sorted (a, b) vertex-index pair."""
    import collections

    counts: collections.Counter = collections.Counter()
    for polygon in mesh.polygons:
        keys = list(polygon.vertices)
        for i in range(len(keys)):
            a, b = keys[i], keys[(i + 1) % len(keys)]
            counts[(a, b) if a <= b else (b, a)] += 1
    return [edge for edge, n in sorted(counts.items()) if n == 1]


def seal_shell(obj) -> int:
    """Close the mesh: cap the boundaries, and SOLIDIFY whatever the cap could not reach.

    r3 needed the Solidify rim often, because ``fill_holes`` alone refuses a boundary that
    runs through a non-manifold junction: ``f_crag`` sat at 1,028 open edges and
    ``f_mossy_rock_b`` at 262 however many times the cap ran.  r4's ``close_shell`` adds the
    ``triangle_fill`` fallback for exactly those, and MEASURED it takes crag to 2 edges /
    0.23 m and mossy_rock_b to 2 / 0.10 m on its own -- so the rim now fires on almost
    nothing.  That matters because Solidify is not free: it DOUBLES the surface, and the
    crag's 2,800 m2 became 5,156 m2 in r3, which at a 5,910-triangle budget is what put
    50.5 % of that shape's area into faces over 1 m2.

    The rim is kept as the last resort, at 0.4 % of the shape's own span with ``offset = 1``
    so the new surface goes INSIDE and the silhouette a player sees does not move.

    (``edge_face_add`` was tried and rejected: it bridges separate loops with one n-gon, which
    triangulates into exactly the long thin slivers this whole change exists to remove --
    ``f_cliff_outcrop_a`` went from 1.85 m of open perimeter to 54.58 m under it.)
    """
    bpy = _bpy()
    close_shell(obj)
    count, length = boundary_edges(obj)
    span = max(obj.dimensions) or 1.0
    # Solidify is a LAST RESORT, not the default.  It doubles the surface, and on a shell the
    # cap already closed it buys nothing while leaving a second wall a few centimetres inside
    # the first -- which reads as splintered plates the moment anything renders both sides.
    # `f_cliff_outcrop_a` needs nothing here: the cap alone takes it from 535 boundary edges
    # and 90.6 m of open perimeter to 39 edges and 1.85 m on a 21 m span.  `f_crag` (1,028
    # edges, 195.9 m) and `f_mossy_rock_b` (262, 22.8 m) do not move under the cap at all,
    # because their boundaries run through non-manifold junctions, and those are the two the
    # rim is for.
    if count == 0 or length / span <= SOLIDIFY_TRIGGER:
        return len(obj.data.polygons)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new(name="solidify", type="SOLIDIFY")
    modifier.thickness = span * SOLIDIFY_FRACTION
    modifier.offset = 1.0
    modifier.use_even_offset = False
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.quads_convert_to_tris(quad_method="BEAUTY", ngon_method="BEAUTY")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    return len(obj.data.polygons)


#: Solidify thickness as a fraction of the shape's longest dimension (0.16 m on a 41 m crag).
SOLIDIFY_FRACTION = 0.004
#: ...and it only runs when the cap left more open perimeter than this, as a multiple of the
#: shape's own span.  Same number as the gate in tests/test_hot_potato_forest.py.
SOLIDIFY_TRIGGER = 0.5


#: r5 (critic r4 B3).  A cap survives only if its relief is coarser than the grain the detail
#: SHIPS at, and `seal_to` decimates the mesh AGAIN after capping it.  MEASURED on the r4 cut:
#: `mesh.fill` closed `f_crag`'s open back with a 35 x 7 x 21 m membrane, `_tessellate_cap`
#: displaced it at the cap's own 0.59 m grain, and the second decimation pass collapsed it
#: straight back into one plane -- 340.1 m2 of `_a150` and 136.4 m2 of the top LOD in a single
#: plane against r2's 32.2 and 10.9, in 142 sliver triangles.  The r4 plate gate could not see
#: it: a FAN of slivers has small faces, and it scored 11.6x largest-over-median and 0.0 % of
#: the area above 16x the median.  So the relief is applied ONE more time, after the last
#: decimation, where nothing can flatten it again.  Plane: normal within this angle and centre
#: within this offset -- the same measure `test_no_shipped_model_detail_is_capped_with_a_plate`
#: now uses, so the build and the gate look at the same thing.
FLAT_PLANE_TOLERANCE_DEG = 4.0
FLAT_PLANE_TOLERANCE_M = 0.25
#: A plane this big, in absolute square metres or as a share of the detail's own surface, is a
#: cap and not rock.  MEASURED over all 77 model details in three cuts -- and the worst plane
#: AREA and the worst plane SHARE are DIFFERENT DETAILS in each, so these are two readings and
#: not one shape's (CORRECTED IN r7, critic r6 M34; b3/r5/planes.json):
#:     r2, the last tree built with no cap at all: area 32.2 m2 (f_crag _a150),
#:         share 22.5 % (f_pebble_cluster _a150)
#:     r3, flat n-gon fans:  area 120.8 m2 (f_cliff_outcrop_a _a100), share 37.1 % (f_stump_a _a400)
#:     r4, the `mesh.fill` membrane: area 340.1 m2 (f_crag _a150),
#:         share 30.2 % (f_windthrow_roots _a200)
#: The build triggers well under
#: the gate's ceilings (40 m2 / 30 %) so a shape has to move a long way before it can fail.
FLAT_PLANE_TRIGGER_M2 = 20.0
FLAT_PLANE_TRIGGER_SHARE = 0.10
#: ...and the relief put on it: this much of the plane's own triangle edge, capped at this
#: much of the shape's span so the silhouette cannot move, at this many periods per edge (a
#: wavelength of ~2.9 edges, so the bumps are resolvable AT the shipped grain -- 1.2 periods
#: per edge, `_tessellate_cap`'s number, aliases into noise at one vertex per period).
FLAT_PLANE_RELIEF_EDGE = 0.40
FLAT_PLANE_RELIEF_SPAN = 0.05
FLAT_PLANE_RELIEF_PERIODS = 0.85
FLAT_PLANE_PASSES = 16


def seal_to(obj, budget: int) -> int:
    """Decimate to ``budget`` AND leave the result closed, both at once.

    A cap does not survive decimation on its own.  ``decimate_to``'s escape hatch for a
    photogrammetry mesh that stalls above its budget is a progressive WELD -- up to 25 % of
    the model's own span -- and welding vertices that far apart tears a closed shell open
    again: ``f_mossy_rock_b``'s 200 px detail came out of a first cut of this function with
    the same 154 boundary edges and 22.5 m of open perimeter it had before the cap, because
    the cap ran, blew the budget, and the re-decimation undid it.

    So the loop lowers the DECIMATION target instead, leaving the cap room to fit under the
    authored budget.  Budget first, closure second, and both usually.

    ``roughen_flat_planes`` then runs on whatever comes out (see ``build_species``).  It is not
    a second cap: it moves vertices and never changes topology, so the budget met here holds.
    """
    target = budget
    for _ in range(5):
        current = decimate_to(obj, target)
        if boundary_edges(obj)[0] == 0:
            return current
        sealed = seal_shell(obj)
        if sealed <= budget:
            return sealed
        target = max(8, int(target * 0.82))
    return decimate_to(obj, budget)


def roughen_flat_planes(obj) -> list[dict]:
    """Displace every plane over the trigger off its own plane, at the SHIPPED grain.

    The cap relief in ``_tessellate_cap`` is applied at the CAP's grain and then decimated
    away; this is applied to whatever came out of the last decimation, so it is the one that
    survives.  Every vertex of the plane moves, not only its interior -- the planes that matter
    are coarse (``f_crag``'s 150 px membrane is nine triangles and has one interior vertex), and
    moving a vertex shared with the rest of the shell tears nothing, because it is one mesh and
    both faces follow it.

    Two properties this function must have, both learned the hard way in r5:

    * **no accumulation.**  Every displacement is measured from the vertex's position and
      normal AT ENTRY, so a vertex caught by three passes ends up where the last pass puts it
      and not three amplitudes away.  A first cut displaced from the current position each
      pass and inflated ``f_windthrow_roots``'s 200 px surface by 21 %, which pushed the r4
      plate gate's own share-above-16x-median from 29.1 % to 33.6 % -- past its 30 % ceiling.
    * **bounded by the shape.**  ``amplitude`` is capped at ``FLAT_PLANE_RELIEF_SPAN`` of the
      span, so no silhouette moves more than that however coarse the plane is.

    Determinism, the same recipe the A/B leg proved 270/270 on: every list is ordered by
    vertex INDEX, every position and normal is snapshotted before anything moves, and the
    displacement is ``mathutils.noise.fractal`` -- a pure function of the position.

    Returns one row per plane it broke up, for the build manifest.
    """
    import numpy as np
    from mathutils import noise as bnoise

    mesh = obj.data
    span = max(obj.dimensions) or 1.0
    cosine = math.cos(math.radians(FLAT_PLANE_TOLERANCE_DEG))
    origin = [(v.co.copy(), v.normal.copy()) for v in mesh.vertices]
    broken: list[dict] = []
    for _ in range(FLAT_PLANE_PASSES):
        mesh.calc_loop_triangles()
        corners = np.array([list(t.vertices) for t in mesh.loop_triangles], dtype=np.int64)
        if not len(corners):
            return broken
        points = np.array([list(v.co) for v in mesh.vertices], dtype=np.float64)
        triangles = points[corners]
        raw = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        area = 0.5 * np.linalg.norm(raw, axis=1)
        unit = raw / np.maximum(np.linalg.norm(raw, axis=1, keepdims=True), 1e-12)
        centre = triangles.mean(axis=1)
        surface = float(area.sum()) or 1e-12
        best_area, best_mask = 0.0, None
        median = float(np.median(area)) or 1e-12
        seeds = [int(i) for i in np.argsort(-area, kind="stable")[:120] if area[i] > median]
        for seed in seeds:
            normal = unit[seed]
            mask = (np.abs(unit @ normal) > cosine) & (
                np.abs(centre @ normal - normal @ centre[seed]) < FLAT_PLANE_TOLERANCE_M
            )
            total = float(area[mask].sum())
            if total > best_area:
                best_area, best_mask = total, mask
        if best_mask is None or (
            best_area <= FLAT_PLANE_TRIGGER_M2 and best_area / surface <= FLAT_PLANE_TRIGGER_SHARE
        ):
            return broken
        moved = sorted(set(corners[best_mask].ravel().tolist()))
        edge = 1.52 * math.sqrt(max(float(area[best_mask].mean()), 1e-9))
        amplitude = min(FLAT_PLANE_RELIEF_EDGE * edge, FLAT_PLANE_RELIEF_SPAN * span)
        frequency = FLAT_PLANE_RELIEF_PERIODS / edge
        for index in moved:
            point, normal = origin[index]
            if normal.length < 1e-6:
                continue
            sample = point * frequency
            mesh.vertices[index].co = point + normal * (
                amplitude * (bnoise.fractal(sample, 0.55, 2.1, 4) - 0.3)
            )
        mesh.update()
        broken.append(
            {
                "plane_m2": round(best_area, 3),
                "share": round(best_area / surface, 4),
                "moved": len(moved),
                "amplitude_m": round(amplitude, 4),
            }
        )
    return broken


def triangulate(obj, weld: bool = False) -> int:
    """Triangulate (and optionally weld coincident vertices) and return the triangle count.

    The weld matters: a glTF mesh arrives with its corners SPLIT wherever a UV seam or a
    sharp normal runs, so collapse decimation has almost nothing it may collapse -- on
    ``boulder_01`` a ratio of 0.05 took 66,122 triangles to 26,611 (40 %), not to 3,306.
    Welding at 1e-5 m rejoins only genuinely coincident corners, and UVs survive because
    Blender stores them per LOOP, not per vertex.
    """
    bpy = _bpy()
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    if weld:
        bpy.ops.mesh.remove_doubles(threshold=1e-5)
        bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.quads_convert_to_tris(quad_method="BEAUTY", ngon_method="BEAUTY")
    bpy.ops.object.mode_set(mode="OBJECT")
    return len(obj.data.polygons)


def weld(obj, threshold: float) -> int:
    bpy = _bpy()
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=threshold)
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.quads_convert_to_tris(quad_method="BEAUTY", ngon_method="BEAUTY")
    bpy.ops.object.mode_set(mode="OBJECT")
    return len(obj.data.polygons)


def _collapse(obj, budget: int, current: int, attempt: int) -> int:
    bpy = _bpy()
    modifier = obj.modifiers.new(name=f"decimate{attempt}", type="DECIMATE")
    modifier.decimate_type = "COLLAPSE"
    modifier.use_collapse_triangulate = True
    modifier.ratio = max(0.0005, min(0.999, budget / current * (0.985 - 0.05 * min(attempt, 8))))
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    return triangulate(obj)


def decimate_to(obj, budget: int) -> int:
    """Collapse-decimate to the largest triangle count that does not exceed ``budget``.

    Collapse decimation has a floor: it will not collapse across a mesh boundary, so a
    photogrammetry model with many shells stalls (``fallen_log_b`` sat at 204 triangles for a
    budget of 180).  Past that floor the fix is to WELD progressively -- 0.2 % of the model's
    own span, doubling -- which merges the shells and lets the collapse continue.  At the
    lowest LOD (80 px, > 260 m away) a 1-2 cm weld on an 8 m log is invisible.
    """
    current = triangulate(obj, weld=True)
    attempt = 0
    while current > budget and attempt < 8:
        current = _collapse(obj, budget, current, attempt)
        attempt += 1
    span = max(obj.dimensions) or 1.0
    threshold = span * 0.002
    while current > budget and threshold < span * 0.25:
        current = weld(obj, threshold)
        if current > budget:
            current = _collapse(obj, budget, current, attempt)
            attempt += 1
        threshold *= 2.0
    if current > budget:
        raise SystemExit(f"{obj.name}: decimation stalled at {current} triangles, budget {budget}")
    return current


def rebind_material(obj, material) -> None:
    """One slot, index 0 on every polygon: the glTF's own materials never reach the DAE."""
    obj.data.materials.clear()
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.material_index = 0
    obj.data.update()


def purge_unused_materials(keep: set[str]) -> None:
    bpy = _bpy()
    for material in list(bpy.data.materials):
        if material.name not in keep:
            bpy.data.materials.remove(material, do_unlink=True)


def duplicate(obj, name: str, parent):
    bpy = _bpy()
    copy = obj.copy()
    copy.data = obj.data.copy()
    copy.name = name
    copy.data.name = name
    bpy.context.collection.objects.link(copy)
    copy.parent = parent
    return copy


def convex_hull_of(obj, name: str, budget: int, parent):
    bpy = _bpy()
    hull = duplicate(obj, name, parent)
    bpy.ops.object.select_all(action="DESELECT")
    hull.select_set(True)
    bpy.context.view_layer.objects.active = hull
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.convex_hull()
    bpy.ops.object.mode_set(mode="OBJECT")
    decimate_to(hull, budget)
    assert_positive_volume(hull, f"{name} (decimated convex hull)")
    return hull


def export_dae(
    nodes, path: Path, tree: dict[str, str | None], materials: set[str], bb: bool
) -> dict:
    bpy = _bpy()
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in nodes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = nodes[0]
    result = bpy.ops.wm.collada_export(
        filepath=str(path),
        check_existing=False,
        selected=True,
        include_children=True,
        include_animations=False,
        include_all_actions=False,
        apply_modifiers=True,
        triangulate=True,
        use_texture_copies=False,
        apply_global_orientation=True,
        export_global_forward_selection="Y",
        export_global_up_selection="Z",
        sort_by_name=True,
    )
    if "FINISHED" not in result:
        raise SystemExit(f"Collada export failed for {path.name}: {result}")
    bpy.ops.object.select_all(action="DESELECT")
    text = quantise_collada(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
    if quantise_collada(text) != text:
        raise SystemExit(f"{path.name}: collada normalisation is not idempotent")
    if bb:
        text = inject_bb_property(path.name, text)
    path.write_bytes(text.encode("utf-8"))
    actual = dae_node_parents(path)
    for name, parent in tree.items():
        if name not in actual:
            raise SystemExit(f"{path.name}: node {name} missing from the export")
        if actual[name] != parent:
            raise SystemExit(f"{path.name}: {name} under {actual[name]!r}, authored {parent!r}")
    extra = set(actual) - set(tree)
    if extra:
        raise SystemExit(f"{path.name}: unexpected nodes {sorted(extra)}")
    got = dae_material_names(path)
    if got != materials:
        raise SystemExit(f"{path.name}: materials {sorted(got)} != {sorted(materials)}")
    blob = path.read_bytes()
    if b"\r" in blob:
        raise SystemExit(f"{path.name}: CR byte in a release text member")
    if bb and fs.BB_PROPERTY.encode() not in blob:
        raise SystemExit(f"{path.name}: BB::DIM property did not survive the write")
    return {
        "file": path.name,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "size": len(blob),
        "node_tris": dae_detail_triangles(path),
        "materials": sorted(got),
    }


def inject_bb_property(label: str, text: str) -> str:
    """B0's proven mechanism: an OpenCOLLADA/Torque user_properties block on the bb node."""
    pattern = re.compile(
        r'(<node id="' + fs.BB_NODE + r'" name="' + fs.BB_NODE + r'"[^>]*>)(.*?)(</node>)', re.S
    )
    match = pattern.search(text)
    if match is None:
        raise SystemExit(f"{label}: no {fs.BB_NODE} node to annotate")
    extra = (
        "\n        <extra>"
        f'<technique profile="OpenCOLLADA">'
        f"<user_properties>{fs.BB_PROPERTY}</user_properties></technique>"
        f'<technique profile="Torque">'
        f"<user_properties>{fs.BB_PROPERTY}</user_properties></technique>"
        "</extra>\n      "
    )
    return text[: match.start(3)] + extra + text[match.start(3) :]


# ------------------------------------------------------------------------------- build loop
def build_species(species: dict, out_root: Path, cache: Path) -> dict:
    bpy = _bpy()
    clear_scene()
    stem = dae_stem(species["key"])
    slot_materials = [make_material(fs.material_name(key)) for _, key in species["materials"]]
    material_names = {m.name for m in slot_materials}
    base = empty(BASE_NODE)
    nodes = [base]
    if species["bb"]:
        nodes.append(empty(fs.BB_NODE, base))
    nodes.append(empty(f"nulldetail{species['null']}", base))
    start = empty(START_NODE, base)
    nodes.append(start)
    expected_tris: dict[str, int] = {}

    open_shell: dict[str, list[float]] = {}
    planes_broken: dict[str, list[dict]] = {}
    solid: dict[str, dict] = {}
    colmesh_info: dict | None = None
    if species["build"] in ("conifer", "snag", "card"):
        grid = next(
            (m["grid"] for m in fs.MATERIALS if m["key"] == species["materials"][-1][1]), (4, 4)
        )
        card_scales = fs.lod_card_scale(species)
        for index, (pixel, budget) in enumerate(species["details"]):
            # a seeded geometry jitter, never a security draw
            detail_rng = random.Random(f"{fs.SHAPE_SEED}:{species['key']}:{pixel}")  # noqa: S311
            scale = card_scales[index] if card_scales else 1.0
            if species["build"] == "conifer":
                layout = dict(fs.conifer_layout(species)[index], index=index)
                mesh = conifer_mesh(species, layout, grid, detail_rng, scale)
            elif species["build"] == "snag":
                mesh = snag_mesh(species, fs.snag_layout(species)[index][1], detail_rng)
            else:
                stems = fs.stem_layout(species)
                mesh = card_cluster_mesh(
                    species,
                    fs.card_layout(species)[index][1],
                    grid,
                    detail_rng,
                    scale,
                    stem_rings=stems[index][1] if stems else 0,
                )
            if mesh.tris != budget:
                raise SystemExit(f"{stem} detail {pixel}: {mesh.tris} tris, budget {budget}")
            name = detail_node(stem, pixel)
            object_from_mesh(name, mesh, slot_materials, start)
            expected_tris[name] = budget
        if species["colmesh"]:
            mesh = colmesh_tube_mesh(species)
            if mesh.tris != species["colmesh"]:
                raise SystemExit(f"{stem} Colmesh: {mesh.tris} tris, budget {species['colmesh']}")
            object_from_mesh(colmesh_node(stem), mesh, slot_materials[:1], start)
            expected_tris[colmesh_node(stem)] = species["colmesh"]
    else:
        asset, part, mirror = species["source"]
        source = import_model(
            cache,
            asset,
            part,
            mirror,
            species["height_m"],
            solid=species.get("solid"),
            seed=zlib.crc32(f"{fs.SHAPE_SEED}:{species['key']}".encode()),
            solid_shells=species.get("solid_shells"),
            skirt_rows=species.get("skirt_rows"),
            body_depth=species.get("body_depth"),
        )
        if species.get("lie_down"):
            bpy.ops.object.select_all(action="DESELECT")
            source.select_set(True)
            bpy.context.view_layer.objects.active = source
            source.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            low = min(v.co[2] for v in source.data.vertices)
            for vertex in source.data.vertices:
                vertex.co[2] -= low
            source.data.update()
        for pixel, budget in species["details"]:
            copy = duplicate(source, detail_node(stem, pixel), start)
            seal_to(copy, budget)
            planes_broken[detail_node(stem, pixel)] = roughen_flat_planes(copy)
            # r9: outward, closed, and SAID so per detail (the gate re-reads the file)
            solid[detail_node(stem, pixel)] = ensure_solid(copy, budget)
            solid[detail_node(stem, pixel)]["uv_stretch"] = uv_stretch(copy)
            expected_tris[detail_node(stem, pixel)] = len(copy.data.polygons)
            count, length = boundary_edges(copy)
            open_shell[detail_node(stem, pixel)] = [count, round(length, 4)]
            rebind_material(copy, slot_materials[0])
        if species["colmesh"]:
            finest = bpy.data.objects[detail_node(stem, species["details"][0][0])]
            hull, colmesh_info = solid_colmesh_of(
                finest, colmesh_node(stem), species["colmesh"], start
            )
            rebind_material(hull, slot_materials[0])
            expected_tris[colmesh_node(stem)] = len(hull.data.polygons)
        bpy.data.objects.remove(source, do_unlink=True)
        purge_unused_materials(material_names)

    nodes.extend(bpy.data.objects[name] for name in expected_tris)
    tree = expected_tree(
        stem,
        tuple(p for p, _ in species["details"]),
        bb=species["bb"],
        null=species["null"],
        colmesh=bool(species["colmesh"]),
    )
    info = export_dae(
        nodes, out_root / fs.species_dae_relative(species), tree, material_names, species["bb"]
    )
    for name, budget in expected_tris.items():
        if info["node_tris"].get(name) != budget:
            raise SystemExit(
                f"{stem}: {name} exported {info['node_tris'].get(name)} tris, built {budget}"
            )
    info.update(
        {
            "key": species["key"],
            "relative": fs.species_dae_relative(species),
            "details": {str(p): expected_tris[detail_node(stem, p)] for p, _ in species["details"]},
            "budgets": {str(p): b for p, b in species["details"]},
            "colmesh_tris": expected_tris.get(colmesh_node(stem), 0),
            # The Colmesh's OWN extent, so the live ray census can put a tight analytic window
            # on a decimated hull instead of `height_m * 1.05` -- `fallen_log_a` is a 10.7 m
            # LOG lying down whose collider is about a metre tall, and a [0.02, 13.12] window
            # over it could not fail.
            "colmesh_bbox": _bbox(bpy.data.objects.get(colmesh_node(stem)))
            if species["colmesh"]
            else None,
            "shape_bbox": _bbox(bpy.data.objects.get(detail_node(stem, species["details"][0][0]))),
            # r3 (D7): what is left open after the cap, per detail: [edges, metres].  The
            # gate reads this and the shipped DAEs both.
            "open_shell": open_shell,
            # r5 (critic r4 B3): every plane `roughen_flat_planes` broke up, per detail,
            # with its area and the amplitude it was displaced by.  The plate gate
            # re-measures the shipped DAE; this is the build's own account of what it did.
            "planes_broken": planes_broken,
            # r9: per detail, the build's own volume / boundary / non-manifold reading, and
            # what the Colmesh is (a decimated solid, or the hull it fell back to)
            "solid": solid,
            "colmesh_kind": colmesh_info,
            # r9: how the scan became a body (voxel closing used, chi, shells; or the face
            # solid's grid, depth and skirt rows)
            "import_solid": dict(IMPORT_REPORT) if species["build"] == "model" else None,
            # r10: which piece of a multi-rock scan `part` chose, and by which decomposition
            "import_part": dict(PART_REPORT) if species["build"] == "model" else None,
            "bb_dim": fs.BB_DIM if species["bb"] else None,
            "nulldetail": species["null"],
            "height_m": species["height_m"],
        }
    )
    return info


def _bbox(obj) -> dict | None:
    """Axis-aligned extent of one Blender object, five decimals (quantised like the DAE)."""
    if obj is None or not getattr(obj, "data", None) or not len(obj.data.vertices):
        return None
    xs = [v.co[0] for v in obj.data.vertices]
    ys = [v.co[1] for v in obj.data.vertices]
    zs = [v.co[2] for v in obj.data.vertices]
    return {
        "min": [round(min(xs), 5), round(min(ys), 5), round(min(zs), 5)],
        "max": [round(max(xs), 5), round(max(ys), 5), round(max(zs), 5)],
    }


def build_cover(cover: dict, out_root: Path, cache: Path) -> dict:
    bpy = _bpy()
    clear_scene()
    stem = dae_stem(cover["key"], cover=True)
    material = make_material(fs.material_name(cover["material"]))
    base = empty(BASE_NODE)
    nodes = [base, empty(f"nulldetail{cover['null']}", base)]
    start = empty(START_NODE, base)
    nodes.append(start)
    rng = random.Random(f"{fs.SHAPE_SEED}:cover:{cover['key']}")  # noqa: S311 - seeded jitter
    expected: dict[str, int] = {}
    detail_name = detail_node(stem, cover["detail_px"])
    if "source" in cover:
        asset, part, mirror = cover["source"]
        source = import_model(cache, asset, part, mirror, 1.0)
        source.name = detail_name
        source.data.name = detail_name
        source.parent = start
        expected[detail_name] = decimate_to(source, cover["tris"])
        rebind_material(source, material)
        hull = convex_hull_of(source, colmesh_node(stem), cover["colmesh"], start)
        rebind_material(hull, material)
        expected[colmesh_node(stem)] = len(hull.data.polygons)
        purge_unused_materials({material.name})
    else:
        mesh = cover_mesh(cover, rng)
        if mesh.tris != cover["tris"]:
            raise SystemExit(f"{stem}: {mesh.tris} tris, budget {cover['tris']}")
        object_from_mesh(detail_name, mesh, [material], start)
        expected[detail_name] = cover["tris"]
        hull_mesh = cover_colmesh_mesh(cover)
        object_from_mesh(colmesh_node(stem), hull_mesh, [material], start)
        expected[colmesh_node(stem)] = hull_mesh.tris
    nodes.extend(bpy.data.objects[name] for name in expected)
    tree = expected_tree(stem, (cover["detail_px"],), bb=False, null=cover["null"], colmesh=True)
    info = export_dae(nodes, out_root / f"{fs.COVER_DIR}/{stem}.dae", tree, {material.name}, False)
    info.update(
        {
            "key": cover["key"],
            "relative": f"{fs.COVER_DIR}/{stem}.dae",
            "details": {str(cover["detail_px"]): expected[detail_name]},
            "budgets": {str(cover["detail_px"]): cover["tris"]},
            "colmesh_tris": expected[colmesh_node(stem)],
            "bb_dim": None,
            "nulldetail": cover["null"],
        }
    )
    return info


def build(out_root: Path, cache: Path, only: set[str] | None = None) -> dict:
    bpy = _bpy()
    started = time.time()
    manifest = {
        "level_id": fs.LEVEL_ID,
        "blender": bpy.app.version_string,
        "collada_decimals": COLLADA_DECIMALS,
        "bb_dim": fs.BB_DIM,
        "shape_seed": fs.SHAPE_SEED,
        "species": {},
        "covers": {},
    }
    for species in fs.SPECIES:
        if only and species["key"] not in only:
            continue
        print(f"[forest] species {species['key']}", flush=True)
        manifest["species"][species["key"]] = build_species(species, out_root, cache)
    for cover in fs.COVER_SHAPES:
        if only and cover["key"] not in only:
            continue
        print(f"[forest] cover   {cover['key']}", flush=True)
        manifest["covers"][cover["key"]] = build_cover(cover, out_root, cache)
    manifest["seconds"] = round(time.time() - started, 1)
    manifest["dae_count"] = len(manifest["species"]) + len(manifest["covers"])
    return manifest


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="the level root in mod/levels/")
    parser.add_argument("--cache", type=Path, required=True, help="cc0_cache/")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--only", default=None, help="comma-separated species/cover keys")
    arguments = parser.parse_args(argv)
    only = set(arguments.only.split(",")) if arguments.only else None
    manifest = build(arguments.out, arguments.cache, only)
    text = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    arguments.manifest.parent.mkdir(parents=True, exist_ok=True)
    arguments.manifest.write_text(text, encoding="utf-8", newline="\n")
    print(
        f"[forest] {manifest['dae_count']} DAEs in {manifest['seconds']}s -> {arguments.manifest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
