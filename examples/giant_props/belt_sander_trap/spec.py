"""The Belt Sander Conveyor Trap - authored constants for Blender + runtime.

A 26 m industrial belt sander scaled until a car is the workpiece. An
abrasive belt runs over a tail (idler) drum and a head (drive) drum with a
flat platen between them. The player drives up a 15% loading ramp onto the
running belt; the belt drags the car toward the head drum while the car
tries to claw its way back out. At the head the car goes over a kicker lip
and gets thrown. A dust-extraction hood, a cyclone, machine guarding, a
service walkway and an operator console with real belt-speed controls make
up the rest of the machine.

DESIGN SPINE - one number, b.speed
==================================
Everything the player can see or feel is a pure function of ONE runtime
variable: ``b.speed``, the live belt surface speed in m/s.

  * the tangential drag applied to cars on the belt,
  * the travel of the 24 splice bars around the belt loop (they are real
    kinematic parts that traverse the whole loop; nothing is faked with a
    static texture),
  * the rotation of both drums (omega = speed / belt_wrap_r),
  * the lift of the two take-up tension rockers on the tail gantry,
  * the console gauge needle angle,
  * the printed toast readout.

Because they all read the same variable there is no way for the readout to
disagree with the physics.

TIME BASE - wall seconds, measured, not assumed
===============================================
``b.speed`` is only truthful if the seconds it is integrated against are
real seconds. AGENTS.md records that ``dtSim`` handed to a prop's
``behavior.update`` measured ~3x faster than wall clock; a later live pass
on the centrifuge concluded that measurement was a stepped-rig artifact and
that live timers run about 1:1. BOTH cannot be assumed, and clamping dt
does not repair a SCALE error. So this prop refuses to guess: it exports a
``behavior.hooks.onUpdate`` GE hook (proplib copies behaviour hooks onto the
extension module table), accumulates the engine's own ``dtReal``, and
differences that accumulator inside ``behavior.update``. Every integration
in this machine - belt speed, belt travel, drum angle, injected drag,
timers - runs on those wall seconds, and the runtime emits the measured
``dtSim per wall second`` ratio once as telemetry so the number stops being
folklore. If the hook never fires the prop degrades to dtSim exactly as
before, and says so in the same event.

GEOMETRY FRAME
==============
Right-handed, meters, Z-up, +Y is the drive direction. The car enters at
-Y (up the loading ramp), the belt carries +Y, the kicker is at +Y. The
world renders authored (x, y) at (-x, -y); that flip is a proper rotation
so every relative direction in this file survives it.

CAR REFERENCE (every clearance below is derived from these)
  width 2.0 m, length 4.5 m, height 1.5 m.
"""

import math

MOD_ID = "ericrolph_belt_sander_trap"
DISPLAY_NAME = "The Belt Sander Conveyor Trap"
VALUE_DOLLARS = 52000
ZIP_BASENAME = "belt_sander_trap_ericrolph.zip"

CAR_WIDTH = 2.0
CAR_LENGTH = 4.5
CAR_HEIGHT = 1.5

# ---------------------------------------------------------------------------
# The belt and its drums
# ---------------------------------------------------------------------------
# 6.0 m of belt = one car width plus 2.0 m of clear belt each side. A car
# being dragged sideways by an abrasive belt wanders; 2 m is a full car
# width of run-off before it reaches the deflector.
BELT_HALF_WIDTH = 3.0
# 1.4 m drums - conveyor proportions rather than bench-sander proportions.
# Two hard constraints set this, and they pull against each other:
#   * the RETURN run (drum axis - wrap radius) must clear grade with real
#     daylight under it, or the belt loop is buried;
#   * BELT_Z sets how far the loading ramp has to climb, and the ramp is
#     the longest single piece of the prop.
# axis 1.05, wrap radius 0.80 -> return run at z 0.25 (0.25 m of daylight),
# drum underside at 0.35, and BELT_Z lands back on 1.85 so the ramp stays
# 14.5 m at 15%.
DRUM_R = 0.70
BELT_THICK = 0.10
# Radius of the belt's OUTER (working) face - the surface cars ride on and
# the path the splice bars travel.
BELT_WRAP_R = DRUM_R + BELT_THICK
DRUM_AXIS_Z = 1.05
# THE drivable plane. Everything about the lane profile is anchored here.
BELT_Z = DRUM_AXIS_Z + BELT_WRAP_R
RETURN_RUN_Z = DRUM_AXIS_Z - BELT_WRAP_R
# Drum centres 21 m apart. The escape run (tangent to tangent) is therefore
# 21 m: long enough that a 6 m/s belt is a real fight and a 21 m/s belt is
# hopeless (a car braking at ~9 m/s^2 against 9 m/s^2 of belt drag needs
# 25^2/(2*0.5) m to stop - far more than the machine is long).
IDLER_Y = -10.5
DRIVE_Y = 10.5
TOP_RUN = DRIVE_Y - IDLER_Y
# Two straight runs plus two half-wraps.
LOOP_LENGTH = 2.0 * TOP_RUN + 2.0 * math.pi * BELT_WRAP_R
# 24 vulcanised segment joins: pitch ~1.96 m, so ~11 bars are on the
# carrying run at any instant. 16 (pitch 2.94) left only ~7 in view and the
# scroll read as "spots drifting past" from the driver's seat; 24 reads as a
# moving SURFACE, which is the whole point of the machine. Each bar costs
# one TSStatic and one small DAE, so this is the honest lever - the belt is
# not a scrolling texture and cannot be densified for free.
BAR_COUNT = 24
BAR_PITCH = LOOP_LENGTH / BAR_COUNT
# The bars stand 3 mm off the belt face. The AGENTS.md relief cap for
# anything a car drives over is +/-0.02 m, and the bars carry no collision
# at all (the cage is a flat plate at BELT_Z), so they can never be a step.
# 3 mm (was 6) also buys clearance under the transfer nose plates, whose
# tips were thinned to halve the one relief defect on the lane - see
# LIP_TIP_CLEAR. They read by CONTRAST (hazard chevron on dark grit).
BAR_PROUD = 0.003
BAR_LENGTH_Y = 0.45
BAR_HALF_WIDTH = 2.85  # inboard of the belt edge so they clear the skirts

# ---------------------------------------------------------------------------
# The lane: one continuous drivable surface, ramp foot to outfeed toe
# ---------------------------------------------------------------------------
# The machine's structural ends: 0.25 m clear of each drum's outer face, so
# the solid end housings can never intersect a drum.
MACHINE_TAIL_Y = IDLER_Y - DRUM_R - 0.25
MACHINE_HEAD_Y = DRIVE_Y + DRUM_R + 0.25
# TRANSFER NOSE PLATES. The lane deck is a dead-flat BELT_Z plane from the
# ramp crest all the way to the kicker toe - ONE surface, no steps. Between
# the machine's solid end housing and the point where the belt has climbed
# to within a few mm of that plane, a tapered steel nose plate bridges the
# drum, exactly like a conveyor's feed skirt. Its underside is cut to the
# belt's own wrap curve plus LIP_TIP_CLEAR, so it can never foul the belt
# or the 6 mm splice bars; it stops where it has thinned to LIP_TIP_THICK.
# The only place the drivable COLLISION plane and the visible surface
# disagree anywhere on this machine is the ~0.13 m band between that tip
# and the drum tangent, and there by at most LIP_TIP_CLEAR + LIP_TIP_THICK
# = 0.010 m - HALF the AGENTS.md relief cap. (Asserted at build time.)
# An independent cull-aware raycast of the shipped mesh measured the old
# 0.014/0.006 pair at 0.0205 m, i.e. marginally OVER the cap, twice per
# traverse; these values were halved in response and the build assert was
# tightened from 0.0201 to 0.0101 so the defect cannot come back. The
# clearance still has to exceed BAR_PROUD (3 mm) or a passing splice bar
# would foul the plate - 7 mm leaves 4 mm. Analytically the band is 10.0 mm;
# the belt's faceted wrap adds a little chord sag on top, and the built mesh
# measures 10.3 mm (467 stations x 5 wheel tracks, 5 mm sampling across both
# tangent bands, zero misses anywhere on the lane).
LIP_TIP_CLEAR = 0.007
LIP_TIP_THICK = 0.003
LIP_ROOT_DROP = 0.16
RAMP_CREST_Y = MACHINE_TAIL_Y - 2.0
# Loading ramp. Grade is DERIVED from the climb so the crest lands exactly
# on the apron height - never retyped (AGENTS.md: cage constants derived
# half from spec and half from literals will drift).
RAMP_RUN = 14.5
RAMP_BLEND = 2.2  # slope-blend length at the toe and at the crest
RAMP_FOOT_Y = RAMP_CREST_Y - RAMP_RUN
# Integrating a trapezoidal GRADE profile (0 -> g over RAMP_BLEND, g, then
# g -> 0 over RAMP_BLEND) gives climb = g * (run - blend). Solving for g
# guarantees the peak grade is exactly this number anywhere on the ramp -
# the centrifuge round-14 law (never blend two HEIGHT datums; blend the
# SLOPE and integrate, or the blend out-dives both ends and stalls a car at
# creep throttle).
RAMP_GRADE = BELT_Z / (RAMP_RUN - RAMP_BLEND)

