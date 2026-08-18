"""Junk Chute Grinder Trap - authored constants for Blender + runtime.

A scrapyard twin-shaft shredder at giant scale. A 20% haul ramp climbs to an
open feed hopper; the deck crests over a 12 m parabolic vertical curve and the
floor steepens into a 35% chute that ends tangent to the crowns of two
counter-rotating toothed rollers. Nose over the lip and the teeth take the car:
it is dragged down through the 2.9 m nip at the rollers' own surface speed,
juddered at the tooth-pass rate, scrubbed alternately against each rotor
shroud, released as it clears the drums and dropped onto the slat discharge
conveyor, which carries the wreck out onto the scrap pile.

The grab is a velocity servo, not a teleport. Every frame the runtime
evaluates the exact surface-velocity field of the two drums at the car's own
azimuth about each drum axis, and drives the car's velocity toward it with a
first-order gain and a hard per-frame dv cap. The pull magnitude IS
omega * ROLL_CAGE_R - the radius of the surface the car is actually resting
on - recomputed from the CURRENT omega, so the visible roller speed and the
felt pull can never disagree, including while the drive bogs down under load
and while the anti-jam auto-reverse runs. (The hook tips, 15% further out,
overspeed that contact surface by 15%: which is exactly what a cutting tooth
does, and is where the scrub comes from.)

Frames and laws this file relies on (see AGENTS.md "Prop authoring field
guide"):

- Authored frame is right-handed, meters, Z-up, +Y = drive direction. The
  world renders authored (x, y) at (-x, -y); points and directions pushed
  through toWorldPoint/toWorldDir survive that flip unchanged.
- setPartPose() applies its quaternion in WORLD space (proplib composes
  ``rotation * state.modelRotation``, and the shipped play-tested precedents -
  catapult_seesaw's X hinge, monster_flyswatter's Y hinge, both 2026-07-23 -
  prove the authored X and Y axes come out MIRRORED). This build does not
  carry a hand-typed mirror sign at all: every spin axis is pushed through
  ``toWorldDir(state, B.spin_axis_*)`` first, which maps the AUTHORED axis to
  its world image. At identity yaw that reduces to exactly the -1 the two
  precedents measured (the model alignment is 180 deg about Z, so authored +Y
  -> world -Y, authored +Z -> world +Z), and unlike a typed sign it is still
  correct when the prop is spawned on a heading other than north - the case
  AGENTS.md warns an identity-yaw test cannot distinguish.
"""

import math

MOD_ID = "ericrolph_junk_chute_grinder"
DISPLAY_NAME = "Junk Chute Grinder Trap"
VALUE_DOLLARS = 47000
ZIP_BASENAME = "junk_chute_grinder_ericrolph.zip"

# ---------------------------------------------------------------------------
# Reference vehicle. Every clearance below is derived from these three
# numbers (a BeamNG compact); wide-body pickups run ~2.3 m so the tight
# dimensions carry a note saying what they leave for one.
# ---------------------------------------------------------------------------
CAR_WIDTH = 2.0
CAR_LENGTH = 4.5
CAR_HEIGHT = 1.5
# Longest wheelbase the drive-in geometry is checked against (a BeamNG
# pickup/van). The build-time crest gate sweeps 2.30 / 2.70 / 3.20 / 3.60 m.
CAR_WHEELBASE_MAX = 3.60

# ---------------------------------------------------------------------------
# Shredder core.
#
# Roller axes run FORE-AFT (+/-Y), so the nip is a long slot the car enters
# lengthwise. This is the whole reason the machine is reliable: the only
# dimension that has to clear is the car's WIDTH (2.0 m). With cross-lane
# axes the binding dimension would be the car's pitched-over length, which
# needs 2.6 m of nip at 75 deg nose-down and 3.6 m at 60 deg - a lottery the
# player loses whenever the car goes in flat.
# ---------------------------------------------------------------------------
# Two radii, and which one is which matters more than any other pair of
# numbers in this file.
#
#   ROLL_CAGE_R  the CONTACT surface: the cutter-disc rim. This is the
#                collision cylinder, the radius the pull speed is computed
#                from, and the radius the nip clearance is measured to.
#   ROLL_TIP_R   the HOOK TIP: purely visual, 0.15 m proud of the contact
#                surface. It is also the datum every fixed part of the hopper
#                is built to clear, because it is what actually sweeps.
#
# Round-1 review measured the old build, which put the collision skin on the
# tooth-tip circle: ~40% of that skin had no visible solid until r = 0.62 -
# half a metre of air - and the thumbnail showed daylight between the tooth
# rows. Moving the skin down to the disc rim fixes both halves at once: the
# continuous disc solids are exactly flush with it, and the hooks stand
# 0.15 m PROUD of it, so when the scrub presses a car onto a shroud the body
# stops at r = 1.00 while the hook tips are already 0.15 m inside its flank -
# teeth visibly biting in, and erring on the safe side (the car is held off
# by the disc rim, never speared by a tooth that has no collision).
ROLL_CAGE_R = 1.00
ROLL_TIP_R = 1.15  # -> 2.30 m swept hook circle, giant-machine scale
ROLL_AXIS_Z = 4.05
# 2.90 m clear nip = 2.0 m car + 0.45 m each side, measured to the COLLISION
# surface. A 2.3 m pickup still clears by 0.30 m per side. Anything narrower
# starts wedging bodywork. The hook tips sweep to a 2.60 m gap.
NIP_HALF = 1.45
ROLL_AXIS_X = NIP_HALF + ROLL_CAGE_R  # 2.45: disc rims just touch the nip line
ROLL_TOP_Z = ROLL_AXIS_Z + ROLL_CAGE_R  # 5.05 collision crown
ROLL_BOT_Z = ROLL_AXIS_Z - ROLL_CAGE_R  # 3.05 collision underside
TIP_TOP_Z = ROLL_AXIS_Z + ROLL_TIP_R  # 5.20: the hopper's build datum
SLOT_HALF_Y = 5.0  # 10 m slot: swallows a 4.5 m car with 2.75 m at each end
TOOTH_ROWS = 10  # cutter discs on a 1.00 m pitch
TEETH_PER_ROW = 6  # 6 hooks/rev -> tooth-pass 1.43 Hz at working speed
TOOTH_STAGGER_DEG = 30.0  # half a hook pitch, so discs interleave like a real rotor

# --- rotor solids ----------------------------------------------------------
# A real twin-shaft rotor is a stack of thick hooked cutter discs separated by
# narrow grooves that the fixed cleaning combs run in. Built that way, the
# worst-case air behind the collision skin is ROLL_CAGE_R - ROLL_SPACER_R =
# 0.10 m over the 38% of the length that is groove, and exactly ZERO over the
# 62% that is disc. build_parts() re-measures both that number and the swept
# hook envelope with a headless raycast over the BUILT mesh and asserts them,
# so neither claim can rot.
CUTTER_DISC_R = ROLL_CAGE_R  # flush with the collision skin by construction
CUTTER_DISC_T = 0.62  # 62% of the 1.00 m row pitch is solid disc
ROLL_SPACER_R = 0.90  # comb groove floor: 0.10 m inside the skin
ROLL_SPACER_T = 0.38
ROLL_BARREL_R = 0.62  # hidden shaft barrel; blocks any see-through line
# Hooks: 6 on each disc rim, tip on the sweep circle, as wide as the disc so
# the comb grooves stay clear. The generator asserts the swept corner radius
# stays inside ROLL_TIP_R + 0.02, because the chute lip and the hopper flank
# base are built exactly ON that circle.
HOOK_ROOT_R = CUTTER_DISC_R
HOOK_TIP_R = ROLL_TIP_R
HOOK_TANGENTIAL = 0.30
HOOK_AXIAL = CUTTER_DISC_T

# ---------------------------------------------------------------------------
# Feed chute. The floor ENDS tangent to the SWEPT hook circle: the leading
# edge sits at exactly TIP_TOP_Z and exactly at ROLL_AXIS_X, so the chute edge
# lands on the sweep circle by construction, not by tuning (the centrifuge's
# "a straight-ended box can never meet a circular lip" lesson). Everything
# fixed that borders the rotor - chute lip, hopper flank base, hopper back
# plate - is built to the SWEPT circle, so a hook can never clip through it;
# the collision skin sits 0.15 m lower, which is the step a car noses over as
# the teeth take it.
# ---------------------------------------------------------------------------
LIP_Y = -SLOT_HALF_Y  # -5.0
LIP_Z = TIP_TOP_Z  # 5.20
MOUTH_Y = -14.0
CHUTE_RUN = LIP_Y - MOUTH_Y  # 9.0 m of chute
# Grade is interpolated (smoothstep) and INTEGRATED, never blended between two
# height datums - the centrifuge crest bug. The result is monotone in grade
# and never steeper than 35% anywhere. Both numbers are MAGNITUDES of a
# DESCENDING grade; the signed convention used by the continuity gate is
# d(z)/d(y), i.e. -CHUTE_GRADE_MOUTH at the mouth.
CHUTE_GRADE_MOUTH = 0.20
CHUTE_GRADE_LIP = 0.35
CHUTE_HALF_LIP = ROLL_AXIS_X  # 2.45 -> 4.90 m wide at the lip
CHUTE_HALF_MOUTH = 4.30  # 8.60 m wide mouth: easy to aim at from the ramp


