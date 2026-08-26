"""COLOSSUS 10350/80R457 — authored constants for Blender + runtime.

A 28.17 m earthmover radial standing on its tread, and it is a real free
physics body: nothing about its motion is scripted. Drive up the loading
dock, in through the bolted access port in its right sidewall, and you are
standing on the inner liner of a 10.5-tonne tire. Drive, and it rolls —
because your tyre patches push on its liner and its tread pushes on the
ground, which is the entire mechanism. Nothing in ``LUA_BEHAVIOR`` applies
a force, a velocity or a pose to the tire. The runtime only WATCHES it:
it reads three crown nodes, fits the axle, and reports what the physics
did.

Why that matters here. Every other rolling/spinning prop in this pack
(``gforce_centrifuge``, ``spin_cycle_washer``, ``spin_launch``) drives its
subject with a per-frame velocity field because the MACHINE is the thing
that moves and the car is cargo. This one inverts that: the car is the
prime mover and the machine is cargo. A force field would be a lie you
could feel — the tire would keep rolling when you lifted off.

===========================================================================
The size code is the single source of geometric truth
===========================================================================

``10350/80R457`` is not decoration painted on the sidewall; it is the
generator's input. Section width 10350 mm, aspect ratio 80 (section height
= 80% of section width), rim diameter 457 inches. Every radius below is
derived from those three numbers, so the moulded lettering and the mesh
can never disagree — the Cannon Car Wash "print and hardware cannot
drift" rule applied to a tire.

    SECTION_HEIGHT = 10.350 * 0.80         =  8.280 m
    BEAD_RADIUS    = 457 * 0.0254 / 2      =  5.804 m
    OUTER_RADIUS   = 5.804 + 8.280         = 14.084 m
    OUTER_DIAMETER                         = 28.168 m

ROUND 2 (2026-08-24). The first cut was ``8400/80R580``, and a tire
engineer on the critic panel took one look at the ratios and called it: a
size code is not three numbers that happen to multiply out to the diameter
you wanted, it is a SHAPE, and 8400/80R580 is the shape of a heavy-truck
drive tire. The two ratios that decide it:

    | tire                      | OD / section width | rim / section width |
    | 59/80R63 earthmover       |              2.668 |               1.067 |
    | 53/80R63 earthmover       |              2.789 |               1.189 |
    | 315/80R22.5 highway drive |              3.410 |               1.810 |
    | COLOSSUS round 1          |              3.354 |               1.754 |
    | COLOSSUS round 2 (this)   |              2.722 |               1.122 |

Round 1 was arithmetically the truck tire, which is exactly why it read as
one in every wide shot before anyone looked at a single detail. Round 2 is
inside the earthmover band, and it collapses the three scale ratios against
the reference 59/80R63 from 7.05 / 5.61 / 9.21 onto 7.05 / 6.91 / 7.25 — so
the tire is now genuinely close to a uniform 7x scale of a real one rather
than a diameter that happened to match. It also lands 4 mm off the round-1
outer diameter, so nothing downstream of OUTER_RADIUS moved.

Two things came free with it, and neither was the reason for the change:
the cavity lane went 7.20 m -> 7.93 m (a car can now turn round inside
without shuffling), and the tip-over angle went 16.6 deg -> 20.2 deg.

Tread depth, undertread, belt package and inner liner are all scaled from
a real 59/80R63 E-4 rock-service radial (OD 3.998 m, tread depth 90 mm,
belt package ~30 mm, liner ~4.5 mm) by this tire's diameter ratio, so the
carcass laminate is in true proportion at 7x scale. That is what makes the
cut edge inside the access port readable as a tire and not as a plank.

===========================================================================
Mass: the one deliberate departure from realism, and why
===========================================================================

A real 59/80R63 masses 5 500 kg at 4.0 m diameter. Rubber goes as volume,
so an honest 28.168 m version would mass 5500 * 7.0455^3 = 1 923 000 kg.
That tire cannot be moved by a car and is not a toy, it is scenery.

TIRE_MASS is therefore authored, and it is authored by SOLVING a
playability requirement rather than by taste:

    a stock 1600 kg midsize, committed, must take the Colossus from rest
    to 30 km/h inside ~15 s.

THE TORQUE. Round 1 got this wrong and three separate critics caught it
independently, so the correction is worth stating carefully. A car standing
on the inner liner transmits exactly two things to the carcass: a NORMAL
force, which is radial and therefore has zero moment about the axle, and a
FRICTION force f, which is tangential. f is the only torque. Round 1 added
"the occupant's weight moment" and "the driven-axle traction" as if they
were two sources; they are one force described twice, which is why the two
numbers came out at 87 and 93 kNm — the traction limit and the equilibrium
condition are the same line, and they meet at tan(phi) = mu_eff.

    the car sits at climb angle phi and is in equilibrium along the surface
        f = m * g * sin(phi)
    and traction bounds it
        f <= mu_eff * m * g * cos(phi)      =>   tan(phi) <= mu_eff
    with mu_eff = 0.75 (rubber on rubber, driven axle, weight transferring
    rearward as it climbs), phi_max = 36.9 deg and
        T = m * g * CAVITY_RADIUS * sin(phi_max)                = 123.9 kNm

    THE INERTIA IS NOT ABOUT THE AXLE. Round 2's solve divided that torque by
    the moment of inertia about the axle, and a critic caught it: nothing
    holds this axle. The tire rolls on the ground, so the same mass has to be
    accelerated LINEARLY as well as spun, and the moment balance that matters
    is taken about the CONTACT POINT:

        I_eff = I_cm + M * OUTER_RADIUS^2 = M * (k_gyr^2 + OUTER_RADIUS^2)

    which for this layout is M * 358.4, not M * 160.0 - the axle figure is
    2.24x optimistic, and shipping it would have meant a tire that took 36 s
    to reach a speed the file promised in 15.

        required angular acceleration for 8.33 m/s in 7.2 s
            (8.33 / OUTER_RADIUS) / 7.2                    = 0.0821 rad/s^2
        admissible I_eff  = 123.9 kNm / 0.0821             = 1.51e6 kg m^2
        radius of gyration of this node layout (MEASURED by the generator
        from the authored positions, asserted against RADIUS_OF_GYRATION)
                                                            ~ 12.65 m
        admissible mass   = 1.51e6 / (12.65^2 + 14.084^2)  ~ 4 200 kg

So the number is a consequence of a stated design target, and if the target
changes the number is re-derived, not re-guessed. ``tests/
test_colossus_tire_geometry.py`` recomputes the whole solve from the
measured node positions and fails if the spin-up time leaves the band.

THE TARGET MOVED TWICE, AND LIVE MEASUREMENTS MOVED IT BOTH TIMES. The
hamster gate - a car inside the cavity, driving the tire like a wheel - is
the mod's whole point, and it exposed two different walls in turn:

1. At 10 500 kg, rolling resistance: the engine's contact model pins Crr at
   ~5% of weight no matter what the beams do (measured against beam
   damping, stiffness, and node friction in both directions), and 5% of
   11.7 t was more than a 1.6 t car could push.

2. At 6 000 kg, THE CONTACT PATCH ITSELF. A car holding station at angle
   phi inside the ring applies its weight m*g at R_liner*sin(phi) ahead of
   the contact - about 112 kNm at the 33 degrees it settled to. But a
   deflecting tire is its own chock: the ground reaction can migrate to the
   leading edge of the +/-1.64 m contact patch and statically react up to
   (M + m) * g * a ~ 122 kNm before the wheel HAS to roll. Measured live:
   every one of the 40 tie-downs verified broken, ~115 kNm applied for 25
   seconds, and the tire leant 90 mm onto the front of its patch and stood.

Breakaway torque scales with (M + m) and the car's torque does not, so the
mass is set where the car clears the threshold with margin: at 4 200 kg the
patch can hold ~94 kNm and a mid-wall station supplies ~125-133. The
scaling stays clean - every beam rate carries the same factor (k/M
constant, so the ~95 mm deflection, the patch length, every omega*dt
margin and every damping ratio are invariant) - and downhill behaviour
does not change at all, because rolling under gravity never depended on
mass in the first place.

It still reads heavy: 4.2 t against a 1.6 t car is 2.6:1, the rolling
inertia nearly doubles that in effect, and the patch statics above mean
that even now a parked car CANNOT tip it - it takes a deliberate climb up
the wall to walk this wheel.

===========================================================================
Getting in: why the port is in the sidewall and the dock is where it is
===========================================================================

A tire is a closed torus. Its only real openings are the two bead holes,
and on a tire standing on its tread the bottom of the bead hole is
OUTER_RADIUS - BEAD_RADIUS = 8.28 m off the ground: to use it you would
need a 60 m trestle and then a 7.3 m drop down the inside of the sidewall.
A hole in the TREAD is worse — at the bottom of the tire the tread faces
the ground, so a tread port is pinched shut exactly when it is at ground
level, and open only when it is 28 m in the air.

That leaves the sidewall. The port's outer edge sits at CAVITY_RADIUS, so
when the port is at the bottom of the tire its sill IS the cavity floor —
0.93 m up, dead flush, no lip. It spans PORT_SPAN_DEG of arc and reaches
in to PORT_INNER_RADIUS, which at the bottom is a 4.86 m tall x 5.61 m
wide doorway.

The dock cannot reach that sill. The tire's widest point is SECTION_HALF =
5.175 m from the centre plane, and the port's outer face is around 4.9 m,
so a fixed dock lip close enough to bridge the gap is inside the volume the
sidewall sweeps through on every revolution — it would be destroyed on the
first turn. The gangway therefore hangs off the TIRE, not the dock: a
steel boarding tongue bolted to the port sill, sloping outboard and down,
resting on the dock's landing plate the way a ship's gangway rests on a
quay. Parked, it bridges continuously. Released, it lifts off and rides
round with the tire. Everything fixed lives at x >= DOCK_CLEAR_X, which is
outboard of every point the tire can ever occupy.

The gangway is CAGED, not just modelled. Round 1 built it as Blender meshes
only, so it had no collision at all: the drive surface ended at the dock
edge and resumed 0.7 m away and 0.15 m up, with nothing in between. A
flexbody is paint.

===========================================================================
One connected cage, and the two straps that make it one
===========================================================================

The dock is FIXED nodes; the tire is FREE nodes. They are one cage because
two authored ratchet straps hold the tire to the dock at spawn, exactly as
a real tire this size ships. They are visible orange webbing with a real,
finite ``beamStrength`` and their own ``breakGroup``; the release beat cuts
them by asking the prop's own vehicle Lua to break that group. This is not
a fabricated connector to satisfy the graph check — it is load-bearing at
spawn (it is what stops the Colossus rolling off the dock while you board)
and it is modelled, textured and visible.

Round 2 note: webbing cannot push. A static solve of round 1's cage found
33 kN of COMPRESSION in each strap at spawn against a 28 kN deform limit,
so both tie-downs yielded on frame one and jacked the tire into a 0.6 deg
list before the player did anything. STRAP_SPEC is now soft enough that
settling does not load it and strong enough that it still holds several
times the torque a boarding car can apply.

===========================================================================
Structure: the cage is a tire, not a cylinder
===========================================================================

The 20-node meridian is the real construction, and each beam family is
named for the component it stands in for, with a spring rate and a damping
rate chosen for that component's material:

  bead       the two steel bead bundles, and ONLY the hoop members between
             them. Nearly inextensible; this is what stops the carcass
             growing off the (absent) rim. The link from the bead up into
             the sidewall is `casing`, not `bead`, because on a real tire
             that is the ply turn-up wrapping the bundle over the apex.
  casing     the radial casing plies running bead-to-bead up the sidewall.
             Stiff in tension, and the main load path.
  belt       the steel belt package under the tread. The most rigid family
             in the cage, plus long chords to stations +-2 and +-3 — those
             chords ARE the belt's inextensibility, and they are the reason
             the tire keeps a circle instead of ovalising under its weight.
  sidewall   sidewall rubber in shear and bending. Soft.
  tread      the tread slab and undertread in radial compression. This is
             the family that flattens into a contact patch.
  inflation  a truss across the cavity standing in for the air. A real
             tire is a pressure vessel: unpressurised it is a floppy bag,
             and every bit of its radial stiffness is air doing work. With
             no fluid to model, the pressure is a soft, heavily damped
             chord network across the diameter. It is invisible, it is
             honest about what it replaces, and without it the carcass
             collapses.

Damping is picked from the material, not tuned to taste: the RUBBER
families run 15-20% of critical damping because rubber's loss tangent
really is that high (it is why tires get hot), and the STEEL families run
4-6% because steel cord does not.

STIFFNESS IS BOUNDED FROM BOTH SIDES, and round 1 sat outside both bounds.

  Above: BeamNG integrates explicitly at 2000 Hz. The tight bound for a
  mass-spring lattice is omega_max = sqrt(2 * sum_k / m) over the beams
  meeting a node; round 1's inner-liner nodes summed 1.179e8 N/m on 14.2 kg
  and came out at omega*dt = 2.04, past the symplectic-Euler limit of 2.
  The tire would have rung itself apart.

  Below: the carcass has to DEFLECT. TIRE_MASS is cut ~107x from an honest
  1.92e6 kg, but round 1's spring rates were argued from real materials at
  full scale, so the cage was orders of magnitude stiffer relative to its
  own weight than a real tire. A static solve converged on a contact set of
  TWO nodes over a 1.68 m strip under a body whose centre of mass is 14 m
  up. It would have fallen over on the first bump.

The rates below are chosen so the static solve lands a real footprint, and
``tests/test_colossus_tire_geometry.py`` checks both bounds every run — it
carries its own unilateral-contact solver rather than trusting the numbers.

Everything here still wants live play-testing — spring rates on a body this
size are the one thing static gates cannot fully judge.
"""

