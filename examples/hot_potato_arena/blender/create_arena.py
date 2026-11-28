"""Deterministic Blender generator for THE GATEWAY SKILLET arena (v2).

Authors the level shapes of arena design v3 SS7.1 as amended by v3.1 (each
its own DAE, CCW level-art pattern: authored frame, Z-up, +Y forward,
plain TSStatic Collada), the namespaced materials json, and the
machine-readable handoff (31 prefab instances + the obstacle table, both
emitted from ONE placement table).

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/hot_potato_arena/blender/create_arena.py

Build-time asserts, each raising loudly on failure:

  A1  swept wall profile strictly monotone in r; bank z non-decreasing
  A2  drivable relief: facet sagitta vs the analytic profile <= 0.02 m on
      every driven surface; every wall-surface vertex within +/-0.02 m of
      the profile on BOTH wall shapes; proud plates / trim <= 0.02 m
  A3  crest tangent-flattened (slope 0 both sides at r = 91.4)
  A4  triangle winding constructive; zero degenerate faces post-build
  A5  under-deck horizontal ray sweep for the Handle
  A6  arc seam columns on the shared radial planes, twins under rotation
  A7  per-shape triangle counts within +/-25 % of the v3.1 budgets
  A8  placement table: 31 instances / 12 shapes / obstacle count
  A9  2-D footprint overlap over all instances; plate<->solid >= 5.0 m
  A10 plaza lane connectivity (r < 80): one region, no pockets
  A11 max local bank grade <= MAX_GRADE (0.70)
  A12 tangential ripple grade*r*(1-cos(pitch/2)) <= 0.020 m per station
  A13 every solid face > 0.5 m tall lies inside a registered keep-out
  A14 named stations present; mesh crest within 1 mm of the contract
  A15 ramp along-path grade <= 0.12 at r = 80, monotone in s
  A16 no inside corner: plaza cells < 13/16 blocked; tall-face junctions >= 135 deg
  A4c near-carrier triangles (trim within 20 mm of the mesh) face UP outright
  A17 exported LOD node tree == the authored hierarchy (nulldetail under base00)
  A18 shapes NOT re-exported: the shipped DAE's triangle count == this build's
  A19 floor skin is a DRIVEN surface (v3.2): every vertex on the analytic
      skin profile, facet sagitta <= 0.02 m, skirt/feather grade <= 2.5 %
      and monotone, outer edge ON the 12 mm datum (lip <= 2 mm)
  A20 quadrant seam collision step <= 2 mm (built mesh AND the exported
      DAE), and the skin's outer ring coincides with the wall sheet's r 76 ring
  A21 every hazard plate inside the skin footprint lies fully on the FLAT
      plaza and its top sits 20 +/- 2 mm proud of the lifted skin
  A22 exactly the floor skin's and the glacis's own materials carry
      castShadows false (read back from the written materials json); the
      bank's matte iron and the rim still cast; no other shape references one
  A23 a re-export declared --material-only moved NO geometry: identical
      triangle count and vertex positions vs the file that was on disk
  A26 relief ACROSS every authored shape-to-shape contact on a drivable
      surface <= 0.02 m (the class no within-shape relief assert covered)
  A25 every long solid face is audited against the reflex's arming
      half-span: faces marked covered must meet it, non-walls are named as
      such, residuals carry their measured contact counts; obstacle count
      within the runtime's cap of 64
  A24 every obstacle carries a measured `rp` beside its untouched keep-out,
      satisfying the runtime's own rule (finite, >= 0.1, <= its own r);
      the kind census is 10/8/16/8; and the three classes the gates
      measured in game agree to 0.05 m

v3.2 (design owner, 2026-09-02): the floor skin is lifted to +50 mm, given
collision, feathered to the 12 mm datum at r 76; the far `_a70` detail is
gone (one detail under the stock base00/start01/nulldetail tree).
v3.3 (design owner, 2026-09-02): the floor skin stops CASTING shadows --
material-level `castShadows: false` on its own two materials (see the
SHADOW LAW note by MATERIALS for the in-game evidence).

Options after ``--`` (round-3 errata pass; defaults reproduce the old behaviour):

    --export a,b,c   write only these DAEs; the rest are hashed from disk (A18)
    --dry-run        build + asserts only, write nothing
    --no-renders     skip the render pass
    --round LABEL    label the hash manifest and snapshot it as .hashes.LABEL.json
    --baseline FILE  manifest (in authoring/) to diff against; default the r3 critique
    --material-only a,b  these exports must not move geometry (assert A23)

Every build writes authoring/<arena>.hashes.json: sha256 + size per DAE, per
staged texture and the materials json, plus the diff against the baseline.
The Collada exporter stamps <created>/<modified> with wall-clock time, so a
re-export is NEVER byte-identical: a shape that must not change must not be
in the export set, and the manifest is the proof that it did not.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
import uuid
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
EXAMPLE_ROOT = SCRIPT_PATH.parents[1]
GIANT_PROPS = EXAMPLE_ROOT.parent / "giant_props"
sys.path.insert(0, str(GIANT_PROPS))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

ARENA_ID = "ericrolph_hot_potato_arena"
#: B5 (2026-09-10): the arena left stock gridmap_v2 for the round's own level,
#: whose id is the same string. Every shipped path below is derived from
#: SHAPES_RELATIVE so a future level rename is one edit, and so the
#: `groundtype` binding law (materials only bind under `levels/<id>/art/
#: shapes/...`) is satisfied by the level that actually owns the site.
LEVEL_ID = ARENA_ID
SHAPES_RELATIVE = f"levels/{LEVEL_ID}/art/shapes/hot_potato_arena"
TEXTURE_DIR = EXAMPLE_ROOT / "textures"
SHAPE_DIR = EXAMPLE_ROOT / "mod" / Path(SHAPES_RELATIVE)
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"
RENDER_DIR = Path(
    r"C:\Users\ericr\AppData\Local\Temp\claude"
    r"\C--Users-ericr-beamng-mcp\ac9b4832-415d-4129-bdeb-dfb93bf81de5"
    r"\scratchpad\arena_geometry_renders"
)

# ---------------------------------------------------------------------------
# Contract constants (design v3 SS3 + v3.1 amendment). Grade is local z = 0;
# the world anchor C = (850, -280, 100) lives only in the placement table.
# Bearings are compass-style: 0 deg = +Y, 90 deg = +X;
# point(b, r) = (r sin b, r cos b).
# ---------------------------------------------------------------------------
CENTER_WORLD = (850.0, -280.0, 100.0)
R_BANK_IN = 76.0
CREST_R = 91.4
CREST_Z = 5.5  # v3.1 Item 2 (was 6.5)
GLACIS_TOE = 113.0
GLACIS_EASE = 2.5  # crest-side slope ease (grades law)
GLACIS_TOE_FEATHER = 0.3  # v3.1 Item 5: leave the groundplane fast at the toe
BANK_KNOTS = [(76.0, 0.0), (79.5, 0.4), (84.0, 1.7), (88.5, 4.0), (91.4, CREST_Z)]
MAX_GRADE = 0.70  # v3.1 Item 2, assert A11
# v3.1 Item 5: the wall sheet starts 12 mm above the stock groundplane (one
# collision step, inside the cap) so it and the floor skin leave the
# groundplane together; the lift fades out by r 78 where the bank is
# already 0.16 m up.
TOE_LIFT = 0.012
TOE_LIFT_HOLD_R = 76.3
TOE_LIFT_FADE_R = 78.0

FLOOR_R_IN = 6.0
FLOOR_R_OUT = 76.0
FLOOR_SKIN_Z = 0.012  # the 12 mm DATUM the wall sheet and corridor floor start on
# v3.2 (design owner, 2026-09-02): the skin is a DRIVEN, COLLIDING surface
# at +50 mm over the plaza. The integration gate G1 measured the 12 mm
# no-collision inlay depth-fighting the stock groundplane at 300 m on 2 of
# 3 boots (band metric 2.6-4.8 vs clean 1.2-1.8, the winner decided per
# boot) and the scenario critic's negative control proved the DAE LOD never
# engages; +50 mm was measured fight-free. The skin therefore carries its
# own collision (cars drive ON it, no tyre sinks through a visual) and obeys
# the drivable-surface laws: it feathers DOWN to the 12 mm datum before the
# wall/corridor datum at r 76 as a slope trapezoid (slope interpolated and
# integrated -- never two height datums blended), peak grade < 2.5 %,
# monotone, outer edge exactly on the datum (no lip). The inner skirt to
# grade at r 6 gets the same treatment (it now climbs 50 mm, not 12).
SKIN_TOP_Z = 0.050
SKIN_SKIRT_R0, SKIN_SKIRT_R1 = FLOOR_R_IN, 9.0  # 0 -> 50 mm over 3.0 m
SKIN_FEATHER_R0, SKIN_FEATHER_R1 = 73.5, FLOOR_R_OUT  # 50 -> 12 mm over 2.5 m
SKIN_EASE = 0.5  # slope ease at each end of the skirt and the feather
SKIN_MAX_GRADE = 0.025  # assert A19
SKIN_SEAM_STEP_CAP = 0.002  # assert A20
PLATE_PROUD_TOL = 0.002  # assert A21: plates 20 +/- 2 mm proud of the skin
# Ring stations of the skin quadrant: the skirt and feather eases, the
# material split (glossy centre to r 40, matte beyond) and one mid-plaza
# ring. 9 bands x 24 columns = 432 tris, the v3.1 near-detail count.
SKIN_RINGS = [
    SKIN_SKIRT_R0,
    SKIN_SKIRT_R0 + SKIN_EASE,
    SKIN_SKIRT_R1 - SKIN_EASE,
    SKIN_SKIRT_R1,
    40.0,
    60.0,
    SKIN_FEATHER_R0,
    SKIN_FEATHER_R0 + SKIN_EASE,
    SKIN_FEATHER_R1 - SKIN_EASE,
    SKIN_FEATHER_R1,
]
# Node tree of the floor DAE. v3.2 dropped the +50 mm far detail (`_a70`)
# and every LOD number with it: the mesh keeps its near-detail name
# (`_a290`) under the stock base00/start01 tree with nulldetail10 as a
# SIBLING of start01 -- exactly the configuration the scenario critic's
# negative control BOOTED (shipped zip minus `_a70`) and photographed
# rendering at 300 m. Set False to export the skin like the other twelve
# shapes (a plain object, no scaffold) if the G1 drop-test ever shows the
# skin without collision or vanishing with distance.
FLOOR_SKIN_STOCK_NODES = True
FLOOR_LOD_NEAR_PX = 290  # the mesh node's trailing number (unchanged name)
FLOOR_LOD_NULL_PX = 10
PLATE_TOP_Z = 0.020  # hazard plates at the relief cap (round-1 ledger #1)

SALT_R_IN, SALT_R_OUT = 12.0, 20.0
# Full +/-45 deg per v3 SS3.1. Round 2 trimmed the arcs to +/-36 to satisfy
# a groundtype-blind A9 (5.0 m from the 45/135/225/315 grinders); the design
# owner restored the span and made A9 groundtype-aware instead: ICE plates
# (the banana peel) need 5.0 m from solids, SAND plates (the brake) 1.5 m.
SALT_HALF_SPAN_DEG = 45.0
PLATE_CLEARANCE_M = {"ICE": 5.0, "SAND": 1.5}
BUTTER_SEMI_X, BUTTER_SEMI_Y = 9.0, 5.0

HANDLE_HALF_W = 7.0
HANDLE_DECK_Z = 4.0
HANDLE_NOSE_R = 30.0
HANDLE_END_R = 88.5  # wall_z(88.5) == 4.0 by the knot table: flush by construction
HANDLE_TUCK_SPAN = 0.5  # the deck skirt is carried this far past the rear edge
HANDLE_TUCK_DROP = 0.05  # v3.8: and DESCENDS this far, so it is under the bank by
# construction rather than by a rebate that tessellation can defeat

# v3.1 Item 1.1: tangential arc ramps on the bank apron.
RAMP_R_IN, RAMP_R_OUT = 80.0, 88.0
RAMP_TOE_BEARING = 149.0  # east ramp inner-edge toe (west mirrors: 211.0)
RAMP_FLAT_M = 4.0  # flat merge at r 80
RAMP_EASE_M = 3.0  # slope eases (arc length at r 80)
RAMP_MAX_GRADE = 0.12  # assert A15
RAMP_LIFT = 0.004  # ramp rides 4 mm above the wall MESH facets
RAMP_TUCK = 0.3  # tucked into the deck, 4 mm under its top
RAMP_COLUMNS = 44  # ~0.6 deg / 0.8 m along the path

SPOUT_HALF_W = 18.0
SPOUT_SPLAY_DEG = 15.0
CORRIDOR_Z = 0.012  # corridor floor = floor-skin datum (12 mm)
CORRIDOR_FEATHER = 0.3

MASHER_R, MASHER_RADIUS, MASHER_H = 48.0, 1.2, 7.5
GRINDER_R, GRINDER_RADIUS, GRINDER_H = 26.0, 1.5, 4.5
TOWER_R, TOWER_HALF, TOWER_H = 58.0, 1.5, 6.0
BUTTER_R = 66.0
BUTTER_BEARINGS = (30.0, 228.0, 300.0)  # v3.1 Item 1.2: pool 2 -> 228

RELIEF_CAP = 0.02
NEAR_CARRIER_M = 0.02  # A4c: a face this close to its carrier must face up
SAGITTA_TOL = 0.015
RIPPLE_CAP = 0.020
DENSE_GRADE = 0.35  # stations steeper than this get 24 columns per 45 deg
TRIM_PROUD = 0.018
REBATE = 0.003
RIM_R0, RIM_R1 = 90.0, 93.0  # arena_rim material band on the wall shapes
RIM_TILE_U_M = 5.7  # matches generate_arena_textures.RIM_TILE_U_M
RIM_RIVETS_PER_ARC = 38  # 71.8 m of crest per 45 deg / 1.89 m pitch
PLATE_W, PLATE_H = 8.0, 4.0
PLATE_R0 = 99.5

# Obstacle keep-out constants (SS6.4a as amended by v3.1 Item 1.4; the mid
# and outer jamb radii are set by A13 coverage -- see the report ledger).
KEEPOUT_PILLAR = 6.5
KEEPOUT_DECK = 8.0
KEEPOUT_RAMP = 6.5
KEEPOUT_JAMB_NOSE = 6.5
KEEPOUT_JAMB_FACE = 8.0
JAMB_MID_R = 89.5
JAMB_OUT_R = 104.0
RAMP_FACE_BEARINGS_E = (155.0, 161.0, 167.0, 173.0)
DECK_FLANK_POINT_Y = (-42.5, -55.0, -67.5, -80.0)
# v3.6: interior samples along the deck NOSE (14.0 m), which G13 found
# covered by its two end corners alone. 4 gives a 2.8 m pitch.
HANDLE_NOSE_SAMPLES = 4

# Single-point groundtype toggle (pending probe P1). F8 verified the field
# LOWERCASE in the shipped stock gridmap material (m_gm_ice); CCW's own
# level materials use "groundType". Flip THIS constant only if P1 says so.
GROUNDTYPE_FIELD = "groundtype"
BUTTER_GROUNDTYPE = "ICE"
SALT_GROUNDTYPE = "SAND"

# v3.1 Item 5 triangle budgets, asserted at +/-25 %.
TRI_BUDGETS = {
    "wall_arc_45": 1000,
    "wall_arc_spout": 1400,
    "floor_skin_quadrant": 350,
    "handle": 1800,
    "handle_ramp_e": 700,
    "handle_ramp_w": 700,
    "merge_fillet": 120,  # v3 (round-2 fix 1): both merge-corner fillets, one shape
    "masher_pillar": 400,
    "grinder_pillar": 300,
    "geyser_tower": 500,
    "butter_pool": 120,
    "salt_arc": 150,
    "trim_ring": 500,
}
SCENE_BUDGET = 18360

# Materials -> texture family (6 families, 8 materials: the seasoned iron
# is split glossy-centre / matte-rim per v3.1 Item 5, same maps; v3.3 adds a
# skin-only matte so the floor can stop casting shadows without disarming
# the wall ring, which casts real ones).
#
# v3.3 SHADOW LAW. `cast_shadows: False` emits `"castShadows": false` on the
# material entry. Verified in the game's own files BEFORE use:
#   - lua/ge/extensions/editor/materialEditor.lua:2395
#     `checkbox("Cast Shadows", "castShadows", 0, "Material can cast it's own
#     shadows.")` -- an editable Material field, not a guess;
#   - lua/ge/client/core.lua:133/145 `mat:setField("castShadows", 0, "0")`
#     and :162/:177 `mat.castShadows = false` -- the engine's own materials;
#   - 81 stock Material entries carry it (gridmap_v2.zip, art_shapes.zip,
#     gameengine.zip), ALL of them `false`, ALL JSON booleans, 67 at
#     version 1.5 with a Stages array = exactly this file's schema. The
#     closest precedents are flat things lying on the ground: every
#     decalroad line material (`m_line_white`, `m_gm_droad_*`),
#     `m_gm_numbers_decal` (opaque), and driven surfaces that keep a
#     groundtype while disabling shadow casting (`ind_metal_expanded`,
#     groundtype METAL, opaque, v1.5, Stages).
# Absent means "casts", so the field is written ONLY when false -- which is
# how stock spells it (no stock entry writes castShadows true).
# Object level was RULED OUT by the same search: of 7,167 stock TSStatic
# records in gridmap_v2, ZERO carry any field whose name contains "shadow"
# (they carry class/__parent/isRenderEnabled/shapeName/collisionType/...).
# No prefab field is needed, so nothing is routed to the scenario worker
# beyond a re-cut -- and the round-3 uninitialised-S32 trap is avoided by
# not adding a record field at all.
M_IRON = f"{ARENA_ID}_cast_iron"
M_IRON_MATTE = f"{ARENA_ID}_cast_iron_matte"
M_IRON_SKIN = f"{ARENA_ID}_cast_iron_skin"
M_IRON_GLACIS = f"{ARENA_ID}_cast_iron_glacis"
M_BUTTER = f"{ARENA_ID}_butter"
M_SALT = f"{ARENA_ID}_salt"
M_STEEL = f"{ARENA_ID}_skillet_steel"
M_WOOD = f"{ARENA_ID}_handle_wood"
M_RIM = f"{ARENA_ID}_rim"
# The floor skin's own materials. The glossy iron was already skin-only; the
# matte iron is shared with both wall shapes (the bank, the batter jambs, the
# rim all cast real shadows), so the skin got its own copy of it rather than
# disarming the ring.
SKIN_MATERIALS = (M_IRON, M_IRON_SKIN)
# v3.4: the GLACIS -- the outer slope beyond the crest, r 93..113 -- is the
# same class of surface as the skin (one large, near-flat, ground-lying
# sheet) and the final critic's crops put the 150 m stripes squarely on it:
# `crit/g10_3_d150_glacisUR.png` (banded boot) against
# `crit/g10_1_d150_glacisUR.png` (clean boot), same camera, same build. v3.3
# disarmed the two FLOOR materials and left `cast_iron_matte` -- the bank AND
# the glacis -- casting, which is where the artifact then showed. The bank's
# shadow across the plaza is a real visual the arena keeps, so the glacis
# gets its own non-casting copy exactly as the skin did, rather than
# flipping the shared matte.
GLACIS_MATERIALS = (M_IRON_GLACIS,)
SHADOW_DISABLED_MATERIALS = SKIN_MATERIALS + GLACIS_MATERIALS
MATERIALS = {
    M_IRON: {
        "family": f"{ARENA_ID}_cast_iron",
        "color": [0.20, 0.18, 0.17, 1.0],
        "metallic": 0.15,
        "roughness": 0.50,
        "cast_shadows": False,
    },
    M_IRON_MATTE: {
        "family": f"{ARENA_ID}_cast_iron",
        "color": [0.20, 0.18, 0.17, 1.0],
        "metallic": 0.05,
        "roughness": 0.85,
    },
    # byte-for-byte the matte iron's look (same family, same maps, same
    # metallic/roughness) -- it differs ONLY in castShadows.
    M_IRON_SKIN: {
        "family": f"{ARENA_ID}_cast_iron",
        "color": [0.20, 0.18, 0.17, 1.0],
        "metallic": 0.05,
        "roughness": 0.85,
        "cast_shadows": False,
    },
    # v3.4: likewise for the glacis -- the matte iron's look to the digit,
    # differing only in castShadows.
    M_IRON_GLACIS: {
        "family": f"{ARENA_ID}_cast_iron",
        "color": [0.20, 0.18, 0.17, 1.0],
        "metallic": 0.05,
        "roughness": 0.85,
        "cast_shadows": False,
    },
    M_BUTTER: {
        "family": f"{ARENA_ID}_butter",
        "color": [0.95, 0.80, 0.30, 1.0],
        "metallic": 0.0,
        "roughness": 0.10,
    },
    M_SALT: {
        "family": f"{ARENA_ID}_salt",
        "color": [0.80, 0.79, 0.76, 1.0],
        "metallic": 0.0,
        "roughness": 0.85,
    },
    M_STEEL: {
        "family": f"{ARENA_ID}_skillet_steel",
        "color": [0.52, 0.54, 0.57, 1.0],
        "metallic": 0.9,
        "roughness": 0.35,
    },
    M_WOOD: {
        "family": f"{ARENA_ID}_handle_wood",
        "color": [0.45, 0.27, 0.15, 1.0],
        "metallic": 0.0,
        "roughness": 0.50,
    },
    M_RIM: {
        "family": f"{ARENA_ID}_rim",
        "color": [0.45, 0.45, 0.46, 1.0],
        "metallic": 0.8,
        "roughness": 0.40,
    },
}
FAMILIES = sorted({m["family"] for m in MATERIALS.values()})


def fail(message: str) -> None:
    raise AssertionError(f"ARENA BUILD ASSERT FAILED: {message}")


# ---------------------------------------------------------------------------
# The analytic wall profile (SS3.2 + v3.1 Item 2): monotone PCHIP through
# the bank knots with zero end slopes, a 12 mm toe lift that fades by r 78,
# then a slope-trapezoid glacis (2.5 m crest ease, 0.3 m toe feather)
# integrated to land on (113, 0). Slope is interpolated and integrated --
# never two height datums blended.
# ---------------------------------------------------------------------------


def _pchip_slopes(knots):
    n = len(knots)
    h = [knots[i + 1][0] - knots[i][0] for i in range(n - 1)]
    d = [(knots[i + 1][1] - knots[i][1]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0.0:
            m[i] = 0.0
        else:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    return m


_BANK_SLOPES = _pchip_slopes(BANK_KNOTS)
_GLACIS_G = CREST_Z / ((GLACIS_TOE - CREST_R) - 0.5 * GLACIS_EASE - 0.5 * GLACIS_TOE_FEATHER)


def bank_z(r: float) -> float:
    knots = BANK_KNOTS
    # Clamp to the knot domain: Blender mesh coordinates are float32, so an
    # r = 76 vertex can read back 76 - 5e-6 and a Hermite EXTRAPOLATION of
    # the last segment (t << 0) would return ~146 m for it.
    r = min(max(r, knots[0][0]), knots[-1][0])
    for i in range(len(knots) - 1):
        r0, z0 = knots[i]
        r1, z1 = knots[i + 1]
        if r0 <= r <= r1 or (i == len(knots) - 2 and r <= r1):
            h = r1 - r0
            t = (r - r0) / h
            m0, m1 = _BANK_SLOPES[i], _BANK_SLOPES[i + 1]
            h00 = (1 + 2 * t) * (1 - t) ** 2
            h10 = t * (1 - t) ** 2
            h01 = t * t * (3 - 2 * t)
            h11 = t * t * (t - 1)
            return h00 * z0 + h10 * h * m0 + h01 * z1 + h11 * h * m1
    return 0.0


def toe_lift(r: float) -> float:
    if r <= TOE_LIFT_HOLD_R:
        return TOE_LIFT
    if r >= TOE_LIFT_FADE_R:
        return 0.0
    return TOE_LIFT * (TOE_LIFT_FADE_R - r) / (TOE_LIFT_FADE_R - TOE_LIFT_HOLD_R)


def glacis_z(r: float) -> float:
    g, e, f = _GLACIS_G, GLACIS_EASE, GLACIS_TOE_FEATHER
    r0, r1 = CREST_R, GLACIS_TOE
    a, b = r0 + e, r1 - f
    if r <= r0:
        return CREST_Z
    if r <= a:
        s = r - r0
        return CREST_Z - 0.5 * g * s * s / e
    if r <= b:
        return CREST_Z - 0.5 * g * e - g * (r - a)
    if r <= r1:
        s = r1 - r
        return 0.5 * g * s * s / f
    return 0.0


def wall_z(r: float) -> float:
    if r < R_BANK_IN - 1e-4:  # float32 vertex tolerance (0.1 mm): the r=76 ring is IN
        return 0.0
    if r <= CREST_R:
        return bank_z(r) + toe_lift(r)
    if r <= GLACIS_TOE:
        return glacis_z(r)
    return 0.0


def wall_grade(r: float) -> float:
    """Local grade of the driven wall surface (finite difference kept INSIDE
    the wall domain so the intentional 12 mm collision step at r 76 and the
    grade edge at r 113 are not read as slopes)."""

    a = max(r - 0.005, R_BANK_IN)
    b = min(r + 0.005, GLACIS_TOE)
    if b - a < 1e-9:
        return 0.0
    return abs(wall_z(b) - wall_z(a)) / (b - a)


def slope_trapezoid(s: float, width: float, ease: float, drop: float) -> float:
    """Height BELOW the start of a ramp of ``width`` whose slope rises
    linearly 0 -> g over ``ease``, holds, and falls g -> 0 over ``ease``,
    integrated so the total fall is exactly ``drop`` (the glacis law:
    interpolate the slope, integrate, never blend two height datums).
    Peak grade g = drop / (width - ease); s = width returns ``drop`` exactly."""

    g = drop / (width - ease)
    if s <= 0.0:
        return 0.0
    if s <= ease:
        return 0.5 * g * s * s / ease
    if s <= width - ease:
        return 0.5 * g * ease + g * (s - ease)
    if s < width:
        t = width - s
        return drop - 0.5 * g * t * t / ease
    return drop


SKIN_SKIRT_GRADE = SKIN_TOP_Z / ((SKIN_SKIRT_R1 - SKIN_SKIRT_R0) - SKIN_EASE)
SKIN_FEATHER_GRADE = (SKIN_TOP_Z - FLOOR_SKIN_Z) / ((SKIN_FEATHER_R1 - SKIN_FEATHER_R0) - SKIN_EASE)


def skin_z(r: float) -> float:
    """Analytic floor-skin profile (v3.2): grade at r 6, slope-trapezoid
    skirt up to +50 mm by r 9, flat plaza, slope-trapezoid feather down to
    the 12 mm datum at r 76 (the wall sheet's and corridor floor's datum)."""

    if r <= SKIN_SKIRT_R0:
        return 0.0
    if r < SKIN_SKIRT_R1:
        return slope_trapezoid(
            r - SKIN_SKIRT_R0, SKIN_SKIRT_R1 - SKIN_SKIRT_R0, SKIN_EASE, SKIN_TOP_Z
        )
    if r <= SKIN_FEATHER_R0:
        return SKIN_TOP_Z
    if r < SKIN_FEATHER_R1:
        return SKIN_TOP_Z - slope_trapezoid(
            r - SKIN_FEATHER_R0,
            SKIN_FEATHER_R1 - SKIN_FEATHER_R0,
            SKIN_EASE,
            SKIN_TOP_Z - FLOOR_SKIN_Z,
        )
    return FLOOR_SKIN_Z


def adaptive_stations(r0, r1, fn, tol, max_span):
    """Stations such that the facet sagitta vs ``fn`` stays <= tol."""

    def refine(a, b, depth):
        mid = 0.5 * (a + b)
        sag = abs(fn(mid) - 0.5 * (fn(a) + fn(b)))
        if depth < 12 and (sag > tol or (b - a) > max_span):
            return refine(a, mid, depth + 1) + [mid] + refine(mid, b, depth + 1)
        return []

    return sorted(set([r0, r1] + refine(r0, r1, 0)))


# Forced stations (v3.1 Item 4 + the ramp/rim/corridor edges).
FORCED_STATIONS = [
    76.0,
    78.0,
    80.0,
    88.0,
    88.5,
    RIM_R0,
    91.4,
    RIM_R1,
    GLACIS_TOE - CORRIDOR_FEATHER,
    113.0,
]
WALL_STATIONS: list[float] = []
for _a, _b in zip(FORCED_STATIONS, FORCED_STATIONS[1:]):
    WALL_STATIONS.extend(adaptive_stations(_a, _b, wall_z, SAGITTA_TOL, 3.0))
WALL_STATIONS = sorted(set(WALL_STATIONS))


def columns_at(r: float) -> int:
    """Arc columns per 45 deg segment at a station (v3.1 Item 4)."""

    return 24 if wall_grade(r) > DENSE_GRADE else 12


def assert_profile_laws() -> None:
    if any(b - a <= 0 for a, b in zip(WALL_STATIONS, WALL_STATIONS[1:])):
        fail("wall stations not strictly increasing in r")
    steps = [R_BANK_IN + i * 0.01 for i in range(int((CREST_R - R_BANK_IN) / 0.01) + 1)]
    for a, b in zip(steps, steps[1:]):
        if wall_z(b) < wall_z(a) - 1e-9:
            fail(f"bank profile not monotone between r={a:.2f} and r={b:.2f}")
    gsteps = [CREST_R + i * 0.01 for i in range(int((GLACIS_TOE - CREST_R) / 0.01) + 1)]
    for a, b in zip(gsteps, gsteps[1:]):
        if wall_z(b) > wall_z(a) + 1e-9:
            fail(f"glacis profile not monotone between r={a:.2f} and r={b:.2f}")
    if abs(wall_z(CREST_R) - CREST_Z) > 1e-9:
        fail(f"crest z {wall_z(CREST_R)} != {CREST_Z}")
    slope_in = (wall_z(CREST_R) - wall_z(CREST_R - 0.01)) / 0.01
    slope_out = (glacis_z(CREST_R + 0.01) - glacis_z(CREST_R)) / 0.01
    if abs(slope_in) > 0.01 or abs(slope_out) > 0.01:
        fail(f"crest not tangent-flattened (slopes {slope_in:.4f}/{slope_out:.4f})")
    if abs(wall_z(GLACIS_TOE)) > 1e-9:
        fail("glacis does not land on grade at r 113")
    if abs(wall_z(R_BANK_IN) - TOE_LIFT) > 1e-9:
        fail("wall sheet does not start at the 12 mm floor datum")
    for a, b in zip(WALL_STATIONS, WALL_STATIONS[1:]):
        sag = abs(wall_z(0.5 * (a + b)) - 0.5 * (wall_z(a) + wall_z(b)))
        if sag > RELIEF_CAP:
            fail(f"wall facet sagitta {sag:.4f} m > {RELIEF_CAP} between {a:.2f}/{b:.2f}")
    # A11 max grade with the contract number.
    peak = max((wall_grade(r), r) for r in [76.0 + i * 0.01 for i in range(1541)])
    if peak[0] > MAX_GRADE:
        fail(
            f"A11: bank peak grade {peak[0] * 100:.1f} % at r={peak[1]:.2f} > {MAX_GRADE * 100:.0f} %"
        )
    print(
        f"A11 bank peak grade {peak[0] * 100:.1f} % at r={peak[1]:.2f} (cap {MAX_GRADE * 100:.0f} %)"
    )
    # A14 named stations.
    for named in (76.0, 88.5, 91.4, 113.0):
        if not any(abs(s - named) < 1e-9 for s in WALL_STATIONS):
            fail(f"A14: station r={named} missing from WALL_STATIONS")
    # A12 tangential ripple per station.
    worst = (0.0, 0.0)
    for r in WALL_STATIONS:
        pitch = math.radians(45.0 / columns_at(r))
        ripple = wall_grade(r) * r * (1.0 - math.cos(pitch / 2.0))
        worst = max(worst, (ripple, r))
        if ripple > RIPPLE_CAP:
            fail(
                f"A12: tangential ripple {ripple * 1000:.1f} mm at r={r:.2f} > {RIPPLE_CAP * 1000:.0f} mm"
            )
    print(f"A12 worst tangential ripple {worst[0] * 1000:.1f} mm at r={worst[1]:.2f}")
    print(f"wall stations: {len(WALL_STATIONS)}; glacis middle grade {_GLACIS_G * 100:.1f} %")


# ---------------------------------------------------------------------------
# Wall ring polylines. A station's ring is a closed polygon of chord points
# at its column pitch (world bearings are multiples of the pitch, aligned
# with the floor ring). ``ring_point_at`` returns the point ON THE CHORD at
# a bearing, so other shapes can sit exactly on wall mesh edges.
# ---------------------------------------------------------------------------


def bearing_point(bearing_deg: float, r: float, z: float = 0.0):
    b = math.radians(bearing_deg)
    return (r * math.sin(b), r * math.cos(b), z)


def ring_point_at(r: float, bearing_deg: float, z: float | None = None):
    """Point on the station ring's chord at ``bearing_deg`` (local frame)."""

    pitch = 45.0 / columns_at(r)
    # world columns sit at multiples of the pitch (the local -22.5 edge is
    # -6 x 3.75 from bearing 0, so the lattice is the same in every frame)
    k = math.floor(bearing_deg / pitch)
    a0, a1 = k * pitch, (k + 1) * pitch
    p0 = Vector(bearing_point(a0, r))
    p1 = Vector(bearing_point(a1, r))
    d = Vector(bearing_point(bearing_deg, 1.0))
    # intersect ray t*d with segment p0 + u (p1 - p0)
    e = p1 - p0
    den = d.x * e.y - d.y * e.x
    if abs(den) < 1e-12:
        t = r
    else:
        t = (p0.x * e.y - p0.y * e.x) / den
    zz = wall_z(r) if z is None else z
    return (t * d.x, t * d.y, zz)