# Kicker: 18% up-ramp off the discharge apron ending in a sharp CONVEX
# break. Convex breaks unload a car (safe); the dangerous ones are concave,
# so the kicker's own toe gets a 1.5 m slope blend and the outfeed's toe
# gets a 2.5 m one.
KICK_START_Y = MACHINE_HEAD_Y + 0.4
KICK_BLEND = 1.5
KICK_GRADE = 0.18
KICK_LIP_Y = 16.0
KICK_RISE = KICK_GRADE * KICK_BLEND / 2.0 + KICK_GRADE * (
    KICK_LIP_Y - KICK_START_Y - KICK_BLEND
)
KICK_LIP_Z = BELT_Z + KICK_RISE
# Outfeed embankment: the landing surface. Descending grades are far more
# forgiving than climbing ones, so 20% is fine; the run is DERIVED so the
# toe lands exactly on grade.
OUT_GRADE = 0.20
OUT_BLEND = 2.5
OUT_RUN = KICK_LIP_Z / OUT_GRADE + OUT_BLEND / 2.0
OUTFEED_END_Y = KICK_LIP_Y + OUT_RUN

# Grade profile of the lane from the ramp foot to the kicker lip: a
# piecewise-LINEAR grade that is INTEGRATED into the deck height. Between
# any two breakpoints the grade is monotone, so it can never exceed either
# end value.
LANE_GRADE_PROFILE = (
    (RAMP_FOOT_Y, 0.0),
    (RAMP_FOOT_Y + RAMP_BLEND, RAMP_GRADE),
    (RAMP_CREST_Y - RAMP_BLEND, RAMP_GRADE),
    # Dead flat at BELT_Z from the ramp crest to the kicker toe: the whole
    # machine bed - feed apron, nose plate, belt, discharge - is one plane.
    (RAMP_CREST_Y, 0.0),
    (KICK_START_Y, 0.0),
    (KICK_START_Y + KICK_BLEND, KICK_GRADE),
    (KICK_LIP_Y, KICK_GRADE),
)
OUTFEED_GRADE_PROFILE = (
    (KICK_LIP_Y, -OUT_GRADE),
    (OUTFEED_END_Y - OUT_BLEND, -OUT_GRADE),
    (OUTFEED_END_Y, 0.0),
)


def _integrate(profile, y_start, y):
    """Trapezoidal integral of a piecewise-linear grade table."""

    total = 0.0
    for (y0, g0), (y1, g1) in zip(profile, profile[1:]):
        if y <= y0:
            break
        span_end = min(y, y1)
        if span_end <= y0:
            continue
        # Grade at span_end by linear interpolation inside this segment.
        t = (span_end - y0) / (y1 - y0)
        g_end = g0 + (g1 - g0) * t
        total += 0.5 * (g0 + g_end) * (span_end - y0)
    del y_start
    return total


def deck_z(y):
    """Height of the drivable lane surface at authored y.

    The single authority for BOTH the visual lane solids and the physics
    cage; nothing in this mod ever retypes a deck height.
    """

    if y <= RAMP_FOOT_Y:
        return 0.0
    if y <= KICK_LIP_Y:
        return _integrate(LANE_GRADE_PROFILE, RAMP_FOOT_Y, y)
    if y >= OUTFEED_END_Y:
        return 0.0
    return KICK_LIP_Z + _integrate(OUTFEED_GRADE_PROFILE, KICK_LIP_Y, y)


# Underside of the lane solids. min(0, deck - 0.25) makes every ramp an
# EMBANKMENT carried to grade instead of a floating plank with a car-sized
# hole under it (centrifuge lesson, 2026-08-08). The cage's own foundation
# row stays at z = 0 so the prop's spawn datum is the map surface.
LANE_UNDERCUT = 0.25


def lane_bottom_z(y):
    return min(0.0, deck_z(y) - LANE_UNDERCUT)


# ---------------------------------------------------------------------------
# Lane cross-section (shared by the visual loft AND the cage)
# ---------------------------------------------------------------------------
# Outboard of the belt edge: a 34% DEFLECTOR up to the service walkway,
# then 1.0 m of walkway grating, then a 1.1 m perforated guard panel. A car
# shoved sideways meets a slope first (slopes deflect, vertical faces in a
# lane pop tires), and only reaches the guard after climbing 0.55 m.
DEFLECTOR_X = 4.6
WALKWAY_X = 5.6
GUARD_PANEL_T = 0.10
GUARD_H = 1.10
# The guard panel is RAKED 20 degrees outboard instead of standing plumb.
# It is the only surface on the machine a car could reach that is not a
# floor or a slope, and although it sits behind a 34% deflector and a 1.0 m
# walkway - so nothing on the lane can touch it - a plumb 1.10 m panel is
# still a wall. Raked, anything that does climb up there is deflected over
# the side rather than stopped dead. 20 deg puts the guard's top edge at
# |x| 6.0: clear of the hood/gantry leg line (6.32 inner face) and clear of
# the belt drive enclosure (its inboard wall is at |x| 5.8, and the panel
# is only outboard of 5.8 above z 3.15, well over the 2.6 m enclosure).
GUARD_RAKE_DEG = 20.0
GUARD_RAKE = GUARD_H * math.tan(math.radians(GUARD_RAKE_DEG))


def guard_face_x(height_above_walk):
    """Outboard x of the raked guard panel's outer face, as a magnitude.

    Read by BOTH the visual guard bands and the cage's guard column, so the
    rake cannot exist in one and not the other.
    """

    t = 0.0 if GUARD_H <= 0.0 else max(0.0, min(1.0, height_above_walk / GUARD_H))
    return WALKWAY_X + GUARD_RAKE * t


# ---------------------------------------------------------------------------
# Drum inspection windows
# ---------------------------------------------------------------------------
# The head and tail drum stations are the signature parts of a belt sander
# and the first build buried both of them: the machine's outer skin ran
# unbroken from the ramp foot to the outfeed toe, so from OUTSIDE you saw a
# grey box and from the lane you saw a green fence. A real conveyor drum
# station is open - you have to be able to see the lagging, the bearing and
# the take-up. So the side frame's OUTER SKIN and its inner face are cut
# away for 3.6 m centred on each drum axis, exposing the drum shell, the
# flanges, the pillow blocks, the take-up screws and (at the head) the
# flywheel. The cage drops the matching collision skin over exactly the
# same spans, so the opening is real and not a hole in front of an
# invisible wall. Everything a car drives on - deck, deflector, walkway -
# is untouched; only the outboard skin below the walkway is opened.
DRUM_WINDOW_HALF = 2.5


def in_drum_window(y):
    """True where the side frame's outer skin is cut away for a drum."""

    return (
        abs(y - IDLER_Y) <= DRUM_WINDOW_HALF
        or abs(y - DRIVE_Y) <= DRUM_WINDOW_HALF
    )
# The deflector/walkway height above the deck. Tapered to a 0.12 m lip at
# the very ends of the lane so the ramp toe and the outfeed toe are flush
# kerbs, not a 0.55 m wall a car can nose into. 0.12 (not 0) keeps the
# walkway node clear of the foundation node - two cage nodes closer than
# 1 cm are the flexbody coincident-triad trap.
SKIRT_RISE = 0.55
SKIRT_END_RISE = 0.12
SKIRT_TAPER = 3.5


def skirt_rise(y):
    lead = min(y - RAMP_FOOT_Y, OUTFEED_END_Y - y)
    if lead >= SKIRT_TAPER:
        return SKIRT_RISE
    t = max(0.0, lead) / SKIRT_TAPER
    return SKIRT_END_RISE + (SKIRT_RISE - SKIRT_END_RISE) * t


# Cage columns across the lane: five on the deck (1.5 m apart - a car's
# track never spans more than one cell), the deflector top, the walkway
# outer edge, the guard top and the foundation.
DECK_COLUMNS = (-3.0, -1.5, 0.0, 1.5, 3.0)

# ---------------------------------------------------------------------------
# Dust extraction hood
# ---------------------------------------------------------------------------
# Underside 3.6 m over the belt: a 1.5 m car has 2.1 m of clear air, and a
# car standing on its roof still passes. The hood stops at y 13.0, upstream
# of the kicker lip, so a launched car flies out from under it.
HOOD_CLEAR = 3.6
HOOD_UNDER_Z = BELT_Z + HOOD_CLEAR
HOOD_TOP_Z = HOOD_UNDER_Z + 1.7
HOOD_Y0 = 6.0
HOOD_Y1 = 13.0
HOOD_HALF_X = 3.6
# Hood legs stand OUTBOARD of the guard line (WALKWAY_X = 5.6), so nothing
# is planted on the walkway or in the deflection path.
HOOD_LEG_X = 6.6
# Extraction cyclone. It stands on a fabricated equipment CABINET whose
# box is exactly the cage lattice under it - the cyclone barrel/cone/stack
# above 3.0 m are visual only, and nothing a car can reach is a ghost.
CYCLONE_X = 9.0
# Parked at the hood's INLET end, not its midpoint. At the midpoint (9.5)
# the cabinet stood squarely across the head drum's inspection window and
# hid the one drum station a player can walk up to - cutting a window and
# then parking the extraction plant in front of it is worse than not
# cutting it. 7.0 puts the whole 2.6 m cabinet clear of the window's 8.7 m
# leading edge; the duct follows the cyclone, so nothing is disconnected.
CYCLONE_Y = HOOD_Y0 + 1.0
CYCLONE_R = 1.5
CYCLONE_CAB = (2.6, 2.6, 3.0)
CYCLONE_TOP_Z = 9.2
# Belt drive: one sheet-metal enclosure on the -X flank (extraction lives
# on +X, so the two service packages never share space). Its box IS its
# collision lattice. Set BEHIND the head drum rather than beside it, for
# the same reason the cyclone moved: sitting at DRIVE_Y - 0.8 it covered
# the head drum's inspection window end to end. From y 11.3 back it clears
# the window and a V-belt guard bridges the 0.8 m to the drum shaft, which
# is how the drive on a real machine of this size is arranged anyway.
DRIVE_ENC_CENTER = (-(WALKWAY_X + 1.4), DRIVE_Y + 2.6, 1.3)
DRIVE_ENC_SIZE = (2.4, 3.6, 2.6)
# The V-belt guard: outboard of the frame skin, spanning drum shaft to
# enclosure at shaft height, so the drive is a visible mechanical run
# instead of a box that happens to sit near a drum.
DRIVE_GUARD_X = -(WALKWAY_X + 0.7)

