# -*- coding: utf-8 -*-
import time


class DetectionScheduler:
    def __init__(self, config):
        self.config = config
        self.last_detection_time = 0.0

    def reset(self):
        self.last_detection_time = 0.0

    def due(self, active: bool, firing: bool, now: float | None = None) -> bool:
        if not active:
            return False

        now = time.perf_counter() if now is None else now
        interval = self._interval(active, firing)
        if interval <= 0:
            return False

        if self.last_detection_time <= 0.0:
            return True
        return now - self.last_detection_time >= interval

    def mark(self, now: float | None = None):
        self.last_detection_time = time.perf_counter() if now is None else now

    def _interval(self, active: bool, firing: bool) -> float:
        fps = self._fps(active, firing)
        return 1.0 / fps if fps > 0 else 0.0

    def _fps(self, active: bool, firing: bool) -> float:
        if not active:
            return 0.0

        default_fps = float(getattr(self.config, "detect_fps", getattr(self.config, "capture_fps", 30)))
        if firing:
            return max(1.0, float(getattr(self.config, "firing_detect_fps", default_fps)))

        if bool(getattr(self.config, "idle_detect_enabled", True)):
            return max(1.0, float(getattr(self.config, "idle_detect_fps", max(1.0, default_fps / 4.0))))

        return max(1.0, default_fps)
