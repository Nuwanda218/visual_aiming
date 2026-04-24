# -*- coding: utf-8 -*-
import math
from typing import Optional, Tuple


class AimPointCalculator:
    def __init__(self, config):
        self.config = config
        self.wakeup = None
        self.locked_aim = None
        self.track_lost_frames = 0
        self._prev_aim_global = None
        self._velocity = (0, 0)
        self.smooth_factor = getattr(config, 'aim_smooth_factor', 0.7)
        self.head_bias = getattr(config, 'head_bias', 0.25)
        self.aim_target_preference = self._clamp_preference(getattr(config, 'aim_target_preference', 1.0))
        self.max_step_pixels = max(1, int(getattr(config, 'max_step_pixels', 10)))
        self.unlock_distance = max(0, int(getattr(config, 'unlock_distance', 50)))
        self.max_track_lost = max(0, int(getattr(config, 'max_track_lost', 5)))
        self.firing_follow_x = float(getattr(config, 'firing_follow_x', 0.45))
        self.firing_follow_y = float(getattr(config, 'firing_follow_y', 0.65))
        self.firing_vertical_boost = float(getattr(config, 'firing_vertical_boost', 1.6))

    def set_wakeup(self, wakeup):
        self.wakeup = wakeup

    def calculate(self, target, roi_left: int, roi_top: int) -> Optional[Tuple[int, int]]:
        if self.wakeup is not None:
            active = self.wakeup.get_active()
            left_held = self.wakeup.get_left_held()
            if left_held and active:
                return self._calculate_during_firing(target, roi_left, roi_top)
            else:
                self._reset_firing_lock()

        if target is None:
            self._prev_aim_global = None
            return None

        raw_aim = self._compute_raw_aim(target, roi_left, roi_top)
        if raw_aim is None:
            self._prev_aim_global = None
            return None

        smoothed_aim = self._smooth_aim(raw_aim)
        return smoothed_aim

    def _calculate_during_firing(self, target, roi_left: int, roi_top: int) -> Optional[Tuple[int, int]]:
        if target is None:
            self.track_lost_frames += 1
            if self.locked_aim is not None and self.track_lost_frames <= self.max_track_lost:
                return self.locked_aim
            self._reset_firing_lock()
            return None

        raw_aim = self._compute_raw_aim(target, roi_left, roi_top)
        if raw_aim is None:
            self.track_lost_frames += 1
            if self.locked_aim is not None and self.track_lost_frames <= self.max_track_lost:
                return self.locked_aim
            self._reset_firing_lock()
            return None

        self.track_lost_frames = 0
        if self.locked_aim is None:
            self.locked_aim = raw_aim
            self._prev_aim_global = raw_aim
            return raw_aim

        self.locked_aim = self._follow_locked_aim(raw_aim)
        self._prev_aim_global = self.locked_aim
        return self.locked_aim

    def _follow_locked_aim(self, raw_aim: Tuple[int, int]) -> Tuple[int, int]:
        dx = raw_aim[0] - self.locked_aim[0]
        dy = raw_aim[1] - self.locked_aim[1]
        dist = math.hypot(dx, dy)

        if self.unlock_distance > 0 and dist >= self.unlock_distance:
            return raw_aim

        step_x = self._compute_follow_step(dx, self.firing_follow_x, self.max_step_pixels)

        y_limit = self.max_step_pixels
        if dy > 0:
            y_limit = max(y_limit, int(round(self.max_step_pixels * self.firing_vertical_boost)))
        step_y = self._compute_follow_step(dy, self.firing_follow_y, y_limit)

        next_x = self.locked_aim[0] + step_x
        next_y = self.locked_aim[1] + step_y
        return (next_x, next_y)

    def _compute_follow_step(self, delta: int, follow_factor: float, max_step: int) -> int:
        if delta == 0:
            return 0

        scaled_step = int(round(delta * follow_factor))
        if scaled_step == 0:
            scaled_step = 1 if delta > 0 else -1

        if abs(scaled_step) > max_step:
            scaled_step = max_step if scaled_step > 0 else -max_step

        return scaled_step

    def _compute_raw_aim(self, target, roi_left: int, roi_top: int) -> Optional[Tuple[int, int]]:
        if target is None:
            return None

        try:
            x, y, w, h = target.bbox
            cx = x + w // 2
            if self._is_head_target(target):
                cy = y + int(h * self._get_head_box_bias())
            else:
                cy = y + int(h * self._get_person_box_bias())

            aim_x = roi_left + cx
            aim_y = roi_top + cy
            return (aim_x, aim_y)
        except Exception:
            return None

    def _smooth_aim(self, raw_aim: Tuple[int, int]) -> Tuple[int, int]:
        if self._prev_aim_global is None:
            self._prev_aim_global = raw_aim
            return raw_aim

        factor = self.smooth_factor
        prev_x, prev_y = self._prev_aim_global
        raw_x, raw_y = raw_aim

        smooth_x = int(prev_x + (raw_x - prev_x) * factor)
        smooth_y = int(prev_y + (raw_y - prev_y) * factor)

        smoothed = (smooth_x, smooth_y)
        self._prev_aim_global = smoothed
        return smoothed

    def _is_head_target(self, target) -> bool:
        head_class_id = int(getattr(self.config, 'yolo_head_class_id', 0))
        return getattr(target, 'class_id', None) == head_class_id or getattr(target, 'class_name', '') == 'head'

    def _get_person_box_bias(self) -> float:
        body_bias = 0.45
        return body_bias - (body_bias - self.head_bias) * self.aim_target_preference

    def _get_head_box_bias(self) -> float:
        head_center_bias = 0.5
        low_pref_bias = 0.62
        return head_center_bias + (low_pref_bias - head_center_bias) * (1.0 - self.aim_target_preference)

    def _clamp_preference(self, value) -> float:
        return max(0.0, min(1.0, float(value)))

    def _reset_firing_lock(self):
        self.locked_aim = None
        self.track_lost_frames = 0
