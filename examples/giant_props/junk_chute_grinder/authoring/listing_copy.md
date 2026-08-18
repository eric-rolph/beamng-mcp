# beamng.com resource listing copy — Junk Chute Grinder Trap

## Subtitle (pick one)

1. A giant twin-shaft shredder that eats cars whole: 120 steel hooks drag
   you through a 2.9 m nip and drop the wreck on a working scrap conveyor.
2. Climb 53 m of haul ramp, nose over the lip, and get taken apart at an
   authentic 14.3 RPM — doors, bonnet, bumpers and tyres off.
3. Giant working scrapyard shredder — 35% feed chute, counter-rotating hook
   rotors, anti-jam auto-reverse, and a scrap-value receipt on the way out.

## Description

**JUNK CHUTE GRINDER** — a twin-shaft scrapyard shredder at giant scale
that treats your car as the feedstock.

The climb is the warning. The haul ramp runs 53 m at a steady 20% to a
crest 7.7 m above the yard, and the rolls at the top are not turning — the
machine just flashes "FEED CHUTE OPEN - drive it in" and waits. Line up on
the 8.6 m mouth and commit: the moment your whole car is in the chute —
"ROLLS TO SPEED" — the stack coughs smoke and the rotors hit working speed
in 1.6 seconds while the floor steepens to 35% under you. Nose over the lip
and the teeth take the car: dragged down through the nip at the rollers'
own surface speed, juddered at the 1.4 Hz tooth-pass rate, ground along one
rotor shroud and thrown onto the other, shedding doors, bonnet, bumpers and
tyre pressure on the way. Clear the drums and it is a 1.7 m free fall onto
the steel pan. The conveyor does the rest — out of the slot, up the
incline, onto the scrap pile, with your scrap value printed on screen as
the wreck settles.

### The rotors

Ten hooked cutter discs per shaft on a 1.00 m pitch, six hardened hooks per
disc — 120 hooks in the machine, staggered 30° so the discs interleave like
a real rotor. The shafts counter-rotate so both nip faces travel down,
sweeping a 2.30 m hook circle at 14.3 RPM. Real twin-shaft shredders run
8–20 RPM; this one sits square in the band, and its contact surface moves
at 1.5 m/s — walking pace. It does not need to be faster.

The grab is a velocity servo, not a teleport. Every frame the runtime
evaluates the exact surface-velocity field of both drums at your car's own
position and steers you toward it, with the pull recomputed from the
rollers' CURRENT speed — so when the drive bogs down under load (it loses
about a third of its RPM with a car in its teeth), the pull sags with it.
The roller speed you see and the pull you feel can never disagree. And the
hook tips ride 15% proud of the contact discs, so they sweep 15% faster
than the surface — which is exactly what a cutting tooth does, and is where
the scrub comes from.

### The anti-jam cycle

A real shredder reverses when it chokes, so this one does:

- Held by the teeth but not going down — less than 0.22 m of progress in
  2.5 seconds — counts as a jam: "JAM - AUTO REVERSE", 4 seconds of
  reverse, then it bites again.
- Three jams on the same wreck and the machine gives up honestly:
  "UNGRINDABLE - SPITTING IT OUT" — the purge throws it back up the chute
  at 54 km/h (about 34 mph), pitched 44° skyward.
- A purged wreck gets 4 seconds of grace before the teeth may take it
  again, and a 60-second throat timeout backstops the whole cycle.

### Details

- 2.90 m clear nip, hook tips closing it to 2.60 m: a 2.0 m compact passes
  with 0.45 m each side, and a 2.3 m wide-body pickup still clears by
  0.30 m per side.
- The 10 m feed slot swallows a 4.5 m car whole, with 2.75 m to spare at
  each end — drawn through in about three seconds.
- Honest damage: the teeth pop breakgroups (doors, bonnet, bumpers) and
  deflate every tyre as the body passes the axis line, and the deformation
  comes from real contact — three measured shroud-contact episodes on the
  way down, then a 6.5 m/s arrival on the pan.
- Working discharge: a 22 m steel slat conveyor runs at 3 m/s on a 4%
  incline, clears a wreck off its tail in 1.5 seconds, and marches its
  slats at exactly the speed its friction pulls at.
- Scrap-value receipt: "DISCHARGED - scrap value ..." reads out your damage
  bill as the wreck settles on the pan.
- The 20% ramp crests on a true parabolic vertical curve — constant rate of
  grade change, no breakover ridge, and the hump under the longest 3.60 m
  wheelbase is 54 mm, a third of a compact's belly clearance.
- The show: a hydraulic power-pack skid with stack smoke and a five-blade
  cooling fan, a spinning amber beacon, grind dust in the throat, and a
  10.3 m gantry sign with 0.77 m capitals you can read from the ramp toe,
  53 m away.
- The rolls only stop once the feed path is clear, nothing is held and the
  pan is empty — a wreck is never stranded on a dead belt.

### How to use

Spawn it from the vehicle selector like any prop, then drive a second
vehicle in. Climb the ramp, aim for the mouth, and commit — the machine
arms itself when the whole car is inside the chute, and a car that only
clips the mouth on the way past will not start the rolls. It is long
(about 94 m from ramp toe to scrap pile), so give it open, flat ground.
Gridmap and the airfields work well.

Built with the shared giant-props framework. Feedback and bug reports
welcome.

The sign says KEEP CLEAR OF ROLLS. The ramp disagrees.
