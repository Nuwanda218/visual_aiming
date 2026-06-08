from __future__ import annotations

import math

from visual_aiming.config.schema import ControlConfig
from visual_aiming.core.schemas import ControlCommand, Vector


class RelativeController:
    def __init__(self, config: ControlConfig) -> None:
        self.config = config
        self.velocity = (0.0, 0.0)
        self.subpixel = (0.0, 0.0)
        # 预计算常量，避免每帧重复 max/min
        self._deadzone = max(0.0, config.deadzone)
        self._max_speed = max(0.0, config.max_speed)
        self._speed_gain = max(0.0, config.speed_gain)
        self._decel_radius = max(config.deadzone + 1.0, config.decel_radius)
        self._near_speed_scale = max(0.01, min(1.0, config.near_speed_scale))
        self._max_step = max(1.0, float(config.max_step))
        self._output_gain = config.output_gain

    def reset(self) -> None:
        self.velocity = (0.0, 0.0)
        self.subpixel = (0.0, 0.0)

    def update(self, error: Vector, active: bool, dt: float) -> ControlCommand:
        if not active:
            self.reset()
            return ControlCommand(mode="none", reason="inactive")

        dt = max(0.0005, min(float(dt), 0.05))
        ex, ey = error[0], error[1]
        distance = math.sqrt(ex * ex + ey * ey)
        if distance <= self._deadzone:
            self.reset()
            return ControlCommand(mode="none", reason="deadzone")

        target_speed = min(self._max_speed, distance * self._speed_gain)
        if distance < self._decel_radius:
            ratio = distance / self._decel_radius
            target_speed *= self._near_speed_scale + (1.0 - self._near_speed_scale) * ratio

        inv_dist = 1.0 / distance
        dir_x = ex * inv_dist
        dir_y = ey * inv_dist
        target_vx = dir_x * target_speed
        target_vy = dir_y * target_speed
        alpha = max(0.0, min(1.0, self.config.acceleration * dt))
        vx = self.velocity[0] + (target_vx - self.velocity[0]) * alpha
        vy = self.velocity[1] + (target_vy - self.velocity[1]) * alpha
        self.velocity = (vx, vy)

        gain_dt = self._output_gain * dt
        move_x = vx * gain_dt + self.subpixel[0]
        move_y = vy * gain_dt + self.subpixel[1]
        limited = False
        length = math.sqrt(move_x * move_x + move_y * move_y)
        if length > self._max_step:
            limited = True
            scale = self._max_step / length
            move_x *= scale
            move_y *= scale

        dx = int(round(move_x))
        dy = int(round(move_y))
        self.subpixel = (move_x - dx, move_y - dy)
        if dx == 0 and dy == 0:
            return ControlCommand(mode="relative", reason="subpixel")
        return ControlCommand(dx=dx, dy=dy, mode="relative", limited=limited, reason="tracking")
