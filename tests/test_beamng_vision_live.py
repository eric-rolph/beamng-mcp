from __future__ import annotations

import base64
import os
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from beamngpy import BeamNGpy, Scenario, Vehicle
from beamngpy.logging import BNGValueError
from beamngpy.sensors import Camera
from PIL import Image

from beamng_mcp.vision import (
    ColorSpace,
    HuggingFaceSegFormerBackend,
    ONNXRuntimeSegmentationBackend,
    ONNXRuntimeSegmentationConfig,
    OpenCVLaneBackend,
    SegFormerConfig,
    SegmentationClassMap,
    SensorFrame,
)
from tests.live_support import (
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    require_confined_profile_target,
    reserve_loopback_ports,
)

ONNX_CUDA_SMOKE_MODEL = base64.b64decode(
    "CAo6egoZCgVpbWFnZRIGbG9naXRzIghJZGVudGl0eRIaY3VkYV9pZGVudGl0eV9zZWdtZW50YXRpb25a"
    "HwoFaW1hZ2USFgoUCAESEAoCCAEKAggDCgIICAoCCAhiIAoGbG9naXRzEhYKFAgBEhAKAggBCgIIAwoC"
    "CAgKAggIQgQKABAR"
)

CITYSCAPES_CLASSES = SegmentationClassMap(
    drivable_class_ids=(0,),
    hazard_class_ids=(11, 12, 13, 14, 15, 16, 17, 18),
    hazard_names={
        11: "person",
        12: "rider",
        13: "car",
        14: "truck",
        15: "bus",
        16: "train",
        17: "motorcycle",
        18: "bicycle",
    },
)


def _live_paths() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the isolated live simulator test"
        )

    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = (binary if binary.is_absolute() else home / binary).resolve()
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not user.is_dir():
        pytest.fail(f"isolated BeamNG user directory does not exist: {user}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("GPU live tests require an explicitly marked isolated BeamNG user folder")
    return home, user, binary


def _capture_rgb(path: Path, bng: BeamNGpy) -> np.ndarray[Any, np.dtype[np.uint8]]:
    deadline = time.monotonic() + 30.0
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        bng.control.step(3, wait=True)
        if path.is_file():
            try:
                with Image.open(path) as captured:
                    image = np.asarray(captured.convert("RGB"), dtype=np.uint8)
                if image.shape == (360, 640, 3) and float(np.std(image)) > 1.0:
                    return image
            except OSError as exc:
                last_error = exc
        time.sleep(0.05)
    pytest.fail(
        "BeamNG retail RenderView did not produce a non-blank 640x360 colour frame within "
        f"30 seconds; last image error was {last_error!r}"
    )


def _create_capture_mod(path: Path) -> None:
    fixtures = Path(__file__).parent / "fixtures"
    created = False
    try:
        package = zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED)
        created = True
        with package:
            package.write(
                fixtures / "beamng_retail_vision_capture.lua",
                "lua/ge/extensions/beamng_mcp/vision_test_capture.lua",
            )
            package.write(
                fixtures / "beamng_retail_vision_modScript.lua",
                "scripts/beamng_mcp_vision_test/modScript.lua",
            )
            package.write(
                fixtures / "beamng_retail_vision_info.json",
                "mod_info/beamng_mcp_vision_test/info.json",
            )
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise


def _exercise_optional_segformer(frame: SensorFrame) -> None:
    model = os.getenv("BEAMNG_MCP_TEST_VISION_MODEL")
    if not model:
        return

    torch = pytest.importorskip("torch")
    pytest.importorskip("transformers")
    if not torch.cuda.is_available():
        pytest.fail("BEAMNG_MCP_TEST_VISION_MODEL was set, but PyTorch CUDA is unavailable")

    backend = HuggingFaceSegFormerBackend(
        SegFormerConfig(
            model_id_or_path=model,
            class_map=CITYSCAPES_CLASSES,
            device="cuda:0",
            dtype="float16",
            allow_downloads=False,
        )
    )
    result = backend.infer(frame)
    assert backend.loaded is True
    assert backend.device == "cuda:0"
    assert result.backend == "huggingface_segformer"
    assert result.image_shape == (frame.height, frame.width)
    assert result.drivable_mask is not None
    assert result.drivable_mask.shape == (frame.height, frame.width)
    assert result.metadata["downloads_allowed"] is False


