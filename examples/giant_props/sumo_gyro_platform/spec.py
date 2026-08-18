"""The Free-Pivot Sumo Gyro-Platform - authored constants for Blender + runtime.

A 26.2 m steel dish carried on a single spherical bearing and centred by four
gas-charged hydraulic rams. Drive on and the deck leans toward you: the tilt
is the steady-state of a real second-order rigid-body model whose forcing term
is the sum of every occupant's weight moment about the bearing. Two cars turn
it into sumo - whoever is further out wins the argument about which way "down"
points. Leave the ring and the rams bleed the deck back to level for the next
round.

Frames. Authored right-handed, metres, Z-up, +Y = drive direction. The prop
renders at world (-x, -y, z) (the shared MODEL_ALIGNMENT_ROTATION); pose
offsets and pose rotations are authored-frame and survive the flip because the
flip is a proper rotation.

Two hard engine problems this prop solves.

(1) The drivable deck MOVES, and it is a runtime TSStatic whose collision is a
    bake that only follows the visual when the runtime asks for a reload. The
    answer here is that the visual and the collision are driven from the SAME
    quantised state (``comX``/``comY``), so they are never in different places
    - the collision is not a lagging copy of the visual, it IS the visual. See
    "Committed pose" below for the derivation of the step size, the rate limit,
    and the measured reload budget.

(2) The boarding threshold is where a fixed ramp meets a surface that swings
    +/-1.26 m vertically. No arrangement of FIXED geometry can seal that
    junction (the annulus a fixed sill would occupy is swept by the deck at
    intermediate tilts - see RIM_SKIRT_Z), so the seal has to travel with the
    deck: the deck's rim ring girder is 1.40 m deep, and at every up-tilt its
    bottom flange stands BELOW the ramp lip. The doorway is a wall, never a
    hole. ``_assert_gate_seal`` in the generator proves it over the whole tilt
    range rather than at the endpoints.
"""

import math
import pathlib

MOD_ID = "ericrolph_sumo_gyro_platform"
DISPLAY_NAME = "The Free-Pivot Sumo Gyro-Platform"

# Files under assets/ the GAME opens by path at runtime, so they must ship to
# the player's disk. Staging is opt-in, never a blind copy of assets/ (that
# once put 11 MB of build inputs in a release zip). The scoreboard's webview
# loads local://local/vehicles/<mod>/scoreboard/screen.html.
SHIP_ASSETS = ("scoreboard/screen.html",)
VALUE_DOLLARS = 47000
ZIP_BASENAME = "sumo_gyro_platform_ericrolph.zip"

# ---------------------------------------------------------------------------
# Reference vehicle. Every clearance, lane width and zone below is sized from
# this. A BeamNG midsize (etk800 class) is ~2.0 m wide, 4.5 m long, 1.5 m
# tall; its spawn mass measured from the jbeam node weights is ~1600 kg.
# ---------------------------------------------------------------------------
CAR_WIDTH = 2.0
CAR_LENGTH = 4.5
CAR_HEIGHT = 1.5
CAR_MASS = 1600.0

# ---------------------------------------------------------------------------
# Deck geometry
# ---------------------------------------------------------------------------
# 12.45 m of dish = a 24.9 m circle of usable floor. A BeamNG sedan needs
# ~11.5 m to turn around, plus its own 4.5 m length: 16 m. Two cars need room
# to circle each other without either being forced over the lip, so the ring
# is sized at ~1.5 turning-circles across. Bigger than this and one car can
# simply run away from the fight forever.
DISH_RADIUS = 12.45
# The lip is a rolled kerb, not a wall: 0.30 m is about half a wheel diameter,
# high enough to stop a slow drift and to read as an edge from the driver's
# seat, low enough that a shove at 4 m/s puts you over it (which is the game).
LIP_HEIGHT = 0.30
LIP_CREST_R = 12.78
DECK_RADIUS = 13.10  # outer edge of the deck plate (lip outer face)
# Deck top surface at the axis. Derived, not chosen: the deck's underside at
# the rim must clear the fixed floor at maximum tilt, and the ramp grade must
# stay drivable. 1.90 satisfies both (see MOAT_FLOOR_Z and RAMP_G1).
DECK_TOP_Z = 1.90
# Concave dish: 0.18 m of rise from centre to lip foot. Deliberately small.
# The dish exists so the centre of the ring is a genuine refuge (cars settle
# there when the deck is level) and so re-levelling gently gathers survivors
# inward, but its rim slope (2 * 0.18 / 12.45 = 2.9%, 1.7 deg) must stay well
# under the tilt authority (5.5 deg) or the dish would cancel the game.
DISH_RISE = 0.18
# 0.50 m box section over the field of the dish. A 26 m plate girder deck
# needs real depth even where nothing else demands it.
DECK_THICKNESS = 0.50
# Spherical bearing centre. A ball joint (not a two-ring gimbal) because a
# sphere is invariant under rotation about its own centre: the socket never
# needs running clearance, so there is no trunnion the tilting deck can strike.
PIVOT_Z = 0.95
BALL_RADIUS = 0.62

# Mechanical stops. 5.5 deg = 9.6% grade at the rim, which rolls a car with
# its brakes off, costs real control authority at speed, and still lets a
# stranded car drive back up (well under the 23% grade that stalls a BeamNG
# automatic at creep throttle - AGENTS.md, centrifuge round 14).
TILT_MAX_DEG = 5.5
TILT_MAX_RAD = math.radians(TILT_MAX_DEG)

# ---------------------------------------------------------------------------
# Rim ring girder - the thing that makes the boarding threshold safe
# ---------------------------------------------------------------------------
# The deck's rim is not a 0.50 m plate edge, it is a 1.40 m deep ring girder
# whose bottom flange is haunched back to the general soffit at
# GIRDER_HAUNCH_R. That depth is DERIVED from the boarding threshold, not
# chosen for looks:
#
#   At an up-tilt of u the deck's gate edge lifts DECK_RADIUS * sin(u) and
#   retreats, so the ramp lip (fixed, at z = RAMP_Z0) faces open air unless
#   something rigidly attached to the deck still spans that height. Nothing
#   FIXED can do it: the annulus a fixed sill would occupy (r 12.93 .. 13.10
#   at the ramp lip's own height) is swept by the deck itself at |tilt| < 1.3
#   deg, so a sill there would be struck by the deck every round.
#
#   So the seal travels with the deck. Requiring the girder's bottom-outer
#   corner to sit at least 0.10 m BELOW the ramp lip at full up-tilt gives
#     RIM_SKIRT_Z <= PIVOT_Z + (RAMP_Z0 - 0.10 - PIVOT_Z - R sin u) / cos u
#   = 0.731 m. 0.70 leaves 0.13 m of overlap; the residual horizontal gap
#   between the girder web and the ramp lip is 0.049 m at full up-tilt and
#   less at every smaller angle (both asserted in _assert_gate_seal).
#
# Cost of the depth: at full DOWN-tilt the same corner swings to z = -0.554,
# which is why the fixed floor carries a drain moat under the rim (below).
RIM_SKIRT_Z = 0.70
GIRDER_HAUNCH_R = 12.40

# ---------------------------------------------------------------------------
# Fixed structure
# ---------------------------------------------------------------------------
UNDER_DECK_Z = 0.12  # fixed base plate under the deck (a floor, not a trap)
# Drain moat under the rim girder. Its floor clears the girder's lowest swept
# point (-0.554 m at full down-tilt) by 0.196 m. It runs full circle because a
# gated trench would need end caps, a gated cage and a second gate window to
# keep consistent - and because a continuous channel around a machine pit is
# what the real thing would have. Nothing can reach it: the guard kerb seals
# the ring everywhere except the doorway, and the doorway is sealed by the
# girder itself.
MOAT_INNER_R = 12.40
MOAT_FLOOR_Z = -0.75
# Guard kerb. Its job is to make the volume under the deck unreachable
# everywhere the boarding ramp does not: at full tilt the high rim stands
# 2.5 m off the floor, and a car that drove in there would be pinned by a
# static collision mesh coming down at 0.16 m/s. 1.05 m with a 0.35 m
# 45-degree toe leaves a 0.70 m vertical face - unclimbable from the apron -
# while still being below the deck rim at full down-tilt, so a shoved car
# always has somewhere to go over the top.
WALL_INNER_R = 13.30
WALL_OUTER_R = 13.95
WALL_TOP_Z = 1.05
WALL_TOE_Z = 0.35
WALL_TOE_R = 14.30
# Landing apron: a catch berm. It rises away from the wall so a car that comes
# off the deck rolls back down to the wall foot instead of touring the map,
# then falls away again to meet the terrain flush at its outer edge (a lip
# there would be a permanent 0.4 m step onto bare ground).
APRON_INNER_R = 14.30
APRON_CREST_R = 20.00
APRON_CREST_Z = 0.40
APRON_OUTER_R = 25.00

# Boarding ramp, on the -Y side so the player drives IN along +Y.
RAMP_AZIMUTH_DEG = 270.0
# 7.0 m wide = two 2.0 m cars abreast with 1.0 m of margin each side. The gap
# cut in the lip and the ramp deck are computed from this ONE number so the
# opening and the thing that fills it can never disagree (AGENTS.md).
RAMP_HALF_WIDTH = 3.50
RAMP_OUTER_R = 26.20
RAMP_KERB_HEIGHT = 0.32
# The ramp crest is built by interpolating GRADE and integrating, never by
# blending two height datums (AGENTS.md round-14 stall lesson). It starts at
# the deck's own outward slope at the rim and eases to the running grade over
# RAMP_CREST_RUN metres; the running grade then falls out of the arithmetic.
RAMP_CREST_RUN = 3.0
# The embankment's inner end is closed by a vertical curtain. It stands 0.16 m
# OUTBOARD of the deck edge because the deck's widest swept point (the lip's
# outer top corner at full down-tilt) reaches r = 13.171: a curtain at
# DECK_RADIUS was being sliced by the deck edge every time the ring leaned
# toward the ramp. The 0.16 m of ramp deck inboard of the curtain is a nosing,
# and the deck's own girder web stands directly behind it when the ring is
# level, so the joint reads as a shutline rather than a gap.
MOUTH_CURTAIN_R = 13.26

# Scoreboard mast, beside the ramp so it is readable from the approach and
# from the deck. Azimuth measured from +X in the authored frame; the cabinet
# faces SCOREBOARD_FACING_DEG, chosen to split the difference between "look at
# the deck" (63 deg from this position) and "look down the ramp" (18 deg).
SCOREBOARD_AZIMUTH_DEG = 243.0
SCOREBOARD_RADIUS = 17.6
SCOREBOARD_FACING_DEG = 42.0

# Hydraulic power unit. The gimbal, the bearing and the rams all live under a
# 26 m lid and are invisible in play, so the machine's power train is put
# where the player actually stands: a skid on the apron with an accumulator
# bank and a pipe run disappearing under the guard kerb. Placed 40 deg round
# from the ramp - clear of the embankment flank (which subtends 19.9 deg at
# this radius) and of the approach chevrons.
HPU_AZIMUTH_DEG = 310.0
HPU_RADIUS = 16.6

# Spin drive (2026-08-13 player round: "an electric motor fly wheel that
# rotates against the larger sumo arena circle to create the motion"). The
# deck is turned by a rubber-tyred flywheel bearing on the arena's own rim,
# standing on the apron in the same bay as the skid that powers it - the one
# piece of this machine's drive train a player can watch doing its job.
# Everything here is DERIVED, never drawn by eye:
#   * the tread has to MEET the deck edge, so the axis stands at
#     DECK_RADIUS + tread radius + a 20 mm kiss gap (the gap is what keeps the
#     wheel out of the deck when the ring leans toward it: a leaning deck's
#     widest swept point is 13.171 m, and the tread's inner face is at 13.12,
#     so they never interpenetrate - see _assert_geometry).
#   * the tread face has to clear the guard wall crest (WALL_TOP_Z) or the
#     wheel would be buried in the wall it overhangs.
#   * the wheel meets the deck ABOVE that crest, which is also the only band
#     of the rim a player can see - so when a full down-tilt drops the rim out
#     of the tread's reach, the wall is already hiding the gap.
# 20 deg round from the skid and AWAY from the ramp. Three constraints fix
# this number: the wheel's footprint reaches r 16.5 and the skid occupies
# 15.4..17.8, so they cannot share an azimuth; the boarding embankment's
# flank subtends 270 +/- 16.7 deg out here, and the wheel subtends +/- 6.5
# deg, so anything inboard of ~294 deg would have the tread buried in the
# ramp's flank (the first cut at 290 did exactly that); and the nearest
# nobori sits at 335 deg but out at r 21.5, well clear radially.
DRIVE_AZIMUTH_DEG = HPU_AZIMUTH_DEG + 20.0
# 1.70 m of tread radius, a 3.4 m wheel. The first cut ran 1.22 and rendered
# as a dark blob against a 26 m arena - a drive nobody would read as the
# cause of anything. Size is legibility here, and the bigger wheel also turns
# SLOWER for the same deck speed (ratio 7.7 rather than 10.7), which is what
# makes the rotation itself readable instead of a strobe.
DRIVE_WHEEL_R = 1.70
# 45 mm, not the 20 it looks like it wants: the deck's top-outer corner
# swings OUTWARD as the ring leans toward the drive, and inside the tread's
# own height band it reaches r 13.134 (derived and asserted in the
# generator's _assert_geometry, swept over the whole tilt range). A tighter
# kiss would have the deck eating the tyre for a couple of degrees of lean.
DRIVE_KISS_GAP = 0.045
DRIVE_AXIS_R = DECK_RADIUS + DRIVE_WHEEL_R + DRIVE_KISS_GAP
DRIVE_FACE_LO = WALL_TOP_Z + 0.05
DRIVE_FACE_HI = 2.53
DRIVE_HUB_Z = 2.86          # belt pulley deck above the wheel
# Rolling without slip: the wheel turns DECK_RADIUS / tread times per deck
# turn, and the opposite way round. The runtime derives the wheel's pose from
# the deck's OWN measured angle change, so spin-up, decay and the wind-back
# home all drive it correctly with no second integrator to keep in step.
DRIVE_RATIO = DECK_RADIUS / DRIVE_WHEEL_R

# ---------------------------------------------------------------------------
# Match scoreboard (2026-08-13 match-system round). Replaces the leaning
# apron kanban: a double-faced tower at the same site, one face to the ring,
# one to the world. NO runtime text exists in this engine (textures are baked -
# the "emissives inert" half of this parenthesis is RETIRED 2026-08-15, round
# 17), so the board is the pack's honest-machine idiom: corner
# COLORS carry identity (East vermilion / West cream, real banzuke
# convention; entry toasts carry the actual vehicle names), win-pip pucks
# carry the score (first to SET_WINS takes the set), and WIN/LOSS plates pose
# into windows when a match is decided. Everything hides by sliding BEHIND
# the apertured faces into the enclosed cabinet/pedestal shaft - the CHIEF
# field-coupling trick, made two-faced by keeping every stroke vertical.
# ---------------------------------------------------------------------------
SB_X = 0.0
SB_Y = 17.8            # tower centre; faces normal +/-Y (ring side is -Y)
SB_PED_W = 6.0         # enclosed pedestal (hides retracted plates), z 0..TOP
SB_PED_D = 1.05
SB_PED_TOP = 2.00
SB_CAB_W = 6.2         # cabinet with the two display faces
SB_CAB_D = 1.30
SB_TOP = 5.10
SB_FACE_RECESS = 0.55  # interior display plates sit this far off centre plane
SB_COL_X = 1.75        # corner column centres: EAST at -X, WEST at +X
SB_LABEL_Z = 4.72      # static EAST / WEST label strips
# Win pips: 5 per corner per face in a row; a pip part carries its puck for
# BOTH faces and hides by dropping SB_PIP_HIDE behind the face strips.
SB_PIP_PITCH = 0.48
SB_PIP_Z = 3.32
SB_PIP_CELL = 0.42     # face aperture cell for one pip
SB_PIP_R = 0.155
# 1.40, not 0.80: the name windows opened in the band a hidden puck used to
# park in, and a "hidden" pip framed by a lit display is not hidden. The
# deeper drop parks them behind the face sheet and inside the collar skirt.
SB_PIP_HIDE = 1.40
# Result window: the WIN plate is authored AT the window, LOSS one shift
# below; pose +shift shows LOSS, pose -SB_RESULT_HIDE parks both in the
# pedestal shaft.
SB_RESULT_Z = 4.05
SB_RESULT_W = 1.50
SB_RESULT_H = 0.55
SB_RESULT_SHIFT = 0.62
SB_RESULT_HIDE = 1.35
# Name band (2026-08-13 player round: "incorporate the cars names into the
# score board appropriately"). A dark recessed window under each corner's
# pips, framed like the other displays, carrying that competitor's vehicle
# name. The NAME is the engine's one dynamic-text channel - baked textures
# cannot change - so the hardware is the window and the runtime draws the
# name INTO it, on whichever face the camera is on. Text that belongs to a
# window reads as part of the board; the same text floating over the roof
# read as debug overlay (it was).
SB_NAME_Z = 2.60
SB_NAME_W = 2.36
SB_NAME_H = 0.80
# The page is TWO-UP - east cell then west cell - so one webview feeds all
# four quads (two corners x two faces) and both names can never disagree.
# Page aspect must equal the WINDOW's aspect per half or the type stretches:
# 755/256 = 2.949 against 2.36/0.80 = 2.950.
SB_NAME_PX_H = 256
SB_NAME_PX_W = 2 * 755

# ---------------------------------------------------------------------------
# THE PA HORN POLE (2026-08-14 player round: "a classic speaker horn set
# facing in four directions on a speaker pole as tall as a street light near
# the score board ... We made one for the Pachinko mod so let's reuse that").
#
# The pachinko machine's cluster, ported whole: same hardware vocabulary, same
# probed emitter recipe, re-sized and re-aimed for this venue. Read by THREE
# consumers - the Blender generator draws the standard, the cage gives it a
# body cars bounce off, and the GE runtime hangs four scene sound emitters at
# the horn mouths and routes every announcer cue through them.
#
# WHERE IT STANDS. Beside the scoreboard's west shoulder and just outboard of
# its back face, so the pole never crosses either display face from the ring
# or from the approach. Both offsets are measured off the cabinet itself
# rather than typed, so moving the board moves the pole with it.
HORN_POLE_X = SB_CAB_W / 2.0 + 2.20        # 5.30, clear of the cabinet's end
HORN_POLE_Y = SB_Y + SB_CAB_D / 2.0 + 0.15  # 18.60, just behind its back face
HORN_POLE_R = math.hypot(HORN_POLE_X, HORN_POLE_Y)
# The apron is a berm, so the foot sits wherever the berm is at that radius
# (the same arithmetic the generator's apron_z runs, asserted equal there).
HORN_APRON_Z = APRON_CREST_Z * math.sin(
    math.pi * (HORN_POLE_R - APRON_INNER_R) / (APRON_OUTER_R - APRON_INNER_R)
)
HORN_POLE_H = 9.60          # a real 9-10 m street light, as asked
HORN_POLE_BURY = 0.20       # foot buried, so a hump of terrain cannot gap it
HORN_POLE_R0 = 0.185        # shaft radius at grade
HORN_POLE_R1 = 0.115        # shaft radius under the cap
HORN_FLANGE_R = 0.44
HORN_AXIS_H = 8.62          # horn cluster axis, above the foot
HORN_POLE_TOP_Z = HORN_APRON_Z + HORN_POLE_H
HORN_AXIS_Z = HORN_APRON_Z + HORN_AXIS_H
# SCALE. Pachinko caricatured its bells to 1.40 m against a 54 m machine. This
# venue is smaller and the pole stands 19 m from the ring centre, so the bell
# is sized for legibility from where a competitor actually sits: 1.10 m
# subtends 3.3 deg at the deck centre, which is about what the board's own
# result plates subtend from the same seat. The whole ASSEMBLY outboard of the
# yoke - driver, U-bracket, bell - scales with it; the POLE does not, because
# a street light is a street light whatever it carries.
HORN_BELL_D = 1.10
HORN_SCALE = HORN_BELL_D / 1.40
HORN_BELL_LEN = 0.50 * HORN_BELL_D
HORN_DRIVER_LEN = 0.34 * HORN_BELL_D
HORN_DRIVER_R = 0.186 * HORN_BELL_D
HORN_THROAT_R = 0.143 * HORN_BELL_D
HORN_REAR_R = 0.42          # driver rear cap, off the pole axis (clears the
                            # yoke collar at 0.19 and leaves the arm visible)
