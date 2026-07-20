"""Runtime and MCP integration tests for truthful staged jobs."""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import AnyUrl

from beamng_mcp.config import Settings
from beamng_mcp.errors import ConflictError
from beamng_mcp.mcp_adapter import create_mcp_server
from beamng_mcp.models import JobInfo, ModArtifact, ModValidation
from beamng_mcp.runtime import Runtime
from beamng_mcp.services.jobs import JobManager


async def _wait_for_thread_event(event: threading.Event) -> None:
    assert await asyncio.to_thread(event.wait, 2), "worker thread did not reach expected stage"


async def _wait_for_terminal(manager: JobManager, job_id: str) -> JobInfo:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 2.0
    while loop.time() < deadline:
        info = manager.get(job_id)
        if info.status not in {"pending", "running"}:
            return info
        await asyncio.sleep(0.005)
    raise AssertionError(f"Job {job_id} did not reach a terminal state")


class BlockingModWork:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.validation_entered = threading.Event()
        self.validation_release = threading.Event()
        self.pack_entered = threading.Event()
        self.pack_release = threading.Event()
        self.install_entered = threading.Event()
        self.install_release = threading.Event()
        self.install_overwrite: bool | None = None

    @staticmethod
    def _block(entered: threading.Event, release: threading.Event) -> None:
        entered.set()
        if not release.wait(2):
            raise TimeoutError("test did not release blocking mod operation")

    def validate(self, mod_name: str) -> ModValidation:
        self._block(self.validation_entered, self.validation_release)
        return ModValidation(valid=True, mod_name=mod_name, files_checked=1)

    def pack(self, mod_name: str) -> ModArtifact:
        self._block(self.pack_entered, self.pack_release)
        return ModArtifact(
            mod_name=mod_name,
            path=str(self.tmp_path / f"{mod_name}.zip"),
            sha256="0" * 64,
            size=1,
        )

    def install(self, mod_name: str, _user: Path, *, overwrite: bool = False) -> ModArtifact:
        self.install_overwrite = overwrite
        self._block(self.install_entered, self.install_release)
        return ModArtifact(
            mod_name=mod_name,
            path=str(self.tmp_path / "installed" / f"{mod_name}.zip"),
            sha256="1" * 64,
            size=1,
        )

    def release_all(self) -> None:
        self.validation_release.set()
        self.pack_release.set()
        self.install_release.set()


def _runtime_for_jobs(mods: object, jobs: JobManager, tmp_path: Path) -> Runtime:
    runtime = object.__new__(Runtime)
    runtime.mods = mods  # type: ignore[assignment]
    runtime.jobs = jobs
    runtime.installation = SimpleNamespace(user=tmp_path / "user")  # type: ignore[assignment]
    runtime.autonomy = SimpleNamespace(running=False)  # type: ignore[assignment]
    runtime._lease_engine_armed = False
    runtime._autonomy_start_pending = False
    runtime._autonomy_transition_lock = asyncio.Lock()
    return runtime


@pytest.mark.asyncio
async def test_mod_test_reports_every_blocking_stage_and_propagates_overwrite(
    tmp_path: Path,
) -> None:
    jobs = JobManager(max_jobs=8, max_concurrent_jobs=2)
    mods = BlockingModWork(tmp_path)
    runtime = _runtime_for_jobs(mods, jobs, tmp_path)
    job = await runtime.start_mod_test("sample", pack=True, install=True, overwrite=True)

    try:
        await _wait_for_thread_event(mods.validation_entered)
        validating = jobs.get(job.job_id)
        assert (validating.stage, validating.cancellable) == ("validating", False)
        with pytest.raises(ConflictError, match="validating"):
            await jobs.cancel(job.job_id)
        mods.validation_release.set()

        await _wait_for_thread_event(mods.pack_entered)
        packing = jobs.get(job.job_id)
        assert (packing.stage, packing.cancellable) == ("packing", False)
        with pytest.raises(ConflictError, match="packing"):
            await jobs.cancel(job.job_id)
        mods.pack_release.set()

        await _wait_for_thread_event(mods.install_entered)
        installing = jobs.get(job.job_id)
        assert (installing.stage, installing.cancellable) == ("installing", False)
        assert mods.install_overwrite is True
        with pytest.raises(ConflictError, match="installing"):
            await jobs.cancel(job.job_id)
        mods.install_release.set()

        finished = await _wait_for_terminal(jobs, job.job_id)
        assert finished.status == "succeeded"
        assert finished.stage == "completed"
        assert finished.cancellable is False
    finally:
        mods.release_all()
        await jobs.shutdown()


