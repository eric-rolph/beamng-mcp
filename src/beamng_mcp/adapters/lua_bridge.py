"""Private, authenticated JSON-RPC-like client for the GELua WebSocket bridge."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed
from websockets.typing import Subprotocol

from ..config import LuaSettings
from ..errors import ConfigurationError, LuaBridgeError
from ..models import BridgeStatus

BRIDGE_SCHEMA = 1
BRIDGE_SUBPROTOCOL = "beamng-mcp-v1"
ALLOWED_METHODS = frozenset(
    {
        "ping",
        "capabilities",
        "telemetry.snapshot",
        "world.list_objects",
        "world.get_object",
        "world.create_object",
        "world.update_object",
        "world.delete_object",
        "world.save_level",
        "safety.lease_arm",
        "safety.lease_renew",
        "safety.lease_disarm",
        "extension.reload",
        "emergency_stop",
    }
)


class LuaBridgeClient:
    """Maintain one loopback bridge connection with correlated request futures."""

    def __init__(self, settings: LuaSettings) -> None:
        self.settings = settings
        self._ws: ClientConnection | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._pending: dict[str, tuple[str, asyncio.Future[dict[str, Any]]]] = {}
        self._connect_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._events: deque[dict[str, Any]] = deque(maxlen=256)
        self._latest_telemetry: dict[str, Any] | None = None
        self._authenticated = False
        self._bridge_version: str | None = None
        self._game_version: str | None = None
        self._last_message_at: datetime | None = None
        self._last_error: str | None = None
        self._latency_ms: float | None = None
        self._native_preamble_received = False

    @property
    def connected(self) -> bool:
        return (
            self._ws is not None and self._reader_task is not None and not self._reader_task.done()
        )

    async def connect(self) -> None:
        token = self.settings.token
        if token is None or not token.get_secret_value():
            raise ConfigurationError(
                "Lua bridge token is missing; run `beamng-mcp install-lua` or configure "
                "BEAMNG_MCP_LUA_TOKEN"
            )
        async with self._connect_lock:
            if self.connected and self._authenticated:
                return
            try:
                await self._close_socket()
                self._ws = await connect(
                    self.settings.url,
                    subprotocols=[Subprotocol(BRIDGE_SUBPROTOCOL)],
                    open_timeout=self.settings.request_timeout_seconds,
                    close_timeout=2,
                    max_size=self.settings.max_message_bytes,
                    max_queue=32,
                    ping_interval=10,
                    ping_timeout=5,
                    compression=None,
                )
                if self._ws.subprotocol != BRIDGE_SUBPROTOCOL:
                    raise LuaBridgeError(
                        "Lua bridge did not negotiate the required "
                        f"{BRIDGE_SUBPROTOCOL!r} subprotocol"
                    )
                ws = self._ws
                self._reader_task = asyncio.create_task(
                    self._reader(ws), name="beamng-lua-bridge-reader"
                )
                result = await self._call_connected("capabilities", {})
                self._authenticated = True
                self._bridge_version = _string_or_none(result.get("bridge_version"))
                self._game_version = _string_or_none(result.get("game_version"))
                self._heartbeat_task = asyncio.create_task(
                    self._heartbeat_loop(ws), name="beamng-lua-bridge-heartbeat"
                )
                self._last_error = None
            except asyncio.CancelledError:
                await self._close_socket()
                raise
            except Exception as exc:
                await self._close_socket()
                self._last_error = f"{type(exc).__name__}: {exc}"
                if isinstance(exc, (ConfigurationError, LuaBridgeError)):
                    raise
                raise LuaBridgeError(f"Cannot connect to {self.settings.url}: {exc}") from exc

    async def close(self) -> None:
        async with self._connect_lock:
            await self._close_socket()

    async def _close_socket(self, *, expected_ws: ClientConnection | None = None) -> None:
        if expected_ws is not None and self._ws is not expected_ws:
            return
        heartbeat = self._heartbeat_task
        self._heartbeat_task = None
        reader = self._reader_task
        self._reader_task = None
        ws = self._ws
        self._ws = None
        pending = tuple(self._pending.values())
        self._pending.clear()
        self._authenticated = False
        self._native_preamble_received = False

        for _, future in pending:
            if not future.done():
                future.set_exception(LuaBridgeError("Lua bridge connection closed"))
        if heartbeat is not None and heartbeat is not asyncio.current_task():
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
        if reader is not None and reader is not asyncio.current_task():
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()

    async def _heartbeat_loop(self, ws: ClientConnection) -> None:
        try:
            while True:
                await asyncio.sleep(5.0)
                if self._ws is not ws:
                    return
                await self._call_connected("ping", {})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._ws is not ws:
                return
            self._last_error = f"heartbeat failed: {type(exc).__name__}: {exc}"
            self._authenticated = False
            await self._close_socket(expected_ws=ws)

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if method not in ALLOWED_METHODS:
            raise LuaBridgeError(f"Lua bridge method {method!r} is not allowlisted")
        if not self.connected or not self._authenticated:
            await self.connect()
        ws = self._ws
        try:
            return await self._call_connected(method, params or {})
        except (ConnectionClosed, OSError) as exc:
            if self._ws is ws:
                self._last_error = f"{type(exc).__name__}: {exc}"
            await self._close_socket(expected_ws=ws)
            raise LuaBridgeError(f"Lua bridge disconnected during {method}") from exc

    async def _call_connected(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        ws = self._ws
        if ws is None:
            raise LuaBridgeError("Lua bridge socket is not connected")
        request_id = uuid.uuid4().hex
        token = self.settings.token
        if token is None:
            raise ConfigurationError("Lua bridge token is not configured")
        envelope = {
            "schema": BRIDGE_SCHEMA,
            "id": request_id,
            "type": "request",
            "method": method,
            "params": params,
            "token": token.get_secret_value(),
        }
        encoded = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > self.settings.max_message_bytes:
            raise LuaBridgeError("Lua bridge request exceeds configured max_message_bytes")

        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (method, future)
        started = time.perf_counter()
        try:
            async with self._send_lock:
                await ws.send(encoded)
            async with asyncio.timeout(self.settings.request_timeout_seconds):
                response = await future
        except TimeoutError as exc:
            raise LuaBridgeError(f"Lua bridge request {method!r} timed out") from exc
        finally:
            self._pending.pop(request_id, None)

        self._latency_ms = (time.perf_counter() - started) * 1000.0
        if response.get("error"):
            error = response["error"]
            if isinstance(error, dict):
                message = error.get("message") or error.get("code") or str(error)
            else:
                message = str(error)
            raise LuaBridgeError(f"Lua bridge {method} failed: {message}")
        result = response.get("result", {})
        return result if isinstance(result, dict) else {"result": result}

    async def _reader(self, ws: ClientConnection) -> None:
        try:
            async for raw in ws:
                if not isinstance(raw, str):
                    continue
                if len(raw.encode("utf-8")) > self.settings.max_message_bytes:
                    raise LuaBridgeError("Lua bridge response exceeded max_message_bytes")
                if self._consume_native_preamble(raw):
                    continue
                message = json.loads(raw)
                if not isinstance(message, dict) or message.get("schema") != BRIDGE_SCHEMA:
                    continue
                self._last_message_at = datetime.now(UTC)
                if message.get("type") == "response" and isinstance(message.get("id"), str):
                    pending = self._pending.get(message["id"])
                    if pending is None:
                        continue
                    expected_method, future = pending
                    if message.get("method") != expected_method:
                        error = LuaBridgeError(
                            "Lua bridge response method mismatch: "
                            f"expected {expected_method!r}, received {message.get('method')!r}"
                        )
                        if not future.done():
                            future.set_exception(error)
                        raise error
                    if not future.done():
                        future.set_result(message)
                elif message.get("type") == "event":
                    self._events.append(message)
                    if message.get("method") == "telemetry.snapshot":
                        params = message.get("params")
                        if isinstance(params, dict):
                            self._latest_telemetry = params
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._ws is ws:
                self._last_error = f"{type(exc).__name__}: {exc}"
        finally:
            if self._reader_task is asyncio.current_task():
                await self._close_socket(expected_ws=ws)

    def _consume_native_preamble(self, raw: str) -> bool:
        """Validate BeamNG's one-time native ``I#`` WebSocket information frame."""

        if not raw.startswith("I#"):
            return False
        if self._native_preamble_received:
            raise LuaBridgeError("Lua bridge sent more than one native product-info preamble")
        try:
            payload = json.loads(raw[2:])
        except json.JSONDecodeError as exc:
            raise LuaBridgeError("Lua bridge sent an invalid native product-info preamble") from exc
        if not isinstance(payload, dict) or payload.get("product") not in {"drive", "tech"}:
            raise LuaBridgeError("Lua bridge sent an invalid native product-info preamble")
        version = payload.get("version")
        if not isinstance(version, str) or not 1 <= len(version) <= 64:
            raise LuaBridgeError("Lua bridge native product-info preamble has no valid version")
        self._native_preamble_received = True
        self._game_version = version
        return True

    async def probe(self) -> BridgeStatus:
        if not self.connected:
            try:
                await self.connect()
            except (ConfigurationError, LuaBridgeError) as exc:
                self._last_error = str(exc)
        if self.connected:
            try:
                await self.call("ping")
            except LuaBridgeError as exc:
                self._last_error = str(exc)
        return self.status()

    def status(self) -> BridgeStatus:
        return BridgeStatus(
            connected=self.connected,
            authenticated=self._authenticated,
            url=self.settings.url,
            bridge_version=self._bridge_version,
            game_version=self._game_version,
            latency_ms=self._latency_ms,
            last_message_at=self._last_message_at,
            last_error=self._last_error,
        )

    @property
    def latest_telemetry(self) -> dict[str, Any] | None:
        return dict(self._latest_telemetry) if self._latest_telemetry else None

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        if not 1 <= limit <= 256:
            raise ValueError("event limit must be between 1 and 256")
        return list(self._events)[-limit:]


def _string_or_none(value: Any) -> str | None:
    return None if value is None else str(value)
