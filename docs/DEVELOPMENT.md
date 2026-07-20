# Development

## Environment

```powershell
uv sync --extra dev
```

Optional vision dependencies are deliberately separate:

```powershell
uv sync --extra dev --extra vision
```

## Checks

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src/beamng_mcp
uv run pytest -q
uv build
```

The unit suite covers:

- MCP schema generation and official in-memory client transport
- HTTP bearer enforcement
- Lua bridge source contract and live local WebSocket client protocol
- post-0.37 `BeamNG.drive.ini`/`userFolder` discovery and the default `current` directory
- path traversal, reparse points, quotas, optimistic concurrency, zip layout, install gates, and backups
- job lifecycle, bounded admission, stage-aware cancellation, and non-cancellable install handling
- bounded camera/array inputs, finite simulator vectors, and brake-over-throttle behavior
- classical/model backend contracts, lane geometry, speed control, and watchdog timing
- engine-lease arm-before-start, healthy-control renewal, fail-closed renewal errors, MCP adapter
  routing, status telemetry, and stop-before-disarm ordering
- BeamNGpy 1.35 call-signature compatibility for every adapter surface
- Blender capability discovery plus fail-closed DAE operator probing
- WebSocket timeout, reconnect, malformed/oversized response, correlation, method-binding,
  authentication, subprotocol, and BeamNG-native preamble behavior

## Real Blender checks

The Blender tests are opt-in and execute only the explicitly configured binary. Use the same path
for both variables when its user profile contains the enabled Blender MCP add-on:

```powershell
$env:BEAMNG_MCP_TEST_BLENDER = "C:\Users\you\Applications\Blender\4.5.4\blender.exe"
$env:BEAMNG_MCP_TEST_BLENDER_ADDON = $env:BEAMNG_MCP_TEST_BLENDER
uv run pytest -q -m blender tests/test_blender_headless.py
```

The fixture runs Blender with `--factory-startup` to test identity and transformed visual/cage
exports, exact bounds, byte-decoded node IDs, source-state restoration, and the selection-only DAE
operator. This supplied export fixture is specifically the built-in `wm.collada_export` reference
route; `--factory-startup` intentionally disables profile add-ons. An alternate profile-installed
exporter needs its own active-profile fixture with an explicitly reviewed expected operator and
equivalent bounds/state-restoration assertions before it is considered calibrated. The separate
profile check does not use factory startup; it verifies the Blender MCP
panel/start operator is registered in the actual profile and confirms that the background guard
has not opened its server. The Doctor capability probe also uses the actual profile so add-on
operators participate in ambiguity checks; its glTF result requires the same four deterministic
options as the exporter.

## Simulator integration tests

Do not run BeamNG in shared CI. Local integration must use a dedicated active user folder containing
the `.beamng-mcp-test-user` sentinel described in [Setup](SETUP.md). Set explicit installation,
binary, and active-user paths:

Run these commands serially. Do not use pytest-xdist or launch two live files concurrently against
the same profile; the harness takes an exclusive profile lock because each test temporarily owns
that profile's bridge configuration and one BeamNG process.

```powershell
$env:BEAMNG_MCP_TEST_BEAMNG_HOME = "C:\Games\BeamNG.drive"
$env:BEAMNG_MCP_TEST_BEAMNG_BINARY = "Bin64\BeamNG.drive.x64.exe"
$env:BEAMNG_MCP_TEST_BEAMNG_USER = "$env:LOCALAPPDATA\beamng-mcp\test-users\BeamNG-0.38.6\current"

# Retail/Tech classification, scenario lifecycle, deterministic stepping, vehicle state,
# authenticated Lua bridge, road graph, and create/update/list/delete of an ephemeral PointLight.
uv run pytest -q -m beamng_live tests/test_beamng_live.py

# Full real Blender → exact evidence → JBeam/material/package → install → spawn/step regression.
uv run pytest -q -m "blender and beamng_live" tests/test_softbody_pipeline_live.py

# Official MCP client → every tool/resource/prompt → grounded mod/vehicle/map/trigger/autonomy run.
$env:BEAMNG_MCP_TEST_BLENDER = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
uv run pytest -q -m "blender and beamng_live" tests/test_mcp_capability_gauntlet_live.py
```

The adapter preserves the active `current` folder for mod/token operations but passes its parent to
BeamNG's `-userpath` launch argument. The harness reserves a random loopback BeamNG tcom port; where
Lua is exercised, it also reserves a random WebSocket port and applies a temporary bridge
configuration only in the sentinel-marked profile. It requires proof that BeamNGpy launched/owns
the process before any scenario or Lua mutation. Attachment to an existing listener causes a
disconnect without quit; cleanup and the watchdog terminate only an owned process, then restore the
original bridge configuration. A narrow bind-then-close race remains, so process ownership and
fresh bridge authentication are both checked.
Tests use unique disposable scenario names, never save a level, and clean their generated
scenario/package. Retail BeamNG.drive results remain experimental even when this smoke passes.
The capability gauntlet samples four well-separated positions from actual road edges, rebuilds the
scenario with a base-origin ramp at one exact XYZ, and adds model-origin clearance to the other
measured surfaces before placing runtime vehicles. It disables AI, selects neutral, holds the
brakes, steps physics until each object settles, checks model-specific clearance and velocity, and
proves persistent/transient restart behavior. Do not use guessed Z values: BeamNGpy 1.35.1
still cannot apply `cling` when `Scenario.add_vehicle` serializes a prefab, and retail runtime
cling behavior is distance/build dependent.

### GPU camera and perception smoke

The GPU test starts retail BeamNG with DX11 rendering enabled, installs a test-only Lua RenderView
fixture into the isolated profile, captures a non-blank 640×360 frame, and runs the deterministic
OpenCV backend while the simulator still owns the GPU:

```powershell
uv run pytest -q -m beamng_gpu tests/test_beamng_vision_live.py
```

The same three `BEAMNG_MCP_TEST_BEAMNG_*` variables and isolated-user sentinel are mandatory. The
OpenCV leg requires no model. When ONNX Runtime GPU is installed, the test also creates a tiny
local identity graph, runs it through the project backend, and requires the active session to
report `CUDAExecutionProvider` while BeamNG still owns the GPU. To opt into the learned CUDA leg,
first review the
[model card and files at the pinned revision](https://huggingface.co/nvidia/segformer-b0-finetuned-cityscapes-512-1024/tree/7a91500a7086b805eeb868719ea5542a3e0bdeb3),
including its license, then cache it outside the repository with the Hugging Face CLI:

```powershell
$modelRoot = Join-Path $env:LOCALAPPDATA "beamng-mcp\models\segformer-b0-cityscapes"
hf download nvidia/segformer-b0-finetuned-cityscapes-512-1024 `
  --revision 7a91500a7086b805eeb868719ea5542a3e0bdeb3 `
  --local-dir $modelRoot
