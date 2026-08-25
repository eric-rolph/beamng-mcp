# BeamNG MCP repository guide

These instructions apply to this repository. This is the `beamng-mcp` simulator-control and
mod-authoring project, not the benchmark repository described by the parent-directory guidance.
Preserve the safety gates and deterministic evidence chain even when a requested shortcut appears
to work locally.

## Architecture and ownership boundaries

- The Python MCP server is the low-rate control plane. `src/beamng_mcp/mcp_adapter.py` exposes
  typed tools; `runtime.py`, `models.py`, and `config.py` own application state and policy.
- `adapters/beamngpy_adapter.py` serializes supported BeamNGpy calls. BeamNGpy is the primary
  simulator API and its supported contract is BeamNG.tech; retail BeamNG.drive behavior is marked
  experimental and must be proven against the pinned runtime.
- `adapters/lua_bridge.py` talks JSON over an authenticated, loopback-only WebSocket to
  `assets/beamng_mod/lua/ge/extensions/beamng_mcp/bridge.lua`. The bridge is an allowlisted local
  data/control plane, not a general Lua evaluator. Its engine-side lease must fail to AI-off plus
  full service and parking brake.
- `services/` owns confined mod workspaces, staging, exact Collada/JBeam construction, packaging,
  jobs, Blender handoffs, and structural validation. Do not bypass quotas, path confinement,
  optimistic-concurrency hashes, confirmation gates, or install backups with ad hoc file writes.
- `vision/` keeps the 10-30 Hz perception/control loop local. OpenCV, ONNX Runtime, and SegFormer
  load lazily. Never put an LLM or network round trip in the real-time steering/braking loop.
- Blender MCP and BeamNG MCP are peer servers orchestrated by the client. Neither receives a
  general-purpose tool for invoking the other.

Read `README.md`, `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`,
`docs/SOFTBODY_AUTHORING.md`, and `docs/TOOLS.md` before changing protocol, safety, structural, or
live-simulator behavior.

## Required Blender-to-BeamNG pipeline

Treat each phase as a gate. Do not advance when the current phase has not produced reviewable,
machine-validated evidence.

1. **Visual and cage authoring in Blender**
   - Build an optimized visual shell and a separate sparse physics cage. Apply scale/rotation and
     keep the final export Z-up with finite coordinates and `meter=1`.
   - Give cage vertices stable `beamng_node_id` POINT-string attributes and assign explicit
     `beamng_ref`, `beamng_back`, `beamng_left`, and `beamng_up` groups. A ground-standing prop
     needs at least three non-collinear minimum-Z `beamng_base` nodes.
   - Extract evaluated, unrounded Blender-world coordinates, bounds, object/material identities,
     topology, and the reviewed rigid transform. Never infer a physics vertex from an image,
     prose, a nominal dimension, or a rounded display value.

2. **Exact coordinate handoff**
   - Call `softbody_handoff_create`, then send its returned `blender_execute_code` to Blender MCP
     verbatim. Do not reconstruct the call from helper paths.
   - Call `softbody_handoff_validate` and review its hashes, transform, exact bounds,
     `measured_volume_m3`, node/base IDs, refnodes, and topology. Stop on any mismatch.
   - The canonical vehicle frame is +X left, +Y backward, +Z up. Record any map/world transform
     separately. Never hallucinate or hand-edit JBeam coordinates after this handoff.

3. **JBeam physics construction**
   - Use `softbody_mod_build` from the validated one-use slot. Policy inputs may select material,
     mass, fixed/grounded behavior, hydros, rails, and slidenodes; they may not replace measured
     geometry.
   - Generate connected beams with explicit three-dimensional/X bracing, non-zero lengths, and
     material-appropriate spring/damping/deformation values. Generate nondegenerate, supported,
     correctly wound collision triangles and an exact flexbody mesh/group mapping.
   - Preserve requested total mass and center of mass. Static infrastructure uses intentionally
     fixed anchors and a heavy stable base; deformable or mechanical objects must be tested at
     limits, not merely parsed.
   - V1 supports one connected cage/visual/material/flexbody. A crusher plate or other disconnected
     mechanism requires a deliberately reviewed multi-body/v2 design, not fabricated connecting
     nodes.

4. **Mod assembly**
   - Keep the generated `.jbeam`, runtime `.dae`, `main.materials.json`, selector/config metadata,
     and canonical structure evidence in one atomic revision. BeamNG 0.38 vehicle flexbodies use
     Collada at runtime; glTF is diagnostic interchange here.
   - Use `softbody_mod_validate`, `mod_file_list`/`mod_file_read`, `mod_validate`, then
     `mod_pack` or `mod_test_start(pack=true)`. Static validation and packing do not prove physics.

5. **Authored Lua and triggers**
   - The generic MCP trigger lifecycle is typed and ephemeral:
     `map_trigger_create` (draft) -> `map_trigger_update(enabled=true)` -> poll events -> disable ->
     `map_trigger_delete(confirm=true)`. It emits events only and accepts no callback, command, or
     arbitrary Lua field.
   - Scenario-specific behavior belongs in a fixed, reviewed scenario-local GELua extension named
     in the scenario JSON `extensions` table. BeamNG must own its load/unload lifecycle; do not use
     a global `modScript.lua` bootstrap. Use `BeamNGTrigger` plus `onBeamNGTrigger`, exact object and
     vehicle identity, finite values, bounded state, mission cleanup, and idempotent enter/exit
     handling. Revalidate the live trigger mode and test type before acting; fail closed on partial
     activation.
   - A launcher must use `Contains` with `Bounding box` and start only when the entire intended
     vehicle is contained. An ambient wash trigger may use `Overlaps`. Same-frame/out-of-order
     nested events must be deferred until their prerequisites are active.

6. **Live validation**
   - Install only the reviewed package into a sentinel-isolated profile, launch a fresh owned
     BeamNG process, and test spawn, settle, collision, mechanism limits, trigger enter/exit,
     reset, reload, telemetry, and Lua logs. Fix failures and rerun the affected gate before moving
     on.
   - Query real map surfaces/road edges. Add model-origin clearance for vehicles and use the
     measured surface Z directly only for base-origin static props. Do not guess Z or rely on
     BeamNGpy `cling` during `Scenario.add_vehicle`; that caused above/below-map spawns.

## Cannon Car Wash baseline

`examples/cannon_car_wash` is the reference end-to-end workflow. Its authoring source and
generator are under `blender/`; its local distributable staging tree is `mod/`; live evidence is
under `telemetry/`.

- The selector model is a rigid `Type: Prop` named Cannon Car Wash. Its validated topology is
  79/79 fixed nodes, 329 beams, 144 collision triangles, one flexbody, and 15,125 kg. The exact
  Blender-derived ground datum is the
  `ericrolph_cannon_car_wash_ground_reference` node at `[0, 0, 0]`, with
  `ericrolph_cannon_car_wash_ground_back` at `[0, 3, 0]`; base-origin placement therefore uses the
  measured map surface Z without an estimated clearance. Eight Blender-derived outer floor/roof
  corner nodes deliberately use collision mode 3 so BeamNG's safe-placement OOBB is valid; keep
  all other selector nodes non-colliding and verify an elevated cling spawn settles flush.
- The selector prop owns a vehicle-local bootstrap which registers its instance with the on-demand
  `ericrolph_cannon_car_wash/runtime` GELua manager. For each placed prop the manager hides the
  static flexbody visual, adds the vehicle-local non-colliding animated visual, an `Overlaps` wash
  trigger, a
  dedicated `Overlaps` repair trigger at the wash midpoint, a `Contains` launch trigger, and
  sixteen particle nodes. The exact inventory is six `BNGP_sprinkler` water jets, six
  `BNGP_waterfallsteam` primary dryer jets, two `BNGP_34` exhaust-steam accents, and two `BNGP_2`
  ambient-dust accents. These objects are transient, namespaced and non-saveable. They follow the
  prop transform; an external reset cancels any held countdown, releases its subject, and rebuilds
  all three triggers so vehicles already inside receive fresh overlap events. All runtime objects
  are removed on unregister/destruction/mission teardown, and the manager unloads after the last
  prop is gone.
  There is no global `modScript.lua`.
- The selector-owned runtime accepts arbitrary real vehicles. Wash occupancy is reference-counted:
  the first real vehicle entering starts the rollers and all sixteen water/dryer layers, and they
  remain active until the final real vehicle exits or resets. An unexpected subject reset outside
  the acknowledged repair callback sequence removes only that subject; never clear the complete
  occupancy table or stop the wash while another vehicle remains. The scenario lifecycle uses the
  same reference-counted occupancy contract.
  Launch begins only when a vehicle is fully contained: it freezes the
  subject, displays `3...`, `2...`, `1...`, `GO!` one second apart, then replaces main-cluster
  velocity with 100 m/s (360 km/h)
  along the measured current forward axis. ParticleEmitterNode emits along local +Z, so every
  static and runtime mister transform must be proven inward after nonzero prop yaw. Countdown hold
  uses an acknowledged controller freeze plus one uniform cluster stop; release must be
  acknowledged and followed by two simulating frames before the only launch impulse. Never restore
  the old per-frame velocity override or direct brake/parking-brake input mutation.
- `ParticleEmitterNode.emitter` requires a `ParticleEmitterData` (`BNGP_*`) object, not a
  `ParticleData` (`BNG_*`) object. The requested labels `BNG_Waterfall_Mist`,
  `BNG_exhaust_steam`, and `BNG_Ambient_Dust` do not exist in the shipped data — RE-VERIFIED
  2026-08-15 against the engine that reports itself as **v0.39.4.0 build 20972**, still zero hits
  across all 173 install zips, alongside 91 distinct `ParticleEmitterData` and 95 `ParticleData`
  objects that DO exist (`D4_particles.py`). The "0.38.6" this line used to name was never read off
  an engine; see the version-provenance law in the Round-16/17 ledger. Their
  verified runtime mappings are `BNGP_waterfallsteam` -> `BNG_waterfallsteam`, `BNGP_34` ->
  `BNG_steam_light_exhaust`, and `BNGP_2` -> `BNG_dust_light`. Preserve exact case. Local +Z is
  the emission axis, and serialized rotation matrices are column-major, so the third column must
  face inward. Do not multiply the 1 ms steam/dust emitters across every nozzle without a measured
  performance budget; this baseline deliberately uses one accent of each type per side.
- Entering the wash midpoint repairs any non-prop vehicle once per wash pass. The only supported
  trigger is namespaced `ericrolph_cannon_car_wash_repair_trigger`, local center
  `[0, 0, 2.1]`, dimensions `[5.4, 2.2, 4.2]`, `Overlaps` plus `Bounding box`. The only supported
  implementation is the stock full-reset pair `vehicle:requestReset(RESET_PHYSICS)` plus
  `vehicle:resetBrokenFlexMesh()`. The repair precheck must acknowledge a dedicated controller
  freeze while preserving its previous state, then snapshot the vehicle's exact live pose.
  `RESET_PHYSICS` moves and can reorient a rolling vehicle even while frozen, so the pose policy
  is `restore_exact_pre_repair_pose`: after consuming its `onVehicleResetted`, re-apply the
  snapshot position and rotation verbatim with `vehicle:setPositionRotation(...)`, consume its
  second callback as `pose_restore_pending`, and allow at most two bounded corrective re-applies
  of the same snapshot. There is no corridor realignment, centerline translation, or dependence
  on the placed prop's yaw — the corridor-basis variant misaligned vehicles at nonzero prop
  rotations and moved the follow camera; the vehicle must end the repair precisely where and how
  it stood. After two positive simulation frames, verify damage <= 0.01, no part damage, no broken
  beams, no deflated tires, position drift <= 0.15 m from the snapshot, horizontal heading dot
  >= 0.995, and upright dot >= 0.98 against the snapshot basis. The direction and upright vectors
  derive from the node cluster, so un-crumpling a heavily damaged body legitimately shifts them a
  few degrees while the vehicle itself does not move — the measured city-bus delta is ~2.9
  degrees, which is why the thresholds tolerate deformation-scale shifts while still refuting
  gross misrotation. Restore the prior freeze state through an acknowledged
  release; only then emit `repair_complete` or permit launch. In the selector runtime the
  authoritative midpoint detection is positional: each wash subject is projected into the prop
  frame every frame with a previous-sample segment test across the band, because BeamNGTrigger
  stops delivering `Overlaps` enter events for the thin transient repair band at rotated prop
  yaws (verified live at 90 degrees with provably correct trigger transforms); the trigger object
  remains for inspection and exit telemetry, and both detection paths funnel through one latched
  `startRepair`. The scenario keeps its persistent fixed-yaw trigger. Every failure/teardown path must make
  a best-effort release so a subject cannot remain frozen. Never substitute `beamstate.reset()`
  (bookkeeping only), flex-mesh reset alone (visual only), recovery/safe teleport (chooses a
  different pose), a hard-coded model yaw correction, or let either intentional callback enter the
  generic reset-abort path.
- The `Contains` launcher occupies the complete wash bay at local center `[0, 0, 2.1]` with
  dimensions `[5.8, 17.5, 4.6]`. Its validated large-vehicle envelope is the stock Wentward
  DT40L city bus (`citybus`, configuration `city`), measured from the vehicle metadata of the
  build this programme actually ran on — engine-REPORTED `0.38.6.0.19963`
  (`examples/cannon_car_wash/telemetry/cannon_car_wash_phase4_results.json`), which is a real
  attestation and not the profile-directory name — as
  3.11 m wide, 12.63 m long, and 2.994 m high and confirmed with its live world OOBB. Launch is
  never eligible until that subject's one-pass repair state is complete. A pre-launch `Contains`
  exit can be an OOBB-edge jitter event for a large suspended vehicle; suppress it only while the
  same active subject is still recorded inside the wash and the wash systems remain active. A real
  wash exit still aborts, while an exit after launch completes the run.
- Suppress wash exits only while the reset/pose-reset edge guard is active. A reset-generated
  re-entry clears the deferred exit before any duplicate-subject return. At guard expiry, remove a
  subject whose exit remains deferred; otherwise reprocess its pending launch. Do not discard a
  legitimate precheck exit, clear `washExitDeferred` without reconciliation, or allow launch while
  the edge guard/deferred-exit flag remains active. Retain the one-pass repair latch until the
  subject exits the full wash; otherwise the reset can recurse.
- Generic `world.get_object`/`world.list_objects` inspection has a separate read-only allowlist for
  packaged `BeamNGTrigger` and `ParticleEmitterNode` objects. Its fields are limited to
  `triggerMode`/`triggerTestType` and `dataBlock`/`emitter`. These classes must remain absent from
  the generic creation and writable-field allowlists; trigger mutation stays on the typed trigger
  API so `luaFunction` never becomes a generic execution surface.
- The Gridmap V2 scenario remains a separate behavior path. Its JSON declares a scenario-owned
  extension, its triggers use the persistent prefab objects, and it defaults to a named D-Series
  while accepting any exact live vehicle subject, including the stock city bus. Do not merge that
  scenario lifecycle into the selector manager or make either extension globally resident.
- `sync_scenario_outputs.py` synchronizes all three Blender-authored trigger transforms plus the
  particle layers into the Phase 2 manifest and scenario prefab. Never update only one generated
  trigger copy or hand-patch runtime geometry independently of the Blender handoff.
- The v1.10 visual export is deliberately bounded: the scenario DAE is 13,830 triangles across 34
  primitive groups and 18 materials; the consolidated selector DAE is 13,782 triangles across 18
  groups. Five real window openings per side are boolean-cut through the walls and liners with
  wall bounds (and therefore the cage) unchanged. The 2048x1024 signage atlas carries the entrance
  sign in its top half plus the FIRING TABLE menu board and exit thank-you strip below, all on the
  single sign_face material. Its separate vehicle-local runtime DAE retains five independently animated brush
  channels. Vertical brushes use 16 alpha-tested radial cards and the overhead brush uses 14;
  collision remains on the simple authored shell. The exported `ambient` animation clip carries an
  explicit `<extra><technique profile="Torque"><cyclic>1</cyclic>` flag — Torque-derived Collada
  loaders default explicit clips to non-cyclic, which froze the rollers after one 2.54 s
  revolution; the flag keeps them looping for the whole reference-counted occupancy window. The
  entrance sign is a tower-mounted cabinet (face card at local `[0, -9.639, 4.90]` on a raised
  fascia, stainless retainer, cannon finial) with a 2048x512 atlas; architectural details
  (parapet/coping, pilasters, wainscot, clearance bar, menu monument, bollards, exit accents,
  rooftop equipment) reuse the existing 18 materials and stay outside the drive envelope. The
  masonry/corrugated tiles are metric-true procedural textures; only wet concrete keeps a photo
  source. The public runtime contains 22 BeamNG-cooked DDS
  textures and no authoring PNGs. Blender's `.blend` file uses numeric preview materials; the two
  namespaced `main.materials.json` files and in-game BeamNG inspection are the PBR authority.
- Thirteen Blender-authored light anchors are synchronized into both lifecycles, all shadowless:
  five cool-blue tunnel PointLights at local X=0, Z=4.34, Y=-6.8/-3.4/0/3.4/6.8, brightness 1.45,
  radius 5.0; four warm-white wall task-fill PointLights at local X=+/-2.7, Y=+/-4.6, Z=3.9,
  colour `[0.92, 0.96, 1.0]`, brightness 1.15, radius 3.8 (each with an emissive WallPack fixture
  on the window pier); two entrance SpotLights at `[-/+1.9, -8.72, 4.08]`, direction
  `[0, -0.97, -0.24]`; and two mirrored exit SpotLights at `[-/+1.9, 8.72, 4.08]`, direction
  `[0, 0.97, -0.24]` — all four spots brightness 1.8, range 7.5, 28/48 degree cones. Persisted
  scenario lights and transient selector lights must produce the same thirteen-object inventory.

Relevant proof gates are:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  .\tests\test_cannon_car_wash_assets.py `
  .\tests\test_cannon_car_wash_phase3_lua_contract.py `
  .\tests\test_cannon_car_wash_selector_runtime_contract.py `
  .\tests\test_cannon_car_wash_distribution.py

.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_phase2_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_phase4_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_selector_runtime_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_distribution_live.py
```

For v1.8, the normal release matrix is four serial cold starts on BeamNG.drive (the matrix was
last run end-to-end against engine-reported `0.38.6.0.19963`; the install has since moved through
`0.39.2.1` to `0.39.4.0 build 20972`, so RE-RECORD the engine string from the log banner on the
next run rather than re-copying this one): Phase 2 for
asset/material/light resolution, Phase 4 for the complete scenario lifecycle (which subsumes Phase
3), selector-runtime for the independent free-roam lifecycle and city-bus envelope, and the exact
prebuilt-ZIP smoke. Run the standalone Phase 3 or selector spawn gates only when their narrower
diagnostics are needed. The final archive smoke must verify the locked release hash before and
after copy, install only to an isolated `USER_FOLDER/mods`, discover both the scenario and Props
entry, scan namespaced warnings/errors, and restore support mods byte-for-byte. Read only new log
bytes with `BeamNGLogCursor`; reset the cursor at each owned-process boundary and treat structured
namespaced Lua events plus W/E records as the console evidence. Use RenderView screenshots for
semantic visual inspection and deterministic OOBB, quaternion, ground-contact, effect, light, and
damage assertions as the release authority. Recorded results are evidence, not permission to skip
reruns after a runtime change. Preserve
`telemetry/cannon_car_wash_phase4_results.json` and
`telemetry/cannon_car_wash_selector_results.json` as source-side evidence; refresh them only from a
successful isolated live gate.

The deterministic archive timestamp in `examples/cannon_car_wash/build_distribution.py` is a
per-release cache epoch, not a permanent 1980 value. BeamNG compares Collada source timestamps to
compiled `.cdae` cache entries; bump the fixed epoch whenever a shipped DAE changes, then rebuild
and rerun the exact-ZIP live gate.

The release builder intentionally writes `ZIP_STORED` members. Python's level-9 DEFLATE stream is
not byte-stable across zlib versions: the historical v1.7 payload produced a three-byte/hash
difference between the development runtime and GitHub's Python 3.11/3.13 runners. Do not re-enable DEFLATE
while the SHA-256 is a cross-runtime release lock; any compression-policy change requires proving
identical bytes across the complete CI matrix and rerunning the installed exact-ZIP gate.

Every generator that writes a release-bound text file must also pass `newline="\n"`. Git's Windows
text filter normalized a locally generated CRLF prefab to LF in CI, changing 23 payload bytes even
with stored ZIP members. Before locking a release, compare each `mod/` worktree byte hash with its
Git blob (`git hash-object --no-filters` versus `git rev-parse HEAD:<path>`); the builder, CI checkout,
and installed archive must all consume the same canonical bytes.

## Namespacing and official Repository policy

Consult current official guidance before preparing a public upload:

- Modding Guidelines:
  <https://www.beamng.com/game/support/policies/modding-guidelines/>
- Correctly packing mods:
  <https://documentation.beamng.com/modding/mod-support/mod_packing/>
- Avoiding game/other-mod overwrites:
  <https://documentation.beamng.com/modding/mod-support/overwritting/>
- Vehicle modeling and deformation-ready mesh guidance:
  <https://documentation.beamng.com/modding/vehicle/vehicle_modeling/>
- BeamNG Lua and UI programming entry point:
  <https://documentation.beamng.com/modding/programming/>
- Mod support/common packing errors:
  <https://documentation.beamng.com/modding/mod-support/>
- Material JSON documentation:
  <https://documentation.beamng.com/modding/vehicle/vehicle-art/materials/>
- Official Repository: <https://www.beamng.com/resources/>
- Repository upload guide and 96x96 icon requirement:
  <https://www.beamng.com/threads/uploading-mods-to-the-repository.16555/>
- Installation behavior:
  <https://www.beamng.com/game/support/portal/modifications/installing-mods/>
- BeamNG EULA: <https://www.beamng.com/game/support/policies/eula/>

Repository-facing assets must be globally namespaced. Cannon Car Wash uses the stable
author-plus-mod prefix
`ericrolph_cannon_car_wash_` for file/object basenames, folders where applicable, JBeam part keys and
slots, flexbody/DAE mesh IDs, material JSON root keys, material `name`, material `mapTo`, Lua
extension identifiers, prefab/scene-object names, and trigger names. Do not overwrite stock or
another mod's data. Keep one stable, unique ZIP filename (allowed filename characters only, no
version suffix) across updates, and increment metadata version instead.

A public Repository ZIP is a separate distribution artifact, not a blind ZIP of the development
tree. Opening it must show only the relevant approved BeamNG top-level folders, currently
`vehicles`, `levels`, `art`, `assets`, `lua`, `scripts`, `ui`, `gameplay`, `settings`,
`trackEditor`, and/or `vehicleGroups`. There must be no extra wrapper folder, loose root payload,
unrelated folder, source/evidence file, or `README`. For Cannon Car Wash v1.8, `mod/` is the exact
40-member public-upload tree and its roots must be exactly `art`, `levels`, `lua`, and `vehicles`. Repository
metadata/icon/gallery images are under `repository/`; coordinate handoffs
are under `authoring/`; Phase contracts are under `validation/`; none enter the ZIP. The stable
filename is `cannon_car_wash_ericrolph.zip`; increment the source-side version without renaming it.
Test that ZIP alone from `USER_FOLDER/mods`, not `mods/repo`, because the latter is managed by the
Repository service. Official current guidance wins if local tooling and upload policy differ.

The Repository form assets are separate from the ZIP. Keep `repository/icon.jpg` exactly 96x96,
upload at least two real in-game images through the form's image uploader, and keep both the form
overview and all provenance/evidence files source-side.

Build public artifacts only with the production allowlist builder, then run both archive and exact
live gates:

```powershell
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\build_distribution.py --overwrite
.\.venv\Scripts\python.exe -m pytest -q .\tests\test_cannon_car_wash_distribution.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_distribution_live.py
```

The v1.13 release lock is 46 members (40 runtime files plus six generated mod_info metadata members), 30,423,845 bytes, SHA-256
`147f694752193b74e3f33f75120dae5f59c31e65ed5fa90dbb9b606da109fd13`. It is recorded in
`repository/submission.json` and the exact distribution live test. A runtime-byte or builder-policy
change requires an intentional metadata update, rebuild, new hash lock, and complete distribution
rerun. The complete four-cold-start release matrix passed on the v1.11 payload (2026-07-22) and
refreshed `release_validation`; v1.11.1 changes only the three selector/scenario thumbnail
JPEGs, revalidated with the static suite and the exact prebuilt-ZIP live gate.

Ship only content authored here or content with documented redistribution permission. Never copy
BeamNG proprietary meshes, maps, textures, or JBeam reference files into the repository or mod.
Strip unused files and use the Repository overview rather than an included README.

## JSON/JSONC and generated artifacts

BeamNG JBeam and material files may legally use JSON-with-comments conventions. Generated files in
this repository intentionally use the strict JSON subset: quoted keys, no comments, no trailing
commas, no `NaN`/infinity, and finite numbers. Keep generated outputs strict so Python validators,
canonical hashing, and tests remain deterministic. Conversely, do not run a third-party or stock
JSONC file through `json.loads` and rewrite it merely to normalize formatting; comments may be
meaningful authoring context.

