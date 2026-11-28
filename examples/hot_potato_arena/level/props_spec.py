"""B4 props and trail dressing: the pure specification the Blender build and the placer share.

Everything here is derived from the FROZEN design (``level_design_v4.md`` §3.4 kindling logs,
§7.2 the bench log, §7.3 the registry, §9 the prefab clusters, §11 the sign) and from
``design/layout.py``'s executable placement, which is re-imported rather than re-derived:
:func:`design_layout` reads the layout JSON the design shipped and every log, prop, foot,
camera and registry row below is that document's row.

The module is stdlib-only on purpose.  ``blender_props.py`` runs inside Blender (no repo
venv, no ``terrain_io``), so the terrain heights it needs are sampled ONCE by
``build_prop_shapes.py`` with ``terrain_io.surface_z`` -- the bilinear read of the shipped
quantised grid, which report_B §3.4 measured to BE the collision surface -- and handed over
as a small ``ground`` document.  A shape is therefore a pure function of
(design layout, sampled ground, this file).

The bench log's proportions are the load-bearing part; see :data:`BENCH` for the arithmetic
and the one deviation from the design's nominal split, which is recorded there and in the
report rather than hidden.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

LEVEL_ID = "ericrolph_hot_potato_arena"
EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
AUTHORING = EXAMPLE_ROOT / "authoring"
LAYOUT_JSON = AUTHORING / f"{LEVEL_ID}.level_layout.json"

#: mod-tree directory every B4 shape and map lives in (never B1's, B2's or B3's)
SHAPE_DIR = "art/shapes/props"
PREFAB_DIR = "art/prefabs"
#: the level group B4 owns; B1 owns level_objects/*, B2 the hearth, B3 vegetation
PROPS_GROUP = f"{LEVEL_ID}_props"

CENTER = (850.0, -280.0, 100.0)
SHAPE_SEED = 0x50524F50  # "PROP"

# --------------------------------------------------------------------------- COLLADA laws
#: pixel sizes for the three shipped details (AGENTS: N is the projected PIXEL size at which
#: the detail engages, larger = closer), matching design §3.4's _a700 / _a250 / _a80.
DETAILS = (700, 250, 80)
NULL_DETAIL = 4
BB_NODE = "bb_autobillboard25"
#: B0 measured: dim 64 -> 256x128, dim 128 -> 512x256.  Design §4.3 puts it on every
#: billboarded shape, "4 logs + 4 props".
BB_PROPERTY = "BB::DIM=128"


# --------------------------------------------------------------------------- materials
def material_name(key: str) -> str:
    return f"{LEVEL_ID}_p_{key}"


def texture_relative(key: str, role: str) -> str:
    suffix = {"b": "color", "nm": "normal", "r": "data", "ao": "data", "o": "data"}[role]
    return f"{SHAPE_DIR}/{material_name(key)}_{role}.{suffix}.png"


#: key -> cook recipe.  ``source`` names the CC0 asset in ``cc0_cache`` (design §12);
#: ``size`` is the shipped square (a power of two -- a non-power-of-two texture is silently
#: never cooked and draws magenta, level_facts).  ``ground`` is the groundType the material
#: binds (mod materials bind groundtype only under levels/<id>/art/shapes/..., AGENTS.md).
MATERIALS: dict[str, dict[str, Any]] = {
    "bench_bark": {
        "source": "knotted_pine_bark",
        "size": 2048,
        "ground": "WOOD",
        "role": "the bench log's round belly, both flanks and the two containment bolsters",
        "tint": (0.96, 0.92, 0.88),
        "rough": (0.62, 0.94),
        # r4: low-frequency weathering, so the flank does not average to one flat value at
        # 60-130 m.  See prop_textures._weathering for why a mip chain removes everything
        # else the tile carries and this is what is left.
        "weather": {"cells": 3, "octaves": 3, "depth": 0.30, "rough": 0.10},
    },
    "bench_hewn": {
        "source": "rough_wood",
        "size": 2048,
        "ground": "WOOD",
        "role": "the chainsaw-flat deck, the hewn wedge ramp and the sawn sides",
        # r4: the deck was the palest surface on the log and the one the broadside frames are
        # mostly made of.  0.94 / 0.90 / 0.84 takes the tint from a warm pale grey to weathered
        # timber without touching its grain.
        "tint": (0.94, 0.90, 0.84),
        "rough": (0.55, 0.90),
        "weather": {"cells": 2, "octaves": 3, "depth": 0.26, "rough": 0.08},
        # r5, a DECLARED DETAIL GRAFT, and the reason it exists is a measurement rather than
        # a frame: on the shipped cook the hewn deck's ``normal_relief_p50`` is **0.090**
        # against its own bark at 0.271, B4's kindling bark at 0.350, B3's forest bark at
        # 0.332 and B1's terrain rock at 0.332 -- 3 to 4x flatter than every neighbour it is
        # seen beside.  A surface with no relief has nothing for the light to do, which is
        # the other half of "flattens into pale timber slabs" (critic pass 3).
        #
        # The graft is the tool marks a hewn face is MADE of, at the scale a giant's tools
        # would leave them: adze scallops repeating along the log, the hewer's reach
        # wandering around the girth, and saw chatter across it.  The tile is 5.57 m in u by
        # 1.91 m in v (measured off the shipped DAE's own UVs, not assumed), so
        # ``stroke_cycles`` 2 is a 0.95 m scallop -- 7.5 screen px at 100 m, which is why it
        # survives the mip chain that eats the grain.
        #
        # Phase jitter is not decoration: a strictly periodic stroke is exactly the comb that
        # cost B1 r13/r14 two revisions, and the periodicity is MEASURED at every distance
        # (``periodic_line_ratio``) rather than assumed away.
        "relief": {
            "stroke_cycles": 2.0,
            "across_cycles": 3.0,
            "chatter_cycles": 5.0,
            "jitter": 0.10,
            #: the tangent-space slope of the steepest tenth of the surface -- the graft
            #: declares the statistic its own gate measures, so the two cannot drift apart
            "slope": 0.25,
            "ao": 0.22,
            "albedo": 0.10,
        },
    },
    "bench_endgrain": {
        "source": "rough_wood",
        "size": 1024,
        "ground": "WOOD",
        "role": "the bench log's end caps: generated growth rings over the rough-wood grain",
        "rings": True,
        "tint": (1.00, 0.94, 0.84),
        "rough": (0.58, 0.92),
    },
    "kindling_bark": {
        "source": "knotted_pine_bark",
        "size": 2048,
        "ground": "WOOD",
        "role": "log_north / log_south / the leaner: round bark",
        "tint": (0.96, 0.93, 0.90),
        "rough": (0.64, 0.95),
    },
    "kindling_char": {
        "source": "burned_ground_01",
        "size": 1024,
        "ground": "WOOD",
        "role": "the burnt bands at the four fire ends of the two round logs",
        "tint": (0.55, 0.52, 0.52),
        "rough": (0.72, 0.99),
    },
    "planks": {
        "source": "weathered_planks",
        "size": 1024,
        "ground": "WOOD",
        "role": "the trail sign board, the split-rail fence and the lantern posts",
        "tint": (1.00, 0.97, 0.92),
        "rough": (0.58, 0.92),
    },
    "sign_face": {
        "source": "weathered_planks",
        "size": 1024,
        "ground": "WOOD",
        "role": "the routed sign face: GIANT'S HEARTH / HOT COALS burnt into the plank",
        "text": True,
        "tint": (1.00, 0.97, 0.92),
        "rough": (0.55, 0.90),
    },
    "metal": {
        "source": "metal_plate_02",
        "overlay": "rust_coarse_01",
        "size": 1024,
        "ground": "METAL",
        "role": "the lantern's body and bail, the tripod ferrules and the fence brackets",
        "tint": (0.86, 0.85, 0.83),
        "rough": (0.32, 0.78),
    },
    "lantern_glass": {
        "source": "metal_plate_02",
        "size": 512,
        "ground": "METAL",
        "role": "the hurricane lantern's globe -- emissive, the night light source's face",
        "emissive": 2500.0,
        "tint": (1.00, 0.86, 0.58),
        "rough": (0.10, 0.24),
    },
    "enamel": {
        "source": "pot_enamel_01",
        "size": 2048,
        "ground": "METAL",
        "role": "the giant enamel pot (pot_enamel_01's own CC0 maps, re-cooked)",
        "gltf": True,
        "tint": (1.00, 1.00, 1.00),
        "rough": (0.18, 0.62),
    },
    "cairn_stone": {
        "source": "cliff_side",
        "size": 1024,
        "ground": "ROCK",
        "role": "the two stacked-stone trail cairns",
        "tint": (0.94, 0.93, 0.92),
        "rough": (0.60, 0.94),
    },
}


# --------------------------------------------------------------------------- the design layout
_LAYOUT_CACHE: dict[str, Any] | None = None


def design_layout() -> dict[str, Any]:
    """The frozen design's ``layout.json`` (B1 copied it into authoring/)."""

    global _LAYOUT_CACHE
    if _LAYOUT_CACHE is None:
        _LAYOUT_CACHE = json.loads(LAYOUT_JSON.read_text(encoding="utf-8"))
    return _LAYOUT_CACHE


