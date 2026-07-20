from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest
from pydantic import SecretStr

from beamng_mcp.config import Settings
from beamng_mcp.errors import SafetyInterlockError
from beamng_mcp.models import AutonomyStart, AutonomyStatus, BridgeStatus, ConnectionStatus
from beamng_mcp.runtime import Runtime


class LeaseLua:
    connected = False

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_arm = False
        self.fail_renew = False
        self.fail_stop = False
        self.arm_expires = 0.5
        self.block_arm = False
        self.arm_started = asyncio.Event()
        self.release_arm = asyncio.Event()

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.events.append(f"lua:{method}")
        self.calls.append((method, params))
        if method == "safety.lease_arm":
            self.arm_started.set()
            if self.block_arm:
                await self.release_arm.wait()
            if self.fail_arm:
                raise RuntimeError("arm rejected")
            return {
                "armed": True,
                "lease_id": params["lease_id"],
                "expires_in_seconds": self.arm_expires,
            }
        if method == "safety.lease_renew":
            if self.fail_renew:
                raise RuntimeError("renew rejected")
            return {
                "armed": True,
                "lease_id": params["lease_id"],
                "expires_in_seconds": 0.25,
            }
        if method == "safety.lease_disarm":
            return {"disarmed": True, "armed": False}
        if method == "emergency_stop":
            if self.fail_stop:
                return {"stopped": False}
            return {"stopped": True}
        return {}

    async def close(self) -> None:
        self.events.append("lua:close")


class LeaseAutonomy:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.running = False
        self.mode: str | None = None
        self.vehicle_id: str | None = None
        self.recent_control = False
        self.fail_start = False
        self.block_prepare = False
        self.block_start = False
        self.prepare_started = asyncio.Event()
        self.release_prepare = asyncio.Event()
        self.start_started = asyncio.Event()
        self.release_start = asyncio.Event()
        self.stop_event = asyncio.Event()

    async def prepare(self, _spec: AutonomyStart) -> None:
        self.events.append("autonomy:prepare")
        self.prepare_started.set()
        if self.block_prepare:
            await self.release_prepare.wait()

    def discard_prepared(self) -> None:
        self.events.append("autonomy:discard_prepared")

    async def start(self, spec: AutonomyStart) -> AutonomyStatus:
        self.events.append("autonomy:start")
        self.start_started.set()
        if self.block_start:
            await self.release_start.wait()
        if self.fail_start:
            raise RuntimeError("autonomy setup rejected")
        self.running = True
        self.mode = spec.mode
        self.vehicle_id = spec.vehicle_id
        return self.status()

    async def stop(self, *, reason: str = "operator_stop") -> AutonomyStatus:
        self.events.append(f"autonomy:stop:{reason}")
        self.running = False
        self.stop_event.set()
        return self.status(reason=reason)

    async def emergency_stop(self, reason: str) -> AutonomyStatus:
        return await self.stop(reason=reason)

    async def shutdown(self) -> None:
        self.events.append("autonomy:shutdown")
        self.running = False

    def has_recent_successful_control(self, _max_age_seconds: float) -> bool:
        return self.recent_control

    def status(self, reason: str | None = None) -> AutonomyStatus:
        return AutonomyStatus(
            running=self.running,
            mode=self.mode,
            vehicle_id=self.vehicle_id,
            emergency_stopped=reason is not None,
            emergency_reason=reason,
        )


class LeaseSimulator:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.block_heartbeat = False
        self.block_after_heartbeats: int | None = None
        self.heartbeat_count = 0
        self.block_emergency_stop = False
        self.emergency_stop_started = asyncio.Event()
        self.release_emergency_stop = asyncio.Event()

    async def status(self) -> ConnectionStatus:
        return ConnectionStatus(connected=True, host="127.0.0.1", port=25252)

    async def emergency_stop(self, vehicle_id: str | None = None) -> None:
        self.events.append(f"simulator:stop:{vehicle_id}")
        self.emergency_stop_started.set()
        if self.block_emergency_stop:
            await self.release_emergency_stop.wait()

    async def vehicle_state(self, vehicle_id: str) -> object:
        self.events.append(f"simulator:heartbeat:{vehicle_id}")
        self.heartbeat_count += 1
        if self.block_heartbeat or (
            self.block_after_heartbeats is not None
            and self.heartbeat_count > self.block_after_heartbeats
        ):
            await asyncio.Event().wait()
        return type("Heartbeat", (), {"vehicle_id": vehicle_id})()

    async def disconnect(self) -> None:
        self.events.append("simulator:disconnect")

    async def shutdown(self) -> None:
        self.events.append("simulator:shutdown")