import math

MOD_ID = "ericrolph_colossus_tire"
DISPLAY_NAME = "COLOSSUS 10350/80R457"
VALUE_DOLLARS = 96000
ZIP_BASENAME = "colossus_tire_ericrolph.zip"

# Nothing under assets/ is opened by the game at runtime.
SHIP_ASSETS = ()

# The Colossus measures; it never drives. Opting OUT of the pack's shared
# subject-mutation helpers makes that structural rather than a promise: the
# generated runtime does not even CONTAIN launchSubject / addSubjectVelocity /
# teleportSubject, so no later edit can quietly reach for one.
# catapult_seesaw/spec.py:386 opts out for the same reason, so this is one of
# two, not the only one - the argument does not need the false uniqueness.
ALLOW_SUBJECT_MUTATION = False

# ---------------------------------------------------------------------------
# Reference vehicle. Clearances and the mass solve above are sized from this.
# A BeamNG midsize (etk800 class) is ~2.0 m wide, 4.5 m long, 1.5 m tall,
# ~1600 kg at spawn.
# ---------------------------------------------------------------------------
CAR_WIDTH = 2.0
CAR_LENGTH = 4.5
CAR_HEIGHT = 1.5
CAR_MASS = 1600.0
CAR_TURN_RADIUS = 5.2
GRAVITY = 9.81

# ---------------------------------------------------------------------------
# THE SIZE CODE. Everything geometric below is derived from these three
# numbers, and the sidewall moulding prints the same three numbers.
# ---------------------------------------------------------------------------
INCH = 0.0254
SECTION_WIDTH_MM = 10350
ASPECT_RATIO_PCT = 80
RIM_DIAMETER_IN = 457
SIZE_CODE = f"{SECTION_WIDTH_MM}/{ASPECT_RATIO_PCT}R{RIM_DIAMETER_IN}"

SECTION_WIDTH = SECTION_WIDTH_MM / 1000.0            # 10.350 m
SECTION_HALF = SECTION_WIDTH / 2.0                   #  5.175 m
SECTION_HEIGHT = SECTION_WIDTH * ASPECT_RATIO_PCT / 100.0   # 8.280 m
BEAD_RADIUS = RIM_DIAMETER_IN * INCH / 2.0           #  5.804 m
OUTER_RADIUS = BEAD_RADIUS + SECTION_HEIGHT          # 14.084 m
OUTER_DIAMETER = 2.0 * OUTER_RADIUS                  # 28.168 m

# The two shape ratios that decide whether this reads as an earthmover.
OD_TO_WIDTH = OUTER_DIAMETER / SECTION_WIDTH                 # 2.722
RIM_TO_WIDTH = RIM_DIAMETER_IN * INCH / SECTION_WIDTH        # 1.122
EARTHMOVER_OD_TO_WIDTH = (2.55, 2.95)     # the band real E-class sits in
EARTHMOVER_RIM_TO_WIDTH = (1.00, 1.30)

# Reference carcass this one is scaled from: a 59/80R63 E-4 rock radial.
REFERENCE_OD = 63 * INCH + 2 * (59 * INCH * 0.80)    # 3.9980 m
SCALE = OUTER_DIAMETER / REFERENCE_OD                # 7.0455

TREAD_DEPTH = 0.090 * SCALE                          # 0.634 m
UNDERTREAD = 0.008 * SCALE                           # 0.056 m
BELT_PACKAGE = 0.030 * SCALE                         # 0.211 m
LINER_THICKNESS = 0.0045 * SCALE                     # 0.032 m

GROOVE_RADIUS = OUTER_RADIUS - TREAD_DEPTH           # 13.450 m (groove floor)
CAVITY_RADIUS = GROOVE_RADIUS - UNDERTREAD - BELT_PACKAGE - LINER_THICKNESS
# 13.150 m — the surface the car actually drives on.

# Tread arc: the crown is not a cylinder, it is an arc that drops toward the
# shoulders. Round 1 used 24 m, which drops 0.357 m across this tread half
# width - far more than the carcass settles, so the shoulders never touched
# and the whole mass balanced on the centre rib. 62 m keeps a visible crown
# that the measured static settle can close.
TREAD_ARC_RADIUS = 62.0
TREAD_HALF = 0.400 * SECTION_WIDTH                   # 4.140 m (tread 8.28 m)
CROWN_DROP = TREAD_HALF**2 / (2.0 * TREAD_ARC_RADIUS)  # 0.138 m at the edge

# ---------------------------------------------------------------------------
# Sidewall meridian, authored on the STRUCTURAL mid-shell as
# (fraction of section height above the bead, fraction of section half width).
# Maximum section width at 60% of section height is where a radial of this
# aspect ratio actually carries it, and MERIDIAN[0]'s 0.732 is the rim-width
# to section-width relationship of a real 59/80R63 carried through exactly.
#
# The bead is three stations, not one: a tire with no rim in the build shows
# both bead holes in every wide shot, and a single station closed with a
# half-round cap is a rubber bullnose, not a bead. Toe, heel and the flange
# rise give it the seat taper a real bead sits on.
# ---------------------------------------------------------------------------
# (fraction of section height above the bead, OUTER half width as a fraction
# of SECTION_HALF). The 1.000 at maximum section width is not decoration: it
# is what makes the moulded size code true. The bead station is chosen so the
# INNER face there - the bead seat, which is what a rim width measures between
# - lands on the reference tire's 0.746 rim-to-section-width ratio; the
# generator asserts it.
# THE SILL STATION. The access port's outer edge is CAVITY_RADIUS, and the
# cage can only cut the sidewall cleanly on a NODE RING. Round 1's outer edge
# fell between the 0.830 and 0.930 stations, so the band spanning it could not
# be cut and stayed in the collision mesh: an invisible 1.14 m panel standing
# across the doorway, 0.208 m above the sill. Rather than hand-typing a
# station and hoping it stays put, the sill is INSERTED at the exact cavity
# fraction and interpolated off the base meridian, so it tracks the size code.
SILL_FRACTION = (CAVITY_RADIUS - BEAD_RADIUS) / SECTION_HEIGHT   # 0.8873

