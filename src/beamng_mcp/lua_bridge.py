import asyncio
import json
import secrets
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve


class LuaBridge:
    """Authenticated, localhost-only JSON-RPC-like WebSocket bridge."""

    def __init__(self, host: str, port: int, shared_secret: str) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Lua bridge must bind to loopback")
        self.host, self.port, self.shared_secret = host, port, shared_secret
        self._server: Server | None = None
        self._client: ServerConnection | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    @property
    def connected(self) -> bool:
        return self._client is not None

    async def start(self) -> None:
        self._server = await serve(self._handler, self.host, self.port, max_size=2**20)

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def request(
        self, operation: str, arguments: dict[str, Any], deadline_seconds: float = 5
    ) -> dict[str, Any]:
        if not self._client:
            raise RuntimeError("BeamNG Lua extension is not connected")
        request_id = secrets.token_hex(8)
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._client.send(json.dumps({"id": request_id, "op": operation, "args": arguments}))
        try:
            return await asyncio.wait_for(future, deadline_seconds)
        finally:
            self._pending.pop(request_id, None)

    async def _handler(self, websocket: ServerConnection) -> None:
        auth = json.loads(await asyncio.wait_for(websocket.recv(), 3))
        if not secrets.compare_digest(str(auth.get("secret", "")), self.shared_secret):
            await websocket.close(code=1008, reason="authentication failed")
            return
        self._client = websocket
        await websocket.send(json.dumps({"type": "ready"}))
        try:
            async for raw in websocket:
                message = json.loads(raw)
                request_id = message.get("id")
                if request_id in self._pending and not self._pending[request_id].done():
                    self._pending[request_id].set_result(message)
        finally:
            if self._client is websocket:
                self._client = None