async def lease_runtime() -> tuple[Runtime, LeaseLua, LeaseAutonomy, LeaseSimulator, list[str]]:
    events: list[str] = []
    runtime = Runtime(
        Settings(
            lua={
                "token": SecretStr("l" * 32),
                "safety_lease_seconds": 0.25,
                "safety_startup_grace_seconds": 0.5,
            }
        )
    )
    await runtime.simulator.shutdown()
    lua = LeaseLua(events)
    autonomy = LeaseAutonomy(events)
    simulator = LeaseSimulator(events)
    runtime.lua = lua  # type: ignore[assignment]
    runtime.autonomy = autonomy  # type: ignore[assignment]
    runtime.simulator = simulator  # type: ignore[assignment]
    return runtime, lua, autonomy, simulator, events


@pytest.mark.asyncio
async def test_native_autonomy_arms_named_engine_lease_before_start() -> None:
    runtime, lua, _autonomy, _simulator, events = await lease_runtime()

    status = await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))

    arm = next(params for method, params in lua.calls if method == "safety.lease_arm")
    assert arm["vehicle_name"] == "ego"
    assert events[:4] == [
        "autonomy:prepare",
        "lua:safety.lease_arm",
        "autonomy:start",
        "simulator:heartbeat:ego",
    ]
    assert events[4] == "lua:safety.lease_renew"
    assert status.engine_deadman_armed is True
    assert status.engine_deadman_control_authorized is True
    assert status.engine_deadman_expires_in_ms is not None

    await runtime.autonomy_stop(reason="test_cleanup")
    local_stop_index = events.index("autonomy:stop:test_cleanup")
    lua_stop_index = events.index("lua:emergency_stop")
    disarm_index = events.index("lua:safety.lease_disarm")
    assert local_stop_index < lua_stop_index < disarm_index
    renewals = events.count("lua:safety.lease_renew")
    await asyncio.sleep(0.3)
    assert events.count("lua:safety.lease_renew") == renewals


@pytest.mark.asyncio
async def test_vision_backend_warmup_completes_before_engine_lease_arm() -> None:
    runtime, _lua, _autonomy, _simulator, events = await lease_runtime()

    await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="vision-lane"))

    prepare_index = events.index("autonomy:prepare")
    arm_index = events.index("lua:safety.lease_arm")
    start_index = events.index("autonomy:start")
    assert prepare_index < arm_index < start_index
    await runtime.autonomy_stop(reason="test_cleanup")


@pytest.mark.asyncio
async def test_native_ai_requires_bounded_vehicle_heartbeat_before_renewal() -> None:
    runtime, lua, autonomy, simulator, events = await lease_runtime()
    simulator.block_heartbeat = True

    with pytest.raises(SafetyInterlockError, match="heartbeat"):
        await asyncio.wait_for(
            runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai")),
            timeout=0.5,
        )

    assert "simulator:heartbeat:ego" in events
    assert not any(method == "safety.lease_renew" for method, _params in lua.calls)
    assert autonomy.running is False
    assert "simulator:stop:ego" in events


@pytest.mark.asyncio
async def test_native_ai_stops_when_recurring_heartbeat_freezes() -> None:
    runtime, lua, autonomy, simulator, _events = await lease_runtime()
    simulator.block_after_heartbeats = 1

    await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))
    await asyncio.wait_for(autonomy.stop_event.wait(), timeout=0.5)

    renewals = [method for method, _params in lua.calls if method == "safety.lease_renew"]
    assert renewals == ["safety.lease_renew"]
    status = runtime.autonomy_status()
    assert status.running is False
    assert status.engine_deadman_control_authorized is False
    assert "heartbeat" in (status.engine_deadman_last_error or "")