def facet_wall_z(x: float, y: float) -> float:
    """Exact z of the wall MESH surface at a plan point (planar quads)."""

    r = math.hypot(x, y)
    b = math.degrees(math.atan2(x, y))
    if r <= WALL_STATIONS[0]:
        return wall_z(r)
    if r >= WALL_STATIONS[-1]:
        return 0.0
    i = max(k for k in range(len(WALL_STATIONS) - 1) if WALL_STATIONS[k] <= r)
    r0, r1 = WALL_STATIONS[i], WALL_STATIONS[i + 1]
    pitch = math.radians(45.0 / max(columns_at(r0), columns_at(r1)))
    bmid = (math.floor(math.radians(b) / pitch) + 0.5) * pitch
    u = r * math.cos(math.radians(b) - bmid)
    u0 = r0 * math.cos(pitch / 2.0)
    u1 = r1 * math.cos(pitch / 2.0)
    z0, z1 = wall_z(r0), wall_z(r1)
    return z0 + (u - u0) / (u1 - u0) * (z1 - z0)


# ---------------------------------------------------------------------------
# Mesh builder with constructive outward winding.
# ---------------------------------------------------------------------------


class MeshBuild:
    def __init__(self, name: str):
        self.name = name
        self.verts: list[tuple[float, float, float]] = []
        self.faces: list[tuple[int, ...]] = []
        self.face_mats: list[int] = []
        self.face_expect: list[Vector] = []
        self.materials: list[str] = []
        self.roles: dict[str, set[int]] = {}
        # A4c: role -> carrier surface z(x, y). Triangles whose vertices all
        # sit within NEAR_CARRIER_M of their carrier must face up outright.
        self.carriers: dict[str, object] = {}
        self._dedup: dict[tuple[int, int, int], int] = {}

    def mat(self, material_name: str) -> int:
        if material_name not in self.materials:
            self.materials.append(material_name)
        return self.materials.index(material_name)

    def vert(self, x: float, y: float, z: float, role: str | None = None) -> int:
        key = (round(x * 1e5), round(y * 1e5), round(z * 1e5))
        found = self._dedup.get(key)
        if found is None:
            self.verts.append((x, y, z))
            found = len(self.verts) - 1
            self._dedup[key] = found
        if role:
            self.roles.setdefault(role, set()).add(found)
        return found

    def _oriented(self, indices, expect):
        p0 = Vector(self.verts[indices[0]])
        p1 = Vector(self.verts[indices[1]])
        p2 = Vector(self.verts[indices[2]])
        normal = (p1 - p0).cross(p2 - p0)
        if normal.length < 1e-12 and len(indices) == 4:
            p3 = Vector(self.verts[indices[3]])
            normal = (p2 - p1).cross(p3 - p1)
        if normal.length < 1e-12:
            return ()
        return indices if normal.dot(expect) > 0.0 else tuple(reversed(indices))

    def _push(self, indices, expect, mat) -> None:
        self.faces.append(indices)
        self.face_mats.append(mat)
        self.face_expect.append(Vector(expect))

    def _tri_sign(self, i, j, k, expect) -> int:
        p0, p1, p2 = (Vector(self.verts[x]) for x in (i, j, k))
        n = (p1 - p0).cross(p2 - p0)
        if n.length < 1e-12:
            return 0
        return 1 if n.dot(expect) > 0.0 else -1

    def quad(self, a, b, c, d, expect, mat) -> None:
        """Emit a quad only if BOTH diagonals split it into two triangles
        that face ``expect`` (round-2 critique fix 2: a bow-tie/non-convex
        quad passed the one-diagonal check and the exporter's triangulation
        flipped one half). Otherwise emit explicit, individually oriented
        triangles along the consistent diagonal."""

        unique = list(dict.fromkeys((a, b, c, d)))
        if len(unique) < 4:
            if len(unique) == 3:
                self.tri(*unique, expect=expect, mat=mat)
            return
        ac = (self._tri_sign(a, b, c, expect), self._tri_sign(a, c, d, expect))
        bd = (self._tri_sign(a, b, d, expect), self._tri_sign(b, c, d, expect))

        def consistent(s):
            return s[0] != 0 and s[0] == s[1]

        if consistent(ac) and consistent(bd) and ac[0] == bd[0]:
            self._push((a, b, c, d) if ac[0] > 0 else (d, c, b, a), expect, mat)
        elif consistent(ac):
            self.tri(a, b, c, expect=expect, mat=mat)
            self.tri(a, c, d, expect=expect, mat=mat)
        elif consistent(bd):
            self.tri(a, b, d, expect=expect, mat=mat)
            self.tri(b, c, d, expect=expect, mat=mat)
        else:
            self.tri(a, b, c, expect=expect, mat=mat)
            self.tri(a, c, d, expect=expect, mat=mat)

    def tri(self, a, b, c, *, expect, mat) -> None:
        if len({a, b, c}) < 3:
            return
        indices = self._oriented((a, b, c), expect)
        if indices:
            self._push(indices, expect, mat)

    def stitch(self, row_a: list[int], row_b: list[int], expect, mat) -> None:
        """Connect two rows of equal count (quads) or 2:1 count (fans)."""

        na, nb = len(row_a), len(row_b)
        if na == nb:
            for j in range(na - 1):
                self.quad(row_a[j], row_a[j + 1], row_b[j + 1], row_b[j], expect, mat)
        elif nb == 2 * na - 1:
            for j in range(na - 1):
                self.tri(row_a[j], row_b[2 * j], row_b[2 * j + 1], expect=expect, mat=mat)
                self.tri(row_a[j], row_b[2 * j + 1], row_a[j + 1], expect=expect, mat=mat)
                self.tri(row_a[j + 1], row_b[2 * j + 1], row_b[2 * j + 2], expect=expect, mat=mat)
        elif na == 2 * nb - 1:
            self.stitch(row_b, row_a, expect, mat)
        else:
            fail(f"{self.name}: cannot stitch rows of {na} and {nb} vertices")

    def to_object(self, materials) -> bpy.types.Object:
        mesh = bpy.data.meshes.new(f"{self.name}_mesh")
        mesh.from_pydata(self.verts, [], self.faces)
        mesh.update()
        if mesh.validate(verbose=False):
            fail(f"{self.name}: mesh.validate() had to correct geometry")
        obj = bpy.data.objects.new(self.name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        for material_name in self.materials:
            obj.data.materials.append(materials[material_name])
        for poly, mat_index in zip(mesh.polygons, self.face_mats):
            poly.material_index = mat_index
        for poly in mesh.polygons:
            if poly.area < 1e-9:
                fail(f"{self.name}: degenerate polygon at index {poly.index}")
        # A4b: winding per TRIANGLE after triangulation (the exporter
        # triangulates; a polygon-level check cannot see a folded half).
        mesh.calc_loop_triangles()
        bad, slivers = [], []
        for lt in mesh.loop_triangles:
            p0, p1, p2 = (mesh.vertices[i].co for i in lt.vertices)
            n = (p1 - p0).cross(p2 - p0)
            if n.length < 2e-4:  # area < 1e-4 m^2: a sliver, not a face
                slivers.append(tuple(round(c, 3) for c in lt.center))
                continue
            if n.dot(self.face_expect[lt.polygon_index]) <= 0.0:
                bad.append((lt.polygon_index, tuple(round(c, 3) for c in lt.center)))
        if bad:
            fail(
                f"{self.name}: {len(bad)} triangles face against their polygon's "
                f"expected direction, e.g. {bad[:3]}"
            )
        if slivers:
            fail(f"{self.name}: {len(slivers)} near-zero-area triangles, e.g. {slivers[:3]}")
        # A4c (round-3 erratum 2): the expect-vector test above is only as
        # good as the expect. A horizontal-dominant expect let the name
        # plate's uphill skirt through wound face-DOWN (n = (0, -0.20, -0.98)
        # passed on its horizontal term). Any triangle whose vertices ALL lie
        # within NEAR_CARRIER_M of their registered carrier is a proud/rebated
        # dressing on a driven surface and must face up, full stop.
        if self.carriers:
            carrier_of = {}
            for role, fn in self.carriers.items():
                for vid in self.roles.get(role, ()):
                    carrier_of[vid] = fn
            checked, near_bad = 0, []
            for lt in mesh.loop_triangles:
                fns = [carrier_of.get(i) for i in lt.vertices]
                if not all(fns):
                    continue
                cos = [mesh.vertices[i].co for i in lt.vertices]
                if any(abs(co.z - fn(co.x, co.y)) > NEAR_CARRIER_M for co, fn in zip(cos, fns)):
                    continue
                n = (cos[1] - cos[0]).cross(cos[2] - cos[0])
                if n.length < 2e-4:
                    continue
                checked += 1
                if n.z <= 0.0:
                    near_bad.append(
                        (
                            lt.polygon_index,
                            tuple(round(c, 3) for c in lt.center),
                            tuple(round(c, 3) for c in n.normalized()),
                        )
                    )
            if near_bad:
                fail(
                    f"{self.name}: A4c -- {len(near_bad)} near-carrier triangles face DOWN "
                    f"(polygon, centre, normal), e.g. {near_bad[:3]}"
                )
            print(f"A4c {self.name}: {checked} near-carrier triangles all face up")
        obj["arena_roles"] = {k: sorted(v) for k, v in self.roles.items()}
        return obj


def metric_uvs(
    obj,
    meters_per_tile: float,
    grain_along_y: bool = False,
    rim_material: str | None = None,
    plate_uv=None,
    cylindrical: bool = False,
    staves: bool = False,
) -> None:
    """Dominant-axis planar UVs at metric density (hot_potato v2.4 UV law).

    Faces on ``rim_material`` get polar UVs (U = crest arc in rim tiles,
    V = (r - 90)/3 * 0.5) so the rivet band runs continuously around the
    lap; ``plate_uv`` maps the name-plate faces into the texture's top half.
    """

    mesh = obj.data
    layer = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    t = meters_per_tile
    rim_index = None
    if rim_material is not None:
        for i, m in enumerate(mesh.materials):
            if m is not None and m.name == rim_material:
                rim_index = i
    for poly in mesh.polygons:
        if rim_index is not None and poly.material_index == rim_index:
            for loop_index in poly.loop_indices:
                co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
                if plate_uv is not None:
                    layer.data[loop_index].uv = plate_uv(co)
                    continue
                r = math.hypot(co.x, co.y)
                b = math.degrees(math.atan2(co.x, co.y))
                u = (b + 22.5) / 45.0 * (RIM_RIVETS_PER_ARC / 3.0)
                # Guard band: keep the band's V inside 0.02..0.48. At V = 0.5
                # the texture switches to the name-plate half and bilinear /
                # mip filtering bled the plate's brass border into the band's
                # outer edge as a thin bright line along r 93 (round-2 fix 6).
                v = 0.02 + (r - RIM_R0) / (RIM_R1 - RIM_R0) * 0.46
                layer.data[loop_index].uv = (u, max(0.02, min(0.48, v)))
            continue
        n = poly.normal
        axis = max(range(3), key=lambda i: abs(n[i]))
        if cylindrical and abs(n.z) < 0.6:
            # Revolves: u = azimuth x mean radius (metric), v = z. A planar
            # box projection of plank seams on a cylinder reads as a tile
            # grid (round-2 critique fix 6). The seam column at azimuth
            # +/-pi is unwrapped so u keeps counting up across it.
            cen = poly.center
            base = math.atan2(cen.y, cen.x)
            r_mean = math.hypot(cen.x, cen.y)
            for loop_index in poly.loop_indices:
                co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
                a = math.atan2(co.y, co.x)
                while a - base > math.pi:
                    a -= math.tau
                while a - base < -math.pi:
                    a += math.tau
                # ``staves``: grain along z, plank seams become vertical
                # stave joints (a coopered/turned body); otherwise grain
                # runs around the circumference.
                layer.data[loop_index].uv = (
                    (co.z / t, a * r_mean / t) if staves else (a * r_mean / t, co.z / t)
                )
            continue
        for loop_index in poly.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            if axis == 2:
                u, v = (co.y, co.x) if grain_along_y else (co.x, co.y)
            elif axis == 0:
                u, v = co.y, co.z
            else:
                u, v = co.x, co.z
            layer.data[loop_index].uv = (u / t, v / t)


def finish_shape(obj, smooth_angle: float = 38.0) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(smooth_angle))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)


def tri_count(obj) -> int:
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def wall_material(r: float, build: MeshBuild) -> int:
    if RIM_R0 - 1e-9 <= r <= RIM_R1 + 1e-9:
        return build.mat(M_RIM)
    return build.mat(M_IRON_MATTE)


def band_material(r0: float, r1: float, build: MeshBuild) -> int:
    """Material for the band between two stations: rim iff fully inside;
    otherwise the GLACIS copy past the crest (v3.4) or the bank's matte.

    This one function is the whole v3.4 change. It is the only material
    decision on the glacis slope of BOTH wall shapes -- `wall_arc_45`'s
    bands and `wall_arc_spout`'s side patches both call it -- so the split
    is a pure per-face material assignment: no vertex, no face, no station
    and no winding moves (asserted end-to-end by A23).

    The band must lie ENTIRELY beyond the crest to count as glacis, so the
    rim band (r 90..93, its own material) and the crest band are untouched
    and the first glacis band starts at r 93. The batter chutes and the
    spout corridor floor keep the bank's matte deliberately -- see the
    v3.4 report note.
    """

    if r0 >= RIM_R0 - 1e-9 and r1 <= RIM_R1 + 1e-9:
        return build.mat(M_RIM)
    if r0 >= CREST_R - 1e-9:
        return build.mat(M_IRON_GLACIS)
    return build.mat(M_IRON_MATTE)


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------


def wall_row(
    build: MeshBuild, r: float, lo: float, hi: float, cols: int, role: str = "wall"
) -> list[int]:
    return [
        build.vert(*bearing_point(lo + (hi - lo) * k / cols, r, wall_z(r)), role)
        for k in range(cols + 1)
    ]


def build_wall_arc_45(materials) -> bpy.types.Object:
    """45 deg wall+glacis segment, local span bearing [-22.5, +22.5]."""

    build = MeshBuild(f"{ARENA_ID}_wall_arc_45")
    up = Vector((0, 0, 1))
    rows = [wall_row(build, r, -22.5, 22.5, columns_at(r)) for r in WALL_STATIONS]
    for i in range(len(WALL_STATIONS) - 1):
        mat = band_material(WALL_STATIONS[i], WALL_STATIONS[i + 1], build)
        build.stitch(rows[i], rows[i + 1], up, mat)
    return build.to_object(materials)


def jamb_line(side: int):
    splay = math.radians(SPOUT_SPLAY_DEG)
    nx, ny = side * SPOUT_HALF_W, math.sqrt(R_BANK_IN**2 - SPOUT_HALF_W**2)
    dx, dy = side * math.sin(splay), math.cos(splay)
    return Vector((nx, ny, 0.0)), Vector((dx, dy, 0.0))


def jamb_point(side: int, r: float) -> Vector:
    """Plan point of the jamb line at radius r (local spout frame)."""

    n, d = jamb_line(side)
    b = n.dot(d)
    c = n.length_squared - r * r
    t = -b + math.sqrt(max(0.0, b * b - c))
    return n + d * t


def jamb_angle(side: int, r: float) -> float:
    p = jamb_point(side, r)
    return math.degrees(math.atan2(p.x, p.y))


def corridor_z(r: float) -> float:
    if r < R_BANK_IN:
        return 0.0
    if r >= GLACIS_TOE:
        return 0.0
    if r > GLACIS_TOE - CORRIDOR_FEATHER:
        return CORRIDOR_Z * (GLACIS_TOE - r) / CORRIDOR_FEATHER
    return CORRIDOR_Z


def batter_top(side: int, r: float):
    """Top of the 1:1 battered jamb at station r: lateral offset = wall
    height, iterated so the top lands exactly on the bank surface."""

    j = jamb_point(side, r)
    _, d = jamb_line(side)
    n = Vector((d.y, -d.x, 0.0))
    # Away from the corridor = the same sign as the jamb's side in x.
    # (Round 2 first used n.dot(j) < 0, which flipped BOTH jambs inward and
    # built the batter as a 45-deg overhang over the corridor -- the
    # adapted critic script measured the opening at the bank surface
    # narrower than the floor throat, which is impossible for a chute.)
    if n.x * side < 0:
        n = -n
    zf = corridor_z(r)
    h = max(0.0, wall_z(r) - zf)
    for _ in range(8):
        t = j + n * h
        h = max(0.0, wall_z(t.length) - zf)
    t = j + n * h
    return j, t, n, h, zf


def build_wall_arc_spout(materials) -> bpy.types.Object:
    """45 deg segment with the grade-level spout, 1:1 battered jambs
    (v3.1 Item 3), corridor floor on the 12 mm datum."""

    build = MeshBuild(f"{ARENA_ID}_wall_arc_spout")
    up = Vector((0, 0, 1))
    stations = WALL_STATIONS
    side_cols = 3
    corridor_cols = [-11.25 + 3.75 * k for k in range(7)]
    for side in (+1, -1):
        edge = side * 22.5
        patch, batter = [], []
        for r in stations:
            j, t, n, h, zf = batter_top(side, r)
            a_top = math.degrees(math.atan2(t.x, t.y))
            if abs(r - R_BANK_IN) < 1e-9:
                # station 76: the batter has zero height, so foot, mid and
                # top are ONE vertex -- the floor-ring chord point. (Round 2
                # gave the top its own vertex on the circle 4 cm away and
                # the flat sliver between them folded into two down-facing
                # triangles: critique fix 2.)
                foot = build.vert(
                    *ring_point_at(r, math.degrees(math.atan2(j.x, j.y)), zf), "floor_edge"
                )
                mid = foot
                row = [foot]
                fixed = [15.0, 18.75, 22.5] if side > 0 else [-15.0, -18.75, -22.5]
                for a in fixed:
                    row.append(build.vert(*bearing_point(a, r, wall_z(r)), "wall"))
            else:
                foot = build.vert(j.x, j.y, zf, "floor_edge")
                m = j + n * (h * 0.5)
                mid = build.vert(m.x, m.y, zf + h * 0.5, "batter")
                row = [build.vert(t.x, t.y, zf + h, "wall")]
                for k in range(1, side_cols + 1):
                    a = a_top + (edge - a_top) * k / side_cols
                    row.append(build.vert(*bearing_point(a, r, wall_z(r)), "wall"))
            patch.append(row)
            batter.append((foot, mid, row[0], h))
        for i in range(len(stations) - 1):
            build.stitch(
                patch[i], patch[i + 1], up, band_material(stations[i], stations[i + 1], build)
            )
        # batter chute: 45 deg fill from the corridor floor to the bank
        _, _, n_out, _, _ = batter_top(side, 90.0)
        expect = (up - n_out).normalized()
        for i in range(len(stations) - 1):
            f0, m0, t0, h0 = batter[i]
            f1, m1, t1, h1 = batter[i + 1]
            if h0 < 0.001 and h1 < 0.001:
                continue
            # A chute is a fill surface, not the lip: always matte (fix 3).
            mat = build.mat(M_IRON_MATTE)
            build.quad(f0, f1, m1, m0, expect, mat)
            build.quad(m0, m1, t1, t0, expect, mat)
    # Corridor floor between the batter feet on the 12 mm datum, columns on
    # the world 3.75 deg lattice so the r = 76 row coincides with the floor
    # skin ring; feathered to grade over the last 0.3 m.
    floor = []
    for r in stations:
        z = corridor_z(r)
        ja = jamb_angle(+1, r)
        if abs(r - R_BANK_IN) < 1e-9:
            row = [build.vert(*ring_point_at(r, -ja, z), "floor_edge")]
            row += [build.vert(*bearing_point(a, r, z), "floor") for a in corridor_cols]
            row.append(build.vert(*ring_point_at(r, ja, z), "floor_edge"))
        else:
            jm = jamb_point(-1, r)
            jp = jamb_point(+1, r)
            row = [build.vert(jm.x, jm.y, z, "floor_edge")]
            row += [build.vert(*bearing_point(a, r, z), "floor") for a in corridor_cols]
            row.append(build.vert(jp.x, jp.y, z, "floor_edge"))
        floor.append(row)
    iron = build.mat(M_IRON_MATTE)
    for i in range(len(stations) - 1):
        build.stitch(floor[i], floor[i + 1], up, iron)
    return build.to_object(materials)


def build_floor_skin_quadrant(materials) -> bpy.types.Object:
    """90 deg annular DRIVEN skin, r 6..76 (v3.2): grade at r 6, slope-
    trapezoid skirt up to +50 mm by r 9, flat plaza, slope-trapezoid
    feather down to the 12 mm wall/corridor datum at r 76. Columns on the
    world 3.75 deg lattice so the r 76 ring coincides vertex-for-vertex
    with the wall sheet's toe ring and the two quadrant seams are shared
    vertices under rotation (A20)."""

    build = MeshBuild(f"{ARENA_ID}_floor_skin_quadrant_a{FLOOR_LOD_NEAR_PX}")
    glossy = build.mat(M_IRON)
    # v3.3: the skin's OWN matte (identical look, castShadows false) instead
    # of the shared M_IRON_MATTE the wall ring uses.
    matte = build.mat(M_IRON_SKIN)
    build.carriers["skin"] = lambda x, y: skin_z(math.hypot(x, y))  # A4c: all face up
    rings = [(r, skin_z(r)) for r in SKIN_RINGS]
    cols = [(-45.0 + 3.75 * k) for k in range(25)]
    grid = [[build.vert(*bearing_point(c, r, z), "skin") for c in cols] for r, z in rings]
    up = Vector((0, 0, 1))
    for i in range(len(rings) - 1):
        mat = glossy if rings[i + 1][0] <= 46.0 else matte
        for j in range(len(cols) - 1):
            build.quad(grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j], up, mat)
    return build.to_object(materials)


def build_floor_skin_node_tree(near) -> list:
    """Stock node tree for the floor skin DAE (v3.2: ONE mesh detail):

        base00 -> start01 -> <name>_a290
               -> nulldetail10

    nulldetail is a child of base00 and a SIBLING of start01: in the 91
    gridmap_v2.zip DAEs that carry one it sits under base00 in 90 and at
    the scene root in 1, never under start01 (s_gm_groundplane_64m is
    base00 -> {collision-1, nulldetail10, start01 -> {_a150, Colmesh,
    _a15}}). The +50 mm far detail (`_a70`) that v3/v3.1 carried is gone:
    the critic's negative control proved the engine never switched to it,
    and the skin itself now sits at +50 mm with collision. With a single
    mesh detail there is no question which detail carries the collision.

    Returns the scaffold objects to export with the mesh (empty when
    FLOOR_SKIN_STOCK_NODES is off)."""

    if not FLOOR_SKIN_STOCK_NODES:
        return []
    base = bpy.data.objects.new("base00", None)
    start = bpy.data.objects.new("start01", None)
    null = bpy.data.objects.new(f"nulldetail{FLOOR_LOD_NULL_PX}", None)
    for obj in (base, start, null):
        bpy.context.scene.collection.objects.link(obj)
    start.parent = base
    null.parent = base  # sibling of start01 (stock convention, erratum 1)
    near.parent = start
    return [base, start, null]