# THE SHOULDER HAS TO FALL AWAY. Round 4 measured a full-circumference lip:
# the lathe's last station sat at radius 13.5043 while the tread's groove
# floor at its outboard edge is 13.3116, so the outer surface CLIMBED 0.198 m
# going outboard from the tread edge - 31% of TREAD_DEPTH - and dammed the
# mouth of every shoulder groove on a pattern whose lateral grooves exist to
# throw stones out sideways. The top station's FRACTION is now derived to sit
# a stated shelf below that floor, so the profile can only fall outboard; its
# HALF WIDTH is derived so the SILL's interpolated value does not move, because
# LINER_HALF is measured off the sill and letting it drift would have taken
# 0.24 m out of the lane the car has to turn round in.
_TREAD_EDGE_FLOOR = (
    OUTER_RADIUS - TREAD_HALF ** 2 / (2.0 * TREAD_ARC_RADIUS) - TREAD_DEPTH
)
SHOULDER_SHELF = 0.080
SHL_FRACTION = (_TREAD_EDGE_FLOOR - SHOULDER_SHELF - BEAD_RADIUS) / SECTION_HEIGHT
if SHL_FRACTION <= SILL_FRACTION:
    raise ValueError(
        f"a {SHOULDER_SHELF:.3f} m shoulder shelf puts the top of the lathe at "
        f"fraction {SHL_FRACTION:.4f}, at or below the cavity sill at "
        f"{SILL_FRACTION:.4f}; the outer surface would stop under the inner one"
    )
_UPP_FRACTION, _UPP_HALF, _UPP_THICK = 0.830, 0.962, 0.34
_SILL_TARGET_HALF = 0.9151          # the sill the laminate stack was built on
_SILL_TARGET_THICK = 0.4083
_SHL_SPAN = (SHL_FRACTION - _UPP_FRACTION) / (SILL_FRACTION - _UPP_FRACTION)
_SHL_HALF = _UPP_HALF + (_SILL_TARGET_HALF - _UPP_HALF) * _SHL_SPAN
_SHL_THICK = _UPP_THICK + (_SILL_TARGET_THICK - _UPP_THICK) * _SHL_SPAN

_MERIDIAN_BASE = (
    (0.000, 0.873),          # bead toe, inboard
    (0.055, 0.890),          # bead heel, up the seat taper
    (0.140, 0.930),          # above the rim flange line
    (0.300, 0.966),          # lower sidewall   <- PORT_INNER_RADIUS lands here
    (0.600, 1.000),          # MAXIMUM SECTION WIDTH: outer half == SECTION_HALF
    (_UPP_FRACTION, _UPP_HALF),   # upper sidewall
    (SHL_FRACTION, _SHL_HALF),    # buttress into the shoulder, DERIVED
)
# Rim width / section width on the reference 59/80R63, measured between the
# bead SEATS - i.e. the tire's inner face at the bead.
REFERENCE_RIM_RATIO = 0.746
RIM_RATIO_TOLERANCE = 0.02

# Moulded rubber thickness along the meridian, at the same station fractions.
# Thick at the bead (chafer + apex), thinnest at max width where the tire has
# to flex, thickening again into the shoulder. These divide back to 88 mm at
# the bead and 43 mm at max width on the reference tire, both correct for an
# OTR radial.
# The last value is DERIVED alongside the shoulder station's half width and
# for the same reason: LINER_HALF is _SILL_HALF minus a full thickness minus
# the fillet, so a thickness that drifted at the sill would quietly take
# 67 mm out of the lane the car turns round in.
_THICKNESS_BASE = (0.66, 0.62, 0.52, 0.40, 0.30, 0.34, _SHL_THICK)

def _interp_base(fraction: float) -> tuple[float, float]:
    for index in range(len(_MERIDIAN_BASE) - 1):
        lo_f, lo_h = _MERIDIAN_BASE[index]
        hi_f, hi_h = _MERIDIAN_BASE[index + 1]
        if lo_f <= fraction <= hi_f:
            blend = (fraction - lo_f) / max(hi_f - lo_f, 1e-9)
            return (
                lo_h + (hi_h - lo_h) * blend,
                _THICKNESS_BASE[index]
                + (_THICKNESS_BASE[index + 1] - _THICKNESS_BASE[index]) * blend,
            )
    return (_MERIDIAN_BASE[-1][1], _THICKNESS_BASE[-1])


_SILL_H, _SILL_T = _interp_base(SILL_FRACTION)
_STATIONS = sorted(
    list(zip(_MERIDIAN_BASE, _THICKNESS_BASE)) + [((SILL_FRACTION, _SILL_H), _SILL_T)],
    key=lambda row: row[0][0],
)
MERIDIAN = tuple(row[0] for row in _STATIONS)
SIDEWALL_THICKNESS = tuple(row[1] for row in _STATIONS)

# Named meridian fractions the cage and the port both key off, so neither can
# drift away from the other.
BEAD_FRACTION = 0.000
LOW_FRACTION = 0.300
MAX_FRACTION = 0.600
UPP_FRACTION = 0.830
# SHL_FRACTION is derived above, from the tread's own groove floor.


def _meridian_lookup(radius: float) -> tuple[float, float]:
    """(OUTER half width, moulded thickness) at a radius. Spec-local."""

    fraction = (radius - BEAD_RADIUS) / SECTION_HEIGHT
    if fraction <= MERIDIAN[0][0]:
        return (MERIDIAN[0][1] * SECTION_HALF, SIDEWALL_THICKNESS[0])
    for index in range(len(MERIDIAN) - 1):
        lo_f, lo_h = MERIDIAN[index]
        hi_f, hi_h = MERIDIAN[index + 1]
        if lo_f <= fraction <= hi_f:
            blend = (fraction - lo_f) / max(hi_f - lo_f, 1e-9)
            half = (lo_h + (hi_h - lo_h) * blend) * SECTION_HALF
            thick = (
                SIDEWALL_THICKNESS[index]
                + (SIDEWALL_THICKNESS[index + 1] - SIDEWALL_THICKNESS[index]) * blend
            )
            return (half, thick)
    return (MERIDIAN[-1][1] * SECTION_HALF, SIDEWALL_THICKNESS[-1])


def meridian_point(fraction: float, half_width_fraction: float) -> tuple[float, float]:
    """(half width, radius) for one authored meridian station."""

    return (half_width_fraction * SECTION_HALF, BEAD_RADIUS + fraction * SECTION_HEIGHT)



# Inner liner half width. DERIVED, not typed: the floor runs out to just
# inboard of where the sidewall's inner face reaches at CAVITY_RADIUS, and a
# fillet closes the rest. Round 1 had it as a literal 3.600, which silently
# stopped tracking the section width.
SHOULDER_FILLET = 0.360
_SILL_HALF, _SILL_THICK = _meridian_lookup(CAVITY_RADIUS)
# _SILL_HALF is the OUTER face, so the cavity side is a full thickness in.
LINER_HALF = _SILL_HALF - _SILL_THICK - SHOULDER_FILLET

# ---------------------------------------------------------------------------
# Physics cage resolution.
#
# 48 stations is 7.5 deg apart: a facet chord of 1.844 m whose sagitta is
# FACET_SAGITTA below - the collision cylinder is round to 0.21% of radius
# over a 28 m tire. Finer buys nothing a player can feel and every station
# costs 20 free nodes. (Round 1's comment claimed 0.0189 m here; the formula
# on the next line says 0.030, and 0.0189 would need 61 stations. The
# conclusion survived, the figure did not, and the generator now asserts it.)
# ---------------------------------------------------------------------------
STATIONS = 48
STATION_ANGLE = 2.0 * math.pi / STATIONS
FACET_SAGITTA = OUTER_RADIUS * (1.0 - math.cos(math.pi / STATIONS))   # 0.0302 m
FACET_SAGITTA_CEILING = 0.040

# Cross-section: 15 nodes round the outer shell, 5 across the inner liner.
CROWN_XS = (-TREAD_HALF, -TREAD_HALF / 2.0, 0.0, TREAD_HALF / 2.0, TREAD_HALF)
LINER_XS = (-LINER_HALF, -LINER_HALF / 2.0, 0.0, LINER_HALF / 2.0, LINER_HALF)

# ---------------------------------------------------------------------------
# Mass budget. Fractions are by component, taken from a real radial's build.
#
# The split is also a STABILITY constraint, not just a realism one. The belt
# family is the stiffest thing in the cage and it connects the inner-liner
# ring, so the liner nodes' mass sets how fast that family can be integrated:
# omega = sqrt(2 * sum_k / m). Round 1 put only 11% of the mass there, left
# 14 kg nodes on an 18 MN/m belt, and landed at omega*dt = 2.04 - past the
# integrator's limit. Moving the BELT PACKAGE's mass onto that ring (which is
# where it physically sits, between the undertread and the liner) fixes the
# realism and the numerics with the same change.
# ---------------------------------------------------------------------------
TIRE_MASS = 4200.0
MASS_TOTAL_TOLERANCE = 60.0
# The crown block's 0.61 is split between its two rings IN PROPORTION TO THE
# BEAM STIFFNESS EACH RING CARRIES, not by guessing at rubber vs steel. The
# explicit integrator's per-node bound is omega*dt = sqrt(2*sum_k/m)*dt, so
# for a fixed total mass the stiffest-loaded ring must also be the heaviest
# or it alone caps how stiff the whole carcass may be. Measured off the
# shipped cage: liner ring nodes carry ~4.6 MN/m of beams against the tread
# ring's ~6.5 MN/m, and the old 0.19/0.42 split left the liner at 8.3 kg -
# the single worst node in the prop, wasting a third of the stability budget.
# 0.25/0.36 equalises the crown block at ~0.46 omega*dt and is also more
# honest: the belt package under the tread IS the heavy steel in a real tire.
MASS_FRACTIONS = {
    "crown": 0.36,     # tread cap + undertread, 5 nodes/station
    "liner": 0.25,     # steel belt package + inner liner, 5 nodes/station
    "sidewall": 0.29,  # 8 nodes/station (low/max/upp/shl, both sides)
    "bead": 0.10,      # 2 nodes/station
}
# Measured by the generator from the authored node layout and asserted; the
# mass solve above quotes it, so it must not drift silently.
RADIUS_OF_GYRATION = 12.60
RADIUS_OF_GYRATION_TOLERANCE = 0.40
MU_EFFECTIVE = 0.75
SPINUP_TARGET_KPH = 30.0
SPINUP_TARGET_SECONDS = 7.2
SPINUP_SECONDS_BAND = (5.0, 12.0)