@pytest.mark.asyncio
async def test_emergency_stop_invalidates_pending_warmup_before_lease_arm() -> None:
    runtime, lua, autonomy, _simulator, events = await lease_runtime()
    autonomy.block_prepare = True
    start_task = asyncio.create_task(
        runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="vision-lane"))
    )
    await asyncio.wait_for(autonomy.prepare_started.wait(), timeout=0.5)

    await runtime.emergency_stop("ego")
    autonomy.release_prepare.set()

    with pytest.raises(SafetyInterlockError, match="cancelled"):
        await asyncio.wait_for(start_task, timeout=0.5)
    assert not any(method == "safety.lease_arm" for method, _params in lua.calls)
    assert "autonomy:start" not in events


@pytest.mark.asyncio
async def test_game_mutation_is_rejected_while_autonomy_warmup_is_pending() -> None:
    runtime, _lua, autonomy, _simulator, _events = await lease_runtime()
    autonomy.block_prepare = True
    start_task = asyncio.create_task(
        runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="vision-lane"))
    )
    await asyncio.wait_for(autonomy.prepare_started.wait(), timeout=0.5)
    mutation_called = False

    async def mutate() -> None:
        nonlocal mutation_called
        mutation_called = True

    with pytest.raises(SafetyInterlockError, match="while autonomy is starting"):
        await runtime.while_autonomy_inactive("mutate the game", mutate)

    assert mutation_called is False
    await runtime.emergency_stop("ego")
    autonomy.release_prepare.set()
    with pytest.raises(SafetyInterlockError, match="cancelled"):
        await asyncio.wait_for(start_task, timeout=0.5)


@pytest.mark.asyncio
async def test_mutation_lock_closes_check_then_act_race_with_autonomy_start() -> None:
    runtime, _lua, autonomy, _simulator, _events = await lease_runtime()
    mutation_started = asyncio.Event()
    release_mutation = asyncio.Event()

    async def mutate() -> None:
        mutation_started.set()
        await release_mutation.wait()

    mutation_task = asyncio.create_task(runtime.while_autonomy_inactive("mutate the game", mutate))
    await asyncio.wait_for(mutation_started.wait(), timeout=0.5)
    start_task = asyncio.create_task(
        runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))
    )
    await asyncio.sleep(0)
    assert autonomy.prepare_started.is_set() is False

    release_mutation.set()
    await mutation_task
    status = await asyncio.wait_for(start_task, timeout=0.5)
    assert status.running is True
    await runtime.autonomy_stop(reason="test_cleanup")


@pytest.mark.asyncio
async def test_disconnect_waits_for_cancelled_warmup_before_closing_simulator() -> None:
    runtime, _lua, autonomy, _simulator, events = await lease_runtime()
    autonomy.block_prepare = True
    start_task = asyncio.create_task(
        runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="vision-lane"))
    )
    await asyncio.wait_for(autonomy.prepare_started.wait(), timeout=0.5)

    disconnect_task = asyncio.create_task(runtime.simulator_disconnect())
    await asyncio.sleep(0)
    assert disconnect_task.done() is False
    assert "simulator:disconnect" not in events

    autonomy.release_prepare.set()
    with pytest.raises(SafetyInterlockError, match="cancelled"):
        await asyncio.wait_for(start_task, timeout=0.5)
    result = await asyncio.wait_for(disconnect_task, timeout=0.5)
    assert result.ok is True
    assert events[-1] == "simulator:disconnect"


