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
  `BNG_exhaust_steam`, and `BNG_Ambient_Dust` do not exist in the pinned BeamNG 0.38.6 data. Their
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
  freeze while preserving its previous state, then snapshot the incoming motion and the wash
  corridor basis. `RESET_PHYSICS` moves and can reorient a rolling vehicle even while frozen. After
  consuming its `onVehicleResetted`, compute the renewed live OOBB, translate it back to the wash
  centerline without changing longitudinal progress, align forward and up to the corridor, and
  choose the corridor sign matching the incoming direction of travel. Apply that deterministic
  source-to-target basis delta with `vehicle:setPositionRotation(...)`, consume its second callback
  as `pose_restore_pending`, and allow at most two bounded corrective retries. After two positive
  simulation frames, verify damage <= 0.01, no part damage, no broken beams, no deflated tires,
  centerline error <= 0.15 m, corridor/upright dot >= 0.999, and preserved travel sign; restore the
  prior freeze state through an acknowledged release; only then emit `repair_complete` or permit
  launch. The isolated D-Series proof currently records 0.036987 m centerline error,
  0.9997017 corridor-direction dot, and 0.9997559 upright dot. Every failure/teardown path must make
  a best-effort release so a subject cannot remain frozen. Never substitute `beamstate.reset()`
  (bookkeeping only), flex-mesh reset alone (visual only), recovery/safe teleport (chooses a
  different pose), a hard-coded model yaw correction, or let either intentional callback enter the
  generic reset-abort path.
- The `Contains` launcher occupies the complete wash bay at local center `[0, 0, 2.1]` with
  dimensions `[5.8, 17.5, 4.6]`. Its validated large-vehicle envelope is the stock Wentward
  DT40L city bus (`citybus`, configuration `city`), measured from BeamNG 0.38.6 metadata as
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
- The v1.8 visual export is deliberately bounded: the scenario DAE is 10,714 triangles across 33
  primitive groups and 18 materials; the consolidated selector DAE is 10,666 triangles across 18
  groups. Its separate vehicle-local runtime DAE retains five independently animated brush
  channels. Vertical brushes use 16 alpha-tested radial cards and the overhead brush uses 14;
  collision remains on the simple authored shell. The public runtime contains 22 BeamNG-cooked DDS
  textures and no authoring PNGs. Blender's `.blend` file uses numeric preview materials; the two
  namespaced `main.materials.json` files and in-game BeamNG inspection are the PBR authority.
- Seven Blender-authored light anchors are synchronized into both lifecycles: five shadowless
  PointLights at local X=0, Z=4.34, and Y=-6.8/-3.4/0/3.4/6.8, brightness 1.25 and radius 4.4, plus two
  shadowless entrance SpotLights at local `[-1.9, -8.72, 4.08]` and `[1.9, -8.72, 4.08]`, direction
  `[0, -0.97, -0.24]`, brightness 1.8, range 7.5, and 28/48 degree inner/outer cones. Persisted
  scenario lights and transient selector lights must produce the same seven-object inventory.

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

For v1.8, the normal release matrix is four serial cold starts on BeamNG.drive 0.38.6: Phase 2 for
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

The v1.8 release lock is 40 members, 23,754,854 bytes, SHA-256
`bdd54a270311fbc5b3d6ffb46022c0fac0474225b355e106f85260e50fd9d583`. It is recorded in
`repository/submission.json` and the exact distribution live test. A runtime-byte or builder-policy
change requires an intentional metadata update, rebuild, new hash lock, and complete distribution
rerun.

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

All live tests must use this sentinel-isolated BeamNG 0.38.6 profile and run serially:

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
recovery/quarantine files while diagnosing a failed atomic install.

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