def log_row(name: str) -> dict[str, Any]:
    for row in design_layout()["logs"]:
        if row["name"] == name:
            return row
    raise KeyError(name)


def prop_row(name: str) -> dict[str, Any]:
    for row in design_layout()["props"]:
        if row["name"] == name:
            return row
    raise KeyError(name)


def bearing_point(bearing_deg: float, r: float) -> tuple[float, float]:
    a = math.radians(bearing_deg)
    return (CENTER[0] + r * math.sin(a), CENTER[1] + r * math.cos(a))


def polar(x: float, y: float) -> tuple[float, float]:
    dx, dy = x - CENTER[0], y - CENTER[1]
    return (math.hypot(dx, dy), math.degrees(math.atan2(dx, dy)) % 360.0)


def heading_vector(heading_deg: float) -> tuple[float, float]:
    a = math.radians(heading_deg)
    return (math.sin(a), math.cos(a))


def engine_yaw_matrix(yaw_ccw_deg: float) -> list[float]:
    """Rows = the local axes in world coordinates (AGENTS.md arena laws)."""

    c = round(math.cos(math.radians(yaw_ccw_deg)), 9) + 0.0
    s = round(math.sin(math.radians(yaw_ccw_deg)), 9) + 0.0
    return [c, s, 0.0, -s, c, 0.0, 0.0, 0.0, 1.0]


def heading_matrix(heading_deg: float) -> list[float]:
    """A shape whose local +X runs along compass ``heading_deg`` (0 = +Y, 90 = +X)."""

    return engine_yaw_matrix(90.0 - heading_deg)