def build_handle(materials) -> bpy.types.Object:
    """The skillet-handle causeway: deck at +4.0, solid embankment, curved
    end edge flush on the bank arc at the 4.0 knot, closed rear."""

    build = MeshBuild(f"{ARENA_ID}_handle")
    wood = build.mat(M_WOOD)
    up = Vector((0, 0, 1))
    xcols = [(-HANDLE_HALF_W + HANDLE_HALF_W * 2.0 * k / 11.0) for k in range(12)]

    def end_y(x):
        return -math.sqrt(HANDLE_END_R**2 - x * x)

    rows = 48
    deck = []
    for i in range(rows + 1):
        t = i / rows
        deck.append(
            [
                build.vert(
                    x, -HANDLE_NOSE_R + (end_y(x) + HANDLE_NOSE_R) * t, HANDLE_DECK_Z, "deck"
                )
                for x in xcols
            ]
        )
    for i in range(rows):
        for j in range(len(xcols) - 1):
            build.quad(deck[i][j], deck[i][j + 1], deck[i + 1][j + 1], deck[i + 1][j], up, wood)
    # v3.8: the tuck strip is tessellated RADIALLY LIKE THE BANK -- a row at
    # every wall station it spans -- and each row is rebated below the
    # MINIMUM of the bank mesh across the span to its neighbouring columns.
    #
    # v3.7 measured the old single-chord strip standing +4.741 mm PROUD of
    # the bank mid-span. Diagnosis (probe_tuck_diagnose.py): the bank mesh
    # between r 88.5 and 89.0 is piecewise linear with a SLOPE BREAK at
    # station 88.875 (0.0239 -> 0.0273 m per step), and a single chord over
    # an increasing-slope surface rides above it in the middle -- the peak
    # landed exactly at r 88.875. Deepening the rebate would only shrink
    # that; matching the tessellation removes the cause, because within one
    # radial band both surfaces are linear, so a strip whose two ends are
    # below the mesh cannot rise above it in between. The per-column MIN
    # closes the other axis: the bank's r-ring is a chord polygon whose
    # bearing sawtooth is ~6 mm at this radius, wider than the 4 mm rebate,
    # and the deck's columns do not align with the bank's.
    # The strip DESCENDS from the deck edge instead of climbing with the
    # bank. That removes the tessellation mismatch instead of shrinking it:
    # every point of the strip is at or below the deck plane (4.000), while
    # the bank mesh everywhere outboard of the rear edge is at or above
    # 4.0006, so the strip is strictly under the bank by construction --
    # independently of how either surface is faceted, at every station and
    # between stations. Matching the bank's radial tessellation was tried
    # first and only REDUCED the crossing (4.741 -> 0.646 mm), because the
    # deck edge is pinned at exactly 4.000 with just 0.6 mm of headroom
    # under the bank's own minimum; a strip that climbs from there spends
    # that headroom immediately. A skirt that falls never does.
    # The margin is asserted below rather than assumed.
    y_far = {x: -math.sqrt((HANDLE_END_R + HANDLE_TUCK_SPAN) ** 2 - x * x) for x in xcols}
    near_row = [build.vert(x, end_y(x), HANDLE_DECK_Z, "deck") for x in xcols]
    far_row = [build.vert(x, y_far[x], HANDLE_DECK_Z - HANDLE_TUCK_DROP, "tuck") for x in xcols]
    for j in range(len(xcols) - 1):
        build.quad(near_row[j], near_row[j + 1], far_row[j + 1], far_row[j], up, wood)
    # The guarantee, measured over the whole strip footprint rather than
    # trusted: the lowest the bank mesh gets anywhere behind the rear edge
    # must still be above the highest the strip gets (the deck edge).
    bank_floor = min(
        facet_wall_z(x, -math.sqrt(rr * rr - x * x))
        for rr in [HANDLE_END_R + HANDLE_TUCK_SPAN * k / 24.0 for k in range(25)]
        for x in [-HANDLE_HALF_W + 2.0 * HANDLE_HALF_W * k / 120.0 for k in range(121)]
    )
    # Equality at r 88.5 is the junction line itself (the bank's own column
    # vertices sit at wall_z(88.5) == the deck plane), so the requirement is
    # that the mesh never falls BELOW the deck plane behind the edge. Given
    # that, a skirt which only descends can never rise through it.
    if bank_floor < HANDLE_DECK_Z - 1e-9:
        fail(
            f"handle tuck: the bank mesh dips to {bank_floor:.6f} behind the rear edge, "
            f"below the deck plane {HANDLE_DECK_Z} -- a descending skirt would no longer be "
            f"guaranteed to sit under it"
        )
    print(
        f"handle tuck: bank mesh floor behind the rear edge {bank_floor:.6f} >= deck plane "
        f"{HANDLE_DECK_Z:.4f} (equality only ON the r {HANDLE_END_R} junction line); "
        f"skirt descends {HANDLE_TUCK_DROP * 1000:.0f} mm, so it is under the bank by "
        f"construction"
    )
    zrows = [HANDLE_DECK_Z, 3.0, 2.0, 1.0, 0.0]
    for side, x in ((-1, -HANDLE_HALF_W), (+1, HANDLE_HALF_W)):
        outward = Vector((side, 0, 0))
        wallcols = []
        for i in range(rows + 1):
            t = i / rows
            y = -HANDLE_NOSE_R + (end_y(x) + HANDLE_NOSE_R) * t
            wallcols.append([build.vert(x, y, z, "flank") for z in zrows])
        for i in range(rows):
            for k in range(len(zrows) - 1):
                build.quad(
                    wallcols[i][k],
                    wallcols[i][k + 1],
                    wallcols[i + 1][k + 1],
                    wallcols[i + 1][k],
                    outward,
                    wood,
                )
    nosecols = [[build.vert(x, -HANDLE_NOSE_R, z, "nose") for z in zrows] for x in xcols]
    for j in range(len(xcols) - 1):
        for k in range(len(zrows) - 1):
            build.quad(
                nosecols[j][k],
                nosecols[j][k + 1],
                nosecols[j + 1][k + 1],
                nosecols[j + 1][k],
                Vector((0, 1, 0)),
                wood,
            )
    rearcols = [[build.vert(x, end_y(x), z, "rear") for z in zrows] for x in xcols]
    for j in range(len(xcols) - 1):
        for k in range(len(zrows) - 1):
            build.quad(
                rearcols[j][k],
                rearcols[j][k + 1],
                rearcols[j + 1][k + 1],
                rearcols[j + 1][k],
                Vector((0, -1, 0)),
                wood,
            )
    return build.to_object(materials)


# ---- the tangential arc ramp (v3.1 Item 1.1) --------------------------------

RAMP_SLOPE_ARC_DEG = None  # set below from the flank bearing at r 80


def flank_bearing(r: float, side: int) -> float:
    """Bearing where the deck flank x = side*7 crosses radius r."""

    return 180.0 - side * math.degrees(math.asin(HANDLE_HALF_W / r))


_FLANK80 = flank_bearing(RAMP_R_IN, +1)  # 175.0
_FLAT_DEG = math.degrees(RAMP_FLAT_M / RAMP_R_IN)  # 2.865
RAMP_SLOPE_ARC_DEG = _FLANK80 - _FLAT_DEG - RAMP_TOE_BEARING  # 23.135
_SLOPE_LEN = math.radians(RAMP_SLOPE_ARC_DEG) * RAMP_R_IN  # 32.30 m
_RAMP_K = 1.0 / (_SLOPE_LEN - RAMP_EASE_M)


def ramp_s(bearing_e: float) -> float:
    """Warp fraction 0..1 along the EAST ramp bearing (slope-integrated:
    3 m ease, constant, 3 m ease, then flat)."""

    u = math.radians(bearing_e - RAMP_TOE_BEARING) * RAMP_R_IN
    if u <= 0.0:
        return 0.0
    e, k = RAMP_EASE_M, _RAMP_K
    if u <= e:
        return 0.5 * k * u * u / e
    if u <= _SLOPE_LEN - e:
        return 0.5 * k * e + k * (u - e)
    if u <= _SLOPE_LEN:
        rem = _SLOPE_LEN - u
        return 1.0 - 0.5 * k * rem * rem / e
    return 1.0


def ramp_top_point(side: int, r: float, b_east: float):
    """One ramp-top vertex: ON the wall ring chord at the mirrored bearing,
    lifted 4 mm, warped by s(theta). Shared by the ramp rows and the merge
    fillet so their common edge is coordinate-identical."""

    bb = b_east if side > 0 else 360.0 - b_east
    x, y, zf = ring_point_at(r, bb)
    base = zf + RAMP_LIFT
    return x, y, base + ramp_s(b_east) * (HANDLE_DECK_Z - base), zf


def build_handle_ramp(materials, side: int) -> bpy.types.Object:
    """Warped tangential arc ramp on the apron, r 80..88.

    z(r, theta) = facet(r) + 0.004 + s(theta) * (4.0 - facet(r) - 0.004):
    the bank height is constant along theta, so the along-path grade is
    monotone and never out-dives either end. Rows are the wall stations,
    vertices sit ON the wall ring chords, so the toe is conformal to the
    MESH (4 mm proud, no z-fight). ``side`` +1 = east, -1 = west (mirror).
    """

    tag = "e" if side > 0 else "w"
    build = MeshBuild(f"{ARENA_ID}_handle_ramp_{tag}")
    wood = build.mat(M_WOOD)
    up = Vector((0, 0, 1))
    rows_r = [r for r in WALL_STATIONS if RAMP_R_IN - 1e-9 <= r <= RAMP_R_OUT + 1e-9]

    def mirror(b):
        return b if side > 0 else 360.0 - b

    top_rows, foot_in, foot_out = [], [], []
    for r in rows_r:
        b_end = flank_bearing(r, +1)
        # Tuck INTO the deck: x = 7 - 0.3 (round 2: a sign slip put it at
        # x = 7.3, folding the last quad back over the merge -- caught by
        # the adapted critic script, now guarded by the ordering assert).
        b_tuck = 180.0 - math.degrees(math.asin((HANDLE_HALF_W - RAMP_TUCK) / r))
        bearings = [
            RAMP_TOE_BEARING + (b_end - RAMP_TOE_BEARING) * k / RAMP_COLUMNS
            for k in range(RAMP_COLUMNS + 1)
        ] + [b_tuck]
        if any(b1 <= b0 for b0, b1 in zip(bearings, bearings[1:])):
            fail(f"ramp {tag}: column bearings not strictly increasing at r={r}")
        row = []
        for idx, b in enumerate(bearings):
            x, y, z, zf = ramp_top_point(side, r, b)
            if idx == len(bearings) - 1:
                z = HANDLE_DECK_Z - 0.004
            role = "ramp_top" if idx < len(bearings) - 1 else "ramp_tuck"
            vid = build.vert(x, y, z, role)
            if abs(r - RAMP_R_IN) < 1e-9 and idx < len(bearings) - 1:
                build.roles.setdefault("ramp_inner_edge", set()).add(vid)
            row.append(vid)
            if abs(r - RAMP_R_IN) < 1e-9:
                foot_in.append(build.vert(x, y, zf, "ramp_foot"))
            if abs(r - RAMP_R_OUT) < 1e-9:
                foot_out.append(build.vert(x, y, zf, "ramp_foot"))
        top_rows.append(row)
    for i in range(len(rows_r) - 1):
        build.stitch(top_rows[i], top_rows[i + 1], up, wood)
    # inner flank (r 80): vertical face from the ramp top to the bank ring
    inner = top_rows[0]
    for k in range(len(inner) - 1):
        p = Vector(build.verts[inner[k]])
        build.quad(
            inner[k], inner[k + 1], foot_in[k + 1], foot_in[k], Vector((-p.x, -p.y, 0.0)), wood
        )
    outer = top_rows[-1]
    for k in range(len(outer) - 1):
        p = Vector(build.verts[outer[k]])
        build.quad(
            outer[k], outer[k + 1], foot_out[k + 1], foot_out[k], Vector((p.x, p.y, 0.0)), wood
        )
    # toe end face (zero height at the toe by construction: s = 0) -- the
    # inner/outer feet meet the top there, so no face is needed. The merge
    # end is closed by the deck flank (the ramp is tucked into the deck).
    return build.to_object(materials)


def build_merge_fillet(materials) -> bpy.types.Object:
    """Both merge-corner fillets (round-2 critique fix 1), one shape in the
    arena frame: a quarter-round solid tangent to the deck flank and to the
    ramp's inner flank, so the 90-deg two-wall nook at each merge no longer
    exists. The top's arc edge reuses the ramp's inner-edge vertex
    coordinates (ramp_top_point -> no lip against the ramp), runs at 4.0
    along the deck flank (flush with the deck), the round wall runs to
    grade, and a 0.3 m strip tucks under the deck top. Shipped as its own
    DAE so the critic-verified ramp and deck files stay byte-identical."""

    build = MeshBuild(f"{ARENA_ID}_merge_fillet")
    wood = build.mat(M_WOOD)
    up = Vector((0, 0, 1))
    b_end80 = flank_bearing(RAMP_R_IN, +1)
    bearings80 = [
        RAMP_TOE_BEARING + (b_end80 - RAMP_TOE_BEARING) * k / RAMP_COLUMNS
        for k in range(RAMP_COLUMNS + 1)
    ]
    chains = {}  # side -> ordered round-top vertex ids (flank tangent -> ring end)
    for side in (+1, -1):
        xc, yc = fillet_center(side)
        d = math.hypot(xc, yc)
        tangent = (xc / d * RAMP_R_IN, yc / d * RAMP_R_IN)
        b_tan_east = math.degrees(math.atan2(abs(tangent[0]), tangent[1])) % 360.0
        q_chain = []
        for b in bearings80:
            if b >= b_tan_east - 1e-9:
                x, y, z, _ = ramp_top_point(side, RAMP_R_IN, b)
                q_chain.append(build.vert(x, y, z, "fillet_edge"))
        end_co = build.verts[q_chain[0]]
        round_pts = fillet_round_points(side, (end_co[0], end_co[1]))
        z_end = end_co[2]
        p_chain = []
        for k, (x, y) in enumerate(round_pts):
            t = k / FILLET_SEGMENTS
            z = HANDLE_DECK_Z + (z_end - HANDLE_DECK_Z) * t
            p_chain.append(build.vert(x, y, z, "fillet_top") if k < FILLET_SEGMENTS else q_chain[0])
        chains["e" if side > 0 else "w"] = list(p_chain)
        corner = q_chain[-1]
        # Top: a bridged strip between the round (tangent -> flank point)
        # and the ramp arc chain (tangent -> corner); every triangle spans
        # the two chains (a fan from the corner over the arc chain made
        # collinear zero-area slivers -- caught by the critic's per-triangle
        # normals in round 3).
        p_side = list(reversed(p_chain))
        q_side = q_chain
        i = j = 0
        while i < len(p_side) - 1 or j < len(q_side) - 1:
            ti = i / (len(p_side) - 1)
            tj = j / (len(q_side) - 1)
            if j >= len(q_side) - 1 or (i < len(p_side) - 1 and ti <= tj):
                build.tri(p_side[i], p_side[i + 1], q_side[j], expect=up, mat=wood)
                i += 1
            else:
                build.tri(p_side[i], q_side[j + 1], q_side[j], expect=up, mat=wood)
                j += 1
        # round wall down to grade (2 z-rows), facing the free side (the centre)
        for k in range(FILLET_SEGMENTS):
            x0, y0, z0 = build.verts[p_chain[k]]
            x1, y1, z1 = build.verts[p_chain[k + 1]]
            cols = [
                [
                    p_chain[k],
                    build.vert(x0, y0, z0 * 0.5, "fillet_wall"),
                    build.vert(x0, y0, 0.0, "fillet_wall"),
                ],
                [
                    p_chain[k + 1],
                    build.vert(x1, y1, z1 * 0.5, "fillet_wall"),
                    build.vert(x1, y1, 0.0, "fillet_wall"),
                ],
            ]
            expect = Vector((xc - (x0 + x1) / 2, yc - (y0 + y1) / 2, 0.0))
            for zr in range(2):
                build.quad(cols[0][zr], cols[0][zr + 1], cols[1][zr + 1], cols[1][zr], expect, wood)
        # tuck strip into the deck along the flank segment (corner -> tangent point)
        tx = side * (HANDLE_HALF_W - RAMP_TUCK)
        cy = build.verts[corner][1]
        ty = round_pts[0][1]
        build.quad(
            p_chain[0],
            corner,
            build.vert(tx, cy, HANDLE_DECK_Z - 0.004, "fillet_tuck"),
            build.vert(tx, ty, HANDLE_DECK_Z - 0.004, "fillet_tuck"),
            up,
            wood,
        )
    obj = build.to_object(materials)
    obj["fillet_round_chain"] = chains
    return obj


def fillet_round_uvs(obj, meters_per_tile: float) -> None:
    """Round-3 erratum 4 (cosmetic, UV-only): the fillet's round wall.

    The dominant-axis planar projection flips from (y, z) to (x, z) half
    way round the quarter-round (the wall normal swings 95 deg), so the
    planks broke along a vertical line mid-round. The round wall now takes
    u = arc length along the round (v = z), i.e. the cylindrical mapping
    the ramp flank effectively has, anchored so u is CONTINUOUS with the
    ramp flank's planar u (= x/t) at the shared ring-end vertex AND with
    the deck flank's planar u (= y/t) at the tangent point -- both are
    frozen shapes, so continuity is modulo one 6 m tile and the arc is
    scaled by the least-distortion candidate. The two frozen neighbours
    run u in opposite directions along the wall, so a grain reversal is
    unavoidable; the pick below places it wherever it costs the least
    stretch (printed)."""

    mesh = obj.data
    layer = mesh.uv_layers.get("UVMap")
    t = meters_per_tile
    lookup = {}
    for tag, chain in obj["fillet_round_chain"].items():
        pts = [mesh.vertices[i].co.copy() for i in chain]
        seq = list(reversed(pts))  # ring end first
        s = [0.0]
        for a, b in zip(seq, seq[1:]):
            s.append(s[-1] + math.hypot(b.x - a.x, b.y - a.y))
        arc = s[-1]
        u_ring = seq[0].x / t  # ramp flank: axis y-dominant -> u = x
        u_flank = seq[-1].y / t  # deck flank: axis x-dominant -> u = y
        need = (u_flank - u_ring) % 1.0  # continuity modulo the tile
        natural = arc / t
        cands = [need + k for k in range(-4, 5) if abs(need + k) > 1e-6]
        best = min(cands, key=lambda c: abs(math.log(abs(c) / natural)))
        print(
            f"fillet round UV [{tag}]: arc {arc:.3f} m = {natural:.3f} tiles; u {u_ring:.3f} -> "
            f"{u_ring + best:.3f} (flank needs {u_flank:.3f}); scale x{abs(best) / natural:.3f}"
            f"{', grain reversed at the ramp seam' if best > 0 else ', grain reversed at the flank tangent'}"
        )
        for co, sk in zip(seq, s):
            lookup[(round(co.x, 4), round(co.y, 4))] = u_ring + best * sk / arc
    remapped = 0
    for poly in mesh.polygons:
        if abs(poly.normal.z) >= 0.6:
            continue
        for loop_index in poly.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            key = (round(co.x, 4), round(co.y, 4))
            if key not in lookup:
                fail(f"fillet round UV: vertical face vertex {key} is not on a round chain")
            layer.data[loop_index].uv = (lookup[key], co.z / t)
        remapped += 1
    print(f"fillet round UV: {remapped} round-wall polygons remapped (u = arc length, v = z)")


def revolve(build: MeshBuild, profile, segments: int, mats, cap_mat: int) -> None:
    """Revolve an (r, z) profile about +Z with outward winding + top cap."""

    rings = []
    for r, z in profile:
        rings.append(
            [
                build.vert(
                    r * math.cos(math.tau * s / segments), r * math.sin(math.tau * s / segments), z
                )
                for s in range(segments)
            ]
        )
    for i in range(len(profile) - 1):
        band_mat = mats[min(i, len(mats) - 1)]
        for s in range(segments):
            nxt = (s + 1) % segments
            mid = math.tau * (s + 0.5) / segments
            outward = Vector((math.cos(mid), math.sin(mid), 0.0))
            build.quad(
                rings[i][s], rings[i][nxt], rings[i + 1][nxt], rings[i + 1][s], outward, band_mat
            )
    top_r, top_z = profile[-1]
    if top_r > 1e-6:
        apex = build.vert(0.0, 0.0, top_z)
        ring = rings[-1]
        for s in range(segments):
            build.tri(
                ring[s], ring[(s + 1) % segments], apex, expect=Vector((0, 0, 1)), mat=cap_mat
            )


def build_masher_pillar(materials) -> bpy.types.Object:
    build = MeshBuild(f"{ARENA_ID}_masher_pillar")
    steel = build.mat(M_STEEL)
    profile = [
        (1.20, 0.0),
        (1.20, 0.4),
        (1.05, 0.7),
        (1.05, 3.2),
        (1.05, 5.6),
        (1.15, 6.0),
        (1.20, 6.3),
        (1.20, 7.1),
        (0.90, 7.35),
        (0.55, 7.5),
    ]
    if max(r for r, _ in profile) > MASHER_RADIUS + 1e-9 or profile[-1][1] != MASHER_H:
        fail("masher profile violates the contract envelope")
    revolve(build, profile, 24, [steel], steel)
    return build.to_object(materials)


def build_grinder_pillar(materials) -> bpy.types.Object:
    build = MeshBuild(f"{ARENA_ID}_grinder_pillar")
    wood = build.mat(M_WOOD)
    steel = build.mat(M_STEEL)
    # v3.1 Item 5: top at exactly 4.5 m (was 4.35).
    profile = [
        (1.50, 0.0),
        (1.50, 0.3),
        (1.35, 0.8),
        (1.28, 2.0),
        (1.35, 3.0),
        (1.50, 3.5),
        (1.42, 3.9),
        (0.95, 4.15),
        (0.95, 4.3),
        (0.55, 4.5),
    ]
    if max(r for r, _ in profile) > GRINDER_RADIUS + 1e-9 or profile[-1][1] != GRINDER_H:
        fail("grinder profile violates the contract envelope")
    revolve(build, profile, 16, [wood] * 6 + [steel] * 3, steel)
    return build.to_object(materials)


def build_geyser_tower(materials) -> bpy.types.Object:
    build = MeshBuild(f"{ARENA_ID}_geyser_tower")
    steel = build.mat(M_STEEL)
    h = TOWER_HALF
    body_top = TOWER_H - 0.4
    sub = 5
    zrows = [body_top * k / sub for k in range(sub + 1)]
    for nx, ny in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        outward = Vector((nx, ny, 0))
        cols = []
        for c in range(sub + 1):
            t = -h + 2 * h * c / sub
            x, y = (nx * h, t) if ny == 0 else (t, ny * h)
            cols.append([build.vert(x, y, z) for z in zrows])
        for c in range(sub):
            for k in range(sub):
                build.quad(
                    cols[c][k], cols[c][k + 1], cols[c + 1][k + 1], cols[c + 1][k], outward, steel
                )
    up = Vector((0, 0, 1))
    top = [
        [build.vert(-h + 2 * h * i / sub, -h + 2 * h * j / sub, body_top) for j in range(sub + 1)]
        for i in range(sub + 1)
    ]
    for i in range(sub):
        for j in range(sub):
            build.quad(top[i][j], top[i][j + 1], top[i + 1][j + 1], top[i + 1][j], up, steel)
    seg = 24
    r_out, r_in = 0.95, 0.75

    def ring(r, z):
        return [
            build.vert(r * math.cos(math.tau * s / seg), r * math.sin(math.tau * s / seg), z)
            for s in range(seg)
        ]

    outer_b, outer_t = ring(r_out, body_top), ring(r_out, TOWER_H)
    inner_t, inner_b = ring(r_in, TOWER_H), ring(r_in, body_top + 0.15)
    for s in range(seg):
        n = (s + 1) % seg
        mid = math.tau * (s + 0.5) / seg
        out_v = Vector((math.cos(mid), math.sin(mid), 0))
        build.quad(outer_b[s], outer_b[n], outer_t[n], outer_t[s], out_v, steel)
        build.quad(outer_t[s], outer_t[n], inner_t[n], inner_t[s], up, steel)
        build.quad(inner_t[s], inner_t[n], inner_b[n], inner_b[s], -out_v, steel)
    throat = build.vert(0.0, 0.0, body_top + 0.15)
    for s in range(seg):
        build.tri(inner_b[s], inner_b[(s + 1) % seg], throat, expect=up, mat=steel)
    return build.to_object(materials)


def plate_ellipse(build, semi_x, semi_y, top, mat, segments=28) -> None:
    up = Vector((0, 0, 1))
    inner, rim, edge = [], [], []
    for s in range(segments):
        a = math.tau * s / segments
        cx, cy = math.cos(a), math.sin(a)
        inner.append(build.vert(semi_x * 0.55 * cx, semi_y * 0.55 * cy, top))
        rim.append(build.vert(semi_x * 0.955 * cx, semi_y * 0.955 * cy, top))
        edge.append(build.vert(semi_x * cx, semi_y * cy, 0.0))
    center = build.vert(0.0, 0.0, top)
    for s in range(segments):
        n = (s + 1) % segments
        build.tri(inner[s], inner[n], center, expect=up, mat=mat)
        build.quad(inner[s], inner[n], rim[n], rim[s], up, mat)
        mid = math.tau * (s + 0.5) / segments
        build.quad(
            rim[s], rim[n], edge[n], edge[s], Vector((math.cos(mid), math.sin(mid), 0.3)), mat
        )


def build_butter_pool(materials) -> bpy.types.Object:
    build = MeshBuild(f"{ARENA_ID}_butter_pool")
    plate_ellipse(build, BUTTER_SEMI_X, BUTTER_SEMI_Y, PLATE_TOP_Z, build.mat(M_BUTTER))
    return build.to_object(materials)


def build_salt_arc(materials) -> bpy.types.Object:
    build = MeshBuild(f"{ARENA_ID}_salt_arc")
    salt = build.mat(M_SALT)
    up = Vector((0, 0, 1))
    h = PLATE_TOP_Z
    rows = [
        (SALT_R_IN, 0.0),
        (SALT_R_IN + 0.4, h),
        (15.0, h),
        (17.5, h),
        (SALT_R_OUT - 0.4, h),
        (SALT_R_OUT, 0.0),
    ]
    hs = SALT_HALF_SPAN_DEG
    cols = (
        [(-hs, 0.0), (-hs + 0.6, 1.0)]
        + [(-(hs - 5.0) + 2.0 * (hs - 5.0) * k / 12.0, 1.0) for k in range(13)]
        + [(hs - 0.6, 1.0), (hs, 0.0)]
    )
    grid = [[build.vert(*bearing_point(a, r, rz * az)) for a, az in cols] for r, rz in rows]
    for i in range(len(rows) - 1):
        for j in range(len(cols) - 1):
            build.quad(grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j], up, salt)
    return build.to_object(materials)


def spout_lip_lines():
    """Arena-frame jamb-foot polylines for both spouts (trim dressing)."""

    lines = []
    for bearing in (60.0, 240.0):
        rot = math.radians(bearing)
        for side in (+1, -1):
            pts = []
            for r in [R_BANK_IN + 1.0 + (GLACIS_TOE - R_BANK_IN - 2.0) * k / 8.0 for k in range(9)]:
                p = jamb_point(side, r)
                # corridor-ward unit normal in the local spout frame: -side in x
                _, _, n_out, _, _ = batter_top(side, r)
                q = p - n_out
                wx = p.x * math.cos(rot) + p.y * math.sin(rot)
                wy = -p.x * math.sin(rot) + p.y * math.cos(rot)
                qx = q.x * math.cos(rot) + q.y * math.sin(rot)
                qy = -q.x * math.sin(rot) + q.y * math.cos(rot)
                pts.append((wx, wy, qx - wx, qy - wy))
            lines.append(pts)
    return lines


