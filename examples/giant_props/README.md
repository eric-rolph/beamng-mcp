# Giant Props pack

Twenty-three oversized cartoon contraptions for BeamNG.drive, built on the Cannon
Car Wash evidence chain: a deterministic Blender generator owns every coordinate,
an exact-coordinate handoff JSON is the single physics source of truth, and
every runtime file is generated — never hand-edited.

| Mod key | Prop | The bit |
| --- | --- | --- |
| `giant_toaster` | The Giant Toaster | Park in a slot, the lever drops and it ticks... then POP: vertical launch. A drive-by browning dial sets power 1–6. |
| `monster_flyswatter` | Monster Flyswatter | Enter the lane, the raised swatter trembles, then slams. Timing game: the head deliberately misses the outer lane edge. |
| `bouncy_castle` | Bouncy Castle Landing Zone | Genuinely soft physics floor (free sprung nodes, ~0.12 damping ratio) and pillow walls. Cars boing. |
| `vacuum_of_doom` | The Vacuum Cleaner of Doom | Spool-up dust, a scripted pull field into the nozzle, SLURP, then an exhaust-stack eject on the far side. |
| `dino_egg_hatcher` | Dino Egg Hatcher | Drive in through the crack; the dome shards rattle, then burst outward as the car launches. Shards cartoon-rewind to re-arm. |
| `catapult_seesaw` | The Catapult Seesaw | Hold still on the X for three counted seconds; the ten-ton block drops on the far end and flings you. |
| `spin_cycle_washer` | Washing Machine Spin Cycle | Door closes, suds mist, drum spins up, scripted tumble, then the door flings open mid-spin. |
| `whale_geyser` | Whale Blowhole Geyser | The tail is the ramp. Park on the blowhole; after the inhale, ride a water column ~24 m up, hover, drop. |
| `boot_of_doom` | The Boot of Doom | The sneaker notices you, draws back, and punts you field-goal style over decorative goal posts. |
| `pendulum_gauntlet` | Wrecking Ball Pendulum Gauntlet | Four real physics pendulums (heavy free-node balls on cables, authored displaced ±40°) over a squishy inflated-mat bridge. |
| `spin_launch` | Spin Launch Kinetic Accelerator | Drive into a 43 m vacuum chamber standing on edge. The airlock seals, the chamber pumps down, the load deck sinks away, and a composite tether whips you round until the tangent points where the console says. POWER 28-182 m/s and ELEVATION 34-72 deg, on a launch tube that pivots around the rim to stay tangent to the release point. |
| `high_five` | Charlie's High Five | An 8.6 m foam-latex hand on a 12.6 m slewing arm. It LEADS you: it reads your closing speed and starts the swing so the palm arrives when you do, at any speed. POWER 1-10 and WRIST TILT 0-42 deg; the launch always leaves along the palm normal. Hold the mast-side line and it goes past your door. |
| `colossus_tire` | COLOSSUS 10350/80R457 | A 28.17 m earthmover radial standing on its tread, and the only prop in the pack that moves entirely on its own physics. Board through the bolted access port in its right sidewall, the tie-downs are cut, and from then on it rolls because YOU push its inner liner and its tread pushes the ground. The runtime never touches it — it fits the axle to three live crown nodes and reports what the physics did, and it is one of two mods in the pack (with `catapult_seesaw`) that set `ALLOW_SUBJECT_MUTATION = False` so it structurally cannot. |
| `giant_fan` | The Giant Fan | A GALEFORCE GF-3600 table fan at 108x with the guard CUT OFF. Each blade is a city bus long and passes 0.35 m over a drivable deck. The rotor is a real jbeam `rotators` body - the stock large_spinner mechanism - so a blade wrecks a car with moving collision geometry at the solver's 2000 Hz, and bogs when it does. The dial keeps the reference detent order 0-3-2-1, so THE FIRST CLICK FROM OFF IS FULL POWER; the chrome plunger on the housing crown starts the 90 deg sweep; BLADE HEIGHT picks which vehicles get hit. |