# --------------------------------------------------------------------------- the bench log
#: §7.2's proportions, with the ONE deviation this round makes and why.
#:
#: The design nominates a 29.2 m wedge at exactly 12 % against a 70.8 m deck.  29.2 x 0.12 =
#: 3.504 m, which is the deck height measured at the log's CENTRE; the rise the ramp actually
#: has to climb is deck 105.006 minus the ground at its toe, and a ramp that meets the deck
#: and the ground with a STEP in grade is the "hung up at slow speeds" class AGENTS.md L1285
#: names (a 0.12 grade discontinuity = 120 mm of second difference at one station, six times
#: the +-0.02 m relief law).  The Handle answers it with 3.0 m eases (DESIGN.md §2.4), and an
#: eased profile of run L with ease e delivers rise = g_max * (L - e): at L 29.2 / e 3.0 that
#: needs 12.96 %.  So the wedge keeps its 29.2 m ON THE LOG and grows a 3.8 m hewn toe apron
#: lying on the ground past the log's end -- run 33.0 m, g_max 11.3 %, deck 70.8 x 7.0 m and
#: every §7.2 radius unchanged.  The toe moves the ramp-foot exit 3.8 m along 210 deg, which
#: takes that exit's runoff from 242 m to 238 m (>= 50 m either way).
BENCH = {
    "name": "bench_log",
    "length_m": 100.0,
    "diam_m": 7.0,
    "deck_len_m": 70.8,
    "ramp_on_log_m": 29.2,
    "ramp_toe_apron_m": 3.8,
    "ease_m": 3.0,
    "grade_law": 0.12,
    "deck_lift_m": 3.5,
    "toe_proud_m": 0.004,  # the Handle's conformal-toe figure (DESIGN.md §2.4)
    "sides": 24,
    "min_side_height_m": 0.10,
    "bury_m": 0.30,
    # --- the broken crown at the WEST end (r2) --------------------------------------
    # r1 ended the deck in a SQUARE 3.40 m face.  Driven off it at ~4 m/s the car's nose
    # dropped into the void, the bumper caught the 90 deg lip, and the vehicle pole-vaulted
    # and came to rest INVERTED back on the deck at x_local +49.49 -- a trap 86 m outside
    # the ring, not the brief's "vertical escape".
    #
    # r2's FIRST attempt rolled the deck off on a convex arc down to a 1.0 m splintered lip,
    # and the recorded trajectories (which r1 never took) showed the same defect in
    # miniature: the roll-off pitches the car 26 deg nose-down, and 26 deg nose-down over a
    # 1.0 m lip puts the BUMPER on the ground while the wheels are still on the log.  At
    # 8 m/s the car went from -25.6 deg and 7.2 m/s to -59.5 deg and 0.65 m/s in ONE tick
    # and toppled; at 12 m/s it dug in, spun and landed on its side.  ANY lip at the foot of
    # a nose-down slope is a plough.
    #
    # So the crown carries no lip at all.  The last ``west_ramp_m`` of the log is an EASED
    # descent -- the same ``ramp_profile`` the east wedge climbs, reversed -- tangent to the
    # deck plane at the top and tangent to the TERRAIN at the foot, ending 4 mm proud of the
    # ground at the log's own end.  There is no edge anywhere for a nose to catch, and the
    # section narrows to ``west_taper`` of the log's half width so the end reads as a
    # snapped-off snout rather than as a sawn wedge.
    #
    # --- r3: the crown is SHORT and STEEP, because r2's was not an exit -------------
    # r2 spent the whole 16 m getting the fall down to 26 %, and critic pass 2 then drove
    # an etk800 UP it at 45 % throttle.  A ramp anyone can climb is not the design's
    # one-way drop-off, and deviation 7 had declared the loss of the drop without noticing
    # the log had grown a second ENTRANCE.  r3 keeps every property that made the descent
    # safe -- tangent to the deck at the top, tangent to the terrain at the foot, convex
    # crest, concave runout, NO LIP anywhere (level_facts law 6) -- and shortens the run so
    # the constant section is 72 %, which no road car climbs.  The eases are now
    # ASYMMETRIC: the crest keeps a 4.25 m radius (a car bridging it on a 2.8 m wheelbase
    # sags 0.23 m, so it tips over the brink instead of hanging on its belly) while the
    # foot is allowed to be tight, because above 6.46 m/s nothing touches it.
    #
    # The FOOT ease is long (5.4 m against the crest's 4.6) for one measured reason: the
    # break face below is only safe if the car ARRIVES at it gently.  r3's first snapped
    # crown had a 2.0 m foot ease, so the surface was still falling at 72 % where it broke
    # 1.05 m up; at 4 m/s the car's nose reached the meadow while its rear was still on the
    # log, dug in, pitched to -77 deg and stopped there -- the "hung up at slow speeds"
    # class AGENTS.md L1285 names.  A 5.4 m foot ease puts the grade at the break at 40 %
    # instead, and drops the face to 0.75 m, which the same drives clear.
    "west_ramp_m": 10.0,
    "west_ease_m": 4.6,
    "west_ease_foot_m": 5.4,
    "west_taper": 0.62,
    # --- the west end is TWO-WAY, and that is a measured conclusion, not a concession ---
    # r3's first boot drove the 72 % crown UP.  Not on traction -- on MOMENTUM: the etk800
    # arrived at the foot at 8.53 m/s off a 14 m run-up, and half v^2 (36 J/kg) is already
    # the same order as g*h (33 J/kg) for a 3.39 m rise.  At 45 % throttle it made it too.
    # The pickup did not (it stalled 1.3 m up and slid back), so it is vehicle-dependent,
    # exactly as r2's 26 % was.  No grade a level can afford beats a run-up: a car that can
    # reach 15 m/s on the meadow brings 112 J/kg to a 33 J/kg hill.
    #
    # One-wayness needs a DISCONTINUITY, so r3 snapped the log: the drivable surface stopped
    # ``west_break_face_m`` above the terrain and the rest was a splintered break face.  It
    # was built at two heights and driven at 4 / 6 / 8 / 10 / 12 m/s
    # (`b4/r3/crown_probe.json`, `b4/r3/evidence/`):
    #
    #   1.05 m  one-way -- etk800 at WOT and 45 %, and the pickup, ALL failed to climb it
    #           -- but at 4 m/s the car's nose reached the meadow while its rear was still
    #           on the log, dug in and stopped at pitch -77 deg, 1.8 m up: hung up.
    #   0.75 m  the same drives at 8 m/s POLE-VAULTED (pitch -85.9 deg, rest up.z -0.9808),
    #           and all three climbs cleared it -- a 0.75 m step is a kerb hop at 13 m/s.
    #
    # That is law 6 in its other direction, and it is worth writing down: **a step at the
    # foot of a nose-down slope ploughs whether the step goes UP or DOWN**, because the
    # failure is the nose reaching the lower surface while the rear is still on the slope.
    # A face tall enough to stop a climb is tall enough to catch a nose.
    #
    # So the crown ends TANGENT TO THE GROUND, the west end is honestly a two-way ramp
    # (deviation 7), and the design's one-way drops are the two flanks -- which no car can
    # climb, because nobody drives up the side of a log.  ``west_break_face_m`` stays as the
    # instrument that measured it; 0.0 means "run to the ground".
    "west_break_face_m": 0.0,
    # --- r3: the dished deck, and the two arrises that stop the roll ------------------
    # Critic pass 2 drove the deck 25 deg off the log's axis at 8 m/s with no brake input
    # and the car left over the SIDE at x_local +29 -- on the plateau, nowhere near either
    # end -- straddled the deck's square arris for 1.07 s and came to rest INVERTED 0.95 m
    # above the meadow.  At 90 deg (0.24 s of straddle) and at 10 deg (fast, so short) the
    # same drop is survived.  The defect is not the height, it is the square corner: a flat
    # face meeting a vertical-tangent flank gives a departing car a fulcrum to pivot on for
    # as long as it takes to cross it.
    #
    # A log that has been adzed out rather than split flat does not have that corner.  The
    # hewn face is DISHED between ``deck_flat_half_m`` and the log's widest line, and the
    # two arrises stand ``arris_h_m`` proud at that line.  An inadvertent drift climbs a
    # rolled 0.34 m shoulder and is turned back; the deck's drivable band is 5.1 m of dead
    # flat, which is wider than any stock BeamNG bridge deck.  The arris exists only where
    # the log stands proud of the ground -- it fades out over ``arris_lift_fade_m`` of
    # clearance, so it is absent at the ramp's toe and through the crown's last metres,
    # where a step-off is harmless and a kerb lying on the grass would be a trap.
    #
    # --- r3, second attempt: the ridge moved INBOARD, because the first one TRIPPED cars ---
    # r3's first section put the shoulder AT the log's widest line, and the 43-cell grid it
    # was built to satisfy refuted it: a car crossing a 0.34 m crest that sits ON the edge
    # arrives at the drop already rolled 20-37 deg, and ten cells that r2's flat deck had
    # survived came to rest INVERTED -- including the design's own inner flank step-off at
    # 3.0 m/s, which r2 landed at up.z +1.000 and the shoulder rolled to -0.9775.  Raising
    # the edge of a 3.5 m ledge does not make leaving it safer; it starts the roll earlier.
    #
    # So the ridge stands 0.85 m INBOARD of the edge and the deck comes back DOWN to the
    # deck plane outboard of it.  A drifting car still climbs a rolled 0.30 m crest and is
    # turned back; a car that crosses it lands on 0.65 m of flat shelf and leaves the log
    # FLAT, which is r2's geometry and r2's outcome.  The section strictly dominates both.
    #
    # --- r3, and this is what SHIPS: the deck is FLAT, because both raised sections were
    # --- refuted by the very grid they were built to satisfy -----------------------------
    # Two 43-cell boots, both kept (`b4/r3/evidence_arris_at_the_edge/`,
    # `b4/r3/evidence_ridge_and_shelf/`), no brake input in any cell:
    #     arris 0.34 m ON the edge          14 cells rolled past 90 deg, 32/43 upright at rest
    #     ridge 0.30 m set 0.65 m INBOARD   25 cells rolled past 90 deg, 24/43 upright at rest
    # Critic pass 2 offered "round the flank shoulder / narrow the deck's drivable band" as
    # the fix.  Measured, it is not one, and the reason the grid makes plain is that raising
    # anything at a 3.5 m ledge starts the roll BEFORE the car leaves: cells that departed
    # over the shoulder were already rolled 20-37 deg at the edge, against 14 deg over r2's
    # square arris.  A car does not topple because the edge is sharp; it topples because it
    # pivots on the edge while half of it is still supported, and a shoulder lengthens that.
    #
    # So r3 shipped the deck FLAT, at the design's own 7.0 m, with no raised edge anywhere.
    #
    # --- r4: the flat deck was refuted too, and by the mechanism r3 itself printed --------
    # Critic pass 3 drove the headings r3's 10 deg grid never sampled, ON r3's own certified
    # cut.  At 8 m/s EVERY off-axis heading from -30 to +25 deg rolls the car past 90 deg
    # except 0 itself; +-5 deg rolls it, and +25 rolls at 2 m/s and at 16 m/s.  r3's
    # ``problems: []`` was an artefact of its own sampling step, and its published safe band
    # ("10 to 25 deg, 4 to 12 m/s") was false on both axes.  r3's own straddle formula said
    # so: ``(L sin t + W cos t) / (v sin t)`` is ``a + b cot t``, monotone worse as the
    # heading approaches zero, extrapolating to 4.6 s at 5 deg.  A 5 deg drift is not a
    # manoeuvre, it is the resolution of a steering input, and on a 60.8 m plateau it reaches
    # the edge inside the deck's own length.
    #
    # Both r3 experiments were 0.30-0.34 m: KERB height, the regime that trips a wheel
    # without containing the car, and the grid duly measured both worse than flat.  r4 built
    # the two sections nobody had tried, drove them on ONE boot (bolster on the outer flank,
    # chamfer on the inner, so a heading's sign selects the treatment) at a 5 deg step from
    # 0 to +-45 and at 2 / 4 / 8 / 12 / 16 m/s, and shipped the winner on both flanks.
    #
    # WHAT SHIPS (r4, second cut): a CONTAINMENT WALL, and NO WINDOWS.
    #
    # The first r4 cut walled the flank at 0.90 m and kept the design's two 6 m split-out
    # windows open as aimed flank exits.  Its own 59-cell boot (``b4/r4/e1_flank_ab.json``)
    # refuted the WINDOWS, not the wall: every bolster cell that rolled (+20 to +40 deg from
    # x_local -18, 11 of 29) crossed the edge INSIDE the outer window or on its fade ramp,
    # while every cell that met the wall itself (+5 / +10 / +15 at 2, 8 and 16 m/s, +45 at
    # all three) was turned back upright.  A window is a ledge, and the straddle formula says
    # a ledge cannot be made safe at a shallow heading or at a low speed by any shape of
    # opening -- at 2 m/s even 35 and 40 deg rolled (the chamfer flank, same boot).  A 3.5 m
    # ledge anywhere along the long edge IS the defect, so there is no ledge anywhere on it.
    #
    # The wall is 1.20 m -- above a road car's belt line, not the 0.30-0.34 m kerb that trips
    # one -- and it is a WALL, not a bump: the inner face rises on a smoothstep over the
    # 0.30 m from ``deck_flat_half_m`` to ``deck_ridge_half_m`` (tangent to the deck at its
    # foot, 80 deg through the middle), the crest is FLAT from there to the log's widest
    # line (``wall_flat_top``: 0.20 m of standing rind), and the outer face drops vertically
    # from the crest to the deck plane at the widest line, where the round belly begins.  It
    # is faded out by CLEARANCE exactly as before (law 6: never a kerb lying on the grass),
    # so it grows out of the wedge where the wedge is 1.2 m clear of the meadow and dies
    # with the crown's descent.  The deck keeps 6.0 m of dead flat between the walls, which
    # is still wider than any stock BeamNG bridge deck.
    #
    # DEVIATION (declared in the report): the design's two flank drops are GONE.  The log has
    # two ways on and off -- the east wedge and the west crown, both two-way -- and a car that
    # drifts anywhere between them scrapes a wall and stays on the deck.  ``flank_splitouts``
    # is kept as the (empty) instrument so a later round can put a window back and re-drive
    # the grid rather than re-invent the experiment.
    #
    # CORRECTION to the brief this round was given: there is NO free bark outboard of the
    # hewn face.  The "4.67 m half width in bark against a 3.50 m hewn face" figure is a
    # maximum over every bark triangle in the a700 and it belongs to the two sawn-off KNOT
    # bosses ``blender_props._add_knot`` hangs off the belly at x +12 and +32 (46 vertices,
    # 26 stations, all of them 0.34-2.55 m up the belly).  The log's own section is 3.50 m
    # half width at every ring and the deck plane is 3.50 m half width too, so the bolster
    # is BUILT out of the drivable band, not merely left uncut (``b4/r4/i1_bench_section.json``).
    #
    # ``arris_h_m`` carries the SIGN of the treatment: > 0 is the wall, < 0 is the downward
    # chamfer (refuted, kept in ``FLANK_AB_RECIPES``).  ``flank_sections`` overrides any of
    # the four per side, which is what let one boot drive both candidates.  Both are kept so
    # a later round can re-run the comparison rather than re-invent it.
    "deck_flat_half_m": 3.00,
    "deck_ridge_half_m": 3.30,
    "arris_h_m": 1.20,
    "arris_lift_fade_m": 1.2,
    #: r4: the wall holds its full height from ``deck_ridge_half_m`` out to the widest line
    #: (a flat 0.20 m crest) instead of r3's ridge-and-shelf, which came back DOWN to the
    #: deck plane there and was the shelf a car left from.
    "wall_flat_top": True,
    #: per-side overrides of the four above, keyed "outer" (-y) / "inner" (+y).  Empty in
    #: the shipped section: both flanks carry the same wall.
    "flank_sections": {},
    # NO split-out windows ship (r4, second cut -- see the WHAT SHIPS block above).  The
    # tuple is the instrument the first r4 cut used: ``{"side", "centre_x", "length_m",
    # "fade_m"}`` rows open that side's wall to nothing for ``length_m`` about ``centre_x``
    # and fade it back over ``fade_m``.  ``+y`` is toward the hearth (the INNER flank).
    "flank_splitouts": (),
}
#: The r4 edge-treatment experiment, kept as a NAMED recipe rather than as a source edit.
#:
#: Critic pass 3 asked for two untested sections -- a containment bolster and a downward
#: chamfer -- and a 5 deg heading grid on each.  Two 27-minute boots would have measured them
#: under two different skies, two cuts and two harnesses.  Instead r4 put one on each FLANK
#: of a single mesh: ``+5 deg`` off the log's axis drifts a car to ``-y`` and ``-5 deg`` to
#: ``+y`` (measured, critic pass 3's own cells), so the SIGN OF THE HEADING selects the
#: treatment and both candidates are driven in one boot against a shared control.
#:
#: Set ``HOT_POTATO_B4_FLANK_AB=bolster_outer_chamfer_inner`` before the shape build, the cut
#: and the boot.  Unset -- which is what ships -- both flanks read :data:`BENCH` and carry the
#: same 0.90 m bolster; a static gate asserts that.
FLANK_AB_ENV = "HOT_POTATO_B4_FLANK_AB"
FLANK_AB_RECIPES: dict[str, dict[str, dict[str, float]]] = {
    # the two candidates, side by side.  The bolster keeps 6.0 m of flat deck and walls the
    # last 0.50 m; the chamfer keeps 5.4 m and falls the last 0.80 m by 0.30 m (37.5 % mean,
    # 56 % peak), which is the "30-40 % downward chamfer" the critic asked for.
    "bolster_outer_chamfer_inner": {
        "outer": {"deck_flat_half_m": 3.00, "deck_ridge_half_m": 3.50, "arris_h_m": 0.90},
        "inner": {"deck_flat_half_m": 2.70, "deck_ridge_half_m": 3.50, "arris_h_m": -0.30},
    },
}


