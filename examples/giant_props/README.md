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
| `gforce_centrifuge` | Charlie's LAHC Centrifuge | A 48 m hypergravity drum: drive in, twelve speed stages pin you to the wall toward 500 RPM, then it throws you out the front door. For science. |
| `glass_atrium` | The Glass Atrium | A ten-storey glass tower: the lift hoists you 40 m, counts down from three, and drops you through every floor of real breakable glass. |
| `spider_web_catcher` | 200MPH Spider Web Catcher | A 15 m elastic orb web arrests a 322 km/h car on real snapping silk strands — then the spider descends to look you over. |
| `pachinko_tower` | Vertical Vehicle Pachinko Tower | A pachinko board stood on end: a chain mast hoists you 43 m up the 52 m tower and tips you into 65 steel pegs and five scoring bins. |
| `belt_sander_trap` | The Belt Sander Conveyor Trap | A 26 m belt sander treats your car as the workpiece: 1.5 s of peace on the stopped grit, then six speeds up to 101 km/h drag you toward the drum and the kicker lip. |
| `sumo_gyro_platform` | The Free-Pivot Sumo Gyro-Platform | A 26.2 m, 212-tonne steel dish balanced on one spherical bearing. Drive two cars aboard and fight over which way "down" points. |
| `junk_chute_grinder` | Junk Chute Grinder Trap | Climb 53 m of haul ramp, nose over the lip, and 120 steel hooks take the car apart through a 2.9 m nip at 14.3 RPM, onto a working scrap conveyor. |
| `football_goal_post` | Charlie's Football Field Goal | A regulation gooseneck goal post: 45 ft of painted steel, cloth flags on real wind, and it knows when you score. |
| `hot_potato` | Hot Potato | A quarter-scale stainless Gateway Arch — the real weighted catenary, panel-quilted steel — with a two-metre smoking, hissing potato under the apex. Claim it at the medallion; it rides your roof bouncing to its own accelerating tick while a hidden fuse burns, and when it runs out, whoever holds it gets wrecked — mashed potato everywhere — before the tuber flies itself home. Classic, hoarder and pinball modes, a hardcore no-tells cue style, and a champion crowned with their name written in fireworks over the arch. The in-game HUD app carries the live status and the full tuning drawer. |
| `spin_launch` | Spin Launch Kinetic Accelerator | Drive into a 43 m vacuum chamber standing on edge. The airlock seals, the chamber pumps down, the load deck sinks away, and a composite tether whips you round until the tangent points where the console says. POWER 28-182 m/s and ELEVATION 34-72 deg, on a launch tube that pivots around the rim to stay tangent to the release point. |
| `high_five` | Charlie's High Five | An 8.6 m foam-latex hand on a 12.6 m slewing arm. It LEADS you: it reads your closing speed and starts the swing so the palm arrives when you do, at any speed. POWER 1-10 and WRIST TILT 0-42 deg; the launch always leaves along the palm normal. Hold the mast-side line and it goes past your door. |
| `colossus_tire` | COLOSSUS 10350/80R457 | A 28.17 m earthmover radial standing chocked in a yard, and the only prop in the pack that moves entirely on its own physics. Come near it and the release cuts all forty tie-downs and WINCHES the chocks clear; after that you can push it, release it on a grade and chase it, or get a car into the cavity (deliberately no ramp — teleport in) and drive: the liner is a real surface, and driving inside turns the wheel. The runtime never drives it — it fits the axle to three live crown nodes, narrates, and cues the audio, and it is one of two mods in the pack (with `catapult_seesaw`) that set `ALLOW_SUBJECT_MUTATION = False` so it structurally cannot. |
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
# contact patch comes out too narrow to stand on.
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
# reach for a free-rolling body: that 1,080 free nodes carrying 5.0 t stand
# upright and stay round after real physics has had them; that the shipped
# release really frees it (the ram waits for the release EVENT, and the
# winched wedges leave the ram line); that the coast is a roll and not a
# slide; and that pushing the SUBJECT rolls the tire. Its first run found a bug
# nothing headless could - the runaway detector measured 3D drift, and the
# round-2 10.5 t tune settled 0.36 m onto its own contact patch, so it fired "the
# tie-downs have parted" before anyone boarded and suppressed the whole
# boarding beat for the rest of the session.
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_giant_props_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_colossus_tire_live.py

# ...the HILL gate: `utah`, three measured slopes, spawn SQUARE TO THE HILL
# (the slope quat is calibrated against BeamNG's opposite-handed rot_quat -
# uncorrected it stood the tire side-on to the fall line), cut the ties, winch
# the chocks clear the way the shipped release does, then touch nothing:
#
# (numbers are the final committed run, serial 60)
#   3.4 deg    PATCH STATICS HOLD IT. The release winches the chocks away,
#              so nothing scripted restrains it: the transient walks it
#              4.5 m downhill at rolling slip 1.21, then it stands. What it
#              may not do is run or fall.
#   13.1 deg   THE RUNAWAY DEMO (nominal 12.4, measured 13.07). Cutting the
#              ties is enough: it rolls off ~29 m of displacement with real
#              rotation, then carves into its ~6 deg settle lean and lies
#              down - which is what dropped tires notoriously do. The gate
#              deliberately does NOT assert the fall line or staying up.
#   22.9 deg   IT THUNDERS: 42 of 45 m down the fall line, 334 deg of
#              rotation at pre-tip slip 0.84, over at ~42 m.
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_colossus_tire_hill_live.py

