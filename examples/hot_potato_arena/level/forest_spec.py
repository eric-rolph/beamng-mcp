"""Design v4 §4 as data: the 54 forest species, their LODs, materials, covers and densities.

This is the single source of truth shared by the three B3 build scripts and by the
static gates:

- ``blender_forest.py``   reads :data:`SPECIES` / :data:`COVER_SHAPES` and exports one DAE
  per entry with exactly the authored triangle budgets and the stock node tree,
- ``forest_textures.py``  reads :data:`MATERIALS` and cooks the six-role maps,
- ``plant_forest.py``     reads :data:`ZONES`, :data:`SPECIES_MIX` and :data:`GROUND_COVERS`
  and writes ``art/forest/managedItemData.json``, ``forest/<item>.forest4.json``,
  the ``GroundCover`` records and the ``ForestWindEmitter``,
- ``tests/test_hot_potato_forest.py`` re-derives every quality-bar number from here.

Nothing in this module imports ``bpy``, ``numpy`` or ``PIL``: the gates can read it in a
bare interpreter.  Every number is either quoted from ``level_design_v4.md`` §4 (the frozen
specification, sha256 ``72e8203504a237b5…``) or is a build choice recorded in
:data:`DEVIATIONS` with its reason.

Naming law (level_facts, "SimObject names are global across classes"): a ``Material`` may
never share a name with a ``TSForestItemData``.  Forest datablocks are
``ericrolph_hot_potato_arena_f_<key>`` and the design's own foliage-material list collides
with the four shrub species on exactly four names -- see ``DEV-3`` below.
"""

from __future__ import annotations

import itertools
import math
import random

LEVEL_ID = "ericrolph_hot_potato_arena"

#: Where each family's DAEs live under ``levels/<id>/``.  ``art/shapes/trees`` is not a
#: taste: ``study/census.py`` buckets a DAE by the third path element, and the quality bar's
#: QB-6 line reads ``shapes.by_category["trees"]`` -- the 18 generated conifers must sit in a
#: directory called exactly ``trees`` or QB-6 measures nothing at all.
TREES_DIR = "art/shapes/trees"
DEADWOOD_DIR = "art/shapes/deadwood"
CARDS_DIR = "art/shapes/undergrowth"
ROCKS_DIR = "art/shapes/rocks"
COVER_DIR = "art/shapes/groundcover"

BB_NODE = "bb_autobillboard25"
#: B0 measured it: the default ``dim 64`` yields a 256 x 128 atlas, ``BB::DIM=128`` yields
#: 512 x 256 (report_B0 §1 IMPOSTER, A4).  Written into the bb node as
#: ``<extra><technique profile="OpenCOLLADA"><user_properties>``.
BB_DIM = 128
#: r4 (critic r3 D8), corrected and completed in r5 (critic r4 B1).  Design §4.3 leaves the
#: 1024 x 512 atlas open and §9 prices it.  Everything below is MEASURED in the QB-9b probe
#: boot (``tests/test_hot_potato_forest_live.py::test_forest_imposter_atlas_knobs``, opt-in).
#: r6 (critic r5 M25): cite the MEASUREMENT, not a basename -- two files are called
#: ``evidence_bbknob.json`` and the older one has no ``INCLUDE_POLES`` in it.  The nine rows
#: below are ``evidence.engine_laws.b_the_view_grid_and_the_poles.knob_probe`` (r5's five,
#: including every ``INCLUDE_POLES`` row) plus r1's four-variant atlas-size sweep.  Read
#: against the shape constructor the engine builds -- its readout is
#: ``1 <equator> <polar> <angle> <dim> <include_poles> <field7>`` -- fields 2, 3, 5 and 6 are
#: DEMONSTRATED by the sweep below; field 7 reads 0 in every recipe and nothing here
#: distinguishes it, so r6 (critic r5) removed the guessed label ``<shadow>`` -- and against
#: the atlas the
#: engine then writes, read back with ``forest_build.imposter_reading``:
#:
#:   recipe                                     constructor       atlas       cells rendered
#:   ``DIM=128``                                ``1 4 0 0 128 1 0``   512x256     6 views
#:   ``DIM=128 EQUATOR_STEPS=8``                ``1 8 0 0 128 1 0``   512x512    10 views
#:   ``DIM=128 POLAR_STEPS=2``                  ``1 4 2 0 128 1 0``  1024x512    22 declared
#:   ``DIM=256``                                ``1 4 0 0 256 1 0``  1024x512     6 views
#:   ``DIM=128 EQUATOR_STEPS=10 POLAR_STEPS=1`` ``1 10 1 0 128 1 0`` 1024x512  **12 of 32**
#:   ``DIM=128 EQUATOR_STEPS=30``               ``1 30 0 0 128 1 0`` 1024x512    32 (30 + 2)
#:   ``DIM=128 EQUATOR_STEPS=30 INCLUDE_POLES=0`` ``1 30 0 0 128 0 0`` 1024x512  30, NO poles
#:   ``DIM=128 EQUATOR_STEPS=32``               ``1 32 0 0 128 1 0`` 1024x1024  34 (32 + 2)
#:   ``DIM=128 EQUATOR_STEPS=32 INCLUDE_POLES=0`` ``1 32 0 0 128 0 0`` 1024x512 **32, NO poles**
#:
#: Three laws come out of that table and only the first two survived r4's wording.
#:
#: 1. ``BB::POLAR_STEPS`` SIZES the atlas and renders nothing: ``EQUATOR_STEPS=10 +
#:    POLAR_STEPS=1`` allocates the 32-cell 1024 x 512 the arithmetic predicts and renders
#:    into TWELVE of them, because ``BB::POLAR_ANGLE`` defaults to 0 so every polar row lands
#:    back on the equator.  Azimuth is the only axis worth buying.
#: 2. Six views is 90 degrees between billboards.  Stock is finer: italy's ``cypress_tree`` is
#:    EIGHT views in a 4 x 2 grid of **256 px** cells (45 deg) and its ``scots_pine`` SIXTEEN
#:    in 4 x 4 (22.5), as are ECUSA's ``tree_douglasfir_large_a`` and WCUSA's
#:    ``pine_radiata_large``.  256 px is the VIEW cell, not 128: at 128 every used tile of all
#:    four stock atlases is cut by its own edge on all four sides (32/32/32/32 and 16/16/16/16
#:    -- they are QUARTER-tiles), and at 256 not one is.
#: 3. **A pole is a DEFAULT, not an invariant.**  r4 shipped "the two poles the engine ALWAYS
#:    adds"; that was wrong and critic r4 caught it.  Not one of the four stock tree atlases
#:    carries a polar cell -- every cell in all four is a side elevation -- while r4's own
#:    atlas carried two (cells 30/31, 35 px tall against a 113 px median, fill 0.07 against
#:    0.28).  ``BB::INCLUDE_POLES`` is a real token and it is what controls them: setting it
#:    to 0 flips the constructor's sixth field to 0 and the atlas comes back with none.
#:
#: So r5 ships the stock shape at B3's own cell: ``EQUATOR_STEPS=32 + INCLUDE_POLES=0`` = 32
#: equator views, 11.25 degrees apart, filling an 8 x 4 grid of 128 px cells = 1024 x 512 --
#: measured end to end on ``fir_tall_b`` before it was adopted, not composed from two readings.
#: It costs the same bytes as r4's 30 + 2 and spends none of them on two plan views of a spire
#: that no ground camera ever samples.  Design §9 prices the 1024 x 512 recipe at +71 MB.
#: The atlas size that comes out is re-measured in every boot and recorded in
#: ``evidence.f2_summary``; the gate reads the shipped header rather than asserting 512 x 256.
BB_EQUATOR_STEPS = 32
BB_POLAR_STEPS = 0
BB_INCLUDE_POLES = 0
BB_PROPERTY = "\n".join(
    (
        f"BB::DIM={BB_DIM}",
        f"BB::EQUATOR_STEPS={BB_EQUATOR_STEPS}",
        f"BB::INCLUDE_POLES={BB_INCLUDE_POLES}",
    )
)
#: views = equator x (2 x polar + 1) + 2 poles when ``BB::INCLUDE_POLES`` is on.  The engine
#: packs them into a grid of ``BB_DIM``-pixel cells, so this is also the floor on the cells a
#: critic should find used.
BB_VIEWS = BB_EQUATOR_STEPS * (2 * BB_POLAR_STEPS + 1) + (2 if BB_INCLUDE_POLES else 0)

#: Seeds.  Every random draw in the B3 pipeline is a pure function of one of these.
SHAPE_SEED = 0x54524545  # "TREE" - Blender geometry jitter
TEXTURE_SEED = 0x54455853  # "TEXS" - atlas cutting
FOREST_SEED = 0x464F5253  # "FORS" - forest4 placement (design §4.4 "seeded FOREST_SEED")
COVER_SEED = 0x434F5652  # "COVR" - GroundCover per-record seed field


# --------------------------------------------------------------------------------------
# Materials (design §4.5 `tables.FOLIAGE_MATERIALS` + the rock/cover families B3 adds)
# --------------------------------------------------------------------------------------
# role -> (file suffix, channel count).  The six-role naming is level_facts' law:
#   *_b.color  *_nm.normal  *_r.data  *_ao.data  *_o.data  *_h.data
ROLE_SUFFIX = {
    "base": "b.color",
    "normal": "nm.normal",
    "roughness": "r.data",
    "ao": "ao.data",
    "opacity": "o.data",
    "height": "h.data",
}
ROLE_FIELD = {
    "base": "baseColorMap",
    "normal": "normalMap",
    "roughness": "roughnessMap",
    "ao": "ambientOcclusionMap",
    "opacity": "opacityMap",
    "height": "heightMap",
}

#: (key, alphaRef, groundType, source recipe, size px, roles, atlas grid or None)
#: ``key`` is the material-name suffix after ``ericrolph_hot_potato_arena_``.
#: The 22 rows tagged ``foliage=True`` are design §4.5's QB-13 list verbatim except for
#: DEV-3 (the four shrub renames).
# --------------------------------------------------------------------------------------
# CUT-OUT SOURCES (r2): where every atlas's real, photographed foliage comes from
# --------------------------------------------------------------------------------------
# Round 1 built the twig and cover atlases from GENERATED masks (`sprig_mask`, `blade_mask`)
# multiplied by a source crop.  Measured against three stock conifers that gave 42 alpha
# islands where stock has 4,281-6,964, a 134 mm mean needle where stock has 4.9-18.4 mm, and
# five ground covers that were one procedural grass sheet in five tints.  Every atlas below
# is now composed from CUT-OUT STAMPS: real islands of the CC0 photograph, taken with the
# source's OWN alpha (or its own segmentation), stamped into each cell at its own rotation,
# scale, mirror and tint.  `forest_textures.cut_stamps` does the cutting.
#
# What the conifer sources actually contain, MEASURED (`forest_textures` docstring has the
# reasoning; the numbers are in report_B3 §"Changes in r2"):
#
#   pine_tree_01          two real pine sprigs on a sheet of bark, UV junk and a colour
#                         checker; the published alpha over those two sprigs is needle-level.
#   fir_tree_01           roughly seven real fir sprigs, alpha needle-level over all of them.
#   pine_sapling_medium   the SAME sheet as pine_tree_01, byte for byte (alpha sha256[:16]
#   fir_sapling_medium    1e5a1fe741f4cb73); likewise fir_sapling_medium == fir_tree_01
#                         (6eecd1cf1e059488).  Design §12 lists them as four downloads; they
#                         are two.  DEV-10 records it.
#   pine_sapling_small    fetched in r2 to look for a third and fourth scan.  Neither carries
#   fir_sapling           a usable sprig -- their twig regions are UV-atlas junk, no island
#                         survives the cut -- so they are NOT used.  Recorded, not assumed.
#
# Variety therefore comes from the two real scans: 2 pine sprigs (plus 6 overlapping
# sub-patches each) and 8 fir sprigs, drawn per cell at a free rotation, so no two of the
# 16 cells of an atlas, and no two of the six atlases, are the same arrangement.
PINE_SPRIGS = dict(
    cc0="pine_tree_01",
    prefix="twig_",
    mask="alpha",
    clump_px=3,
    min_px=140,
    max_px=900,
    limit=2,
    subdivide=(6, 0.55),
)
FIR_SPRIGS = dict(
    cc0="fir_tree_01",
    prefix="twig_",
    mask="alpha",
    clump_px=6,
    min_px=110,
    max_px=900,
    limit=8,
    subdivide=(3, 0.6),
)
#: r9: the same two scans as WHOLE sprigs for the spray cells (`forest_textures.
#: compose_spray_atlas`): no sub-patches, because a spray is built from sprigs, not confetti.
PINE_SPRIG_WHOLE = {k: v for k, v in PINE_SPRIGS.items() if k != "subdivide"}
FIR_SPRIG_WHOLE = {k: v for k, v in FIR_SPRIGS.items() if k != "subdivide"}
#: the stock needle-card albedo band the spray cells are graded onto (b3/r9/stock_census.json:
#: ECUSA douglas fir 0.218 / 0.539 / 84.5, italy scots pine 0.220 / 0.617 / 73.6, WCUSA
#: radiata 0.308 / 0.483 / 70.4 -- sRGB luma / saturation / hue), by family
PINE_GRADE = dict(luma=0.240, sat=0.580, hue=78.0)
FIR_GRADE = dict(luma=0.235, sat=0.545, hue=84.0)
#: r12 (critic B11-5 / r10 N-8): the three broadleaf shrub sheets were the only cut-out foliage
#: that shipped UNGRADED -- Poly Haven's shrub albedo at sRGB luma 0.54-0.60, saturation
#: 0.54-0.66, hue 60-66 -- and the engine's imposter bake reproduces a pure-card shape's sheet
#: almost unchanged (MEASURED on the r11 atlases, b3/r12/bake_response_r12.json), so
#: `f_shrub_01` / `f_shrub_03` baked to mean RGB (149,154,74) / (144,144,54): the chartreuse
#: cones on the verge in `critB11_trail_ahead`.  Graded through that measured transfer onto the
#: band the eight pine ATLASES occupy under the same instrument (b3/r12/atlas_eyes_r12_before:
#: saturation 0.531-0.592, hue 61.8-68.3, luma 0.164-0.237): hue 67 on the sheet lands the bake
#: mid-band, sat 0.58 inside it, and luma 0.25 puts the bake at the top of the pines' range --
#: a shrub a shade lighter than the conifers behind it, and no longer lime.  `f_shrub_leaf_02`
#: keeps its greyer, bluer character (it is a different plant) a little outside the pines' hue.
SHRUB_GRADE = dict(luma=0.250, sat=0.580, hue=67.0)
#: r12: `f_shrub_leaf_03` shipped 6.0 % of its opaque texels at AO < 0.05 (the model atlas's
#: black UV-padding AO under the leaf islands; the pine twig sheets carry 0.0 %) -- black
#: patches under any light.  Every shrub sheet's AO is floored at the pine sheets' own p05
#: (0.55-0.59, b3/r12 measured), the same shape of rule as `FOLIAGE_ROUGHNESS_FLOOR`.
SHRUB_AO_FLOOR = 0.55
#: the same two scans cut SMALLER, for the needle clumps of the forest-litter cover.
#: `subdivide_only` (r3, M8) drops the parent stamps so these pools cannot share a stamp with
#: the SPRIGS pools they are cut from -- DEV-10's disjointness claim was false for 4 stamps
#: across 2 pairs because `stride`/`phase` only deal WITHIN one pool.
PINE_NEEDLES = dict(PINE_SPRIGS, limit=2, subdivide=(10, 0.34), subdivide_only=True)
FIR_NEEDLES = dict(FIR_SPRIGS, limit=6, subdivide=(6, 0.35), subdivide_only=True)

#: ground-cover sources, all from design §12's own list
#: r10 (B9-2): every MODEL atlas below carries UV-padding facets; `facet_reject` cuts them
#: per texel.  The pale-seed-head sources keep a high `bright` so real seed heads survive.
GRASS_TUFTS = dict(  # real blades, tufts and seed heads on black (a model atlas)
    cc0="grass_medium_01",
    mask="bright",
    clump_px=6,
    min_px=60,
    max_px=1200,
    limit=9,
    facet_reject={"bright": 0.62, "sat": 0.12, "dark": 0.05},
)
REED_BLADES = dict(  # long blades and stems on black
    cc0="grass_medium_02",
    mask="bright",
    clump_px=6,
    min_px=60,
    max_px=1600,
    limit=7,
    facet_reject={"bright": 0.62, "sat": 0.12, "dark": 0.05},
)
FERN_FRONDS = dict(  # six pinnate fronds, cut off the atlas's flat backdrop colour
    cc0="fern_02",
    mask="offcolour",
    cover=0.11,
    clump_px=4,
    min_px=250,
    max_px=1900,
    limit=5,
    fill=(0.02, 0.8),
    green_min=12.0,
    # r10 (B9-2): the same facets `texel_hue` filters by hue, also cut by flatness/brightness
    facet_reject={"bright": 0.55, "sat": 0.16, "dark": 0.05},
    # r9: the fronds share their islands with the atlas's tan UV-padding facets (hue 30-45,
    # 41-64 % of two islands); only foliage hues survive the cut
    texel_hue=(52.0, 165.0),
)
NEEDLE_LITTER = dict(  # the needle/twig scatter of the litter tile itself
    cc0="forest_leaves_04",
    mask="carve",
    clump_px=3,
    cover=0.09,
    w_bright=0.6,
    min_px=90,
    max_px=420,
    limit=20,
    fill=(0.03, 0.9),
)
#: r10 (critic B9-2): `facet_reject` is the per-texel model-atlas facet cut
#: (`forest_textures.facet_texels`).  `dry_branches_medium_01` is a MODEL atlas and most of
#: what r9 cut out of it was not a twig at all -- flat pale backdrop shards and UV padding,
#: which `gc_litter`'s grade turned into the pale grey bevelled slabs the critic read as the
#: letter "A" on the forest floor.  `bark_debris_01` carries the same class, smaller.
TWIG_BUNDLES = dict(
    cc0="dry_branches_medium_01",
    mask="offcolour",
    cover=0.10,
    clump_px=6,
    min_px=100,
    max_px=520,
    limit=12,
    fill=(0.02, 0.55),
    # the most contaminated source in the set: `probe/stamps/BIG_TWIG_BUNDLES.png` shows most
    # of what r9 cut out of it was backdrop shard, not twig, so it runs the filter hard
    facet_reject={"level": 14.0, "radius": 3, "grow": 5},
)
BARK_CHIPS = dict(
    cc0="bark_debris_01",
    mask="offcolour",
    cover=0.12,
    clump_px=6,
    min_px=80,
    max_px=900,
    limit=10,
    fill=(0.01, 0.9),
    facet_reject=True,
)
CHAR_STALKS = dict(  # burnt straw and char twigs off the burned-ground scan
    cc0="burned_ground_01",
    mask="carve",
    clump_px=3,
    cover=0.06,
    w_bright=0.7,
    min_px=150,
    max_px=600,
    limit=16,
    fill=(0.06, 0.9),
    # r10 (N-7): the grey and tan flat slabs in `gc_stubble`.  Burnt straw is legitimately
    # pale and colourless, so ONLY the flatness clause runs here -- `bright` is set out of
    # reach.  (A blanket saturation cap was measured in r3 to take this source from 16
    # usable stamps to 3.)
    facet_reject={"level": 18.0, "radius": 3, "grow": 5, "bright": 0.66, "sat": 0.10},
)
ALPINE_TUFTS = dict(
    cc0="sparse_grass",
    mask="carve",
    clump_px=3,
    cover=0.05,
    w_bright=0.6,
    min_px=110,
    max_px=700,
    limit=14,
    fill=(0.028, 0.9),
    # r10 (N-7): the pale untextured tabs the critic found scattered through `gc_alpine`
    facet_reject={"bright": 0.62, "sat": 0.12, "dark": 0.05},
)
MEADOW_FLECKS = dict(
    cc0="leafy_grass",
    mask="carve",
    clump_px=3,
    cover=0.05,
    w_green=0.6,
    min_px=150,
    max_px=800,
    limit=12,
    fill=(0.035, 0.9),
)


def _shrub_leaves(asset: str) -> dict:
    """r3 (M2): the four shrub MODEL atlases, cut the same way `fern_02` is.

    r2's contact sheet says all seventeen atlases are "photographed CC0 foliage stamped in,
    not a generated mask" -- and for these four it was false: they had no ``sources``, so
    ``cook_material`` sent them down the r1 ``cook_atlas`` path with ``leaf_mask``, a drawn
    broad-leaf blob multiplied by a crop.  They are Poly Haven model atlases with a flat
    backdrop, exactly like ``fern_02``, so ``offcolour`` cuts them: MEASURED at cover=0.16 it
    yields 8 / 6 / 10 / 8 real leaf clusters off shrub_01..04 at mean saturation 0.21-0.71.
    With these four converted, ``leaf_mask`` -- and the whole generated-mask path -- is deleted
    from ``forest_textures`` rather than left where a future material could reach it.
    """
    return dict(
        cc0=asset,
        mask="offcolour",
        cover=0.16,
        clump_px=6,
        min_px=110,
        max_px=1500,
        limit=10,
        fill=(0.02, 0.85),
        green_min=4.0,
        # these four atlases pad their UV space with flat khaki facets that hang off the leaf
        # clusters, so the island filter here is on TEXEL AREA, not on the island's mean
        achromatic_texel_max=0.10,
        # r10 (B9-2 / N-7): and the surviving facet texels are CUT OUT rather than merely
        # counted -- which is also what ends `shrub_leaf_04`'s straight-edged alpha crops.
        facet_reject={"bright": 0.50, "sat": 0.18, "dark": 0.05},
        # ...and the khaki UV SLIVERS, which are too thin for the flatness clause to see, go
        # the way `fern_02`'s tan facets went in r9: a per-texel foliage-hue window.
        texel_hue=(50.0, 170.0),
    )