@pytest.mark.asyncio
async def test_mod_install_job_blocks_autonomy_start() -> None:
    runtime, _lua, _autonomy, _simulator, _events = await lease_runtime()
    install_started = asyncio.Event()
    release_install = asyncio.Event()

    async def install_worker(context: Any) -> dict[str, Any]:
        await context.set_stage("installing", cancellable=False)
        install_started.set()
        await release_install.wait()
        await context.set_stage("install_complete", cancellable=True)
        return {}

    await runtime.jobs.start("mod_install_test", install_worker)
    await asyncio.wait_for(install_started.wait(), timeout=0.5)
    try:
        with pytest.raises(SafetyInterlockError, match="mod installation job"):
            await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))
    finally:
        release_install.set()
        await runtime.jobs.shutdown()


@pytest.mark.asyncio
async def test_cancelled_thread_mutation_holds_lock_until_worker_finishes() -> None:
    runtime, _lua, autonomy, _simulator, _events = await lease_runtime()
    mutation_started = threading.Event()
    release_mutation = threading.Event()

    def blocking_mutation() -> None:
        mutation_started.set()
        assert release_mutation.wait(1.0)

    async def mutate() -> None:
        await asyncio.to_thread(blocking_mutation)

    mutation_task = asyncio.create_task(runtime.while_autonomy_inactive("mutate the game", mutate))
    assert await asyncio.to_thread(mutation_started.wait, 0.5)
    mutation_task.cancel()

    start_task = asyncio.create_task(
        runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))
    )
    await asyncio.sleep(0)
    assert mutation_task.done() is False
    assert autonomy.prepare_started.is_set() is False

    release_mutation.set()
    with pytest.raises(asyncio.CancelledError):
        await mutation_task
    status = await asyncio.wait_for(start_task, timeout=0.5)
    assert status.running is True
    await runtime.autonomy_stop(reason="test_cleanup")


@pytest.mark.asyncio
async def test_fail_closed_mutation_propagates_cancellation_into_peer_cleanup() -> None:
    runtime, _lua, _autonomy, _simulator, _events = await lease_runtime()
    mutation_sent = asyncio.Event()
    peer_closed = asyncio.Event()

    async def mutate() -> None:
        mutation_sent.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            peer_closed.set()
            raise

    mutation_task = asyncio.create_task(
        runtime.while_autonomy_inactive(
            "create a map trigger",
            mutate,
            propagate_cancellation=True,
        )
    )
    await asyncio.wait_for(mutation_sent.wait(), timeout=0.5)
    mutation_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await mutation_task
    assert peer_closed.is_set()

    # Cancellation cleanup completes before the transition lock becomes available.
    followup_completed = False

    async def followup() -> None:
        nonlocal followup_completed
        followup_completed = True

    await runtime.while_autonomy_inactive("run a follow-up mutation", followup)
    assert followup_completed is True


@pytest.mark.asyncio
async def test_cancelled_start_during_lease_arm_brakes_and_disarms() -> None:
    runtime, lua, autonomy, _simulator, events = await lease_runtime()
    lua.block_arm = True
    start_task = asyncio.create_task(
        runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))
    )
    await asyncio.wait_for(lua.arm_started.wait(), timeout=0.5)

    start_task.cancel()
    await asyncio.sleep(0)
    assert start_task.done() is False
    lua.release_arm.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(start_task, timeout=0.5)

    assert autonomy.running is False
    assert runtime.autonomy_status().engine_deadman_armed is False
    assert "lua:emergency_stop" in events
    assert "lua:safety.lease_disarm" in events


