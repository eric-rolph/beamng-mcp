"""Bounded JSON Streamable HTTP client for BeamNG's official in-game MCP.

Only reviewed typed requests are forwarded. No discovery-based tool registration,
arbitrary code, unrestricted files, persistent edits, or driving-policy bypass.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError

from ..config import NativeMCPSettings
from ..errors import BeamNGMCPError
from ..native_models import NativeModel, NativeRequest, NativeScreenshot, NativeSnapshot

REQUEST_ADAPTER: TypeAdapter[NativeRequest] = TypeAdapter(NativeRequest)
SUPPORTED_ACTIONS = frozenset(REQUEST_ADAPTER.json_schema()["discriminator"]["mapping"])
NATIVE_TOOL_NAMES = [
    "native_status",
    "native_inspect",
    "native_camera_control",
    "native_editor_control",
    "native_screenshot",
    "native_simulation_control",
    "native_display_control",
    "native_vehicle_control",
    "native_environment_control",
]


class NativeMCPError(BeamNGMCPError):
    """Native server unavailable or returned an invalid/error response."""


class NativeMCPClient:
    def __init__(self, settings: NativeMCPSettings) -> None:
        self.settings = settings
        self._lock = asyncio.Lock()
        self._sequence = 0
        self._initialized = False
        self.server_info: dict[str, Any] = {}
        self.protocol_version = "2025-11-25"

    async def _rpc(
        self, method: str, params: dict[str, Any], *, notification: bool = False
    ) -> dict[str, Any]:
        if not self.settings.enabled:
            raise NativeMCPError("Official MCP integration is disabled in native_mcp settings")
        self._sequence += 1
        request_id = self._sequence
        request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        if notification:
            del request["id"]
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                async with httpx.AsyncClient(
                    trust_env=False, follow_redirects=False, timeout=self.settings.timeout_seconds
                ) as client:
                    async with client.stream(
                        "POST",
                        self.settings.url,
                        json=request,
                        headers={
                            "Accept": "application/json, text/event-stream",
                            "MCP-Protocol-Version": self.protocol_version,
                        },
                    ) as response:
                        response.raise_for_status()
                        if notification:
                            if response.status_code != 202:
                                raise NativeMCPError(
                                    "Official MCP did not accept initialization notification"
                                )
                            return {}
                        if (
                            response.headers.get("content-type", "").split(";")[0]
                            != "application/json"
                        ):
                            raise NativeMCPError("Official BeamNG MCP must return application/json")
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            chunks.extend(chunk)
                            if len(chunks) > self.settings.max_response_bytes:
                                raise NativeMCPError(
                                    "Official MCP response exceeds configured byte limit"
                                )
            payload = json.loads(chunks)
        except (httpx.HTTPError, TimeoutError) as exc:
            raise NativeMCPError(
                f"Official BeamNG MCP unavailable at {self.settings.url}: {type(exc).__name__}. "
                "Enable MCP server in BeamNG Options > Advanced and check its port."
            ) from exc
        except (ValueError, UnicodeError) as exc:
            raise NativeMCPError("Official MCP returned invalid JSON") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("jsonrpc") != "2.0"
            or payload.get("id") != request_id
        ):
            raise NativeMCPError("Official MCP returned a mismatched JSON-RPC response")
        if "error" in payload:
            raise NativeMCPError(f"Official MCP protocol error: {str(payload['error'])[:1000]}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise NativeMCPError("Official MCP result must be an object")
        return result

    async def _initialize(self) -> None:
        if self._initialized:
            return
        result = await self._rpc(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "beamng-mcp-native-adapter", "version": "0.3.0"},
            },
        )
        info = result.get("serverInfo")
        if not isinstance(info, dict) or info.get("name") != "beamng-game":
            raise NativeMCPError("Endpoint does not identify as the official beamng-game server")
        version = result.get("protocolVersion")
        if version not in {"2025-03-26", "2025-06-18", "2025-11-25"}:
            raise NativeMCPError("Official MCP negotiated an unsupported protocol version")
        self.server_info = info
        self.protocol_version = version
        await self._rpc("notifications/initialized", {}, notification=True)
        self._initialized = True

    async def status(self) -> dict[str, Any]:
        async with self._lock:
            await self._initialize()
            result = await self._rpc("tools/list", {})
            tools = result.get("tools")
            if not isinstance(tools, list) or any(
                not isinstance(t, dict) or not isinstance(t.get("name"), str) for t in tools
            ):
                raise NativeMCPError("Official MCP returned an invalid tool catalog")
            names = {t["name"] for t in tools}
            return {
                "connected": True,
                "url": self.settings.url,
                "server": self.server_info,
                "protocol_version": self.protocol_version,
                "official_tool_count": len(names),
                "supported_actions": sorted(names & SUPPORTED_ACTIONS),
                "missing_upstream_actions": sorted(SUPPORTED_ACTIONS - names),
                "not_forwarded": sorted(names - SUPPORTED_ACTIONS),
                "note": (
                    "Native tools cover running-game inspection, views, simulation, limited "
                    "vehicle operations and lighting. Other tools may require BeamNGpy or the "
                    "custom Lua bridge. Native tools attach to the running game; they do not "
                    "launch it. Code execution and unrestricted filesystem/editor mutations "
                    "are not forwarded."
                ),
            }

    async def call(self, request: NativeModel) -> list[dict[str, Any]]:
        # Validate again at the domain boundary, even for model_construct() callers.
        try:
            checked = REQUEST_ADAPTER.validate_python(
                request.model_dump(by_alias=True, exclude_none=True)
            )
        except ValidationError as exc:
            raise NativeMCPError("Invalid or unsupported official MCP request") from exc
        arguments = checked.model_dump(by_alias=True, exclude_none=True, exclude={"action"})
        async with self._lock:
            await self._initialize()
            if checked.action in {"set_position", "recover_vehicle", "spawn"}:
                # Upstream resolves arbitrary scene IDs without checking their class.
                # Require membership in the engine vehicle list before a vehicle mutation.
                vehicles_result = await self._rpc(
                    "tools/call", {"name": "get_vehicles", "arguments": {}}
                )
                vehicles_content = self._validate_content(vehicles_result, "get_vehicles")
                try:
                    vehicles = json.loads("\n".join(i["text"] for i in vehicles_content))
                except ValueError as exc:
                    raise NativeMCPError("Invalid vehicle list; mutation refused") from exc
                if not isinstance(vehicles, list) or any(
                    not isinstance(v, dict) or type(v.get("id")) is not int for v in vehicles
                ):
                    raise NativeMCPError("Invalid vehicle list; mutation refused")
                if checked.action == "spawn":
                    if len(vehicles) >= 32:
                        raise NativeMCPError("Native spawning is limited to 32 live vehicles")
                elif arguments["id"] not in {v["id"] for v in vehicles}:
                    raise NativeMCPError("Target is not a currently spawned vehicle")
            result = await self._rpc("tools/call", {"name": checked.action, "arguments": arguments})
        return self._validate_content(result, checked.action)

    async def health(self) -> dict[str, Any]:
        """Small read-only connection check; does not certify every tool or legacy backend."""
        started = time.monotonic()
        report: dict[str, Any] = {"ready": False, "checks": {}, "scope": "native read-only"}
        try:
            report["catalog"] = await self.status()
            for action in ("get_status", "get_simulation_state", "get_camera_state"):
                result = await self.inspect(NativeSnapshot(action=action))
                if not isinstance(result["data"], dict):
                    raise NativeMCPError(f"{action} did not return a state object")
                report["checks"][action] = result["data"]
            report["ready"] = not report["catalog"]["missing_upstream_actions"]
            if not report["ready"]:
                report["error"] = "Official server is missing supported actions"
        except NativeMCPError as exc:
            report["error"] = str(exc)
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        return report

    @staticmethod
    def _validate_content(result: dict[str, Any], action: str) -> list[dict[str, Any]]:
        content = result.get("content")
        if not isinstance(content, list) or not content:
            raise NativeMCPError("Official MCP returned no content")
        for item in content:
            if not isinstance(item, dict):
                raise NativeMCPError("Official MCP content must be an object")
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                continue
            if item.get("type") == "image" and action == "screenshot_image":
                if item.get("mimeType") not in {"image/jpeg", "image/png"} or not isinstance(
                    item.get("data"), str
                ):
                    raise NativeMCPError("Official MCP returned an invalid image")
                try:
                    base64.b64decode(item["data"], validate=True)
                except ValueError as exc:
                    raise NativeMCPError("Official MCP image is not valid base64") from exc
                continue
            raise NativeMCPError("Official MCP returned an unsupported content type")
        if result.get("isError") is not False:
            message = " ".join(i.get("text", "") for i in content)
            raise NativeMCPError(f"Official MCP tool failed: {message[:2000]}")
        return content

    async def inspect(self, request: NativeModel) -> dict[str, Any]:
        content = await self.call(request)
        text = "\n".join(item["text"] for item in content)
        try:
            data = json.loads(text)
        except ValueError:
            data = text
        return {"source": "beamng-game", "action": request.action, "data": data}  # type: ignore[attr-defined]

    async def screenshot(self, scale: float) -> list[dict[str, Any]]:
        return await self.call(NativeScreenshot(scale=scale))
