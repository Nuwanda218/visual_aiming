from __future__ import annotations

import math

from visual_aiming.config.schema import ControlConfig
from visual_aiming.core.schemas import ControlCommand, Vector


class RelativeController:
    def __init__(self, config: ControlConfig) -> None:
        self.config = config
        self.velocity = (0.0, 0.0)
        self.subpixel = (0.0, 0.0)

    def reset(self) -> None:
        self.velocity = (0.0, 0.0)
        self.subpixel = (0.0, 0.0)

    def update(self, error: Vector, active: bool, dt: float) -> ControlCommand:
        if not active:
            self.reset()
            return ControlCommand(mode="none", reason="inactive")

        dt = max(0.0005, min(float(dt), 0.05))
        distance = math.hypot(error[0], error[1])
        if distance <= max(0.0, self.config.deadzone):
            self.reset()
            return ControlCommand(mode="none", reason="deadzone")

        target_speed = min(max(0.0, self.config.max_speed), distance * max(0.0, self.config.speed_gain))
        decel_radius = max(self.config.deadzone + 1.0, self.config.decel_radius)
        if distance < decel_radius:
            scale = max(0.01, min(1.0, self.config.near_speed_scale))
            ratio = max(0.0, min(1.0, distance / decel_radius))
            target_speed *= scale + (1.0 - scale) * ratio

        direction = (error[0] / distance, error[1] / distance)
        target_velocity = (direction[0] * target_speed, direction[1] * target_speed)
        alpha = max(0.0, min(1.0, self.config.acceleration * dt))
        self.velocity = (
            self.velocity[0] + (target_velocity[0] - self.velocity[0]) * alpha,
            self.velocity[1] + (target_velocity[1] - self.velocity[1]) * alpha,
        )

        move_x = self.velocity[0] * dt * self.config.output_gain + self.subpixel[0]
        move_y = self.velocity[1] * dt * self.config.output_gain + self.subpixel[1]
        limited = False
        max_step = max(1.0, float(self.config.max_step))
        length = math.hypot(move_x, move_y)
        if length > max_step:
            limited = True
            scale = max_step / length
            move_x *= scale
            move_y *= scale

        dx = int(round(move_x))
        dy = int(round(move_y))
        self.subpixel = (move_x - dx, move_y - dy)
        if dx == 0 and dy == 0:
            return ControlCommand(mode="relative", reason="subpixel")
        return ControlCommand(dx=dx, dy=dy, mode="relative", limited=limited, reason="tracking")