HORN_MOUTH_R = HORN_REAR_R + HORN_DRIVER_LEN + HORN_BELL_LEN
# The cluster's widest horizontal reach: a bell rim point, which is a mouth
# radius out along its own axis and a bell radius across it.
HORN_ENVELOPE_R = math.hypot(HORN_MOUTH_R, HORN_BELL_D / 2.0 + 0.052)
# AIM. One horn points straight at the ring centre - which is where the cars,
# the shikiri circle and the player's camera all are - and the other three
# follow at 90 deg. That also puts the ring-facing horn within 10 deg of the
# boarding approach, so the announcement reaches a car queuing at the ramp
# from the same mouth it reaches a car on the clay.
HORN_AIM_DEG = math.degrees(math.atan2(-HORN_POLE_Y, -HORN_POLE_X)) % 360.0
HORN_DIRS = [
    (round(math.cos(math.radians(HORN_AIM_DEG + 90.0 * k)), 6) + 0.0,
     round(math.sin(math.radians(HORN_AIM_DEG + 90.0 * k)), 6) + 0.0)
    for k in range(4)
]
HORN_MOUTHS = [
    [round(HORN_POLE_X + dx * HORN_MOUTH_R, 4) + 0.0,
     round(HORN_POLE_Y + dy * HORN_MOUTH_R, 4) + 0.0,
     round(HORN_AXIS_Z, 4) + 0.0]
    for dx, dy in HORN_DIRS
]
# CLEARANCE, arithmetic rather than eye. Unlike pachinko's pole this one
# stands ON a landing apron - cars come off the deck in every direction, so
# there is no "off the drive surface" spot to hide it in. It is therefore
# given a body in the cage (the scoreboard tower's own box-lattice idiom) and
# the arithmetic below only has to keep it out of the OTHER structures.
assert HORN_POLE_R - HORN_ENVELOPE_R > DECK_RADIUS + 1.0, (
    "the horn pole reaches the deck's swept envelope")
assert APRON_INNER_R < HORN_POLE_R < APRON_OUTER_R, (
    "the horn pole's foot is off the apron")
# The scoreboard cabinet, in plan. The bells hang 3.5 m above its roof so this
# is a legibility margin, not a collision one - but a bell overhanging the
# board reads as clutter from the ring.
_SB_NEAR = (SB_CAB_W / 2.0, SB_Y + SB_CAB_D / 2.0)
assert math.hypot(HORN_POLE_X - _SB_NEAR[0], HORN_POLE_Y - _SB_NEAR[1]) \
    >= HORN_ENVELOPE_R + 0.60, "a horn bell overhangs the scoreboard cabinet"

# ---------------------------------------------------------------------------
# Match rules. Two competitors, one loser: the first car with ANY OOBB corner
# past the clay (KO_RADIUS, the player's "even partially off the brown
# circle" rule) is out. No draws - the spin ramp guarantees a decision.
# ---------------------------------------------------------------------------
SET_WINS = 5                # a full pip row = the set; scores then clear
# Player live round 2026-08-13: KO at the clay edge read as losing "at the
# red ring" - too strict. The loss line is now the deck plate's VERY OUTER
# edge: you are out when part of the car hangs past the machine itself.
KO_RADIUS = DECK_RADIUS     # 13.10
STAGE_RADIUS = 4.6          # both cars this close to the shikiri-sen...
STAGE_SPEED = 1.0           # ...this slow...
STAGE_MIN_GAP = 2.2         # ...not touching...
STAGE_HOLD_SECONDS = 1.2    # ...for this long, on opposite sides -> countdown
COUNTDOWN_GO_SECONDS = 1.65 # where "GO" lands in the 1.875 s clip (tunable)
COUNTDOWN_STOP_SECONDS = 2.60  # stop the source inside the 2.5 s silent pad
# Spin escalation: continuous, never stepped. The deck is axisymmetric, so
# the VISUAL spins free (no extra collision bakes - a spun disc bakes to the
# same shape, the 15 mm paint reliefs are inside the drivable cap); cars are
# carried by a tangential velocity field, the washer/centrifuge recipe. A
# field-matched car travels the tangent unless its tires supply omega^2*r of
# centripetal grip - at full omega that is more than rubber has anywhere
# outside the centre, which is what ends stalemates.
SPIN_OMEGA_MAX = 2.0        # rad/s; 19 RPM, rim surface 26 m/s
SPIN_ACCEL = 0.020          # rad/s^2: 100 s from calm to unsurvivable
SPIN_DECEL = 0.35           # rad/s^2 spin-down after the KO
SPIN_DRAG_ACCEL = 7.0       # m/s^2 cap on the field's tangential correction
SPIN_MIN_R = 1.2            # no field inside the shikiri circle
# The arena is a machine with a DOORWAY: the deck's lip carries a gap at the
# ramp, and the deck's baked collision is authored at spin 0. A match must
# therefore end with the deck wound back to its home angle, or the doorway you
# can SEE stops agreeing with the one you can drive through (live round
# 2026-08-13: "the entrance isn't rotated in place correctly"). The drive
# wheel walks it home during re-levelling, after the cars have been set down.
SPIN_HOME_RATE = 0.9        # rad/s wind-back: <= 3.5 s from the worst angle
SPIN_HOME_EPS = 0.004       # rad (~0.23 deg) - close enough to call it home
DECIDED_HOLD_SECONDS = 3.2  # savour the KO before the machine tidies up
MATCH_MAX_SECONDS = 300.0   # watchdog only; a void match scores nobody
# Post-match: both competitors are set down side by side in front of the
# ramp, facing it, with room to line up again.
# 31.5 (was 27.0): live round 2026-08-13 set cars down AT the ramp foot -
# player asked for a full car length of breathing room behind it.
RESET_SPOT_DIST = 27.0 + CAR_LENGTH
RESET_SPOT_GAP = 2.9        # half-gap sideways between the two spots

# Reset buttons on BOTH pedestal faces (player round 2026-08-13: the board
# reads from ring and outside, so its one control must too). "face" is the
# outward normal sign in y: +1 outward, -1 toward the ring; the generator
# mirrors the cap dressing and click-box anchor with it.
PANEL_BUTTONS = (
    {"id": "btn_reset", "title": "Sumo Scoreboard: Reset Competitors & Scores",
     "position": (0.0, SB_Y + SB_PED_D / 2.0, 1.35), "cap": "round_white",
     "label": "RESET", "face": 1.0},
    {"id": "btn_reset_ring",
     "title": "Sumo Scoreboard: Reset Competitors & Scores",
     "position": (0.0, SB_Y - SB_PED_D / 2.0, 1.35), "cap": "round_white",
     "label": "RESET", "face": -1.0},
)
PANEL_FRAME_X = (1.2, SB_Y + SB_PED_D / 2.0, 1.35)
PANEL_FRAME_Y = (0.0, SB_Y + SB_PED_D / 2.0, 2.05)

# ---------------------------------------------------------------------------
# Committed pose: how the collision follows the visual
# ---------------------------------------------------------------------------
# The deck is one TSStatic with collision. Static collision only updates on
# be:reloadCollision(), which is GLOBAL and not free, so the deck cannot be
# re-baked every frame. Instead the deck is POSED (visual) and BAKED
# (collision) from the same committed angles:
#
#   TILT_BAKE_STEP_DEG   the size of one committed move. The deck does not
#                        glide: it advances in steps of EXACTLY this angle, at
#                        most one per TILT_BAKE_INTERVAL. 0.085 deg at the
#                        13.10 m rim = 0.0194 m, inside the pack's +/-0.02 m
#                        relief budget for anything a car drives over (a step
#                        deeper than a sidewall and narrower than a contact
#                        patch is what destroyed the centrifuge's tyres).
#   TILT_BAKE_INTERVAL   minimum seconds between two reloads: a hard ceiling
#                        of 8 global collision rebuilds per second.
#   TILT_RATE_MAX_RAD_S  = step / interval, EXACTLY. Not an independent knob:
#                        deriving it this way is what keeps the committed pose
#                        within one step of the physical one. Physically it is
#                        the rams' hydraulic flow limit; at the rim it is
#                        0.1555 m/s.
#
# THE STEP MUST BE CLAMPED, NOT ASSUMED. An earlier cut of this file claimed
# "the committed pose can never lag by more than one step" because
# rate_max = step / interval. That is false, and the harness proves it: the
# deadband ``err < bake_step`` is evaluated once per frame and the integrator
# advances rate_max*dt past it, so the delivered step is
# (bake_step + rate_max*dt)*R - measured 26.67 mm at 60 fps and 34.28 mm at
# the dt clamp with the old constants, against a claimed 22.86 mm. The runtime
# now advances the committed pose TOWARD the physical one by at most one step
# and carries the remainder, which makes the delivered step exactly
# bake_step*R at every frame rate. Harness (60 s per case, this file's
# constants, five load profiles):
#
#   max committed move at the 13.10 m rim   19.43 mm at 144 / 60 / 30 / 20 fps
#                                           (identical at all four - that IS
#                                            the point of the clamp)
#   reloads per second, ring idle           0.00
#   reloads per second, none in watch range 0.00  (occupancy-gated, below)
#   reloads per second, one car centre->lip 0.88  (peak 7)
#   reloads per second, one car circling
#     r = 10 m at 8 m/s                     7.42  (peak 8)
#   reloads per second, two cars scrapping  7.08  (peak 8)
#   re-level from the stops, survivor       10.05 s, 63 reloads
#   re-level from the stops, ring empty     10.05 s,  0 reloads
#
# The circling case IS the operating point of a live round, and it sits at the
# ceiling: a 184-tonne deck chasing a load vector that rotates at 0.8 rad/s
# runs at its flow limit continuously. So the honest budget to design against
# is 8/s while a vehicle is within reach, not the 0.9/s of a car driving out
# to the lip. Three things keep that bounded, and the ORDER of the first one
# is load-bearing:
#
#   * TILT_BAKE_INTERVAL gates EVERY rebuild, the owed "debt" bake included.
#     An earlier cut ran the debt branch before the interval gate, which made
#     the old "ceiling is 1/interval by construction" claim false: a vehicle
#     dithering on the watch boundary forced an unthrottled rebuild on every
#     inward crossing - worst case one per two frames, ~30/s. The debt branch
#     now sits BEHIND the clock, so 8/s is the ceiling by the order of the
#     gates. After a long unwatched glide the clock is already far past the
#     interval, so the first watched frame still bakes immediately;
#     throttling only ever bites on rapid re-crossings.
#   * The runtime skips the rebuild entirely while no eligible vehicle is
#     inside the watch radius (an idle machine and an empty re-level cost the
#     engine nothing, and the visual is then free to glide), and the watcher
#     test carries BAKE_WATCH_HYSTERESIS so a car sitting exactly on the
#     boundary cannot toggle the watched state frame to frame.
#   * The interval self-derates on hardware where a rebuild is actually
#     expensive. The reload itself is DEFERRED by the framework (the helper
#     only sets a pending flag; be:reloadCollision fires after part posing),
#     so the cost cannot be timed at the call site: the runtime instead
#     measures whole-frame wall time and keeps two EMAs - frames that carried
#     a bake and frames that did not - whose difference is the rebuild's real
#     cost on the player's hardware. The effective interval stretches by
#     cost / BAKE_COST_BUDGET_MS (clamped to BAKE_BACKOFF_MAX), and the flow
#     limit follows step / interval_eff in LOCKSTEP, so a derated machine
#     leans slower instead of letting the committed pose lag the physical one
#     - the one-step invariant survives the backoff. The measured cost ships
#     in every stats event as bake_ms, so live captures on real hardware
#     answer the question this budget used to leave open.
#
# And the prop never calls launchSubject, addSubjectVelocity or teleportSubject
# at all - not once, anywhere. Cars move because the floor moved, which is the
# whole point of the machine.
TILT_BAKE_STEP_DEG = 0.085
TILT_BAKE_INTERVAL = 0.125
TILT_BAKE_STEP_RAD = math.radians(TILT_BAKE_STEP_DEG)
TILT_RATE_MAX_RAD_S = TILT_BAKE_STEP_RAD / TILT_BAKE_INTERVAL
# Guard kerb outer face plus one car length, plus the ground a 60 m/s
# (216 km/h) approach covers in one full bake interval. The debt bake is
# throttled by the interval like every other bake, so the stale-bake exposure
# window is up to TILT_BAKE_INTERVAL rather than one frame - the radius buys
# that time back: a car first watched out here cannot reach any pose of the
# deck before the owed rebuild is allowed to land.
BAKE_APPROACH_SPEED = 60.0
BAKE_WATCH_RADIUS = (
    WALL_OUTER_R + CAR_LENGTH + BAKE_APPROACH_SPEED * TILT_BAKE_INTERVAL
)
# A watcher stays a watcher until it leaves radius + hysteresis: without the
# band, a car parked exactly on the boundary flips watchers 0<->1 with
# position noise, and each flip re-arms a debt bake.
BAKE_WATCH_HYSTERESIS = 3.0
# Adaptive backoff: stretch = clamp(measured bake_ms / budget, 1, max).
# 3 ms is ~20% of a 60 Hz frame; at the 4x cap the ceiling degrades to 2/s
# and the rim flow limit to 39 mm/s - slower, never wrong.
BAKE_COST_BUDGET_MS = 3.0
BAKE_BACKOFF_MAX = 4.0
BAKE_COST_EMA_ALPHA = 0.2

# ---------------------------------------------------------------------------
# Rigid-body model of the deck (the numbers the Lua integrates)
# ---------------------------------------------------------------------------
# Mass budget of the authored machine (a fictional but self-consistent one):
#   deck plate    25 mm top plate + ribs + soffit ~= 300 kg/m^2 over
#                 pi * 13.1^2 = 539 m^2                        -> 160 000 kg
#   rim girder    1.40 m deep welded ring section + haunch +
#                 the rolled kerb on top of it, ~640 kg/m over
#                 the 81 m circumference                       ->  52 000 kg
# Second moment about any diameter through the bearing:
#   disc   M R^2 / 4 = 160000 * 13.10^2 / 4                    -> 6.86e6
#   ring   M R^2 / 2 =  52000 * 12.95^2 / 2                    -> 4.36e6
#   hub, socket, ram eyes, anti-yaw lugs (lumped, < 1 %)       -> 0.08e6
INERTIA = 1.13e7  # kg m^2

# Restoring stiffness. The deck's mass centre sits 0.66 m ABOVE the bearing
# (212 t at a combined centroid of 1.61 m, bearing at 0.95 m), so gravity is
# DEstabilising:
#   K_gravity = -212000 * 9.81 * 0.658 = -1.37e6 N m / rad
# Four gas-charged rams on a 5.2 m bolt circle supply the stability. For rams
# at 0/90/180/270 deg the pair sum is isotropic: K_rams = 2 k a^2, so
#   k = (2.57e6 + 1.37e6) / (2 * 5.2^2) = 72.8 kN/m per ram.
# The net 2.57e6 N m/rad is chosen from the feel target, not the other way
# round: one 1600 kg car parked 10 m out gives
#   psi = 1600 * 9.81 * 10 / 2.57e6 = 0.0611 rad = 3.50 deg,
# so a lone driver gets a strong, obvious lean; at the 12.45 m lip foot the
# same car makes 4.36 deg. A single car can NEVER reach the 5.5 deg stops
# (that needs 15.7 m of leverage on a 12.45 m dish) - the stops only ever
# engage when two cars gang up on one side, which is exactly the moment the
# machine should feel like it has run out of patience.
STIFFNESS = 2.57e6  # N m / rad
RAM_BOLT_CIRCLE = 5.2

# Damping ratio 0.75: settles without oscillating, but keeps a little
# overshoot so the deck "breathes" when a car crosses the centre.
#   c = 2 * zeta * sqrt(K I) = 1.5 * sqrt(2.57e6 * 1.13e7) = 8.08e6
# Natural frequency sqrt(K/I) = 0.477 rad/s -> a 13.2 s free period; this is
# a 212-tonne machine and it must not twitch.
# 0.45 (was 0.75): player live round 2026-08-13 - "the wobble should be a
# bit more". Underdamped on purpose now: the deck overshoots and rocks a
# visible beat or two under a moving load instead of oozing to steady state.
DAMPING = 2.0 * 0.45 * math.sqrt(STIFFNESS * INERTIA)
# Re-levelling closes the ram bypass valves: zeta = 1.05, no overshoot, so the
# deck cannot swing past level and tip a survivor the other way.
DAMPING_RELEVEL = 2.0 * 1.05 * math.sqrt(STIFFNESS * INERTIA)

# Ram geometry. The eye sits on the deck soffit at the bolt circle; the foot
# is 2.2 m further out on a fixed tower so the ram is a 2.37 m strut rather
# than a 1.05 m stub - stroke then reads as +9.6/-5.8 % of length instead of
# a comic 48 %. The foot tower top clears the deck soffit at full tilt by
# 0.20 m; the generator asserts it.
RAM_EYE_R = RAM_BOLT_CIRCLE
RAM_EYE_Z = DECK_TOP_Z + DISH_RISE * (RAM_EYE_R / DISH_RADIUS) ** 2 - DECK_THICKNESS
RAM_FOOT_R = 7.40
RAM_FOOT_Z = 0.55
RAM_REST_LENGTH = math.hypot(RAM_FOOT_R - RAM_EYE_R, RAM_EYE_Z - RAM_FOOT_Z)
# Barrel length as a fraction of the rest length. The rod is what extends; the
# barrel is a rigid steel tube and does NOT change length (the previous cut
# scaled the whole assembly, barrel included, which is not how a ram works).
# 0.62 leaves the rod 0.24 m inside the barrel at full extension.
RAM_BARREL_FRACTION = 0.62
RAM_ROD_OVERLAP = 0.10  # of rest length, how far the rod starts inside the barrel

