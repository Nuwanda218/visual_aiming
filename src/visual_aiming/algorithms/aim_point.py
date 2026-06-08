from __future__ import annotations

from typing import Optional

from visual_aiming.config.schema import AimConfig
from visual_aiming.core.schemas import AimMeasurement, Detection, Point


class AimStrategy:
    def __init__(self, config: AimConfig, head_class_id: int) -> None:
        self.config = config
        self.head_class_id = head_class_id

    def measure(self, detection: Optional[Detection], roi_offset: Point, crosshair: Point) -> AimMeasurement:
        if detection is None:
            return AimMeasurement(point=None, crosshair=crosshair, error=(0.0, 0.0), valid=False)

        bias = self._vertical_bias(detection)
        roi_x = detection.x + detection.w // 2
        roi_y = detection.y + int(detection.h * bias)
        point = (roi_offset[0] + roi_x, roi_offset[1] + roi_y)
        error = (float(point[0] - crosshair[0]), float(point[1] - crosshair[1]))
        return AimMeasurement(point=point, crosshair=crosshair, error=error, valid=True)

    def _vertical_bias(self, detection: Detection) -> float:
        if detection.class_id == self.head_class_id or detection.class_name == "head":
            return self.config.head_bias
        return self.config.body_bias