def _weigh(spec: dict, weight: float) -> dict:
    return dict(spec, weight=weight)


FOLIAGE_MATERIALS: tuple[dict, ...] = (
    # --- twig card atlases: every cell is real photographed needles (r2) ---------------
    # `sources` names the cut-out pools; `phase`/`stride` deal the pool out so that no two
    # atlases carry the same stamps.  16 cells, 2-4 stamps each, free rotation.
    {
        "key": "f_pine_twig_a",
        "alphaRef": 71,
        "groundType": "LEAVES_STRONG",
        "size": 1024,
        "cc0": "pine_tree_01",
        "kind": "twig",
        "grid": (4, 4),
        "tint": (1.00, 1.00, 1.00),
        "compose": "spray",
        "sources": (dict(PINE_SPRIG_WHOLE),),
        # r10 (critic B9-3.3): r9 crammed 12-20 whole sprigs into a 256-texel cell, so every
        # cell of `f_pine_twig_a` came out a rounded clump of overlapping lobes -- "a broadleaf
        # texture, no needle, no linear axis, no negative space".  The photographed sprigs are
        # good (`b3/r10/probe/stamps/BIG_PINE_SPRIG_WHOLE.png`: a shoot with radiating needles
        # and its own woody axis); what they needed was ROOM.  Half as many, half again as
        # long, spread short of the tip, with the stem wide enough to read: the needles now get
        # 2-3 texels each instead of 1 and the axis survives to the shipped mip.
        "spray": dict(
            pairs=(4, 5),
            angle_deg=(44.0, 70.0),
            scale=(0.46, 0.60),
            taper=0.58,
            spread=(0.08, 0.86),
            tip_stamps=(1, 1),
            stem_width=(0.018, 0.028),
            lean_deg=8.0,
        ),
        "grade": PINE_GRADE,
    },
    {
        "key": "f_pine_twig_b",
        "alphaRef": 60,
        "groundType": "LEAVES_STRONG",
        "size": 1024,
        "cc0": "pine_tree_01",
        "kind": "twig",
        "grid": (4, 4),
        "tint": (1.00, 1.00, 1.00),
        "compose": "spray",
        "sources": (dict(PINE_SPRIG_WHOLE),),
        "spray": dict(
            pairs=(4, 6),
            angle_deg=(40.0, 66.0),
            scale=(0.44, 0.58),
            taper=0.55,
            spread=(0.08, 0.86),
            tip_stamps=(1, 1),
            stem_width=(0.018, 0.028),
            lean_deg=8.0,
        ),
        "grade": dict(PINE_GRADE, hue=74.0, sat=0.60),
    },
    {
        "key": "f_fir_twig_a",
        "alphaRef": 63,
        "groundType": "LEAVES_STRONG",
        "size": 1024,
        "cc0": "fir_tree_01",
        "kind": "twig",
        "grid": (4, 4),
        "tint": (1.00, 1.00, 1.00),
        "compose": "spray",
        "sources": (dict(FIR_SPRIG_WHOLE, phase=0, stride=2),),
        "spray": dict(
            pairs=(4, 6),
            angle_deg=(48.0, 74.0),
            scale=(0.44, 0.58),
            taper=0.58,
            spread=(0.08, 0.86),
            tip_stamps=(1, 1),
            stem_width=(0.018, 0.028),
            lean_deg=8.0,
        ),
        "grade": FIR_GRADE,
    },
    {
        "key": "f_fir_twig_b",
        "alphaRef": 47,
        "groundType": "LEAVES_STRONG",
        "size": 1024,
        "cc0": "fir_tree_01",
        "kind": "twig",
        "grid": (4, 4),
        "tint": (1.00, 1.00, 1.00),
        "compose": "spray",
        "sources": (dict(FIR_SPRIG_WHOLE, phase=1, stride=2),),
        "spray": dict(
            pairs=(5, 7),
            angle_deg=(44.0, 70.0),
            scale=(0.42, 0.55),
            taper=0.55,
            spread=(0.08, 0.86),
            tip_stamps=(1, 1),
            stem_width=(0.018, 0.028),
            lean_deg=8.0,
        ),
        "grade": dict(FIR_GRADE, hue=88.0, sat=0.52),
    },
    {
        "key": "f_sapling_twig",
        "alphaRef": 60,
        "groundType": "LEAVES_STRONG",
        "size": 1024,
        "cc0": "pine_sapling_medium",
        "kind": "twig",
        "grid": (4, 4),
        "tint": (1.00, 1.00, 1.00),
        "compose": "spray",
        "sources": (dict(PINE_SPRIG_WHOLE),),
        "spray": dict(
            pairs=(4, 6),
            angle_deg=(42.0, 68.0),
            scale=(0.42, 0.56),
            taper=0.60,
            spread=(0.08, 0.86),
            tip_stamps=(1, 1),
            stem_width=(0.018, 0.028),
            lean_deg=8.0,
        ),
        "grade": dict(PINE_GRADE, luma=0.255),
    },
    # --- shrub / fern / reed / dwarf cards (DEV-3: `_f_shrub_01..04` renamed) -----------
    {
        "key": "f_shrub_leaf_01",
        # r12b: 75 -> 28.  The reference must stay UNDER the cell's mean alpha (255 x
        # coverage): the 128 px imposter bake averages a card down to a texel or two, and a
        # block whose mean alpha sits under alphaRef is dropped whole (leaf_02's r12 note).
        # At r12's coverage 0.175 the mean was 45 against 75 -- the thin 0.489 bake; at the
        # r12b coverage 0.19-0.23 it is 48-59, still under 75.  28 is leaf_02's value, whose
        # bake matched its prediction to 0.04.
        "alphaRef": 28,
        "groundType": "LEAVES_THIN",
        "size": 1024,
        "cc0": "shrub_01",
        "kind": "model_card",
        "grid": (4, 2),
        "tint": (1.0, 1.0, 1.0),
        "sources": (_weigh(_shrub_leaves("shrub_01"), 1.0),),
        # r12b: the r12 bake of the dome read bbox fill 0.489 against the gate's 0.70 x
        # 0.712 = 0.498 while `predict_fill_r12.py` had said 0.69 at these stamps; the
        # sparsest sheet lost the most in the engine's bake (leaf_02, stamped (4, 6) at
        # (0.70, 1.00), baked 0.04 ABOVE its prediction), and alphaRef 75 -> 28 moved the
        # prediction by 0.013 (`b3/r12/alpharef_sweep_shrub01.json`). So: leaf_02's stamps.
        "per_cell": (4, 6),
        "stamp_span": (0.70, 1.00),
        "upright_deg": 180.0,
        # r12 (critic B11-5): graded like every conifer twig -- see SHRUB_GRADE
        "grade": SHRUB_GRADE,
        "ao_floor": SHRUB_AO_FLOOR,
    },
    {
        "key": "f_shrub_leaf_02",
        # r10: re-measured on the r10 atlas (`b3/r10/alpharef_r10.json`); the facet cut
        # made these cells sparser, so the old reference dissolved at the 4-texel mip.
        # r12: re-measured on the r12 atlas (b3/r12/alpharef_r12.json) after the cells were
        # re-stamped denser (below) and KEPT at 28: it passes the mip gate at 1.81x, and it
        # has to stay under the cell's mean alpha (255 x coverage) -- at r11's 0.11 coverage
        # that mean WAS 28, so the 128 px bake, which averages a card down to a texel or two,
        # kept half the blocks and dropped half: the "near-transparent skeleton" of critic
        # r11.  DEV-21's fixed point (38 on this sheet) would put it back on that edge.
        "alphaRef": 28,
        "groundType": "LEAVES_THIN",
        "size": 1024,
        "cc0": "shrub_02",
        "kind": "model_card",
        "grid": (4, 2),
        "tint": (1.0, 1.0, 1.0),
        "sources": (_weigh(_shrub_leaves("shrub_02"), 1.0),),
        # r12: 4-6 stamps per cell at 0.70-1.00 of the cell (was 2-4 at 0.50-0.95): the
        # shrub_02 pool cuts thin, holed clusters (b3/r12/EYES_r12_sheets.png), and the cell
        # has to be as full as the other shrubs' (0.25-0.26) for the 128 px bake to keep it
        # (DEV-21's mip law); 3-5 at 0.60-1.00 measured 0.158, up from 0.110
        "per_cell": (4, 6),
        "stamp_span": (0.70, 1.00),
        "upright_deg": 180.0,
        # r12: graded with the others but kept greyer and a touch bluer -- a different plant
        "grade": dict(SHRUB_GRADE, sat=0.50, hue=72.0),
        "ao_floor": SHRUB_AO_FLOOR,
    },
    {
        "key": "f_shrub_leaf_03",
        # r10: re-measured on the r10 atlas (`b3/r10/alpharef_r10.json`); the facet cut
        # made these cells sparser, so the old reference dissolved at the 4-texel mip
        "alphaRef": 70,
        "groundType": "LEAVES_THIN",
        "size": 1024,
        "cc0": "shrub_03",
        "kind": "model_card",
        "grid": (4, 2),
        "tint": (1.0, 1.0, 1.0),
        "sources": (_weigh(_shrub_leaves("shrub_03"), 1.0),),
        "per_cell": (2, 4),
        "stamp_span": (0.50, 0.95),
        "upright_deg": 180.0,
        # r12 (critic B11-5): graded like every conifer twig -- see SHRUB_GRADE
        "grade": SHRUB_GRADE,
        "ao_floor": SHRUB_AO_FLOOR,
    },
    {
        "key": "f_shrub_leaf_04",
        # r10: re-measured on the r10 atlas (`b3/r10/alpharef_r10.json`); the facet cut
        # made these cells sparser, so the old reference dissolved at the 4-texel mip
        "alphaRef": 68,
        "groundType": "LEAVES_THIN",
        "size": 1024,
        "cc0": "shrub_04",
        "kind": "model_card",
        "grid": (4, 2),
        "tint": (1.0, 1.0, 1.0),
        "sources": (_weigh(_shrub_leaves("shrub_04"), 1.0),),
        "per_cell": (2, 4),
        "stamp_span": (0.50, 0.95),
        "upright_deg": 180.0,
    },
    {
        # design 4.1: "the ferns and reeds whose polygon leaves are replaced by cards cut from
        # THEIR OWN ATLASES".  r2 does that literally -- these two are the real fern fronds and
        # the real reed blades, cut out, not a generated leaf-cluster mask.
        "key": "f_fern",
        "alphaRef": 34,
        "groundType": "LEAVES_THIN",
        "size": 1024,
        "cc0": "fern_02",
        "kind": "model_card",
        "grid": (4, 2),
        "tint": (1.0, 1.0, 1.0),
        "sources": (_weigh(FERN_FRONDS, 1.0),),
        "grade": dict(luma=0.26, sat=0.55, hue=92.0),
        "per_cell": (1, 2),
        "stamp_span": (0.80, 1.0),
        "rooted": True,
        "upright_deg": 12.0,
    },
    {
        "key": "f_reed",
        "alphaRef": 31,
        "groundType": "LEAVES_THIN",
        "size": 1024,
        "cc0": "grass_medium_02",
        "kind": "model_card",
        "grid": (4, 2),
        "tint": (1.04, 1.0, 0.86),
        "sources": (_weigh(REED_BLADES, 0.8), _weigh(GRASS_TUFTS, 0.2)),
        "per_cell": (2, 4),
        "stamp_span": (0.75, 1.0),
        "rooted": True,
        "upright_deg": 10.0,
    },
    {
        "key": "f_dwarf_pine",
        "alphaRef": 46,
        "groundType": "LEAVES_STRONG",
        "size": 1024,
        "cc0": "fir_sapling_medium",
        "kind": "twig",
        "grid": (4, 4),
        "tint": (0.92, 0.96, 0.90),
        "compose": "spray",
        "sources": (dict(FIR_SPRIG_WHOLE, phase=1, stride=2),),
        "spray": dict(
            pairs=(5, 7),
            angle_deg=(44.0, 70.0),
            scale=(0.38, 0.50),
            taper=0.60,
            spread=(0.08, 0.86),
            tip_stamps=(1, 1),
            stem_width=(0.018, 0.028),
            lean_deg=8.0,
        ),
        "grade": dict(FIR_GRADE, luma=0.245),
        "per_cell": (12, 20),
        "stamp_span": (0.20, 0.40),
    },
    # --- ground-cover billboard atlases: design §4.5's NAMED content, cut out for real ---
    # r1 shipped all five of these as `blade_mask` (tapered grass blades) in five tints, so
    # §4.5's "fern fronds, needle clumps, twig bundles" and "burnt stalks, char twigs" were
    # brown grass and dark grass.  Every one is now composed of cut-outs from the §12 sources
    # the design names for it.  16 cells each: the first 6 (or 5) are the COARSE record's
    # types and cells 8.. are the FINE record stacked on the same terrain layer (§4.5 covers
    # one cover per layer where stock stacks 4-17; DEV-12).
    {
        "key": "gc_meadow",
        "alphaRef": 52,
        "groundType": "GRASS",
        "size": 1024,
        "cc0": "grass_medium_01",
        "kind": "grass",
        "grid": (4, 4),
        "tint": (1.16, 1.14, 0.96),
        # r2b: `leafy_grass`'s carve cuts SPECKLE, not blades -- from the meadow at eye height
        # (the LOD-seam frame) it read as dark blobs and pale flecks.  The meadow is the two
        # sources that cut real grass: `grass_medium_01`'s tufts and blades and
        # `grass_medium_02`'s longer stems.
        "sources": (
            _weigh(GRASS_TUFTS, 0.80),
            _weigh(REED_BLADES, 0.20),
        ),
        "per_cell": (3, 6),
        "stamp_span": (0.55, 1.0),
        "rooted": True,
        "upright_deg": 22.0,
    },
    {
        "key": "gc_litter",
        "alphaRef": 54,
        "groundType": "GRASS",
        "size": 1024,
        "cc0": "forest_leaves_04",
        "kind": "grass",
        "grid": (4, 4),
        "tint": (1.0, 1.0, 1.0),
        # r9: the three covers that read this atlas (litter cells 0-5, ferns 6-10, needle
        # mat 11-15, see GROUND_COVERS) each get their OWN pool.  r2-r8 drew one mixture
        # into all sixteen cells, so the "fern" cover was mostly rust-tinted needle clumps
        # -- the saturated hay-coloured carpet of every S7 frame.  The fallen needles are
        # still tinted, to a duff brown rather than orange (1.55/1.02/0.66 -> 1.22/1.0/0.78).
        "sources": (_weigh(NEEDLE_LITTER, 0.5), _weigh(TWIG_BUNDLES, 0.5)),
        "cell_sources": (
            (
                0,
                6,
                (
                    dict(FIR_NEEDLES, weight=0.16, stamp_tint=(1.22, 1.00, 0.78)),
                    dict(PINE_NEEDLES, weight=0.10, stamp_tint=(1.26, 1.02, 0.80)),
                    _weigh(NEEDLE_LITTER, 0.40),
                    _weigh(TWIG_BUNDLES, 0.24),
                    _weigh(BARK_CHIPS, 0.10),
                ),
            ),
            (6, 11, (_weigh(FERN_FRONDS, 1.0),)),
            (
                11,
                16,
                (
                    dict(FIR_NEEDLES, weight=0.40, stamp_tint=(1.18, 1.00, 0.80)),
                    dict(PINE_NEEDLES, weight=0.25, stamp_tint=(1.22, 1.02, 0.82)),
                    _weigh(NEEDLE_LITTER, 0.35),
                ),
            ),
        ),
        "grade": dict(sat=0.46, luma=0.27),
        "per_cell": (3, 6),
        "stamp_span": (0.50, 0.95),
        "upright_deg": 180.0,
    },
    {
        "key": "gc_alpine",
        "alphaRef": 51,
        "groundType": "GRASS",
        "size": 1024,
        "cc0": "sparse_grass",
        "kind": "grass",
        "grid": (4, 4),
        "tint": (0.92, 0.98, 0.88),
        "sources": (_weigh(ALPINE_TUFTS, 0.15), _weigh(GRASS_TUFTS, 0.85)),
        "per_cell": (3, 6),
        "stamp_span": (0.55, 0.95),
        "rooted": True,
        "upright_deg": 18.0,
    },
    {
        "key": "gc_stubble",
        # r10: re-measured on the r10 atlas (`b3/r10/alpharef_r10.json`).  Dropping the model
        # atlas from the mix left denser char stamps, so the reference goes UP, not down: 65
        # is the largest that keeps its coverage at the 4-texel mip and 58 is that with margin.
        # r11: and BACK DOWN again, for the same reason in reverse.  The r10 facet cut had
        # taken 19.3 % of this atlas's opaque texels; r11's outline clause gives most of them
        # back, the stamps are dense again, and 58 now dissolves at the 4-texel mip (0.086 near
        # against 0.062 far, ratio 0.726).  Re-measured on the r11 atlas
        # (`b3/r11/alpharef_r11.json`): 41 is the largest reference that survives its own mip
        # chain.  This is the reference tracking the art, which is what it is for.
        "alphaRef": 41,
        "groundType": "GRASS",
        "size": 1024,
        "cc0": "burned_ground_01",
        "kind": "grass",
        "grid": (4, 4),
        "tint": (0.60, 0.53, 0.47),
        # r10 (B9-2 / N-7): `dry_branches_medium_01` is DROPPED from the scorch cover.  It is
        # a model atlas whose UV padding is the source of the pale flat slabs the critic found
        # here, and the burnt-ground scan already cuts real char twigs and straw -- measured,
        # its share of this atlas was 0.28 and every flat-and-straight region the audit found
        # in it came from that share.  Kept in `gc_litter`, where the filter clears it.
        "sources": (
            _weigh(CHAR_STALKS, 0.62),
            _weigh(GRASS_TUFTS, 0.38),
        ),
        "per_cell": (3, 6),
        "stamp_span": (0.55, 0.95),
        "rooted": True,
        "upright_deg": 26.0,
    },
    {
        "key": "gc_reeds",
        "alphaRef": 25,
        "groundType": "GRASS",
        "size": 1024,
        "cc0": "grass_medium_02",
        "kind": "grass",
        "grid": (4, 4),
        "tint": (0.96, 1.0, 0.80),
        "sources": (_weigh(REED_BLADES, 0.75), _weigh(GRASS_TUFTS, 0.25)),
        "per_cell": (2, 4),
        "stamp_span": (0.70, 1.0),
        "rooted": True,
        "upright_deg": 14.0,
    },
    # --- bark / wood (opaque, but NATURE + alphaTest so the strict foliage classifier of
    #     study/census_lib.foliage_class counts them, exactly as design §4.5 intends) -----
    {
        "key": "f_pine_bark",
        "alphaRef": 84,
        "groundType": "WOOD",
        "size": 1024,
        "cc0": "pine_bark",
        "kind": "tile",
        "grid": None,
        "tint": (1.0, 1.0, 1.0),
    },
    {
        "key": "f_fir_bark",
        "alphaRef": 84,
        "groundType": "WOOD",
        "size": 1024,
        "cc0": "bark_brown_02",
        "kind": "tile",
        "grid": None,
        "tint": (1.0, 1.0, 1.0),
    },
    {
        "key": "f_knotted_bark",
        "alphaRef": 84,
        "groundType": "WOOD",
        "size": 1024,
        "cc0": "knotted_pine_bark",
        "kind": "tile",
        "grid": None,
        "tint": (1.0, 1.0, 1.0),
    },
    # r11 (critic B10-1).  THE BRANCH MATERIAL.  Until this round every generated conifer
    # carried exactly two materials, `*_bark` and `*_twig_*`, so the whole branch armature was
    # drawn in the TRUNK's tile and `stock_census.classify` -- which is what every published
    # `branch_tris` is read through -- returned "wood" for it: `branch_tris == 0` on all
    # sixteen conifers, where italy's scots pine reads 276 and WCUSA's radiata 1,106.  A
    # statistic that is structurally zero cannot see a regression, and this one did not.
    #
    # The name matters and is not decoration: `classify` keys on the substring `branches`, so
    # this material is counted as BRANCH by the census and, in `bare_wood_silhouette`'s
    # armature mask, is removed from the silhouette exactly as bark is.  It is a `tile`, so it
    # ships a fully opaque opacity map and the critic's own side view paints it at coverage
    # 1.0 -- identical to the wood it replaces.  Nothing about the measurement gets easier.
    #
    # `knotted_pine_bark` at 512 with a darker, greyer tint is neither pine's trunk tile
    # (`pine_bark`) nor fir's (`bark_brown_02`): a limb reads greyer and finer than the bole of
    # either, and at 512 over a 0.4 m repeat it is ~0.8 mm per texel, the same band the twig
    # cards are sized to.
    {
        "key": "f_branches",
        "alphaRef": 84,
        "groundType": "WOOD",
        "size": 512,
        "cc0": "knotted_pine_bark",
        "kind": "tile",
        "grid": None,
        "tint": (0.70, 0.665, 0.60),
    },
    {
        "key": "f_deadwood",
        "alphaRef": 84,
        "groundType": "WOOD",
        "size": 1024,
        "cc0": "knotted_pine_bark",
        "kind": "tile",
        "grid": None,
        "tint": (0.86, 0.82, 0.76),
    },
    {
        "key": "f_kindling_bark",
        "alphaRef": 84,
        "groundType": "WOOD",
        "size": 1024,
        "cc0": "knotted_pine_bark",
        "kind": "tile",
        "grid": None,
        "tint": (0.72, 0.62, 0.54),
    },
)

