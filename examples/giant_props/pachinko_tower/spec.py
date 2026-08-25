"""The Vertical Vehicle Pachinko Tower - authored constants for Blender + runtime.

A ~54 m pachinko board stood on end. The player drives into a lift carriage
at the base of the right-hand shaft (exactly where a real pachinko machine
feeds its balls). The chain hoist carries the carriage 43 m up the mast; a
counterweight rides the other side of the chain loop. At the top the release
gate (a hinged flap across the crown chute) swings open and the car is
EJECTED off the still-level deck: a horizontal velocity field walks it
inboard and a bounded KICKER impulse throws it airborne over the convex
hinge lip onto the crown chute's 40 deg ice, and from there into
a staggered field of 28 kite-section steel pegs on a FRICTIONLESS
groundmodel (mu = 0 exactly, read back out of the live engine). (The deck's 68 deg tip is
now an EMPTY-deck flourish that plays only after the car is gone - tipping an
occupied deck field-failed three times and is forbidden by THE CONFORMAL BAKE
LAW in BEHAVIOR.) The car ricochets down
into one of five scoring bins; the machine reads the car's real resting
position and reports the bin and its value.

The scoreboard is a MACHINE, not a message: a pointer trolley rides a rail
across the bin fascia and drives to the centre of the bin the car actually
landed in (past the end of the scale when the play scored nothing), and sweeps
the fascia as an attract mode while the tower waits. Textures cannot change at
runtime, so a part that moves to the answer is the honest readout a prop can
have. (That sentence used to end "and emissives are inert on this pipeline".
Retired 2026-08-15 by measurement - see THE EMISSIVE VERDICT below. The moving
pointer is still the right readout; it is no longer the ONLY one.)

Frames and hard engine facts this file is built on
--------------------------------------------------
* Authored frame: right-handed, meters, Z-up, +Y is the drive-in direction.
  The world renders authored (x, y) at (-x, -y); every constant below is
  authored, and the runtime's toWorldPoint/toWorldDir do the flip.
* A runtime TSStatic's static collision is a SNAPSHOT that only refreshes on
  be:reloadCollision(). A continuously moving platform therefore cannot carry
  a car by contact. Two consequences drive the whole design:
    - the hoist carries the car with a capped vertical velocity servo (the
      support impulse a floor would apply), never a position write;
    - the release EJECTS the car across the LEVEL deck with a horizontal
      velocity field, over the hinge lip onto the chute's static ice; the
      tip is an empty-deck flourish afterwards, with no bake. (Two designs
      were tried and field-failed 2026-08-13: detent snaps teleport the
      plate through the car, and servo-carrying a LEVEL car along a
      tipping plate's arc ends with an endpoint bake standing a 68 deg
      wall through the middle of the car - THE CONFORMAL BAKE LAW in
      BEHAVIOR tells that story.)
  Two corollaries the first cut missed. (1) A bake at a pose the deck is only
  PASSING THROUGH leaves an invisible collision plate hanging in mid-air for
  as long as the stroke lasts, so bakes happen only at poses the deck actually
  STOPS at - home and docked - and the deck is levelled before it
  is lowered rather than at the same time. (2) The support servo that carries a
  car UP has no downward mirror: on the way down the stale plate is above the
  target and the car is resting on it, and velocity cannot push a car through a
  solid surface. The carriage therefore interlocks at the crown rather than
  pretending it can lower a load (updateReturning says this at length).
* THE HIDDEN-WORK LAW (2026-08-14h, and the most expensive thing in this file
  to rediscover). BEFORE YOU REMOVE A CRUDE BEHAVIOUR, FIND OUT WHAT IT WAS
  DOING FOR YOU. The hoist used to STOP DEAD at the dock, and the car - which
  is in free flight on a velocity servo, not standing on anything - sailed
  1.1 to 4.8 m past the plate and fell back onto it. That looked like nothing
  but a defect, and the player duly reported it as one ("the momentum makes
  lighter vehicles fly up when it stops"). It was also THE ONLY THING RIGHTING
  THE CAR. Nothing in this engine can apply a torque (see THE TWO-CONTACT LAW
  below), so a car that picks up any rotation at lift-off arrives at the crown
  tilted, and the LANDING - contact, the one attitude fix that exists - was
  what flattened it out again. Deleting the overshoot with a clean ease-out
  took arrival tilt from 2.6 to 15.1 degrees and the score from 10 of 14 to
  ZERO of 8, every play stalling on the deck lip. The ease-out was right and
  it shipped; it just had to buy the landing back deliberately
  (hoist_seat_lift_m + dock_seat_dv_mps, see seatLiftNow and updateDock).
* THE DROOP LAW (2026-08-14h). A PARKED CAR AND A FLYING CAR ARE DIFFERENT
  HEIGHTS, and the number this file measures is the parked one. car_rest_height
  is sampled from the REF NODE while the car sits on the loading floor with its
  suspension COMPRESSED. For the whole ride it is in free flight, and a car in
  free flight DROOPS: measured on the attitude probe, ref-to-lowest-node grows
  0.40-0.43 m between lift-off and the crown, every play. So a car held at
  exactly restHeight has its ref node in the right place and its WHEELS 0.4 m
  BELOW THE PLATE, and the dock bake then stamps the deck straight through
  them. This is THE CONFORMAL BAKE LAW again, in the direction nobody was
  watching: the fix is not to move the bake, it is to lift the SERVO clear by
  more than the droop. The old overshoot hid this completely, because a car
  1.1 m above the plate is above it wheels and all.
* Zone triggers fire on CROSSINGS. A car standing inside a box when the
  machine comes home never re-enters it, so the idle branch polls load_zone
  occupancy as well as listening for entries.
* Every dimension below is derived from the BeamNG compact-car reference:
  2.0 m wide, 4.5 m long, 1.5 m tall.
"""

import math

MOD_ID = "ericrolph_pachinko_tower"
DISPLAY_NAME = "Vertical Vehicle Pachinko Tower"
VALUE_DOLLARS = 95000
ZIP_BASENAME = "pachinko_tower_ericrolph.zip"

# ---------------------------------------------------------------------------
# Reference vehicle. Everything downstream is derived from these three numbers
# so the peg pitch, bin width and doorway sizes are not magic.
# ---------------------------------------------------------------------------
CAR_WIDTH = 2.0
CAR_LENGTH = 4.5
CAR_HEIGHT = 1.5
# Worst-case silhouette of a tumbling car in the fall plane's DEPTH axis:
# it can present its full length-height diagonal across the board depth.
CAR_DIAGONAL = math.hypot(CAR_LENGTH, CAR_HEIGHT)  # 4.743 m
# The BODY CHORD: the longest straight line through the car in ANY orientation.
# This - not the width, and not the fall-plane diagonal - is the number the peg
# lattice has to beat, because a wedge does not care which way the car is
# pointing: whatever chord it presents into a converging throat is what has to
# be longer than the throat for the throat to arrest it.
CAR_CHORD = math.sqrt(CAR_LENGTH**2 + CAR_WIDTH**2 + CAR_HEIGHT**2)  # 5.148 m

# ---------------------------------------------------------------------------
# The board (the fall volume). X = scatter axis, Z = fall axis, Y = depth.
# ---------------------------------------------------------------------------
FIELD_HW = 12.0
# 3.45 -> 6.90 m clear depth = 1.45 x CAR_DIAGONAL. A car that lands nose-down
# and rotates about the depth axis still cannot bridge front screen to
# backboard, so it can never jam across the board. Asserted, not asserted-in-
# prose: a comment that claims a derivation and a constant that no longer
# satisfies it is exactly how these files rot.
DEPTH_HALF = 3.45
assert 2 * DEPTH_HALF >= 1.45 * CAR_DIAGONAL, "board depth no longer clears a tumbling car"
WALL_T = 0.70  # visual wall thickness, built OUTBOARD of the collision plane

BIN_COUNT = 5
BIN_PITCH = 2.0 * FIELD_HW / BIN_COUNT  # 4.80
# Rounded to the micrometre and de-negative-zeroed: without it the centre bin's
# centre serialized into the shipped runtime.lua as -8.881784197001252e-16, and
# the generator's "is this the divider next to the jackpot" test had to compare
# against a tolerance instead of a number.
BIN_EDGES = [round(-FIELD_HW + BIN_PITCH * i, 6) + 0.0 for i in range(BIN_COUNT + 1)]
BIN_CENTERS = [
    round((BIN_EDGES[i] + BIN_EDGES[i + 1]) / 2.0, 6) + 0.0 for i in range(BIN_COUNT)
]
BIN_FLOOR_Z = 0.35
# Bin mouth plane == divider ridge height. 4.65 m of pocket above the floor is
# deeper than a car is tall (1.5) plus its bounce, so a car that drops in stays
# in; and the score is read at this plane.
RIDGE_Z = 5.00

# ---------------------------------------------------------------------------
# THE FALL VOLUME IS FRICTIONLESS TO ITS WALLS (2026-08-14i, serial 75).
# ---------------------------------------------------------------------------
# The peg field has been mu = 0 since 2026-08-14h and the dividers and chute
# with it - but the BOX AROUND THEM was still vanilla `metal`, mu 0.85 static
# / 0.65 sliding (read out of gameengine.zip art/groundmodels.json, not
# assumed). So the machine was a frictionless obstacle course inside a sticky
# box, and that combination is not a detail: it is what makes a rest possible
# at all.
#
# THE ARITHMETIC, which is why this is a fix and not a tuning knob. A rest
# needs the contact wrenches to span the gravity wrench - three equations in
# the x-z plane (two force, one moment). A frictionless contact contributes
# ONE generator (its normal), so two frictionless contacts give two generators
# for three equations and CANNOT balance: the 10^8-pose sweep that closed the
# 2026-08-14i design round found 0 stable rests at mu = 0 over 4 silhouettes,
# 60 attitudes, 53k positions, up to 7 contacts, 8 lattice variants and 0.20 m
# of compliance - against 502 to 2290 at mu = 0.4. The peg lattice by itself
# cannot hold a car in any pose.
#
# A METAL WALL PUTS THE MISSING GENERATOR BACK, and it puts it back in exactly
# the plane where it does the damage. A car draped on a peg flank (outward
# normal (0.838, 0.545), 33 deg above horizontal) has to ROLL OFF the crown to
# fall, and that roll happens in the x-z plane - which is the plane a board
# face's friction cone opens into. The wall is not a bystander to the hang; it
# is the second contact that makes the hang feasible.
#
# WHICH THE LIVE CENSUS ALREADY SAID, before anyone did the algebra: 56 plays
# on the shipped lattice, 16 hangs (28.6%), and 10 of the 13 FIELD hangs had
# the x = 0 centre column as nearest peg with 11 of 13 on an odd (3-column)
# row - cars draped over ONE peg, not wedged between two. One peg plus one
# board face is a two-contact rest that only exists because the face has grip.
#
# SO THE INVARIANT IS NAMED, NOT COMMENTED. Every collision triangle whose
# three nodes all lie inside the fall volume must carry
# FALL_VOLUME_GROUNDMODEL, asserted in the generator against the BUILT cage
# (assert_fall_volume_frictionless) rather than against the source call list,
# so a future surface dropped into this volume fails at import instead of in
# the player's game.
#
# THE Z FLOOR CAME DOWN TO THE BIN FLOOR (2026-08-15, serial 79), AND THAT IS
# THIS ROUND'S WHOLE FIX. The serial-75 treatment stopped at RIDGE_Z = 5.00 on
# the reasoning that "above the bin mouth a car is FALLING, at and below it a
# car is IN a bin". That sentence is true about INTENT and false about
# GEOMETRY, and the serial-78 census proved it: all five surviving concessions
# sat in the BIN MOUTH, rest_z 3.17 to 4.73, for 23.9 to 48.5 s - i.e. one
# metre BELOW where the frictionless treatment stopped. The give-up telemetry
# named the second contact outright: clear_y_front <= 0 on four of the five,
# the node cloud pressed into the front depth face.
#
# THE MECHANISM, EXACTLY. `in_fall_volume` was z > FALL_VOLUME_Z_LO STRICT and
# a quad only goes frictionless when ALL FOUR corners are inside. The wall
# grids carry a node station at z = 5.00, so the band from 5.00 to 6.00 - the
# lowest band of the front face, which only exists from RIDGE_Z up at all -
# had its bottom corners exactly ON the excluded plane and stayed `metal`. The
# conceded cars measured node_z_hi 5.38 to 6.11. They were resting against the
# one metal band the serial-75 change left behind, and they were resting
# against it because it was the only gripping face still in reach.
#
# So the treatment now runs from BIN_FLOOR_Z, and the same wrench-count
# argument that justified it above the ridge justifies it below: at mu = 0 a
# two-contact rest is arithmetically impossible, and a bin mouth is not a
# different defect from a peg field, it is the same defect one metre lower.
#
# THE RULE THAT SEPARATES BOARD FROM FLOOR, stated because "everything below
# the ridge is drive-on" was the wrong rule and cost a round. The volume is
# now the full box from the bin floor to the wall top, and membership of it is
# decided by geometry, not by height:
#
#   A collision face inside the box is FRICTIONLESS unless it lies IN THE
#   BIN-FLOOR PLANE ITSELF (all three of its nodes at z == BIN_FLOOR_Z).
#
# That is the drive-on/board split expressed as the thing it actually is - a
# floor is horizontal at the one height cars park at; a board face is
# vertical. It has exactly one member on the exempt side, `binfloor`, and it
# is checked on the built cage, so a future horizontal surface dropped into
# the pocket does not get the exemption by accident: it has to be at the bin
# floor height to qualify, and if it is not, it must be frictionless.
#
# THE BIN'S WALLS GO FRICTIONLESS AND ITS FLOOR DOES NOT, which is the split
# the pocket needs and could not have before. A scored car sits on asphalt at
# friction 1.0 and drives out over the asphalt exit apron exactly as it did;
# what it can no longer do is hang itself on the pocket's SIDES on the way in.
#
# WHAT IS STILL DELIBERATELY OUTSIDE THE BOX, and why each one is safe -
# verified against the built cage by the fence, not asserted from the source
# list. Every remaining drive-on surface is excluded by x or by y, never by z,
# so lowering the z floor could not reach any of them:
#   * `dockfloor`, `loadramp`  x spans 12.00 -> 18.60, outboard corners
#   * `guard`                  x = DOCK_X1 = 18.60
#   * `wouter`                 x = SHAFT_X1 = 23.00
#   * `pitfloor`               x in {18.60, 20.40, 23.00}
#   * `island`                 y = LOAD_GROUND_Y = -12.00
#   * `exitramp`               y in {-6.50, -14.50}, both past DEPTH_HALF
#   * `binfloor`               inside the box, exempt by the bin-floor plane
# `binfloor` is the ONLY surface the exemption exists for, and only its two
# inboard y bands are inside the box at all; its outer band reaches
# y = -6.50 and leaves by depth.
#
# THE ONE SHARED FACE, stated because it is a real trade. `wright` at
# x = +FIELD_HW is the fall volume's right-hand board AND the shaft's inboard
# wall, one node grid, double-sided triangles - so the carriage now rides up
# beside a frictionless face. Nothing in the hoist leans on that face for
# grip: the car is carried by the carriage plate under it, and the shaft's
# other three sides are unchanged. Splitting the surface to give the two sides
# different models is NOT available - see the node-id note below.
#
# WHY IT COULD NOT BE DONE BY ADDING A SURFACE. `back`, `front`, `wleft` and
# `wright` are single store.surface() calls, and the vehicle-side audio binds
# to literal node id 0. Splitting any of them into a new named surface
# reorders the node list and moves that binding. The generator therefore takes
# a PER-QUAD groundModel selector, so node names, ids, count, order, positions
# and masses stay bit-identical and only the groundModel string moves.
FALL_VOLUME_GROUNDMODEL = "frictionless"
# The box now starts at the bin floor and membership in z is INCLUSIVE, so the
# bin-floor plane is inside it and is excluded by the named exemption below
# rather than by an off-by-one on a strict inequality. That is deliberate: the
# strict inequality is exactly what left the 5.00 -> 6.00 band metal, and a
# rule that depends on which side of a floating-point comparison a node
# station lands on is not a rule.
FALL_VOLUME_Z_LO = BIN_FLOOR_Z
# The one exempt plane: horizontal collision faces at the bin floor height are
# what a scored car parks on and drives out over, and they keep their asphalt.
# Nothing else in the box may claim this exemption - see the split rule above.
FALL_VOLUME_DRIVE_ON_Z = BIN_FLOOR_Z
assert FALL_VOLUME_Z_LO <= FALL_VOLUME_DRIVE_ON_Z < RIDGE_Z, (
    "the drive-on exemption plane must lie inside the fall volume and below "
    "the bin mouth, or the exemption is either unreachable or covering board"
)

# ---------------------------------------------------------------------------
# THE FRICTION LEVER IS NOW SPENT, AND IT WAS NEVER THE WHOLE MECHANISM.
# READ THIS BEFORE PROPOSING ANOTHER GROUNDMODEL OR LATTICE ROUND.
# (2026-08-15, serial 79, measured.)
# ---------------------------------------------------------------------------
# STATE OF THE LEVER. Every collision triangle a falling car can reach is now
# mu = 0: the peg field, the dividers, the chute, and - as of this serial -
# all four board faces from the BIN FLOOR to the wall top. The fence proves
# it against the built cage (0 non-frictionless triangles inside the volume).
# There is no gripping surface left in the fall path to take away.
#
# AND CARS STILL STOP ON ~70% OF RELEASES. Serial 79, three seeded sessions,
# car repaired between plays, first two cycles of each session discarded:
# `raps == 0` - the fraction of releases where the car never stopped at all -
# came out around 30%, against 24% for serial 78 and 8% for the serial 74
# control measured the same way. The direction is right and the size is not
# nearly enough, and one more surface cannot be the answer because there is
# no surface left.
#
# WHY, AND IT IS NOT SUBTLE. THE WRENCH-COUNT ARGUMENT THIS FILE IS BUILT ON
# IS A RIGID-BODY ARGUMENT, AND THE THING FALLING IS NOT A RIGID BODY.
# "Two frictionless contacts give two generators for three equations and
# CANNOT balance", and the 10^8-pose sweep that found 0 stable rests at mu = 0
# - both of those are statements about a rigid silhouette. The give-up
# telemetry measures the actual object, and it is nowhere near rigid:
#
#   node-cloud extent at the moment the machine concedes, every build that
#   has the telemetry, against a car whose own tumbling diagonal is 4.74 m:
#
#     serial 77   diagonals  9.88   7.80  17.21 m
#     serial 78   diagonals 12.83  13.85  10.63   8.13  10.62 m
#     serial 79   diagonals 13.51  14.38   9.69 m
#
#   Not one is under 7.8 m. The median is about 2.5x the car's own diagonal,
#   and these are only the nodes within the telemetry's +/-6 m plausibility
#   clamp - the true extent is larger, because the clamp is discarding the
#   rest (node_n reads 632-767, not the whole cloud).
#
# A shell deformed to two or three times its own diagonal does not touch a
# peg at two points. It WRAPS it. A wrap is a continuum of contact normals
# spanning a wide angular range, and a set of normals spanning a wide enough
# range spans the gravity wrench ON ITS OWN - with no friction anywhere. That
# is why mu = 0 did not close this out and why no achievable mu could: the
# frictionless proof does not apply to the object in question.
#
# WHAT THIS RULES OUT FOR THE NEXT ROUND, so the same ground is not bought
# twice:
#   * more groundmodel work. The volume is already mu = 0 throughout.
#   * any lattice re-cut justified by RIGID-body feasibility. The 200k-point
#     (phase, pitch, radius) search that returned 0 feasible designs was
#     scored against rigid poses, so it was answering a question about a
#     steel ball while a deformable car was the thing falling. Its "0" is not
#     evidence about this failure mode in either direction.
#   * the retract ladder. It is a rescue for a car that has already stopped;
#     it cannot make a car not stop, which is the actual bar.
#
# AND IT SUSPENDS MOST OF THE "ALREADY SPENT" LIST. The rulings that the
# lattice cannot be re-cut, that the 6.10 m chord-clean pitch is dead, that a
# 3-phase stagger is worse, that depth stagger fails, and that peg RADIUS is
# spent at a 0.857 m floor were ALL decided by the same two searches - the
# 200k-point (phase, pitch, radius) grid and the 10^8-pose compliance sweep -
# and both scored RIGID poses against a fixed 5.148 m car chord. None of them
# is evidence about a shell deformed to 2-3x its size. They are suspended,
# not refuted: someone has to re-derive them against a WRAPPING criterion
# (can the deformed shell get around this pin?) instead of a CHORD criterion
# (can a rigid body bridge or wedge between these pins?), and radius is the
# one most worth reopening, because a shell can wrap a thin pin and cannot
# wrap a fat one.
#
# THE ONE RULING THAT SURVIVES UNTOUCHED is the subset-map law: a peg may
# only contract about its own axis, never translate or rotate. That is a
# geometric containment argument about not sweeping steel through a car, and
# it does not depend on anything being rigid. See
# assert_peg_retract_is_subset_map.
#
# A CUSTOM GROUNDMODEL CANNOT SOFTEN THE COLLISION. RULED OUT BY PROBE, NOT
# BY ARGUMENT (2026-08-15). The hope was that defining our own groundmodel
# instead of reusing vanilla FRICTIONLESS might expose a contact-stiffness or
# restitution knob - which would sidestep the flexbody and retract conflicts
# that make node compliance expensive. It does not exist. Parsed out of the
# shipped gameengine.zip art/groundmodels.json, all 32 engine groundmodels
# between them use exactly these fields and no others:
#
#   friction        staticFrictionCoefficient, slidingFrictionCoefficient,
#                   hydrodynamicFriction, stribeckVelocity, roughnessCoefficient
#   deformable      shearStrength, defaultDepth, fluidDensity,
#     TERRAIN       flowConsistencyIndex, flowBehaviorIndex, dragAnisotropy
#   presentation    collisiontype, skidMarks, aliases
#   misc            strength (only ever 0, 1 or 10)
#
# A regex for stiff|restit|damp|bounce|elast|spring|compl over every field
# name in the file returns NOTHING. The deformable-terrain group is how deep a
# WHEEL sinks into mud, sand or snow - it is not contact softness against a
# collision triangle on a prop, and a prop's triangles do not sink. So the
# groundmodel is a friction surface and only a friction surface, this project
# has already taken it to mu = 0, and there is no second knob behind it.
#
# THE UNTOUCHED LEVER, and it is the whole other side of the collision:
# EVERY NODE OF THIS MACHINE IS `fixed: true`. All 960 peg nodes, and in fact
# all 1382 nodes of the prop, are welded to the world - so the 4503 beams
# never deflect and every pin is an immovable piston. A real pachinko ball
# plinks because the BALL is rigid; ours cannot be, so the only compliance
# available is on the pin side, and there is currently none anywhere. A car
# falling 40 m (about 28 m/s unimpeded) meets steel with infinite effective
# mass, eight rows in a row. Giving the pins real give - non-fixed nodes on
# stiff-but-finite beams back to fixed anchors - is the first thing that
# would attack peak deformation per strike rather than its consequences, and
# nobody has tried it. It is not free: the retract writes peg node positions
# directly, the single flexbody is skinned to those same nodes, and both
# assume the nodes do not move on their own. That is a round's work, not a
# footnote, and it should be sized against the measurement below.
# ---------------------------------------------------------------------------
# Divider cross-section, (half-width, z) from the bin floor to the ridge.
# The WIDEST point is what sets the drive-out throat, so the fillet is the
# governing number: 4.80 - 2 x 1.00 = 2.80 m of flat bin floor, i.e. 0.40 m
# each side of a 2.0 m car. (First cut used a 1.35 fillet base and a 1.00
# body; the cage raycast measured the real throat at 2.10 m - 5 cm of
# clearance per side - which is why the fillet now tapers inward from 1.00.)
# The 1.00 -> 0.80 taper still gives a scraping tire a 53 deg ramp to climb
# instead of a square corner.
DIVIDER_PROFILE = [(1.00, BIN_FLOOR_Z), (0.80, 0.62), (0.80, 3.00)]
DIVIDER_RIDGE_Z = RIDGE_Z
# The two dividers flanking the middle bin lean their ridges 1.10 m inward, so
# the jackpot mouth is 4.80 - 2 * 1.10 = 2.60 m: a 2.0 m wide car only drops in
# if it arrives near-vertical or well aligned. That, not a dice roll, is what
# makes the middle bin the hard one.
CENTER_HORN_LEAN = 1.10
# Dividers run 3.05 m past the front screen plane to flank the drive-out lane.
DIVIDER_Y_FRONT = -6.50
# Drive-out apron: bin floor -> grade at 4.4% (0.35 m over 8.0 m).
EXIT_GROUND_Y = -14.50

# ---------------------------------------------------------------------------
# Peg field. Diamond-section (square bar rotated 45 deg) steel pegs running the
# full board depth, exactly like a pachinko pin sticking out of the board.
# ---------------------------------------------------------------------------
# ROW COUNT, ROW PITCH, PEG SECTION AND COLUMN COUNT ARE ONE DECISION, and the
# thing they trade against each other is THE TWO-CONTACT LAW. The whole block
# was re-derived 2026-08-14, after the shipped 65-peg field let only ~3 plays
# in 15 reach a scoring bin.
#
# THE TWO-CONTACT LAW (2026-08-14). Three measurements, one conclusion:
#
#   1. THERE IS NO TORQUE, AND IT IS NOT AN ARTEFACT OF WHICH API IS USED.
#      Probed twice. GE side: the same impulse through the ref node and through
#      a node 2.71 m off-centre produced identical yaw and displacement, because
#      applyClusterVelocityScaleAdd translates the whole cluster. VEHICLE side
#      (probed 2026-08-14f, because the first law only covered the GE API):
#      obj.applyForceVector, obj.applyForce and
#      obj.applyClusterLinearAngularAccel all EXIST inside the car - and a
#      couple of +/-4000 N applied to two nodes 4.67 m apart, ~18.7 kN.m, which
#      should have rotated the body about 8 degrees in the 0.2 s window,
#      produced 0.27 degrees - LESS than the 0.96 degrees the same forces
#      produced in the SAME direction as a pure-translation control, and both
#      at noise level. The soft-body lattice absorbs a node force locally,
#      deforming the structure around it instead of accelerating the body.
#      SETTLED: no script in this engine, on either side, can apply a useful
#      righting torque to a car. Every attitude fix must be geometric or must
#      come from CONTACT. Do not re-open this. Probed live: the same impulse delivered through the
#      ref node and through a node 2.71 m off-centre produced identical yaw and
#      identical displacement. A car body is ONE physics cluster and
#      applyClusterVelocityScaleAdd is a pure translation, so a wedged car can
#      never be rotated free. Un-wedging is purely GEOMETRIC - no knocker tune
#      can ever be the fix, which is why every previous round failed.
#   2. VANILLA `ICE` IS NOT FRICTIONLESS. mu_static = 0.4, i.e. a 21.8 deg
#      friction angle, so any support shallower than that holds a car outright.
#      That is why "make the pegs slippery" never cured a hang.
#   3. THEREFORE a peg's 45 deg FACES are not rests (45 > 21.8: a car slides
#      off), and a single crown is a knife edge that rolls out. Every hang in
#      this machine is a TWO-CONTACT pose - either a flat car face bridging two
#      CROWNS (a level table, which needs no friction at all) or a car jammed
#      in the converging THROAT between neighbouring pegs (which arrests a
#      rigid body at any face angle, so only throat WIDTH cures it).
#
# The lattice must therefore satisfy three inequalities at once (a fourth
# pair, the wall reach, was added 2026-08-14h when the circular section made
# it binding - see the PEG_R block):
#   * crown spacing  > CAR_CHORD          - no two crowns can table a car
#   * throat width   > CAR_CHORD          - no throat can pinch one
#   * half-pitch lane < CAR_WIDTH         - the staggered row still blocks
#                                           every lane, so no free chute opens
# The first two push the PITCH up past 5.148 m; the third pulls the HALF pitch
# down. With a small peg both cannot hold at once, so the lattice necessarily
# gets coarser and the pegs BIGGER together: 10 rows of 0.60 m pegs at 3.70
# became 7 rows of 1.10 m pegs at 7.60, and 65 pegs became 25. A rigid-body
# scan over a fine pose grid found 544 stable resting poses in the old field
# and ZERO in this one, holding at mu 0.4, 0.7 and 1.0.
#
# Per-row frontal steel barely moved - 36.7% on the even rows and 27.5% on the
# odd, against the old 35% / 39.6% - so the board still presents the same
# amount of obstacle per row; it is the same steel in fewer, fatter pins.
#
# Rows land at z 40 / 36 / 32 / 28 / 24 / 20 / 16 / 12. Bottom row 12.00 leaves
# 12.00 - PEG_R_Z_DN 0.40 - RIDGE_Z 5.00 = 6.60 m of clear drop onto the ridges,
# past the >= 4.0 m assert below. It is longer than the 4.74 m tumbling
# diagonal, so unlike every previous field a nose-down car can no longer
# bridge the bottom row to a ridge.
# F3, THE PEG PARITY (2026-08-14c). PEG_ROWS was 7 - ODD - so the BOTTOM row
# was an EVEN row, with columns at +/-3.80 and +/-11.40 and its gaps centred on
# 0 and +/-7.60. That put 5.40 m of clear air directly over the 2.60 m jackpot
# mouth with 6.60 m of unobstructed drop below it: the jackpot was the only bin
# in the machine fed by a STRAIGHT DROP while every other bin was fed by
# ricochet, which is why it took 3 of 8 scores live on build 36 and inverted
# the story the fascia tells. Eight rows makes the bottom row ODD - a peg
# standing over the jackpot mouth, and the gaps landing on the bin-1 and bin-3
# floors instead.
#
# The extra row is bought at the TOP, which is the only free direction: the
# bottom row stays at 12.00 so the clear-drop assert is untouched, row 0 stays
# EVEN so the wall reach and assert_no_clean_column are unchanged, and the new
# top row's crest at 41.69 still clears the crown chute's underside (42.39 at
# x 11.40, asserted below). It also answers the "the flat elevation reads
# vertically empty" note from the build-36 aesthetic pass for free.
PEG_ROWS = 8
PEG_TOP_Z = 40.00
PEG_ROW_PITCH = 4.00
# THE SECTION IS A CIRCLE SINCE 2026-08-14h (the player: "make the geometry of
# the pins smaller in diameter and circular"). PEG_R is now the RADIUS - the
# half-width in x AND the reach in z, both ways - where it used to be the
# half-width in x only, of a KITE with a 1.55 m spike above and a 0.40 m
# underside below.
#
# HOW SMALL A CIRCULAR PEG IS ALLOWED TO BE, WHICH IS NOT A FREE CHOICE. Four
# inequalities have to hold at once, and every one of them is a function of the
# radius R and the pitch p alone:
#
#   throat    p - 2R > CAR_CHORD              no pair in a row can wedge a car
#   lane      p/2 - 2R < CAR_WIDTH            the staggered row still blocks
#                                             every lane, so no free chute
#   wall in   1.5 p + R >= FIELD_HW           the outermost even peg reaches
#                                             INTO the wall, closing the side
#                                             channel (see WHY THE WALL STUBS
#                                             ARE GONE)
#   wall out  1.5 p + R <= FIELD_HW + WALL_T  ...and does not punch through it
#
# Take the first two alone and they give CAR_CHORD + 2R < p < 2 CAR_WIDTH + 4R,
# which has a solution only for R > (CAR_CHORD - 2 CAR_WIDTH) / 2 = 0.574 m.
# THAT NUMBER IS A TRAP, and it is the one this round started from. It ignores
# the wall. Put the wall constraints in - with PEG_COLUMNS_EVEN = 4 the
# outermost peg centre is at 1.5 p, so the pitch is bounded BELOW by
# (FIELD_HW - R) / 1.5 as well - and the feasible window closes at
#
#   (FIELD_HW - R) / 1.5 < 2 CAR_WIDTH + 4R  ->  R > (FIELD_HW - 3 CAR_WIDTH)/7
#
# i.e. R > 0.857 m. Below that NO pitch exists that both closes the side
# channel and keeps every lane blocked, and the honest peg-radius floor on this
# board is 0.86, not 0.57. Asserted below in both forms so the trap cannot be
# walked into again.
#
# ...AND THE PRICE OF EVERY CENTIMETRE OFF THE PEG, stated as the law it is.
# The pitch cannot go below the throat bound, so the narrowest the half-pitch
# lane can ever be is
#     lane_min = (CAR_CHORD + 2R) / 2 - 2R = CAR_CHORD / 2 - R
# A SMALLER PEG WIDENS THE FREE LANE ONE FOR ONE. At the old R 1.10 the lane
# was 1.60 m; at 0.95 it is 1.85 m against a 2.0 m reference car (an etk800's
# node cloud measures 2.02 m across, read live), so the field is still closed
# but by 0.17 m instead of 0.42 m. That is the real, measured cost of "smaller",
# it is charged against BOARD CHARACTER rather than against the score (a car
# that threads a lane still lands in a bin - it just does not carom on the way
# down), and the n=15 bin distribution is what watches it.
#
# WHY 0.95 AND NOT THE FLOOR. 0.86 leaves a 0.06 m pitch window; 0.95 leaves
# 0.43 m and is where the four margins balance. It also keeps the peg well
# clear of the build-24 disaster - PEG_R 0.35 scored 0 of 4, because thin pins
# do not DEFLECT and cars arrive at the bottom still pointed straight down.
# Frontal steel per row goes 36.7% -> 31.7% (even) and 27.5% -> 23.8% (odd):
# a 14% reduction, nothing like build 24's 68%.
#
# ...AND THE CIRCLE WAS BUILT, FLOWN AND MEASURED, AND IT LOST. Everything from
# here to PEG_SECTION_SHAPE is kept because it is the record of that round, not
# because it is what ships.
#
#   build 55  circle  R 0.95, R_z 0.95/0.95, pitch 7.50, air 1.96:   5 of 15
#   build 58  D       R 1.10, R_z 1.10/0.40, pitch 7.60, air 2.36:   6 of 15
#   build 56  KITE    R 1.10, R_z 1.55/0.40, pitch 7.60, air 1.91:  11 of 14
#   build 50  KITE    as above but pegs on ice, not frictionless:   10 of 14
#
# WHERE THE CARS DIED, WHICH IS THE WHOLE POINT. Nine of the ten build-55 hangs
# were INSIDE the peg field between rows, eight of them 2.2-3.1 m below a peg
# centre and within 0.6 m of its column, and the fall traces show the cars are
# not resting - they are TUMBLING IN PLACE, up-vector wandering 0.25-0.77
# (40-75 deg of tilt) while the knocker rocks them 2 m back and forth for
# twenty seconds. They are pinched between the BELLY of the row above and the
# CROWNS of the row below, and a car at 60 deg presents 3.9 m into a 1.96 m
# gap. Build 50's four hangs, by contrast, were one chute, one divider, one
# throat and one unclassified: three of them outside the field entirely.
#
# IT IS THE CROWN, NOT THE BELLY - and the D-SECTION is what proved it.
#
# The first reading of build 55 was that the circle's round BELLY was the
# killer: a kite's belly is a shallow ceiling that slides a car off, a circle's
# is a converging pocket that closes on one. That reading predicted a fix, so
# it got built and flown as build 58 - a true semicircular crown over the
# kite's own 0.40 m shed, R_x and the pitch untouched, so the ONLY variable
# against the 11-of-14 kite was the crown. IT SCORED 6 OF 15. Same belly, same
# lattice, same groundmodel, same hoist; round crown; and it failed like the
# circle. The belly hypothesis is DEAD, and what is left standing is the crown.
#
# WHAT THE CROWN IS ACTUALLY FOR, then. Not friction, and not the cradle - it
# is the DEFLECTOR. A 1.55 m spike turns a car aside at the row line, before it
# can get down into the space between rows. A 1.10 m dome lets it slip past the
# crown line into that space, and once a car is BETWEEN two rows nothing can
# get it out: seven of the D's nine hangs sat 0.86-1.31 m below a row centre,
# most of them INVERTED (up-vector -0.14 to -0.56), floating in the middle of
# the gap with 0.8 m of clear air to the belly above and 1.5 m to the crowns
# below. They were not wedged against anything. They were LOOSE IN THE POCKET,
# and the knocker cannot walk a car out of a pocket it fits inside.
#
# WHICH MAKES THIS THE THIRD INDEPENDENT CONFIRMATION OF THE ROW-AIR LAW, and
# the first from the crown direction:
#     build 24  air bought by THINNING the pegs      0 of 4
#     build 29  air bought by DROPPING rows          2 of 15
#     build 58  air bought by SHORTENING the crown   6 of 15
#     build 56  1.91 m of air, the least of any     11 of 14
# ROW AIR IS NOT HEADROOM TO BE MAXIMISED. It is the MOUTH OF THE PINCH. Every
# centimetre of extra air is a centimetre more of car that can get in between
# two rows, and the assert below is written against CAR_HEIGHT as a FLOOR, not
# as a target - clearing it by 0.41 m scores; clearing it by 0.86 m does not.
#
# AND FRICTIONLESS CANNOT PAY FOR ANY OF IT. That was the bet - 22.5 deg facets
# are harmless with mu = 0 - and the bet was sound for the CRADLE, which is a
# friction mode. It is irrelevant to a car floating loose between two rows,
# which is not being held by anything at all.
#
# THE D-SECTION: built, flown, and REFUSED at 6 of 15 (build 58). It is kept
# here because the look it delivers is real - see the drive-in capture - and
# because it is the experiment that killed the belly hypothesis. Everything
# below describes it as designed; the verdict is above.
# If the BELLY is what kills a car and the CROWN is all anyone ever sees, then
# take the round crown and keep the kite's belly: a semicircle above the
# equator, the same 0.40 m shallow shed below it. The player gets round pins
# from the front, the drive-in approach and every frame of a car falling past
# them, and the machine keeps the one surface the measurement says matters.
#
# IT IS DELIBERATELY FREE IN X. R_x stays at the kite's 1.10 and the pitch at
# 7.60, so the throat (5.40 m), the half-pitch lane (1.60 m), the wall
# embedment (0.50 m) and both lattice asserts are the SAME NUMBERS the 11-of-14
# build shipped - the lane still clears an etk800's measured 2.02 m body by
# 0.42 m, where the circle at R 0.95 had eroded that to 0.17. Nothing that was
# working is being spent on this.
#
# WHAT IT COSTS AND WHAT IT BUYS. The crown reach drops 1.55 -> 1.10, so the
# peg is 29% shorter in profile (visibly smaller and stubbier, which is the
# half of "smaller in diameter" that is actually available) and the row air
# GROWS 1.91 -> 2.36 m - a 0.45 m gain, bigger than either previous section
# managed, and aimed squarely at the tumbling-car pinch that killed the circle.
# The section area is 2.151 m2 against the kite's 2.145: the same steel, moved.
#
# The risk it accepts, stated plainly: the crown facets go from 54.6 deg to
# 22.5, which is the CRADLE exposure the kite's tall apex was cut for. That is
# the bet FRICTIONLESS is here to cover (mu = 0 exactly - a 22.5 deg facet
# cannot hold anything), and unlike the circle's belly-pinch, the cradle really
# is a friction mode, so the bet is being made where it can pay.
#
# ---------------------------------------------------------------------------
# 2026-08-15, serial 82: THE DEE IS NOW SHIPPED, AND A MEASUREMENT SAYS WHY.
#
# Everything above this line was written as an argument. The deformation time
# series (n = 7 plays on serial 81, deform.py, 10 Hz from deck to rest) is the
# first DATA on the question, and it moved the target.
#
# What it found. The car's clamped node-cloud diagonal, against a 4.74 m
# tumbling diagonal and a 5.32 m repaired-on-the-deck baseline:
#
#     parked on the deck        5.32      chute exit                5.60
#     ABOVE the top crown       6.09      <- last moment provably untouched
#     after the z=40 row        6.07 median, but 10.15 / 10.65 / 11.96
#                                         in 3 of the 7 plays
#     at rest                  11.08      peak in play             15.23
#
# Two readings, and the second is the one that matters.
#
# (1) The car arrives at the lattice INTACT. Above the top crown it is 6.09 m,
#     1.14x its own parked baseline, in every play. The kicker, the chute and
#     the free fall do not break it. So pin geometry IS the live lever - the
#     opposite branch, where nothing about the pins could help, was the
#     pre-registered alternative and it did not happen.
#
# (2) The damage is a FIRST-STRIKE event, not eight rows of accumulation.
#     The top row's tallest steel reaches z = 41.69, so the 1.69 m between
#     "above the crown" and the z=40 sample is one row's worth of contact -
#     and in plays 2, 6 and 7 the diagonal jumps +2.86, +3.07 and +3.30 m
#     across exactly that 1.69 m. One row adds three metres. That also
#     explains the retract ladder firing as often after two rows as after
#     eight.
#
# THE CROWN IS WHAT A CAR MEETS ON THAT FIRST STRIKE, so the crown is where
# the cheapest available change has to go. The dee is that change and it is
# free in x: PEG_R stays 1.10, the pitch stays 7.60, the throat stays 5.40 m
# against the 5.148 m chord, and every lattice assert keys off PEG_R and the
# column positions, none of which move. Only PEG_R_Z_UP changes, 1.55 -> 1.10.
#
# JUDGE IT ON THE DEFORMATION ENDPOINT, NOT ON HANG COUNT. The round crown was
# rejected once before on hang count at small n, which is the error the time
# series exists to stop repeating: the metric is the peak clamped diagonal per
# strike, measured the same way on both builds.
#
# ...AND THEN THE DEE WAS BUILT AND MEASURED, AND IT IS NOT SHIPPED. Serial 82
# was built (fence clean: contained to the peg crowns, free in x, every
# drive-on surface and the frictionless invariant intact, 788 tests unchanged)
# and run through the SAME probe, same seed, n = 7 against n = 7:
#
#   DEFORMATION - the metric this was to be judged on - improved:
#     first strikes over +2 m      3 of 7  ->  1 of 7
#     first-strike jump, range     [-0.12 .. 3.30]  ->  [-0.01 .. 2.09]
#     peak clamped diagonal, med   15.23  ->  13.51
#     at rest, median              11.08  ->  10.82   (flat)
#     solver blowups                3 of 7 ->  3 of 7 (flat)
#
#   GAMEPLAY moved the other way:
#     conceded                      1 of 7 ->  2 of 7
#     assisted (needed pin retract) 3      ->  4
#     retract events                9      -> 14
#     bins reached                 {0,1,3} -> {1} only
#
# That is THE CRADLE, exactly where the note above said the bet was being
# placed: 22.5 deg crown facets hold a car that 54.6 deg facets shed, and mu=0
# did not cover it because a deforming shell presses its own pocket and does
# not need friction to sit in one. The dee buys a gentler first strike and
# pays for it in cars parked on crowns.
#
# NEITHER DIFFERENCE IS RESOLVABLE AT n = 7 - 1 vs 2 concedes is noise, and so
# is 3 vs 4 assists. The 3-of-7 -> 1-of-7 first-strike result is the sturdiest
# number here because the effect is 3 m and it was predicted before the run.
# So the constant goes back to the shipped, live-verified kite, and what this
# round actually establishes is the MEASUREMENT and the TRADE, not a winner.
# The next round should take the dee to a real census (n >= 20 per arm) before
# anyone decides; the deformation gain may well survive and the gameplay loss
# may well evaporate.
# ---------------------------------------------------------------------------
PEG_SECTION_SHAPE = "kite"
assert PEG_SECTION_SHAPE in ("kite", "circle", "dee")
# The circle's parameters, live for PEG_SECTION_SHAPE == "circle" only. The
# facet count must be a MULTIPLE OF FOUR: that is what puts a vertex at 0 and
# 180 degrees, so the section's widest half-width is exactly PEG_R (the number
# every throat/lane/embedment assert is written against), and a vertex at 90,
# so the crown is an EDGE. Rotate the octagon by half a facet and the crown
# becomes a 1.34 m DEAD LEVEL face running the full board depth - a level table
# needs no friction at all to hold a car, so no groundmodel could fix it.
PEG_FACETS = 8
assert PEG_FACETS % 4 == 0, (
    "the peg section needs vertices at 0/90/180/270 deg: at 0 and 180 so its "
    "widest half-width really is PEG_R, and at 90 so the crown is an edge "
    "rather than a level face a car can table on"
)
PEG_CROWN_FACET_DEG = 180.0 / PEG_FACETS
# THE SHIPPED SECTION. PEG_R is the half-width in X; PEG_R_Z_UP is the crown
# reach and PEG_R_Z_DN the belly reach, and on the kite they are deliberately
# NOT equal - the tall crown gives 54.6 deg flanks a deforming floorpan cannot
# settle on, and the shallow belly gives a tumbling car a ceiling that sheds it
# instead of a pocket that closes on it. The circle sets all three equal, which
# is exactly what the build-55 measurement above says costs half the score.
if PEG_SECTION_SHAPE == "circle":
    PEG_R = 0.95
    PEG_R_Z_UP = PEG_R
    PEG_R_Z_DN = PEG_R
elif PEG_SECTION_SHAPE == "dee":
    # Round on top, kite underneath: R_z_up = R_x makes the crown a true
    # semicircle, R_z_dn keeps the shed the circle threw away.
    PEG_R = 1.10
    PEG_R_Z_UP = PEG_R
    PEG_R_Z_DN = 0.40
else:
    PEG_R = 1.10
    PEG_R_Z_UP = 1.55
    PEG_R_Z_DN = 0.40
# THE SCALLOP (2026-08-14g), and the reason it exists - now more load-bearing
# than ever, because a round crown is a smoother ridge than a kite's apex.
# Every peg is a prism running the full 6.90 m board depth, so its crown is a
# CONTINUOUS HORIZONTAL KNIFE-EDGE 6.9 m long. A car lying across that ridge is
# balanced on a LINE - and because a car is soft-bodied, it presses a groove
# around the ridge and that groove becomes a restraining pocket. That is
# failure mode 2, the cradle, and it is the one mode every rigid-body scan in
# this project has been blind to. Sharpening the apex does not help; a sharper
# edge presses a deeper groove, which is why the 45 deg diamond -> 54.6 deg
# kite did not close it.
#
# So break the LINE. The crown height is modulated along the DEPTH axis, so a
# car lying across a peg contacts two or three high points that are NOT
# collinear, has nothing continuous to balance on, and rocks off. On the
# circular section the modulation is a scale on the UPPER HALF ONLY - a barrel
# waisted along its own length - so the equator, and therefore the widest
# half-width, is untouched at every station.
#
# THE POINT OF DOING IT THIS WAY: it changes NOTHING IN X. The peg's x
# footprint, the throat, the half-pitch lane, the wall reach,
# assert_no_clean_column and assert_no_two_contact_rest all key off PEG_R and
# the column positions, none of which this touches. Verified, not assumed - the
# generator's width-coupling assert probes the real section and would fail if
# the modulation leaked into x.
#
# So be honest about what the scallop bets on: NOT slope. It bets on the
# soft-body groove argument - that a crown broken into discrete dimples cannot
# press the single continuous channel a 6.9 m straight ridge presses, so there
# is no channel to restrain the car along. That is the mechanism, it is the
# same one the cradle diagnosis rests on, and it is why the amplitude only has
# to be enough to interrupt the ridge rather than enough to shed a car.
#
# AMPLITUDE AND THE UNDERSIDE TRADE AGAINST EACH OTHER: row air is
# PEG_ROW_PITCH - PEG_R_Z_DN - (PEG_R_Z_UP + AMPLITUDE + TILT/2), so every
# centimetre of crown wave is a centimetre off the gap a car falls through. At
# 0.22/0.16 the air was 1.75 m - BELOW the 1.85 m configuration that produced
# the documented midpoint hang - which is why it was halved. It is HELD at 0.10
# now that the crown reach is 0.95 rather than 1.55, even though that makes the
# wave a relatively deeper 11% of the reach instead of 6%: 0.22 on a 1.55 apex
# already read as jagged shards from the drive-in angle, and the same absolute
# wave on a smaller peg is more visible, not less.
PEG_SCALLOP_AMPLITUDE = 0.10
PEG_SCALLOP_PERIODS = 2.0
# ...AND A TILT. A pure cosine leaves every crest at the SAME height, so they
# are collinear along the depth axis and a car lying nose-to-tail can seesaw on
# two of them. The tilt puts every high point at a different height - measured,
# the seven shipped crowns are all distinct.
#
# BE PRECISE ABOUT WHAT THAT BUYS, THOUGH: adjacent crests differ by 0.04 m
# over 3.45 m, which is 0.66 deg - nowhere near the 21.8 deg friction angle, so
# the tilt does NOT make a two-crest rest slide out, and an earlier version of
# this comment claiming it did was wrong. It would take about 34x this tilt to
# do that, and that much would cost the row air. What it actually does is
# remove the DEGENERATE case - two contacts at exactly equal height sharing the
# load - and bias the car toward the low face. Modest, real, and not a cure.
PEG_SCALLOP_TILT = 0.08
# Stations across the depth. 7 gives ~3 per period - enough to read as a wave
# in both mesh and cage without multiplying the node count past reason, and
# with an 8-vertex section the node count per station has already doubled.
PEG_SCALLOP_STATIONS = 7
# The CREST is now the tallest point of a peg, so it is the crest that has to
# clear a car between rows, not the nominal apex.
# The tallest steel on a peg is crest + half the tilt, and THAT is what has to
# pass a car between rows.
PEG_CROWN_MAX = PEG_R_Z_UP + PEG_SCALLOP_AMPLITUDE + PEG_SCALLOP_TILT / 2.0
PEG_ROW_AIR = PEG_ROW_PITCH - PEG_R_Z_DN - PEG_CROWN_MAX
# The circle IMPROVED this and it is worth saying why, because the intuition
# runs the other way: going round GREW the underside from 0.40 to 0.95, but it
# SHRANK the crown reach from 1.55 to 0.95, and the crown is the bigger term.
# 1.91 m of air became 1.96 m for free.
assert PEG_ROW_AIR > CAR_HEIGHT, (
    f"peg rows cannot pass a car at all: {PEG_ROW_AIR:.2f} m of air for a "
    f"{CAR_HEIGHT} m car"
)
PEG_PITCH_X = 7.50 if PEG_SECTION_SHAPE == "circle" else 7.60
# THE derivation that makes this a pachinko board and not a chute. It is now
# sized against the car's CHORD, not its width. The 2026-08-13 version of this
# comment read "clear gap = 2.50 m, which is WIDER than the 2.00 m car, so a
# car CAN thread a single row" - that is superseded, because a gap sized to the
# WIDTH only passes a car that arrives square, and cars arrive at every
# attitude there is (the live telemetry found them inverted and on their
# sides). The number that has to be beaten is the longest chord a car can
# present into a converging throat:
#   clear throat between neighbouring pegs = PEG_PITCH_X - 2 * PEG_R = 5.40 m,
#   against the 5.148 m body chord - so no throat in the field can arrest a
#   car at ANY orientation; and the crowns stand 7.60 m apart, which no car
#   can table across either.
#
# THE PITCH IS NOT FREE, IT IS A WINDOW, and the radius sets it (2026-08-14h).
# It has to stay above (FIELD_HW - PEG_R) / 1.5 so the outermost even peg still
# reaches into the wall, and below 2 * CAR_WIDTH + 4 * PEG_R so the half-pitch
# lane stays blocked. At PEG_R 1.10 that window is [7.348, 7.733] and 7.60 sits
# inside it with 0.25 m below and 0.13 m above, putting 0.50 m of peg inside
# the wall slab with 0.20 m still to its outer face. At the circle's 0.95 the
# window moves to [7.367, 7.800] and the shipped pitch would have been 7.50.
# Every one of those numbers is asserted below rather than trusted to this
# comment, and _PEG_R_FLOOR carries the reason the window can close entirely.
# What must never exist is a lane that clears a row AND the staggered row
# beneath it, which would be a free chute from crown to bins. That holds by
# construction: odd rows sit half a pitch across, so every even-row gap is
# centred exactly on an odd-row peg (and vice versa), and the even rows' own
# outermost pegs are driven INTO the side walls to close the side channels.
# assert_no_clean_column proves the chute question at build time, and
# assert_no_two_contact_rest proves the chord clearances beside it. HOW MUCH
# of that proof is pairwise is worth being exact about, because this comment
# used to say "over every CONSECUTIVE ROW PAIR" flat: the VERTICAL lane proof
# is pairwise (no car-wide vertical lane clears any two consecutive rows), and
# the DIAGONAL proof is WHOLE-BOARD (no straight line of any slope threads all
# eight rows). It has to be, because every consecutive pair on this board
# DOES admit diagonals - 5398 of 6001 swept slopes - so a pairwise diagonal
# claim would be false. The achievable-launch proof is whole-board too.
PEG_OFFSET_X = PEG_PITCH_X / 2.0
PEG_COLUMNS_EVEN = 4
PEG_COLUMNS_ODD = 3


def peg_row_xs(row: int) -> list[float]:
    """Peg centres for a row, centred on the board.

    MOVED HERE 2026-08-18 (P0.2/P0.3). It used to live only in the Blender
    generator, which was fine while only the mesh needed it - and stopped being
    fine the moment the aperture table below had to enumerate the openings a
    row actually has. The generator now imports this; the docstring explaining
    WHY both row types are centred stays there, next to the mesh it shapes.
    """

    count = PEG_COLUMNS_EVEN if row % 2 == 0 else PEG_COLUMNS_ODD
    span = (count - 1) * PEG_PITCH_X
    return [-span / 2.0 + PEG_PITCH_X * i for i in range(count)]


def peg_row_runs(row: int) -> list[tuple[float, float]]:
    """The steel of a peg row as x intervals - the RUNS, in the §2.1 sense.

    A rank is a set of RUNS separated by GATES. On the shipped lattice a run is
    one peg's projected span; after Phase 1 it is one inclined prism wearing
    many pins. Both answer ``rank_runs(rank) -> [(x0, x1)]``, which is what
    lets P0.2's interval algebra be written once.
    """

    return sorted((x - PEG_R, x + PEG_R) for x in peg_row_xs(row))


def runs_to_gates(
    runs: list[tuple[float, float]], lo: float = -FIELD_HW, hi: float = FIELD_HW
) -> list[tuple[float, float]]:
    """Clear spans between runs, clipped to the COLLISION walls.

    Clipped to the collision wall and not to the visual board edge on purpose:
    a peg that reaches 0.50 m into a 0.70 m wall slab closes the side channel,
    and measuring to the visual edge would report a 0.20 m gate that no car can
    reach. Same rule the design document measures every gate width by.
    """

    out: list[tuple[float, float]] = []
    x = lo
    for a, b in sorted(runs):
        # A run wholly OUTSIDE [lo, hi] must be dropped, not clipped. Without
        # this line only `b` was clamped, so a run at [14.5, 16.7] against a
        # 12.0 wall still contributed `a = 14.5 > x` and manufactured a gate
        # (12.0, 14.5) beyond the wall - a gate no car can reach, reported as
        # if it were a lane. The shipped peg rows never leave the field so
        # nothing downstream changes today; Phase 1's inclined runs do, and a
        # positive control built on a tiled pattern hit it on 2026-08-18.
        if b <= lo or a >= hi:
            continue
        a, b = max(a, lo), min(b, hi)
        if a > x:
            out.append((x, a))
        x = max(x, b)
    if x < hi:
        out.append((x, hi))
    return out


# Pegs run the full board depth (-DEPTH_HALF .. +DEPTH_HALF) and share the side
# walls' own cage nodes, so a peg can never be a floating island.
#
# The half-pitch stagger is NOT applied as an offset - it falls out of dropping
# one column on the odd rows, because both row types are centred on the board.
# Adding PEG_OFFSET_X on top of that shifted the odd rows off-centre and opened
# a 2.75 m free lane against the left wall (caught by assert_no_clean_column).
# So the offset constant is kept as the CHECK rather than as the mechanism:
assert abs(
    ((PEG_COLUMNS_EVEN - 1) - (PEG_COLUMNS_ODD - 1)) * PEG_PITCH_X / 2.0 - PEG_OFFSET_X
) < 1e-9, "odd/even column counts no longer produce a half-pitch stagger"
# THE DIAGONAL (2026-08-14g), AND WHY IT IS NO LONGER THE DEFECT (2026-08-14i).
# Every check below is WITHIN a row: crown spacing and throat measured along x.
# Nothing checks the DIAGONAL between an odd-row peg and the even-row peg one
# row up or down and half a pitch across. That gap in the asserts is real and
# is left documented - but the WEDGE it was written about is not what hangs
# cars on the shipped machine, and the numbers below have been corrected.
#
# THE ARITHMETIC, re-derived from the section's own support function rather
# than from the old prose (scratchpad throat.py, which walks every scallop
# station of the SHIPPED kite):
#     centre-to-centre along the stagger diagonal = hypot(3.80, 4.00) = 5.5172 m
#     kite support toward that diagonal, apex end, worst station     = 1.2252 m
#     kite support toward it, flank end (equator, scallop-invariant) = 0.7576 m
#     CLEAR THROAT                                    5.5172 - 1.9828 = 3.534 m
# 3.534 m at the crest station, 3.563 m at the trough - the scallop moves it by
# 3 cm and cannot touch it, because a diagonal wedge lives in the x-z plane and
# the scallop only modulates depth.
#
# THE OLD NUMBERS HERE WERE WRONG AND ARE KEPT ONLY AS A WARNING: this block
# used to record an apex-end support of 1.341 m and a throat of 3.417 m. 1.341
# EXCEEDS the section's true support in that direction (1.225), i.e. it claimed
# steel the peg does not have, and three geometry rounds were then spent
# chasing a 0.12 m error.
#
# AND THE 18 STABLE POSES WERE AN ICE-ERA MEASUREMENT. That scan was run at
# mu = 0.4, when the pegs were on `ice`. The pegs have been FRICTIONLESS since
# 2026-08-14h and the fall volume's walls since 2026-08-14i, and at mu = 0 the
# same wrench-cone machinery finds ZERO stable rests anywhere on this lattice -
# 10^8 poses, 4 silhouettes, 60 attitudes, 53k positions, up to 7 contacts,
# 0.20 m of compliance. Two frictionless contacts cannot balance three
# equations, so a diagonal wedge held by two flanks is arithmetically
# impossible now, whatever its throat measures. Every stable-pose count written
# anywhere in this file must be read with the mu it was measured at attached.
#
# WHAT THE LIVE CENSUS FOUND INSTEAD, and it is not this pocket: of 13 field
# hangs in the 56-play census, 10 had the x = 0 CENTRE COLUMN as nearest peg,
# 11 were on an odd (3-column) row, and 9 of the 16 total hangs sat in
# z 25.6-30.0 - one pocket straddling the crown (29.69) and equator (28.00) of
# the single peg at (0, 28). Cars DRAPED OVER ONE PEG, not wedged between two.
# One peg plus one board face is a two-contact rest that needs the FACE to have
# grip, which is the reasoning behind FALL_VOLUME_GROUNDMODEL above.
#
# NOT ASSERTED, deliberately: an assert on the diagonal would fail on the
# shipped lattice, and no lattice reachable from here closes it - a 200k-point
# (phase, pitch, radius) grid using an OPTIMISTIC section returned 0 feasible
# designs, a 3- or 4-phase stagger makes every diagonal SHORTER (the
# adjacent-row offset drops from p/2 to p/3), and depth stagger is capped at
# 2.0 m by the 4.90 m depth a car needs to not walk past in y. The number is
# written here so the next round starts from it instead of rediscovering it -
# and so that nobody spends another round closing a wedge that mu = 0 has
# already un-built.

# THE LATTICE ASSERTS. Written against CAR_CHORD and CAR_WIDTH rather than
# against numbers, so a future pitch/section/column change that reopens the
# defect fails at import instead of in the player's game. On the shipped kite
# the THROAT is the binding one - it clears by 0.25 m, where the lane clears by
# 0.40 and the crowns by 2.45. (On the circle it inverts: the LANE becomes the
# binding one at 0.15 m, which is half the reason the circle is not shipped.)
#
# THE RADIUS FLOOR, asserted at the top of the block because it is the one that
# explains the others. Four constraints, two of them about the wall, close the
# feasible window entirely below R = (FIELD_HW - 3 * CAR_WIDTH) / 7.
_PEG_R_FLOOR = (FIELD_HW - 3.0 * CAR_WIDTH) / 7.0
assert PEG_R > _PEG_R_FLOOR, (
    f"PEG_R {PEG_R} is under the {_PEG_R_FLOOR:.3f} m floor: with "
    f"{PEG_COLUMNS_EVEN} even columns on a {2 * FIELD_HW} m board there is NO "
    "pitch that both reaches the wall and keeps the half-pitch lane blocked"
)
_PEG_PITCH_LO = max(CAR_CHORD + 2 * PEG_R, (FIELD_HW - PEG_R) / 1.5)
_PEG_PITCH_HI = min(2 * CAR_WIDTH + 4 * PEG_R, (FIELD_HW + WALL_T - PEG_R) / 1.5)
assert _PEG_PITCH_LO < PEG_PITCH_X < _PEG_PITCH_HI, (
    f"PEG_PITCH_X {PEG_PITCH_X} is outside the "
    f"[{_PEG_PITCH_LO:.3f}, {_PEG_PITCH_HI:.3f}] window PEG_R {PEG_R} allows"
)
assert PEG_PITCH_X - 2 * PEG_R > CAR_CHORD, (
    f"peg throat is {PEG_PITCH_X - 2 * PEG_R:.2f} m against a "
    f"{CAR_CHORD:.3f} m car chord: the field can wedge a car"
)
assert PEG_PITCH_X > CAR_CHORD, (
    f"peg crowns are {PEG_PITCH_X:.2f} m apart against a {CAR_CHORD:.3f} m "
    "car chord: a car can table across two of them"
)
assert PEG_PITCH_X / 2.0 - 2 * PEG_R < CAR_WIDTH, (
    f"the half-pitch lane is {PEG_PITCH_X / 2.0 - 2 * PEG_R:.2f} m of clear "
    f"air: a {CAR_WIDTH} m car has a free chute past the staggered row"
)
# The stagger's diagonal must stay STEEP. A shallow crown-to-crown diagonal is
# a staircase a car rides down instead of being deflected by; 46.5 deg here.
_STAGGER_DEG = math.degrees(math.atan2(PEG_ROW_PITCH, PEG_OFFSET_X))
assert _STAGGER_DEG > 35.0, (
    f"the row stagger runs at {_STAGGER_DEG:.1f} deg: shallow enough for a car "
    "to ride crown to crown instead of being deflected"
)

# WHY THE WALL STUBS ARE GONE (2026-08-14). THE WALL IS A PEG THAT NEVER ENDS.
# The side channel used to be closed by a half-peg stubbed out of each wall on
# the odd rows. Those stubs were themselves a trap of exactly the kind the
# TWO-CONTACT LAW describes: a stub crown sat 2.75 m from the outermost odd
# peg AT THE SAME HEIGHT, which is an 11.3 deg shelf - shallower than ICE's
# 21.8 deg friction angle, so it held a car outright. They created hangs while
# closing a chute.
#
# The channel is now closed the honest way: the even rows' outermost peg is
# driven INTO the wall slab, so wall and peg are one continuous obstacle and
# there is no crown standing near the wall at all. A crown TANGENT to a wall
# is not a lean trap, because the wall contact lands BELOW the crown, so its
# moment ADDS to tipping the car off - where the old stub's crown-beside-crown
# pair added to holding it on. Asserted in both directions: the outermost peg
# edge must reach INTO the wall, and must not punch out through its far face.
_OUTER_PEG_EDGE = (PEG_COLUMNS_EVEN - 1) * PEG_PITCH_X / 2.0 + PEG_R
assert _OUTER_PEG_EDGE >= FIELD_HW, (
    f"the outermost even-row peg edge stops at {_OUTER_PEG_EDGE:.2f} m, short "
    f"of the {FIELD_HW} m wall: a free bypass lane runs down the side channel"
)
assert _OUTER_PEG_EDGE <= FIELD_HW + WALL_T, (
    f"the outermost even-row peg edge reaches {_OUTER_PEG_EDGE:.2f} m and "
    f"punches out through the {FIELD_HW + WALL_T} m outer wall face"
)

PEG_ROW_Z = [PEG_TOP_Z - PEG_ROW_PITCH * k for k in range(PEG_ROWS)]
# The derivation above, asserted so it cannot rot: the bottom row's steel must
# keep a real drop (>= 4.0 m) above the divider ridges. The steel that matters
# is the bottom VERTEX, which is why this reads PEG_R_Z_DN and not PEG_R - the
# kite's shallow underside lifts the clearance from 5.90 to 6.60 m for free.
assert PEG_ROW_Z[-1] - PEG_R_Z_DN - RIDGE_Z >= 4.0, "peg field crowds the bin mouths"
# What the coordinator asked for rather than changed blind: how many rows the
# drop assert would still allow, if the flat elevation wants filling in. The
# binding constraint is bottom row - PEG_R_Z_DN - RIDGE_Z >= 4.0, i.e. a
# bottom row no lower than 9.40, i.e. PEG_TOP_Z - PITCH * (rows - 1) >= 9.40.
MAX_PEG_ROWS = int((PEG_TOP_Z - (RIDGE_Z + 4.0 + PEG_R_Z_DN)) // PEG_ROW_PITCH) + 1
assert MAX_PEG_ROWS >= PEG_ROWS, "the row-count headroom calculation is inverted"
# ...and the answer is SEVEN, i.e. there is ZERO headroom at this pitch. Adding
# a row means either dropping PEG_ROW_PITCH (forbidden - it is the pinch fix)
# or lifting PEG_TOP_Z, and the top of the board is not free either: the top
# row's APEX must pass under the crown chute slab wherever the two overlap in
# x. That is asserted further down, once the chute constants exist, because
# "just add rows" is exactly the kind of cheap-looking change that would
# silently drive steel through the chute's underside.

# ---------------------------------------------------------------------------
# Crown chute (the fixed apron that turns the released car into the field) and
# the release gate flap that blocks it while the machine is idle.
# ---------------------------------------------------------------------------
APRON_DEG = 40.0
APRON_X_HI = 12.60  # = the tipper hinge line: chute and deck meet exactly
APRON_X_LO = 6.00
APRON_Z_HI = 44.00
APRON_Z_LO = APRON_Z_HI - (APRON_X_HI - APRON_X_LO) * math.tan(math.radians(APRON_DEG))
APRON_T = 0.60  # slab thickness measured vertically
# FIXED 2026-08-18, P0.6. RAISED 3.40 -> 5.50. Its own round, its own n = 15,
# not bundled - which are the terms the 2026-08-14c note below set for it.
#
# THE DEFECT, KEPT VERBATIM BECAUSE IT IS THE EVIDENCE. Raised 2026-08-14c and
# held out of that build on purpose, because the fix rebuilds the gate flap and
# would have confounded a five-change round.
#
# THE SAME ERROR CLASS AS PEG_PITCH_X-VS-WIDTH. The comment used to read
# "chute headroom: 2.3 x car height, so a tumbling car passes" - but a tumbling
# car does not present its HEIGHT, it presents its DIAGONAL. The numbers:
#     HOOD_CLEAR (was)      3.400   what the throat actually was
#     CAR_HEIGHT x 2.3      3.450   what it was sized against
#     CAR_DIAGONAL          4.743   what a tumbling car presents in this plane
#     CAR_CHORD             5.148   attitude-independent, the honest target
#     HOOD_CLEAR (now)      5.500   OPEN, +0.352 m over the chord
# So the throat WAS 1.34 m shorter than a tumbling car and 1.75 m shorter than
# chord-clean, and a car that pitched up on the 40 deg slab JAMMED between the
# slab and the hood. Measured live on build 36, play 9: the chute surface at
# x 9.53 is z 41.42 and the car came to rest at 43.18 - 1.55 m higher than a
# car resting on the slab, i.e. wedged nose-up in the throat, where it ate 43
# raps and 7 lip kicks and never reached the board.
#
# WHY 5.50 AND NOT THE BANKED 5.20. The old note banked "CAR_CHORD (5.148, or a
# round 5.20)" and made the choice conditional on re-checking "the crown
# structure above the chute ... for the extra 1.8 m". THE RE-CHECK WAS DONE BY
# MEASUREMENT, not by eye: every authored object was built in Blender and its
# world bounding box dumped, and inside the hood's own footprint
# (x 6.00..12.60, |y| <= DEPTH_HALF) THERE IS NOTHING ABOVE THE HOOD AT ALL.
# The nearest solid in any direction is
#     +x   machine_beam_front / machine_nosing at x 17.89   -> 5.29 m clear
#     -y   the marquee sign frame at y -4.25 (z 46.8..49.7) -> 0.30 m clear
#     +z   nothing, at any height, at any x in the footprint
# so the crown pays NO structure for the extra headroom, and the argument for
# preferring 5.20 evaporated when it was measured. 5.20 would have left
# +0.052 m over the chord - a ROUNDING margin on the one aperture every car
# passes. 5.50 leaves +0.352 m.
#
# CORRECTED 2026-08-18, D4. This used to read "+0.352 m, which is exactly the
# margin the two narrowest OPEN transit apertures downstream ALREADY carry".
# That sentence was arithmetically false about the board that ships. Enumerate
# TRANSIT_APERTURES over the SHIPPED geometry and the OPEN ones downstream of
# the throat are the two 5.400 m in-row gaps, whose margin is +0.252 m, not
# +0.352. The +0.352 figure belongs to Phase 1's replacement gauge, which does
# not exist yet - the design note that carries it says "once Phase 1 lands"
# and this file dropped the qualifier, which is precisely the narrated-instead-
# of-checked failure class this round claims to be retiring.
#
# THE CHOICE SURVIVES THE CORRECTION AND THAT IS WHY IT IS NOT BEING REOPENED:
# 5.50 > 5.400, so the throat really does stop being the machine's thinnest
# OPEN transit aperture. That is now the CHECKED property (see the assert on
# _OPEN_TRANSIT_MAX below the aperture lists) rather than a sentence, because
# a sentence is what got this wrong. 5.20 would have failed it outright: 5.20
# < 5.400 would have left the throat still the thinnest thing on the fall
# path, which is a stronger argument against 5.20 than the one made here
# originally, and it is the argument the assert makes.
# WHAT IT DOES COST, and it is the only cost found: the hood's outboard corner
# stands 50.10 rather than 48.00, i.e. 4.10 m over the bezel head rail instead
# of 2.00 m. The marquee's own bezel top is 50.38, so the silhouette is
# unchanged from straight on; from the front right the corner is taller.
HOOD_CLEAR = 5.50
GATE_HINGE_X = APRON_X_LO
GATE_HINGE_Z = APRON_Z_LO + HOOD_CLEAR
GATE_LEN = HOOD_CLEAR  # the flap exactly spans the throat when it hangs down
# Folding the flap flat against the hood needs -(90 + APRON_DEG) degrees of
# textbook R_y. This used to be justified by ONE hand-worked example at
# GATE_LEN 3.40 ("R_y(-130) * (0,0,-3.4) = (2.60, 2.19), and the hood rises
# 2.18 m over that same 2.60 m run"), which is exactly the kind of check that
# silently stops being true when the constant it was worked at moves.
#
# FIXED 2026-08-18, D1. THE REPLACEMENT WAS A TAUTOLOGY AND THE TAUTOLOGY IS
# THE INTERESTING PART, so it is written down rather than quietly deleted.
# The first repair asserted
#     _GATE_FOLD_TIP_Z == _HOOD_UNDER_AT_TIP
# but computed _GATE_FOLD_TIP_Z from the CLOSED FORM (GATE_HINGE_Z +
# L sin d), never from GATE_OPEN_DEG. Substituting APRON_Z_LO's own
# definition (:APRON_Z_LO, = APRON_Z_HI - (X_HI - X_LO) tan d) makes the two
# sides identical symbol-for-symbol, for EVERY HOOD_CLEAR, EVERY GATE_LEN,
# EVERY APRON_DEG and - the part that matters - EVERY GATE_OPEN_DEG, because
# GATE_OPEN_DEG does not appear on either side. Setting GATE_OPEN_DEG = -47
# left the assert passing. A check that cannot fail is not a check; it is a
# comment with an `assert` in front of it, which is worse than a comment
# because it reads as evidence.
#
# So the fold is now built the only way that can disagree with the angle: by
# APPLYING the rotation. _rot_y is the textbook right-handed R_y,
#     x' = x cos t + z sin t
#     z' = -x sin t + z cos t
# and the flap hangs along local -z, so the tip offset is R_y(GATE_OPEN_DEG)
# applied to (0, 0, -GATE_LEN). TWO asserts follow and they check different
# things:
#   (1) THE ONE THAT CAN FAIL. The numerically rotated tip must land on the
#       closed form (L cos d, L sin d). This is the only statement in the
#       block that reads GATE_OPEN_DEG, so it is the only one a wrong fold
#       angle can trip - and it trips at 1e-9 for a one-degree error, let
#       alone the -47 that used to sail through.
#   (2) THE IDENTITY, KEPT AND LABELLED AS ONE. The closed form equals the
#       hood underside for every L and every apron angle:
#           apron_z(GATE_HINGE_X) + L cos d tan d + HOOD_CLEAR
#         = (GATE_HINGE_Z - HOOD_CLEAR) + L sin d + HOOD_CLEAR
#         = GATE_HINGE_Z + L sin d
#       It cannot fail while APRON_Z_LO is DERIVED from the apron angle, and
#       it is retained for the day somebody types APRON_Z_LO as a literal -
#       which is a real edit, and the only edit this assert guards. It is NOT
#       evidence about the fold angle and is no longer described as such.
# NOTE the engine applies +Y axisAngle poses with the OPPOSITE sense to that
# math (the tipper proved it live, 2026-08-13), so applyMachinePose NEGATES
# this value at the pose site - the constant keeps the textbook sign so the
# derivation above stays checkable.
GATE_OPEN_DEG = -(90.0 + APRON_DEG)


def _rot_y(deg: float, x: float, z: float) -> tuple[float, float]:
    """Textbook right-handed rotation about +Y, applied - not assumed."""

    t = math.radians(deg)
    return x * math.cos(t) + z * math.sin(t), -x * math.sin(t) + z * math.cos(t)


# The tip, ROTATED. Nothing below this line may reintroduce the closed form
# as the definition of the tip: the closed form is the thing being checked.
_GATE_TIP_DX, _GATE_TIP_DZ = _rot_y(GATE_OPEN_DEG, 0.0, -GATE_LEN)
_GATE_ROT_TIP_X = GATE_HINGE_X + _GATE_TIP_DX
_GATE_ROT_TIP_Z = GATE_HINGE_Z + _GATE_TIP_DZ
_GATE_FOLD_TIP_X = GATE_HINGE_X + GATE_LEN * math.cos(math.radians(APRON_DEG))
_GATE_FOLD_TIP_Z = GATE_HINGE_Z + GATE_LEN * math.sin(math.radians(APRON_DEG))
# (1) THE ASSERT THAT CAN FAIL - the only one that reads GATE_OPEN_DEG.
assert (
    abs(_GATE_ROT_TIP_X - _GATE_FOLD_TIP_X) < 1e-9
    and abs(_GATE_ROT_TIP_Z - _GATE_FOLD_TIP_Z) < 1e-9
), (
    f"GATE_OPEN_DEG = {GATE_OPEN_DEG} folds the flap tip to "
    f"({_GATE_ROT_TIP_X:.4f}, {_GATE_ROT_TIP_Z:.4f}), not to the flat-against-"
    f"the-hood pose ({_GATE_FOLD_TIP_X:.4f}, {_GATE_FOLD_TIP_Z:.4f}). The fold "
    f"angle must be -(90 + APRON_DEG) = {-(90.0 + APRON_DEG)}."
)
_HOOD_UNDER_AT_TIP = (
    APRON_Z_HI
    - (APRON_X_HI - _GATE_FOLD_TIP_X) * math.tan(math.radians(APRON_DEG))
    + HOOD_CLEAR
)
# (2) THE IDENTITY. Holds for every L and every apron angle while APRON_Z_LO
# stays derived; guards the day it stops being derived. Not fold-angle
# evidence - see (1) for that.
assert abs(_GATE_FOLD_TIP_Z - _HOOD_UNDER_AT_TIP) < 1e-9, (
    f"the folded gate flap's tip is at z {_GATE_FOLD_TIP_Z:.4f} but the hood "
    f"underside above it is at {_HOOD_UNDER_AT_TIP:.4f}: APRON_Z_LO is no "
    "longer derived from the apron angle"
)
assert _GATE_FOLD_TIP_X < APRON_X_HI, (
    f"the folded gate flap reaches x {_GATE_FOLD_TIP_X:.3f}, past the hood's "
    f"outboard edge at {APRON_X_HI}: the flap no longer has a hood to fold "
    "against"
)

# ---------------------------------------------------------------------------
# P0.3 - THE CHORD LAW, AS ASSERTS OVER THREE LISTS (2026-08-18).
# ---------------------------------------------------------------------------
# The law itself, and it is a law about APERTURES, not about lanes:
#
#   * CLOSED     clear width <  CAR_WIDTH (2.000).  Nothing passes, ever.
#   * OPEN       clear width >  CAR_CHORD (5.148).  Everything passes at every
#                attitude, because the chord is the longest straight line
#                through the car in ANY orientation.
#   * FORBIDDEN  2.000 <= width <= 5.148.  A SQUARE car passes and a TUMBLING
#                car jams, and the live telemetry at :817-819 found cars
#                arriving "inverted and on their sides", so both bounds are
#                real. No authored TRANSIT aperture may live here.
#
# A TRANSIT aperture is one the car must pass through and CONTINUE PAST. A
# TERMINAL aperture is one where the fall path ENDS - the five bin mouths -
# and arrest is its function, not its failure (:2562-2566 says so in as many
# words). Terminal apertures are exempt, the exemption is a CLOSED LIST of
# exactly five, and a terminal aperture may never be followed by another one.
#
# Lanes are the OPPOSITE direction of the same idea and are NOT in these
# lists: an aperture is bounded BELOW by the chord, a lane is bounded ABOVE by
# the width. Confusing the two has cost this project rounds. The lane asserts
# live at :939-942 and in assert_no_clean_column, where they belong.
#
# WHY THE LISTS ARE COUNTED. An exemption that is not counted is a hole through
# which any failing aperture can be pushed to make a build pass. So every list
# has an exact len() assert, and every exemption carries the constant it comes
# from, the date it was raised, the live evidence that it is real, and the
# phase item that retires it. An exemption is a debt register entry, not a
# waiver.
CHORD_LAW_CLOSED = "CLOSED"
CHORD_LAW_OPEN = "OPEN"
CHORD_LAW_FORBIDDEN = "FORBIDDEN"


def classify_aperture(width: float) -> str:
    """CLOSED / OPEN / FORBIDDEN for a clear width, by the Chord Law."""

    if width < CAR_WIDTH:
        return CHORD_LAW_CLOSED
    if width > CAR_CHORD:
        return CHORD_LAW_OPEN
    return CHORD_LAW_FORBIDDEN


def _peg_row_apertures() -> list[tuple[str, float, float, str]]:
    """Every opening a peg row actually has, derived - never typed.

    THE ROW HAS FOUR KINDS OF OPENING, not one, and only one of them had ever
    been written down. :821 records the IN-ROW gap (PEG_PITCH_X - 2*PEG_R) and
    the whole lattice is argued around it. But an ODD row carries three pegs
    where an even row carries four, so its outermost peg stops at 8.70 while
    the wall stands at 12.00 - and that WALL GAP is an aperture too. It is
    enumerated here because this function walks the row instead of quoting a
    comment, which is exactly the failure class that cost two rounds
    (":821 says throat" / "the chute has a throat" - two objects, one word).
    """

    out: list[tuple[str, float, float, str]] = []
    seen: set[tuple[str, float]] = set()
    for row in range(PEG_ROWS):
        parity = "even" if row % 2 == 0 else "odd"
        gates = runs_to_gates(peg_row_runs(row))
        for a, b in gates:
            width = b - a
            touches_wall = abs(a + FIELD_HW) < 1e-9 or abs(b - FIELD_HW) < 1e-9
            kind = "wall gap" if touches_wall else "in-row gap"
            key = (f"{parity} row {kind}", round(width, 6))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                (
                    f"peg field, {parity}-row {kind}",
                    width,
                    PEG_ROW_Z[row],
                    f"peg_row_runs({parity} rows), z {PEG_ROW_Z[-1]:.0f}-{PEG_ROW_Z[0]:.0f}",
                )
            )
    return out


# (name, clear width, the z it lives at, where the number comes from)
TRANSIT_APERTURES: list[tuple[str, float, float, str]] = [
    (
        "T19 crown chute throat",
        HOOD_CLEAR,
        APRON_Z_LO,
        "HOOD_CLEAR, this file. Raised 3.40 -> 5.50 by P0.6, 2026-08-18.",
    ),
] + _peg_row_apertures()

# The five bin mouths, and the list is closed at five by assert. Derived from
# the divider geometry rather than from the 4.80/5.90/2.60/5.90/4.80 comment at
# :2124-2129, so that a divider change cannot leave the comment behind.
_MOUTH_EDGES = [BIN_EDGES[0]] + [
    edge + (CENTER_HORN_LEAN if edge < 0 else -CENTER_HORN_LEAN)
    if abs(edge) < BIN_PITCH
    else edge
    for edge in BIN_EDGES[1:-1]
] + [BIN_EDGES[-1]]
TERMINAL_APERTURES: list[tuple[str, float, float, str]] = [
    (
        f"E{i} bin {i} mouth",
        _MOUTH_EDGES[i + 1] - _MOUTH_EDGES[i],
        RIDGE_Z,
        "divider ridges + CENTER_HORN_LEAN",
    )
    for i in range(BIN_COUNT)
]

# THE DEBT REGISTER. Every entry: (aperture name, width, raised, evidence,
# the phase item that retires it).
FORBIDDEN_EXEMPTIONS: list[tuple[str, float, str, str, str]] = [
    (
        "peg field, odd-row wall gap",
        FIELD_HW - ((PEG_COLUMNS_ODD - 1) * PEG_PITCH_X / 2.0 + PEG_R),
        "2026-08-18",
        "FOUND BY THIS ASSERT, not by inspection, and it is the SECOND shipped "
        "violation - the design document enumerated only the in-row gap and "
        "recorded the shipped peg field as consistent. An odd row carries "
        "three pegs, so its outermost peg edge stops at 8.70 and the wall "
        "stands at 12.00: a 3.30 m opening, squarely in the band. It is not a "
        "free chute - the even row above and below reaches INTO the wall slab "
        "(_OUTER_PEG_EDGE, :966-975) and assert_no_clean_column proves no "
        "car-wide VERTICAL lane clears two consecutive rows, and separately "
        "that no straight diagonal and no achievable launch threads the WHOLE "
        "board - so it has never shown up as one. What "
        "it is, is an aperture a tumbling car can wedge in, on the fall path, "
        "four times per descent.",
        "Phase 1. The replacement gauge has NO wall gap in either pattern: "
        "pattern A's outer runs are [-12.15,-10.95] and [10.95,12.15] and "
        "pattern B's are [-12.15,-6.825] and [6.825,12.15], so every rank of "
        "the new board runs its outermost steel THROUGH the collision wall by "
        "construction. This retires on the day the pegs are deleted.",
    ),
]
# T19 was the exemption this list was created to carry. P0.6 retired it in the
# same round, which is what an exemption is supposed to do; it is kept here so
# the discipline has a memory and the jam log stays attached to a live object.
FORBIDDEN_EXEMPTIONS_RETIRED: list[tuple[str, float, str, str, str]] = [
    (
        "T19 crown chute throat",
        3.400,
        "2026-08-14c",
        "HOOD_CLEAR, this file. Jam logged live, build 36 play 9: chute "
        "surface at x 9.53 is z 41.42, car at rest at 43.18 - wedged nose-up, "
        "43 raps and 7 lip kicks, never reached the board.",
        "RETIRED 2026-08-18 by P0.6: HOOD_CLEAR 3.40 -> 5.50, OPEN by 0.352 m.",
    ),
]

_EXEMPT_NAMES = {name for name, *_ in FORBIDDEN_EXEMPTIONS}
for _name, _width, _z, _source in TRANSIT_APERTURES:
    _cls = classify_aperture(_width)
    assert _cls != CHORD_LAW_FORBIDDEN or _name in _EXEMPT_NAMES, (
        f"TRANSIT aperture {_name!r} is {_width:.3f} m - FORBIDDEN by the "
        f"Chord Law ({CAR_WIDTH} <= w <= {CAR_CHORD:.3f}), and it is not in "
        f"FORBIDDEN_EXEMPTIONS. Source: {_source}. Either open it past the "
        f"chord, close it under the width, or add a counted, dated, evidenced "
        f"exemption that names the phase item which retires it."
    )
for _name, _width, _raised, _evidence, _retires in FORBIDDEN_EXEMPTIONS:
    assert classify_aperture(_width) == CHORD_LAW_FORBIDDEN, (
        f"{_name!r} is exempted from a band it is not in ({_width:.3f} m is "
        f"{classify_aperture(_width)}): a stale exemption is a licence"
    )
    assert any(
        _name == _n and abs(_width - _w) < 1e-9 for _n, _w, _, _ in TRANSIT_APERTURES
    ), f"exemption {_name!r} does not match any transit aperture at {_width:.3f} m"
assert len(TERMINAL_APERTURES) == 5, (
    f"the terminal list holds {len(TERMINAL_APERTURES)} entries, not 5. It is "
    "closed at five so that the next aperture which fails the law cannot be "
    "quietly relabelled 'terminal' to make a build pass - which is exactly "
    "what would have happened to the 2.60 m jackpot mouth."
)
# CORRECTED 2026-08-18, D7. This used to be `== 1`, justified as "an exact
# count, not a ceiling". The exactness was doing no work: the register held one
# entry only because P0.3 RAISED the wall-gap exemption and P0.6 RETIRED T19 in
# the SAME round, so the count is an arithmetic coincidence of two independent
# events, not a property anybody chose. Worse, `== 1` fires on the good change
# too - retiring the last exemption would have tripped it - which trains the
# next reader to edit the number rather than think about it.
#
# What the register is actually for is a CEILING with a person behind it, so
# that is what it now says. The invariants that carry real weight are asserted
# individually above and are unaffected: every exemption must be genuinely
# FORBIDDEN (no stale licences), must match a live transit aperture by name
# and width (no orphans), and carries its raise date, its live evidence and
# the phase item that retires it.
assert len(FORBIDDEN_EXEMPTIONS) <= 1, (
    f"FORBIDDEN_EXEMPTIONS holds {len(FORBIDDEN_EXEMPTIONS)} entries. One is "
    "the ceiling: a second shipped aperture that a tumbling car can wedge in "
    "is a decision somebody has to make on purpose, in writing, with the live "
    "evidence and the retiring phase item attached - not a list that grew."
)
assert len(FORBIDDEN_EXEMPTIONS_RETIRED) == 1
# A terminal aperture may never be followed by another aperture. On a machine
# whose fall path is monotone in z that is checkable as a height rule: nothing
# on the transit list may live at or below the plane the fall path ends on.
# (The bin-floor drive-out throat, 2.80 m between the divider fillets at
# :385-392, sits BELOW the ridge and is FORBIDDEN by width - it is not on this
# list because it is not on the fall path at all: it is traversed by a car
# under its own power at walking pace after it has already scored. The law is
# about a falling body, and a driver is not one.)
_TERMINAL_Z = max(_z for _, _, _z, _ in TERMINAL_APERTURES)
for _name, _width, _z, _source in TRANSIT_APERTURES:
    assert _z > _TERMINAL_Z, (
        f"TRANSIT aperture {_name!r} sits at z {_z:.2f}, at or below the "
        f"terminal plane at {_TERMINAL_Z:.2f}: a terminal aperture may never "
        "be followed by another aperture"
    )

# D4, 2026-08-18. THE THROAT IS NOT THE THINNEST APERTURE ON THE FALL PATH -
# CHECKED, NOT NARRATED. HOOD_CLEAR's own comment used to assert this in prose
# and got the number wrong (see the correction there). The prose is now backed
# by the enumeration it was always claiming to be a summary of: every OPEN
# transit aperture the machine actually has, excluding the throat itself,
# taken from the same TRANSIT_APERTURES list the Chord Law is checked over.
#
# It is a strict `>`, and the equality case is the one worth naming: if some
# future edit made an in-row gap exactly HOOD_CLEAR, the throat would be TIED
# for thinnest rather than clear of it, and "the throat stops being the
# machine's thinnest aperture" would again be a sentence nobody had checked.
_OPEN_TRANSIT_EXCL_THROAT = [
    (_name, _width)
    for _name, _width, _z, _source in TRANSIT_APERTURES
    if classify_aperture(_width) == CHORD_LAW_OPEN and not _name.startswith("T19 ")
]
assert _OPEN_TRANSIT_EXCL_THROAT, (
    "no OPEN transit aperture other than the throat: either the board has "
    "lost its peg rows or the throat's name has drifted from 'T19 ...' and "
    "this check is now silently comparing HOOD_CLEAR against itself"
)
_OPEN_TRANSIT_MAX = max(_w for _, _w in _OPEN_TRANSIT_EXCL_THROAT)
_OPEN_TRANSIT_MIN = min(_w for _, _w in _OPEN_TRANSIT_EXCL_THROAT)
assert HOOD_CLEAR > _OPEN_TRANSIT_MAX, (
    f"the crown chute throat is {HOOD_CLEAR:.3f} m and the widest OPEN "
    f"transit aperture downstream is {_OPEN_TRANSIT_MAX:.3f} m "
    f"({[n for n, w in _OPEN_TRANSIT_EXCL_THROAT if w == _OPEN_TRANSIT_MAX]}): "
    "the throat is the thinnest thing every car has to pass through, which is "
    "the condition P0.6 raised HOOD_CLEAR to end. Raise HOOD_CLEAR above the "
    "widest downstream OPEN aperture, or say in writing why the one aperture "
    "on the fall path that every single car transits should be the tightest."
)

# THE BOARD'S CEILING (see MAX_PEG_ROWS above). The top peg row's APEX has to
# pass under the chute slab everywhere the two overlap in x, so this is the
# assert that makes "just add rows / raise the field" fail loudly instead of
# quietly driving a peg through the chute a car is sliding down.
# The outermost column carries the F6 wall gusset, whose shed face rises a
# further (FIELD_HW - outer peg x) above the apex at the wall plane, so the
# tallest point of the top row is NOT the apex - check both.
# The CREST, not the nominal apex: the scallop's high points are the tallest
# steel in the row and they are what has to clear the slab.
_TOP_APEX_Z = PEG_TOP_Z + PEG_CROWN_MAX
_OUTER_PEG_X = (PEG_COLUMNS_EVEN - 1) * PEG_PITCH_X / 2.0
_GUSSET_RISE = FIELD_HW - _OUTER_PEG_X
_TOP_POINTS = [
    (_x, _TOP_APEX_Z)
    for _x in [-_OUTER_PEG_X + PEG_PITCH_X * _i for _i in range(PEG_COLUMNS_EVEN)]
] + [
    (FIELD_HW, _TOP_APEX_Z + _GUSSET_RISE),
    (-FIELD_HW, _TOP_APEX_Z + _GUSSET_RISE),
]
for _peg_x, _top_z in _TOP_POINTS:
    if APRON_X_LO <= _peg_x <= APRON_X_HI:
        _chute_underside = (
            APRON_Z_HI - (APRON_X_HI - _peg_x) * math.tan(math.radians(APRON_DEG)) - APRON_T
        )
        assert _top_z < _chute_underside, (
            f"the top peg row reaches {_top_z:.2f} at x={_peg_x:.2f}, "
            f"through the crown chute's underside at {_chute_underside:.2f}"
        )

# ---------------------------------------------------------------------------
# Lift shaft, carriage, mast, chain loop and counterweight.
# ---------------------------------------------------------------------------
DECK_X0 = 12.60
DECK_X1 = 17.40  # 4.80 m deck: 1.40 m of margin each side of a 2.0 m car
DECK_HALF_Y = 3.30  # 6.60 m deck: 1.05 m of margin each end of a 4.5 m car
# The fixed loading floor runs 1.2 m past the deck to a full-height guard
# wall; everything past it is the machinery pit, so no car can ever reach the
# chain, the sheaves or the counterweight.
# DOCK_X1 is also the machinery pit's near face and the guard wall's plane.
DOCK_X1 = 18.60
GUARD_TOP_Z = 4.50
SHAFT_X1 = 23.00

# ---------------------------------------------------------------------------
# THE VERTICAL LETTER SIGN, P-A-C-H-I-N-K-O down the outboard shaft flank.
#
# These four numbers used to live only inside the Blender generator, which was
# fine while nothing but the mesh needed them. Round 2 of the lighting review
# needs them in three more places - the eight letter floods are positioned off
# the plates, the capture harness has to aim a camera at the plate face, and
# the write-budget arithmetic counts the plates - and a number that gets
# retyped into a second file is this project's own leading defect class. So
# they are spec data now and the generator imports them.
#
# THE DISPLAY FACE LOOKS OUTBOARD, +x. That is not a detail: round 1 shot every
# "letters" capture from a camera whose view direction was dominated by -y, so
# eight frames of "the chase" were actually eight frames of the board front
# with the two lamp tubes in them, and the plates were edge-on off the side of
# the frame. LETTER_PLATE_X / LETTER_PLATE_Z below are what a camera has to be
# aimed at, and the harness derives its shot from them through the runtime's
# own toWorldPoint so a yaw cannot re-introduce the same mistake.
LETTER_PLATE = 2.90                       # square plate, y and z
LETTER_GAP = 1.50
LETTER_STEP = LETTER_PLATE + LETTER_GAP   # 4.40
LETTER_TOP_Z = 42.90                      # top frame edge 43.26, clear of the crown
LETTER_FACE_X = SHAFT_X1 + WALL_T         # 23.70, the outboard wall face
LETTER_PLATE_X = round(LETTER_FACE_X + 0.51, 4)   # 24.21, the lit face itself
LETTER_PLATE_Z = [
    round(LETTER_TOP_Z - _k * LETTER_STEP - LETTER_PLATE / 2.0, 4) for _k in range(8)
]
assert len(LETTER_PLATE_Z) == 8
assert LETTER_PLATE_Z[0] == 41.45 and LETTER_PLATE_Z[7] == 10.65, LETTER_PLATE_Z

DOCK_FLOOR_Z = 0.90  # loading floor collision plane
# The deck plate is drawn 15 mm proud of the loading floor so its outline reads
# without z-fighting. 15 mm is inside the 20 mm relief cap for drivable
# surfaces (AGENTS.md), so it is not a step.
DECK_HOME_Z = DOCK_FLOOR_Z + 0.015
DECK_DOCK_Z = APRON_Z_HI  # the tipped deck feeds the chute at its hinge
LIFT_TRAVEL = DECK_DOCK_Z - DECK_HOME_Z  # 43.085 m
DOORWAY_HEAD_Z = 6.00  # 4 x car height; the trolley arm clears it
MAST_X = 20.40
MAST_HALF_Y = 3.00
MAST_TOP_Z = 52.00
SHEAVE_Z = 50.50
SHEAVE_R = 1.30
CHAIN_FRONT_X = MAST_X - SHEAVE_R  # 19.10, the carriage reach
CHAIN_BACK_X = MAST_X + SHEAVE_R  # 21.70, the counterweight reach
LOAD_GROUND_Y = -12.00  # where the drive-in ramp meets grade
# 4.60 puts the yoke head 0.60 m clear of the head sheave when docked
# (DECK_DOCK_Z + 4.60 = 48.60 vs the sheave's 50.50 - 1.30 tangent).
YOKE_HEIGHT = 4.60
BOTTOM_SHEAVE_Z = 1.60
CW_X = CHAIN_BACK_X
CW_W = 1.60
CW_H = 2.40
# The chain is a closed LOOP over a head and a foot sheave (carriage clamped
# to the front reach, counterweight to the back reach), so the drawn chain is
# geometrically constant and only the sheaves turn - no length animation, and
# no TSStatic non-uniform scale to rely on. CW_TOP_Z is then pinned by the
# requirement that the counterweight's underside still clears the foot sheave
# at full travel: 1.60 + 1.30 + 0.20 + LIFT_TRAVEL + CW_H = 48.585 -> 48.60.
CW_TOP_Z = 48.60

WALL_TOP_Z = 46.00
SIGN_Z0 = 47.20
SIGN_H = 2.10  # 20.0 x 2.10 = 9.52:1, the marquee family's authored aspect

_SIGN_ASPECT = 9.55

# ---------------------------------------------------------------------------
# THE LAMP RUN (round 6, 2026-08-14). Round 5 built the tubes, the head rail
# and the marquee lit bar as LACQUER, and said so: emissive maps were believed
# inert on this pipeline (WRONG - see THE EMISSIVE VERDICT below, 2026-08-15;
# the tubes could carry a real 3-component emissiveFactor whenever someone
# wants to spend the Blender round on it) and the only working glow a GE-side
# PointLight. Round 6 puts the lights in, so these four numbers are now read
# by TWO consumers - the
# Blender generator that draws the tube geometry, and the GE runtime that hangs
# lights on it. They were literals inside build_visual until now; a light at a
# retyped coordinate is a light hanging in mid-air next to its own tube (the
# centrifuge's "derive every dimension from spec, never retype a number").
LAMP_TUBE_X = FIELD_HW - 0.70            # 11.30, inboard of the bezel stiles
LAMP_TUBE_Y = -DEPTH_HALF - 0.95         # -4.40, 0.95 m proud of the board face
LAMP_TUBE_Z0 = RIDGE_Z + 1.45 + 0.85     # 7.30
LAMP_TUBE_Z1 = WALL_TOP_Z - 0.45 - 0.85  # 44.70, where the dome lamps cap it
# The fascia wash stands OFF the plaque band rather than sitting on it: a
# PointLight at a panel renders as a disc at any brightness (AGENTS.md, the
# centrifuge sign round), so the bin fascia is lit like a real fascia - from
# out front, above the drive-out apron, under the marker rail at z 8.00.
LAMP_FASCIA_Y = DIVIDER_Y_FRONT - 2.70   # -9.20
LAMP_FASCIA_Z = RIDGE_Z + 2.00           # 7.00
# THE MARQUEE FLOOD, and the number serial 63 got wrong. At 0.83 m out front
# the marquee light punched a blown white disc straight through the middle of
# "PACHINKO TOWER" - the exact failure AGENTS.md records from the centrifuge
# sign round ("a PointLight AT the panel renders as a disc at any brightness,
# full stop"), and the fix there was the same one: light the sign like a real
# floodlit fascia, from far enough out that the inverse-square variation across
# the cabinet is gentle. 7.55 m out, radius raised to cover a 23 m sign.
# ROUND 6 EXPERIMENT, TRIED AND REVERTED (build 68, 2026-08-14). The round-5
# notes proposed replacing the slat screen with a translucent pane so the whole
# playfield reads at once. It was built with glass_atrium's exact proven recipe
# - no texture, alpha 0.17 in the colour, doubleSided, and the generated
# material came out `"translucent": true` byte-for-byte in the same shape as
# the atrium's - and it is a DISASTER at 24 x 41 m:
#
#   * By day the pane is a mirror before it is a window. At roughness 0.06 a
#     smooth surface IS its reflection (this file's own peg-steel lesson), and
#     a 1000 m2 sheet facing an open sky returns far more skylight than 17% of
#     the shaded board behind it transmits. The whole playfield - pegs,
#     sunburst, artwork, the entire point of the machine - vanished behind a
#     milky white wall.
#   * At night it is worse, and for the opposite reason: the twelve lights sit
#     0.95 m in FRONT of it, so the pane catches four enormous specular discs
#     and the board behind them goes black. The lighting round it was supposed
#     to complement is exactly what it destroys.
#
# It is not a tuning problem (roughness and alpha only trade one failure for
# the other), it is a scale problem: the atrium's panes work because they are
# small, edge-lit and seen against interior geometry. So the slat screen
# stays. Kept as a flag rather than deleted so the next round does not
# re-propose it without the evidence: flip it and look at the 18:47 captures.
BOARD_GLASS = False

LAMP_MARQUEE_Y = -DEPTH_HALF - 7.55      # -11.00, out over the apron
LAMP_MARQUEE_Z = SIGN_Z0 + SIGN_H / 2.0  # 48.25, the title band's own centre

# ---------------------------------------------------------------------------
# THE PA HORN POLE (round 8, 2026-08-14). A street-light-height steel pole
# beside the scoreboard carrying four re-entrant horns at 90 deg, and the four
# announcement sources that hang on them. Read by TWO consumers, like the lamp
# run above: the Blender generator draws the hardware, the GE runtime hangs
# scene sound emitters at the mouths.
#
# WHERE IT STANDS, AND WHY THAT EXACT SPOT. A drawn-but-non-collidable object a
# car can occupy is the hazard-backstop defect this machine already shipped
# once and had to take back, so the pole is placed by CLEARANCE ARITHMETIC and
# not by eye:
#
#   * every drivable surface on this prop stops at authored x = -12.70 (the
#     plinth / bin-apron edge; the exit apron's own slab and its `exitramp`
#     cage surface stop 0.70 m short of that at -12.00). Nothing the machine
#     can do puts a car outboard of that line - the fall volume is inside the
#     left wall, the bins open onto the apron, and the loading approach is
#     26 m away on the far side at x >= +12.
#   * the pole's widest part is a horn mouth on the +x diagonal. Its rim
#     reaches x = HORN_ENVELOPE_X, and the assert below keeps that at least
#     HORN_DRIVE_CLEAR metres outboard of -12.70 for good.
#
# It is NOT unreachable in the sense of being fenced: a player who deliberately
# drives off the side of the exit apron onto open terrain can walk a car into
# it, exactly as they can with a lamp post at the edge of any BeamNG car park.
# What it is not is IN THE WAY - no drive line, no bin mouth, no exit path and
# no loading approach passes within a metre of it. That is the honest claim.
#
# SCALE. A real re-entrant PA horn bell is ~0.40 m and would be a speck 9 m up
# beside a 54 m machine, so the bells are caricatured to HORN_BELL_D while the
# POLE stays at a genuine street-light height (HORN_POLE_TOP_Z), which is what
# was actually asked for. The two are deliberately inconsistent: the pole has
# to read as a street light, the horns have to read as horns.
HORN_POLE_X = -15.60
HORN_POLE_Y = -9.80
HORN_POLE_TOP_Z = 9.60        # a real 9-10 m street light, not a tower element
HORN_POLE_BASE_Z = -0.20      # buried, so a hump of terrain cannot show a gap
HORN_POLE_R0 = 0.185          # shaft radius at grade
HORN_POLE_R1 = 0.115          # shaft radius under the cap
HORN_FLANGE_R = 0.44
HORN_AXIS_Z = 8.62            # the horn cluster's axis height
HORN_BELL_D = 1.40            # bell mouth diameter (the caricature)
HORN_BELL_LEN = 0.50 * HORN_BELL_D
HORN_DRIVER_LEN = 0.34 * HORN_BELL_D
HORN_DRIVER_R = 0.186 * HORN_BELL_D
HORN_THROAT_R = 0.143 * HORN_BELL_D
HORN_REAR_R = 0.42            # rear cap distance from the pole axis
HORN_MOUTH_R = HORN_REAR_R + HORN_DRIVER_LEN + HORN_BELL_LEN
# The four directions, rotated 45 deg off the machine's own grid: that aims one
# horn straight down the drive-in approach (which lies to +x, -y of the pole)
# and one out over the open apron, instead of firing two of the four flat into
# the board's left wall 2.9 m away.
_ROOT_HALF = 2.0 ** 0.5 / 2.0
HORN_DIRS = [
    (-_ROOT_HALF, -_ROOT_HALF), (_ROOT_HALF, -_ROOT_HALF),
    (_ROOT_HALF, _ROOT_HALF), (-_ROOT_HALF, _ROOT_HALF),
]
HORN_MOUTHS = [
    [round(HORN_POLE_X + dx * HORN_MOUTH_R, 4) + 0.0,
     round(HORN_POLE_Y + dy * HORN_MOUTH_R, 4) + 0.0,
     HORN_AXIS_Z]
    for dx, dy in HORN_DIRS
]
# The drive-clearance proof. -12.70 is the plinth/bin-apron edge, i.e. the
# outboard limit of every surface this machine lets a car stand on.
HORN_DRIVE_EDGE_X = -(FIELD_HW + WALL_T)  # -12.70
HORN_ENVELOPE_X = round(
    max(m[0] for m in HORN_MOUTHS) + HORN_BELL_D / 2.0, 4)
HORN_DRIVE_CLEAR = 0.90
assert HORN_ENVELOPE_X <= HORN_DRIVE_EDGE_X - HORN_DRIVE_CLEAR, (
    "the horn pole's envelope reaches a drivable surface: "
    f"{HORN_ENVELOPE_X} vs {HORN_DRIVE_EDGE_X}"
)
# ... and it must stay clear of the scoreboard's rail, which ends at
# x = -(FIELD_HW + WALL_T) and hangs at y = DIVIDER_Y_FRONT - 0.95, z = 8.00.
_RAIL_END = (HORN_DRIVE_EDGE_X, DIVIDER_Y_FRONT - 0.95)
assert min(
    math.hypot(m[0] - _RAIL_END[0], m[1] - _RAIL_END[1]) for m in HORN_MOUTHS
) >= HORN_BELL_D / 2.0 + 0.70, "a horn bell reaches the payout marker rail"

# ---------------------------------------------------------------------------
# ROUND 5 (2026-08-14): 1970s WOODEN CABINET x MODERN PARLOUR.
#
# Rounds 1-4 pushed the machine from grey industrial towards "parlour", but it
# arrived as ONE language: a red-painted steel tower with a cream board. The
# owner's reference is two machines at once - a blonde plywood 1970s cabinet
# with nickel bezels, cast corner brackets and hand-screened pastel playfield
# art, re-skinned by a modern parlour that adds glossy faceted shrouds,
# holographic numerals, chrome facets and lit tubes.
#
# The split this palette takes, so neither language wins:
#   VINTAGE owns the CABINET and the BOARD - blonde birch ply carcass, nickel
#   trim and hardware, ivory field with mint foliage and mustard/teal confetti,
#   brass pin heads (already there since round 3), cream-on-red deco plaques,
#   a lacquered mask ornament and pink/blue ring targets.
#   MODERN owns the MACHINERY SIDE and the MONEY - gloss black lacquer facet
#   shrouds over the hoist flank, segmented lamp tubes down the board's edges
#   and across its head, a chrome-outlined holographic JACKPOT, and speaker
#   grilles in the board's top corners.
# Deep parlour red survives as the accent that belongs to BOTH (marquee field,
# stringer bands, ridge caps, chute hood) - it is the hinge between them.
#
# What could NOT be done in this round: every glow. Emissive maps were believed
# inert on this pipeline and the only working glow recipe a GE-side PointLight,
# which lives in LUA_BEHAVIOR - frozen for that art pass. The lamp tubes are
# therefore real lacquer geometry with a lit-cell shading cheat baked into
# lamp_bands, and they read as unlit tubes at night.
# THAT PREMISE IS FALSE, and this file now says so in one place - see THE
# EMISSIVE VERDICT immediately below. The lamp tubes have not been rebuilt yet;
# they are a known, costed piece of work, not a limit of the engine.
# ---------------------------------------------------------------------------

# ===========================================================================
# THE EMISSIVE VERDICT (2026-08-15). MEASURED, NOT ARGUED.
#
# This file carried a load-bearing law in four places: "vehicle-material
# emissive is INERT in this pipeline, in every variant anyone has tried". The
# law is RETIRED. The observation behind it was real - every material anyone
# tried really did render black - but the diagnosis was wrong, and the cost of
# the wrong diagnosis was the whole lamp run, the marquee, the bin fascia and
# the payout readout being designed around an engine limitation that does not
# exist.
#
# THE ACTUAL DEFECT IS A FOUR-ELEMENT `emissiveFactor`. Three components emit;
# four are inert, and NOTHING rescues four - not `emissive: true`, not
# `emissiveIntensityNits`, not a value above 1.0. Measured at midnight on a
# real renderer (dx11 windowed, 2560x1421, BeamNG 0.39.4.0 build 20972 - the
# SAME BINARY the player runs, only the user directory is isolated) with all
# twelve of this prop's own PointLights disabled, so every bright pixel in the
# frame is material radiance. Round 4 re-ran it with the decisive pair ADJACENT
# in the same row, because round 3's pair differed in row AND column:
#
#   cell                                  comps  nits  midnight sRGB
#   01 FACTOR3 ONLY  [1,1,1]                  3     -          255.0  EMITS
#   02 F4 UNIT       [1,1,1,1]                4     -            0.0  DEAD
#   03 F4 +NITS      centrifuge letter_glow   4  1800            0.0  DEAD
#   18 CFUGE AMBER   centrifuge beacon_amber  4     -            0.0  DEAD
#   (round 3, same verdicts: 16 F3 OVER1 [2.0,2.05,2.1] 3 comps -> 255.0 EMITS;
#    02 FACTOR+FLAG 3 comps + emissive:true -> 253.0 EMITS)
#
# The unlit control reads exactly sRGB 0.0 in the same frame, and cell 19 - a
# real centrifuge material, transcribed verbatim - reads 0.0 with the lights
# off and 107 with them on. That single pair is the old law's entire evidence
# base, explained: what everyone saw glowing was PointLight wash on a bright
# albedo. Every shipped BeamNG `emissiveFactor` ARRAY writes THREE components:
# 440 in content/vehicles/*.zip, 486 game-wide, histogram {3: 486, 4: 0}, zero
# exceptions. (A further 1,325 keys are JSON null, so a key-presence grep
# returns 1,811 - say which count you mean.) The pack wrote four by analogy
# with `color`, which really is RGBA.
#
# The pack's own "10 of 10" is CONSISTENCY, NOT CORROBORATION. All eight
# materials that never worked are 4-component and both that do work
# (spin_cycle_washer display_lcd, sumo_gyro_platform name_lcd) are 3 - but
# those two ALSO carry `emissive: true` AND `emissiveIntensityNits`, and all
# eight dead ones carry NEITHER. Within this pack, component count is perfectly
# confounded with flag+nits, so the pack data alone cannot tell "4 kills it"
# from "you need nits". The calibration strip does all the actual work: cells
# 01 and 02 differ ONLY in component count, and cell 03 has flag AND nits AND
# is still dead.
#
# WHAT THAT BUYS THIS MACHINE, in the units the design needs (noon,
# TimeOfDay 0.00, unlit control of the same surface = sRGB 17.5):
#
#     60 nit -> sRGB  21   marginal against its own control
#    180 nit -> sRGB  30   reads as lighter paint
#    800 nit -> sRGB  62   unmistakable
#   1800 nit -> sRGB  95   mid-grey panel
#   3500 nit -> sRGB 126
#  15000 nit -> sRGB 217
#  30000 nit -> sRGB 252   last unclipped rung
#  50000 nit -> sRGB 255   fully clipped
#
#   ~3400 nit == as bright as this cabinet's own sunlit blonde ply
#  ~10200 nit == as bright as a sunlit ground plane
#   ~2400 nit == as bright as the sky at zenith
#
# Those three were re-measured in round 4 on CLEAN patches with the boxes drawn
# on the overlay. Round 3 hand-typed them, never drew them, and its ply box
# straddled four dark beams - reading 19% too dark, which drags the derived
# threshold down with it. Never quote a reference brightness from a box that
# has not been drawn.
#
# AND THE TRAP THAT MATTERS MOST HERE: auto-exposure moves under you. At
# midnight, MEASURED rung by rung: 60 -> sRGB 140, 180 -> 213, 240 -> 230,
# 320 -> 245, and 400 -> 254 with 100% of pixels clipped. So night clipping
# starts between 320 and 400 nit, not the "~500" round 3 extrapolated. There is
# NO single nits value that is legible at noon and subtle at midnight - the
# usable night band is ~60-320 as measured (its floor is still unmeasured; 60
# nit still has plenty of modelling left, so "30" was invented) and the usable
# noon band ~1500-15000, and they do not overlap. A
# lamp tube that must work in both has to have its nits driven from Lua per
# time of day, exactly as the yokoku rig already drives PointLight brightness.
# `emissiveMap` MULTIPLIES per texel (round 4: a half-black/half-white map
# renders sRGB 0.0 and 255.0 in the SAME tile at midnight), so a patterned or
# chasing glow is available from material alone. Round 3 called it a no-op on
# a test that used a uniformly WHITE map - white x [1,1,1] = [1,1,1], so it
# could not have failed - and on a map the cooker never even imported, because
# it was named `.emissive.png` and only `.color`/`.data`/`.normal` are cooked.
# Full ledger, method and reproduction: AGENTS.md, "Round-16/17: the
# photometric ledger".
# ===========================================================================

# ---------------------------------------------------------------------------
# THE REVERSE-PRINT INK, and why it is a named constant rather than eight
# literals. Round 3 proved that on a BACKLIT plate the choice of which half
# of the artwork is dark is not decoration - it is the difference between a
# sign that spells its word after dark and a white rectangle that does not.
# The marquee band, the five payout plaques and now the eight letter plates
# all wear the same dress, and they share these two values so that a future
# edit cannot drift one family back onto a white field on its own.
#
# THE RULE, stated once: ANY PLATE THAT IS BOTH SELF-LUMINOUS AND FLOODLIT
# MUST BE REVERSE-PRINTED. A lit field has no headroom; a lit glyph does.
# ---------------------------------------------------------------------------
LETTER_INK = [0.97, 0.93, 0.80]       # cream type, the marquee band's own
LETTER_FIELD = [0.55, 0.06, 0.09]     # deep parlour red, the cabinet's own
# The letter plates' DAY nits, and the one number in this file that is a rung
# LOWER than the family it belongs to. Every other lit sign face on the
# machine is lit by its own glow and a soft fill. These eight are the only
# ones that also carry a 5500 cd flood 3.4 m away, so their own glow may sit
# on the 1200-nit rung (the LCD/gasket rung, a measured one) and the plate
# still totals what an 1800-nit marquee face totals once the flood is on it.
# That is the critic's secondary ask - drop the nominal until the face clears
# clipping BEFORE flood - taken as a fixture decision rather than a fudge.
LETTER_PLATE_DAY_NITS = 1200

PALETTE = {
    f"{MOD_ID}_steel": {
        "texture": {"family": "steel_worn"},
        "color": [0.48, 0.51, 0.55, 1.0],
        "metallic": 0.85,
        "roughness": 0.38,
    },
    # Nickel-plated trim: the vintage cabinet's bezel, sash, hardware and
    # cast brackets. scribed_chrome's machined lines are right for plate, but
    # the round-2 peg lesson applies with full force - at metallic 0.9 /
    # roughness 0.15 a surface IS its reflection and a 25 m bezel would go
    # sky-grey head-on and black obliquely. Mostly-metal but half-matte keeps
    # the plating anchored to its own bright base from every camera, and it
    # sits a clear value step above the cabinet ply (0.72 vs 0.48 luminance)
    # so the frame reads in front of the wood rather than on it.
    f"{MOD_ID}_nickel": {
        # Round 5b: a shade deeper and warmer than the first cut. At 0.70 the
        # plating was brighter than the blonde ply it trims and the front
        # elevation read as a pale grey cage with wood behind it; 0.63 with a
        # warm bias sits just UNDER the ply's value, which is what makes trim
        # read as trim.
        "texture": {"family": "scribed_chrome", "size": 256,
                    "params": {"base": [0.635, 0.640, 0.660]}},
        "color": [0.635, 0.640, 0.660, 1.0],
        "metallic": 0.55,
        "roughness": 0.30,
    },
    # The cabinet carcass. Blonde birch ply with real sheet joints; see
    # birch_ply for why the joint is sized in meters and the laminations are
    # not drawn at all. Authored at 4.5 m per tile on every flank.
    f"{MOD_ID}_cabinet_ply": {
        # Round 5b: paler and less orange (the first cut read as packing
        # crate), and the sheet joint softened - at full strength the panel
        # grid was the loudest thing on a 45 m flank.
        "texture": {"family": "birch_ply", "params": {
            "base": [0.875, 0.790, 0.605], "late": [0.700, 0.585, 0.395],
            "seam": 0.62, "wear": 0.35}},
        "color": [0.845, 0.755, 0.575, 1.0],
        "metallic": 0.0,
        "roughness": 0.38,
    },
    # The playfield. This replaces board_cream on the board FACE only - the
    # bin dividers keep the plain cream enamel, because a screen-printed
    # foliage field on a deflector reads as dirt.
    f"{MOD_ID}_board_field": {
        "texture": {"family": "parlour_field"},
        "color": [0.925, 0.895, 0.795, 1.0],
        "metallic": 0.0,
        "roughness": 0.56,
    },
    # Modern-parlour body-kit lacquer: the faceted shrouds over the hoist
    # flank and the crown fairing. Gloss black with almost no peel, and only
    # a little metal so the facets shade by their own normals instead of
    # mirroring the sky.
    f"{MOD_ID}_lacquer_black": {
        "texture": {"family": "painted_metal", "size": 128,
                    "params": {"base": [0.055, 0.055, 0.066], "rough": 0.15,
                               "peel": 0.12}},
        "color": [0.055, 0.055, 0.066, 1.0],
        "metallic": 0.30,
        "roughness": 0.17,
    },
    # Red-orange lacquer plastic: the central mask ornament and the dome lamp.
    # The one hot colour on the board, and the vintage reference's own.
    f"{MOD_ID}_lacquer_orange": {
        "texture": {"family": "painted_metal", "size": 128,
                    "params": {"base": [0.88, 0.28, 0.085], "rough": 0.18,
                               "peel": 0.2}},
        "color": [0.88, 0.28, 0.085, 1.0],
        "metallic": 0.15,
        "roughness": 0.20,
    },
    # The screen-print palette, as PAINT, for the objects that carry the same
    # story in three dimensions: sunburst rays, the ornament's lattice, the
    # ring targets' rings and eyes, the stringer bands. Small textures on
    # purpose - these are flat inks and a 512 map of flat ink is 300 kB of
    # download for nothing.
    f"{MOD_ID}_accent_yellow": {
        "texture": {"family": "painted_metal", "size": 128,
                    "params": {"base": [0.92, 0.745, 0.145], "rough": 0.26}},
        "color": [0.92, 0.745, 0.145, 1.0],
        "metallic": 0.05,
        "roughness": 0.28,
    },
    f"{MOD_ID}_accent_teal": {
        "texture": {"family": "painted_metal", "size": 128,
                    "params": {"base": [0.155, 0.475, 0.545], "rough": 0.28}},
        "color": [0.155, 0.475, 0.545, 1.0],
        "metallic": 0.05,
        "roughness": 0.30,
    },
    f"{MOD_ID}_accent_pink": {
        "texture": {"family": "painted_metal", "size": 128,
                    "params": {"base": [0.905, 0.475, 0.555], "rough": 0.30}},
        "color": [0.905, 0.475, 0.555, 1.0],
        "metallic": 0.0,
        "roughness": 0.32,
    },
    f"{MOD_ID}_accent_blue": {
        "texture": {"family": "painted_metal", "size": 128,
                    "params": {"base": [0.145, 0.325, 0.615], "rough": 0.28}},
        "color": [0.145, 0.325, 0.615, 1.0],
        "metallic": 0.05,
        "roughness": 0.30,
    },
    f"{MOD_ID}_accent_mint": {
        "texture": {"family": "painted_metal", "size": 128,
                    "params": {"base": [0.635, 0.775, 0.625], "rough": 0.30}},
        "color": [0.635, 0.775, 0.625, 1.0],
        "metallic": 0.0,
        "roughness": 0.32,
    },
    # Lamp tubes. THE HONEST LIMITATION OF THIS ROUND: these are lacquer, not
    # light. lamp_bands bakes a lit-cell falloff and a bright core into the
    # colour so a segment reads as illuminated in daylight, but PointLights
    # live in the frozen Lua, so at night they are painted tubes.
    # This comment used to say "there is no emissive path on this pipeline".
    # There is: a THREE-element `emissive` here plus
    # `"stage": {"emissiveIntensityNits": N}` lights the tube for real (THE
    # EMISSIVE VERDICT above). Not done in this round because the night band
    # (~60-320 nit, measured) and the day band (~1500-15000) do not overlap, so a
    # convincing tube needs its nits driven from Lua per time of day - a
    # design round, not a palette edit.
    # The warm tube runs the board's two vertical edges; the rainbow runs the
    # head rail.
    f"{MOD_ID}_lamp_warm": {
        "texture": {"family": "lamp_bands", "size": 256},
        "color": [0.95, 0.45, 0.10, 1.0],
        "metallic": 0.05,
        "roughness": 0.14,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class 'playfield_edge');
        # the authored value is the DAY target and is what a capture with no
        # runtime attached will show.
        "emissive": [0.95, 0.45, 0.10],
        "stage": {"emissiveIntensityNits": 3500},
    },
    f"{MOD_ID}_lamp_rainbow": {
        "texture": {
            "family": "lamp_bands",
            "size": 256,
            "params": {"colors": [[0.98, 0.45, 0.06], [0.97, 0.82, 0.12],
                                  [0.34, 0.72, 0.36], [0.16, 0.62, 0.68]]},
        },
        "color": [0.60, 0.66, 0.34, 1.0],
        "metallic": 0.05,
        "roughness": 0.14,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class 'playfield_edge');
        # the authored value is the DAY target and is what a capture with no
        # runtime attached will show.
        "emissive": [0.60, 0.66, 0.34],
        "stage": {"emissiveIntensityNits": 3500},
    },
    # Maker's plate and inspection tag. FICTIONAL, deliberately and
    # completely: the reference photos carry a real manufacturer's mark and
    # real Japanese certification stickers, and none of that is reproduced
    # here. "Kogane-Do Amusement Works" is an invented in-world maker and the
    # "Parlour Machine Inspection Board" is an invented body; the model,
    # serial and certificate numbers are this mod's own build numbers. What
    # makes a data plate read as real is the FORMAT - maker line, rule, a
    # label/value block, statutory small print at the bottom - not the names,
    # which is the same finding as the goal post's builder plate.
    f"{MOD_ID}_plate_maker": {
        "texture": {
            "family": "panel_legend",
            "size": 512,
            "params": {
                "title": "",
                "aspect": 3.0,
                "base": [0.58, 0.59, 0.61],
                "ink": [0.075, 0.075, 0.085],
                "label_scale": 0.105,
                "labels": [
                    [0.5, 0.775, "K O G A N E - D O", 1.55],
                    [0.5, 0.610, "A M U S E M E N T   W O R K S", 0.78],
                    [0.28, 0.395, "MODEL", 0.80],
                    [0.66, 0.395, "VVP-50 VERTICAL", 0.92],
                    [0.28, 0.250, "SERIAL", 0.80],
                    [0.66, 0.250, "No. 0060", 0.92],
                    [0.5, 0.095, "28 PIN  5 POCKET   PAT. PEND.", 0.62],
                ],
                "rules": [[0.520, 0.44, 0.016]],
            },
        },
        "color": [0.58, 0.59, 0.61, 1.0],
        "metallic": 0.55,
        "roughness": 0.36,
    },
    f"{MOD_ID}_plate_cert": {
        "texture": {
            "family": "panel_legend",
            "size": 512,
            "params": {
                "title": "",
                "aspect": 2.4,
                "base": [0.86, 0.84, 0.74],
                "ink": [0.20, 0.10, 0.12],
                "label_scale": 0.115,
                "labels": [
                    [0.5, 0.790, "INSPECTED", 1.35],
                    [0.5, 0.630, "PARLOUR MACHINE INSPECTION BOARD", 0.60],
                    [0.5, 0.420, "CERT. PT-0060", 1.05],
                    [0.5, 0.245, "VALID TO 08 / 2027", 0.72],
                    [0.5, 0.090, "REMOVAL OF THIS TAG VOIDS PLAY", 0.52],
                ],
                "rules": [[0.545, 0.40, 0.014]],
            },
        },
        "color": [0.86, 0.84, 0.74, 1.0],
        "metallic": 0.0,
        "roughness": 0.55,
    },
    # Pegs are DARK gunmetal, not chrome. The first cut used scribed_chrome's
    # default base and the pegs disappeared: measured off the shipped texture,
    # chrome's mean luminance is 0.856 against board_cream's 0.871, i.e. a
    # 1.016:1 contrast ratio - the entire point of the machine was invisible
    # against the board it stands on. scribed_chrome's machined-line detail is
    # still what a pachinko pin should look like, so only the base moved:
    # 0.19 luminance gives 3.7:1 against the cream field, comfortably past the
    # 3:1 that WCAG calls the floor for large graphical objects.
    # Round 2: the dark base alone was not enough, because at metallic 0.92 /
    # roughness 0.26 the albedo barely matters - a metal that smooth IS its
    # reflection, so the shanks mirrored the flat sky and went pale
    # environment-grey head-on and void-black at three-quarter. One machine,
    # two colours, depending on where you stood. Mostly-dielectric and
    # half-matte keeps the shading anchored to the dark base, so every peg
    # reads the same machined gunmetal from every camera.
    # Round 4: 0.19 luminance still rendered as mid slate-grey next to the
    # screen slats, and the three-quarter view collapsed into one grey
    # lattice over the artwork. TRUE dark gunmetal now: ~0.11 luminance is
    # 5.6:1 against board_cream, so the shanks read as dark pins, the copper
    # heads pop off them, and the sunburst owns the mid tones.
    f"{MOD_ID}_peg_steel": {
        "texture": {"family": "scribed_chrome", "params": {"base": [0.10, 0.11, 0.13]}},
        "color": [0.11, 0.12, 0.14, 1.0],
        "metallic": 0.30,
        "roughness": 0.50,
    },
    f"{MOD_ID}_hazard": {
        "texture": {"family": "hazard_chevron"},
        "color": [0.94, 0.72, 0.08, 1.0],
        "metallic": 0.1,
        "roughness": 0.5,
    },
    f"{MOD_ID}_board_red": {
        "texture": {"family": "painted_metal", "params": {"base": [0.62, 0.09, 0.11]}},
        "color": [0.62, 0.09, 0.11, 1.0],
        "metallic": 0.15,
        "roughness": 0.45,
    },
    f"{MOD_ID}_board_cream": {
        "texture": {"family": "painted_metal", "params": {"base": [0.90, 0.87, 0.78]}},
        "color": [0.90, 0.87, 0.78, 1.0],
        "metallic": 0.1,
        "roughness": 0.5,
    },
    # Blackened-oxide steel, round 4. The mid-grey galvanized read tried to
    # keep the slats "legible as a screen", but at 0.37 luminance they sat in
    # the SAME value band as the cream board behind them - the three-quarter
    # view became grey scaffolding lying ON the artwork instead of a dark
    # grille in FRONT of it. Figure/ground needs the rails out of the board's
    # value range entirely: near-black oxide recedes, the cream/red sunburst
    # and copper caps come forward, and the copper mullions carry the sash
    # story. Roughness stays at half-matte so the dark bars shade as oxide
    # steel instead of mirroring the sky (the round-2 peg lesson).
    # Round 5b keeps round 4's VALUE (the figure/ground argument below is
    # still right - the slats have to stay out of the board's value band) and
    # only moves its HUE: cool blue-black glazing bars over a warm ivory
    # playfield read as plant steel, the same near-black with a warm bias
    # reads as japanned timber sash. Luminance 0.13 -> 0.14, so the contrast
    # ratio against the field is untouched at ~4.7:1.
    f"{MOD_ID}_screen": {
        "texture": {"family": "mesh_weave", "params": {"base": [0.155, 0.135, 0.120]}},
        "color": [0.155, 0.135, 0.120, 1.0],
        "metallic": 0.5,
        "roughness": 0.50,
    },
    # (The round-6 board_glass entry lived here. It shipped for exactly one
    # build; see BOARD_GLASS above for why a 24 x 41 m translucent pane is a
    # mirror by day and a lens for its own lamps by night. Deleted rather than
    # left dead: an unreferenced palette entry still generates and ships a
    # material set nothing points at.)
    f"{MOD_ID}_concrete": {
        "texture": {"family": "concrete"},
        "color": [0.62, 0.60, 0.57, 1.0],
        "metallic": 0.0,
        "roughness": 0.82,
    },
    f"{MOD_ID}_asphalt": {
        "texture": {"family": "asphalt"},
        "color": [0.16, 0.16, 0.17, 1.0],
        "metallic": 0.0,
        "roughness": 0.9,
    },
    # The brass family: mullions, crown sign frame, peg heads, sheaves and
    # marker ticks. At the family's default base the mottle dominated and the
    # whole family read as rust-brown corten - the design story says vintage
    # parlor BRASS, and the front sash is the material the player parks in
    # front of. Brighter warm base + a lower roughness floor (the family's
    # rough param sets the in-game roughness MAP's baseline; the palette
    # factor below is what the Blender preview and the untextured fallback
    # use) turns the same mottle into polish wear on bright metal, so sash,
    # sign frames and peg heads tell one polished-brass story.
    # Round 6: STILL BROWN. Round 5's brighter base fixed the corten read but
    # the peg heads came back as milk chocolate against the new ivory field -
    # the field's own luminance is 0.90, and copper at base value 0.70 with a
    # mottle that swings +/-0.21 spends most of its area BELOW the board it is
    # supposed to stand out from. Brass is a bright, near-yellow metal: the
    # base goes up to 0.86 and, crucially, its green channel comes up with it
    # (0.42 -> 0.66 is what separates brass from copper - copper's g/r is
    # ~0.60, brass's is ~0.76), while the roughness FLOOR drops from 0.30 to
    # 0.17 so the heads carry a specular highlight instead of reading as
    # matte paint. Kept a clear step off pure gold (jackpot_gold is the one
    # gilt on the machine) and metallic left at 0.9, because at this
    # roughness the family's own mottle still anchors the colour.
    f"{MOD_ID}_copper": {
        "texture": {"family": "copper", "params": {"base": [0.86, 0.66, 0.30], "rough": 0.17}},
        "color": [0.86, 0.66, 0.30, 1.0],
        "metallic": 0.9,
        "roughness": 0.18,
    },
    f"{MOD_ID}_deck_grip": {
        "texture": {"family": "rubber_tread", "params": {"base": [0.20, 0.21, 0.22]}},
        "color": [0.20, 0.21, 0.22, 1.0],
        "metallic": 0.0,
        "roughness": 0.85,
    },
    # Bin interiors, round 4. The old garden-green enamel was the one colour
    # on the machine that belonged to no other part of it - the payoff band
    # the player stares at read as municipal planters under a parlor board.
    # The pockets are now dark gunmetal trays (a shade up from peg_steel so a
    # landed car still reads inside them), the divider bodies wear the
    # cabinet's cream enamel and the ridge caps its red, so the bin band
    # tells the same red-cream-copper story as the board above - with the
    # jackpot's gold still the only exception on the fascia.
    f"{MOD_ID}_bin_gunmetal": {
        "texture": {"family": "painted_metal", "params": {"base": [0.13, 0.14, 0.16]}},
        "color": [0.13, 0.14, 0.16, 1.0],
        "metallic": 0.35,
        "roughness": 0.45,
    },
    # Jackpot gold: the crown treatment for the ONE bin that matters. Painted
    # metal like the cabinet colours (same peel, same blotch) so it reads as
    # the parlor's gilt paint rather than a foreign chrome; metallic is kept
    # at 0.55 with a mid roughness so the glint anchors to the warm base
    # instead of mirroring the sky (the peg-steel lesson: a smooth high-metal
    # surface IS its reflection and stops being a colour).
    f"{MOD_ID}_jackpot_gold": {
        "texture": {"family": "painted_metal", "params": {"base": [0.86, 0.63, 0.14]}},
        "color": [0.86, 0.63, 0.14, 1.0],
        "metallic": 0.55,
        "roughness": 0.35,
    },
    # Marquee backer boards, round 4. The crown and flank title plates used
    # to sit on slabs of the copper family, and at sign scale the patina
    # mottle stopped reading as metal at all - it read as mud-brown
    # rust-streaked planking. Lean into the plank read instead: a lacquered
    # red-brown hardwood backer (deeper and redder than the copper's warm
    # tan, so the two never blur), which is what a real parlor marquee is
    # mounted on. Copper stays the FRAME metal - value plaque frames, letter
    # frames, mullions, ticks - and the wood is only ever the board behind a
    # sign. wood family defaults: cathedral figure, French-polish sheen; the
    # early/late pair below is the mahogany version of its walnut default.
    f"{MOD_ID}_marquee_wood": {
        "texture": {
            "family": "wood",
            "params": {"early": [0.44, 0.17, 0.10], "late": [0.13, 0.045, 0.03]},
        },
        "color": [0.38, 0.15, 0.09, 1.0],
        "metallic": 0.0,
        "roughness": 0.26,
    },
    # Signs. marquee draws into a 9.55:1 strip and stretches it into the square
    # texture, so every plate that wears one is authored at that aspect and
    # keeps Blender's default full-face cube UVs (no metric_uv, no bevel).
    # The crown marquee is the one piece of pure theatre the tower gets, and
    # the default navy-on-white read as office wayfinding. Parlor colours
    # instead: cream lettering on the cabinet's own deep red, so the sign and
    # the board tell one story. (Value plates and the DRIVE IN instruction
    # stay white - those are signage that must be READ, not felt.)
    f"{MOD_ID}_sign_title": {
        "texture": {
            "family": "marquee",
            "params": {
                "text": "PACHINKO TOWER",
                "fg": [0.97, 0.93, 0.80],
                "bg": [0.55, 0.06, 0.09],
            },
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class 'marquee');
        # the authored value is the DAY target and is what a capture with no
        # runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": 1800},
    },
    # One ink for the money (and the instruction): every white-field sign
    # letters in the same deep parlor red the JACKPOT plate already wears.
    # The marquee family's default navy was the last office colour on the
    # machine; white fields stay for readability, the ink tells one story.
    f"{MOD_ID}_sign_load": {
        "texture": {
            "family": "marquee",
            "params": {"text": "DRIVE IN - HOLD STILL", "fg": [0.62, 0.03, 0.05]},
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
    },
    # Round-5 payout band: FOUR VINTAGE PLAQUES AND ONE MODERN ONE. The
    # digit plates now letter in cream on the cabinet's own deep parlour red
    # - the deco nameplate treatment off the 1970s reference, and the same
    # dress the crown marquee wears - while the JACKPOT goes holographic
    # (see sign_bin_2). Inverting the old red-on-white is what lets the
    # fascia read as a period payout board instead of five office labels,
    # and it leaves the one plate that matters as the only thing on the
    # machine wearing a spectrum.
    f"{MOD_ID}_sign_bin_0": {
        "texture": {
            "family": "marquee",
            "params": {"text": "3000", "fg": [0.965, 0.925, 0.795],
                       "bg": [0.55, 0.06, 0.09]},
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class 'gasket');
        # the authored value is the DAY target and is what a capture with no
        # runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": 1200},
    },
    f"{MOD_ID}_sign_bin_1": {
        "texture": {
            "family": "marquee",
            "params": {"text": "1500", "fg": [0.965, 0.925, 0.795],
                       "bg": [0.55, 0.06, 0.09]},
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class 'gasket');
        # the authored value is the DAY target and is what a capture with no
        # runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": 1200},
    },
    # THE ONE MODERN PLATE. Round 4 made the jackpot cream-on-red like the
    # marquee, which was correct and made it identical to the four plates
    # beside it. The modern parlour's whole signature is the enormous
    # holographic numeral - rainbow foil, hard chrome outline, drop shadow -
    # so that is exactly what the 10000 gets, on a deep violet-black field
    # dark enough for the shadow to exist. fg is unused on the holo path (the
    # fill is the spectrum); bg is the plate field, and it is violet rather
    # than pure black so the drop shadow has something to darken.
    #
    # THE WINDOW DEBT: the holo path draws TWO ink layers outside the glyph,
    # so this texture's measured ink windows are wider than the flat ones.
    # The generator's jackpot word windows were re-measured off the built
    # PNG after this change; do not copy the round-4 numbers back.
    f"{MOD_ID}_sign_bin_2": {
        "texture": {
            "family": "marquee",
            "params": {
                "text": "JACKPOT 10000",
                "holo": True,
                "fg": [0.97, 0.93, 0.80],
                "bg": [0.105, 0.085, 0.155],
            },
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class 'gasket');
        # the authored value is the DAY target and is what a capture with no
        # runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": 1200},
    },
    f"{MOD_ID}_sign_bin_3": {
        "texture": {
            "family": "marquee",
            "params": {"text": "800", "fg": [0.965, 0.925, 0.795],
                       "bg": [0.55, 0.06, 0.09]},
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class 'gasket');
        # the authored value is the DAY target and is what a capture with no
        # runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": 1200},
    },
    f"{MOD_ID}_sign_bin_4": {
        "texture": {
            "family": "marquee",
            "params": {"text": "400", "fg": [0.965, 0.925, 0.795],
                       "bg": [0.55, 0.06, 0.09]},
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class 'gasket');
        # the authored value is the DAY target and is what a capture with no
        # runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": 1200},
    },
    # Vertical parlor sign: one marquee plate per letter of P-A-C-H-I-N-K-O,
    # hung down the outboard shaft face (the classic parlor treatment is
    # stacked UPRIGHT letters, not a rotated banner).
    #
    # REVERSE-PRINTED, and round 3 is where that stopped being a style note
    # and became the reason the sign is legible at all. These eight plates
    # were white-field / red-ink, matching the payout plaques as they were
    # BEFORE round 5 inverted those too. Under the letter floods that art is
    # unreadable at night, and the mechanism is arithmetic rather than taste:
    #
    #   * the glow map is ALBEDO seen through the backlight (see
    #     texture_kit._marquee_glow), so a 0.93-albedo field emits nearly all
    #     of the plate's nits and renders at sRGB 200-240 - 38% of the face
    #     already CLIPPED - before a single flood photon lands on it;
    #   * a clipped field cannot get brighter. So every candela the chase
    #     head adds goes into raising the RED GLYPH toward a field that
    #     cannot move away from it. Michelson contrast inside the plate
    #     measured 0.000 - a uniform white square - on 1 to 3 of the 8 plates
    #     in EVERY frame of EVERY mode, and the sign never once spelled
    #     PACHINKO after dark. Raising or lowering the flood cannot fix it:
    #     36.3% clip at 5500 cd against 37.4% at 9000 cd is the same
    #     plateau, which is what a saturated surface looks like.
    #
    # The marquee band 6 m away, photographed in the SAME frame, clipped
    # 0.0% - because it is cream type on the cabinet's deep red, and on a lit
    # box the DARK half is the half with headroom. That is reverse-printed
    # signwriting and it is why the type on a real parlour box is brighter
    # than its field. The plates now wear the marquee's own dress, so the
    # flood saturates the GLYPH and the letter gets MORE legible as the chase
    # head passes - which is the entire point of a marquee chase.
    f"{MOD_ID}_sign_letter_0": {
        "texture": {
            "family": "marquee",
            "params": {"text": "P", "fg": LETTER_INK, "bg": LETTER_FIELD},
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class
        # 'letter_plate'); the authored value is the DAY target and is what
        # a capture with no runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": LETTER_PLATE_DAY_NITS},
    },
    f"{MOD_ID}_sign_letter_1": {
        "texture": {
            "family": "marquee",
            "params": {"text": "A", "fg": LETTER_INK, "bg": LETTER_FIELD},
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class
        # 'letter_plate'); the authored value is the DAY target and is what
        # a capture with no runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": LETTER_PLATE_DAY_NITS},
    },
    f"{MOD_ID}_sign_letter_2": {
        "texture": {
            "family": "marquee",
            "params": {"text": "C", "fg": LETTER_INK, "bg": LETTER_FIELD},
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class
        # 'letter_plate'); the authored value is the DAY target and is what
        # a capture with no runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": LETTER_PLATE_DAY_NITS},
    },
    f"{MOD_ID}_sign_letter_3": {
        "texture": {
            "family": "marquee",
            "params": {"text": "H", "fg": LETTER_INK, "bg": LETTER_FIELD},
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class
        # 'letter_plate'); the authored value is the DAY target and is what
        # a capture with no runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": LETTER_PLATE_DAY_NITS},
    },
    f"{MOD_ID}_sign_letter_4": {
        "texture": {
            "family": "marquee",
            "params": {"text": "I", "fg": LETTER_INK, "bg": LETTER_FIELD},
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class
        # 'letter_plate'); the authored value is the DAY target and is what
        # a capture with no runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": LETTER_PLATE_DAY_NITS},
    },
    f"{MOD_ID}_sign_letter_5": {
        "texture": {
            "family": "marquee",
            "params": {"text": "N", "fg": LETTER_INK, "bg": LETTER_FIELD},
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class
        # 'letter_plate'); the authored value is the DAY target and is what
        # a capture with no runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": LETTER_PLATE_DAY_NITS},
    },
    f"{MOD_ID}_sign_letter_6": {
        "texture": {
            "family": "marquee",
            "params": {"text": "K", "fg": LETTER_INK, "bg": LETTER_FIELD},
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class
        # 'letter_plate'); the authored value is the DAY target and is what
        # a capture with no runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": LETTER_PLATE_DAY_NITS},
    },
    f"{MOD_ID}_sign_letter_7": {
        "texture": {
            "family": "marquee",
            "params": {"text": "O", "fg": LETTER_INK, "bg": LETTER_FIELD},
        },
        "color": [1.0, 1.0, 1.0, 1.0],
        "metallic": 0.0,
        "roughness": 0.35,
        # LIT. Three components - four is inert and nothing rescues it.
        # Level is DRIVEN from Lua per time of day (fixture class
        # 'letter_plate'); the authored value is the DAY target and is what
        # a capture with no runtime attached will show.
        "emissive": [1.0, 1.0, 1.0],
        "stage": {"emissiveIntensityNits": LETTER_PLATE_DAY_NITS},
    },
    # PA horn paint (round 8). The reference unit is grey-olive enamel over
    # spun steel, chalked by weather - not a metal, not a plastic. `steel` is
    # far too specular for it (a 1.4 m bell at metallic 0.85 mirrors the sky
    # and loses its shape entirely), so the bells and driver bodies get their
    # own paint while the pole, bracket and hardware stay galvanised `steel`.
    # peel is high because the whole point of the finish is that it is OLD.
    f"{MOD_ID}_horn_olive": {
        "texture": {"family": "painted_metal", "size": 256, "params": {
            "base": [0.415, 0.435, 0.360], "rough": 0.47, "peel": 0.95}},
        "color": [0.415, 0.435, 0.360, 1.0],
        "metallic": 0.22,
        "roughness": 0.47,
    },
}

# Winding is retired wholesale on this pack (AGENTS.md 2026-08-07 policy):
# an inside-out hand-built mesh is invisible in game and renders perfectly in
# Blender, so every surface draws from both sides.
for _palette_entry in PALETTE.values():
    _palette_entry["double_sided"] = True

# Bin values. Derived, not sprinkled: the car enters at the TOP RIGHT (the
# crown chute lip at x = +6.0), so value grows with how far left the car must
# be knocked, and the middle bin pays the jackpot because its mouth is choked
# to 2.60 m by the horned dividers. Mouth widths, left to right, are
# 4.80 / 5.90 / 2.60 / 5.90 / 4.80 m.
BIN_VALUES = [3000, 1500, 10000, 800, 400]

TRIGGERS = {
    # Contains: the car must be fully on the carriage deck before the machine
    # will hoist it. 4.4 x 6.2 sits inside the 4.8 x 6.6 deck and clears the
    # pack gate's 2.9 x 4.5 x 3.0 minimum. The box floor is deliberately
    # 0.50 m BELOW the deck surface: the catapult seesaw's countdown never
    # latched because a big SUV's live OOBB dipped under a zone floor set at
    # the deck plane, and Contains needs the whole box, not the centre.
    "load_zone": {
        "mode": "Contains",
        "center": [(DECK_X0 + DECK_X1) / 2.0, 0.0, DOCK_FLOOR_Z + 1.70],
        "dimensions": [4.4, 6.2, 4.4],
    },
    # Overlaps: the whole fall volume. CONSUMED by behavior.onEnter as the
    # rogue-car detector - a car that arrives on the board without having been
    # hoisted (knocked in by another prop, or driven off the crown chute) is
    # adopted as the subject and scored where it lands instead of being
    # ignored. Adoption deliberately keys off the CROSSING and not off
    # occupancy: a car left wedged in the pegs after a fall timeout is already
    # inside the box, generates no new crossing, and therefore cannot put the
    # machine into an adopt/timeout loop.
    "field_zone": {
        "mode": "Overlaps",
        "center": [0.0, 0.0, (RIDGE_Z + WALL_TOP_Z) / 2.0],
        "dimensions": [2 * FIELD_HW + 0.2, 2 * DEPTH_HALF + 0.2, WALL_TOP_Z - RIDGE_Z],
    },
    # Overlaps: the bin pockets and the drive-out lane in front of them.
    # CONSUMED twice: the scored event carries the engine's own in_catch read
    # next to the geometric bin read so the two can be compared in the log,
    # and driving out of it cuts the payout hold short so the tower re-arms
    # for the next player instead of holding an empty pose.
    "catch_zone": {
        "mode": "Overlaps",
        "center": [0.0, (DIVIDER_Y_FRONT + DEPTH_HALF) / 2.0, RIDGE_Z / 2.0 + 0.2],
        "dimensions": [2 * FIELD_HW + 0.2, DEPTH_HALF - DIVIDER_Y_FRONT, RIDGE_Z + 0.4],
    },
    # Overlaps: the crown - the chute, the hood throat and the docked deck at
    # the top of its travel. This zone exists for ONE structural reason: the
    # framework only delivers onSubjectGone for a vehicle it can find in some
    # zone (removeSubjectEverywhere), and a car sitting on the tipped deck at
    # z ~44.5 was inside none of the others, so a player who hit "reset" up
    # there left the machine waiting out its full release timeout. Spans the
    # chute lip (x = 6.0) to the outboard deck edge (x = 17.4) and from the
    # chute's low end up past the docked deck's kick rail.
    "crown_zone": {
        "mode": "Overlaps",
        "center": [(APRON_X_LO + DECK_X1) / 2.0, 0.0, (APRON_Z_LO - 1.0 + DECK_DOCK_Z + 3.0) / 2.0],
        "dimensions": [
            DECK_X1 - APRON_X_LO,
            2 * DEPTH_HALF + 0.2,
            (DECK_DOCK_Z + 3.0) - (APRON_Z_LO - 1.0),
        ],
    },
}

# One dust burst per bin so the machine puffs where the car actually landed.
# BNGP_2 is the only emitter this pack has ever confirmed for itself. (It was
# said to be "confirmed on 0.38.6"; that string was the test profile directory
# name. Re-checked 2026-08-15 against v0.39.4.0 build 20972: still shipped.)
EFFECTS = {
    f"bin_dust_{index}": {
        "emitter": "BNGP_2",
        "position": [center, -1.2, BIN_FLOOR_Z + 0.6],
        "direction": [0.0, 0.0, 1.0],
    }
    for index, center in enumerate(BIN_CENTERS)
}

# ---------------------------------------------------------------------------
# THE HOIST EASE-OUT (2026-08-14h, the player: "slow down the upward movement
# of the elevator toward the end because the momentum makes lighter vehicles
# fly up when it stops").
#
# WHAT WAS ACTUALLY WRONG. updateHoist ran a SQUARE command: liftRate was
# hoist_speed_mps for the whole 43.085 m and then 0 in one frame at the dock.
# The car is not standing on anything during the ride (the deck's collision is
# baked at HOME until the dock - see updateHoist), so it is a free body whose
# velocity the servo writes each frame, and the servo may only change that
# velocity by frame_dv_cap per frame. Cancelling 8.0 m/s at 1.5 m/s per frame
# therefore takes six frames, during which the car keeps climbing ~0.4 m past
# the dock height while the deck has already stopped - and it is at exactly
# that moment that the dock bake puts a floor back under it. The car lands on
# a plate that has come up under it. That is the "fly up when it stops" the
# player sees, and it is worse for a LIGHT vehicle only because a light car's
# suspension rebounds further off the same arrival.
#
# THE PROFILE, AND WHY IT IS DERIVED. Constant deceleration to zero at the
# dock: v(s) = sqrt(2 * a * s) over the last HOIST_TAPER_M metres, capped at
# the cruise speed. Both numbers come out of constants that are already tuned:
#
#   * the taper LASTS EXACTLY dock_settle_seconds. The machine already waits
#     that long at the top for the car to seat, so the ease-out is sized to
#     the settle it feeds: s = v * t / 2 = 8.0 * 1.6 / 2 = 6.40 m.
#   * that fixes the deceleration at a = v / t = 8.0 / 1.6 = 5.00 m/s^2,
#     which is the number that actually matters and is asserted below:
#     A MUST STAY UNDER g. The servo can only hold a car DOWN by removing
#     velocity, and gravity is already removing 9.81 m/s^2 of it for free. A
#     ramp shallower than g is one the car can follow while still being
#     pulled onto the deck rather than thrown off it; a ramp steeper than g
#     would need the servo to accelerate the car downward, which is the same
#     ballistic-arrival failure in the other direction.
#
# THE RIDE TIME BUDGET. 8.0 m/s was chosen as a MEASURED KNEE (see
# hoist_speed_mps): slower is worse because tilt integrates over airtime, and
# FASTER was also worse because the servo could no longer arrest the climb
# inside dock_settle_seconds. The taper costs
#   HOIST_TAPER_M / hoist_speed  ->  2 * HOIST_TAPER_M / hoist_speed
# i.e. 0.80 s on a 5.39 s ride (+15%), and it buys the arrest the 10 m/s
# experiment could not get. It is the cheap half of that trade, not a return
# to the slow rides that produced 45 deg arrivals.
HOIST_SPEED_MPS = 8.0
DOCK_SETTLE_SECONDS = 1.6
HOIST_TAPER_M = HOIST_SPEED_MPS * DOCK_SETTLE_SECONDS / 2.0  # 6.40
HOIST_TAPER_DECEL = HOIST_SPEED_MPS**2 / (2.0 * HOIST_TAPER_M)  # 5.00 m/s^2
assert HOIST_TAPER_DECEL < 9.81, (
    f"the hoist ease-out decelerates at {HOIST_TAPER_DECEL:.2f} m/s2, harder "
    "than gravity: the servo would have to drive the car DOWN onto the deck"
)
# The sqrt profile's commanded speed goes to zero AT the dock, so a floor is
# needed or the last centimetres take unboundedly many frames. It engages
# under v^2 / (2a) = 0.012 m of remaining travel and costs ~0.04 s.
HOIST_CREEP_MPS = 0.35
# THE SEAT DROP that has to be paid for the ease-out. Derived from the height
# the OVERSHOOT used to leave the car at when the carriage stopped, measured
# 1.1-1.4 m over the s51 n=15: sqrt(2 * g * 1.2) = 4.85 m/s of arrival, of
# which the car's own 0.22 m rest height already supplies ~2.1. 4.0 reproduces
# it with margin to spare and stays inside the machine's own impulse ceiling.
DOCK_SEAT_DV_MPS = 2.0
DOCK_SEAT_FALL_M = DOCK_SEAT_DV_MPS**2 / (2.0 * 9.81)
# THE DROOP LIFT. See seatLiftNow() for the mechanism; the number is set by a
# MEASUREMENT rather than a feel: a car in free flight on the servo droops
# 0.40-0.43 m between lift-off and the crown (attitude probe, five plays,
# ref-node to lowest-node), so the set-point has to rise by more than that or
# the dock bake stamps the deck through the car's hanging wheels. 0.90 is 2.2x
# the measured droop, and the fall it then produces (4.2 m/s) is the landing
# that rights the car - the same work the old overshoot was doing by accident,
# from 1.1-1.4 m instead of 0.9.
HOIST_SEAT_LIFT_M = 0.90
_MEASURED_FLIGHT_DROOP_M = 0.43
assert HOIST_SEAT_LIFT_M > 2.0 * _MEASURED_FLIGHT_DROOP_M, (
    f"the droop lift is {HOIST_SEAT_LIFT_M} m against a measured "
    f"{_MEASURED_FLIGHT_DROOP_M} m of flight droop: the dock bake will land "
    "inside the car's wheels"
)
# Total arrival: 0.20 s of free fall, then the seat tap, then the rest of the
# drop. Kept under the machine's own 7.0 m/s impulse ceiling.
_DOCK_ARRIVAL_MPS = (
    (math.sqrt(2 * 9.81 * 0.196) + DOCK_SEAT_DV_MPS) ** 2
    + 2 * 9.81 * (HOIST_SEAT_LIFT_M - 0.196)
) ** 0.5
assert _DOCK_ARRIVAL_MPS < 7.0, (
    f"the car reaches the deck at {_DOCK_ARRIVAL_MPS:.2f} m/s: harder than "
    "any other impulse this machine allows itself"
)
_HOIST_RIDE_S = (LIFT_TRAVEL - HOIST_TAPER_M) / HOIST_SPEED_MPS + 2.0 * HOIST_TAPER_M / HOIST_SPEED_MPS
assert HOIST_TAPER_M < LIFT_TRAVEL / 2.0, "the ease-out is most of the ride"

BEHAVIOR = {
    # ---- presentation -------------------------------------------------
    "camera_distance": 70.0,
    # ---- geometry the runtime needs (authored frame) -------------------
    "field_hw": FIELD_HW,
    "depth_half": DEPTH_HALF,
    # The box the peg-restore node scan sweeps. Deliberately the SAME box
    # field_zone describes (RIDGE_Z to WALL_TOP_Z) so the node cloud and the
    # trigger are answering one question with two instruments - see
    # fieldCloudOccupied. Derived from the same constants the zone spec uses,
    # so the two cannot drift apart.
    "peg_guard_z_lo": RIDGE_Z,
    "peg_guard_z_hi": WALL_TOP_Z,
    # A bin only pays for a car actually DOWN IN the pocket. Wheels on the
    # bin floor put the highest plausible ref node at
    # BIN_FLOOR_Z + car_rest_height_max = 1.95, and a car standing on its
    # nose tops out near 2.2; a car perched ON a divider body reads 3.2+ and
    # on the centre horns 5.2+. 2.45 separates the regimes with margin both
    # ways. The first cut guarded only above RIDGE_Z + 1.0 = 6.0 - higher
    # than any resting ref node can reach - so a car sitting ON the centre
    # horn was paid the jackpot it was physically blocking, and a car perched
    # on a divider body was paid whichever bin the rounding chose.
    "score_max_z": BIN_FLOOR_Z + CAR_HEIGHT + 0.6,
    "bin_pitch": BIN_PITCH,
    "peg_pitch_x": PEG_PITCH_X,
    "bin_values": BIN_VALUES,
    # 5 entries, so no vec3 coercion. Drives the payout marker's park points.
    "bin_centers": BIN_CENTERS,
    # A resting car only scores while it is still inside a bin pocket; past
    # this the divider walls have ended and it has driven itself out.
    "bin_y_front": DIVIDER_Y_FRONT,
    "deck_center_x": (DECK_X0 + DECK_X1) / 2.0,
    "deck_half_x": (DECK_X1 - DECK_X0) / 2.0,
    "deck_half_y": DECK_HALF_Y,
    "deck_home_z": DECK_HOME_Z,
    "lift_travel": LIFT_TRAVEL,
    "sheave_radius": SHEAVE_R,
    "gate_open_deg": GATE_OPEN_DEG,
    # ---- loading -------------------------------------------------------
    # Same "hold still" gate the seesaw uses: 0.7 m/s is above sensor noise
    # and below a crawl, so a driver who has actually stopped latches.
    "park_speed_max": 0.7,
    "park_seconds": 2.5,
    "load_timeout_seconds": 150.0,
    # Idle re-arm. Zone triggers only fire on CROSSINGS (AGENTS.md), so a car
    # already standing on the deck when the tower comes home cannot re-arm it
    # by entering - and two of this machine's own abort paths park a car
    # exactly there. The idle branch therefore POLLS load_zone occupancy, and
    # this grace stops the poll from re-arming inside the same frame the
    # "reloaded" toast is drawn.
    "rearm_grace_seconds": 1.2,
    # ---- hoist ---------------------------------------------------------
    # Speed, not duration: the carriage then always ends exactly at the dock
    # no matter what dtSim really is on the player's machine.
    # LESS AIRTIME IS LESS INTEGRATED ROTATION - and the curve has a KNEE,
    # measured, not guessed (2026-08-14f). The car flies the whole ride held
    # by a torque-free servo, so the tilt it arrives with is the integral of
    # its lift-off rate over the airtime. Baking a floor under it was tried
    # first and DESTROYS the car (see updateHoist). Speed is what is left.
    #
    # Mean arrival tilt / arrival ref-above-contact gap, attitude probe,
    # 5-6 plays each:
    #     3.2 m/s (13.5 s ride)   45.4 deg    0.73 - 0.96 m
    #     6.0 m/s ( 7.2 s ride)   14.6 deg    0.44 - 0.49 m
    #     8.0 m/s ( 5.4 s ride)    2.8 deg    0.12 - 0.25 m   <-- the knee
    #    10.0 m/s ( 4.3 s ride)   15.9 deg    0.50 - 0.76 m
    # It is not monotonic. Past 8 the servo can no longer arrest the climb
    # inside dock_settle_seconds, so the car arrives still moving and lands
    # badly - the gain from less airtime is spent on a worse arrival. At 8
    # the cars come in level (2.8 deg) and SEATED: 0.12-0.25 m is the
    # undamaged seated value measured in F7, i.e. the ride no longer
    # degrades the arrival at all.
    #
    # ...AND SINCE 2026-08-14h THIS IS THE CRUISE SPEED ONLY. The last
    # hoist_taper_m of travel ramps it down to a standstill at the dock - see
    # THE HOIST EASE-OUT above for why the square command is what threw light
    # cars off the plate, and hoistCommandRate() for the four lines that
    # implement it.
    "hoist_speed_mps": HOIST_SPEED_MPS,
    "hoist_taper_m": HOIST_TAPER_M,
    "hoist_taper_decel": HOIST_TAPER_DECEL,
    "hoist_creep_mps": HOIST_CREEP_MPS,
    # Ramped in over the same taper. See seatLiftNow(): without it the ease-out
    # hands the dock bake a car whose wheels are hanging through the plate.
    "hoist_seat_lift_m": HOIST_SEAT_LIFT_M,
    "return_speed_mps": 5.2,
    # Fallback only. The servo's set-point is MEASURED at the moment the
    # hoist starts (the car's own ref-node height above the deck it is
    # already parked on), because that height is per-vehicle - an etk800's
    # ref node sits 0.205 m up, a pickup's much higher - and guessing it
    # would make the car settle with a drop when the deck re-bakes at the
    # dock. This value is used only if the measurement is out of range.
    "car_rest_height": 0.45,
    "car_rest_height_min": 0.10,
    "car_rest_height_max": 1.60,
    # Support servo. hoist_kp is the proportional term on height error, in
    # 1/s; 2.6 gives a ~0.4 s correction time constant, far softer than the
    # ~19 m/s single-frame injection that shredded cars on the centrifuge.
    "hoist_kp": 2.6,
    # Must stay above hoist_speed_mps or the servo cannot even track the
    # deck it is following, let alone correct height error on top. The ease-out
    # only ever commands LESS than hoist_speed_mps, so it needs nothing extra
    # here - asserted below rather than asserted in prose.
    "hoist_v_max": 12.0,
    # Per-frame velocity change cap. Cancelling gravity alone needs
    # g * dt = 0.163 m/s at 60 Hz, so 1.5 leaves 9x of authority and is a
    # quarter of the centrifuge's proven 6.0 m/s cap.
    "frame_dv_cap": 1.5,
    # Skip a sample already moving absurdly fast (AGENTS.md: never feed a
    # solver that is already losing the vehicle).
    "runaway_speed_mps": 45.0,
    # Abort thresholds, derived from the deck's own half-extents plus one
    # margin: the car has left the platform it is being carried on.
    "slip_margin_m": 0.85,
    "slip_drop_m": 3.0,
    # Watchdog, not a schedule: with the 2026-08-14h ease-out the hoist
    # finishes in (LIFT_TRAVEL - taper) / speed + 2 * taper / speed
    # = 4.59 + 1.60 = 6.19 s (it was 5.39 s on the square command). 40 s is
    # 6x that, so it only fires if the phase genuinely hangs (a pcall'd pose
    # call that throws every frame, or a stalled dtSim).
    "hoist_timeout_seconds": 40.0,
    # A sample this far outside the machine's own footprint is not on the
    # machine any more (the player reset, or something threw the car clear).
    # 2 * FIELD_HW is the board width, so 6.0 m of slop is unambiguous.
    "lost_margin_m": 6.0,
    # ---- release -------------------------------------------------------
    # ALSO the length of the hoist ease-out (HOIST_TAPER_M is derived from it),
    # so changing this changes how the carriage arrives as well as how long it
    # then waits.
    "dock_settle_seconds": DOCK_SETTLE_SECONDS,
    # THE SEAT DROP. See updateDock for the measurement that forced it: the
    # ease-out removed the overshoot, and the overshoot's fall was the only
    # thing righting a hoisted car. 4.0 m/s reproduces it deliberately;
    # 0.20 s lets the dock bake land first. Both are asserted below.
    "dock_seat_dv_mps": DOCK_SEAT_DV_MPS,
    "dock_seat_delay_seconds": 0.20,
    "gate_seconds": 1.4,
    # Ratchet detents. Never exactly three - a 3-number list is serialized
    # as a vec3 by lua_kit and B.x[1] then throws. Since the tip became an
    # empty-deck flourish these are VISUAL-ONLY - the rack's tooth angles -
    # and the deck's motion no longer stops at them. Kept because the rack
    # generator imports this list.
    "tip_detents": [0.0, 17.0, 34.0, 51.0, 68.0],
    # THE CONFORMAL BAKE LAW (2026-08-13, third live failure of the tip
    # mechanism, and the one that killed it): a collision bake may only be
    # taken at a pose the subject vehicle is ALREADY conformally resting
    # on. The carry servo moved the car's ref point along the tipping
    # plate's arc, but the CAR ITSELF STAYED LEVEL - so the endpoint bake
    # stood a 68 deg wall through the middle of a level car (tan(68) x
    # half a wheelbase ~ 4 m of embedded steel). The solver then either
    # ejected the car violently (the player's "vehicles fall through the
    # lift") or set it down to slide into the 180-68-40 = 72 deg V-notch
    # where plate meets chute and JAM (police-truck screenshot; the log
    # run rested exactly on the 68 deg surface line at x 13.38). No angle,
    # ramp rate, or bake count fixes this: tipping an OCCUPIED deck is
    # unworkable on snapshot collision, full stop.
    #
    # So the release no longer tips the car at all. The deck stays LEVEL
    # on its honest dock bake, an EJECT velocity field (the sumo/car-wash
    # tangential-push pattern, both live-proven) walks the car inboard
    # over the hinge lip - a CONVEX edge, which geometrically cannot trap -
    # and the crown chute's static 40 deg ice slab does the redirect. The
    # tip below is now an empty-deck FLOURISH that plays after release,
    # with NO bake at all (nothing stands on the crown deck once the car
    # is gone; the drawn plate over level collision touches nothing).
    # Whole-cycle budget: 3 global be:reloadCollision calls (dock,
    # gate-open, return endpoint), none with a car in a pose it is not
    # already resting on.
    "tip_full_deg": 68.0,
    "tip_ramp_seconds": 3.3,
    # The eject field. 2.6 m/s inboard reads as a firm conveyor shove and
    # crosses the 4.8 m deck in under 2 s; after eject_boost_seconds the
    # command grows 0.6 (m/s)/s so locked brakes or a bent wheel only
    # delay the drop, capped far below anything that hurts a car.
    "eject_speed_mps": 2.6,
    "eject_speed_max_mps": 4.5,
    "eject_boost_seconds": 5.0,
    # Y-centering cap while ejecting: recenters toward the boarded y,
    # never yanks.
    "eject_y_vmax": 1.5,
    # Unstick hop. The 2026-08-13 live round proved a pure horizontal field
    # is not enough: velocity is injected into the body's node cluster, so
    # gripping tyres drag it back and the car "slides around and gets
    # stuck" (one logged run spent the whole 20 s timeout at x 15.03,
    # exactly where it parked). A 2.0 m/s vertical tap every 0.9 s lifts
    # the car ~0.20 m - wheels unloaded, lateral grip momentarily gone,
    # and the horizontal field gets a free stroke. Same primitive and same
    # size as the field knocker, which is proven.
    "eject_hop_dv_mps": 2.0,
    "eject_hop_interval_seconds": 0.9,
    # THE KICKER. Where the level deck meets the 40 deg chute there is a
    # CONVEX break no car's breakover angle can follow: a car creeping over
    # it grounds its belly on the lip and stops dead (the player's
    # screenshots, twice). Real pachinko fires the ball with a kicker, and
    # so does this: inside lip_kick_zone_m of the hinge the machine throws
    # ONE bounded impulse - 4.0 m/s inboard plus 2.6 m/s up, a 0.34 m hop
    # that carries the car over the break AIRBORNE instead of dragging it
    # across. Re-arms only after the car drifts back out of the zone, so a
    # car that fails to leave gets a fresh kick rather than a burst.
    "lip_kick_zone_m": 1.3,
    "lip_kick_x_mps": 4.0,
    "lip_kick_z_mps": 2.6,
    # The kicker RE-ARMS ON A TIMER, not on position. The first cut re-armed
    # only once the car had drifted 1.9 m back OUTBOARD of the lip zone -
    # motion nothing in the machine can produce, since the eject field
    # commands inboard for the whole phase - so a car that failed to clear
    # the break got exactly one kick and then nothing at all.
    "lip_kick_interval_seconds": 2.0,
    # Successive kicks climb the same 1.35 ladder as the field knocker. 1.6 x
    # the base 4.771 m/s impulse is 7.63 m/s, in the same bounded family as
    # rap_dv_max_mps and far below the ~19 m/s that shredded cars on the
    # centrifuge.
    "lip_kick_scale_max": 1.6,
    "release_timeout_seconds": 20.0,
    # Deck levelling rate on the way home. Was a bare 60.0 literal in the Lua.
    "tip_return_deg_per_second": 60.0,
    # How long the carriage waits at the crown for a car that is still standing
    # on it before coming home anyway. See updateReturning for why a car cannot
    # be carried DOWN on a snapshot-collision deck. Bounded on purpose: a wreck
    # must never pin the machine.
    "return_hold_seconds": 12.0,
    # ---- the fall ------------------------------------------------------
    "settle_speed_mps": 1.1,
    "settle_seconds": 0.8,
    # THE OUTER BACKSTOP ONLY, since 2026-08-14b. It used to be the machine's
    # ONLY answer to a hang, and that made a failed play 75 seconds of silence
    # followed by "HUNG ON THE BOARD" - measured live on 7 of 15 plays, and the
    # single worst thing this machine did to a player. The descent give-up
    # below now resolves a genuine hang in ~20 s; this only fires if a car is
    # somehow moving enough to dodge the give-up's stationary test forever.
    "fall_timeout_seconds": 75.0,
    # ---- the give-up ---------------------------------------------------
    # WHY THE MACHINE MUST BE ALLOWED TO CONCEDE. There is no torque
    # (probed live: identical yaw from a ref-node and a 2.71 m off-centre
    # impulse), so a car cradled on a peg cannot be rotated off it - only
    # walked. When walking is not working, no further raps will help, and
    # every extra second is a player watching nothing happen. A machine that
    # RECOGNISES it has lost and says so is better than one that stalls, and
    # this is the only fix in the file that improves every failure mode at
    # once, including the ones geometry cannot cure (the crown chute, the
    # divider horns).
    #
    # The test is DESCENT, not motion, for the same reason the spell reset is:
    # a rap is a 3+ m/s impulse, so a car that is going nowhere still "moves"
    # every 1.6 s. b.markZ already tracks the spell's descent datum, so the
    # give-up costs one comparison.
    #
    # 6 raps is deliberately past the top of the escalation ladder: the dv
    # sequence is 3.10 / 4.19 / 5.65 / 7.00 / 7.00 / 7.00, so a car that is
    # still there has taken three impulses at the cap and the ladder has
    # nothing left to offer. The check runs on the SEVENTH rap opportunity, so
    # rap 6 gets a full interval to work before the machine judges it.
    # Timing: rap_idle 2.2 + 7 x rap_interval 1.6 = 13.4 s after the car first
    # goes still, plus a 3-8 s fall, so a failed play resolves in ~17-21 s
    # against the old 75.
    "giveup_spell_raps": 6,
    # ---- the retract ladder (2026-08-14i) ------------------------------
    # Which rap of a stuck spell each tier of the retractable pin lands on.
    # See THE RETRACTABLE PIN in this file for the mechanism and the probe
    # that proved it, and the GE-half comment for why they sit here.
    #
    # Rap 1 is the knocker ALONE. That is not politeness: most stuck cars come
    # free on the first impulse, and a machine that dissolves its own board at
    # the first hesitation is not a pachinko machine. Only when the impulse
    # has been shown not to work does the pin start getting out of the way.
    #
    # All three land BELOW giveup_spell_raps (6), so the full-field retract
    # always gets two more rap intervals to resolve before the machine is
    # allowed to concede. The concede therefore stops being the normal end of
    # a bad play and becomes what it should always have been: the thing that
    # never happens.
    "retract_peg_raps": 2,
    "retract_row_raps": 3,
    "retract_all_raps": 4,
    # ---- F1: the bin band is a wedge BY DESIGN -------------------------
    # BIN_PITCH is 4.80 m, already under the 5.148 m car chord before the
    # horns lean, and the jackpot mouth is a 2.60 m near-parallel slot two
    # metres deep. NO bin mouth on this machine can clear a car chord, and
    # that is not a defect - catching the car is what a bin is FOR. The two
    # real defects were that the machine called it "HUNG ON THE BOARD - no
    # score" to a player watching their car sit square in the jackpot's
    # mouth, and that the peg-field rap rule LIFTED a bridged car off the
    # mouth it was straddling. In this band a bridged car needs SEATING, not
    # unseating: the "a downward rap cannot lift a car off what gravity holds
    # it on" reasoning is right in the peg field and exactly backwards here.
    "ridge_band_lo": round(RIDGE_Z - 1.0, 6),
    "ridge_band_hi": round(RIDGE_Z + 2.5, 6),
    # Seating rap: mostly DOWN, with enough lateral to walk the car toward
    # the centre of the mouth it is straddling.
    "seat_dir_x": 0.55,
    "seat_dir_z": -0.835,
    # A car conceded while straddling a named mouth is paid a stated fraction
    # of that bin. This does not reopen the old "paid the jackpot it was
    # blocking" defect, because the value is explicitly different and the
    # message says which bin and that it is a partial.
    "straddle_pay_fraction": 0.25,
    # THE definition of progress, and since F4 the ONLY one. Descend this far
    # and the stuck spell resets (fresh markZ, ladder back to 3.10, side and
    # regime re-chosen); fail to and the machine concedes. One number, so the
    # reset and the give-up cannot open a dead band between them.
    "giveup_descend_m": 0.5,
    # Anti-hang knocker. The two-peg BRIDGE this was written for no longer
    # exists: the 2026-08-14 lattice puts the crowns 7.60 m apart, past the
    # 5.148 m car chord, so no car can table across a neighbouring pair at any
    # attitude (assert_no_two_contact_rest). The knocker is kept as the
    # BACKSTOP for what geometry cannot rule out - a car hung on the crown
    # chute, planted between two divider horns, or resting on some pose the
    # rigid-body scan does not model (soft-body cradling in a peg's pressed-in
    # groove). The machine raps it loose the way a pachinko cabinet's
    # knocker does. The impulse is applied along a UNIT diagonal
    # (+/-0.7071, 0, +0.7071), so 3.1 m/s of delta-v is 2.19 m/s upward -
    # a 2.19^2 / (2 g) = 0.245 m hop, which is what actually unseats a car
    # resting on two pins - plus 2.19 m/s sideways to walk it off them. The
    # first cut pushed DOWN (z = -1) and could never lift anything; it also
    # scaled a non-unit vector, so its real magnitude was 2.51 and not the
    # 2.2 the comment claimed. Fires at most every 1.6 s, only while the car
    # is stationary above the bins.
    "rap_speed_mps": 0.55,
    "rap_idle_seconds": 2.2,
    "rap_interval_seconds": 1.6,
    "rap_dv_mps": 3.1,
    # Escalation for a genuine wedge (2026-08-13 live: a car planted
    # nose-down between two divider horns shrugged off 3.1 m/s raps). Each
    # successive rap in one stuck spell grows 35% until the cap; 5.5 is
    # still a jolt a parked car survives, far under the ~19 m/s injection
    # that shredded cars on the centrifuge. The counter resets the moment
    # the car actually moves, so a car that plinks free and re-wedges lower
    # starts gentle again.
    # 2026-08-14 live: 11 raps that never exceeded 4.2 m/s failed to free a
    # car wedged between peg rows 7 and 8 for the whole 75 s fall timeout.
    # 7.0 m/s along the unit diagonal is 4.95 m/s upward - a 1.25 m hop. That
    # no longer lifts a car over a whole peg (the section is 2.20 m across
    # since the 2026-08-14 lattice), and it is deliberately NOT being raised
    # to chase one: the hop was never how this worked. The rap direction is
    # lateral-dominant (rap_dir_x 0.94), so what the impulse actually buys is
    # WALK along the row, and 7.0 m/s is the largest jolt in the bounded family
    # this pack trusts - a third of the ~19 m/s injection that shredded cars on
    # the centrifuge. Geometry, not this number, is what clears the field.
    "rap_dv_max_mps": 7.0,
    # F4, THE DEAD BAND (2026-08-14c). There used to be TWO definitions of
    # progress: the spell reset at rap_descend_reset_m = 1.0 and the give-up
    # tested descent < giveup_descend_m = 0.5. Within one spell the descent is
    # confined to [0, 1.0) BY CONSTRUCTION, so a car that crept 0.5-1.0 m and
    # then jammed satisfied NEITHER test - the spell never reset, spellRaps
    # climbed forever at the capped 7.0 m/s, and the give-up could never fire.
    # That is the full 75 s stall the give-up exists to abolish, reachable by
    # exactly the centimetre-scale creeping the live logs are full of.
    #
    # There is now ONE number. giveup_descend_m is the definition of progress:
    # descend that far and the spell resets; fail to and the machine concedes.
    # rap_descend_reset_m is retired rather than left lying around at a second
    # value, because a spare threshold is how the dead band got built.
    # Peg-field rap direction, as a unit vector in (x, z). Lateral-dominant on
    # purpose. NOTE THE MODEL THIS WAS TUNED AGAINST IS NO LONGER THE SHIPPED
    # SHAPE: the argument was "a peg is a square bar on its corner, so its
    # flanks are 45 deg ramps that convert a sideways shove into lift for
    # free". The kite's upper flanks run 54.6 deg, which returns about 0.71x
    # the lift that argument assumes. The tune measures fine as it stands, but
    # anyone re-tuning it should start from 54.6 and not from 45. Lateral is
    # the ONLY axis that can walk a crosswise car out from between two pegs.
    # The old 0.7071/0.7071 diagonal spent half the impulse fighting gravity
    # directly and measured 1.0 m of hop for under 0.5 m of walk.
    "rap_dir_x": 0.94,
    "rap_dir_z": 0.34,
    # F5, THE CHUTE TEST (2026-08-14c). This used to be an x bound plus a
    # single z FLOOR, and the floor was catastrophically close to the top of
    # the peg field: chute_z_lo was APRON_Z_LO - 1.0 = 37.463 while the top
    # row's apex reached PEG_TOP_Z + PEG_R_Z_UP = 37.55 - the field poked
    # 0.09 m THROUGH the threshold. A car cradled on a row-0 peg outboard of
    # chute_x_lo therefore read as "on the chute" and was handed the
    # deliberately LIFT-FREE rap rule, whose entire justification is that the
    # 40 deg slab supplies the downhill - except there is no slab under a
    # row-0 peg, and the one impulse that could unseat the car was switched
    # off for the whole spell, because spellChute latches at spellRaps == 1.
    # A candidate cause of the very cradles the kite section was cut to fix.
    #
    # A HORIZONTAL PLANE CANNOT SEPARATE A SLOPED SLAB FROM A FIELD REACHING
    # UP UNDER IT. So the test is now the slab's own plane: the chute surface
    # at the car's x, which at x 11.40 sits at 42.99 against a row-0 rest near
    # 37.9 - five metres of separation instead of a 0.09 m inversion - and the
    # x window is closed at the top as well, since nothing outboard of the
    # hinge line is chute either.
    "chute_x_lo": APRON_X_LO,
    "apron_x_hi": APRON_X_HI,
    "apron_z_hi": APRON_Z_HI,
    "apron_tan": round(math.tan(math.radians(APRON_DEG)), 6),
    # ---- P0.4, THE CENSUS BOXES (2026-08-18) --------------------------
    # The eight-class census metric needs to answer "is the car resident
    # HERE" for several heres, and the file had no instrument that could.
    # `field_zone` reports CROSSINGS, not residents - :2149-2151 says so
    # outright ("already inside the box, generates no new crossing") - so no
    # arrangement of trigger zones can classify a car that has already
    # stopped. The only whole-volume test that existed was
    # fieldCloudOccupied, hard-wired to the peg field. cloudOccupied(state,
    # box) is that function generalised, and these are its boxes.
    #
    # A BOX MAY BE SHEARED ALONG X. `zslope`/`zx0` move both z limits with x:
    #     lo(px) = z0 + zslope * (px - zx0)
    #     hi(px) = z1 + zslope * (px - zx0)
    # The crown chute throat is the volume between a 40 deg slab and a hood
    # parallel to it, and an axis-aligned box over it necessarily swallows
    # the top peg row - which would report every row-0 drape as a throat jam
    # and hand the census a fabricated fault class. The shear is the same
    # correction F5 already made to the rap rule: A HORIZONTAL PLANE CANNOT
    # SEPARATE A SLOPED SLAB FROM A FIELD REACHING UP UNDER IT.
    #
    # THREE CLASSES HAVE NO BOX YET, AND THAT IS THE POINT. `held`,
    # `knife_hang` and `shaft_hang` are 役物 and 裏箱 classes; the geometry
    # arrives in Phase 2. They are declared in the class order NOW so that
    # Phase 2 supplies a box rather than re-specifying a metric, and a class
    # with no box simply never matches. Asserted below at exactly three.
    "census_boxes": {
        # The throat: between the chute slab and the hood, sheared with the
        # slab. z0/z1 are the slab surface and the hood underside at
        # x = apron_x_hi; both slide down-slope going inboard. 0.30 m of
        # deformation pad each way - a soft body pushes nodes through a
        # collision plane, and this is a sensor, not a collision test.
        "throat": {
            "x0": APRON_X_LO,
            "x1": APRON_X_HI,
            "y0": -DEPTH_HALF,
            "y1": DEPTH_HALF,
            "z0": APRON_Z_HI - 0.30,
            "z1": APRON_Z_HI + HOOD_CLEAR + 0.30,
            "zslope": round(math.tan(math.radians(APRON_DEG)), 6),
            "zx0": APRON_X_HI,
        },
        # The bin mouths. DERIVED as the band between the highest a scoring
        # car's ref node can sit (score_max_z) and the mouth plane itself
        # (RIDGE_Z), which is a geometric definition; the serial-78 census's
        # five concessions measured rest_z 3.17 to 4.73 (:186-189) and sit
        # inside it with margin at both ends, which is corroboration and not
        # the definition.
        "mouth": {
            "x0": -FIELD_HW,
            "x1": FIELD_HW,
            "y0": DIVIDER_Y_FRONT,
            "y1": DEPTH_HALF,
            "z0": BIN_FLOOR_Z + CAR_HEIGHT + 0.6,
            "z1": RIDGE_Z,
        },
        # The open field. The SAME box the peg guard and field_zone use, on
        # purpose: one question, three instruments, no drift.
        "field": {
            "x0": -FIELD_HW - 0.1,
            "x1": FIELD_HW + 0.1,
            "y0": -DEPTH_HALF - 0.1,
            "y1": DEPTH_HALF + 0.1,
            "z0": RIDGE_Z,
            "z1": WALL_TOP_Z,
        },
    },
    # The order the classifier tests boxes in, and it is data rather than
    # control flow so the class set can be read without reading Lua. The
    # first three have no box today (Phase 2 supplies them); `clean` and
    # `unclassified` are decided by outcome, not by geometry, and are not
    # in this list.
    "census_box_order": ["throat", "yakumono_held", "yakumono", "shaft", "mouth", "field"],
    # How far above the carriage plate a car still counts as settled ON it,
    # for a REPEAT kick's lift gate (kick 1 always lifts - see updateTipping),
    # and since 2026-08-14c for the unstick hop as well (F8).
    #
    # F7, SETTLED FROM THE LOGS RATHER THAN FROM MEMORY. Two comments in this
    # file used to disagree fourfold about a settled ref node's height - 0.22 m
    # in one place, "0.80-1.05 m measured over 28 kicks" in another - with this
    # 0.50 threshold sitting between them, so the term was either load-bearing
    # or dead and nobody could say which. It needed no test round to settle:
    # pachinko_kicked already logs z and the deck plane is a constant 44.00
    # through tipping. Over the 26 kicks in the build-35 run the heights are
    # BIMODAL with nothing whatsoever in between - 13 samples at 0.18-0.23 m
    # (settled) and 13 at 1.06-1.37 m (levitating). 0.50 sits in the empty gap
    # with better than 2x margin either side, so the gate is real, it is doing
    # its job, and the 0.22 comment was the correct one.
    # THE PLATE-CONTACT BAND (2026-08-14f). Used with the LOWEST-NODE gate
    # below, not the ref node. A seated car's lowest node sits ON the plate -
    # the crown probe measured 44.000 to the millimetre in every case,
    # tilted or not - so 0.15 m is generous contact and nothing else.
    "plate_contact_m": 0.15,
    "lip_kick_lift_max_m": 0.50,
    # ---- payout / reset ------------------------------------------------
    "score_hold_seconds": 4.5,
    "return_timeout_seconds": 40.0,
    # ---- payout marker (the scoreboard, as a machine) -------------------
    # A pointer carriage rides a rail across the bin fascia. It is the only
    # honest "scoreboard" a prop can have: textures cannot change at runtime,
    # so the readout is
    # a REAL part that drives to the bin the car actually landed in. While
    # the tower is idle it sweeps the fascia as an attract mode.
    "marker_travel": abs(BIN_CENTERS[0]),  # 9.60 - the outer bin centres
    # 9.0 m/s: crosses the full 19.2 m fascia in 2.1 s, so a payout reads as
    # a deliberate traverse rather than a snap, and it still tracks the idle
    # sweep whose peak rate is 9.60 * 0.62 = 5.95 m/s.
    "marker_speed_mps": 9.0,
    "marker_sweep_rate": 0.62,  # rad/s -> a 10.1 s round trip
    # F-2: THE READOUT MUST NEVER SIT STILL ON A VALUE IT DOES NOT MEAN. The
    # pointer used to park at bin centre 0.0 for the whole boarding-hoist-dock-
    # arming-fall stretch - 20-30 s, the majority of every play - and 0.0 IS the
    # JACKPOT tick, so the machine silently claimed a 10000 win on every play it
    # had not yet resolved. And a scoreless play parked at marker_null_x = 11.2,
    # which is INSIDE bin 4's plaque (8.00-11.20), so "no score" pointed at 400.
    # There is no cure by moving the constant: end posts at +/-12.4 and a 1.70 m
    # trolley cap the largest clean park at ~11.15, i.e. there is no position
    # past the last plaque. So the fix is a STATE THAT IS VISIBLY NOT A VALUE -
    # the pointer hunts, faster than the idle attract sweep so it reads as
    # working rather than resting. A moving pointer cannot be misread as a
    # claim, which is the only honest thing a one-axis readout can do.
    "marker_search_rate": 1.9,
    # Park position for a play that scored nothing: off the end of the value
    # scale, level with the gutter side of the board.
    # RETIRED by F-2 and kept only so the number is on the record: 11.2 is
    # INSIDE bin 4's plaque (8.00-11.20), so parking "no score" here pointed the
    # cone at 400. Nothing reads it now - a scoreless play hunts instead.
    "marker_null_x": FIELD_HW - 0.8,
}

# ---------------------------------------------------------------------------
# P0.4 - THE CENSUS METRIC. Eight classes, EXHAUSTIVE BY CONSTRUCTION.
# ---------------------------------------------------------------------------
# `raps == 0` no longer means what it meant, and the classes it is replaced by
# have to partition every play that ends. The set:
#
#   held         resident in the 役物 with 貯留 armed         NOT a fault - the game
#   field_hang   resident in the open field                    fault
#   mouth_hang   resident in a bin mouth (serial-78 signature) fault
#   shaft_hang   resident in the 裏箱                          fault, and new
#   throat_jam   resident in the crown chute throat            fault, and NOT in the field
#   knife_hang   resident in the 役物 with 貯留 spent          fault
#   clean        reached a bin, raps == 0, no concession       not a fault
#   unclassified anything else that stops                      FAULT BY CONSTRUCTION
#
# `unclassified` is the whole point of the redesign of this metric. The
# previous five-class set had a hole in the most expensive place - a car
# stopped on the 振り分け knife matched NO class, and that is the highest-value
# three seconds in the game - so the next hole must report itself as a fault
# instead of as silence.
#
# AND A NINTH OUTCOME THAT IS NOT A CLASS: `sensor_unknown`. See
# cloudOccupied's tri-state in the Lua. A play whose sensor could not read the
# roster is DROPPED FROM THE CENSUS - not counted clean, not counted a fault -
# because a classifier that guesses is a classifier that fabricates. It is
# emitted, and counted, so the drop rate itself is visible.
#
# WHERE THE CLASS IS DECIDED, and this is a deliberate departure from the
# literal wording of the spec that ordered the metric. The design says the
# class is decided "at concede/settle". Taken literally that puts a car which
# stopped on a peg, ate nine raps, came free and then landed in a bin into
# `unclassified` - it is not clean (raps > 0) and at rest it is resident
# nowhere. That is a real play, it is the exact failure the 70% baseline
# counts, and burying it in the catch-all would make the headline number both
# right and uninformative. So the class is latched AT THE FIRST RAP OF A PLAY
# - the moment the machine itself first decided the car had stopped - and the
# rest-time classification is the fallback for a play that ends without ever
# having been rapped. Same eight classes, same exhaustiveness; the box that
# names the fault is read where the fault actually happened.
CENSUS_CLASSES = [
    "held",
    "field_hang",
    "mouth_hang",
    "shaft_hang",
    "throat_jam",
    "knife_hang",
    "clean",
    "unclassified",
]
CENSUS_FAULT_CLASSES = [
    "field_hang",
    "mouth_hang",
    "shaft_hang",
    "throat_jam",
    "knife_hang",
    "unclassified",
]
CENSUS_SENSOR_UNKNOWN = "sensor_unknown"
assert len(CENSUS_CLASSES) == 8, "the census class set is not eight classes"
assert CENSUS_SENSOR_UNKNOWN not in CENSUS_CLASSES, (
    "sensor_unknown is not a class - it is the absence of a classification, "
    "and a play that gets it leaves the census entirely"
)
assert set(CENSUS_FAULT_CLASSES) == set(CENSUS_CLASSES) - {"held", "clean"}, (
    "the fault set and the class set have come apart: every class that is not "
    "`held` and not `clean` is a fault, including `unclassified`"
)
# Exactly three classes are declared with no box, and they are the three whose
# geometry Phase 2 builds. Asserted at three so that a fourth cannot be added
# silently - a class that can never match is a class that reports nothing.
_CENSUS_BOXED = set(BEHAVIOR["census_boxes"])
_CENSUS_ORDER = BEHAVIOR["census_box_order"]
_CENSUS_UNBUILT = [name for name in _CENSUS_ORDER if name not in _CENSUS_BOXED]
assert _CENSUS_UNBUILT == ["yakumono_held", "yakumono", "shaft"], (
    f"the unbuilt census boxes are {_CENSUS_UNBUILT}, not the three 役物/裏箱 "
    "classes Phase 2 supplies"
)
assert set(_CENSUS_BOXED) <= set(_CENSUS_ORDER), (
    "a census box exists that the classifier never tests"
)
for _box_name, _box in BEHAVIOR["census_boxes"].items():
    assert _box["x0"] < _box["x1"] and _box["y0"] < _box["y1"] and _box["z0"] < _box["z1"], (
        f"census box {_box_name!r} is degenerate or inverted: nothing will "
        "ever be resident in it and the class it feeds will read zero forever"
    )
# The throat box must not swallow the top peg row, or every row-0 drape gets
# reported as a throat jam. Checked at the row's crest, at every peg x the row
# actually has, wherever it overlaps the chute in x.
_THROAT = BEHAVIOR["census_boxes"]["throat"]
for _px in peg_row_xs(0) + [FIELD_HW]:
    if _THROAT["x0"] <= _px <= _THROAT["x1"]:
        _floor = _THROAT["z0"] + _THROAT["zslope"] * (_px - _THROAT["zx0"])
        _crest = PEG_TOP_Z + PEG_CROWN_MAX + (FIELD_HW - _px if _px >= FIELD_HW else 0.0)
        assert _crest < _floor, (
            f"the throat sensor's floor at x={_px:.2f} is z {_floor:.2f}, at or "
            f"below the top peg row's crest at {_crest:.2f}: a car draped on "
            "row 0 would be classified as a throat jam"
        )

# The servo has to be able to TRACK the carriage before it can correct height
# error on top of it, and the ease-out never commands more than the cruise
# speed, so this one assert covers the whole hoist command envelope.
assert BEHAVIOR["hoist_v_max"] > BEHAVIOR["hoist_speed_mps"], (
    f"hoist_v_max is {BEHAVIOR['hoist_v_max']} against a "
    f"{BEHAVIOR['hoist_speed_mps']} m/s cruise: the servo cannot even track "
    "the deck it is following"
)
assert BEHAVIOR["dock_seat_dv_mps"] <= BEHAVIOR["rap_dv_max_mps"], (
    "the dock seat impulse is bigger than the biggest impulse this machine "
    "allows itself anywhere else"
)
assert (
    BEHAVIOR["dock_seat_delay_seconds"] + 1.0 < BEHAVIOR["dock_settle_seconds"]
), (
    "the seat drop must land at least a second before the lowest-node scan at "
    "the end of the dock settle, or the scan captures a car mid-bounce"
)
assert BEHAVIOR["hoist_timeout_seconds"] > 4.0 * _HOIST_RIDE_S, (
    f"the hoist ride is now {_HOIST_RIDE_S:.2f} s and the watchdog is "
    f"{BEHAVIOR['hoist_timeout_seconds']} s: not enough margin to be a watchdog"
)

# The rack's last tooth IS the release angle; a drift between them would draw
# a pawl that never reaches the tooth the deck actually stops on.
assert BEHAVIOR["tip_full_deg"] == BEHAVIOR["tip_detents"][-1], (
    "tip_full_deg must equal the rack's final tooth angle"
)

# ---------------------------------------------------------------------------
# THE YOKOKU LIGHT RIG (round 6, 2026-08-14) - the fixtures.
#
# WHY THESE LIVE HERE AND NOT IN BEHAVIOR. Behaviour PARAMS reach the runtime
# through the handoff, which only the Blender stage rewrites; behaviour CODE
# ships fresh at build.py time (AGENTS.md, and it has half-shipped a build on
# this pack before). The light rig is ADDITIVE ART on a machine whose tuned
# table is frozen, so keeping every light constant out of BEHAVIOR means the
# fence proof is trivial - BEHAVIOR is byte-identical to serial 62's - and a
# lighting retune can never accidentally ship half a physics change. They are
# spliced into LUA_BEHAVIOR below rather than typed into it, because the tube
# coordinates are shared with the Blender generator (LAMP_TUBE_*).
#
# TWELVE lights, which is the centrifuge's own order of magnitude (11). Each is
# a real PointLight created in behavior.init at a FIXED prop-local position and
# stored in state.effects, so the framework's cleanupInstallation deletes it on
# every teardown path there is. A real light is the right night mechanism here
# whatever emissive does, because these twelve exist to ILLUMINATE the board and
# emissive self-glows without casting anything. (This comment used to justify
# them with "emissive maps are inert on this pipeline" - retired 2026-08-15, THE
# EMISSIVE VERDICT above. The justification changed; the rig did not.)
#
#   8 tube lights - four up each of the board's two lamp tubes. The tube
#       geometry is 37.4 m long, so one light per tube would be one pool and
#       35 m of dark lacquer; four per side at the quarter points is what makes
#       the run read as a SEGMENTED tube, and it is also what lets the rig say
#       "the carriage is here" and "the car is falling past here" in the only
#       axis this machine cares about.
#   1 head rail  - the rainbow rail across the top of the glass.
#   1 marquee    - stood 0.83 m OUT FRONT of the marquee's lit bars. A light at
#       a panel renders as a disc at any brightness (AGENTS.md); a light off
#       the panel washes it. Same reason the fascia pair stands off.
#   2 fascia     - the bin payout band, lit from the drive-out apron side.
# ---------------------------------------------------------------------------
_LAMP_TUBE_Z = [
    round(LAMP_TUBE_Z0 + (LAMP_TUBE_Z1 - LAMP_TUBE_Z0) * k / 3.0, 4) for k in range(4)
]

LIGHT_SPECS: list[dict] = []
for _side, _sx in (("l", -LAMP_TUBE_X), ("r", LAMP_TUBE_X)):
    for _k, _z in enumerate(_LAMP_TUBE_Z):
        LIGHT_SPECS.append({
            "slot": f"lamp_{_side}{_k}",
            "pos": [_sx, LAMP_TUBE_Y, _z],
            # radius has to cross the 24 m board or the far edge never sees the
            # tier colour at all; brightness is what stops it blowing out the
            # ivory field it stands 0.95 m in front of.
            "radius": 17.0,
            "brightness": 1.30,
            # Rainbow-chase phase. Runs up the left tube and down the right, so
            # the jackpot chase circles the glass instead of pulsing at it.
            "chase": round((_k / 8.0) if _side == "l" else (0.5 + _k / 8.0), 4),
        })
LIGHT_SPECS.append({
    "slot": "lamp_rail", "pos": [0.0, LAMP_TUBE_Y, LAMP_TUBE_Z1],
    "radius": 18.0, "brightness": 1.45, "chase": 0.4375,
})
LIGHT_SPECS.append({
    "slot": "lamp_marquee", "pos": [-1.0, LAMP_MARQUEE_Y, LAMP_MARQUEE_Z],
    # 26 m so the sign's far ends are still inside the falloff at 13.8 m, and
    # brightness down from serial 63's 1.55 now that it is a flood and not a
    # muzzle against the panel.
    "radius": 26.0, "brightness": 1.15, "chase": 0.9375,
})
for _index, _fx in enumerate((-6.0, 6.0)):
    LIGHT_SPECS.append({
        "slot": f"lamp_fascia_{_index}",
        "pos": [_fx, LAMP_FASCIA_Y, LAMP_FASCIA_Z],
        "radius": 13.0, "brightness": 1.60,
        "chase": 0.1875 + 0.5 * _index,
    })

assert len(LIGHT_SPECS) == 12, len(LIGHT_SPECS)
assert len({entry["slot"] for entry in LIGHT_SPECS}) == 12, "duplicate light slot"
# A light inside the drive volume would be invisible and pointless, but a light
# inside the FALL volume is worse: it would sit where a car can be. Every
# fixture is either outboard of the board face (y <= LAMP_TUBE_Y) or in front
# of the bin fascia, both of which are outside field_zone and catch_zone.
assert all(entry["pos"][1] <= LAMP_TUBE_Y + 1e-9 for entry in LIGHT_SPECS), (
    "a light strayed into the fall volume"
)


def _light_specs_lua() -> str:
    rows = []
    for entry in LIGHT_SPECS:
        # Round at the emitter: LAMP_TUBE_Z1 is 46.00 - 0.45 - 0.85, which is
        # 44.699999999999996 in binary float, and a lamp position printed to
        # 16 digits is noise in a file people read.
        x, y, z = (round(value, 4) + 0.0 for value in entry["pos"])
        rows.append(
            f'  {{slot = "{entry["slot"]}", pos = vec3({x}, {y}, {z}), z = {z}, '
            f'radius = {entry["radius"]}, brightness = {entry["brightness"]}, '
            f'chase = {entry["chase"]}}},'
        )
    return "\n".join(rows)


# ===========================================================================
# THE PHOTOMETRIC FIXTURE SCHEDULE (round 9, 2026-08-15). SI IN, ENGINE OUT.
#
# The commission asks for a modern parlour light show specified in real units -
# lumens for omnidirectional sources, candela for directional ones, nits for
# emissive surfaces - and explicitly rejects non-physical scalars. This engine
# can meet that natively, and this block is the ONE PLACE the SI values live.
# Everything downstream reads a converted number; nothing downstream retypes a
# photometric quantity.
#
# ---------------------------------------------------------------------------
# THE THREE MEASUREMENTS THIS BLOCK STANDS ON
# ---------------------------------------------------------------------------
#
# 1. THE CALIBRATION LAW (AGENTS.md, 3269 of 3269 shipped paired instances,
#    zero exceptions): 5000 cd == brightness 1.0. A SpotLight's `intensity` is
#    CANDELA, a PointLight's is LUMENS, and `intensityUnit` is PRESENTATIONAL -
#    spots tagged "lm" still store candela, so nothing here branches on it. The
#    conversion is applied by the two helpers below and nowhere else.
#
# 2. THE RUNTIME MATERIAL API - PROBED IN GAME 2026-08-15, and this is the
#    keystone the whole emissive half rests on. It had never been observed
#    working. It works, WITH A CONDITION:
#
#      scenetree.findObject(<materialName>)  returns class "material" carrying
#      setField / getField / postApply / preApply / reload / flush / save.
#
#      `mat:setField("emissiveIntensityNits", 0, v)` ALONE DOES NOT REACH THE
#      RENDERER. The field takes the value (getField reads it back) and the
#      pixel does not move: four cells told "60" kept their shipped ordering
#      exactly, +74 / +93 / +109 / +131 sRGB above the untouched 60-nit
#      reference cell in the SAME frame.
#
#      `mat:setField(...)` FOLLOWED BY `mat:postApply()` DOES. The same four
#      cells then read 84.0, 84.0, 84.0, 84.0 against the untouched 60-nit
#      reference cell's 84.0 - a deviation of 0.0 sRGB, five independent tiles,
#      one frame, one exposure. Eight cells shipped at 60/180/240/320/400/
#      550/800/1800 nit and all told "240" read 161.0 with a SPREAD OF 0.0, so
#      the runtime value REPLACES the authored one outright. `emissiveFactor`
#      drives the same way. The write SURVIVES a prop respawn, because a
#      material is a SCENE object and not a per-vehicle one.
#
#      METHOD NOTE, and it is the reason the first cut of the analysis got this
#      backwards: AUTO-EXPOSURE MOVES WITH TOTAL SCENE LUMINANCE, so no two
#      frames are comparable and the published night ladder cannot be used as a
#      cross-frame yardstick. Every number above is a WITHIN-FRAME comparison
#      against a cell that ships at the target value and is never written. The
#      proof that this matters is in the data: between the baseline and the
#      bare-setField frame the three UNTOUCHED cells moved +5.0, +4.0 and +5.0.
#
# 3. THE COST, MEASURED THE HARD WAY. `postApply()` is not free and it is not
#    close to free:
#
#      setField alone            0.55 - 2.7 us   per material
#      setField + postApply()    1462 - 4042 us  per material  (1.5 - 4.0 ms)
#
#    Three orders of magnitude apart. The first attempt to measure this asked
#    for 8,000 pairs in one queued chunk and TOOK THE ENGINE DOWN - the socket
#    dropped mid-chunk. So the ramp above is measured with a liveness check
#    between rungs, and the number is a design constraint, not trivia:
#    A MATERIAL CANNOT BE DRIVEN EVERY FRAME. One postApply is up to a quarter
#    of a 60 fps frame; ten would be two whole frames.
#
# ---------------------------------------------------------------------------
# THE ARCHITECTURAL SPLIT THAT MEASUREMENT FORCES
# ---------------------------------------------------------------------------
#
# The twelve PointLights already on this machine write `color` and `brightness`
# with setField and NO postApply, and they have photographed correctly across
# five rounds of captures. Materials need the flush; lights do not. So the two
# mechanisms have opposite cost profiles, and the show is split along that line
# rather than along any aesthetic one:
#
#   LIGHTS  (free, ~1 us)   -> everything INSTANTANEOUS and WHOLE-MACHINE: the
#                              impact-frame strobe, the fever burst, the tier
#                              colour, the fall tracking. Per frame, no budget.
#   SURFACES (1.5-4 ms)     -> everything STRUCTURAL and PER-PANEL: which of
#                              the thirteen sign faces is lit, how bright the
#                              marquee is for this time of day, the chase step.
#                              EVENT-RATE, hard-budgeted, round-robin.
#
# A chase is not a per-frame quantity. It is a low-rate discrete event stream:
# thirteen panels stepping at 2 Hz is 26 writes a second, which at the measured
# 1.5 ms is 3.9% of one core. It is affordable precisely because it is not
# animated continuously, and the writer below enforces that.
# ---------------------------------------------------------------------------

# --- the conversion boundary. Applied here; never applied twice. -----------
CANDELA_PER_BRIGHTNESS = 5000.0                       # measured, 3269/3269
LUMENS_PER_BRIGHTNESS = 4.0 * math.pi * CANDELA_PER_BRIGHTNESS   # 62831.853


def spot_brightness(candela: float) -> float:
    """SpotLight: `intensity` is candela. brightness = cd / 5000."""
    return round(candela / CANDELA_PER_BRIGHTNESS, 4)


def point_brightness(lumens: float) -> float:
    """PointLight: `intensity` is lumens. brightness = lm / (4*pi*5000)."""
    return round(lumens / LUMENS_PER_BRIGHTNESS, 4)


# ---------------------------------------------------------------------------
# THE SCALE RECONCILIATION, stated once, applied in one place, and NOT
# over-claimed. The commission's figures are authored for a real parlour
# cabinet. A Japanese pachinko machine's outer frame is ~0.52 m wide; this
# cabinet is 25.40 m across. k = 48.8.
#
# LUMINANCE IS SCALE INVARIANT. A surface emitting 1800 cd/m^2 looks exactly as
# bright whether it is 0.4 m across or 20 m across - nits are per unit area on
# both sides of the ratio. So EVERY ONE OF THE OWNER'S NITS TARGETS TRANSFERS
# TO THIS PROP UNCHANGED, and the emissive half of this schedule carries no
# fudge factor at all. That is not a convenience; it is the reason the emissive
# half is the rigorous half.
#
# INTENSITY AND FLUX ARE NOT. Hold a fixture's aim and multiply its distance by
# k and the illuminance falls as k^-2.
#
#   DIRECTIONAL FIXTURES SHIP AS AUTHORED. A SpotLight's candela is already a
#   beam-axis figure and the owner's numbers land in range under the
#   calibration law: 8500 cd -> brightness 1.70, 1200 cd -> 0.24. No scaling is
#   applied to them and none is needed.
#
#   THE OMNIDIRECTIONAL FILL IS ANCHORED, AND THE ANCHOR IS NAMED. A free-field
#   k^2 argument would demand 650 lm * 2384 = 1.55 Mlm, brightness 24.7, four
#   times past this rig's own 6.0 ceiling. THAT NUMBER IS NOT PUBLISHED HERE AS
#   IF IT WERE DERIVED, because BeamNG's PointLight is not a free-field
#   inverse-square source - it carries a hard `radius` cutoff and an
#   `attenuationRatio`, and NOTHING IN THIS REPOSITORY MEASURES THAT FALLOFF.
#   What is measured is this prop's own marquee flood: brightness 1.15,
#   photographed and accepted across four rounds. That is the anchor, and the
#   factor it implies is written down rather than hidden inside a literal.
CABINET_W = 2.0 * (FIELD_HW + WALL_T)                 # 25.40 m
PARLOUR_CABINET_W = 0.52                              # a real machine's frame
PROP_SCALE = round(CABINET_W / PARLOUR_CABINET_W, 2)  # 48.85

_MARQUEE_FLOOD_ANCHOR_LM = 1.15 * LUMENS_PER_BRIGHTNESS   # 72,256.6 lm
FILL_SCALE = round(_MARQUEE_FLOOD_ANCHOR_LM / 650.0, 1)   # 111.2, NOT k^2

# ---------------------------------------------------------------------------
# THE DAY/NIGHT BAND, and why a static nits value is not an option.
#
# MEASURED (AGENTS.md round 17): the usable NIGHT band is ~60-400 nit, with
# saturation beginning somewhere in the open interval (400, 550] and the floor
# unmeasured below 60. The usable NOON band is ~1500-15000. THEY DO NOT
# OVERLAP. There is no single number that works at both times, so nits is
# driven from Lua against time of day - which is exactly what the keystone
# probe above licenses.
#
# The night targets are not invented, they are the day targets mapped by ONE
# named ratio, chosen so the BRIGHTEST surface on the machine lands on the
# 320-nit rung. 400 nit is measured unsaturated (22,470 of 22,470 subpixels at
# exactly 254, none at 255) but it is the last rung before an interval nobody
# has measured, and a show should not live on the edge of an unmeasured
# interval.
DAY_BAND = (1500.0, 15000.0)
NIGHT_BAND = (60.0, 400.0)
NIGHT_PEAK_NITS = 320.0
_BRIGHTEST_DAY_NITS = 3500.0                          # the playfield edge LEDs
# Held EXACT rather than rounded: rounding it to 4 places put the brightest
# surface at 319.9 instead of the 320.0 rung it is defined to sit on, and a
# schedule whose own anchor misses by 0.1 nit invites the reader to wonder what
# else drifted. The displayed value is 0.0914; the arithmetic uses the ratio.
NIGHT_RATIO = NIGHT_PEAK_NITS / _BRIGHTEST_DAY_NITS              # 0.0914...


def night_nits(day: float) -> float:
    """Map a daylight nits target into the measured night band.

    Clamped at both ends: nothing is allowed above NIGHT_PEAK_NITS (headroom
    against the unmeasured (400, 550] interval) and nothing below the lowest
    rung anyone has actually read.
    """
    return round(min(NIGHT_PEAK_NITS, max(NIGHT_BAND[0], day * NIGHT_RATIO)), 1)


# ---------------------------------------------------------------------------
# THE FIXTURE SCHEDULE. Six classes, the commission's own, each carrying its SI
# target, the mechanism that realises it, and the engine value that mechanism
# needs. Read the `engine` column as DERIVED - every one of them is a call to
# one of the two converters above or to night_nits().
#
#  class                SI target                     mechanism
#  -------------------  ----------------------------  ---------------------
#  1 marquee            1800 nit + 650 lm @ 6500 K    emissive + PointLight
#  2 playfield edge     3500 nit (wide gamut)         emissive
#  3 centre strobes     8500 cd, 25/45 deg, 5500 K    SpotLight
#  4 peg spotlights     1200 cd @ 4000 K              SpotLight
#  5 sub-panel bezel    180 lm @ 3000 K               PointLight
#  6 LCD/matrix gasket  1200 nit                      emissive
#  7 letter flood       5500 cd, 24/42 deg, 3200 K    SpotLight
#  8 letter plate       1200 nit (reverse-printed)    emissive + flood
#
# COLOUR TEMPERATURE IS A REAL FIELD AND IS USED AS ONE. `useColorTemperature`
# + `colorTemperatureKelvin` are in the shipped field census, so the Kelvin
# targets are set as Kelvin rather than hand-mixed into an RGB triple. The tier
# ladder still drives `color` for the SHOW colours; correlated colour
# temperature is the fixture's own white point underneath it.
FIXTURE_CLASSES: dict[str, dict] = {
    "marquee": {
        "si": "1800 nit emissive + 650 lm fill @ 6500 K",
        "day_nits": 1800.0,
        "fill_lumens": 650.0 * FILL_SCALE,
        "kelvin": 6500,
    },
    "playfield_edge": {
        "si": "3500 nit emissive, wide gamut",
        "day_nits": 3500.0,
        "kelvin": 6500,
    },
    "centre_strobe": {
        "si": "8500 cd, 25 deg inner / 45 deg outer, 5500 K",
        "candela": 8500.0,
        "inner_deg": 25.0,
        "outer_deg": 45.0,
        "kelvin": 5500,
    },
    "peg_spot": {
        "si": "1200 cd @ 4000 K",
        "candela": 1200.0,
        "inner_deg": 30.0,
        "outer_deg": 55.0,
        "kelvin": 4000,
    },
    # ROUND 2. One flood per letter plate, on a bracket outboard of the shaft.
    # THIS IS WHERE THE CHASE LIVES NOW. A driven SURFACE costs 1.5-4.0 ms a
    # write (measured) and can be refreshed at 7.5 Hz in the worst case; a
    # light costs a setField and can be refreshed every frame. A chase is a
    # high-rate signal, so it belongs on the cheap fixture, and a lit sign
    # whose letters run is lit by BULBS in front of the plates in any case -
    # the plate itself just glows.
    # 150 cd, AND IT IS THE FIRST NUMBER HERE THAT WAS EVER CHOSEN ON THE
    # LEGIBILITY AXIS. Every earlier value on this line was picked by watching
    # MEAN PLATE LUMINANCE - 2600 cd moved it 6-7% ("a shimmer"), 9000 cd moved
    # it 30-85% but clipped 33-37% of the head plate, and 5500 was called the
    # midpoint. It was not a midpoint. 36.3% clip at 5500 against 37.4% at 9000
    # is the SAME SATURATION PLATEAU, and mean luminance is exactly the
    # quantity that rises as a letter is erased, so the axis could not tell the
    # difference. Measured against Michelson contrast INSIDE the plate face
    # instead, at three levels (attract 0.80, fever 1.00, and the impact
    # strobe's 2.20), on the reverse-printed artwork, at midnight:
    #
    #     cd     Michelson(worst)   clipped(fever)   plate mean   decodes as
    #      0          0.92               0.0%            32       PACHINKO
    #    150          0.60               9.4%            66       PACHINKO
    #    300          0.54              21.9%            84       PACHINKO
    #    450          0.52              24.6%            98       PACHINKO
    #    650          0.50              29.4%           112       PACHINKO
    #    900          0.50              31.4%           124       PACHINKO
    #   1400          0.50 (0.495)      34.2%           140       PACHI.K.
    #   5500          0.49              44.5%           176       ........
    #
    # READ THE 0 cd ROW FIRST. With the plates reverse-printed the sign is
    # ALREADY a well-exposed, perfectly legible sign with NOTHING shining on
    # it: contrast 0.92, not one clipped pixel, type at sRGB 123 on a field at
    # 5. That is the fact that resets this number by a factor of 37. A flood
    # sized to move a surface already sitting at sRGB 220 has to be enormous; a
    # flood sized to HIGHLIGHT a surface sitting at 32 does not. 150 cd doubles
    # the plate's luminance - a 2x chase, where round 2 called 30-85% "a
    # chase" - and it is the largest rung that still clips under 10% at fever
    # and holds Michelson above 0.60 under the impact strobe.
    #
    # The 24/42 degree cone is kept: it is what keeps the pool off the
    # neighbour 1.5 m away, and at this candela it also stops flooding the
    # shaft structure behind the plates, which at 5500 cd was rendering a blown
    # cream ellipse wider than the plate itself.
    "letter_flood": {
        "si": "150 cd, 24 deg inner / 42 deg outer, 3200 K",
        "candela": 150.0,
        "inner_deg": 24.0,
        "outer_deg": 42.0,
        "kelvin": 3200,
    },
    # ROUND 3. The eight P-A-C-H-I-N-K-O plates, split off `marquee` because
    # they are the only lit surface on this machine that is ALSO floodlit.
    # The marquee band carries a 650 lm fill; a letter plate carries a
    # dedicated flood as well. The 1200-nit rung was chosen for that reason
    # and then CONFIRMED photographically: with the flood switched off
    # entirely, a 1200-nit reverse-printed plate photographs at midnight
    # with its type at sRGB 123 on a field at 5, Michelson 0.92 and NOT ONE
    # CLIPPED PIXEL. The plate's own glow is a finished sign; the flood is
    # a highlight on top of it, which is why the flood is now 150 cd.
    "letter_plate": {
        "si": "1200 nit emissive, reverse-printed, + 150 cd flood",
        "day_nits": float(LETTER_PLATE_DAY_NITS),
        "kelvin": 6500,
    },
    "bezel": {
        "si": "180 lm @ 3000 K",
        "lumens": 180.0 * FILL_SCALE,
        "kelvin": 3000,
    },
    "gasket": {
        "si": "1200 nit emissive",
        "day_nits": 1200.0,
        "kelvin": 6500,
    },
}

# Every class that emits a surface gets both bands computed HERE, so no Lua
# ever sees a magic number and no reader has to trust that 165 came from 1800.
for _name, _entry in FIXTURE_CLASSES.items():
    if "day_nits" in _entry:
        _entry["night_nits"] = night_nits(_entry["day_nits"])
    if "candela" in _entry:
        _entry["brightness"] = spot_brightness(_entry["candela"])
    for _key in ("lumens", "fill_lumens"):
        if _key in _entry:
            _entry["brightness"] = point_brightness(_entry[_key])

assert FIXTURE_CLASSES["centre_strobe"]["brightness"] == 1.7, "8500 cd must be 1.70"
assert FIXTURE_CLASSES["peg_spot"]["brightness"] == 0.24, "1200 cd must be 0.24"
assert FIXTURE_CLASSES["playfield_edge"]["night_nits"] == NIGHT_PEAK_NITS
assert all(
    NIGHT_BAND[0] <= entry["night_nits"] <= NIGHT_PEAK_NITS
    for entry in FIXTURE_CLASSES.values() if "night_nits" in entry
), "a surface was scheduled outside the MEASURED night band"
assert all(
    DAY_BAND[0] * 0.7 <= entry["day_nits"] <= DAY_BAND[1]
    for entry in FIXTURE_CLASSES.values() if "day_nits" in entry
), "a surface was scheduled outside the measured day band"


# ---------------------------------------------------------------------------
# THE EMISSIVE SURFACE SET. Thirteen sign faces plus the two lamp runs.
#
# THIS COSTS NO GEOMETRY AND NO BLENDER ROUND, which is the whole reason it is
# affordable in one pass. The `marquee` texture family ALREADY returns a fifth
# (emissive) channel and texture_kit ALREADY writes it as `<base>_glow.color.png`
# under the cookable-suffix law - fifteen of them are on disk right now. They
# were being DROPPED by prop_builder's dead-emissive path for one reason only:
# no palette entry declared an `emissive`. Declaring it is the entire change.
#
# And the family draws them the right way round for a backlit sign. NOT the way
# this comment said for two rounds: it claimed the lettered branch writes
# `emissive = 1.0 - mask`, which would force every glyph to zero. That WAS the
# code and it was the inverted-sign defect; texture_kit._marquee_glow was
# corrected in round 2 to `albedo x transmission(albedo) x backlight`, so every
# texel now emits its OWN colour and its day polarity survives the night. A
# plate with cream type on a red field stays cream-on-red after dark, which is
# what a real parlour marquee does. The corollary is the round-3 blocker: with
# the polarity preserved, a WHITE-field plate emits nearly all of its nits
# through the field, and a field with no headroom cannot carry a chase.
#
# THE CHASE LIVES IN THE EIGHT LETTER PLATES. P-A-C-H-I-N-K-O are eight
# SEPARATE materials on eight separate plates stacked up the outboard shaft
# face. Driving their nits out of phase is a real chase running 37 m up the
# tower, and it needs no scrolling UV, no animFlags and no new mesh - only
# eight cheap, quantised, budgeted writes. The five bin plates are a second,
# horizontal run across the payout fascia.
#
# `chase` is the phase offset around one cycle, 0..1. The letters run bottom to
# top so the machine reads as filling up; the bin plates sweep centre-outward
# from the jackpot, which is the plate the machine cares about.
EMISSIVE_LETTERS = 8
EMISSIVE_BINS = BIN_COUNT

EMISSIVE_SPECS: list[dict] = []
for _k in range(EMISSIVE_LETTERS):
    EMISSIVE_SPECS.append({
        "slot": f"sign_letter_{_k}",
        "material": f"{MOD_ID}_sign_letter_{_k}",
        "cls": "letter_plate",
        "chase": round(_k / EMISSIVE_LETTERS, 4),
    })
for _k in range(EMISSIVE_BINS):
    # CONVERGES INWARD ONTO THE JACKPOT, and round 1's spec said the opposite.
    # |k - 2| is the distance from bin 2, and a phase that GROWS with distance
    # arrives later the further out you are - so the wave starts at the rim and
    # closes on the middle. That is the right gesture for a jackpot (it is the
    # machine pointing at where the money is), which is why the offsets are
    # kept and the sentence is the thing that was wrong.
    EMISSIVE_SPECS.append({
        "slot": f"sign_bin_{_k}",
        "material": f"{MOD_ID}_sign_bin_{_k}",
        "cls": "gasket",
        "chase": round(abs(_k - (EMISSIVE_BINS - 1) / 2.0) / EMISSIVE_BINS, 4),
    })
EMISSIVE_SPECS.append({
    "slot": "sign_title", "material": f"{MOD_ID}_sign_title",
    "cls": "marquee", "chase": 0.0,
})
# NOT `lamp_*`. The twelve PointLights already own that prefix and the file
# asserts on their count; a driven SURFACE and the LAMP standing in front of it
# are different fixtures and must not share a namespace. `tube_` is the
# geometry these materials are actually on.
EMISSIVE_SPECS.append({
    "slot": "tube_warm", "material": f"{MOD_ID}_lamp_warm",
    "cls": "playfield_edge", "chase": 0.25,
})
EMISSIVE_SPECS.append({
    "slot": "tube_rainbow", "material": f"{MOD_ID}_lamp_rainbow",
    "cls": "playfield_edge", "chase": 0.75,
})

assert len(EMISSIVE_SPECS) == EMISSIVE_LETTERS + EMISSIVE_BINS + 3
assert len({e["slot"] for e in EMISSIVE_SPECS}) == len(EMISSIVE_SPECS)
assert all(e["cls"] in FIXTURE_CLASSES for e in EMISSIVE_SPECS)

# ===========================================================================
# THE WRITE BUDGET, AND THE ARCHITECTURE IT ACTUALLY FORCES.
#
# ROUND 1 GOT THIS BADLY WRONG AND THE ERROR IS WORTH KEEPING ON THE RECORD.
# The justification said "thirteen panels stepping at 2 Hz is 26 writes a
# second, which at the measured 1.5 ms is 3.9% of one core". The SHIPPED system
# was nothing like that. Every surface ran the mode's own chase wave, so at
# 132 BPM with chaseBeats 1.0 (reach) and 0.5 (fever) the sixteen surfaces
# between them demanded 800-950 quantiser crossings a second against a cap of
# EMISSIVE_WRITE_BUDGET x 60 = 120. Simulated frame by frame at 60 fps the cap
# was SPENT IN FULL ON 100% OF FRAMES in play, reach and fever - 3.0-8.0 ms of
# main thread, permanently, on a 16.7 ms budget, for one prop's sign lighting.
#
# It was also, at that rate, not even a chase. A saturated budget pins each of
# the sixteen surfaces to 120/16 = 7.5 Hz while the waveform runs at 2.2 Hz
# (reach) and 4.4 Hz (fever): Nyquist ratios of 1.7 and 0.85, the second of
# them below Nyquist outright. Simulated over 12 s the displayed peak letter
# matched the intended peak on 28% of frames in reach and 13% in fever, and
# jumped to a NON-ADJACENT plate 94 and 131 times. The two modes the whole show
# builds toward were the two that could not render as a travelling wave, and
# they were also the two nobody had photographed.
#
# THE FIX IS NOT A SMALLER NUMBER, IT IS THE DESIGN THE MEASUREMENT ALWAYS
# IMPLIED. A surface write costs 1.5-4.0 ms; a light write costs a setField.
# Three orders of magnitude apart is not a tuning problem, it is a decision
# about what each fixture is FOR:
#
#   * SURFACES CARRY STRUCTURAL STATE. Which mode the machine is in, and what
#     time of day it is. A plateau, plus one slow common breathe so the sign
#     is alive rather than static. Low rate by construction.
#   * LIGHTS CARRY EVERY INSTANTANEOUS GESTURE. The travelling chase, the
#     impact strobe, the fever gate. Free, and frame-accurate.
#
# So the chase left the surfaces, and eight LETTER FLOODS were added (one per
# plate) so the letters still run - on a fixture that can actually do it.
#
# WHAT THAT COSTS, ARITHMETIC RATHER THAN HOPE. A surface's target is
# nominal x level x gain x weight with weight in [1 - surfaceDepth, 1], so in
# quantiser units it sweeps level x gain x EMISSIVE_QUANT_STEPS x surfaceDepth
# steps, and a cosine crosses each step twice a cycle:
#
#     writes/s = 2 x EMISSIVE_QUANT_STEPS x level x gain x surfaceDepth
#                  x SURFACE_BREATHE_HZ x <surfaces>
#
# evaluated per mode in EMISSIVE_WRITE_DEMAND below and ASSERTED against the
# cap with margin. The worst mode comes out near 33 writes a second - which is
# finally the number round 1's justification claimed, now that the system
# underneath it is the one being described.
# ===========================================================================
EMISSIVE_WRITE_BUDGET = 2
# Quantisation, same discipline as the light rig's 1/40. A surface is only
# rewritten when its target crosses a step, so a smooth breathe does not
# generate a write per frame. 24 steps over the night band is 14 nit a step,
# which is under one sRGB code at the measured night slope.
EMISSIVE_QUANT_STEPS = 24
# THE BREATHE, and why it is this slow. The guaranteed worst-case refresh of
# ONE surface is the whole cap shared out: 120 writes/s / 16 surfaces =
# 7.5 Hz. A waveform on a surface must therefore be far below 7.5/2 Hz, not
# near it - round 1 ran 2.2 and 4.4 Hz there. 0.125 Hz is an 8 s swell, a
# Nyquist ratio of 30 against the WORST case and effectively unquantised in
# the normal one, and it is what a big lit sign does anyway. It is ALSO the
# lever that sets the cost - write demand is exactly linear in it - and 8 s is
# what brings the worst mode under a tenth of a frame at the worst measured
# per-write cost rather than under a tenth at the best one.
SURFACE_BREATHE_HZ = 0.125
# How far a letter flood drops between passes. Near-total, because the plate
# it is on never goes dark - the surface keeps its structural glow - so this
# is the contrast between "lit plate" and "lit plate with the chase head on
# it", not between light and dark.
LETTER_CHASE_DEPTH = 0.88
# The measured postApply cost, kept here as data because two separate pieces
# of arithmetic below and one telemetry assert all reference it.
EMISSIVE_WRITE_MS = (1.5, 4.0)
FRAME_MS_AT_60 = 1000.0 / 60.0

# ---------------------------------------------------------------------------
# THE FOUR MODES, in Python, because three separate pieces of arithmetic below
# depend on them and the Lua table is spliced from this one. `depth` is the
# LIGHT depth (free, fast); `surfaceDepth` is what a driven material is allowed
# to move by, and it is small on purpose - see the budget note above.
# ---------------------------------------------------------------------------
SHOW_MODES: dict[str, dict[str, float]] = {
    "attract": {"level": 0.80, "chaseBeats": 8.0, "depth": 0.35,
                "gain": 1.00, "surfaceDepth": 0.06},
    "play":    {"level": 0.90, "chaseBeats": 4.0, "depth": 0.38,
                "gain": 1.10, "surfaceDepth": 0.08},
    "reach":   {"level": 0.97, "chaseBeats": 1.0, "depth": 0.80,
                "gain": 1.25, "surfaceDepth": 0.10},
    "fever":   {"level": 1.00, "chaseBeats": 0.5, "depth": 1.00,
                "gain": 1.45, "surfaceDepth": 0.12},
}

# The floors. Round 1 hard-asserted that every surface's AUTHORED nominal sat
# in the measured 60-320 nit night band and then multiplied it at runtime by
# level x weight x gain and clamped only the TOP, so the assert described a
# number the renderer never saw: simulated night troughs were 57.0 in attract,
# 26.6 in reach and 1.0 in fever, and the quantiser wrote a literal 0.0 because
# `q` floored to zero underneath the `nits < 1 -> 1` clamp. Both ends are
# clamped now, the quantiser cannot floor to zero, and - more to the point -
# EMISSIVE_RUNTIME_BAND below asserts the band at the value that is WRITTEN, so
# the floor is a guard that never has to shape anything.
EMISSIVE_NIGHT_FLOOR = NIGHT_BAND[0]          # 60.0, the lowest measured rung
EMISSIVE_DAY_FLOOR = round(DAY_BAND[0] * 0.5, 1)   # 750.0


def emissive_write_demand() -> dict[str, float]:
    """Writes per second the driven surfaces ASK FOR from the BREATHE, per mode.

    The cap is EMISSIVE_WRITE_BUDGET x 60. Round 1's shipped system asked for
    62 / 159 / 801-827 / 909-944 against that cap of 120 and therefore ran
    pinned to it on 100% of frames in three of the four modes.

    SCOPE, STATED because round 2 left it unstated and a code audit caught it:
    this is the breathe term ONLY. It is a claim about a world with a FROZEN
    time of day, which is the world every capture so far has been taken in
    (the harness sets `core_environment.setTimeOfDay({time=0.5, play=false})`).
    A MOVING sun is a second, independent source of demand and it is modelled
    separately in emissive_tod_demand() below. Total demand is the sum.
    """

    surfaces = len(EMISSIVE_SPECS)
    out = {}
    for name, params in SHOW_MODES.items():
        out[name] = round(
            2.0 * EMISSIVE_QUANT_STEPS * params["level"] * params["gain"]
            * params["surfaceDepth"] * SURFACE_BREATHE_HZ * surfaces, 1)
    return out


# The peak rate at which a raised-cosine day, put through the runtime's own
# smoothstep, moves `blend`. d(blend)/dt = 6f(1-f) x |df/dt| and with
# f = 0.5 + 0.5 cos(2*pi*t) that is 1.5*pi*|sin|^3 per unit time-of-day, so the
# peak is 1.5*pi and it happens at f = 0.5 - exactly the regime boundary, which
# is why the model below prices the step at the NIGHT (smaller) one.
TOD_BLEND_PEAK_SLEW = round(1.5 * math.pi, 4)


def emissive_tod_demand(day_length_s: float) -> float:
    """Writes per second the driven surfaces ask for from a MOVING SUN.

    THE DEFECT THIS MODELS, and it is a real one that five rounds of capture
    could not have seen. Round 2 fixed a stranding bug by caching the WRITTEN
    STRING rather than the quantiser index. Correct - but the index was
    scale-invariant, and losing that invariance meant that while `nominal`
    moved with the sun, `q * step` moved with it too, at %.1f resolution, on
    EVERY surface on EVERY frame. Demand across a dawn was unbounded in the
    model and pinned at 2 writes/frame in the engine.

    The runtime now bands against the REGIME nominal, which is constant inside
    a regime, so a surface is only rewritten when its target genuinely crosses
    a step. What is left is this, and it is bounded:

        writes/s = sum over surfaces of  d(nits)/dt / step

    with d(nits)/dt = (day - night) x level x gain x d(blend)/dt and
    step = night_nominal / EMISSIVE_QUANT_STEPS. The (day - night) / night
    ratio is ~9.94 for every class on this machine (NIGHT_RATIO is a constant
    and playfield_edge's night value clamps to the same place), so the total is
    very nearly 16 surfaces x 24 steps x 9.94 x 1.45 x 1.5*pi / day_length.

    It is priced at FEVER (level x gain = 1.45), which is the worst mode, and
    at the peak slew, which lasts a moment rather than a dawn. Both are
    deliberate: this is a ceiling, not an average.
    """

    if day_length_s <= 0.0:
        raise ValueError("day_length_s must be positive")
    worst = max(p["level"] * p["gain"] for p in SHOW_MODES.values())
    total = 0.0
    for entry in EMISSIVE_SPECS:
        cls = FIXTURE_CLASSES[entry["cls"]]
        night = cls["night_nits"]
        step = night / EMISSIVE_QUANT_STEPS
        total += (cls["day_nits"] - night) * worst * (
            TOD_BLEND_PEAK_SLEW / day_length_s) / step
    return round(total, 2)


def emissive_min_day_seconds(fraction_of_cap: float = 0.5) -> float:
    """The shortest day length that keeps the sun's own demand inside a given
    fraction of the write cap. Inverts emissive_tod_demand(), which is exactly
    proportional to 1 / day_length."""

    at_one = emissive_tod_demand(1.0)
    return round(at_one / (EMISSIVE_WRITE_BUDGET * 60.0 * fraction_of_cap), 1)


def emissive_runtime_band(night: bool) -> dict[str, dict[str, tuple[float, float]]]:
    """The nits actually WRITTEN, per fixture class, PER MODE.

    THIS FUNCTION USED TO LIE, in two ways that a code audit caught and that
    are both fixed here.

      * Its docstring said "the nits actually WRITTEN" and it modelled neither
        the runtime's floor/ceiling clamp nor its quantiser. It returned the
        continuous, unclamped, unquantised TARGET, which can sit up to half a
        step from what the renderer is given. The file's own capture proved the
        gap: the measured midnight marquee value is 123.5 and the old bound
        recomputed to 123.8. Nil impact at a ~2x margin to the floor, and still
        the wrong number under the right label.
      * It collapsed the mode axis with min/max before returning, so a failing
        assert could name the class but not the mode.

    It is now a transcription of Emissive.update's arithmetic in the same
    order: nominal -> level x weight x gain -> clamp -> quantise -> the value
    the string is formatted from. The breathe is sampled at its two extremes,
    which is where the band's edges are.
    """

    # The same two constants the Lua receives as EMISSIVE_NIGHT_PEAK /
    # EMISSIVE_DAY_PEAK - spliced from here, so there is one source.
    ceiling = NIGHT_PEAK_NITS if night else DAY_BAND[1]
    floor = EMISSIVE_NIGHT_FLOOR if night else EMISSIVE_DAY_FLOOR
    out: dict[str, dict[str, tuple[float, float]]] = {}
    for cls_name, cls in FIXTURE_CLASSES.items():
        if "night_nits" not in cls:
            continue
        nominal = cls["night_nits"] if night else cls["day_nits"]
        # THE SPAN IS THE REGIME'S, matching the runtime after round 3. At a
        # pure midnight or a pure noon the blended nominal and the regime
        # nominal are the same value, which is why this reads as one variable.
        step = max(1.0, nominal) / EMISSIVE_QUANT_STEPS
        per_mode: dict[str, tuple[float, float]] = {}
        for mode_name, params in SHOW_MODES.items():
            written = []
            for weight in (1.0 - params["surfaceDepth"], 1.0):
                nits = nominal * params["level"] * weight * params["gain"]
                nits = min(ceiling, max(floor, nits))
                q = max(1, math.floor(nits / step + 0.5))
                # `%.1f` is what the runtime formats, so the model rounds the
                # same way rather than carrying digits the renderer never sees.
                written.append(round(q * step, 1))
            per_mode[mode_name] = (min(written), max(written))
        out[cls_name] = per_mode
    return out


EMISSIVE_WRITE_DEMAND = emissive_write_demand()
EMISSIVE_WRITE_CAP = EMISSIVE_WRITE_BUDGET * 60.0
# The sun's own demand, as a requirement on the level rather than as a
# number this file can assert on its own: a day shorter than this drives
# the queue past half the cap at the moment the light is changing fastest.
EMISSIVE_TOD_MIN_DAY_SECONDS = emissive_min_day_seconds(0.5)
# MEASURED, not assumed. Filled from a live probe of
# core_environment.getTimeOfDay().dayLength on the isolated test profile;
# None means nobody has read it yet and the assert below stands down rather
# than inventing a default. See the round-3 [PERF] block.
# PROBED 2026-08-15 on the isolated test profile, freeroam/smallgrid:
# core_environment.getTimeOfDay() returned
#   {dayLength = 1800, time = 0.9, play = false, day = 20, ...}
# so a full cycle is 1800 s and the sun's own peak demand is 14.5 w/s
# against a 120 w/s cap - 12%, and 8.3x inside the 434.6 s floor below.
MEASURED_DAY_LENGTH_S: float | None = 1800.0
if MEASURED_DAY_LENGTH_S is not None:
    assert emissive_tod_demand(MEASURED_DAY_LENGTH_S) <= EMISSIVE_WRITE_CAP * 0.5, (
        f"a {MEASURED_DAY_LENGTH_S:.0f} s day asks for "
        f"{emissive_tod_demand(MEASURED_DAY_LENGTH_S)} writes/s from the sun "
        f"alone, over half the {EMISSIVE_WRITE_CAP:.0f}/s cap"
    )
# HEADROOM, not a near miss. The worst mode has to leave the budget room for
# a mode change (which re-targets every surface at once) without the queue
# ever going saturated, so half the cap is the line.
assert max(EMISSIVE_WRITE_DEMAND.values()) <= EMISSIVE_WRITE_CAP * 0.5, (
    f"driven-surface write demand {EMISSIVE_WRITE_DEMAND} exceeds half of "
    f"the {EMISSIVE_WRITE_CAP:.0f}/s cap"
)
# And the honest main-thread cost, which is what B-2 was actually about:
# demand x the measured per-write millisecond, spread over 60 frames.
EMISSIVE_WORST_MS_PER_FRAME = round(
    max(EMISSIVE_WRITE_DEMAND.values()) * EMISSIVE_WRITE_MS[1] / 60.0, 3)
EMISSIVE_TYPICAL_MS_PER_FRAME = round(
    max(EMISSIVE_WRITE_DEMAND.values()) * EMISSIVE_WRITE_MS[0] / 60.0, 3)
# The gate is a tenth of a frame at the WORST measured per-write cost, so the
# number this file quotes is the pessimistic one. Round 1 quoted the optimistic
# one (0.65 ms) for a system that actually cost 3.0-8.0.
assert EMISSIVE_WORST_MS_PER_FRAME <= FRAME_MS_AT_60 * 0.10, (
    f"the sign lighting would cost {EMISSIVE_WORST_MS_PER_FRAME} ms/frame"
)

# THE NIGHT CEILING IS ALLOWED TO CLAMP - that is the whole reason fever is
# carried by colour and rate after dark - but THE FLOOR MUST NEVER FIRE, or the
# schedule is once again describing a number nothing writes.
for _night in (True, False):
    _floor = EMISSIVE_NIGHT_FLOOR if _night else EMISSIVE_DAY_FLOOR
    for _cls, _modes in emissive_runtime_band(_night).items():
        for _mode, (_lo, _hi) in _modes.items():
            # NAMES THE MODE. The old form min/maxed the mode axis away, so
            # a failure told you which class was out of band and left you to
            # find out which of the four shows put it there.
            assert _lo >= _floor, (
                f"{_cls} in {_mode} would be WRITTEN at {_lo} nit, under "
                f"the {'night' if _night else 'day'} floor {_floor}"
            )
            if _night:
                assert _lo <= NIGHT_PEAK_NITS, (
                    f"{_cls} in {_mode} has a night TROUGH of {_lo} nit, "
                    f"above the {NIGHT_PEAK_NITS} nit ceiling"
                )

# ---------------------------------------------------------------------------
# THE DIRECTIONAL FIXTURES. Three centre strobes on the marquee soffit aimed
# down the board, and one spotlight per peg row washing the pins.
#
# POSITIONS ARE DERIVED, NEVER RETYPED - this file's own law, and the reason
# the lamp lights sit on their tubes. The strobes hang off the marquee flood's
# own y and the sign band's own z; the peg spots sit on the tube line at the
# EXACT z of the peg row they light, read straight out of PEG_ROW_Z.
STROBE_X = round(FIELD_HW * 0.5, 4)                    # 6.00
STROBE_Y = LAMP_MARQUEE_Y + 1.20                       # just inboard of the flood
STROBE_Z = SIGN_Z0 - 0.60                              # under the marquee soffit
PEG_SPOT_Y = LAMP_TUBE_Y - 1.60                        # outboard of the lamp run
PEG_SPOT_X = LAMP_TUBE_X + 1.10                        # outboard of the tubes

SPOT_SPECS: list[dict] = []
for _index, _sx in enumerate((-STROBE_X, 0.0, STROBE_X)):
    SPOT_SPECS.append({
        "slot": f"strobe_{_index}",
        "cls": "centre_strobe",
        "pos": [_sx, STROBE_Y, STROBE_Z],
        # Aimed down the board face and slightly inboard, so three cones cover
        # the 24 m field without three hot discs on the glass.
        "dir": [(-_sx) * 0.25, 0.55, -1.0],
        "range": 46.0,
        "chase": round(_index / 3.0, 4),
    })
for _row, _z in enumerate(PEG_ROW_Z):
    # Alternate sides so consecutive rows are lit from opposite edges: a pin
    # field lit from one side only has every peg casting the same shadow, and
    # the stagger is the thing the board is actually about.
    _side = -1.0 if (_row % 2 == 0) else 1.0
    SPOT_SPECS.append({
        "slot": f"pegspot_{_row}",
        "cls": "peg_spot",
        "pos": [_side * PEG_SPOT_X, PEG_SPOT_Y, round(_z + 1.20, 4)],
        "dir": [-_side, 0.85, -0.25],
        "range": 26.0,
        "chase": round(_row / len(PEG_ROW_Z), 4),
        "row": _row,
        "rowz": round(_z, 4),
    })

# ---- THE LETTER FLOODS ---------------------------------------------------
# One per plate, standing off the lit face and turned slightly toward the
# street side so the pool sits on the plate and not on the shaft wall behind
# it. Positions are read straight out of LETTER_PLATE_X / LETTER_PLATE_Z:
# nothing here is typed twice.
#
# THE CHASE PHASE IS THE ONE THE LETTERS USED TO CARRY. k/8 up the stack, so
# the wave runs BOTTOM TO TOP and the sign fills up - which is the direction
# round 1 claimed for the letters and, unlike the bin claim below, actually
# built. It reads the same as before; it is now carried by a fixture that can
# actually run at the rate a chase needs.
LETTER_SPOT_STANDOFF = 3.40
LETTER_SPOT_Y = -2.20
for _k, _lz in enumerate(LETTER_PLATE_Z):
    SPOT_SPECS.append({
        "slot": f"letterspot_{_k}",
        "cls": "letter_flood",
        "pos": [round(LETTER_PLATE_X + LETTER_SPOT_STANDOFF, 4), LETTER_SPOT_Y, _lz],
        "dir": [-LETTER_SPOT_STANDOFF, -LETTER_SPOT_Y, 0.0],
        "range": 14.0,
        # Bottom plate first: LETTER_PLATE_Z is top-down, so the phase has to
        # be counted from the BOTTOM for the wave to travel upward.
        "chase": round((len(LETTER_PLATE_Z) - 1 - _k) / len(LETTER_PLATE_Z), 4),
        "letter": _k,
    })

assert len(SPOT_SPECS) == 3 + PEG_ROWS + 8, len(SPOT_SPECS)
assert len({entry["slot"] for entry in SPOT_SPECS}) == len(SPOT_SPECS)
# Same law as the PointLights: no fixture may sit inside the volume a car can
# occupy. The original form of this test was `y <= LAMP_TUBE_Y`, which is a
# PROXY for that law and only holds while every fixture is on the board's front
# elevation. The letter floods are on the shaft's outboard FLANK at x = 27.6,
# past the carriage deck's far edge, where y is irrelevant - so the test is
# stated in the terms the law is actually about: a fixture is safe if it is
# outboard of the board face OR outboard of everything a car can reach in x.
CAR_REACH_X = max(FIELD_HW, DECK_X1) + 1.0
assert all(
    entry["pos"][1] <= LAMP_TUBE_Y + 1e-9 or entry["pos"][0] >= CAR_REACH_X
    for entry in SPOT_SPECS
), "a spotlight strayed into the fall volume"


def _spot_specs_lua() -> str:
    rows = []
    for entry in SPOT_SPECS:
        cls = FIXTURE_CLASSES[entry["cls"]]
        x, y, z = (round(v, 4) + 0.0 for v in entry["pos"])
        dx, dy, dz = (round(v, 4) + 0.0 for v in entry["dir"])
        rows.append(
            f'  {{slot = "{entry["slot"]}", cls = "{entry["cls"]}", '
            f"pos = vec3({x}, {y}, {z}), dir = vec3({dx}, {dy}, {dz}), "
            f'range = {entry["range"]}, brightness = {cls["brightness"]}, '
            f'inner = {cls["inner_deg"]}, outer = {cls["outer_deg"]}, '
            f'kelvin = {cls["kelvin"]}, chase = {entry["chase"]}, '
            # BOTH DISCRIMINATORS. `row` was omitted here while the Lua
            # branched on it, so every spotlight fell through to the
            # strobe waveform. A field the runtime tests has to be
            # emitted, and -1 is the absent sentinel so the test is a
            # number comparison rather than a nil check on a spliced table.
            f'row = {entry.get("row", -1)}, '
            f'letter = {entry.get("letter", -1)}, '
            f'rowz = {entry.get("rowz", -1)}}},'
        )
    return "\n".join(rows)


def _show_constants_lua() -> str:
    """The show's own constants, as Lua locals.

    Emitted rather than typed into the runtime for the same reason the light
    and audio tables are spliced: these are DERIVED photometric numbers - the
    night ceiling is the measured 320-nit rung, the write budget is set by a
    measured 1.5-4.0 ms postApply - and a derived number that gets retyped is
    the defect class this file's own ledger names as its leading one.
    """
    return "\n".join([
        f"local EMISSIVE_WRITE_BUDGET = {EMISSIVE_WRITE_BUDGET}",
        f"local EMISSIVE_QUANT_STEPS = {EMISSIVE_QUANT_STEPS}",
        f"local EMISSIVE_NIGHT_PEAK = {NIGHT_PEAK_NITS}",
        f"local EMISSIVE_DAY_PEAK = {DAY_BAND[1]}",
        f"local EMISSIVE_NIGHT_FLOOR = {EMISSIVE_NIGHT_FLOOR}",
        f"local EMISSIVE_DAY_FLOOR = {EMISSIVE_DAY_FLOOR}",
        f"local SURFACE_BREATHE_HZ = {SURFACE_BREATHE_HZ}",
        f"local LETTER_CHASE_DEPTH = {LETTER_CHASE_DEPTH}",
    ])


def _show_modes_lua() -> str:
    rows = []
    for name, params in SHOW_MODES.items():
        rows.append(
            f'  {name} = {{level = {params["level"]}, '
            f'chaseBeats = {params["chaseBeats"]}, depth = {params["depth"]}, '
            f'gain = {params["gain"]}, surfaceDepth = {params["surfaceDepth"]}}},'
        )
    return "\n".join(rows)


def _emissive_specs_lua() -> str:
    rows = []
    for entry in EMISSIVE_SPECS:
        cls = FIXTURE_CLASSES[entry["cls"]]
        rows.append(
            # NO `chase`. The travelling wave is on the letter floods now;
            # a surface that cannot be refreshed above 7.5 Hz has no business
            # carrying a 2.2-4.4 Hz waveform, and shipping the field anyway
            # would leave the next reader believing it still does.
            f'  {{slot = "{entry["slot"]}", mat = "{entry["material"]}", '
            f'day = {cls["day_nits"]}, night = {cls["night_nits"]}}},'
        )
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# THE CUE SET (round 7, 2026-08-14). 36 mono 48 kHz Ogg cues, procedurally
# synthesised against this machine's own event list and convolved through one
# parlour IR so they share a room. The set and its measurements are
# authoring/pachinko_audio_manifest.json; every stop time below is that file's
# published `recommended_stop_s`, copied here so the shipped table is a
# GREPPABLE constant rather than a build-time file read.
#
# THREE ENGINE FACTS THIS IS BUILT ON, all of them expensive to rediscover:
#
# 1. `AudioDefaultLoop3D` is the ONLY sound description proven audible on this
#    pipeline (centrifuge audio mechanism v3, after fileName-`SFXEmitter` and
#    `Engine.Audio.playOnce` both tested silent/unprovable, AGENTS.md). So
#    there IS no one-shot: every cue wraps forever unless something stops it.
#    Each one-shot therefore ships with a silent tail pad, and its stop time
#    lands INSIDE that pad - after the audible content, before the wrap - so
#    the cut is inaudible and clock drift has room. Loops carry stop = None
#    and are stopped by state, not by a clock.
# 2. `obj:createSFXSource` is an `obj` method, independent of the vehicle VM's
#    module stack - which is why it works on a bare proplib prop, and why the
#    audio lives VEHICLE-side while the lights live GE-side (THE PROP CANNOT
#    HOST VEHICLE LIGHT PROPS law, AGENTS.md).
# 3. FMOD downmixes 3D sources to mono, so the whole set is authored mono.
#    Nothing is lost and the bytes are halved.
#
# Volumes are linear 0..1 and are a MIX, not a normalisation: the bank was
# already normalised as a bank at synthesis time (a soft strike really is
# quieter than a hard one), so these numbers only set each layer's place in
# the mix - beds under, announcements over, the kicker and the jackpot on top.
# ---------------------------------------------------------------------------
AUDIO_CUE_TABLE: list[tuple[str, float | None, float]] = [
    # name, stop seconds (None = a loop, stopped by state), mix volume
    # --- the pin bank: 15 modal strikes, 5 per velocity class ----------
    ("pin_soft_01", 0.82, 0.60),      # 1.345 s
    ("pin_soft_02", 0.965, 0.60),     # 1.490 s
    ("pin_soft_03", 0.922, 0.60),     # 1.447 s
    ("pin_soft_04", 0.949, 0.60),     # 1.474 s
    ("pin_soft_05", 0.919, 0.60),     # 1.444 s
    ("pin_med_01", 1.105, 0.60),      # 1.630 s
    ("pin_med_02", 0.89, 0.60),       # 1.415 s
    ("pin_med_03", 1.026, 0.60),      # 1.551 s
    ("pin_med_04", 1.088, 0.60),      # 1.613 s
    ("pin_med_05", 1.01, 0.60),       # 1.535 s
    ("pin_hard_01", 1.4, 0.60),       # 1.925 s
    ("pin_hard_02", 1.575, 0.60),     # 2.100 s
    ("pin_hard_03", 1.488, 0.60),     # 2.013 s
    ("pin_hard_04", 1.304, 0.60),     # 1.829 s
    ("pin_hard_05", 1.471, 0.60),     # 1.996 s
    # --- transport and mechanism ---------------------------------------
    ("attract_bed", None, 0.42),      # 12.000 s, loop
    ("hoist_loop", None, 0.62),       # 2.000 s, loop
    ("hoist_settle", 2.225, 0.72),    # 2.750 s
    ("gate_open", 1.225, 0.78),       # 1.750 s
    ("kicker_impulse", 1.625, 0.95),  # 2.150 s
    ("chute_slide", None, 0.66),      # 3.000 s, loop
    # --- the yokoku ladder: one bell family, four decades ---------------
    ("yokoku_t1", 1.525, 0.70),       # 2.050 s
    ("yokoku_t2", 1.975, 0.74),       # 2.500 s
    ("yokoku_t3", 2.652, 0.80),       # 3.240 s
    ("yokoku_t4", 3.646, 0.88),       # 4.455 s
    # --- the reach and its two resolutions ------------------------------
    ("reach_loop", None, 0.48),       # 2.000 s, loop (6-voice Risset riser)
    ("reach_win", 5.967, 0.80),       # 7.290 s
    ("reach_fail", 4.862, 0.78),      # 5.940 s
    # --- the payout ------------------------------------------------------
    ("payout_small", 1.725, 0.85),    # 2.250 s
    ("payout_medium", 3.094, 0.90),   # 3.780 s
    ("payout_jackpot", 7.514, 1.00),  # 9.180 s
    ("concede", 2.873, 0.80),         # 3.510 s
    # --- the knocker, escalating with the rap ladder ---------------------
    ("knocker_1", 0.775, 0.86),       # 1.300 s
    ("knocker_2", 0.842, 0.86),       # 1.367 s
    ("knocker_3", 0.908, 0.86),       # 1.433 s
    ("knocker_4", 0.975, 0.86),       # 1.500 s
]

AUDIO_CUE_NAMES = [name for name, _stop, _volume in AUDIO_CUE_TABLE]
assert len(AUDIO_CUE_NAMES) == len(set(AUDIO_CUE_NAMES)) == 36, "cue name collision"

# THE PIN POOL. 15 sources are created ONCE, up front, and round-robined
# within the velocity class; a source per collision would create hundreds of
# engine sources during one fall through eight rows of pegs.
AUDIO_PIN_POOL = {
    cls: [name for name in AUDIO_CUE_NAMES if name.startswith(f"pin_{cls}_")]
    for cls in ("soft", "med", "hard")
}
assert all(len(pool) == 5 for pool in AUDIO_PIN_POOL.values()), AUDIO_PIN_POOL

# THE PIN DETECTOR. This engine gives a GE-side prop no car/cage contact
# callback, so a strike is INFERRED from the subject sample the machine
# already takes every frame: the frame-to-frame change in its velocity with
# free fall removed is, by definition, an impulse it received from something
# solid. Thresholds in m/s of that impulse. The floor is set well above the
# position-differencing noise (a soft body's ref node jitters a few cm/s),
# and the gap keeps a burst of sub-frame contacts from machine-gunning the
# bank - one strike per 0.12 s is already 8 a second.
AUDIO_PIN_MIN_MPS = 1.5
AUDIO_PIN_MED_MPS = 4.0
AUDIO_PIN_HARD_MPS = 8.0
AUDIO_PIN_GAP_SECONDS = 0.12

# ---------------------------------------------------------------------------
# THE PA HORNS (round 8, 2026-08-14) - which cues leave the machine and go up
# the pole, and the four scene emitters that carry them.
#
# THE MECHANISM, PROBED RATHER THAN ASSUMED (three live probes, recorded off a
# WASAPI loopback of the game's own output - "an object was created" is not
# "a sound was heard", and this pack has believed that before):
#
#   * `SFXEmitter` + a `fileName` pointing at the shipped .ogg + `is3D = 1`,
#     `isLooping = 1`, `playOnAdd = 0` is AUDIBLE and positional. Measured
#     rms 0.0338 against a true floor of 8.5e-17 at 18 m.
#   * `SFXEmitter` + `track` is DIGITAL SILENCE on this build - with a
#     hand-built SFXProfile, with useTrackDescriptionOnly either way, and
#     with a stock FMOD event string. The field never even reads back. That
#     is the "fileName-SFXEmitter proved unprovable" note in AGENTS.md
#     finally resolved, and resolved the other way round: fileName is the
#     half that works and `track` is the half that does not.
#   * THE CONES ARE REAL, and exact. A 30/70 deg cone at outsideVolume 0.05
#     measured 0.000350 behind and 0.00700 in front - a ratio of 0.0500, the
#     set value to three figures - while an identical emitter without a cone
#     measured 0.00700 from all three directions. So "four directions" is an
#     audible fact here and not just a picture.
#   * FOUR COPIES OF ONE MONO CUE DO NOT STATIONARY-COMB. Measured at two
#     listening positions: four horns against one horn came out +5.66 and
#     +5.69 dB, i.e. a POWER sum (+6.0), not a coherent one (+12.0). The
#     engine applies no propagation delay, so the only thing decorrelating
#     the four is that each `play()` lands on a different frame - which is
#     what a real horn array does, and what makes the result read as a
#     cluster rather than as one loudspeaker. Deliberately staggering the
#     starts by 11/22/33 ms changed the level by 0.1-0.2 dB and is therefore
#     NOT done: it buys nothing and adds a schedule to maintain.
#
# WHICH CUES MOVE. A PA horn ANNOUNCES; it does not make the pin clatter. The
# announcements - the yokoku ladder, the two reach resolutions, the payouts and
# the concede - go up the pole. Every physical cue stays where it physically
# originates: pin strikes at the pegs, the hoist loop and its settle, the gate,
# the kicker, the chute slide, the knocker and the attract bed all stay on the
# vehicle-side `createSFXSource` at the prop's own reference node.
HORN_CUES = (
    "yokoku_t1", "yokoku_t2", "yokoku_t3", "yokoku_t4",
    "reach_win", "reach_fail",
    "payout_small", "payout_medium", "payout_jackpot", "concede",
)
assert set(HORN_CUES) <= set(AUDIO_CUE_NAMES), "a horn cue is not in the cue set"
assert len(HORN_CUES) == len(set(HORN_CUES)) == 10
# Nothing on the horns may be a LOOP: a scene emitter has no vehicle-side stop
# clock behind it, and the GE hold table is what stops these.
assert all(
    stop is not None for name, stop, _v in AUDIO_CUE_TABLE if name in HORN_CUES
), "a horn cue is a loop, and the pole has no loop owner"

# Cone geometry, in the engine's own terms: the angles are FULL angles, so the
# inner half-angle is 50 deg and the outer 110 deg. With four horns 90 deg
# apart that puts every azimuth inside somebody's inner cone, and the power sum
# around the compass varies by 1.2 dB - a cluster that is directional per horn
# and even overall, which is exactly what a four-way PA head does.
HORN_CONE_IN_DEG = 100.0
HORN_CONE_OUT_DEG = 220.0
HORN_CONE_OUT_VOL = 0.30
# Full level to the far end of the machine, gone by the time you are off the
# level. (The stock AudioDefaultLoop3D description uses 20/120; a PA horn
# should carry a little further than a machine noise.)
HORN_REF_M = 22.0
HORN_MAX_M = 150.0
# Per-horn mix trim. The emitter path measured ~1.8x the vehicle-side path at
# the same nominal volume and the same distance, and four horns power-sum to
# ~1.38x on top of that; 0.50 lands the announcement about 2 dB above where it
# used to sit at the prop origin, which is the point of putting it on a PA.
HORN_GAIN = 0.50


def _horn_specs_lua() -> str:
    rows = []
    for index, (mouth, (dx, dy)) in enumerate(zip(HORN_MOUTHS, HORN_DIRS)):
        x, y, z = (round(v, 4) + 0.0 for v in mouth)
        rows.append(
            f'  {{slot = "horn_{index}", pos = vec3({x}, {y}, {z}), '
            f'dir = vec3({round(dx, 6) + 0.0}, {round(dy, 6) + 0.0}, 0)}},'
        )
    return "\n".join(rows)


def _peg_rows_lua() -> str:
    """The peg lattice, for the GE side's nearest-peg lookup.

    Spliced rather than added to BEHAVIOR for the same reason the light and
    audio tables are: the tuned BEHAVIOR table is a knob list, and a lattice
    is not a knob. ``row`` is the index that appears in the cage NODE NAMES
    (peg_<row>_<col>_<segment>), which is what the vehicle side matches on -
    so this table and the node names cannot drift apart without the selector
    simply finding nothing.
    """

    rows = []
    for index, z in enumerate(PEG_ROW_Z):
        count = PEG_COLUMNS_EVEN if index % 2 == 0 else PEG_COLUMNS_ODD
        span = (count - 1) * PEG_PITCH_X
        xs = [round(-span / 2.0 + PEG_PITCH_X * i, 6) + 0.0 for i in range(count)]
        rows.append(
            f"  {{row = {index}, z = {z}, xs = {{{', '.join(str(x) for x in xs)}}}}},"
        )
    return "local PEG_ROWS = {\n" + "\n".join(rows) + "\n}"


def _horn_cues_lua() -> str:
    volumes = {name: volume for name, _stop, volume in AUDIO_CUE_TABLE}
    rows = []
    for name in HORN_CUES:
        rows.append(f'  {{name = "{name}", vol = {round(volumes[name] * HORN_GAIN, 4)}}},')
    return "\n".join(rows)

# ``sound/`` under the vehicle folder, staged by prop_builder from assets/ -
# the SHIPPED-ASSET LAW: what reaches a player's disk is declared, never a
# blind copy of the assets tree.
SHIP_ASSETS = tuple(f"sound/{MOD_ID}_{name}.ogg" for name in AUDIO_CUE_NAMES)
# Drift guard in both directions: a cue named here with no file would ship a
# path the engine silently fails to open (createSFXSource returns an id for a
# missing file and simply never makes a sound), and a file in assets/sound/
# that no cue names would be a build input reaching a player's disk.
_AUDIO_DIR = __import__("pathlib").Path(__file__).resolve().parent / "assets" / "sound"
if _AUDIO_DIR.is_dir():
    _AUDIO_ON_DISK = {path.name for path in _AUDIO_DIR.glob("*.ogg")}
    assert _AUDIO_ON_DISK == {f"{MOD_ID}_{name}.ogg" for name in AUDIO_CUE_NAMES}, (
        "assets/sound/ and AUDIO_CUE_TABLE disagree: "
        f"{sorted(_AUDIO_ON_DISK ^ {f'{MOD_ID}_{n}.ogg' for n in AUDIO_CUE_NAMES})}"
    )


def _audio_cues_lua() -> str:
    """The vehicle-side cue table: stop clock and mix volume per cue."""
    rows = []
    for name, stop, volume in AUDIO_CUE_TABLE:
        stop_lua = "nil" if stop is None else f"{stop}"
        rows.append(f'  {name} = {{stop = {stop_lua}, vol = {volume}}},')
    return "\n".join(rows)


def _audio_pin_pool_lua() -> str:
    rows = []
    for cls in ("soft", "med", "hard"):
        names = ", ".join(f'"{name}"' for name in AUDIO_PIN_POOL[cls])
        rows.append(f"  {cls} = {{{names}}},")
    return "\n".join(rows)


# GE dtSim per wall second. The audio plays on FMOD's real-time clock while
# the GE observer counts in dtSim, so any GE-side duration has to be stated in
# whichever unit its clock runs on.
#
# MEASURED BOTH WAYS, 2026-08-14, because AGENTS.md records dtSim running
# ~3x wall in a prop's behavior.update and that number would have made every
# clock here three times too short. dock and arming are fixed sim-second
# windows with no other exit (dock_settle_seconds = 1.6, gate_seconds = 1.4),
# so their WALL duration measures the ratio directly:
#
#   deterministic rig, set_deterministic(60) + resume:
#       dock 1.6 sim / 0.532 wall = 3.006     arming 1.4 / 0.468 = 2.992
#   non-deterministic, the way a player runs the game:
#       dock 1.6 sim / 1.616 wall = 0.990     arming 1.4 / 1.417 = 0.988
#
# So dtSim is wall time. The 3x is the HARNESS: a deterministic rig steps the
# world as fast as the machine can, and the whole simulation - gravity
# included - runs in fast-forward with it, which is why the ratio is uniform
# across two unrelated phases. It was never a property of behavior.update.
# 1.0 is therefore the value, and it stays a NAMED constant rather than an
# assumption baked into a dozen literals: one number to change if a future
# engine disagrees. (The same reading says the centrifuge's 11.2 s hand-off
# clock lands where its clip says it should for a player.)
AUDIO_SIM_PER_WALL = 1.0


def _audio_ge_lua() -> str:
    """The GE observer's own constants: the pin-impulse thresholds, and the
    one-shot lengths for the single decision the GE side makes with them -
    the attract bed may not open under a payout that is still resolving.
    Loops are absent: a loop's life is a state, not a duration."""
    scale = AUDIO_SIM_PER_WALL
    rows = [
        f"local AUDIO_PIN_MIN = {AUDIO_PIN_MIN_MPS}",
        f"local AUDIO_PIN_MED = {AUDIO_PIN_MED_MPS}",
        f"local AUDIO_PIN_HARD = {AUDIO_PIN_HARD_MPS}",
        f"local AUDIO_PIN_GAP = {round(AUDIO_PIN_GAP_SECONDS * scale, 4)}",
        "-- One-shot lengths in dtSim seconds (wall seconds x "
        f"{scale}, see AUDIO_SIM_PER_WALL).",
        "local AUDIO_HOLD = {",
    ]
    for name, stop, _volume in AUDIO_CUE_TABLE:
        if stop is not None and not name.startswith("pin_"):
            rows.append(f"  {name} = {round(stop * scale, 4)},")
    rows.append("}")
    return "\n".join(rows)


# The vehicle VM owns the sources, because obj:createSFXSource is an obj
# method. It owns the stop clocks too: they run on the vehicle's own graphics
# dt, which is REAL time - the same clock the audio itself plays on - rather
# than on GE dtSim, which AGENTS.md measures at ~3x wall. The GE runtime only
# ever names a cue; every decision about how long a sound lives is made here,
# next to the source it applies to.
VEHICLE_LUA_EXTRA = f"""
-- =====================================================================
-- THE PACHINKO CUE SET (round 7, 2026-08-14).
--
-- Mechanism: obj:createSFXSource + AudioDefaultLoop3D, the only path this
-- pack has ever proven audible (centrifuge audio mechanism v3). Node id is
-- literal 0 - the prop's own reference node - so every cue emits from one
-- point on a 54 m machine. That is a real limitation and not a lapse: node
-- ids here are cage indices, and picking a crown node for the gate and a
-- bin node for the payout would bind the soundtrack to the cage numbering
-- that the fence forbids touching.
--
-- EVERY ONE-SHOT IS A LOOP WEARING A STOP CLOCK. See AUDIO_CUES in spec.py.
-- =====================================================================
local AUDIO_PATH = "vehicles/{MOD_ID}/sound/{MOD_ID}_"
local AUDIO_CUES = {{
--@AUDIO_CUES@--
}}
local AUDIO_PIN_POOL = {{
--@AUDIO_PIN_POOL@--
}}

local audioId = {{}}      -- cue name -> engine source id, created at most once
local audioStopIn = {{}}  -- cue name -> real seconds left before its stop
local audioPrimed = false
-- Census counters, for the live L-SYNC trace: which cue was dispatched, and
-- how many have been. They make "the sound landed on the frame the light
-- flashed" a MEASUREMENT rather than a claim about the source code, since
-- nothing else on this side of the boundary is observable from the GE side.
local audioPlays = 0
local audioLast = "none"

local function audioSource(name)
  local id = audioId[name]
  if id ~= nil then return id end
  local cue = AUDIO_CUES[name]
  if cue == nil then return nil end
  local ok, created = pcall(function()
    return obj:createSFXSource(
      AUDIO_PATH .. name .. ".ogg", "AudioDefaultLoop3D", "pt_" .. name, 0)
  end)
  if not ok or created == nil then return nil end
  audioId[name] = created
  pcall(function() obj:setVolumePitch(created, cue.vol, 1) end)
  return created
end

-- Stop only the id you started. A blanket stop cuts a clip another trigger
-- still needs (the centrifuge's rule, learned the same way).
local function audioStop(name)
  audioStopIn[name] = nil
  local id = audioId[name]
  if id ~= nil then pcall(function() obj:stopSFX(id) end) end
end

local function audioPlay(name)
  local cue = AUDIO_CUES[name]
  if cue == nil then return end
  local id = audioSource(name)
  if id == nil then return end
  audioStopIn[name] = cue.stop  -- nil for a loop: it lives until state says stop
  audioPlays = audioPlays + 1
  audioLast = name
  pcall(function() obj:playSFX(id) end)
end

-- POOL THE PIN BANK UP FRONT. Fifteen sources, created once when the prop
-- registers; a fall through eight rows of pegs would otherwise ask the engine
-- for a source per collision.
local function audioPrime()
  if audioPrimed then return end
  audioPrimed = true
  for _class, pool in pairs(AUDIO_PIN_POOL) do
    for index = 1, #pool do audioSource(pool[index]) end
  end
end

local function audioStopAll()
  for name, id in pairs(audioId) do
    audioStopIn[name] = nil
    pcall(function() obj:stopSFX(id) end)
  end
end

-- The stop clocks, serviced on the vehicle's own graphics dt. Writing nil to
-- the key currently being visited is legal in a pairs() walk (adding one is
-- not, and nothing here adds).
local audioBaseUpdateGFX = updateGFX
local function audioUpdateGFX(dt)
  audioBaseUpdateGFX(dt)
  for name, remaining in pairs(audioStopIn) do
    remaining = remaining - dt
    if remaining <= 0 then
      audioStopIn[name] = nil
      local id = audioId[name]
      if id ~= nil then pcall(function() obj:stopSFX(id) end) end
    else
      audioStopIn[name] = remaining
    end
  end
end

-- RESET HYGIENE. A reset that leaves a LOOP running would leave it running
-- forever: the fresh state has no handle to it. Both teardown paths the
-- vehicle VM has therefore silence everything they can still reach, before
-- the registration machinery runs.
local audioBaseOnReset = onReset
local function audioOnReset()
  audioStopAll()
  audioBaseOnReset()
end

local audioBaseOnExtensionUnloaded = onExtensionUnloaded
local function audioOnExtensionUnloaded()
  audioStopAll()
  audioBaseOnExtensionUnloaded()
end

M.updateGFX = audioUpdateGFX
M.onReset = audioOnReset
M.onExtensionUnloaded = audioOnExtensionUnloaded
M.pachinkoAudioPrime = audioPrime
M.pachinkoAudioPlay = audioPlay
M.pachinkoAudioStop = audioStop
M.pachinkoAudioStopAll = audioStopAll

-- Read-only census for the live cleanup trace: how many sources exist, which
-- of them the VM still holds a handle to, and what is on a stop clock.
M.pachinkoAudioReport = function()
  local created, clocked = 0, 0
  local live = {{}}
  for name, id in pairs(audioId) do
    created = created + 1
    live[#live + 1] = name .. "=" .. tostring(id)
  end
  for _name, _left in pairs(audioStopIn) do clocked = clocked + 1 end
  obj:queueGameEngineLua(string.format(
    "log('I', 'pachinko_audio', 'AUDIO_REPORT plays=%d last=%s sources=%d"
    .. " clocked=%d primed=%s ids=%s')",
    audioPlays, audioLast, created, clocked, tostring(audioPrimed),
    table.concat(live, ",")))
end
"""
VEHICLE_LUA_EXTRA = VEHICLE_LUA_EXTRA.replace(
    "--@AUDIO_CUES@--", _audio_cues_lua()
).replace("--@AUDIO_PIN_POOL@--", _audio_pin_pool_lua())
assert "--@AUDIO_" not in VEHICLE_LUA_EXTRA, "audio splice failed"

# ---------------------------------------------------------------------------
# THE RETRACTABLE PIN (2026-08-14i, serial 76). Vehicle-side half.
# ---------------------------------------------------------------------------
# What finally hangs a car on this machine is a car DRAPED OVER ONE PEG. The
# 56-play census said so (10 of 13 field hangs had the x = 0 centre column as
# nearest peg, 9 of 16 in z 25.6-30.0 around the single peg at (0, 28)), the
# give-up telemetry added in the same round proved those cars are NOT touching
# a board face (0.67 to 1.95 m of clearance to the nearest one, measured over
# the whole node cloud), and a headless A/B reproduced it on demand: dropped
# square onto that peg, an etk800 settles at z = 29.29 and sits there.
#
# Nothing about the pin's SHAPE can fix that. mu is already 0; the lattice has
# no feasible redesign (0 designs over a 200k-point grid, and a 3-phase
# stagger makes every diagonal shorter); the knocker cannot rotate a car
# because cluster impulses carry no torque. So the pin gets out of the way.
#
# THE PRIMITIVE IS A RADIAL COLLAPSE TOWARD THE PEG'S OWN DEPTH AXIS. Every
# section vertex moves along the straight line to the peg's (x, z) centroid;
# y - the depth axis - is untouched. Because each section is CONVEX (the
# generator asserts it) and the centroid is interior, the collapsed peg is a
# strict SUBSET of the peg that was already there. No point of it ever
# occupies space it did not already occupy, so it cannot stamp steel through
# a car in any pose. That is the whole safety argument, and it is why a
# TRANSLATING peg is forbidden: a translation's leading face is new geometry,
# and new geometry next to a car is the tipped-deck disaster again.
#
# RE-EXTENSION IS THE DANGEROUS DIRECTION and is gated on the field being
# empty - see pegRestore on the GE side. The vehicle VM cannot see where cars
# are, so it never decides this for itself.
#
# MEASURED, NOT ASSUMED, before any of it was built (scratchpad probe2/probe3):
#   * obj:setNodePosition DOES move fixed:true cage nodes. The row-3 centre
#     peg's 32 nodes went from a +/-1.100 m span to +/-0.110 m and the GE side
#     read the new span back.
#   * THE COLLISION FOLLOWS, same frame, no bake: identical drop, same
#     session, one variable - before the collapse the car rests on the crown
#     at z = 29.29 for the full sample window; after it, it falls to the bin
#     floor at z = 0.21. Vehicle collision triangles are recomputed from node
#     positions every frame, so be:reloadCollision is neither needed nor used.
#
# THE OUTER COLUMNS COLLAPSE TOWARD THE WALL, NOT TOWARD THEMSELVES. Every
# 4-column (even) row's first and last peg is embedded 0.50 m into the wall
# slab and carries the F6 wall-corner gusset. Contracting one toward its own
# centroid would pull it off the wall and open a free bypass lane down the
# side channel - the one thing assert_no_clean_column exists to prevent. So
# for those pegs the contraction point is moved PEG_WALL_INSET outboard, onto
# the wall plane, and the peg shrinks to a stub that is still welded to the
# wall. It is still a subset map: the shifted point is inside the gusseted
# hull at every scallop station (checked numerically, 0 violations over the
# whole field x 7 stations), so the safety argument is untouched.
#
# THE NUMBERS, re-derived from the section's own support function over every
# pair of pegs within 9 m and every scallop station (scratchpad
# throat_retract.py), against the 5.148 m car chord:
#     s = 1.00 (shipped)  worst pairwise clear throat 3.513   PINCH
#     s = 0.50                                        4.526   PINCH
#     s = 0.20                                        5.121   PINCH by 27 mm
#     s = 0.10                                        5.319   CLEAR
#     s = 0.05                                        5.418   CLEAR
# and the outer stub still reaches |x| = 12.158 against the 12.00 m wall
# plane at s = 0.10, i.e. the side channel is closed at full retract. 0.10 is
# therefore the shipped scale: the first value that clears the chord, with the
# next step up failing by 27 mm.
#
# Excluding the outer columns outright - the obvious first design - was
# measured and REJECTED: it leaves a 4.405 m worst throat, because the
# binding pair becomes the full-size outer peg against its collapsed diagonal
# neighbour. A field that is only mostly retracted is not a retracted field.
#
# WHAT IT MEASURED LIVE, headless rig, etk800, one deterministic session per
# build, counted on pachinko_released as the denominator and classified by
# where the machine conceded (z > 10 is the peg field; the bottom row is at
# z = 12):
#
#   build                        releases   PEG-FIELD hangs   bin/divider   auto-resets
#   serial 74 (shipped control)     14          2 (14%)            2             0
#   serial 75 (walls only)          14          4 (29%)            2             0
#   serial 76 (retract, 0.6 s)      15          0                  2             3
#   serial 77 (retract, 1.8 s)      24          0                  3             2
#   serial 78 (this build)          23          0                  5             2
#
# ZERO peg-field hangs in 62 releases with the retract live, against 2 of 14
# on the shipped control and 4 of 14 with the walls change alone. The pooled
# 56-play census this round started from was 16 hangs (28.6%).
#
# TWO RESIDUALS, both named rather than buried. (1) The concessions that are
# left are all in the BIN MOUTH between the divider horns, not on the board -
# a different defect, untouched by this round, and the obvious next one.
# (2) About 2 plays in 23 still end with the engine auto-resetting the car:
# see the ramp note and the tier-1 scale note for the measurement and the two
# mitigations already spent on it. The next lever if it matters is
# obj:breakCollisionTriangle, which takes a peg's collision away while moving
# nothing at all - at the cost of a pin that is still visible while a car
# falls through it, and with no known way to put the triangles back.
#
# THE FRAME PROBLEM IS SIDESTEPPED, NOT SOLVED. obj:getNodePosition returns an
# offset from obj:getPosition() and obj:setNodePosition consumes the same
# frame (beamstate.lua's save/load round-trip proves the pairing). Every home
# position and every centroid here is recorded in THAT frame at prime, so no
# authored-to-vehicle mapping, no yaw and no sign triple is ever needed.
_PEG_RETRACT_LUA = r"""
-- =====================================================================
-- THE RETRACTABLE PIN. See spec.py for the safety argument and the probe.
-- =====================================================================
local PEG_RAMP_SECONDS = @PEG_RAMP@
local PEG_MAX_STEP_M = @PEG_MAXSTEP@
local PEG_RETRACT_SCALE = @PEG_SCALE@
local PEG_WALL_INSET = @PEG_INSET@

local pegGroups = nil    -- "row:col" -> {cids, hx, hz, hy, cx, cz, outer}
local pegLive = {}       -- "row:col" -> {cur, target}
local pegBuilt = false
local pegLast = "none"

local function pegBuild()
  if pegBuilt then return end
  pegBuilt = true
  local nodes = v and v.data and v.data.nodes
  if not nodes then return end
  local acc, rows = {}, {}
  for _, n in pairs(nodes) do
    local name = n.name
    if name then
      local row, col = string.match(name, "_peg_(%d+)_(%d+)_")
      if row then
        local key = row .. ":" .. col
        local g = acc[key]
        if not g then
          g = {cids = {}, hx = {}, hy = {}, hz = {}, sx = 0, sz = 0,
               row = row, col = tonumber(col)}
          acc[key] = g
          rows[row] = rows[row] or {}
          rows[row][#rows[row] + 1] = g
        end
        -- HOME IS READ IN THE SET/GET FRAME, once, while the cage is pristine.
        local p = obj:getNodePosition(n.cid)
        local k = #g.cids + 1
        g.cids[k], g.hx[k], g.hy[k], g.hz[k] = n.cid, p.x, p.y, p.z
        g.sx, g.sz = g.sx + p.x, g.sz + p.z
      end
    end
  end
  local fieldX, groups = 0, 0
  for _key, g in pairs(acc) do
    local n = #g.cids
    g.cx, g.cz = g.sx / n, g.sz / n
    fieldX = fieldX + g.cx
    groups = groups + 1
  end
  fieldX = (groups > 0) and (fieldX / groups) or 0
  -- The wall-embedded outer columns, found STRUCTURALLY (a four-column row's
  -- lowest and highest column index), never by a hard-coded x. Their
  -- contraction point moves PEG_WALL_INSET outboard so the stub stays welded
  -- to the wall instead of peeling off it and opening the side channel.
  for _row, list in pairs(rows) do
    if #list == 4 then
      local lo, hi = list[1], list[1]
      for i = 2, #list do
        if list[i].col < lo.col then lo = list[i] end
        if list[i].col > hi.col then hi = list[i] end
      end
      lo.outer, hi.outer = true, true
    end
  end
  for _key, g in pairs(acc) do
    if g.outer then
      g.cx = g.cx + ((g.cx >= fieldX) and PEG_WALL_INSET or -PEG_WALL_INSET)
    end
  end
  -- REACH, measured AFTER the outer shift because the shift is what makes it
  -- vary between pegs. pegApply moves a node along (home - c), so this node's
  -- travel for a scale change ds is exactly |home - c| * ds and the group's
  -- WORST travel is maxr * ds. That is the number the per-frame clamp in
  -- pegUpdate divides into its budget, and it is measured off the live cage
  -- rather than derived from the section, so a lattice or gusset change
  -- carries the clamp with it instead of silently invalidating it.
  for _key, g in pairs(acc) do
    local maxr = 0
    for i = 1, #g.cids do
      local dx, dz = g.hx[i] - g.cx, g.hz[i] - g.cz
      local r = math.sqrt(dx * dx + dz * dz)
      if r > maxr then maxr = r end
    end
    g.maxr = maxr
  end
  pegGroups = acc
end

local function pegApply(g, scale)
  for i = 1, #g.cids do
    obj:setNodePosition(g.cids[i], vec3(
      g.cx + (g.hx[i] - g.cx) * scale,
      g.hy[i],
      g.cz + (g.hz[i] - g.cz) * scale))
  end
end

-- Selector: "row:col" one peg, "row:*" a whole row, "*:*" the field,
-- "restore" puts everything back (GE gates that on an empty field).
local function pegRetract(selector)
  pegBuild()
  if not pegGroups then return end
  pegLast = tostring(selector)
  local restore = (selector == "restore")
  -- "<row>:<col>#<scale>", either field wildcarded, scale optional. The GE
  -- side chooses the scale per tier (see pegRetract there): the peg a car is
  -- WRAPPED AROUND only goes half way in.
  local body, wanted = string.match(tostring(selector), "^(.-)#([%d%.]+)$")
  body = body or tostring(selector)
  local scale = tonumber(wanted) or PEG_RETRACT_SCALE
  if scale < PEG_RETRACT_SCALE then scale = PEG_RETRACT_SCALE end
  if scale > 1.0 then scale = 1.0 end
  local wantRow, wantCol = string.match(body, "^([%d%*]+):([%d%*]+)$")
  local touched = 0
  for key, g in pairs(pegGroups) do
    local hit = restore
    if not hit and wantRow then
      local row, col = string.match(key, "^(%d+):(%d+)$")
      hit = (wantRow == "*" or wantRow == row)
        and (wantCol == "*" or wantCol == col)
    end
    if hit then
      local live = pegLive[key]
      if not live then live = {cur = 1.0, target = 1.0}; pegLive[key] = live end
      -- A tier may only ever take a peg FURTHER in. A later, shallower
      -- selector must never re-extend one: re-extension is the direction
      -- that can stamp steel through a car, and only pegRestore - which
      -- checks the field is empty - is allowed to do it.
      local want = restore and 1.0 or scale
      if restore or want < live.target then live.target = want end
      touched = touched + 1
    end
  end
  obj:queueGameEngineLua(string.format(
    "log('I','pachinko_peg','PEG_RETRACT sel=%s groups=%d')",
    tostring(selector), touched))
end

-- The ramp. A peg that teleports to its collapsed size in one frame hands the
-- solver a discontinuity right where a car is resting; ramping it lets the car
-- slide off the shrinking crown the way it would off a real one.
--
-- THE CLAMP IS THE GOVERNING RULE AND THE DURATION IS THE FREE VARIABLE, which
-- is the opposite of what shipped through serial 78. PEG_RAMP_SECONDS alone
-- fixes total DURATION, so per-frame vertex travel scales with 1/fps - and
-- setNodePosition is only reachable from updateGFX, so every write is a
-- TELEPORT as far as the 2000 Hz solver is concerned and per-frame travel IS
-- the discontinuity. The arithmetic that justified 1.8 s assumed 60 fps and
-- was measured under the null renderer, where nothing was rendering at all;
-- at 25 fps the same 1.8 s ramp delivers more travel per frame than the 0.6 s
-- ramp did at 60, which is the version that auto-reset 3 cars in 15 plays.
--
-- So the step is min(nominal, budget / reach): the ramp can never move a
-- vertex more than PEG_MAX_STEP_M in one frame no matter what the frame rate
-- does, and a slow frame buys extra WALL-CLOCK seconds rather than extra
-- travel. Reach is per group (see pegBuild), so the outer pegs - whose
-- contraction point is shifted outboard and whose worst node is therefore
-- further from it - ramp proportionally slower on their own merits.
local function pegUpdate(dt)
  if not pegGroups then return end
  local nominal = dt / PEG_RAMP_SECONDS
  for key, live in pairs(pegLive) do
    if live.cur ~= live.target then
      local g = pegGroups[key]
      local step = nominal
      if g and g.maxr and g.maxr > 0 then
        local lim = PEG_MAX_STEP_M / g.maxr
        if lim < step then step = lim end
      end
      local delta = live.target - live.cur
      if math.abs(delta) <= step then
        live.cur = live.target
      elseif delta > 0 then
        live.cur = live.cur + step
      else
        live.cur = live.cur - step
      end
      if g then pegApply(g, live.cur) end
    end
  end
end

local pegBaseUpdateGFX = M.updateGFX
local function pegUpdateGFX(dt)
  pegBaseUpdateGFX(dt)
  pcall(pegUpdate, dt)
end

-- A reset rebuilds the cage from the jbeam, so every collapsed peg is back at
-- full size and the VM's idea of what is retracted has to go with it.
local pegBaseOnReset = M.onReset
local function pegOnReset()
  pegLive = {}
  pegBaseOnReset()
end

M.updateGFX = pegUpdateGFX
M.onReset = pegOnReset
M.pachinkoPegRetract = function(selector) pcall(pegRetract, selector) end
M.pachinkoPegReport = function()
  local n, collapsed = 0, 0
  for _key, live in pairs(pegLive) do
    n = n + 1
    if live.cur < 0.999 then collapsed = collapsed + 1 end
  end
  obj:queueGameEngineLua(string.format(
    "log('I','pachinko_peg','PEG_REPORT tracked=%d collapsed=%d last=%s built=%s')",
    n, collapsed, pegLast, tostring(pegBuilt)))
end
"""
PEG_RETRACT_SCALE = 0.10
# The single-peg tier's stop. Half the travel of a full collapse, because the
# peg a car is wrapped around is the one case that destabilised the solver -
# see the GE-side pegRetract for the 5-of-5 measurement. Crown reach goes
# 1.55 -> 0.70 m and half-width 1.10 -> 0.50 m, which is still a peg a car
# cannot drape over.
PEG_RETRACT_SCALE_NEAR = 0.45
assert PEG_RETRACT_SCALE < PEG_RETRACT_SCALE_NEAR < 1.0
# THE RAMP IS A NUMERICAL BUDGET, NOT A PIECE OF SHOWMANSHIP. Measured on the
# first flying build (serial 76, 0.6 s): 3 of 15 plays ended with the engine
# logging "Instability detected for vehicle ID: <subject>" and auto-resetting
# the car, every one of them 0.2-0.4 s into a retract ramp - i.e. at the point
# where the vertices are moving fastest.
#
# The collapse is a subset map, so it can never PUSH a car; what it can do is
# move a contact surface faster than the solver can follow. setNodePosition is
# only reachable from updateGFX (updateFixedStep is a controller hook, not an
# extension one), so each write is a TELEPORT as far as the 2000 Hz solver is
# concerned: at 0.6 s a crown vertex jumps 27.5 mm per graphics frame with the
# contact spring resolving nothing in between.
#
# 1.8 s puts that at 9.2 mm per frame - a third of the motion, and under the
# node radius - while still finishing inside two rap intervals, so the ladder's
# cadence is unchanged. It is deliberately LONGER than rap_interval_seconds
# (1.6): the tiers overlap, which is harmless because a higher tier's selector
# always contains the lower tier's pegs and they simply keep ramping.
#
# ---------------------------------------------------------------------------
# AND THAT WHOLE PARAGRAPH IS CONDITIONAL ON 60 FPS, WHICH NOTHING GUARANTEED
# (2026-08-15, serial 79).
# ---------------------------------------------------------------------------
# "27.5 mm at 0.6 s" and "9.2 mm at 1.8 s" are both `reach / (fps * seconds)`
# evaluated at fps = 60. A duration is not a travel budget: it is a travel
# budget DIVIDED BY a frame rate, and the frame rate was never fixed, never
# measured, and - because the entire serial 74-78 census ran under the null
# renderer - never even plausibly 60 during the measurements that produced
# these numbers. At 25 fps the shipped 1.8 s ramp delivers 22 mm per frame,
# which is MORE VIOLENT than the 0.6 s ramp that auto-reset 3 cars in 15
# plays. The ramp was frame-rate-dependent in exactly the direction that hurts
# the players with the weakest machines.
#
# Two further errors in the same block, corrected rather than deleted because
# the reasoning is worth keeping and the numbers are not:
#   * the 9.2 mm figure used a reach of ~0.99 m, not the group's true worst
#     node distance from its contraction point. The OUTER pegs' contraction
#     point is shifted PEG_WALL_INSET outboard, so their worst node is further
#     out still, and they were always ramping faster than the quoted figure.
#   * "under the node radius" was never checked against the outer pegs at all.
#
# THE FIX IS TO CLAMP THE QUANTITY THAT MATTERS. PEG_MAX_STEP_M is the most a
# single vertex may move in one graphics frame, and pegUpdate takes
# min(dt / PEG_RAMP_SECONDS, PEG_MAX_STEP_M / reach) with reach measured per
# group off the live cage. PEG_RAMP_SECONDS survives as a nominal FLOOR on the
# speed - it still stops a 300 fps machine from finishing the collapse in a
# quarter of a second - but the clamp is what governs at every frame rate a
# player will actually see, and total duration is now the free variable.
#
# WHY 8 mm. It is below the 9.2 mm the shipped build believed it was
# delivering, so it is a strict tightening on the build that still auto-reset
# two cars; it is well under the node radius; and it is a TRAVEL, so it means
# the same thing at 25 fps as at 144. The cost is honest and stated: duration
# now floats. A full 1.00 -> 0.10 collapse of the worst group covers
# 0.9 * reach, so at reach ~1.55 m that is ~175 frames - about 2.9 s at 60 fps
# and about 7 s at 25. That is slower theatre than 1.8 s, and it is the right
# trade only because this round's real work (the fall volume reaching the bin
# floor) is meant to stop the ladder firing at all; if the ladder is still
# firing often enough for its duration to matter, the round has failed for a
# different reason and tuning this number would be treating the symptom.
PEG_RAMP_SECONDS = 1.8
PEG_MAX_STEP_M = 0.008
assert 0.0 < PEG_MAX_STEP_M < 0.0092, (
    "the per-frame travel clamp must be a strict tightening on the 9.2 mm the "
    "serial-78 build believed its 1.8 s ramp was delivering at 60 fps"
)
# How far outboard of an outer peg's centre the wall plane is. Derived, not
# typed: it is the gap the F6 gusset spans, and if the lattice moves it moves
# with it.
PEG_WALL_INSET = round(FIELD_HW - _OUTER_PEG_X, 6)
assert 0.0 < PEG_WALL_INSET < PEG_R, (
    f"the outer peg's wall inset {PEG_WALL_INSET} is not inside its own "
    "section: the retract's contraction point would leave the hull and the "
    "collapse would stop being a subset map"
)
VEHICLE_LUA_EXTRA += _PEG_RETRACT_LUA.replace(
    "@PEG_RAMP@", repr(PEG_RAMP_SECONDS)
).replace("@PEG_MAXSTEP@", repr(PEG_MAX_STEP_M)).replace(
    "@PEG_SCALE@", repr(PEG_RETRACT_SCALE)
).replace(
    "@PEG_INSET@", repr(PEG_WALL_INSET)
)
assert "@PEG_" not in VEHICLE_LUA_EXTRA, "peg retract splice failed"
assert "M.pachinkoPegRetract" in VEHICLE_LUA_EXTRA


_LUA_BEHAVIOR_SOURCE = r"""
-- =====================================================================
-- Pachinko Tower runtime.
--
-- Phases: idle -> loading -> hoist -> dock -> arming -> tipping ->
--         falling -> payout -> returning -> idle
--
-- Three structural rules, each of which cost a review round:
--
-- 1. b.elapsed is the PHASE clock, and only setPhase and behavior.update
--    may write it. The first cut let the tip ratchet reset it once per
--    detent, which made the tipping timeout AND the TILT fallback - the two
--    safety nets for the one phase that can genuinely hang - permanently
--    unreachable. Every sub-timer below therefore carries its OWN
--    accumulator: tipHold, rapTimer, parkTimer, settleTimer,
--    stuckTimer, idleGrace.
--
-- 2. A phase timeout is a WATCHDOG, not a schedule. Each PHASE_TIMEOUT
--    entry is at least 2x its phase's nominal duration (the arithmetic is
--    beside each tunable in spec.py) and stays reachable the moment that
--    phase stops making progress.
--
-- 3. The machine may be armed by a CROSSING or by OCCUPANCY. Zone triggers
--    only fire on crossings (AGENTS.md), and this machine's own abort paths
--    deposit cars inside load_zone, so the idle branch polls occupancy the
--    way catapult_seesaw's updateParking does.
--
-- Collision bakes, whole cycle: dock(1) + gate open(1) + one endpoint bake
-- at the end of the return(1) = 3, flat. Nothing is baked mid-stroke and
-- NEVER at a pose the car is not already conformally resting on, so no
-- stale collision plate is ever left floating between the deck's stopped
-- poses (home floor, docked crown; the tip flourish draws over the level
-- crown bake with nothing aboard).
-- =====================================================================

-- =====================================================================
-- THE YOKOKU LIGHT RIG (round 6, 2026-08-14).
--
-- Pachinko's defining visual grammar is YOKOKU - the anticipation
-- announcement - and its whole content is COLOUR CODING:
--
--     white / blue  low      "a play is happening"
--     green         medium   "something is about to happen"
--     red           high     "this one could pay"
--     gold          near-certain
--     rainbow       jackpot
--
-- Every tier below is driven from state the machine ALREADY tracks, and
-- this module reads it and writes nothing back. It adds no gameplay
-- state, takes no decision, and touches no tunable: b.phase, b.lift,
-- b.lx / b.lz, b.kicks, b.lastValue and b.conceded are all read-only
-- here. That is deliberate - the machine's behaviour was tuned over many
-- live rounds and a 5 cm change halves its score rate, so the lights are
-- a strict observer of it.
--
-- THREE ENGINE FACTS THIS IS BUILT ON:
--
-- 1. Vehicle-material emissive WAS believed INERT in this pipeline, in
--    every variant anyone had tried (AGENTS.md, centrifuge builds 63-69),
--    and that is why the lamp tubes, head rail, marquee bar and bin
--    fascia that round 5 built are LACQUER with a lit-cell cheat baked
--    into the colour map: they read as lamps at noon and as painted tubes
--    at midnight. RETIRED 2026-08-15 by measurement (spec.py, THE
--    EMISSIVE VERDICT; AGENTS.md, "Round-16/17: the photometric
--    ledger"): the defect was a FOUR-element emissiveFactor, and a
--    three-element one emits fine. These lights stay as they are
--    regardless - emissive self-glows but ILLUMINATES nothing, and every
--    one of these fixtures exists to throw light onto the board, not to
--    look bright itself.
--
--    GENERATED-LUA DRIFT, declared 2026-08-15 (round 17): the BUILT
--    mod/lua/ge/extensions/ericrolph_pachinko_tower/runtime.lua (~609-617)
--    still carries the ORIGINAL, refuted wording of this paragraph - it
--    was not regenerated when this source was corrected, and is not being
--    regenerated now, because another session is active in this tree.
--    Comments only; no executable line differs. Clears on next rebuild.
-- 2. A PointLight AT a panel renders as a DISC at any brightness. The
--    tube lights sit ON their tubes on purpose (a lamp SHOULD pool on the
--    board behind it - that is what a real cabinet does), but the marquee
--    and fascia fixtures stand off their panels, because a disc on a sign
--    is just a disc.
-- 3. Lights stored in state.effects are swept by the framework's
--    cleanupInstallation on prop destruction, unregistration and mission
--    end, exactly like the particle emitters. Nothing else in this file
--    needs a teardown path, and a leaked light would outlive the prop.
--
-- Position is re-asserted whenever the prop's origin moves, because the
-- framework's own effect-transform sweep only knows about EFFECT_SPECS
-- members and these are not among them.
-- =====================================================================
local LIGHT_SPECS = {
--@LIGHT_SPECS@--
}

local Lights = {last = {}, flash = 0, kicks = 0, ready = false}

local function clamp01(v)
  if v < 0 then return 0 end
  if v > 1 then return 1 end
  return v
end

-- Linear blend between two RGB triples. Returns three values rather than a
-- table so no per-frame garbage is produced (this runs 12x a frame).
local function mixRGB(r1, g1, b1, r2, g2, b2, t)
  t = clamp01(t)
  return r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t
end

-- Fully saturated hue, 0..1 around the wheel. Only the jackpot chase and the
-- attract drift use it; everything else names its colours outright, because a
-- named tier colour is the entire point of a yokoku ladder.
local function hueRGB(h)
  h = (h % 1.0) * 6.0
  local i = math.floor(h)
  local f = h - i
  if i == 0 then return 1, f, 0
  elseif i == 1 then return 1 - f, 1, 0
  elseif i == 2 then return 0, 1, f
  elseif i == 3 then return 0, 1 - f, 1
  elseif i == 4 then return f, 0, 1
  else return 1, 0, 1 - f end
end

-- ONE engine write per changed light per frame, and none at all when nothing
-- changed. A breathing sine produces a new float every single frame, and
-- setField is an engine round trip; quantizing to 1/40 is finer than the eye
-- and collapses a 12-light show to a few writes a second at idle.
local function lightWrite(state, spec, r, g, b, bright)
  local light = state.effects[spec.slot]
  if not light then return end
  if bright < 0 then bright = 0 end
  if bright > 6.0 then bright = 6.0 end
  local qr = math.floor(clamp01(r) * 40 + 0.5)
  local qg = math.floor(clamp01(g) * 40 + 0.5)
  local qb = math.floor(clamp01(b) * 40 + 0.5)
  local qv = math.floor(bright * 40 + 0.5)
  local key = ((qr * 41 + qg) * 41 + qb) * 256 + qv
  if Lights.last[spec.slot] == key then return end
  -- THE CACHE RECORDS WHAT WAS WRITTEN, NOT WHAT WAS INTENDED. This used
  -- to store `key` before the pcall and unconditionally of it, so a single
  -- failed setField stranded the fixture at its old colour until the show
  -- happened to ask for a different key - which in idle attract can be
  -- never. Emissive was fixed in round 2 and its two siblings were not;
  -- this is the same defect class, closed here.
  local wrote = pcall(function()
    light:setField("color", 0,
      string.format("%.3f %.3f %.3f 1", qr / 40, qg / 40, qb / 40))
    light:setField("brightness", 0, string.format("%.3f", qv / 40))
  end)
  if wrote then Lights.last[spec.slot] = key end
end

-- Create-once, at fixed prop-local positions. The centrifuge's proven recipe
-- verbatim: loadMode 1, preApply, fields, postApply, registerInMission under a
-- namespaced scene name, non-saveable, and a delete on any failure so a
-- half-built light is never left in the scene tree.
Lights.create = function(state)
  for index = 1, #LIGHT_SPECS do
    local spec = LIGHT_SPECS[index]
    if not state.effects[spec.slot] then
      local light = createObject("PointLight")
      if light then
        local ok = pcall(function()
          light.loadMode = 1
          if type(light.preApply) == "function" then light:preApply() end
          if type(light.setCanSave) == "function" then light:setCanSave(false) end
          light.canSave = false
          light:setField("canSave", 0, "0")
          local p = toWorldPoint(state, spec.pos)
          light:setPosition(vec3(p.x, p.y, p.z))
          light:setField("radius", 0, tostring(spec.radius))
          light:setField("brightness", 0, tostring(spec.brightness))
          light:setField("color", 0, "0.85 0.85 0.95 1")
          -- Twelve shadow-casting lights over a 54 m prop is a frame-rate
          -- bill nobody asked for, and none of these is a key light.
          light:setField("castShadows", 0, "0")
          light:setField("isEnabled", 0, "1")
          if type(light.postApply) == "function" then light:postApply() end
        end)
        local registered = ok and registerInMission(
          light, string.format("%s_p%d_light_%s", PROP_MODEL, state.propId,
                               spec.slot))
        if registered then
          state.effects[spec.slot] = light
        else
          pcall(function() light:delete() end)
        end
      end
    end
  end
  Lights.last = {}
  Lights.flash = 0
  Lights.kicks = 0
  Lights.prevZ = nil
  Lights.phase = nil
  Lights.origin = nil
  Lights.ready = true
end

-- The tier ladder. Returns colour, a global level, an animation mode and the
-- focus height the mode needs. NOTHING here writes to b.
Lights.tier = function(state)
  local b = state.behavior
  local phase = b.phase
  -- TIER 2 AS A CRESCENDO (round 7, 2026-08-14). The one gesture the
  -- reference has that this machine had no window for is the PRE-RELEASE
  -- TEASE. Tier 2 used to be `arming or tipping`, and both are flashes:
  -- arming is a fixed 1.4 s gate sweep and tipping ends the frame the car
  -- crosses the hinge line, which on a good release is well under a second.
  -- Green appeared and was gone.
  --
  -- The window that was already there and unused is DOCK - the 1.6 s the
  -- machine spends letting the car seat at the crown, during which nothing
  -- moves and the lights were still showing boarding white. Starting the
  -- ramp there and running it through arming gives ~3.0 s of visible
  -- escalation: white-blue at the moment of arrival, full tier-2 green at
  -- the instant the gate finishes opening, and a pulse that quickens with
  -- it. It touches no tunable and no phase transition - only which colour
  -- this observer draws for a phase the machine was already in - and it
  -- lands exactly on the existing tier-2 values, so `tipping` continues the
  -- ramp's endpoint below without a step.
  --
  -- Placed ABOVE the ladder rather than edited into it: the branches below
  -- still name dock and arming, and never see them.
  if phase == "dock" or phase == "arming" then
    local ramp
    if phase == "arming" then
      -- Second half: the gate sweep. Ends at 1.0 as `tipping` takes over.
      ramp = 0.5 + 0.5 * clamp01(b.elapsed / B.gate_seconds)
    else
      -- First half: the settle. The car is seating and the machine is
      -- deciding to fire.
      ramp = 0.5 * clamp01(b.elapsed / B.dock_settle_seconds)
    end
    local r, g, bl = mixRGB(0.60, 0.78, 1.00, 0.20, 0.96, 0.38, ramp)
    return r, g, bl, 0.55 + 0.30 * ramp, "build", ramp
  end
  if phase == "loading" or phase == "dock" then
    -- TIER 1, boarding. Cold parlour white-blue: a play exists, nothing has
    -- happened yet.
    return 0.60, 0.78, 1.00, 0.55, "flat", nil
  elseif phase == "hoist" then
    -- TIER 1 rising. The fill tracks the carriage up the tubes, so the board
    -- itself reports the height of the lift.
    local f = clamp01((b.lift or 0) / B.lift_travel)
    return 0.52, 0.74, 1.00, 0.55 + 0.35 * f, "fill", nil
  elseif phase == "arming" or phase == "tipping" then
    -- TIER 2. The gate is opening and the kicker is about to fire: green is
    -- the parlour's "something is about to happen".
    return 0.20, 0.96, 0.38, 0.85, "flat", nil
  elseif phase == "falling" then
    -- TIER 3, and it DEEPENS. The machine already knows the car's height every
    -- frame, so the board burns green at the crown, amber through the pins and
    -- full red by the time the car is over the mouths.
    local top = B.apron_z_hi
    local bottom = B.ridge_band_lo
    local lz = b.lz or top
    local depth = clamp01((top - lz) / (top - bottom))
    local r, g, bl
    if depth < 0.5 then
      r, g, bl = mixRGB(0.20, 0.96, 0.38, 1.00, 0.60, 0.10, depth * 2)
    else
      -- The deep end was 1.00/0.11/0.05 in serial 64 and photographed as warm
      -- TUNGSTEN, not as red: the playfield is ivory (0.925/0.895/0.795), so a
      -- light with any green left in it comes back off that field as amber and
      -- the bottom of the ladder stopped being a different colour from the
      -- middle of it. Nearly monochromatic red is what survives the bounce.
      r, g, bl = mixRGB(1.00, 0.60, 0.10, 1.00, 0.055, 0.02, (depth - 0.5) * 2)
    end
    -- ...and it has to arrive BRIGHTER as well as redder, or "deep in the
    -- board" reads as the machine winding down instead of winding up.
    local level = 0.72 + 0.38 * depth
    -- TIER 4. The centre bin is the jackpot and its mouth is choked to 2.60 m,
    -- so a car lined up on it low down is the machine's own "this one could
    -- pay". Gold fades IN over the last 9 m of fall rather than switching, so
    -- it reads as a promise rather than a result.
    local centre = B.bin_centers[3] or 0
    if b.lx and math.abs(b.lx - centre) <= B.bin_pitch * 0.75 then
      local gold = clamp01(((B.ridge_band_hi + 9.0) - lz) / 9.0)
      r, g, bl = mixRGB(r, g, bl, 1.00, 0.78, 0.20, gold)
      level = level + 0.22 * gold
    end
    return r, g, bl, level, "track", lz
  elseif phase == "payout" then
    local value = b.lastValue or 0
    local hold = clamp01(1 - b.elapsed / B.score_hold_seconds)
    if b.conceded then
      -- THE CONCESSION. The machine has decided it has lost, and the lights
      -- have to lose with it - a cut to black reads as a crash, a SLUMP reads
      -- as giving up. Red drains to a cold dead grey-blue and the run dims
      -- from the top down (see the "slump" mode below).
      local s = clamp01(1 - b.elapsed / (B.score_hold_seconds * 0.85))
      local r, g, bl = mixRGB(0.16, 0.17, 0.26, 1.00, 0.28, 0.10, s)
      -- The floor is 0.22 and not 0.09 for the same reason the slump weight
      -- has one: measured off the serial-64 capture, the run bottomed out at
      -- brightness 0.02, which renders as pure black. A conceding machine
      -- should look BEATEN, not switched off.
      return r, g, bl, 0.22 + 0.52 * s * s, "slump", nil
    elseif value >= 10000 then
      -- TIER 5. The only full rainbow the machine ever runs, and it runs it
      -- for one bin.
      return 1, 1, 1, 1.00, "chase", nil
    elseif value > 0 then
      -- A real win, but not THE win: gold for the big bins, warm white for the
      -- small ones, both pulsing and both decaying with the payout hold.
      local pulse = 0.5 + 0.5 * math.sin(b.clock * 8.0)
      local r, g, bl = 1.00, 0.80, 0.26
      if value < 1000 then r, g, bl = 1.00, 0.93, 0.74 end
      return r, g, bl, (0.55 + 0.45 * pulse) * (0.45 + 0.55 * hold), "flat", nil
    end
    -- Scored nothing and did not concede (gutter, off the board, timed out):
    -- no colour is a claim. Cold and low.
    return 0.52, 0.58, 0.72, 0.26, "flat", nil
  end
  -- TIER 0, idle and returning: the attract cycle. Slow, pastel and vintage -
  -- a cabinet breathing in an empty parlour, not a machine advertising.
  -- Serial 63 mixed these 56% toward white and the idle machine photographed
  -- as plain warm floodlight - a pastel that desaturated has no hue left to
  -- read at all, and TIER 0 has to be visibly a colour or the ladder starts at
  -- tier 1. 38% white keeps it soft and vintage while the hue survives.
  local pr, pg, pb = hueRGB((b.clock * 0.030) % 1.0)
  return 0.38 + 0.62 * pr, 0.38 + 0.62 * pg, 0.38 + 0.62 * pb, 0.32, "breathe", nil
end

Lights.update = function(state, dtSim)
  if not Lights.ready then return end
  local b = state.behavior
  -- The framework's transform sweep only re-poses EFFECT_SPECS members, so a
  -- placed prop that ever moves would leave its lights behind. Cheap to fix
  -- and a real defect if it is not.
  local origin = state.origin
  if origin and (not Lights.origin
      or (origin - Lights.origin):length() > 0.01) then
    Lights.origin = vec3(origin.x, origin.y, origin.z)
    for index = 1, #LIGHT_SPECS do
      local spec = LIGHT_SPECS[index]
      local light = state.effects[spec.slot]
      if light then
        local p = toWorldPoint(state, spec.pos)
        pcall(function() light:setPosition(vec3(p.x, p.y, p.z)) end)
      end
    end
  end
  -- ---- IMPACT-FRAME SYNC ---------------------------------------------
  -- The single most recognisable gesture in pachinko lighting: a white
  -- strobe on the frame something is HIT. Both triggers are derived from
  -- state the machine already keeps, so not one line of tuned code had to
  -- be touched to get frame accuracy - b.kicks increments in the same
  -- frame the kicker impulse is applied, and the fall sample is this
  -- frame's.
  local kicks = b.kicks or 0
  if kicks > Lights.kicks then Lights.flash = 1.0 end
  Lights.kicks = kicks
  local phase = b.phase
  if phase == "falling" and b.lz and Lights.prevZ
      and Lights.prevZ >= B.ridge_band_lo and b.lz < B.ridge_band_lo then
    -- The car has dropped past the bin mouths: contact with the pocket.
    Lights.flash = 1.0
  end
  Lights.prevZ = (phase == "falling") and b.lz or nil
  if phase == "payout" and Lights.phase ~= "payout"
      and (b.lastValue or 0) > 0 then
    Lights.flash = 1.0
  end
  Lights.phase = phase
  -- dtSim runs ~3x wall on this engine (AGENTS.md), so 2.6 per sim-second is
  -- roughly a 0.13 s wall strobe - one blink, not a flicker.
  Lights.flash = math.max(0, Lights.flash - dtSim * 2.6)

  local r, g, bl, level, mode, focus = Lights.tier(state)
  local deckZ = B.deck_home_z + (b.lift or 0)
  local flash = Lights.flash
  for index = 1, #LIGHT_SPECS do
    local spec = LIGHT_SPECS[index]
    local lr, lg, lb, weight = r, g, bl, 1.0
    if mode == "breathe" then
      -- A slow wave travelling up the run, so the idle machine looks alive
      -- without looking busy.
      weight = 0.42 + 0.58
        * (0.5 + 0.5 * math.sin(b.clock * 0.5 - spec.z * 0.055))
    elseif mode == "fill" then
      -- Lit below the carriage, dark above it: the board IS the lift gauge.
      weight = 0.26 + 0.74 * clamp01((deckZ - spec.z) / 9.0 + 0.5)
    elseif mode == "track" and focus then
      -- The segment the car is passing burns brightest.
      weight = 0.24 + 0.76 * clamp01(1 - math.abs(spec.z - focus) / 15.0)
    elseif mode == "build" and focus then
      -- The pre-release tease. `focus` is the 0..1 crescendo ramp, and it
      -- drives the PULSE RATE as well as the colour: 3 Hz as the car seats,
      -- 12 Hz as the gate finishes. A tier that only brightens reads as a
      -- dimmer being turned up; a tier that quickens reads as a machine
      -- making up its mind. The z term walks the pulse up the run so the
      -- whole 46 m of tube is visibly one wave rather than twelve lamps.
      weight = 0.55 + 0.45
        * (0.5 + 0.5 * math.sin(b.clock * (3.0 + 9.0 * focus) - spec.z * 0.030))
    elseif mode == "chase" then
      lr, lg, lb = hueRGB(b.clock * 0.5 + spec.chase)
      weight = 0.72 + 0.28
        * (0.5 + 0.5 * math.sin(b.clock * 6.0 + spec.chase * 6.2832))
    elseif mode == "slump" then
      -- Dies from the crown DOWN over the payout hold, which is the direction
      -- a machine that has run out of ideas should go dark in. Calibrated so
      -- the marquee (z 48.25) is already fading on the first frame of the
      -- concession and the fascia (z 7.0) is the last thing left burning as
      -- the hold ends - not "all off", which reads as a crash rather than a
      -- surrender.
      -- ...to a cold EMBER, not to nothing: serial 64 slumped the whole run to
      -- brightness 0.00-0.02, which photographs as the mod having crashed
      -- rather than as the machine conceding. The 0.12 floor keeps a dim blue
      -- pilot glow on the fascia and the tube feet.
      weight = 0.12 + 0.88 * clamp01(1.6 - spec.z / 36.0
        - b.elapsed / (B.score_hold_seconds * 0.75))
    end
    local bright = spec.brightness * level * weight
    if flash > 0.001 then
      lr = lr + (1 - lr) * flash
      lg = lg + (1 - lg) * flash
      lb = lb + (1 - lb) * flash
      bright = bright + spec.brightness * 1.5 * flash
    end
    lightWrite(state, spec, lr, lg, lb, bright)
  end
end


-- =====================================================================
-- THE SHOW (round 9, 2026-08-15): a drift-free musical clock, a four-mode
-- state machine, eleven directional fixtures and fifteen driven surfaces.
--
-- Same contract as the light rig and the soundtrack above: this is an
-- OBSERVER. It reads b.phase, b.lx, b.lz, b.lift, b.kicks, b.lastValue,
-- b.conceded and b.elapsed, and it writes nothing back. No tuned constant is
-- touched, no phase transition is taken, no gameplay state is added.
--
-- ---------------------------------------------------------------------
-- WHY THE CLOCK IS dtReal AND NOT dtSim
-- ---------------------------------------------------------------------
-- `Engine.Audio` exposes NO playback position anywhere in the GE tree - the
-- surface is playOnce / createSource / createSource2 / deleteSource /
-- get+setChannelVolume / getGlobalParams / getInfo / getCanUseHardware /
-- createAudioDevice / intercomPlay+StopPacenote. So a show cannot be
-- synchronised CLOSED-LOOP against the audio; it can only run OPEN-LOOP from
-- the instant a cue was triggered. That makes the choice of clock decisive
-- rather than stylistic.
--
-- dtSim is scaled by simTimeAuthority. Slow motion, bullet time and pause are
-- all bound to player keys, and in a giant-prop sandbox they are used
-- constantly. FMOD plays at wall rate regardless. A musical timeline on dtSim
-- therefore desynchronises WITHOUT BOUND the moment anyone touches the time
-- scale - not by a tolerable amount, by an unbounded one, because the error is
-- an integral of a scale factor the player controls.
--
-- proplib now passes both (lua_kit.py, onPreRender already received dtReal and
-- simply never forwarded it). So:
--
--     MUSICAL / CHOREOGRAPHIC timing  -> dtReal   (this module)
--     PHYSICS-COUPLED effects         -> dtSim    (the impact strobe, which
--                                                  must land on the frame the
--                                                  kicker fires, whatever the
--                                                  time scale is doing)
--
-- DRIFT-FREE BY CONSTRUCTION, not by tuning. There is exactly ONE accumulator
-- in this module, Show.clock, and every musical quantity is DERIVED from it by
-- division. Nothing counts beats by adding a beat. A derived index cannot
-- accumulate error: the only error is the float resolution of a single sum,
-- which at 1/60 s increments stays exact in a double for far longer than any
-- session.
-- ---------------------------------------------------------------------
local SPOT_SPECS = {
--@SPOT_SPECS@--
}

local EMISSIVE_SPECS = {
--@EMISSIVE_SPECS@--
}

--@SHOW_CONSTANTS@--

local SHOW_BPM = 132.0
local SHOW_BEAT = 60.0 / SHOW_BPM              -- 0.4545... s
local SHOW_SUBDIV = 4                          -- the show quantises to 1/4 beat
local SHOW_TICK = SHOW_BEAT / SHOW_SUBDIV      -- 0.11363... s

local Show = {
  clock = 0.0,        -- THE one accumulator. dtReal seconds since init.
  simClock = 0.0,     -- its dtSim twin, kept ONLY so drift can be measured.
  frames = 0,
  mode = "attract",
  modeClock = 0.0,
  lastStep = -1,
  lastEmit = -32,
  maxSkip = 0,
  ready = false,
}

-- Derived, never accumulated. This is the whole drift argument.
local function showBeat() return Show.clock / SHOW_BEAT end
local function showStep() return math.floor(Show.clock / SHOW_TICK) end

-- 0..1 within the current quarter-beat, for anything that wants to swing
-- rather than snap.
local function showPhase() return (Show.clock % SHOW_TICK) / SHOW_TICK end

-- ---------------------------------------------------------------------
-- THE FOUR MODES. The commission names Attract / Normal Play / Reach /
-- Fever-Jackpot. This machine already has a nine-phase tuned state machine
-- that must not be touched, so the modes are DERIVED from it rather than
-- added to it - one pure function of state the machine already keeps.
--
-- REACH is the interesting one, because "reach" in a real machine means the
-- outcome is still open but the machine has shown you it might pay. This
-- machine has two such windows and they are both already on the record: the
-- dock/arming/tipping crescendo (the release is coming), and a fall whose x
-- is lined up on the jackpot mouth (this one could pay). The second is the
-- true reach, and the tier ladder above already fades gold into it.
-- ---------------------------------------------------------------------
local function showModeFor(b)
  local phase = b.phase
  if phase == "payout" then
    if (b.lastValue or 0) >= 10000 then return "fever" end
    return "play"
  end
  if phase == "falling" then
    local centre = B.bin_centers[3] or 0
    if b.lx and math.abs(b.lx - centre) <= B.bin_pitch * 0.75 then
      return "reach"
    end
    return "play"
  end
  if phase == "dock" or phase == "arming" or phase == "tipping" then
    return "reach"
  end
  if phase == "idle" or phase == "returning" then return "attract" end
  return "play"
end

-- Per-mode show parameters. `rate` is in BEATS, so every one of them is
-- quantised to the same grid and the machine never looks like two shows
-- running at once.
-- LEVELS BRACKET THE NOMINAL, THEY DO NOT SCALE IT AWAY. The first cut used
-- attract level 0.55 with depth 0.45, which put an 1800-nit marquee at 545 nit
-- at NOON - measured territory for "reads as lighter paint" (+11.9 sRGB over
-- control at 180 nit) rather than for a lit sign. The authored value is the
-- surface's nominal; a mode rides around it. Read the pairs as (trough, peak)
-- fractions of nominal: attract 0.752-0.80, play 0.911-0.99, reach
-- 1.091-1.213, fever 1.276-1.45.
--
-- THOSE ARE surfaceDepth NUMBERS AND THEY USED TO BE depth NUMBERS. Until
-- round 3 this comment quoted 0.52-0.80 / 0.65-0.99 / 0.24-1.21 / 0.00-1.45,
-- computed from `depth` - the LIGHT depth - and left over from before the
-- surfaces and the lights were split onto separate depths. It told a reader
-- that fever still drives a MATERIAL to a 0.00 trough, which was the exact
-- defect round 2 fixed. A stale comment about a fixed defect is how the
-- defect gets re-introduced.
--
-- FEVER'S OVERDRIVE IS REAL BY DAY AND NEARLY ABSENT AT NIGHT, and that is the
-- measurement talking, not a compromise. The night band tops out at the 320-nit
-- rung, so a 320-nit tube has NO headroom left and fever has to be carried by
-- COLOUR and RATE - which is what chaseBeats 0.5 and the strobes' hard
-- quarter-beat gate are for.
-- `depth` is the LIGHT depth. `surfaceDepth` is what a driven MATERIAL is
-- allowed to move by, and it is an order of magnitude smaller because a
-- surface write costs 1.5-4.0 ms and a light write does not. Spliced from
-- spec.py, which asserts the resulting write demand against the cap.
local SHOW_MODES = {
--@SHOW_MODES@--
}

-- =====================================================================
-- THE DIRECTIONAL FIXTURES. Three centre strobes on the marquee soffit and
-- one spotlight per peg row, alternating sides so consecutive rows are lit
-- from opposite edges.
--
-- Created by the centrifuge's proven recipe, identical to the twelve
-- PointLights above: loadMode 1, preApply, setCanSave(false), fields,
-- postApply, registerInMission under a namespaced name, and a delete on any
-- failure so a half-built light never survives in the scene tree. They live
-- in state.effects, so the framework's cleanupInstallation sweeps them on
-- every teardown path there is.
--
-- PHOTOMETRY: `brightness` here is already the converted value - candela
-- divided by the measured 5000 cd == brightness 1.0 law, done in spec.py at
-- the ONE conversion boundary. 8500 cd -> 1.70, 1200 cd -> 0.24. The Kelvin
-- targets are set as Kelvin through useColorTemperature rather than mixed
-- into an RGB triple, because that field exists and is what it is for.
-- =====================================================================
local Spots = {last = {}, ready = false, origin = nil}

Spots.create = function(state)
  for index = 1, #SPOT_SPECS do
    local spec = SPOT_SPECS[index]
    if not state.effects[spec.slot] then
      local light = createObject("SpotLight")
      if light then
        local ok = pcall(function()
          light.loadMode = 1
          if type(light.preApply) == "function" then light:preApply() end
          if type(light.setCanSave) == "function" then light:setCanSave(false) end
          light.canSave = false
          light:setField("canSave", 0, "0")
          local p = toWorldPoint(state, spec.pos)
          local d = toWorldDir(state, spec.dir)
          local q = quatFromDir(d, vec3(0, 0, 1))
          light:setPosRot(p.x, p.y, p.z, q.x, q.y, q.z, q.w)
          light:setField("range", 0, tostring(spec.range))
          light:setField("innerAngle", 0, tostring(spec.inner))
          light:setField("outerAngle", 0, tostring(spec.outer))
          light:setField("brightness", 0, tostring(spec.brightness))
          light:setField("color", 0, "1 1 1 1")
          light:setField("useColorTemperature", 0, "1")
          light:setField("colorTemperatureKelvin", 0, tostring(spec.kelvin))
          -- Eleven more shadow casters over a 54 m prop is a frame-rate bill
          -- nobody asked for, and none of these is a key light. Same call the
          -- twelve PointLights make, for the same reason.
          light:setField("castShadows", 0, "0")
          light:setField("isEnabled", 0, "1")
          if type(light.postApply) == "function" then light:postApply() end
        end)
        local registered = ok and registerInMission(
          light, string.format("%s_p%d_spot_%s", PROP_MODEL, state.propId,
                               spec.slot))
        if registered then
          state.effects[spec.slot] = light
        else
          pcall(function() light:delete() end)
        end
      end
    end
  end
  Spots.last = {}
  Spots.origin = nil
  Spots.ready = true
end

-- ONE engine write per changed fixture per frame, and none when nothing
-- changed. A SpotLight takes setField WITHOUT postApply - the twelve
-- PointLights on this machine have written colour and brightness that way
-- across five rounds of captures - so this is the CHEAP mechanism and it is
-- what carries every instantaneous gesture. Quantised to 1/40 exactly like
-- the PointLight rig, for exactly the same reason.
local function spotWrite(state, spec, bright)
  local light = state.effects[spec.slot]
  if not light then return end
  if bright < 0 then bright = 0 end
  if bright > 6.0 then bright = 6.0 end
  local q = math.floor(bright * 40 + 0.5)
  if Spots.last[spec.slot] == q then return end
  -- Cache on success only. See the note in lightWrite: a spot stranded by
  -- one failed setField is a letter that drops out of the chase, and the
  -- chase is the thing this whole rig exists to do.
  local wrote = pcall(function()
    light:setField("brightness", 0, string.format("%.3f", q / 40))
  end)
  if wrote then Spots.last[spec.slot] = q end
end

Spots.update = function(state, mode, flash)
  if not Spots.ready then return end
  local b = state.behavior
  local params = SHOW_MODES[mode] or SHOW_MODES.attract
  -- Re-pose on any prop move, same as the PointLights: the framework's
  -- transform sweep only knows about EFFECT_SPECS members and these are not
  -- among them.
  local origin = state.origin
  if origin and (not Spots.origin
      or (origin - Spots.origin):length() > 0.01) then
    Spots.origin = vec3(origin.x, origin.y, origin.z)
    for index = 1, #SPOT_SPECS do
      local spec = SPOT_SPECS[index]
      local light = state.effects[spec.slot]
      if light then
        pcall(function()
          local p = toWorldPoint(state, spec.pos)
          local d = toWorldDir(state, spec.dir)
          local q = quatFromDir(d, vec3(0, 0, 1))
          light:setPosRot(p.x, p.y, p.z, q.x, q.y, q.z, q.w)
        end)
      end
    end
  end

  local beat = showBeat()
  for index = 1, #SPOT_SPECS do
    local spec = SPOT_SPECS[index]
    local weight
    if spec.row >= 0 then
      -- PEG SPOTLIGHTS. In play they track the car down the board, so the row
      -- the car is passing is the row that burns; otherwise they run the
      -- musical chase down the field.
      if b.phase == "falling" and b.lz then
        local rowZ = spec.rowz
        weight = 0.20 + 0.80 * clamp01(1 - math.abs(rowZ - b.lz) / 12.0)
      else
        local wave = (beat / params.chaseBeats + spec.chase) % 1.0
        weight = (1.0 - params.depth) + params.depth
          * (0.5 + 0.5 * math.cos(wave * 6.2831853))
      end
    elseif spec.letter >= 0 then
      -- LETTER FLOODS. THE CHASE. One flood per plate, phase-offset up the
      -- stack, so P-A-C-H-I-N-K-O fills from the bottom. This is the wave that
      -- used to be attempted on the plate MATERIALS at 1.5-4.0 ms a write
      -- against a 7.5 Hz ceiling; here it is a setField and it can run at the
      -- frame rate, so reach (2.2 Hz) and fever (4.4 Hz) are finally sampled
      -- far above Nyquist rather than under it.
      local wave = (beat / params.chaseBeats + spec.chase) % 1.0
      -- Sharper than a cosine: a chase should have a defined head, not a
      -- sinusoidal smear across all eight plates at once. ^3 keeps one plate
      -- clearly the peak and its neighbours clearly behind it.
      local bell = (0.5 + 0.5 * math.cos(wave * 6.2831853)) ^ 3
      -- THE LETTERS RUN THEIR OWN DEPTH. `params.depth` is the FIELD
      -- lighting's, and at attract's 0.35 it left the sign moving 6-7% -
      -- measured, from the frames. The vertical sign is the one fixture on
      -- this machine whose entire job is to chase, so it always chases hard;
      -- the mode still sets the RATE, which is what a mode should set.
      local d = math.max(params.depth, LETTER_CHASE_DEPTH)
      weight = (1.0 - d) + d * bell
    else
      -- CENTRE STROBES. These are the marquee's own, and they are the one
      -- fixture class that is allowed to be violent: a hard 1/4-beat gate in
      -- fever, a slow swell in attract.
      --
      -- HOW BIG THE ROUND-2 SPOTLIGHT FIX ACTUALLY WAS, stated honestly
      -- because "not cosmetic" was left unqualified and it is only true in
      -- half the show. `row` was omitted from the spliced table while this
      -- branch tested it, so every peg spot fell through to the strobe
      -- waveform. That IS a real behavioural bug and the three branches are
      -- genuinely different functions - car-altitude tracking, a cubed bell,
      -- and a binary fever gate. But OUTSIDE `falling` and outside `fever`
      -- the peg branch and this one differ only by `depth` against
      -- `0.7 * depth`: in attract that is 0.35 against 0.245, about a 10%
      -- amplitude difference nobody would see. The visually significant part
      -- of the fix fires during PLAY and FEVER, and only then.
      if mode == "fever" then
        weight = ((showStep() + index) % 2 == 0) and 1.0 or 0.10
      else
        local wave = (beat / params.chaseBeats + spec.chase) % 1.0
        weight = (1.0 - params.depth * 0.7) + params.depth * 0.7
          * (0.5 + 0.5 * math.cos(wave * 6.2831853))
      end
    end
    local bright = spec.brightness * params.level * weight
    -- The impact-frame strobe. Shares the light rig's own `flash`, computed
    -- from b.kicks and the bin-mouth crossing on dtSim, so a physics event
    -- lands on its own frame whatever the show clock is doing.
    if flash > 0.001 then
      bright = bright + spec.brightness * 1.2 * flash
    end
    spotWrite(state, spec, bright)
  end
end

-- =====================================================================
-- THE DRIVEN SURFACES, and the budget that measurement forces on them.
--
-- PROBED IN GAME 2026-08-15 (see THE PHOTOMETRIC FIXTURE SCHEDULE in
-- spec.py for the full result and its method):
--
--   scenetree.findObject(<materialName>) returns class "material".
--   setField ALONE DOES NOT REACH THE RENDERER - the field takes the value
--     and the pixel does not move.
--   setField + postApply() DOES - four cells told "60" landed on an
--     untouched 60-nit reference cell at 0.0 sRGB deviation, same frame.
--   setField costs ~0.55 us. setField + postApply costs 1.5 - 4.0 ms.
--
-- Three orders of magnitude. So a surface CANNOT be driven every frame, and
-- this module is built around that fact rather than apologising for it:
--
--   * targets are computed for every surface every frame (that is free),
--   * a surface is only QUEUED when its quantised target actually changes,
--   * at most EMISSIVE_WRITE_BUDGET writes are committed per frame,
--   * the cursor is round-robin, so no surface can starve and a burst
--     propagates as a sweep rather than as a dropped frame.
--
-- The result is that a chase is what it physically is on this engine - a
-- low-rate discrete event stream - and everything that has to be
-- instantaneous lives in the lights instead, where it costs nothing.
-- =====================================================================
local Emissive = {
  mats = {},
  last = {},
  target = {},
  -- The blended day/night nominal for each surface THIS FRAME. The
  -- quantiser bands against it, because banding against the DAY
  -- target gave the night band a 75-nit step - about three usable
  -- levels across 60-320, which is not a chase.
  nominal = {},
  cursor = 1,
  writes = 0,
  queued = 0,
  ready = false,
}

Emissive.create = function(state)
  Emissive.mats = {}
  Emissive.last = {}
  Emissive.target = {}
  Emissive.nominal = {}
  Emissive.cursor = 1
  Emissive.writes = 0
  local found = 0
  for index = 1, #EMISSIVE_SPECS do
    local spec = EMISSIVE_SPECS[index]
    local m = nil
    pcall(function() m = scenetree.findObject(spec.mat) end)
    if m then
      Emissive.mats[spec.slot] = m
      found = found + 1
    end
  end
  Emissive.ready = found > 0
  emitEvent(state, "I", "emissive_bound", {
    found = found, total = #EMISSIVE_SPECS,
  })
end

-- ---------------------------------------------------------------------
-- THE TIME-OF-DAY SCHEDULE, and why there has to be one.
--
-- MEASURED: the usable NIGHT band is ~60-400 nit and the usable NOON band is
-- ~1500-15000. THEY DO NOT OVERLAP. The same 1800-nit surface is a mid-grey
-- panel at noon (sRGB 95) and a fully clipped white blob at midnight. So
-- there is NO static nits value that works at both times, and the only way to
-- serve both is to drive it - which is exactly what the keystone probe
-- licenses and what this function exists to do.
--
-- `time` is 0 at midday and 0.5 at midnight (the calibration captures set
-- 0.00 for day and 0.50 for night and got day and night). A raised cosine
-- gives 1 at noon and 0 at midnight with smooth shoulders through dawn and
-- dusk, which is what the exposure is doing anyway.
-- ---------------------------------------------------------------------
local function daylightFraction()
  local t = nil
  pcall(function()
    local tod = core_environment and core_environment.getTimeOfDay()
    if tod and tod.time then t = tod.time end
  end)
  -- No environment module (a bare level, a headless harness): assume day,
  -- which is the condition a surface authored at its day target already suits.
  if not t then return 1.0 end
  return 0.5 + 0.5 * math.cos(t * 6.2831853)
end

Emissive.update = function(state, mode, flash)
  if not Emissive.ready then return end
  local b = state.behavior
  local params = SHOW_MODES[mode] or SHOW_MODES.attract
  local day = daylightFraction()
  -- Smoothstep so dawn and dusk are not a linear ramp through the middle of
  -- two bands that do not overlap.
  local blend = day * day * (3.0 - 2.0 * day)
  local beat = showBeat()

  -- 1. TARGETS. Free - no engine call in this loop.
  --
  -- STRUCTURAL ONLY. No chase phase and no flash term: both are high-rate
  -- signals and both now live on the lights, where a write is a setField
  -- rather than a 1.5-4.0 ms postApply. What is left is what a big lit sign
  -- actually does - it sits at the level its mode calls for and breathes,
  -- slowly, all of it together.
  -- DE-PHASED ACROSS THE SET. One common breathe puts all sixteen surfaces
  -- across a quantiser step within the same few frames, so a demand that
  -- averages comfortably under the cap would still arrive in bursts that
  -- momentarily saturate it. A fixed per-surface offset spreads the same
  -- number of writes evenly over the cycle - and it stops the machine pulsing
  -- as one slab, which is not what a wall of separate lit plates does.
  local n = #EMISSIVE_SPECS
  local phase = Show.clock * SURFACE_BREATHE_HZ
  for index = 1, n do
    local spec = EMISSIVE_SPECS[index]
    local breathe = 0.5 + 0.5 * math.cos(
      (phase + (index - 1) / n) * 6.2831853)
    local weight = (1.0 - params.surfaceDepth) + params.surfaceDepth * breathe
    local nominal = spec.night + (spec.day - spec.night) * blend
    local nits = nominal * params.level * weight * params.gain
    -- THE NIGHT CEILING IS A HARD CLAMP, and it is the honest consequence of
    -- the measurement. Saturation begins somewhere in the open interval
    -- (400, 550] and nothing inside it has ever been measured, so the show is
    -- not allowed to wander in there looking for headroom. At night FEVER is
    -- therefore carried by COLOUR and RATE, not by level - which is not a
    -- compromise, it is what the band says is available.
    -- BOTH ENDS. Round 1 clamped only the ceiling, so the schedule's
    -- "every surface sits in 60-320 nit" assert described the AUTHORED
    -- nominal while the runtime drove night troughs to 57.0 / 26.6 / 1.0.
    -- spec.py now asserts that the floor never fires; it is here as a guard,
    -- not as a shaper.
    local ceiling, floor
    if blend < 0.5 then
      ceiling, floor = EMISSIVE_NIGHT_PEAK, EMISSIVE_NIGHT_FLOOR
    else
      ceiling, floor = EMISSIVE_DAY_PEAK, EMISSIVE_DAY_FLOOR
    end
    if nits > ceiling then nits = ceiling end
    if nits < floor then nits = floor end
    Emissive.target[spec.slot] = nits
    -- THE SPAN THE QUANTISER BANDS AGAINST IS THE REGIME'S, NOT THE
    -- INSTANT'S, and round 3 is where that stopped being a detail.
    --
    -- Round 2 fixed a stranding bug by making `Emissive.last` hold the
    -- WRITTEN STRING instead of the quantiser index. That was right - an
    -- index is scale-invariant and aliased day onto night - but it had an
    -- uncounted consequence. `nominal` above is recomputed EVERY FRAME
    -- from core_environment.getTimeOfDay(), so if the step is derived from
    -- it, the formatted string moves every frame that the sun moves, and
    -- every surface asks for a write on every frame of dawn and of dusk.
    -- playfield_edge alone travels 320 -> 3500 nit across one dawn at
    -- %.1f resolution. The round-robin bounds the COST at 2 writes a frame,
    -- so this could never have blown the frame budget - but a permanently
    -- pinned queue is exactly the failure this file blames round 1 for, and
    -- a bounded defect is still a defect.
    --
    -- Banding against the REGIME nominal keeps everything the round-2 fix
    -- bought and gives none of it back: the step is still the surface's own
    -- (a 3500-nit tube and a 1200-nit plate get different steps), it is
    -- still different at night than by day (so the written strings cannot
    -- alias across the bands, which is what stranded them), and it is now
    -- CONSTANT while the sun moves, so a slow ramp writes only when it
    -- genuinely crosses a step. See EMISSIVE_TOD_DEMAND in spec.py for the
    -- residual rate and the minimum day length it implies.
    Emissive.nominal[spec.slot] =
      (blend < 0.5) and spec.night or spec.day
  end

  -- 2. QUEUE + COMMIT. Round-robin from the cursor, hard-capped.
  local budget = EMISSIVE_WRITE_BUDGET
  local n = #EMISSIVE_SPECS
  local examined = 0
  while budget > 0 and examined < n do
    local spec = EMISSIVE_SPECS[Emissive.cursor]
    Emissive.cursor = Emissive.cursor + 1
    if Emissive.cursor > n then Emissive.cursor = 1 end
    examined = examined + 1
    local want = Emissive.target[spec.slot]
    if want then
      -- Quantise against the surface's own REGIME nominal, so a 3500-nit
      -- tube and a 1200-nit plate both get EMISSIVE_QUANT_STEPS meaningful
      -- steps - and so does the SAME surface at midnight, whose whole band is
      -- 60-320 nit. Banding against the DAY target instead (the first cut of
      -- this) gave every letter a 75-nit step and the live capture read all
      -- eight of them stuck on exactly "75"; banding against the LIVE
      -- blended nominal (round 2) wrote every surface every frame of dawn.
      local span = math.max(1.0, Emissive.nominal[spec.slot] or spec.day)
      local step = span / EMISSIVE_QUANT_STEPS
      local q = math.floor(want / step + 0.5)
      -- q FLOORS TO ZERO and the quantiser then writes a literal "0.0",
      -- underneath the clamp that was supposed to stop exactly that. One
      -- step is the darkest a driven surface is allowed to be.
      if q < 1 then q = 1 end
      -- THE STRANDING BUG. `last` used to hold q, and q is an index into a
      -- band whose WIDTH is the surface's current nominal - so the same index
      -- means 1425 nit by day and 130 nit at night. A surface whose day index
      -- equalled its night index was judged unchanged and never rewritten:
      -- measured at midnight, sign_letter_1 and sign_letter_2 sat on the DAY
      -- quantum of 1425 nit beside six siblings at 123.5. `last` holds the
      -- STRING THAT WAS WRITTEN now, which is the renderer's real state and
      -- has no band to alias inside.
      local text = string.format("%.1f", q * step)
      if Emissive.last[spec.slot] ~= text then
        local m = Emissive.mats[spec.slot]
        if m then
          local wrote = pcall(function()
            m:setField("emissiveIntensityNits", 0, text)
            -- MANDATORY. Measured: without this the field takes the value and
            -- the rendered pixel does not move. This single call is the
            -- 1.5-4.0 ms, and it is the entire reason for the budget above.
            m:postApply()
          end)
          if wrote then
            Emissive.last[spec.slot] = text
            Emissive.writes = Emissive.writes + 1
            budget = budget - 1
          end
        end
      end
    end
  end
end

-- =====================================================================
-- THE SHOW'S OWN UPDATE. Called once per frame with BOTH clocks.
-- =====================================================================
Show.begin = function(state)
  Show.clock = 0.0
  Show.simClock = 0.0
  Show.frames = 0
  Show.mode = "attract"
  Show.modeClock = 0.0
  Show.lastStep = -1
  Show.lastEmit = -32
  Show.maxSkip = 0
  Show.ready = true
  Spots.create(state)
  Emissive.create(state)
end

Show.update = function(state, dtSim, dtReal)
  if not Show.ready then return end
  local b = state.behavior
  -- THE ONE ACCUMULATOR. Everything musical is derived from it.
  Show.clock = Show.clock + (dtReal or 0)
  -- Its dtSim twin exists only so the divergence can be MEASURED rather than
  -- asserted; nothing reads it but the telemetry below.
  Show.simClock = Show.simClock + (dtSim or 0)
  Show.frames = Show.frames + 1

  local mode = showModeFor(b)
  if mode ~= Show.mode then
    Show.mode = mode
    Show.modeClock = Show.clock
    emitEvent(state, "I", "show_mode", {
      mode = mode,
      phase = b.phase,
      beat = showBeat(),
      clock_real = Show.clock,
      clock_sim = Show.simClock,
    })
  end

  -- The quarter-beat tick. Published so a capture harness can measure DRIFT
  -- against wall time without instrumenting the mod: one event per 32 ticks
  -- is ~3.6 s of log at 132 BPM, which is cheap and long enough to fit.
  local stepNow = showStep()
  if stepNow ~= Show.lastStep then
    local skipped = stepNow - Show.lastStep - 1
    Show.lastStep = stepNow
    -- SURVIVORSHIP BIAS, fixed. This used to fire on `stepNow % 32 == 0`,
    -- which means a frame hitch that jumped the index PAST a multiple of 32
    -- dropped that sample silently - so the run least likely to be recorded
    -- was the run with the worst drift, which is the only run the telemetry
    -- exists for. It fires now when at least 32 steps have elapsed since the
    -- last sample, which no hitch can skip, and it carries the number of
    -- steps the hitch swallowed.
    if stepNow - Show.lastEmit >= 32 then
      Show.lastEmit = stepNow
      Show.maxSkip = math.max(Show.maxSkip or 0, skipped)
      -- WINDOWED, and the cumulative figure is kept beside it rather
      -- than replaced. `Emissive.writes / Show.clock` is a LIFETIME
      -- AVERAGE: both terms count from the moment the show began, so
      -- what it reports is the mean rate over the whole session and not
      -- the rate of the mode being measured. That is why five rounds of
      -- [PERF] read a near-flat 5.29-5.66 writes/s across four modes
      -- whose modelled demand differs by 3.6x, and it is why the model
      -- and the measurement appeared to disagree about the SHAPE. They
      -- were not measuring the same thing. This one divides the writes
      -- since the last emit by the seconds since the last emit, which is
      -- an instantaneous rate and is what the model predicts.
      local windowClock = Show.clock - (Show.lastEmitClock or 0)
      local windowWrites = Emissive.writes - (Show.lastEmitWrites or 0)
      Show.lastEmitClock = Show.clock
      Show.lastEmitWrites = Emissive.writes
      emitEvent(state, "I", "show_tick", {
        step = stepNow,
        skipped = skipped,
        max_skip = Show.maxSkip,
        -- LIFETIME average, kept because six rounds of artefacts quote it.
        writes_per_s = (Show.clock > 0.01)
          and (Emissive.writes / Show.clock) or 0,
        -- The rate the demand model actually predicts.
        writes_per_s_window = (windowClock > 0.01)
          and (windowWrites / windowClock) or 0,
        window_s = windowClock,
        window_writes = windowWrites,
        beat = showBeat(),
        clock_real = Show.clock,
        clock_sim = Show.simClock,
        -- The IDEAL time this step should have landed at. Drift is
        -- (clock_real - ideal), and it is bounded by one frame BY
        -- CONSTRUCTION because the step index is derived from the clock
        -- rather than counted.
        ideal = stepNow * SHOW_TICK,
        frames = Show.frames,
        mode = Show.mode,
        writes = Emissive.writes,
      })
    end
  end

  Spots.update(state, Show.mode, Lights.flash or 0)
  Emissive.update(state, Show.mode, Lights.flash or 0)
end

-- =====================================================================
-- THE SOUNDTRACK (round 7, 2026-08-14).
--
-- Same contract as the light rig above, for the same reason: this machine's
-- behaviour was tuned over many live rounds and a 5 cm change halves its
-- score rate, so the audio is a STRICT OBSERVER. It reads b.phase, b.lift,
-- b.lx / b.ly / b.lz, b.localXRate / b.localYRate / b.localZRate,
-- b.settleTimer, b.kicks, b.rapCount, b.spellRaps, b.lastValue and
-- b.conceded, and it writes nothing back. It adds no gameplay state and
-- takes no decision.
--
-- THE L-SYNC IS THE WHOLE POINT. The owner's reference calls out impact-frame
-- synchronisation - sub-bass, prop movement and a white flash inside the same
-- few milliseconds. The light rig already strobes off two exact triggers:
-- b.kicks incrementing, and b.lz crossing down through B.ridge_band_lo. This
-- module fires the kicker thump and the bin-contact hit off THE SAME TWO
-- PREDICATES, evaluated from the same state in the same behavior.update call,
-- one statement after Lights.update has flashed on them. It keeps its own
-- prevZ rather than reading Lights' - two observers, one truth - and the
-- bookkeeping is deliberately line-for-line identical so they cannot drift.
-- Driving the sound off the state the lights already read is what makes the
-- sync free; there is no scheduler and no offset to keep in step.
--
-- The residual skew is honest and worth naming: the GE side can only ASK the
-- vehicle VM to play (obj:createSFXSource is an obj method), and a
-- queueLuaCommand executes on the vehicle's next tick. Light and sound are
-- committed on the same frame; the sound is dispatched within one frame of
-- it. That is the floor for any GE-driven audio on this engine.
--
-- FOUR THINGS STOLEN FROM THE CENTRIFUGE'S WIRING, each of which cost it a
-- round: funnel every way a loop can end through ONE latch so a hand-off
-- cannot double-fire; create a source lazily exactly once; clear the flags in
-- behavior.init so a reset mid-play cannot fire a stale hand-off; and stop
-- only the id you started.
-- =====================================================================
--@AUDIO_GE@--

local Audio = {ready = false, on = {}, hold = {}, rr = {}}

-- The GE side never touches a source. It names a cue, and the vehicle VM -
-- which owns them, because createSFXSource is an obj method - does the rest.
-- The model rotation is a proper rotation, so a world point's AUTHORED
-- coordinates are just its dot products with the three model axes. No
-- quaternion inverse required (and none is exposed).
--
-- DEFINED HERE, above audioSend, because it is the lowest-level helper in
-- this file and several node-cloud scans below need it. It used to sit far
-- lower and fieldCloudOccupied - which is a node-cloud scan - was written
-- above it, so `localOf` resolved as a nil GLOBAL inside it. The chunk
-- still compiled; the peg-restore gate would simply have thrown the first
-- time it ran. test_local_helpers_defined_before_use caught it.
-- It depends on nothing from this file, only on the prelude's toWorldDir.
local function localOf(state, worldPoint)
  local d = worldPoint - state.origin
  return d:dot(toWorldDir(state, vec3(1, 0, 0))),
         d:dot(toWorldDir(state, vec3(0, 1, 0))),
         d:dot(toWorldDir(state, vec3(0, 0, 1)))
end

local function audioSend(state, method, argument)
  pcall(function()
    local propObj = be:getObjectByID(state.propId)
    if not propObj then return end
    if argument then
      propObj:queueLuaCommand(string.format(
        "if extensions.%s_vehicle and extensions.%s_vehicle.%s then"
        .. " extensions.%s_vehicle.%s(%q) end",
        PROP_MODEL, PROP_MODEL, method, PROP_MODEL, method, argument))
    else
      propObj:queueLuaCommand(string.format(
        "if extensions.%s_vehicle and extensions.%s_vehicle.%s then"
        .. " extensions.%s_vehicle.%s() end",
        PROP_MODEL, PROP_MODEL, method, PROP_MODEL, method))
    end
  end)
end

-- =====================================================================
-- THE RETRACTABLE PIN - GE half (2026-08-14i).
--
-- The vehicle VM owns the geometry (setNodePosition is an obj method and the
-- node frame only exists over there). This side owns the DECISION: which peg
-- the car is on, when to escalate, and - the one that matters - when it is
-- safe to put the pins back.
--
-- THE LADDER, escalating on the SAME spell counter the knocker already uses,
-- so a car gets the impulse ladder first and the pins only when the impulse
-- has demonstrably failed:
--     rap 1              knocker only, which frees most cars
--     rap retract_peg    the peg the car is draped on collapses
--     rap retract_row    its whole row collapses
--     rap retract_all    the field collapses; at scale 0.10 the worst
--                        pairwise throat is 5.319 m against a 5.148 m car
--                        chord, so there is nothing left to hang on
--     rap giveup_spell   the concede, now a backstop that should never fire
-- Tiers only ever go UP within a play, so an escalation cannot be undone by
-- the car drifting nearer a different peg between raps.
--
-- RE-EXTENSION IS THE ONLY DIRECTION THAT CAN STAMP STEEL THROUGH A CAR, and
-- it is gated on field_zone being EMPTY - the engine's own occupancy, not a
-- position guess, and the same Overlaps box that spans the whole fall volume.
-- A car still hung on the board therefore keeps the pins retracted for as
-- long as it is there, which is the correct answer and not a leak.
--@PEG_ROWS@--
--@PEG_SCALES@--

local function nearestPeg(lx, lz)
  local bestRow, bestCol, bestD = 0, 0, math.huge
  for i = 1, #PEG_ROWS do
    local row = PEG_ROWS[i]
    for j = 1, #row.xs do
      local dx, dz = lx - row.xs[j], lz - row.z
      local d = dx * dx + dz * dz
      if d < bestD then bestD, bestRow, bestCol = d, row.row, j - 1 end
    end
  end
  return bestRow, bestCol, math.sqrt(bestD)
end

-- Is this car actually among the pegs? The ladder is a PIN remedy and must
-- not fire for a car that is stalled somewhere without any pins - the crown
-- chute above the field, the deck, or the bin dividers below it. The band is
-- the peg rows themselves plus one crown reach of margin at each end.
local function inPegField(lx, lz)
  if lx == nil or lz == nil then return false end
  if math.abs(lx) > B.field_hw then return false end
  local top, bottom = PEG_ROWS[1].z, PEG_ROWS[#PEG_ROWS].z
  return lz <= top + 2.0 and lz >= bottom - 2.0
end

-- Selectors are the peg NAMES' own row/column text, zero-padded, so the
-- vehicle side can match them against the cage node names it already has and
-- neither end has to agree about coordinates. The "#scale" suffix is how far
-- in they go.
--
-- TIER 1 ONLY GOES HALF WAY IN. The change is kept; THE MEASUREMENT THAT WAS
-- WRITTEN HERE TO JUSTIFY IT WAS WRONG, and it is corrected rather than
-- deleted because a wrong number left standing is how the next round gets
-- misled the same way (2026-08-15, serial 79).
--
-- WHAT THIS COMMENT USED TO CLAIM: that all 5 serial 76/77 auto-resets were
-- tier-1 retracts of a peg the car was "1.02-1.05 m from", and that "the
-- other 18 retracts, at 1.27-2.94 m, were all clean".
--
-- WHAT THE RECORDS ACTUALLY SAY, re-read event by event out of the shipped
-- run JSON (attribution is by event ORDER - the retract immediately preceding
-- each subject_reset - which is the same evidence the original claim had):
--
--   serial 76   reset after tier 1 at 2.12 m
--               reset after tier 1 at 2.45 m
--               reset after tier 3 at 4.51 m      <- not tier 1 at all
--   serial 77   reset after tier 1 at 1.02 m
--               reset after tier 1 at 1.05 m
--   serial 78   reset after tier 1 at 1.24 m
--               reset after tier 3 at 2.62 m      <- not tier 1 at all
--
-- So: 2 of 5 matched the quoted band, TWO OF SEVEN WERE NOT TIER 1, and two
-- resets fired at distances (2.12, 2.45) that sit INSIDE the range the
-- comment declared clean. The "1.27-2.94 m all clean" range is not a fact
-- about the data either - the clean retracts run from 0.95 m to 8.17 m.
--
-- THEREFORE THE PROXIMITY STORY IS NOT ESTABLISHED, and no threshold should
-- be fitted to it. What survives is the mechanism, which never depended on
-- the distances: the collapse cannot PUSH (it is a subset map), but a surface
-- receding THROUGH a node already inside it is a contact the solver has to
-- resolve. What that points at is TRAVEL PER FRAME, not distance to the peg -
-- see PEG_MAX_STEP_M, which is this round's actual response, and note that
-- the reset that fired after a tier-3 whole-field collapse is exactly the
-- case a distance threshold could never have caught.
--
-- Tier 1's half-reach stays because it is cheap and it is the gentler
-- direction; it is no longer claimed to be the thing that fixed anything. The
-- full collapse is kept for the row and field tiers, which fire 1.6 s later
-- by which time the car has moved. The remaining travel from 0.45 to 0.10 is
-- also shorter, so the escalation gets gentler as it goes deeper rather than
-- more violent.
local function pegRetract(state, tier, lx, lz)
  local b = state.behavior
  local row, col, distance = nearestPeg(lx or 0, lz or 0)
  local selector = "*:*#" .. PEG_SCALE_FULL
  if tier <= 1 then
    selector = string.format("%02d:%02d#%s", row, col, PEG_SCALE_NEAR)
  elseif tier == 2 then
    selector = string.format("%02d:*#%s", row, PEG_SCALE_FULL)
  end
  b.pegTier = tier
  b.pegRetracted = true
  audioSend(state, "pachinkoPegRetract", selector)
  emitEvent(state, "I", "pachinko_peg_retract", {
    subject_id = b.subjectId,
    tier = tier,
    selector = selector,
    peg_row = row,
    peg_col = col,
    peg_distance = distance,
    x = lx,
    z = lz,
  })
end

-- THE RESTORE GATE READS THE NODE CLOUD (2026-08-15, serial 79).
--
-- Re-extending a peg is the one operation in this machine that can stamp
-- steel through a car, and until now it was gated on zoneCount("field_zone").
-- That gate is not a measurement of where any car is. It is a read of
-- EVENT-SOURCED BOOKKEEPING, and the bookkeeping is provably lossy.
--
-- THE MECHANISM, traced rather than assumed - and NOT the one the review
-- suggested. `state.zones` is not ref-node based: the engine trigger is
-- triggerTestType "Bounding box", so its occupancy test is already a whole-
-- body test and its RESOLUTION was never the problem. The problem is its
-- LIFETIME. `state.zones[zone][id]` is set by an enter event and cleared by
-- an exit event, and two things wipe it out from under the gate:
--
--   * onVehicleResetted -> removeSubjectEverywhere -> rebuildTriggers, and
--     rebuildTriggers does `state.zones = {}` WHOLESALE. Every vehicle reset
--     - the player pressing Insert, the engine's own instability auto-reset,
--     or in the census rig every single teleport(reset=True) at the start of
--     a play - empties the table. The rebuild only restores occupancy for a
--     car that then generates a FRESH enter event.
--   * a car ALREADY INSIDE a box does not generate a crossing at all. That
--     is not a suspicion; it is written into this file's own field_zone note
--     as a deliberate property ("a car left wedged in the pegs ... is already
--     inside the box, generates no new crossing").
--
-- THE EVIDENCE IT IS ALREADY HAPPENING. Serial 78 logged 24 field_zone
-- `zone_enter` events and only 16 `zone_exit`s. Eight plays put a car in the
-- box and never took it out again - and they are the hung ones. Yet across
-- every retract build not ONE `pachinko_peg_restore_blocked` event has ever
-- fired, on any of 12 restores. A gate that has never once said no, over a
-- census in which cars demonstrably stayed in the box, is not passing a test;
-- it is reading a table that had already been cleared.
--
-- It has been harmless so far only because the lowest peg sits at z 12.00 and
-- nothing has yet stopped that high. That is luck about the LATTICE, not a
-- property of the gate, and the next lattice change spends it.
--
-- So the gate now also SCANS THE CLOUD, over the same box field_zone
-- describes - the rule is unchanged, a direct measurement is added next to
-- the bookkeeping. The zone count is still consulted and still blocks on its
-- own, so this is strictly additive: a vehicle either system can see blocks
-- the restore, and a node scan cannot go stale because there is nothing to
-- keep up to date.
--
-- DELIBERATELY CONSERVATIVE, and the trade is named. A false block costs
-- nothing but a retracted field for another second - updateIdle retries on a
-- 1 s timer forever. A false PASS costs a car with a peg through it. So the
-- scan takes every id either system knows about, and any one node inside the
-- box is enough.
-- THE ROSTER IS getAllVehicles(), NOT THE ZONE TABLE AND NOT b.subjectId.
-- This was very nearly written as a scan over the subject plus the zone
-- occupants, which would have been theatre: pegRestore only ever runs from
-- updateIdle, and by then dropSubject has already set b.subjectId to nil and
-- the zone table is the very thing that cannot be trusted. The scan would
-- have had an empty roster in exactly the state it exists to guard. This
-- codebase already settled the point in another mod - "getAllVehicles() is
-- ground truth. Trigger-set bookkeeping made a parked car invisible for
-- minutes" (hot_potato) - and this is the same failure with steel attached.
-- P0.4 (2026-08-18): THE SENSOR, LIFTED - AND THE FAILURE SEMANTICS LEFT
-- BEHIND ON PURPOSE.
--
-- cloudOccupied(state, box, onlyId) -> hits, unknown
--
-- Same node-cloud scan fieldCloudOccupied always was, over an ARBITRARY box
-- instead of a hard-wired one, because `shaft_hang`, `throat_jam` and
-- `knife_hang` all need "is a car resident HERE" and a trigger zone cannot
-- answer that (:2149-2151: already inside the box, generates no crossing).
--
-- THE THIRD RETURN IS THE WHOLE POINT OF THE LIFT. The original returned 1 -
-- "occupied" - when pcall(getAllVehicles) failed, and that is exactly right
-- for its own job: a blocked peg restore costs a second, an unblocked one
-- costs a car with a peg through it. It is exactly WRONG for a classifier.
-- A generic box sensor that answers "occupied" on a roster hiccup reports the
-- car resident in the shaft AND the throat AND the 役物 on the same frame,
-- and whichever branch the classifier tests first FABRICATES A FAULT CLASS
-- OUT OF A SENSOR THAT KNEW NOTHING. So the primitive reports what it
-- actually knows - hits, and separately "I could not read the roster" - and
-- each caller decides what to do about not knowing. There is exactly one
-- fail-closed caller and it is named as one, below.
--
-- A box may be SHEARED along x (see census_boxes in BEHAVIOR): zslope/zx0
-- slide both z limits with x, which is what a 40 deg chute throat needs and
-- what an axis-aligned box cannot express without swallowing the peg field.
--
-- THE ROSTER IS getAllVehicles(), NOT THE ZONE TABLE AND NOT b.subjectId.
-- This was very nearly written as a scan over the subject plus the zone
-- occupants, which would have been theatre: pegRestore only ever runs from
-- updateIdle, and by then dropSubject has already set b.subjectId to nil and
-- the zone table is the very thing that cannot be trusted. The scan would
-- have had an empty roster in exactly the state it exists to guard. This
-- codebase already settled the point in another mod - "getAllVehicles() is
-- ground truth. Trigger-set bookkeeping made a parked car invisible for
-- minutes" (hot_potato) - and this is the same failure with steel attached.
-- `onlyId` narrows the scan to ONE vehicle without narrowing the ROSTER: the
-- census asks about the subject, the peg guard asks about everything, and
-- both read the same ground truth.
local function cloudOccupied(state, box, onlyId)
  local ok, all = pcall(getAllVehicles)
  if not ok or type(all) ~= "table" then return 0, true end
  local hits = 0
  local partial = false
  local slope = box.zslope or 0
  local zx0 = box.zx0 or 0
  for _, vehicle in ipairs(all) do
    local inside = false
    -- pcall because getNodeCount can exist while getNodePosition throws, and
    -- a throw here takes the frame down. getNodePosition is an OFFSET from
    -- getPosition, so it has to go through localOf rather than raw world z.
    --
    -- FIXED 2026-08-18, D2. THE RETURN OF THIS pcall USED TO BE DISCARDED,
    -- and the comment immediately above named the failure mode as real while
    -- the code swallowed it. A vehicle whose node read threw came out of this
    -- loop with `inside` still false and `unknown` still false, i.e. counted
    -- as READ AND NOT IN THE BOX. The tri-state was therefore only ever wired
    -- for a getAllVehicles failure; the node path still failed OPEN, in both
    -- callers, and both of those are the failures the tri-state exists to
    -- prevent:
    --   * fieldCloudOccupied returned 0 and the pegs drove back into a car
    --     the sensor could not read - the exact cost the fail-closed rule is
    --     written to buy off.
    --   * censusClassify saw hits = 0, unknown = false from every box, fell
    --     through to nil, and booked `unclassified` - a FAULT, IN THE
    --     DENOMINATOR, fabricated by a sensor that knew nothing. Which is
    --     verbatim the outcome P0.4 exists to eliminate, arriving by the one
    --     route P0.4 did not close.
    -- So the return is captured and a failed read makes the whole answer
    -- unknown. `hits` is still returned rather than zeroed: what was counted
    -- before the throw is real, and a caller that wants to fail closed does
    -- so on the flag, not on the count.
    --
    -- NOTE WHAT THIS DELIBERATELY DOES NOT DO. The id checks run BEFORE any
    -- node call, so a broken vehicle that is neither the machine nor the
    -- census subject returns from the closure normally and does NOT poison a
    -- narrowed (onlyId) read. The census asks about ONE car and is spoiled
    -- only by a failure that could have concerned that car - including a
    -- getId() that throws, because a vehicle whose identity cannot be read
    -- might be the subject.
    local okv = pcall(function()
      local id = vehicle:getId()
      if id == state.propId then return end     -- the machine is not a car
      if onlyId and id ~= onlyId then return end
      if not (vehicle.getNodeCount and vehicle.getNodePosition) then return end
      local count = vehicle:getNodeCount() or 0
      local base = vehicle:getPosition()
      for i = 0, count - 1 do
        local np = vehicle:getNodePosition(i)
        if np then
          local px, py, pz = localOf(state, base + np)
          local shift = slope * (px - zx0)
          if px >= box.x0 and px <= box.x1
            and py >= box.y0 and py <= box.y1
            and pz >= box.z0 + shift and pz <= box.z1 + shift then
            inside = true
            return
          end
        end
      end
    end)
    if not okv then
      partial = true
    elseif inside then
      hits = hits + 1
    end
  end
  if partial then return hits, true end
  return hits, false
end

-- THE ONE FAIL-CLOSED CALLER. Kept as its own named function rather than
-- inlined, so that "this box fails closed" is a property of the peg guard and
-- not a property of the sensor - which is what let the classifier inherit it
-- by accident in the first draft of P0.4.
local FIELD_GUARD_BOX = {
  x0 = -(B.field_hw + 0.1), x1 = B.field_hw + 0.1,
  y0 = -(B.depth_half + 0.1), y1 = B.depth_half + 0.1,
  z0 = B.peg_guard_z_lo, z1 = B.peg_guard_z_hi,
}

local function fieldCloudOccupied(state)
  local hits, unknown = cloudOccupied(state, FIELD_GUARD_BOX)
  -- Fail CLOSED, HERE, and deliberately not in the sensor. If the roster
  -- cannot be read, the honest answer is "I do not know whether the field is
  -- empty", and the safe reading of that is occupied: a blocked restore costs
  -- a second, an unblocked one costs a car with a peg through it.
  if unknown then return 1 end
  return hits
end

-- P0.4, THE CLASSIFIER. Which box names which class - data, so that adding a
-- 役物 box in Phase 2 is a BEHAVIOR change and not a control-flow change.
local CENSUS_BOX_CLASS = {
  throat = "throat_jam",
  yakumono_held = "held",
  yakumono = "knife_hang",
  shaft = "shaft_hang",
  mouth = "mouth_hang",
  field = "field_hang",
}
local CENSUS_UNKNOWN = "sensor_unknown"

-- Returns a class name, or CENSUS_UNKNOWN if the roster could not be read, or
-- nil for "read cleanly and the car is resident in no declared box".
-- THE THREE ANSWERS ARE DIFFERENT AND MUST STAY DIFFERENT. nil is knowledge
-- (it becomes `unclassified`, which is a fault); CENSUS_UNKNOWN is the
-- absence of knowledge (it takes the play out of the census). Collapsing them
-- is how a sensor fault turns into a fabricated hang rate.
local function censusClassify(state)
  local b = state.behavior
  local boxes = B.census_boxes or {}
  local order = B.census_box_order or {}
  local anyRead = false
  for _, name in ipairs(order) do
    local box = boxes[name]
    -- A class with no box yet (役物, 裏箱 - Phase 2) simply never matches.
    if box then
      local hits, unknown = cloudOccupied(state, box, b.subjectId)
      if unknown then
        -- Bail on the FIRST unknown rather than testing the rest: a partial
        -- sweep answers a different question from the one the order encodes.
        return CENSUS_UNKNOWN
      end
      anyRead = true
      if hits > 0 then return CENSUS_BOX_CLASS[name] end
    end
  end
  if not anyRead then return CENSUS_UNKNOWN end
  return nil
end

-- Latched at the FIRST rap of a play - the moment the machine itself first
-- decided the car had stopped. See THE CENSUS METRIC in spec.py for why the
-- class is read there and not only at rest. Retries on later raps if the
-- roster could not be read, because a recoverable sensor hiccup should cost
-- nothing; a play only leaves the census if EVERY read failed.
local function censusLatchStop(state)
  local b = state.behavior
  if b.censusStopClass then return end
  local class = censusClassify(state)
  if class == CENSUS_UNKNOWN then return end
  b.censusRead = true
  if class then b.censusStopClass = class end
end

local function pegRestore(state)
  local b = state.behavior
  if not b.pegRetracted then return end
  local occupants = zoneCount(state, "field_zone")
  local cloud = fieldCloudOccupied(state)
  if occupants > 0 or cloud > 0 then
    if not b.pegRestoreBlocked then
      b.pegRestoreBlocked = true
      -- Both sensors reported separately and on purpose: `cloud > occupants`
      -- is the case the zone count was blind to, and it should be visible in
      -- the log as itself rather than averaged into one number.
      emitEvent(state, "I", "pachinko_peg_restore_blocked", {
        occupants = occupants,
        cloud_occupants = cloud,
        zone_missed = (cloud > 0 and occupants == 0) or false,
      })
    end
    return
  end
  b.pegRetracted = false
  b.pegRestoreBlocked = false
  b.pegTier = 0
  audioSend(state, "pachinkoPegRetract", "restore")
  emitEvent(state, "I", "pachinko_peg_restore", {})
end

Audio.play = function(state, name)
  Audio.hold[name] = AUDIO_HOLD[name]
  audioSend(state, "pachinkoAudioPlay", name)
end

Audio.stop = function(state, name)
  Audio.hold[name] = nil
  Audio.on[name] = false
  audioSend(state, "pachinkoAudioStop", name)
end

-- THE LATCH. A loop is started and stopped by a STATE CHANGE, never by a
-- condition being true again this frame: an un-latched loop re-issues playSFX
-- every frame and the bed restarts 60 times a second.
Audio.setLoop = function(state, name, want)
  want = want and true or false
  if want == (Audio.on[name] or false) then return end
  Audio.on[name] = want
  audioSend(state, want and "pachinkoAudioPlay" or "pachinkoAudioStop", name)
end

-- THE YOKOKU LADDER, monotone within a play. A tier can only ever go up, and
-- it stops the tier below as it goes, so the escalation is a SWAP and never a
-- pile-up of four bells from the same family.
Audio.tierUp = function(state, tier)
  local at = Audio.tierAt or 0
  if tier <= at then return end
  if at > 0 then Audio.stop(state, "yokoku_t" .. at) end
  Audio.tierAt = tier
  Audio.play(state, "yokoku_t" .. tier)
end

-- Round-robin inside the velocity class, over the pooled fifteen.
Audio.pinStrike = function(state, class)
  local slot = (Audio.rr[class] or 0) + 1
  if slot > 5 then slot = 1 end
  Audio.rr[class] = slot
  Audio.play(state, string.format("pin_%s_%02d", class, slot))
end

-- Is a resolution still speaking? The attract bed waits for it.
Audio.resolving = function()
  return (Audio.hold.payout_jackpot or Audio.hold.payout_medium
    or Audio.hold.payout_small or Audio.hold.concede
    or Audio.hold.reach_win or Audio.hold.reach_fail) ~= nil
end

Audio.newPlay = function()
  Audio.tierAt = 0
  Audio.settled = false
  Audio.committed = false
  Audio.pinned = false
  Audio.vx, Audio.vy, Audio.vz = nil, nil, nil
  Audio.pinCool = 0
end

-- THE PIN DETECTOR. This engine hands a GE-side prop no contact callback for
-- a car striking static cage triangles, so a strike is INFERRED from the
-- sample the machine already takes: the frame-to-frame change in the
-- subject's velocity WITH FREE FALL REMOVED is, by definition, an impulse it
-- received from something solid. It is an inference and not an event - two
-- pegs struck inside one frame read as one harder strike - but it is the
-- honest one, because the quantity it measures (impact velocity) is exactly
-- the quantity the bank was synthesised against: level, brightness, decay and
-- the click/ring/thud balance all move with v.
Audio.pins = function(state, dtSim)
  local b = state.behavior
  if dtSim <= 0.0001 then return end
  local vx, vy, vz = b.localXRate, b.localYRate, b.localZRate
  if vx == nil or vy == nil or vz == nil then return end
  local pvx, pvy, pvz = Audio.vx, Audio.vy, Audio.vz
  Audio.vx, Audio.vy, Audio.vz = vx, vy, vz
  Audio.pinCool = (Audio.pinCool or 0) - dtSim
  if pvx == nil then return end
  local dx, dy = vx - pvx, vy - pvy
  local dz = (vz - pvz) + 9.81 * dtSim
  local hit = math.sqrt(dx * dx + dy * dy + dz * dz)
  if hit < AUDIO_PIN_MIN or Audio.pinCool > 0 then return end
  Audio.pinCool = AUDIO_PIN_GAP
  -- ...but only a strike OFF THE CHUTE ends the slide. Measured live on
  -- serial 71: the kicker throws the car onto the 40 deg slab and it LANDS,
  -- which is a 9 m/s impulse two frames after chute_slide starts. Treating
  -- that landing as the first pin contact cut the slide loop after 33 ms and
  -- the cue effectively never played. A strike is still a strike - the
  -- landing gets its own hard modal hit, correctly - but the thing that ends
  -- the SLIDE is arriving in the pin field, which is what the cue set means
  -- by "stop on first pin contact".
  if not Audio.onChute then Audio.pinned = true end
  local class = "soft"
  if hit >= AUDIO_PIN_HARD then class = "hard"
  elseif hit >= AUDIO_PIN_MED then class = "med" end
  Audio.pinStrike(state, class)
end

-- The payout is the one place the machine states a RESULT, so it is the one
-- place the soundtrack is allowed to. Every branch reads b.lastValue and
-- b.conceded - the values payout() has already written this frame - so the
-- cue and the printed label can never disagree.
Audio.resolve = function(state)
  local b = state.behavior
  local value = b.lastValue or 0
  if b.conceded then
    -- A tease still ringing under a concession is a lie about what happened.
    if (Audio.tierAt or 0) > 0 then Audio.stop(state, "yokoku_t" .. Audio.tierAt) end
    Audio.play(state, "concede")
  elseif value >= 10000 then
    -- Fired on the same frame Lights.tier switches to the rainbow chase:
    -- both read b.lastValue >= 10000 on the first frame of payout.
    Audio.play(state, "payout_jackpot")
  elseif value >= 1500 then
    Audio.play(state, "payout_medium")
  elseif value > 0 then
    Audio.play(state, "payout_small")
  elseif Audio.hold.reach_fail == nil then
    -- No score and no concession: gutter, off the board, hung, timed out.
    if (Audio.tierAt or 0) > 0 then Audio.stop(state, "yokoku_t" .. Audio.tierAt) end
    Audio.play(state, "reach_fail")
  end
end

-- Called from behavior.init, which runs on registration AND on every reset.
-- Silence first, prime second: a reset mid-play must not leave a loop running
-- with nothing left holding its handle.
Audio.create = function(state)
  Audio.on = {}
  Audio.hold = {}
  Audio.rr = {}
  Audio.phase = nil
  Audio.prevZ = nil
  Audio.kicks = 0
  -- b.rapCount is a SESSION counter (setPhase does not clear it), so the
  -- edge detector is seeded from its live value; seeding it at 0 would fire
  -- a knocker on the first frame after any reset that followed a stuck play.
  Audio.raps = (state.behavior and state.behavior.rapCount) or 0
  Audio.newPlay()
  audioSend(state, "pachinkoAudioStopAll")
  audioSend(state, "pachinkoAudioPrime")
  Audio.ready = true
end

Audio.update = function(state, dtSim)
  if not Audio.ready then return end
  local b = state.behavior
  local phase = b.phase

  for name, left in pairs(Audio.hold) do
    left = left - dtSim
    if left <= 0 then Audio.hold[name] = nil else Audio.hold[name] = left end
  end

  -- ---- THE IMPACT FRAME ----------------------------------------------
  -- b.kicks increments in the same frame the kicker impulse is applied.
  local kicks = b.kicks or 0
  local kickFrame = kicks > Audio.kicks
  Audio.kicks = kicks
  if kickFrame then Audio.play(state, "kicker_impulse") end
  -- The car dropping past the bin mouths: contact with the pocket. The
  -- predicate and the prevZ bookkeeping are the strobe's, verbatim.
  local binFrame = phase == "falling" and b.lz and Audio.prevZ
    and Audio.prevZ >= B.ridge_band_lo and b.lz < B.ridge_band_lo
  Audio.prevZ = (phase == "falling") and b.lz or nil
  if binFrame then Audio.pinStrike(state, "hard") end
  -- The knocker rap, on the frame the impulse is applied, at the rung the
  -- escalation ladder has actually reached.
  local raps = b.rapCount or 0
  local rapFrame = raps > Audio.raps
  Audio.raps = raps
  if rapFrame then
    local step = b.spellRaps or 1
    if step < 1 then step = 1 end
    if step > 4 then step = 4 end
    Audio.play(state, "knocker_" .. step)
  end

  -- ---- PHASE EDGES ---------------------------------------------------
  if phase ~= Audio.phase then
    Audio.phase = phase
    if phase == "idle" or phase == "loading" then Audio.newPlay() end
    -- TIER 1 as the carriage starts up: "a play is happening". The lights
    -- are white/blue and rising on the same phase.
    if phase == "hoist" then Audio.tierUp(state, 1) end
    -- TIER 2 under the green crescendo: dock + arming is the pre-release
    -- tease the light rig now ramps across, and t2 is 2.50 s against its
    -- 3.0 s window - the bell resolves as the gate finishes opening.
    if phase == "dock" then Audio.tierUp(state, 2) end
    if phase == "arming" then Audio.play(state, "gate_open") end
    if phase == "payout" then Audio.resolve(state) end
  end

  -- ---- THE RISE ------------------------------------------------------
  -- The settle is the ease-out, not the arrival: hoist_taper_m before the
  -- dock the servo starts shedding speed, and that is what the cue plays.
  if phase == "hoist" and not Audio.settled
      and (b.lift or 0) >= B.lift_travel - B.hoist_taper_m then
    Audio.settled = true
    Audio.play(state, "hoist_settle")
  end

  -- ---- THE FALL ------------------------------------------------------
  if phase == "falling" and b.lz then
    -- TIER 3 at the same depth the board burns full red: the ladder and the
    -- colour cross together because they test the same expression.
    local depth = clamp01((B.apron_z_hi - b.lz) / (B.apron_z_hi - B.ridge_band_lo))
    if depth >= 0.5 then Audio.tierUp(state, 3) end
    -- TIER 4 on the machine's own gold condition - lined up on the choked
    -- 2.60 m jackpot mouth and low enough for it to mean something. Same
    -- test the lights use to fade gold in, so bell and colour arrive on one
    -- frame. It is a promise the physics is free to break, which is exactly
    -- what a yokoku is.
    local centre = B.bin_centers[3] or 0
    if b.lx and math.abs(b.lx - centre) <= B.bin_pitch * 0.75
        and b.lz <= B.ridge_band_hi + 9.0 then
      Audio.tierUp(state, 4)
    end
    -- THE COMMIT. The machine is counting the car out in a pocket
    -- (settleTimer running below score_max_z); settle_seconds later payout
    -- names the bin. The bounds are payout()'s own gutter/off-board tests,
    -- read from the same B, so the reach cannot resolve against the score.
    if not Audio.committed and (b.settleTimer or 0) > 0 and b.lz < B.score_max_z then
      Audio.committed = true
      Audio.stop(state, "reach_loop")
      local inBounds = b.lx and b.ly
        and b.lx <= B.field_hw + 0.4 and b.lx >= -B.field_hw - 0.4
        and b.ly <= B.depth_half + 0.6 and b.ly >= B.bin_y_front - 1.0
      Audio.play(state, inBounds and "reach_win" or "reach_fail")
    end
  end

  -- ---- THE BEDS ------------------------------------------------------
  Audio.setLoop(state, "hoist_loop", phase == "hoist")
  Audio.setLoop(state, "reach_loop", phase == "falling" and not Audio.committed)
  -- The attract bed is the empty machine breathing, and it waits its turn:
  -- opening it under a jackpot fanfare would talk over the only cue in the
  -- set that has anything to say.
  Audio.setLoop(state, "attract_bed",
    (phase == "idle" or phase == "returning") and not Audio.resolving())
  -- The chute, from the car's own plane test: on the 40 deg slab, until the
  -- first pin contact of the play - which is the moment it stops sliding and
  -- starts being a pachinko ball.
  local onChute = false
  if phase == "falling" and b.lx and b.lz and not Audio.pinned then
    local chuteZ = B.apron_z_hi - (B.apron_x_hi - b.lx) * B.apron_tan
    onChute = b.lx > B.chute_x_lo and b.lx <= B.apron_x_hi
      and b.lz > chuteZ - 1.5 and b.lz < chuteZ + 3.0
  end
  -- Read by the pin detector below, which runs after this: an impulse taken
  -- while the car is still on the slab is the landing, not the pin field.
  Audio.onChute = onChute
  Audio.setLoop(state, "chute_slide", onChute)

  -- ---- THE PIN FIELD -------------------------------------------------
  -- A machine impulse is not a pin strike: it has its own cue, and its
  -- velocity change lands in the NEXT position-derived sample, so both the
  -- history and the cooldown are cleared rather than just this frame skipped.
  if kickFrame or rapFrame then
    Audio.vx, Audio.vy, Audio.vz = nil, nil, nil
    Audio.pinCool = AUDIO_PIN_GAP
  elseif phase == "falling" then
    Audio.pins(state, dtSim)
  end
end

-- =====================================================================
-- THE PA HORN CLUSTER (round 8, 2026-08-14). Four re-entrant horns on a
-- street-light pole beside the scoreboard, and the announcements that come
-- out of them.
--
-- WHY THIS EXISTS AS A BLOCK AND NOT AS EDITS. Everything below is APPENDED:
-- one module, then four wrappers that rebind Audio.play / Audio.stop /
-- Audio.create / Audio.update to themselves-plus-a-horn-step. Not a line of
-- the Audio module, the phase machine or the tuned table is touched, which is
-- the fence this round works behind - and it is the same idiom the vehicle
-- bootstrap already uses for updateGFX and onReset. Callers reach Audio.play
-- through the table, so the rebind takes effect everywhere without a single
-- call site changing.
--
-- WHY SCENE OBJECTS AND NOT NODES. obj:createSFXSource takes a NODE id, and
-- the only node this prop's runtime may name is 0 (node ids here are cage
-- indices and the cage is frozen), which is why the whole soundtrack has been
-- coming out of one point on a 54 m machine. A scene object has no such
-- problem: it takes a world position, and it is created, registered and swept
-- by exactly the recipe the twelve PointLights already use - stored in
-- state.effects so cleanupInstallation deletes it on every teardown path.
--
-- THE MECHANISM IS PROBED, NOT ASSUMED (see spec.py for the numbers):
-- fileName + is3D is audible, `track` is digital silence on this build, and
-- the cone fields are wired and exact. The cone is what makes "four
-- directions" an audible fact rather than a picture.
--
-- EVERY HORN CUE IS A LOOP WEARING A STOP CLOCK, exactly like the vehicle
-- side - AudioDefaultLoop3D taught this pack that there is no one-shot - but
-- the clock lives HERE, because the emitter has no vehicle VM behind it. It
-- runs on the same dtSim these announcements are already timed by
-- (Audio.hold), so the two clocks cannot drift apart.
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

local Horn = {ready = false, hold = {}, origin = nil}
local HORN_IS = {}
for _index = 1, #HORN_CUE_LIST do HORN_IS[HORN_CUE_LIST[_index].name] = true end

-- state.effects key. The horn's own slot label is carried in HORN_SPECS so
-- the key, the scene name and the table row all read the same way.
local function hornSlot(cue, horn)
  return "pahorn_" .. cue .. "_" .. horn.slot
end

-- Re-pose every emitter. Split out of create because the framework's own
-- transform sweep only knows about EFFECT_SPECS members, so a placed prop that
-- ever moves would leave its horns behind - the same defect the light rig has
-- to guard against, and the same fix.
Horn.place = function(state, force)
  local origin = state.origin
  if not origin then return end
  if not force and Horn.origin
      and (origin - Horn.origin):length() <= 0.01 then
    return
  end
  Horn.origin = vec3(origin.x, origin.y, origin.z)
  for hi = 1, #HORN_SPECS do
    local horn = HORN_SPECS[hi]
    local p = toWorldPoint(state, horn.pos)
    local d = toWorldDir(state, horn.dir)
    -- The game's own aim recipe (photomodeFlash, and the centrifuge's
    -- steered SpotLights): quatFromDir -> toTorqueQuat -> the rotation
    -- field. setPosRot does nothing here, and a cone with no orientation
    -- would point wherever the identity transform happens to look.
    local ok, rot = pcall(function()
      local q = quatFromDir(d, vec3(0, 0, 1)):toTorqueQuat()
      return string.format("%f %f %f %f", q.x, q.y, q.z, q.w)
    end)
    for ci = 1, #HORN_CUE_LIST do
      local emitter = state.effects[hornSlot(HORN_CUE_LIST[ci].name, horn)]
      if emitter then
        pcall(function()
          if ok and rot then emitter:setField("rotation", 0, rot) end
          emitter:setPosition(vec3(p.x, p.y, p.z))
        end)
      end
    end
  end
end

-- POOLED UP FRONT, one emitter per cue per horn, created once when the prop
-- registers. The alternative - one emitter per horn whose fileName is
-- rewritten per announcement - cannot carry two announcements at once, and
-- this machine overlaps them routinely (a tier-4 bell is still ringing when
-- the jackpot lands).
Horn.create = function(state)
  for ci = 1, #HORN_CUE_LIST do
    local cue = HORN_CUE_LIST[ci]
    for hi = 1, #HORN_SPECS do
      local horn = HORN_SPECS[hi]
      local slot = hornSlot(cue.name, horn)
      if not state.effects[slot] then
        local emitter = createObject("SFXEmitter")
        if emitter then
          emitter = Sim.upcast(emitter)
          local ok = pcall(function()
            emitter:setTransform(MatrixF(true))
            emitter.canSave = false
            if type(emitter.setCanSave) == "function" then
              emitter:setCanSave(false)
            end
            -- playOnAdd defaults TRUE: without this line all forty
            -- announcements start blaring the moment the prop registers.
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
            emitter, string.format("pt_horn_p%d_%s_%s", state.propId,
                                   cue.name, horn.slot))
          if registered then
            state.effects[slot] = emitter
          else
            pcall(function() emitter:delete() end)
          end
        end
      end
    end
  end
  Horn.hold = {}
  Horn.origin = nil
  Horn.place(state, true)
  Horn.ready = true
end

-- Returns false when the pole could not take the cue, and the caller then
-- falls back to the vehicle-side source. A missing emitter should cost the
-- announcement its POSITION, never the announcement.
Horn.play = function(state, name)
  if not Horn.ready then return false end
  local spoke = false
  for hi = 1, #HORN_SPECS do
    local emitter = state.effects[hornSlot(name, HORN_SPECS[hi])]
    if emitter then
      spoke = true
      -- Stop before play: these are looping sources, and re-announcing a
      -- tier that is still sounding has to restart it, not be swallowed.
      pcall(function() emitter:stop() end)
      pcall(function() emitter:play() end)
    end
  end
  if spoke then Horn.hold[name] = AUDIO_HOLD[name] end
  return spoke
end

Horn.stop = function(state, name)
  Horn.hold[name] = nil
  for hi = 1, #HORN_SPECS do
    local emitter = state.effects[hornSlot(name, HORN_SPECS[hi])]
    if emitter then pcall(function() emitter:stop() end) end
  end
end

Horn.stopAll = function(state)
  for ci = 1, #HORN_CUE_LIST do Horn.stop(state, HORN_CUE_LIST[ci].name) end
end

Horn.update = function(state, dtSim)
  if not Horn.ready then return end
  Horn.place(state, false)
  -- Writing nil to the key currently being visited is legal in a pairs()
  -- walk, and Horn.stop does exactly that. Nothing here ADDS a key.
  for name, left in pairs(Horn.hold) do
    left = left - dtSim
    if left <= 0 then
      Horn.stop(state, name)
    else
      Horn.hold[name] = left
    end
  end
end

-- There is deliberately NO self-report here. The cleanup evidence this round
-- owes is a walk of the engine's object-id space for the `pt_horn_`
-- namespace, and a module counting its own table cannot see the two things
-- that walk exists to catch: an emitter the engine still holds after
-- state.effects let go of it, and two ids wearing one name.

-- ---- THE ROUTING -----------------------------------------------------
-- Four rebinds, no edits. Announcements go up the pole; everything else goes
-- where it always went.
local audioBasePlay = Audio.play
Audio.play = function(state, name)
  if HORN_IS[name] and Horn.play(state, name) then
    -- The base sets this too, and Audio.resolving() reads it to hold the
    -- attract bed off a payout that is still speaking. Routing the sound
    -- somewhere else must not change what the machine believes about it.
    Audio.hold[name] = AUDIO_HOLD[name]
    return
  end
  audioBasePlay(state, name)
end

local audioBaseStop = Audio.stop
Audio.stop = function(state, name)
  if HORN_IS[name] then Horn.stop(state, name) end
  audioBaseStop(state, name)
end

local audioBaseCreate = Audio.create
Audio.create = function(state)
  audioBaseCreate(state)
  Horn.create(state)
  -- A reset mid-announcement must not leave a horn talking to an empty lot.
  Horn.stopAll(state)
end

local audioBaseUpdate = Audio.update
Audio.update = function(state, dtSim)
  audioBaseUpdate(state, dtSim)
  Horn.update(state, dtSim)
end

local PHASE_TIMEOUT = {
  -- F-1: dock USED to be the one phase with no watchdog, which was harmless
  -- only while updateDock was pure arithmetic. It now runs a node scan that can
  -- throw, and the harness pcalls behavior.update - so a throw aborts the whole
  -- frame INCLUDING the setPhase("arming") two lines later, the condition is
  -- still true next frame, and the machine hangs at the crown forever with no
  -- watchdog able to fire. The scan is pcall'd (the cause); this is the class.
  dock = "release_timeout_seconds",
  loading = "load_timeout_seconds",
  hoist = "hoist_timeout_seconds",
  arming = "release_timeout_seconds",
  tipping = "release_timeout_seconds",
  falling = "fall_timeout_seconds",
  returning = "return_timeout_seconds",
}

-- Nearest bin index/centre for an authored x. Defined HERE, above every
-- caller, because a table method defined above a `local function` calls it as
-- a nil global and pcall swallows it (AGENTS.md).
local function nearestBinIndex(lx)
  local best, bestd = 1, math.huge
  for i = 1, #B.bin_centers do
    local d = math.abs(lx - B.bin_centers[i])
    if d < bestd then bestd, best = d, i end
  end
  return best, bestd
end

local function nearestBinCenter(lx)
  local index = nearestBinIndex(lx)
  return B.bin_centers[index]
end

local function applyMachinePose(state)
  local b = state.behavior
  local lift = b.lift or 0
  setPartPose(state, "carriage", vec3(0, 0, lift), nil)
  -- The deck pivots on the chute hinge line (authored x = APRON_X_HI).
  -- EMPIRICAL SIGN (play-tested 2026-08-13): the engine applies these +Y
  -- axisAngle poses with the OPPOSITE sense to the textbook R_y derivation.
  -- The first cut passed -tip "to raise the outboard edge" per the hand
  -- math, and the live deck tipped outboard-edge-DOWN, dumping the car into
  -- the machinery pit. Direction here is OBSERVED, not derived: +tip raises
  -- the outboard (+x) edge in game. The gate and sheave angles are negated
  -- with it so every +Y rotation in this file speaks the same convention.
  setPartPose(state, "tipper", vec3(0, 0, lift),
    axisAngle(vec3(0, 1, 0), math.rad(b.tip or 0)))
  -- The kick/stop rails ride the deck but live in their own COLLISIONLESS
  -- part: the tipper's stale home bake used to leave them standing invisibly
  -- in the loading bay for the whole cycle (see build_parts).
  setPartPose(state, "deck_rails", vec3(0, 0, lift),
    axisAngle(vec3(0, 1, 0), math.rad(b.tip or 0)))
  setPartPose(state, "counterweight", vec3(0, 0, -lift), nil)
  -- The chain loop is closed and static; only the sheave turns, by the
  -- travel divided by its pitch radius (negated: same empirical convention).
  setPartPose(state, "sheave", nil,
    axisAngle(vec3(0, 1, 0), -lift / B.sheave_radius))
  setPartPose(state, "gate", nil, axisAngle(vec3(0, 1, 0), -math.rad(b.gate or 0)))
  -- The payout marker rides its rail in authored +x. Pose offsets are added
  -- in authored space before the model flip, so this is just its x.
  setPartPose(state, "marker", vec3(b.marker or 0, 0, 0), nil)
end

local function clearEffects(state)
  for index = 0, #B.bin_values - 1 do
    setEffectActive(state, "bin_dust_" .. index, false)
  end
end

local function setPhase(state, phase)
  local b = state.behavior
  b.phase = phase
  -- Every sub-timer is cleared with the phase clock so no phase can inherit
  -- a partially elapsed accumulator from the one before it.
  b.elapsed = 0
  b.tipHold = 0
  b.rapTimer = 0
  b.settleTimer = 0
  b.stuckTimer = 0
  b.holdTimer = 0
  b.holdBaked = false
  b.holdGaveUp = false
  b.rideY = nil
  b.spellRaps = 0
  b.markZ = nil
  -- Latched per stuck spell, and reset here so no play can inherit the
  -- previous one's walk direction or chute/field rule (see updateFalling).
  b.spellSide = nil
  b.spellChute = nil
  b.spellSeat = nil
  -- Per-PLAY, exactly like b.kicks below and for the same reason: the retract
  -- LADDER position must start at the bottom every release. b.pegRetracted is
  -- deliberately NOT reset here - that one tracks the state of real geometry,
  -- and only pegRestore, which checks the field is empty, may clear it.
  b.pegTier = 0
  b.hopTimer = 0
  -- Per-PLAY, so the kick ladder starts from the bottom every release. Left
  -- unreset in the first cut, the counter carried across plays and the second
  -- car of a session was met with a capped 7.6 m/s kick from its very first
  -- frame in the lip zone.
  b.kicks = 0
  b.kickTimer = nil
end

local function dropSubject(state)
  local b = state.behavior
  b.subjectId = nil
  b.lastPos = nil
  b.restHeight = nil
  b.speed = 0
  b.localZRate = 0
  b.localXRate = 0
  b.localYRate = 0
  b.lx, b.ly, b.lz = nil, nil, nil
  b.settleTimer = 0
  b.stuckTimer = 0
  b.rapTimer = 0
  b.markZ = nil
  b.spellSide = nil
  b.spellChute = nil
  b.spellSeat = nil
  b.plateRef = nil
  b.conceded = false
  b.markerMode = nil
end

behavior.init = function(state)
  local b = state.behavior
  b.phase = "idle"
  b.elapsed = 0
  b.clock = 0
  b.lift = 0
  b.tip = 0
  b.gate = 0
  b.marker = 0
  b.markerTarget = nil
  b.parkTimer = 0
  b.idleGrace = 0
  b.lastCount = nil
  b.paid = false
  b.droveOff = false
  b.stats = {plays = 0, jackpots = 0, best = 0}
  dropSubject(state)
  setPhase(state, "idle")
  applyMachinePose(state)
  requestCollisionReload(state)
  -- Additive: the yokoku light rig. Idempotent (each slot is created only if
  -- state.effects does not already hold it), so behavior.reset re-entering
  -- init cannot double up, and cleanupInstallation is what deletes them.
  Lights.create(state)
  Show.begin(state)
  -- Additive: the cue set. Idempotent in the same way, and deliberately here
  -- rather than anywhere else, because init is the ONE path every reset runs
  -- through: it silences whatever the previous state left playing BEFORE it
  -- primes the pin pool, so a reset mid-fall cannot leave a loop running that
  -- nothing holds a handle to any more.
  Audio.create(state)
end

behavior.reset = function(state)
  behavior.init(state)
  clearEffects(state)
end

-- Arming path shared by the zone CROSSING and the idle occupancy POLL, so
-- the two can never drift apart.
local function armLoading(state, vehicle)
  local b = state.behavior
  dropSubject(state)
  b.subjectId = vehicle:getId()
  b.parkTimer = 0
  b.lastCount = nil
  b.markerMode = "search"
  b.markerTarget = nil
  b.paid = false
  b.droveOff = false
  showMessage("Hold still on the carriage deck...", 2.4)
  emitEvent(state, "I", "pachinko_boarded", {subject_id = b.subjectId})
  setPhase(state, "loading")
end

behavior.onEnter = function(state, zone, vehicle)
  local b = state.behavior
  if zone == "load_zone" then
    if b.phase == "idle" then
      armLoading(state, vehicle)
    elseif b.phase ~= "loading" then
      showMessage("Tower is busy - wait for the carriage to come home.", 2.0)
    end
    return
  end
  if zone == "field_zone" and b.phase == "idle" and not b.subjectId then
    -- A car reached the board without being hoisted: knocked in from the
    -- crown, dropped by another prop, or driven off the chute lip. Score it
    -- where it lands rather than ignoring it. Adoption keys off the CROSSING
    -- (not occupancy) so a car already wedged in the pegs after a fall
    -- timeout cannot re-adopt itself into a loop.
    b.subjectId = vehicle:getId()
    b.lastPos = nil
    b.rapCount = 0
    -- P0.4: the census latch is per PLAY, and an adopted car is a new play.
    b.censusStopClass = nil
    b.censusRead = false
    b.markerMode = "search"
    b.markerTarget = nil
    b.paid = false
    b.droveOff = false
    showMessage("Loose car on the board - playing it as it lies!", 2.4)
    emitEvent(state, "I", "pachinko_adopted", {subject_id = b.subjectId})
    setPhase(state, "falling")
  end
end

behavior.onExit = function(state, zone, vehicleId)
  local b = state.behavior
  if zone == "load_zone" and b.phase == "loading" and b.subjectId == vehicleId then
    dropSubject(state)
    b.parkTimer = 0
    b.lastCount = nil
    b.idleGrace = B.rearm_grace_seconds
    setPhase(state, "idle")
  elseif zone == "catch_zone" and b.phase == "payout" and b.subjectId == vehicleId then
    -- The score is already on screen and the player has driven out of the
    -- bins: there is nothing left to hold the pose for.
    showMessage("Come back around for another drop.", 2.0)
    -- F-7: this early exit skipped clearEffects, so the bin dust burst kept
    -- emitting through the whole return. Every other path out of payout stops
    -- it; this one has to as well.
    clearEffects(state)
    setPhase(state, "returning")
  end
end

behavior.onSubjectGone = function(state, vehicleId, reason)
  local b = state.behavior
  if b.subjectId ~= vehicleId then return end
  dropSubject(state)
  if b.phase ~= "idle" and b.phase ~= "returning" then
    emitEvent(state, "I", "subject_lost", {reason = reason, phase = b.phase})
    setPhase(state, "returning")
  end
end

-- Live subject sample: position in authored coordinates plus the speeds
-- derived from consecutive frames (the same primitive the seesaw uses; no
-- velocity API is guaranteed on the GE side).
local function sampleSubject(state, dtSim)
  local b = state.behavior
  local vehicle = b.subjectId and exactVehicle(b.subjectId) or nil
  if not vehicle then return nil end
  local raw = vehicle:getPosition()
  local position = vec3(raw.x, raw.y, raw.z)
  local lx, ly, lz = localOf(state, position)
  if b.lastPos and dtSim > 0.0001 then
    local delta = position - b.lastPos
    b.speed = delta:length() / dtSim
    b.localZRate = delta:dot(toWorldDir(state, vec3(0, 0, 1))) / dtSim
    b.localXRate = delta:dot(toWorldDir(state, vec3(1, 0, 0))) / dtSim
    b.localYRate = delta:dot(toWorldDir(state, vec3(0, 1, 0))) / dtSim
  else
    b.speed = 0
    b.localZRate = 0
    b.localXRate = 0
    b.localYRate = 0
  end
  b.lastPos = position
  b.lx, b.ly, b.lz = lx, ly, lz
  return vehicle, lx, ly, lz
end

-- "This sample is not on the machine any more." A player reset teleports the
-- car to its spawn point without destroying it, so exactVehicle still hands
-- back a live object whose position has nothing to do with the board; scoring
-- that position would invent a bin.
local function sampleIsLost(lx, ly, lz)
  local margin = B.lost_margin_m
  return lx > B.deck_center_x + B.deck_half_x + margin
    or lx < -B.field_hw - margin
    or ly > B.depth_half + margin
    or ly < B.bin_y_front - margin
    or lz < -margin
end

local function onDeck(state, lx, ly, lz)
  local b = state.behavior
  local deckZ = B.deck_home_z + (b.lift or 0)
  return math.abs(lx - B.deck_center_x) <= B.deck_half_x + B.slip_margin_m
    and math.abs(ly) <= B.deck_half_y + B.slip_margin_m
    and lz >= deckZ - B.slip_drop_m
    and lz <= deckZ + B.slip_drop_m
end

-- THE DROOP LIFT (2026-08-14h), and THE CONFORMAL BAKE LAW read the other way
-- round. The law is usually quoted as "never bake a surface into a car"; this
-- is the case where obeying it needs the SERVO to move rather than the bake.
--
-- restHeight is measured from the car's REF NODE while it is parked on the
-- loading floor, i.e. with its suspension COMPRESSED under its own weight.
-- For the whole ride the car is in free flight held by a torque-free velocity
-- servo, and a car in free flight DROOPS: its wheels hang. Measured on the
-- attitude probe, ref-to-lowest-node grows 0.40-0.43 m between lift-off and
-- the crown, every play. So a car held at exactly restHeight has its ref node
-- in the right place and its WHEELS 0.4 m BELOW THE PLATE, and the dock bake
-- then stamps the deck straight through them.
--
-- The square hoist command hid this completely: it overshot the dock by
-- 1.1-4.8 m, so at bake time the whole car was above the plate and the bake
-- was clean. Take the overshoot away - which is precisely what the player
-- asked for - and the bake starts landing inside the car. That, not the ride
-- itself, is what left cars at 10-32 deg of tilt with 0.5-1.0 m of ref-to-
-- contact and produced 0 of 8 on the first ease-out build.
--
-- So the last hoist_taper_m of travel ALSO lifts the servo set-point by
-- hoist_seat_lift_m, ramped in with the ease-out so there is no step. The car
-- reaches the dock at rest, entirely above the plate, the bake is clean, and
-- then the servo lets go and it falls that same distance onto a real surface.
-- A 0.90 m fall is 4.2 m/s of arrival - a landing, which is the only thing in
-- this machine that can RIGHT a car, since no script can apply torque.
local function seatLiftNow(b)
  local remaining = B.lift_travel - (b.lift or 0)
  if remaining >= B.hoist_taper_m then return 0 end
  if remaining <= 0 then return B.hoist_seat_lift_m end
  return B.hoist_seat_lift_m * (1 - remaining / B.hoist_taper_m)
end

-- The support impulse a real floor would apply, as a VELOCITY constraint.
-- A runtime TSStatic's collision is a snapshot that only refreshes on
-- be:reloadCollision(), so a moving deck cannot carry a car by contact;
-- this servo tracks the deck's height and climb rate instead. Position is
-- never written, the correction is capped every frame, and an absurdly
-- fast sample is skipped outright.
local function hoistServo(state, vehicle, lz)
  local b = state.behavior
  if b.speed > B.runaway_speed_mps then return end
  local targetZ = B.deck_home_z + b.lift + (b.restHeight or B.car_rest_height)
    + seatLiftNow(b)
  local heightError = targetZ - lz
  local correction = heightError * B.hoist_kp
  if correction > B.hoist_v_max then correction = B.hoist_v_max end
  if correction < -B.hoist_v_max then correction = -B.hoist_v_max end
  local want = (b.liftRate or 0) + correction
  local dv = want - b.localZRate
  if dv > B.frame_dv_cap then dv = B.frame_dv_cap end
  if dv < -B.frame_dv_cap then dv = -B.frame_dv_cap end
  addSubjectVelocity(state, vehicle, toWorldDir(state, vec3(0, 0, 1)) * dv)
end

-- Walk the car inboard across the LEVEL deck and over the hinge lip onto
-- the chute: the sumo/car-wash tangential-push pattern. The car stays on
-- the deck's real dock-pose collision the whole time (no aerial carry, no
-- z axis needed - the floor is honest), so the only commanded axes are a
-- constant inboard x rate and a gentle y recenter. The command escalates
-- slowly after eject_boost_seconds so locked brakes only delay the drop.
-- See THE CONFORMAL BAKE LAW in BEHAVIOR for why the deck must never tip
-- while the car is aboard.
local function ejectServo(state, vehicle)
  local b = state.behavior
  if b.speed > B.runaway_speed_mps then return end
  local speed = B.eject_speed_mps
  if b.elapsed > B.eject_boost_seconds then
    speed = speed + (b.elapsed - B.eject_boost_seconds) * 0.6
  end
  if speed > B.eject_speed_max_mps then speed = B.eject_speed_max_mps end
  local dvx = (-speed) - (b.localXRate or 0)
  -- A ONE-SIDED FIELD, NOT A REGULATOR. The first cut clamped dvx in both
  -- directions, so any car already moving inboard FASTER than eject_speed_mps
  -- got BRAKED - and since ejectServo runs before the kicker every frame, the
  -- kicker's whole horizontal component was erased within ~2 frames (the
  -- servo can shed 1.5 m/s per frame, the kick adds 4.0 once). The field may
  -- push the car inboard; it may never pull it back.
  if dvx > 0 then dvx = 0 end
  if dvx < -B.frame_dv_cap then dvx = -B.frame_dv_cap end
  local targetY = b.rideY or (b.ly or 0)
  local wantY = (targetY - (b.ly or targetY)) * B.hoist_kp
  if wantY > B.eject_y_vmax then wantY = B.eject_y_vmax end
  if wantY < -B.eject_y_vmax then wantY = -B.eject_y_vmax end
  local dvy = wantY - (b.localYRate or 0)
  if dvy > B.frame_dv_cap then dvy = B.frame_dv_cap end
  if dvy < -B.frame_dv_cap then dvy = -B.frame_dv_cap end
  -- THE UNIT-AXIS LAW. lua_kit's toWorldDir NORMALIZES its result, so handing
  -- it a non-unit local vector silently throws the magnitude away. The first
  -- cut passed vec3(dvx, dvy, 0) straight in and therefore injected a FIXED
  -- 1.0 m/s every frame along the normalized (dvx, dvy) direction: it both
  -- ignored the frame_dv_cap servo output and dumped the whole 1.0 m/s into
  -- y whenever dvx passed through zero, chattering the car sideways instead
  -- of walking it inboard. Every world delta in this file is now built as a
  -- sum of SCALED UNIT AXES.
  addSubjectVelocity(state, vehicle,
    toWorldDir(state, vec3(1, 0, 0)) * dvx
    + toWorldDir(state, vec3(0, 1, 0)) * dvy)
end

local function binIndexFor(lx)
  local index = math.floor((lx + B.field_hw) / B.bin_pitch)
  if index < 0 then index = 0 end
  if index > (#B.bin_values - 1) then index = #B.bin_values - 1 end
  return index
end

-- SCORING INTEGRITY (2026-08-15, serial 79). Two defects, both of which let
-- the machine pay for outcomes it had itself declared were not outcomes.
--
-- 1. A CONCESSION PAID. `b.conceded` only ever chose a LABEL, inside the
--    "above the bin mouths" branch. A conceded car that had come to rest
--    lower than that fell through to the ordinary bin branch and was paid in
--    full: serial 78 paid 2500 for bin 2 after 48.5 s and 12 raps, and 375
--    after 23.9 s. The machine spent three quarters of a minute failing to
--    free a car, announced that it had given up, and then scored it. A
--    concession is the machine's own verdict that the play is unrecoverable;
--    it now pays nothing wherever the car happens to be sitting, and the
--    verdict is checked FIRST so no position can route around it.
--
-- 2. A RESCUED PLAY SET RECORDS. `b.pegTier` existed and was never emitted
--    and never consulted. At tier 3 all 28 pegs are 0.22 m nubs - there is no
--    lattice left - and a car falling through that could set `stats.best` and
--    increment `stats.jackpots` exactly as if the board had decided it.
--
--    THE HONEST LINE, drawn where the board stops being the board: tier 1
--    takes ONE peg half in. That is a nudge, the lattice is intact, and the
--    fall is still the board's - it scores normally. Tier 2 and 3 take a
--    whole row or the whole field out; whatever the car does after that is
--    the machine's doing, not the player's. Those plays are ASSISTED: they
--    still PAY, because the ball really did end up in that bin and a zero
--    would punish the player for the machine's own rescue, but they cannot
--    set `stats.best` and cannot be counted as a jackpot, and the message
--    says so rather than quietly recording a record nobody earned.
--
-- Both facts now leave the machine on `pachinko_scored` (`conceded`,
-- `peg_tier`, `assisted`), so a census can separate earned results from
-- rescued ones without re-deriving them from the event order.
local function payout(state, lx, ly, lz)
  local b = state.behavior
  b.stats.plays = b.stats.plays + 1
  -- The engine's own read of where the car is, next to the geometric one, so
  -- a disagreement shows up in the log instead of being silently averaged.
  local inCatch = zoneOccupants(state, "catch_zone")[b.subjectId] ~= nil
  local tier = b.pegTier or 0
  local assisted = tier >= 2
  local label, value, index
  if b.conceded then
    -- Checked before every geometric branch, deliberately: the whole defect
    -- was that a position could out-vote the verdict.
    label = "The board has it. TILT gives up - no score."
    value = 0
    b.markerMode = "search"
    b.markerTarget = nil
  elseif lz > B.score_max_z
    and lz > B.ridge_band_lo and lz < B.ridge_band_hi
    and math.abs(lx) <= B.field_hw then
    -- F1: STRADDLING A MOUTH IS NOT "HUNG ON THE BOARD". Every mouth on this
    -- machine is narrower than a car chord by design, so a car stopped across
    -- one has nearly scored, and telling a player watching their car sit
    -- square in the jackpot's mouth that it is hung on the board is simply
    -- wrong. Name the bin, drive the marker to its tick, and pay a stated
    -- fraction. This cannot reopen the old "paid the jackpot it was blocking"
    -- defect, because the value is explicitly reduced and the message says
    -- both which bin and that it is a partial.
    index = binIndexFor(lx)
    local full = B.bin_values[index + 1] or 0
    value = math.floor(full * B.straddle_pay_fraction)
    b.markerMode = "value"
    b.markerTarget = B.bin_centers[index + 1] or 0
    label = string.format(
      assisted and "ACROSS THE MOUTH of bin %d - pins pulled, %d of %d, no record."
        or "ACROSS THE MOUTH of bin %d - part payout, %d of %d.",
      index + 1, value, full)
    setEffectActive(state, "bin_dust_" .. index, true)
  elseif lz > B.score_max_z then
    -- Not down in a pocket and not across a mouth: wedged in the pegs, hung
    -- on the crown chute, or perched ON a divider body. The old guard sat at
    -- ridge + 1.0 - above any resting ref node - so a car sitting on the
    -- jackpot's own horn was PAID the jackpot it was blocking.
    -- A CONCESSION AND A TIMEOUT ARE DIFFERENT EVENTS AND SHOULD NOT READ THE
    -- SAME. The concession is handled in the first branch above, because it
    -- has to out-rank position; what is left here is the timeout.
    label = "HUNG ON THE BOARD - no score."
    value = 0
    b.markerMode = "search"
    b.markerTarget = nil
  elseif lx > B.field_hw + 0.4 then
    label, value = "GUTTER - back to the loader. No score.", 0
    b.markerMode = "search"
    b.markerTarget = nil
  elseif lx < -B.field_hw - 0.4
    or ly > B.depth_half + 0.6
    or ly < B.bin_y_front - 1.0 then
    label, value = "OFF THE BOARD - no score.", 0
    b.markerMode = "search"
    b.markerTarget = nil
  else
    index = binIndexFor(lx)
    value = B.bin_values[index + 1] or 0
    b.markerMode = "value"
    b.markerTarget = B.bin_centers[index + 1] or 0
    if value >= 10000 then
      if assisted then
        -- Not a jackpot. The field was taken away before this landed, and
        -- the machine says so out loud rather than banking the record.
        label = string.format(
          "ASSISTED - pins pulled. Middle bin, %d points, no record.", value)
      else
        label = string.format("JACKPOT! Middle bin - %d points!", value)
        b.stats.jackpots = b.stats.jackpots + 1
      end
    elseif assisted then
      label = string.format(
        "ASSISTED - pins pulled. Bin %d, %d points, no record.",
        index + 1, value)
    else
      label = string.format("Bin %d - %d points.", index + 1, value)
    end
    setEffectActive(state, "bin_dust_" .. index, true)
  end
  -- P0.4, THE CENSUS. Decided here because payout() is the ONE funnel every
  -- terminal outcome goes through - concession, timeout, straddle, gutter and
  -- score alike - so a class assigned here is assigned to every play that
  -- ends, which is what "exhaustive by construction" has to mean in code and
  -- not only in prose.
  local reachedBin = (index ~= nil) and not b.conceded and lz <= B.score_max_z
  local censusClass, censusCounted, censusSource
  if reachedBin and (b.rapCount or 0) == 0 then
    censusClass, censusCounted, censusSource = "clean", true, "outcome"
  elseif b.censusStopClass then
    censusClass, censusCounted, censusSource = b.censusStopClass, true, "first_rap"
  else
    local now = censusClassify(state)
    if now == CENSUS_UNKNOWN then
      if b.censusRead then
        -- The sensor DID read cleanly earlier this play and found the car in
        -- no declared box; only this last read failed. That is knowledge, and
        -- the class it supports is the catch-all - which is a fault.
        censusClass, censusCounted, censusSource = "unclassified", true, "at_rest"
      else
        -- Never got a clean read. DROP THE PLAY. Not clean, not a fault, not
        -- in the denominator - because a classifier that guesses fabricates.
        censusClass, censusCounted, censusSource = CENSUS_UNKNOWN, false, "at_rest"
      end
    elseif now then
      censusClass, censusCounted, censusSource = now, true, "at_rest"
    else
      censusClass, censusCounted, censusSource = "unclassified", true, "at_rest"
    end
  end
  -- FIXED 2026-08-18, D3. THIS WAS THE ONE AGGREGATION THE CODE PERFORMED AND
  -- IT MERGED EXACTLY WHAT THE EVENT KEYS SEPARATE: `sensor_unknown` went
  -- into the same histogram as the eight real classes, so any readout over
  -- b.stats.census - the natural thing to read - had the dropped plays back
  -- in the denominator, and the separation survived only as a comment on the
  -- event payload. The discriminator is `censusCounted`, the SAME value the
  -- event carries as `census_counted`, so the in-memory tally and the event
  -- stream cannot disagree about which plays are in the census.
  b.stats.census = b.stats.census or {}
  b.stats.census_dropped = b.stats.census_dropped or 0
  if censusCounted then
    b.stats.census[censusClass] = (b.stats.census[censusClass] or 0) + 1
  else
    -- Not a class and not a count of one: a play the sensor could not read.
    -- It is kept as a scalar rather than a one-key table precisely so that
    -- nothing can iterate it alongside the classes and sum the two.
    b.stats.census_dropped = b.stats.census_dropped + 1
  end
  -- Records are for plays the BOARD decided. See the assisted/conceded note
  -- above payout: a rescued or conceded play may pay, but it may not stand.
  if not assisted and value > (b.stats.best or 0) then b.stats.best = value end
  b.paid = true
  b.lastValue = value
  b.lastBin = index
  showMessage(label, 4.0)
  emitEvent(state, "I", "pachinko_scored", {
    subject_id = b.subjectId,
    bin = index,
    value = value,
    rest_x = lx,
    rest_y = ly,
    rest_z = lz,
    in_catch_zone = inCatch,
    raps = b.rapCount or 0,
    plays = b.stats.plays,
    best = b.stats.best,
    -- THE PROVENANCE OF THIS SCORE, so a census never has to infer it from
    -- event ordering again. `peg_tier` is how much of the lattice had been
    -- taken away when the car came to rest (0 = none, 1 = one peg half in,
    -- 2 = a row, 3 = the whole field); `assisted` is tier >= 2, i.e. the
    -- board was no longer the board; `conceded` is the machine's own verdict
    -- that the play was unrecoverable.
    peg_tier = tier,
    assisted = assisted,
    conceded = b.conceded and true or false,
    -- P0.4. THE census line. `census_counted = false` means the sensor could
    -- not read the roster at any point in this play and the play is OUT of
    -- the denominator; `census_class = "unclassified"` means it IS in the
    -- denominator and IS a fault. The two must never be conflated in a
    -- readout, so they are separate keys.
    census_class = censusClass,
    census_counted = censusCounted,
    census_source = censusSource,
  })
  setPhase(state, "payout")
end

local function updateIdle(state, dtSim)
  local b = state.behavior
  if b.lift > 0 or b.tip > 0 or b.gate ~= 0 then
    setPhase(state, "returning")
    return
  end
  -- PUT THE PINS BACK, and nowhere else. Idle is the only phase in which the
  -- fall volume is meant to be empty, and pegRestore re-checks field_zone
  -- anyway - so a car still hung on the board simply keeps the field
  -- retracted until it is gone. Retried on a slow timer rather than every
  -- frame: the check is free but the queueLuaCommand behind it is not.
  if b.pegRetracted then
    b.pegRestoreTimer = (b.pegRestoreTimer or 0) + dtSim
    if b.pegRestoreTimer >= 1.0 then
      b.pegRestoreTimer = 0
      pegRestore(state)
    end
  end
  if b.idleGrace and b.idleGrace > 0 then
    b.idleGrace = b.idleGrace - dtSim
    return
  end
  -- Occupancy poll, not a crossing: see structural rule 3 at the top. The
  -- hoist slip-abort drops a car onto the loading floor, and a normal play
  -- that never left the deck comes home standing on it - both inside
  -- load_zone. Without this poll the tower would sit there forever waiting for
  -- an entry event that can no longer happen.
  local vehicle = firstOccupant(state, "load_zone")
  if vehicle then armLoading(state, vehicle) end
end

local function updateLoading(state, dtSim)
  local b = state.behavior
  local vehicle = sampleSubject(state, dtSim)
  if not vehicle then
    vehicle = firstOccupant(state, "load_zone")
    if not vehicle then
      dropSubject(state)
      b.idleGrace = B.rearm_grace_seconds
      setPhase(state, "idle")
      return
    end
    b.subjectId = vehicle:getId()
    b.lastPos = nil
    -- A DIFFERENT car just became the subject, so it has not held still for
    -- anything yet. Without this the incoming car inherited the previous
    -- one's parkTimer and could be hoisted within a frame or two of arriving,
    -- while still rolling.
    b.parkTimer = 0
    b.lastCount = nil
    return
  end
  if b.speed <= B.park_speed_max then
    b.parkTimer = b.parkTimer + dtSim
  else
    b.parkTimer = 0
    b.lastCount = nil
  end
  local remaining = B.park_seconds - b.parkTimer
  local count = math.max(0, math.ceil(remaining))
  if b.parkTimer > 0.15 and count ~= b.lastCount and count > 0 then
    b.lastCount = count
    showMessage(string.format("Hoisting in %d...", count), 0.9)
  end
  if b.parkTimer >= B.park_seconds then
    -- Measure this vehicle's own ref-node height above the deck it is
    -- standing on and make THAT the servo set-point, so the car is held
    -- exactly where contact was already holding it and settles with no drop
    -- when the deck's collision re-bakes at the dock.
    local measured = (b.lz or 0) - B.deck_home_z
    if measured >= B.car_rest_height_min and measured <= B.car_rest_height_max then
      b.restHeight = measured
    else
      b.restHeight = B.car_rest_height
    end
    b.liftRate = B.hoist_speed_mps
    b.rapCount = 0
    -- P0.4: reset the census latch with the rap count it is twinned to. A
    -- class left over from the previous play would be reported against this
    -- one, which is the quietest possible way to poison a census.
    b.censusStopClass = nil
    b.censusRead = false
    showMessage("GOING UP!", 2.0)
    emitEvent(state, "I", "pachinko_hoist_started", {
      subject_id = b.subjectId,
      rest_height = b.restHeight,
    })
    setPhase(state, "hoist")
  end
end

-- Lowest tracked node in AUTHORED z. The model transform is a 180 deg yaw
-- about Z, so z is unchanged by it and the origin offset is the whole
-- conversion. Returns nil when the set was never captured, so callers can fall
-- back to the old ref-node test rather than silently gating on nothing.
local function lowestNodeZ(state, vehicle)
  local b = state.behavior
  if not vehicle or not b.lowNodes or not vehicle.getNodePosition then return nil end
  local plateZ = B.deck_home_z + (b.lift or 0)
  local zs = {}
  local ok = pcall(function()
    for k = 1, #b.lowNodes do
      local np = vehicle:getNodePosition(b.lowNodes[k])
      if np then
        -- PROJECT ON THE MODEL AXIS, do not take raw world z. The old code
        -- justified raw z with "the transform is a 180 degree yaw", but the
        -- model rotation carries the PROP's own rotation too, so a tilted
        -- placement broke it. localOf already does this properly.
        local world = vehicle:getPosition() + np
        local _, _, lz = localOf(state, world)
        -- F-4: A DETACHED NODE POISONS A MIN. Nodes are never destroyed in
        -- BeamNG - beams break - so a shed wheel or bumper node keeps
        -- existing and falls away forever. A min over six nodes follows it
        -- down, making "on the plate" permanently true and re-admitting the
        -- very levitation this gate exists to exclude. Anything implausibly
        -- far below the plate is not the car resting, it is debris.
        if lz > plateZ - 1.0 then zs[#zs + 1] = lz end
      end
    end
  end)
  if not ok or #zs == 0 then return nil end
  -- MEDIAN, not min: one bad sample cannot move it.
  table.sort(zs)
  return zs[math.floor((#zs + 1) / 2)]
end

-- THE EASE-OUT (2026-08-14h). Commanded carriage rate as a function of how
-- much travel is LEFT, not of how much time has passed - so the profile is
-- exact no matter what dtSim really is on the player's machine, exactly like
-- the cruise speed it replaces. Constant deceleration to a standstill at the
-- dock: v = sqrt(2 a s), capped at the cruise speed, floored at a creep so
-- the last centimetre closes in finite frames. See THE HOIST EASE-OUT in
-- spec.py for why a is derived from dock_settle_seconds and why it has to
-- stay under g.
local function hoistCommandRate(b)
  local remaining = B.lift_travel - (b.lift or 0)
  if remaining <= 0 then return 0 end
  local v = math.sqrt(2 * B.hoist_taper_decel * remaining)
  if v > B.hoist_speed_mps then v = B.hoist_speed_mps end
  if v < B.hoist_creep_mps then v = B.hoist_creep_mps end
  return v
end

local function updateHoist(state, dtSim)
  local b = state.behavior
  b.lift = math.min(B.lift_travel, b.lift + hoistCommandRate(b) * dtSim)
  -- Re-read AFTER the step: the servo has to be told the rate the carriage is
  -- doing NOW, and on the taper that is a different number every frame. The
  -- old square command set this to hoist_speed_mps for the whole ride and
  -- then to 0 in one frame, which is the discontinuity the player saw as
  -- light cars flying off the deck at the top.
  b.liftRate = (b.lift < B.lift_travel) and hoistCommandRate(b) or 0
  -- "GIVE IT A FLOOR" WAS TRIED HERE AND FAILED (2026-08-14e). For the whole
  -- 43 m ride the deck's collision sits at its HOME bake, so the car is not
  -- standing on anything for 13.5 s. The three-point attitude trace proves
  -- that is what wrecks the arrival - every play starts near level and arrives
  -- tilted, monotonically (8.3->28.1->39.5, 3.8->36.8->81.0, 3.8->14.3->20.0,
  -- 0.6->6.6->15.1, 13.4->45.8->71.6 degrees) - because a velocity servo
  -- applies no torque and any rate picked up at lift-off integrates for the
  -- entire ride.
  --
  -- The obvious cure is to re-bake the deck periodically through the hoist so
  -- the car rides the plate. IT DOES NOT WORK, AND THE CONFORMAL BAKE LAW IS
  -- EXACTLY WHY. The tempting argument is that the servo holds the car at
  -- restHeight above the deck's drawn pose, so a bake stamps the plate right
  -- where the car already rests. But the car is NOT resting on the drawn deck
  -- during the hoist - it is FLYING at that height, with no contact at all.
  -- A bake therefore stamps a plate into a body in free flight, the solver
  -- resolves the fresh overlap by throwing it, and the car is destroyed within
  -- the first second: measured at 0.9 s intervals, the attitude trace read
  -- 98.8 / 59.0 / 43.0 degrees of tilt by ref_z 8 m - barely off the loading
  -- floor - and every play aborted before the crown.
  --
  -- The law's real content is that there is no safe bake pose for a subject
  -- that is not conformally resting on something. A floor cannot be introduced
  -- under a flying car by stamping one; the car has to never fly, and snapshot
  -- collision cannot give continuous support to a platform that moves. Curing
  -- this properly means changing the carry mechanism, not the bake schedule.
  local vehicle, lx, ly, lz = sampleSubject(state, dtSim)
  if not vehicle then
    setPhase(state, "returning")
    return
  end
  -- Off-deck abort: the car is no longer above the deck, so stop pretending
  -- to hold it and let gravity have it. It lands on the loading floor, which
  -- is inside load_zone - the idle occupancy poll re-arms from there.
  local deckZ = B.deck_home_z + b.lift
  if math.abs(lx - B.deck_center_x) > B.deck_half_x + B.slip_margin_m
    or math.abs(ly) > B.deck_half_y + B.slip_margin_m
    or lz < deckZ - B.slip_drop_m then
    showMessage("LOAD SLIPPED - aborting the hoist.", 2.6)
    emitError(state, "hoist_load_slipped", {x = lx, y = ly, z = lz})
    dropSubject(state)
    setPhase(state, "returning")
    return
  end
  hoistServo(state, vehicle, lz)
  if b.lift >= B.lift_travel then
    b.lift = B.lift_travel
    b.liftRate = 0
    -- Re-bake so the deck is a REAL surface again before the car is asked
    -- to rest on it. Bake 1 of 3.
    requestCollisionReload(state)
    b.seated = false
    showMessage("Docked. Opening the release gate...", 2.2)
    setPhase(state, "dock")
  end
end

local function updateDock(state, dtSim)
  local b = state.behavior
  local vehicle = sampleSubject(state, dtSim)
  -- THE SEAT DROP (2026-08-14h), and the measurement that forced it.
  --
  -- The square hoist command used to STOP DEAD at the dock while the car was
  -- still climbing at 8 m/s, and the servo could only shed frame_dv_cap per
  -- frame, so the car sailed on past the plate and then fell back onto it.
  -- Measured over the s51 n=15: the car was 1.1-1.4 m above the plate at the
  -- moment the carriage stopped. THAT FALL WAS DOING REAL WORK AND NOBODY
  -- KNEW IT. A hoisted car arrives TILTED - the servo applies no torque, so
  -- any rate it picks up at lift-off integrates for the whole ride - and the
  -- landing is what flattened it out again. Contact is the only thing in this
  -- machine that can right a car (THE NO-TORQUE LAW), and the overshoot was
  -- an accidental source of it.
  --
  -- Remove the overshoot (which is exactly what the player asked for) and the
  -- righting goes with it. Measured, back to back, same rig, n=5 attitude
  -- probe: arrival tilt 2.6 deg -> 15.1 deg, and the following n=15 scored
  -- 0 of 8 with every single play stalling ON THE DECK LIP - up-vector z
  -- 0.75-0.87, creeping inboard 0.2 m per kick over nine and ten kicks and
  -- never going airborne over the convex break.
  --
  -- So the drop becomes DELIBERATE and BOUNDED instead of a side effect of
  -- how hard the servo was overshooting. One impulse, once, straight down,
  -- onto a plate that has already been re-baked and is genuinely there. It is
  -- sized against the drop seatLiftNow() already sets up rather than against
  -- the whole landing: the droop lift leaves the car hoist_seat_lift_m above
  -- the plate at rest, gravity does most of the work, and this tap just makes
  -- sure it arrives HARD enough to squash the suspension flat instead of
  -- feathering down. Total arrival is ~5.4 m/s, inside rap_dv_max_mps (7.0)
  -- and nowhere near the ~19 m/s single-frame injection that shredded cars on
  -- the centrifuge.
  --
  -- WHY IT IS HERE AND NOT AT THE END OF updateHoist: the bake is a REQUEST.
  -- Pressing a car downward in the same frame the plate is asked for risks
  -- pushing it through a surface that does not exist yet. dock_seat_delay
  -- gives the bake its frame, and the impulse still lands 1.4 s before the
  -- lowest-node scan at the end of the settle - which is the whole point,
  -- because that scan has to capture the wheels of a SEATED car, not the
  -- flank panels of a tilted one.
  if not b.seated and b.elapsed >= B.dock_seat_delay_seconds then
    b.seated = true
    if vehicle and (b.speed or 0) <= B.runaway_speed_mps then
      addSubjectVelocity(state, vehicle,
        toWorldDir(state, vec3(0, 0, 1)) * (-B.dock_seat_dv_mps))
      emitEvent(state, "I", "pachinko_seated", {
        subject_id = b.subjectId,
        dv = B.dock_seat_dv_mps,
        z = b.lz,
      })
    end
  end
  if b.elapsed >= B.dock_settle_seconds then
    -- THE PLATE DATUM (2026-08-14d). Measured HERE, once, at the end of the
    -- dock settle. It is PURE TELEMETRY: it was briefly wired into the two
    -- on-the-plate gates as a fix for the crown-settle failure, the live A/B
    -- said 8-of-15 became 4-of-15 with the same five crown failures, and the
    -- gates were reverted. The measurement stays because it is the most
    -- informative number this machine emits and the next round needs it.
    --
    -- WHAT THE PROBE FOUND. The instrument sampled the car's whole node cloud
    -- every frame through dock and arming. In a LOST play the car's lowest
    -- node sits at exactly 44.000 - dead on the plate, to the millimetre -
    -- while its REF node reads 44.56 to 44.95. Nothing was holding the car up.
    -- Nothing was floating. The car was standing on the deck the whole time.
    -- What differs between a good play and a lost one is only the distance
    -- from a car's ref node to its own lowest contact: 0.20-0.31 m fresh,
    -- 0.57-0.95 m once its suspension has settled differently or it has taken
    -- damage from earlier plays.
    --
    -- Every downstream "is it on the plate" test compared the REF node to the
    -- absolute plane plus lip_kick_lift_max_m (44.50). So a car resting
    -- perfectly on the deck read as LEVITATING the moment its ref-to-contact
    -- distance passed 0.50 m, and the machine then withheld the two impulses -
    -- the kicker's lift and the unstick hop - that are the only things which
    -- move it. It was not a bake, not a servo, and not a phantom surface: it
    -- was a PROXY. The separation is exact: every build-38 play whose arming
    -- ref exceeded 44.50 was lost, every play under it scored.
    --
    -- So the datum is per-car and per-play: where THIS car's ref node actually
    -- sits when THIS car is resting on the plate. Then "on the plate" means
    -- "near where it settled", which is true regardless of ride height, damage
    -- or suspension state. Fall back to the old absolute only if the sample is
    -- missing or absurd.
    local settled = b.lz
    if settled and settled > B.deck_home_z + b.lift - 1.0
      and settled < B.deck_home_z + b.lift + B.car_rest_height_max then
      b.plateRef = settled
    else
      b.plateRef = B.deck_home_z + b.lift + B.car_rest_height
    end
    -- THE LOWEST-NODE SET. Build 39 failed because it rebased the plate gates
    -- on a per-car CONSTANT measured once here - and a constant is exactly what
    -- a tilted car invalidates. The right quantity is the car's LOWEST NODE:
    -- seated, it is on the plate at any attitude; levitating, the whole car is
    -- high and every node with it. So this gate is tighter AND more correct at
    -- once, and unlike build 39's it cannot re-admit build 22's levitation.
    --
    -- Cost is why it is done THIS way. Scanning the whole node cloud every
    -- frame is not affordable from GE, but scanning it ONCE per play at the one
    -- moment the car is known to be resting is free, and tracking the six
    -- lowest nodes after that is six queries a frame during tipping only.
    -- PCALL: getNodeCount can exist while getNodePosition(i) throws - a
    -- trailer, a mod vehicle, node data not ready. A throw here would
    -- take the whole frame down with it (see PHASE_TIMEOUT).
    local scan = exactVehicle(b.subjectId)
    b.lowNodes = nil
    local scanOk = pcall(function()
    if scan and scan.getNodeCount then
      local count = scan:getNodeCount() or 0
      local picks = {}
      for i = 0, count - 1 do
        local np = scan:getNodePosition(i)
        if np then picks[#picks + 1] = {i = i, z = np.z} end
      end
      if #picks > 0 then
        table.sort(picks, function(p1, p2) return p1.z < p2.z end)
        b.lowNodes = {}
        for k = 1, math.min(6, #picks) do b.lowNodes[k] = picks[k].i end
      end
    end
    end)
    if not scanOk then b.lowNodes = nil end
    emitEvent(state, "I", "pachinko_plate_datum", {
      subject_id = b.subjectId,
      plate_ref = b.plateRef,
      above_plate = b.plateRef - (B.deck_home_z + b.lift),
      hoist_rest_height = b.restHeight,
    })
    setPhase(state, "arming")
  end
end

local function updateArming(state, dtSim)
  local b = state.behavior
  sampleSubject(state, dtSim)
  local t = math.min(1, b.elapsed / B.gate_seconds)
  local smooth = t * t * (3 - 2 * t)
  b.gate = B.gate_open_deg * smooth
  if t >= 1 then
    b.gate = B.gate_open_deg
    -- The gate is a collision part too; bake it at the open endpoint before
    -- anything can arrive at the chute throat. Bake 2 of 3.
    requestCollisionReload(state)
    b.tip = 0
    showMessage("EJECTING!", 1.6)
    setPhase(state, "tipping")
  end
end

local function updateTipping(state, dtSim)
  local b = state.behavior
  local vehicle, lx, ly, lz = sampleSubject(state, dtSim)
  if not vehicle then
    setPhase(state, "returning")
    return
  end
  -- The car has left the deck once it is inboard of the hinge line or has
  -- dropped clear of the chute: that IS the release, read from geometry.
  -- Checked before the eject field runs so a car that drives itself off
  -- early hands over the moment it happens.
  local hingeX = B.deck_center_x - B.deck_half_x
  if lx < hingeX - 0.2 or lz < B.deck_home_z + b.lift - 2.0 then
    b.rapCount = b.rapCount or 0
    emitEvent(state, "I", "pachinko_released", {subject_id = b.subjectId, x = lx, z = lz})
    setPhase(state, "falling")
    return
  end
  -- The eject. The deck stays LEVEL on its dock bake (b.tip stays 0 while
  -- the car is aboard - THE CONFORMAL BAKE LAW, see BEHAVIOR); the field
  -- walks the car inboard over the hinge lip onto the chute's static ice.
  -- The tip itself plays as an empty-deck flourish in updateFalling.
  if b.rideY == nil then b.rideY = ly or 0 end
  ejectServo(state, vehicle)
  local inLipZone = lx < B.deck_center_x - B.deck_half_x + B.lip_kick_zone_m
  -- Unstick hop: tyres unloaded for a moment so the field can actually
  -- move a car that is gripping the deck rather than sliding on it. It is
  -- SUPPRESSED inside the lip zone: there the car should be going ballistic
  -- off the kicker, and a hop landing in the same frame as a kick would sum
  -- their vertical components (2.0 + 2.6) into an impulse neither was sized
  -- for, aimed straight at the chute hood.
  --
  -- F8: AND IT NEEDS THE SAME ALTITUDE GATE THE KICKER HAS. A 2.0 m/s tap is
  -- 0.816 s of flight against a 0.9 s interval, so a settled car is back on
  -- the plate for only ~84 ms between hops - and any bounce, kerb landing or
  -- frame dip that delays the touchdown stacks the next hop onto a car that
  -- is still airborne. That is build 22's levitation, rebuilt out of the
  -- other primitive. Reuse the kicker's own test: hop only from the plate.
  b.hopTimer = (b.hopTimer or 0) + dtSim
  -- REVERTED 2026-08-14d. This was briefly rebased on the measured plate
  -- datum (b.plateRef) on the theory that a car whose ref node sits high
  -- above its own wheels is still on the deck and was being wrongly
  -- denied its hop. The theory was WRONG, or at least incomplete, and
  -- the live A/B says so: build 38 scored 8 of 15, build 39 with the
  -- rebased gate scored 4 of 15 and produced the SAME five crown
  -- failures. Loosening this gate re-admits build 22's levitation for
  -- the cars that really are airborne, and that costs more than the
  -- seated cars it rescues. The absolute plane stays until something
  -- measures better than it.
  -- LOWEST-NODE GATE (2026-08-14f), with the old ref-node test kept only as
  -- the fallback for a play whose node scan never happened.
  local plateZ = B.deck_home_z + b.lift
  local lowZ = lowestNodeZ(state, vehicle)
  local hopOnPlate
  if lowZ ~= nil then
    hopOnPlate = lowZ < plateZ + B.plate_contact_m
  else
    hopOnPlate = lz < plateZ + B.lip_kick_lift_max_m
  end
  if b.hopTimer >= B.eject_hop_interval_seconds and not inLipZone and hopOnPlate then
    b.hopTimer = 0
    addSubjectVelocity(state, vehicle,
      toWorldDir(state, vec3(0, 0, 1)) * B.eject_hop_dv_mps)
  end
  -- The kicker at the lip. A bounded impulse throws the car over the convex
  -- deck/chute break airborne. It RE-ARMS ON A TIMER, not on position: the
  -- first cut only re-armed once the car had drifted 1.9 m back OUTBOARD,
  -- which nothing in the machine can produce (the field commands inboard the
  -- whole time), so a car that failed to clear got exactly one kick and then
  -- sat in the lip zone until the release timed out. Successive kicks
  -- escalate on the same 1.35 ladder the field knocker uses.
  if inLipZone then
    b.kickTimer = (b.kickTimer or B.lip_kick_interval_seconds) + dtSim
    if b.kickTimer >= B.lip_kick_interval_seconds then
      b.kickTimer = 0
      b.kicks = (b.kicks or 0) + 1
      local scale = math.pow(1.35, b.kicks - 1)
      if scale > B.lip_kick_scale_max then scale = B.lip_kick_scale_max end
      -- Scaled unit axes, not a composite local vector: |(-4.0, 0, 2.6)| is
      -- 4.771, and the normalizing toWorldDir was reducing the whole kick to
      -- 1.0 m/s - 0.545 m/s of it upward, a 15 mm hop instead of the authored
      -- 0.34 m. Live 2026-08-14 that left the car dribbling over the lip with
      -- no energy: one play stalled at x 12.13 on the 40 deg chute and sat
      -- there for the entire 75 s fall timeout.
      -- A KICK LIFTS ONLY WHEN THE CAR IS BACK DOWN ON THE PLATE. The job of
      -- the vertical component is to get a car that is SITTING on the deck
      -- airborne over the convex break; repeating it while the car is already
      -- airborne just JUGGLES it (live build 22: four successive kicks held an
      -- etk800 at z 45.07-45.13, a metre clear of the plate, drifting inboard
      -- 0.4 m per kick without ever landing).
      --
      -- The first cut gated on the kick INDEX (b.kicks == 1), but the
      -- condition that actually discriminates is ALTITUDE. A car bumped by
      -- kick 1 that settles back down OUTBOARD of the lip zone re-arms
      -- kickTimer without re-arming b.kicks, so every later kick was pure
      -- horizontal - and pure horizontal is exactly the creep-and-belly-ground
      -- failure on the convex break that the kicker exists to prevent. Gating
      -- on the plate keeps the proven-healthy first kick identical (kick 1
      -- always has the car on the deck) and cannot reintroduce levitation,
      -- because levitation IS the car being ~1 m above the plate.
      -- MEASURED, not reasoned: gating on altitude ALONE is wrong, because
      -- altitude does not separate the two cases. Live over 28 kicks, cars
      -- entering the lip zone sat 0.80-1.05 m above the plate, and build 22's
      -- levitation sat at 1.07-1.13 m - the bands touch. An altitude-only
      -- gate stripped the lift from 22 of those 28 kicks and the score rate
      -- collapsed to 1 in 10.
      --
      -- So the gate is the UNION of the two conditions, which is a strict
      -- superset of the proven-healthy build 23 behaviour: kick 1 always
      -- lifts (there the car is by construction still parked on the plate,
      -- and that is the configuration that scored), and a LATER kick lifts
      -- only if the car has provably settled back down onto it. Levitation
      -- needs repeated lift while airborne, and that is exactly the
      -- combination this excludes.
      -- Absolute plane, and REVERTED to it 2026-08-14d for the reason
      -- spelled out at hopOnPlate: the measured-datum version halved the
      -- score in a live A/B without curing a single crown failure.
      -- Same lowest-node gate as the hop: a car resting on the plate at ANY
      -- attitude passes it, and a car that is genuinely airborne cannot.
      local onPlate
      if lowZ ~= nil then
        onPlate = lowZ < plateZ + B.plate_contact_m
      else
        onPlate = lz < plateZ + B.lip_kick_lift_max_m
      end
      local kz = (b.kicks == 1 or onPlate) and (B.lip_kick_z_mps * scale) or 0
      addSubjectVelocity(state, vehicle,
        toWorldDir(state, vec3(1, 0, 0)) * (-B.lip_kick_x_mps * scale)
        + toWorldDir(state, vec3(0, 0, 1)) * kz)
      showMessage("KICKER!", 1.2)
      emitEvent(state, "I", "pachinko_kicked", {x = lx, z = lz, kick = b.kicks})
    end
  else
    -- Outboard of the lip zone the next arrival gets a fresh first kick.
    b.kickTimer = B.lip_kick_interval_seconds
  end
end

local function updateFalling(state, dtSim)
  local b = state.behavior
  -- The empty-deck tip FLOURISH: the car is gone, so the drawn plate may
  -- sweep to full tip as pure theater - the crown collision stays at the
  -- level dock bake it already holds and NOTHING re-bakes (nothing stands
  -- on the deck to care). updateReturning levels it on the way home.
  --
  -- Gated on the carriage actually BEING at the crown. behavior.onEnter's
  -- adopt path (a loose car that arrives in field_zone without being hoisted)
  -- sets phase = falling with b.lift == 0, and without this guard the empty
  -- flourish stood the LOADING deck up 68 degrees in the bay at ground level
  -- while its collision stayed flat - a drawn plate players drive straight
  -- through, at the one place in the machine a player is guaranteed to be.
  if b.lift > B.lift_travel - 0.5 and b.tip < B.tip_full_deg then
    b.tip = math.min(B.tip_full_deg,
      b.tip + (B.tip_full_deg / B.tip_ramp_seconds) * dtSim)
  end
  local vehicle, lx, ly, lz = sampleSubject(state, dtSim)
  if not vehicle then
    setPhase(state, "returning")
    return
  end
  if sampleIsLost(lx, ly, lz) then
    emitEvent(state, "I", "subject_lost", {reason = "left_machine", phase = b.phase})
    dropSubject(state)
    setPhase(state, "returning")
    return
  end
  -- Settle-and-score only once the car is genuinely DOWN IN a pocket (or on
  -- the ground in front of them); anything resting higher - divider bodies,
  -- horns, peg bridges - stays in the knocker's jurisdiction below.
  if lz < B.score_max_z and b.speed < B.settle_speed_mps then
    b.settleTimer = b.settleTimer + dtSim
    if b.settleTimer >= B.settle_seconds then
      payout(state, lx, ly, lz)
    end
    return
  end
  b.settleTimer = 0
  -- Anti-hang knocker. The two-peg bridge this was written for is GONE since
  -- the 2026-08-14 lattice (crowns 7.60 m apart against a 5.148 m car chord),
  -- so this is now the backstop for the poses geometry cannot rule out: hung
  -- on the crown chute, planted between two divider horns, or cradled in a
  -- groove a soft body presses into a peg flank. Single bounded impulses on a
  -- fixed interval, never a per-frame push, and the direction carries a
  -- genuine UP component - a downward rap cannot lift a car off whatever
  -- gravity is holding it on.
  if lz >= B.score_max_z then
    -- A STUCK SPELL ENDS ON DESCENT, NOT ON MOTION. The first cut cleared
    -- stuckTimer/rapTimer/spellRaps whenever b.speed rose above
    -- rap_speed_mps - which every rap does by construction, since a rap is a
    -- 3+ m/s impulse. So the escalation reset to 3.1 m/s after every single
    -- rap and the cadence stretched from the authored 1.6 s to
    -- rap_idle + rap_interval = 3.8 s. Measured live 2026-08-14: an etk800
    -- wedged between peg rows 7 and 8 at x 5.25, z 13.87 took only 11 raps
    -- in 57 s, none above 4.2 m/s, and never came loose - the fall timed out
    -- and paid HUNG ON THE BOARD. The spell now ends only when the car has
    -- genuinely dropped rap_descend_reset_m down the board, so a wedge gets
    -- the full escalating ladder at the authored interval and free-fall
    -- still resets it every metre.
    -- F4: ONE DEFINITION OF PROGRESS. This used to reset at
    -- rap_descend_reset_m (1.0) while the give-up tested against
    -- giveup_descend_m (0.5), which left a dead band - descend 0.5 to 1.0 m
    -- and then jam, and neither the reset nor the give-up could fire, so the
    -- ladder pinned at the cap and the play ran the full fall timeout.
    if b.markZ == nil then b.markZ = lz end
    if b.markZ - lz >= B.giveup_descend_m then
      b.markZ = lz
      b.stuckTimer = 0
      b.rapTimer = 0
      b.spellRaps = 0
      b.spellSide = nil
      b.spellChute = nil
      b.spellSeat = nil
    end
    if b.speed < B.rap_speed_mps then
      b.stuckTimer = b.stuckTimer + dtSim
    end
    if b.stuckTimer >= B.rap_idle_seconds then
      b.rapTimer = b.rapTimer + dtSim
      if b.rapTimer >= B.rap_interval_seconds then
        b.rapTimer = 0
        -- THE GIVE-UP, checked BEFORE the next rap so the previous one had a
        -- full interval to work. A car that has taken the whole escalation
        -- ladder and descended essentially nothing is not coming free - there
        -- is no torque to rotate it off, and the ladder has already capped.
        -- Concede it as a DECISION with a beat (a line, the marker driving to
        -- the null park, the dust) instead of stalling out the fall timeout.
        if (b.spellRaps or 0) >= B.giveup_spell_raps
            and ((b.markZ or lz) - lz) < B.giveup_descend_m then
          -- Do NOT showMessage here. payout() prints its own label in the same
          -- frame and would overwrite this one, so the machine's concession was
          -- invisible for four builds and the player only ever saw the generic
          -- "HUNG ON THE BOARD". The flag makes payout say it instead, once.
          b.conceded = true
          -- GIVE-UP TELEMETRY (2026-08-14i). THE ONE MEASUREMENT THAT SETTLES
          -- WHERE A HUNG CAR ACTUALLY IS. Every hang record until now was the
          -- car's REF node - a single point, which cannot tell a car draped on
          -- a peg crown apart from a car pinned against a board face 0.2 m
          -- away. This scans the whole node cloud once, at the one moment the
          -- machine has already decided the play is lost, and reports the
          -- cloud's extent in AUTHORED x/y/z plus its clearance to the four
          -- faces of the fall volume.
          --
          -- HOW TO READ IT, decided before the data arrives so the answer is
          -- not fitted to it: hung cars systematically within ~0.2 m of
          -- y = +/-depth_half (or x = +/-field_hw) confirm that a board face
          -- is the second contact and that FALL_VOLUME_GROUNDMODEL is the
          -- right lever. Hung cars sitting MID-DEPTH, clear of every face,
          -- mean the soft body is grooving around a peg crown and no
          -- groundModel can reach it - which would send the next round to the
          -- retractable pin instead of to more surface tuning.
          --
          -- Same shape as updateDock's scan and for the same reasons: pcall
          -- (getNodeCount can exist while getNodePosition throws, and a throw
          -- here takes the frame down), getNodePosition is an offset from
          -- getPosition and must go through localOf rather than raw world z,
          -- and a plausibility clamp keeps a shed node - which falls forever,
          -- because BeamNG breaks beams and never destroys nodes - out of the
          -- min/max. ONE local table rather than eight locals: this function
          -- is long and Lua's per-function local budget is finite.
          local span = {}
          local cloud = exactVehicle(b.subjectId)
          pcall(function()
            if cloud and cloud.getNodeCount and cloud.getNodePosition then
              local count = cloud:getNodeCount() or 0
              local base = cloud:getPosition()
              span.n = 0
              for i = 0, count - 1 do
                local np = cloud:getNodePosition(i)
                if np then
                  local px, py, pz = localOf(state, base + np)
                  if math.abs(px - lx) <= 6 and math.abs(py - ly) <= 6
                    and math.abs(pz - lz) <= 6 then
                    span.n = span.n + 1
                    if span.x0 == nil or px < span.x0 then span.x0 = px end
                    if span.x1 == nil or px > span.x1 then span.x1 = px end
                    if span.y0 == nil or py < span.y0 then span.y0 = py end
                    if span.y1 == nil or py > span.y1 then span.y1 = py end
                    if span.z0 == nil or pz < span.z0 then span.z0 = pz end
                    if span.z1 == nil or pz > span.z1 then span.z1 = pz end
                  end
                end
              end
            end
          end)
          emitEvent(state, "I", "pachinko_gave_up", {
            subject_id = b.subjectId,
            -- REMOVED 2026-08-18, D3. This used to carry
            --     census_class = b.censusStopClass
            -- with NO census_counted companion, and every conceded play emits
            -- this event AND, ~15 lines later, a pachinko_scored carrying the
            -- authoritative triple (class, counted, source). A reducer written
            -- the obvious way - "every event with a census_class" - therefore
            -- DOUBLE-COUNTED every conceded play, and counted it once through
            -- a key that had no `counted` gate on it, which is the precise
            -- conflation the two-key split exists to make impossible.
            -- The class is not lost: payout emits it, gated, for this same
            -- play. Concession is a REASON, not a classification, and the
            -- reason is already fully described by the fields below.
            raps = b.rapCount or 0,
            spell_raps = b.spellRaps,
            descent = (b.markZ or lz) - lz,
            rest_x = lx,
            rest_y = ly,
            rest_z = lz,
            seconds = b.elapsed,
            node_n = span.n,
            node_x_lo = span.x0,
            node_x_hi = span.x1,
            node_y_lo = span.y0,
            node_y_hi = span.y1,
            node_z_lo = span.z0,
            node_z_hi = span.z1,
            -- Clearances, signed, in metres: how far the nearest node of the
            -- cloud is from each face of the fall volume. Negative means the
            -- cloud has deformed past the collision plane.
            clear_y_front = span.y0 and (span.y0 + B.depth_half) or nil,
            clear_y_back = span.y1 and (B.depth_half - span.y1) or nil,
            clear_x_left = span.x0 and (span.x0 + B.field_hw) or nil,
            clear_x_right = span.x1 and (B.field_hw - span.x1) or nil,
          })
          -- payout reads the position and reports HUNG for anything above the
          -- bin mouths, so this cannot invent a bin; it also puts the marker
          -- into its HUNT, which is the visible half of the concession.
          payout(state, lx, ly, lz)
          return
        end
        b.rapCount = (b.rapCount or 0) + 1
        -- P0.4. THE CENSUS CLASS IS LATCHED HERE, at the machine's own first
        -- admission that the car has stopped. Writes nothing but b.census*,
        -- reads no gameplay state, and cannot change a single decision below
        -- it - deliberately, because a metric that can steer the machine it
        -- measures is not a metric.
        censusLatchStop(state)
        -- Escalate within one stuck spell: a car planted nose-down between
        -- two divider horns shrugged off flat 3.1 m/s raps live
        -- (2026-08-13), so each successive rap grows 35% up to the cap.
        b.spellRaps = (b.spellRaps or 0) + 1
        -- THE RETRACT LADDER (2026-08-14i). The knocker gets the first rap on
        -- its own, because an impulse frees most cars and a peg that is still
        -- there is what makes the board a board. From the second rap on, the
        -- machine stops trying to push the car off the pin and takes the pin
        -- away instead: the one it is draped on, then that whole row, then the
        -- field. Tiers only rise - a car drifting nearer a different peg
        -- between raps must never un-retract the one it was just freed from.
        -- The whole-field tier lands BEFORE giveup_spell_raps on purpose: at
        -- scale 0.10 there is no rest left anywhere on the lattice, so the
        -- play resolves into a bin and SCORES instead of paying nothing.
        local tier = 0
        if b.spellRaps >= B.retract_all_raps then
          tier = 3
        elseif b.spellRaps >= B.retract_row_raps then
          tier = 2
        elseif b.spellRaps >= B.retract_peg_raps then
          tier = 1
        end
        -- ONLY IN THE FIELD. Measured on serial 76: a car stalled on the
        -- CROWN CHUTE at (13.0, 44.2) - 4.5 m from the nearest peg and not
        -- even over the board - walked the whole ladder and dissolved the
        -- entire peg field, which does nothing for a car on the chute and
        -- takes the board away from the play that follows. The chute stall
        -- has its own branch (spellChute) and keeps it. Same for a car
        -- conceded down among the bin dividers: below the bin-mouth plane
        -- there are no pegs to take away.
        if tier > (b.pegTier or 0) and inPegField(lx, lz) then
          pegRetract(state, tier, lx, lz)
        end
        local dv = B.rap_dv_mps * math.pow(1.35, b.spellRaps - 1)
        if dv > B.rap_dv_max_mps then dv = B.rap_dv_max_mps end
        -- THE RAP DIRECTION IS HELD FOR A WHOLE SPELL. The first cut flipped
        -- sides on every rap, which cancels itself: applyClusterVelocityScaleAdd
        -- is a pure TRANSLATION with no torque, so a car bridged across two
        -- pegs cannot be re-oriented, only walked - and a walk that reverses
        -- every 1.6 s goes nowhere. Measured live 2026-08-14: an etk800
        -- bridged across peg row 2 hopped a full 1.0 m in z on every rap for
        -- 23 s and 39 raps, yet its x only ever oscillated between 2.4 and
        -- 3.9 (net 0.75 m) and it never descended a single row. Holding one
        -- side for the spell turns the same impulse into ~2.5 m of travel per
        -- rap; three of those cross the 7.60 m peg pitch, and the escalation
        -- ladder is what gets there. The side flips only when a
        -- NEW spell starts, so a car that walks into a fresh wedge on the far
        -- side gets walked back rather than pinned against a wall.
        -- BOTH the walk direction AND which rule applies are LATCHED for the
        -- whole spell, and the direction is derived from GEOMETRY.
        --
        -- The first cut flipped spellSide from its own previous value, so the
        -- first spell of a play always walked +x (nil -> -(-1) -> +1): toward
        -- the near wall the car entered beside, ~6 m of run against 18 m the
        -- other way, and toward the gutter read. Worse, spellSide was in none
        -- of setPhase/dropSubject/init, so play N's first rap direction
        -- depended on the parity of play N-1's spell count - hidden cross-play
        -- state that made two identical-looking runs diverge. Walking toward
        -- the board's CENTRE is both reproducible and the direction with the
        -- most board left to fall through.
        --
        -- Latching the chute/field choice matters even more, because the two
        -- branches push in OPPOSITE x. Re-tested per rap, a car near the
        -- boundary chatters across it forever: field branch shoves it +x past
        -- chute_x_lo, the chute branch shoves it back -x, markZ - lz never
        -- reaches rap_descend_reset_m so the spell never ends, the ladder pins
        -- at the cap, and the fall times out as HUNG. chute_x_lo is 6.00 =
        -- APRON_X_LO, which is exactly where every car is delivered, so this
        -- trap sat on the machine's own main line.
        if b.spellRaps == 1 then
          -- WALK TOWARD THE NEAREST GAP, NOT TOWARD THE CENTRE. This used to
          -- be `(lx > 0) and -1 or 1`, i.e. always toward x = 0 - and since F3
          -- put a peg AT x = 0 on every odd row, that policy walked every
          -- stuck car onto the one obstacle in the middle of the board. All
          -- six of build 46's remaining hangs sat at x 0.66-3.04, which is
          -- exactly where a car walked from further out arrives. The rap
          -- policy and the hang cluster pointed the same way.
          --
          -- Gaps are half a pitch either side of a peg column, so the nearest
          -- gap centre is found by rounding to the column lattice and stepping
          -- half a pitch toward whichever side the car is already nearer.
          local half = B.peg_pitch_x * 0.5
          local nearestCol = math.floor(lx / B.peg_pitch_x + 0.5) * B.peg_pitch_x
          local gap = nearestCol + ((lx >= nearestCol) and half or -half)
          if gap > B.field_hw - 1.0 then gap = nearestCol - half end
          if gap < -B.field_hw + 1.0 then gap = nearestCol + half end
          b.spellSide = (gap > lx) and 1 or -1
          -- x alone is not the chute: lx > 6.0 is true across the whole
          -- right-hand third of the PEG FIELD (even rows reach x 11.10), so
          -- the x-only test was handing the "the 40 deg slab supplies the
          -- downhill" rule to cars stuck on pegs 30 m lower - and that rule
          -- deliberately carries no lift, which is the one thing that unseats
          -- a car from a peg.
          -- F5: TEST THE SLAB'S OWN PLANE, not a horizontal floor. The old
          -- test was `lz > chute_z_lo`, a single height 0.09 m BELOW the top
          -- peg row's apex, so cars cradled on row 0 were handed the chute's
          -- lift-free rule and could never be unseated. The chute is a
          -- SLOPE; only its own plane can say whether a car is on it.
          local chuteZ = B.apron_z_hi - (B.apron_x_hi - lx) * B.apron_tan
          b.spellChute = lx > B.chute_x_lo and lx <= B.apron_x_hi
            and lz > chuteZ - 1.0
          -- F1: the ridge band is its own regime - see seat_dir_z.
          b.spellSeat = (not b.spellChute)
            and lz > B.ridge_band_lo and lz < B.ridge_band_hi
            and math.abs(lx) <= B.field_hw
        end
        if b.spellChute then
          -- ON THE CHUTE: PURE INBOARD, NO LIFT. The 40 deg slab already has
          -- all the downhill any car needs; all that is missing is a shove.
          -- A rap with an UP component here is a juggling machine - the throat
          -- is only HOOD_CLEAR tall, so a 1.25 m hop just bounces the car
          -- between the slab and the hood (live build 22: 45 raps held a car
          -- at z 44.5 over a chute surface at 42.9 for the whole timeout).
          addSubjectVelocity(state, vehicle, toWorldDir(state, vec3(-1, 0, 0)) * dv)
        elseif b.spellSeat then
          -- F1: IN THE BIN BAND, SEAT IT - DO NOT LIFT IT. Every mouth on
          -- this machine is narrower than a car chord by design, so a car
          -- across a mouth is a car that has nearly scored. Lifting it is
          -- the one thing that cannot help. Aim mostly DOWN, with enough
          -- lateral to walk it toward the centre of the mouth it straddles.
          -- Scaled unit axes (THE UNIT-AXIS LAW).
          local target = nearestBinCenter(lx)
          local side = (target > lx) and 1 or -1
          addSubjectVelocity(state, vehicle,
            toWorldDir(state, vec3(1, 0, 0)) * (B.seat_dir_x * side * dv)
            + toWorldDir(state, vec3(0, 0, 1)) * (B.seat_dir_z * dv))
        else
          -- IN THE PEG FIELD: LATERAL-DOMINANT, and let the peg do the
          -- lifting. A peg is a kite - a tall diamond - so its flanks are
          -- 54.6 degree ramps. Shoving a wedged car hard along x
          -- makes the peg it is leaning on convert that into lift far more
          -- effectively than aiming the impulse up does, and it is the only
          -- axis that can get a car out from between two of them:
          -- applyClusterVelocityScaleAdd is a pure translation with no torque,
          -- so a car whose 4.5 m length has ended up lying ACROSS the board
          -- can never be re-oriented at all - it can only be walked out
          -- sideways. (Since the 2026-08-14 lattice the 5.40 m throat clears
          -- the car's 5.148 m chord in every attitude, so this is a backstop
          -- rather than the mechanism it once was.) The old 45 degree diagonal spent half its
          -- budget on lift: live 2026-08-14 it hopped a car a full metre in z
          -- on every rap and still moved it under 0.5 m in x in 25 s.
          -- Scaled unit axes (THE UNIT-AXIS LAW), not a composite local
          -- vector. It is only safe today because rap_dir_x/rap_dir_z happen
          -- to form a unit pair; built this way the ratio survives any
          -- retune toward "more lateral" instead of being silently
          -- renormalised.
          addSubjectVelocity(state, vehicle,
            toWorldDir(state, vec3(1, 0, 0)) * (B.rap_dir_x * (b.spellSide or -1) * dv)
            + toWorldDir(state, vec3(0, 0, 1)) * (B.rap_dir_z * dv))
        end
        if b.rapCount == 1 then showMessage("TILT! Shaking it loose...", 1.6) end
      end
    end
  else
    b.markZ = nil
    b.stuckTimer = 0
    b.rapTimer = 0
    b.spellRaps = 0
    b.spellSide = nil
    b.spellChute = nil
    b.spellSeat = nil
  end
end

local function updateReturning(state, dtSim)
  local b = state.behavior
  b.liftRate = 0
  -- Level the deck BEFORE lowering it, and do not bake on the way. The first
  -- cut baked the instant the tip hit zero, which left a 4.8 x 6.6 m invisible
  -- collision plate hanging at z ~39.7 for the 7.5 s the deck took to come
  -- down. The rule that replaces it: the deck's stale bake may only ever sit
  -- at a pose the deck actually STOPPED at - home flat, or docked at whatever
  -- angle the release ended on - and both of those are inside volumes no car
  -- can reach.
  if b.tip > 0 then
    b.tip = math.max(0, b.tip - B.tip_return_deg_per_second * dtSim)
    return
  end

  -- A car that is still aboard CANNOT be carried down, and it is worth being
  -- explicit about why, because the obvious fix does not work. The hoist
  -- carries a car UP by holding it with a velocity servo while the deck's
  -- stale collision plate sits harmlessly below it. Downward is not the mirror
  -- image: the stale plate is then ABOVE the descending target, the car is
  -- resting ON it, and no amount of downward velocity moves a car through a
  -- solid surface. Re-baking on a cadence does not fix it either - between
  -- bakes the plate is still a fixed floor the car cannot pass, so the cadence
  -- would have to be a bake every few centimetres of travel.
  --
  -- So the carriage does what a real hoist interlock does: it refuses to leave
  -- the crown while anything is standing on it. One bake puts a real, flat,
  -- correctly-drawn deck under the car, the chute is right there to drive off
  -- into, and crown_zone means a player who resets instead is delivered to
  -- onSubjectGone. The wait is BOUNDED - a wreck must never pin the machine -
  -- so after return_hold_seconds the carriage goes home regardless.
  --
  -- "Still up there?" is asked TWO ways, because the two reads fail in
  -- opposite directions and the interlock needs both. The geometric one is
  -- exact but relative to the DRAWN deck, so it goes false the instant the
  -- carriage starts moving - even though the car is still standing at the top
  -- on the deck's stale collision plate, which is the whole case this guards.
  -- crown_zone is the engine's own answer to "is there a vehicle at the top of
  -- this machine" and does not care where the deck is drawn. (crown_zone also
  -- earns its keep without being named: the framework only delivers
  -- onSubjectGone for a vehicle it can find in SOME zone, and before this zone
  -- existed a car on the tipped deck was in none of them, so a player who
  -- reset up here left the tower waiting out its whole release timeout.)
  local vehicle, lx, ly, lz
  if b.subjectId then vehicle, lx, ly, lz = sampleSubject(state, dtSim) end
  local onDrawnDeck = vehicle ~= nil
    and not sampleIsLost(lx, ly, lz)
    and onDeck(state, lx, ly, lz)
  -- crown_zone spans the chute as well as the deck, so the zone answer alone
  -- would hold the carriage for a car it had ALREADY released down the
  -- chute. The sample's own x narrows it: over the deck's span means aboard,
  -- inboard of the hinge means released cargo. A nil sample stays
  -- conservative (hold) - the zone is then the only witness there is.
  local atCrown = b.subjectId ~= nil
    and zoneOccupants(state, "crown_zone")[b.subjectId] ~= nil
    and (lx == nil or lx >= B.deck_center_x - B.deck_half_x - 0.2)
  local aboard = onDrawnDeck or atCrown
  -- THE MACHINE MUST HONOUR THE DROP IT JUST INVITED. The hold below tells
  -- the player "drive off down the chute", and taking that invitation is the
  -- best drop in the whole prop - from the crown, under power, off the same
  -- lip a release uses. It used to pay NOTHING: the field_zone adopt path in
  -- onEnter is gated on phase == "idle" but the phase here is "returning",
  -- and adoption keys off the zone CROSSING, which this car spent on its way
  -- up. So the car plinked the whole board and the tower just re-armed
  -- around it. When the same geometric test the interlock uses goes false -
  -- the subject is inboard of the hinge while still in crown_zone, i.e. it is
  -- released cargo rather than a passenger - hand it straight to the fall.
  -- ...but at most once, and never after this play has already been paid.
  -- Without the latch a fall that TIMES OUT with the car resting on the chute
  -- (in crown_zone, inboard of the hinge - exactly the build 20 stall) scores
  -- HUNG, drops into returning, matches this test, and is handed straight
  -- back to falling: a permanent 75-second scoring loop.
  if b.subjectId and b.lift > 0 and not aboard and lx ~= nil
    and not b.paid and not b.droveOff
    and zoneOccupants(state, "crown_zone")[b.subjectId] ~= nil
    and lx < B.deck_center_x - B.deck_half_x - 0.2
    and not sampleIsLost(lx, ly, lz) then
    showMessage("Nice - playing that one as it lies!", 2.4)
    emitEvent(state, "I", "pachinko_drove_off", {x = lx, z = lz})
    b.droveOff = true
    b.rapCount = b.rapCount or 0
    b.markerMode = "search"
    b.markerTarget = nil
    setPhase(state, "falling")
    return
  end
  -- F2: THE INTERLOCK ONLY MEANS ANYTHING AT THE CROWN. `onDeck` carries no
  -- altitude term of its own - it measures against the deck's CURRENT height,
  -- which sweeps all the way from 44.0 to 0.9 during this phase - so `aboard`
  -- went true for any car standing anywhere under the descending carriage.
  -- Two ways a player met it with no error at all: score, drive out of the
  -- bins and park back in the loading bay (~20-25 m against a 9.4 s return,
  -- so they arrive first), or simply come to rest in bin 4 against the right
  -- wall, which is inside the same x window. Either way the carriage froze
  -- 3.2 m above them for 12 s, printed "drive off down the chute" while they
  -- stood at ground level with the chute 43 m up, baked collision mid-stroke,
  -- and then fired the release kicker at MAXIMUM into a parked car.
  --
  -- Gate it at the crown, reusing the flourish's own guard, and require the
  -- play to be unpaid: a paid car is a passenger no longer.
  if aboard and b.lift > B.lift_travel - 0.5 and not b.paid and not b.holdGaveUp then
    -- The gate is deliberately NOT closing while the hold runs: the one
    -- exit this bake offers is down the chute, through the throat the gate
    -- blocks. The first cut sealed the gate at the top of the phase and
    -- walled the passenger in 43 m up.
    if not b.holdBaked then
      b.holdBaked = true
      requestCollisionReload(state)
      -- SAY WHAT WILL ACTUALLY HAPPEN. "Drive off down the chute" invites the
      -- player to creep over the convex hinge lip, which is the exact
      -- belly-grounding failure THE KICKER exists to defeat.
      showMessage("Carriage holding - 12 s, then we launch you onto the board.", 3.0)
      emitEvent(state, "I", "return_blocked",
        {x = lx, z = lz, on_deck = onDrawnDeck, in_crown_zone = atCrown})
    end
    b.holdTimer = b.holdTimer + dtSim
    if b.holdTimer < B.return_hold_seconds then return end
    b.holdGaveUp = true
    -- ONE LAST SHOVE AT THE OPEN GATE BEFORE THE FLOOR LEAVES.
    --
    -- Giving up used to mean the carriage simply descended out from under a
    -- car parked 43 m up: a designed car-deletion, and the player's reward
    -- for not finding the exit was a 43 m fall with no board under it. The
    -- gate has not started closing yet at this instant (it is sealed further
    -- down, only once nothing is held), so the throat the hold invited the
    -- player through is still open for one more moment. Fire the kicker at
    -- maximum toward it - same inboard axis and lift as the release kicker,
    -- built as scaled unit axes per THE UNIT-AXIS LAW - so the car is thrown
    -- ONTO the board and plays out as a real drop instead of being dropped
    -- down the back of the machine.
    --
    -- This path is not theoretical: return_blocked -> return_forced fired
    -- unprompted in two separate 15-play runs, so it is reachable in the rig
    -- and a player will meet it.
    -- MAXIMUM, i.e. the top of the kicker's own escalation ladder, and only
    -- when there is actually a sampled vehicle to push (in this phase
    -- `vehicle` is nil unless a subject is still being tracked).
    if vehicle then
      local scale = B.lip_kick_scale_max
      addSubjectVelocity(state, vehicle,
        toWorldDir(state, vec3(1, 0, 0)) * (-B.lip_kick_x_mps * scale)
        + toWorldDir(state, vec3(0, 0, 1)) * (B.lip_kick_z_mps * scale))
    end
    showMessage("Clearing the carriage - hold on!", 2.4)
    emitEvent(state, "I", "return_forced", {seconds = b.holdTimer, x = lx, z = lz})
  end
  -- Seal the gate only once nothing is held at the crown (or the hold gave
  -- up): it swings shut while the carriage descends, and the single endpoint
  -- bake at the bottom closes both it and the deck.
  if b.gate ~= 0 then
    local step = math.abs(B.gate_open_deg) * dtSim / B.gate_seconds
    if math.abs(b.gate) <= step then b.gate = 0 else
      b.gate = b.gate + (b.gate < 0 and step or -step)
    end
  end
  if b.lift > 0 then
    b.lift = math.max(0, b.lift - B.return_speed_mps * dtSim)
    b.liftRate = -B.return_speed_mps
    return
  end
  if b.gate == 0 then
    -- ONE endpoint bake closes the whole return: the deck plate is a drivable
    -- floor again and the gate leaf is shut across the chute throat.
    requestCollisionReload(state)
    clearEffects(state)
    dropSubject(state)
    b.parkTimer = 0
    b.lastCount = nil
    b.idleGrace = B.rearm_grace_seconds
    b.markerTarget = nil
    emitEvent(state, "I", "pachinko_rearmed", {plays = b.stats.plays})
    showMessage("Tower reloaded. Drive in to play.", 2.2)
    setPhase(state, "idle")
  end
end

-- The payout marker: a real carriage on a real rail, slewed at a real speed.
-- Idle sweeps the fascia (attract mode); a live play HUNTS; only a scored
-- play points at a bin and holds there.
--
-- A VALUE POSITION MUST BE EARNED, NEVER DEFAULTED TO. The first cut fell
-- through to `b.markerTarget or 0` whenever markerMode was unset - and
-- bin_centers[3] is 0.0, which is the JACKPOT tick. Three paths reach here
-- with markerMode nil in a NON-idle phase, because dropSubject clears the
-- mode while setPhase("returning") keeps the machine live: onSubjectGone
-- (a vehicle swap or delete), the hoist's off-deck abort, and falling's
-- sampleIsLost - which is exactly what a player gets for pressing R
-- mid-fall. Each one drove the pointer to 10000 and held it there for the
-- whole return, on a play that scored nothing. So the value branch now
-- demands BOTH an explicit "value" mode and a real target, and everything
-- else hunts: an unset marker can no longer claim a jackpot.
local function updateMarker(state, dtSim)
  local b = state.behavior
  local target
  if b.phase == "idle" then
    target = B.marker_travel * math.sin(b.clock * B.marker_sweep_rate)
  elseif b.markerMode == "value" and b.markerTarget then
    target = b.markerTarget
  else
    -- Play in progress, a play that scored nothing, or a lost subject:
    -- HUNT, do not point.
    target = B.marker_travel * math.sin(b.clock * B.marker_search_rate)
  end
  local delta = target - (b.marker or 0)
  local step = B.marker_speed_mps * dtSim
  if delta > step then delta = step end
  if delta < -step then delta = -step end
  b.marker = (b.marker or 0) + delta
end

-- TWO CLOCKS (round 9). proplib now forwards dtReal alongside dtSim
-- (lua_kit.py onPreRender already received it and simply never passed it on).
-- Every line of this machine's tuned behaviour keeps dtSim, unchanged and
-- untouched; only the SHOW reads dtReal, because a musical timeline on a clock
-- the player can scale desynchronises from the audio without bound.
behavior.update = function(state, dtSim, dtReal)
  local b = state.behavior
  b.clock = b.clock + dtSim
  b.elapsed = b.elapsed + dtSim

  local timeoutKey = PHASE_TIMEOUT[b.phase]
  if timeoutKey and b.elapsed > B[timeoutKey] then
    -- The last sampled pose rides on EVERY timeout, x as well as z. The three
    -- failure modes a hang can be (soft-body cradling ON a crown, a throat
    -- wedge at a gap MIDPOINT, or a chute/divider hang outboard of the field)
    -- are distinguished by x alone, and two consecutive geometry rounds each
    -- cost a full test cycle because only z was on the record.
    emitEvent(state, "I", "phase_timeout", {
      phase = b.phase,
      seconds = b.elapsed,
      rest_x = b.lx,
      rest_y = b.ly,
      rest_z = b.lz,
    })
    if b.phase == "falling" and b.lz then
      -- Wedged in the pegs and the knocker has not shaken it out. Score the
      -- position the car is actually in - payout reports "HUNG ON THE BOARD"
      -- for anything still above the bin mouths, so this cannot invent a bin.
      showMessage("Timed out on the board - reading the position.", 2.6)
      payout(state, b.lx, b.ly, b.lz)
    else
      -- The subject is deliberately NOT dropped here: returning carries a car
      -- that is still on the deck back down, and it drops the subject itself
      -- once the machine is home.
      showMessage("Tower timed out - resetting.", 2.4)
      setPhase(state, "returning")
    end
  end

  if b.phase == "idle" then
    updateIdle(state, dtSim)
  elseif b.phase == "loading" then
    updateLoading(state, dtSim)
  elseif b.phase == "hoist" then
    updateHoist(state, dtSim)
  elseif b.phase == "dock" then
    updateDock(state, dtSim)
  elseif b.phase == "arming" then
    updateArming(state, dtSim)
  elseif b.phase == "tipping" then
    updateTipping(state, dtSim)
  elseif b.phase == "falling" then
    updateFalling(state, dtSim)
  elseif b.phase == "payout" then
    if b.elapsed >= B.score_hold_seconds then
      clearEffects(state)
      setPhase(state, "returning")
    end
  elseif b.phase == "returning" then
    updateReturning(state, dtSim)
  end

  updateMarker(state, dtSim)
  applyMachinePose(state)
  -- Additive and strictly last: the light rig is an OBSERVER of everything
  -- above it. It reads b.phase / b.lift / b.lx / b.lz / b.kicks /
  -- b.lastValue / b.conceded and writes nothing back, so no decision this
  -- machine makes can depend on it.
  Lights.update(state, dtSim)
  -- Strictly after the light rig, because the show reads
  -- Lights.flash: the impact strobe is computed from b.kicks and
  -- the bin-mouth crossing on dtSim, and the spots and surfaces
  -- share it so a physics event lands on all three mechanisms in
  -- the same frame. The show's own clock is dtReal; the flash it
  -- borrows is not, and that is deliberate.
  Show.update(state, dtSim, dtReal)
  -- ...and the soundtrack immediately after it, for the same reason and on
  -- the same terms. It reads the same frame's state - including the two
  -- triggers Lights has just strobed on - and writes nothing back, so the
  -- kicker thump, the bin-contact hit and the jackpot fanfare are committed
  -- on the frame their light is.
  Audio.update(state, dtSim)
end
"""

# Splice the generated fixture table into the behaviour chunk. See the light
# rig block above for why the constants live in Python rather than in BEHAVIOR.
LUA_BEHAVIOR = _LUA_BEHAVIOR_SOURCE.replace("--@LIGHT_SPECS@--", _light_specs_lua())
assert "--@LIGHT_SPECS@--" not in LUA_BEHAVIOR, "light spec splice failed"
LUA_BEHAVIOR = LUA_BEHAVIOR.replace("--@SPOT_SPECS@--", _spot_specs_lua())
assert "--@SPOT_SPECS@--" not in LUA_BEHAVIOR, "spot spec splice failed"
assert LUA_BEHAVIOR.count('slot = "strobe_') == 3
assert LUA_BEHAVIOR.count('slot = "pegspot_') == PEG_ROWS
LUA_BEHAVIOR = LUA_BEHAVIOR.replace(
    "--@EMISSIVE_SPECS@--", _emissive_specs_lua())
assert "--@EMISSIVE_SPECS@--" not in LUA_BEHAVIOR, "emissive spec splice failed"
assert LUA_BEHAVIOR.count("mat = \"") == len(EMISSIVE_SPECS)
LUA_BEHAVIOR = LUA_BEHAVIOR.replace(
    "--@SHOW_CONSTANTS@--", _show_constants_lua())
assert "--@SHOW_CONSTANTS@--" not in LUA_BEHAVIOR, "show constant splice failed"
LUA_BEHAVIOR = LUA_BEHAVIOR.replace("--@SHOW_MODES@--", _show_modes_lua())
assert "--@SHOW_MODES@--" not in LUA_BEHAVIOR, "show mode splice failed"
# STRUCTURAL, and counted INSIDE THE SPOT TABLE. The old form counted
# `"row = "` over the whole 8000-line runtime against a >= threshold, and
# the hand-written Lua contributes two unrelated hits of its own - so with
# 19 spot specs the count was 21 against a floor of 19 and TWO ENTRIES
# COULD HAVE LOST THEIR DISCRIMINATOR AND STILL PASSED. Worse, the letter
# check was `count("letter = 0,") == 1`, which proves only that
# letterspot_0 carries the key and says nothing about the other eighteen -
# and a missing `letter` throws at runtime inside a path that is not
# pcall-wrapped. Both are now exact counts over the spliced table alone.
_spot_table = LUA_BEHAVIOR[LUA_BEHAVIOR.index("local SPOT_SPECS = {"):]
_spot_table = _spot_table[:_spot_table.index("\n}")]
assert _spot_table.count('{slot = "') == len(SPOT_SPECS), (
    f"the spot table holds {_spot_table.count(chr(123) + chr(115))} rows, "
    f"not {len(SPOT_SPECS)}"
)
for _discriminator in ("row = ", "letter = ", "rowz = ", "chase = "):
    assert _spot_table.count(_discriminator) == len(SPOT_SPECS), (
        f"{_discriminator!r} appears {_spot_table.count(_discriminator)} "
        f"times in the spot table, not once per each of the "
        f"{len(SPOT_SPECS)} fixtures - the runtime branches on all four "
        f"and a missing one is a fixture on the wrong waveform"
    )
# And every letter index is present exactly once, not just index 0.
for _k in range(8):
    assert _spot_table.count(f"letter = {_k},") == 1, (
        f"letterspot_{_k} did not splice its letter index"
    )
assert _spot_table.count("letter = -1,") == len(SPOT_SPECS) - 8
# The old assert is kept, weakened form and all, purely as a tripwire on
# the splice itself; the four above are what actually guarantee the shape.
assert LUA_BEHAVIOR.count("row = ") >= len(SPOT_SPECS), (
    "the spotlight table lost its branch discriminator again"
)
assert "spec.chase" not in LUA_BEHAVIOR.split("Emissive.update")[1].split(
    "Show.begin")[0], "a driven surface is still reading a chase phase"
# Every photometric number the runtime uses must have arrived by SPLICE. If a
# nits value or a candela conversion can be found in the hand-written Lua
# source, someone retyped a derived quantity.
assert "emissiveIntensityNits\", 0, \"1800" not in LUA_BEHAVIOR
assert LUA_BEHAVIOR.count('slot = "lamp_') == len(LIGHT_SPECS)
# Same pattern for the audio constants, and for the same reason: the tuned
# BEHAVIOR table is 88 keys and stays 88 keys.
LUA_BEHAVIOR = LUA_BEHAVIOR.replace("--@AUDIO_GE@--", _audio_ge_lua())
assert "--@AUDIO_GE@--" not in LUA_BEHAVIOR, "audio spec splice failed"
assert "local AUDIO_HOLD = {" in LUA_BEHAVIOR
# ... and for the horn cluster, whose mouth coordinates are shared with the
# Blender generator exactly the way the lamp tubes' are.
LUA_BEHAVIOR = LUA_BEHAVIOR.replace("--@PEG_ROWS@--", _peg_rows_lua()).replace(
    "--@PEG_SCALES@--",
    f"local PEG_SCALE_FULL = {PEG_RETRACT_SCALE}\n"
    f"local PEG_SCALE_NEAR = {PEG_RETRACT_SCALE_NEAR}",
)
assert "--@PEG_SCALES@--" not in LUA_BEHAVIOR, "peg scale splice failed"
assert "--@PEG_ROWS@--" not in LUA_BEHAVIOR, "peg lattice splice failed"
assert LUA_BEHAVIOR.count("local PEG_ROWS = {") == 1
assert LUA_BEHAVIOR.count("  {row = ") == len(PEG_ROW_Z)
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
assert "--@HORN_" not in LUA_BEHAVIOR, "horn splice failed"
assert "@HORN_" not in LUA_BEHAVIOR and "@MOD_ID@" not in LUA_BEHAVIOR
assert LUA_BEHAVIOR.count('slot = "horn_') == len(HORN_MOUTHS) == 4
assert LUA_BEHAVIOR.count("local HORN_CUE_LIST") == 1
for _cue in HORN_CUES:
    assert f'name = "{_cue}"' in LUA_BEHAVIOR, _cue
