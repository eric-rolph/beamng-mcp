import asyncio
import time
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(slots=True)
class Perception:
    timestamp: float
    latency_ms: float
    detections: list[dict[str, Any]]


class VisionEngine:
    """Lazy-loaded CUDA perception backend; keeps heavyweight deps optional."""

    def __init__(self, model: str, device: str) -> None:
        self.model_name, self.device = model, device
        self._model: Any = None

    async def load(self) -> dict[str, Any]:
        await asyncio.to_thread(self._load)
        return {"loaded": True, "model": self.model_name, "device": self.device}

    def _load(self) -> None:
        from ultralytics import YOLO

        self._model = YOLO(self.model_name)

    async def infer(self, frame: np.ndarray) -> Perception:
        if self._model is None:
            raise RuntimeError("Vision model is not loaded")
        started = time.perf_counter()
        results = await asyncio.to_thread(
            self._model.predict, frame, device=self.device, verbose=False
        )
        detections: list[dict[str, Any]] = []
        for result in results:
            for box in result.boxes:
                detections.append({
                    "class_id": int(box.cls.item()),
                    "confidence": float(box.conf.item()),
                    "xyxy": [float(value) for value in box.xyxy[0].tolist()],
                })
        return Perception(time.time(), (time.perf_counter() - started) * 1000, detections)
