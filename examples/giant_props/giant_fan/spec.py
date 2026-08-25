"""The Giant Fan — authored constants for Blender + runtime.

A GALEFORCE GF-3600 three-blade oscillating table fan, scaled 108x, with the
guard cut off. Each blade is a city bus: 12.19 m root to tip, 2.59 m across at
its widest, on a rotor that sweeps 30.78 m and passes 0.35 m over a drivable
deck. Turn the dial and the thing that comes round is the size of the vehicle
you are sitting in.

===========================================================================
WHY THIS PROP IS BUILT DIFFERENTLY FROM EVERY OTHER ONE IN THE PACK
===========================================================================

Every other rotating prop here — ``spin_cycle_washer``'s drum,
``gforce_centrifuge``'s arm, ``junk_chute_grinder``'s rotors,
``belt_sander_trap``'s drums — is THEATRE. The thing that visibly turns is a
runtime ``TSStatic`` with ``collisionType`` "None", and the collision under it
is a stationary skin; what moves the car is a scripted per-frame velocity
field. That is the right answer when the machine is a conveyor and the car is
cargo. It is the wrong answer here, because the entire point of a fan with no
guard is that the BLADE hits you.

The three cheaper mechanisms were each measured and rejected:

* a moving ``TSStatic`` re-baked with ``be:reloadCollision()`` — the bake is
  GLOBAL and costs milliseconds. ``sumo_gyro_platform`` gets away with a
  continuously spinning deck only because a dish is AXISYMMETRIC, so its baked
  hull is pose-invariant. A three-blade rotor is maximally non-axisymmetric:
  every angle is a different hull.
* ``obj:setNodePosition`` from vehicle ``updateGFX`` (the ``pachinko_tower``
  mechanism) — collision does follow, same frame, no bake. But it is only
  reachable at GRAPHICS rate, and pachinko's own measured stability clamp is
  0.008 m of travel per frame. At TIP_R that is a 0.48 m/s tip speed.
* a scripted impulse — which is what the user explicitly did not ask for.

So the fan uses BeamNG's own ``rotators``: the mechanism behind the stock
``large_spinner`` prop, i.e. literally the way a car gets wrecked by a spinning
prop in this game. The rotor is a REAL free-node softbody with its own
collision triangles, driven through a ``powertrain`` shaft by an
``electricMotor``, solved at the engine's 2000 Hz. Nothing about the strike is
scripted: the car is hit by moving geometry and the solver does the rest, so
the rotor also takes the hit back and bogs.

Stock's structure, copied exactly (verified against the installed 0.39.4.0
tree, NOT copied as content — see AGENTS.md:357; the torque curve, the
controller and every value here are authored):

* the rotator group is the DRIVE COLLAR only — a compact ring on the axis.
  ``large_spinner``'s ``spin_center`` is eight nodes; its four ARMS are group
  ``spin_top`` and are NOT in the rotator group. They follow through beams.
  The fan's three blades follow its hub ring the same way.
* the collar is beamed to BOTH axis nodes and to nothing else on the head.
* the axis nodes are ordinary FREE nodes, which is what lets the whole rotor
  ride a head that yaws and tilts. A rotator on a moving hub is a steered
  wheel, and every car in the game is the proof.

===========================================================================
THE THREE CONTROLS
===========================================================================

POWER is the dial, and it keeps the real Lasko detent order — reading
clockwise the face is 0, 3, 2, 1, so THE FIRST CLICK FROM OFF IS FULL POWER.
That is not a bug and it is the best joke on the machine.

SWEEP is the big chrome plunger on the crown of the motor housing, where an
oscillating table fan's oscillation knob actually lives. Push it and the head
starts its 90-degree sweep; push it again and it centres and locks.

TILT is a five-rung ladder, and the rungs are authored as STRIKE HEIGHTS, not
as angles: the number that matters is how far the blade tip clears the deck at
bottom-dead-centre, because that is what decides which vehicles get hit.

Both sweep and tilt are linear ``hydros`` on a crank — the ``large_crusher``
primitive — not ``torsionHydros``. ``torsionHydros`` are real and stock uses
them in 85 files, but across all 177 spring values in those files the range is
100 .. 1.5e6, and this machine's joints need 1e8 .. 1e9. A crank's lever arm
supplies the missing orders of magnitude with a ``beamSpring`` stock already
ships.

Frames: authored right-handed, meters, Z-up. **+Y is the fan's face** — the
direction it blows, and the killing floor. The machine is entered from +Y.
"""

from __future__ import annotations

import math

MOD_ID = "ericrolph_giant_fan"
DISPLAY_NAME = "The Giant Fan"
VALUE_DOLLARS = 240000
ZIP_BASENAME = "giant_fan_ericrolph.zip"

BRAND = "GALEFORCE GF-3600"

# ---------------------------------------------------------------------------
# 1. The defining number.
#
# "Each fan blade should be the size of a city bus." A standard 40-ft North
# American transit bus is 12.19 x 2.59 x 3.20 m. BLADE_SPAN is that length and
# BLADE_CHORD_MAX is that width; every other dimension on the machine is
# derived from the rotor those two numbers make.
# ---------------------------------------------------------------------------
BUS_L, BUS_W, BUS_H = 12.19, 2.59, 3.20

BLADE_SPAN = BUS_L  # 12.19, root -> tip
HUB_R = 3.20  # blade root circle
TIP_R = HUB_R + BLADE_SPAN  # 15.39, max swept radius
ROTOR_D = 2.0 * TIP_R  # 30.78
BLADE_COUNT = 3
SCALE_VS_12IN = TIP_R / 0.1425  # 108.0x a real 12-inch fan

# ---------------------------------------------------------------------------
# 2. The forced elevation, and the one deliberate proportion break.
#
# Scaling a real table fan proportionally puts the hub axis 2.1 blade-radii
# above the table — 32 m up for us — and THE BLADES COULD THEN NEVER TOUCH A
# CAR, which destroys the mod. So the head sits one blade-radius plus a hair
# above the deck instead, and the clearance is the authored number:
#
#     HUB_Z = DECK_Z + TIP_R + BLADE_BOTTOM_CLEAR
#
# This is the same species of forced dimension as spin_launch's
# HUB_Z = DECK_Z + TETHER_R: one gameplay constraint fixes the elevation and
# everything else keys off it. It is a deviation from the reference, it is
# deliberate, and it is the reason the machine works.
#
# The base is re-datumed on its FEET so the spawn datum is honest: the four
# pads' underside rings sit at exactly z = 0, which is what
# test_reference_node_is_the_lowest_node measures (the spin_launch tombstone).
# ---------------------------------------------------------------------------
FOOT_PROUD = 0.52  # the feet stand the slab off the ground
BASE_UNDERSIDE_Z = FOOT_PROUD  # 0.52
DECK_Z = 2.40  # drivable deck top
BASE_H = DECK_Z - FOOT_PROUD  # 1.88, slab body thickness
BLADE_BOTTOM_CLEAR = 0.35  # tip -> deck at BDC, zero tilt
HUB_Z = DECK_Z + TIP_R + BLADE_BOTTOM_CLEAR  # 18.14
TOP_Z = HUB_Z + TIP_R  # 33.53, overall height

# ---------------------------------------------------------------------------
# 3. Blade planform, and the axial extent a TWISTED paddle actually has.
#
# A fan blade is not a slab: it is a paddle set at a pitch that washes out
# along the span. Its extent ALONG THE FAN AXIS is therefore NOT
# BLADE_THICK/2 — it is (chord*sin(pitch) + thick*cos(pitch))/2, which is
# between 1.8x and 2.5x that. Every clearance on this machine is checked
# against the real number, because using the slab thickness is how a blade
# ends up passing through the neck.
# ---------------------------------------------------------------------------
# "The size of a city bus" sets the SPAN exactly - 12.19 m, root to tip. It
# cannot also set the chord: a bus is 4.7 : 1 in plan and a Lasko blade is
# about 1.4 : 1, so a blade built to a bus's plan footprint reads as a stick,
# not as a fan. The compromise is stated rather than hidden: the span is
# exactly a bus long, and the PLANFORM AREA (about 40 m^2) is a bus's side
# elevation, 12.19 x 3.20. The blade is bus-sized by length and by area, and
# it is shaped like the reference.
BLADE_CHORD_ROOT, BLADE_CHORD_MAX, BLADE_CHORD_TIP = 2.30, 4.30, 3.55
CHORD_MAX_S = 0.76  # widest OUTBOARD, like the reference paddle
BLADE_THICK = 0.62  # shell thickness, and the collision depth budget
PITCH_ROOT_DEG, PITCH_TIP_DEG = 32.0, 14.0
BLADE_STATIONS_S = (0.00, 0.20, 0.40, 0.62, 0.82, 1.00)
STATION_NODES = (4, 4, 4, 4, 6, 6)  # the outboard two carry the nose


def blade_chord(s: float) -> float:
    """Chord at spanwise fraction ``s``; widest outboard, like the reference."""

    if s <= CHORD_MAX_S:
        return BLADE_CHORD_ROOT + (BLADE_CHORD_MAX - BLADE_CHORD_ROOT) * s / CHORD_MAX_S
    return BLADE_CHORD_MAX + (BLADE_CHORD_TIP - BLADE_CHORD_MAX) * (s - CHORD_MAX_S) / (
        1.0 - CHORD_MAX_S
    )


def blade_pitch(s: float) -> float:
    """Blade pitch in radians; a classic axial-fan washout, root to tip."""

    return math.radians(PITCH_ROOT_DEG - (PITCH_ROOT_DEG - PITCH_TIP_DEG) * s)


def blade_axial_half(s: float) -> float:
    """Half-extent ALONG THE FAN AXIS. Not BLADE_THICK/2 — see above."""

    p = blade_pitch(s)
    return (blade_chord(s) * math.sin(p) + BLADE_THICK * math.cos(p)) / 2.0


def blade_inplane_half(s: float) -> float:
    """Half-extent IN the disc plane (chordwise), used by the swept hull."""

    p = blade_pitch(s)
    return (blade_chord(s) * math.cos(p) + BLADE_THICK * math.sin(p)) / 2.0


BLADE_AXIAL_HALF_ROOT = blade_axial_half(0.0)  # 0.753070
BLADE_AXIAL_HALF_TIP = blade_axial_half(1.0)  # 0.554810

BLADE_AZIMUTHS = tuple(2.0 * math.pi * i / BLADE_COUNT for i in range(BLADE_COUNT))
# The four section corners the cage and the visual loft both emit, as
# (chord_frac, thick_frac). Stated once so the strike-height solver below and
# the generator cannot disagree about what a blade actually occupies.
BLADE_SECTION_CORNERS = ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5))


def blade_section(s: float) -> tuple[float, float, float]:
    """(radius, chord, pitch) at spanwise fraction ``s``."""

    return (HUB_R + s * BLADE_SPAN, blade_chord(s), blade_pitch(s))


def blade_point(
    azimuth: float, s: float, chord_frac: float, thick_frac: float
) -> tuple[float, float, float]:
    """A point on a blade, in world coordinates.

    ``azimuth`` is the blade's angle about the fan axis, measured so that 0 is
    bottom-dead-centre - the authored rest pose, and therefore also the park
    detent and the reset pose. ``chord_frac`` runs -0.5 (leading edge) to
    +0.5 (trailing edge); ``thick_frac`` is -0.5 .. +0.5 through the shell.

    The section is set at its pitch, which is why a blade's extent ALONG the
    fan axis is chord*sin(pitch) + thick*cos(pitch) and not the shell
    thickness. Every clearance on this machine is checked against that.

    This lives HERE rather than in the generator because the strike-height
    ladder is solved against the blade's real corner cloud, and a second copy
    of the sampler would be a second blade.
    """

    radius, chord, pitch = blade_section(s)
    # In-section local axes: `c` runs along the chord, `t` through the shell.
    c = chord * chord_frac
    t = BLADE_THICK * thick_frac
    # Rotate the section by its pitch about the blade's own span axis. The
    # result is (in-plane, axial) relative to the disc.
    in_plane = c * math.cos(pitch) + t * math.sin(pitch)
    axial = -c * math.sin(pitch) + t * math.cos(pitch)
    # Place it round the fan axis. The disc plane sits DISC_OFFSET_Y forward.
    ca, sa = math.cos(azimuth), math.sin(azimuth)
    # Blade runs outward along (sin a, 0, -cos a) from the hub at azimuth 0
    # pointing straight DOWN, so azimuth 0 is bottom-dead-centre.
    ex, ez = sa, -ca  # unit vector along the span, in the disc plane
    px = radius * ex + in_plane * (-ez)
    pz = radius * ez + in_plane * (ex)
    return (px, DISC_OFFSET_Y + axial, HUB_Z + pz)


