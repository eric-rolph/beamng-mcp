"""Charlie's High Five — authored constants for Blender + runtime.

A five-storey foam-latex right hand on a slewing steel boom beside the
road. Drive into the approach lane and the fingers twitch, the arm cocks
back up-road, and the whole rig WHIPS around its mast to backhand you down
the tarmac. POWER 1-10 scales the slap; TILT 0-60 deg rolls the wrist so
the palm meets you flat (a skipping slapshot) or canted back (a punt into
low orbit). The launch always leaves along the palm normal, because that
is the only direction a slap can send anything.

Reference (2026-08-24): the *Jackass 3D* "High Five" gag — a giant tan
foam hand on a horizontal axle carried by a matte-black rigging post with
a ball finial, a bolted flange base and a chain-and-turnbuckle return.
Frames pulled at 0/6/93/100.5 s. The visual language of the STAND is
copied deliberately: matte black, exposed fasteners, obviously a rig. The
HAND is not copied — it is generated here from human proportions at
HAND_SCALE, so every crease and knuckle has a measurable source.

Why a fifth swinging contraption is not a fourth flyswatter. The pack
already lands things vertically (`monster_flyswatter` slams down,
`boot_of_doom` punts up, `catapult_seesaw` flings). This one sweeps a
HORIZONTAL cone at bumper height, so the strike arrives from behind-left
in the mirror and the car leaves down-road on the tangent. It is also the
only prop in the pack that LEADS its subject: the runtime reads the
subject's closing speed every frame and starts the swing so the palm
arrives when the car does, instead of firing on a fixed timer and
whiffing at anything other than 25 m/s (see `swing_lead_seconds`).

===========================================================================
The hand is derived, not sculpted
===========================================================================

Every dimension of the hand below is a real hand measurement multiplied by
one number. HUMAN_HAND_M is the standard adult male hand length — wrist
crease to middle fingertip, 195 mm — and HAND_SCALE is whatever it takes
to reach HAND_LENGTH. Nothing in the generator may use a "looks about
right" radius: if a proportion is not in this file with its human source
in millimetres beside it, it does not exist.

That is the same law the Colossus tire runs under (the size code is the
generator's input), and it exists for the same reason: the moulded detail
and the silhouette cannot drift apart if they are computed from one
number. It also means the hand is re-scalable — change HAND_LENGTH and
every crease, nail and knuckle moves with it.

===========================================================================
Frame
===========================================================================

Authored frame: right-handed, meters, Z-up, +Y is the drive direction.
The mast stands off the -X shoulder; the road runs along X = 0. The
origin IS the strike point: at contact azimuth the palm centre passes
exactly through (0, 0, WRIST_Z).

Hand-local axes, used throughout the generator:

    u   proximal -> distal   (wrist -> fingertips)
    v   ulnar -> radial      (little-finger side -> thumb side)
    n   dorsal -> volar      (back of hand -> out of the palm)

For a RIGHT hand these satisfy ``n = v x u``. With the fingers pointing
radially outward from the mast and the palm facing the sweep tangent,
that identity puts v at +Z — thumb UP — which is exactly a natural
forehand slap and is why the pose needed no fudging.
"""

import math

MOD_ID = "ericrolph_high_five"
DISPLAY_NAME = "Charlie's High Five"
VALUE_DOLLARS = 46000
ZIP_BASENAME = "high_five_ericrolph.zip"

# Nothing under assets/ is loaded by the game at runtime: the hand is
# generated, not imported, so there is no hero GLB to ship.
# The slap thwack: synthesized from source by authoring/make_slap_audio.py
# (deterministic, seeded), played through the pack's only proven-audible
# path (obj:createSFXSource, the centrifuge mechanism).
SHIP_ASSETS = ("sound/ericrolph_high_five_slap.ogg",)

# Vehicle-side Lua: the one-shot slap sound. The loop profile is the only
# proven-audible path, so the clip carries a 1.2 s silent tail and the GE
# runtime queues the stop while the cursor is inside it -- the cut is never
# heard and the wrap is never reached (the centrifuge's defuse, 2026-08-09).
VEHICLE_LUA_EXTRA = f'''
local slapSfxId = nil
local SLAP_OGG = "vehicles/{MOD_ID}/sound/{MOD_ID}_slap.ogg"

local function playSlap()
  if slapSfxId == nil then
    local ok, id = pcall(function()
      return obj:createSFXSource(SLAP_OGG, "AudioDefaultLoop3D",
        "high_five_slap", 0)
    end)
    slapSfxId = (ok and id) or nil
    if slapSfxId then
      pcall(function() obj:setVolumePitch(slapSfxId, 1.0, 1) end)
    end
  end
  if slapSfxId then pcall(function() obj:playSFX(slapSfxId) end) end
end

local function stopSlap()
  if slapSfxId then pcall(function() obj:stopSFX(slapSfxId) end) end
end

M.playSlap = playSlap
M.stopSlap = stopSlap
'''

# ---------------------------------------------------------------------------
# Hand anatomy — one scale factor, human millimetres beside every ratio
# ---------------------------------------------------------------------------
# Sources are standard adult-male hand anthropometry (hand length 195 mm,
# palm width across the metacarpal heads 88 mm, palm length wrist-crease
# to middle MCP 105 mm). Ratios below are stored as the raw millimetre
# figure over 195 so the provenance survives a change of HAND_LENGTH.

HUMAN_HAND_M = 0.195
HAND_LENGTH = 8.60                       # wrist crease -> middle fingertip
HAND_SCALE = HAND_LENGTH / HUMAN_HAND_M  # 44.10

def _mm(millimetres: float) -> float:
    """A human hand dimension in mm, at this hand's scale, in metres."""

    return round(millimetres / 1000.0 * HAND_SCALE, 4)


PALM_LENGTH = _mm(105.0)      # wrist crease -> middle metacarpal head
PALM_WIDTH = _mm(88.0)        # across the metacarpal heads
PALM_THICK_WRIST = _mm(34.0)  # dorsal-volar at the wrist crease
PALM_THICK_MCP = _mm(26.0)    # dorsal-volar at the knuckles
WRIST_WIDTH = _mm(62.0)       # across the styloids
WRIST_THICK = _mm(38.0)

# Finger lengths measured from the MCP crease. 105 + 90 = 195 pins the
# middle finger; the rest are the standard ratios to it.
FINGER_LENGTH_MM = {
    "index": 90.0 * 0.850,
    "middle": 90.0,
    "ring": 90.0 * 0.920,
    "little": 90.0 * 0.700,
}
# Proximal-phalanx diameter, ungloved, at the base.
# Proximal-phalanx diameter at the base. Nudged 8% over the anthropometric
# figures on purpose: this is a CAST FOAM PROP, and a mould that thin at
# 44x scale would not survive being swung, which is also why the reference
# hand's fingers are visibly chunkier than the hand they were cast from.
FINGER_DIAMETER_MM = {"index": 24.0, "middle": 24.5, "ring": 23.0, "little": 19.5}
# Proximal : middle : distal phalanx split of the finger length.
PHALANX_SPLIT = (0.45, 0.32, 0.23)

# Metacarpal heads sit on an arc, not a line: the index head is the most
# distal and the little head the most proximal and lowest. (dv, du) are
# offsets from the MIDDLE head, in human mm, v = toward the thumb.
# Spread is checked against PALM_WIDTH: index-to-little centres (66 mm)
# plus the outer half-diameters (9.5 + 7.5) come to 83 of the 88 mm the
# palm is wide, which leaves the 5 mm of rounded shoulder a real hand has
# and nothing more. An earlier 56 mm spread left 15 mm of bare palm
# sticking out past the knuckles on each side, and the distal end read as
# a chopped loaf because nothing covered it.
MCP_OFFSET_MM = {
    "index": (24.0, -4.0),
    "middle": (0.0, 0.0),
    "ring": (-22.0, -5.0),
    # -42 put this head 90 mm from the palm's own ulnar edge, and everything
    # distal of it hung off the bottom of the machine. -38 keeps the head
    # row covering the palm (checked by test_metacarpal_heads_cover...) and
    # buys 0.18 m of ground clearance.
    "little": (-38.0, -15.0),
}
# Splay about the palm normal, measured from the middle ray, and the
# relaxed curl at each joint. An open hand is not a flat hand: even at
# rest the fingers carry ~15 deg of MCP flexion, which is what stops a
# generated hand reading as a cartoon glove.
# Splay, measured from the middle ray. Pulled in from 12/-9/-16 after the
# first textured render: at -16 the little fingertip sat at v = -2.62
# against a palm half-width of 1.94, so 17% of the hand hung outside its
# own silhouette and the digit read as a spider leg. On the reference prop
# the fingertips sit at or inside the knuckle line.
# Opened back out from {8, 0, -4, -6}. Those closed the spider-leg gap
# (17% of the hand hanging outside its own silhouette) but overshot: at
# 100 m the four fingers read as one mass. The reference prop is equally
# closed, but it is filmed at two metres, not from a car. At -9 the little
# fingertip sits 8.8% outside the palm half-width, which reads as splayed
# without reading as a spider.
# Pulled toward PACKED. The reference's strapped fingers TOUCH; at
# 10/-5/-7 the straps bridged finger-width air gaps and read as hoops on
# separated tubes rather than tension on one paddle. A little spread
# survives so the digits still read as digits.
FINGER_SPLAY_DEG = {"index": 4.0, "middle": 0.0, "ring": -2.0, "little": -3.0}
# (MCP, PIP, DIP). These are an OPEN, offered hand, not a relaxed one: the
# gag is a high five, so the palm has to present flat. The first pass used
# true relaxed-hand angles (13/19/11 and up) and they sum to 43-60 deg of
# accumulated flexion, which put the middle fingertip 2.07 m proud of a
# palm only 0.91 m thick — a claw. These sum to 23-32 deg, which is a
# gentle arc over 4 m of finger and still not a flat cartoon glove.
# THIRD pass, and the direction of travel has been one way the whole
# time: 43-60 deg (relaxed anatomy) read as a claw; 23-32 read as a hand
# reaching for a doorknob the moment the alert twitch stacked on top of
# it. The reference prop's fingers are DEAD STRAIGHT, packed together and
# bound into one paddle by two elastic straps -- tension, not anatomy, is
# the read a high five wants. 9-15 deg keeps just enough arc that the
# paddle is not a plank; the straps (built into the hand part) do the
# unifying the earlier splay tuning was trying to fake.
FINGER_CURL_DEG = {
    "index": (3.0, 4.0, 2.0),
    "middle": (3.0, 4.0, 2.0),
    "ring": (4.0, 5.0, 3.0),
    "little": (5.0, 6.0, 4.0),
}
# Alert twitch: degrees of EXTENSION rippled through the joints while the
# hand has noticed you but has not committed. Extension, not flexion: a
# hand about to slap TENSES FLAT -- the fingers strain straighter, they do
# not curl toward a grab. (Flexion twitch on top of the old 23-32 deg curl
# hit 44-53 deg in the armed state: the hand a driver actually approached
# read as reaching for a doorknob.) Scaled per finger so the ripple runs
# little -> index like a real drum-roll.
TWITCH_DEG = 4.0
TWITCH_PHASE = {"little": 0.0, "ring": 0.7, "middle": 1.4, "index": 2.1}

# Thumb: a two-phalanx ray off the trapezium, abducted out of the palm
# plane and rotated 90 deg about its own axis so the nail faces radially
# — the single detail that separates a hand from a five-finger starfish.
# Measured from the CMC (trapezium), not the MCP: this ray is rooted at the
# wrist, so it carries the metacarpal too. 65 mm is the MCP-to-tip figure
# and using it here produced a thumb that stopped level with the palm.
THUMB_LENGTH_MM = 102.0
# A real thumb is ~30% fatter than a finger and the reference prop's is
# nearly double. 24.0 made it the same tube as the index.
THUMB_DIAMETER_MM = 29.0
# The thumb ray is metacarpal + two phalanges, and the metacarpal is the
# one that carries the thenar mass. THUMB_SPLIT divides what is LEFT of
# THUMB_LENGTH_MM once the metacarpal has taken its share.
THUMB_METACARPAL_FRAC = 0.44
THUMB_SPLIT = (0.55, 0.45)
# (dv, du) of the CMC joint FROM THE MIDDLE METACARPAL HEAD. du is large
# and NEGATIVE because the trapezium sits down at the wrist: the thumb ray
# is as long as the palm and starts where the palm starts. Authored +22
# once, which put the whole thumb 1 m distal of the knuckles growing out
# of thin air.
THUMB_ROOT_MM = (34.0, -76.0)
# The reference thumb is out near perpendicular — that wide-open angle is
# what makes the silhouette read as an offered high five rather than as a
# hand reaching for something.
THUMB_ABDUCT_DEG = 58.0        # out of the palm plane, toward +v
THUMB_PALMAR_DEG = 30.0        # forward toward the palm side (+n)
# Pronation about the thumb's own ray. This is THE detail that separates
# a hand from a five-pointed starfish: the thumb is rotated most of a
# quarter turn relative to the fingers, so its pad faces the fingers and
# its nail faces outward. Without it the thumb flexes in the wrong plane
# and reads as a short sixth finger.
THUMB_PRONATE_DEG = 76.0
THUMB_CURL_DEG = (10.0, 13.0)

# The metacarpal head is WIDER than the phalanx behind it — that is why a
# fist shows knuckles. Each digit's proximal ball carries this swell, and
# it is what makes the row of heads cover the palm's distal end instead of
# leaving a bare cliff between them.
MCP_HEAD_SWELL = 0.26

# THE MOULD PARTING SEAM, in geometry. See hand_sculpt._parting_seam for
# why it cannot be a texture term. FLASH_PROUD is how far the flash rubber
# stands off the silhouette and FLASH_WIDTH_DEG how much of the section arc
# it occupies; the dressing pattern (the stretches where the mould shop got
# the flash off cleanly) is a smooth function of u so it stays deterministic
# and scales with the hand.
# 1.15 mm was 51 mm on this hand and a reviewer could not find it in any
# of eleven renders including one at arm's length. On the reference prop the
# flash line is the loudest single signal that the thing is a CASTING.
# Fraction of PALM_WIDTH/2 the hand drops per unit of (1 - cos tilt).
# 1.0 would hold the palm’s ulnar edge at exactly its flat height at
# every detent; 0.75 is as far as it can go before the little finger,
# which hangs 0.6 m below that edge, reaches the tarmac.
ROLL_COMPENSATION = 0.75

FLASH_PROUD_MM = 1.90
# IN GRID COLUMNS, not degrees, and this is the third framing because the
# first two were both measured wrong.
#
# `_bump` is a Gaussian whose `width` argument is its SIGMA, so
# FLASH_WIDTH_DEG = 8.0 was not an 8-degree bead: it had support out to
# 3 sigma = +/-24 degrees and measured 50 of the palm's 192 columns, a
# 1.75 m arc carrying a 0.067 m rise. A 4% gradient, which is a hill. Both
# earlier comments here quoted column counts that are simply not what the
# code produces — they were reasoned about rather than measured, which is
# how a feature stays inert for four rounds while its own comment calls it
# "the loudest single signal that the thing is a CASTING".
#
# Degrees were the wrong unit anyway. The palm's columns are 0.072 m of arc
# and a digit's are 0.030 m, so one angle cannot mean one feature on both.
# What the seam actually needs is to be the FINEST THING THE GRID CAN
# CARRY: below about one column of sigma it aliases along its length, and
# above about 1.5 it stops clearing the 38-degree auto-smooth angle and
# shades away to nothing. 1.3 sits in that window on both grids with room
# either side, and the physical widths it lands on — 0.156 m on the palm,
# 0.060-0.093 m on the digits — are what a 44x casting's dressed flash
# should measure. test_the_parting_seam_is_a_fin_and_not_a_hill asserts
# both halves of that: the crest break in degrees AND the width in metres.
FLASH_WIDTH_COLUMNS = 1.3
FLASH_DRESS = 0.45             # 0 = untrimmed everywhere, 1 = trimmed flush

