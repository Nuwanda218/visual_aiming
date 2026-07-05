"""控制执行层 — FPS 风格鼠标速度控制器。

直接复用 C:\\Users\\Nuwanda\\Desktop\\main.py 中 MouseController 的核心逻辑：
速度追随、近距离减速、方向微扰、抖动模拟。
"""
from __future__ import annotations

import math
import random


class FpsController:
    """FPS 风格速度控制器：将目标位置转化为平滑的鼠标移动量。

    核心流程（每帧调用 update）：
    1. 计算当前位置到目标的距离和方向
    2. 方向加微扰（模拟人手抖动）
    3. 速度追随（加速度平滑逼近目标速度）
    4. 近距离减速（防止过冲）
    5. 输出移动量 (dx, dy)
    """

    def __init__(
        self,
        speed: float = 100.0,
        acceleration: float = 0.3,
        jitter_intensity: float = 0.5,
        deadzone: float = 0.1,
    ) -> None:
        self.speed = speed
        self.acceleration = acceleration
        self.jitter_intensity = jitter_intensity
        self.deadzone = deadzone
        # 内部速度状态
        self.velocity_x = 0.0
        self.velocity_y = 0.0

    def reset(self) -> None:
        """重置速度状态（目标丢失时调用）。"""
        self.velocity_x = 0.0
        self.velocity_y = 0.0

    def update(self, error_x: float, error_y: float) -> tuple[int, int]:
        """输入误差向量，输出平滑的鼠标移动量。

        参数:
            error_x: 瞄准点相对准星的水平偏移（像素）
            error_y: 瞄准点相对准星的垂直偏移（像素）

        返回:
            (dx, dy) 本帧应移动的鼠标像素量
        """
        dist = math.sqrt(error_x * error_x + error_y * error_y)

        # 死区：误差太小不动
        if dist < self.deadzone:
            self.reset()
            return (0, 0)

        # 计算目标方向（加微扰模拟人手抖动）
        target_angle = math.atan2(error_y, error_x)
        deviation_factor = min(1.0, dist / (self.speed * 5))
        angle_deviation = random.uniform(-0.3, 0.3) * deviation_factor
        perturbed_angle = target_angle + angle_deviation

        # 目标速度
        target_vel_x = math.cos(perturbed_angle) * self.speed
        target_vel_y = math.sin(perturbed_angle) * self.speed

        # 速度追随（加速度平滑）
        self.velocity_x += (target_vel_x - self.velocity_x) * self.acceleration
        self.velocity_y += (target_vel_y - self.velocity_y) * self.acceleration

        # 近距离减速（防止过冲）
        current_speed = math.sqrt(self.velocity_x ** 2 + self.velocity_y ** 2)
        if current_speed > 0 and dist < self.speed * 3:
            decel_factor = max(0.1, dist / (self.speed * 3))
            self.velocity_x *= decel_factor
            self.velocity_y *= decel_factor

        # 加微抖动
        dx = self.velocity_x + random.uniform(-self.jitter_intensity, self.jitter_intensity)
        dy = self.velocity_y + random.uniform(-self.jitter_intensity, self.jitter_intensity)

        return (int(round(dx)), int(round(dy)))