def blade_corner_cloud() -> tuple[tuple[float, float, float], ...]:
    """Every corner node the rotor's collision cage carries.

    Three blades x BLADE_STATIONS_S x four section corners: exactly the set
    the generator emits as free nodes, so the lowest point of THIS cloud is
    the lowest point of the thing that hits a car.
    """

    return tuple(
        blade_point(azimuth, s, chord_frac, thick_frac)
        for azimuth in BLADE_AZIMUTHS
        for s in BLADE_STATIONS_S
        for chord_frac, thick_frac in BLADE_SECTION_CORNERS
    )

# ---------------------------------------------------------------------------
# 4. The offset that makes the machine assemblable.
#
# The disc plane has to stand far enough in front of the yaw axis and the tilt
# trunnion that a blade sweeping past bottom-dead-centre misses the neck. Both
# constraints are evaluated against the REAL axial extent above.
# ---------------------------------------------------------------------------
# The housing is NOT symmetric about the trunnion. On a real table fan the
# motor's front rim sits just behind the blades and the body extends back over
# the yoke - which is also what puts the tilt pivot near the machine's centre
# of mass. A housing centred on the trunnion would have to be half as long
# again to reach the disc, and it read as a barrel.
HSG_L = 6.60  # motor housing length
ROTOR_STANDOFF = 1.00  # AUTHORED: disc plane to housing rim
# DISC_OFFSET_Y is set by the BLADE-versus-NECK sweep, not by the housing:
# at bottom-dead-centre the blade passes the neck, and the binding station is
# the one that maximises neck_r(z) + blade_axial_half(s(z)). Solved in
# _disc_offset_floor() below; the authored value carries a 1.00 m margin.
DISC_OFFSET_Y = 6.70

# ---------------------------------------------------------------------------
# 5. Rotor mass and the speed ladder.
#
# TIP SPEEDS are authored and omega is derived (omega = v_tip / TIP_R), the
# spin_launch discipline: the number on the machine is the number the blade
# actually does. Setting 1's 22 m/s is, to within a rounding, the tip speed of
# a REAL 12-inch Lasko on high — so the smallest setting on this machine blows
# exactly as hard as the thing it is a scale model of, and setting 3 is three
# times that.
#
# DIAL_RATIO is normalised against the MOTOR's redline, not against setting 3,
# because that is what the rotator's speed ratio actually means:
# spinner-style control closes on abs(motorAV) / motor.maxAV.
# ---------------------------------------------------------------------------
BLADE_SHELL_KG = 6500.0  # per blade, moulded shell
ROOT_FERRULE_KG = 1200.0  # per blade, steel root fitting
TIP_CAP_KG = 300.0  # per blade, moulded tip closure
HUB_KG = 9000.0  # hub ring + spider + backplate
HUB_RING_R = HUB_R  # the collar ring radius
HUB_RING_Y = (5.85, 7.05)  # the ring STRADDLES the axis node pair
ROTOR_KG = BLADE_COUNT * (BLADE_SHELL_KG + ROOT_FERRULE_KG + TIP_CAP_KG) + HUB_KG

GEAR_RATIO = 40.0
SHAFT_FRICTION = 140.0  # N.m at the rotor
MOTOR_INERTIA = 23.0


def _rotor_inertia() -> float:
    """Rotor polar inertia about the fan axis, DERIVED from the mass table.

    Each blade is a tapered rod from HUB_R to TIP_R carrying the shell and its
    root ferrule, plus a tip cap concentrated at TIP_R; the hub is a ring at
    HUB_RING_R. Nothing here is a round number chosen to make a gate pass.
    """

    r1, r2 = HUB_R, TIP_R
    rod = (BLADE_SHELL_KG + ROOT_FERRULE_KG) * (r1 * r1 + r1 * r2 + r2 * r2) / 3.0
    cap = TIP_CAP_KG * r2 * r2
    return BLADE_COUNT * (rod + cap) + HUB_KG * HUB_RING_R**2


ROTOR_INERTIA = _rotor_inertia()  # 2_587_145.66 kg.m^2

# BeamNG's own pair, from lua/vehicle/powertrain/electricMotor.lua: init does
# `device.maxAV = device.maxRPM * rpmToAV`, so this is the constant the speed
# ratio is built from. pi/30 is NOT the number the engine uses here.
RPM_TO_AV = 0.104719755
AV_TO_RPM = 9.549296596425384

MOTOR_MAX_RPM = 1760.0  # 1800 synchronous less 2.2% slip
MOTOR_MAX_AV = MOTOR_MAX_RPM * RPM_TO_AV  # 184.3067688
REDLINE_AV = MOTOR_MAX_AV / GEAR_RATIO  # 4.60766922, the rotor's redline

TIP_MPS = (0.0, 22.0, 42.0, 68.0)  # AUTHORED
DIAL_ORDER = (0, 3, 2, 1)  # the real Lasko detent order
OMEGA = tuple(v / TIP_R for v in TIP_MPS)  # DERIVED
OMEGA_3 = OMEGA[3]  # 4.418453541260559
DIAL_RATIO = tuple(w * GEAR_RATIO / MOTOR_MAX_AV for w in OMEGA)

# SOLVED, not asserted: bisected against the closed-loop rotor simulation
# (the real motor curve, the real blade aero drag, the controller's own brake
# ramp) for a coast-down of exactly COASTDOWN_S from setting 3. Measured
# 25.02 s. A round 4e6 would have stopped 2.3 million kg.m^2 in 1.6 s, which
# reads as the rotor hitting a wall rather than winding down.
BRAKE_TORQUE = 480_150.0  # N.m
BRAKE_SPRING = 3900  # a MULTIPLIER on brakeTorque, not a stiffness
BRAKE_DAMP = 1.6e7  # the engine default is ZERO
DOWNSTEP_BRAKE = 0.50  # fraction of BRAKE_TORQUE on a dial DOWN-step
SPINUP_S = 8.0
COASTDOWN_S = 25.0
DIAL_DEBOUNCE_S = 0.60

# The authored rest pose IS a blade at bottom-dead-centre, so the park detent,
# the rest pose and the reset pose are all the same angle: stop the fan and a
# bus-sized blade is lying across the deck in front of you.
BDC_AZIMUTH = 0.0
CREEP_FAST, CREEP_SLOW = 0.040, 0.012
PARK_ENTRY_AV = CREEP_FAST * REDLINE_AV
PARK_SLOW_AV = CREEP_SLOW * REDLINE_AV
PARK_FAST_LEAD = 0.50  # rad short of the detent
PARK_LOCK_LEAD = 0.055

# ---------------------------------------------------------------------------
# 6. Sweep and tilt.
#
# TILT_CLEAR_M is authored as the blade tip's clearance over the deck at
# bottom-dead-centre, one rung at a time, because that is the number that
# decides what gets hit. The angles are solved from it, never the other way
# round.
# ---------------------------------------------------------------------------
SWEEP_HALF_RAD = math.pi / 4.0  # +-45 deg, 90 deg total
SWEEP_PERIOD_S = 16.0
SWEEP_ARM_S = 1.20  # the dog clutch engaging: the head does not move yet

YAW_CRANK_R = 4.60  # crank pin radius on the yoke collar
YAW_ANCHOR_BACK = 11.00  # deck stanchion offset, -Y
YAW_PIN_Z, YAW_ANCHOR_Z = 9.20, 2.62
YAW_DZ = YAW_PIN_Z - YAW_ANCHOR_Z  # 6.58, invariant under yaw

TILT_CLEAR_M = (0.35, 1.30, 1.55, 1.95, 2.60)  # AUTHORED strike heights
TILT_RUNG_NAME = ("EVERYTHING", "SUPERCAR", "COUPE", "CAR", "TRUCK")
TILT_PIN = (0.0, -3.80, -3.30)  # head lug, relative to the trunnion
TILT_ANCHOR = (0.0, -9.60, 12.20)  # yoke rear cross-tie bracket, world

YAW_HYDRO_SPRING, YAW_HYDRO_DAMP = 2.85e8, 3.00e6

# The tilt hydro is the ONLY member that resists the head's pitch: every one of
# the head-to-yoke beams lands on trunnion_l / trunnion_r, which sit ON the
# pitch axis and therefore carry no pitch moment at all. So this one spring,
# through a 1.43 m crank lever at the bottom rung, holds 122 t of head, rotor
# and blade whose centre of mass is 2.46 m in front of the axis.
#
# At the 6.80e7 this shipped with, that is 2.06 MN of compression and 30 mm of
# squat: 1.2 deg of nose-down droop, and - worse - the crank's length curve
# L(theta) is NOT monotone. It has a minimum 10 deg nose-DOWN, so commanding
# the rest length has a SECOND solution near 19 deg nose-down where the blade
# disc is 1.3 m through the deck and the spring energy is zero. That far well
# is the global minimum, and at 6.80e7 with the ladder commanded at rest length
# only 88 kJ of barrier stood between the two - an eighth of the kinetic energy
# of a 1500 kg car at 30 m/s. A single lower-blade strike face-planted the
# machine into a pose the tilt control cannot climb out of, because past the
# dead centre dL/dtheta changes sign and "raise the head" lowers it.
#
# 1.00e9 puts the barrier at 9.5 MJ at the lowest rung (with the ladder solved
# below, which no longer parks the crank on the dead centre either), the static
# droop at 0.069 deg and the sweep's gyroscopic nod at 0.104 deg. It costs
# nothing in force - the hydro's load is set by moment equilibrium, not by k -
# and it is well inside the solver: sqrt(k / 4800 kg reduced) * (1/2000 s) is
# 0.23, against the explicit integrator's limit of 2.
#
# The damping is scaled to hold the PITCH mode's damping ratio, not the beam's:
# c * lever^2 / (2 * sqrt(K_pitch * I_pitch)) is 0.11 at 1.00e7, against 0.15 at
# the shipped pair. c * dt / m_reduced is 1.04, also inside 2.
TILT_HYDRO_SPRING, TILT_HYDRO_DAMP = 1.00e9, 1.00e7
YAW_RATE, TILT_RATE = 0.30, 0.030  # ratio units per second


# The trunnion axis: the X line through the hub station. Both trunnion nodes
# sit on it, so a head pitch is a rotation of the whole head about it.
TRUNNION_Z = HUB_Z

# The tilting body, MEASURED off the built cage's own node table rather than
# re-derived here: the head, rotor and blade groups together, and the y of
# their combined centre of mass relative to the trunnion (positive is in FRONT
# of the axis, which is what makes the head droop). The generator distributes
# these masses node by node, so a second mass model here would be a second
# machine; test_the_tilt_body_ledger_matches_the_built_cage recomputes both
# from the shipped jbeam and fails if either drifts.
TILT_BODY_KG = 127_090.0
TILT_BODY_CG_Y = 2.299479  # in front of the trunnion
TILT_BODY_CG_DZ = -0.319318  # above (+) / below (-) the trunnion
GRAVITY = 9.81


def blade_swept_floor(theta: float) -> float:
    """Lowest point the blade disc SWEEPS, over the deck, at head pitch ``theta``.

    Nose UP is positive. This is the number that decides what gets hit, and it
    is not the lowest static corner: the rotor turns, so every corner reaches
    the bottom of its own circle once per revolution. The outermost blade node
    is 15.4946 m from the hub axis - 0.105 m beyond TIP_R, because the tip
    station's chord corners sit 1.797 m off the radial line - so the static
    minimum flatters the machine by a tenth of a metre at every rung.

    For a corner at axial station ``py`` and radius ``r`` about the hub axis,
    the swept circle's centre sits at ``HUB_Z + py*sin(theta)`` and its plane
    contains the world X axis, so the circle bottoms exactly ``r*cos(theta)``
    below that centre.
    """

    s_, c = math.sin(theta), math.cos(theta)
    lowest = min(
        py * s_ - math.hypot(px, pz - TRUNNION_Z) * c
        for px, py, pz in blade_corner_cloud()
    )
    return lowest + TRUNNION_Z - DECK_Z


