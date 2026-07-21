# Cannon Car Wash

This example is the complete Blender MCP → BeamNG MCP workflow for a drive-through car-wash
trap. The distributable mod lives in [`mod`](mod); Blender authoring files stay outside that folder
so they cannot leak into the packed archive.

## Phase gates

1. **Blender asset:** `blender/create_cannon_car_wash.py` repeatably rebuilds the `.blend`, Z-up
   Collada, material file, and geometry manifest. The checked-in PNG is the validated authoring
   preview. The manifest records the exact trigger bounds and drive axis used by every later phase.
2. **Engine setup:** `phase2_manifest.json` fixes the Gridmap V2 asset origin, grounded D-Series
   spawn, exact `BeamNGTrigger` center/scale, and world `+Y` drive direction.
3. **Lua behavior:** `phase3_manifest.json` describes the exact trigger/vehicle identity checks,
   real-time job-system countdown, hold/release sequence, and 100 m/s forward velocity injection.
4. **Impact telemetry:** `phase4_manifest.json` fixes the concrete wall bounds and State,
   Electrics, Damage, and log assertions. The latest live result is in
   [`telemetry/cannon_car_wash_phase4_results.json`](telemetry/cannon_car_wash_phase4_results.json).

Each gate is validated before the next one runs. The live approach uses direct input arbitration
only inside a sentinel-isolated BeamNG profile. On BeamNG 0.38's default D-Series automatic,
selector index `2` means Drive; it is not physical second gear.

## Rebuild the Blender asset

```powershell
blender --factory-startup --background `
  --python .\examples\cannon_car_wash\blender\create_cannon_car_wash.py
```

Factory startup keeps the scene deterministic. During the save, the generator also uses a relative
preview path and temporarily blanks user asset-library paths, preventing authoring-machine details
from leaking into the portable `.blend`. It writes only the reviewed example paths. Re-run the
asset and Lua contract tests after any geometry change:

```powershell
python -m pytest -q `
  .\tests\test_cannon_car_wash_assets.py `
  .\tests\test_cannon_car_wash_phase3_lua_contract.py
```

## Run the isolated live gates

Set the three live-test variables to a BeamNG 0.38 installation and sentinel-marked disposable
profile, then run each phase independently:

```powershell
$env:BEAMNG_MCP_TEST_BEAMNG_HOME = '<BeamNG installation>'
$env:BEAMNG_MCP_TEST_BEAMNG_USER = '<sentinel-isolated user profile>\current'
$env:BEAMNG_MCP_TEST_BEAMNG_BINARY = 'Bin64\BeamNG.drive.x64.exe'

python -m pytest -q -s .\tests\test_cannon_car_wash_phase2_live.py
python -m pytest -q -s .\tests\test_cannon_car_wash_phase3_live.py
python -m pytest -q -s .\tests\test_cannon_car_wash_phase4_live.py
```

The Phase 4 test prints one `CANNON_PHASE4_TELEMETRY` JSON record. It fails on an ungrounded spawn,
slow or misaligned launch, missing wall collision, insufficient structural damage/deceleration,
countdown drift, duplicate launch, or tagged Lua error.

## Package and install

Stage the contents of `mod` as one MCP mod workspace named `cannon_car_wash`, then use the normal
gated workflow:

```text
mod_validate → mod_pack → mod_install(confirm=true)
```

The resulting zip has `info.json` at its root and repository metadata/icon under
`mod_info/cannon_car_wash`, so it is discoverable by BeamNG's Mod Manager when placed under the
active user profile's `mods/repo` directory.
