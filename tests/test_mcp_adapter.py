from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import SecretStr

from beamng_mcp.config import Settings
from beamng_mcp.mcp_adapter import BearerAuthMiddleware, create_mcp_server


@pytest.mark.asyncio
async def test_mcp_exposes_curated_typed_surface(tmp_path: Path) -> None:
    settings = Settings(workspace={"root": tmp_path / "workspace"})
    mcp, runtime = create_mcp_server(settings)
    tools = await mcp.list_tools()
    names = {tool.name for tool in tools}
    assert len(tools) == 47
    assert {"simulator_connect", "mod_validate", "autonomy_start", "emergency_stop"} <= names
    assert not any("eval" in name or "shell" in name for name in names)
    delete = next(tool for tool in tools if tool.name == "map_object_delete")
    save = next(tool for tool in tools if tool.name == "map_save")
    create = next(tool for tool in tools if tool.name == "scenario_create")
    status = next(tool for tool in tools if tool.name == "simulator_status")
    assert delete.annotations is not None and delete.annotations.destructiveHint is True
    assert status.annotations is not None and status.annotations.readOnlyHint is True
    assert delete.inputSchema["properties"]["confirm"]["default"] is False
    assert create.inputSchema["properties"]["overwrite"]["default"] is False
    assert create.inputSchema["properties"]["confirm_overwrite"]["default"] is False
    assert "level" in save.inputSchema["required"]
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_official_in_memory_client_can_call_structured_tool(tmp_path: Path) -> None:
    settings = Settings(workspace={"root": tmp_path / "workspace"})
    mcp, runtime = create_mcp_server(settings)
    async with create_connected_server_and_client_session(
        mcp, read_timeout_seconds=timedelta(seconds=5)
    ) as session:
        result = await session.call_tool("capabilities_get", {})
        assert result.isError is False
        assert result.structuredContent is not None
        assert result.structuredContent["server_version"] == "0.1.0"
        assert result.structuredContent["mode"] == "offline"
    # Lifespan owns shutdown; a second shutdown remains safe.
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_direct_mod_install_uses_autonomy_transition_interlock(tmp_path: Path) -> None:
    settings = Settings(workspace={"root": tmp_path / "workspace"})
    mcp, runtime = create_mcp_server(settings)
    async with create_connected_server_and_client_session(mcp) as session:
        runtime._autonomy_start_pending = True
        try:
            result = await session.call_tool(
                "mod_install",
                {"mod_name": "sample", "confirm": True, "overwrite": False},
            )
        finally:
            runtime._autonomy_start_pending = False

        assert result.isError is True
        assert "while autonomy is starting" in str(result.content)
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_standalone_tool_cannot_start_unleased_native_ai(tmp_path: Path) -> None:
    settings = Settings(workspace={"root": tmp_path / "workspace"})
    mcp, runtime = create_mcp_server(settings)
    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.call_tool(
            "vehicle_ai_configure",
            {"config": {"vehicle_id": "ego", "mode": "traffic"}},
        )
        assert result.isError is True
        assert "require autonomy_start" in str(result.content)
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_http_bearer_middleware_rejects_missing_token() -> None:
    calls: list[str] = []

    async def app(scope, receive, send):
        calls.append("called")

    middleware = BearerAuthMiddleware(app, "a" * 32)
    messages: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await middleware(
        {"type": "http", "method": "POST", "path": "/mcp", "headers": []},
        receive,
        send,
    )
    assert calls == []
    assert messages[0]["status"] == 401


@pytest.mark.asyncio
async def test_http_bearer_middleware_accepts_exact_token() -> None:
    calls: list[str] = []

    async def app(scope, receive, send):
        calls.append("called")

    middleware = BearerAuthMiddleware(app, "a" * 32)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [(b"authorization", b"Bearer " + b"a" * 32)],
        },
        receive,
        send,
    )
    assert calls == ["called"]


def test_http_bearer_middleware_requires_high_entropy_length() -> None:
    with pytest.raises(ValueError, match="32"):
        BearerAuthMiddleware(object(), SecretStr("short").get_secret_value())