# The name the rest of the file and the gates use. Kept as an alias so the
# ladder, the neck-sweep check and the tests all read ONE definition of "how
# far is the blade off the deck".
blade_clearance_at_pitch = blade_swept_floor


def tilt_droop(theta: float) -> float:
    """Nose-down pitch the tilt hydro gives up under the head's own weight.

    The head's gravity moment about the trunnion is ``M*g*dz_cg/dtheta``; the
    hydro resists it through its crank lever ``dL/dtheta``, so the beam is
    compressed by ``moment / (k * lever)`` and the head rotates by that over
    the lever again. Small - 0.069 deg at the bottom rung - but it is 0.008 m
    of announced strike height, and at the spring rate this machine shipped
    with it was 1.2 deg and 0.14 m.
    """

    step = 1e-7
    lever = (
        tilt_length_ratio(theta + step) - tilt_length_ratio(theta - step)
    ) * TILT_REST_LEN / (2.0 * step)
    moment = TILT_BODY_KG * GRAVITY * (
        TILT_BODY_CG_Y * math.cos(theta) - TILT_BODY_CG_DZ * math.sin(theta)
    )
    return moment / (TILT_HYDRO_SPRING * lever * lever)


def tilt_angle_for_clearance(clear_m: float) -> float:
    """SETTLED head pitch that puts the swept blade ``clear_m`` above the deck.

    Solved numerically against ``blade_swept_floor`` because the lowest point
    of a twisted paddle migrates along the span as the head pitches; the
    bisection is exact to 1e-12 while staying obviously correct to a reader.

    The rest pose (theta 0) sweeps 0.245 m over the deck, not the 0.350 m
    BLADE_BOTTOM_CLEAR names, so even the bottom rung asks for a little nose-up:
    BLADE_BOTTOM_CLEAR sets HUB_Z off TIP_R, and the blade's corner nodes reach
    past TIP_R.
    """

    lo, hi = math.radians(-5.0), math.radians(35.0)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if blade_swept_floor(mid) < clear_m:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# 6b. The two cranks, solved rather than typed.
#
# A `hydros` row does NOT command an angle. hydros.lua sets `center` to 1 for
# a linear hydro and maps the electrics value LINEARLY ONTO THE BEAM'S LENGTH
# RATIO (`ratio = 1 + cmd * (outLimit - 1)`, written through
# setBeamLengthRefRatio); the crank then turns length into angle, and a crank
# is not linear. So every limit below is the crank's own length ratio at the
# authored angle, and every ladder entry is normalised in LENGTH.
#
# Hand-typed ratios are how this machine shipped with a sweep that ran
# -61.5 deg .. +90 deg and jammed 0.48 m past the linkage's geometric reach.
# ---------------------------------------------------------------------------
YAW_REST_LEN = math.hypot(math.hypot(YAW_CRANK_R, YAW_ANCHOR_BACK), YAW_DZ)
YAW_MAX_REACH = math.hypot(YAW_CRANK_R + YAW_ANCHOR_BACK, YAW_DZ)  # 16.930930


def yaw_length_ratio(theta: float) -> float:
    """Sweep crank length / rest length at head yaw ``theta``.

    The pin turns on YAW_CRANK_R about the vertical yaw axis; the anchor is
    fixed on the deck YAW_ANCHOR_BACK behind it and YAW_DZ below. The height
    difference is invariant under yaw, so L(t)^2 is affine in sin(t) and the
    ratio is monotone over -90 .. +90 with its GLOBAL MAXIMUM at +90 - a dead
    centre no command may ever ask for.
    """

    x = -YAW_CRANK_R * math.cos(theta)
    y = -YAW_CRANK_R * math.sin(theta)
    return (
        math.hypot(math.hypot(x, y - YAW_ANCHOR_BACK), YAW_DZ) / YAW_REST_LEN
    )


YAW_IN_LIMIT = yaw_length_ratio(-SWEEP_HALF_RAD)  # 0.783674
YAW_OUT_LIMIT = yaw_length_ratio(+SWEEP_HALF_RAD)  # 1.177223


TILT_REST_LEN = math.hypot(
    TILT_PIN[1] - TILT_ANCHOR[1], TILT_PIN[2] - (TILT_ANCHOR[2] - TRUNNION_Z)
)  # 6.372566


def tilt_length_ratio(theta: float) -> float:
    """Tilt crank length / rest length at head pitch ``theta`` (nose up +).

    The pin rides on the head and swings about the trunnion; the anchor is on
    the yoke, which does not tilt.
    """

    py, pz = TILT_PIN[1], TILT_PIN[2]
    ay, az = TILT_ANCHOR[1], TILT_ANCHOR[2] - TRUNNION_Z
    y = py * math.cos(theta) - pz * math.sin(theta)
    z = py * math.sin(theta) + pz * math.cos(theta)
    return math.hypot(y - ay, z - az) / TILT_REST_LEN


# The SETTLED pitch at each rung: what the head really sits at once the blade
# is turning and gravity has had its say.
TILT_RAD = tuple(tilt_angle_for_clearance(c) for c in TILT_CLEAR_M)
TILT_DEG = tuple(math.degrees(t) for t in TILT_RAD)  # 0.895 .. 16.528
TILT_NOM_INDEX = 0  # rung 0 is the pose the machine boots into: EVERYTHING

# ...and the pitch the hydro is COMMANDED to, which is the settled pitch plus
# the droop the head will give back. A ladder solved on a weightless head is a
# console that announces heights the machine does not strike.
TILT_CMD_RAD = tuple(t + tilt_droop(t) for t in TILT_RAD)

TILT_RATIO = tuple(tilt_length_ratio(t) for t in TILT_CMD_RAD)
TILT_OUT_LIMIT = TILT_RATIO[-1]  # 1.114465

# ---------------------------------------------------------------------------
# 7. Node weights.
#
# The pivots carry the whole machine, and blender_kit's add_node defaults to
# 125 kg. A 33-tonne rotor hung off two 125 kg nodes is a spring, not a shaft.
# ---------------------------------------------------------------------------
PIVOT_NODE_KG = 2600.0  # hub axis pair: 33 t of rotor rides here
TRUNNION_NODE_KG = 4800.0  # the whole head hangs off the trunnion pair
# Hydro endpoints. SIZED BY THE WORST LOAD THEY CARRY, not by feel: at dial 3
# with the sweep running, yawing a 2 688 410 kg.m^2 rotor turning at 4.4185
# rad/s at the crank's peak 0.3113 rad/s puts a 3.698e6 N.m gyroscopic moment
# about the TRUNNION axis - 126 % of the head's own weight moment, alternating
# once per 16 s cycle. Through the tilt crank's 1.42925 m lever that is a
# 4.647e6 N peak on the tilt pin, which at the 9600 kg this shipped with is
# 484 m/s^2: 21 % over the ceiling the file itself authors two lines down.
# Raising TILT_HYDRO_SPRING does not help - the force is set by moment
# equilibrium, not by k - so the node has to carry it.
ACTUATOR_NODE_KG = 12_800.0  # -> 363 m/s^2 at the peak, 9 % inside the ceiling
NODE_FORCE_CEIL = 400.0  # m/s^2 ceiling on every free pivot node

# ---------------------------------------------------------------------------
# 8. The wind.
#
# A giant fan that does not blow is half a mod. Downwind of the disc the
# runtime adds a per-frame velocity (never SETS it — the pack's law), inside a
# cone that yaws and tilts with the head, with a hub dead-zone because a real
# axial fan has no flow at its centre.
# ---------------------------------------------------------------------------
JET_R0, JET_HUB_DEAD = TIP_R, HUB_R
JET_SPREAD = math.tan(math.radians(14.0))
A_MAX_MPS2, FALLOFF_D0, JET_MAX_D = 8.6, 34.0, 140.0
NEAR_FADE_D = 5.0  # C1 ramp-in, so the field does not step at the disc

# ---------------------------------------------------------------------------
# 9. Body dimensions. Every value is a real 12-inch Lasko dimension x 108
# unless noted. +Y is the fan's face.
#
# The base is a FOUR-LOBED rounded square, per the reference photograph: the
# lobes are on the DIAGONALS and the four mid-edge centres are concave
# scallops. There is no "front lobe" — the front centre is a scallop, which is
# where the machine's own dial face goes.
# ---------------------------------------------------------------------------
BASE_X = BASE_Y = 26.00
LOBE_R = 10.15  # corner arc radius; centres at (+-2.85, +-2.85)
LOBE_C = 2.85
SCALLOP_CHORD, SCALLOP_SAG = 5.70, 0.55
SCALLOP_R = SCALLOP_CHORD**2 / (8 * SCALLOP_SAG) + SCALLOP_SAG / 2  # 7.659091
SCALLOP_C = 12.45 + SCALLOP_R  # 20.109091, arc centre on the axis
BASE_CROWN, BASE_DRAFT_DEG = 0.28, 3.0
# How square the footprint reads. 1.0 is a circle; the reference is a rounded
# SQUARE with proud diagonal lobes, so the outline is driven by a superellipse
# whose exponent is well above 2.
BASE_SQUARENESS = 4.4
DECK_INSET = 0.80
KERB_H = 0.22
UNDERSIDE_RECESS_D, UNDERSIDE_INSET = 0.62, 1.90
FOOT_R = 1.18
FOOT_C = 8.10  # four pads at (+-8.10, +-8.10)
RAMP_RUN, RAMP_W = 9.00, 7.20  # 2.40/9.00 -> 14.93 deg
# Where a ramp meets the deck. ONE number, used by the visible wedge AND by the
# collision cage, because they used to disagree: the wedge crested here and the
# cage crested at BASE_X/2 - 2.30, which put the drivable surface 0.41 m under
# the ramp you can see and left its outer 1.48 m with no collision at all. The
# value is the base outline's own y on the ramp centreline to within 0.14 m
# (the outline runs 12.15 m at the ramp's inboard edge and 13.27 m on its
# centreline), so the crest lands ON the slab across the ramp's full width.
RAMP_CREST_Y = 12.282
KICK_RAMP_X = 6.60  # two FRONT kick ramps
REAR_RAMP_X = -6.60  # one REAR service ramp
BAY_C = (-6.60, -8.40)  # the level console bay
BAY_W, BAY_D = 5.00, 4.20
KICKER_LIP_L, KICKER_LIP_DEG = 3.20, 18.0

# The machine's own dial face, on the FRONT scallop. Decoration: the working
# controls are the ground console below. Sized to the 1.88 m wall it sits on,
# which is the second acknowledged proportion break on this machine.
ESC_W, ESC_H = 4.80, 1.72
ESC_C_Z = 1.46
ESC_RECESS, ESC_BEZEL, ESC_TILT_DEG = 0.50, 0.16, 22.0
POINTER_L, POINTER_W, POINTER_PROUD = 0.36, 0.151, 0.09
KNOB_R = 0.19
DETENT_R = 0.52

# The working console, in the rear bay, on its -X wall.
PANEL_X = BAY_C[0] - BAY_W / 2.0  # -9.10
PANEL_W, PANEL_H = 3.60, 1.50
PANEL_Z = DECK_Z + 1.15  # 3.55
PANEL_Z0 = PANEL_Z - PANEL_H / 2.0
PANEL_PROUD = 0.12
REPEATER_R = 0.45

# Neck (fixed, part of the base), on the yaw axis at y = 0.
NECK_R_BOT, NECK_R_TOP = 4.95, 3.10
NECK_TOP_Z = 11.30
NECK_H = NECK_TOP_Z - DECK_Z  # 8.90
NECK_SWAGE_N, NECK_SWAGE_MINOR_R, NECK_SWAGE_V = 2, 0.22, (0.30, 0.62)
NECK_WARN_Z = (3.10, 5.15)
YAWPIVOT_LO_Z, YAWPIVOT_HI_Z = 8.60, 11.30

# Yoke: yaws, does not tilt.
YOKE_COLLAR_R = 3.55
YOKE_COLLAR_Z = (9.20, 10.90)
YOKE_ARM_T, YOKE_ARM_W, YOKE_HALF_SPAN = 1.51, 2.30, 6.55
YOKE_ARM_H = HUB_Z - YAWPIVOT_HI_Z  # 6.84
TRUNNION_HALF_SPAN = 5.60
TRUNNION_PIN_R = 1.05
YOKE_TIE_Y, YOKE_TIE_Z = -9.60, 12.20

