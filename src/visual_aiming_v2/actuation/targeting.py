"""控制执行层 — 目标选择、瞄点计算、指令生成。"""
from __future__ import annotations

import math
from typing import Optional, Sequence

from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.shared.schemas import Command, Detection, Point
from visual_aiming_v2.actuation.control import FpsController


def select_target(
    detections: Sequence[Detection],
    crosshair: Point,
    head_label: str = "head",
    person_label: str = "person",
) -> Optional[Detection]:
    """有头选头，无头选 person，都没有返回 None。同类中选距离准星最近的。"""
    if not detections:
        return None

    cx, cy = crosshair

    # 按类别分组
    heads = [d for d in detections if d.label == head_label]
    persons = [d for d in detections if d.label == person_label]

    # 优先选 head
    candidates = heads if heads else persons
    if not candidates:
        # 既不是 head 也不是 person，退回选最近的
        candidates = list(detections)

    return min(candidates, key=lambda d: math.hypot(d.center[0] - cx, d.center[1] - cy))


def compute_aim_point(
    detection: Detection,
    head_label: str = "head",
    head_bias: float = 0.35,
    body_bias: float = 0.25,
) -> Point:
    """计算瞄准点：head 框偏上，person 框估算头部位置。"""
    aim_x = detection.x + detection.w // 2

    if detection.label == head_label:
        # head 框：中心偏上（bias=0.35 表示从顶部 35% 位置）
        aim_y = detection.y + int(detection.h * head_bias)
    else:
        # person 框：顶部偏下（bias=0.25 表示从顶部 25% 位置，估算头部）
        aim_y = detection.y + int(detection.h * body_bias)

    return (aim_x, aim_y)


def compute_error(aim_point: Point, crosshair: Point) -> tuple[int, int]:
    """计算瞄准点相对准星的偏移量。"""
    return (aim_point[0] - crosshair[0], aim_point[1] - crosshair[1])


class Actuator:
    """把 Detection 序列转换为 Command。支持直接误差输出或 FPS 速度控制。"""

    def __init__(self, config: Config, use_controller: bool = False) -> None:
        # 准星 = ROI 中心 + 偏移量
        offset_x = getattr(config, "crosshair_offset_x", 0)
        offset_y = getattr(config, "crosshair_offset_y", 0)
        self.crosshair = (config.image_width // 2 + offset_x, config.image_height // 2 + offset_y)

        # 瞄点选择参数
        self.head_label = getattr(config, "head_label", "head")
        self.person_label = getattr(config, "person_label", "person")
        self.head_bias = getattr(config, "head_bias", 0.35)
        self.body_bias = getattr(config, "body_bias", 0.25)

        # FPS 速度控制器（可选）
        self.controller: FpsController | None = None
        if use_controller:
            self.controller = FpsController(
                speed=getattr(config, "control_speed", 100.0),
                acceleration=getattr(config, "control_acceleration", 0.3),
                deadzone=getattr(config, "control_deadzone", 2.0),
            )

    def process(self, detections: Sequence[Detection]) -> Command:
        # 有头选头，无头选 person
        selected = select_target(detections, self.crosshair, self.head_label, self.person_label)
        if selected is None:
            if self.controller is not None:
                self.controller.reset()
            return Command.noop("no_target")

        # 计算瞄准点（带偏置）
        aim_point = compute_aim_point(selected, self.head_label, self.head_bias, self.body_bias)

        # 计算误差
        ex, ey = compute_error(aim_point, self.crosshair)

        # 通过 FPS 控制器平滑输出，或直接输出原始误差
        if self.controller is not None:
            dx, dy = self.controller.update(float(ex), float(ey))
        else:
            dx, dy = ex, ey

        if dx == 0 and dy == 0:
            return Command.noop("on_target")

        return Command(dx=dx, dy=dy, mode="relative", reason="tracking")