def chute_floor_z(y: float) -> float:
    """Chute floor height. s = 0 at the lip, 1 at the mouth."""

    s = min(1.0, max(0.0, (LIP_Y - y) / CHUTE_RUN))
    smooth_integral = s**3 - 0.5 * s**4  # integral of 3s^2-2s^3 from 0 to s
    return LIP_Z + CHUTE_RUN * (
        CHUTE_GRADE_LIP * s + (CHUTE_GRADE_MOUTH - CHUTE_GRADE_LIP) * smooth_integral
    )


def chute_half_width(y: float) -> float:
    """Half width of the chute floor; linear funnel, 10.7 deg per side."""

    s = min(1.0, max(0.0, (LIP_Y - y) / CHUTE_RUN))
    return CHUTE_HALF_LIP + (CHUTE_HALF_MOUTH - CHUTE_HALF_LIP) * s


MOUTH_Z = chute_floor_z(MOUTH_Y)  # 7.675

# ---------------------------------------------------------------------------
# Hopper. Open-topped; the side walls run at ~55 deg so anything that lands
# on one slides into the slot instead of parking on it. No vertical collision
# faces anywhere a car can reach (centrifuge "wall in orbit" law).
# ---------------------------------------------------------------------------
RIM_Z = 9.60
RIM_HALF_X = 5.60
# The back plate starts exactly where the flanks and the swept hook circle
# end, so its base line IS the hopper's rotor datum line and the cage can
# alias those nodes instead of rebuilding them (the coincident-node flexbody
# trap, AGENTS.md 2026-08-08).
BACK_BASE_Z = TIP_TOP_Z
BACK_RIM_Y = 8.60  # (9.60-5.20)/(8.60-5.00) -> 50.7 deg: scrap always slides

# ---------------------------------------------------------------------------
# Haul ramp. 20% constant grade with a smoothstep toe and a PARABOLIC CREST
# VERTICAL CURVE at the top.
#
# Why 20%: the centrifuge measured an automatic at creep throttle stalling and
# rolling back on a 23% CREST (AGENTS.md, round 14). This grade is monotone -
# the toe blend integrates the slope so the grade never exceeds 20% anywhere -
# and 20% leaves 3 points of margin against that measured failure.
#
# Why the crest curve (round-1 review blocker): the ramp arrives CLIMBING at
# +20% and the chute leaves DESCENDING at -20%. Butting them together at the
# mouth is a 22.6 deg breakover ridge across the full 8.6 m width, on the only
# path into the machine - a compact grounds out on the apex at creep and
# launches off it at speed. CREST_LEN is a true civil-engineering vertical
# curve: the GRADE is linear in y (so the profile is a parabola and dz/dy is
# continuous everywhere), the rate of grade change is a constant
# (RAMP_GRADE + CHUTE_GRADE_MOUTH) / CREST_LEN = 0.0333 per metre, and the
# resulting middle ordinate over a 3.60 m wheelbase is 0.0333 * 3.60^2 / 8 =
# 0.054 m - a third of a compact's belly clearance. The generator re-measures
# the number on the FACETED cage polyline (which is what the tyres actually
# touch) for four wheelbases and asserts it, and separately asserts that the
# two profile functions agree in SIGNED grade at the mouth. The old assert
# compared a +y forward difference on the ramp against a -y difference on the
# chute, so equal magnitudes across a sign flip - i.e. a crest - passed it.
#
# The curve is symmetric (+0.20 -> -0.20), so its net rise is zero: it costs
# exactly CREST_LEN of extra ramp and nothing else.
# ---------------------------------------------------------------------------
RAMP_GRADE = 0.20
RAMP_BLEND = 6.0  # toe blend length; nothing scrapes entering the climb
CREST_LEN = 12.0  # crest vertical curve, ENDS at the mouth
RAMP_HALF_W = CHUTE_HALF_MOUTH  # 4.30: deck width matches the mouth exactly
KERB_RUN = 1.05  # sloped kerb: 35.5 deg inner face, deflects, never trips
KERB_RISE = 0.75
SKIRT_ANGLE_DEG = 62.0  # embankment skirt from the kerb crest to grade

CREST_Y0 = MOUTH_Y - CREST_LEN  # -26.0: where the crest curve starts
# Net rise across the curve: integral of a grade that runs linearly from
# +RAMP_GRADE to -CHUTE_GRADE_MOUTH. Zero when the two are equal, but written
# out so the profile stays exact if either is ever retuned.
CREST_RISE = CREST_LEN * (RAMP_GRADE - CHUTE_GRADE_MOUTH) / 2.0
CREST_START_Z = MOUTH_Z - CREST_RISE  # 7.675
# Straight climb length, solved so the toe lands at exactly z = 0.
RAMP_STRAIGHT = (CREST_START_Z - RAMP_GRADE * RAMP_BLEND * 0.5) / RAMP_GRADE
RAMP_RUN = RAMP_BLEND + RAMP_STRAIGHT + CREST_LEN  # 53.375
TOE_Y = MOUTH_Y - RAMP_RUN


def ramp_deck_z(y: float) -> float:
    """Ramp deck height, integrated from a piecewise-continuous grade.

    Three segments, all C1 in grade: a smoothstepped toe sag (0 -> +20%), a
    constant +20% climb, and a constant-rate crest curve that hands over to
    ``chute_floor_z`` at MOUTH_Y with grade exactly -CHUTE_GRADE_MOUTH.
    """

    if y <= TOE_Y:
        return 0.0
    if y >= MOUTH_Y:
        return MOUTH_Z
    run = y - TOE_Y
    if run < RAMP_BLEND:
        u = run / RAMP_BLEND
        return RAMP_GRADE * RAMP_BLEND * (u**3 - 0.5 * u**4)
    if y < CREST_Y0:
        return RAMP_GRADE * run - RAMP_GRADE * RAMP_BLEND * 0.5
    u = (y - CREST_Y0) / CREST_LEN
    return CREST_START_Z + CREST_LEN * (
        RAMP_GRADE * u - 0.5 * (RAMP_GRADE + CHUTE_GRADE_MOUTH) * u * u
    )


def lane_z(y: float) -> float:
    """The ONE drive-lane profile: ramp below the mouth, chute above it.

    Everything that touches the driving surface - visual deck, visual chute
    floor, cage nodes, trigger heights, the build-time crest gate - goes
    through this function, so the mesh, the physics and the assert cannot be
    reading three different curves.
    """

    return ramp_deck_z(y) if y <= MOUTH_Y else chute_floor_z(y)


def lane_grade(y: float, eps: float = 0.02) -> float:
    """Signed dz/dy of the drive lane, ONE convention, central difference."""

    return (lane_z(y + eps) - lane_z(y - eps)) / (2.0 * eps)


def ramp_skirt_x(y: float) -> float:
    """Outer x where the embankment skirt meets grade."""

    crest = ramp_deck_z(y) + KERB_RISE
    return RAMP_HALF_W + KERB_RUN + crest / math.tan(math.radians(SKIRT_ANGLE_DEG))


# ---------------------------------------------------------------------------
# Discharge conveyor. A steel slat pan conveyor, which is what actually runs
# under a shredder. It spans the FULL slot (y -6.6 .. +15.6) so a wreck that
# drops out of any part of the 10 m nip lands on belt, never on bare apron.
# 5.60 m wide > the 5.20 m span the drums drop material through.
# ---------------------------------------------------------------------------
BELT_Y_TAIL = -6.60
BELT_Y_HEAD = 15.60
BELT_Z_TAIL = 1.05
BELT_GRADE = 0.04  # +4% discharge incline
BELT_HALF_W = 2.80
BELT_SKIRT_X = 3.60  # skirt boards, 68 deg, keep the wreck on the pan
BELT_SKIRT_RISE = 0.90
BELT_SPEED = 3.0  # m/s: clears a 4.5 m wreck off the tail in 1.5 s
SLAT_PITCH = 1.10
# Plinth: the trough the conveyor sits in. Round-1 review found the pan was a
# roof over an OPEN, drivable 1.9 m pocket - a car could enter from the head
# end or either side and clip up through the one-sided pan quads. The plinth
# closes that volume with sloped faces only (58 deg, gentler than the 62 deg
# embankment skirt this prop already ships) - no vertical collision face
# anywhere, and the visual gets matching plating so the geometry is not a lie.
BELT_PLINTH_ANGLE_DEG = 58.0
BELT_PLINTH_RUN = 1.0 / math.tan(math.radians(BELT_PLINTH_ANGLE_DEG))  # 0.6249


