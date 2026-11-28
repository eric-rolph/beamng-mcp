"""B2's hearth: the frozen design's §3 turned into records, budgets and names.

This module is PURE.  It reads the frozen ``layout.json`` (vendored into
``authoring/`` by B1) and the frozen ``terrain_model`` and turns them into

* the six stone shapes' LOD/Colmesh/texture budgets (:data:`STONE_SOURCES`),
* the ember-crust plate's mesh recipe and the 24 sector instances,
* the level-shipped particle / SFX / decal datablocks (B0's proven forms),
* the 619 static-decal rows in 12 keys and 6 families,
* every scene record of the ``hearth`` / ``night_light`` / ``Audio`` groups.

Nothing here touches the disk or Blender; ``blender_hearth`` builds the shapes,
``hearth_textures`` cooks the maps and ``place_hearth`` writes the tree.

Laws this module is written against (``level_round/level_facts.md``):

* the core ``EmberEmitter`` / ``EmberNode`` / ``EmberParticle`` do NOT exist and
  ``BNGP_65`` is a 20 ms flash -- the embers are a LEVEL-shipped datablock
  triple under ``levels/<id>/art/datablocks/*.datablocks.json`` (B0 r2);
* a level ``SFXProfile`` with ``AudioDefaultLoop3D`` loops; the stock
  ``FireLoopSound1/2`` are one-shot and are never named;
* ``nightLight`` / ``utcOffset`` and the night-window fields are STRINGS;
* a material's ``version`` must match the slots its maps occupy -- every
  material here authors PBR slots (``baseColorMap`` ...) and declares 1.5;
* every texture dimension is a power of two or it is silently never cooked;
* SimObject names are global across classes, so every name is namespaced and
  the census gate refuses a collision.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from pathlib import Path
from typing import Any

EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
AUTHORING = EXAMPLE_ROOT / "authoring"
LEVEL_ID = "ericrolph_hot_potato_arena"
LEVEL_RELATIVE = f"levels/{LEVEL_ID}"

#: The frozen design layout, vendored by B1 beside the other authoring inputs.
LAYOUT_PATH = AUTHORING / f"{LEVEL_ID}.level_layout.json"
#: The frozen design's own lock, so a gate can prove the layout it read is v4's.
DESIGN_LOCK_PATH = AUTHORING / "level_design_v4.lock.json"

C = (850.0, -280.0, 100.000)

# --- directories inside the level tree (B2 owns all four) ----------------------------
SHAPE_DIR = "art/shapes/hearth"
DECAL_DIR = "art/decal"
DATABLOCK_DIR = "art/datablocks"
AUDIO_DIR = "dynamicAudioEmitters"

#: Scene groups B2 adds under ``MissionGroup``.  JV's own are ``night_light`` and
#: ``Audio``, but a SimGroup's name is a SimObject name and those are GLOBAL across
#: classes (level_facts), and the level already carries a terrain layer whose
#: internalName is ``hearth`` -- so B2's three groups are namespaced like everything
#: else this round ships.  The DIRECTORY under ``main/MissionGroup/`` must carry the
#: same name (stock: ``main/MissionGroup/night_light/items.level.json`` holds a group
#: named ``night_light``).
GROUP_HEARTH = f"{LEVEL_ID}_hearth"
GROUP_NIGHT = f"{LEVEL_ID}_night_light"
GROUP_AUDIO = f"{LEVEL_ID}_audio"

# --- seeds (every random draw below is a pure function of one of these) --------------
SHAPE_SEED = 0x48525448  # "HRTH"
CRUST_SEED = 0x43525354  # "CRST"
DECAL_SEED = 0x44434C53  # "DCLS"
TEXTURE_SEED = 0x48544558  # "HTEX"

# --- stones (design §3.1) ------------------------------------------------------------
#: ``asset -> (native longest axis m, detail budgets, colmesh budget, map size)``.
#: Details ``_a900`` 6,000 / ``_a400`` 2,000 / ``_a150`` 600 triangles, a
#: ``bb_autobillboard25`` imposter node, ``nulldetail4`` and a
#: ``Colmesh_<stem>-1`` (design §3.1).
STONE_DETAILS: tuple[tuple[int, int], ...] = ((900, 6000), (400, 2000), (150, 600))
STONE_NULLDETAIL = 4
#: r6 DEVIATION from §3.1's "<= 240 triangles (QB-7's rock guidance is <= 250)", stated
#: once and gated per source below.  240 was the budget for a CONVEX HULL, which needs
#: no triangles because it has no concavity to follow.  r6 makes the collider a
#: DECIMATED COPY of the visual solid (``blender_forest.solid_colmesh_of``, B3 r9's
#: proven route), and a copy is only worth its collapse error: at 240 triangles a 36 m
#: stone's collider carries 3 m faces and would re-create in the collapse exactly the
#: phantom wall the hull was removed to kill.  B3 ships 2,000 for its 21 m and 15 m
#: cliff outcrops and 4,000 for the 41 m crag on the SAME three detail budgets as these
#: stones, and critic B3 pass 9 rammed those in the engine: hit vs Colmesh vs visual
#: agreed to 0.014-0.092 m.  The hearth takes the same ladder by world height.  240
#: remains the DEFAULT for anything without a row.
STONE_COLMESH_TRIS = 240

#: r6: how each stone source is turned into a body, and how big its collider may be.
#: ``solid="voxel"`` re-meshes a closed-ISH scan through OpenVDB and transfers its UVs
#: back: three of the five other stones carry 1-5 non-manifold edges and 0-6 boundary
#: edges at every LOD that no weld can close (B3's own finding on these same PolyHaven
#: scans), and a collider that cannot close falls back to the convex hull -- which is the
#: phantom wall again, in miniature.  B3 ships ``namaqualand_boulder_02/03/05`` on exactly
#: this route.  ``None`` keeps the plain weld-and-seal import for the two scans that
#: already close (``boulder_01``, ``namaqualand_boulder_04``), which r6 measures at
#: 0.99-1.00 volume ratio with a decimated-solid collider -- there is nothing left for a
#: remesh to buy them.
#:
#: **r7 (critic B2 pass 6's N4): ``solid="face"`` is RETIRED and this docstring no longer
#: documents it.**  ``rock_solid.solid_from_face_scan`` thickens a photogrammetry FACE scan
#: into an invented body.  It passes every geometry gate -- volume ratio 0.972-1.000,
#: phantom p50 4 mm, the drive-in proof at 0.0000 m -- and the boot's own frames refused it:
#: the invented skirt renders as a 35 m wall of ruled ledges (``b2/r6/view6/R6_faces_day.jpg``).
#: The husk probe then put a number on the same body, **fill 0.197 / solidity 0.59**, which
#: is SUSPECT under both bars.  Two methods, one verdict.  ``STONE_SOLID`` has carried four
#: ``"voxel"`` entries and no ``"face"`` since the re-source; the words above described a
#: route nothing takes, and a reader arriving in r8 would have believed the hearth ships it.
STONE_SOLID: dict[str, str] = {
    "rock_face_01": "voxel",
    "namaqualand_boulder_02": "voxel",
    "namaqualand_boulder_03": "voxel",
    "namaqualand_boulder_05": "voxel",
}
#: deterministic seed for a body route's invented relief, kept because ``blender_hearth``
#: still passes it to ``import_model``.  r7: the route it was named for (``solid="face"``)
#: is retired, so this is reachable only if a future revision re-declares one.
STONE_SOLID_SEED = 0x48525346  # "HRSF" -- hearth rock solid face
#: collider triangle budget per source (see ``STONE_COLMESH_TRIS``).
#:
#: **The three declared deviations from design §3.1, r7 (critic B2 pass 6's N5).**  r6 took
#: two of these and declared one; all three are now on the record here, beside the code:
#:
#: 1. **The budget.**  §3.1 reads *"Colmesh <= 240 tris (a convex-hull decimation of the
#:    ``_a150`` mesh; QB-7's rock guidance <= 250)"*.  240 is explicitly a budget for a
#:    convex HULL, and a hull is the phantom wall the 2026-09-07 law forbids.  A concave
#:    copy decimated to 240 collapses back into one.  DECLARED, argued, and correct.
#: 2. **The collider's SOURCE detail.**  §3.1 says the decimation is of the ``_a150`` mesh;
#:    the collider is decimated from the FINEST visual instead, which is what makes it hug
#:    the visual to a median 0.0000 m.  r6 took this silently.  DECLARED here.
#: 3. **The §3.1 source column.**  Its heading is *"source model (CC0) -> scale"* and the
#:    four hero rows read ``rock_face_01 (7.11 m) x 5.1``.  Since the re-source the shipped
#:    stone is ``rock_07 (0.32 m) x 112`` and those four rows are wrong as written.  The
#:    frozen spec is not B2's to edit, so the corrected rows are published in the report's
#:    deviation table; ``stone_source_folder`` is where the change actually lives.  The 112x
#:    is also the direct cause of C6-1 and of the low-frequency attenuation above.
STONE_COLMESH_BUDGET: dict[str, int] = {
    "rock_face_01": 4000,  # 36 m x 26 m -- B3's crag row
    "boulder_01": 2000,  # 30 m -- B3's cliff outcrop row
    "namaqualand_boulder_03": 2000,  # 28 m
    "namaqualand_boulder_04": 2000,  # 22 m
    "namaqualand_boulder_02": 2000,  # 20 m
    "namaqualand_boulder_05": 600,  # 10 m
}

#: **r7 (critic C6-1): the detail graft, and every number that sets it.**
#:
#: r6 fixed the hearth's geometry by re-sourcing the 36 m slot to ``rock_07`` -- a full
#: 360-degree scan, which killed the facade -- and shipped that scan's own maps with it.
#: Measured on the shipped bytes (``b2/r7/map_detail_r7.py``, the critic's definitions
#: unchanged), those maps are the worst surface in the ring:
#:
#: =========================== ========= ==================== ==============
#: statistic                   hero r6   five neighbours      ring median
#: =========================== ========= ==================== ==============
#: colour power above N/4         0.0273   0.1255 - 0.1827        0.1707
#: colour mean |Laplacian|        0.0295   0.0709 - 0.1023        0.0771
#: normal xy relief p50           0.1542   0.1386 - 0.2483        0.1723
#: =========================== ========= ==================== ==============
#:
#: **Re-sourcing again does not fix it.**  Every scan in ``cc0_cache/`` was measured at the
#: cook's own 2048 (``map_detail_sources.json``): the critic's two suggested alternatives
#: read colour HF **0.061** (``rock_09``) and **0.015** (``stone_01``) -- both WORSE than
#: ``rock_07``'s neighbours, and ``rock_09`` carries a constant roughness of its own.
#:
#: **And the biggest cause is not detail at all, it is gloss.**  ``rock_07``'s ``arm`` G
#: channel is a CONSTANT **0.2979** (p05 0.2941, p95 0.3020, std 0.0025 across 2048x2048;
#: ``b2/r7/gloss_probe.json``).  That is a placeholder, not a measurement, and the cook
#: shipped it: ``rock_face_01_r.data.png`` reads mean **0.4096** over 0.3765-0.4431 -- the
#: only roughness in the ring below 0.86 (the other five are 0.8622-0.9686).  A near
#: constant LOW roughness over a 36 m face is one broad specular lobe across the whole
#: stone, which is what "wax", "crumpled-foil sheen" and "faceted amber resin" describe.
#:
#: So the fix is a texture and material one, the geometry is untouched, and it has three
#: parts.  A slot names a DETAIL DONOR -- a CC0 scan already in the provenance ledger --
#: and the cook takes from it only what the slot's own source cannot supply:
#:
#: 1. **roughness**, whenever the source's own is degenerate (``ROUGHNESS_DEGENERATE_STD``).
#:    A constant is not a measurement.
#: 2. **high-frequency grain** on colour, normal and AO, tiled ``DETAIL_TILES`` times so it
#:    lands at a rock's own scale rather than the source's magnified one.
#: 3. **an attenuation of the base colour's lowest frequencies**, which is the other half of
#:    the same fact: this slot magnifies a **0.32 m** scan **112x**, so a 5 cm patch of the
#:    original becomes 5.6 m on the placed stone and a 30 cm one becomes 34 m.  Colour
#:    blotches ten to thirty metres across are the magnification, not the rock.
#:
#: The constants were chosen by a published sweep (``b2/r7/detail_graft_sweep2.json``),
#: against the pass rule critic B2 r6 wrote for this defect -- *the hero stone must be no
#: worse than the ring's median* -- and NOT by eye.  At these values the hero lands colour
#: HF **0.186** / mean |lap| **0.094** / normal p50 **0.184**, clearing all three medians,
#: with zero clipped pixels and a colour std of 0.103 inside the neighbours' 0.091-0.116.
#: ``rock_face_01``'s own photograph was measured as the alternative donor at the same
#: settings and lands 0.176 -- it clears too; ``namaqualand_boulder_06`` is chosen because
#: it is the strongest rock in the cache (source colour HF 0.212) and is the same
#: photogrammetry family as four of the five neighbours, so the grain reads as the ring's.
#: Only HIGH-FREQUENCY content is taken: the donor's body, silhouette and colour are not.
STONE_DETAIL_DONOR: dict[str, str] = {"rock_face_01": "namaqualand_boulder_06"}
#: how many times the donor is tiled across the map.  The slot is 36 m over a 2048 map =
#: 17.58 mm/texel; 4 tiles puts the donor's 2.6 m scan at roughly its own physical scale.
DETAIL_TILES = 4
#: the grain cut, in map pixels: content finer than this is the donor's, coarser is the
#: body's.  3 px at 17.58 mm/texel is about 5 cm on the placed stone.
DETAIL_SIGMA_PX = 3.0
DETAIL_COLOUR_GAIN = 2.2
DETAIL_NORMAL_GAIN = 0.6
DETAIL_AO_GAIN = 0.6
#: the low-frequency attenuation: colour structure coarser than 2 x 96 px (**3.38 m** on
#: the placed stone) is halved.  Not removed -- halved, so the stone keeps its own body.
DETAIL_BASE_LF_SIGMA_PX = 96.0
DETAIL_BASE_LF_GAIN = 0.50
#: a roughness channel flatter than this over a whole 2k map is a placeholder.  ``rock_07``
#: reads 0.0025 and ``rock_09`` 0.0026; every scan with a real one reads 0.017-0.081.
ROUGHNESS_DEGENERATE_STD = 0.010
#: Where the substituted roughness is PLACED, and how much it is allowed to vary.  Taking
#: the donor's channel raw and letting the cook's own darkness lift run on top of it landed
#: the hero at mean **0.9929** / std 0.0152 -- above the ring's own maximum and clipped
#: nearly flat, which trades a uniform GLOSSY surface for a uniform MATTE one.  Both
#: numbers below are the MEDIAN of the five neighbours' shipped ``_r.data.png``
#: (means 0.8622 / 0.8771 / 0.9305 / 0.9670 / 0.9686; stds 0.0284 / 0.0344 / 0.0372 /
#: 0.0559 / 0.0568), so the substituted channel keeps the donor's measured VARIATION and is
#: placed at the ring's measured LEVEL.  Neither is a taste knob.
DETAIL_ROUGHNESS_TARGET_MEAN = 0.9305
DETAIL_ROUGHNESS_TARGET_STD = 0.0372


def stone_detail_donor(asset: str) -> str | None:
    """The ``cc0_cache/`` folder one stone slot borrows high-frequency detail from."""

    return STONE_DETAIL_DONOR.get(asset)


def stone_source_folder(asset: str) -> str:
    """The ``cc0_cache/`` folder one stone SLOT is derived from.

    r6: the design's §3.1 table names the slot (``rock_face_01``) and the frozen
    ``layout.json`` uses that name on 4 of its 28 rows, so the slot name is not free.
    The CC0 SCAN behind it is: ``source`` lets a slot be re-sourced without renaming the
    material, the shape stem, the cooked maps or a single layout row.  Defaults to the
    slot's own name, which is what the other five do.
    """

    return str(STONE_SOURCES[asset].get("source", asset))


def stone_solid(asset: str) -> str | None:
    """The body route for one stone source (``"face"`` or ``None``)."""

    return STONE_SOLID.get(asset)


def stone_colmesh_budget(asset: str) -> int:
    """The collider triangle budget for one stone source."""

    return int(STONE_COLMESH_BUDGET.get(asset, STONE_COLMESH_TRIS))


#: r2 (critic r1 D1): the three 1024 rows are now 2048.  Every CC0 source in
#: ``cc0_cache/`` is a PolyHaven **2k** set, so 1024 was a DOWNSAMPLE and the three
#: stones that took it carried the round's worst texel densities -- 44.298 mm/texel on
#: ``namaqualand_boulder_04`` (the 22 m stone at the -30 deg slot of all four
#: clusters), 33.829 on ``_02``, 16.371 on ``_05``.  Cooking them at the source's own
#: 2048 recovers REAL detail (44.298 -> 22.149 / 33.829 -> 16.915 / 16.371 -> 8.186)
#: and costs +37.8 MB of resident DDS over the 1024 rows design section 9 budgets for them.
#: The three 2048 rows are NOT raised: their sources are 2k as well, so a 4096 cook
#: would be an upsample -- fake resolution that improves the metric and shows the
#: player nothing.  Section 8's "<= 15 mm/texel" therefore still misses on five of six
#: sources and the only honest fix is a 4k re-fetch; the price is in report section 8.
STONE_SOURCES: dict[str, dict[str, Any]] = {
    "boulder_01": {"native_m": 1.83, "map_px": 2048, "part": None},
    # r6: the SLOT keeps its name (the frozen layout uses it on four rows) but is re-sourced.
    # `rock_face_01` is a scan of a cliff FACE and has no back; r6 first rebuilt one with
    # `rock_solid.solid_from_face_scan`, which passes every geometry gate (volume ratio
    # 0.972-1.000, phantom p50 4 mm) and then FAILED the only test that matters -- the boot's
    # own frames show the invented body's skirt as a 35 m wall of ruled ledges, and two of the
    # four instances turn exactly that wall to the arena (`b2/r6/view6/R6_faces_day.jpg`).
    # `rock_07` is a full 360-degree scan: photographed on every bearing, closed, and it
    # reads as an angular layered monolith rather than a sixth rounded boulder
    # (`b2/r6/cand/CAND_SHEET.jpg`, six candidates at this exact size).  native_m 0.32 is a
    # 112x magnification, the largest in the ring -- but mm/texel at world scale is
    # world_size x 1000 / map_px whatever the source's own size, so it lands at the same
    # 24 mm/texel the others do (`b2/r6/uv_probe.json`), and rock is self-similar.
    "rock_face_01": {"native_m": 0.32, "map_px": 2048, "part": None, "source": "rock_07"},
    "namaqualand_boulder_02": {"native_m": 2.53, "map_px": 2048, "part": None},
    "namaqualand_boulder_03": {"native_m": 3.07, "map_px": 2048, "part": None},
    "namaqualand_boulder_04": {"native_m": 2.52, "map_px": 2048, "part": None},
    "namaqualand_boulder_05": {"native_m": 1.36, "map_px": 2048, "part": None},
}

#: The soot grading (§3.1).  The design asks for "multiply by 0.45 -> 1.0 from the
#: inner face upward over the lower 6 m, baked into a vertex-colour channel and
#: applied via ``vertColor true``".  DEVIATION, stated once and gated: the gradient
#: is a function of HEIGHT ABOVE THE FOOT only, not of facing.  Four clusters share
#: one DAE per source at four different yaws (STONE_PATTERN), so a facing-dependent
#: bake would need four DAEs per source -- and soot from a bed of coals rises, it
#: does not pick a compass direction.  ``vertColor true`` inside ``Stages[0]`` on a
#: v1.5 material is stock practice (italy ``italy_rocksface``).
SOOT_FLOOR = 0.45
SOOT_TOP_M = 6.0

# --- the ember particles (design §3.2), re-tuned in r2 --------------------------------
#: B2's own particle sprites.  The design names the stock ``art/shapes/particles/
#: ember.png`` by path and r1 shipped it; the critic then found what it draws.
#:
#: **What r1's frames actually contained** (critic r1 D2, reproduced here from the
#: shipped PNGs): the glow emitter rendered as a hard-edged SATURATED WHITE RECTANGLE
#: -- on ``S4_ember_night`` the blue channel jumps from 90 to 255 across five pixels
#: and holds 255 for thirty-six, bbox fill 0.98, 972 px, gone in the emitters-off
#: control -- and the sparks rasterised as filled squares (median blob aspect 1.00,
#: fill 0.875).  Two causes, both measurable from the datablocks:
#:
#: 1. **Stacking.**  ``pd_ember_glow`` lives 2500 ms and its emitter ejects every
#:    120 ms at 0.2 m/s, so ~21 sprites are alive per node and drift 0.5 m in a whole
#:    lifetime -- they sit on top of each other.  ADDITIVE at colour alpha 0.35 sums
#:    to ~7x saturation, and once every channel clips, the visible edge is no longer
#:    the sprite's falloff, it is the sprite's BOUNDING BOX.
#: 2. **The texture never reaches zero alpha.**  Stock ``ember.png``'s alpha runs
#:    4..255 (mean 132), so even its corners contribute; under 7x saturation the
#:    corners clip too and the quad shows.
#:
#: r2 fixes both.  The two sprites are AUTHORED here
#: (``hearth_textures.cook_particles``) with a true radial falloff that reaches alpha
#: **0** well inside the border, and the tuning below brings the summed additive peak
#: from ~7.3 down to **~0.5** for the glow (10.4 live sprites x 0.06 peak alpha x 0.8
#: mean texture alpha over the core) and from 1.0 to 0.75 for a spark.  DEVIATION from
#: the frozen ``layout.json particle_datablocks``, stated: three colour ramps, one
#: ejection period and two texture paths differ from the freeze; the geometry, the
#: node count, the blend style and the datablock NAMES do not.
PARTICLE_DIR = "art/shapes/particles"
#: sprite -> (pixels, the design intent the cook renders)
PARTICLE_SPRITES: dict[str, dict[str, Any]] = {
    "spark": {
        "px": 64,
        "core": 0.16,
        "falloff": 2.2,
        "note": "a hot coal fleck: a small white-hot core with a short radial tail",
    },
    "glow": {
        "px": 128,
        "core": 0.10,
        "falloff": 1.5,
        "note": "the bed's breath: a broad soft dome with a ragged rim, alpha 0 at the edge",
    },
    "wisp": {
        "px": 128,
        "core": 0.05,
        "falloff": 1.2,
        "note": "a warm-grey steam puff, ragged rim, alpha 0 at the edge",
    },
}


def particle_texture(kind: str) -> str:
    """The level-relative VFS path a ``ParticleData.textureName`` names."""

    if kind not in PARTICLE_SPRITES:
        raise HearthSpecError(f"unknown particle sprite {kind!r}")
    return f"{LEVEL_RELATIVE}/{PARTICLE_DIR}/{LEVEL_ID}_particle_{kind}.png"


#: Applied over the frozen records in :func:`particle_datablock_files`.
PARTICLE_TUNING: dict[str, dict[str, Any]] = {
    "pd_ember": {
        "textureName": None,  # filled in below with particle_texture("spark")
        "colors": [
            [1.0, 0.52, 0.12, 0.75],
            [1.0, 0.38, 0.07, 0.62],
            [0.8, 0.19, 0.02, 0.32],
            [0.3, 0.05, 0.0, 0.0],
        ],
    },
    "pd_ember_glow": {
        "textureName": None,  # filled in below with particle_texture("glow")
        "colors": [
            [1.0, 0.35, 0.08, 0.060],
            [1.0, 0.30, 0.06, 0.050],
            [0.6, 0.12, 0.02, 0.025],
            [0.2, 0.03, 0.0, 0.0],
        ],
    },
    "pe_ember_glow": {
        # 2500 ms / 240 ms = 10.4 live sprites per node instead of 20.8
        "ejectionPeriodMS": 240,
        "periodVarianceMS": 80,
    },
}
PARTICLE_TUNING["pd_ember"]["textureName"] = particle_texture("spark")
PARTICLE_TUNING["pd_ember_glow"]["textureName"] = particle_texture("glow")

#: The six heat wisps over the slab, re-datablocked in r2 -- and this is the one the
#: round chased for two revisions.  The design (section 3.2) asks for "6 x BNGP_24
#: (BNG_steam) at r 150 every 60 deg as **low-alpha** heat wisps over the slab".  The
#: stock set is not low-alpha: at golden hour each one renders as a BLOWN WHITE EGG.
#:
#: Both earlier diagnoses were wrong, and the frames say so.  r1 called the six white
#: pills strung along the S2 ring lens FLARES and zeroed ``flareScale`` on the 24 ember
#: lights; critic r1 called them ``ember_glow`` sprites and the one in S4
#: ``track_lantern_2``'s flare.  r2 zeroed ``track_lantern_2``'s flare AND replaced the
#: glow sprite -- and the eggs stayed, in the same places.  Projected into the r2 frames
#: they are the WISPS: S2 blob centroids x = 320.8 / 960.0 / 1321.9 / 1611.4 against
#: ``hearth_heat_wisp_3 / _2 / _0 / _1`` at x = 310.1 / 960.0 / 1320.6 / 1609.9
#: (1.3-10.7 px), and the S4 egg at (1692.8, 543.5) against ``hearth_heat_wisp_2`` at
#: (1684.4, 567.1).  Six emitters, six eggs, every one attributed.
#:
#: DEVIATION, stated: the six nodes keep the stock node datablock
#: ``lightExampleEmitterNodeData1`` and their position, and swap ``BNGP_24`` for a level
#: pair whose sprite is authored here -- NORMAL blend (steam is not additive), peak
#: colour alpha 0.05 over ~6.7 live sprites, so the wisp is the haze the design asked
#: for instead of a saturated puff.
WISP_EMITTER_PREFIX = f"{LEVEL_ID}_hearth_heat_wisp"
HEAT_WISP_DATABLOCKS: list[dict[str, Any]] = [
    {
        "name": f"{LEVEL_ID}_pd_heat_wisp",
        "class": "ParticleData",
        "file": f"{LEVEL_RELATIVE}/{DATABLOCK_DIR}/{LEVEL_ID}_embers_particle.datablocks.json",
        "textureName": particle_texture("wisp"),
        "lifetimeMS": 4000,
        "lifetimeVarianceMS": 1200,
        "gravityCoefficient": -0.03,
        "dragCoefficient": 0.8,
        "sizes": [2.0, 5.0, 8.0, 9.0],
        "times": [0.0, 0.25, 0.7, 1.0],
        "colors": [
            [0.88, 0.84, 0.78, 0.0],
            [0.90, 0.86, 0.80, 0.05],
            [0.86, 0.81, 0.75, 0.03],
            [0.82, 0.77, 0.71, 0.0],
        ],
        "inheritedVelFactor": 0.0,
        "constantAcceleration": 0.0,
        "spinSpeed": 0.0,
    },
    {
        "name": f"{LEVEL_ID}_pe_heat_wisp",
        "class": "ParticleEmitterData",
        "file": (
            f"{LEVEL_RELATIVE}/{DATABLOCK_DIR}/{LEVEL_ID}_embers_particleemitter.datablocks.json"
        ),
        "particles": f"{LEVEL_ID}_pd_heat_wisp",
        "ejectionPeriodMS": 600,
        "periodVarianceMS": 200,
        "ejectionVelocity": 0.6,
        "velocityVariance": 0.3,
        "ejectionOffset": 0.0,
        "thetaMin": 0,
        "thetaMax": 25,
        "phiReferenceVel": 0,
        "phiVariance": 360,
        "blendStyle": "NORMAL",
        "softnessDistance": 3.0,
        "overrideAdvance": False,
        "orientParticles": False,
    },
]

# --- ember crust (design §3.2) -------------------------------------------------------
CRUST_COUNT = 24
CRUST_R_INNER = 176.0
CRUST_R_OUTER = 199.0
CRUST_SECTOR_DEG = 360.0 / CRUST_COUNT
CRUST_GRID = (20, 24)  # radial x tangential quads -> 960 triangles
CRUST_LUMP_MIN = 0.02
CRUST_LUMP_MAX = 0.35
CRUST_MAP_PX = 2048
CRUST_NITS = 2500
CRUST_EMISSIVE_FACTOR = [1.0, 0.36, 0.08]

# --- decals (design §3.2 hearth keys + §6 pan keys) ----------------------------------
#: ``key -> (rows, size range m, radius range m, datablock renderPriority, family)``.
#: 619 rows, 12 keys, 6 families (QB-21 asks >= 300 rows / >= 3 families).
DECAL_KEYS: dict[str, dict[str, Any]] = {
    "dcl_ember_pile": {
        "rows": 64,
        "size": (3.0, 9.0),
        "r": (176.0, 200.0),
        "prio": 10,
        "family": "ember",
        "cell": 0,
        "material": "ember",
    },
    "dcl_ash_drift": {
        "rows": 96,
        "size": (6.0, 18.0),
        "r": (150.0, 222.0),
        "prio": 8,
        "family": "ash",
        "cell": 1,
        "material": "atlas",
    },
    "dcl_scorch_streak": {
        "rows": 80,
        "size": (8.0, 24.0),
        "r": (113.0, 260.0),
        "prio": 6,
        "family": "scorch",
        "cell": 2,
        "material": "atlas",
        "radial": True,
    },
    "dcl_soot_splash": {
        "rows": 48,
        "size": (4.0, 12.0),
        "r": (113.0, 200.0),
        "prio": 6,
        "family": "soot",
        "cell": 3,
        "material": "atlas",
    },
    "dcl_skid_arc": {
        "rows": 40,
        "size": (6.0, 14.0),
        "r": (118.0, 170.0),
        "prio": 12,
        "family": "skid",
        "cell": 4,
        "material": "atlas",
        "tangential": True,
    },
    "dcl_needle_litter": {
        "rows": 60,
        "size": (4.0, 10.0),
        "r": (0.0, 0.0),
        "prio": 20,
        "family": "litter",
        "cell": 5,
        "material": "atlas",
        "trail": True,
    },
    "dcl_grease_ring": {
        "rows": 24,
        "size": (6.0, 6.0),
        "r": (66.0, 72.0),
        "prio": 30,
        "family": "pan",
        "cell": 6,
        "material": "atlas",
        "tangential": True,
    },
    "dcl_scorch_bloom": {
        "rows": 3,
        "size": (14.0, 14.0),
        "r": (0.0, 0.0),
        "prio": 30,
        "family": "pan",
        "cell": 7,
        "material": "atlas",
        "geysers": True,
    },
    "dcl_tyre_scuff": {
        "rows": 60,
        "size": (3.0, 6.0),
        "r": (10.0, 88.0),
        "prio": 30,
        "family": "pan",
        "cell": 8,
        "material": "atlas",
    },
    "dcl_seasoning_flake": {
        "rows": 80,
        "size": (1.0, 3.0),
        "r": (6.0, 88.0),
        "prio": 30,
        "family": "pan",
        "cell": 9,
        "material": "atlas",
    },
    "dcl_salt_scatter": {
        "rows": 40,
        "size": (1.0, 2.0),
        "r": (40.0, 76.0),
        "prio": 30,
        "family": "pan",
        "cell": 10,
        "material": "atlas",
    },
    "dcl_butter_smear": {
        "rows": 24,
        "size": (2.0, 4.0),
        "r": (30.0, 70.0),
        "prio": 30,
        "family": "pan",
        "cell": 11,
        "material": "atlas",
    },
}
DECAL_ATLAS_PX = 2048
DECAL_ATLAS_GRID = 4  # 4 x 4 cells of 512 px
DECAL_EMBER_PX = 1024
#: The three arena geyser sites (DESIGN.md §4.4; bearings 60 / 180 / 300 at r 44).
GEYSER_SITES = ((60.0, 44.0), (180.0, 44.0), (300.0, 44.0))
#: Where the needle-litter rows sit: along the trail, in the forest.  The trail's
#: node list is B1's ``layout.json decal_roads.trail_surface``; the litter rides the
#: first 60 nodes past the forest edge.
LITTER_TRAIL_KEY = "trail_surface"
LITTER_R_MIN = 360.0

# --- audio forest (design §5.3) ------------------------------------------------------
AUDIO_FOREST_META = {
    "type": "meta",
    "version": 1,
    "mainEvent": "event:>Ambient>Wind>Wind_ConiferousDeciduous_02",
    "roomtoneEnabled": 1,
    "roomtoneEvent": "event:>Ambient>Roomtones>Roomtone_ConiferousDeciduous_02",
    "roomtoneZ": 0,
}


class HearthSpecError(RuntimeError):
    """The hearth spec disagrees with the frozen layout."""


def persistent_id(name: str) -> str:
    """The same uuid5 namespace ``level_writer`` uses, so ids never collide."""

    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"beamng-mcp:{LEVEL_ID}:level:{name}"))


def _r6(value: float) -> float:
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


_LAYOUT: dict[str, Any] | None = None


def layout() -> dict[str, Any]:
    global _LAYOUT
    if _LAYOUT is None:
        if not LAYOUT_PATH.is_file():
            raise HearthSpecError(f"missing the frozen design layout at {LAYOUT_PATH}")
        _LAYOUT = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    return _LAYOUT


def bearing_point(bearing_deg: float, r: float) -> tuple[float, float]:
    """Compass convention: 0 = +Y, 90 = +X (design §1)."""

    theta = math.radians(bearing_deg)
    return C[0] + r * math.sin(theta), C[1] + r * math.cos(theta)


def polar(x: float, y: float) -> tuple[float, float]:
    dx, dy = x - C[0], y - C[1]
    return math.hypot(dx, dy), math.degrees(math.atan2(dx, dy)) % 360.0


# --- names ---------------------------------------------------------------------------
def stone_stem(asset: str) -> str:
    return f"{LEVEL_ID}_h_{asset}"


def stone_material(asset: str) -> str:
    return f"{LEVEL_ID}_rock_hero_{asset}"


def crust_stem() -> str:
    return f"{LEVEL_ID}_h_ember_crust"


def crust_material() -> str:
    return f"{LEVEL_ID}_ember_crust"


def decal_material(kind: str) -> str:
    return f"{LEVEL_ID}_dcl_{kind}"


def decal_datablock(key: str) -> str:
    return f"{LEVEL_ID}_{key}"


def object_name(base: str) -> str:
    return f"{LEVEL_ID}_{base}"


def shape_path(file_name: str) -> str:
    return f"/{LEVEL_RELATIVE}/{SHAPE_DIR}/{file_name}"


def texture_path(directory: str, file_name: str) -> str:
    return f"/{LEVEL_RELATIVE}/{directory}/{file_name}"


# --- rotation ------------------------------------------------------------------------
def yaw_matrix(yaw_deg: float) -> list[float]:
    """rotationMatrix ROWS are the local axes (AGENTS.md arena law).

    A compass yaw of ``psi`` turns the shape's local +Y toward that bearing, so the
    rows are (cos, -sin, 0) / (sin, cos, 0) / (0, 0, 1) with ``psi`` measured
    clockwise from +Y -- i.e. the standard Z rotation by ``-psi`` in maths
    convention.  Written out rather than composed so the sign is inspectable.
    """

    psi = math.radians(yaw_deg)
    c, s = math.cos(psi), math.sin(psi)
    return [_r6(c), _r6(-s), 0.0, _r6(s), _r6(c), 0.0, 0.0, 0.0, 1.0]


IDENTITY = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]


# --- stones --------------------------------------------------------------------------
def stones() -> list[dict[str, Any]]:
    """The 28 stone rows of ``layout.json`` with the scale each source needs."""

    rows = []
    for stone in layout()["stones"]:
        source = STONE_SOURCES[stone["asset"]]
        # blender_hearth exports every stone source at 1 m longest axis, so the
        # TSStatic scale IS the design's footprint diameter.  One number, one place.
        scale = float(stone["diam"])
        rows.append(
            {
                **stone,
                "scale": scale,
                "map_px": source["map_px"],
                "shape": f"{stone_stem(stone['asset'])}.dae",
                "material": stone_material(stone["asset"]),
                "object": object_name(stone["name"]),
            }
        )
    if len(rows) != 28:
        raise HearthSpecError(f"expected 28 stones, layout has {len(rows)}")
    return rows


def stone_height_scale(asset: str) -> float:
    """Vertical scale so the design's height/diameter ratio is honoured.

    ``blender_hearth`` normalises every source to a 1 m longest HORIZONTAL axis and
    records the resulting height; the TSStatic ships a uniform ``scale`` (BeamNG's
    TSStatic scale is a 3-vector but a non-uniform one breaks the Colmesh's convex
    hull for the physics), so the design's height column is a CHECK, not a control.
    """

    return 1.0


# --- ember crust ---------------------------------------------------------------------
CRUST_R_MID = (CRUST_R_INNER + CRUST_R_OUTER) / 2.0

#: **One crust tile, in metres, on each axis.**
#:
#: ``u`` is the radius and runs from :data:`CRUST_R_INNER` to :data:`CRUST_R_OUTER`
#: exactly once (``blender_hearth.CRUST_RADIAL_TILES = 1``), so a tile is 23.000 m
#: radially.  ``v`` is tangential and tiles :data:`CRUST_TANGENTIAL_TILES` times across
#: a 15 degree sector's arc at the mid radius, so a tile is 24.544 m the other way.
#:
#: These live here because :mod:`hearth_textures` sizes its lumps in METRES against the
#: design's 0.3-1.2 m band and r3 published the band on the SHORT axis only: its 18-cell
#: layer is 1.278 m on the long axis and it was reported as "inside the design's
#: 0.3-1.2 m band" (critic r3, D8).  ``test_the_crust_lumps_are_inside_the_design_band``
#: now checks the long axis, and ``test_the_crust_tile_metres_agree_with_the_exporter``
#: keeps this copy of the tile count honest against ``blender_hearth``'s.
CRUST_TANGENTIAL_TILES = 2.0
CRUST_TILE_U_M = CRUST_R_OUTER - CRUST_R_INNER
CRUST_TILE_V_M = math.radians(CRUST_SECTOR_DEG) * CRUST_R_MID / CRUST_TANGENTIAL_TILES


def crust_plates() -> list[dict[str, Any]]:
    """24 sector plates, one DAE instanced with 24 yaws (design §3.2).

    The mesh is authored about its OWN sector centroid (bearing 0, r 187.5), not
    about C: a plate whose origin sat at C would carry a 199 m bounding sphere, so
    the engine could never cull it and its detail selection would be meaningless.
    Instance *i* therefore sits at ``bearing_point(i * 15, 187.5)`` and carries the
    same yaw -- which reproduces the ring exactly because rotating the local frame
    about the instance origin and moving that origin around C is the same rigid
    motion as rotating the whole plate about C.
    """

    rows = []
    for index in range(CRUST_COUNT):
        yaw = index * CRUST_SECTOR_DEG
        x, y = bearing_point(yaw, CRUST_R_MID)
        rows.append(
            {
                "name": f"ember_crust_{index:02d}",
                "object": object_name(f"ember_crust_{index:02d}"),
                "yaw": yaw,
                "position": [_r6(x), _r6(y), C[2]],
                "rotationMatrix": yaw_matrix(yaw),
            }
        )
    return rows


# --- particle / sfx datablocks -------------------------------------------------------
def particle_datablock_files() -> dict[str, dict[str, Any]]:
    """The five records of ``layout.json particle_datablocks``, split by file.

    The particle file must sort BEFORE the emitter file (server.lua walks the level
    directory in sorted order and an emitter whose ``particles`` is not registered
    yet is refused): ``…_embers_particle.datablocks.json`` <
    ``…_embers_particleemitter.datablocks.json``.
    """

    files: dict[str, dict[str, Any]] = {}
    for record in [*layout()["particle_datablocks"], *HEAT_WISP_DATABLOCKS]:
        relative = str(record["file"]).removeprefix(f"{LEVEL_RELATIVE}/")
        payload = {k: v for k, v in record.items() if k not in {"file", "note", "b0"}}
        # r2: PARTICLE_TUNING overrides the freeze on the three keys the FRAMES forced
        # (see its comment).  Keyed by the un-namespaced suffix so the table reads like
        # the design's own names.
        suffix = str(record["name"]).removeprefix(f"{LEVEL_ID}_")
        payload.update(PARTICLE_TUNING.get(suffix, {}))
        payload["persistentId"] = persistent_id(f"datablock:{record['name']}")
        files.setdefault(relative, {})[str(record["name"])] = payload
    return files


def particle_tuning_deviations() -> list[dict[str, Any]]:
    """Every field r2 changed against the frozen layout, with both values.

    A deviation nobody can diff is a deviation nobody can audit, so the report and the
    evidence both read this rather than a prose list.
    """

    rows: list[dict[str, Any]] = []
    for record in layout()["particle_datablocks"]:
        suffix = str(record["name"]).removeprefix(f"{LEVEL_ID}_")
        for field, value in PARTICLE_TUNING.get(suffix, {}).items():
            rows.append(
                {
                    "datablock": str(record["name"]),
                    "field": field,
                    "frozen": record.get(field),
                    "shipped": value,
                }
            )
    return rows


def sfx_datablock_file() -> tuple[str, dict[str, Any]]:
    """The two level ``SFXProfile``s (B0's measured looping form)."""

    document: dict[str, Any] = {}
    relative = ""
    for record in layout()["sfx_profiles"]:
        relative = str(record["file"]).removeprefix(f"{LEVEL_RELATIVE}/")
        payload = {k: v for k, v in record.items() if k not in {"file", "note", "b0"}}
        payload["persistentId"] = persistent_id(f"datablock:{record['name']}")
        document[str(record["name"])] = payload
    if not relative:
        raise HearthSpecError("layout.json carries no sfx_profiles")
    return relative, document


def decal_datablock_file() -> tuple[str, dict[str, Any]]:
    """One ``DecalData`` per key, on the shared atlas cell it draws.

    ``DecalData`` is registered by the same ``*.datablocks.json`` branch B0 proved
    for ``ParticleData`` and ``SFXProfile`` (server.lua L200-223 hands every
    ``*datablocks.json`` member to ``loadJsonMaterialsFile``, which dispatches on the
    record's ``class``); the namespaced path is what keeps the names ours.
    """

    document: dict[str, Any] = {}
    for key, spec in DECAL_KEYS.items():
        name = decal_datablock(key)
        cell = int(spec["cell"])
        row, column = divmod(cell, DECAL_ATLAS_GRID)
        step = 1.0 / DECAL_ATLAS_GRID
        if spec["material"] == "ember":
            coords = [[0.0, 0.0, 1.0, 1.0]]
        else:
            coords = [[_r6(column * step), _r6(row * step), _r6(step), _r6(step)]]
        document[name] = {
            "name": name,
            "class": "DecalData",
            "persistentId": persistent_id(f"datablock:{name}"),
            "material": decal_material(spec["material"]),
            "size": float(spec["size"][1]),
            "renderPriority": int(spec["prio"]),
            "fadeStartPixelSize": 60,
            "fadeEndPixelSize": 70,
            "randomize": False,
            "frame": 0,
            "texCols": DECAL_ATLAS_GRID,
            "texRows": DECAL_ATLAS_GRID,
            "textureCoordCount": 0,
            "textureCoords": coords,
        }
    return f"{DATABLOCK_DIR}/{LEVEL_ID}_decals.datablocks.json", document


# --- materials -----------------------------------------------------------------------
def _stage_paths(directory: str, stem: str, roles: dict[str, str]) -> dict[str, Any]:
    return {slot: texture_path(directory, f"{stem}_{suffix}.png") for slot, suffix in roles.items()}


ROCK_ROLES = {
    "baseColorMap": "b.color",
    "normalMap": "nm.normal",
    "roughnessMap": "r.data",
    "ambientOcclusionMap": "ao.data",
}


def rock_materials_document() -> dict[str, Any]:
    document: dict[str, Any] = {}
    for asset in STONE_SOURCES:
        name = stone_material(asset)
        stage = _stage_paths(SHAPE_DIR, name, ROCK_ROLES)
        # the soot bake lives in the mesh's COLOR channel; stock italy_rocksface is
        # the same recipe (v1.5, PBR slots, vertColor inside Stages[0]).
        stage["vertColor"] = True
        document[name] = {
            "name": name,
            "mapTo": name,
            "class": "Material",
            "persistentId": persistent_id(f"material:{name}"),
            "Stages": [stage, {}, {}, {}],
            "annotation": "ROCK",
            "groundType": "ROCK",
            "castShadows": True,
            "materialTag0": "beamng",
            "materialTag1": "Natural",
            "useAnisotropic": True,
            "version": 1.5,
        }
    name = crust_material()
    stage = _stage_paths(
        SHAPE_DIR,
        name,
        {
            "baseColorMap": "b.color",
            "normalMap": "nm.normal",
            "roughnessMap": "r.data",
        },
    )
    stage["emissiveMap"] = texture_path(SHAPE_DIR, f"{name}_e.color.png")
    document[name] = {
        "name": name,
        "mapTo": name,
        "class": "Material",
        "persistentId": persistent_id(f"material:{name}"),
        "Stages": [stage, {}, {}, {}],
        # r2 (critic r1 D10): the two DECAL materials keep ASPHALT because they lie on
        # the hearth slab and the design calls that slab ASPHALT.  The crust PLATE is a
        # bed of coal, so the semantic camera should not label it road: ROCK, the same
        # annotation the six stones carry and the only one this level has proven live.
        "annotation": "ROCK",
        "castShadows": False,
        "emissive": True,
        "emissiveFactor": list(CRUST_EMISSIVE_FACTOR),
        "emissiveIntensityNits": CRUST_NITS,
        "materialTag0": "beamng",
        "materialTag1": "Natural",
        "version": 1.5,
    }
    return document


def decal_materials_document() -> dict[str, Any]:
    atlas = decal_material("atlas")
    ember = decal_material("ember")
    document = {
        atlas: {
            "name": atlas,
            "mapTo": "unmapped_mat",
            "class": "Material",
            "persistentId": persistent_id(f"material:{atlas}"),
            "Stages": [
                {
                    **_stage_paths(
                        DECAL_DIR,
                        f"{LEVEL_ID}_t_dcl_atlas",
                        {
                            "baseColorMap": "b.color",
                            "normalMap": "nm.normal",
                            "roughnessMap": "r.data",
                            "opacityMap": "o.data",
                        },
                    ),
                    "opacityFactor": 0.92,
                },
                {},
                {},
                {},
            ],
            "annotation": "ASPHALT",
            "castShadows": False,
            "materialTag0": "beamng",
            "materialTag1": "decal",
            "translucent": True,
            "translucentZWrite": True,
            "version": 1.5,
        },
        ember: {
            "name": ember,
            "mapTo": "unmapped_mat",
            "class": "Material",
            "persistentId": persistent_id(f"material:{ember}"),
            "Stages": [
                {
                    **_stage_paths(
                        DECAL_DIR,
                        f"{LEVEL_ID}_t_dcl_ember",
                        {
                            "baseColorMap": "b.color",
                            "normalMap": "nm.normal",
                            "roughnessMap": "r.data",
                            "opacityMap": "o.data",
                        },
                    ),
                    "emissiveMap": texture_path(DECAL_DIR, f"{LEVEL_ID}_t_dcl_ember_e.color.png"),
                    "opacityFactor": 1.0,
                },
                {},
                {},
                {},
            ],
            "annotation": "ASPHALT",
            "castShadows": False,
            "emissive": True,
            "emissiveFactor": list(CRUST_EMISSIVE_FACTOR),
            "emissiveIntensityNits": CRUST_NITS,
            "materialTag0": "beamng",
            "materialTag1": "decal",
            "translucent": True,
            "translucentZWrite": True,
            "version": 1.5,
        },
    }
    return document


# --- scene records -------------------------------------------------------------------
def _record(class_name: str, name: str, parent: str, **fields: Any) -> dict[str, Any]:
    record = {
        "name": name,
        "class": class_name,
        "persistentId": persistent_id(name),
        "__parent": parent,
    }
    record.update(fields)
    return record


def stone_records() -> list[dict[str, Any]]:
    """28 TSStatics on the ``Colmesh_<stem>-1`` collider (design §3.1).

    ``collisionType "Collision Mesh"`` so the Colmesh node is what the wheels meet
    (report_B P3b); ``prebuildCollisionData`` is authored as the string every stock
    record uses for it.
    """

    records = []
    for stone in stones():
        scale = float(stone["scale"])
        records.append(
            _record(
                "TSStatic",
                stone["object"],
                GROUP_HEARTH,
                shapeName=shape_path(stone["shape"]),
                position=[_r6(stone["x"]), _r6(stone["y"]), _r6(stone["z"])],
                rotationMatrix=yaw_matrix(float(stone["yaw"])),
                scale=[scale, scale, scale],
                collisionType="Collision Mesh",
                decalType="Collision Mesh",
                prebuildCollisionData="1",
                useInstanceRenderData=True,
                castShadows=True,
            )
        )
    return records


def crust_records() -> list[dict[str, Any]]:
    """24 ember-crust sector plates: light only, no collision (design §3.2)."""

    records = []
    for plate in crust_plates():
        records.append(
            _record(
                "TSStatic",
                plate["object"],
                GROUP_HEARTH,
                shapeName=shape_path(f"{crust_stem()}.dae"),
                position=[_r6(v) for v in plate["position"]],
                rotationMatrix=plate["rotationMatrix"],
                scale=[1.0, 1.0, 1.0],
                collisionType="None",
                decalType="None",
                castShadows=False,
                useInstanceRenderData=True,
            )
        )
    return records


#: Design amendment A2 (2026-09-15, the user's call; ``authoring/design_amendments.md``):
#: the two kindling logs, the enamel pot, the lantern tripod and the lantern that hung from
#: it came OFF the map (``place_props.py``).  The frozen layout is never edited, so the
#: hearth objects that only existed for those props are FILTERED here at render time: the
#: fire + smoke emitter pair at each of the four log ends, the four kindling fire lights,
#: and the lantern's point and spot lights.  34 -> 26 emitter nodes, 36 -> 30 lights.
REMOVED_WITH_THE_PROPS = frozenset(
    {
        *(
            f"kindling_log_{log}_{end}_{kind}"
            for log in ("north", "south")
            for end in ("e", "w")
            for kind in ("fire", "smoke", "light")
        ),
        "lantern_point",
        "lantern_spot",
        # 2026-09-16, the user's second message: the four lantern posts came off the map,
        # and with them the track lanterns B2 hung on them.
        *(f"track_lantern_{i}" for i in range(4)),
    }
)


def removed_with_the_props(name: str) -> bool:
    """True for a layout object that only existed for a prop removed on 2026-09-15."""

    return name.removeprefix(f"{LEVEL_ID}_") in REMOVED_WITH_THE_PROPS


def emitter_records() -> list[dict[str, Any]]:
    """26 ``ParticleEmitterNode``s: the design's 34 (§3.2; ``layout.json emitters``) less
    the eight log-end fire/smoke nodes removed with the kindling logs (amendment A2).

    Never ``EmberEmitter`` / ``EmberNode``: B0 measured them MISSING and the record
    shape that names them logs ``GameBase::setDataBlockProperty - Can't unset
    datablock`` once per boot.  Twelve spark nodes and eight glow nodes name the
    level triple; the fire / smoke / steam nodes name stock BNGP sets on the stock
    ``lightExampleEmitterNodeData1``.
    """

    records = []
    for emitter in layout()["emitters"]:
        if removed_with_the_props(object_name(str(emitter["name"]))):
            continue  # A2: the log-end fire/smoke pairs went with the kindling logs
        name = str(emitter["emitter"])
        if name.startswith("Ember"):
            raise HearthSpecError(f"{emitter['name']} names the missing core datablock {name}")
        if object_name(str(emitter["name"])).startswith(WISP_EMITTER_PREFIX):
            name = f"{LEVEL_ID}_pe_heat_wisp"  # r2: see HEAT_WISP_DATABLOCKS
        records.append(
            _record(
                "ParticleEmitterNode",
                object_name(str(emitter["name"])),
                GROUP_HEARTH,
                dataBlock=str(emitter["dataBlock"]),
                emitter=name,
                active=bool(emitter["active"]),
                position=[_r6(emitter["x"]), _r6(emitter["y"]), _r6(emitter["z"])],
                rotationMatrix=list(IDENTITY),
                scale=[float(v) for v in emitter["scale"]],
            )
        )
    if len(records) != 26:
        raise HearthSpecError(f"expected 26 emitter nodes (34 less A2's 8), got {len(records)}")
    return records


#: Lights whose lens-flare sprite is suppressed, and why each one is on the list.
#: DEVIATION from §3.3, and the frames are the reason: the design gives every night
#: light ``flareType "vehicleReverseLightFlare"`` at scale 0.3-1.5 (JV's stock choice
#: for STREET LAMPS), and the night window opens at 0.29 -- so at the load clock 0.30,
#: a GOLDEN-HOUR frame, all 36 flares draw.
#:
#: r1 zeroed the 24 ember lights (24 white pills in a ring across S2, kept as
#: ``b2/preview/S2_before_flare_fix.png``): coals do not have a lens flare.
#: r2 zeroes the four track lanterns as well.  The critic projected the blown white
#: egg in the middle-right of ``S4_driver_ash_band`` -- centroid (1702.9, 544.3), bbox
#: x 1676-1725 / y 515-567 -- and ``track_lantern_2`` lands INSIDE it at (1718.6,
#: 551.6), 255.7 m out; the next candidate is 104 px away.  A 4,000-intensity lamp
#: with an 18 m radius does not throw a 50 px flare at 255 m, and there is no lamp
#: post there at all until B4 builds one.  The rule this leaves is a rule, not a
#: taste: **a flare needs a source the camera can see.**
FLARELESS_LIGHT_PREFIXES = (
    f"{LEVEL_ID}_ember_light_",
    f"{LEVEL_ID}_track_lantern_",
)

#: The ember-bed re-light.  **r4 rebuilds its geometry, because r3's moved the metric
#: the wrong way and said the opposite.**
#:
#: r3 claimed the re-light was "the direct answer to ``lit_fraction 1.0, longest dark
#: run 0.0 deg``".  Critic r3 re-ran B2's own ``b2/s6_glow_band.py`` on B2's own
#: certified r3 frame and got ``lit_fraction 1.0, longest_dark_run_deg 0.0`` -- IDENTICAL
#: -- with the band 25 % MORE even on four independent statistics (CV 0.609 -> 0.453,
#: p90/p10 5.51 -> 3.64, 15 degree window max/min 3.25 -> 3.03, fraction above luma 60
#: 0.72 -> 0.95).  The mechanism is arithmetic: r3 grew every pool from the design's
#: 34 m to 54-66 m while the lights stayed **49.077 m** apart, so each point of the ring
#: sat inside three or four overlapping pools and the 2.6x intensity spread could not
#: show.  r3's own claim is withdrawn in r4's report.
#:
#: Two things also have to stay true, and they are what makes this a geometry problem
#: rather than an intensity one:
#:
#: * design section 8's S6 rule is "**the ring reads as a continuous glow band**".  A
#:   dark gap is a FAIL, not the fix.  What was wrong is that the band had no structure,
#:   not that it was continuous.
#: * critic r3's best finding about r3 was that the stones ARE lit now -- "the boulder
#:   goes from dim and flat to clearly lit warm on its lower face ... I would ship the
#:   night bed".  The nearest stone face is **23.61 m** from an ember light (critic r3
#:   D2 measured it; r3's report said 28.9 m and that does not reproduce), so whatever
#:   lights it has to reach 23.6 m with something left.
#:
#: So r4 changes the POOL PITCH instead of the pool size, which is the one lever that
#: moves the band without touching either constraint:
#:
#: * KEY (even index, 12 lights, **30 degree** centres): radius **48**, intensity
#:   **30,000**, castShadows kept.  These are the pools.  The KEY-to-KEY chord is
#:   98.15 m, so a point midway between two KEYs is **49.08 m** from each -- outside a
#:   48 m radius entirely.  Under r3 that same point sat inside four overlapping pools.
#: * FILL (odd index, 12 lights, sitting on those troughs): radius **38**, intensity
#:   **4,200**, castShadows off.  Small and dim on purpose: it lifts the trough enough
#:   to keep the band continuous and to wrap the near bed, and not enough to fill it in.
#:   38 m is not a taste number either -- it is the smallest radius that still reaches
#:   the four chock stones whose nearest FILL is 37.04 m away.
#:
#: What the model says, all three tables through :func:`ember_ring_profile`
#: (``b2/r4/ring_profile.json``); the design's own row and r2's are the same table:
#:
#: =====================  ==========  ======  ======
#: ..                     design/r2   r3      r4
#: =====================  ==========  ======  ======
#: coefficient of var.    2.762       2.760   3.458
#: KEY bins / FILL bins   0.92        1.48    6.58
#: harmonic 12 / 24       0.046       0.204   0.778
#: trough is zero         no          no      no
#: bed-mean irradiance    58.6        84.3    82.2
#: giant-stone irradiance 8.3         35.3    26.6
#: =====================  ==========  ======  ======
#:
#: So r4 buys a 30 degree pool pitch (harmonic 12 is now four fifths of harmonic 24's
#: amplitude, against r3's one fifth), keeps the ring's overall brightness, keeps 75 %
#: of r3's light on the stones -- the thing critic r3 said it would ship -- and keeps
#: the band continuous, which is what design section 8 actually asks for.  The model
#: also reproduces the finding that blocked r3: r3's table has the same coefficient of
#: variation as the design's, i.e. its re-light bought no modulation at all.
#:
#: Neither radius carries the per-light variance any more (r3's did, which is why four
#: of its published bands did not reproduce -- critic r3 D1); the variance moves
#: intensity only, so the geometry is exact and the deviation table IS the shipped value.
EMBER_KEY = {"radius": 48.0, "intensity": 30000.0, "castShadows": True}
EMBER_FILL = {"radius": 38.0, "intensity": 4200.0, "castShadows": False}
EMBER_VARIANCE = (0.72, 0.56)
#: The ember ring's own geometry, read from the design's frozen light table rather than
#: assumed: 24 lights at r 188 on 15 degree centres is a 49.077 m nearest-neighbour
#: chord (critic r3 verified both numbers).
EMBER_RING_R = 188.0
EMBER_RING_STEP_DEG = 15.0


def ember_variance(name: str) -> float:
    """A stable per-light multiplier in [0.72, 1.28], from the light's own name."""

    digest = hashlib.sha256(f"{TEXTURE_SEED}:ember:{name}".encode()).digest()
    unit = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return round(EMBER_VARIANCE[0] + EMBER_VARIANCE[1] * unit, 6)


def ember_tuning(name: str, index: int) -> dict[str, Any]:
    """The override table for one ember light (see :data:`EMBER_KEY`).

    The radius is the role's value EXACTLY.  r3 scaled it by ``0.88 + 0.12 * variance``
    and then published theoretical band ends beside realised ones, which is why critic
    r3 D1 could not reproduce four of the six numbers in r3's own table.  Intensity is
    the only thing the per-light hash moves now.
    """

    base = EMBER_KEY if index % 2 == 0 else EMBER_FILL
    var = ember_variance(name)
    return {
        "radius": float(base["radius"]),
        "intensity": _r6(float(base["intensity"]) * var),
        "castShadows": bool(base["castShadows"]),
        "role": "key" if index % 2 == 0 else "fill",
        "variance": var,
    }


def ember_ring_profile(samples: int = 720) -> dict[str, Any]:
    """The ring's predicted irradiance against bearing, from the SHIPPED light records.

    This is the instrument r3 did not have: it answers "is the band modulated" from the
    records alone, before a frame exists, so a change to the light table can never again
    be claimed to have done something the frame contradicts.  ``b2/s6_glow_band.py``
    then measures the same thing from the frame's own pixels and the two are published
    side by side.

    The falloff is Torque's point-light form -- inverse square with a smooth window that
    reaches zero at ``radius`` -- and it is integrated ACROSS THE BED at each bearing
    (the crust annulus r 176-199, cosine-weighted against a surface 1.2 m below the
    lights) rather than sampled on the ring line.  Sampling the line puts a 1/d
    singularity under every lamp and measures nothing a viewer at 470 m can see; the
    annulus mean is what one column of the S6 band actually shows.

    What is used is the SHAPE, never the absolute value:

    * ``key_over_fill`` -- the alternation the 30 degree KEY pitch buys.
    * ``harmonic_12_over_24`` -- a one-line DFT.  A ring of 24 identical lights can only
      modulate at harmonic 24 (every 15 degrees); a KEY/FILL ring modulates at harmonic
      12 (every 30 degrees).  This ratio is the pool pitch, as a number.
    * ``trough_over_mean`` and ``minimum_is_zero`` -- design section 8's S6 rule is
      "the ring reads as a **continuous** glow band", so a zero here is a FAIL, not a
      success.  r3's mistake was to call continuity the defect.
    """

    lights = [
        record
        for record in light_records()
        if record["name"].startswith(f"{LEVEL_ID}_ember_light_")
    ]
    positions = [
        (
            float(r["position"][0]),
            float(r["position"][1]),
            float(r["radius"]),
            float(r["intensity"]),
        )
        for r in lights
    ]
    height = 1.2  # the design's ember lights sit terrain + 1.2, the bed is the terrain
    radii = [CRUST_R_INNER + (CRUST_R_OUTER - CRUST_R_INNER) * (i + 0.5) / 12 for i in range(12)]
    values = []
    for step in range(samples):
        bearing = 360.0 * step / samples
        total = 0.0
        for r in radii:
            px, py = bearing_point(bearing, r)
            for lx, ly, radius, intensity in positions:
                flat = math.hypot(px - lx, py - ly)
                distance = math.hypot(flat, height)
                if distance >= radius:
                    continue
                window = (1.0 - (distance / radius) ** 2) ** 2
                # cosine against an up-facing surface: height / distance
                total += intensity * window * height / distance**3
        values.append(total / len(radii))
    mean = sum(values) / len(values)
    peak, trough = max(values), min(values)
    # A point light directly over the bed is a near-singularity: the raw peak is one
    # sample a metre from a lamp, which nothing at 470 m resolves.  The robust pair is
    # p90/p10 -- the same statistic ``b2/s6_glow_band.py`` reads off the frame, so the
    # model and the frame are directly comparable.
    ordered = sorted(values)
    p10 = ordered[int(0.10 * (len(ordered) - 1))]
    p90 = ordered[int(0.90 * (len(ordered) - 1))]
    # KEY lights sit at bearings 7.5 + 30k, FILL at 22.5 + 30k
    key_bins = [v for i, v in enumerate(values) if abs(((360.0 * i / samples) - 7.5) % 30.0) < 3.0]
    fill_bins = [
        v for i, v in enumerate(values) if abs(((360.0 * i / samples) - 22.5) % 30.0) < 3.0
    ]
    harmonics = {}
    for order in (12, 24):
        real = sum(v * math.cos(2 * math.pi * order * i / samples) for i, v in enumerate(values))
        imag = sum(v * math.sin(2 * math.pi * order * i / samples) for i, v in enumerate(values))
        harmonics[order] = math.hypot(real, imag) * 2.0 / samples
    return {
        "samples": samples,
        "ring_r": EMBER_RING_R,
        "lights": len(lights),
        "method": (
            "inverse-square with a (1-(d/radius)^2)^2 window, cosine-weighted, integrated "
            "over the crust annulus r 176-199 at each of 720 bearings"
        ),
        "nearest_neighbour_chord_m": _r6(
            2.0 * EMBER_RING_R * math.sin(math.radians(EMBER_RING_STEP_DEG) / 2.0)
        ),
        "peak": _r6(peak),
        "trough": _r6(trough),
        "mean": _r6(mean),
        "peak_over_trough": _r6(peak / trough) if trough else None,
        "trough_over_mean": _r6(trough / mean),
        "p90_over_p10": _r6(p90 / p10) if p10 else None,
        "coefficient_of_variation": _r6(
            (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5 / mean
        ),
        "key_bin_mean": _r6(sum(key_bins) / len(key_bins)),
        "fill_bin_mean": _r6(sum(fill_bins) / len(fill_bins)),
        "key_over_fill": _r6((sum(key_bins) / len(key_bins)) / (sum(fill_bins) / len(fill_bins))),
        "harmonic_12_amplitude": _r6(harmonics[12] / mean),
        "harmonic_24_amplitude": _r6(harmonics[24] / mean),
        "harmonic_12_over_24": _r6(harmonics[12] / harmonics[24]) if harmonics[24] else None,
        "minimum_is_zero": trough <= 0.0,
    }


def ember_light_deviations() -> list[dict[str, Any]]:
    """Every ember light's frozen value beside its r3 value -- auditable, not prose."""

    rows = []
    index = 0
    for light in layout()["night_lights"]:
        name = object_name(str(light["name"]))
        if not name.startswith(f"{LEVEL_ID}_ember_light_"):
            continue
        tuned = ember_tuning(name, index)
        rows.append(
            {
                "name": name.removeprefix(f"{LEVEL_ID}_"),
                "role": tuned["role"],
                "radius": [float(light["radius"]), tuned["radius"]],
                "intensity": [float(light["intensity"]), tuned["intensity"]],
                "castShadows": [bool(light["castShadows"]), tuned["castShadows"]],
            }
        )
        index += 1
    return rows


def _is_ember_light(name: str) -> bool:
    """Does this light lose its flare sprite?  (See ``FLARELESS_LIGHT_PREFIXES``.)"""

    return name.startswith(FLARELESS_LIGHT_PREFIXES)


def flare_census() -> dict[str, Any]:
    """Which lights still draw a flare, and at what scale -- counted, never asserted.

    r1's report said "10 flares remain"; the records said 12.  This function is the
    number now, and the report quotes it.
    """

    kept, dropped = [], []
    for record in light_records():
        row = {"name": record["name"], "flareScale": record["flareScale"]}
        (kept if record["flareScale"] > 0.0 else dropped).append(row)
    return {
        "lights": len(kept) + len(dropped),
        "with_flare": len(kept),
        "flareless": len(dropped),
        "kept": sorted(kept, key=lambda r: r["name"]),
        "kept_names": sorted(r["name"].removeprefix(f"{LEVEL_ID}_") for r in kept),
    }


def light_records() -> list[dict[str, Any]]:
    """36 night lights (design §3.3).

    ``nightLight`` is a STRING ("1"); ``isEnabled false`` because
    ``environment.lua`` is what turns them on inside the window LevelInfo's
    ``nightLightsNightStart`` / ``nightLightsNightEnd`` strings name (B1 authors
    those on the LevelInfo; B2 gates them live).
    """

    records = []
    ember_index = 0
    for light in layout()["night_lights"]:
        name = object_name(str(light["name"]))
        if removed_with_the_props(name):
            continue  # A2: four kindling fire lights and the lantern's two lights
        tuned: dict[str, Any] = {}
        if _is_ember_light(name) and name.startswith(f"{LEVEL_ID}_ember_light_"):
            tuned = ember_tuning(name, ember_index)
            ember_index += 1
        common: dict[str, Any] = {
            "position": [_r6(light["x"]), _r6(light["y"]), _r6(light["z"])],
            "color": [*[float(v) for v in light["color"]], 1.0],
            "brightness": 1.0 if float(light["intensity"]) >= 12000 else 0.7,
            "intensity": float(tuned.get("intensity", light["intensity"])),
            "castShadows": bool(tuned.get("castShadows", light["castShadows"])),
            "texSize": int(light["texSize"]),
            "nightLight": "1",
            "isEnabled": False,
            "attenuationRatio": [1.0, 0.0, 0.0],
            "flareType": str(light["flareType"]),
            "flareScale": float(light["flareScale"]) if not _is_ember_light(name) else 0.0,
        }
        if str(light["class"]) == "SpotLight":
            # a SpotLight shines along its LOCAL +Y = ROW 1 of rotationMatrix: stock
            # WCUSA garage lights and SpotLight_107 aim down with row 1 = (0, 0, -1).
            records.append(
                _record(
                    "SpotLight",
                    name,
                    GROUP_NIGHT,
                    **common,
                    range=float(light["range"]),
                    innerAngle=float(light["innerAngle"]),
                    outerAngle=float(light["outerAngle"]),
                    rotationMatrix=[1.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 1.0, 0.0],
                )
            )
        else:
            records.append(
                _record(
                    "PointLight",
                    name,
                    GROUP_NIGHT,
                    **common,
                    radius=float(tuned.get("radius", light["radius"])),
                )
            )
    if len(records) != 26:
        raise HearthSpecError(f"expected 26 lights (36 less A2's 10), got {len(records)}")
    return records


def audio_records() -> list[dict[str, Any]]:
    """18 SFXEmitters + 13 SFXSpaces (design §5.3).

    Every fire emitter names a LEVEL ``SFXProfile`` whose description is
    ``AudioDefaultLoop3D``: B0 measured the stock ``FireLoopSound1/2`` as one-shot
    (``AudioDefault3D``), so naming them would ship eight silent fires.  The object's
    ``maxDistance`` reads ``referenceDistance + 0.01`` whatever is authored -- the
    authored pair is kept because it is what the design specifies and what a human
    editor reads, and the gate asserts the READ value, not the authored one.
    """

    records = []
    for emitter in layout()["sfx_emitters"]:
        track = str(emitter["track"])
        if track in {"FireLoopSound1", "FireLoopSound2"}:
            raise HearthSpecError(f"{emitter['name']} names the one-shot stock profile {track}")
        records.append(
            _record(
                "SFXEmitter",
                object_name(str(emitter["name"])),
                GROUP_AUDIO,
                track=track,
                position=[_r6(emitter["x"]), _r6(emitter["y"]), _r6(emitter["z"])],
                rotationMatrix=list(IDENTITY),
                scale=[1.0, 1.0, 1.0],
                is3D=bool(emitter["is3D"]),
                isLooping=bool(emitter["isLooping"]),
                playOnAdd=bool(emitter["playOnAdd"]),
                referenceDistance=float(emitter["referenceDistance"]),
                maxDistance=float(emitter["maxDistance"]),
                volume=float(emitter["volume"]),
            )
        )
    for space in layout()["sfx_spaces"]:
        records.append(
            _record(
                "SFXSpace",
                object_name(str(space["name"])),
                GROUP_AUDIO,
                position=[_r6(v) for v in space["centre"]],
                rotationMatrix=list(IDENTITY),
                scale=[float(v) for v in space["scale"]],
                soundAmbience=str(space["soundAmbience"]),
            )
        )
    if len(records) != 31:
        raise HearthSpecError(f"expected 18 emitters + 13 spaces, got {len(records)}")
    return records


def group_records() -> list[dict[str, Any]]:
    """The three ``SimGroup`` rows B2 adds to ``main/MissionGroup/items.level.json``.

    JV carries both ``night_light`` and ``Audio`` as top-level groups; ``hearth`` is
    ours.  ``place_hearth`` MERGES these into B1's rendered listing rather than
    rewriting it, and the report hands B1/B6 the three-line patch for
    ``level_writer.mission_group_records()``.
    """

    return [
        {
            "name": group,
            "class": "SimGroup",
            "persistentId": persistent_id(f"group:{group}"),
            "__parent": "MissionGroup",
        }
        for group in (GROUP_HEARTH, GROUP_NIGHT, GROUP_AUDIO)
    ]


# --- static decals -------------------------------------------------------------------
def _uid(key: str, index: int) -> int:
    """A stable 32-bit uid per row (stock rows carry one; the format's last field)."""

    digest = uuid.uuid5(uuid.NAMESPACE_URL, f"beamng-mcp:{LEVEL_ID}:decal:{key}:{index}")
    return int.from_bytes(digest.bytes[:4], "big") & 0x7FFFFFFF


def _tangent(bearing_deg: float) -> tuple[float, float, float]:
    theta = math.radians(bearing_deg)
    return (math.sin(theta), math.cos(theta), 0.0)


def decal_rows(z_at) -> dict[str, list[list[float]]]:
    """619 rows in 12 keys / 6 families (design §3.2 + §6).

    ``z_at`` is injected (``terrain_model.z_at``) so this stays pure and a test can
    feed it a flat surface.  Every normal is the bilinear surface normal at the row's
    xy -- inside r 210 the hearth is exactly 100.000, so it is (0, 0, 1) there and
    the scorch streaks that run out to r 260 pick up the real slope.
    """

    import numpy as np

    rows: dict[str, list[list[float]]] = {}
    trail = layout()["decal_roads"][LITTER_TRAIL_KEY]["nodes"]
    trail_far = [n for n in trail if polar(float(n["x"]), float(n["y"]))[0] >= LITTER_R_MIN]
    for key, spec in DECAL_KEYS.items():
        # NEVER ``hash()``: PYTHONHASHSEED randomises it per process, so the rows
        # would differ between two runs of the same build.  uuid5 is stable.
        salt = int.from_bytes(
            uuid.uuid5(uuid.NAMESPACE_URL, f"beamng-mcp:{LEVEL_ID}:decalseed:{key}").bytes[:4],
            "big",
        )
        rng = np.random.default_rng(DECAL_SEED ^ salt)
        count = int(spec["rows"])
        out: list[list[float]] = []
        for index in range(count):
            if spec.get("geysers"):
                bearing, radius = GEYSER_SITES[index % len(GEYSER_SITES)]
                x, y = bearing_point(bearing, radius)
                size = float(spec["size"][0])
                heading = bearing
            elif spec.get("trail"):
                if not trail_far:
                    raise HearthSpecError("no trail nodes past the forest edge for the litter key")
                node = trail_far[int(index * len(trail_far) / max(count, 1))]
                jitter = rng.uniform(-6.0, 6.0, 2)
                x, y = float(node["x"]) + float(jitter[0]), float(node["y"]) + float(jitter[1])
                size = float(rng.uniform(*spec["size"]))
                heading = float(rng.uniform(0.0, 360.0))
            else:
                low, high = spec["r"]
                # equal-area radial draw, so the rows do not bunch at the inner edge
                radius = math.sqrt(rng.uniform(low * low, high * high))
                bearing = (index * 360.0 / max(count, 1) + float(rng.uniform(-6.0, 6.0))) % 360.0
                x, y = bearing_point(bearing, radius)
                size = float(rng.uniform(*spec["size"]))
                if spec.get("radial"):
                    heading = bearing
                elif spec.get("tangential"):
                    heading = (bearing + 90.0) % 360.0
                else:
                    heading = float(rng.uniform(0.0, 360.0))
            z = float(z_at(x, y))
            # the surface normal from the same bilinear patch castRayStatic uses
            step = 0.5
            dzdx = (float(z_at(x + step, y)) - float(z_at(x - step, y))) / (2 * step)
            dzdy = (float(z_at(x, y + step)) - float(z_at(x, y - step))) / (2 * step)
            norm = math.sqrt(dzdx * dzdx + dzdy * dzdy + 1.0)
            normal = (-dzdx / norm, -dzdy / norm, 1.0 / norm)
            tx, ty, tz = _tangent(heading)
            # re-orthogonalise the tangent against the normal
            dot = tx * normal[0] + ty * normal[1] + tz * normal[2]
            tx, ty, tz = tx - dot * normal[0], ty - dot * normal[1], tz - dot * normal[2]
            tlen = math.sqrt(tx * tx + ty * ty + tz * tz) or 1.0
            out.append(
                [
                    0,
                    _r6(size),
                    0,
                    _r6(x),
                    _r6(y),
                    _r6(z),
                    _r6(normal[0]),
                    _r6(normal[1]),
                    _r6(normal[2]),
                    _r6(tx / tlen),
                    _r6(ty / tlen),
                    _r6(tz / tlen),
                    _uid(key, index),
                ]
            )
        rows[decal_datablock(key)] = out
    return rows


def decal_census() -> dict[str, Any]:
    families = sorted({str(spec["family"]) for spec in DECAL_KEYS.values()})
    return {
        "keys": len(DECAL_KEYS),
        "rows": sum(int(spec["rows"]) for spec in DECAL_KEYS.values()),
        "families": families,
        "family_count": len(families),
    }


# --- the level_obstacles handoff for B5 ----------------------------------------------
def obstacle_rows() -> list[dict[str, Any]]:
    """``layout.registry_rows()`` with the owner of each row named.

    The runtime's ``hotPotatoRegisterObstacles`` takes ``{x, y, r, rp}`` with
    ``r in [0.5, 30]`` and ``rp <= r``, and a call REPLACES the set; the arena's own
    46 rows plus these 67 need ask #8's cap of 128.  B2 PROVES the 28 stone rows
    (the shapes it places); the other 39 belong to B4's props and are carried
    through unverified so B5 gets one file.
    """

    b2_names = {str(stone["name"]) for stone in layout()["stones"]}
    rows = []
    for row in layout()["registry_full"]:
        name = str(row["name"])
        rows.append(
            {
                "name": name,
                "x": _r6(row["x"]),
                "y": _r6(row["y"]),
                "r": _r6(row["r"]),
                "rp": _r6(row["rp"]),
                "why": str(row["why"]),
                "owner": "B2" if name in b2_names else "B4",
            }
        )
    bad = [r for r in rows if not (0.5 <= r["r"] <= 30.0) or r["rp"] > r["r"]]
    if bad:
        raise HearthSpecError(f"registry rows outside the runtime's contract: {bad}")
    return rows


# --- frame geometry: the fixed-pixel-box law, made unnecessary (r2) -------------------
#: The free camera every judged frame is shot through: 1920 x 1080, VERTICAL FOV 60,
#: Z up, no roll.  Validated by critic r1 to **0.7 px** on a known blob.
FRAME_W = 1920
FRAME_H = 1080
FRAME_VFOV_DEG = 60.0


def camera_basis(
    eye: tuple[float, float, float], aim: tuple[float, float, float]
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """(forward, right, up) for a Z-up look-at camera with no roll."""

    fx, fy, fz = (aim[i] - eye[i] for i in range(3))
    norm = math.sqrt(fx * fx + fy * fy + fz * fz)
    if norm <= 0:
        raise HearthSpecError("degenerate camera: eye == aim")
    f = (fx / norm, fy / norm, fz / norm)
    rx, ry, rz = f[1] * 1.0 - f[2] * 0.0, f[2] * 0.0 - f[0] * 1.0, f[0] * 0.0 - f[1] * 0.0
    rn = math.sqrt(rx * rx + ry * ry + rz * rz)
    if rn <= 1e-9:
        raise HearthSpecError("degenerate camera: looking straight up or down")
    r = (rx / rn, ry / rn, rz / rn)
    u = (
        r[1] * f[2] - r[2] * f[1],
        r[2] * f[0] - r[0] * f[2],
        r[0] * f[1] - r[1] * f[0],
    )
    return f, r, u


def project_point(
    point: tuple[float, float, float],
    eye: tuple[float, float, float],
    aim: tuple[float, float, float],
) -> tuple[float, float, float] | None:
    """World -> (px, py, depth); ``None`` when the point is behind the camera."""

    f, r, u = camera_basis(eye, aim)
    d = tuple(point[i] - eye[i] for i in range(3))
    depth = sum(d[i] * f[i] for i in range(3))
    if depth <= 0.01:
        return None
    tan_half = math.tan(math.radians(FRAME_VFOV_DEG) / 2.0)
    y_ndc = sum(d[i] * u[i] for i in range(3)) / (depth * tan_half)
    x_ndc = sum(d[i] * r[i] for i in range(3)) / (depth * tan_half * (FRAME_W / FRAME_H))
    return (FRAME_W * (0.5 + 0.5 * x_ndc), FRAME_H * (0.5 - 0.5 * y_ndc), depth)


def stone_cylinders() -> list[dict[str, float]]:
    """Each stone as the vertical cylinder a ray test needs: (x, y, foot z, radius, height)."""

    out = []
    for stone in stones():
        out.append(
            {
                "x": float(stone["x"]),
                "y": float(stone["y"]),
                "z0": float(stone["z"]),
                "radius": float(stone["diam"]) / 2.0,
                "height": float(stone["height"]),
            }
        )
    return out


def ground_classification(
    eye: tuple[float, float, float],
    aim: tuple[float, float, float],
    bands: dict[str, tuple[float, float]],
    z_plane: float = 100.0,
    step: int = 2,
) -> dict[str, Any]:
    """Per-pixel masks for named RADIUS BANDS of the ground, by projection.

    This function exists because of a law this round paid for twice.  A fixed pixel
    box is a guess about where the world lands in the frame, and both times the guess
    was wrong: r1's soot boxes sat on the ash below the stone, and r1's crust "slab
    control" box sat on ``hearth_stone_02`` -- so the headline 3.068x red excess was
    crust-vs-ROCK.  Nothing here is read off a picture.  Every pixel's ray is
    intersected with the ground plane, the hit's radius from the hearth centre says
    which band it is in, and any pixel whose ray meets a stone's cylinder FIRST is
    dropped, so no stone (or its silhouette) can contribute to either class.

    Returns the boolean masks (at ``step`` px sampling), the per-pixel radius and
    bearing, and the count in each band.  ``bands`` maps a name to an inclusive
    ``(r_min, r_max)`` in metres.
    """

    import numpy as np

    f, r, u = camera_basis(eye, aim)
    tan_half = math.tan(math.radians(FRAME_VFOV_DEG) / 2.0)
    px = np.arange(0, FRAME_W, step, dtype=np.float64) + 0.5
    py = np.arange(0, FRAME_H, step, dtype=np.float64) + 0.5
    gx, gy = np.meshgrid(px, py)
    x_ndc = (gx / FRAME_W - 0.5) * 2.0
    y_ndc = (0.5 - gy / FRAME_H) * 2.0
    sx = x_ndc * tan_half * (FRAME_W / FRAME_H)
    sy = y_ndc * tan_half
    dx = f[0] + sx * r[0] + sy * u[0]
    dy = f[1] + sx * r[1] + sy * u[1]
    dz = f[2] + sx * r[2] + sy * u[2]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (z_plane - eye[2]) / dz
    hits_ground = np.isfinite(t) & (t > 0.0)
    t = np.where(hits_ground, t, np.nan)
    wx = eye[0] + t * dx
    wy = eye[1] + t * dy
    radius = np.sqrt((wx - C[0]) ** 2 + (wy - C[1]) ** 2)
    bearing = (np.degrees(np.arctan2(wx - C[0], wy - C[1]))) % 360.0

    blocked = np.zeros_like(radius, dtype=bool)
    for cylinder in stone_cylinders():
        ox, oy = eye[0] - cylinder["x"], eye[1] - cylinder["y"]
        a = dx * dx + dy * dy
        b = 2.0 * (ox * dx + oy * dy)
        c = ox * ox + oy * oy - cylinder["radius"] ** 2
        disc = b * b - 4.0 * a * c
        with np.errstate(invalid="ignore", divide="ignore"):
            root = np.sqrt(np.maximum(disc, 0.0))
            t_in = (-b - root) / (2.0 * a)
            t_out = (-b + root) / (2.0 * a)
        near = np.maximum(t_in, 0.0)
        far = np.minimum(t_out, np.where(hits_ground, t, np.inf))
        z_near = eye[2] + near * dz
        z_far = eye[2] + far * dz
        low, high = cylinder["z0"], cylinder["z0"] + cylinder["height"]
        inside = (
            ((z_near >= low) & (z_near <= high))
            | ((z_far >= low) & (z_far <= high))
            | ((z_near < low) & (z_far > high))
            | ((z_far < low) & (z_near > high))
        )
        blocked |= (disc > 0.0) & (far > near) & (t_out > 0.0) & inside

    usable = hits_ground & ~blocked & np.isfinite(radius)
    masks = {
        name: usable & (radius >= low) & (radius <= high) for name, (low, high) in bands.items()
    }
    return {
        "step": step,
        "eye": list(eye),
        "aim": list(aim),
        "z_plane": z_plane,
        "bands": {k: list(v) for k, v in bands.items()},
        "masks": masks,
        "radius": radius,
        "bearing": bearing,
        "blocked_by_a_stone_px": int(blocked.sum()),
        "counts": {name: int(mask.sum()) for name, mask in masks.items()},
    }


def stone_band_classification(
    eye: tuple[float, float, float],
    aim: tuple[float, float, float],
    stone_name: str,
    bands: dict[str, tuple[float, float]],
    radius_fraction: float = 0.55,
    step: int = 2,
) -> dict[str, Any]:
    """Per-pixel masks for WORLD-HEIGHT bands on one stone, by projection.

    A ray is kept when it enters that stone's cylinder before anything else and the
    entry point's world z falls in the band.  ``radius_fraction`` shrinks the cylinder
    to a core column so the mask stays INSIDE the rock's real silhouette -- a rock is
    not a cylinder, and a mask that reaches its bounding radius would sample the sky
    past its shoulder.  Nothing here is a pixel box (see ``ground_classification``).
    """

    import numpy as np

    row = next((s for s in stones() if s["name"] == stone_name), None)
    if row is None:
        raise HearthSpecError(f"no stone named {stone_name}")
    f, r, u = camera_basis(eye, aim)
    tan_half = math.tan(math.radians(FRAME_VFOV_DEG) / 2.0)
    px = np.arange(0, FRAME_W, step, dtype=np.float64) + 0.5
    py = np.arange(0, FRAME_H, step, dtype=np.float64) + 0.5
    gx, gy = np.meshgrid(px, py)
    sx = (gx / FRAME_W - 0.5) * 2.0 * tan_half * (FRAME_W / FRAME_H)
    sy = (0.5 - gy / FRAME_H) * 2.0 * tan_half
    dx = f[0] + sx * r[0] + sy * u[0]
    dy = f[1] + sx * r[1] + sy * u[1]
    dz = f[2] + sx * r[2] + sy * u[2]
    cx, cy = float(row["x"]), float(row["y"])
    z0 = float(row["z"])
    radius = float(row["diam"]) / 2.0 * radius_fraction
    ox, oy = eye[0] - cx, eye[1] - cy
    a = dx * dx + dy * dy
    b = 2.0 * (ox * dx + oy * dy)
    c = ox * ox + oy * oy - radius * radius
    disc = b * b - 4.0 * a * c
    with np.errstate(invalid="ignore", divide="ignore"):
        t_in = (-b - np.sqrt(np.maximum(disc, 0.0))) / (2.0 * a)
    z_hit = eye[2] + t_in * dz
    on_stone = (disc > 0.0) & (t_in > 0.0) & (z_hit >= z0) & (z_hit <= z0 + float(row["height"]))
    masks = {
        name: on_stone & (z_hit >= low) & (z_hit <= high) for name, (low, high) in bands.items()
    }
    return {
        "stone": stone_name,
        "asset": row["asset"],
        "step": step,
        "radius_fraction": radius_fraction,
        "bands_world_z": {k: list(v) for k, v in bands.items()},
        "masks": masks,
        "world_z": z_hit,
        "counts": {name: int(mask.sum()) for name, mask in masks.items()},
        "on_stone_px": int(on_stone.sum()),
    }
