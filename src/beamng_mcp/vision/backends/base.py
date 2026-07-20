"""Shared backend errors and dependency-free image helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from ..models import ColorSpace, SensorFrame


class BackendUnavailableError(RuntimeError):
    """Raised when an explicitly selected optional runtime is unavailable."""


class ModelLoadError(RuntimeError):
    """Raised when a configured local model cannot be loaded."""


def uint8_image(image: NDArray[Any]) -> NDArray[np.uint8]:
    """Convert integer or floating image data to contiguous uint8 safely."""

    array = np.asarray(image)
    if array.dtype == np.uint8:
        return np.ascontiguousarray(array)
    if np.issubdtype(array.dtype, np.floating):
        finite = np.nan_to_num(array, nan=0.0, posinf=255.0, neginf=0.0)
        if finite.size and float(np.max(finite)) <= 1.0:
            finite = finite * 255.0
        return np.ascontiguousarray(np.clip(finite, 0.0, 255.0).astype(np.uint8))
    return np.ascontiguousarray(np.clip(array, 0, 255).astype(np.uint8))


def frame_as_rgb(frame: SensorFrame) -> NDArray[np.uint8]:
    image = uint8_image(frame.image)
    if frame.color_space is ColorSpace.RGB:
        return image
    if frame.color_space is ColorSpace.BGR:
        return np.ascontiguousarray(image[..., ::-1])
    return np.repeat(image[..., None], 3, axis=2)


def frame_as_bgr(frame: SensorFrame) -> NDArray[np.uint8]:
    image = uint8_image(frame.image)
    if frame.color_space is ColorSpace.BGR:
        return image
    if frame.color_space is ColorSpace.RGB:
        return np.ascontiguousarray(image[..., ::-1])
    return np.repeat(image[..., None], 3, axis=2)


def resize_nearest(array: NDArray[Any], height: int, width: int) -> NDArray[Any]:
    """Dependency-free nearest-neighbor resize for masks and fallback paths."""

    source = np.asarray(array)
    if height <= 0 or width <= 0:
        raise ValueError("resize dimensions must be positive")
    if source.shape[0] == height and source.shape[1] == width:
        return np.ascontiguousarray(source)
    y_index = np.minimum(
        (np.arange(height, dtype=np.float64) * source.shape[0] / height).astype(int),
        source.shape[0] - 1,
    )
    x_index = np.minimum(
        (np.arange(width, dtype=np.float64) * source.shape[1] / width).astype(int),
        source.shape[1] - 1,
    )
    return np.ascontiguousarray(source[y_index[:, None], x_index[None, :]])


def resize_image(array: NDArray[Any], height: int, width: int) -> NDArray[Any]:
    """Use OpenCV bilinear resize when available, otherwise nearest-neighbor."""

    try:
        import cv2
    except ImportError:
        return resize_nearest(array, height, width)
    return np.ascontiguousarray(cv2.resize(array, (width, height), interpolation=cv2.INTER_LINEAR))
