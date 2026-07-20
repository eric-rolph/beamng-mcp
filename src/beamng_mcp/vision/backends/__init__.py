"""Perception backends with optional dependencies loaded on demand."""

from .base import BackendUnavailableError, ModelLoadError
from .onnx import ONNXRuntimeSegmentationBackend, ONNXRuntimeSegmentationConfig
from .opencv import OpenCVLaneBackend, OpenCVLaneConfig
from .segformer import HuggingFaceSegFormerBackend, SegFormerConfig

__all__ = [
    "BackendUnavailableError",
    "HuggingFaceSegFormerBackend",
    "ModelLoadError",
    "ONNXRuntimeSegmentationBackend",
    "ONNXRuntimeSegmentationConfig",
    "OpenCVLaneBackend",
    "OpenCVLaneConfig",
    "SegFormerConfig",
]