(Get-FileHash (Join-Path $modelRoot "pytorch_model.bin") -Algorithm SHA256).Hash
# Expected: EC0A4AD8388261A33E9FAD6045FEABF8B0F764BBA6FC5511397FE39714400A91
$env:BEAMNG_MCP_TEST_VISION_MODEL = $modelRoot
uv run pytest -q -m beamng_gpu tests/test_beamng_vision_live.py
```

The test forces `cuda:0`, FP16, and `allow_downloads=false`; setting the variable therefore never
causes a network fetch. This small SegFormer-B0 model is a repeatable CUDA integration baseline,
not a claim of state-of-the-art driving perception. Keep model weights, caches, and any datasets
outside git.

This harness is not a production retail vision fallback. The tested BeamNG.drive 0.38.6 build
rejects BeamNGpy `Camera` with a BeamNG.tech-license error, so production `vision-lane` and `hybrid`
modes still require BeamNG.tech's supported camera path. The Lua fixture exists only inside the
sentinel-marked test profile and is removed after the test.

### Broader manual matrix

At minimum verify:

1. `doctor` resolves the active `userFolder` from `BeamNG.drive.ini`, including relative and
   default `current` cases.
2. `install-lua --force` updates the recognized mod, `modScript.lua`, and token without traversing
   a reparse point.
3. GELua logs bridge startup and `lua_bridge_status(probe=true)` authenticates.
4. BeamNG.tech reports `tech_enabled=true` through `simulator_status`.
5. Create and remove one temporary vehicle.
6. Attach/poll/remove every supported sensor type.
7. Run deterministic pause/step and a low-speed native-AI episode. Confirm the engine lease arms
   before AI starts, renews, and is reported by `autonomy_status`.
8. Run a stationary camera/perception episode before enabling direct controls. Confirm vision or
   hybrid renewal begins only after a successful control delivery.
9. Suspend lease renewal and confirm GELua disables AI and applies full service plus parking brake
   after expiry. Independently delay frames and confirm the Python watchdog brakes.
10. Create a managed ephemeral object in a cloned test level. Verify pre-existing object edits are
    rejected until their operator gate is enabled.
11. Create a typed trigger draft and verify no scene object or event exists before enable. Enable
    it, move a real vehicle out → in → out, verify one typed enter and exit, then disable/delete it.
    Confirm generic trigger creation and callback/command/name injection are rejected.
12. Verify `map_save` rejects a missing or mismatched level ID; exercise a confirmed exact-level
    save only on disposable cloned content.
13. Leave mod installation disabled for pack-only tests. In a dedicated user folder, verify that
    enabling `allow_mod_install` plus confirmation installs the reviewed artifact and that disabling
    the gate blocks both direct and job-based installation.

## Version upgrades

BeamNGpy and BeamNG are coupled. Update the compatibility matrix, package pin, docs, bridge
feature probes, and live integration result together. Native GELua WebSocket/editor bindings are
internal and must be revalidated for every BeamNG update.

The MCP Python SDK is pinned below v2. Keep SDK-specific work in `mcp_adapter.py`; do not leak SDK
types into domain, mod, bridge, or vision modules.

## Release checklist

1. Update version in `pyproject.toml`, `beamng_mcp.__init__`, `server.json`, the packaged Lua
   `mod_info` metadata, and changelog.
2. Refresh the lockfile.
3. Run all checks and a clean wheel/sdist install.
4. Run local BeamNG.tech and Drive-tier integration matrices.
5. Verify the official post-0.37 user-folder rules and packaged `modScript.lua` against the target
   BeamNG release.
6. Exercise every default-off operator gate and exact-target confirmation on disposable content.
7. Fault-inject lease arm, renewal, expiry, explicit stop, and process loss; record the engine-side
   brake result while BeamNG is still updating.
8. Confirm no BeamNG/proprietary assets, generated mods, model weights, or secrets are present.
9. Publish a GitHub release and then PyPI.
10. Validate and publish `server.json` to the MCP Registry after the PyPI artifact exists.