# Fingernails: 12 mm long on a 19 mm finger, wrapping ~140 deg of the
# dorsal arc, standing 0.8 mm proud of the nail bed.
NAIL_LENGTH_MM = 12.0
# 140 deg put the plate +/-70 deg off dorsal — past the equator and down
# onto the flanks, so the nail read as a painted band wrapping the
# fingertip rather than as a plate sitting on the back of it.
NAIL_WRAP_DEG = 104.0
NAIL_PROUD_MM = 0.9
NAIL_INSET_MM = 1.6            # from the fingertip, so the pulp shows past it

# Palmar creases as REAL grooves, not paint. The three named creases of a
# human palm, each as (start_v, start_u, end_v, end_u) in human mm from the
# middle metacarpal head, plus a width and depth. A tiling skin map cannot
# place these — they are the one piece of hand detail that is positional,
# so they are cut into the mesh and survive the voxel remesh.
# Deeper and wider than a real palm's, deliberately. At 44x a true 2.6 mm
# crease is 115 mm on a 4.6 m palm — geometrically correct and invisible
# from a car. These are MOULD lines on a cast prop, and on the reference
# hand they are the most recognisable thing about it.
# 7.0, and the "deep and NARROW" reasoning that put this at 2.6 was a
# right observation with a wrong cause. The crease was not reading as a
# shadow line because `_grid_to_object` smooth-shaded the hand — the
# normal was interpolated straight across every wall, so no width would
# ever have cast one. Narrowing it to 2.6 did not fix that and did do
# real damage: a 0.221 m deep trench 0.115 m wide, with quartic walls,
# INVERTS. 446 quads on the palm had adjacent facets over 38 degrees
# apart and the worst pair sat at 180 — the surface folded back on
# itself, all of it hidden by the same smooth shading.
#
# With the shading fixed, the crease can be what a flexion crease
# actually is: wider than it is deep, about 1:1.4 here. It reads because
# its walls are now shaded, which is what was wanted all along.
CREASE_WIDTH_MM = 7.0
CREASE_DEPTH_MM = 5.0
PALM_CREASES = (
    # distal transverse ("heart line"): ulnar edge to between index/middle
    ("distal_transverse", (-42.0, -12.0), (14.0, -3.0)),
    # proximal transverse ("head line"): radial edge, sweeps ulnar-down
    ("proximal_transverse", (30.0, -22.0), (-34.0, -34.0)),
    # thenar ("life line"): arcs around the ball of the thumb
    ("thenar", (26.0, -18.0), (2.0, -74.0)),
)
# Flexion creases across the volar side of each joint: (fraction along the
# phalanx chain, width mm, depth mm). MCP gets a double crease, as it does
# on a real finger.
# Depths halved and the doubled MCP crease dropped after the first
# textured render (2026-08-24): six creases at true anatomical depth on a
# 4 m finger do not read as skin folds, they read as segments, and every
# digit came out looking like a caterpillar. A crease on a CAST FOAM prop
# is a mould line, not a fold — shallow, and there are fewer of them.
# (fraction along the digit, width mm, depth mm). The MCP crease at the
# base is the DEEPEST on a real finger; the first pass had it shallowest
# because the interphalangeal joints were being creased a second time by a
# separate loop over PHALANX_SPLIT's own joint fractions — which are these
# same numbers. One loop now, and it owns all three.
JOINT_CREASES = ((0.0, 3.4, 2.4), (0.45, 3.4, 1.5), (0.77, 2.8, 1.1))

# THERE IS NO REMESH. This block used to carry REMESH_VOXEL_MM,
# REMESH_SMOOTH_ITERATIONS, REMESH_SMOOTH_FACTOR and HAND_TRIANGLE_BUDGET,
# describing a union-and-voxel-remesh pipeline that was designed and then
# abandoned — and none of the four constants was ever read by anything.
# They are gone because a spec that describes a process the generator does
# not run is worse than no comment at all: a reviewer read the 1.6 mm voxel
# (70 mm at this scale), correctly concluded that every crease, the mould
# seam and the 0.9 mm nail relief would all be erased by it, and was
# reasoning about a pipeline that does not exist.
#
# What actually happens: the palm and each digit are built directly as
# analytic (s, theta) quad grids by hand_sculpt.py. No booleans, no
# remesh, no decimation. Detail is limited only by the grid resolution
# passed to build_palm/build_digit, so a crease is exactly as deep as
# CREASE_DEPTH_MM says it is.
# NOMINAL tile pitch. The realised pitch per part is
# `reference / round(reference / this)`, because u must wrap a whole number
# of times, so the smaller this is the tighter the parts agree: at 2.60 the
# five digits and the palm realised pitches spanning 1.69x — the thumb's
# pore stipple came out 69% finer than the middle finger's, which is
# visible where the thenar meets the palm. At 0.65 the spread is 4%.
SKIN_METERS_PER_TILE = 0.65

# ---------------------------------------------------------------------------
# The rig (authored frame)
# ---------------------------------------------------------------------------
# The mast axis is the slew axis. The origin is the strike point: at
# contact azimuth the palm centre passes through (0, 0, WRIST_Z).

# SCALE (2026-08-24, first assembled render). The rig was authored around a
# 6.9 m boom on a 6.3 m mast and it read as a chess piece holding a bus: an
# 8.6 m hand needs an arm longer than itself or the machine looks like a
# toy someone glued a prop to. Everything below is sized off WRIST_R, which
# is now 9.6 m — 12.6 m of boom, carried 10.5 m up.
WRIST_R = 9.60             # horizontal radius of the wrist from the mast axis
# Hand-axis height. This used to be 2.30, with a comment saying the palm
# bottom cleared the road — which it did. The DIGITS did not: the little
# finger's metacarpal head already sits within 90 mm of the palm's ulnar
# edge, and 10.5 degrees of splay over 2.8 m of finger takes its tip half a
# metre further down again. Measured on the shipped meshes, the pinky swept
# 0.42 m UNDER the tarmac at TILT 0 and 0.09 m under at the default
# setting, for the whole stroke and while parked.
#
# The swing is about a vertical axis, so z is identical at every azimuth
# and there is nowhere in the stroke where it recovers. 2.72 puts the worst
# swept vertex of the worst digit at +0.32 m; the ulnar splay is pulled in
# to match (see FINGER_SPLAY_DEG and MCP_OFFSET_MM).
WRIST_Z = 2.72
HUB_Z = 10.50              # slew ring / shoulder centre
MAST_TOP_Z = 8.00          # top of the tapered column, under the slew ring
# The origin IS the strike point, so the mast stands exactly one palm-centre
# offset further out than the wrist: at contact azimuth the palm centre
# passes through (0, 0, WRIST_Z) by construction, not by adjustment.
PALM_CENTRE_U = 2.30
MAST_X = -(WRIST_R + PALM_CENTRE_U)
MAST_Y = 0.0

# THE ARM HAS AN ELBOW, and it is not decoration.
#
# The arm sweeps a CONE about the vertical slew axis: the hand travels a
# horizontal circle at WRIST_Z while the structure carrying it stays clear
# overhead of everything inside that circle. A single straight boom from the
# hub to the wrist does that, but it arrives at 40 degrees nose-down while the
# hand it carries is horizontal, so the wrist is a 40-degree kink in the
# middle of the silhouette — which is exactly what the first assembled render
# looked like.
#
# Two members instead. A steep UPPER ARM drops most of the height right next
# to the mast, and a near-level FOREARM runs out to the wrist, so the wrist
# only has to break 23 degrees — which is real wrist extension, and is what a
# hand about to slap something actually does.
ELBOW_R = 3.60             # horizontal radius of the elbow pin
ELBOW_Z = 4.90
UPPER_RUN = ELBOW_R
UPPER_RISE = HUB_Z - ELBOW_Z
UPPER_LENGTH = math.hypot(UPPER_RUN, UPPER_RISE)
UPPER_PITCH_DEG = math.degrees(math.atan2(UPPER_RISE, UPPER_RUN))
FORE_RUN = WRIST_R - ELBOW_R
FORE_RISE = ELBOW_Z - WRIST_Z
FORE_LENGTH = math.hypot(FORE_RUN, FORE_RISE)
FORE_PITCH_DEG = math.degrees(math.atan2(FORE_RISE, FORE_RUN))
ELBOW_BREAK_DEG = UPPER_PITCH_DEG - FORE_PITCH_DEG
BOOM_ROOT_DEPTH = 2.05     # box-section depth at the shoulder
# THE KNEE. A straight member from the hub (r 0, z 10.5) to the elbow
# (r 3.6, z 4.9) pitches 57 degrees and by construction crosses the slew
# ring band (z 8.00-8.62, r 2.085) at centreline radii 1.2-1.6 -- 1.7 m
# of rotating steel inside fixed steel at EVERY azimuth, and no root
# offset can fix a line whose path is wrong (the first "fix" bought
# 0.28 m of a 1.99 m problem and a reviewer recomputed it to rubble).
# So the boom is a luffing-derrick dogleg: a shallow shoulder segment
# from the hub OVER the ring, a knee joint outside it, then the steep
# drop to the elbow.
#
# THE KNEE IS AT z 9.45, NOT THE 9.10 FIRST DERIVED -- because the first
# derivation walked the girders and forgot the JOINT. The knee box is
# 1.55 m tall; centred at 9.10 its bottom face reached z 8.325, which is
# 0.208 m INTO the slew teeth (z 8.087-8.533) across their full radial
# depth -- eleven teeth bitten at any azimuth, all 96 ground through per
# swing, invisible in every render because it reads as tight machinery.
# A reviewer walked the box envelope the gate did not. At 9.45 the box
# bottom (8.675) clears the tooth band by 0.142 m and the ring top by
# 0.055; the shoulder shallows to 20.2 degrees (belly clearance grows)
# and the drop steepens to 80.7 (still 0.25+ m outside the ring).
# test_the_boom_clears_the_slew_ring now walks BOTH girders AND the box.
BOOM_KNEE_R = 2.85
BOOM_KNEE_Z = 9.45
#: (across-arm, along-arm, tall) of the knee joint box. In spec rather
#: than inline in the generator so the clearance gate walks the same
#: numbers the mesh is built from.
BOOM_KNEE_BOX = (1.62, 1.55, 1.55)
BOOM_ELBOW_DEPTH = 1.62    # both members at the elbow pin
BOOM_TIP_DEPTH = 1.18      # at the wrist collar
BOOM_WIDTH = 1.40
ELBOW_PIN_R = 0.58
ELBOW_CHEEK = 0.24         # cheek plate thickness each side
RAM_BORE_R = 0.30          # the elbow ram that sets the forearm angle

# Counterweight: a bolted stack of plates on the short side of the hub,
# authored to actually balance the first moment of the arm about the slew
# axis (see the mass ledger under BEHAVIOR).
CWT_R = -4.10              # negative radius = opposite the boom
CWT_PLATES = 7
# (across, thick, tall) per plate. Resized 2026-08-26 from
# (2.45, 0.44, 1.55): a rescale had reached the plates but not the ledger,
# and the shipped stack was 91.8 t = 4.8x overbalanced against the arm's
# 78.9 t.m while the ledger sold 1.53x. These give 7 x 4.19 t = 29.4 t at
# 4.10 m = 120 t.m = 1.52x, which is the number the paragraph always
# claimed. The plate stack is the ledger's load-bearing wall; they move
# together or the nameplate lies.
CWT_PLATE = (1.68, 0.30, 1.06)
CWT_Z = 9.30

# Mast: a tapered black steel tower on a bolted flange, gusseted, with a
# caged ladder up the road-facing side and the rigging-stand chain and
# turnbuckle from the reference.
MAST_BASE = 4.60           # square, at grade
MAST_TOP = 2.50            # square, under the slew ring
MAST_PLATE = (6.40, 6.40, 0.46)
MAST_PLATE_BOLTS = 16
MAST_BOLT_R = 0.135
MAST_GUSSETS = 4
MAST_GUSSET = (2.30, 0.14, 3.10)
SLEW_RING_R = 2.05
SLEW_RING_H = 0.62
SLEW_TEETH = 96
LADDER_RUNGS = 18
# Azimuth of the slew drive. NOT on the safe side: the pinion, gearbox and
# their power pack are the parts that say the mast turns, and with
# everything on the far face a driver saw a blank tapered obelisk. 132 deg
# is legible from the road and still 28 deg clear of the swept sector.
DRIVE_AZIMUTH = 132.0
FINIAL_R = 0.62            # the reference stand's ball finial, kept
BOLLARD_X = -7.60          # shoulder line between the road and the mast
# Bollards mark the approach, and they are placed OUTSIDE the swept circle
# on purpose: the fingertips reach 18.2 m and sweep at 0.36 m above grade,
# so anything standing inside that annulus gets mown down on the first
# slap. These sit at 19.5 m and 25.4 m.
BOLLARD_Y = (-25.0, -19.0, 19.0, 25.0)
BOLLARD_HEIGHT = 1.15          # real road-bollard height, on a visible base

# Wrist collar: the black steel cuff that swallows the foam stump, matching
# the reference's axle-into-wrist joint. TILT rotates inside this.
# The collar has to SWALLOW the foam stump, so its bore cannot be smaller
# than the wrist is wide: WRIST_WIDTH/2 is 1.367 m and the first authored
# radius was 1.02, which put the wrist visibly through the cuff.
# The bore is an ELLIPSE, and it has to be: a wrist is 1.72:1, so a round
# cuff big enough not to cut the width leaves a 0.80 m black crescent above
# and below the stump. Half-extents are measured off the palm's own section
# at the cuff mouth at build time, plus this clearance, so the cuff cannot
# drift out of agreement with the hand it swallows.
COLLAR_R = 1.62                # nominal, still used for the flange and bolts
COLLAR_CLEARANCE = 0.17
COLLAR_LENGTH = 2.20
COLLAR_BOLTS = 12

# ---------------------------------------------------------------------------
# Swing geometry (azimuth about the mast axis, degrees)
# ---------------------------------------------------------------------------
# 0 deg = boom points +X, straight across the road; positive = toward +Y
# (down-road). The palm normal is the sweep tangent, so at 0 deg it is
# exactly +Y and the launch is straight down the tarmac before TILT.

REST_DEG = -72.0           # parked up-road, well clear of the lane
WINDUP_DEG = -104.0        # cocked further back
CONTACT_DEG = 0.0          # palm centre over the origin
FOLLOW_DEG = 78.0          # follow-through, hand ends down-road

# ---------------------------------------------------------------------------
# Derived hand frame — the generator and the runtime read the SAME vectors
# ---------------------------------------------------------------------------
# Nothing below is authored. These are the consequences of REST_DEG,
# WRIST_R and WRIST_Z, and they are computed once here so the Blender
# generator, the Lua constants block and the offline math test cannot hold
# three different opinions about where the wrist is.

REST_RAD = math.radians(REST_DEG)

#: proximal -> distal, horizontal, radially out from the mast
U_REST = (math.cos(REST_RAD), math.sin(REST_RAD), 0.0)
#: dorsal -> volar (palm normal) = the sweep tangent
N_REST = (-math.sin(REST_RAD), math.cos(REST_RAD), 0.0)
#: ulnar -> radial (thumb). n = v x u for a right hand puts this at +Z.
V_REST = (0.0, 0.0, 1.0)

#: the wrist crease centre — the hand part's pivot, and the roll axis origin
WRIST_POINT = (
    round(MAST_X + WRIST_R * U_REST[0], 6),
    round(MAST_Y + WRIST_R * U_REST[1], 6),
    WRIST_Z,
)
#: the slew axis is vertical through here; only x/y are ever used
SLEW_POINT = (MAST_X, MAST_Y)

FINGER_ORDER = ("index", "middle", "ring", "little")
DIGIT_ORDER = FINGER_ORDER + ("thumb",)