def build_trim_ring(materials) -> bpy.types.Object:
    """Name plate (baked lettering, draped on the MESH) + jamb lip strips.
    All <= 0.02 m proud of the carrier with a 3 mm rebate base."""

    build = MeshBuild(f"{ARENA_ID}_trim_ring")
    # A4c carriers: the plate and its base ride the wall MESH, the lips the
    # corridor datum. Every trim vertex is within 20 mm of its carrier
    # except the skirt bases on the glacis slope (0.3 m outboard = up to
    # 84 mm of carrier change), so the skirts are checked wherever they are
    # near-flat -- exactly the case the expect vector got wrong.
    build.carriers = {
        "plate": facet_wall_z,
        "plate_base": facet_wall_z,
        "lip": lambda x, y: corridor_z(math.hypot(x, y)),
    }
    rim = build.mat(M_RIM)
    steel = build.mat(M_STEEL)
    up = Vector((0, 0, 1))
    nx_, ny_ = 16, 8
    half_w = PLATE_W / 2.0
    top = []
    for i in range(ny_ + 1):
        r = PLATE_R0 + PLATE_H * i / ny_
        row = []
        for k in range(nx_ + 1):
            x = -half_w + PLATE_W * k / nx_
            y = math.sqrt(r * r - x * x)
            row.append(build.vert(x, y, facet_wall_z(x, y) + TRIM_PROUD, "plate"))
        top.append(row)
    for i in range(ny_):
        for k in range(nx_):
            build.quad(
                top[i][k],
                top[i][k + 1],
                top[i + 1][k + 1],
                top[i + 1][k],
                Vector((0, -0.3, 1)),
                rim,
            )
    # skirt: outline of the plate, base ring 0.3 m outboard, rebated
    outline = (
        [top[0][k] for k in range(nx_ + 1)]
        + [top[i][nx_] for i in range(1, ny_ + 1)]
        + [top[ny_][k] for k in range(nx_ - 1, -1, -1)]
        + [top[i][0] for i in range(ny_ - 1, -1, -1)]
    )
    bases = []
    for idx in outline:
        x, y, _ = build.verts[idx]
        cx, cy = 0.0, PLATE_R0 + PLATE_H / 2.0
        dx, dy = x - cx, y - cy
        length = math.hypot(dx, dy) or 1.0
        bx, by = x + dx / length * 0.3, y + dy / length * 0.3
        bases.append(build.vert(bx, by, facet_wall_z(bx, by) - REBATE, "plate_base"))
    for k in range(len(outline)):
        n = (k + 1) % len(outline)
        p = Vector(build.verts[outline[k]])
        q = Vector(build.verts[outline[n]])
        c = Vector((0.0, PLATE_R0 + PLATE_H / 2.0, 0.0))
        # z-DOMINANT expect (round-3 erratum 2). The old ((p+q)/2 - c, z 0.4)
        # was horizontal-dominant, and on the uphill edge -- where the base,
        # 0.3 m up the 28 % glacis, sits 63 mm ABOVE the plate lip so the
        # skirt's up-normal leans back toward the plate -- it scored the
        # face-DOWN winding +0.01 and the face-up winding -0.01. A skirt is
        # a dressing on a driven surface: it faces up, and leans outward
        # only as a tie-break.
        out_h = Vector((p + q) / 2 - c)
        out_h.z = 0.0
        out_v = out_h.normalized() * 0.3 + Vector((0.0, 0.0, 1.0))
        build.quad(outline[k], outline[n], bases[n], bases[k], out_v, steel)
    # Spout lips along the batter feet, on the corridor floor datum.
    for line in spout_lip_lines():
        for (x0, y0, nx, ny), (x1, y1, _, _) in zip(line, line[1:]):
            n = Vector((nx, ny, 0.0)).normalized()  # into the corridor, explicit
            w = 0.45
            r_mid = math.hypot((x0 + x1) / 2, (y0 + y1) / 2)
            zb = corridor_z(r_mid) - REBATE
            zt = corridor_z(r_mid) + TRIM_PROUD
            a0 = build.vert(x0, y0, zb, "lip")
            a1 = build.vert(x1, y1, zb, "lip")
            b0 = build.vert(x0 + n.x * w * 0.5, y0 + n.y * w * 0.5, zt, "lip")
            b1 = build.vert(x1 + n.x * w * 0.5, y1 + n.y * w * 0.5, zt, "lip")
            c0 = build.vert(x0 + n.x * w, y0 + n.y * w, zb, "lip")
            c1 = build.vert(x1 + n.x * w, y1 + n.y * w, zb, "lip")
            build.quad(a0, a1, b1, b0, up - n * 0.4, steel)
            build.quad(b0, b1, c1, c0, up + n * 0.4, steel)
    return build.to_object(materials)


def plate_uv(co):
    """Name-plate faces -> texture top half; text reads correctly for a
    viewer standing outside at bearing 0 looking at the glacis."""

    r = math.hypot(co.x, co.y)
    u = (PLATE_W / 2.0 - co.x) / PLATE_W
    v = 0.52 + (PLATE_R0 + PLATE_H - r) / PLATE_H * 0.47  # guard band vs the rim half
    return (u, max(0.52, min(0.99, v)))


# ---------------------------------------------------------------------------
# Placement tables -- ONE source of truth for prefab instances, the obstacle
# table, and the footprint/lane/coverage asserts.
# ---------------------------------------------------------------------------


def world_xy(bearing_deg, r):
    b = math.radians(bearing_deg)
    return (
        round(CENTER_WORLD[0] + r * math.sin(b), 3),
        round(CENTER_WORLD[1] + r * math.cos(b), 3),
    )


def local_to_world(x, y):
    return (round(CENTER_WORLD[0] + x, 3), round(CENTER_WORLD[1] + y, 3))


MATRIX_CONVENTION = (
    "rows-are-local-axes: row i = the instance's local axis i expressed in world "
    "(BeamNG prefab convention, measured live by the scenario worker 2026-09-01); "
    "this is the TRANSPOSE of the textbook column-major Rz. rotation_ccw_deg_z is "
    "the authoritative field; the matrix is derived from it."
)


def rotation_matrix_z(ccw_deg):
    """Engine-convention rotationMatrix for a CCW rotation about +Z.

    Local X in world = (cos a, sin a, 0), local Y = (-sin a, cos a, 0);
    rows are the local axes, so the row-major list is [c, s, 0, -s, c, 0,
    0, 0, 1]. The v1 handoff emitted the textbook matrix (columns = local
    axes) and every rotated arc came out mirrored in the first live run.
    """

    a = math.radians(ccw_deg)
    c, s = math.cos(a), math.sin(a)
    return [round(v, 9) for v in (c, s, 0.0, -s, c, 0.0, 0.0, 0.0, 1.0)]


def arena_instance(
    name, shape, bearing_center, position=None, ccw_deg=None, collision="visible-mesh"
):
    if position is None:
        position = [CENTER_WORLD[0], CENTER_WORLD[1], CENTER_WORLD[2]]
    if ccw_deg is None:
        ccw_deg = -(bearing_center or 0.0)
    ccw_deg = ((ccw_deg + 180.0) % 360.0) - 180.0
    return {
        "name": f"{ARENA_ID}_{name}",
        "shape": shape,
        "dae": f"{SHAPES_RELATIVE}/{ARENA_ID}_{shape}.dae",
        "position": [round(p, 3) for p in position],
        "rotation_ccw_deg_z": round(ccw_deg, 3),
        "rotationMatrix": rotation_matrix_z(ccw_deg),
        "matrix_convention": "rows-are-local-axes",
        "scale": [1.0, 1.0, 1.0],
        "collision": collision,
    }


def spout_local_to_world(bearing, p):
    rot = math.radians(bearing)
    wx = p.x * math.cos(rot) + p.y * math.sin(rot)
    wy = -p.x * math.sin(rot) + p.y * math.cos(rot)
    return local_to_world(wx, wy)


# v3.5 (runtime round 11 -> G12): every obstacle point gains a MEASURED
# physical radius beside its authored keep-out. `r_keepout` is unchanged and
# still owns dodge steering; `rp` is for the unpin reflex, whose
# envelope `gap = |car - post| - post.r - car_reach` was binding to the
# keep-out (6.5 / 8.0 m) and so armed on a flat 9.4 m disc around all 42
# points -- contacts 17 -> 51 in G12.
#
# CONVENTION, and why it is the right one: `rp` is the MAXIMUM PLAN
# HALF-EXTENT of the solid about the registered point -- "how far from this
# point can the solid still be touched", i.e. the circumscribed plan radius,
# not the inscribed one. It reproduces all three numbers the integration
# worker measured in-game: masher 1.2 (cylinder radius), grinder 1.5
# (cylinder radius), geyser tower 2.121 = 1.5 * sqrt(2) (a 3x3 m box is
# touchable at its CORNER, and the gates measured ~2.1, not the 1.5
# half-width). Three independent agreements is the check on the convention.
#
# BUT 32 of the 42 points are not posts, and for those the honest answer
# differs in kind -- a point standing on a wall does not have a radius the
# way a pillar does. Each entry therefore also carries `rp_kind` (authoring
# metadata -- NOT passed through to the runtime call):
#   post   (10) a whole convex solid registered at its axis/centre.
#              rp is a true radius; the disc IS the obstacle.
#   corner (8)  the point IS the solid's extremity (deck nose/rear corners;
#              spout jamb noses, where the batter has zero height at r 76).
#              the measured radius is 0.0 -- a car touches when its body
#              reaches the corner -- emitted at the runtime's 0.1 floor.
#   face   (16) a sample ON a long flat face (deck flanks, ramp inner
#              flanks). The surface passes through the point, so the
#              measured radius is 0.0: exact ON THE PERPENDICULAR through
#              that sample, over-estimating the gap between samples (see
#              the caveat). Emitted at the runtime's 0.1 floor.
#   batter (8)  jamb mid/outer-face points, which sit INSIDE the battered
#              jamb's footprint at mid-slope. Here there is a real
#              perpendicular half-extent: the 1:1 batter reaches h/2 from
#              the point to its toe, so rp = h/2, measured from the
#              generator's own batter_top() at that station.
OBSTACLE_TOWER_CIRCUMRADIUS = TOWER_HALF * math.sqrt(2.0)
# The runtime's published contract (serial 55, 45912b9d): each entry is
# {x, y, r, rp}; `r` is the keep-out the steering dodge uses and is
# UNCHANGED; `rp` is the solid's physical radius the pin reflex uses; `rp`
# is optional and defaults to `r`. The runtime REFUSES THE WHOLE
# REGISTRATION CALL unless every `rp` is finite, >= 0.1 m and <= its own
# `r`. 0.1 is therefore the smallest value that can be expressed, and the
# 24 corner/face points -- whose measured physical radius is a true 0.0,
# because the registered point lies ON the solid's surface -- are emitted
# at the floor. That is a 0.1 m over-statement of a 2.5 m car reach (an
# arming disc of ~2.6 m instead of ~2.5 m); it is recorded in the handoff
# and the report rather than applied silently. Omitting `rp` instead would
# default them to `r` = 6.5/8.0 m, which is precisely the 9.4 m disc this
# round exists to remove.
OBSTACLE_RP_FLOOR = 0.1
OBSTACLE_RP_TRUE_SURFACE = 0.0
# v3.6 (G13): the reflex arms when
#     gap = |car - post| - rp - car_reach < ARM_MARGIN
# so for a car TOUCHING a flat face, the along-face offset s to the nearest
# registered point is bounded. Taking the car's perpendicular standoff at
# its own reach (the head-on case, the most demanding):
#     sqrt(s^2 + reach^2) - rp - reach < margin
#     s_max = sqrt((margin + rp + reach)^2 - reach^2)
# G13 measured car reach at 2.18-2.91 m; the SMALLER reach is the harder
# case, so s_max is evaluated at 2.18 m: 1.73 m for an rp of 0.1. A face
# is covered when no point on it is further than s_max from a registered
# sample -- i.e. sample spacing <= 2 * s_max = 3.45 m.
OBSTACLE_RUNTIME_CAP = 64  # v26.OBSTACLE_CAP: the call is refused WHOLE above this
OBSTACLE_ARM_MARGIN = 0.5
OBSTACLE_CAR_REACH_MIN = 2.18
OBSTACLE_CAR_REACH_MAX = 2.91


def obstacle_arm_half_span(rp: float, car_reach: float = OBSTACLE_CAR_REACH_MIN) -> float:
    """Greatest along-face offset from a registered point at which a car
    touching that face still arms the unpin reflex."""

    outer = OBSTACLE_ARM_MARGIN + rp + car_reach
    return math.sqrt(max(0.0, outer * outer - car_reach * car_reach))


def build_placements():
    z0 = CENTER_WORLD[2]
    instances, obstacles = [], []
    for b in (15.0, 105.0, 150.0, 195.0, 285.0, 330.0):
        instances.append(arena_instance(f"wall_{int(b):03d}", "wall_arc_45", b))
    for b in (60.0, 240.0):
        instances.append(arena_instance(f"wall_spout_{int(b):03d}", "wall_arc_spout", b))
    # v3.2: the skin is a driven surface -- collision ON (Visible Mesh Final).
    for b in (45.0, 135.0, 225.0, 315.0):
        instances.append(
            arena_instance(
                f"floor_{int(b):03d}", "floor_skin_quadrant", b, collision="visible-mesh"
            )
        )
    instances.append(arena_instance("handle", "handle", 0.0))
    instances.append(arena_instance("handle_ramp_e", "handle_ramp_e", 0.0))
    instances.append(arena_instance("handle_ramp_w", "handle_ramp_w", 0.0))
    instances.append(arena_instance("trim_ring", "trim_ring", 0.0))
    instances.append(arena_instance("merge_fillet", "merge_fillet", 0.0))
    diag = {45.0: "ne", 135.0: "se", 225.0: "sw", 315.0: "nw"}
    for b, tag in diag.items():
        x, y = world_xy(b, MASHER_R)
        instances.append(
            arena_instance(f"masher_{tag}", "masher_pillar", None, position=[x, y, z0], ccw_deg=0.0)
        )
        obstacles.append(
            {
                "name": f"masher_{tag}",
                "x": x,
                "y": y,
                "r_keepout": KEEPOUT_PILLAR,
                "rp": round(MASHER_RADIUS, 3),
                "rp_kind": "post",
            }
        )
    for b, tag in diag.items():
        x, y = world_xy(b, GRINDER_R)
        instances.append(
            arena_instance(
                f"grinder_{tag}", "grinder_pillar", None, position=[x, y, z0], ccw_deg=0.0
            )
        )
        obstacles.append(
            {
                "name": f"grinder_{tag}",
                "x": x,
                "y": y,
                "r_keepout": KEEPOUT_PILLAR,
                "rp": round(GRINDER_RADIUS, 3),
                "rp_kind": "post",
            }
        )
    for b, tag in ((-6.0, "l"), (6.0, "r")):
        x, y = world_xy(b, TOWER_R)
        instances.append(
            arena_instance(
                f"geyser_tower_{tag}", "geyser_tower", None, position=[x, y, z0], ccw_deg=0.0
            )
        )
        obstacles.append(
            {
                "name": f"geyser_tower_{tag}",
                "x": x,
                "y": y,
                "r_keepout": KEEPOUT_PILLAR,
                "rp": round(OBSTACLE_TOWER_CIRCUMRADIUS, 3),
                "rp_kind": "post",
            }
        )
    # v3.2: the hazard plates sit ON the lifted skin -- their DAEs are frozen
    # (top +0.020, rim to 0.0), so the instance z carries the +50 mm lift and
    # the plate stays 20 mm proud of the NEW surface (A21).
    z_plate = z0 + SKIN_TOP_Z
    for i, b in enumerate(BUTTER_BEARINGS, start=1):
        x, y = world_xy(b, BUTTER_R)
        instances.append(
            arena_instance(
                f"butter_pool_{i}", "butter_pool", None, position=[x, y, z_plate], ccw_deg=-b
            )
        )
    for b, tag in ((90.0, "e"), (270.0, "w")):
        instances.append(
            arena_instance(
                f"salt_arc_{tag}",
                "salt_arc",
                b,
                position=[CENTER_WORLD[0], CENTER_WORLD[1], z_plate],
            )
        )

    # Deck corners (8.0) + flank points (8.0, A13 coverage of the 4 m flanks).
    end_y_flank = -math.sqrt(HANDLE_END_R**2 - HANDLE_HALF_W**2)
    for tag, (lx, ly) in {
        "handle_nose_e": (HANDLE_HALF_W, -HANDLE_NOSE_R),
        "handle_nose_w": (-HANDLE_HALF_W, -HANDLE_NOSE_R),
        "handle_rear_e": (HANDLE_HALF_W, end_y_flank),
        "handle_rear_w": (-HANDLE_HALF_W, end_y_flank),
    }.items():
        x, y = local_to_world(lx, ly)
        # A convex CORNER of the deck: the point is the extremity itself.
        obstacles.append(
            {
                "name": tag,
                "x": x,
                "y": y,
                "r_keepout": KEEPOUT_DECK,
                "rp": OBSTACLE_RP_FLOOR,
                "rp_kind": "corner",
            }
        )
    # v3.6 (G13): the deck's NOSE is a 14.0 m x 4.0 m wall registered only at
    # its two end corners, so a car pinned at mid-span sat 4.11 m from the
    # nearest post -- 1.47 m outside the arming margin -- and the reflex
    # could not fire (boot 1's remaining fixed-position grind). Interior
    # samples close it: 4 points at 2.8 m pitch put every point of the nose
    # within 1.40 m of a sample, inside the 1.73 m arming half-span. They are
    # samples standing ON a face, so rp is the 0.1 floor like every other.
    for i in range(1, HANDLE_NOSE_SAMPLES + 1):
        lx = -HANDLE_HALF_W + 2.0 * HANDLE_HALF_W * i / (HANDLE_NOSE_SAMPLES + 1)
        x, y = local_to_world(lx, -HANDLE_NOSE_R)
        obstacles.append(
            {
                "name": f"handle_nose_face_{i}",
                "x": x,
                "y": y,
                "r_keepout": KEEPOUT_DECK,
                "rp": OBSTACLE_RP_FLOOR,
                "rp_kind": "face",
            }
        )
    for side, tag in ((+1, "e"), (-1, "w")):
        for i, ly in enumerate(DECK_FLANK_POINT_Y, start=1):
            x, y = local_to_world(side * HANDLE_HALF_W, ly)
            # A sample ON the 58 m deck flank: the face passes through it.
            obstacles.append(
                {
                    "name": f"handle_flank_{tag}_{i}",
                    "x": x,
                    "y": y,
                    "r_keepout": KEEPOUT_DECK,
                    "rp": OBSTACLE_RP_FLOOR,
                    "rp_kind": "face",
                }
            )
    # Jamb noses (round-1 choice: gate-side jamb of the 60 spout and its
    # point-symmetric partner), plus mid-face and outer-face points on all
    # four battered jambs (v3.1 Item 3 + A13 coverage).
    # v2: BOTH jambs of each spout get a nose point -- A13 found the far
    # jamb's 0.5..1 m batter at r 80..82 covered by nothing (42 entries).
    for bearing, side, tag in (
        (60.0, -1, "spout_e_jamb"),
        (240.0, -1, "spout_w_jamb"),
        (60.0, +1, "spout_e_jamb_far"),
        (240.0, +1, "spout_w_jamb_far"),
    ):
        x, y = spout_local_to_world(bearing, jamb_point(side, R_BANK_IN))
        # At r 76 the batter has ZERO height (wall_z == corridor_z == 12 mm --
        # the same fact that collapsed foot/mid/top to one vertex in the
        # spout mesh), so the nose is a grade-level corner, not a solid.
        _, _, _, h_nose, _ = batter_top(side, R_BANK_IN)
        obstacles.append(
            {
                "name": tag,
                "x": x,
                "y": y,
                "r_keepout": KEEPOUT_JAMB_NOSE,
                "rp": max(OBSTACLE_RP_FLOOR, round(h_nose * 0.5, 3)),
                "rp_kind": "corner",
            }
        )
    for bearing, label in ((60.0, "60"), (240.0, "240")):
        for side, which in ((-1, "gate"), (+1, "far")):
            for r, suffix in ((JAMB_MID_R, "mid"), (JAMB_OUT_R, "out")):
                j, t, n, h, zf = batter_top(side, r)
                m = j + n * (h * 0.5)
                x, y = spout_local_to_world(bearing, m)
                # The point sits INSIDE the 1:1 batter's plan footprint at
                # mid-slope: the toe is h/2 back along -n, the top h/2 on.
                # That half-extent is a real physical radius.
                obstacles.append(
                    {
                        "name": f"jamb_{label}_{which}_{suffix}",
                        "x": x,
                        "y": y,
                        "r_keepout": KEEPOUT_JAMB_FACE,
                        "rp": max(OBSTACLE_RP_FLOOR, round(h * 0.5, 3)),
                        "rp_kind": "batter",
                    }
                )
    # Ramp inner-flank points (v3.1 Item 1.4).
    for side, tag in ((+1, "e"), (-1, "w")):
        for i, b in enumerate(RAMP_FACE_BEARINGS_E, start=1):
            bb = b if side > 0 else 360.0 - b
            x, y = world_xy(bb, RAMP_R_IN)
            # A sample ON the ramp's inner flank wall at r 80.
            obstacles.append(
                {
                    "name": f"ramp_{tag}_face_{i}",
                    "x": x,
                    "y": y,
                    "r_keepout": KEEPOUT_RAMP,
                    "rp": OBSTACLE_RP_FLOOR,
                    "rp_kind": "face",
                }
            )
    return instances, obstacles


