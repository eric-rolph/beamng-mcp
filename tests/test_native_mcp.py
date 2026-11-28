from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import ValidationError

from beamng_mcp.adapters.native_mcp import (
    REQUEST_ADAPTER,
    SUPPORTED_ACTIONS,
    NativeMCPClient,
    NativeMCPError,
)
from beamng_mcp.config import NativeMCPSettings, Settings
from beamng_mcp.mcp_adapter import create_mcp_server
from beamng_mcp.native_models import NativeSnapshot


def mock_server(monkeypatch: pytest.MonkeyPatch, handler: Any) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []

    def route(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if body["method"] == "initialize":
            result = {
                "serverInfo": {"name": "beamng-game", "version": "1.0.0"},
                "protocolVersion": "2025-11-25",
            }
        elif body["method"] == "notifications/initialized":
            return httpx.Response(202)
        else:
            result = handler(body)
            if isinstance(result, httpx.Response):
                return result
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    original = httpx.AsyncClient

    def client(**kwargs: Any) -> httpx.AsyncClient:
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        return original(transport=httpx.MockTransport(route), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return requests


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:29292/mcp",
        "http://localhost:29292/mcp",
        "https://127.0.0.1:29292/mcp",
        "http://127.0.0.1:29292/mcp?",
        "http://127.0.0.1:29292/mcp#",
        "http://user@127.0.0.1:29292/mcp",
        " http://127.0.0.1:29292/mcp",
        "http://127.0.0.1:29292/other",
        "http://127.0.0.1:99999/mcp",
        "http://127.0.0.2:29292/mcp",
    ],
)
def test_native_endpoint_rejects_remote_and_ambiguous_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        NativeMCPSettings(url=url)


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "run_lua", "code": "anything"},
        {"action": "write_file", "path": "anything"},
        {"action": "get_status", "code": "anything"},
        {"action": "get_status", "arguments": {"name": "run_lua"}},
        {
            "action": "set_free_camera",
            "pos": {"x": float("nan"), "y": 0, "z": 0},
            "rot": {"x": 0, "y": 0, "z": 0, "w": 1},
        },
        {"action": "get_object", "id": 1, "name": "other"},
        {"action": "get_object"},
        {"action": "get_navgraph", "maxNodes": 2001},
        {"action": "screenshot_image", "scale": 100},
        {"action": "debug_clear"},
        {"action": "debug_clear", "id": "someone_else"},
        {"action": "debug_draw", "id": "beamng_mcp_debug_32", "pos": {"x": 0, "y": 0, "z": 0}},
        {
            "action": "debug_draw",
            "id": "beamng_mcp_debug_1",
            "kind": "text",
            "pos": {"x": 0, "y": 0, "z": 0},
        },
        {
            "action": "debug_draw",
            "id": "beamng_mcp_debug_1",
            "ttl": 0,
            "pos": {"x": 0, "y": 0, "z": 0},
        },
        {"action": "toggle_ui"},
        {"action": "spawn", "model": "pickup", "add": False},
        {"action": "spawn", "model": "../pickup"},
        {"action": "spawn", "model": "pickup", "config": "/vehicles/pickup/custom.pc"},
        {"action": "set_position", "pos": {"x": 1, "y": 2, "z": 3}},
        {"action": "recover_vehicle", "id": 0},
        {"action": "set_time_of_day", "time": 1.01},
        {"action": "set_time_of_day", "time": 0.5, "dayLength": 0},
        {"action": "set_time_of_day", "time": 0.5, "celestialProfile": "arbitrary/path"},
        {"action": "raycast", "from": {"x": 0, "y": 0, "z": 0}, "to": {"x": 0, "y": 0, "z": 0}},
    ],
)
def test_native_requests_reject_unsafe_unbounded_or_ambiguous_input(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        REQUEST_ADAPTER.validate_python(payload)


async def test_native_client_handshake_aliases_and_unknown_catalog_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(body: dict[str, Any]) -> dict[str, Any]:
        if body["method"] == "tools/list":
            return {"tools": [{"name": "get_status"}, {"name": "run_lua"}, {"name": "future_tool"}]}
        assert body["params"] == {
            "name": "raycast",
            "arguments": {
                "from": {"x": 0.0, "y": 0.0, "z": 10.0},
                "to": {"x": 0.0, "y": 0.0, "z": 0.0},
                "renderGeometry": False,
                "includeTerrain": True,
            },
        }
        return {"isError": False, "content": [{"type": "text", "text": '{"distance": 10}'}]}

    requests = mock_server(monkeypatch, handler)
    client = NativeMCPClient(NativeMCPSettings())
    status = await client.status()
    assert status["supported_actions"] == ["get_status"]
    assert status["not_forwarded"] == ["future_tool", "run_lua"]
    request = REQUEST_ADAPTER.validate_python(
        {"action": "raycast", "from": {"x": 0, "y": 0, "z": 10}, "to": {"x": 0, "y": 0, "z": 0}}
    )
    assert (await client.inspect(request))["data"] == {"distance": 10}
    assert [r["method"] for r in requests] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
    ]
    assert "id" not in requests[1]