def hand_point(du: float, dv: float, dn: float) -> tuple[float, float, float]:
    """Authored-frame point from hand-local (u, v, n) metres off the wrist."""

    return (
        round(WRIST_POINT[0] + du * U_REST[0] + dv * V_REST[0] + dn * N_REST[0], 6),
        round(WRIST_POINT[1] + du * U_REST[1] + dv * V_REST[1] + dn * N_REST[1], 6),
        round(WRIST_POINT[2] + du * U_REST[2] + dv * V_REST[2] + dn * N_REST[2], 6),
    )


def hand_dir(du: float, dv: float, dn: float) -> tuple[float, float, float]:
    """Authored-frame direction from hand-local (u, v, n) components."""

    raw = (
        du * U_REST[0] + dv * V_REST[0] + dn * N_REST[0],
        du * U_REST[1] + dv * V_REST[1] + dn * N_REST[1],
        du * U_REST[2] + dv * V_REST[2] + dn * N_REST[2],
    )
    length = math.sqrt(sum(component * component for component in raw)) or 1.0
    return tuple(round(component / length, 6) for component in raw)


def mcp_local(name: str) -> tuple[float, float, float]:
    """Metacarpal-head (knuckle) centre in hand-local (u, v, n) metres.

    The heads sit on an arc: MCP_OFFSET_MM carries each head's (dv, du)
    from the middle head, which itself is PALM_LENGTH distal of the wrist
    crease. n is the dorsal-volar height of the joint centre — a knuckle
    is not on the mid-plane, it rides toward the DORSAL side, which is why
    a fist shows knuckles and a palm does not.
    """

    dv_mm, du_mm = MCP_OFFSET_MM[name]
    return (PALM_LENGTH + _mm(du_mm), _mm(dv_mm), _mm(-3.0))


def thumb_cmc_local() -> tuple[float, float, float]:
    dv_mm, du_mm = THUMB_ROOT_MM
    return (PALM_LENGTH + _mm(du_mm), _mm(dv_mm), _mm(4.0))


def _rotate(vector, axis, angle):
    """Rodrigues rotation. Plain trig on purpose: the engine's quaternion
    product runs the opposite handedness to the textbook one, and this
    geometry is shared with a pure-Python test that must not have to model
    that."""

    cosine, sine = math.cos(angle), math.sin(angle)
    dot = sum(a * b for a, b in zip(vector, axis))
    cross = (
        axis[1] * vector[2] - axis[2] * vector[1],
        axis[2] * vector[0] - axis[0] * vector[2],
        axis[0] * vector[1] - axis[1] * vector[0],
    )
    return tuple(
        vector[i] * cosine + cross[i] * sine + axis[i] * dot * (1.0 - cosine)
        for i in range(3)
    )


def finger_flex_axis(name: str) -> tuple[float, float, float]:
    """Authored-frame flexion axis of one finger, positive = curl inward.

    A finger flexes about its own width axis. Splay rotates the whole ray
    about the palm normal, so the width axis rotates with it. The SIGN
    falls out of the right-hand identity n = v x u: rotating a point about
    +v carries the fingertip toward +n, which is into the palm, which is
    flexion. Nothing here is chosen — it is the only axis that curls.
    """

    splay = math.radians(FINGER_SPLAY_DEG.get(name, 0.0))
    # Positive splay means "toward the thumb" (+v). Rot(n, +s) carries u
    # toward -v, so a toward-the-thumb splay is a NEGATIVE turn about n.
    return tuple(round(value, 6) for value in _rotate(V_REST, N_REST, -splay))


def finger_ray_dir(name: str) -> tuple[float, float, float]:
    """Authored-frame long axis of one finger's proximal phalanx."""

    splay = math.radians(FINGER_SPLAY_DEG.get(name, 0.0))
    return tuple(round(value, 6) for value in _rotate(U_REST, N_REST, -splay))


def finger_pivot(name: str) -> tuple[float, float, float]:
    return hand_point(*mcp_local(name))


def thumb_frame() -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """The thumb's (ray, flexion axis), built in ONE place.

    Three turns, in this order and no other:

    1. ABDUCT the whole ray out of the palm plane about the palm normal,
    2. carry it forward toward the PALM about its own width axis — a
       positive turn, because ``axis x ray`` is +n here,
    3. PRONATE the width axis about the finished ray, which is the quarter
       turn that makes the thumb oppose the fingers instead of being a
       short sixth one.

    The generator projects these same two vectors into its hand-local frame
    rather than re-deriving them, because it did re-derive them once and
    the two copies drifted: the mesh got the corrected signs and the
    runtime kept the originals, so the thumb's twitch flexed about an axis
    24 degrees off its own shaft and nothing failed until it moved.
    """

    abduct = math.radians(THUMB_ABDUCT_DEG)
    ray = _rotate(U_REST, N_REST, -abduct)
    axis = _rotate(V_REST, N_REST, -abduct)
    ray = _rotate(ray, axis, math.radians(THUMB_PALMAR_DEG))
    axis = _rotate(axis, ray, math.radians(THUMB_PRONATE_DEG))
    return (
        tuple(round(value, 6) for value in ray),
        tuple(round(value, 6) for value in axis),
    )


def thumb_flex_axis() -> tuple[float, float, float]:
    return thumb_frame()[1]


def thumb_ray_dir() -> tuple[float, float, float]:
    return thumb_frame()[0]


def thumb_pivot() -> tuple[float, float, float]:
    return hand_point(*thumb_cmc_local())


DIGIT_PIVOTS = {name: finger_pivot(name) for name in FINGER_ORDER}
DIGIT_PIVOTS["thumb"] = thumb_pivot()
DIGIT_AXES = {name: finger_flex_axis(name) for name in FINGER_ORDER}
DIGIT_AXES["thumb"] = thumb_flex_axis()
DIGIT_RAYS = {name: finger_ray_dir(name) for name in FINGER_ORDER}
DIGIT_RAYS["thumb"] = thumb_ray_dir()


# ---------------------------------------------------------------------------
# Control console
# ---------------------------------------------------------------------------
# Sited on the shoulder INSIDE the swing circle, facing -Y so an arriving
# driver reads it head-on, and low enough to pass under the boom (which
# clears 3.73 m at this radius). Same mid-century cabinet grammar as the
# Boot of Doom console — cream enamel case, solid walnut end panels, a
# graphite legend plate — because they are the same builder's plate.

# Sited at 6.0 m from the mast axis: inside the wrist's 9.6 m sweep circle,
# so the HAND never passes over the player, and 5.4 m under the boom, which
# does — reading the panel means watching the arm go by overhead.
CONSOLE_CX = -8.40
CONSOLE_CY = -5.00
# Every plane on the cabinet is an OFFSET from CONSOLE_CY, not an absolute
# y. The console has been moved twice already (clear of the boom, then
# clear of the wrist collar's sweep) and each move silently left the legend
# plate and the click anchors behind at their old absolute coordinates.
CONSOLE_FACE_Y = CONSOLE_CY - 0.275     # fascia plane
CASE_W = 1.78
CASE_D = 0.55
CASE_Z0 = 0.62
CASE_Z1 = 1.74
CHEEK_T = 0.075
FRAME_PROUD = 0.035
CAP_T = 0.045
CAP_LIP = 0.016
BASE_INSET = 0.065
BASE_RAIL_H = 0.055
BASE_RAIL_T = 0.045
BOLT_PLATE = 0.10
FOOT_Z = 0.03
# One 45-degree segment, not proplib's default two: two 30-degree steps
# both fall under the 38-degree auto-smooth angle and shade into a melted
# blob. (Boot of Doom console rebuild, 2026-08-13.)
EDGE_EASE = 0.004

PLATE_Y = CONSOLE_CY - 0.281     # legend plate centre (0.012 skin)
PLATE_W = 1.58
PLATE_H = 0.88
PLATE_Z0 = 0.75
POWER_ROW_Z = 1.345
POWER_SEG_PITCH = 0.079
POWER_SEG_DX0 = -0.3555          # segment 1 (viewer LEFT = authored -x)
TILT_ROW_Z = 0.985
TILT_SEG_PITCH = 0.079
# Seven steps at 0.079 pitch span 0.474, so the first sits at half of that
# below centre. -0.2765 was one whole pitch out and put the row 40 mm off
# the panel's axis while the comment said "centred".
TILT_SEG_DX0 = -0.237            # seven tilt steps, centred
BUTTON_ANCHOR_Y = CONSOLE_CY - 0.377    # click anchors 9 cm proud of the plate

BACK_PLATE_W = 0.27
BACK_PLATE_H = 0.1755
BACK_PLATE_MARGIN_X = 0.095
BACK_PLATE_MARGIN_Z = 0.085
BACK_PLATE_SCREW_INSET = 0.013
BACK_PLATE_SCREW_R = 0.005

PANEL_BUTTONS = (
    {"id": "btn_power_down", "title": "Slap Power: Decrease",
     "dx": -0.58, "z": POWER_ROW_Z},
    {"id": "btn_power_up", "title": "Slap Power: Increase",
     "dx": 0.58, "z": POWER_ROW_Z},
    {"id": "btn_tilt_down", "title": "Wrist Tilt: Lower",
     "dx": -0.58, "z": TILT_ROW_Z},
    {"id": "btn_tilt_up", "title": "Wrist Tilt: Raise",
     "dx": 0.58, "z": TILT_ROW_Z},
)


def _u(dx: float) -> float:
    """Plate u from an authored x-offset. The plate faces -y, so the world
    mirror puts authored -x on the viewer's LEFT and u runs WITH x."""

    return round(0.5 + dx / PLATE_W, 4)


def _v(z: float) -> float:
    return round((z - PLATE_Z0) / PLATE_H, 4)


PANEL_LEGEND_LABELS = [
    [0.5, _v(1.475), "POWER", 0.8],
    [_u(-0.58), _v(1.245), "-", 0.9],
    [_u(0.58), _v(1.245), "+", 0.9],
    [_u(POWER_SEG_DX0), _v(1.262), "1X", 0.55],
    # The printed top of the ladder has to be what the machine does:
    # power_multiplier_max came down from 5.0 to 2.6 when the ballistic
    # measurements showed P10 throwing a car 1844 m.
    [_u(-POWER_SEG_DX0), _v(1.262), "2.6X", 0.55],
    [0.5, _v(1.115), "WRIST TILT", 0.8],
    [_u(-0.58), _v(0.885), "-", 0.9],
    [_u(0.58), _v(0.885), "+", 0.9],
    [_u(TILT_SEG_DX0), _v(0.902), "FLAT", 0.5],
    # The scale has to say what the machine does: seven detents of 7 deg
    # top out at 42, and the label read 60 for a setting that no longer
    # exists. It was also printed one segment pitch beyond the last segment.
    [_u(-TILT_SEG_DX0), _v(0.902), "42", 0.5],
    [0.5, 0.075, "SLAP - PALM NORMAL LAUNCH", 0.62],
]

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