Design rule shared by every contraption: **exaggerate the anticipation**.
The toaster ticks, the swatter hovers, the egg wobbles, the whale inhales,
the boot draws back, the airlock seals in your face — the pause
before the chaos is the joke.

## Layout

- `proplib/` — shared toolkit: `blender_kit.py` (Blender-side authoring +
  cage builder + exports), `prop_builder.py` (handoff → JBeam/materials/
  info/bootstrap), `lua_kit.py` (generated GELua runtime with the shared
  trigger lifecycle and per-mod behaviour chunk), `packaging.py`
  (deterministic `ZIP_STORED` distribution builder).
- `<mod_key>/spec.py` — the mod's authored constants (geometry numbers,
  palette, triggers, effects, tunables, and the Lua behaviour chunk). The
  Blender generator and the runtime consume the same values.
- `<mod_key>/blender/create_<mod_key>.py` — deterministic generator.
- `<mod_key>/authoring/` — handoff JSON + thumbnail render (evidence).
- `<mod_key>/assets/` — checked-in files that are *not* generated: hero `.glb`
  meshes the Blender generator imports, the baked maps the `external` texture
  family stages into `<mod_key>/textures/`, and the odd file the game itself
  opens by path at runtime (the washer's LCD `screen.html`). These are BUILD
  INPUTS by default and do not ship. **Shipping is opt-in**: a spec lists the
  runtime-loaded ones in `SHIP_ASSETS` (paths relative to `assets/`) and
  `prop_builder` stages exactly those into the vehicle folder. A blind copy of
  this directory once shipped boot_of_doom's 3.6 MB hero `.glb` plus a second,
  unreferenced copy of its three baked maps — 11 MB of a 42 MB ZIP that nothing
  in the built tree pointed at.
- `<mod_key>/mod/` — the generated distributable tree.
- `<mod_key>/dist/` — the stable-named ZIP plus its SHA-256 lock.

## Building

```powershell
$blender454 = 'C:\Users\ericr\Applications\Blender\4.5.4\blender.exe'

# 1. Procedural PBR texture sets (deterministic, seeded; numpy/Pillow in the
#    repo venv — Blender only loads the PNGs for preview).
.\.venv\Scripts\python.exe .\examples\giant_props\build.py <mod_key> textures

# 2. Geometry, cage, handoff, thumbnails (deterministic).
& $blender454 --factory-startup --background `
  --python .\examples\giant_props\<mod_key>\blender\create_<mod_key>.py

# 3. Handoff -> JBeam/materials/runtime/textures, then the distribution ZIP.
.\.venv\Scripts\python.exe .\examples\giant_props\build.py <mod_key> all
```

## Textures

`proplib/texture_kit.py` generates tileable colour/normal/roughness (and
opacity) PNG sets per material, seeded by material name. Families are
grounded in real references (2026-07-22 research pass): Sunbeam-style
scribed chrome and bakelite, commercial PVC inflatable vinyl with
triple-stitch seam bands, RIDGID-style ribbed poly drums, perforated
stainless washer drums, forged pear wrecking balls on chain, powder-coated
playground steel, Chuck Taylor-style canvas/foxing/gum tread. Large
surfaces use metric box UVs (`metric_uv=` on the primitives) so texel
density stays true in meters — the Cannon Car Wash "tiny blocks" lesson.
Ships as PNG (BeamNG cooks on first load); pre-cooked DDS remains a
Repository-upload step, per the car wash release policy.

The 2026-08-24 tire pass added seven more, because the kit's existing
`rubber_tread` is a *sneaker outsole* and none of the five surfaces a real
tire presents look like each other: `tire_tread` (mould grain, vent spew
whiskers, stone nicks, a polish mask that lightens and smooths together),
`tire_sidewall` (circumferential mould ripple, parting line, ozone checking,
and antiozonant bloom deposited in the RECESSES rather than sprayed on),
`tire_sidewall_print` (raised moulded print — it drives height, not colour,
because that is what makes real sidewall type legible), `tire_liner`
(halobutyl with the curing bladder's vent lattice embossed into it),
`tire_laminate` (the carcass in section for the port's cut edge: liner, tie
gum, casing plies, cushion, four steel belts, nylon cap ply, undertread,
tread cap, with steel cord cross-sections at their own per-band pitch),
`tire_bead` (woven chafer over apex stock, rim-polished) and
`diamond_plate`.

## Validation

```powershell
# Static gates for every mod (handoff hashes, JBeam/cage consistency,
# materials coverage, runtime boilerplate, ZIP locks).
.\.venv\Scripts\python.exe -m pytest -q .\tests\test_giant_props_pack.py

# Headless state-machine gates: the REAL generated runtime.lua run under
# lupa against stubbed engine globals. Cheap, and they see mechanics the
# static gates cannot - hot_potato's multi-car passing, spin_launch's
# release window and its aiming identity.
#
# THESE SKIP SILENTLY WITHOUT lupa, which is why they are run from the repo
# venv above and not from a bare `python`. A review that reported "all gates
# pass" from an interpreter without lupa was reporting on a suite in which
# every one of these had quietly been skipped.
.\.venv\Scripts\python.exe -m pytest -q .\tests\test_hot_potato_logic.py `
    .\tests\test_spin_launch_sequence.py .\tests\test_colossus_tire_sequence.py

# Per-mod structural gates the shared pack suite cannot express.
# colossus_tire's carries a unilateral-contact static solver: it settles the
# real cage under gravity TO A RESIDUAL - not to a step count, which stopped
# with the ground carrying a third of the weight and made every number taken
# off the settle a measurement of a falling tire - and then fails if the
# contact patch comes out too narrow to stand on, or if the boarding
# centreline has a hole or a step in it once everything has sagged.
#
# It also parses the SHIPPED Collada, which for a long time nothing did: zero
# degenerate faces, zero duplicated faces, zero edges traversed the same way
# by both their faces, zero triangles with world area and no UV area, every
# material at its authored grain size KEYED BY GEOMETRY (three of them appear
# in both meshes and a bare key let one silently overwrite the other), every
# closed solid of positive volume - the one orientation rule with no escape
# hatch, and the one that finally caught nine inside-out port gussets - and a
# mesh that is already welded, because joining one object per surface for
# export left 554 coincident vertex pairs down each edge of the drive lane
# carrying a 30-degree false crease.

# And the textures, which until round 4 nothing in the suite opened at all:
# slope in the pack's band, slope that still survives two mip levels, no wrap
# step larger than the map's own interior steps, and a decoded albedo that
# matches what the palette says it asked the family for.
.\.venv\Scripts\python.exe -m pytest -q .\tests\test_colossus_tire_textures.py
.\.venv\Scripts\python.exe -m pytest -q .\tests\test_colossus_tire_geometry.py

# Live gates (opt-in; sentinel-isolated profile). The toaster one boots BeamNG
# with the packaged Giant Toaster and proves the shared runtime core every mod
# generates: register -> zone -> tick -> POP -> launch.
#
# The Colossus one proves the four things static gates structurally cannot
# reach for a free-rolling body: that 1,072 free nodes carrying 10.5 t stand
# upright and stay round after real physics has had them; that the dock and
# the inner liner are solid FROM ABOVE (a one-sided collision triangle wound
# the wrong way is invisible to everything else); that the doorway is clear;
# and that pushing the SUBJECT rolls the tire. Its first run found a bug
# nothing headless could - the runaway detector measured 3D drift, and a 28 m
# carcass settles 0.36 m onto its own contact patch, so it fired "the
# tie-downs have parted" before anyone boarded and suppressed the whole
# boarding beat for the rest of the session.
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_giant_props_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_colossus_tire_live.py

# ...and the HILL gate, which is the only one that answers the question the
# prop actually raises. It boots on `utah`, settles the carcass on a MEASURED
# slope, cuts the tie-downs and then touches nothing: everything after that
# is gravity. Two grades, because they prove opposite things.
#
#   3.4 deg   the chocks HOLD. It has to climb its own 0.705 m wedge to get
#             out, which needs about 16 deg of grade, so it creeps 0.96 m in
#             30 s. A chock that let 10.5 tonnes walk out of it would be
#             scenery rather than hardware, so that is asserted too.
#   22.9 deg  gravity climbs the chock and it goes: 78 m of travel, 47 m of
#             descent, 1.24 revolutions, ~11 km/h average - and it finally
#             lies over on the camber, which is what a free tire does.
#
# The FLAT gate carries the material measurements, because smallgrid is a
# perfect plane and there is nothing to blame a reading on:
#
#   slip ratio 1.007   coasting freely at 3.2 m/s, path length against
#                      R x d-theta. It rolls without slipping to 0.7%.
#   ripple 6.4 mm RMS  steady rolling, against a 30.2 mm facet sagitta on the
#                      48-station collision hull. The contact patch swallows
#                      the polygon by about five to one.
#   Crr 0.062          free-coast deceleration over g. Hysteretic - the right
#                      mechanism - but high: a real tire is 1-2% on hard
#                      ground and 5-8% on soft, so this reads as soft ground.
#                      Halving the tread damping moved it by 0.2 points, so
#                      the loss is spread across sidewall, casing and the
#                      inflation truss, not concentrated in the tread.
#   ring 458 mm p-p    the carcass oscillating on its own compliance after an
#                      18 m/s impact, decaying over a few seconds. A rigid
#                      hoop would not do it at all.
#
# The measurement that matters is PATH LENGTH against R x d-theta over the
# UPRIGHT segment: 0.852, where a rigid drum reads 1.000. That shortfall is
# the loaded-tire signature (0.89 against the loaded radius rather than the
# free one), and it is the one number that separates this from a barrel.
# The carcass held its shape through all of it: 0.37 m worst radius error
# over a 90 m run that ended in a tumble.
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_colossus_tire_hill_live.py
```

The live gate exercises the shared runtime core every mod generates
from `lua_kit.py`. Per-mod live play-testing (soft-body tuning for the
castle/bridge, pendulum amplitude, ride controller feel) is still expected
before any public upload; see AGENTS.md for the sentinel-profile rules.

## Physics notes

- Static contraptions are all-fixed cages (Cannon Car Wash values: 15 MN/m
  beams, `FLT_MAX` strength). Rigidity is irrelevant for fixed nodes; beams
  exist for connectivity and flexbody binding.
- The castle floor/walls and gauntlet deck/bumpers are *free* collidable
  nodes on named soft beam specs, anchored to fixed frames — one connected
  cage per prop, per the v1 constraint.
- The wrecking balls are free-node octahedra with their own collision
  triangles on stiff cable chains; authored displaced so gravity swings them
  from spawn. Air drag decays the swing over minutes; resetting the prop
  re-cocks them.
- Launches replace subject velocity via
  `applyClusterVelocityScaleAdd(refNode, 0, ...)`; force fields (vacuum,
  geyser, tumble) integrate small per-frame velocity adds with
  position-delta speed caps.
- `spin_launch` is the one prop that has to hold a payload on a VERTICAL
  circle, which no force field can do - gravity wins at the top. Its tether
  field REPLACES the ref-node cluster velocity every frame with the tangent
  plus a correction toward the tether point, so the constraint lives in
  velocity space and the car cannot fall off. The soft body still takes the
  full escalating G-load, because only the ref-node cluster is driven and
  every other node has to follow it through its own beams.
- `colossus_tire` goes the other way and drives NOTHING. It is 212,484
  visual triangles over 1,074 free nodes
  in a tire-shaped cage — bead bundles, casing plies, a steel belt package
  with long chords to stations ±2 and ±3, sidewall rubber, a tread slab that
  flattens into a contact patch, and a soft damped truss across the cavity
  standing in for the air a real tire is pressurised with. The car rolls it
  by pushing on the inner liner; the ground rolls it back. Its runtime fits a
  circle to three live crown nodes 120° apart to recover the axle, the
  rotation and the ground speed, which is exact and keeps working 300 m from
  the dock where a trigger box cannot follow. Damping is picked per material —
  the rubber families run 15-20% of critical because rubber's loss tangent
  really is that high, the steel families 4-6%.
