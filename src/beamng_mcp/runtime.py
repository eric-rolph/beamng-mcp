"""Process-level application runtime shared across MCP sessions and transports."""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypeVar

from . import __version__
from .adapters.beamngpy_adapter import BeamNGpyAdapter
from .adapters.lua_bridge import LuaBridgeClient
from .autodetect import Installation, detect_installation
from .config import Settings
from .errors import SafetyInterlockError
from .installer import discover_lua_token
from .models import (
    AutonomyStart,
    AutonomyStatus,
    CapabilitySnapshot,
    JobInfo,
    MapObjectMutation,
    MapObjectPatch,
    OperationResult,
)
from .services.autonomy import AutonomyService
from .services.jobs import JobContext, JobManager
from .services.mods import ModWorkspace
from .services.structural import StructuralModService

T = TypeVar("T")


async def _await_to_completion(
    operation: Awaitable[T],
    *,
    on_cancel: Callable[[], None] | None = None,
) -> tuple[T, bool]:
    """Keep an in-flight mutation attached even when its caller is cancelled."""

    task = asyncio.ensure_future(operation)
    cancellation_requested = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if not cancellation_requested and on_cancel is not None:
                on_cancel()
            cancellation_requested = True
        except Exception:
            break
    return task.result(), cancellation_requested


TOOL_NAMES = [
    "capabilities_get",
    "simulator_status",
    "simulator_connect",
    "simulator_disconnect",
    "simulation_control",
    "environment_get",
    "environment_set",
    "traffic_control",
    "scenario_list",
    "scenario_load",
    "scenario_create",
    "scenario_control",
    "vehicle_list",
    "vehicle_state",
    "vehicle_spawn",
    "vehicle_remove",
    "vehicle_control",
    "vehicle_teleport",
    "vehicle_ai_configure",
    "sensor_attach",
    "sensor_poll",
    "sensor_remove",
    "map_road_network",
    "map_road_edges",
    "map_object_list",
    "map_object_get",
    "map_object_create",
    "map_object_update",
    "map_object_delete",
    "map_save",
    "lua_bridge_status",
    "lua_extension_reload",
    "mod_scaffold",
    "mod_file_list",
    "mod_file_read",
    "mod_file_write",
    "mod_validate",
    "mod_pack",
    "mod_install",
    "mod_test_start",
    "softbody_handoff_create",
    "softbody_handoff_validate",
    "softbody_mod_build",
    "softbody_mod_validate",
    "job_get",
    "job_list",
    "job_cancel",
    "autonomy_start",
    "autonomy_stop",
    "autonomy_status",
    "emergency_stop",
]


