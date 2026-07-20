# Setup

## 1. Choose a feature tier

For the supported sensor/scenario/autonomy surface, use BeamNG.tech 0.38 with BeamNGpy 1.35.1.
Retail BeamNG.drive 0.38.6 can use the included GELua bridge, but BeamNGpy behavior there is
experimental. In the tested retail build, BeamNGpy `Camera` is explicitly license-gated, so
production `vision-lane` and `hybrid` modes require BeamNG.tech; the repository's retail RenderView
GPU fixture is test-only.

BeamNGpy compatibility is version-sensitive. Consult the official
[compatibility table](https://documentation.beamng.com/api/beamngpy/v1.35/compatibility.html)
before upgrading either side.

## 2. Install Python dependencies

```powershell
git clone https://github.com/eric-rolph/beamng-mcp.git
Set-Location .\beamng-mcp
uv sync --extra dev
```

For local neural perception:

```powershell
uv sync --extra vision --extra dev
```

Copy and edit the example configuration if auto-detection is insufficient:

```powershell
Copy-Item .\beamng-mcp.example.toml .\beamng-mcp.toml
```

Paths accept forward slashes in TOML, which avoids Windows backslash escaping.

### Direct BeamNG executable

Set both the installation root and direct 64-bit simulator executable when auto-detection could
select a launcher or a different installed edition:

```toml
[beamng]
home = "C:/Games/BeamNG.drive"
binary = "Bin64/BeamNG.drive.x64.exe"
user = "C:/Users/you/AppData/Local/BeamNG/BeamNG.drive/current"
```

`binary` may be absolute or relative to `home`. Use `Bin64/BeamNG.tech.x64.exe` for a licensed Tech
installation. The runtime derives this value from a detected direct executable when it is omitted.

### BeamNG 0.37+ user-folder discovery

BeamNG no longer uses a version-named user directory as the default. The supported Windows lookup
is:

1. Read `%LOCALAPPDATA%\BeamNG\BeamNG.drive.ini`.
2. If `userFolder = ...` is present and absolute, use it.
3. If it is relative, resolve it relative to the INI file's directory.
4. If it is empty or absent, use `%LOCALAPPDATA%\BeamNG\BeamNG.drive\current`.

If `beamng.user` is set explicitly, that value wins. You can always verify the active location with
**Launcher → Manage User Folder → Open in Explorer**. These rules come from BeamNG's official
[version information](https://documentation.beamng.com/support/version/) and
[user-folder guide](https://documentation.beamng.com/support/userfolder/).

The configured value is always the exact active folder used for mods and bridge-token discovery.
When that folder is named `current`, BeamNG MCP passes its parent to BeamNG's `-userpath` launch
argument because modern BeamNG creates/appends `current` itself. Do not work around this by setting
`beamng.user` to the parent; doing so would make mod installation and token discovery target the
wrong directory.

## 3. Run diagnostics

```powershell
uv run beamng-mcp doctor
uv run beamng-mcp doctor --json
```

The command checks installation paths, package versions, the resolved current user folder, the Lua
mod, NVIDIA GPU information, and the configured/discovered Blender executable. Blender is launched
briefly in background mode with its active user/add-on profile to report its exact version and
unambiguous selection-only Collada export operator. glTF availability is true only when its operator
exposes `filepath`, `export_format`, `use_selection`, and `export_yup`, matching the reviewed
exporter's deterministic call. BeamNG is not launched or connected, and secrets are never revealed.

## 4. Install the Lua bridge

```powershell
uv run beamng-mcp install-lua
```

The installer writes:

```text
%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\mods\unpacked\beamng_mcp\
├── lua/ge/extensions/beamng_mcp/bridge.lua
├── scripts/beamng_mcp/modScript.lua
├── settings/beamng_mcp.json
└── mod_info/beamng_mcp/info.json
```

For a customized `userFolder`, replace the prefix with the resolved directory. The packaged
`modScript.lua` loads the extension when BeamNG activates the mod; this follows BeamNG's extension
model and unpacked-mod layout described in the official
[extension guide](https://documentation.beamng.com/modding/programming/extensions/) and
[mod-packing guide](https://documentation.beamng.com/modding/mod-support/mod_packing/).

It replaces the token placeholder with a random per-install secret. Use `--force` to update a
recognized installation. If a directory exists without the expected config, the installer refuses
to replace it.

BeamNGpy also requests the bridge during `simulator_connect`. For troubleshooting a bridge-only
retail Drive session, open the GELua console and load:

```lua
extensions.load("beamng_mcp/bridge")
```

The bridge should log a loopback WebSocket on port 8765. It intentionally refuses to start when
the token placeholder is still present.

## 5. Configure the AI client

stdio is recommended for local clients:

```json
{
  "mcpServers": {
    "beamng": {
      "command": "C:/absolute/path/beamng-mcp/.venv/Scripts/beamng-mcp.exe",
      "args": ["serve", "--transport", "stdio"],
      "env": {
        "BEAMNG_MCP_CONFIG": "C:/absolute/path/beamng-mcp/beamng-mcp.toml"
      }
    }
  }
}
```

Do not point `BEAMNG_MCP_CONFIG` at a file containing committed secrets.

## 6. Optional Streamable HTTP

Generate a 32+ character random token, store it outside git, and set:

```powershell
$env:BEAMNG_MCP_HTTP_TOKEN = "..."
uv run beamng-mcp serve --transport streamable-http --port 8766
```

Endpoint: `http://127.0.0.1:8766/mcp`

Clients must send `Authorization: Bearer <token>`. The server refuses non-loopback hosts. HTTP is
not needed for the normal child-process/stdio configuration.

## 7. Verify through MCP

Call:

1. `capabilities_get`
2. `simulator_status`
3. `lua_bridge_status(probe=true)` after the extension is loaded
4. `simulator_connect`
5. `vehicle_list`

The capability response clearly states whether the session is offline, experimental Drive, or
supported Tech mode.

## Autonomy safety lease

All three `autonomy_start` modes require the authenticated GELua bridge. The runtime first disables
native AI, applies full brake, and warms a configured vision backend. It then arms a lease for the
selected vehicle before starting native AI or a vision controller; the start fails closed and
attempts braking if GELua cannot confirm the lease.

The defaults are:

```toml
[lua]
safety_lease_seconds = 1.0
safety_startup_grace_seconds = 5.0
```

Both settings accept 0.25 through 5 seconds. `safety_startup_grace_seconds` applies only to the
initial arm so camera attachment and first control delivery have a bounded window; model warmup
already completed while the vehicle was braked. Every successful renewal resets the shorter
`safety_lease_seconds` countdown. After changing either value, run
`uv run beamng-mcp install-lua --force` so Python and the installed GELua configuration agree.

If renewal stops, GELua uses game-engine real time to expire the lease, disables vehicle AI, and
sets throttle to zero with full service and parking brake. This protects against a stalled Python
process or control path while the game engine is still updating; it cannot act if BeamNG itself is
frozen. Keep an independent manual emergency-stop path available.

## Blender soft-body authoring

The soft-body workflow uses an existing Blender MCP as a peer server. BeamNG MCP does not embed or
patch Blender MCP. `softbody_handoff_create` returns a random slot containing
`beamng_softbody_export.py` and `run_export.py`, plus a `blender_execute_code` string. After
reviewing the returned paths and selected Blender objects, send that exact string verbatim to
Blender MCP's execute-code tool. Do not retype the runner path or construct a different invocation.

Requirements:

- Blender scene units are Metric with scale 1.0 and Z up.
- V1 requires `asset_name == mod_name`. The visual object, physics cage, and sole DAE material must
  equal the asset name or start with `<asset_name>_`.
- The handoff contains exactly one visual mesh, one physics cage, and one material, producing one
  flexbody and effectively one structural asset per mod. It accepts no external textures.
- Every physics-cage vertex has a unique string POINT attribute named `beamng_node_id`; all public
  handoff nodes come from those contiguous evaluated cage vertices. Separate control-object nodes
  are not supported.
- Four single-node vertex groups define `beamng_ref`, `beamng_back`, `beamng_left`, and
  `beamng_up`; ground-standing assets also define at least three non-collinear `beamng_base`
  nodes.
- Cage edges and X-braces must form one connected normal-beam graph. Build-time hydros,
  rails/slidenodes, and the current schema cannot join otherwise disconnected moving bodies.
- The handoff supplies an explicit proper-rigid world-to-BeamNG transform that preserves +Z and
  maps the chosen asset origin to `(0, 0, 0)`.
- A tested selection-only Collada exporter is registered in Blender. BeamNG 0.38 flexbodies use
  DAE; glTF is diagnostic only. The helper refuses DAE export if it cannot find an unambiguous
  exporter with a selection-only option.

Blender versions can be installed side by side. The validated Windows reference uses portable
Blender 4.5.4 LTS, where the live probe finds the selection-only `wm.collada_export` operator;
Blender 5.2 can remain installed for unrelated work. Download versioned builds from Blender's
[previous versions page](https://www.blender.org/download/previous-versions/), extract each portable
build to its own directory, and select the authoring runtime explicitly:

```toml
[blender]
executable = "C:/Users/you/Applications/Blender/4.5.4/blender.exe"
probe_timeout_seconds = 20.0
```

The exact validated Windows artifacts were:

| Artifact | SHA-256 |
| --- | --- |
| `blender-4.5.4-windows-x64.zip` | `0DE55DF1D99E4E7152605022CB648E795D5D49209C5C5C4889E1A19FB401A054` |
| Blender MCP 1.6.4 `blender_mcp_addon.py` | `BBA60831F5F89A74DEDA0294B131668A086CF46EB35A6A01ABBD0D21D9E92630` |

These hashes identify the tested files; still obtain Blender and
[Blender MCP](https://github.com/ahujasid/blender-mcp) from their official publisher repositories
and verify publisher metadata before installing.

Install and enable the matching Blender MCP 1.6.4 add-on in that runtime's own user profile; on
Windows, a 4.5 add-on normally lives below
`%APPDATA%\Blender Foundation\Blender\4.5\scripts\addons`, not the 5.x profile. Start the loopback
server from the Blender MCP panel only while authoring. Then require
`softbody_authoring.blender_runtime.compatible` to be `true` in `beamng-mcp doctor --json`, and run
the real profile/export checks documented in [Development](DEVELOPMENT.md). The supplied
factory-startup export fixture is the built-in `wm.collada_export` reference; alternate add-on
exporters need an equivalent active-profile fixture with a reviewed expected operator. Capability
probing is authoritative: it loads the active profile so an add-on that registers a second DAE
exporter makes the result ambiguous and fail closed. Do not infer DAE support from a version string
alone. When no explicit binary is configured, discovery probes common side-by-side candidates
until one satisfies the DAE contract; an explicit path probes only that requested runtime.

Blender MCP 1.6.4 exposes an unauthenticated loopback execute-code interface with the authority of
the Blender process and may capture executed-code telemetry. Keep it on loopback, review the
returned code, and set `BLENDER_MCP_DISABLE_TELEMETRY=1` before launching Blender MCP when working
with private models or paths. Handoff hashes detect consistency changes; they are not
cryptographic attestation.

Slots are capped, expire, are single-use, and are bound to the exact structured request plus the
reviewed helper/runner hashes in the current BeamNG MCP process. A server restart invalidates all
outstanding slots even when their directories still exist; create a new handoff. Before a build,
review the validation summary's measured volume, node IDs, base-node IDs, and refnodes. If using
the volume/density mass route, submit that measured volume unchanged.

See [Soft-Body Authoring](SOFTBODY_AUTHORING.md) for the complete model/cage convention, tool
sequence, mechanical rigging rules, and in-game acceptance checklist.

## Mod installation

Writing, validating, and packing a mod stays available with the safe defaults. Copying a package
into BeamNG's active mod directory requires both an operator configuration change and a confirmed
tool call:

```toml
[workspace]
allow_mod_install = true
max_file_bytes = 2097152
max_mod_files = 4096
max_mod_bytes = 536870912
```

Then use `mod_install(confirm=true)`. `mod_test_start(install=true)` is subject to the same
configuration gate and requires `confirm_install=true`.

Despite its historical tool name, `mod_test_start` performs static package checks and an optional
copy only. It does not activate the mod or run BeamNG. The repository now has an opt-in developer
regression that builds a concrete ramp with real Blender, installs it into a marked disposable
profile, loads it through BeamNGpy, and steps physics; this is not exposed as an unrestricted MCP
tool and does not replace the broader manual collision/mechanism checklist.

An authored mod containing Lua is code that BeamNG will execute when the mod is activated. The
validator checks paths, quotas, JSON, symlinks, and some suspicious Lua patterns, but it is not a
sandbox. Review the packed artifact and leave `allow_mod_install = false` for pack-only workflows.

## Existing map objects

The bridge may create and subsequently edit objects it manages. Updating or deleting objects that
were already part of the loaded level is disabled by default. To opt in for a cloned test level:

1. Set `workspace.allow_existing_map_object_edits = true`.
2. Re-run `install-lua --force` to copy the independent gate into GELua configuration.
3. Inspect the exact object before updating it; deletion still requires `confirm=true`.

This gate is independent from persistent saving. Enabling existing-object edits does not enable
`map_save`.

## Ephemeral typed triggers

Typed triggers do not use either map-edit operator gate because they cannot adopt or persist
existing level objects. Create a disabled draft, inspect it, explicitly enable it, then disable and
delete it when the test finishes:

```text
map_trigger_create
map_trigger_update(enabled=true)
map_trigger_get
map_trigger_events(after_sequence=0)
map_trigger_update(enabled=false)
map_trigger_delete(confirm=true)
```

The v1 bridge creates Box volumes only and reports selected vehicle `enter`/`exit` events through
its authenticated connection. It does not accept a scene name, Lua callback, command, tick, or
arbitrary action. Drafts are connection-local and are discarded on disconnect or mission change.
Use each event page's `next_sequence` for the next `map_trigger_events` call, and treat
`truncated=true` as an explicit observation gap rather than assuming no trigger activity occurred.
After upgrading beamng-mcp, run `uv run beamng-mcp install-lua --force`; the Python client refuses
trigger calls if the installed extension does not advertise the matching typed handlers.

## Persistent map editing

Leave it disabled for normal operation. To enable it:

1. Work from a cloned writable level under the user folder.
2. Set `workspace.allow_persistent_map_edits = true` in TOML.
3. Re-run `install-lua --force` so GELua's independent config gate changes too.
4. Open and initialize World Editor.
5. Read the loaded level identifier and pass that exact value with confirmation, for example
   `map_save(level="west_coast_usa", confirm=true)`.

`level` is mandatory and must match the loaded level. Changing the Python flag without updating
the installed Lua config is intentionally insufficient.

## Disposable live-test profile

Never run the local integration suite against your normal BeamNG `current` folder. Create a
dedicated root whose active child is named `current`, mark that exact active directory, and install
an independent bridge there:

```powershell
$testBase = Join-Path $env:LOCALAPPDATA "beamng-mcp\test-users\BeamNG-0.38.6"
$testUser = Join-Path $testBase "current"
New-Item -ItemType Directory -Force -Path $testUser | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $testUser ".beamng-mcp-test-user") | Out-Null
uv run beamng-mcp install-lua --user $testUser --force
```

The sentinel is only the first path guard. The harness also takes an exclusive lock for that exact
profile, reserves random loopback BeamNG tcom and (where used) Lua WebSocket ports, atomically
applies a temporary random bridge port/token only inside this profile, and performs no scenario or
Lua mutation until BeamNGpy proves it launched and owns a still-running process. If it attached to
an existing listener instead, it disconnects without sending quit. Cleanup may quit/terminate only
the owned process and restores the original bridge configuration after shutdown.

There is an unavoidable small bind-then-close race while handing a reserved port to BeamNG. The
process-ownership assertion catches a competing tcom listener, while the fresh WebSocket token
prevents authentication to a stale/unrelated bridge. The tests also use temporary scenario names,
avoid persistent level saves, and remove their installed test package. Review the exact paths and
commands in [Development](DEVELOPMENT.md) before running them.

## Troubleshooting

### Bridge probe fails

- Confirm BeamNG is running and the GELua extension is loaded.
- Confirm port 8765 is not used by another extension/process.
- Run `install-lua --force` after changing versions or config.
- Check the BeamNG log for `beamng_mcp_bridge` messages.
- Ensure Windows Firewall permits loopback communication.

### BeamNGpy cannot connect

- Confirm the configured home contains `Bin64/BeamNG.tech.x64.exe` or
  `Bin64/BeamNG.drive.x64.exe`.
- Set `beamng.binary` to that direct executable if launcher discovery selects the wrong edition.
- Confirm `beamng.user`, or `userFolder` in `BeamNG.drive.ini`, resolves to the running simulator's
  current user folder.
- Keep host/listen IP on `127.0.0.1`.
- Do not assume retail Drive is a supported BeamNGpy target.

### Vision backend unavailable

- Install `.[vision]`.
- For SegFormer, cache the model locally or explicitly set `allow_model_downloads = true`.
- For ONNX, confirm the path, input/output layouts, class IDs, and available execution providers.
- In `doctor --json`, require
  `vision_runtime.onnxruntime.provider_libraries.CUDAExecutionProvider.loadable=true`; the provider
  list by itself can advertise a DLL whose CUDA dependencies cannot load.
- Keep `onnxruntime-gpu<1.27` with this CUDA 12.8 profile. ONNX Runtime 1.27 removed CUDA 12 support.
- Treat a non-loadable TensorRT provider as unavailable until the matching TensorRT runtime is
  installed; CUDA remains the supported GPU fallback.
- On Blackwell, use CUDA 12.8+ compatible packages.

### Blender handoff reports Collada unavailable

- Inspect `softbody_authoring.blender_runtime` in `beamng-mcp doctor --json`; it includes the exact
  executable, version, active-profile operator, deterministic glTF capability, and fail-closed error.
- Set `blender.executable` or `BEAMNG_MCP_BLENDER_EXECUTABLE` to the intended side-by-side binary.
- A Blender MCP executable on `PATH` does not prove that its add-on is enabled in this Blender
  profile. Run the profile test from [Development](DEVELOPMENT.md).
- Require one unambiguous export operator with a selection-only option. Disable or remove duplicate
  profile DAE exporters rather than relying on factory-startup results. A glTF exporter does not
  satisfy the BeamNG 0.38 soft-body runtime contract.
