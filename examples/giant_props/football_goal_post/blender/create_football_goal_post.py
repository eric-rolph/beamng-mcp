"""Deterministic Blender generator for the Regulation Football Goal Post.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/football_goal_post/blender/create_football_goal_post.py

Geometry notes
--------------

The swan neck is the visual signature and gets real tube math: the
pedestal rises vertically to ``POST_TOP_Z``, then ONE cubic Bezier with
vertical tangents at both ends sweeps it forward 8 ft and up to the
crossbar (``neck_curve``), so it leaves the pedestal plumb and arrives
plumb with no tangent discontinuity anywhere. It is swept as a single
lofted tube, not a chain of elbow segments.

The crossbar passes through a transverse BORE in that pipe, just under
its square-cut end (ID-00010) — there is no sleeve and no flare. The
uprights land on WELDED FIXED END STUBS standing out of the crossbar's
crown (ID-00011 Detail View B); they do not pass through the bar.

Every tube carries metric UVs with the tile width equal to its own
circumference, so the painted-metal texture wraps each diameter exactly
once — no seam line mid-surface, constant texel density in meters.

Toolchain provenance — READ BEFORE TRUSTING ANY REBUILD
-------------------------------------------------------

Round 5 recorded that a rebuild was "not guaranteed to reproduce" the
shipped artifact. That was too soft. The correct statement is that it is
NOT CHECKABLE, and the reason is worth being exact about:

  * `examples/giant_props/proplib/` is entirely UNTRACKED in git — not
    ignored, untracked — so there is no revision of the shared library
    to name, diff, or roll back to.
  * On the serial-28 artifact, `prop_builder.py` (21:07) and
    `texture_kit.py` (21:08) both post-dated the 20:52 ZIP. The delta
    between the library that built the artifact and the library on disk
    is unknown, and unknowable after the fact.
  * The handoff pins the OUTPUT — a sha256 of the DAE — and carried no
    toolchain provenance at all: no generator hash, no proplib hash. An
    output hash tells you two artifacts differ. It cannot tell you why,
    and it cannot tell you what produced either one.

Those two modules are shared by all 18 mods in this pack, so the blast
radius of that unknown delta is the pack, not this example.

CONSEQUENCE, AND IT IS THE POINT OF WRITING THIS DOWN. Any build after
serial 28 is a FIRST build against an unknown-delta shared library while
also carrying two geometry fixes — the flag hem winding and the four
base gussets — so it inherits NONE of an earlier round's sign-off and
needs the full gate: this census, the pack test suite, and a live look
at the pedestal foot in game.

WHAT SERIAL 29 ACTUALLY DID, since it was built (2026-08-15 22:15) from
this source before that warning could be read. Its DAE was measured
directly, by importing the shipped file and running mesh_census over it:
85,372 triangles, 146 closed solids, 13,863 open sheets, and 0 inward-
facing solids, 0 folds, 0 same-direction half-edges. Both geometry fixes
are in it and neither is double-flipped. That closes the GEOMETRY half of
the gate and nothing else — the pack suite and the live look are still
owed, and it is worth knowing that `prop_builder.py` and
`texture_kit.py` were both modified again at 22:19:52, three and a half
minutes after that build was staged. The provenance gap is not a
historical footnote; it moved again while this note was being written.

`record_toolchain()` below now stamps generator, spec and per-module
proplib sha256s into the handoff, so the NEXT artifact is at least
checkable even though this one is not.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
EXAMPLE_ROOT = SCRIPT_PATH.parents[1]
PACK_ROOT = EXAMPLE_ROOT.parent
sys.path.insert(0, str(PACK_ROOT))
sys.path.insert(0, str(EXAMPLE_ROOT))

import spec  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"

# Tube circumferences: metric UV tile widths for seam-free wraps.
POST_WRAP = 2.0 * math.pi * spec.POST_RADIUS
BAR_WRAP = 2.0 * math.pi * spec.BAR_RADIUS
UPRIGHT_WRAP = 2.0 * math.pi * spec.UPRIGHT_RADIUS
# (No PAD_WRAP. The pole pad is not a plain tube — pad_shell() lofts a
# cinched-and-swollen profile and carries its own UVs — so a tube
# circumference was never going to be read here. Deleted round 4 by
# assert_no_dead_constants().)

# Tessellation. Auto-smooth fixes SHADING, never the SILHOUETTE — a
# 36-sided tube still shows a faceted outline against the sky, which is
# what reads as "low poly" on a prop made almost entirely of tubes
# (player report 2026-08-13). These are cheap: the whole post is a few
# thousand triangles either way.
TUBE_SEGMENTS = 64          # pedestal, crossbar, uprights, pole pad
FITTING_SEGMENTS = 48       # collars, sleeves, caps, end fittings
BOLT_SEGMENTS = 6           # hex heads and nuts
WASHER_SEGMENTS = 20        # round washers and serrated flanges
# Swan neck Bezier: vertical handles at both ends. The low handle governs
# how long the tube stays plumb off the pedestal, the high one how
# squarely it arrives under the crossbar.
NECK_SEGMENTS = 72
NECK_HANDLE_LOW = 1.05
NECK_HANDLE_HIGH = 0.78

# Crossbar tee (ID-00010). There is NO sleeve and no flare: the gooseneck
# runs at constant 6-5/8" pipe right to the top, where it is cut square and
# closed with a flat plate, and the crossbar passes through a transverse
# BORE in the pipe just under that cut. The proof is in the hardware — the
# 5/8" through-bolts are 8.000" long, and 8.000" is exactly the 6-5/8" pipe
# OD (6.625") plus a washer/lock-washer/nut stack. A bolt that long could
# not be spanning a 0.105 m sleeve; it is spanning the pipe itself.
NECK_CAP_Z = spec.CROSSBAR_TOP_Z + 0.022   # pipe end, just over the bore
NECK_CAP_T = 0.012
# The two 5/8 x 8 through-bolts sit either side of centre. 30 mm is as far
# out as they can go and still leave a stock 8.000" bolt with only ~20 mm of
# thread past the nut — spread them wider and they read as over-long.
TEE_BOLT_X = 0.030
TEE_CROWN_X = 0.050       # the two 3/8 serrated-flange bolts on the cap

# The crossbar runs past each upright by about one tube diameter and is
# closed with a flat capped end carrying the builder's mark (ID-00023).
BAR_OVERHANG = 0.135
BAR_HALF_LENGTH = spec.UPRIGHT_X + BAR_OVERHANG
BAR_CAP_T = 0.018
BAR_CAP_PROUD = 0.0035     # the cap rim stands off the tube, ID-00023

# --- Field build-up, dimensioned off the ID-00003 elevation ------------
# "Natural Grass Application": finish grade sits 9-5/8 in above the top of
# the concrete footing, and that subgrade is soil capped by the sod mat.
# Finish grade is set to the pole pad's bottom so the whole mounting kit
# is buried exactly as the drawing shows it.
GRADE_Z = 0.36                        # finish grade == pole pad bottom
SUBGRADE = 9.625 * 0.0254             # 9-5/8 in, per the drawing
FOOTING_TOP_Z = GRADE_Z - SUBGRADE    # top of the concrete footing
SOD_T = 0.055                         # sod mat: grass + root/thatch layer
SOD_Z0 = GRADE_Z - SOD_T
TURF_T = 0.008                        # turf skin thickness
SOIL_HALF = 1.1                       # the patch covers the old pad exactly
SOD_HALF = SOIL_HALF + 0.012          # laid sod overhangs its cut slightly
# Mown football turf stands 25-40 mm. The first pass used 85 mm with wide
# height scatter and rendered a hayfield — height and UNIFORMITY are what
# say "mown" more than any texture detail does.
GRASS_FRINGE = 0.038
GRASS_PANELS = 4        # blade-card atlas columns
GRASS_MOW_PITCH = 0.70  # metres per mow pass (3 bands across the patch)

SLAB_HALF = SOIL_HALF
SLAB_TOP_Z = FOOTING_TOP_Z

# Base hardware, dimensioned straight off the manufacturer's install
# sheets (Plate Mount Football Goal Posts, ID-00020 / ID-00015).
GROUND_PLATE = 16.0 * 0.0254          # 16 in square steel ground plate
GROUND_PLATE_T = 0.5 * 0.0254         # 1/2 in thick
BOLT_SQUARE = 14.0 * 0.0254           # 14 in anchor bolt square
# The gooseneck plate matches the ground plate: on a 14 in bolt square a
# 15 in plate leaves only 12.7 mm of edge distance and the 3/4 flat washers
# hang off the corners.
BASE_PLATE = 16.0 * 0.0254            # gooseneck base plate
BASE_PLATE_T = 0.75 * 0.0254
# 3/4-10 hardware, real sizes: hex nut 41/64" tall across 1-1/8" flats, USS
# flat washer 0.148" thick, helical lock washer 0.188" thick.
HEX_NUT_R = 0.0165                    # circumradius of a 1-1/8" A/F hex
HEX_NUT_H = 0.0163
FLAT_WASHER_R = 0.0235
FLAT_WASHER_T = 0.0038
LOCK_WASHER_R = 0.0160
LOCK_WASHER_T = 0.0048
GROUND_PLATE_TOP = SLAB_TOP_Z + GROUND_PLATE_T
# THE STANDOFF IS THE LEVELLING NUT. It is not a free 28 mm gap with a nut
# hovering in the middle of it (the old value left 8.5 mm of daylight under
# the nut and 2.5 mm over it — two floating faces on the same part).
BASE_PLATE_Z = GROUND_PLATE_TOP + HEX_NUT_H
BASE_PLATE_TOP = BASE_PLATE_Z + BASE_PLATE_T
# ID-00020 dimensions the anchor projection at 2-3/4" above the ground
# plate, and the whole stack has to live inside it: nut 16.3 + plate 19.1 +
# washer 3.8 + lock 4.8 + nut 16.3 = 60.3 mm, leaving 9.6 mm of thread
# proud. The old studs ran 134 mm past the last nut, which is what a bolt
# looks like when nobody has cut it.
ANCHOR_PROJECTION = 2.75 * 0.0254
ANCHOR_TOP_Z = GROUND_PLATE_TOP + ANCHOR_PROJECTION
ANCHOR_R = 0.0095                     # 3/4" stud
# ID-00015: the webs are big — each one runs from the pipe out to within a
# whisker of the plate's edge (half-width 0.203) and stands about 0.7 of a
# pipe diameter tall.
GUSSET_REACH = 0.185
GUSSET_RISE = 0.115
GUSSET_T = 0.010
LEVEL_BOLT_R = 0.155                  # levelling bolts inboard of the anchors
LEVEL_BOLT_HEAD_H = 0.0127            # 3/4-10 x 2" hex head
LEVEL_WASHER_R = 0.0187               # 3/4" SAE flat washer, 1-1/2" OD
LEVEL_WASHER_T = 0.0033
JAM_NUT_H = 0.0079                    # 3/4-10 jam nut: half a full nut

# Directional flags (GPDSTRGPT): 4 in x 42 in, hung from a spring hook
# just under the upright cap.
FLAG_HOOK_Z = 13.66
FLAG_LENGTH = 42.0 * 0.0254
FLAG_WIDTH = 4.0 * 0.0254
# The cloth hangs from the grommet in the flag's doubled HEM, which is
# clear of the tube on the field side — not from the tube's own centreline.
# The mount is a CHAIN and every link is derived from the one before it:
# tube -> weld pad -> bored tab -> snap hook -> grommet -> hem -> cloth.
#
# NAMED HEM, NOT HEADER (round 4). In flag trade terms a HEADER is the
# reinforced hoist band a grommet is set into, so it is a fair synonym for
# what this model builds — and that is exactly why it was a defect rather
# than a harmless one. The chain above listed `grommet -> header -> cloth`
# as two links when there is one; the geometry is carried by
# FLAG_HEM_REACH / FLAG_HEM_RUN / FLAG_HEM_T; a fourth constant
# FLAG_HEADER_H = 0.030 sat beside them holding exactly
# FLAG_HEM_REACH + FLAG_HEM_RUN and was read by nothing; and the shipped
# listing copy already says "pad, bored tab, hook, grommet, hem". Three
# names for one thing is what the round-3 lug/pad cleanup was about, so
# the same ruling applies: the reinforced band is the HEM, everywhere.
# The cloth anchor used to be its own independent pair of constants, so any
# tweak to the hardware silently desynced the flag from the hook it is
# supposed to hang on (player: "the attachment is off").
#
# ONE RING, NOT TWO (player, 2026-08-15: "let's remove the chain link
# circled in green from the flag attachments"). The welded anchor EYE that
# used to hang level with the lug is gone, and what carries the hook now is
# a single BORED FLAT TAB: one plate, one hole, hook threaded through it.
#
# THE TAB IS A CHOICE, NOT A FALLBACK, and the argument that used to say it
# was impossible was simply invalid. Its premises are sound — the hook's
# ring must stay in the Y-Z plane because flag_anchor's whole derivation
# depends on it, and the wire has to run along the bore's axis where it
# passes through — but those two only rule out a bore along X. What they
# actually do is CONSTRAIN the bore axis to lie in the Y-Z plane, and a
# Y-Z ring's tangent is purely +/-Y at the ring's top and bottom. A tab
# lying in the X-Z plane, bored along Y, is therefore threaded exactly at
# the ring's crown — which is also the one place a hook hanging in a hole
# actually bears.
#
# Both forms were then built and rendered side by side at the owner's
# viewing distance, because an argument is not evidence about how something
# looks. The clevis lost on the picture: a pad, two ears and a cross pin
# make a blob with about as much mass as the two rings it replaced, and at
# a metre the ring reads as fused into it. This joint is where the owner
# asked for LESS. The tab is one 10 mm x 5 mm flat bar with a 7 mm hole in
# its eye, and the ring hangs THROUGH that hole.
#
# BE HONEST ABOUT WHAT READS AT A METRE. At the owner's distance a pixel is
# about 1.1 mm, and the seating crescent between the wire and the top of
# the bore is ~1.4 mm — one pixel, a single lit dot. What actually carries
# the "threaded, not glued" read at that range is the RING'S OWN APERTURE,
# 24.8 mm of clear air inside a 35 mm circle, with the tab's shank crossing
# it. The bore only becomes daylight in the macro shots. A claim about a
# 1.4 mm feature has to state the range it is true at.
# NAMED PAD, NOT LUG (round 3). These constants were FLAG_LUG_* while the
# comment beside them said "This is the mount's PAD" and the prose two
# functions away said "welded pad" — three names for one box. A lug is a
# projecting piece you put a hole through, which on this mount is the TAB;
# what is welded flat to the tube is a doubler PAD. One name, everywhere.
FLAG_PAD_Y = spec.UPRIGHT_RADIUS + 0.008
FLAG_PAD_SIZE = (0.018, 0.026, 0.016)
FLAG_PAD_FACE_Y = FLAG_PAD_Y + FLAG_PAD_SIZE[1] / 2.0   # outer face of the pad
FLAG_HOOK_R = 0.015
FLAG_WIRE_R = 0.0026                  # 3/16 in spring-hook wire, as drawn
FLAG_TAB_T = 0.005                    # 3/16 in flat bar...
FLAG_TAB_W = 0.010                    # ...3/8 in wide in the shank
FLAG_TAB_EYE_R = 0.0055               # upset eye: 1.6 x the bore, which is
FLAG_TAB_BORE_R = 0.0035              # the edge distance a bored eye is cut to
# BROKEN ARRIS on the plate's outline and on both mouths of the bore. This
# is a 45-degree chamfer cut into the mesh AFTER the booleans, by
# break_arris() — never a Bevel modifier left pending across a boolean.
# See break_arris' docstring for the bug that made this constant a lie for
# one round: the modifier survived, evaluated after the EXACT boolean, and
# clamped to ZERO WIDTH against the boolean's 0.23 nm artifact edges,
# shipping 514 zero-area triangles per tab and no chamfer at all.
FLAG_TAB_BEVEL = 0.0006
# A polygonal cutter INSCRIBES the circle it is asked for, so a 24-gon at
# the nominal radius leaves a hole whose flats are 0.03 mm INSIDE nominal —
# and 0.03 mm is the whole clearance a wire resting on a bore's floor has.
# Circumscribe instead and the hole is never tighter than it was drawn.
#
# THE EYE IS DELIBERATELY LEFT INSCRIBED, and the asymmetry is the point,
# not an oversight (round-4 audit). A radius earns the circumscribing
# correction when something has to FIT in it: the bore carries a wire and
# 0.03 mm is a third of its whole seating clearance. The eye carries
# nothing — it is silhouette — so its 28-gon flats sitting at 5.465 mm
# against a declared 5.5 mm cost 0.035 mm of edge distance on a part whose
# edge distance is 2.0 mm, and correcting it would only move a line nobody
# measures. Care spent where nothing fits is care that stops meaning
# anything where something does.
FLAG_BORE_SEGMENTS = 24
FLAG_BORE_CUT_R = FLAG_TAB_BORE_R / math.cos(math.pi / FLAG_BORE_SEGMENTS)
# The tab is welded flat to the pad's outer face, so the plane the bore's
# axis has to lie in — the tab's MID-plane — is half a plate thickness
# proud of that face. The ring is centred on the same plane, and that is
# what makes the bore's Y axis the wire's OWN tangent rather than merely
# something near it.
FLAG_TAB_Y = FLAG_PAD_FACE_Y + FLAG_TAB_T / 2.0
FLAG_HOOK_Y = FLAG_TAB_Y
# The ring swings in front of the weld pad, so it is the pad's BOTTOM EDGE
# that fixes how far down the ring hangs: clear that by FLAG_HOOK_CLEAR and
# the whole 35 mm circle turns in free air instead of grazing steel. A 1 mm
# miss there is the difference between hardware that hangs and hardware
# that looks glued on, and at the range this is actually looked at you can
# see which one it is. (In Y the ring clears the tube by 5.9 mm, because
# the pad and the tab together stand it 23.5 mm off the tube's axis face.)
FLAG_HOOK_CLEAR = 0.0035
FLAG_HOOK_CZ = (FLAG_HOOK_Z - FLAG_PAD_SIZE[2] / 2.0 - FLAG_HOOK_CLEAR
                - (FLAG_HOOK_R + FLAG_WIRE_R))
# (FLAG_LINK_DROP is gone with the chain that needed it. It used to be the
# CAUSE — the interlock spacing two rings had to be set apart by — and the
# hook's height was derived from it. Under a bored tab the drop is a
# CONSEQUENCE of where the pad's bottom edge is, so a constant holding it
# would have been written and never read, which is the same defect as the
# FLAG_EAR_REACH this round deleted. What couples the cloth to the
# hardware is FLAG_HOOK_CZ, and flag_anchor reads that directly.)
# Where the hole is centred, and the one derivation on this mount that is
# genuinely easy to get wrong twice.
#
# A wire hanging in a hole does NOT bed on the floor at the hole's MIDDLE:
# it curves away from the bore's axis, so it rides on the two mouths and
# stands clear in between. And the part of the wire that gets there first
# is not its centreline but the ring's INNER surface, radius (R - r): that
# is the point of the whole torus that reaches furthest from the bore's
# axis once you are half a plate thickness along it. Deriving the height
# from the centreline instead — sqrt(R^2 - (t/2)^2) + bore - wire — puts
# the hole 0.045 mm high and the wire that far into its own floor.
#
# FLAG_BORE_SEAT is the one deliberate slop on this joint. A 32-faceted
# wire in a 24-faceted hole cannot be tangent to better than its own facet
# error, so a bore placed for exact tangency MEASURES as a 0.03 mm
# interference and "tangent to the micron" becomes a claim nobody can
# check — which is exactly how the previous version of this mount went
# wrong. Two tenths of a millimetre of seating clearance is what a 5.2 mm
# wire hanging in a 7.0 mm hole really has, it is a third of a pixel at
# the range this is looked at, and it measures as contact.
#
# AND THE BEARING LINE IS THE CHAMFER'S EDGE, NOT THE PLATE'S FACE. Once
# both mouths are chamfered by FLAG_TAB_BEVEL the cylindrical wall only
# survives over |dy| <= t/2 - bevel, so that — not t/2 — is where the wire
# first meets metal. Deriving from t/2 with a chamfered mouth is not
# dangerous (the wire ends up 0.108 mm LOOSER, never tighter) but it makes
# FLAG_BORE_SEAT a number that no longer measures: the minimum gap would
# read 0.31 mm against a declared 0.20. The half-width below restores the
# constant to something a ruler can confirm.
FLAG_BORE_SEAT = 0.0002
FLAG_BORE_Z = (FLAG_HOOK_CZ
               + math.sqrt((FLAG_HOOK_R - FLAG_WIRE_R) ** 2
                           - (FLAG_TAB_T / 2.0 - FLAG_TAB_BEVEL) ** 2)
               + FLAG_TAB_BORE_R - FLAG_BORE_SEAT)
# Doubled leading hem, carried by the CLOTH mesh: how far it stands ahead
# of the grommet, how far back it lies over the flag, and its thickness.
# (FLAG_HEADER_H = 0.030 stood here until round 4. It was written once and
# read never — the third time this file has grown a constant that holds a
# quantity some other constant already owns, after FLAG_EAR_REACH and the
# FLAG_LINK_DROP that was argued away above. REACH + RUN is that same
# 0.030 to the millimetre. assert_no_dead_constants() at the foot of this
# file now fails the build on the fourth.)
FLAG_HEM_REACH = 0.011
FLAG_HEM_RUN = 0.019
FLAG_HEM_T = 0.005
FLAG_DROOP = {"l": 34.0, "r": 30.0}   # rest-pose hang angle per side


def flag_anchor(side):
    """Where the cloth hangs from — the exact point on the snap hook's wire
    that the flag's grommet is threaded onto.

    The last link of the chain was still missing (player, 2026-08-14:
    "let's connect the ring to a grommet in flag"): the cloth was dropped a
    hook radius plus half a hem BELOW the hook, so the ring finished in
    mid-air above the hem and nothing actually held the flag up.

    The right point is not the bottom of the ring — a wire tangent there
    runs ALONG the cloth and would lie across the grommet instead of
    through it. Take the point of the circle furthest downstream measured
    in the flag's own direction ``L``: there the wire's tangent,
    ``(0, -sin phi, cos phi)`` at ``phi = L``, is exactly the cloth's
    normal, so the hook pierces the grommet dead square and the whole rest
    of the ring stands clear, upstream of the hem. Threading angle is
    ``cos(phi - L)``, which is 1 here and 0 at the bottom of the ring.
    """

    xc = -spec.UPRIGHT_X if side == "l" else spec.UPRIGHT_X
    lean = -math.radians(FLAG_DROOP[side])
    return (
        xc,
        FLAG_HOOK_Y + FLAG_HOOK_R * math.cos(lean),
        FLAG_HOOK_CZ + FLAG_HOOK_R * math.sin(lean),
    )
# Cloth simulation grid. 10 x 3 over a 1.07 m x 0.10 m ribbon puts a node
# every ~12 cm along the stream, which is enough for the fold-and-snap
# read without paying for a full curtain.
FLAG_ROWS = 10
FLAG_COLS = 3
FLAG_DRAG_COEF = 10.0   # stock utv_flags value; jbeam scales it by 0.01

# --- Upright to crossbar (ID-00011 Detail View B, ID-00023) ------------
# The uprights do NOT pass through the crossbar. A WELDED FIXED END STUB
# stands out of the crossbar's crown and the upright slips over it, so what
# you actually see at the joint is a band of bare galvanised stub between
# the upright's square-cut bottom edge and the bar's curved surface: nearly
# closed at the sides, ~30 mm open front and back. That crescent is the
# single most recognisable feature of a real goal post joint, and modelling
# the upright as a tube shoved through the bar throws it away.
STUB_RADIUS = spec.UPRIGHT_RADIUS - 0.003   # upright slips OVER the stub
UPRIGHT_BASE_Z = spec.CROSSBAR_TOP_Z + 0.006
STUB_BOLT_X = (-0.082, 0.068)   # 3/8 crown bolts: inboard, then outboard
# (both clear the 0.0568 outer edge of the saddle weld by ~1 mm, so the
# serrated flanges land on bar metal rather than half on the bead)
STUB_TIE_Z = (0.075, 0.195)     # 1/4-20 bolts up the upright, +Y face
UPRIGHT_SPLICE_Z = 8.385        # two-piece 35 ft upright, joined mid-run

# The pad starts above the whole mounting kit (gusset webs top out at
# 0.335) so the install hardware reads instead of being swallowed.
PAD_BOTTOM_Z = GRADE_Z
# NFHS/NCAA both require the post to be padded to 6 ft. The old pad stopped
# at 1.45 m (4 ft 9 in) — a short sock on a tall post — and left the top
# 0.36 m of the authored collision prism (which runs to z 1.95) with no
# visual at all, so a car "hit" the pad where there was nothing to see.
# spec.PAD_TOP_Z has always declared 1.93; nothing was reading it.
PAD_TOP_Z = spec.PAD_TOP_Z
# (No PAD_HEIGHT. The pad's extent is the pair of z levels above, both of
# which are read; the difference between them was written and never asked
# for. Deleted round 4 by assert_no_dead_constants().)
# Pole pad shell: cinched at the straps, swollen between them. PAD_RADIUS
# stays the OUTER (bulge) radius so the authored collision prism is still
# the right size.
PAD_STRAP_R = spec.PAD_RADIUS - 0.026   # shell radius under a strap
PAD_BULGE = 0.026                       # free-span swell over that
PAD_CINCH_WIDTH = 0.13                  # how far the cinch reaches
PAD_EDGE_ROLL = 0.10                    # rolled hem at the open bottom
PAD_THROAT = 0.075                      # length of the cinched-down top
PAD_STRAP_W = 0.075                     # webbing width
PAD_STRAP_Z = (0.56, 0.94, 1.32, 1.70)
# Side-release buckle sized off that webbing: the shell runs a little wider
# than the strap it swallows, the way every 3 in buckle does.
BUCKLE_W = 0.092
BUCKLE_T = 0.020
PAD_TILE = 0.62                          # vinyl texture tile, metres


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def flag_surface(side: str):
    """Rest-shape sampler for one flag: ``(s, w) -> world point``.

    s runs 0..1 from the spring hook to the free tail, w runs -0.5..0.5
    across the 4 in width. The SAME sampler feeds the render mesh and the
    soft-body cage grid, so the flexbody's rest pose sits exactly on its
    nodes — author them separately and the skinned mesh spawns distorted.

    The rest pose is deliberately a light-air hang, not a full-stream
    banner: the cloth physics does the streaming once the wind reaches
    it, and a heavily pre-shaped rest pose would fight the solver.
    """

    from mathutils import Matrix, Vector

    xc = -spec.UPRIGHT_X if side == "l" else spec.UPRIGHT_X
    wave_phase, twist_phase = (0.0, 1.1) if side == "l" else (2.3, 3.4)
    droop = FLAG_DROOP[side]
    # Start ON the hook's wire, NOT the tube centreline and not a nominal
    # drop below the hardware: the flag hangs from its grommet and the
    # grommet is threaded on the hook (see flag_anchor).
    anchor = Vector(flag_anchor(side))

    # Integrate the centreline once at fine resolution, then sample it.
    steps = 96
    ds = 1.0 / steps
    points = [anchor.copy()]
    tangents = []
    point = anchor.copy()
    for i in range(steps + 1):
        s = i * ds
        # Streams -Y, away from the tube it hangs on, so the rest pose
        # never lies back across the upright.
        yaw = math.radians(90.0 + 15.0 * math.sin(2 * math.pi * 1.1 * s + wave_phase) * s)
        # s**1.6: sag accelerates toward the tail instead of reading as
        # one constant-slope stick.
        pitch = -math.radians(droop + 26.0 * s**1.6)
        tangent = Vector(
            (
                math.cos(pitch) * math.cos(yaw),
                math.cos(pitch) * math.sin(yaw),
                math.sin(pitch),
            )
        ).normalized()
        tangents.append(tangent)
        if i:
            point = point + tangents[i - 1] * (FLAG_LENGTH * ds)
            points.append(point.copy())

    def sample(s: float, w: float) -> Vector:
        s = min(max(s, 0.0), 1.0)
        index = min(int(s * steps), steps)
        centre = points[index]
        tangent = tangents[index]
        across = tangent.cross(Vector((0.0, 0.0, 1.0)))
        if across.length < 1e-6:
            across = Vector((0.0, 1.0, 0.0))
        across.normalize()
        normal = across.cross(tangent).normalized()
        # Gentle twist only: past ~30 deg the strip turns edge-on
        # mid-span and the flag pinches into a taffy twist.
        twist = math.radians(22.0 * math.sin(2 * math.pi * 0.8 * s + twist_phase) * s)
        spin = Matrix.Rotation(twist, 4, tangent)
        across = (spin @ across).normalized()
        normal = (spin @ normal).normalized()
        bow = 0.3 * (w * w - 0.25) * FLAG_WIDTH
        return centre + across * (w * FLAG_WIDTH) + normal * bow

    return sample


def flag_mesh(name, material, side, *, segments=30, ribs=4):
    """Render mesh for one flag, skinned at runtime to its cloth nodes.

    Zero thickness on purpose: at 4 in wide real flag cloth has no
    silhouette, and the palette entry carries ``double_sided`` plus
    ``invertBackFaceNormals`` so the back face lights correctly.

    The doubled leading HEM is part of this mesh, not a box parked beside
    it. It used to be an axis-aligned slab in the static visual flexbody,
    so while the flag streamed and folded the hem hung in the air dead
    still — a stiff shelf on the end of a moving ribbon (player,
    2026-08-15: "let's have the grommet attachment area cloth like so it
    moves with the cloth its attached to"). Built into the flag mesh it is
    skinned to the same cloth nodes and deforms with them.
    """

    import bpy
    from mathutils import Vector

    sample = flag_surface(side)
    stride = ribs + 1
    vertices = []
    uvs = []
    # The ribbon STARTS where the hem ends. Running it from s=0 put the
    # zero-thickness sheet straight through the middle of the 5 mm hem
    # band, and the two surfaces cut each other into a torn-looking star at
    # the corner. Cloth is not two things in the same place.
    hem_s = FLAG_HEM_RUN / FLAG_LENGTH
    for i in range(segments + 1):
        s = hem_s + (1.0 - hem_s) * i / segments
        for j in range(stride):
            vertices.append(tuple(sample(s, j / ribs - 0.5)))
            # u across the width, v along the length: the satin floats and
            # drape creases stretch down the flag like real long-float silk.
            uvs.append((j / ribs, s))

    faces = []
    for i in range(segments):
        for j in range(ribs):
            a = i * stride + j
            faces.append((a, a + 1, a + stride + 1, a + stride))

    # --- doubled leading hem -------------------------------------------
    # Reaches UPSTREAM of the cloth's own leading edge, because the hem is
    # folded and sewn before the grommet is set: the hole needs cloth all
    # round it. sample() clamps at s=0, so upstream stations are
    # extrapolated along the tangent there.
    # THE QUANTISED-SAMPLER TRAP. flag_surface integrates its centreline at
    # 96 steps and sample() indexes with int(s * steps), so s is quantised
    # to 11.1 mm along the flag. Any finite difference shorter than about
    # two steps returns the SAME point and the difference collapses to
    # zero — which is what happened with a 4 mm probe: the leading
    # extrapolation fell back to a hardcoded -Y and shot the hem sideways
    # into the tube, and every surface normal degenerated to +Z. Probe
    # coarse (45 mm ~ four steps) and the derivatives are real.
    probe = 0.045

    def hem_point(distance, w):
        if distance >= 0.0:
            return sample(distance / FLAG_LENGTH, w)
        root = sample(0.0, w)
        step = sample(probe / FLAG_LENGTH, w)
        back = root - step
        if back.length < 1e-9:
            back = Vector((0.0, -1.0, 0.0))
        return root + back.normalized() * (-distance)

    stations = [-FLAG_HEM_REACH + (FLAG_HEM_REACH + FLAG_HEM_RUN) * k / 4.0
                for k in range(5)]
    normals = []
    for distance in stations:
        centre = hem_point(distance, 0.0)
        along = hem_point(distance + probe, 0.0) - centre
        across = hem_point(distance, 0.12) - hem_point(distance, -0.12)
        normal = along.cross(across)
        normals.append(normal.normalized() if normal.length > 1e-9
                       else Vector((0.0, 0.0, 1.0)))

    hem_base = len(vertices)
    for face_index, lift in enumerate((0.5, -0.5)):
        for station_index, distance in enumerate(stations):
            for j in range(stride):
                w = j / ribs - 0.5
                point = (hem_point(distance, w)
                         + normals[station_index] * (lift * FLAG_HEM_T))
                vertices.append(tuple(point))
                uvs.append((j / ribs, 0.004 * (station_index + face_index)))
    sheet = len(stations) * stride
    # WINDING (round 5). Six groups of quads are wound by hand here, and
    # until round 5 two of them disagreed with the other four: the two
    # SHEETS and the two END caps enclosed the band the wrong way round,
    # so the 16 side-strip triangles were the only ones facing out and the
    # solid measured a NEGATIVE 11.2 cm^3. Measured on the shipped DAE by
    # flood-filling a consistent orientation: 16 of 96 triangles carried
    # the minority winding, 221.2786 mm^2 on the left flag and 221.1050 on
    # the right, and 20 half-edges were traversed twice in the same
    # direction. Flipping the sheets and the ends (the sides were already
    # right) takes both flags to 0 minority triangles, 0 same-direction
    # half-edges and +11.21 / +11.25 cm^3 — which is the hem's own volume,
    # 101.60 mm x 22.11 mm x 5.00 mm = 11.23 cm^3, so the sign is now the
    # outward one and not merely a consistent one.
    #
    # NOTHING VISIBLE HUNG ON THIS, and that is the point: the palette
    # entry ships `doubleSided` + `invertBackFaceNormals`, so no face was
    # ever culled and back faces already lit correctly. It was invisible
    # BY DECLARATION, not by luck or by distance — but a closed band whose
    # normals point into its own interior is a lie about the geometry, and
    # the mesh census below now reports it instead of nobody looking.
    for face_index, wind in enumerate((True, False)):
        base = hem_base + face_index * sheet
        for i in range(len(stations) - 1):
            for j in range(ribs):
                a = base + i * stride + j
                quad = (a, a + 1, a + stride + 1, a + stride)
                faces.append(tuple(reversed(quad)) if wind else quad)
    # Close the fold: the two edges down each side, plus the front and back
    # ends, so the hem is a solid band rather than two loose sheets.
    top, bottom = hem_base, hem_base + sheet
    for i in range(len(stations) - 1):
        for j in (0, ribs):
            a, b = top + i * stride + j, top + (i + 1) * stride + j
            c, d = bottom + (i + 1) * stride + j, bottom + i * stride + j
            faces.append((a, b, c, d) if j == ribs else (d, c, b, a))
    for station_index, wind in ((0, False), (len(stations) - 1, True)):
        for j in range(ribs):
            a = top + station_index * stride + j
            b = bottom + station_index * stride + j
            quad = (a, a + 1, b + 1, b)
            faces.append(tuple(reversed(quad)) if wind else quad)

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    layer = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for loop_index in poly.loop_indices:
            layer.data[loop_index].uv = uvs[mesh.loops[loop_index].vertex_index]

    bk.assign_material(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def weld_solids(target, others):
    """Boolean-UNION `others` into `target`, then delete them.

    The mirror of ``bk.cut_openings``, and needed for the same reason: two
    primitives that merely OVERLAP leave surfaces buried inside the metal
    where they cross, and where those surfaces graze coplanar they shimmer
    at each other under any camera move. A shank and its eye have to
    become ONE solid before a hole is cut through them, or the hole is cut
    through a seam.

    THIS IS NOT THE SAME CONSTRUCTION AS THE TAB SITTING ON THE PAD, which
    the mount's measurements report as `TAB..PAD 0.0000 mm` and call a
    required weld membrane (round-4 audit: "the code refuses elsewhere
    exactly what it allows here"). It refuses OVERLAP; the tab and the pad
    do not overlap at all, they TOUCH, on one plane, back to back with
    opposed normals — which is the same Z-FIGHT LAW build_visual() states
    for the footing and the subgrade: stacked layers never overlap, they
    only ever touch. Under backface culling exactly one of a back-to-back
    pair is ever drawn from any viewpoint, so there is nothing to fight,
    and the two cases are told apart by a measurement rather than by which
    docstring you read: V_solid puts TAB INTERSECT PAD at 42 vertices in a
    bounding box 0.00000 mm thick — a membrane enclosing no volume —
    against HOOK INTERSECT GATE, a real solid 4.18 mm thick and
    111.795 mm^3 of genuinely shared steel.

    IT ALSO MOVES EACH BOOLEAN TO THE FRONT OF THE STACK BEFORE APPLYING
    IT, which ``bk.cut_openings`` does not — see PROPLIB BUG in
    break_arris() below. `modifier_apply` on a modifier that is not first
    applies it to the BASE mesh and silently leaves everything ahead of it
    pending, so a primitive built with a bevel goes through the boolean
    unbevelled and then gets bevelled again at export, against boolean
    edges. The `assert` is the cheap half of the fix: no target of a weld
    may carry a pending deforming modifier at all.
    """

    import bpy

    pending = [m.type for m in target.modifiers if m.type not in ("NODES",)]
    assert not pending, (
        f"{target.name} has pending modifiers {pending} at weld time; "
        "apply or defer them or the boolean will be applied out of order"
    )
    for other in others:
        modifier = target.modifiers.new("Weld", "BOOLEAN")
        modifier.operation = "UNION"
        modifier.solver = "EXACT"
        modifier.object = other
    bpy.context.view_layer.objects.active = target
    for modifier in [m for m in target.modifiers if m.type == "BOOLEAN"]:
        target.modifiers.move(list(target.modifiers).index(modifier), 0)
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    for other in others:
        mesh = other.data
        bpy.data.objects.remove(other, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return target


def planar_folds(mesh, *, faces=None, tol=1e-10, rel=0.0):
    """Every coplanar patch of `mesh` whose triangles do NOT tile once.

    THE ONE TEST THAT SEES A ZERO-THICKNESS SHEET. A folded planar patch —
    a face ear-clipped onto itself, an inverted triangle, a capped hole —
    is invisible to every integral invariant this generator had been
    using: it encloses no volume, adds no handle, leaves every edge
    bordering exactly two faces, and its triangles have real area. Round
    2 shipped a capped bore under those checks; round 3 shipped 46 mm^2 of
    folded membrane under thirty-eight of them. Both were the same defect
    class and neither was visible to `len(edge.link_faces) == 2`, which is
    structurally incapable of seeing a fold.

    What it cannot hide from is that inside ONE planar patch of ONE solid,

        sum |area|  -  |sum area|  =  2 x (area of the doubled sheet)

    because the reversed sheet subtracts from the vector sum while adding
    to the scalar one. Grouping is per patch and per solid on purpose: two
    DIFFERENT solids may legitimately share a plane with opposing normals
    (the tab's back face lies flat on the pad's front face — that is the
    weld), and that is contact, not a fold. Pass `faces` to restrict the
    scan to ONE solid inside a joined mesh; mesh_census() below hands it
    one connected component at a time for exactly that reason.

    THREE THINGS THIS CANNOT SEE, recorded so the next round does not have
    to rediscover them:

    1. A SAME-WINDING DOUBLE COVER. Two layers wound the same way add to
       the vector sum and the scalar sum alike, so sum|area| == |sum area|
       and D is zero by construction. It is the WORSE defect of the two —
       a reversed layer is backface-culled from outside, a same-winding
       one draws from the same side as the surface it duplicates and
       z-fights in the open. Catching it needs a coplanar-overlap test
       (2D SAT or polygon clipping), not an area invariant. Found in the
       wild 2026-08-15 in another mod in this pack: 0.0834 m^2 of it on
       spin_cycle_washer's front panel, invisible to both this and the
       round-4 method.
    2. NEARLY-coplanar folds. The plane key rounds the unit normal to 4 dp
       and the offset to a 2 um lattice, so a fold that opens by more than
       that lands in two buckets and reads as zero. Conversely, pooling
       triangles that are NOT coplanar makes D positive automatically —
       which is why a tolerance sweep on this invariant is not a free
       robustness check but a false-positive generator.
    3. WINDING CONSISTENCY. D is blind to a closed solid whose normals all
       point inward, and to a patch flipped relative to its neighbours.
       mesh_census() counts same-direction half-edges for that.

    `tol` IS AN ABSOLUTE FLOOR AND DOES NOT SCALE; `rel` IS A RELATIVE ONE
    AND DOES. Blender stores vertices in float32, so D carries a rounding
    residue proportional to the patch's own area and to how far from the
    origin it sits. On a 25 mm booleaned tab that residue is far under the
    1e-10 m^2 floor, which is why break_arris has always been able to use
    the absolute test alone. Over the whole model it is not: measured on
    the shipped serial 28, 3052 patches carry D > 1e-12 m^2 and the worst
    reaches 0.0152 mm^2 — every one of them float32 noise, and every one
    of them under 2.3e-7 of its own patch area, which is float32 epsilon.
    Round 3's real fold was 46.356 mm^2 on ~340 mm^2 of plate: a RATIO of
    1.4e-1, six orders of magnitude clear. So a whole-model scan tests the
    ratio (mesh_census uses rel=1e-5, 44x over the measured noise and
    13000x under the real defect) and break_arris keeps rel=0.

    Returns a list of (normal, offset, triangle count, doubled area).
    """

    from mathutils import Vector

    buckets: dict = {}
    for face in (mesh.faces if faces is None else faces):
        loops = face.loops[:]
        if len(loops) != 3:
            raise AssertionError("planar_folds wants a triangulated mesh")
        a, b, c = (loop.vert.co for loop in loops)
        vec = (b - a).cross(c - a) * 0.5
        if vec.length <= 1e-14:
            continue
        unit = vec.normalized()
        lead = next(i for i in range(3) if abs(unit[i]) > 1e-9)
        canon = unit if unit[lead] > 0.0 else -unit
        key = (round(canon.x, 4), round(canon.y, 4), round(canon.z, 4),
               round(canon.dot(a) / 2e-6))
        buckets.setdefault(key, []).append(vec)
    out = []
    for key, vecs in sorted(buckets.items()):
        total = Vector((0.0, 0.0, 0.0))
        for vec in vecs:
            total += vec
        scalar = sum(vec.length for vec in vecs)
        doubled = scalar - total.length
        if doubled > tol and doubled > rel * scalar:
            out.append((key[:3], key[3], len(vecs), doubled))
    return out


def _connected_faces(mesh):
    """Split a bmesh into vertex-connected components: one solid each."""

    mesh.verts.index_update()
    parent = list(range(len(mesh.verts)))

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for face in mesh.faces:
        indices = [loop.vert.index for loop in face.loops]
        root = find(indices[0])
        for other in indices[1:]:
            merge = find(other)
            if merge != root:
                parent[merge] = root
    groups: dict = {}
    for face in mesh.faces:
        groups.setdefault(find(face.loops[0].vert.index), []).append(face)
    return list(groups.values())


def mesh_census(mesh_groups):
    """Fold + winding census over EVERY exported mesh group. Round 5.

    WHY THIS EXISTS: `planar_folds` was only ever asserted inside
    `break_arris`, which is called on ONE object in this whole generator —
    the flag tab. Round 4 then reported "folded sheet: 0" as a fact about
    THE MODEL. It was a fact about the tab. The flag hem, a hand-wound
    96-triangle band in a different function, had carried 16 minority-
    winding triangles since it was written, and no check in the file was
    pointed at it. Three rounds running, the thing that shipped was outside
    the scope of the check that cleared it, so the check now walks
    everything that gets exported.

    Runs on the EVALUATED mesh, the same way `export_multi_flexbody` does,
    so a modifier still pending at export time — the proplib bevel bug in
    `break_arris`' docstring — is measured as it will actually ship rather
    than as the source object looks.

    TWO BUCKETS, because the invariant means different things in each:

      CLOSED  every edge borders two faces. D = sum|area| - |sum area| is
              a fold, full stop, and the signed volume has a right sign.
      OPEN    at least one boundary edge — a sheet. The flag ribbon and
              every grass blade live here. A sheet has no inside, so
              volume is meaningless and a "fold" may be a legitimate
              double-back of cloth. Reported SEPARATELY and never pooled
              into the closed number, rather than dropped, which is what
              round 4 effectively did by never looking.

    REPORTS the fold number and the whole OPEN bucket, and ASSERTS on one
    thing: an inward-facing CLOSED solid. The split is not squeamishness,
    it is what each number means. A fold on a sheet may be legitimate
    cloth doubling back; a fold measured through a pending modifier on
    14k grass blades is a number whose tolerance nobody has earned. Those
    stay reporting, prefixed WARNING, because a build-breaking assert on a
    bucket whose semantics vary by component is a worse failure mode than
    a loud line of output.

    `inv` in the CLOSED bucket has none of that ambiguity. The component
    is closed and manifold, so it encloses a volume; that volume has a
    right sign and a wrong one; the wrong one is a mis-wound solid, full
    stop, with no legitimate reading. It is 0 model-wide once the flag hem
    and the four base gussets are fixed. And it is exactly the defect that
    rode 28 builds undetected while every other check in this file passed
    it. In a generator whose signature failure mode is "a warning that
    fires every build is how a real one gets skipped past", the one
    counter that CAN be a hard gate has no business being a print
    statement — so it is an assert.
    """

    import bmesh
    import bpy

    depsgraph = bpy.context.evaluated_depsgraph_get()
    grand = {"fold": 0.0, "flips": 0, "inverted": 0}
    inward = []                 # every mis-wound closed solid, for the assert
    for group_name in sorted(mesh_groups):
        tally = {
            "closed": {"n": 0, "tris": 0, "fold": 0.0, "flips": 0, "inv": 0},
            "open": {"n": 0, "tris": 0, "fold": 0.0, "flips": 0, "inv": 0},
        }
        flagged = []
        for source in sorted(mesh_groups[group_name], key=lambda o: o.name):
            evaluated = source.evaluated_get(depsgraph)
            data = bpy.data.meshes.new_from_object(
                evaluated, preserve_all_data_layers=False, depsgraph=depsgraph
            )
            if data is None:          # an object that evaluates to no mesh
                continue
            mesh = bmesh.new()
            mesh.from_mesh(data)
            bmesh.ops.triangulate(mesh, faces=mesh.faces[:],
                                  quad_method="BEAUTY", ngon_method="BEAUTY")
            for component in _connected_faces(mesh):
                edges = {edge for face in component for edge in face.edges}
                boundary = sum(1 for edge in edges
                               if len(edge.link_faces) == 1)
                seen: dict = {}
                volume = 0.0
                # ABOUT THE COMPONENT'S OWN ORIGIN, not the model's. The
                # divergence-theorem sum a.(b x c)/6 over ABSOLUTE positions
                # cancels catastrophically for a small solid far from the
                # origin: each of the flag grommet's 384 terms is ~0.5 m^3
                # and they sum to 7e-7 m^3, a million-to-one cancellation,
                # which in float32 leaves ~1000 mm^3 of noise on a 728 mm^3
                # part — enough to invert its SIGN. Measured: the grommet
                # reads +728.4335 mm^3 in float64 and -226.8577 in float32,
                # and the census called it inside-out. Translating to a
                # local origin is exact (a closed surface encloses the same
                # volume wherever it sits) and removes the amplification.
                origin = component[0].loops[0].vert.co.copy()
                for face in component:
                    verts = [loop.vert for loop in face.loops]
                    for index in range(3):
                        pair = (verts[index].index,
                                verts[(index + 1) % 3].index)
                        seen[pair] = seen.get(pair, 0) + 1
                    a, b, c = (vert.co - origin for vert in verts)
                    volume += a.dot(b.cross(c)) / 6.0
                flips = sum(1 for count in seen.values() if count > 1)
                folds = planar_folds(mesh, faces=component, rel=1e-5)
                doubled = sum(item[3] for item in folds)
                inverted = int(not boundary and volume < 0.0)
                slot = tally["open" if boundary else "closed"]
                slot["n"] += 1
                slot["tris"] += len(component)
                slot["fold"] += doubled
                slot["flips"] += flips
                slot["inv"] += inverted
                if inverted:
                    inward.append((group_name, source.name, len(component),
                                   volume))
                if doubled > 1e-12 or flips or inverted:
                    flagged.append((source.name, len(component), boundary,
                                    doubled, flips, inverted, volume))
            mesh.free()
            bpy.data.meshes.remove(data)
        total_tris = tally["closed"]["tris"] + tally["open"]["tris"]
        print(f"    census {group_name}: {total_tris} triangles, "
              f"{tally['closed']['n']} closed solids, "
              f"{tally['open']['n']} open sheets")
        for kind in ("closed", "open"):
            slot = tally[kind]
            mark = ("WARNING " if slot["fold"] > 1e-12 or slot["flips"]
                    or slot["inv"] else "")
            print(f"      {mark}{kind:6s}: {slot['tris']:6d} tris, "
                  f"fold D = {slot['fold'] * 1e6:.4f} mm^2 "
                  f"(sheet {slot['fold'] * 5e5:.4f} mm^2), "
                  f"{slot['flips']} same-direction half-edges, "
                  f"{slot['inv']} inward-facing solids")
            grand["fold"] += slot["fold"]
            grand["flips"] += slot["flips"]
            grand["inverted"] += slot["inv"]
        for name, tris, boundary, doubled, flips, inverted, volume in flagged:
            print(f"      WARNING   {name}: {tris} tris, "
                  f"{'OPEN' if boundary else 'CLOSED'}, "
                  f"fold D = {doubled * 1e6:.4f} mm^2, "
                  f"{flips} same-direction half-edges, "
                  f"volume {volume * 1e9:.4f} mm^3"
                  f"{' INWARD' if inverted else ''}")
    print(f"    census total: fold D = {grand['fold'] * 1e6:.4f} mm^2, "
          f"{grand['flips']} same-direction half-edges, "
          f"{grand['inverted']} inward-facing solids")
    if inward:
        detail = "; ".join(
            f"{group}/{name}: {tris} tris, {volume * 1e9:.4f} mm^3"
            for group, name, tris, volume in inward
        )
        raise AssertionError(
            f"{len(inward)} closed solid(s) wound inside out — {detail}. "
            "A closed component with negative enclosed volume is mis-wound, "
            "and the material is not doubleSided, so it ships mis-lit. Fix "
            "the face winding; do not relax this check."
        )
    return grand


def declutter_arris(mesh, arris, width):
    """Dissolve every vertex that sits in a plate FACE closer to an arris
    than the chamfer is wide, and keep going until none is left.

    THIS IS THE WHOLE OF ROUND 3's BUG, AND IT IS A DISTANCE PROBLEM, NOT
    A TESSELLATION ONE. Measured on the shipped tab, the two biggest
    reversed triangles were:

        before the bevel   (-5.000, 2.191) (-5.000, 20.946) (-4.955, 2.386)
        after  the bevel   (-4.400, 2.157) (-4.400, 20.946) (-4.955, 2.386)

    — the SAME three-cornered face, with the two corners that sat on the
    arris moved 0.6 mm inboard and straight past the third, which sits
    0.045 mm inside the arris and does not move. The face turns inside
    out. `ngon_method` never sees it and the trailing triangulate merely
    inherits it, so blaming the ear-clipper was wrong.

    The offenders are all stale points the EXACT boolean leaves behind and
    that carry no shape at all: 28-gon vertices of the eye that fall just
    inside the shank's side plane (r = 5.5 mm at 25.71 deg lands at
    x = 4.955 against a shank half-width of 5.000), and the shank's own
    side plane where it crosses the eye disc. Dissolving them changes the
    solid's volume by nothing measurable — 1093.2683 mm^3 before and
    after, to four decimals — and takes the two plate faces from
    192.353 / 193.782 mm^2 (which is 170 mm^2 of face plus a doubled
    sheet) to 169.895 / 169.895, equal to each other and to the vector
    sum. It is a mesh repair, not a design change.

    ITERATED, because dissolving re-triangulates and a vertex that was
    safe against its old neighbour can become the near one: pass 0 clears
    11 vertices here, pass 1 clears the last, pass 2 confirms none.
    """

    import bmesh

    def crowded(edges):
        on_arris = {vert for edge in edges for vert in edge.verts}
        near = set()
        for edge in edges:
            head, tail = (vert.co for vert in edge.verts)
            span = tail - head
            for face in edge.link_faces:
                if abs(face.normal.y) < 1.0 - 1e-3:
                    continue                       # a wall, not a plate face
                for vert in face.verts:
                    if vert in on_arris:
                        continue
                    param = max(0.0, min(1.0, (vert.co - head).dot(span)
                                         / span.length_squared))
                    if (vert.co - (head + span * param)).length < width:
                        near.add(vert)
        return near

    cleared = 0
    for _ in range(8):
        mesh.normal_update()
        victims = crowded(arris(mesh))
        if not victims:
            return cleared
        mesh.verts.index_update()
        bmesh.ops.dissolve_verts(
            mesh, verts=sorted(victims, key=lambda vert: vert.index))
        bmesh.ops.triangulate(mesh, faces=mesh.faces[:],
                              quad_method="BEAUTY", ngon_method="BEAUTY")
        cleared += len(victims)
    raise AssertionError("declutter_arris did not converge in 8 passes")


def break_arris(target, width, *, scrub=1e-5):
    """Chamfer the plate arrises of a BOOLEANED solid, into the mesh data.

    PROPLIB BUG THIS EXISTS TO ROUTE AROUND (filed in AGENTS.md, round 3).
    ``bk._finish_primitive`` adds a BEVEL modifier and leaves it pending;
    ``bk.cut_openings`` then appends a BOOLEAN and calls `modifier_apply`
    on the boolean alone. Blender applies a not-first modifier to the base
    mesh and keeps the earlier ones pending, so the bevel survives, is
    evaluated at EXPORT time against the boolean's output, and — because
    the EXACT solver leaves 0.23 nm artifact edges behind — clamps to zero
    width. What ships is full bevel TOPOLOGY at zero AREA: measured on the
    round-2 tab, 514 degenerate triangles per side, 0.0% oblique surface,
    and a knife-sharp arris where a 0.6 mm chamfer was declared. The tab
    was the only bevelled box in this model that goes through a boolean,
    which is why nothing had tripped it before. NOT fixed in proplib: three
    other shipped mods boolean a bevelled box and a stack-order fix there
    would silently re-cut their geometry.

    So: build the primitive with bevel=0.0, boolean it, and call this.

    Four things make it come out right rather than merely present, and
    every one of them was found by measuring, not by reasoning.

    1. TRIANGULATE BEFORE THE BEVEL, OR THE BEVEL EATS THE HOLE. A bmesh
       face cannot have a hole, so Blender's boolean hands back the plate's
       pierced face as ONE n-gon with a zero-width KEYHOLE slit joining the
       outline to the bore rim. That n-gon tessellates correctly on its
       own — but bevel it and the slit is re-formed wrongly: the FIRST
       version of this function shipped a tab whose back face carried two
       triangles spanning the bore (face area 249 mm^2 against the front
       face's 174) and three valence-4 edges. The hole was capped. Nothing
       that measures VERTICES can see that, and neither can a boolean
       intersection test, because a cap encloses no volume. What sees it is
       edge valence and the plate's own volume. Triangulated first, the
       keyhole is gone before anything touches it: edge valence {2: 627},
       volume 1093.268 mm^3 against an analytic 1095.737 (-0.23%, which is
       the 24-gon-versus-circle and the two reflex corners).
    2. SCRUB, BUT ONLY TO EPSILON. The EXACT boolean leaves nine 0.23 nm
       edges here, and the trailing triangulate turns them into exported
       slivers: with the scrub off, 8 exactly-zero-area triangles, 22 more
       arris edges than the plate has, and chamfer tilts running out to
       55.6 degrees. It is deliberately NOT larger: 0.12 mm also passes
       every zero-area and hole test but leaves a valence-0 wire edge
       behind and pulls the two faces 10 mm^2 out of symmetry, which is a
       worse artifact than the one it fixes.
       (ROUND 3 GAVE THIS PARAGRAPH THE WRONG JOB, and round 4 measured
       it. It said the 0.23 nm edges were what made clamp_overlap flatten
       the chamfer to 0.64% oblique. They are not: that run was ALREADY
       scrubbed, so the edges were gone and clamp still collapsed. What
       clamp was clamping against is item 4 below. With item 4 in place,
       clamp_overlap=True and clamp_overlap=False now produce the same
       394 triangles, the same 1093.2683 mm^3 and the same 18.473%
       oblique, so it is left ON as the cheap belt to item 4's braces.)
    3. BEVEL THE ARRIS SET, NOT THE MESH. Only edges where a plate FACE
       meets an in-plane WALL are arrises — the plate's outline and the
       bore's two mouths. The union seam between shank and eye is wall-to-
       wall and the eye's outline on the face is face-to-face; both carry
       the boolean's remaining short edges, and neither is an arris. Naming
       the set instead of an angle threshold means the chamfer is a
       constant 0.6 mm at a constant 45 degrees everywhere it exists,
       instead of a width that varies with local topology.
    4. DECLUTTER THE FACES FIRST, OR THE BEVEL TURNS THEM INSIDE OUT. An
       offset cannot be run past geometry that is nearer than the offset.
       The boolean leaves stale points 0.022 to 0.497 mm inside an arris
       that is about to move 0.600 mm, and the triangles hanging off them
       invert — 46.4 mm^2 of folded, zero-thickness membrane across the
       two tabs, which shipped for a whole round because it passes every
       volume, genus, valence and zero-area test there is. See
       declutter_arris' docstring for the two coordinate triples that
       settle what actually happened, and planar_folds' for why nothing
       else could see it.

    The trailing triangulate is not tidiness. Blender's Collada exporter
    triangulates whatever n-gons it is given, with its own ear-clipper, and
    writes AT MOST 7 SIGNIFICANT FIGURES PER COMPONENT, INDEPENDENTLY —
    near z = 13.65 m a 10 um grid, and out at x = 2.87 m a 1 um one. Three
    seam vertices 45/59/104 um apart tessellated into a sliver that had
    real area in Blender and quantised onto one line in the DAE: an exactly
    zero-area triangle that NO in-Blender assertion could see. Hand the
    exporter triangles and what ships is what was measured here.

    (NOT `%.7g`, which this docstring claimed until round 5 and the shipped
    file disproves: it holds `2.03919e-4`, where C's %g would emit
    `0.000203919` — different notation threshold, single-digit exponent,
    and a shortest-round-trip digit count rather than a fixed one. A census
    of 602k numeric tokens in the shipped DAE tops out at 7 significant
    figures, so the GRID above is right even though the format string was
    not. AND THE COROLLARY THAT MATTERS FOR NORMALS: because each component
    is written to its own relative precision, a small component of a unit
    vector — `-1 2.9177e-6 5.95832e-5` occurs in this file — is stored to
    around 1e-12 absolute while the leading one is stored to 1e-7. Scoring
    a normal by its worst PER-COMPONENT relative change is therefore
    meaningless: a 2e-7 nudge really is millions of last-places of a 3e-6
    component, and the score says nothing about the surface. A unit
    vector's error measure is the ANGLE between it and the reference. Use
    that.)

    THE TWO ASSERTS AT THE END ARE NOT THE SAME ASSERT. Edge valence sees
    a hole and a gap; it is structurally blind to a fold, because a folded
    sheet leaves every edge bordering exactly two faces. Only the second
    one has ever caught anything on the first try.
    """

    import bmesh

    def arris_of(mesh):
        mesh.normal_update()
        return [
            edge for edge in mesh.edges
            if len(edge.link_faces) == 2
            and min(abs(f.normal.y) for f in edge.link_faces) < 1e-3
            and max(abs(f.normal.y) for f in edge.link_faces) > 1.0 - 1e-3
        ]

    mesh = bmesh.new()
    mesh.from_mesh(target.data)
    bmesh.ops.remove_doubles(mesh, verts=mesh.verts, dist=scrub)
    bmesh.ops.triangulate(mesh, faces=mesh.faces[:], quad_method="BEAUTY",
                          ngon_method="BEAUTY")
    cleared = declutter_arris(mesh, arris_of, width)
    arris = arris_of(mesh)
    bmesh.ops.bevel(
        mesh, geom=arris, offset=width, offset_type="OFFSET", segments=1,
        profile=0.5, affect="EDGES", clamp_overlap=True,
    )
    bmesh.ops.triangulate(mesh, faces=mesh.faces[:], quad_method="BEAUTY",
                          ngon_method="BEAUTY")
    for edge in mesh.edges:
        assert len(edge.link_faces) == 2, (
            f"{target.name} is not a closed manifold after break_arris: "
            f"an edge borders {len(edge.link_faces)} faces"
        )
    folds = planar_folds(mesh)
    assert not folds, (
        f"{target.name} carries a folded zero-thickness membrane after "
        "break_arris: "
        + "; ".join(f"plane n={n} offset {d} — {k} triangles, "
                    f"{a * 1e6:.4f} mm^2 doubled" for n, d, k, a in folds)
    )
    print(f"    break_arris {target.name}: {len(arris)} arris edges, "
          f"{cleared} crowding vertices dissolved, no planar fold")
    mesh.to_mesh(target.data)
    mesh.free()
    target.data.update()
    return target


def flag_attachment(name, side, xc, material):
    """The RIGID half of the flag mount, ID-00011 step 1: a welded pad on
    the tube, a bored flat tab standing off it, and a 3/16 in 304 SS spring
    hook (PURCHP-0097) threaded through the tab's hole.

    ONE ring, on purpose (player, 2026-08-15). The anchor eye that used to
    sit between the pad and the hook is gone; see the FLAG_TAB_* block for
    why what replaced it is a bored tab and not a clevis pin.

    Everything here is metal hanging off the tube, so it belongs in the
    static visual mesh. The cloth half — the doubled hem — is built in
    flag_mesh(), and the brass eyelet in flag_grommet(); both ride the
    flag's own flexbody so they move with the cloth.

    The first build hung the flag off the tube CENTRELINE with a 5 mm
    hook, so the cloth spawned inside the upright and the hardware was
    invisible — the player's "they should have proper attachments". Every
    piece here sits clear of the tube and reads at close range.
    """

    objects = []
    # Welded PAD on the +Y face, biting into the tube so it reads as welded
    # rather than parked alongside. Everything else on the mount is
    # measured off this pad's outer face. (It was named "lug" here and
    # FLAG_LUG_* above while the prose called it a pad; round 3 settled on
    # PAD. The lug on this mount is the tab.)
    #
    # It keeps a plain bevel= because it goes through no boolean: its
    # pending Bevel modifier is evaluated at export against its own eight
    # box edges and comes out at full width. That is the CONTROL that made
    # the tab's missing chamfer measurable — same material, same export,
    # 21.3% oblique surface area against the tab's 0.0%.
    objects.append(
        bk.add_box(
            f"{name}_weld_pad",
            (xc, FLAG_PAD_Y, FLAG_HOOK_Z),
            FLAG_PAD_SIZE,
            material,
            bevel=0.0025,
        )
    )
    # The tab: ONE flat bar welded to the pad's outer face over the pad's
    # whole height, reaching down past its bottom edge to a bored eye. The
    # eye is upset wider than the shank because a hole needs edge distance
    # and a bar does not, and because a shank that runs out to a wider
    # rounded eye is the silhouette that says "this was cut to a drawing".
    # Shank and eye are welded into a single solid BEFORE the bore is cut,
    # so the hole is cut through metal rather than through a seam.
    tab_top_z = FLAG_HOOK_Z + FLAG_PAD_SIZE[2] / 2.0
    # bevel=0.0 ON PURPOSE: a pending Bevel modifier does not survive a
    # boolean intact, it survives it BROKEN. The chamfer is cut after both
    # booleans by break_arris(), whose docstring holds the whole bug.
    tab = bk.add_box(
        f"{name}_tab",
        (xc, FLAG_TAB_Y, (FLAG_BORE_Z + tab_top_z) / 2.0),
        (FLAG_TAB_W, FLAG_TAB_T, tab_top_z - FLAG_BORE_Z),
        material,
        bevel=0.0,
    )
    weld_solids(tab, [
        bk.add_cylinder(
            f"{name}_tab_eye",
            (xc, FLAG_TAB_Y, FLAG_BORE_Z),
            FLAG_TAB_EYE_R,
            FLAG_TAB_T,
            material,
            vertices=28,
            axis="Y",
        ),
    ])
    bk.cut_openings(tab, [
        bk.add_cylinder(
            f"{name}_tab_bore",
            (xc, FLAG_TAB_Y, FLAG_BORE_Z),
            FLAG_BORE_CUT_R,
            FLAG_TAB_T * 4.0,
            None,
            vertices=FLAG_BORE_SEGMENTS,
            axis="Y",
        ),
    ])
    break_arris(tab, FLAG_TAB_BEVEL)
    objects.append(tab)
    # Snap hook: plane Y-Z (axis X). Its crown runs along Y, which is the
    # bore's axis, so the wire threads the hole square instead of crossing
    # it — that is the whole reason the tab lies in X-Z. It hangs PLUMB
    # under the hole with its wire bedded on the bore's floor at both
    # mouths (FLAG_BORE_Z), so the ring is carried by metal at a visible
    # contact instead of hovering next to it.
    hook_y = FLAG_HOOK_Y
    hook_z = FLAG_HOOK_CZ
    objects.append(
        bk.add_torus(
            f"{name}_hook",
            (xc, hook_y, hook_z),
            FLAG_HOOK_R,
            FLAG_WIRE_R,
            material,
            rotation=(0.0, math.pi / 2.0, 0.0),
            major_segments=32,
            minor_segments=10,
        )
    )
    # Sprung gate across the hook's throat, on the outboard side — away
    # from the tab, which is where you would open it to unclip the hook.
    objects.append(
        bk.add_cylinder(
            f"{name}_hook_gate",
            (xc, hook_y + FLAG_HOOK_R * 0.72, hook_z),
            0.0022,
            FLAG_HOOK_R * 1.35,
            material,
            vertices=10,
            axis="Z",
        )
    )
    # NOTHING SOFT IS BUILT HERE. The doubled hem lives in flag_mesh() and
    # the brass eyelet in flag_grommet(), both of which go into the flag's
    # own flexbody so they deform with the cloth. What stays in this list is
    # only what is genuinely welded to the tube: the pad, the bored tab,
    # and the snap hook with its gate. The dividing line is not
    # metal-vs-fabric — the grommet is metal — it is whether the part's
    # position is owned by the structure or by the cloth.
    return objects


def flag_grommet(name, side, xc, material):
    """The brass eyelet, built as part of the CLOTH rather than the tube.

    A grommet is swaged through the hem: it is the one metal part on this
    prop whose position is owned by the fabric, not by the structure. Left
    in the static visual mesh it stayed nailed to one point in space while
    the hem it is crimped into swung away from it (player, 2026-08-15:
    "let's make the metal grommet attached to the grommet fabric area so it
    flows with the cloth"). Returned separately so main() can put it in the
    flag's mesh group, where the flexbody skins it to the same cloth nodes
    as the hem.

    The hook still passes through the bore, and the cloth's leading row is
    held to the upright tip, so this barely travels — but it travels WITH
    the cloth, which is the difference between crimped and glued-on.
    """

    from mathutils import Vector

    sample = flag_surface(side)
    root = sample(0.0, 0.0)
    ahead = sample(0.03, 0.0)
    lean = math.atan2(ahead[2] - root[2], ahead[1] - root[1])
    normal = Vector((0.0, -math.sin(lean), math.cos(lean)))

    objects = []
    for rim_index, lift in ((0, 0.0034), (1, -0.0034)):
        seat = root + normal * lift
        objects.append(
            bk.add_torus(
                f"{name}_rim_{rim_index}",
                (xc, seat[1], seat[2]),
                0.0072,
                0.0024,
                material,
                rotation=(lean, 0.0, 0.0),
                major_segments=24,
                minor_segments=8,
            )
        )
    barrel = bk.add_cylinder(
        f"{name}_barrel",
        (xc, root[1], root[2]),
        # Just inside the rims' 4.8 mm throat, so the barrel lines the hole
        # instead of bursting through it. Clear bore 4.6 mm against the
        # hook's 2.6 mm wire.
        0.0046,
        0.0090,
        material,
        vertices=24,
        axis="Z",
    )
    barrel.rotation_euler = (lean, 0.0, 0.0)
    objects.append(barrel)
    return objects


def grass_field(materials) -> list:
    """Dense turf: one mesh of jittered crossed blade cards over the mat.

    The first attempt failed for three reasons the player saw instantly —
    the cards sat on a REGULAR grid (which the eye reads as corduroy no
    matter how good the blade texture is), they were far too sparse to
    hide the flat plane underneath, and each one was its own Blender
    object, which caps how many you can afford. This builds every card
    into a single mesh, so density is nearly free, and places them on a
    jittered-cell scatter with per-card yaw, height and width.
    """

    import bpy

    blade = materials[f"{MOD_ID}_grass_blades"]
    rng = _fringe_rng()
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    uvs: list[tuple[float, float]] = []
    face_lean: list[float] = []

    def emit(cx, cy, cz, width, height, yaw, panel, flip, lean):
        half = width / 2.0
        dx, dy = math.cos(yaw) * half, math.sin(yaw) * half
        # Mow stripes are not paint — they are blades physically LAID OVER
        # in alternating directions. Tilting the card tops is what makes
        # the stripe survive into the geometry instead of hiding under it.
        # WORLD-frame lay. This was originally rotated by the card's own
        # yaw, which is random per card, so every card leaned a different
        # way and the stripe cancelled itself out. A mow band is exactly
        # one thing: every blade in it laid the SAME world direction.
        lx, ly = lean, 0.0
        face_lean.append(lean)
        base_index = len(vertices)
        vertices.extend(
            [
                (cx - dx, cy - dy, cz),
                (cx + dx, cy + dy, cz),
                (cx + dx + lx, cy + dy + ly, cz + height),
                (cx - dx + lx, cy - dy + ly, cz + height),
            ]
        )
        faces.append((base_index, base_index + 1, base_index + 2, base_index + 3))
        # Atlas column, optionally mirrored: 4 panels x flip = 8 distinct
        # looks, which kills the repeated-motif tell at grazing angles.
        u0 = panel / GRASS_PANELS
        u1 = (panel + 1) / GRASS_PANELS
        if flip:
            u0, u1 = u1, u0
        uvs.extend([(u0, 0.0), (u1, 0.0), (u1, 1.0), (u0, 1.0)])

    # Jittered-cell scatter across the mat, plus a skirt that drapes over
    # the sod cut so the edge is fringed rather than razor-cut.
    cells = 52
    reach = SOD_HALF + 0.02
    step = 2.0 * reach / cells
    for ix in range(cells):
        for iy in range(cells):
            # Real turf grows from crowns, so density is patchy at the
            # 100-300 mm scale. A perfectly even scatter is a dead CG
            # giveaway even when every other cue is right.
            cell_x = -reach + (ix + 0.5) * step
            cell_y = spec.POST_Y - reach + (iy + 0.5) * step
            cell_dy = cell_y - spec.POST_Y
            clump = 0.5 + 0.28 * math.sin(1.7 * cell_x + 2.3 * cell_dy + 0.4)
            clump += 0.16 * math.sin(4.1 * cell_x - 3.3 * cell_dy + 1.9)
            clump += 0.09 * math.sin(8.3 * cell_x + 7.1 * cell_dy)
            count = 2 if clump < 0.45 else (3 if clump < 0.8 else 4)
            for _ in range(count):
                px = -reach + (ix + rng()) * step
                py = spec.POST_Y - reach + (iy + rng()) * step
                # Skip the pad footprint: no grass growing through vinyl.
                if math.hypot(px, py - spec.POST_Y) < spec.PAD_RADIUS + 0.02:
                    continue
                # Tight height scatter: a mower cuts one plane, so the
                # variation is millimetres, not a factor of three.
                height = GRASS_FRINGE * (0.88 + rng() * 0.24)
                width = 0.052 + rng() * 0.030
                yaw = rng() * math.pi
                # Roots undulate on a low-frequency swell — a real field is
                # never a mathematical plane — and the skirt outside the
                # sod line drops so it drapes over the cut face.
                dy = py - spec.POST_Y
                cz = (
                    GRADE_Z
                    - 0.009
                    + 0.011 * math.sin(0.9 * px + 1.31 * dy + 0.7)
                    + 0.007 * math.sin(2.7 * px - 1.9 * dy + 2.2)
                    + 0.004 * math.sin(5.9 * px + 4.3 * dy)
                )
                overhang = max(
                    abs(px) - SOD_HALF, abs(py - spec.POST_Y) - SOD_HALF, 0.0
                )
                cz -= min(overhang * 1.4, 0.03)
                # Mow bands. A mower makes a HARD edge between passes, so
                # this is a square wave, not a sinusoid: a sine ramp gives
                # a gradual transition that reads as shading variation
                # rather than stripes. `max(sin, 0)` was worse still — it
                # flattened one whole half to upright, leaving a single
                # soft boundary instead of alternating passes.
                laid = int(math.floor((py - spec.POST_Y) / GRASS_MOW_PITCH)) % 2 == 0
                # 1.07 (a ~47 deg lay) splays the cards into flat
                # rosettes; 0.55 reads as laid-over grass while the
                # normal tilt below carries most of the stripe's contrast.
                lean = height * (0.55 if laid else 0.10)
                panel = int(rng() * GRASS_PANELS) % GRASS_PANELS
                flip = rng() < 0.5
                emit(px, py, cz, width, height, yaw, panel, flip, lean)
                emit(
                    px,
                    py,
                    cz,
                    width * 0.85,
                    height * 0.92,
                    yaw + math.pi / 2.0,
                    int(rng() * GRASS_PANELS) % GRASS_PANELS,
                    rng() < 0.5,
                    lean,
                )

    mesh = bpy.data.meshes.new(f"{MOD_ID}_grass_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(f"{MOD_ID}_grass", mesh)
    bpy.context.collection.objects.link(obj)
    layer = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for loop_index in poly.loop_indices:
            layer.data[loop_index].uv = uvs[mesh.loops[loop_index].vertex_index]
    # UP-BIASED CUSTOM NORMALS. Every card has its own four verts, so
    # shade_smooth() is a no-op here — there is nothing to smooth across —
    # and each quad keeps a horizontal face normal. That lights every card
    # as a little vertical wall: cards facing the sun blow out, cards
    # facing away go black, and the field turns to salt-and-pepper mottle.
    # This is an ASSET defect, not a preview artifact: it follows the mesh
    # into the engine. Blending 80% world-up with 20% face normal is the
    # standard foliage trick — at 100% up the cards lose all form, below
    # ~60% the wall effect comes back.
    from mathutils import Vector

    up = Vector((0.0, 0.0, 1.0))
    loop_normals = [(0.0, 0.0, 1.0)] * len(mesh.loops)
    for poly_index, poly in enumerate(mesh.polygons):
        lean = face_lean[poly_index] if poly_index < len(face_lean) else 0.0
        # Lay gain. This is NOT the geometrically literal card tilt: with
        # `lean` topping out near 0.04, a gain of 6 tilts the laid band
        # only 17 deg vs 2.6 deg upright, which measures as a 6% shading
        # delta — invisible, and smaller than the random horizontal 0.20
        # face-normal term, so per-card noise beats the stripe. There is
        # also a dead zone: the lambert peak near 28 deg gives +11%, and
        # the literal 47 deg card lay lands at 6% DARKER. 34 pushes the
        # laid band to ~60 deg for a ~20% darker band, which reads, and
        # demotes the 0.20 term to a perturbation.
        blended = (
            up * 0.80
            + Vector(poly.normal) * 0.20
            + Vector((lean * 34.0, 0.0, 0.0))
        ).normalized()
        for loop_index in poly.loop_indices:
            loop_normals[loop_index] = blended
    mesh.normals_split_custom_set(loop_normals)

    bk.assign_material(obj, blade)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(False)
    return [obj]


def _unused_grass_fringe(materials) -> list:
    """Alpha-cutout blade cards around the sod edge and over the mat.

    A flat turf plane always betrays itself at a grazing angle — from a
    driver's eye height it is a green decal with a hard cut edge. Real
    silhouette is what fixes that, so the mat gets a perimeter fringe of
    crossed blade cards standing proud of grade, plus scattered tufts to
    break the plane where it meets the pole.
    """

    blade = materials[f"{MOD_ID}_grass_blades"]
    objects = []
    rng = _fringe_rng()

    def card(name, centre, width, height, yaw):
        return bk.add_box(
            name,
            (centre[0], centre[1], centre[2] + height / 2.0),
            (width, 0.0016, height),
            blade,
            bevel=0.0,
            rotation=(0.0, 0.0, yaw),
            metric_uv=(width, height),
        )

    # Perimeter fringe: cards laid along each edge, crossed in pairs so the
    # run keeps volume when you walk around it.
    per_side = 13
    for edge_index, (dx, dy) in enumerate(((0, 1), (0, -1), (1, 0), (-1, 0))):
        for step in range(per_side):
            t = (step + 0.5) / per_side - 0.5
            jitter = (rng() - 0.5) * 0.04
            if dx:
                centre = (
                    dx * SOD_HALF,
                    spec.POST_Y + t * 2.0 * SOD_HALF + jitter,
                    GRADE_Z - 0.012,
                )
                base_yaw = math.pi / 2.0
            else:
                centre = (
                    t * 2.0 * SOD_HALF + jitter,
                    spec.POST_Y + dy * SOD_HALF,
                    GRADE_Z - 0.012,
                )
                base_yaw = 0.0
            height = GRASS_FRINGE * (0.75 + rng() * 0.5)
            width = 0.16 + rng() * 0.08
            objects.append(
                card(
                    f"{MOD_ID}_grass_edge_{edge_index}_{step}",
                    centre,
                    width,
                    height,
                    base_yaw + (rng() - 0.5) * 0.5,
                )
            )
            objects.append(
                card(
                    f"{MOD_ID}_grass_edge_{edge_index}_{step}_x",
                    centre,
                    width * 0.8,
                    height * 0.85,
                    base_yaw + math.pi / 2.0 + (rng() - 0.5) * 0.4,
                )
            )
    # Tufts across the mat, kept clear of the pole pad footprint.
    for tuft in range(22):
        angle = rng() * 2.0 * math.pi
        radius = spec.PAD_RADIUS + 0.12 + rng() * (SOD_HALF - spec.PAD_RADIUS - 0.2)
        centre = (
            radius * math.cos(angle),
            spec.POST_Y + radius * math.sin(angle),
            GRADE_Z - 0.010,
        )
        height = GRASS_FRINGE * (0.5 + rng() * 0.45)
        width = 0.13 + rng() * 0.06
        yaw = rng() * math.pi
        objects.append(
            card(f"{MOD_ID}_grass_tuft_{tuft}", centre, width, height, yaw)
        )
        objects.append(
            card(
                f"{MOD_ID}_grass_tuft_{tuft}_x",
                centre,
                width * 0.8,
                height * 0.85,
                yaw + math.pi / 2.0,
            )
        )
    return objects


def _fringe_rng():
    """Tiny deterministic LCG — the generator must rebuild byte-identical,
    and Python's `random` module state is not guaranteed across versions."""

    state = {"value": 0x2F6E2B1}

    def nxt() -> float:
        state["value"] = (1103515245 * state["value"] + 12345) & 0x7FFFFFFF
        return state["value"] / float(0x7FFFFFFF)

    return nxt


def neck_point(t: float):
    """One point on the swan neck's centreline: ``(y, z, tangent_angle)``.

    Cubic Bezier in the y-z plane with VERTICAL tangents at both ends, so
    the join to the pedestal below and to the pipe's cut end above are both
    tangent-continuous — no kink where the straight tube becomes curve.
    """

    p0 = (spec.POST_Y, spec.POST_TOP_Z)
    p3 = (0.0, NECK_CAP_Z)
    # Handle lengths set the fullness of the sweep. Long handles push the
    # curve's belly outward and flatten its crown, which is the profile the
    # elevation drawing shows.
    p1 = (p0[0], p0[1] + NECK_HANDLE_LOW)
    p2 = (p3[0], p3[1] - NECK_HANDLE_HIGH)

    mt = 1.0 - t
    y = mt**3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t**3 * p3[0]
    z = mt**3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t**3 * p3[1]
    dy = (
        3 * mt * mt * (p1[0] - p0[0])
        + 6 * mt * t * (p2[0] - p1[0])
        + 3 * t * t * (p3[0] - p2[0])
    )
    dz = (
        3 * mt * mt * (p1[1] - p0[1])
        + 6 * mt * t * (p2[1] - p1[1])
        + 3 * t * t * (p3[1] - p2[1])
    )
    return (y, z, math.atan2(dy, dz))


def neck_curve():
    """The swan neck centreline as ``[(y, z, tangent_angle_from_+z)]``."""

    return [neck_point(i / NECK_SEGMENTS) for i in range(NECK_SEGMENTS + 1)]


def sweep_tube(name, path, radius_of, material, *, rings=TUBE_SEGMENTS, uv=None):
    """Loft a closed ring along a y-z-plane path.

    ``path`` is [(y, z, tangent_angle)] and ``radius_of(index, z)`` returns
    the ring radius, so the same loft builds both the constant-section
    gooseneck and the cinched, swelling pole pad.

    ``uv`` is ``(u_tile, v_tile)`` in metres — u wraps the ring's own
    circumference, v runs TRUE ARC LENGTH, so a texture never stretches
    round a bend and never seams mid-surface.
    """

    import bpy

    radii = [radius_of(i, z) for i, (_y, z, _a) in enumerate(path)]
    vertices = []
    for (y, z, angle), radial in zip(path, radii):
        # Frame: the curve lives in the y-z plane, so x is always the
        # binormal and the ring only has to rotate about x.
        ny, nz = math.cos(angle), -math.sin(angle)
        for i in range(rings):
            theta = 2.0 * math.pi * i / rings
            vertices.append(
                (
                    radial * math.cos(theta),
                    y + radial * math.sin(theta) * ny,
                    z + radial * math.sin(theta) * nz,
                )
            )
    faces = []
    for ring in range(len(path) - 1):
        for i in range(rings):
            j = (i + 1) % rings
            a = ring * rings
            b = (ring + 1) * rings
            faces.append((a + i, a + j, b + j, b + i))

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    layer = mesh.uv_layers.new(name="UVMap")
    lengths = [0.0]
    for (y0, z0, _a0), (y1, z1, _a1) in zip(path, path[1:]):
        lengths.append(lengths[-1] + math.hypot(y1 - y0, z1 - z0))
    u_tile, v_tile = uv or (1.0, 1.0)
    for poly in mesh.polygons:
        for loop_index in poly.loop_indices:
            index = mesh.loops[loop_index].vertex_index
            ring, column = divmod(index, rings)
            layer.data[loop_index].uv = (
                column / rings * (2.0 * math.pi * radii[ring]) / u_tile,
                lengths[ring] / v_tile,
            )
    bk.assign_material(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def swan_neck(yellow) -> list:
    """The gooseneck: one constant-section 6-5/8" pipe swept along the
    Bezier, cut square at the top and closed with a flat plate.

    No flare and no sleeve. The earlier build swelled the tube into a
    0.105 m barrel wrapping the crossbar, which is not on ID-00010 — the
    crossbar goes THROUGH the pipe, and the 8.000" through-bolts are the
    proof (6.625" pipe OD + a washer/lock/nut stack is 8" to the millimetre).
    """

    neck = sweep_tube(
        f"{MOD_ID}_neck",
        neck_curve(),
        lambda _i, _z: spec.POST_RADIUS,
        yellow,
        uv=(POST_WRAP, 0.5),
    )
    # Flat end plate. Set 1.5 mm inside the pipe wall so the two cylindrical
    # surfaces never become coincident and z-fight.
    cap = bk.add_cylinder(
        f"{MOD_ID}_neck_cap",
        (0.0, 0.0, NECK_CAP_Z - NECK_CAP_T / 2.0),
        spec.POST_RADIUS - 0.0015,
        NECK_CAP_T,
        yellow,
        vertices=FITTING_SEGMENTS,
        bevel=0.0025,
    )
    return [neck, cap]


def _shift(point, axis: str, delta: float):
    index = {"X": 0, "Y": 1, "Z": 2}[axis]
    moved = list(point)
    moved[index] += delta
    return tuple(moved)


_AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}
# Right-handed (a, b, n) triples so a x b = n and face winding stays sane.
_AXIS_FRAME = {"X": (1, 2, 0), "Y": (2, 0, 1), "Z": (0, 1, 2)}


def pipe_drop(seat, axis, sign, host_axis, host_centre, host_r):
    """``drop(a, b)`` for a bolt landing radially on a round pipe.

    Returns how far the pipe's surface falls away from the seat plane at
    local offsets ``(a, b)``, measured along the bolt's own axis. Solved
    against the real cylinder rather than approximated, because the flanges
    that look wrong are the ones on a seat that is not the pipe's crown —
    there the fall-off is ASYMMETRIC and a symmetric cosine model lifts one
    side of the washer clean off the metal.
    """

    index_a, index_b, index_n = _AXIS_FRAME[axis]
    host = _AXIS_INDEX[host_axis]
    index_q = ({0, 1, 2} - {index_n, host}).pop()
    outward = math.copysign(1.0, seat[index_n] - host_centre[index_n])

    def drop(a, b):
        offset = {index_a: a, index_b: b}
        across = seat[index_q] + offset.get(index_q, 0.0) - host_centre[index_q]
        reach = math.sqrt(max(host_r * host_r - across * across, 0.0))
        surface = host_centre[index_n] + outward * reach
        return -(surface - seat[index_n]) * sign

    return drop


def saddle_flange(name, seat, axis, sign, radius, thickness, material, drop,
                  segments=WASHER_SEGMENTS):
    """A washer flange whose BEARING FACE is machined to the pipe under it.

    THE SUNK-BOLT FIX (player, 2026-08-14: "these bolts are merged too much
    into the yellow cylinder"). A flat disc pressed onto a round tube can
    only do one of two wrong things — hover on its high point, or sink far
    enough that the rim disappears and the head looks half-swallowed. The
    old code chose sinking, and on a 4 in upright a 1.3 mm flange sank 1.6
    mm, so the washer was entirely inside the pipe and only a shallow hex
    nub showed.

    A conforming flange has neither problem: the underside follows the
    cylinder exactly, and the flat top is set one full thickness above the
    HIGHEST point of that curve, so every part of the washer is proud of
    the metal and the head that seats on it stands clear all round.

    Returns ``(object, top)`` — ``top`` being the height of that flat face
    above the seat, which is where the head goes.
    """

    import bpy

    index_a, index_b, index_n = _AXIS_FRAME[axis]
    lows = []
    rim = []
    for k in range(segments):
        theta = 2.0 * math.pi * k / segments
        a, b = radius * math.cos(theta), radius * math.sin(theta)
        rim.append((a, b))
        lows.append(-drop(a, b))
    top = max(lows + [0.0]) + thickness

    def point(a, b, height):
        coords = list(seat)
        coords[index_a] += a
        coords[index_b] += b
        coords[index_n] += sign * height
        return tuple(coords)

    vertices = [point(a, b, low) for (a, b), low in zip(rim, lows)]
    vertices += [point(a, b, top) for a, b in rim]
    centre_low = len(vertices)
    vertices.append(point(0.0, 0.0, -drop(0.0, 0.0)))
    centre_top = len(vertices)
    vertices.append(point(0.0, 0.0, top))

    faces = []
    for k in range(segments):
        nxt = (k + 1) % segments
        faces.append((k, nxt, nxt + segments, k + segments))     # rim wall
        faces.append((centre_low, nxt, k))                        # bearing face
        faces.append((centre_top, k + segments, nxt + segments))  # flat top
    if sign < 0:
        faces = [tuple(reversed(face)) for face in faces]

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bk.assign_material(obj, material)
    return obj, top


def flange_bolt(
    name,
    seat,
    axis,
    sign,
    material,
    *,
    head_r,
    head_h,
    flange_r,
    flange_t,
    sink=0.0,
    drop=None,
):
    """A hex washer head with a serrated flange, SEATED on a surface.

    ``seat`` is the point where the flange's underside meets the metal and
    ``sign`` (+1/-1) points out of it, so every face downstream is measured
    from real contact rather than from a nominal coordinate: flange on the
    steel, head on the flange.

    On a FLAT host that is the whole story. On a curved one, pass ``drop``
    (see :func:`pipe_drop`) and the flange is generated to fit the pipe —
    ``sink`` is then unused, and unwanted: it was the old workaround, and
    burying the washer is what made these bolts look merged into the tube.
    """

    if drop is not None:
        flange, top = saddle_flange(
            f"{name}_flange", seat, axis, sign, flange_r, flange_t,
            material, drop,
        )
        return [
            flange,
            bk.add_cylinder(
                f"{name}_head",
                _shift(seat, axis, sign * (top + head_h / 2.0)),
                head_r,
                head_h,
                material,
                vertices=BOLT_SEGMENTS,
                axis=axis,
                bevel=0.0012,
            ),
        ]

    base = _shift(seat, axis, -sign * sink)
    return [
        bk.add_cylinder(
            f"{name}_flange",
            _shift(base, axis, sign * flange_t / 2.0),
            flange_r,
            flange_t,
            material,
            vertices=WASHER_SEGMENTS,
            axis=axis,
        ),
        bk.add_cylinder(
            f"{name}_head",
            _shift(base, axis, sign * (flange_t + head_h / 2.0)),
            head_r,
            head_h,
            material,
            vertices=BOLT_SEGMENTS,
            axis=axis,
            bevel=0.0012,
        ),
    ]


def hwh_38(name, seat, axis, sign, material, *, sink=0.0, drop=None):
    """3/8-16 x 1" hex washer head, serrated flange, Grade 5 — the fastener
    the drawings call for at every AdjustRight and crossbar joint."""

    return flange_bolt(
        name,
        seat,
        axis,
        sign,
        material,
        head_r=0.00825,
        head_h=0.0061,
        # 2.4 mm of flange, not 1.8: on a painted pipe the washer is the
        # part that says "bolted", and a rim thinner than the paint's own
        # highlight disappears at any distance.
        flange_r=0.0105,
        flange_t=0.0024,
        sink=sink,
        drop=drop,
    )


def hwh_14(name, seat, axis, sign, material, *, sink=0.0, drop=None):
    """1/4-20 x 1" hex washer head with serrated flange (ID-00011 item 1)."""

    return flange_bolt(
        name,
        seat,
        axis,
        sign,
        material,
        # Head grown from the bare 1/4-20 minimum to a stout 7/16 A/F with
        # 5 mm of height: at the distance these are actually looked at, the
        # catalogue-minimum head was a dark speck flush with the paint.
        head_r=0.0063,
        head_h=0.0050,
        flange_r=0.0082,
        flange_t=0.0018,
        sink=sink,
        drop=drop,
    )


def saddle_weld(name, xc, stub_r, material, *, bead=0.009, segments=FITTING_SEGMENTS):
    """The fillet weld running round a vertical stub where it lands on the
    crossbar's cylinder.

    The intersection of a tube with a tube is a saddle curve, so no torus or
    cone can sit on it — the bead has to be generated against the bar's real
    surface height ``z = zc + sqrt(R^2 - y^2)`` at every station round the
    stub. Without this the stub reads as a pipe pushed into another pipe,
    which is exactly the tell the drawings do not have.
    """

    import bpy

    def bar_z(y):
        return spec.BAR_CENTER_Z + math.sqrt(
            max(spec.BAR_RADIUS**2 - y * y, 1e-9)
        )

    # Three rings: foot on the bar, crown of the bead, throat on the stub.
    profile = ((bead, 0.0), (bead * 0.62, bead * 0.62), (0.0, bead))
    vertices = []
    for radial_out, lift in profile:
        radius = stub_r + radial_out
        for i in range(segments):
            theta = 2.0 * math.pi * i / segments
            y = radius * math.sin(theta)
            vertices.append((xc + radius * math.cos(theta), y, bar_z(y) + lift))
    faces = []
    for ring in range(len(profile) - 1):
        for i in range(segments):
            j = (i + 1) % segments
            a = ring * segments
            b = (ring + 1) * segments
            faces.append((a + i, a + j, b + j, b + i))

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    layer = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for loop_index in poly.loop_indices:
            index = mesh.loops[loop_index].vertex_index
            ring, column = divmod(index, segments)
            layer.data[loop_index].uv = (
                column / segments * 2.0 * math.pi * stub_r / 0.25,
                ring * bead / 0.25,
            )
    bk.assign_material(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def gusset_plate(name, angle, material):
    """One triangular base gusset: a real 8 mm PLATE standing on edge.

    ID-00015 shows four flat webs welded pipe-to-plate on the plate axes,
    BETWEEN the anchor studs. The old build used a 3-sided cone, which is a
    triangular pyramid lying on its side, and put them on the diagonals
    pointing straight at the anchors.

    THE LEFT-HANDED FRAME (round 5). Every one of these five faces was
    wound inside out, on all four gussets, in every build up to and
    including serial 28.

    SEVERITY, STATED CORRECTLY, because the first write-up of this round
    overstated it and this docstring is the durable record. It is NOT a
    hole. A triangular prism is CONVEX: reverse the winding and the near
    faces cull, but the FAR faces of the same solid then draw, so the
    silhouette is unchanged and the part still occludes what is behind
    it. Nothing becomes see-through. What shipped is four ~105 x 115 x
    10 mm plates with INVERTED NORMALS — lit from the wrong side, reading
    dark against the yellow, specular in the wrong place. Modest, but
    real, and on parts that are DELIBERATELY exposed: PAD_BOTTOM_Z is set
    above the whole mounting kit so the install hardware reads instead of
    being swallowed, which puts these four plates at ground level, where
    the camera and the car both are. Worth fixing. Not worth pulling a
    published mod for.

    Nothing in the file could see it: it encloses volume, it is closed and
    manifold, every edge borders two faces, no edge is traversed twice the
    same way, and there is no fold. Only the SIGN of the enclosed volume
    says anything, and until mesh_census() nothing looked at it.

    The winding is easy to get wrong here and the reason is worth writing
    down. The natural frame to reason in is (u = radial, v = z,
    n = tangential), and that frame is LEFT-handed: u x v = (ca, sa, 0) x
    (0, 0, 1) = (sa, -ca, 0) = -n. Work the cross products as if it were
    right-handed — which is what happened — and every face comes out
    confidently backwards. Measured: the as-written list encloses
    -60317.500 mm^3 and the reversed list +60317.500 mm^3, against a wedge
    of (GUSSET_REACH - r_in) x GUSSET_RISE / 2 x GUSSET_T = 60317.500 mm^3
    exactly, so the sign is settled by arithmetic and not by eye.
    """

    import bpy

    ca, sa = math.cos(angle), math.sin(angle)
    tx, ty = -sa, ca            # tangential, the plate's thickness axis
    r_in = spec.POST_RADIUS - 0.004
    r_out = GUSSET_REACH
    z0 = BASE_PLATE_TOP - 0.002
    corners = ((r_in, z0), (r_out, z0), (r_in, z0 + GUSSET_RISE))
    vertices = []
    for side in (-1.0, 1.0):
        off = side * GUSSET_T / 2.0
        for radial, z in corners:
            vertices.append(
                (radial * ca + tx * off, spec.POST_Y + radial * sa + ty * off, z)
            )
    faces = [
        (1, 2, 0),
        (5, 4, 3),
        (3, 4, 1, 0),
        (4, 5, 2, 1),
        (5, 3, 0, 2),
    ]
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bk.assign_material(obj, material)
    return obj


def moulded_shell(name, x0, x1, half_w, half_t, material, place, *,
                  stations=26, ring=24, end_r=0.017, corner=3.0,
                  uv_tile=0.07):
    """One injection-moulded body: a rounded-rectangle section lofted along
    x and domed off at both ends.

    A buckle is not a box. Every edge on a moulded part is radiused by the
    tool, the ends are hemispherical in plan AND in section, and the flanks
    are a rounded rectangle rather than a rectangle — which is why a
    bevelled cube reads as a black brick no matter how good its texture is
    (player, 2026-08-14: "make the buckles like you'd find on a backpack").

    ``half_w`` is a callable of x (so a half can waist in toward the joint),
    ``place(lx, lo, lw)`` maps the buckle's own frame into world space, and
    ``corner`` is the superellipse exponent: 2 is an ellipse, large is a
    box, ~3 is the moulded look.

    ``uv_tile`` is metres per texture repeat, and it is small on purpose:
    the moulded grain is drawn at ~50 cells across the map, so a 0.20 m
    tile put the pebbles at 4 mm — five times life size, which at macro
    range read as melted wax rather than an etched cavity. 0.07 m lands
    them at about 1.4 mm.
    """

    import bpy

    def envelope(x):
        reach = min(x - x0, x1 - x)
        if reach >= end_r:
            return 1.0
        return math.sqrt(max(1.0 - ((end_r - reach) / end_r) ** 2, 0.0))

    def section(scale_w, scale_t, index):
        theta = 2.0 * math.pi * index / ring
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        across = math.copysign(abs(cos_t) ** (2.0 / corner), cos_t)
        out = math.copysign(abs(sin_t) ** (2.0 / corner), sin_t)
        return scale_w * across, scale_t * out

    vertices = []
    uvs = []
    # Inset the end stations so the loft never collapses to a degenerate
    # ring — the caps are real n-gons and the mesh stays manifold for the
    # boolean slots.
    span = x1 - x0
    for i in range(stations + 1):
        x = x0 + span * (0.012 + 0.976 * i / stations)
        e = envelope(x)
        for k in range(ring):
            lw, lo = section(half_w(x) * e, half_t * e ** 0.42, k)
            vertices.append(place(x, lo, lw))
            uvs.append((x / uv_tile, (k / ring) * (4.0 * half_w(x)) / uv_tile))
    faces = []
    for i in range(stations):
        for k in range(ring):
            a = i * ring + k
            b = i * ring + (k + 1) % ring
            faces.append((a, b, b + ring, a + ring))
    # Caps.
    first = len(vertices)
    vertices.append(place(x0 + span * 0.012, 0.0, 0.0))
    uvs.append((x0 / uv_tile, 0.0))
    last = len(vertices)
    vertices.append(place(x1 - span * 0.012, 0.0, 0.0))
    uvs.append((x1 / uv_tile, 0.0))
    for k in range(ring):
        faces.append((first, (k + 1) % ring, k))
        base = stations * ring
        faces.append((last, base + k, base + (k + 1) % ring))

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    layer = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for loop_index in poly.loop_indices:
            layer.data[loop_index].uv = uvs[mesh.loops[loop_index].vertex_index]
    bk.assign_material(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(38.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def side_release_buckle(name, place, tilt, material):
    """A backpack side-release buckle, built as the two mouldings it is.

    Reference: the standard Duraflex-pattern buckle the player supplied.
    The parts that make it recognisable, in order of how much work each
    one does: the SEAM between the two halves (a buckle that is one solid
    lump is a block), the two long slits on the socket's face with the
    prong tips showing through them, the webbing slot at each end with the
    strap visible running through it, and the moulded tool grain.
    """

    female_x = (-0.010, 0.070)
    male_x = (-0.080, -0.018)
    half_t = BUCKLE_T / 2.0
    wide = BUCKLE_W / 2.0

    def waist_female(x):
        # Narrows toward the mouth, so the pair reads with the wasp waist
        # a real buckle has at its joint.
        return wide * (0.90 + 0.10 * min(max((x - female_x[0]) / 0.032, 0.0), 1.0))

    def waist_male(x):
        return wide * (0.90 + 0.10 * min(max((male_x[1] - x) / 0.030, 0.0), 1.0))

    objects = []
    female = moulded_shell(
        f"{name}_socket", female_x[0], female_x[1], waist_female, half_t,
        material, place, end_r=0.014,
    )
    male = moulded_shell(
        f"{name}_plug", male_x[0], male_x[1], waist_male, half_t,
        material, place, end_r=0.014,
    )

    def cutter(cname, lx, lo, lw, dims):
        return bk.add_box(
            cname, place(lx, lo, lw), dims, None,
            bevel=0.0, rotation=(tilt, 0.0, 0.0),
        )

    # Webbing slots, cut clean through so the strap shows in the gap.
    bk.cut_openings(female, [
        cutter(f"{name}_fslot", 0.0545, 0.0, 0.0, (0.0095, BUCKLE_T + 0.02, 0.078)),
        # The two face slits over the prongs.
        cutter(f"{name}_slit_a", 0.024, 0.013, 0.0335, (0.040, 0.020, 0.0100)),
        cutter(f"{name}_slit_b", 0.024, 0.013, -0.0335, (0.040, 0.020, 0.0100)),
    ])
    bk.cut_openings(male, [
        cutter(f"{name}_mslot", -0.0645, 0.0, 0.0, (0.0095, BUCKLE_T + 0.02, 0.078)),
    ])
    objects.extend((female, male))

    # The plug's tongue, bridging the mouth gap: without it the two halves
    # read as two separate lumps sitting near each other.
    objects.append(
        bk.add_box(
            f"{name}_tongue", place(-0.012, 0.0, 0.0), (0.036, 0.016, 0.058),
            material, bevel=0.003, rotation=(tilt, 0.0, 0.0),
        )
    )
    # Sprung prongs, showing through the socket's slits.
    for prong_index, lw in ((0, 0.0335), (1, -0.0335)):
        objects.append(
            bk.add_box(
                f"{name}_prong_{prong_index}", place(0.012, 0.0, lw),
                (0.056, 0.013, 0.0072), material,
                bevel=0.0018, rotation=(tilt, 0.0, 0.0),
            )
        )
    return objects


def neck_decal(name, material, *, t=0.5, length=0.15, aspect=2.6):
    """The builder's plate, wrapped ONTO the pipe instead of parked beside it.

    A flat 0.15 x 0.04 box tangent to a 0.084 m tube stands 2.4 mm proud at
    its own edges — at close range the label visibly hovers. This is a curved
    patch generated against the same Bezier the pipe is swept from, with a
    hand-built 0..1 UV so the legend prints once, upright, along the tube.
    """

    import bpy

    height = length / aspect
    rows, cols = 6, 14
    radius = spec.POST_RADIUS + 0.0016
    half_phi = (height / 2.0) / radius
    # Convert the patch's half-length into a Bezier parameter step by
    # measuring the local arc length per unit t.
    y0, z0, _a0 = neck_point(t - 0.01)
    y1, z1, _a1 = neck_point(t + 0.01)
    dt = 0.5 * length / (math.hypot(y1 - y0, z1 - z0) / 0.02)

    vertices = []
    uvs = []
    for row in range(rows + 1):
        v = row / rows
        y, z, angle = neck_point(t - dt + 2.0 * dt * v)
        ny, nz = math.cos(angle), -math.sin(angle)
        for col in range(cols + 1):
            u = col / cols
            phi = -half_phi + 2.0 * half_phi * u
            vertices.append(
                (
                    radius * math.cos(phi),
                    y + radius * math.sin(phi) * ny,
                    z + radius * math.sin(phi) * nz,
                )
            )
            # Both axes flipped: the model's 180-degree yaw into BeamNG
            # vehicle space rotates the printed face, so the plate came
            # out upside down AND mirrored (player report) — a 180-degree
            # texture rotation, which is exactly a flip of BOTH axes.
            uvs.append((1.0 - v, u))
    faces = []
    stride = cols + 1
    for row in range(rows):
        for col in range(cols):
            a = row * stride + col
            faces.append((a, a + 1, a + stride + 1, a + stride))

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    layer = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for loop_index in poly.loop_indices:
            layer.data[loop_index].uv = uvs[mesh.loops[loop_index].vertex_index]
    bk.assign_material(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def build_visual(materials) -> list:
    yellow = materials[f"{MOD_ID}_goal_yellow"]
    steel = materials[f"{MOD_ID}_steel"]
    concrete = materials[f"{MOD_ID}_concrete"]
    vinyl = materials[f"{MOD_ID}_pad_vinyl"]
    foam = materials[f"{MOD_ID}_pad_foam"]
    strap = materials[f"{MOD_ID}_strap_black"]
    buckle = materials[f"{MOD_ID}_buckle_nylon"]
    # Fasteners on the PAINTED structure wear the paint; the base mounting
    # kit stays galvanised because it is site hardware installed under the
    # turf, which is what the drawing specifies and what you would actually
    # find if you dug it up.
    bolt = materials[f"{MOD_ID}_bolt_yellow"]
    decal = materials[f"{MOD_ID}_builder_decal"]
    cap_face = materials[f"{MOD_ID}_bar_cap"]
    soil = materials[f"{MOD_ID}_field_soil"]
    sod_side = materials[f"{MOD_ID}_sod_edge"]
    turf = materials[f"{MOD_ID}_field_turf"]

    objects = []

    # --- Field build-up (ID-00003, "Natural Grass Application") ---------
    # The drawing's section is the spec: concrete footing, then 9-5/8 in of
    # subgrade soil, capped by the sod mat at finish grade. The mounting
    # kit is BUILT and then BURIED, exactly as installed — you see turf and
    # the pole, and the hardware is under your feet.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_footing",
            (0.0, spec.POST_Y, FOOTING_TOP_Z / 2.0),
            (2.0 * SOIL_HALF, 2.0 * SOIL_HALF, FOOTING_TOP_Z),
            concrete,
            # No bevel: the 22.5-degree bevel steps fall under the 38-degree
            # auto-smooth and drag the big top face's corner normals, which
            # renders as diagonal shading bands across the whole slab.
            bevel=0.0,
            metric_uv=(1.15, 1.15),
        )
    )
    # Z-FIGHT LAW: the subgrade STARTS at the footing top, it does not
    # span from zero. Both blocks share a footprint, so a soil block
    # running 0..SOD_Z0 put its side faces in the same plane AND the same
    # z range as the footing's — two coplanar surfaces fighting for the
    # bottom band of the section (player report, in-game shimmer along the
    # edge). Stacked layers never overlap; they only ever touch.
    subgrade_h = SOD_Z0 - FOOTING_TOP_Z
    objects.append(
        bk.add_box(
            f"{MOD_ID}_subgrade",
            (0.0, spec.POST_Y, FOOTING_TOP_Z + subgrade_h / 2.0),
            (2.0 * SOIL_HALF, 2.0 * SOIL_HALF, subgrade_h),
            soil,
            bevel=0.0,
            metric_uv=(0.85, 0.85),
        )
    )
    # Sod mat: its SIDES carry the cut-edge texture (grass / thatch /
    # soil), so v must run 0..1 over exactly the mat thickness. Its top
    # stops just BELOW grade so the turf skin can sit proud of it rather
    # than sharing its top plane.
    sod_h = SOD_T - TURF_T * 0.75
    objects.append(
        bk.add_box(
            f"{MOD_ID}_sod",
            (0.0, spec.POST_Y, SOD_Z0 + sod_h / 2.0),
            (2.0 * SOD_HALF, 2.0 * SOD_HALF, sod_h),
            sod_side,
            bevel=0.0,
            metric_uv=(0.42, sod_h),
        )
    )
    # Turf skin: a separate thin slab whose TOP is a one-shot 0..1 mowed
    # field print, laid over the mat so the mowing stripes are authored at
    # true scale instead of tiling every 40 cm.
    # Inset slightly and standing proud of the mat: same z-fight rule —
    # matching the mat's footprint would put the two boxes' side faces in
    # one plane and their tops in another.
    turf_half = SOD_HALF - 0.002
    turf_slab = bk.add_box(
        f"{MOD_ID}_turf",
        (0.0, spec.POST_Y, GRADE_Z - TURF_T / 2.0),
        (2.0 * turf_half, 2.0 * turf_half, TURF_T),
        turf,
        bevel=0.0,
    )
    turf_mesh = turf_slab.data
    turf_uv = turf_mesh.uv_layers.active or turf_mesh.uv_layers.new(name="UVMap")
    for poly in turf_mesh.polygons:
        for loop_index in poly.loop_indices:
            vx, vy, _vz = turf_mesh.vertices[turf_mesh.loops[loop_index].vertex_index].co
            turf_uv.data[loop_index].uv = (
                vx / (2.0 * turf_half) + 0.5,
                (vy - spec.POST_Y) / (2.0 * turf_half) + 0.5,
            )
    objects.append(turf_slab)
    objects.extend(grass_field(materials))
    # Base Plate Mounting Kit, ID-00020: a 16 in square 1/2 in steel ground
    # plate on a 14 in bolt square, four 3/4-10 galvanised anchor studs each
    # carrying a levelling nut UNDER the gooseneck plate and a flat washer,
    # lock washer and hex nut over it, with 2-3/4 in of stud left proud.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_ground_plate",
            (0.0, spec.POST_Y, SLAB_TOP_Z + GROUND_PLATE_T / 2.0),
            (GROUND_PLATE, GROUND_PLATE, GROUND_PLATE_T),
            steel,
            bevel=0.0,
            metric_uv=(0.42, 0.42),
        )
    )
    # Gooseneck base plate (ID-00015) — painted with the post, not galvanised.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_base_plate",
            (0.0, spec.POST_Y, BASE_PLATE_Z + BASE_PLATE_T / 2.0),
            (BASE_PLATE, BASE_PLATE, BASE_PLATE_T),
            yellow,
            bevel=0.004,
            metric_uv=(0.42, 0.42),
        )
    )
    # Four triangular gusset webs on the plate AXES — ID-00015 welds them
    # between the anchor studs, not on the diagonals pointing at them.
    for gusset_index in range(4):
        objects.append(
            gusset_plate(
                f"{MOD_ID}_base_gusset_{gusset_index}",
                math.radians(gusset_index * 90.0),
                yellow,
            )
        )
    # Fillet weld round the pipe where it lands on the plate.
    objects.append(
        bk.add_torus(
            f"{MOD_ID}_base_weld",
            (0.0, spec.POST_Y, BASE_PLATE_TOP),
            spec.POST_RADIUS + 0.005,
            0.006,
            yellow,
            major_segments=FITTING_SEGMENTS,
            minor_segments=8,
        )
    )
    for bolt_index in range(4):
        angle = math.radians(45.0 + bolt_index * 90.0)
        # 14 in square bolt pattern: the drawing dimensions the SQUARE, so
        # the stud circle radius is half the diagonal of 14 in.
        reach = BOLT_SQUARE / 2.0 * math.sqrt(2.0)
        bx = reach * math.cos(angle)
        by = spec.POST_Y + reach * math.sin(angle)
        # Stud: cast into the footing, cut off at the 2-3/4 in projection.
        stud_bottom = SLAB_TOP_Z - 0.06
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_anchor_stud_{bolt_index}",
                (bx, by, (stud_bottom + ANCHOR_TOP_Z) / 2.0),
                ANCHOR_R,
                ANCHOR_TOP_Z - stud_bottom,
                steel,
                vertices=12,
            )
        )
        # Levelling nut: seated ON the ground plate and carrying the base
        # plate on its own top face. It IS the standoff.
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_level_nut_{bolt_index}",
                (bx, by, GROUND_PLATE_TOP + HEX_NUT_H / 2.0),
                HEX_NUT_R,
                HEX_NUT_H,
                steel,
                vertices=BOLT_SEGMENTS,
            )
        )
        stack = BASE_PLATE_TOP
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_flat_washer_{bolt_index}",
                (bx, by, stack + FLAT_WASHER_T / 2.0),
                FLAT_WASHER_R,
                FLAT_WASHER_T,
                steel,
                vertices=WASHER_SEGMENTS,
            )
        )
        stack += FLAT_WASHER_T
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_lock_washer_{bolt_index}",
                (bx, by, stack + LOCK_WASHER_T / 2.0),
                LOCK_WASHER_R,
                LOCK_WASHER_T,
                steel,
                vertices=WASHER_SEGMENTS,
            )
        )
        stack += LOCK_WASHER_T
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_anchor_nut_{bolt_index}",
                (bx, by, stack + HEX_NUT_H / 2.0),
                HEX_NUT_R,
                HEX_NUT_H,
                steel,
                vertices=BOLT_SEGMENTS,
                bevel=0.0015,
            )
        )
    # Four 3/4-10 x 2 in levelling bolts (ID-00015 item 1). Page 7 step 4:
    # "thread the levelling bolts into the pre-threaded holes until the
    # bottom side of the bolt comes into contact with the steel plate
    # below" — so the shank is ONE continuous piece running from the ground
    # plate, through the base plate, up to the head. The old build had a
    # 24 mm stub floating 10 mm above the ground plate and a hex head
    # floating 3 mm above the base plate with nothing joining them.
    for level_index in range(4):
        angle = math.radians(45.0 + level_index * 90.0)
        bx = LEVEL_BOLT_R * math.cos(angle)
        by = spec.POST_Y + LEVEL_BOLT_R * math.sin(angle)
        # A jack screw is not a bare stud with a head on it (player,
        # 2026-08-15: "these bolt types are missing washers and nuts"). It
        # is run down onto the plate below and then LOCKED, so what stands
        # above the base plate is a flat washer, a jam nut run hard down on
        # it, and only then the head. Every one of the four anchor studs
        # beside them already carried its washer/lock/nut stack, which is
        # exactly why these four read as unfinished next to them.
        seat = BASE_PLATE_TOP
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_level_washer_{level_index}",
                (bx, by, seat + LEVEL_WASHER_T / 2.0),
                LEVEL_WASHER_R,
                LEVEL_WASHER_T,
                steel,
                vertices=WASHER_SEGMENTS,
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_level_jam_nut_{level_index}",
                (bx, by, seat + LEVEL_WASHER_T + JAM_NUT_H / 2.0),
                HEX_NUT_R,
                JAM_NUT_H,
                steel,
                vertices=BOLT_SEGMENTS,
                bevel=0.0012,
            )
        )
        head_bottom = seat + LEVEL_WASHER_T + JAM_NUT_H
        # ONE continuous shank from the ground plate to the underside of the
        # head, threading through the base plate, the washer and the jam nut
        # (all of which are annular in reality and hide it here).
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_level_shank_{level_index}",
                (bx, by, (GROUND_PLATE_TOP + head_bottom) / 2.0),
                ANCHOR_R,
                head_bottom - GROUND_PLATE_TOP,
                steel,
                vertices=12,
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_level_bolt_{level_index}",
                (bx, by, head_bottom + LEVEL_BOLT_HEAD_H / 2.0),
                HEX_NUT_R,
                LEVEL_BOLT_HEAD_H,
                steel,
                vertices=BOLT_SEGMENTS,
                bevel=0.0015,
            )
        )
    # (The GPAFIT grade access frame was removed at the player's request —
    # ID-00003 lists it as optional, and it read as a steel picture frame
    # lying on the turf.)

    # --- Pedestal and swan neck ----------------------------------------
    post_bottom = SLAB_TOP_Z
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_post",
            (0.0, spec.POST_Y, (post_bottom + spec.POST_TOP_Z) / 2.0),
            spec.POST_RADIUS,
            spec.POST_TOP_Z - post_bottom,
            yellow,
            vertices=TUBE_SEGMENTS,
            metric_uv=(POST_WRAP, 0.5),
        )
    )
    # The swan neck is ONE continuous S-curve, not two elbows with a
    # straight horizontal run between them (ID-00001 elevation — the
    # player's "curved like this"). A cubic Bezier with vertical tangents
    # at both ends is exactly that shape: it leaves the pedestal plumb,
    # sweeps over, and arrives under the crossbar plumb again, with
    # curvature that eases instead of switching on at a hard tangent point.
    objects.extend(swan_neck(yellow))

    # --- Crossbar tee (ID-00010) ----------------------------------------
    # Two 5/8-11 x 8 in galvanised hex head bolts, driven through in
    # OPPOSITE directions (the drawing calls that out in red), each with a
    # flat washer UNDER THE HEAD as well as under the lock washer and nut —
    # item 2 has QTY 4 for two bolts. They cross the pipe on the Y axis,
    # spaced either side of centre along the bar; an 8 in bolt is exactly
    # the 6-5/8 in pipe plus that stack, which is what proved there is no
    # sleeve here to begin with.
    # The neck pipe reaches y = 0 only at its very TOP (NECK_CAP_Z); at
    # the crossbar's centre height its centreline is still short of the
    # goal plane. Seating this hardware at a nominal y = 0 is why the
    # heads and washers floated off the pipe on one side and sank into it
    # on the other (player report). Sample the real curve instead.
    neck_y_at_bar = min(
        neck_curve(), key=lambda sample: abs(sample[1] - spec.BAR_CENTER_Z)
    )[0]
    for through_index, flip in enumerate((1.0, -1.0)):
        bolt_x = TEE_BOLT_X * flip
        # Where the bolt leaves the pipe wall at this station.
        wall_y = math.sqrt(spec.POST_RADIUS**2 - bolt_x**2)
        # OPPOSITE directions per the drawing's red note: one bolt enters
        # from -y and nuts on +y, the other the reverse. `flip` chooses
        # which wall the head bears on; the stacks then grow AWAY from the
        # pipe on each side.
        # SPOTFACE BOSSES. A 5/8 flat washer is 44 mm across, and over
        # that span a 168 mm pipe's surface falls away ~18 mm — so a flat
        # washer laid straight on the pipe buries half of itself and
        # leaves the other half hanging, which is the crescent the player
        # saw "warping into the pipe". Real equipment machines a spotface
        # (or welds a pad) to give the fastener a flat seat. The boss face
        # clears the HIGHEST point of pipe within its own footprint.
        boss_r = 0.0245
        boss_face = (
            math.sqrt(spec.POST_RADIUS**2 - max(abs(bolt_x) - boss_r, 0.0) ** 2)
            + 0.0008
        )
        for boss_side in (1.0, -1.0):
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_tee_boss_{through_index}_{int(boss_side)}",
                    (
                        bolt_x,
                        neck_y_at_bar + boss_side * (boss_face - 0.016),
                        spec.BAR_CENTER_Z,
                    ),
                    boss_r,
                    0.032,
                    yellow,
                    vertices=FITTING_SEGMENTS,
                    axis="Y",
                    bevel=0.0025,
                )
            )
        head_face = neck_y_at_bar - flip * boss_face
        nut_face = neck_y_at_bar + flip * boss_face
        washer_t, lock_t, nut_h, head_h = 0.0045, 0.0035, 0.0140, 0.0110
        stack = nut_face
        for label, radius, thick, verts in (
            ("washer_b", 0.0220, washer_t, WASHER_SEGMENTS),
            ("lock", 0.0155, lock_t, WASHER_SEGMENTS),
            ("nut", 0.0138, nut_h, BOLT_SEGMENTS),
        ):
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_tee_bolt_{through_index}_{label}",
                    (bolt_x, stack + flip * thick / 2.0, spec.BAR_CENTER_Z),
                    radius,
                    thick,
                    bolt,
                    vertices=verts,
                    axis="Y",
                    bevel=0.0012 if verts == BOLT_SEGMENTS else 0.0,
                )
            )
            stack += flip * thick
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_tee_bolt_{through_index}_washer_a",
                (bolt_x, head_face - flip * washer_t / 2.0, spec.BAR_CENTER_Z),
                0.0220,
                washer_t,
                bolt,
                vertices=WASHER_SEGMENTS,
                axis="Y",
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_tee_bolt_{through_index}_head",
                (
                    bolt_x,
                    head_face - flip * (washer_t + head_h / 2.0),
                    spec.BAR_CENTER_Z,
                ),
                0.0138,
                head_h,
                bolt,
                vertices=BOLT_SEGMENTS,
                axis="Y",
                bevel=0.0015,
            )
        )
        # The shank is drawn to its full 8.000 in, so it runs past the nut
        # exactly as far as a stock-length bolt does on the real post.
        shank_start = head_face - flip * washer_t
        shank_len = 8.0 * 0.0254
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_tee_bolt_{through_index}_shank",
                (bolt_x, shank_start + flip * shank_len / 2.0, spec.BAR_CENTER_Z),
                0.0079,
                shank_len,
                bolt,
                vertices=12,
                axis="Y",
            )
        )
    # Two 3/8-16 serrated-flange hex bolts down through the pipe's end plate
    # (ID-00010 item 5) — the pair that locks the bar's rotation once it is
    # level. Seated on the plate, not hovering over it.
    for crown_index, crown_x in enumerate((-TEE_CROWN_X, TEE_CROWN_X)):
        objects.extend(
            hwh_38(
                f"{MOD_ID}_tee_crown_{crown_index}",
                (crown_x, 0.0, NECK_CAP_Z),
                "Z",
                1.0,
                bolt,
            )
        )
    # Builder's plate, curved onto the pipe on the +x flank of the sweep,
    # where the tube is only 14 degrees off horizontal so the legend reads
    # level.
    objects.append(neck_decal(f"{MOD_ID}_neck_decal", decal))
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_crossbar",
            (0.0, 0.0, spec.BAR_CENTER_Z),
            spec.BAR_RADIUS,
            2.0 * BAR_HALF_LENGTH,
            yellow,
            vertices=TUBE_SEGMENTS,
            axis="X",
            metric_uv=(BAR_WRAP, 0.5),
        )
    )
    # Flat capped bar ends carrying the builder's mark (ID-00023 shows the
    # logo embossed dead centre of the cap). The old bar stopped 3 cm past
    # the upright with an open smooth-shaded end, which read as a rounded
    # tube tip; the real bar runs a full diameter past and is closed flat.
    for side_index, cap_x in enumerate((-BAR_HALF_LENGTH, BAR_HALF_LENGTH)):
        outward = math.copysign(1.0, cap_x)
        cap = bk.add_cylinder(
            f"{MOD_ID}_bar_cap_{side_index}",
            (cap_x + outward * BAR_CAP_T / 2.0, 0.0, spec.BAR_CENTER_Z),
            spec.BAR_RADIUS + BAR_CAP_PROUD,
            BAR_CAP_T,
            cap_face,
            vertices=FITTING_SEGMENTS,
            axis="X",
            bevel=0.004,
        )
        # Hand-map the OUTWARD disc face to 0..1 so the mark prints once,
        # centred, instead of the primitive's radial fan smearing it.
        #
        # THE LOCAL-VS-WORLD UV BUG (measured 2026-08-15, not guessed). The
        # primitives keep their location on the OBJECT — add_cylinder applies
        # rotation and scale but not location — so `mesh.vertices[].co` is
        # LOCAL and already centred on the disc. Subtracting the world-frame
        # BAR_CENTER_Z from it therefore pushed v out to -22.27..-21.27: the
        # right span, one full tile, but landing on a non-integer offset, so
        # the map WRAPPED across the face. The disc's lower 27% was showing
        # the texture's top edge and the upper 73% the rest, which put the
        # mark high on the cap and printed a phantom second pair of arcs low
        # on it. Probed with a standalone Blender script rather than reasoned
        # about: the seam sat 30.5 mm below a 67 mm disc's centre.
        mesh = cap.data
        layer = mesh.uv_layers.active or mesh.uv_layers.new(name="UVMap")
        span = 2.0 * (spec.BAR_RADIUS + BAR_CAP_PROUD)
        for poly in mesh.polygons:
            if poly.normal.x * outward > 0.5:
                for loop_index in poly.loop_indices:
                    _vx, vy, vz = mesh.vertices[mesh.loops[loop_index].vertex_index].co
                    layer.data[loop_index].uv = (
                        0.5 + outward * vy / span,
                        0.5 + vz / span,
                    )
                continue
            # THE WRAPPED-LOGO FIX (player, 2026-08-15: "the logo got
            # wrapped around the extreme edges"). Only the printed face was
            # being mapped; every OTHER polygon of the cap — the cylindrical
            # rim band, the inward face, and the bevel between them — kept
            # the primitive's default cylinder UVs, which run the full 0..1
            # of the map. Measured: 117 of the 240 texcoords on those faces
            # landed inside the medallion, so the letters and the bead ring
            # were smeared right around the rim and read as a second, warped
            # copy of the mark at any oblique angle.
            #
            # They are sent to a small patch in the map's CORNER instead,
            # which is plain painted field: the artwork is radial and its
            # outermost feature, the bead, ends at 0.998 of the disc radius,
            # so the corners at radius 1.414 carry nothing but paint. The
            # patch is a real 0.06-wide square rather than a single point so
            # the UVs stay non-degenerate and mip selection behaves.
            for loop_index in poly.loop_indices:
                _vx, vy, vz = mesh.vertices[mesh.loops[loop_index].vertex_index].co
                layer.data[loop_index].uv = (
                    0.02 + 0.06 * (0.5 + vy / span),
                    0.02 + 0.06 * (0.5 + vz / span),
                )
        objects.append(cap)

    # --- Uprights: welded fixed end stubs, AdjustRight hardware ---------
    # ID-00011 Detail View B / ID-00023. The upright is NOT a tube pushed
    # through the crossbar with a painted collar round it. A galvanised stub
    # is welded to the bar's crown, the upright slips OVER it, and the
    # square-cut bottom of the upright leaves a crescent of bare stub
    # showing: ~6 mm at the sides where the bar's surface is highest, ~31 mm
    # front and back where it has fallen away. That crescent, and the fillet
    # weld under it, are what make the joint read as fabricated steel.
    for side, xc in (("l", -spec.UPRIGHT_X), ("r", spec.UPRIGHT_X)):
        outward = math.copysign(1.0, xc)
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_stub_{side}",
                (xc, 0.0, (spec.BAR_CENTER_Z + UPRIGHT_BASE_Z + 0.12) / 2.0),
                STUB_RADIUS,
                UPRIGHT_BASE_Z + 0.12 - spec.BAR_CENTER_Z,
                steel,
                vertices=TUBE_SEGMENTS,
                metric_uv=(2.0 * math.pi * STUB_RADIUS, 0.3),
            )
        )
        objects.append(
            saddle_weld(f"{MOD_ID}_stub_weld_{side}", xc, STUB_RADIUS, steel)
        )
        # Two 3/8-16 x 1 in hex washer head serrated flange bolts down
        # through the bar's crown, one either side of the stub — FOUR
        # across both sides. There WAS a third per side, offset along the
        # bar's field face, which made six; the player had it deleted on
        # 2026-08-15 and it is not coming back, so the count this file
        # records against ID-00023 is now four crown bolts and no face
        # bolt. Do not re-cite six from an older revision of this comment.
        # Asymmetric on purpose: outboard there is only the cap end to work
        # against, and the drawing shows that bolt pulled in closer.
        bar_axis = (0.0, 0.0, spec.BAR_CENTER_Z)
        for bolt_index, dx in enumerate(STUB_BOLT_X):
            crown_seat = (xc + outward * dx, 0.0, spec.CROSSBAR_TOP_Z)
            objects.extend(
                hwh_38(
                    f"{MOD_ID}_stub_crown_{side}_{bolt_index}",
                    crown_seat,
                    "Z",
                    1.0,
                    bolt,
                    drop=pipe_drop(crown_seat, "Z", 1.0, "X", bar_axis,
                                   spec.BAR_RADIUS),
                )
            )
        # Two 1/4-20 serrated flange bolts up the upright, into the stub
        # inside it (ID-00011 item 1, qty 4 = two per upright). They are on
        # the +Y face — the pedestal side — not the field side (player,
        # 2026-08-15: "move it to the other side").
        # BOTH move, and that is a judgement worth recording. The pair is
        # ONE treatment into ONE stub, 120 mm apart on the same face;
        # splitting it across opposite faces would be hardware no drawing
        # shows and no fabricator would make. The lower bolt is NOT hidden
        # by the saddle bead either — it stands 94 mm clear of the bead's
        # crown and renders plainly from the field — so only one of them
        # being in the player's screenshot is a crop, not a bolt that
        # cannot be seen.
        # The +Y face is clear here: the flag mount is 10.5 m higher up
        # the same face and the pole pad tops out at 1.93 m, both far from
        # the 3.13 m and 3.25 m these two land on.
        for tie_index, dz in enumerate(STUB_TIE_Z):
            tie_seat = (xc, spec.UPRIGHT_RADIUS, UPRIGHT_BASE_Z + dz)
            objects.extend(
                hwh_14(
                    f"{MOD_ID}_stub_tie_{side}_{tie_index}",
                    tie_seat,
                    "Y",
                    1.0,
                    bolt,
                    drop=pipe_drop(tie_seat, "Y", 1.0, "Z",
                                   (xc, 0.0, 0.0), spec.UPRIGHT_RADIUS),
                )
            )
        # Detail View B: 35 ft uprights ship in two pieces. The seam sits at
        # the halfway point of the run, and the sleeve is nearly flush — a
        # 3.5 mm proud band read as a collar, so it comes down to 2 mm and
        # gets the two small bolts the detail actually shows.
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_upright_splice_{side}",
                (xc, 0.0, UPRIGHT_SPLICE_Z),
                spec.UPRIGHT_RADIUS + 0.002,
                0.16,
                yellow,
                vertices=FITTING_SEGMENTS,
                metric_uv=(UPRIGHT_WRAP, 0.5),
            )
        )
        splice_r = spec.UPRIGHT_RADIUS + 0.002
        for splice_index, dz in ((0, -0.052), (1, 0.052)):
            splice_seat = (xc, -splice_r, UPRIGHT_SPLICE_Z + dz)
            objects.extend(
                hwh_14(
                    f"{MOD_ID}_splice_bolt_{side}_{splice_index}",
                    splice_seat,
                    "Y",
                    -1.0,
                    bolt,
                    drop=pipe_drop(splice_seat, "Y", -1.0, "Z",
                                   (xc, 0.0, 0.0), splice_r),
                )
            )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_upright_{side}",
                (xc, 0.0, (UPRIGHT_BASE_Z + spec.UPRIGHT_TOP_Z) / 2.0),
                spec.UPRIGHT_RADIUS,
                spec.UPRIGHT_TOP_Z - UPRIGHT_BASE_Z,
                yellow,
                vertices=TUBE_SEGMENTS,
                metric_uv=(UPRIGHT_WRAP, 0.5),
            )
        )
        objects.append(
            bk.add_sphere(
                f"{MOD_ID}_cap_{side}",
                (xc, 0.0, spec.UPRIGHT_TOP_Z),
                0.052,
                yellow,
                segments=48,
                rings=24,
                scale=(1.0, 1.0, 0.55),
            )
        )
        # Directional flag mount: welded pad, bored tab, snap hook. The
        # grommet and the hem it is swaged into belong to the CLOTH and are
        # built in flag_grommet()/flag_mesh(), not here. (This line named a
        # "welded eye" for a round after the anchor eye was deleted, and
        # then a "header" for a round after that part turned out never to
        # have existed. A call-site summary is documentation and rots like
        # documentation.) The cloth itself is soft-body and lives in the
        # cage.
        objects.extend(
            flag_attachment(f"{MOD_ID}_flag_mount_{side}", side, xc, steel)
        )

    # --- Pedestal safety pad: vinyl shell over foam ----------------------
    # A pole pad is a heat-sealed vinyl SHELL wrapped round a foam core and
    # cinched by straps, so the softness has to be in the SILHOUETTE: the
    # shell swells between the straps and pinches in at each one.
    #
    # It is also SWEPT ALONG THE POLE, not lathed about a vertical axis. A
    # 6 ft pad on this post necessarily covers the first 0.38 m of the sweep,
    # and every real gooseneck pad leans out of the top with the pipe. A
    # surface of revolution cannot do that, which is why the old pad had to
    # stop at 1.45 m — 4 ft 9 in of cover on a post the rulebook wants
    # padded to 6 ft, and 0.36 m short of its own collision prism.
    objects.append(pad_shell(f"{MOD_ID}_pad", vinyl))
    # Foam liner glimpsed INSIDE the open bottom edge of the wrap. The hem
    # rolls in to r 0.2375 at grade, so a 0.258 liner did not peek out of
    # the pad — it wore the pad like a sleeve, 20 mm of bare foam standing
    # proud of the vinyl all the way round.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_pad_foam_liner",
            (0.0, spec.POST_Y, PAD_BOTTOM_Z + 0.030),
            0.228,
            0.060,
            foam,
            vertices=TUBE_SEGMENTS,
        )
    )
    # Drawcord closing the throat of the wrap onto the pipe.
    throat_y, throat_z, throat_a = pad_frame(PAD_TOP_Z - 0.006)
    objects.append(
        bk.add_torus(
            f"{MOD_ID}_pad_cord",
            (0.0, throat_y, throat_z),
            spec.POST_RADIUS + 0.0085,
            0.008,
            strap,
            rotation=(-throat_a, 0.0, 0.0),
            major_segments=FITTING_SEGMENTS,
            minor_segments=10,
        )
    )
    # Soft webbing straps: a wide flat band (not a round bead), each closed
    # by a side-release buckle on the field side. Sampled off the pad's own
    # path so the upper straps lean with the pipe instead of staying level
    # while the pad under them tilts away.
    for strap_index, strap_z in enumerate(PAD_STRAP_Z):
        sy, sz, sa = pad_frame(strap_z)
        ny, nz = math.cos(sa), -math.sin(sa)
        band_r = PAD_STRAP_R + 0.006
        band = bk.add_cylinder(
            f"{MOD_ID}_pad_strap_{strap_index}",
            (0.0, sy, sz),
            band_r,
            PAD_STRAP_W,
            strap,
            vertices=TUBE_SEGMENTS,
            bevel=0.004,
            # v spans the width exactly ONCE so the webbing's rolled
            # selvedge lands on the strap's real edges instead of tiling
            # a false edge cord across the middle of it.
            metric_uv=(2.0 * math.pi * PAD_STRAP_R / 6.0, PAD_STRAP_W),
        )
        band.rotation_euler = (-sa, 0.0, 0.0)
        objects.append(band)

        # The buckle's own frame: lx along the strap, lo out of the pad,
        # lw across the webbing. Bedded 1 mm into the strap so it sits on
        # the webbing rather than hovering over it.
        centre_r = band_r + BUCKLE_T / 2.0 - 0.001

        def place(lx, lo, lw, sy=sy, sz=sz, ny=ny, nz=nz, centre_r=centre_r):
            r = centre_r + lo
            return (lx, sy - r * ny - lw * nz, sz - r * nz + lw * ny)

        objects.extend(
            side_release_buckle(
                f"{MOD_ID}_pad_buckle_{strap_index}", place, -sa, buckle
            )
        )
    return objects


