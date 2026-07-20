"""Small process-level job manager for cancellable mod and simulation work."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..errors import ConflictError, NotFoundError
from ..models import JobInfo


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class JobContext:
    job_id: str
    _manager: JobManager

    async def progress(self, value: float) -> None:
        await self._manager._set_progress(self.job_id, value)

    async def set_stage(self, stage: str, *, cancellable: bool = True) -> None:
        """Publish the current stage before beginning its work."""

        await self._manager._set_stage(self.job_id, stage, cancellable=cancellable)


Worker = Callable[[JobContext], Awaitable[dict[str, Any]]]


class JobManager:
    def __init__(self, max_jobs: int = 128, max_concurrent_jobs: int = 8) -> None:
        if max_jobs < 1:
            raise ValueError("max_jobs must be at least 1")
        if not 1 <= max_concurrent_jobs <= max_jobs:
            raise ValueError("max_concurrent_jobs must be between 1 and max_jobs")
        self.max_jobs = max_jobs
        self.max_concurrent_jobs = max_concurrent_jobs
        self._jobs: dict[str, JobInfo] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._shutdown_started = False

    async def start(self, kind: str, worker: Worker) -> JobInfo:
        job_id = uuid.uuid4().hex
        now = _now()
        info = JobInfo(
            job_id=job_id,
            kind=kind,
            status="pending",
            created_at=now,
            updated_at=now,
            progress=0.0,
        )
        async with self._lock:
            if self._shutdown_started:
                raise ConflictError("The job manager is shutting down and cannot accept new work")
            self._prune()
            if len(self._jobs) >= self.max_jobs:
                raise ConflictError(
                    f"Job history has reached its retained capacity of {self.max_jobs}; "
                    "wait for an active job to finish or cancel a cancellable job"
                )
            active_jobs = sum(job.status in {"pending", "running"} for job in self._jobs.values())
            if active_jobs >= self.max_concurrent_jobs:
                raise ConflictError(
                    f"The concurrent job limit of {self.max_concurrent_jobs} is in use; "
                    "wait for a running job to finish or cancel a cancellable job"
                )
            self._jobs[job_id] = info
            self._tasks[job_id] = asyncio.create_task(
                self._run(job_id, worker), name=f"beamng-job-{job_id[:8]}"
            )
        return info.model_copy(deep=True)

    async def _run(self, job_id: str, worker: Worker) -> None:
        try:
            await self._update(job_id, status="running", stage="running", cancellable=True)
            result = await worker(JobContext(job_id, self))
            await self._update(
                job_id,
                status="succeeded",
                stage="completed",
                cancellable=False,
                progress=1.0,
                result=result,
            )
        except asyncio.CancelledError:
            await self._update(job_id, status="cancelled", stage="cancelled", cancellable=False)
            raise
        except Exception as exc:
            await self._update(
                job_id,
                status="failed",
                stage="failed",
                cancellable=False,
                error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            self._tasks.pop(job_id, None)

    async def _set_progress(self, job_id: str, value: float) -> None:
        current = self._jobs[job_id].progress
        await self._update(job_id, progress=max(current, min(1.0, value)))

    async def _set_stage(self, job_id: str, stage: str, *, cancellable: bool) -> None:
        if not stage or stage != stage.strip() or len(stage) > 128:
            raise ValueError("job stage must be 1 to 128 characters without outer whitespace")
        await self._update(job_id, stage=stage, cancellable=cancellable)
        # A shutdown cannot cancel an asyncio task while it awaits asyncio.to_thread:
        # cancellation would detach the worker thread and let it keep mutating after
        # shutdown returned.  Non-cancellable stages therefore run to a cooperative
        # boundary, where the owning task cancels itself before starting more work.
        if cancellable and self._shutdown_started:
            raise asyncio.CancelledError

    async def _update(self, job_id: str, **values: Any) -> None:
        async with self._lock:
            info = self._jobs[job_id]
            values["updated_at"] = _now()
            self._jobs[job_id] = info.model_copy(update=values)

    def get(self, job_id: str) -> JobInfo:
        info = self._jobs.get(job_id)
        if info is None:
            raise NotFoundError(f"Job {job_id!r} was not found")
        return info.model_copy(deep=True)

    def list(self, limit: int = 50) -> list[JobInfo]:
        if not 1 <= limit <= self.max_jobs:
            raise ValueError(f"limit must be between 1 and {self.max_jobs}")
        ordered = sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)
        return [item.model_copy(deep=True) for item in ordered[:limit]]

    async def cancel(self, job_id: str) -> JobInfo:
        async with self._lock:
            info = self._jobs.get(job_id)
            if info is None:
                raise NotFoundError(f"Job {job_id!r} was not found")
            if info.status not in {"pending", "running"}:
                return info.model_copy(deep=True)
            if not info.cancellable:
                raise ConflictError(
                    f"Job {job_id!r} cannot be cancelled during non-cancellable stage "
                    f"{info.stage!r}; wait for the stage to finish, then retry"
                )
            task = self._tasks.get(job_id)
            if task is not None and not task.done():
                task.cancel()

        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                self._tasks.pop(job_id, None)
        if self._jobs[job_id].status in {"pending", "running"}:
            await self._update(job_id, status="cancelled", stage="cancelled", cancellable=False)
        return self.get(job_id)

    async def shutdown(self) -> None:
        async with self._lock:
            self._shutdown_started = True
            tasks = list(self._tasks.items())
            for job_id, task in tasks:
                info = self._jobs.get(job_id)
                if info is not None and info.cancellable:
                    task.cancel()
        if tasks:
            waiter = asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
            shutdown_cancelled = False
            while not waiter.done():
                try:
                    await asyncio.shield(waiter)
                except asyncio.CancelledError:
                    # Defer propagation until any detached worker thread has reached
                    # its cooperative boundary. Repeated cancellation is handled too.
                    shutdown_cancelled = True
            if shutdown_cancelled:
                raise asyncio.CancelledError

    def _prune(self) -> None:
        if len(self._jobs) < self.max_jobs:
            return
        finished = [
            job
            for job in sorted(self._jobs.values(), key=lambda item: item.updated_at)
            if job.status in {"succeeded", "failed", "cancelled"}
        ]
        while len(self._jobs) >= self.max_jobs and finished:
            old = finished.pop(0)
            self._jobs.pop(old.job_id, None)
