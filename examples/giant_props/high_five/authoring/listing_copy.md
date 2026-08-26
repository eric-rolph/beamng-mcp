# beamng.com resource listing — Charlie's High Five

Submission-ready copy. Numbers below are read from `spec.py` /
`runtime.lua`, not remembered — re-check them if the tunables move.

## Resource title

    Charlie's High Five

## Tag line (the one-liner under the title)

> An 8.6 m foam-latex hand on a slewing arm. It watches you come, works
> out when you will arrive, and swings early so the palm is already there.

Alternates, if a shorter one is wanted:

1. It does not react to you. It leads you.
2. Giant working slap machine — 108 m approach corridor, ten power
   settings, and a wrist that tilts the launch from flat to 42 degrees.
3. There is one lane it cannot reach. Finding it is the game.

## Category

Vehicles → Props (`"Type": "Prop"` in `info.json`; it spawns from the
vehicle selector like the barrels and the wrecking ball).

## Description

**CHARLIE'S HIGH FIVE** — an 8.6 m hand, cast in foam latex at 44.1 times
life size, bolted to a slewing steel arm beside the road. It parks folded
back at 72 degrees off the centreline, and it is looking down the road.

### It leads you

This is the part worth reading twice. Most props react: you hit a trigger,
they start moving, and if you were quick you have already gone. This one
does not react. A 9.6 m wide, 108 m long corridor runs up the road ahead of
it, and the moment you enter, the machine starts timing you. It measures
your closing speed, divides by the distance left, and works out when you
will arrive. Then it waits — twitching on its mount, 7 degrees of idle
tremble — until the moment when *starting the swing now* means the palm
gets to the strike point exactly when you do.

The swing takes 0.28 seconds — a real slap's strike is a tenth of a
second and change, and on video it is four frames of violence between a
slow draw and a held follow-through. So it fires 0.28 seconds before you
arrive.
That single equality is the whole machine, and it is asserted by a test
that fails if the two numbers ever drift apart.

The consequence: it hits at 15 km/h and it hits at 500 km/h. Verified in a
headless harness from 4 to 140 m/s, with sub-metre contact error below
60 m/s. You do not outrun it. You have to outsmart it.

### Or just drive onto the pad

There is a hand stencilled on the road in front of the machine. Drive onto
it — from any direction, at any speed, or roll to a stop on it — and the
arm comes round immediately. No wind-up, no warning: you are standing on
the contact point, so there is nothing to lead and nothing to wait for.

Two ways in, then. Come down the road and the machine reads you and times
itself to meet you. Wander onto the pad and it just swings.

### The sequence

Cross into the corridor and it wakes — 0.45 s of alert, then 0.85 s of
wind-up as the arm cocks back from 72 to 104 degrees. It will hold that
draw for up to 3.2 seconds waiting for you, and it drops you as a target if
you slow below 2.5 m/s of closing speed, because a machine that swings at
someone who parked is a machine that looks stupid.

Then the swing: 104 degrees through to 0, in 0.28 seconds, accelerating all
the way into the contact. Everything in the strike zone — 9.0 m across, 7.6 m deep, 3.9 m
tall — leaves at 28 to 34 m/s, rolled fresh per car, before the console
gets involved. Follow-through carries the arm on to +78 degrees, holds
0.4 s, and then takes 2.1 s to swing home. 1.2 s of cooldown, and it is
looking down the road again.

Two cars in the corridor at once and it takes the one arriving first. Both
in the strike zone and both go.

### The console

A mid-century cream-and-walnut cabinet stands at the mast, facing the road,
and both caps on it are clickable:

- **POWER, 1 to 10** — a ten-segment lit bar, linear from 1.0x to 2.6x. At
  the stock setting of 3 a car leaves at 137–166 km/h. At 1 it is 101–122.
  At 10 the same slap sends it out at 262–318 km/h.
- **WRIST TILT, 0 to 42 degrees** — seven detents, 7 degrees apart, on
  their own gauge. The launch always leaves along the palm normal, so this
  is genuinely a ballistic choice: flat is a skid down the road, 42 is a
  high arc that comes down somewhere you will have to go and look for.

