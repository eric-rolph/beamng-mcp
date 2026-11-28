# Hot Potato — design blueprint

Status: **built and play-tested live** (2026-08-25). Static suite, a 14-case
headless state-machine gate (`tests/test_hot_potato_logic.py`) and a live run
on the sentinel-isolated profile all pass: pickup, transfer on a real impact,
and detonation were each confirmed in game with screenshots.

v2 replaced the structure and the pickup. What v1 shipped and why it failed is
kept below, because the failure is the useful part.

A carried explosive passes between vehicles on contact or proximity. When the
fuse runs out, whoever is holding it gets wrecked. Last car intact wins.

This document adapts the general BeamNG blueprint to *this* repository: the
Giant Props framework (`proplib/`), the evidence chain in `AGENTS.md`, and the
APIs that BeamNG 0.39 actually ships. Section 1 is the part worth reading
first — a third of the reference blueprint does not survive contact with the
shipped engine.

---

## 1. Blueprint audit

Every claim below was checked against the game's own Lua tree at
`E:\SteamLibrary\steamapps\common\BeamNG.drive\lua\` and against the laws
recorded in `AGENTS.md`.

| Blueprint claim | Verdict | What is actually true |
| --- | --- | --- |
| `onVehicleCollision(veh1, veh2, ...)` GE hook | **Does not exist** | Zero occurrences in the entire shipped Lua tree. There is no vehicle-vehicle collision event on the GE side at all. Touch must be derived positionally (§4). |
| `veh:getSpawnWorldOBox()` | **Wrong name** | `getSpawnWorldOOBB()`, used all over `ge/extensions/career/`. `:getHalfExtents()` confirmed live (AGENTS.md round 15). The version this row used to name, "0.38.6", came from the test PROFILE DIRECTORY name and not from an engine; the repo's only engine-REPORTED strings are `0.38.6.0.19963` and `0.39.2.1` (cannon_car_wash telemetry) and `0.39.4.0 build 20972` (the current install). The call was not re-run this round, so read it as as-verified-then. |
| `Engine.Platform.getRealMilliseconds()` | **Does not exist** | `Engine.Platform.getSystemTimeMS()` (`ge/extensions/core/cameraInput.lua:26`). |
| `fire.explodeVehicle()` | **Exists, does something else** | `vehicle/fire.lua:427`. It walks `flammableNodes`, sets `vaporState = 100`, breaks container beams and ignites. That is a **fuel-tank ignition**, not a blast: no impulse, no deformation, nothing at all on a vehicle with no flammable nodes or with fire disabled in gameplay settings. It is a *garnish*, not the detonation. |
| `obj:addForce(id, vec3(...))` | **Wrong name** | Per-node force is `obj:applyForceVector(cid, vec)`; time-scaled is `obj:applyForceVectorTime(cid, vec, dt)` (`vehicle/controller/playerController.lua:164-202`). |
| 80,000 N one-shot "crushes the chassis flat" | **Off by orders of magnitude** | `applyForceVector` is one physics step. At 2000 Hz and a ~20 kg node, 80 kN buys Δv ≈ F·dt/m = 2 m/s for that node — a nudge. A crush needs the force *sustained across a window* of vehicle ticks (§5, Tier C). |
| `Engine.Audio.playOnce('AudioChannelExplosion', 'art/sound/explosion.ogg', pos)` | **Wrong signature and wrong mechanism** | Shipped form is `Engine.Audio.playOnce('AudioGui', 'event:>UI>Career>Buy_01')` — an FMOD *event path* on a named channel, not a file path, and no position argument. AGENTS.md records the file-path and `SFXEmitter` routes as unprovable/silent; this repo's proven mechanism ("audio v3") is vehicle-side `obj:createSFXSource` with a raw ogg, edge-driven from GE. |
| `particleEmitter:emitExplosion(pos)` | **Not an API** | Particles are `ParticleEmitterNode` scene objects bound to a `ParticleEmitterData` (`BNGP_*`) datablock — exactly what `lua_kit.createEffect` already builds. Note the `BNGP_` (emitter) vs `BNG_` (data) trap from the car wash. |
| `ai.setMode('flee')` / `('chase')` | **Correct** | `vehicle/ai.lua:6192`; chase additionally needs `ai.setTargetObjectID(id)` (`:6210`). |
| Anti-ping-pong immunity cooldown | **Correct and essential** | Keep it. Extend it to cover resets and despawns (§4). |
| Hover the potato as a TSStatic | **Correct** | And already free: `PART_SPECS` + `posePartObjects`. One catch in §3. |
| Phase 1 in the Flowgraph editor | **Skip it here** | Flowgraph state cannot enter the deterministic evidence chain, and `lua_kit.py` already hands you the whole lifecycle the prototype would be discovering. Go straight to a behaviour chunk. |

Two repo laws that the blueprint could not have known, and that shape the
design more than anything above:

- **`dtSim` in `behavior.update` is not wall seconds** — measured ~3× fast
  (AGENTS.md). A fuse the player watches count down *must* run on
  `Engine.Platform.getSystemTimeMS()` deltas, or be calibrated by measuring
  the wall-clock result. Do not reason about it in seconds.
- **~~Vehicle-material `emissiveFactor` is inert in this pipeline~~ RETIRED
  2026-08-15 (round 17) — the observation was real, the diagnosis was wrong.**
  Every variant tried across builds 63–69 really did render dead black, but the
  cause was a FOUR-element `emissiveFactor`; a THREE-element one emits fine, and
  `emissiveMap` multiplies per texel. See the photometric ledger in the
  repo-root `AGENTS.md`. The mechanism below is STILL real light objects (§6),
  for a reason that survives: emissive self-glows but ILLUMINATES NOTHING, so a
  marker that has to throw light on its surroundings needs a light object either
  way. What is now also possible, and was not thought to be, is a genuinely
  self-lit potato skin or marker face.

---

## 2. Where the mod lives

The binding constraint is `AGENTS.md`: gameplay must not be bootstrapped by a
global `modScript.lua`. Some object must own the GE extension's load/unload
lifecycle. That gives two legitimate shells, and they should share one core.
The BeamMP Client package has one narrow exception: its nested
`scripts/ericrolph_hot_potato/modScript.lua` loads only the custom-event
transport adapter. The spawned prop still owns gameplay registration, reset,
and teardown; installing the zip normally therefore retains the original
single-player lifecycle.

```
              ┌──────────────────────────────────────────┐
              │  ericrolph_hot_potato/runtime  (GE Lua)  │
              │  generated by proplib/lua_kit.py from    │
              │  spec.LUA_BEHAVIOR + the Blender handoff │
              │                                          │
              │  · carrier state machine + fuse          │
              │  · positional sweep over getAllVehicles  │
              │  · potato pose, effects, lights          │
              │  · detonation ladder                     │
              └───────┬──────────────────────────┬───────┘
       bootstrapped by │                          │ bootstrapped by
                       │                          │
        ┌──────────────┴────────┐    ┌────────────┴──────────────┐
        │ SHELL A (recommended) │    │ SHELL B (later)           │
        │ The Potato Dispenser  │    │ Scenario JSON `extensions`│
        │ — a Giant Props prop; │    │ — fixed spawns, AI field, │
        │ vehicle bootstrap     │    │ last-car-standing scoring │
        │ registers the prop    │    │ (the car wash Gridmap     │
        │ with the runtime      │    │ pattern)                  │
        └───────────────────────┘    └───────────────────────────┘