# Motor housing: yaws AND tilts. Symmetric about the trunnion station.
HSG_R_FRONT, HSG_R_REAR, HSG_WALL = 5.30, 4.05, 0.24
HSG_FRONT_Y = DISC_OFFSET_Y - ROTOR_STANDOFF  # +5.70
HSG_REAR_Y = HSG_FRONT_Y - HSG_L  # -0.90
HSG_R_AT_TRUNNION = HSG_R_REAR + (HSG_R_FRONT - HSG_R_REAR) * (
    (0.0 - HSG_REAR_Y) / HSG_L
)  # the radius at the trunnion station y = 0
HSG_REAR_DOME_RISE, HSG_PARTING_V = 1.85, 0.50
HSG_LOUVRE_N, HSG_LOUVRE_PITCH, HSG_LOUVRE_DEPTH = 14, 0.62, 0.16
WARN_BAND_Y = (1.57, -0.48)
MOTOR_BELL_KG, MOTOR_BELL_Y = 39_820.0, -5.400126
BEACON_R, BEACON_AZ = 0.55, 0.60

# The amputated guard flange — see the block comment below.
FLANGE_OD, FLANGE_W, FLANGE_T = 12.70, 0.86, 0.44
RIM_BEAD_R = 0.48
BOSS_N, BOSS_R, BOSS_PROUD, BOSS_BORE_R, BOSS_PCD = 8, 0.62, 0.55, 0.27, 11.60
STUB_N, STUB_R, STUB_L, STUB_ROOT_L, STUB_BEND_DEG = 4, 0.30, 4.90, 4.30, 12.0
STICKER_W, STICKER_H = 4.20, 1.40
UV_GHOST_R = (5.49, 6.35)

# Hub cap and the crown plunger.
CAP_R, CAP_PROUD, CAP_DOME_RISE = 4.10, 1.94, 0.95
BADGE_A, BADGE_B, BADGE_PROUD = 2.10, 1.35, 0.22
BADGE_BEZEL_MAJOR, BADGE_BEZEL_MINOR = 0.8625, 0.11
BADGE_BOSS_R, BADGE_BOSS_PROUD = 0.52, 0.38
NIB_N, NIB_L, NIB_W, NIB_R = 8, 0.36, 0.14, 2.30
PLUNGER_R, PLUNGER_PROUD, PLUNGER_TRAVEL = 1.30, 1.40, 0.55
CROWN_BOSS_R = 0.90

# Blade profile detail (visual mesh only).
LE_ROLL_R, LE_ROLL_ARC_DEG, LE_ROLL_SEG = 0.32, 190.0, 12
TIP_CORNER_R, TIP_CORNER_SEG = 0.86, 16

CABLE_R, CABLE_RUN = 0.38, 42.0
STRAIN_RELIEF_L, STRAIN_RELIEF_R = 2.20, 0.72
GANTRY_W, GANTRY_STAIR_RISE = 2.60, 0.28

# ---------------------------------------------------------------------------
# 10. THE DELETED GUARD IS A WOUND, NOT AN ABSENCE.
#
# The user asked for no protective grate so cars can be launched into the
# blades. The cheap reading is "do not model the guard". The good one is that
# somebody CUT IT OFF, and the machine still carries the evidence:
#
#   * the mounting flange is still there, a bare closed ring with its rolled
#     bead, because the guard bolted to it;
#   * eight screw bosses stand proud with their bores EMPTY;
#   * four guard stub wires are snapped off 4.30 m out, bent 12 degrees, with
#     torn dark ends;
#   * and the ring of shell the guard shaded for years is the ONLY part of
#     this machine that is still factory white. Everything the sun could
#     reach has yellowed. The guard's own UV ghost is the brightest thing on
#     the fan, and it is exactly the shape of the thing that is missing.
#
# The fallen guard itself lies on the apron with its warning sticker face up.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 11. Camera. The pack default frames a 33.5 m machine from inside itself.
# ---------------------------------------------------------------------------
CAMERA_DISTANCE = 62.0


# ---------------------------------------------------------------------------
# 12. The working console.
#
# The machine's own dial is on the far face and 1.5 m up a wall; it is the
# thing you READ, not the thing you press. The controls you actually use are a
# ground-level console in a bay cut into the rear of the base, so a player on
# foot walks up to it and a player in a car sees it from the service ramp.
#
# Every cap carries its OWN frame node pair. The triggers2 box basis is
# (idX - idRef, idY - idRef), so one shared pair skews and translates the
# hitbox of every cap not co-located with it - the hover ghost floats half a
# cap away (AGENTS.md:897).
#
# ASCII titles only: BeamNG's tooltip renderer prints unicode escapes
# literally (the cannon-wash v1.48 lesson).
# ---------------------------------------------------------------------------
PANEL_Y0 = BAY_C[1] - PANEL_W / 2.0


def _plate_u(y: float) -> float:
    """Legend-plate U from a world Y. The plate runs along +-Y on the wall."""

    return (y - PANEL_Y0) / PANEL_W


def _plate_v(z: float) -> float:
    """Legend-plate V from a world Z, measured UP from the plate bottom."""

    return (z - PANEL_Z0) / PANEL_H


CAP_R_BIG, CAP_R_SMALL = 0.30, 0.22
_CAP_Z = PANEL_Z + 0.10
_LABEL_Z = PANEL_Z - 0.44

PANEL_BUTTONS = (
    {
        "id": "dial_cw",
        "title": "GALEFORCE: turn the speed dial (0 - 3 - 2 - 1)",
        "position": (PANEL_X + PANEL_PROUD, BAY_C[1] - 1.30, _CAP_Z),
        "size": 2.0 * CAP_R_BIG,
        "cap": "white",
        "label": "SPEED",
        "label_z": _LABEL_Z,
    },
    {
        "id": "dial_off",
        "title": "GALEFORCE: dial straight to 0 (OFF)",
        "position": (PANEL_X + PANEL_PROUD, BAY_C[1] - 0.45, _CAP_Z),
        "size": 2.0 * CAP_R_BIG,
        "cap": "red",
        "label": "OFF",
        "label_z": _LABEL_Z,
    },
    {
        "id": "osc",
        "title": "GALEFORCE: oscillate on / off (90 deg sweep)",
        "position": (PANEL_X + PANEL_PROUD, BAY_C[1] + 0.45, _CAP_Z),
        "size": 2.0 * CAP_R_BIG,
        "cap": "white",
        "label": "OSC",
        "label_z": _LABEL_Z,
    },
    {
        "id": "tilt_up",
        "title": "GALEFORCE: raise the blade height one rung",
        "position": (PANEL_X + PANEL_PROUD, BAY_C[1] + 1.22, _CAP_Z + 0.26),
        "size": 2.0 * CAP_R_SMALL,
        "cap": "white",
        # The two HEIGHT caps are STACKED at one Y, so the pair gets ONE
        # legend between them; two labels at the same (u, v) would overprint.
        "label": "HEIGHT",
        "label_z": _LABEL_Z,
    },
    {
        "id": "tilt_dn",
        "title": "GALEFORCE: lower the blade height one rung",
        "position": (PANEL_X + PANEL_PROUD, BAY_C[1] + 1.22, _CAP_Z - 0.30),
        "size": 2.0 * CAP_R_SMALL,
        "cap": "white",
        "label": "",
        "label_z": _LABEL_Z,
    },
    # The plunger on the housing crown is the SAME verb as `osc`, on the part
    # of the machine where an oscillating table fan's oscillation control
    # actually lives. It is 24 m up, so it is a SECOND route to the verb, not
    # the only one: reachable on foot from the service gantry, and hittable by
    # a car that has been thrown onto the crown.
    {
        "id": "plunger",
        "title": "GALEFORCE: the oscillation plunger",
        "position": (0.0, HSG_FRONT_Y, HUB_Z + 6.00),
        "size": 2.0 * PLUNGER_R,
        "cap": "chrome",
        "label": "",
        "label_z": _LABEL_Z,
    },
)

# ---------------------------------------------------------------------------
# 13. Drive-through zones.
#
# One only, and it is a SAFETY verb rather than a control: a stop pad that cuts
# the fan when you park on it. Dwell-gated at 0.40 s under 1.0 m/s, so a car
# crossing it at speed can never trip it - the gate is strictly stronger than
# making the box longer.
#
# IT IS NOT IN THE CONSOLE BAY, and that is the whole point of where it is.
# Centred on the bay it was exactly the floor you have to stop on to reach the
# controls: 3.40 m of x-window over a 1.9 m car on the rear ramp's own
# centreline, 5.60 m of y-window bracketing the console's own station. Every
# return trip to the dial cancelled the setting 0.4 s after you pressed it, and
# no amount of resetting the accumulator on a press fixed that - the car is
# still parked, still slow, still contained on the next frame. So the pad moved
# 9.00 m across the deck, clear of the rear service ramp's x -10.20 .. -3.00
# footprint and 9.8 m from the nearest console cap, where "park on the pad" is
# a thing you choose to do rather than the only way to reach a button.
#
# MIN_CONTAINS_DIMENSIONS in tests/test_giant_props_pack.py is (2.9, 4.5, 3.0):
# a Contains trigger must be able to hold a compact car whole.
# ---------------------------------------------------------------------------
STOP_PAD_C = (BAY_C[0] + 9.00, BAY_C[1])  # (2.40, -8.40), on the open deck
TRIGGERS = {
    "stop_pad": {
        "mode": "Contains",
        "center": (STOP_PAD_C[0], STOP_PAD_C[1], DECK_Z + 1.60),
        "dimensions": (3.40, 5.60, 3.20),
    },
}

STOP_PAD_DWELL_S = 0.40
STOP_PAD_SPEED_MAX = 1.0

