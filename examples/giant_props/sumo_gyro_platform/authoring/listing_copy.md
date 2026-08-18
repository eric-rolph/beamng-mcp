# beamng.com resource listing copy — The Free-Pivot Sumo Gyro-Platform

## Subtitle (pick one)

1. A 26.2 m, 212-tonne steel dish balanced on one spherical bearing — drive
   two cars aboard and fight over which way "down" points.
2. The floor leans at whoever stands on it — one midsize heels it 4.36
   degrees; park 30 tonnes aboard and the deck believes every kilogram.
3. Giant free-pivot sumo ring — real rigid-body tilt, four hydraulic rams,
   zero scripted shoves. The floor is the weapon.

## Description

**THE FREE-PIVOT SUMO GYRO-PLATFORM** — a 26.2 m steel dish carried on a
single spherical bearing, centred by four gas-charged hydraulic rams, and
aware of every kilogram you park on it.

Drive up the 7 m-wide boarding ramp while the deck is locked level and the
junction is flush. The first car aboard opens a six-second boarding window —
the ramp takes two cars abreast, and the ring never arms without giving a
second car time to join. Then the wait: GIMBAL FREE IN 5... 4... 3... — and
if anyone is still straddling the ramp, the count holds for them (25 seconds,
no longer). The bypass valves blow off, the bearing goes free, and 212 tonnes
of deck starts leaning toward whoever is standing on it.

That lean is the entire game. The tilt is the steady state of a real
rigid-body model forced by every occupant's weight moment about the bearing:
a 1600 kg car parked 10 m out heels the deck 3.5 degrees, and the same car at
the lip foot pulls 4.36. No midsize ever reaches the 5.5-degree mechanical
stops alone — that car would need 15.7 m of leverage on a 12.45 m dish.
Slamming it into the stops takes two cars ganging up on one side, or
genuinely heavy iron: about two tonnes parked out at the lip is where the
deck runs out of patience. And at the stops the rim is a 9.6% grade that
rolls a car with its brakes off. The lip is a 0.30 m rolled kerb: enough to
stop a drift, not enough to stop a shove. About 14 km/h (9 mph) of contact
puts your opponent over it and onto the catch berm, which rolls them back to
the wall foot instead of letting them tour the map. Whoever is further out
wins the argument about which way "down" points.

Stand still and the house calls it: a car that has not moved 0.45 m in 20
seconds is NO CONTEST — dropped from the tally, and the deck stops leaning
toward it. When the ring clears (or the 3-minute round clock runs out, or a
challenger has been queuing on the ramp for 12 seconds), the rams re-level
the deck with zero overshoot — about 10 seconds from the stops — while the
concave dish gathers the survivors gently back toward the centre. The deck
locks level, the junction reads flush. Drive on.

### The bearing

- No scripted forces, ever. This prop never calls a launcher, never injects
  velocity, never teleports. Your car moves because the floor under it moved.
- Every vehicle is weighed at its true spawned mass — anything from 300 kg
  to 30 tonnes counts — so a loaded truck leans the ring exactly as hard as
  it should.
- Top-heavy on purpose: the deck's mass centre rides 0.66 m above the
  bearing, so gravity is actively trying to tip the machine and the four
  rams on their 5.2 m circle have to outvote it. That is why it feels alive.
- A 13.2-second free period at damping ratio 0.75: the deck settles without
  wobbling, but still breathes when a car crosses the centre.

### The scoreboard

A mast beside the ramp carries a painted mechanical semaphore — green OPEN,
amber ARM, red LIVE, blue RESET — and a tally column that climbs one notch
for every car in the fight, up to four. The STATE readout is a moving machine
part, and it turns: no icon, no fake indicator, nothing that could show you a
state the machine is not actually in.

The board does carry two lit panels, in the cabinet windows, and they carry
one thing only — the competitors' names. Drive aboard and your vehicle's
name goes up, on both faces of the board, so the crowd on either side reads
the same fight. When the panels are dark, nobody is aboard.

### Details

- Fully automatic round lifecycle: 6 s boarding window, counted 5 s arming,
  rounds capped at 3 minutes, ~10 s no-overshoot re-level, straight back to
  green. No buttons — the machine referees itself.
- The boarding threshold is engineered, not faked: the deck edge sweeps
  ±1.26 m through full tilt, so the rim carries a 1.40 m deep ring girder
  whose flange always stands below the ramp lip. The doorway is a wall,
  never a hole.
- Countdown interlock: the count holds while anyone is on the ramp junction
  (bounded at 25 s, so a parked wreck cannot pin the machine), and a
  challenger queuing mid-round gets the round called for them after 12 s.
- No-contest purge: motionless for 20 seconds — or wrecked for 5 — and you
  stop counting and stop steering the tilt. Move again and you are back in
  the fight.
- Four real hydraulic rams: 2.37 m struts whose chrome rods genuinely
  stroke, plus a bypass blow-off puff whenever the bearing unlocks or
  re-locks.
- The rams' flow limit caps the deck edge at 0.156 m/s — the floor leans,
  it never yanks.
- 24.9 m of usable floor, sized about 1.5 turning circles across: room to
  circle an opponent, no room to run away forever. The dished centre is a
  genuine refuge.
- Guard kerb and drain moat keep anything from ending up under the deck —
  and if something ever does, the machine locks level as a safety stop.

### How to use

Spawn it from the vehicle selector like any prop, then drive a second
vehicle in — sumo needs an opponent, though even one car gets a proper lean
out of it. The installation (ring, catch apron, boarding ramp) spans about
51 m end to end, so give it flat open ground; Gridmap and the airfields work
well. Rounds run themselves: drive aboard, wait out the count, push.

Built with the shared giant-props framework. Feedback and bug reports welcome.

Drive on. "Down" is negotiable.
