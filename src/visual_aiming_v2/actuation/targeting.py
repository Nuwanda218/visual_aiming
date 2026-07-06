"""控制执行层 — 目标选择、瞄点计算、指令生成。"""
from __future__ import annotations

import math
from typing import Optional, Sequence

from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.shared.schemas import Command, Detection, Point
from visual_aiming_v2.actuation.control import FpsController
from visual_aiming_v2.actuation.aim_filter import AimSmoother
from visual_aiming_v2.actuation.tracker import TargetTracker


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
        aim_y = detection.y + int(detection.h * head_bias)
    else:
        aim_y = detection.y + int(detection.h * body_bias)

    return (aim_x, aim_y)


def compute_error(aim_point: Point, crosshair: Point) -> tuple[int, int]:
    """计算瞄准点相对准星的偏移量。"""
    return (aim_point[0] - crosshair[0], aim_point[1] - crosshair[1])


class Actuator:
    """把 Detection 序列转换为 Command。

    内部流水线：
    TargetTracker(P6) → compute_aim_point → AimSmoother(P5) → compute_error → FpsController → Command
    """

    def __init__(self, config: Config, use_controller: bool = False) -> None:
        # 准星 = ROI 中心 + 偏移量
        capture = config.capture
        targeting = config.targeting
        self.crosshair = (
            capture.image_width // 2 + capture.crosshair_offset_x,
            capture.image_height // 2 + capture.crosshair_offset_y,
        )

        # 瞄点选择参数
        self.head_label = targeting.head_label
        self.person_label = targeting.person_label
        self.head_bias = targeting.head_bias
        self.body_bias = targeting.body_bias

        # P6: 目标锁定器（Step 4 会替换为 Detection 框匹配）
        self.tracker = TargetTracker()

        # P5: 当前仍保留已有 Kalman，Step 5 先诊断再决定是否替换
        self.smoother = AimSmoother(hold_frames=config.smoothing.hold_frames)

        # FPS 速度控制器（可选；Step 6 会接入 near_radius/near_speed_scale）
        self.controller: FpsController | None = None
        if use_controller:
            self.controller = FpsController(
                speed=config.control.speed,
                acceleration=config.control.acceleration,
                deadzone=config.control.deadzone,
            )

        # 最近一次 process 的中间状态（供诊断日志读取）
        self.last_raw_aim: Optional[Point] = None
        self.last_smoothed_aim: Optional[Point] = None

    def process(self, detections: Sequence[Detection]) -> Command:
        # P6: 目标锁定（只在目标消失时被动切换）
        select_fn = lambda dets, ch: select_target(dets, ch, self.head_label, self.person_label)
        selected = self.tracker.update(detections, self.crosshair, select_fn)

        if selected is not None:
            raw_aim = compute_aim_point(selected, self.head_label, self.head_bias, self.body_bias)
        else:
            raw_aim = None

        # P5: Kalman 平滑（目标丢失时 hold 预测）
        smoothed_aim = self.smoother.smooth(raw_aim)

        # 记录中间状态（供诊断日志读取）
        self.last_raw_aim = raw_aim
        self.last_smoothed_aim = smoothed_aim

        if smoothed_aim is None:
            if self.controller is not None:
                self.controller.reset()
            return Command.noop("no_target")

        # 计算误差
        ex, ey = compute_error(smoothed_aim, self.crosshair)

        # 通过 FPS 控制器平滑输出，或直接输出原始误差
        if self.controller is not None:
            dx, dy = self.controller.update(float(ex), float(ey))
        else:
            dx, dy = ex, ey

        if dx == 0 and dy == 0:
            return Command.noop("on_target")

        return Command(dx=dx, dy=dy, mode="relative", reason="tracking")
