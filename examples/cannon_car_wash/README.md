# Cannon Car Wash

This example is the repeatable Blender MCP to BeamNG MCP workflow for a drive-through
wash-and-launch trap and rigid vehicle-selector prop.

The mod/ directory is intentionally the exact public-upload staging tree. It contains exactly 40
runtime files below the BeamNG-approved `art`, `levels`, `lua`, and `vehicles` top-level folders.
Authoring evidence, Blender sources, submission metadata, gallery images, and live telemetry stay
beside it and never enter the ZIP.

## Runtime behavior

- The Gridmap V2 scenario spawns a grounded Gavril D-Series at the entrance. Its scenario-owned
  extension drives three persistent prefab triggers, five animated brushes, six inward-facing
  water jets, a ten-node layered dryer, full-containment countdown, and launch for any exact live
  vehicle subject, including the stock Wentward city bus.
- The vehicle selector exposes `ericrolph_cannon_car_wash` as a Props-category model with the same
  behavior in free roam. A vehicle-local bootstrap registers each placed wash with an on-demand
  GELua manager; it accepts arbitrary real vehicles rather than requiring the scenario truck.
- The first vehicle entering starts the animated rollers and all sixteen particle nodes. Occupancy
  is reference-counted, so the rollers and effects stay active until the final vehicle exits. The
  exit dryer combines
  six `BNGP_waterfallsteam` primary jets with two `BNGP_34` steam and two `BNGP_2` dust accents.
  Crossing the wash midpoint repairs transient physics, flex-mesh, tire, and mechanical damage
  once per wash pass. It briefly preserves/freezes the controller state, performs BeamNG's full
  physics reset, then uses the renewed live OOBB to center the vehicle without changing its
  longitudinal progress. It aligns forward and upright to the wash corridor, preserves the
  incoming direction-of-travel sign, verifies clean integrity and pose gates, and acknowledges
  release back to the prior freeze state before launch can proceed. The current isolated D-Series
  proof records 0.036987 m centerline error, 0.9997017 corridor-direction dot, and 0.9997559
  upright dot; the selector-runtime path also passes with the stock city bus.
  The full-bay launch trigger uses `Contains` plus `Bounding box`, so the manager does not freeze a
  subject until it is fully inside and its midpoint repair has completed. Its dimensions are
  validated against the stock 12.63 m Wentward DT40L city bus.
  It then displays `3... 2... 1... GO!` one second apart and replaces the main-cluster velocity
  with 100 m/s (360 km/h) along the
  vehicle's measured current forward axis.
- The selector cage has 79 fixed nodes, 329 beams, 144 collision triangles, one multi-material
  flexbody, and a mass of 15,125 kg. Its exact Blender-derived ground datum is
  `ericrolph_cannon_car_wash_ground_reference` at `[0, 0, 0]`, backed by
  `ericrolph_cannon_car_wash_ground_back` at `[0, 3, 0]`, so surface-Z placement is flush.

Every authored runtime path, JBeam part/group/mesh, material key/name/mapTo, DAE geometry, scene
object, trigger, Lua extension, and UI category uses the ericrolph_cannon_car_wash namespace.
Required stock references remain unchanged.

The scenario gameplay extension lives beside the scenario JSON and is declared in that scenario's
`extensions` table. BeamNG loads it only for the Cannon Car Wash scenario and unloads it on scenario
stop. The selector uses a distinct vehicle-local bootstrap and on-demand GE manager; transient
visuals, triggers, and emitters are cleaned up per prop, and the manager unloads after the final
instance disappears. Neither path uses a global `modScript.lua` bootstrap.

## Visual asset and PBR budget

- The scenario Collada is 10,714 triangles across 33 geometry/primitive groups and 18 materials.
- The selector Collada is consolidated to 10,666 triangles across 18 primitive/material groups.
  Its separate vehicle-local runtime Collada retains five independent animated brush channels.
- Each vertical brush uses 16 alpha-tested radial cards; the overhead brush uses 14. Alpha test,
  colour-dilated card edges, and a shared 512 atlas provide density without blended-card sorting.
- Four 1K tileable source families provide exterior CMU, interior brick, wet concrete, and painted
  corrugated blue. The sign is 1024x256 and emissive; brush maps are 512. The public mod contains
  22 verified cooked DDS files and no authoring PNGs.
- Seven synchronized scene lights provide actual illumination: five cool tunnel PointLights and
  two blue entrance/sign SpotLights. The scenario owns persistent prefab lights; the selector
  manager creates transform-following non-saveable equivalents and removes them with the prop.
- Blender's saved preview uses numeric materials. BeamNG's namespaced `main.materials.json` files,
  cooked DDS resolution, and in-engine dusk/day inspection are the authoritative PBR result.

See [TECHNICAL_ART.md](TECHNICAL_ART.md) for the geometry/UV process, exact light specification,
PBR JSON examples, texture cooking, performance budgets, and inspection workflow. Source-image
provenance and reproducible derivation are recorded in [textures/README.md](textures/README.md).

## Source and distribution layout