#: Rock and cover-shape materials: opaque PBR, ``annotation ROCK``, no alphaTest, so the
#: foliage classifier correctly leaves them out of QB-13's population.
ROCK_MATERIALS: tuple[dict, ...] = (
    {"key": "r_boulder", "size": 1024, "cc0": "boulder_01", "annotation": "ROCK"},
    {"key": "r_namaqualand", "size": 1024, "cc0": "namaqualand_boulder_03", "annotation": "ROCK"},
    {"key": "r_mossy", "size": 1024, "cc0": "rock_moss_set_01", "annotation": "ROCK"},
    {"key": "r_cliff", "size": 1024, "cc0": "rock_face_01", "annotation": "ROCK"},
    {"key": "r_scree", "size": 512, "cc0": "rock_07", "annotation": "ROCK"},
    {"key": "r_crag", "size": 1024, "cc0": "mountainside", "annotation": "ROCK"},
    {"key": "gcs_ash", "size": 512, "cc0": "burned_ground_01", "annotation": "ROCK"},
    {"key": "gcs_pebble", "size": 512, "cc0": "rock_09", "annotation": "ROCK"},
    {"key": "gcs_debris", "size": 512, "cc0": "knotted_pine_bark", "annotation": "ROCK"},
)

MATERIALS: tuple[dict, ...] = FOLIAGE_MATERIALS + ROCK_MATERIALS


def material_name(key: str) -> str:
    return f"{LEVEL_ID}_{key}"


def texture_relative(key: str, role: str) -> str:
    """Path of one cooked map relative to the level root."""
    directory = COVER_DIR if key.startswith(("gc_", "gcs_")) else _material_dir(key)
    return f"{directory}/{LEVEL_ID}_{key}_{ROLE_SUFFIX[role]}.png"


def _material_dir(key: str) -> str:
    if key.startswith("r_"):
        return ROCKS_DIR
    if key.startswith(
        (
            "f_pine_twig",
            "f_fir_twig",
            "f_sapling_twig",
            "f_pine_bark",
            "f_fir_bark",
            "f_dwarf_pine",
            "f_branches",  # r11: the branch material lives with the trees it clothes
        )
    ):
        return TREES_DIR
    if key.startswith(("f_knotted_bark", "f_deadwood", "f_kindling_bark")):
        return DEADWOOD_DIR
    return CARDS_DIR


#: Which roles each material kind ships.  Cut-outs add the opacity map; tiles do not.
#: MEASURED on the sentinel (B3 forest boot 2): a Material with ``alphaTest: true`` and NO
#: ``opacityMap`` does not render -- every trunk came back wearing the engine's checkered
#: "IMPORTANT" placeholder while the twig cards beside them (same file, same level, with an
#: opacity map) were perfect.  The five WOOD materials of design §4.5 carry alphaTest because
#: that is what puts them in the strict foliage classifier's population (QB-13 counts 22), so
#: they ship a fully opaque opacity map rather than dropping the flag.
MATERIAL_ROLES = {
    "twig": ("base", "normal", "roughness", "ao", "opacity"),
    "model_card": ("base", "normal", "roughness", "ao", "opacity"),
    "grass": ("base", "normal", "roughness", "ao", "opacity"),
    "tile": ("base", "normal", "roughness", "ao", "opacity"),
    "rock": ("base", "normal", "roughness", "ao"),
}


# --------------------------------------------------------------------------------------
# Species (design §4.2, rows 1-54)
# --------------------------------------------------------------------------------------
# Field reference
#   key        datablock/DAE suffix -> ericrolph_hot_potato_arena_f_<key>
#   family     drives the wind/physics preset and the generator branch
#   build      "conifer" | "snag" | "model" | "card"
#   height_m   the design's "height / size" column; models are scaled to it
#   details    ((pixel size, triangle budget), ...) highest px first
#   bb         ships bb_autobillboard25 + BB::DIM=128
#   null       nulldetail pixel size (every forest DAE ships one, tables.DAE_CENSUS)
#   colmesh    Colmesh triangle budget; 0 = drive-through by design (cards, debris)
#   radius/mass/rigidity  TSForestItemData physics (design §4.2 right column)
#   materials  ((slot, material key), ...) - slot names become the DAE material symbols
#   source     for build="model": (cc0 id, part index or None, mirror)
#   dir        DAE directory
_TREE = dict(family="conifer", build="conifer", dir=TREES_DIR)
_SNAG = dict(family="snag", build="snag", dir=TREES_DIR)
_DEAD = dict(family="deadwood", build="model", dir=DEADWOOD_DIR)
_CARD = dict(family="card", build="card", dir=CARDS_DIR)
_ROCK = dict(family="rock", build="model", dir=ROCKS_DIR)

# r11 (critic B10-1): slot 0 trunk bark, slot 1 BRANCH, slot 2 twig cards.  The twig atlas
# stays LAST because `build_species` reads the cell grid off `materials[-1]`, and the Colmesh
# still takes `materials[:1]`, so only the generated conifers see the new slot.
_BRANCH = ("branch", "f_branches")
_PINE_MATS = (("bark", "f_pine_bark"), _BRANCH, ("twig", "f_pine_twig_a"))
_PINE_MATS_B = (("bark", "f_pine_bark"), _BRANCH, ("twig", "f_pine_twig_b"))
_FIR_MATS = (("bark", "f_fir_bark"), _BRANCH, ("twig", "f_fir_twig_a"))
_FIR_MATS_B = (("bark", "f_fir_bark"), _BRANCH, ("twig", "f_fir_twig_b"))
_SAP_MATS = (("bark", "f_pine_bark"), _BRANCH, ("twig", "f_sapling_twig"))
_DWARF_MATS = (("bark", "f_pine_bark"), _BRANCH, ("twig", "f_dwarf_pine"))
_SNAG_MATS = (("bark", "f_knotted_bark"),)

