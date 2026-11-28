# Official MCP comparison — November 8, 2026

## Evidence and scope

Compared the live official `beamng-game` 1.0.0 catalog (102 tools, MCP 2025-11-25)
and the locally installed `lua/ge/extensions/mcp` implementation. The installed engine
reports 0.40.5.0.302427. Official release information:
https://beamng.tech/blog/beamng-tech-039/

This change adds nine typed MCP tools covering 53 native actions, bringing this server
to 66 tools. It reuses the installed official server over loopback HTTP; it does not copy
BeamNG's licensed Lua implementation into this MIT repository. The endpoint is configurable
but restricted to numeric loopback addresses and `/mcp`. No redirects or environment proxies
are followed. Responses, query geometry, list bounds, and image encodings are checked.
Unknown actions and extra arguments fail closed. Native simulation, vehicle and lighting changes use the existing
autonomy interlock. No mutation is retried automatically after an uncertain response.

## Compatibility finding

The native route attaches to a running retail game independently of BeamNGpy. On this machine,
the old isolated BeamNGpy live gate failed: retail 0.40.5 lacks `tech_techCore`, and the game's
`-tcom` startup path fails before the socket becomes available. The owned test process was
terminated by its watchdog. Full legacy control/sensor/physics compatibility is not established.
The existing BeamNGpy API pin remains unchanged; its mock signature checks pass, which does not
establish runtime compatibility. Use native_status/native_inspect first for a running game.

The official API is broader, including unrestricted Lua/JS execution and filesystem/editor
mutations. Forwarding all of those would bypass this repository's documented controls.
Consequently this is an integration and feature expansion, not full feature parity or a claim
of superior runtime performance. Existing/narrower rows below are alternatives or partial
coverage; BeamNGpy-dependent rows do not become operational merely because native MCP connects.

Upstream async get_ai/get_electrics have shared previous-result slots without request/vehicle
correlation. They are not forwarded as if they were fresh attested sensor readings. Screenshots
also use a shared pending slot; the tool documents this and is not used for autonomy. Log queries consume a shared diagnostic cursor; instability queries now preserve events by
default (clear=false). Native inspection snapshots may return
large catalogs; the response byte cap applies, rather than silently returning partial data.

## Tool inventory

Coverage categories: Native: 53, Excluded: 33, Existing / narrower: 15, Equivalent: 1.