def _exercise_onnx_cuda(frame: SensorFrame) -> None:
    try:
        import onnxruntime as ort
    except ImportError:
        return
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        return

    with tempfile.TemporaryDirectory(prefix="beamng-mcp-onnx-") as root:
        model_path = Path(root) / "identity-segmentation.onnx"
        model_path.write_bytes(ONNX_CUDA_SMOKE_MODEL)
        backend = ONNXRuntimeSegmentationBackend(
            ONNXRuntimeSegmentationConfig(
                model_path=model_path,
                class_map=SegmentationClassMap(drivable_class_ids=(1,)),
                provider_preference=("CUDAExecutionProvider",),
            )
        )
        result = backend.infer(frame)

    assert backend.active_providers[0] == "CUDAExecutionProvider"
    assert result.backend == "onnxruntime_segmentation"
    assert result.image_shape == (frame.height, frame.width)
    assert result.drivable_mask is not None
    assert result.drivable_mask.shape == (frame.height, frame.width)


def _run_live_vision_test(
    home: Path,
    user: Path,
    binary: Path,
    port: int,
    port_reservation: Any,
) -> None:
    launch_user = user.parent if user.name.casefold() == "current" else user
    bng = BeamNGpy(
        "127.0.0.1",
        port,
        home=str(home),
        binary=str(binary),
        user=str(launch_user),
        quit_on_close=False,
        headless=True,
        nogpu=False,
        gfx="dx11",
    )
    scenario: Scenario | None = None
    scenario_directory: Path | None = None
    owned_process: Any | None = None
    capture_mod = require_confined_profile_target(
        user,
        Path("mods") / "repo" / "beamng_mcp_vision_live_test.zip",
    )
    capture_mod_owned = False
    capture = require_confined_profile_target(
        user,
        Path("screenshots") / "beamng-mcp" / "vision-live.png",
    )
    capture_owned = False
    capture_parent_owned = not capture.parent.exists()

    def watchdog() -> None:
        process = owned_process or bng.process
        if process is not None and process.poll() is None:
            process.terminate()

    timer = threading.Timer(180.0, watchdog)
    timer.daemon = True
    timer.start()
    try:
        if capture_mod.exists():
            pytest.fail(f"refusing to overwrite existing isolated-profile test mod: {capture_mod}")
        if capture.exists():
            pytest.fail(f"refusing to overwrite existing isolated-profile capture: {capture}")
        capture_owned = True
        capture_mod.parent.mkdir(parents=True, exist_ok=True)
        _create_capture_mod(capture_mod)
        capture_mod_owned = True
        port_reservation.release()
        bng.open(
            launch=True,
            listen_ip="127.0.0.1",
        )
        owned_process = claim_owned_beamng_process(bng)
        assert bng.connection.skt is not None
        assert bng.tech_enabled() is False

        scenario = Scenario(
            "gridmap_v2",
            f"beamng_mcp_vision_{uuid.uuid4().hex[:12]}",
            description="Disposable beamng-mcp GPU vision integration fixture",
        )
        scenario_directory = require_confined_profile_target(
            user,
            Path("levels") / "gridmap_v2" / "scenarios" / scenario.name,
        )
        vehicle = Vehicle("ego", "etk800", license="MCPVISION", color="White")
        scenario.add_vehicle(vehicle, pos=(0.0, 0.0, 0.5), cling=True)
        scenario.make(bng)

        bng.scenario.load(scenario, precompile_shaders=False)
        bng.scenario.start()
        assert vehicle.is_connected() is True
        vehicle.control(throttle=0.0, brake=1.0, parkingbrake=1.0, is_adas=True)
        bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
        bng.control.pause()

        image = _capture_rgb(capture, bng)
        with pytest.raises(BNGValueError, match=r"requires a BeamNG\.tech license"):
            Camera(
                name="beamng_mcp_retail_boundary",
                bng=bng,
                vehicle=vehicle,
                resolution=(64, 64),
                is_using_shared_memory=False,
                is_render_annotations=False,
                is_render_depth=False,
            )
        frame = SensorFrame(
            image=image,
            captured_at=time.monotonic(),
            sequence=1,
            color_space=ColorSpace.RGB,
            source="beamng_retail_render_view",
            metadata={"resolution": [640, 360], "renderer": "dx11"},
        )

        classical = OpenCVLaneBackend().infer(frame)
        assert classical.backend == "opencv_classical"
        assert classical.frame_sequence == 1
        assert classical.image_shape == (360, 640)
        assert classical.lane_mask is not None
        assert classical.lane_mask.shape == (360, 640)
        assert classical.inference_ms >= 0.0

        _exercise_onnx_cuda(frame)
        _exercise_optional_segformer(frame)
    finally:
        try:
            cleanup_owned_beamng_session(
                bng,
                owned_process=owned_process,
                scenario=scenario,
            )
        finally:
            timer.cancel()
            cleanup_exact_live_artifacts(
                profile=user,
                files=tuple(
                    path
                    for path, owned in (
                        (capture, capture_owned),
                        (capture_mod, capture_mod_owned),
                    )
                    if owned
                ),
                empty_directories=tuple(
                    path
                    for path in (
                        scenario_directory,
                        capture.parent if capture_parent_owned else None,
                    )
                    if path is not None
                ),
            )


