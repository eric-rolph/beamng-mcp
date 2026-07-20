"""Geometry extraction shared by semantic-segmentation backends."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

import numpy as np
from numpy.typing import NDArray

from .models import HazardObservation, LaneEstimate, PerceptionResult, SensorFrame


@dataclass(frozen=True, slots=True)
class LaneGeometryConfig:
    """Parameters for deriving a lane centerline from a drivable-area mask."""

    lookahead_y_ratio: float = 0.48
    sample_rows: int = 18
    row_half_window: int = 2
    minimum_row_coverage: float = 0.35
    minimum_lane_width_ratio: float = 0.12
    maximum_lane_width_ratio: float = 0.98

    def __post_init__(self) -> None:
        if not 0.1 <= self.lookahead_y_ratio < 0.9:
            raise ValueError("lookahead_y_ratio must be in [0.1, 0.9)")
        if self.sample_rows < 4:
            raise ValueError("sample_rows must be at least 4")
        if self.row_half_window < 0:
            raise ValueError("row_half_window cannot be negative")
        if not 0.0 < self.minimum_row_coverage <= 1.0:
            raise ValueError("minimum_row_coverage must be in (0, 1]")
        if not 0.0 < self.minimum_lane_width_ratio < self.maximum_lane_width_ratio <= 1.0:
            raise ValueError("lane width ratios must satisfy 0 < min < max <= 1")


@dataclass(frozen=True, slots=True)
class SegmentationClassMap:
    """Semantic class IDs used to interpret a model's label map."""

    drivable_class_ids: tuple[int, ...]
    lane_class_ids: tuple[int, ...] = ()
    hazard_class_ids: tuple[int, ...] = ()
    hazard_names: Mapping[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.drivable_class_ids and not self.lane_class_ids:
            raise ValueError("at least one drivable or lane class ID is required")
        all_ids = self.drivable_class_ids + self.lane_class_ids + self.hazard_class_ids
        if any(class_id < 0 for class_id in all_ids):
            raise ValueError("segmentation class IDs cannot be negative")
        object.__setattr__(
            self,
            "drivable_class_ids",
            tuple(dict.fromkeys(self.drivable_class_ids)),
        )
        object.__setattr__(self, "lane_class_ids", tuple(dict.fromkeys(self.lane_class_ids)))
        object.__setattr__(self, "hazard_class_ids", tuple(dict.fromkeys(self.hazard_class_ids)))
        object.__setattr__(self, "hazard_names", MappingProxyType(dict(self.hazard_names)))


def _runs(indices: NDArray[np.int_]) -> list[tuple[int, int]]:
    if indices.size == 0:
        return []
    split_points = np.flatnonzero(np.diff(indices) > 1) + 1
    return [(int(part[0]), int(part[-1])) for part in np.split(indices, split_points) if part.size]


def _choose_run(
    runs: list[tuple[int, int]],
    expected_center: float,
    image_width: int,
) -> tuple[int, int] | None:
    """Choose a road segment, favoring one containing the prior centerline."""

    if not runs:
        return None
    containing = [run for run in runs if run[0] <= expected_center <= run[1]]
    if containing:
        return max(containing, key=lambda run: run[1] - run[0])

    # A large nearby segment is more likely to be the current road than a
    # thin semantic island at an image edge.
    def score(run: tuple[int, int]) -> float:
        width = run[1] - run[0] + 1
        center = (run[0] + run[1]) / 2.0
        distance = abs(center - expected_center) / max(image_width, 1)
        return width * (1.0 - min(distance, 0.95))

    return max(runs, key=score)


def estimate_lane_from_drivable_mask(
    mask: NDArray[np.bool_],
    *,
    confidence_map: NDArray[np.floating] | None = None,
    config: LaneGeometryConfig | None = None,
) -> LaneEstimate | None:
    """Estimate lane center and heading from a boolean drivable-area mask."""

    cfg = config or LaneGeometryConfig()
    road = np.asarray(mask, dtype=bool)
    if road.ndim != 2:
        raise ValueError("drivable mask must be two-dimensional")
    height, width = road.shape
    if height < 8 or width < 8:
        return None
    if confidence_map is not None and tuple(confidence_map.shape) != road.shape:
        raise ValueError("confidence_map must match the drivable mask shape")

    bottom_y = height - 2
    lookahead_y = max(0, min(bottom_y - 1, round(height * cfg.lookahead_y_ratio)))
    sample_y = np.linspace(bottom_y, lookahead_y, cfg.sample_rows).round().astype(int)
    minimum_width = cfg.minimum_lane_width_ratio * width
    maximum_width = cfg.maximum_lane_width_ratio * width

    centers: list[float] = []
    widths: list[float] = []
    rows: list[float] = []
    confidences: list[float] = []
    expected_center = width / 2.0

    for y in sample_y:
        y0 = max(0, int(y) - cfg.row_half_window)
        y1 = min(height, int(y) + cfg.row_half_window + 1)
        active = np.flatnonzero(np.any(road[y0:y1], axis=0))
        run = _choose_run(_runs(active), expected_center, width)
        if run is None:
            continue
        left, right = run
        lane_width = float(right - left + 1)
        if not minimum_width <= lane_width <= maximum_width:
            continue
        center = (left + right) / 2.0
        rows.append(float(y))
        centers.append(center)
        widths.append(lane_width)
        expected_center = 0.65 * expected_center + 0.35 * center
        if confidence_map is not None:
            segment = np.asarray(confidence_map[y0:y1, left : right + 1], dtype=np.float32)
            confidences.append(float(np.clip(np.mean(segment), 0.0, 1.0)))

    coverage = len(rows) / cfg.sample_rows
    if len(rows) < 3 or coverage < cfg.minimum_row_coverage:
        return None

    y_values = np.asarray(rows, dtype=np.float64)
    x_values = np.asarray(centers, dtype=np.float64)
    degree = 2 if len(rows) >= 6 else 1
    coefficients = np.polyfit(y_values, x_values, degree)
    bottom_x = float(np.polyval(coefficients, bottom_y))
    lookahead_x = float(np.polyval(coefficients, lookahead_y))
    bottom_x = float(np.clip(bottom_x, 0.0, width - 1.0))
    lookahead_x = float(np.clip(lookahead_x, 0.0, width - 1.0))

    center_offset = float(np.clip((bottom_x - width / 2.0) / (width / 2.0), -1.0, 1.0))
    heading = math.atan2(lookahead_x - bottom_x, max(bottom_y - lookahead_y, 1))
    heading = float(np.clip(heading, -math.pi / 2, math.pi / 2))

    curvature = 0.0
    if degree == 2:
        # Pixel-space second derivative normalized by image width.  The value
        # is dimensionless and intended for relative speed limiting, not as a
        # calibrated road-radius measurement.
        curvature = float(np.clip(2.0 * coefficients[0] * width, -1.0, 1.0))

    width_values = np.asarray(widths, dtype=np.float64)
    width_stability = math.exp(
        -float(np.std(width_values)) / max(float(np.mean(width_values)), 1.0)
    )
    fit_residual = float(np.sqrt(np.mean((np.polyval(coefficients, y_values) - x_values) ** 2)))
    fit_quality = math.exp(-fit_residual / max(width * 0.08, 1.0))
    semantic_confidence = float(np.mean(confidences)) if confidences else 1.0
    confidence = float(
        np.clip(
            coverage
            * (0.35 + 0.25 * width_stability + 0.25 * fit_quality + 0.15 * semantic_confidence),
            0.0,
            1.0,
        )
    )

    return LaneEstimate(
        center_offset=center_offset,
        heading_error_rad=heading,
        curvature=curvature,
        confidence=confidence,
        center_x_px=bottom_x,
        lookahead_x_px=lookahead_x,
        lane_width_px=float(np.median(width_values)),
    )


def hazards_from_labels(
    labels: NDArray[np.integer],
    class_map: SegmentationClassMap,
    *,
    confidence_map: NDArray[np.floating] | None = None,
) -> tuple[HazardObservation, ...]:
    """Convert semantic hazard classes into conservative aggregate hazards."""

    label_map = np.asarray(labels)
    if label_map.ndim != 2:
        raise ValueError("labels must be two-dimensional")
    if confidence_map is not None and tuple(confidence_map.shape) != label_map.shape:
        raise ValueError("confidence_map must match labels")
    height, width = label_map.shape
    observations: list[HazardObservation] = []

    for class_id in class_map.hazard_class_ids:
        ys, xs = np.nonzero(label_map == class_id)
        if xs.size == 0:
            continue
        x_norm = xs.astype(np.float64) / max(width - 1, 1)
        y_norm = ys.astype(np.float64) / max(height - 1, 1)
        centrality = np.clip(1.0 - np.abs(x_norm - 0.5) * 2.0, 0.0, 1.0)
        proximity = np.clip(y_norm, 0.0, 1.0)
        weighted_presence = float(np.mean(centrality * proximity))
        area_score = min(1.0, xs.size / max(height * width * 0.035, 1.0))
        bottom_score = float(np.max(proximity))
        confidence = (
            float(np.mean(np.asarray(confidence_map)[ys, xs]))
            if confidence_map is not None
            else 1.0
        )
        score = float(
            np.clip(
                (0.5 * bottom_score + 0.3 * weighted_presence + 0.2 * area_score)
                * np.clip(confidence, 0.0, 1.0),
                0.0,
                1.0,
            )
        )
        bbox = (
            float(np.min(x_norm)),
            float(np.min(y_norm)),
            float(np.max(x_norm)),
            float(np.max(y_norm)),
        )
        observations.append(
            HazardObservation(
                kind=class_map.hazard_names.get(class_id, f"class_{class_id}"),
                score=score,
                bbox=bbox,
                metadata={"class_id": class_id, "pixel_count": int(xs.size)},
            )
        )

    return tuple(sorted(observations, key=lambda item: item.score, reverse=True))


def perception_from_segmentation(
    frame: SensorFrame,
    labels: NDArray[np.integer],
    *,
    class_map: SegmentationClassMap,
    backend: str,
    inference_ms: float,
    confidence_map: NDArray[np.floating] | None = None,
    geometry_config: LaneGeometryConfig | None = None,
    metadata: Mapping[str, object] | None = None,
) -> PerceptionResult:
    """Build a fully typed perception result from a semantic label map."""

    label_map = np.asarray(labels)
    if label_map.ndim != 2 or tuple(label_map.shape) != (frame.height, frame.width):
        raise ValueError("segmentation labels must match the source frame dimensions")
    if confidence_map is not None and tuple(confidence_map.shape) != label_map.shape:
        raise ValueError("confidence_map must match segmentation labels")

    drivable_mask = np.isin(label_map, class_map.drivable_class_ids)
    lane_mask = (
        np.isin(label_map, class_map.lane_class_ids)
        if class_map.lane_class_ids
        else np.zeros_like(drivable_mask)
    )
    geometry_mask = drivable_mask
    if not np.any(geometry_mask) and np.any(lane_mask):
        # A lane-marking-only model cannot define the complete road area, but
        # retaining the mask lets a caller inspect why geometry was absent.
        geometry_mask = lane_mask
    lane = estimate_lane_from_drivable_mask(
        geometry_mask,
        confidence_map=confidence_map,
        config=geometry_config,
    )
    hazards = hazards_from_labels(label_map, class_map, confidence_map=confidence_map)
    return PerceptionResult(
        frame_sequence=frame.sequence,
        captured_at=frame.captured_at,
        image_shape=(frame.height, frame.width),
        backend=backend,
        lane=lane,
        hazards=hazards,
        drivable_mask=np.asarray(drivable_mask, dtype=bool),
        lane_mask=np.asarray(lane_mask, dtype=bool),
        inference_ms=inference_ms,
        metadata=metadata or {},
    )
