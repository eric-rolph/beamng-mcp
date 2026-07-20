from __future__ import annotations

import asyncio
import json
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
    assert len(tools) == 57
    assert {
        "simulator_connect",
        "mod_validate",
        "softbody_handoff_create",
        "softbody_mod_build",
        "softbody_mod_validate",
        "map_trigger_create",
        "map_trigger_get",
        "map_trigger_update",
        "map_trigger_list",
        "map_trigger_events",
        "map_trigger_delete",
        "autonomy_start",
        "emergency_stop",
    } <= names
    assert not any("eval" in name or "shell" in name for name in names)
    delete = next(tool for tool in tools if tool.name == "map_object_delete")
    save = next(tool for tool in tools if tool.name == "map_save")
    create = next(tool for tool in tools if tool.name == "scenario_create")
    spawn = next(tool for tool in tools if tool.name == "vehicle_spawn")
    status = next(tool for tool in tools if tool.name == "simulator_status")
    mod_test = next(tool for tool in tools if tool.name == "mod_test_start")
    emergency_stop = next(tool for tool in tools if tool.name == "emergency_stop")
    assert delete.annotations is not None and delete.annotations.destructiveHint is True
    assert status.annotations is not None and status.annotations.readOnlyHint is True
    assert mod_test.annotations is not None and mod_test.annotations.destructiveHint is True
    assert emergency_stop.annotations is not None
    assert emergency_stop.annotations.idempotentHint is True
    assert delete.inputSchema["properties"]["confirm"]["default"] is False
    assert create.inputSchema["properties"]["overwrite"]["default"] is False
    assert create.inputSchema["properties"]["confirm_overwrite"]["default"] is False
    scenario_vehicle_schema = create.inputSchema["$defs"]["ScenarioVehiclePlacement"]
    scenario_vehicle_cling = scenario_vehicle_schema["properties"]["cling"]
    assert scenario_vehicle_cling["default"] is False
    assert scenario_vehicle_cling["const"] is False
    assert "position" in scenario_vehicle_schema["required"]
    runtime_vehicle_schema = spawn.inputSchema["$defs"]["VehicleSpawn"]
    assert "position" in runtime_vehicle_schema["required"]
    assert runtime_vehicle_schema["properties"]["cling"]["default"] is False
    assert "level" in save.inputSchema["required"]
    trigger_create = next(tool for tool in tools if tool.name == "map_trigger_create")
    trigger_update = next(tool for tool in tools if tool.name == "map_trigger_update")
    trigger_events = next(tool for tool in tools if tool.name == "map_trigger_events")
    trigger_delete = next(tool for tool in tools if tool.name == "map_trigger_delete")
    assert trigger_create.annotations is not None
    assert trigger_create.annotations.openWorldHint is False
    create_request_schema = trigger_create.inputSchema["$defs"]["MapTriggerCreate"]
    assert set(create_request_schema["required"]) == {"position", "scale"}
    assert trigger_update.annotations is not None
    assert trigger_update.annotations.destructiveHint is True
    assert trigger_events.annotations is not None
    assert trigger_events.annotations.readOnlyHint is True
    assert trigger_events.inputSchema["properties"]["after_sequence"]["default"] == 0
    assert trigger_events.inputSchema["properties"]["limit"]["default"] == 50
    assert {
        "handle",
        "events",
        "after_sequence",
        "next_sequence",
        "latest_sequence",
        "current_count",
        "truncated",
        "has_more",
        "limit",
    } <= set(trigger_events.outputSchema["required"])
    assert trigger_delete.annotations is not None
    assert trigger_delete.annotations.destructiveHint is True
    assert trigger_delete.inputSchema["properties"]["confirm"]["default"] is False
    softbody_build = next(tool for tool in tools if tool.name == "softbody_mod_build")
    assert softbody_build.annotations is not None
    assert softbody_build.annotations.destructiveHint is True
    assert "request" in softbody_build.inputSchema["required"]
    resources = await mcp.list_resources()
    prompts = await mcp.list_prompts()
    assert len(resources) == 4
    assert len(prompts) == 4
    assert any(str(resource.uri) == "beamng://authoring/softbody/v1" for resource in resources)
    assert any(prompt.name == "build_softbody_mod" for prompt in prompts)
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
        assert result.structuredContent["server_version"] == "0.3.0"
        assert result.structuredContent["mode"] == "offline"
        assert any(
            "Scenario.add_vehicle" in limitation and "model-origin clearance" in limitation
            for limitation in result.structuredContent["limitations"]
        )
        invalid_trigger = await session.call_tool(
            "map_trigger_create",
            {
                "request": {
                    "position": {"x": "1", "y": 0.0, "z": 0.0},
                    "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                }
            },
        )
        assert invalid_trigger.isError is True
        unconfirmed_delete = await session.call_tool(
            "map_trigger_delete",
            {"handle": "trg_" + "a" * 32, "confirm": False},
        )
        assert unconfirmed_delete.isError is True
        for coerced_confirmation in (1, "true"):
            coerced_delete = await session.call_tool(
                "map_trigger_delete",
                {
                    "handle": "trg_" + "a" * 32,
                    "confirm": coerced_confirmation,
                },
            )
            assert coerced_delete.isError is True
        for invalid_cursor in (True, "0"):
            invalid_events = await session.call_tool(
                "map_trigger_events",
                {
                    "handle": "trg_" + "a" * 32,
                    "after_sequence": invalid_cursor,
                },
            )
            assert invalid_events.isError is True
    # Lifespan owns shutdown; a second shutdown remains safe.
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_road_network_serializes_numeric_road_ids_for_mcp_client(
    tmp_path: Path,
) -> None:
    settings = Settings(workspace={"root": tmp_path / "workspace"})
    mcp, runtime = create_mcp_server(settings)

    async def road_network(
        *, include_edges: bool, drivable_only: bool
    ) -> dict[float, dict[str, object]]:
        assert include_edges is True
        assert drivable_only is True
        return {31375.0: {"nodes": ["a", "b"]}}

    runtime.simulator.road_network = road_network  # type: ignore[method-assign]
    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.call_tool(
            "map_road_network",
            {"include_edges": True, "drivable_only": True, "limit": 1},
        )

        assert result.isError is False
        assert result.structuredContent == {
            "31375.0": {"nodes": ["a", "b"]},
            "_meta": {"returned": 1, "total": 1, "truncated": False},
        }
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_trigger_mutation_tools_propagate_cancellation_to_lua_cleanup(
    tmp_path: Path,
) -> None:
    settings = Settings(workspace={"root": tmp_path / "workspace"})
    mcp, runtime = create_mcp_server(settings)
    guarded_operations: list[tuple[str, bool]] = []

    async def capture_guard(
        operation: str,
        _callback,
        *,
        propagate_cancellation: bool = False,
    ) -> None:
        guarded_operations.append((operation, propagate_cancellation))
        raise RuntimeError("guard capture")

    runtime.while_autonomy_inactive = capture_guard  # type: ignore[method-assign]
    handle = "trg_" + "a" * 32
    calls = [
        (
            "map_trigger_create",
            {
                "request": {
                    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                }
            },
        ),
        ("map_trigger_update", {"patch": {"handle": handle, "enabled": True}}),
        ("map_trigger_delete", {"handle": handle, "confirm": True}),
    ]

    async with create_connected_server_and_client_session(mcp) as session:
        for tool_name, arguments in calls:
            result = await session.call_tool(tool_name, arguments)
            assert result.isError is True

    assert guarded_operations == [
        ("create a map trigger", True),
        ("update a map trigger", True),
        ("delete a map trigger", True),
    ]
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_mcp_creates_a_reviewed_blender_softbody_handoff(tmp_path: Path) -> None:
    settings = Settings(workspace={"root": tmp_path / "workspace"})
    mcp, runtime = create_mcp_server(settings)
    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.call_tool(
            "softbody_handoff_create",
            {
                "request": {
                    "mod_name": "demo",
                    "asset_name": "demo",
                    "visual_object": "demo_mesh",
                    "cage_object": "demo_cage",
                    "coordinates": {
                        "source_origin_world": [0.0, 0.0, 0.0],
                        "source_world_to_beamng_vehicle": [
                            [1.0, 0.0, 0.0, 0.0],
                            [0.0, 1.0, 0.0, 0.0],
                            [0.0, 0.0, 1.0, 0.0],
                            [0.0, 0.0, 0.0, 1.0],
                        ],
                    },
                }
            },
        )
        assert result.isError is False
        assert result.structuredContent is not None
        assert set(result.structuredContent) == {
            "asset_name",
            "blender_execute_code",
            "blender_runner_path",
            "directory",
            "expires_at",
            "manifest_path",
            "mod_name",
            "slot_id",
            "visual_path",
        }
        slot_id = result.structuredContent["slot_id"]
        assert isinstance(slot_id, str)
        assert len(slot_id) == 32 and set(slot_id) <= set("0123456789abcdef")
        runner = Path(result.structuredContent["blender_runner_path"])
        helper = runner.parent / "beamng_softbody_export.py"
        runner_exists, helper_exists, runner_text = await asyncio.gather(
            asyncio.to_thread(runner.is_file),
            asyncio.to_thread(helper.is_file),
            asyncio.to_thread(runner.read_text, encoding="utf-8"),
        )
        assert runner_exists
        assert helper_exists
        assert "export_beamng_softbody" in runner_text
        assert "demo_mesh" in runner_text
        assert result.structuredContent["blender_execute_code"] == (
            f"import runpy\nrunpy.run_path({json.dumps(str(runner))}, run_name='__main__')"
        )
        assert Path(result.structuredContent["directory"]) == runner.parent
        assert Path(result.structuredContent["manifest_path"]) == (
            runner.parent / "structure.manifest.json"
        )
        assert Path(result.structuredContent["visual_path"]) == runner.parent / "visual.dae"
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