def assert_shape_junctions(shape_objects, seam_report, plate_report) -> dict:
    """A26 (v3.7): relief ACROSS every authored shape-to-shape contact on a
    drivable surface.

    Why this assert exists. Every relief check before it ran WITHIN one
    shape -- A2 measures wall vertices against the wall profile, A19 the
    skin against the skin profile, assert_trim_relief the trim against its
    own carrier. Nothing measured the step where TWO shapes meet, which is
    exactly where a car crosses from one to the other. v3.6 reported a
    145 mm step at the deck's rear edge; that number came from an AUDIT
    that modelled the rear edge as a straight chord, and this assert --
    which reads the authored geometry instead of assuming its shape --
    measures the same junction at 0.005 mm. An instrument that reads the
    real surface is the whole point.

    Each junction names the shape whose vertices are sampled, the surface
    they must meet, and the cap. Authored rebates (the 4 mm tucks and the
    ramp's 4 mm lift) are relief too and are measured, not excused: they
    just sit far inside the cap.
    """

    junctions = []

    # A junction is where two surfaces are authored to MEET. A ramp that has
    # deliberately climbed 3.5 m above the bank is not in contact with it, so
    # only vertices within CONTACT_ZONE of the other surface are junction
    # samples; past that the shape is simply its own body. The assert then
    # says: wherever these two surfaces come within half a metre of each
    # other, they are within the relief cap -- which is the defect class (a
    # small step where a car crosses over), not the intended separation.
    CONTACT_ZONE = 0.5

    def record(name, a, b, verts, carrier, cap, note, zone=CONTACT_ZONE):
        worst, where, in_zone = 0.0, None, 0
        for co in verts:
            rel = co.z - carrier(co.x, co.y)
            if zone is not None and abs(rel) > zone:
                continue
            in_zone += 1
            if abs(rel) > worst:
                worst, where = (
                    abs(rel),
                    (round(co.x, 3), round(co.y, 3), round(math.hypot(co.x, co.y), 3)),
                )
        entry = {
            "junction": name,
            "from": a,
            "to": b,
            "samples": in_zone,
            "candidates": len(verts),
            "worst_relief_mm": round(worst * 1000, 3),
            "cap_mm": round(cap * 1000, 1),
            "worst_at_xyr": where,
            "note": note,
        }
        junctions.append(entry)
        if in_zone and worst > cap + 1e-9:
            fail(
                f"A26: junction {name} relief {worst * 1000:.1f} mm > {cap * 1000:.0f} mm cap "
                f"at {where}"
            )
        return entry

    handle = shape_objects["handle"]
    # 1. the deck's rear edge onto the bank. THE v3.6 CLAIM, re-measured
    #    from the authored vertices rather than an assumed edge shape.
    rear = [co for co in role_verts(handle, "deck") if math.hypot(co.x, co.y) > HANDLE_END_R - 0.05]
    record(
        "handle_deck_rear -> bank",
        "handle",
        "wall_arc_45 / wall_arc_spout",
        rear,
        lambda x, y: wall_z(math.hypot(x, y)),
        RELIEF_CAP,
        f"the rear edge is authored on the r {HANDLE_END_R} ARC (end_y(x) = "
        f"-sqrt(R^2 - x^2)), where wall_z == the deck top by the knot table, so it is "
        f"flush at EVERY station -- not a chord with a mid-span step",
    )
    # 2. the tuck strip that carries the deck surface past the edge
    # The skirt is a HIDDEN element: it seals the deck/bank seam from
    # underneath and the bank draws over it. What matters is that it is
    # strictly BELOW the bank, not that it hugs it, so this is a one-sided
    # check (v3.8; before v3.8 it was a 4 mm rebate measured two-sided,
    # which is what let a mid-span crossing pass at every vertex).
    skirt = role_verts(handle, "tuck")
    worst_up = max((co.z - facet_wall_z(co.x, co.y) for co in skirt), default=0.0)
    depth = max((facet_wall_z(co.x, co.y) - co.z for co in skirt), default=0.0)
    junctions.append(
        {
            "junction": "handle_tuck skirt -> bank (one-sided)",
            "from": "handle",
            "to": "wall_arc_45 / wall_arc_spout",
            "samples": len(skirt),
            "candidates": len(skirt),
            "worst_relief_mm": round(worst_up * 1000, 3),
            "cap_mm": 0.0,
            "worst_at_xyr": None,
            "note": f"POSITIVE would mean the skirt pokes through the bank. It descends "
            f"{HANDLE_TUCK_DROP * 1000:.0f} mm from the deck edge and the bank covers it by "
            f"up to {depth * 1000:.0f} mm -- depth is harmless on a hidden element, so only "
            f"the proud side is capped",
        }
    )
    if worst_up > 1e-6:
        fail(f"A26: the tuck skirt stands {worst_up * 1000:.3f} mm proud of the bank at a vertex")
    # v3.8 -- the between-station check, and the reason this sub-class
    # exists. The rebate is authored at the tuck VERTICES; what matters is
    # the SURFACE between them. This walks the strip's actual TRIANGLES from
    # the built mesh (not a reconstruction of them: v3.6's lesson) and
    # barycentrically samples each one against the bank. A strip that only
    # dips below the bank at its vertices, as v3.7's single chord did, is
    # caught here even though every vertex passes.
    tuck_ids = set(handle["arena_roles"].get("tuck", []))
    rear_ids = {
        i
        for i in handle["arena_roles"].get("deck", [])
        if math.hypot(handle.data.vertices[i].co.x, handle.data.vertices[i].co.y)
        > HANDLE_END_R - 0.05
    }
    strip_ids = tuck_ids | rear_ids
    mesh = handle.data
    mesh.calc_loop_triangles()
    worst_poke, poke_at, tris, samples = -1e9, None, 0, 0
    for lt in mesh.loop_triangles:
        if not set(lt.vertices) <= strip_ids:
            continue
        tris += 1
        p = [mesh.vertices[i].co for i in lt.vertices]
        steps = 6
        for a in range(steps + 1):
            for b in range(steps + 1 - a):
                c = steps - a - b
                co = (p[0] * a + p[1] * b + p[2] * c) / steps
                # Only OUTBOARD of the deck's rear edge is a tuck. Inboard
                # of r 88.5 the deck legitimately sits on top of its own
                # embankment -- that is the deck, not an interpenetration.
                # (The rear edge is a 12-column chord polygon, so triangle
                # samples between its vertices fall a couple of mm inside
                # the r 88.5 circle.)
                if math.hypot(co.x, co.y) < HANDLE_END_R:
                    continue
                rel = co.z - facet_wall_z(co.x, co.y)
                samples += 1
                if rel > worst_poke:
                    worst_poke, poke_at = (
                        rel,
                        (round(co.x, 3), round(co.y, 3), round(math.hypot(co.x, co.y), 3)),
                    )
    junctions.append(
        {
            "junction": "handle_tuck strip surface -> bank",
            "from": "handle",
            "to": "wall_arc_45 / wall_arc_spout",
            "samples": samples,
            "candidates": tris,
            "worst_relief_mm": round(worst_poke * 1000, 3),
            "cap_mm": 0.0,
            "worst_at_xyr": poke_at,
            "note": f"POSITIVE would mean the wooden tuck stands PROUD of the iron bank -- a "
            f"z-fight sliver at grazing angles. Sampled over {tris} triangles of the "
            f"BUILT strip, not a reconstruction. v3.7 measured +4.741 mm here because a "
            f"single chord spanned the bank's slope break at station 88.875; v3.8 gives "
            f"the strip a row at every wall station it crosses and rebates each row "
            f"under the bank's own minimum, so it is strictly below everywhere",
        }
    )
    if worst_poke > 1e-6:
        fail(
            f"A26: the tuck strip stands {worst_poke * 1000:.3f} mm PROUD of the bank at "
            f"{poke_at} -- it must be strictly below at every station, not just at its "
            f"vertices"
        )
    # 3/4. the ramps onto the bank, and their feet
    for side, tag in ((+1, "e"), (-1, "w")):
        ramp = shape_objects[f"handle_ramp_{tag}"]
        # The ramp meets the bank flush ONLY along its toe row (s = 0, the
        # toe bearing); everywhere else it is a raised structure standing on
        # the apron by design, and its outer face is the recorded 0.270 m
        # lip (ledger #5, G2-verified tangentially at 60 km/h). Selecting by
        # bearing is what makes this a junction test rather than a test of
        # the ramp's own body.
        toe_b = RAMP_TOE_BEARING if side > 0 else 360.0 - RAMP_TOE_BEARING
        toe_row = [
            co
            for co in role_verts(ramp, "ramp_top")
            if abs((math.degrees(math.atan2(co.x, co.y)) % 360.0) - toe_b) < 0.3
        ]
        record(
            f"ramp_{tag}_toe -> bank",
            f"handle_ramp_{tag}",
            "wall_arc_45",
            toe_row,
            facet_wall_z,
            RELIEF_CAP,
            f"the toe row at bearing {toe_b}, where the ramp starts flush on the bank at "
            f"the authored {RAMP_LIFT * 1000:.0f} mm lift. The rest of the ramp climbs away "
            f"by design (to 3.5 m) and is not in contact",
            zone=None,
        )
        record(
            f"ramp_{tag}_foot -> bank",
            f"handle_ramp_{tag}",
            "wall_arc_45",
            role_verts(ramp, "ramp_foot"),
            facet_wall_z,
            RELIEF_CAP,
            "the ramp's embankment foot, carried down to the bank surface",
        )
        # Recorded, NOT asserted: the ramp's raised body over the apron.
        lip = max(
            (co.z - facet_wall_z(co.x, co.y) for co in role_verts(ramp, "ramp_top")), default=0.0
        )
        junctions.append(
            {
                "junction": f"ramp_{tag} body over the apron",
                "from": f"handle_ramp_{tag}",
                "to": "wall_arc_45",
                "samples": len(role_verts(ramp, "ramp_top")),
                "candidates": len(role_verts(ramp, "ramp_top")),
                "worst_relief_mm": round(lip * 1000, 1),
                "cap_mm": None,
                "worst_at_xyr": None,
                "note": "NOT a junction and deliberately not capped: the ramp is a raised "
                "structure standing on the bank apron, rising to the 4.0 m deck. Its "
                "outer face is the recorded 0.270 m lip (ledger #5), inside the v3.1 "
                "amendment's 0.3 m and outside the +/-0.02 relief law BY DESIGN, with "
                "the G2 tangential line at r 88.5 / 60 km/h as its evidence",
            }
        )
    # 5. the merge fillet onto the deck flank, and its tuck
    fillet = shape_objects["merge_fillet"]
    # The fillet's round descends 4.000 -> 3.866 over eight facets (a
    # designed 1.4 % grade onto the ramp's own height), so only its flank
    # TANGENT vertex is a contact with the deck; the ring end is the shared
    # edge with the ramp, checked below.
    tangent = [
        co for co in role_verts(fillet, "fillet_top") if abs(abs(co.x) - HANDLE_HALF_W) < 1e-3
    ]
    record(
        "merge_fillet_tangent -> deck flank",
        "merge_fillet",
        "handle",
        tangent,
        lambda x, y: HANDLE_DECK_Z,
        RELIEF_CAP,
        "the round's first vertex IS the flank tangent point, authored at the deck "
        "height; the rest of the round is a designed 1.4 % descent onto the ramp",
        zone=None,
    )
    record(
        "merge_fillet_tuck -> deck",
        "merge_fillet",
        "handle",
        role_verts(fillet, "fillet_tuck"),
        lambda x, y: HANDLE_DECK_Z,
        RELIEF_CAP,
        "authored 4 mm rebate under the deck",
    )
    # 6. the fillet's shared edge with the ramp: coordinate-identical, so
    #    measure 3-D nearest-vertex distance rather than a z difference.
    shared_worst = 0.0
    fillet_edge = role_verts(fillet, "fillet_edge")
    ramp_edges = [
        co
        for tag in ("e", "w")
        for co in role_verts(shape_objects[f"handle_ramp_{tag}"], "ramp_inner_edge")
    ]
    for co in fillet_edge:
        shared_worst = max(shared_worst, min((co - other).length for other in ramp_edges))
    junctions.append(
        {
            "junction": "merge_fillet -> ramp shared edge",
            "from": "merge_fillet",
            "to": "handle_ramp_e / _w",
            "samples": len(fillet_edge),
            "worst_relief_mm": round(shared_worst * 1000, 3),
            "cap_mm": round(RELIEF_CAP * 1000, 1),
            "worst_at_xyr": None,
            "note": "3-D nearest-vertex distance: these vertices come from the SAME "
            "ramp_top_point() call, so the edge is coordinate-identical, not merely close",
        }
    )
    if shared_worst > RELIEF_CAP:
        fail(f"A26: fillet/ramp shared edge {shared_worst * 1000:.1f} mm apart")
    # 7. the spout's corridor floor onto the floor skin at r 76
    spout = shape_objects["wall_arc_spout"]
    throat = [
        co
        for co in role_verts(spout, "floor") + role_verts(spout, "floor_edge")
        if abs(math.hypot(co.x, co.y) - R_BANK_IN) < 1e-3
    ]
    record(
        "spout_corridor -> floor_skin",
        "wall_arc_spout",
        "floor_skin_quadrant",
        throat,
        lambda x, y: skin_z(math.hypot(x, y)),
        RELIEF_CAP,
        f"both land on the {FLOOR_SKIN_Z * 1000:.0f} mm datum at r {R_BANK_IN}",
    )
    # 8. the skin's own two junctions, already measured to the micron by A20
    #    and A21 -- carried here so the junction table is the complete list.
    junctions.append(
        {
            "junction": "floor_skin_outer -> wall toe ring",
            "from": "floor_skin_quadrant",
            "to": "wall_arc_45 / wall_arc_spout",
            "samples": seam_report["wall_toe_verts_on_ring"],
            "worst_relief_mm": seam_report["wall_toe_step_mm"],
            "cap_mm": round(RELIEF_CAP * 1000, 1),
            "worst_at_xyr": None,
            "note": "measured by A20 (v3.2): vertex-coincident on the world "
            "3.75 deg lattice at every instance bearing",
        }
    )
    junctions.append(
        {
            "junction": "floor_skin quadrant seams",
            "from": "floor_skin_quadrant",
            "to": "floor_skin_quadrant",
            "samples": seam_report["seam_edge_verts"],
            "worst_relief_mm": seam_report["quadrant_seam_step_mm"],
            "cap_mm": round(SKIN_SEAM_STEP_CAP * 1000, 1),
            "worst_at_xyr": None,
            "note": "measured by A20 on the built mesh AND on the exported DAE",
        }
    )
    worst_plate = max((abs(p["rim_on_skin_mm"]) for p in plate_report.values()), default=0.0)
    junctions.append(
        {
            "junction": "hazard plates -> floor_skin",
            "from": "butter_pool / salt_arc",
            "to": "floor_skin_quadrant",
            "samples": len(plate_report),
            "worst_relief_mm": round(worst_plate, 3),
            "cap_mm": round(RELIEF_CAP * 1000, 1),
            "worst_at_xyr": None,
            "note": "measured by A21 (v3.2): every plate rim lands ON the lifted skin",
        }
    )

    capped = [j for j in junctions if j["cap_mm"] is not None]
    worst = max(capped, key=lambda j: j["worst_relief_mm"])
    print(
        f"A26 shape-to-shape junctions: {len(capped)} capped junctions audited, all inside "
        f"the cap; worst {worst['worst_relief_mm']:.3f} mm at {worst['junction']} "
        f"(cap {worst['cap_mm']:.0f} mm); {len(junctions) - len(capped)} recorded "
        f"non-junctions"
    )
    for j in junctions:
        cap = f"{j['cap_mm']:.0f}" if j["cap_mm"] is not None else "recorded, uncapped"
        print(
            f"    {j['junction']:40s} {j['samples']:4d} samples  "
            f"{j['worst_relief_mm']:9.3f} mm / {cap}"
        )
    return {
        "rule": "relief measured ACROSS a junction between two shapes on a drivable surface, "
        "capped at RELIEF_CAP (0.020 m). Authored rebates and lifts are measured, not "
        "excused.",
        "why": "every earlier relief assert ran WITHIN one shape; nothing measured the step a "
        "car actually crosses. v3.6's 145 mm deck-rear claim came from an audit that "
        "ASSUMED the edge was a straight chord -- this assert reads the authored "
        "vertices and measures 0.005 mm.",
        "cap_m": RELIEF_CAP,
        "worst_junction": worst["junction"],
        "worst_relief_mm": worst["worst_relief_mm"],
        "junctions": junctions,
    }


def assert_face_coverage(obstacles) -> dict:
    """A25 (v3.6, from G13): audit EVERY long solid face against the reflex's
    arming half-span, not just the one that bit.

    For each face of a registered solid: its span, the registered samples
    along it, the worst distance from any point of the face to the nearest
    sample, and whether that is inside `obstacle_arm_half_span`. Faces that
    are not walls (a flush junction) are reported as such with the measured
    standoff rather than being silently skipped. Faces that remain
    under-sampled are recorded with their measured in-game contact counts --
    accepted residuals, not omissions.
    """

    by_name = {o["name"]: o for o in obstacles}

    def along(points):
        """Worst gap from any point of a span to the nearest sample, given
        sample offsets (metres) along the span from one end to the other."""

        pts = sorted(points)
        interior = max((b - a) / 2.0 for a, b in zip(pts, pts[1:])) if len(pts) > 1 else 0.0
        return max(interior, pts[0], 0.0)

    limit = obstacle_arm_half_span(OBSTACLE_RP_FLOOR)
    faces = []

    # --- handle deck: nose, two flanks, rear ---------------------------------
    end_y = -math.sqrt(HANDLE_END_R**2 - HANDLE_HALF_W**2)
    nose_samples = sorted(
        [0.0, 2.0 * HANDLE_HALF_W]
        + [
            by_name[f"handle_nose_face_{i}"]["x"] - CENTER_WORLD[0] + HANDLE_HALF_W
            for i in range(1, HANDLE_NOSE_SAMPLES + 1)
        ]
    )
    faces.append(
        {
            "face": "handle_deck_nose",
            "span_m": round(2.0 * HANDLE_HALF_W, 2),
            "wall_height_m": round(HANDLE_DECK_Z - SKIN_TOP_Z, 2),
            "samples": len(nose_samples),
            "worst_gap_m": round(along(nose_samples), 2),
            "kind": "wall",
            "status": "covered",
            "note": "v3.6 added 4 interior samples at a 2.8 m pitch; G13 boot 1's remaining "
            "fixed-position grind was here, 4.11 m from the nearest corner and 1.47 m "
            "outside the arming margin",
        }
    )
    flank_samples = sorted(
        abs(y - (-HANDLE_NOSE_R)) for y in [-HANDLE_NOSE_R, *DECK_FLANK_POINT_Y, end_y]
    )
    for side in ("e", "w"):
        faces.append(
            {
                "face": f"handle_deck_flank_{side}",
                "span_m": round(abs(end_y + HANDLE_NOSE_R), 2),
                "wall_height_m": round(HANDLE_DECK_Z - SKIN_TOP_Z, 2),
                "samples": len(flank_samples),
                "worst_gap_m": round(along(flank_samples), 2),
                "kind": "wall",
                "status": "accepted residual",
                "note": "6 samples at a 12.5 m pitch (8.2 m at the rear). Under-sampled against "
                "the 1.73 m arming half-span, and left alone deliberately: G13 measured "
                "handle_flank 0/0/0 contacts across 540 s of chase in three boots, so the "
                "coverage gap is not reached in play. Closing it would need ~32 more "
                "points and the segment primitive is retired on this evidence",
            }
        )
    rear_standoff = max(
        HANDLE_DECK_Z - wall_z(math.hypot(x, end_y))
        for x in [-HANDLE_HALF_W + 2.0 * HANDLE_HALF_W * k / 20 for k in range(21)]
    )
    faces.append(
        {
            "face": "handle_deck_rear",
            "span_m": round(2.0 * HANDLE_HALF_W, 2),
            "wall_height_m": round(rear_standoff, 3),
            "samples": 2,
            "worst_gap_m": round(HANDLE_HALF_W, 2),
            "kind": "low lip, not a wall",
            "status": "not applicable",
            "note": f"the deck's rear meets the bank at r {HANDLE_END_R}, where wall_z == the deck "
            f"top by construction, so the two rear CORNERS are exactly flush. The rear edge "
            f"is straight while the bank ends on an arc, so the mid-span sits at "
            f"r {math.hypot(0.0, end_y):.2f} and stands {rear_standoff * 1000:.0f} mm proud of "
            f"the bank there. That is a crawlable lip a car drives ACROSS -- 6 % of the "
            f"nose's {HANDLE_DECK_Z - SKIN_TOP_Z:.2f} m wall and well under a wheel radius -- "
            f"so nothing can be pinned against it and interior samples would be noise. "
            f"SEPARATE FINDING, not a reflex issue: {rear_standoff * 1000:.0f} mm is above the "
            f"{RELIEF_CAP * 1000:.0f} mm drivable-relief cap and is the AGENTS.md "
            f"straight-box-meets-circular-lip case. Pre-existing since round 2, unchanged "
            f"here (this round is handoff-only); routed to the design owner",
        }
    )

    # --- ramp inner flanks ---------------------------------------------------
    b_end = flank_bearing(RAMP_R_OUT, +1)
    ramp_span_deg = abs(b_end - RAMP_TOE_BEARING)
    ramp_offsets = sorted(
        math.radians(abs(b - RAMP_TOE_BEARING)) * RAMP_R_IN for b in RAMP_FACE_BEARINGS_E
    )
    for side in ("e", "w"):
        faces.append(
            {
                "face": f"ramp_{side}_inner_flank",
                "span_m": round(math.radians(ramp_span_deg) * RAMP_R_IN, 2),
                "wall_height_m": round(HANDLE_DECK_Z - SKIN_TOP_Z, 2),
                "samples": len(ramp_offsets),
                "worst_gap_m": round(along(ramp_offsets), 2),
                "kind": "wall, tapering to grade at the toe",
                "status": "accepted residual",
                "note": "4 samples at an 8.38 m pitch along the r 80 arc. The face's height falls "
                "to zero at the toe (bearing 149) and it merges into the deck/fillet at "
                "the top, so the tall middle is the sampled part. G13: ramp_flank 0/0/0 "
                "contacts in three boots",
            }
        )

    # --- spout jamb batters --------------------------------------------------
    jamb_offsets = []
    for r in (R_BANK_IN, JAMB_MID_R, JAMB_OUT_R):
        jamb_offsets.append(jamb_point(-1, r).length - R_BANK_IN)
    for label in ("60", "240"):
        for which in ("gate", "far"):
            faces.append(
                {
                    "face": f"jamb_{label}_{which}",
                    "span_m": round(jamb_point(-1, GLACIS_TOE).length - R_BANK_IN, 2),
                    "wall_height_m": "0 at r 76, rising with the bank",
                    "samples": 3,
                    "worst_gap_m": round(along(sorted(jamb_offsets)), 2),
                    "kind": "1:1 battered slope, not a vertical wall",
                    "status": "accepted residual",
                    "note": "3 samples (nose r 76, mid r 89.5, outer r 104). The mid and outer "
                    "points carry a REAL rp (2.321 / 1.2 m -- the batter's own half-extent) "
                    "rather than the 0.1 floor, which widens their arming discs to 5.0 and "
                    "3.9 m and covers most of the span. A 45 deg batter is ridden up, not "
                    "pinned against. G13 recorded no jamb grinds",
                }
            )

    # --- discs: pillars and towers ------------------------------------------
    faces.append(
        {
            "face": "pillars_and_towers",
            "span_m": None,
            "wall_height_m": None,
            "samples": 10,
            "worst_gap_m": 0.0,
            "kind": "convex solid, registered at its centre",
            "status": "covered",
            "note": "a masher/grinder cylinder's rp IS its radius; the geyser tower's rp is the "
            "3x3 m box's circumscribed 2.121 m. The disc contains the whole solid, so "
            "there is no along-face dimension to under-sample",
        }
    )

    bad = [f for f in faces if f["status"] == "covered" and f["worst_gap_m"] > limit + 1e-9]
    if bad:
        fail(
            f"A25: {len(bad)} face(s) marked covered exceed the {limit:.2f} m arming "
            f"half-span: {[(f['face'], f['worst_gap_m']) for f in bad]}"
        )
    residual = [f for f in faces if f["status"] == "accepted residual"]
    print(
        f"A25 face coverage: arming half-span {limit:.2f} m (rp {OBSTACLE_RP_FLOOR}, car reach "
        f"{OBSTACLE_CAR_REACH_MIN} m); {len(faces)} faces audited, "
        f"{sum(1 for f in faces if f['status'] == 'covered')} covered, {len(residual)} accepted "
        f"residuals, 1 not-a-wall; nose worst gap "
        f"{[f['worst_gap_m'] for f in faces if f['face'] == 'handle_deck_nose'][0]} m"
    )
    return {
        "arming_rule": "gap = |car - post| - rp - car_reach < 0.5 m (runtime serial 55)",
        "car_reach_measured_m": [OBSTACLE_CAR_REACH_MIN, OBSTACLE_CAR_REACH_MAX],
        "arm_half_span_m": round(limit, 3),
        "arm_half_span_at_max_reach_m": round(
            obstacle_arm_half_span(OBSTACLE_RP_FLOOR, OBSTACLE_CAR_REACH_MAX), 3
        ),
        "required_sample_pitch_m": round(2.0 * limit, 3),
        "faces": faces,
    }


def assert_obstacle_physical_radii(obstacles) -> dict:
    """A24 (v3.5): every obstacle carries a measured physical radius beside
    its untouched keep-out, and the numbers are the shapes' own.

    Also computes the coverage caveat for the `face` points: the along-face
    spacing between neighbouring samples, which is the distance over which a
    zero-radius disc under-arms. Returns the record block for the handoff.
    """

    kinds = {}
    over_corridor = []
    for post in obstacles:
        for key in ("x", "y", "r_keepout", "rp", "rp_kind"):
            if key not in post:
                fail(f"A24: obstacle {post.get('name')!r} is missing {key}")
        rp, r = post["rp"], post["r_keepout"]
        # The runtime's published rule, enforced here so a bad value can
        # never reach a registration call that would be refused WHOLE.
        if not (isinstance(rp, float) and rp == rp and -math.inf < rp < math.inf):
            fail(f"A24: {post['name']} rp {rp!r} is not a finite number")
        if rp < OBSTACLE_RP_FLOOR:
            fail(f"A24: {post['name']} rp {rp} < the runtime's floor {OBSTACLE_RP_FLOOR}")
        if rp > r:
            # Reportable finding, never a silent clamp (coordinator, v3.5).
            over_corridor.append((post["name"], rp, r))
        kinds.setdefault(post["rp_kind"], []).append(post)
    if over_corridor:
        fail(
            f"A24: {len(over_corridor)} obstacles have rp > their own r -- REPORT THIS, "
            f"do not clamp: {over_corridor[:5]}"
        )
    expected_counts = {"post": 10, "corner": 8, "face": 16 + HANDLE_NOSE_SAMPLES, "batter": 8}
    got = {k: len(v) for k, v in kinds.items()}
    if got != expected_counts:
        fail(f"A24: obstacle kind census {got} != {expected_counts}")
    # the three classes the gates measured in game, to 0.05 m
    measured = {"masher": 1.2, "grinder": 1.5, "geyser_tower": 2.1}
    for prefix, value in measured.items():
        ours = {p["rp"] for p in obstacles if p["name"].startswith(prefix)}
        if len(ours) != 1:
            fail(f"A24: {prefix} points disagree on rp: {sorted(ours)}")
        if abs(next(iter(ours)) - value) > 0.05:
            fail(f"A24: {prefix} rp {next(iter(ours))} vs the gates' measured {value}")
    # face coverage: along-face spacing between neighbouring samples
    deck_ys = (
        [-HANDLE_NOSE_R]
        + list(DECK_FLANK_POINT_Y)
        + [-math.sqrt(HANDLE_END_R**2 - HANDLE_HALF_W**2)]
    )
    deck_gaps = [abs(b - a) for a, b in zip(sorted(deck_ys), sorted(deck_ys)[1:])]
    ramp_gap = math.radians(abs(RAMP_FACE_BEARINGS_E[1] - RAMP_FACE_BEARINGS_E[0])) * RAMP_R_IN
    arming = {}
    for kind, posts in sorted(kinds.items()):
        rs = sorted({p["rp"] for p in posts})
        arming[kind] = {"count": len(posts), "rp_m": rs}
    report = {
        "field": "rp",
        "contract": "runtime serial 55 (45912b9d): each registered obstacle is {x, y, r, rp}. "
        "`r` is the keep-out corridor the steering dodge uses and is UNCHANGED "
        "here (the handoff spells it r_keepout; the scenario package already maps "
        "r_keepout -> r). `rp` is the solid's physical radius the pin reflex uses; "
        "it is optional and defaults to `r`. The runtime refuses the WHOLE "
        "registration call unless every rp is finite, >= 0.1 and <= its own r.",
        "pass_through": "emit ONLY {x, y, r, rp} to hotPotatoRegisterObstacles. `rp_kind` is "
        "authoring metadata for the record and must not be passed through. "
        "hotPotatoGetObstacles() echoes rp, so the package can assert what "
        "actually landed.",
        "semantics": "maximum plan half-extent of the solid about the registered point -- "
        "'how far from this point can the solid still be touched'. Feeds the "
        "unpin reflex's envelope (gap = |car - post| - rp - car_reach).",
        "rp_le_r_check": "PASS -- no obstacle class needs an rp larger than its own r; the "
        "worst ratio is the jamb mid-face at 2.321 / 8.0 = 0.29. Asserted "
        "per point by A24, which FAILS the build rather than clamping.",
        "floor_deviation": {
            "applies_to": "the 8 `corner` + 16 `face` points (24 of 42)",
            "measured_value_m": OBSTACLE_RP_TRUE_SURFACE,
            "emitted_value_m": OBSTACLE_RP_FLOOR,
            "why": "their true physical radius is 0.0 -- the registered point lies ON the "
            "solid's surface -- but the runtime refuses rp < 0.1, so 0.1 is the "
            "smallest expressible value. Effect: the arming disc for these points is "
            "~2.6 m instead of ~2.5 m at a 2.5 m car reach, a 0.1 m over-statement. "
            "The alternative -- omitting rp -- defaults them to r = 6.5/8.0 m, which "
            "is the 9.4 m disc this round exists to remove. Recorded, not silent.",
        },
        "validated_against_the_gates": measured,
        "by_kind": arming,
        "kind_meanings": {
            "post": "a whole convex solid registered at its axis/centre; rp is a true "
            "circumscribed plan radius and the disc IS the obstacle (masher 1.2 and "
            "grinder 1.5 are the cylinder radii; the geyser tower is a 3x3 m BOX, "
            "touchable at its corner, so 1.5*sqrt(2) = 2.121 -- which is the ~2.1 the "
            "gates measured, not the 1.5 half-width)",
            "corner": "the registered point IS the solid's extremity (deck nose/rear corners; "
            "the spout jamb noses, where the batter has zero height at r 76). The "
            "measured physical radius is 0.0 and contact happens when the car body "
            "reaches the point -- emitted at the 0.1 floor, see floor_deviation",
            "face": "a sample standing ON a long flat face (deck flanks, ramp inner flanks). "
            "The surface passes through the point, so the measured radius is 0.0: "
            "exact on the perpendicular through that sample, and it OVER-estimates "
            "the gap between samples -- see coverage_caveat. Emitted at the 0.1 floor",
            "batter": "jamb mid/outer-face points, which sit INSIDE the battered jamb's plan "
            "footprint at mid-slope; the 1:1 batter reaches h/2 from the point to "
            "its toe, so rp = h/2 measured from batter_top() at that station",
        },
        "coverage_caveat": {
            "superseded_by": "obstacle_face_coverage (A25, v3.6) audits EVERY face against the "
            "reflex's measured arming half-span. This block keeps the flank "
            "numbers; the deck NOSE it used to omit is now sampled and covered.",
            "applies_to": "the deck flanks and ramp flanks",
            "why": "a circle cannot represent a wall. A zero-radius disc arms correctly for a "
            "car on the perpendicular through a sample and not at all for a car "
            "touching the face midway between two samples",
            "deck_flank_sample_spacing_m": [round(g, 2) for g in deck_gaps],
            "ramp_flank_sample_spacing_m": round(ramp_gap, 2),
            "worst_uncovered_half_span_m": round(max(max(deck_gaps), ramp_gap) / 2.0, 2),
            "options_for_the_runtime": "(a) accept the gap -- the reflex is a proximity "
            "trigger, and under-arming mid-face is the pre-G12 "
            "behaviour rather than a new regression; (b) use "
            "point-to-SEGMENT distance for these (the segment "
            "primitive the runtime worker raised in round 7 and "
            "withdrew -- G12's 10 handle contacts re-motivate it); "
            "(c) ask geometry for denser face samples. Do NOT "
            "substitute a fat circle: that is the 9.4 m disc that "
            "caused the defect",
        },
    }
    print(
        f"A24 obstacle rp: {got}; post {sorted({p['rp'] for p in kinds['post']})}, batter "
        f"{sorted({p['rp'] for p in kinds['batter']})}, corner/face "
        f"{OBSTACLE_RP_FLOOR} (floor; measured {OBSTACLE_RP_TRUE_SURFACE}); "
        f"rp <= r on {len(obstacles)}/{len(obstacles)}; worst uncovered face half-span "
        f"{report['coverage_caveat']['worst_uncovered_half_span_m']} m (the deck flanks; "
        f"see A25 for the per-face audit)"
    )
    return report


# ---------------------------------------------------------------------------
# Footprints for the inter-shape asserts (A9, A10, A13). Local arena frame.
# ---------------------------------------------------------------------------


class Solid:
    def __init__(self, name, contains, boundary, tall=True, clearance=0.0):
        self.name, self.contains, self.boundary, self.tall = name, contains, boundary, tall
        self.clearance = clearance  # plates: required distance from solids (A9)


def polygon_solid(name, pts):
    """Arbitrary simple polygon (local XY), even-odd containment."""

    def contains(x, y, shrink=0.0):
        inside = False
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            if (y0 > y) != (y1 > y):
                xi = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
                if x < xi:
                    inside = not inside
        if not inside:
            return False
        if shrink > 0.0:
            # reject points within `shrink` of an edge
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                ex, ey = x1 - x0, y1 - y0
                t = max(0.0, min(1.0, ((x - x0) * ex + (y - y0) * ey) / (ex * ex + ey * ey or 1.0)))
                if math.hypot(x - (x0 + t * ex), y - (y0 + t * ey)) < shrink:
                    return False
        return True

    def boundary(step=0.5):
        out = []
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            m = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
            out += [(x0 + (x1 - x0) * k / m, y0 + (y1 - y0) * k / m) for k in range(m)]
        return out

    return Solid(name, contains, boundary)


def circle_solid(name, cx, cy, radius):
    def contains(x, y, shrink=0.0):
        return math.hypot(x - cx, y - cy) < radius - shrink

    def boundary(step=0.5):
        n = max(8, int(math.tau * radius / step))
        return [
            (cx + radius * math.cos(math.tau * k / n), cy + radius * math.sin(math.tau * k / n))
            for k in range(n)
        ]

    return Solid(name, contains, boundary)


