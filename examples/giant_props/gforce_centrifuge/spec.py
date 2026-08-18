"""Charlie's LAHC Centrifuge — authored constants for Blender + runtime.

Shipped name (2026-08-11): the beamng.com listing is "Charlie's LAHC
Centrifuge" — C.H.I.E.F. phonetic, LAHC after the marquee's
LORENTZ-ACTUATED HYPER-G COMPLEX — so DISPLAY_NAME matches it and players
find in the vehicle selector the thing they downloaded. Internal names
(MOD_ID, ZIP_BASENAME, the gforce_centrifuge directory) are unchanged:
renaming those would orphan every installed copy.

A giant laboratory centrifuge bowl: banked steel drum wall, central
spindle with a rotating overhead boom, and an RPM dial the size of a
dinner table. Drive up the trestle, drop into the bowl, and the machine
notices its new SAMPLE: the drum spins up through escalating RPM plateaus
(10 - 50 - 120 - 250 - 500), a per-frame tangential velocity field drags
the car into orbit, and the banked wall supplies the centripetal reaction
— so the soft-body takes real, escalating G-load until parts let go. After
holding maximum RPM the centrifuge SPITS the sample out the front
entrance at the speed it is going (player 2026-08-09): the mouth opens
mid-spin and the sample is launched down the corridor centreline on its
first pass. The car itself is the spinning bob; nothing else moves it.

Anticipation: plateau messages escalate, the boom visibly accelerates, the
needle sweeps the dial, and the hub smokes past 400 RPM.
"""

MOD_ID = "ericrolph_gforce_centrifuge"
DISPLAY_NAME = "Charlie's LAHC Centrifuge"
VALUE_DOLLARS = 31000
ZIP_BASENAME = "gforce_centrifuge_ericrolph.zip"

# Authored frame: right-handed, meters, Z-up, +Y drive direction. Entry
# trestle at -Y climbs to the rim shelf; the bowl centre is the origin.
# CHIEF-scale bowl (2026-08-05 rebuild): shallow cone floor blending into
# a velodrome bank. Cone r 2->16 rising z 0.5->2.6; bank r 16->19.5
# climbing z 2.6->7.0 on a concave curve.
CONE_INNER_R = 2.0
CONE_INNER_Z = 0.5
# Aligned to the track_bowl component's ACTUAL geometry (its cone ends at
# BANK_R0 = 15.20, deck z = 0.5 + 13.2*0.15 = 2.48). The cage previously
# claimed 16.0/2.6, and that 0.8 m mismatch was the see-through gap the
# player photographed - collision floor where no visual floor existed.
CONE_OUTER_R = 15.2
CONE_OUTER_Z = 2.48
# MEASURED off the track_bowl component's real Hermite bank curve
# (scratchpad/measure_bank.py). The previous hand-written chords were up
# to 1.60 m away from the rendered surface - collision floating in air
# above the wall and dipping below it elsewhere. That divergence IS the
# "gap between the inner ring and the outer wall" the player drove across.
# Sampled straight off track_bowl._bank_frame() over its FULL arc s=0..1.
#
# This previously stopped at s = BANK_S_HAZARD (0.779), i.e. r 18.551 /
# z 5.775, because the sampling run was capped at the hazard band.  The
# VISUAL bank keeps going to r 19.5 / z 7.0, so the top 1.2 m of visible
# banked wall carried no collision anywhere around the drum - a car that
# rode high went straight through it (player: "a visible geometric gap
# between the inner rotating ring and the outer structural ring/wall,
# as seen where the vehicle drives across").  Nine points hold the cage
# within 0.04 m of the true curve over the whole span.
BANK_PROFILE = (
    (15.2, 2.48),
    (15.737, 2.666),
    (16.275, 3.037),
    (16.812, 3.555),
    (17.35, 4.181),
    (17.887, 4.877),
    (18.425, 5.604),
    (18.962, 6.325),
    (19.5, 7.0),
)
RIM_TOP_R = 19.5
RIM_TOP_Z = 7.0
# Legacy names still used by the runtime helpers (kept in sync).
FLOOR_R = 15.2
FLOOR_TOP_Z = 2.48
WALL_SEGMENTS = 28
# Entry: stadium-style vomitory tunnel under the bank at -Y, door plug
# covers the bank opening while spinning (segments 20,21).
GARAGE_SEGMENTS = {20, 21}
# How far UP the bank the doorway's collision cut runs, in BANK_PROFILE
# level indices: quads below this level are omitted in the garage columns.
#
# HEADROOM (2026-08-11, player: "I cannot get larger vehicles to pass
# through into the centrifuge, visually it looks like I should"). They
# were right about the visual - the VISUAL bank opens full height there
# (`skip_frac=1.0`), but the cage only cut levels 0..4, so BANK_PROFILE
# level 5 (r 17.887, z 4.877) stood as an INVISIBLE LINTEL across the
# mouth. Section-plane probe of the shipped jbeam: clear height pinched
# to 2.53 m at the lintel's inner edge, over a deck at 2.35. A hatchback
# roof at ~1.45 m sails under it; the MD-series tanker at ~3.3 m cannot.
# Vertical raycasts had never caught it - the corridor walls are vertical
# and therefore edge-on to a down ray, so the corridor measured "9 m
# clear" while a truck sat stopped in it.
#
# REVERTED TO 5 (2026-08-11, same day): raising it to 7 DID give 4.10 m
# of headroom, and it caused a worse bug - "now that I'm testing larger
# vehicles, they're getting stuck ... near the door". Azimuthal sweep of
# the shipped cage, worst jump between adjacent samples at the doorway
# edge (node column 22):
#
#     r 16.5   0.113 m      <- pre-existing, levels 1..4
#     r 17.0   0.158 m      <- pre-existing
#     r 17.5   0.303 m      <- pre-existing
#     r 18.0   2.537 m      <- CREATED by cutting levels 5..6
#
# Radially the doorway is smooth at every radius, so none of this shows
# up driving in or out; it bites when a car crosses the doorway
# SIDEWAYS, which is what circulating and being ejected both do.
#
# THE LAW: you cannot put a hole in a banked wall without either a cliff
# at its edge or a swale big enough to swallow the bank. FAIR_KEEP only
# fairs levels 1..4; levels 5+ stand full height, so the cut edge at
# level 5..6 was an unfaired 2.5 m face with a hole behind it. The lintel
# is not decoration - it is what makes the cut edge continuous surface
# instead of a rim to catch on.
#
# Headroom therefore has to come from ARCHING the soffit (lift the
# garage columns' level 5..7 nodes so the surface stays unbroken and
# merely bulges upward over the doorway), not from removing it. That
# needs one shared arch function sampled by BOTH the cage columns and
# build_mouth_shelf's outer rows - the shelf tucks under level 5 at
# r 17.867 and would otherwise tear open - plus a live entry test.
# 8 (2026-08-12, b140 - the state-swap): every lintel quad is out of the
# doorway window; only the 8->curl containment quad remains, its lower
# edge the level-8 ring (r 19.62, z 7.0) = 4.65 m of UNIFORM clearance
# over the threshold, no chord-fan taper. The b135 lesson ("you cannot
# put a hole in a banked wall") still stands - the hole is now legal
# because it only EXISTS while the mouth is open: while sealed, the
# extended mouth shelf carries the full pure-profile wall across the
# window (see shelf_drop), so a wall-riding car never meets a cut edge.
# The b135 wrecks happened because the shelf of that era stopped at
# r 17.867 and the sealed ride DID meet the hole. Open-state edge faces
# at cols 20/22 (z 4.9..7.0) remain reachable only by deliberately
# hooning up the flank bank of an idle machine and sailing out the
# window - flagged for live test, not probeable.
DOOR_CUT_LEVELS = 8
# Doorway-flank fairing (round 15 coda, camber-preserving since b93): the
# cut-edge bank columns are pulled toward the mouth deck by these
# per-level keep factors. ONE source of truth shared by three surfaces
# that must be flush to the millimetre: the collision cage's faired
# columns, the visual bank's faired sheet (build 95 - before that the
# visual stayed full height and cars riding the faired collision looked
# sunk INSIDE the bank: the player's "vehicles fall into entrance /
# mesh doesn't close up" screenshot), and the mouth-shelf door part
# whose raised top continues this exact profile across the doorway.
FAIR_KEEP = {1: 0.55, 2: 0.35, 3: 0.20, 4: 0.15}
# --- Doorway arch -----------------------------------------------------
# THE HEADROOM FIX, done the way law 14 says it has to be done. The
# lintel (BANK_PROFILE levels 5..8 carried across the doorway) pinches
# the entrance to 2.53 m, which stops anything taller than a car. It
# cannot be CUT - that leaves an unfaired cliff at the cut edge and cars
# get stuck on it (b135, reverted same day). So it gets LIFTED instead:
# the surface stays unbroken and merely bulges upward over the mouth,
# like a velodrome's banking swooping over a tunnel portal.
#
# Half-width is ONE cage column, and that number is a VISIBILITY
# boundary, not a styling knob. The b138 arch used two columns on the
# theory that "the doorway columns are already cut away" - wrong: the
# visual cut window is 257..283 deg, i.e. columns 20-21 ONLY. A +-25.7
# deg arch therefore lifted a full column of VISIBLE bank on each flank,
# and the player got a textureless grey dune swallowing the hazard band
# ("the entrance ... doesn't conform visually with the rest of the
# inside wall"). At +-12.857 deg the weight is exactly zero at node
# columns 20 (257.14) and 22 (282.86), and the visual bank's nearest
# retained cells end at 256.875/283.125 - so EVERY lifted vertex lies
# inside the already-invisible sector. The arch exists only in
# collision; the interior reads exactly as the accepted baseline.
#
# The soffit is therefore a chord fan (nodes at 257.14 / 270 / 282.86):
# 4.92 m clear at the lane centre, 4.15 m at the edges of a 2.6 m-wide
# vehicle box, tapering to the old 2.52 m at the jambs. Tall vehicles
# fit down the middle, which is where the ramp feeds them anyway.
#
# The CLOSED state carries none of this: the mouth shelf and the door
# leaf stay pure BANK_PROFILE (seamless-closure law, build 101), so the
# sealed spinning drum is still an unbroken velodrome. That leaves a
# closed-state pocket between the shelf top and the arched soffit -
# unreachable: orbits live at r 14..16.8 and the pocket starts at
# r 17.35 above z 4.9.
#
# RETIRED (2026-08-12, b140): DOOR_ARCH_LIFT = 0.0, permanently. The
# b139 arch passed every static probe and failed live in a dozen
# rotations: the player's car "instantly snapped to the ceiling above
# the entrance and got stuck". Root cause is geometric and absolute -
# LIFTING A LEANING WALL MOVES ITS FACE INBOARD AT FIXED HEIGHT. The
# bank leans ~50 deg, so +2.4 m of lift shoves the riding face up to
# ~1.8 m toward the drum centre through the band z 5..7, and the lifted
# curl (8.8 -> 11.2) becomes an overhanging pocket directly over the
# mouth: a wall-riding car crossing the sector gets rammed inboard at
# wall speed, pitched up the warp, and pinned into the pocket by the
# field. No arch shape avoids this; an arch and a wall-riding sealed
# state are mutually exclusive.
#
# The needs are DISJOINT IN TIME, which is the actual fix (b140):
# headroom only matters while the mouth is OPEN; pure wall only matters
# while SEALED. So the doorway's static lintel is gone entirely
# (DOOR_CUT_LEVELS = 8: only the 8->curl containment quad spans the
# window, lower edge z 7.0 = 4.65 m of uniform clearance), and the
# SEALED coverage comes from the mouth shelf extended to the rim at
# pure BANK_PROFILE - the machinery built for exactly this state swap.
DOOR_ARCH_LIFT = 0.0
DOOR_ARCH_HALF_DEG = 360.0 / WALL_SEGMENTS            # 12.857 deg
# R0 is the radius the lift starts from, and it is a SAFETY number, not a
# styling one. At 16.275 (level 2) the ramp reached down into the driving
# band: it lifted the faired flank columns' low levels, and the doorway-
# edge azimuthal step went 0.303 -> 0.562 m at r 17.5 - the same
# get-stuck mechanism as the b135 cut, just smaller. At 17.35 (level 4)
# the lift is confined to the lintel band above the drivable bank, the
# low-level steps stay at their pre-arch values, and the mouth shelf's
# closed-state swale is untouched where cars actually circulate (orbits
# r 14..16.8). The trade is a steeper lip at the very top of the banking
# over the mouth, which is what you would build there anyway.
DOOR_ARCH_R0 = 17.350                                 # level 4 radius
DOOR_ARCH_R1 = 17.887                                 # level 5, the soffit


def door_arch(az_deg: float, radius: float) -> float:
    """Vertical lift of the doorway lintel at (azimuth, radius), metres.

    Sampled by the collision cage's bank columns and by the visual
    bank's z_remap - where it evaluates to zero on every visible vertex
    BY CONSTRUCTION (the window ends inside the visual cut; see the
    half-width note above). build_mouth_shelf deliberately does NOT
    sample it: the closed mouth must stay pure BANK_PROFILE.
    """
    if DOOR_ARCH_LIFT <= 0.0 or radius <= DOOR_ARCH_R0:
        return 0.0
    import math as _math
    d = abs(((az_deg - 270.0) + 180.0) % 360.0 - 180.0)
    if d >= DOOR_ARCH_HALF_DEG:
        return 0.0
    w = 0.5 * (1.0 + _math.cos(_math.pi * d / DOOR_ARCH_HALF_DEG))
    s = min((radius - DOOR_ARCH_R0) / (DOOR_ARCH_R1 - DOOR_ARCH_R0), 1.0)
    s = s * s * (3.0 - 2.0 * s)
    return DOOR_ARCH_LIFT * w * s
# The mouth deck datum the fairing scales toward. The cage computes its
# own deck_ref from the ramp blend and asserts it equals this constant;
# the visual and the shelf use the constant directly.
FAIR_DECK_Z = 2.48


def faired_bank_z(radius: float) -> float:
    """Faired swale height at ``radius``: the bank profile with FAIR_KEEP
    applied at levels 1-4, linear between level radii, full profile at and
    beyond level 5. This IS the doorway crossing surface (collision, visual
    and shelf all sample it)."""
    knots = []
    for level, (r, z) in enumerate(BANK_PROFILE):
        keep = FAIR_KEEP.get(level, 1.0)
        knots.append((r, FAIR_DECK_Z + (z - FAIR_DECK_Z) * keep))
    if radius <= knots[0][0]:
        return knots[0][1]
    for (r0, z0), (r1, z1) in zip(knots, knots[1:]):
        if radius <= r1:
            t = (radius - r0) / (r1 - r0)
            return z0 + (z1 - z0) * t
    return knots[-1][1]


LIP_GAP_SEGMENTS = set()
RAMP_HALF_W = 2.2
# High enough that a car riding the rim curl (z ~4.6 + body) clears it.
BOOM_PIVOT = (0.0, 0.0, 6.4)
CONSOLE_X = 21.6
# Dial sits in a raised binnacle on the pedestal top (round 14); the
# needle part still spins about +Z, so the gauge stays horizontal.
DIAL_PIVOT = (21.6, 0.15, 2.02)

# Interactive console buttons (cannon-wash recipe): caps on the console's
# -Y face, walkable from the spiral entry side. Authored positions; the
# cage grows matching anchor + frame nodes and the jbeam gains triggers2.
# Round 14 (player 2026-08-08): "a real control panel for a centrifuge" -
# pedestal cabinet, gauge binnacle with glass, an E-STOP mushroom, RPM
# up/down pair, and a guarded PURGE that ejects everything in the bowl.
# Positions are the VISUAL cap centres on the front plate (y -0.70 face);
# the cage anchors, triggers2 click boxes and the Blender caps all render
# from this one table (car-wash calibration lesson: one source or the
# click boxes drift off the paint).
# Panel grid (relaid 2026-08-09h, player: "lower the HYPER-G DRUM CONTROL
# black faceplate ... to give room to the field coupling and controls and
# labels ... a better visual indicator of how much of an adjustment we've
# made"). The graphite plate now drops 0.20 m into the cream apron it was
# floating above (bottom 0.745 -> 0.545), and the freed band carries the
# field-coupling instrument: each control is a MINUS cap, a five-segment
# lit bar graph, and a PLUS cap on one line, sub-headed and scale-marked.
#   z 1.563  TITLE
#   z 1.375  START / E-STOP / PURGE      (labels z 1.200)
#   z 1.055  RPM+ / RPM- at the plate edges (labels z 0.960)
#            FIELD COUPLING header centred between them
#   z 0.855  WALL ADHESION / FIELD DRAG sub-heads
#   z 0.755  [-] [bar 5 seg] [+] per control
#   z 0.665  MIN / NOM / MAX scale marks + the cap's own - / + glyph
# Cap radii for clearance maths: estop 0.125, purge 0.11, green 0.088,
# white 0.063, small 0.041.
_BAR_Z = 0.755
_ADH_BAR_X0, _DRG_BAR_X0, _BAR_PITCH = 21.00, 21.86, 0.070
PANEL_BUTTONS = (
    {"id": "btn_start", "title": "Centrifuge: Start Protocol",
     "position": (20.98, -0.70, 1.375), "cap": "round_green",
     "label": "START", "label_z": 1.200, "label_scale": 0.8},
    {"id": "btn_stop", "title": "Centrifuge: EMERGENCY STOP",
     "position": (21.60, -0.70, 1.375), "cap": "estop",
     "label": "E-STOP", "label_z": 1.200, "label_scale": 0.8},
    {"id": "btn_purge", "title": "PURGE: Eject Bowl Contents",
     "position": (22.22, -0.70, 1.375), "cap": "purge",
     "label": "PURGE", "label_z": 1.200, "label_scale": 0.8},
    {"id": "btn_faster", "title": "Drum RPM: Increase (Manual Hold)",
     "position": (20.92, -0.70, 1.055), "cap": "round_white",
     "label": "RPM +", "label_z": 0.945},
    {"id": "btn_slower", "title": "Drum RPM: Decrease (Manual Hold)",
     "position": (22.28, -0.70, 1.055), "cap": "round_white",
     "label": "RPM -", "label_z": 0.945},
    # Field coupling: caps bracket their own bar graph, so the cap print
    # is just the sign - the bar and its sub-head carry the meaning.
    {"id": "btn_adh_down", "title": "Wall Adhesion: Decrease",
     "position": (20.86, -0.70, _BAR_Z), "cap": "round_small",
     "label": "-", "label_z": 0.665, "label_scale": 0.9},
    {"id": "btn_adh_up", "title": "Wall Adhesion: Increase",
     "position": (21.42, -0.70, _BAR_Z), "cap": "round_small",
     "label": "+", "label_z": 0.665, "label_scale": 0.9},
    {"id": "btn_drag_down", "title": "Field Drag: Decrease",
     "position": (21.72, -0.70, _BAR_Z), "cap": "round_small",
     "label": "-", "label_z": 0.665, "label_scale": 0.9},
    {"id": "btn_drag_up", "title": "Field Drag: Increase",
     "position": (22.28, -0.70, _BAR_Z), "cap": "round_small",
     "label": "+", "label_z": 0.665, "label_scale": 0.9},
)
PANEL_FRAME_X = (22.9, -0.70, 1.38)
PANEL_FRAME_Y = (21.02, -0.70, 2.0)