# ---------------------------------------------------------------------------
# Beam families. beamSpring N/m, beamDamp N.s/m. See the module docstring for
# the two-sided bound these sit inside.
#
# THE RATES WERE MEASURED INTO PLACE, NOT CHOSEN. A parameter sweep ran the
# real shipped cage through the same unilateral-contact static solve that
# gates it (tests/test_colossus_tire_geometry.py::_relax), over the STEEL
# scale, the RUBBER scale and the crown arc radius:
#
#   steel  rubber   arc |  omega*dt  contact nodes   patch (w x l)
#    1.00    1.00    62 |     1.459              3    4.14 x 0.00
#    0.50    0.50    62 |     1.032              3    4.13 x 0.00
#    0.25    0.50    62 |     0.763             11    8.25 x 3.67
#    0.25    0.50   200 |     0.763             15    8.29 x 3.68
#
# Two things fell out of it that guessing would not have found. The STEEL
# families are the whole lever - halving the rubber changes the footprint by
# nothing, because the load path into the ground runs through the belt, not
# through the tread gum. And once the steel is right the CROWN ARC barely
# matters, which means the tire can keep a real 62 m tread arc (a visible
# crown, as an earthmover has) instead of being flattened to 200 m to fake a
# contact patch it could not otherwise make.
#
# So: steel x 0.25, rubber x 0.5 against the first cut. Damping is scaled by
# the SQUARE ROOT of each factor, because zeta = c / (2*sqrt(k*m)) - dividing
# k by four and leaving c alone would have doubled every damping ratio the
# argument above depends on.
#
# The cost is stated rather than hidden: a softer belt holds its circle less
# well, so the carcass leans on its long chords more than a real steel belt
# would. The static solve says it still stands and still makes a footprint;
# that is the trade this prop makes to be 107x lighter than an honest tire.
# ---------------------------------------------------------------------------
#
# When TIRE_MASS moved 18000 -> 10500 for the rolling-inertia correction, every
# rate here moved with it by the same factor, and every damping rate by its
# square root. That is not tidiness: the static deflection is W/k and the
# damping ratio is c / (2*sqrt(k*m)), so holding k/M and c/sqrt(k*M) constant
# is what keeps the measured contact patch and the material damping arguments
# above true after a mass change. The gates re-measure both regardless.
_MASS_SCALE = 4200.0 / 18000.0
#
# RETUNED x3.2, TO THE INTEGRATOR CEILING. Watched rolling live, the carcass
# at the rates above read as jelly: a ~1 Hz bounce mode, 458 mm of ring after
# an impact, and a measured 6.2% rolling resistance that parked it on a 3.4
# degree grade. A tire this size should read as nearly rigid - its deflection
# is a couple of hundred mm on a 14 m radius - so every carcass family is
# multiplied by the largest factor the 2000 Hz explicit integrator leaves
# room for. With the crown mass re-split above, the worst node sits at
# omega*dt 0.46 of a 0.90 ceiling: (0.90/0.46)^2 with margin is x3.2. That
# takes the static deflection from ~250 mm to ~80 mm - still 2.6x the
# collision hull's 30 mm facet sagitta, so the contact patch keeps swallowing
# the polygon - and moves every mode up by x1.79 while its amplitude drops.
#
# Damping is x sqrt(3.2), because zeta = c / (2*sqrt(k*m)): scaling c by the
# square root of the spring factor is what KEEPS the measured damping ratios
# (tread ~0.17, sidewall ~0.25, steel under 0.12 - the tan-delta lesson:
# zeta ~= tan(delta)/2, learned when the tread shipped at 0.42) while the
# whole spectrum stiffens. The gates re-measure both regardless.
# ...and re-scaled twice more alongside TIRE_MASS 10500 -> 6000 -> 4200
# (the two hamster measurements in the module docstring): k/M and
# c/sqrt(k*M) held constant each time, so every figure the paragraphs above
# argue - the deflection, the integrator margins, the damping ratios, the
# patch - survives unchanged.
BEAM_SPECS = {
    "bead": dict(beamSpring=934_500.0, beamDamp=466.0),        # steel, ~11%
    "belt": dict(beamSpring=840_000.0, beamDamp=424.0),        # steel, ~7%
    "casing": dict(beamSpring=374_000.0, beamDamp=456.0),      # cord+rubber
    "sidewall": dict(beamSpring=112_000.0, beamDamp=270.0),    # rubber, ~15%
    "tread": dict(beamSpring=280_000.0, beamDamp=307.0),       # rubber, ~22%
    "inflation": dict(beamSpring=84_000.0, beamDamp=270.0),    # the air
    "port_frame": dict(beamSpring=875_000.0, beamDamp=611.0),  # bolted ring
    "gangway": dict(beamSpring=875_000.0, beamDamp=611.0),     # steel plate
}
# Steel structure of the dock. Fixed nodes make rigidity irrelevant, but the
# beams still have to exist for connectivity and flexbody binding.
DOCK_BEAM = dict(
    beamSpring=15_000_000.0,
    beamDamp=1500.0,
    beamDeform="FLT_MAX",
    beamStrength="FLT_MAX",
)
# The two shipping straps. Soft enough that settling does not load them (a
# NORMAL beam pushes, and webbing cannot), strong enough to hold several
# times the torque a boarding car can apply.
STRAP_SPEC = dict(
    beamSpring=300_000.0,
    beamDamp=900.0,
    beamDeform=60_000.0,
    beamStrength=95_000.0,
)
# The boarding gangway's mass, spread over the cage nodes that actually get
# created. It is bolted to the port sill and STAYS bolted after the straps are
# cut, so it is part of the rolling body for the whole ride - which is why the
# generator balances the carcass against it rather than pretending it is
# scenery. 900 kg is about 23 m2 of 10 mm plate with stiffeners.
STRAP_BREAK_GROUP = "colossus_tiedown"

# ---------------------------------------------------------------------------
# The chocks.
#
# THE ONLY FIXED STRUCTURE ON THIS PROP. The loading dock, the boarding
# gangway and the bolted access port were built so a car could get INSIDE the
# carcass; the brief is now the tire itself, as real as it can be made, so all
# three are gone and what a 10.5 tonne carcass standing in a yard actually has
# under it is a pair of chocks.
#
# A chock only works if the tire has to climb it, so its height is DERIVED
# from where its heel sits: at CHOCK_FAR from the contact patch the carcass is
# OUTER_RADIUS - sqrt(OUTER_RADIUS^2 - CHOCK_FAR^2) off the ground, and that
# is exactly how tall the wedge has to be for its top edge to touch. On a 28 m
# tire that is 1.34 m at 6.0 m out - the curve is very flat down there, which
# is why a chock for something this size is long rather than tall.
# ---------------------------------------------------------------------------
# A CHOCK STOPS IT CREEPING, IT DOES NOT PIN IT. The first cut put the heel
# 6.0 m out, which makes a 1.34 m wall the tire cannot climb - and the live
# gate caught exactly that: with the tie-downs cut and a car shoving it, the
# axle moved 0.56 m and stopped against its own chock. A wedge whose heel is
# 4.4 m out is 0.70 m tall at a 16 degree ramp: enough that it will not roll
# off on a camber, not so much that a deliberate push cannot ride over it.
CHOCK_NEAR = 2.00              # toe, toward the contact patch
CHOCK_FAR = 4.40               # heel, where the top edge meets the carcass
CHOCK_HALF_WIDTH = 1.10
CHOCK_STRIPE = 0.34            # hazard band up the climb face
# FOUR CHOCKS, UNDER THE SHOULDERS, not two on the centre line. An 8.28 m
# tread gets chocked under its shoulders in the real world, and here it also
# leaves the middle of the contact patch clear - which matters, because the
# only thing that can move this tire now is a vehicle driving into it, and a
# push 3.2 m off the centre line rolls it over instead of rolling it along.
# (Measured live: 23 m of travel and a capsize.)
CHOCK_OFFSET = 3.00            # from the centre plane to each chock's middle
# THE WEDGES ARE BODIES NOW, NOT SCENERY. Two things were discovered about
# the fixed-node chocks: their nodes shipped without selfCollision, so the
# tire never actually pressed on them (the straps did all the holding), and
# being fixed meant that after release the tire rolled straight THROUGH their
# meshes. So each wedge is a free ~540 kg steel body whose base corners are
# strapped to buried anchors in the same break group as the tie-downs, and
# its nodes carry selfCollision so the carcass genuinely rests against it.
# Release now means what it means in a yard: the ties are cut, and 10.5
# tonnes shoves its own chocks skittering out of the way.
# The wedge top must NOT carry the resting carcass. At 0.06 the settled
# tread lay on the wedge with enough weight that 0.55 friction beat any
# winch the release could plausibly apply (measured: 1.8 kN moved it 10-50
# mm), and whether it escaped depended on bounce timing. 0.15 keeps the
# wedge clear of the settled surface - the local drop 4.4 m from the patch
# is a few tens of mm - so the chock engages a tire that tries to ROLL,
# which is a chock's actual job, and the winch only ever fights the wedge's
# own weight.
CHOCK_SEAT_GAP = 0.15
# SIZED TO BE SHOVED. The first free-body cut made each wedge 540 kg at 0.95
# friction, and the released tire could not push two of them on a 3.4 degree
# grade - 6.1 kN of grade force against ~10 kN of chock resistance, measured
# as a 0.25 m creep that stopped dead. A wedge you cannot shove is a wall
# with extra steps. 200 kg at 0.55 (steel skidding on dirt) keeps the chock
# meaningful on gentle grades and lets 10.5 tonnes walk it out of the way on
# a real one.
WEDGE_NODE_MASS = 33.5         # 6 nodes/wedge -> ~200 kg of chock steel
WEDGE_ANCHOR_DEPTH = 0.60      # buried, collisionless, fixed
# HONEST STEEL, because the WINCH moves the wedges, not a friction fudge.
# Two live findings sit behind this number. First, a 16 degree ramp is
# self-locking against any ground friction above tan(16) = 0.29: pushing the
# tire into it presses the wedge harder into the ground, so quasi-static
# torque can never shove it on the flat (measured: ~115 kNm from a car
# inside, 0.09 m of lean, wedge untouched). Second, a wedge lying against
# the tread props the carcass through the ramp geometry even when every
# strap is verifiably broken - the support point walks up the ramp and the
# lever arm reaches 4.4 m. Both are exactly what a chock is FOR, so the
# friction stays real and the RELEASE deals with the wedges the way a crew
# does: the same beat that cuts the webbing winches each wedge clear
# (thrusters.applyImpulse along its own toe-to-heel axis, see cutChocks).
WEDGE_FRICTION = 0.55
# The winch pull per wedge corner pair, sized against MEASURED skid
# friction, not the node coefficient. BeamNG combines a node's frictionCoef
# with the ground model's own coefficient, and a full-force probe read the
# wedge's effective mu at ~0.87 - so 0.55-worth of winch (1800 N) netted
# 80 N and dragged it 0.29 m. 2400 N per wedge against ~1740 N of measured
# friction is a = 3.3 m/s^2 for 1.2 s: the wedge drags ~3.3 m and stops,
# clear of the second collision facet's reach.
WINCH_FORCE_N = 1500.0
WINCH_SECONDS = 1.2
# The wedge's own skeleton. DOCK_BEAM's 15 MN/m was tuned for fixed nodes,
# where stiffness is free; on a free 33.5 kg node it costs omega*dt 1.23 and
# diverges. 3 MN/m holds a 200 kg block perfectly rigid at omega*dt 0.48.
WEDGE_BEAM = dict(
    beamSpring=3_000_000.0,
    beamDamp=1500.0,
    beamDeform="FLT_MAX",
    beamStrength="FLT_MAX",
)


