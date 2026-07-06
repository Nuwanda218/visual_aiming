"""控制执行层 — FPS 风格鼠标速度控制器。

速度追随、近距离减速，无人为抖动。
"""
from __future__ import annotations

import math


class FpsController:
    """FPS 风格速度控制器：将目标位置转化为平滑的鼠标移动量。

    核心流程（每帧调用 update）：
    1. 计算当前位置到目标的距离和方向
    2. 速度追随（加速度平滑逼近目标速度）
    3. 近距离减速（防止过冲）
    4. 输出移动量 (dx, dy)
    """

    def __init__(
        self,
        speed: float = 180.0,
        acceleration: float = 0.45,
        deadzone: float = 3.0,
        near_radius: float = 80.0,
        near_speed_scale: float = 0.35,
    ) -> None:
        self.speed = speed
        self.acceleration = acceleration
        self.deadzone = deadzone
        self.near_radius = near_radius
        self.near_speed_scale = near_speed_scale
        # 内部速度状态
        self.velocity_x = 0.0
        self.velocity_y = 0.0

    def reset(self) -> None:
        """重置速度状态（目标丢失时调用）。"""
        self.velocity_x = 0.0
        self.velocity_y = 0.0

    def update(self, error_x: float, error_y: float) -> tuple[int, int]:
        """输入误差向量，输出平滑的鼠标移动量。"""
        dist = math.sqrt(error_x * error_x + error_y * error_y)

        # 死区：误差小于阈值时停止输出
        if dist < self.deadzone:
            self.reset()
            return (0, 0)

        # 计算目标方向
        target_angle = math.atan2(error_y, error_x)

        # 近距离减速：由 near_radius 显式控制，不再使用 speed * 3 隐式放大减速区
        speed_scale = 1.0
        near_radius = max(0.0, float(self.near_radius))
        if near_radius > 0.0 and dist < near_radius:
            ratio = max(0.0, min(1.0, dist / near_radius))
            near_scale = max(0.0, min(1.0, float(self.near_speed_scale)))
            speed_scale = near_scale + (1.0 - near_scale) * ratio

        # 目标速度
        target_speed = max(0.0, float(self.speed)) * speed_scale
        target_vel_x = math.cos(target_angle) * target_speed
        target_vel_y = math.sin(target_angle) * target_speed

        # 速度追随（加速度平滑）
        acceleration = max(0.0, min(1.0, float(self.acceleration)))
        self.velocity_x += (target_vel_x - self.velocity_x) * acceleration
        self.velocity_y += (target_vel_y - self.velocity_y) * acceleration

        return (int(round(self.velocity_x)), int(round(self.velocity_y)))
