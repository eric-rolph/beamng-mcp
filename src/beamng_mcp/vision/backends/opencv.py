"""Weight-free classical lane detection using OpenCV."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..models import LaneEstimate, PerceptionResult, SensorFrame
from .base import BackendUnavailableError, frame_as_bgr


@dataclass(frozen=True, slots=True)
class OpenCVLaneConfig:
    """Tunable parameters for the classical lane backend."""

    roi_top_ratio: float = 0.50
    roi_top_half_width_ratio: float = 0.18
    gaussian_kernel: int = 5
    canny_low: int = 55
    canny_high: int = 165
    white_lightness_threshold: int = 165
    hough_threshold: int = 24
    min_line_length_ratio: float = 0.08
    max_line_gap_ratio: float = 0.05
    minimum_vertical_component: float = 0.45
    assumed_lane_width_ratio: float = 0.46
    minimum_lane_width_ratio: float = 0.18
    maximum_lane_width_ratio: float = 0.88

    def __post_init__(self) -> None:
        if not 0.2 <= self.roi_top_ratio < 0.9:
            raise ValueError("roi_top_ratio must be in [0.2, 0.9)")
        if not 0.05 <= self.roi_top_half_width_ratio <= 0.45:
            raise ValueError("roi_top_half_width_ratio must be in [0.05, 0.45]")
        if self.gaussian_kernel < 3 or self.gaussian_kernel % 2 == 0:
            raise ValueError("gaussian_kernel must be an odd integer >= 3")
        if not 0 <= self.canny_low < self.canny_high <= 255:
            raise ValueError("Canny thresholds must satisfy 0 <= low < high <= 255")
        if not 0 <= self.white_lightness_threshold <= 255:
            raise ValueError("white_lightness_threshold must be in [0, 255]")
        if self.hough_threshold < 1:
            raise ValueError("hough_threshold must be positive")
        if not 0.0 < self.min_line_length_ratio <= 1.0:
            raise ValueError("min_line_length_ratio must be in (0, 1]")
        if not 0.0 <= self.max_line_gap_ratio <= 1.0:
            raise ValueError("max_line_gap_ratio must be in [0, 1]")
        if not 0.0 < self.minimum_vertical_component <= 1.0:
            raise ValueError("minimum_vertical_component must be in (0, 1]")
        if not 0.0 < self.minimum_lane_width_ratio < self.assumed_lane_width_ratio:
            raise ValueError("assumed lane width must exceed minimum lane width")
        if not self.assumed_lane_width_ratio < self.maximum_lane_width_ratio <= 1.0:
            raise ValueError("maximum lane width must exceed assumed lane width and be <= 1")


class OpenCVLaneBackend:
    """Detect lane boundaries with color thresholding, Canny, and Hough lines.

    OpenCV is imported only when :meth:`infer` is first called, so importing
    the package does not make the optional dependency mandatory.
    """

    name = "opencv_classical"

    def __init__(self, config: OpenCVLaneConfig | None = None) -> None:
        self.config = config or OpenCVLaneConfig()

    @staticmethod
    def _cv2() -> Any:
        try:
            import cv2
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise BackendUnavailableError(
                "OpenCVLaneBackend requires the optional 'opencv-python' dependency"
            ) from exc
        return cv2

    @staticmethod
    def _fit_boundary(
        segments: list[tuple[int, int, int, int, float]],
    ) -> tuple[float, float, float] | None:
        if not segments:
            return None
        y_values: list[float] = []
        x_values: list[float] = []
        weights: list[float] = []
        total_length = 0.0
        for x1, y1, x2, y2, length in segments:
            x_values.extend((float(x1), float(x2)))
            y_values.extend((float(y1), float(y2)))
            endpoint_weight = math.sqrt(max(length, 1.0))
            weights.extend((endpoint_weight, endpoint_weight))
            total_length += length
        if len(set(y_values)) < 2:
            return None
        slope, intercept = np.polyfit(
            np.asarray(y_values),
            np.asarray(x_values),
            1,
            w=np.asarray(weights),
        )
        return float(slope), float(intercept), total_length

    def infer(self, frame: SensorFrame) -> PerceptionResult:
        cv2 = self._cv2()
        started = time.perf_counter()
        cfg = self.config
        image = frame_as_bgr(frame)
        height, width = image.shape[:2]

        hls = cv2.cvtColor(image, cv2.COLOR_BGR2HLS)
        white = cv2.inRange(
            hls,
            np.asarray((0, cfg.white_lightness_threshold, 0), dtype=np.uint8),
            np.asarray((255, 255, 255), dtype=np.uint8),
        )
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        yellow = cv2.inRange(
            hsv,
            np.asarray((12, 55, 80), dtype=np.uint8),
            np.asarray((42, 255, 255), dtype=np.uint8),
        )
        color_mask = cv2.bitwise_or(white, yellow)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (cfg.gaussian_kernel, cfg.gaussian_kernel), 0)
        edges = cv2.Canny(blurred, cfg.canny_low, cfg.canny_high)
        color_edges = cv2.Canny(color_mask, max(20, cfg.canny_low // 2), cfg.canny_high)
        edges = cv2.bitwise_or(edges, color_edges)

        top_y = round(height * cfg.roi_top_ratio)
        half_top = round(width * cfg.roi_top_half_width_ratio)
        polygon = np.asarray(
            [
                [
                    (int(width * 0.03), height - 1),
                    (width // 2 - half_top, top_y),
                    (width // 2 + half_top, top_y),
                    (int(width * 0.97), height - 1),
                ]
            ],
            dtype=np.int32,
        )
        roi = np.zeros_like(edges)
        cv2.fillPoly(roi, polygon, 255)
        masked_edges = cv2.bitwise_and(edges, roi)

        lines = cv2.HoughLinesP(
            masked_edges,
            rho=1,
            theta=np.pi / 180,
            threshold=cfg.hough_threshold,
            minLineLength=max(8, int(height * cfg.min_line_length_ratio)),
            maxLineGap=max(2, int(height * cfg.max_line_gap_ratio)),
        )

        left_segments: list[tuple[int, int, int, int, float]] = []
        right_segments: list[tuple[int, int, int, int, float]] = []
        if lines is not None:
            for raw_line in lines[:, 0, :]:
                x1, y1, x2, y2 = (int(value) for value in raw_line)
                dx = x2 - x1
                dy = y2 - y1
                length = math.hypot(dx, dy)
                if length < 1.0 or abs(dy) / length < cfg.minimum_vertical_component:
                    continue
                if dy == 0:
                    continue
                x_at_bottom = x1 + (height - 1 - y1) * dx / dy
                segment = (x1, y1, x2, y2, length)
                if x_at_bottom < width / 2.0:
                    left_segments.append(segment)
                else:
                    right_segments.append(segment)

        left = self._fit_boundary(left_segments)
        right = self._fit_boundary(right_segments)
        lane: LaneEstimate | None = None

        if left is not None or right is not None:
            bottom_y = height - 2
            lookahead_y = top_y
            assumed_width = cfg.assumed_lane_width_ratio * width

            def evaluate(line: tuple[float, float, float] | None, y: int) -> float | None:
                return None if line is None else line[0] * y + line[1]

            left_bottom = evaluate(left, bottom_y)
            left_top = evaluate(left, lookahead_y)
            right_bottom = evaluate(right, bottom_y)
            right_top = evaluate(right, lookahead_y)

            if left_bottom is None and right_bottom is not None:
                left_bottom = right_bottom - assumed_width
                right_reference = right_top if right_top is not None else right_bottom
                left_top = right_reference - assumed_width * 0.55
            if right_bottom is None and left_bottom is not None:
                right_bottom = left_bottom + assumed_width
                left_reference = left_top if left_top is not None else left_bottom
                right_top = left_reference + assumed_width * 0.55

            assert left_bottom is not None and right_bottom is not None
            assert left_top is not None and right_top is not None
            bottom_width = right_bottom - left_bottom
            top_width = right_top - left_top
            plausible = (
                cfg.minimum_lane_width_ratio * width
                <= bottom_width
                <= cfg.maximum_lane_width_ratio * width
                and top_width > width * 0.04
            )
            if plausible:
                bottom_center = float(np.clip((left_bottom + right_bottom) / 2.0, 0, width - 1))
                lookahead_center = float(np.clip((left_top + right_top) / 2.0, 0, width - 1))
                offset = float(np.clip((bottom_center - width / 2.0) / (width / 2.0), -1.0, 1.0))
                heading = math.atan2(
                    lookahead_center - bottom_center,
                    max(bottom_y - lookahead_y, 1),
                )
                both_sides = left is not None and right is not None
                support = (left[2] if left else 0.0) + (right[2] if right else 0.0)
                support_score = min(1.0, support / max(height * 2.2, 1.0))
                width_target = cfg.assumed_lane_width_ratio * width
                width_score = math.exp(-abs(bottom_width - width_target) / max(width * 0.28, 1.0))
                perspective_score = 1.0 if top_width <= bottom_width * 1.15 else 0.55
                confidence = float(
                    np.clip(
                        (0.52 if both_sides else 0.25)
                        + 0.24 * support_score
                        + 0.16 * width_score
                        + 0.08 * perspective_score,
                        0.0,
                        1.0,
                    )
                )
                lane = LaneEstimate(
                    center_offset=offset,
                    heading_error_rad=float(np.clip(heading, -math.pi / 2, math.pi / 2)),
                    curvature=0.0,
                    confidence=confidence,
                    center_x_px=bottom_center,
                    lookahead_x_px=lookahead_center,
                    lane_width_px=float(bottom_width),
                )

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return PerceptionResult(
            frame_sequence=frame.sequence,
            captured_at=frame.captured_at,
            image_shape=(height, width),
            backend=self.name,
            lane=lane,
            lane_mask=np.asarray(masked_edges > 0, dtype=bool),
            inference_ms=elapsed_ms,
            metadata={
                "line_count": 0 if lines is None else len(lines),
                "left_segment_count": len(left_segments),
                "right_segment_count": len(right_segments),
            },
        )