def belt_z(y: float) -> float:
    return BELT_Z_TAIL + BELT_GRADE * (y - BELT_Y_TAIL)


def belt_plinth_x(y: float) -> float:
    """Outer x where the conveyor plinth face meets the apron."""

    return BELT_HALF_W + belt_z(y) * BELT_PLINTH_RUN


BELT_Z_HEAD = belt_z(BELT_Y_HEAD)
# Sloped end caps: the plinth face rolled around the ends, so neither end is a
# wall standing in open ground.
BELT_TAIL_TOE_Y = BELT_Y_TAIL - BELT_Z_TAIL * BELT_PLINTH_RUN
BELT_HEAD_TOE_Y = BELT_Y_HEAD + BELT_Z_HEAD * BELT_PLINTH_RUN
# 3.05 (drum underside) -> 1.31 (pan at y=0). The servo lets go at
# ROLL_BOT_Z + grip_z_release_above and has faded to nothing by ROLL_BOT_Z, so
# this whole gap is genuine free fall onto steel - see the LUA notes on damage.
DROP_TO_BELT = ROLL_BOT_Z - belt_z(0.0)

# ---------------------------------------------------------------------------
# Scrap pile and ground apron.
# ---------------------------------------------------------------------------
# Clear of both the apron edge and the conveyor's head toe: two nodes at the
# same point would be the coincident-node flexbody trap, and the strip between
# them is bare terrain at the same height, so nothing can fall into it.
PILE_TOE_Y = BELT_HEAD_TOE_Y + 0.8
PILE_CREST_Y = 20.0
PILE_TAIL_Y = 27.0
PILE_TOE_Z = 0.0  # flush with the apron: no step at the seam
PILE_CREST_Z = 1.70
PILE_HALF_W = 5.40
APRON_Y_MIN = -13.0
APRON_Y_MAX = BELT_Y_HEAD
APRON_HALF_X = 9.0

# Structure.
COLUMN_X = 6.40
COLUMN_Y = 5.40
COLUMN_HALF = 0.45
COLUMN_TOP_Z = 10.40
WALK_Z = 6.40
WALK_X_IN = 5.95
WALK_X_OUT = 7.45
PACK_X = -7.60  # hydraulic power pack skid, clear of the y=+/-5.4 columns
PACK_Y = 9.60
PACK_STACK_Z = 6.60
# Gantry sign over the chute mouth. Sized so the legend is READ, not implied:
# 0.77 m capitals on a 10.30 x 2.20 m plate are legible from the ramp toe
# 53 m back. The 1.50 m plate this replaces carried 0.13 m type (the family's
# default title_scale is 8.8% of the plate height) and rendered as a white
# smudge in the close-up probe.
SIGN_W = 2 * RIM_HALF_X - 0.9  # 10.30
SIGN_H = 2.20
SIGN_Z = 11.00
SIGN_POST_TOP = SIGN_Z + SIGN_H / 2.0  # 12.10: the posts must reach the plate
BEACON_PIVOT = (COLUMN_X, -COLUMN_Y, 12.35)
FAN_PIVOT = (PACK_X + 1.45, PACK_Y, 1.70)
FAN_BLADES = 5

# ---------------------------------------------------------------------------
# Posed parts: the authored axis each one spins about, and the rotational
# symmetry its geometry is built with.
#
# Round-1 review caught the cooling fan built as a disc in the Y-Z plane
# (axis = X) but posed about Y: one blade never moved and the other four swung
# through the radiator at 9 rad/s. The cure is not a corrected literal - it is
# making the SAME table drive the pose and a build-time geometric proof.
# build_parts() rotates each part's vertex cloud by 2*pi/fold about the axis
# named here and asserts it maps onto itself, and rejects the other two axes
# wherever fold >= 3; a mismatch between geometry and pose axis is a build
# failure, not a shipped animation.
# ---------------------------------------------------------------------------
PART_SPIN = {
    "roller_left": {"axis": (0.0, 1.0, 0.0), "fold": TEETH_PER_ROW},
    "roller_right": {"axis": (0.0, 1.0, 0.0), "fold": TEETH_PER_ROW},
    "power_fan": {"axis": (1.0, 0.0, 0.0), "fold": FAN_BLADES},
    # 2-fold only, so the discrimination half of the test is skipped for the
    # beacon: a box is symmetric about all three of its own axes. That is also
    # exactly why the beacon vane is built 2-fold - its apparent direction of
    # rotation is deliberately unreadable.
    "beacon": {"axis": (0.0, 0.0, 1.0), "fold": 2},
}