# ---------------------------------------------------------------------------
# 14. Palette.
#
# Every entry is srgb-encoded. texture_kit writes linear floats straight to
# bytes unless told otherwise, so an authored linear 0.043 lands as byte 11 and
# the engine decodes it as 0.0035 - twelve times darker than authored. The kit
# is opt-in because twenty shipped mods were tuned against the un-encoded
# output; the fan has never shipped, so it has no look to preserve.
#
# With srgb on, every colour-shaped parameter of every family must be stated,
# defaults included: a parameter left at its default is still a raw linear
# number that the encode then makes about three times lighter (AGENTS.md).
# ---------------------------------------------------------------------------
PALETTE = {
    # The guard's UV ghost: the ONLY factory-white shell left on the machine.
    f"{MOD_ID}_shell_white": {
        "texture": {
            "family": "molded_nylon",
            "size": 1024,
            "normal_strength": 2.2,
            "srgb": True,
            "params": {
                "base": (0.905, 0.900, 0.878),
                "grain": 0.10,
                "rough": 0.42,
                "sheen": 0.55,
            },
        },
        "color": [0.905, 0.900, 0.878, 1.0],
        "metallic": 0.0,
        "roughness": 0.42,
    },
    # Everything the sun could reach.
    f"{MOD_ID}_shell_yellowed": {
        "texture": {
            "family": "molded_nylon",
            "size": 1024,
            "normal_strength": 2.2,
            "srgb": True,
            "params": {
                "base": (0.862, 0.826, 0.700),
                "grain": 0.10,
                "rough": 0.46,
                "sheen": 0.45,
            },
        },
        "color": [0.862, 0.826, 0.700, 1.0],
        "metallic": 0.0,
        "roughness": 0.46,
    },
    # The blade shells. ALPHA 1.0, and there is no argument about it: this
    # machine has no glass on it. prop_builder turns any alpha below 1.0 into
    # `translucent: true, alphaRef: 0`, which put all three 12.19 m paddles,
    # the hub disc and the four torn guard stubs into the blended pass at 62%
    # opacity - you could read the flange bolt bosses through the blade that is
    # about to eat your car. 0.62 is BLADE_THICK; it landed in the RGBA slot.
    f"{MOD_ID}_blade_smoke": {
        "texture": {
            "family": "molded_nylon",
            "size": 1024,
            "normal_strength": 1.2,
            "srgb": True,
            "params": {
                "base": (0.352, 0.340, 0.322),
                "grain": 0.22,
                "rough": 0.28,
                "sheen": 0.60,
            },
        },
        "color": [0.352, 0.340, 0.322, 1.0],
        "metallic": 0.0,
        "roughness": 0.28,
        "material": {"castShadows": True},
    },
    f"{MOD_ID}_blade_smoke_dark": {
        "texture": {
            "family": "molded_nylon",
            "size": 1024,
            "normal_strength": 1.2,
            "srgb": True,
            "params": {
                "base": (0.246, 0.238, 0.225),
                "grain": 0.22,
                "rough": 0.28,
                "sheen": 0.60,
            },
        },
        "color": [0.246, 0.238, 0.225, 1.0],
        "metallic": 0.0,
        "roughness": 0.28,
        "material": {"castShadows": True},
    },
    # A torn alpha-cut paint smear on the leading blade: the mark a car leaves
    # on the thing that hit it. c1 == c2 kills stripe_decal's diagonal term, so
    # what survives is the family's own wear alpha, and the three `seams` are
    # hard 0.30 m gouges through it.
    f"{MOD_ID}_blade_transfer": {
        "texture": {
            "family": "stripe_decal",
            "size": 512,
            "srgb": True,
            "params": {
                "c1": (0.62, 0.14, 0.11),
                "c2": (0.62, 0.14, 0.11),
                "width_m": 2.4,
                "height_m": 0.9,
                "period_m": 0.62,
                "seams": (-0.70, 0.05, 0.78),
                "seam_width": 0.30,
            },
        },
        "color": [0.62, 0.14, 0.11, 1.0],
        "metallic": 0.0,
        "roughness": 0.34,
    },
    f"{MOD_ID}_chrome": {
        "texture": {
            "family": "brushed_metal",
            "size": 512,
            "srgb": True,
            "params": {"base": (0.885, 0.895, 0.920), "rough": 0.10},
        },
        "color": [0.885, 0.895, 0.920, 1.0],
        "metallic": 1.0,
        "roughness": 0.10,
        "material": {"dynamicCubemap": True},
    },
    # The machine's own face: 0 at the top, then 3, 2, 1 CLOCKWISE. That is the
    # real Lasko layout, and it is why the first click from OFF is full power.
    f"{MOD_ID}_dial_face": {
        "texture": {
            "family": "panel_legend",
            "size": 1024,
            "normal_strength": 3.0,
            "srgb": True,
            "params": {
                "aspect": ESC_W / ESC_H,
                "base": (0.412, 0.386, 0.342),
                "ink": (0.118, 0.110, 0.100),
                "title": "",
                "frame": False,
                "label_scale": 0.150,
                "labels": (
                    (0.500000, 0.802326, "0"),
                    (0.608333, 0.500000, "3"),
                    (0.500000, 0.197674, "2"),
                    (0.391667, 0.500000, "1"),
                ),
            },
        },
        "color": [0.412, 0.386, 0.342, 1.0],
        "metallic": 0.0,
        "roughness": 0.52,
    },
    f"{MOD_ID}_panel_legend": {
        "texture": {
            "family": "panel_legend",
            "size": 1024,
            "normal_strength": 2.6,
            "srgb": True,
            "params": {
                "title": BRAND,
                "aspect": PANEL_W / PANEL_H,
                "base": (0.412, 0.386, 0.342),
                "ink": (0.118, 0.110, 0.100),
                "label_scale": 0.085,
                "labels": [],
            },
        },
        "color": [0.412, 0.386, 0.342, 1.0],
        "metallic": 0.0,
        "roughness": 0.44,
    },
    f"{MOD_ID}_cap_red": {
        "texture": {
            "family": "bakelite",
            "size": 512,
            "normal_strength": 2.0,
            "srgb": True,
            "params": {"base": (0.72, 0.08, 0.06)},
        },
        "color": [0.72, 0.08, 0.06, 1.0],
        "metallic": 0.05,
        "roughness": 0.38,
    },
    f"{MOD_ID}_cap_white": {
        "texture": {
            "family": "bakelite",
            "size": 512,
            "normal_strength": 2.0,
            "srgb": True,
            "params": {"base": (0.88, 0.89, 0.90)},
        },
        "color": [0.88, 0.89, 0.90, 1.0],
        "metallic": 0.05,
        "roughness": 0.38,
    },
    # The night read: a 33.5 m machine must not be a black cutout.
    f"{MOD_ID}_beacon_lens": {
        "texture": {
            "family": "molded_nylon",
            "size": 512,
            "normal_strength": 1.6,
            "srgb": True,
            "params": {
                "base": (0.36, 0.05, 0.04),
                "grain": 0.18,
                "rough": 0.32,
                "sheen": 0.60,
            },
        },
        "color": [0.36, 0.05, 0.04, 1.0],
        "metallic": 0.0,
        "roughness": 0.32,
    },
    # type_aspect pre-compresses the type by the badge's own aspect, so the
    # stretch a 2.10 x 1.35 ellipse applies to a SQUARE map puts it back.
    # Without it the "GF" ships 55.6% too wide.
    f"{MOD_ID}_hub_badge": {
        "texture": {
            "family": "stamped_mark",
            "size": 512,
            "normal_strength": 4.0,
            "srgb": True,
            "params": {
                "text": "GF",
                "base": (0.862, 0.826, 0.700),
                "fit_circle": True,
                "type_aspect": BADGE_A / BADGE_B,
                "ring": True,
                "mark_span": 0.58,
                "mark_height": 0.40,
                "bead_band": (0.900, 0.975),
                "groove_band": (0.860, 0.898),
                "pocket_r": 0.880,
                "depth": 0.62,
                "rough": 0.22,
                "wear": 0.10,
            },
        },
        "color": [0.862, 0.826, 0.700, 1.0],
        "metallic": 0.15,
        "roughness": 0.22,
    },
    # Moulded INTO the shell, so ink == base: it reads by relief alone, the way
    # real moulded-in warning text does.
    f"{MOD_ID}_moulded_warning": {
        "texture": {
            "family": "panel_legend",
            "size": 2048,
            "normal_strength": 5.0,
            "srgb": True,
            "params": {
                "aspect": 6.0,
                "base": (0.862, 0.826, 0.700),
                "ink": (0.862, 0.826, 0.700),
                "title": "",
                "frame": False,
                "label_scale": 0.230,
                "labels": (
                    (0.5, 0.62, "CAUTION - DO NOT OPERATE WITHOUT GUARD"),
                    (0.5, 0.22, "KEEP HANDS AND OBJECTS CLEAR OF BLADES", 0.94),
                    (0.5, 0.86, BRAND, 1.30),
                ),
            },
        },
        "color": [0.862, 0.826, 0.700, 1.0],
        "metallic": 0.0,
        "roughness": 0.46,
    },
    f"{MOD_ID}_bore_shadow": {
        "texture": {
            "family": "molded_nylon",
            "size": 512,
            "srgb": True,
            "params": {
                "base": (0.045, 0.045, 0.050),
                "grain": 0.30,
                "rough": 0.90,
                "sheen": 0.35,
            },
        },
        "color": [0.045, 0.045, 0.050, 1.0],
        "metallic": 0.0,
        "roughness": 0.90,
    },
    f"{MOD_ID}_foot_rubber": {
        "texture": {
            "family": "rubber_tread",
            "size": 512,
            "srgb": True,
            "params": {"base": (0.085, 0.082, 0.080), "pattern": "bars", "rough": 0.78},
        },
        "color": [0.085, 0.082, 0.080, 1.0],
        "metallic": 0.0,
        "roughness": 0.78,
    },
    f"{MOD_ID}_machine_steel": {
        "texture": {
            "family": "machined_steel",
            "size": 512,
            "srgb": True,
            "params": {"base": (0.44, 0.46, 0.49), "rough": 0.34},
        },
        "color": [0.44, 0.46, 0.49, 1.0],
        "metallic": 0.88,
        "roughness": 0.34,
    },
    f"{MOD_ID}_gantry_steel": {
        "texture": {
            "family": "steel_worn",
            "size": 1024,
            "srgb": True,
            "params": {"base": (0.50, 0.53, 0.57), "rough": 0.44},
        },
        "color": [0.50, 0.53, 0.57, 1.0],
        "metallic": 0.80,
        "roughness": 0.44,
    },
    f"{MOD_ID}_hazard": {
        "texture": {
            "family": "hazard_chevron",
            "size": 512,
            "srgb": True,
            "params": {"c1": (0.95, 0.75, 0.08), "c2": (0.12, 0.12, 0.13)},
        },
        "color": [0.95, 0.75, 0.08, 1.0],
        "metallic": 0.0,
        "roughness": 0.45,
    },
}

# The console legend is printed FROM the button table, so the labels can never
# drift from the caps they name.
PALETTE[f"{MOD_ID}_panel_legend"]["texture"]["params"]["labels"] = [
    [_plate_u(b["position"][1]), _plate_v(b["label_z"]), b["label"], 0.85]
    for b in PANEL_BUTTONS
    if b["id"] != "plunger" and b["label"]
]

# AGENTS.md policy (2026-08-07), after three invisible-surface bugs: the
# winding question was retired wholesale rather than fixed per surface. A 12 m
# single-sided blade shell is invisible from one side in game and perfect in
# every Blender render.
for _entry in PALETTE.values():
    _entry["double_sided"] = True


# ---------------------------------------------------------------------------
# 15. UV densities, in METRES PER TILE, keyed by material.
#
# The Cannon Car Wash "tiny blocks" lesson: a primitive's default UV stretches
# one tile across the whole object, so a 32 m housing circumference and a 2 m
# box land two orders of texel density apart across a visible seam. Every
# large surface is mapped in metres.
#
# The four ONE-TILE materials are exempt and MUST be: their texture is a single
# printed artwork, not a tiling pattern, and tiling a legend prints it twice.
# ---------------------------------------------------------------------------
UV_METERS = {
    f"{MOD_ID}_shell_white": (2.60, 2.60),
    f"{MOD_ID}_shell_yellowed": (2.60, 2.60),
    f"{MOD_ID}_blade_smoke": (3.10, 3.10),
    f"{MOD_ID}_blade_smoke_dark": (3.10, 3.10),
    f"{MOD_ID}_chrome": (1.40, 1.40),
    f"{MOD_ID}_cap_red": (0.60, 0.60),
    f"{MOD_ID}_cap_white": (0.60, 0.60),
    f"{MOD_ID}_beacon_lens": (1.10, 1.10),
    f"{MOD_ID}_bore_shadow": (0.55, 0.55),
    f"{MOD_ID}_foot_rubber": (1.20, 1.20),
    f"{MOD_ID}_machine_steel": (2.20, 2.20),
    f"{MOD_ID}_gantry_steel": (2.20, 2.20),
    f"{MOD_ID}_hazard": (2.10, 2.10),
    f"{MOD_ID}_blade_transfer": (2.40, 0.90),
}

# One tile, never metric: a printed artwork tiled twice is printed twice.
ONE_TILE_MATERIALS = {
    f"{MOD_ID}_dial_face",
    f"{MOD_ID}_panel_legend",
    f"{MOD_ID}_hub_badge",
    f"{MOD_ID}_moulded_warning",
}


# ---------------------------------------------------------------------------
# 16. Cage node names the authored JBeam sections reference.
#
# `build_jbeam` prefixes every node id with MOD_ID, so the authored sections
# must spell the FULL prefixed name - which is exactly the string
# `CageBuilder.add_node` returns. `check_jbeam_section_refs` validates every
# one of these against the measured cage before the jbeam is written, so a
# node renamed in Blender is a build error rather than a rotator the engine
# silently deletes.
# ---------------------------------------------------------------------------
N = MOD_ID  # local alias, purely to keep the tables below readable

HUBAXIS_FRONT = f"{N}_hubaxis_front"
HUBAXIS_REAR = f"{N}_hubaxis_rear"
YOKE_ARM_R = f"{N}_yoke_arm_r_lo"
YAW_CRANK_PIN = f"{N}_yaw_crank_pin"
YAW_ANCHOR = f"{N}_yaw_anchor"
TILT_PIN_NODE = f"{N}_tilt_pin"
TILT_ANCHOR_NODE = f"{N}_tilt_anchor"
MOTOR_REACTION = (f"{N}_hsg_rr_0", f"{N}_hsg_rr_1", f"{N}_hsg_rr_2")

GROUP_ROTOR = f"{N}_rotor"  # the DRIVE COLLAR only
GROUP_BLADE = f"{N}_blade"  # the three blades, dragged by beams
GROUP_HEAD = f"{N}_head"
GROUP_YOKE = f"{N}_yoke"

