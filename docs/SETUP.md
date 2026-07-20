# Setup

## 1. Choose a feature tier

For the supported sensor/scenario/autonomy surface, use BeamNG.tech 0.38 with BeamNGpy 1.35.1.
Retail BeamNG.drive 0.38.6 can use the included GELua bridge, but BeamNGpy behavior there is
experimental.

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

## 3. Run diagnostics

```powershell
uv run beamng-mcp doctor
uv run beamng-mcp doctor --json
```

The command checks installation paths, package versions, the resolved current user folder, the Lua mod,
and NVIDIA GPU information. It does not launch or connect to BeamNG and does not reveal secrets.

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
copy only. It does not activate the mod or run BeamNG. Use a disposable user folder and inspect the
game log for the runtime smoke test; automated in-game activation is not part of 0.1.0.

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
- Confirm `beamng.user`, or `userFolder` in `BeamNG.drive.ini`, resolves to the running simulator's
  current user folder.
- Keep host/listen IP on `127.0.0.1`.
- Do not assume retail Drive is a supported BeamNGpy target.

### Vision backend unavailable

- Install `.[vision]`.
- For SegFormer, cache the model locally or explicitly set `allow_model_downloads = true`.
- For ONNX, confirm the path, input/output layouts, class IDs, and available execution providers.
- On Blackwell, use CUDA 12.8+ compatible packages.