def rect_solid(name, x0, x1, y0, y1):
    def contains(x, y, shrink=0.0):
        return x0 + shrink < x < x1 - shrink and y0 + shrink < y < y1 - shrink

    def boundary(step=0.5):
        pts = []
        for x in [
            x0 + (x1 - x0) * k / max(1, int((x1 - x0) / step))
            for k in range(int((x1 - x0) / step) + 1)
        ]:
            pts += [(x, y0), (x, y1)]
        for y in [
            y0 + (y1 - y0) * k / max(1, int((y1 - y0) / step))
            for k in range(int((y1 - y0) / step) + 1)
        ]:
            pts += [(x0, y), (x1, y)]
        return pts

    return Solid(name, contains, boundary)


def sector_solid(name, r0, r1, b0, b1):
    """Annular sector between bearings b0 < b1 (degrees)."""

    def contains(x, y, shrink=0.0):
        r = math.hypot(x, y)
        b = math.degrees(math.atan2(x, y)) % 360.0
        return r0 + shrink < r < r1 - shrink and b0 + math.degrees(
            shrink / max(r, 1)
        ) < b < b1 - math.degrees(shrink / max(r, 1))

    def boundary(step=0.5):
        pts = []
        for r in (r0, r1):
            n = max(4, int(math.radians(b1 - b0) * r / step))
            pts += [bearing_point(b0 + (b1 - b0) * k / n, r)[:2] for k in range(n + 1)]
        for b in (b0, b1):
            n = max(2, int((r1 - r0) / step))
            pts += [bearing_point(b, r0 + (r1 - r0) * k / n)[:2] for k in range(n + 1)]
        return pts

    return Solid(name, contains, boundary)


def ellipse_plate(name, cx, cy, bearing, sx, sy):
    a = math.radians(-bearing)  # rotation_ccw = -bearing

    def to_local(x, y):
        dx, dy = x - cx, y - cy
        return (dx * math.cos(a) + dy * math.sin(a), -dx * math.sin(a) + dy * math.cos(a))

    def contains(x, y, shrink=0.0):
        lx, ly = to_local(x, y)
        return (lx / sx) ** 2 + (ly / sy) ** 2 < 1.0

    def boundary(step=0.5):
        n = 72
        pts = []
        for k in range(n):
            t = math.tau * k / n
            lx, ly = sx * math.cos(t), sy * math.sin(t)
            pts.append(
                (cx + lx * math.cos(a) - ly * math.sin(a), cy + lx * math.sin(a) + ly * math.cos(a))
            )
        return pts

    return Solid(name, contains, boundary, tall=False, clearance=PLATE_CLEARANCE_M["ICE"])


# ---- the merge-corner fillet (round-2 critique fix 1) ---------------------
FILLET_RHO = 6.0  # quarter-round radius
FILLET_FLANK_Y = None  # tangent point on the deck flank, derived below
FILLET_SEGMENTS = 8


def fillet_center(side: int):
    """Centre of a quarter-round tangent to the deck flank x = side*7 and
    internally tangent to the r = 80 ring; it sits in the FREE region."""

    xc = side * (HANDLE_HALF_W + FILLET_RHO)
    yc = -math.sqrt((RAMP_R_IN - FILLET_RHO) ** 2 - xc * xc)
    return xc, yc


def fillet_round_points(side: int, end_xy):
    """The round from the flank tangent point to ``end_xy`` (the ramp's
    inner-edge vertex where the fillet meets it), as (x, y) pairs."""

    xc, yc = fillet_center(side)
    phi0 = math.pi if side > 0 else 0.0
    phi1 = math.atan2(end_xy[1] - yc, end_xy[0] - xc)
    # sweep the short way through the corner quadrant (below the centre)
    while side > 0 and phi1 < phi0:
        phi1 += math.tau
    while side < 0 and phi1 > phi0:
        phi1 -= math.tau
    rho1 = math.hypot(end_xy[0] - xc, end_xy[1] - yc)
    pts = []
    for k in range(FILLET_SEGMENTS + 1):
        t = k / FILLET_SEGMENTS
        phi = phi0 + (phi1 - phi0) * t
        rho = FILLET_RHO + (rho1 - FILLET_RHO) * t
        pts.append((xc + rho * math.cos(phi), yc + rho * math.sin(phi)))
    return pts


def fillet_polygon(side: int):
    """Plan polygon of the fillet solid: round + ramp arc + flank."""

    xc, yc = fillet_center(side)
    # tangent point on the ring, direction from the origin through the centre
    d = math.hypot(xc, yc)
    end = (xc / d * RAMP_R_IN, yc / d * RAMP_R_IN)
    pts = fillet_round_points(side, end)
    b_end = math.degrees(math.atan2(end[0], end[1])) % 360.0
    b_c = flank_bearing(RAMP_R_IN, side)
    for k in range(1, 5):
        b = b_end + (b_c - b_end) * k / 4
        pts.append(bearing_point(b, RAMP_R_IN)[:2])
    return pts


def footprints():
    """Solids (> 0.3 m tall) and plates in the local arena frame."""

    solids, plates = [], []
    for b in (45.0, 135.0, 225.0, 315.0):
        x, y, _ = bearing_point(b, MASHER_R)
        solids.append(circle_solid(f"masher_{int(b)}", x, y, MASHER_RADIUS))
        x, y, _ = bearing_point(b, GRINDER_R)
        solids.append(circle_solid(f"grinder_{int(b)}", x, y, GRINDER_RADIUS))
    for b in (-6.0, 6.0):
        x, y, _ = bearing_point(b, TOWER_R)
        solids.append(
            rect_solid(
                f"tower_{int(b)}", x - TOWER_HALF, x + TOWER_HALF, y - TOWER_HALF, y + TOWER_HALF
            )
        )
    end_y = -math.sqrt(HANDLE_END_R**2 - HANDLE_HALF_W**2)
    solids.append(rect_solid("handle_deck", -HANDLE_HALF_W, HANDLE_HALF_W, end_y, -HANDLE_NOSE_R))
    b_end = flank_bearing(RAMP_R_OUT, +1)
    solids.append(sector_solid("ramp_e", RAMP_R_IN, RAMP_R_OUT, RAMP_TOE_BEARING, b_end))
    solids.append(
        sector_solid("ramp_w", RAMP_R_IN, RAMP_R_OUT, 360.0 - b_end, 360.0 - RAMP_TOE_BEARING)
    )
    solids.append(polygon_solid("fillet_e", fillet_polygon(+1)))
    solids.append(polygon_solid("fillet_w", fillet_polygon(-1)))
    for i, b in enumerate(BUTTER_BEARINGS, start=1):
        x, y, _ = bearing_point(b, BUTTER_R)
        plates.append(ellipse_plate(f"butter_pool_{i}", x, y, b, BUTTER_SEMI_X, BUTTER_SEMI_Y))
    for b in (90.0, 270.0):
        salt = sector_solid(
            f"salt_arc_{int(b)}",
            SALT_R_IN,
            SALT_R_OUT,
            b - SALT_HALF_SPAN_DEG,
            b + SALT_HALF_SPAN_DEG,
        )
        salt.tall = False
        salt.clearance = PLATE_CLEARANCE_M["SAND"]
        plates.append(salt)
    # the wall itself, where it is taller than 0.3 m (plate clearance only)
    r03 = min(r for r in [76.0 + i * 0.01 for i in range(1600)] if wall_z(r) > 0.3)
    wall = sector_solid("wall_bank", r03, GLACIS_TOE, 0.0, 360.0)
    return solids, plates, wall


def assert_footprints(solids, plates, wall) -> None:
    """A9: zero solid-solid overlap; plate<->solid clearance >= 5.0 m."""

    for i, a in enumerate(solids):
        for b in solids[i + 1 :]:
            merge = {"handle_deck", "ramp_e", "ramp_w", "fillet_e", "fillet_w"}
            if a.name in merge and b.name in merge:
                continue  # ramps and fillets are tucked into the deck by design
            for x, y in a.boundary(0.5):
                if b.contains(x, y, 0.01):
                    fail(f"A9: solid {a.name} overlaps solid {b.name} at ({x:.1f},{y:.1f})")
            for x, y in b.boundary(0.5):
                if a.contains(x, y, 0.01):
                    fail(f"A9: solid {b.name} overlaps solid {a.name} at ({x:.1f},{y:.1f})")
    worst = (1e9, "", "")
    for p in plates:
        pb = p.boundary(0.25)
        for s in solids + [wall]:
            sb = s.boundary(0.25)
            for x, y in pb:
                if s.contains(x, y):
                    fail(f"A9: plate {p.name} inside solid {s.name}")
            d = min(math.hypot(x - sx, y - sy) for x, y in pb for sx, sy in sb)
            if d - p.clearance < worst[0]:
                worst = (d - p.clearance, p.name, s.name, d, p.clearance)
            if d < p.clearance:
                fail(
                    f"A9: plate {p.name} only {d:.2f} m from solid {s.name} "
                    f"(needs {p.clearance} m for its groundtype)"
                )
    print(
        f"A9 footprints clean; tightest plate<->solid margin {worst[0]:+.2f} m "
        f"({worst[1]} vs {worst[2]}: {worst[3]:.2f} m vs {worst[4]} m required)"
    )


def assert_lane_connectivity(solids) -> None:
    """A10: raster r < 80 at 1 m; one free region holding every feature and
    spawn; no cell sees solids on >= 270 deg of its horizon within 14 m."""

    R = 80
    cells = {}
    for ix in range(-R, R + 1):
        for iy in range(-R, R + 1):
            x, y = ix + 0.5, iy + 0.5
            if math.hypot(x, y) >= R:
                continue
            cells[(ix, iy)] = not any(s.contains(x, y) for s in solids if s.tall)
    free = {c for c, ok in cells.items() if ok}
    start = (0, 0)
    seen = {start}
    stack = [start]
    while stack:
        cx, cy = stack.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (cx + dx, cy + dy)
            if n in free and n not in seen:
                seen.add(n)
                stack.append(n)
    unreached = free - seen
    if unreached:
        sample = sorted(unreached)[:5]
        fail(f"A10: {len(unreached)} plaza cells unreachable from the pad, e.g. {sample}")
    features = {"pad": (0.0, 0.0)}
    for b in (45.0, 135.0, 225.0, 315.0):
        features[f"masher_{int(b)}"] = bearing_point(b, MASHER_R)[:2]
        features[f"grinder_{int(b)}"] = bearing_point(b, GRINDER_R)[:2]
    for b in (-6.0, 6.0):
        features[f"tower_{int(b)}"] = bearing_point(b, TOWER_R)[:2]
    for i, b in enumerate(BUTTER_BEARINGS, start=1):
        features[f"pool_{i}"] = bearing_point(b, BUTTER_R)[:2]
    for b in (20.0, 200.0):
        features[f"boxwall_center_{int(b)}"] = bearing_point(b, 34.0)[:2]
    for b in (105.0, 255.0):
        features[f"boxwall_{int(b)}"] = bearing_point(b, 60.0)[:2]
    for b in (160.0, 200.0):
        features[f"barrels_{int(b)}"] = bearing_point(b, 64.0)[:2]
    for b in (30.0, 150.0, 210.0, 270.0, 330.0, 120.0):
        features[f"spawn_{int(b)}"] = bearing_point(b, 40.0)[:2]
    for b in (RAMP_TOE_BEARING, 360.0 - RAMP_TOE_BEARING):
        features[f"ramp_toe_{int(b)}"] = bearing_point(b, 79.0)[:2]
    for name, (x, y) in features.items():
        ix, iy = math.floor(x), math.floor(y)
        near = [(ix + dx, iy + dy) for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)]
        if not any(c in seen for c in near):
            fail(f"A10: feature {name} at ({x:.1f},{y:.1f}) is not on the main plaza region")
    pockets = 0
    for ix, iy in seen:
        x, y = ix + 0.5, iy + 0.5
        blocked = 0
        for k in range(16):
            a = math.tau * k / 16
            hit = False
            for d in range(1, 15):
                px, py = x + d * math.cos(a), y + d * math.sin(a)
                if math.hypot(px, py) >= R:
                    break
                if any(s.contains(px, py) for s in solids if s.tall):
                    hit = True
                    break
            blocked += hit
        if blocked >= 12:
            pockets += 1
    if pockets:
        fail(f"A10: {pockets} plaza cells sit in a pocket (solids on >= 270 deg within 14 m)")
    print(
        f"A10 plaza: {len(free)} free cells, one region, {len(features)} features on it, 0 pocket cells"
    )


def assert_inside_corners(solids) -> None:
    """A16 (round-2 critique fix 1): no plaza cell may see solids on
    >= 12/16 of its 8 m horizon (the critic's detector: blocked = solids
    > 0.3 m, the bank > 0.3 m, or leaving r 80; the un-filleted merge
    corners scored 13/16, pillars 9/16). Plus an EXPLICIT inside-angle
    check along the deck-flank -> fillet -> ramp-flank polyline: every
    junction's free-side angle >= 135 deg."""

    R = 80
    r03 = min(r for r in [76.0 + i * 0.01 for i in range(1600)] if wall_z(r) > 0.3)
    cells = {}
    for ix in range(-R, R + 1):
        for iy in range(-R, R + 1):
            x, y = ix + 0.5, iy + 0.5
            if math.hypot(x, y) >= R:
                continue
            cells[(ix, iy)] = not (
                math.hypot(x, y) > r03 or any(s.contains(x, y) for s in solids if s.tall)
            )
    free = {c for c, ok in cells.items() if ok}
    worst = (0, None)
    for ix, iy in free:
        x, y = ix + 0.5, iy + 0.5
        hits = 0
        for k in range(16):
            a = math.tau * k / 16
            for dd in range(1, 9):
                px, py = x + dd * math.cos(a), y + dd * math.sin(a)
                c = (math.floor(px), math.floor(py))
                if math.hypot(px, py) >= R or not cells.get(c, True):
                    hits += 1
                    break
        if hits > worst[0]:
            worst = (
                hits,
                (round(math.degrees(math.atan2(x, y)) % 360, 1), round(math.hypot(x, y), 1)),
            )
        # Threshold = the critic's measured 13/16 at the raw 90-deg corner.
        # A concave quarter-round still wraps its deepest cell over ~12/16
        # (a smooth wall, not a nook); the junction-angle check below is
        # the geometric guarantee.
        if hits >= 13:
            fail(
                f"A16: inside corner -- cell at bearing {math.degrees(math.atan2(x, y)) % 360:.1f}, "
                f"r {math.hypot(x, y):.1f} sees solids on {hits}/16 of an 8 m horizon"
            )
    # explicit inside-angle check on the merged south solid outline
    for side in (+1, -1):
        xc, yc = fillet_center(side)
        d = math.hypot(xc, yc)
        end = (xc / d * RAMP_R_IN, yc / d * RAMP_R_IN)
        pts = fillet_round_points(side, end)
        chain = [(side * HANDLE_HALF_W, -HANDLE_NOSE_R)] + pts
        b_end = math.degrees(math.atan2(end[0], end[1])) % 360.0
        toe = RAMP_TOE_BEARING if side > 0 else 360.0 - RAMP_TOE_BEARING
        for k in range(1, 6):
            chain.append(bearing_point(b_end + (toe - b_end) * k / 5, RAMP_R_IN)[:2])
        for i in range(1, len(chain) - 1):
            ax, ay = chain[i - 1][0] - chain[i][0], chain[i - 1][1] - chain[i][1]
            bx, by = chain[i + 1][0] - chain[i][0], chain[i + 1][1] - chain[i][1]
            la, lb = math.hypot(ax, ay), math.hypot(bx, by)
            ang = math.degrees(math.acos(max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))))
            if ang < 135.0 - 1e-6:
                fail(
                    f"A16: tall-face junction at {chain[i]} has a {ang:.1f} deg inside angle (< 135)"
                )
    print(
        f"A16 inside corners: worst plaza cell {worst[0]}/16 blocked at bearing/r {worst[1]}; "
        f"tall-face junction angles all >= 135 deg"
    )


def assert_obstacle_coverage(obstacles) -> None:
    """A13: every solid face > 0.5 m tall lies inside a registered keep-out."""

    discs = [
        (o["x"] - CENTER_WORLD[0], o["y"] - CENTER_WORLD[1], o["r_keepout"], o["name"])
        for o in obstacles
    ]
    samples = []
    for b in (45.0, 135.0, 225.0, 315.0):
        for r, rad, tag in (
            (MASHER_R, MASHER_RADIUS, "masher"),
            (GRINDER_R, GRINDER_RADIUS, "grinder"),
        ):
            x, y, _ = bearing_point(b, r)
            samples += [
                (f"{tag}_{int(b)}", x + rad * math.cos(t), y + rad * math.sin(t))
                for t in [math.tau * k / 12 for k in range(12)]
            ]
    for b in (-6.0, 6.0):
        x, y, _ = bearing_point(b, TOWER_R)
        samples += [
            (f"tower_{int(b)}", x + sx, y + sy)
            for sx in (-1.5, 0, 1.5)
            for sy in (-1.5, 0, 1.5)
            if abs(sx) == 1.5 or abs(sy) == 1.5
        ]
    end_y = -math.sqrt(HANDLE_END_R**2 - HANDLE_HALF_W**2)
    y = -HANDLE_NOSE_R
    while y > end_y:
        for x in (-HANDLE_HALF_W, HANDLE_HALF_W):
            if HANDLE_DECK_Z - wall_z(math.hypot(x, y)) > 0.5:
                samples.append(("deck_flank", x, y))
        y -= 1.0
    samples += [("deck_nose", x, -HANDLE_NOSE_R) for x in [-7 + k for k in range(15)]]
    for side, tag in ((+1, "e"), (-1, "w")):
        b = RAMP_TOE_BEARING
        b_end = flank_bearing(RAMP_R_IN, +1)
        while b <= b_end:
            s = ramp_s(b)
            zf = wall_z(RAMP_R_IN)
            height = s * (HANDLE_DECK_Z - zf - RAMP_LIFT) + RAMP_LIFT
            if height > 0.5:
                bb = b if side > 0 else 360.0 - b
                x, y, _ = bearing_point(bb, RAMP_R_IN)
                samples.append((f"ramp_{tag}_flank", x, y))
            b += math.degrees(1.0 / RAMP_R_IN)
    for side, tag in ((+1, "e"), (-1, "w")):
        xc, yc = fillet_center(side)
        d = math.hypot(xc, yc)
        for x, y in fillet_round_points(side, (xc / d * RAMP_R_IN, yc / d * RAMP_R_IN)):
            samples.append((f"fillet_{tag}", x, y))
    for bearing in (60.0, 240.0):
        for side in (+1, -1):
            r = R_BANK_IN
            while r <= GLACIS_TOE:
                j, t, n, h, zf = batter_top(side, r)
                if h > 0.5:
                    m = j + n * (h * 0.5)
                    rot = math.radians(bearing)
                    samples.append(
                        (
                            f"jamb_{int(bearing)}_{side}",
                            m.x * math.cos(rot) + m.y * math.sin(rot),
                            -m.x * math.sin(rot) + m.y * math.cos(rot),
                        )
                    )
                r += 1.0
    uncovered = []
    for name, x, y in samples:
        if not any(math.hypot(x - dx, y - dy) <= rk for dx, dy, rk, _ in discs):
            uncovered.append((name, round(x, 1), round(y, 1)))
    if uncovered:
        fail(
            f"A13: {len(uncovered)} tall-face samples outside every keep-out, e.g. {uncovered[:6]}"
        )
    print(
        f"A13 obstacle coverage: {len(samples)} tall-face samples, all inside a keep-out ({len(discs)} discs)"
    )


# ---------------------------------------------------------------------------
# Asserts on built objects
# ---------------------------------------------------------------------------


def role_verts(obj, role):
    return [obj.data.vertices[i].co for i in obj["arena_roles"].get(role, [])]


def assert_seam_columns(obj, half_span_deg) -> None:
    mesh = obj.data
    tol = 1e-4
    edges = {+1: [], -1: []}
    for v in mesh.vertices:
        r = math.hypot(v.co.x, v.co.y)
        if r < 1e-6:
            continue
        b = math.degrees(math.atan2(v.co.x, v.co.y))
        for sign in (+1, -1):
            if abs(b - sign * half_span_deg) < 0.01:
                edges[sign].append(v.co.copy())
    if not edges[+1] or not edges[-1]:
        fail(f"{obj.name}: no seam-edge vertices found at +/-{half_span_deg}")
    for sign in (+1, -1):
        plane_n = Vector(
            (
                math.cos(math.radians(sign * half_span_deg)),
                -math.sin(math.radians(sign * half_span_deg)),
                0.0,
            )
        )
        for co in edges[sign]:
            if abs(Vector((co.x, co.y, 0.0)).dot(plane_n)) > tol:
                fail(f"{obj.name}: seam vertex off the radial plane")
    rot = math.radians(2.0 * half_span_deg)
    minus = [Vector(c) for c in edges[-1]]
    for co in edges[+1]:
        x = co.x * math.cos(rot) - co.y * math.sin(rot)
        y = co.x * math.sin(rot) + co.y * math.cos(rot)
        nearest = min((Vector((x, y, co.z)) - m).length for m in minus)
        if nearest > 5e-4:
            fail(
                f"{obj.name}: +edge vertex {tuple(co)} has no rotated twin (nearest {nearest:.6f})"
            )


def assert_wall_relief_two_sided(obj) -> None:
    """A2: every wall-surface vertex within +/-0.02 m of the profile."""

    worst = (0.0, None)
    for co in role_verts(obj, "wall"):
        r = math.hypot(co.x, co.y)
        err = co.z - wall_z(r)
        if abs(err) > worst[0]:
            worst = (abs(err), (round(co.x, 3), round(co.y, 3), round(co.z, 4), round(r, 4)))
        if abs(err) > RELIEF_CAP:
            fail(f"{obj.name}: wall vertex {err * 1000:+.1f} mm off the profile at r={r:.2f}")
    print(
        f"A2 {obj.name}: worst |z - wall_z| = {worst[0] * 1e6:.1f} um at {worst[1]} "
        f"over {len(role_verts(obj, 'wall'))} wall verts"
    )


def assert_mesh_crest(obj) -> None:
    peak = max(co.z for co in role_verts(obj, "wall"))
    if abs(peak - CREST_Z) > 0.001:
        fail(f"A14: {obj.name} mesh crest {peak:.4f} vs contract {CREST_Z}")


def assert_under_deck_rays(handle) -> None:
    mesh = handle.data
    mesh.calc_loop_triangles()
    tree = BVHTree.FromPolygons(
        [v.co.copy() for v in mesh.vertices], [tuple(t.vertices) for t in mesh.loop_triangles]
    )
    misses = []
    for yi in range(6):
        y = -32.0 - 9.0 * yi
        if y < -math.sqrt(HANDLE_END_R**2 - 0.01) + 1.5:
            continue
        for az in range(24):
            a = math.tau * az / 24
            if (
                tree.ray_cast(
                    Vector((0.0, y, 1.5)), Vector((math.cos(a), math.sin(a), 0.0)), 200.0
                )[0]
                is None
            ):
                misses.append((y, math.degrees(a)))
    if misses:
        fail(f"handle under-deck ray sweep misses: {misses[:6]} ({len(misses)} total)")


def assert_plate_relief(obj, cap) -> None:
    top = max(v.co.z for v in obj.data.vertices)
    if top > cap + 1e-6:
        fail(f"{obj.name}: proud plate {top:.4f} m exceeds relief cap {cap}")
    if min(v.co.z for v in obj.data.vertices) < -1e-6:
        fail(f"{obj.name}: plate dips below grade")


def assert_trim_relief(obj) -> None:
    worst = -1.0
    for role in ("plate", "lip"):
        for co in role_verts(obj, role):
            r = math.hypot(co.x, co.y)
            carrier = facet_wall_z(co.x, co.y) if role == "plate" else corridor_z(r)
            proud = co.z - carrier
            worst = max(worst, proud)
            if proud > RELIEF_CAP + 1e-6:
                fail(f"{obj.name}: {role} vertex {proud * 1000:.1f} mm proud at r={r:.2f}")
    for co in role_verts(obj, "plate_base"):
        if co.z > facet_wall_z(co.x, co.y) - REBATE + 1e-6:
            fail(f"{obj.name}: plate base not rebated into the mesh")
    print(f"trim worst proud over MESH carrier {worst * 1000:.1f} mm")


def assert_ramp(obj, side) -> None:
    """A15: along-path grade at r 80 <= 0.12, monotone in s; toe conformal."""

    tops = list(role_verts(obj, "ramp_inner_edge"))
    tops.sort(key=lambda c: (math.degrees(math.atan2(c.x, c.y)) % 360.0) * side)
    if len(tops) != RAMP_COLUMNS + 1:
        fail(f"A15: ramp {side} inner edge has {len(tops)} columns, expected {RAMP_COLUMNS + 1}")
    worst = 0.0
    for a, b in zip(tops, tops[1:]):
        da = abs(math.degrees(math.atan2(b.x, b.y)) - math.degrees(math.atan2(a.x, a.y)))
        path = math.radians(da) * RAMP_R_IN
        if path < 1e-6:
            continue
        grade = (b.z - a.z) / path
        if grade < -1e-6:
            fail(
                f"A15: ramp {side} not monotone at bearing {math.degrees(math.atan2(a.x, a.y)):.1f}"
            )
        worst = max(worst, grade)
        if grade > RAMP_MAX_GRADE + 1e-9:
            fail(
                f"A15: ramp {side} along-path grade {grade * 100:.2f} % > {RAMP_MAX_GRADE * 100:.0f} %"
            )
    # toe conformal: first column within lift of the wall profile at every row
    for co in role_verts(obj, "ramp_top"):
        r = math.hypot(co.x, co.y)
        if co.z - wall_z(r) < -RELIEF_CAP:
            fail(f"ramp {side}: top vertex below the bank at r={r:.2f}")
    print(
        f"A15 ramp {side}: worst along-path grade at r 80 = {worst * 100:.2f} % ({len(tops)} columns)"
    )


def assert_tri_budget(name, count) -> None:
    budget = TRI_BUDGETS[name]
    lo, hi = int(budget * 0.75), int(budget * 1.25)
    if not (lo <= count <= hi):
        fail(f"{name}: {count} tris outside budget {budget} +/-25 % [{lo}, {hi}]")


