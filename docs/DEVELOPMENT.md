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

## Simulator integration tests

Do not run BeamNG in shared CI. Local integration should use a dedicated user folder and a known
scenario. At minimum verify:

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
11. Verify `map_save` rejects a missing or mismatched level ID; exercise a confirmed exact-level
    save only on disposable cloned content.
12. Leave mod installation disabled for pack-only tests. In a dedicated user folder, verify that
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
