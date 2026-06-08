from __future__ import annotations

import math
from typing import Optional

from visual_aiming.config.schema import PredictionConfig
from visual_aiming.core.schemas import AimMeasurement, Point, PredictedAim, RuntimeMode


class AlphaBetaPredictor:
    def __init__(self, config: PredictionConfig) -> None:
        self.config = config
        self.position: Optional[tuple[float, float]] = None
        self.velocity = (0.0, 0.0)
        self.last_time: Optional[float] = None

    def reset(self) -> None:
        self.position = None
        self.velocity = (0.0, 0.0)
        self.last_time = None

    def update(self, measurement: AimMeasurement, mode: RuntimeMode, now: float) -> PredictedAim:
        if not mode.active:
            self.reset()
            return PredictedAim(point=None, velocity=(0.0, 0.0), confidence=0.0, state="inactive")

        if measurement.valid and measurement.point is not None:
            return self._accept_measurement(measurement.point, mode, now)
        return self._predict_without_measurement(now)

    def _accept_measurement(self, point: Point, mode: RuntimeMode, now: float) -> PredictedAim:
        x, y = float(point[0]), float(point[1])
        if self.position is None or self.last_time is None:
            self.position = (x, y)
            self.velocity = (0.0, 0.0)
            self.last_time = now
            return PredictedAim(point=point, velocity=self.velocity, confidence=1.0, state="tracking")

        raw_dt = now - self.last_time
        # 时钟回退或异常跳跃时，重置追踪器
        if raw_dt < 0.0:
            self.position = (x, y)
            self.velocity = (0.0, 0.0)
            self.last_time = now
            return PredictedAim(point=point, velocity=self.velocity, confidence=1.0, state="reset")

        dt = max(1e-4, min(raw_dt, 0.12))
        predicted_x = self.position[0] + self.velocity[0] * dt
        predicted_y = self.position[1] + self.velocity[1] * dt
        residual_x = x - predicted_x
        residual_y = y - predicted_y

        if self.config.reset_distance > 0 and math.hypot(residual_x, residual_y) >= self.config.reset_distance:
            self.position = (x, y)
            self.velocity = (0.0, 0.0)
            self.last_time = now
            return PredictedAim(point=point, velocity=self.velocity, confidence=1.0, state="reset")

        alpha = max(0.01, min(0.95, self.config.alpha))
        beta = max(0.0, min(0.80, self.config.beta))
        self.position = (predicted_x + alpha * residual_x, predicted_y + alpha * residual_y)
        if not (mode.firing and self.config.firing_freeze):
            self.velocity = (
                self.velocity[0] + beta * residual_x / dt,
                self.velocity[1] + beta * residual_y / dt,
            )
        else:
            self.velocity = (0.0, 0.0)
        self.last_time = now
        return self._prediction(now, "tracking", 1.0)

    def _predict_without_measurement(self, now: float) -> PredictedAim:
        if self.position is None or self.last_time is None:
            return PredictedAim(point=None, velocity=(0.0, 0.0), confidence=0.0, state="lost")
        age_ms = max(0.0, (now - self.last_time) * 1000.0)
        if age_ms > max(0.0, self.config.max_hold_ms):
            self.reset()
            return PredictedAim(point=None, velocity=(0.0, 0.0), confidence=0.0, state="lost")
        confidence = max(0.0, 1.0 - age_ms / max(1.0, self.config.max_hold_ms))
        prediction = self._prediction(now, "held", confidence)
        return prediction

    def _prediction(self, now: float, state: str, confidence: float) -> PredictedAim:
        if self.position is None:
            return PredictedAim(point=None, velocity=(0.0, 0.0), confidence=0.0, state="lost")
        elapsed = 0.0 if self.last_time is None else max(0.0, min(now - self.last_time, 0.12))
        lead = max(0.0, min(self.config.lead_time + elapsed, 0.15))
        x = self.position[0] + self.velocity[0] * lead
        y = self.position[1] + self.velocity[1] * lead
        return PredictedAim(point=(int(round(x)), int(round(y))), velocity=self.velocity, confidence=confidence, state=state)