def pad_frame(z: float):
    """The pole's centreline frame at height ``z``: ``(y, z, angle)``.

    Straight below ``POST_TOP_Z``, then on the Bezier. Anything mounted on
    the pad — strap, buckle, drawcord — is placed from this rather than from
    a nominal y, because above 1.55 m the pipe has already walked forward
    and a strap left at the pedestal's y would hang in mid air.
    """

    if z <= spec.POST_TOP_Z:
        return (spec.POST_Y, z, 0.0)
    low, high = 0.0, 1.0
    for _ in range(40):
        mid = 0.5 * (low + high)
        if neck_point(mid)[1] < z:
            low = mid
        else:
            high = mid
    y, _z, angle = neck_point(0.5 * (low + high))
    return (y, z, angle)


def pad_path():
    """Centreline samples the pad shell is swept along, bottom to throat."""

    path = []
    straight = 26
    for i in range(straight):
        path.append(
            (
                spec.POST_Y,
                PAD_BOTTOM_Z + (spec.POST_TOP_Z - PAD_BOTTOM_Z) * i / straight,
                0.0,
            )
        )
    curved = 34
    low, high = 0.0, 1.0
    for _ in range(40):
        mid = 0.5 * (low + high)
        if neck_point(mid)[1] < PAD_TOP_Z:
            low = mid
        else:
            high = mid
    top_t = 0.5 * (low + high)
    for i in range(curved + 1):
        path.append(neck_point(top_t * i / curved))
    return path