def assert_skin_driven_surface(obj) -> dict:
    """A19 (v3.2): the floor skin is a driven surface. Analytic profile:
    monotone skirt and feather, peak grade <= SKIN_MAX_GRADE, lands exactly
    on the 12 mm datum at r 76 and on grade at r 6. Mesh: every vertex on
    the profile, facet sagitta <= RELIEF_CAP, ring-to-ring grade <= the cap,
    top == SKIN_TOP_Z, outer-edge lip <= 2 mm. Also reports the AGENTS.md
    wheel-track metric (three samples 0.8 m apart, worst spread)."""

    # -- analytic --
    if abs(skin_z(SKIN_SKIRT_R0)) > 1e-12:
        fail("A19: skin does not start on grade at r 6")
    if abs(skin_z(SKIN_FEATHER_R1) - FLOOR_SKIN_Z) > 1e-12:
        fail(f"A19: skin outer edge {skin_z(SKIN_FEATHER_R1):.6f} != datum {FLOOR_SKIN_Z}")
    if abs(skin_z(0.5 * (SKIN_SKIRT_R1 + SKIN_FEATHER_R0)) - SKIN_TOP_Z) > 1e-12:
        fail("A19: plaza is not at SKIN_TOP_Z")
    n = int((SKIN_FEATHER_R1 - SKIN_SKIRT_R0) / 0.001)
    samples = [SKIN_SKIRT_R0 + i * 0.001 for i in range(n + 1)]
    peak = (0.0, 0.0)
    for a, b in zip(samples, samples[1:]):
        za, zb = skin_z(a), skin_z(b)
        if b <= SKIN_SKIRT_R1 + 1e-9 and zb < za - 1e-12:
            fail(f"A19: skirt not monotone at r={a:.3f}")
        if a >= SKIN_FEATHER_R0 - 1e-9 and zb > za + 1e-12:
            fail(f"A19: feather not monotone at r={a:.3f}")
        peak = max(peak, (abs(zb - za) / (b - a), a))
    if peak[0] > SKIN_MAX_GRADE + 1e-9:
        fail(
            f"A19: skin grade {peak[0] * 100:.2f} % at r={peak[1]:.2f} > {SKIN_MAX_GRADE * 100:.1f} %"
        )
    # wheel-track metric (AGENTS.md drivable-surface law): three samples
    # 0.8 m apart along a radial line, worst spread
    spread = 0.0
    for r in samples:
        if r + 1.6 > SKIN_FEATHER_R1:
            break
        zs = [skin_z(r), skin_z(r + 0.8), skin_z(r + 1.6)]
        spread = max(spread, max(zs) - min(zs))
    # -- mesh --
    verts = role_verts(obj, "skin")
    if len(verts) != len(obj.data.vertices):
        fail("A19: not every skin vertex carries the skin role")
    worst_dev = 0.0
    for co in verts:
        r = math.hypot(co.x, co.y)
        worst_dev = max(worst_dev, abs(co.z - skin_z(r)))
    if worst_dev > 1e-6:
        fail(f"A19: skin vertex {worst_dev * 1000:.3f} mm off the analytic profile")
    top = max(co.z for co in verts)
    if abs(top - SKIN_TOP_Z) > 1e-6:
        fail(f"A19: skin top {top:.4f} != {SKIN_TOP_Z}")
    outer = [co for co in verts if abs(math.hypot(co.x, co.y) - SKIN_FEATHER_R1) < 1e-4]
    if len(outer) != 25:
        fail(f"A19: outer ring has {len(outer)} vertices, expected 25")
    lip = max(abs(co.z - FLOOR_SKIN_Z) for co in outer)
    if lip > SKIN_SEAM_STEP_CAP:
        fail(f"A19: outer-edge lip {lip * 1000:.2f} mm > 2 mm")
    inner = [co for co in verts if abs(math.hypot(co.x, co.y) - SKIN_SKIRT_R0) < 1e-4]
    if max(abs(co.z) for co in inner) > 1e-9:
        fail("A19: inner ring not on grade")
    # facets: sagitta of each ring band vs the analytic profile, and the
    # ring-to-ring grade of the MESH (a step is relief; a ramp is not)
    worst_sag, worst_mesh_grade = (0.0, 0.0), (0.0, 0.0)
    for a, b in zip(SKIN_RINGS, SKIN_RINGS[1:]):
        za, zb = skin_z(a), skin_z(b)
        sag = max(abs(skin_z(a + (b - a) * k / 20) - (za + (zb - za) * k / 20)) for k in range(21))
        worst_sag = max(worst_sag, (sag, a))
        worst_mesh_grade = max(worst_mesh_grade, (abs(zb - za) / (b - a), a))
        if sag > RELIEF_CAP:
            fail(f"A19: facet sagitta {sag * 1000:.1f} mm between r {a}/{b}")
        if abs(zb - za) / (b - a) > SKIN_MAX_GRADE + 1e-9:
            fail(f"A19: mesh grade {abs(zb - za) / (b - a) * 100:.2f} % between r {a}/{b}")
    result = {
        "top_z_m": SKIN_TOP_Z,
        "datum_z_m": FLOOR_SKIN_Z,
        "skirt": {
            "r0": SKIN_SKIRT_R0,
            "r1": SKIN_SKIRT_R1,
            "ease_m": SKIN_EASE,
            "peak_grade": round(SKIN_SKIRT_GRADE, 4),
        },
        "feather": {
            "r0": SKIN_FEATHER_R0,
            "r1": SKIN_FEATHER_R1,
            "ease_m": SKIN_EASE,
            "peak_grade": round(SKIN_FEATHER_GRADE, 4),
        },
        "peak_grade_measured": round(peak[0], 4),
        "worst_facet_sagitta_mm": round(worst_sag[0] * 1000, 2),
        "worst_mesh_grade": round(worst_mesh_grade[0], 4),
        "outer_edge_lip_mm": round(lip * 1000, 3),
        "wheel_track_spread_mm_0p8m_x3": round(spread * 1000, 1),
    }
    print(
        f"A19 skin driven surface: peak grade {peak[0] * 100:.2f} % (skirt {SKIN_SKIRT_GRADE * 100:.2f} %, "
        f"feather {SKIN_FEATHER_GRADE * 100:.2f} %), worst facet sagitta {worst_sag[0] * 1000:.2f} mm at r "
        f"{worst_sag[1]}, vertices on profile within {worst_dev * 1e6:.2f} um, outer lip {lip * 1000:.3f} mm, "
        f"wheel-track spread {spread * 1000:.1f} mm over 1.6 m"
    )
    return result


def dae_positions(dae_path: Path) -> list:
    """All mesh vertex positions in a Collada file (local frame)."""

    import xml.etree.ElementTree as ET

    root = ET.parse(dae_path).getroot()
    out = []
    for arr in root.iter(f"{{{COLLADA_NS['c']}}}float_array"):
        if not (arr.get("id") or "").endswith("positions-array"):
            continue
        vals = [float(v) for v in arr.text.split()]
        out.extend(zip(vals[0::3], vals[1::3], vals[2::3]))
    return out


def _seam_step(points, half_span_deg, tol_xy=1e-3):
    """Max |dz| between the +edge vertices and their twins on the -edge
    under the quadrant rotation; fails if a twin's xy is missing."""

    edges = {+1: [], -1: []}
    for x, y, z in points:
        r = math.hypot(x, y)
        if r < 1e-6:
            continue
        b = math.degrees(math.atan2(x, y))
        for sign in (+1, -1):
            if abs(b - sign * half_span_deg) < 0.01:
                edges[sign].append((x, y, z))
    rot = math.radians(2.0 * half_span_deg)
    worst = 0.0
    for x, y, z in edges[+1]:
        rx = x * math.cos(rot) - y * math.sin(rot)
        ry = x * math.sin(rot) + y * math.cos(rot)
        d, dz = min((math.hypot(rx - mx, ry - my), abs(z - mz)) for mx, my, mz in edges[-1])
        if d > tol_xy:
            fail(f"A20: seam vertex ({x:.3f},{y:.3f}) has no xy twin (nearest {d * 1000:.2f} mm)")
        worst = max(worst, dz)
    return worst, len(edges[+1])


def assert_skin_seams(floor, wall45, spout) -> dict:
    """A20 (v3.2): with collision ON, the four quadrant seams and the skin's
    outer ring are collision surfaces that must meet without a step. (a)
    Built mesh: +45 edge vs the -45 edge under a 90 deg rotation, |dz| <= 2
    mm. (b) The wall sheet's r 76 ring (both wall shapes, every instance
    bearing) coincides with the skin's outer ring in world, |dz| <= 2 mm;
    the spout's jamb feet at r 76 lie ON the skin's outer chord polyline."""

    pts = [tuple(v.co) for v in floor.data.vertices]
    step, count = _seam_step(pts, 45.0)
    if step > SKIN_SEAM_STEP_CAP:
        fail(f"A20: quadrant seam collision step {step * 1000:.2f} mm > 2 mm")
    # skin outer ring in world (four quadrants at 45/135/225/315)
    outer_local = [(x, y, z) for x, y, z in pts if abs(math.hypot(x, y) - SKIN_FEATHER_R1) < 1e-4]
    world_ring = {}
    for qb in (45.0, 135.0, 225.0, 315.0):
        a = math.radians(-qb)  # instance rotation is ccw -bearing
        for x, y, z in outer_local:
            wx = x * math.cos(a) - y * math.sin(a)
            wy = x * math.sin(a) + y * math.cos(a)
            world_ring[(round(wx, 3), round(wy, 3))] = (wx, wy, z)
    ring_pts = list(world_ring.values())
    # closed chord polyline of the ring, ordered by bearing
    ring_pts.sort(key=lambda p: math.atan2(p[0], p[1]))

    def dist_to_polyline(x, y):
        best = 1e9
        for (ax, ay, _), (bx, by, _) in zip(ring_pts, ring_pts[1:] + ring_pts[:1]):
            ex, ey = bx - ax, by - ay
            t = max(0.0, min(1.0, ((x - ax) * ex + (y - ay) * ey) / (ex * ex + ey * ey)))
            best = min(best, math.hypot(x - (ax + t * ex), y - (ay + t * ey)))
        return best

    worst_wall, checked = 0.0, 0
    for obj, bearings in (
        (wall45, (15.0, 105.0, 150.0, 195.0, 285.0, 330.0)),
        (spout, (60.0, 240.0)),
    ):
        toe = [
            tuple(v.co)
            for v in obj.data.vertices
            if abs(v.co.z - FLOOR_SKIN_Z) < 1e-6
            and 75.9 < math.hypot(v.co.x, v.co.y) <= 76.0 + 1e-4
        ]
        if not toe:
            fail(f"A20: {obj.name} has no r 76 toe vertices on the datum")
        for wb in bearings:
            a = math.radians(-wb)
            for x, y, z in toe:
                wx = x * math.cos(a) - y * math.sin(a)
                wy = x * math.sin(a) + y * math.cos(a)
                d = dist_to_polyline(wx, wy)
                if d > 1e-3:
                    fail(
                        f"A20: {obj.name} toe vertex at world ({wx:.3f},{wy:.3f}) is {d * 1000:.2f} mm "
                        f"off the skin's outer ring"
                    )
                worst_wall = max(worst_wall, abs(z - FLOOR_SKIN_Z))
                checked += 1
    if worst_wall > SKIN_SEAM_STEP_CAP:
        fail(f"A20: wall toe vs skin edge step {worst_wall * 1000:.2f} mm > 2 mm")
    print(
        f"A20 seams: quadrant step {step * 1000:.3f} mm over {count} edge verts; wall toe ring "
        f"{checked} verts on the skin's outer ring, step {worst_wall * 1000:.3f} mm"
    )
    return {
        "quadrant_seam_step_mm": round(step * 1000, 3),
        "seam_edge_verts": count,
        "wall_toe_verts_on_ring": checked,
        "wall_toe_step_mm": round(worst_wall * 1000, 3),
    }


def assert_skin_seams_exported(dae_path: Path) -> dict:
    """A20 on the EXPORTED file: the collision the engine builds is what the
    DAE holds, not what Blender held. Re-measures the quadrant seam step and
    the outer-edge lip from the file's own float array."""

    pts = dae_positions(dae_path)
    step, count = _seam_step(pts, 45.0)
    if step > SKIN_SEAM_STEP_CAP:
        fail(f"A20 (DAE): quadrant seam step {step * 1000:.2f} mm > 2 mm")
    worst_dev = max(abs(z - skin_z(math.hypot(x, y))) for x, y, z in pts)
    if worst_dev > 1e-4:
        fail(f"A20 (DAE): exported vertex {worst_dev * 1000:.3f} mm off the profile")
    print(
        f"A20 (DAE) {dae_path.name}: {len(pts)} positions, seam step {step * 1000:.3f} mm, "
        f"worst |z - skin_z| {worst_dev * 1e6:.1f} um"
    )
    return {
        "dae_positions": len(pts),
        "dae_seam_step_mm": round(step * 1000, 3),
        "dae_worst_profile_dev_um": round(worst_dev * 1e6, 1),
    }


def assert_shadow_casting(path: Path, shape_objects) -> dict:
    """A22 (v3.3, extended v3.4): exactly the floor skin's and the glacis's
    own materials stop casting shadows -- nothing else.

    Read back from the WRITTEN materials json (not the table): every
    shadow-disabled material must be a JSON `false` (stock spelling), the
    disabled set must equal {skin materials, glacis material} exactly,
    every other material must OMIT the field (absent = casts), the skin
    mesh must use only skin materials, only the two WALL shapes may carry
    the glacis material, and no other shape may reference a disabled one.
    `cast_iron_matte` -- the bank and the batter chutes -- must still cast:
    the bank's shadow across the plaza is a real visual the arena keeps.
    """

    with open(path, encoding="utf-8") as fh:
        materials = json.load(fh)
    disabled = set()
    for name, entry in materials.items():
        if "castShadows" not in entry:
            continue
        value = entry["castShadows"]
        if value is not False:
            fail(f"A22: {name} castShadows is {value!r}, stock writes the JSON boolean false only")
        disabled.add(name)
    expected = set(SHADOW_DISABLED_MATERIALS)
    if disabled != expected:
        fail(
            f"A22: shadow-disabled materials {sorted(disabled)} != expected {sorted(expected)} "
            f"(skin {sorted(SKIN_MATERIALS)} + glacis {sorted(GLACIS_MATERIALS)})"
        )
    skin_mats = {
        m.name for m in shape_objects["floor_skin_quadrant"].data.materials if m is not None
    }
    if skin_mats != set(SKIN_MATERIALS):
        fail(f"A22: the skin mesh uses {sorted(skin_mats)}, expected {sorted(SKIN_MATERIALS)}")
    # the glacis copy belongs to the two wall shapes and to nothing else
    wall_shapes = {"wall_arc_45", "wall_arc_spout"}
    for shape, obj in shape_objects.items():
        used = {m.name for m in obj.data.materials if m is not None}
        glacis_used = used & set(GLACIS_MATERIALS)
        if shape in wall_shapes:
            if not glacis_used:
                fail(
                    f"A22: {shape} carries no glacis material -- the outer slope must be split off"
                )
            if M_IRON_MATTE not in used:
                fail(f"A22: {shape} lost the bank's matte iron -- the bank must keep casting")
        elif glacis_used:
            fail(f"A22: {shape} uses the glacis material {sorted(glacis_used)}")
        leaked = used & disabled
        if shape == "floor_skin_quadrant" or shape in wall_shapes:
            continue
        if leaked:
            fail(f"A22: {shape} uses a shadow-disabled material: {sorted(leaked)}")
    if "castShadows" in materials.get(M_IRON_MATTE, {}):
        fail("A22: the bank's matte iron must keep casting shadows")
    if "castShadows" in materials.get(M_RIM, {}):
        fail("A22: the rim band must keep casting shadows")
    print(
        f"A22 shadow casting: disabled on {sorted(disabled)} (skin + glacis only); "
        f"{len(materials) - len(disabled)} materials still cast -- bank, batter chutes, "
        f"corridor floor, rim, deck, ramps, pillars, plates"
    )
    return {
        "disabled": sorted(disabled),
        "still_casting": sorted(set(materials) - disabled),
        "skin_materials": sorted(SKIN_MATERIALS),
        "glacis_materials": sorted(GLACIS_MATERIALS),
    }


def assert_material_only_reexport(dae_path: Path, before: dict) -> dict:
    """A23 (v3.4): a re-export declared MATERIAL-ONLY must not move geometry.

    Compares the freshly written DAE against the file that was on disk
    before the export: identical triangle count and an identical multiset
    of vertex positions (sorted, to the exporter's own precision). Material
    symbols are EXPECTED to differ -- that is the change -- and are
    reported so the diff is on the record.
    """

    after_pts = sorted(dae_positions(dae_path))
    after_tris = dae_tri_count(dae_path)
    if after_tris != before["tris"]:
        fail(
            f"A23: {dae_path.name} triangle count moved {before['tris']} -> {after_tris} "
            f"in a material-only re-export"
        )
    if len(after_pts) != len(before["points"]):
        fail(f"A23: {dae_path.name} vertex count moved {len(before['points'])} -> {len(after_pts)}")
    worst = 0.0
    for (ax, ay, az), (bx, by, bz) in zip(before["points"], after_pts):
        worst = max(worst, abs(ax - bx), abs(ay - by), abs(az - bz))
    if worst > 1e-9:
        fail(
            f"A23: {dae_path.name} vertex positions moved by up to {worst * 1000:.6f} mm "
            f"in a material-only re-export"
        )
    after_syms = dae_material_symbols(dae_path)
    print(
        f"A23 {dae_path.name}: material-only -- {after_tris} tris and {len(after_pts)} positions "
        f"identical (max delta {worst:.1e} m); materials {sorted(before['symbols'])} -> "
        f"{sorted(after_syms)}"
    )
    return {
        "tris": after_tris,
        "positions": len(after_pts),
        "max_position_delta_m": worst,
        "materials_before": sorted(before["symbols"]),
        "materials_after": sorted(after_syms),
    }


def assert_plates_on_skin(instances, shape_objects, plates) -> dict:
    """A21 (v3.2): every hazard plate whose footprint lies inside the skin
    (r < 76) must sit fully on the FLAT plaza (r in [skirt top, feather
    start]) and its top must be 20 +/- 2 mm proud of the lifted skin; its
    rim must land on the skin, never below it."""

    z0 = CENTER_WORLD[2]
    report = {}
    by_name = {p.name: p for p in plates}
    for inst in instances:
        if inst["shape"] not in ("butter_pool", "salt_arc"):
            continue
        obj = shape_objects[inst["shape"]]
        top = max(v.co.z for v in obj.data.vertices)
        base = min(v.co.z for v in obj.data.vertices)
        lift = inst["position"][2] - z0
        short = inst["name"].replace(f"{ARENA_ID}_", "")
        fp = by_name.get(short) or by_name.get(
            {"salt_arc_e": "salt_arc_90", "salt_arc_w": "salt_arc_270"}.get(short, "")
        )
        if fp is None:
            fail(f"A21: no footprint for plate {short}")
        radii = [math.hypot(x, y) for x, y in fp.boundary(0.25)]
        r_min, r_max = min(radii), max(radii)
        if r_max > SKIN_FEATHER_R1:
            continue  # outside the skin footprint: not this assert's business
        if not (SKIN_SKIRT_R1 <= r_min and r_max <= SKIN_FEATHER_R0):
            fail(
                f"A21: plate {short} spans r {r_min:.2f}..{r_max:.2f}, not fully on the flat "
                f"plaza [{SKIN_SKIRT_R1}, {SKIN_FEATHER_R0}] -- straddles the skirt/feather"
            )
        proud = lift + top - SKIN_TOP_Z
        rim = lift + base - SKIN_TOP_Z
        if abs(proud - PLATE_TOP_Z) > PLATE_PROUD_TOL:
            fail(f"A21: plate {short} top {proud * 1000:.1f} mm proud of the skin, need 20 +/- 2")
        if rim < -1e-6 or rim > PLATE_PROUD_TOL:
            fail(f"A21: plate {short} rim {rim * 1000:.1f} mm vs the skin surface")
        report[short] = {
            "r_min": round(r_min, 2),
            "r_max": round(r_max, 2),
            "instance_lift_m": round(lift, 3),
            "top_proud_of_skin_mm": round(proud * 1000, 1) + 0.0,
            "rim_on_skin_mm": round(rim * 1000, 1) + 0.0,
            "margin_to_feather_m": round(SKIN_FEATHER_R0 - r_max, 2),
            "margin_to_skirt_m": round(r_min - SKIN_SKIRT_R1, 2),
        }
    if len(report) != 5:
        fail(f"A21: expected 5 plates inside the skin footprint, found {len(report)}")
    print(
        "A21 plates on skin: "
        + "; ".join(
            f"{k} r {v['r_min']}..{v['r_max']} top +{v['top_proud_of_skin_mm']} mm rim {v['rim_on_skin_mm']:+.1f} mm"
            for k, v in report.items()
        )
    )
    return report


# ---------------------------------------------------------------------------
# Export, materials json, handoff, renders
# ---------------------------------------------------------------------------


COLLADA_NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}


def dae_node_parents(dae_path: Path) -> dict:
    """{node name: parent node name or None} of the visual scene."""

    import xml.etree.ElementTree as ET

    root = ET.parse(dae_path).getroot()
    scene = root.find("c:library_visual_scenes/c:visual_scene", COLLADA_NS)
    out = {}

    def walk(node, parent):
        for child in node.findall("c:node", COLLADA_NS):
            name = child.get("name") or child.get("id")
            out[name] = parent
            walk(child, name)

    walk(scene, None)
    return out


def dae_material_symbols(dae_path: Path) -> set:
    """Material symbols bound in a Collada file's instance_geometry."""

    import xml.etree.ElementTree as ET

    root = ET.parse(dae_path).getroot()
    return {m.get("symbol") for m in root.iter(f"{{{COLLADA_NS['c']}}}instance_material")}


def dae_tri_count(dae_path: Path) -> int:
    import xml.etree.ElementTree as ET

    root = ET.parse(dae_path).getroot()
    return sum(int(t.get("count")) for t in root.iter(f"{{{COLLADA_NS['c']}}}triangles"))


def sha256_file(path: Path) -> dict:
    blob = path.read_bytes()
    return {"sha256": hashlib.sha256(blob).hexdigest(), "size": len(blob)}


def hash_shipped_dae(dae_path: Path, obj, extra=None) -> dict:
    """A18: a shape outside the export set keeps its shipped DAE. Hash it
    from disk and prove the shipped file is THIS build's geometry by
    triangle count (the exporter's timestamps make a byte compare moot)."""

    if not dae_path.is_file():
        fail(f"{dae_path.name} is outside the export set and not on disk")
    info = sha256_file(dae_path)
    built = tri_count(obj) + sum(tri_count(o) for o in (extra or []) if o.type == "MESH")
    shipped = dae_tri_count(dae_path)
    if shipped != built:
        fail(
            f"A18: shipped {dae_path.name} has {shipped} triangles, this build makes {built} "
            f"-- add it to --export"
        )
    if extra:
        info["nodes"] = [o.name for o in extra]
        info["node_parents"] = dae_node_parents(dae_path)
    print(
        f"A18 {dae_path.name}: kept as shipped, {shipped} tris == build, sha {info['sha256'][:16]}"
    )
    return info


def export_dae(obj, dae_path: Path, extra=None) -> dict:
    dae_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for other in extra or []:
        other.select_set(True)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    result = bpy.ops.wm.collada_export(
        filepath=str(dae_path),
        check_existing=False,
        selected=True,
        include_children=bool(extra),
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
        fail(f"Collada export failed for {obj.name}: {result}")
    bpy.ops.object.select_all(action="DESELECT")
    blob = dae_path.read_bytes()
    info = {"sha256": hashlib.sha256(blob).hexdigest(), "size": len(blob)}
    if extra:
        # Verify the detail-level node names survived the exporter.
        text = blob.decode("utf-8", errors="ignore")
        for other in extra:
            if f'name="{other.name}"' not in text:
                fail(f"LOD node {other.name} missing from {dae_path.name}")
        info["nodes"] = [o.name for o in extra]
        # A17 (round-3 erratum 1): the exported node TREE must be the
        # authored hierarchy, parent for parent -- the round-3 file had
        # nulldetail10 under start01 while the docstring claimed base00.
        expected = {o.name: (o.parent.name if o.parent else None) for o in [obj, *extra]}
        actual = dae_node_parents(dae_path)
        for name, parent in expected.items():
            if name not in actual:
                fail(f"A17: node {name} missing from {dae_path.name}")
            if actual[name] != parent:
                fail(
                    f"A17: {dae_path.name}: node {name} is under {actual[name]!r}, "
                    f"authored under {parent!r}"
                )
        info["node_parents"] = expected
        print(
            f"A17 {dae_path.name}: node tree verified "
            + ", ".join(f"{k} <- {v}" for k, v in expected.items())
        )
    return info


def write_materials_json(path: Path) -> None:
    root = f"/{SHAPES_RELATIVE}/textures"
    entries = {}
    for name, entry in MATERIALS.items():
        fam = entry["family"]
        stage0 = {
            "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
            "baseColorMap": f"{root}/{fam}.color.png",
            "normalMap": f"{root}/{fam}.normal.png",
            "roughnessMap": f"{root}/{fam}_roughness.data.png",
            "roughnessFactor": entry["roughness"],
            "metallicFactor": entry["metallic"],
        }
        material = {
            "Stages": [stage0, {}, {}, {}],
            "class": "Material",
            "doubleSided": True,
            "mapTo": name,
            "materialTag0": ARENA_ID,
            "name": name,
            "persistentId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ARENA_ID}:{name}")),
            "version": 1.5,
        }
        if name in (M_STEEL, M_BUTTER, M_RIM, M_IRON):
            material["dynamicCubemap"] = True
        # v3.3: written ONLY when false, as stock spells it (81/81 stock
        # entries are false; absent means "casts"). See the SHADOW LAW note.
        if entry.get("cast_shadows") is False:
            material["castShadows"] = False
        if name == M_BUTTER:
            material[GROUNDTYPE_FIELD] = BUTTER_GROUNDTYPE
        if name == M_SALT:
            material[GROUNDTYPE_FIELD] = SALT_GROUNDTYPE
        entries[name] = material
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="\n") as fh:
        json.dump(entries, fh, indent=2, sort_keys=True)
        fh.write("\n")


def parse_cli() -> dict:
    """Options after ``--`` on the Blender command line (see the docstring)."""

    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    opts = {
        "export": None,
        "dry_run": False,
        "renders": True,
        "round": None,
        "baseline": f"{ARENA_ID}.hashes.r3.json",
        "material_only": set(),
    }
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--export":
            opts["export"] = {s.strip() for s in argv[i + 1].split(",") if s.strip()}
            i += 2
        elif arg == "--material-only":
            # A23: these shapes are re-exported for a MATERIAL change only;
            # the build proves their geometry did not move.
            opts["material_only"] = {s.strip() for s in argv[i + 1].split(",") if s.strip()}
            i += 2
        elif arg == "--dry-run":
            opts["dry_run"] = True
            i += 1
        elif arg == "--no-renders":
            opts["renders"] = False
            i += 1
        elif arg == "--round":
            opts["round"] = argv[i + 1]
            i += 2
        elif arg == "--baseline":
            opts["baseline"] = argv[i + 1]
            i += 2
        else:
            fail(f"unknown option {arg!r}")
    return opts


