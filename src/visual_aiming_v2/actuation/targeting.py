from __future__ import annotations

import math
from typing import Optional, Sequence

from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.shared.schemas import Command, Detection, Point


def select_nearest(detections: Sequence[Detection], crosshair: Point) -> Optional[Detection]:
    """选择距离准星最近的目标，作为当前最小可用目标选择策略。"""

    if not detections:
        return None
    cx, cy = crosshair
    return min(detections, key=lambda d: math.hypot(d.center[0] - cx, d.center[1] - cy))


def compute_error(detection: Detection, crosshair: Point) -> tuple[int, int]:
    """计算目标中心相对准星的偏移量，正负号直接表达移动方向。"""

    cx, cy = detection.center
    return (cx - crosshair[0], cy - crosshair[1])


class Actuator:
    """把 Detection 序列转换为 Command，当前不直接执行任何系统鼠标动作。"""

    def __init__(self, config: Config) -> None:
        # 准星 = ROI 中心 + 偏移量，偏移量默认为 0
        offset_x = getattr(config, "crosshair_offset_x", 0)
        offset_y = getattr(config, "crosshair_offset_y", 0)
        self.crosshair = (config.image_width // 2 + offset_x, config.image_height // 2 + offset_y)

    def process(self, detections: Sequence[Detection]) -> Command:
        selected = select_nearest(detections, self.crosshair)
        if selected is None:
            return Command.noop("no_target")
        dx, dy = compute_error(selected, self.crosshair)
        if dx == 0 and dy == 0:
            return Command.noop("on_target")
        return Command(dx=dx, dy=dy, mode="relative", reason="tracking")