PALETTE = {
    f"{MOD_ID}_mill_steel": {
        "texture": {"family": "steel_worn", "params": {"base": [0.40, 0.43, 0.47]}},
        "color": [0.40, 0.43, 0.47, 1.0],
        "metallic": 0.85,
        "roughness": 0.45,
    },
    f"{MOD_ID}_machine_orange": {
        # Worn safety orange: the colour every scrap machine is painted, and
        # the peel parameter is what makes it read as twenty years old.
        "texture": {
            "family": "painted_metal",
            "params": {"base": [0.80, 0.33, 0.05], "rough": 0.46, "peel": 0.85},
        },
        "color": [0.80, 0.33, 0.05, 1.0],
        "metallic": 0.25,
        "roughness": 0.5,
    },
    f"{MOD_ID}_tooth_steel": {
        # Hardened tips: bright where the wear keeps them polished.
        "texture": {"family": "brushed_metal", "params": {"base": [0.70, 0.72, 0.76]}},
        "color": [0.70, 0.72, 0.76, 1.0],
        "metallic": 0.95,
        "roughness": 0.22,
    },
    f"{MOD_ID}_hazard": {
        "texture": {"family": "hazard_chevron"},
        "color": [0.95, 0.75, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    f"{MOD_ID}_grate": {
        "texture": {"family": "drum_perforated", "params": {"base": [0.52, 0.54, 0.57]}},
        "color": [0.52, 0.54, 0.57, 1.0],
        "metallic": 0.8,
        "roughness": 0.4,
    },
    f"{MOD_ID}_deck_asphalt": {
        "texture": {"family": "asphalt"},
        "color": [0.17, 0.17, 0.18, 1.0],
        "metallic": 0.0,
        "roughness": 0.9,
    },
    f"{MOD_ID}_concrete": {
        "texture": {"family": "concrete", "params": {"fine": 0.6}},
        "color": [0.60, 0.59, 0.56, 1.0],
        "metallic": 0.0,
        "roughness": 0.85,
    },
    f"{MOD_ID}_rust_scrap": {
        "texture": {"family": "steel_worn", "params": {"base": [0.42, 0.24, 0.14]}},
        "color": [0.42, 0.24, 0.14, 1.0],
        "metallic": 0.55,
        "roughness": 0.75,
    },
    f"{MOD_ID}_hydraulic_black": {
        "texture": {"family": "bakelite", "params": {"base": [0.10, 0.10, 0.11]}},
        "color": [0.10, 0.10, 0.11, 1.0],
        "metallic": 0.3,
        "roughness": 0.55,
    },
    f"{MOD_ID}_beacon_amber": {
        # Plain amber plastic, NOT emissive. This used to be justified with
        # "vehicle-material emissive is inert in this pipeline (AGENTS.md
        # round 15) - nothing on this prop glows and the report says so".
        # RETIRED 2026-08-15 (round 17): emissive is NOT inert - a
        # THREE-element `emissiveFactor` emits fine, and the materials that
        # rendered black had FOUR elements. AGENTS.md round 15 now marks that
        # bullet RETIRED, so it can no longer be cited as authority.
        # (The "the report says so" cross-reference was stale too: this mod's
        # listing copy only ever claimed the beacon SPINS, which it does.)
        # Left non-emissive DELIBERATELY - making it glow is a design change
        # and a material-data change, not a comment fix.
        "color": [0.95, 0.53, 0.05, 0.55],
        "metallic": 0.0,
        "roughness": 0.15,
    },
    f"{MOD_ID}_legend": {
        # The generator gives the plate's front face an explicit full-image
        # UV. Blender's primitive cube does NOT map each face to 0..1 - it
        # writes a six-face cross atlas, and the -Y face was sampling only
        # u 0.375..0.625, v 0.75..1.0 of this texture (measured on a
        # factory-startup cube). That is why the old legend rendered as a
        # smudge no matter what type size it was drawn at.
        "texture": {
            "family": "panel_legend",
            "params": {
                # Both lines go through `labels`, not `title`: the family pins
                # the title at v = 0.885 (right under the top frame line),
                # which clips any type big enough to read at this distance.
                # `labels` takes its own v and a per-label size multiplier, so
                # the layout is ours. 0.075 * 4.7 = 0.352 of the plate height
                # = 0.77 m capitals; the sub-line is 0.33 m.
                "title": "",
                "labels": [
                    [0.5, 0.62, "JUNK CHUTE GRINDER", 4.7],
                    [0.5, 0.24, "KEEP CLEAR OF ROLLS", 2.0],
                ],
                # Drawn at the PLATE's true aspect and then stretched into the
                # square texture (marquee lesson): anything else renders the
                # legend as a squashed hairline.
                "aspect": SIGN_W / SIGN_H,
            },
            "size": 1024,
        },
        "color": [0.06, 0.06, 0.07, 1.0],
        "metallic": 0.2,
        "roughness": 0.4,
    },
}

# EVERY material renders both sides (pack policy 2026-08-07). Blender does not
# backface-cull and BeamNG does, so a headless render can never catch an
# inside-out surface; this mod is built almost entirely from generated quad
# strips, which is precisely the geometry class that shipped invisible ramps
# and door leaves before the policy existed.
for _palette_entry in PALETTE.values():
    _palette_entry["double_sided"] = True
del _palette_entry

# The chute Contains box. Round-1 review measured the old 5.4 m box against a
# 5.578 m floor at its downstream end: a car hugging either wall was never
# fully CONTAINED and could not arm the machine from this zone. The funnel is
# widest at the box's UPSTREAM station, so the box is sized from there - a
# Contains box that is wider than the geometry it watches costs nothing (the
# flanks confine the car anyway) while a narrow one silently fails.
CHUTE_ZONE_Y = -9.5
CHUTE_ZONE_LEN = 7.0
CHUTE_ZONE_W = 2.0 * chute_half_width(CHUTE_ZONE_Y - CHUTE_ZONE_LEN / 2.0) + 0.60

TRIGGERS = {
    # Overlaps: an approach hint on the upper ramp. Fires early on purpose.
    "approach_zone": {
        "mode": "Overlaps",
        # Floor well BELOW the deck at the centre station: the deck climbs
        # 2.8 m across the box's 16 m length, and an axis-aligned box over a
        # 20% grade whose floor sits ON the surface stops overlapping cars at
        # the downhill end (the catapult's zone-floor lesson, 2026-07-23).
        "center": [0.0, -30.0, ramp_deck_z(-30.0) + 0.60],
        "dimensions": [9.0, 16.0, 6.4],
    },
    # Contains: the chute proper. Contains (not Overlaps) so the machine only
    # arms once a whole vehicle is committed to the chute - a car clipping the
    # mouth on the way past must not spin the rolls up. Height: the floor
    # drops 1.9 m across the box's own length, so the floor must sit well
    # below the centre-station surface or a car at the downhill end is never
    # CONTAINED (the catapult measured exactly this failure).
    "chute_zone": {
        "mode": "Contains",
        "center": [0.0, CHUTE_ZONE_Y, chute_floor_z(CHUTE_ZONE_Y) + 1.4],
        "dimensions": [CHUTE_ZONE_W, CHUTE_ZONE_LEN, 5.2],
    },
    # Overlaps: the throat. A car being fed between the drums is never fully
    # contained by anything, and entries must read the instant the nose pokes
    # in - the exact case AGENTS.md says Contains reads late on.
    "throat_zone": {
        "mode": "Overlaps",
        "center": [0.0, 0.0, 4.20],
        "dimensions": [7.6, 11.6, 4.6],
    },
    # Overlaps: everything on or just above the discharge pan.
    "discharge_zone": {
        "mode": "Overlaps",
        "center": [0.0, 4.5, belt_z(4.5) + 1.3],
        "dimensions": [8.0, 23.0, 4.2],
    },
}

EFFECTS = {
    # Only emitters this pack has proven present, by shipped mods in the
    # pack: BNGP_2 (9 uses) and BNGP_34 (5 uses). The version this comment
    # used to name ("0.38.6") was the test PROFILE DIRECTORY name, not an
    # engine; a 2026-08-15 census of the installed engine (v0.39.4.0 build 20972)
    # finds both still shipped, among 91 ParticleEmitterData objects.
    "grind_dust": {
        "emitter": "BNGP_2",
        "position": [0.0, 0.0, 5.40],
        "direction": [0.0, 0.0, 1.0],
    },
    "discharge_dust": {
        "emitter": "BNGP_34",
        "position": [0.0, -2.60, belt_z(-2.60) + 0.9],
        "direction": [0.0, 0.0, 1.0],
    },
    "stack_smoke": {
        "emitter": "BNGP_2",
        "position": [PACK_X + 1.9, PACK_Y - 1.5, PACK_STACK_Z],
        "direction": [0.0, 0.0, 1.0],
    },
}

# ---------------------------------------------------------------------------
# Runtime tunables.
#
# Timing note: AGENTS.md records dtSim in behavior.update measuring ~3x wall
# seconds; the centrifuge's 2026-08-09 coda retracted that ("stepped-rig
# artifact, live timers ~= 1:1"). Nothing here depends on an exact wall
# duration - every phase exits on an EVENT and carries a timer only as a
# backstop - so the machine behaves sanely under either reading.
#
# EVERY key below is read by LUA_BEHAVIOR and every `B.x` in LUA_BEHAVIOR
# appears below: the generator cross-checks both directions and fails the
# build on either an orphan tunable or a nil lookup (the centrifuge's
# nil-key freeze, and round-1's two dead keys).
# ---------------------------------------------------------------------------
BEHAVIOR = {
    "camera_distance": 46.0,
    # --- geometry mirrored to the runtime (this file is the only source) ---
    "roll_axis_x": ROLL_AXIS_X,
    "roll_axis_z": ROLL_AXIS_Z,
    # The CONTACT radius, not the hook tip: the car rests on the disc rims.
    "roll_cage_r": ROLL_CAGE_R,
    "roll_top_z": ROLL_TOP_Z,
    "roll_bot_z": ROLL_BOT_Z,
    "slot_half_y": SLOT_HALF_Y,
    "teeth_per_rev": float(TEETH_PER_ROW),
    "belt_y_tail": BELT_Y_TAIL,
    "belt_y_head": BELT_Y_HEAD,
    "belt_z_tail": BELT_Z_TAIL,
    "belt_grade": BELT_GRADE,
    "belt_half_w": BELT_HALF_W,
    "slat_pitch": SLAT_PITCH,
    # --- spin axes, in AUTHORED coordinates ------------------------------
    # 3-number lists arrive in Lua as vec3 (AGENTS.md), which is exactly what
    # toWorldDir wants. No hand-typed mirror sign anywhere: see the module
    # docstring for why toWorldDir(authored axis) is the provably correct
    # argument to axisAngle, at every spawn heading.
    "spin_axis_roller": list(PART_SPIN["roller_left"]["axis"]),
    "spin_axis_fan": list(PART_SPIN["power_fan"]["axis"]),
    "spin_axis_beacon": list(PART_SPIN["beacon"]["axis"]),
    # --- grip envelope ----------------------------------------------------
    # Derived in behavior.init from the geometry keys above plus these
    # margins, so the envelope tracks the machine instead of being four more
    # hand-typed metres that can silently disagree with it.
    # x: the throat plus a metre of slop on each side; beyond roll_axis_x +
    # 1.30 the body is under the hopper wall, not on the drums.
    "grip_x_margin": 1.30,
    "grip_x_fade": 0.80,
    # y lead: 0.70 m ahead of the slot mouth is the car-CENTRE position at
    # which the nose (2.25 m ahead) is 1.55 m out over the slot and the front
    # axle is already unsupported. Any earlier and the field would brake a car
    # still fully on the chute floor, freezing it there instead of feeding it.
    "grip_y_lead": 0.70,
    "grip_y_trail": 0.30,
    "grip_y_fade": 0.90,
    # z: the servo lets go 0.70 m ABOVE the drum underside and has faded to
    # nothing AT it. Measured release: car datum z = 3.02 already falling at
    # 2.89 m/s, 1.73 m of unpowered drop left, arriving on the pan at
    # 6.49 m/s. That free fall is the only mechanism in this framework
    # that deforms a car without a scripted contact - a uniform cluster
    # velocity add cannot deform anything by construction, so the machine has
    # to MAKE the car hit something. Top at 1.10 m above the crowns: a car
    # teetering nose-down on the lip.
    "grip_z_release_above": 0.70,
    "grip_z_head": 1.10,
    "grip_z_fade": 0.70,
    # --- drive -----------------------------------------------------------
    # 1.50 rad/s = 14.3 rev/min. Derived: a 4.5 m car should take about three
    # seconds to be drawn through, so the CONTACT surface speed is
    # v = 4.5/3 = 1.5 m/s and omega = v / ROLL_CAGE_R = 1.50. The hook tips
    # therefore sweep at 1.725 m/s. Real twin-shaft shredders run 8-20 rev/min.
    "roll_omega_run": 1.50,
    "roll_omega_reverse": -1.20,  # anti-jam reverse, deliberately slower
    "omega_slew": 0.95,  # rad/s^2: 0 -> full in 1.58 s, full -> reverse in 2.8 s
    "bog_fraction": 0.32,  # the drive loses a third of its speed under load
    # Load ramps in 1/1.40 = 0.71 s (a rotor bogs within one tooth pass) and
    # decays in 1/0.50 = 2.0 s (the drive takes longer to recover than to
    # stall), so the visible speed sag tracks what is actually in the throat.
    "load_rise_rate": 1.40,
    "load_fall_rate": 0.50,
    # --- velocity coupling ----------------------------------------------
    # First-order servo toward the drums' own surface velocity. grip_rate is
    # the corner frequency: at 7 /s the car reaches ~63% of the roller speed
    # in 143 ms, which is a firm bite without being a step change.
    "grip_rate": 7.0,
    "gravity_comp": 9.81,  # the rolls carry the body's weight while gripped
    # 0.60 m/s per frame at 60 Hz = 36 m/s^2 = 3.7 g, on the FEED channel
    # alone. The centrifuge shipped 6.0 for a machine whose whole point was
    # violence; a grab that reads as machinery, not as a collision, wants an
    # order of magnitude less.
    #
    # Feed and chew are capped SEPARATELY (they are orthogonal channels of an
    # orthonormal frame, so the split is exact). One shared cap let a big
    # lateral chew demand scale the whole delta vector down and starve the
    # pull: measured at 1.00 m/s of achieved feed against a 1.50 m/s roller
    # surface - i.e. the visible roller speed and the felt pull DID disagree,
    # by a third, exactly the thing this machine's headline claim forbids.
    # Split, the feed channel tracks omega * ROLL_CAGE_R and nothing the chew
    # does can touch it. Re-measured after the split: steady feed inside the
    # nip is 1.428 m/s against a 1.500 m/s contact surface - 4.8% slip, in
    # the only direction a real machine slips.
    "frame_dv_cap": 0.60,
    "chew_dv_cap": 0.55,
    "max_sample_speed": 45.0,  # skip anything already moving absurdly fast
    # Tooth-pass judder: the TARGET velocity oscillates, so the servo can
    # never integrate an unbounded impulse train (an additive per-frame shake
    # at 1.24 Hz would accumulate 6 m/s over a half period and launch the
    # car).
    "chew_shake_mps": 2.20,
    # SCRUB. The judder alone oscillates about the centre line and round-1
    # measured it peaking at 0.461 m against 0.450 m of side clearance - a 2%
    # margin in a frictionless open-loop model, which in-game friction eats.
    # The scrub is a SUSTAINED one-sided lateral target that reverses every
    # half period, so the body is driven onto one rotor shroud, ground along
    # it, then thrown onto the other. Unopposed travel in one half period is
    # chew_scrub_mps * (T - 1/grip_rate) = 3.00 * (0.55 - 0.14) = 1.23 m
    # against 0.45 m of clearance at the nip and 0.50 m where the chew reaches
    # full strength, so the crossing costs about 0.2 s of a 0.55 s half period
    # and the servo spends the rest of it PRESSING - the target velocity is
    # never reached, so the push does not decay. Real contact with real
    # collision geometry is the honest way to deform a car from a scripted
    # machine. Measured (frictionless point mass, which UNDER-states a 4.5 m
    # pitched body): 3 separate shroud-contact episodes per trip, peak
    # excursion 0.569 m, deepest penetration into the shroud plane 0.039 m.
    "chew_scrub_mps": 3.00,
    "chew_scrub_half_seconds": 0.55,
    # Both chew terms ramp in over the first 0.60 m BELOW the collision crown.
    # A car teetering nose-down on the lip is still resting on two crowns; a
    # sustained 2.2 m/s sideways shove there threw it 1.45 m off centre and
    # onto a hopper flank instead of feeding it (measured in the servo
    # replication). The teeth only chew what is actually between the drums.
    "chew_depth_fade": 0.60,
    # Breakgroup separation. This IS real BeamNG damage and it is the only
    # kind this framework can command directly: doors, bonnet, bumpers and
    # tyres come off as the teeth take the car. It rides on a vehicle-Lua
    # command, pcall-guarded on BOTH sides, so on any engine build where the
    # call is missing the machine simply does not shed panels.
    "shred_breakgroups": True,
    # --- conveyor --------------------------------------------------------
    # Belt friction acts ONLY along the belt direction; the vertical channel
    # is left alone so the wreck still rests on the pan under gravity.
    "belt_speed": BELT_SPEED,
    # 3.0 /s: a wreck dumped across the slats reaches belt speed in ~0.33 s,
    # which is what a steel pan with 0.16 m slats does to a sliding body.
    "belt_grip_rate": 3.0,
    # 0.45 m/s per frame = 27 m/s^2 = 2.8 g: below the grip cap, because the
    # pan only has friction to work with, not teeth.
    "belt_dv_cap": 0.45,
    "belt_ride_min": -0.40,  # local height band counted as "on the pan"
    "belt_ride_max": 1.60,
    # --- lifecycle -------------------------------------------------------
    "idle_grace_seconds": 6.0,  # nothing anywhere -> coast the rolls down
    "track_grace_seconds": 3.0,  # keep servicing through a blanked trigger set
    "run_timeout_seconds": 60.0,  # backstop: still gripped after a minute -> purge
    # Transient-phase watchdog. The longest transient is the 4.0 s jam
    # reversal, so 30 s is ~7x margin and still bounded.
    "hard_reset_seconds": 30.0,
    # Jam: gripped, rolls forward, and the body has not dropped 0.22 m in
    # 2.5 s. 0.22 m is ~6% of one feed window (1.5 m/s * 2.5 s = 3.75 m of
    # nominal travel), so normal feeding never trips it and a wedged body
    # always does.
    "jam_window_seconds": 2.5,
    "jam_progress_min": 0.22,
    "jam_clear_seconds": 4.0,  # long enough for the 2.8 s reversal plus bite
    "max_jam_clears": 3,
    "purge_speed_mps": 15.0,  # spat back up the chute at ~44 deg
    "purge_seconds": 1.5,
    "regrip_block_seconds": 4.0,  # a purged wreck is not instantly re-eaten
    # --- show ------------------------------------------------------------
    "beacon_rate": 3.0,  # rad/s ~ 0.48 rev/s (centrifuge's corrected value)
    # 9 rad/s = 1.43 rev/s. Fast enough to read as running, slow enough not to
    # strobe against a 60 Hz frame rate the way the centrifuge's beacon did.
    "fan_rate": 9.0,
    # --- safety ----------------------------------------------------------
    # Phys-explosion watchdog: a vehicle whose spawn OOBB half-extent balloons
    # past 24 m has had a node explode; stop feeding a solver that is already
    # losing it (AGENTS.md round 15; API confirmed live on the install of the
    # day - the "0.38.6" that used to sit here came from the profile directory
    # name and has not been re-confirmed since the engine moved to 20972).
    "safety_enabled": True,
    "safety_extent_max": 24.0,
    "quarantine_seconds": 8.0,
}

# Tunables the framework itself consumes; they never appear as `B.x` in the
# behavior source and are exempt from the orphan-key gate.
FRAMEWORK_TUNABLES = frozenset({"camera_distance"})

LUA_BEHAVIOR = r"""
-- ==========================================================================
-- Junk Chute Grinder Trap
--
-- Coordinate readout: the model rotation is orthonormal, so dotting a world
-- offset with the three transformed unit axes is an EXACT inverse - no quat
-- inverse call needed, and it is built from the same toWorldDir the triggers
-- and effects are placed with, so the local frame the physics uses and the
-- local frame the geometry was authored in cannot drift apart.
-- ==========================================================================

-- What this machine can and cannot do to a car, stated plainly because the
-- honest answer is short:
--   CAN  - separate breakgroups and deflate tyres, via a guarded vehicle-Lua
--          command (beamstate). Doors, bonnet, bumpers, tyres.
--   CAN  - create real deformation INDIRECTLY, by making the car hit things.
--          Measured in a 60 Hz servo replication against the shipped
--          tunables (see the report): the body reaches a rotor shroud in 3
--          separate episodes on the way down, and the release drops it 1.73 m
--          onto the steel pan, arriving at 6.49 m/s - the equivalent of a
--          2.15 m free fall.
--   CANNOT - deform anything directly. addSubjectVelocity is
--          applyClusterVelocityScaleAdd, a UNIFORM velocity add over the
--          whole node cluster; by construction it cannot strain a single
--          beam. Any claim that a velocity servo "crushes" a car is false.
local SHRED_COMMAND = "pcall(function()"
  .. " if beamstate and beamstate.breakAllBreakgroups then"
  .. " beamstate.breakAllBreakgroups() end"
  .. " if beamstate and beamstate.deflateTire and wheels and wheels.wheelCount then"
  .. " for i = 0, wheels.wheelCount - 1 do beamstate.deflateTire(i) end end"
  .. " end)"

local function localOf(state, world, ex, ey, ez)
  local d = world - state.origin
  return vec3(d:dot(ex), d:dot(ey), d:dot(ez))
end

-- Trapezoidal window: 1 inside [low, high], falling linearly to 0 over fade.
local function window(value, low, high, fade)
  if value <= low - fade or value >= high + fade then return 0 end
  if value < low then return (value - low + fade) / fade end
  if value > high then return (high + fade - value) / fade end
  return 1
end

-- The grip envelope is DERIVED from the shipped machine geometry plus named
-- margins, so it cannot drift away from the drums it is supposed to describe.
local function gripEnvelope(b)
  b.gripXHalf = B.roll_axis_x + B.grip_x_margin
  b.gripYMin = -B.slot_half_y - B.grip_y_lead
  b.gripYMax = B.slot_half_y + B.grip_y_trail
  b.gripZMin = B.roll_bot_z + B.grip_z_release_above
  b.gripZMax = B.roll_top_z + B.grip_z_head
end

local function gripFactor(b, lp)
  return window(lp.x, -b.gripXHalf, b.gripXHalf, B.grip_x_fade)
    * window(lp.y, b.gripYMin, b.gripYMax, B.grip_y_fade)
    * window(lp.z, b.gripZMin, b.gripZMax, B.grip_z_fade)
end

-- Exact surface-velocity field of the two counter-rotating drums.
--
-- Parametrise the LEFT drum's tip circle by the azimuth a measured from its
-- crown toward the nip:  p = axis + R*(sin a, 0, cos a).  With the drum
-- turning so its nip face travels DOWN, the surface velocity there is
--     v_left(a)  = v_s * ( cos a, 0, -sin a)
-- and by mirror symmetry on the right drum
--     v_right(a) = v_s * (-cos a, 0, -sin a).
-- Sample each drum at the BODY's own azimuth and average. Checks:
--   nip centre (0, 4.05):   a_L = a_R = 90 deg   -> (0, 0, -1.000) v_s
--   crown centre (0, 5.05): a_L = a_R = 67.8 deg -> (0, 0, -0.926) v_s
--   off-centre (1.2, 5.05): a_L 74.7, a_R 51.3   -> (-0.181, 0, -0.872) v_s
-- i.e. the field rakes an off-centre body back to the middle and feeds it
-- down, which is exactly what the crowns of a twin-shaft shredder do. The
-- magnitude is always v_s = omega * ROLL_CAGE_R, read from the CURRENT omega,
-- so the pull can never disagree with the visible roller speed.
local function rollerField(lp, surfaceSpeed)
  local dz = lp.z - B.roll_axis_z
  local aL = math.atan2(lp.x + B.roll_axis_x, dz)
  local aR = math.atan2(B.roll_axis_x - lp.x, dz)
  local fx = (math.cos(aL) - math.cos(aR)) * 0.5 * surfaceSpeed
  local fz = -(math.sin(aL) + math.sin(aR)) * 0.5 * surfaceSpeed
  return fx, fz
end

local function readDamage(vehicleId)
  local info = map and map.objects and map.objects[vehicleId]
  local value = info and info.damage or nil
  if type(value) == "number" and value == value then return value end
  return nil
end

local function setPhase(state, phase, message, ttl)
  local b = state.behavior
  if b.phase == phase then return end
  b.phase = phase
  b.elapsed = 0
  if message then showMessage(message, ttl or 2.0) end
  emitEvent(state, "I", "grinder_phase", {phase = phase, omega = b.omega})
end

-- --------------------------------------------------------------------------
-- Per-subject service: grip servo, belt friction, jam watch, safety.
-- Returns true when this subject is currently held by the teeth.
-- --------------------------------------------------------------------------
local function serviceSubject(state, vehicle, dtSim, ex, ey, ez)
  local b = state.behavior
  local id = vehicle:getId()
  local world = vehicle:getPosition()
  if not world then return false end
  local lp = localOf(state, world, ex, ey, ez)
  local track = b.tracked[id]
  if not track then
    track = {jams = 0, markZ = lp.z, markT = b.clock, peakDamage = 0}
    b.tracked[id] = track
  end
  track.seen = b.clock
  track.lp = lp
  -- onBelt is pure geometry and is refreshed BEFORE any early return: the
  -- spin-down interlock reads it, so a stale value would either strand a
  -- wreck on a dead pan or pin the rolls running forever.
  track.onBelt = lp.y > B.belt_y_tail - 0.6 and lp.y < B.belt_y_head + 0.6
    and math.abs(lp.x) < B.belt_half_w + 1.2
    and (lp.z - (B.belt_z_tail + B.belt_grade * (lp.y - B.belt_y_tail)))
        > B.belt_ride_min
    and (lp.z - (B.belt_z_tail + B.belt_grade * (lp.y - B.belt_y_tail)))
        < B.belt_ride_max

  -- Phys-explosion watchdog: quarantine a sample the solver is losing rather
  -- than keep injecting energy into it.
  if B.safety_enabled and (b.clock - (track.safetyCheck or -1)) > 0.5 then
    track.safetyCheck = b.clock
    local ok, half = pcall(function()
      return vehicle:getSpawnWorldOOBB():getHalfExtents()
    end)
    if ok and half and type(half.x) == "number" then
      local extent = math.max(half.x, math.max(half.y, half.z))
      if extent > B.safety_extent_max then
        track.blockUntil = b.clock + B.quarantine_seconds
        emitEvent(state, "W", "sample_quarantined", {
          subject_id = id, extent = extent,
        })
      end
    end
  end
  if track.blockUntil and b.clock < track.blockUntil then return false end

  local okVel, velocity = pcall(function() return vehicle:getVelocity() end)
  if not okVel or not velocity then return false end
  local speed = velocity:length()
  if speed ~= speed or speed > B.max_sample_speed then return false end

  local damage = readDamage(id)
  if damage and damage > (track.peakDamage or 0) then track.peakDamage = damage end

  local held = false
  local grip = gripFactor(b, lp)
  if grip > 0 and math.abs(b.omega) > 0.02 then
    local surfaceSpeed = b.omega * B.roll_cage_r
    local fx, fz = rollerField(lp, surfaceSpeed)
    -- Tooth-pass modulation. The fast term is the judder of discrete teeth;
    -- the slow scrubSign term is the sustained press that walks the body onto
    -- one shroud and grinds it along, then throws it onto the other. Both
    -- fade in with DEPTH below the crown - a car still teetering on the lip
    -- is resting on two crowns, not being chewed.
    local phase = b.rollAngle * B.teeth_per_rev
    -- Intermittent bite. The band is not arbitrary: contact alternates
    -- between the disc rim (1.00 x the field) and a hook tip, which is
    -- ROLL_TIP_R / ROLL_CAGE_R = 1.15 x further out and therefore moving
    -- 1.15 x faster. Mean 1.02, so the feed does NOT quietly run slow - the
    -- old 0.89-mean version made the machine feed at 0.69 of its own roller
    -- speed while claiming the two could not disagree.
    local bite = 1.02 + 0.13 * math.sin(phase * 2.0)
    local depth = (B.roll_top_z - lp.z) / B.chew_depth_fade
    if depth < 0 then depth = 0 elseif depth > 1 then depth = 1 end
    local lateral = fx + depth * (
      b.scrubSign * B.chew_scrub_mps + math.sin(phase) * B.chew_shake_mps)
    local gain = math.min(1, dtSim * B.grip_rate) * grip
    -- ex/ey/ez are the orthonormal image of the authored axes, so splitting
    -- the servo into channels along them is exact, not an approximation.
    --
    -- FEED channel (ey, ez): the roller field plus weight support. No ey
    -- target on purpose - the drums present no axial surface velocity, so the
    -- servo brakes fore-aft slide, and that braking IS the grab.
    local feed = ey * (-velocity:dot(ey) * gain)
      + ez * ((fz * bite - velocity:dot(ez)) * gain
              + B.gravity_comp * dtSim * grip)
    local feedMag = feed:length()
    if feedMag > B.frame_dv_cap then feed = feed * (B.frame_dv_cap / feedMag) end
    -- CHEW channel (ex): judder plus the sustained scrub, capped on its own
    -- so it can never borrow authority from the pull.
    local chew = ex * ((lateral - velocity:dot(ex)) * gain)
    local chewMag = chew:length()
    if chewMag > B.chew_dv_cap then chew = chew * (B.chew_dv_cap / chewMag) end
    if addSubjectVelocity(state, vehicle, feed + chew) then
      held = grip > 0.35
    end
  end

  -- Real damage, once per subject, at the moment the body passes the roller
  -- axis line: that is when the teeth have it from both sides. Guarded on
  -- both sides of the bridge, so a missing beamstate API is a no-op.
  if held and B.shred_breakgroups and not track.shredded
    and b.omega > 0.02 and lp.z < B.roll_axis_z then
    track.shredded = true
    b.stats.shredded = (b.stats.shredded or 0) + 1
    pcall(function() vehicle:queueLuaCommand(SHRED_COMMAND) end)
    emitEvent(state, "I", "grinder_bit", {subject_id = id})
  end

  if held and b.omega > 0.02 then
    -- Jam watch: progress resets the mark; so does being lifted clear, so a
    -- reversal never leaves a stale "no progress" clock behind.
    if lp.z < track.markZ - B.jam_progress_min or lp.z > track.markZ + 0.50 then
      track.markZ = lp.z
      track.markT = b.clock
    elseif (b.clock - track.markT) > B.jam_window_seconds then
      track.markZ = lp.z
      track.markT = b.clock
      track.jams = (track.jams or 0) + 1
      b.jamId = id
    end
  end

  -- Belt friction. Along-belt only: the pan drags, it does not levitate, so
  -- the wreck still settles onto the slats under gravity.
  if track.onBelt and b.powered then
    local inv = 1 / math.sqrt(1 + B.belt_grade * B.belt_grade)
    local dir = ey * inv + ez * (B.belt_grade * inv)
    local along = velocity:dot(dir)
    local push = (b.beltSpeed - along) * math.min(1, dtSim * B.belt_grip_rate)
    if push > B.belt_dv_cap then push = B.belt_dv_cap end
    if push < -B.belt_dv_cap then push = -B.belt_dv_cap end
    addSubjectVelocity(state, vehicle, dir * push)
  end
  return held
end

-- --------------------------------------------------------------------------
-- Purge: the rolls spit the sample back up the chute. This is the escape
-- hatch that makes "every phase has a way out" true even for a wreck the
-- teeth cannot swallow.
-- --------------------------------------------------------------------------
local function purgeSubject(state, vehicleId)
  local b = state.behavior
  local vehicle = vehicleId and exactVehicle(vehicleId) or nil
  if not vehicle then return false end
  local ey = toWorldDir(state, vec3(0, 1, 0))
  local ez = toWorldDir(state, vec3(0, 0, 1))
  -- Unit vector: (-0.72)^2 + 0.69^2 = 0.994, back down the chute at 44 deg.
  local direction = ey * -0.72 + ez * 0.69
  if not launchSubject(state, vehicle, direction * B.purge_speed_mps) then
    return false
  end
  local track = b.tracked[vehicleId]
  if track then
    track.jams = 0
    track.blockUntil = b.clock + B.regrip_block_seconds
    track.markT = b.clock
  end
  emitEvent(state, "I", "grinder_purged", {subject_id = vehicleId})
  return true
end

behavior.init = function(state)
  local b = state.behavior
  b.phase = "idle"
  b.clock = 0
  b.elapsed = 0
  b.busy = 0
  b.omega = 0
  b.omegaCmd = 0
  b.rollAngle = 0
  b.beaconAngle = 0
  b.fanAngle = 0
  b.beltTravel = 0
  b.beltSpeed = 0
  b.load = 0
  b.powered = false
  b.scrubSign = 1
  b.scrubClock = 0
  b.tracked = {}
  b.jamId = nil
  b.gripId = nil
  b.purgeTried = nil
  b.lastHeld = nil
  b.stats = {fed = 0, purged = 0, jams = 0, shredded = 0}
  gripEnvelope(b)
  setPartPose(state, "roller_left", nil, quat(0, 0, 0, 1))
  setPartPose(state, "roller_right", nil, quat(0, 0, 0, 1))
  setPartPose(state, "belt_slats", vec3(0, 0, 0), nil)
  setPartPose(state, "beacon", nil, quat(0, 0, 0, 1))
  setPartPose(state, "power_fan", nil, quat(0, 0, 0, 1))
end

behavior.reset = function(state)
  behavior.init(state)
  setEffectActive(state, "grind_dust", false)
  setEffectActive(state, "discharge_dust", false)
  setEffectActive(state, "stack_smoke", false)
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if zone == "approach_zone" and b.phase == "idle" then
    showMessage("FEED CHUTE OPEN - drive it in", 2.4)
  elseif zone == "chute_zone" and b.phase == "idle" then
    emitEvent(state, "I", "grinder_charged", {subject_id = vehicle:getId()})
  elseif zone == "throat_zone" and (b.omega or 0) > 0.4 then
    showMessage("IN THE ROLLS", 1.6)
  end
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  local b = state.behavior
  b.tracked[vehicleId] = nil
  if b.jamId == vehicleId then b.jamId = nil end
  if b.gripId == vehicleId then b.gripId = nil end
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  -- Defensive: registerProp pcalls behavior.init, so a one-off failure there
  -- would otherwise leave every field nil and throw on the first arithmetic.
  if not b.phase then behavior.init(state) end
  if dtSim < 0 then dtSim = 0 end
  b.clock = b.clock + dtSim
  b.elapsed = b.elapsed + dtSim

  local ex = toWorldDir(state, vec3(1, 0, 0))
  local ey = toWorldDir(state, vec3(0, 1, 0))
  local ez = toWorldDir(state, vec3(0, 0, 1))

  -- ---- 1. who is in the machine ----------------------------------------
  -- Two populations on purpose:
  --   feed  = chute + throat: these ARM the machine and keep it running.
  --   serve = feed + discharge: these get physics.
  -- A wreck parked on the scrap pile sits inside discharge_zone forever; if
  -- it also armed the machine the rolls would never stop (and the hard-reset
  -- backstop would just re-arm them every four minutes).
  local serve = {}
  for vehicleId in pairs(zoneOccupants(state, "chute_zone")) do
    serve[vehicleId] = "feed"
  end
  for vehicleId in pairs(zoneOccupants(state, "throat_zone")) do
    serve[vehicleId] = "feed"
  end
  for vehicleId in pairs(zoneOccupants(state, "discharge_zone")) do
    if not serve[vehicleId] then serve[vehicleId] = "out" end
  end
  -- Grace: an Overlaps/Contains trigger set can blank for a frame (the
  -- centrifuge lost a parked car for minutes this way), so a subject stays
  -- serviced for track_grace_seconds after its last sighting. The grace
  -- population never re-arms the machine, only keeps it servicing.
  for vehicleId, track in pairs(b.tracked) do
    if serve[vehicleId] then
      track.seen = b.clock
    elseif (b.clock - (track.seen or 0)) > B.track_grace_seconds then
      b.tracked[vehicleId] = nil
      if b.jamId == vehicleId then b.jamId = nil end
      if b.gripId == vehicleId then b.gripId = nil end
    else
      serve[vehicleId] = "out"
    end
  end
  -- POSITION overrides the trigger box. throat_zone reaches down past the
  -- drums (it has to: a car being fed is never fully inside anything), so a
  -- wreck lying on the pan under the rolls still overlaps it. Demote anything
  -- already below the drum underside to "out" - otherwise a wreck the belt
  -- could not shift would arm the machine forever.
  local feedCount = 0
  for vehicleId, role in pairs(serve) do
    if role == "feed" then
      local track = b.tracked[vehicleId]
      if track and track.lp and track.lp.z < B.roll_bot_z then
        serve[vehicleId] = "out"
      else
        feedCount = feedCount + 1
      end
    end
  end
  local beltBusy = false
  for _, track in pairs(b.tracked) do
    if track.onBelt then beltBusy = true end
  end
  -- The rolls may only stop when the feed path is clear, nothing is held,
  -- and the pan is empty - so a wreck can never be stranded on a dead belt.
  local canStop = feedCount == 0
    and not beltBusy
    and (b.clock - (b.lastHeld or -1e9)) > B.idle_grace_seconds

  -- ---- 2. drive state machine ------------------------------------------
  if b.phase == "idle" then
    b.omegaCmd = 0
    b.powered = false
    if feedCount > 0 then
      setPhase(state, "spinup", "ROLLS TO SPEED", 2.0)
      setEffectActive(state, "stack_smoke", true)
    end
  elseif b.phase == "spinup" then
    b.omegaCmd = B.roll_omega_run
    b.powered = true
    if b.omega >= B.roll_omega_run - 0.02 then
      setPhase(state, "running", "GRINDING", 1.8)
    end
  elseif b.phase == "running" then
    b.omegaCmd = B.roll_omega_run * (1 - B.bog_fraction * b.load)
    b.powered = true
    if b.jamId then
      b.stats.jams = b.stats.jams + 1
      setPhase(state, "reversing", "JAM - AUTO REVERSE", 2.2)
    elseif b.busy > B.run_timeout_seconds then
      setPhase(state, "purging", "THROAT TIMEOUT - CLEARING", 2.2)
    elseif canStop then
      setPhase(state, "spindown", "ROLLS STOPPING", 1.6)
    end
  elseif b.phase == "reversing" then
    b.omegaCmd = B.roll_omega_reverse
    b.powered = true
    if b.elapsed >= B.jam_clear_seconds then
      local stuck = b.jamId and b.tracked[b.jamId] or nil
      if stuck and (stuck.jams or 0) >= B.max_jam_clears then
        setPhase(state, "purging", "UNGRINDABLE - SPITTING IT OUT", 2.4)
      else
        b.jamId = nil
        setPhase(state, "running", "RE-FEEDING", 1.6)
      end
    end
  elseif b.phase == "purging" then
    b.omegaCmd = B.roll_omega_reverse
    b.powered = true
    if not b.purgeTried then
      b.purgeTried = true
      if purgeSubject(state, b.jamId or b.gripId) then
        b.stats.purged = b.stats.purged + 1
      end
      b.jamId = nil
      b.busy = 0
    end
    if b.elapsed >= B.purge_seconds then
      b.purgeTried = nil
      setPhase(state, "running", nil)
    end
  elseif b.phase == "spindown" then
    b.omegaCmd = 0
    b.powered = math.abs(b.omega) > 0.05
    if feedCount > 0 then
      setPhase(state, "spinup", "ROLLS TO SPEED", 1.8)
    elseif math.abs(b.omega) <= 0.05 then
      b.omega = 0
      b.tracked = {}
      b.jamId = nil
      b.gripId = nil
      setEffectActive(state, "stack_smoke", false)
      setPhase(state, "idle", nil)
      emitEvent(state, "I", "grinder_idle", {
        fed = b.stats.fed, purged = b.stats.purged, jams = b.stats.jams,
      })
    end
  end

  -- Backstop of last resort. "idle" and "running" are steady states with
  -- their own exits (presence / canStop / run_timeout); every TRANSIENT phase
  -- must complete inside hard_reset_seconds or the machine scrubs itself.
  -- b.elapsed is cleared HERE rather than by setPhase, because setPhase
  -- early-returns when the phase is unchanged: a stalled spindown would
  -- otherwise re-enter this block every frame forever, wiping b.tracked and
  -- b.gripId each time and disarming jam detection permanently (round-1
  -- review, latent because omega decays from 1.30 to 0.05 in 1.53 s).
  if b.phase ~= "idle" and b.phase ~= "running"
    and b.elapsed > B.hard_reset_seconds then
    b.tracked = {}
    b.jamId = nil
    b.gripId = nil
    b.purgeTried = nil
    b.lastHeld = nil
    b.elapsed = 0
    if b.phase == "spindown" then
      showMessage("GRINDER RESET", 2.0)
    else
      setPhase(state, "spindown", "GRINDER RESET", 2.0)
    end
  end

  -- Slew the drive toward its command; omega is the ONLY speed authority for
  -- both the visual rotation and the pull.
  local step = B.omega_slew * dtSim
  if b.omega < b.omegaCmd then
    b.omega = math.min(b.omegaCmd, b.omega + step)
  elseif b.omega > b.omegaCmd then
    b.omega = math.max(b.omegaCmd, b.omega - step)
  end
  b.beltSpeed = B.belt_speed * math.min(1, math.abs(b.omega) / B.roll_omega_run)

  -- Scrub reversal clock: the sustained lateral press flips sides on a fixed
  -- half period, independent of the tooth-pass phase, so the two never lock
  -- into a standing wave.
  b.scrubClock = b.scrubClock + dtSim
  if b.scrubClock >= B.chew_scrub_half_seconds then
    b.scrubClock = 0
    b.scrubSign = -b.scrubSign
  end

  -- ---- 3. physics on every serviced subject -----------------------------
  local heldCount = 0
  if dtSim > 0 then
    for vehicleId in pairs(serve) do
      local vehicle = eligibleSubject(vehicleId)
      if vehicle then
        if serviceSubject(state, vehicle, dtSim, ex, ey, ez) then
          heldCount = heldCount + 1
          b.gripId = vehicleId
          b.lastHeld = b.clock
        end
      else
        b.tracked[vehicleId] = nil
      end
    end
  end
  if heldCount > 0 then
    b.busy = b.busy + dtSim
    b.load = math.min(1, b.load + dtSim * B.load_rise_rate)
  else
    b.busy = 0
    b.load = math.max(0, b.load - dtSim * B.load_fall_rate)
    if b.gripId and not b.tracked[b.gripId] then b.gripId = nil end
  end

  -- Discharge report: fires once per subject, the first time it settles on
  -- the pan below the drums.
  for vehicleId, track in pairs(b.tracked) do
    if track.onBelt and not track.reported and track.lp and track.lp.y > 0.5 then
      track.reported = true
      b.stats.fed = b.stats.fed + 1
      local damage = track.peakDamage or 0
      if damage > 0 then
        showMessage(string.format("DISCHARGED - scrap value %d", math.floor(damage)), 3.0)
      else
        showMessage("DISCHARGED to the pile", 2.4)
      end
      emitEvent(state, "I", "grinder_discharged", {
        subject_id = vehicleId, damage = damage,
      })
    end
  end

  -- ---- 4. show ----------------------------------------------------------
  b.rollAngle = b.rollAngle + b.omega * dtSim
  -- The drums counter-rotate: the LEFT one (authored -x) turns right-handed
  -- about authored +Y, the right one left-handed, so both nip faces travel
  -- DOWN - which is the sign convention rollerField() is derived from.
  --
  -- The axis handed to axisAngle is the WORLD image of the authored axis
  -- (proplib poses with `rotation * modelRotation`, i.e. in world space), so
  -- there is no hand-typed mirror sign to get wrong and the drums still turn
  -- about their own shafts when the prop is spawned on any heading. At
  -- identity yaw toWorldDir(0,1,0) = (0,-1,0), reproducing exactly the -1
  -- that catapult_seesaw and monster_flyswatter measured in play-testing.
  local rollAxis = toWorldDir(state, B.spin_axis_roller)
  setPartPose(state, "roller_left", nil, axisAngle(rollAxis, b.rollAngle))
  setPartPose(state, "roller_right", nil, axisAngle(rollAxis, -b.rollAngle))

  -- Slat pan: the slats march at the same belt speed the friction uses, and
  -- wrap every slat pitch. The slat array overruns both pulleys by one pitch
  -- so the wrap can never expose a gap.
  b.beltTravel = (b.beltTravel + b.beltSpeed * dtSim) % B.slat_pitch
  local inv = 1 / math.sqrt(1 + B.belt_grade * B.belt_grade)
  setPartPose(state, "belt_slats",
    vec3(0, b.beltTravel * inv, b.beltTravel * B.belt_grade * inv), nil)

  if b.powered then
    b.beaconAngle = b.beaconAngle + B.beacon_rate * dtSim
    b.fanAngle = b.fanAngle + B.fan_rate * dtSim
  end
  setPartPose(state, "beacon", nil,
    axisAngle(toWorldDir(state, B.spin_axis_beacon), b.beaconAngle))
  -- The fan disc lies in the authored Y-Z plane, so its axis is authored X.
  -- Round-1 review found it posed about Y: one blade invariant, the other
  -- four sweeping 0.52 m out of a 0.22 m thick radiator. Both the axis and
  -- the geometry now come from spec.PART_SPIN and the generator proves they
  -- agree.
  setPartPose(state, "power_fan", nil,
    axisAngle(toWorldDir(state, B.spin_axis_fan), b.fanAngle))

  setEffectActive(state, "grind_dust", heldCount > 0 and math.abs(b.omega) > 0.4)
  setEffectActive(state, "discharge_dust", beltBusy and b.beltSpeed > 0.5)
end
"""
