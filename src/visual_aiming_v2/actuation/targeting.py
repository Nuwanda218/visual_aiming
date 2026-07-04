from __future__ import annotations

import math
from typing import Optional, Sequence

from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.shared.schemas import Command, Detection, Point


def select_nearest(detections: Sequence[Detection], crosshair: Point) -> Optional[Detection]:
    if not detections:
        return None
    cx, cy = crosshair
    return min(detections, key=lambda d: math.hypot(d.center[0] - cx, d.center[1] - cy))


def compute_error(detection: Detection, crosshair: Point) -> tuple[int, int]:
    cx, cy = detection.center
    return (cx - crosshair[0], cy - crosshair[1])


class Actuator:
    def __init__(self, config: Config) -> None:
        self.crosshair = (config.image_width // 2, config.image_height // 2)

    def process(self, detections: Sequence[Detection]) -> Command:
        selected = select_nearest(detections, self.crosshair)
        if selected is None:
            return Command.noop("no_target")
        dx, dy = compute_error(selected, self.crosshair)
        if dx == 0 and dy == 0:
            return Command.noop("on_target")
        return Command(dx=dx, dy=dy, mode="relative", reason="tracking")