Source-only artifacts include `.blend` files, generators, geometry/selector handoff evidence,
previews used for review, test telemetry, caches, logs, temporary interchange, model weights, and
machine-specific paths. Runtime distribution contains only files the game needs. Rebuild derived
DAE/JBeam/material/manifest outputs from the checked-in generator and measured handoff; do not
silently patch coordinates in one derived file and leave the evidence chain inconsistent.

## Validated local runtimes and safe commands

The validated Blender runtime is the side-by-side 4.5.4 installation below. Do not replace it with
an older or newer Blender merely because another version is installed; change versions only for an
explicit compatibility reason and rerun exporter capability plus geometry evidence tests.

```powershell
$blender454 = 'C:\Users\ericr\Applications\Blender\4.5.4\blender.exe'

# Deterministic full asset rebuild.
# GIANT-PROPS WARNING: behavior/cage PARAMS ship via the handoff this stage
# writes, while LUA_BEHAVIOR code ships fresh from spec.py at build.py time.
# After ANY spec.py constant change, this Blender stage MUST re-run or the
# constant silently stays at its old value (verify: unzip -p dist.zip
# .../runtime.lua | grep <param>). See the prop-authoring guide.
& $blender454 --factory-startup --background `
  --python .\examples\cannon_car_wash\blender\create_cannon_car_wash.py