The tilt does something less obvious as well. As the wrist rolls, the whole
hand is driven down a visible vertical slide in the wrist knuckle, so the
palm stays on a car's flank instead of climbing to its roofline. The slide
is not decoration — the roll would otherwise pull the foam stump out
through its own collar, and you can watch it working.

### The lane it cannot reach

The strike zone does not cover the full width of the corridor. Hold the
mast-side line and there is a drivable gap about 2.3 m wide where the palm
goes past your door. It is deliberate, it is measured, and it is the
difference between a prop that happens to you and one you can beat.

### The hand

Not a sculpt and not an imported mesh — every vertex is generated from one
scale factor and a set of anatomical measurements, so the whole thing is
reproducible from source.

- Four fingers and an opposed thumb, each rooted on a ball-and-socket
  knuckle concentric with its own pivot, so flexing a digit moves no
  surface point at the joint.
- The fingers are STRAPPED — two black elastic bands binding them into
  one tense paddle, exactly as the film prop's are, each band fitted to
  the actual finger surfaces it crosses. When the machine notices you,
  the fingers strain straighter against the straps.
- Palmar creases cut at real proportions, a thenar web built where the
  anatomy puts it rather than where it was convenient, metacarpal heads
  that show through the back of the hand and not the front.
- A mould parting line down both silhouettes, standing 84 mm proud, dressed
  back in stretches the way a mould shop actually gets it — because the
  loudest thing that says "this is a casting" is the flash the trimmer
  missed.
- Fingernails on their own plates, sitting at 1.18 times the skin's
  luminance, which is where they sit on the real prop this is modelled on.

Foam latex over a matte-black steel rig with cast-iron pivot bosses, guy
chains, hazard chevrons and a builder's plate. 8,010 kg, 26 posable parts.

### Details

- Full sequence: 0.45 s alert, 0.85 s wind-up, up to 3.2 s hold, a 0.28 s
  swing timed to arrive with you, 0.4 s follow hold, 0.55 s follow, 2.1 s
  return, 1.2 s cooldown. The palm tip passes 177 m/s at contact.
- The slap TUMBLES the car: the impulse lands on the flank above the
  centre of mass, so the car leaves rolling end-over-end with a drag yaw,
  through the engine's own physics — measured live at 6-7.6 rad/s. POWER
  scales the spin along with the speed.
- THE MACHINE KEEPS SCORE. It watches what it launched until it stops
  moving, then announces the flight while the palm is still held out:
  "213 m. 7 rotations. On its wheels." — and if you land on the roof, it
  waits a beat and adds "The hand pretends not to look." Rotations are
  measured off the car, not assumed.
- Speed helps. Arrive faster than the slap and the palm keeps your
  momentum instead of braking it — hot runs genuinely out-throw slow
  ones, so the scoreboard is a challenge, not a dice roll.
- The strike has a SOUND: a rising whoosh into a deep double thump,
  synthesized from source like everything else here, timed so the boom
  lands on the contact frame.
- Launch speed rolled per car at 28–34 m/s, then multiplied by POWER.
- Elevation comes from WRIST TILT alone; the launch is always along the
  palm normal, so the console reads as a real ballistic control.
- The corridor is an ARMING trigger, not a leash: leaving it does not call
  off a swing already being timed for you.
- The painted pad arms it too, independently of the corridor, and swings
  from rest at once.
- Nothing on the hand sweeps below the road at any tilt setting, parked or
  swinging — checked against every digit at every detent, not against a
  representative edge.
- Two-car targeting, correct in both directions.
- The machine drops you if you stop closing. It is not interested in
  parked cars.

### How to use

Spawn it from the vehicle selector like any prop, then drive a second
vehicle at it down the road it is facing. Give it room downrange: at stock
power a slap wants 100 m of clear ground, and a great deal more with POWER
up and TILT flat. Flat open spaces — Gridmap and the airfields work well.

Built with the shared giant-props framework, same shop as Charlie's Boot of
Doom. Feedback and bug reports welcome.

It already knows when you will get here.

---

# Upload

**Not yet submitted.** This mod has no `repo_update/` or `repo_submission/`
staging, and should not get one until the visual play-test below is done.

In-game, the vehicle selector card comes from the mod itself —
`authoring/ericrolph_high_five_thumbnail.jpg` is copied to `default.jpg`
and `standard.jpg` at build time, and the selector name comes from
`info.json` (`spec.DISPLAY_NAME`). Nothing to upload for those.

