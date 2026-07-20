"""Lazy Hugging Face SegFormer semantic-segmentation backend."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..geometry import (
    LaneGeometryConfig,
    SegmentationClassMap,
    perception_from_segmentation,
)
from ..models import PerceptionResult, SensorFrame
from .base import BackendUnavailableError, ModelLoadError, frame_as_rgb


@dataclass(frozen=True, slots=True)
class SegFormerConfig:
    """Configuration for a locally cached or explicitly downloadable model."""

    model_id_or_path: str
    class_map: SegmentationClassMap
    device: str = "auto"
    dtype: str = "auto"
    allow_downloads: bool = False
    revision: str | None = None
    geometry: LaneGeometryConfig = field(default_factory=LaneGeometryConfig)

    def __post_init__(self) -> None:
        if not self.model_id_or_path.strip():
            raise ValueError("model_id_or_path cannot be empty")
        if self.device != "auto" and self.device != "cpu" and not self.device.startswith("cuda"):
            raise ValueError("device must be 'auto', 'cpu', or a CUDA device such as 'cuda:0'")
        if self.dtype not in {"auto", "float16", "float32", "bfloat16"}:
            raise ValueError("dtype must be auto, float16, float32, or bfloat16")


class HuggingFaceSegFormerBackend:
    """Semantic segmentation backed by Transformers and PyTorch.

    Construction is side-effect free: neither optional framework imports nor
    model resolution happen until the first call to :meth:`infer`.  Downloads
    are disabled by default via ``local_files_only=True``.
    """

    name = "huggingface_segformer"

    def __init__(self, config: SegFormerConfig) -> None:
        self.config = config
        self._torch: Any | None = None
        self._processor: Any | None = None
        self._model: Any | None = None
        self._device: str | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def device(self) -> str | None:
        return self._device

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import (
                AutoImageProcessor,
                SegformerForSemanticSegmentation,
            )
        except (ImportError, RuntimeError) as exc:  # pragma: no cover - environment dependent
            raise BackendUnavailableError(
                "SegFormer requires optional 'torch' and 'transformers' dependencies"
            ) from exc

        requested = self.config.device
        device = "cuda:0" if requested == "auto" and torch.cuda.is_available() else requested
        if device == "auto":
            device = "cpu"
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise BackendUnavailableError(
                f"SegFormer device {device!r} was requested but CUDA is unavailable"
            )

        load_options: dict[str, Any] = {
            "local_files_only": not self.config.allow_downloads,
        }
        if self.config.revision is not None:
            load_options["revision"] = self.config.revision
        try:
            processor_factory: Any = AutoImageProcessor
            processor = processor_factory.from_pretrained(
                self.config.model_id_or_path,
                use_fast=False,
                **load_options,
            )
            model = SegformerForSemanticSegmentation.from_pretrained(
                self.config.model_id_or_path,
                **load_options,
            )
        except Exception as exc:
            download_hint = (
                "Downloads are disabled; pre-cache the model or set "
                "allow_downloads=True explicitly."
                if not self.config.allow_downloads
                else "The model could not be resolved or loaded."
            )
            raise ModelLoadError(
                f"Unable to load SegFormer model {self.config.model_id_or_path!r}. {download_hint}"
            ) from exc

        dtype = self.config.dtype
        if dtype == "auto":
            dtype = "float16" if device.startswith("cuda") else "float32"
        torch_dtype = getattr(torch, dtype)
        model = model.to(device=device, dtype=torch_dtype)
        model.eval()

        self._torch = torch
        self._processor = processor
        self._model = model
        self._device = str(device)

    @staticmethod
    def _move_inputs(
        encoded: dict[str, Any], *, device: str, floating_dtype: Any
    ) -> dict[str, Any]:
        """Move processor outputs while matching floating inputs to model precision."""

        moved: dict[str, Any] = {}
        for key, value in encoded.items():
            if not hasattr(value, "to"):
                moved[key] = value
            elif hasattr(value, "is_floating_point") and value.is_floating_point():
                moved[key] = value.to(device=device, dtype=floating_dtype)
            else:
                moved[key] = value.to(device=device)
        return moved

    def infer(self, frame: SensorFrame) -> PerceptionResult:
        started = time.perf_counter()
        self._ensure_loaded()
        assert self._torch is not None
        assert self._processor is not None
        assert self._model is not None
        assert self._device is not None
        torch = self._torch

        rgb = frame_as_rgb(frame)
        encoded = self._processor(images=rgb, return_tensors="pt")
        model_dtype = next(self._model.parameters()).dtype
        encoded = self._move_inputs(
            encoded,
            device=self._device,
            floating_dtype=model_dtype,
        )
        with torch.inference_mode():
            logits = self._model(**encoded).logits
            logits = torch.nn.functional.interpolate(
                logits,
                size=(frame.height, frame.width),
                mode="bilinear",
                align_corners=False,
            )
            probabilities = torch.softmax(logits.float(), dim=1)
            confidence, labels = torch.max(probabilities, dim=1)

        label_map = labels[0].detach().cpu().numpy().astype(np.int64, copy=False)
        confidence_map = confidence[0].detach().cpu().numpy().astype(np.float32, copy=False)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return perception_from_segmentation(
            frame,
            label_map,
            class_map=self.config.class_map,
            backend=self.name,
            inference_ms=elapsed_ms,
            confidence_map=confidence_map,
            geometry_config=self.config.geometry,
            metadata={
                "model": self.config.model_id_or_path,
                "device": self._device,
                "downloads_allowed": self.config.allow_downloads,
            },
        )
