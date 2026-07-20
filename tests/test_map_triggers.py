from __future__ import annotations

import math
from typing import Any

import pytest
from pydantic import ValidationError

from beamng_mcp.errors import SafetyInterlockError
from beamng_mcp.models import (
    MapTriggerAction,
    MapTriggerCreate,
    MapTriggerDeleteResult,
    MapTriggerEvent,
    MapTriggerEventPage,
    MapTriggerInfo,
    MapTriggerList,
    MapTriggerPatch,
)
from beamng_mcp.runtime import TOOL_NAMES, Runtime

HANDLE = "trg_" + "a" * 32
OTHER_HANDLE = "trg_" + "b" * 32


def _descriptor(handle: str = HANDLE, **updates: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "handle": handle,
        "engine_name": "beamng_mcp_trigger_" + handle.removeprefix("trg_"),
        "shape": "box",
        "position": {"x": 1.0, "y": 2.0, "z": 3.0},
        "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        "scale": {"x": 4.0, "y": 5.0, "z": 6.0},
        "mode": "center",
        "test_type": "bounding_box",
        "debug": False,
        "action": {"type": "emit_bridge_event", "events": ["enter", "exit"]},
        "enabled": False,
        "persistent": False,
        "sequence": 0,
        "count": 0,
    }
    value.update(updates)
    return value


def _event(sequence: int, handle: str = HANDLE) -> MapTriggerEvent:
    suffix = handle.removeprefix("trg_")
    return MapTriggerEvent(
        handle=handle,
        event="enter" if sequence % 2 else "exit",
        subject_id=7,
        subject_name="ego",
        trigger_id=42,
        trigger_name="beamng_mcp_trigger_" + suffix,
        sequence=sequence,
        count=sequence,
        time_seconds=float(sequence),
    )


def _descriptor_at(sequence: int, handle: str = HANDLE) -> dict[str, Any]:
    if sequence == 0:
        return _descriptor(handle=handle)
    event = _event(sequence, handle)
    return _descriptor(
        handle=handle,
        sequence=sequence,
        count=sequence,
        last_event={
            "sequence": event.sequence,
            "event": event.event,
            "subject_id": event.subject_id,
            "subject_name": event.subject_name,
            "time_seconds": event.time_seconds,
        },
    )


def test_trigger_schema_is_box_only_normalizes_rotation_and_rejects_code_fields() -> None:
    request = MapTriggerCreate(
        position={"x": 1, "y": 2.0, "z": 3.0},
        rotation={"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.5},
        scale={"x": 4.0, "y": 5.0, "z": 6.0},
    )
    assert request.shape == "box"
    assert request.rotation.w == pytest.approx(1.0)
    assert math.fsum(
        component * component
        for component in (
            request.rotation.x,
            request.rotation.y,
            request.rotation.z,
            request.rotation.w,
        )
    ) == pytest.approx(1.0)
    assert request.mode == "center"

    with pytest.raises(ValidationError, match="position"):
        MapTriggerCreate.model_validate({"scale": {"x": 1.0, "y": 1.0, "z": 1.0}})
    with pytest.raises(ValidationError, match="scale"):
        MapTriggerCreate.model_validate({"position": {"x": 0.0, "y": 0.0, "z": 0.0}})

    with pytest.raises(ValidationError, match="extra_forbidden"):
        MapTriggerCreate.model_validate({"luaFunction": "os.execute('no')"})
    with pytest.raises(ValidationError, match="literal_error"):
        MapTriggerCreate.model_validate({"shape": "sphere"})
    with pytest.raises(ValidationError, match="nonzero"):
        MapTriggerCreate.model_validate(
            {
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.0},
                "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
            }
        )


@pytest.mark.parametrize("value", [True, "1", float("nan"), float("inf")])
def test_trigger_coordinates_reject_coerced_or_nonfinite_numbers(value: object) -> None:
    with pytest.raises(ValidationError):
        MapTriggerCreate.model_validate(
            {
                "position": {"x": value, "y": 0.0, "z": 0.0},
                "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
            }
        )