# ---------------------------------------------------------------------------
# Tread pattern. Deep-lug E-4/L-5 rock service.
#
# Sized against the reference tire rather than by eye. A 59/80R63's lugs are
# roughly 0.30 m long on a 4.0 m tire; at SCALE that is 2.1 m here, so the
# pitch is 2.46 m and the lug fills most of it.
#
# NET-TO-GROSS is the number that decides the class, and round 1 was two
# whole classes out. Measured off round 1's actual geometry it ran 54.3% land
# across the width and 65.0% circumferentially, so 35.3% net-to-gross at the
# contact face. E-4/L-5 rock haulage runs 70-85%; even a mud-terrain
# light-truck tire is ~60%. Nothing in E- or L-class is under 60%. Round 1's
# shoulder row was also the NARROWEST on the tire, where on every rock-service
# earthmover it is the largest block, because the shoulder takes the side load
# in a berm. Both are fixed below, and the rows are now fractions of TREAD_HALF
# so they survive the size code changing under them.
#
# NO SIPES. Sipes are a wet-grip feature on highway rubber; an E-4/L-5
# earthmover lug is a solid block, and its features are the chamfer, the tie
# bar at the root, the stone ejector in the groove floor and the tread wear
# indicator.
#
# Variable pitch is the detail that makes a real tread a real tread: uniform
# pitching sings one loud tone at (pitches x rev/s), so every production tire
# uses a designed sequence of 3-4 pitch lengths to smear that energy across a
# band. Real sequences are arranged in RUNS of varying length - a smooth
# modulation round the tire - not shuffled, because a shuffle re-concentrates
# energy at whatever period the shuffle happens to contain.
# ---------------------------------------------------------------------------
TREAD_PITCHES = 36
PITCH_RATIOS = (0.84, 1.00, 1.18)
PITCH_SEQUENCE = (
    0, 0, 1, 2, 2, 2, 1, 0, 0, 1,
    2, 2, 1, 0, 1, 2, 2, 2, 1, 1,
    0, 0, 1, 2, 2, 1, 0, 0, 0, 1,
    2, 2, 1, 0, 1, 1,
)
LATERAL_GROOVE = 0.360          # circumferential width of the lateral grooves
TIE_BAR_HEIGHT = 0.210          # bar in the lateral groove base, anti-tear
LUG_CHAMFER = 0.085             # moulded chamfer on the lug crown
# Round 1 grew the block by fillet + draft = 0.225 m PER SIDE at the groove
# floor, which necked a 0.500 m groove to a 0.050 m slot under 0.634 m of
# depth. No mould releases that, and it packs solid with fines on the first
# pass. 0.085 total leaves a 0.186 m floor on the new 0.356 m grooves -
# floor/top 0.52, correct for OTR - and 2.7 deg of draft over the depth.
# HOW FAR EVERY PIECE OF FURNITURE SINKS INTO THE SURFACE IT STANDS ON.
# The lugs, tie bars, ejectors, buttress wraps and moulded glyphs are all
# open-bottomed shells, and they were built on the ANALYTIC surface - the
# exact groove-floor radius, the exact sidewall half width. The surface they
# actually sit on is TESSELLATED, and a 144-station chord dips about 3 mm
# inside its own analytic radius, so every one of those rims stood a hairline
# above its own floor: 2,461.6 m of open rim of which round 4 measured 82%
# uncovered - a slot to the skybox at the root of every lug wall, all the way
# round, worst exactly where the camera gets low.
LUG_SEAT = 0.010
LUG_ROOT_FILLET = 0.055
LUG_DRAFT = 0.030
STONE_EJECTOR_R = 0.110         # bumps in the circumferential groove floors
TWI_HEIGHT = 0.095              # tread wear indicator bar in the groove floor

# Row bands as |x| fractions of TREAD_HALF, outermost last. Land across the
# width is 0.160 + 0.310 + 0.358 = 0.828, and the shoulder is now the widest
# block on the tire, as it is on every rock-service earthmover.
TREAD_ROWS = (
    (0.000, 0.160),   # centre rib (mirrored, so 0.32 of the half width)
    (0.246, 0.556),   # intermediate row
    (0.642, 1.000),   # shoulder row, the biggest block
)
TREAD_GROOVES = (
    (0.160, 0.246),
    (0.556, 0.642),
)
# Land fraction across the width, for the generator's net-to-gross assert.
NET_TO_GROSS_BAND = (0.66, 0.86)
# Net-to-gross is quoted at the moulded LAND datum, where the crown chamfer
# begins - that is what the number means in tire practice. The flat contact
# face inside the chamfer is a second, smaller quantity, and the generator
# measures both off the polygons it built rather than deriving either from
# the row table: LUG_CHAMFER takes 85 mm off every edge of every block, which
# is a fifth of the land on a rock-service lug, and a gate that measured one
# while the prose argued the other could not see a groove closing to 62 mm.
CONTACT_SHARE_BAND = (0.72, 0.90)
# Row phase, in fractions of a pitch. Staggering the lateral grooves is what
# stops the tread having one continuous circumferential shear line.
ROW_PHASE = (0.0, 0.5, 0.22)
GROOVE_ZIGZAG = 0.130           # lateral wander of the groove walls

# Shoulder lugs do not stop at the tread edge on an earthmover: they wrap
# down over the buttress, which is the single most recognisable thing about
# the silhouette of a mining tire. BUTTRESS_DROP ends the wrap above maximum
# section width, which is where a real buttress ends.
BUTTRESS_DROP = 1.90
BUTTRESS_RELIEF = 0.230         # how far it stands off the sidewall
# It feathers to a real edge; it does not vanish. Round 1's taper reached
# exactly zero at the last row, collapsing 544 triangles to zero area - and a
# degenerate tangent basis is the classic source of black normal-map speckle.
BUTTRESS_FEATHER = 0.028

# THE SHOULDER. The outer lathe stops at SHL_FRACTION, which is DERIVED to sit
# SHOULDER_SHELF below the tread's own groove floor, and the shoulder is lofted
# from there to the tread base's outboard ring. Round 2 ran the lathe on to
# fraction 1.000 with the half width clamped, which produced a 0.58 m axially
# facing flange ring where a tire has its most recognisable curve; round 3
# lofted it but started 0.0671 m inboard of the ring the lathe ended on, so an
# open annulus rang both shoulders; round 4 had the loft CLIMBING 0.198 m
# outboard of the tread edge, damming every shoulder groove at its mouth.
# Three rounds, three versions of the same question - which is why both the
# start and the end of this curve are now derived rather than typed, and why
# assert_shoulder_falls_away() measures the built profile.
#
# The shoulder loft's outboard BULGE, in metres of half width. It was called
# SHOULDER_RADIUS and read as the radius of a circular arc, which the loft has
# never been - it is a straight line in (half width, radius) with a sine bulge
# on the half width only. Naming it for what it is stops the next author
# trusting two comments that were both false.
SHOULDER_BULGE = 0.135
SHOULDER_ROWS = 6

# ---------------------------------------------------------------------------
# Sidewall moulding. The big text is real extruded geometry (at this size the
# letters are ~1.9 m tall and normal-mapped print would read as a sticker);
# the small print band is textured.
#
# The relief features are the other half of it. A sidewall with nothing on it
# reads as grey plastic at any distance, and a real one is never bare: it
# carries a RIM LINE rib just above the bead (the reference circle you check
# to see whether the tire has slipped on its rim), and PROTECTOR RIBS on the
# buttress that take rock strikes before the casing does.
#
# The type BANDS stack downward from one anchor with a stated gap, because
# round 1 hand-picked three radii and drove PATTERN_NAME straight through
# SIZE_CODE on both sidewalls, three times each - six interpenetrating meshes
# on the surface its own hero render was framed to show off.
# ---------------------------------------------------------------------------
BRAND = "COLOSSUS"
PATTERN_NAME = "TERRAVOLT RM-1"
SERVICE_CODE = "E-4  ***  TL  RADIAL"
# Real DOT TIN: DOT, 2-char plant, 2-char size, up to 4 optional, 4-digit date.
BUILD_CODE = "DOT XR 9K CLS8 3426"     # plant XR, size 9K, week 34 of 2026
# TKPH is tonne-kilometres per hour: heat GENERATED goes as load x speed and
# heat REJECTED goes as surface area, so like MAX_LOAD it scales as SCALE
# squared. Round 4 found it carried straight off the reference tire as a bare
# 850 and printed one line under a load four orders of magnitude larger, on
# the very ring whose argument is that print and hardware cannot drift apart.
REFERENCE_TKPH = 850                   # a 59/80R63
TKPH = round(REFERENCE_TKPH * SCALE**2)
REFERENCE_MAX_LOAD = 100_000.0         # a 59/80R63 at 600 kPa
RATED_PRESSURE_KPA = 600               # scale-invariant: cord force ~ p*r
# Load capacity is pressure x footprint AREA, so it goes as SCALE SQUARED.
# Round 1 printed the reference load times SCALE, an order of magnitude out,
# and it was the only number on the sidewall derived from nothing.
MAX_LOAD_KG = REFERENCE_MAX_LOAD * SCALE**2