@pytest.mark.parametrize(
    "response,match",
    [
        (httpx.Response(302, headers={"Location": "http://example.com"}), "unavailable"),
        (
            httpx.Response(200, text="data: {}", headers={"Content-Type": "text/event-stream"}),
            "application/json",
        ),
        (httpx.Response(200, json={"jsonrpc": "2.0", "id": 999, "result": {}}), "mismatched"),
        (
            httpx.Response(200, text="{broken", headers={"Content-Type": "application/json"}),
            "invalid JSON",
        ),
        (
            {"isError": True, "content": [{"type": "text", "text": "failure"}]},
            "tool failed: failure",
        ),
        ({"content": [{"type": "text", "text": "missing success flag"}]}, "tool failed"),
        (
            {"isError": False, "content": [{"type": "resource_link", "uri": "file:///secret"}]},
            "unsupported content",
        ),
        (
            {
                "isError": False,
                "content": [{"type": "image", "mimeType": "image/jpeg", "data": "AA=="}],
            },
            "unsupported content",
        ),
        ({"isError": False, "content": []}, "no content"),
    ],
)
async def test_native_client_fails_closed(
    monkeypatch: pytest.MonkeyPatch, response: Any, match: str
) -> None:
    requests = mock_server(monkeypatch, lambda _: response)
    client = NativeMCPClient(NativeMCPSettings())
    with pytest.raises(NativeMCPError, match=match):
        await client.inspect(NativeSnapshot(action="get_status"))
    assert sum(r["method"] == "tools/call" for r in requests) == 1


async def test_native_response_limit_and_disabled_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = mock_server(
        monkeypatch, lambda _: {"isError": False, "content": [{"type": "text", "text": "x" * 5000}]}
    )
    client = NativeMCPClient(NativeMCPSettings(max_response_bytes=4096))
    with pytest.raises(NativeMCPError, match="byte limit"):
        await client.inspect(NativeSnapshot(action="get_status"))
    count = len(requests)
    disabled = NativeMCPClient(NativeMCPSettings(enabled=False))
    with pytest.raises(NativeMCPError, match="disabled"):
        await disabled.status()
    assert len(requests) == count


async def test_native_tools_over_official_client_and_image_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    encoded = base64.b64encode(b"test-image-payload").decode()

    def handler(body: dict[str, Any]) -> dict[str, Any]:
        name = body["params"]["name"]
        if name == "screenshot_image":
            return {
                "isError": False,
                "content": [{"type": "image", "mimeType": "image/jpeg", "data": encoded}],
            }
        return {"isError": False, "content": [{"type": "text", "text": '{"physicsRunning": true}'}]}

    requests = mock_server(monkeypatch, handler)
    mcp, runtime = create_mcp_server(Settings(workspace={"root": tmp_path / "workspace"}))
    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.call_tool(
            "native_inspect", {"request": {"action": "get_simulation_state"}}
        )
        assert not result.isError
        assert result.structuredContent is not None
        assert result.structuredContent["data"]["physicsRunning"] is True
        screenshot = await session.call_tool("native_screenshot", {"scale": 0.2})
        assert not screenshot.isError
        assert screenshot.content[0].type == "image"
        assert screenshot.content[0].data == encoded
        before = len(requests)
        invalid = await session.call_tool(
            "native_inspect", {"request": {"action": "run_lua", "code": "return 1"}}
        )
        assert invalid.isError
        assert len(requests) == before
    await runtime.shutdown()