def pad_shell(name, material):
    """The pole pad: a vinyl shell SWEPT along the pipe, swelling between its
    straps, drawn in at each one, rolled at the open bottom and cinched down
    onto the pipe at the top."""

    top_z = PAD_TOP_Z

    def radius_of(_index, z):
        radius = PAD_STRAP_R + PAD_BULGE
        for strap_z in PAD_STRAP_Z:
            # Gaussian cinch centred on each strap.
            d = (z - strap_z) / PAD_CINCH_WIDTH
            radius -= PAD_BULGE * 1.02 * math.exp(-d * d)
        # Roll the wrap over at the open bottom hem.
        edge = (z - PAD_BOTTOM_Z) / PAD_EDGE_ROLL
        if edge < 1.0:
            radius -= (1.0 - edge) ** 2 * 0.030
        # Close the throat onto the pipe over the last PAD_THROAT metres, so
        # the pad ends as a cinched collar rather than an open barrel with a
        # cone lid parked on it.
        throat = (top_z - z) / PAD_THROAT
        if throat < 1.0:
            s = max(throat, 0.0)
            s = s * s * (3.0 - 2.0 * s)
            # Bite INSIDE the pipe: a throat that stops 6 mm short leaves
            # a dark annular hole you can see straight down into.
            closed = spec.POST_RADIUS - 0.003
            radius = closed + (radius - closed) * s
        return max(radius, 0.05)

    return sweep_tube(
        name,
        pad_path(),
        radius_of,
        material,
        uv=(PAD_TILE, PAD_TILE),
    )