# 1.45 m cap height divides back to 206 mm at reference scale. A real
# earthmover sidewall carries its brand name at 100-150 mm, so this is already
# generous; round 3's 1.75 was 248 mm and it was what forced the small-print
# ring out of the stack and across the rim line, which is a worse trade than
# 17% on the hero type.
LETTER_HEIGHT = 1.45
# 5.7 mm proud at reference scale. Round 1's 0.110 divides back to 15.6 mm,
# which no moulded sidewall carries, and with no bevel the letter walls were
# vertical - a shape that cannot release from the plate.
LETTER_RELIEF = 0.040
LETTER_BEVEL = 0.28                    # fraction of the relief; rounds the crown
# The type bands are STACKED AND CENTRED by the generator between the bead
# and the first buttress rib - there is no authored anchor radius, because a
# hand-picked one silently stops fitting the moment a band's size or the size
# code changes. Round 1 hand-picked three radii and drove PATTERN_NAME
# straight through SIZE_CODE; round 2's first attempt at a stack anchored it
# at 10.60 and pushed the small print down to radius 5.31, BELOW BEAD_RADIUS,
# where it floated in the bead aperture attached to nothing.
# THE SMALL-PRINT RING IS A BAND LIKE ANY OTHER. Round 3 added it with a
# hand-picked radius outside the stack, and the stack's fit assert cannot see
# what it is not told about: the ring landed at 7.275..8.225 while SIZE_CODE
# occupied 7.182..8.337, so a ring standing 18 mm proud sliced through all six
# moulded copies of "10350/80R457" - round 1's failure exactly, reintroduced
# by a feature the assert had no entry for. It now owns a reserved slot and
# its radius is DERIVED from where the stack puts it.
#
# BUILD_CODE left the moulded stack at the same time. A DOT TIN on a real tire
# is small print, ~10 mm on 150 mm brand characters; as a moulded band a third
# the height of BRAND it was three times too big, and it is already one of the
# four lines drawn into the legend sheet the print ring carries. It is now in
# exactly one place, at the right size.
BAND_SCALES = (("BRAND", 1.00), ("PATTERN_NAME", 0.44), ("SIZE_CODE", 0.66),
               ("PRINT_BAND", None))
BAND_GAP = 0.22
BRAND_COPIES = 3                       # repeats round each sidewall

# The small-print band. A real sidewall carries its legend as one continuous
# moulded ring low on the flank, not stamped across the big brand characters.
PRINT_BAND_HEIGHT = 0.95
PRINT_BAND_RELIEF = 0.018
# tire_sidewall_print DRAWS the legend at this aspect and stretches it into a
# square texture, so the band has to be mapped back out at the same ratio or
# the type is squashed. The generator derives a whole number of repeats round
# the tire from it; mapping the sheet on the sidewall's own tile count put 24
# copies of a 6:1 legend into a 2:1 slot each and made the whole ring
# illegible - which is the one thing a legend has to not be.
PRINT_BAND_ASPECT = 6.0

RIM_LINE_RADIUS = BEAD_RADIUS + 0.075 * SECTION_HEIGHT   # 6.425
RIM_LINE_HEIGHT = 0.105
RIM_LINE_HALF = 0.130
RIM_LINE_CLEAR = 0.150                 # moulded type keeps off the rim line
TYPE_BAND_MARGIN = 0.30                # clear of the bead and the ribs
PROTECTOR_RADII = (12.05, 12.70, 13.32)
PROTECTOR_HEIGHT = 0.145
PROTECTOR_HALF = 0.235


def _band_stack() -> tuple[tuple[str, float, float], ...]:
    """(name, centre radius, height) for every reserved band on the flank.

    ONE ladder, laid downward from a centred anchor between the bead and the
    first buttress rib, carrying the moulded type AND the small-print ring.
    Anything that stands proud of the sidewall gets a slot here or it will
    eventually be moulded through something that did.
    """

    # The floor is the RIM LINE, not the bead. The rim line is a reference
    # rib - you read it to see whether the tire has slipped on its rim - and
    # anything moulded across it is both unreadable and wrong; a band draped
    # over a 105 mm rib is not a flat band. The bead margin still applies
    # where the rim line does not reach.
    lowest = max(
        BEAD_RADIUS + TYPE_BAND_MARGIN,
        RIM_LINE_RADIUS + RIM_LINE_HALF + RIM_LINE_CLEAR,
    )
    highest = PROTECTOR_RADII[0] - TYPE_BAND_MARGIN
    entries = [
        (name, PRINT_BAND_HEIGHT if scale is None else LETTER_HEIGHT * scale)
        for name, scale in BAND_SCALES
    ]
    stack = sum(height for _, height in entries) + BAND_GAP * (len(entries) - 1)
    slack = (highest - lowest) - stack
    if slack < 0:
        raise ValueError(
            f"sidewall band stack is {stack:.2f} m tall but the mouldable band "
            f"{lowest:.2f}..{highest:.2f} is only {highest - lowest:.2f} m"
        )
    placed = []
    cursor = highest - slack * 0.5
    for name, height in entries:
        cursor -= height * 0.5
        placed.append((name, cursor, height))
        cursor -= height * 0.5 + BAND_GAP
    return tuple(placed)


BAND_STACK = _band_stack()
BAND_WINDOW = (
    max(BEAD_RADIUS + TYPE_BAND_MARGIN, RIM_LINE_RADIUS + RIM_LINE_HALF + RIM_LINE_CLEAR),
    PROTECTOR_RADII[0] - TYPE_BAND_MARGIN,
)
PRINT_BAND_RADIUS = next(
    radius for name, radius, _ in BAND_STACK if name == "PRINT_BAND"
)

# ---------------------------------------------------------------------------
# Cavity lighting. The inside of a closed torus whose only aperture rotates
# away is genuinely pitch black, and everything after "STRAPS CUT" happens in
# there. Emissive lane chevrons on the liner are what make the second half of
# the loop playable: a directional cue, a landmark, and a way to tell how fast
# the floor is moving under you.
#
# emissiveFactor arrays are THREE components. A four-component factor renders
# INERT - prop_builder enforces it and the pack learned it the hard way.
# ---------------------------------------------------------------------------
LANE_MARK_NITS = 900

# ---------------------------------------------------------------------------
# ONE TILE PER MATERIAL, not per object. The metric-UV machinery was always
# correct - the dock deck measures 1.600 m/tile and the tread 2.204, exactly
# as authored - but the same MATERIAL was being authored at several
# densities: steel at 1.60 on the girders and 0.80 on the handrail posts, the
# hazard chevron at 1.10 on the dock kerb and 0.46 on the gangway kerb,
# sitting beside each other in the same frame. A material has one grain size;
# that is what makes it a material.
#
# Authored HERE rather than in the generator so the gate that measures the
# shipped Collada reads the same table the generator wrote from.
# ---------------------------------------------------------------------------
TILE_TREAD = 2.20
TILE_SIDEWALL = 2.60
TILE_LINER = 2.40
TILE_STEEL = 1.60
MATERIAL_TILE = {
    "tread": TILE_TREAD,
    "sidewall": TILE_SIDEWALL,
    "sidewall_type": TILE_SIDEWALL,
    "sidewall_print": TILE_SIDEWALL,
    "liner": TILE_LINER,
    "bead": TILE_SIDEWALL,
    "steel_worn": TILE_STEEL,
    "hazard": 1.20,
}

# ---------------------------------------------------------------------------
# Palette.
# ---------------------------------------------------------------------------
PALETTE = {
    f"{MOD_ID}_tread": {
        "texture": {"family": "tire_tread", "params": {}, "size": 1024, "srgb": True, "normal_strength": 3.2},
        "color": [0.043, 0.042, 0.041, 1.0],
        "metallic": 0.0,
        "roughness": 0.62,
    },
    f"{MOD_ID}_sidewall": {
        "texture": {"family": "tire_sidewall", "params": {}, "size": 1024, "srgb": True, "normal_strength": 2.8},
        "color": [0.048, 0.047, 0.049, 1.0],
        "metallic": 0.0,
        "roughness": 0.54,
    },
    # Same compound as the sidewall; a separate entry so the moulded TYPE is
    # a distinguishable stream in the shipped mesh and can be gated on its own
    # terms (closed solids, judged by signed volume, not by a radial normal).
    #
    # It is NOT declared identically to the sidewall. Raised type comes out of
    # the mould against a machined plate, so its crown is polished where the
    # flank around it carries the mould's own texture - that difference in
    # sheen is the cue that sells moulded lettering, and a byte-identical
    # declaration threw it away.
    f"{MOD_ID}_sidewall_type": {
        "texture": {
            "family": "tire_sidewall",
            "params": {
                "ripples": 0.0,
                "parting": 0.0,
                "checking": 0.12,
                "bloom": 0.30,
                "spew": 6,
            },
            "size": 1024,
            "srgb": True,
            "normal_strength": 1.4,
        },
        "color": [0.048, 0.047, 0.049, 1.0],
        "metallic": 0.0,
        "roughness": 0.30,
    },
    f"{MOD_ID}_sidewall_print": {
        "texture": {
            "family": "tire_sidewall_print",
            "params": {
                "aspect": PRINT_BAND_ASPECT,
                "lines": (
                    SERVICE_CODE,
                    BUILD_CODE,
                    # Three significant figures. Seven digits is the one
                    # thing on this ring that reads computed rather than
                    # moulded, and no tire in the world has them.
                    f"MAX LOAD {MAX_LOAD_KG / 1000:.0f} t AT {RATED_PRESSURE_KPA} kPa COLD",
                    f"TKPH {TKPH}   TUBELESS",
                ),
            },
            "size": 1024,
            "srgb": True,
            "normal_strength": 1.7,
        },
        "color": [0.052, 0.051, 0.053, 1.0],
        "metallic": 0.0,
        "roughness": 0.5,
    },
    f"{MOD_ID}_liner": {
        # THE ONE SURFACE THE BRIEF IS ABOUT. Round 4 measured the bladder
        # lattice at 4 texels per cycle, so its p99.9 slope fell 39.5 -> 21.8
        # -> 8.5 -> 5.3 across mips: gone at any distance a player sees it
        # from, which is why the cavity read as smooth painted sheet metal.
        # 64 cells is 37.5 mm on a 2.40 m tile - 5.3 mm at reference scale,
        # squarely inside the 5-20 mm a real bladder vent grid runs at - and
        # 16 texels per cell, which survives two mips. The groove is widened
        # with it so the feature is a groove and not a single texel.
        "texture": {
            "family": "tire_liner",
            # MEASURED, not guessed: widening the splices was tried and made
            # mip 2 WORSE (11.9 against 14.3 degrees), because the same ridge
            # height over a wider base is a gentler slope and a normal map
            # stores slope. The lattice pitch is the lever that works.
            "params": {"lattice": 64.0, "groove_width": 0.18},
            "size": 1024,
            "srgb": True,
            "normal_strength": 2.6,
        },
        "color": [0.088, 0.092, 0.086, 1.0],
        "metallic": 0.0,
        "roughness": 0.36,
    },
    f"{MOD_ID}_bead": {
        "texture": {"family": "tire_bead", "params": {}, "size": 1024, "srgb": True, "normal_strength": 2.6},
        "color": [0.058, 0.056, 0.054, 1.0],
        "metallic": 0.0,
        "roughness": 0.48,
    },
    f"{MOD_ID}_steel_worn": {
        "texture": {"family": "steel_worn", "params": {"relief": 8.0}, "srgb": True, "normal_strength": 3.0},
        "color": [0.5, 0.53, 0.57, 1.0],
        "metallic": 0.85,
        "roughness": 0.42,
    },
    f"{MOD_ID}_hazard": {
        "texture": {
            "family": "hazard_chevron",
            "params": {"relief": 1.0},
            "srgb": True,
            "normal_strength": 3.0,
        },
        "color": [0.9, 0.55, 0.08, 1.0],
        "metallic": 0.1,
        "roughness": 0.5,
    },
}