# ---------------------------------------------------------------------------
# 17. The authored JBeam sections.
#
# These are the mechanisms the cage compiler deliberately does not synthesise.
# The shapes follow stock's, the VALUES are all authored here.
# ---------------------------------------------------------------------------
JBEAM_SECTIONS = {
    # `allowedIgnitionLevels: [2]` keeps the motor energised: stock puts it on
    # the spinner's top-level part for exactly this reason.
    "electrics": {"allowedIgnitionLevels": [2]},
    # `radius` is NOT optional. wheels.lua sets dynamicRadius from it and
    # evaluates wheelAVdir * dynamicRadius every graphics frame; a nil radius
    # is arithmetic-on-nil, every frame, forever.
    "components": {"radius": TIP_R},
    "powertrain": [
        ["type", "name", "inputName", "inputIndex"],
        # THE ROOT DEVICE. Stock's spinner gets its motor from a slotted part
        # (`large_motor`); this prop has no `slots` section, so the device has
        # to be declared here or it does not exist. powertrain.lua builds
        # devices ONLY from rows of this table, merges the top-level `motor`
        # block into the device NAMED motor, and only sets a child's `parent`
        # when `deviceLookup[inputName]` resolves. Without this row the shaft
        # is an orphan root, shaft.lua forces mode "disconnected" and zeroes
        # propulsionTorque every step, `powertrain.getDevice("motor")` returns
        # nil, and the controller's updateGFX early-returns - which kills
        # power, sweep, tilt and the wind in one line.
        ["electricMotor", "motor", "", 0],
        [
            "shaft",
            "shaft",
            "motor",
            1,
            {
                "gearRatio": GEAR_RATIO,
                "friction": SHAFT_FRICTION,
                "connectedWheel": "fan_rotor",
            },
        ],
    ],
    "motor": {
        # An authored curve for a 33 t rotor: flat to a third of redline, then
        # falling, which is what a big squirrel-cage induction motor does.
        # Sized so setting 3 sits at 96% of redline against the rotor's own
        # aero drag - a fan's load IS its blades.
        "torque": [
            ["rpm", "torque"],
            [0, 62000],
            [300, 62000],
            [600, 60500],
            [900, 52000],
            [1200, 41000],
            [1500, 32000],
            [1760, 26500],
        ],
        "electricsThrottleName": "throttle",
        "electricsThrottleFactorName": "throttleFactor",
        "maxRPM": MOTOR_MAX_RPM,
        "inertia": MOTOR_INERTIA,
        "friction": 22.0,
        "dynamicFriction": 0.0009,
        "electricalEfficiency": 0.912,
        "torqueReactionNodes:": list(MOTOR_REACTION),
        "uiName": "GALEFORCE 3-phase",
        "soundConfig": "motorSound",
    },
    "motorSound": {"sampleName": "ElectricSpinner_01", "mainGain": -2},
    "rotators": [
        ["name", "[group]:", "node1:", "node2:", "nodeArm:", "wheelDir"],
        {"radius": TIP_R},
        # brakeSpring is a MULTIPLIER on brakeTorque, not a stiffness, and the
        # engine's brakeDamp default is ZERO - an undamped brake spring on
        # 2.3e6 kg.m^2 rings.
        {"brakeTorque": BRAKE_TORQUE, "brakeSpring": BRAKE_SPRING},
        {"brakeDamp": BRAKE_DAMP},
        # rotatorType defaults to "wheel", which makes useDefaultBrakeInput
        # true: without this the player's own parking brake grabs the rotor.
        {"parkingTorque": 0},
        {"selfCollision": False},
        [
            "fan_rotor",
            [GROUP_ROTOR],
            HUBAXIS_FRONT,
            HUBAXIS_REAR,
            YOKE_ARM_R,
            -1,
        ],
    ],
    "controller": [["fileName"], ["giantFan", {}]],
    # Sweep and tilt: linear hydros on a crank. The crank's lever arm supplies
    # the joint stiffness, so beamSpring is sized against the moment each joint
    # really carries (see TILT_HYDRO_SPRING above).
    #
    # NO beamLimitSpring / beamLimitDamp here, and none is wanted: jbeam's
    # stage2 only reads those two in addBeamByData's BEAM_BOUNDED branch, and a
    # hydro is beamType BEAM_HYDRO, which falls through to the plain linear
    # path. Authoring them stated a bound the engine does not apply.
    #
    # autoCenterRate is stated EXPLICITLY as a positive number, not zero:
    # hydros.lua takes the autocentre branch whenever the command equals the
    # input centre, which the SWEEP does every time it is switched off. A zero
    # rate there would freeze the head wherever the sweep stopped.
    "hydros": [
        ["id1:", "id2:"],
        {"beamDeform": "FLT_MAX", "beamStrength": "FLT_MAX"},
        [
            YAW_CRANK_PIN,
            YAW_ANCHOR,
            {
                "beamSpring": YAW_HYDRO_SPRING,
                "beamDamp": YAW_HYDRO_DAMP,
                "inputSource": "fanSweep",
                # SOLVED from the crank, never typed: the ratio the linkage
                # really has at -/+SWEEP_HALF_RAD. Deliberately asymmetric
                # about 1.0 - hydros.lua builds separate multIn/multOut about
                # center = 1, so a crank's own asymmetry is handled natively.
                "inLimit": YAW_IN_LIMIT,
                "outLimit": YAW_OUT_LIMIT,
                "inRate": YAW_RATE,
                "outRate": YAW_RATE,
                "inputFactor": 1,
                "autoCenterRate": YAW_RATE,
            },
        ],
        [
            TILT_PIN_NODE,
            TILT_ANCHOR_NODE,
            {
                "beamSpring": TILT_HYDRO_SPRING,
                "beamDamp": TILT_HYDRO_DAMP,
                "inputSource": "fanTilt",
                # The whole tilt ladder is on the OUT side - every rung
                # commands the crank longer than its rest length - so the IN
                # side is never reached. 1.0 is the honest statement of that:
                # this hydro never pulls the head below its rest pose.
                "inLimit": 1.0,
                # The crank's length ratio at the TOP rung. TILT_INPUT is
                # normalised against the same span, so rung i lands on exactly
                # TILT_CLEAR_M[i].
                "outLimit": TILT_OUT_LIMIT,
                "inRate": TILT_RATE,
                "outRate": TILT_RATE,
                "inputFactor": 1,
                "autoCenterRate": TILT_RATE,
            },
        ],
    ],
}

# ---------------------------------------------------------------------------
# 18. The vehicle-side controller.
#
# Written here, not adapted from stock: AGENTS.md:357 forbids copying BeamNG
# JBeam or Lua into this repository. The main-controller INTERFACE is an API
# and is implemented; every line of the body is authored.
#
# It does four things stock's spinner controller does not:
#
#   1. reads the rotor's speed off the MOTOR and divides by the gear ratio,
#      exactly once. powertrain/shaft.lua has already multiplied the rotator's
#      raw angular velocity by `wheelDirection`, so a controller that applies
#      wheelDir again squares it back to raw and inverts the whole speed loop;
#   2. RAMPS the brake instead of slamming it. Stock sets desiredBrake = 1
#      whenever the measured ratio overshoots the target by 0.05, so every
#      dial DOWN-step is a full-torque stop. On this machine that reads as the
#      rotor hitting a wall; a 33 t rotor should take 25 s to wind down;
#   3. drives `electrics.values.fanSweep` and `fanTilt`, which are the two
#      hydro input sources;
#   4. takes its setpoints per-vehicle. Stock's `onGameplayEvent` is a
#      BROADCAST with no vehicle filter, so two of the same prop on one map
#      move together. The GE runtime reaches this controller through
#      `vehicle:queueLuaCommand`, which targets one vehicle by construction.
# ---------------------------------------------------------------------------
GIANT_FAN_CONTROLLER_LUA = """
-- GALEFORCE GF-3600 rotor controller.
--
-- Authored for this mod. The BeamNG main-controller interface is implemented
-- because the engine requires it; none of the body is copied from stock.

local M = {}

M.type = "main"
M.relevantDevice = nil
M.throttle = 0
M.brake = 0
M.clutchRatio = 0
M.engineInfo = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "manual", 0, 0, 0, 1}

local abs, min, max, floor = math.abs, math.min, math.max, math.floor

local AV_TO_RPM = 9.549296596425384

-- Authored ladders, mirrored from spec.py. The Lua side never derives them.
local DIAL_RATIO = {@DIAL_RATIO@}
local DIAL_ORDER = {@DIAL_ORDER@}
local TIP_MPS    = {@TIP_MPS@}
local TILT_INPUT = {@TILT_INPUT@}
local TILT_CLEAR = {@TILT_CLEAR@}

local GEAR_RATIO      = @GEAR_RATIO@
local SWEEP_PERIOD_S  = @SWEEP_PERIOD_S@
local SWEEP_ARM_S     = @SWEEP_ARM_S@
local DOWNSTEP_BRAKE  = @DOWNSTEP_BRAKE@
local PARK_ENTRY_AV   = @PARK_ENTRY_AV@
local BRAKE_RAMP_S    = 1.60   -- how long the brake takes to reach its setting

local motor, rotator = nil, nil
local invMotorMaxAV = 0

local dial = 1          -- index into DIAL_ORDER; 1 == the OFF detent
local tiltRung = 1      -- index into TILT_INPUT; 1 == the lowest strike height
local sweeping = false
local sweepClock = 0.0
local sweepArm = 0.0

local targetRatio = 0.0
local ratioError = 0.0
local integral = 0.0
local desiredBrake = 0.0
local brakeCommand = 0.0

-- The rotor's angular velocity IN ITS OWN SENSE.
--
-- `wheels.wheelRotators[i].angularVelocity` is RAW: a wheelDir -1 rotator
-- reports a negative speed while visibly turning forwards. But this reads the
-- speed off the MOTOR, and powertrain/shaft.lua's wheelShaftUpdateVelocity has
-- already signed it:
--
--     device.outputAV1 = device.wheel.angularVelocity * device.wheelDirection
--     device.inputAV   = device.outputAV1 * device.gearRatio
--     motor.outputAV1  = device.inputAV
--
-- so motor.outputAV1 is rawAV * wheelDir * gearRatio and dividing by the gear
-- ratio is the whole correction. Applying wheelDir a SECOND time here squares
-- it back to the raw value, which inverts the sign of the entire speed loop:
-- `ratio` goes negative, `ratioError` can never fall below its setpoint, the
-- throttle pins at 1.0 at every dial setting, the down-step brake branch
-- becomes unreachable, and `fanTipSpeed` reaches the GE runtime negative,
-- where applyWind's `if speed < 1.0 then return end` switches the jet off for
-- good. Read it once, here, and nowhere else.
local function rotorAV()
  if not motor then return 0.0 end
  return (motor.outputAV1 or 0.0) / GEAR_RATIO
end

local function dialSetting()
  return DIAL_ORDER[dial] or 0
end

local function applySetpoints()
  targetRatio = DIAL_RATIO[dialSetting() + 1] or 0.0
end

local function setDial(index)
  if type(index) ~= "number" then return end
  index = floor(index)
  if index < 1 then index = 1 end
  if index > #DIAL_ORDER then index = #DIAL_ORDER end
  dial = index
  applySetpoints()
end

local function stepDial()
  -- 0 -> 3 -> 2 -> 1 -> 0. The real Lasko detent order, which is why the
  -- first click from OFF is full power.
  setDial(dial % #DIAL_ORDER + 1)
end

local function dialOff()
  setDial(1)
end

local function setTiltRung(index)
  if type(index) ~= "number" then return end
  index = floor(index)
  if index < 1 then index = 1 end
  if index > #TILT_INPUT then index = #TILT_INPUT end
  tiltRung = index
end

local function stepTilt(delta)
  setTiltRung(tiltRung + (delta or 0))
end

local function setSweep(on)
  local wanted = on and true or false
  if wanted == sweeping then return end
  sweeping = wanted
  if sweeping then
    -- The dog clutch has to engage before the head moves. That pause is the
    -- anticipation beat: the plunger goes down and NOTHING happens for a
    -- moment.
    sweepArm = SWEEP_ARM_S
  end
end

local function toggleSweep()
  setSweep(not sweeping)
end

local function status()
  local av = rotorAV()
  return {
    dial = dialSetting(),
    tilt_rung = tiltRung,
    tilt_clear = TILT_CLEAR[tiltRung] or 0.0,
    sweeping = sweeping,
    sweep_phase = sweepClock / SWEEP_PERIOD_S,
    omega = av,
    tip_mps = av * @TIP_R@,
    tip_target = TIP_MPS[dialSetting() + 1] or 0.0,
    rpm = abs(av) * AV_TO_RPM,
  }
end

local function updateWheelsIntermediate(dt)
  if rotator then
    rotator.desiredBrakingTorque = (rotator.brakeTorque or 0) * brakeCommand
  end
end

local function updateGFX(dt)
  if not motor then return end

  local av = rotorAV()
  local ratio = av * GEAR_RATIO * invMotorMaxAV

  -- Speed control: proportional plus a bounded integral. The integral is what
  -- holds the setting against the rotor's own aero drag, which on a fan is
  -- most of the load.
  ratioError = targetRatio - ratio
  if targetRatio > 0.001 then
    integral = min(max(integral + ratioError * dt * 0.9, 0.0), 1.0)
  else
    integral = 0.0
  end
  local throttle = min(max(ratioError * 3.2 + integral, 0.0), 1.0)

  -- The brake. A dial DOWN-step gets a PARTIAL brake and a ramp, so a 33 t
  -- rotor winds down over ~25 s instead of stopping like it hit a wall.
  local wantBrake = 0.0
  if targetRatio < 0.001 then
    throttle = 0.0
    wantBrake = (abs(av) > PARK_ENTRY_AV) and 1.0 or 0.35
  elseif ratio - targetRatio > 0.02 then
    throttle = 0.0
    wantBrake = DOWNSTEP_BRAKE
  end
  local step = dt / BRAKE_RAMP_S
  if wantBrake > brakeCommand then
    brakeCommand = min(brakeCommand + step, wantBrake)
  else
    brakeCommand = max(brakeCommand - step, wantBrake)
  end

  electrics.values.throttle = throttle
  electrics.values.rpm = abs(av) * AV_TO_RPM * GEAR_RATIO
  electrics.values.fanDial = dialSetting()
  electrics.values.fanTipSpeed = av * @TIP_R@

  -- The sweep. A sinusoid in the hydro's own ratio units, centred on 1.0.
  if sweepArm > 0.0 then
    sweepArm = max(0.0, sweepArm - dt)
  elseif sweeping then
    sweepClock = (sweepClock + dt) % SWEEP_PERIOD_S
  end
  local target
  if sweeping and sweepArm <= 0.0 then
    target = math.sin(2.0 * math.pi * sweepClock / SWEEP_PERIOD_S)
  else
    -- Not sweeping: drive the command back to centre and let the hydro's own
    -- autoCenterRate carry the head home. Never leave it where it stopped.
    target = 0.0
    sweepClock = 0.0
  end
  electrics.values.fanSweep = target
  electrics.values.fanTilt = TILT_INPUT[tiltRung] or 0.0

  M.engineInfo[1] = electrics.values.rpm
  M.engineInfo[2] = @MOTOR_MAX_RPM@
  M.engineInfo[5] = electrics.values.rpm
  M.engineInfo[6] = string.format("%d", dialSetting())
end

local function reset()
  dial = 1
  tiltRung = 1
  sweeping = false
  sweepClock = 0.0
  sweepArm = 0.0
  integral = 0.0
  desiredBrake = 0.0
  brakeCommand = 0.0
  applySetpoints()
  electrics.values.throttle = 0
  electrics.values.fanSweep = 0.0
  electrics.values.fanTilt = TILT_INPUT[1] or 0.0
  electrics.values.fanDial = 0
  electrics.values.fanTipSpeed = 0.0
end

local function init(jbeamData)
  motor = powertrain.getDevice(jbeamData.motorName or "motor")
  if motor then
    invMotorMaxAV = 1.0 / (motor.maxAV or 1.0)
  end
  local wanted = jbeamData.rotatorName or "fan_rotor"
  -- wheelRotators is ZERO-indexed with wheelRotatorCount entries. Stock's own
  -- loop runs 0..count and leans on the nil check; this one does not overrun.
  for i = 0, (wheels.wheelRotatorCount or 0) - 1 do
    local r = wheels.wheelRotators[i]
    if r and r.name == wanted then
      rotator = r
      break
    end
  end
  reset()
end

local function setEngineIgnition(enabled)
  if motor then motor:setIgnition(enabled and 1 or 0) end
end

local function sendTorqueData()
  if motor and playerInfo.firstPlayerSeated then motor:sendTorqueData() end
end

M.init = init
M.reset = reset
M.updateGFX = updateGFX
M.updateWheelsIntermediate = updateWheelsIntermediate

-- Mandatory main-controller API.
M.shiftUp = nop
M.shiftDown = nop
M.shiftToGearIndex = nop
M.cycleGearboxModes = nop
M.setGearboxMode = nop
M.setStarter = nop
M.setEngineIgnition = setEngineIgnition
M.setFreeze = nop
M.vehicleActivated = nop
M.sendTorqueData = sendTorqueData

-- The per-vehicle control surface. The GE runtime calls these through
-- vehicle:queueLuaCommand, so they can only ever affect THIS fan.
M.setDial = setDial
M.stepDial = stepDial
M.dialOff = dialOff
M.setTiltRung = setTiltRung
M.stepTilt = stepTilt
M.setSweep = setSweep
M.toggleSweep = toggleSweep
M.status = status

return M
"""