def add_flag_cloth(cage: bk.CageBuilder, side: str, mounts: list[str]) -> None:
    """Soft-body cloth for one directional flag.

    This is BeamNG's own flag recipe (``vehicles/utv/utv_flags.jbeam``),
    which is the only way a prop reacts to wind CORRECTLY: the engine
    broadcasts ground wind to every spawned vehicle via ``obj:setWind``,
    the solver derives drag and lift from (wind - node velocity) on each
    TRIANGLE, and the cloth streams on its own. A posed rigid flag can
    only ever be an animation that ignores the actual air.

    The numbers are stock: gram-scale nodes on ``|NM_CLOTH``, stiff-ish
    structural beams, near-zero-stiffness diagonals so the sheet folds
    instead of behaving like a panel, and ``dragCoef`` on the triangles —
    cloth with no triangles is invisible to the air.
    """

    sample = flag_surface(side)
    nodes: dict[tuple[int, int], str] = {}
    for row in range(FLAG_ROWS):
        s = row / (FLAG_ROWS - 1)
        for col in range(FLAG_COLS):
            w = col / (FLAG_COLS - 1) - 0.5
            nodes[(row, col)] = cage.add_node(
                f"flag{side}_{row}_{col}",
                tuple(sample(s, w)),
                # Row 0 is the spring hook: held by the upright.
                fixed=(row == 0),
                collision=False,
                weight=0.001 if row else 0.6,
                node_material="|NM_CLOTH",
                group=f"flag_{side}",
            )
    # Tie the held row to the upright tip. Both ends are fixed nodes, so
    # these carry no load — they exist because the cage must be ONE
    # connected graph and cloth would otherwise be an island.
    for col in range(FLAG_COLS):
        for mount in mounts:
            cage.add_beam(nodes[(0, col)], mount)
    for row in range(FLAG_ROWS):
        for col in range(FLAG_COLS):
            if row + 1 < FLAG_ROWS:
                cage.add_beam(nodes[(row, col)], nodes[(row + 1, col)], "cloth_weave")
            if col + 1 < FLAG_COLS:
                cage.add_beam(nodes[(row, col)], nodes[(row, col + 1)], "cloth_weave")
            if row + 1 < FLAG_ROWS and col + 1 < FLAG_COLS:
                cage.add_beam(
                    nodes[(row, col)], nodes[(row + 1, col + 1)], "cloth_shear"
                )
                cage.add_beam(
                    nodes[(row, col + 1)], nodes[(row + 1, col)], "cloth_shear"
                )
    # Aero surface — this is what the air actually acts on; cloth with no
    # triangles is invisible to the wind. SINGLE winding on purpose: the
    # solver already derives force from the flow on either face, so the
    # double-sided helper would just double the drag off stock's numbers.
    for row in range(FLAG_ROWS - 1):
        for col in range(FLAG_COLS - 1):
            cage.add_quad(
                [
                    nodes[(row, col)],
                    nodes[(row, col + 1)],
                    nodes[(row + 1, col + 1)],
                    nodes[(row + 1, col)],
                ],
                ground_model="rubber",
                extra={"dragCoef": FLAG_DRAG_COEF},
            )


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    # Flag cloth beam specs (stock utv_flags numbers): the weave holds the
    # sheet together, the shear diagonals are essentially free so it can
    # fold and twist like textile rather than flexing like a plate.
    cage.define_beam_spec(
        "cloth_weave",
        beamSpring=1000.0,
        beamDamp=0.1,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "cloth_shear",
        beamSpring=0.25,
        beamDamp=0.05,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )

    # Field patch: fixed lattice up to FINISH GRADE, walkable turf top,
    # refnode home. The collision now matches the built-up soil/sod, not
    # the old exposed concrete slab.
    slab = cage.add_box_lattice(
        "slab",
        (-SLAB_HALF, spec.POST_Y - SLAB_HALF, 0.0),
        (SLAB_HALF, spec.POST_Y + SLAB_HALF, GRADE_Z),
        subdivisions=(2, 2, 1),
        fixed=True,
        collision=False,
        collision_faces=("top",),
        face_ground_models={"top": "grass"},
    )

    # Pedestal pad: octagonal prism hugging the vinyl pad (mid-face
    # distance 0.268 m vs the 0.27 m pad surface).
    ring: dict[tuple[int, int], str] = {}
    for k in range(8):
        angle = math.radians(22.5 + k * 45.0)
        px = 0.29 * math.cos(angle)
        py = spec.POST_Y + 0.29 * math.sin(angle)
        for level, z in ((0, GRADE_Z), (1, 1.95)):
            ring[(k, level)] = cage.add_node(
                f"padring_{k}_{level}",
                (px, py, z),
                fixed=True,
                collision=True,
                weight=110.0,
            )
    pad_top_c = cage.add_node(
        "pad_top_c", (0.0, spec.POST_Y, 1.95), fixed=True, collision=True, weight=110.0
    )
    for k in range(8):
        nxt = (k + 1) % 8
        cage.add_beam(ring[(k, 0)], ring[(k, 1)])
        for level in (0, 1):
            cage.add_beam(ring[(k, level)], ring[(nxt, level)])
        cage.add_beam(ring[(k, 0)], ring[(nxt, 1)])
        cage.add_quad_both(
            [ring[(k, 0)], ring[(nxt, 0)], ring[(nxt, 1)], ring[(k, 1)]],
            ground_model="rubber",
        )
    for k in (0, 2, 4, 6):
        cage.add_beam(pad_top_c, ring[(k, 1)])
        cage.add_quad_both(
            [ring[(k, 1)], ring[(k + 1, 1)], ring[((k + 2) % 8, 1)], pad_top_c],
            ground_model="rubber",
        )

    # --- Gooseneck: collision SWEPT ALONG THE BEZIER --------------------
    # This was two hand-placed volumes left over from when the neck was two
    # elbows and a straight run: a vertical box at the pedestal's y from
    # z 1.95 to 2.62, and a flat slab at z 2.35 under the horizontal run.
    # The sweep was rebuilt as one Bezier long ago and nothing followed it
    # here, so collision and geometry had drifted a very long way apart —
    # measured, not guessed:
    #
    #     z=1.95  pipe centre y=2.285   box front face y=2.308   0.11 m out
    #     z=2.30  pipe centre y=1.619                            0.77 m out
    #     z=2.62  pipe centre y=0.460                            1.93 m out
    #
    # i.e. above the pad the box stood in open air while the actual pipe
    # curved away in front of it, and the slab was up to 0.23 m off the
    # pipe it was meant to represent. A car met the gooseneck by passing
    # through it in some places and hitting nothing in others.
    #
    # Sampling the same neck_curve() the visual sweep uses costs 12 more
    # nodes and makes the two agree by construction: change the curve and
    # the collision follows it, which is the whole point.
    NECK_CAGE_STATIONS = 7
    NECK_CAGE_HALF = spec.POST_RADIUS + 0.02   # a little proud of the paint
    neck_ring: dict[tuple[int, int], str] = {}
    for station in range(NECK_CAGE_STATIONS):
        t = station / (NECK_CAGE_STATIONS - 1)
        y, z, angle = neck_point(t)
        # Offset perpendicular to the centreline, in the y-z plane.
        oy, oz = math.cos(angle), -math.sin(angle)
        for ci, (sx, so) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1))):
            neck_ring[(station, ci)] = cage.add_node(
                f"neckswp_{station}_{ci}",
                (
                    sx * NECK_CAGE_HALF,
                    y + so * NECK_CAGE_HALF * oy,
                    z + so * NECK_CAGE_HALF * oz,
                ),
                fixed=True,
                collision=True,
                # 28 nodes replacing 12, so the per-node weight comes down to
                # match: 28 x 37 is the same 1,040 kg the box and slab
                # carried between them, and the prop's shipped mass does not
                # jump 920 kg for a change that is purely about where the
                # collision surface sits.
                weight=37.0,
            )
    for station in range(NECK_CAGE_STATIONS):
        for ci in range(4):
            nxt = (ci + 1) % 4
            cage.add_beam(neck_ring[(station, ci)], neck_ring[(station, nxt)])
            if station + 1 < NECK_CAGE_STATIONS:
                cage.add_beam(neck_ring[(station, ci)],
                              neck_ring[(station + 1, ci)])
                cage.add_beam(neck_ring[(station, ci)],
                              neck_ring[(station + 1, nxt)])
                cage.add_quad_both([
                    neck_ring[(station, ci)],
                    neck_ring[(station, nxt)],
                    neck_ring[(station + 1, nxt)],
                    neck_ring[(station + 1, ci)],
                ])
    # Cap the top ring so a car landing on the crown has something to hit.
    cage.add_quad_both([
        neck_ring[(NECK_CAGE_STATIONS - 1, 0)],
        neck_ring[(NECK_CAGE_STATIONS - 1, 1)],
        neck_ring[(NECK_CAGE_STATIONS - 1, 2)],
        neck_ring[(NECK_CAGE_STATIONS - 1, 3)],
    ])

    # Crossbar: thin fixed wall band at true tube height.
    bar_stations = (
        -spec.UPRIGHT_X,
        -spec.UPRIGHT_X / 2.0,
        0.0,
        spec.UPRIGHT_X / 2.0,
        spec.UPRIGHT_X,
    )
    bar: dict[tuple[int, int], str] = {}
    for i, x in enumerate(bar_stations):
        for k, z in ((0, spec.BAR_CENTER_Z - spec.BAR_RADIUS), (1, spec.CROSSBAR_TOP_Z)):
            bar[(i, k)] = cage.add_node(
                f"bar_{i}_{k}", (x, 0.0, z), fixed=True, collision=True, weight=90.0
            )
    for i in range(len(bar_stations)):
        cage.add_beam(bar[(i, 0)], bar[(i, 1)])
        if i + 1 < len(bar_stations):
            for k in (0, 1):
                cage.add_beam(bar[(i, k)], bar[(i + 1, k)])
            cage.add_beam(bar[(i, 0)], bar[(i + 1, 1)])
            cage.add_quad_both(
                [bar[(i, 0)], bar[(i + 1, 0)], bar[(i + 1, 1)], bar[(i, 1)]]
            )

    # Uprights: slender fixed columns so airborne cars clang off the tube
    # instead of sailing through it.
    up: dict[tuple[int, int, int], str] = {}
    for s, xc in ((0, -spec.UPRIGHT_X), (1, spec.UPRIGHT_X)):
        for ci, (dx, dy) in enumerate(
            ((-0.07, -0.07), (0.07, -0.07), (0.07, 0.07), (-0.07, 0.07))
        ):
            for level, z in ((0, spec.CROSSBAR_TOP_Z), (1, 8.4), (2, spec.UPRIGHT_TOP_Z)):
                up[(s, ci, level)] = cage.add_node(
                    f"upright_{s}_{ci}_{level}",
                    (xc + dx, dy, z),
                    fixed=True,
                    collision=True,
                    weight=80.0,
                )
        for ci in range(4):
            nxt = (ci + 1) % 4
            for level in (0, 1):
                cage.add_beam(up[(s, ci, level)], up[(s, ci, level + 1)])
                cage.add_beam(up[(s, ci, level)], up[(s, nxt, level + 1)])
                cage.add_quad_both(
                    [
                        up[(s, ci, level)],
                        up[(s, nxt, level)],
                        up[(s, nxt, level + 1)],
                        up[(s, ci, level + 1)],
                    ]
                )
            for level in (0, 1, 2):
                cage.add_beam(up[(s, ci, level)], up[(s, nxt, level)])
        cage.add_quad_both(
            [up[(s, 0, 2)], up[(s, 1, 2)], up[(s, 2, 2)], up[(s, 3, 2)]]
        )

    # Stitch every cluster into one connected graph.
    for k in (0, 2, 4, 6):
        cage.add_beam(slab[(1, 1, 1)], ring[(k, 0)])
    # The pad's top ring hands off to the sweep's FIRST station, and the
    # sweep's LAST station lands on the crossbar's centre node. The two
    # beams that used to join the vertical box to the horizontal slab are
    # gone with them — the swept ring chain is already continuous.
    for k, ci in ((1, 1), (3, 2), (5, 3), (7, 0)):
        cage.add_beam(ring[(k, 1)], neck_ring[(0, ci)])
    cage.add_beam(pad_top_c, neck_ring[(0, 0)])
    cage.add_beam(pad_top_c, neck_ring[(0, 2)])
    for ci in range(4):
        cage.add_beam(neck_ring[(NECK_CAGE_STATIONS - 1, ci)], bar[(2, 0)])
    for ci in range(4):
        cage.add_beam(bar[(0, 1)], up[(0, ci, 0)])
        cage.add_beam(bar[(4, 1)], up[(1, ci, 0)])
    cage.add_beam(bar[(0, 0)], up[(0, 0, 0)])
    cage.add_beam(bar[(4, 0)], up[(1, 1, 0)])

    # Directional flag cloth, hung off the upright tips.
    for flag_side, s in (("l", 0), ("r", 1)):
        add_flag_cloth(
            cage, flag_side, [up[(s, ci, 2)] for ci in range(4)]
        )

    cage.set_refnodes_existing(
        ref=slab[(1, 1, 0)],
        back=slab[(1, 0, 0)],
        left=slab[(0, 1, 0)],
        up=slab[(1, 1, 1)],
    )
    cage.set_spawn_envelope(
        [
            slab[(0, 0, 0)],
            slab[(2, 0, 0)],
            slab[(0, 2, 0)],
            slab[(2, 2, 0)],
            up[(0, 0, 2)],
            up[(0, 3, 2)],
            up[(1, 1, 2)],
            up[(1, 2, 2)],
        ]
    )
    cage.auto_base_nodes()
    return cage