def _apply_flank_ab() -> str | None:
    import os

    name = os.getenv(FLANK_AB_ENV, "").strip()
    if not name:
        return None
    if name not in FLANK_AB_RECIPES:
        raise KeyError(f"{FLANK_AB_ENV}={name!r} is not one of {sorted(FLANK_AB_RECIPES)}")
    BENCH["flank_sections"] = {k: dict(v) for k, v in FLANK_AB_RECIPES[name].items()}
    return name


#: the recipe in force, or ``None`` for the shipped symmetric section
FLANK_AB_ACTIVE = _apply_flank_ab()

BENCH_RAMP_RUN_M = BENCH["ramp_on_log_m"] + BENCH["ramp_toe_apron_m"]
#: gravity used for the crown's release-speed arithmetic (BeamNG's own default)
GRAVITY = 9.81


def smoothstep(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3.0 - 2.0 * t)


def ramp_grade(
    s: float, run: float, ease: float, g_max: float, ease_end: float | None = None
) -> float:
    """Grade at ``s`` metres from the TOE, eased at both ends (slope interpolation).

    AGENTS.md L1285: interpolate the SLOPE between the end grades and integrate, so the
    grade is monotone in magnitude and never exceeds either end anywhere.

    ``ease_end`` (r3) eases the FAR end over a different length from the near end.  The west
    crown needs that: its crest must stay wide enough that a car bridging it does not ground
    on its belly, while its foot may be tight because above the release speed nothing is
    touching the foot at all.
    """

    far = ease if ease_end is None else ease_end
    if s <= 0.0 or s >= run:
        return 0.0
    if s < ease:
        return g_max * smoothstep(s / ease)
    if s > run - far:
        return g_max * smoothstep((run - s) / far)
    return g_max