def test_gpu_early_refusal_preserves_a_preexisting_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = tmp_path / "current"
    user.mkdir()
    (user / ".beamng-mcp-test-user").touch()
    capture = user / "screenshots" / "beamng-mcp" / "vision-live.png"
    capture.parent.mkdir(parents=True)
    original = b"pre-existing capture"
    capture.write_bytes(original)
    fake_bng = SimpleNamespace(
        process=None,
        quit_on_close=False,
        disconnect=lambda: None,
    )
    monkeypatch.setitem(
        _run_live_vision_test.__globals__,
        "BeamNGpy",
        lambda *_args, **_kwargs: fake_bng,
    )
    reservation = SimpleNamespace(release=lambda: pytest.fail("must not launch"))

    with pytest.raises(pytest.fail.Exception, match="refusing to overwrite"):
        _run_live_vision_test(
            tmp_path / "home",
            user,
            tmp_path / "BeamNG.drive.x64.exe",
            49123,
            reservation,
        )

    assert capture.read_bytes() == original


def test_gpu_zip_creation_race_preserves_the_competing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = tmp_path / "current"
    user.mkdir()
    (user / ".beamng-mcp-test-user").touch()
    competing_bytes = b"created concurrently"

    def lose_creation_race(path: Path) -> None:
        path.write_bytes(competing_bytes)
        raise FileExistsError(path)

    fake_bng = SimpleNamespace(
        process=None,
        quit_on_close=False,
        disconnect=lambda: None,
    )
    monkeypatch.setitem(
        _run_live_vision_test.__globals__,
        "BeamNGpy",
        lambda *_args, **_kwargs: fake_bng,
    )
    monkeypatch.setitem(
        _run_live_vision_test.__globals__,
        "_create_capture_mod",
        lose_creation_race,
    )
    reservation = SimpleNamespace(release=lambda: pytest.fail("must not launch"))

    with pytest.raises(FileExistsError):
        _run_live_vision_test(
            tmp_path / "home",
            user,
            tmp_path / "BeamNG.drive.x64.exe",
            49123,
            reservation,
        )

    package = user / "mods" / "repo" / "beamng_mcp_vision_live_test.zip"
    assert package.read_bytes() == competing_bytes


def test_capture_mod_creation_removes_its_own_partial_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "partial.zip"

    def fail_write(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated ZIP write failure")

    monkeypatch.setattr(zipfile.ZipFile, "write", fail_write)

    with pytest.raises(OSError, match="simulated ZIP write failure"):
        _create_capture_mod(package)

    assert not package.exists()


def test_gpu_refuses_a_linked_mod_target_before_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = tmp_path / "current"
    user.mkdir()
    (user / ".beamng-mcp-test-user").touch()
    real_mods = user / "real-mods"
    real_mods.mkdir()
    try:
        (user / "mods").symlink_to(real_mods, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory links are unavailable on this host: {exc}")
    fake_bng = SimpleNamespace(
        process=None,
        quit_on_close=False,
        disconnect=lambda: None,
    )
    monkeypatch.setitem(
        _run_live_vision_test.__globals__,
        "BeamNGpy",
        lambda *_args, **_kwargs: fake_bng,
    )
    reservation = SimpleNamespace(release=lambda: pytest.fail("must not launch"))

    with pytest.raises(RuntimeError, match="link or reparse"):
        _run_live_vision_test(
            tmp_path / "home",
            user,
            tmp_path / "BeamNG.drive.x64.exe",
            49123,
            reservation,
        )

    assert not (real_mods / "repo" / "beamng_mcp_vision_live_test.zip").exists()


def test_gpu_live_path_discovery_preserves_a_linked_profile_for_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    monkeypatch.setenv("BEAMNG_MCP_TEST_BEAMNG_HOME", str(home))
    monkeypatch.setenv("BEAMNG_MCP_TEST_BEAMNG_USER", str(linked_user))
    monkeypatch.setenv("BEAMNG_MCP_TEST_BEAMNG_BINARY", str(binary))

    _, discovered_user, _ = _live_paths()

    assert discovered_user == Path(os.path.abspath(linked_user))
    assert discovered_user.is_symlink()


@pytest.mark.beamng_live
@pytest.mark.beamng_gpu
def test_isolated_retail_render_view_runs_local_perception_and_records_camera_boundary() -> None:
    home, user, binary = _live_paths()
    with isolated_profile_lock(user), reserve_loopback_ports(1) as reservation:
        _run_live_vision_test(
            home,
            user,
            binary,
            reservation.ports[0],
            reservation,
        )
