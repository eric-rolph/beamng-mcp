# beamng.com resource listing copy — The Vacuum Cleaner of Doom

## Subtitle (pick one)

1. A giant shop vac that drags your car down a 21 m suction lane, swallows it
   whole, and spits it out the exhaust stack at 162 km/h.
2. Drive into the dust cloud, fight a pull field that out-pulls gravity, lose,
   and leave through the chimney at 100 mph. SLURP.
3. Giant working vacuum prop — ramping suction that tops 1.2 g, a 0.8-second
   digestion, and a ballistic far-side ejection with a steam blast.

## Description

**THE VACUUM CLEANER OF DOOM** — an oversized shop vac that has decided your
car is debris.

Roll into the approach lane and the machine notices. The vaned turbine cap
starts to turn, dust storms around the nozzle bell, and for 1.2 seconds that
is all that happens — "The vacuum awakens..." Then MAXIMUM SUCTION: an
invisible pull field drags every vehicle in the lane toward the mouth,
ramping from 4 to 12 m/s² over three seconds. That top figure is more
acceleration than gravity gives you straight down — once the ramp tops out,
street tyres do not get a vote. The field caps your approach at 14 m/s
(about 50 km/h), so you arrive at the bell throat fast but in one piece.
Then: SLURP. You are swallowed. The canister digests you for 0.8 seconds,
and PTOOEY — you exit the angled exhaust stack on the far side at 45 m/s
(162 km/h, about 100 mph), 25 degrees above the horizon, riding a steam
blast as the flap claps open behind you.

### The pull field

The suction is honest physics, not a cutscene: a per-frame acceleration
toward the nozzle, applied to everything inside the 10 m wide, 21 m long
lane. Your speed toward the mouth is measured from real position deltas
every frame and capped at 14 m/s, so nothing integrates to silly velocities
and nothing pancakes against the back of the throat. Early in the ramp
(0.4 g) you can still power back out of the lane. Late in the ramp you
cannot. Choose quickly.

### The exhaust stack

One car goes down the hatch at a time, but the machine handles a queue: the
moment one digestion ends, the next customer pressed against the mouth goes
straight down — a traffic jam disappears one 0.8-second gulp at a time.
Every ejection fires you from 5.8 m up, the flap kicking 70 degrees open
with a blast of steam and easing shut again inside a second.

### Details

- Full sequence with on-screen commentary: "The vacuum awakens..." →
  "MAXIMUM SUCTION" → "SLURP!" → "PTOOEY!"
- Pull field ramps 4 → 12 m/s² over 3 s; approach speed capped at 14 m/s so
  arrivals are dramatic, not fatal.
- Ejection at 45 m/s — 162 km/h — 25 degrees above horizontal, launched from
  the exhaust stack on the far side.
- The turbine cap physically spins: dead still at idle, winding up to about
  172 RPM at full suction, spinning back down as the machine sleeps.
- Swallows queued vehicles back to back, one 0.8 s digestion at a time.
- 6.4 m safety-orange ribbed drum with latch band, dome lid, ribbed hose,
  caster deck, and a flattened-cone nozzle bell.
- Self re-arming: 1.5 s after the lane empties it winds down to idle, ready
  for the next customer. No reset required.
- Lists at $28,000 in the vehicle selector. A bargain, considering.

### How to use

Spawn it from the vehicle selector like any prop, then drive a second
vehicle straight at the nozzle. Give it room: the suction lane reaches 21 m
out front of the mouth, and ejected vehicles fly a long way past the far
side — flat, open ground in both directions. Gridmap and the airfields work
well. There are no controls; proximity does the rest.

Built with the shared giant-props framework. Feedback and bug reports
welcome.

You are the debris.