@pytest.mark.asyncio
async def test_cancelled_start_during_native_ai_setup_brakes_and_disarms() -> None:
    runtime, _lua, autonomy, _simulator, events = await lease_runtime()
    autonomy.block_start = True
    start_task = asyncio.create_task(
        runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))
    )
    await asyncio.wait_for(autonomy.start_started.wait(), timeout=0.5)

    start_task.cancel()
    await asyncio.sleep(0)
    assert start_task.done() is False
    autonomy.release_start.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(start_task, timeout=0.5)

    assert autonomy.running is False
    assert runtime.autonomy_status().engine_deadman_armed is False
    assert "lua:emergency_stop" in events
    assert "lua:safety.lease_disarm" in events


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["stop", "disconnect", "shutdown"])
async def test_lifecycle_transition_blocks_start_already_queued_on_mutation(
    lifecycle: str,
) -> None:
    runtime, _lua, autonomy, _simulator, _events = await lease_runtime()
    mutation_started = asyncio.Event()
    release_mutation = asyncio.Event()

    async def mutate() -> None:
        mutation_started.set()
        await release_mutation.wait()

    mutation_task = asyncio.create_task(runtime.while_autonomy_inactive("mutate the game", mutate))
    await asyncio.wait_for(mutation_started.wait(), timeout=0.5)
    start_task = asyncio.create_task(
        runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))
    )
    await asyncio.sleep(0)

    if lifecycle == "stop":
        lifecycle_task = asyncio.create_task(runtime.autonomy_stop(reason="queued_stop"))
    elif lifecycle == "disconnect":
        lifecycle_task = asyncio.create_task(runtime.simulator_disconnect())
    else:
        lifecycle_task = asyncio.create_task(runtime.shutdown())
    await asyncio.sleep(0)
    release_mutation.set()
    await mutation_task

    with pytest.raises(SafetyInterlockError):
        await asyncio.wait_for(start_task, timeout=0.5)
    await asyncio.wait_for(lifecycle_task, timeout=0.5)
    assert autonomy.running is False
    assert autonomy.prepare_started.is_set() is False


@pytest.mark.asyncio
async def test_emergency_stop_blocks_new_autonomy_start_until_all_paths_finish() -> None:
    runtime, _lua, _autonomy, simulator, _events = await lease_runtime()
    simulator.block_emergency_stop = True
    emergency_task = asyncio.create_task(runtime.emergency_stop("ego"))
    await asyncio.wait_for(simulator.emergency_stop_started.wait(), timeout=0.5)

    with pytest.raises(SafetyInterlockError):
        await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))

    simulator.release_emergency_stop.set()
    result = await asyncio.wait_for(emergency_task, timeout=0.5)
    assert result.ok is True


@pytest.mark.asyncio
async def test_active_autonomy_rejects_install_enabled_mod_test() -> None:
    runtime, _lua, _autonomy, _simulator, _events = await lease_runtime()
    await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))
    try:
        with pytest.raises(SafetyInterlockError, match="mod installation job"):
            await runtime.start_mod_test("sample", install=True)
    finally:
        await runtime.autonomy_stop(reason="test_cleanup")


@pytest.mark.asyncio
async def test_lua_reload_waits_for_fresh_authenticated_bridge() -> None:
    events: list[str] = []

    class ReloadLua:
        async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
            events.append(f"call:{method}:{params['name']}")
            return {"scheduled": True, "name": params["name"]}

        async def close(self) -> None:
            events.append("close")

        async def probe(self) -> BridgeStatus:
            events.append("probe")
            return BridgeStatus(
                connected=True,
                authenticated=True,
                url="ws://127.0.0.1:8765",
                bridge_version="0.1.0",
                game_version="0.38",
            )

    runtime = object.__new__(Runtime)
    runtime.settings = Settings()
    runtime.lua = ReloadLua()  # type: ignore[assignment]

    result = await runtime.reload_lua_extension("beamng_mcp/bridge")

    assert events == ["call:extension.reload:beamng_mcp/bridge", "close", "probe"]
    assert result["bridge_ready"] is True
    assert result["bridge_version"] == "0.1.0"


@pytest.mark.asyncio
async def test_autonomy_start_arm_failure_rolls_back_and_brakes() -> None:
    runtime, lua, _autonomy, _simulator, events = await lease_runtime()
    lua.fail_arm = True

    with pytest.raises(SafetyInterlockError, match="arm failed"):
        await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))

    assert "autonomy:start" not in events
    assert "simulator:stop:ego" in events
    assert events[:3] == [
        "autonomy:prepare",
        "lua:safety.lease_arm",
        "simulator:stop:ego",
    ]
    assert "lua:emergency_stop" in events
    status = runtime.autonomy_status()
    assert status.engine_deadman_armed is False
    assert status.engine_deadman_control_authorized is False
    assert status.engine_deadman_last_error is not None


