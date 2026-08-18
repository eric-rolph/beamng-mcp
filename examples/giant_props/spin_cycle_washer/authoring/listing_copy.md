# beamng.com resource listing copy — Washing Machine Spin Cycle

## Subtitle (pick one)

1. A 13 m front loader that floats your car in 5.2 m of wash water, spins the
   whole pool to 76 RPM, and throws you out the porthole at 92 km/h.
2. Drive in through the glass door, bob on a real waterline, get carried
   around the drum at 65 km/h, and leave with the drain surge.
3. Giant working washing machine — real buoyancy, suds, a 46-degree banking
   waterline, and a porthole that flings open mid-spin.

## Description

**WASHING MACHINE SPIN CYCLE** — a 13 m front loader that treats your car as
a full load of laundry.

Roll up the ramp and it taunts you before you're even inside: "Delicates
cycle? No. MAXIMUM SPIN." Drive through the open porthole and the glass door
swings shut behind you in one second. Then — the pause. For three seconds
the fill spray runs and 5.2 m of wash water rises around your car, and you
float. You bob. The pool is already creeping into a lazy 6 RPM slosh,
gently dragging you with it. The machine is savouring this.

Then the slosh becomes a current. A four-second wash cycle winds the pool
up to a deceptively gentle 27 RPM while suds foam on the surface and the
waterline starts to tilt. Five more seconds take it to MAXIMUM SPIN: 76
RPM, the surface banked at about 46 degrees and climbing the wall with your
car in it, the current carrying you around the drum at up to 65 km/h
(40 mph). At the peak the porthole flings open in a quarter of a second
and the water leaves — and so do you: 24 m/s out the door and 9 m/s
straight up, a 92 km/h (57 mph) launch at about 21 degrees, riding the
drain surge.

### The water

The water is not a cut-scene — it is a per-frame force field on your car. A
buoyancy controller bobs you toward the live waterline, with weight support
that scales in as you submerge, and the swirl drags you toward the spinning
water's own local velocity (omega times radius) — hard-capped at 18 m/s, so
the current can carry you but never hit you harder than the water itself is
moving. Per-frame velocity changes are capped at 2 m/s: you get pushed,
never teleported. The visible pool genuinely rises, banks with the spin,
and wobbles at the surface, and the suds ride on top of it.

### The drum

An 8.4 m-wide, 10 m-deep drum bored straight through the front of a 13 m
enamel cabinet, with double porthole trim, a rubber door gasket, a
detergent drawer, a program dial, and a warm lamp strip across the top of
the mouth so the interior reads as a lit drum instead of a black void. The
ribbed liner spins in lockstep with the water — at full spin its rim is
doing 121 km/h; be glad the current is capped at 65. The glass door swings
through 110 degrees: a full second to close you in, a quarter-second to
throw you out.

### Details

- Fully automatic cycle, nothing to press: door close (1 s), fill (3 s),
  wash (4 s), MAXIMUM SPIN (5 s), fling, a 1 s drain, then a 3 s cooldown
  before it re-arms itself for the next load.
- Ejection rides the drain: 24 m/s out plus 9 m/s of lift, fired 0.3 s
  after the door starts to fling, with a steam burst out the mouth.
- Real buoyancy and swirl forces, all speed-capped (18 m/s water field,
  2 m/s per-frame delta) — pushy water, not teleporting water.
- Escape clause: back out while it is loading or filling and it concedes —
  "The laundry escaped!" — reopens the door, drains, and resets.
- Wreck-safe: if the loaded vehicle despawns mid-cycle, the machine aborts
  and drains instead of jamming.
- Fill spray from above, suds mist from the wash cycle until the fling,
  foam floating on the waterline, door steam on ejection.
- Valued at $34,000 in the vehicle selector. Commercial-grade, allegedly.

### How to use

Spawn it from the vehicle selector like any prop, then drive a second
vehicle up the front ramp and through the porthole. The cycle starts on its
own once you are fully inside the drum. Give it flat open ground: the
cabinet is 13 m on a side, the entry ramp runs about 6 m out the front, and
the machine throws you back out the way you came in — keep that lane clear
for the landing. Gridmap and the airfields work well.

Built with the shared giant-props framework. Feedback and bug reports
welcome.

Delicates cycle? No.