@pytest.mark.parametrize(
    "action",
    [
        {"type": "emit_bridge_event", "events": []},
        {"type": "emit_bridge_event", "events": ["enter", "enter"]},
        {"type": "emit_bridge_event", "events": ["tick"]},
        {"type": "lua", "events": ["enter"]},
        {"type": "emit_bridge_event", "events": ["enter"], "code": "return true"},
    ],
)
def test_trigger_action_is_closed_and_requires_unique_enter_exit_events(
    action: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        MapTriggerAction.model_validate(action)


@pytest.mark.parametrize(
    "patch",
    [
        {"handle": HANDLE},
        {"handle": HANDLE, "enabled": None},
        {"handle": HANDLE, "enabled": 1},
        {"handle": HANDLE, "enabled": "true"},
        {"handle": "beamng_mcp_trigger_" + "a" * 32, "enabled": True},
    ],
)
def test_trigger_patch_requires_a_strict_non_null_change(patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MapTriggerPatch.model_validate(patch)


def test_trigger_result_models_reject_inconsistent_or_untyped_bridge_payloads() -> None:
    assert isinstance(MapTriggerInfo.model_validate(_descriptor()), MapTriggerInfo)
    event_info = MapTriggerInfo.model_validate(
        _descriptor(
            sequence=1,
            count=1,
            last_event={
                "sequence": 1,
                "event": "enter",
                "subject_id": 7,
                "subject_name": "ego",
                "time_seconds": 12.5,
            },
        )
    )
    assert event_info.last_event is not None and event_info.last_event.subject_id == 7
    with pytest.raises(ValidationError):
        MapTriggerInfo.model_validate(_descriptor(enabled="false"))
    with pytest.raises(ValidationError):
        MapTriggerInfo.model_validate(_descriptor(persistent=True))
    with pytest.raises(ValidationError):
        MapTriggerInfo.model_validate(_descriptor(persistent=0))
    with pytest.raises(ValidationError):
        MapTriggerInfo.model_validate(_descriptor(last_event="enter"))
    with pytest.raises(ValidationError, match="count does not match"):
        MapTriggerList.model_validate({"triggers": [_descriptor()], "count": 0, "limit": 10})
    with pytest.raises(ValidationError):
        MapTriggerDeleteResult.model_validate({"deleted": False, "handle": HANDLE})
    with pytest.raises(ValidationError):
        MapTriggerDeleteResult.model_validate({"deleted": 1, "handle": HANDLE})


def test_trigger_event_page_enforces_cursor_and_handle_invariants() -> None:
    page = MapTriggerEventPage(
        handle=HANDLE,
        events=[_event(2), _event(3)],
        after_sequence=1,
        next_sequence=3,
        latest_sequence=5,
        current_count=5,
        oldest_available_sequence=1,
        truncated=False,
        has_more=True,
        limit=2,
    )
    assert [event.sequence for event in page.events] == [2, 3]

    invalid_pages = [
        page.model_dump() | {"after_sequence": True},
        page.model_dump() | {"limit": "2"},
        page.model_dump() | {"events": [_event(2), _event(2)]},
        page.model_dump() | {"events": [_event(2, OTHER_HANDLE)]},
        page.model_dump() | {"has_more": False},
    ]
    for payload in invalid_pages:
        with pytest.raises(ValidationError):
            MapTriggerEventPage.model_validate(payload)


class TriggerLua:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, params))
        handle = params.get("handle", HANDLE)
        if method == "trigger.list":
            return {"triggers": [_descriptor()], "count": 1, "limit": params["limit"]}
        if method == "trigger.delete":
            return {"deleted": True, "handle": handle}
        enabled = params.get("enabled", False)
        return _descriptor(
            handle=handle,
            enabled=enabled,
            object_id=42 if enabled else None,
        )

    async def call_validated_trigger_mutation(
        self,
        method: str,
        params: dict[str, Any],
        validator: Any,
    ) -> Any:
        return validator(await self.call(method, params))

    def buffered_trigger_events(self, handle: str) -> list[MapTriggerEvent]:
        return []


class TriggerEventLua:
    def __init__(self, descriptor: dict[str, Any], events: list[MapTriggerEvent]) -> None:
        self.descriptor = descriptor
        self.events = events
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, params))
        assert method == "trigger.get"
        return self.descriptor

    def buffered_trigger_events(self, _handle: str) -> list[MapTriggerEvent]:
        return [event.model_copy(deep=True) for event in self.events]