def ramp_rise_factor(run: float, ease: float, ease_end: float | None = None) -> float:
    """``rise / g_max`` for an eased profile: the run less half of each ease.

    ``smoothstep`` integrates to exactly half its interval, so an ease of length ``e``
    contributes ``g_max * e / 2`` instead of ``g_max * e``.
    """

    far = ease if ease_end is None else ease_end
    return run - 0.5 * ease - 0.5 * far


def ramp_profile(
    run: float, ease: float, rise: float, steps: int, ease_end: float | None = None
) -> list[tuple[float, float]]:
    """``steps`` + 1 (s, z above the toe) samples of the eased ramp that climbs ``rise``."""

    g_max = rise / ramp_rise_factor(run, ease, ease_end)
    out = [(0.0, 0.0)]
    z = 0.0
    fine = 4096
    ds = run / fine
    marks = {round(run * k / steps, 9) for k in range(steps + 1)}
    nxt = sorted(marks)[1:]
    target = nxt.pop(0)
    for i in range(fine):
        s0 = i * ds
        s1 = s0 + ds
        z += (
            0.5
            * (
                ramp_grade(s0, run, ease, g_max, ease_end)
                + ramp_grade(s1, run, ease, g_max, ease_end)
            )
            * ds
        )
        while target is not None and s1 >= target - 1e-9:
            out.append((target, z))
            target = nxt.pop(0) if nxt else None
    # integration closes on ``rise`` analytically; pin the last sample so it does exactly
    out[-1] = (run, rise)
    return out


def bench_max_grade(rise: float) -> float:
    return rise / (BENCH_RAMP_RUN_M - BENCH["ease_m"])


# ------------------------------------------------------------------- the west crown
def crown_half_width(radius: float, x: float, crown_x: float, run: float, taper: float) -> float:
    """Half width of the log's section at ``x``: full body, then the crown's smooth taper."""

    if x <= crown_x:
        return radius
    t = min(1.0, max(0.0, (x - crown_x) / run))
    return radius * (1.0 - (1.0 - taper) * smoothstep(t))


def ease_crest_radius(g_max: float, ease: float) -> float:
    """Smallest radius of curvature in an eased profile's CONVEX crest.

    ``ramp_grade`` interpolates the slope with a smoothstep over the ease, and
    ``max smoothstep' = 1.5``, so the steepest change of grade is ``1.5 g_max / ease`` per
    metre and the tightest radius is its reciprocal.  This is the number that decides
    whether a car stays on the surface or flies off the top of the descent.
    """

    if g_max <= 0.0 or ease <= 0.0:
        return math.inf
    return ease / (1.5 * g_max)


# ------------------------------------------------------------------- the dished deck (r3)
def arris_rise(
    a: float,
    flat_half: float,
    radius: float,
    height: float,
    crest_half: float | None = None,
    flat_top: bool = False,
) -> float:
    """Section height above the flat drivable band at across-fraction ``a`` in [-1, 1].

    Zero over the drivable band; a smoothstep to ``height`` at ``crest_half``; and, when the
    crest is set INBOARD of the log's widest line, EITHER a smoothstep back down to zero at
    that line (r3's ridge-and-shelf, ``flat_top`` False) OR -- r4's wall -- ``height`` held
    flat all the way out to it (``flat_top`` True), so the crest is a standing rind with no
    shelf beyond it.  Every segment's derivative is 0 at both of its ends, so there is no
    grade step anywhere across the section (AGENTS.md L1285).

    ``height`` carries the SIGN of the treatment, and r4 uses both signs:

    * ``height > 0`` is a **containment bolster** -- the un-adzed bark left standing along
      the flank.  With ``crest_half == radius`` it does not come back down, so the outboard
      edge of the deck IS the top of the wall and there is no shelf beyond it to leave from.
    * ``height < 0`` is a **downward chamfer** -- the outer band of the hewn face falls away.
      It is the only edge treatment that SHORTENS the straddle (the outboard wheels lose
      support earlier) instead of lengthening it, which is why r4 built and drove both.

    r3's two refuted experiments were ``height`` 0.34 and 0.30 with a crest at or inboard of
    the widest line: kerb height, the regime that trips a wheel without containing the car.
    """

    if height == 0.0 or radius <= 0.0:
        return 0.0
    t = min(1.0, abs(a))
    edge = min(0.999999, max(0.0, flat_half / radius))
    crest = 1.0 if crest_half is None else max(edge + 1e-6, crest_half / radius)
    if t <= edge:
        return 0.0
    # a crest AT (or outboard of) the log's widest line has no outer shelf: the section
    # rises -- or falls -- all the way to the edge and stops there.  r3's ``min(0.999999)``
    # clamp turned that case into a 1-micron shelf that read back as ZERO rise at |a| = 1,
    # i.e. a wall with a hole in its last sliver.
    if crest >= 1.0 - 1e-9:
        return height * smoothstep((t - edge) / (1.0 - edge))
    if t <= crest:
        return height * smoothstep((t - edge) / (crest - edge))
    if flat_top:
        return height
    return height * (1.0 - smoothstep((t - crest) / (1.0 - crest)))


#: the two long edges, named the way the hearth lies (``+y`` is toward it)
FLANK_SIDES = ("outer", "inner")