SPECIES: tuple[dict, ...] = (
    # 1-3 tall pines --------------------------------------------------------------------
    dict(
        _TREE,
        key="pine_tall_a",
        height_m=28.0,
        details=((600, 13000), (300, 9600), (100, 6800)),
        bb=True,
        null=8,
        colmesh=24,
        radius=0.55,
        mass=12,
        rigidity=10.2,
        materials=_PINE_MATS,
    ),
    dict(
        _TREE,
        key="pine_tall_b",
        height_m=30.0,
        details=((600, 13000), (300, 9600), (100, 6800)),
        bb=True,
        null=8,
        colmesh=24,
        radius=0.55,
        mass=12,
        rigidity=10.2,
        materials=_PINE_MATS_B,
    ),
    dict(
        _TREE,
        key="pine_tall_c",
        height_m=26.0,
        details=((600, 13000), (300, 9600), (100, 6800)),
        bb=True,
        null=8,
        colmesh=24,
        radius=0.55,
        mass=12,
        rigidity=10.2,
        materials=_PINE_MATS,
    ),
    # 4-5 mid pines ---------------------------------------------------------------------
    dict(
        _TREE,
        key="pine_mid_a",
        height_m=18.0,
        details=((600, 5590), (300, 4110), (100, 3000)),
        bb=True,
        null=8,
        colmesh=20,
        radius=0.4,
        mass=8,
        rigidity=12.0,
        materials=_PINE_MATS,
    ),
    dict(
        _TREE,
        key="pine_mid_b",
        height_m=15.0,
        details=((600, 5590), (300, 4110), (100, 3000)),
        bb=True,
        null=8,
        colmesh=20,
        radius=0.4,
        mass=8,
        rigidity=12.0,
        materials=_PINE_MATS_B,
    ),
    # 6-8 tall firs ---------------------------------------------------------------------
    dict(
        _TREE,
        key="fir_tall_a",
        height_m=26.0,
        details=((600, 8200), (300, 5800), (100, 4550)),
        bb=True,
        null=8,
        colmesh=24,
        radius=0.5,
        mass=11,
        rigidity=10.2,
        materials=_FIR_MATS,
    ),
    dict(
        _TREE,
        key="fir_tall_b",
        height_m=24.0,
        details=((600, 8200), (300, 5800), (100, 4550)),
        bb=True,
        null=8,
        colmesh=24,
        radius=0.5,
        mass=11,
        rigidity=10.2,
        materials=_FIR_MATS_B,
    ),
    dict(
        _TREE,
        key="fir_tall_c",
        height_m=22.0,
        details=((600, 8200), (300, 5800), (100, 4550)),
        bb=True,
        null=8,
        colmesh=24,
        radius=0.5,
        mass=11,
        rigidity=10.2,
        materials=_FIR_MATS,
    ),
    # 9-10 mid firs ---------------------------------------------------------------------
    dict(
        _TREE,
        key="fir_mid_a",
        height_m=16.0,
        details=((600, 4820), (300, 3850), (100, 2554)),
        bb=True,
        null=8,
        colmesh=20,
        radius=0.4,
        mass=7,
        rigidity=12.0,
        materials=_FIR_MATS,
    ),
    dict(
        _TREE,
        key="fir_mid_b",
        height_m=13.0,
        details=((600, 4820), (300, 3850), (100, 2554)),
        bb=True,
        null=8,
        colmesh=20,
        radius=0.4,
        mass=7,
        rigidity=12.0,
        materials=_FIR_MATS_B,
    ),
    # 11-13 pine saplings ---------------------------------------------------------------
    dict(
        _TREE,
        key="pine_sapling_a",
        height_m=5.0,
        details=((400, 1600), (150, 1052)),
        bb=True,
        null=6,
        colmesh=12,
        radius=0.2,
        mass=2,
        rigidity=20.0,
        materials=_SAP_MATS,
    ),
    dict(
        _TREE,
        key="pine_sapling_b",
        height_m=3.5,
        details=((400, 1600), (150, 1052)),
        bb=True,
        null=6,
        colmesh=12,
        radius=0.2,
        mass=2,
        rigidity=20.0,
        materials=_SAP_MATS,
    ),
    dict(
        _TREE,
        key="pine_sapling_c",
        height_m=2.2,
        details=((400, 1600), (150, 1052)),
        bb=True,
        null=6,
        colmesh=12,
        radius=0.2,
        mass=2,
        rigidity=20.0,
        materials=_SAP_MATS,
    ),
    # 14-15 fir saplings ----------------------------------------------------------------
    dict(
        _TREE,
        key="fir_sapling_a",
        height_m=4.5,
        details=((400, 1500), (150, 986)),
        bb=True,
        null=6,
        colmesh=12,
        radius=0.2,
        mass=2,
        rigidity=20.0,
        materials=_DWARF_MATS,
    ),
    dict(
        _TREE,
        key="fir_sapling_b",
        height_m=2.8,
        details=((400, 1500), (150, 986)),
        bb=True,
        null=6,
        colmesh=12,
        radius=0.2,
        mass=2,
        rigidity=20.0,
        materials=_DWARF_MATS,
    ),
    # 16 dwarf alpine pine --------------------------------------------------------------
    dict(
        _TREE,
        key="dwarf_pine_alpine",
        height_m=3.0,
        details=((400, 1300), (150, 852)),
        bb=True,
        null=6,
        colmesh=10,
        radius=0.3,
        mass=3,
        rigidity=30.0,
        materials=_DWARF_MATS,
        wind_flag=True,
    ),
    # 17-18 snags -----------------------------------------------------------------------
    dict(
        _SNAG,
        key="snag_a",
        height_m=18.0,
        details=((500, 700), (200, 300)),
        bb=True,
        null=6,
        colmesh=16,
        radius=0.4,
        mass=9,
        rigidity=40.0,
        materials=_SNAG_MATS,
    ),
    dict(
        _SNAG,
        key="snag_b",
        height_m=12.0,
        details=((500, 700), (200, 300)),
        bb=True,
        null=6,
        colmesh=16,
        radius=0.4,
        mass=9,
        rigidity=40.0,
        materials=_SNAG_MATS,
    ),
    # 19-21 fallen logs -----------------------------------------------------------------
    dict(
        _DEAD,
        key="fallen_log_a",
        height_m=10.7,
        details=((500, 1200), (200, 500), (80, 180)),
        bb=True,
        null=6,
        colmesh=160,
        solid="voxel",
        radius=1.2,
        mass=30,
        rigidity=50.0,
        materials=(("wood", "f_deadwood"),),
        source=("dead_tree_trunk", None, False),
        lie_down=True,
    ),
    dict(
        _DEAD,
        key="fallen_log_b",
        height_m=8.1,
        details=((500, 1200), (200, 500), (80, 180)),
        bb=True,
        null=6,
        colmesh=160,
        solid="voxel",
        radius=1.2,
        mass=30,
        rigidity=50.0,
        materials=(("wood", "f_deadwood"),),
        source=("dead_tree_trunk_02", None, False),
        lie_down=True,
    ),
    dict(
        _DEAD,
        key="fallen_log_c",
        height_m=7.6,
        details=((500, 1200), (200, 500), (80, 180)),
        bb=True,
        null=6,
        colmesh=160,
        solid="voxel",
        radius=1.2,
        mass=30,
        rigidity=50.0,
        materials=(("wood", "f_deadwood"),),
        source=("dead_tree_trunk", None, True),
        lie_down=True,
    ),
    # 22-23 stumps ----------------------------------------------------------------------
    dict(
        _DEAD,
        key="stump_a",
        height_m=2.3,
        details=((400, 800), (150, 300)),
        bb=True,
        null=6,
        colmesh=100,
        solid="voxel",
        radius=0.7,
        mass=20,
        rigidity=50.0,
        materials=(("wood", "f_deadwood"),),
        source=("tree_stump_01", None, False),
    ),
    dict(
        _DEAD,
        key="stump_b",
        height_m=2.1,
        details=((400, 800), (150, 300)),
        bb=True,
        null=6,
        colmesh=100,
        solid="voxel",
        radius=0.7,
        mass=20,
        rigidity=50.0,
        materials=(("wood", "f_deadwood"),),
        source=("tree_stump_02", None, False),
    ),
    # 24-25 root plates -----------------------------------------------------------------
    dict(
        _DEAD,
        key="windthrow_roots",
        height_m=4.3,
        # r10: 1200 -> 3000 on the top detail.  The husk gate reads this shape at solidity 0.191
        # against 0.287 for the largest loose part of its own `pine_roots` scan, and the cause is
        # the decimator, measured: a500 (1,182 tris) 0.191, a200 (394) 0.154, the 156-tri Colmesh
        # 0.329 -- a fan of centimetre-thick roots loses volume every time it is halved.
        details=((500, 3000), (200, 900)),
        bb=True,
        null=6,
        colmesh=160,
        solid="voxel",
        radius=1.5,
        mass=25,
        rigidity=50.0,
        materials=(("wood", "f_deadwood"),),
        source=("pine_roots", None, False),
    ),
    dict(
        _DEAD,
        key="root_cluster",
        height_m=6.2,
        details=((500, 1000), (200, 400)),
        bb=True,
        null=6,
        colmesh=160,
        solid="voxel",
        radius=1.5,
        mass=25,
        rigidity=50.0,
        materials=(("wood", "f_deadwood"),),
        source=("root_cluster_01", None, False),
    ),
    # 26-27 debris (drive-through: no Colmesh, by design) --------------------------------
    dict(
        _DEAD,
        key="bark_debris",
        height_m=2.4,
        details=((300, 500), (100, 160)),
        bb=True,
        null=6,
        colmesh=0,
        radius=0.6,
        mass=4,
        rigidity=50.0,
        materials=(("wood", "f_deadwood"),),
        source=("bark_debris_01", None, False),
    ),
    dict(
        _DEAD,
        key="branch_pile",
        height_m=3.2,
        details=((300, 500), (100, 160)),
        bb=True,
        null=6,
        colmesh=0,
        radius=0.8,
        mass=4,
        rigidity=50.0,
        materials=(("wood", "f_deadwood"),),
        source=("dry_branches_medium_01", None, False),
    ),
    # 28-31 shrubs (polygon leaves replaced by cards, design §4.1) -----------------------
    # r12 (critic B11-5): shrub_01/02/03 hang their cards on a DOME (`blender_forest.
    # card_cluster_mesh`, shape "dome"): an ellipsoid widest at half height with every card's
    # front face OUTWARD.  The r2 "bush" is a cone -- spread 0.42 h at the base falling to
    # nothing at the top -- and its cards are wound with the front toward the centre, which is
    # what the critic's atlas sheet shows ("chrome-yellow cones") and what the imposter's
    # normal atlas records (b3/r12/normals_eyes_r12_before.json).  shrub_04 keeps "bush"
    # untouched: outside this revision's write set, and its DAE stays byte-reproducible.
    dict(
        _CARD,
        key="shrub_01",
        height_m=2.6,
        # r13 (the user, 2026-09-16): a 2.6-5.3 m shrub is 120 px tall at ~30 m, so the
        # two-step chain handed it to its billboard just past the verge - flat half-discs
        # with no depth on every meadow.  A third detail keeps the mesh out to ~100 m.
        details=((300, 700), (120, 468), (40, 320)),  # 700/468 = 1.50x, 468/320 = 1.46x
        bb=True,
        null=6,
        colmesh=0,
        radius=0.5,
        mass=2,
        rigidity=10.0,
        # D7 (the user, twice): the four shrubs were leaf cards and NOTHING else -- one
        # material, no stem geometry, so every crown floated.  Slot 0 is now bark and the
        # cards move to slot 1.  `f_knotted_bark` is the snags' bark, already shipped and
        # already cooked, so the stem costs no new texture and no new material.
        materials=(("bark", "f_knotted_bark"), ("leaf", "f_shrub_leaf_01")),
        # 8 % of each detail's triangles.  A SHARE, not a count: see `stem_layout`.
        stem=0.08,
        card_shape="dome",
    ),
    dict(
        _CARD,
        key="shrub_02",
        height_m=5.3,
        # r13 (the user, 2026-09-16): a 2.6-5.3 m shrub is 120 px tall at ~30 m, so the
        # two-step chain handed it to its billboard just past the verge - flat half-discs
        # with no depth on every meadow.  A third detail keeps the mesh out to ~100 m.
        details=((300, 700), (120, 468), (40, 320)),  # 700/468 = 1.50x, 468/320 = 1.46x
        bb=True,
        null=6,
        colmesh=0,
        radius=0.5,
        mass=2,
        rigidity=10.0,
        # D7 (the user, twice): the four shrubs were leaf cards and NOTHING else -- one
        # material, no stem geometry, so every crown floated.  Slot 0 is now bark and the
        # cards move to slot 1.  `f_knotted_bark` is the snags' bark, already shipped and
        # already cooked, so the stem costs no new texture and no new material.
        materials=(("bark", "f_knotted_bark"), ("leaf", "f_shrub_leaf_02")),
        # 8 % of each detail's triangles.  A SHARE, not a count: see `stem_layout`.
        stem=0.08,
        card_shape="dome",
        # r12: a 5.3 m plant on the same 350-card budget as the 2.0-2.6 m shrubs hangs a fifth
        # of their card area per metre of silhouette, which is the other half of why its
        # imposter was a skeleton.  Leaf-CLUSTER cards up to 1.1 m across (0.21 of its height;
        # r2's complaint was 2.3-4.2 m cards at 0.43-0.80) -- only this species.
        card_half_m=(0.26, 0.55),
    ),
    dict(
        _CARD,
        key="shrub_03",
        height_m=2.0,
        # r13 (the user, 2026-09-16): a 2.6-5.3 m shrub is 120 px tall at ~30 m, so the
        # two-step chain handed it to its billboard just past the verge - flat half-discs
        # with no depth on every meadow.  A third detail keeps the mesh out to ~100 m.
        details=((300, 700), (120, 468), (40, 320)),  # 700/468 = 1.50x, 468/320 = 1.46x
        bb=True,
        null=6,
        colmesh=0,
        radius=0.5,
        mass=2,
        rigidity=10.0,
        # D7 (the user, twice): the four shrubs were leaf cards and NOTHING else -- one
        # material, no stem geometry, so every crown floated.  Slot 0 is now bark and the
        # cards move to slot 1.  `f_knotted_bark` is the snags' bark, already shipped and
        # already cooked, so the stem costs no new texture and no new material.
        materials=(("bark", "f_knotted_bark"), ("leaf", "f_shrub_leaf_03")),
        # 8 % of each detail's triangles.  A SHARE, not a count: see `stem_layout`.
        stem=0.08,
        card_shape="dome",
    ),
    dict(
        _CARD,
        key="shrub_04",
        height_m=2.2,
        # r13 (the user, 2026-09-16): a 2.6-5.3 m shrub is 120 px tall at ~30 m, so the
        # two-step chain handed it to its billboard just past the verge - flat half-discs
        # with no depth on every meadow.  A third detail keeps the mesh out to ~100 m.
        details=((300, 700), (120, 468), (40, 320)),  # 700/468 = 1.50x, 468/320 = 1.46x
        bb=True,
        null=6,
        colmesh=0,
        radius=0.5,
        mass=2,
        rigidity=10.0,
        # D7 (the user, twice): the four shrubs were leaf cards and NOTHING else -- one
        # material, no stem geometry, so every crown floated.  Slot 0 is now bark and the
        # cards move to slot 1.  `f_knotted_bark` is the snags' bark, already shipped and
        # already cooked, so the stem costs no new texture and no new material.
        materials=(("bark", "f_knotted_bark"), ("leaf", "f_shrub_leaf_04")),
        # 8 % of each detail's triangles.  A SHARE, not a count: see `stem_layout`.
        stem=0.08,
        # D7: the last shrub still on the r12 "bush" arrangement, which r13 replaced on the
        # other three because a regular ellipsoid of dense cards reads as a smooth ball and
        # because "bush" winds every card's FRONT toward the plant's centre, so the imposter
        # bake records back-facing normals and the engine lights it from the wrong side.  It
        # was left out then to keep its DAE byte-reproducible; this revision re-exports all
        # four anyway, so the reason has expired.
        card_shape="dome",
    ),
    # 32-33 ferns -----------------------------------------------------------------------
    dict(
        _CARD,
        key="fern_a",
        height_m=2.6,
        details=((300, 420), (120, 282)),
        bb=True,
        null=6,
        colmesh=0,
        radius=0.5,
        mass=1,
        rigidity=10.0,
        materials=(("leaf", "f_fern"),),
        card_shape="rosette",
    ),
    dict(
        _CARD,
        key="fern_b",
        height_m=1.6,
        details=((300, 420), (120, 282)),
        bb=True,
        null=6,
        colmesh=0,
        radius=0.4,
        mass=1,
        rigidity=10.0,
        materials=(("leaf", "f_fern"),),
        card_shape="rosette",
    ),
    # 34 reeds --------------------------------------------------------------------------
    # (design 4.3 counts "54 forest items" among the 68 BB::DIM=128 pairs, so the reed clump
    #  is billboarded too even though 4.2's abbreviated table does not repeat "+ bb25" on it)
    dict(
        _CARD,
        key="reed_clump",
        height_m=2.0,
        details=((200, 160), (80, 108)),
        bb=True,
        null=6,
        colmesh=0,
        radius=0.4,
        mass=1,
        rigidity=10.0,
        materials=(("leaf", "f_reed"),),
        card_shape="tuft",
    ),
    # 35-41 boulders --------------------------------------------------------------------
    dict(
        _ROCK,
        key="boulder_forest_a",
        height_m=4.6,
        details=((600, 2000), (250, 700), (100, 240)),
        bb=True,
        null=4,
        colmesh=300,
        solid="voxel",
        radius=2.3,
        mass=200,
        rigidity=100.0,
        materials=(("rock", "r_boulder"),),
        source=("boulder_01", None, False),
        snap=True,
    ),
    dict(
        _ROCK,
        key="boulder_forest_b",
        height_m=2.2,
        details=((600, 2000), (250, 700), (100, 240)),
        bb=True,
        null=4,
        colmesh=300,
        solid="voxel",
        radius=2.0,
        mass=200,
        rigidity=100.0,
        materials=(("rock", "r_boulder"),),
        source=("boulder_01", None, True),
        snap=True,
    ),
    dict(
        _ROCK,
        key="nq_boulder_02",
        height_m=7.6,
        details=((600, 2000), (250, 700), (100, 240)),
        bb=True,
        null=4,
        colmesh=300,
        solid="voxel",
        radius=3.8,
        mass=200,
        rigidity=100.0,
        materials=(("rock", "r_namaqualand"),),
        source=("namaqualand_boulder_02", None, False),
        snap=True,
    ),
    dict(
        _ROCK,
        key="nq_boulder_03",
        height_m=6.1,
        details=((600, 2000), (250, 700), (100, 240)),
        bb=True,
        null=4,
        colmesh=300,
        solid="voxel",
        radius=3.0,
        mass=200,
        rigidity=100.0,
        materials=(("rock", "r_namaqualand"),),
        source=("namaqualand_boulder_03", None, False),
        snap=True,
    ),
    dict(
        _ROCK,
        key="nq_boulder_04",
        height_m=6.3,
        details=((600, 2000), (250, 700), (100, 240)),
        bb=True,
        null=4,
        colmesh=300,
        solid="voxel",
        radius=3.2,
        mass=200,
        rigidity=100.0,
        materials=(("rock", "r_namaqualand"),),
        source=("namaqualand_boulder_04", None, False),
        snap=True,
    ),
    dict(
        _ROCK,
        key="nq_boulder_05",
        height_m=5.4,
        details=((600, 2000), (250, 700), (100, 240)),
        bb=True,
        null=4,
        colmesh=300,
        solid="voxel",
        radius=2.7,
        mass=200,
        rigidity=100.0,
        materials=(("rock", "r_namaqualand"),),
        source=("namaqualand_boulder_05", None, False),
        snap=True,
    ),
    dict(
        _ROCK,
        key="nq_boulder_06",
        height_m=6.0,
        details=((600, 2000), (250, 700), (100, 240)),
        bb=True,
        null=4,
        colmesh=300,
        solid="voxel",
        radius=3.0,
        mass=200,
        rigidity=100.0,
        materials=(("rock", "r_namaqualand"),),
        source=("namaqualand_boulder_06", None, False),
        snap=True,
    ),
    # 42-46 mossy rocks (rock_moss_set_01 split 3, _02 split 2) --------------------------
    dict(
        _ROCK,
        key="mossy_rock_a",
        height_m=12.0,
        details=((500, 1500), (200, 500), (80, 180)),
        bb=True,
        null=4,
        colmesh=300,
        solid="voxel",
        radius=5.0,
        mass=200,
        rigidity=100.0,
        materials=(("rock", "r_mossy"),),
        source=("rock_moss_set_01", 0, False),
        snap=True,
    ),
    dict(
        _ROCK,
        key="mossy_rock_b",
        height_m=7.0,
        details=((500, 1500), (200, 500), (80, 180)),
        bb=True,
        null=4,
        colmesh=300,
        solid="voxel",
        radius=3.5,
        mass=200,
        rigidity=100.0,
        materials=(("rock", "r_mossy"),),
        source=("rock_moss_set_01", 1, False),
        snap=True,
    ),
    dict(
        _ROCK,
        key="mossy_rock_c",
        height_m=5.0,
        details=((500, 1500), (200, 500), (80, 180)),
        bb=True,
        null=4,
        colmesh=300,
        solid="voxel",
        # r10, and this row's history is worth keeping.  r9 shipped this rock at genus 2 and
        # justified it with a LOGIC ERROR the critic caught (N-2): `voxel_solid`'s closing only
        # ever ADDS material, so a handle surviving it proves nothing about the handle's width.
        # The r10 root cause is upstream of all of that: `import_model`'s `part` index was
        # selecting a UV CHART, not a rock (`rock_moss_set_01` has 6 meshes and 71 loose
        # pieces), so what was voxelised here was a 4,044-poly fragment of the 10,996-poly
        # scan -- which is where the handles, the "24 components at 2 cm", and fill 0.188 /
        # solidity 0.489 came from.  With `part` indexing the glTF's own meshes the rock is
        # **chi 2 at a500, a200, a80 and in its Colmesh** -- a ball, no declaration needed --
        # and the husk gate reads 0.362 / 0.847, above the stock median solidity of 0.801.
        radius=2.5,
        mass=200,
        rigidity=100.0,
        materials=(("rock", "r_mossy"),),
        source=("rock_moss_set_01", 2, False),
        snap=True,
    ),
    dict(
        _ROCK,
        key="mossy_rock_d",
        height_m=4.0,
        details=((500, 1500), (200, 500), (80, 180)),
        bb=True,
        null=4,
        colmesh=300,
        solid="voxel",
        radius=2.0,
        mass=200,
        rigidity=100.0,
        materials=(("rock", "r_mossy"),),
        source=("rock_moss_set_02", 0, False),
        snap=True,
    ),
    dict(
        _ROCK,
        key="mossy_rock_e",
        height_m=3.0,
        details=((500, 1500), (200, 500), (80, 180)),
        bb=True,
        null=4,
        colmesh=300,
        solid="voxel",
        radius=2.0,
        mass=200,
        rigidity=100.0,
        materials=(("rock", "r_mossy"),),
        source=("rock_moss_set_02", 1, False),
        snap=True,
    ),
    # 47-48 cliff outcrops --------------------------------------------------------------
    dict(
        _ROCK,
        key="cliff_outcrop_a",
        height_m=21.0,
        details=((700, 9000), (300, 2600), (100, 600)),
        bb=True,
        null=4,
        # r10: 2000 -> 2600.  `rock_solid.DEPTH_SHARE` 0.35 -> 0.65 (the husk fix) makes the
        # body about 85 % more surface, and a fixed Colmesh budget spread over more surface is
        # a coarser hull: `cliff_outcrop_b`'s car-band phantom MAX went 0.135 -> 0.344 m at
        # 2000, over the adopted 0.25 bar, while p50/p90 stayed at 0.023/0.061.  The collision
        # budget follows the body.
        colmesh=2600,
        # D7 / amendment A7 (2026-09-17, the user's second report of the same rocks, with a
        # screenshot: "they're not water tight and they have very strange slices through them
        # that shouldn't be there").  A5 measured the cause -- the face solid's skirt is cut
        # into ROWS and a row is a ledge -- and left it unfixed after four attempts.  What
        # fixes it is the pair A5 never combined: `rock_solid.SKIRT_ROW_SHARE` 0.05 -> 0.008
        # so the ledges go, THEN the voxel remesher over the finished body, which is this
        # route.  The handles that defeated the remesh-only attempt WERE the ledges.  Sliver
        # area at the shipped budgets falls 0.477 -> 0.014 / 0.326 -> 0.019 / 0.228 -> 0.010,
        # the husk gate passes on all three, and the shapes move under a metre where the
        # rejected attempt moved 2.1 m.  Full table and the rejected alternatives (plain
        # `voxel`, and re-sourcing onto closed scans -- refused on the renders, they are
        # boulders) in `rock_solid.SKIRT_ROW_SHARE`.
        #
        # NOT what an earlier draft of this comment claimed: `h_rock_face_01` is NOT the same
        # CC0 scan.  `hearth_spec.STONE_SOURCES` re-sources that slot to `rock_07` -- same slot
        # name, different scan -- which is exactly why the hearth could take the voxel route
        # and these three cannot.
        solid="face_voxel",
        # D7: the ONE handle the remesh leaves is the scan's own arch.  `rock_face_01` reads
        # genus 4 at source, and the proof that this one is REAL rather than a topological
        # crumb is that it survives the whole closing ladder: `voxel_solid` only stops when
        # `chi == 2 * shells`, so this shape ran every step to 16 voxels and the handle is
        # still there -- an opening wider than 2 x 16 x 0.13 m, about 4 m.  The cave is
        # visible in the clay renders (`round_records/d7/shots/`).
        #
        # This is the FIRST use of `solid_genus` (the gate has always had it; `mossy_rock_c`
        # declared genus 2 in r9 and the declaration turned out to be covering a `part`-index
        # bug, so r10 fixed the bug and withdrew it -- read that row before adding another).
        # The bar it has to meet is the gate's own: measured, closed, manifold topology, not
        # a way past a failure.  Here it is one arch in a cliff, closed at chi 0 with zero
        # boundary and zero non-manifold edges.  `cliff_outcrop_b` and `crag` come out genus 0
        # and declare nothing.
        solid_genus=1,
        # D7: this shape's own row share and body depth.  Both were swept through the REAL
        # builder and judged on the SHIPPED bytes, because the offline probe measures the BODY
        # and all three gates read the DETAILS -- `seal_to` and `ensure_solid` decimate and
        # re-close each LOD, which moves every number: at rows 0.008 the body is genus 1 and
        # its details are genus 3, and at rows 0.014 / depth 0.65 the body reads husk
        # 0.681 / 0.341 while the shipped finest visual reads 0.649 / 0.252 and FAILS.
        #
        # Three gates have to pass together and they pull against each other -- a finer skirt
        # and a deeper body each buy one and cost another (`d7/sweep_real_*.json`):
        #
        #   rows / depth   genus  solidity  fill   sliver  verdict
        #   0.014 / 0.65     1     0.649    0.252  0.0162  husk FAIL
        #   0.020 / 0.65     3     0.663    0.294  0.0173  ok, but 3 handles
        #   0.025 / 0.65     2     0.667    0.289  0.0170  ok, but 2 handles
        #   0.014 / 0.95     6     0.704    0.366  0.0129  ok, but 6 handles
        #   0.025 / 0.70     1     0.675    0.317  0.0185  <- ships, all three clear
        #
        # 0.025 / 0.70 is the only pair measured that lands ONE handle with the husk passing
        # on BOTH of its branches (solidity over 0.67 outright, fill over 0.28 as well) and
        # the sliver area in the band the uncomplained-about rocks occupy.  `cliff_outcrop_b`
        # and `crag` need neither knob: they take the module defaults and come out chi 2 at
        # every detail.
        skirt_rows=0.025,
        body_depth=0.70,
        radius=8.0,
        mass=500,
        rigidity=100.0,
        materials=(("rock", "r_cliff"),),
        source=("rock_face_01", None, False),
        snap=True,
    ),
    dict(
        _ROCK,
        key="cliff_outcrop_b",
        height_m=15.0,
        details=((700, 9000), (300, 2600), (100, 600)),
        bb=True,
        null=4,
        colmesh=2600,
        # D7 / amendment A7 (2026-09-17, the user's second report of the same rocks, with a
        # screenshot: "they're not water tight and they have very strange slices through them
        # that shouldn't be there").  A5 measured the cause -- the face solid's skirt is cut
        # into ROWS and a row is a ledge -- and left it unfixed after four attempts.  What
        # fixes it is the pair A5 never combined: `rock_solid.SKIRT_ROW_SHARE` 0.05 -> 0.008
        # so the ledges go, THEN the voxel remesher over the finished body, which is this
        # route.  The handles that defeated the remesh-only attempt WERE the ledges.  Sliver
        # area at the shipped budgets falls 0.477 -> 0.014 / 0.326 -> 0.019 / 0.228 -> 0.010,
        # the husk gate passes on all three, and the shapes move under a metre where the
        # rejected attempt moved 2.1 m.  Full table and the rejected alternatives (plain
        # `voxel`, and re-sourcing onto closed scans -- refused on the renders, they are
        # boulders) in `rock_solid.SKIRT_ROW_SHARE`.
        #
        # NOT what an earlier draft of this comment claimed: `h_rock_face_01` is NOT the same
        # CC0 scan.  `hearth_spec.STONE_SOURCES` re-sources that slot to `rock_07` -- same slot
        # name, different scan -- which is exactly why the hearth could take the voxel route
        # and these three cannot.
        solid="face_voxel",
        radius=8.0,
        mass=500,
        rigidity=100.0,
        materials=(("rock", "r_cliff"),),
        source=("rock_face_02", None, False),
        snap=True,
    ),
    # 49-51 scree -----------------------------------------------------------------------
    dict(
        _ROCK,
        key="scree_rock_a",
        height_m=6.4,
        details=((400, 1600), (150, 420)),
        bb=True,
        null=4,
        colmesh=160,
        solid="voxel",
        radius=3.0,
        mass=50,
        rigidity=100.0,
        materials=(("rock", "r_scree"),),
        source=("rock_07", None, False),
        snap=True,
    ),
    dict(
        _ROCK,
        key="scree_rock_b",
        height_m=2.2,
        details=((400, 600), (150, 200)),
        bb=True,
        null=4,
        colmesh=120,
        solid="voxel",
        radius=1.5,
        mass=50,
        rigidity=100.0,
        materials=(("rock", "r_scree"),),
        source=("stone_01", None, False),
        snap=True,
    ),
    dict(
        _ROCK,
        key="pebble_cluster",
        height_m=1.1,
        details=((400, 600), (150, 200)),
        bb=True,
        null=4,
        colmesh=80,
        solid="voxel",
        solid_shells=0.02,  # a CLUSTER: every pebble over 2 % of the volume is kept
        radius=1.0,
        mass=50,
        rigidity=100.0,
        materials=(("rock", "r_scree"),),
        source=("rock_09", None, False),
        snap=True,
    ),
    # 52 driftwood ----------------------------------------------------------------------
    dict(
        _ROCK,
        key="driftwood",
        height_m=6.0,
        details=((500, 900), (200, 350)),
        bb=True,
        null=6,
        colmesh=160,
        solid="voxel",
        radius=1.2,
        mass=30,
        rigidity=50.0,
        materials=(("wood", "f_deadwood"),),
        source=("dead_tree_trunk_02", None, True),
        snap=True,
        lie_down=True,
        family="deadwood",
    ),
    # 53 lichen boulder -----------------------------------------------------------------
    dict(
        _ROCK,
        key="lichen_boulder",
        height_m=8.0,
        details=((500, 1500), (200, 500), (80, 180)),
        bb=True,
        null=4,
        colmesh=300,
        solid="voxel",
        radius=3.0,
        mass=200,
        rigidity=100.0,
        materials=(("rock", "r_mossy"),),
        source=("rock_moss_set_01", 2, True),
        snap=True,
    ),
    # 54 crag ---------------------------------------------------------------------------
    dict(
        _ROCK,
        key="crag",
        height_m=41.0,
        # r10: the 150 px detail was 600 triangles.  The crag is 41 m and carries 8,640 m2 of
        # surface, so 590 triangles is 14.6 m2 -- a 5.5 m triangle -- and NO relief a rock can
        # plausibly wear survives a straddle that long: after `SKIRT_RELIEF_WAVELENGTH` 0.35
        # -> 0.14 its worst single plane still read 148.8 m2 against the plate gate's 100
        # (both cliff outcrops came down to 43.3 and 19.8 on the wavelength alone).  1,600 is
        # 5.4 m2 a triangle, the same order as the outcrops' coarsest, and it costs 1,000
        # triangles on a shape with 27 instances.
        details=((900, 6000), (400, 2000), (150, 1600)),
        bb=True,
        null=4,
        colmesh=4000,
        # D7 / amendment A7 (2026-09-17, the user's second report of the same rocks, with a
        # screenshot: "they're not water tight and they have very strange slices through them
        # that shouldn't be there").  A5 measured the cause -- the face solid's skirt is cut
        # into ROWS and a row is a ledge -- and left it unfixed after four attempts.  What
        # fixes it is the pair A5 never combined: `rock_solid.SKIRT_ROW_SHARE` 0.05 -> 0.008
        # so the ledges go, THEN the voxel remesher over the finished body, which is this
        # route.  The handles that defeated the remesh-only attempt WERE the ledges.  Sliver
        # area at the shipped budgets falls 0.477 -> 0.014 / 0.326 -> 0.019 / 0.228 -> 0.010,
        # the husk gate passes on all three, and the shapes move under a metre where the
        # rejected attempt moved 2.1 m.  Full table and the rejected alternatives (plain
        # `voxel`, and re-sourcing onto closed scans -- refused on the renders, they are
        # boulders) in `rock_solid.SKIRT_ROW_SHARE`.
        #
        # NOT what an earlier draft of this comment claimed: `h_rock_face_01` is NOT the same
        # CC0 scan.  `hearth_spec.STONE_SOURCES` re-sources that slot to `rock_07` -- same slot
        # name, different scan -- which is exactly why the hearth could take the voxel route
        # and these three cannot.
        solid="face_voxel",
        radius=15.0,
        mass=1000,
        rigidity=100.0,
        materials=(("rock", "r_crag"),),
        source=("mountainside", None, False),
        snap=True,
    ),
)

#: Wind and damping presets (italy ``cypress_tree`` scaled by height, design §4.2).
WIND_PRESET = {
    "conifer": dict(
        windScale=0.3, branchAmp=0.10, detailAmp=0.08, detailFreq=1.5, trunkBendScale=0.05
    ),
    "snag": dict(
        windScale=0.05, branchAmp=0.02, detailAmp=0.01, detailFreq=0.5, trunkBendScale=0.01
    ),
    "deadwood": dict(
        windScale=0.05, branchAmp=0.02, detailAmp=0.01, detailFreq=0.5, trunkBendScale=0.01
    ),
    "card": dict(
        windScale=0.5, branchAmp=0.15, detailAmp=0.20, detailFreq=2.2, trunkBendScale=0.02
    ),
    "rock": dict(windScale=0.0, branchAmp=0.0, detailAmp=0.0, detailFreq=0.0, trunkBendScale=0.0),
}
#: Small conifers whip more than big ones; the design says "scaled by height".
CONIFER_WIND_BY_HEIGHT = ((20.0, 0.30), (10.0, 0.35), (5.0, 0.40), (0.0, 0.45))
DAMPING_COEFFICIENT = 3.0
TIGHTNESS_COEFFICIENT = 1.0
SHADOW_NULL_DETAIL_SIZE = 40


def wind_fields(species: dict) -> dict:
    preset = dict(WIND_PRESET[species["family"]])
    if species["family"] == "conifer":
        for floor, value in CONIFER_WIND_BY_HEIGHT:
            if species["height_m"] >= floor:
                preset["windScale"] = value
                break
    return preset


# --------------------------------------------------------------------------------------
# GroundCover shape sources (design §4.5; nine unique DAEs shared by the five shape covers)
# --------------------------------------------------------------------------------------
COVER_SHAPES: tuple[dict, ...] = (
    dict(
        key="gcs_ash_lump_a",
        detail_px=100,
        tris=100,
        colmesh=8,
        null=2,
        material="gcs_ash",
        kind="lump",
        seed=1,
    ),
    dict(
        key="gcs_ash_lump_b",
        detail_px=100,
        tris=100,
        colmesh=8,
        null=2,
        material="gcs_ash",
        kind="lump",
        seed=2,
    ),
    dict(
        key="gcs_cinder",
        detail_px=100,
        tris=80,
        colmesh=8,
        null=2,
        material="gcs_ash",
        kind="flake",
        seed=3,
    ),
    dict(
        key="gcs_pebble_a",
        detail_px=120,
        tris=120,
        colmesh=8,
        null=2,
        material="gcs_pebble",
        kind="pebble",
        seed=4,
        source=("rock_07", None, False),
    ),
    dict(
        key="gcs_pebble_b",
        detail_px=120,
        tris=120,
        colmesh=8,
        null=2,
        material="gcs_pebble",
        kind="pebble",
        seed=5,
        source=("rock_09", None, False),
    ),
    dict(
        key="gcs_pebble_c",
        detail_px=120,
        tris=120,
        colmesh=8,
        null=2,
        material="gcs_pebble",
        kind="pebble",
        seed=6,
        source=("stone_01", None, False),
    ),
    dict(
        key="gcs_cone",
        detail_px=100,
        tris=80,
        colmesh=8,
        null=2,
        material="gcs_debris",
        kind="cone",
        seed=7,
    ),
    dict(
        key="gcs_twig",
        detail_px=100,
        tris=60,
        colmesh=8,
        null=2,
        material="gcs_debris",
        kind="twig",
        seed=8,
    ),
    dict(
        key="gcs_bark_chip",
        detail_px=100,
        tris=60,
        colmesh=8,
        null=2,
        material="gcs_debris",
        kind="chip",
        seed=9,
    ),
)


