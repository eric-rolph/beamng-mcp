"""Lazy ONNX Runtime segmentation with bounded GPU provider settings."""

from __future__ import annotations

import importlib
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from ..geometry import (
    LaneGeometryConfig,
    SegmentationClassMap,
    perception_from_segmentation,
)
from ..models import PerceptionResult, SensorFrame
from .base import (
    BackendUnavailableError,
    ModelLoadError,
    frame_as_rgb,
    resize_image,
    resize_nearest,
)

Layout = Literal["auto", "nchw", "nhwc"]


@dataclass(frozen=True, slots=True)
class ONNXRuntimeSegmentationConfig:
    """Configuration for a local ONNX semantic-segmentation model."""

    model_path: str | Path
    class_map: SegmentationClassMap
    input_size: tuple[int, int] | None = None
    input_layout: Layout = "auto"
    output_layout: Layout = "auto"
    input_name: str | None = None
    output_name: str | None = None
    provider_preference: tuple[str, ...] = (
        "TensorrtExecutionProvider",
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    )
    device_id: int = 0
    gpu_memory_limit_mb: int = 4096
    tensorrt_workspace_mb: int = 2048
    enable_tensorrt_fp16: bool = True
    mean: tuple[float, float, float] = (0.485, 0.456, 0.406)
    std: tuple[float, float, float] = (0.229, 0.224, 0.225)
    geometry: LaneGeometryConfig = field(default_factory=LaneGeometryConfig)

    def __post_init__(self) -> None:
        if not str(self.model_path):
            raise ValueError("model_path cannot be empty")
        if self.input_size is not None and min(self.input_size) <= 0:
            raise ValueError("input_size must contain positive (height, width)")
        if self.input_layout not in {"auto", "nchw", "nhwc"}:
            raise ValueError("input_layout must be auto, nchw, or nhwc")
        if self.output_layout not in {"auto", "nchw", "nhwc"}:
            raise ValueError("output_layout must be auto, nchw, or nhwc")
        if not self.provider_preference:
            raise ValueError("provider_preference cannot be empty")
        if self.device_id < 0:
            raise ValueError("device_id cannot be negative")
        if not 128 <= self.gpu_memory_limit_mb <= 131_072:
            raise ValueError("gpu_memory_limit_mb must be between 128 and 131072")
        if not 64 <= self.tensorrt_workspace_mb <= self.gpu_memory_limit_mb:
            raise ValueError(
                "tensorrt_workspace_mb must be at least 64 and no larger than gpu_memory_limit_mb"
            )
        if any(value <= 0.0 for value in self.std):
            raise ValueError("normalization std values must be positive")


