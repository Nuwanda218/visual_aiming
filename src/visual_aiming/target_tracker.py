# -*- coding: utf-8 -*-
from __future__ import annotations

import math
from typing import Optional, Tuple


class TargetTracker:
    def __init__(
        self,
        smoothing_factor: float = 0.66,
        prediction_time: float = 0.025,
        stop_threshold: float = 10.0,
        reset_distance: float = 200.0,
    ) -> None:
        self.alpha = float(smoothing_factor)
        self.prediction_time = float(prediction_time)
        self.stop_threshold = float(stop_threshold)
        self.reset_distance = float(reset_distance)
        self.last_x: Optional[float] = None
        self.last_y: Optional[float] = None
        self.last_time: Optional[float] = None
        self.vx = 0.0
        self.vy = 0.0

    def reset(self) -> None:
        self.last_x = None
        self.last_y = None
        self.last_time = None
        self.vx = 0.0
        self.vy = 0.0

    def has_track(self) -> bool:
        return self.last_x is not None and self.last_y is not None and self.last_time is not None

    def has_recent_track(self, now: float, max_age_ms: float) -> bool:
        if not self.has_track() or self.last_time is None:
            return False
        return (now - self.last_time) * 1000.0 <= max(0.0, float(max_age_ms))

    def update(self, point: Tuple[int, int], now: float) -> Tuple[int, int]:
        x = float(point[0])
        y = float(point[1])
        if self.last_x is None or self.last_y is None or self.last_time is None:
            self.last_x = x
            self.last_y = y
            self.last_time = now
            self.vx = 0.0
            self.vy = 0.0
            return point

        dt = max(1e-4, min(now - self.last_time, 0.12))
        raw_vx = (x - self.last_x) / dt
        raw_vy = (y - self.last_y) / dt
        jump_distance = math.hypot(x - self.last_x, y - self.last_y)

        if self.reset_distance > 0 and jump_distance >= self.reset_distance:
            self.last_x = x
            self.last_y = y
            self.last_time = now
            self.vx = 0.0
            self.vy = 0.0
            return point

        dot_product = raw_vx * self.vx + raw_vy * self.vy
        if dot_product < 0:
            self.vx = raw_vx
            self.vy = raw_vy
        else:
            alpha = max(0.0, min(self.alpha, 0.98))
            self.vx = self.vx * alpha + raw_vx * (1.0 - alpha)
            self.vy = self.vy * alpha + raw_vy * (1.0 - alpha)

        if abs(self.vx) < self.stop_threshold:
            self.vx = 0.0
        if abs(self.vy) < self.stop_threshold:
            self.vy = 0.0

        self.last_x = x
        self.last_y = y
        self.last_time = now
        return self.predict(now)

    def predict(self, now: float) -> Tuple[int, int]:
        if self.last_x is None or self.last_y is None:
            return (0, 0)
        elapsed = 0.0 if self.last_time is None else max(0.0, min(now - self.last_time, 0.12))
        lead_time = max(0.0, min(self.prediction_time + elapsed, 0.15))
        pred_x = self.last_x + self.vx * lead_time
        pred_y = self.last_y + self.vy * lead_time
        return (int(round(pred_x)), int(round(pred_y)))