# Console legend plate frame (round 15, player: "professionally and
# realistically labeled"): 1.9 m wide, now 1.15 m tall (2026-08-09h) and
# centred at x 21.6, z 1.12. Label (u, v) live in the plate face's own
# 0..1 frame, v UP from the plate bottom; a button may pin its label to
# an explicit world z (label_z) instead of the default drop below the cap.
_PLATE_X0, _PLATE_W = 20.65, 1.9
_PLATE_Z0, _PLATE_H = 0.545, 1.15
# The five bar segments per gauge live at these world x/z; the runtime
# lights segment i while the level is >= i, so the print, the geometry
# and the Lua all index the same ladder.
BAR_SEG_Z = _BAR_Z
BAR_SEG_X = {
    "adh": tuple(round(_ADH_BAR_X0 + _BAR_PITCH * i, 4) for i in range(5)),
    "drag": tuple(round(_DRG_BAR_X0 + _BAR_PITCH * i, 4) for i in range(5)),
}
# Where each gauge's factory setpoint sits on its own ladder (see the
# adh/drag step tables in onButtonPressed). BOTH are the middle segment:
# the ladders are logarithmic rather than linear precisely so a centred
# nominal can still reach a genuinely loose setting - and a bar that
# reads 3-of-5 at rest makes "how far have I moved it" a glance.
BAR_NOM_INDEX = {"adh": 3, "drag": 3}


def _u(x):
    return round((x - _PLATE_X0) / _PLATE_W, 4)


def _v(z):
    return round((z - _PLATE_Z0) / _PLATE_H, 4)


PANEL_LEGEND_LABELS = [
    [_u(b["position"][0]),
     _v(b["label_z"]) if "label_z" in b
     else round(_v(b["position"][2]) - b.get("label_dv", 0.145), 4),
     b["label"], b.get("label_scale", 1.0)]
    for b in PANEL_BUTTONS
] + [
    [0.5, _v(0.955), "FIELD COUPLING", 1.0],
    [_u(21.14), _v(0.855), "WALL ADHESION", 0.72],
    [_u(22.00), _v(0.855), "FIELD DRAG", 0.72],
] + [
    # MIN / NOM / MAX under each bar - NOM sits on the segment that is
    # the machine's designed setpoint, so "how far have I moved it" is
    # readable without counting.
    [_u(x), _v(0.665), text, 0.55]
    for gauge, lo, hi in (("adh", "MIN", "MAX"), ("drag", "MIN", "MAX"))
    for x, text in (
        (BAR_SEG_X[gauge][0], lo),
        (BAR_SEG_X[gauge][BAR_NOM_INDEX[gauge] - 1], "NOM"),
        (BAR_SEG_X[gauge][4], hi),
    )
]