PALETTE = {
    # THE hero material. Foam latex, not skin: the reference hand is a
    # matte cast prop with a warm sandy cast, faint mould-seam ridges down
    # the sides and a dusty finish that catches no specular at all. A
    # glossy pink "skin" shader here would look like a mannequin, which is
    # exactly wrong — the joke is that it is obviously a PROP.
    f"{MOD_ID}_foam_latex": {
        "texture": {
            "family": "foam_latex",
            # Linear values in an 8-bit PNG that the engine reads as sRGB
            # arrive up to 9x too dark, and rotate hue on the way.
            "srgb": True,
            "size": 2048,
            "params": {
                # THE ALBEDO, not a highlight. sRGB (190, 168, 118) was
                # sampled off the lit side of the reference hand and sits at
                # the 99.5th percentile of that hand's own pixels — its
                # MEDIAN is (110, 86, 42). Normalising against the white
                # fridge in the same frame puts the palm's true albedo near
                # sRGB (146, 120, 66) at saturation 0.80, against 0.65 for
                # the highlight. Saturation is exposure-invariant, so the
                # rendered palm measuring 0.22 against the reference's
                # 0.48-0.55 was never a lighting problem and was never
                # fixable in `mottle` or `dust` — those are wash terms; the
                # base is the constant. Values below are the LINEAR form.
                #
                # They were briefly [0.22819, 0.12597, 0.0331] because the
                # sRGB migration ran a blanket decode over every colour in
                # the palette, including this one — which had already been
                # authored linear. Decoding a linear value a second time is
                # not a no-op: it took the rendered albedo to sRGB
                # (131, 99, 51), caramel instead of khaki, 2.86x too dark
                # and 2.7x too saturated. Six of six components matched
                # decode(intended) exactly, which is how it was caught.
                # test_the_hero_colour_survives_the_srgb_round_trip now
                # asserts the encode lands on the sampled swatch.
                "base": [0.280, 0.185, 0.055],
                "deep": [0.160, 0.098, 0.030],
                # 0.42 read as camouflage at 8 m and 0.26 still read as
                # bleach damage: the blotches are ~0.5 m across, which is
                # a pigment defect nobody would ship a prop with.
                # Back up from 0.16 once the base went to its true linear
                # value: on a dark ochre the same amplitude that read as
                # bleach damage on a pale cream is barely a variation.
                # 0.38 went the wrong way. Cutting `dust` was right —
                # it is a near-neutral lifter — and then adding back more
                # of a SECOND near-neutral lifter put the wash straight
                # back. Measured on the render, the base swatch has
                # R-B = 72 and the rendered surface had R-B = 36: the tile
                # was destroying exactly half the authored chroma between
                # the constant and the pixel.
                "mottle": 0.20,
                "pores": 0.55,
                # ZERO. The parting line is GEOMETRY (see FLASH_PROUD_MM),
                # and measured at 0.10 the tile's seam window came out
                # DARKER than the tile average — it was documenting a
                # feature that is not there.
                "seam": 0.0,
                # Near-neutral, so it is spent sparingly. See mottle.
                "dust": 0.08,
                "rough": 0.78,
            },
            # The pore field carried a global std of 2.6 code values and
            # fell below quantisation by mip 3, so the pores existed in
            # colour and nowhere else and read as printed grain at every
            # distance. This is the hero material; it gets the relief.
            "normal_strength": 6.0,
        },
        "color": [0.280, 0.185, 0.055, 1.0],
        "metallic": 0.0,
        "roughness": 0.78,
    },
    # Nails are the one part of a cast hand that is painted afterwards:
    # pale, faintly translucent, and the only place on the whole 8.6 m
    # prop with a real specular highlight.
    f"{MOD_ID}_nail": {
        "texture": {
            "family": "nail_keratin",
            # Linear values in an 8-bit PNG that the engine reads as sRGB
            # arrive up to 9x too dark, and rotate hue on the way.
            "srgb": True,
            "size": 1024,
            "params": {
                # Only half a stop lighter than the foam it sits in. At
                # [0.683, 0.499, 0.400] the plate was three times the skin
                # albedo and read as five white sticking plasters at every
                # distance — the most eye-catching wrong thing on the prop.
                # Re-derived against the corrected foam: about 1.5x its
                # luminance, which is where a prop nail sits.
                # 0.90x the foam's base, WHICH IS NOT THE RATIO THAT MATTERS
                # and is why this entry has now been "corrected" wrongly.
                #
                # The reference's 1.09 is a ratio between what you SEE. The
                # base is an input to nail_keratin, which lifts it — plate
                # sheen, lunula, striation — so a base at 0.90x lands the
                # MAP at 1.18x and the rendered plate at 1.07x, which is
                # the number the reference sets. Re-authoring the base to
                # 1.09x to "match the reference" took the map to 1.41x and
                # the plate 20% too bright: correcting an input to equal a
                # figure that describes an output.
                #
                # So the constant is left where a measurement put it, and
                # test_the_nail_holds_its_ratio_to_the_foam asserts the
                # SHIPPED MAPS instead. What drifts here is the comment, not
                # usually the value, and a claimed ratio nothing checks is
                # worse than no claim because it reads as verified.
                #
                # B/G 0.89: the reference nails are a desaturated PINK.
                # ROSE PINK, airbrushed -- the film prop's tips are rounded pink
                # spray, not grey-tan plates. Same linear luminance as the
                # tan it replaces (0.1767, the value the shipped-map ratio
                # gate holds at 1.05-1.30 x foam), so only the hue moves.
                "base": [0.270, 0.1505, 0.161],
                # Sampled off the reference frames: the real nails read
                # PINK — blue above green, saturation about a third of the
                # surrounding foam — and a near-neutral lunula was the other
                # half of why they looked like plasters.
                # PINK, per the reference frames: blue above green, and only
                # a third the saturation of the surrounding foam.
                "lunula": [0.305, 0.180, 0.195],
                # 0.22, down from 0.75. The striation grain at 0.75 read as woven
                # tape at 1080p in-game -- fabric, not keratin. The film tips
                # are smooth airbrushed spray; what little grain survives is
                # under the gloss.
                "striate": 0.22,
                # Airbrushed lacquer over foam: glossier than skin.
                "rough": 0.38,
                # The colour the plate dissolves into at the lateral fold:
                # the foam it sits in, not white.
                "bed": [0.280, 0.185, 0.055],
            },
            # 94.3% of the nail normal map was within one code step of
            # flat — below the quantisation floor. No striae, no arch, no
            # gloss break, which is why the nails read as sticking plasters.
            "normal_strength": 8.0,
        },
        "color": [0.270, 0.1505, 0.161, 1.0],
        # A cast prop's nails are chalky matte pink with no highlight at
        # all. At roughness 0.24 and metallic 0.05 they were the ONLY
        # specular surface on a prop where everything else is 0.78, so they
        # clipped to white under any key light and read as five sticking
        # plasters — the brightest object in the driver's-eye frame.
        "metallic": 0.0,
        "roughness": 0.52,
    },
    # The rig is matte black, exactly like the reference stand. 1024 and
    # metric UVs everywhere: the Boot of Doom hinge block proved a 512 map
    # stretched over 3 m reads as soft banding rather than steel.
    f"{MOD_ID}_rig_black": {
        "texture": {
            "family": "painted_metal",
            # Linear values in an 8-bit PNG that the engine reads as sRGB
            # arrive up to 9x too dark, and rotate hue on the way.
            "srgb": True,
            "size": 1024,
            # 0.035 is a real matte-black machine enamel. The sRGB round trip
            # off the old authored value landed at 0.011 — darker than any
            # paint, and it leaves nothing for the weathering to modulate.
            "params": {
                "base": [0.035, 0.035, 0.038],
                "rough": 0.52,
                "peel": 0.34,
                # 0.75 was a 1.71x albedo swing on a near-black paint and
                # 0.30 of chalk lifted the tower to a neutral mid grey in
                # 256-texel clouds: the machine read as a mouldy tarpaulin,
                # which is the "digital camo" failure steel_worn's own
                # docstring was written about. Loud and wrong is worse than
                # flat. The weathering that actually says "this has stood
                # outside" is the vertical runoff, not the blotching.
                # Halfway back. 0.75/0.30 was a mouldy tarpaulin; 0.35/0.12
                # overcorrected to flat plastic with no sheen variation and
                # no edge wear at all.
                "grain": 0.55,
                "chalk": 0.18,
                "orange_peel": 0.55,
                "runoff": 0.55,
            },
            # 14, not 5. Measured at 5.0 the generated map's normal Z channel
            # was LITERALLY CONSTANT 255 and its mean tilt 0.84 degrees, on a
            # tower whose reference photograph carries a standard deviation of
            # 40 code values of specular breakup at the same mean luma where
            # this measured 2.8.
            "normal_strength": 14.0,
        },
        "color": [0.035, 0.035, 0.038, 1.0],
        # ZERO. A matte machine ENAMEL is a dielectric; at 0.45 on an albedo
        # of 0.035 the diffuse was killed and what was left was a dark
        # tinted specular returning a uniform grey under a uniform sky —
        # which is most of why the mast read as flat facets. console_cream
        # is the same family and the same finish class at 0.1.
        "metallic": 0.0,
        "roughness": 0.52,
    },
    # Bare machined faces — slew ring teeth, collar bore, pins, bolt heads.
    f"{MOD_ID}_steel": {
        "texture": {
            "family": "machined_steel",
            # Linear values in an 8-bit PNG that the engine reads as sRGB
            # arrive up to 9x too dark, and rotate hue on the way.
            "srgb": True,
            "size": 1024,
            "params": {"base": [0.17473, 0.18732, 0.20944], "rough": 0.36},
            # machined_steel puts its realism in roughness, which survives
            # the encode; the flange discs and bolt heads still rendered as
            # flat grey coins because the normal was 0.43 deg of mean tilt.
            # 4.0 only took that to 0.72 degrees — still a flat coin. The
            # same measurement is why rig_black sits at 14.
            "normal_strength": 9.0,
        },
        "color": [0.17473, 0.18732, 0.20944, 1.0],
        "metallic": 0.85,
        "roughness": 0.36,
    },
    f"{MOD_ID}_cast_iron": {
        "texture": {
            "family": "cast_iron",
            "size": 1024,
            # INSIDE the texture dict. prop_builder reads
            # texture.get("srgb"), and on this entry and btn_bakelite the key
            # landed one level up beside "color", where nothing reads it —
            # the ast pass that inserted it anchored on the family node, and
            # these two write their texture on one line. Both shipped
            # UN-encoded while their colours had been re-authored anyway, so
            # the cast iron rendered at albedo 0.021 against the matte-black
            # enamel beside it at 0.035: the iron came out DARKER than the
            # paint, which is backwards.
            "srgb": True,
            # The oxide too: cast_iron defaults it to a DISPLAY value, which
            # under srgb=True would encode to a pale milky tan rather than
            # rust. Passed rather than patched into the family, because the
            # family is shared.
            # THE IRON HAS TO SIT ABOVE THE PAINT. At base 0.0212 with
            # metallic 0.7 the effective diffuse was 0.0060 against
            # rig_black's 0.0352 — the castings rendered 5.9x DARKER than
            # the matte enamel bolted to them, which is backwards on any
            # real machine. An earlier note here spotted the inversion and
            # prescribed srgb, but srgb moved both entries' absolute level
            # and left the ORDERING exactly where it was: the fix for a
            # ratio is never a change that scales both sides.
            #
            # Foundry-skinned cast iron runs 2-4x above matte black. 0.117
            # linear luma at metallic 0.25 gives 0.088 effective, i.e.
            # 2.5x the enamel.
            "params": {
                "base": [0.1210, 0.1160, 0.1210],
                # The rust has to keep its RATIO to the iron, not merely
                # move in the same direction. Lifting the base 5.71x and
                # the oxide only 2.49x landed the stain at 0.985x the
                # body's luminance — iso-luminant, which is the one place
                # a stain cannot be seen; all it had left was 19 counts of
                # chroma. Scaled to hold the ~1.1x a rust bloom needs
                # (luminance 0.232), hue unchanged.
                "oxide": [0.5634, 0.1523, 0.0472],
                # The sand-cast grain, bought back. See cast_iron's own
                # note: the linear contrast never changed, but at this
                # lighter base the sRGB encode leaves it under one code
                # value of standard deviation, which is a banding map.
                "contrast": 2.0,
            },
        },
        "color": [0.1210, 0.1160, 0.1210, 1.0],
        # 0.25, not 0.7. A casting that has stood outside wears an oxide
        # SKIN, and oxide is a dielectric — this is the same argument
        # rig_black makes in its own entry and it was never applied here.
        "metallic": 0.25,
        "roughness": 0.62,
    },
    f"{MOD_ID}_hazard": {
        "texture": {
            "family": "hazard_chevron",
            # Linear values in an 8-bit PNG that the engine reads as sRGB
            # arrive up to 9x too dark, and rotate hue on the way.
            "srgb": True,
            "size": 512,
            # `relief` exists for exactly this and high_five was not
            # opting in: mean tilt 0.32 degrees on a plinth the player
            # parks against. Painted chevrons on plate have a real paint
            # edge, and this draws it.
            "params": {
                "c1": [0.91141, 0.50708, 0.0049],
                "c2": [0.01165, 0.01165, 0.01341],
                "relief": 0.55,
            },
            "normal_strength": 7.0,
        },
        "color": [0.91141, 0.50708, 0.0049, 1.0],
        # Painted chevrons on steel are paint, and paint is a dielectric.
        "metallic": 0.0,
        "roughness": 0.55,
    },
    # Road decal: the hazard border and the painted open-hand silhouette are
    # PAINT in the map, never geometry. (No lane arrows — this comment used
    # to promise them and the family has never drawn any.) Marking plates on a
    # drivable surface betray themselves by casting shadows and catching
    # edge light (Boot of Doom, 2026-08-13; the same law as the catapult
    # ramp_deck).
    f"{MOD_ID}_slap_pad": {
        "texture": {
            "family": "slap_pad",
            # Linear values in an 8-bit PNG that the engine reads as sRGB
            # arrive up to 9x too dark, and rotate hue on the way.
            "srgb": True,
            # 1024, not 2048. At 2048 this one 9.7 m road patch was 11.7 MB of
            # an 84 MB zip — 14% of the download for the flattest surface on
            # the prop, whose own family docstring says it carries no relief.
            "size": 1024,
            "params": {
                # slap_pad defaults these in LINEAR; with srgb=True they would encode
                # ~3x lighter than authored, so they are stated here converted.
                "base": [0.02198, 0.02198, 0.02452],
                "aspect": 1.0,
                "paint": [0.74841, 0.74841, 0.71057],
                "warn": [0.8689, 0.477, 0.0049],
                "hand_scale": 0.60,
            },
        },
        "color": [0.02198, 0.02198, 0.02452, 1.0],
        "metallic": 0.0,
        "roughness": 0.90,
    },
    f"{MOD_ID}_console_cream": {
        "texture": {
            "family": "painted_metal",
            # Linear values in an 8-bit PNG that the engine reads as sRGB
            # arrive up to 9x too dark, and rotate hue on the way.
            "srgb": True,
            "size": 1024,
            # A mid-century enamel cabinet genuinely has orange peel, and
            # at a bright base the sRGB encode compressed painted_metal's
            # +/-3% spread to NINETEEN unique RGB triplets — the flattest
            # surface on the prop.
            "params": {
                "base": [0.80735, 0.74841, 0.60383],
                "rough": 0.34,
                "peel": 0.25,
                "grain": 0.25,
                "orange_peel": 0.30,
            },
            # Mean tilt was 0.34 degrees — the flattest surface on the prop,
            # on the one panel the player stands directly in front of.
            "normal_strength": 8.0,
        },
        "color": [0.80735, 0.74841, 0.60383, 1.0],
        "metallic": 0.1,
        "roughness": 0.34,
    },
    f"{MOD_ID}_console_walnut": {
        "texture": {
            "family": "wood",
            # Linear values in an 8-bit PNG that the engine reads as sRGB
            # arrive up to 9x too dark, and rotate hue on the way.
            "srgb": True,
            "size": 1024,
            "params": {
                "early": [0.13287, 0.0489, 0.01848],
                "late": [0.02323, 0.00883, 0.00412],
                "rings": 17.0,
                "sheen": 0.0,
                "pore": 0.2,
            },
        },
        "color": [0.08898, 0.0331, 0.01165, 1.0],
        "metallic": 0.0,
        "roughness": 0.45,
    },
    f"{MOD_ID}_panel_legend": {
        "texture": {
            "family": "panel_legend",
            # Linear values in an 8-bit PNG that the engine reads as sRGB
            # arrive up to 9x too dark, and rotate hue on the way.
            "srgb": True,
            "size": 1024,
            "params": {
                # panel_legend defaults these in LINEAR; with srgb=True they would encode
                # ~3x lighter than authored, so they are stated here converted.
                "base": [0.0044, 0.0049, 0.00575],
                "ink": [0.82757, 0.89001, 0.9774],
                "title": "SLAP CONTROL",
                "labels": PANEL_LEGEND_LABELS,
                "aspect": PLATE_W / PLATE_H,
            },
        },
        "color": [0.0044, 0.0049, 0.00575, 1.0],
        "metallic": 0.3,
        "roughness": 0.5,
    },
    # Builder's plate. Ratings derive from the mass/energy ledger under
    # BEHAVIOR — the LINE rating, not the stroke peak, because the peak
    # comes out of the flywheel. Period notation, matching the Boot of
    # Doom and LAHC Centrifuge plates: same maker, same drawing office.
    f"{MOD_ID}_plate_data": {
        "texture": {
            "family": "panel_legend",
            # Linear values in an 8-bit PNG that the engine reads as sRGB
            # arrive up to 9x too dark, and rotate hue on the way.
            "srgb": True,
            "size": 512,
            "params": {
                # panel_legend defaults these in LINEAR; with srgb=True they would encode
                # ~3x lighter than authored, so they are stated here converted.
                "base": [0.0044, 0.0049, 0.00575],
                "ink": [0.82757, 0.89001, 0.9774],
                "title": "",
                "aspect": BACK_PLATE_W / BACK_PLATE_H,
                "labels": [
                    [0.5, 0.855, "C H A R L I E   C O .", 1.25],
                    [0.5, 0.665, "SALUTATION MACHINERY", 0.8],
                    [0.5, 0.530, "MODEL HF-5   SER. 0041", 0.75],
                    [0.5, 0.395, "6600 V  3 PH  60 CY", 0.75],
                    [0.5, 0.260, "990 A   13300 H.P.", 0.75],
                    [0.5, 0.110, "DUTY S5 6 OPS/MIN   PAT. PEND.   U.S.A.", 0.52],
                ],
                "rules": [[0.775, 0.30, 0.014]],
            },
        },
        "color": [0.0044, 0.0049, 0.00575, 1.0],
        "metallic": 0.6,
        "roughness": 0.38,
    },
    f"{MOD_ID}_btn_bakelite": {
        "texture": {
            "family": "bakelite",
            "srgb": True,
            "params": {"base": [0.00719, 0.00598, 0.00598]},
        },
        "color": [0.00719, 0.00598, 0.00598, 1.0],
        "metallic": 0.15,
        "roughness": 0.4,
    },
    f"{MOD_ID}_seg_amber": {
        "color": [0.98, 0.62, 0.10, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    # THE ARMED BEACON. The old "armed lamp" was an 8 cm unlit jelly-bean
    # on an 8.6 m machine -- its arming gesture (a 9 cm slide) was
    # invisible at any distance, which the dusk render finally proved.
    # This is a real industrial dome beacon at the centrifuge's proven
    # daylight-conspicuity rating; the slide gag stays on top of the glow.
    f"{MOD_ID}_beacon_red": {
        "color": [0.95, 0.10, 0.06, 1.0],
        "emissive": [1.0, 0.10, 0.05],
        "metallic": 0.0,
        "roughness": 0.30,
        "stage": {"emissiveIntensityNits": 1800},
        "double_sided": True,
    },
    f"{MOD_ID}_seg_red": {
        "color": [0.85, 0.14, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_seg_green": {
        "color": [0.22, 0.78, 0.30, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
}

# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------
# Both Overlaps. A Contains approach gate would demand the whole vehicle be
# inside a lane box before the hand woke up, and would abort every time a
# wheel crossed the edge — the mistake Boot of Doom's kick pad was
# play-tested out of on 2026-07-22.

TRIGGERS = {
    # The approach corridor, and its LENGTH IS A DERIVED SAFETY MARGIN, not
    # a look-nice number. The machine cannot swing until the alert and the
    # windup have run, so a subject must stay in the corridor for at least
    #
    #     alert_seconds + windup_seconds + swing_lead_seconds
    #       = 0.45 + 0.85 + 0.28 = 1.58 s
    #
    # (This line has been stale once already -- it read 0.30 while the lead
    # was 0.45. It is arithmetic on three BEHAVIOR keys; trust those.)
    #
    # or it is past the strike plane before the arm is cocked. At the
    # 60 m/s a committed player will actually arrive at, that is 96 m. 120 m
    # carries the margin to 2.0 s, and it also means the "the hand sees you
    # coming" line lands a long way out, which is the anticipation the pack
    # is built on. Being long costs nothing: the release is decided by the
    # LEAD, not by the corridor.
    # The near edge stops 16 m short of the strike plane, and that gap is
    # the CONSOLE APRON. The console sits at y = -5.0 on the shoulder, and
    # with the corridor running to y = -4 a player parked where they could
    # read the panel overlapped both boxes at once and was launched every
    # 8.7 s, forever, while trying to set the dials. 108 m still leaves
    # 124 m of run-up to the plane, well over the 96 m the timing budget
    # above needs.
    "approach": {
        "mode": "Overlaps",
        "center": [0.0, -70.0, 2.0],
        "dimensions": [9.6, 108.0, 4.6],
    },
    # The lane the palm actually sweeps, swept at contact time exactly like
    # the flyswatter and the boot: whoever is in it when the palm arrives
    # gets slapped, whether they parked on the mark or tried to run.
    #
    # OFFSET +2.0 IN X, and that is the whole of this prop's skill line.
    # At contact the hand occupies x from -2.3 (the wrist) to +6.3 (the
    # fingertips). Centred on the origin the box ran -5.2 to +5.2, so it
    # launched cars at x = -4.5 with nothing over them but the forearm
    # passing 3.4 m overhead, and did NOT launch a car at x = +6.2 that the
    # fingertips demonstrably swept. Both halves wrong, in opposite
    # directions. Matching the box to the hand fixes the phantom AND makes
    # the mast-side lane a real dodge — hold the inside line and the palm
    # goes past your door, which is the same trick monster_flyswatter's
    # outer lane edge is built on.
    "slap_zone": {
        "mode": "Overlaps",
        "center": [2.0, 0.0, 1.95],
        "dimensions": [9.0, 7.6, 3.9],
    },
}

EFFECTS = {
    # Impact burst AT the strike interface, thrown down-road -- not fog on
    # the tarmac. The old single node sat at the pad surface and stayed on
    # for the whole follow+hold (1.3 s): a beige dome squatting on the
    # stencil through every after-shot of the mod. Two nodes now bracket
    # the contact height and the swing turns them off 0.3 s after the hit.
    # THE CLOUD MUST TRAVEL. Switching the emitters off cannot recall
    # particles already emitted, and BNGP_2's dust ejects at 1 m/s -- so
    # the 0.3 s burst still parked a beige dome on the pad stencil for the
    # particle lifetime, dead centre of every after-shot (chase_015-020).
    # These are census-verified emitters whose particles LEAVE: utah dust
    # ejects at 4.2 m/s, sand at 3, and gravel is ballistic chunks that
    # fall instead of hang. Aimed down-road, the wake follows the car out
    # of frame instead of squatting on the joke.
    "slap_dust": {
        "emitter": "BNGP_utah_dust",
        "position": [0.0, 0.6, 1.3],
        "direction": [0.0, 0.80, 0.60],
    },
    "slap_dust2": {
        "emitter": "BNGP_8",
        "position": [0.6, -0.3, 0.7],
        "direction": [0.15, 0.76, 0.63],
    },
    "slap_grit": {
        "emitter": "BNGP_16",
        "position": [0.0, 0.2, 0.5],
        "direction": [0.0, 0.85, 0.53],
    },
    # Steam off the slew gearbox after a swing — the drive dumping heat.
    "slew_steam": {
        "emitter": "BNGP_34",
        "position": [MAST_X, MAST_Y + 1.15, HUB_Z - 0.55],
        "direction": [0.0, 0.55, 0.84],
    },
}

# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------
# Power ledger behind the 13300 H.P. nameplate, derived from the numbers
# in this file rather than invented. A reviewer's recompute (2026-08-26)
# caught THREE figures here that did not reproduce -- the swung inertia
# had forgotten the counterweight it swings, the cwt paragraph was a full
# rescale stale (its shipped mass was 4.8x the balance its own text
# claimed), and the 2300 V "ceiling" argument used a current that was
# arithmetic fiction. Everything below re-derives, and the cwt GEOMETRY
# was resized to make the balance paragraph true rather than the
# paragraph bent to excuse the geometry.
#
#   hand      8.6 m of foam latex over a steel spine, ~4.1 t. As a rod
#             from 9.6 to 18.2 m (not a point mass at 11.9, which
#             understated its own spread): I = m(r1^2+r1r2+r2^2)/3
#             = 8.18e5 kg m^2
#   arm       6.66 m upper + 6.54 m forearm + collar, ~13.8 t, c.g. at
#             5.6 m: 4.24e5
#   cwt       7 plates x 1.68 x 0.30 x 1.06 m of steel = 7 x 4.19 t
#             = 29.4 t at 4.10 m, first moment 120 t.m against the arm's
#             hand 42.2 + boom 36.7 = 78.9 t.m — deliberately OVER-balanced
#             at 1.52x, because the reference stand is chain-guyed and a
#             real slew bearing prefers its overturning moment on the
#             machine side. (The plates measured 2.45 x 0.44 x 1.55 for
#             one round: a rescale reached them but not this paragraph,
#             and the stack was 4.8x overbalanced while the text said
#             1.53x. The geometry moved to meet the text.)
#   swung     I = 8.18e5 + 4.24e5 + cwt (29.4e3 x 4.10^2 + spread 2.1e4
#             = 5.14e5) = 1.756e6 kg m^2 — the cwt SLEWS WITH THE ARM,
#             which is the whole point of a counterweight, and the one
#             component the previous total forgot
#   stroke    -104 -> 0 deg in slap_seconds on a t^slap_ease pose, so
#             omega peaks at ease*dtheta/T = 1.5*1.8151/0.28 = 9.72 rad/s,
#             a 177 m/s fingertip and 115 m/s at the palm centre.
#             NOT "a real slap at scale": Froude time scaling at 44.1x is
#             sqrt(44.1) = 6.64, which maps a 0.10-0.15 s human strike to
#             0.66-1.0 s; 0.28 s back-translates to a 42 ms human stroke,
#             beyond any recorded human motion, and the fingertip runs
#             Mach 0.52. The argument for it is FILM GRAMMAR (the strike
#             is subliminal violence between a staged draw and a held
#             follow-through -- see the slap block below), and the ledger
#             claims the physics it has, not the realism it does not.
#   power     theta ~ t^1.5 is the CONSTANT-POWER trajectory: P = I a w
#             = 1.125 I dtheta^2 / T^3 = 296 MW, flat across the whole
#             stroke -- precisely what an ideal flywheel dumping through a
#             power-limited drive does. (Torque diverges as t^-0.5 at the
#             first instant; a real drive torque-limits the first degree.)
#             The ease exponent was chosen for feel and turned out to be
#             the machine's most literal piece of engineering.
#   energy    arm 0.5 * 1.756e6 * 9.7237^2 = 83.0 MJ, plus 1.4 MJ into a
#             1.6 t car at the default power setting = 84.4 MJ per slap
#   contact   the 0.12 s injection dwell is defensible twice over: it is
#             the Froude-scaled human slap contact (10-30 ms x 6.64 =
#             66-200 ms) AND the kinematic window before the 59 m/s
#             follow-through palm falls behind the launched car.
#   LINE      the plate rates a DUTY, and the duty is PRINTED ON IT --
#             "S5 6 OPS/MIN" -- because "shortest possible cycle" was
#             false twice over (the corridor cycle is 5.83 s with no
#             hold and the pad path cycles in 4.53 s, and pairing the
#             slap's energy with the whiff's period was incoherent).
#             At 6 slaps/min: 84.4 MJ / 10 s = 8.44 MW mechanical,
#             9.93 MW electrical at 85% drive efficiency = 13,300 H.P.
#             That genuinely outgrows a 2300 V bus (9.93e6 / (1.732 x
#             2300 x 0.88) = 2,830 A against ~2,000 A gear), so 6600 V:
#             9.93e6 / (1.732 * 6600 * 0.88) = 987 A, plated 990 A.
#             (The previous revision plated 630 A off a 2,320 A figure
#             that reproduced from no equation in the file.)
#
#             HISTORY, kept as a warning (the lines it once pointed at
#             were rewritten in the 2026-08-26 recompute):
#             THE STROKE-DERIVED LINES ARE THE ONES THAT GO STALE. They were
#             computed against a 0.30 s QUADRATIC swing and survived the
#             change to 0.45 s on t^1.4 — energy goes as omega^2, so they
#             were out by 4.6x while the two lines above them had already
#             been corrected. A timing change silently invalidates the
#             whole chain and the builder's plate that descends from it,
#             and a comment admitting that while still printing the wrong
#             figures is worse than either fixing or deleting them.

BEHAVIOR = {
    "camera_distance": 46.0,

    # --- the anticipation ------------------------------------------------
    "alert_seconds": 0.45,
    "windup_seconds": 0.85,
    # The hand does not fire on a timer. Once cocked it HOLDS, tracking the
    # subject's closing speed, and releases when the subject is
    # swing_lead_seconds from the strike plane. This is the whole reason
    # the prop works at 15 m/s and at 55 m/s.
    # MUST EQUAL slap_seconds. The release fires when the subject is this
    # many seconds from the strike plane; the palm arrives slap_seconds
    # after the release. They are one number wearing two hats, and tuning
    # either alone mis-aims the whole machine by the difference times the
    # closing speed — 0.10 s at 40 m/s is 4 m, more than half the strike
    # zone. test_high_five_geometry asserts the identity.
    "swing_lead_seconds": 0.28,
    # Seconds WITHOUT A USABLE LEAD before the hand gives up and slaps
    # anyway. Not seconds spent cocked: a 12 m/s car legitimately needs
    # ~11 s of cocked time to cross the corridor, and when this counted
    # cocked time instead it fired first every single pass, so the
    # prediction never decided anything below about 20 m/s and the palm
    # arrived 54 m behind the car. The timer now measures how long the
    # machine has had no reason to keep waiting, which is what a fallback
    # is for — so a parked car still gets slapped after 3.2 s, and that is
    # still the funnier outcome for anyone who stops to look at it.
    "max_hold_seconds": 3.2,
    # Lead prediction is only trusted above this closing speed; below it
    # the hold timer owns the release, so a reversing or stationary car
    # cannot produce a nonsense negative or enormous time-to-arrive.
    "min_closing_mps": 2.5,

    # --- the slap --------------------------------------------------------
    # 0.28 s on t^1.5, and this REVERSES an earlier play-test on purpose.
    #
    # The 2026-08-24 note here argued frames-over-the-road: at 0.30 s/t^2
    # the stroke was 85 ms over the road and read as a flicker, so it was
    # slowed to 0.45 s for legibility. The 2026-08-25 play-test overrode
    # that: at 0.45 s the swing reads as MACHINERY, not as a slap. A real
    # slap's strike phase is 0.10-0.15 s and on video it is 3-6 frames --
    # the strike itself is subliminal violence, and the READ comes from the
    # slow wind-up before it and the held follow-through after it, both of
    # which this machine already stages. So the stroke is fast again, the
    # legibility burden moves to the anticipation and the dust hit, and the
    # two decisions and their dates are both kept here because whoever
    # tunes this next needs to know it has already been pushed both ways.
    #
    # Peak omega = ease * 1.8151 rad / 0.28 s = 9.72 rad/s: a 177 m/s
    # fingertip, 115 m/s at the palm centre. Every figure in the power
    # ledger above descends from this pair -- recompute the chain and the
    # builder's plate if either moves.
    "slap_seconds": 0.28,
    "slap_ease": 1.5,
    # THE TUMBLE. launchSubject replaces linear velocity along the palm
    # normal, which alone reads as a nudge from a giant air hockey paddle:
    # the car sails flat. A real slap is an off-centre impulse -- the palm
    # lands on the flank ABOVE the car's centre of mass, so it both throws
    # and SPINS. The engine has no GE-side angular injection, but the
    # vehicle VM's `thrusters.applyAccel(accel, dt, nodeId, angularAccel)`
    # wraps obj:applyClusterLinearAngularAccel, so the runtime queues the
    # spin into the car's own physics over a contact dwell and the tumble
    # integrates honestly from there.
    #
    # One physical model, not two dials: spin axis = r x d, where r is the
    # palm-centre-to-car-CoM offset and d the launch direction. That single
    # cross product yields end-over-end roll AND drag yaw with coherent
    # signs. Magnitude = transfer * (arm rate at contact) * POWER mult --
    # the arm rate comes from the ACTUAL swingFrom, so a pad slap from rest
    # spins less than a full corridor windup, for free.
    "slap_contact_seconds": 0.12,
    "slap_spin_transfer": 0.35,
    # NOTE: the maximum reachable spin is 0.35 * 9.7237 * 2.6 = 8.85, so
    # this cap binds at NO console setting today -- it guards future edits
    # to transfer/ease/timing, not the shipped ladder.
    "slap_spin_cap_rps": 9.0,
    # THE RELEASE FIRES EARLY BY THIS MUCH -- and 0.06, not the 0.10
    # first fitted, because the first fit trusted one measurement taken
    # with a different detector. The pre-bias lag looked like 0.11 s
    # (car 2.9 m PAST the plane at 26.5 m/s, speed-jump detector on the
    # CoM); with the bias in, altitude-detected offsets across 22/40/55
    # m/s back out a true lag of only ~0.045 s, and at 0.10 the palm led
    # a 55 m/s car by enough that ordinary run-to-run spread tipped a
    # session-6 pass into a WHIFF -- the machine beaten by the player it
    # is explicitly sized never to lose to. 0.06 centres every measured
    # offset inside +/-1.5 m with 4+ m of whiff margin. The stub cannot
    # reproduce any of this (its quantization ceiling is ~0.9 m); the
    # live gate's arrival assertion is the guard.
    "release_bias_seconds": 0.06,
    # The pad path swings from REST, so its palm arrives at 72/104 of the
    # windup swing's speed -- and the LAUNCH scales the same way, because
    # one physical model covers speed and spin or it covers neither.
    # (The spin already did this via swingFrom; the speed draw did not,
    # which a reviewer read as the model applied by halves.)
    "pad_alert_seconds": 0.5,
    # Flight scoreboard: the machine watches what it launched and reports.
    "score_settle_mps": 1.5,
    "score_settle_seconds": 0.8,
    "score_timeout_seconds": 12.0,
    # The palm held out down-road after the car it just launched. It is what
    # a person does after a high five, and it is the frame the clip gets cut
    # on.
    "follow_hold_seconds": 0.40,
    "follow_seconds": 0.55,
    "return_seconds": 2.10,
    "cooldown_seconds": 1.20,

    # --- launch ----------------------------------------------------------
    # Base palm speed before POWER. The palm centre genuinely travels at
    # ~106 m/s at peak, so handing the car even a third of that is
    # generous; these are the authored play numbers, not the kinematics.
    # Narrowed from 24-38. A 1.58x speed span is 2.5x in range, which is SIX
    # TIMES the P9->P10 step (1.098x) — so the top third of a ten-segment
    # ladder could not be told apart by watching, and the console was
    # selling a precision the machine did not have.
    "slap_speed_min_mps": 28.0,
    "slap_speed_max_mps": 34.0,

    # --- animation -------------------------------------------------------
    # Degrees of extra flexion added at every joint of a twitching finger.
    "twitch_deg": TWITCH_DEG,
    "twitch_rate": 17.0,

    # --- console ---------------------------------------------------------
    # POWER 1..10 -> 1.0x..5.0x. TILT is seven detents, 0..60 deg in tens,
    # so the ladder shows the setting honestly with seven segments.
    "power_levels": 10,
    # 5.0 put P10/TILT-40 at 1844 m of range, a 387 m apex and 17.8 s of
    # hang time — off most maps and unwatchable. 2.6 tops out near 500 m,
    # which is still enormous and still lands somewhere you can see.
    "power_multiplier_max": 2.6,
    # Seven detents of SEVEN degrees, not ten. The wrist rolls about the
    # forearm axis through WRIST_POINT at z = 2.30, so the palm's ulnar edge
    # climbs as 2.30 - (PALM_WIDTH/2)*cos(tilt): 0.36 m at flat, but 1.05 m
    # at 50 deg and 1.33 m at 60 — over the roofline. At those two detents
    # the hand measurably passed OVER the car and launched it anyway, which
    # is the one thing this machine must never do. 42 deg keeps the bottom
    # edge at 0.86 m, still into the door.
    "tilt_levels": 7,
    "tilt_step_deg": 7.0,
    "default_power_level": 3,
    "default_tilt_index": 2,
}

# ---------------------------------------------------------------------------
# Runtime behaviour
# ---------------------------------------------------------------------------
# GEOMETRY travels with the CODE, not through the handoff. Everything the
# pose maths needs — pivots, axes, azimuths — is formatted into the Lua
# below straight from the derived section above, so a build.py-only rebuild
# always ships geometry that agrees with spec.py. Only PLAY numbers (times,
# speeds, console ranges) go through BEHAVIOR/`B`, and those are the ones
# the REQUIRED guard checks, because those are the ones a stale handoff can
# silently drop. (sumo serial 30, 2026-08-14.)


def _vec3(value) -> str:
    return f"vec3({value[0]:.6f}, {value[1]:.6f}, {value[2]:.6f})"


def _lua_constants() -> str:
    newline = "\n"
    digit_axes = newline.join(
        f"  {name} = {_vec3(DIGIT_AXES[name])}," for name in DIGIT_ORDER
    )
    digit_pivots = newline.join(
        f"  {name} = {_vec3(DIGIT_PIVOTS[name])}," for name in DIGIT_ORDER
    )
    twitch_phase = newline.join(
        f"  {name} = {TWITCH_PHASE.get(name, 0.0):.3f}," for name in DIGIT_ORDER
    )
    rest_curl = newline.join(
        [
            f"  {name} = {sum(FINGER_CURL_DEG[name]) / 3.0:.4f},"
            for name in FINGER_ORDER
        ]
        + [f"  thumb = {sum(THUMB_CURL_DEG) / 2.0:.4f},"]
    )
    digits = ", ".join(f'"{name}"' for name in DIGIT_ORDER)
    return f"""
-- === generated from spec.py - do not hand-edit ==========================
local DIGITS = {{{digits}}}
-- Authored-frame flexion axis of each digit. A positive angle curls INTO
-- the palm; spec.finger_flex_axis explains why this is the only axis that
-- can, and where its sign comes from.
local DIGIT_AXES = {{
{digit_axes}
}}
-- Authored-frame joint centre each digit part pivots about. The proximal
-- cap of every digit is a sphere concentric with this point, so flexing it
-- cannot open a gap at the knuckle however far it turns.
local DIGIT_PIVOTS = {{
{digit_pivots}
}}
local TWITCH_PHASE = {{
{twitch_phase}
}}
-- How far the hand drops per unit of (1 - cos tilt), so the palm’s
-- ulnar edge stays on the car’s flank instead of climbing to the
-- roofline at the top detent. See poseArm.
local ROLL_DROP = {ROLL_COMPENSATION * PALM_WIDTH / 2.0:.6f}
local WRIST_POINT = {_vec3(WRIST_POINT)}
local FOREARM_AXIS = {_vec3(U_REST)}
local SLEW_X, SLEW_Y = {SLEW_POINT[0]:.6f}, {SLEW_POINT[1]:.6f}
local REST_DEG = {REST_DEG:.4f}
local WINDUP_DEG = {WINDUP_DEG:.4f}
local CONTACT_DEG = {CONTACT_DEG:.4f}
local FOLLOW_DEG = {FOLLOW_DEG:.4f}
-- === end generated ======================================================
"""


LUA_BEHAVIOR = _lua_constants() + r"""
-- Every scalar this chunk reads out of the handoff. Behaviour CODE is
-- re-read from spec.py on every build.py run, but behaviour PARAMS reach
-- the runtime through the handoff, which only the BLENDER stage rewrites -
-- so adding a tunable and rebuilding with build.py alone ships Lua that
-- demands a key the shipped table does not have. That failure is silent and
-- total, so it is checked out loud at registration.
local REQUIRED = {
  "alert_seconds", "windup_seconds", "swing_lead_seconds", "max_hold_seconds",
  "min_closing_mps", "slap_seconds", "follow_seconds", "return_seconds",
  "cooldown_seconds", "slap_speed_min_mps", "slap_speed_max_mps",
  "slap_ease", "follow_hold_seconds",
  "slap_contact_seconds", "slap_spin_transfer", "slap_spin_cap_rps",
  "release_bias_seconds", "pad_alert_seconds",
  "score_settle_mps", "score_settle_seconds", "score_timeout_seconds",
  "twitch_deg", "twitch_rate",
  "power_levels", "power_multiplier_max", "tilt_levels", "tilt_step_deg",
  "default_power_level", "default_tilt_index", "camera_distance",
}

local function tunablesPresent(state)
  local missing = {}
  for _, name in ipairs(REQUIRED) do
    if type(B[name]) ~= "number" then missing[#missing + 1] = name end
  end
  if #missing == 0 then return true end
  emitError(state, "handoff_tunables_missing", {keys = table.concat(missing, ",")})
  showMessage(
    "High Five: shipped build is missing runtime constants. "
    .. "Re-run the Blender stage.", 8.0)
  return false
end

-- ===========================================================================
-- Rotation conventions, stated once
-- ===========================================================================
-- The engine's `q * vec3` applies the OPPOSITE handedness to the textbook
-- quaternion axisAngle() builds - the same reversal documented on basisQuat's
-- conjugate and behind the "quats compose LEFT-TO-RIGHT" rule. So an ordinary
-- right-handed turn of `angle` about `axis` needs the axis NEGATED going in.
-- Boot of Doom found this empirically on 2026-08-13 ("vec3(-1,0,0) makes
-- positive angles lift the toe") before there was a written reason for it.
-- Every orientation in this chunk goes through turn(), so the reversal is
-- applied in exactly one place and can be re-proved in exactly one place.
-- The phases in which the machine has a subject and has not swung at it
-- yet. Declared HERE, above poseConsole, and not beside behavior.onEnter
-- where it was first written: a Lua local binds at its definition point, so
-- a table declared below its first reader resolves as a nil GLOBAL and the
-- chunk still compiles clean. It cost 1200 silenced behavior_update_failed
-- errors in one 20 s run — every one swallowed by lua_kit's pcall, with the
-- only symptom being that the arm stopped advancing past `cocked`.
local TRACKING_PHASES = {alert = true, windup = true, cocked = true}

local function turn(axis, angle)
  return axisAngle(vec3(-axis.x, -axis.y, -axis.z), angle)
end

-- POSITIONS never go through a quaternion. Rodrigues in plain trig is
-- handedness-unambiguous, it is the same formula spec.py and the offline math
-- test use, and it cannot silently transpose the way a quat-vector product
-- can. A transposed frame is exactly identity on a level spawn and metres
-- wrong on a slope (measured live 2026-08-24), which is the worst possible
-- failure signature.
local function rodrigues(v, axis, angle)
  local c, s = math.cos(angle), math.sin(angle)
  local dot = v.x * axis.x + v.y * axis.y + v.z * axis.z
  local k = 1 - c
  return vec3(
    v.x * c + (axis.y * v.z - axis.z * v.y) * s + axis.x * dot * k,
    v.y * c + (axis.z * v.x - axis.x * v.z) * s + axis.y * dot * k,
    v.z * c + (axis.x * v.y - axis.y * v.x) * s + axis.z * dot * k)
end

-- Rotate an authored-frame point about the vertical slew axis.
local function swingPoint(p, delta)
  local dx, dy = p.x - SLEW_X, p.y - SLEW_Y
  local c, s = math.cos(delta), math.sin(delta)
  return vec3(SLEW_X + dx * c - dy * s, SLEW_Y + dx * s + dy * c, p.z)
end

-- ===========================================================================
-- Console readings
-- ===========================================================================
local function powerMult(state)
  local level = state.behavior.powerLevel or B.default_power_level
  return 1.0 + (level - 1) * (B.power_multiplier_max - 1.0) / (B.power_levels - 1)
end

local function tiltDegrees(state)
  return (state.behavior.tiltIndex or B.default_tilt_index) * B.tilt_step_deg
end

-- ===========================================================================
-- Pose
-- ===========================================================================
-- The authored REST pose is baked into every exported mesh, so every part
-- rotation below is a DELTA from rest, never an absolute angle.
--
-- The arm is one rigid body about the slew axis. The hand rides on the arm
-- and adds the TILT roll about the forearm. Each digit rides on the hand and
-- adds its own flexion. The product runs left-to-right, so the innermost
-- joint is the LEFT operand: flex, then roll, then swing.
local function poseArm(state, azimuthDeg, tiltDeg)
  local delta = math.rad(azimuthDeg - REST_DEG)
  local roll = math.rad(tiltDeg or 0)
  local swingQ = turn(vec3(0, 0, 1), delta)
  local rollQ = turn(FOREARM_AXIS, roll)
  setPartPose(state, "arm", nil, swingQ)
  -- The CUFF takes the swing and the drop but NOT the roll: it is the
  -- housing the hand turns inside, and it rides a vertical slide in the
  -- wrist knuckle so the palm can be held down as the wrist rolls. Bolting
  -- it to the arm instead left a rigid 0.374 m displacement across the
  -- joint at the top detent, against 0.17 m of bore clearance — the stump
  -- would come out through the cuff wall.
  local cuffDrop = ROLL_DROP * (1 - math.cos(roll))
  setPartPose(
    state, "wrist",
    swingPoint(WRIST_POINT, delta) - WRIST_POINT - vec3(0, 0, cuffDrop),
    swingQ)
  -- p' = Swing(Roll(p - W) + W), plus a DROP.
  --
  -- The wrist rolls about an axis at WRIST_Z, so the palm's ulnar edge
  -- climbs as WRIST_Z - halfWidth*cos(tilt) — 0.78 m flat but 1.28 m at the
  -- top detent, which is roofline. Capping the tilt angle only netted 5 cm
  -- of that. The honest fix is to lower the hand as it rolls so the blade
  -- stays on the car's flank at every setting, which is what a machine with
  -- a wrist actuator would have to do anyway.
  --
  -- 0.75, not 1.0: full compensation would take the LITTLE FINGER below
  -- grade, and the fingers hang 0.6 m under the palm's edge. The residual
  -- keeps the swept minimum at +0.15 m. test_nothing_on_the_hand_sweeps_
  -- below_grade and test_the_palm_still_reaches_a_cars_body pin both ends.
  local drop = ROLL_DROP * (1 - math.cos(roll))
  setPartPose(
    state, "hand",
    swingPoint(WRIST_POINT, delta) - WRIST_POINT - vec3(0, 0, drop),
    rollQ * swingQ)
  return drop
end

local function poseDigits(state, azimuthDeg, tiltDeg, twitchDeg, clock)
  local delta = math.rad(azimuthDeg - REST_DEG)
  local roll = math.rad(tiltDeg or 0)
  local swingQ = turn(vec3(0, 0, 1), delta)
  local rollQ = turn(FOREARM_AXIS, roll)
  for _, name in ipairs(DIGITS) do
    local axis = DIGIT_AXES[name]
    local pivot = DIGIT_PIVOTS[name]
    -- abs(sin), SUBTRACTED: the twitch is EXTENSION. A hand about to
    -- slap tenses flat -- the fingers strain straighter than their
    -- authored rest arc, they do not curl toward a grab. (Flexion twitch
    -- was the old read, and stacked on the old 23-32 deg curls it put the
    -- armed hand at 44-53 deg: a doorknob reach, the opposite of a five.)
    local flexDeg = 0
    if twitchDeg > 0 then
      flexDeg = -math.abs(
        math.sin(clock * B.twitch_rate + (TWITCH_PHASE[name] or 0))) * twitchDeg
    end
    -- Position: the pivot is carried by the hand's roll and then the arm's
    -- swing. Its own flexion turns about it and so cannot move it.
    local carried = rodrigues(pivot - WRIST_POINT, FOREARM_AXIS, roll) + WRIST_POINT
    -- The digits ride the hand, so they take the same roll drop it does.
    local drop = ROLL_DROP * (1 - math.cos(roll))
    setPartPose(
      state, "finger_" .. name,
      swingPoint(carried, delta) - pivot - vec3(0, 0, drop),
      turn(axis, math.rad(flexDeg)) * rollQ * swingQ)
  end
end

local function poseMachine(state, azimuthDeg, tiltDeg, twitchDeg, clock)
  poseArm(state, azimuthDeg, tiltDeg)
  poseDigits(state, azimuthDeg, tiltDeg, twitchDeg, clock)
  -- Recorded, not derived: a gate that recomputed the azimuth from the
  -- phase and the clock would be asserting on its own copy of the easing
  -- rather than on where the palm went.
  state.behavior.azimuthDeg = azimuthDeg
end

-- Console instruments. A segment is proud of the plate while the setting
-- reaches it and pushed +0.12 authored y - straight back through the plate
-- into the cabinet - when it does not (the centrifuge bar-graph idiom).
local function poseConsole(state)
  local b = state.behavior
  local lit = b.powerLevel or B.default_power_level
  for i = 1, B.power_levels do
    setPartPose(
      state, string.format("pow_seg%d", i),
      vec3(0, i <= lit and 0 or 0.12, 0), nil)
  end
  local tilt = (b.tiltIndex or B.default_tilt_index) + 1
  for i = 1, B.tilt_levels do
    setPartPose(
      state, string.format("tilt_seg%d", i),
      vec3(0, i <= tilt and 0 or 0.12, 0), nil)
  end
  -- TRACKING, not "busy". Lit while the machine has a subject and has not
  -- swung yet, which is exactly the window in which the information is
  -- worth anything to a driver; dark once it is committed, because by then
  -- nothing you do with it matters.
  local tracking = b.phase and TRACKING_PHASES[b.phase] and b.subjectId
  setPartPose(state, "armed_lamp", vec3(0, tracking and 0 or 0.09, 0), nil)
end

-- ===========================================================================
-- Lead prediction
-- ===========================================================================
-- Local +Y is the drive direction, so the strike plane is local y = 0 and a
-- subject's time to arrive is its own -y distance over its +y closing speed.
-- Both are projected through the LIVE prop frame, so this stays correct on a
-- slope and at any prop yaw.
local function timeToStrike(state, vehicle)
  local ok, position = pcall(function() return vehicle:getPosition() end)
  if not ok or not position or not finiteVector3(position) then return nil end
  local moving, velocity = pcall(function() return vehicle:getVelocity() end)
  if not moving or not velocity or not finiteVector3(velocity) then return nil end
  local forward = toWorldDir(state, vec3(0, 1, 0))
  local along = (position - toWorldPoint(state, vec3(0, 0, 0))):dot(forward)
  local closing = velocity:dot(forward)
  if closing < B.min_closing_mps then return nil end
  -- Already past the strike plane. Returning 0 here forced an immediate
  -- release and a guaranteed whiff 0.45 s later; nil hands it to the blind
  -- timer for the same outcome without burning the stroke.
  if along >= 0 then return nil end
  return -along / closing
end

-- Seconds until the tracked subject reaches the strike plane, or NIL when
-- there is no usable answer: no subject, a subject that has despawned, or
-- one that is stationary or reversing.
--
-- nil and "not yet due" are DIFFERENT and the caller must treat them
-- differently. An earlier version collapsed both into false, so the blind
-- timer counted every frame the machine was correctly waiting for a car
-- that was still 100 m out, and fired first on every pass below about
-- 20 m/s. The tell was that the measured miss distance did not change at
-- all when the fix went in.
-- Can the HAND actually get to this subject, laterally?
--
-- timeToStrike is purely longitudinal, and without this the re-scoring loop
-- would hand the aim to whoever arrives soonest regardless of which lane they
-- are in — so a fast car holding the mast-side ESCAPE lane outbid a slower one
-- in the kill lane, and the machine then timed its swing for someone it could
-- not reach and missed the one it could. Measured: nothing was launched at all.
--
-- The strike zone IS the hand's reach (its x span is wrist-to-fingertips), so
-- the zone's own half-extent is the honest test, and reading it from
-- TRIGGER_SPECS means it cannot drift from the box that does the launching.
local function reachable(state, vehicle)
  local ok, position = pcall(function() return vehicle:getPosition() end)
  if not ok or not position or not finiteVector3(position) then return false end
  local spec = TRIGGER_SPECS.slap_zone
  local lateral = (position - toWorldPoint(state, vec3(0, 0, 0)))
    :dot(toWorldDir(state, vec3(1, 0, 0)))
  return math.abs(lateral - spec.position.x) <= spec.scale.x / 2.0
end

local function leadSeconds(state, b)
  if not b.subjectId then return nil end
  local vehicle = exactVehicle(b.subjectId)
  if not vehicle then return nil end
  return timeToStrike(state, vehicle)
end

-- ===========================================================================
-- The slap
-- ===========================================================================
-- Forward declaration: slapStrikeZone flushes a superseded watch, and the
-- scorer is defined further down (it needs nothing above this point). A
-- bare `local function` there would leave THIS reference compiling as a
-- nil global -- the exact trap documented at the top of this chunk, which
-- this file then walked into a second time while fixing the scoreboard.
local finalizeWatch

local function slapStrikeZone(state)
  local mult = powerMult(state)
  local tilt = math.rad(tiltDegrees(state))
  -- ONE physical model covers speed and spin, or it covers neither: the
  -- palm from REST arrives at 72/104 of the windup swing's speed, so the
  -- launch scales exactly as the spin already did via swingFrom.
  local fromRadShared = math.rad(math.abs(state.behavior.swingFrom or WINDUP_DEG))
  local reachScale = fromRadShared / math.rad(math.abs(WINDUP_DEG))
  -- The palm normal at contact: the sweep tangent, rolled up by TILT about
  -- the forearm axis. At CONTACT_DEG the tangent is authored +y exactly, so
  -- the rolled normal is (0, cos tilt, sin tilt) and the launch elevation IS
  -- the tilt setting. Nothing else may set this direction - a slap can only
  -- throw a thing along the palm it was struck with.
  local direction = toWorldDir(state, vec3(0, math.cos(tilt), math.sin(tilt)))
  local slapped = 0
  for vehicleId in pairs(zoneOccupants(state, "slap_zone")) do
    local vehicle = exactVehicle(vehicleId)
    if vehicle then
      local speed = (B.slap_speed_min_mps
        + math.random() * (B.slap_speed_max_mps - B.slap_speed_min_mps))
        * mult * reachScale
      -- A PALM AT 100+ M/S NEVER BRAKES A CAR. Replace semantics alone
      -- turned a 55 m/s arrival into a 42 m/s departure, and the moment
      -- the scoreboard existed that read as the machine answering "your
      -- speed never mattered" to the one experiment every player runs.
      -- The launch keeps the car's own momentum along the palm normal
      -- when that is the larger number: hot runs out-throw slow ones,
      -- the dial still owns the floor, and the pad/corridor contrast
      -- survives untouched.
      local carried, incoming = pcall(function() return vehicle:getVelocity() end)
      if carried and incoming and finiteVector3(incoming) then
        local projection = incoming.x * direction.x
          + incoming.y * direction.y + incoming.z * direction.z
        if projection > speed then speed = projection end
      end
      if launchSubject(state, vehicle, direction * speed) then
        -- THE TUMBLE. See the slap_spin_* tunables for the model. The spin
        -- goes through the vehicle's OWN physics (thrusters.applyAccel ->
        -- obj:applyClusterLinearAngularAccel) over the contact dwell, so
        -- what happens after the palm leaves is the engine's honest
        -- integration, not an animation.
        local armRate = B.slap_ease * fromRadShared / B.slap_seconds
        local spin = math.min(
          B.slap_spin_cap_rps, B.slap_spin_transfer * armRate * mult)
        -- r: the EFFECTIVE CONTACT CENTROID relative to the struck car's
        -- CoM, authored frame. Not derived -- bounded: the palm plane
        -- centre sits ~1.8 m above a pickup's CoM, the car-face contact
        -- centroid ~0.5 m, and 1.30 is the authored point between them
        -- (foam wraps the roofline, so the pressure centre rides high).
        -- The engine then redistributes whatever is injected: measured
        -- live, torque-free precession amplifies the tumble 30-90% toward
        -- the car's low-inertia roll axis (Dzhanibekov), inside the
        -- energy bound sqrt(2E/I_roll). The injected number is the SEED.
        local r = vec3(-0.8, 0, 1.30)
        local d = vec3(0, math.cos(tilt), math.sin(tilt))
        local axis = vec3(
          r.y * d.z - r.z * d.y,
          r.z * d.x - r.x * d.z,
          r.x * d.y - r.y * d.x)
        local axisLen = axis:length()
        if axisLen > 1e-6 and spin > 0.01 then
          -- toWorldDir NORMALIZES -- it is a direction transform. Rotate
          -- the unit axis, then scale, or the spin ships as 1.00 rad/s
          -- whatever the model says (caught by the magnitude gate).
          local w = toWorldDir(state, axis) * spin
          local perDt = 1.0 / B.slap_contact_seconds
          vehicle:queueLuaCommand(string.format(
            "thrusters.applyAccel(vec3(0,0,0), %.4f, nil, vec3(%.4f, %.4f, %.4f))",
            B.slap_contact_seconds, w.x * perDt, w.y * perDt, w.z * perDt))
        end
        slapped = slapped + 1
        emitEvent(state, "I", "high_five_slapped", {
          subject_id = vehicleId,
          slap_speed_mps = speed,
          -- INJECTED, not final: the engine's rigid-body redistribution
          -- runs it up 30-90% after the palm leaves. The scoreboard
          -- measures the real thing; this field seeds it.
          spin_injected_rps = math.floor(spin * 100) / 100,
          power_mult = math.floor(mult * 100) / 100,
          tilt_deg = tiltDegrees(state),
        })
      end
    end
  end
  if slapped > 0 then
    setEffectActive(state, "slap_dust", true)
    setEffectActive(state, "slap_dust2", true)
    setEffectActive(state, "slap_grit", true)
    setEffectActive(state, "slew_steam", true)
    -- THE SCOREBOARD ARMS. The machine launched something; now it watches
    -- where it lands, because a 200 m tumbling flight that nobody
    -- measures reads as a glitch and one that gets a number reads as a
    -- score. Primary subject only -- the one it was aiming at, or the
    -- first thing it hit.
    local watchId = state.behavior.aimedAt
    if not watchId then
      for vehicleId in pairs(zoneOccupants(state, "slap_zone")) do
        watchId = vehicleId
        break
      end
    end
    local watched = watchId and exactVehicle(watchId) or nil
    if watched then
      -- FLUSH, never eat: if the previous flight is still being watched
      -- when this slap arms, score it where it is rather than dropping
      -- it. The unconditional overwrite lost the corridor flight every
      -- time a pad slap followed it.
      if state.behavior.watch then
        local previous = exactVehicle(state.behavior.watch.id)
        if previous then
          local prevOk, prevUp = pcall(function()
            return previous:getDirectionVectorUp()
          end)
          finalizeWatch(state, previous, prevOk and prevUp or nil)
        else
          state.behavior.watch = nil
        end
      end
      local origin = watched:getPosition()
      local up = watched:getDirectionVectorUp()
      state.behavior.watch = {
        id = watchId,
        x = origin.x, y = origin.y,
        lastUpX = up.x, lastUpY = up.y, lastUpZ = up.z,
        rolled = 0, settled = 0, elapsed = 0,
      }
    end
    -- Thresholded on the LADDER, not on the multiplier:
    -- power_multiplier_max came down 5.0 -> 2.6 and left this gated at
    -- >= 4.0, so maxing the console gave the same line as leaving it alone.
    if (state.behavior.powerLevel or B.default_power_level) >= B.power_levels - 1 then
      showMessage("HIGH FIVE! DON'T LEAVE ME HANGING!", 2.0)
    else
      showMessage("HIGH FIVE!", 1.8)
    end
  elseif state.behavior.aimedAt then
    -- Somebody was being aimed at and is not there any more. Announcing
    -- "the empty air" here reads as the mod telling the player it failed;
    -- this reads as the machine being annoyed, which is the joke.
    showMessage("Left hanging.", 1.6)
    emitEvent(state, "I", "high_five_whiffed", {dodged = true})
  else
    showMessage("The hand high-fives the empty air.", 1.6)
    emitEvent(state, "I", "high_five_whiffed", {dodged = false})
  end
end

-- ===========================================================================
-- Lifecycle
-- ===========================================================================
behavior.init = function(state)
  local b = state.behavior
  b.phase = "idle"
  b.elapsed = 0
  b.clock = 0
  b.blind = 0
  b.swingFrom = nil
  b.subjectId = nil
  b.watch = nil
  b.winceAt = nil
  b.slapSfxOffAt = nil
  b.faulted = not tunablesPresent(state)
  if b.faulted then return end
  b.powerLevel = b.powerLevel or B.default_power_level
  b.tiltIndex = b.tiltIndex or B.default_tilt_index
  poseMachine(state, REST_DEG, tiltDegrees(state), 0, 0)
  poseConsole(state)
end

behavior.reset = function(state)
  behavior.init(state)
  -- ALL the burst emitters: a reset landing inside the 0.3 s dust window
  -- stranded slap_dust2 and slap_grit emitting forever, because this list
  -- predated them.
  setEffectActive(state, "slap_dust", false)
  setEffectActive(state, "slap_dust2", false)
  setEffectActive(state, "slap_grit", false)
  setEffectActive(state, "slew_steam", false)
end

behavior.onPanelButton = function(state, buttonId)
  local b = state.behavior
  if b.faulted then return end
  if buttonId == "btn_power_up" then
    b.powerLevel = math.min(B.power_levels, (b.powerLevel or B.default_power_level) + 1)
  elseif buttonId == "btn_power_down" then
    b.powerLevel = math.max(1, (b.powerLevel or B.default_power_level) - 1)
  elseif buttonId == "btn_tilt_up" then
    b.tiltIndex = math.min(B.tilt_levels - 1, (b.tiltIndex or B.default_tilt_index) + 1)
  elseif buttonId == "btn_tilt_down" then
    b.tiltIndex = math.max(0, (b.tiltIndex or B.default_tilt_index) - 1)
  else
    return
  end
  poseConsole(state)
  -- The wrist follows the dial immediately while the hand is parked, so the
  -- setting is something you can SEE before you commit to driving at it.
  -- Mid-swing the pose loop owns the wrist and this would fight it.
  if b.phase == "idle" or b.phase == "cooldown" then
    poseMachine(state, REST_DEG, tiltDegrees(state), 0, b.clock)
  end
  local mult = powerMult(state)
  showMessage(
    string.format("Slap power %.1fx - wrist tilt %d deg", mult, tiltDegrees(state)), 1.6)
  emitEvent(state, "I", "high_five_console_set", {
    power_level = b.powerLevel,
    power_mult = math.floor(mult * 100) / 100,
    tilt_deg = tiltDegrees(state),
  })
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if b.faulted then return end
  if zone ~= "approach" then return end
  if b.phase == "idle" then
    b.phase = "alert"
    b.elapsed = 0
    b.subjectId = vehicle:getId()
    showMessage("The hand sees you coming.", 1.4)
    emitEvent(state, "I", "high_five_alerted", {subject_id = b.subjectId})
  elseif TRACKING_PHASES[b.phase] and not b.subjectId then
    -- ADOPT. Over 108 m of corridor a car drifting wide, overtaking or
    -- clipping the shoulder leaves the box routinely, and without this the
    -- machine kept its arm cocked at nobody, fired blind 3.2 s later and
    -- was already returning by the time the car actually arrived. Measured:
    -- zero launches for any subject that left and came back.
    b.subjectId = vehicle:getId()
    b.blind = 0
    emitEvent(state, "I", "high_five_reacquired", {subject_id = b.subjectId})
  end
end

-- onExit is handed a vehicle ID, not a vehicle object: lua_kit calls it from
-- removeSubjectEverywhere as well as from the trigger path, and by then the
-- object may already be gone.
behavior.onExit = function(state, zone, vehicleId)
  local b = state.behavior
  if zone ~= "approach" or b.subjectId ~= vehicleId then return end
  -- THE CORRIDOR IS AN ARMING TRIGGER, NOT THE TRACKING LEASH, and getting
  -- that backwards cost the mod every speed below 110 km/h.
  --
  -- The corridor's near edge is 16 m short of the strike plane so a player
  -- at the console is not standing in the trap. But the release fires when
  -- the subject is swing_lead_seconds away, i.e. 0.45*v metres out, and
  -- those two cross at v = 13.75/0.45 = 30.6 m/s. Below that the subject
  -- left the box BEFORE the lead could ever fire, so this handler dropped
  -- it, the blind timer ran its 3.2 s, and the hand slapped an empty mark
  -- while the car was 67 m down the road. Measured: whiff at 6, 8, 10, 12,
  -- 15, 18, 20, 25 and 30 m/s; hits only from 32 up.
  --
  -- So while the machine is tracking, an exit means nothing. Nothing is
  -- lost by holding on: timeToStrike already returns nil once the subject
  -- is past the plane or closing below min_closing_mps, and b.blind already
  -- covers the genuinely-gone case. With this one early return the band is
  -- 6-140 m/s and the console apron stays unarmed.
  if TRACKING_PHASES[b.phase] then return end
  b.subjectId = nil
end

-- Everything the offline gates need to see, and nothing they should have to
-- reach into state for. azimuth is reported so a test can measure where the
-- palm actually is at contact rather than trusting the phase name.
behavior.getStatus = function(state)
  local b = state.behavior
  return {
    phase = b.phase or "unknown",
    elapsed = b.elapsed or 0,
    power_level = b.powerLevel or B.default_power_level,
    power_mult = powerMult(state),
    tilt_index = b.tiltIndex or B.default_tilt_index,
    tilt_deg = tiltDegrees(state),
    subject_id = b.subjectId or -1,
    slapped = b.slapped and true or false,
    faulted = b.faulted and true or false,
    azimuth_deg = b.azimuthDeg or REST_DEG,
    blind = b.blind or 0,
  }
end

-- The thwack is CUED AT SWING ENTRY, not at contact. The clip carries a
-- 0.25 s whoosh before its impact (make_slap_audio.py IMPACT) and the
-- stroke takes 0.28 s, so cueing at the release puts the boom on the
-- contact frame; cued at contact it trailed the palm by a quarter second
-- and the car was ten metres gone when the boom arrived. A whiff still
-- swings, so a whiff still whooshes, which is what air sounds like.
local function cueSlapSound(state)
  pcall(function()
    local propObj = be:getObjectByID(state.propId)
    if propObj then
      propObj:queueLuaCommand(string.format(
        "if extensions.%s_vehicle and extensions.%s_vehicle.playSlap"
        .. " then extensions.%s_vehicle.playSlap() end",
        PROP_MODEL, PROP_MODEL, PROP_MODEL))
    end
  end)
  state.behavior.slapSfxOffAt = state.behavior.clock + 1.7
end

-- Score the watched flight NOW, wherever it is. One exit for every path
-- -- settle, timeout, and supersede -- because the version where only the
-- settle path scored silently ate the corridor flight whenever a pad slap
-- armed the next watch: 8 launches, 5 scores, in the very logs meant to
-- prove the feature.
finalizeWatch = function(state, flyer, up)
  local b = state.behavior
  local w = b.watch
  b.watch = nil
  -- A new scoreline claims the wince: if flight A earned a pending
  -- "pretends not to look" and flight B scores inside the 2.5 s window,
  -- the aside must not trail B's number as if it were about B.
  b.winceAt = nil
  if not w then return end
  local rest = flyer:getPosition()
  local dx, dy = rest.x - w.x, rest.y - w.y
  local metres = math.sqrt(dx * dx + dy * dy)
  local turns = w.rolled / (2 * math.pi)
  local attitude = "On its wheels."
  if up and up.z < -0.5 then
    attitude = "On the ROOF."
  elseif up and up.z < 0.6 then
    attitude = "On its side."
  end
  local turnsText
  if turns < 0.75 then
    turnsText = "No full rotation."
  elseif turns < 1.5 then
    turnsText = "One rotation."
  else
    turnsText = string.format("%d rotations.", math.floor(turns + 0.5))
  end
  showMessage(
    string.format("%d m. %s %s", math.floor(metres + 0.5),
      turnsText, attitude), 4.0)
  if attitude == "On the ROOF." then
    b.winceAt = b.clock + 2.5
  end
  emitEvent(state, "I", "high_five_scored", {
    subject_id = w.id,
    distance_m = math.floor(metres * 10 + 0.5) / 10,
    rotations = math.floor(turns * 100 + 0.5) / 100,
    attitude = attitude,
  })
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  if b.faulted then return end
  b.clock = b.clock + dtSim
  b.elapsed = b.elapsed + dtSim
  local tilt = tiltDegrees(state)

  -- The slap sound's queued stop, parked in the clip's silent tail.
  if b.slapSfxOffAt and b.clock >= b.slapSfxOffAt then
    b.slapSfxOffAt = nil
    pcall(function()
      local propObj = be:getObjectByID(state.propId)
      if propObj then
        propObj:queueLuaCommand(string.format(
          "if extensions.%s_vehicle and extensions.%s_vehicle.stopSlap"
          .. " then extensions.%s_vehicle.stopSlap() end",
          PROP_MODEL, PROP_MODEL, PROP_MODEL))
      end
    end)
  end

  -- THE SCOREBOARD. The machine watches what it launched until it stops
  -- moving, then says the number out loud while the palm is still held
  -- out. Runs in every phase: the flight outlasts the follow-through.
  if b.winceAt and b.clock >= b.winceAt then
    b.winceAt = nil
    -- The wince, DELAYED. Issued in the same tick as the scoreline it
    -- comments on, it replaced it -- showMessage shares one UI category
    -- and same-category messages overwrite, so "On the ROOF." died
    -- unread at the exact moment it was earned. 2.5 s later is also
    -- simply better comic timing: score, beat, aside.
    showMessage("The hand pretends not to look.", 2.4)
  end
  if b.watch then
    local w = b.watch
    w.elapsed = w.elapsed + dtSim
    local flyer = exactVehicle(w.id)
    if not flyer then
      b.watch = nil
    else
      local up = flyer:getDirectionVectorUp()
      -- Accumulated attitude change: the honest rotation count, measured
      -- off the car, not read back from the injected seed (the engine
      -- amplifies the tumble 30-90% after the palm leaves).
      -- YAW-BLIND, by choice: up-vector drift never sees rotation
      -- about the up axis, so a flat-spin helicopter scores "no full
      -- rotation" while doing 720. "Rotations" here means TUMBLES --
      -- the end-over-end that reads on camera -- and the injected axis
      -- is roll-dominant, but roughly half the yaw component goes
      -- uncounted. If the scoreboard ever under-sells obvious flat
      -- spins, this is why, and the fix is tracking the forward vector
      -- too.
      local dot = math.max(-1, math.min(1,
        up.x * w.lastUpX + up.y * w.lastUpY + up.z * w.lastUpZ))
      w.rolled = w.rolled + math.acos(dot)
      w.lastUpX, w.lastUpY, w.lastUpZ = up.x, up.y, up.z
      local speed = flyer:getVelocity():length()
      if speed < B.score_settle_mps then
        w.settled = w.settled + dtSim
      else
        w.settled = 0
      end
      -- A RECOVERED CAR IS NOT A LANDING. Pressing recover mid-flight
      -- teleports the subject; scoring the recovery point produced
      -- "3 m. 4 rotations." measured to the wrong place. A jump no slap
      -- can explain drops the watch silently.
      local here = flyer:getPosition()
      if w.prevX then
        local jump = math.sqrt(
          (here.x - w.prevX) ^ 2 + (here.y - w.prevY) ^ 2)
        if jump > 40.0 then
          b.watch = nil
        end
      end
      if b.watch then
        w.prevX, w.prevY = here.x, here.y
        if w.settled >= B.score_settle_seconds
            or w.elapsed >= B.score_timeout_seconds then
          finalizeWatch(state, flyer, up)
        end
      end
    end
  end

  -- RE-SCORE THE SUBJECT, every frame, in every tracking phase.
  --
  -- Latching first-come meant a 12 m/s car entering ahead of a 40 m/s one
  -- held the machine while the fast car drove through untouched, and it let
  -- stray AI traffic steal the slot from the player. Smallest time-to-strike
  -- wins, which is the only ordering that means anything to a machine whose
  -- whole job is to arrive when you do.
  --
  -- Above the phase branch, not inside `cocked`: during the 0.85 s windup a
  -- faster car could otherwise not take the aim, and the snap-swing path out
  -- of `windup` would then fire at the wrong one. `sortedKeys` rather than
  -- raw pairs() because two near-equal leads would otherwise thrash the
  -- selection, and this file argues elsewhere that unordered iteration is
  -- not acceptable.
  if TRACKING_PHASES[b.phase] then
    -- REACHABLE CANDIDATES WIN OUTRIGHT. A car in the escape lane may hold
    -- the aim only while there is nobody in the kill lane to hold it for.
    local current = exactVehicle(b.subjectId)
    local best, bestLead = b.subjectId, leadSeconds(state, b)
    local bestReach = current ~= nil and reachable(state, current)
    for _, vehicleId in ipairs(sortedKeys(zoneOccupants(state, "approach"))) do
      if vehicleId ~= b.subjectId then
        local other = exactVehicle(vehicleId)
        local lead = other and timeToStrike(state, other) or nil
        if lead then
          local reach = reachable(state, other)
          local better = (reach and not bestReach)
            or (reach == bestReach and (not bestLead or lead < bestLead))
          if better then
            best, bestLead, bestReach = vehicleId, lead, reach
          end
        end
      end
    end
    if best ~= b.subjectId then
      b.subjectId = best
      b.blind = 0
      emitEvent(state, "I", "high_five_retargeted", {subject_id = best})
    end
  end

  if b.phase == "idle" then
    poseMachine(state, REST_DEG, tilt, 0, b.clock)
    -- THE PAD IS A TRIGGER IN ITS OWN RIGHT, and this is a play-test fix.
    --
    -- Until now the ONLY way to arm the machine was the approach corridor,
    -- which runs y = -124 .. -16. The painted pad is y = -4.3 .. +4.3. So
    -- the one object in the scene that says "drive here" -- a hand stencilled
    -- on the road -- sat 11.7 m outside the only trigger that did anything,
    -- and `onEnter` opens with `if zone ~= "approach" then return end`. Drive
    -- onto the pad from the side, or from anywhere nearer than 16 m, and the
    -- hand simply watched.
    --
    -- The affordance and the mechanism have to be the same thing. A car in
    -- the strike zone is already AT the contact point, so there is nothing to
    -- lead and no reason to wait: swing from rest, now. The corridor still
    -- does what it always did for anyone arriving down the road at speed --
    -- that is the anticipation the machine is built on -- but arriving any
    -- other way is no longer silence.
    if zoneCount(state, "slap_zone") > 0 then
      local onPad = firstOccupant(state, "slap_zone")
      if onPad then
        -- SETUP, then punchline. The line and the swing used to land in
        -- the same tick, so the player read "You are standing ON it."
        -- while already airborne -- setup and punchline inside one 0.28 s
        -- beat. Half a second of the alert ripple first converts "random
        -- explosion" into "I watched it decide", and you still cannot
        -- escape: the swing needs 0.28 s and you are 0 m from the palm.
        b.subjectId = onPad:getId()
        b.aimedAt = b.subjectId
        b.phase = "pad_alert"
        b.elapsed = 0
        showMessage("You are standing ON it.", 1.2)
      end
    end

  elseif b.phase == "pad_alert" then
    poseMachine(state, REST_DEG, tilt, B.twitch_deg, b.clock)
    if b.elapsed >= B.pad_alert_seconds then
      b.swingFrom = REST_DEG
      b.phase = "slapping"
      b.elapsed = 0
      b.slapped = false
      emitEvent(state, "I", "high_five_pad_swing", {subject_id = b.subjectId})
      cueSlapSound(state)
    end

  elseif b.phase == "alert" then
    -- Parked, but the fingers have noticed. The ripple runs little -> index;
    -- the arm has not moved yet, which is the whole gag.
    poseMachine(state, REST_DEG, tilt, B.twitch_deg, b.clock)
    if b.elapsed >= B.alert_seconds then
      b.phase = "windup"
      b.elapsed = 0
      showMessage("It draws back...", 1.2)
      emitEvent(state, "I", "high_five_winding", {})
    end

  elseif b.phase == "windup" then
    local t = math.min(1, b.elapsed / B.windup_seconds)
    local smooth = t * t * (3 - 2 * t)
    local azimuth = REST_DEG + (WINDUP_DEG - REST_DEG) * smooth
    poseMachine(state, azimuth, tilt, B.twitch_deg * 0.6, b.clock)
    -- A subject arriving faster than the windup can finish gets swung at
    -- from WHEREVER THE ARM HAS GOT TO. Waiting for a full draw against a
    -- 60 m/s car is how you whiff at the only people committed enough to
    -- earn the slap, and a half-drawn arm snapping forward looks more
    -- alarmed than a tidy one, which is the right read.
    local lead = leadSeconds(state, b)
    if lead ~= nil and lead <= B.swing_lead_seconds + B.release_bias_seconds then
      b.phase = "slapping"
      b.aimedAt = b.subjectId
      b.swingFrom = azimuth
      b.elapsed = 0
      b.slapped = false
      emitEvent(state, "I", "high_five_snap_swing", {from_deg = azimuth})
      cueSlapSound(state)
    elseif t >= 1 then
      b.phase = "cocked"
      b.elapsed = 0
      b.blind = 0
      -- The flywheel is spooling. That IS what the duty cycle in the power
      -- ledger is for, and it gives the approach something to read.
      setEffectActive(state, "slew_steam", true)
    end

  elseif b.phase == "cocked" then
    -- Latching first-come meant a 12 m/s car entering ahead of a 40 m/s one
    -- held the machine while the fast car drove through untouched, and it
    -- also let stray AI traffic steal the slot from the player.
    -- Held at full draw, LEADING the subject. b.blind counts only the time
    -- with NO usable lead, so a slow car crossing 120 m of corridor is
    -- never preempted while a parked one still gets dealt with.
    local lead = leadSeconds(state, b)
    -- The fingers drum HARDER the closer you get. This is the longest beat
    -- in the show — up to 5 s at 25 m/s — and at a fixed amplitude it was
    -- also the deadest. The lead is already computed; spending it on the
    -- twitch costs nothing and is the only cue a driver gets that the
    -- machine is tracking them specifically.
    local urgency = 0.30
    if lead then urgency = math.max(0.30, math.min(1.0, 1.5 / math.max(lead, 0.2))) end
    poseMachine(state, WINDUP_DEG, tilt, B.twitch_deg * urgency, b.clock)
    local release = false
    if lead == nil then
      -- Nothing to wait FOR. Only this counts against the fallback.
      b.blind = (b.blind or 0) + dtSim
      release = b.blind >= B.max_hold_seconds
    else
      b.blind = 0
      -- Biased early: live, the palm lands ~0.11 s behind the maths
      -- (see release_bias_seconds).
      release = lead <= B.swing_lead_seconds + B.release_bias_seconds
    end
    if release then
      b.phase = "slapping"
      -- Latched at release. slapStrikeZone used to branch on the LIVE
      -- subjectId, which by contact time is routinely nil — so a clean pass
      -- at one car on an empty road printed "the hand high-fives the empty
      -- air", the mod telling the player nobody was there.
      b.aimedAt = b.subjectId
      b.swingFrom = WINDUP_DEG
      b.elapsed = 0
      b.slapped = false
      cueSlapSound(state)
      emitEvent(state, "I", "high_five_swinging", {
        tilt_deg = tilt,
        power_mult = math.floor(powerMult(state) * 100) / 100,
      })
    end

  elseif b.phase == "slapping" then
    -- t^1.5 ease-IN, which is not a feel curve: theta ~ t^1.5 is the
    -- CONSTANT-POWER trajectory (P = I a w = 1.125 I dtheta^2 / T^3, flat
    -- across the whole stroke) -- literally what an ideal flywheel dumping
    -- through a power-limited drive does. See the power ledger.
    local t = math.min(1, b.elapsed / B.slap_seconds)
    local from = b.swingFrom or WINDUP_DEG
    poseMachine(
      state, from + (CONTACT_DEG - from) * t ^ B.slap_ease, tilt, 0, b.clock)
    if not b.slapped and t >= 1 then
      b.slapped = true
      slapStrikeZone(state)
      b.phase = "follow"
      b.elapsed = 0
    end

  elseif b.phase == "follow" then
    local t = math.min(1, b.elapsed / B.follow_seconds)
    local smooth = 1 - (1 - t) * (1 - t)
    poseMachine(
      state, CONTACT_DEG + (FOLLOW_DEG - CONTACT_DEG) * smooth, tilt, 0, b.clock)
    -- The dust is an IMPACT, not weather: 0.3 s and gone. Left on through
    -- follow+hold it stood as a beige dome on the pad stencil in every
    -- after-shot of the mod.
    if b.elapsed >= 0.30 then
      setEffectActive(state, "slap_dust", false)
      setEffectActive(state, "slap_dust2", false)
      setEffectActive(state, "slap_grit", false)
    end
    if t >= 1 then
      b.phase = "holding"
      b.elapsed = 0
    end

  elseif b.phase == "holding" then
    -- Palm out, down-road, after the car it just launched.
    poseMachine(state, FOLLOW_DEG, tilt, 0, b.clock)
    if b.elapsed >= B.follow_hold_seconds then
      b.phase = "returning"
      b.elapsed = 0
      -- Belt-and-braces off; the follow window is the real owner now.
      setEffectActive(state, "slap_dust", false)
      setEffectActive(state, "slap_dust2", false)
      setEffectActive(state, "slap_grit", false)
    end

  elseif b.phase == "returning" then
    local t = math.min(1, b.elapsed / B.return_seconds)
    local smooth = t * t * (3 - 2 * t)
    poseMachine(
      state, FOLLOW_DEG + (REST_DEG - FOLLOW_DEG) * smooth, tilt, 0, b.clock)
    if t >= 1 then
      b.phase = "cooldown"
      b.elapsed = 0
      setEffectActive(state, "slew_steam", false)
    end

  elseif b.phase == "cooldown" then
    poseMachine(state, REST_DEG, tilt, 0, b.clock)
    if b.elapsed >= B.cooldown_seconds then
      b.phase = "idle"
      b.elapsed = 0
      b.subjectId = nil
      if zoneCount(state, "approach") > 0 then
        local waiting = firstOccupant(state, "approach")
        if waiting then
          b.phase = "alert"
          b.subjectId = waiting:getId()
          showMessage("The hand sees you coming. Again.", 1.4)
        end
      end
    end
  end
  poseConsole(state)
end
"""
