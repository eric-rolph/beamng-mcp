# Cannon Car Wash

This example is the repeatable Blender MCP to BeamNG MCP workflow for a drive-through
wash-and-launch trap and rigid vehicle-selector prop.

The mod/ directory is intentionally the exact public-upload staging tree. It contains only 16
runtime files below the BeamNG-approved `art`, `levels`, `lua`, and `vehicles` top-level folders.
Authoring evidence, Blender sources, submission metadata, gallery images, and live telemetry stay
beside it and never enter the ZIP.

## Runtime behavior

- The Gridmap V2 scenario spawns a grounded Gavril D-Series at the entrance. Its scenario-owned
  extension drives three persistent prefab triggers, five animated brushes, six inward-facing
  water jets, a ten-node layered dryer, full-containment countdown, and named D-Series launch.
- The vehicle selector exposes `ericrolph_cannon_car_wash` as a Props-category model with the same
  behavior in free roam. A vehicle-local bootstrap registers each placed wash with an on-demand
  GELua manager; it accepts arbitrary real vehicles rather than requiring the scenario truck.
- Wash entry starts the animated rollers and all sixteen particle nodes. The exit dryer combines
  six `BNGP_waterfallsteam` primary jets with two `BNGP_34` steam and two `BNGP_2` dust accents.
  Crossing the entry-water arch repairs transient physics, flex-mesh, tire, and mechanical damage
  once per wash pass. It briefly preserves/freezes the controller state, restores the exact
  pre-reset pose after BeamNG's physics reset, verifies clean integrity, and acknowledges release
  back to the prior freeze state before launch can proceed.
  The separate launch trigger uses
  `Contains` plus `Bounding box`, so the manager does not freeze a subject until it is fully inside.
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

## Source and distribution layout

~~~text
blender/       Blender source, preview, and deterministic generator
authoring/     exact geometry and selector-cage handoff evidence
validation/    Phase 2/3/4 contracts used by static and live gates
telemetry/     latest successful isolated live-test evidence
repository/    upload-form metadata, provenance, icon, and gallery images
mod/           exact 16-file BeamNG public ZIP root (art/, levels/, lua/, vehicles/)
~~~

The stable release filename is cannon_car_wash_ericrolph.zip. Keep that filename across updates
and increment repository/submission.json instead.

## Rebuild

~~~powershell
$blender454 = '<path to Blender 4.5.4 LTS executable>'
& $blender454 --factory-startup --background --python .\examples\cannon_car_wash\blender\create_cannon_car_wash.py
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\build_selector_prop.py
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\sync_scenario_outputs.py
~~~

The generator saves a portable Z-up Blender file, exports the namespaced scenario and selector
Collada files, and writes source-side coordinate handoffs. The selector builder refuses a stale
DAE hash and creates the JBeam/material/configuration files only from that handoff. The final sync
copies the Blender-authored particle-layer transforms into both the scenario manifest and prefab and
refreshes their DAE lock. Never patch JBeam or emitter coordinates independently.

## Static and distribution gates

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q `
  .\tests\test_cannon_car_wash_assets.py `
  .\tests\test_cannon_car_wash_phase3_lua_contract.py `
  .\tests\test_cannon_car_wash_selector_runtime_contract.py `
  .\tests\test_cannon_car_wash_distribution.py
~~~

The distribution gate builds a deterministic, explicitly allowlisted 16-file ZIP and rejects
loose root files, wrapper folders, README/mod_info content, source evidence, unsafe names,
unnamespaced runtime declarations, invalid JSON, broken references, and nondeterministic members.

## Isolated live gates

~~~powershell
$env:BEAMNG_MCP_TEST_BEAMNG_HOME = '<BeamNG.drive installation>'
$env:BEAMNG_MCP_TEST_BEAMNG_BINARY = '<BeamNG.drive executable>'
$env:BEAMNG_MCP_TEST_BEAMNG_USER = '<sentinel-isolated BeamNG user profile>\current'
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_phase2_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_phase3_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_phase4_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_selector_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_selector_runtime_live.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_distribution_live.py
~~~

Run these serially against only the sentinel-marked profile. They install and exercise the exact
runtime staging tree, not a development tree with injected metadata. Phase 4 proves the
scenario-owned D-Series path; the selector-runtime gate spawns the prop flush to a measured map
surface and drives an arbitrary vehicle through its on-demand triggers. Together they print the
velocity, damage, countdown, wash-state, cleanup, and Lua-log evidence used to refresh telemetry/.

## Public upload

Build the artifact from the production immutable allowlist, then test that exact ZIP alone in the
sentinel-isolated profile's USER_FOLDER/mods directory:

~~~powershell
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\build_distribution.py --overwrite
.\.venv\Scripts\python.exe -m pytest -q .\tests\test_cannon_car_wash_distribution.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_distribution_live.py
~~~

The verified v1.6 artifact contains 16 members, is 1,882,321 bytes, and has SHA-256
`20ff19d331f22f97a71f806d34ee5cdf4a5aade24d61e376a88b814316db0455`; the same lock is stored in
repository/submission.json. Do not place a pre-submission ZIP under mods/repo; BeamNG owns that
location for Repository-managed downloads.

The operator must still use the official Repository form: upload the ZIP, icon, and at least two
gallery images, paste the overview in repository/SUBMISSION.md, verify authorship/provenance, and
submit it for moderator review. No automation in this repository publishes the mod.