class ONNXRuntimeSegmentationBackend:
    """Run a local segmentation graph using TensorRT, CUDA, then CPU.

    The session is created lazily.  Provider options bound both TensorRT's
    workspace and CUDA's arena, preventing the vision process from claiming
    all memory on a GPU shared with BeamNG.
    """

    name = "onnxruntime_segmentation"

    def __init__(self, config: ONNXRuntimeSegmentationConfig) -> None:
        self.config = config
        self._session: Any | None = None
        self._input_name: str | None = None
        self._output_name: str | None = None
        self._input_height: int | None = None
        self._input_width: int | None = None
        self._input_layout: Literal["nchw", "nhwc"] | None = None
        self._active_providers: tuple[str, ...] = ()

    @property
    def loaded(self) -> bool:
        return self._session is not None

    @property
    def active_providers(self) -> tuple[str, ...]:
        return self._active_providers

    def _build_provider_specs(self, available: Sequence[str]) -> list[Any]:
        available_set = set(available)
        byte_limit = int(self.config.gpu_memory_limit_mb * 1024 * 1024)
        workspace_limit = int(self.config.tensorrt_workspace_mb * 1024 * 1024)
        providers: list[Any] = []
        for provider in self.config.provider_preference:
            if provider not in available_set:
                continue
            if provider == "TensorrtExecutionProvider":
                providers.append(
                    (
                        provider,
                        {
                            "device_id": self.config.device_id,
                            "trt_max_workspace_size": workspace_limit,
                            "trt_fp16_enable": self.config.enable_tensorrt_fp16,
                            "trt_engine_cache_enable": False,
                        },
                    )
                )
            elif provider == "CUDAExecutionProvider":
                providers.append(
                    (
                        provider,
                        {
                            "device_id": self.config.device_id,
                            "gpu_mem_limit": byte_limit,
                            "arena_extend_strategy": "kSameAsRequested",
                            "cudnn_conv_algo_search": "HEURISTIC",
                            "do_copy_in_default_stream": True,
                        },
                    )
                )
            else:
                providers.append(provider)
        return providers

    @staticmethod
    def _dimension(value: Any) -> int | None:
        return int(value) if isinstance(value, int) and value > 0 else None

    def _resolve_input_geometry(self, shape: Sequence[Any]) -> None:
        if len(shape) != 4:
            raise ModelLoadError(f"Expected a rank-4 image input, got shape {tuple(shape)!r}")
        layout = self.config.input_layout
        if layout == "auto":
            channels_first = self._dimension(shape[1])
            channels_last = self._dimension(shape[3])
            if channels_first in {1, 3, 4}:
                layout = "nchw"
            elif channels_last in {1, 3, 4}:
                layout = "nhwc"
            else:
                layout = "nchw"
        self._input_layout = layout

        if self.config.input_size is not None:
            self._input_height, self._input_width = self.config.input_size
            return
        if layout == "nchw":
            height, width = self._dimension(shape[2]), self._dimension(shape[3])
        else:
            height, width = self._dimension(shape[1]), self._dimension(shape[2])
        if height is None or width is None:
            raise ModelLoadError(
                "The ONNX model has dynamic spatial dimensions; configure "
                "input_size=(height, width)"
            )
        self._input_height, self._input_width = height, width

    def _ensure_session(self) -> None:
        if self._session is not None:
            return
        gpu_requested = any(
            provider in {"CUDAExecutionProvider", "TensorrtExecutionProvider"}
            for provider in self.config.provider_preference
        )
        if gpu_requested:
            try:
                # Importing compatible PyTorch first loads its CUDA/cuDNN DLLs
                # without ONNX Runtime's stdout-printing preload helper. Stdout
                # must remain exclusively available to the MCP stdio transport.
                importlib.import_module("torch")
            except ImportError:
                # A standalone ONNX installation may instead provide native
                # dependencies through its normal DLL search path.
                pass
        try:
            ort = importlib.import_module("onnxruntime")
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise BackendUnavailableError(
                "ONNX backend requires optional 'onnxruntime' or 'onnxruntime-gpu'"
            ) from exc

        model_path = Path(self.config.model_path).expanduser()
        if not model_path.is_file():
            raise ModelLoadError(
                f"ONNX model must be an existing local file; not found: {model_path}"
            )
        providers = self._build_provider_specs(ort.get_available_providers())
        if not providers:
            raise BackendUnavailableError(
                "None of the requested ONNX Runtime providers are available: "
                + ", ".join(self.config.provider_preference)
            )

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        try:
            session = ort.InferenceSession(
                str(model_path),
                sess_options=options,
                providers=providers,
            )
        except Exception as exc:  # ONNX Runtime exposes several runtime-specific errors
            raise ModelLoadError(f"Unable to create ONNX Runtime session for {model_path}") from exc

        inputs = session.get_inputs()
        outputs = session.get_outputs()
        if not inputs or not outputs:
            raise ModelLoadError("ONNX model must expose at least one input and one output")
        input_meta = next(
            (item for item in inputs if item.name == self.config.input_name),
            inputs[0],
        )
        output_meta = next(
            (item for item in outputs if item.name == self.config.output_name),
            outputs[0],
        )
        if self.config.input_name is not None and input_meta.name != self.config.input_name:
            raise ModelLoadError(f"ONNX input {self.config.input_name!r} does not exist")
        if self.config.output_name is not None and output_meta.name != self.config.output_name:
            raise ModelLoadError(f"ONNX output {self.config.output_name!r} does not exist")

        self._resolve_input_geometry(input_meta.shape)
        self._session = session
        self._input_name = input_meta.name
        self._output_name = output_meta.name
        self._active_providers = tuple(session.get_providers())

    def _preprocess(self, frame: SensorFrame) -> NDArray[np.float32]:
        assert self._input_height is not None and self._input_width is not None
        assert self._input_layout is not None
        image = resize_image(frame_as_rgb(frame), self._input_height, self._input_width)
        tensor = image.astype(np.float32) / 255.0
        mean = np.asarray(self.config.mean, dtype=np.float32)
        std = np.asarray(self.config.std, dtype=np.float32)
        tensor = (tensor - mean) / std
        if self._input_layout == "nchw":
            tensor = np.transpose(tensor, (2, 0, 1))
        return np.ascontiguousarray(tensor[None, ...], dtype=np.float32)

    def _decode_output(
        self,
        raw_output: NDArray[Any],
        target_height: int,
        target_width: int,
    ) -> tuple[NDArray[np.int64], NDArray[np.float32]]:
        output = np.asarray(raw_output)
        if output.ndim == 4:
            layout = self.config.output_layout
            if layout == "auto":
                # Segmentation class dimensions are normally far smaller than
                # either spatial dimension.
                layout = "nchw" if output.shape[1] <= output.shape[-1] else "nhwc"
            logits = output[0]
            if layout == "nhwc":
                logits = np.moveaxis(logits, -1, 0)
            logits = logits.astype(np.float32, copy=False)
            logits -= np.max(logits, axis=0, keepdims=True)
            exp = np.exp(logits)
            probabilities = exp / np.maximum(np.sum(exp, axis=0, keepdims=True), 1e-12)
            labels = np.argmax(probabilities, axis=0).astype(np.int64, copy=False)
            confidence = np.max(probabilities, axis=0).astype(np.float32, copy=False)
        elif output.ndim == 3:
            labels = output[0].astype(np.int64, copy=False)
            confidence = np.ones(labels.shape, dtype=np.float32)
        elif output.ndim == 2:
            labels = output.astype(np.int64, copy=False)
            confidence = np.ones(labels.shape, dtype=np.float32)
        else:
            raise RuntimeError(f"Unsupported ONNX segmentation output shape: {output.shape!r}")

        labels = resize_nearest(labels, target_height, target_width).astype(np.int64, copy=False)
        confidence = resize_image(confidence, target_height, target_width).astype(
            np.float32,
            copy=False,
        )
        return labels, np.clip(confidence, 0.0, 1.0)

    def infer(self, frame: SensorFrame) -> PerceptionResult:
        started = time.perf_counter()
        self._ensure_session()
        assert self._session is not None
        assert self._input_name is not None and self._output_name is not None
        tensor = self._preprocess(frame)
        raw = self._session.run([self._output_name], {self._input_name: tensor})[0]
        labels, confidence = self._decode_output(raw, frame.height, frame.width)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return perception_from_segmentation(
            frame,
            labels,
            class_map=self.config.class_map,
            backend=self.name,
            inference_ms=elapsed_ms,
            confidence_map=confidence,
            geometry_config=self.config.geometry,
            metadata={
                "model_path": str(Path(self.config.model_path)),
                "providers": self._active_providers,
                "gpu_memory_limit_mb": self.config.gpu_memory_limit_mb,
                "input_size": (self._input_height, self._input_width),
            },
        )
