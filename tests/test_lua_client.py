from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import SecretStr, ValidationError
from websockets.asyncio.server import serve

from beamng_mcp.adapters.lua_bridge import BRIDGE_SCHEMA, BRIDGE_SUBPROTOCOL, LuaBridgeClient
from beamng_mcp.config import LuaSettings
from beamng_mcp.errors import LuaBridgeError
from beamng_mcp.models import MapTriggerDeleteResult, MapTriggerInfo


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
async def test_lua_bridge_accepts_beamng_native_product_info_preamble() -> None:
    async def handler(websocket) -> None:
        first = True
        async for raw in websocket:
            request = json.loads(raw)
            if first:
                first = False
                await websocket.send(
                    'I#{"product":"drive","version":"0.38.6.0.19963","clientId":1}'
                )
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "id": request["id"],
                        "type": "response",
                        "method": request["method"],
                        "result": {"pong": True},
                    }
                )
            )

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(url=f"ws://127.0.0.1:{port}", token=SecretStr("secret" * 8))
        )
        try:
            assert await client.call("ping") == {"pong": True}
            assert client.status().connected is True
            assert client.status().authenticated is True
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_rejects_non_allowlisted_method_without_connecting() -> None:
    client = LuaBridgeClient(LuaSettings(token=SecretStr("secret" * 8)))
    with pytest.raises(LuaBridgeError, match="not allowlisted"):
        await client.call("lua.eval", {"code": "return 1"})


@pytest.mark.asyncio
async def test_lua_bridge_rejects_unadvertised_trigger_method_before_mutation() -> None:
    seen_methods: list[str] = []

    async def handler(websocket) -> None:
        async for raw in websocket:
            request = json.loads(raw)
            seen_methods.append(request["method"])
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "id": request["id"],
                        "type": "response",
                        "method": request["method"],
                        "result": {"methods": ["ping"]},
                    }
                )
            )

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(url=f"ws://127.0.0.1:{port}", token=SecretStr("secret" * 8))
        )
        try:
            with pytest.raises(LuaBridgeError, match="install-lua --force"):
                await client.call(
                    "trigger.create",
                    {"handle": "trg_" + "a" * 32},
                )
            assert seen_methods == ["capabilities"]
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_allows_advertised_trigger_method() -> None:
    seen_methods: list[str] = []

    async def handler(websocket) -> None:
        async for raw in websocket:
            request = json.loads(raw)
            seen_methods.append(request["method"])
            result = (
                {"methods": ["trigger.list"]}
                if request["method"] == "capabilities"
                else {"triggers": [], "count": 0}
            )
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "id": request["id"],
                        "type": "response",
                        "method": request["method"],
                        "result": result,
                    }
                )
            )

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(url=f"ws://127.0.0.1:{port}", token=SecretStr("secret" * 8))
        )
        try:
            assert await client.call("trigger.list", {"limit": 10}) == {
                "triggers": [],
                "count": 0,
            }
            assert seen_methods == ["capabilities", "trigger.list"]
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_queues_only_sanitized_typed_trigger_events() -> None:
    async def handler(websocket) -> None:
        async for raw in websocket:
            request = json.loads(raw)
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "id": request["id"],
                        "type": "response",
                        "method": request["method"],
                        "result": {"methods": ["ping"]},
                    }
                )
            )
            if request["method"] != "capabilities":
                continue
            base = {
                "handle": "trg_" + "a" * 32,
                "event": "enter",
                "subject_id": 7,
                "subject_name": "ego",
                "trigger_id": 42,
                "trigger_name": "beamng_mcp_trigger_" + "a" * 32,
                "sequence": 1,
                "count": 1,
                "time_seconds": 12.5,
            }
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "type": "event",
                        "method": "trigger.event",
                        "params": {**base, "event": "tick"},
                    }
                )
            )
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "type": "event",
                        "method": "trigger.event",
                        "params": {**base, "subject_id": True},
                    }
                )
            )
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "type": "event",
                        "method": "trigger.event",
                        "params": base,
                        "untrusted": "discarded",
                    }
                )
            )

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(url=f"ws://127.0.0.1:{port}", token=SecretStr("secret" * 8))
        )
        try:
            await client.connect()
            for _ in range(20):
                if client.recent_events(limit=50):
                    break
                await asyncio.sleep(0.01)
            assert client.recent_events(limit=50) == [
                {
                    "schema": BRIDGE_SCHEMA,
                    "type": "event",
                    "method": "trigger.event",
                    "params": {
                        "handle": "trg_" + "a" * 32,
                        "event": "enter",
                        "subject_id": 7,
                        "subject_name": "ego",
                        "trigger_id": 42,
                        "trigger_name": "beamng_mcp_trigger_" + "a" * 32,
                        "sequence": 1,
                        "count": 1,
                        "time_seconds": 12.5,
                    },
                }
            ]
            buffered = client.buffered_trigger_events("trg_" + "a" * 32)
            assert len(buffered) == 1
            assert buffered[0].sequence == 1
            assert buffered[0].event == "enter"
            assert client.buffered_trigger_events("trg_" + "b" * 32) == []
        finally:
            await client.close()


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