@pytest.mark.asyncio
async def test_autonomy_setup_failure_brakes_before_disarming_engine_lease() -> None:
    runtime, _lua, autonomy, _simulator, events = await lease_runtime()
    autonomy.fail_start = True

    with pytest.raises(SafetyInterlockError, match="Autonomy start failed"):
        await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))

    simulator_stop_index = events.index("simulator:stop:ego")
    lua_stop_index = events.index("lua:emergency_stop")
    disarm_index = events.index("lua:safety.lease_disarm")
    assert simulator_stop_index < lua_stop_index < disarm_index
    status = runtime.autonomy_status()
    assert status.running is False
    assert status.engine_deadman_armed is False
    assert status.engine_deadman_control_authorized is False


@pytest.mark.asyncio
async def test_vision_renewal_failure_revokes_control_and_stops_autonomy() -> None:
    runtime, lua, autonomy, _simulator, events = await lease_runtime()
    autonomy.recent_control = True
    lua.fail_renew = True
    await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="vision-lane"))

    await asyncio.wait_for(autonomy.stop_event.wait(), timeout=1.0)

    renew_index = events.index("lua:safety.lease_renew")
    local_stop_index = events.index("autonomy:stop:engine_deadman_failure")
    lua_stop_index = events.index("lua:emergency_stop")
    disarm_index = events.index("lua:safety.lease_disarm")
    assert renew_index < local_stop_index < lua_stop_index < disarm_index
    status = runtime.autonomy_status()
    assert status.running is False
    assert status.engine_deadman_armed is False
    assert status.engine_deadman_control_authorized is False
    assert "renewal failed" in (status.engine_deadman_last_error or "")


@pytest.mark.asyncio
async def test_vision_startup_without_successful_control_fails_before_lease_expiry() -> None:
    runtime, lua, autonomy, _simulator, events = await lease_runtime()
    lua.arm_expires = 0.25
    await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="vision-lane"))

    await asyncio.wait_for(autonomy.stop_event.wait(), timeout=1.0)

    assert "lua:safety.lease_renew" not in events
    assert "autonomy:stop:engine_deadman_failure" in events
    status = runtime.autonomy_status()
    assert status.engine_deadman_control_authorized is False
    assert "No recent successful BeamNG control" in (status.engine_deadman_last_error or "")


@pytest.mark.asyncio
async def test_stop_leaves_lease_armed_when_lua_brake_fails() -> None:
    runtime, lua, _autonomy, _simulator, events = await lease_runtime()
    await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))
    lua.fail_stop = True

    with pytest.raises(SafetyInterlockError, match="Lua stop"):
        await runtime.autonomy_stop(reason="operator_stop")

    assert "lua:emergency_stop" in events
    assert "lua:safety.lease_disarm" not in events
    status = runtime.autonomy_status()
    assert status.engine_deadman_armed is True
    assert status.engine_deadman_control_authorized is False


@pytest.mark.asyncio
async def test_emergency_stop_keeps_fail_closed_lease_when_lua_brake_fails() -> None:
    runtime, lua, _autonomy, _simulator, events = await lease_runtime()
    await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))
    lua.fail_stop = True

    result = await runtime.emergency_stop("ego")

    assert result.ok is False
    assert result.data["outcomes"]["engine_deadman"]["fail_closed"] is True
    assert "lua:safety.lease_disarm" not in events
    assert runtime.autonomy_status().engine_deadman_armed is True


@pytest.mark.asyncio
async def test_simulator_disconnect_uses_lease_aware_stop_wrapper() -> None:
    runtime, _lua, _autonomy, _simulator, events = await lease_runtime()
    await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))

    result = await runtime.simulator_disconnect()

    assert result.ok is True
    local_stop_index = events.index("autonomy:stop:simulator_disconnect")
    lua_stop_index = events.index("lua:emergency_stop")
    disarm_index = events.index("lua:safety.lease_disarm")
    disconnect_index = events.index("simulator:disconnect")
    assert local_stop_index < lua_stop_index < disarm_index < disconnect_index