def cover_shape_path(key: str) -> str:
    return f"/levels/{LEVEL_ID}/{COVER_DIR}/{LEVEL_ID}_{key}.dae"


def species_dae_relative(species: dict) -> str:
    return f"{species['dir']}/{LEVEL_ID}_f_{species['key']}.dae"


def species_shape_file(species: dict) -> str:
    return f"/levels/{LEVEL_ID}/{species_dae_relative(species)}"


def datablock_name(species: dict) -> str:
    return f"{LEVEL_ID}_f_{species['key']}"


# --------------------------------------------------------------------------------------
# GroundCover records (design §4.5, tables.GROUND_COVERS)
# --------------------------------------------------------------------------------------
#: billboard atlas cell -> [u, v, w, h] for a `grid` of (cols, rows).
def billboard_uvs(grid: tuple[int, int], index: int) -> list[float]:
    cols, rows = grid
    col, row = index % cols, index // cols
    return [round(col / cols, 6), round(row / rows, 6), round(1.0 / cols, 6), round(1.0 / rows, 6)]


#: italy `small_grass_dry_close_02` gust recipe (study §7.3), design §4.5.
COVER_WIND = dict(
    maxBillboardTiltAngle=40,
    windGustFrequency=0.1,
    windGustLength=0.5,
    windGustStrength=0.2,
    windTurbulenceFrequency=0.6,
    windTurbulenceStrength=0.1,
)

# r2 -- DEV-12, the STACKING deviation.  Design §4.5 puts exactly ONE cover on each terrain
# layer.  Measured over five stock maps, stock stacks 4-17 covers on a single layer (italy's
# `Grass` carries 12), and that stacking is the second-order reason open ground reads thin.
# The five billboard covers are therefore split into TWELVE records at different size bands
# on the SAME layers, drawing from different cells of the same 16-cell atlas (`cell_base`).
# The element budget is SPLIT, not inflated: the billboard total is still 940,000 and the
# grand total still design §4.5's 1.41 M, so density per layer is unchanged and QB-16/18 read
# the design's numbers.  forest_floor now carries 4 covers (3 billboard + the debris shapes),
# meadow 3, alpine / scorch / shore 2 each.
GROUND_COVERS: tuple[dict, ...] = (
    dict(
        name="gc_meadow_grass",
        kind="billboard",
        material="gc_meadow",
        layers=("meadow",),
        types=6,
        cell_base=0,
        size=(0.25, 0.9),
        maxElements=150000,
        radius=60,
        dissolve=35,
    ),
    dict(
        name="gc_meadow_tufts",
        kind="billboard",
        material="gc_meadow",
        layers=("meadow",),
        types=5,
        cell_base=6,
        size=(0.10, 0.32),
        maxElements=90000,
        radius=55,
        dissolve=30,
    ),
    dict(
        name="gc_meadow_seedheads",
        kind="billboard",
        material="gc_meadow",
        layers=("meadow",),
        types=5,
        cell_base=11,
        size=(0.30, 0.70),
        maxElements=60000,
        radius=55,
        dissolve=32,
    ),
    dict(
        name="gc_forest_litter",
        kind="billboard",
        material="gc_litter",
        layers=("forest_floor",),
        types=6,
        cell_base=0,
        size=(0.2, 0.7),
        maxElements=110000,
        radius=50,
        dissolve=30,
    ),
    dict(
        # r9 (DEV-22): the fern carpet thinned 100,000 -> 40,000 and shortened so the needle
        # duff shows between the ferns -- the design's density read as a saturated carpet in
        # every S7 frame.  The litter and the needle mat ARE the duff and keep the design's
        # counts.
        name="gc_forest_ferns",
        kind="billboard",
        material="gc_litter",
        layers=("forest_floor",),
        types=5,
        cell_base=6,
        size=(0.30, 0.78),
        maxElements=40000,
        radius=55,
        dissolve=32,
    ),
    dict(
        name="gc_forest_needlemat",
        kind="billboard",
        material="gc_litter",
        layers=("forest_floor",),
        types=5,
        cell_base=11,
        size=(0.08, 0.26),
        maxElements=90000,
        radius=50,
        dissolve=30,
    ),
    dict(
        name="gc_alpine_turf",
        kind="billboard",
        material="gc_alpine",
        layers=("alpine",),
        types=5,
        cell_base=0,
        size=(0.15, 0.5),
        maxElements=60000,
        radius=50,
        dissolve=30,
    ),
    dict(
        name="gc_alpine_cushion",
        kind="billboard",
        material="gc_alpine",
        layers=("alpine",),
        types=5,
        cell_base=6,
        size=(0.07, 0.2),
        maxElements=40000,
        radius=50,
        dissolve=30,
    ),
    dict(
        name="gc_scorch_stubble",
        kind="billboard",
        material="gc_stubble",
        layers=("scorch",),
        types=5,
        cell_base=0,
        size=(0.15, 0.5),
        maxElements=72000,
        radius=50,
        dissolve=30,
    ),
    dict(
        name="gc_scorch_char",
        kind="billboard",
        material="gc_stubble",
        layers=("scorch",),
        types=5,
        cell_base=6,
        size=(0.07, 0.24),
        maxElements=48000,
        radius=50,
        dissolve=30,
    ),
    dict(
        name="gc_lake_reeds",
        kind="billboard",
        material="gc_reeds",
        layers=("shore",),
        types=5,
        cell_base=0,
        size=(0.6, 1.8),
        maxElements=72000,
        radius=60,
        dissolve=35,
    ),
    dict(
        name="gc_shore_sedge",
        kind="billboard",
        material="gc_reeds",
        layers=("shore",),
        types=5,
        cell_base=6,
        size=(0.2, 0.6),
        maxElements=48000,
        radius=55,
        dissolve=32,
    ),
    dict(
        name="gc_ash_chunks",
        kind="shape",
        layers=("ash",),
        types=3,
        size=(0.15, 0.4),
        maxElements=100000,
        radius=50,
        cull=50,
        shapes=("gcs_ash_lump_a", "gcs_ash_lump_b", "gcs_cinder"),
    ),
    dict(
        name="gc_scree_pebbles",
        kind="shape",
        layers=("scree", "rock"),
        types=3,
        size=(0.2, 0.6),
        maxElements=150000,
        radius=70,
        cull=70,
        shapes=("gcs_pebble_a", "gcs_pebble_b", "gcs_pebble_c"),
    ),
    dict(
        name="gc_forest_debris",
        kind="shape",
        layers=("forest_floor",),
        types=3,
        size=(0.1, 0.35),
        maxElements=120000,
        radius=50,
        cull=50,
        shapes=("gcs_cone", "gcs_twig", "gcs_bark_chip"),
    ),
    dict(
        name="gc_trail_gravel",
        kind="shape",
        layers=("trail",),
        types=3,
        size=(0.08, 0.2),
        maxElements=60000,
        radius=50,
        cull=50,
        shapes=("gcs_pebble_b", "gcs_pebble_c", "gcs_pebble_a"),
    ),
    dict(
        name="gc_hearth_grit",
        kind="shape",
        layers=("hearth",),
        types=2,
        size=(0.1, 0.3),
        maxElements=40000,
        radius=50,
        cull=50,
        shapes=("gcs_cinder", "gcs_ash_lump_b"),
    ),
)

#: design §4.2: one ForestWindEmitter with Utah's values at world(300 deg, 420 m).
WIND_EMITTER = dict(
    name=f"{LEVEL_ID}_wind",
    bearing_deg=300.0,
    radius_m=420.0,
    z_offset=20.0,
    strength=0.5,
    gustFrequency=2,
    gustStrength=3,
    gustWobbleStrength=3,
    gustYawAngle=50,
    turbulenceStrength=5.25,
)


# --------------------------------------------------------------------------------------
# Placement (design §4.4)
# --------------------------------------------------------------------------------------
CATEGORIES = ("trees", "saplings", "shrubs_ferns", "deadfall", "rocks")

#: (zone key, design hectares, {category: instances per hectare}) - `tables.DENSITY` verbatim.
ZONES: tuple[dict, ...] = (
    dict(
        key="forest_core",
        design_ha=262,
        label="forest core (forest_floor, r 400-850)",
        per_ha=dict(trees=160, saplings=90, shrubs_ferns=120, deadfall=25, rocks=40),
    ),
    dict(
        key="forest_edge",
        design_ha=24,
        label="forest edge (r 350-400)",
        per_ha=dict(trees=60, saplings=120, shrubs_ferns=200, deadfall=20, rocks=20),
    ),
    dict(
        key="meadow",
        design_ha=38,
        label="meadow / lake shelf / lane runouts",
        per_ha=dict(trees=0, saplings=8, shrubs_ferns=15, deadfall=2, rocks=10),
    ),
    dict(
        key="scree_rock",
        design_ha=78,
        label="scree / rock (walls)",
        per_ha=dict(trees=12, saplings=20, shrubs_ferns=10, deadfall=5, rocks=300),
    ),
    dict(
        key="alpine",
        design_ha=10,
        label="alpine + crest",
        per_ha=dict(trees=0, saplings=30, shrubs_ferns=5, deadfall=0, rocks=144),
    ),
    dict(
        key="shore",
        design_ha=5,
        label="lakeshore (shore)",
        per_ha=dict(trees=0, saplings=0, shrubs_ferns=40, deadfall=20, rocks=30),
    ),
)

#: Which species fill each (zone, category) and in what proportion.  The lists honour the
#: "zone" column of design §4.2 row by row; the pine:fir 60:40 and 55 % tall split of the
#: forest core is the design's own sentence.
SPECIES_MIX: dict[tuple[str, str], tuple[tuple[str, float], ...]] = {
    ("forest_core", "trees"): (
        ("pine_tall_a", 0.60 * 0.55 / 3),
        ("pine_tall_b", 0.60 * 0.55 / 3),
        ("pine_tall_c", 0.60 * 0.55 / 3),
        ("pine_mid_a", 0.60 * 0.45 / 2),
        ("pine_mid_b", 0.60 * 0.45 / 2),
        ("fir_tall_a", 0.40 * 0.55 / 3),
        ("fir_tall_b", 0.40 * 0.55 / 3),
        ("fir_tall_c", 0.40 * 0.55 / 3),
        ("fir_mid_a", 0.40 * 0.45 / 2),
        ("fir_mid_b", 0.40 * 0.45 / 2),
    ),
    ("forest_core", "saplings"): (
        ("pine_sapling_a", 0.22),
        ("pine_sapling_b", 0.22),
        ("pine_sapling_c", 0.20),
        ("fir_sapling_a", 0.18),
        ("fir_sapling_b", 0.18),
    ),
    ("forest_core", "shrubs_ferns"): (
        ("fern_a", 0.40),
        ("fern_b", 0.35),
        ("shrub_03", 0.15),
        ("shrub_01", 0.10),
    ),
    ("forest_core", "deadfall"): (
        ("fallen_log_a", 0.16),
        ("fallen_log_b", 0.16),
        ("fallen_log_c", 0.14),
        ("stump_a", 0.12),
        ("stump_b", 0.12),
        ("windthrow_roots", 0.08),
        ("root_cluster", 0.08),
        ("bark_debris", 0.07),
        ("branch_pile", 0.07),
    ),
    ("forest_core", "rocks"): (
        ("boulder_forest_a", 0.14),
        ("boulder_forest_b", 0.16),
        ("nq_boulder_02", 0.06),
        ("nq_boulder_03", 0.08),
        ("nq_boulder_04", 0.08),
        ("nq_boulder_05", 0.08),
        ("nq_boulder_06", 0.06),
        ("mossy_rock_a", 0.04),
        ("mossy_rock_b", 0.06),
        ("mossy_rock_c", 0.08),
        ("mossy_rock_d", 0.08),
        ("mossy_rock_e", 0.08),
    ),
    ("forest_edge", "trees"): (
        ("pine_mid_a", 0.30),
        ("pine_mid_b", 0.30),
        ("fir_mid_a", 0.20),
        ("fir_mid_b", 0.20),
    ),
    ("forest_edge", "saplings"): (
        ("pine_sapling_a", 0.20),
        ("pine_sapling_b", 0.22),
        ("pine_sapling_c", 0.22),
        ("fir_sapling_a", 0.18),
        ("fir_sapling_b", 0.18),
    ),
    ("forest_edge", "shrubs_ferns"): (
        ("shrub_01", 0.28),
        ("shrub_02", 0.16),
        ("shrub_03", 0.24),
        ("shrub_04", 0.22),
        ("fern_a", 0.10),
    ),
    ("forest_edge", "deadfall"): (
        ("fallen_log_b", 0.18),
        ("fallen_log_c", 0.18),
        ("stump_a", 0.20),
        ("stump_b", 0.20),
        ("bark_debris", 0.12),
        ("branch_pile", 0.12),
    ),
    ("forest_edge", "rocks"): (
        ("boulder_forest_a", 0.20),
        ("boulder_forest_b", 0.28),
        ("mossy_rock_c", 0.18),
        ("mossy_rock_d", 0.18),
        ("mossy_rock_e", 0.16),
    ),
    ("meadow", "saplings"): (
        ("pine_sapling_b", 0.30),
        ("pine_sapling_c", 0.30),
        ("fir_sapling_b", 0.40),
    ),
    ("meadow", "shrubs_ferns"): (
        ("shrub_01", 0.30),
        ("shrub_02", 0.14),
        ("shrub_03", 0.30),
        ("shrub_04", 0.26),
    ),
    ("meadow", "deadfall"): (
        ("stump_b", 0.34),
        ("bark_debris", 0.33),
        ("branch_pile", 0.33),
    ),
    ("meadow", "rocks"): (
        ("boulder_forest_b", 0.34),
        ("mossy_rock_e", 0.33),
        ("scree_rock_b", 0.33),
    ),
    ("scree_rock", "trees"): (("snag_a", 0.5), ("snag_b", 0.5)),
    ("scree_rock", "saplings"): (
        ("pine_sapling_c", 0.40),
        ("fir_sapling_b", 0.35),
        ("dwarf_pine_alpine", 0.25),
    ),
    ("scree_rock", "shrubs_ferns"): (("shrub_03", 0.55), ("shrub_04", 0.45)),
    ("scree_rock", "deadfall"): (
        ("branch_pile", 0.40),
        ("bark_debris", 0.30),
        ("fallen_log_c", 0.30),
    ),
    # r10 (critic B9-1, and the arithmetic that finally explained the residue): the two cliff
    # outcrops used to take 0.08 / 0.09 of this mix -- 1,872 and 2,106 instances.  Each one is
    # a 26.7 x 24.0 x 20.3 m massif of 4,722 m3, and the ground footprint of its keep-out
    # volume in the 0.30 m slab the planter tests averages 135.3 m2 and 116.7 m2.  Summed:
    # 25.33 ha + 24.59 ha = 49.9 ha of rock footprint in a zone that MEASURES 48.24 ha.  The
    # design asked for more rock than there is ground, so 99.9 % of the zone's legal cells
    # were inside a body and NOTHING could be planted there legally -- not a pebble, not a
    # sapling (`r10/freespace_r10.json`, `r10/freespace_sweep.json`).
    #
    # r9 hid this because those two shapes shipped as thin shells; `rock_solid.DEPTH_SHARE`
    # 0.35 -> 0.65 (the r10 husk fix) made the volume real and the arithmetic visible.  The
    # fix is the density, not the gate: at 0.01 each the outcrops cover 5.1 ha of the 48.24
    # and the zone's blocked share falls 99.9 % -> ~30 %, which is a boulder field a car can
    # drive through instead of one continuous wall of interpenetrating props.  Every
    # zone/category count and the 154,686 total are UNCHANGED -- only the split inside
    # `scree_rock/rocks` moves, into the small and medium rocks that make a scree slope.
    ("scree_rock", "rocks"): (
        ("scree_rock_a", 0.20),
        ("scree_rock_b", 0.32),
        ("pebble_cluster", 0.31),
        ("nq_boulder_02", 0.05),
        ("nq_boulder_04", 0.05),
        ("nq_boulder_06", 0.05),
        ("cliff_outcrop_a", 0.01),
        ("cliff_outcrop_b", 0.01),
    ),
    ("alpine", "saplings"): (("dwarf_pine_alpine", 1.0),),
    ("alpine", "shrubs_ferns"): (("shrub_03", 1.0),),
    ("alpine", "rocks"): (
        ("lichen_boulder", 0.30),
        ("scree_rock_a", 0.16),
        ("scree_rock_b", 0.20),
        ("pebble_cluster", 0.20),
        ("crag", 24 / 1440.0),
    ),
    ("shore", "shrubs_ferns"): (("reed_clump", 1.0),),
    ("shore", "deadfall"): (("driftwood", 1.0),),
    ("shore", "rocks"): (
        ("mossy_rock_c", 0.24),
        ("mossy_rock_d", 0.26),
        ("mossy_rock_e", 0.26),
        ("pebble_cluster", 0.24),
    ),
}

#: Poisson-disc minimum spacing and slope ceiling per category (design §4.4 names the three
#: spacings; saplings and deadfall are build choices recorded as DEV-5).
PLACEMENT = {
    "trees": dict(min_spacing_m=3.5, max_grade=0.55, snap=False),
    "saplings": dict(min_spacing_m=2.0, max_grade=0.60, snap=False),
    "shrubs_ferns": dict(min_spacing_m=1.5, max_grade=0.65, snap=False),
    "deadfall": dict(min_spacing_m=2.5, max_grade=0.55, snap=True),
    "rocks": dict(min_spacing_m=0.8, max_grade=1.20, snap=True),
}

#: Scale jitter: design §4.4 "Scale 0.85-1.15 log-normal, yaw random".
#: r9 (DEV-23): the envelope every instance stays inside is 0.70-1.30, and the band is per
#: FAMILY -- the design's 0.85-1.15 gave a stand of 26-30 m firs whose heights read uniform
#: from the track (the user: "heights uniform"), where a natural stand has a 2:1 spread.
#: Rocks and deadwood keep the design's band, because their camera clearance and keep-outs
#: are sized off it.
SCALE_MIN, SCALE_MAX = 0.70, 1.30
SCALE_BANDS: dict[str, tuple[float, float]] = {
    "conifer": (0.70, 1.30),
    "snag": (0.80, 1.20),
    "card": (0.75, 1.25),
    "deadwood": (0.85, 1.15),
    "rock": (0.85, 1.15),
}


def scale_band(species: dict) -> tuple[float, float]:
    return SCALE_BANDS[species["family"]]


def scale_sigma(band: tuple[float, float]) -> float:
    """ln(max) / 1.85: ~95 % of the log-normal draws land inside the band before clipping."""
    return math.log(band[1]) / 1.85


SCALE_SIGMA = scale_sigma((SCALE_MIN, SCALE_MAX))

#: r9 (DEV-24): a conifer leans.  Every r8 trunk was plumb, which is the one thing a real
#: stand never is; the lean is |N(0, LEAN_SIGMA_DEG)| capped at LEAN_MAX_DEG, toward a random
#: azimuth, on the families that grow (not the rocks and logs, which sit on the ground).
LEAN_MAX_DEG = 5.0
LEAN_SIGMA_DEG = 2.2
LEAN_FAMILIES = ("conifer", "snag")

#: r9 (DEV-25): CLUMPED density.  A Poisson disc is a regular carpet -- every tree the same
#: distance from its neighbours -- and a forest is stands and glades.  `plant_forest.place`
#: still draws the design's exact count per zone and category, but offers the candidates in
#: PRIORITY order: a low-frequency noise field of this wavelength per category (weighted
#: CLUMP_WEIGHT against a uniform draw) fills the dense patches first, so the count lands in
#: stands with gaps between them.  Exact counts in, exact counts out.
CLUMP_WAVELENGTH_M: dict[str, float] = {
    "trees": 28.0,
    "saplings": 14.0,
    "shrubs_ferns": 10.0,
    "deadfall": 20.0,
    "rocks": 16.0,
}
CLUMP_WEIGHT = 0.6

#: Keep-outs (design §4.4).  ``terrain_model.tree_free`` already covers the clearing, the
#: lane runouts and the S1 sightline cone; these are the extra ones.
ROAD_KEEPOUT_M = 9.0  # "the road corridor +- 9 m; the trail corridor +- 9 m"
LAKE_KEEPOUT_E = 1.05  # "the lake e < 1.05"
EVERYTHING_KEEPOUT_R = 262.0  # "r < 262 for everything"
SPAWN_KEEPOUT_M = 12.0  # build choice: no instance within 12 m of a spawn sphere
CAMERA_KEEPOUT_M = 6.0  # build choice: no instance within 6 m of a truth-frame eye

