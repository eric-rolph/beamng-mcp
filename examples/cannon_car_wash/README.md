# Cannon Car Wash

This example is the repeatable Blender MCP to BeamNG MCP workflow for a drive-through
wash-and-launch trap and rigid vehicle-selector prop.

The mod/ directory is intentionally the exact public-upload staging tree. It contains only 14
runtime files below BeamNG-approved top-level folders. Authoring evidence, Blender sources,
submission metadata, gallery images, and live telemetry stay beside it and never enter the ZIP.

## Runtime behavior

- The Gridmap V2 scenario spawns a grounded Gavril D-Series at the entrance.
- The full-bay ericrolph_cannon_car_wash_wash_activation_trigger starts five ambient brush
  animations and twelve inward-facing BNGP_sprinkler emitters while a vehicle overlaps the bay.
- The exit ericrolph_cannon_car_wash_launch_trigger uses Contains plus Bounding box. The exact
  named D-Series must be fully inside and the wash must already be active.
- Lua holds the truck, displays 3-2-1-GO on one-second job-system intervals, then replaces its
  cluster velocity with 100 m/s along its measured current forward axis.
- The vehicle selector exposes ericrolph_cannon_car_wash as a Props-category model. Its measured
  cage has 77 fixed nodes, 322 beams, 144 collision triangles, one multi-material flexbody, and a
  mass of 14,875 kg.

Every authored runtime path, JBeam part/group/mesh, material key/name/mapTo, DAE geometry, scene
object, trigger, Lua extension, and UI category uses the ericrolph_cannon_car_wash namespace.
Required stock references remain unchanged.

The gameplay extension lives beside the scenario JSON and is declared in that scenario's
`extensions` table. BeamNG loads it only for Cannon Car Wash and unloads it on scenario stop; there
is no global `modScript.lua` bootstrap.

## Source and distribution layout

~~~text
blender/       Blender source, preview, and deterministic generator
authoring/     exact geometry and selector-cage handoff evidence
validation/    Phase 2/3/4 contracts used by static and live gates
telemetry/     latest successful isolated live-test evidence
repository/    upload-form metadata, provenance, icon, and gallery images
mod/           exact 14-file BeamNG public ZIP root
~~~

The stable release filename is cannon_car_wash_ericrolph.zip. Keep that filename across updates
and increment repository/submission.json instead.

## Rebuild

~~~powershell
$blender454 = '<path to Blender 4.5.4 LTS executable>'
& $blender454 --factory-startup --background --python .\examples\cannon_car_wash\blender\create_cannon_car_wash.py
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\build_selector_prop.py
~~~

The generator saves a portable Z-up Blender file, exports the namespaced scenario and selector
Collada files, and writes source-side coordinate handoffs. The selector builder refuses a stale
DAE hash and creates the JBeam/material/configuration files only from that handoff. Never patch
JBeam coordinates independently.

## Static and distribution gates

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q .\tests\test_cannon_car_wash_assets.py .\tests\test_cannon_car_wash_phase3_lua_contract.py .\tests\test_cannon_car_wash_distribution.py
~~~

The distribution gate builds a deterministic, explicitly allowlisted 14-file ZIP and rejects
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
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_distribution_live.py
~~~

Run these serially against only the sentinel-marked profile. They install and exercise the exact
runtime staging tree, not a development tree with injected metadata. Phase 4 prints the velocity,
damage, countdown, wash-state, and Lua-log evidence used to refresh telemetry/.

## Public upload

Build the artifact from the production immutable allowlist, then test that exact ZIP alone in the
sentinel-isolated profile's USER_FOLDER/mods directory:

~~~powershell
.\.venv\Scripts\python.exe .\examples\cannon_car_wash\build_distribution.py --overwrite
.\.venv\Scripts\python.exe -m pytest -q .\tests\test_cannon_car_wash_distribution.py
.\.venv\Scripts\python.exe -m pytest -q -s .\tests\test_cannon_car_wash_distribution_live.py
~~~

Use the member count, size, and SHA-256 printed by the builder and locked in
repository/submission.json. Do not place a pre-submission ZIP under mods/repo; BeamNG owns that
location for Repository-managed downloads.

The operator must still use the official Repository form: upload the ZIP, icon, and at least two
gallery images, paste the overview in repository/SUBMISSION.md, verify authorship/provenance, and
submit it for moderator review. No automation in this repository publishes the mod.
