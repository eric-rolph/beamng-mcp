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
| `map_trigger_create` | Create a connection-owned disabled Box-trigger draft; no scene object yet |
| `map_trigger_get` | Read one trigger draft/live record owned by the current bridge connection |
| `map_trigger_update` | Edit a disabled draft or explicitly enable/disable it; enabled geometry is immutable |
| `map_trigger_list` | List only trigger records owned by the current bridge connection |
| `map_trigger_events` | Page sanitized enter/exit events for one owned handle with bounded loss-aware cursors |
| `map_trigger_delete` | Confirmed deletion of the live object, if any, and its draft |
| `map_save` | Gated exact-level World Editor save request; BeamNG 0.38 reports it as unverified |
| `lua_bridge_status` | Connection/auth/latency/last error, optional probe |
| `lua_extension_reload` | Reload the allowlisted bridge and wait for fresh authenticated readiness |

Generic map-object mutation authority is bound to the exact object reference, ID, name, class, and
scene registrations captured at creation. Renames refresh that evidence, identity mismatches fail
closed without discarding the record, and mission transitions clear the level-scoped registry so a
recycled numeric ID cannot adopt prior authority. A mismatched record is a non-authorizing
tombstone: it blocks bridge reload until exact managed deletion proves its ID and name absent or
the mission changes.

The trigger API is not a wrapper around generic scene fields. `map_trigger_create` returns a
disabled draft identified by an opaque `trg_...` handle. `map_trigger_update(enabled=true)` creates
an ephemeral `BeamNGTrigger`; setting `enabled=false` deletes that engine object while retaining
the editable draft. Enabled triggers accept no other updates. V1 supports Box volumes, typed
center/contains/overlaps modes, race-corners/bounding-box tests, and a single
`emit_bridge_event` action selecting unique enter/exit events. It does not expose scene names,
`luaFunction`, commands, ticking, dynamic fields, persistence, or existing-trigger adoption.

Each engine trigger is `canSave=false`, uses the fixed `onBeamNGTrigger` callback, and is deleted
with its draft when the owning authenticated peer disappears, a mission changes, or the bridge
unloads under normal engine behavior. If exact identity or deletion cannot be proved, the bridge
instead retains an ownerless, event-silent quarantine for an exact cleanup retry or verified
mission teardown; retained quarantines consume the global trigger cap. Upgrade skew fails closed
before mutation with `install-lua --force` guidance.
`lua_extension_reload` also refuses to unload the bridge while any bridge-managed scene record
remains: this includes generic map objects plus trigger drafts, live triggers, and quarantines.
Once accepted, the bridge blocks further scene mutations and rechecks both registries immediately
before unloading, so another request in the same engine event batch cannot add state behind the
guard. Delete managed objects and triggers through their MCP tools before requesting a reload.
That guard applies to MCP-requested reloads. An operator-forced unload through BeamNG's console or
extension manager remains unsafe: exact generic-object authorization is lost, and although the
unload hook attempts trigger cleanup, module-local quarantine evidence cannot survive if the
engine unloads the extension despite a cleanup failure.
Do not force-unload the bridge while managed scene records remain.
If a trigger mutation times out or its caller is cancelled after sending begins, the client closes
that bridge peer before returning; disconnect cleanup removes connection-owned drafts and live
triggers whose mutation outcome could otherwise be unknown.

`map_trigger_events` first revalidates current ownership with `trigger.get`, then reads only typed
events already sanitized by the Python bridge client. Supply the prior page's `next_sequence` as
`after_sequence`. `truncated=true` reports deque overflow or another sequence gap; when every
requested event has already fallen out of the buffer, the next cursor advances safely to the
trigger's current sequence instead of repeatedly returning the same empty page.

BeamNG's own volume sampling still depends on trigger mode, test type, object bounds, and motion.
In the 0.38.6 deterministic harness, a broad rotated volume crossed reliably while a very thin
rotated volume could miss a teleport-based crossing. Validate thin/speed-trap geometry with
`debug=true`, representative vehicle motion, and the intended mode/test pair; the
[official trigger reference](https://documentation.beamng.com/modding/levels/level_classes/beamngtrigger/)
likewise calls out test-type/object-bound mismatches as a common cause of missed events.

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

## Blender-evidenced soft-body authoring

| Tool | Purpose |
| --- | --- |
| `softbody_handoff_create` | Create a capped, expiring, one-use Blender inbox and return the exact `blender_execute_code` string to run verbatim |
| `softbody_handoff_validate` | Stable-read and verify raw `beamng-blender-handoff-v1` DAE/hash/axis/bounds/cage-vertex/topology evidence; return measured volume, node/base IDs, and refnodes without writing a mod |
| `softbody_mod_build` | Convert to canonical `beamng-structure-v1`, apply reviewed mass/material/mechanism policy, compile deterministic JBeam/configuration metadata, consume the slot, and transactionally commit the bundle |
| `softbody_mod_validate` | Recompile an assembled bundle from embedded provenance and compare every generated file and hash |

The Blender and BeamNG servers are peers; the MCP client executes the exact generated runner
through Blender MCP by passing the returned `blender_execute_code` verbatim, not by reconstructing
code from `blender_runner_path`. The BeamNG tools never accept arbitrary source paths,
model-authored node coordinates, or separate control-object nodes. V1 requires
`asset_name == mod_name`, asset-namespaced visual/cage/material names, exactly one visual
mesh/material/flexbody and structural asset per mod, a connected normal-beam cage, and no external
textures. Consequently, the public path cannot represent a disconnected moving crusher plate;
hydros and rails/slidenodes do not substitute for a structural connection during validation.

`softbody_mod_build` supports typed hydros and rails/slidenodes; a BeamNG hinge is a tested
node/beam/rail/torsion pattern, not a literal `hinges` section. A volume-based mass input must equal
the measured Blender volume returned by validation. Replacing any existing generated target
requires `overwrite=true` and a complete `expected_sha256` map for every target that currently
exists. The slot is consumed before commit, so a commit failure requires a new handoff. V1 runtime
builds require Collada DAE and generate `<asset>.jbeam`, `<asset>.dae`, `main.materials.json`,
`info.json`, `<asset>.pc`, `info_<asset>.json`, and `<asset>.structure.json`.

Slots bind the exact structured request and reviewed helper/runner digests in the current server
session, fail closed after restart, and are capped/pruned. Those hashes are consistency evidence,
not cryptographic attestation. Blender MCP 1.6.4's unauthenticated loopback execute-code interface
is full-trust local code execution and may capture code telemetry; set
`BLENDER_MCP_DISABLE_TELEMETRY=1` before launching it for private assets. See
[Soft-Body Authoring](SOFTBODY_AUTHORING.md).

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
- Typed triggers are always bridge-created and connection-owned. The existing-object gate cannot
  adopt a level trigger, and `map_save` cannot persist one.
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
- `beamng://authoring/softbody/v1`

Job resources expose the same `stage` and `cancellable` state as the job tools.

Prompts:

- `inspect_current_scene`
- `build_and_test_mod`
- `build_softbody_mod`
- `cautious_autonomous_run`