PALETTE = {
    f"{MOD_ID}_drum_steel": {
        "texture": {"family": "steel_worn"},
        "color": [0.5, 0.53, 0.57, 1.0],
        "metallic": 0.8,
        "roughness": 0.4,
        # Double-sided: the banked wall must read from inside the bowl AND
        # from above/outside (round 5: single-sided made the near half of
        # the wall-ride surface invisible from oblique angles; the actual
        # "lid" was the shell cylinder's end cap, fixed in round 4).
        "double_sided": True,
    },
    f"{MOD_ID}_bank_hazard": {
        "texture": {"family": "hazard_chevron"},
        "color": [0.95, 0.75, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
    },
    f"{MOD_ID}_floor_concrete": {
        # fine mode: this family also skins the vault walls, the concourse
        # deck and the entry plaza at arm's length, where the legacy texel
        # pits rendered as grey confetti blocks (player 2026-08-08).
        # 1024 -> 2048 (2026-08-10, player green-outlined the concourse
        # deck AGAIN): this is the largest surface set in the mod and it
        # is laid at a multi-metre tile, so 1024 gave it the LOWEST texel
        # density anywhere on the prop - roughly a quarter of the console
        # plate's. The b126 basis fix removed the lattice and added real
        # aggregate; the resolution is what lets that aggregate survive
        # being stretched over a 20 m floor instead of blurring back into
        # the flat wash it replaced.
        "texture": {"family": "concrete", "params": {"fine": 1.0},
                    "size": 2048},
        "color": [0.62, 0.6, 0.57, 1.0],
        "metallic": 0.0,
        "roughness": 0.85,
    },
    f"{MOD_ID}_console_cream": {
        "texture": {
            "family": "painted_metal",
            "params": {"base": [0.88, 0.85, 0.76], "rough": 0.4},
        },
        "color": [0.88, 0.85, 0.76, 1.0],
        "metallic": 0.1,
        "roughness": 0.4,
    },
    f"{MOD_ID}_pylon_dark": {
        "texture": {"family": "bakelite"},
        "color": [0.09, 0.08, 0.08, 1.0],
        "metallic": 0.2,
        "roughness": 0.5,
    },
    f"{MOD_ID}_needle_red": {
        "color": [0.85, 0.1, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.4,
    },
    f"{MOD_ID}_dial_white": {
        "color": [0.94, 0.93, 0.88, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_beacon_amber": {
        "color": [1.0, 0.62, 0.1, 1.0],
        # THREE components, not four (2026-08-15, round 18). This factor was
        # [1.0, 0.55, 0.08, 1.0] and therefore rendered COMPLETELY INERT - the
        # beacon lenses have been dark since the day they were modelled. See
        # AGENTS.md "Round-16/17: the photometric ledger" and
        # prop_builder.check_emissive_factor, which now refuses to build a
        # four-element factor at all. The hue is unchanged; only the alpha
        # (which emissiveFactor never had) is gone.
        "emissive": [1.0, 0.55, 0.08],
        "metallic": 0.0,
        "roughness": 0.3,
        # 1800 nit, the top of the measured near-linear band. A hazard beacon
        # is the one thing in this prop that has to be conspicuous IN
        # DAYLIGHT, and 1800 is where the noon curve reads +75.7 sRGB over an
        # unlit control ("unmistakable" starts at 800). Night clips - which is
        # correct here and nowhere else in this palette: a real rotating
        # beacon IS a blown-out point after dark, and the measured bloom
        # (screen-space, starts only at saturation, gone by 21 px at this
        # rung) gives it the small halo a beacon should have.
        "stage": {"emissiveIntensityNits": 1800},
    },
    f"{MOD_ID}_ramp_steel": {
        "texture": {
            "family": "painted_metal",
            "params": {"base": [0.55, 0.58, 0.6], "rough": 0.5},
        },
        "color": [0.55, 0.58, 0.6, 1.0],
        "metallic": 0.3,
        "roughness": 0.5,
    },
    f"{MOD_ID}_paint_white": {
        "color": [0.92, 0.92, 0.9, 1.0],
        "metallic": 0.0,
        "roughness": 0.6,
    },
    f"{MOD_ID}_obs_glass": {
        "color": [0.55, 0.72, 0.78, 0.28],
        # Cyan emissive (player 2026-08-08): the vision bands and oculi
        # read as lit-from-within after dark, so the drum glows.
        #
        # "First cut used 0.10-0.26 and the night facade rendered pitch black
        # - BeamNG's night tonemap needs HDR-ish factors before a surface
        # reads as a light source at distance." RETIRED 2026-08-15 (round 18):
        # the facade was pitch black because this factor had FOUR components
        # and four is inert at ANY magnitude. Raising 0.26 to 0.9 changed
        # nothing and could not have; the fourth element was the whole defect
        # (AGENTS.md, Round-16/17 photometric ledger).
        "emissive": [0.45, 0.75, 0.9],
        "metallic": 0.0,
        "roughness": 0.08,
        "transparent": True,
        # 180 nit, DELIBERATELY the dimmest rung in this palette, because this
        # is the largest emissive AREA on the prop - the whole vision band and
        # every oculus. Measured night response at 180 is sRGB 213 with 0.00%
        # of pixels clipped, so the glass keeps its modelling and the drum
        # reads lit-from-within rather than as a white wall; 400 and up clips
        # to flat white. At noon it lands at +11.9 sRGB over control, which on
        # 0.28-alpha glass is the faint interior lift it should be.
        "stage": {"emissiveIntensityNits": 180},
    },
    # CHIEF facility design language (2026-08-05 rebuild): white flowing
    # shell, terracotta louvers, waffle vault, blue rotor.
    f"{MOD_ID}_shell_white": {
        "color": [0.92, 0.93, 0.94, 1.0],
        "metallic": 0.15,
        "roughness": 0.38,
        "double_sided": True,
    },
    # Entry marquee (player 2026-08-08): backlit cabinet sign over the
    # canopy. Light diffuser field, royal-blue silhouette lettering
    # rendered into the colour map by the "marquee" texture family; the
    # uniform emissive lights the panel at night so the letters read as
    # silhouettes - a true backlit sign with no extra plumbing. Royal
    # blue ties it to the rotor/spoke blues; the graphite frame is built
    # in louver_facade.
    f"{MOD_ID}_marquee": {
        # Cabinet panel. Was DARK graphite (round 15 coda) so the white
        # letter backplates would be the only bright shapes on it.
        # 2026-08-11 the player asked for the FACE only - "the top and
        # bottom of the sign colour/texture is good in black" - to become
        # "a very fine piece of single piece of wood from a length of
        # tree finished to look both natural and luxurious". The frame
        # bands above and below are separate meshes on their own
        # material, so swapping this one key changes exactly the face and
        # leaves the black surround alone.
        #
        # The chrome channel letters still read against it: the wood is a
        # mid-tone warm brown (mean luma ~0.25) and the letters are
        # polished steel with white backplates, so the contrast is
        # comfortably higher than dark-letters-on-dark-panel ever was.
        #
        # A textured entry takes baseColorFactor from `tint` (default
        # white) and its roughness from the map, so "color"/"roughness"
        # below are inert here - the family carries both. Kept for
        # reference and in case the texture is ever dropped.
        "texture": {"family": "wood", "size": 2048},
        "color": [0.30, 0.17, 0.09, 1.0],
        "metallic": 0.0,
        "roughness": 0.22,
    },
    f"{MOD_ID}_letter_glow": {
        # Backplate glyphs behind the channel letters: bright near-white,
        # lifted at night by the (barely-visible) gap lights.
        #
        # "Emissive kept for any engine that ever honours it" - RETIRED
        # 2026-08-15 (round 18). THIS engine honours it; the factor was
        # [2.0, 2.05, 2.1, 1.0] and a four-element factor is inert, which is
        # the real reason build 79 rendered a black sign and the round-15
        # coda had to conclude "the b78 glowing rims were pool-lit".
        "color": [0.95, 0.96, 0.98, 1.0],
        # NORMALISED to max 1.0, hue untouched (2.0/2.1, 2.05/2.1, 1.0). The
        # old >1 magnitudes were reaching for brightness the factor is the
        # wrong control for: the factor TINTS and emissiveIntensityNits sets
        # the level, so a factor above 1 just multiplies the nits by a number
        # nobody can read off the material. Stock does the same.
        "emissive": [0.952381, 0.97619, 1.0],
        "metallic": 0.0,
        "roughness": 0.28,
        # 320 nit: the sign is a NIGHT problem and only a night problem. Its
        # daylight read already works and is not emissive at all - white
        # plates + the two distant floods give reverse-lit channel letters
        # (round 15 coda, unchanged by this). 320 is the brightest measured
        # rung that does not clip at midnight (sRGB 245, 0.00% clipped), so
        # the plates stay letter-SHAPED behind their dark channel letters
        # instead of fusing into one blown rectangle with a bloom halo, which
        # is exactly what 400+ would do to a sign this size.
        "stage": {"emissiveIntensityNits": 320},
    },
    f"{MOD_ID}_terracotta": {
        # Round 15 (player): the louver fins + piers get "the look and
        # feel and texture of copper metal" - dull worn-penny chosen over
        # shiny (aged architectural copper cladding suits the steel/glass
        # language; mirror copper reads as a toy at building scale). The
        # material NAME stays terracotta so the 144 fin + pier
        # assignments and DAE slots are untouched; the family swap plus
        # the metallic factor do the conversion. Maps are written in
        # display space - base is the sRGB penny albedo.
        "texture": {
            "family": "copper",
            "params": {"base": [0.545, 0.30, 0.195], "rough": 0.5},
            "size": 1024,
        },
        "color": [0.55, 0.30, 0.20, 1.0],
        "metallic": 0.85,
        "roughness": 0.5,
    },
    # Dark spandrel glass for the recessed curtain-wall band. pylon_dark's
    # bakelite family read as matte black plastic; this is near-mirror
    # smooth so it takes a crisp specular streak, but metallic stays low:
    # at 0.18 the band mirrored so much sky that the shadow reveal behind
    # the fins went pale and the louver rhythm lost its contrast.
    # NB colour here is LINEAR (no texture map -> baseColorFactor is the
    # authority); 0.10/0.12/0.14 linear renders as a 40%-grey wall, which
    # is why the reveal went pale. 0.028/0.034/0.040 lands on ~22% display:
    # dark glass, not a matte void.
    f"{MOD_ID}_spandrel_glass": {
        "color": [0.028, 0.034, 0.04, 1.0],
        "metallic": 0.05,
        "roughness": 0.1,
    },
    # PURE MIRROR GLAZING for the two horizontal vision bands that ring the
    # facade (player 2026-08-10: "update the horizontal outside glass strips
    # ... to a pure mirror glass reflective look"). Modelled on the game's
    # own `generic_chrome` (vehicles/common/generic_mat_tex): a metallic-1,
    # roughness-0 OPAQUE surface plus dynamicCubemap - not a transparent
    # glass shader. That distinction is the whole trick and it is why this
    # is safe to do now. Round 15 tried the stock vehicle `glass` material
    # by name for a real cubemap; its shader is tuned for car-sized panes
    # and at building scale it produced the mirrored-windows ARTIFACT the
    # player rejected in b99 (fixed then by falling back to obs_glass). A
    # plain PBR chrome has no glass shader to misbehave - it just reflects
    # the probe - so the mirror look arrives without the artifact.
    #
    # dynamicCubemap true is BeamNG's standard PBR reflection-probe binding
    # (905 uses in vehicles/common alone). NOTE: `alphaType` does NOT exist
    # in BeamNG material data (0 occurrences across the stock vehicle set -
    # it is a glTF/Godot spelling); opacity is expressed by the Stage's
    # opacityFactor plus translucent/translucentBlendOp, which is what the
    # engine actually reads.
    #
    # ROUGHNESS 0.0 DID NOT SURVIVE CONTACT (2026-08-10, player: "the
    # reflection chrome glass looks bad, the reflection looks blocky").
    # My prediction that an opaque chrome would dodge the b99 artifact was
    # WRONG, and for a reason that has nothing to do with the shader: the
    # reflection source is BeamNG's per-vehicle dynamic cubemap, which is
    # sized for a car. Stretched across a 47 m drum, each of its texels
    # covers most of a metre, and at roughness 0 the surface resolves them
    # individually - blocks of sky, ground and building with hard edges.
    # A mirror can only be as sharp as its probe.
    #
    # So: keep the metal (that part was right - no transparent glass
    # shader misbehaving), but give roughness enough to pull a blurrier
    # cubemap mip, and tint it. Real architectural mirror glazing is a
    # dark cool grey that returns a SHEEN, not a photograph; the darker
    # base also stops the reflection from being the loudest thing on the
    # facade. If the player wants the hard mirror back, the knob is
    # roughness - but it cannot be sharper than the probe.
    f"{MOD_ID}_mirror_glass": {
        "color": [0.42, 0.47, 0.55, 1.0],
        "metallic": 0.9,
        "roughness": 0.22,
        "stage": {"opacityFactor": 1.0},
        "material": {
            "dynamicCubemap": True,
            "translucent": False,
            "translucentBlendOp": "None",
            "castShadows": True,
        },
    },
    # Dark graphite plinth steel. drum_steel (0.5/0.53/0.57) was invisible
    # against grey ground; this reads as a base course at any distance.
    f"{MOD_ID}_facade_steel": {
        "texture": {
            "family": "steel_worn",
            "params": {"base": [0.26, 0.27, 0.3], "rough": 0.35},
        },
        "color": [0.26, 0.27, 0.3, 1.0],
        "metallic": 0.75,
        "roughness": 0.35,
    },
    f"{MOD_ID}_waffle_white": {
        "color": [0.96, 0.96, 0.95, 1.0],
        "metallic": 0.0,
        "roughness": 0.85,
        "double_sided": True,
    },
    f"{MOD_ID}_rotor_blue": {
        "color": [0.07, 0.14, 0.44, 1.0],
        "metallic": 0.2,
        "roughness": 0.25,
    },
    f"{MOD_ID}_rotor_white": {
        "color": [0.93, 0.94, 0.96, 1.0],
        "metallic": 0.25,
        "roughness": 0.25,
    },
    # LINEAR, like spandrel_glass: no texture family means baseColorFactor
    # is the authority. [0.88, 0.42, 0.05] linear resolves to ~#F2AE3D
    # display -- sand/apricot, not the brief's ORANGE gantry crane.
    # [0.72, 0.14, 0.01] lands on ~#DD6919: safety orange at hall scale.
    f"{MOD_ID}_crane_orange": {
        "color": [0.72, 0.14, 0.01, 1.0],
        "metallic": 0.1,
        "roughness": 0.45,
    },
    f"{MOD_ID}_spoke_blue": {
        "color": [0.1, 0.22, 0.58, 1.0],
        "metallic": 0.15,
        "roughness": 0.4,
    },
    f"{MOD_ID}_track_grey": {
        "color": [0.64, 0.66, 0.68, 1.0],
        "metallic": 0.35,
        "roughness": 0.45,
        # The door leaf is a single swept surface with the tunnel below it,
        # so it has to read from underneath as well as from the deck.
        "double_sided": True,
    },
    # Raceway asphalt for the drivable cone (player: "the main track
    # appears to be invisible, it should be a raceway"). Dark, matte, with
    # painted lane lines laid over it.
    f"{MOD_ID}_track_asphalt": {
        # NO texture family ON PURPOSE. Every shipped material in this pack
        # carries COOKED .dds maps; a newly-added family only produced raw
        # .png, and since a mapped material sets baseColorFactor to white
        # and defers to the map, the cone rendered WHITE in-engine while
        # looking correct in Blender (player: "the track is missing").
        # Textureless -> baseColorFactor IS the colour, always visible.
        "color": [0.20, 0.21, 0.23, 1.0],
        "metallic": 0.0,
        "roughness": 0.92,
        # Double-sided: the cone is a single sheet with open air beneath it,
        # so backface culling made the whole deck VANISH from any eye below
        # the deck plane - leaving the blue spokes and lane lines floating
        # over the pale concrete apron. Same reason drum_steel carries it.
        "double_sided": True,
    },
    f"{MOD_ID}_lane_paint": {
        "color": [0.93, 0.93, 0.90, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
    },
    # High-tech interior lighting (textureless so they always render).
    f"{MOD_ID}_beacon_cyan": {
        "color": [0.35, 0.85, 1.0, 1.0],
        # Three components (2026-08-15, round 18) - was [.., 1.0] and inert.
        # See beacon_amber above for the law and the reasoning.
        "emissive": [0.45, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.25,
        # 1800 nit, matching beacon_amber: same fixture class, same job.
        "stage": {"emissiveIntensityNits": 1800},
    },
    f"{MOD_ID}_light_panel": {
        # Pale-blue fixture glow (player 2026-08-08): the vault cans'
        # diffuser discs read as cool-blue luminaires and the bowl gets a
        # matching PointLight (behavior.init) so the interior is actually
        # lit at night, with the discs reading as its source.
        "color": [0.88, 0.94, 1.0, 1.0],
        # "1.1-1.6 read as unlit plastic on the player's build (round 15
        # screenshot); lamp-strength HDR so the discs read as sources."
        # RETIRED 2026-08-15 (round 18): 1.1-1.6 read as unlit plastic because
        # the factor had FOUR components, and so did the 1.5-2.2 that replaced
        # it. Both were inert. Normalised to max 1.0 (hue preserved, /2.2) with
        # the level moved to nits, per the letter_glow note.
        "emissive": [0.681818, 0.840909, 1.0],
        "metallic": 0.0,
        "roughness": 0.2,
        # 800 nit - a diffuser disc, so it is allowed to blow out after dark
        # the way a real luminaire does, and at noon it is +44.5 sRGB over
        # control ("unmistakable") which is what the round-15 screenshot was
        # asking for when it called these unlit plastic. These discs also
        # carry a matching PointLight (behavior.init) and that division of
        # labour is unchanged: emissive makes the disc LOOK like the source,
        # the PointLight is the only thing that actually lights the bowl.
        "stage": {"emissiveIntensityNits": 800},
    },
    f"{MOD_ID}_panel_legend": {
        # Engraved legend plate for the console (round 15): brushed
        # near-black field, machined frame, white title + a label under
        # each cap. Label (u, v) computed from PANEL_BUTTONS so the print
        # can never drift from the caps it annotates.
        "texture": {
            "family": "panel_legend",
            "params": {
                "labels": PANEL_LEGEND_LABELS,
                "title": "HYPER-G DRUM CONTROL",
                # 1.9 x 1.15 m plate (2026-08-09h). Type sizes are given
                # as fractions of PLATE height and were dropped in step
                # with the taller plate so the print stays ~0.067 m tall
                # in world - the extra 0.20 m is label room, not bigger
                # letters.
                "aspect": round(_PLATE_W / _PLATE_H, 4),
                "title_scale": 0.068,
                "label_scale": 0.068 * 0.853,
            },
            # 1024 -> 2048 (2026-08-10, player: "the control panel seems
            # to be blurry all of a sudden"). It was, and I caused it in
            # b121: the plate grew 0.95 -> 1.15 m while the map stayed
            # 1024, dropping vertical texel density 1078 -> 890 px/m, and
            # the type scale dropped with the plate so the letters lost
            # another 23% of their texels on top. A 2048 map more than
            # restores both. LAW: a legend map's real resolution is
            # px / PLATE METRE, not px - growing the plate silently
            # blurs the print.
            "size": 2048,
        },
        "color": [0.055, 0.06, 0.068, 1.0],
        "metallic": 0.25,
        "roughness": 0.4,
    },
    f"{MOD_ID}_btn_green": {
        "color": [0.12, 0.68, 0.22, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_btn_white": {
        # RPM pair (2026-08-09g relayout): white caps, distinct from the
        # blue coupling cluster and the traffic-light top row.
        "color": [0.88, 0.89, 0.91, 1.0],
        "metallic": 0.0,
        "roughness": 0.3,
    },
    f"{MOD_ID}_btn_red": {
        "color": [0.82, 0.12, 0.1, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_btn_blue": {
        "color": [0.12, 0.3, 0.85, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_btn_orange": {
        "color": [0.95, 0.55, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
}

# EVERY material renders both sides. Single-sided materials have now shipped
# an invisible ramp, an invisible door leaf, and a see-through under-bank
# cavity - each one invisible in-game while passing every Blender check,
# because Blender does not backface-cull and BeamNG does. Per-surface fixes
# kept missing the next surface (the player prompted over a dozen times).
# The overdraw cost on a single prop is negligible; the bug class is not.
for _palette_entry in PALETTE.values():
    _palette_entry["double_sided"] = True
del _palette_entry

TRIGGERS = {
    # The whole bowl interior; Overlaps because a car being shredded at
    # 2000 g is never fully contained by anything.
    "drum_zone": {
        "mode": "Overlaps",
        # GENEROUS on purpose, round 2 (b90 forensics): the July lesson
        # ("a 15.2 m box flapped enter/exit four times per lap and
        # tripped the abandon path") recurred at the next radius up -
        # at ~350 RPM the sample rides the CREST orbit (r ~19.9, z 7.6)
        # and a 40 m box clipped it at the cardinals, aborting the
        # protocol mid-ladder. The box must contain the crest orbit
        # PLUS a car's OOBB at every azimuth: 46 x 46 x 11. False
        # corner-arming is still prevented by the insideBowl radial
        # gate (r <= 24), not by shrinking this box.
        "center": [0.0, 0.0, 4.6],
        "dimensions": [46.0, 46.0, 11.0],
    },
    "rim_zone": {
        "mode": "Overlaps",
        "center": [0.0, -22.5, 1.6],
        "dimensions": [10.0, 9.0, 3.4],
    },
}

EFFECTS = {
    # NO particle effects at all (round 15 finale, player: "remove the
    # particle effects at any RPM"). spin_dust went first (cream plume on
    # machined steel = rendering glitch); hub_smoke followed - its white
    # puff ballooned over the rotor dome and read as a giant glowing
    # blob, not machinery strain.
}

BEHAVIOR = {
    "camera_distance": 64.0,
    "spin_center": [0.0, 0.0, 2.0],
    # RPM plateaus with escalating taunts; the field caps what physics
    # sees, the dial happily reads all five hundred.
    # Twelve plateaus at 5.5 s each = 60.5 s from the first gentle carousel
    # to the top of the ladder (player: "ramp up from slow to the fastest
    # speed it's capable, roughly one minute"). Six stages at 5 s topped
    # out in 25 s, which read as a jump rather than a build.
    "rpm_stages": [
        10.0, 25.0, 45.0, 70.0, 100.0, 135.0,
        175.0, 220.0, 275.0, 340.0, 415.0, 500.0,
    ],
    # Calibrated live, not derived: the hold is only one term per rung (the
    # RPM ramp and the wall-speed cap ramp each reset stageTimer first), so
    # the relationship is affine, not proportional: t500 = 9.67 + (11/3) *
    # hold sim-seconds (11 inter-stage holds over the dtSim ~3x factor).
    # MEASURED end-to-end 2026-08-08 once the empty-bowl abort was removed
    # (before that, t500 had only ever been extrapolated - every run died
    # at the ejection): hold 14.0 -> 500 RPM at t = 61.0 s, one second past
    # the player's "tops out at 500 by the 60 second mark". 13.0 lands it
    # at ~57.3 s. Re-measure if the ladder length, rpm_ramp_per_s or
    # cap_ramp_mps2 change.
    # Raised 13.0 -> 15.5 with the round-15 continuous ramp: the hold
    # clock now runs from stage ENTRY (the climb fills 90% of it), so the
    # interval model is t500 ~ (11*hold + last_climb)/3 real seconds.
    # 15.5 lands ~59 s; re-measure via the probe rpm trace if the ladder
    # or rpm_ramp_fill changes.
    "stage_hold_seconds": 15.5,
    "rpm_ramp_per_s": 28.0,
    "rpm_ramp_fill": 0.9,
    "max_hold_seconds": 8.0,
    # Per-stage wall-speed targets. The dial reads RPM; physics gets a
    # tangential cap the banked wall + rim curl can actually react
    # (review 2026-07-23: raw omega*r demanded 25-135 g from an open
    # outward-leaning bank — cars exited over the rim at stage 2).
    # 45 m/s at r~9.5 is still ~22 g of scrubbing torture.
    # Twelve rungs matching rpm_stages, climbing to the field cap so the
    # last plateau really is the fastest the engine will carry a car.
    "stage_speeds_mps": [
        8.0, 14.0, 21.0, 30.0, 40.0, 51.0,
        63.0, 76.0, 90.0, 105.0, 120.0, 135.0,
    ],
    # The effective cap RAMPS toward the stage target (live run 2026-07-23:
    # jumping the cap at a stage boundary shoved the car to 14 m/s at
    # small radius — it spiralled out and ski-jumped off the bank). A real
    # centrifuge spins up gradually so the load stays seated on the wall.
    "cap_ramp_mps2": 4.5,
    # Raised from 115 so the top rung is not clipped: the player asked for
    # "the fastest speed it's capable". 135 m/s (486 km/h) at r~16 is about
    # 116 g - far past what any bank can hold, which IS the torture test.
    "field_speed_cap_mps": 140.0,
    "drag_rate": 3.5,
    "frame_dv_cap": 6.0,
    # --- Round 15 phys-safety block (player: stretched black polygon
    # lines = physics node explosions). REVERTIBLE by design:
    # safety_enabled False restores exact pre-round-15 behavior, and each
    # threshold tunes independently. Context: the field was ALREADY
    # vehicle-gated (insideBowl), per-frame dv-capped (frame_dv_cap) and
    # applied to the ref-node cluster only (detached debris receives no
    # field energy, so the "force follows the breakaway part" runaway
    # cannot occur here). The real gaps were feeding a sample whose
    # motion is already insane, and never detecting node excursions.
    "safety_enabled": True,
    # Field skip for samples the map layer reports faster than this.
    "safety_skip_mps": 150.0,
    # Live-OOBB half-extent above this = a node excursion (no stock car
    # spans 40 m; one lost node inflates the box by hundreds).
    "safety_node_dist": 40.0,
    "safety_check_interval": 1.0,
    # Quarantine length after an excursion (dtSim seconds; ~1/3 real).
    "safety_release_seconds": 20.0,
    "min_radius": 2.4,
    # Interior gate: the field, arming, and abort only consider vehicles
    # actually inside the bowl (debris in the zone box must not count).
    # 24.0 -> 19.5 (2026-08-10 audit blocker). insideBowl is the predicate
    # interiorCount uses to decide "a sample is aboard", and at 24 m it
    # reached far past the drum wall and swallowed the ENTRANCE RAMP -
    # whose deck the cage puts at r 19.91..23.96 - plus the rim greeting
    # zone. A player parked on the ramp to watch therefore counted as a
    # sample: the mouth sealed in their face, the ladder's completion
    # fired an eject for a car that was not in the drum, the eject's own
    # `remaining` count (which reads drum_zone, and drum_zone does NOT
    # contain the ramp) returned 0 so the throw ended without launching,
    # needEmpty latched, and the 40 s eject timeout volcanoed them at
    # ~50 m/s. Two constraints bound the value: strictly ABOVE everything
    # drivable inside the drum (the bank tops out at r 17.9 - the mouth
    # shelf's outer row is 17.867), and strictly BELOW the ramp deck's
    # inner end at 19.91. 19.5 clears the bowl by 1.6 m and the ramp by
    # 0.41 m, and sits well inside drum_zone's 23 m half-extent so the
    # two occupancy authorities finally nest.
    "bowl_radius": 19.5,
    # Round 7 (player pinned at the door): auto-arm only once the sample
    # reaches mid-bowl; the doorway band stays force-free while idle.
    "arm_radius": 13.0,
    # Containment assist (2026-08-05 functional gate: a spun car slid out
    # through the vomitory gap at 18 m/s and reached r 52). The banked
    # wall geometry cannot be trusted alone at high tangential speed, so
    # the runtime applies an inward corrective while spinning: beyond
    # hold_radius the sample is pushed back toward the wall line.
    # Damage is beamstate.damage, published to the GE side every frame as
    # map.objects[id].damage. Scale reference from the game's own code:
    # traffic respawns at >=500, freeform delivery calls >1000 notable and
    # >5000 heavy. 4000 keeps "battered but drives" and rejects "wreck".
    # Only flavours the eject message now (intact vs remains) - EVERY
    # protocol ending goes out the mouth since the 2026-08-09 directive.
    "survive_damage_max": 4000.0,
    # --- MOUTH EJECT (player 2026-08-09: "spit the car at the speed it's
    # currently going out the front entrance"). Supersedes both prior
    # endings - the survivor self-drive unload AND the over-the-rim fling.
    # The drum bleeds to eject_speed_mps while the mouth opens (collision
    # bake deferred by the sector-clear gate), then each sample is
    # velocity-launched down the corridor centreline on the first tick it
    # sweeps into the doorway window, PRESERVING its current speed.
    # 34 m/s: fast enough to read as "spat", slow enough that the launch
    # window (the +/-12.8 deg bank cut) spans ~2 ticks of sweep and the
    # flat trajectory touches down on the exit ramp, not in the next county.
    "eject_speed_mps": 34.0,
    # NOT zero and NOT below 30: under 30 RPM the field drops outer-band
    # cars (door protection, applySpinField) and under 20 the stall purge
    # disarms - the eject needs both alive until every sample is out.
    "eject_rpm_floor": 30.5,
    # cos 10 deg. The bank cut spans +/-12.86 deg, but firing at its edge
    # from r >= 17.4 puts the CENTRE of the car within ~5 cm of the jamb
    # line at r 19.5 (worked geometry, 2026-08-09) - the corner clips.
    # +/-10 deg with the eject_max_r gate below restores ~0.8-1.0 m of
    # corner margin, and the 20 deg window still spans >= 1.6 ticks of
    # sweep at every reachable launch speed (<= ~14.3 deg/tick at 80 m/s,
    # r 16, dtSim 0.05), so a crossing cannot straddle-skip it.
    "eject_window_cos": 0.985,
    # Launch only from at-or-below the patch outer edge: the magnetic
    # hold pins the eject orbit near r 15.9-16.5 anyway, and a wide
    # slider at r 18+ aimed through the cut would shave the jamb. One
    # that never comes down is stall-purged or timeout-volcanoed.
    "eject_max_r": 17.0,
    # Corridor-centreline aim target distance. Aiming at a far centreline
    # point (not straight along the gate) converges an off-centre launch
    # toward the middle of the corridor: worst-case lateral at the jamb
    # line drops from 4.4 m (hugging) to ~3.4 m against a 4.45 m half-width.
    "eject_aim_dist": 34.0,
    # The open-endpoint collision bake is a GLOBAL swap: during eject it
    # may only land while every interior sample is >72 deg from the mouth,
    # so no car ever has the floor vanish mid-crossing.
    "eject_bake_clear_cos": 0.30,
    # TRAVEL GATE (red-team F1, 2026-08-09). The shelf's visual pose must
    # never LEAD its collision bake by more than the certified <=2 s
    # travel leg: any FOREIGN be:reloadCollision (another prop's cleanup
    # or endpoint bake, anything engine-side) re-bakes all TSStatics from
    # current transforms, so a long pose/collision divergence is an open
    # mouth waiting for someone else to make it real. The shelf therefore
    # stays CLOSED during eject until every interior sample is clear of
    # the sector AND predicted to stay clear for travel + margin; only
    # then does the burial start, with the instantaneous bake gate as the
    # arrival backstop. Prediction needs bled speed, which the eject
    # bleed guarantees within ~4 s. If phase-locked multi-car traffic
    # never opens a predicted window (~6% of 3-car phasings), fall back
    # to instantaneous-clear-only after eject_travel_fallback_s - the
    # bounded-window risk beats the guaranteed timeout volcano.
    "eject_travel_clear_s": 2.0,
    "eject_travel_fallback_s": 15.0,
    "eject_min_speed": 8.0,
    # Sim-seconds (~13 real; dtSim runs ~3x wall). If the mouth never
    # lines up (seized wreck, blocked bake) the machine volcanoes the
    # stragglers instead of jamming - the no-jam law from round 15.
    "eject_timeout": 40.0,
    # --- Idle doorway-squatter purge (player 2026-08-09 approach
    # screenshot: "the entrance seems partially closed"). A wreck parked
    # in the fall-interlock band pins the shelf raised and the leaf sealed
    # FOREVER at idle - every later approach finds a half-closed mouth.
    # Sim-seconds (~15/25 real): warn, then volcano the squatter.
    "door_squat_warn_s": 45.0,
    "door_squat_purge_s": 75.0,
    # Containment. hold_damp is the fraction of the sample's OUTWARD radial
    # velocity cancelled each frame once it drifts past hold_radius - that
    # is what actually pins it at 100+ g, because it is a velocity
    # constraint and not a force. hold_gain/hold_max_dv are the gentler
    # spring that walks it back to the hold line afterwards; hold_max_dv is
    # a PER-FRAME dv cap, so 30 never bound and the spring was the only
    # thing acting. Raised together so the top rungs are reachable.
    "hold_radius": 15.9,
    "hold_damp": 0.55,
    "hold_gain": 90.0,
    "hold_max_dv": 8.0,
    "bowl_along_min": -2.5,
    "bowl_along_max": 8.6,
    "estimate_sane_mps": 150.0,
    "spin_down_per_s": 90.0,
    "boom_visual_omega_cap": 11.0,
    "dial_sweep_deg": 270.0,
    "dial_max_rpm": 500.0,
    # Panel PURGE: clears wrecks/debris from the drum regardless of phase.
    # Also the eject-timeout and doorway-squatter fallback velocities.
    # (fling_* deleted 2026-08-09: the over-the-rim protocol fling is
    # superseded by the mouth eject.)
    "purge_up_mps": 40.0,
    "purge_out_mps": 30.0,
    # --- Rotating beacon LIGHTS (player 2026-08-09: "the orange parts on
    # this safety light should emit orange light ... light rays physically
    # spun around ... similar to how the cop lights work"). This used to
    # say "material emissive is INERT on this prop (proven at the sign
    # rounds)" - RETIRED 2026-08-15, round 17: this prop's emissiveFactor
    # arrays all have FOUR elements, which is what kills them; three emit.
    # Real lights are STILL correct here, because the player asked for the
    # lamp to EMIT LIGHT onto its surroundings and emissive illuminates
    # nothing. So the
    # glow is a real amber PointLight at the head and the rays are two
    # opposed SpotLights steered by beaconAngle every tick - the cop-bar
    # recipe, GE edition. Position mirrors interior_vault.BEACON_POS
    # (asserted in create_gforce_centrifuge at Blender time); z is the
    # pivot + 0.09 so the source sits inside the lens band of the head.
    # 2026-08-12: pivot rose to 10.245 with the housing-tower fix (the
    # lamp no longer retracts into solid frame steel), so the light
    # rides up with it.
    "beacon_light_pos": [0.0, 5.15, 10.335],
    # Downward tilt of the sweeping beams in degrees (negative = down).
    # A real rotator washes the structure around it, not the horizon;
    # -6 puts the sweep onto the vault girders and canopy.
    "beacon_ray_pitch_deg": -6.0,
    # Daylight-visible levels (2026-08-09b: the player tested under full
    # sun and saw nothing; the bowl light's own comment has always said
    # "invisible under daylight sun" - night-level brightness reads as
    # OFF at noon). Deliberately hot so the head glows and the sweep
    # paints the girders even at midday.
    "beacon_ray_range": 30.0,
    "beacon_ray_brightness": 6.0,
    "beacon_glow_radius": 9.0,
    "beacon_glow_brightness": 4.0,
    # rad/s of dtSim. The old 9.0 spun ~4.3 rev/s REAL (dtSim ~3x wall):
    # two opposed beams strobed at 8.6 flashes/s - flicker, not sweep.
    # 3.0 lands ~1.4 rev/s real, the classic rotator cadence.
    "beacon_rate": 3.0,
    # --- Spin-up soundtrack (player 2026-08-09): three ~63 s stereo FX
    # stems (a loop + two risers) mixed to ONE stereo file
    # (authoring/mix_spinup_audio.sh), started in unison with the spin
    # and stopped when the spinning is over. The SFXEmitter is 2D
    # (is3D=0) because FMOD downmixes 3D sources to mono and the STEREO
    # image is the explicit ask - so distance falloff is scripted: volume
    # follows the camera's distance from the drum centre. Full level out
    # to the rim, silent by ~75 m ("heard from the outside edge, but not
    # much louder than that").
    "spin_audio_path": (
        "/vehicles/ericrolph_gforce_centrifuge/sound/"
        "ericrolph_gforce_centrifuge_spinup.ogg"),
    "spin_audio_volume": 0.85,
    "spin_audio_full_m": 30.0,
    "spin_audio_silent_m": 75.0,
    "smoke_rpm": 400.0,
    # Mouth shelf (build 95; FULL-HEIGHT since b140). The raised patch
    # now carries the ENTIRE wall across the doorway - pure BANK_PROFILE
    # out to the rim (outer row r 19.5, z 7.0) - because the static
    # lintel is gone from the window (DOOR_CUT_LEVELS = 8) and sealed
    # coverage is the shelf's job alone. Buried, its top (7.0, hemmed)
    # must sink at least 0.4 m under the lowest ramp surface over its
    # footprint (~2.1 at r 17.9): 7.0 - 5.5 = 1.5, giving 0.6 m margin,
    # while the buried floor (1.95 - 5.5 = -3.55) rides inside the
    # terrain, unreachable.
    #
    # Travel times are EXPOSURE windows (red-team pass): while rising the
    # mouth is unfloored (mitigated by the floor gate's 32-RPM clamp) and
    # any EXTERNAL be:reloadCollision could snapshot a mid-pose, so both
    # legs are kept short - the same 2.0 s up / 1.6 s down as always,
    # which with the deeper drop means faster travel speeds
    # (5.5/2.0 = 2.75, 5.5/1.6 = 3.4375).
    "shelf_drop": 5.5,
    "shelf_rise_mps": 2.75,
    "shelf_fall_mps": 3.4375,
}

# --- Stock-style emergency lighting + spin soundtrack (2026-08-09c) -----
# Player: "instead of using the beacon that we've made ... can we grab an
# emergency light off an existing car and use that, hooking up the correct
# triggers?" The stock mechanism (excavated from vehicles/common/
# lightEmitters/USLightbarLedBulbs.jbeam) is jbeam "props" rows with the
# magic mesh "SPOTLIGHT": real engine spotlights with candela intensities
# and a light cookie, switched by an electrics value — that IS the
# cop-light. Four amber units ring the trolley-roof beacon site, driven
# in an alternating rotator chase by the vehicle-side lua below. The
# amber color {255,90,14} and intensity 2250 cd are the stock LED unit's
# own numbers. JBEAM COORDS ARE NEGATED AUTHORED (standing law): the
# beacon anchor authored (0, 5.15, ~9.95) sits at jbeam (0, -5.15, ...).
# JBEAM SPOTLIGHT props ABANDONED (2026-08-09c, four probe cycles): the
# stock emergency-light mechanism lives in the vehicle VM's module stack
# (electrics + props + the loader's registration), and a bare prop's VM
# does not boot it. Late-requiring electrics DID revive the values table
# (the chase cycled, verified by readback), but the props/SPOTLIGHT
# renderer never lit through require + reset + manual update. LAW: a
# proplib prop cannot host vehicle-light jbeam props; emergency lighting
# stays GE-side (real PointLight/SpotLights steered per tick), audio
# stays vehicle-side (obj:createSFXSource, an obj method independent of
# the module stack).

# Vehicle-VM code appended to the generated bootstrap lua. Owns BOTH
# spin-FX systems: the amber chase (cycling the electrics the SPOTLIGHT
# props key on — two opposed pairs alternating at 0.25 s, the stock
# lightbar controller's cadence, which reads as rotation) and the spin
# soundtrack (obj:createSFXSource loop — the mod-siren mechanism, the
# proven-audible raw-ogg path; starts and stops exactly with the spin).
# The GE runtime pushes setSpinActive on phase edges.
VEHICLE_LUA_EXTRA = f"""
-- CHIEF spin soundtrack (2026-08-09c): obj:createSFXSource loop - the
-- mod-siren raw-ogg mechanism, an obj method independent of the vehicle
-- module stack (which a bare prop does not boot). Starts and stops
-- exactly with the spinning; the GE runtime pushes setSpinActive on
-- phase edges.
local spinActive = false
local sfxId = nil
local SPIN_OGG = "vehicles/{MOD_ID}/sound/{MOD_ID}_spinup.ogg"

local function setSpinActive(active)
  active = active and true or false
  if active == spinActive then return end
  spinActive = active
  if active then
    if sfxId == nil then
      local ok, id = pcall(function()
        return obj:createSFXSource(SPIN_OGG, "AudioDefaultLoop3D",
          "chief_spinup", 0)
      end)
      sfxId = (ok and id) or nil
      if sfxId then
        pcall(function() obj:setVolumePitch(sfxId, 0.85, 1) end)
      end
    end
    if sfxId then pcall(function() obj:playSFX(sfxId) end) end
  else
    if sfxId then pcall(function() obj:stopSFX(sfxId) end) end
  end
end

M.setSpinActive = setSpinActive

-- CHIEF shutdown one-shot (player 2026-08-12): "if the E-Stop is
-- pressed or when the sequence ends, play these sounds". Mechanical
-- machine-shutdown foley layered over a sci-fi power-down whine, mixed
-- offline (authoring/mix_shutdown_audio.sh). The GE runtime queues
-- playShutdown on the same falling edge that stops the spin loop - the
-- power-down always enters exactly as the soundtrack leaves - and
-- queues stopShutdown 11.2 s later: the loop profile (the only
-- proven-audible path) is defused by parking the stop inside the
-- clip's 2.5 s silent tail pad, so the cut is never audible and the
-- wrap is never reached.
local shutdownSfxId = nil
local SHUTDOWN_OGG = "vehicles/{MOD_ID}/sound/{MOD_ID}_shutdown.ogg"

local function playShutdown()
  if shutdownSfxId == nil then
    local ok, id = pcall(function()
      return obj:createSFXSource(SHUTDOWN_OGG, "AudioDefaultLoop3D",
        "chief_shutdown", 0)
    end)
    shutdownSfxId = (ok and id) or nil
    if shutdownSfxId then
      pcall(function() obj:setVolumePitch(shutdownSfxId, 0.85, 1) end)
    end
  end
  if shutdownSfxId then
    pcall(function() obj:playSFX(shutdownSfxId) end)
  end
end

local function stopShutdown()
  if shutdownSfxId then
    pcall(function() obj:stopSFX(shutdownSfxId) end)
  end
end

M.playShutdown = playShutdown
M.stopShutdown = stopShutdown
"""

# ===========================================================================
# GENERATED-LUA DRIFT, DECLARED 2026-08-15 (round 17). The emissive comments
# in the LUA_BEHAVIOR source below were corrected this round; the BUILT
# artefact was deliberately NOT regenerated, because another session is
# active in this tree and rebuilding the published centrifuge under it is not
# a documentation change. So these five comment blocks in
#     mod/lua/ge/extensions/ericrolph_gforce_centrifuge/runtime.lua
# still carry the RETIRED "material emissive is inert" wording:
#     runtime.lua ~546-550   <- spec.py beacon LIGHTS
#     runtime.lua ~585-590   <- spec.py LENS WASH
#     runtime.lua ~880-887   <- spec.py extraLights preamble
#     runtime.lua ~898-906   <- spec.py sign FLOODS
#     runtime.lua ~917-928   <- spec.py NO sign pool lights
# Only COMMENTS drift; no executable line changed, so the built behaviour is
# byte-for-byte the tested one. The drift clears on the next rebuild of this
# mod - which is also when the four-element emissiveFactor arrays in this
# prop's palette should be repaired, since that is a regression-sweep round
# in its own right and WILL visibly change the published mod.
# ===========================================================================
LUA_BEHAVIOR = r"""
-- One line per rung of rpm_stages (twelve since the ~60 s ramp landed);
-- short of that the later rungs all fell through to "...".
local STAGE_LINES = {
  "10 RPM. A gentle carousel. How nice.",
  "25 RPM. Warming up. Enjoy this part.",
  "45 RPM. Your coffee would be unhappy.",
  "70 RPM. Hold onto your lunch.",
  "100 RPM. Triple digits. We are only getting started.",
  "135 RPM. Your suspension files a complaint.",
  "175 RPM. Complaint denied.",
  "220 RPM. Parts are now officially optional.",
  "275 RPM. Physics would like a word with your tyres.",
  "340 RPM. Structural integrity is a spectrum.",
  "415 RPM. Please keep all limbs inside the vehicle.",
  "500 RPM. MAXIMUM TORTURE. FOR SCIENCE.",
}

local function poseSpinners(state)
  local b = state.behavior
  -- Rotor arm tracks drum RPM (visually capped so blades stay readable).
  setPartPose(
    state, "rotor", nil,
    axisAngle(vec3(0, 0, 1), b.rotorAngle or 0))
  -- Warning beacon (restored 2026-08-09c after the jbeam-SPOTLIGHT
  -- excursion - a bare prop's VM cannot host vehicle light props, see
  -- the JBEAM_PROPS tombstone): amber head retracts into its housing at
  -- idle and pops up spinning while the protocol runs (eject included).
  local beaconOn = b.phase == "spinning" or b.phase == "eject"
  local beaconUp = beaconOn and 0.0 or -0.36
  setPartPose(
    state, "beacon", vec3(0, 0, beaconUp),
    axisAngle(vec3(0, 0, 1), b.beaconAngle or 0))
  -- Beacon LIGHTS: the amber PointLight is the lit lens (this used to cite
  -- "material emissive is inert - sign-round law"; RETIRED 2026-08-15,
  -- round 17 - the real cause was a 4-element emissiveFactor, and emissive
  -- would not throw light on the trolley anyway), the two opposed SpotLights ARE
  -- the sweeping rays, yaw-locked to the head so the lit lobes track
  -- the lens apertures. Daylight-hot brightness (the fin_beacon_close
  -- frame is the reference look).
  local lit = beaconOn and true or false
  if b.beaconLit ~= lit then
    b.beaconLit = lit
    for _, slot in ipairs({"beacon_glow", "beacon_ray_a", "beacon_ray_b",
                           "beacon_lens_a", "beacon_lens_b"}) do
      local l = state.effects[slot]
      if l then
        pcall(function() l:setField("isEnabled", 0, lit and "1" or "0") end)
      end
    end
  end
  if lit then
    -- B.beacon_light_pos is a VEC3 at runtime (pipeline converts
    -- 3-number lists; indexing it threw every lit tick in b107).
    local base = toWorldPoint(state, B.beacon_light_pos)
    -- Aim recipe from the game's own photomodeFlash.lua: setPosition +
    -- the "rotation" field set to quatFromDir(dir, up):toTorqueQuat().
    local tanp = math.tan(math.rad(B.beacon_ray_pitch_deg or 0))
    for i, slot in ipairs({"beacon_ray_a", "beacon_ray_b"}) do
      local l = state.effects[slot]
      if l then
        local yaw = (b.beaconAngle or 0) + (i == 2 and math.pi or 0)
        local dirWorld = state.modelRotation
          * vec3(-math.sin(yaw), math.cos(yaw), tanp)
        dirWorld:normalize()
        pcall(function()
          local q = quatFromDir(dirWorld, vec3(0, 0, 1))
          if q.toTorqueQuat then q = q:toTorqueQuat() end
          l:setPosition(vec3(base.x, base.y, base.z))
          l:setField("rotation", 0,
            q.x .. " " .. q.y .. " " .. q.z .. " " .. q.w)
        end)
      end
    end
    -- LENS WASH (player 2026-08-12: "the orange face should glow orange
    -- and emit light"). This used to open "material emissive is INERT on
    -- this prop (sign-round law)" - RETIRED 2026-08-15, round 17: a
    -- THREE-element emissiveFactor emits, and this prop's are all FOUR.
    -- The request has two halves and they still need different mechanisms:
    -- "glow orange" is now available from the MATERIAL (repair the array,
    -- add nits), but "emit light" is not - emissive self-glows and casts
    -- nothing. The big glow PointLight sits INSIDE the opaque
    -- head, so it pools amber on the trolley while the lamp's own faces
    -- stay sun-lit plastic. The recipe for a glowing SURFACE lit from
    -- outside is the reverse-lit sign's: park a real light just OUTSIDE
    -- the face. Do not delete these lights when the arrays are repaired -
    -- they are what puts amber ON THE TROLLEY.
    -- Two tight amber points orbit with the head, 0.19 m out along each
    -- lens aperture (head r 0.125 + margin clear of the 0.135 cap), so
    -- the visible orange face is always saturated by its own lamp.
    -- 0.19 is a lamp-geometry constant, not a B tunable (standing law).
    for i, slot in ipairs({"beacon_lens_a", "beacon_lens_b"}) do
      local l = state.effects[slot]
      if l then
        local yaw = (b.beaconAngle or 0) + (i == 2 and math.pi or 0)
        local dir = state.modelRotation
          * vec3(-math.sin(yaw), math.cos(yaw), 0.0)
        dir:normalize()
        pcall(function()
          l:setPosition(vec3(base.x + dir.x * 0.19,
            base.y + dir.y * 0.19, base.z + dir.z * 0.19))
        end)
      end
    end
  end
  -- Curved plug door: rotates about the drum axis to open (slides along
  -- the wall). CLOSED while a sample is inside or the drum spins, so the
  -- wall-ride surface is continuous; opens for idle approach/exit.
  setPartPose(
    state, "door", nil,
    axisAngle(vec3(0, 0, 1), b.doorSlide or 0))
  -- Mouth shelf (build 95): the doorway aperture's RIDEABLE floor. The
  -- leaf above stays collisionless theater; this wedge is the physics.
  -- Pure vertical translation between two poses that are BOTH safe to
  -- leave a stale collision bake at: raised = the faired-swale crossing
  -- surface (flush with the flank columns by shared spec.FAIR_KEEP
  -- construction), buried = entirely under the ramp lattice. That is
  -- the structural answer to the round-15 door post-mortem: a stale
  -- mid-slide bake CANNOT stand in the lane because neither endpoint
  -- does.
  setPartPose(
    state, "shelf", vec3(0, 0, -(b.shelfDrop or B.shelf_drop)),
    axisAngle(vec3(0, 0, 1), 0))
  -- C.H.I.E.F. FIELD COUPLING bar graphs (2026-08-09h, player: "a better
  -- visual indicator of how much of an adjustment we've made"). The
  -- 0.025 m/level sliders were invisible from the driver's seat; each
  -- gauge is now five amber blocks over machined sockets. Segment i is
  -- PROUD of the plate while the level is >= i and otherwise translates
  -- +0.12 in authored y, which is straight back through the plate into
  -- the console body - opaque geometry, so it simply is not there. (+y
  -- is the back: every cap on this panel is authored at y -0.70, the
  -- FRONT face, and the world mirror maps authored-back to world-back.)
  local adhLit = b.adhStep or 3
  local dragLit = b.dragStep or 3
  for i = 1, 5 do
    setPartPose(
      state, string.format("adh_seg%d", i),
      vec3(0, i <= adhLit and 0 or 0.12, 0),
      axisAngle(vec3(0, 0, 1), 0))
    setPartPose(
      state, string.format("drag_seg%d", i),
      vec3(0, i <= dragLit and 0 or 0.12, 0),
      axisAngle(vec3(0, 0, 1), 0))
  end
  local sweep = math.rad(B.dial_sweep_deg)
  local frac = math.min(1, (b.rpm or 0) / B.dial_max_rpm)
  -- Ticks are authored at 90deg - frac*270deg; the needle mesh points +X,
  -- so a +90deg base keeps the zero tick honest (review 2026-07-23).
  setPartPose(
    state, "dial_needle", nil,
    axisAngle(vec3(0, 0, 1), math.rad(90) - frac * sweep))
end

-- Interior gate: is this world position actually inside the bowl? Zone
-- occupancy alone lies (debris left behind keeps a flung car "present").
local function insideBowl(state, position)
  local center = toWorldPoint(state, B.spin_center)
  local axis = toWorldDir(state, vec3(0, 0, 1))
  local offset = position - center
  local along = offset:dot(axis)
  if along < B.bowl_along_min or along > B.bowl_along_max then return false end
  local radial = offset - axis * along
  return radial:length() <= B.bowl_radius
end

local function interiorCount(state)
  -- Ground truth over zone occupancy (the b96 eachShelfVehicle pattern,
  -- extended 2026-08-09): trigger rebuilds blank the occupant sets and a
  -- parked car whose enter event is lost goes invisible for MINUTES -
  -- the b109 probe photographed the ladder climbing "empty" with a
  -- sample parked mid-bowl and the mouth held open. The occupancy door,
  -- the floor gate and the eject all key off this count. Falls back to
  -- the set if the API is unavailable.
  local ok, all = pcall(getAllVehicles)
  if ok and type(all) == "table" then
    local count = 0
    for _, vehicle in ipairs(all) do
      if not isSelfProp(vehicle) then
        local okp, position = pcall(function()
          return vehicle:getPosition()
        end)
        if okp and position and insideBowl(state, position) then
          count = count + 1
        end
      end
    end
    return count
  end
  local count = 0
  for vehicleId in pairs(zoneOccupants(state, "drum_zone")) do
    local vehicle = exactVehicle(vehicleId)
    if vehicle and insideBowl(state, vehicle:getPosition()) then
      count = count + 1
    end
  end
  return count
end

local function radialDistance(state, position)
  local center = toWorldPoint(state, B.spin_center)
  local axis = toWorldDir(state, vec3(0, 0, 1))
  local offset = position - center
  local radial = offset - axis * offset:dot(axis)
  return radial:length()
end

-- EJECT BAKE GATE predicate: true only while every interior sample is
-- far (>72 deg) from the mouth sector. Opening the aperture is a GLOBAL
-- collision swap; landing it under a mid-crossing car is the fall-in bug
-- with extra steps, so during eject the open-endpoint bake waits for
-- this. Outside queuers (r >= 19) never block it - the swap cannot
-- touch them.
local function mouthSectorClear(state)
  local center = toWorldPoint(state, B.spin_center)
  local axis = toWorldDir(state, vec3(0, 0, 1))
  local gate = toWorldDir(state, vec3(0, -1, 0))
  for vehicleId in pairs(zoneOccupants(state, "drum_zone")) do
    local vehicle = exactVehicle(vehicleId)
    if vehicle then
      local position = vehicle:getPosition()
      if insideBowl(state, position) then
        local offset = position - center
        local radial = offset - axis * offset:dot(axis)
        local rl = radial:length()
        if rl > 3.0 and rl < 19.0
          and radial:dot(gate) > rl * B.eject_bake_clear_cos then
          return false
        end
      end
    end
  end
  return true
end

-- TRAVEL GATE predicate (red-team F1): may the eject burial START? Every
-- interior sample must be outside the sector now AND predicted to stay
-- out for the full travel + margin (angular distance ahead of its CCW
-- sweep over its map-layer angular rate). After eject_travel_fallback_s
-- without a window (phase-locked multi-car), instantaneous clearance
-- alone suffices - the arrival bake gate remains the backstop.
local function clearForTravel(state)
  local b = state.behavior
  if not mouthSectorClear(state) then return false end
  if (b.ejectTimer or 0) > B.eject_travel_fallback_s then return true end
  local center = toWorldPoint(state, B.spin_center)
  local axis = toWorldDir(state, vec3(0, 0, 1))
  local gate = toWorldDir(state, vec3(0, -1, 0))
  local edge = math.acos(math.min(1.0, B.eject_bake_clear_cos))
  for vehicleId in pairs(zoneOccupants(state, "drum_zone")) do
    local vehicle = exactVehicle(vehicleId)
    if vehicle then
      local position = vehicle:getPosition()
      if insideBowl(state, position) then
        local offset = position - center
        local radial = offset - axis * offset:dot(axis)
        local rl = radial:length()
        if rl > 3.0 and rl < 19.0 then
          local rhat = vec3(radial.x, radial.y, radial.z)
          rhat:normalize()
          -- Signed azimuth from the mouth axis, positive CCW (the field
          -- direction). The car reaches the sector's trailing edge after
          -- sweeping ((-edge) - ang) mod 2pi.
          local cross = gate:cross(rhat)
          local ang = math.atan2(cross:dot(axis), gate:dot(rhat))
          local ahead = (-edge - ang) % (2.0 * math.pi)
          local rate = 0.5
          local okv = pcall(function()
            local info = map and map.objects and map.objects[vehicleId]
            if info and info.vel then
              local tdir = axis:cross(rhat)
              rate = math.max(0.15, math.abs(info.vel:dot(tdir)) / rl)
            end
          end)
          if not okv then rate = 4.5 end
          if ahead / rate < B.eject_travel_clear_s then
            return false
          end
        end
      end
    end
  end
  return true
end

-- A sample only ARMS the protocol once it is genuinely mid-bowl; cars in
-- the doorway band must be free to drive in (round 7: the field pinned
-- an entering car against the door jamb the moment it crossed the sill).
local function armableCount(state)
  -- Same ground-truth hardening as interiorCount: a lost enter event
  -- must not leave a mid-bowl car unable to arm the protocol.
  local ok, all = pcall(getAllVehicles)
  if ok and type(all) == "table" then
    local count = 0
    for _, vehicle in ipairs(all) do
      if not isSelfProp(vehicle) then
        local okp, position = pcall(function()
          return vehicle:getPosition()
        end)
        if okp and position and insideBowl(state, position)
          and radialDistance(state, position) <= B.arm_radius then
          count = count + 1
        end
      end
    end
    return count
  end
  local count = 0
  for vehicleId in pairs(zoneOccupants(state, "drum_zone")) do
    local vehicle = exactVehicle(vehicleId)
    if vehicle then
      local position = vehicle:getPosition()
      if insideBowl(state, position)
        and radialDistance(state, position) <= B.arm_radius then
        count = count + 1
      end
    end
  end
  return count
end

behavior.init = function(state)
  local b = state.behavior
  b.phase = "idle"
  -- Red-team F5: manual mode must not survive a prop reset - a stale
  -- flag turned later drive-in arms into sealed 10-RPM holds forever.
  b.manual = nil
  -- Same reasoning for the soundtrack state: a reset mid-spin must not
  -- fire the shutdown one-shot (spinFxOn cleared = no falling edge),
  -- must not start the next session pre-killed, and must drop any
  -- in-flight shutdown stop clock.
  b.fxKill = nil
  b.spinFxOn = nil
  b.shutdownT = nil
  b.manualStage = nil
  b.ejectMouthGo = nil
  b.doorSlide = 0
  -- Mouth shelf starts fully buried (idle = doorway open at deck level).
  b.shelfDrop = B.shelf_drop
  b.shelfReloaded = true
  requestCollisionReload(state)
  b.rpm = 0
  b.stage = 0
  b.stageTimer = 0
  b.speedCap = 0
  b.boomAngle = 0
  b.tracked = {}
  b.ejected = {}
  b.stats = b.stats or {max_rpm = 0, peak_tangential_mps = 0, mouth_ejects = 0}
  -- Bowl fill light (player 2026-08-08: fixtures should "light up the
  -- interior of the centrifuge bowl at night"). Emissive materials in
  -- BeamNG self-glow but cast nothing, so ONE PointLight rides the drum
  -- axis under the vault. Stored in state.effects: cleanupInstallation
  -- deletes it with everything else. Invisible under daylight sun.
  if not state.effects.bowl_glow then
    local light = createObject("PointLight")
    if light then
      local ok = pcall(function()
        light.loadMode = 1
        if type(light.preApply) == "function" then light:preApply() end
        local p = toWorldPoint(state, vec3(0, 0, 7.0))
        light:setPosition(vec3(p.x, p.y, p.z))
        light:setField("radius", 0, "34")
        light:setField("brightness", 0, "1.15")
        light:setField("color", 0, "0.62 0.78 0.92 1")
        light:setField("isEnabled", 0, "1")
        if type(light.postApply) == "function" then light:postApply() end
      end)
      local registered = ok and registerInMission(
        light, string.format("%s_p%d_light_bowl", PROP_MODEL, state.propId))
      if registered then
        state.effects.bowl_glow = light
      else
        pcall(function() light:delete() end)
      end
    end
  end
  -- RETIRED 2026-08-15 (round 17). This used to read: "Round 15: material
  -- emissiveFactor proved INERT on this vehicle in every variant tried
  -- (textured, plain colour, explicit emissiveMap, double-sided or not)".
  -- The observation was real; the diagnosis was wrong twice over. Every
  -- variant tried carried a FOUR-element emissiveFactor (three emit fine),
  -- and the "explicit emissiveMap" variant was never even cooked, because
  -- the generator named it `.emissive.png` and only `.color`/`.data`/
  -- `.normal` are cooked. The round-14 "glowing interior" WAS the bowl
  -- PointLight's wash - that part stands. Real lights remain the right
  -- mechanism for anything that must ILLUMINATE, since emissive casts
  -- nothing; they are no longer the ONLY night mechanism. The sign gets three lights
  -- INSIDE the channel-letter standoff gap: the panel washes bright at
  -- grazing range while the letter faces point away and stay dark - a
  -- true reverse-lit gradient. The vault ring gets three cool fills so
  -- the near-flush can lenses read as the sources of the bowl light.
  local extraLights = {
    -- (sign lights are appended below: a string of small dim pools along
    -- the text arc, not a few floods)
    {key = "ring_a", pos = vec3(0.0, 15.3, 8.2), radius = 20.0,
     brightness = 0.8, color = "0.62 0.78 0.92 1"},
    {key = "ring_b", pos = vec3(-13.25, -7.65, 8.2), radius = 20.0,
     brightness = 0.8, color = "0.62 0.78 0.92 1"},
    {key = "ring_c", pos = vec3(13.25, -7.65, 8.2), radius = 20.0,
     brightness = 0.8, color = "0.62 0.78 0.92 1"},
    -- Sign FLOODS (round 15 coda, amended round 17): the b79 night probe
    -- showed a black sign the moment the pools were deleted. That is still
    -- true and still the reason for these floods - but NOT because "the
    -- backplates are inert like every vehicle material". letter_glow's
    -- emissiveFactor has FOUR elements; a three-element one emits. So the
    -- sign is lit like a real floodlit fascia: two
    -- lights ~7 m OUT FRONT. At that distance the inverse-square
    -- variation across the cabinet is gentle - no discs, physically -
    -- and the near-white plates return ~9x the graphite cabinet, so the
    -- glow still reads as the letter shapes. Brightness picked by live
    -- setField ladder on the b80 rig.
    -- z 10.1, not 7.4 (b81 ladder): at 7.4 the portal canopy lip
    -- eclipsed the upper cabinet - the band below the sign lit up while
    -- the letters stayed dark, and brightness 0.25..1.4 changed almost
    -- nothing because the light simply never reached the glyphs. At
    -- letter height the sight line clears the roof.
    {key = "sign_fl_l", pos = vec3(-4.5, -33.0, 10.1), radius = 26.0,
     brightness = 0.8, color = "1 0.97 0.9 1"},
    {key = "sign_fl_r", pos = vec3(4.5, -33.0, 10.1), radius = 26.0,
     brightness = 0.8, color = "1 0.97 0.9 1"},
  }
  -- NO sign pool lights (round 15 coda). The full history: 5 floods in
  -- the standoff gap blew out the panel (b63), 16 pools at 0.32 fused
  -- into a blown strip (b70), 0.07 read as circular bulbs (b77), and
  -- even 0.012 still painted a chain of discs (b78 probe) - a
  -- PointLight AT the panel renders as a disc at any brightness, full
  -- stop. And the b79 probe closed the other door: with the pools gone
  -- the sign went black. That used to be read as "proving letter_glow's
  -- emissiveFactor is as inert as every other vehicle material" - RETIRED
  -- 2026-08-15, round 17: it proves letter_glow SPECIFICALLY is dead, and
  -- the cause is its FOUR-element array. (The b78 "glowing rims" were
  -- pool-lit - that reading survives.) Night lighting is therefore the two DISTANT sign floods
  -- in extraLights above: far enough that the wash is even (no discs),
  -- while the white glyph backplates out-return the graphite cabinet
  -- ~9x, keeping the glow letter-shaped.
  for _, lightSpec in ipairs(extraLights) do
    local slot = "light_" .. lightSpec.key
    if not state.effects[slot] then
      local l = createObject("PointLight")
      if l then
        local ok = pcall(function()
          l.loadMode = 1
          if type(l.preApply) == "function" then l:preApply() end
          local p = toWorldPoint(state, lightSpec.pos)
          l:setPosition(vec3(p.x, p.y, p.z))
          l:setField("radius", 0, tostring(lightSpec.radius))
          l:setField("brightness", 0, tostring(lightSpec.brightness))
          l:setField("color", 0, lightSpec.color)
          l:setField("isEnabled", 0, "1")
          if type(l.postApply) == "function" then l:postApply() end
        end)
        local reg = ok and registerInMission(
          l, string.format("%s_p%d_light_%s", PROP_MODEL, state.propId,
                           lightSpec.key))
        if reg then
          state.effects[slot] = l
        else
          pcall(function() l:delete() end)
        end
      end
    end
  end
  -- Beacon lights (restored 2026-08-09c): created disabled; poseSpinners
  -- enables + steers them. effects.* members, swept by cleanup.
  local beaconLightSpecs = {
    {slot = "beacon_glow", class = "PointLight", fields = {
      radius = tostring(B.beacon_glow_radius),
      brightness = tostring(B.beacon_glow_brightness),
      color = "1 0.42 0.06 1"}},
    {slot = "beacon_ray_a", class = "SpotLight", fields = {
      radius = tostring(B.beacon_ray_range),
      range = tostring(B.beacon_ray_range),
      brightness = tostring(B.beacon_ray_brightness),
      innerAngle = "10", outerAngle = "26",
      castShadows = "0", color = "1 0.38 0.05 1"}},
    {slot = "beacon_ray_b", class = "SpotLight", fields = {
      radius = tostring(B.beacon_ray_range),
      range = tostring(B.beacon_ray_range),
      brightness = tostring(B.beacon_ray_brightness),
      innerAngle = "10", outerAngle = "26",
      castShadows = "0", color = "1 0.38 0.05 1"}},
    -- Lens-wash points (2026-08-12): tiny hot ambers steered per tick to
    -- the two lens apertures so the head's orange faces read as burning
    -- (see the LENS WASH comment in poseSpinners). Daylight-hot per the
    -- beacon brightness law - dimmer reads as OFF at noon; the 0.9 m
    -- radius keeps the heat on the lamp, cap rim and housing mouth only.
    {slot = "beacon_lens_a", class = "PointLight", fields = {
      radius = "0.9", brightness = "5.0",
      castShadows = "0", color = "1 0.45 0.08 1"}},
    {slot = "beacon_lens_b", class = "PointLight", fields = {
      radius = "0.9", brightness = "5.0",
      castShadows = "0", color = "1 0.45 0.08 1"}},
  }
  for _, ls in ipairs(beaconLightSpecs) do
    if not state.effects[ls.slot] then
      local l = createObject(ls.class)
      if l then
        local ok = pcall(function()
          l.loadMode = 1
          if type(l.preApply) == "function" then l:preApply() end
          local p = toWorldPoint(state, B.beacon_light_pos)
          l:setPosition(vec3(p.x, p.y, p.z))
          for fieldName, fieldValue in pairs(ls.fields) do
            l:setField(fieldName, 0, fieldValue)
          end
          l:setField("isEnabled", 0, "0")
          if type(l.postApply) == "function" then l:postApply() end
        end)
        local reg = ok and registerInMission(
          l, string.format("%s_p%d_%s", PROP_MODEL, state.propId, ls.slot))
        if reg then
          state.effects[ls.slot] = l
        else
          pcall(function() l:delete() end)
        end
      end
    end
  end
  b.beaconLit = nil
  -- Spin-FX flag re-pushed on init so a reloaded runtime resyncs the
  -- vehicle-side soundtrack.
  b.spinFxOn = nil
  poseSpinners(state)
end

behavior.reset = function(state)
  behavior.init(state)
end

local function armSpin(state, subjectId)
  local b = state.behavior
  b.phase = "spinning"
  b.fxKill = nil
  b.stage = 1
  b.stageTimer = 0
  b.sampleLost = nil
  b.ejected = {}
  b.ejectMouthGo = nil
  -- Red-team F5: a stale manual flag surviving a prop reset turned every
  -- later drive-in "auto" arm into a sealed-mouth 10-RPM hold forever.
  -- Arming IS the auto protocol; manual mode is only ever entered by the
  -- RPM buttons themselves.
  b.manual = false
  showMessage("SAMPLE LOADED. Beginning torture protocol.", 2.4)
  emitEvent(state, "I", "centrifuge_armed", {subject_id = subjectId})
end

-- MOUTH EJECT entry (player 2026-08-09: "spit the car at the speed it's
-- currently going out the front entrance"). Supersedes BOTH prior
-- endings: the survivor self-drive unload and the over-the-rim fling.
-- The eject branch of behavior.update runs the choreography; the actual
-- launches live in applySpinField where per-sample velocity is known.
local function enterEject(state, worstDamage)
  local b = state.behavior
  b.phase = "eject"
  b.ejectTimer = 0
  b.ejectMouthGo = nil
  b.ejected = b.ejected or {}
  -- Bleed target: the sample's CURRENT regime capped at eject speed -
  -- never speed a slow manual hold UP just to throw it harder.
  b.ejectCap = math.min(B.eject_speed_mps,
    math.max(B.eject_min_speed, b.speedCap or B.eject_speed_mps))
  if (worstDamage or 0) < B.survive_damage_max then
    showMessage(string.format(
      "SAMPLE INTACT (%d damage). EJECTING VIA THE FRONT ENTRANCE - "
      .. "do not resist the machine's generosity.",
      math.floor(worstDamage or 0)), 3.4)
  else
    showMessage(
      "PROTOCOL COMPLETE. SAMPLE REJECTED - returning the remains to "
      .. "sender, entrance-first.", 3.2)
  end
  emitEvent(state, "I", "centrifuge_eject_begin",
    {damage = math.floor(worstDamage or 0)})
end

-- Volcano launch for everything interior: the PURGE button, the eject
-- timeout, the idle doorway-squatter purge and the idle self-clean all
-- share it. Up-and-out with no tangential term - the drum may not be
-- turning. Red-team F4 filters: a just-launched car mid-flight keeps its
-- AIMED exit velocity (never replaced by a volcano), and a node-excursion
-- quarantined sample receives NO velocity injection at all - the same
-- energy-feed contract the field honors. Returns cleared, skipped.
local function purgeBowl(state)
  local b = state.behavior
  local center = toWorldPoint(state, B.spin_center)
  local axis = toWorldDir(state, vec3(0, 0, 1))
  local cleared = 0
  local skipped = 0
  for vehicleId in pairs(zoneOccupants(state, "drum_zone")) do
    local vehicle = exactVehicle(vehicleId)
    if vehicle then
      local launchedAlready = b.ejected and b.ejected[vehicleId]
      local quarantine = b.nodeSafety and b.nodeSafety[vehicleId]
      if launchedAlready or (quarantine and quarantine > 0) then
        skipped = skipped + 1
      else
        local position = vehicle:getPosition()
        if insideBowl(state, position) then
          local offset = position - center
          local radial = offset - axis * offset:dot(axis)
          local velocity
          if radial:length() > 0.3 then
            radial:normalize()
            velocity = radial * B.purge_out_mps + axis * B.purge_up_mps
          else
            velocity = axis * B.purge_up_mps
          end
          if launchSubject(state, vehicle, velocity) then
            cleared = cleared + 1
            emitEvent(state, "I", "centrifuge_purged",
              {subject_id = vehicleId})
          end
        end
      end
    end
  end
  return cleared, skipped
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  -- ALL FOUR rim_zone greetings deleted 2026-08-10 (player). They fired
  -- on approach, before the player had done anything, and between them
  -- they narrated every phase the machine could be in - four different
  -- toasts for simply driving toward the building. The drum_zone
  -- "SAMPLE DETECTED" line below is kept: that one answers an action.
  -- Note the rim greetings were also the loudest symptom of the
  -- insideBowl radius bug (interiorCount counts the entrance ramp), so
  -- their removal is not a workaround for it - fix bowl_radius too.
  if zone == "drum_zone" and b.phase == "idle" and not b.needEmpty
    and insideBowl(state, vehicle:getPosition()) then
    showMessage("SAMPLE DETECTED. Proceed to the centre of the drum.", 2.4)
  end
end

behavior.onExit = function(state, zone, vehicleId)
  if zone == "drum_zone" then
    -- Drop the velocity-estimator seed: a stale last-position across an
    -- exit/re-entry reads as hundreds of m/s and kicks the car.
    state.behavior.tracked[vehicleId] = nil
  end
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  state.behavior.tracked[vehicleId] = nil
end

-- Console buttons (2026-08-05): manual override. Start spins the drum with
-- or without a sample (drive in WHILE it spins), Faster/Slower step the
-- stage ladder, Stop winds down. Manual mode never auto-escalates, never
-- flings, and never aborts on an empty bowl.
behavior.onPanelButton = function(state, buttonId)
  local b = state.behavior
  if buttonId == "btn_start" then
    -- Round 15 (player: "I couldn't start"): START now launches the
    -- AUTO protocol - the twelve-stage crescendo - which is what the
    -- label promises. Works on an empty drum too (full demonstration to
    -- 500; the empty-complete path already exists). Manual holds moved
    -- to the RPM +/- buttons.
    -- EJECT GUARD (red-team F2): arming from eject wiped b.ejected while
    -- a launched car was in flight - the magnetic hold then slammed
    -- ~20 m/s into it one tick later and revoked its launch over an OPEN
    -- mouth. The throw finishes first, always.
    -- Message deleted 2026-08-10 (player). The guard stays: RPM control
    -- during an eject is still refused, silently.
    if b.phase == "eject" then
      return
    end
    local wasManual = b.manual
    b.manual = false
    b.needEmpty = nil
    b.sampleLost = nil
    if b.phase ~= "spinning" then
      armSpin(state, nil)
      showMessage(
        "PROTOCOL START: twelve-stage crescendo engaged. "
        .. "Samples ride at their own risk.", 2.8)
    elseif wasManual then
      -- Converting a manual hold to the auto ladder: restart the stage
      -- clock or the long-accrued hold time advances (or ejects) on the
      -- very next tick (red-team F5 rider).
      b.stageTimer = 0
      showMessage(string.format(
        "AUTO PROTOCOL ENGAGED from stage %d. The crescendo resumes.",
        b.stage or 1), 2.6)
    else
      showMessage("Protocol already running.", 2.0)
    end
  elseif buttonId == "btn_stop" then
    b.manual = false
    if b.phase == "spinning" or b.phase == "eject" then
      -- E-STOP AUDIO (player 2026-08-12): the press itself kills the
      -- soundtrack and cues the shutdown one-shot via the FX falling
      -- edge - immediately, not after the eject throw finishes. The
      -- machine keeps its stop choreography; only the music dies now.
      b.fxKill = true
      -- STOP = eject (player 2026-08-09): whatever is aboard gets spat
      -- out the front entrance at the speed it is currently going. A
      -- stage-1 carousel rider rolls out at ~8 m/s; a mid-ladder sample
      -- gets the full 34 m/s send-off after the bleed.
      local worst = 0
      for vehicleId in pairs(zoneOccupants(state, "drum_zone")) do
        local vehicle = exactVehicle(vehicleId)
        if vehicle and insideBowl(state, vehicle:getPosition()) then
          local data = map and map.objects and map.objects[vehicleId]
          local hurt = data and data.damage or 0
          if hurt > worst then worst = hurt end
        end
      end
      if b.phase == "spinning" and interiorCount(state) > 0 then
        enterEject(state, worst)
      elseif b.phase == "spinning" then
        b.phase = "spindown"
      end
    end
    showMessage("MANUAL STOP: spinning down.", 2.2)
  elseif buttonId == "btn_faster" or buttonId == "btn_slower" then
    -- EJECT GUARD (red-team F3): the manual branch used to hijack phase
    -- "spinning" out of eject - collision stayed open through the 2 s
    -- rise while launches were disabled (the forbidden fast-over-open
    -- regime), and manualStage seeded from stage 12 = a 500 RPM "hold".
    if b.phase == "eject" then
      showMessage(
        "EJECTION IN PROGRESS - speed control returns after the throw.",
        2.4)
      return
    end
    local step = buttonId == "btn_faster" and 1 or -1
    b.manualStage = math.max(1, math.min(#B.rpm_stages,
      (b.manualStage or b.stage or 1) + step))
    if b.phase ~= "spinning" then
      -- Round 15: RPM buttons are the entry into MANUAL HOLD - from
      -- idle, one press spins the drum up to the selected stage and
      -- keeps it there (empty bowl allowed; the manual branch already
      -- handles it). START owns the auto protocol.
      b.manual = true
      b.phase = "spinning"
      b.fxKill = nil
      b.stage = b.manualStage
      b.stageTimer = 0
      b.speedCap = 0
      showMessage(string.format(
        "MANUAL SPIN: stage %d (%d RPM). Operator assumes all liability.",
        b.manualStage, B.rpm_stages[b.manualStage]), 2.6)
    else
      if b.manual then b.stage = b.manualStage end
      showMessage(string.format("SPEED SET: stage %d (%d RPM).",
        b.manualStage, B.rpm_stages[b.manualStage]), 2.2)
    end
  elseif buttonId == "btn_adh_up" or buttonId == "btn_adh_down" then
    -- C.H.I.E.F. WALL ADHESION (player 2026-08-09f): live hold_damp -
    -- how hard the magnetic hold cancels outward drift, i.e. how hard
    -- the machine grinds the sample sideways into the wall. Lower =
    -- gentler on tyres, higher escape risk at the top rungs.
    -- Ladder widened 2026-08-09h (player: "how much level adjustment
    -- should we give"). damp is the fraction of outward radial velocity
    -- cancelled EACH FRAME, so it COMPOUNDS: over six frames 0.55 leaves
    -- 1% of an overshoot standing and 0.03 leaves 84%. That is why the
    -- old 0.15..0.95 span felt like one setting - every rung pinned the
    -- sample inside a tenth of a second. The rungs are logarithmic now,
    -- 0.03 (the sample visibly hunts up the bank and can reach the rim)
    -- to 1.00 (outward motion cancelled outright, welded), with the
    -- shipped 0.55 setpoint still dead centre.
    local step = buttonId == "btn_adh_up" and 1 or -1
    b.adhStep = math.max(1, math.min(5, (b.adhStep or 3) + step))
    local vals = {0.03, 0.15, 0.55, 0.80, 1.00}
    b.holdDampEff = vals[b.adhStep]
    local note = "Nominal coupling."
    if b.adhStep == 1 then
      note = "Loose hold - samples may leave the wall at speed."
    elseif b.adhStep == 2 then
      note = "Soft hold - expect radial hunting on the bank."
    elseif b.adhStep >= 4 then
      note = "Welded. Extra tyre seasoning."
    end
    showMessage(string.format(
      "WALL ADHESION: level %d/5 (damp %.2f). %s",
      b.adhStep, b.holdDampEff, note), 3.0)
  elseif buttonId == "btn_drag_up" or buttonId == "btn_drag_down" then
    -- C.H.I.E.F. FIELD DRAG: live drag_rate - how aggressively the
    -- tangential field forces the sample to orbit speed. Lower = less
    -- slip-angle scrub, slower spin-up response.
    -- Ladder widened 2026-08-09h: this IS a rate (1/s), so the level is
    -- a slip time-constant - 0.8 = 1.25 s to pull the sample onto field
    -- speed, 14 = 0.07 s. Straddling the 3.5 setpoint by a factor of ~4
    -- each way is what makes the control legible: the low end lets the
    -- sample fight and scrub, the high end snaps it to orbit speed and
    -- is the actual answer to "how do I stop popping tyres".
    local step = buttonId == "btn_drag_up" and 1 or -1
    b.dragStep = math.max(1, math.min(5, (b.dragStep or 3) + step))
    local vals = {0.8, 1.8, 3.5, 7.0, 14.0}
    b.dragRateEff = vals[b.dragStep]
    local note = "Nominal coupling."
    if b.dragStep <= 2 then
      note = "Gentle on tyres, lazy on schedule."
    elseif b.dragStep >= 4 then
      note = "Low slip angle, high wall grind."
    end
    showMessage(string.format(
      "FIELD DRAG: level %d/5 (rate %.1f). %s",
      b.dragStep, b.dragRateEff, note), 3.0)
  elseif buttonId == "btn_purge" then
    -- Housekeeping fling: eject EVERYTHING inside the drum - wrecks,
    -- shed parts still tracked as their vehicle, parked cars - from any
    -- phase. Straight up-and-out, no tangential term: the drum may not
    -- be turning when the operator clears it. (Shared with the eject
    -- timeout and the idle doorway-squatter purge via purgeBowl.)
    local cleared, skipped = purgeBowl(state)
    if skipped > 0 then
      showMessage(string.format(
        "BOWL PURGE: %d cleared, %d in flight or quarantined - try again "
        .. "shortly.", cleared, skipped), 2.8)
    elseif cleared > 0 then
      showMessage(string.format(
        "BOWL PURGE: %d object%s ejected. Mind the skies.",
        cleared, cleared == 1 and "" or "s"), 2.8)
    else
      showMessage("BOWL PURGE: drum already clear.", 2.2)
    end
  end
end

local function applySpinField(state, dtSim)
  local b = state.behavior
  if dtSim <= 0 or (b.rpm or 0) < 1.0 then return end
  local omega = b.rpm * math.pi / 30.0
  local stageCap = math.max(2.0, b.speedCap or 0)
  local center = toWorldPoint(state, B.spin_center)
  local axis = toWorldDir(state, vec3(0, 0, 1))
  -- Round 15 phys watchdog (player: stretched black polygons = node
  -- explosions). GE-side and API-defensive: the live OOBB half-extent of
  -- a healthy car is a few metres; one exploded node inflates it by
  -- hundreds. On excursion the sample is quarantined - dropped from the
  -- field for safety_release_seconds so the machine stops feeding energy
  -- into a solver that is already losing the vehicle. safety_enabled
  -- False reverts to exact pre-round-15 behavior.
  if B.safety_enabled then
    b.safetyClock = (b.safetyClock or 0) + dtSim
    b.nodeSafety = b.nodeSafety or {}
    if b.safetyClock >= (B.safety_check_interval or 1.0) then
      b.safetyClock = 0
      for vehicleId in pairs(b.tracked or {}) do
        local vehicle = exactVehicle(vehicleId)
        if vehicle then
          local worst = 0
          local ok = pcall(function()
            local box = vehicle:getSpawnWorldOOBB()
            local ext = box:getHalfExtents()
            worst = math.max(ext.x, math.max(ext.y, ext.z))
          end)
          if ok and worst > (B.safety_node_dist or 40.0) then
            if not b.nodeSafety[vehicleId] or b.nodeSafety[vehicleId] <= 0 then
              showMessage(
                "PHYS SANITIZER: node excursion detected - "
                .. "field released for this sample.", 3.0)
              emitEvent(state, "W", "node_excursion", {
                vehicle = vehicleId, extent = math.floor(worst)})
            end
            b.nodeSafety[vehicleId] = B.safety_release_seconds or 20.0
          end
        end
      end
    end
  end
  for vehicleId in pairs(zoneOccupants(state, "drum_zone")) do
    local vehicle = exactVehicle(vehicleId)
    if vehicle and b.ejected and b.ejected[vehicleId] then
      -- Launched samples are DONE: no field, no magnetic hold, no gap
      -- assist, no stall purge. Anything applied after the launch
      -- corrupts the aim - the mouth eject SETS an exact velocity and
      -- the sample must keep it all the way out of the bowl.
      -- TRANSIENT latch (red-team F2/F3/F4 ghosts): it expires the
      -- moment the launch is spent - the car left the bowl, or came to
      -- rest back inside. After that it is an ordinary occupant again
      -- (purgeable, field-draggable, launchable next eject).
      local spent = false
      local okq = pcall(function()
        if not insideBowl(state, vehicle:getPosition()) then
          spent = true
          return
        end
        local info = map and map.objects and map.objects[vehicleId]
        if info and info.vel and info.vel:length() < 3.0 then
          spent = true
        end
      end)
      if okq and spent then
        b.ejected[vehicleId] = nil
      else
        b.tracked[vehicleId] = nil
        vehicle = nil
      end
    end
    if vehicle then
      local position = vehicle:getPosition()
      if b.rpm < 30 and radialDistance(state, position) > 17.9 then
        -- Low-rpm door protection: entering/exiting cars in the outer
        -- band are never dragged into the jambs.
        b.tracked[vehicleId] = nil
      elseif not insideBowl(state, position) then
        -- Never drag anything that is not physically in the bowl (flung
        -- cars kept "present" by their debris, or corner-clip entrants).
        b.tracked[vehicleId] = nil
      else
        local track = b.tracked[vehicleId]
        local velocity = vec3(0, 0, 0)
        if track then
          velocity = (position - track.position) * (1 / dtSim)
        end
        -- STUCK AUTO-PURGE (round 15 endgame). The player's one
        -- non-negotiable: "vehicles should spin freely without getting
        -- stuck in spots in the bowl". After the full forensic
        -- campaign, the last stuck mode is dynamical, not geometric: a
        -- sample that spins out at the doorway crossing wrecks its
        -- tires and parks under the field's pin. Rather than let ANY
        -- future stuck mode grind forever, the machine now measures
        -- each tracked sample's angular progress and, after 12 s of no
        -- sweep while the drum runs, PURGES it sky-high with the
        -- existing launch machinery. A torture centrifuge disposes of
        -- seized specimens. Stuck is now impossible by construction.
        local offsetT = position - center
        local radialT = offsetT - axis * offsetT:dot(axis)
        local angT = math.atan2(radialT.y, radialT.x)
        local stallT = 0.0
        if track and track.ang then
          local dAng = angT - track.ang
          if dAng > math.pi then dAng = dAng - 2 * math.pi end
          if dAng < -math.pi then dAng = dAng + 2 * math.pi end
          -- > 20, not > 60 (red-team finding 1b): a blocker squatting
          -- the doorway band holds the shelf's rise interlock, and the
          -- floor gate parks the drum at 32 RPM - stall must accrue
          -- THERE or the blocker is never purged and the machine jams
          -- forever. 20 keeps stage-1 carousel riders (10 RPM) exempt.
          -- Radius gate 19.6 (b97 probe): the drum interior INCLUDING
          -- the bank runs to r 19.5 - a flat-tired sample wedged high
          -- on the bank at 18.6 must accrue - but a car slowly
          -- approaching on the outer ramp at r 19.6+ is queueing, not
          -- stalled, and the b97 probe photographed the 20-RPM gate
          -- yeeting exactly such an innocent approacher at r ~20.
          if math.abs(dAng) < 0.006 and (b.rpm or 0) > 20
            and radialT:length() < 19.6 then
            stallT = (track.stall or 0) + dtSim
          end
        end
        b.tracked[vehicleId] = {position = vec3(position.x, position.y, position.z),
                                ang = angT, stall = stallT}
        if stallT > 12.0 then
          local outR = vec3(radialT.x, radialT.y, radialT.z)
          local launchV
          if outR:length() > 0.3 then
            outR:normalize()
            launchV = outR * B.purge_out_mps + axis * B.purge_up_mps
          else
            launchV = axis * B.purge_up_mps
          end
          if launchSubject(state, vehicle, launchV) then
            showMessage("SAMPLE SEIZED - AUTO-PURGE ENGAGED. NEXT.", 2.8)
            emitEvent(state, "I", "stuck_autopurge", {subject_id = vehicleId})
          end
          b.tracked[vehicleId] = nil
          track = nil
        end
        if track and velocity:length() > B.estimate_sane_mps then
          -- Teleport-sized displacement: re-seed instead of reacting.
          track = nil
        end
        if track and B.safety_enabled then
          -- Quarantined (node excursion) or map-layer-insane samples get
          -- NO field or containment dv: a mid-explosion vehicle must not
          -- receive more energy. Decays back to normal on its own.
          -- Decay moved to behavior.update (single authority): at idle
          -- this whole function early-outs and a quarantined carcass
          -- stayed unpurgeable forever (red-team F4/F6 interplay).
          local quarantine = b.nodeSafety and b.nodeSafety[vehicleId]
          if quarantine and quarantine > 0 then
            track = nil
          else
            local info = map and map.objects and map.objects[vehicleId]
            if info and info.vel
                and info.vel:length() > (B.safety_skip_mps or 150.0) then
              track = nil
            end
          end
        end
        if track then
          local offset = position - center
          local along = offset:dot(axis)
          local radial = offset - axis * along
          local fieldOk = true
          if B.safety_enabled and radial:length() > 13.2 then
            -- Door-band release (round 15 gauntlet): a vehicle out past
            -- the lip with near-zero tangential speed is ENTERING or
            -- EXITING, not riding the drum - dragging it sideways into
            -- the jambs mid-protocol is what shredded tires. A real
            -- sample out there carries high tangential speed and keeps
            -- the field.
            local tdir = axis:cross(radial)
            tdir:normalize()
            if math.abs(velocity:dot(tdir)) < 4.0 then
              fieldOk = false
            end
          end
          if fieldOk and radial:length() > B.min_radius then
            local field = axis:cross(radial) * omega
            local cap = math.min(stageCap, B.field_speed_cap_mps)
            if field:length() > cap then
              field:normalize()
              field = field * cap
            end
            local slip = field - velocity
            slip.z = 0
            -- Panel-adjustable (C.H.I.E.F. FIELD DRAG, 2026-08-09f).
            local dragRate = b.dragRateEff or B.drag_rate
            local delta = slip * math.min(0.6, dtSim * dragRate)
            -- STALL RECOVERY (b91 endgame - the final stuck mechanism,
            -- measured by the angular-progress detector): once the
            -- torture shreds the tires, rim friction exceeds the
            -- gentle per-tick correction and the sample PARKS on the
            -- deck while the drum spins - the player's "stuck in spots
            -- in the bowl", in its last surviving form. A sample
            -- moving under 6 m/s while the drum runs above 60 RPM gets
            -- the full correction rate (still frame_dv_cap-limited):
            -- the machine grips harder until its sample moves. A
            -- centrifuge never lets the specimen rest.
            if velocity:length() < 6.0 and b.rpm > 60 then
              delta = slip * math.min(1.0, dtSim * dragRate * 3.0)
            end
            if delta:length() > B.frame_dv_cap then
              delta:normalize()
              delta = delta * B.frame_dv_cap
            end
            addSubjectVelocity(state, vehicle, delta)
            -- Containment assist: the wall is geometry, but a fast sample
            -- can climb or find the vomitory mouth. Push it back inboard
            -- proportional to how far past the hold line it has drifted.
            -- NO doorway bridge (round 15 coda). A sector-local holdLine
            -- (15.9 -> 14.6 across the mouth) lived here for one build
            -- and was the b79 ejection: snapping the hold target 1.3 m
            -- at the sector edges kicks the orbit radially every lap,
            -- the orbit goes ECCENTRIC (r swinging 13.5..16 inside one
            -- lap in the crumb log), eccentric orbits pump up the bank,
            -- and the mouth gap is the one opening in the rim - the
            -- sample flew out at z ~6 and landed 250 m away. The b68
            -- uniform hold contained the same protocol to 491 RPM with
            -- a steady orbit. The hold line must be AXISYMMETRIC; the
            -- mouth needs no special casing once no wall stands in the
            -- band (the guards are gone) - a circulating sample clears
            -- the opening tangentially on geometry alone.
            local overshoot = radial:length() - B.hold_radius
            if overshoot > 0 then
              local inward = vec3(radial.x, radial.y, radial.z)
              inward:normalize()
              -- MAGNETIC HOLD. Holding a car at the top of the ladder needs
              -- ~116 g, and a spring stiff enough for that would inject
              -- ~19 m/s of inward velocity in a SINGLE frame - a teleport
              -- that shreds the car. So damp first: cancel the outward
              -- radial component of its velocity outright, which pins the
              -- sample as a velocity constraint rather than a huge force,
              -- then add the (much softer) spring to walk it back to the
              -- hold line. Player chose "keep 500 RPM, glue it to the wall"
              -- over capping the ladder at the ~100 m/s the bank alone can
              -- carry, so this is deliberately superhuman above stage ~9.
              --
              local outward = velocity:dot(inward)
              -- Panel-adjustable (C.H.I.E.F. WALL ADHESION, 2026-08-09f).
              local damp = outward > 0
                and outward * (b.holdDampEff or B.hold_damp) or 0.0
              local pull = math.min(B.hold_max_dv, overshoot * B.hold_gain * dtSim)
              addSubjectVelocity(state, vehicle, inward * (-(pull + damp)))
            end
            -- GAP BANKING ASSIST (b89 forensics - the complete force
            -- budget, at last). A circulating sample at 27 m/s on
            -- r 15.3 needs ~4.8 g centripetal. The slip field supplies
            -- ~60% per tick; the BANK FOOT (the 38%-slope band at
            -- r 15.2-15.7) physically supplies the rest via tire
            -- normal force - the crumbs show r pinned at 15.3 all the
            -- way around, then jumping +0.7 m at the mouth, where the
            -- flank fairing removed that support. The car side-slides
            -- across flat deck and shreds its tires: SEVEN geometry
            -- builds died at the identical spot because the missing
            -- force was never geometric. (b89's softened hold was the
            -- opposite of the fix and is reverted above.) This term
            -- applies exactly the bank-fraction centripetal
            -- (0.45 v_t^2/r, capped 30 m/s^2) through the gap sector,
            -- smoothstepped at the edges (force-continuous - the b79
        -- kick law), and only for samples with real tangential
            -- speed, so entering and exiting cars never feel it.
            if B.safety_enabled then
              local gateDir = toWorldDir(state, vec3(0, -1, 0))
              local rl = radial:length()
              local cgate = radial:dot(gateDir) / math.max(rl, 0.001)
              if cgate > 0.88 and rl > 13.5 then
                local tdir2 = axis:cross(radial)
                tdir2:normalize()
                local vt = velocity:dot(tdir2)
                if math.abs(vt) > 10.0 then
                  local s = math.min(1.0, (cgate - 0.88) / 0.09)
                  s = s * s * (3.0 - 2.0 * s)
                  local inw2 = vec3(radial.x, radial.y, radial.z)
                  inw2:normalize()
                  local assist = math.min(30.0,
                                          0.45 * vt * vt / math.max(rl, 8.0))
                  addSubjectVelocity(state, vehicle,
                                     inw2 * (-assist * s * dtSim))
                end
              end
            end
            local tangential = velocity - axis * velocity:dot(axis)
            if tangential:length() > (b.stats.peak_tangential_mps or 0) then
              b.stats.peak_tangential_mps = math.floor(tangential:length() * 10) / 10
            end
          else
            -- Dead-centre parking is a null spot for the tangential
            -- field: ease the sample outward so the drum can grab it.
            local out = toWorldDir(state, vec3(1, 0, 0))
            addSubjectVelocity(state, vehicle, out * math.min(1.5, dtSim * 12.0))
          end
          -- MOUTH LAUNCH (player 2026-08-09: "spit the car at the speed
          -- it's currently going out the front entrance"). Fires the
          -- first tick a sample sweeps into the doorway window once the
          -- aperture is real (open bake landed) and the leaf is clear.
          -- SET velocity (launchSubject, scale 0), never add: current
          -- horizontal speed, aimed at a far corridor-centreline point
          -- so an off-centre launch converges toward the middle of the
          -- opening instead of hugging a jamb. Window +/-10 deg with the
          -- eject_max_r 17.0 gate = >= 0.8 m of jamb corner margin
          -- (worked geometry in the tunables comment); sweep tops out
          -- ~14.3 deg/tick at the fastest reachable launch, under the
          -- 20 deg window, so a crossing cannot straddle-skip it.
          -- Runs AFTER the field/hold dv above - launchSubject replaces
          -- velocity outright, so the last word is the aim.
          if b.phase == "eject" and b.shelfReloaded
            and (b.shelfDrop or 0) >= B.shelf_drop - 0.001
            and (b.doorSlide or 0) >= math.rad(38.0)
            and radial:length() > 13.0
            and radial:length() <= B.eject_max_r then
            local gate = toWorldDir(state, vec3(0, -1, 0))
            local rl = radial:length()
            local tdirE = axis:cross(radial)
            tdirE:normalize()
            -- Red-team F8: only launch samples actually RIDING the drum
            -- (real CCW tangential speed). A player nosing IN through
            -- the open mouth mid-eject is a visitor, not cargo - the
            -- old check snap-launched them backwards out of the throat.
            if radial:dot(gate) > rl * B.eject_window_cos
              and velocity:dot(tdirE) > 6.0 then
              local hv = velocity - axis * velocity:dot(axis)
              local speed = math.max(B.eject_min_speed, hv:length())
              local aim = (center + gate * B.eject_aim_dist) - position
              aim = aim - axis * aim:dot(axis)
              if aim:length() > 0.5 then
                aim:normalize()
                if launchSubject(state, vehicle, aim * speed) then
                  b.ejected[vehicleId] = true
                  b.tracked[vehicleId] = nil
                  b.stats.mouth_ejects = (b.stats.mouth_ejects or 0) + 1
                  showMessage(string.format(
                    "SAMPLE EJECTED AT %d KM/H. Please exit in the "
                    .. "direction of travel.", math.floor(speed * 3.6)), 2.8)
                  emitEvent(state, "I", "centrifuge_mouth_eject", {
                    subject_id = vehicleId,
                    speed_mps = math.floor(speed * 10) / 10})
                end
              end
            end
          end
        end
      end
    end
  end
end

-- flingSample DELETED (2026-08-09): the tangential over-the-rim toss at
-- protocol end is superseded by the mouth eject ("spit the car at the
-- speed it's currently going out the front entrance"). The only remaining
-- ballistic exit is purgeBowl - housekeeping, not an ending.

behavior.update = function(state, dtSim)
  local b = state.behavior
  -- Quarantine decay lives HERE, not in the field loop: the field
  -- early-outs below 1 RPM and a quarantined carcass never healed at
  -- idle - unpurgeable forever (red-team F4/F6 interplay).
  if b.nodeSafety then
    for vid, t in pairs(b.nodeSafety) do
      if t > 0 then b.nodeSafety[vid] = t - dtSim end
    end
  end
  if b.phase == "idle" then
    local inside = interiorCount(state)
    if b.needEmpty and inside == 0 then
      -- The bowl has genuinely cleared since the last fling: unlatch.
      b.needEmpty = nil
    end
    if b.needEmpty and inside > 0 then
      -- SELF-CLEAN (red-team F6): a fouled drum used to sit silently
      -- disarmed forever unless the operator guessed PURGE. ~30 real
      -- seconds of idle foulage and the machine disposes of the carcass
      -- itself (purgeBowl skips quarantined samples; they get the next
      -- pass once their timer decays).
      b.foulT = (b.foulT or 0) + dtSim
      if b.foulT >= 90.0 then
        b.foulT = 0
        local cleared = purgeBowl(state)
        if cleared > 0 then
          showMessage(
            "SELF-CLEANING ENGAGED. The management apologizes for the "
            .. "debris.", 3.0)
          emitEvent(state, "I", "centrifuge_selfclean", {})
        end
      end
    else
      b.foulT = 0
    end
    if b.rpm > 0.5 then
      b.rpm = math.max(0, b.rpm - B.spin_down_per_s * dtSim)
      b.speedCap = math.max(0, (b.speedCap or 0) - 25.0 * dtSim)
    elseif not b.needEmpty and armableCount(state) > 0 then
      b.speedCap = 0
      armSpin(state, nil)
    end
  elseif b.phase == "spinning" then
    if b.manual then
      -- Manual hold: track the operator's stage in both directions, no
      -- escalation, no fling, empty bowl allowed.
      local target = B.rpm_stages[b.stage]
      local speedTarget = B.stage_speeds_mps[math.max(1, math.min(b.stage,
        #B.stage_speeds_mps))]
      -- THE FLOOR GATE (red-team finding 3): the drum does not
      -- accelerate past gentle-carousel drag until the doorway floor
      -- is settled. 32 RPM keeps the mouth crossings in the proven
      -- benign regime AND stays above the 30-RPM tracking threshold,
      -- so a blocker holding the rise interlock still accrues stall
      -- and gets auto-purged instead of jamming the machine forever.
      -- OCCUPIED-SCOPED (occupancy rule 2026-08-09): the gate protects
      -- mouth-crossers; an empty drum spinning with its mouth open has
      -- none, and clamping it would cap the empty demonstration at 32.
      if (b.shelfDrop or 0) > 0.0 and interiorCount(state) > 0 then
        target = math.min(target, 32.0)
        speedTarget = math.min(speedTarget, 8.0)
      end
      if b.rpm < target then
        b.rpm = math.min(target, b.rpm + B.rpm_ramp_per_s * dtSim)
      elseif b.rpm > target then
        b.rpm = math.max(target, b.rpm - B.spin_down_per_s * 0.4 * dtSim)
      end
      if (b.speedCap or 0) < speedTarget then
        b.speedCap = math.min(speedTarget, (b.speedCap or 0)
          + B.cap_ramp_mps2 * dtSim)
      else
        b.speedCap = math.max(speedTarget, b.speedCap - 8.0 * dtSim)
      end
      if b.rpm > (b.stats.max_rpm or 0) then
        b.stats.max_rpm = math.floor(b.rpm)
      end
    else
      -- Player 2026-08-08: the crescendo COMPLETES - the drum tops out at
      -- 500 RPM by the 60 s mark even when the sample leaves the bowl.
      -- This used to abort to spindown the moment interiorCount hit zero,
      -- and since every stock car is ejected around stage 10, the machine
      -- had never once demonstrated its top rung. Announce the loss once
      -- and keep climbing.
      if interiorCount(state) == 0 and not b.sampleLost then
        -- Message deleted 2026-08-10 (player); the latch and the
        -- telemetry event both stay.
        b.sampleLost = true
        emitEvent(state, "I", "centrifuge_abandoned", {})
      end
      local target = B.rpm_stages[b.stage]
      local prev = b.stage > 1 and B.rpm_stages[b.stage - 1] or 0.0
      local speedTarget = B.stage_speeds_mps[math.max(1, math.min(b.stage,
        #B.stage_speeds_mps))]
      -- THE FLOOR GATE (red-team finding 3, same as the manual branch):
      -- no hypergravity until the doorway floor is settled. The clamp
      -- self-releases the tick after the shelf bakes; under a rise-
      -- interlock hold it keeps every open-mouth crossing in the
      -- benign sub-9 m/s regime until the auto-purge clears the holder.
      -- OCCUPIED-SCOPED (occupancy rule 2026-08-09): an empty crescendo
      -- runs open-mouthed at full song; the tick a sample drives in,
      -- interiorCount arms this clamp and the drum falls to intake
      -- speed while the mouth seals behind the newcomer.
      if (b.shelfDrop or 0) > 0.0 and interiorCount(state) > 0 then
        target = math.min(target, 32.0)
        speedTarget = math.min(speedTarget, 8.0)
      end
      b.speedCap = math.min(speedTarget, (b.speedCap or 0)
        + B.cap_ramp_mps2 * dtSim)
      -- Round 15 (player): "make the ramp up in RPMs change second by
      -- second". The old constant 28 RPM/s slew crossed each rung gap in
      -- a couple of sim-seconds and then sat FLAT for the whole hold -
      -- chunky. The rate is now per-stage: each climb is spread across
      -- rpm_ramp_fill of the hold window, so the drum accelerates the
      -- entire inter-stage interval like a real motor and plateaus only
      -- long enough for the taunt to land. The hold clock runs from
      -- stage entry; advancing still requires the wall-speed cap to have
      -- caught up, which it always does mid-climb (4.5 m/s^2 vs a 14 s
      -- window).
      local last = b.stage >= #B.rpm_stages
      local hold = last and B.max_hold_seconds or B.stage_hold_seconds
      local rate = (target - prev)
        / math.max(1.0, hold * (B.rpm_ramp_fill or 0.9))
      b.stageTimer = b.stageTimer + dtSim
      if b.rpm < target then
        local before = b.rpm
        b.rpm = math.min(target, b.rpm + rate * dtSim)
        if before < target and b.rpm >= target then
          showMessage(STAGE_LINES[b.stage] or "...", 2.6)
          emitEvent(state, "I", "centrifuge_stage", {
            stage = b.stage, rpm = math.floor(b.rpm)})
        end
      elseif b.rpm > target then
        -- Only reachable under the floor gate (auto stages never
        -- regress): wind the dial down with the drag so the machine
        -- doesn't read 137 RPM while cars crawl at carousel speed.
        b.rpm = math.max(target, b.rpm - B.spin_down_per_s * 0.4 * dtSim)
      end
        if b.stageTimer >= hold and b.rpm >= target
            and b.speedCap >= speedTarget - 0.1 then
          if last then
            -- Ladder complete. EVERY occupied ending is now the mouth
            -- eject (player 2026-08-09) - intact or wreck, the sample
            -- goes out the front entrance at the speed it is going.
            -- beamstate.damage reaches the GE side as
            -- map.objects[id].damage; it only flavours the message.
            local worst = 0
            for vehicleId in pairs(zoneOccupants(state, "drum_zone")) do
              local vehicle = exactVehicle(vehicleId)
              if vehicle and insideBowl(state, vehicle:getPosition()) then
                local data = map and map.objects and map.objects[vehicleId]
                local hurt = data and data.damage or 0
                if hurt > worst then worst = hurt end
              end
            end
            if interiorCount(state) == 0 then
              -- Sample left mid-ladder; the drum still topped out. Take a
              -- bow and wind down - nothing to eject, and no needEmpty
              -- latch (it is already empty).
              -- Message deleted 2026-08-10 (player); the phase change
              -- and the completion event both stay.
              b.phase = "spindown"
              emitEvent(state, "I", "centrifuge_complete", {empty = true})
            else
              enterEject(state, worst)
            end
          else
            b.stage = b.stage + 1
            b.stageTimer = 0
          end
        end
      if b.rpm > (b.stats.max_rpm or 0) then
        b.stats.max_rpm = math.floor(b.rpm)
      end
    end
  elseif b.phase == "eject" then
    -- MOUTH EJECT choreography (player 2026-08-09). The drum bleeds to
    -- the eject cap while the mouth opens under THREE nested gates: the
    -- travel gate below latches b.ejectMouthGo (burial may only start
    -- with every sample predicted clear for the whole travel - red-team
    -- F1), the arrival bake gate backstops the collision swap, and the
    -- leaf follows the certified floor-first sequence. The LAUNCHES
    -- live in applySpinField, the first tick each sample sweeps into
    -- the doorway window. rpm holds at eject_rpm_floor, NOT zero:
    -- below 30 the field drops outer-band cars (door protection) and
    -- below 20 the stall purge disarms - the eject needs both alive.
    b.rpm = math.max(B.eject_rpm_floor, b.rpm - B.spin_down_per_s * dtSim)
    local cap = b.ejectCap or B.eject_speed_mps
    if (b.speedCap or 0) > cap then
      b.speedCap = math.max(cap, b.speedCap - 25.0 * dtSim)
    else
      b.speedCap = math.min(cap, (b.speedCap or 0) + B.cap_ramp_mps2 * dtSim)
    end
    b.ejectTimer = (b.ejectTimer or 0) + dtSim
    -- TRAVEL GATE latch (red-team F1): the burial may only start once
    -- every sample is predicted clear for the whole travel. One-way per
    -- eject: once moving, the arrival bake gate is the backstop.
    if not b.ejectMouthGo and clearForTravel(state) then
      b.ejectMouthGo = true
    end
    local remaining = 0
    for vehicleId in pairs(zoneOccupants(state, "drum_zone")) do
      local vehicle = exactVehicle(vehicleId)
      if vehicle and not (b.ejected and b.ejected[vehicleId])
        and insideBowl(state, vehicle:getPosition()) then
        remaining = remaining + 1
      end
    end
    if remaining == 0 then
      -- DEBOUNCED (b107 probe): trigger rebuilds blank the occupant set
      -- for a tick, and a single blank tick used to end the eject around
      -- a still-circulating sample mid-lap. A full second of genuinely
      -- empty readings is required before the throw is declared done.
      b.ejectEmptyT = (b.ejectEmptyT or 0) + dtSim
    else
      b.ejectEmptyT = 0
    end
    if remaining == 0 and (b.ejectEmptyT or 0) >= 1.0 then
      -- Everyone is out (or airborne and leaving). If a launched car
      -- wrecked back INTO the bowl, latch needEmpty so the idle arm
      -- cannot restart the protocol on a carcass.
      b.phase = "spindown"
      if interiorCount(state) > 0 then b.needEmpty = true end
      emitEvent(state, "I", "centrifuge_eject_done", {})
    elseif b.ejectTimer >= B.eject_timeout then
      -- The mouth never lined up (seized wreck, blocked bake). The
      -- machine does not jam - round-15 law. Volcano the stragglers.
      local cleared = purgeBowl(state)
      if cleared > 0 then
        showMessage(
          "EJECTION TIMED OUT - PURGING THE STRAGGLERS SKYWARD.", 2.8)
      end
      b.needEmpty = true
      b.phase = "spindown"
    end
  elseif b.phase == "spindown" then
    b.rpm = math.max(0, b.rpm - B.spin_down_per_s * dtSim)
    b.speedCap = math.max(0, (b.speedCap or 0) - 25.0 * dtSim)
    if b.rpm <= 0.5 then
      b.phase = "idle"
      b.stage = 0
      b.sampleLost = nil
      emitEvent(state, "I", "centrifuge_idle", {})
    end
  end
  applySpinField(state, dtSim)
  local omega = (b.rpm or 0) * math.pi / 30.0
  b.rotorAngle = ((b.rotorAngle or 0)
    + math.min(6.5, omega) * dtSim) % (2 * math.pi)
  -- Beacon spins at a fixed lamp rate while the protocol runs; parked
  -- otherwise so the retracted head never grinds inside its housing.
  local beaconRate = (b.phase == "spinning" or b.phase == "eject")
    and (B.beacon_rate or 3.0) or 0.0
  b.beaconAngle = ((b.beaconAngle or 0) + beaconRate * dtSim) % (2 * math.pi)
  -- SPIN FX push (2026-08-09c, mechanism v3): the VEHICLE-side lua owns
  -- both the amber emergency-light chase (stock SPOTLIGHT jbeam props -
  -- the cop-light mechanism the player asked to borrow) and the spin
  -- soundtrack (obj:createSFXSource loop - the mod-siren raw-ogg path,
  -- the proven-audible one after two GE-side mechanisms tested silent).
  -- One edge-triggered flag crosses the GE/vehicle boundary; the loop
  -- starts and stops exactly with the spinning, eject included.
  -- b.fxKill (player 2026-08-12): latched TRUE by the STOP button (the
  -- E-Stop cuts the music the instant it is pressed, even though the
  -- machine still spends a few seconds throwing the occupant out) and
  -- by the end-of-clip handoff below. Cleared wherever a fresh spin
  -- session starts. While latched the soundtrack stays off for the
  -- rest of the session; the falling edge it causes is what cues the
  -- shutdown one-shot.
  local wantFx = (b.phase == "spinning" or b.phase == "eject")
    and not b.fxKill
  -- Player 2026-08-09d ("good audio timing"): the soundtrack started
  -- 3.5 s AFTER the spin began - the drum audibly wound up first, then
  -- the music entered. 2026-08-11 that delay went to ZERO: the clip now
  -- opens with a helicopter rotor start-up at full level from sample
  -- zero ("have this sound start as soon as the centrifuge starts
  -- spinning"), and the riser bed behind it fades up across 5 s. The
  -- rotor IS the wind-up the delay used to leave room for, so keeping
  -- both would start the rotor 3.5 s late and push the bed out to 8.5 s.
  -- Hardcoded, not a B tunable: new BEHAVIOR keys require a Blender
  -- handoff pass (standing law) and this is a timing constant.
  if wantFx then
    b.fxDelayT = (b.fxDelayT or 0) + dtSim
  else
    b.fxDelayT = 0
  end
  -- End-of-clip handoff (player 2026-08-12: "when the sequence sound
  -- ends, this sound should play"): the spinup ogg runs 191.2 s with a
  -- tail fade ending at 191.2, but the SFX source is a LOOP profile -
  -- left alone it would wrap and restart the rotor head mid-session.
  -- Kill at 191.0 s (inside the faded tail, inaudible as a cut) so a
  -- manual hold that outlives the music hands off to the shutdown
  -- one-shot instead of looping. 191.0 is a clip-length constant, not
  -- a B tunable (same standing law as the delay above).
  if wantFx and (b.fxDelayT or 0) >= 191.0 then
    b.fxKill = true
    wantFx = false
  end
  local wantPlay = wantFx and (b.fxDelayT or 0) >= 0.0
  if wantPlay ~= (b.spinFxOn or false) then
    local wasOn = b.spinFxOn and true or false
    b.spinFxOn = wantPlay
    pcall(function()
      local propObj = be:getObjectByID(state.propId)
      if propObj then
        propObj:queueLuaCommand(string.format(
          "if extensions.%s_vehicle and extensions.%s_vehicle.setSpinActive"
          .. " then extensions.%s_vehicle.setSpinActive(%s) end",
          PROP_MODEL, PROP_MODEL, PROP_MODEL,
          wantPlay and "true" or "false"))
        -- Shutdown one-shot rides the SAME edge that stops the loop:
        -- every way the soundtrack can end (E-Stop, sequence complete,
        -- eject done or timed out, end-of-clip) funnels through this
        -- falling edge, so the power-down always enters exactly as the
        -- music leaves and can never double-fire.
        if wasOn and not wantPlay then
          propObj:queueLuaCommand(string.format(
            "if extensions.%s_vehicle and extensions.%s_vehicle.playShutdown"
            .. " then extensions.%s_vehicle.playShutdown() end",
            PROP_MODEL, PROP_MODEL, PROP_MODEL))
          b.shutdownT = 0
        end
      end
    end)
  end
  -- Fake-one-shot stop clock: the shutdown source is a LOOP profile
  -- (the only proven-audible path), so stop it 11.2 s after the play -
  -- inside the clip's 2.5 s silent tail pad (audible end 10.9, wrap
  -- 13.39), where the cut is silent and slow-motion clock drift has
  -- 2.2 s of margin before the wrap could re-clunk.
  if b.shutdownT then
    b.shutdownT = b.shutdownT + dtSim
    if b.shutdownT >= 11.2 then
      b.shutdownT = nil
      pcall(function()
        local propObj = be:getObjectByID(state.propId)
        if propObj then
          propObj:queueLuaCommand(string.format(
            "if extensions.%s_vehicle and extensions.%s_vehicle.stopShutdown"
            .. " then extensions.%s_vehicle.stopShutdown() end",
            PROP_MODEL, PROP_MODEL, PROP_MODEL))
        end
      end)
    end
  end
  -- Player rule (2026-08-05): the entrance slides away for entry and
  -- seals once the machine runs, so the raceway is continuous while a
  -- sample is being spun. Idle = open, anything else = closed.
  -- "eject" commands the mouth open the moment it begins - that IS the
  -- ejection: the collision bake stays deferred behind the sector-clear
  -- gate below, so cars still riding the sealed profile keep their floor
  -- until the swap is provably safe. "spindown" opens too: it only ever
  -- follows an empty or needEmpty-latched bowl in this machine, and
  -- opening early is what guarantees an approaching player finds the
  -- mouth OPEN, not half-way (player 2026-08-09 approach screenshot).
  -- phaseOpen is the PHYSICS signal (drives the shelf); doorOpen is the
  -- THEATER signal (drives the leaf) and may additionally be held open
  -- by the corridor scan below. They were one variable until the
  -- red-team pass (2026-08-09) proved the coupling recreated the
  -- fall-in bug: any corridor holder pinned the shelf BURIED while the
  -- drum spun.
  -- OCCUPANCY RULE (player 2026-08-09, screenshot of the sealed leaf
  -- from the ramp: "this grey metal door should be open before a vehicle
  -- enters the centrifuge and then close when a vehicle enters"). The
  -- seal exists for RIDERS - raceway continuity while a sample is spun.
  -- An empty drum has no riders: the 2026-08-08 empty crescendo used to
  -- seal for its whole ~61 s demonstration and every approaching player
  -- met a giant closed slab. Sealed is now required ONLY while spinning
  -- WITH a sample aboard; the moment one drives in, interiorCount flips,
  -- the rise interlock walks the shelf up behind it and the (occupied-
  -- scoped) floor gate keeps the drum at intake speed until the mouth
  -- is sealed - exactly the player's requested cycle.
  local phaseOpen = b.phase == "idle" or b.phase == "eject"
    or b.phase == "spindown"
    or (b.phase == "spinning" and interiorCount(state) == 0)
  local doorOpen = phaseOpen
  -- ENTRY INTERLOCK (2026-08-07). A closed leaf bridges the tunnel: its
  -- surface stands ~1.2 m over the ramp deck, and the built mesh measured
  -- only 0.55 m of headroom at r 16.  Nothing that can wall off the only
  -- way in may be driven by phase alone, so a vehicle anywhere in the
  -- doorway corridor pins the door open no matter what the drum is doing.
  if not doorOpen then
    local centre = toWorldPoint(state, B.spin_center)
    local axis = toWorldDir(state, vec3(0, 0, 1))
    local gate = toWorldDir(state, vec3(0, -1, 0))
    for _, zoneName in ipairs({"rim_zone", "drum_zone"}) do
      for vehicleId in pairs(zoneOccupants(state, zoneName)) do
        local vehicle = exactVehicle(vehicleId)
        if vehicle then
          local offset = vehicle:getPosition() - centre
          local radial = offset - axis * offset:dot(axis)
          local dist = radial:length()
          -- OUTSIDE THE DRUM WALL ONLY (rim is 19.5). Two earlier cuts at
          -- this both failed live: `dist > 8.0` matched a car circulating
          -- the deck, and `dist > 15.6` still matched one wall-riding the
          -- bank at r 16-19 - either way every lap past the doorway
          -- re-opened the leaf and the ring never sealed. Nothing that is
          -- being spun can reach past the rim, so only a vehicle genuinely
          -- out in the tunnel holds the door.
          if dist > 19.8 and dist < 34.0
            and radial:dot(gate) > dist * 0.90 then
            doorOpen = true
            break
          end
        end
      end
      if doorOpen then break end
    end
  end
  -- Retract straight DOWN into a pocket under the bank: rotating it along
  -- the wall left flat panels sticking into the driving line (player).
  -- Slides along the ring like a pocket door (player: "star trek door,
  -- but curved to match the ring"), 28 deg into the neighbouring sector.
  -- The leaf may only SHOW open when the shelf is genuinely lowered -
  -- an open-looking doorway over a raised (solid) shelf would be a lie
  -- cars drive into. At eject this sequences the choreography floor-
  -- first: the shelf sinks until its top actually clears the deck, then
  -- the leaf slides. Written as a FRACTION of shelf_drop so the gate
  -- tracks drop changes instead of silently loosening. Calibration for
  -- the b140 full-height shelf: top starts at 7.0, deck is 2.35, so the
  -- doorway is passable once sunk >= (7.0 - 2.45) = 4.55 of 5.5 = 0.83;
  -- 0.85 adds margin. (The old 0.75 was the same calculation for the
  -- 4.877-tall shelf of the 3.2 m drop era: 0.75 * 3.2 = 2.4.)
  -- 40 deg, not 28 (b97 interior shot): the open leaf used to tuck
  -- behind the full-height bank, but the visual fairing scooped that
  -- sheet down and left the parked leaf's upper half standing naked on
  -- the flank - a slab that LOOKS like collision. At 40 deg the whole
  -- leaf (25.7 deg of arc) parks beyond the fairing blend zone
  -- (cut + one segment = az 296), fully concealed by unfaired bank.
  local doorTarget = (doorOpen
      and (b.shelfDrop or B.shelf_drop) > B.shelf_drop * 0.85)
    and math.rad(40.0) or 0.0
  local slide = b.doorSlide or 0
  if slide < doorTarget then
    b.doorSlide = math.min(doorTarget, slide + math.rad(34.0) * dtSim)
  elseif slide > doorTarget then
    b.doorSlide = math.max(doorTarget, slide - math.rad(34.0) * dtSim)
  end
  -- NO door collision reload (red-team finding 2): the leaf is
  -- collisionless, but its legacy endpoint bakes were GLOBAL - every
  -- door settle 0.82 s into a shelf travel snapshotted the shelf
  -- MID-POSE, parking invisible collision at arbitrary heights in the
  -- lane. The shelf is the only reload requester in this prop now.
  -- ============ MOUTH SHELF (build 95: "vehicles fall into entrance",
  -- player screenshot 2026-08-09 of a car nose-down INSIDE the doorway
  -- band). The aperture had NO riding surface while spinning: the leaf
  -- is collisionless theater, so a dragged car crossing the doorway
  -- dropped into the faired collision depression under the full-height
  -- visual bank. The shelf is a solid wedge whose raised top IS the
  -- faired swale (spec.faired_bank_z), so during spin the mouth sector
  -- carries one continuous crossing surface from flank to flank.
  -- Collision follows the pose only at ENDPOINT bakes (door lesson);
  -- both endpoints are safe surfaces, so staleness is structurally
  -- harmless: stale-raised = the legit crossing floor, stale-buried =
  -- under the ramp.
  -- PHASE drives the shelf, never the corridor hold (red-team finding
  -- 1: a parked tunnel car used to pin the shelf buried while the drum
  -- spun - the fall-in bug restored). While the shelf is unsettled the
  -- ramp clamps in behavior.update keep the drum at gentle-carousel
  -- speed, so an open mouth is only ever crossed slowly.
  -- During eject the phase alone does NOT open the mouth: the travel
  -- gate (clearForTravel, red-team F1) must have latched first, so the
  -- pose never leads the bake by more than one certified travel leg.
  local mouthCommanded = phaseOpen
  if b.phase == "eject" and not b.ejectMouthGo then
    mouthCommanded = false
  end
  local shelfTarget = mouthCommanded and B.shelf_drop or 0.0
  local drop0 = b.shelfDrop or B.shelf_drop
  local sCentre = toWorldPoint(state, B.spin_center)
  local sAxis = toWorldDir(state, vec3(0, 0, 1))
  local sGate = toWorldDir(state, vec3(0, -1, 0))
  local function eachShelfVehicle(fn)
    -- Ground truth over zone occupancy (red-team finding: trigger
    -- rebuilds blank the occupant sets for a tick, and spawned-in-place
    -- cars may never fire an enter event).
    local ok, all = pcall(getAllVehicles)
    if ok and type(all) == "table" then
      for _, vehicle in ipairs(all) do
        if fn(vehicle) then return true end
      end
      return false
    end
    for vehicleId in pairs(zoneOccupants(state, "drum_zone")) do
      local vehicle = exactVehicle(vehicleId)
      if vehicle and fn(vehicle) then return true end
    end
    return false
  end
  if shelfTarget == 0.0 and drop0 > 0.0 then
    -- RISE INTERLOCK: never inflate collision under a vehicle. Slow
    -- traffic (< 9 m/s, the whole footprint) and ANY vehicle over the
    -- tall back-face annulus (r 17.1+, where the raised wedge stands
    -- 2 m proud) hold the rise. Dragged crossers orbit at r <= 16.9
    -- and 15+ m/s, so they hold nothing - they are why the shelf
    -- exists. Guard runs to drop == 0 (the old 0.05 cutoff left the
    -- last 62 ms unguarded).
    eachShelfVehicle(function(vehicle)
      local offset = vehicle:getPosition() - sCentre
      local along = offset:dot(sAxis)
      local radial = offset - sAxis * along
      local dist = radial:length()
      -- 0.88 = cos(~28.4 deg): the b100 full-profile patch spans cage
      -- cols 19..23 (half-angle 25.7 deg), wider than the old swale
      -- wedge.
      if along >= 3.6 or radial:dot(sGate) <= dist * 0.88 then
        return false
      end
      local okv, vel = pcall(function() return vehicle:getVelocity() end)
      local speed = (okv and vel) and vel:length() or 0.0
      -- Outer bound 17.95 = the patch's true footprint (max r 17.867)
      -- plus margin: a car at 18.0+ is entirely beyond it, so the
      -- rise cannot touch it - holding for it just jammed the machine
      -- (b97 probe). Any-speed hold from 16.8: the full-profile patch
      -- rises 1.5-2.1 m into the air out there.
      if (dist > 14.6 and dist < 17.95 and speed < 9.0)
        or (dist > 16.8 and dist < 17.95) then
        shelfTarget = B.shelf_drop
        return true
      end
      return false
    end)
  elseif shelfTarget > 0.0 and drop0 < B.shelf_drop
    and b.phase ~= "eject" then
    -- FALL INTERLOCK (red-team finding 4): never yank the floor from
    -- under a vehicle standing on the swale (r < 17.2 - NOT the back-
    -- face annulus, else a survivor waiting at the closed door would
    -- deadlock the fall). SKIPPED during eject: samples sweep this
    -- sector every lap at speed and would stall the travel forever -
    -- there the deferred BAKE gate, not the interlock, is the safety
    -- (visual travel under a crosser is harmless while the collision
    -- stays sealed at the closed endpoint).
    local holder = nil
    eachShelfVehicle(function(vehicle)
      local offset = vehicle:getPosition() - sCentre
      local along = offset:dot(sAxis)
      local radial = offset - sAxis * along
      local dist = radial:length()
      if along < 3.6 and dist > 14.6 and dist < 17.2
        and radial:dot(sGate) > dist * 0.88 then
        holder = vehicle
        shelfTarget = 0.0
        return true
      end
      return false
    end)
    -- IDLE DOORWAY-SQUATTER PURGE (player 2026-08-09: "the entrance
    -- seems partially closed when I approach"). A wreck parked in this
    -- band pins the shelf raised and the leaf sealed FOREVER at idle -
    -- every later approach met a half-closed mouth. The machine now
    -- warns (~15 real s of continuous squatting) and then volcanoes the
    -- squatter (~25 real s). Living players crossing the band reset the
    -- clock the moment they leave it.
    if holder and b.phase == "idle" then
      b.doorSquatT = (b.doorSquatT or 0) + dtSim
      if b.doorSquatT >= B.door_squat_purge_s then
        local offset = holder:getPosition() - sCentre
        local radial = offset - sAxis * offset:dot(sAxis)
        local velocity
        if radial:length() > 0.3 then
          radial:normalize()
          velocity = radial * B.purge_out_mps + sAxis * B.purge_up_mps
        else
          velocity = sAxis * B.purge_up_mps
        end
        if launchSubject(state, holder, velocity) then
          -- Flourish dropped 2026-08-10 (player). The line itself stays:
          -- being launched out of the doorway without warning would read
          -- as the machine malfunctioning.
          showMessage("DOORWAY CLEARED BY FORCE.", 2.8)
          emitEvent(state, "I", "door_squat_purge", {})
        end
        b.doorSquatT = 0
        b.doorSquatWarned = nil
      elseif b.doorSquatT >= B.door_squat_warn_s
        and not b.doorSquatWarned then
        showMessage("CLEAR THE DOORWAY. The machine is patient. Briefly.", 2.8)
        b.doorSquatWarned = true
      end
    else
      b.doorSquatT = 0
      b.doorSquatWarned = nil
    end
  else
    b.doorSquatT = 0
    b.doorSquatWarned = nil
  end
  local drop = drop0
  if drop > shelfTarget then
    drop = math.max(shelfTarget, drop - B.shelf_rise_mps * dtSim)
  elseif drop < shelfTarget then
    drop = math.min(shelfTarget, drop + B.shelf_fall_mps * dtSim)
  end
  if drop ~= b.shelfDrop then
    b.shelfDrop = drop
    b.shelfReloaded = false
  elseif not b.shelfReloaded then
    -- EJECT BAKE GATE (2026-08-09). The endpoint bake is a GLOBAL
    -- collision swap; during eject the open-endpoint bake may only land
    -- while every interior sample is >72 deg from the mouth, so no car
    -- ever has the floor vanish mid-crossing. Until it lands, crossers
    -- ride the sealed closed-profile collision (certified regime) under
    -- an already-sunken visual - a sub-2 s cosmetic divergence, spent at
    -- the far side of the drum by construction. Idle/spindown arrivals
    -- bake immediately (b95-b101 certified low-speed behavior).
    local bakeOk = true
    if b.phase == "eject" then
      bakeOk = mouthSectorClear(state)
    end
    if bakeOk then
      b.shelfReloaded = true
      requestCollisionReload(state)
    end
  end
  poseSpinners(state)
end
"""
