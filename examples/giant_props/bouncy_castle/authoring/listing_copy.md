# beamng.com resource listing copy — Bouncy Castle Landing Zone

## Subtitle (pick one)

1. A 20-metre inflatable castle with a real soft-body trampoline floor that throws your car up to 8 m in the air whenever it feels like it.
2. 81 sprung floor nodes, pillow walls, and a scripted BOING every one to five seconds — up to 45 km/h straight up.
3. Drive onto the quilt, get welcomed, wait a few seconds... BOING: one to eight metres of altitude, announced on screen to the metre.

## Description

**BOUNCY CASTLE LANDING ZONE** — a 20 m inflatable castle with a genuinely soft
physics floor. Cars don't crash here. They boing.

Drive up the ramp and through the six-metre gate. The moment you roll onto the
quilt, the castle greets you — "Boing! Welcome to the bouncy castle!" — and
quietly schedules your first super-jump: one to five seconds out, and it is not
telling you which. That pause is the whole joke. You sit there on a floor that
is already giving under your tyres, and then BOING — a ballistic kick worth
anywhere from one to eight metres of altitude, up to about 45 km/h (28 mph)
straight up, announced on screen with the height it rolled, to the nearest
metre. You land, the sprung floor hands most of the energy straight back, and
the next boing is already on the clock. It never stops scheduling. Stay an
hour and it will boing you for the hour.

### The trampoline

The floor is not an animation — it is real soft-body physics. A 9×9 lattice of
free, collidable sprung nodes (81 of them, on 2.5 m quilt cells) rides over a
fixed base frame at a damping ratio around 0.16 of critical, which is engineer
for "most of every landing comes back as bounce." Your suspension argues with a
floor that argues back. Three of the walls are stacked inflatable bolsters,
softer still than the floor, so glancing off them is part of the ride, not the
end of it.

### The boing schedule

Every vehicle on the floor runs its own independent jump timer — a random
one-to-five-second countdown to a random one-to-eight-metre launch. The
vertical kick is computed ballistically for the rolled height, so the
"BOING! +6 m" banner is arithmetic, not a mood. Kicks add on top of whatever
motion you already have, so mid-bounce momentum carries, and jumps taken
off-centre drift you gently back toward the middle — the chaos self-contains
by design. Come back within six seconds of the last hello and the castle
skips the pleasantries and goes straight back to scheduling.

### Details

- Real trampoline floor: 81 free sprung collision nodes in a 9×9 grid over a
  fixed base at ~0.16 of critical damping — the deck is springy even before
  the script does anything.
- Drop-tested: an earlier floor let a car dropped from 8 m punch straight
  through to the terrain. The shipping floor catches it.
- Pillow walls on three sides topping out at 3.4 m; the south side is the open
  gate with a bumper-railed entry ramp.
- Truth in advertising: every launch is rolled between 1 and 8 m, converted to
  an exact ballistic kick, and announced to the metre.
- Tuned down for your own good: the maximum roll used to be 20 m, until cars
  kept sailing clean over the walls. Eight keeps the party inside.
- The bounce zone blankets the full 20 × 20 m floor and the first 4.4 m of air
  above it — bring friends, every car inside bounces on its own timer.
- Castle dressing: corner towers with cone roofs and flags, alternating
  red-and-yellow battlements along the wall tops, quilted vinyl throughout.
- Books into the vehicle selector at $32,000. Commercial-grade inflatable
  vinyl is not cheap.

### How to use

Spawn it from the vehicle selector like any prop, then drive a second vehicle
in through the south gate — the entry ramp reaches 14.6 m out from the
castle's centre, so give it a flat pad roughly 30 m on a side. Gridmap and the
airfields work well. There are no buttons and no control zones: any vehicle
that reaches the floor is on the schedule automatically, and it comes off the
schedule the moment it leaves. It also makes a fine crash mat — aim your ramp
jumps at the quilt and let the floor do the catching.

Built with the shared giant-props framework. Feedback and bug reports welcome.

The next boing is already scheduled. The castle just isn't telling you when.