def _lua_list(values) -> str:
    return ", ".join(repr(float(v)) for v in values)


def _tilt_input_ratios() -> tuple[float, ...]:
    """Hydro command per tilt rung, in the hydro's own input units.

    hydros.lua builds `center` = 1 from the jbeam defaults (inputCenter 0,
    inputInLimit -1, inputOutLimit 1) and then maps a command onto the beam's
    length ratio as `ratio = 1 + cmd * (outLimit - 1)` for cmd >= 0. So the
    normalisation has to be about the beam's own REST length, ratio 1.0 - not
    about the bottom rung. Every rung of this ladder commands the crank LONGER
    than rest (even the bottom one asks for 0.9 deg of nose-up, because the
    blade's corner nodes reach past TIP_R and the rest pose only sweeps 0.245 m
    over the deck), so the whole ladder lives on the hydro's OUT side and the
    IN side is never commanded at all.

    The ladder is linear in LENGTH, not in angle. hydros.lua maps the command
    straight onto the length ratio and the CRANK does the length-to-angle
    conversion, so dividing the angle span evenly asks for the wrong length at
    every intermediate rung - which is how every rung above the first came to
    strike 1.0 .. 1.5 m higher than the height it announces.
    """

    span = TILT_OUT_LIMIT - 1.0
    if span <= 0.0:
        return tuple(0.0 for _ in TILT_RATIO)
    return tuple((r - 1.0) / span for r in TILT_RATIO)


TILT_INPUT = _tilt_input_ratios()

VEHICLE_CONTROLLERS = {
    "giantFan": (
        GIANT_FAN_CONTROLLER_LUA.replace("@DIAL_RATIO@", _lua_list(DIAL_RATIO))
        .replace("@DIAL_ORDER@", ", ".join(str(int(v)) for v in DIAL_ORDER))
        .replace("@TIP_MPS@", _lua_list(TIP_MPS))
        .replace("@TILT_INPUT@", _lua_list(TILT_INPUT))
        .replace("@TILT_CLEAR@", _lua_list(TILT_CLEAR_M))
        .replace("@GEAR_RATIO@", repr(float(GEAR_RATIO)))
        .replace("@SWEEP_PERIOD_S@", repr(float(SWEEP_PERIOD_S)))
        .replace("@SWEEP_ARM_S@", repr(float(SWEEP_ARM_S)))
        .replace("@DOWNSTEP_BRAKE@", repr(float(DOWNSTEP_BRAKE)))
        .replace("@PARK_ENTRY_AV@", repr(float(PARK_ENTRY_AV)))
        .replace("@MOTOR_MAX_RPM@", repr(float(MOTOR_MAX_RPM)))
        .replace("@TIP_R@", repr(float(TIP_R)))
    )
}


# ---------------------------------------------------------------------------
# 19. The vehicle -> GE telemetry push.
#
# The wind field lives on the GE side (it acts on other vehicles), but the
# machine's state lives in the vehicle controller. Rather than have GE guess,
# the vehicle pushes its real state up on a cadence, so the field is driven by
# what the rotor is ACTUALLY doing - including the spin-up lag and any bog
# from eating a car.
# ---------------------------------------------------------------------------
VEHICLE_LUA_EXTRA = """
-- The GE runtime owns the wind, because the wind acts on OTHER vehicles. The
-- machine's real state lives here, in the vehicle VM. Rather than have GE
-- model the rotor and drift out of sync, the vehicle pushes what the rotor is
-- ACTUALLY doing on a cadence - including the spin-up lag and any bog from
-- eating a car.
--
-- prop_builder appends this block AFTER `M.updateGFX = updateGFX`, and the
-- bootstrap's own updateGFX early-returns the moment registration is
-- confirmed, so the telemetry has to WRAP it rather than replace it.
local FAN_TELEMETRY_HZ = 12.0
local fanTelemetryElapsed = 0.0

local function pushFanTelemetry(dt)
  fanTelemetryElapsed = fanTelemetryElapsed + dt
  if fanTelemetryElapsed < 1.0 / FAN_TELEMETRY_HZ then return end
  fanTelemetryElapsed = 0.0
  if not controller or not controller.getController then return end
  local fan = controller.getController("giantFan")
  if not fan or not fan.status then return end
  local ok, s = pcall(fan.status)
  if not ok or type(s) ~= "table" then return end
  obj:queueGameEngineLua(string.format(
    "local e = extensions[%q] if e and e.onFanTelemetry then" ..
    " e.onFanTelemetry(%d, %f, %d, %d, %s) end",
    GE_EXTENSION_NAME, obj:getID(), s.tip_mps or 0.0, s.dial or 0,
    s.tilt_rung or 1, tostring(s.sweeping and true or false)))
end

local fanBaseUpdateGFX = M.updateGFX
M.updateGFX = function(dt)
  if fanBaseUpdateGFX then pcall(fanBaseUpdateGFX, dt) end
  pcall(pushFanTelemetry, dt)
end
"""

# ---------------------------------------------------------------------------
# 20. Runtime tunables.
#
# SCALARS AND 3-VECTORS ONLY. test_required_tunables_all_ship slices the
# shipped `local B = {` block at the first `}`, so a single list-valued entry
# silently hides every alphabetically later key from the gate - and a mod
# whose tunable check fails holds every part at its authored pose. The two
# ladders are emitted as raw Lua constants ahead of the chunk instead.
# ---------------------------------------------------------------------------
BEHAVIOR = {
    "camera_distance": CAMERA_DISTANCE,
    # geometry the field needs
    "tip_r": TIP_R,
    "hub_r": HUB_R,
    "rotor_standoff": ROTOR_STANDOFF,
    "deck_z": DECK_Z,
    # wind
    "jet_spread": JET_SPREAD,
    "jet_hub_dead": JET_HUB_DEAD,
    "a_max": A_MAX_MPS2,
    "falloff_d0": FALLOFF_D0,
    "jet_max_d": JET_MAX_D,
    "near_fade_d": NEAR_FADE_D,
    "omega_3": OMEGA_3,
    "tip_max": TIP_MPS[-1],
    # the pack's standard field-safety envelope
    "frame_dv_cap": 1.2,
    "max_sample_speed": 70.0,
    "dt_clamp": 0.05,
    "safety_extent_max": 24.0,
    "quarantine_seconds": 8.0,
    # controls
    "dial_debounce": DIAL_DEBOUNCE_S,
    "stop_pad_dwell": STOP_PAD_DWELL_S,
    "stop_pad_speed_max": STOP_PAD_SPEED_MAX,
    "sweep_period": SWEEP_PERIOD_S,
    "plunger_travel": PLUNGER_TRAVEL,
}

_LADDERS_LUA = """
-- Authored ladders. Raw constants rather than B entries: the tunables gate
-- reads the B table by slicing at its first closing brace, so one list-valued
-- entry would hide every key after it.
local TIP_MPS      = {%s}
local TILT_CLEAR_M = {%s}
local TILT_RUNG    = {%s}
local DIAL_ORDER   = {%s}
""" % (
    ", ".join(repr(float(v)) for v in TIP_MPS),
    ", ".join(repr(float(v)) for v in TILT_CLEAR_M),
    ", ".join('"%s"' % n for n in TILT_RUNG_NAME),
    ", ".join(str(int(v)) for v in DIAL_ORDER),
)

