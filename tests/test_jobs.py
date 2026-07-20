"""Job state, capacity, and cancellation truthfulness tests."""

from __future__ import annotations

import asyncio
import threading

import pytest

from beamng_mcp.errors import ConflictError
from beamng_mcp.models import JobInfo
from beamng_mcp.services.jobs import JobContext, JobManager


async def _wait_for_terminal(manager: JobManager, job_id: str) -> JobInfo:
    for _ in range(100):
        info = manager.get(job_id)
        if info.status not in {"pending", "running"}:
            return info
        await asyncio.sleep(0)
    raise AssertionError(f"Job {job_id} did not reach a terminal state")


@pytest.mark.asyncio
async def test_job_stage_metadata_tracks_success() -> None:
    manager = JobManager(max_jobs=4, max_concurrent_jobs=2)

    async def worker(context: JobContext) -> dict[str, object]:
        await context.set_stage("validating", cancellable=True)
        await context.progress(0.5)
        return {"valid": True}

    started = await manager.start("validation", worker)
    assert started.stage == "queued"
    assert started.cancellable is True

    finished = await _wait_for_terminal(manager, started.job_id)
    assert finished.status == "succeeded"
    assert finished.stage == "completed"
    assert finished.cancellable is False
    assert finished.progress == 1.0
    await manager.shutdown()


@pytest.mark.asyncio
async def test_concurrent_job_quota_rejects_excess_work() -> None:
    manager = JobManager(max_jobs=4, max_concurrent_jobs=2)
    release = asyncio.Event()

    async def worker(_context: JobContext) -> dict[str, object]:
        await release.wait()
        return {}

    first = await manager.start("blocked", worker)
    second = await manager.start("blocked", worker)
    with pytest.raises(ConflictError, match=r"concurrent job limit.*wait"):
        await manager.start("overflow", worker)

    release.set()
    await _wait_for_terminal(manager, first.job_id)
    await _wait_for_terminal(manager, second.job_id)
    await manager.shutdown()


@pytest.mark.asyncio
async def test_retained_capacity_rejects_when_no_finished_job_can_be_pruned() -> None:
    manager = JobManager(max_jobs=2, max_concurrent_jobs=2)
    release = asyncio.Event()

    async def worker(_context: JobContext) -> dict[str, object]:
        await release.wait()
        return {}

    first = await manager.start("blocked", worker)
    second = await manager.start("blocked", worker)
    with pytest.raises(ConflictError, match=r"retained capacity.*wait"):
        await manager.start("overflow", worker)

    await manager.cancel(first.job_id)
    await manager.cancel(second.job_id)
    await manager.shutdown()


@pytest.mark.asyncio
async def test_finished_jobs_are_pruned_to_admit_new_work() -> None:
    manager = JobManager(max_jobs=2, max_concurrent_jobs=2)

    async def worker(_context: JobContext) -> dict[str, object]:
        return {}

    first = await manager.start("quick", worker)
    await _wait_for_terminal(manager, first.job_id)
    second = await manager.start("quick", worker)
    await _wait_for_terminal(manager, second.job_id)
    third = await manager.start("quick", worker)

    assert manager.get(third.job_id).status in {"pending", "running", "succeeded"}
    assert len(manager.list(limit=2)) == 2
    await manager.shutdown()


@pytest.mark.asyncio
async def test_cancel_refuses_non_cancellable_stage_then_works_at_cooperative_stage() -> None:
    manager = JobManager(max_jobs=4, max_concurrent_jobs=2)
    blocking_entered = asyncio.Event()
    blocking_release = asyncio.Event()
    cooperative_entered = asyncio.Event()
    cooperative_release = asyncio.Event()

    async def worker(context: JobContext) -> dict[str, object]:
        await context.set_stage("installing", cancellable=False)
        blocking_entered.set()
        await blocking_release.wait()
        await context.set_stage("finalizing", cancellable=True)
        cooperative_entered.set()
        await cooperative_release.wait()
        return {}

    job = await manager.start("staged", worker)
    await asyncio.wait_for(blocking_entered.wait(), timeout=1)

    blocked = manager.get(job.job_id)
    assert blocked.stage == "installing"
    assert blocked.cancellable is False
    with pytest.raises(ConflictError, match=r"installing.*wait.*retry"):
        await manager.cancel(job.job_id)
    assert manager.get(job.job_id).status == "running"

    blocking_release.set()
    await asyncio.wait_for(cooperative_entered.wait(), timeout=1)
    cancelled = await manager.cancel(job.job_id)
    assert cancelled.status == "cancelled"
    assert cancelled.stage == "cancelled"
    assert cancelled.cancellable is False
    await manager.shutdown()


@pytest.mark.asyncio
async def test_shutdown_waits_for_a_non_cancellable_worker_thread() -> None:
    manager = JobManager(max_jobs=4, max_concurrent_jobs=2)
    entered = threading.Event()
    release = threading.Event()
    mutation_finished = threading.Event()

    def blocking_mutation() -> None:
        entered.set()
        assert release.wait(2), "test did not release the blocking mutation"
        mutation_finished.set()

    async def worker(context: JobContext) -> dict[str, object]:
        await context.set_stage("installing", cancellable=False)
        await asyncio.to_thread(blocking_mutation)
        await context.set_stage("install_complete", cancellable=True)
        return {}

    job = await manager.start("threaded", worker)
    assert await asyncio.to_thread(entered.wait, 1)
    shutdown = asyncio.create_task(manager.shutdown())
    try:
        await asyncio.sleep(0.02)
        assert shutdown.done() is False
        assert mutation_finished.is_set() is False
        assert manager.get(job.job_id).stage == "installing"
        shutdown.cancel()
        await asyncio.sleep(0.02)
        assert shutdown.done() is False

        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(shutdown, timeout=1)
        assert mutation_finished.is_set() is True
        finished = manager.get(job.job_id)
        assert finished.status == "cancelled"
        assert finished.stage == "cancelled"
    finally:
        release.set()
        await manager.shutdown()


def test_job_manager_rejects_invalid_capacity_configuration() -> None:
    with pytest.raises(ValueError, match="max_jobs"):
        JobManager(max_jobs=0)
    with pytest.raises(ValueError, match="max_concurrent_jobs"):
        JobManager(max_jobs=2, max_concurrent_jobs=3)