# ...and the HAMSTER gate, the mod's whole point: a car TELEPORTED into the
# cavity (spawn placement silently relocates a vehicle spawned inside another
# one - measured twice at identical coordinates) lands on the liner, arms the
# machine by being in the approach zone, and after the shipped release cuts
# the ties and winches the chocks clear, DRIVING INSIDE TURNS THE WHEEL:
# a straight lap measured 93.75 m of tire travel at slip 0.994; the final
# committed run steered a curved lap - path 32.1 m against arc 39.3 m,
# rolling ratio 0.82 - car still inside throughout. The mass is
# set by that inequality - breakaway needs m/(M+m) > e/(R sin phi), because
# the tire's own contact patch is a built-in chock that statically reacts
# ~(M+m)*g*e before the wheel has to roll. Measured at the 6 t tune: 115 kNm
# held with all 40 straps audited broken; at the shipped 4.2 t the patch
# holds ~94 kNm against the ~125-133 a mid-wall station supplies.
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_colossus_tire_hamster_live.py

# The FLAT gate carries the material measurements, because smallgrid is a
# perfect plane and there is nothing to blame a reading on:
#
#   slip ratio 1.008   coasting freely, path length against R x d-theta.
#                      It rolls without slipping (0.994 driven from inside,
#                      0.997-1.02 across every clean-ground run).
#   ripple 7-15 mm RMS steady rolling by speed window, against a 30.2 mm
#                      facet sagitta on the 48-station collision hull: the
#                      ~95 mm contact patch swallows the polygon.
#   Crr 0.023-0.031    free-coast deceleration over g, by speed window -
#                      real-tire territory (1-2% hard ground, 5-8% soft).
#                      It took three retunes to get here from 6.2%:
#                      stiffness x3.2 to the integrator ceiling, then two
#                      mass rescales with k/M held constant, because the
#                      residual loss lives in the engine's contact model and
#                      scales with weight.
#   ring ~0.2 m p-p    after a 12 m/s ram, decaying in about a second - and
#                      the run's first metres now include honestly SHOVING
#                      both 200 kg front chocks out of the path (their
#                      collision hulls are closed; nothing ghosts through
#                      them). The jelly this carcass shipped with - 458 mm
#                      of ring, 250 mm of static sag - is gone: deflection
#                      is ~95 mm on a 14 m radius, modes ~1.8x higher.
```

The live gate exercises the shared runtime core every mod generates
from `lua_kit.py`. Per-mod live play-testing (soft-body tuning for the
castle/bridge, pendulum amplitude, ride controller feel) is still expected
before any public upload; see AGENTS.md for the sentinel-profile rules.

## Local play deployment

```powershell
# Report the REAL play profile (%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\mods)
# against every mod's release lock, shadow-scan the mods tree by zip CONTENT,
# and diff the unpacked MCP bridge code. Exits nonzero on any finding.
.\.venv\Scripts\python.exe .\examples\giant_props\deploy_local.py

# Copy exactly what is stale, re-hash each copy against its lock. Refuses to
# run while BeamNG is open or while a namespace conflict stands.
.\.venv\Scripts\python.exe .\examples\giant_props\deploy_local.py --deploy
```

The play profile is not the sentinel test profile: live gates keep installing
through the service into the isolated profile, and nothing test-shaped ever
goes to the real one. The full rules are in AGENTS.md under "Local play
deployment".

## Playtest eye (whole-image aesthetic evidence)

```powershell
# Boot the sentinel rig, spawn the packaged mod plus a parked scale vehicle,
# solve orbit/approach/detail cameras off the prop's measured world box, and
# capture NORMAL-EXPOSURE in-game screenshots (what a player actually sees;
# renderViews' fixed exposure cannot adjudicate look). Writes frames,
# manifest.json, and a labeled contact_sheet.jpg to
# <mod>/authoring/playtest_eye/ (gitignored evidence, like authoring/verify/).
.\.venv\Scripts\python.exe .\examples\giant_props\playtest_eye.py <mod_key>
```

The contact sheet is sized for a vision-language reviewer to judge the set as
a whole; `playtest_eye_rubric.md` is the prompt contract that turns that
judgment into ranked, measurable findings for the critic loop. Blender
renders in `authoring/verify/` remain the per-feature instrument; the eye is
the in-game gestalt instrument — first read, silhouette, scale against the
parked vehicle, material response under real tonemapping, grounding.

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
- `colossus_tire` goes the other way and drives NOTHING. It is ~264,000
  visual triangles over 1,080 free nodes (1,056 carcass + 24 in four loose
  chock wedges) in a tire-shaped cage — bead bundles, casing plies, a steel
  belt package with long chords to stations ±2 and ±3, sidewall rubber, a
  tread slab that flattens into a contact patch, and a soft damped truss
  across the cavity standing in for the air a real tire is pressurised
  with. A car rolls it by pushing on the inner liner; the ground rolls it
  back. Its runtime fits a circle to three live crown nodes 120° apart to
  recover the axle, the rotation and the ground speed, which is exact and
  keeps working 300 m from its spawn where a trigger box cannot follow.
  Damping is a RATIO, not a loss tangent (that lesson is recorded in
  AGENTS.md): rubber families sit at 0.12-0.25 of critical — the material's
  tan-delta converts to ~5-12% and the rest is settling margin the live
  gates pay for — and the steel families under 0.12.