def flank_section(side: str, bench: dict[str, Any] | None = None) -> dict[str, float]:
    """``(flat_half, ridge_half, height)`` of one flank's edge treatment, in metres.

    The shipped section is symmetric, so both sides read the same three numbers off
    :data:`BENCH`.  ``BENCH["flank_sections"]`` overrides any of them per side, which is how
    r4 drove a containment bolster and a downward chamfer against each other on ONE boot
    instead of two: the sign of the heading picks the flank, and the flank picks the
    treatment, so both candidates were measured under an identical sky, terrain, cut and
    harness.  Keep it: the next round that wants to compare two sections should not have to
    spend two 27-minute boots to do it.
    """

    if side not in FLANK_SIDES:
        raise KeyError(side)
    b = BENCH if bench is None else bench
    over = dict((b.get("flank_sections") or {}).get(side, {}))
    return {
        "flat_half": float(over.get("deck_flat_half_m", b["deck_flat_half_m"])),
        "ridge_half": float(over.get("deck_ridge_half_m", b["deck_ridge_half_m"])),
        "height": float(over.get("arris_h_m", b["arris_h_m"])),
        # r4: a wall holds its height from the crest to the widest line; r3's ridge and
        # the first r4 cut's bolster (crest AT the widest line) read False here harmlessly
        "flat_top": bool(over.get("wall_flat_top", b.get("wall_flat_top", False))),
    }


def flank_kind(height: float) -> str:
    """What a signed section height means, in one word, for reports and evidence rows.

    ``bolster`` is the word the first r4 cut used for its 0.90 m section; the shipped 1.20 m
    flat-crested wall reads the same word so every r4 evidence row stays comparable.
    """

    if height > 0.0:
        return "bolster"
    if height < 0.0:
        return "chamfer"
    return "flat"


def arris_lift_factor(clearance: float, fade: float) -> float:
    """The arris exists only where the log stands proud: 0 on the ground, 1 above ``fade``.

    A raised edge lying on the grass at the ramp's toe or at the crown's foot would be
    exactly the lip level_facts law 6 forbids, so the shoulder is faded out by CLEARANCE
    rather than by station -- it cannot survive a change to either end's geometry.
    """

    if fade <= 0.0:
        return 1.0
    return smoothstep(min(1.0, max(0.0, clearance / fade)))


def splitout_factor(x: float, side: str, windows=None) -> float:
    """0 inside this side's split-out window, 1 outside it, smoothstepped over the fade.

    A split-out is where the loggers took a slab off the flank: the arris is gone for
    ``length_m`` and the flank is a drop again.  It is the design's one-way flank exit,
    made into something a player AIMS at instead of something a 25 deg drift falls into.
    """

    factor = 1.0
    for window in windows if windows is not None else BENCH["flank_splitouts"]:
        if window["side"] != side:
            continue
        half = 0.5 * float(window["length_m"])
        fade = float(window["fade_m"])
        d = abs(x - float(window["centre_x"]))
        if d <= half:
            factor = 0.0
        elif d < half + fade:
            factor = min(factor, smoothstep((d - half) / fade))
    return factor


def splitout_window(side: str, windows=None) -> tuple[float, float] | None:
    """(x_lo, x_hi) of this side's split-out core in local metres, or None: no window.

    r4 ships no windows (``BENCH["flank_splitouts"]`` is empty), so every caller must be
    written for ``None`` -- the wall is continuous and there is no flank exit to drive.
    """

    if side not in FLANK_SIDES:
        raise KeyError(side)
    for window in windows if windows is not None else BENCH["flank_splitouts"]:
        if window["side"] == side:
            half = 0.5 * float(window["length_m"])
            return (float(window["centre_x"]) - half, float(window["centre_x"]) + half)
    return None


def crest_release_speed(g_max: float, ease: float) -> float:
    """Speed above which a car leaves an eased crest: ``v^2 / R = g``.

    Below it the wheels stay loaded over the whole descent; above it the car flies from the
    crest with its pitch frozen and lands further down the slope -- a jump, not a flip.
    Either way there is no lip, so there is nothing for the nose to catch on.
    """

    return math.sqrt(GRAVITY * ease_crest_radius(g_max, ease))


# --------------------------------------------------------------------------- the shape table
def _log_shape(key: str, layout_name: str) -> dict[str, Any]:
    row = log_row(layout_name)
    return {
        "key": key,
        "family": "logs",
        "layout": layout_name,
        "length": float(row["length"]),
        "diam": float(row["diam"]),
    }


SHAPES: dict[str, dict[str, Any]] = {
    "bench_log": {
        "key": "bench_log",
        "family": "logs",
        "layout": "bench_log",
        "kind": "bench",
        "materials": ("bench_bark", "bench_hewn", "bench_endgrain"),
        "budget": {700: 7000, 250: 1500, 80: 520},
        # r3: 1400 forced a 55 % COLLAPSE of the authored collider, and a collapsed collider
        # is why critic pass 2 (N6) found it riding up to +8.02 mm above its own visual at
        # the descent's foot.  3200 is above the authored count, so ``decimate_to`` never
        # runs and the drivable surface a wheel meets is the one this file describes.  A
        # 3.1 k static collision mesh is noise against the level's 116,018 Colmesh solids.
        "colmesh": 4300,
        "bb": True,
        "collision": "Collision Mesh",
        "note": "half-log deck +3.5 m with the hewn wedge ramp; the only drivable outside solid",
    },
    "log_north": {
        **_log_shape("log_north", "log_north"),
        "kind": "round_log",
        "materials": ("kindling_bark", "kindling_char", "bench_endgrain"),
        "budget": {700: 4200, 250: 1000, 80: 320},
        "colmesh": 260,
        "bb": True,
        "collision": "Collision Mesh",
        "char_ends": True,
        "note": "kindling: lit at both ends, half sunk 1.0 m",
    },
    "log_south": {
        **_log_shape("log_south", "log_south"),
        "kind": "round_log",
        "materials": ("kindling_bark", "kindling_char", "bench_endgrain"),
        "budget": {700: 4200, 250: 1000, 80: 320},
        "colmesh": 260,
        "bb": True,
        "collision": "Collision Mesh",
        "char_ends": True,
        "note": "kindling: lit at both ends, half sunk 1.0 m",
    },
    "leaner_log": {
        **_log_shape("leaner_log", "leaner_log"),
        "kind": "leaner",
        "materials": ("kindling_bark", "kindling_char", "bench_endgrain"),
        "budget": {700: 4200, 250: 1000, 80: 320},
        "colmesh": 260,
        "bb": True,
        "collision": "Collision Mesh",
        "char_ends": False,
        "note": "the next log, leaned on hearth_stone_15's shoulder at z 112.0",
    },
    "lantern_tripod": {
        "key": "lantern_tripod",
        "family": "props",
        "kind": "tripod",
        "materials": ("kindling_bark", "metal"),
        "budget": {700: 2600, 250: 780, 80: 240},
        "colmesh": 220,
        "bb": True,
        "collision": "Collision Mesh",
        "note": "three 2.5 m poles x 70 m on a 40 m foot circle, apex +62 m, lashed",
    },
    "giant_lantern": {
        "key": "giant_lantern",
        "family": "props",
        "kind": "lantern",
        "materials": ("metal", "lantern_glass"),
        "budget": {700: 2400, 250: 720, 80: 220},
        "colmesh": 180,
        "bb": True,
        "collision": "Collision Mesh",
        "note": "a 16 m hurricane lantern hung at +46 m; its globe is the emissive face",
    },
    "enamel_pot": {
        "key": "enamel_pot",
        "family": "props",
        "kind": "pot",
        "materials": ("enamel",),
        "budget": {700: 3600, 250: 1000, 80: 300},
        "colmesh": 200,
        "bb": True,
        "collision": "Collision Mesh",
        "note": "pot_enamel_01 (CC0) x 54, upright, lid on",
    },
    "trail_sign": {
        "key": "trail_sign",
        "family": "props",
        "kind": "sign",
        "materials": ("planks", "sign_face", "metal"),
        "budget": {700: 900, 250: 320, 80: 120},
        "colmesh": 60,
        "bb": False,
        "collision": "Collision Mesh",
        "note": "2.4 m routed trail sign: GIANT'S HEARTH / HOT COALS",
    },
    "trail_cairn": {
        "key": "trail_cairn",
        "family": "props",
        "kind": "cairn",
        "materials": ("cairn_stone",),
        "budget": {700: 1400, 250: 420, 80: 150},
        "colmesh": 90,
        "bb": False,
        "collision": "Collision Mesh",
        "note": "a 1.8 m stack of seven weathered slabs",
    },
    "fence_post": {
        "key": "fence_post",
        "family": "props",
        "kind": "fence_post",
        "materials": ("planks", "metal"),
        "budget": {700: 320, 250: 130, 80: 60},
        "colmesh": 40,
        "bb": False,
        "collision": "Collision Mesh",
        "note": "a split-rail post, 1.35 m clear, mortised twice",
    },
    "fence_rail": {
        "key": "fence_rail",
        "family": "props",
        "kind": "fence_rail",
        "materials": ("planks",),
        "budget": {700: 220, 250: 90, 80: 40},
        "colmesh": 24,
        "bb": False,
        "collision": "Collision Mesh",
        "note": "a 3.9 m riven rail",
    },
    "lantern_post": {
        "key": "lantern_post",
        "family": "props",
        "kind": "lantern_post",
        "materials": ("planks", "metal", "lantern_glass"),
        "budget": {700: 560, 250: 210, 80: 90},
        "colmesh": 56,
        "bb": False,
        "collision": "Collision Mesh",
        "note": "2.6 m post carrying track_lantern_<i> (B2 owns the light)",
    },
}