#: r3 (D7): the SIZE-AWARE half of that rule.  A 21 m photogrammetry cliff 10.8 m from a
#: truth-frame eye is not a rock in the composition, it is a wall the camera is standing
#: inside -- h/d = 1.94, and the r2 crest frame is a third sky-full of its back faces.  A
#: solid model may not stand closer to an eye than ``CAMERA_CLEAR_HEIGHT_K`` times its own
#: full-scale height; cards and generated conifers keep the flat 6 m, because a tree at 6 m is
#: a tree and the S7 forest-floor frame is made of them.
#:
#: r2 deferred this fix on the argument that it needs a re-fill loop and would cost the
#: design's zone counts.  MEASURED on r2's own shipped zip, at k = 1.35 the rule touches
#: **6 of 43,926** model instances, and none of the 27 crags (nearest eye 87.5 m).  It is
#: implemented as a WITHIN-BLOCK SWAP rather than a re-fill: every accepted point already
#: clears 6 m, so trading a big shape's near point for a small shape's far point is always
#: legal and moves no instance count by one -- QB-16's 154,686 is preserved by construction.
CAMERA_CLEAR_HEIGHT_K = 1.35
CAMERA_CLEAR_FAMILIES = ("rock", "deadwood")


def camera_clear_radius(species: dict) -> float:
    """How far this species must stand from a truth-frame eye, in metres."""
    if species["build"] != "model" or species["family"] not in CAMERA_CLEAR_FAMILIES:
        return CAMERA_KEEPOUT_M
    return max(
        CAMERA_KEEPOUT_M, CAMERA_CLEAR_HEIGHT_K * species["height_m"] * scale_band(species)[1]
    )


# --------------------------------------------------------------------------------------
# Deviations from the frozen design, each with its reason
# --------------------------------------------------------------------------------------
DEVIATIONS: tuple[dict, ...] = (
    dict(
        id="DEV-1",
        subject="species count",
        design="the orchestrator's brief says 56 TSForestItemData (18 conifers + 38 others)",
        built="54",
        reason="the FROZEN design governs: level_design_v4.md 4.2 is titled '54 TSForestItemData', "
        "its table has rows 1-54, tables.FOREST_DATABLOCKS == 54 and tables.DAE_CENSUS's "
        "forest block has 54 entries (18 + 7 + 2 + 7 + 20). 18 + 38 = 56 is an arithmetic "
        "slip in the brief, not a spec.",
    ),
    dict(
        id="DEV-2",
        subject="DAE directories",
        design="art/shapes/hot_potato_arena_forest (the scaffold's single directory)",
        built="art/shapes/{trees,deadwood,undergrowth,rocks,groundcover}",
        reason="study/census.py buckets a DAE by the third path element and qb_check.py reads "
        "shapes.by_category['trees'] for QB-6. In one merged directory QB-6 measures "
        "nothing. Stock does the same (levels/italy/art/shapes/trees/...).",
    ),
    dict(
        id="DEV-3",
        subject="four foliage material names",
        design="tables.FOLIAGE_MATERIALS names _f_shrub_01.._f_shrub_04",
        built="_f_shrub_leaf_01.._f_shrub_leaf_04",
        reason="species 28-31 are named shrub_01..04, so their datablocks are "
        "ericrolph_hot_potato_arena_f_shrub_01..04 - byte-identical to the design's "
        "material names. level_facts: SimObject names are global across classes; the "
        "engine refuses the re-declaration and drops every instance of the item "
        "(boot 1 run 1 lost every rock that way). The count stays 22 for QB-13.",
    ),
    dict(
        id="DEV-4",
        subject="nine GroundCover shape DAEs",
        design="tables.DAE_CENSUS lists 87 DAEs and no cover shapes",
        built="+9 (gcs_ash_lump_a/b, gcs_cinder, gcs_pebble_a/b/c, gcs_cone, gcs_twig, "
        "gcs_bark_chip), each with a nulldetail and a real Colmesh",
        reason="the five shape covers of design 4.5 need a shapeFilename each and the forest "
        "items are 1.1-41 m shapes, far too big at cover sizes 0.08-0.6 m. Sharing the "
        "nine across the ten covers keeps the addition minimal, and giving each a "
        "Colmesh follows the design's own B3/B4 rule so QB-7's colmesh line RISES "
        "(87 -> 96 DAEs, 63 -> 72 with Colmesh: 72.4 % -> 75.0 %).",
    ),
    dict(
        id="DEV-5",
        subject="sapling and deadfall spacing",
        design="min spacing 3.5 m trees, 1.5 m shrubs, 0.8 m rocks (saplings/deadfall unstated)",
        built="saplings 2.0 m, deadfall 2.5 m",
        reason="interpolated between the three stated classes by trunk size; recorded so the "
        "placement is reproducible.",
    ),
    dict(
        id="DEV-6",
        subject="zone areas",
        design="4.4's hectare column (262/24/38/78/10/5 = 417 ha)",
        built="the measured masks of the frozen terrain model "
        "(285.5/6.1/13.6/48.2/7.0/2.9 = 363.3 ha)",
        reason="the whole 2048 m block is 419.4 ha, so 417 ha of vegetated zones cannot be "
        "right; the annulus r 350-400 is 11.8 ha before the lane clearings, not 24. The "
        "design's own 2.7 row 'plantable area 309 ha' reproduces EXACTLY from the frozen "
        "model (309.2 ha measured). B3 keeps the design's INSTANCE COUNTS (area x per-ha "
        "= 154,686, the number QB-16 asserts) and reports the real per-hectare density.",
    ),
    dict(
        id="DEV-7",
        subject="an opaque opacity map on the five WOOD materials",
        design="4.5 lists the six-role maps and gives every foliage material alphaTest",
        built="the tile recipe also writes *_o.data.png, a constant 255",
        reason="measured live: alphaTest true with no opacityMap renders the engine's "
        "placeholder material (every trunk was checkered while the twig cards were right). "
        "Dropping alphaTest instead would take the five WOOD rows out of "
        "study/census_lib.foliage_class's STRICT population and QB-13's count would fall "
        "from 22 to 17.",
    ),
    dict(
        id="DEV-8",
        subject="audio forest meta",
        design="10's B2 row owns 'audio forest meta'; the B3 brief says 'if the design names one'",
        built="not shipped by B3",
        reason="the design assigns it to B2 (hearth/audio). Writing it here would clobber B2's "
        "file in a parallel round.",
    ),
    dict(
        id="DEV-9",
        subject="conifer canopy triangle budget and twig-card size",
        design="4.2's per-species detail budgets (pine_tall 600->1,800 / 300->900 / 100->320) "
        "and no stated card size",
        built="the ten tall/mid conifers' TOP detail is raised (pine_tall 4,300, fir_tall "
        "4,200, pine_mid 2,800, fir_mid 2,400; saplings 1,600/1,500, dwarf 1,300) and a twig "
        "card is a SQUARE 0.24-0.36 m half-side instead of 0.30-0.46 x the branch reach; the "
        "_a300 details are re-proportioned and the _a100 details are UNCHANGED",
        reason="measured against three stock conifers (ECUSA tree_douglasfir_large_a, italy "
        "scots_pine, WCUSA pine_radiata_large): stock hangs 2,037-2,697 cards of 0.12-0.53 m2 "
        "at 0.82-1.30 mm per texel and carries 4,034-5,599 FOLIAGE triangles in its top LOD. "
        "r1 hung 836 cards of 4.36 m2 at 3.93 mm/texel, which is why a needle measured 134 mm "
        "wide. pine_tall_a now hangs 2,086 cards of 0.23-0.52 m2. QB-6's own window (top LOD "
        "p50 600-2,500) still holds at 2,400, and because only the top detail grows the cost "
        "at distance -- the _a100 mesh 8,600 instances deep -- is unchanged.",
    ),
    dict(
        id="DEV-10",
        subject="the twig atlases are cut-out compositions, and two of design 12's four "
        "conifer scans are one file",
        design="4.1: twig cards UV-mapped into the CC0 twig atlases of pine_tree_01 / "
        "fir_tree_01 / pine_sapling_medium; 12 lists four conifer downloads",
        built="six atlases composed from CUT-OUT STAMPS taken with the sources' own published "
        "alpha, dealt out so no two atlases share a stamp; pine_sapling_medium and "
        "fir_sapling_medium resolve to the pine_tree_01 / fir_tree_01 sheets",
        reason="MEASURED: pine_sapling_medium's five twig maps are byte-identical to "
        "pine_tree_01's (alpha sha256[:16] 1e5a1fe741f4cb73) and fir_sapling_medium shares "
        "fir_tree_01's alpha (6eecd1cf1e059488), so 12's four ids are two sheets. "
        "pine_sapling_small and fir_sapling were fetched in r2 to look for more and carry no "
        "usable sprig (their twig regions are UV-atlas junk; no island survives the cut), so "
        "they are recorded and not used. **r3 CORRECTION**: r2 wrote 'dealt out so no "
        "two atlases share a stamp' and critic r2 measured it FALSE for 4 stamps across "
        "2 pairs -- stride/phase only separate WITHIN one pool, and PINE_SPRIGS and "
        "PINE_NEEDLES (likewise FIR_SPRIGS and FIR_NEEDLES) are two different "
        "subdivisions of the SAME sheet, so both pools begin with the same parent "
        "stamps. subdivide_only drops those parents from the NEEDLES pools; re-measured "
        "on the critic's own instrument, 0 of 15 pairs share a stamp and 74 distinct "
        "stamps come out of 74 dealt. r1 also replaced the sources' needle-level alpha "
        "with a GENERATED blob (forest_textures.sprig_mask) and magnified the crop up to "
        "3.3x; both are gone.",
    ),
    dict(
        id="DEV-11",
        subject="the five billboard cover atlases carry 4.5's NAMED content",
        design="4.5: gc_forest_litter is 'fern fronds, needle clumps, twig bundles', "
        "gc_scorch_stubble 'burnt stalks, char twigs', gc_lake_reeds reeds",
        built="each cover atlas is composed from cut-outs of the 12 sources the design names "
        "for it -- fern_02 fronds, pine/fir needle sprigs, forest_leaves_04 litter and "
        "dry_branches_medium_01 twigs for the litter; burned_ground_01 char stalks for the "
        "stubble; grass_medium_02 blades for the reeds; grass_medium_01 tufts for the meadow",
        reason="r1 shipped all five as the same generated blade_mask in five tints, so the "
        "litter under the S7 camera was brown grass and the stubble was dark grass; 8's S7 "
        "pass rule asks for needle litter and ferns. This deviation was NOT recorded in r1 "
        "and is recorded here as the defect it was.",
    ),
    dict(
        id="DEV-12",
        subject="cover STACKING: five billboard records become twelve",
        design="4.5's ten GroundCover records, one billboard cover per terrain layer",
        built="17 records -- the five billboard covers split into twelve at different size "
        "bands on the same layers, drawing different cells of the same atlas; the five shape "
        "covers unchanged",
        reason="measured over five stock maps, stock stacks 4-17 covers on one terrain layer "
        "(italy's Grass carries 12) where 4.5 stacks one. The element budget is SPLIT, not "
        "inflated: the billboard total is still 940,000 and the grand total still 1,410,000, "
        "so QB-16/18 read the design's numbers and per-layer density is unchanged; "
        "forest_floor now carries 4 covers, meadow 3, alpine/scorch/shore 2.",
    ),
    dict(
        id="DEV-13",
        subject="cliff-outcrop and large-scree triangle budgets",
        design="4.2: cliff_outcrop 700->3,000 / 300->1,000 / 100->300; scree_rock_a "
        "400->600 / 150->200",
        built="cliff_outcrop 700->9,000 / 300->2,600 / 100->600; scree_rock_a "
        "400->1,600 / 150->420",
        reason="MEASURED on the shipped DAEs: at the design's budget a 21 m cliff_outcrop "
        "carries a 0.80 m MEDIAN triangle edge and a 3.30 m longest edge, and at 10.8 m from "
        "the crest camera those triangles silhouette against the sky as flat ribbons (the "
        "r2 crest frame shows it). scree_rock_a is `rock_07 x 20` -- a 0.32 m pebble scan "
        "blown up to 6.4 m -- so 600 triangles is a 0.61 m median edge on it too, while "
        "scree_rock_b (stone_01 x 15, 2.2 m) reads 0.20 m and needs nothing. The budgets are "
        "raised only on those three shapes; QB-6 measures TREE shapes only and is unmoved, "
        "and QB-7's hero stays far under 130,000.",
    ),
    # ---- r3 ------------------------------------------------------------------------------
    dict(
        id="DEV-14",
        subject="the DISTANCE LOD ladder of every card-bearing shape (r3)",
        design="4.2's per-species detail budgets; r2 raised only the TOP detail (DEV-9) and "
        "left the design's lower ones: pine_tall 300->1,720 / 100->320",
        built="every conifer and card shape's lower details are re-cut so each FOLIAGE step is "
        "<= 1.5x: pine_tall 300->2,842 / 100->1,880, fir_tall 2,776 / 1,836, pine_mid 1,842 / "
        "1,214, fir_mid 1,576 / 1,036, the saplings 150->1,052 / 986 / 852, the shrubs "
        "120->468, the ferns 282 and the reed clump 108.  The card is also scaled by "
        "sqrt(cards_top / cards_here) so the ladder conserves the crown's coverage AREA",
        reason="MEASURED against three stock conifers (critic r2, out of the game's own zips): "
        "ECUSA tree_douglasfir_large_a 5,395 -> 3,776 -> 2,643, italy scots_pine 4,074 -> "
        "2,795 -> 1,886, WCUSA pine_radiata_large 5,140 -> 3,855 -> 2,570 -- steps of "
        "1.33-1.50x and a lowest LOD keeping 46-50 % of its top.  r2's f_pine_tall_a stepped "
        "2.51x then 5.61x to 296 foliage triangles, 7 % of its top, and design 4.3's own "
        "arithmetic (935 px per unit of height/distance at 1080p) puts that mesh in charge of "
        "EVERY tree between 87 m and 262 m.  Three of the six r2 frames show the result: a "
        "pole plantation.  QB-6 gates the top-LOD p50 (unmoved at 2,400) and the low/top p50, "
        "which its own <= 0.6 window REWARDED for being thin; that row now has a floor too.",
    ),
    dict(
        id="DEV-15",
        subject="whorl pitch jitter and a lower canopy base on the generated conifers (r3)",
        design="4.1's whorled conifer: pines 8-12 whorls x 5-7 branches, firs 14-18 x 6-8",
        built="the whorl COUNT is unchanged; its z is jittered +- 0.45 pitch and every card "
        "+- 0.60 pitch about its own whorl, and the pine canopy starts at 0.24 of the tree's "
        "height instead of 0.32 (firs 0.16 instead of 0.18)",
        reason="r2 put every card of a whorl at exactly the whorl's z, which over an 18 m crown "
        "is a 1.5-1.6 m comb.  Critic r2 measured the vertical banding energy at 0.332 "
        "(f_pine_tall_a) and 0.320 (f_pine_mid_a) against three stock conifers' 0.051-0.103, "
        "with 24.1 % and 29.7 % of the crown's rows near-empty sky: the hero frame read as an "
        "araucaria, flat plates on a bare pole, from 40 m out.  The two jitters overlap "
        "adjacent whorls (total spread ~2.1 pitches) so the profile is continuous, and they "
        "move no triangle: every authored budget is still met exactly.",
    ),
    dict(
        id="DEV-16",
        subject="the four shrub-leaf atlases become cut-outs, and the generated-mask cook is "
        "deleted (r3)",
        design="4.1: 'the ferns and reeds whose polygon leaves are replaced by cards cut from "
        "THEIR OWN ATLASES'",
        built="f_shrub_leaf_01..04 gain `sources` (offcolour, cover 0.16, 7/4/10/8 real leaf "
        "clusters) and forest_textures loses cook_atlas, sprig_mask, leaf_mask, blade_mask, "
        "MASK_FUNCTIONS and the whole r1 window search",
        reason="r2's contact sheet says all seventeen atlases are photographed foliage 'not a "
        "generated mask'; for these four it was false -- they had no sources, so cook_material "
        "sent them down the r1 path with leaf_mask, a drawn broad-leaf blob times a crop.  "
        "Deleting the path is what makes the sentence true and keeps it true.",
    ),
    dict(
        id="DEV-17",
        subject="a SIZE-AWARE camera keep-out for solid model shapes (r3)",
        design="4.4's keep-outs; the flat 6 m camera-eye radius is a build choice of r1's",
        built="a rock or deadwood MODEL may not stand closer to a truth-frame eye than 1.35 x "
        "its own full-scale height (cliff_outcrop_a 32.6 m, crag 63.7 m); cards, generated "
        "conifers and snags keep the flat 6 m",
        reason="r2's crest frame shows a 21 m photogrammetry cliff shell 10.8 m from the eye -- "
        "height/distance 1.94, i.e. the camera standing inside it.  r2 deferred the fix on the "
        "argument that species are assigned after the Poisson pass so it needs a re-fill loop "
        "and would cost the design's zone counts.  MEASURED on r2's own zip the rule touches "
        "6 of 43,926 model instances and none of the 27 crags, and it is implemented as a "
        "within-block SWAP (every accepted point already clears 6 m, so trading a big shape's "
        "near point for a small shape's far point is always legal) -- so QB-16's 154,686 is "
        "preserved by construction, not by a loop that might not converge.",
    ),
    dict(
        id="DEV-18",
        subject="every CC0 model shell is capped, and rock materials are doubleSided (r3)",
        design="4.1: the CC0 rocks are imported, decimated and given a convex-hull Colmesh",
        built="blender_forest.close_shell fills every boundary loop at import and seal_to "
        "re-caps after each decimation; the nine rock/cover-shape materials gain doubleSided",
        reason="rock_face_01 and mountainside are scans of a cliff FACE, not closed solids: "
        "f_cliff_outcrop_a's top LOD shipped with 535 boundary edges and 90.6 m of open "
        "perimeter on a 21 m span, and f_crag with 191.9 m on 41 m.  Seen from behind an open "
        "shell's back faces silhouette as the tan ribbons across a third of the r2 crest "
        "frame.  Capping takes cliff_outcrop_a to 38 edges and 1.88 m (perimeter/span 4.31 -> "
        "0.09) with no change to any triangle budget; doubleSided makes the residue LIGHT "
        "rather than silhouette.",
    ),
    dict(
        id="DEV-19",
        subject="the shell cap is TESSELLATED ROCK, not a flat n-gon fan (r4)",
        design="4.1: the CC0 rocks are imported, decimated and given a convex-hull Colmesh",
        built="close_shell fills with holes_fill, falls back to triangle_fill for the "
        "boundaries that run through non-manifold junctions, subdivides the fill to 0.15 m2 "
        "faces and displaces every interior cap vertex onto fractal noise at 0.40 of the cap "
        "triangle's own edge, then gives the cap the rock's own texel density by planar "
        "projection.  The Solidify rim of DEV-18 stays as a last resort and now fires on "
        "nothing.",
        reason="DEV-18 closed the shells and paid for it with plates: f_cliff_outcrop_a's "
        "largest triangle went 1.22 -> 106.15 m2, its surface 504 -> 907 m2 with 40.2 % in "
        "faces over 1 m2, and from the crest eye 39.9 % of the near rock a player sees was "
        "smeared flat cap against 4.2 % in r2.  Displacement is what survives decimation -- a "
        "flat cap collapses straight back into a plate, a bumpy one cannot -- and "
        "triangle_fill is what finally closes f_crag (195.9 m -> 0.23 m) without the Solidify "
        "rim that doubled its surface.",
    ),
    dict(
        id="DEV-20",
        subject="the imposter atlas is a 32-view equator RING with no poles, re-baked every "
        "round (r4; the poles removed in r5)",
        design="4.3: BB::DIM=128 on every billboard node = 512 x 256; QB-9b's 512 px height "
        "left OPEN, with 'B3 tries the other BB:: knobs for 1024 x 512 and records the outcome'",
        built="BB::DIM=128 + BB::EQUATOR_STEPS=32 + BB::INCLUDE_POLES=0 = 32 views around the "
        "equator at 11.25 degrees and no polar cell, filling an 8 x 4 grid of 128 px cells = "
        "1024 x 512; the harvest writes authoring/<level>_forest_imposters.json recording each "
        "atlas's sha256 AND the sha256 of the DAE it was baked from, and two static gates read "
        "it",
        reason="the atlas is the one shipped artefact B3 does not author -- the engine bakes "
        "it -- and all 54 were byte-identical across r1, r2 and r3 while the conifers under "
        "them were rebuilt twice, so the forest past 262 m (which design 4.3 says is the whole "
        "forest as seen from the arena) was still drawn with r1's geometry.  Six views is "
        "90 degrees of azimuth between billboards, against 45 for italy's cypress_tree (8 "
        "views at 256 px) and 22.5 for its scots_pine (16).  BB::POLAR_STEPS is not the "
        "answer: measured, EQUATOR_STEPS=10 + POLAR_STEPS=1 allocated 32 cells and rendered "
        "into 12, because BB::POLAR_ANGLE defaults to 0.  r4 then spent two of its 32 cells on "
        "poles on the false premise that the engine always adds them; critic r4 disproved that "
        "-- no stock tree atlas carries a polar cell -- and the r5 probe boot measured "
        "BB::INCLUDE_POLES=0 end to end: constructor 1 32 0 0 128 0 0, atlas 1024 x 512, 32 of "
        "32 cells rendered, zero poles.  Same bytes, finer azimuth, and the stock shape.  "
        "Design 9 prices the 1024 x 512 atlas at +71 MB and names the cuts that pay for it.",
    ),
    dict(
        id="DEV-21",
        subject="the shape-foliage alphaRef is set from the atlas's OWN coverage (r4)",
        design="4.5's material table gives alphaTest 1 with alphaRef 84-110 on the cut-outs",
        built="every cut-out material's alphaRef is 255 x its own opaque coverage, "
        "measured on its shipped opacity map and capped at the design's value: pine twigs "
        "110 -> 61/50, fir twigs 110 -> 45, sapling twig 110 -> 66, dwarf pine 110 -> 98, "
        "shrub leaves 84 -> 80/32/84/58, fern 84 -> 25, reed 84 -> 37, and the five "
        "GroundCover atlases 70 -> 57/24/43/24/24.  The five opaque barks keep 84.  "
        "QB-13's own window is alphaRef p50 50-100 and max <= 150: the p50 moves 84 -> "
        "57.5 and the max 110 -> 98, both inside it.",
        reason="THE FAR FOREST WAS THIN BECAUSE OF THIS, not because the geometry was.  An "
        "alpha-tested atlas keeps its coverage only while the mip it is sampled at still has "
        "texels above the reference; MEASURED on the shipped f_pine_twig_a cell, coverage "
        "holds at 0.25-0.28 from 512 px down to 8 px and then collapses to 0.062 at 4 px and "
        "0.000 at 2 px, because a mip texel is the AVERAGE alpha of its block and 0.24 x 255 "
        "= 61 is under alphaRef 110.  A 28 m pine baked into a 128 px imposter cell draws its "
        "0.60 m cards at 2.7 px, i.e. exactly that mip -- so the r4 bake came out with 282 "
        "opaque texels in a 1024 x 512 atlas, a string of specks, and r1's bake (whose cards "
        "were 1.6x larger before DEV-9 tripled the count) came out a 12.6 %-fill stipple.  At "
        "the measured reference the same cell reads 0.56 at 4 px.  The cost at full "
        "resolution is +9 to +17 % coverage on the conifer twigs -- a slightly softer needle "
        "edge, which is the right direction for critic r3's 'chunky, hard-edged clumps'.",
    ),
    dict(
        id="DEV-22",
        subject="the fern carpet is thinned (r9)",
        design="4.5: gc_forest_ferns 100,000 elements at 0.35-0.95 m; 1.41 M cover elements",
        built="40,000 at 0.30-0.78 m; the litter and needle-mat covers keep the design's "
        "110,000 and 90,000, so the total is 1,350,000",
        reason="the user's r9 override: the design's density read as a saturated hay-coloured "
        "carpet in every S7 frame, and nothing of the duff showed between the fronds.  The "
        "fronds were also the wrong colour (see forest_textures.cut_stamps, texel_hue): the "
        "count and the colour are two halves of the same defect.",
    ),
    dict(
        id="DEV-23",
        subject="the scale band is 0.70-1.30 on the conifers (r9)",
        design="4.4: scale 0.85-1.15 log-normal on every instance",
        built="per family: conifers 0.70-1.30, snags 0.80-1.20, cards 0.75-1.25; rocks and "
        "deadwood keep 0.85-1.15 (their camera clearance and keep-outs are sized off it)",
        reason="the user's r9 override, 'heights uniform': a stand of 26-30 m firs at +-15 % "
        "reads as one height from the track, where a natural stand spans about 2:1.  The "
        "envelope every instance stays inside is SCALE_MIN..SCALE_MAX = 0.70..1.30 and the "
        "forest4 gate checks it.",
    ),
    dict(
        id="DEV-24",
        subject="conifers and snags lean (r9)",
        design="4.4: yaw random; nothing else on the rotation",
        built="|N(0, 2.2 deg)| capped at 5 deg toward a random azimuth, composed into the "
        "forest4 rotationMatrix; rocks, deadwood and cards stay plumb",
        reason="the user's r9 override: every r8 trunk was plumb, which is the one thing a "
        "real stand never is.  Five degrees is under what a driver notices as 'falling' and "
        "over what reads as a ruler.",
    ),
    dict(
        id="DEV-25",
        subject="clumped placement (r9)",
        design="4.4: a seeded Poisson disc per category (an even carpet)",
        built="the same Poisson disc and the same exact counts, with the candidates offered "
        "in the order of a per-category noise field (CLUMP_WAVELENGTH_M, CLUMP_WEIGHT), so "
        "the count lands in stands with gaps between them",
        reason="the user's r9 override: an even disc has every tree the same distance from "
        "its neighbours, and a forest is stands and glades.  Exact counts in, exact counts "
        "out -- QB-16's 154,686 is preserved by construction.",
    ),
    dict(
        id="DEV-26",
        subject="every B3 map ships at <= 1024 (r9)",
        design="4.5 / QB-12: 'at least 7 % of the maps at 2048'",
        built="all 146 maps at <= 1024; the twig and litter atlases are COMPOSED at 1024 and "
        "not downsampled from 2048",
        reason="level_facts 2026-09-06 (PROVEN): at GraphicTextureQuality 'Normal' -- both the "
        "sentinel and the real profile -- the engine allocates an 11-level object and a 2048 "
        "source renders at 1024; a 12-level chain is refused and never streams in.  A 2048 "
        "map bought nothing visible and could cost the map.",
    ),
    dict(
        id="DEV-27",
        subject="the forest rocks are bodies and their Colmesh is the visual, decimated (r9)",
        design="4.2: rocks as decimated scans with a convex-hull Colmesh of 60-240 triangles",
        built="the three cliff-face scans rebuilt as heightfield bodies (rock_solid), every "
        "other rock and log voxel-remeshed to a closed manifold, and the Colmesh a decimated "
        "copy of the finest detail: 300 triangles on the boulders, 2,000 on the outcrops, "
        "4,000 on the crag",
        reason="the user's r9 requirement, and the law critic B2 pass 5 proved: a face scan "
        "wrapped on a hull is a facade even when watertight, with an invisible wall metres in "
        "front of the rock (cliff_outcrop_a 1.54 m p90, the crag 1.77 m).  The adopted gate "
        "-- visual/Colmesh volume >= 0.5, LOD parity, phantom gap p50/p90/max <= 0.06/0.12/"
        "0.25 m -- is tests/test_hot_potato_forest.py's rock gate now.",
    ),
    dict(
        id="DEV-28",
        subject="the ten tall/mid conifers carry 2.1-2.5x the twig cards at every detail (r9)",
        design="4.2's per-species detail budgets as raised by DEV-9 (pine_tall 4,300 / 2,842 / "
        "1,880; fir_tall 4,200 / 2,776 / 1,836; pine_mid 2,800 / 1,842 / 1,214; fir_mid 2,400 "
        "/ 1,576 / 1,036) and QB-6's 'top LOD p50 600-2,500 tris'",
        built="pine_tall 8,940 / 6,610 / 4,664; fir_tall 8,200 / 5,800 / 4,550; pine_mid "
        "5,590 / 4,110 / 3,000; fir_mid 4,820 / 3,850 / 2,554 -- each the r9 budget plus "
        "three triangles per r9 card, so a 28 m pine hangs 3,698 cards at its top detail where "
        "the first r9 cut hung 1,546; the card size, the atlases, the skeleton and the "
        "area-conserving ladder are unchanged; the 18 conifers' top-budget p50 is 4,820",
        reason="MEASURED side by side with stock in one boot (b3/r9/sbs_measure_r9.json, "
        "imposter_luma_r9.json): the first r9 cut's tall conifers baked at an equator "
        "bbox-fill of 0.14-0.25 where ECUSA's douglas fir and italy's scots pine bake at "
        "0.35-0.40, and in the shared frames their foliage share was at or under stock's -- "
        "the colour was in the stock band, the AMOUNT of foliage was not.  The census "
        "explains it: stock hangs 142 card-equivalents per metre of height (2,697 on 19.4 m, "
        "1,130 m2 at 0.317 coverage) and the r9 crown hung 55 (1,546 on 28 m, 566 m2) with "
        "the same mean card (0.37 vs 0.42 m2).  2.5x the cards is stock's density per metre, "
        "and 8,940 triangles on a 28 m pine is stock's 5,471 on a 19.4 m fir, scaled.  QB-6's "
        "window was written for the design's 836-card canopy; the p50 now sits inside stock's "
        "own 4,034-5,599 foliage triangles (DEV-9's census).",
    ),
    dict(
        id="DEV-29",
        subject="the three shrub imposters: graded sheets, an AO floor, dome cards wound "
        "outward (r12)",
        design="4.1's shrubs as card clumps cut from their own model atlases; 4.3's imposter "
        "band drawn from those cards",
        built="f_shrub_leaf_01/02/03 gain `grade` (SHRUB_GRADE luma 0.25 / sat 0.58 / hue 67; "
        "shrub_02 sat 0.50 / hue 72) and `ao_floor` 0.55; shrub_02's cells carry 3-5 stamps at "
        "0.60-1.00 of the cell and its alphaRef is re-measured on the r12 atlas; shrub_01/02/03 "
        "hang their cards on the new `dome` card_shape with the front face OUTWARD; shrub_04, "
        "the ferns and the reed are untouched (outside the r12 write set).  r12b (the second "
        "and last revision under PROCESS_20260915): shrub_01's cells re-stamped like shrub_02's "
        "((4, 6) at 0.70-1.00) because its r12 bake read bbox fill 0.489 against the gate's "
        "0.498 while the calibrated predictor had said 0.69 -- the sparsest sheet eroded most "
        "in the engine's bake and alphaRef was shown not to be the lever",
        reason="critic B11-5 / r10 N-8: `f_shrub_01` and `f_shrub_03` baked to mean RGB "
        "(149,154,74) and (144,144,54) -- chartreuse cones on the verge in the driver's forward "
        "view -- and `f_shrub_02` to a speckle.  MEASURED (b3/r12/atlas_eyes_r12_before.json, "
        "bake_response_r12.json): the bake reproduces a pure-card sheet almost unchanged, and "
        "the shrub sheets were the only cut-out foliage never graded (sRGB luma 0.54-0.60 where "
        "every conifer twig is 0.24); the eight pine atlases occupy sat 0.531-0.592 / hue "
        "61.8-68.3 / luma 0.164-0.237 under the same instrument.  The black card-shaped gashes "
        "are not in the colour atlas (no opaque texel under luma 0.12 in any shrub cell) but in "
        "the NORMAL atlas (normals_eyes_r12_before.json): `card_cluster_mesh` winds every bush "
        "card with its front toward the centre and the bake stores that normal -- stored-X "
        "against column correlates -0.84 to -0.92 on the four shrubs where the solid snag reads "
        "+0.73 -- so the runtime lights the billboard from the wrong side.  shrub_03 also "
        "shipped 6.0 % of its opaque texels at AO < 0.05 (pines 0.0 %).",
    ),
)


