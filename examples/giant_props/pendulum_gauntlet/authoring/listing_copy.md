# beamng.com resource listing copy — Wrecking Ball Pendulum Gauntlet

## Subtitle (pick one)

1. Four free-swinging 2.2 m physics wrecking balls sweep a 40 m inflatable
   bridge — time the gaps or get batted off it.
2. Drive in, bounce across, and dodge four gravity-driven wrecking balls that
   bottom out below deck level — clear the far gate inside 90 seconds.
3. Giant pendulum-dodge prop — four free-swinging wrecking balls, a genuinely
   squishy inflated deck, and a machine that re-cocks itself.

## Description

**WRECKING BALL PENDULUM GAUNTLET** — a 40 m elevated bridge of inflated mats
where four steel wrecking balls have the right of way.

The balls are moving before you are. Each one spawns cocked 40 degrees up its
arc, and gravity does the rest — no motors, no animation loop. Drive up the
asphalt ramp and through the gate ("DODGE THE WRECKING BALLS!") and the run is
on: four gantries, 10 m apart, each swinging a 2.2 m forged ball on a 6.4 m
cable chain, neighbours cocked on opposite sides so the lane closes from both
directions. Underneath, the deck is inflated pillows — it squishes and bounces
under your suspension while you're trying to time a wrecking ball. Make the
opposite gate inside 90 seconds and the machine calls it: "GAUNTLET CLEARED!
Nice dodging."

Then the anticipation part. Air drag calms the swings over minutes — and the
gauntlet notices. When the widest swing over an 8-second window drops below
1.2 m, it re-arms itself to full amplitude: instantly if the place is empty,
or after a polite "Re-cocking the wrecking balls in 3..." if you're standing
on the bridge. The pause is the warning. The warning is the joke.

### The pendulums

Not animated — simulated. Each ball is a heavy cluster of real physics nodes
on a cable chain, with its own collision surface, and the ball you see is
matched every frame to the live physics ball — what you see is exactly where
the hit is. And do the arithmetic: anchor at 10.4 m, chain 6.4 m, ball radius
1.1 m — the ball's belly bottoms out at 2.9 m over a deck that sits at 3.0 m.
At the bottom of the arc it is below deck level. You do not drive under it.
You go when it's gone: at full swing the ball hangs 4.1 m off the centreline,
entirely outside the lane.

### The bridge

Forty metres of inflated vinyl pillows in alternating red and blue — twenty
2 m bays — with yellow bumper bolsters down both edges, all of it sprung,
collidable, and genuinely soft, riding a 3 m-high steel truss with asphalt
ramps at both ends. The floor is part of the gauntlet: it wobbles while you
aim.

### Details

- Four steel gantries at 10 m spacing hang 2.2 m wrecking balls on 6.4 m
  cable chains, cocked alternately 40 degrees left and right so adjacent
  balls attack from opposite sides.
- Real pendulum physics: gravity swings the balls from the moment the prop
  spawns, air drag decays the swing over minutes, and every ball hits
  vehicles through its own collision surfaces.
- Timed runs between the gates: enter either end, exit the opposite end
  inside 90 seconds to clear the gauntlet.
- Self-re-arming: when the widest swing over an 8-second window settles
  below 1.2 m, the machine re-cocks to full amplitude — after a 3-second
  warning if anyone is on or near the bridge, instantly otherwise.
- Re-cocking is safe by geometry: the reset poses hang the balls 4.1 m off
  the centreline — clear outboard of the lane — and about 5.5 m up, so a
  re-arm can never drop a ball onto a car mid-bridge.
- Resetting the prop yourself re-cocks it on demand: "Pendulums re-cocked.
  DODGE!"
- The deck pillows and bumper bolsters are sprung free physics nodes — the
  inflated mats genuinely squish and rebound under your wheels.
- Hazard-chevron trim, worn steel, forged-ball finish, stitched inflatable
  vinyl — the palette says playground, the physics say demolition site.

### How to use

Spawn it from the vehicle selector like any prop, then drive a second vehicle
in through either gate — both ends arm a timed run. It is long: 56 m end to
end with the ramps, and the balls sweep more than 5 m either side of the
centreline, so give it a flat open strip. Gridmap and the airfields work
well. No buttons, no console — the gates are the start and finish lines, and
the machine runs itself.

Built with the shared giant-props framework. Feedback and bug reports welcome.

Go when it's gone.
