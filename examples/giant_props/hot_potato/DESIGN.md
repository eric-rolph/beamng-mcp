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

The binding constraint is `AGENTS.md`: **no global `modScript.lua`**. Some
object must own the GE extension's load/unload lifecycle. That gives two
legitimate shells, and they should share one core.

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
- **Multiplayer.** BeamMP sync is out of scope for this framework; the
  runtime is single-client by construction. Say so in the Repository overview
  rather than implying it works.
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
