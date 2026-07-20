"""Thin FastMCP v1 adapter; domain services intentionally do not import the SDK."""

from __future__ import annotations

import functools
import hmac
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any, Literal, ParamSpec, TypeVar, cast

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import StrictBool
from starlette.responses import JSONResponse

from .config import Settings
from .errors import BeamNGMCPError, SafetyInterlockError
from .models import (
    AutonomyStart,
    AutonomyStatus,
    BridgeStatus,
    CapabilitySnapshot,
    ConnectionStatus,
    JobInfo,
    MapObjectMutation,
    MapObjectPatch,
    MapTriggerCreate,
    MapTriggerDeleteResult,
    MapTriggerEventPage,
    MapTriggerInfo,
    MapTriggerList,
    MapTriggerPatch,
    ModArtifact,
    ModFileInfo,
    ModFileWrite,
    ModValidation,
    OperationResult,
    ScenarioInfo,
    ScenarioRef,
    ScenarioSelector,
    ScenarioVehiclePlacement,
    SensorReading,
    SensorSpec,
    TriggerCursor,
    TriggerHandle,
    TriggerListLimit,
    VehicleAIConfig,
    VehicleControl,
    VehicleInfo,
    VehicleSpawn,
    VehicleTeleport,
)
from .runtime import Runtime
from .services.jbeam import MATERIAL_CATALOG_VERSION, MATERIAL_PRESETS
from .structural_models import (
    AssetStage,
    AssetStageRequest,
    AssetStageValidation,
    BlenderStructuralManifest,
    StructuralBuildRequest,
    StructuralBuildResult,
    StructuralValidation,
)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])
P = ParamSpec("P")
R = TypeVar("R")

READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
ACTION = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
)
IDEMPOTENT_ACTION = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False
)


def tool_guard(function: F) -> F:
    @functools.wraps(function)
    async def guarded(*args: Any, **kwargs: Any) -> Any:
        try:
            return await function(*args, **kwargs)
        except ToolError:
            raise
        except (BeamNGMCPError, ValueError, OSError) as exc:
            raise ToolError(str(exc)) from exc

    return cast(F, guarded)