_BEHAVIOR_LUA = r"""
-- ==========================================================================
-- The Giant Fan - game-engine behaviour.
--
-- The MACHINE is not driven from here. Its rotor is a real jbeam rotator and
-- its head is on real hydros, so every moving part is solved by the physics
-- core at 2000 Hz. This chunk does three things the vehicle VM cannot:
--
--   1. forwards a console press to THIS fan's controller (per-vehicle, via
--      queueLuaCommand - never a broadcast);
--   2. blows the wind, which acts on OTHER vehicles and so has to live GE-side;
--   3. reports state.
--
-- The wind's direction is read from the machine itself: the two hub-axis cage
-- nodes give the real fan axis in world space, so the jet follows the sweep,
-- the tilt and any gyroscopic nod for free, with no state to keep in sync.
-- ==========================================================================

local function fanController(state, call)
  local vehicle = exactVehicle(state.propId)
  if not vehicle then return false end
  local ok = pcall(function()
    vehicle:queueLuaCommand(
      "local c = controller.getController('giantFan') if c then c." .. call .. " end")
  end)
  return ok
end

local function announceDial(state)
  local setting = state.behavior.dial or 0
  if setting == 0 then
    showMessage("GALEFORCE: 0 - OFF", 2.0)
  else
    showMessage(string.format("GALEFORCE: %d - %s  (%d m/s at the tip)",
      setting, (setting == 3 and "HIGH") or (setting == 2 and "MEDIUM") or "LOW",
      math.floor((TIP_MPS[setting + 1] or 0) + 0.5)), 2.4)
  end
end

local function announceTilt(state)
  local rung = state.behavior.tiltRung or 1
  showMessage(string.format("BLADE HEIGHT %.2f m - %s",
    TILT_CLEAR_M[rung] or 0.0, TILT_RUNG[rung] or "?"), 2.4)
end

-- --------------------------------------------------------------------------
-- The wind.
--
-- A per-frame velocity ADD, never a SET: the pack's law, because replacing a
-- cluster velocity is a teleport. Inside a cone that opens 14 degrees from the
-- disc, with a hub dead-zone (a real axial fan has no flow at its centre) and
-- a C1 ramp-in over the first few metres so the field does not step at the
-- disc plane.
-- --------------------------------------------------------------------------
local function fanAxis(state, vehicle)
  local position = vehicle:getPosition()
  local front = nodeWorldPosition(state, vehicle, position, FAN_AXIS_FRONT)
  local rear = nodeWorldPosition(state, vehicle, position, FAN_AXIS_REAR)
  if not front or not rear then return nil, nil end
  local axis = front - rear
  if axis:length() < 0.001 then return nil, nil end
  axis:normalize()
  -- The disc stands ROTOR_STANDOFF in front of the housing rim.
  return axis, front + axis * B.rotor_standoff
end

local function applyWind(state, dtSim)
  local speed = state.behavior.tipSpeed or 0.0
  if speed < 1.0 then return end
  local selfVehicle = exactVehicle(state.propId)
  if not selfVehicle then return end
  local axis, disc = fanAxis(state, selfVehicle)
  if not axis then return end

  local dt = math.min(dtSim, B.dt_clamp)
  local strength = speed / math.max(B.tip_max, 1.0)
  strength = strength * strength          -- thrust goes as tip speed squared

  -- ge_utils.lua's getAllVehicles() returns BeamNGVehicle OBJECTS; the ids
  -- live in a cache it does not hand out. Passing an object where an id is
  -- expected makes eligibleSubject's integer() guard reject every vehicle,
  -- silently, forever - so the id comes off the object first.
  local okAll, all = pcall(getAllVehicles)
  if not okAll or type(all) ~= "table" then return end
  for _, vehicle in ipairs(all) do
    local okId, vehicleId = pcall(function() return vehicle:getId() end)
    local subject = okId and integer(vehicleId) and eligibleSubject(vehicleId) or nil
    if subject then
      local ok, delta = pcall(function()
        local p = subject:getPosition()
        local rel = p - disc
        local d = rel:dot(axis)
        if d <= 0.0 or d > B.jet_max_d then return nil end
        local radial = (rel - axis * d):length()
        local cone = B.tip_r + B.jet_spread * d
        if radial > cone then return nil end
        -- hub dead-zone, faded so its edge is not a wall
        local core = B.jet_hub_dead * (1.0 + 0.25 * d / math.max(B.falloff_d0, 1.0))
        local hub = math.min(1.0, math.max(0.0, (radial - core * 0.55) / math.max(core * 0.45, 0.1)))
        local edge = math.min(1.0, math.max(0.0, (cone - radial) / math.max(cone * 0.30, 0.1)))
        local near = math.min(1.0, d / math.max(B.near_fade_d, 0.1))
        local fall = 1.0 / (1.0 + (d / math.max(B.falloff_d0, 1.0)) ^ 2)
        local a = B.a_max * strength * hub * edge * near * fall
        if a <= 0.0 then return nil end
        local dv = math.min(a * dt, B.frame_dv_cap)
        return axis * dv
      end)
      if ok and delta and finiteVector3(delta) then
        addSubjectVelocity(state, subject, delta)
      end
    end
  end
end

-- --------------------------------------------------------------------------
-- Behaviour hooks.
-- --------------------------------------------------------------------------
function behavior.init(state)
  local b = state.behavior
  b.dial = 0
  b.tiltRung = 1
  b.sweeping = false
  b.tipSpeed = 0.0
  b.dialCooldown = 0.0
  b.padDwell = 0.0
  b.padArmed = false
  b.announced = false
end

-- The stop pad ARMS ON ENTRY, and only if the fan was already running when you
-- drove on. A car that was parked on the pad before the fan started can never
-- trip it, however long it sits there - which is the failure the earlier
-- "only bank dwell while the dial is non-zero" guard could not close, because
-- the instant a press set the dial the accumulator started again under a car
-- that had not moved. The runtime dispatches both hooks from onBeamNGTrigger.
function behavior.onEnter(state, zone, vehicle)
  if zone ~= "stop_pad" then return end
  local b = state.behavior
  b.padArmed = ((b.dial or 0) ~= 0)
  b.padDwell = 0.0
end

function behavior.onExit(state, zone, vehicleId)
  if zone ~= "stop_pad" then return end
  local b = state.behavior
  b.padArmed = false
  b.padDwell = 0.0
end

function behavior.reset(state)
  behavior.init(state)
  fanController(state, "reset()")
  showMessage(string.format(
    "GALEFORCE GF-3600 reset - dial 0, blade height %.2f m", TILT_CLEAR_M[1]), 2.6)
end

function behavior.update(state, dtSim, dtReal)
  local b = state.behavior
  if (b.dialCooldown or 0) > 0 then
    b.dialCooldown = math.max(0.0, b.dialCooldown - dtSim)
  end

  -- The stop pad. A dwell gate, not a bigger box: 0.40 s of continuous
  -- containment under 1 m/s cannot be satisfied by a crossing at any speed.
  --
  -- Three conditions, and all three are needed: the car has to be slow, the
  -- fan has to be running, and the pad has to have been ARMED by driving onto
  -- it while it was running. Arming is what makes this a verb you perform
  -- rather than a state you can be caught in.
  local occupant = firstOccupant(state, "stop_pad")
  if occupant then
    local ok, slow = pcall(function()
      return occupant:getVelocity():length() <= B.stop_pad_speed_max
    end)
    if ok and slow and (b.dial or 0) ~= 0 and b.padArmed then
      b.padDwell = (b.padDwell or 0.0) + dtSim
      if b.padDwell >= B.stop_pad_dwell then
        b.dial = 0
        b.padDwell = 0.0
        fanController(state, "dialOff()")
        showMessage("STOP PAD - the fan is winding down.", 2.6)
      end
    else
      b.padDwell = 0.0
    end
  else
    b.padDwell = 0.0
  end

  applyWind(state, dtSim)
end

function behavior.onPanelButton(state, buttonId)
  local b = state.behavior
  -- Touching the console is an explicit intent. Clear the timer AND disarm the
  -- pad, so a press is never undone by where the car happens to be standing;
  -- the pad rearms when you leave it and drive back on.
  b.padDwell = 0.0
  b.padArmed = false
  if buttonId == "dial_cw" then
    if (b.dialCooldown or 0) > 0 then return end
    b.dialCooldown = B.dial_debounce
    -- 0 -> 3 -> 2 -> 1 -> 0, the real detent order.
    local index = 1
    for i, value in ipairs(DIAL_ORDER) do
      if value == (b.dial or 0) then index = i break end
    end
    b.dial = DIAL_ORDER[index % #DIAL_ORDER + 1]
    fanController(state, "stepDial()")
    announceDial(state)
  elseif buttonId == "dial_off" then
    b.dial = 0
    fanController(state, "dialOff()")
    announceDial(state)
  elseif buttonId == "osc" or buttonId == "plunger" then
    b.sweeping = not b.sweeping
    fanController(state, "toggleSweep()")
    showMessage(b.sweeping and "OSCILLATE ON - 90 degree sweep"
                            or "OSCILLATE OFF - returning to centre", 2.2)
  elseif buttonId == "tilt_up" or buttonId == "tilt_dn" then
    local step = (buttonId == "tilt_up") and 1 or -1
    local rung = math.max(1, math.min(#TILT_CLEAR_M, (b.tiltRung or 1) + step))
    if rung == b.tiltRung then return end
    b.tiltRung = rung
    fanController(state, string.format("setTiltRung(%d)", rung))
    announceTilt(state)
  end
end

function behavior.getStatus(state)
  local b = state.behavior
  return {
    dial = b.dial or 0,
    tilt_rung = b.tiltRung or 1,
    tilt_clear = TILT_CLEAR_M[b.tiltRung or 1] or 0.0,
    sweeping = b.sweeping and true or false,
    tip_mps = b.tipSpeed or 0.0,
  }
end

-- The vehicle VM pushes its real state up at 12 Hz. Registered as an extra GE
-- hook so the shared core exports it on M.
behavior.hooks = {
  onFanTelemetry = function(vehicleId, tipSpeed, dial, tiltRung, sweeping)
    local state = installations[vehicleId]
    if not state or not state.behavior then return end
    local b = state.behavior
    if finiteNumber(tipSpeed) then b.tipSpeed = tipSpeed end
    if integer(dial) then b.dial = dial end
    if integer(tiltRung) then b.tiltRung = tiltRung end
    b.sweeping = sweeping and true or false
    if not b.announced and (b.tipSpeed or 0) > 1.0 then
      b.announced = true
    end
  end,
}
"""

# The two cage nodes the wind reads its axis from. Named here so the Lua and
# the generator can never disagree about them.
_FRAME_NODES_LUA = (
    'local FAN_AXIS_FRONT = "%s"\nlocal FAN_AXIS_REAR = "%s"\n'
    % (HUBAXIS_FRONT, HUBAXIS_REAR)
)

LUA_BEHAVIOR = _LADDERS_LUA + _FRAME_NODES_LUA + _BEHAVIOR_LUA

# Nothing static ships with this mod: the motor's voice is a stock sound
# sample referenced BY NAME through soundConfig, which is a reference and not
# a redistribution.
SHIP_ASSETS = ()
EFFECTS = {}


def _disc_offset_floor() -> float:
    """Smallest DISC_OFFSET_Y that keeps the blade clear of the neck.

    At bottom-dead-centre a blade hangs straight down past the neck. The
    binding station is the one that maximises neck_r(z) + blade_axial_half(s),
    and it is NOT the tip: the axial extent of a twisted paddle peaks inboard,
    while the neck is fattest at its base. Both terms are swept.
    """

    worst = 0.0
    steps = 2000
    for i in range(steps + 1):
        z = DECK_Z + (NECK_TOP_Z - DECK_Z) * i / steps
        radius = HUB_Z - z
        if not (HUB_R <= radius <= TIP_R):
            continue
        s = (radius - HUB_R) / BLADE_SPAN
        neck = NECK_R_BOT + (NECK_R_TOP - NECK_R_BOT) * (z - DECK_Z) / NECK_H
        worst = max(worst, neck + blade_axial_half(s))
    return worst


DISC_OFFSET_FLOOR = _disc_offset_floor()
BLADE_NECK_CLEARANCE = DISC_OFFSET_Y - DISC_OFFSET_FLOOR
BLADE_PLANFORM_M2 = sum(
    0.5
    * (blade_chord(i / 400.0) + blade_chord((i + 1) / 400.0))
    * (BLADE_SPAN / 400.0)
    for i in range(400)
)