@pytest.mark.asyncio
async def test_lua_bridge_timeout_does_not_poison_the_next_request() -> None:
    ping_count = 0

    async def handler(websocket) -> None:
        nonlocal ping_count
        async for raw in websocket:
            request = json.loads(raw)
            if request["method"] == "ping":
                ping_count += 1
                if ping_count == 1:
                    continue
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "id": request["id"],
                        "type": "response",
                        "method": request["method"],
                        "result": {"pong": True},
                    }
                )
            )

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=0.1,
            )
        )
        try:
            with pytest.raises(LuaBridgeError, match="timed out"):
                await client.call("ping")

            assert await client.call("ping") == {"pong": True}
            assert client.status().connected is True
            assert client.status().authenticated is True
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_trigger_mutation_timeout_closes_peer_and_reconnects_cleanly() -> None:
    connection_count = 0
    mutation_applied = asyncio.Event()
    first_peer_closed = asyncio.Event()

    async def handler(websocket) -> None:
        nonlocal connection_count
        connection_count += 1
        current_connection = connection_count
        try:
            async for raw in websocket:
                request = json.loads(raw)
                if request["method"] == "trigger.create":
                    mutation_applied.set()
                    await websocket.wait_closed()
                    return
                result = (
                    {"methods": ["trigger.create", "ping"]}
                    if request["method"] == "capabilities"
                    else {"pong": True}
                )
                await websocket.send(
                    json.dumps(
                        {
                            "schema": BRIDGE_SCHEMA,
                            "id": request["id"],
                            "type": "response",
                            "method": request["method"],
                            "result": result,
                        }
                    )
                )
        finally:
            if current_connection == 1:
                first_peer_closed.set()

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=0.1,
            )
        )
        try:
            with pytest.raises(LuaBridgeError, match="timed out"):
                await client.call("trigger.create", {"handle": "trg_" + "a" * 32})

            assert mutation_applied.is_set()
            await asyncio.wait_for(first_peer_closed.wait(), timeout=1.0)
            assert client.status().connected is False
            assert client.status().authenticated is False

            assert await client.call("ping") == {"pong": True}
            assert connection_count == 2
            assert client.status().connected is True
            assert client.status().authenticated is True
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_cancelled_trigger_mutation_closes_uncertain_peer_before_propagating() -> None:
    connection_count = 0
    mutation_applied = asyncio.Event()
    first_peer_closed = asyncio.Event()

    async def handler(websocket) -> None:
        nonlocal connection_count
        connection_count += 1
        current_connection = connection_count
        try:
            async for raw in websocket:
                request = json.loads(raw)
                if request["method"] == "trigger.update":
                    mutation_applied.set()
                    await websocket.wait_closed()
                    return
                result = (
                    {"methods": ["trigger.update", "ping"]}
                    if request["method"] == "capabilities"
                    else {"pong": True}
                )
                await websocket.send(
                    json.dumps(
                        {
                            "schema": BRIDGE_SCHEMA,
                            "id": request["id"],
                            "type": "response",
                            "method": request["method"],
                            "result": result,
                        }
                    )
                )
        finally:
            if current_connection == 1:
                first_peer_closed.set()

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=5.0,
            )
        )
        mutation = asyncio.create_task(
            client.call(
                "trigger.update",
                {"handle": "trg_" + "a" * 32, "enabled": True},
            )
        )
        try:
            await asyncio.wait_for(mutation_applied.wait(), timeout=1.0)
            mutation.cancel()
            with pytest.raises(asyncio.CancelledError):
                await mutation

            await asyncio.wait_for(first_peer_closed.wait(), timeout=1.0)
            assert client.status().connected is False
            assert client.status().authenticated is False

            assert await client.call("ping") == {"pong": True}
            assert connection_count == 2
        finally:
            mutation.cancel()
            await asyncio.gather(mutation, return_exceptions=True)
            await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "validator"),
    [
        ("trigger.create", MapTriggerInfo.model_validate),
        ("trigger.update", MapTriggerInfo.model_validate),
        ("trigger.delete", MapTriggerDeleteResult.model_validate),
    ],
)
async def test_invalid_typed_trigger_mutation_response_closes_exact_peer_before_error(
    method,
    validator,
) -> None:
    peer_closed = asyncio.Event()

    async def handler(websocket) -> None:
        try:
            async for raw in websocket:
                request = json.loads(raw)
                result = {"methods": [method]} if request["method"] == "capabilities" else {}
                await websocket.send(
                    json.dumps(
                        {
                            "schema": BRIDGE_SCHEMA,
                            "id": request["id"],
                            "type": "response",
                            "method": request["method"],
                            "result": result,
                        }
                    )
                )
        finally:
            peer_closed.set()

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=1.0,
            )
        )
        try:
            with pytest.raises(ValidationError):
                await client.call_validated_trigger_mutation(method, {}, validator)

            await asyncio.wait_for(peer_closed.wait(), timeout=1.0)
            assert client.status().connected is False
            assert client.status().authenticated is False
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_cancellation_during_invalid_response_cleanup_waits_for_close_and_wins() -> None:
    peer_closed = asyncio.Event()

    async def handler(websocket) -> None:
        try:
            async for raw in websocket:
                request = json.loads(raw)
                result = (
                    {"methods": ["trigger.create"]} if request["method"] == "capabilities" else {}
                )
                await websocket.send(
                    json.dumps(
                        {
                            "schema": BRIDGE_SCHEMA,
                            "id": request["id"],
                            "type": "response",
                            "method": request["method"],
                            "result": result,
                        }
                    )
                )
        finally:
            peer_closed.set()

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=1.0,
            )
        )
        await client.connect()
        original_close = client._close_socket
        close_started = asyncio.Event()
        release_close = asyncio.Event()

        async def delayed_close(*, expected_ws=None) -> None:
            close_started.set()
            await release_close.wait()
            await original_close(expected_ws=expected_ws)

        client._close_socket = delayed_close  # type: ignore[method-assign]
        mutation = asyncio.create_task(
            client.call_validated_trigger_mutation(
                "trigger.create",
                {},
                MapTriggerInfo.model_validate,
            )
        )
        try:
            await asyncio.wait_for(close_started.wait(), timeout=1.0)
            mutation.cancel()
            await asyncio.sleep(0)
            assert mutation.done() is False

            release_close.set()
            with pytest.raises(asyncio.CancelledError):
                await mutation
            await asyncio.wait_for(peer_closed.wait(), timeout=1.0)
            assert client.status().connected is False
        finally:
            release_close.set()
            await asyncio.gather(mutation, return_exceptions=True)
            await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_waits_for_authentication_before_sending_concurrent_calls() -> None:
    capabilities_seen = asyncio.Event()
    release_capabilities = asyncio.Event()
    seen_methods: list[str] = []
    response_tasks: list[asyncio.Task[None]] = []

    async def send_response(websocket, request: dict[str, object]) -> None:
        if request["method"] == "capabilities":
            await release_capabilities.wait()
        await websocket.send(
            json.dumps(
                {
                    "schema": BRIDGE_SCHEMA,
                    "id": request["id"],
                    "type": "response",
                    "method": request["method"],
                    "result": {},
                }
            )
        )

    async def handler(websocket) -> None:
        async for raw in websocket:
            request = json.loads(raw)
            seen_methods.append(request["method"])
            if request["method"] == "capabilities":
                capabilities_seen.set()
            task = asyncio.create_task(send_response(websocket, request))
            response_tasks.append(task)

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=1.0,
            )
        )
        first = asyncio.create_task(client.call("ping"))
        second: asyncio.Task[dict[str, object]] | None = None
        try:
            await asyncio.wait_for(capabilities_seen.wait(), timeout=1.0)
            second = asyncio.create_task(client.call("telemetry.snapshot"))
            await asyncio.sleep(0.05)

            assert seen_methods == ["capabilities"]
            assert second.done() is False

            release_capabilities.set()
            assert await first == {}
            assert await second == {}
            assert sorted(seen_methods) == ["capabilities", "ping", "telemetry.snapshot"]
            assert client.status().authenticated is True
        finally:
            release_capabilities.set()
            pending = [task for task in (first, second) if task is not None]
            await asyncio.gather(*pending, return_exceptions=True)
            await client.close()
            await asyncio.gather(*response_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_lua_bridge_cancelled_connect_closes_the_partial_connection() -> None:
    capabilities_seen = asyncio.Event()
    peer_closed = asyncio.Event()

    async def handler(websocket) -> None:
        try:
            async for raw in websocket:
                request = json.loads(raw)
                if request["method"] == "capabilities":
                    capabilities_seen.set()
        finally:
            peer_closed.set()

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=5.0,
            )
        )
        connection = asyncio.create_task(client.connect())
        try:
            await asyncio.wait_for(capabilities_seen.wait(), timeout=1.0)
            connection.cancel()
            with pytest.raises(asyncio.CancelledError):
                await connection

            await asyncio.wait_for(peer_closed.wait(), timeout=1.0)
            assert client.status().connected is False
            assert client.status().authenticated is False
        finally:
            connection.cancel()
            await asyncio.gather(connection, return_exceptions=True)
            await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_close_waits_for_an_in_progress_socket_open() -> None:
    handshake_started = asyncio.Event()
    release_handshake = asyncio.Event()
    peer_closed = asyncio.Event()

    async def process_request(_connection, _request):
        handshake_started.set()
        await release_handshake.wait()
        return None

    async def handler(websocket) -> None:
        try:
            async for raw in websocket:
                request = json.loads(raw)
                await websocket.send(
                    json.dumps(
                        {
                            "schema": BRIDGE_SCHEMA,
                            "id": request["id"],
                            "type": "response",
                            "method": request["method"],
                            "result": {},
                        }
                    )
                )
        finally:
            peer_closed.set()

    async with serve(
        handler,
        "127.0.0.1",
        0,
        subprotocols=[BRIDGE_SUBPROTOCOL],
        process_request=process_request,
    ) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=1.0,
            )
        )
        connection = asyncio.create_task(client.connect())
        closing: asyncio.Task[None] | None = None
        try:
            await asyncio.wait_for(handshake_started.wait(), timeout=1.0)
            closing = asyncio.create_task(client.close())

            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(closing), timeout=0.05)

            release_handshake.set()
            await connection
            await closing
            await asyncio.wait_for(peer_closed.wait(), timeout=1.0)
            assert client.status().connected is False
            assert client.status().authenticated is False
        finally:
            release_handshake.set()
            await asyncio.gather(connection, return_exceptions=True)
            if closing is not None:
                await asyncio.gather(closing, return_exceptions=True)
            await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_stale_close_does_not_close_a_replacement_connection() -> None:
    reader_cancelling = asyncio.Event()
    release_reader = asyncio.Event()

    class FakeSocket:
        def __init__(self) -> None:
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    async def slow_reader() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            reader_cancelling.set()
            await release_reader.wait()
            raise

    client = LuaBridgeClient(LuaSettings(token=SecretStr("secret" * 8)))
    old_socket = FakeSocket()
    replacement_socket = FakeSocket()
    old_future: asyncio.Future[dict[str, object]] = asyncio.get_running_loop().create_future()
    replacement_future: asyncio.Future[dict[str, object]] = (
        asyncio.get_running_loop().create_future()
    )
    client._ws = old_socket  # type: ignore[assignment]
    client._reader_task = asyncio.create_task(slow_reader())
    client._pending["old"] = ("ping", old_future)  # type: ignore[assignment]

    closing = asyncio.create_task(client._close_socket())
    try:
        await asyncio.wait_for(reader_cancelling.wait(), timeout=1.0)
        client._ws = replacement_socket  # type: ignore[assignment]
        client._authenticated = True
        client._native_preamble_received = True
        client._pending["replacement"] = (  # type: ignore[assignment]
            "telemetry.snapshot",
            replacement_future,
        )
        release_reader.set()
        await closing

        assert old_socket.close_calls == 1
        assert replacement_socket.close_calls == 0
        assert client._ws is replacement_socket
        assert client._authenticated is True
        assert client._native_preamble_received is True
        assert client._pending == {"replacement": ("telemetry.snapshot", replacement_future)}
        with pytest.raises(LuaBridgeError, match="connection closed"):
            await old_future
        assert replacement_future.done() is False
    finally:
        release_reader.set()
        await asyncio.gather(closing, return_exceptions=True)
        if not old_future.done():
            old_future.cancel()
        elif not old_future.cancelled():
            old_future.exception()
        replacement_future.cancel()
        await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_stale_request_failure_does_not_close_replacement() -> None:
    send_started = asyncio.Event()
    release_send = asyncio.Event()

    class FailingSocket:
        def __init__(self) -> None:
            self.close_calls = 0

        async def send(self, _encoded: str) -> None:
            send_started.set()
            await release_send.wait()
            raise OSError("old socket failed")

        async def close(self) -> None:
            self.close_calls += 1

    class ReplacementSocket:
        def __init__(self) -> None:
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    async def idle_reader() -> None:
        await asyncio.Event().wait()

    client = LuaBridgeClient(LuaSettings(token=SecretStr("secret" * 8)))
    old_socket = FailingSocket()
    replacement_socket = ReplacementSocket()
    old_reader = asyncio.create_task(idle_reader())
    replacement_reader: asyncio.Task[None] | None = None
    client._ws = old_socket  # type: ignore[assignment]
    client._reader_task = old_reader
    client._authenticated = True

    calling = asyncio.create_task(client.call("ping"))
    try:
        await asyncio.wait_for(send_started.wait(), timeout=1.0)
        replacement_reader = asyncio.create_task(idle_reader())
        client._ws = replacement_socket  # type: ignore[assignment]
        client._reader_task = replacement_reader
        client._authenticated = True

        release_send.set()
        with pytest.raises(LuaBridgeError, match="disconnected during ping"):
            await calling

        assert replacement_socket.close_calls == 0
        assert client._ws is replacement_socket
        assert client.status().connected is True
        assert client.status().authenticated is True
    finally:
        release_send.set()
        await asyncio.gather(calling, return_exceptions=True)
        old_reader.cancel()
        await asyncio.gather(old_reader, return_exceptions=True)
        await old_socket.close()
        await client.close()
        if replacement_reader is not None:
            await asyncio.gather(replacement_reader, return_exceptions=True)