~~~text
blender/       Blender source, preview, and deterministic generator
authoring/     exact geometry and selector-cage handoff evidence
validation/    Phase 2/3/4 contracts used by static and live gates
telemetry/     latest successful isolated live-test evidence
repository/    upload-form metadata, provenance, icon, and gallery images
textures/      source images, deterministic PBR builder, cook handoff, and provenance
mod/           exact 40-file BeamNG public ZIP root (art/, levels/, lua/, vehicles/)
~~~

The stable release filename is cannon_car_wash_ericrolph.zip. Keep that filename across updates
and increment repository/submission.json instead.

## Rebuild

~~~powershell
$blender454 = '<path to Blender 4.5.4 LTS executable>'
& $blender454 --factory-startup --background --python .\examples\cannon_car_wash\blender\create_cannon_car_wash.py
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\textures\build_pbr_textures.py
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\textures\cook_release_textures.py stage
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\build_selector_prop.py
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\sync_scenario_outputs.py
~~~

The generator saves a portable Z-up Blender file, exports the namespaced scenario and selector
Collada files, and writes source-side coordinate handoffs. The selector builder refuses a stale
DAE hash and creates the JBeam/material/configuration files only from that handoff. The final sync
copies all three Blender-authored trigger transforms and particle-layer transforms into both the
scenario manifest and prefab, and refreshes their DAE lock. Never patch JBeam, trigger, or emitter
coordinates independently. `build_pbr_textures.py` creates 22 deterministic logical PNG maps and
their source-side manifest. `cook_release_textures.py stage` places only that known set for one
isolated BeamNG cook; after the visual load, run `collect --profile-current <sentinel-current>` to
validate dimensions and DDS channel classes, copy the 22 release DDS files, and remove staged PNGs.

## Static and distribution gates

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q `
  .\tests\test_cannon_car_wash_assets.py `
  .\tests\test_cannon_car_wash_phase3_lua_contract.py `
  .\tests\test_cannon_car_wash_selector_runtime_contract.py `
  .\tests\test_cannon_car_wash_distribution.py
~~~

The distribution gate builds a deterministic, explicitly allowlisted 40-file ZIP and rejects
loose root files, wrapper folders, README/mod_info content, source evidence, unsafe names,
unnamespaced runtime declarations, invalid JSON, broken references, and nondeterministic members.
Members are stored without DEFLATE so the complete archive remains byte-identical across Python and
zlib versions; release-bound generators also force LF newlines so Windows checkout filters cannot
change payload bytes. BeamNG still receives a standard ZIP, while the release SHA-256 stays portable.

## Isolated live gates

~~~powershell
$env:BEAMNG_MCP_TEST_BEAMNG_HOME = '<BeamNG.drive installation>'
$env:BEAMNG_MCP_TEST_BEAMNG_BINARY = '<BeamNG.drive executable>'
$env:BEAMNG_MCP_TEST_BEAMNG_USER = '<sentinel-isolated BeamNG user profile>\current'
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_phase2_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_phase4_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_selector_runtime_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_distribution_live.py
~~~

Run these serially against only the sentinel-marked profile. They install and exercise the exact
runtime staging tree, not a development tree with injected metadata. Phase 2 proves all materials,
textures, meshes, and seven lights resolve. Phase 4 subsumes Phase 3 and proves the scenario-owned
path with its default D-Series, including repair alignment and gallery capture. The
selector-runtime gate spawns the prop flush to a measured map surface, validates two-vehicle
occupancy, and drives a stock city bus through its on-demand triggers. The final exact-ZIP gate
proves the immutable public artifact. The narrower `phase3_live` and `selector_live` tests remain
available for diagnosis but are not repeated when a broader gate already covers their behavior.

Live support reads only appended `beamng.log` bytes through `BeamNGLogCursor`, resets the cursor at
owned-process boundaries, and scans structured namespaced events plus W/E records. GELua/BeamNGpy
queries provide exact transforms, OOBBs, material/light inventories, trigger state, damage, and
velocity. RenderView images receive semantic visual review; a local vision model may assist, but
numeric centerline/quaternion/ground-contact/cleanup assertions remain the deterministic authority.

## Public upload

Build the artifact from the production immutable allowlist, then test that exact ZIP alone in the
sentinel-isolated profile's USER_FOLDER/mods directory:

~~~powershell
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\build_distribution.py --overwrite
.\.venv\Scripts\python.exe -m pytest -q .\tests\test_cannon_car_wash_distribution.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_distribution_live.py
~~~

The v1.8 artifact contains 40 members, is 23,754,854 bytes, and has SHA-256
`bdd54a270311fbc5b3d6ffb46022c0fac0474225b355e106f85260e50fd9d583`; the same lock is stored in
`repository/submission.json` and must be proven by the exact prebuilt-ZIP live gate. Do not place a
pre-submission ZIP under `mods/repo`; BeamNG owns that location for Repository-managed downloads.

The operator must still use the official Repository form: upload the ZIP, icon, and at least two
gallery images, paste the overview in repository/SUBMISSION.md, verify authorship/provenance, and
submit it for moderator review. No automation in this repository publishes the mod.