# ---------------------------------------------------------------------------
# Tail end frame: the gantry, the nameplate and the take-up tension rockers
# ---------------------------------------------------------------------------
# The driver spends the whole 14.5 m ramp climb looking at ONE thing: the
# far end of the lane. The first build put nothing there, so the machine
# read as "a conveyor in a shed" from the only viewpoint that matters. The
# tail end frame fixes that: a portal over the feed end carrying the
# machine's nameplate, with the belt take-up rockers hung off its legs.
# Everything here is either collidable structure or mounted on it.
GANTRY_Y = MACHINE_TAIL_Y - 1.0
# Same column line as the hood legs: one machine, one leg line.
GANTRY_LEG_X = HOOD_LEG_X
GANTRY_LEG_HALF = 0.28
GANTRY_TOP_Z = 7.60
# Header box bottom. Must clear HOOD_UNDER_Z (the machine's own declared
# overhead datum) so the tail portal never becomes the lowest ceiling on
# the lane - asserted at build time. 5.60 leaves 3.75 m over the deck, more
# than the hood's own curtains (3.375 m).
GANTRY_HEADER_Z0 = 5.60
# Header half-depth. 0.40 (not 0.28, the leg half-width) so the header's
# cage lattice corners stand 0.12 m clear of the leg lattice corners - two
# cage nodes closer than 1 cm are the flexbody coincident-triad trap, and
# the build asserts it.
GANTRY_HEADER_HALF_Y = 0.40
SIGN_HALF_X = 4.8
SIGN_HALF_Z = 0.75
SIGN_Z = (GANTRY_HEADER_Z0 + GANTRY_TOP_Z) / 2.0
# Take-up tension rockers. A belt sander without visible belt tensioning is
# just a conveyor; the brief asks for a tension arm and the take-up screws
# alone (0.09 m rods buried inside the frame) were not one. These are
# fore-aft rockers on the gantry legs: a counterweight aft, a spring
# canister forward standing in a guide cup, pivoting about +X. Hung on the
# OUTBOARD face of each leg (|x| 7.05): on the machine face the leg itself
# hid them from every viewpoint outside the guarding, and out here they are
# silhouetted against the sky from the ramp and completely open from the
# flank. Well clear of the guard panel's top edge at |x| 6.0.
TENSION_X = GANTRY_LEG_X + 0.45
TENSION_PIVOT_Z = 4.30
TENSION_ARM_HALF = 1.50
# 8 deg of lift from stopped to 28 m/s moves the rocker tip 0.21 m, which
# is legible at 20 m. Belt tension really does climb with speed, so the
# rocker is driven by the same b.speed as everything else, not by a clock.
TENSION_SWEEP_DEG = 8.0

# ---------------------------------------------------------------------------
# Operator console
# ---------------------------------------------------------------------------
# ON THE APPROACH APRON, 2.8 m short of the ramp toe and 5.2 m off the
# centreline, facing -Y. First placement put it alongside the ramp at
# y -17 - which put it on the far side of the machine's guard fence, so a
# player who parked on the ramp had to walk the whole guard run to reach
# it. Out here you drive past it on your right, stop, set the speed, and
# then drive up; the belt arms itself either way.
CONSOLE_X = 5.2
CONSOLE_Y = RAMP_FOOT_Y - 2.8
CONSOLE_TOP_Z = 1.80
# Legend plate frame. Label (u, v) live in this plate's own 0..1 face UV
# frame (v measured UP from the plate bottom), computed from the same
# button table that places the caps, so print and caps cannot drift.
PLATE_X0 = CONSOLE_X - 0.95
PLATE_W = 1.90
PLATE_Z0 = 0.60
PLATE_H = 1.10
# Buttons: caps sit 60 mm proud of the legend skin; the cage's console box
# front face is pulled 8 cm BEHIND the plate so no collision plane stands
# in front of the click boxes and swallows the mouse ray (round-15 lesson).
BUTTON_Y = CONSOLE_Y - 0.76
PANEL_BUTTONS = (
    {"id": "btn_run", "title": "Belt Sander: RUN",
     "position": (CONSOLE_X - 0.62, BUTTON_Y, 1.32), "cap": "green",
     "radius": 0.085, "label": "RUN", "label_z": 1.13},
    {"id": "btn_stop", "title": "Belt Sander: STOP (lock out)",
     "position": (CONSOLE_X, BUTTON_Y, 1.32), "cap": "red",
     "radius": 0.115, "label": "STOP", "label_z": 1.13},
    {"id": "btn_eject", "title": "Belt Sander: EJECT (clear the belt)",
     "position": (CONSOLE_X + 0.62, BUTTON_Y, 1.32), "cap": "amber",
     "radius": 0.100, "label": "EJECT", "label_z": 1.13},
    {"id": "btn_slower", "title": "Belt Speed: slower",
     "position": (CONSOLE_X - 0.55, BUTTON_Y, 0.88), "cap": "white",
     "radius": 0.070, "label": "SPEED -", "label_z": 0.73},
    {"id": "btn_faster", "title": "Belt Speed: faster",
     "position": (CONSOLE_X + 0.55, BUTTON_Y, 0.88), "cap": "white",
     "radius": 0.070, "label": "SPEED +", "label_z": 0.73},
)
# Default frame pair. Every button also carries its OWN frame nodes (the
# triggers2 basis is idX-idRef / idY-idRef, so a shared pair skews and
# translates the hitbox of every button not co-located with it); these two
# only exist because the builder validates them. Kept 1.30 m out so they
# cannot land within a centimetre of a per-button frame node.
PANEL_FRAME_X = (CONSOLE_X + 1.30, CONSOLE_Y - 0.85, 1.32)
PANEL_FRAME_Y = (CONSOLE_X - 1.30, CONSOLE_Y - 0.85, 1.32)

# Belt-speed gauge on the console binnacle. Dial faces -Y; the needle
# rotates about +Y so the tip sweeps toward +X, which is the operator's
# RIGHT when facing +Y - a conventional clockwise gauge.
DIAL_X = CONSOLE_X
# 4 cm PROUD of the binnacle's front face (which sits at CONSOLE_Y - 0.66):
# the first build had the dial 6 cm inside the binnacle box, so the render
# showed a bare hood with a needle and no scale at all.
DIAL_Y = CONSOLE_Y - 0.70
DIAL_Z = 2.32
DIAL_HALF = 0.55
NEEDLE_SPAN_DEG = 125.0
# Tip stops inside the printed tick ring (labels sit at 0.355 of the dial
# half-width; 0.34/1.10 = 0.309) - at 0.42 the needle covered the "0".
NEEDLE_LENGTH = 0.34

# The operator-selectable belt speed ladder, m/s of belt surface speed.
# Every rung is a real machine setting and the drag it produces is
# BELT_DRAG_PER_MPS * v (see BEHAVIOR below):
#   3 m/s  -> 0.13 g   any car walks out
#   6 m/s  -> 0.26 g   most cars walk out
#  10 m/s  -> 0.43 g   a strong car crawls out; the fun rung
#  15 m/s  -> 0.64 g   only real power holds station
#  21 m/s  -> 0.90 g   at the tyre limit: nothing escapes
#  28 m/s  -> capped   hopeless, and the throw off the kicker is violent
SPEED_STEPS = (3.0, 6.0, 10.0, 15.0, 21.0, 28.0)
SPEED_MAX = SPEED_STEPS[-1]
DEFAULT_STEP = 3  # 10 m/s - the rung that is actually a contest