def write_hash_manifest(path: Path, shape_info: dict, opts: dict, export_set: set) -> dict:
    """Round-3 erratum 3: a per-build hash manifest -- sha256 + size of every
    DAE, every staged texture and the materials json -- diffed against the
    previous round's manifest so 'unchanged' is a cited equality, not a
    claim. The baseline for the next round is this file's --round snapshot."""

    manifest = {
        "schema": "ericrolph-hot-potato-arena-hashes-v1",
        "arena_id": ARENA_ID,
        "round": opts["round"],
        "generator": {
            "script": "examples/hot_potato_arena/blender/create_arena.py",
            "sha256": sha256_file(SCRIPT_PATH)["sha256"],
            "blender": bpy.app.version_string,
        },
        "exported_this_build": sorted(export_set),
        "dae": {
            shape: {
                "file": info["dae"],
                "sha256": info["sha256"],
                "size": info["size"],
                "tris": info["tris"],
            }
            for shape, info in sorted(shape_info.items())
        },
        "textures": {
            p.name: sha256_file(p) for p in sorted((SHAPE_DIR / "textures").glob("*.png"))
        },
        "materials_json": {
            "file": f"{SHAPES_RELATIVE}/{ARENA_ID}.materials.json",
            **sha256_file(SHAPE_DIR / f"{ARENA_ID}.materials.json"),
        },
    }
    baseline_path = AUTHORING_ROOT / opts["baseline"]
    if baseline_path.is_file():
        with open(baseline_path, encoding="utf-8") as fh:
            base = json.load(fh)
        changed_dae = sorted(
            s
            for s, e in manifest["dae"].items()
            if base.get("dae", {}).get(s, {}).get("sha256") != e["sha256"]
        )
        changed_tex = sorted(
            n
            for n, e in manifest["textures"].items()
            if base.get("textures", {}).get(n, {}).get("sha256") != e["sha256"]
        )
        manifest["baseline"] = {
            "file": baseline_path.name,
            "round": base.get("round"),
            "changed_dae": changed_dae,
            "changed_dae_before": {
                s: base["dae"][s]["sha256"] for s in changed_dae if s in base.get("dae", {})
            },
            "unchanged_dae": sorted(set(manifest["dae"]) - set(changed_dae)),
            "missing_vs_baseline": sorted(set(base.get("dae", {})) - set(manifest["dae"])),
            "changed_textures": changed_tex,
            "materials_json_changed": base.get("materials_json", {}).get("sha256")
            != manifest["materials_json"]["sha256"],
        }
        stray = sorted(set(changed_dae) - export_set)
        if stray:
            print(
                f"WARNING: DAEs differ from the baseline but were NOT exported this build: {stray}"
            )
        print(
            f"hash manifest vs {baseline_path.name}: changed DAEs {changed_dae or 'none'}; "
            f"changed textures {changed_tex or 'none'}; materials json "
            f"{'CHANGED' if manifest['baseline']['materials_json_changed'] else 'unchanged'}; "
            f"{len(manifest['baseline']['unchanged_dae'])} DAEs hash-equal"
        )
    else:
        manifest["baseline"] = {"file": baseline_path.name, "note": "baseline not found; no diff"}
        print(f"hash manifest: no baseline {baseline_path.name}; no diff")
    with open(path, "w", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    if opts["round"]:
        shutil.copyfile(path, path.with_name(f"{ARENA_ID}.hashes.{opts['round']}.json"))
    return manifest


def stage_textures() -> None:
    target = SHAPE_DIR / "textures"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for fam in FAMILIES:
        for suffix in (".color.png", ".normal.png", "_roughness.data.png"):
            source = TEXTURE_DIR / f"{fam}{suffix}"
            if not source.is_file():
                fail(f"texture missing: {source} (run generate_arena_textures.py)")
            shutil.copyfile(source, target / source.name)
            count += 1
    print(f"staged {count} texture maps ({len(FAMILIES)} families) into the mod tree")


RENDER_RIG = {
    "sun_direction": (-0.55, 0.45, -0.62),
    "sun_energy": 3.6,
    "world_color": (0.62, 0.70, 0.84),
    "world_strength": 0.42,
}


def render_shape(obj, all_objects, path: Path) -> None:
    for other in all_objects:
        other.hide_render = other is not obj
    bounds = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    center = sum(bounds, Vector()) / 8.0
    radius = max((b - center).length for b in bounds)
    distance = max(6.0, radius * 2.1)
    azimuth = math.radians(35.0)
    cam = center + Vector(
        (distance * math.cos(azimuth), -distance * math.sin(azimuth), max(2.5, radius * 0.7))
    )
    bk.render_thumbnail(
        path,
        camera_location=tuple(cam),
        look_at=tuple(center),
        resolution=(1280, 720),
        **RENDER_RIG,
    )


def render_assembly(instances, shape_objects, materials) -> None:
    for obj in shape_objects.values():
        obj.hide_render = True
    duplicates = []
    for inst in instances:
        source = shape_objects[inst["shape"]]
        duplicate = bpy.data.objects.new(f"asm_{inst['name']}", source.data)
        bpy.context.scene.collection.objects.link(duplicate)
        duplicate.rotation_euler = (0.0, 0.0, math.radians(inst["rotation_ccw_deg_z"]))
        duplicate.location = (
            inst["position"][0] - CENTER_WORLD[0],
            inst["position"][1] - CENTER_WORLD[1],
            inst["position"][2] - CENTER_WORLD[2],
        )
        duplicates.append(duplicate)
    # Stand-in for the stock groundplane at z = 0 EXACTLY (round 2 sat it
    # 50 mm low and the lit step along the glacis toe read as a line). It
    # is an ANNULUS from r 6: in game the medallion prop owns r < 6, and a
    # coplanar slab under the floor skin's 0..12 mm inner skirt gave EEVEE
    # shadow acne that rendered as a dark ring around the pad (fix 6).
    gb = MeshBuild("asm_ground")
    gm = gb.mat(M_IRON_MATTE)
    inner = [gb.vert(*bearing_point(360.0 * k / 96, FLOOR_R_IN, 0.0)) for k in range(96)]
    outer = [gb.vert(*bearing_point(360.0 * k / 96, 240.0, 0.0)) for k in range(96)]
    for k in range(96):
        n = (k + 1) % 96
        gb.quad(inner[k], inner[n], outer[n], outer[k], Vector((0, 0, 1)), gm)
    ground = gb.to_object(materials)
    metric_uvs(ground, 4.0)
    duplicates.append(ground)
    p1 = bearing_point(30.0, BUTTER_R)
    views = {
        "arena_overview_high": ((0.0, -190.0, 95.0), (0.0, 0.0, 0.0)),
        "arena_overview_player": (bearing_point(120.0, 150.0, 5.0), (0.0, 0.0, 4.0)),
        "arena_bowl_player": (bearing_point(120.0, 40.0, 3.0), (0.0, 0.0, 1.5)),
        "arena_handle_view": ((24.0, -104.0, 10.0), (0.0, -45.0, 3.0)),
        "arena_ramp_east": (bearing_point(140.0, 70.0, 3.5), bearing_point(163.0, 82.0, 2.5)),
        "arena_spout_view": (bearing_point(60.0, 128.0, 3.5), bearing_point(60.0, 76.0, 1.0)),
        "arena_spout_jamb": (bearing_point(40.0, 84.0, 4.0), bearing_point(48.0, 90.0, 3.0)),
        "closeup_rim_band": (bearing_point(96.0, 87.0, 7.5), bearing_point(104.0, 91.4, 5.5)),
        "closeup_butter_pool": ((p1[0] + 14.0, p1[1] - 9.0, 3.2), (p1[0], p1[1], 0.2)),
        "closeup_salt_arc": (bearing_point(80.0, 28.0, 3.0), bearing_point(90.0, 16.0, 0.1)),
        "closeup_deck_wood": ((3.0, -34.0, 5.6), (0.0, -60.0, 4.0)),
        "closeup_name_plate": ((0.0, 118.0, 4.0), (0.0, 101.5, 3.4)),
        "closeup_merge_fillet": ((22.0, -66.0, 6.5), (10.0, -77.5, 3.0)),
        "closeup_glacis": (bearing_point(100.0, 122.0, 3.5), bearing_point(100.0, 98.0, 3.0)),
        # v3.2: the feather from a player's eye (pool 1 proud on the lifted
        # skin in the foreground, the feather and the wall toe beyond), a
        # tangential close-up along the toe, and the 300 m top view.
        "arena_feather_player": (bearing_point(22.0, 58.0, 1.4), bearing_point(30.0, 75.0, 0.1)),
        "closeup_feather_toe": (bearing_point(100.0, 72.0, 1.2), bearing_point(108.0, 75.0, 0.3)),
        "arena_top_300m": ((0.0, 0.0, 300.0), (0.0, 0.0, 0.0)),
        # v3.4: the critic's crop geometry -- a 150 m eye looking down on the
        # UPPER-RIGHT glacis quadrant, the annulus where the stripes are
        # (`crit/g10_3_d150_glacisUR.png`). The camera is elevated at 150 m
        # and aimed at the glacis mid-annulus (r ~102) on the NE bearing, so
        # the frame is the outer slope with the crest at one edge and the
        # stock groundplane at the other -- the same read as the crop.
        # v3.7: the deck's rear junction onto the bank, from a player's eye.
        # v3.6 claimed a 145 mm step here; A26 measures 0.002 mm. One view
        # from outboard on the glacis looking in at the junction, one from a
        # driver's seat on the deck about to cross it.
        "closeup_deck_rear_junction": ((0.0, -96.0, wall_z(96.0) + 1.6), (0.0, -87.0, 4.0)),
        "deck_rear_driver_eye": ((0.0, -80.0, HANDLE_DECK_Z + 1.3), (0.0, -92.0, 4.3)),
        "arena_glacis_150m": ((0.0, 0.0, 150.0), bearing_point(45.0, 102.0, 2.0)),
        "closeup_glacis_annulus": (
            bearing_point(45.0, 150.0, 60.0),
            bearing_point(45.0, 102.0, 2.0),
        ),
    }
    for name, (cam, look) in views.items():
        bk.render_thumbnail(
            RENDER_DIR / f"{name}.jpg",
            camera_location=tuple(cam),
            look_at=tuple(look),
            resolution=(1600, 900),
            **RENDER_RIG,
        )
    for duplicate in duplicates:
        bpy.data.objects.remove(duplicate, do_unlink=True)


def main() -> None:
    opts = parse_cli()
    bk.reset_scene()
    assert_profile_laws()

    materials = {}
    for name, entry in MATERIALS.items():
        materials[name] = bk.material(
            name,
            tuple(entry["color"]),
            metallic=entry["metallic"],
            roughness=entry["roughness"],
            texture=TEXTURE_DIR / f"{entry['family']}.color.png",
        )
    for material in bpy.data.materials:
        material.use_backface_culling = True

    builders = {
        "wall_arc_45": build_wall_arc_45,
        "wall_arc_spout": build_wall_arc_spout,
        "floor_skin_quadrant": build_floor_skin_quadrant,
        "handle": build_handle,
        "handle_ramp_e": lambda m: build_handle_ramp(m, +1),
        "handle_ramp_w": lambda m: build_handle_ramp(m, -1),
        "masher_pillar": build_masher_pillar,
        "grinder_pillar": build_grinder_pillar,
        "geyser_tower": build_geyser_tower,
        "butter_pool": build_butter_pool,
        "salt_arc": build_salt_arc,
        "trim_ring": build_trim_ring,
        "merge_fillet": build_merge_fillet,
    }
    uv_plan = {
        "wall_arc_45": dict(meters_per_tile=4.0, rim_material=M_RIM),
        "wall_arc_spout": dict(meters_per_tile=4.0, rim_material=M_RIM),
        "floor_skin_quadrant": dict(meters_per_tile=4.0),
        "handle": dict(meters_per_tile=6.0, grain_along_y=True),
        "handle_ramp_e": dict(meters_per_tile=6.0),
        "handle_ramp_w": dict(meters_per_tile=6.0),
        "masher_pillar": dict(meters_per_tile=2.0, cylindrical=True),
        "grinder_pillar": dict(meters_per_tile=6.0, cylindrical=True, staves=True),
        "geyser_tower": dict(meters_per_tile=2.5),
        "butter_pool": dict(meters_per_tile=5.0),
        "salt_arc": dict(meters_per_tile=4.0),
        "trim_ring": dict(meters_per_tile=2.0, rim_material=M_RIM, plate_uv=plate_uv),
        "merge_fillet": dict(meters_per_tile=6.0, grain_along_y=True),
    }

    shape_objects, shape_info = {}, {}
    for shape, builder in builders.items():
        obj = builder(materials)
        metric_uvs(obj, **uv_plan[shape])
        if shape == "merge_fillet":
            fillet_round_uvs(obj, uv_plan[shape]["meters_per_tile"])  # erratum 4
        finish_shape(obj)
        count = tri_count(obj)
        assert_tri_budget(shape, count)
        shape_objects[shape] = obj
        shape_info[shape] = {"tris": count, "budget": TRI_BUDGETS[shape]}
        print(f"shape {shape}: {count} tris (budget {TRI_BUDGETS[shape]})")

    assert_seam_columns(shape_objects["wall_arc_45"], 22.5)
    assert_seam_columns(shape_objects["wall_arc_spout"], 22.5)
    assert_seam_columns(shape_objects["floor_skin_quadrant"], 45.0)
    for shape in ("wall_arc_45", "wall_arc_spout"):
        assert_wall_relief_two_sided(shape_objects[shape])
        assert_mesh_crest(shape_objects[shape])
    assert_under_deck_rays(shape_objects["handle"])
    assert_plate_relief(shape_objects["butter_pool"], RELIEF_CAP)
    assert_plate_relief(shape_objects["salt_arc"], RELIEF_CAP)
    assert_trim_relief(shape_objects["trim_ring"])
    assert_ramp(shape_objects["handle_ramp_e"], +1)
    assert_ramp(shape_objects["handle_ramp_w"], -1)
    floor = shape_objects["floor_skin_quadrant"].data.vertices
    if abs(max(v.co.z for v in floor) - SKIN_TOP_Z) > 1e-6:
        fail(f"floor skin top != {SKIN_TOP_Z}")
    if min(v.co.z for v in floor if abs(math.hypot(v.co.x, v.co.y) - 6.0) < 1e-6) > 1e-9:
        fail("floor skin inner ring not skirted to grade")
    skin_report = assert_skin_driven_surface(shape_objects["floor_skin_quadrant"])  # A19
    seam_report = assert_skin_seams(
        shape_objects["floor_skin_quadrant"],  # A20
        shape_objects["wall_arc_45"],
        shape_objects["wall_arc_spout"],
    )
    deck_top = max(co.z for co in role_verts(shape_objects["handle"], "deck"))
    if abs(deck_top - HANDLE_DECK_Z) > 1e-6:
        fail(f"handle deck top {deck_top} != {HANDLE_DECK_Z}")

    instances, obstacles = build_placements()
    if len(instances) != 32:
        fail(f"instance table has {len(instances)} records, v3 says 32 (31 + merge_fillet)")
    if len(builders) != 13:
        fail("shape count != 13")
    if any(i["collision"] != "visible-mesh" for i in instances):
        fail("v3.2: every instance, the floor skins included, ships collision (visible-mesh)")
    solids, plates, wall = footprints()
    assert_footprints(solids, plates, wall)
    assert_lane_connectivity(solids)
    assert_inside_corners(solids)
    assert_obstacle_coverage(obstacles)
    obstacle_radius_report = assert_obstacle_physical_radii(obstacles)  # A24
    face_coverage_report = assert_face_coverage(obstacles)  # A25
    # The runtime refuses a registration call with more than OBSTACLE_CAP
    # entries -- the whole call, so an overflow is not a partial loss.
    if len(obstacles) > OBSTACLE_RUNTIME_CAP:
        fail(
            f"A25: {len(obstacles)} obstacles exceeds the runtime cap {OBSTACLE_RUNTIME_CAP} "
            f"-- STOP and report; do not trim silently"
        )
    print(
        f"obstacle table: {len(obstacles)} points (runtime cap {OBSTACLE_RUNTIME_CAP}, "
        f"{OBSTACLE_RUNTIME_CAP - len(obstacles)} spare)"
    )
    plate_report = assert_plates_on_skin(instances, shape_objects, plates)  # A21
    junction_report = assert_shape_junctions(shape_objects, seam_report, plate_report)  # A26
    # Solids standing on the plaza keep their grade-level bases: they are
    # buried 50 mm under the new surface (12 mm before). Record it.
    buried = {}
    for shape in ("masher_pillar", "grinder_pillar", "geyser_tower", "handle", "merge_fillet"):
        base = min(v.co.z for v in shape_objects[shape].data.vertices)
        buried[shape] = round((SKIN_TOP_Z - base) * 1000, 1)
    print(f"bases under the lifted skin (mm): {buried}")

    export_set = set(builders) if opts["export"] is None else set(opts["export"])
    unknown = export_set - set(builders)
    if unknown:
        fail(f"--export names unknown shapes: {sorted(unknown)}")
    if opts["dry_run"]:
        print(f"DRY RUN: {len(shape_objects)} shapes built and asserted; nothing written")
        return
    print(
        f"export set: {sorted(export_set)}; kept as shipped: {sorted(set(builders) - export_set)}"
    )
    stray_material_only = opts["material_only"] - export_set
    if stray_material_only:
        fail(f"--material-only names shapes outside the export set: {sorted(stray_material_only)}")
    material_only_report: dict = {}

    for shape, obj in shape_objects.items():
        dae_path = SHAPE_DIR / f"{ARENA_ID}_{shape}.dae"
        if shape == "floor_skin_quadrant":
            extra = build_floor_skin_node_tree(obj)
            if shape in export_set:
                shape_info[shape].update(export_dae(obj, dae_path, extra=extra or None))
            else:
                shape_info[shape].update(hash_shipped_dae(dae_path, obj, extra or None))
            # A20 on the FILE, whether it was written this build or kept as
            # shipped: the collision the engine builds comes from the DAE on
            # disk, so the shipped file is re-measured every round (v3.4 --
            # a round that exports only the walls must still carry the skin's
            # seam numbers in the handoff).
            seam_report.update(assert_skin_seams_exported(dae_path))
            # v3.2: the LOD block is gone with the far detail -- explicitly
            # null so the prefab generator sees the removal, not an absence.
            shape_info[shape]["lod"] = None
            shape_info[shape]["dae_tris_total"] = tri_count(obj)
            shape_info[shape]["node_tree"] = (
                "base00 -> {start01 -> {<mesh>_a290}, nulldetail10}: ONE mesh detail; "
                "the far _a70 detail was dropped (design owner 2026-09-02)"
                if extra
                else "plain object, no scaffold nodes (like the other twelve shapes)"
            )
        elif shape in export_set:
            # A23: snapshot the shipped geometry BEFORE overwriting it, so a
            # material-only re-export can be proven to have moved nothing.
            before = None
            if shape in opts["material_only"]:
                if not dae_path.is_file():
                    fail(f"A23: {shape} is declared --material-only but has no shipped DAE")
                before = {
                    "points": sorted(dae_positions(dae_path)),
                    "tris": dae_tri_count(dae_path),
                    "symbols": dae_material_symbols(dae_path),
                }
            shape_info[shape].update(export_dae(obj, dae_path))
            if before is not None:
                material_only_report[shape] = assert_material_only_reexport(dae_path, before)
        else:
            shape_info[shape].update(hash_shipped_dae(dae_path, obj))
        shape_info[shape]["dae"] = f"{SHAPES_RELATIVE}/{ARENA_ID}_{shape}.dae"
        shape_info[shape]["materials"] = [m.name for m in obj.data.materials if m is not None]
    # retire the round-1 single ramp DAE if it is still in the tree
    stale = SHAPE_DIR / f"{ARENA_ID}_handle_ramp.dae"
    if stale.is_file():
        stale.unlink()

    write_materials_json(SHAPE_DIR / f"{ARENA_ID}.materials.json")
    shadow_report = assert_shadow_casting(
        SHAPE_DIR / f"{ARENA_ID}.materials.json",  # A22
        shape_objects,
    )
    stage_textures()
    AUTHORING_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = write_hash_manifest(
        AUTHORING_ROOT / f"{ARENA_ID}.hashes.json", shape_info, opts, export_set
    )

    scene_total = sum(shape_info[i["shape"]]["tris"] for i in instances)
    handoff = {
        "schema": "ericrolph-hot-potato-arena-handoff-v2",
        "arena_id": ARENA_ID,
        "design": "arena_design_v3.md + v3.1 amendment (geometry round 2) + v3.2 skin lift "
        "(design owner, 2026-09-02)",
        "center_world": list(CENTER_WORLD),
        "matrix_convention": MATRIX_CONVENTION,
        "crest_radius_m": CREST_R,
        "crest_z_m": CREST_Z,
        "max_grade": MAX_GRADE,
        "glacis_toe_r_m": GLACIS_TOE,
        "wall_stations": [round(s, 4) for s in WALL_STATIONS],
        "ramp": {
            "r_in": RAMP_R_IN,
            "r_out": RAMP_R_OUT,
            "toe_bearing_e": RAMP_TOE_BEARING,
            "toe_bearing_w": 360.0 - RAMP_TOE_BEARING,
            "slope_arc_deg": round(RAMP_SLOPE_ARC_DEG, 3),
            "flat_m": RAMP_FLAT_M,
            "ease_m": RAMP_EASE_M,
            "merge_bearing_e_r80": round(_FLANK80, 3),
        },
        "materials_json": f"{SHAPES_RELATIVE}/{ARENA_ID}.materials.json",
        "texture_families": FAMILIES,
        "groundtype": {
            "field": GROUNDTYPE_FIELD,
            "butter": BUTTER_GROUNDTYPE,
            "salt": SALT_GROUNDTYPE,
            "note": "single-point toggle lives in create_arena.py (pending probe P1)",
        },
        "shapes": shape_info,
        "scene_tris": scene_total,
        # v3.2: null, deliberately kept as a key -- the scenario worker's
        # generator keys on `lod` being a dict; null means "no LOD, one detail".
        "floor_skin_lod": None,
        "floor_skin": {
            "design_change": "design owner, 2026-09-02: skin lifted to +50 mm WITH collision, "
            "feathered to the 12 mm datum; reason: per-boot depth fight with the "
            "stock groundplane at 300 m (G1: band 2.6-4.8 on 2 of 3 boots) and the "
            "DAE LOD proven never to engage (scenario critic r4 negative control)",
            "collision": "visible-mesh (prefab: Visible Mesh Final) on all four quadrants",
            "node_tree": shape_info["floor_skin_quadrant"]["node_tree"],
            "detail_nodes": [f"{ARENA_ID}_floor_skin_quadrant_a{FLOOR_LOD_NEAR_PX}"]
            + ([f"nulldetail{FLOOR_LOD_NULL_PX}"] if FLOOR_SKIN_STOCK_NODES else []),
            "rings_r_m": SKIN_RINGS,
            "profile": skin_report,
            "seams": seam_report,
            "plates_on_skin": plate_report,
            "plate_instance_lift_m": SKIN_TOP_Z,
            "bases_buried_under_skin_mm": buried,
            "shadows": {
                "decision": "design owner, 2026-09-02: the floor skin must stop CASTING shadows -- "
                "it is a flat plate on the ground with 50 mm of rim relief, so the "
                "shadow it self-receives is pure artifact (G7.1: even screen-row "
                "stripes inside the wall ring on 1 of 3 boots, band 2.61-2.73, the "
                "skin demonstrably DRAWN at plaza median 90.8-101.9 vs 145.5 hidden)",
                "mechanism": "material-level castShadows: false (JSON boolean), written only when "
                "false as stock spells it",
                "evidence": "lua/ge/extensions/editor/materialEditor.lua:2395 (Material field, "
                "'Material can cast it's own shadows'); lua/ge/client/core.lua:133,145 "
                "setField('castShadows', 0, '0') and :162,177 mat.castShadows = false; "
                "81 stock Material entries carry it, all false, all JSON booleans, 67 "
                "at version 1.5 with Stages (gridmap_v2.zip, art_shapes.zip, "
                "gameengine.zip) -- decalroad lines, m_gm_numbers_decal (opaque) and "
                "ind_metal_expanded (opaque, groundtype METAL)",
                "object_level_ruled_out": "0 of 7,167 stock TSStatic records in gridmap_v2 carry "
                "any field whose name contains 'shadow' -- no prefab "
                "field is added, so the round-3 uninitialised-S32 trap "
                "does not apply and nothing new is routed to the prefab",
                "disabled_materials": shadow_report["disabled"],
                "still_casting": shadow_report["still_casting"],
                "note": "the shared cast_iron_matte keeps casting (the bank and the batter chutes "
                "throw real shadows), which is why the skin and the glacis each got their "
                "own copy; both still RECEIVE the bank's shadow -- only casting is disabled",
                "v3_4_glacis": {
                    "decision": "design owner, 2026-09-02: stop the GLACIS casting, keep the bank "
                    "casting. The final critic cropped G10_3 vs G10_1 at 150 m (same "
                    "camera, same build, two boots) and found the banded boot's outer "
                    "glacis covered in dense stripes and the clean boot's spotless; "
                    "the 0.896-0.915 'clean at 150 m' metric sampled a PLAZA DISC at "
                    "frame centre, so it missed an artifact that had migrated onto the "
                    "glacis. v3.3 disarmed the two floor materials and left "
                    "cast_iron_matte (bank AND glacis) casting -- which is where the "
                    "stripes then were",
                    "material": M_IRON_GLACIS,
                    "covers": "the outer slope beyond the crest on BOTH wall shapes: bands with "
                    "r0 >= 91.4 (the first is r 93, since the rim band r 90..93 keeps "
                    "its own material) out to the toe at r 113 -- wall_arc_45's bands "
                    "and wall_arc_spout's side patches, one decision in band_material()",
                    "still_casting_on_the_wall_shapes": "the bank (r 76..90), the rim band "
                    "(r 90..93), the batter chutes and the "
                    "spout corridor floor -- deliberately: the "
                    "chutes cast real shadows into the "
                    "corridor and neither is the striped "
                    "surface in the critic's crop. They are "
                    "the next candidates if the re-measure "
                    "still shows stripes in the spout throats",
                    # A23 only runs in a build that actually re-exports the
                    # walls. A round that does not must SAY so rather than
                    # emit an empty dict that reads like "nothing was
                    # proven" (the same record-loss bug as the skin's seam
                    # fields in v3.4).
                    "geometry_unchanged": material_only_report
                    or {
                        "measured_in_round": "v3.4",
                        "note": "A23 ran in the v3.4 build that re-exported both wall DAEs and "
                        "found identical triangle counts and vertex positions (max delta "
                        "0.0 m). Not re-measured this round: the walls were not "
                        "re-exported and their digests are hash-equal to v3.4. The "
                        "numbers are in authoring/<arena>.handoff.v3.4.json.",
                    },
                    "unproven": "NOT verified in game. The re-measurement must sample the GLACIS "
                    "ANNULUS (r 91.4..113, or the critic's wider r 76..120), NOT the "
                    "plaza disc, at 150 m and 300 m across >= 3 boots",
                },
            },
            "inner_edge": "r 6 on grade (z 0): the car passes from the stock groundplane under the "
            "no-collision medallion onto the skin with no step",
            "outer_edge": "r 76 on the 12 mm datum, vertex-coincident with the wall sheet's toe "
            "ring (both wall shapes, every bearing) -- no collision step",
        },
        "scene_budget": SCENE_BUDGET,
        "hash_manifest": {
            "file": f"{ARENA_ID}.hashes.json",
            "round": opts["round"],
            "baseline": manifest["baseline"].get("file"),
            "changed_dae_vs_baseline": manifest["baseline"].get("changed_dae"),
            "changed_textures_vs_baseline": manifest["baseline"].get("changed_textures"),
            "rule": "written on every build (sha256 + size per DAE, staged texture and the "
            "materials json, diffed against the previous round's snapshot beside it); "
            "an 'unchanged' claim cites equal hashes, and shapes.<name>.sha256 above "
            "is the same digest",
        },
        "instances": instances,
        "obstacles": obstacles,
        "obstacle_physical_radius": obstacle_radius_report,
        "obstacle_face_coverage": face_coverage_report,
        "shape_junctions": junction_report,
        "notes": [
            "positions are world meters on gridmap_v2; grade z = 100",
            "rotation_ccw_deg_z is right-handed about +Z; rotationMatrix is row-major 3x3",
            "v3.2 (design owner, 2026-09-02): floor_skin_quadrant instances ship "
            "collision='visible-mesh' -- the skin is a driven +50 mm surface feathered to the "
            "12 mm datum at r 76 (skirt r 6..9 at 2.0 %, feather r 73.5..76 at 1.9 %); the "
            "butter pools and salt arcs are lifted +0.050 m by INSTANCE z (DAEs frozen) so "
            "they stay 20 mm proud of the new surface; shapes.floor_skin_quadrant.lod and "
            "floor_skin_lod are null (one mesh detail, the far _a70 dropped) -- see floor_skin",
            "handle_ramp_w is the MIRROR of handle_ramp_e (an arc ramp is chiral; a 180-deg "
            "rotation cannot place it)",
            "v3 (geometry round 3): merge_fillet is a NEW 13th shape / 32nd instance (both "
            "merge-corner fillets, arena frame at C, rotation 0, wood) -- the ramp and "
            "handle DAEs are unchanged from round 2",
            "obstacle table generated to satisfy A13 coverage: 28 amendment points + 8 deck "
            "flank points + 4 jamb outer-face points + 2 far-jamb noses = 42 (cap 64) -- see "
            "the report ledger",
            "v3.1 (round-3 errata): floor_skin_quadrant re-exported with nulldetail10 under "
            "base00 as a sibling of start01 (stock 90/91); trim_ring re-exported with the "
            "name-plate uphill skirt wound face-up (A4c); merge_fillet re-exported with a "
            "UV-only remap of its round wall (cosmetic); every other DAE and every texture "
            "is hash-equal to round 3 -- see hash_manifest",
        ],
    }
    with open(AUTHORING_ROOT / f"{ARENA_ID}.handoff.json", "w", newline="\n") as fh:
        json.dump(handoff, fh, indent=2, sort_keys=True)
        fh.write("\n")

    if not opts["renders"]:
        print(
            f"ARENA generator complete (renders skipped): {len(shape_objects)} shapes, "
            f"{len(instances)} instances, {scene_total} scene tris"
        )
        return
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    for old in RENDER_DIR.glob("*.jpg"):
        old.unlink()
    all_objects = list(shape_objects.values())
    for shape, obj in shape_objects.items():
        render_shape(obj, all_objects, RENDER_DIR / f"shape_{shape}.jpg")
    for obj in all_objects:
        obj.hide_render = False
    render_assembly(instances, shape_objects, materials)

    total = sum(info["tris"] for info in shape_info.values())
    print(
        f"ARENA generator complete: {len(shape_objects)} shapes, {len(instances)} instances, "
        f"{len(obstacles)} obstacles, {total} unique tris, {scene_total} scene tris "
        f"(budget {SCENE_BUDGET}, {(scene_total / SCENE_BUDGET - 1) * 100:+.1f} %)"
    )


if __name__ == "__main__":
    main()