def create_mcp_server(
    settings: Settings, runtime: Runtime | None = None
) -> tuple[FastMCP, Runtime]:
    app_runtime = runtime or Runtime(settings)

    @asynccontextmanager
    async def lifespan(_: FastMCP[Any]) -> AsyncIterator[Runtime]:
        async with app_runtime:
            yield app_runtime

    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            f"127.0.0.1:{settings.mcp.port}",
            f"localhost:{settings.mcp.port}",
            f"[::1]:{settings.mcp.port}",
        ],
        allowed_origins=[
            f"http://127.0.0.1:{settings.mcp.port}",
            f"http://localhost:{settings.mcp.port}",
        ],
    )
    mcp = FastMCP(
        "BeamNG MCP",
        instructions=(
            "Control BeamNG through typed, loopback-only tools. Query status and "
            "capabilities first. Use emergency_stop on stale perception, lost control, "
            "or unexpected motion. Blender and BeamNG MCP are peer servers: use the "
            "evidence-bound softbody handoff instead of inventing JBeam coordinates. "
            "Persistent map saves, deletes, and mod installation require explicit confirmation."
        ),
        website_url="https://github.com/eric-rolph/beamng-mcp",
        host=settings.mcp.host,
        port=settings.mcp.port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        lifespan=lifespan,
        transport_security=transport_security,
    )

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def capabilities_get() -> CapabilitySnapshot:
        """Return supported tiers, connection state, safety gates, and available tool names."""

        return await app_runtime.capabilities()

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def simulator_status() -> ConnectionStatus:
        """Return BeamNGpy connection and BeamNG.tech feature-tier status."""

        return await app_runtime.simulator.status()

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def simulator_connect(launch: bool | None = None) -> ConnectionStatus:
        """Connect to BeamNG, optionally launching the configured installation."""

        return await app_runtime.while_autonomy_inactive(
            "connect or relaunch the simulator",
            lambda: app_runtime.simulator.connect(launch=launch),
        )

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def simulator_disconnect() -> OperationResult:
        """Stop autonomous control and disconnect without forcing the game process to quit."""

        return await app_runtime.simulator_disconnect()

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def simulation_control(
        action: Literal["pause", "resume", "step", "deterministic", "realtime"],
        steps: int = 1,
        steps_per_second: int = 60,
        speed_factor: int = 1,
    ) -> OperationResult:
        """Pause, resume, step, or change deterministic simulation timing."""

        async def apply() -> None:
            if action == "pause":
                await app_runtime.simulator.pause()
            elif action == "resume":
                await app_runtime.simulator.resume()
            elif action == "step":
                await app_runtime.simulator.step(steps)
            elif action == "deterministic":
                await app_runtime.simulator.set_deterministic(
                    steps_per_second=steps_per_second, speed_factor=speed_factor
                )
            else:
                await app_runtime.simulator.set_nondeterministic()

        await app_runtime.while_autonomy_inactive("change simulation timing", apply)
        return OperationResult(message=f"Simulation action {action!r} completed")

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def environment_get() -> dict[str, Any]:
        """Read gravity and time-of-day state."""

        return await app_runtime.simulator.environment_state()

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def environment_set(
        gravity: float | None = None,
        time_of_day: float | str | None = None,
        play: bool | None = None,
        weather_preset: str | None = None,
        transition_seconds: float = 1.0,
    ) -> dict[str, Any]:
        """Set gravity, time-of-day playback, and/or a weather preset."""

        return await app_runtime.while_autonomy_inactive(
            "change the simulation environment",
            lambda: app_runtime.simulator.set_environment(
                gravity=gravity,
                time_of_day=time_of_day,
                play=play,
                weather_preset=weather_preset,
                transition_seconds=transition_seconds,
            ),
        )

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def traffic_control(
        action: Literal["spawn", "stop", "reset"],
        max_amount: int | None = None,
        police_ratio: float = 0.0,
        parked_amount: int | None = None,
        stop_vehicles: bool = True,
    ) -> OperationResult:
        """Spawn, stop, or reset simulator traffic."""

        await app_runtime.while_autonomy_inactive(
            "change simulation traffic",
            lambda: app_runtime.simulator.traffic_control(
                action,
                max_amount=max_amount,
                police_ratio=police_ratio,
                parked_amount=parked_amount,
                stop_vehicles=stop_vehicles,
            ),
        )
        return OperationResult(message=f"Traffic action {action!r} completed")

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def scenario_list(level: str | None = None) -> list[ScenarioInfo]:
        """List available BeamNG scenarios, optionally within one level."""

        return await app_runtime.simulator.list_scenarios(level)

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def scenario_load(ref: ScenarioSelector) -> ScenarioInfo:
        """Load an existing scenario by level and scenario name."""

        return await app_runtime.while_autonomy_inactive(
            "load a scenario", lambda: app_runtime.simulator.load_scenario(ref)
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    @tool_guard
    async def scenario_create(
        ref: ScenarioRef,
        vehicles: list[ScenarioVehiclePlacement],
        description: str | None = None,
        load: bool = True,
        overwrite: bool = False,
        confirm_overwrite: bool = False,
    ) -> ScenarioInfo:
        """Create surface-relative scenario files; replacement needs two explicit flags."""

        if overwrite and not confirm_overwrite:
            raise SafetyInterlockError("Scenario overwrite requires confirm_overwrite=true")
        if confirm_overwrite and not overwrite:
            raise ValueError("confirm_overwrite=true requires overwrite=true")
        return await app_runtime.while_autonomy_inactive(
            "create or overwrite a scenario",
            lambda: app_runtime.simulator.create_scenario(
                ref,
                vehicles,
                description=description,
                load=load,
                overwrite=overwrite,
            ),
        )

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def scenario_control(action: Literal["start", "restart", "stop"]) -> OperationResult:
        """Start, restart, or stop the loaded scenario."""

        async def apply() -> None:
            if action == "start":
                await app_runtime.simulator.scenario_start()
            elif action == "restart":
                await app_runtime.simulator.scenario_restart()
            else:
                await app_runtime.simulator.scenario_stop()

        await app_runtime.while_autonomy_inactive("change scenario lifecycle", apply)
        return OperationResult(message=f"Scenario action {action!r} completed")

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def vehicle_list() -> list[VehicleInfo]:
        """List vehicles and their current kinematic state."""

        return await app_runtime.simulator.list_vehicles()

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def vehicle_state(vehicle_id: str) -> VehicleInfo:
        """Read one vehicle's position, velocity, direction, and speed."""

        return await app_runtime.simulator.vehicle_state(vehicle_id)

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def vehicle_spawn(spec: VehicleSpawn) -> VehicleInfo:
        """Spawn at measured surface plus model-origin clearance and connect."""

        return await app_runtime.while_autonomy_inactive(
            "spawn a vehicle", lambda: app_runtime.simulator.spawn_vehicle(spec)
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    @tool_guard
    async def vehicle_remove(vehicle_id: str, confirm: bool = False) -> OperationResult:
        """Despawn a vehicle; confirm=true is required."""

        if not confirm:
            raise SafetyInterlockError("Vehicle removal requires confirm=true")
        await app_runtime.while_autonomy_inactive(
            "remove a vehicle", lambda: app_runtime.simulator.remove_vehicle(vehicle_id)
        )
        return OperationResult(message=f"Vehicle {vehicle_id!r} removed")

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def vehicle_control(command: VehicleControl) -> OperationResult:
        """Apply clamped steering, throttle, brake, clutch, parking brake, and gear inputs."""

        await app_runtime.while_autonomy_inactive(
            "apply direct vehicle control",
            lambda: app_runtime.simulator.control_vehicle(command),
        )
        return OperationResult(message=f"Control applied to {command.vehicle_id}")

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def vehicle_teleport(command: VehicleTeleport) -> OperationResult:
        """Teleport a vehicle to a position and optional quaternion rotation."""

        success = await app_runtime.while_autonomy_inactive(
            "teleport a vehicle", lambda: app_runtime.simulator.teleport_vehicle(command)
        )
        return OperationResult(ok=success, message=f"Teleport returned {success}")

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def vehicle_ai_configure(config: VehicleAIConfig) -> OperationResult:
        """Disable or stop standalone native AI; moving modes require autonomy_start."""

        if config.mode not in {"disabled", "stopping"}:
            raise SafetyInterlockError(
                "Moving native AI modes require autonomy_start(mode='native-ai') so the "
                "engine deadman is armed"
            )

        await app_runtime.while_autonomy_inactive(
            "reconfigure vehicle AI", lambda: app_runtime.simulator.configure_ai(config)
        )
        return OperationResult(message=f"Native AI configured for {config.vehicle_id}")

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def sensor_attach(spec: SensorSpec) -> OperationResult:
        """Attach a camera, lidar, radar, ultrasonic, GPS, IMU, or vehicle-state sensor."""

        await app_runtime.while_autonomy_inactive(
            "attach a sensor", lambda: app_runtime.simulator.attach_sensor(spec)
        )
        return OperationResult(message=f"Sensor {spec.name!r} attached")

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def sensor_poll(name: str) -> SensorReading:
        """Poll a sensor; large arrays and images are saved as bounded local artifacts."""

        return await app_runtime.simulator.poll_sensor(name)

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def sensor_remove(name: str) -> OperationResult:
        """Remove an attached sensor and release shared memory."""

        await app_runtime.while_autonomy_inactive(
            "remove a sensor", lambda: app_runtime.simulator.remove_sensor(name)
        )
        return OperationResult(message=f"Sensor {name!r} removed")

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def map_road_network(
        include_edges: bool = True, drivable_only: bool = True, limit: int = 500
    ) -> dict[str, Any]:
        """Read a bounded slice of the current map road network."""

        if not 1 <= limit <= 2000:
            raise ValueError("limit must be between 1 and 2000")
        network = await app_runtime.simulator.road_network(
            include_edges=include_edges, drivable_only=drivable_only
        )
        items = list(network.items())
        result = {str(road_id): road for road_id, road in items[:limit]}
        result["_meta"] = {
            "returned": min(len(items), limit),
            "total": len(items),
            "truncated": len(items) > limit,
        }
        return result

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def map_road_edges(road_id: str) -> list[dict[str, Any]]:
        """Read left, middle, and right edge points for one road."""

        return await app_runtime.simulator.road_edges(road_id)

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def map_object_list(
        class_name: str | None = None, name_prefix: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        """List allowlisted live scene objects through the GELua bridge."""

        return await app_runtime.map_list_objects(
            class_name=class_name, name_prefix=name_prefix, limit=limit
        )

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def map_object_get(object_id: str | int) -> dict[str, Any]:
        """Read one live scene object by name or numeric ID."""

        return await app_runtime.map_get_object(object_id)

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def map_object_create(mutation: MapObjectMutation) -> dict[str, Any]:
        """Create an allowlisted live scene object without saving the level."""

        return await app_runtime.while_autonomy_inactive(
            "create a map object", lambda: app_runtime.map_create_object(mutation)
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    @tool_guard
    async def map_object_update(patch: MapObjectPatch) -> dict[str, Any]:
        """Update an allowlisted live scene object's transform or safe fields."""

        return await app_runtime.while_autonomy_inactive(
            "update a map object", lambda: app_runtime.map_update_object(patch)
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    @tool_guard
    async def map_object_delete(object_id: str | int, confirm: bool = False) -> dict[str, Any]:
        """Delete a live scene object; confirm=true is required."""

        return await app_runtime.while_autonomy_inactive(
            "delete a map object",
            lambda: app_runtime.map_delete_object(object_id, confirm=confirm),
        )

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def map_trigger_create(request: MapTriggerCreate) -> MapTriggerInfo:
        """Create a disabled, ephemeral box-trigger draft with bridge-event actions only."""

        return await app_runtime.while_autonomy_inactive(
            "create a map trigger",
            lambda: app_runtime.map_trigger_create(request),
            propagate_cancellation=True,
        )

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def map_trigger_get(handle: TriggerHandle) -> MapTriggerInfo:
        """Read one bridge-owned trigger by its opaque handle."""

        return await app_runtime.map_trigger_get(handle)

    @mcp.tool(annotations=DESTRUCTIVE)
    @tool_guard
    async def map_trigger_update(patch: MapTriggerPatch) -> MapTriggerInfo:
        """Update a trigger draft or explicitly enable/disable it."""

        return await app_runtime.while_autonomy_inactive(
            "update a map trigger",
            lambda: app_runtime.map_trigger_update(patch),
            propagate_cancellation=True,
        )

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def map_trigger_list(limit: TriggerListLimit = 100) -> MapTriggerList:
        """List a bounded set of bridge-owned ephemeral triggers."""

        return await app_runtime.map_trigger_list(limit=limit)

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def map_trigger_events(
        handle: TriggerHandle,
        after_sequence: TriggerCursor = 0,
        limit: TriggerListLimit = 50,
    ) -> MapTriggerEventPage:
        """Page sanitized bridge events for one currently owned trigger handle."""

        return await app_runtime.map_trigger_events(
            handle,
            after_sequence=after_sequence,
            limit=limit,
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    @tool_guard
    async def map_trigger_delete(
        handle: TriggerHandle, confirm: StrictBool = False
    ) -> MapTriggerDeleteResult:
        """Delete a bridge-owned trigger; confirm=true is required."""

        return await app_runtime.while_autonomy_inactive(
            "delete a map trigger",
            lambda: app_runtime.map_trigger_delete(handle, confirm=confirm),
            propagate_cancellation=True,
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    @tool_guard
    async def map_save(level: str, confirm: bool = False) -> dict[str, Any]:
        """Request an editor save behind both gates; BeamNG 0.38 cannot verify durability."""

        return await app_runtime.while_autonomy_inactive(
            "save the loaded level",
            lambda: app_runtime.map_save(level=level, confirm=confirm),
        )

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def lua_bridge_status(probe: bool = False) -> BridgeStatus:
        """Read bridge status; probe=true attempts an authenticated loopback connection."""

        return await app_runtime.lua.probe() if probe else app_runtime.lua.status()

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def lua_extension_reload(name: str = "beamng_mcp/bridge") -> dict[str, Any]:
        """Reload an extension from the Lua bridge's own strict allowlist."""

        return await app_runtime.while_autonomy_inactive(
            "reload the GELua bridge",
            lambda: app_runtime.reload_lua_extension(name),
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    @tool_guard
    async def mod_scaffold(
        mod_name: str,
        title: str,
        author: str,
        kind: Literal["lua", "vehicle", "level", "mixed"] = "lua",
    ) -> list[ModFileInfo]:
        """Create a new path-confined mod workspace with a manifest and type-specific roots."""

        return await _to_thread(
            app_runtime.mods.scaffold, mod_name, title=title, author=author, kind=kind
        )

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def mod_file_list(mod_name: str) -> list[ModFileInfo]:
        """List mod workspace files with sizes and SHA-256 revisions."""

        return await _to_thread(app_runtime.mods.list_files, mod_name)

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def mod_file_read(mod_name: str, path: str) -> OperationResult:
        """Read one UTF-8 mod file and return its SHA-256 for optimistic writes."""

        content, info = await _to_thread(app_runtime.mods.read_file, mod_name, path)
        return OperationResult(
            message="File read", data={"content": content, "file": info.model_dump()}
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    @tool_guard
    async def mod_file_write(request: ModFileWrite) -> ModFileInfo:
        """Atomically write a UTF-8 mod file, optionally requiring an expected SHA-256."""

        return await _to_thread(app_runtime.mods.write_file, request)

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def softbody_handoff_create(request: AssetStageRequest) -> AssetStage:
        """Create an expiring Blender export slot with a reviewed, exact-coordinate runner."""

        return await _to_thread(app_runtime.structural.create_handoff, request)

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def softbody_handoff_validate(slot_id: str) -> AssetStageValidation:
        """Validate staged DAE hashes, axes, bounds, vertices, topology, refs, and base evidence."""

        return await _to_thread(app_runtime.structural.validate_handoff, slot_id)

    @mcp.tool(annotations=DESTRUCTIVE)
    @tool_guard
    async def softbody_mod_build(request: StructuralBuildRequest) -> StructuralBuildResult:
        """Compile and transactionally assemble one validated Blender handoff as a JBeam prop."""

        return await _to_thread(app_runtime.structural.build, request)

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def softbody_mod_validate(mod_name: str, asset_name: str) -> StructuralValidation:
        """Recompile and hash-check an assembled DAE/JBeam/material/provenance bundle."""

        return await _to_thread(app_runtime.structural.validate_mod, mod_name, asset_name)

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def mod_validate(mod_name: str) -> ModValidation:
        """Validate paths, sizes, manifests, JSON, symlinks, and risky Lua patterns."""

        return await _to_thread(app_runtime.mods.validate, mod_name)

    @mcp.tool(annotations=DESTRUCTIVE)
    @tool_guard
    async def mod_pack(mod_name: str) -> ModArtifact:
        """Build a correctly rooted BeamNG zip after validation."""

        return await _to_thread(app_runtime.mods.pack, mod_name)

    @mcp.tool(annotations=DESTRUCTIVE)
    @tool_guard
    async def mod_install(
        mod_name: str, confirm: bool = False, overwrite: bool = False
    ) -> ModArtifact:
        """Install a packed mod into the configured user folder; confirmation is mandatory."""

        if not confirm:
            raise SafetyInterlockError("Mod installation requires confirm=true")
        return await app_runtime.while_autonomy_inactive(
            "install a mod into the active BeamNG user folder",
            lambda: _to_thread(
                app_runtime.mods.install,
                mod_name,
                app_runtime.installation.user,
                overwrite=overwrite,
            ),
        )

    @mcp.tool(annotations=DESTRUCTIVE)
    @tool_guard
    async def mod_test_start(
        mod_name: str,
        pack: bool = True,
        install: bool = False,
        confirm_install: bool = False,
        overwrite: bool = False,
    ) -> JobInfo:
        """Start static validate/pack checks; optional install does not execute the mod."""

        if install and not confirm_install:
            raise SafetyInterlockError("Test installation requires confirm_install=true")
        if overwrite and not install:
            raise ValueError("overwrite=true requires install=true")
        return await app_runtime.start_mod_test(
            mod_name,
            pack=pack,
            install=install,
            overwrite=overwrite,
        )

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def job_get(job_id: str) -> JobInfo:
        """Read one job's status, current stage, cancellability, result, and error."""

        return app_runtime.jobs.get(job_id)

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def job_list(limit: int = 50) -> list[JobInfo]:
        """List recent jobs with their current stages and cancellability."""

        return app_runtime.jobs.list(limit)

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def job_cancel(job_id: str) -> JobInfo:
        """Cancel cooperative work; non-cancellable stages return an actionable error."""

        return await app_runtime.jobs.cancel(job_id)

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def autonomy_start(spec: AutonomyStart) -> AutonomyStatus:
        """Start native AI, vision lane keeping, or hybrid simulated autonomous driving."""

        return await app_runtime.autonomy_start(spec)

    @mcp.tool(annotations=ACTION)
    @tool_guard
    async def autonomy_stop(reason: str = "operator_stop") -> AutonomyStatus:
        """Stop autonomous driving and apply full braking."""

        return await app_runtime.autonomy_stop(reason=reason)

    @mcp.tool(annotations=READ_ONLY)
    @tool_guard
    async def autonomy_status() -> AutonomyStatus:
        """Read perception rate, latency, controls, watchdog, and emergency state."""

        return app_runtime.autonomy_status()

    @mcp.tool(annotations=IDEMPOTENT_ACTION)
    @tool_guard
    async def emergency_stop(vehicle_id: str | None = None) -> OperationResult:
        """Immediately brake through every connected control path; safe and idempotent."""

        return await app_runtime.emergency_stop(vehicle_id)

    @mcp.resource("beamng://status", mime_type="application/json")
    async def status_resource() -> str:
        return (await app_runtime.capabilities()).model_dump_json(indent=2)

    @mcp.resource("beamng://vehicles", mime_type="application/json")
    async def vehicles_resource() -> str:
        vehicles = await app_runtime.simulator.list_vehicles()
        return json.dumps([vehicle.model_dump(mode="json") for vehicle in vehicles], indent=2)

    @mcp.resource("beamng://autonomy", mime_type="application/json")
    async def autonomy_resource() -> str:
        return app_runtime.autonomy_status().model_dump_json(indent=2)

    @mcp.resource("beamng://jobs/{job_id}", mime_type="application/json")
    async def job_resource(job_id: str) -> str:
        """Return status, stage, cancellability, progress, and outcome for one job."""

        return app_runtime.jobs.get(job_id).model_dump_json(indent=2)

    @mcp.resource("beamng://authoring/softbody/v1", mime_type="application/json")
    def softbody_contract_resource() -> str:
        """Return versioned authoring schemas and explicitly non-authoritative presets."""

        return json.dumps(
            {
                "schema": "beamng-softbody-authoring-resource-v1",
                "raw_handoff_schema": "beamng-blender-handoff-v1",
                "canonical_manifest_version": "beamng-structure-v1",
                "runtime_visual_format": "dae",
                "gltf_status": "diagnostic_only",
                "v1_limits": [
                    "one connected physics-cage graph",
                    "one visual mesh, material, flexbody, structural asset, and mod",
                    "cage vertices only; no separate control-object nodes",
                    "no generated actuator controller or input action",
                    "Blender MCP execute-code remains a full-trust local boundary",
                ],
                "material_catalog": MATERIAL_CATALOG_VERSION,
                "material_presets": {
                    name: asdict(preset) for name, preset in MATERIAL_PRESETS.items()
                },
                "handoff_request_schema": AssetStageRequest.model_json_schema(),
                "build_request_schema": StructuralBuildRequest.model_json_schema(),
                "canonical_manifest_schema": BlenderStructuralManifest.model_json_schema(),
            },
            indent=2,
            sort_keys=True,
        )

    @mcp.prompt()
    def inspect_current_scene() -> str:
        return (
            "Inspect BeamNG safely. Call capabilities_get and simulator_status first; "
            "then list vehicles, read the road network, and query scene objects. "
            "Summarize before making any mutation."
        )

    @mcp.prompt()
    def build_and_test_mod(mod_name: str, goal: str) -> str:
        return (
            f"Build mod {mod_name!r} for this goal: {goal}. Scaffold it, inspect every "
            "file revision before writing, validate, start a pack-only test job, and "
            "report issues. Do not install unless the user explicitly confirms installation."
        )

    @mcp.prompt()
    def build_softbody_mod(mod_name: str, asset_name: str, goal: str) -> str:
        return (
            f"Create BeamNG soft-body asset {asset_name!r} in mod {mod_name!r}: {goal}. "
            "Treat Blender MCP and BeamNG MCP as peers. Author a low-poly visual shell and a "
            "separate sparse physics cage in Blender; assign unique beamng_node_id POINT strings "
            "and the beamng_ref/back/left/up/base vertex groups. Choose and state an explicit "
            "proper-rigid Blender-world to BeamNG-vehicle transform (+X left, +Y backward, +Z "
            "up). Call softbody_handoff_create, then pass its returned blender_execute_code "
            "verbatim to Blender MCP. Call softbody_handoff_validate and stop on any error. Build "
            "with reviewed mass/material/mechanism inputs using softbody_mod_build, then call "
            "softbody_mod_validate and mod_test_start(pack=true). Never invent or hand-edit node "
            "coordinates. Do not install without explicit operator confirmation, and do not call "
            "the asset physically correct until the documented in-game spawn, settle, collision, "
            "actuator-limit, reset, reload, and log checks pass. v1 requires one connected cage; "
            "use a manually reviewed/v2 multi-part assembly for disconnected crusher plates or "
            "other mechanism bodies."
        )

    @mcp.prompt()
    def cautious_autonomous_run(vehicle_id: str) -> str:
        return (
            f"Prepare a cautious simulated autonomous run for {vehicle_id!r}. Verify the "
            "simulator and sensor tier, begin at low speed, monitor autonomy_status, and "
            "call emergency_stop immediately on stale frames, low confidence, bridge "
            "loss, unexpected motion, or operator request."
        )

    return mcp, app_runtime


async def _to_thread(function: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    import asyncio

    return await asyncio.to_thread(function, *args, **kwargs)


class BearerAuthMiddleware:
    """Minimal loopback HTTP bearer gate; stdio does not use HTTP authentication."""

    def __init__(self, app: Any, token: str) -> None:
        if len(token) < 32:
            raise ValueError("HTTP bearer token must contain at least 32 characters")
        self.app = app
        self.token = token.encode("utf-8")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            supplied = headers.get(b"authorization", b"")
            expected = b"Bearer " + self.token
            if not hmac.compare_digest(supplied, expected):
                response = JSONResponse(
                    {"error": "unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
