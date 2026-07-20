from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import SecretStr
from websockets.asyncio.server import serve

from beamng_mcp.adapters.lua_bridge import BRIDGE_SCHEMA, BRIDGE_SUBPROTOCOL, LuaBridgeClient
from beamng_mcp.config import LuaSettings
from beamng_mcp.errors import LuaBridgeError


@pytest.mark.asyncio
async def test_lua_bridge_protocol_correlation_auth_and_events() -> None:
    seen: list[dict] = []

    async def handler(websocket) -> None:
        async for raw in websocket:
            request = json.loads(raw)
            seen.append(request)
            result = {"pong": True}
            if request["method"] == "capabilities":
                result = {
                    "schema": 1,
                    "methods": ["ping"],
                    "bridge_version": "0.1.0",
                    "game_version": "0.38.6",
                }
            response = {
                "schema": BRIDGE_SCHEMA,
                "id": request["id"],
                "type": "response",
                "method": request["method"],
                "result": result,
            }
            await websocket.send(json.dumps(response))
            if request["method"] == "capabilities":
                await websocket.send(
                    json.dumps(
                        {
                            "schema": 1,
                            "type": "event",
                            "method": "telemetry.snapshot",
                            "params": {"speed_mps": 4.5},
                        }
                    )
                )

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(url=f"ws://127.0.0.1:{port}", token=SecretStr("secret" * 8))
        )
        result = await client.call("ping")
        await asyncio.sleep(0)
        assert result == {"pong": True}
        assert all(request["schema"] == 1 for request in seen)
        assert all(request["token"] == "secret" * 8 for request in seen)
        assert client.latest_telemetry == {"speed_mps": 4.5}
        assert client.status().authenticated is True
        assert client.status().bridge_version == "0.1.0"
        assert client.status().game_version == "0.38.6"
        await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_rejects_non_allowlisted_method_without_connecting() -> None:
    client = LuaBridgeClient(LuaSettings(token=SecretStr("secret" * 8)))
    with pytest.raises(LuaBridgeError, match="not allowlisted"):
        await client.call("lua.eval", {"code": "return 1"})


@pytest.mark.asyncio
async def test_lua_bridge_surfaces_structured_errors() -> None:
    async def handler(websocket) -> None:
        async for raw in websocket:
            request = json.loads(raw)
            if request["method"] == "capabilities":
                response = {
                    "schema": 1,
                    "id": request["id"],
                    "type": "response",
                    "method": request["method"],
                    "result": {},
                }
            else:
                response = {
                    "schema": 1,
                    "id": request["id"],
                    "type": "response",
                    "method": request["method"],
                    "error": {"code": "rejected", "message": "denied"},
                }
            await websocket.send(json.dumps(response))

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(url=f"ws://127.0.0.1:{port}", token=SecretStr("secret" * 8))
        )
        with pytest.raises(LuaBridgeError, match="denied"):
            await client.call("world.save_level", {"confirm": True})
        await client.close()