def shape_stem(key: str) -> str:
    return f"{LEVEL_ID}_p_{key}"


def shape_relative(key: str) -> str:
    return f"{SHAPE_DIR}/{shape_stem(key)}.dae"


def shape_path(key: str) -> str:
    return f"/levels/{LEVEL_ID}/{shape_relative(key)}"


# --------------------------------------------------------------------------- fence + prefabs
#: the split-rail fence runs along the trail's DOWNHILL (outer) edge through the forest,
#: where S8 looks at it: 20 posts at 8.0 m pitch from trail m 470, two rails per bay.
FENCE = {
    "start_m": 470.0,
    "pitch_m": 8.0,
    "posts": 20,
    "rails_per_bay": 2,
    "lateral_m": 4.6,
    "rail_z": (0.55, 1.05),
}
FENCE_RAILS = (FENCE["posts"] - 1) * FENCE["rails_per_bay"]
FENCE_SEGMENTS = FENCE["posts"] + FENCE_RAILS

#: design §9: four prefab files, 430 instances, 4,480 instantiated statics.
PREFAB_CLUSTERS = (
    {
        "key": "pf_deadfall_cluster",
        "members": 12,
        "instances": 200,
        "zone": "forest",
        "r": (380.0, 840.0),
        "spread": 16.0,
        "layers": ("forest_floor", "scree"),
    },
    {
        "key": "pf_scree_cluster",
        "members": 10,
        "instances": 150,
        "zone": "scree",
        "r": (700.0, 1010.0),
        "spread": 13.0,
        "layers": ("scree", "rock", "alpine"),
    },
    {
        "key": "pf_trail_edge",
        "members": 8,
        "instances": 50,
        "zone": "trail",
        "r": (300.0, 1060.0),
        "spread": 7.0,
        "layers": (),
    },
    {
        "key": "pf_shore_drift",
        "members": 6,
        "instances": 30,
        "zone": "shore",
        "r": (300.0, 730.0),
        "spread": 11.0,
        "layers": ("shore", "lakebed"),
    },
)
PREFAB_INSTANCES = sum(c["instances"] for c in PREFAB_CLUSTERS)
PREFAB_STATICS = sum(c["members"] * c["instances"] for c in PREFAB_CLUSTERS)

#: the B3 shapes each cluster re-uses (a prefab GROUPS existing statics; B4 authors none of
#: these meshes and never rewrites B3's files).
B3_SHAPES = {
    "deadwood": (
        "f_fallen_log_a",
        "f_fallen_log_b",
        "f_fallen_log_c",
        "f_stump_a",
        "f_stump_b",
        "f_root_cluster",
        "f_windthrow_roots",
        "f_branch_pile",
        "f_bark_debris",
    ),
    "rocks": (
        "f_boulder_forest_a",
        "f_boulder_forest_b",
        "f_mossy_rock_a",
        "f_mossy_rock_b",
        "f_mossy_rock_c",
        "f_mossy_rock_d",
        "f_mossy_rock_e",
        "f_lichen_boulder",
        "f_scree_rock_a",
        "f_scree_rock_b",
        "f_pebble_cluster",
        "f_nq_boulder_02",
        "f_nq_boulder_05",
        "f_nq_boulder_06",
        "f_driftwood",
        "f_cliff_outcrop_a",
    ),
    "undergrowth": ("f_fern_a", "f_fern_b", "f_shrub_02", "f_shrub_03", "f_reed_clump"),
}


def b3_shape_path(family: str, key: str) -> str:
    return f"/levels/{LEVEL_ID}/art/shapes/{family}/{LEVEL_ID}_{key}.dae"


#: cluster member tables: (family, shape key, local polar offset r, bearing, yaw, scale)
#: are generated deterministically in ``place_props``; the SHAPE MIX is pinned here so the
#: census can read the six QB-27 dressing families off the spec.
CLUSTER_MIX = {
    "pf_deadfall_cluster": (
        ("deadwood", "f_fallen_log_a"),
        ("deadwood", "f_fallen_log_b"),
        ("deadwood", "f_fallen_log_c"),
        ("deadwood", "f_stump_a"),
        ("deadwood", "f_stump_b"),
        ("deadwood", "f_root_cluster"),
        ("deadwood", "f_windthrow_roots"),
        ("deadwood", "f_branch_pile"),
        ("deadwood", "f_bark_debris"),
        ("rocks", "f_mossy_rock_a"),
        ("rocks", "f_boulder_forest_a"),
        ("undergrowth", "f_fern_a"),
    ),
    "pf_scree_cluster": (
        ("rocks", "f_scree_rock_a"),
        ("rocks", "f_scree_rock_b"),
        ("rocks", "f_pebble_cluster"),
        ("rocks", "f_nq_boulder_05"),
        ("rocks", "f_nq_boulder_06"),
        ("rocks", "f_lichen_boulder"),
        ("rocks", "f_mossy_rock_c"),
        ("rocks", "f_mossy_rock_d"),
        ("rocks", "f_cliff_outcrop_a"),
        ("deadwood", "f_bark_debris"),
    ),
    "pf_trail_edge": (
        ("rocks", "f_scree_rock_b"),
        ("rocks", "f_pebble_cluster"),
        ("rocks", "f_mossy_rock_b"),
        ("rocks", "f_mossy_rock_e"),
        ("deadwood", "f_branch_pile"),
        ("deadwood", "f_stump_b"),
        ("undergrowth", "f_fern_b"),
        ("undergrowth", "f_shrub_03"),
    ),
    "pf_shore_drift": (
        ("rocks", "f_driftwood"),
        ("rocks", "f_pebble_cluster"),
        ("rocks", "f_nq_boulder_02"),
        ("rocks", "f_mossy_rock_e"),
        ("undergrowth", "f_reed_clump"),
        ("deadwood", "f_bark_debris"),
    ),
}