class QuickModWork:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.pack_calls = 0
        self.install_overwrite: bool | None = None

    def validate(self, mod_name: str) -> ModValidation:
        return ModValidation(valid=True, mod_name=mod_name, files_checked=1)

    def pack(self, mod_name: str) -> ModArtifact:
        self.pack_calls += 1
        return ModArtifact(
            mod_name=mod_name,
            path=str(self.tmp_path / f"{mod_name}.zip"),
            sha256="2" * 64,
            size=1,
        )

    def install(self, mod_name: str, _user: Path, *, overwrite: bool = False) -> ModArtifact:
        self.install_overwrite = overwrite
        return self.pack(mod_name)


class BoundaryJobManager(JobManager):
    def __init__(self) -> None:
        super().__init__(max_jobs=4, max_concurrent_jobs=2)
        self.boundary_entered = asyncio.Event()
        self.boundary_release = asyncio.Event()

    async def _set_stage(self, job_id: str, stage: str, *, cancellable: bool) -> None:
        await super()._set_stage(job_id, stage, cancellable=cancellable)
        if stage == "validation_complete":
            self.boundary_entered.set()
            await self.boundary_release.wait()


@pytest.mark.asyncio
async def test_mod_test_can_cancel_at_cooperative_boundary(tmp_path: Path) -> None:
    jobs = BoundaryJobManager()
    mods = QuickModWork(tmp_path)
    runtime = _runtime_for_jobs(mods, jobs, tmp_path)
    job = await runtime.start_mod_test("sample")

    await asyncio.wait_for(jobs.boundary_entered.wait(), timeout=2)
    boundary = jobs.get(job.job_id)
    assert (boundary.stage, boundary.cancellable) == ("validation_complete", True)

    cancelled = await jobs.cancel(job.job_id)
    assert cancelled.status == "cancelled"
    assert mods.pack_calls == 0
    await jobs.shutdown()


@pytest.mark.asyncio
async def test_mod_test_overwrite_defaults_off(tmp_path: Path) -> None:
    jobs = JobManager(max_jobs=4, max_concurrent_jobs=2)
    mods = QuickModWork(tmp_path)
    runtime = _runtime_for_jobs(mods, jobs, tmp_path)
    job = await runtime.start_mod_test("sample", install=True)

    try:
        finished = await _wait_for_terminal(jobs, job.job_id)
        assert finished.status == "succeeded"
        assert mods.install_overwrite is False
    finally:
        await jobs.shutdown()


class ResourceJobs:
    def __init__(self, info: JobInfo) -> None:
        self.info = info

    def get(self, _job_id: str) -> JobInfo:
        return self.info


class RecordingRuntime:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.info = JobInfo(
            job_id="job-1",
            kind="mod_test",
            status="running",
            stage="packing",
            cancellable=False,
            created_at=now,
            updated_at=now,
            progress=0.5,
        )
        self.jobs = ResourceJobs(self.info)
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> RecordingRuntime:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def start_mod_test(self, mod_name: str, **kwargs: Any) -> JobInfo:
        self.calls.append({"mod_name": mod_name, **kwargs})
        return self.info


@pytest.mark.asyncio
async def test_mcp_propagates_overwrite_and_exposes_truthful_job_schema(tmp_path: Path) -> None:
    runtime = RecordingRuntime()
    mcp, _ = create_mcp_server(
        Settings(workspace={"root": tmp_path / "workspace"}),
        runtime=runtime,  # type: ignore[arg-type]
    )
    tool = next(tool for tool in await mcp.list_tools() if tool.name == "mod_test_start")
    assert tool.inputSchema["properties"]["overwrite"]["default"] is False
    assert "Current work stage" in tool.outputSchema["properties"]["stage"]["description"]
    assert "job_cancel" in tool.outputSchema["properties"]["cancellable"]["description"]

    async with create_connected_server_and_client_session(mcp) as session:
        result = await session.call_tool(
            "mod_test_start",
            {
                "mod_name": "sample",
                "pack": True,
                "install": True,
                "confirm_install": True,
                "overwrite": True,
            },
        )
        assert result.isError is False
        assert result.structuredContent is not None
        assert result.structuredContent["stage"] == "packing"
        assert result.structuredContent["cancellable"] is False

        resource = await session.read_resource(AnyUrl("beamng://jobs/job-1"))
        payload = json.loads(resource.contents[0].text)  # type: ignore[union-attr]
        assert payload["stage"] == "packing"
        assert payload["cancellable"] is False

    assert runtime.calls == [
        {"mod_name": "sample", "pack": True, "install": True, "overwrite": True}
    ]