class FailingShutdownAutonomy:
    running = False

    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def shutdown(self) -> None:
        self.events.append("autonomy:shutdown")
        raise RuntimeError("autonomy cleanup failed")


class FailingShutdownComponent:
    def __init__(self, events: list[str], label: str, *, fail: bool) -> None:
        self.events = events
        self.label = label
        self.fail = fail

    async def shutdown(self) -> None:
        self.events.append(f"{self.label}:shutdown")
        if self.fail:
            raise RuntimeError(f"{self.label} cleanup failed")


class ClosingLua:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def close(self) -> None:
        self.events.append("lua:close")


@pytest.mark.asyncio
async def test_shutdown_attempts_every_cleanup_and_aggregates_failures() -> None:
    events: list[str] = []
    runtime = object.__new__(Runtime)
    runtime._lease_engine_armed = False
    runtime._lease_task = None
    runtime._autonomy_transition_lock = asyncio.Lock()
    runtime.autonomy = FailingShutdownAutonomy(events)  # type: ignore[assignment]
    runtime.jobs = FailingShutdownComponent(events, "jobs", fail=True)  # type: ignore[assignment]
    runtime.lua = ClosingLua(events)  # type: ignore[assignment]
    runtime.simulator = FailingShutdownComponent(  # type: ignore[assignment]
        events, "simulator", fail=True
    )

    with pytest.raises(SafetyInterlockError) as raised:
        await runtime.shutdown()

    assert events == [
        "jobs:shutdown",
        "autonomy:shutdown",
        "lua:close",
        "simulator:shutdown",
    ]
    message = str(raised.value)
    assert "autonomy cleanup failed" in message
    assert "jobs cleanup failed" in message
    assert "simulator cleanup failed" in message


@pytest.mark.asyncio
async def test_cancelled_shutdown_finishes_join_and_component_cleanup() -> None:
    runtime, _lua, _autonomy, _simulator, events = await lease_runtime()
    job_started = asyncio.Event()
    release_job = asyncio.Event()

    async def worker(context: Any) -> dict[str, Any]:
        await context.set_stage("mutating", cancellable=False)
        job_started.set()
        await release_job.wait()
        await context.set_stage("mutation_complete", cancellable=True)
        return {}

    await runtime.jobs.start("blocking_mutation", worker)
    await asyncio.wait_for(job_started.wait(), timeout=0.5)
    shutdown_task = asyncio.create_task(runtime.shutdown())
    await asyncio.sleep(0)
    shutdown_task.cancel()
    await asyncio.sleep(0)
    assert shutdown_task.done() is False

    release_job.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(shutdown_task, timeout=0.5)

    assert "autonomy:shutdown" in events
    assert "lua:close" in events
    assert "simulator:shutdown" in events


@pytest.mark.asyncio
async def test_shutdown_stops_active_autonomy_before_waiting_for_static_job() -> None:
    runtime, _lua, autonomy, _simulator, events = await lease_runtime()
    await runtime.autonomy_start(AutonomyStart(vehicle_id="ego", mode="native-ai"))
    job_started = asyncio.Event()
    release_job = asyncio.Event()

    async def worker(context: Any) -> dict[str, Any]:
        await context.set_stage("packing", cancellable=False)
        job_started.set()
        await release_job.wait()
        await context.set_stage("pack_complete", cancellable=True)
        return {}

    await runtime.jobs.start("mod_test", worker)
    await asyncio.wait_for(job_started.wait(), timeout=0.5)
    shutdown_task = asyncio.create_task(runtime.shutdown())

    await asyncio.wait_for(autonomy.stop_event.wait(), timeout=0.5)
    assert "lua:emergency_stop" in events
    assert "lua:safety.lease_disarm" in events
    assert runtime._lease_task is None
    assert shutdown_task.done() is False

    release_job.set()
    await asyncio.wait_for(shutdown_task, timeout=0.5)