@pytest.mark.parametrize(
    "tool,payload",
    [
        ("native_vehicle_control", {"action": "spawn", "model": "pickup"}),
        (
            "native_vehicle_control",
            {"action": "set_position", "id": 7, "pos": {"x": 1, "y": 2, "z": 3}},
        ),
        ("native_vehicle_control", {"action": "recover_vehicle", "id": 7}),
        ("native_environment_control", {"action": "set_time_of_day", "time": 0.5}),
    ],
)
async def test_native_vehicle_and_lighting_interlocks_and_routing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tool: str, payload: dict[str, Any]
) -> None:
    def handler(body: dict[str, Any]) -> dict[str, Any]:
        data = '[{"id":7}]' if body["params"]["name"] == "get_vehicles" else '"done"'
        return {"isError": False, "content": [{"type": "text", "text": data}]}

    payloads = mock_server(monkeypatch, handler)
    mcp, runtime = create_mcp_server(Settings(workspace={"root": tmp_path}))
    async with create_connected_server_and_client_session(mcp) as session:
        runtime._autonomy_start_pending = True
        blocked = await session.call_tool(tool, {"request": payload})
        assert blocked.isError
        assert not payloads
        runtime._autonomy_start_pending = False
        result = await session.call_tool(tool, {"request": payload})
        assert not result.isError
        assert payloads[-1]["params"]["name"] == payload["action"]
        if payload["action"] == "spawn":
            assert payloads[-1]["params"]["arguments"] == {"model": "pickup", "add": True}
        elif "id" in payload:
            assert payloads[-1]["params"]["arguments"]["id"] == 7
    await runtime.shutdown()


@pytest.mark.parametrize("vehicles", [{}, [{"id": "7"}], [{"id": 8}]])
async def test_vehicle_mutation_refuses_unverified_target(
    monkeypatch: pytest.MonkeyPatch, vehicles: Any
) -> None:
    requests = mock_server(
        monkeypatch,
        lambda _: {"isError": False, "content": [{"type": "text", "text": json.dumps(vehicles)}]},
    )
    client = NativeMCPClient(NativeMCPSettings())
    with pytest.raises(NativeMCPError):
        await client.call(REQUEST_ADAPTER.validate_python({"action": "recover_vehicle", "id": 7}))
    assert [r["params"]["name"] for r in requests if r["method"] == "tools/call"] == [
        "get_vehicles"
    ]


async def test_native_spawn_cap_and_preserved_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = mock_server(
        monkeypatch,
        lambda _: {
            "isError": False,
            "content": [{"type": "text", "text": json.dumps([{"id": i} for i in range(32)])}],
        },
    )
    client = NativeMCPClient(NativeMCPSettings())
    with pytest.raises(NativeMCPError, match="32 live vehicles"):
        await client.call(REQUEST_ADAPTER.validate_python({"action": "spawn", "model": "pickup"}))
    assert requests[-1]["params"]["name"] == "get_vehicles"
    await client.call(REQUEST_ADAPTER.validate_python({"action": "get_instability"}))
    assert requests[-1]["params"] == {"name": "get_instability", "arguments": {"clear": False}}


@pytest.mark.parametrize("missing", [True, False])
async def test_native_health_reports_missing_actions_and_read_only_scope(
    monkeypatch: pytest.MonkeyPatch, missing: bool
) -> None:
    def handler(body: dict[str, Any]) -> dict[str, Any]:
        if body["method"] == "tools/list":
            names = SUPPORTED_ACTIONS - {"spawn"} if missing else SUPPORTED_ACTIONS
            return {"tools": [{"name": name} for name in sorted(names)]}
        return {"isError": False, "content": [{"type": "text", "text": "{}"}]}

    requests = mock_server(monkeypatch, handler)
    report = await NativeMCPClient(NativeMCPSettings()).health()
    assert report["ready"] is not missing
    assert report["scope"] == "native read-only"
    assert [r["params"]["name"] for r in requests if r["method"] == "tools/call"] == [
        "get_status",
        "get_simulation_state",
        "get_camera_state",
    ]


async def test_native_health_reports_connection_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_server(monkeypatch, lambda _: httpx.Response(503))
    report = await NativeMCPClient(NativeMCPSettings()).health()
    assert not report["ready"]
    assert "unavailable" in report["error"]


async def test_native_simulation_respects_autonomy_interlock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requests = mock_server(
        monkeypatch,
        lambda _: {"isError": False, "content": [{"type": "text", "text": "physics paused"}]},
    )
    mcp, runtime = create_mcp_server(Settings(workspace={"root": tmp_path / "workspace"}))
    async with create_connected_server_and_client_session(mcp) as session:
        runtime._autonomy_start_pending = True
        blocked = await session.call_tool(
            "native_simulation_control", {"request": {"action": "pause_physics"}}
        )
        assert blocked.isError
        assert requests == []
        runtime._autonomy_start_pending = False
        result = await session.call_tool(
            "native_simulation_control", {"request": {"action": "pause_physics"}}
        )
        assert not result.isError
        assert requests[-1]["params"] == {"name": "pause_physics", "arguments": {}}
        before = len(requests)
        invalid = await session.call_tool(
            "native_simulation_control", {"request": {"action": "step_physics", "steps": 1001}}
        )
        assert invalid.isError
        assert len(requests) == before
    await runtime.shutdown()
