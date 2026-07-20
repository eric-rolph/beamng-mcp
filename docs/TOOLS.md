# Tool Catalog

All normal results are structured. Expected operational failures are returned as MCP tool errors
with actionable text. Read-only/destructive/idempotent hints are metadata for clients, not security
controls; the server still enforces gates itself.

## Capability and lifecycle

| Tool | Purpose |
| --- | --- |
| `capabilities_get` | Feature tier, connection state, limitations, complete tool list |
| `simulator_status` | BeamNGpy host, version, Tech flag, last error |
| `simulator_connect` | Connect or launch the configured simulator |
| `simulator_disconnect` | Stop autonomy and disconnect without forcing game exit |
| `simulation_control` | Pause, resume, step, deterministic, or real-time mode |
| `environment_get` | Gravity and time-of-day state |
| `environment_set` | Gravity, time, playback, weather preset |
| `traffic_control` | Spawn, stop, or reset traffic |

## Scenarios and vehicles

| Tool | Purpose |
| --- | --- |
| `scenario_list` | Enumerate scenarios, optionally by level |
| `scenario_load` | Load an existing scenario |
| `scenario_create` | Generate scenario files with vehicles |
| `scenario_control` | Start, restart, or stop loaded scenario |
| `vehicle_list` | Current vehicle inventory and kinematics |
| `vehicle_state` | One vehicle's position/direction/velocity/speed |
| `vehicle_spawn` | Spawn and connect a vehicle |
| `vehicle_remove` | Despawn with explicit confirmation |
| `vehicle_control` | Complete one-shot normalized actuation; may remain latched until a follow-up |
| `vehicle_teleport` | Position/quaternion teleport |
| `vehicle_ai_configure` | Disable or stop native AI; moving modes must use leased `autonomy_start` |

## Sensors

| Tool | Purpose |
| --- | --- |
| `sensor_attach` | Camera, lidar, radar, ultrasonic, GPS, IMU, electrics, damage, state, roads, powertrain |
| `sensor_poll` | Structured small data plus local artifacts for images/large arrays |
| `sensor_remove` | Remove sensor and release resources |

## Maps and Lua

| Tool | Purpose |
| --- | --- |
| `map_road_network` | Bounded road metadata/edges |
| `map_road_edges` | Left/middle/right points for one road |
| `map_object_list` | Allowlisted live GELua scene objects |
| `map_object_get` | One object by name or numeric ID |
| `map_object_create` | Ephemeral allowlisted object creation |
| `map_object_update` | Transform/safe-field update; pre-existing objects require the operator gate |
| `map_object_delete` | Confirmed deletion; pre-existing objects require the operator gate |
| `map_save` | Gated exact-level World Editor save request; BeamNG 0.38 reports it as unverified |
| `lua_bridge_status` | Connection/auth/latency/last error, optional probe |
| `lua_extension_reload` | Reload the allowlisted bridge and wait for fresh authenticated readiness |

## Mods and jobs

| Tool | Purpose |
| --- | --- |
| `mod_scaffold` | Create Lua, vehicle, level, or mixed workspace |
| `mod_file_list` | Paths, sizes, SHA-256 revisions |
| `mod_file_read` | Bounded UTF-8 read with revision |
| `mod_file_write` | Atomic write with optional expected revision |
| `mod_validate` | Structure, JSON, quotas, symlink, and risky-Lua checks; not a sandbox |
| `mod_pack` | Correctly rooted zip artifact |
| `mod_install` | Default-off operator-gated and confirmed user-folder install; backup on overwrite |
| `mod_test_start` | Static validate/pack job; optional gated install, but no in-game execution |
| `job_get` | One job's stage, cancellability, progress, result, and error |
| `job_list` | Recent jobs with stage and cancellability metadata |
| `job_cancel` | Cancel cooperative work; blocking stages return retry guidance |

## Autonomous driving and safety

| Tool | Purpose |
| --- | --- |
| `autonomy_start` | Warm safely, arm the lease, then start targeted native AI, vision lane, or hybrid |
| `autonomy_stop` | Revoke control, stop/brake locally and in GELua, then disarm the lease |
| `autonomy_status` | Rate, latency, watchdog, last control, emergency state, and `engine_deadman_*` telemetry |
| `emergency_stop` | Concurrent full-brake attempts through available paths, then lease disarm |

Safety-relevant tool conditions:

- `mod_install` requires `workspace.allow_mod_install = true` and `confirm=true`. Installing an
  authored Lua mod executes code inside BeamNG.
- Updating or deleting a pre-existing level object requires
  `workspace.allow_existing_map_object_edits = true` in Python and the installed Lua bridge.
- `map_save` requires `workspace.allow_persistent_map_edits = true` in both layers, an initialized
  World Editor, `confirm=true`, and a `level` value equal to the loaded level identifier.
- Every `autonomy_start` mode requires an authenticated GELua lease for the selected vehicle. A
  failed arm prevents start; a missed renewal expires in GELua and disables AI with full service
  and parking brake.
- Tool annotations help clients choose approval UX, but they are not authorization. Default-off
  configuration gates are controlled outside MCP.

## Resources and prompts

Resources:

- `beamng://status`
- `beamng://vehicles`
- `beamng://autonomy`
- `beamng://jobs/{job_id}`

Job resources expose the same `stage` and `cancellable` state as the job tools.

Prompts:

- `inspect_current_scene`
- `build_and_test_mod`
- `cautious_autonomous_run`