# Selector-only rebuild from the reviewed .blend, followed by measured JBeam generation.
try {
  $env:CANNON_CAR_WASH_STAGE = 'vehicle_prop'
  & $blender454 .\examples\cannon_car_wash\blender\cannon_car_wash.blend `
    --background --python .\examples\cannon_car_wash\blender\create_cannon_car_wash.py
} finally {
  Remove-Item Env:CANNON_CAR_WASH_STAGE -ErrorAction SilentlyContinue
}
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\build_selector_prop.py
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\sync_scenario_outputs.py
```

All live tests must use this sentinel-isolated profile and run serially. **`BeamNG-0.38.6` in the
path below is a DIRECTORY ID, not a version** — it has outlived two engine updates and is kept only
because other sessions have live paths pointed at it:

```powershell
$env:BEAMNG_MCP_TEST_BEAMNG_HOME = 'E:\SteamLibrary\steamapps\common\BeamNG.drive'
$env:BEAMNG_MCP_TEST_BEAMNG_BINARY = `
  'E:\SteamLibrary\steamapps\common\BeamNG.drive\Bin64\BeamNG.drive.x64.exe'
$env:BEAMNG_MCP_TEST_BEAMNG_USER = `
  'C:\Users\ericr\AppData\Local\beamng-mcp\test-users\BeamNG-0.38.6\current'
```

Never test, install test fixtures, or modify bridge settings in the real profile at
`C:\Users\ericr\AppData\Local\BeamNG\BeamNG.drive\current`. The isolated profile must contain the
`.beamng-mcp-test-user` sentinel. Do not use pytest-xdist or run two live test files concurrently
against one profile. Tests may stop only the BeamNG process they launched and proved they own.

For installation, prefer `mod_validate -> mod_pack -> operator review ->
mod_install(confirm=true)`. `workspace.allow_mod_install` must be explicitly enabled. An overwrite
must produce the service's timestamped recovery backup; report and preserve that backup until the
new package passes clean-profile validation. Do not hand-copy over an installed archive or delete
recovery/quarantine files while diagnosing a failed atomic install. Never park a mod backup or any
other `.zip` anywhere under a profile's `mods/` tree: BeamNG registers every zip below `mods/`
recursively and mounts it, so a stale copy shadows the installed runtime nondeterministically — a
real-profile v1.7 backup zip under `mods/beamng_mcp_backups/` silently reverted Cannon Car Wash to
its pre-pose-preservation repair. Keep backups in a profile-root sibling directory (for example
`beamng-mcp-backups/`), and note that `install` now fails closed when another archive in the mods
tree ships the same vehicle or GE-extension namespace.

Detect that shadowing by what an archive CONTAINS, never by its filename. The sentinel profile held
a `pachinko_tower_ericrolph.zip` shipping the `ericrolph_pachinko_tower` namespace — the mod id
reversed — so every substring check on the mod id missed it while BeamNG mounted it happily. Scan
`mods/**/*.zip` for members under `vehicles/<mod_id>/` or `lua/ge/extensions/<mod_id>/` instead
(`tests/test_giant_props_slope_live.py::_namespace_conflicts`), and fail closed.

### Sloped-terrain gating

A sloped SPOT does not give you a tilted PROP, so measure the attitude, never assume it. Spawning
Boot of Doom at the same steep utah point four ways measured base-plane tilts of 0.93 / 2.35 /
53.19 / 0.00003 degrees — the engine simply does not conform a YAWED spawn to a steep slope, and
that level "slope+yaw" spawn is what produced a physically impossible number in an early revision
of the comment table in `lua_kit.py`. `tests/test_giant_props_slope_live.py` therefore asserts the
tilt SPREAD across the sampled attitudes rather than requiring each sloped spawn to be tilted.

Sample only quiescent states. Comparing part-to-node distances across attitudes is meaningless if
the behaviour is mid-animation, and a matching `behavior_phase` does not prove a matching pose —
behaviours animate within a phase on elapsed time. Requiring two consecutive probes to agree to
2 mm dropped the gate's own worst-case drift from 1.7 mm to 24 um, i.e. most of what looked like
frame error was sampling noise. Props whose parts track free-swinging nodes (pendulum_gauntlet)
are not rigid by construction and cannot be gated this way at all.

### A Lua `local` TABLE binds at its definition point, exactly like a `local function`

`tests/test_giant_props_pack.py::test_local_helpers_defined_before_use` scans for a
`local function` called above its own definition, because that name resolves as a nil GLOBAL and
blows up the first time the path runs. A `local` TABLE has identical semantics and the gate does
not look for it. High Five declared `local TRACKING_PHASES = {...}` beside `behavior.onEnter`,
below the `poseConsole` that reads it: the chunk compiled clean, a lupa syntax gate passed, and it
produced **1200 silenced `behavior_update_failed` errors in a 20 s run** — every one swallowed by
`lua_kit`'s `pcall`, with the only symptom being that the arm stopped advancing past one phase.
Declare shared tables at the top of the behaviour chunk with the other constants, and treat a
headless state-machine gate (`test_high_five_sequence.py`, `test_spin_launch_sequence.py`) as the
thing that actually catches this class — it asserts on the error log, which is the only place a
`pcall`-swallowed fault surfaces.

### Opting a palette into `srgb` must convert the family's DEFAULTS too

`texture_kit.build_set(srgb=True)` re-encodes the colour map, and the palette entry's own colours
must be re-authored to the linear values the engine was already seeing or the whole look shifts by
up to 9x. That much is in `_srgb_encode`'s docstring. What is not: an entry only overrides SOME of
its family's colour parameters, and every one it leaves alone — `slap_pad`'s 0.16 asphalt,
`panel_legend`'s base and ink, `cast_iron`'s grey — is still a raw linear number that the encode
then makes roughly three times LIGHTER. The road patch came back from the first sRGB build as pale
concrete. State every colour-shaped default explicitly in the palette, converted; introspecting
`inspect.signature(FAMILIES[family])` finds them all.

### A clearance claim must sweep the SWEPT GEOMETRY, not a representative edge

High Five's `WRIST_Z` carried the comment "palm bottom clears the road", and it did — the number
was derived from `PALM_WIDTH/2` below the hand axis, and the gate that guarded it asserted on the
same quantity. Both were true and both were beside the point: the DIGITS splay below the palm's
ulnar edge, and the little finger swept **0.42 m under the tarmac** at the flat tilt setting and
0.09 m under at the shipped default, for the whole stroke and while parked. A gate that re-states
the constant's own derivation cannot fail. Sample the actual parts at their actual poses across
the actual control range — and assert the OTHER side of it too, because clearance bought by
lifting the machine is clearance spent on sailing over the thing it is supposed to hit.

### Smooth shading is an ANAESTHETIC: it hides folds, and the cure is not an angle test

High Five's hand was built with a bare `shade_smooth()`, which interpolates the normal across
every edge regardless of angle. Under it, **four separate constructs were folding the surface back
on itself** and not one was visible in a render:

- **Every digit, at both interphalangeal joints.** `DigitSurface` emitted the last spine sample of
  one phalanx and the first of the next at the SAME arc length, so the frame lerp's `span` was zero
  and it returned the upstream direction unchanged — the section frame rotated by the whole flexion
  angle between two adjacent stations. The volar strip stepped **65-123 mm BACKWARD** against a
  station pitch of 21-33 mm. Ten joints, five parts, facets 179.9° apart.
- **`ball_limit` returning `-inf`** where no metacarpal head covered the point, switching the palm's
  web bulge off for a single station and back on: a one-row crater 0.26 m deep.
- **The clamp that used it**, which made the SURFACE track a level set of `ball_limit`. A level set
  does not follow the grid, so walking a column weaves in and out of the binding region — a ragged
  staircase, facets 177° apart. Softening it made it worse; reducing the amplitude under it did
  nothing (226 quads → 170 across a 3× sweep). **The constraint was never sample-time**: the
  amplitude simply asked for more than the envelope had room for, and halving it satisfied the
  envelope by construction with no clamp at all. A limit is for ASSERTING against, not for dragging
  a surface along.
- **Palmar creases narrowed to 0.115 m wide against 0.221 m deep** to make them "cast a shadow
  line". They inverted. And the premise was wrong anyway: smooth shading never erased grooves, only
  arrises — at 0.309 m the crease spans nine faces and reads on its own.

**The obvious repair is a trap.** Switching to `shade_auto_smooth(38°)` like the rest of the pack
made things worse, because an angle test has to DISCOVER which edges are sharp and on an organic
cap its input is undefined: a single-pole dome over a 3.2:1 section runs its two parameter
directions within 1.6° of collinear in one patch, and those quads' face normals are the sign of a
difference of two nearly equal products — noise. The angle test duly split them into a blocky
staircase. A reviewer reported a 179.6° "fold" there that is a **4.1° dihedral** once measured on a
well-formed quad.

So: mark known discontinuities EXPLICITLY (the mould seam is a known column — `edge.smooth = False`
along it) and smooth everything else. Reserve angle tests for well-conditioned meshes like machined
plate.

And gate it on the OUTCOME, in both grid directions, over **every part**: the fold gate written
specifically to catch this covered only the palm, so the worst defect in the mod was structurally
invisible to it and a reviewer found it in a render. Separate degenerate quads from real folds and
bound each, rather than widening one threshold until it catches nothing.

### `_bump`'s `width` argument is a SIGMA, so the feature is six times wider than the number

Same mod, same round. `FLASH_WIDTH_DEG = 8.0` was not an 8° bead: `_bump` is a Gaussian clamped at
3σ, so it spanned **±24°** — 50 of the palm's 192 columns, a 1.75 m arc carrying a 0.067 m rise. A
4% gradient. A hill. Two successive comments on that constant quoted column counts the code does not
produce, because they were reasoned about rather than measured, and the parting line stayed invisible
through four review rounds while its own comment called it "the loudest single signal that the thing
is a CASTING".

Degrees were the wrong unit as well: the palm's columns are 0.072 m of arc and a digit's are 0.030 m,
so one angle cannot mean one feature on both. Size a feature that must survive a discrete grid in
COLUMNS of that grid, and assert its realised width in **metres of prop**.

And when a reviewer prescribes both a target and the knob value that reaches it, **measure the
knob**: "0.85 gives −0.25 m" was justified by geometry that 0.75 actually delivers.

### A ratio that describes an OUTPUT must not be asserted on the INPUT that produces it

High Five's nail colour is authored relative to the skin, and the reference measures the plate at
**1.09x** the foam. A reviewer found the authored base sitting at 0.90x with the comment above it
claiming 1.21x, and the obvious repair was to re-author the base to 1.09x. That repair is wrong, and
a gate written against the palette constants passed on it.

`nail_keratin` **lifts** its base — plate sheen, lunula, striation. A base at 0.90x lands the shipped
map at 1.18x and the rendered plate at 1.07x, which is exactly the reference. Moving the base to
1.09x took the map to 1.41x: 20% too bright, arrived at by making an input equal a figure that
describes an output. The constant was never the thing that was wrong; the comment was.

So gate the artefact. `test_the_nail_holds_its_ratio_to_the_foam` reads the two shipped PNGs and
bounds their measured luminance ratio. Only quantities that are genuinely authored — the nail's hue,
the bed tracking the foam's own base — are checked where they are authored.

The same shape one aisle over, where the ordering really was inverted: the cast iron rendered 5.9x
darker than the matte enamel bolted to it. A note had spotted it and prescribed `srgb: True` — but
**srgb scales both entries, and the fix for a ratio is never a change that scales both sides.** It
shipped inverted for two more rounds. Gate the relation on the quantity that reaches the renderer:
`metallic: 0.7` meant 70% of that albedo was never diffuse, so no change to the base alone could
have been legible.

And when two reviewers disagree, reconcile them before acting. One had measured the RENDERED ratio
at 1.07 and called it exact; the next measured the AUTHORED ratio at 0.90 and called it broken. Both
were right, about different quantities, and taking the second at face value undid the first.

### A feature nobody can photograph is indistinguishable from a feature that is not there

High Five's mould parting line was inert for three review rounds, then real but unfindable for two
more. The second half was not a modelling problem: the seam measured a 42-99 degree crest against a
3 degree median, and every reviewer looking for it came back empty. **The evidence set could not
show it.** A two-part mould splits on the SILHOUETTE, so the line runs along the hand's width axis —
and every camera in the review set looked down the volar/dorsal axis, where a bead is exactly
edge-on and contributes a couple of pixels of outline.

It then took **three attempts** to add a camera that worked, and the two failures are the lesson.

**First: the feature has to be LIT, not merely facing you.** `V_REST` is `(0, 0, 1)` — the thumb
axis points at the sky, so of the seam's two meridians the radial crest faces up and the ulnar
crest faces the ground. The first pair of cameras went to the ulnar edge: **955 of 955 crest
samples lit on the radial side, 0 of 955 on the ulnar**, and 712 of 726 ulnar samples are
self-shadowed by the hand rather than merely Lambert-dark. A correct structural diagnosis, aimed at
the dark half of it.

**Second — and this is the more general one — a swept optimum is worthless if the objective cannot
discriminate.** The replacement bearing was *solved*, not guessed: sweep every azimuth and
elevation, count crest samples that are front-facing and lit, take the maximum. It scored 91%. So
does almost every other bearing, because the metric omitted self-shadowing, framing and
self-occlusion — and, fatally, ORIENTATION. The crest runs along the hand's long axis; the "solved"
camera looked 31 degrees off that axis, straight down the length of the line, with the hand's own
mass stacked in front of it. **82 unoccluded samples against a broadside camera's 571, and a
cross-crest gradient below its own no-bead control.** Optimising a proxy that cannot tell good from
bad returns an arbitrary answer with a confident number attached, which is worse than a guess
because it looks like evidence.

So: score what you actually need — visible AND lit AND unoccluded AND in frame AND oblique to the
feature — and sanity-check the spread of the objective across the search space. A metric that
returns 91% everywhere is not measuring the thing you care about. And keep one lighting model
across the set: a shot lit differently from its siblings is not comparable evidence, which is the
whole point of having a set.

### The part your test suite skips is where the defect goes

`test_digit_tips_converge_on_a_point` asserts that High Five's five digits close on a point, and
documents at length what happens otherwise ("the pole was not a point, it was a segment... a flat
triangular beak"). Nothing asserted it for the **palm**, which has the same kind of cap.

So when the mould seam was found fading toward the palm's pole — the bead was folded into the
section's half-extents and then scaled by the dome, so it thinned exactly where the form rolls away
and the line is all you can see of the edge — the obvious repair was to hold it at full height. That
fixed the dihedral, and opened the palm's pole to a **0.126 m segment** with seam facets at 155-165
degrees, because a bead that keeps its height while the ring collapses is a bead the ring cannot
close around. **All 74 gates passed.** A reviewer found it.

Two habits fall out:

- **Fixing one end of a constraint is the moment to check the other.** "Constant height" and "closes
  on a point" are in direct tension at a pole; the answer was a taper confined to the last 8% of the
  cap, not a choice between them. And note the newly-written gate for the first property — bead
  variation under 2% across the cap — would have *forbidden* the fix for the second if its window
  had not been scoped to the cap body.
- **Look for the asymmetry.** When a suite covers five of six similar parts, the sixth is not
  merely untested, it is where the next defect will be, because every reviewer's eye and every
  author's assumption has been trained on the covered five.

Same shape, twice more in one session: a fold gate that constructed only a `PalmSurface` (so ten
self-intersecting digit joints were structurally invisible to it), and a seam gate that measured its
maximum at ONE station and therefore never reached the cap at all.

### Giant Props releases: `dist` is a RE-ZIP, not a rebuild

`build.py <key> dist` only archives whatever `<mod>/mod/` holds at that instant — it never
regenerates textures or materials. That makes re-cutting a release a live hazard, because
`build.py <key> prop` rewrites cooked `.dds` back to raw `.png` for any mod without a certified
harvest manifest. Running `prop` across the pack and then `dist` silently downgraded seven mods'
textures (whale_geyser 7.2 MB -> 4.8 MB) and would have shipped uncommitted `texture_kit.py` work
in three more. Only 10 of 20 mod trees differed from their shipped zip by runtime.lua alone.

So when landing a shared-runtime fix: snapshot each shipped zip, restore every member that differs
for a reason OTHER than the file you meant to change back into `mod/`, re-cut, then prove
member-by-member that exactly one member moved. `serial.json` bumps only on a real content change,
so a no-op rebuild is idempotent and reproduces the hash — but ONLY below the timestamp clamp
(`packaging._serial_timestamp`, serial <= days since 2026-08-01). Above it the member timestamp
rides the wall clock and every rebuild yields a new sha256. Re-staging `dist/repo_update` or
`dist/repo_submission` is part of the re-cut; a test pins the catapult one.

**`high_five` is the first mod to cross that clamp** — it reached serial 25 on 2026-08-25, i.e. 25
serials against 24 days since 2026-08-01, so its `member_timestamp` now reads the build clock
(`2026-08-25T05:09:30`) instead of a synthetic day. Two practical consequences: a no-op rebuild of
this mod no longer reproduces its sha256, so its lock cannot be verified by re-cutting; and anyone
diffing two builds across a day boundary will see `member_timestamp` move for no content reason.
That is the scheme working as named, not a defect — but it is the point at which hash-stability
stops being a property you can lean on, and the mod that gets there first will not be the last.


### Giant Props: the Collada exporter is not deterministic, and the fix is quantisation

Blender's Collada exporter stamps wall-clock `<created>`/`<modified>` and `Blender User` as the
author, AND jitters the last ULP of normals and UVs between runs of an otherwise identical
generator (positions and topology are exact). `.gitignore` has recorded the second half of that
since 2026-08; it is why `examples/giant_props/*/mod/` is not tracked. The practical effect is that
a mod's `visual.sha256`, its handoff, its build serial and its ZIP lock all move on a rebuild that
changed nothing, which quietly makes the whole evidence chain unfalsifiable.

`colossus_tire`'s generator fixes it locally in `normalise_collada()`: pin the two timestamps and
the author, then re-emit every `<float_array>` at **five decimal places**. Five is measured, not
chosen — at six, 97 values still straddled a rounding boundary and flipped between two runs; at
five, two consecutive full generator runs produce a byte-identical DAE, and five decimals is 0.01
mm on a 28 m prop, 0.0006 degrees on a normal and 26 um of texture on a UV. Any mod that wants a
verifiable lock needs this; doing it in `blender_kit` would invalidate twenty-two other mods'
hashes in one commit, so it is per-mod until someone lands that deliberately.

### Giant Props: `normal_strength` belongs INSIDE the palette's `texture` dict

`prop_builder.ensure_textures` reads it as `entry["texture"]["normal_strength"]`. A
`normal_strength` sitting beside `color`/`roughness` at the entry level is read by nothing at all
and every map is baked at the default 2.0. `colossus_tire` shipped thirteen of them in the wrong
place for three rounds; the symptom was one material (the carcass laminate at the port's cut edge)
measuring 95% of its texels under one degree of slope while every other map in the same mod
reached 25-52 degrees. Measure the shipped `.normal.png` slope distribution when a surface looks
plastic - that is the fastest way to see it.

### Giant Props: colossus_tire's mass is a documented departure

TIRE_MASS is 10,500 kg where an honest 28.168 m carcass would be ~1,923,000 kg (rubber goes as
volume, and the scale factor is 7.0455). It is not taste: it is solved backwards from a
playability requirement - a stock car pushing the inner liner at mu 0.75 has to spin the tire up to
30 km/h in 12-28 s - through the CONTACT-POINT rolling inertia I_cm + M*R^2, not the axle inertia.
Any change to the size code, the mass or the friction has to re-run that solve, and the beam
families rescale with it: every `beamSpring` by the mass ratio and every `beamDamp` by its square
root, which is what keeps the damping ratios where the materials argument put them.


## Prop authoring field guide (hard-won engine behavior)

Everything below was proven live on BeamNG 0.39 during the Cannon Car Wash v1.20-v1.48 arc.
Treat these as engine contracts until a probe proves otherwise.

### TSStatics and collision

- A TSStatic spawned at runtime (`createObject` + `registerObject`) gets **no static collision at
  all** until `be:reloadCollision()` is called — `collisionType` alone does nothing, and
  `castRayStatic` never sees runtime TSStatics even after the reload (verify with a physics
  drop-test or `obj:getWorldBox()`, never with rays). Call `be:reloadCollision()` after creation
  AND after every `setPosRot` pose change you want the collision to follow.
- Use collisionType `"Visible Mesh Final"`, not `"Visible Mesh"` — the latter logs a performance
  warning that live gates treating log warnings as errors will fail on.
- Scenario-placed (prefab) TSStatics get collision at level load; only runtime spawns need the
  reload. Colmesh conventions: only nodes named exactly `Colmesh-N` are collision-only/invisible;
  any other name renders (material-less geometry renders fallback orange).

### Ambient animation clips

- The Collada exporter bakes animation **through `scene.frame_end` only**. When a clip is
  stretched, THREE places must move together: the keyframe positions, the clip `<extra>` end pin,
  and `scene.frame_end`. If frame_end lags, the engine plays the baked prefix and freezes on the
  last pose for the rest of the declared clip (surge-stall). Audit by parsing the DAE's animation
  `<float_array>` input times — the span must equal the declared clip length.
- Ambient clips play ROTATION channels only (translation channels are silently ignored), one
  channel per node, no nested animated empties. Two-keyframe channels need LINEAR interpolation
  set explicitly plus a CYCLES modifier.
- Toggling `playAmbient` RESTARTS the clip from frame zero. Never re-assert it on a cadence; read
  it back first — and the readback returns `"1"` OR `"true"` depending on engine path, so compare
  truthiness, not an exact string.
- `setPosRot` on the animated TSStatic also restarts the clip. Guard transform refreshes with a
  pose-delta check — but keep every SIDE EFFECT the guarded routine performed (mesh-alpha hides,
  etc.); an idempotence guard that skips side effects reintroduces them as bugs.

### Selector-prop double rendering

A jbeam selector prop renders TWICE: the flexbody (vehicle mesh, follows physics) and any separate
animated TSStatic visual. The runtime must hide the flexbody copy (`setMeshAlpha 0`) and RE-ASSERT
that hide every refresh tick — resets and launches silently re-show it, producing offset ghost
geometry.

### Textures and atlases

- BeamNG samples atlas V from the image BOTTOM. Authored DAE v=0 reads the bottom image row.
  Never trust texcoord numbers for orientation — stage a marker texture (colored thirds) and
  probe it live once per atlas.
- Deep mips average the WHOLE texture: thin faces sampling a small UV window inherit surrounding
  colors at grazing angles (mip bleed). Give edge faces an untextured factor material, or pad the
  window generously.
- Alpha-tested cutouts: draw at 2x and LANCZOS-downsample so the alpha threshold cuts through a
  smooth gradient (hard bitmap silhouettes otherwise). Derive normals from the pre-fray artwork.
- Materials must REFERENCE a texture for the engine to cook it; logical names use `.png` with the
  real `/art/shapes/<id>/textures/` root. A file literally named `main.materials.json` under
  `art/` is special-cased by the startup scan — explicit later loads of that filename silently
  no-op; use any other name for material sets the runtime must load itself.
- Level-independent lifecycles (vehicle selector on any map) auto-load NOTHING from art/: ship a
  dedicated materials json next to the shapes and have the runtime `loadJson`+create materials,
  then verify via `scenetree.findObject(materialName)` after registration.
- Backface lighting: luminance-derived micro-normals invert on doubleSided backfaces and shade
  the two sides differently — flatten the normal where both faces must match.

### Lua runtime patterns (GE extensions)

- LuaJIT limit: ~60 upvalues per function. Never scatter top-level `local` constants; group each
  feature into ONE module table (`local Feature = {...}` + `function Feature.x()`).
- Lexical binding: a table method defined ABOVE a `local function helper` silently calls it as a
  nil global (pcall swallows it). Define methods AFTER every helper they call — table-field
  dispatch (`Feature.method(...)`) resolves at call time and is immune.
- Quats compose LEFT-TO-RIGHT: `a * b` applies a THEN b. `model * tilt` tilts about the WORLD
  axis (yaw-broken); `tilt * model` tilts about the model-local axis (yaw-correct). An identity-
  yaw test CANNOT distinguish these — always verify rotation composition on a yawed spawn, via
  `obj:getWorldBox()` spans.
- The vehicle-object rotation (`getRotation`) is stale for driven vehicles (updates on
  spawn/teleport/reset only); derive live headings from the node cloud (`quatFromDir`, which
  differs from the object convention by exactly 180 deg about up).
- That staleness is NOT limited to driven vehicles. An all-`fixed:true` prop that settles onto
  sloped terrain keeps reporting its spawn attitude forever, while the flexbody renders at the
  real nodes. `getPosition` does track; `getRotation` does not. Anything dead-reckoned from the
  object transform therefore drifts by the ROTATION ERROR TIMES THE LEVER ARM, so props with
  geometry far from the ref node fail hardest. Measured on utah 2026-08-24 against a Boot of
  Doom console node 13 m out: flat 0.209 m, a gentle 0.48 m-per-12 m slope 1.03 m, a 7 m-per-12 m
  slope 11.6 m — the gentle case being the shipped-mod bug report (indicator lights floating a
  metre under their own panel). Rebuild the frame from the four refNodes' live positions instead:
  two long baselines give an orthonormal basis, and the error drops to 0-2 mm at every attitude.
  **Never gate this on `smallgrid`** — flat ground is the one condition where the object transform
  and the node cloud agree, so it hides the bug completely.
- A quaternion you build yourself needs CONJUGATING before the engine will accept it. Shepperd's
  matrix-to-quat yields the textbook quat (rotation `q*v*inverse(q)`), but the engine's `q * vec3`
  applies the opposite handedness — the same reversal behind the left-to-right composition rule
  above. Feeding the textbook quat in transposes the rotation: exactly identity on a level spawn,
  silently wrong the moment the prop tilts. The two errors also compose, so fixing one and not the
  other still misses (Boot of Doom: 11.6 m raw, 2.2 m with the wrong conjugate, 18.9 m with the
  wrong composition order, 0.000 m with both right). Solve conventions by measuring every
  candidate against a known node position, not by reasoning about them.
- `vehicle:setOriginalTransform(x,y,z,rx,ry,rz,rw)` is the official reset-home setter; every
  `setPositionRotation` re-homes the vehicle as a side effect.
- Trigger tooltips print unicode escapes literally — ASCII only in input-action titles.

### Interactive dashboard-style buttons on a prop

The selector prop IS a vehicle, so vehicle triggers work: `triggers2` rows in the jbeam (anchored
to three cage nodes forming a local frame; add dedicated anchor nodes at the panel with small
mass), `triggerEventLinks2` mapping `action0` to input actions, an `input_actions.json` with
ASCII titles, and a vehicle-side controller whose `onGameplayEvent` forwards presses to the GE
runtime via `obj:queueGameEngineLua`. Trigger boxes land offset from their anchor nodes by a
constant few cm — measure the live centers once (vlua reads its trigger table; ship the measured
correction into the node positions). Walking-mode hover highlights confirm the wiring.

### Zones and occupancy

- `Contains` + bounding-box trigger tests drop a MOVING vehicle the moment its bbox pokes past
  the zone: entries read late, exits read early. For lifecycle decisions (keep machinery running
  while anyone is inside) maintain a CENTER-in-envelope positional sweep over the full structure,
  separate from service-semantics zones, plus a few seconds of off-grace.
- Positional sweeps must also drop occupants that vanish without exit events (deleted vehicles).

### Packaging and caches

- ZIP_EPOCH must postdate any plausible cache mtime on the target machine (stamp next-day noon).
  The game prefers whichever of cache/zip is newer; a stale epoch silently serves old caches.
- Rebuild the distribution after EVERY tree change including version stamps (2-byte drift fails
  determinism checks). Verify shipped content by CONTENT HASH of zip members, never by dims or
  counts alone.
- Derived files are never edit targets: the selector `main.materials.json` derives from the
  scenario materials; the selector thumbnails (`default.jpg`, `standard.jpg`) derive from the
  scenario thumbnail jpg. Edit the source, rebuild, verify the derived copy changed.
- Stray real directories under the user profile's `mods/` (backup folders etc.) shadow textures
  via the engine's find-by-name fallback: keep backups OUTSIDE `mods/`. Diagnose resolution with
  `FS:getFileRealPath` / `FS:findFiles`.

### Diagnosis instruments (in preference order)

**The pipeline-stage doctrine (2026-08-08, the "green area" hunt).** What the player sees is
the END of a pipeline: generator source → exported DAE → materials.json → engine cook (.cdae)
→ flexbody NODE SKINNING → rasterization (exposure/culling). Each stage can break
independently, and **a pass at stage N proves nothing about stage N+1**. The see-through deck
ring survived a clean source probe, a clean shipped-DAE raycast (16k rays), clean materials,
a clean log, and a clean cook — because the defect lived in the skinning stage, which no
mesh-level instrument touches. When the player films something your probes call closed, do
not re-run the passing instrument harder; step DOWN the pipeline to the first stage you have
not yet tested, and test THAT stage in isolation. The full-stack instrument (normal-exposure
in-game screenshot, item 2 below) reproduces first; the per-stage instruments then bisect.

Also: the player annotates screenshots with hand-painted marker (magenta rings, green fills).
Before theorizing about a striking color, check whether it is annotation or render — nothing
in a prop's palette may even contain that color. One question ("is the green your marker or
in-game?") is cheaper than a wrong build cycle.

1. The player's own `beamng.log` (`<profile>/beamng.log`): the runtime's emitted events land
   there — read it before theorizing about behavior on the player's machine.
2. **Normal-exposure in-game screenshots — the full-stack reproduction instrument.** Attach to
   the running test rig (`BeamNGpy(..., quit_on_close=False)` then `open(launch=False)`), then:
   `commands.setFreeCamera(); core_camera.setPosRot(0, px,py,pz, qx,qy,qz,qw)` (quat via
   `quatFromDir((target-pos):normalized(), vec3(0,0,1))`), step ~30 frames, then
   `screenshot.doScreenshot(nil, nil, 'screenshots/<name>', 'png')`. This uses the game's real
   tonemapping — it sees exactly what the player sees. The fixed-exposure `renderViews` path
   CANNOT adjudicate visibility questions (a hole to bright sky and sunlit steel are both
   pure white, at any ToD); use renderViews only for rough composition checks in its ToD
   windows (~0.75 sunrise / ~0.845 dusk). The prop's runtime visual renders authored (x, y)
   at world (-x, -y) — flip probe camera coordinates.
3. **The TSStatic A/B fork — mesh vs skinning.** For "exists in the DAE but not on screen":
   spawn the SAME DAE as a plain TSStatic next to the prop (createObject('TSStatic');
   setField shapeName/position/collisionType='None'; registerObject; add to MissionGroup —
   copy the runtime's own recipe). If the static renders what the flexbody drops, the
   mesh/materials/cook are innocent and the cage NODE BINDING is the culprit (look for
   coincident nodes first; the invisible band's boundary is the nearest-node Voronoi edge —
   a ragged arc at the midpoint between node rings is the signature). Small separate meshes
   (lane tori) surviving inside a dead band is another skinning tell: they bound to different
   nodes.
4. Player screen recordings: extract frames (`ffmpeg -vf fps=2`) and compute consecutive-frame
   mean-abs diffs — periodicity in the numbers identifies clip-length effects instantly.
5. Marker textures (colored regions, one cook) for any UV/orientation question.
6. `obj:getWorldBox()` spans for any rotation/pose question (rays can't see runtime TSStatics).
7. Physics drop-tests for collision questions.
8. Headless-Blender raycasts over the BUILT scene. `exec` the generator with its trailing
   `main()` stripped, call `build_visual()`/`build_parts()`, then `scene.ray_cast()` on a grid.
   This measures what actually got built rather than what the source appears to say, and it
   answers "is there a hole / a step / a lip" in seconds. Enumerate **every** hit down a column
   (re-cast from just under each hit), never just the topmost: a single-hit sample steps clean
   over near-vertical geometry and reports phantom gaps. Exclude ceiling objects by name or
   start the ray below them.
   **For VISUAL holes the raycast MUST be cull-aware or it lies.** A plain `ray_cast` counts
   backface-culled faces as solid, so every "is there a hole" probe kept declaring surfaces
   closed while the player kept filming see-through gaps (this misled more than a dozen fix
   rounds). Walk the ray: on each hit, if `normal.dot(direction) > 0` and the material is not
   doubleSided, step 2 mm past the hit and continue — that face draws nothing in-engine. Also
   sweep sightline FANS from player-plausible eye positions (low, oblique, in doorways), not
   just vertical columns: the gaps live at grazing angles.
9. Artifact-level checks on the SHIPPED files, not just the source: import the zip's DAE into
   headless Blender and re-run the raycast map against it (closes the source-vs-artifact gap);
   and diff per-material triangle counts (`grep -o 'material="..." count="[0-9]*"' *.dae`) —
   a feature removal or loss shows as an exact count delta (the oculus glass removal was
   precisely −720 obs_glass triangles). The static visual is JOINED into one mesh at export,
   so object names do NOT survive into the DAE — grep for names proves nothing.

**A visual-fix round is not done until a normal-exposure in-game screenshot from the player's
own camera class shows the fix.** The functional gate drives on COLLISION and its renderViews
blow out — a fully invisible deck passes all four phases. Mesh probes + gate green is
necessary, never sufficient, for anything the player will look at.

### Drivable surfaces must be authored as surfaces, not as renders

The centrifuge deck was tuned entirely for zoom renders and shipped as a tyre trap. Rules that
came out of it (2026-08-07):

- **Cap relief on anything a car drives on at about ±0.02 m.** Seam shutlines authored at 0.13 m
  deep and 0.15 m wide are narrower than a contact patch and deeper than a sidewall; 32 per lap
  destroyed the car. A shutline only has to out-shadow its own chamfer to read. Measure it: sweep
  three samples 0.8 m apart across a wheel track and report the worst spread. 197 mm was the
  bug; 35 mm is fine.
- **A straight-ended box can never meet a circular lip.** A box ends on a line, a bowl ends on an
  arc, so the corners leave a crescent of open air and the centre leaves a step. Build entry
  ramps as a function of RADIUS using the deck's own `cone_z`, so the inner edge lands on the
  lip arc at the lip's exact height — flush by construction, not by tuning.
- **Inlays that run past the surface they are inlaid into become tongues.** Spokes drawn to
  r 15.8 looked right over solid bank and hung over the void in the doorway sector as a 0.31 m
  step. Clamp inlays to the surface that carries them.
- **Sampling a curve to an intermediate parameter silently truncates the collision cage.** The
  cage profile was sampled to `BANK_S_HAZARD` (0.779) instead of s = 1.0, so the top 1.2 m of
  visible banked wall had no collision anywhere around the drum. Always sample generator curves
  over their full domain and assert the cage's outermost point equals the visual's.
- **A material that is looked up and never assigned means a missing object.** `bank_hazard` sat
  assigned-and-unused in `build()` — the band it belonged to had never been swept, leaving a
  0.95 m annular hole. Grep for palette keys with no `assign_material` consumer.
- **Swept profiles must be monotonic in radius.** A profile that ran 16.0 then back to 15.758
  folded the surface through itself at the doorway. Assert monotonicity at build time.
- **Never let a runtime-posed part be the only thing keeping the entrance open.** Interlock it:
  any vehicle in the corridor pins the door open regardless of state machine phase.
- **A raised deck needs an outer face and a back face, or it renders as a floating disc.** The
  cone sat 2.48 m over the concourse with no skirt built down its edge and a single-sided
  material, so from any eye below the deck plane the track vanished, the spoke inlays and lane
  lines floated in mid-air, and the pale textured ground apron filled the frame. The collision
  cage had had a skirt at that radius the whole time — mesh and physics disagreed about whether
  the dish had sides. Check both: a horizontal ray sweep outward from under the deck should hit
  something at every azimuth.
- **Elevated ramps need their underside carried to grade.** A constant-thickness plank leaves a
  floor-to-deck hole under the doorway that cars drop into. Make the underside `min(z - t, 0)`
  so the ramp is an embankment.
- **A constant-width slab through a flared portal leaves wedge trenches (2026-08-08).** The
  vomitory corridor is a 26° wedge (jambs at az 257/283) but the ramp is a parallel-sided
  6.7 m solid, so a grade-deep open trench ran between each ramp flank and its jamb — ~0.1 m
  at the skirt line growing to ~1.1 m at the drum skin. From the bank you looked down it at
  raw ground; from grade you sighted up past the deck to the gantry. Whenever a straight
  element passes through a radial/flared opening, FILL the flanks to the jamb planes (flush
  with the deck, small rebate against z-fighting, tucked past the jamb so no coplanar edge)
  — and give the fill collision quads, or a straying wheel sinks through a floor it can see.
  The probe invariant that catches the whole class: a top-down cull-aware map over the drum
  footprint must find ZERO samples whose first drawn surface is at ground level.
- **Pitched liner boxes poke through curved walls at their high corners (2026-08-08).** The
  vomitory wall/cap boxes are pitched up the tunnel angle, so their inner-end TOP corners
  reached z 4.7–5.0 where the bank face has receded to larger radius — pale steel nubs
  sticking out of the banked wall beside the doorway (the player circled them in green).
  Checking the box's *center* height is not enough; check its corners. The exact assert:
  every liner vertex must satisfy `r >= bank_face_r(z) - 0.02` unless it is inside the
  doorway window BELOW the header. Fix by pulling the boxes back along the tunnel, not by
  shaving height (which ruins the liner everywhere else).
- **`collision: false` on a node does not disarm a face.** Collision triangles are emitted
  independently of node flags, so a "disabled" ring still presents a solid surface. Skip the
  QUADS, not just the nodes.
- **Blender does not backface-cull; BeamNG does. Headless renders CANNOT catch an inside-out
  mesh.** Two hand-built `from_pydata` meshes shipped inverted in one session — the entry ramp
  and the door leaf — and both rendered perfectly in every Blender check while being invisible
  in game (the player filmed a car driving on thin air, and a "closed" door that still read as
  a hole). Two defences, use both:
  1. Assert on winding at build time. For a closed solid, run
     `bmesh.ops.recalc_face_normals` and let bmesh orient it. For an OPEN surface (a door leaf,
     a bank sweep) recalc has no "outside" to work from — decide by the mean normal instead:
     `if sum(p.normal.z for p in mesh.polygons) < 0: mesh.flip_normals()`.
  2. Render with culling forced on to match the engine:
     `for m in bpy.data.materials: m.use_backface_culling = m.name not in double_sided_set`.
     Anything that vanishes in that render vanishes in game.
  Deriving a quad's winding by hand is error-prone: `(a, a+1, b+1, b)` walking +y then +x has a
  cross product of **−Z**, not +Z. Three of the ramp's six windings were wrong.
  3. **Policy (2026-08-07): every palette entry is forced `double_sided` in spec.py.** After an
     invisible ramp, an invisible door leaf, and a see-through under-bank cavity each shipped
     despite per-surface fixes, the winding question was retired wholesale — a post-processing
     loop after PALETTE sets `double_sided: True` on everything. The overdraw on one prop is
     negligible. New interior volumes (service cavities under raised decks) still need their
     openings walled off (portal jambs), because double-siding makes a cavity's walls visible
     but not *intentional-looking*.
- **An opening and the thing that fills it must be cut from the same number.** The bank's
  doorway was `skip_az=(253, 287)` while the door leaf swept `257..283` and the cage's
  `GARAGE_SEGMENTS` covered `257.1..282.9` — three different windows, leaving a lit slot at each
  jamb. Also note `_swept_mesh` decides per FACE MIDPOINT, so the real hole is up to one face
  wider than its nominal window: give the filler a couple of degrees of overlap and let the
  inset hide it.
- **An "open when idle" interlock must test position, not just presence.** Pinning the door open
  for any vehicle within 26° of the doorway also matched a car already circulating the deck, so
  every lap re-opened it and it never sealed. Gate on being outboard of the lip.
- **Coincident cage nodes make FLEXBODY vertex bands invisible (2026-08-08).** The engine
  skins each visual vertex to a local triad of nearby cage nodes; a triad containing two
  coincident nodes is a degenerate basis and every vertex bound to it collapses — its
  triangles simply do not draw. The perimeter skirt built its own ring at (r 15.2, z 2.48),
  exactly on top of the cone's rim ring (28 duplicate pairs), so the whole outer deck band
  from the inter-ring midpoint outward (r ~13.4..15.2, ragged boundary) was invisible IN
  GAME for three days while every mesh-level probe, DAE raycast, and materials check passed —
  the player's "green area". Two rules: (1) ALIAS shared rings, never rebuild them (the bank
  already did this; the skirt didn't), and build_cage now asserts no two nodes sit within
  1 cm. (2) The decisive instrument for "exists in DAE but not on screen" is the A/B fork:
  spawn the same DAE as a plain TSStatic next to the prop — if the static renders what the
  flexbody drops, the mesh/cook is innocent and the NODE BINDING is the culprit. renderViews
  cannot judge this (fixed exposure blows out daylight); use `screenshot.doScreenshot` with
  a free camera for normal tonemapping.
- **Behavior PARAMS ship via the handoff; behavior CODE ships fresh (2026-08-08).** Editing a
  value in spec.py's behavior params dict and running `build.py all` does NOT change the shipped
  runtime: the params table in runtime.lua is serialized from `authoring/*.handoff.json`, which
  only the BLENDER stage rewrites — while LUA_BEHAVIOR code IS read fresh from spec.py at
  `build.py` time. So a code edit and a constant edit made together can ship half-applied (the
  sampleLost logic landed in build 53; the stage_hold change silently did not until the Blender
  stage re-ran in build 55). After ANY spec.py params change, re-run the Blender generator, and
  verify the constant inside the zip (`unzip -p ... runtime.lua | grep <param>`) before testing.
- **The corollary bites in the other direction too: `mod/**/*.lua` are GENERATED (2026-08-12).**
  Both the GE runtime and the vehicle bootstrap under `mod/` are emitted from spec.py's
  `LUA_BEHAVIOR` / `VEHICLE_LUA_EXTRA` templates at `build.py` time. Editing the mod-tree lua
  files directly WORKS until the next build, then silently vanishes: the b145 centrifuge zip
  shipped without its entire shutdown-audio wiring because the edits sat in the generated files
  and the geometry rebuild regenerated them (caught only by grepping the generated file for a
  new symbol after building). Same family as the car-wash "selector materials.json is DERIVED"
  law. Edit the spec.py template, rebuild, then grep the generated file to confirm the symbol
  arrived.
- **Stale unpacked stagings shadow the fresh build in probes.** Probes that extract the dist
  zip into `mods/unpacked/<unique>/` and never clean up leave N copies of the same mod id; the
  engine loads one of the OLD ones. Symptom: a tuning change measures IDENTICAL results twice.
  Delete prior stagings before extracting (same family as the mods/-backup texture shadowing
  above).
- **Lingering test-rig instances attach instead of launching.** `quit_on_close=False` leaves
  the game running after a probe exits; the next `bng.open(launch=True)` on the same port
  silently ATTACHES to it — with the old mod list still mounted. Two symptoms seen the same
  day: "Model not found" after deleting the stagings the running instance had mounted, and
  measurements that quietly ran against the previous build. Before any launch-fresh probe,
  kill test instances ONLY (never the player's real game):
  `Get-CimInstance Win32_Process -Filter "Name = 'BeamNG.drive.x64.exe'" |
   Where-Object { $_.CommandLine -like '*test-users*' } | Stop-Process`. The flip side is
  useful on purpose: a deliberately-kept instance plus `open(launch=False)` gives instant
  re-attach for camera/screenshot work without a 3-minute boot.
- **Cage constants derived half from spec and half from literals will drift.** `cone_radii`
  ended in a hardcoded `16.0` while its height function divided by `spec.CONE_OUTER_R` (15.2),
  silently *extrapolating* the ring 0.8 m past the visual rim into an invisible curb. spec.py
  even carried a comment saying that exact mismatch had been fixed — the constants were
  corrected and the cage literal was not. Derive every cage dimension from spec or from the
  component's own function; never retype a number.

**`dtSim` in a prop's `behavior.update` is NOT wall seconds — measured ~3x faster.** Every
timer that accumulates `dtSim` therefore fires ~3x early: a nominal 15 s release window ran
5.0 s, and `stage_hold_seconds` had to be calibrated (5.5 -> 29 s ladder, 11.5 -> 51 s) instead
of derived. Do not reason about these constants in seconds — measure the wall-clock result and
scale. State the real duration in the comment next to the tunable so the next reader is not
misled by the name.
**A mid-sequence abort can make the calibration itself fiction (2026-08-08).** The ladder's
"tops out at ~60 s" number had only ever been EXTRAPOLATED, because an empty-bowl failsafe
aborted every run at the ejection (~stage 7-10) — the top rung had never once been reached in
any measurement. When a timed sequence has an early-exit path, either measure with that path
disabled or fix the behavior so the sequence completes (here the player wanted the latter: the
crescendo now finishes for an empty drum). First true end-to-end measurement moved the constant
from 14.0 to 13.0 (t500: 61.0 s -> 57.5 s target). The affine model that survived measurement:
`t500 = 9.67 + (n_holds/3) * stage_hold` sim-seconds.

Vehicle damage is available to the GE side as `map.objects[vehId].damage` — the vehicle Lua
publishes `math.floor(beamstate.damage)` every frame (`vehicle/mapmgr.lua`). Scale reference
from shipped code: traffic respawns at >=500, freeform delivery calls >1000 notable and >5000
heavy. Useful for "did the sample survive" gates.

`addSubjectVelocity` -> `applyClusterVelocityScaleAdd(refNode, 1, ...)` applies uniformly to
the whole node cluster, so it changes velocity without deforming the body. To PIN a vehicle
against high centripetal load, damp its outward radial velocity component (a velocity
constraint) rather than raising a positional spring — a spring stiff enough for ~116 g injects
~19 m/s in a single frame, which reads as a teleport and shreds the car.

Probe hygiene: `beamngpy`'s `Vehicle.control()` only writes the fields you name, so a
`brake=1.0` from an earlier phase persists and the next phase reports "the car cannot move".
Clear `brake`/`parkingbrake` explicitly when starting a new driving phase. Background Bash
resets cwd to the home directory — always invoke `.venv/Scripts/python.exe` by absolute path
or the run dies with "No such file or directory" after the game has already launched.

### Grades, ramps and the slow-speed stall class (centrifuge round 14, 2026-08-08)

- **Never blend two HEIGHT datums to round a crest.** A smoothstep between an extrapolated
  deck plane and an approach plane must out-dive the steeper one mid-window: two ~15–16%
  surfaces blended into a measured ~23% peak, and an automatic at creep throttle stalls on
  23% and rolls back (the player's "sometimes get hung up at slow speeds" — momentum masks
  it at normal speeds). Interpolate the SLOPE between the end grades and integrate: the
  grade is then monotone and never exceeds either end anywhere.
- **Stall discriminator for entry probes**: on a detected stall, floor the throttle for
  4 s. "Escaped at WOT" = marginal grade (fix the surface); "did not move" = hard geometry
  (find the obstruction). Also run a CRAWL line (~1.1 m/s): it finds grade problems the
  2 m/s lines lottery through, and centre-line failures acquit side-specific theories.
- A wall-hug line jamming at a doorway throat is physics, not a defect, when
  car-half-width + offset exceeds the jamb line — check the arithmetic before hunting
  invisible walls.
- **Collision plates must never outreach their visual** — and a square plate under a round
  pad must INSCRIBE it (half-extent ≤ r/√2) or its corners are an invisible shelf on bare
  terrain. When a visual footprint shrinks, shrink the plate in the same commit.

### Probe placement and camera truths (2026-08-08)

- **Spawn-per-run is the only placement primitive that never lied.** Raw
  `setPositionRotation` on a handbraked softbody snapped it 5 km; `beamngpy` `teleport`
  (safeTeleport) landed 35 m off target and tripped the position assert. Spawning a fresh
  vehicle per run costs ~15 s and always lands where asked. Despawn between runs.
- **Zone triggers fire on CROSSINGS**: a car spawned INSIDE a trigger box never enters
  occupancy — machines that arm on zone entry can only be armed by driving in. (Useful
  inversely: spawning a car inside the bowl parks an inert object for purge-style tests.)
- **Screenshot cameras take WORLD coords; the prop renders flipped** (authored (x,y) at
  world (−x,−y), the standing MODEL_ALIGNMENT_ROTATION). The first console close-ups
  photographed the empty concourse on the opposite side of the building.
- **TaskStop kills the whole process tree** — a probe python's game dies with it, and the
  next `open(launch=False)` attach fails. Stop probes by letting them exit, and treat a
  surviving instance (quit_on_close=False + python self-exit) as the only attachable case.

### Night, emissives and text (2026-08-08)

- **`emissiveFactor` needs HDR-strength values to read at night.** 0.1–0.5 renders BLACK
  under the night tonemap (the "glowing" facade was pitch dark); ~1.0 reads as a lamp,
  ~1.6–1.8 as a backlit sign. (UNRESOLVED, flagged 2026-08-15: this bullet says emissive
  worked, the round-15 bullet says it never did, and the round-16 ledger below says which
  material shapes do and do not emit. Nobody recorded WHICH material these three readings
  came from, so it cannot be reconciled by reading — it needs the array shape of that
  material. Treat the round-16 nits ladder as the calibrated scale and this as folklore.)
  Emissive materials self-glow but cast nothing — for actual
  illumination create a `PointLight` from `behavior.init` via the framework's
  `createObject` + `registerInMission` recipe and store it in `state.effects` so
  `cleanupInstallation` deletes it with everything else.
- **Text on a wide panel via a square texture must be drawn at the PANEL'S aspect and then
  stretched into the square** (PIL: render into a strip at face aspect, `resize` to
  size×size). Drawing straight into the square and letting UVs squash it 9:1 produced an
  unreadable hairline. Backlit-sign trick with zero extra plumbing: light diffuser colour
  map + dark silhouette letters + uniform HDR emissive.
- Shared texture families take OPT-IN detail params (e.g. concrete `fine`/`striate`) so
  other mods stay byte-identical; the legacy texel-scale pits read as "Minecraft chips"
  once metric UVs magnify them — kill the chunk scale, add micro grain + soft pores +
  metre-scale stains instead, and raise that material's `size` to 1024.
- **Reverse-lit channel lettering recipe**: Blender FONT curve → mesh, extrude ~0.026
  local (fixed-depth remap so the fit scale cannot thin it), fit-scale to the band, wrap
  each vertex onto the arc (glyph x → azimuth, extrude → radius), float ~35 mm off a
  plain even-glow diffuser (texture family with empty text — do NOT also print letters:
  PIL and Blender kern differently and halo zones will misalign). Two traps: the model's
  world transform is a 180° ROTATION (handedness-preserving), so arc text runs with
  INCREASING azimuth for the authored −y viewer — a "compensating" mirror ships the sign
  backwards; and any reflection-like vertex remap flips face windings — glyph solids are
  closed, so recalc_face_normals after wrapping.

### Round-15 hard rules: glow, triggers, tire slicers, phys safety (2026-08-08)

- **~~Vehicle-material emissive is INERT in this pipeline — all of it.~~ RETIRED
  2026-08-15 — the observation was real, the diagnosis was wrong.** Every variant
  tried across builds 63–69 did render dead black, and every glow anyone perceived
  on the centrifuge really was the bowl PointLight's wash on white surfaces — the
  midnight capture of `19 CFUGE AMBER` (beacon_amber verbatim) reads sRGB 0.0 with
  the lights off and 107 with them on, which is that story in two frames. But the
  cause was never the emissive path. It was a FOUR-element `emissiveFactor`; see
  the round-16/17 ledger below for the measurement (round 4 re-proved it on an
  adjacent same-row pair: 3 components sRGB 255.0, 4 components sRGB 0.0). Real light objects are still the
  right mechanism for anything that must ILLUMINATE (emissive self-glows and casts
  nothing), and the rest of this bullet stands: reverse-lit sign recipe = lights
  INSIDE the channel-letter standoff gap, panel washes bright at grazing range,
  letter faces point away and stay dark; an emissive-look disc recessed into a can
  reads dark from every angle a driver has — mount lenses near-flush AND light the
  area.
- **materials.json audits: keys sort `Stages` before `name`.** An `emissiveFactor`
  hit belongs to the material whose `name` appears BELOW it, not above. Two rounds
  have now false-alarmed on this exact misread.
- **triggers2 basis is per-trigger: idX/idY minus idRef.** Shared frame nodes give
  every off-row button a skewed, TRANSLATED hitbox (hover ghost floating half a cap
  away). Author one orthonormal frame pair per button (+0.4 x / +0.4 z off its own
  anchor). And the whole click box must live OUTSIDE collision: anchors proud of the
  cap face, cage front pulled behind the plate — a collision plane in front of the
  buttons swallows the mouse ray and hover never fires.
- **Panel labels: engraved-legend texture family with authored 0..1 face UVs**, label
  (u,v) computed from the same spec table that places the caps, drawn at the plate's
  true aspect then stretched square (marquee lesson). bk.add_box UVs are metric — a
  legend needs a hand-unwrapped face.
- **Tire slicers: floor collision must run wall-to-wall wherever the visuals say
  "drivable".** A visual shoulder with no collision beneath is a slot; its far side —
  a zero-thickness quad edge (skirt/bank doorway) — is a knife at sidewall height.
  Both player deflations were exactly this. Fix pattern: guard walls ON the visual
  jamb plane (collision matches visuals), corner wedges folding onto the adjacent
  wall so mouth corners deflect, and outer floor rails on the SAME surface authority
  the visual samples. End the strip by REUSING the neighbouring wall's nodes — a new
  node 4 cm from an old one is the flexbody coincident-triad trap.
- **Deflation gauntlet is a standard gate now**: off-center (±2.35) + wall-scrape
  entries at crawl and 6 m/s, polling per-wheel `wheels.wheels[i].isTireDeflated`
  into an electrics value. Center-only runs pass while off-center slices — the
  lottery the player always loses. (beamngpy: the Electrics sensor is NOT
  auto-attached; attach it or KeyError.)
- **Phys-explosion watchdog (stretched-black-polygon lines)**: GE-side, no VE
  plumbing — `vehicle:getSpawnWorldOOBB():getHalfExtents()` (API confirmed live; the round that
  wrote this named "0.38.6" from the PROFILE DIRECTORY, so the correct statement is "confirmed live
  on the install of the day" — it has not been re-run since the engine moved to 0.39.4.0 build
  20972) balloons by hundreds of metres when one node explodes; quarantine the
  sample (drop it from the field N seconds, toast once) so the machine stops feeding
  a solver that is already losing the vehicle. Everything behind a `safety_enabled`
  master switch with per-threshold tunables = selectively adjustable, one-flag
  revert. Context that made this cheap: the spin field was already insideBowl-gated,
  per-frame dv-capped, and applied to the REF-NODE CLUSTER only, so detached debris
  never receives field energy.
- **Curved parts on flexbodies: facet density is the honest lever.** The
  join-and-export path flattens Blender smooth-shading marks (auto-smooth modifiers
  don't survive `object.join()`), so a "smooth" dome still renders faceted in-game.
  Double segments (drums 32→64+, dome bands az 128 × 20 rows) before chasing normal
  pipelines.
- **Continuous machine ramps: slew per-stage, not per-rate.** A constant RPM/s slew
  crosses each rung gap in seconds then sits flat — "chunky". Rate =
  (target − prev) / (hold × fill) spreads the climb across the whole hold window;
  hold clock runs from stage ENTRY. Re-measure t500 whenever the interval model
  changes.
- **Deterministic mode makes byte-identical replays — use that as an instrument.**
  Same spawn sequence + set_deterministic ⇒ crumbs identical to the centimetre. If a
  collision change ships and the failure replay is STILL identical, either the
  content did not load (check the staged jbeam sha vs the repo, and the cdae cache
  mtimes in temp/vehicles/<name>/) or the changed geometry was never the blocker.
  Both happened in round 15. Related rig traps: killing rigs by CommandLine filter
  sometimes leaves the MAIN process alive while its CEF children die — and a
  surviving main still listening on the probe port silently replays the OLD build
  for the entire next probe. Verify `total: 0` before relaunching, and rotate ports.
- **RESOLVED (round 15 finale, builds 72–73) — the mouth pin, named exactly.**
  The blend window of the round-14 crest curve starts at RAMP_R_IN 13.4 — INSIDE
  the physical lip (15.2) — so the softened slope bulged the approach 9–10 cm
  above the dish over the last 1.6 m and the collision tongue ended in an exposed
  cross-edge (jbeam: tunnel_1_0 z 2.33 vs cone 2.24). Slow front wheels dropped
  off it (sidewall raked the edge = the FR deflations), the sagging corner hooked
  the belly, WOT-proof high-centre. Fix: cap the curve's excess over the dish to
  15 mm inside the lip (create: ramp_surface_z inboard branch) — outer grades,
  crest, toe, plaza untouched; the lip gains a ~6° knuckle (breakover ~11°).
  SECOND find: build 64's "shrail" outer rails duplicated a LEGACY `shoulder_i_j`
  cage strip that already ran wall-to-wall — two strips at ±3–4 cm interleave =
  a W-canyon across x 3.5–4.9 that itself popped tires deterministically at the
  plaza (removed in 73; ONE surface, ONE authority). The r15b "every off-center
  entry deflated" evidence that motivated the rails was pure spin-field
  contamination (a prior run's overshoot armed the machine). Diagnosis toolkit
  that cracked it: measured ref-node offset (etk800 ≈ 0.205 m on flat ground —
  never guess it), analytic jbeam triangle/node dumps in a world-space box (the
  jbeam bakes the 180° flip: authored (x,y) → jbeam (−x,−y)), drive-in creep +
  silhouette screenshots (spawns inside the prop's footprint get RELOCATED by
  the game — always drive in). Also: PART_SPECS never serialized the `collision`
  flag, so part TSStatics were collisionType None all along — the door leaf
  never had physics; raceway sealing is the hold system, period.
- **CLOSED (build 76): the transition is warp-free at every speed and line.**
  The last catch was MESH TOPOLOGY, not the height formula: straight
  cross-lane cage rows sampling the RADIAL blend warp ~20 cm centre-to-rail
  inside the mouth, and a creeping off-centre car straddles that diagonal and
  levers a sidewall into the seams (the mirrored asymmetry in outcomes was the
  car's own drivetrain bias, not the cage — mirror-dump proved the flanks
  identical). Fix = the ARC TONGUE: constant-radius rows (13.6→16.0; use
  15.25/15.65, a row at exactly r 15.2 drops its centre node onto cone_3_21
  and trips the coincident-node assert) × 3 columns — every node in a row at
  ONE z, zero warp by construction, quads only, stitched to the straight
  stations at y 16.125. Verify entrances with the FULL 13-line gauntlet:
  crawls/6 m/s/scrapes stopping at the lip PLUS full-speed drive-THROUGHS
  (8/12 m/s, three lines) PLUS 1.6 m/s off-centre creep-throughs — the
  lip-stopping runs alone shipped two knuckle regressions. Build-chain traps:
  a TaskStop'd build can leave an orphan blender.exe whose late writes corrupt
  the NEXT build's handoff ("visual Collada changed after Blender handoff
  extraction" → kill orphans, rerun); and grep the blender log for Traceback
  before packing — build_cage asserts fail the stage while Blender still
  exits 0.
- **CLOSED (build 79): dragged samples cross the doorway clean — the wall-in-
  orbit law.** The player's "car crashes at the entrance when the RPMs drag it"
  was the round-15 jamb GUARD WALLS (panes z 2.4–5.3 at r 15.2–16.8 + corner
  wedges at r 15.2): a sample circulating at the ~15.2 hold line broadsided
  one every doorway pass — all 4 tires by t=10 s at 30 RPM, launched 9 m.
  Entry gauntlets NEVER catch this class (13/13 clean while the spin sample
  died) — only a spin-protocol run with a mouth-crossing watch does; the b78
  probe added it permanently (crossing count + deflations + OOBB extent +
  pre-wreck crumb dump). Windings cannot fix a wall inside an orbit: one-way
  panes just choose which lap direction dies, and once a car is ever inside
  the jamb plane the "safe" side is a head-on wall outbound. The guards'
  reason to exist was a PHANTOM — the analytic mouth audit (swept-arc raycast
  profiles at r 13.8–15.4 across the sector + near-vertical-face census from
  the packed jbeam) proved the cone deck spans the whole mouth sector
  hole-free and step-free, with the skirt "knife blades" topping out AT deck
  height under the floor seam. Law: NO vertical collision inside r 17 near
  the mouth, ever — floors and slopes only; the Lua doorway bridge (holdLine
  14.6 in the mouth sector) adds drift margin. The audit script
  (mouth_audit.py pattern: parse packed jbeam, classify tris by node prefix,
  raycast swept arcs, census |nz|<0.45 faces with tangential/radial normal
  signs) is the instrument of record for any "collides at the mouth" claim.
- **(build 109) — the FIVE-DEMAND round: mouth eject, occupancy door,
  cop-light beacon, spin-up soundtrack, open-portal geometry.** Player
  2026-08-09, five directives in one session: (1) "spit the car at the
  speed it's currently going out the front entrance" — the protocol's two
  endings (survivor self-drive unload, over-the-rim flingSample) are
  DELETED, replaced by the EJECT phase: drum bleeds to eject_speed_mps
  (34) at eject_rpm_floor 30.5 (keeps the r>17.9 field drop + stall purge
  alive), mouth opens under THREE nested gates (travel gate: burial may
  only START with every interior sample predicted clear for travel+margin;
  arrival bake gate: the GLOBAL collision swap waits for >72° clearance;
  floor-first leaf choreography), then launchSubject SETS each sample's
  velocity = its current horizontal speed aimed at a corridor-centreline
  point 34 m out, first tick it sweeps the ±10° doorway window at
  r 13-17 with vt>6 (window+max_r worked out to keep ~1 m of jamb corner
  margin at every reachable speed; sweep ≤14.3°/tick < 20° window = no
  straddle-skip). Ejected latch is TRANSIENT (expires on bowl-exit or
  rest); remaining==0 is DEBOUNCED 1 s (trigger blank-tick); timeout 40
  sim-s → purgeBowl volcano (no-jam law). STOP = eject when occupied.
  (2) "this grey metal door should be open before a vehicle enters and
  close when a vehicle enters" (screenshot of the sealed leaf from the
  ramp — the 2026-08-08 EMPTY crescendo sealed the mouth for its whole
  61 s demonstration) — OCCUPANCY RULE: sealed is required only while
  spinning WITH a sample aboard; the floor gate is occupied-scoped so an
  empty crescendo runs open-mouthed at full song, and a car driving in
  mid-demo trips interiorCount → intake clamp (32 rpm / 8 m/s) → rise
  interlock walks the shelf up behind it → crescendo resumes. Plus: idle
  DOORWAY-SQUATTER purge (a wreck pinning the fall interlock sealed the
  mouth forever), rim-zone explainer messages, needEmpty self-clean at
  idle (~30 real s) with quarantine decay moved to behavior.update (it
  never decayed at idle — unpurgeable carcass).
  (3) Rotating beacon = REAL lights (cop-bar recipe): amber PointLight
  glow + two opposed SpotLights steered per tick from beaconAngle, aim
  via the game's own photomodeFlash recipe — quatFromDir(dir,up)
  :toTorqueQuat() written to the "rotation" field; setPosition + field
  write, never setPosRot. beacon_rate 9→3.0 (9 strobed 8.6 flashes/s
  real). (4) Spin-up soundtrack: three ~63 s stereo stems mixed to ONE
  ogg (authoring/mix_spinup_audio.sh, peak −0.5 dB), fileName-based
  SFXEmitter (FMOD "track" events are engine-only), is3D=0 to PRESERVE
  STEREO (3D downmixes to mono) with SCRIPTED camera-distance falloff
  (full ≤30 m, silent 75 m), play/stop edges on phase, change-gated
  volume writes with no postApply (playAmbient restart-risk class).
  (5) Approach messages for sealed occupied runs.
  RED-TEAM (adversarial subagent, 5 blockers all fixed pre-ship): F1
  pose must never LEAD the bake beyond one travel leg (foreign global
  reloads bake current transforms — the travel gate is the fix); F2/F3
  START/RPM± re-entered "spinning" from eject (hold slammed ~20 m/s into
  a just-launched car / manualStage seeded 500-RPM "hold") — buttons
  eject-guarded, armSpin clears b.manual; F4 purgeBowl now skips
  in-flight launches + quarantined samples; F5 b.manual survived resets.
  PIPELINE LAWS (b104/b107 probe tuition, the expensive kind): BEHAVIOR
  dict keys ship via the BLENDER-STAGE HANDOFF — a spec.py-only rebuild
  leaves every new B.* key NIL at runtime (b104: enterEject froze the
  machine at 500 RPM mid-eject; the recorded "params ship via handoff"
  gotcha, re-learned); 3-NUMBER LISTS BECOME VEC3 in the B table
  (B.spin_center precedent) — bp[1] threw 'struct __luaVec3_t cannot be
  indexed' every lit tick and silently killed beacon creation inside its
  pcall (10.6k log errors, machine otherwise healthy: the error sat at
  the TAIL of update after all machine logic); grep beamng.log for
  behavior_update_failed BEFORE theorizing about frozen phases.
  FIELD-ORPHAN REGIME (probe-harness law): a car parked at r>13.2 with
  |vt|<4 is released by the round-15 door-band valve and NEVER re-dragged
  below the rpm-60 stall-grip — probe cars must park at r≤12 (inside
  arm_radius) or they sit until the 12 s stall purge volcanoes them; a
  seized end-of-ladder wreck (vt≈0) is correctly REFUSED by the launch's
  vt-gate and ends via stall purge or eject timeout, torture-by-design.
  PORTAL GEOMETRY (b109, the player's green-circled "grey metal door"):
  at true idle the entrance still read half-closed — the slab was the
  HAZARD BAND, the bank's top course and the ONE ring still swept
  continuous across the doorway (a DAE raycast at the player's exact
  camera pinned it; its old "continuous on purpose" note guarded the
  unswept-era full-ring void, not the portal). b109 cuts its 257-283
  window; the leaf already spans BANK_PROFILE to the crest so the
  sealed state stays whole, and the leaf's upper course is split into a
  second plug wearing bank_hazard with metric cylindrical UVs so the
  chevron warning ring stays unbroken when shut. Idle approach shots:
  portal clear to the cornice, vault and far wall visible THROUGH it.
  Live verdicts (b107-b109 rigs): WITNESSED mouth launch PASS (through
  the mouth axis at ang 87°, landed rolling at its preserved ~15 m/s);
  audio falloff by field readback (0.837 @ r24 / 0 @ r100); beacon
  objects live + rotation readback distinct every sample; occupancy
  opened the empty crescendo at 183 RPM with the mouth open; travel
  gate + bake landed mid-eject with a seized wreck aboard; 0 fall-ins
  in every run; every phase ends idle with the mouth OPEN; final log
  sweep clean (0 errors).
  C-CODA (b110-b116, player: "grab an emergency light off an existing
  car" + "still no sound"): LAW - A PROPLIB PROP CANNOT HOST VEHICLE
  LIGHT JBEAM PROPS. The stock mechanism (excavated: vehicles/common
  lightEmitters = "SPOTLIGHT" props, amber {255,90,14} @ 2250 cd,
  glowMap material swaps, lightbar/beaconSpin controllers, FMOD-event
  soundscapes) rides the vehicle VM's module stack, which a bare prop
  never boots: 'electrics' was nil (fatal on first touch), late
  require("electrics") revived the VALUES (chase verified 0/1<->1/0 by
  readback) but require+reset+manual-update of the props module never
  made a SPOTLIGHT render - four probe cycles, abandoned. Emergency
  lighting stays GE-side (the b111 rig restored: lit lens PointLight +
  two beaconAngle-steered SpotLights, daylight-hot, photographed);
  audio stays VEHICLE-side via obj:createSFXSource loop (an obj method
  independent of the module stack - the mod-siren raw-ogg mechanism,
  audio mechanism v3 after fileName-SFXEmitter and Engine.Audio.playOnce
  both proved unprovable/silent), pushed by an edge flag from GE.
  Vehicle enter/exit counts for occupancy hardened to getAllVehicles
  ground truth (trigger-set blanking made a parked car invisible for
  minutes); TEST-RIG temp/* caches must be cleared between builds (a
  deterministic rig re-serving stale code is byte-identical to a re-run,
  but identical telemetry across suspected-different builds means CHECK
  STALENESS FIRST and also whether the fix even alters that scenario's
  arc); a probe camera aimed at AUTHORED coords photographs empty air -
  world = flipped (the beacon "verification" shots missed the beacon for
  three rounds).

  G-CODA (b118-b123, the CONTROL PANEL rounds - player: "the activation
  area of the mouse hover box isn't aligned to the buttons", then "lower
  the black faceplate to give room ... a better visual indicator of how
  much of an adjustment we've made"). Three transferable results:
  (1) TRIGGER BOXES EXTEND FROM THEIR ORIGIN CORNER, so every ghost sat
  half-a-box up-and-right and the error SCALED WITH BOX SIZE (mushroom
  caps worst, small caps mildest - that scaling is the fingerprint).
  Fix = baseTranslation -size/2 per row. This is separate from, and was
  masked by, the round-15 per-button-frame bug (triggers2 basis is
  idX-idRef / idY-idRef, so one shared frame pair skews every off-row
  box): BOTH must be right, and fixing one leaves a residual that reads
  like the other.
  (2) LAY PANEL PRINT OUT ANALYTICALLY, NOT BY EYE. Every label and cap
  is a box: print bold-Arial text width as ~0.62 em/char, cap radii from
  the cap-style table, then assert the rectangles are disjoint before
  running Blender. Two rounds of "labels run into each other" ended the
  moment the layout was checked as geometry. Type sizes must be FRACTIONS
  OF PLATE HEIGHT that you re-scale when the plate grows, or a taller
  plate just prints bigger letters and eats the room it gained.
  (3) A POSE-ONLY BAR GRAPH: pose parts can only move, never recolour or
  light up, so an N-of-5 indicator = 5 bright blocks over 5 static
  machined sockets, each block shoved +0.12 m in AUTHORED y (straight
  back through the opaque plate into the cabinet) when unlit. Safe by
  construction because posePartObjects computes
  origin + modelRotation*(pivot + offset): the offset is added in
  AUTHORED space and the flip is a proper rotation, so "inside the
  cabinet" stays inside the cabinet in world. Also: the exporter does
  NOT delete DAEs for parts you removed - orphan meshes ride the zip
  until you sweep mod/vehicles/<id>/ by hand.
  (4) Control-ladder tuning: hold_damp is a PER-FRAME fraction, so it
  COMPOUNDS - the old 0.15..0.95 span was five flavours of "pinned"
  (0.15 still kills 99.99% of an overshoot inside a second). Panel
  ladders over compounding quantities must be LOGARITHMIC: 0.03 / 0.15 /
  0.55(nom) / 0.80 / 1.00. drag_rate is already a rate (1/s), widened
  0.8..14 = slip time constants 1.25 s..0.07 s, and its top end is the
  real answer to "what pops the tyres" - less slip angle, less scrub.

  H-CODA (b124-b125, facade + threshold polish). Four transferable laws:
  (5) VERIFY MATERIAL KEYS AGAINST SHIPPED GAME DATA before writing them.
  A mirror-glass spec called for `"alphaType": "none"` - that key has ZERO
  occurrences in the install's vehicle materials (it is a glTF/Godot
  spelling). RE-DERIVED 2026-08-15 on engine-reported **0.39.4.0 build 20972**: still zero, over
  173 zips / 921 `materials.json` / 6,532 material entries / 0 parse failures. The "0.38.6" this
  line was written with came from the profile directory name, not an engine — a census over engine
  data is only true of the engine it was run on, so name the build and re-run it.
  Real and confirmed by count: dynamicCubemap (241),
  translucent (267), translucentBlendOp (124), castShadows (55),
  opacityFactor (41, a STAGE key not a root key). The stock reference for
  a true mirror is `generic_chrome` in vehicles/common/generic_mat_tex:
  metallicFactor 1, roughnessFactor ~0.07, dynamicCubemap true, opaque.
  Grep content/vehicles/*.zip before inventing a field - same discipline
  as the nonexistent particle emitters.
  (6) A MIRROR IS NOT GLASS. Round 15's mirrored-windows artifact was the
  stock TRANSPARENT glass shader misbehaving at building scale; an OPAQUE
  PBR chrome has no glass shader to misbehave and gives the mirror look
  safely. Reaching for "the reflective material" is what caused the bug;
  reaching for "a metal that reflects" is the fix.
  (7) A STRAIGHT LINE CHASING A SLANTED PLANE LOSES SOMEWHERE. The
  corridor reveal wall was flared to bury its END in the entry pier, but
  the pier's inner face is a plane at 13 deg to the lane, so the two
  crossed twice and left the wall up to 7.6 cm INBOARD over a 0.7 m
  stretch - a few centimetres in plan, but a full-height brown sliver
  down the corridor (player green-marked it twice, one round apart). Fix:
  solve the plane for x at each station and take max(flare, plane +
  burial). Both terms monotonic, so no kink, and burial becomes a
  property of the construction rather than of one tuned endpoint.
  (8) RING UVs MUST WRAP ON WHOLE TILES. `_swept_mesh` ran u from 0 to
  circumference/tile_m, which is essentially never an integer, so at
  azimuth 0 the last column met the first at a FRACTIONAL tile and the
  chevrons jumped phase - one straight radial seam, invisible on a plain
  texture and unmissable on a diagonal one. Round the span to whole tiles;
  the tile stretches under 1% and the seam is gone from every ring the
  builder makes. Any closed swept surface with a patterned material has
  this latent bug.
  (10) FIX THE NOISE BASIS, NOT THE MATERIAL (b126, the big one). Every
  procedural texture in the pack bottoms out in texture_kit._value_noise,
  which built an np.kron cell grid and softened it with two axis-aligned
  BOX blurs. That is not bilinear whatever the docstring said - a box
  blur's support is a square, so the cell lattice survives as axis-aligned
  steps. THREE separate rounds of "make concrete less blocky" (the `fine`
  mode, the copper-v3 speckle recipe, the round-15 vault-beam pass) each
  layered more detail ON TOP of a blocky basis and each failed, because
  the artifact was underneath. Replaced with true bilinear sampling under
  Perlin's smoothstep fade - isotropic, C1, still exactly periodic, and
  cheaper than the two FFT passes. Two riders: (a) _fbm must renormalise
  to [0,1] afterwards, because summing octaves of a well-behaved basis
  narrows the distribution and every consumer's threshold was calibrated
  against the old per-octave stretch - skip this and the fix reads as "all
  the detail vanished"; (b) once the blockiness is gone the families have
  nothing left, so concrete needed real exposed aggregate (chip mask with
  per-chip tone, sand grain, pour drift) and steel_worn needed real
  anisotropy - a tiled single-row scratch field is a flat wash, mill steel
  needs directional grain smeared over a finite run so it has ends.
  (11) A LEGEND MAP'S RESOLUTION IS px PER PLATE METRE, not px. Growing
  the console plate 0.95 -> 1.15 m silently dropped the print from 1078 to
  890 px/m and the player saw it immediately ("blurry all of a sudden").
  Scale the map with the plate.
  (12) A MIRROR CAN ONLY BE AS SHARP AS ITS PROBE. roughness 0 + metallic
  1 + dynamicCubemap on a 47 m drum resolves individual cubemap texels as
  metre-wide blocks of sky and ground - the probe is sized for a car. The
  opaque-chrome trick does dodge the transparent-glass artifact, but not
  this. Tint it dark and give roughness ~0.2 so the sample pulls a
  blurrier mip; architectural mirror glazing is a sheen, not a photograph.
  (13) OPEN — THE BANK-FOOT SCALLOP (b129, player: "always popping a tire
  even at the lowest RPM crossing the closed entrance"). NOT FIXED. The
  cage dish/bank rings are 28-gons, and a polygon's radial error converts
  into HEIGHT error through the bank's radial gradient:
      dz ~= (z_B - z_A) * r * (sec(pi/n) - 1) / (r_B - r_A)
  At r 15.8, n=28, ring spacing ~0.5 m, rise ~0.28 m -> 0.056 m, which is
  what the shipped cage measures. A 6 cm scallop repeating every 12.86 deg
  all the way round; the mouth shelf is a fine mesh built at the TRUE bank
  height, so it lands on the scallop floor and every jamb crossing steps
  off a column onto it. Speed-independent, and it shows at the entrance
  only because that is the one place a car crosses a surface boundary.
  NODE REPOSITIONING CANNOT FIX IT. Inscribed puts the error at mid-chord,
  circumscribed (what b129 does, KEPT in tree, NOT installed) puts it at
  the columns, anything between splits it. Only n and the ring spacing are
  real terms: 28 -> 56 columns cuts it 4x to 0.014 m and clears the bar.
  THE TRAP: WALL_SEGMENTS=28 is an INDEX BASIS, not a resolution knob -
  the doorway is columns 19..23, fairing columns are picked by index, and
  build_mouth_shelf spans `19 * 360/WALL_SEGMENTS` to `23 * ...`. Raising
  it renumbers the door leaf, patch hems and flank fairing. Convert those
  to fractions of the count first.
  INSTRUMENT + BAR (both scripts are in the b129 session): sample the
  static cage AND the shelf DAE together along constant-radius arcs;
  under 0.02 m at r 15.8 across azimuth and across both jambs, matching
  what r 14.0 and r 15.0 already do. Re-run the 13-line entry gauntlet
  before installing.
  THREE WRONG MODELS were burned getting here, all from measuring the
  wrong thing: (a) the pier-trim orientation (the trim's 0.20 m dimension
  was RADIAL, so it faced the corridor edge-on while spanning 0.95 m
  across the lane); (b) an arc sample that read the static cage ONLY -
  the mouth shelf is a posable part whose collision lives in its own DAE,
  so the "10.4 cm step" was the depth of the hole the shelf FILLS; (c)
  the inscription theory above. Measure every surface a wheel can touch,
  not the one that is easiest to parse.
  (9) A proud strip a car drives over wants a CROWNED section, not a slab:
  ease the top to the deck over ~a third of the width at each shoulder
  (smoothstep pair) with the feet buried, so the edges emerge from the
  surface and a tyre meets a tangent instead of a lip.
  (14) YOU CANNOT PUT A HOLE IN A BANKED WALL. Shipped and reverted the
  same day (b135 -> b136). The player could not drive a truck in: the
  VISUAL bank opens full height at the doorway (`skip_frac=1.0`) but the
  cage only cut BANK_PROFILE levels 0..4, so level 5 (r 17.887, z 4.877)
  stood as an INVISIBLE LINTEL pinching the entrance to 2.53 m. Cutting
  to level 7 gave a real 4.10 m and a WORSE bug - "they're getting stuck
  ... near the door" - because FAIR_KEEP only fairs levels 1..4. Levels 5+
  stand full height, so the new cut edge was an unfaired 2.5 m face with a
  hole behind it. Azimuthal jump at the doorway edge went 0.303 m (r 17.5,
  pre-existing) -> 2.537 m (r 18.0, created). THE LINTEL IS NOT
  DECORATION: it is what makes the cut edge continuous surface instead of
  a rim. A hole in a bank has either a cliff at its edge or a swale big
  enough to swallow the bank. Headroom has to come from ARCHING the
  soffit - lift the garage columns' level 5..7 nodes so the surface stays
  unbroken and merely bulges - one shared arch function (spec.door_arch).
  CODA (b137-b139, CLOSED): the arch worked and burned two more lessons
  before it settled. (a) A VISIBLE ARCH IS A DUNE. The b138 +-2-column
  window rested on the false belief that "the doorway columns" are cols
  19..23 - that is the SHELF's span; the visual cut is 257..283 deg =
  cols 20-21 ONLY, so the arch lifted a full column of VISIBLE bank per
  flank and the player got a textureless grey swell swallowing the
  hazard band ("doesn't conform visually with the rest of the inside
  wall"). Final form: half-width = ONE column (360/28 deg), weight
  exactly 0 at node cols 20/22, while the nearest retained visual cells
  end at 256.875/283.125 - every lifted vertex lies inside the
  already-invisible sector, the arch is COLLISION-ONLY, and the interior
  reads byte-identical to the accepted baseline. Soffit = chord fan:
  4.92 m at lane centre, 4.20 m for a 2.6 m-wide box, 2.52 m at the
  jambs; tall vehicles fit down the middle, where the ramp feeds them.
  (b) THE CLOSED STATE MUST NOT ARCH. b137 arched the mouth shelf too
  and the raised "seamless closure" grew a 2.4 m hump - the
  divot-in-reverse the b101 law bans - dragging shelf_drop to 5.7 m and
  the travel speeds with it. Shelf and leaf stay pure BANK_PROFILE; the
  closed-state pocket between patch top and arched soffit is
  unreachable (orbits r<=16.8, pocket starts r 17.35 above z 4.9). All
  three reverted together, and the leaf-open gate became a FRACTION of
  shelf_drop (0.75 = the historic 2.4 m) so it can never silently
  loosen against a future drop change. Jambs now snap to the rings'
  shared cut-cell boundary (256.875/283.125, AZIMUTH_STEPS quantised)
  instead of the nominal 257/283 - a jamb on the nominal edge stands
  0.125 deg INSIDE the opening and 4.3 cm of every ring's end face
  pokes out beside the post (the player's green-circled yellow tab).
  CODA-2 (b140, the arch is DEAD): b139 failed live in a dozen
  rotations - the car "instantly snapped to the ceiling above the
  entrance and got stuck". LIFTING A LEANING WALL MOVES ITS FACE
  INBOARD AT FIXED HEIGHT: at ~50 deg of bank, +2.4 m of lift rams the
  riding face up to ~1.8 m toward the drum centre through z 5..7, and
  the lifted curl (8.8 -> 11.2, confirmed by node dump of the shipped
  cage) is an overhang pocket the field pins the car into. NO arch
  shape coexists with sealed wall-riding. THE ACTUAL FIX is that the
  two needs are DISJOINT IN TIME: headroom only matters OPEN, pure
  wall only matters SEALED - so the states swap coverage. Static
  lintel fully cut (DOOR_CUT_LEVELS=8; only the 8->curl containment
  quad spans the window = 4.7 m UNIFORM open clearance, no chord-fan
  taper) and the mouth shelf extended to the rim at pure BANK_PROFILE
  carries the sealed wall. The extension is a WINDOW-ONLY sub-grid
  (cage cols 20-21) - putting it in the shelf's main cols-19-23 grid
  would twin the static flank quads (b85 class) - and rides 30 mm
  RECESSED so the door leaf's courses (hazard band included) stay the
  visible closed wall as accepted since b101. shelf_drop 5.5 (top 7.0
  buries 0.6 under the ramp), speeds 2.75/3.4375 hold the 2.0/1.6 s
  exposure windows, leaf gate 0.85 (top clears deck before the leaf
  shows open). REINTERPRETATION: the b135 wrecks were the SAME class -
  the era's shelf stopped at r 17.867, so the sealed ride met the
  cut's hole. The full law: WHILE SEALED, THE DOORWAY BAND MUST BE
  EXACTLY PURE PROFILE - hole, cliff, or lift, any divergence in the
  rideable band is a wreck machine. Sealed-state coverage lives in a
  posable part's DAE, which STATIC JBEAM PROBES CANNOT SEE - only a
  live ladder run validates it.
  (15) A VERTICAL RAYCAST IS BLIND TO A VERTICAL WALL - the triangles are
  edge-on, the barycentric test degenerates, and they are silently
  skipped. A down-ray probe cheerfully reported "9 m clear corridor" with
  a truck stopped in it. To measure clearance, CUT THE SOUP WITH THE
  CROSS-SECTION PLANE (triangle -> segment in the section) and test a
  vehicle-sized rectangle against the segments. Down-rays remain correct
  for "how high is the road here" and nothing else.
  (16) RADIAL SMOOTHNESS IS NOT AZIMUTHAL SMOOTHNESS. The doorway
  measured perfectly smooth at every radius while stopping trucks,
  because driving in/out is radial and the snag is only met crossing
  SIDEWAYS - which is what circulating and being ejected both do. Sweep
  both axes or you will certify a defect as clean.
  (17) WHAT READS AS "TILED" IS A REPEATED STRAIGHT LINE, NOT REPEATED
  NOISE. Two rounds were spent flattening the concrete family's
  pour-scale blotching (real, worth doing) while the actual complaint was
  the two control-joint grooves the family stamps at fixed v - one hard
  dark line every half tile, forever, locked to the tile grid. The eye
  forgives repeated noise and never forgives a repeated straight edge.
  Look for the most GEOMETRIC feature in a texture before touching its
  noise.
- **CLOSED (build 101, INSTALLED) — the SEAMLESS closure + hoist-stripe
  coda.** Player follow-ups on b99: "the entrance when closed should be
  seamless, there shouldn't be a divot both visually or in mesh" and
  "something is wrong with the black texture underneath the gantry hoist".
  (1) The raised patch is no longer the faired swale — it is the FULL
  BANK PROFILE (spec.BANK_PROFILE chords, cage-exact) spanning cage cols
  19..23 (doorway + both faired flanks), every boundary vertex tucked
  6 mm UNDER the surrounding static geometry (the junction-band hem
  trick) so the patch emerges through the faired sheet with hairline
  shutline seams. Closed = an unbroken velodrome; the divot, the leaf
  outline and the aperture all vanish (the leaf sits 25 mm below the
  track line, hidden under the patch skin). Open state (entry, fairing,
  b99 certification) untouched. Live: 0 fall-ins vs the FULL-profile
  reference, 17.4 laps, crossings riding UP the continuous bank as rpm
  climbs. Rise-interlock sector widened to cos 0.88 / any-speed 16.8+
  for the bigger footprint. LAW: a rideable closure must match the
  surface it interrupts, not the safety fairing beneath it — fair the
  OPEN state, restore the FULL state when closed.
  (2) A hazard-material band saw only a sliver of the 6 m chevron tile
  (0.16 m tall = 3%) and rendered as arbitrary diagonal smears — ALWAYS
  give small hazard trim its own metric_uv (0.35 m tiles fixed the hook
  block's band).
- **CLOSED (build 99, INSTALLED, critic-certified WOWED) — the mouth-shelf
  round: "vehicles fall into entrance / the mesh doesn't close up".**
  The b94 aperture had NO riding surface while spinning: the leaf is
  collisionless theater, and the b93 fairing lowered the flank COLLISION to a
  swale while the VISUAL bank stayed full height — dragged cars fell through
  the ghost door into the depression and looked swallowed by the wall. Fix =
  the MOUTH SHELF part: a solid wedge whose raised top IS spec.faired_bank_z
  (shared constants → millimetre-flush with the flank columns, audited
  +0.0000 at all 16 seam checks), collision=true, raised while the protocol
  runs, buried 3.2 m under the ramp at idle. Laws minted:
  (1) ENDPOINT-BAKE IS ONLY SAFE WHEN BOTH ENDPOINTS ARE SAFE — a vertical
  burial qualifies, the old door's lateral slide never could (its stale pose
  stood in the lane).
  (2) be:reloadCollision IS GLOBAL — only the collision-owning part may
  request reloads; the collisionless door's legacy endpoint requests were
  deterministically baking the shelf MID-TRAVEL (red-team find).
  (3) PHASE DRIVES PHYSICS, CORRIDOR HOLDS DRIVE THEATER — coupling the
  shelf to the leaf's corridor hold let any tunnel parker pin the floor
  open while the drum spun.
  (4) FLOOR GATE: no hypergravity until the floor is settled (rpm<=32,
  drag<=8 m/s while shelfDrop>0) — turns every unfloored-mouth window into
  the benign-crossing regime.
  (5) VISUAL MUST FOLLOW COLLISION FAIRING (z_remap on the bank sheet +
  jamb tops; and the 28° leaf pocket became a naked slab over the faired
  sheet → park at 40°, past the blend zone).
  (6) Stall accrual radius < 19.6: the bank (to 19.5) is IN the drum — a
  flat-tired car wedged at 18.6 must purge — but the outer ramp is a QUEUE,
  and >20-RPM accrual without the gate yeeted an innocent approacher.
  (7) Stock vehicle "glass" on building-scale glazing renders as a glitchy
  full mirror — use the mod's own obs_glass; never leave a stock-named
  material slot in a prop DAE.
  HARNESS LAWS (five rig-cycles of tuition): an uncommanded BeamNG vehicle
  DRIVES OFF on its own (assistant/arcade; frame-autopsy with a no-prop
  control proved it) — spam control() on every probe car, kill_ai() at
  spawn; a car CANNOT be script-parked in the doorway band (crest rollback →
  arcade auto-reverse, capture-drag past arm_radius 13, teleport
  relocation — 7 attempts) so the rise-interlock hold path ships code-audit-
  covered, honestly documented; python `x or -1` eats a 0.0 shelf reading
  (falsy-zero); post-purge landed wrecks poison the stuck detector unless
  gated r<21.
- **CLOSED (build 94, INSTALLED) — the stuck-vehicle endgame, and its laws.**
  Fourteen build-probe cycles convicted, in order: guard walls (wall-in-orbit),
  the doorway bridge (hold must be axisymmetric), ~370 surface collision
  spheres (wheel-reach rule; set_spawn_envelope FORCES collision=True on its
  8 corners — relocate them off driveable surfaces), the flank pit (fairing +
  corner lids), the TWIN-TILING bug (add_quad+reversed re-triangulates on the
  opposite diagonal → one-way ghost ceilings over twisted quads; and the
  naive fix — exactly-coincident mirrored triples — pops tires ON FLAT
  GROUND: jbeam triangles carry contact/pressure state, NEVER emit the same
  node triple twice; correct emitter = HIGHER-DIAGONAL-UP with a crossed-
  diagonal fallback for walls and degenerate quads), the CAMBER law (a bank-
  riding orbit must never cross a flattened band — fairing keeps 55% of the
  foot), and finally the structural guarantee: STUCK AUTO-PURGE (per-sample
  angular-progress stall clock in the field; 12 s of no sweep while the drum
  runs → launchSubject up-and-out). Terminal instruments, in escalating
  order of power: sphere census, fine-gate swept circles, gate2 (exact-twin
  count + facing-aware ghost-pinch scan, thresholds gap 5 cm..1.2 m, z<=6),
  wreck-site ball query, spin watch with crumb ring buffer, and the
  FRAME-BY-FRAME DETERMINISTIC AUTOPSY (0.05 s stepping + per-wheel
  isTireDeflated/downForce + chase shots) — which ended four blind fix
  cycles in one run. Verdict criteria = the PLAYER'S WORDS (smooth entry, no
  entrance collisions, never stuck, containment, frame intact) — NOT tire
  life (torture-by-design; the b68 "clean" baseline never measured spin-car
  deflations) and NOT protocol completion (sample survival is an experience
  knob). drum_zone must contain the CREST orbit + car OOBB (46 m; the July
  zone-flap lesson recurs at every radius you forget).
- **Round 15 coda — the sign is GEOMETRY + DISTANT floods.** A PointLight AT
  a panel renders as a circular disc at ANY brightness (16 pools: 0.32 blew
  a strip, 0.07 = bulbs, 0.012 = still discs) — and deleting the pools
  proved the other half (b79: black sign): letter_glow's emissiveFactor is
  inert — the b78 "glowing rims" were pool-lit. (That last clause used to read
  "as inert as EVERY vehicle material, no exceptions, ever". Corrected
  2026-08-15: letter_glow is inert because its emissiveFactor has FOUR
  components; a three-component factor emits fine. Round-16/17 ledger above. The
  disc finding and the recipe below are untouched by that.) The working
  recipe: (1) white glyph BACKPLATES —
  rerun the FONT→convert→wrap pipeline, extrude 0.003, offset 0.016/scale
  (~16 mm rim so the plate reads around its dark letter even head-on),
  parked r_face+0.004 behind the r_face+0.045 letters over a graphite
  cabinet; (2) TWO floods ~7 m OUT FRONT (authored (±4.5, −34.0, 7.4),
  radius 24) — at distance the wash is even (no discs, physically) and the
  near-white plates out-return the graphite ~9×, so the night glow still
  reads letter-shaped. Day reads as classy reverse-lit channel letters.

### Round-16/17: the photometric ledger — emissive materials and light objects (2026-08-15)

Everything below is MEASURED on a real renderer, not argued. Method: a 20-cell
labelled calibration strip (4 × 5 grid of 4.60 × 3.00 m quads on a black backing
panel, each with a baked engraved legend) stood 2.15 m proud of the
`pachinko_tower` board face, built into an ISOLATED copy of the mod tree so the
shipped build was never touched. Captured on `smallgrid` at `TimeOfDay` 0.00 and
0.50, dx11 windowed, 2560 × 1421, isolated `test-users` profile — and in the
readings quoted here **all 12 of the prop's own PointLights were disabled**
(`scenetree.findClassObjects("PointLight")` → `isEnabled 0`), so every bright
pixel is material radiance and nothing else. Photometry is a pinhole solve, not
eyeballing: the plane is fronto-parallel, `fov` 65° VERTICAL (read live from
`core_camera.getFovDeg()`), `d` = 26.37 m, `f` = (H/2)/tan(fov/2) = 1115.3 px;
predicted 21.00 m backing span 888 px against 880 measured. Four rounds of
captures and the per-cell JSON are in the 2026-08-15 session scratchpad
(`calib_pack/` + `calib_capture.py`; analysis = `r17_analyze.py` →
`r17_analysis.json` + `r17_overlay.png` + `r17_ply_zoom.png`).

**READ THIS BEFORE TRUSTING A NUMBER BELOW.** Every figure here has now been
through six passes, and the corrections have not converged on "round 3 was
sloppy": rounds 4, 5 AND 6 each found errors *in the correction that preceded
them*. The recurring failure is not bad measurement, it is **arithmetic done
outside the model the measurement lives in** — a clip predicate off by one
code, a ratio of readings compared to a ratio of texels, a curve inversion fed
an un-subtracted control, a robust estimator pointed at a feature it is not
robust to — and, round 6's finding, **a number RE-TYPED by hand instead of
printed from the file it is sourced to**. Round 5's own audit trail is
`D1_diff.py` (every clipped_pct, old predicate vs new), `D2_cook.py` (the cook
ledger), `r17_audit2.py` (scope and suffix censuses over all 173 zips),
`D4_particles.py`, `D5_final.py` and `D_semantic_proof.py`; round 6 adds
`E_r6_table.py` (the noon table, generated), `E_r6_apply.py` (these edits,
hash-guarded) and a rewritten `D_semantic_proof.py`; round 7 adds
`F_r7_recorder.py` (one shared replayer), `F_r7_census.py`, `F_r7_sweep.py`
and `F_r7_residue.py`; round 8 adds `G_r8_sweep.py` (the version sweep,
rewritten so classification is exactly-one rather than first-match),
`G_r8_synth.py` (seven synthetic law violations, all of which the round-7
sweep silently placed), `G_r8_directs.py` (the UNSCRIPTED AGENTS.md edits,
recovered from session transcripts by AST) and `G_r8_agents_reverse.py` (the
reversal round 7 declared out of scope).

**WHEN TWO INSTRUMENTS DISAGREE, RECONCILE THEM TO THE BYTE.** Round 6 ran
two: a tree-integrity diff against a pre-round baseline of sha256 + size, and
an edit RECORDER that replays every apply script. On
`examples/giant_props/proplib/prop_builder.py` they disagreed — the diff
attributed the file's whole +3,517 bytes to this work while the recorder
accounted for only +1,070 — and round 6 published "5 of 5 proved" over the
2,447-byte gap. The proof could not see it: it compares NOW against
NOW-MINUS-MY-EDITS, so anything a concurrent session wrote is inside BOTH
sides. Round 7 resolves it by reconstructing `before` and hashing it against
the baseline (`F_r7_residue.py`), which fails loud on any residue. The
residue is **exactly 2,447 bytes and is not this programme's**: the function
`check_emissive_factor` (2,381 bytes, `def` line through its two trailing
blanks) plus its single call site (66 bytes), both written by the concurrent
ROUND 18 session documented in the next section. Removing precisely those two
spans from the reconstruction reproduces the baseline **sha256
`8b00c81d0b7997755379...`, byte for byte, 32,319 bytes**. The lesson is
narrower than "check your work": a delta measured against a wall-clock
baseline and a delta measured by replaying your own writes are DIFFERENT
QUANTITIES in a concurrently-edited tree, and the difference is other
people's work. Publish both, or publish neither. Where a value is an
INTERVAL between two measured
rungs, it is written as an interval; where it is a single number with a
spread, the spread is given. **Do not re-narrow either one without a capture.**

- **THE ENGINE IS 0.39.4.0 build 20972, not 0.38.6.** Rounds 1–3 captioned every
  artefact "BeamNG 0.38.6". That string came from the stale PROFILE DIRECTORY
  NAME `test-users\BeamNG-0.38.6\`, never from an engine: line 1 of every capture
  log reads `v 0.39.4.0 - x64 - build 20972`. **The finding transfers to the
  player's build because it IS the player's build** — `calib_capture.py` launches
  `E:\SteamLibrary\...\BeamNG.drive\Bin64\BeamNG.drive.x64.exe`, the same binary
  as the live install; only the USER directory is isolated. The profile directory
  keeps its misleading name for now (other sessions have live paths pointed at
  it); treat the name as an ID, never as a version.

  **THE PROVENANCE TABLE — every engine string this repository has ever had from
  an engine, and everything else is hearsay.** Round 4 stated the law and then
  broke it in the same diff, adding two fresh "0.38.6" attributions while
  correcting others. Round 5 swept all of them:

  | string | where it came from | status |
  |---|---|---|
  | `0.38.6.0.19963` | `examples/cannon_car_wash/telemetry/cannon_car_wash_phase4_results.json` → `beamng_version` | **engine-reported**, July 2026 |
  | `0.39.2.1` | `examples/cannon_car_wash/telemetry/cannon_car_wash_selector_results.json` → `runtime.beamng_drive` | **engine-reported**, a later run |
  | `0.39.4.0 build 20972` | `beamng.log` line 1 AND `integrity.json` → `buildinfo` in the install itself | **engine-reported**, current |
  | `BeamNG-0.38.6` | `test-users\BeamNG-0.38.6\` | **a directory name.** Not a version. |

  The install has moved TWICE while the docs kept saying one thing, and the
  repo contained the proof of both moves all along. Consequences: any census
  over engine data is true only of the build it ran on, so it must carry the
  build. Remaining `0.38.6` strings are TEST FIXTURES, PROFILE IDs, frozen
  release/submission records, or as-tested-then attributions that the
  `0.38.6.0.19963` telemetry supports. **That exemption is by CLASS and never
  by directory** — see the round-6/7 entry at the end of this section, which
  is the current statement of the law and which OVERRULES the round-5 line
  that used to stand here naming `examples/cannon_car_wash/` as exempt
  wholesale. It is not exempt wholesale: two present-tense engine claims
  inside it were corrected in rounds 6 and 7. `F_r7_sweep.py` classifies
  every surviving occurrence in the repository and fails on any it cannot
  place.

  **THE SWEEP CENSUS, GENERATED, AND WHICH POPULATION IT COUNTS.**
  `F_r7_census.py` replays every apply script with the writer stubbed and
  counts from the record, because round 6 typed this sentence and a critic
  replaying the same recorder got a different number. They were counting two
  different things, and the sentence did not say which:

  - **VERSION-SWEEP SITES** — edits whose REPLACED text contained `0.38.6`.
    Round 5: **14 over 7 files** (6 + 1 + 2 + 2 + 1 + 1 + 1), which is what
    the round-5 sentence meant and is confirmed by the recorder. In THIS file
    the `BNG_*` particle claim, the citybus metadata line, the release-matrix
    pin, the profile-path preamble, the `getSpawnWorldOOBB` line and the
    `alphaType` census; and in the pack `proplib/prop_builder.py`,
    `belt_sander_trap/spec.py` (×2), `junk_chute_grinder/spec.py` (×2),
    `pachinko_tower/spec.py`, `sumo_gyro_platform/spec.py` and
    `hot_potato/DESIGN.md`.
    Rounds 6–8 add 14 more, in this file's own round-7 sweep site,
    `README.md`'s retail-camera sentence (×2), `docs/ARCHITECTURE.md`,
    `docs/AUTONOMY.md` (×2), `docs/DEVELOPMENT.md` (×2), `docs/SETUP.md` (×2),
    the cannon geometry manifest, `create_cannon_car_wash.py` (×2) and the
    manifest's test (`README.md`'s support MATRIX keeps its 0.38.6 pin) —
    **cumulative 28 sites over 15 files**.
  - **EVERY RECORDED EDIT** — the whole round-5 write log, version-related or
    not. In the pack that is **13 writes at 12 distinct sites over
    7 files** (`sumo_gyro_platform/spec.py` was written 4 times at 3
    sites; `D_apply_sumo2` rewrote what `D_apply_sumo` had just written).
    The extra file that appears only in this population is
    `sumo_gyro_platform/authoring/listing_copy.md`, **a shipped listing
    document carrying a player-facing correction**, and the round-5 sentence
    named neither it nor the population it belongs to. Round 6's
    `prop_builder.py` count of 1 and `sumo_gyro_platform/spec.py` count of 1
    are right for the version population and wrong for this one (2 and 3).

  **Two of the round-5 corrections above were RE-RUN on 20972** rather
  than merely re-labelled, and both survived: `alphaType` is still zero over
  173 zips / 921 `materials.json` / 6,532 entries / 0 parse failures, and
  `BNG_Waterfall_Mist` / `BNG_exhaust_steam` / `BNG_Ambient_Dust` still do not
  exist beside the 91 `ParticleEmitterData` and 95 `ParticleData` objects that
  do. **Not re-verified and still owed a banner:** the `getSpawnWorldOOBB`
  half-extent behaviour, and the identical Lua comment at
  `hot_potato/spec.py` (left untouched because it is emitted verbatim into
  generated `mod/lua/.../runtime.lua` and into a shipped zip, and this round
  was forbidden to rebuild — fix it in the same pass that next rebuilds that
  mod). Also deliberately untouched: `proplib/texture_kit.py`, where "0.38.6"
  appears INSIDE a quotation of the retired false diagnosis and the very next
  line already says the version it blamed was wrong too; and
  `examples/giant_props/build.py` + the profile path above, which are IDs.
- **THE ZERO IS THE CONTROL CELL, NOT A "BACKING PANEL" BOX.** Rounds 1–3
  subtracted a box placed 0.20 m below the bottom row and called it bare backing
  panel. It never was: the black skirt there is 0.40 m (~17 px at this focal
  length) and the box is 12 px tall, so it straddled the panel edge onto the
  decorated playfield behind. It read a plausible 0.0054 in round 3 only because
  the playfield happened to be dark there; the SAME PIXELS read 0.107 in round 4,
  twenty times higher, purely because the board's own textures rebuilt. Cell 00
  — same base colour, same roughness, same window, no emissive keys — is the
  reference, and is what every "over control" number already used.
- **A FOUR-ELEMENT `emissiveFactor` KILLS THE EMISSIVE PATH DEAD, and nothing
  rescues it.** This one line is the whole "emissive is inert" law. Every shipped
  BeamNG `emissiveFactor` ARRAY writes THREE components, with no exceptions
  anywhere in the install, and the pack's palettes wrote FOUR by analogy with
  `color`, which really is RGBA. **Say which count you mean** (`r17_audit.py`
  re-derives all of these; 173 zips, 127 of them carrying 921 `materials.json`
  over 6,532 material entries, 0 parse failures):

  | scope | count |
  |---|---|
  | `emissiveFactor` arrays in `content/vehicles/*.zip` | **440**, histogram `{3: 440}` |
  | `emissiveFactor` arrays in EVERY zip in the install (173 of them) | **486**, histogram `{3: 486, 4: 0}` |
  | …of those, in stages that also carry `emissiveIntensityNits` | 461, all 3-component |
  | `emissiveFactor` keys whose value is JSON `null` | 1,325 |
  | naive count of the KEY being present at all | 1,811 |

  A key-presence grep returns 1,811 and means nothing; the shape claim is about
  the 486 real arrays. (Rounds 1–3 quoted "439 of 439" for the vehicle scope —
  right idea, off by one, and silent about which scope it counted.) The
  GAME-WIDE row's caption used to read "(+ levels, art_shapes, gameengine)",
  which UNDERSOLD it: `r17_audit2.py` splits all 173 zips into vehicles (440),
  levels (25), art_shapes+gameengine (21) and **the other 27 zips (0)**. 486 is
  not a scope choice — it is every `emissiveFactor` array that ships, anywhere,
  and there is no zip left over to hide a 4-component one in.

  Measured at midnight with the control at exactly sRGB 0.0:

  | cell | components | max value | `emissive:true` | nits | night sRGB | |
  |---|---|---|---|---|---|---|
  | `12 FACTOR3 ONLY` | 3 | 1.00 | – | – | 253.0 | EMITS |
  | `16 F3 OVER1` | 3 | 2.10 | – | – | 255.0 | EMITS |
  | `02 FACTOR+FLAG` | 3 | 1.00 | yes | – | 253.0 | EMITS |
  | `01 FACTOR ONLY` (centrifuge `letter_glow` verbatim) | 4 | 2.10 | – | – | **0.0** | DEAD |
  | `17 F4 UNIT` | 4 | 1.00 | – | – | **0.0** | DEAD |
  | `19 CFUGE AMBER` (centrifuge `beacon_amber` verbatim) | 4 | 1.00 | – | – | **0.0** | DEAD |
  | `18 F4 +NITS` | 4 | 2.10 | yes | 1800 | **0.0** | DEAD |

  Read the last row twice: adding `emissive: true` AND `emissiveIntensityNits:
  1800` to a 4-component factor still renders sRGB 0.0 at midnight and −0.2
  against its own control at noon. The array shape has to be repaired; no other
  key can compensate.

  **Round 4 replicated it with the decisive pair ADJACENT** (round 3's cells
  differed in row AND column, which is worth ~10% on its own — see the tone
  curve caveat below). Same row, neighbouring columns, differing only in whether
  a fourth component is appended to an otherwise identical `[1,1,1]`:

  | cell | components | flag | nits | night sRGB | |
  |---|---|---|---|---|---|
  | `01 FACTOR3 ONLY` | 3 | – | – | 255.0 | EMITS |
  | `02 F4 UNIT` | 4 | – | – | **0.0** | DEAD |
  | `03 F4 +NITS` (centrifuge `letter_glow` + flag + 1800) | 4 | yes | 1800 | **0.0** | DEAD |
  | `18 CFUGE AMBER` (centrifuge `beacon_amber` verbatim) | 4 | – | – | **0.0** | DEAD |

  **THE PACK'S "10 OF 10" IS CONSISTENCY, NOT CORROBORATION — say so.** All 8
  "never worked" pack materials are 4-component and both that DO work (washer
  `display_lcd`, sumo `name_lcd`) are 3-component. But both working materials
  ALSO carry `emissive: true` AND `emissiveIntensityNits`, and all eight dead
  ones carry NEITHER. Within the pack, component count is perfectly confounded
  with flag+nits, so the pack data alone cannot separate "4 kills it" from "you
  need nits". **The calibration strip does all the actual work** — cells 01/02
  differ ONLY in component count, and cell 03 has flag AND nits AND is dead.
- **`emissive: true` IS A NO-OP — now tested where it can actually show.**
  Round 3 "proved" this by comparing two SATURATED cells at night (253.0 vs
  253.0), which has no discriminating power at all. Round 4 used adjacent
  same-row pairs at the two rungs that stay UNSATURATED at midnight:

  | nits | flag, night sRGB | no flag, night sRGB | clipped | linear difference |
  |---|---|---|---|---|
  | 180 | 213.0 | 213.0 | 0.00% | **0.00%** |
  | 60 | 140.0 | 140.0 | 0.00% | **0.00%** |

  Identical to the last digit, unsaturated, adjacent. (At noon the same pairs
  differ by −3.4% and +26%, but the WHOLE 60-nit noon signal is only 0.0019
  linear over control — which is +3.8 sRGB codes, not a sub-level quantity —
  and the flag-vs-no-flag DIFFERENCE inside it is sRGB 23.07 against 22.32,
  **0.75 of one level**. That difference is what sits under a code; round 5
  attached the clause to the wrong quantity. Either way noon cannot adjudicate
  this and should not be quoted.) Consistent with the shipped census: most
  live emissive stages omit the flag. **`emissiveFactor` with three components
  is sufficient on its own**; nits is how you CONTROL it, not how you enable
  it. A bare 3-component factor
  with no flag and no nits behaves like **~415–460 nit** (round 4 cell 01, no
  flag: 458 nit read off the day curve; round 3's no-flag cell gave ~415 and its
  with-flag cell ~440 — the FACTOR is doing the work, not the flag).
- **`emissiveMap` MULTIPLIES, per texel — the round-16 "it is a NO-OP" law is
  WITHDRAWN as a false negative.** It had two independent, each-sufficient
  defects. (a) The map was never COOKED (see the suffix law below). (b) Even if
  it had been, the test had ZERO discriminating power: the map was 128×128
  uniformly (255,255,255), so white × factor `[1,1,1]` = `[1,1,1]` — "multiplies"
  and "ignored" predicted IDENTICAL pixels. Round 4 re-tested with NON-UNIT maps,
  all cells sharing factor `[1,1,1]` + flag + 1800 nit (day, linear over control):

  | cell | emissive map | displayed linear | ratio to white |
  |---|---|---|---|
  | `12 MAP WHITE` | uniform 255 | 0.108595 | 1.000 |
  | `13 MAP GREY50` | uniform 128 | 0.020727 | **0.191** |
  | `16 1800 NIT` | none at all | 0.107664 | 0.991 |

  A grey map at half code renders at a FIFTH of the white one, not a half:
  **the map multiplies, and it is decoded as sRGB — but do that arithmetic
  THROUGH the curve.**
  Round 4 set the measured 0.191 beside 0.216 and 0.502 and called the first a
  match. It compared a ratio of READINGS to a ratio of TEXELS, which is only
  valid if the response is linear in nits — and the day curve in this very
  ledger proves it is not (3.171e-5 linear/nit at 60 nit against 5.981e-5 at
  1800 — `per_nit_e5` in `day_tone_curve`, a factor of 1.89 of superlinearity
  across the range in question). Run each hypothesis forward through the
  measured curve instead:

  | hypothesis | texel | implied emitted | predicted 13/12 reading ratio |
  |---|---|---|---|
  | map decoded as sRGB | 0.2159 | 388.5 nit | **0.163** |
  | map used linearly | 0.5020 | 903.5 nit | **0.466** |
  | *measured* | — | 443 nit (inverted) | **0.191** |

  So the effective texel the engine used is **0.246**. Against that, the sRGB
  hypothesis is out by **+14%** and the linear one by **−51%** — sRGB is
  wrong by a seventh, linear by a factor of two, so **the conclusion is safe
  and it is not close.** But the 0.191-vs-0.216 "near match" round 4 rested it
  on was a coincidence of two errors leaning the same way; the honest
  comparison is 0.191 measured against 0.163 predicted, and must be quoted
  that way.
  The residual +14% is one rung of evidence and is NOT separated here from DDS
  quantisation of the grey map, mip selection, or inversion error in the
  400–550 nit segment; it is enough to reject linear, not enough to fit a
  decode curve.

  **THE AUTHORING CONSEQUENCE, which is the point of knowing any of this:**
  a `.color` glow map is decoded as sRGB, so **a texel that should emit half
  the material's nits is written 188, not 128.** (`255·(1.055·0.5^(1/2.4) −
  0.055) = 188`.) Write 128 and you get ~22% of the material's light where you
  asked for 50% — less than half of what you intended.

  **The strong form of the multiplication claim** is cell `14 MAP SPLIT LR`,
  whose map is black on one half and white on the
  other — both states in ONE tile, so no per-cell confound (position, row,
  column, ordering, neighbour bloom) can touch it. At midnight the bright half
  reads sRGB **255.0** and the dark half sRGB **0.0**, in the same tile, at the
  same instant; at noon the ratio is 0.0116. **So a chase LED matrix, a lit
  glyph, a patterned sign face are all available from material alone** — this is
  the capability the false law was denying.
- **THE COOKABLE-SUFFIX LAW: a texture whose middle suffix BeamNG does not
  recognise is skipped SILENTLY, and the material that references it samples
  nothing.** This was the pipeline bug behind the whole `emissiveMap` false
  negative, and it is the more valuable finding of the two.
  `proplib/texture_kit.py` wrote glow maps as `<base>.emissive.png`. Nothing in
  the engine consumes that name: no `.dds` is produced, no warning is logged, no
  error is raised, and the uncooked-texture gate can never clear because the cook
  that would produce the DDS never happens.
  - **THE COOK LEDGER — 209 in, 208 out, and the one missing file names
    itself.** This is the proof; everything else is corroboration. Count the
    texture PNGs in the probe zip that the game actually loaded, then count the
    imports in that run's `beamng.log`. They must balance, and they do not:

    | | count |
    |---|---|
    | `textures/*.png` shipped in the probe zip | **209** |
    | …`.color` / `.data` / `.normal` | 71 / 69 / 68 = **208** |
    | …`.emissive` | **1** (`..._calib_15.emissive.png`) |
    | `"started importing"` lines in `beamng.log` | **208** |
    | …`.color` / `.data` / `.normal` | **71 / 69 / 68** |
    | texture WARNINGS in the run | **1**, an unrelated `art/skies/clouds/…` path fixup |
    | texture ERRORS in the run | **0** |
    | log lines mentioning `.emissive` **anywhere** | **0** |

    The import histogram matches the shipped histogram SUFFIX BY SUFFIX, not
    merely in total. Exactly one file went in and did not come out, it is the
    one with the unrecognised middle suffix, and the engine said nothing about
    it — no warning, no error, not even a mention of the name. That is the
    whole law: **an unrecognised middle suffix is skipped silently.** Reproduce
    with `D2_cook.py`.
  - **THE CELL-15 PIXEL PAIR IS NON-DISCRIMINATING — DO NOT CITE IT.** Round 4
    also shipped cell 15 as a byte-identical twin of cell 12 differing only in
    the filename, and offered the resulting pixels as the proof. They are not
    proof of anything. The map was uniformly WHITE, so "the map cooked and
    multiplied by 1.0" and "the map never cooked and nothing multiplied" make
    the SAME prediction; measured oldname/white = 1.0001 and
    oldname/no-map-at-all = 1.0089, which is consistent with both. Round 4's
    own spec comment diagnosed exactly this failure mode for round 3's
    `emissiveMap` no-op — and then rebuilt it. The discriminating version is a
    GREY map under the old filename (0.021 if it cooks, 0.109 if it does not, a
    5× separation); it was NOT captured this round, because the cook ledger
    above already settles the question and a fresh capture costs a whole
    session. If anyone re-opens this, run the grey twin, not the white one.
  - **Stock never hits it.** Of **20,959** shipped images the middle suffixes are
    bare (7,643), `.data` (5,420), `.color` (3,945), `.normal` (1,916),
    `.imposter` (924), `.imposter_normals` (924), `.hdr` (162), `.depth` (18)
    and 7 stragglers with a numeric or one-off segment. Those classes **sum
    to exactly 20,959**, which is the check that makes the census a census
    rather than a sample — round 4 published 20,958/7,642 and the review
    re-derived 20,959/7,641, and neither showed a closure. **ZERO shipped
    images are named `*.emissive.*`**, over every zip in the install.
    Of 447 stock `emissiveMap` values, 376 end `.color.png` and 15 `.data.png`
    (the rest are `@`-prefixed runtime textures). Stock separates a glow map from
    its albedo by the BASE name, not the suffix — `autobello_lights_g.color.png`
    beside `autobello_lights.color.png`.
  - **Fixed** in `texture_kit.py`: glow maps are now `<base>_glow.color.png`,
    which matches both stock practice and the kit's own `_roughness.data.png`
    precedent. `.color` rather than `.data` because a glow map is authored in
    sRGB and is allowed to be tinted. (Cannon Car Wash had independently got
    this right with `_sign_emissive.data.png` — a working emissive map on a
    shipped, live-verified mod, and the counter-example that should have been
    noticed two rounds ago.)
  - **THE ORPHANS, COUNTED PROPERLY: 22 files, and they ship nowhere.** The
    round-4 disclosure said 15, which was one mod's share, not the total. On
    disk today: `pachinko_tower` 15, `sumo_gyro_platform` 5,
    `gforce_centrifuge` 1, `hot_potato` 1 = **22 `*.emissive.png`**. The
    reassuring half is verified, not assumed: **0 entries whose name contains
    `emissive` across all 19 `dist/*.zip`** (999 entries in total). They are
    uncooked, unreferenced, unshipped bytes sitting in source trees — dead
    weight to delete on the next rebuild, not a live defect. `prop_builder.py`
    dropped them for the RIGHT REASON (the material declares no emission) and
    described them in the present tense as the live drop-set, which stopped
    being true when `texture_kit.py` moved to `_glow.color.png`; that comment
    is now marked historical.
  - **WHY IT HID FOR TWO ROUNDS.** Every glow map the pack had ever authored
    was uniformly WHITE, and a white
    map is invisible either way — cooked it multiplies by 1.0, uncooked it
    multiplies by nothing. **A NULL TEST CANNOT FIND A BROKEN PIPELINE. Author
    the probe non-unit or do not bother.**
- **`emissiveFactor` still tints once nits is driving.** `19 RED 1800` with factor
  `[1.0, 0.12, 0.06]` at 1800 nit reads sRGB 53.6 at noon against the white
  1800-nit cell's 95.0, and renders red — per channel `[91.0, 37.0, 32.9]`.
  Colour-coded material glow is available. **BUT THE TINT IS A DAYLIGHT
  PROPERTY AT THIS BRIGHTNESS.** The same cell at midnight reads
  `[255.0, 255.0, 252.0]`: two of its three channels are saturated, so a
  material authored to glow red renders very nearly WHITE at night. (That is
  where its 66.67% saturated figure comes from — two channels of three, not
  two thirds of the tile.) If the hue has to survive darkness, drive the nits
  down into the night band below, or the exposure will bleach the tint out.
- **NEVER READ A DAYLIGHT DELTA AS GLOW — READ IT AT NIGHT.** `18 CFUGE AMBER` is
  **+115.0 sRGB over control at noon** and **sRGB 0.0 at midnight**. It is the
  only cell in the strip with a bright `baseColorFactor`, so that +115 is
  entirely ALBEDO: a cream panel in sunlight, no emission whatever. Round 3's
  factorial table printed exactly this number beside the verdict DEAD and did not
  annotate it. **That misreading — a bright daylight surface mistaken for a
  glowing one — is what created the original false law.** At midnight the control
  reads exactly 0.0, which is why night is the discriminator and noon is not.
- **THE NITS → APPEARANCE CURVE AT NOON** (`TimeOfDay` 0.00, smallgrid, GT7 SDR
  tonemapper; the unlit control of the same base surface reads sRGB 19.3).
  "displayed linear" is the sRGB-decoded frame value minus THE CONTROL CELL.
  Rungs ≤1800 are round 4, above are round 3; the two rounds agree to +0.6% at
  1800, +3.4% at 800 and −3.7% at 180, which is what licenses the splice (they
  differ by +11.6% at 60 nit, deep in the toe where the signal is 0.0019):

  | nits | sRGB | +over control | displayed linear | vs proportional (1800 = 1.00) |
  |---|---|---|---|---|
  | 60 | 23.1 | +3.8 | 0.001903 | 0.530 |
  | 180 | 31.2 | +11.9 | 0.007103 | 0.660 |
  | 240 | 34.6 | +15.3 | 0.009749 | 0.679 |
  | 320 | 39.3 | +20.0 | 0.013856 | 0.724 |
  | 400 | 43.9 | +24.6 | 0.018304 | 0.765 |
  | 550 | 51.4 | +32.1 | 0.026882 | 0.817 |
  | 800 | 63.8 | +44.5 | 0.044233 | 0.924 |
  | 1800 | 95.0 | +75.7 | 0.107664 | 1.000 |
  | 3500 | 126.0 | — | 0.202744 | 0.968 |
  | 15000 | 217.0 | — | 0.687959 | 0.767 |
  | 30000 | 252.0 | — | 0.967540 | 0.539 |
  | 50000 | 255.0 (100% clipped) | — | 0.994095 | 0.332 |

  A textbook filmic response, and the last column is how you read it. **TOE**
  at the bottom: 60 nit returns 0.53 of what proportionality would give, and the
  shortfall closes monotonically upward — 800 nit is STILL 7.6% under, so 800 is
  the top of the toe and not the bottom of the straight part. **NEAR-LINEAR
  1800–3500, and only there** — those two rungs sit within 3.2% of proportional.
  **SHOULDER** from ~15000 (0.77), hard clip between 30000 and 50000 (30000 reads
  sRGB 252 with no subpixel at 255 at all; 50000 is 100% saturated).

  That column is `(v/anchor)/(n/1800)` against the round-4 1800-nit cell, and
  every cell of this table is now GENERATED by `E_r6_table.py` straight out of
  `r17_analysis.json`, and required to appear in this file as ONE CONTIGUOUS
  BLOCK, verbatim, in the raw text — which is also how round 6's malformed
  splice of it was caught: that verifier COUNTS each needle instead of merely
  finding one, so a duplicated header fails as an ambiguity, and it parses
  every markdown table in this section for exactly one header, one separator,
  a uniform column count, and — round 8 — the SEPARATOR'S OWN column count.
  **Round 7 checked this table ROW BY ROW, which is a comparison against a
  MULTISET OF LINES: swap the 60-nit and 30000-nit rows and every count is
  preserved, so the gate read 95/95 over a scrambled tone curve.** Order is
  now asserted directly — contiguously for the noon table, and as an
  ascending-position check for the night ladder, whose editorial bolding
  means it cannot be regenerated verbatim. The same round-7 blind spot ran
  through the structure pass (the separator was checked for existence and
  position, never for its width, so narrowing it from five columns to four
  broke the rendering and passed) and through coverage (thirteen figures this
  JSON sources appeared here with no needle at all, including the ply clean
  box, the noon split ratio and the published clean-ply figure). The
  check list is now
  GENERATED from the JSON's leaves, and a leaf that renders into this section
  without a needle is a FAILURE unless it is named as a coincidence with a
  reason.

  **ROUND 9: FOUR CHECKS THAT PINNED A VALUE WHERE THE PROPERTY WAS A PLACE.**
  All four round-8 mechanisms worked exactly as advertised — not one round-7 or
  round-8 mutation slipped past them — and all four were the wrong shape, in
  the same way. `want_raw` pinned the noon table's CONTENT by substring, so a
  fabricated row APPENDED below it left the generated block intact and passed.
  `want_order` pinned the night ladder's SEQUENCE by ascending find positions,
  so an extra rung SPLICED between two real ones passed — including
  `| 450 | 255.0 | 0 | 22,470 | 100% |`, a measurement planted inside the very
  interval this section's own conclusion declares unmeasured. The coverage gate
  asked whether a figure's digits appear inside some needle's TEXT rather than
  whether a needle covers its SITE, so one needle spelling `400` marked all
  nine occurrences of `400` covered — it reported zero gaps while **86 sites
  were physically untouched**. And the coincidence list was keyed on the
  STRING, which bans it everywhere: exempting `209` for the cook ledger removed
  the gate from every `209` in the section. Twenty-two of thirty-eight
  mutations passed at **102 of 102**, and among them the night section's
  headline conclusion swapped end for end, `254 IS NOT CLIPPED` inverted, and
  ten of eleven table headers rewritten. **The lesson is not that the
  instruments were broken. It is that each closed the specific hole it was
  shown instead of the class that hole belongs to** — which is the failure
  round 7 named correctly and round 8 then committed.
  So: the noon block is now compared against the ledger's MAXIMAL table block
  (extent, not containment); every one of the eleven tables is pinned by
  header text, separator, row-label ORDER and row COUNT, three of those
  sequences DERIVED from the JSON and eight declared literals that are labelled
  as declared; coverage is computed on character OFFSETS, all 278 sites
  individually accounted; exemptions are (region, string) pairs scoped to one
  passage; and the section's two load-bearing sentences — the
  highest-unsaturated/lowest-saturated conclusion and the `254 IS NOT CLIPPED`
  verdict — are now DERIVED from `night_ladder` rather than quoted, so a
  sentence cannot disagree with the table above it. Round 6's 98 checks were a presence
  test, not a correspondence test: 38 of its needles were eight characters or
  fewer, four separate checks all reduced to the string `| 255.0 |`, and one
  of those four was not a row of the table it claimed to check. Single-cell
  mutations passed 98 of 98. The ROUND-4 factorial table is also sourced now
  — `factor_array_factorial`, 19 cells — leaving only the ROUND-3 midnight
  table genuinely unsourceable from this JSON, which the verifier declares
  rather than skips. — `day_tone_curve[*].vs_proportional_on_1800` for the
  round-4 rungs (asserted equal to the recomputed value), `round3_day_curve`
  above 1800. Round 5 typed it by hand and the seven rungs ≤800 came out a
  uniform 0.605× the JSON: one column carrying two different normalisations,
  the lower half of it unsourced, and directly contradicting the sentence
  beneath it. The sRGB and displayed-linear figures above 1800 nit are round
  3's, referenced to round 3's OWN control cell, which is why their "+over
  control" is blank rather than zero.
- **Named daylight thresholds — MEASURE THE REFERENCE ON A CLEAN PATCH, AND DRAW
  THE BOX.** Against its own unlit control at noon a cell is *marginal* at 60 nit
  (+3.8 sRGB), *clearly a lighter panel* at 180 (+11.9), and *unmistakable* at
  800 (+44.5). To read as bright as a real sunlit surface, invert the curve —
  but round 3's three reference boxes were hand-typed, never drawn on the
  overlay, and one was badly contaminated by dark structure INSIDE the box:

  | reference | raw box | → nit | clean patch | → nit | note |
  |---|---|---|---|---|---|
  | sky at zenith | sRGB 105.1, std 3.4 | 2468 | sRGB 102.0, **std 1.1** | **2314** | raw 6.7% HIGH (clouds) |
  | sunlit ground plane | sRGB 185.4, std 14.7 | 9904 | sRGB 186.6, std 9.7 | **10013** | raw 1.1% low |
  | sunlit blonde ply (prop's own) | sRGB 102.6, std 37.7 | 2624 | see below — **a range, not a number** | | |

  So *"looks like a lamp at noon"* costs roughly **2.3 k nits** (sky) and
  *"out-reads the sunlit ground at noon"* roughly **10 k**.

  **TWO CORRECTIONS THAT MOVE ALL THREE FIGURES, and one that kills a
  reference outright.**
  1. *Subtract the control before inverting.* The curve maps nits → displayed
     linear OVER CONTROL, and rounds 3–4 fed it a reference's ABSOLUTE
     displayed linear. The question is "what nits make a CELL read as bright as
     this surface", and a cell reads control + f(nits), so f(nits) =
     reference − control. Small (control = 0.0068 linear) but one-directional:
     every previously published day-match figure was HIGH, by **1.6% to 5.0%**
     — on the clean patches, ground 1.6%, ply 3.7%, sky 5.0%; on the raw boxes,
     ground 1.6%, ply 4.5%, sky 4.7%. Round 5 wrote "2–5%" here and "2-4%" in
     the code comment; the first excludes ground at both ends of the pack and
     the second also excludes sky. In a ledger whose thesis is *quote the
     interval*, two stated intervals and neither one correct. The numbers above
     are corrected; the old ones survive in the JSON as `*_uncorrected`, so the
     real interval is re-derivable from `day_match_nits` alone.
  2. *std does not find a groove.* Round 4's "clean" ply box `[1880, 921, 1904,
     933]` carried std 8.2 against the sky patch's 1.1 and nobody read the
     tell. **72.5% of that box's own pixels are inside a plywood groove** — its
     full 12-row profile, `round4_box_row_profile` in the JSON, is 125.5,
     121.5, 122.6, 126.5, 125.2, 120.8, 118.4, 112.8, 112.2, 116.6, 120.9,
     122.8: a 14-code trough across rows 4–9, not a flat panel. Median-of-
     windows is robust to outliers but NOT to a dark linear feature crossing
     most of the candidate windows: the median of a contaminated population is
     just a typical contaminated value. Round 5 flags groove pixels explicitly
     (a pixel more than 10 sRGB below the local median along its row OR its
     column, dilated), then admits only windows containing none —
     `groove_mask()` / `masked_population()` in `r17_analyze.py`. **69% of the
     whole ply column is groove, seam or beam shadow.**
  3. *The ply is not one brightness, so it was never one number.* Like-for-like
     — a groove-free box in the SAME inter-beam band, `[1883, 934, 1897, 946]`
     — reads sRGB 131.7 → **4097 nit**, against the published 3382: the old
     figure was **~17% low**, not "clean". But sampling the groove-free
     population down the whole column shows the panel's own shading gradient
     runs sRGB 126.6 → 161.3, i.e. **3.5 k → 6.7 k nit**, with **11 of its 14
     bands inside 3,523–4,413 nit** and the other three at 4,930, 5,704 and
     6,735. (Round 5 wrote "12 of its 14 between 3.5 k and 4.9 k"; the
     4,930-nit band is above 4.9 k, so it is 11 — `column_gradient` in the
     JSON, counted rather than eyeballed.) There is no fourth-significant-figure
     answer here and there never was. **Quote the ply as ~3.5–5 k nit or not at
     all — and prefer not at all:** it is a PROP-OWNED surface whose texture set
     is not stable across rebuilds, while the sky and ground are SCENE-owned.
     Note the honest hierarchy of the three: sky std 1.1, ground std 9.7, ply
     69% masked. **The flattest reference is the trustworthy one.**

  `r17_overlay.png` draws all three raw boxes, all three round-4 clean patches
  and the round-5 groove-free ply box in magenta; `r17_ply_zoom.png` is a 6×
  crop with the rejected box and its replacement side by side, so the groove is
  visible rather than asserted. **Never quote a reference brightness from a box
  that has not been drawn — and never from one whose std says it is dirty.**
- **THERE IS NO SINGLE NITS VALUE THAT WORKS DAY AND NIGHT.** Auto-exposure moves
  under you: the same 1800-nit cell is a mid-grey panel at noon (sRGB 95) and a
  fully clipped white blob at midnight. **The night ladder, MEASURED** (round 3
  quoted "~30–500 nit" from two points and extrapolation at both ends; these are
  rungs, not a fit):

  | nits | night sRGB | subpixels @254 | @255 | saturated |
  |---|---|---|---|---|
  | 60 | 140.0 | 0 | 0 | 0.00% |
  | 180 | 213.0 | 0 | 0 | 0.00% |
  | 240 | 230.0 | 0 | 0 | 0.00% |
  | 320 | 245.0 | 0 | 0 | 0.00% |
  | 400 | **254.0** | **22,470 of 22,470** | **0** | **0.00%** |
  | 550 | 255.0 | 0 | 22,470 | **100%** |
  | 800 / 1800 | 255.0 | 0 | 22,470 | 100% |

  (22,470 subpixels = the 7,490-pixel sampling window, 55% of the tile in each
  axis, × 3 channels; the census is `saturation` on every cell in the JSON, so
  any window can be re-checked.)

  **254 IS NOT CLIPPED.** Rounds 1–4 counted `>= 254` as clipped, which is
  wrong: 254 is the second-brightest code an 8-bit channel carries and a cell
  sitting flat at 254 still has a level of headroom. The 400-nit tile is
  22,470 of 22,470 subpixels at EXACTLY 254 with NONE at 255 — unsaturated, and
  visibly not yet a white blob. The 550-nit tile is 22,470/22,470 at 255 — that
  is saturation. Re-deriving every `clipped_pct` in `r17_analysis.json` under
  the corrected predicate moved **exactly one cell of eighty** (`D1_diff.py`):
  night `10 400 NIT`, 100.00% → 0.00%. Nothing else moved, and in particular
  neither `14 MAP SPLIT LR` (49.53%) nor `19 RED 1800` (66.67%) rode on the
  threshold — their saturated subpixels are at 255 with zero at 254, so those
  figures were always right. No rung entered or left the curve inversion.

  So: **the highest rung measured UNSATURATED is 400 nit and the lowest
  measured fully saturated is 550**; saturation begins somewhere in the open
  interval **(400, 550]**, and nothing inside that interval has been measured.
  The usable night band is therefore roughly **60–400 nit**, with the FLOOR
  still unmeasured — 60 nit reads sRGB 140 with plenty of modelling left, so
  the real floor is well below 60 and "30" was invented. Note how this went
  wrong twice in opposite directions: round 3 guessed "~500" with no
  measurement, round 4 replaced it with a measured-sounding "320/400" that
  EXCLUDED the truth the guess had happened to contain. A rung ladder gives an
  INTERVAL; quote the interval. The usable noon band is roughly
  **1500–15000**. They do not overlap — that CONCLUSION was always safe, and it
  is the one that matters. Pick the condition that matters, or drive nits from
  Lua per time of day.
- **Bloom is screen-space, tight, and only starts at saturation.** Measured at
  midnight outward from a tile edge onto pure black (0.00000): the unlit control
  and round 3's `12 FACTOR3 ONLY` (sRGB 253, unclipped) show 0.00 at every distance; 800 nit
  (clipped) gives sRGB 8.9 at 10.6 px and 0.0 by 21 px; 15000 nit gives 97.6 at
  10.6 px, 7.2 at 21 px, 0.0 by 42 px. So the halo appears only once the cell
  saturates and grows with how far past saturation it is, and even at 15000 nit it
  is ≲ 3% of frame height. Do not design around bloom as a glow-spreader.
- **LIGHT OBJECTS: the field census and the calibration law.** From 4,202 shipped
  `PointLight`/`SpotLight` instances in `west_coast_usa`, `italy` and `glow_city`.
  Real fields: `intensity`, `intensityUnit` ("cd"/"lm"/"ev"), `radius` (PointLight)
  / `range` (SpotLight), `innerAngle`/`outerAngle`, `color`, `brightness`,
  `castShadows`, `shadowType`, `attenuationRatio`, `useColorTemperature`,
  `colorTemperatureKelvin`, `colorTemperatureFilamentId`
  (sodium|mercury|warmLed|phosphorLed), `colorTemperatureDegradation`,
  `dayIntensity`/`nightIntensity`, `nightLight`, `isEnabled`, `flareType`/
  `flareScale`, `animationType` (FireLightAnim|SpinLightAnim), `animationPeriod`,
  `animationPhase`, `texSize`, `priority`.
  **THE CALIBRATION LAW, 3269 of 3269 paired instances, zero exceptions:
  `5000 cd == brightness 1.0`.** SpotLight `intensity` is candela
  (`brightness = intensity / 5000`); PointLight `intensity` is lumens
  (`brightness = intensity / (4 * pi * 5000)`). **`intensityUnit` is
  PRESENTATIONAL** — spots tagged `"lm"` still store candela, so never branch on
  it. Reproduce with `probe_light2.py` (field census) and `probe_calib.py`
  (the 5000 fit) — both walk the level ZIPs' JSON/JSONL and need no running game.
- **Material key spelling, since two rounds have got it wrong.** It is `Stages`
  (capital S) and `emissiveIntensityNits`. Stock `etk800_glass_on` = `emissiveMap`
  + `emissiveFactor` + `emissiveIntensityNits: 15000` + `translucent: true`.
  Shipped nits values cluster at 50/75/100/150/200/500/1000/7500/10000/20000, so
  the ladder above brackets the whole range anyone ships. `probe_mat2.py` dumps
  the stage-field census from `gameengine.zip` and a vehicle ZIP.
- **The generator writes whatever length the palette gives it.**
  `proplib/prop_builder.py` does
  `stage0["emissiveFactor"] = [round(float(c), 6) for c in entry["emissive"]]` and
  reaches `emissiveIntensityNits` only through the raw `stage` passthrough. A
  palette entry that wants glow needs a THREE-element `emissive` and, if the
  brightness matters, `"stage": {"emissiveIntensityNits": N}`. And if it wants a
  PATTERNED glow it needs a texture family that returns a 5th (emissive) channel
  — which `texture_kit.py` now writes as `<base>_glow.color.png`, per the
  cookable-suffix law above.
- **ROUND 6: HAND-TRANSCRIPTION IS NOW THE LEADING DEFECT SOURCE IN THIS
  LEDGER. IF A SCRIPT CAN PRINT IT, DO NOT TYPE IT.** Round 6 found no new
  measurement error and no new reasoning error. Every defect it found was a
  correct number in `r17_analysis.json` that arrived here altered by a human
  hand: the whole lower half of the noon curve's last column (above), the
  320-nit sRGB cell (39.4 → 39.3), the map-decode slope pair
  (3.24e-5 / 5.99e-5 → 3.171e-5 / 5.981e-5, and with it the superlinearity
  factor 1.85 → 1.89), the control-subtraction interval (2–5% → 1.6–5.0%), the
  ply band count (12 of 14 → 11 of 14), the ply box's std (8.24 → 8.2) and
  groove fraction (72% → 72.5%), the sky and ground raw-box errors (6% → 6.7%,
  1% → 1.1%), and in `r17_analyze.py` a `clip()` docstring still quoting
  25,752 subpixels for a window the same file measures at **22,470**
  (107×70×3) — in the very script this ledger names as the reproduction path.
  None of these changes a conclusion. That is the point: the conclusions
  survived six passes and the TRANSCRIPTION did not, so the defect class to
  design against is no longer bad physics, it is a keyboard between a JSON file
  and a markdown table.
- **ROUND 6: OPEN DEBT, TWO VERIFIER TRAPS, AND THE VERSION LAW APPLIED BY
  CLASS.**
  - **OWED TO THE NEXT REBUILD — a false claim that is already DISTRIBUTED.**
    `hot_potato/spec.py:345` emits the Lua comment
    `-- explodes. Confirmed live on 0.38.6.` verbatim into generated
    `mod/lua/.../runtime.lua:576` **and into the shipped
    `dist/hot_potato_ericrolph.zip` at that same line, where it is the only
    version string in the archive.** Rounds 5 and 6 both left it deliberately:
    editing the source without regenerating desyncs source from artifact, and
    neither round was permitted to rebuild. So it is not handled, it is DEBT.
    **Whoever next rebuilds `hot_potato` must correct the source string and
    re-pack in the same pass** — same correction as everywhere else, `0.38.6`
    was the test PROFILE DIRECTORY name and never an engine.
  - **TRAP 1 — stale worktrees.** `.claude/worktrees/unruffled-turing-15bf66/`
    and `.claude/worktrees/funny-euclid-f97552/` each hold a COMPLETE
    pre-remediation copy of `AGENTS.md`. A grep-based verifier run without
    `--exclude-dir=.claude` finds uncorrected originals of all 14 version sites
    and will report the round-5 sweep as never done. Exclude `.claude/`,
    `workspace/` and any vendored venv (`.wheel-smoke/`) from every census over
    this repository; `D_lineendings.py` now does.
  - **TRAP 2 — the extension set, and a CRLF shebang is not cosmetic.** The
    round-5 line-ending census carried no shell suffix, so
    `sumo_gyro_platform/authoring/mix_call_audio.sh` — pure CRLF, shebang
    included — was invisible to the giant_props scan AND the repo-wide one.
    On Linux the kernel hands the trailing CR to execve and the script dies
    with `bad interpreter: /usr/bin/env bash^M`. Converted to LF in round 6,
    content otherwise byte-identical. `D_lineendings.py` now covers
    shell/batch/PowerShell suffixes and separately reports EXECUTABLE TEXT
    whose newlines are CRLF, which must be zero. **Both scopes now print on a
    bare `python D_lineendings.py`** — in round 6 the repo-wide figure quoted
    here needed an undocumented `--repo` flag, so the number in the ledger was
    not the number the default run produced, which is the same defect as a
    census that does not state its extension list. Counts under the widened
    set, measured after the conversion: giant_props **13 PURE_CRLF**, repo-wide
    (ex-`workspace/`, ex-`.claude/`, ex-vendored-venv) **15**, MIXED **0**,
    CRLF-shebang **0**. Under the round-5 extension set the same tree reads 13
    PURE_CRLF, and a reviewer scanning a narrower set read 11 — three
    different numbers, all honest, because the file-set differs.
    **A line-ending census is only as wide as its extension list — state the
    list, or the count means nothing.**
    **AND THE DENOMINATOR IS NOT A CONSTANT.** Those four figures are stable;
    the file COUNTS they are out of are not. Round 6 wrote "13 of 223" and
    "15 of 393"; re-running the same script unchanged in round 7 gives 13 of
    **224** and 15 of **394**, because a concurrent session added
    `football_goal_post/authoring/stage_upload.py` in between. Nothing was
    wrong and nothing was fixed — the tree grew. In a repository other agents
    are editing live, a ratio quoted without a timestamp turns into a false
    number with nobody having touched it. Quote the numerator, the rule that
    produced it, and when.
  - **THE VERSION-SWEEP EXEMPTION IS BY CLASS, NOT BY DIRECTORY.** A CENSUS
    ("the engine does not contain X") must carry the build it ran on. A SUPPORT
    PIN ("the baseline is BeamNG 0.38") is a declaration of what this project
    targets, not a measurement of an engine, and moving it to 0.39.4.0 would
    assert support that has never been validated — the release matrix above
    says in terms that it has not been re-run since the install moved. Applied:
    `examples/cannon_car_wash/blender/create_cannon_car_wash.py` stated the
    SAME census as this file's `BNG_*` line ("BeamNG 0.38.6 does not contain
    the three user-facing semantic labels") and is CORRECTED in round 6 —
    "cannon_car_wash was left alone deliberately" was a directory-shaped
    exemption under a class-shaped law. `README.md` and
    `.github/ISSUE_TEMPLATE/bug_report.yml` KEEP 0.38, because both are pins;
    README gains one clause so the pin cannot be misread as the engine in use.
    **AND THE SWEEP THAT CHECKED THIS IS A CENSUS, NOT A GATE — round 9,
    stated so the next reader does not over-trust it.** `G_r8_sweep.py` places
    every surviving occurrence — **78 on 75 lines as this paragraph is
    written**, and 75 on 72 before it was, because writing this bullet added
    three mentions; the count is a measurement of a moving tree, so re-run it
    rather than quoting it (three lines carry two occurrences; it
    used to count lines and report them as occurrences, and on
    `hot_potato/DESIGN.md:31` the class it printed described only one of the
    two while the `"0.38.6"` beside it went unclassified — it is per-occurrence
    now, with a column). Every occurrence matches exactly one declared class
    and none is placed by a path alone. That is a true statement about the tree
    as it stands and it is what certified the de-attribution. It is **not** a
    defence against future writing: four of its ten rules narrow on no path,
    five predicates are bare keyword or shape presence, and a critic took seven
    synthetic law-violating sentences and **added one ordinary word to each** —
    a word from the record-marks list, a pair of quotes, the word "harness" —
    and **six of seven were placed silently**. Round 8 had exchanged a
    directory exemption for a word exemption. No eleventh rule fixes that,
    because these are predicates over one line of text and the property they
    want is what a sentence MEANS. Use it to audit what exists; do not use it
    to bless what is added.

### What round 9 leaves safe to rely on, and what it does not (2026-08-15)

**This section is the product of the nine verification rounds. Read it before
trusting any number above, and before building a new check on top of one.**

SAFE TO RELY ON — measured, re-derivable, and adversarially tested:

- **Every figure in this section that `r17_analysis.json` can source.** 109
  checks, each a counted, row-anchored needle; the tables are compared against
  text regenerated from the JSON. Re-run `E_r6_verify.py`.
- **The shape of all eleven tables** — header text, separator, row-label order
  and row count. A swapped row, a spliced rung, a transposed `@254`/`@255`
  header or a deleted table fails. Three sequences are DERIVED from the JSON;
  **eight are declared literals and pin drift only**.
- **Site coverage.** EVERY ledger site of every sourceable figure is
  individually accounted — needled, pinned by a table header, inside a declared
  region, or a prose instance of a declared class — with **zero unaccounted**.
  The site total moves as this section is edited (it read 278 before this
  closing section was written and 290 after, and writing the round-9
  post-mortem above put a deliberately fabricated rung into the prose, which
  the gate flagged on its first run and which is now a declared region). The
  invariant to quote is the zero, not the total.
- **The night section's two headline claims** — highest unsaturated 400 /
  lowest saturated 550, and `254 IS NOT CLIPPED` — are derived from the ladder,
  not typed beside it.
- **The de-attribution census**: **78 occurrences of `0.38.6` on 75 lines**
  (three lines carry two), each in exactly one class, none by directory.
- **`AGENTS.md` reconstructs from recorded edits — as a MEASUREMENT WITH A
  TIMESTAMP, not a property of the file.** It reconstructed to **+109 bytes at
  02:44Z against sha `1b95c7bc…`**, before this closing section was written,
  with the 6,943-byte foreign `PROPLIB BUG` section named and subtracted.
  Re-running the reversal on the file as shipped gave **+16,576 raw**, and
  **+9,633** after that subtraction, at sha `20ca33a2…` — because two of round
  9's own closing-section edits are no longer reversible in greedy order, later
  edits having overwritten their spans. **Every one of those numbers is
  stamped, and every one is already stale: re-derive the residue, never quote
  it.** This bullet originally quoted +109 flat, with neither hash nor time —
  the exact sin the last bullet of this section forbids, committed inside the
  section that forbids it, and caught only because someone re-ran the script
  instead of reading the number. The round-9 run that would have shown the
  drift was piped through `tail -32`, which cut the RESIDUE line off. **A
  filter that hides the one line you are accountable for is not a convenience;
  it is how a stale number survives a re-run.**
  What survives unchanged is the NEGATIVE result, and it is now DERIVED rather
  than asserted: `phantom_check()` reverses twice, once with the six
  aborted-command pairs dropped and once with them restored, and the sentence
  is chosen by whether the two reconstructions match. Round 9 had first written
  that conclusion as the literal "the residue is still exactly +109", printed
  unconditionally — the identical hard-coded-verdict defect this round was
  convened to remove from this very file, reintroduced eighty lines below the
  fix, in the same round, by the same hand. **The defect you just corrected is
  the one you are most likely to commit next.**
- **The suite runs clean under the repo venv, but only on a quiet tree.**
  `.venv\Scripts\python.exe -m pytest` — four runs in the same half hour gave
  **827 passed / 0 failed** twice, **826 / 1** once and **825 / 2** once, in
  27–54 s. Round 8 reported "522 passed, 33 failed, 61 skipped, 24 collection
  errors" and attributed all of it away: that was **the system interpreter**,
  and ~300 tests never executed. Use the venv.
  What did NOT reproduce is the round-8 story attached to it. Every failure
  across all four runs sits in `tests/test_giant_props_pack.py` on the harvest
  and texture-rebuild tests, and `test_certified_harvest_still_ships_dds`
  **passes in isolation**. That is consistent with another session rewriting
  the pack underneath the run — `D_integrity.py` counts 585 files changed by
  other sessions during this round — but **consistency is not causation and
  round 9 did not establish it**. Round 8 wrote "1 = a texture rebuild by the
  concurrent lighting session" as though it had. Quote the spread and the
  interpreter; do not name a cause you did not measure.

NOT GUARANTEED — and a future round must not read a clean run as covering these:

- **Prose that carries no number is unverified.** A fabricated sentence such as
  "a further tile was observed just under saturation" passes every check.
- **Anything the JSON cannot source is checked by nothing** — it is LISTED, not
  verified. That **includes** the round-3 midnight factorial table, the
  bloom-vs-distance measurements, the light-object censuses, the zip/material
  censuses, the TEXTURE-COOK LEDGER census (209 / 208 / 71 / 69 / 68 / 1 / 0)
  and the capture geometry. Corrupt a figure inside any of them and the gate
  stays green, by construction: the gate walks JSON leaves into the ledger, so
  a figure with no leaf is invisible to it — mutating the cook ledger's
  `**209**` to `**210**` passes, and silently drops the site total by one.
  **Read that list as "includes", not "is".** It was written as an exhaustive
  enumeration and was not one; the governing rule in the sentence before it is
  what carries the guarantee, and an enumeration that reads as complete
  quietly narrows a rule that is broader than any list.
- **Eight of the eleven table row-orders are declared, not derived.** They
  catch a change; they do not certify today's order is right.
- **A markdown row without a trailing pipe is invisible** to the structural
  parser. Inside the generated noon table the block comparison still catches
  it; anywhere else it would not.
- **The `0.38.6` sweep does not gate new writing** — see the paragraph above.
- **Round 8's four instruments each closed the hole they were shown.** The
  score to remember is not "22 of 38 missed" — it is that every mechanism
  worked as specified and none generalised. Round 9 wrote its own 28 fresh
  mutations rather than re-run the ones it was handed, and **its own battery
  found a defect in its own fix**: an unresolvable region END anchor silently
  widened an exemption to the bottom of the document, which is the very
  failure mode this round existed to remove. Whatever comes next: generate
  fresh adversarial cases before claiming a property, and where a general
  guarantee cannot be had, **state the narrow one**.
- **This file is edited by concurrent sessions while it is being measured.**
  AGENTS.md grew 164,262 → 175,095 bytes during one battery run and produced a
  results table whose rows were measured against different documents. Every
  instrument that reads it now hashes it before and after and voids its own
  output if it moved. Quote a number with the hash and the time, or not at all.

### Round 18: the repair (2026-08-15)

Round 17 corrected the documentation and the texture pipeline but not the
material data. Round 18 repaired the data. All eight 4-component arrays are
gone; every `emissiveFactor` the pack ships is now three components, asserted
by `test_emissive_factors_have_three_components` over the shipped
`main.materials.json` of every mod.

- **THE PALETTE LIVES IN THE HANDOFF, so a spec.py edit alone does nothing.**
  `build_materials` reads `handoff["palette"]`, which `blender_kit.write_handoff`
  froze at the last Blender run — editing `spec.py` and running `build.py <key>
  all` rebuilds materials from the STALE palette. The four repaired mods each
  needed their Blender generator re-run first. This is the same trap AGENTS.md
  already records for behavior/cage params, one aisle over; the new
  `check_emissive_factor` is what surfaced it, by raising on values that were no
  longer in the spec file being edited.
- **The nits chosen, and the principle: pick the CONDITION, then read the
  ladder.** There is no value that works day and night, so each material is
  tuned for the condition that matters to it, and area matters as much as
  intent — the largest emissive surface gets the lowest rung.

  | material | nits | tuned for |
  |---|---|---|
  | centrifuge `obs_glass` | 180 | night, unclipped (largest area on the pack) |
  | centrifuge `letter_glow` | 320 | night; brightest rung that does not clip, so the plates stay letter-SHAPED |
  | centrifuge `light_panel` | 800 | both; a diffuser may blow out after dark |
  | centrifuge `beacon_amber` / `beacon_cyan` | 1800 | DAYLIGHT conspicuity; night clip is correct for a beacon |
  | toaster `element_glow` | 800 | daylight (shaded slot); night saturation reads as red-hot |
  | spider `eye_glow` | 800 | small lenses, needs the level to register |
  | washer `drum_lamp` | 800 | matches its sibling `display_lcd` |

- **A FACTOR ABOVE 1.0 IS THE WRONG BRIGHTNESS CONTROL — normalise it.**
  `letter_glow` wrote `[2.0, 2.05, 2.1]` and `light_panel` `[1.5, 1.85, 2.2]`,
  both reaching for brightness through the factor. The factor TINTS and
  multiplies; nits sets the level. Both were divided by their max (hue exactly
  preserved) so the shipped nits value is the number you can actually read off
  the material. Stock does the same.
- **`emissive: true` was NOT added** — measured a no-op at both unsaturated
  night rungs (identical to the last sRGB digit), and most shipped stages omit
  it. A three-component factor is sufficient on its own.
- **The guard is a RAISE, not a truncate**, and it checks the FINAL stage dicts
  after the `stage`/`stage1` passthroughs merge, so the raw-key door is shut
  too. Truncating would have let an author keep believing the alpha means
  something, and the value they meant may not survive a trim — `letter_glow`'s
  repair was to normalise and move the level to nits, not to lop off the `1.0`.
- **WHAT IS STILL OPEN.** (1) No live look yet — the four rebuilt zips have not
  been seen in game (a hand-launched session held the GPU; `r18_capture.py` in
  the 2026-08-15 scratchpad is written and waiting, and captures night with
  every PointLight disabled so any bright pixel is material radiance). Round
  17's cells were verbatim copies of `beacon_amber` and `letter_glow` and read
  sRGB 0.0, so that is the BEFORE reading whenever the after is captured.
  (2) This visibly changes the PUBLISHED centrifuge — and **its listing copy
  DOES promise the glow, twice.** Rounds 3–5 all asserted the opposite; a
  round-5 sweep of every one of the 18 `authoring/listing_copy.md` files for
  glow/emissive/lit language found 15 with none at all, `pachinko_tower` with a
  DENIAL ("No screens, no fake glow"), and two with CLAIMS:
  `gforce_centrifuge/authoring/listing_copy.md:63` "glowing beacon" and `:81`
  "lenses now genuinely glow while the beams sweep", plus
  `giant_toaster/authoring/listing_copy.md:19,65` "glowing" elements. Now read
  what those two actually ship. The PUBLISHED centrifuge — the copy the player
  downloaded, `…\BeamNG.drive\current\mods\repo\gforce_centrifuge_ericrolph.zip`
  — carries all five emissive materials as **4-component with no nits**, i.e.
  provably dark by cells 02/03/18 of the strip; the player's installed
  `giant_toaster` and `spider_web_catcher` and the `drum_lamp` of
  `spin_cycle_washer` are the same. **So a published listing promises light
  that the published build cannot emit.** That is the one finding in this whole
  ledger with a player on the other end of it, and three rounds recorded its
  negation. It is not fixable by editing copy — the copy is already live on
  beamng.com and the rebuilt zip now makes it TRUE — so the fix is a live look
  followed by a republish, and nothing was republished here. (For contrast, the
  two materials that always worked are 3-component: the washer's `display_lcd`
  and sumo's `name_lcd`, both verified 3-component with nits inside the
  player's own installed zips.) (3) The four mods now ship raw PNG instead of cooked
  DDS: none of them has a harvest manifest, and most of their texture bytes
  changed under round 17's `texture_kit.py` work, so the DDS that had been
  shipping were bakes of superseded PNGs. `build.py <key> harvest` after a live
  run restores the cooked set.

### PROPLIB BUG: `cut_openings` applies booleans out of stack order (2026-08-15)

**Open, deliberately unfixed, worked around locally in `football_goal_post`.**

`proplib.blender_kit.add_box(bevel=...)` adds a BEVEL modifier and leaves it
pending. `cut_openings` then appends BOOLEAN modifiers and calls
`bpy.ops.object.modifier_apply` on the booleans ALONE. Blender applies a
not-first modifier to the BASE mesh and leaves everything ahead of it pending
(it prints `Info: Applied modifier was not first, result may not be as
expected`, which is not an error and does not fail a build). The exporters
evaluate the depsgraph, so the surviving bevel is applied at EXPORT time to the
boolean's OUTPUT — and Blender's EXACT solver leaves sub-nanometre artifact
edges behind (nine at 0.23 nm on the goal post's 10x5 mm flag tab), against
which bevel's clamp-overlap limits the width to ZERO.

**What ships is full bevel TOPOLOGY at zero AREA.** Measured on the round-2
`football_goal_post` DAE: 514 zero-area triangles per tab, 1028 in an
83,688-triangle model and *every* degenerate triangle in the model inside those
two parts; 0.0% oblique surface area; bevel-shaped vertex multiplicity
(`{3:94, 6:9, 7:4}`); one all-zero normal exported and referenced by 56
corners; and a knife-sharp arris where the generator declared a 0.6 mm chamfer.
The control is the same mount's weld pad — same material, `bevel=0.0025`, no
boolean — at 108 triangles, 0 degenerate, 21.3% oblique.

**NOT FIXED IN PROPLIB, and the reason is blast radius, not difficulty.** Three
other shipped mods boolean a target that is carrying a pending bevel:
`catapult_seesaw` (4 deck boards, `bevel=0.03`), `giant_toaster` (shell,
`bevel=0.85`) and `spin_cycle_washer` (body, `bevel=0.4`). Applying the whole
stack in order inside `cut_openings` would re-cut all three, each of which is
packaged, hashed, listed and — for the washer — installed. That belongs in a
round that rebuilds and re-gates them, not in a flag-mount round.
`cut_openings`' docstring now carries the warning and points here.

**AND HERE IS THE BLAST RADIUS MEASURED RATHER THAN ASSERTED (round 4).** Every
shipped DAE in `examples/giant_props`, scanned read-only for exactly-zero-area
triangles and for planar folds (`sum|a|` vs `|sum a|` per coplanar patch per
index-connected body). 19 mods, 171 DAEs:

| mod | tris | zero-area | folded patches | largest sheet |
|---|---|---|---|---|
| `gforce_centrifuge` **(PUBLISHED)** | 304,710 | **148** (144 `bank_hazard`, 4 `shell_white`) | 19 | 0.000105 mm² |
| `spin_cycle_washer` **(INSTALLED)** | 42,812 | **120** (96 `button_satin`, 24 `dial_blue`) | 1 | **1,882,515 mm² (1.88 m²)** |
| `giant_toaster` | 6,032 | 43 (40 `chrome_dark`, 3 `chrome`) | 3 | 14,400.7 mm² ×2 |
| `catapult_seesaw` | 91,132 | 22 (8 `target_red`, 8 `cast_iron`, 6 `paint_white`) | 1 | 0.014 mm² |
| `dino_egg_hatcher` | 5,441 | 17 (all `eggshell`, across 4 shard DAEs) | 0 | — |
| `boot_of_doom` | 127,412 | 16 (all `plate_data`) | 0 | — |
| `sumo_gyro_platform` | 35,022 | 2 (`deck_hazard`) | 0 | — |
| `whale_geyser` | 24,160 | 0 | 1 | 0.000053 mm² |
| **`football_goal_post`** | **85,372** | **0** | **0** | — |
| 10 others | — | 0 | 0 | — |

Read it carefully, because the two columns say different things.

- **The zero-area counts are NOT all this bug.** Round 2's signature was a
  chamfer clamped to zero width, which shows as degenerates *plus* a collapsed
  oblique fraction. The washer's chamfer SURVIVED — `enamel_white` measures
  27.8%/35.4% oblique — and its 120 degenerates sit in `button_satin` (96 of
  432 triangles) and `dial_blue` (24 of 152), both of which still measure 57%
  and 71% oblique. **That is a different and still unexplained source, and it
  is open.** Same shape of doubt for the centrifuge, whose 144 sit in a
  98.4%-oblique hazard-stripe band.
- **The fold column is the new test and it found something bigger.** The washer
  ships ONE folded patch of **1.88 m²** — 50 coplanar `enamel_white` triangles
  in one index-connected body, 9 of them reversed, on the plane y = 6.5 — and
  the toaster ships two of 0.0144 m² each in `chrome_dark` at y = 7.125,
  mirrored in x. Those are metre-scale zero-thickness membranes on an INSTALLED
  and a listed mod, and no existing check in this pack could see them. The
  centrifuge's 19, whale geyser's 1 and the catapult's 1 are all under
  0.02 mm² — detector noise at the 1e-10 m² threshold, not membrane.
- **Still filed, not fixed.** This session owns `football_goal_post`. The
  numbers are here so the owning round starts from a measurement.

**The local fix, and the three things it took to make the chamfer real.** The
goal post builds the tab with `bevel=0.0`, booleans it, and then cuts the
chamfer into the mesh data with `break_arris()`:

- **Triangulate BEFORE the bevel.** A bmesh face cannot have a hole, so the
  boolean returns a pierced face as ONE n-gon with a zero-width KEYHOLE slit.
  That n-gon tessellates correctly by itself; bevel it and the slit re-forms
  wrongly. The first version of this fix shipped a tab whose back face carried
  two triangles SPANNING THE BORE (face area 249 mm² against the front face's
  174) and three valence-4 edges — **the hole was capped**. Nothing that
  measures vertices can see that, and neither can a boolean intersection test,
  because a cap encloses no volume. **Edge valence, Euler characteristic and
  the part's own volume are what see it**: fixed reads `{2: 627}`, `V-E+F = 0`
  (one closed surface of genus 1) and 1093.383 mm³ against an analytic
  1095.844; capped read `V-E+F = 1`.
- **Scrub to epsilon, not to taste.** `remove_doubles` at 1e-5 kills the
  boolean's nanometre edges. With the scrub off the trailing triangulate turns
  them into 8 exactly-zero-area exported triangles, 22 spurious arris edges and
  chamfer tilts out to 55.6°. 1.2e-4 also passes every zero-area test and
  leaves a valence-0 WIRE edge plus 10 mm² of face asymmetry — a worse artifact
  than the one it fixes.
  **Round 4 corrected this bullet's other half.** It used to say the nanometre
  edges were what made `clamp_overlap` flatten the chamfer to 0.64% oblique.
  They are not — that measurement was taken on an ALREADY-SCRUBBED mesh, so the
  edges were gone and clamp still collapsed. What clamp was clamping against is
  the next bullet. With the declutter in place, `clamp_overlap=True` and
  `False` now give the same 394 triangles, 1093.2683 mm³ and 18.473% oblique,
  so it is left ON.
- **Declutter the faces, or the bevel turns them inside out.** See THE FOLD LAW
  below. An offset cannot be run past geometry nearer than the offset, and the
  EXACT boolean leaves stale points 0.022–0.497 mm inside an arris that is
  about to move 0.600 mm.
- **Bevel a NAMED EDGE SET, not an angle threshold.** Only face-meets-wall
  edges are arrises. The union seam is wall-to-wall and the eye's outline on
  the face is face-to-face; both carry the boolean's remaining short edges and
  neither is an arris.

**AND THE EXPORTER IS PART OF THE GEOMETRY.** Blender's Collada exporter
triangulates whatever n-gons it is handed, with its own ear-clipper, and writes
`%.7g` — near z = 13.65 m that is a **10 µm grid**. Three seam vertices
45/59/104 µm apart tessellated into a sliver with real (if tiny) area inside
Blender and quantised onto ONE LINE in the DAE: an exactly zero-area triangle
that no in-Blender assertion could see, and which two separate in-Blender
probes predicted as zero. **Hand the exporter triangles and what ships is what
was measured.** Corollary for every mod here: an in-Blender measurement is a
prediction, and the DAE is the observation.

**And bevel a chamfered bore changes where a pin BEARS.** Once both mouths are
chamfered by `b`, the cylindrical wall only survives over `|dy| <= t/2 - b`, so
that — not `t/2` — is where a wire hanging in the hole first meets metal.
Deriving the bore height from `t/2` is not dangerous (the wire ends up 0.108 mm
LOOSER) but it makes the declared seating clearance unmeasurable: the minimum
gap reads 0.31 mm against a declared 0.20. `FLAG_BORE_Z` now uses the chamfered
half-width and the shipped DAE measures 0.000202 m against a declared 0.000200.

**Verification that would have caught the original.** `M_dae.py` (round 3)
asserts, from the SHIPPED DAE: zero-area triangles == 0 MODEL-WIDE (the correct
baseline — the round-2 census found none anywhere outside the two tabs); the
tab's oblique surface area > 0 with its chamfer-tilt range; the tab's y-plane
count (4, not 2); closed 2-manifold and Euler 0; volume within 1% of analytic;
no face triangle reaching into the bore; and minimum surface-to-surface
distance between every pair of mount components. A ruler built on vertex
positions, hole radius and ray parity is **structurally blind to the SURFACE**
of the part it is defending.

**Two ruler traps found while building that.** (1) `VEHICLE_ROTATION` is
`Matrix.Rotation(pi, 4, "Z")` — a 180° YAW, `(x,y,z) -> (-x,-y,z)`. Undoing
only Y leaves X mirrored: harmless for a mirror-symmetric part, but it swaps
the LEFT and RIGHT uprights' labels and it reads `flag_r`'s cloth as 5.69 m
from its own hook instead of 5.1 mm. (2) A hand-rolled Möller triangle test is
not evidence. With unnormalised plane normals a 0.2 mm gap between two 1e-8 m²
triangles evaluates to 4e-12 and vanishes under any absolute epsilon;
normalised, it still called 50 hook/tab pairs "penetrating" when the parts are
0.189 mm apart. Report a DISTANCE, and cross-check with a solver you did not
write. `bmesh.calc_volume` is not that cross-check either — on an open mesh it
is not a volume, and it read 0.00000 mm³ on one build of a face-to-face contact
and 116.49643 on the next without the geometry moving. Classify a boolean
INTERSECT by its result's THINNEST BOUNDING-BOX AXIS: a solid overlap is thick
in every axis, a contact is flat in one.

**Shipped-DAE determinism, measured — and restated in round 4 because round 3
described it wrongly.** Two consecutive Blender runs off identical sources give
DAEs that differ on exactly 6 of 838 lines. Round 3 called four of them "NORMALS
float arrays" and concluded "positions are the build lock". Both halves were
wrong. The four are **one** NORMALS pool, **one** UV (`map-0`) pool, and **two
`<p>` index arrays** — line 666 (`steel`, 158 of 19,848 VERTEX indices differ)
and line 678 (`goal_yellow`, 12,558 of 56,352 VERTEX and 5,531 NORMAL). What
moves run to run is the **triangle emit order**, and a byte-identical position
ARRAY says nothing on its own about which triangles were built out of it.

The lock that does hold, measured by `D4_lock.py` over two builds, is the
**order-independent triangle multiset keyed on the vertex POSITION triple**,
rotated to a canonical first corner with the winding kept:

- 82,980 of 82,980 visual-mesh triangles match, zero A-only, zero B-only;
- per-material area agrees to `0.000e+00` on 13 of 14 materials and to
  1.8e-15 m² on `goal_yellow`, which is float summation order.

**Do not claim the corner attributes are bit-identical — they are not.** Over
two independent pairs of consecutive builds, 271 and then 369 triangles carry a
corner NORMAL that moves, and 1,376 then 5,843 carry a corner UV that moves.
Bounded in units of the last place `%.7g` writes: **normals ≤ 2 places, UVs ≤ 6**
(`0.03851944 -> 0.03851950`, which is 1.6 parts per million and 8e-4 of a texel
on a 512 px map). The honest statement is therefore: **positions and topology
are exact, order-independently; corner attributes are stable to the exporter's
own print precision and not below it.**

**And the ULP ruler has the same trap as the position grid.** `%.7g` keeps
seven SIGNIFICANT digits, so the print place of a *vector* is set by its
LARGEST component. Scoring each component against its own magnitude reads a
2e-07 move on a normal component of 6.6e-09 as thirty thousand places out and
fails a build that is fine.

**And keep the scopes of a zero-area row apart.** Round 3 reported
"0 of 85,420; min area 2.4e-08 m²" as one line. The count is model-wide; the
area was the VISUAL mesh alone. Model-wide the floor is in the CLOTH:
`flag_r` 4.559e-09 m², `flag_l` 1.138e-08 m², visual mesh 8.514e-08 m² (round
4, after the tab's chamfer slivers went). Those cloth slivers are in the
doubled hem's back sheet, centre column, at the two stations where it lands on
the ribbon's leading row; their shortest side is 5.0 µm and 13.0 µm and it lies
**entirely along x**, where a coordinate of ~2.87 m prints at 7 significant
digits and therefore quantises at **1 µm, not 10 µm** — so they are 5 and 13
grid steps from collapsing, not 1.3, and re-quantising the shipped values
through `%.7g` yields 0 zero-area triangles with an unchanged minimum. `%.7g`
is a grid *per axis and per magnitude*; z at 13.65 m is the 10 µm one. Watched,
not changed: they are in a soft body whose vertices move every frame.

### THE FOLD LAW: a coplanar zero-thickness sheet is invisible to every integral invariant (2026-08-15, round 4)

**Applies to every mod in this pack, not just the one that found it.**

A folded planar patch — one face ear-clipped onto itself, a triangle turned
inside out by an offset, a capped hole — passes *all* of this:

| check | why it passes |
|---|---|
| signed volume | a sheet encloses nothing |
| Euler characteristic / genus | it adds no handle |
| edge valence `{2: N}` | every edge still borders exactly two faces |
| zero-area census | its triangles have real area |
| oblique-area / tilt band | it lies in a plane that already exists |
| boolean INTERSECT volume | zero, like a contact |
| ray parity through a solid | still even |

`football_goal_post` shipped a capped bore under the first four in round 2 and
**46.4 mm² of folded membrane across two tabs under thirty-eight assertions**
in round 3. Both were the same defect class. `len(edge.link_faces) == 2` is
structurally incapable of seeing either.

**The one test that sees it.** Inside ONE planar patch of ONE index-connected
body,

```
sum |area|  -  |sum area|  =  2 x (area of the doubled sheet)
```

because a reversed sheet subtracts from the vector sum while adding to the
scalar one. On the round-3 tab: `sum|a|` 193.804 mm² against `|sum a|`
169.904 mm², and 193.804 − 2×11.950 = 169.904 exactly. Equivalent one-liners
that catch the same thing: *no two faces coincident with opposing normals*, or
*ray parity ≤ 2 crossings*. Any of the three is cheap and none of the seven
above is a substitute.

**Group per patch and per BODY, and build the body from shared INDICES.** Two
different solids may legitimately share a plane with opposing normals — the
tab's back face lies on the pad's front face, which is the weld, and the
footing's top face lies on the subgrade's bottom face, which is the Z-FIGHT
LAW. Welding bodies by POSITION fuses those and reports a designed 4.84 m²
contact as a fold. Blender's join keeps separate solids on separate index runs;
a real fold is one face ear-clipped onto itself and shares indices.

**The cause, on the goal post, was a distance and not a tessellation.**
Measured pre- and post-bevel, the two biggest reversed triangles were the SAME
three-cornered face:

```
before   (-5.000, 2.191)  (-5.000, 20.946)  (-4.955, 2.386)
after    (-4.400, 2.157)  (-4.400, 20.946)  (-4.955, 2.386)
```

The two corners on the arris moved 0.6 mm inboard, straight past a third that
sits 0.045 mm inside it and does not move. `ngon_method` never saw it; blaming
the ear-clipper was wrong. **An offset may not be run past geometry nearer than
the offset.** The offenders were all stale points the EXACT boolean leaves
behind and that carry no shape: 28-gon vertices of the eye falling just inside
the shank's side plane (r = 5.5 mm at 25.71° lands at x = 4.955 against a
half-width of 5.000), and the shank's own side plane crossing the eye disc.

**The repair is to dissolve them before bevelling, and to ITERATE**, because
dissolving re-triangulates and a vertex that was safe against its old neighbour
becomes the near one: 11 cleared on pass 0, 1 on pass 1, 0 on pass 2. It is a
mesh repair, not a design change — volume 1093.2683 mm³ before and after to
four decimals — and it takes the plate's two faces from 192.353 / 193.782 mm²
(170 mm² of face plus a doubled sheet) to 169.895 / 169.895, equal to each
other and to the vector sum.

**And a 0.6 mm chamfer is a READING-DISTANCE feature, not a macro one.** The
membrane rendered as two black tapering wedges down both long arrises, hiding
93% of the chamfer at z = 2.4 mm and 55% at 10.0 mm. Before/after renders of
the SHIPPED DAE: peak pixel difference 227/255 in macro, **52/255 at 0.23 m
reading distance**, and only 41/255 over about two pixels at the owner's 1.0 m.
So it was invisible where round 3 looked and unmistakable where it did not.

### A CONSTANT WRITTEN AND NEVER READ IS A CLAIM THAT NO LONGER HAS TO BE TRUE

Three times in one file: `FLAG_EAR_REACH`, `FLAG_LINK_DROP`, `FLAG_HEADER_H` —
each a number describing a part of the mount that had stopped existing, and
`FLAG_HEADER_H` held exactly `FLAG_HEM_REACH + FLAG_HEM_RUN` while four
present-tense comments described a "header" nothing built. That is how prose
drifts three names ahead of geometry. `create_football_goal_post.py` now fails
its own build on the fourth, via `assert_no_dead_constants()`: parse the file
with `ast`, collect module-level ALL-CAPS assignments, subtract every `Name`
load, assert the difference is empty. `ast` and not grep, so a name surviving
only in a comment still counts as dead. It found two more on the first run
(`PAD_WRAP`, `PAD_HEIGHT`), both deleted.

## Verification and Git hygiene

Run focused tests first, then the repository checks before claiming completion:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src/beamng_mcp
uv run pytest -q
uv build
git diff --check
```

For Blender, Lua, BeamNGpy, packaging, map-placement, or physics changes, add the relevant opt-in
Blender/live gates from `docs/DEVELOPMENT.md`; document the exact simulator/Blender versions and
any skipped gate. Do not call a mod functional based only on static tests.

Branch and PR references are not durable project state: check `git status`, the current branch,
remote tracking, and PR status before editing or publishing. Preserve unrelated user changes. Do
not commit, push, merge, publish a public mod, or mutate GitHub state unless the user explicitly
requests that action.
