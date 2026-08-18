# Giant Props pack

Ten oversized cartoon contraptions for BeamNG.drive, built on the Cannon Car
Wash evidence chain: a deterministic Blender generator owns every coordinate,
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

Design rule shared by every contraption: **exaggerate the anticipation**.
The toaster ticks, the swatter hovers, the egg wobbles, the whale inhales,
the boot draws back — the pause before the chaos is the joke.

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

## Validation

```powershell
# Static gates for all ten mods (handoff hashes, JBeam/cage consistency,
# materials coverage, runtime boilerplate, ZIP locks).
.\.venv\Scripts\python.exe -m pytest -q .\tests\test_giant_props_pack.py

# Live smoke gate (opt-in; sentinel-isolated profile): boots BeamNG with the
# packaged Giant Toaster, proves register -> zone -> tick -> POP -> launch.
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_giant_props_live.py
```

The live gate exercises the shared runtime core that all ten mods generate
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