# Occupant torque is clipped at 2.5x the torque needed to sit on the stops.
# Nothing sane exceeds it (that is four 1600 kg cars at the lip, or one
# 40 t truck); the clip only stops a hauled-in extreme from making the
# integrator stiff. The stops bound the ANGLE regardless.
TORQUE_CAP = 2.5 * STIFFNESS * TILT_MAX_RAD

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
PALETTE = {
    f"{MOD_ID}_deck_plate": {
        # Dohyo clay. The fighting surface is painted steel in the ochre of a
        # real sumo ring, so the machine reads SUMO at first glance instead of
        # helipad - the whole colour story hangs off this one surface.
        # 0.47/0.33/0.19 is real dohyo ochre-brown: the previous 0.56/0.41/0.25
        # rendered milk-coffee pink under flat light and threw away the
        # contrast against the sand apron and the deck's white paint marks.
        "texture": {"family": "painted_metal", "params": {"base": [0.47, 0.33, 0.19]}},
        "color": [0.47, 0.33, 0.19, 1.0],
        # Matte: clay paint must not mirror the sky - at glancing angles any
        # metallic sheen washes the warm deck cold.
        "metallic": 0.05,
        "roughness": 0.68,
    },
    f"{MOD_ID}_deck_hazard": {
        "texture": {"family": "hazard_chevron"},
        "color": [0.94, 0.74, 0.09, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    f"{MOD_ID}_tawara": {
        # Rice-straw bale tone for the deck's rolled kerb. On a real dohyo
        # the ring boundary IS a course of half-buried tawara, and the lip
        # wearing construction amber was the one surface inside the clay
        # still saying "helipad". Straw family already ships in the pack;
        # this is only a new colourway of it.
        "texture": {"family": "straw", "params": {"base": [0.72, 0.58, 0.30]}},
        "color": [0.72, 0.58, 0.30, 1.0],
        "metallic": 0.0,
        "roughness": 0.8,
    },
    f"{MOD_ID}_steel": {
        # Graphite structural steel, darker than the old mid-grey: the clay
        # deck, vermilion arena wall and gold hazard bands carry the colour
        # story, and the frame should read as the thing holding them up.
        "texture": {"family": "steel_worn", "params": {"base": [0.40, 0.42, 0.46]}},
        "color": [0.40, 0.42, 0.46, 1.0],
        "metallic": 0.85,
        "roughness": 0.38,
    },
    f"{MOD_ID}_concrete": {
        # Warm raked-sand tone: the ring around a real dohyo is brushed sand
        # (the ja-no-me), not machine-hall grey.
        "texture": {"family": "concrete", "params": {"fine": True, "base": [0.67, 0.62, 0.53]}},
        "color": [0.67, 0.62, 0.53, 1.0],
        "metallic": 0.0,
        "roughness": 0.85,
    },
    f"{MOD_ID}_concrete_dark": {
        # The raked-sand tone's ~13% darker sibling. The apron lathe
        # alternates the two per ring band so the sand annulus reads as
        # concentric ja-no-me rake bands at distance - full rings, tonally
        # uniform along their whole arc, so there is no pointable landmark
        # (Law 17). It was ~6% darker, and that delta drowned in the concrete
        # family's own value noise: every wide shot showed one uniform cream
        # disc. ~13% survives render distance and still reads as raked sand,
        # not as a different pavement.
        "texture": {"family": "concrete", "params": {"fine": True, "base": [0.58, 0.54, 0.46]}},
        "color": [0.58, 0.54, 0.46, 1.0],
        "metallic": 0.0,
        "roughness": 0.85,
    },
    f"{MOD_ID}_paint_cream": {
        # Venue cream, shared by everything painted rather than lit: nobori
        # header bands / borders / glyph strokes, the ramp's lane paint and
        # the apron plaque trim. Colour-only on purpose - paint over cloth or
        # asphalt reads by tone and relief, so a flat matte cream is the
        # honest material. (Used to add "and emissive is inert in this pack" -
        # RETIRED 2026-08-15, round 17. Paint is still the right call for a
        # venue surface; it just is not forced any more.)
        "color": [0.97, 0.94, 0.86, 1.0],
        "metallic": 0.0,
        "roughness": 0.62,
    },
    f"{MOD_ID}_rod_chrome": {
        "texture": {"family": "scribed_chrome"},
        "color": [0.78, 0.80, 0.83, 1.0],
        "metallic": 0.95,
        "roughness": 0.18,
    },
    f"{MOD_ID}_ramp_asphalt": {
        "texture": {"family": "asphalt"},
        "color": [0.16, 0.16, 0.17, 1.0],
        "metallic": 0.0,
        "roughness": 0.92,
    },
    f"{MOD_ID}_signage": {
        "texture": {"family": "panel_legend"},
        "color": [0.10, 0.11, 0.13, 1.0],
        "metallic": 0.1,
        "roughness": 0.55,
    },
    # --- sumo dressing (visual-only meshes; see build_visual) --------------
    f"{MOD_ID}_torii_red": {
        # Shrine vermilion, worn like painted plant: the entrance gate and the
        # guard wall's arena face.
        "texture": {
            "family": "wood_painted",
            "params": {"base": [0.63, 0.13, 0.08], "wear": 0.22, "rough": 0.5},
        },
        "color": [0.63, 0.13, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    f"{MOD_ID}_lacquer_black": {
        "color": [0.055, 0.055, 0.065, 1.0],
        "metallic": 0.05,
        "roughness": 0.5,
    },
    f"{MOD_ID}_marquee": {
        # The ring's name, carried where a shrine gate carries its tablet (and
        # repeated on the apron billboard). A painted board, by choice, so
        # nothing pretends to glow. (Used to read "emissive is inert in this
        # pack" - RETIRED 2026-08-15, round 17. AND NOTE WHERE THAT RETIRED
        # LAW ACTUALLY GOT TO: this line, and its siblings in six other
        # spec/blender files, are SOURCE COMMENTS. A round-5 sweep of all 18
        # authoring/listing_copy.md files found ZERO occurrences of
        # glow/emissive/lit/nit in this mod's copy and zero in
        # junk_chute_grinder's - the two the wrong law was accused of
        # reaching. It never reached a word of player-facing text in either.
        # Three listing copies DO use glow language - gforce_centrifuge,
        # giant_toaster and pachinko_tower - and only the first two are
        # claims rather than denials; see AGENTS.md round 5 for what those
        # two promise against what their PUBLISHED zips actually ship.)
        # INVERTED in round
        # 4: a vermilion field hung on a vermilion gate read red-on-red, so
        # the tablet is now venue-cream carrying vermilion type (the
        # hpu_legend ink) - how a real kanban reads against painted plant.
        "texture": {
            "family": "marquee",
            "params": {
                "text": "SUMO GYRO-PLATFORM",
                "fg": [0.45, 0.09, 0.06],
                "bg": [0.97, 0.94, 0.86],
            },
        },
        "color": [0.97, 0.94, 0.86, 1.0],
        "metallic": 0.0,
        "roughness": 0.45,
    },
    # (The status pylon's painted colour-code legend went out with the pylon
    # itself in the 2026-08-13 player round. A machine that needs a key to
    # explain its own indicator lights is signage, and this one no longer
    # has indicator lights to explain.)
    f"{MOD_ID}_name_lcd": {
        # LIVE competitor-name panels. The emissive map is not a file: the
        # "@" prefix names a dynamic texture target that a CEF webview fills
        # at runtime with assets/scoreboard/screen.html - the stock ETK800
        # dash-screen mechanism ("@etk800_gauges_screen" + htmlTexture.create),
        # proven in this pack by the washer's LCD. It is the only way to draw
        # a CHOSEN string onto a surface here: baked textures cannot change,
        # and the debug overlay this replaces drew at a fixed screen size, so
        # it could only hover in front of the board (player, 2026-08-14).
        #
        # The tag must match htmlTexture.create's byte-for-byte, "@" and all,
        # and the registry is process-GLOBAL, which is what the mod-id prefix
        # buys. No "texture" key: this material ships no file at all, so it
        # also carries zero texture-cook cost.
        #
        # Base is near-black glass on purpose: if the webview ever fails to
        # come up, the panel reads as a screen that is switched off rather
        # than as a missing texture.
        "color": [0.010, 0.012, 0.018, 1.0],
        "metallic": 0.45,
        "roughness": 0.12,
        "stage": {
            "emissive": True,
            "emissiveFactor": [1.0, 1.0, 1.0],
            "emissiveIntensityNits": 700,
            "emissiveMap": f"@{MOD_ID}_name",
        },
    },
    f"{MOD_ID}_drive_iron": {
        # The flywheel: sand-cast iron, because a drive wheel that has to
        # turn 212 tonnes of deck should look like it has the mass to do it.
        "texture": {"family": "cast_iron", "size": 1024},
        "color": [0.145, 0.14, 0.145, 1.0],
        "metallic": 0.6,
        "roughness": 0.54,
    },
    f"{MOD_ID}_drive_tyre": {
        # The friction tread. This is the one surface on the machine whose
        # whole job is to GRIP, so it is the one that looks like rubber.
        "texture": {
            "family": "rubber_tread",
            "params": {"base": [0.135, 0.135, 0.145]},
        },
        "color": [0.135, 0.135, 0.145, 1.0],
        "metallic": 0.0,
        "roughness": 0.88,
    },
    f"{MOD_ID}_hpu_legend": {
        # Cream service-legend strip for the skid's torii-red panels: venue
        # cream field, vermilion ink - so the power plant names itself
        # instead of sitting beside the arena as primer-grey boxes. The skid
        # feeds BOTH circuits now: the four tilt rams it always drove, and
        # (2026-08-13 player round) the ring-drive motor beside it.
        "texture": {
            "family": "panel_legend",
            "params": {
                "base": [0.93, 0.90, 0.82],
                "ink": [0.45, 0.09, 0.06],
                "title": "RING DRIVE & RAM POWER",
                "aspect": 4.0,
                "title_scale": 0.15,
                "label_scale": 0.11,
                "labels": [
                    [0.5, 0.20, "440V 3PH MOTOR - FOUR RAM CIRCUITS - KEEP CLEAR"],
                ],
            },
        },
        "color": [0.93, 0.90, 0.82, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    # Nobori banner cloth. These are REAL soft-body sheets now (2026-08-13
    # player round), so every piece of venue artwork that used to be a proud
    # cream slab bolted to a rigid box - header band, edge piping, glyph
    # column - is painted into the texture instead: geometry cannot ride a
    # waving cloth, and this pack's law is that paint lives in the map. The
    # family draws a whole banner into 0..1 with u across the width and v
    # down the drop, which is exactly how the cloth mesh is unwrapped.
    #
    # The material keys below are the goal post's proven cloth set: zero
    # thickness needs doubleSided, doubleSided needs invertBackFaceNormals or
    # the sheet goes black whenever it twists away, and subSurface is what
    # makes lightweight cloth glow with the sun behind it.
    f"{MOD_ID}_banner_red": {
        "texture": {
            "family": "nobori",
            "size": 1024,
            "params": {"base": [0.62, 0.09, 0.08], "glyphs": 5},
        },
        "color": [0.62, 0.09, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.62,
        "double_sided": True,
        "stage": {
            "detailNormalMap": (
                "/vehicles/common/generic_mat_tex/detail_fabric_nm.normal.png"
            ),
            "detailNormalMapStrength": 0.50,
            "detailScale": [5, 5],
            "clearCoatFactor": 0.08,
            "clearCoatRoughnessFactor": 0.72,
        },
        "material": {
            "invertBackFaceNormals": True,
            "subSurface": True,
            "subSurfaceIntensity": 0.5,
        },
    },
    f"{MOD_ID}_banner_indigo": {
        "texture": {
            "family": "nobori",
            "size": 1024,
            "params": {"base": [0.14, 0.17, 0.40], "glyphs": 4},
        },
        "color": [0.14, 0.17, 0.40, 1.0],
        "metallic": 0.0,
        "roughness": 0.62,
        "double_sided": True,
        "stage": {
            "detailNormalMap": (
                "/vehicles/common/generic_mat_tex/detail_fabric_nm.normal.png"
            ),
            "detailNormalMapStrength": 0.50,
            "detailScale": [5, 5],
            "clearCoatFactor": 0.08,
            "clearCoatRoughnessFactor": 0.72,
        },
        "material": {
            "invertBackFaceNormals": True,
            "subSurface": True,
            "subSurfaceIntensity": 0.5,
        },
    },
    # Four flag colours for the status prism AND the dish's two painted match
    # lines. Plain colours on purpose: a painted mechanical semaphore is an
    # honest readout - it shows its working and cannot lie about state it does
    # not have. (The old justification was "emissive is inert on vehicle
    # materials in this pipeline (AGENTS.md), so a status light would be a
    # lie" - RETIRED 2026-08-15, round 17: emissive works with a THREE-element
    # factor. A lit status light is now a DIFFERENT design, not an impossible
    # one. Note this same file already ships a working three-element emissive
    # on _name_lcd, which is defined EARLIER IN THIS SAME PALETTE, roughly
    # 140 lines ABOVE here - the refuted law and its own live
    # counter-example sat in one file, and nobody looked up. Round 17's
    # version of this note said "90 lines" and "below"; both were wrong.
    # Direction and file, not a line number: a comment cannot keep an
    # absolute line number true - the note directly above `_marquee` in this
    # very round shifted both of round 17's numbers by 11 the moment it was
    # written.)
    f"{MOD_ID}_flag_open": {
        # Shrine green, deepened again in round 4: [0.09, 0.42, 0.16] still
        # floated toward nursery mint at render distance. This is cedar-
        # shrine paint - dark enough that the refuge ring reads as lacquered
        # colour on a 212-tonne machine, not putting-green felt (and richer
        # paddle paint on the semaphore, same semantics).
        "color": [0.05, 0.28, 0.10, 1.0],
        "metallic": 0.0,
        "roughness": 0.45,
    },
    f"{MOD_ID}_flag_arm": {
        "color": [0.92, 0.61, 0.06, 1.0],
        "metallic": 0.0,
        "roughness": 0.45,
    },
    # --- match scoreboard materials (2026-08-13 match round) ---
    # "Fluorescent" here = maximum-chroma paint: these two exist solely to
    # SNAP against their dull ring counterparts when the pose-swap brings them
    # proud of the deck. (Was "in an engine with inert emissives" - RETIRED
    # 2026-08-15, round 17.)
    f"{MOD_ID}_fluoro_live": {
        "color": [0.10, 0.95, 0.25, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_fluoro_ko": {
        "color": [1.0, 0.10, 0.06, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_pip_gold": {
        # Kachiboshi pucks - a filled gold circle per win, banzuke-style.
        "color": [0.88, 0.66, 0.16, 1.0],
        "metallic": 0.55,
        "roughness": 0.35,
    },
    f"{MOD_ID}_sign_win": {
        "texture": {"family": "marquee",
                    "params": {"text": "WIN", "fg": [0.97, 0.94, 0.86],
                               "bg": [0.09, 0.42, 0.16]}},
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_sign_loss": {
        "texture": {"family": "marquee",
                    "params": {"text": "LOSS", "fg": [0.97, 0.94, 0.86],
                               "bg": [0.42, 0.06, 0.05]}},
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_sign_east": {
        "texture": {"family": "marquee",
                    "params": {"text": "EAST", "fg": [0.97, 0.94, 0.86],
                               "bg": [0.42, 0.06, 0.05]}},
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_sign_west": {
        "texture": {"family": "marquee",
                    "params": {"text": "WEST", "fg": [0.42, 0.06, 0.05],
                               "bg": [0.97, 0.94, 0.86]}},
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    f"{MOD_ID}_flag_live": {
        # Blood-vermilion, kin to the torii, deepened again in round 4:
        # [0.58, 0.09, 0.07] still drifted salmon under flat light. This
        # depth is dried-lacquer red - the danger ring and the LIVE paddle
        # read as the torii's own family, never pastel.
        "color": [0.42, 0.06, 0.05, 1.0],
        "metallic": 0.0,
        "roughness": 0.45,
    },
    f"{MOD_ID}_flag_reset": {
        "color": [0.16, 0.38, 0.78, 1.0],
        "metallic": 0.0,
        "roughness": 0.45,
    },
    f"{MOD_ID}_horn_enamel": {
        # PA horn paint. The reference unit is enamel over spun steel - not a
        # metal, not a plastic - and `steel` is far too specular for it: a
        # 1.10 m bell at metallic 0.85 mirrors the sky and loses its shape
        # entirely, which is the whole point of a flared silhouette. So the
        # bells, driver bodies and junction box get their own paint while the
        # pole, brackets and hardware stay galvanised steel.
        #
        # Pachinko's is a chalked grey-olive at peel 0.95, because a 1970s
        # parlour's PA is meant to read as derelict. A sumo venue keeps its
        # kit: same finish, warmer and neutral so it sits with the raked-sand
        # apron rather than going green against it, and peeled a third as
        # hard - weathered, not abandoned.
        "texture": {"family": "painted_metal", "size": 256, "params": {
            "base": [0.455, 0.450, 0.435], "rough": 0.47, "peel": 0.32}},
        "color": [0.455, 0.450, 0.435, 1.0],
        "metallic": 0.22,
        "roughness": 0.47,
    },
}

# EVERY material renders both sides. Blender does not backface-cull and BeamNG
# does, so a single-sided surface that looks perfect in every headless check
# can be invisible in game; the pack retired the whole bug class by forcing
# doubleSided on every prop material (AGENTS.md 2026-08-07 policy).
for _palette_entry in PALETTE.values():
    _palette_entry["double_sided"] = True
del _palette_entry

# ---------------------------------------------------------------------------
# Trigger zones
# ---------------------------------------------------------------------------
_RAMP_C = math.cos(math.radians(RAMP_AZIMUTH_DEG))
_RAMP_S = math.sin(math.radians(RAMP_AZIMUTH_DEG))
# Boarding corridor, MESSAGING ONLY. The interlock that actually holds the
# countdown is a positional sweep (see CORRIDOR_* below), because a Contains
# box drops a moving vehicle the moment its bbox pokes past the zone and the
# previous 5.2 x 6.6 m box only Contained a 4.5 m car inside a 2.1 m window of
# a 13.1 m corridor - a queuing car usually failed to hold the countdown at
# all (AGENTS.md "Zones and occupancy"). This box now spans the WHOLE corridor
# so the message is at least as reliable as a Contains test can be.
_CORRIDOR_MID_R = 0.5 * (DECK_RADIUS + RAMP_OUTER_R)
_CORRIDOR_LENGTH = RAMP_OUTER_R - DECK_RADIUS
# The running surface falls from 2.09 m at the deck to 0 at the outer end, so
# a 1.5 m car occupies z 0 .. 3.6 somewhere along it; the box spans
# -0.3 .. 4.1 to CONTAIN it anywhere in the corridor.
_CORRIDOR_Z = 1.90

TRIGGERS = {
    "ramp_zone": {
        "mode": "Contains",
        "center": [
            _CORRIDOR_MID_R * _RAMP_C,
            _CORRIDOR_MID_R * _RAMP_S,
            _CORRIDOR_Z,
        ],
        "dimensions": [8.4, _CORRIDOR_LENGTH + 0.3, 4.4],
    },
    # The whole arena, for approach/leave messages only. Overlaps because a
    # car being shoved over the lip is never fully contained by anything, and
    # because the physics never trusts trigger occupancy: the torque balance
    # runs off a getAllVehicles positional sweep (AGENTS.md - trigger sets
    # blank out and made a parked car invisible for minutes on the
    # centrifuge). 28 m spans the 26.2 m deck plus a car's diagonal.
    "arena_zone": {
        "mode": "Overlaps",
        "center": [0.0, 0.0, 2.6],
        "dimensions": [28.0, 28.0, 6.0],
    },
}

# Positional corridor, in the ramp's OWN frame: s runs outward along the ramp
# centreline, d across it. A vehicle counts as in the corridor when its centre
# is inside this rectangle and within the height band - a centre-in-envelope
# test, which is what AGENTS.md prescribes for lifecycle decisions.
CORRIDOR_HALF_WIDTH = RAMP_HALF_WIDTH + 0.70  # lane + both kerbs + 0.06 m
CORRIDOR_NEAR_R = DECK_RADIUS - 0.60  # starts just inboard of the threshold
CORRIDOR_FAR_R = RAMP_OUTER_R
CORRIDOR_Z_MIN = -1.50
CORRIDOR_Z_MAX = 4.60

EFFECTS = {
    # Ram bypass-valve blow-off, pulsed for a moment when the gimbal unlocks
    # and again when it re-locks. BNGP_2 is a stock emitter used by the existing
    # pack mods - present in v0.39.4.0 build 20972, re-checked 2026-08-15; the
    # "0.38.6" that used to qualify it was a directory name, not an engine.
    # Invented emitter names fail at load.
    # Placed at the guard kerb beside the ramp mouth (not under the deck, where
    # nothing would ever see it) so the puff reads from the boarding approach.
    "valve_vent": {
        "emitter": "BNGP_2",
        "position": [
            15.0 * _RAMP_C - 5.0 * _RAMP_S,
            15.0 * _RAMP_S + 5.0 * _RAMP_C,
            0.35,
        ],
        "direction": [0.0, 0.0, 1.0],
    },
}

# ---------------------------------------------------------------------------
# Runtime tunables (shipped through the Blender handoff - a spec-only rebuild
# leaves every new key nil at runtime, AGENTS.md b104)
# ---------------------------------------------------------------------------
BEHAVIOR = {
    "camera_distance": 46.0,
    # --- machine model ---
    "inertia": INERTIA,
    "stiffness": STIFFNESS,
    "damping": DAMPING,
    "damping_relevel": DAMPING_RELEVEL,
    "torque_cap": TORQUE_CAP,
    "gravity": 9.81,
    "tilt_max_rad": TILT_MAX_RAD,
    "rate_max": TILT_RATE_MAX_RAD_S,
    "bake_step_rad": TILT_BAKE_STEP_RAD,
    "bake_interval": TILT_BAKE_INTERVAL,
    "bake_watch_radius": BAKE_WATCH_RADIUS,
    "bake_watch_hysteresis": BAKE_WATCH_HYSTERESIS,
    "bake_cost_budget_ms": BAKE_COST_BUDGET_MS,
    "bake_backoff_max": BAKE_BACKOFF_MAX,
    "bake_cost_ema_alpha": BAKE_COST_EMA_ALPHA,
    # A frame hitch must not integrate a 0.5 s step. 0.05 s is 3 x a 60 Hz
    # frame and still leaves omega*dt = 0.024, deep inside the stability
    # region of the semi-implicit Euler step used here. With the committed
    # step clamped, the delivered collision move no longer depends on dt at
    # all - this clamp is now only about integrator stability.
    "dt_max": 0.05,
    # --- deck geometry the runtime needs to answer "is this car aboard" ---
    "deck_top_z": DECK_TOP_Z,
    "dish_rise": DISH_RISE,
    "dish_radius": DISH_RADIUS,
    "pivot_z": PIVOT_Z,
    "wall_inner_r": WALL_INNER_R,
    # Load radius = the lip crest. Outboard of the crest a car is already
    # leaving, and counting it would let a car that is half over the edge keep
    # driving the tilt that is throwing it off.
    "load_radius": LIP_CREST_R,
    # Ram anchor geometry, so the Lua rebuilds the exact same struts the
    # Blender generator drew (one source of truth, no retyped numbers).
    "ram_eye_r": RAM_EYE_R,
    "ram_eye_z": RAM_EYE_Z,
    "ram_foot_r": RAM_FOOT_R,
    "ram_foot_z": RAM_FOOT_Z,
    # A car is "aboard" when its reference node sits in this band above the
    # committed deck surface. -0.55 catches a low ref node on a compressed
    # suspension; +2.8 still catches a car mid-barrel-roll but drops one that
    # has been thrown clear.
    "aboard_below": -0.55,
    "aboard_above": 2.80,
    # Anything this far BELOW the committed deck surface, inside the guard
    # kerb, is under the deck - which the geometry says cannot happen. If it
    # ever does, the machine locks level instead of closing on it.
    "under_deck_below": -0.90,
    # --- corridor interlock (positional; the trigger is messaging only) ---
    "corridor_cos": _RAMP_C,
    "corridor_sin": _RAMP_S,
    "corridor_half": CORRIDOR_HALF_WIDTH,
    "corridor_near": CORRIDOR_NEAR_R,
    "corridor_far": CORRIDOR_FAR_R,
    "corridor_z_min": CORRIDOR_Z_MIN,
    "corridor_z_max": CORRIDOR_Z_MAX,
    # A car that queues on the ramp through a live round is not made to wait
    # out the whole four minutes: this many continuous seconds in the corridor
    # ends the round early and gives them the ring.
    "corridor_end_seconds": 12.0,
    # --- occupant mass ---
    "mass_default_kg": CAR_MASS,
    "mass_min_kg": 300.0,
    "mass_max_kg": 30000.0,
    "mass_prune_seconds": 6.0,
    # --- derelict purge (every phase needs a way out, AGENTS.md) ---
    # A rider that has not moved 0.45 m in 20 s is not playing: it is a
    # handbraked spectator or a wreck. It stops counting as a rider AND stops
    # dragging the tilt toward its own side, so a dead car can neither pin the
    # round open nor hold the deck leaning at it. Anything past the "heavy
    # damage" mark in the shipped scale (AGENTS.md: traffic respawns at 500,
    # freeform calls >5000 heavy) is written off after 5 s instead of 20.
    "stuck_seconds": 20.0,
    "stuck_move_eps": 0.45,
    "wreck_damage": 5000.0,
    "wreck_seconds": 5.0,
    # --- round lifecycle ---
    # Measured by executing THIS Lua chunk (lupa, stubbed framework helpers,
    # 60 Hz) rather than a Python paraphrase of it:
    #   empty ring, 30 s                     phase open, 1 reload (the init bake)
    #   one car at r = 10 m                  open -> arming -> live, settles at
    #                                        3.40 deg against a 3.50 deg
    #                                        closed form, ram lengths 2.254 ..
    #                                        2.534 m about a 2.370 m rest
    #   rider motionless 20 s                purged, round ends, deck re-levels
    #                                        and re-opens with it still aboard
    #   rider at damage 6000                 written off between 3 s and 6 s
    #   derelict parked in the corridor      holds arming for the bounded 25 s,
    #                                        then the round runs to completion
    #   car actually queuing in the corridor round called at 12 s
    #   vehicle under the deck               trapped, gimbal stays locked
    #   reset at the 5.50 deg stops          committed pose unchanged, 0.00 mm
    #                                        of instantaneous rim travel
    #   every committed move, every case     <= 19.43 mm at the rim
    # Guaranteed boarding window. The ring will not start a countdown for at
    # least this long after it goes green, so a second car can always join and
    # the ramp junction is never flush for less than open_hold + arm_seconds.
    "open_hold_seconds": 6.0,
    # 5 s of countdown: long enough to read three numbered warnings and to
    # back off the ramp, short enough that nobody waits around.
    "arm_seconds": 5.0,
    # A car in the boarding corridor holds the countdown, because the junction
    # between the fixed ramp and the moving deck is only flush while the deck
    # is locked level. The hold is not open-ended - 25 s and the machine arms
    # anyway, so a parked wreck can never pin the prop forever.
    "arm_wait_max": 25.0,
    # Zero riders has to be debounced: a car crossing the lip bounces in and
    # out of the aboard band for a moment.
    "clear_debounce": 1.6,
    # Round intermission, not a hard stop: after three minutes the deck
    # returns to level whatever is happening, which re-opens the ramp
    # junction. If the survivors are still aboard when it finishes it simply
    # re-arms and a new round starts, so this can never strand the machine
    # mid-lean.
    "round_max_seconds": 180.0,
    # Re-level is a damped return, but a damped return is only asymptotic.
    # After this long the bypass valves are declared shut and the deck is
    # walked to level at the flow limit, which reaches zero from the stops in
    # tilt_max/rate_max = 8.1 s. Every phase therefore terminates. The walk is
    # eased in over relevel_bleed_ramp so the changeover is not a step in deck
    # speed. Measured whole re-level from the stops: 10.05 s at 60 fps and
    # 10.07 s at 30 fps, strictly monotone, no overshoot, every committed move
    # inside the 19.43 mm bound.
    "relevel_hard_seconds": 8.0,
    "relevel_bleed_ramp": 1.5,
    # Settled = within one bake step of level and slower than a tenth of the
    # rate limit. The snap to exact zero is therefore at most one bake step,
    # the same bound every other committed move obeys.
    "level_eps_rad": TILT_BAKE_STEP_RAD,
    "rate_eps": TILT_RATE_MAX_RAD_S * 0.10,
    # --- scoreboard ---
    # (The colour-semaphore prism, its painted legend and the rider tally
    # went out with the instruction pylon in the 2026-08-13 player round -
    # a board that has to explain its own colour code is signage, and this
    # machine now says everything it needs to with the match board.)
    "vent_seconds": 1.4,
    "stats_interval": 0.5,
    # --- match system (2026-08-13) ---
    "set_wins": SET_WINS,
    "ko_radius": KO_RADIUS,
    "stage_radius": STAGE_RADIUS,
    "stage_speed": STAGE_SPEED,
    "stage_min_gap": STAGE_MIN_GAP,
    "stage_hold_seconds": STAGE_HOLD_SECONDS,
    "countdown_go_seconds": COUNTDOWN_GO_SECONDS,
    "countdown_stop_seconds": COUNTDOWN_STOP_SECONDS,
    "spin_omega_max": SPIN_OMEGA_MAX,
    "spin_accel": SPIN_ACCEL,
    "spin_decel": SPIN_DECEL,
    "spin_drag_accel": SPIN_DRAG_ACCEL,
    "spin_min_r": SPIN_MIN_R,
    # Win calls: three takes per corner (authoring/mix_win_audio.sh bakes
    # them). Longest take is 1.36 s and the shortest clip is 2.98 s including
    # its silent pad, so one stop time at 1.95 s serves all six.
    # Announcer calls: three takes per corner of each kind, baked by
    # authoring/mix_call_audio.sh. Longest take is 2.21 s and the shortest
    # clip is 4.36 s including its silent pad, so one stop time at 2.60 s
    # serves all twelve.
    "call_takes": 3,
    # Six welcome-back takes; the sixth is round-two only.
    "back_takes": 6,
    # 3.70 s clears the longest take (3.40) and sits inside every clip's
    # 4.0 s pad, so ONE stop time serves all twenty-four without wrapping.
    "call_stop_seconds": 3.70,
    # Announcer dead air between one call ending and the next beginning. The
    # PA is ONE voice: playCall enqueues and the pump starts the next clip
    # only after the last one's stop clock has run out plus this gap (see
    # pumpCalls). The floor on the gap is perceptual - under about 0.3 s of
    # silence two utterances run together as one breath and the listener
    # hears a stumble rather than two announcements - and the ceiling is
    # that the second corner's welcome still has to land inside the moment
    # that caused it. 0.40 s sits just over the floor: a clean sentence
    # boundary, and total onset-to-onset separation of 4.10 s.
    "call_gap_seconds": 0.40,
    # The nobori are real cloth on BeamNG's PHYSICS ground wind, and no stock
    # level ships a wind value - it starts at (0,0,0), so out of the box the
    # banners would hang dead still. Correct, but not what a venue looks
    # like. On spawn the prop sets a light breeze ONLY IF the level's wind is
    # still exactly zero, so it never overrides a wind the player dialled in.
    # Set to 0 to disable; ground wind is global and does reach other
    # vehicles' aero, though 4 m/s is about 9 mph.
    "breeze_mps": 4.0,
    "breeze_heading_deg": 205.0,
    "spin_home_rate": SPIN_HOME_RATE,
    "spin_home_eps": SPIN_HOME_EPS,
    "drive_ratio": DRIVE_RATIO,
    "decided_hold_seconds": DECIDED_HOLD_SECONDS,
    "match_max_seconds": MATCH_MAX_SECONDS,
    # Reset spots: scalars, never a 3-number list (lua_kit vec3 coercion).
    "reset_dist": RESET_SPOT_DIST,
    "reset_gap": RESET_SPOT_GAP,
    "ramp_az_cos": _RAMP_C,
    "ramp_az_sin": _RAMP_S,
    # Scoreboard pose strokes (all vertical so one part serves both faces).
    "sb_pip_hide": SB_PIP_HIDE,
    "sb_result_shift": SB_RESULT_SHIFT,
    "sb_result_hide": SB_RESULT_HIDE,
    "ring_hide_drop": 0.30,
    # (The nameplate anchor keys went with the debug-overlay text: the names
    # are a live webview texture now, so the runtime pushes STRINGS, not
    # world positions.)
}

# ---------------------------------------------------------------------------
# THE PA HORNS - which sounds leave the machine and go up the pole, and the
# four scene emitters that carry them.
#
# THE MECHANISM IS PACHINKO'S, PROBED THERE RATHER THAN ASSUMED HERE (three
# live probes off a WASAPI loopback of the game's own output, because "an
# object was created" is not "a sound was heard" and this pack has believed
# that before). The findings that this port depends on, verbatim in substance:
#
#   * `SFXEmitter` + a `fileName` pointing at the shipped .ogg + `is3D = 1`,
#     `isLooping = 1`, `playOnAdd = 0` is AUDIBLE and positional. `track` is
#     digital silence on this build, whatever you feed it.
#   * THE CONES ARE REAL, and exact: a 30/70 deg cone at outsideVolume 0.05
#     measured a front/back ratio of 0.0500, the set value to three figures.
#     So "four directions" is an audible fact here, not just a picture.
#   * Four copies of one mono cue POWER-sum (+5.7 dB measured, not +12), so
#     the cluster reads as four horns rather than as one loud loudspeaker.
#
# WHICH CUES MOVE: all of them. The player's ask was "all announcer sounds",
# and on this machine every sound IS an announcement - twenty-four voice takes
# and the countdown. Nothing physical is voiced (the deck, the rams and the
# drive make no sound at all), so unlike pachinko there is no split to make.
CALL_KINDS = (("welcome", 3), ("back", 6), ("win", 3))
HORN_CUES = tuple(
    f"{kind}_{side}_{take}"
    for kind, takes in CALL_KINDS
    for side in ("east", "west")
    for take in range(1, takes + 1)
) + ("countdown",)
assert len(HORN_CUES) == len(set(HORN_CUES)) == 25

# Cone geometry in the engine's own terms: these are FULL angles, so the inner
# half-angle is 50 deg and the outer 110. With four horns 90 deg apart every
# azimuth falls inside somebody's inner cone and the power sum around the
# compass varies by 1.2 dB - directional per horn, even overall, which is what
# a four-way PA head does.
HORN_CONE_IN_DEG = 100.0
HORN_CONE_OUT_DEG = 220.0
HORN_CONE_OUT_VOL = 0.30
# Full level everywhere a competitor can stage: the shikiri circle's far edge
# is HORN_POLE_R + STAGE_RADIUS from the pole, and roll-off starts there.
HORN_REF_M = round(HORN_POLE_R + STAGE_RADIUS, 1)   # 23.9
HORN_MAX_M = 150.0
# Per-horn mix trim. The emitter path measured ~1.8x the vehicle-side path at
# the same nominal volume and distance, and four horns power-sum to ~1.38x on
# top of that. 0.50 therefore lands the announcement about 2 dB ABOVE where it
# sat on the vehicle - which is the point of putting it on a PA, and which
# preserves the "twice as loud" round: that gain lives in the FILES (they are
# peak-normalised to -1 dBFS by authoring/mix_call_audio.sh) and is untouched
# here. The countdown carries its old 0.9 vehicle trim through the same sum.
HORN_GAIN = 0.50
HORN_CUE_GAIN = {"countdown": 0.9 * HORN_GAIN}


def _horn_specs_lua() -> str:
    rows = []
    for index, (mouth, (dx, dy)) in enumerate(zip(HORN_MOUTHS, HORN_DIRS)):
        x, y, z = mouth
        rows.append(
            f'  {{slot = "h{index}", pos = vec3({x}, {y}, {z}), '
            f"dir = vec3({dx}, {dy}, 0)}},"
        )
    return "\n".join(rows)


def _horn_cues_lua() -> str:
    return "\n".join(
        f'  {{name = "{name}", vol = {HORN_CUE_GAIN.get(name, HORN_GAIN)}}},'
        for name in HORN_CUES
    )


# Vehicle-side audio: the ONLY proven-audible path in this pack is a
# createSFXSource on the prop VEHICLE (CHIEF, 2026-08-09). It is now the PA's
# FALLBACK rather than its main line - a missing emitter must cost an
# announcement its position, never the announcement - so every clip still
# ships a vehicle source and the GE decides per cue which path speaks. Ships
# from THIS template at build time (derived-lua law) - never edit the
# generated vehicle lua.
VEHICLE_LUA_EXTRA = f"""
local countdownSfxId = nil
local COUNTDOWN_OGG = "vehicles/{MOD_ID}/sound/{MOD_ID}_countdown.ogg"
local function playCountdown()
  if countdownSfxId == nil then
    local ok, id = pcall(function()
      return obj:createSFXSource(COUNTDOWN_OGG, "AudioDefaultLoop3D",
        "sumo_countdown", 0)
    end)
    countdownSfxId = (ok and id) or nil
    if countdownSfxId then
      pcall(function() obj:setVolumePitch(countdownSfxId, 0.9, 1) end)
    end
  end
  if countdownSfxId then
    pcall(function() obj:playSFX(countdownSfxId) end)
  end
end
local function stopCountdown()
  if countdownSfxId then
    pcall(function() obj:stopSFX(countdownSfxId) end)
  end
end
M.playCountdown = playCountdown
M.stopCountdown = stopCountdown
-- ... and under the PA's own naming, so the GE has ONE fallback code path
-- for every cue instead of a special case for this one.
M.play_countdown = playCountdown
M.stop_countdown = stopCountdown

-- Announcer calls: welcome_<side>_<take> as a corner is claimed,
-- win_<side>_<take> as it takes the match. Three takes of each, rolled at
-- random by the GE runtime, which queues the exact function it picked - so
-- WHICH TAKE is random but which CORNER never is. Faked one-shots: a loop
-- source each, stopped by the GE inside that ogg's silent pad.
--
-- One function per clip rather than one that takes an argument, because
-- queueVehicleFx can only name a function - it passes nothing.
local callSfx = {{}}
local function callSource(tag)
  if callSfx[tag] == nil then
    local ok, id = pcall(function()
      return obj:createSFXSource(
        "vehicles/{MOD_ID}/sound/{MOD_ID}_" .. tag .. ".ogg",
        "AudioDefaultLoop3D", "sumo_" .. tag, 0)
    end)
    callSfx[tag] = (ok and id) or false
    if callSfx[tag] then
      -- Full source gain; the oggs are peak-normalised to -1 dBFS by
      -- authoring/mix_call_audio.sh, so the level lives in the FILE where
      -- every take gets the same treatment.
      pcall(function() obj:setVolumePitch(callSfx[tag], 1.0, 1) end)
    end
  end
  return callSfx[tag] or nil
end
local function stopAllCalls()
  for _, id in pairs(callSfx) do
    if id then pcall(function() obj:stopSFX(id) end) end
  end
end
-- {{kind, takes}}: welcome-back has six, the others three.
for _, family in ipairs({{{{"welcome", 3}}, {{"back", 6}}, {{"win", 3}}}}) do
  local kind, count = family[1], family[2]
  for _, side in ipairs({{"east", "west"}}) do
    for take = 1, count do
      local tag = kind .. "_" .. side .. "_" .. take
      M["play_" .. tag] = function()
        local id = callSource(tag)
        if id then pcall(function() obj:playSFX(id) end) end
      end
      -- Per-clip stop, not a blanket one: two calls can overlap (both cars
      -- claiming corners a second apart), and stopping every source at the
      -- later deadline would cut the first clip past its pad and let it
      -- wrap audibly.
      M["stop_" .. tag] = function()
        local id = callSfx[tag]
        if id then pcall(function() obj:stopSFX(id) end) end
      end
    end
  end
end
M.stopAllCalls = stopAllCalls


-- ---------------------------------------------------------------------------
-- Live name displays. A CEF webview renders scoreboard/screen.html into the
-- dynamic texture "@{MOD_ID}_name", which the board's four window quads carry
-- as their emissive map. The tag here MUST equal the material's emissiveMap
-- string exactly, "@" included, or the material silently falls back to its
-- black base with no error anywhere.
--
-- The page is 1510x256 and TWO-UP (east cell | west cell); each quad's UVs
-- select its own half, so one webview feeds all four panels.
local htmlTexture = require("htmlTexture")
local NAME_TAG = "@{MOD_ID}_name"
local NAME_URL = "local://local/vehicles/{MOD_ID}/scoreboard/screen.html"
local nameUp = false

-- create() is not reliable the first time on a cold load (the webview
-- subsystem may not be up yet), so this retries every frame until it takes
-- and is a single boolean test forever after.
local function nameEnsure()
  if nameUp then return end
  nameUp = pcall(htmlTexture.create, NAME_TAG, NAME_URL, {SB_NAME_PX_W}, {SB_NAME_PX_H},
    15, "automatic") and true or false
end

local nameBaseLoaded = M.onVehicleLoaded
M.onVehicleLoaded = function(...)
  nameBaseLoaded(...)
  nameUp = false
  nameEnsure()
end

-- The washer's LCD skips this and gets away with it because its GE feed
-- pushes continuously. A name is not a continuously varying quantity, so a
-- reset here has to force the page back up and the GE side to re-send.
local nameBaseReset = M.onReset
M.onReset = function(...)
  if nameBaseReset then nameBaseReset(...) end
  nameUp = false
  nameEnsure()
end

local nameBaseUpdateGFX = M.updateGFX
M.updateGFX = function(dt, ...)
  nameBaseUpdateGFX(dt, ...)
  nameEnsure()
end

-- Payload crosses the GE -> vehicle VM boundary as JSON inside a Lua source
-- string (queueLuaCommand cannot carry a table), so it is decoded here.
M.onEricrolphSumoGyroName = function(payloadJson)
  nameEnsure()
  if not nameUp then return end
  local ok, data = pcall(jsonDecode, payloadJson)
  if ok and type(data) == "table" then
    pcall(htmlTexture.call, NAME_TAG, "updateData", data)
  end
end
"""

LUA_BEHAVIOR = r"""
-- ==========================================================================
-- ROTATION CONVENTION (derived, then cross-checked against a live result)
--
-- BeamNG quats carry a negated w ("T3d's quats use -w", lua/common/mathlib
-- .lua) and quat*vec3 applies b - 2w(v x b) + 2 v x (v x b), i.e. the
-- rotation of the CONJUGATE. The framework's axisAngle(n, t) builds the raw
-- quat (sin(t/2)n, cos(t/2)), whose conjugate is the rotation by -t about n.
-- So axisAngle rotates the WRONG WAY round by construction. The catapult
-- seesaw found the same negation empirically from an in-game screenshot
-- (its plank comment) - two independent confirmations.
--
-- rhq(axis, angle) is therefore the honest right-hand-rule rotation, and
-- q * v (quat times vec3) rotates v by exactly that. Everything below is
-- authored-frame; posePartObjects composes pose * modelRotation, and quats
-- compose left-to-right, so the pose is applied before the world flip.
-- ==========================================================================
local function rhq(axis, angleRad)
  return axisAngle(axis, -angleRad)
end

-- Tilt is stored as a rotation VECTOR w = (psiX, psiY, 0): a single rotation
-- of |w| about the horizontal axis w/|w|, through the bearing centre. The
-- height a deck point at authored (x, y) picks up is then
--   dz = (w x p).z = psiX * y - psiY * x
-- which is the ONE formula the deck surface, the aboard test, the rams and
-- the tilt repeater all sample. A mass at +y makes psiX negative (see the
-- torque sum) and that point drops: the deck leans TOWARD its load.
local function tiltQuat(px, py)
  local mag = math.sqrt(px * px + py * py)
  if mag < 1e-7 then return quat(0, 0, 0, 1) end
  return rhq(vec3(px / mag, py / mag, 0), mag)
end

-- Minimal rotation taking unit vector a to unit vector b. Used to aim each
-- ram from its AUTHORED rest attitude, so the identity pose of every ram part
-- is already the correct pose: if behavior.init ever fails, the machine looks
-- exactly as built rather than sprouting four cylinders through the deck.
local function alignQuat(ax, ay, az, bx, by, bz)
  local cx = ay * bz - az * by
  local cy = az * bx - ax * bz
  local cz = ax * by - ay * bx
  local sine = math.sqrt(cx * cx + cy * cy + cz * cz)
  if sine < 1e-9 then return quat(0, 0, 0, 1) end
  local cosine = ax * bx + ay * by + az * bz
  return rhq(vec3(cx / sine, cy / sine, cz / sine), math.atan2(sine, cosine))
end

-- Spawn mass from the jbeam node weights, the same sum vehicle/input.lua
-- uses for its own vehicleMass(). Cached per id; anything implausible or
-- unavailable falls back to the reference car so a missing API degrades the
-- feel rather than the machine.
local function subjectMass(state, vehicleId)
  local b = state.behavior
  b.mass = b.mass or {}
  local cached = b.mass[vehicleId]
  if cached then return cached end
  local total = 0
  local ok, data = pcall(function()
    return core_vehicle_manager.getVehicleData(vehicleId)
  end)
  local nodes = ok and data and data.vdata and data.vdata.nodes or nil
  if nodes then
    for _, node in pairs(nodes) do
      total = total + (node.nodeWeight or 0)
    end
  end
  if not (total >= B.mass_min_kg and total <= B.mass_max_kg) then
    total = B.mass_default_kg
  end
  b.mass[vehicleId] = total
  return total
end

local function subjectDamage(vehicleId)
  local ok, value = pcall(function()
    local entry = map and map.objects and map.objects[vehicleId]
    return entry and entry.damage or 0
  end)
  if ok and type(value) == "number" and finiteNumber(value) then return value end
  return 0
end

-- Committed deck surface height at authored (x, y). Uses the COMMITTED tilt,
-- never the integrator's, so the aboard test asks about the surface that is
-- actually baked into collision.
local function deckSurfaceZ(state, x, y)
  local b = state.behavior
  local r = math.sqrt(x * x + y * y)
  if r > B.dish_radius then r = B.dish_radius end
  local dish = B.deck_top_z + B.dish_rise * (r / B.dish_radius) * (r / B.dish_radius)
  return dish + (b.comX or 0) * y - (b.comY or 0) * x
end

-- Per-subject stillness clock. Returns its tracking entry and the number of
-- seconds of no motion at which it is written off - shorter if it is already
-- past the heavy-damage mark in the shipped scale. Both the rider purge and
-- the "someone is queuing" rule read it, so a handbraked spectator, a wreck
-- on the deck and an abandoned car on the ramp are all the same fact measured
-- once.
local function stillTime(state, vehicleId, x, y, dt)
  local b = state.behavior
  b.track = b.track or {}
  local entry = b.track[vehicleId]
  if not entry then
    entry = {x = x, y = y, still = 0, purged = false}
    b.track[vehicleId] = entry
  end
  local moved = math.sqrt((x - entry.x) * (x - entry.x) + (y - entry.y) * (y - entry.y))
  if moved >= B.stuck_move_eps then
    entry.x, entry.y = x, y
    entry.still = 0
  else
    entry.still = entry.still + dt
  end
  local limit = B.stuck_seconds
  if subjectDamage(vehicleId) >= B.wreck_damage then limit = B.wreck_seconds end
  return entry, limit
end

-- A rider that has stopped moving stops counting as a rider AND stops
-- contributing torque, so neither a spectator nor a write-off can pin the
-- round open or hold the deck leaning at it. Returns true while it is still a
-- live contender.
local function contender(state, vehicleId, entry, limit)
  if entry.still < limit then
    if entry.purged then
      entry.purged = false
      -- The return needs an event as much as the drop does. Without it the
      -- log recorded every purge and no un-purge, so a session full of
      -- rider_purged said nothing about whether any of them came back and
      -- the whole cycle was undiagnosable after the fact.
      emitEvent(state, "I", "rider_returned",
        {subject_id = vehicleId, still = entry.still})
      showMessage("Back in the fight.", 1.6)
    end
    return true
  end
  if not entry.purged then
    entry.purged = true
    emitEvent(state, "I", "rider_purged", {subject_id = vehicleId, still = entry.still})
    showMessage("NO CONTEST - a car has stopped moving. Dropping it from the tally.", 3.0)
  end
  return false
end

-- The authoritative occupancy + forcing term. Positional sweep over every
-- spawned vehicle, projected into the prop's authored frame by dotting with
-- the prop's own world axes (exact, and it needs no quaternion inverse).
-- The board announces WHO by toast (the one place text can exist at
-- runtime); the corners themselves are colors. Jbeam key, uppercased, is the
-- most honest name the engine offers a vehicle.
local function vehName(vehicle)
  local ok, name = pcall(function() return vehicle:getJBeamFilename() end)
  if ok and type(name) == "string" and #name > 0 then
    return string.upper(name)
  end
  return "CHALLENGER"
end

-- Countdown audio lives on the prop VEHICLE (createSFXSource is the only
-- proven-audible path in this pack); GE just rings the bell. The extension
-- name is the bootstrap's own, <mod_id>_vehicle.
local function queueVehicleFx(state, fn)
  pcall(function()
    local propObj = be:getObjectByID(state.propId)
    if propObj then
      propObj:queueLuaCommand(string.format(
        "if extensions.ericrolph_sumo_gyro_platform_vehicle"
        .. " and extensions.ericrolph_sumo_gyro_platform_vehicle.%s"
        .. " then extensions.ericrolph_sumo_gyro_platform_vehicle.%s() end",
        fn, fn))
    end
  end)
end

-- =====================================================================
-- THE PA HORN CLUSTER (2026-08-14 player round). Four horns on a
-- street-light standard beside the scoreboard, and every announcement this
-- machine makes coming out of all four of them.
--
-- WHY SCENE OBJECTS AND NOT NODES. obj:createSFXSource takes a NODE id, and
-- the only node this runtime may name is 0 (node ids here are cage indices
-- and the cage is frozen), which is why the whole soundtrack has been coming
-- out of one point at the middle of a 26 m arena. A scene object has no such
-- problem: it takes a world position and a cone direction, and it is created,
-- registered and swept by the same recipe the framework's own emitters use -
-- parked in state.effects so cleanupInstallation deletes it on every teardown
-- path.
--
-- POOLED UP FRONT, one emitter per cue per horn. The alternative - four
-- emitters whose fileName is rewritten per announcement - would be a quarter
-- of the objects, and this machine's PA is deliberately ONE VOICE
-- (pumpCalls serialises), so it would even be sufficient. It is not done
-- because a post-creation fileName rewrite is UNPROVEN on this build and the
-- pooled form is the one that was measured. "An object was created" is not
-- "a sound was heard".
--
-- WHO OWNS THE CLOCK. Not this module. b.callStops and b.cdStopT already stop
-- every clip inside its own silent pad, and they keep doing it - they just
-- call hushCall now instead of the vehicle directly. One timing authority.
-- =====================================================================
local HORN_SPECS = {
--@HORN_SPECS@--
}
local HORN_CUE_LIST = {
--@HORN_CUES@--
}
local HORN_PATH = "vehicles/@MOD_ID@/sound/@MOD_ID@_"
local HORN_CONE_IN = @HORN_CONE_IN@
local HORN_CONE_OUT = @HORN_CONE_OUT@
local HORN_CONE_OUT_VOL = @HORN_CONE_OUT_VOL@
local HORN_REF = @HORN_REF@
local HORN_MAX = @HORN_MAX@

local Horn = {}

-- state.effects key. The horn's own slot label is carried in HORN_SPECS so
-- the key, the scene name and the table row all read the same way.
local function hornSlot(cue, horn)
  return "pahorn_" .. cue .. "_" .. horn.slot
end

-- Re-pose and re-aim every emitter. This exists because the framework's own
-- transform sweep only knows about EFFECT_SPECS members and skips everything
-- else, so a placed prop that is ever moved or rotated would leave its horns
-- behind. Placement state lives on the BEHAVIOR table, not on this module, so
-- two arenas placed in one session cannot fight over it.
Horn.place = function(state, force)
  local b = state.behavior
  local origin = state.origin
  if not origin then return end
  local rot = state.modelRotation
  if not force and b.hornOrigin and b.hornRot and rot
      and (origin - b.hornOrigin):length() <= 0.01
      and math.abs(rot.x - b.hornRot.x) < 0.0005
      and math.abs(rot.y - b.hornRot.y) < 0.0005
      and math.abs(rot.z - b.hornRot.z) < 0.0005
      and math.abs(rot.w - b.hornRot.w) < 0.0005 then
    return
  end
  b.hornOrigin = vec3(origin.x, origin.y, origin.z)
  if rot then b.hornRot = {x = rot.x, y = rot.y, z = rot.z, w = rot.w} end
  for hi = 1, #HORN_SPECS do
    local horn = HORN_SPECS[hi]
    local p = toWorldPoint(state, horn.pos)
    local d = toWorldDir(state, horn.dir)
    -- The game's own aim recipe (photomodeFlash, and the centrifuge's steered
    -- SpotLights): quatFromDir -> toTorqueQuat -> the rotation FIELD.
    -- setPosRot does nothing here, and a cone with no orientation points
    -- wherever the identity transform happens to look.
    local ok, rotField = pcall(function()
      local q = quatFromDir(d, vec3(0, 0, 1)):toTorqueQuat()
      return string.format("%f %f %f %f", q.x, q.y, q.z, q.w)
    end)
    for ci = 1, #HORN_CUE_LIST do
      local emitter = state.effects[hornSlot(HORN_CUE_LIST[ci].name, horn)]
      if emitter then
        pcall(function()
          if ok and rotField then emitter:setField("rotation", 0, rotField) end
          emitter:setPosition(vec3(p.x, p.y, p.z))
        end)
      end
    end
  end
end

Horn.create = function(state)
  -- `have` counts what EXISTS at the end, not what this pass built. init can
  -- run twice (registerProp pcalls it, and a half-built table sends
  -- behavior.reset back through it), and counting only new objects would
  -- report zero on the second pass and silently retire the whole pole to the
  -- vehicle fallback.
  local have, made, failed = 0, 0, 0
  for ci = 1, #HORN_CUE_LIST do
    local cue = HORN_CUE_LIST[ci]
    for hi = 1, #HORN_SPECS do
      local horn = HORN_SPECS[hi]
      local slot = hornSlot(cue.name, horn)
      if not state.effects[slot] then
        local emitter = createObject("SFXEmitter")
        if emitter then
          if Sim and type(Sim.upcast) == "function" then
            emitter = Sim.upcast(emitter)
          end
          local ok = pcall(function()
            emitter:setTransform(MatrixF(true))
            emitter.canSave = false
            if type(emitter.setCanSave) == "function" then
              emitter:setCanSave(false)
            end
            -- playOnAdd defaults TRUE: without this line all hundred sources
            -- start blaring the moment the prop registers.
            emitter:setField("playOnAdd", 0, "0")
            emitter:setField("useTrackDescriptionOnly", 0, "0")
            emitter:setField("fileName", 0, HORN_PATH .. cue.name .. ".ogg")
            emitter:setField("is3D", 0, "1")
            emitter:setField("isLooping", 0, "1")
            emitter:setField("isStreaming", 0, "0")
            emitter:setField("volume", 0, tostring(cue.vol))
            emitter:setField("referenceDistance", 0, tostring(HORN_REF))
            emitter:setField("maxDistance", 0, tostring(HORN_MAX))
            emitter:setField("coneInsideAngle", 0, tostring(HORN_CONE_IN))
            emitter:setField("coneOutsideAngle", 0, tostring(HORN_CONE_OUT))
            emitter:setField("coneOutsideVolume", 0, tostring(HORN_CONE_OUT_VOL))
          end)
          local registered = ok and registerInMission(
            emitter, string.format("sg_horn_p%d_%s_%s", state.propId,
                                   cue.name, horn.slot))
          if registered then
            state.effects[slot] = emitter
            made = made + 1
          else
            failed = failed + 1
            pcall(function() emitter:delete() end)
          end
        else
          failed = failed + 1
        end
      end
      if state.effects[slot] then have = have + 1 end
    end
  end
  state.behavior.hornOrigin = nil
  state.behavior.hornRot = nil
  Horn.place(state, true)
  state.behavior.hornReady = have > 0
  emitEvent(state, "I", "sumo_horns", {
    have = have, made = made, failed = failed,
    want = #HORN_CUE_LIST * #HORN_SPECS,
  })
end

-- Returns false when the pole could not take the cue, and the caller falls
-- back to the vehicle source. A missing emitter should cost an announcement
-- its POSITION, never the announcement.
Horn.play = function(state, name)
  if not state.behavior.hornReady then return false end
  local spoke = false
  for hi = 1, #HORN_SPECS do
    local emitter = state.effects[hornSlot(name, HORN_SPECS[hi])]
    if emitter then
      spoke = true
      -- Stop before play: these are looping sources, and re-announcing a take
      -- that is still sounding has to restart it, not be swallowed.
      pcall(function() emitter:stop() end)
      pcall(function() emitter:play() end)
    end
  end
  return spoke
end

Horn.stop = function(state, name)
  for hi = 1, #HORN_SPECS do
    local emitter = state.effects[hornSlot(name, HORN_SPECS[hi])]
    if emitter then pcall(function() emitter:stop() end) end
  end
end

Horn.stopAll = function(state)
  for ci = 1, #HORN_CUE_LIST do Horn.stop(state, HORN_CUE_LIST[ci].name) end
end

-- ONE way to speak and one way to hush, whichever wire carries the cue. The
-- pole is tried first and which path took it is remembered, so the stop goes
-- back down the same wire it came up. An unknown path (a table restored by an
-- older build) stops BOTH, which is the safe way round.
local function sayCall(state, tag)
  local b = state.behavior
  b.callVia = b.callVia or {}
  if Horn.play(state, tag) then
    b.callVia[tag] = "horn"
  else
    queueVehicleFx(state, "play_" .. tag)
    b.callVia[tag] = "veh"
  end
end

local function hushCall(state, tag)
  local b = state.behavior
  local via = b.callVia and b.callVia[tag]
  if via ~= "veh" then Horn.stop(state, tag) end
  if via ~= "horn" then queueVehicleFx(state, "stop_" .. tag) end
  if b.callVia then b.callVia[tag] = nil end
end

-- Announcer calls. THE PA IS ONE VOICE. playCall rolls a take and ENQUEUES
-- it; pumpCalls starts a clip only when the previous clip's own stop clock
-- has run out plus call_gap_seconds of deliberate dead air. Firing straight
-- at the vehicle was the bug: the corner-claim branches live inside a sweep
-- over EVERY vehicle within one frame, so with two cars already aboard when
-- the reset button opens the corners, both corners filled on the SAME frame
-- and both welcome calls started on the same frame and talked over each
-- other (player, 2026-08-14).
--
-- Each clip still gets ITS OWN stop clock via b.callStops - that table and
-- call_stop_seconds are unchanged, and remain the only timing authority for
-- when a clip may be cut. Serialising means only one entry is ever live in
-- it, but the pump still drains the table generically so a state saved by
-- an older build (several clips in the air at once) still stops cleanly.
--
-- Ordering is authored, not accidental: within one frame EAST reads before
-- WEST regardless of the order getAllVehicles happened to hand the sweep.
-- Two rivals resuming their own corners on the same frame is the case that
-- would otherwise come out backwards.
local CALL_RANK = {east = 1, west = 2}

-- How many welcome-back takes are eligible right now. The last one is
-- ROUND-TWO ONLY (player, 2026-08-14) - and when it is eligible it just
-- joins the pool, so round two rolls across all of them rather than always
-- playing that one. Rounds already decided is simply the two scores summed,
-- so re-entering after exactly one decision IS the walk-up to round two.
local function backTakes(state)
  local b = state.behavior
  local decided = (b.scoreE or 0) + (b.scoreW or 0)
  if decided == 1 then return B.back_takes end
  return B.back_takes - 1
end

local function playCall(state, kind, side, takes)
  local b = state.behavior
  local tag = kind .. "_" .. side .. "_"
    .. math.random(1, takes or B.call_takes)
  local rank = CALL_RANK[side] or 9
  local frame = b.frameN or 0
  b.callQ = b.callQ or {}
  -- Ordered insert, but ONLY against calls raised on this same frame: a call
  -- already waiting from an earlier frame was announced first in the world
  -- and keeps its place. Within the frame, lower rank goes first.
  local at = #b.callQ + 1
  while at > 1 do
    local prev = b.callQ[at - 1]
    if prev.frame ~= frame or prev.rank <= rank then break end
    b.callQ[at] = prev
    at = at - 1
  end
  b.callQ[at] = {tag = tag, rank = rank, frame = frame}
end

-- Start the head of the queue when the air is clear. "Clear" is the same
-- stop clock the calls already used - b.callStops empty means nothing is
-- sounding - plus call_gap_seconds of silence after it emptied.
local function pumpCalls(state, dt)
  local b = state.behavior
  local sounding = false
  if b.callStops then
    for tag, remaining in pairs(b.callStops) do
      remaining = remaining - dt
      if remaining <= 0 then
        b.callStops[tag] = nil
        hushCall(state, tag)
      else
        b.callStops[tag] = remaining
        sounding = true
      end
    end
  end
  if sounding then
    -- Re-arm the gap while anything is in the air, so the gap is always
    -- measured from the moment the air actually went quiet.
    b.callGapT = B.call_gap_seconds
    return
  end
  if (b.callGapT or 0) > 0 then
    b.callGapT = b.callGapT - dt
    return
  end
  local queued = b.callQ
  if not queued or #queued == 0 then return end
  local entry = table.remove(queued, 1)
  sayCall(state, entry.tag)
  b.callStops = b.callStops or {}
  b.callStops[entry.tag] = B.call_stop_seconds
  b.callGapT = B.call_gap_seconds
end

-- Draining the QUEUE matters as much as stopping what is sounding: without
-- it a reset taken mid-announcement would leak the calls still waiting into
-- the next match.
local function silenceCalls(state)
  local b = state.behavior
  b.callStops = {}
  b.callQ = {}
  -- Arm the gap rather than clearing it: cutting a clip off and starting the
  -- next one in the same instant is the one thing a PA never does, and after
  -- a reset it is exactly what would happen (the corners re-fill on the very
  -- next sweep, one frame later).
  b.callGapT = B.call_gap_seconds
  -- Both wires, unconditionally: this is the "silence everything" path and it
  -- runs after resets, where b.callVia may be stale or gone.
  Horn.stopAll(state)
  b.callVia = {}
  queueVehicleFx(state, "stopAllCalls")
end

-- The corner toasts had the same defect wearing a different coat: two
-- showMessage calls on one frame is not two toasts, it is the second one
-- overwriting the first, and the player never read the EAST name. These are
-- NOT serialised like the calls, because both corners filling at once is
-- genuinely ONE event (it is what pressing reset with two cars aboard
-- means) and one event deserves one line. The claim branches record the
-- name; the flush at the end of the frame decides whether that frame was
-- one claim or two. The single-claim wording and its 3.2 s are untouched -
-- that is the common case and it must not change.
local function flushCornerToast(state)
  local b = state.behavior
  local e, w = b.toastE, b.toastW
  b.toastE, b.toastW = nil, nil
  if e and w then
    showMessage("EAST CORNER - " .. e .. "     WEST CORNER - " .. w, 4.0)
  elseif e then
    showMessage("EAST CORNER - " .. e, 3.2)
  elseif w then
    showMessage("WEST CORNER - " .. w, 3.2)
  end
end

-- It answers four questions at once: who is aboard (torque), who is in the
-- boarding corridor (interlock), who is close enough that the deck owes a
-- collision rebuild, and whether anything has somehow got UNDER the deck.
local function sweepDeck(state, dt)
  local b = state.behavior
  b.riders = 0
  b.parked = 0
  b.corridor = 0
  b.queuing = 0
  b.watchers = 0
  b.trapped = 0
  -- Aboard stamps age out every sweep: staging must read a competitor's
  -- CURRENT presence, never a stale last-aboard position.
  if b.fieldTrack then
    for _, entry in pairs(b.fieldTrack) do entry.aboard = nil end
  end
  b.torqueX = 0
  b.torqueY = 0
  -- Fail SAFE, not cheap: if the vehicle list is unavailable the machine
  -- assumes somebody is within reach, so a broken sweep costs collision
  -- rebuilds rather than skipping one that was owed.
  local ok, all = pcall(getAllVehicles)
  if not ok or type(all) ~= "table" then
    b.watchers = 1
    return
  end
  -- All three axes, not just two: dotting against the prop's own basis is
  -- exact for any spawn orientation, whereas taking delta.z as the authored
  -- height silently assumes the prop was placed dead level.
  local ex = toWorldDir(state, vec3(1, 0, 0))
  local ey = toWorldDir(state, vec3(0, 1, 0))
  local ez = toWorldDir(state, vec3(0, 0, 1))
  local origin = state.origin
  if not origin then
    b.watchers = 1
    return
  end
  for _, vehicle in ipairs(all) do
    local idOk, vehicleId = pcall(function() return vehicle:getId() end)
    if idOk and eligibleSubject(vehicleId) then
      local position = vehicle:getPosition()
      if finiteVector3(position) then
        local delta = position - origin
        local x = delta:dot(ex)
        local y = delta:dot(ey)
        local z = delta:dot(ez)
        local r = math.sqrt(x * x + y * y)
        -- Hysteresis band: a car that was a watcher last frame keeps the
        -- status until it leaves radius + hysteresis, so a vehicle parked
        -- exactly on the boundary cannot toggle the watched state (and
        -- re-arm the debt bake) with position noise.
        local wasWatch = b.watch and b.watch[vehicleId]
        local watchR = B.bake_watch_radius
          + (wasWatch and B.bake_watch_hysteresis or 0)
        if r <= watchR then
          b.watchers = b.watchers + 1
          if b.watch then b.watch[vehicleId] = true end
        elseif wasWatch then
          b.watch[vehicleId] = nil
        end
        local height = z - deckSurfaceZ(state, x, y)
        local claimed = false
        if r <= B.wall_inner_r and height <= B.under_deck_below then
          b.trapped = b.trapped + 1
          claimed = true
        elseif r <= B.load_radius
          and height >= B.aboard_below and height <= B.aboard_above then
          claimed = true
          -- Two-competitor registration: the first two cars aboard take the
          -- EAST then WEST corners and keep them - scores live on the board
          -- - until the reset button or their own despawn releases them.
          -- Nobody else is tracked; a third car aboard is a spectator.
          local isE = b.slotE and b.slotE.id == vehicleId
          local isW = b.slotW and b.slotW.id == vehicleId
          if not isE and not isW
            and b.phase ~= "live" and b.phase ~= "decided" then
            -- A corner whose car despawned keeps its NAME on the board
            -- ("last battling") but its seat is open: a new claimant takes
            -- the corner and that corner's score starts over.
            -- Coming BACK to your own corner is not a new registration.
            -- Everything in the claim branches - zeroing that corner's
            -- score, the toast, the welcome call - is for a NEW RIVAL
            -- taking over an open corner. Firing it for the same car cost
            -- EAST every win it had: the corner was vacated between
            -- matches, the same car re-claimed it, and the "new claimant
            -- starts over" rule wiped its own score every round (live log,
            -- 2026-08-14).
            --
            -- RESUMING IS CHECKED FIRST, both corners before either claim,
            -- or two returning rivals with both seats open would swap
            -- corners and wipe BOTH scores between them.
            local resumeE = b.slotE and b.slotE.id == nil
              and b.slotE.lastId == vehicleId
            local resumeW = b.slotW and b.slotW.id == nil
              and b.slotW.lastId == vehicleId
            if resumeE then
              b.slotE.id = vehicleId
              isE = true
              playCall(state, "back", "east", backTakes(state))
            elseif resumeW then
              b.slotW.id = vehicleId
              isW = true
              playCall(state, "back", "west", backTakes(state))
            elseif b.slotE == nil or b.slotE.id == nil then
              if b.slotE then b.scoreE = 0 end
              b.slotE = {id = vehicleId, name = vehName(vehicle)}
              isE = true
              b.toastE = b.slotE.name
              playCall(state, "welcome", "east")
              emitEvent(state, "I", "sumo_registered",
                {corner = "east", subject_id = vehicleId})
            elseif b.slotW == nil or b.slotW.id == nil then
              if b.slotW then b.scoreW = 0 end
              b.slotW = {id = vehicleId, name = vehName(vehicle)}
              isW = true
              b.toastW = b.slotW.name
              playCall(state, "welcome", "west")
              emitEvent(state, "I", "sumo_registered",
                {corner = "west", subject_id = vehicleId})
            end
          end
          local entry, limit = stillTime(state, vehicleId, x, y, dt)
          -- A registered competitor's weight ALWAYS moves the deck during a
          -- match: the derelict purge (which un-counts a car standing still
          -- 20 s) exists to stop abandoned cars pinning open-ended rounds,
          -- and it made braked play-testing read as a dead machine.
          if contender(state, vehicleId, entry, limit)
            or ((isE or isW) and (b.phase == "live" or b.phase == "decided")) then
            local mass = subjectMass(state, vehicleId)
            -- Weight moment about the bearing: M = r x (0, 0, -m g).
            b.torqueX = b.torqueX - mass * B.gravity * y
            b.torqueY = b.torqueY + mass * B.gravity * x
            b.riders = b.riders + 1
          else
            b.parked = b.parked + 1
          end
          -- Spin drag field (the washer/centrifuge recipe): steer the car's
          -- authored-plane velocity toward the surface's omega x r, bounded
          -- per frame. A field-matched car still needs omega^2 * r of tire
          -- grip to hold its circle - running out of grip IS the endgame.
          local ft = b.fieldTrack and b.fieldTrack[vehicleId]
          if ft and dt > 1e-4 then
            local vx = (x - ft.x) / dt
            local vy = (y - ft.y) / dt
            local speed = math.sqrt(vx * vx + vy * vy)
            ft.spd = speed
            if b.phase == "live" and (b.omega or 0) > 0
              and r > B.spin_min_r and speed < 60.0 then
              -- TANGENTIAL COMPONENT ONLY (live round 2026-08-13: matching
              -- the full velocity vector fought throttle and steering at
              -- grip-level accel - cars read as "locked in place"). The
              -- field carries you AROUND; driving across it stays yours.
              local tx, ty = -y / r, x / r
              local vt = vx * tx + vy * ty
              local dvt = (b.omega * r) - vt
              local cap = B.spin_drag_accel * dt
              if dvt > cap then dvt = cap end
              if dvt < -cap then dvt = -cap end
              addSubjectVelocity(state, vehicle, ex * (tx * dvt) + ey * (ty * dvt))
            end
          end
          if b.fieldTrack then
            b.fieldTrack[vehicleId] = ft or {}
            b.fieldTrack[vehicleId].x = x
            b.fieldTrack[vehicleId].y = y
            b.fieldTrack[vehicleId].aboard = true
          end
        end
        -- Corridor test in the ramp's own frame: s along the centreline, d
        -- across it. A rectangle, not a bounding box, and it reads the
        -- vehicle CENTRE - the Contains trigger it replaces dropped a moving
        -- car the instant its bbox left the zone. Only vehicles the deck has
        -- NOT already claimed are eligible: the corridor starts 0.6 m inboard
        -- of the threshold so a car straddling the joint is caught, and
        -- without this guard a rider parked near the boarding edge would hold
        -- its own countdown and then call its own round off.
        if not claimed then
          local s = x * B.corridor_cos + y * B.corridor_sin
          local d = -x * B.corridor_sin + y * B.corridor_cos
          if s >= B.corridor_near and s <= B.corridor_far
            and math.abs(d) <= B.corridor_half
            and z >= B.corridor_z_min and z <= B.corridor_z_max then
            b.corridor = b.corridor + 1
            -- Only a car that is still MOVING counts as queuing. Without
            -- this, one abandoned car on the ramp would call every round off
            -- after corridor_end_seconds forever - the machine would cycle
            -- endlessly and no round would ever be fought.
            local entry = stillTime(state, vehicleId, x, y, dt)
            if entry.still < B.stuck_seconds then
              b.queuing = b.queuing + 1
            end
          end
        end
      end
    end
  end
end

local function pruneCaches(state, dt)
  local b = state.behavior
  b.massPrune = (b.massPrune or 0) + dt
  if b.massPrune < B.mass_prune_seconds then return end
  b.massPrune = 0
  if b.mass then
    for vehicleId in pairs(b.mass) do
      if not exactVehicle(vehicleId) then b.mass[vehicleId] = nil end
    end
  end
  if b.track then
    for vehicleId in pairs(b.track) do
      if not exactVehicle(vehicleId) then b.track[vehicleId] = nil end
    end
  end
  if b.watch then
    for vehicleId in pairs(b.watch) do
      if not exactVehicle(vehicleId) then b.watch[vehicleId] = nil end
    end
  end
  if b.fieldTrack then
    for vehicleId in pairs(b.fieldTrack) do
      if not exactVehicle(vehicleId) then b.fieldTrack[vehicleId] = nil end
    end
  end
end

-- Wall clock in milliseconds for the frame-cost sampler. os.clockhp is
-- BeamNG's high-resolution clock; plain os.clock is the fallback; a sandbox
-- with neither runs without adaptivity (interval_eff stays at the base).
local clockMs = nil
do
  local src = os and (os.clockhp or os.clock) or nil
  if src then clockMs = function() return src() * 1000.0 end end
end

-- Effective bake interval and flow limit under adaptive backoff. The two move
-- in LOCKSTEP: rate = step / interval_eff is the invariant that keeps the
-- committed pose within one bake step of the physical one, so a machine that
-- slows its rebuild cadence slows its rams by exactly the same factor.
-- (Declared above integrate/bleedToLevel on purpose: Lua locals bind at
-- definition point, and both of those call effRateMax.)
local function effInterval(b)
  local stretch = 1.0
  if b.bakeMs and (B.bake_cost_budget_ms or 0) > 0 then
    stretch = b.bakeMs / B.bake_cost_budget_ms
    if stretch < 1.0 then stretch = 1.0 end
    if stretch > B.bake_backoff_max then stretch = B.bake_backoff_max end
  end
  return B.bake_interval * stretch
end

local function effRateMax(b)
  return B.bake_step_rad / effInterval(b)
end

-- The one place a rebuild is requested. The reload itself is deferred to the
-- framework's frame tail, so the cost is attributed by the sampler in
-- behavior.update, not timed here: bakePending marks the frame as a payer.
local function bakeNow(state)
  local b = state.behavior
  b.bakeClock = 0
  b.bakes = (b.bakes or 0) + 1
  b.bakePending = true
  requestCollisionReload(state)
end

-- Semi-implicit Euler on I*psi'' = T - K*psi - c*psi', per axis, plus the
-- hydraulic flow limit and the bump stops.
local function integrate(state, dt)
  local b = state.behavior
  local tx, ty = 0, 0
  if b.phase == "live" then
    tx, ty = b.torqueX, b.torqueY
    local mag = math.sqrt(tx * tx + ty * ty)
    if mag > B.torque_cap then
      tx = tx * B.torque_cap / mag
      ty = ty * B.torque_cap / mag
    end
  end
  local damping = (b.phase == "relevel") and B.damping_relevel or B.damping
  local accelX = (tx - B.stiffness * b.psiX - damping * b.velX) / B.inertia
  local accelY = (ty - B.stiffness * b.psiY - damping * b.velY) / B.inertia
  b.velX = b.velX + accelX * dt
  b.velY = b.velY + accelY * dt
  -- Hydraulic flow limit: the rams cannot pass oil faster than this, so the
  -- deck surface can never exceed rate * 13.10 = 0.156 m/s at the rim at the
  -- base interval. Under adaptive backoff the limit follows step/interval_eff
  -- so the committed pose still never lags by more than one step.
  local rateCap = effRateMax(b)
  local rate = math.sqrt(b.velX * b.velX + b.velY * b.velY)
  if rate > rateCap then
    b.velX = b.velX * rateCap / rate
    b.velY = b.velY * rateCap / rate
  end
  b.psiX = b.psiX + b.velX * dt
  b.psiY = b.psiY + b.velY * dt
  -- Bump stops. Inelastic: the outward component of the rate is DELETED, so
  -- the stop can only ever remove energy. Nothing riding the deck is pushed.
  local tilt = math.sqrt(b.psiX * b.psiX + b.psiY * b.psiY)
  if tilt > B.tilt_max_rad then
    local scale = B.tilt_max_rad / tilt
    b.psiX = b.psiX * scale
    b.psiY = b.psiY * scale
    local ux = b.psiX / B.tilt_max_rad
    local uy = b.psiY / B.tilt_max_rad
    local radial = b.velX * ux + b.velY * uy
    if radial > 0 then
      b.velX = b.velX - radial * ux
      b.velY = b.velY - radial * uy
    end
  end
  if not (finiteNumber(b.psiX) and finiteNumber(b.psiY)
    and finiteNumber(b.velX) and finiteNumber(b.velY)) then
    b.psiX, b.psiY, b.velX, b.velY = 0, 0, 0, 0
    emitError(state, "tilt_integrator_nonfinite")
  end
end

-- Walk the state down to level at the flow limit. Used only as the re-level
-- backstop, so "settled" is never an asymptote we wait on. The rate is eased
-- in over relevel_bleed_ramp seconds: an asymptotic return has almost no
-- speed left when the backstop engages, and stepping straight to the flow
-- limit would be a visible change of pace under a survivor's wheels.
local function bleedToLevel(state, dt)
  local b = state.behavior
  local ramp = (b.relevelT - B.relevel_hard_seconds) / B.relevel_bleed_ramp
  if ramp > 1 then ramp = 1 elseif ramp < 0 then ramp = 0 end
  local tilt = math.sqrt(b.psiX * b.psiX + b.psiY * b.psiY)
  local step = effRateMax(b) * ramp * dt
  if tilt <= step or tilt < 1e-9 then
    b.psiX, b.psiY = 0, 0
  else
    b.psiX = b.psiX - step * b.psiX / tilt
    b.psiY = b.psiY - step * b.psiY / tilt
  end
  b.velX, b.velY = 0, 0
end

-- The only place the deck's visual and its collision are written, and they
-- are written from the same two numbers. Returns true when a bake landed.
--
-- Two properties this function is responsible for:
--   * The committed pose advances toward the physical one by AT MOST one bake
--     step and carries the remainder. Snapping com = psi instead (the first
--     cut) delivers bake_step + rate_max*dt, which is frame-rate dependent
--     and measured 26.7 mm at 60 fps against a 20 mm budget.
--   * While no eligible vehicle is inside bake_watch_radius, nothing can
--     touch the deck, so the state is kept in sync but the GLOBAL collision
--     rebuild is skipped entirely and the machine owes one debt bake for
--     when a vehicle next appears. An idle machine and an empty re-level
--     cost the engine nothing.
local function commitPose(state, dt, force)
  local b = state.behavior
  b.bakeClock = (b.bakeClock or 0) + dt
  local errX = b.psiX - b.comX
  local errY = b.psiY - b.comY
  local err = math.sqrt(errX * errX + errY * errY)
  if (b.watchers or 0) <= 0 then
    if err > 0 then
      b.comX, b.comY = b.psiX, b.psiY
      b.needBake = true
    end
    return false
  end
  -- The interval gates EVERY bake, the owed debt bake included. After a long
  -- unwatched glide bakeClock is already far past the interval, so the first
  -- watched frame still bakes immediately; only rapid re-crossings of the
  -- watch boundary are throttled. (Running the debt branch before this gate
  -- is the bug that made the old "ceiling by construction" claim false.)
  if b.bakeClock < effInterval(b) then return false end
  if b.needBake then
    b.needBake = false
    bakeNow(state)
    return true
  end
  if not force and err < B.bake_step_rad then return false end
  -- err == 0 with force set means com == psi ~= 0 exactly: nothing to move,
  -- so no bake is owed - without this guard a locked machine resting at a
  -- nonzero committed pose would burn a zero-move rebuild every interval.
  if err < 1e-12 then return false end
  local move = err
  if move > B.bake_step_rad then move = B.bake_step_rad end
  b.comX = b.comX + errX * move / err
  b.comY = b.comY + errY * move / err
  bakeNow(state)
  return true
end

-- Every reachable pose of this part is a drivable floor: the deck is a dish
-- with |slope| <= 5.5 deg + 1.7 deg of dish, it has no vertical faces a car
-- can meet from the deck side, and it never travels through a lane. That is
-- why a stale bake here is safe in a way the centrifuge's sliding door never
-- was (AGENTS.md mouth-shelf law: endpoint-bake is only safe when BOTH
-- endpoints are safe - here EVERY point of the travel is an endpoint).
local function poseDeck(state)
  local b = state.behavior
  -- Spin about the deck's own axis FIRST, then tilt (quats compose
  -- left-to-right: a*b = a-then-b). The disc is axisymmetric, so its baked
  -- collision is pose-invariant under spin - only the 15 mm paint reliefs
  -- sweep, inside the drivable cap - which is why the spin costs zero extra
  -- collision rebuilds.
  local tq = tiltQuat(b.comX, b.comY)
  setPartPose(state, "deck", nil, rhq(vec3(0, 0, 1), b.spinAngle or 0) * tq)
  -- The drive wheel is SLAVED to the deck's own measured angle change, not
  -- to a second integrator: rolling contact means it turns drive_ratio times
  -- per deck turn, the other way. Reading the deck means spin-up, decay and
  -- the wind-back home all drive it correctly with nothing to keep in step.
  local ds = (b.spinAngle or 0) - (b.spinPrev or 0)
  while ds > math.pi do ds = ds - 2 * math.pi end
  while ds < -math.pi do ds = ds + 2 * math.pi end
  b.spinPrev = b.spinAngle or 0
  local drive = (b.driveAngle or 0) - ds * B.drive_ratio
  -- Wrap rather than let a long session accumulate: float precision on a
  -- multi-thousand-radian angle turns a smooth wheel into a jittering one.
  while drive > math.pi do drive = drive - 2 * math.pi end
  while drive < -math.pi do drive = drive + 2 * math.pi end
  b.driveAngle = drive
  setPartPose(state, "drive_wheel", vec3(0, 0, 0), rhq(vec3(0, 0, 1), drive))
  -- Fluorescent rings: annuli are spin-invariant, so they ride tilt only.
  -- Hidden = dropped into the deck body, the CHIEF pose-swap idiom.
  -- Explicit zero, never nil: setPartPose treats a nil offset as "keep the
  -- previous offset", so nil-as-shown left anything once hidden hidden
  -- forever (live round 2026-08-13: the WIN plate and both rings).
  local hide = vec3(0, 0, -(B.ring_hide_drop or 0.3))
  local shown = vec3(0, 0, 0)
  setPartPose(state, "ring_live", b.ringLive and shown or hide, tq)
  setPartPose(state, "ring_ko", b.ringKo and shown or hide, tq)
end

-- The match board: pips show wins (a full row is the set), result plates
-- pose WIN / LOSS after a decision, and everything hides by sliding behind
-- the apertured faces. Corner identity is COLOR (East vermilion / West
-- cream) because runtime text does not exist in this engine - the entry
-- toast carries the vehicle's name instead.
local function poseMatchBoard(state)
  local b = state.behavior
  -- vec3(0,0,0) for "shown", never nil (nil = keep previous offset).
  local pipHide = vec3(0, 0, -B.sb_pip_hide)
  local pipShow = vec3(0, 0, 0)
  for i = 1, 5 do
    setPartPose(state, "pip_e_" .. i,
      (i <= (b.scoreE or 0)) and pipShow or pipHide, nil)
    setPartPose(state, "pip_w_" .. i,
      (i <= (b.scoreW or 0)) and pipShow or pipHide, nil)
  end
  local function resultOffset(result)
    if result == "win" then return vec3(0, 0, 0) end
    if result == "loss" then return vec3(0, 0, B.sb_result_shift) end
    return vec3(0, 0, -B.sb_result_hide)
  end
  setPartPose(state, "result_e", resultOffset(b.resultE), nil)
  setPartPose(state, "result_w", resultOffset(b.resultW), nil)
end

-- Four centring rams, each authored in its true rest attitude (foot to eye)
-- and each split the way a real cylinder is: a rigid steel BARREL pinned at
-- the foot, and a chrome ROD that slides out of it to meet the deck eye. The
-- barrel is only aimed; the rod is aimed and then translated along its own
-- axis by exactly (length - rest). Nothing is scaled, and nothing is faked.
local function poseRams(state)
  local b = state.behavior
  for index = 1, 4 do
    local foot = b.ramFoot[index]
    local eye = b.ramEye[index]
    local rest = b.ramRest[index]
    -- Eye position after the deck rotation, about the bearing centre.
    local rel = vec3(eye.x, eye.y, eye.z - B.pivot_z)
    local moved = tiltQuat(b.comX, b.comY) * rel
    local dx = moved.x - foot.x
    local dy = moved.y - foot.y
    local dz = (moved.z + B.pivot_z) - foot.z
    local length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length > 0.05 then
      local ux, uy, uz = dx / length, dy / length, dz / length
      local axis = b.ramAxis[index]
      local aim = alignQuat(axis.x, axis.y, axis.z, ux, uy, uz)
      local reach = length - rest
      setPartPose(state, "ram_" .. index, nil, aim)
      setPartPose(state, "ram_rod_" .. index,
        vec3(ux * reach, uy * reach, uz * reach), aim)
    end
  end
end

local function setPhase(state, phase)
  local b = state.behavior
  if b.phase == phase then return end
  b.phase = phase
  b.phaseT = 0
  -- warn() measures its cooldown in phaseT, which just restarted; keeping the
  -- old key would suppress the new phase's first warning for several seconds.
  b.warnKey = nil
  b.warnT = nil
  emitEvent(state, "I", "phase", {phase = phase, riders = b.riders or 0})
end

local function vent(state)
  local b = state.behavior
  b.ventT = B.vent_seconds
  setEffectActive(state, "valve_vent", true)
end

-- Rate-limited nag, one channel, so three different warnings cannot stack.
local function warn(state, key, seconds, message)
  local b = state.behavior
  if b.warnKey ~= key or (b.phaseT - (b.warnT or -99)) > seconds then
    b.warnKey = key
    b.warnT = b.phaseT
    showMessage(message, 2.4)
  end
end

-- The player's KO rule verbatim: ANY part of the car past the clay is out.
-- OOBB corners, horizontal radius in the authored plane about the bearing.
local function koCornerRadius(state, vehicle)
  local origin = state.origin
  if not origin then return nil end
  local ex = toWorldDir(state, vec3(1, 0, 0))
  local ey = toWorldDir(state, vec3(0, 1, 0))
  local worst = nil
  pcall(function()
    local oobb = vehicle:getSpawnWorldOOBB()
    for i = 0, 7 do
      local p = oobb:getPoint(i)
      local d = vec3(p.x, p.y, p.z) - origin
      local lx, ly = d:dot(ex), d:dot(ey)
      local rr = math.sqrt(lx * lx + ly * ly)
      if not worst or rr > worst then worst = rr end
    end
  end)
  return worst
end

-- One winner, one loser, never a draw. Pips advance, result plates pose,
-- the red ring flares, and the machine savours it before tidying up.
local function decideMatch(state, loser, reason)
  local b = state.behavior
  local winner = (loser == "east") and "west" or "east"
  if winner == "east" then b.scoreE = (b.scoreE or 0) + 1
  else b.scoreW = (b.scoreW or 0) + 1 end
  b.resultE = (winner == "east") and "win" or "loss"
  b.resultW = (winner == "west") and "win" or "loss"
  b.ringLive = false
  b.ringKo = true
  local winScore = (winner == "east") and b.scoreE or b.scoreW
  if winScore >= B.set_wins then
    b.setDone = winner
    showMessage(string.format("%s TAKES THE SET  %d - %d",
      string.upper(winner), b.scoreE or 0, b.scoreW or 0), 4.5)
  else
    showMessage(string.format("%s WINS  %d - %d",
      string.upper(winner), b.scoreE or 0, b.scoreW or 0), 4.0)
  end
  emitEvent(state, "I", "sumo_decided", {winner = winner, loser = loser,
    reason = reason, score_e = b.scoreE, score_w = b.scoreW})
  -- The win call. Three takes per corner, rolled fresh each time so the
  -- same victory never sounds canned twice running; the CORNER is not
  -- random, only the take. Same faked one-shot as the countdown - a loop
  -- source stopped inside the ogg's silent pad by a phase-independent clock.
  playCall(state, "win", winner)
  vent(state)
  b.decidedT = 0
  setPhase(state, "decided")
end

local function updateOpen(state, dt)
  local b = state.behavior
  -- Locked level: the ram bypass valves are shut, the integrator is parked at
  -- zero, and the ramp/deck junction is flush. ZERO collision reloads happen
  -- in this phase once the deck has finished walking to exact level.
  b.psiX, b.psiY, b.velX, b.velY = 0, 0, 0, 0
  b.omega = 0
  if b.trapped > 0 then
    warn(state, "trapped", 4.0,
      "VEHICLE UNDER THE DECK - gimbal locked. Back out through the ramp.")
    return
  end
  -- Staging, not signage: two claimed corners squared off across the
  -- shikiri-sen ARE the start button. Both inside stage_radius, one on each
  -- side of the gate axis, apart, slow, ramp corridor clear, held for
  -- stage_hold_seconds - then the countdown sings. The machine explains
  -- itself by what it does, not by what it says.
  local e = b.slotE and b.fieldTrack and b.fieldTrack[b.slotE.id]
  local w = b.slotW and b.fieldTrack and b.fieldTrack[b.slotW.id]
  local staged = false
  if e and w and e.aboard and w.aboard and (b.corridor or 0) == 0 then
    local re = math.sqrt(e.x * e.x + e.y * e.y)
    local rw = math.sqrt(w.x * w.x + w.y * w.y)
    local se = e.x * B.ramp_az_cos + e.y * B.ramp_az_sin
    local sw = w.x * B.ramp_az_cos + w.y * B.ramp_az_sin
    local gap = math.sqrt((e.x - w.x) ^ 2 + (e.y - w.y) ^ 2)
    staged = re <= B.stage_radius and rw <= B.stage_radius
      and se * sw < 0 and gap >= B.stage_min_gap
      and (e.spd or 9) <= B.stage_speed and (w.spd or 9) <= B.stage_speed
  end
  if staged then
    b.stageT = (b.stageT or 0) + dt
    if b.stageT >= B.stage_hold_seconds then
      b.stageT = 0
      b.resultE, b.resultW = nil, nil
      sayCall(state, "countdown")
      b.cdStopT = B.countdown_stop_seconds
      setPhase(state, "countdown")
    end
  else
    b.stageT = 0
  end
end

-- 3... 2... 1... LET'S GO. The deck stays locked under the audio; the ring
-- goes live the moment GO lands (countdown_go_seconds into the clip).
local function updateCountdown(state, dt)
  local b = state.behavior
  b.psiX, b.psiY, b.velX, b.velY = 0, 0, 0, 0
  b.omega = 0
  if b.trapped > 0 then
    hushCall(state, "countdown")
    b.cdStopT = nil
    setPhase(state, "open")
    return
  end
  if b.phaseT >= B.countdown_go_seconds then
    b.ringLive = true
    b.roundT = 0
    b.clearT = 0
    b.spinAngle = 0
    vent(state)
    setPhase(state, "live")
  end
end

-- After the KO: the spin bleeds off while everyone reads the board, then
-- both competitors are set down side by side in front of the ramp, facing
-- the ring, with room to line up for the next match.
local function updateDecided(state, dt)
  local b = state.behavior
  b.decidedT = (b.decidedT or 0) + dt
  b.omega = math.max(0, (b.omega or 0) - B.spin_decel * dt)
  b.spinAngle = (b.spinAngle or 0) + b.omega * dt
  if b.decidedT >= B.decided_hold_seconds then
    local dirx, diry = B.ramp_az_cos, B.ramp_az_sin
    local px, py = -diry, dirx
    for _, entry in ipairs({{1, b.slotE}, {-1, b.slotW}}) do
      local sign, slot = entry[1], entry[2]
      local vehicle = slot and exactVehicle(slot.id)
      if vehicle then
        local ax = dirx * B.reset_dist + px * (sign * B.reset_gap)
        local ay = diry * B.reset_dist + py * (sign * B.reset_gap)
        local pos = toWorldPoint(state, vec3(ax, ay, 0.6))
        -- BeamNG vehicle space runs -Y forward: map that onto the ring-ward
        -- direction so both cars face the ramp they are about to climb.
        local face = toWorldDir(state, vec3(-dirx, -diry, 0))
        local rot = alignQuat(0, -1, 0, face.x, face.y, face.z)
        pcall(function() teleportSubject(state, vehicle, pos, rot) end)
      end
    end
    b.ringKo = false
    b.omega = 0
    b.relevelT = 0
    setPhase(state, "relevel")
  end
end

local function endRound(state, message)
  local b = state.behavior
  setPhase(state, "relevel")
  b.relevelT = 0
  vent(state)
  showMessage(message, 2.8)
end

local function updateLive(state, dt)
  local b = state.behavior
  b.roundT = b.roundT + dt
  -- Escalation: the ring spins up CONTINUOUSLY, never in steps. Holding a
  -- circle on the carried surface needs omega^2 * r of centripetal grip, so
  -- the longer a match runs the smaller the survivable ring becomes - which
  -- is why there is no draw clock: physics ends every stalemate.
  b.omega = math.min(B.spin_omega_max, (b.omega or 0) + B.spin_accel * dt)
  b.spinAngle = (b.spinAngle or 0) + b.omega * dt
  if (b.riders or 0) <= 0 and (b.parked or 0) <= 0 then
    b.clearT = b.clearT + dt
  else
    b.clearT = 0
  end
  if b.trapped > 0 then
    b.omega = 0
    b.ringLive = false
    endRound(state, "SAFETY STOP - something is under the deck. Levelling.")
    return
  end
  if b.clearT >= B.clear_debounce then
    b.ringLive = false
    b.omega = 0
    endRound(state, "Ring abandoned - match void.")
    return
  end
  if b.roundT >= B.match_max_seconds then
    b.ringLive = false
    b.omega = 0
    endRound(state, "Match void - levelling.")
    return
  end
  -- KO watch: first competitor with any OOBB corner past the clay is out.
  for _, side in ipairs({"east", "west"}) do
    local slot = (side == "east") and b.slotE or b.slotW
    local vehicle = slot and exactVehicle(slot.id)
    if vehicle then
      local worst = koCornerRadius(state, vehicle)
      if worst and worst > B.ko_radius then
        decideMatch(state, side, "over_the_edge")
        return
      end
    end
  end
end

-- Wind the deck back to its home angle. The arena has a DOORWAY - the lip's
-- gap at the ramp - and the deck's baked collision is authored at spin 0, so
-- a ring left standing at whatever angle the KO happened to stop it at shows
-- a wall where the entrance is and an entrance where the wall is. Homing runs
-- during re-levelling, i.e. after the cars have been set down, and the drive
-- wheel turns with it because poseDeck reads the deck's own angle change.
-- Returns true once it is home.
local function homeSpin(state, dt)
  local b = state.behavior
  local spin = b.spinAngle or 0
  -- Shortest way round: unwrap into (-pi, pi] first, so a ring stopped at
  -- 359 deg backs up one degree instead of grinding the long way.
  while spin > math.pi do spin = spin - 2 * math.pi end
  while spin < -math.pi do spin = spin + 2 * math.pi end
  local step = B.spin_home_rate * dt
  if math.abs(spin) <= math.max(step, B.spin_home_eps) then
    b.spinAngle = 0
    return true
  end
  b.spinAngle = spin - (spin > 0 and step or -step)
  return false
end

local function updateRelevel(state, dt)
  local b = state.behavior
  b.relevelT = b.relevelT + dt
  local homed = homeSpin(state, dt)
  local tilt = math.sqrt(b.psiX * b.psiX + b.psiY * b.psiY)
  local rate = math.sqrt(b.velX * b.velX + b.velY * b.velY)
  if homed and tilt <= B.level_eps_rad and rate <= B.rate_eps then
    b.psiX, b.psiY, b.velX, b.velY = 0, 0, 0, 0
    if b.setDone then
      -- Set complete: the pips clear for a fresh set; the corners stay
      -- claimed - same rivals, next set - until the reset button says
      -- otherwise.
      b.scoreE, b.scoreW = 0, 0
      b.resultE, b.resultW = nil, nil
      b.setDone = nil
    end
    setPhase(state, "open")
  end
end

-- The nobori are soft-body cloth, so they stream on BeamNG's PHYSICS ground
-- wind (core_environment.getGroundWind, broadcast to every vehicle as
-- obj:setWind). Note this engine has TWO unrelated wind systems: that one,
-- and the legacy Torque cloud/foliage wind whose getWindSpeed() returns
-- cloud scroll speed - reading it here would be a silent no-op.
local function seedBreeze(state)
  if (B.breeze_mps or 0) <= 0 then return end
  pcall(function()
    if not (core_environment and core_environment.getGroundWind
      and core_environment.setGroundWind) then return end
    local wind = core_environment.getGroundWind()
    -- Seed DEAD AIR only: a wind the player dialled in has to win.
    if wind and wind:length() > 0.01 then return end
    local heading = math.rad(B.breeze_heading_deg or 0)
    core_environment.setGroundWind(
      math.sin(heading) * B.breeze_mps,
      math.cos(heading) * B.breeze_mps,
      0)
  end)
end

-- Rebuild the derived geometry every init/reset. Kept apart from the state
-- reset so behavior.reset can restore the machine's geometry without
-- discarding the pose it is currently holding.
local function buildGeometry(state)
  local b = state.behavior
  b.ramFoot = {}
  b.ramEye = {}
  b.ramRest = {}
  b.ramAxis = {}
  for index = 1, 4 do
    local angle = (index - 1) * math.pi * 0.5
    local c, s = math.cos(angle), math.sin(angle)
    local foot = vec3(c * B.ram_foot_r, s * B.ram_foot_r, B.ram_foot_z)
    local eye = vec3(c * B.ram_eye_r, s * B.ram_eye_r, B.ram_eye_z)
    local dx, dy, dz = eye.x - foot.x, eye.y - foot.y, eye.z - foot.z
    local rest = math.sqrt(dx * dx + dy * dy + dz * dz)
    b.ramFoot[index] = foot
    b.ramEye[index] = eye
    b.ramRest[index] = rest
    -- The as-built axis. The Blender generator lays every ram piece along
    -- this same unit vector, so aim = identity at rest.
    b.ramAxis[index] = vec3(dx / rest, dy / rest, dz / rest)
  end
end

-- The competitors' NAMES, pushed into the board's own lit windows. Baked
-- textures cannot change at runtime, so the painted layer stays EAST/WEST
-- and the names live on a webview texture the vehicle VM owns (see
-- VEHICLE_LUA_EXTRA). This used to be debug-overlay text, which draws at a
-- fixed SCREEN size and so could only hover in front of the board however
-- the geometry was arranged (player, 2026-08-14).
--
-- A name is not a continuously varying quantity: push when it CHANGES, plus
-- a slow heartbeat so a page that came up late still gets filled.
local function pushNames(state, dt, force)
  local b = state.behavior
  local east = (b.slotE and b.slotE.name) or ""
  local west = (b.slotW and b.slotW.name) or ""
  b.nameBeat = (b.nameBeat or 0) + (dt or 0)
  if not force and east == b.nameE and west == b.nameW and b.nameBeat < 2.0 then
    return
  end
  b.nameBeat = 0
  b.nameE, b.nameW = east, west
  pcall(function()
    local propObj = be:getObjectByID(state.propId)
    if not propObj then return end
    -- Tables cannot cross the VM boundary: JSON in, %q to make it a safe
    -- Lua string literal, jsonDecode on the far side.
    propObj:queueLuaCommand(string.format(
      "extensions.hook('onEricrolphSumoGyroName', %q)",
      jsonEncode({east = east, west = west})))
  end)
end

local function poseAll(state, dt)
  poseDeck(state)
  poseRams(state)
  poseMatchBoard(state)
  pushNames(state, dt)
end

-- Every tunable this chunk reads. The framework pcalls behavior.init and
-- DISCARDS the result, so a handoff that is missing a key (the classic
-- failure: edit spec.py, rebuild only build.py, never re-run Blender) would
-- otherwise throw on the first arithmetic and vanish without a word. Checking
-- first turns that into a named error and a toast, and because every part is
-- authored in its correct rest pose the machine then simply stands there
-- looking right instead of sprouting hardware through the deck.
local REQUIRED = {
  "inertia", "stiffness", "damping", "damping_relevel", "torque_cap",
  "gravity", "tilt_max_rad", "rate_max", "bake_step_rad", "bake_interval",
  "bake_watch_radius", "bake_watch_hysteresis", "bake_cost_budget_ms",
  "bake_backoff_max", "bake_cost_ema_alpha",
  "dt_max", "deck_top_z", "dish_rise", "dish_radius",
  "pivot_z", "wall_inner_r", "load_radius", "ram_eye_r", "ram_eye_z",
  "ram_foot_r", "ram_foot_z", "aboard_below", "aboard_above",
  "under_deck_below", "corridor_cos", "corridor_sin", "corridor_half",
  "corridor_near", "corridor_far", "corridor_z_min", "corridor_z_max",
  "corridor_end_seconds", "mass_default_kg", "mass_min_kg", "mass_max_kg",
  "set_wins", "ko_radius", "stage_radius", "stage_speed", "stage_min_gap",
  "stage_hold_seconds", "countdown_go_seconds", "countdown_stop_seconds",
  "spin_omega_max", "spin_accel", "spin_decel", "spin_drag_accel",
  "spin_min_r", "spin_home_rate", "spin_home_eps", "drive_ratio",
  "call_takes", "back_takes", "call_stop_seconds", "call_gap_seconds",
  "breeze_mps", "breeze_heading_deg",
  "decided_hold_seconds", "match_max_seconds",
  "reset_dist", "reset_gap", "ramp_az_cos", "ramp_az_sin",
  "sb_pip_hide", "sb_result_shift", "sb_result_hide", "ring_hide_drop",
  "mass_prune_seconds", "stuck_seconds", "stuck_move_eps", "wreck_damage",
  "wreck_seconds", "open_hold_seconds", "arm_seconds", "arm_wait_max",
  "clear_debounce", "round_max_seconds", "relevel_hard_seconds",
  "relevel_bleed_ramp", "level_eps_rad", "rate_eps",
  "vent_seconds", "stats_interval",
}

local function tunablesPresent(state)
  local missing = {}
  for _, name in ipairs(REQUIRED) do
    if type(B[name]) ~= "number" then missing[#missing + 1] = name end
  end
  if #missing == 0 then return true end
  emitError(state, "handoff_tunables_missing", {keys = table.concat(missing, ",")})
  showMessage(
    "Gyro platform: shipped build is missing runtime constants. "
    .. "Re-run the Blender stage.", 8.0)
  return false
end

behavior.init = function(state)
  local b = state.behavior
  if not tunablesPresent(state) then
    b.phase = "fault"
    b.broken = true
    return
  end
  b.broken = false
  b.phase = "open"
  b.phaseT = 0
  b.psiX, b.psiY = 0, 0
  b.velX, b.velY = 0, 0
  b.comX, b.comY = 0, 0
  b.bakeClock = 0
  b.bakes = 0
  b.needBake = true
  b.riders, b.parked, b.corridor, b.queuing, b.trapped = 0, 0, 0, 0, 0
  b.watchers = 1
  b.torqueX, b.torqueY = 0, 0
  b.armT, b.armWait, b.roundT, b.clearT, b.relevelT, b.queueT = 0, 0, 0, 0, 0, 0
  b.boardT = 0
  b.ventT = 0
  b.statsT = 0
  b.mass = {}
  b.track = {}
  b.watch = {}
  b.fieldTrack = {}
  b.massPrune = 0
  -- Match state. Scores and corners are the board's memory; init is a cold
  -- boot, so they clear here (a warm behavior.reset keeps them).
  b.slotE, b.slotW = nil, nil
  b.scoreE, b.scoreW = 0, 0
  b.resultE, b.resultW = nil, nil
  b.setDone = nil
  b.omega = 0
  b.spinAngle = 0
  b.spinPrev = 0
  b.driveAngle = 0
  b.stageT = 0
  b.decidedT = 0
  b.cdStopT = nil
  -- Announcer: what is sounding, what is waiting, the gap between them, and
  -- which wire carried each clip (the pole, or the vehicle fallback).
  b.callStops = {}
  b.callQ = {}
  b.callGapT = 0
  b.callVia = {}
  b.hornOrigin, b.hornRot = nil, nil
  b.toastE, b.toastW = nil, nil
  b.ringLive, b.ringKo = false, false
  buildGeometry(state)
  -- The PA. Built here so every announcement from the first frame onward has
  -- somewhere to come from; state.origin is still nil at init, so the horns
  -- are aimed properly by the first Horn.place in behavior.update.
  Horn.create(state)
  Horn.stopAll(state)
  seedBreeze(state)
  poseAll(state, 0)
  pushNames(state, 0, true)
  requestCollisionReload(state)
end

-- A reset must NOT snap the deck. behavior.init drives the committed pose
-- straight to zero, which at the stops is 1.26 m of instantaneous static
-- collision travel at the rim with cars possibly aboard - the one committed
-- move in the machine that was not bounded to a bake step. Instead a reset
-- keeps psi and com exactly where they are, rebuilds the derived geometry,
-- and enters the re-level phase, so the deck walks home through the same
-- rate-limited, step-clamped path every other move uses.
behavior.reset = function(state)
  local b = state.behavior
  setEffectActive(state, "valve_vent", false)
  if b.broken then return end
  -- Every field poseAll touches has to be present, not just the pose itself:
  -- if a previous init threw part way (a nil handoff key is the classic, and
  -- registerProp pcalls init and discards the result) the table can be half
  -- built, and the safe answer then is a full init rather than a pose from
  -- half a state.
  if not (b.phase and finiteNumber(b.psiX) and finiteNumber(b.psiY)
    and finiteNumber(b.comX) and finiteNumber(b.comY)
    and finiteNumber(b.spinAngle) and finiteNumber(b.driveAngle)) then
    behavior.init(state)
    return
  end
  b.velX, b.velY = 0, 0
  b.riders, b.parked, b.corridor, b.queuing, b.trapped = 0, 0, 0, 0, 0
  b.watchers = 1
  b.torqueX, b.torqueY = 0, 0
  b.armT, b.armWait, b.roundT, b.clearT, b.queueT = 0, 0, 0, 0, 0
  b.boardT = 0
  b.ventT = 0
  b.mass = {}
  b.track = {}
  b.watch = {}
  b.fieldTrack = {}
  b.needBake = true
  -- A warm reset voids any match in flight but keeps the board: corners and
  -- scores survive a prop reset; only the reset button wipes them.
  b.omega = 0
  b.stageT = 0
  b.decidedT = 0
  b.cdStopT = nil
  b.toastE, b.toastW = nil, nil
  b.ringLive, b.ringKo = false, false
  hushCall(state, "countdown")
  silenceCalls(state)
  buildGeometry(state)
  pushNames(state, 0, true)
  setPhase(state, "relevel")
  b.relevelT = 0
  poseAll(state, 0)
  requestCollisionReload(state)
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if zone == "ramp_zone" then
    if b.phase == "live" then
      showMessage("Ring is live. The threshold is shut - wait for green.", 2.4)
    elseif b.phase == "open" or b.phase == "arming" then
      showMessage("Boarding lane clear. Drive on.", 2.0)
    end
    return
  end
  if zone ~= "arena_zone" then return end
  if b.phase == "live" then
    showMessage("RING IS LIVE - the deck is loose and it leans at you.", 2.6)
  elseif b.phase == "relevel" then
    showMessage("Deck is still re-levelling. Wait for green.", 2.4)
  end
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  local b = state.behavior
  if b.mass then b.mass[vehicleId] = nil end
  if b.track then b.track[vehicleId] = nil end
  if b.watch then b.watch[vehicleId] = nil end
  if b.fieldTrack then b.fieldTrack[vehicleId] = nil end
  -- A competitor who despawns mid-match forfeits; outside a match their
  -- corner simply opens up for the next challenger.
  if b.slotE and b.slotE.id == vehicleId then
    if b.phase == "live" or b.phase == "countdown" then
      decideMatch(state, "east", "forfeit")
    end
    -- Name AND last holder stay on the board: the seat opens, but the
    -- corner still remembers whose it was, so the same car coming back is
    -- not mistaken for a new rival.
    b.slotE.lastId = vehicleId
    b.slotE.id = nil
  elseif b.slotW and b.slotW.id == vehicleId then
    if b.phase == "live" or b.phase == "countdown" then
      decideMatch(state, "west", "forfeit")
    end
    b.slotW.lastId = vehicleId
    b.slotW.id = nil
  end
end

-- The board's one control, mirrored on both faces: RESET wipes corners,
-- scores and result plates. Everything else about the game is played, not
-- pressed.
behavior.onPanelButton = function(state, buttonId)
  local b = state.behavior
  if buttonId ~= "btn_reset" and buttonId ~= "btn_reset_ring" then return end
  b.slotE, b.slotW = nil, nil
  b.scoreE, b.scoreW = 0, 0
  b.resultE, b.resultW = nil, nil
  b.setDone = nil
  b.ringLive, b.ringKo = false, false
  -- The announcer clears on EVERY press, not only from a live phase: the
  -- button has just wiped the corners the pending calls were about, and a
  -- queued welcome for a corner that no longer exists would otherwise be
  -- announced into the next match. Any pending corner toast goes with it.
  b.toastE, b.toastW = nil, nil
  silenceCalls(state)
  if b.phase == "live" or b.phase == "decided" or b.phase == "countdown" then
    b.omega = 0
    b.cdStopT = nil
    hushCall(state, "countdown")
    b.relevelT = 0
    setPhase(state, "relevel")
  end
  showMessage("Scoreboard cleared - corners open.", 2.6)
  emitEvent(state, "I", "sumo_reset", {})
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  if not b.phase then behavior.init(state) end
  -- A build that failed its tunable check holds every part at its authored
  -- rest pose and does nothing else; the error has already been emitted once.
  if b.broken then return end
  local dt = dtSim or 0
  if dt <= 0 then return end
  if dt > B.dt_max then dt = B.dt_max end
  b.phaseT = (b.phaseT or 0) + dt
  -- Frame stamp for the announcer queue's ordering. Phase-independent (it
  -- must survive a setPhase mid-frame) and it only ever has to distinguish
  -- "this frame" from "an earlier one", so a plain counter is exact.
  b.frameN = (b.frameN or 0) + 1

  -- Frame-cost sampler for the adaptive bake backoff. The reload fires in
  -- the framework's frame tail, AFTER this update returns, so the frame that
  -- requested a bake pays for it inside the wall-time delta that closes at
  -- the NEXT update: bakePending (set by bakeNow during the last update) is
  -- consumed here to attribute the just-closed delta. Two EMAs - bake frames
  -- and clean frames - and their difference is the rebuild's measured cost
  -- on this hardware. Deltas over 250 ms are discarded (pause, alt-tab, a
  -- load hitch), so a stall cannot poison the estimate.
  if clockMs then
    local now = clockMs()
    if b.frameT0 then
      local ms = now - b.frameT0
      if ms >= 0 and ms < 250 then
        local alpha = B.bake_cost_ema_alpha
        if b.bakePending then
          b.bakeFrameMs = b.bakeFrameMs
            and (b.bakeFrameMs + alpha * (ms - b.bakeFrameMs)) or ms
        else
          b.cleanFrameMs = b.cleanFrameMs
            and (b.cleanFrameMs + alpha * (ms - b.cleanFrameMs)) or ms
        end
        if b.bakeFrameMs and b.cleanFrameMs then
          local cost = b.bakeFrameMs - b.cleanFrameMs
          b.bakeMs = (cost > 0) and cost or 0
        end
      end
    end
    b.frameT0 = now
    b.bakePending = false
  end

  sweepDeck(state, dt)
  pruneCaches(state, dt)

  -- Countdown audio stop clock, phase-independent: GO moves the phase to
  -- live at 1.65 s but the source keeps playing until 2.60 s, inside the
  -- ogg's silent pad, so the loop profile can never wrap audibly.
  if b.cdStopT then
    b.cdStopT = b.cdStopT - dt
    if b.cdStopT <= 0 then
      b.cdStopT = nil
      hushCall(state, "countdown")
    end
  end
  -- The announcer. One stop clock PER CLIP still (call_stop_seconds is past
  -- the end of the longest take and still inside the shortest clip's silent
  -- pad, so no take can wrap), and on top of that the serialiser: the next
  -- queued call only starts once the air is clear and the gap has elapsed.
  pumpCalls(state, dt)
  -- Keep the cluster on the pole. The framework's transform sweep skips
  -- anything it has no EFFECT_SPECS row for, so the horns re-pose themselves;
  -- this is a four-float comparison on the frames where nothing moved.
  Horn.place(state, false)
  flushCornerToast(state)

  if b.phase == "open" then
    updateOpen(state, dt)
  elseif b.phase == "countdown" then
    updateCountdown(state, dt)
  elseif b.phase == "live" then
    updateLive(state, dt)
  elseif b.phase == "decided" then
    updateDecided(state, dt)
  elseif b.phase == "relevel" then
    updateRelevel(state, dt)
  else
    -- Unknown phase can only come from a corrupted table; fail level.
    setPhase(state, "relevel")
    b.relevelT = 0
  end

  -- decided integrates too: torque only feeds the model in "live", so after
  -- the KO the rams spring the deck back while the spin bleeds off.
  if b.phase == "live" or b.phase == "decided" then
    integrate(state, dt)
  elseif b.phase == "relevel" then
    if b.relevelT > B.relevel_hard_seconds then
      bleedToLevel(state, dt)
    else
      integrate(state, dt)
    end
  end

  local locked = (b.phase == "open" or b.phase == "countdown")
  local settled = locked and (b.comX ~= 0 or b.comY ~= 0)
  commitPose(state, dt, settled)
  poseAll(state, dt)

  if b.ventT > 0 then
    b.ventT = b.ventT - dt
    if b.ventT <= 0 then setEffectActive(state, "valve_vent", false) end
  end

  b.statsT = b.statsT + dt
  if b.statsT >= B.stats_interval then
    b.statsT = 0
    local tilt = math.sqrt(b.psiX * b.psiX + b.psiY * b.psiY)
    b.stats = {
      phase = b.phase,
      riders = b.riders,
      parked = b.parked,
      corridor = b.corridor,
      queuing = b.queuing,
      trapped = b.trapped,
      tilt_deg = tilt * 180 / math.pi,
      committed_deg = math.sqrt(b.comX * b.comX + b.comY * b.comY) * 180 / math.pi,
      rate_deg_s = math.sqrt(b.velX * b.velX + b.velY * b.velY) * 180 / math.pi,
      bakes = b.bakes,
      bake_ms = b.bakeMs,
      interval_eff = effInterval(b),
      round_seconds = b.roundT,
    }
  end
end
"""

# ---------------------------------------------------------------------------
# Horn splice. The cluster's mouth coordinates, its cue table and the emitter
# tuning go into the runtime as LITERALS rather than as behaviour tunables:
# none of it is dialled at play time, and a literal can never be the missing
# handoff key that trips tunablesPresent and breaks the whole prop (the b104
# derived-lua trap this mod has already paid for once).
LUA_BEHAVIOR = LUA_BEHAVIOR.replace(
    "--@HORN_SPECS@--", _horn_specs_lua()
).replace("--@HORN_CUES@--", _horn_cues_lua())
for _token, _value in (
    ("@MOD_ID@", MOD_ID),
    ("@HORN_CONE_IN@", HORN_CONE_IN_DEG),
    ("@HORN_CONE_OUT@", HORN_CONE_OUT_DEG),
    ("@HORN_CONE_OUT_VOL@", HORN_CONE_OUT_VOL),
    ("@HORN_REF@", HORN_REF_M),
    ("@HORN_MAX@", HORN_MAX_M),
):
    LUA_BEHAVIOR = LUA_BEHAVIOR.replace(_token, str(_value))
del _token, _value
assert "@HORN_" not in LUA_BEHAVIOR and "@MOD_ID@" not in LUA_BEHAVIOR, (
    "horn splice left a placeholder in the runtime")
assert LUA_BEHAVIOR.count('slot = "h') == len(HORN_MOUTHS) == 4
for _cue in HORN_CUES:
    assert f'name = "{_cue}"' in LUA_BEHAVIOR, f"horn cue {_cue} did not splice"
del _cue
# Every cue must have a file on disk, and every file must be a cue: a cue with
# no ogg makes an emitter the engine silently never plays, and an ogg no cue
# names is a build input reaching a player's disk for nothing.
_SOUND_DIR = pathlib.Path(__file__).resolve().parent / "mod" / "vehicles" / MOD_ID / "sound"
if _SOUND_DIR.is_dir():
    _on_disk = {p.stem[len(MOD_ID) + 1:] for p in _SOUND_DIR.glob(f"{MOD_ID}_*.ogg")}
    assert _on_disk == set(HORN_CUES), (
        "sound folder and horn cue list disagree: "
        f"only on disk {sorted(_on_disk - set(HORN_CUES))}, "
        f"only in cues {sorted(set(HORN_CUES) - _on_disk)}"
    )
    del _on_disk
