from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

import numpy as np
from mcp.server.fastmcp import FastMCP

from .app import Application
from .models import ControlInput, LuaRequest, ScenarioSpec

app = Application()


@asynccontextmanager
async def lifespan(_: FastMCP):
    await app.lua.start()
    await app.safety.start()
    try:
        yield app
    finally:
        await app.safety.close()
        await app.beamng.disconnect()
        await app.lua.close()


mcp = FastMCP(
    "BeamNG MCP",
    instructions=(
        "Control BeamNG safely. Connect first; require an explicit heartbeat while driving."
    ),
    lifespan=lifespan,
)


@mcp.tool()
async def beamng_status() -> dict[str, Any]:
    """Return bridge, simulator, vision, and safety configuration status."""
    return {
        "beamng_connected": app.beamng.connected,
        "lua_connected": app.lua.connected,
        "vision_model": app.settings.vision_model,
        "vision_device": app.settings.vision_device,
        "max_speed_kph": app.settings.max_speed_kph,
    }


@mcp.tool()
async def beamng_connect() -> dict[str, Any]:
    """Connect to a running BeamNG instance, optionally launching it per server configuration."""
    return await app.beamng.connect()


@mcp.tool()
async def scenario_create(spec: ScenarioSpec) -> dict[str, Any]:
    """Create a BeamNG scenario with vehicles and procedural decal roads."""
    return await app.beamng.create_scenario(spec)


@mcp.tool()
async def scenario_load(start: bool = True) -> dict[str, Any]:
    """Load the scenario created during this MCP session and optionally start it."""
    return await app.beamng.load_scenario(start)


@mcp.tool()
async def scenario_export(spec: ScenarioSpec) -> dict[str, Any]:
    """Export a validated scenario specification as a mod-development artifact."""
    return await app.beamng.export_scenario(spec, app.settings.artifact_dir / "scenarios")


@mcp.tool()
async def vehicle_state(vehicle_id: str) -> dict[str, Any]:
    """Poll position, direction, velocity, and other state for a session vehicle."""
    return await app.beamng.state(vehicle_id)


@mcp.tool()
async def vehicle_control(command: ControlInput, speed_kph: float = 0) -> dict[str, Any]:
    """Apply bounded controls. Calls must repeat before the dead-man timeout or brakes engage."""
    safe = app.safety.validate(command, speed_kph, app.settings.max_speed_kph)
    result = await app.beamng.control(safe)
    app.safety.heartbeat(command.vehicle_id)
    return result


@mcp.tool()
async def vehicle_emergency_stop(vehicle_id: str) -> dict[str, Any]:
    """Immediately release throttle and apply brake and parking brake."""
    await app.beamng.stop(vehicle_id)
    return {"stopped": vehicle_id}


@mcp.tool()
async def vehicle_ai_mode(vehicle_id: str, mode: str) -> dict[str, Any]:
    """Set BeamNG's built-in AI mode (for example disabled, random, traffic, or span)."""
    return await app.beamng.ai_mode(vehicle_id, mode)


@mcp.tool()
async def map_roads() -> dict[str, Any]:
    """Read the current level's road graph and road edges."""
    return await app.beamng.map_data()


@mcp.tool()
async def camera_attach(
    vehicle_id: str,
    name: str = "front_camera",
    width: int = 640,
    height: int = 384,
    update_seconds: float = 0.1,
) -> dict[str, Any]:
    """Attach a shared-memory colour/depth camera to a session vehicle."""
    if not 64 <= width <= 4096 or not 64 <= height <= 4096:
        raise ValueError("Camera dimensions must be between 64 and 4096")
    if not 0.01 <= update_seconds <= 5:
        raise ValueError("Camera update_seconds must be between 0.01 and 5")
    return await app.beamng.camera_attach(
        vehicle_id, name, (width, height), update_seconds
    )


@mcp.tool()
async def vision_observe(camera_name: str = "front_camera") -> dict[str, Any]:
    """Run one perception pass over the latest shared-memory camera frame."""
    frame = await app.beamng.camera_frame(camera_name)
    perception = await app.vision.infer(np.asarray(frame))
    return asdict(perception)


@mcp.tool()
async def lua_call(request: LuaRequest) -> dict[str, Any]:
    """Invoke an allow-listed engine extension operation over the local Lua WebSocket."""
    allowed = {"ping", "getVehicleData", "setTimeOfDay", "spawnPrefab", "removeObject"}
    if request.operation not in allowed:
        raise ValueError(f"Lua operation is not allowed: {request.operation}")
    return await app.lua.request(request.operation, request.arguments)


@mcp.tool()
async def vision_load() -> dict[str, Any]:
    """Load the configured perception model on the configured CUDA device."""
    return await app.vision.load()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