# --------------------------------------------------------------------------------------
# Derived tables the gates re-check
# --------------------------------------------------------------------------------------
SPECIES_BY_KEY = {s["key"]: s for s in SPECIES}
TREE_SPECIES = tuple(s for s in SPECIES if s["dir"] == TREES_DIR)


def largest_remainder(total: int, weights: list[float]) -> list[int]:
    """Split ``total`` by ``weights`` so the parts sum to exactly ``total`` (deterministic)."""
    if total <= 0 or not weights:
        return [0] * len(weights)
    scale = sum(weights)
    raw = [total * w / scale for w in weights]
    out = [int(v) for v in raw]
    remainder = total - sum(out)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - out[i]), i))
    for i in range(remainder):
        out[order[i % len(order)]] += 1
    return out


def zone_category_counts() -> dict[tuple[str, str], int]:
    """{(zone, category): instances} straight from the design's density table."""
    out: dict[tuple[str, str], int] = {}
    for zone in ZONES:
        for category in CATEGORIES:
            n = zone["design_ha"] * zone["per_ha"][category]
            if n:
                out[(zone["key"], category)] = int(n)
    return out


def species_counts() -> dict[str, int]:
    """{species key: total instances} - the design's counts split by SPECIES_MIX."""
    totals: dict[str, int] = {s["key"]: 0 for s in SPECIES}
    for (zone, category), n in zone_category_counts().items():
        mix = SPECIES_MIX[(zone, category)]
        parts = largest_remainder(n, [w for _, w in mix])
        for (key, _), part in zip(mix, parts, strict=True):
            totals[key] += part
    return totals


TOTAL_INSTANCES = sum(species_counts().values())
TOTAL_COVER_ELEMENTS = sum(c["maxElements"] for c in GROUND_COVERS)


# --------------------------------------------------------------------------------------
# Exact triangle budgets -> exact geometry (the QB-6 numbers are the design's, to the unit)
# --------------------------------------------------------------------------------------
# A "tube" is the capped, tapered trunk primitive every generated shape is built from:
# R radial segments, S rings, one bottom-fan centre and one apex vertex.
#   triangles = R (bottom fan) + 2 R (S - 1) (side band) + R (apex fan) = 2 R S
# Everything else is a CARD (one quad = 2 triangles) UV-mapped into a twig atlas cell, so
# every authored budget is met to the triangle without a decimation guess.
def tube_tris(radial: int, rings: int) -> int:
    return 2 * radial * rings


#: (radial, rings) for the trunk of each detail, highest pixel size first.
CONIFER_TRUNK_TUBES = {3: ((8, 8), (6, 5), (4, 3)), 2: ((6, 4), (4, 2))}
#: snags carry no cards: main trunk + two broken stubs, summing to the budget exactly.
SNAG_TUBES = {700: ((10, 30), (5, 5), (5, 5)), 300: ((8, 15), (5, 3), (5, 3))}

#: r9.  A branch is a 3-sided tapered tube (``BRANCH_RADIAL``): 12 triangles with one bend
#: (``rings=2``), 6 as a straight spike (``rings=1``).  The skeleton may take at most this share
#: of a detail's budget; past it the ladder drops the bend, then the sub-branches, then the
#: skeleton altogether -- which is the ``_a100`` detail, where a 26 m tree is 100 px tall and
#: an 8 cm branch is under a pixel.
BRANCH_RADIAL = 3
BRANCH_SHARE_MAX = 0.36
BRANCH_LADDER = ((2, 1), (1, 1), (1, 0), (0, 0))  # (main branch rings, sub-branch rings)

#: r11 (critic B10-1).  How thin a branch gets at the end of its WOOD, as a share of its base
#: radius, and how thick it is at the ring halfway there.  r9-r10 used a flat 0.55 for the mid
#: ring and let the apex fan close on a point, which is a taper in geometry but reads as a
#: constant-width ribbon at 15-40 m because the profile is linear over eight metres.  A real
#: limb loses most of its girth in its first third.
BRANCH_MID_RADIUS = 0.42
#: The tile repeat along a branch, in metres of girth: v repeats once per this many
#: circumferences.  `add_branch_tube` used to map the whole 1024 px bark tile ONCE over the
#: full branch (8 mm per texel along, 0.3 mm around) -- the single biggest reason the armature
#: renders as a smeared plank rather than as bark.  1.0 makes the texel square.
BRANCH_UV_GIRTHS = 1.0
#: r11 (critic B10-1).  An ABSOLUTE margin, in metres, between the end of a branch's wood and
#: its tip, applied on top of ``wood_reach``.  ``wood_reach`` is a share, so on a short branch
#: -- an upper-crown whorl or a sub-branch, where the card count per segment is 2-4 and the
#: sprays cannot overlap -- 42 % of 0.9 m is only 0.38 m of clearance, less than one card, and
#: the wood tip is again the outermost opaque thing in its height band.  0.55 m is two thirds
#: of a twig card's full width (2 x ``TWIG_CARD_HALF_M``), so the outermost spray always
#: straddles the end of the wood however short the branch is.
BRANCH_TIP_MARGIN_M = 0.55
#: ...but never take a branch below this share of its length, or a 0.3 m sub-branch would
#: carry no wood at all and the sprays on it would hang off nothing.
BRANCH_WOOD_MIN = 0.22


def conifer_layout(species: dict) -> tuple[dict, ...]:
    """One row per detail, highest pixel size first, exact by budget.

    ``trunk + mains x 2 x BRANCH_RADIAL x branch_rings + subs x 2 x BRANCH_RADIAL x sub_rings
    + 2 x cards == budget`` on every row.  The skeleton (``mains``/``subs``) is the species'
    :func:`crown_plan`, shared by every LOD so the silhouette is the same at every distance;
    only its triangle cost and the card count change down the ladder.
    """
    tubes = CONIFER_TRUNK_TUBES[len(species["details"])]
    plan = crown_plan(species)
    mains, subs = plan["mains"], plan["subs"]
    out = []
    previous_cards: int | None = None
    for (px, budget), (radial, rings) in zip(species["details"], tubes, strict=True):
        trunk = tube_tris(radial, rings)
        for branch_rings, sub_rings in BRANCH_LADDER:
            skeleton = mains * tube_tris(BRANCH_RADIAL, branch_rings) + subs * tube_tris(
                BRANCH_RADIAL, sub_rings
            )
            if skeleton > BRANCH_SHARE_MAX * budget:
                continue
            cards_here = (budget - trunk - skeleton) // 2
            # r9: the skeleton is a FIXED cost that steepens the foliage ladder -- with the
            # share cap alone `pine_tall_a` stepped 1.70x and `fir_tall_a` 1.79x against
            # LOD_STEP_MAX.  A lower detail keeps the richest skeleton that still lets its
            # cards step down by no more than the stock ratio; the last resort is no skeleton
            # at all, which is right for a 100 px tree whose branches are under a pixel.
            if previous_cards is None or previous_cards / max(cards_here, 1) <= LOD_STEP_MAX:
                break
        remaining = budget - trunk - skeleton
        if remaining < 2 or remaining % 2:
            raise ValueError(f"{species['key']} detail {px}: budget {budget} cannot be met")
        previous_cards = remaining // 2
        out.append(
            dict(
                px=px,
                budget=budget,
                radial=radial,
                rings=rings,
                branch_rings=branch_rings,
                sub_rings=sub_rings,
                mains=mains,
                subs=subs,
                skeleton_tris=skeleton,
                cards=remaining // 2,
            )
        )
    return tuple(out)


def snag_layout(species: dict) -> tuple[tuple[int, tuple[tuple[int, int], ...]], ...]:
    out = []
    for px, budget in species["details"]:
        tubes = SNAG_TUBES[budget]
        if sum(tube_tris(*t) for t in tubes) != budget:
            raise ValueError(f"{species['key']} detail {px}: snag tubes miss {budget}")
        out.append((px, tubes))
    return tuple(out)


#: D7: the radial segment count of a shrub's woody stem.  Five is the fewest that still reads
#: as round from a car; the stem is 2-6 % of the plant's height in radius, so a sixth segment
#: buys nothing and costs cards.
STEM_RADIAL = 5


def stem_layout(species: dict) -> tuple[tuple[int, int, int], ...]:
    """((pixel size, rings, triangles), ...) for the woody stem, or () for a stemless shape.

    D7, the user twice: *"trees that were very spherical were missing trunks"*.  Every card
    shape in this level was leaf cards and nothing else -- `shrub_01`'s shipped DAE carries
    exactly ONE material, `f_shrub_leaf_01`, and no stem geometry at all -- so the crown floats.
    A shrub row now says `stem=<share of its triangle budget>` and gets a tapered tube.

    The share, not a fixed count, is what keeps the LOD ladder legal.  `foliage_ladder` judges
    the step between details on FOLIAGE triangles alone, against `LOD_STEP_MAX` 1.5, and the
    four shrubs ship 700 / 468 / 320 -- steps of 1.496 and 1.463, which have almost no room.
    Subtracting a FIXED stem widens every step (a 40-triangle stem takes them to 1.542 and
    1.529, and the gate is right to refuse that); subtracting a constant SHARE leaves them
    where they are.  At 0.08: stems 60 / 40 / 30, cards 320 / 214 / 145, steps 1.495 and 1.476.
    """
    share = species.get("stem") or 0.0
    if not share:
        return ()
    out = []
    for px, budget in species["details"]:
        rings = max(2, round(share * budget / (2 * STEM_RADIAL)))
        out.append((px, rings, 2 * STEM_RADIAL * rings))
    return tuple(out)