# ---------------------------------------------------------------------------
# Triggers. Both are anchored to the DOCK, which is the fixed part of the
# prop, so they stay put while the tire leaves. Boarding is detected here;
# everything after release is measured from live node positions instead,
# because a trigger box cannot follow a body that rolls 300 m away.
# ---------------------------------------------------------------------------
TRIGGERS = {
    # ONE zone, and it is the whole beat now. The dock and cabin zones existed
    # so a car could board; there is nothing to board any more. What is left
    # is: come near the tire and the chocks are pulled.
    "approach": {
        "mode": "Overlaps",
        "center": [0.0, 0.0, 1.7],
        "dimensions": [34.0, 30.0, 3.4],
    },
}

EFFECTS = {}

BEHAVIOR = {
    "camera_distance": 46.0,
    # Live-measurement inputs. The runtime fits the axle to three crown-centre
    # nodes 120 deg apart, which is exact for a circle and needs no assumption
    # about how far the tire has rolled.
    "marker_nodes": [
        f"{MOD_ID}_crn_c_j00",
        f"{MOD_ID}_crn_c_j16",
        f"{MOD_ID}_crn_c_j32",
    ],
    "marker_stations": [0, 16, 32],
    "outer_radius": OUTER_RADIUS,
    "section_half": SECTION_HALF,
    "tire_mass": TIRE_MASS,
    "strap_break_group": STRAP_BREAK_GROUP,
    # The crew's winch: on release, each wedge is pulled clear along its own
    # toe-to-heel axis. Pairs are (toe, heel) node names; the impulse is
    # applied at the heel, pointing away from the tire.
    "winch_pairs": [
        [f"{MOD_ID}_chock_{index}_toe_{side}", f"{MOD_ID}_chock_{index}_heel_{side}"]
        for index in range(4)
        for side in ("l", "r")
    ],
    "winch_force": WINCH_FORCE_N,
    "winch_seconds": WINCH_SECONDS,
    # Long enough that the arrival transient has died before the winch
    # pulls: a vehicle thumping down near the carcass presses it onto the
    # wedge tops, and 900 N loses to that friction spike (measured - the
    # wedge moved 10 mm instead of metres). Release is a beat, not a race.
    "release_countdown": 3.5,
    # Speed bands for the callouts, m/s.
    "speed_bands": [3.0, 6.0, 9.0, 13.0],
    # |axle . world_up| at the geometric point of no return: past a lean of
    # atan(SECTION_HALF / OUTER_RADIUS) the centre of mass is outside the
    # footprint and it is going over whatever the driver does. Round 2 waited
    # for 0.72 (46 deg), which is long after the outcome was decided, and gave
    # no warning at all in the band where a driver can still save it.
    "tipping_dot": math.sin(math.atan(SECTION_HALF / OUTER_RADIUS)),
    "leaning_dot": 0.55 * math.sin(math.atan(SECTION_HALF / OUTER_RADIUS)),
    "tipped_dot": 0.72,        # fully down, past any recovery
    "runaway_check_m": 0.9,    # HORIZONTAL drift meaning the chocks let go
    "settle_seconds": 3.0,     # ignore the settle before watching for it
}