@pytest.mark.asyncio
async def test_runtime_maps_trigger_models_to_flattened_typed_lua_contract(monkeypatch) -> None:
    runtime = object.__new__(Runtime)
    runtime.lua = TriggerLua()
    monkeypatch.setattr("beamng_mcp.runtime.secrets.token_hex", lambda _size: "a" * 32)

    created = await runtime.map_trigger_create(
        MapTriggerCreate(
            position={"x": 1.0, "y": 2.0, "z": 3.0},
            rotation={"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.5},
            scale={"x": 4.0, "y": 5.0, "z": 6.0},
        )
    )
    assert created.handle == HANDLE
    method, params = runtime.lua.calls[-1]
    assert method == "trigger.create"
    assert params["handle"] == HANDLE
    assert params["rotation"] == {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    assert "enabled" not in params

    updated = await runtime.map_trigger_update(
        MapTriggerPatch(handle=HANDLE, enabled=True, debug=True)
    )
    assert updated.enabled is True
    assert runtime.lua.calls[-1] == (
        "trigger.update",
        {"handle": HANDLE, "debug": True, "enabled": True},
    )

    assert (await runtime.map_trigger_get(HANDLE)).handle == HANDLE
    assert runtime.lua.calls[-1] == ("trigger.get", {"handle": HANDLE})
    listed = await runtime.map_trigger_list(limit=12)
    assert listed.count == 1
    assert runtime.lua.calls[-1] == ("trigger.list", {"limit": 12})

    with pytest.raises(SafetyInterlockError, match="confirm=true"):
        await runtime.map_trigger_delete(HANDLE, confirm=False)
    deleted = await runtime.map_trigger_delete(HANDLE, confirm=True)
    assert deleted.deleted is True
    assert runtime.lua.calls[-1] == (
        "trigger.delete",
        {"handle": HANDLE, "confirm": True},
    )


@pytest.mark.asyncio
async def test_runtime_rejects_invalid_trigger_results_and_direct_coercion() -> None:
    runtime = object.__new__(Runtime)
    runtime.lua = TriggerLua()

    with pytest.raises(ValidationError):
        await runtime.map_trigger_get(True)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        await runtime.map_trigger_list(limit=True)  # type: ignore[arg-type]

    async def invalid_call(_method: str, _params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    runtime.lua.call = invalid_call  # type: ignore[method-assign]
    with pytest.raises(ValidationError):
        await runtime.map_trigger_get(HANDLE)


@pytest.mark.asyncio
async def test_runtime_pages_contiguous_trigger_events_with_a_stable_cursor() -> None:
    runtime = object.__new__(Runtime)
    runtime.lua = TriggerEventLua(_descriptor_at(5), [_event(sequence) for sequence in range(1, 6)])

    page = await runtime.map_trigger_events(HANDLE, after_sequence=1, limit=2)

    assert [event.sequence for event in page.events] == [2, 3]
    assert page.after_sequence == 1
    assert page.next_sequence == 3
    assert page.latest_sequence == 5
    assert page.current_count == 5
    assert page.oldest_available_sequence == 1
    assert page.truncated is False
    assert page.has_more is True
    assert runtime.lua.calls == [("trigger.get", {"handle": HANDLE})]


@pytest.mark.asyncio
async def test_runtime_marks_trigger_event_deque_overflow_and_internal_gaps() -> None:
    runtime = object.__new__(Runtime)
    runtime.lua = TriggerEventLua(
        _descriptor_at(300),
        [_event(sequence) for sequence in range(45, 301)],
    )

    overflow = await runtime.map_trigger_events(HANDLE, after_sequence=0, limit=50)
    assert [event.sequence for event in overflow.events] == list(range(45, 95))
    assert overflow.oldest_available_sequence == 45
    assert overflow.next_sequence == 94
    assert overflow.latest_sequence == 300
    assert overflow.truncated is True
    assert overflow.has_more is True

    runtime.lua = TriggerEventLua(_descriptor_at(4), [_event(1), _event(3), _event(4)])
    gap = await runtime.map_trigger_events(HANDLE, after_sequence=0, limit=50)
    assert [event.sequence for event in gap.events] == [1, 3, 4]
    assert gap.next_sequence == 4
    assert gap.truncated is True
    assert gap.has_more is False


@pytest.mark.asyncio
async def test_runtime_advances_past_fully_lost_events_without_leaking_other_handles() -> None:
    runtime = object.__new__(Runtime)
    runtime.lua = TriggerEventLua(_descriptor_at(12), [])

    lost = await runtime.map_trigger_events(HANDLE, after_sequence=3, limit=50)
    assert lost.events == []
    assert lost.oldest_available_sequence is None
    assert lost.next_sequence == 12
    assert lost.latest_sequence == 12
    assert lost.truncated is True
    assert lost.has_more is False

    runtime.lua = TriggerEventLua(_descriptor_at(1), [_event(1, OTHER_HANDLE)])
    wrong_handle = await runtime.map_trigger_events(HANDLE)
    assert wrong_handle.events == []
    assert wrong_handle.next_sequence == 1
    assert wrong_handle.truncated is True


@pytest.mark.asyncio
async def test_runtime_trigger_event_page_rejects_coercion_and_mismatched_ownership() -> None:
    runtime = object.__new__(Runtime)
    runtime.lua = TriggerEventLua(_descriptor_at(0), [])

    for after_sequence in (True, "0"):
        with pytest.raises(ValidationError):
            await runtime.map_trigger_events(
                HANDLE,
                after_sequence=after_sequence,  # type: ignore[arg-type]
            )
    for limit in (True, "50", 0, 101):
        with pytest.raises(ValidationError):
            await runtime.map_trigger_events(HANDLE, limit=limit)  # type: ignore[arg-type]

    runtime.lua = TriggerEventLua(_descriptor_at(0, OTHER_HANDLE), [])
    with pytest.raises(SafetyInterlockError, match="requested handle"):
        await runtime.map_trigger_events(HANDLE)


def test_runtime_curated_surface_contains_exactly_six_trigger_tools() -> None:
    assert len(TOOL_NAMES) == 57
    assert [name for name in TOOL_NAMES if name.startswith("map_trigger_")] == [
        "map_trigger_create",
        "map_trigger_get",
        "map_trigger_update",
        "map_trigger_list",
        "map_trigger_events",
        "map_trigger_delete",
    ]