def card_layout(species: dict) -> tuple[tuple[int, int], ...]:
    """((pixel size, card count), ...) for a pure-card shape (shrubs, ferns, reeds).

    D7: a shape with a `stem` spends part of each detail's budget on the tube, so the cards are
    what is LEFT.  `foliage_ladder` reads this function, so the ladder gate automatically judges
    the leaves without the trunk -- which is the same convention the conifers have always used.
    """
    stems = dict((px, tris) for px, _rings, tris in stem_layout(species))
    out = []
    for px, budget in species["details"]:
        remaining = budget - stems.get(px, 0)
        if remaining % 2:
            raise ValueError(f"{species['key']} detail {px}: odd card budget {remaining}")
        out.append((px, remaining // 2))
    return tuple(out)


def foliage_ladder(species: dict) -> tuple[int, ...]:
    """FOLIAGE triangles per detail, highest pixel size first (the trunk tube subtracted).

    This is the quantity the distance LOD is actually judged on -- a trunk is a pole at any
    triangle count, and it was the foliage that collapsed 5.61x in r2's last step.  ``None``
    for shapes that carry no cards (snags, models).
    """
    if species["build"] == "conifer":
        return tuple(2 * row["cards"] for row in conifer_layout(species))
    if species["build"] == "card":
        return tuple(2 * cards for _, cards in card_layout(species))
    return ()


def lod_card_scale(species: dict) -> tuple[float, ...]:
    """Card half-side multiplier per detail so the ladder conserves alpha-coverage AREA.

    A card's contribution to the crown's opacity is its AREA, so halving the card count and
    leaving the size alone halves the coverage -- which is exactly how r2's lowest LOD became
    "a scatter of faint disconnected specks" 1.70 m wide against its own 7.15 m top LOD.
    sqrt(cards_top / cards_here) puts the coverage back, and it is derived from the authored
    budgets rather than tuned, so it cannot drift away from ``foliage_ladder``.
    """
    ladder = foliage_ladder(species)
    if not ladder:
        return ()
    return tuple(math.sqrt(ladder[0] / value) for value in ladder)


#: Colmesh tubes: 2 R S == the authored budget.  Model species get a decimated convex hull
#: instead (no closed form), which is why only the generated shapes carry an analytic window.
COLMESH_TUBES = {24: (6, 2), 20: (5, 2), 16: (4, 2), 12: (3, 2), 10: (5, 1), 8: (4, 1)}

#: Twig-card size in METRES (half-side; the card is square because the atlas cell is).
#: Round 1 sized cards as a fraction of the branch reach and got 4.36 m^2 cards at 3.93 mm
#: per texel; three stock conifers measure 0.12-0.53 m^2 at 0.82-1.30 mm per texel.  A
#: half-side of 0.24-0.36 m is 0.23-0.52 m^2 of card and, over one 512 px cell of a 2048
#: atlas, 0.97-1.45 mm per texel -- the stock band, measured.  The cap keeps a 2.2 m
#: sapling's cards inside its own crown.
TWIG_CARD_HALF_M = (0.24, 0.36)
TWIG_CARD_REACH_CAP = 0.55

#: Leaf/frond/blade card half-side in METRES for the pure-card shapes (shrubs, ferns, reeds),
#: capped at a fraction of the plant's own height so a 1.6 m fern does not carry a 0.8 m frond.
#: r1 sized these as `height x 0.22..0.40`, which put 2.3-4.2 m cards on the 5.3 m `shrub_02`.
LEAF_CARD_HALF_M = (0.18, 0.42)
LEAF_CARD_HEIGHT_CAP = 0.26

# ---------------------------------------------------------------------------- the LOD ladder
#: r3.  A DISTANCE LOD is not a cheaper copy of the near mesh, it is the same SILHOUETTE drawn
#: with fewer, bigger cards.  r2 shipped the design's original ladder untouched below the top
#: detail: `pine_tall_a` went 4,172 -> 1,660 -> 296 FOLIAGE triangles, a last step of 5.61x
#: against the three stock conifers' <= 1.50x, and its lowest LOD kept 7 % of its top where
#: ECUSA's douglasfir keeps 49 %, italy's scots pine 46 % and WCUSA's radiata 50 %.  Since
#: design §4.3's own arithmetic (935 px per unit of H/d at 1080p) puts a 28 m tree's `_a100`
#: cut at 87 m and its imposter cut at 262 m, that 296-triangle mesh was what rendered EVERY
#: tree between 87 and 262 m -- the band a driver spends most of the time looking at, and the
#: band three of the six r2 frames show as a pole plantation.
#:
#: The r3 ladder is built from two rules, both measured against those three stock conifers:
#:   1. every step in FOLIAGE triangles is <= LOD_STEP_MAX (stock: 1.33-1.50)
#:   2. the card is scaled by sqrt(cards_top / cards_here), so the ladder conserves the crown's
#:      alpha-coverage AREA rather than shrinking it -- which is why the lowest LOD keeps the
#:      crown's WIDTH instead of dissolving into disconnected specks.
#: `forest_spec.lod_card_scale` is that sqrt, computed from the authored budgets, so the two
#: rules cannot drift apart.
LOD_STEP_MAX = 1.5
#: stock's lowest-LOD share of its own top LOD: 0.49 / 0.46 / 0.50.  The gate's floor.
LOD_LOW_TOP_MIN = 0.35

# ------------------------------------------------------------------------- crown architecture
#: r9 -- the user's override of r8's verdict: "fix the trees to make them reasonably realistic".
#:
#: r3-r8 hung every card at a random point inside a cone envelope (a golden-ratio radius, a
#: +-1 pitch z-spread and a free roll), which killed r2's plate comb -- and drew, at the
#: driver's eye, a uniform column of speckle around a bare pole that ends above the foliage:
#: the orchestrator's read of `b3_s7_forest_floor.png` is "poplars or cypresses ... no crown
#: taper, no tiered branch whorls, no spire, foliage clumps that float unattached".  MEASURED
#: against stock in `b3/r9/stock_census.json`: ECUSA's four douglas firs are serrated tiers
#: (a width-profile peak every 10 m on the 1 m bands, 0.05-0.17 centroid peaks per metre),
#: widest 72-84 % of the way down, W/H 0.37-0.47 with a 5-10 % spire; italy's scots pine is
#: a bare trunk to 45 % with an irregular rounded crown at W/H 0.61; r8's pines read W/H
#: 0.27-0.30 with 0 profile peaks and their trunk apex 1.2 m above the last card.
#:
#: The r9 crown is a BRANCH SKELETON, built once per species by :func:`crown_plan` and shared
#: by every LOD: whorls at a jittered pitch, each with 4-7 branches whose reach follows the
#: family's envelope (floor at the base, widest tier, then ``(1-u)^taper`` to a spire), drawn
#: as thin tapered tubes the sprays ATTACH to.  Cards hang along each branch as side sprays
#: with the spray's base on the branch axis, so nothing floats and the trunk shows between
#: the tiers at the base.  Every number below is either a stock reading from the census or a
#: botanical proportion; the per-species draw inside each range is what makes ten conifers
#: ten different trees.
CANOPY_TOP = 0.995
#: Two more knobs, added on the first crown-lab sheet of r9 (``b3/r9/crown_lab_sideviews.png``):
#: ``foliage_from`` is where along a branch the sprays BEGIN, as a share of its length -- a
#: pine keeps needles only on its last two or three years of growth, so its foliage is a
#: tuft at the branch end and the inner branch is bare wood (the lab's first pines carried
#: cards along the whole branch and read as Araucaria plates); a fir holds needles for a
#: decade and its sprays run the whole branch.  ``root_scatter`` jitters each branch's
#: insertion up or down the trunk by that share of the whorl pitch: a conifer's whorls are
#: pseudo-whorls with internodal branches, and it is what keeps the tiers from reading as a
#: comb on the gate's own banding statistic (stock douglas firs read prominence 5.6-11.5 on
#: it, italy's scots pine 16.2; ``b3/r9/stock_banding.json``).
CROWN_FAMILIES: dict[str, dict] = {
    "fir": dict(
        base=(0.10, 0.17),  # crown base, share of the tree's height
        # r10 (critic B9-3.1) -- THE INVERTED CONSTANT.  The census reads "widest 72-84 % of
        # the way DOWN from the top"; r9 wrote 0.72-0.84 into a parameter that means "UP from
        # the crown base", so every fir was widest a fifth of the way down and narrowed below
        # it.  Measured on the shipped bytes (`census/taper_compare.txt`): at 25 % down ours
        # were 0.938-1.000 of max width where all six stock douglas firs are 0.346-0.729, and
        # our `widest`-from-the-top read 0.20 / 0.27 / 0.35 against stock's 0.33-0.90.  A
        # crown coordinate u maps to a share from the top of about 0.865 - 0.86 u, so the
        # census band 0.72-0.84 down is u = 0.03-0.17 and the stock SPREAD 0.50-0.90 down is
        # u = 0.0-0.42.  0.10-0.30 sits inside both: widest 0.61-0.78 down, a cone.
        #
        # ...but 0.10-0.30 only put ONE of the five firs inside the plan's own [0.72, 0.84]
        # (0.583 / 0.680 / 0.714 / 0.733 / 0.870) and left `fir_mid_a`'s 25 %-down taper at
        # 0.748, 0.034 over the stock douglas fir's max.  The generator is bpy-free, so the
        # band was SWEPT offline through the census's own `profile_stats` instrument over 42
        # candidate ranges (`r10/crown_sweep.json`, and the sweep reproduces the shipped tree's
        # 0.583-0.870 / 0.515-0.748 exactly at 0.10-0.30, which is what makes it trustworthy).
        # 0.04-0.18 is the best of them: **4 of 5 inside [0.72, 0.84]** (0.800 / 0.810 / 0.833
        # / 0.840, with `fir_tall_b` 0.870 the one outside) and **all five tapers inside the
        # stock douglas fir's 0.381-0.714** at 0.502-0.635.  Trimming `width_over_height` with
        # it was measured too (`r10/crown_pick.json`) and costs more than it buys: it drops the
        # plan band back to 3 of 5 to save one W/H reading.
        widest=(0.04, 0.18),
        width_over_height=(0.38, 0.45),  # ECUSA douglas firs 0.37-0.47; r9 shipped 0.47-0.56
        upper_taper=0.72,  # (1-u)^p above the widest tier: 1.0 is a straight cone
        lower_floor=0.74,  # the lowest tier's reach as a share of the widest tier's
        pitch=(0.040, 0.052),  # whorl pitch, share of the tree's height (1.0-1.4 m on 26 m)
        pitch_jitter=0.36,
        per_whorl=(5, 7),
        elevation_deg=(-28.0, -2.0),  # branch angle to the horizontal at the whorl
        elevation_rise_deg=16.0,  # the upper whorls rise this much more than the lower ones
        sag=0.10,  # mid-branch droop, share of the branch length
        tip_lift=0.14,  # the tip curls back up by this share of the branch length
        sub_branches=0,
        spire=0.09,  # the top share of the height that is the leader with mini whorls
        foliage_from=0.10,
        # r11 (critic B10-1): how far along a branch the WOOD runs, as a share of its length.
        # See the pine's note -- a fir never had the defect (0.0 % of its crown bands) because
        # its sprays start at 0.10 and run the whole branch, but it inherits the same rule so
        # that no future foliage change can uncover a tip.
        wood_reach=0.88,
        root_scatter=0.30,
    ),
    "pine": dict(
        base=(0.30, 0.42),  # italy scots_pine: bare trunk to 45 %
        widest=(0.50, 0.70),
        # r10 (critic B9-3.2): the pines shipped W/H 0.39-0.43 against scots pine's 0.61 and
        # their imposter card filled 0.177-0.189 of its box where the LOWEST of twelve stock
        # atlases is 0.221.  A scots pine is bare to 45 % of its height and still the densest
        # imposter in the set, so the fix is not less trunk: it is a wider, deeper, more
        # closely whorled crown carrying foliage further back down each branch.
        width_over_height=(0.54, 0.66),
        upper_taper=0.50,  # a rounder, fuller top than a fir
        lower_floor=0.70,
        pitch=(0.058, 0.080),  # 1.6-2.2 m on 28 m: a pine's internodes are long
        # r10: 0.50 -> 0.74 and root_scatter 0.70 -> 1.00.  This round raised the three tall
        # pines' card budgets 8,940/6,610/4,664 -> 13,000/9,600/6,800 (their imposters baked
        # below stock's own equator-fill floor), and more cards on the same whorls is a
        # STRONGER vertical period: `pine_tall_a` came out at banding prominence 18.74 on a
        # 2.94 m period against the adopted ceiling of 18.0 (stock's worst, italy's scots
        # pine, is 16.2) -- a ladder of plates on a pole, which is the exact defect critic r2
        # named.  Swept in the bpy-free generator over 16 combinations
        # (`b3/r10/banding_sweep.json`, and it reproduces the shipped 18.74 at 2.94 m
        # exactly): at 0.74/1.00 `pine_tall_a` reads 11.64 and no pine is over 12.89, with
        # trough 4.3 % and band strength 0.052.  root_scatter 1.00 is the parameter's own
        # botanical limit -- a pseudo-whorl's internodal branch can sit anywhere in the
        # internode -- and the budget is untouched, so the imposter fill is untouched too.
        pitch_jitter=0.74,
        per_whorl=(5, 8),
        elevation_deg=(-12.0, 30.0),
        elevation_rise_deg=24.0,
        sag=0.04,
        tip_lift=0.28,
        sub_branches=3,
        spire=0.07,
        foliage_from=0.34,
        # r11 (critic B10-1).  THE BLOCKING NUMBER.  r10 drew the woody tube from the trunk to
        # the branch's Bezier apex -- the whole branch -- while the sprays stopped at
        # `1 - (1-foliage_from)*0.5/count` and the last two turned UP into the candle tuft, so
        # the outermost thing on a pine branch, horizontally, was bark.  Measured through the
        # critic's own `bare_wood_silhouette` (`r11/armature_lab.py`, which reproduces its
        # table to the decimal): 56.7 % / 55.9 % / 36.8 % of `pine_tall_a` / `_b` / `pine_mid_a`
        # crown height bands were widened by naked wood, mean 0.21-0.90 m and max 3.20 m,
        # where italy's `scots_pine` -- with a comparable 586-triangle armature -- reads 0.0 %
        # and 0.05 m.  Ending the wood inside the needle mass is what a real pine does: the
        # outer third of a branch is the last two or three years' shoot, thinner than a pencil
        # and buried in needles.  Swept in the bpy-free lab over the whole family
        # (`r11/wood_reach_sweep.json`); the shipped value is the loosest one that puts every
        # pine at 0.0 % with margin.
        wood_reach=0.52,
        root_scatter=1.00,
    ),
    "sapling": dict(
        base=(0.06, 0.12),
        widest=(0.62, 0.80),
        width_over_height=(0.40, 0.50),
        upper_taper=0.85,
        lower_floor=0.80,
        pitch=(0.085, 0.115),
        pitch_jitter=0.30,
        per_whorl=(4, 6),
        elevation_deg=(-10.0, 10.0),
        elevation_rise_deg=10.0,
        sag=0.05,
        tip_lift=0.12,
        sub_branches=0,
        spire=0.10,
        foliage_from=0.15,
        wood_reach=0.86,  # r11 (critic B10-1)
        root_scatter=0.25,
    ),
    "dwarf": dict(
        base=(0.03, 0.06),
        widest=(0.50, 0.70),
        width_over_height=(0.50, 0.62),
        upper_taper=0.70,
        lower_floor=0.85,
        pitch=(0.10, 0.14),
        pitch_jitter=0.30,
        per_whorl=(4, 6),
        elevation_deg=(5.0, 30.0),
        elevation_rise_deg=8.0,
        sag=0.0,
        tip_lift=0.15,
        sub_branches=1,
        spire=0.08,
        foliage_from=0.30,
        wood_reach=0.66,  # r11 (critic B10-1): a dwarf pine is a tuft on a knee of wood
        root_scatter=0.30,
    ),
}
#: cards reserved for the LEADER (vertical cards on the trunk tip), top detail first
LEADER_CARDS = (4, 3, 2)
#: how far along a main branch a sub-branch forks, and how long it is (share of the rest)
SUB_BRANCH_AT = (0.40, 0.72)
SUB_BRANCH_LENGTH = (0.45, 0.70)


def crown_family(species: dict) -> str:
    key = species["key"]
    if key.startswith("dwarf"):
        return "dwarf"
    if "sapling" in key:
        return "sapling"
    return "fir" if key.startswith("fir") else "pine"


def _smoothstep(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def crown_envelope(u: float, widest: float, family: dict) -> float:
    """Reach at crown height ``u`` (0 = crown base, 1 = tip) as a share of the widest tier's."""
    if u <= widest:
        floor = family["lower_floor"]
        return floor + (1.0 - floor) * _smoothstep(u / max(widest, 1e-6))
    return max(((1.0 - u) / max(1.0 - widest, 1e-6)) ** family["upper_taper"], 0.03)


def crown_plan(species: dict) -> dict:
    """The deterministic branch skeleton of one generated conifer, shared by every LOD.

    Pure python off ``SHAPE_SEED`` and the species key, so the gates can re-derive it in a
    bare interpreter and the generator cannot drift from what the layout budgeted.  Lengths
    are metres in the shape's own frame at scale 1; azimuths and elevations are radians.
    """
    family = CROWN_FAMILIES[crown_family(species)]
    rng = random.Random(f"{SHAPE_SEED}:{species['key']}:crown")  # noqa: S311 - seeded geometry
    height = species["height_m"]
    base = height * rng.uniform(*family["base"])
    tip = height * CANOPY_TOP
    spire_top = height * (1.0 - family["spire"])
    width_over_height = rng.uniform(*family["width_over_height"])
    r_max = 0.5 * width_over_height * height
    widest = rng.uniform(*family["widest"])
    pitch = height * rng.uniform(*family["pitch"])
    jitter = family["pitch_jitter"]
    elevation_lo, elevation_hi = family["elevation_deg"]
    whorls: list[dict] = []
    z = base + rng.uniform(0.0, 0.6) * pitch
    phase = rng.uniform(0.0, 2.0 * math.pi)
    mains = subs = 0
    while z < tip - 0.12 * pitch:
        u = (z - base) / max(tip - base, 1e-6)
        in_spire = z >= spire_top
        reach = r_max * crown_envelope(u, widest, family)
        count = rng.randint(2, 3) if in_spire else rng.randint(*family["per_whorl"])
        phase += 2.399963 + rng.uniform(-0.3, 0.3)  # the golden angle: no two tiers align
        branches = []
        for index in range(count):
            azimuth = (phase + 2.0 * math.pi * index / count + rng.uniform(-0.22, 0.22)) % (
                2.0 * math.pi
            )
            length = max(0.25, reach * rng.uniform(0.84, 1.16))
            elevation = math.radians(
                rng.uniform(elevation_lo, elevation_hi) + family["elevation_rise_deg"] * (u - 0.5)
            )
            branch = dict(
                azimuth=round(azimuth, 5),
                length=round(length, 4),
                elevation=round(elevation, 5),
                sag=round(family["sag"] * rng.uniform(0.6, 1.4), 4),
                lift=round(family["tip_lift"] * rng.uniform(0.6, 1.4), 4),
                # the insertion, up or down the trunk from the whorl's own z (a pseudo-whorl)
                dz=round(rng.uniform(-1.0, 1.0) * family["root_scatter"] * pitch, 4),
                subs=[],
            )
            if not in_spire and length > 1.2:
                for _ in range(family["sub_branches"]):
                    at = rng.uniform(*SUB_BRANCH_AT)
                    side = rng.choice((-1.0, 1.0))
                    branch["subs"].append(
                        dict(
                            at=round(at, 4),
                            yaw=round(side * math.radians(rng.uniform(28.0, 52.0)), 5),
                            pitch=round(math.radians(rng.uniform(2.0, 26.0)), 5),
                            length=round(length * (1.0 - at) * rng.uniform(*SUB_BRANCH_LENGTH), 4),
                        )
                    )
            subs += len(branch["subs"])
            branches.append(branch)
        mains += count
        whorls.append(dict(z=round(z, 4), u=round(u, 4), reach=round(reach, 4), branches=branches))
        step = pitch * (1.0 + rng.uniform(-jitter, jitter))
        z += step * (0.55 if in_spire else 1.0)
    return dict(
        family=crown_family(species),
        base=round(base, 4),
        tip=round(tip, 4),
        spire_top=round(spire_top, 4),
        r_max=round(r_max, 4),
        width_over_height=round(width_over_height, 4),
        widest=round(widest, 4),
        pitch=round(pitch, 4),
        whorls=whorls,
        mains=mains,
        subs=subs,
    )


#: Trunk proportions used by both the generator and the ray-census predictor.
TRUNK_RADIUS_FRACTION = 0.020  # base radius as a fraction of the tree's height
TRUNK_TAPER = 0.85  # radius at the top ring = base * (1 - TRUNK_TAPER)
COLMESH_HEIGHT_FRACTION = 0.90  # the Colmesh cone covers 90 % of the tree


def colmesh_profile(species: dict) -> dict | None:
    """Ring z/r table of a generated shape's Colmesh cone, in LOCAL metres at scale 1.

    Rings sit at z = Hc * s / S for s in 0..S-1 with r = r0 (1 - TRUNK_TAPER s / S); the apex
    closes the cone at z = Hc.  ``None`` for model species (convex hull, no closed form).
    """
    if species["build"] not in ("conifer", "snag") or species["colmesh"] not in COLMESH_TUBES:
        return None
    radial, rings = COLMESH_TUBES[species["colmesh"]]
    height = species["height_m"] * COLMESH_HEIGHT_FRACTION
    r0 = species["height_m"] * TRUNK_RADIUS_FRACTION
    table = [(height * s / rings, r0 * (1.0 - TRUNK_TAPER * s / rings)) for s in range(rings)]
    return {"radial": radial, "rings": table, "apex_z": height, "r_base": r0}


def colmesh_hit_window(species: dict, lateral_offset_m: float, scale: float) -> tuple[float, float]:
    """(low, high) metres above the instance base where a vertical ray meets the Colmesh.

    The cone is faceted, so a ray at a fixed radius meets it anywhere between the inscribed
    radius (cos(pi/R) x r) and the circumscribed r -- the same argument the level scaffold's
    ``blender_placeholders.canopy_flank_z`` makes for its placeholder canopy.
    """
    profile = colmesh_profile(species)
    if profile is None:
        raise ValueError(f"{species['key']} has no analytic Colmesh")
    d = lateral_offset_m / scale
    inscribed = math.cos(math.pi / profile["radial"])
    segments = [*profile["rings"], (profile["apex_z"], 0.0)]

    def z_where(shrink: float) -> float:
        for (z0, r0), (z1, r1) in itertools.pairwise(segments):
            a, b = r0 * shrink, r1 * shrink
            if a >= d >= b and a > b:
                return z0 + (z1 - z0) * (a - d) / (a - b)
        raise ValueError(f"offset {lateral_offset_m} m never meets {species['key']}'s Colmesh")

    return scale * z_where(inscribed), scale * z_where(1.0)


#: Cover shapes reuse the tube primitive for their Colmesh (8 tris = R 4, S 1).
COVER_COLMESH_TUBE = COLMESH_TUBES[8]