class Runtime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.installation: Installation = detect_installation(settings)
        if self.settings.beamng.home is None and self.installation.home is not None:
            self.settings.beamng.home = self.installation.home
        if self.settings.beamng.user is None:
            self.settings.beamng.user = self.installation.user
        if self.settings.lua.token is None:
            self.settings.lua.token = discover_lua_token(self.installation.user)
        assert self.settings.workspace.artifacts is not None
        self.simulator = BeamNGpyAdapter(
            self.settings.beamng,
            self.settings.workspace.artifacts.expanduser().resolve(),
            extensions=["beamng_mcp/bridge"] if self.settings.lua.token is not None else None,
        )
        self.lua = LuaBridgeClient(self.settings.lua)
        self.mods = ModWorkspace(self.settings.workspace)
        self.structural = StructuralModService(self.mods)
        self.jobs = JobManager()
        self._lease_task: asyncio.Task[None] | None = None
        self._lease_id: str | None = None
        self._lease_vehicle_name: str | None = None
        self._lease_engine_armed = False
        self._lease_control_authorized = False
        self._lease_expires_monotonic: float | None = None
        self._lease_last_renewal_monotonic: float | None = None
        self._lease_last_error: str | None = None
        self._autonomy_start_generation = 0
        self._autonomy_start_pending = False
        self._autonomy_start_done = asyncio.Event()
        self._autonomy_start_done.set()
        self._autonomy_lifecycle_blockers = 0
        self._runtime_shutting_down = False
        self._autonomy_transition_lock = asyncio.Lock()
        self.autonomy = AutonomyService(
            self.simulator,
            self.settings.vision,
            control_authorized=self._engine_lease_control_is_authorized,
        )

    async def __aenter__(self) -> Runtime:
        self.mods.ensure()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.shutdown()

    async def shutdown(self) -> None:
        # Latch before the first await so a queued start cannot slip between
        # cancellation of an existing start and component teardown.
        self._runtime_shutting_down = True
        self._invalidate_pending_autonomy_start()
        _, cancellation_requested = await _await_to_completion(self._shutdown_impl())
        if cancellation_requested:
            raise asyncio.CancelledError

    async def _shutdown_impl(self) -> None:
        await self._wait_for_pending_autonomy_start()
        failures: list[str] = []

        # Revoke control and stop lease renewal before potentially waiting for a
        # long, non-cancellable static validation/pack job. Install mutations
        # cannot coexist with active autonomy because they share this lock.
        if self.autonomy.running or self._lease_engine_armed:
            async with self._autonomy_transition_lock:
                try:
                    await self._autonomy_stop_unlocked(reason="server_shutdown")
                except Exception as exc:
                    failures.append(f"autonomy pre-stop: {type(exc).__name__}: {exc}")

        # Stop/join jobs first. A job already holding the transition lock is
        # allowed to finish its non-cancellable mutation; a job that has not yet
        # entered the lock observes the shutdown latch and fails before mutation.
        try:
            await self.jobs.shutdown()
        except Exception as exc:
            failures.append(f"jobs: {type(exc).__name__}: {exc}")

        async with self._autonomy_transition_lock:
            try:
                if self.autonomy.running or self._lease_engine_armed:
                    await self._autonomy_stop_unlocked(reason="server_shutdown")
                else:
                    await self._stop_lease_renewal()
                    await self.autonomy.shutdown()
            except Exception as exc:
                failures.append(f"autonomy: {type(exc).__name__}: {exc}")
            for label, cleanup in (
                ("Lua bridge", self.lua.close),
                ("BeamNGpy", self.simulator.shutdown),
            ):
                try:
                    await cleanup()
                except Exception as exc:
                    failures.append(f"{label}: {type(exc).__name__}: {exc}")
        if failures:
            raise SafetyInterlockError("Runtime shutdown incomplete: " + "; ".join(failures))

    async def capabilities(self) -> CapabilitySnapshot:
        simulator_status = await self.simulator.status()
        lua_status = self.lua.status()
        if simulator_status.connected:
            mode: Literal["offline", "drive", "tech"] = (
                "tech" if simulator_status.tech_enabled else "drive"
            )
        elif lua_status.connected:
            mode = "drive"
        else:
            mode = "offline"
        limitations: list[str] = []
        if mode != "tech":
            limitations.append(
                "BeamNGpy is officially supported only with BeamNG.tech; "
                "retail Drive support is experimental"
            )
        if not simulator_status.connected:
            limitations.append("BeamNGpy tools require simulator_connect")
        if not lua_status.connected:
            limitations.append("Live map mutations require the installed and loaded GELua bridge")
        if not self.settings.workspace.allow_persistent_map_edits:
            limitations.append("Persistent level saves are disabled by configuration")
        limitations.extend(
            [
                "BeamNG 0.38 acknowledges map-save requests but does not provide a durable-save "
                "confirmation to the bridge",
                "vehicle_control is an explicit one-shot input outside the engine deadman and "
                "can remain latched until another control command",
                "mod_test_start validates, packs, and optionally installs; it does not launch "
                "BeamNG or prove that a mod executes correctly",
                "softbody static validation proves coordinate/topology/package integrity, not "
                "in-game stability or actuator behavior",
                "BeamNG 0.38 flexbody runtime assets require Collada DAE; glTF handoffs are "
                "diagnostic only",
                "Blender MCP execute-code is a full-trust local boundary; structural handoffs "
                "prove consistency, not cryptographic Blender execution attestation",
                "softbody authoring v1 supports one connected cage and cannot assemble "
                "disconnected multi-body mechanisms",
            ]
        )
        return CapabilitySnapshot(
            server_version=__version__,
            mode=mode,
            beamngpy_connected=simulator_status.connected,
            lua_connected=lua_status.connected,
            beamngpy_officially_supported=bool(simulator_status.tech_enabled),
            tools=TOOL_NAMES,
            limitations=limitations,
        )

    def _engine_lease_control_is_authorized(self) -> bool:
        deadline = self._lease_expires_monotonic
        return (
            self._lease_engine_armed
            and self._lease_control_authorized
            and deadline is not None
            and time.monotonic() < deadline - 0.02
        )

    def _invalidate_pending_autonomy_start(self) -> None:
        self._autonomy_start_generation = getattr(self, "_autonomy_start_generation", 0) + 1

    def _autonomy_start_is_current(self, generation: int) -> bool:
        return generation == getattr(self, "_autonomy_start_generation", 0)

    async def _wait_for_pending_autonomy_start(self) -> None:
        done = getattr(self, "_autonomy_start_done", None)
        if done is not None and not done.is_set():
            await done.wait()

    def _begin_autonomy_lifecycle_transition(self) -> None:
        self._autonomy_lifecycle_blockers = getattr(self, "_autonomy_lifecycle_blockers", 0) + 1

    def _end_autonomy_lifecycle_transition(self) -> None:
        blockers = getattr(self, "_autonomy_lifecycle_blockers", 0)
        self._autonomy_lifecycle_blockers = max(0, blockers - 1)

    def _autonomy_transition_active(self) -> bool:
        return (
            self.autonomy.running
            or self._lease_engine_armed
            or self._autonomy_start_pending
            or getattr(self, "_autonomy_lifecycle_blockers", 0) > 0
            or getattr(self, "_runtime_shutting_down", False)
        )

    async def while_autonomy_inactive(
        self,
        operation: str,
        callback: Callable[[], Awaitable[T]],
    ) -> T:
        """Serialize a run-invalidating mutation with autonomy lifecycle transitions."""

        async with self._autonomy_transition_lock:
            if self._autonomy_transition_active():
                raise SafetyInterlockError(
                    f"Cannot {operation} while autonomy is starting, running, or fail-closed; "
                    "call autonomy_stop first"
                )
            result, cancellation_requested = await _await_to_completion(callback())
            if cancellation_requested:
                raise asyncio.CancelledError
            return result

    def _set_lease_deadline(
        self,
        response: dict[str, Any],
        *,
        request_started: float,
        renewed: bool,
    ) -> None:
        if response.get("armed") is not True:
            raise SafetyInterlockError("GELua did not confirm that the safety lease is armed")
        response_lease_id = response.get("lease_id")
        if response_lease_id != self._lease_id:
            raise SafetyInterlockError("GELua safety lease response did not match this run")
        expires_in = response.get("expires_in_seconds")
        if not isinstance(expires_in, (int, float)) or not 0.25 <= float(expires_in) <= 5.0:
            raise SafetyInterlockError("GELua returned an invalid safety lease expiry")
        now = time.monotonic()
        self._lease_engine_armed = True
        self._lease_control_authorized = True
        # The engine's countdown starts no later than request receipt. Anchoring to
        # request send time is conservative and never adds WebSocket RTT to the lease.
        self._lease_expires_monotonic = request_started + float(expires_in)
        if renewed:
            self._lease_last_renewal_monotonic = now
        self._lease_last_error = None

    async def _arm_engine_lease(self, spec: AutonomyStart) -> None:
        if self.settings.lua.token is None:
            raise SafetyInterlockError(
                "Autonomy requires the authenticated GELua engine safety lease"
            )
        self._lease_id = uuid.uuid4().hex
        self._lease_vehicle_name = spec.vehicle_id
        try:
            request_started = time.monotonic()
            response = await self.lua.call(
                "safety.lease_arm",
                {"lease_id": self._lease_id, "vehicle_name": spec.vehicle_id},
            )
            self._set_lease_deadline(
                response,
                request_started=request_started,
                renewed=False,
            )
        except Exception:
            self._lease_control_authorized = False
            self._lease_engine_armed = False
            self._lease_expires_monotonic = None
            self._lease_id = None
            self._lease_vehicle_name = None
            raise

    async def _renew_engine_lease(self) -> None:
        lease_id = self._lease_id
        if lease_id is None:
            raise SafetyInterlockError("No engine safety lease is available to renew")
        request_started = time.monotonic()
        response = await self.lua.call("safety.lease_renew", {"lease_id": lease_id})
        self._set_lease_deadline(
            response,
            request_started=request_started,
            renewed=True,
        )

    async def _require_native_ai_heartbeat(self) -> None:
        vehicle_name = self._lease_vehicle_name
        if vehicle_name is None:
            raise SafetyInterlockError("Native-AI heartbeat has no target vehicle")
        timeout = max(
            0.05,
            min(self.settings.lua.safety_lease_seconds * 0.4, 0.5),
        )
        try:
            async with asyncio.timeout(timeout):
                state = await self.simulator.vehicle_state(vehicle_name)
        except TimeoutError as exc:
            raise SafetyInterlockError(
                f"BeamNGpy vehicle-state heartbeat exceeded {timeout:g} seconds"
            ) from exc
        except Exception as exc:
            raise SafetyInterlockError(
                f"BeamNGpy vehicle-state heartbeat failed: {type(exc).__name__}: {exc}"
            ) from exc
        if state.vehicle_id != vehicle_name:
            raise SafetyInterlockError("BeamNGpy vehicle-state heartbeat target mismatch")

    async def _disarm_engine_lease(self) -> None:
        lease_id = self._lease_id
        if lease_id is None:
            return
        response = await self.lua.call("safety.lease_disarm", {"lease_id": lease_id})
        if response.get("armed") is not False:
            raise SafetyInterlockError("GELua did not confirm safety lease disarm")
        self._lease_engine_armed = False
        self._lease_control_authorized = False
        self._lease_expires_monotonic = None
        self._lease_id = None
        self._lease_vehicle_name = None

    async def _lua_stop_autonomy_vehicle(self) -> None:
        params: dict[str, Any] = {}
        if self._lease_vehicle_name is not None:
            params["vehicle_name"] = self._lease_vehicle_name
        response = await self.lua.call("emergency_stop", params)
        if response.get("stopped") is not True:
            raise SafetyInterlockError("GELua did not confirm the emergency stop")

    async def _stop_lease_renewal(self) -> None:
        task = getattr(self, "_lease_task", None)
        self._lease_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _handle_lease_failure(self, message: str) -> None:
        self._lease_last_error = message
        self._lease_control_authorized = False
        failures: list[str] = []
        if self.autonomy.running:
            try:
                await self.autonomy.stop(reason="engine_deadman_failure")
            except Exception as exc:
                failures.append(f"local stop: {type(exc).__name__}: {exc}")
        try:
            await self.simulator.emergency_stop(self._lease_vehicle_name)
        except Exception as exc:
            failures.append(f"BeamNGpy stop: {type(exc).__name__}: {exc}")
        lua_stopped = False
        try:
            await self._lua_stop_autonomy_vehicle()
            lua_stopped = True
        except Exception as exc:
            failures.append(f"Lua stop: {type(exc).__name__}: {exc}")
        if lua_stopped:
            try:
                await self._disarm_engine_lease()
            except Exception as exc:
                failures.append(f"lease disarm: {type(exc).__name__}: {exc}")
        if failures:
            self._lease_last_error = message + "; " + "; ".join(failures)

    async def _lease_renewal_loop(self, mode: str) -> None:
        interval = max(0.05, min(self.settings.lua.safety_lease_seconds / 3.0, 0.5))
        try:
            while self._lease_id is not None:
                await asyncio.sleep(interval)
                if not self.autonomy.running:
                    await self._handle_lease_failure(
                        "Autonomy stopped while engine lease was armed"
                    )
                    return
                deadline = self._lease_expires_monotonic
                if deadline is None:
                    await self._handle_lease_failure("Engine safety lease deadline is unavailable")
                    return
                if mode == "native-ai":
                    eligible = True
                else:
                    eligible = self.autonomy.has_recent_successful_control(
                        self.settings.lua.safety_lease_seconds * 0.75
                    )
                if not eligible:
                    if time.monotonic() >= deadline - 0.05:
                        await self._handle_lease_failure(
                            "No recent successful BeamNG control before engine lease expiry"
                        )
                        return
                    continue
                try:
                    if mode == "native-ai":
                        await self._require_native_ai_heartbeat()
                    await self._renew_engine_lease()
                except Exception as exc:
                    await self._handle_lease_failure(
                        f"Engine safety lease renewal failed: {type(exc).__name__}: {exc}"
                    )
                    return
        except asyncio.CancelledError:
            raise
        finally:
            if self._lease_task is asyncio.current_task():
                self._lease_task = None

    def autonomy_status(self) -> AutonomyStatus:
        status = self.autonomy.status()
        now = time.monotonic()
        deadline = self._lease_expires_monotonic
        renewed = self._lease_last_renewal_monotonic
        return status.model_copy(
            update={
                "engine_deadman_armed": self._lease_engine_armed,
                "engine_deadman_control_authorized": self._engine_lease_control_is_authorized(),
                "engine_deadman_lease_seconds": self.settings.lua.safety_lease_seconds,
                "engine_deadman_expires_in_ms": (
                    max(0.0, deadline - now) * 1000.0 if deadline is not None else None
                ),
                "engine_deadman_last_renewal_age_ms": (
                    max(0.0, now - renewed) * 1000.0 if renewed is not None else None
                ),
                "engine_deadman_last_error": self._lease_last_error,
            }
        )

    async def autonomy_start(self, spec: AutonomyStart) -> AutonomyStatus:
        cancellation_blocked = False

        def cancel_transition() -> None:
            nonlocal cancellation_blocked
            if cancellation_blocked:
                return
            self._begin_autonomy_lifecycle_transition()
            self._invalidate_pending_autonomy_start()
            cancellation_blocked = True

        try:
            try:
                status, cancellation_requested = await _await_to_completion(
                    self._autonomy_start_impl(spec),
                    on_cancel=cancel_transition,
                )
            except Exception:
                if cancellation_blocked:
                    raise asyncio.CancelledError from None
                raise
            if not cancellation_requested:
                return status

            # The inner transition normally observes the generation invalidation
            # before arming. If cancellation landed after its final await, stop the
            # now-complete run before propagating cancellation to the MCP transport.
            if self.autonomy.running or self._lease_engine_armed:
                await _await_to_completion(self.autonomy_stop(reason="start_request_cancelled"))
            raise asyncio.CancelledError
        finally:
            if cancellation_blocked:
                self._end_autonomy_lifecycle_transition()

    async def _autonomy_start_impl(self, spec: AutonomyStart) -> AutonomyStatus:
        async with self._autonomy_transition_lock:
            if self._autonomy_transition_active():
                raise SafetyInterlockError("Autonomy or its engine safety lease is already active")
            if any(
                job.kind == "mod_install_test" and job.status in {"pending", "running"}
                for job in self.jobs.list(self.jobs.max_jobs)
            ):
                raise SafetyInterlockError(
                    "Autonomy cannot start while a mod installation job can mutate the game"
                )
            self._autonomy_start_pending = True
            self._autonomy_start_done.clear()
            self._invalidate_pending_autonomy_start()
            generation = self._autonomy_start_generation
        try:
            try:
                await self.autonomy.prepare(spec)
            except Exception as exc:
                self._lease_last_error = f"Autonomy preparation failed: {type(exc).__name__}: {exc}"
                with contextlib.suppress(Exception):
                    await self.simulator.emergency_stop(spec.vehicle_id)
                raise SafetyInterlockError(self._lease_last_error) from exc
            async with self._autonomy_transition_lock:
                if not self._autonomy_start_is_current(generation):
                    self.autonomy.discard_prepared()
                    raise SafetyInterlockError(
                        "Autonomy start was cancelled before the engine lease was armed"
                    )
                try:
                    await self._arm_engine_lease(spec)
                except Exception as exc:
                    self._lease_last_error = (
                        f"Engine safety lease arm failed: {type(exc).__name__}: {exc}"
                    )
                    with contextlib.suppress(Exception):
                        await self.simulator.emergency_stop(spec.vehicle_id)
                    with contextlib.suppress(Exception):
                        await self.lua.call("emergency_stop", {"vehicle_name": spec.vehicle_id})
                    raise SafetyInterlockError(self._lease_last_error) from exc
                if not self._autonomy_start_is_current(generation):
                    await self._handle_lease_failure(
                        "Autonomy start was cancelled after the engine lease was armed"
                    )
                    raise SafetyInterlockError(self._lease_last_error or "Autonomy start cancelled")
                try:
                    await self.autonomy.start(spec)
                    if not self._autonomy_start_is_current(generation):
                        raise SafetyInterlockError("Autonomy start was cancelled during setup")
                    if spec.mode == "native-ai":
                        await self._require_native_ai_heartbeat()
                        await self._renew_engine_lease()
                    if not self._autonomy_start_is_current(generation):
                        raise SafetyInterlockError(
                            "Autonomy start was cancelled before lease renewal began"
                        )
                except Exception as exc:
                    await self._handle_lease_failure(
                        f"Autonomy start failed after lease arm: {type(exc).__name__}: {exc}"
                    )
                    raise SafetyInterlockError(self._lease_last_error or str(exc)) from exc
                self._lease_task = asyncio.create_task(
                    self._lease_renewal_loop(spec.mode),
                    name=f"engine-safety-lease-{spec.vehicle_id}",
                )
                return self.autonomy_status()
        finally:
            async with self._autonomy_transition_lock:
                self._autonomy_start_pending = False
                self._autonomy_start_done.set()

    async def autonomy_stop(self, *, reason: str = "operator_stop") -> AutonomyStatus:
        self._begin_autonomy_lifecycle_transition()
        try:
            self._invalidate_pending_autonomy_start()
            try:
                async with self._autonomy_transition_lock:
                    stopped = await self._autonomy_stop_unlocked(reason=reason)
            finally:
                await self._wait_for_pending_autonomy_start()
            return stopped
        finally:
            self._end_autonomy_lifecycle_transition()

    async def _autonomy_stop_unlocked(self, *, reason: str) -> AutonomyStatus:
        await self._stop_lease_renewal()
        self._lease_control_authorized = False
        failures: list[str] = []
        try:
            stopped = await self.autonomy.stop(reason=reason)
        except Exception as exc:
            failures.append(f"local stop: {type(exc).__name__}: {exc}")
            stopped = self.autonomy.status()
        lua_stopped = False
        try:
            await self._lua_stop_autonomy_vehicle()
            lua_stopped = True
        except Exception as exc:
            failures.append(f"Lua stop: {type(exc).__name__}: {exc}")
        if lua_stopped:
            try:
                await self._disarm_engine_lease()
            except Exception as exc:
                failures.append(f"lease disarm: {type(exc).__name__}: {exc}")
        if failures:
            self._lease_last_error = "; ".join(failures)
            raise SafetyInterlockError("Autonomy stop incomplete: " + self._lease_last_error)
        self._lease_last_error = None
        return stopped.model_copy(
            update={
                "engine_deadman_armed": False,
                "engine_deadman_control_authorized": False,
                "engine_deadman_lease_seconds": self.settings.lua.safety_lease_seconds,
            }
        )

    async def simulator_disconnect(self) -> OperationResult:
        self._begin_autonomy_lifecycle_transition()
        try:
            self._invalidate_pending_autonomy_start()
            await self._wait_for_pending_autonomy_start()
            warnings: list[str] = []
            async with self._autonomy_transition_lock:
                if self.autonomy.running or self._lease_engine_armed:
                    try:
                        await self._autonomy_stop_unlocked(reason="simulator_disconnect")
                    except Exception as exc:
                        warnings.append(f"autonomy stop: {type(exc).__name__}: {exc}")
                try:
                    await self.simulator.disconnect()
                except Exception as exc:
                    warnings.append(f"disconnect: {type(exc).__name__}: {exc}")
            return OperationResult(
                ok=not warnings,
                message=(
                    "BeamNGpy disconnected"
                    if not warnings
                    else "Simulator disconnect completed with safety warnings"
                ),
                data={"warnings": warnings},
            )
        finally:
            self._end_autonomy_lifecycle_transition()

    async def map_list_objects(
        self, *, class_name: str | None = None, name_prefix: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        return await self.lua.call(
            "world.list_objects",
            {"class": class_name, "name_prefix": name_prefix, "limit": limit},
        )

    async def map_get_object(self, object_id: str | int) -> dict[str, Any]:
        params = {"id": object_id} if isinstance(object_id, int) else {"name": object_id}
        return await self.lua.call("world.get_object", params)

    async def map_create_object(self, mutation: MapObjectMutation) -> dict[str, Any]:
        params = mutation.model_dump(mode="json")
        params["class"] = params.pop("class_name")
        return await self.lua.call("world.create_object", params)

    async def _preflight_map_object_mutation(self, object_id: str | int) -> None:
        if self.settings.workspace.allow_existing_map_object_edits:
            return
        descriptor = await self.map_get_object(object_id)
        if descriptor.get("managed") is not True:
            raise SafetyInterlockError(
                "Editing an existing map object requires "
                "workspace.allow_existing_map_object_edits=true and Lua bridge reinstallation"
            )

    async def map_update_object(self, patch: MapObjectPatch) -> dict[str, Any]:
        await self._preflight_map_object_mutation(patch.object_id)
        params = patch.model_dump(mode="json", exclude_none=True)
        object_id = params.pop("object_id")
        params["id" if isinstance(object_id, int) else "name"] = object_id
        return await self.lua.call("world.update_object", params)

    async def map_delete_object(self, object_id: str | int, *, confirm: bool) -> dict[str, Any]:
        if not confirm:
            raise SafetyInterlockError("Deletion requires confirm=true")
        await self._preflight_map_object_mutation(object_id)
        params: dict[str, Any] = {"confirm": True}
        params["id" if isinstance(object_id, int) else "name"] = object_id
        return await self.lua.call("world.delete_object", params)

    async def map_save(self, *, level: str | None, confirm: bool) -> dict[str, Any]:
        if not self.settings.workspace.allow_persistent_map_edits:
            raise SafetyInterlockError(
                "Persistent map edits are disabled; enable workspace.allow_persistent_map_edits "
                "and reinstall/reconfigure the Lua bridge"
            )
        if not confirm:
            raise SafetyInterlockError("Saving a level requires confirm=true")
        if not isinstance(level, str) or not level:
            raise SafetyInterlockError("Saving a level requires the exact loaded level identifier")
        snapshot = await self.lua.call("telemetry.snapshot", {})
        loaded_level = snapshot.get("level")
        if not isinstance(loaded_level, str) or level != loaded_level:
            raise SafetyInterlockError(
                f"Confirmed level {level!r} does not match the loaded level {loaded_level!r}"
            )
        return await self.lua.call("world.save_level", {"level": level, "confirm": True})

    async def reload_lua_extension(self, name: str) -> dict[str, Any]:
        response = await self.lua.call("extension.reload", {"name": name})
        if response.get("scheduled") is not True:
            raise SafetyInterlockError("GELua did not confirm that extension reload was scheduled")

        # Reload happens after the bridge sends its response. Drop the old client,
        # allow at least one game tick, and keep the mutation lock until a freshly
        # authenticated bridge is reachable again.
        await self.lua.close()
        await asyncio.sleep(0.1)
        deadline = time.monotonic() + min(
            max(self.settings.lua.request_timeout_seconds * 2.0, 1.0), 10.0
        )
        status = await self.lua.probe()
        while not (status.connected and status.authenticated) and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
            status = await self.lua.probe()
        if not (status.connected and status.authenticated):
            raise SafetyInterlockError(
                "GELua reload was scheduled but the authenticated bridge did not return"
            )
        return {
            **response,
            "bridge_ready": True,
            "bridge_version": status.bridge_version,
            "game_version": status.game_version,
        }

    async def emergency_stop(self, vehicle_id: str | None = None) -> OperationResult:
        self._begin_autonomy_lifecycle_transition()
        self._invalidate_pending_autonomy_start()
        cancellation_requested = False
        try:
            result, cancellation_requested = await _await_to_completion(
                self._emergency_stop_impl(vehicle_id)
            )
        finally:
            # A still-pending start remains an interlock by itself and must observe
            # the stale generation before it can arm. Do not make emergency response
            # latency depend on a cold or wedged model warmup.
            self._end_autonomy_lifecycle_transition()
        if cancellation_requested:
            raise asyncio.CancelledError
        return result

    async def _emergency_stop_impl(self, vehicle_id: str | None = None) -> OperationResult:
        await self._stop_lease_renewal()
        self._lease_control_authorized = False

        async def stop_autonomy() -> str:
            await self.autonomy.emergency_stop("mcp_emergency_stop")
            return "applied"

        async def stop_beamngpy() -> str:
            if not (await self.simulator.status()).connected:
                return "not_connected"
            await self.simulator.emergency_stop(vehicle_id)
            return "applied"

        async def stop_lua() -> str:
            params: dict[str, Any] = {}
            if vehicle_id is not None:
                params["vehicle_name"] = vehicle_id
            # LuaBridgeClient.call connects on demand. Do not require an already-open
            # socket here: that would disable an independent emergency control path.
            response = await self.lua.call("emergency_stop", params)
            if response.get("stopped") is not True:
                raise SafetyInterlockError("GELua did not confirm the emergency stop")
            return "applied"

        stop_timeout = min(self.settings.lua.request_timeout_seconds, 5.0)

        async def attempt(operation: Awaitable[str]) -> dict[str, Any]:
            try:
                async with asyncio.timeout(stop_timeout):
                    status = await operation
                return {"status": status}
            except TimeoutError:
                return {
                    "status": "timeout",
                    "error": f"operation exceeded {stop_timeout:g} seconds",
                }
            except Exception as exc:
                return {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }

        operations: dict[str, Awaitable[str]] = {}
        outcomes: dict[str, dict[str, Any]] = {}
        if self.autonomy.running:
            operations["autonomy"] = stop_autonomy()
        else:
            outcomes["autonomy"] = {"status": "not_running"}
        operations["beamngpy"] = stop_beamngpy()
        if self.lua.connected or self.settings.lua.token is not None:
            operations["lua"] = stop_lua()
        else:
            outcomes["lua"] = {"status": "not_configured"}

        tasks = {
            path: asyncio.create_task(attempt(operation), name=f"emergency-stop-{path}")
            for path, operation in operations.items()
        }
        if tasks:
            results = await asyncio.gather(*tasks.values())
            outcomes.update(zip(tasks, results, strict=True))

        # Disarming is intentionally sequenced after the independent GELua brake
        # attempt. If either call fails, the engine lease remains fail-closed and
        # expires into another full-brake command.
        lua_stop_applied = outcomes.get("lua", {}).get("status") == "applied"
        if getattr(self, "_lease_id", None) is not None and lua_stop_applied:

            async def disarm() -> str:
                await self._disarm_engine_lease()
                return "disarmed"

            outcomes["engine_deadman"] = await attempt(disarm())
        elif getattr(self, "_lease_id", None) is not None:
            outcomes["engine_deadman"] = {
                "status": "failed",
                "error": "Lua stop did not succeed; lease left armed to expire",
                "fail_closed": True,
            }
        else:
            outcomes["engine_deadman"] = {"status": "not_armed"}

        stopped = [path for path, outcome in outcomes.items() if outcome["status"] == "applied"]
        errors = [
            f"{path}: {outcome['error']}"
            for path, outcome in outcomes.items()
            if outcome["status"] in {"failed", "timeout"}
        ]
        if errors:
            self._lease_last_error = "; ".join(errors)
        if stopped:
            message = "Emergency stop applied through " + ", ".join(stopped)
            if errors:
                message += "; one or more control paths failed"
        else:
            message = "Emergency stop was not applied by any control path"
        return OperationResult(
            ok=bool(stopped) and not errors,
            message=message,
            data={"paths": stopped, "outcomes": outcomes, "warnings": errors},
        )

    async def start_mod_test(
        self,
        mod_name: str,
        *,
        pack: bool = True,
        install: bool = False,
        overwrite: bool = False,
    ) -> JobInfo:
        if overwrite and not install:
            raise ValueError("overwrite=true requires install=true")

        async def worker(context: JobContext) -> dict[str, Any]:
            await context.set_stage("validating", cancellable=False)
            await context.progress(0.1)
            validation = await asyncio.to_thread(self.mods.validate, mod_name)
            await context.set_stage("validation_complete", cancellable=True)
            if not validation.valid:
                return {"validation": validation.model_dump(mode="json"), "packed": None}

            artifact = None
            if pack:
                await context.set_stage("packing", cancellable=False)
                await context.progress(0.5)
                artifact = await asyncio.to_thread(self.mods.pack, mod_name)
                await context.set_stage("pack_complete", cancellable=True)

            await context.progress(0.75)
            installed = None
            if install:
                await context.set_stage("installing", cancellable=False)
                installed = await self.while_autonomy_inactive(
                    "install a tested mod into the active BeamNG user folder",
                    lambda: asyncio.to_thread(
                        self.mods.install,
                        mod_name,
                        self.installation.user,
                        overwrite=overwrite,
                    ),
                )
                await context.set_stage("install_complete", cancellable=True)

            await context.set_stage("finalizing", cancellable=True)
            await context.progress(0.95)
            return {
                "validation": validation.model_dump(mode="json"),
                "packed": artifact.model_dump(mode="json") if artifact else None,
                "installed": installed.model_dump(mode="json") if installed else None,
            }

        if not install:
            return await self.jobs.start("mod_test", worker)
        async with self._autonomy_transition_lock:
            if self._autonomy_transition_active():
                raise SafetyInterlockError(
                    "Cannot start a mod installation job while autonomy is active; "
                    "call autonomy_stop first"
                )
            return await self.jobs.start("mod_install_test", worker)