```

**Recommendation: build Shell A first.** It is the only one that fits the
pack's existing machinery end to end — spawnable from the vehicle selector on
any map, free-roam, and it inherits `cleanupInstallation`, trigger validation,
reset handling and mission teardown for nothing. Shell B reuses the same
behaviour chunk verbatim once A is proven, exactly as the car wash keeps a
selector runtime and a Gridmap scenario against one contract.

The Dispenser also solves a real design problem: something has to *start* the
round and *own* the potato between rounds. A physical arch you drive through —
potato sitting in a cradle, klaxon, gate — is a better answer than an invisible
global rule, and it makes the mod legible the moment a player spawns it.

Names follow the pack: `MOD_ID = "ericrolph_hot_potato"`,
`ZIP_BASENAME = "hot_potato_ericrolph.zip"`.

---

## 3. The potato

A `PART_SPECS` entry — a TSStatic the framework creates, poses and deletes.

- **Collision `None`.** It must never be a physical object. (The framework's
  `createPart` already defaults to `"None"`; only parts declaring
  `collision: true` get `"Visible Mesh Final"` plus the
  `be:reloadCollision()` dance, which we explicitly do not want.)
- **Pose it onto the carrier, not the prop.** `posePartObjects` computes
  `origin + modelRotation * (pivot + offset)`. So each frame the behaviour
  sets

  ```
  offset = inverse(modelRotation) * (carrierWorld + hover - state.origin) - pivot
  ```

  and because `modelRotation` is orthonormal, that inverse is three dot
  products against the transformed unit axes — the exact trick the junk chute
  grinder already uses (`localOf`). No quaternion inverse call.
- **Hover height** from `carrier:getSpawnWorldOOBB():getHalfExtents().z`
  plus clearance. Cache it per vehicle id: the *spawn* OOBB does not change
  with deformation, so this is one call per carrier, not one per frame.
- **Spin and bob belong in the pose quaternion, never in an ambient clip.**
  `setPosRot` restarts a Collada ambient clip from frame zero (AGENTS.md), and
  `posePartObjects` calls `setPosRot` every single frame — a baked spin clip
  would be frozen on frame 0 forever. Drive the yaw from accumulated time and
  the bob from a sine on the offset's z.

Visually: a cartoon russet potato, scorch-marked, with a cartoon fuse. Author
it in the Blender generator like every other prop; the cage is trivial (it is
a non-colliding visual), but the prop as a whole still needs the standard
fixed cage, ref/back/left/up groups and three non-collinear `beamng_base`
nodes for the **Dispenser**, not for the potato part.

---

## 4. Transfer engine

**Do not use `BeamNGTrigger` zones for the transfer.** They are anchored to
the prop's transform and cannot follow a moving carrier, and the pack has
already paid for the lesson twice: `Contains` + bounding box drops a moving
vehicle the moment its bbox pokes the boundary (entries read late, exits read
early), and the car wash proved overlap events stop being delivered entirely
for a thin band at rotated yaws. The trigger objects the framework builds stay
useful for the Dispenser's own arch (round start), and nothing else.

The authoritative mechanism is a **positional sweep in `behavior.update`**,
the same shape as the centrifuge's field:

```lua
local ok, all = pcall(getAllVehicles)
-- for each: exactVehicle(id), skip isSelfProp, skip immune, measure
```

Per tick, against the carrier:

1. **Roster.** Eligible = every live non-prop vehicle. `getAllVehicles()` is
   ground truth; the car wash learned that trigger-set bookkeeping can make a
   parked car invisible for minutes.
2. **Distance.** `map.objects[id].pos` is available GE-side and is the cheap
   read; `vehicle:getPosition()` is the exact one. Both are used in this pack.
3. **Touch mode** = distance ≤ `radius(carrier) + radius(target) + eps`, where
   each radius is the horizontal half-extent of that vehicle's spawn OOBB.
   This is an inscribed-circle approximation, and it should be *stated as one*
   — it will register a pass slightly before paint touches paint on two long
   vehicles. That is better than a false negative, and it is honest.
4. **Radius mode** = a configured `trigger_radius` (2–25 m), same maths with a
   constant.
5. **Transfer** → new carrier, previous carrier gets `immune_until = now +
   cooldown` (1.5–2.5 s wall clock). One transfer per tick, maximum.

Three cases the reference blueprint does not cover, all of which will happen
within a minute of real play:

- **The carrier despawns or resets.** `behavior.onSubjectGone` fires
  (framework already wires it through `sweepZones` and `onVehicleDestroyed`).
  Rule: the potato returns to the Dispenser cradle and the fuse pauses — do
  not silently pick a new victim, and do not leave the potato orbiting a dead
  id.
- **The carrier is the only car left.** Round ends; do not detonate a winner.
- **A car joins mid-round.** It is eligible immediately but starts immune for
  one cooldown, so spawning next to the carrier is not an instant death.

---

## 5. Detonation

An honest ladder, in the order it should be built. The framework's own
`launchSubject`/`addSubjectVelocity` helpers are `applyClusterVelocityScaleAdd`
— a **uniform** velocity add over the whole node cluster. As the junk chute
grinder's spec says in as many words: by construction it cannot strain a single
beam, and any claim that a velocity servo crushes a car is false. Deformation
has to come from the vehicle side.

| Tier | Mechanism | Side | What it actually does |
| --- | --- | --- | --- |
| **A. Pop** | `launchSubject(state, veh, vec3(0,0,v))` | GE | Vertical launch. Deforms nothing directly — but the *landing* does, and this is the pack's proven, reliable showstopper (the toaster's POP). |
| **B. Shed** | `beamstate.breakAllBreakgroups()` + `beamstate.deflateTire(i)` for every wheel, via `vehicle:queueLuaCommand` | VLUA | Doors, bonnet, bumpers detach; all four tyres blow. Proven in `junk_chute_grinder`. Copy the guarded `pcall` form verbatim so a missing API is a no-op. |
| **C. Crush** | `obj:applyForceVector(cid, vec)` on nodes above the potato plane, **sustained over a window** | VLUA | The only route to real deformation. Requires a small vehicle-side ticker, not a one-shot: size the force from Δv = F·dt/m per step and integrate over ~50–150 ms. |
| **D. Burn** | `fire.explodeVehicle()` | VLUA | Fuel ignition, delayed, silently inert without flammable nodes or with fire disabled. Ship it as garnish behind a tunable; never as the effect that sells the moment. |

Recommended detonation frame: **B and C together, then A on the following
tick, then D.** Shed the panels, press the roof, launch the wreck, set it
alight.

Two safety rails carried over from round 15, both of which apply because we are
pushing nodes:

- **Phys-explosion watchdog.** `vehicle:getSpawnWorldOOBB():getHalfExtents()`
  balloons by hundreds of metres when a node explodes. If it does, stop
  feeding the solver — quarantine that vehicle and toast once.
- **Everything behind a `safety_enabled` master switch** with per-threshold
  tunables, so the whole class reverts with one flag.

---

## 6. Fuse, HUD, audio, and the "you are it" tell

- **Fuse on wall clock.** `Engine.Platform.getSystemTimeMS()` deltas, not
  accumulated `dtSim`. Modes: fixed (30 s), random range (15–45 s), shared
  pool vs. reset-per-transfer.
- **HUD.** MVP is the framework's `showMessage` (`guihooks.message` into the
  mod's own UI category) — countdown at 10/5/4/3/2/1 and transfer callouts. A
  real UI app under `ui/` is a separate, larger decision; do not bundle it into
  the first shippable version.
- **Beep.** Interval `≈ k / remaining` so tempo accelerates. Audio is
  vehicle-side `obj:createSFXSource` on a raw ogg, driven by an edge flag from
  GE — this repo has already burned two other mechanisms (`fileName`
  `SFXEmitter`, `Engine.Audio.playOnce`) proving silent or unprovable.
- **The carrier marker.** The blueprint's proximity ring wants a glow. This
  used to read "glow is exactly what this pipeline cannot do — vehicle-material
  emissive is inert"; that half is RETIRED (round 17: three-component
  `emissiveFactor` emits). The half that still stands, and that decides the
  design, is the other one: a `PointLight` sitting *at* a surface renders as a
  circular disc at any brightness, and emissive alone illuminates nothing. The proven recipe is the centrifuge's cop-light beacon:
  an amber `PointLight` plus two opposed `SpotLight`s created in
  `behavior.init`, stored in `state.effects` so `cleanupInstallation` deletes
  them, steered per tick by writing a `quatFromDir(dir, up):toTorqueQuat()`
  into the `"rotation"` field (`setPosition` + field write — never
  `setPosRot`). Beacon rate ~3.0; 9 strobed at 8.6 flashes/s against a 60 Hz
  frame rate.
- **Flame trail.** A `ParticleEmitterNode` following the carrier. Verified
  emitter inventory relevant here (exact case matters):
  `BNGP_Fire_Huge`, `BNGP_confetti`, `BNGP_utah_dust_huge`,
  `BNGP_waterfallsteam`, plus `BNGP_1`…`BNGP_83`. `BNGP_confetti` for the
  winner is free and worth it.

Note one framework interaction: `synchronizeInstallation` re-poses
`state.effects` only when the **prop** moves (guarded by a pose delta), so a
behaviour that writes an effect's transform every frame does not fight it — as
long as the Dispenser is stationary, which it is.

---

## 7. AI

`vehicle:queueLuaCommand("ai.setMode('flee')")` for everyone near the carrier,
and `ai.setMode('chase')` + `ai.setTargetObjectID(carrierId)` on the carrier's
hunters. Both confirmed in `vehicle/ai.lua`. Re-issue on transfer, and clear
modes at round end. Traffic AI will fight you for control of the same
vehicles; scope the AI feature to cars the mod spawned, or to a scenario
(Shell B), rather than to whatever traffic happens to exist.

---

## 8. Build and validation roadmap

Standard pack pipeline (`examples/giant_props/README.md`):

```bash
python examples/giant_props/build.py hot_potato textures
```

```bash
python examples/giant_props/build.py hot_potato all
```

with the Blender stage between them. Remember the pipeline law that has bitten
this pack repeatedly: **behaviour *params* ship via the Blender handoff, while
behaviour *code* ships fresh from `spec.py` at `build.py` time.** After any
tunable change, re-run the Blender stage or the constant silently keeps its old
value — verify inside the zip before testing.

Order of work:

1. `spec.py` — `MOD_ID`, `DISPLAY_NAME`, `VALUE_DOLLARS`, `ZIP_BASENAME`,
   `PALETTE`, geometry constants, tunables, `LUA_BEHAVIOR`.
2. `blender/create_hot_potato.py` — Dispenser arch + cradle + potato part,
   cage, handoff.
3. Behaviour chunk: roster → transfer → fuse → detonation ladder, in that
   order, each provable on its own.
4. **Bump the count gate**: `tests/test_giant_props_pack.py:87` asserts
   `len(MOD_KEYS) == 18`. It becomes 19.
5. Static gate: `pytest -q tests/test_giant_props_pack.py`.
6. Live gates on the sentinel-isolated profile, serially, per `AGENTS.md`.
7. Distribution build + SHA-256 lock.

**The live gate this mod needs that no existing prop's gate provides:** every
other prop is a fixed machine tested with one subject. Hot Potato is only real
with **three or more simultaneous vehicles**, so the functional gate has to
spawn a field, force a transfer, prove the cooldown blocks the immediate
bounce-back, run the fuse to zero, and assert the detonation on the right
vehicle. Budget for that harness — it is the genuinely new work here, and the
pack's existing single-subject live tests will not catch a transfer bug.

---

## 9. Open questions

- **Proximity ring.** No mechanism in this repo yet renders a world-space ring
  that follows a vehicle. `debugDrawer` is debug-only; a decal projection is
  unproven here. The beacon lights (§6) cover "who is it" adequately — treat
  the ring as a later probe, not a v1 requirement.
- **Multiplayer authority.** BeamMP now elects the client that owns the prop's
  canonical `MPVehicleGE` server ID as authority. That client alone runs the
  pickup/pass/fuse/scoring state machine and publishes complete snapshots at
  5 Hz; followers render snapshots and apply vehicle mutations only to cars
  they own. Joining is fail-closed (`pending`) until the relay assigns a role,
  so a late or missing relay cannot create two independent rounds. The same
  zip remains fully local when `MPCoreNetwork.isMPSession()` is false.
- **Shell B scoring.** Last-car-standing needs an elimination predicate.
  `map.objects[vehId].damage` is available GE-side (traffic respawns at ≥500,
  the game's own code calls >1000 notable and >5000 heavy) and is the obvious
  candidate.

---

## 10. What the live run changed (2026-08-25)

The first build shipped and the potato just bobbed under the arch. The
player's own `beamng.log` settled it in one read: `prop_registered`, then no
`zone_enter` at all across 100 seconds of driving through the gate. The
`Contains` trigger never fired once. Four things came out of the live work:

- **Pickup is a positional sweep now, not a trigger.** The trigger survives as
  telemetry and a secondary path; in the live run it fires ~30 ms *after* the
  sweep has already handed the potato over.
- **Contact range had to become directional.** The first model used one
  averaged radius per car (1.68 m for an etk800), so two of them bumper to
  bumper - centres 4.6 m apart - sat outside a 3.9 m "contact" range and a
  rear-end tap could never transfer, while a side-swipe would fire early. It
  is now the exact box support function along the separation axis: ~5.15 m
  nose-to-tail, ~2.25 m abreast. Every headless test passed before this fix
  because they all placed cars 2 m apart.
- **The fuse only burns while the simulation runs.** It is still wall-clock
  (dtSim is ~3x fast), but it accumulates a per-frame delta gated on
  `dtSim > 0` and clamps any jump over 0.5 s. Found live: under a
  paused-and-stepped session a 62 s fuse expired during 18 s of stepping.
  A player who pauses should not lose the round.
- **The tuber anchors on the body centre.** `getPosition()` is the ref node,
  which sits forward of centre on most vehicles and left the potato
  overhanging the windscreen; `getSpawnWorldOOBB():getCenter()` is the
  geometric middle.

Two things the screenshots caught that no assertion would have: the fuse
emitter (`BNGP_waterfallsteam`) threw a 30 m column that read as a separate
object hanging over the car - it is `BNGP_34` now - and the detonation is
genuinely spectacular, which is not something a green gate can tell you.

## 11. Mod controls

Every gameplay number is a live option, clamped on the way in and persisted to
`settings/ericrolph_hot_potato.json` in the user folder. There is no UI app
yet; the surface is the GE extension, which the console drives directly:

```
extensions.ericrolph__hot__potato_runtime.hotPotatoSetOption("transfer_mode", "radius")
extensions.ericrolph__hot__potato_runtime.hotPotatoSetOption("radius_m", 18)
extensions.ericrolph__hot__potato_runtime.hotPotatoGetOptions()
extensions.ericrolph__hot__potato_runtime.hotPotatoResetOptions()
```

A UI app would call the same three functions through `bngApi.engineLua`, which
is why they are exported as hooks rather than buried in the behaviour.


## 12. The v2.1 repair round (2026-08-29) — three shipped bugs and a critic

The player's recording surfaced three defects in one clip, and each turned
out to be a different LAYER failing:

- **The whole structure rendered as v1's gantry on NO MATERIAL orange.**
  Not a materials bug — a PACKAGING bug. The deterministic member stamp
  (2026-08-01 + serial days) was OLDER than the profile's v1 `.cdae` cache,
  so the engine never imported the v2 arch: v1 shapes, v1 cooked DDS,
  v2 materials.json, all at once, on a profile `deploy_local.py` called
  current. The scheme now stamps the wall-clock moment the serial bumped
  (`stamped_at`), `--deploy` purges the mod's cache dir, and the live gate
  asserts every shipped material resolves as a real Material object. Full
  law: THE STALE-CACHE TRAP in `proplib/packaging.py` and AGENTS.md
  "Packaging and caches".
- **The fuse tick outlived the mod.** `Engine.Audio.playOnce` of the game's
  REVERSE BEEP — a looping FMOD event with no stop handle — leaked one
  immortal beeper per tick (filmed: 0.45–1.1 s spacing against an authored
  1.55 s interval, still beeping after deletion). §6's own audio law said
  this path was banned; the generated runtime shipped it anyway. The tick
  is now audio mechanism v3 in the CARRIER's VM: one shipped 1.3 s
  beep+sizzle loop (`authoring/make_tick_audio.py`), pitch mapped from the
  interval options so rate and tone accelerate as one knob, moved between
  VMs on transfer, and silenced on every exit — including prop deletion,
  via a new framework hook (`behavior.cleanup`, called first thing in
  `cleanupInstallation` while the state still names what it owns).
- **One detonation bricked single player.** `b.out` was never cleared, so
  the only car could never re-arm the pad (the 2026-08-28 log: four pad
  crossings post-boom, zero pickups). Eliminations are per-round now
  (`endRound`), with exploded-node physics quarantine kept separate and
  cross-round.

A critic pass over the live screenshots then drove a polish round: the
potato's roof seat was half a car too high (`height * 2.0` — centre plus a
FULL height — instead of centre + half + belly − sink); the fuse steam was
a 3 m-particle cumulus (BNGP_34) and is now the game's own 0.8 m tailpipe
condensation (BNGP_46, chosen from `managedParticleEmitterData.json` by
measured particle size) rising from a MODELLED charred fuse cord the potato
finally has; the post-boom potato rides the blast tumbling instead of
freezing at roof height for eleven seconds; confetti erupts over the winner
with an 8 s burnout instead of fountaining at the arch until the next
round; and OPTION_RANGE now actually covers every gameplay number §11
claims it does. The beacon strobes on the audible beat (loop length over
the pitch actually sent), so the light cannot accelerate past the sound at
the pitch clamp.

The multi-vehicle live gate §8 called for exists now:
`tests/test_hot_potato_live.py` — pad pickup, a real ram transfer, the
tag-back hold, per-VM tick probes (a three-VM round trip: GE → carrier VM →
GE echo), detonation with physics agreement, the detonated car re-arming
the next round, and prop-deletion audio teardown, in ~47 s, with
normal-exposure screenshots as the visual instrument.
## 13. The v2.2 hyper-realism round (2026-08-29) — true quarter scale and four critic rounds

The player put the real monument's photographs beside the mod and asked for
the distance closed: "scaled to 1/4 size ... spare no expense geometry or
texture wise, we want this hyper-realistic," plus a realistic medallion with
inlaid copper, an actual TNT-cord fuse, honest base plates, and an in-game
way to adjust the options. A supplied reference STL was measured first and
set aside: at 73 units tall with height/half-span 1.89 and an undersized
cross-section it is LESS accurate than the parametric weighted catenary the
generator already carries, so the fidelity work went into scale and
surfacing, not geometry replacement.

**Scale.** Every arch number is now the published foot figure over four:
centroid half-span 22.801 m (299.2239 ft), apex 47.63 m, section 4.115 m to
1.295 m (54 ft to 17 ft). 181 stations; the pylon lattice widened to match
the 4.1 m legs.

**Surfacing.** Four new texture families ship: `arch_stainless` (metallic-1.0
skin whose albedo is the alloy's F0, panel courses at the prototype's 12 ft
over four, per-panel normal-map cant for the patchwork-reflection quilt,
`dynamicCubemap` real reflections), `fuse_cord` (two-hand yarn braid with
true over/under parity on a swept parallel-transport tube), `ember_coal`
(hot-dominant emissive map at 15 k nits — the photometric ledger's own curve
says 800 reads as paint in daylight — plus a warm PointLight riding the fuse
tip, because vehicle-material emissive casts on nothing), and
`honed_steel_disc` (~120 concentric grooves per tile for the medallion's
polar UVs — circles by construction, after machined_steel's isotropic
blotches sheared into spiral arms under the polar map). The medallion is a
polar-UV plate with a flared tapered rim and two FLUSH copper annulus
inlays; the copper's albedo is the game-art copper family (linear 0.50/
0.18/0.09 → sRGB ~188/117/84) after the textbook F0 measured out as rose on
the rendered frame. The plinths are two-step triangular fine-cast concrete
pads — and Blender's 3-vertex cone puts vertex 0 at +Y, not +X, which is
why the first cut shipped both plinths corner-to-camera.

**The steam lesson, measured twice.** Both early emitters eject at a 1 ms
period: a thousand puffs a second stack into an opaque column when parked
and land as separate evenly-spaced blobs per render frame at speed (the
"marching row"). BNGP_20 (BNG_smoke_white2) is the shipped answer: 50 ms
period so the puffs overlap into one translucent ribbon, peak particle
alpha 0.199, 0.7 s life.

**Mod controls in game.** The settings panel is a stock-style UI app shipped
at the zip root (`ui/modules/apps/hotPotatoTuner/`) via the new
SHIP_ROOT_ASSETS staging law in prop_builder. It builds its sliders FROM the
runtime — the new `hotPotatoGetOptionSchema` hook returns OPTION_RANGE — so
a new option appears in the panel with no app change and no drift;
`tests/test_hot_potato_ui_app.py` pins the manifest, the staging and every
hook the JavaScript calls against the shipped runtime.

**The critic series.** Four rounds, thirteen defects raised and closed with
in-engine evidence, verdict UTTERLY WOWED on round 4. The instrument grew
with the round: the live gate now takes reading-distance close-ups (fuse,
copper, plinth) alongside the action set, and the gate's pickup wait was
made race-proof after the teleport's reset event was measured landing AFTER
the position sweep had already given the potato away (round_started →
carrier_lost(subject_reset) → pad_trigger re-pickup inside ~25 ms).
Non-blocking notes on record: burnished-vs-fresh copper hue is taste, the
arch's distance mip-flattening is engine-side, and the cord shows mild
faceting only at 4x forensic zoom.

## 14. The v2.3 round: bare tuber, HUD app, party options (2026-08-29)

The brief: "remove the wick, keep the potato smoking; there's an audio
glitch where the audio persists after the explosion; move the controls to a
HUD app; think about options that'd make for a fun hot potato game and add
them."

**The wick is gone.** The swept fuse cord, its charred tip, the ember
sphere, three palette materials (`fuse_cord`, `fuse_char`, `fuse_ember`)
and the ember PointLight are all removed — the tuber ships bare, and the
BNGP_20 wisp now rises off the scorched crown itself (`SMOKE_RISE` 0.50,
just inside the 0.58 semi-z silhouette). And the idle potato now SMOKES:
with the ember lamp retired, the wisp is the "come and take it" invitation,
gated by the new `smoke_enabled` option. Serial 28 dropped from 40 to 30
members with the ten orphaned fuse DDS pruned from the harvest.

**The audio persistence, fixed at three layers.** The stop path was the
pack's only raw-ogg loop being stopped the FMOD-event way, and it was never
proven by ear. (1) `TICK_STOP` is now unconditional on `S.on` and goes
mute-stop-cut: `setVolume(id, 0)` first — the one write PROVEN audible on
this source, since the pitch rise rides the same call — then `stopSFX`,
then `cutSFX`. (2) The boom phase re-sends the stop every 0.3 s for its
first 1.2 s: the original single stop crossed the GE→vehicle boundary in
the same frame the VM was being fed break, crush and fire commands. (3)
`TICK_START` now uses the stock restart recipe (sounds.lua
`playSoundSkipAI`: cut before play), so any zombie voice is killed by the
next start instead of stacking. A fourth guard closes the sound-alike:
`detonate()` re-stamps the victim's first-seen time past the boom sequence,
so a wreck burning ON the medallion can no longer re-arm a fresh round —
and a fresh tick — the instant the round settles. The live gate now probes
the victim's VM after the boom and the logic suite counts the re-sent
stops.

**The HUD app.** ui/apps.lua (the game's own scanner) requires
domElement+directive+appName and files category-less apps under "unknown" —
which is why the tuner was hard to find in the Add App browser. The app now
declares `ui.apps.categories.utility`, and it grew a live STATUS face fed
by the new `hotPotatoGetStats` hook: who is hot ("YOU ARE HOT" throbs when
it's the player), a fuse bar driven by urgency, pass count, and the wins
ledger. The tuning drawer (schema-built, unchanged law) folds away behind a
button so the in-play footprint is small. The numeric countdown is GATED:
`hotPotatoGetStats` publishes seconds only when `show_countdown` is on —
the hidden fuse read through the accelerating tick is still the design, and
urgency ships always because the tick already broadcasts it audibly. The
live gate asks the scanner itself for the app (`getUIAppsData`).

**The party options** (all clamped in OPTION_RANGE, all live, all in the
drawer): `camp_burn_multiplier`/`camp_speed_kmh` (dawdle below the speed
and the shared fuse burns up to 5x faster — the anti-camping pressure),
`pass_knockback_mps` (the receiver of an impact pass gets shoved along the
hit axis), `blast_radius_m`/`blast_push_mps` (an area shockwave at
detonation — bystanders inside the radius get a falloff radial shove;
uniform cluster adds, so nothing can be damaged by it), `carrier_boost_mps2`
extended to −6..8 (negative = ball-and-chain handicap: drags a moving
carrier, floored so it can never reverse one), `audio_volume` (master for
the tick and the stingers), `smoke_enabled`, `show_countdown`, and
`wins_to_champion` with a wins ledger that outlives rounds: enough round
wins and the session crowns CHAMPION OF THE ARCH, doubles the confetti and
resets the board. Eight new logic tests pin each behaviour.

## 15. The v2.4 round: the return flight, the mash, and the whole show made optional (2026-08-29)

The player's second play session came back with a list: the round restarted
itself onto another car, the app never appeared in the Add App grid, the
potato clipped the carrier's roof, the footing tops looked bad — plus a
wishlist (mash everywhere, name in fireworks, hardcore mode, steam hiss,
party modes). Serial 30 answers all of it.

**The round-flow fix.** The old boom settle handed the potato to the
NEAREST car ("STILL IN PLAY!") — which read exactly like "the game restarts
itself". That path is gone: every round-over route (boom, fizzle, win,
carrier lost, reset, quarantine) now ends in `beginReturn` — the alien
return flight. From wherever the round left the tuber it climbs STRAIGHT UP
to a cruise line, drifts level to the point above its perch, and eases down
onto it, slow-yawing with a small circling nutation, smoking and hissing
the whole way. Rounds arm ONLY at the medallion, from idle. Pinned by
`test_boom_settles_into_a_return_flight_not_a_respawn` (a car parked on the
medallion mid-flight must NOT arm) and flown live.

**The Add-App mystery, measured.** The v2.3 fix (types/category) was
necessary but not the whole story: the grid the player scrolls is built by
`ui_appSelector_general` from a CACHED app list invalidated only by mod
activate/deactivate/manager-ready — a file drop or Ctrl+R never refreshes
it, and `getDetails` reads FRESH while `getTiles` reads the CACHE, which is
precisely the scanner-sees-it/grid-doesn't asymmetry we shipped into. What
a mod can fix, v2.4 fixes: `category: "Gameplay"` (a real grid group),
`isAuxiliary: false` (aux apps hide behind a default-off display option),
`interactive: "required"` (the mouse badge), an authored `app.png` tile
(without one the grid shows the generic placeholder), and the unrecognised
`preserveSpace` dropped. The live gate now asserts against BOTH layers: the
raw scanner AND `ui_appSelector_general.getAppData()` — the cache itself.
Player instructions: after installing/updating the mod, restart the game or
toggle the mod in the mod manager once; then Esc → UI Apps → edit layout →
Add App → Gameplay → "Hot Potato".

**Carry.** `carry_clearance_m` (default 0.30) rides on top of the OOBB
seat: the box is the UNDEFORMED body, so roof rails and crumpled roofs
poked through the old flush seat. The bounce (`bounce_enabled`,
`bounce_amplitude_m`) launches a parabolic hop ON each tick beat — the
potato jumps its own countdown, higher and faster as the fuse closes, and
only ever UP from the clearance baseline.

**The glow ramps like metal in a forge.** `glowHeat` drives the carrier
glow through a blackbody-style lerp — ember red → orange → yellow-white —
with brightness climbing in step (real incandescence brightens AND whitens
together; that coupling is what sells "physically hotter"). Gated by
`glow_ramp_enabled`; `beacon_enabled` is the master light switch.

**Audio v4 (critic round).** The tick loop is re-authored ("tick v2"):
thock (190 Hz body knock) + 70 Hz sub pulse (survives engine roar) + the
950 Hz tick with a droop chirp + the TOCK at t=0.65 — a falling minor
third, the two-note hot-potato song (two notes is the maximum motif that
survives the 0.6→5.0 transposition span) + dual sizzle bands (the old
2400–7800 band transposed ABOVE HEARING at panic pitch; the new 700–2000
band stays present) + ten Poisson crackle snaps. Same file, same loop
length, zero runtime change. On top: the SILENCE BEAT (escalating style
stops the tick and douses the beacon `silence_gap_seconds` before the boom
— the horror cut), the layered detonation (the proven boom one-shot at
0.85/0.55/1.6, offset), pass dings pitched by closing speed, and the
champion arpeggio. `tick_style` = escalating / steady / off — steady is
hardcore: constant pitch, constant volume, urgency pinned to 0 in the HUD
and the countdown force-hidden, because freezing pitch alone would ship a
lie through the other channels. The steam hiss is stock one-shots ONLY
(`Air_Brakes`/`Air_Dryer_Purge` pitched 1.5–1.95, jittered 2.4–5 s,
positional): the raw-file GE playOnce route stays banned as recorded
silent in this repo's evidence chain.

**The mash.** Six sculpted dollops (new additive `mashed_potato` texture
family: whipped-peak lumps, glossy butter pools, russet skin flecks) live
parked at authored homes 30 m under the plaza (`MASH_HOMES`, shared
Python↔Lua). Detonation flings them on ballistic arcs from the boom
anchor; they land at the victim's measured ground line, sit for
`mash_seconds`, melt back below grade and re-park. Posed parts with no
cage — they cannot touch physics. The generator serialises 3-lists as
vec3 literals, so authored homes index as `.x/.y/.z`, never `[1]` — the
first cut read nil pivots and parked the flight 30 m underground.

**The fireworks.** `crownChampion` (reached by wins in classic or the
points race in hoarder) writes the champion's name across the sky above
the arch: a pool of 28 point lights, a 5×7 bitmap font, one shell per
letter streaking up from the apex and blooming into the glyph (letter
colours cycle a festival palette, pitch-stepped stingers arpeggiate across
the name), then a sparkle-rain finale. The player's own crown uses
`Steam.playerName` (the same property the game's chat seeds nicknames
from); an AI champion gets its model name. Gated by `fireworks_enabled`;
lights live in `state.effects` so teardown sweeps them.

**Game modes.** `game_mode`: classic; hoarder (holding EARNS a point a
second — first to `hoard_target_points` is crowned, a boom halves the
victim's hoard, the HUD shows the points race); pinball (ANY touch passes,
knockback floored at 8 m/s — bumper cars).

**The footing fix.** `add_cone` scales the whole primitive UV for the side
walls (U by circumference, V by slant) — right for the skirt, ~64:1
anisotropic squash for the cap fans, which smeared the plinth tops into
herringbone streaks (the player's screenshot). `flatten_horizontal_uvs`
re-projects near-horizontal faces planar to XY at the same metric density;
the sides keep their mapping.

**Verification.** 43 logic tests (16 new), UI-app static gate grown to pin
the browser-manifest fields, and the live gate now also asserts: the
Add-App backend cache lists the app, the mash flies above grade, and the
boom hands over to `return` before idle. Two live runs green (cook +
final all-DDS serial 30).

**The v2.4.1 critic round — "provably invisible mash".** The critic
pixel-scanned the boom money shot and found zero cream pixels outside the
flames: the chunks rested with their CENTRE at the ground line (buried to
the waist — only their shadow smudges showed) and the fountain launched
fast enough to fly over the boom camera. Serial 31 fixes all three
causes: chunks rest at ground + 0.45×radius (`mash_radii` now ships to
the runtime; the generator serialises the 6-list as a plain table, unlike
the vec3-literal 3-lists), radii up ~35% (0.46–0.95 m — comedy beats
conservation of potato), the toss slowed to 3.5–7.5 m/s out / 5–9 m/s up
so the splatter hangs at the blast anchor, and the live gate grew a
dedicated `hp_mash` screenshot AT the anchor ~3 s post-boom so the gag is
photographed, not presumed. Re-reviewed on the pixels: "cream body, warm
butter tint, lumpy sculpted silhouettes — unmistakably mashed potato" —
VERDICT: SHIP IT, with two non-blocking engine-side notes on file (the
stock fire emitter's faceted debris triangles read as untextured shards
against the sky, and one ownerless shadow ellipse in the anchor shot —
likely the shadow of an out-of-frame chunk under the low sun).

**The v2.4.2 round — ship a whole HUD layout.** The player's follow-up
screenshot showed them scrolling the HUD LAYOUTS list — where an app can
never appear (apps live one level deeper, behind a layout's pencil-edit
-> Add App). Rather than only documenting the deeper path, the mod now
meets the player on the screen they actually found: measured against
`ui/appLayouts.lua`, `getAvailableLayouts()` re-scans the virtual
`/settings/ui_apps/originalLayouts/` on EVERY call (no cache — unlike
the Add-App grid) and mod zips overlay that VFS root, so serial 32 ships
`settings/ui_apps/originalLayouts/hot_potato.uilayout.json`: the stock
Freeroam apps (minus dragRace/forcedInduction) plus the tuner already
placed on the left edge. Type `freeroam` with filename stem
`hot_potato` keeps stock Freeroam the type DEFAULT
(`findDefaultLayoutByType` prefers stem == type), so installing the mod
never hijacks a HUD uninvited — but one tap of the layout's use button
maps freeroam -> Hot Potato via the type-layout map until the player
picks stock Freeroam back. The tuner entry carries `appVersion` because
that field drives the game's original->user layout merge: without it a
future mod update never propagates into saved user copies. Pinned
statically (strict JSON, LF-only, stock-app whitelist, staging law) and
live (the `ui_appLayouts` backend must list title "Hot Potato", type
freeroam, tuner present).

**The v2.4.3 round — the blank panel.** The player placed the app and got
an empty box. Root cause, measured in the 0.38 UI source: `bngApi` is
ONLY a window global (`ui/lib/int/vueService.js`:
`window.bngApi = window.bridge.api`) — it was never registered as an
Angular service, so the panel's DI annotation `['bngApi', ...]` threw
`Unknown provider: bngApiProvider` at instantiation, $compile died, and
the mount slot stayed empty. The working third-party precedent
(jump-button) uses the bare global. Fix: inject only Angular built-ins
($interval), reach the engine through the global. Three gates so the
class stays dead: a static pin that every DI token in the directive's
annotation array is $-prefixed; a single-root-element pin on app.html
(replace:true throws on multiple roots); and a NODE INSTANTIATION
HARNESS that evals the real app.js under a faithful shell stub (bngApi
global-only, DI resolving only Angular built-ins), instantiates the
factory and runs link() — the pre-fix code fails it with the player's
exact "Unknown provider: bngApiProvider", verified by negative test.
A live CEF render probe was attempted first (mount the real directive
via window.UIAppsServiceShim, report back per the mcp/tools/ui.lua
executeJS -> sendEngineLua round-trip) and is ON RECORD as not viable:
in BeamNGpy tech sessions the JS never reports back through ANY bridge
channel (three runs, silent on both window.beamng.sendEngineLua and
window.bngApi.engineLua), so CEF-side rendering stays a
player-verified surface for now.

**The v2.5 round — dead controls, the acoustic brief, AI drivers, and
fireworks for every winner (2026-08-30).** The player's panel screenshots
came back WORKING — and carrying the next four asks.

*The dead dropdowns and the frozen number boxes.* Two more measured shell
laws. (1) The legacy app shell ships AngularJS 1.5.8
(`ui/lib/ext/angular`), and ngModel support for `input[type=range]` only
exists from Angular 1.6: under 1.5.8 the slider fell back to the TEXT
binding, a drag wrote the value into the model as a STRING, and the
paired number input threw `ngModel:numfmt` with its view frozen —
exactly the player's toast (`fuse_base_seconds = 436`) against a box
stuck at 60. (2) NO stock legacy app uses a native `<select>` anywhere
in `ui/modules/apps`: the game's offscreen CEF never renders the
dropdown popup, which is why clicking showed nothing (and why scroll
over the focused select could still change it). Fixes: a hand-rolled
`hptSlider` directive that owns both directions (element→model as
parseFloat on 'input', model→element on $watch, engine apply debounced)
so the shared value is always a Number; and enums render as segmented
buttons in the page itself. Both fixes were PROVEN interactively against
the game's own angular.js 1.5.8 in a browser harness before shipping
(drag → box tracks + engine receives a Number; enum click → applies and
highlights), then pinned by `test_controls_obey_the_measured_1_5_8_shell_laws`
and the widened all-directives DI gate.

*The steam whistle (the acoustic brief).* The potato's own voice is now a
synthesized aerodynamic orifice whistle riding the pack's only proven
raw-ogg channel — sources in the carrier's VM, beside the tick.
`make_whistle_audio.py` bakes two assets: a seamless 2.2 s LOOP
(2150 Hz fundamental — 2150 × 2.2 s = 4730 exact cycles so the seam is
phase-clean — with a 27 Hz skin-flap flutter on both frequency and
amplitude, 2x/3x harmonics plus an inharmonic 2.7x tissue partial, a
3–7 kHz wet hiss breathing WITH the flutter, a 300–800 Hz boiling
murmur, and droplet dropouts), and a 2.8 s SPUTTER one-shot (pitch
gliding 1.0→0.8 as exit velocity falls below resonance, collapsing into
staccato chirps with growing gaps and falling pitch, a last wet breath,
a hard-zero landing). Runtime dynamics per the brief's decay curve: the
loop starts abruptly at peak on pickup, holds steady, and in escalating
tick style glides DOWN (pitch 1.0 → 0.72 across the cue window — the
pressure subsiding, the exact counter-gesture to the rising tick), then
stops for the sputter timed so its dying wheeze lands at the mouth of
the silence gap. Steady style holds pitch 1.0 and never sputters — the
hardcore contract extends to the whistle. The sputter source uses
`AudioDefault3D`, the stock NON-looping description the game's own
crash/glass one-shots use (measured in gameengine.zip
`audioProfiles.datablocks.json`), so cut+play fires it once with no
loop to leak. New options: `whistle_enabled`, `whistle_volume`. The
fizzle plays the sputter as the cooked holder's death wheeze.

*AI drivers.* "This game is meant to be multiplayer": `ai_enabled` (off
by default) turns every vehicle that is not the player's into a
hot-potato player through the stock vehicle AI — the police-pursuit
machinery, measured at its exports (`lua/vehicle/ai.lua`: M.setMode,
M.setTargetObjectID — a manually set target overrides the AI's own
player pick — M.setAggression, M.setSpeedMode/M.setSpeed). The carrier
CHASES its nearest target (the player included); everyone else FLEES
the carrier; between rounds they hold position. Roles re-resolve on a
0.8 s sweep keyed by role strings, so commands cross the GE→vehicle
boundary only on change; `ai_aggression` and `ai_speed_kmh` ride along.
The release path is total: option off, prop reset and teardown all hand
every commanded car back (`ai.setMode('disabled')`); a car that leaves
the roster parks. Gated end-to-end under lupa (chase/flee/skip-player/
release).

*Fireworks for any winner.* `celebrate` now calls `beginFireworks` for
EVERY round win, not only the crowning — the winner's name in the sky
each round, the champion still earning the long confetti burn. Pinned by
a first-win-must-not-crown lupa gate.

One framework note for the ledger: BEHAVIOR keys reach the runtime
through the BLENDER handoff (`create_hot_potato.py` copies spec.BEHAVIOR
into `behavior.tunables`; lua_kit bakes that into the generated B
table), so adding an option REQUIRES the Blender stage before
`build.py prop` — a prop build alone leaves the new keys out of B and
`tunablesPresent` refuses the whole behaviour with `tunables_missing`.
The first v2.5 build did exactly that and the whole lupa suite went
red at once; the Blender re-run fixed all 46 failures.


## v2.6 — the arena round (2026-08-30)

Player brief, in order: the whistle is "annoying now and doesn't sound
like a potato in a microwave releasing steam"; a ~100-yard arena the AI
stay inside (on/off, sizable, with a see-through halo while the game
runs); the reverse "protect the potato" game type; damage options
(no-damage arena play, degrees, transfer-collision invincibility); and
the medallion popping tires.

*The whistle re-voice.* The v2.5 voice took "high-frequency and
piercing" literally — a 2150 Hz sine stack with FM flutter, a smoke
alarm. Real slit-vent steam is NARROWBAND NOISE, not a tone. The
re-voice (authoring/make_whistle_audio.py) inverts the mix: a
falling-tilt 1.2–9 kHz hiss bed is now the primary voice, the "whistle"
is a soft noise formant near 2.6 kHz, a barely-there tonal ghost (~18 dB
under the old voice) keeps the runtime's downward glissando legible,
flutter dropped to ±8% amplitude breathing at 19 Hz, and droplet pops +
a 150–500 Hz simmer carry the wet body. Level came down twice over: the
asset peaks at −9 dBFS (was −1.5) and the drive gain fell from
0.5+0.1·u to 0.30+0.08·u. The sputter one-shot became a wet die-off of
noise puffs instead of tonal chirps.

*The arena.* `arena_enabled` (on, 91.4 m = 100 yards, `arena_radius_m`
20–500) draws a horizontal circle around the medallion that every
consumer reads through one helper family: a car outside cannot receive
the potato (transfer eligibility), the AI never conscripts an outside
car ("any AI vehicle within the game radius becomes part of the hot
potato game" — and only those), and a conscripted car that strays out
is steered straight back with `ai.setSlotTrafficTarget` — measured as
the ONE vehicle-AI export taking raw world coordinates with no navgraph
(ai.lua:5833). Its 0.5 s watchdog brakes the car if the target goes
stale, so a per-frame heartbeat (0.25 s throttle) refreshes every
returning car between the 0.8 s role sweeps; an 80%-radius hysteresis
line stops boundary flip-flop. `arena_halo_enabled` walls the circle
with translucent immediate-mode `drawTriSolid` quads (both windings, 48
segments, 7 m, the zone.lua:414-434 fence recipe) on live/boom frames
only — no scene object exists to leak.

*Protect mode.* `game_mode = "protect"` is the reverse game: held
seconds score toward `hoard_target_points` exactly like hoarder, but
the boom costs nothing (hoarder's half-your-hoard punishment stays
hoarder-only — riding the fuse to the end is protect's whole point).
The AI role table now keys on DESIRE: hot modes (classic, pinball) run
carrier-chases/mob-flees; hold modes (hoarder, protect) invert to
carrier-flees/mob-chases — which also fixed hoarder's AI, whose v2.5
carrier helpfully chased people to give its points away.

*The AI command-order bug, measured.* `ai.setMode` →
`resetMapAndRoute` (ai.lua:5780) → `resetAggression`/`resetParameters`:
the v2.5 role command sent aggression and the speed cap BEFORE setMode,
which silently wiped them. Role commands now open with setMode; a lupa
gate pins the order.

*Damage armor.* No invulnerability flag exists anywhere in stock
BeamNG Lua (searched: traffic "invulnerability" is damage-triggered
respawn). The real mechanism is the jbeam loader's own unbreakable
semantic — `beamStrength = math.huge` (stage2.lua:28) — applied live
per vehicle: `obj:setBeamStrength/setBeamDeform(cid, math.huge)` over
`v.data.beams`, restored from the authored values that survive the
override. `damage_mode`: "normal" | "tires_safe" (wheel+pressure-group
beams armored plus `beamstate.deflateTire` patched out — both halves
required: the spike-strip path calls the module field, the beam-break
path a local upvalue) | "no_damage" (everything). One idempotent
vehicle-side ARMOR_SET command carries all three; a 0.7 s GE sweep
reconciles roster vs desire. `transfer_shield_seconds` (default 3)
full-armors BOTH cars of a pass inline at the transfer. The detonation
victim always has armor stripped first, queued ahead of break/crush/
fire in the same VM. Armor releases on option change, prop reset and
teardown.

*The medallion tire-popper.* The pad cage shipped `collision_faces=
("top",)`: a 6×6 m plane floating 0.05 m above grade with NO side
faces — its rim a razor step hidden mid-disc (the visual disc is 8.4 m
and smooth). Fix: the visual plate dropped to a 12 mm flush inlay
(MEDALLION_TOP_Z 0.05 → 0.012) and the cage pad ships no collision at
all (cars roll the real plaza ground through the visual); the lattice
keeps its authored height via PAD_CAGE_TOP_Z so node ids and the
refnode frame are unchanged. The built jbeam went 68 → 60 collision
triangles, pad-referencing count now zero.

Two framework laws for the ledger:

- **Lua's 200-local ceiling is real and near.** The generated runtime's
  main chunk stood at 198 top-level locals before this round; fifteen
  new `local function`s failed to COMPILE under lupa ("too many local
  variables") — and LuaJIT shares the cap, so the game would have
  refused the chunk identically. v2.6 ships as ONE table local (`v26`)
  with a field per helper; new families must follow that shape.
- The v2.5 tunables law held: this round ran Blender FIRST and the new
  keys arrived in B on the first build.


## v2.7 — the magnet round (2026-09-01)

Player brief, in order: a magnetic force that pulls vehicles back inside
the arena when they drive out (on/off in the HUD, strength adjustable);
ideas for other containment methods; scoreboard THINKING only (no build);
fluffier mash ("not enough triangles"), with very light steam off the
chunks; and "I don't think the fireworks are working" — test until a
critic is utterly wowed.

*The arena magnet.* `obj:setPlanets{x, y, z, radius, mass}` is the
engine's own gravity well — vehicle-physics-side, per node, every physics
step (funstuff.lua's explode drives it with mass −3e13·size to REPEL;
positive mass attracts; beamstate.lua:624-663 wraps the same export with
timers). A well is a STANDING setting, so unlike the slotTraffic return
there is no watchdog to feed: the 0.5 s sweep places it when a member
strays out, refreshes its mass, lifts it at the 90% re-entry line
(hysteresis against boundary chatter), and `v26.magnetRelease` lifts
everything on toggle-off, on any exit from the live phase, and at
init/reset/teardown. Raw planet gravity fades as G·M/d² — weakest exactly
when a runaway needs it most — so the sweep recomputes `mass =
arena_magnet_g · 9.81 · d² / G` from each car's CURRENT range: a
constant-force tether at any distance. Membership rides the ARENA, not
the magnet toggle (any vehicle, player included, seen inside the ring
during a live round is drafted for that round; flipping the magnet on
mid-round still catches a car already outside; bystanders are never
touched). Options: `arena_magnet_enabled` (on), `arena_magnet_g`
(0.1–2.5, default 0.6).

*The fireworks were invisible, not broken.* The v2.4 show positioned a
pool of PointLights at glyph pixels in open sky — and a point light with
no surface near it renders NOTHING: the state machine ran perfectly while
the sky stayed empty. The rework draws the show with the debug drawer
(the halo already proved immediate-mode primitives render in-world):
every star is a coloured glow shell held near 0.85 alpha around an
OPAQUE white-hot core at 0.4x (`v26.fwStar`); the launch is a swaying
shell head with a cooling ember trail; each burst opens with a
collapsing white flash; glyph stars bloom, twinkle on per-ember phases
and SAG as they burn, with half-size midpoint stars filling every stroke
between adjacent lit pixels; the finale rains sixty-plus multi-hue
embers with segmented fading comet tails. The lights are demoted to what
they can do: glow on the arch below (first 12 pixels carry dim pool
lights). Two more live-shot laws: a FLAT GLYPH MIRRORS from the far side
(the r2 run photographed E as 3), so `fw.flip` faces the whole layout
toward the player at showtime; and letter scale had to be judged in
pixels, not intuition — FW_PX walked 1.05 (pinpricks) → 1.6 ("8% of
frame height") → 2.6 (an 18 m letter) across three live rounds.
`hotPotatoTestFireworks(name)` fires a full pass on demand — the HUD
app's "Test fireworks" button and the live gate share it (the hook parks
the request on v26; the next behaviour frame owns the state and consumes
it). `fw_stage` ships in both stats channels so cameras can time the
letters.

*The mash re-sculpt.* The v2.4 chunk count was never the problem — its
folds were 6–16 cm at game scale, a smooth blob from any real camera
distance. v2.7 goes after shape AND density: billows roughly twice as
deep (0.14–0.28), a spoon-swirl ridge climbing the flank (soft-serve),
mid-band whip peaks, the fine ripple, flatter squash, taller crown, and a
0.35 radius floor so stacked folds cannot pinch through the centre. The
sphere budget tiers by chunk: 128×96 / 112×80 / 96×64 — 101,600
triangles across the six dollops (was ~50k), the hero chunk (24.3k)
outweighing the potato itself. They render for seconds per boom; the
budget is the point.

*Steam off the chunks.* Twelve new `mash_steam_*` effects — a PAIR of
BNGP_20 wisps per chunk (the measured lightest voice in the managed set:
50 ms period, peak particle alpha 0.199, the potato crown's own wisp;
one wisp per chunk was "functionally invisible at 85 m", the critic
round). Ship inactive at the under-plaza homes; stepMash switches each
pair on when its chunk lands, wavers them across the crown on offset
phases, obeys `smoke_enabled` mid-steam, and kills them when the chunk
sinks away. The critic round also lightened the mash albedo ~27% with
the green pulled out ([0.87,0.78,0.52] "dijon-khaki / crumpled tarps" →
[0.97,0.88,0.70] butter-cream) and ringed each landing with eight
deterministic half-sunk splatter droplets, drawn immediate-mode while
the chunk sits landed.

*Containment alternatives considered* (for the ledger; the magnet + the
v2.6 AI steering shipped): a static invisible collision wall (a real
scene object to leak, and a 90 km/h AI face-plant generator); an
out-of-bounds fuse-burn penalty (invisible punishment, illegible in
play); speed-capping stray cars via `ai.setSpeed` (AI-only, and fights
the return steering); teleport-back (reads as a bug, not a rule). The
gravity well is the only mechanism that is physical, engine-native,
player-inclusive, strength-adjustable and self-cleaning.

Gates: 7 new lupa tests (tether mass law, dial + mid-round toggle, well
release on boom, stars against the sky, dark when disabled, steam
lifecycle, effect census 18); the live gate fires the test hook and
photographs a burst and the finale over the arch. The player's mandate
("pair with a subagent critic that must be utterly wowed") ran as two
adversarial review rounds over real live screenshots: round 1 returned
NOT WOWED twice with seven ranked fixes (all applied — letter scale,
star anatomy, stroke fill, flash taming, finale depth, mash albedo,
steam doubling, splatter); round 2 returned WOWED on both fireworks and
mash, with a do-not-regress list pinning exactly the combination that
crossed the line.

## v2.7.1 — the live-play fix round (2026-09-01)

One playtest, four reports, all fixed in one round: "it doesn't seem as
if the magnetic system is working", "AI vehicles seem to crash into the
arch often", "I didn't see the confetti or fireworks after not having
the potato", and "let's tone down the steam coming from the mashed
potato chunks".

*The magnet was real and imperceptible.* The v2.7 well passed every
gate because the gates pinned the command law, not the felt result: a
FLAT 0.6 g pull loses to tire grip, which holds a parked car against
~0.9 g of sideways drag (and BeamNG's own directionalGravity flowgraph
node uses our identical mass = a*r^2/G law — the math was never the
problem). The well now hangs 0.6x the car's horizontal range above the
pad (~31 degrees of elevation): sin(31)*1.2 g of lift unloads the tires
while cos(31)*1.2 g drags the car home — the tractor-beam feel — at a
new 1.2 g default (dial range now 0.1–3.0). The sweep tightened to
0.25 s so the constant-gee law tracks a fast car, and the grip is drawn:
while a well holds a car, a marching line of amber beads arcs from the
car back to the ring (immediate-mode with the halo, drawn even when the
halo wall is toggled off — an invisible force that moves your car must
always show its hand).

*The arch was in everyone's flight path.* Every steering mode this mod
uses drives a straight line — chase/flee beeline at their target, and
the containment return aims dead at pad_center, which from beyond either
arch foot runs exactly THROUGH that foot (the playtest's crumpled police
car). The engine's avoidCars cannot save it: it models obstacles as
car-sized boxes and the arch is one giant OBB centred midair between the
legs. The fix is a dodge reflex (v26.stepDodge, 4x a second): ray each
commanded car's velocity ahead (max(14 m, 2.2 s)), and when the line
passes within 6.5 m of a foot (B.arch_feet, a new authored key), send a
one-shot slotTrafficTarget abeam the foot on the side the car already
favors. The return heartbeat holds off while a car dodges; when the ray
clears, b.aiApplied[id] is wiped so the next role sweep re-arms the game
role the slot-traffic override ate.

*The boom celebrated nobody.* celebrate() — confetti, fireworks, the
champion ledger — was only reachable via last-car-standing and the
crowning, so an ordinary classic boom with survivors ended with "The
potato returns to the arch..." and a shrug, and the ledger never accrued
in normal play. Classic hot potato has a natural round winner: the LAST
PASSER, who shed the potato onto the victim just in time. giveTo now
records b.lastPasser; the boom settle crowns them ("PASSED IT JUST IN
TIME!") if they survived, wins count toward the crowning, and a
no-transfer round still has no winner. Hold modes (hoarder/protect) keep
their own win condition — there the boom is the carrier's tragedy, not
the passer's triumph.

*Steam, toned down.* The critic round had doubled the chunk wisps for an
85 m money shot; at play distance the player called it too much. One
BNGP_20 wisp per chunk is the shipped voice (the six `mash_steam_b*`
emitters are deleted, effect census 18 → 12). The player's word outranks
the critic's do-not-regress list — the critic optimises a screenshot,
the player optimises the game.

Gates: 65 lupa tests (3 new: the dodge side-step and role re-arm, the
dodge win's fireworks, hold modes refusing the crown; the magnet law
tests re-pinned to the hoisted well). The live gate grew the two proofs
lupa cannot give: the ENGINE drag — AI steering off, the passer
teleported 120 m out with the parking brake ON, and the well alone must
haul the braked hulk measurably home — and the natural show, fw_stage
already lit at the boom settle with NO test button involved. Build
serial 41.

## v2.8 — the arena hooks (2026-09-01)

The Gateway Skillet arena design (v3, critic round 3: WOWED) asks the
runtime for exactly two things, both priced in its §6.4: a way to tell
the dodge reflex about the pillars, towers and jambs a scenario builds
around the arch, and a fix for a bug the design found in the runtime's
own law. No geometry, no new options, no new B keys — the Blender stage
was not run; this is a `prop` + `dist` re-cut of runtime.lua alone.

*The obstacle census.* `hotPotatoRegisterObstacles(list)` is a GE hook
beside hotPotatoSetOption: a dense array of `{x, y, r}` — world metres,
posts are 2-D (any z is ignored), r the keep-out radius in [0.5, 30],
at most 64. A call REPLACES the whole set; only `nil` or an empty table
clears it. Everything else is refused WHOLE — false, one warning, no
throw, prior set untouched: a non-table, an entry that is not a table,
a non-finite or non-number x/y/r (the string "6.5" is refused), r out
of range, a 65th entry, and any table that is not a dense 1-based array.
That last clause is the critic round's HIGH finding: `ipairs` walks a
lone `{x, y, r}` post passed without its wrapping braces, a decoded list
with a `null` hole, or a keyed table as "no entries", and the first cut
accepted that as a CLEAR with a true return and no warning — the exact
mistake a scenario author is most likely to make, answered by wiping
the census while reporting success. The fix counts `pairs` keys against
`ipairs` visits and refuses on mismatch. The cap likewise went from
truncate-with-true to refuse: a scenario that registers 70 posts and
asserts true must not believe all 70 are protected. A half-valid list
must never leave the AI dodging phantoms, and a half-read one must
never leave it dodging nothing. `hotPotatoGetObstacles()` returns `{count, entries}`
as a copy. The set parks on `v26` exactly like the fireworks request
(hooks have no prop handle): it survives rounds and prop resets, and
`behavior.cleanup` clears it so a dead scenario's posts never haunt the
next session. In the sweep, `v26.dodgePosts` reduces the arch feet
(prop-local, converted, keep-out 6.5) and the registered set to one
list of world posts, and the ray now keeps the NEAREST threatening post
along the heading instead of the first one found. That is a fix to the
shipped v2.7.1 dodge, not only an arena accommodation, and the first
cut of this entry claimed otherwise ("with two feet that never
mattered") until the critic's probe proved it: with BOTH feet on the
ray — a car westbound along the span from beyond the east foot at
25 m/s, which is exactly a containment return toward pad_center — the
first-found order picked the WEST foot 53 m out and aimed the car at
(−30.8, −9.5), a line straight through the east foot 7 m ahead.
Nearest-along aims it abeam the east foot at (14.8, −9.5). The shipped
gate (west foot, eastbound) could not see it; the geometry is now a
lupa case of its own. Each post's own r sets its side-step (r + 3
abeam, along + 8 ahead), so the 8 m handle corners get a wider berth
than a 6.5 m pillar.

*The scoring gate.* The design's F25, verified here: in hoarder and
protect, `b.score[b.carrier] += b.lastDelta` and the crown check ran
unconditionally on position, while the v2.6 arena law ("a car outside
the circle is not part of the game") was enforced on the RECEIVING side
only. An out-of-ring carrier therefore scored a point a second
uncontested — nobody outside can reach it, nobody inside may take it —
and in protect, where the boom costs nothing, riding spout-dive cycles
approached a free win. Accrual and the crown now sit behind the transfer
sweep's own `v26.insideArena(state, position)`, on their own per-frame
carrier position read (the crowned branch's fetch runs only on the
crowning frame — the critic's erratum #4). `b.score = b.score or {}`
stays outside the gate so the scoreboard's shape is unchanged; with the
arena off `insideArena` is always true and every in-ring frame scores
exactly as before. Classic and pinball have no hoard and are untouched.

Two laws held, one measured:

- **Zero new top-level locals.** Every helper (`registerObstacles`,
  `obstacleReport`, `dodgePosts`, `finiteNumber`, the cap and range
  constants, the set itself) is a `v26` field; the two hooks are
  `behavior.hooks` fields. The 200-local ceiling was not approached.
- **The re-cut law, proven member by member.** sha256 of every file
  under `mod/` and every member of the shipped zip was snapshotted
  before `prop`; after `prop` + `dist`, 45/45 members and exactly ONE
  moved — `lua/ge/extensions/ericrolph_hot_potato/runtime.lua`
  (c2addf9d… → 7fc49006…, serial 42 → 43). The critic round re-cut
  under the same law, snapshot to proof: again 45/45, again only
  runtime.lua (7fc49006… → cb43403e…), serial 43 → 44, stamped
  2026-09-01T15:54:33. The certified textures did not move either time.
- **The hook contract is the scenario worker's interface**, coded
  against in parallel: returns true on accept and false on refusal,
  never throws, and `hotPotatoGetObstacles` exists so the live gate and
  the scenario's own lupa suite can assert what the runtime holds.

*The critic round.* One adversarial pass (NOT WOWED, five ranked fixes,
all closed): the non-dense-array hole and the truncating cap above; the
along-span two-feet divergence, restated honestly above and pinned; and
a harness finding that outranks this round — the lupa suite's `tick()`
crash guard had been DEAD since it was written. It looks for
`behavior_update_failed` in the logged event, but the stub `jsonEncode`
was `tostring`, so every record arrived as `table: 0x…` and a throwing
behaviour frame passed every gate in the file silently (the critic
proved it by making the carrier's getPosition throw for ten frames: ten
"E" events, zero assertions). The stub now renders the record as sorted
`key=value` text and the guard is live; re-running the whole suite under
it caught nothing that was not already green — but from here on a
per-frame throw fails the gate that saw it, which is what the guard was
for. The fifth fix is a note, not a change: on a real getPosition
failure `carrierPose` throws before the scoring gate's pcall runs and
the framework aborts the frame, so "no accrual, no crash" holds via the
framework and the gate's pcall is belt to that brace.

*Ask #3 — the subject filter (round 3, from the scenario's live smoke).*
The arena spawns 12 cardboard boxes and 4 barrels as breakable scenery,
and the runtime reported `field = 22`: every non-dispenser vehicle was a
subject, so a box could receive the potato, be chased by the AI and be
detonated. A shipped-gameplay bug the arena merely made visible — any
free-roam session with a prop on the map had it. The mechanism is the
stock game's own: every vehicle model carries `Type` from its info.json
(`cardboard_box` and `barrels` ship `"Prop"`; etk800 `"Car"`, pickup
`"Truck"` — read from the vehicle zips; the full stock census is Prop
67, Car 28, Trailer 13, Truck 10, Heavy Machinery 2, Traffic 1, Debug
1). The runtime reads the model name with `vehicle:getJBeamFilename()`
— the GE vehicle object's method, the same name traffic reads as
`obj.jbeam` — and asks `core_vehicles.getModel(name).model.Type`.
Traffic refuses to drive
anything whose lowercased type is not in `{car, truck, automation,
traffic, proptraffic, player}` (`gameplay/traffic/vehicle.lua:29-34`,
"Ignoring traffic vehicle due to invalid vehicle type"), and the traffic
editor tests `.model.Type == "Prop"` outright
(`editor/trafficManager.lua:1948`). `getModel` returns `{}` for a key it
does not know (`core/vehicles.lua:759-764`) and stamps `Type =
"Unknown"` when the info file has none (`:843-844`). The runtime's
`v26.isPropVehicle` excludes ONLY `v26.SCENERY_TYPES` — `Prop` and
`Trailer`, case-insensitive — and fails OPEN everywhere else — no
`core_vehicles`, no model, no Type, "Unknown", "Heavy Machinery", a
throwing lookup: eligible. That is a deliberate asymmetry against
traffic's allow-list: a real car must never be failed closed, and a box
slipping through on a bad frame is the lesser evil. Trailers (critic
round 3, optional, taken): a hitched trailer sits permanently inside its
tow car's pass range and can neither drive nor be conscripted, so it
goes with the boxes; the fail-open posture is unchanged. The on-foot
player (critic round 3): stock `unicycle` ships `Type = "Prop"`, and the
game's own traffic code special-cases it to `'player'`
(`traffic/vehicle.lua:31`) for exactly this reason — mirrored, so a
walking player stays in the game exactly as before v2.8.

*The cache, and the claim the critic struck.* The first cut cached one
verdict per vehicle id, "invalidated in `onSubjectGone`, T3D ids being
session-unique". Both halves were wrong at the file level. The engine
REUSES the vehicle object on replace (`core/vehicles.lua:1716-1765`:
`vehsToReuse`, `replaceOtherVehicle` on the same object, then the
`onVehicleReplaced` hook, which lua_kit never subscribes), so the id
outlives the model; and `onSubjectGone` fires only `if wasTracked`
(lua_kit:826-840) — a box that never entered a trigger set is never
invalidated. Reproduced under the stubs: a box replaced in place by an
etk800 stayed `props_excluded 1` and never received; a destroyed box
respawned as a car with the same id stayed a prop. In play: a player who
Tabs into a box and picks a car from the selector would have been
invisible to the game for the rest of the session — the one failure the
filter was built never to produce, on the extents cache's borrowed
assumption ("stale extents misplace the potato by a roof height; a
stale verdict deletes a player"). The verdict is now keyed by id AND
model — `{model, prop}` per id — and the model is re-read with
`getJBeamFilename()` every roster pass (one C call per vehicle, the same
class as the `getId()` the loop already pays); `getModel` runs once per
(id, model); the entry still drops in `onSubjectGone` and the table is
wiped on init/reset. Both replace directions and the destroy-then-reuse
case are lupa gates. `roster(state)` refuses props, so every consumer
that reads the roster — transfer eligibility, AI conscription, the
containment return, the magnet, the dodge (it steers only commanded
cars), the armor sweep, the field count, last-car-standing and
`min_players` — sees cars only; `roster(state, true)` asks for the whole
field, and only the detonation shockwave does, because the arena scatters
its pantry stacks with the boom on purpose (geyser pops are scenario-side
and never touched the roster). `props_excluded` ships in both stats
channels so the live gate can assert `field == real cars`. The `local
v26 = {}` declaration moved above `roster()` — it is needed there as an
upvalue — with the 200-local count unchanged at 185.

*The carrier that became scenery (critic round 4).* The filter opened a
hole the field count could fall into: a carrying player who opens the
selector and picks a box keeps the same object and id, `roster()` now
drops it, the field reads 1 against a peak of 2 — and the
last-car-standing check crowned the BOX: confetti and fireworks on a
cardboard box and a `round_won` for its id in the persistent champion
ledger, while the real car still playing lost a round it could not
contest. Self-inflicted, so MEDIUM, but the ledger is state that
outlives the session and the result was exactly backwards. Folded into
the existing carrier-lost path at the top of the live phase:
`if not carrier or v26.isPropVehicle(state, b.carrier, carrier)` → the
potato flies home, "Potato returning to the arch." with reason
`carrier_became_scenery`, nobody wins, the ledger is untouched.
`isPropVehicle` is cache-hot there (the roster pass just re-read the
model), so it costs one table lookup a frame. The mirror holds: a
carrier replaced in place by another CAR model keeps the potato — what a
player changing cars mid-round expects. The critic also measured the
per-pass cost claim and found the filter a net WIN — 0.174 ms/frame
against 0.193 for the pre-filter runtime with 23 vehicles, because every
downstream sweep now walks 7 entries instead of 23. And the trailer
census above was 12 in two places because the counting script compared
a lowercased zip member path against the mixed-case stem
`containerTrailer`; the case-tolerant count is 13, as the critic said.

Gates: 80 lupa tests (15 new: sixteen registered posts join the sweep —
side-step, role re-arm, nearest-along against a decoy, the arch feet
retained; the along-span two-feet case at the probe's exact geometry;
validation — eleven refusals including the three non-dense tables and
the 65th entry — the cap at exactly 64, z ignored, replace, clear, copy,
reset-survives, teardown-clears; hoarder and protect freeze outside a
20 m ring for 12 held seconds with no crown and resume inside; arena off
scores anywhere; classic outside the ring keeps burning its fuse with no
scoreboard; the subject filter — a box in pass range never receives, a
barrel inside the ring is never conscripted, herded or tethered while
the car beside it is, `field` and `props_excluded` read 2 and 2, and the
carrier wins last-car-standing over two remaining props; "Unknown" type
and a missing `core_vehicles` both fail open; the shockwave still shoves
a box; a box replaced in place by a car receives within the join window
and a car replaced by a box is scenery from the next pass, and a
destroyed box whose id returns as a car receives; the walking player
receives; a trailer never does; a carrier that becomes a box mid-round
sends the potato home with no LAST CAR STANDING, no `round_won`, no
fireworks and an empty wins board, while a carrier that becomes a pickup
stays the carrier). The lupa stubs gained a
`core_vehicles.getModel` mirror with `unicycle = "Prop"` and a
`"Trailer"` staged. The
BeamMP sync (4), HUD app (8) and pack (467) suites are unchanged and
green under the armed guard. The live proof — 3 minutes of chase/flee
with zero pillar collisions, the hold-mode spout-spam uptime, and
`field == 6` with sixteen props on the map — belongs to the arena
scenario's G3/G5 gates; this round is lupa-only by design. Re-cut a
third time under the same law: 45/45, only runtime.lua (cb43403e… →
24db22d7…), serial 44 → 45, stamped 2026-09-01T16:11:11; and a fourth
for the cache fix: 45/45, only runtime.lua (24db22d7… → 4a136fd9…),
serial 45 → 46, stamped 2026-09-01T16:23:13; and a fifth for the
scenery-carrier fold: 45/45, only runtime.lua (4a136fd9… → 2e24400d…),
serial 46 → 47, stamped 2026-09-01T18:52:10. Build serial 47.

## v2.9 — the crest-ram magnet round (2026-09-02)

The Gateway Skillet's G2 gate rammed the pan wall at three speeds and
found two shipped magnet bugs that no gate this mod ever had could see.
60 km/h passed every clause — over the crest, onto the glacis, well
engages, home in 2.25 s. 85 km/h flew to **r 190.5 m and was never
hauled back at all** in 75 s. 110 km/h **rolled during the haul** (min
up-vector z 0.20 — past 78 degrees). The v2.7.1 gate that certified this
magnet dragged a BRAKED hulk from 120 m with the parking brake on: a
pure radial pull on a car with no rotation and no tangential speed. It
was the right proof of the force law and no proof at all of the two
things a fast tangential exit does differently. That is the asymmetry
law again, and this time the untested sixth case was the one the arena's
whole anti-perimeter-looping claim rests on.

*Diagnosis first.* The well law itself is innocent: a lupa probe of the
shipped serial 47 at 95 / 110 / 150 / 190.5 / 250 / 400 m emits a
well-formed command at every range, each carrying exactly the dialled
1.2 g at the true 3D reach (0.617 g lift / 1.029 g haul). There is no
range cap, no mass clamp, no format break — `%.5g` of 8.7e15 is a fine
Lua number. What is not innocent is WHEN the magnet is armed, and two
paths in `v26.stepMagnet` produce "no well at all" at any range:

1. **Membership was sampled only by the 0.25 s sweep.** A car is drafted
   only when a sweep catches it with `distance <= arena_radius_m` during
   the LIVE phase. At 85 km/h a car covers 5.9 m between sweeps; a
   crossing no sweep samples from the inside leaves the car un-drafted,
   and there is no later path that can draft a car already outside — by
   design, so bystanders are never grabbed. Un-drafted is un-haulable,
   for the rest of the round.
2. **The round end abandoned everyone still outside.** The frame the
   phase left "live", every well was dropped AND `b.arenaMembers` wiped.
   A car outside at that moment is stranded: the next round drafts only
   from inside the ring. Reproduced in lupa — well placed, round ends,
   one clear, car sits at 190.5 m forever.

*The fixes.* Membership is now sampled EVERY FRAME (a position read per
roster car, the same cost class as the transfer sweep that already runs
there); only the well SEND stays on the 0.25 s throttle, so the command
budget is unchanged. A crossing now has to beat one frame (~0.4 m at
85 km/h) instead of one sweep. And the haul FINISHES across the round
end: a member still outside keeps its well until it is home, bounded by
`MAGNET_GRACE_SECONDS` (20 s). The v2.7 law that a well must never
outlive the mod is intact — arena off, magnet off, prop init, reset and
teardown all release instantly, and the grace expiry releases too.

*The roll.* A uniform gravity-like force cannot torque a car; what rolls
it is the missing tire load. The fixed 31-degree hoist removes
`sin(31) x dial` of the car's weight — 0.617 g at the 1.2 g default, so
the tires carry 38 %. A car that crosses the crest at 110 km/h arrives
already rotating, and with almost no load there is nothing to damp it.
So the hoist is now SPEED-AWARE: full v2.7.1 0.6 below 10 m/s (the
braked-hulk tractor beam, measured and kept byte-identical), tapering to
25 % of it by 28 m/s. Measured on the new cut at r 190.5 m: a 110 km/h
car gets a well 28.6 m up instead of 114.3, 0.178 g of lift instead of
0.617 — it keeps **0.82 g of weight** — and the haul actually goes UP to
1.187 g because more of the pull is horizontal. The grab also ramps in
over 0.6 s instead of arriving as a 1.2 g step on a car doing 30 m/s.
Finally a cap: whatever the host dials, lift may never exceed
`MAGNET_LIFT_CAP_G` (0.65 g) — the design's own ceiling argument (arena
design v3 section 4.4: lift >= 1 g takes the wheels off the ground)
turned into a guard. It bites by LOWERING the well, never by weakening
the haul, and it is slack at every dial below 1.27 g, so nothing about
the shipped feel changes.

Fail-open, as everywhere in this mod: every lever here only ever REDUCES
force or delays it. A car that cannot be hauled is never made
undriveable, and a bystander never seen inside the ring is still never
touched.

Gates: 86 lupa tests (6 new, 2 rewritten): a far member at 110 / 190.5 /
250 m carries the dialled gees with > 1 g of inward haul; the grab ramps
from under half strength to full; a fast car's lift drops below 0.3 g
while its haul grows; the cap holds lift at 0.65 g even at the 3.0 g
dial while the haul keeps 2.8 g+; one frame inside the ring is enough to
be drafted; the haul finishes past the round end, releases the moment
the car is home, and is released again when the grace expires. The
`_magnet_mass` helper now takes the speed-aware hoist, and the old
"never outlives the round" gate is rewritten as "finishes its haul, then
never outlives it" — the contract genuinely changed. Sync (4), HUD app
(8) and pack (467) unchanged: **565 passed**. Re-cut under the law:
45/45, only runtime.lua (2e24400d… → 115cc621…), serial 47 → 48,
stamped 2026-09-02T08:20:02. The proof this round is lupa and arithmetic
only — the integration worker owns the simulator and re-runs the crest
rams as G8 against serial 48. Build serial 48.

## v2.10 — the dodge that never committed (2026-09-02)

The arena's G8.1 confirmed v2.9 live at all three crest-ram speeds (85
km/h: r 190.5 and never hauled, now r 114.6 home in 6.9 s; 110 km/h:
up-vector 0.20, now 0.858), and it answered the open engine question the
v2.9 entry left on the record: hauled cars RISE while tethered (60 km/h
1.25 → 2.12 m, 110 km/h 3.83 → 13.31 m) with the ground falling away and
the bead tether photographed. **`obj:setPlanets` ADDS a lifting
attractor; it does not replace world gravity.** The v2.7.1 reading was
right and the flowgraph node's wording was the red herring. Two defects
survived that round, both measured on serial 48.

*The dodge was not preventing strikes.* 25 obstacle contacts in G7.3 with
all 42 posts registered and confirmed through `hotPotatoGetObstacles`,
plus repeat strikes in G3 at 10-17 m/s (one at 12.9 m/s doing 7,456
damage). Registration was never in question. Three things were wrong with
the avoidance, and the first is the one that produced *repeat* strikes:

1. **It never committed.** The v2.7.1 sweep recomputed the side-step from
   the car's CURRENT heading every 0.25 s and released the instant the ray
   stopped clipping the post. So the car aimed off, its heading cleared,
   the dodge released, the 0.8 s role sweep re-aimed the beeline at the
   carrier — through the post — and 0.25 s later the dodge fired again: a
   4 Hz limit cycle that oscillates around an obstacle while closing on
   it. The aim point is now LATCHED in world space at the moment of
   commitment and held until the car is genuinely past the post (behind
   the heading it committed on, or opening the range on it).
2. **The avoidance angle shrank with range.** The old target was the car's
   own heading plus a FIXED `keep-out + 3` m of lateral offset, placed 8 m
   beyond the post. Detected at 37 m (17 m/s x 2.2 s of lookahead) that is
   a 12-degree deviation — nowhere near enough to leave a 6.5 m corridor,
   and the car re-entered it the moment the dodge let go. The aim point is
   now computed FROM THE POST — abeam it, at `keep-out + 4` m — so the
   commanded deviation is whatever passing the obstacle actually demands,
   at any range.
3. **The corridor ignored speed.** A car at 17 m/s needs more room than
   one at 5 m/s. The trigger corridor now grows 0.35 m per m/s (capped at
   +6 m), so a fast car starts its manoeuvre earlier and wider.

Plus the stomp: the role sweep re-sent chase/flee mid-dodge whenever the
role STRING changed (a new carrier, a boundary crossing), overriding the
slot-traffic target with a beeline. `stepAI` now records a dodging car's
role without sending it; the dodge release wipes `b.aiApplied[id]` and
the next sweep re-sends it. And a side-step whose aim point lands inside
ANOTHER registered post is refused in favour of the other side — a long
wall registered as a string of beads is exactly that case.

**A wall is still not a post, and that is a DESIGN ask, not a runtime
one.** Point-plus-radius keep-outs cannot express a 44.5 m ramp flank.
Beads spaced under their own diameter do cover the face, and the
aim-point check above stops the car steering from one bead into its
neighbour — but the correct escape from a long face is around its END,
which no amount of point-radius reasoning can derive. A segment/wall
primitive (`{x1, y1, x2, y2, r}`) in `hotPotatoRegisterObstacles` is the
real answer, and it is routed as a design change rather than built
silently here.

*Sustained orbit rolled cars, and the roll is why they never came back.*
4 of 6 G3 excursions never re-entered, up-vector z 0.03-0.32, at BOTH the
1.2 g default and the 2.0 g escalation. The v2.9 lift cap did not cover
it because it is a different mechanism: the well is a body force through
the centre of mass, resisted by the tires at the ground, so whenever the
tires can HOLD that force instead of sliding, the pair is a rollover
couple — pull x CG height against weight x half-track. A ballistic crest
exit never rolls because the car is airborne or sliding, which is exactly
why G8.1 came home at 0.81-0.86. A powered, steered orbit is the opposite
case: the driver is holding grip and cornering, and the well's inward
pull spends the same lateral budget until the car tips. So the cap is on
the LATERAL share of the pull — the component across the car's own
travel. A pull aligned with or against travel is a shove, not a tip, so
the braked hulk and the crest ram are untouched by construction. The
budget is the static rollover threshold (half-track / CG height, taken
conservatively at 1.2) scaled by the weight left after the well's lift,
and the well may take only 60 % of it — the driver's own cornering has to
live there too. The limit is SOLVED rather than scaled: wanting
`g·cos·lateral <= R·M·(1 - g·sin)` gives `g <= R·M / (cos·lateral +
R·M·sin)`, which is monotone. Scaling against the uncapped lift was the
first cut and it measured a HIGHER dial pulling a tangential car LESS
than a lower one; the solve removes that. Measured at r 110 m, 25 m/s:
radial keeps 1.171 g of haul at 1.2 g and 1.952 g at 2.0 g, while
tangential converges to 0.620 g at BOTH dials — exactly the budget, with
0.86 g of weight still on the tires.

Consequence worth stating: the design's §4.4 escalation lever no longer
buys extra TANGENTIAL pull, because the tip budget is a property of the
car, not the dial. What the lever still buys is radial authority. The
anti-orbit argument is now "the well cannot roll you, and it out-pulls
you radially", not "crank it until the wheels leave the ground" — that
regime is forbidden by the v2.9 lift cap anyway.

Fail-open throughout, as everywhere in this mod: every lever added here
only reduces or delays force, or refuses a bad aim point in favour of a
better one. No car is ever made undriveable, and a bystander never seen
inside the ring is still never touched.

Gates: 92 lupa tests (6 new, 3 rewritten). New: the dodge holds its
latched aim after the heading clears and refuses the role stomp; the aim
point clears a post by >= 10 m at 37 m of range; the corridor widens with
speed (a 9 m miss is fine at 5 m/s, dodged at 17 m/s); a bead wall never
gets an aim point inside a neighbouring bead; a tangential orbit is
capped inside the tip budget while still being hauled; a slow haul keeps
the full dial. Rewritten: the two dodge gates that asserted the OLD
release rule ("heading cleared") now assert the new one ("car is past the
post"), and the decoy expectation moves to the aim-from-the-post number.
Sync (4), HUD app (8), pack (467): **571 passed**.

What lupa CANNOT prove here, and what G9 must: whether the committed
manoeuvre actually clears the obstacle when a real AI follows the
slot-traffic target with real steering dynamics, and whether the capped
tangential pull still completes a re-entry against a driver who is
fighting it. Both are car-dynamics questions; the runtime side is pinned
at the command level only.

Re-cut under the law: 45/45, only runtime.lua (115cc621… → 4a027f2a…),
serial 48 → 50, stamped 2026-09-02T09:10:34. Serial 49 was cut and then
superseded within the round by the exact tip-limit solve above — a real
content change, so it took a real serial rather than a quiet overwrite.
Build serial 50.

## v2.11 — the fall line (2026-09-02)

G9 settled two things about v2.10 and opened one. **The dodge is fixed:
25 contact events fell to 1** across 180 s / 1,800 samples / 4 transfers,
with zero pillar, zero tower and zero ramp-flank contacts; minimum
clearances 0.61 m (grinder_se), 1.90 m (grinder_sw) and >= 4.65 m
everywhere else. The one survivor was a jamb at 9.3 m/s, 181 damage,
0.03 m closest approach. **That result also withdrew this mod's own
design ask**: the latch cleared the 44.5 m ramp flank with no segment
primitive, so point-plus-radius stays, and the honest caveat goes on the
record — the surviving contact is a jamb, the other long face
approximated by a 4-point chain, so if a segment primitive is ever
revisited it is the JAMB chain that argues for it, not the flank.

**And the flat tip limit is proven correct**: an orbit at 29.9 m/s held
up-vector 0.88 at both dials and never rolled. What remained is a
different defect wearing the same symptom. 9 of 10 rolls happened on the
30 % GLACIS CROSS-SLOPE (r 99-111, ground z 101.0 falling to 100.0) at
**6.3-20.7 m/s** — not orbit speed — and G9.3's ram regression showed the
same signature moving between speeds across boots (60 pass / 85 pass /
110 fail, then 60 pass / 85 fail / 110 pass). Stochastic, not
speed-specific: low-speed sideways drag across a fall line is a trip
ramp, and every run still completed its haul in 6.85-6.9 s.

*Why the flat solve is too generous there.* It balances the well's
lateral pull against weight x half-track over CG height — the FLAT
couple. On a slope two terms change at once: the normal load holding the
car down is only cos(theta) of its weight, and gravity's own in-plane
component sin(theta) is ALREADY spending the tipping budget before the
well adds anything. So the allowance becomes
`RATIO x MARGIN x cos(theta) - sin(theta)`, which at a 30 % grade is
0.403 against 0.720 on the apron — and at grade 0 it reduces to the flat
expression exactly, so the apron cannot move. The speed gate needed the
same treatment: no orbit is sustainable below 8 m/s, but a trip needs
about 6, so on a slope the cap binds from 3 m/s.

*The hoist was backwards on a slope.* Lift is precisely what strips the
load that resists a trip, so the hoist now fades out as the grade rises
and is gone by 30 %: on a cross-slope the well PRESSES instead of
lifting. Measured across the fall line at 25 m/s, 1.2 g dial: haul
0.620 g / lift 0.139 g on the flat, 0.522 / 0.059 at 15 %, and 0.402 /
0.000 at 30 %. The car is still hauled at every grade — the slope tames
the pull, it never stops it, and a floor keeps a gentle pull even on
ground too steep to hold any lateral drag at all.

*Reading the ground.* Three `castRayStatic` probes 2.5 m around the car,
the plane through the hits giving the surface normal. The export returns
a DISTANCE, not a normal, which is why it takes three — the same idiom
Cannon Car Wash has shipped since 2026-08-01. Prefab statics (what an
arena is) get their collision at level load and ARE ray-visible;
runtime-spawned TSStatics never are, and neither are vehicles, so this
reads terrain and map geometry only — exactly what a trip ramp is made
of. It runs ONLY for cars the magnet is actually hauling (0-2 of them),
cached half a second: a handful of rays a second, and a gate prices it.
Every failure path — no export, a probe that misses, a car in the air —
falls open to FLAT, which is the shipped behaviour, never a weaker haul
on a guess.

*Rejected, with the reason on the record.* Pulling the car ALONG the
fall line instead of shrinking the budget was considered and refused:
on the OUTER glacis (design v3 section 3.1: r 91.4->113, z 6.5->0, and
G9's own ground z 101.0->100.0 across r 99->111) downhill points
OUTWARD, away from the arena. Steering the well down the fall line would
drive a strayed car further out — the opposite of containment. The fall
line is used to READ the danger, not to aim the pull.

Gates: 99 lupa tests (7 new). The slope solve is checked against its own
arithmetic at 0 %, 15 % and 30 % (0.620 / 0.522 / 0.402 g of haul); the
apron number is pinned to v2.10's measured 0.620 g so the braked hulk and
every flat behaviour are byte-identical; a 6.3 m/s traverse is capped on
a slope and NOT on the flat; a missed probe falls open to flat; the probe
is proven to run only for hauled cars and to stay inside 3-15 rays for
2 s of hauling. Sync (4), HUD app (8), pack (467): **578 passed**.

What lupa cannot prove, for G10: whether the tamed lateral pull actually
stops the trip on real suspension geometry, and whether re-entry still
completes against a driver fighting it. The runtime side is pinned at the
command level only.

Re-cut under the law: 45/45, only runtime.lua (4a027f2a… → 7b943dd8…),
serial 50 → 51, stamped 2026-09-02T09:34:07. Build serial 51.

## v2.12 — the pin, and the last open items (2026-09-02)

G10 on serial 51: orbit uprightness **1/6 → 5/6 at 1.2 g and 2/6 → 5/6 at
2.0 g**, crest-ram hauls **6.85-6.95 s on all six** (the regression target
held), and the dodge's dangerous signature gone — zero contacts above
2.7 m/s, zero flank, jamb or tower. This is the last runtime round of the
arena effort; what could not be closed honestly is recorded below rather
than chased.

*The falsifier fired, and the ruling is: the reference run was never
flat.* Attempt 1 (bearing 100) moved between serials — max r 113.2 → 115.1
at 1.2 g, min up-vector 0.886 → 0.942 — with max speed unchanged to the
decimal (29.9 / 29.8). At grade 0 every v2.11 term reduces to the v2.10
expression EXACTLY: the allowance `RATIO·MARGIN·cos(0) − sin(0)` is
`RATIO·MARGIN`, the hoist's slope factor is 1, and the speed gate stays at
8 m/s. So a run whose numbers move cannot have been at grade 0 throughout
— and that run reaches r 113-115, which is the glacis toe and past it,
having crossed the bank (r 76-91.4) and the whole glacis (91.4-113) to get
there. The integration worker's reading is correct and is now pinned by a
gate that asserts the flat well is identical to the digit (hoist 9.0 m,
lift 0.139 g, haul 0.620 g) AND that the same car on a 30 % grade sees the
slope terms engage. The direction of the change is its own corroboration:
less lateral pull on the sloped part of the path means less tipping (uz
UP) and slightly less inward drag (max r up 1.9 m), with speed untouched
— exactly the signature of the slope term, and nothing like a flat-path
regression.

*The pin (D-8), fixed.* With the fast strikes gone, what remained was
their opposite: 23 contacts at two grinders by three cars over 145 s,
every one at ≤ 2.7 m/s, median 0.7 m/s, at FIXED positions — cars pinned
against a pillar, grinding in place. The dodge rays the VELOCITY vector,
so a pinned car is invisible to it: `speed > 3.0` gates it out. **That
floor is v2.7.1's own** (baseline spec L3286, shipped long before the
arena work) and it is NOT the magnet's slope gate — that is a different
constant in a different function, and the two were never coupled. The
brief's suspicion was reasonable and the record should be exact. A
stationary car needs a different reflex anyway: not "steer around what you
are about to hit" but "back away from what you are already touching". So a
car within 1.5 m of a registered keep-out at ≤ 3 m/s for 1.5 s is given a
latched target on the far side of itself from the post, `keep-out + 10` m
out. Latched, so it commits rather than becoming the 4 Hz limit cycle
v2.10 killed; time-boxed at 6 s, so a car that cannot get clear is handed
back to its game role instead of being steered at a wall for ever; and it
ignores a car that is merely creeping in open ground.

*Re-entry (D-5): an accepted trade, stated plainly.* Re-entry went 3/6 →
2/6 at both dials while uprightness went 1/6 → 5/6. That is the direct,
deliberate consequence of the slope cap, not a side effect: on the glacis
the lateral pull is cut from 0.620 g to 0.402 g, and on a traverse the
inward direction IS the lateral direction, so less tipping and less
inward drag are the same number. There is no clean way to have both
inside this mechanism — the well hangs over the pad, so its direction is
geometry, not a choice, and the only free variable is magnitude. Raising
it re-rolls the car. The trade is taken with the reason on the record: an
upright car outside the ring is strictly better than a rolled one, the
transfer sweep and the hold-mode scoring gate already exclude out-of-ring
cars from the game, and a car that stays on its wheels can drive itself
back in.

*Recorded, not fixed.* **D-7**: the stochastic ram roll (boot 1 rolled at
110 km/h, up-vector −0.826; boot 2 clean 3/3) — one roll per boot, moving
between speeds, which is a dice-roll signature rather than a threshold.
**D-9**: the D-series pickup rolled at r 82.5, INSIDE the ring on the
bank (ground z 101.19, 17.8 m/s) — a position class no etk800 roll
occupied. Together they answer the residual risk this ledger named in
v2.11: it is neither purely vehicle-specific nor purely position-specific.
The taller car tipped on the steeper surface, which is what a SHARED
tipping ratio predicts. The tip budget uses one conservative generic
number for every car — `half-track / CG height = 1.2`. A future round
wanting these closed needs a PER-VEHICLE measurement instead: half-track
from the spawn OOBB (`getSpawnWorldOOBB():getHalfExtents()`, already read
once per car for the extents cache) and CG height from the same box, so a
pickup and a hatchback get different budgets. That is a real change to the
magnet's contract and belongs in its own round with its own live gate,
not bolted onto this one.

Gates: 103 lupa tests (4 new): a pinned car is backed out and a momentary
pause is not; the escape commits, refuses the role stomp, and hands back
at its ceiling; a slow car in open ground is left alone; and the falsifier
ruling is pinned from both sides (flat identical to the digit, slope
engaging). Sync (4), HUD app (8), pack (467): **582 passed**.

Re-cut under the law: 45/45, only runtime.lua (7b943dd8… → dece0943…),
serial 51 → 52, stamped 2026-09-02T10:02:35. Build serial 52.

## v2.13 — the out-of-bounds burn, and a reversed decision (2026-09-02)

The final critic withheld WOWED on a finding that outranks every gate this
effort passed: **the brief's failure mode #1 is not countered, only
relocated.** G10.1 on the shipped build measured a powered car holding
29.9 m/s at r ~115 m for 40 s and never returning — on **4 of 6 bearings,
at BOTH magnet dials, upright throughout** (min uz 0.94). The bearing
pattern is the tell, and no report of mine stated it: the two bearings
that DO re-enter are the SPOUTS; the four that escape climb the bank onto
the flat runoff apron past the r 113 toe. Tall class 0/3. In a 1v1 endgame
the orbiter wins by driving in a circle.

**The v2.6 decision is reversed on evidence.** That ledger considered this
exact mechanism — the player's own out-of-bounds fuse penalty — and
declined it: "an out-of-bounds fuse-burn penalty (invisible punishment,
illegible in play)", choosing the magnet as the shipped answer. The magnet
is a good mechanism and v2.9-v2.12 made it a much better one, but G10
measured it failing at the one job this counter existed for. A
justification that is measured false is not a justification. The
legibility objection was real, though, and is answered rather than
ignored: the state is published in both stats channels and both
transitions are announced.

*The mechanism, in the player's words.* "If the vehicle carrying the
potato goes out of bounds, the potato detonate timer accelerates to 3x
speed until they re-enter the arena." `oob_burn_multiplier` (1.0-5.0,
default **1.0 = OFF**) burns the fuse faster while the CARRIER is outside
`v26.insideArena` — the same one ring definition every other consumer
uses, so with the arena disabled it returns true and this is
byte-identical to before. Targeting the carrier is not a simplification,
it is the whole point: a non-carrier outside already cannot receive
(v2.6) and cannot score (v2.8), so **only a carrier can win by orbiting**.

*Two burns, one rule.* Camp burn and out-of-bounds burn combine with
**max(), never a product**. They are two answers to the same question —
this carrier is not playing — and 3x camping times 3x out-of-bounds would
be a 9x fuse that detonates almost instantly: a punishment no player could
read as a rule.

*No new B key, and therefore no Blender stage.* `OPT` is seeded from `B`,
which is the handoff's `behavior.tunables` block written by the Blender
generator — so a new option would normally mean a Blender run and a much
wider re-cut. It does not here: the option is declared in OPTION_RANGE
(which is what the HUD app builds its controls from, and what clamps and
persists it) and its shipped default lives in `seedOptions` behind an
`OPT[key] == nil` check. The handoff is byte-identical, `build.py prop`
alone ships it, and the tunables law's own preferred path — "prefer adding
no new B keys" — is honoured rather than worked around. The arena turns it
on in its boot calls like every other arena option, and hand-back is
already solved.

Gates: 110 lupa tests (7 new): the option defaults off, appears in the
schema and clamps to 5.0; a carrier outside burns 3x and returns to real
time on re-entry; default-off and arena-off are both no-ops; camp and
out-of-bounds take the max, and the larger of the two wins; a non-carrier
outside changes nothing; the flag lights in both stats channels with
exactly one message per transition (never repeating while held); and an
orbiting carrier's own fuse ends the round. Sync (4), HUD app (8), pack
(467): **589 passed**.

Re-cut under the law: 45/45, only runtime.lua (dece0943… → 2bbdfda9…),
handoff unchanged, serial 52 → 53, stamped 2026-09-02T10:16:16. Note for
whoever ships the arena: every runtime re-cut invalidates the arena
package's `depends_on` pin, so the arena needs its own one-member re-cut
against serial 53. Build serial 53.

## v2.14 — the envelope that never armed (2026-09-02)

G11 measured the v2.12 unpin reflex and it **did not close D-8**. The log
is unambiguous and it is not the failure this ledger predicted: twelve
grinding events at one spot, `events_with_car_within_6_5m = 0` with the
nearest car at 12.2 m — so nothing was pinning anything — and **the
reflex's own envelope counter reads 0. It never armed at all.** Minimum
clearance during the events was **1.85-2.02 m against a 1.5 m trigger**.
The v2.12 entry called this reflex a fix; the honest description is that
it was never exercised, and the docs now say so.

*The measurement is the fix.* The 1.5 m envelope was a constant chosen
with reference to neither the obstacle nor the car, measured from the
car's REFERENCE POINT to the keep-out edge. A ref node is roughly a car's
centre, and a 4.4-4.8 m car carries about 2.5 m of circumscribed
half-extent — so a ref clearance of 1.9 m is a **body already ~0.6 m
inside the keep-out**: a clearance that reads safe while the contact is
real. That is why the events clustered just outside a threshold that
looked generous.

So the envelope is now measured to the car's nearest extent and expressed
in the two quantities that define the encounter: **the post's own authored
keep-out** (6.5 m for pillars, towers and jamb noses; 8.0 m for handle
corners and jamb mid-faces — already in the registry) **plus the car's
cached extents** (the circumscribed plan radius of the spawn OOBB, one
read per car per session, the same cache the transfer sweep has used since
v1). The only constant left is a 0.5 m margin. It arms at the measured
1.85-2.02 m because the body gap there is negative; it cannot arm on
open-ground creeping because a car dawdling tens of metres from every post
has an extent gap of tens of metres. Every ask-#5 anti-limit-cycle guard
is untouched: the target is latched, the release is range-only, and the
escape is time-boxed at 6 s.

Gates: 113 lupa tests (2 new, 1 reshaped): the exact G11 geometry — a car
at 1.9 m of ref clearance from a 6.5 m post at 0.7 m/s for 2 s, with no
other car inside 6.5 m — must arm the escape; and the envelope is proven
to scale with the post rather than being constant, by parking a car at one
fixed 10.5 m radius where an 8.0 m post arms and a 6.5 m post does not.
The v2.12 cases still pass unchanged. Sync (4), HUD app (8), pack (467):
**592 passed**.

Re-cut under the law: 45/45, only runtime.lua (2bbdfda9… → 083005da…),
handoff unchanged, serial 53 → 54, stamped 2026-09-02T10:25:21. Build
serial 54.

## v2.15 — two radii, and a rate you can read (2026-09-02)

G12 returned two findings. One is a real contract defect this round fixes;
the other is a measurement the code says cannot happen as reported, and the
fix for it is an instrument rather than a behaviour change.

*The pin armed — on the wrong radius.* v2.14's envelope worked (0 → 4,093
arming samples, the number that round was most exposed on) but it sized
itself on `post.r`, the authored KEEP-OUT (6.5 m for pillars and towers,
8.0 m for handle corners and jamb faces). The keep-out is an avoidance
corridor, not a description of the thing: the arena's pillars measure
1.2-2.1 m. So the arming disc inflated to a flat ~9.4 m around all 42
posts and started shoving cars that were merely driving past — contacts
17 → 51, grinds 1 → 3. The two radii answer different questions and this
round separates them:

- **`r`, the keep-out**, is how wide a berth a MOVING car should give. The
  steering dodge keeps using it, and always should have.
- **`rp`, the solid's physical radius**, is how big the thing actually is.
  The pin reflex uses it, because "am I grinding against this" is a
  question about the solid.

`hotPotatoRegisterObstacles` now accepts `{x, y, r, rp}`. **`rp` is
optional and defaults to `r`**, so every caller written before this round
behaves exactly as it did; it is validated like every other field
(numeric, at least 0.1 m, and never larger than the `r` it sits inside —
refused whole, one warning, prior set untouched), and
`hotPotatoGetObstacles` reports it. The arch feet supply their own: the
2.06 m half-side the 6.5 m keep-out was derived from in v2.7.1. The escape
distance moved to the solid too — backing a car 16.5 m out of a 1.5 m
pillar was itself part of what pushed cars off course.

*The fuse burn measured 1.71x against a specified 3.0x — and the code says
that number cannot come from the burn.* `remaining = fuseEnds - now`. Each
behaviour frame `advanceClock` sets `b.now = b.now + delta` and
`b.lastDelta = delta` **on the same two lines from the same value**
(L1063-1064), and the penalty subtracts `(burn - 1) x b.lastDelta`. So the
fuse falls at exactly `burn` times the mod's own clock. There is no ramp,
no smoothing, and no partial application anywhere in the path.

A ratio strictly between 1 and `burn` therefore means frames elapsed in the
MEASURER's wall time during which the penalty line did not run. Exactly two
things do that, and neither is the burn: the round left the "live" phase
(the harness's own disclosed `reset=True` → `drop_round` behaviour), or
`advanceClock` zeroed its delta — L1060 discards any wall gap over 0.5 s
and L1062 skips frames with `dtSim == 0`, freezing `b.now` and
`b.lastDelta` together so the fuse pauses while real seconds pass. The
same single cause explains the driven sample reading `oob` false and 1.00x:
if the round was not live, the live branch never ran, so the flag was never
set and no penalty was applied. One cause, both readings — and it is
consistent with the boundary probe being clean, since that probe never
moved the carrier.

Rather than argue the point, the rate is now published. `fuse_burn` (the
multiplier actually applied this frame) and `clock_delta` (the delta it
rode on) ship in `behavior_stats`, and `fuse_burn` in the HUD payload too.
A gate reads the rate instead of inferring it from a clock it does not own,
and a future disagreement between published rate and observed slope is
immediately attributable: if `fuse_burn` reads 3.0 while the measured ratio
reads 1.71, the missing 1.29 is stalled or non-live frames, provably.

Gates: 119 lupa tests (6 new): absent `rp` reports as `r` and behaves as
before; the pin no longer arms 5.5 m clear of a 1.5 m pillar but still
arms against the solid, and backs out to 11.5 m rather than 16.5; the
steering dodge still aims the full 10.5 m keep-out berth on the same post;
a bad `rp` is refused whole; and the published burn reads 1.0 in the ring,
3.0 outside, with the fuse falling by exactly that rate. Sync (4), HUD app
(8), pack (467): **598 passed**.

Re-cut under the law: 45/45, only runtime.lua (083005da… → 83e3cd1e…),
handoff unchanged, serial 54 → 55, stamped 2026-09-02T11:41:20. Build
serial 55.

## v2.16 — the registry cap, ask #8 (2026-09-05)

*Ask #8 — `OBSTACLE_CAP` 64 → 128, from the standalone level's design
round (critic C r2, defect 2).* The cap was sized in v2.8 for the arena
alone: the Gateway Skillet registers **46** posts (its handoff's
`obstacles` list — 42 through v2.14, 46 once the long wall faces gained
their interior sample points), and 64 left that room. The standalone level
keeps the arena unchanged inside r 113 and places its own solids outside
the pan — 20 hearth stones and 8 chocks (`r = ρ + 4, rp = ρ`), three
tangential logs as chains at ≤ 12 m pitch (10 + 8 + 7 points, so
`sqrt(r² − (pitch/2)²) ≥ rp` covers the whole log), the leaner's
car-height foot (3), the tripod feet (3), the pot, the sign, 2 cairns and 4
lantern posts — which the design round's layout model counts honestly at
**67 rows** (`registry_rows()` in that round's `layout.py`, which lives in
the level round's design scratchpad `level_round/design/` beside its
`layout.out`, NOT under `examples/hot_potato_arena/level/` — it lands in
the repo with the level; level design v2 §7.3 carries the same breakdown).
A call REPLACES the set, so the level must hand the runtime
the arena's posts and its own in ONE list: 46 + 67 = **113**. The v1
design's "46 + 40 = 86 in one call" would have registered NOTHING — a
65th entry refuses the whole call, by design (v2.8: a scenario that
registers 70 posts and asserts true must not believe all 70 are
protected). That refusal is the right behaviour and stays; only the
number moves. 128 holds the 113 with the level's optional 8-point shore
fence (121) still inside it; the 18-row fallback the design priced for a
refused ask is recorded there, not built. Nothing else about the contract
changes: the dodge sweep and the pin reflex are linear passes over what is
REGISTERED, so the per-frame cost follows the count (113 against 46
distance tests), not the cap; malformed and non-dense lists are refused
whole exactly as before; `rp` still defaults to `r`.

One constant and its two doc comments in `spec.py` — `v26.OBSTACLE_CAP =
128` with a note above it recording the arithmetic, and the hook table's
"at most 128 entries" / "a 129th entry" — no handoff change, no Blender
stage, no new options, no new top-level locals. The lupa pin moved in
place: `test_obstacle_registration_validates_caps_and_clears` now refuses
the 129th entry (not truncated), refuses a malformed entry INSIDE the cap
(127 good + one junk row = 128 entries, so the walk must examine and reject
it rather than trip the cap first — the earlier "malformed 130th behind 128
good ones" case was moot because the cap trips on the 129th step of the
walk, before the junk at row 130 is reached, and rows 1–128 pass validation
first), asserts exactly one `more than 128 entries` warning and
exactly one `rejected entry 128` by text, accepts exactly 128 (entry 128 at
x 127, entry 129 nil), and still proves a call replaces, `{}` and nil
clear, the report is a copy, the set survives a prop reset and dies at
teardown.

Gates: 119 lupa tests (0 new, 1 re-pinned), sync (4), the arena's own lupa
suite (57 — its registered count derives from its handoff and did not
move), pack `-k hot_potato` (22 passed, 1 skipped for the console panel):
green. The arena's lock still chains to serial 55 (`depends_on.build_serial
55`, `45912b9d…`), so `tests/test_hot_potato_arena_package.py`'s lock-chain
assert fails by construction until the arena is re-cut against 56
(`sync_scenario_outputs.py` → `build_distribution --overwrite`); that
re-cut belongs to the level round's B5, which re-cuts the arena anyway when
the scenario moves levels. Three stale "64" mirrors sit in the arena, all
the arena's (B5's) to correct at that re-cut and none touched under this
ask: its DESIGN.md §5.1 ("at most 64") and §5.4 ("count ~= 42"), and — the
executable one — `blender/create_arena.py`, where `OBSTACLE_RUNTIME_CAP =
64` (L1845, its comment claiming to BE `v26.OBSTACLE_CAP`) is enforced by
the A25 `fail(...)` at L3868-3872 and restated in the A25 docstring at L54
("cap of 64"). The arena still builds under it (46 ≤ 64 ≤ 128), so that is
a build-stage assert stating the wrong contract, not a runtime defect — but
a B5 that fixes only the two prose lines leaves the arena's own stage
refusing tables the runtime now accepts. It must read 128 at the re-cut.

Re-cut under the law: 45/45, only runtime.lua (83e3cd1e… → 81dc78d8…),
the 19 certified DDS and the harvest manifest untouched, handoff unchanged,
lock sha == zip sha (67cc432b…), serial 55 → 56, stamped
2026-09-05T11:28:53. Build serial 56.