PALETTE = {
    # Abrasive belt: brown aluminium-oxide grit. asphalt's aggregate noise
    # is the closest family to a coated abrasive.
    f"{MOD_ID}_belt_grit": {
        "texture": {"family": "asphalt", "params": {"base": [0.28, 0.18, 0.11]}},
        "color": [0.30, 0.20, 0.13, 1.0],
        "metallic": 0.0,
        "roughness": 0.97,
    },
    # Travelling splice bars: the motion cue. Chevron contrast, not relief.
    f"{MOD_ID}_belt_splice": {
        "texture": {"family": "hazard_chevron"},
        "color": [0.95, 0.72, 0.06, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
    },
    f"{MOD_ID}_frame_steel": {
        "texture": {"family": "steel_worn", "params": {"base": [0.42, 0.45, 0.50]}},
        "color": [0.42, 0.45, 0.50, 1.0],
        "metallic": 0.85,
        "roughness": 0.42,
    },
    # Ramp / apron / walkway: checker tread plate.
    f"{MOD_ID}_tread_plate": {
        "texture": {"family": "rubber_tread",
                    "params": {"base": [0.46, 0.47, 0.49], "pattern": "dots"}},
        "color": [0.46, 0.47, 0.49, 1.0],
        "metallic": 0.7,
        "roughness": 0.55,
    },
    f"{MOD_ID}_hazard": {
        "texture": {"family": "hazard_chevron"},
        "color": [0.95, 0.75, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    # Machine guarding: the classic perforated/woven safety-green panel.
    f"{MOD_ID}_guard_mesh": {
        "texture": {"family": "mesh_weave", "params": {"base": [0.16, 0.42, 0.24]}},
        "color": [0.16, 0.42, 0.24, 1.0],
        "metallic": 0.4,
        "roughness": 0.6,
    },
    # Painted machine sheet metal (hood, cyclone, console body, motor).
    f"{MOD_ID}_machine_paint": {
        "texture": {"family": "painted_metal",
                    "params": {"base": [0.24, 0.34, 0.42], "peel": 0.35}},
        "color": [0.24, 0.34, 0.42, 1.0],
        "metallic": 0.35,
        "roughness": 0.45,
    },
    f"{MOD_ID}_concrete": {
        "texture": {"family": "concrete"},
        "color": [0.62, 0.60, 0.57, 1.0],
        "metallic": 0.0,
        "roughness": 0.85,
    },
    f"{MOD_ID}_panel_dark": {
        "texture": {"family": "bakelite"},
        "color": [0.08, 0.08, 0.09, 1.0],
        "metallic": 0.1,
        "roughness": 0.45,
    },
    # Engraved control legend - labels computed from PANEL_BUTTONS.
    f"{MOD_ID}_panel_legend": {
        "texture": {
            "family": "panel_legend",
            "size": 1024,
            "params": {
                "title": "BELT SANDER CONTROL",
                "aspect": PLATE_W / PLATE_H,
                "labels": [],  # filled in below, after the helpers exist
            },
        },
        "color": [0.06, 0.07, 0.08, 1.0],
        "metallic": 0.1,
        "roughness": 0.42,
    },
    # Gauge dial face - its own legend sheet so the ticks are real print.
    f"{MOD_ID}_dial_face": {
        "texture": {
            "family": "panel_legend",
            "size": 1024,
            "params": {
                "title": "",
                "aspect": 1.0,
                "base": [0.88, 0.88, 0.86],
                "ink": [0.05, 0.05, 0.06],
                "labels": [],  # filled in below
            },
        },
        "color": [0.88, 0.88, 0.86, 1.0],
        "metallic": 0.0,
        "roughness": 0.4,
    },
    # Machine nameplate on the tail gantry - the one thing the driver is
    # looking straight at for the whole ramp climb. Safety-yellow ground,
    # black print, same panel_legend printer as the console legend so the
    # type is real print and not a decal texture.
    f"{MOD_ID}_machine_sign": {
        "texture": {
            "family": "panel_legend",
            "size": 1024,
            "params": {
                "title": "",
                "aspect": SIGN_HALF_X / SIGN_HALF_Z,
                "base": [0.86, 0.66, 0.05],
                "ink": [0.05, 0.05, 0.06],
                "label_scale": 0.34,
                "labels": [
                    [0.5, 0.600, "BELT SANDER No.3", 1.0],
                    [0.5, 0.215, "GRIT 40   6.0 m BELT   MIND THE NIP", 0.46],
                ],
            },
        },
        "color": [0.86, 0.66, 0.05, 1.0],
        "metallic": 0.1,
        "roughness": 0.5,
    },
    f"{MOD_ID}_btn_green": {
        "color": [0.10, 0.62, 0.20, 1.0], "metallic": 0.1, "roughness": 0.35},
    f"{MOD_ID}_btn_red": {
        "color": [0.72, 0.08, 0.06, 1.0], "metallic": 0.1, "roughness": 0.35},
    f"{MOD_ID}_btn_amber": {
        "color": [0.88, 0.50, 0.04, 1.0], "metallic": 0.1, "roughness": 0.35},
    f"{MOD_ID}_btn_white": {
        "color": [0.88, 0.89, 0.90, 1.0], "metallic": 0.1, "roughness": 0.35},
    f"{MOD_ID}_needle_red": {
        "color": [0.80, 0.06, 0.05, 1.0], "metallic": 0.2, "roughness": 0.35},
}


def _plate_u(x):
    return round((x - PLATE_X0) / PLATE_W, 4)


def _plate_v(z):
    return round((z - PLATE_Z0) / PLATE_H, 4)


PALETTE[f"{MOD_ID}_panel_legend"]["texture"]["params"]["labels"] = [
    [_plate_u(b["position"][0]), _plate_v(b["label_z"]), b["label"], 0.85]
    for b in PANEL_BUTTONS
] + [
    # The plate's own frame is inset 3.5%, and panel_legend already prints
    # the title at v 0.885 - a second heading up there overprinted it in
    # the first render. Only the warning line is added, and its v is
    # computed from a z that is actually inside the plate (a label at
    # v < 0 is simply not drawn, which is how the first one vanished).
    [0.5, _plate_v(0.665), "MIND THE NIP", 0.62],
]


def _dial_label(speed, text, scale=0.8):
    """Place a tick label at the angle the needle will point for `speed`.

    Uses the SAME map as the runtime needle (see LUA_BEHAVIOR): angle =
    -span + 2*span*(v/vmax), tip direction (sin a, cos a) in the dial's
    own (u, v) face frame. Print and pointer therefore cannot disagree.
    """

    angle = math.radians(-NEEDLE_SPAN_DEG + 2.0 * NEEDLE_SPAN_DEG * speed / SPEED_MAX)
    return [
        round(0.5 + 0.355 * math.sin(angle), 4),
        round(0.5 + 0.355 * math.cos(angle), 4),
        text,
        scale,
    ]


PALETTE[f"{MOD_ID}_dial_face"]["texture"]["params"]["labels"] = (
    [_dial_label(0.0, "0")]
    + [_dial_label(v, str(int(v))) for v in SPEED_STEPS]
    + [[0.5, 0.30, "BELT m/s", 0.6]]
)

# AGENTS.md policy 2026-08-07: every palette entry is forced double-sided.
# Three separate invisible-surface bugs shipped on this pack despite
# per-surface winding fixes; the overdraw on one prop is negligible.
for _entry in PALETTE.values():
    _entry["double_sided"] = True

# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------
# Both zones are Overlaps: they are the CANDIDATE set for the per-frame
# sweep, not the authority. Contains drops a moving vehicle the instant its
# bbox pokes out (entries late, exits early), which is exactly wrong for a
# machine whose whole job is to move cars. The authority for "is this car
# on the belt" is a positional test in prop-local coordinates (see
# BS.onBelt in LUA_BEHAVIOR).
TRIGGERS = {
    "lane_zone": {
        "mode": "Overlaps",
        "center": [0.0, (RAMP_FOOT_Y + OUTFEED_END_Y) / 2.0, BELT_Z + 0.6],
        "dimensions": [
            2.0 * WALKWAY_X,
            OUTFEED_END_Y - RAMP_FOOT_Y,
            2.0 * (BELT_Z + 2.6),
        ],
    },
    # Sits over the approach apron AND the console pad, so the greeting
    # fires while the console is still in front of the driver.
    "approach_zone": {
        "mode": "Overlaps",
        "center": [2.0, RAMP_FOOT_Y - 2.0, 1.6],
        "dimensions": [16.0, 10.0, 3.2],
    },
}

# The contact-line emitters' PARKED station: over the platen, level with
# the extraction hood, which is where a machine with nothing on it would
# blow dust from. With a car aboard the runtime slides all three of them
# along the belt to the car's own y (see BS.aimEffects) - the first build
# pinned them here and played "dust at the contact line" up to 14 m away
# from the actual contact line.
EFFECT_HOME_Y = (HOOD_Y0 + HOOD_Y1) / 2.0

EFFECTS = {
    # Grinding dust thrown off the contact line where the platen presses
    # the belt into the workpiece. BNGP_2 is the dust emitter this pack has
    # shipped on seven props; no invented emitter names. `BNG_exhaust_steam`
    # and friends do not exist in the shipped data and fail at load -
    # RE-VERIFIED 2026-08-15 against the engine that reports itself as
    # v0.39.4.0 build 20972 (`integrity.json` buildinfo), which is what the
    # install actually is; the "0.38.6" this line used to name was copied
    # from the test PROFILE DIRECTORY name, never off an engine.
    # `BNG_Waterfall_Mist`, `BNG_exhaust_steam` and `BNG_Ambient_Dust`: still
    # zero hits across all 173 shipped zips.
    "grind_dust_l": {
        "emitter": "BNGP_2",
        "position": [-1.7, EFFECT_HOME_Y, BELT_Z + 0.2],
        "direction": [-0.35, 0.55, 0.75],
    },
    "grind_dust_r": {
        "emitter": "BNGP_2",
        "position": [1.7, EFFECT_HOME_Y, BELT_Z + 0.2],
        "direction": [0.35, 0.55, 0.75],
    },
    # SPARKS. The brief asks for sparks at the contact line. THIS PACK has
    # verified exactly four ParticleEmitterData objects live - BNGP_2
    # (dust), BNGP_34 (light exhaust steam), BNGP_sprinkler and
    # BNGP_waterfallsteam - and none of them is a spark. Be precise about
    # what that does and does not say: a 2026-08-15 census of the installed
    # engine (v0.39.4.0 build 20972) finds 91 distinct ParticleEmitterData
    # objects shipped, three of which DO reference a spark particle -
    # BNGP_1 (BNG_sparks), BNGP_9 (BNG_sparks_explosion) and BNGP_82
    # (BNG_brake_spark). So "there is no spark emitter" was too strong; what
    # is true is that this pack has never verified one LIVE on a prop
    # vehicle, and an unverified name that fails at load costs a whole test
    # cycle (AGENTS.md). Trying one is a future round with a live gate, not
    # a comment edit. Until then the flare stays honest: a bright BNGP_34
    # plume thrown up
    # the centreline of the same contact line, mixing with the two dust
    # fans either side of it. It reads as a hot cut; it is not sold as
    # sparks anywhere in the runtime's text.
    "grind_flare": {
        "emitter": "BNGP_34",
        "position": [0.0, EFFECT_HOME_Y, BELT_Z + 0.25],
        "direction": [0.0, 0.45, 0.89],
    },
    # Cyclone stack plume: the extraction system doing its job.
    "hood_exhaust": {
        "emitter": "BNGP_34",
        "position": [CYCLONE_X, CYCLONE_Y, CYCLONE_TOP_Z + 0.9],
        "direction": [0.0, 0.0, 1.0],
    },
}

BEHAVIOR = {
    "camera_distance": 60.0,
    # --- geometry the runtime needs (all derived above, never retyped) ---
    "belt_z": BELT_Z,
    "belt_half_width": BELT_HALF_WIDTH,
    "belt_wrap_r": BELT_WRAP_R,
    "drum_axis_z": DRUM_AXIS_Z,
    "idler_y": IDLER_Y,
    "drive_y": DRIVE_Y,
    "loop_length": LOOP_LENGTH,
    "bar_count": BAR_COUNT,
    "bar_pitch": BAR_PITCH,
    "needle_span_deg": NEEDLE_SPAN_DEG,
    "tension_sweep_deg": TENSION_SWEEP_DEG,
    # --- the time base (see the module docstring) ---
    # After this many WALL seconds of samples the runtime emits one
    # time_base_measured event carrying the measured dtSim-per-wall-second
    # ratio (and whether the wall clock was available at all). 12 s is long
    # enough that a loading hitch cannot dominate the average and short
    # enough that the number is in beamng.log before the first run ends.
    "time_base_report_seconds": 12.0,
    # --- the speed ladder ---
    "speed_steps": list(SPEED_STEPS),
    "speed_max": SPEED_MAX,
    "default_step": DEFAULT_STEP,
    # Drive motor: 28 m/s in 4.7 s. Brake: 28 m/s in 3.1 s. Both are ramps,
    # so the bars, the drums, the needle and the drag all follow one
    # continuously-varying speed instead of snapping between rungs.
    "belt_accel_mps2": 6.0,
    "belt_decel_mps2": 9.0,
    # --- the drag model ---
    # A car on a moving abrasive belt feels Coulomb friction in the
    # direction of contact-patch slip, bounded by mu * g. BeamNG's tyre
    # model already solves the car against a STATIC ground, so what this
    # field injects is the extra term the moving surface adds.
    #
    #   a = min(drag_max, drag_per_belt_mps * v_belt)
    #         * clamp((v_belt - v_car_y) / slip_knee, -1, +1)
    #
    # * The saturation SCALES WITH BELT SPEED (0.42 per m/s). Physically a
    #   faster abrasive belt does more work on the contact patch per unit
    #   time and grabs harder - it is also the only term that gives the
    #   operator a meaningful control, which the machine is built around.
    #   3 m/s -> 1.26 m/s^2; 10 -> 4.2; 21 -> 8.8.
    # * drag_max 9.0 m/s^2 is the PHYSICAL ceiling: mu = 0.92 rubber on
    #   coated abrasive. The model can never exceed real friction. The belt
    #   band's collision triangles carry the "asphalt" ground model to
    #   match: BeamNG has no abrasive ground model, "metal" is its smooth
    #   sheet-steel model, and sizing the injected drag against mu 0.92
    #   while the tyres pushed back through a low-grip surface model biased
    #   the winnable half of the design. asphalt is the highest-grip stock
    #   model this pack has shipped and the same one under the ramp; the
    #   steel transfer plates and the discharge deck keep "metal", which is
    #   what they actually are - so the belt genuinely bites and the plates
    #   at either end genuinely do not.
    # * slip_knee 3.0 m/s is the tyre's linear creep region: below 3 m/s of
    #   slip the tyres partly roll with the belt and the drag tapers to
    #   zero, so a car already matched to belt speed feels NOTHING. That is
    #   what makes a high setting hopeless: you get swept up to belt speed
    #   and then have to brake off 20+ m/s inside 21 m of machine.
    "drag_per_belt_mps": 0.42,
    "drag_max_mps2": 9.0,
    "drag_slip_knee_mps": 3.0,
    # Per-frame safety envelope. At 60 Hz and full drag the honest dv is
    # 9.0/60 = 0.15 m/s; the cap is 10x that, so it only bites when dtSim
    # spikes (a loading hitch) - where an uncapped integration would be a
    # teleport. dt itself is clamped for the same reason AND because
    # AGENTS.md has an open question about dtSim's wall-clock scale.
    "frame_dv_cap": 1.5,
    "dt_clamp": 0.05,
    "max_sample_speed": 80.0,
    # --- "is this car on the belt" positional test, prop-local metres ---
    # x: half the belt plus 0.5 m, so a car hanging a wheel over the edge
    # still gets dragged. y: tangent to tangent plus 0.4 m, which also
    # covers the sliver of nose plate at each drum.
    # z is measured at the REF NODE, which sits ~0.2 m above whatever the
    # car is resting on (etk800 measured 0.205 m on flat ground) and up to
    # ~1.3 m above it when the car is on its roof or its side. The window
    # [-0.6, +1.8] therefore holds every attitude a car can come to rest
    # in, with 0.5 m of margin over the worst one - and rejects anything
    # more than about half a metre clear of the belt, so a car the kicker
    # has already thrown is never re-grabbed in mid-air.
    "contact_margin_x": 0.5,
    "contact_margin_y": 0.4,
    "contact_z_low": -0.6,
    "contact_z_high": 1.8,
    # --- lifecycle ---
    # The machine is a TRAP: it spools up on its own 1.5 s after something
    # lands on the belt, and (if it started itself) idles down 20 s after
    # the belt is empty. An operator RUN overrides both.
    "auto_start_seconds": 1.5,
    "auto_stop_seconds": 20.0,
    # STOP is a LOCKOUT, not a pause. The first build's STOP only cleared
    # b.running, so the auto-arm branch re-armed the belt 1.5 s later while
    # the car was still on it - there was no way to stop the machine to
    # rescue anything, and the toast said "coasting down" while it spun
    # straight back up. STOP now latches b.hold, which suppresses auto-arm
    # entirely. The latch clears when an operator presses RUN or EJECT, or
    # 3 s after the belt goes EMPTY: the machine is still a trap for the
    # next car, it just cannot re-arm under the one you stopped for.
    "hold_release_seconds": 3.0,
    # ... and the lockout is itself bounded. "Every phase needs a way out"
    # (AGENTS.md): the latch clears on an empty belt, but a WRECK cannot
    # drive off, so a dead car would otherwise pin a locked-out machine for
    # good. After 60 wall seconds held with something still aboard the
    # machine announces itself and runs the ordinary purge cycle, which
    # sweeps the belt and then auto-idles. 60 s is far longer than any
    # rescue takes and short enough that nothing is bricked.
    "hold_timeout_seconds": 60.0,
    # No-jam law. A wreck that stops moving on the belt first triggers a
    # PURGE (top speed for 8 s to sweep it off the head end); if it is
    # still there 18 s later it gets launched outright. Nothing can pin
    # this machine forever.
    "jam_speed_mps": 0.6,
    "jam_seconds": 22.0,
    "jam_purge_seconds": 8.0,
    "jam_hard_seconds": 18.0,
    # --- the kicker ---
    # Trip 0.6 m before the lip so the impulse lands as the car leaves it.
    # dv_up = clamp(0.62 * v_forward, 3, 13): the 18% lip only converts
    # ~18% of forward speed geometrically, and 0.62 is the cartoon
    # multiplier that makes the throw read. 13 m/s up = 8.6 m of air; it is
    # ADDED (the car keeps every bit of the speed the belt gave it) and
    # fires exactly once per visit, so it can never be a teleport.
    "kick_trip_y": KICK_LIP_Y - 0.6,
    "kick_rearm_y": DRIVE_Y,
    "kick_deck_z": KICK_LIP_Z,
    "kick_min_mps": 2.5,
    "kick_lift_ratio": 0.62,
    "kick_min_up": 3.0,
    "kick_max_up": 13.0,
    # A car that gets back out past here beat the machine.
    "escape_y": MACHINE_TAIL_Y,
    # --- safety watchdog ---
    # A node explosion balloons the spawn OOBB by hundreds of metres; a
    # normal car's half-extents are ~2.5 m. Quarantined samples stop
    # receiving the field so the machine is not feeding a solver that has
    # already lost the car.
    "safety_enabled": True,
    "oobb_extent_max": 20.0,
    "quarantine_seconds": 8.0,
    "watchdog_period": 0.5,
    # Live readout cadence while anyone is on the belt.
    "readout_period": 0.5,
    # --- effects ---
    # Dust/flare gate. 0.5 m/s, not "> the slowest rung": the first build
    # gated on speed > 3.0 which is EXACTLY rung 1, so the machine ran its
    # slowest setting with no dust and no cyclone plume at all.
    "effect_speed_min": 0.5,
    # Parked station for the contact-line emitters (over the platen, under
    # the hood). With a car aboard they are slid to the car's own y.
    "effect_home_y": EFFECT_HOME_Y,
    # Only re-transform the emitters when the contact line has actually
    # moved this far. Chasing every centimetre would be three setPosRot
    # calls a frame for a plume 25 cm wide; 0.4 m is a quarter of the
    # emitter spacing and invisible.
    "effect_track_step": 0.4,
}

LUA_BEHAVIOR = r"""
-- ======================================================================
-- Belt Sander Conveyor Trap
-- ======================================================================
-- ONE module table (LuaJIT's ~60-upvalue limit; AGENTS.md Lua rule), and
-- every method is a table field so call-time dispatch cannot trip the
-- "method defined above the helper it calls" nil-global trap.
local BS = {}

-- ======================================================================
-- WALL-CLOCK TIME BASE
-- ======================================================================
-- behavior.update is handed dtSim. AGENTS.md records dtSim measured ~3x
-- faster than wall seconds inside a prop's update; a later live pass
-- concluded that was a stepped-rig artifact and live timers run ~1:1.
-- This machine's entire contract is that the gauge says 10 m/s and the
-- belt really moves 10 m/s, so it cannot integrate an unknown time base -
-- and clamping dt bounds a spike, it does not repair a SCALE error.
--
-- proplib copies anything in behavior.hooks onto the GE extension module
-- table, so the prop can subscribe to onUpdate(dtReal, dtSim, dtRaw) and
-- keep its own accumulator of REAL seconds. behavior.update differences
-- that accumulator; dtSim is used only if the hook never fires, and the
-- runtime says which happened in the time_base_measured event.
BS.wall = 0.0
BS.wallTicks = 0

behavior.hooks = {
  onUpdate = function(dtReal)
    -- Guard exactly like the rest of the prop: NaN, negative and absurd
    -- frames never reach an accumulator.
    if type(dtReal) ~= "number" then return end
    if dtReal ~= dtReal then return end
    if dtReal <= 0 or dtReal > 1.0 then return end
    BS.wall = BS.wall + dtReal
    BS.wallTicks = BS.wallTicks + 1
  end,
}

-- Returns the frame's length in WALL seconds, clamped. Also runs the
-- self-calibration that turns "dtSim might be 3x" from folklore into a
-- measured number in beamng.log.
BS.timeStep = function(state, dtSim)
  local b = state.behavior
  local sim = dtSim or 0
  if sim ~= sim or sim < 0 then sim = 0 end
  if sim > B.dt_clamp then sim = B.dt_clamp end
  local dt = sim
  local wall = BS.wall
  if b.wallSeen and wall > b.wallSeen then
    dt = wall - b.wallSeen
    if dt > B.dt_clamp then dt = B.dt_clamp end
    b.wallOk = true
  end
  b.wallSeen = wall
  if not b.calDone then
    b.calWall = b.calWall + dt
    b.calSim = b.calSim + sim
    if b.calWall >= B.time_base_report_seconds then
      b.calDone = true
      local ratio = b.calSim / math.max(1e-6, b.calWall)
      emitEvent(state, "I", "time_base_measured", {
        wall_clock = b.wallOk and "onUpdate_dtReal" or "dtSim_fallback",
        sim_per_wall = math.floor(ratio * 1000) / 1000,
        wall_seconds = math.floor(b.calWall * 10) / 10,
        frames = BS.wallTicks,
      })
    end
  end
  return dt
end

-- Arc-length parameterisation of the belt loop, authored frame.
-- s = 0 at the TAIL tangent (top of the idler drum). s increases along the
-- carrying run to +Y, over the head drum, back along the return run, and
-- up around the tail drum. Returns the loop point on the belt's OUTER face
-- (y, z) plus the tilt theta about +X that carries a slat authored flat on
-- the carrying run to its correct attitude anywhere on the loop.
--   carrying run  theta = 0
--   head wrap     theta = -phi        (0 -> -pi)
--   return run    theta = -pi
--   tail wrap     theta = -(pi+alpha) (-pi -> -2pi)
-- theta decreases monotonically over the loop, which is exactly the drum
-- rotation sense: the top of a drum travels +Y.
BS.point = function(s)
  local lt = B.drive_y - B.idler_y
  local rw = B.belt_wrap_r
  local wrap = math.pi * rw
  s = s % B.loop_length
  if s <= lt then
    return B.idler_y + s, B.belt_z, 0.0
  end
  if s <= lt + wrap then
    local phi = (s - lt) / rw
    return B.drive_y + rw * math.sin(phi),
           B.drum_axis_z + rw * math.cos(phi),
           -phi
  end
  if s <= 2 * lt + wrap then
    return B.drive_y - (s - lt - wrap), B.drum_axis_z - rw, -math.pi
  end
  local alpha = (s - 2 * lt - wrap) / rw
  return B.idler_y - rw * math.sin(alpha),
         B.drum_axis_z - rw * math.cos(alpha),
         -(math.pi + alpha)
end

-- Every moving part is posed from b.travel (metres of belt that have gone
-- by) and b.speed. Nothing here has an independent clock.
BS.pose = function(state)
  local b = state.behavior
  for k = 0, B.bar_count - 1 do
    local home = k * B.bar_pitch
    -- The bar mesh is AUTHORED at its home point with its home tilt baked
    -- in, so the runtime applies the DELTA. At travel = 0 the pose is the
    -- identity and the shipped DAE is exactly what you see.
    local hy, hz, ht = BS.point(home)
    local y, z, t = BS.point(home + b.travel)
    setPartPose(state, string.format("bar%02d", k),
                vec3(0, y - hy, z - hz),
                axisAngle(vec3(1, 0, 0), t - ht))
  end
  -- Drums: surface speed IS belt speed, so omega = v / r. Negative about
  -- +X carries the top of the drum toward +Y.
  local drum = axisAngle(vec3(1, 0, 0), -(b.drumAngle or 0))
  setPartPose(state, "drum_head", nil, drum)
  setPartPose(state, "drum_tail", nil, drum)
  -- Gauge needle: a pure linear map of the SAME b.speed the drag uses.
  local frac = 0
  if B.speed_max > 0 then frac = b.speed / B.speed_max end
  if frac < 0 then frac = 0 elseif frac > 1 then frac = 1 end
  -- The needle mesh is authored ON the zero stop, so this is the delta
  -- from zero and frac = 0 is the identity pose.
  setPartPose(state, "needle", nil, axisAngle(vec3(0, 1, 0),
    math.rad(2 * B.needle_span_deg * frac)))
  -- Take-up tension rockers on the tail gantry. Belt tension climbs with
  -- belt speed, so they read the SAME frac the needle does: positive
  -- rotation about +X lifts the forward (spring) end and drops the
  -- counterweight. Authored at rest, so frac = 0 is the identity pose.
  local rocker = axisAngle(vec3(1, 0, 0), math.rad(B.tension_sweep_deg * frac))
  setPartPose(state, "tension_l", nil, rocker)
  setPartPose(state, "tension_r", nil, rocker)
end

-- ----------------------------------------------------------------------
-- Effects
-- ----------------------------------------------------------------------
-- Emitter toggles are LATCHED, never re-asserted. Re-sending setActive on
-- a cadence is the same hazard class as re-asserting playAmbient (which
-- restarts the clip, AGENTS.md), and every other prop in this pack toggles
-- only on transitions. b.fx caches the last value actually sent.
BS.effect = function(state, name, active)
  local b = state.behavior
  local want = active and true or false
  if b.fx[name] == want then return end
  b.fx[name] = want
  setEffectActive(state, name, want)
end

BS.allEffectsOff = function(state)
  local b = state.behavior
  b.fx = {}
  for name in pairs(EFFECT_SPECS) do
    b.fx[name] = false
    setEffectActive(state, name, false)
  end
end

-- The three contact-line emitters ride the car. Their x offset, their
-- aim and their height come straight out of EFFECT_SPECS - the same table
-- the prop's own transform sync reads - so only the y is overridden and
-- nothing here can drift from spec.EFFECTS.
BS.contactEffects = {"grind_dust_l", "grind_dust_r", "grind_flare"}

BS.aimEffects = function(state, ly)
  local b = state.behavior
  local target = ly or B.effect_home_y
  if target < B.idler_y then target = B.idler_y end
  if target > B.drive_y then target = B.drive_y end
  if b.fxY and math.abs(target - b.fxY) < B.effect_track_step then return end
  b.fxY = target
  for _, name in ipairs(BS.contactEffects) do
    local effect = state.effects[name]
    local row = EFFECT_SPECS[name]
    if effect and row then
      pcall(function()
        local direction = toWorldDir(state, row.direction)
        setObjectTransform(
          effect,
          toWorldPoint(state, vec3(row.position.x, target, row.position.z)),
          vec3(0, 0, 1):getRotationTo(direction),
          vec3(1, 1, 1)
        )
      end)
    end
  end
end

BS.targetSpeed = function(state)
  local b = state.behavior
  if not b.running then return 0.0 end
  if b.purgeUntil and b.clock < b.purgeUntil then
    return B.speed_steps[#B.speed_steps]
  end
  return B.speed_steps[b.step] or 0.0
end

BS.start = function(state, auto)
  local b = state.behavior
  b.running = true
  b.autoStarted = auto and true or false
  b.emptyFor = 0
  b.armTimer = 0
  -- Starting always clears the operator lockout: RUN and EJECT are the
  -- two ways a human takes the machine back.
  b.hold = false
  b.holdSettled = false
  b.holdFor = 0
end

-- STOP is a LOCKOUT. Clearing b.running alone was not enough: the auto-arm
-- branch in behavior.update would re-start the belt B.auto_start_seconds
-- later while the car that needed rescuing was still aboard. b.hold
-- suppresses auto-arm until an operator presses RUN/EJECT or the belt goes
-- empty for B.hold_release_seconds - so the trap still re-arms for the
-- NEXT car, and never for the one you stopped it for.
BS.stop = function(state, latch)
  local b = state.behavior
  b.running = false
  b.autoStarted = false
  b.purgeUntil = nil
  b.armTimer = 0
  if latch then
    b.hold = true
    b.holdSettled = false
    b.holdFor = 0
  end
end

BS.rider = function(state, vehicleId)
  local b = state.behavior
  local rider = b.riders[vehicleId]
  if not rider then
    rider = {jam = 0, kicked = false, deep = false, watchdog = 0}
    b.riders[vehicleId] = rider
  end
  return rider
end

-- Positional membership test in prop-local metres. This, not the trigger,
-- decides who the belt is allowed to drag.
BS.onBelt = function(lx, ly, lz)
  return math.abs(lx) <= B.belt_half_width + B.contact_margin_x
    and ly >= B.idler_y - B.contact_margin_y
    and ly <= B.drive_y + B.contact_margin_y
    and lz >= B.belt_z + B.contact_z_low
    and lz <= B.belt_z + B.contact_z_high
end

-- Candidate set: the Overlaps zone UNION the GE vehicle table. The zone
-- alone can miss a car that entered before the trigger existed; map.objects
-- alone is not guaranteed on every code path. Everything is filtered by
-- eligibleSubject (drops the prop itself and any other installation) and
-- then by the positional test, so a wide net costs nothing.
BS.candidates = function(state)
  local ids = {}
  for vehicleId in pairs(zoneOccupants(state, "lane_zone")) do
    ids[vehicleId] = true
  end
  if map and map.objects then
    for vehicleId in pairs(map.objects) do ids[vehicleId] = true end
  end
  return ids
end

BS.quarantined = function(state, rider)
  return rider.quarantineUntil ~= nil
    and state.behavior.clock < rider.quarantineUntil
end

-- Phys-explosion watchdog: a single exploded node balloons the spawn OOBB
-- by hundreds of metres. Quarantining stops the machine feeding a solver
-- that has already lost the car.
BS.watchdog = function(state, vehicle, rider, dt)
  if not B.safety_enabled then return end
  rider.watchdog = rider.watchdog + dt
  if rider.watchdog < B.watchdog_period then return end
  rider.watchdog = 0
  local ok, extents = pcall(function()
    return vehicle:getSpawnWorldOOBB():getHalfExtents()
  end)
  if not ok or not extents then return end
  if extents.x > B.oobb_extent_max
    or extents.y > B.oobb_extent_max
    or extents.z > B.oobb_extent_max then
    if not BS.quarantined(state, rider) then
      showMessage("SAMPLE INTEGRITY LOST - belt field released.", 2.4)
      emitEvent(state, "I", "sample_quarantined", {
        subject_id = vehicle:getId(),
        extent = math.floor(extents.x * 10) / 10,
      })
    end
    rider.quarantineUntil = state.behavior.clock + B.quarantine_seconds
  end
end

BS.kick = function(state, vehicle, rider, ly, forward, ez)
  if ly < B.kick_rearm_y then rider.kicked = false end
  if rider.kicked or ly < B.kick_trip_y then return end
  if forward < B.kick_min_mps then return end
  rider.kicked = true
  local lift = B.kick_lift_ratio * forward
  if lift < B.kick_min_up then lift = B.kick_min_up end
  if lift > B.kick_max_up then lift = B.kick_max_up end
  -- ADD, never set: the car keeps every bit of the speed the belt gave it
  -- and simply gains the lift the kicker lip is worth.
  if addSubjectVelocity(state, vehicle, ez * lift) then
    local stats = state.behavior.stats
    stats.kicks = (stats.kicks or 0) + 1
    showMessage(string.format("OFF THE KICKER at %.0f m/s!", forward), 2.2)
    emitEvent(state, "I", "sample_kicked", {
      subject_id = vehicle:getId(),
      forward_mps = math.floor(forward * 10) / 10,
      lift_mps = math.floor(lift * 10) / 10,
    })
  end
end

-- The no-jam law. Anything that stops moving on a running belt is first
-- swept (purge = top speed) and then, if it is still aboard, thrown.
BS.jam = function(state, vehicle, rider, dt, onBelt)
  local b = state.behavior
  if not onBelt or b.speed < 1.0 then
    rider.jam = 0
    return
  end
  local speed = 0
  local ok, velocity = pcall(function() return vehicle:getVelocity() end)
  if ok and finiteVector3(velocity) then speed = velocity:length() end
  if speed > B.jam_speed_mps then
    rider.jam = 0
    return
  end
  rider.jam = rider.jam + dt
  if rider.jam >= B.jam_seconds + B.jam_hard_seconds then
    rider.jam = 0
    local forward = toWorldDir(state, vec3(0, 1, 0))
    local up = toWorldDir(state, vec3(0, 0, 1))
    if launchSubject(state, vehicle, forward * 18.0 + up * 9.0) then
      showMessage("DISCHARGE OVERRIDE - clearing the belt.", 2.6)
      emitEvent(state, "I", "jam_discharged", {subject_id = vehicle:getId()})
    end
  elseif rider.jam >= B.jam_seconds then
    if not b.purgeUntil or b.clock >= b.purgeUntil then
      b.purgeUntil = b.clock + B.jam_purge_seconds
      showMessage("BELT JAM - PURGE CYCLE, full speed.", 2.6)
      emitEvent(state, "I", "purge_started", {subject_id = vehicle:getId()})
    end
  end
end

BS.sweep = function(state, dt)
  local b = state.behavior
  local origin = toWorldPoint(state, vec3(0, 0, 0))
  local ex = toWorldDir(state, vec3(1, 0, 0))
  local ey = toWorldDir(state, vec3(0, 1, 0))
  local ez = toWorldDir(state, vec3(0, 0, 1))
  local aboard = 0
  local worst = nil
  for vehicleId in pairs(BS.candidates(state)) do
    local vehicle = eligibleSubject(vehicleId)
    if vehicle then
      local position = vehicle:getPosition()
      local velocity = vehicle:getVelocity()
      if finiteVector3(position) and finiteVector3(velocity) then
        local offset = position - origin
        local lx, ly, lz = offset:dot(ex), offset:dot(ey), offset:dot(ez)
        local forward = velocity:dot(ey)
        local onBelt = BS.onBelt(lx, ly, lz)
        local rider = BS.rider(state, vehicleId)
        -- The kicker gate only needs to know the car is on the discharge
        -- structure, so it uses the kicker deck height, not the belt's.
        if math.abs(lx) <= B.belt_half_width + B.contact_margin_x
          and lz >= B.kick_deck_z + B.contact_z_low
          and lz <= B.kick_deck_z + B.contact_z_high then
          BS.kick(state, vehicle, rider, ly, forward, ez)
        elseif ly < B.kick_rearm_y then
          rider.kicked = false
        end
        if onBelt then
          aboard = aboard + 1
          -- Only sample the OOBB for cars actually on the belt: this runs
          -- over every vehicle on the map, and the watchdog is the only
          -- per-candidate engine call that is not free.
          BS.watchdog(state, vehicle, rider, dt)
          rider.deep = rider.deep or (ly > B.idler_y + 3.0)
          if worst == nil or ly > worst.ly then
            worst = {ly = ly, forward = forward}
          end
          if not BS.quarantined(state, rider)
            and velocity:length() < B.max_sample_speed
            and b.speed > 0.05 then
            -- Coulomb-style tangential drag toward the belt's surface
            -- velocity, saturating at min(drag_max, k * belt speed), with
            -- a linear creep region below slip_knee. See the derivation in
            -- spec.py BEHAVIOR.
            local slip = b.speed - forward
            local knee = slip / B.drag_slip_knee_mps
            if knee > 1 then knee = 1 elseif knee < -1 then knee = -1 end
            local grip = B.drag_per_belt_mps * b.speed
            if grip > B.drag_max_mps2 then grip = B.drag_max_mps2 end
            local dv = grip * knee * dt
            if dv > B.frame_dv_cap then dv = B.frame_dv_cap end
            if dv < -B.frame_dv_cap then dv = -B.frame_dv_cap end
            addSubjectVelocity(state, vehicle, ey * dv)
          end
        elseif rider.deep and ly < B.escape_y and lz < B.belt_z + 1.8 then
          rider.deep = false
          if b.speed > B.speed_steps[1] then
            showMessage("YOU BEAT THE BELT. Out the feed end.", 2.8)
            emitEvent(state, "I", "sample_escaped", {
              subject_id = vehicleId,
              belt_mps = math.floor(b.speed * 10) / 10,
            })
          end
        end
        BS.jam(state, vehicle, rider, dt, onBelt)
      end
    else
      b.riders[vehicleId] = nil
    end
  end
  return aboard, worst
end

BS.readout = function(state, dt, aboard, worst)
  local b = state.behavior
  b.readoutTimer = b.readoutTimer + dt
  if b.readoutTimer < B.readout_period then return end
  b.readoutTimer = 0
  if aboard <= 0 or not worst then return end
  -- Every number here is measured or is the exact variable that drives the
  -- drag, the bars, the drums, the rockers and the needle - and the
  -- seconds it was integrated against are wall seconds (see BS.timeStep).
  local togo = math.max(0, B.drive_y - worst.ly)
  if b.hold then
    showMessage(string.format(
      "BELT LOCKED OUT - %.1f m/s and falling   %.0f m to the drum",
      b.speed, togo), 0.9)
  else
    showMessage(string.format(
      "BELT %.1f m/s   YOU %+.1f m/s   %.0f m to the drum",
      b.speed, worst.forward, togo), 0.9)
  end
end

behavior.init = function(state)
  local b = state.behavior
  b.clock = 0
  b.travel = 0
  b.drumAngle = 0
  b.speed = 0
  b.step = B.default_step
  b.running = false
  b.autoStarted = false
  b.hold = false
  b.holdSettled = false
  b.holdFor = 0
  b.armTimer = 0
  b.emptyFor = 0
  b.readoutTimer = 0
  b.purgeUntil = nil
  b.riders = {}
  b.phase = "idle"
  b.stats = {peak_belt_mps = 0, kicks = 0}
  -- Effect latch cache + the emitters' current station. nil (not false) so
  -- the first BS.effect call always reaches the engine.
  b.fx = {}
  b.fxY = nil
  -- Time base bookkeeping (see BS.timeStep).
  b.wallSeen = nil
  b.wallOk = false
  b.calWall = 0
  b.calSim = 0
  b.calDone = false
  BS.pose(state)
end

behavior.reset = function(state)
  behavior.init(state)
  BS.allEffectsOff(state)
  BS.aimEffects(state, nil)
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if zone == "approach_zone" then
    showMessage(string.format(
      "BELT SANDER No.3 - console on your right, setpoint %.0f m/s. "
      .. "RED STOP locks the belt out if you need off. "
      .. "Drive up when you are ready.", B.speed_steps[b.step]), 3.8)
  elseif zone == "lane_zone" then
    emitEvent(state, "I", "lane_entered", {subject_id = vehicle:getId()})
  end
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  state.behavior.riders[vehicleId] = nil
end

behavior.onPanelButton = function(state, buttonId)
  local b = state.behavior
  if buttonId == "btn_run" then
    if b.running and not b.autoStarted then
      showMessage(string.format("Belt already running at %.1f m/s.",
        B.speed_steps[b.step]), 2.0)
    else
      BS.start(state, false)
      showMessage(string.format(
        "BELT RUN - setpoint %.1f m/s. Mind the nip.",
        B.speed_steps[b.step]), 2.6)
      emitEvent(state, "I", "belt_run", {setpoint = B.speed_steps[b.step]})
    end
  elseif buttonId == "btn_stop" then
    -- The rescue control. It LATCHES: the belt brakes to zero and the
    -- machine will not re-arm itself while anything is still aboard. The
    -- toast quotes the real braking time from the live speed and the real
    -- decel ramp, so it cannot promise something the machine will not do.
    local was = b.speed
    BS.stop(state, true)
    showMessage(string.format(
      "BELT STOP - braking from %.1f m/s (%.1f s). LOCKED OUT.",
      was, was / B.belt_decel_mps2), 2.6)
    emitEvent(state, "I", "belt_stop", {
      from_mps = math.floor(was * 10) / 10,
      brake_seconds = math.floor(was / B.belt_decel_mps2 * 10) / 10,
    })
  elseif buttonId == "btn_eject" then
    -- Manual no-jam path: sweep the belt at full speed for one purge
    -- window. Anything aboard reaches the kicker and leaves the normal
    -- way, through the lip, at whatever speed it earns. Started as AUTO on
    -- purpose: EJECT is a one-shot clearing cycle, so when the belt is
    -- clear the machine idles itself down B.auto_stop_seconds later
    -- instead of running at setpoint forever (auto-idle is gated on
    -- autoStarted, so an operator-flagged eject would have armed the
    -- machine permanently).
    BS.start(state, true)
    b.purgeUntil = b.clock + B.jam_purge_seconds
    showMessage("EJECT - full speed until the belt is clear.", 2.6)
    emitEvent(state, "I", "eject_requested", {})
  elseif buttonId == "btn_faster" or buttonId == "btn_slower" then
    local step = b.step + (buttonId == "btn_faster" and 1 or -1)
    if step < 1 then step = 1 end
    if step > #B.speed_steps then step = #B.speed_steps end
    b.step = step
    showMessage(string.format(
      "BELT SETPOINT %.1f m/s   (running %.1f m/s)",
      B.speed_steps[step], b.speed), 2.2)
    emitEvent(state, "I", "belt_setpoint", {
      step = step, setpoint = B.speed_steps[step],
    })
  end
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  -- WALL seconds, clamped, before ANY integration. The clamp bounds the
  -- injected dv, the belt travel per frame and every timer against a
  -- loading hitch; the wall clock is what makes the m/s on the gauge mean
  -- m/s in the room (see BS.timeStep).
  local dt = BS.timeStep(state, dtSim)
  b.clock = b.clock + dt

  local aboard, worst = BS.sweep(state, dt)

  -- Auto-arm / auto-idle. The machine is a trap: it spools up on its own
  -- when something lands on it, and idles down when the belt is empty -
  -- but only if IT started itself. An operator RUN keeps running, and an
  -- operator STOP holds the machine down (b.hold) so the trap cannot
  -- re-arm under the car someone just stopped it for.
  if aboard > 0 then
    b.emptyFor = 0
    if b.hold then
      -- The lockout is bounded. It normally clears when the belt goes
      -- empty, but a wreck cannot drive off, so a dead car would pin a
      -- held machine for good. On timeout the machine says so and runs
      -- the ordinary purge cycle, which sweeps the belt and auto-idles.
      b.holdFor = b.holdFor + dt
      if b.holdFor >= B.hold_timeout_seconds then
        showMessage("LOCKOUT TIMED OUT - purge cycle, clearing the belt.", 3.2)
        emitEvent(state, "I", "belt_hold_timeout", {aboard = aboard})
        BS.start(state, true)
        b.purgeUntil = b.clock + B.jam_purge_seconds
      end
    end
    if not b.running and not b.hold then
      b.armTimer = b.armTimer + dt
      if b.armTimer >= B.auto_start_seconds then
        BS.start(state, true)
        showMessage(string.format(
          "BELT SANDER ARMED - %.0f m/s. Get off or drive out.",
          B.speed_steps[b.step]), 3.0)
        emitEvent(state, "I", "belt_auto_armed", {
          setpoint = B.speed_steps[b.step],
        })
      end
    end
  else
    b.armTimer = 0
    b.emptyFor = b.emptyFor + dt
    if b.running and b.autoStarted and b.emptyFor >= B.auto_stop_seconds then
      BS.stop(state, false)
      emitEvent(state, "I", "belt_auto_idle", {})
    end
    -- The lockout is released once the belt has been clear a moment: the
    -- machine goes back to being a trap for whatever arrives next.
    if b.hold and b.emptyFor >= B.hold_release_seconds then
      b.hold = false
      b.holdSettled = false
      emitEvent(state, "I", "belt_hold_released", {})
    end
  end
  if b.purgeUntil and b.clock >= b.purgeUntil then b.purgeUntil = nil end

  -- ONE speed integration. Everything downstream is a function of it.
  local target = BS.targetSpeed(state)
  if b.speed < target then
    b.speed = math.min(target, b.speed + B.belt_accel_mps2 * dt)
  elseif b.speed > target then
    b.speed = math.max(target, b.speed - B.belt_decel_mps2 * dt)
  end
  if b.speed > b.stats.peak_belt_mps then
    b.stats.peak_belt_mps = math.floor(b.speed * 10) / 10
  end
  b.travel = (b.travel + b.speed * dt) % B.loop_length
  -- The drum angle gets its own accumulator: wrapping travel at the loop
  -- length would jump the drums by loop/r radians once per lap.
  b.drumAngle = (b.drumAngle + b.speed * dt / B.belt_wrap_r) % (2 * math.pi)
  b.phase = (b.speed > 0.05) and "running" or "idle"
  -- One-shot confirmation that the lockout actually did what the STOP
  -- toast promised. Without it the operator has to guess whether the belt
  -- is still coasting.
  if b.hold and not b.holdSettled and b.speed <= 0.001 then
    b.holdSettled = true
    showMessage("BELT STOPPED - locked out. Drive off; RUN to re-arm.", 3.0)
    emitEvent(state, "I", "belt_stopped", {aboard = aboard})
  end

  BS.pose(state)
  -- Latched toggles only (BS.effect memoises), and the contact line
  -- follows the deepest car on the belt instead of a fixed authored y.
  local running = b.speed > B.effect_speed_min
  local loaded = aboard > 0
  BS.effect(state, "grind_dust_l", running and loaded)
  BS.effect(state, "grind_dust_r", running and loaded)
  BS.effect(state, "grind_flare", running and loaded)
  BS.effect(state, "hood_exhaust", running)
  BS.aimEffects(state, (loaded and worst) and worst.ly or nil)
  BS.readout(state, dt, aboard, worst)
end
"""