Regenerating everything:

```
blender --factory-startup --background \
    --python examples/giant_props/high_five/blender/create_high_five.py
python examples/giant_props/build.py high_five all
```

The Blender stage must run first. The palette ships inside the handoff, so
a `spec.py` edit followed by `build.py all` alone rebuilds the material
JSON from the *previous* palette — a trap this mod fell into once already.

**Textures are pre-cooked.** All 36 maps ship as DDS harvested from a game
session that actually loaded serial 25, certified against today's source
PNGs in `textures_cooked/ericrolph_high_five.harvest.json`. Players pay no
cook on first load and never see BeamNG's IMPORTING TEXTURE placeholder;
the trade is download size, 78.6 MB of PNG becoming 98.6 MB of DDS. To
re-harvest after any texture change:

```
# play the mod once so the game cooks the new PNGs, then:
GIANT_PROPS_PROFILE=%LOCALAPPDATA%\BeamNG\BeamNG.drive\current     python examples/giant_props/build.py high_five harvest
python examples/giant_props/build.py high_five all
```

Note the pack's re-zip trap applies from here on: `build.py <key> prop`
rewrites cooked DDS back to raw PNG for any mod WITHOUT a certified
manifest. This mod now has one, so `prop` keeps the DDS — but verify the
zip's member extensions after any re-cut rather than assuming it.

**Live gate: PASSING.** `tests/test_high_five_live.py` boots BeamNG in the
sentinel-isolated profile, spawns the prop, puts an ETK 800 85 m up the
approach corridor and drives it at the machine under its own power. It
asserts the full chain against a car that never stopped moving, which is
the one thing the headless harness cannot reach — a reactive machine would
produce most of this chain against a PARKED car and miss a moving one,
because a 0.85 s wind-up is 19 m at this speed. Measured in-engine:

| | measured |
|---|---|
| approach speed at the corridor's end | 25.8 m/s |
| outcome | `high_five_slapped`, not `high_five_whiffed` |
| slap speed the runtime rolled | 43.2–45.4 m/s across runs |
| speed the car actually reached | within 0.06 m/s of it |
| launch elevation vs WRIST TILT setting | **14.0 deg vs 14.0 deg** |
| runtime errors | none |

The same session then teleports the car onto the painted pad — authored
(0, 0), having never been inside the corridor — and requires a second
slap from `high_five_pad_swing`, which also proves the machine re-arms
after a full follow-through, return and cooldown. Measured: launched from
a standstill at 38.6 m/s.

That elevation row is the console's whole premise — the launch leaves along
the palm normal, so TILT is a ballistic control and not a decoration — and
until this gate existed it was only ever the arithmetic that produces it,
never the physics that results.

**The visual play-test happened** (2026-08-26, eight live sessions, three
critic lanes unanimously wowed): the palm visibly connects on film, the
dust travels, the scoreboard speaks on camera, the beacon proves itself
at midnight, and in-game action frames now exist for a gallery
(scratchpad frames2/3/4/6/7/8 of the build session).

**Still owed before upload:**

1. **Console cap click-boxes and frame cost** — the two questions only a
   human at a screen with a mouse can answer.
2. **`machined_steel`'s effective diffuse (0.0279) sits below the matte
   enamel's (0.0352)** — the bare metal is darker than the paint, which is
   backwards. Deliberately not corrected against a studio rig whose dim
   world flatters dielectrics and starves metals; check it under a real
   sky first.
3. **A whiff plays the full slap clip** — the whoosh is right for hitting
   air, but the foam whomp and crack play over nothing. A dedicated whiff
   tail (whoosh + mast clang) would sell "Left hanging." harder.
4. Filed for their own rounds: painted distance rungs down-road, a
   mechanical slap counter on the console, selling TILT 0 as the
   skipping-stone mode, documenting two-car pad griefing.

**Note on release hashes:** this mod has crossed the packaging timestamp
clamp (serial 26 against 24 days since the 2026-08-01 epoch), so its
`member_timestamp` now rides the build clock and a no-op rebuild no longer
reproduces its sha256. Its lock cannot be verified by re-cutting the way
the rest of the pack's can.
