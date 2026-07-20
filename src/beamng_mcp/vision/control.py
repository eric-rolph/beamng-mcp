"""Lane-centering and confidence/hazard-aware longitudinal control."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .models import ControlCommand, LaneEstimate, PerceptionResult


@dataclass(frozen=True, slots=True)
class LaneCenterControllerConfig:
    proportional_offset: float = 0.85
    proportional_heading: float = 0.65
    derivative_offset: float = 0.05
    steering_deadband: float = 0.015
    steering_rate_limit_per_s: float = 2.8
    maximum_steering: float = 1.0
    default_dt_s: float = 0.05

    def __post_init__(self) -> None:
        if (
            min(
                self.proportional_offset,
                self.proportional_heading,
                self.derivative_offset,
            )
            < 0.0
        ):
            raise ValueError("controller gains cannot be negative")
        if not 0.0 <= self.steering_deadband < 1.0:
            raise ValueError("steering_deadband must be in [0, 1)")
        if self.steering_rate_limit_per_s <= 0.0:
            raise ValueError("steering_rate_limit_per_s must be positive")
        if not 0.0 < self.maximum_steering <= 1.0:
            raise ValueError("maximum_steering must be in (0, 1]")
        if self.default_dt_s <= 0.0:
            raise ValueError("default_dt_s must be positive")


class LaneCenterController:
    """Stateful PD steering controller with slew-rate limiting."""

    def __init__(self, config: LaneCenterControllerConfig | None = None) -> None:
        self.config = config or LaneCenterControllerConfig()
        self._previous_offset: float | None = None
        self._previous_steering = 0.0
        self._previous_at: float | None = None

    def reset(self) -> None:
        self._previous_offset = None
        self._previous_steering = 0.0
        self._previous_at = None

    def compute(self, lane: LaneEstimate, *, now: float) -> float:
        cfg = self.config
        dt = (
            cfg.default_dt_s
            if self._previous_at is None
            else max(1e-3, min(now - self._previous_at, 1.0))
        )
        derivative = (
            0.0
            if self._previous_offset is None
            else (lane.center_offset - self._previous_offset) / dt
        )
        requested = (
            cfg.proportional_offset * lane.center_offset
            + cfg.proportional_heading * lane.heading_error_rad
            + cfg.derivative_offset * derivative
        )
        requested = float(np.clip(requested, -cfg.maximum_steering, cfg.maximum_steering))
        if abs(requested) < cfg.steering_deadband:
            requested = 0.0

        maximum_delta = cfg.steering_rate_limit_per_s * dt
        steering = float(
            np.clip(
                requested,
                self._previous_steering - maximum_delta,
                self._previous_steering + maximum_delta,
            )
        )
        self._previous_offset = lane.center_offset
        self._previous_steering = steering
        self._previous_at = now
        return steering


@dataclass(frozen=True, slots=True)
class SpeedGovernorConfig:
    cruise_speed_mps: float = 13.9
    confidence_full_speed: float = 0.75
    confidence_stop: float = 0.18
    confidence_emergency: float = 0.06
    hazard_slowdown_start: float = 0.20
    hazard_stop: float = 0.78
    hazard_emergency: float = 0.92
    curvature_slowdown: float = 1.6
    throttle_gain: float = 0.20
    brake_gain: float = 0.28
    maximum_throttle: float = 0.75
    maximum_service_brake: float = 0.75
    emergency_brake: float = 1.0

    def __post_init__(self) -> None:
        if self.cruise_speed_mps <= 0.0:
            raise ValueError("cruise_speed_mps must be positive")
        confidence_thresholds_valid = (
            0.0
            <= self.confidence_emergency
            < self.confidence_stop
            < self.confidence_full_speed
            <= 1.0
        )
        if not confidence_thresholds_valid:
            raise ValueError("confidence thresholds must satisfy emergency < stop < full_speed")
        if not 0.0 <= self.hazard_slowdown_start < self.hazard_stop < self.hazard_emergency <= 1.0:
            raise ValueError("hazard thresholds must satisfy slowdown_start < stop < emergency")
        if self.curvature_slowdown < 0.0:
            raise ValueError("curvature_slowdown cannot be negative")
        if self.throttle_gain <= 0.0 or self.brake_gain <= 0.0:
            raise ValueError("speed gains must be positive")
        for name, value in (
            ("maximum_throttle", self.maximum_throttle),
            ("maximum_service_brake", self.maximum_service_brake),
            ("emergency_brake", self.emergency_brake),
        ):
            if not 0.0 < value <= 1.0:
                raise ValueError(f"{name} must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class SpeedDecision:
    target_speed_mps: float
    throttle: float
    brake: float
    emergency: bool
    reason: str


class SpeedGovernor:
    """Reduce speed as lane confidence falls or hazards become imminent."""

    def __init__(self, config: SpeedGovernorConfig | None = None) -> None:
        self.config = config or SpeedGovernorConfig()

    def decide(self, perception: PerceptionResult, *, current_speed_mps: float) -> SpeedDecision:
        if not math.isfinite(current_speed_mps) or current_speed_mps < 0.0:
            raise ValueError("current_speed_mps must be finite and non-negative")
        cfg = self.config
        confidence = perception.lane_confidence
        hazard = perception.hazard_score

        if perception.lane is None or confidence <= cfg.confidence_emergency:
            return SpeedDecision(
                target_speed_mps=0.0,
                throttle=0.0,
                brake=cfg.emergency_brake,
                emergency=True,
                reason="lane_lost",
            )
        if hazard >= cfg.hazard_emergency:
            return SpeedDecision(
                target_speed_mps=0.0,
                throttle=0.0,
                brake=cfg.emergency_brake,
                emergency=True,
                reason="imminent_hazard",
            )

        confidence_factor = float(
            np.clip(
                (confidence - cfg.confidence_stop)
                / (cfg.confidence_full_speed - cfg.confidence_stop),
                0.0,
                1.0,
            )
        )
        hazard_factor = float(
            np.clip(
                (cfg.hazard_stop - hazard) / (cfg.hazard_stop - cfg.hazard_slowdown_start),
                0.0,
                1.0,
            )
        )
        curvature_factor = 1.0 / (1.0 + cfg.curvature_slowdown * abs(perception.lane.curvature))
        target = cfg.cruise_speed_mps * min(
            confidence_factor,
            hazard_factor,
            curvature_factor,
        )
        if confidence <= cfg.confidence_stop:
            target = 0.0
        if hazard >= cfg.hazard_stop:
            target = 0.0

        speed_error = target - current_speed_mps
        throttle = float(np.clip(speed_error * cfg.throttle_gain, 0.0, cfg.maximum_throttle))
        brake = float(np.clip(-speed_error * cfg.brake_gain, 0.0, cfg.maximum_service_brake))
        if target <= 0.0 and current_speed_mps > 0.05:
            brake = max(brake, cfg.maximum_service_brake)

        if hazard >= cfg.hazard_slowdown_start:
            reason = "hazard_slowdown" if target > 0.0 else "hazard_stop"
        elif confidence < cfg.confidence_full_speed:
            reason = "low_confidence" if target > 0.0 else "confidence_stop"
        elif curvature_factor < 0.99:
            reason = "curve_slowdown"
        else:
            reason = "cruise"
        return SpeedDecision(
            target_speed_mps=float(max(target, 0.0)),
            throttle=throttle,
            brake=brake,
            emergency=False,
            reason=reason,
        )


class DrivingController:
    """Combine lateral and longitudinal decisions into one vehicle command."""

    def __init__(
        self,
        lane_controller: LaneCenterController | None = None,
        speed_governor: SpeedGovernor | None = None,
    ) -> None:
        self.lane_controller = lane_controller or LaneCenterController()
        self.speed_governor = speed_governor or SpeedGovernor()

    def reset(self) -> None:
        self.lane_controller.reset()

    def compute(
        self,
        perception: PerceptionResult,
        *,
        current_speed_mps: float,
        now: float,
    ) -> ControlCommand:
        speed = self.speed_governor.decide(
            perception,
            current_speed_mps=current_speed_mps,
        )
        if speed.emergency:
            self.lane_controller.reset()
            return ControlCommand.emergency_stop(
                issued_at=now,
                reason=speed.reason,
                brake=speed.brake,
                frame_sequence=perception.frame_sequence,
            )
        steering = (
            0.0
            if perception.lane is None
            else self.lane_controller.compute(perception.lane, now=now)
        )
        return ControlCommand(
            steering=steering,
            throttle=speed.throttle,
            brake=speed.brake,
            target_speed_mps=speed.target_speed_mps,
            issued_at=now,
            frame_sequence=perception.frame_sequence,
            emergency=False,
            reason=speed.reason,
            metadata={
                "lane_confidence": perception.lane_confidence,
                "hazard_score": perception.hazard_score,
                "backend": perception.backend,
            },
        )
