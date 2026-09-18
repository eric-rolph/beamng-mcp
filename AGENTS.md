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

## Where the mods went

The content this pipeline produces — six GIS-derived maps, the giant props pack and the Cannon
Car Wash — lives in [`beamng-mods`](https://github.com/eric-rolph/beamng-mods), and so do the
laws that belong to it: the Cannon Car Wash baseline, the prop authoring field guide, the per-mod
round ledgers, the release re-cut law, and local play deployment. Those are laws about building a
mod. What stays here is the machinery and the laws that govern it.

Read that repository's `AGENTS.md` before authoring or re-cutting any mod. Nothing in this file
supersedes it on content, and nothing in it supersedes this file on the server.

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

Repository-facing assets must be globally namespaced, with a stable author-plus-mod prefix
(`<author>_<mod>_`) on file and object basenames, folders where applicable, JBeam part keys and
slots, flexbody and DAE mesh IDs, material JSON root keys, material `name`, material `mapTo`, Lua
extension identifiers, prefab and scene-object names, and trigger names. Do not overwrite stock or
another mod's data. Keep one stable, unique ZIP filename (allowed filename characters only, no
version suffix) across updates, and increment metadata version instead.

A public Repository ZIP is a separate distribution artifact, not a blind ZIP of the development
tree. Opening it must show only the relevant approved BeamNG top-level folders, currently
`vehicles`, `levels`, `art`, `assets`, `lua`, `scripts`, `ui`, `gameplay`, `settings`,
`trackEditor`, and/or `vehicleGroups`. There must be no extra wrapper folder, loose root payload,
unrelated folder, source or evidence file, or `README`. Repository metadata, icons and gallery
images, coordinate handoffs and phase contracts all stay source-side and none of them enter the
ZIP. Test that ZIP alone from `USER_FOLDER/mods`, not `mods/repo`, because the latter is managed
by the Repository service. Official current guidance wins if local tooling and upload policy
differ.

The Repository form assets are separate from the ZIP. Keep the form icon exactly 96x96, upload at
least two real in-game images through the form's image uploader, and keep both the form overview
and all provenance and evidence files source-side.

Build public artifacts only with a production allowlist builder, never a blind ZIP, and gate each
release on both its archive contract and its live gates. A runtime-byte or builder-policy change
requires an intentional metadata update, rebuild, new hash lock, and a complete distribution
rerun. Each mod's own release lock, hash and outstanding gates are recorded in `beamng-mods`, not
here.

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
```

Each mod in `beamng-mods` invokes that binary through its own build script, and its `AGENTS.md`
carries the invocations and the warnings that go with them. The one that matters here: a stage
that writes a handoff ships PARAMS through the handoff, while Lua code ships fresh at build time,
so a constant changed in a spec does not reach the shipped runtime until the Blender stage re-runs.


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
`mods/**/*.zip` for members under `vehicles/<mod_id>/` or `lua/ge/extensions/<mod_id>/` instead,
and fail closed. The worked implementation is `_namespace_conflicts` in the slope live gate in
`beamng-mods`.

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
