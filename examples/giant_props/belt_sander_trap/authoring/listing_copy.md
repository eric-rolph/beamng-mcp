# beamng.com resource listing copy — The Belt Sander Conveyor Trap

## Subtitle (pick one)

1. A 26 m industrial belt sander that treats your car as the workpiece —
   grit-40 belt, six speeds up to 101 km/h, and a kicker lip for the ride out.
2. Land on the stopped grit and you get exactly 1.5 seconds of peace before
   the belt arms itself and starts dragging you toward the drum at up to 0.9 g.
3. Giant working belt sander — 24 travelling splice bars, a five-button
   console, an honest wall-clock speed gauge, and a no-jam law that launches
   wrecks.

## Description

**BELT SANDER No.3** — a 26 m industrial belt sander scaled up until a car is
the workpiece.

The machine greets you on the approach apron — console on your right,
setpoint 10 m/s, red STOP if you need off, drive up when you are ready.
Climb the 14.5 m loading ramp at a 15% grade, staring the whole way at the
safety-yellow nameplate on the tail gantry — GRIT 40, 6.0 m BELT, MIND THE
NIP. Then your tyres touch stopped grit, and for exactly 1.5 seconds,
nothing happens.

Then the belt arms. It spools toward its setpoint — zero to the 28 m/s top
rung takes 4.7 seconds — and starts hauling you toward the head drum, with a
live readout scoring the fight every half second: belt speed, your speed,
metres left to the drum. The drag is honest Coulomb friction and it scales
with belt speed: 0.13 g at the gentle 3 m/s rung, 0.43 g at the default
10 m/s (the rung that is actually a contest), 0.90 g at 21 m/s, where
nothing escapes. Matching the belt's speed is no refuge either — the drag
fades as your slip does, which is exactly the trap: you get swept up to belt
speed and then have to brake off 20+ m/s inside 21 m of machine. At the top
rung the stopping-distance arithmetic asks for over 600 m. There are 21.

Two ways off. Claw back out the feed end against anything above the bottom
rung and the machine concedes on screen: YOU BEAT THE BELT. Ride it to the
far end instead and the 18% kicker lip trips 0.6 m before the edge and fires
exactly once, adding up to 13 m/s of straight lift — 8.6 m of air — on top
of every bit of speed the belt gave you. The 20% outfeed embankment is the
landing. Twenty seconds after the belt is empty, the machine idles back down
and waits for the next car.

### The belt is real

The abrasive loop is not a scrolling texture. Twenty-four hazard-chevron
splice bars are real moving parts that travel the entire 47 m belt loop —
about eleven in view on the carrying run at any instant — and both 1.4 m
drums turn at exactly the belt's surface speed. The take-up tension rockers
on the tail gantry lift 8 degrees as the belt speeds up, and the grinding
dust and hot flare slide along the belt to stay on your contact line. Every
one of those motions is a pure function of ONE runtime variable — the live
belt speed — and the same number drives the drag under your tyres, so
nothing you see can disagree with anything you feel. The whole thing is
integrated against measured wall-clock seconds, so 10 m/s on the gauge is
10 m/s on the belt.

### The console

A five-button BELT SANDER CONTROL pedestal stands on the approach apron —
you drive past it on your right. Every cap is clickable:

- **RUN** — starts the belt at the setpoint and takes the machine back from
  any lockout.
- **STOP** — the rescue control, and it latches: the belt brakes hard (full
  speed to zero in 3.1 s), the toast quotes the real stopping time from the
  live speed, and the trap will not re-arm underneath the car you stopped it
  for. The lockout releases itself 3 s after the belt is clear.
- **EJECT** — an 8 s full-speed sweep, the same purge the jam law runs,
  carrying anything aboard out over the kicker; once the belt has been
  empty 20 s, the machine idles itself down.
- **SPEED − / +** — walks the six-rung ladder: 3, 6, 10, 15, 21, 28 m/s
  (11 to 101 km/h; 7 to 63 mph).

The gauge above the caps is honest print: the dial's tick labels are placed
at the exact angles the needle will point for each speed, so the print and
the pointer cannot disagree.

### Details

- A true trap lifecycle: the belt arms itself 1.5 s after anything lands on
  it and idles down 20 s after it empties — but only if it started itself.
  An operator RUN keeps running until told otherwise.
- The drag saturates at mu 0.92 (rubber on coated abrasive), so the field
  can never exceed real friction — and the belt face carries a genuinely
  high-grip ground model, so the grit bites and the steel transfer plates
  at either end genuinely do not.
- No-jam law: a wreck that sits still on a running belt for 22 s triggers
  an 8 s full-speed purge; still aboard 18 s after that, it is launched
  outright. Even the STOP lockout times out after 60 s with a dead car
  aboard. Nothing can pin this machine forever.
- Kicker discipline: it fires once per visit and ADDS its 3–13 m/s of lift
  to the speed you kept — never a teleport, and a thrown car is never
  re-grabbed in mid-air.
- The dust-extraction hood clears the belt by 3.6 m — a car standing on its
  roof still passes — and stops short of the kicker so a launched car flies
  out from under it. The cyclone's stack plume runs whenever the belt does.
- Open drum stations at both ends: drum shell, pillow blocks, take-up
  screws and the head-end flywheel are all on display, the way a real
  conveyor wears them.
- 34% side deflectors, a service walkway and raked safety-green guarding:
  the lane shrugs cars off its flanks instead of stopping them dead.
- A physics watchdog quarantines any car the crash solver has already lost
  and releases the belt field instead of feeding the wreck.

### How to use

Spawn it from the vehicle selector like any prop, then drive a second
vehicle in. Stop at the console to pick a rung, or skip it — the trap arms
itself at the default 10 m/s either way. It is long: 57.5 m of drivable
lane from ramp foot to outfeed toe, plus whatever the kicker adds. Give it
flat, open ground with a clear line past the outfeed — Gridmap and the
airfields work well.

Built with the shared giant-props framework. Feedback and bug reports
welcome.

Mind the nip.