def build_studio_stage():
    """Studio stage for the shipped presentation art, and its camera.

    Same recipe as the boot's: the shared kit's thumbnail helper renders one
    flat sun against a flat sky, which reads as a grey snapshot next to the
    stock selector cards. Stock BeamNG previews are studio shots — subject
    filling the frame on a seamless cyclorama, key/fill/rim, soft contact
    shadow — so this builds that stage.

    Destructive to the scene (replaces the world, adds lights and a floor),
    so everything that calls it runs after the exports.
    """

    import bmesh
    import bpy

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    scene.render.film_transparent = False
    if hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 128
    # THE WASHED-CARD FIX. Blender 4.x tonemaps through AgX by default, which
    # desaturates saturated paint and lifts the floor toward white — the goal
    # post's safety yellow came out cream and the stage came out milk, and no
    # amount of light or backdrop tuning moved it, because the tonemapper was
    # doing the damage after the fact. Standard is 1:1, so the yellow on the
    # card is the yellow in the palette. Light energies below are set for it.
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"

    world = bpy.data.worlds.new("selector_world")
    scene.world = world
    world.use_nodes = True
    tree = world.node_tree
    for node in list(tree.nodes):
        if node.type != "OUTPUT_WORLD":
            tree.nodes.remove(node)
    output = tree.nodes["World Output"]
    tex_co = tree.nodes.new("ShaderNodeTexCoord")
    separate = tree.nodes.new("ShaderNodeSeparateXYZ")
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    background = tree.nodes.new("ShaderNodeBackground")
    tree.links.new(tex_co.outputs["Window"], separate.inputs["Vector"])
    tree.links.new(separate.outputs["Y"], ramp.inputs["Fac"])
    tree.links.new(ramp.outputs["Color"], background.inputs["Color"])
    tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    # DARKER than the boot's stage, on purpose. This subject is a lattice of
    # thin painted tubes, not a solid mass: on the boot's light-grey
    # cyclorama the safety yellow washed out to cream and the card read as a
    # pale wire sketch. Dropping the backdrop and the floor two stops makes
    # the paint the brightest thing in frame, which is the only way an
    # outline silhouette carries a 500x281 card.
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.33, 0.355, 0.395, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.085, 0.10, 0.125, 1.0)

    for name, kind, energy, size, location, rotation in (
        # Modest energies, because Standard clips at 1.0 with nothing to
        # roll the highlights off: the first pass at these levels burned a
        # white pool into the floor, frosted the grass tips and blew the
        # flags' satin sheen out to paper.
        ("sel_key", "SUN", 1.25, None, None, (54.0, 0.0, -142.0)),
        ("sel_fill", "AREA", 8000.0, 30.0, (-18.0, -24.0, 12.0), (56.0, 0.0, -36.0)),
        ("sel_rim", "AREA", 6500.0, 22.0, (12.0, 16.0, 11.0), (66.0, 0.0, 166.0)),
    ):
        data = bpy.data.lights.new(name, kind)
        data.energy = energy
        if kind == "SUN":
            data.angle = math.radians(6.0)
        else:
            data.size = size
        light = bpy.data.objects.new(name, data)
        if location is not None:
            light.location = location
        light.rotation_euler = tuple(math.radians(value) for value in rotation)
        scene.collection.objects.link(light)

    mesh = bpy.data.meshes.new("sel_floor")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=120.0)
    bm.to_mesh(mesh)
    bm.free()
    floor = bpy.data.objects.new("sel_floor", mesh)
    floor_material = bpy.data.materials.new("sel_floor_mat")
    floor_material.use_nodes = True
    shader = floor_material.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (0.215, 0.225, 0.245, 1.0)
    # Enough gloss to catch a soft reflection under the pad, which is what
    # grounds the prop; a fully matte floor lets it hover.
    shader.inputs["Roughness"].default_value = 0.62
    mesh.materials.append(floor_material)
    floor.location = (0.0, 0.0, -0.004)
    scene.collection.objects.link(floor)

    camera_data = bpy.data.cameras.new("sel_cam")
    camera = bpy.data.objects.new("sel_cam", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    return camera


def shoot(camera, path, *, azimuth, elevation, lens, fit_radius, target,
          resolution) -> None:
    """Orbit the studio camera and render.

    Azimuth 0 is +y (behind the post, the pedestal side); 180 is the field
    the kicker stands on. Distance solves the fit radius against the
    horizontal field of view, so changing the lens reframes instead of
    just cropping.
    """

    import bpy
    from mathutils import Vector

    scene = bpy.context.scene
    camera.data.lens = lens
    fov = 2.0 * math.atan(18.0 / lens)
    distance = fit_radius / math.tan(fov * 0.5) * 1.02
    a = math.radians(azimuth)
    e = math.radians(elevation)
    focus = Vector(target)
    camera.location = focus + Vector(
        (math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e))
    ) * distance
    camera.rotation_euler = (focus - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.resolution_x, scene.render.resolution_y = resolution
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


# Selector-card framings kept for comparison. Not shipped: they render into
# authoring/review/ so a framing change can be judged side by side instead of
# by memory of the last run.
CARD_CANDIDATES = (
    ("a_wide20", 202.0, -12.0, 20.0, 4.90, (0.0, 0.50, 2.85)),
    ("b_tight24", 203.0, -13.0, 24.0, 4.60, (0.0, 0.35, 3.05)),
    ("c_low18", 200.0, -15.0, 18.0, 5.10, (0.0, 0.45, 2.70)),
)


def render_presentation(camera) -> None:
    """The shipped selector card plus the beamng.com listing gallery.

    THE FRAMING PROBLEM this prop has and the boot did not: a goal post is
    35 ft of upright over an 18 ft 6 in span, so fitting the whole thing
    into a 16:9 card leaves the subject a hairline down the middle — which
    is exactly what the old auto-thumbnail was. The card therefore frames
    the BUSINESS END from the field: turf, pad, gooseneck, crossbar and one
    end cap, with the uprights running out of the top of frame. Everything
    that was actually built reads at 500x281, and the silhouette is still
    unmistakably a goal post.

    The gallery keeps one establishing shot at full height and then goes
    close on the parts worth a screenshot.
    """

    # NEGATIVE elevation puts the camera BELOW the crossbar looking up. On a
    # subject this tall that is worth more than any amount of backing off:
    # perspective converges the uprights into the top corners, so a 16:9
    # card ends up full of goal post instead of full of sky.
    shoot(
        camera,
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        azimuth=203.0, elevation=-13.0, lens=24.0, fit_radius=4.60,
        target=(0.0, 0.35, 3.05), resolution=(500, 281),
    )
    gallery = AUTHORING_ROOT / "listing"
    # Clear it first. Renumbering a shot leaves the old file behind, and a
    # gallery folder is uploaded wholesale — 06_joint.jpg and 07_plate.jpg
    # survived a renumber and rode into the staging set as two extra,
    # months-stale shots that nothing would have flagged but the age check.
    if gallery.is_dir():
        for stale in gallery.glob("*.jpg"):
            stale.unlink()
    for name, azimuth, elevation, lens, fit_radius, target in CARD_CANDIDATES:
        shoot(
            camera, AUTHORING_ROOT / "review" / f"card_{name}.jpg",
            azimuth=azimuth, elevation=elevation, lens=lens,
            fit_radius=fit_radius, target=target, resolution=(500, 281),
        )
    for name, azimuth, elevation, lens, fit_radius, target in (
        # Establishing: the whole H, flag tips to turf. The fit has to cover
        # 13.72 m of height, which at 16:9 means 13.72/2*16/9 = 12.2 m of
        # horizontal fit MINIMUM — the first pass used 12.6 around a centre
        # 0.6 m too low and guillotined the flags.
        ("01_goal", 206.0, 12.0, 50.0, 13.6, (0.0, 1.10, 6.90)),
        ("02_crossbar", 203.0, -13.0, 24.0, 4.60, (0.0, 0.35, 3.05)),
        ("03_base", 196.0, 8.0, 46.0, 1.30, (0.0, 2.20, 0.72)),
        # Azimuth 90 is +x, so the cap face needs a camera OUTBOARD of the
        # bar end: at 232 the camera sat inboard and shot the bar's flank.
        ("04_end_cap", 106.0, 5.0, 85.0, 0.13, (3.014, 0.0, 2.985)),
        # The flag lies nearly FLAT — it streams +y and droops, so its face
        # points mostly up. Shooting it from the side at 4 degrees showed
        # its edge and a wall of upright; it needs looking down on.
        # Framed from the MEASURED rest pose, after three guesses missed:
        # sampling the surface gives a mean face normal of
        # (-0.02, -0.645, -0.763) and a centre of (2.873, 0.494, 13.28).
        # Face-on to THAT side is azimuth 182 / elevation -50 — but the
        # upright stands between it and the camera, so shoot the opposite
        # face instead, from above and behind at azimuth 2 / elevation 50.
        # Fit 0.95 because a 1.07 m flag will not fit a 0.70 m frame height
        # at whatever angle it happens to lie on screen.
        ("05_flag", 2.0, 50.0, 50.0, 1.06, (2.873, 0.494, 13.25)),
        ("06_flag_mount", 318.8, 20.0, 55.0, 0.11, (2.8702, 0.10, 13.625)),
        ("07_joint", 208.0, 6.0, 70.0, 0.42, (2.87, 0.0, 3.14)),
        ("08_buckle", 161.3, 9.0, 55.0, 0.16, (0.0, 2.155, 0.94)),
        # Azimuth/elevation solved from the review camera that already
        # frames this plate, not guessed: at 250 the camera was round the
        # far side of the sweep and the shot was a wall of bare pipe.
        ("09_plate", 105.6, 10.4, 60.0, 0.125, (0.10, 1.24, 2.39)),
    ):
        shoot(
            camera,
            gallery / f"{name}.jpg",
            azimuth=azimuth, elevation=elevation, lens=lens,
            fit_radius=fit_radius, target=target, resolution=(1280, 720),
        )


def tab_review(review) -> None:
    """The two review shots the flag TAB never had.

    It is the part under scrutiny — it carries the only chamfer in this
    model that has to be cut by hand after a boolean — and every existing
    framing of it was a wider shot in which its two long arrises are a few
    pixels. Round 3 shipped 46 mm^2 of folded membrane down exactly those
    two arrises and no review render in the tree could have shown it.

    NOT bk.render_thumbnail, and not a change to it. That helper is fixed
    at a 32 mm lens and takes Blender's default 0.1 m near clip, so the
    closest legal framing of a 25 mm part still leaves it at a fifth of
    the frame. Three other mods take their whole review set through it and
    a lens argument there would be a proplib behaviour change. This is a
    local camera with a long lens and a near clip, aimed by the mount's
    own constants.

    The second framing is deliberately almost edge-on to the plate: a
    0.6 mm chamfer is a 45 degree facet and declares itself at a grazing
    angle or not at all.
    """

    import bpy
    from mathutils import Vector

    scene = bpy.context.scene
    # The plate runs from the eye's bottom (BORE_Z - EYE_R) to the shank's
    # top (BORE_Z + 20.9 mm), so its middle is 8 mm above the bore, not at
    # it. Aiming at the bore put a third of the frame on empty sky.
    target = Vector((spec.UPRIGHT_X, FLAG_TAB_Y, FLAG_BORE_Z + 0.008))
    sun_data = bpy.data.lights.new("tab_sun", "SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("tab_sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = Vector((-0.4, 0.35, -1.0)).to_track_quat(
        "-Z", "Y").to_euler()
    world = bpy.data.worlds.new("tab_world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (
        0.72, 0.82, 0.92, 1.0)
    scene.world = world
    previous = scene.camera
    # 135 mm over a 27 mm-tall frame is an 11.4 degree vertical field, so a
    # 45 mm subject wants 0.225 m of stand-off. Both offsets are that long;
    # the first is square to the plate's +Y face, the second swung 55
    # degrees outboard so the light rakes across the same two arrises.
    for name, offset, lens in (
        ("tab", Vector((0.060, 0.215, 0.035)), 135.0),
        ("tab_raking", Vector((0.185, 0.128, 0.012)), 135.0),
    ):
        camera_data = bpy.data.cameras.new("tab_camera")
        camera_data.lens = lens
        camera_data.clip_start = 0.005
        camera = bpy.data.objects.new("tab_camera", camera_data)
        scene.collection.objects.link(camera)
        camera.location = target + offset
        camera.rotation_euler = (target - camera.location).to_track_quat(
            "-Z", "Y").to_euler()
        scene.camera = camera
        scene.render.resolution_x, scene.render.resolution_y = 640, 480
        scene.render.filepath = str(review / f"{MOD_ID}_{name}.jpg")
        bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(camera, do_unlink=True)
        bpy.data.cameras.remove(camera_data)
    scene.camera = previous
    bpy.data.objects.remove(sun, do_unlink=True)
    bpy.data.lights.remove(sun_data)


def assert_no_dead_constants() -> int:
    """Fail the build on any module-level constant that is never read.

    THE FOURTH TIME IS A TEST, NOT A COMMENT. FLAG_EAR_REACH, FLAG_LINK_DROP
    and FLAG_HEADER_H were each a number written into this file that nothing
    ever asked for, and each one described a part of the mount that had
    stopped existing. A constant with no reader is not dead weight, it is a
    claim about the geometry that no longer has to be true — which is
    exactly how the prose here drifted three names ahead of the code.

    Reads this file's own source with `ast` rather than grepping, so a name
    that survives only in a comment or a docstring still counts as dead:
    the round-4 audit found FLAG_HEADER_H by grep and had to argue about
    whether its four prose mentions counted. They do not.

    THREE LIMITS OF THIS CHECK, measured round 5. Do not widen it without
    reading them, because each one turns into a deleted live constant:

    1. IT AUDITS ONLY THIS FILE. `spec.py`'s 21 constants are not covered,
       and three of them — VALUE_DOLLARS, ZIP_BASENAME, LUA_BEHAVIOR — have
       their ONLY readers outside the mod directory entirely, in build.py,
       lua_kit.py and prop_builder.py. Point this at spec.py as written and
       it deletes all three. Any extension must parse the whole pack, not
       one file and not one directory.
    2. NO SCOPE ANALYSIS. `read` is every Load-context Name in the module,
       at any depth, so an UPPERCASE local or parameter anywhere in the file
       would mask a genuinely dead module constant. Nothing today does this;
       it is latent, not theoretical.
    3. A DEAD CHAIN SURFACES ONE LINK PER BUILD. Eight constants here are
       read only by other module-level assignments, so deleting a dead leaf
       can make its feeder dead, which only the NEXT run reports. Expect to
       run the build twice after any deletion.

    It handles f-strings correctly — `ast.walk` descends into FormattedValue
    — and there is no `globals()`/`getattr` indirection in this file, so a
    name that does not appear as a Load really is unread.

    ASSETS ARE THE SAME SPECIES AND ARE NOW IN SCOPE: see
    assert_no_orphan_textures() below. A texture family for a part that no
    longer exists is a dead constant with a file size — round 5 found and
    deleted `ribbon_orange`'s three PNGs, authored 2026-08-13 for a part
    removed before the first build, never in the mod tree or the ZIP, and
    invisible to every check in this file because none of them look at
    disk.
    """

    import ast

    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    declared = {}
    for node in tree.body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign)
                   else [])
        for target in targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                declared.setdefault(target.id, target.lineno)
    read = {node.id for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    dead = sorted((line, name) for name, line in declared.items()
                  if name not in read)
    assert not dead, (
        "constants written and never read (delete them or use them): "
        + ", ".join(f"{name} at line {line}" for line, name in dead)
    )
    return len(declared)


# Suffixes prop_builder appends to a material name when it writes a map.
TEXTURE_SUFFIXES = (".color.png", ".normal.png", "_roughness.data.png",
                    "_opacity.data.png", "_metallic.data.png", "_ao.data.png")


def assert_no_orphan_textures() -> int:
    """Fail the build on a texture file no palette entry can claim.

    THE DEAD CONSTANT'S TWIN, IN MEGABYTES. `ribbon_orange`'s three PNGs
    sat in `textures/` from 2026-08-13 to round 5: authored for a part that
    was cut before the first build, never copied into the mod tree, never
    in the ZIP, and unreachable by every check in this file because all of
    them read source and none of them read disk. Same species as
    FLAG_HEADER_H — an asset with no reader is a claim that a part exists.

    Deliberately one-directional. It fails on a file the palette cannot
    account for; it does NOT fail on a palette entry with no file yet,
    because prop_builder writes those on demand and a clean tree is the
    normal state before the first run.
    """

    known = set()
    for name in spec.PALETTE:
        for suffix in TEXTURE_SUFFIXES:
            known.add(f"{name}{suffix}")
    directory = EXAMPLE_ROOT / "textures"
    if not directory.is_dir():
        return 0
    present = sorted(path.name for path in directory.glob("*.png"))
    orphans = [name for name in present if name not in known]
    assert not orphans, (
        "texture files no palette entry claims (delete them or add the "
        "material): " + ", ".join(orphans)
    )
    return len(present)


def record_toolchain(handoff_path: Path, handoff: dict) -> dict:
    """Stamp what BUILT this artifact into the handoff, beside what it IS.

    The handoff already pins the output: a sha256 of the DAE. That number
    can tell you two artifacts differ. It cannot tell you WHY, because
    nothing in the tree recorded the code that produced either of them —
    and `proplib/` is untracked in git, so there is not even a revision
    to name. See the module docstring: on the serial-28 artifact both
    shared modules post-dated the ZIP by a quarter of an hour and there
    was no way, afterwards, to say what had changed in them.

    So: generator, spec and every proplib module, hashed. This does not
    make the PREVIOUS artifact checkable — nothing can, that evidence is
    gone — it makes the next one checkable, and it makes a library edit
    between two builds visible in the diff instead of invisible.

    Written back over `write_handoff`'s own output with its exact
    serialisation (indent=2, sort_keys, trailing newline, LF), so the
    file stays byte-identical across re-runs of an unchanged toolchain.
    """

    def digest(path: Path) -> dict:
        data = path.read_bytes()
        return {"sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data)}

    proplib_dir = PACK_ROOT / "proplib"
    handoff["toolchain"] = {
        "generator": {"path": f"{SCRIPT_PATH.name}", **digest(SCRIPT_PATH)},
        "spec": {"path": "spec.py", **digest(EXAMPLE_ROOT / "spec.py")},
        "proplib": {
            module.name: digest(module)
            for module in sorted(proplib_dir.glob("*.py"))
        },
    }
    handoff_path.write_text(
        json.dumps(handoff, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return handoff["toolchain"]


def main() -> None:
    print(f"    {assert_no_dead_constants()} module constants, all read")
    print(f"    {assert_no_orphan_textures()} texture files, all claimed")
    bk.reset_scene()
    materials = build_materials()
    visual_objects = build_visual(materials)

    # Each flag is its own flexbody bound to its own cloth node group, so
    # the solver deforms the render mesh directly. Binding both flags into
    # one mesh would skin each flag to the other's nodes.
    cloth = materials[f"{MOD_ID}_flag_cloth"]
    steel = materials[f"{MOD_ID}_steel"]
    mesh_groups = {f"{MOD_ID}_visual": visual_objects}
    for side in ("l", "r"):
        xc = -spec.UPRIGHT_X if side == "l" else spec.UPRIGHT_X
        # The eyelet rides in this group, not in the static visual: a
        # flexbody group may carry several materials (export_multi_flexbody
        # joins them and keeps every slot), so brass hardware set in the
        # cloth deforms with the cloth instead of hanging in the air.
        mesh_groups[f"{MOD_ID}_flag_{side}_mesh"] = [
            flag_mesh(f"{MOD_ID}_flag_{side}", cloth, side),
            *flag_grommet(f"{MOD_ID}_flag_grommet_{side}", side, xc, steel),
        ]

    visual = bk.export_multi_flexbody(
        MOD_ID, VEHICLE_DIR / f"{MOD_ID}.dae", mesh_groups
    )
    # Immediately after the export and before anything else touches the
    # scene: every group that just shipped, measured the way it shipped.
    # export_multi_flexbody duplicates its inputs and deletes only the
    # joins, so mesh_groups is still live here.
    mesh_census(mesh_groups)

    cage = build_cage()
    behavior = dict(spec.BEHAVIOR)
    handoff_path = AUTHORING_ROOT / f"{MOD_ID}.handoff.json"
    handoff = bk.write_handoff(
        handoff_path,
        mod_id=MOD_ID,
        display_name=spec.DISPLAY_NAME,
        cage=cage,
        visual=visual,
        visual_dae_relative=f"vehicles/{MOD_ID}/{MOD_ID}.dae",
        visual_mesh_name=f"{MOD_ID}_visual",
        parts=[],
        palette=spec.PALETTE,
        behavior={
            "tunables": behavior,
            "triggers": spec.TRIGGERS,
            "effects": spec.EFFECTS,
            "camera_distance": behavior.get("camera_distance", 30.0),
        },
        flexbodies_extra=[
            {"mesh": f"{MOD_ID}_flag_{side}_mesh", "groups": [f"flag_{side}"]}
            for side in ("l", "r")
        ],
    )
    toolchain = record_toolchain(handoff_path, handoff)
    print(f"    toolchain: generator {toolchain['generator']['sha256'][:12]}, "
          f"{len(toolchain['proplib'])} proplib modules hashed")
    # Review renders: close-up evidence for the detail passes (not shipped).
    review = AUTHORING_ROOT / "review"
    for name, camera_location, look_at in (
        ("base", (1.5, 1.05, 0.62), (0.0, 2.44, 0.30)),
        ("base_wide", (2.6, -0.6, 1.1), (0.0, 2.35, 0.9)),
        # Grass judged from a driver's eye height and from a low grazing
        # angle, which is where flat turf betrays itself.
        ("grass_eye", (1.55, 0.62, 1.18), (0.15, 2.30, 0.40)),
        ("grass_graze", (0.95, 0.98, 0.435), (0.0, 2.60, 0.395)),
        ("grass_edge", (1.35, 1.30, 0.52), (0.30, 1.95, 0.36)),
        ("tee", (2.4, -2.6, 2.4), (0.0, 0.6, 2.9)),
        # Square onto the crossbar's end cap, where the die-struck mark is.
        ("bar_cap", (3.27, -0.09, 3.03),
         (BAR_HALF_LENGTH + BAR_CAP_T / 2.0, 0.0, spec.BAR_CENTER_Z)),
        # Oblique, so the cap's RIM BAND is in shot: the angle the wrapped
        # logo showed up at, and the only angle that proves it is gone.
        ("bar_cap_oblique", (3.30, -0.26, 2.90),
         (BAR_HALF_LENGTH + BAR_CAP_T / 2.0, 0.0, spec.BAR_CENTER_Z)),
        # The pad's side-release buckle, straight on and then raking.
        ("buckle", (0.10, 1.86, 0.99), (0.0, 2.155, 0.94)),
        ("buckle_raking", (0.14, 1.94, 0.83), (0.0, 2.155, 0.94)),
        # The 1/4-20 ties up the upright. They moved to the +Y face on
        # 2026-08-15, and these two cameras moved with them — a review
        # shot left on the old face photographs bare paint and quietly
        # stops being evidence of anything.
        ("tie_bolts", (2.87, 0.42, 3.20), (2.87, 0.0508, 3.19)),
        ("tie_bolt_close", (2.845, 0.185, 3.145), (2.87, 0.0508, 3.129)),
        # The last joint in the hardware chain: hook wire through the
        # grommet. ("Chain" here is the chain of derivations, not the
        # chain LINK the owner had deleted -- that word is retired as
        # hardware on this mount.)
        # Framed OFF flag_anchor rather than off a literal. The old target
        # was flag_anchor's value on the day it was typed, so re-hanging
        # the hook on different hardware would have walked this shot off
        # the grommet without anything failing.
        ("grommet",
         tuple(a + d for a, d in zip(flag_anchor("r"), (-0.070, 0.080, 0.040))),
         flag_anchor("r")),
        # The tee at reading distance: the bore, the two opposed 8 in
        # through-bolts and the end plate with its pair of flange bolts.
        ("tee_close", (0.62, -0.66, 3.28), (0.0, 0.02, 3.02)),
        ("tee_under", (0.55, -0.62, 2.66), (0.0, 0.05, 3.00)),
        # The builder's plate, on the +x flank of the sweep.
        # The flag mount is on the +Y face, so it needs a camera from
        # behind the upright — a field-side view only ever sees the tube.
        # Framed OFF the mount's own constants, for the reason the grommet
        # shot is: these two were literals aimed at where the hardware sat
        # the day they were typed, and the 2026-08-15 re-hang dropped the
        # ring 13 mm past them. A review shot that no longer contains the
        # thing it is named after is worse than no review shot.
        # ...and pulled in to half the old stand-off, because the hardware
        # they photograph is now a 55 mm mount instead of a 90 mm one and
        # at the old distance it was a smudge in the middle of the frame.
        ("flag_mount", (spec.UPRIGHT_X + 0.125, FLAG_TAB_Y + 0.163,
                        FLAG_BORE_Z + 0.035),
         (spec.UPRIGHT_X, FLAG_TAB_Y, FLAG_BORE_Z - 0.008)),
        ("flag_mount_side", (spec.UPRIGHT_X, FLAG_TAB_Y + 0.195,
                             FLAG_BORE_Z - 0.020),
         (spec.UPRIGHT_X, FLAG_TAB_Y, FLAG_BORE_Z - 0.008)),
        # (The TAB's own two shots are NOT in this list -- see
        # tab_review() below. bk.render_thumbnail is fixed at a 32 mm lens
        # and Blender's default 0.1 m near clip, so the closest legal
        # framing of a 25 mm part still puts it at a fifth of the frame,
        # which is the same not-looking that round 3 was pulled up for.)
        ("decal", (0.78, 1.05, 2.52), (0.10, 1.24, 2.39)),
        ("splice", (2.40, -0.52, 8.45), (2.87, -0.02, 8.38)),
        # Looking DOWN on the upright joint: the two 3/8 crown bolts only
        # exist for this view, since from field level the bar's crown is
        # never visible.
        ("joint_top", (2.62, -0.42, 3.62), (2.90, 0.0, 3.05)),
        ("pad_top", (1.30, 0.95, 2.24), (0.10, 2.10, 1.80)),
        ("tip", (2.45, -0.52, 13.80), (2.87, -0.10, 13.62)),
        # The flag now hangs off the FIELD side and streams -Y with its
        # face roughly level, so look down onto it from above and outboard.
        ("flag", (1.86, 0.46, 13.94), (2.87, 0.55, 13.36)),
        ("flag_back", (2.25, -0.30, 13.05), (2.88, -0.60, 13.45)),
        ("stub", (2.35, -0.62, 3.34), (2.90, 0.0, 3.06)),
        ("stub_wide", (1.9, -1.2, 3.45), (2.90, 0.0, 3.10)),
        ("neck", (3.4, -1.8, 1.9), (0.0, 1.6, 2.4)),
    ):
        bk.render_thumbnail(
            review / f"{MOD_ID}_{name}.jpg",
            camera_location=camera_location,
            look_at=look_at,
            resolution=(640, 480),
        )
    tab_review(review)
    # Last, and in this order: the studio stage replaces the world and adds
    # a floor, so nothing that exports or measures may run after it.
    render_presentation(build_studio_stage())
    print("FOOTBALL_GOAL_POST generator complete")


if __name__ == "__main__":
    main()