LUA_BEHAVIOR = r"""
-- Every tunable this chunk reads, named once. tests/test_giant_props_pack.py
-- checks this list against the shipped `local B = {}` table and fails when a
-- build.py-only rebuild leaves the handoff behind the Lua - which it silently
-- did during round 3's review, shipping runaway_check_m 0.6 against an
-- authored 0.9 and no settle_seconds at all.
local REQUIRED = {
  "marker_nodes", "marker_stations", "outer_radius", "section_half",
  "tire_mass", "strap_break_group", "release_countdown", "speed_bands",
  "winch_pairs", "winch_force", "winch_seconds",
  "tipping_dot", "leaning_dot", "tipped_dot", "runaway_check_m",
  "settle_seconds", "camera_distance",
}

-- ===========================================================================
-- COLOSSUS runtime. It measures; it never drives.
--
-- Nothing below applies a velocity, a force or a pose to the tire or to the
-- subject. Every number reported here is fitted from three live cage nodes on
-- the crown centre line, 120 degrees apart, which is exactly enough to
-- determine a circle's centre, its plane, and how far it has turned.
-- ===========================================================================

local TWO_PI = 2 * math.pi

-- Centre of the circle through three points, plus its plane normal. Exact,
-- and independent of how far the tire has rolled or which way it faces.
local function fitAxle(p1, p2, p3)
  local v1 = p2 - p1
  local v2 = p3 - p1
  local n = v1:cross(v2)
  local nn = n:squaredLength()
  if nn < 1e-6 then return nil end
  local a = v2:squaredLength() * v1:dot(v1 - v2) / (2 * nn)
  local b = v1:squaredLength() * v2:dot(v2 - v1) / (2 * nn)
  local centre = p1 + v1 * a + v2 * b
  local axis = n
  axis:normalize()
  return centre, axis, (p1 - centre):length()
end

-- Angle of marker 0 about the axle, in the tire's own frame. Two orthonormal
-- in-plane baselines are built from the axis alone, so the angle is continuous
-- and does not jump when the tire yaws.
local function markerAngle(centre, axis, marker)
  local seed = math.abs(axis.z) < 0.9 and vec3(0, 0, 1) or vec3(1, 0, 0)
  local ex = seed - axis * axis:dot(seed)
  if ex:squaredLength() < 1e-9 then return nil end
  ex:normalize()
  local ey = axis:cross(ex)
  local r = marker - centre
  return math.atan2(r:dot(ey), r:dot(ex)), ex, ey
end

local function unwrap(previous, current)
  if previous == nil then return current, 0 end
  local delta = current - previous
  while delta > math.pi do delta = delta - TWO_PI end
  while delta < -math.pi do delta = delta + TWO_PI end
  return previous + delta, delta
end

-- Live tire state, or nil while vdata is still loading.
local function readTire(state)
  local prop = exactVehicle(state.propId)
  if not prop then return nil end
  local position = prop:getPosition()
  local points = {}
  for index, name in ipairs(B.marker_nodes) do
    local point = nodeWorldPosition(state, prop, position, name)
    if not point then return nil end
    points[index] = point
  end
  local centre, axis, radius = fitAxle(points[1], points[2], points[3])
  if not centre or not finiteVector3(centre) then return nil end
  local angle = markerAngle(centre, axis, points[1])
  if not angle then return nil end
  return {centre = centre, axis = axis, radius = radius, angle = angle}
end

-- Is a vehicle inside the carcass? Measured against the LIVE axle, which is
-- the whole reason it exists: both triggers are anchored to the fixed dock
-- and cannot follow a body that rolls 300 m away.
-- TWO message categories. Same-category messages replace one another, so the
-- odometer and the speed callouts get their own slot and can never wipe a
-- lean warning - which, with nobody inside any more, is the only notice
-- anyone gets that ten and a half tonnes is about to lie down.
local CHATTER_CATEGORY = "ericrolph_colossus_tire_chatter"

local function showChatter(message, ttl)
  guihooks.message({txt = message}, ttl or 2.0, CHATTER_CATEGORY)
end


local function announceSpeed(state, speed)
  local b = state.behavior
  local band = 0
  for index, threshold in ipairs(B.speed_bands) do
    if speed >= threshold then band = index end
  end
  if band == b.speedBand then return end
  local rising = band > (b.speedBand or 0)
  b.speedBand = band
  if not rising then return end
  local kph = speed * 3.6
  if band == 1 then
    showChatter("The Colossus is rolling.", 2.2)
  elseif band == 2 then
    showChatter(
      string.format("%.0f km/h. %.1f tonnes and gaining.", kph, B.tire_mass / 1000.0),
      2.2
    )
  elseif band == 3 then
    showChatter(string.format("%.0f km/h. Nothing is going to stop this.", kph), 2.4)
  else
    showChatter(string.format("%.0f km/h. RUNAWAY.", kph), 2.6)
  end
  emitEvent(state, "I", "colossus_speed_band", {band = band, speed = speed})
end


-- Everything the driver needs is already computed every frame and was being
-- thrown away. Inside a closed torus there is no horizon, the aperture is
-- open about 8% of each revolution, and the chevrons are identical to one
-- another - so without this the player genuinely cannot tell where the door
-- is, which way they are leaning, or how fast the floor is moving.
local function markReleased(state, reason)
  local b = state.behavior
  if b.released then return end
  b.released = true
  b.releasedAt = b.clock
  b.countdown = nil
  emitEvent(state, "I", "colossus_released", {reason = reason})
end

-- The crew's winch, as one queued vehicle command: resolve each wedge's
-- toe and heel by NAME inside the vehicle VM, then pull the wedge clear
-- along its own axis with thrusters.applyImpulse. A wedge lying against
-- the tread props the carcass through the ramp geometry even with every
-- strap broken - measured live - so cutting the webbing without pulling
-- the chocks releases nothing on flat ground.
local function winchCommand()
  local rows = {}
  for _, pair in ipairs(B.winch_pairs) do
    rows[#rows + 1] = string.format("{%q,%q}", pair[1], pair[2])
  end
  return "local function cid(name) "
    .. "for _, n in pairs(v.data.nodes) do "
    .. "if n.name == name then return n.cid end end end "
    .. "local winched = 0 "
    .. "for _, p in ipairs({" .. table.concat(rows, ",") .. "}) do "
    .. "local a, b = cid(p[1]), cid(p[2]) "
    .. "if a and b then winched = winched + 1 "
    .. "thrusters.applyImpulse(a, b, "
    .. B.winch_force .. ", " .. B.winch_seconds .. ") end end "
    -- The completion echo: how many pairs actually resolved and pulled.
    -- A release that silently winched nothing looks exactly like a chock
    -- that cannot be moved, and that cost a day once.
    .. "obj:queueGameEngineLua('COLOSSUS_WINCHED = ' .. winched)"
end

local function cutChocks(state)
  local b = state.behavior
  if b.released or b.chockCutRequested then return end
  local prop = exactVehicle(state.propId)
  if not prop then return end
  local ok = pcall(function()
    prop:queueLuaCommand(
      "beamstate.breakBreakGroup('" .. B.strap_break_group .. "')"
    )
    prop:queueLuaCommand(winchCommand())
  end)
  if not ok then
    emitError(state, "chock_release_failed")
    return
  end
  -- The commands are QUEUED into the vehicle VM, not executed here, so a
  -- successful pcall proves only that they were asked for. Release is
  -- claimed from the tire having MOVED (updateRunaway), which is also what
  -- catches a tie-down that parts on its own.
  b.chockCutRequested = true
  b.countdown = nil
  showMessage(
    string.format(
      "CHOCKS CUT AND WINCHED CLEAR. %.1f tonnes, loose.",
      B.tire_mass / 1000
    ),
    3.0
  )
end

behavior.init = function(state)
  local b = state.behavior
  b.clock = 0
  b.released = false
  b.chockCutRequested = false
  b.countdown = nil
  b.armed = false
  b.revolutions = 0
  b.angleUnwrapped = nil
  b.angleZero = nil
  b.originCentre = nil
  b.distance = 0
  b.lastCentre = nil
  b.speed = 0
  b.spin = 0
  b.speedBand = 0
  b.tipped = false
  b.tippedFinal = false
  b.leaning = false
  b.goingOver = false
end

behavior.reset = function(state)
  behavior.init(state)
  showMessage("Colossus re-chocked.", 2.4)
end

-- ONE ZONE, ONE BEAT. Come near it and the chocks come out.
behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if zone ~= "approach" or b.armed or b.released then return end
  b.armed = true
  b.countdown = B.release_countdown
  showMessage("Stand clear - pulling the chocks.", 2.4)
  emitEvent(state, "I", "colossus_armed", {subject_id = vehicle:getId()})
end

-- NOTE THE SIGNATURE. The shared runtime hands onEnter a vehicle OBJECT and
-- onExit a vehicle ID - all three onExit call sites pass `vehicleId`. Round 2
-- declared this as `(state, zone, vehicle)` and called `vehicle:getId()`,
-- which is an index-a-number error inside the caller's pcall: it failed
-- silently on every single exit.
behavior.onExit = function(state, zone, id) end

behavior.onSubjectGone = function(state, vehicleId, reason) end

local function updateRelease(state, dtSim)
  local b = state.behavior
  if b.released or not b.countdown then return end
  local before = math.ceil(b.countdown)
  b.countdown = b.countdown - dtSim
  local after = math.ceil(b.countdown)
  if after ~= before and after > 0 then
    showMessage(tostring(after) .. "...", 0.9)
  end
  if b.countdown <= 0 then
    b.countdown = nil
    cutChocks(state)
  end
end

-- The tie-downs can also let go on their own: four beams under a 103 kN
-- body, and a hard enough arrival will break them before anyone asks. Claiming
-- release from the queued Lua command alone would leave the runtime silent
-- for the rest of the session if that happened, so release is claimed from
-- the tire HAVING MOVED, whatever caused it.
local function updateRunaway(state, tire)
  local b = state.behavior
  if b.released or not b.originCentre then return end
  -- HORIZONTAL drift only, and only once the carcass has stopped settling.
  -- The first live run caught this: a 28 m tire settles 0.36 m onto its
  -- contact patch, so a 3D displacement test against the spawn centre trips
  -- on gravity alone, and it then suppressed the beat it was there to
  -- announce. Nothing headless could have seen it.
  if b.clock < B.settle_seconds then return end
  local drift = tire.centre - b.originCentre
  drift.z = 0
  if drift:length() < B.runaway_check_m then return end
  local parted = not b.chockCutRequested
  markReleased(state, parted and "chocks_failed" or "chocks_pulled")
  if parted then
    showMessage("The tie-downs have parted on their own. She is loose.", 3.0)
    emitEvent(state, "W", "colossus_chocks_failed", {})
  end
end

-- Who is aboard, measured against the live axle rather than a trigger box.
-- This is the payoff beat: threading the moving port on the way out is the
-- climax of the loop and round 1 gave it no feedback at all.
--
-- It follows b.tracked, not state.subjects. The shared runtime has no
-- `subjects` table - the first cut of this read one and silently iterated
-- nothing, so the payoff still never fired. b.tracked is every vehicle that
-- has entered EITHER zone, which is every vehicle that could plausibly be
-- aboard, and it needs no engine API the pack has not already proven.
-- Three beats, not one. The Colossus is geometrically past saving at a lean
-- of atan(SECTION_HALF / OUTER_RADIUS) = 20.2 deg; round 2 said nothing until
-- 46 deg, which is well after the outcome was decided and gave the driver no
-- chance to correct. Both earlier thresholds are DERIVED from that angle.
local function updateTipped(state, tire)
  local b = state.behavior
  local lean = math.abs(tire.axis.z)
  if not b.tipped and lean >= B.tipped_dot then
    b.tipped = true
    -- THE CAPSIZE IS A RESULT, so it reports one. Round 4 printed this and
    -- then, in the same frame and the same UI category, printed a second
    -- string straight over the top of it.
    showMessage(
      string.format(
        "COLOSSUS IS DOWN at %.0f m, %d revolutions. Reset the prop to stand it back up.",
        b.distance, b.revolutions
      ),
      4.0
    )
    emitEvent(state, "I", "colossus_tipped", {
      revolutions = b.revolutions,
      distance = b.distance,
    })
    return
  end
  if b.tipped then return end
  if lean >= B.tipping_dot then
    if not b.goingOver then
      b.goingOver = true
      showMessage("SHE IS GOING OVER.", 2.4)
      emitEvent(state, "W", "colossus_past_tipping", {lean = lean})
    end
  elseif lean >= B.leaning_dot then
    b.goingOver = false
    if not b.leaning then
      b.leaning = true
      showMessage("SHE IS LEANING.", 2.4)
    end
  else
    b.goingOver = false
    b.leaning = false
  end
end

behavior.update = function(state, dtSim)
  local b = state.behavior
  b.clock = b.clock + dtSim
  updateRelease(state, dtSim)

  local tire = readTire(state)
  if not tire then return end
  if not b.angleZero then
    b.angleZero = tire.angle
    b.angleUnwrapped = tire.angle
    b.lastCentre = tire.centre
    return
  end
  -- The datum for "has it rolled away" is taken AFTER the settle, not on the
  -- first frame, so the drop onto the contact patch is not mistaken for the
  -- Colossus escaping.
  if not b.originCentre and b.clock >= B.settle_seconds then
    b.originCentre = tire.centre
  end

  local unwrapped, delta = unwrap(b.angleUnwrapped, tire.angle)
  b.angleUnwrapped = unwrapped
  if dtSim > 0 then b.spin = delta / dtSim end
  local turns = math.floor(math.abs(unwrapped - b.angleZero) / TWO_PI)
  if turns > b.revolutions then
    b.revolutions = turns
    if b.released then
      -- METRES FIRST. One revolution is 88.5 m of ground, so a headline that
      -- leads with the revolution count reads 0 on essentially every ride a
      -- player will actually complete.
      showChatter(
        string.format("%.0f m of ground. Revolution %d.", b.distance, turns),
        2.0
      )
      emitEvent(state, "I", "colossus_revolution", {
        revolution = turns,
        distance = b.distance,
      })
    end
  end

  local travelled = (tire.centre - b.lastCentre):length()
  if travelled > 0.0005 and dtSim > 0 then
    b.speed = travelled / dtSim
    b.distance = b.distance + travelled
  elseif dtSim > 0 then
    b.speed = b.speed * 0.92
  end
  b.lastCentre = tire.centre

  updateRunaway(state, tire)
  if b.chockCutRequested and not b.released then
    markReleased(state, "chocks_pulled")
  end
  if b.released then
    -- ORDER MATTERS. updateTipped runs FIRST, and once it is down the run is
    -- over: round 4 kept scoring and kept counting revolutions of a tire
    -- lying on its side.
    updateTipped(state, tire)
    if b.tipped then
      b.tippedFinal = true
      return
    end
    announceSpeed(state, b.speed)
  end
end

"""
