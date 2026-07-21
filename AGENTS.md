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

- The selector model is a physical-only `Type: Prop` named Cannon Car Wash. Its current validated
  topology is 77/77 fixed nodes, 322 beams, 144 collision triangles, one flexbody, and 14,875 kg.
  It has open portals and zero measured shell movement during settle and vehicle contact.
- The Gridmap V2 scenario supplies the behavior that the selector prop intentionally does not:
  `ericrolph_cannon_car_wash_wash_activation_trigger` is a full-bay `Overlaps` trigger that
  starts/stops ambient brush animation and twelve `BNGP_sprinkler` emitters;
  `ericrolph_cannon_car_wash_launch_trigger` is a `Contains` / `Bounding box` trigger for the
  exact named D-Series.
- Launch requires the wash system to be active and the truck to be fully contained. It holds the
  truck, displays `3...`, `2...`, `1...`, `GO!` on one-second job-system intervals, then replaces
  cluster velocity with 100 m/s (360 km/h) along the measured current forward axis. Activation is
  transactional, live trigger configuration is checked, and simultaneous nested entry is deferred.
- Do not add scenario Lua, triggers, or particle emitters to the vehicle-selector prop unless the
  product behavior is intentionally redesigned and separately tested.

Relevant proof gates are:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  .\tests\test_cannon_car_wash_assets.py `
  .\tests\test_cannon_car_wash_phase3_lua_contract.py

.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_phase2_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_phase3_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_phase4_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_selector_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_distribution_live.py
```

The v1.3.0 migration passed all four dedicated authoring/behavior gates plus the exact prebuilt-ZIP
smoke on BeamNG.drive 0.38.6. That final smoke verifies the locked release hash before and after
copy, installs only to an isolated `USER_FOLDER/mods`, discovers both scenario and Props entry,
loads the scenario, settles the truck on Gridmap V2, scans namespaced warnings/errors, and restores the
support mod byte-for-byte. The repository-wide result at this evidence refresh was 536 passed with
12 environment-gated skips, plus clean Ruff, mypy, and PEP 517 sdist/wheel builds. These results are
evidence, not permission to skip reruns after a change. Preserve
`telemetry/cannon_car_wash_phase4_results.json` and
`telemetry/cannon_car_wash_selector_results.json` as source-side evidence; refresh them only from a
successful isolated live gate.

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
unrelated folder, source/evidence file, or `README`. For Cannon Car Wash, `mod/` is the exact
14-file public-upload tree and its roots must be exactly `levels` and `vehicles`. Repository
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

The v1.3.0 release lock (member count, byte size, and SHA-256) is recorded in
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

At the time this guide was added, work was on `codex/cannon-car-wash-prop` with draft PR #8 at
<https://github.com/eric-rolph/beamng-mcp/pull/8>; earlier Cannon Car Wash work had already been
merged. Treat that as orientation, not durable state: check `git status`, the current branch,
remote tracking, and PR status before editing or publishing. Preserve unrelated user changes. Do
not commit, push, merge, publish a public mod, or mutate GitHub state unless the user explicitly
requests that action.
