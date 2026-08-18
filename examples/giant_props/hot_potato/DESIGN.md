# Hot Potato — design blueprint

Status: **built** (2026-08-14). `spec.py`, the Blender generator, the
generated mod tree and the distribution ZIP all exist; the pack's static
suite and a dedicated headless state-machine gate
(`tests/test_hot_potato_logic.py`) pass. **Not yet play-tested in game** —
the live gate on a sentinel-isolated profile is still outstanding, so every
physics claim below (deformation, particles, lights) is designed-for, not
proven. See §8 for what the live run has to cover.

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