| Official tool | Coverage | Route / reason |
| --- | --- | --- |
| `clear_editor_selection` | Native | Reviewed typed request; bounded arguments and response |
| `copy_file` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `create_editor_object` | Existing / narrower | map_object_create (allowlisted classes only) |
| `debug_clear` | Native | Reviewed typed request; bounded arguments and response |
| `debug_draw` | Native | Reviewed typed request; bounded arguments and response |
| `delete_editor_selection` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `delete_file` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `delete_object` | Existing / narrower | map_object_delete (confirmation and ownership gate) |
| `drive_to` | Existing / narrower | vehicle_ai_configure / autonomy_start (BeamNGpy + lease) |
| `dump_vue_state` | Native | Reviewed typed request; bounded arguments and response |
| `editor_load_level` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `editor_redo` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `editor_save_level` | Existing / narrower | map_save (exact level + confirmation + config gate) |
| `editor_status` | Native | Reviewed typed request; bounded arguments and response |
| `editor_undo` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `file_info` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `find_files` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `find_objects` | Native | Reviewed typed request; bounded arguments and response |
| `fit_view_to_selection` | Native | Reviewed typed request; bounded arguments and response |
| `get_ai` | Existing / narrower | vehicle_state / autonomy_status (partial) |
| `get_camera_state` | Native | Reviewed typed request; bounded arguments and response |
| `get_configs` | Native | Reviewed typed request; bounded arguments and response |
| `get_editor_selection` | Native | Reviewed typed request; bounded arguments and response |
| `get_electrics` | Existing / narrower | sensor_attach + sensor_poll (correlated BeamNGpy sensor) |
| `get_fps_limit_reason` | Native | Reviewed typed request; bounded arguments and response |
| `get_ground_at_point` | Native | Reviewed typed request; bounded arguments and response |
| `get_instability` | Native | Reviewed typed request; bounded arguments and response |
| `get_logs` | Native | Reviewed typed request; bounded arguments and response |
| `get_navgraph` | Native | Reviewed typed request; bounded arguments and response |
| `get_object` | Native | Reviewed typed request; bounded arguments and response |
| `get_part_tree` | Native | Reviewed typed request; bounded arguments and response |
| `get_performance_metrics` | Native | Reviewed typed request; bounded arguments and response |
| `get_player_vehicle_id` | Native | Reviewed typed request; bounded arguments and response |
| `get_position` | Native | Reviewed typed request; bounded arguments and response |
| `get_render_info` | Native | Reviewed typed request; bounded arguments and response |
| `get_simulation_state` | Native | Reviewed typed request; bounded arguments and response |
| `get_status` | Native | Reviewed typed request; bounded arguments and response |
| `get_time_of_day` | Native | Reviewed typed request; bounded arguments and response |
| `get_ui_state` | Native | Reviewed typed request; bounded arguments and response |
| `get_var` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `get_vehicle` | Native | Reviewed typed request; bounded arguments and response |
| `get_vehicle_damage` | Native | Reviewed typed request; bounded arguments and response |
| `get_vehicle_files` | Native | Reviewed typed request; bounded arguments and response |
| `get_vehicles` | Native | Reviewed typed request; bounded arguments and response |
| `get_vram_usage` | Native | Reviewed typed request; bounded arguments and response |
| `inject_input` | Existing / narrower | vehicle_control (typed inputs; BeamNGpy) |
| `list_dir` | Existing / narrower | mod_file_list (confined workspace only) |
| `list_edit_modes` | Native | Reviewed typed request; bounded arguments and response |
| `list_editor_classes` | Native | Reviewed typed request; bounded arguments and response |
| `list_levels` | Native | Reviewed typed request; bounded arguments and response |
| `load_extension` | Existing / narrower | lua_extension_reload (reviewed extension allowlist only) |
| `load_file` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `load_level` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `make_dir` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `orbit_camera` | Native | Reviewed typed request; bounded arguments and response |
| `pause_physics` | Native | Reviewed typed request; bounded arguments and response |
| `profiler_run` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `raycast` | Native | Reviewed typed request; bounded arguments and response |
| `read_file` | Existing / narrower | mod_file_read (confined workspace only) |
| `recover_vehicle` | Native | Reviewed typed request; bounded arguments and response |
| `reload_lua` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `reload_ui` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `reload_vehicle` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `remove_vehicle` | Existing / narrower | vehicle_remove (confirmation; BeamNGpy) |
| `rename_file` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `reset_vehicle` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `resume_physics` | Native | Reviewed typed request; bounded arguments and response |
| `run_lua` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `run_lua_vehicle` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `run_optick_ui` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `screenshot` | Equivalent | native_screenshot returns image inline; no arbitrary screenshot path API |
| `screenshot_image` | Native | Reviewed typed request; bounded arguments and response |
| `select_editor_objects` | Native | Reviewed typed request; bounded arguments and response |
| `serialize_object` | Native | Reviewed typed request; bounded arguments and response |
| `set_ai` | Existing / narrower | vehicle_ai_configure / autonomy_start (BeamNGpy + lease) |
| `set_camera` | Native | Reviewed typed request; bounded arguments and response |
| `set_edit_mode` | Native | Reviewed typed request; bounded arguments and response |
| `set_editor_active` | Native | Reviewed typed request; bounded arguments and response |
| `set_editor_transform` | Existing / narrower | map_object_update (partial: single target) |
| `set_free_camera` | Native | Reviewed typed request; bounded arguments and response |
| `set_object_field` | Existing / narrower | map_object_update (allowlisted fields / existing-object gate) |
| `set_position` | Native | Reviewed typed request; bounded arguments and response |
| `set_simulation_speed` | Native | Reviewed typed request; bounded arguments and response |
| `set_time_of_day` | Native | Reviewed typed request; bounded arguments and response |
| `set_ui_state` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `set_var` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `show_message` | Native | Reviewed typed request; bounded arguments and response |
| `spawn` | Native | Reviewed typed request; bounded arguments and response |
| `step_physics` | Native | Reviewed typed request; bounded arguments and response |
| `test_configs` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `test_hydro` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `toggle_ui` | Native | Reviewed typed request; bounded arguments and response |
| `trigger_action` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `ui_click` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `ui_eval` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `ui_hover` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `ui_key` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `ui_scroll` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `ui_type` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `unload_extension` | Excluded | Needs unrestricted execution/file/UI access or a separate reviewed mutation/lifecycle policy |
| `view_objects` | Native | Reviewed typed request; bounded arguments and response |
| `write_file` | Existing / narrower | mod_file_write (confined workspace only) |