@pytest.mark.asyncio
async def test_lua_bridge_reconnects_after_abrupt_disconnect() -> None:
    connection_count = 0

    async def handler(websocket) -> None:
        nonlocal connection_count
        connection_count += 1
        current_connection = connection_count
        async for raw in websocket:
            request = json.loads(raw)
            if request["method"] == "ping" and current_connection == 1:
                websocket.transport.abort()
                return
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "id": request["id"],
                        "type": "response",
                        "method": request["method"],
                        "result": {"connection": current_connection},
                    }
                )
            )

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=0.5,
            )
        )
        try:
            with pytest.raises(LuaBridgeError):
                await client.call("ping")
            assert client.status().connected is False
            assert client.status().authenticated is False

            assert await client.call("ping") == {"connection": 2}
            assert connection_count == 2
            assert client.status().connected is True
            assert client.status().authenticated is True
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_closes_protocol_peer_after_malformed_json() -> None:
    peer_closed = asyncio.Event()

    async def handler(websocket) -> None:
        async for raw in websocket:
            request = json.loads(raw)
            if request["method"] == "ping":
                await websocket.send("{")
                await websocket.wait_closed()
                peer_closed.set()
                return
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "id": request["id"],
                        "type": "response",
                        "method": request["method"],
                        "result": {},
                    }
                )
            )

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=0.5,
            )
        )
        try:
            with pytest.raises(LuaBridgeError):
                await client.call("ping")

            await asyncio.wait_for(peer_closed.wait(), timeout=1.0)
            assert client.status().connected is False
            assert client.status().authenticated is False
            assert "JSONDecodeError" in (client.status().last_error or "")
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_rejects_and_closes_an_oversized_response() -> None:
    peer_closed = asyncio.Event()

    async def handler(websocket) -> None:
        async for raw in websocket:
            request = json.loads(raw)
            result = {} if request["method"] == "capabilities" else {"blob": "x" * 5000}
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "id": request["id"],
                        "type": "response",
                        "method": request["method"],
                        "result": result,
                    }
                )
            )
            if request["method"] == "ping":
                await websocket.wait_closed()
                peer_closed.set()
                return

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=0.5,
                max_message_bytes=4096,
            )
        )
        try:
            with pytest.raises(LuaBridgeError):
                await client.call("ping")

            await asyncio.wait_for(peer_closed.wait(), timeout=1.0)
            assert client.status().connected is False
            assert client.status().authenticated is False
            assert client.status().last_error
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_ignores_wrong_correlation_id_without_poisoning_connection() -> None:
    ping_count = 0

    async def handler(websocket) -> None:
        nonlocal ping_count
        async for raw in websocket:
            request = json.loads(raw)
            response_id = request["id"]
            if request["method"] == "ping":
                ping_count += 1
                if ping_count == 1:
                    response_id = "not-the-request-id"
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "id": response_id,
                        "type": "response",
                        "method": request["method"],
                        "result": {"pong": True},
                    }
                )
            )

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=0.1,
            )
        )
        try:
            with pytest.raises(LuaBridgeError, match="timed out"):
                await client.call("ping")

            assert await client.call("ping") == {"pong": True}
            assert client.status().connected is True
            assert client.status().authenticated is True
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_rejects_response_method_correlation_mismatch() -> None:
    peer_closed = asyncio.Event()

    async def handler(websocket) -> None:
        async for raw in websocket:
            request = json.loads(raw)
            response_method = request["method"]
            if request["method"] == "ping":
                response_method = "capabilities"
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "id": request["id"],
                        "type": "response",
                        "method": response_method,
                        "result": {"pong": True},
                    }
                )
            )
            if request["method"] == "ping":
                await websocket.wait_closed()
                peer_closed.set()
                return

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=0.5,
            )
        )
        try:
            with pytest.raises(LuaBridgeError, match="method mismatch"):
                await client.call("ping")

            await asyncio.wait_for(peer_closed.wait(), timeout=1.0)
            assert client.status().connected is False
            assert client.status().authenticated is False
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_auth_rejection_fails_connect_and_cleans_up() -> None:
    seen_methods: list[str] = []
    peer_closed = asyncio.Event()

    async def handler(websocket) -> None:
        async for raw in websocket:
            request = json.loads(raw)
            seen_methods.append(request["method"])
            await websocket.send(
                json.dumps(
                    {
                        "schema": BRIDGE_SCHEMA,
                        "id": request["id"],
                        "type": "response",
                        "method": request["method"],
                        "error": {"code": "unauthorized", "message": "invalid token"},
                    }
                )
            )
            await websocket.wait_closed()
            peer_closed.set()
            return

    async with serve(handler, "127.0.0.1", 0, subprotocols=[BRIDGE_SUBPROTOCOL]) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("wrong-token" * 4),
                request_timeout_seconds=0.5,
            )
        )
        try:
            with pytest.raises(LuaBridgeError, match="invalid token"):
                await client.connect()

            await asyncio.wait_for(peer_closed.wait(), timeout=1.0)
            assert seen_methods == ["capabilities"]
            assert client.status().connected is False
            assert client.status().authenticated is False
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_lua_bridge_requires_negotiated_protocol_before_authentication() -> None:
    peer_closed = asyncio.Event()

    async def handler(websocket) -> None:
        try:
            async for raw in websocket:
                request = json.loads(raw)
                await websocket.send(
                    json.dumps(
                        {
                            "schema": BRIDGE_SCHEMA,
                            "id": request["id"],
                            "type": "response",
                            "method": request["method"],
                            "result": {},
                        }
                    )
                )
        finally:
            peer_closed.set()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = LuaBridgeClient(
            LuaSettings(
                url=f"ws://127.0.0.1:{port}",
                token=SecretStr("secret" * 8),
                request_timeout_seconds=0.5,
            )
        )
        try:
            with pytest.raises(LuaBridgeError, match="subprotocol"):
                await client.connect()

            await asyncio.wait_for(peer_closed.wait(), timeout=1.0)
            assert client.status().connected is False
            assert client.status().authenticated is False
        finally:
            await client.close()