#: QB-27's six dressing families, mapped to the shapes that carry them
DRESSING_FAMILIES = {
    "signage": ("trail_sign",),
    "fences_rails": ("fence_post", "fence_rail"),
    "poles_lights": ("lantern_post", "lantern_tripod", "giant_lantern"),
    "debris_junk": ("f_bark_debris", "f_branch_pile"),
    "vehicles_props": ("enamel_pot", "bench_log"),
    "rocks_cliffs": ("trail_cairn", "f_scree_rock_a", "f_boulder_forest_a"),
}


# --------------------------------------------------------------------------- the road stack
#: design §2.3.1 verbatim: layer -> (width, textureLength, startEndFade, distanceFade,
#: renderPriority, drivability).  B1 built the stack from the same table; B4 owns it from
#: this round on and the static gate below compares the SHIPPED records against these rows.
#:
#: ONE row deviates from the design table, and it is measured rather than chosen:
#: ``m_dirt_variation`` -- the SURFACE layer -- carries textureLength 32, not 128.  128 is a
#: 16:1 stretch on the 8 m track and a 21:1 stretch on the 6 m trail, which is the smear the
#: r1 critic measured in both trail frames.  ``b4/census_stock_texturelength.py`` counts the
#: ratio over 39,251 visible stock DecalRoads: surface-class roads run p05 2.0, MEDIAN 4.0,
#: p95 15.0, and only 227 of 10,905 pass 16:1.  The design's 64-300 m figures came from the
#: study's measurement of variation OVERLAYS, whose stock median ratio is 16:1 -- and every
#: overlay row below is inside that band.  32 puts the track at 4.0:1 and the trail at 5.3:1.
ROAD_STACK = {
    "m_dirt_variation": {
        "width": {"track": 8.0, "trail": 6.0},
        "textureLength": 32,
        "startEndFade": [20, 20],
        "distanceFade": [250, 50],
        "renderPriority": 20,
        "drivability": {"track": 0.5, "trail": 0.3},
        "records": 2,
    },
    "m_dirt_flows": {
        "width": 2.5,
        "textureLength": 8,
        "startEndFade": [5, 5],
        "distanceFade": [150, 50],
        "renderPriority": 14,
        "drivability": -1,
        "records": 14,
    },
    "m_dirt_gravel": {
        "width": 3.0,
        "textureLength": 12,
        "startEndFade": [5, 5],
        "distanceFade": [150, 50],
        "renderPriority": 10,
        "drivability": -1,
        "records": 9,
    },
    "m_dirt_tiretracks": {
        # r3: ONE centred 3.6 m record per road instead of two 3.5 m records at +-1.2 m.
        # The ruts opacity mask already paints a PAIR inside the record, so r2 shipped four
        # ruts across a 6 m trail -- a wash, which is why critic pass 2 saw no wheel path.
        "width": 3.6,
        "textureLength": 16,
        "startEndFade": [20, 20],
        "distanceFade": [150, 50],
        "renderPriority": 4,
        "drivability": -1,
        "records": 2,
    },
    "m_bank_erosion": {
        "width": 4.0,
        "textureLength": 16,
        "startEndFade": [5, 5],
        "distanceFade": [150, 50],
        "renderPriority": 12,
        "drivability": -1,
        "records": 4,
    },
    "m_mud_cracks": {
        "width": 4.0,
        "textureLength": 6,
        "startEndFade": [3, 3],
        "distanceFade": [120, 40],
        "renderPriority": 8,
        "drivability": -1,
        "records": 12,
    },
    "m_puddle_wet": {
        "width": 3.0,
        "textureLength": 5,
        "startEndFade": [2, 2],
        "distanceFade": [120, 40],
        "renderPriority": 6,
        "drivability": -1,
        "records": 10,
    },
    "m_track_dust_overlay": {
        "width": 5.0,
        "textureLength": 48,
        "startEndFade": [30, 30],
        "distanceFade": [200, 50],
        "renderPriority": 16,
        "drivability": -1,
        # r3: the TRACK only.  On the trail this pale 35 % wash WAS the paleness.
        "records": 1,
    },
    "m_skid_arc": {
        "width": 4.0,
        "textureLength": 20,
        "startEndFade": [30, 30],
        "distanceFade": [150, 50],
        "renderPriority": 3,
        "drivability": -1,
        "records": 40,
    },
    "m_needle_litter": {
        "width": 2.5,
        "textureLength": 4,
        "startEndFade": [0.2, 0.2],
        "distanceFade": [80, 40],
        "renderPriority": 1,
        "drivability": -1,
        "records": 10,
    },
}

#: the members B4 owns in ``main/MissionGroup/decal_road/items.level.json``: every visible
#: track and trail layer (§2.3.1's eight-layer stack) plus the needle litter.  The 40 hearth
#: skid arcs on the slab are B2's hearth dressing and are NOT B4's, even though they live in
#: the same file -- the report names the split.
B4_ROAD_PREFIXES = (
    f"{LEVEL_ID}_track_",
    f"{LEVEL_ID}_trail_",
)
B2_ROAD_PREFIXES = (f"{LEVEL_ID}_hearth_skid_",)
B1_ROAD_PREFIXES = (f"{LEVEL_ID}_ai_",)


def road_owner(name: str) -> str:
    if name.startswith(B2_ROAD_PREFIXES):
        return "B2"
    if name.startswith(B1_ROAD_PREFIXES):
        return "B1"
    if name.startswith(B4_ROAD_PREFIXES):
        return "B4"
    return "?"


# --------------------------------------------------------------------------- cameras
#: B4's two camera bookmarks (§8): S5 at the night clock, S8 on the trail switchback.
B4_CAMERAS = ("S5_lantern_night", "S8_trail_switchback")


def camera_row(name: str) -> dict[str, Any]:
    for row in design_layout()["cameras"]:
        if row["name"] == name:
            return row
    raise KeyError(name)


__all__ = [
    "B4_CAMERAS",
    "BENCH",
    "BENCH_RAMP_RUN_M",
    "CLUSTER_MIX",
    "DETAILS",
    "FENCE",
    "FLANK_AB_ACTIVE",
    "FLANK_AB_ENV",
    "FLANK_AB_RECIPES",
    "FLANK_SIDES",
    "GRAVITY",
    "LEVEL_ID",
    "MATERIALS",
    "PREFAB_CLUSTERS",
    "ROAD_STACK",
    "SHAPES",
    "arris_lift_factor",
    "arris_rise",
    "bench_max_grade",
    "crest_release_speed",
    "crown_half_width",
    "design_layout",
    "ease_crest_radius",
    "flank_kind",
    "flank_section",
    "heading_matrix",
    "material_name",
    "ramp_grade",
    "ramp_profile",
    "ramp_rise_factor",
    "shape_path",
    "shape_relative",
    "shape_stem",
    "splitout_factor",
    "splitout_window",
    "texture_relative",
]
