from __future__ import annotations

import os
import subprocess
import threading
import uuid
from contextlib import ExitStack
from pathlib import Path

import pytest
from beamngpy import BeamNGpy, Scenario, Vehicle

from beamng_mcp.config import WorkspaceSettings
from beamng_mcp.services.mods import ModWorkspace
from beamng_mcp.services.structural import StructuralModService
from beamng_mcp.structural_models import (
    AssetStageRequest,
    CoordinateContract,
    MassInputs,
    StructuralBuildRequest,
    StructuralMaterial,
)
from tests.live_support import (
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    require_confined_profile_target,
    reserve_loopback_ports,
)


def _configured_paths() -> tuple[Path, Path, Path, Path]:
    blender_value = os.getenv("BEAMNG_MCP_TEST_BLENDER")
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not all((blender_value, home_value, user_value, binary_value)):
        pytest.skip("configure both Blender and isolated BeamNG live-test environment variables")
    blender = Path(str(blender_value)).resolve()
    home = Path(str(home_value)).resolve()
    user = Path(os.path.abspath(str(user_value)))
    binary = Path(str(binary_value))
    if not blender.is_file():
        pytest.fail(f"configured Blender executable does not exist: {blender}")
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG executable does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("live soft-body tests require an explicitly marked isolated BeamNG user folder")
    return blender, home, user, binary


def test_softbody_path_discovery_preserves_a_linked_profile_for_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blender = tmp_path / "blender.exe"
    blender.touch()
    home = tmp_path / "home"
    home.mkdir()
    binary = home / "BeamNG.drive.x64.exe"
    binary.touch()
    real_user = tmp_path / "real-current"
    real_user.mkdir()
    (real_user / ".beamng-mcp-test-user").touch()
    linked_user = tmp_path / "current"
    try:
        linked_user.symlink_to(real_user, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory links are unavailable on this host: {exc}")
    monkeypatch.setenv("BEAMNG_MCP_TEST_BLENDER", str(blender))
    monkeypatch.setenv("BEAMNG_MCP_TEST_BEAMNG_HOME", str(home))
    monkeypatch.setenv("BEAMNG_MCP_TEST_BEAMNG_USER", str(linked_user))
    monkeypatch.setenv("BEAMNG_MCP_TEST_BEAMNG_BINARY", str(binary))

    _, _, discovered_user, _ = _configured_paths()

    assert discovered_user == Path(os.path.abspath(linked_user))
    assert discovered_user.is_symlink()


@pytest.mark.blender
@pytest.mark.beamng_live
def test_real_blender_ramp_builds_installs_and_loads_in_isolated_beamng(
    tmp_path: Path,
) -> None:
    blender, home, user, binary = _configured_paths()
    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(1))
        (tcom_port,) = reservation.ports
        mods = ModWorkspace(
            WorkspaceSettings(
                root=tmp_path / "workspace",
                allow_mod_install=True,
                max_file_bytes=16 * 1024 * 1024,
            )
        )
        structural = StructuralModService(mods)
        coordinates = CoordinateContract(
            source_origin_world=(0.0, 0.0, 0.0),
            source_world_to_beamng_vehicle=(
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            ),
        )
        stage = structural.create_handoff(
            AssetStageRequest(
                mod_name="live_ramp",
                asset_name="live_ramp",
                visual_object="live_ramp_visual",
                cage_object="live_ramp_physics",
                coordinates=coordinates,
            )
        )
        fixture = Path(__file__).with_name("fixtures") / "blender_structural_ramp.py"
        completed = subprocess.run(  # noqa: S603 - explicitly configured local test binary
            [
                str(blender),
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python",
                str(fixture),
                "--",
                stage.blender_runner_path,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr

        handoff = structural.validate_handoff(stage.slot_id)
        assert handoff.valid is True, handoff.issues
        assert handoff.manifest is not None
        assert handoff.manifest.measured_volume_m3 == pytest.approx(6.0)
        build = structural.build(
            StructuralBuildRequest(
                slot_id=stage.slot_id,
                mod_name="live_ramp",
                asset_name="live_ramp",
                title="BeamNG MCP Live Concrete Ramp",
                author="beamng-mcp integration test",
                material=StructuralMaterial(
                    preset="concrete",
                    material_id="live_ramp_material",
                    base_color=(0.45, 0.47, 0.5, 1.0),
                    roughness=0.9,
                ),
                mass=MassInputs(closed_volume_m3=handoff.manifest.measured_volume_m3),
                grounded=True,
                fixed=True,
            )
        )
        assert build.total_mass_kg == pytest.approx(14_400.0)
        assert structural.validate_mod("live_ramp", "live_ramp").valid is True
        mods.pack("live_ramp")
        installed_path: Path | None = None
        bng: BeamNGpy | None = None
        scenario: Scenario | None = None
        scenario_directory: Path | None = None
        owned_process: object | None = None
        timer: threading.Timer | None = None
        try:
            installed = mods.install("live_ramp", user)
            installed_path = Path(installed.path)
            launch_user = user.parent if user.name.casefold() == "current" else user
            bng = BeamNGpy(
                "127.0.0.1",
                tcom_port,
                home=str(home),
                binary=str(binary),
                user=str(launch_user),
                quit_on_close=False,
                headless=True,
                nogpu=True,
            )

            def watchdog() -> None:
                if bng is not None:
                    process = bng.process
                    if process is not None and process.poll() is None:
                        process.terminate()

            timer = threading.Timer(180.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)
            scenario = Scenario("gridmap_v2", f"live_ramp_{uuid.uuid4().hex[:12]}")
            scenario_directory = require_confined_profile_target(
                user,
                Path("levels") / "gridmap_v2" / "scenarios" / scenario.name,
            )
            ramp = Vehicle("ramp", "live_ramp", license="MCPRAMP")
            scenario.add_vehicle(ramp, pos=(0.0, 0.0, 0.1), cling=True)
            scenario.make(bng)
            bng.control.pause()
            bng.scenario.load(scenario, precompile_shaders=False)
            bng.scenario.start()
            assert ramp.is_connected() is True
            bng.control.pause()
            bng.control.step(3, wait=True)
            ramp.sensors.poll("state")
            state = ramp.sensors.data["state"]
            assert len(state["pos"]) == 3
        finally:
            try:
                if bng is not None:
                    cleanup_owned_beamng_session(
                        bng,
                        owned_process=owned_process,
                        scenario=scenario,
                    )
            finally:
                if timer is not None:
                    timer.cancel()
                cleanup_exact_live_artifacts(
                    profile=user,
                    files=(installed_path,) if installed_path is not None else (),
                    empty_directories=(scenario_directory,)
                    if scenario_directory is not None
                    else (),
                )
