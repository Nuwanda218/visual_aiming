"""控制执行层 — 目标锁定器（Detection 框匹配 + 被动切换）。

锁定当前瞄准的目标，只要当前帧还能找到与上一锁定 Detection
中心位置和尺寸相近的框，就继续锁定。只有锁定框确认消失后，
才被动切换到下一个目标。
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

from visual_aiming_v2.shared.schemas import Detection, Point


def detection_boxes_match(
    locked: Detection,
    candidate: Detection,
    match_distance_ratio: float = 0.75,
    min_match_distance: float = 18.0,
    size_ratio_min: float = 0.55,
    size_ratio_max: float = 1.8,
) -> bool:
    """判断 candidate 是否仍是 locked 对应的同一个检测框。

    本阶段不依赖 IOU，而是使用更直观的 Detection 框中心距离和尺寸比例。
    """
    if locked.w <= 0 or locked.h <= 0 or candidate.w <= 0 or candidate.h <= 0:
        return False

    lx, ly = locked.center
    cx, cy = candidate.center
    center_distance = math.hypot(cx - lx, cy - ly)
    locked_diag = math.hypot(locked.w, locked.h)
    allowed_distance = max(float(min_match_distance), locked_diag * max(0.0, float(match_distance_ratio)))
    if center_distance > allowed_distance:
        return False

    width_ratio = candidate.w / float(locked.w)
    height_ratio = candidate.h / float(locked.h)
    min_ratio = max(0.01, float(size_ratio_min))
    max_ratio = max(min_ratio, float(size_ratio_max))
    return min_ratio <= width_ratio <= max_ratio and min_ratio <= height_ratio <= max_ratio


class TargetTracker:
    """目标锁定器：锁定当前 Detection，只在确认消失时被动切换。"""

    def __init__(
        self,
        match_distance_ratio: float = 0.75,
        min_match_distance: float = 18.0,
        size_ratio_min: float = 0.55,
        size_ratio_max: float = 1.8,
        lost_frame_grace: int = 2,
    ) -> None:
        self.match_distance_ratio = match_distance_ratio
        self.min_match_distance = min_match_distance
        self.size_ratio_min = size_ratio_min
        self.size_ratio_max = size_ratio_max
        self.lost_frame_grace = max(0, int(lost_frame_grace))
        self.locked_target: Optional[Detection] = None
        self.locked_frames: int = 0
        self.lost_frames: int = 0
        self.switched: bool = False
        self.has_measurement_this_frame: bool = False

    def update(
        self,
        detections: Sequence[Detection],
        crosshair: Point,
        select_fn,
    ) -> Optional[Detection]:
        """每帧调用：返回本帧可用的新测量目标，或 None。"""
        self.switched = False
        self.has_measurement_this_frame = False

        if not detections:
            return self._handle_missing_detections()

        if self.locked_target is not None:
            matched = self._find_detection_match(detections)
            if matched is not None:
                self.locked_target = matched
                self.locked_frames += 1
                self.lost_frames = 0
                self.has_measurement_this_frame = True
                return matched

            previous = self.locked_target
            best = select_fn(detections, crosshair)
            self.locked_target = best
            self.locked_frames = 1 if best is not None else 0
            self.lost_frames = 0
            self.switched = best is not None and best is not previous
            self.has_measurement_this_frame = best is not None
            return best

        best = select_fn(detections, crosshair)
        self.locked_target = best
        self.locked_frames = 1 if best is not None else 0
        self.lost_frames = 0
        self.has_measurement_this_frame = best is not None
        return best

    def reset(self) -> None:
        """热键停用时重置。"""
        self.locked_target = None
        self.locked_frames = 0
        self.lost_frames = 0
        self.switched = False
        self.has_measurement_this_frame = False

    def _handle_missing_detections(self) -> Optional[Detection]:
        if self.locked_target is None:
            self.locked_frames = 0
            self.lost_frames = 0
            return None

        self.lost_frames += 1
        self.has_measurement_this_frame = False
        if self.lost_frames > self.lost_frame_grace:
            self.locked_target = None
            self.locked_frames = 0
            return None
        return None

    def _find_detection_match(self, detections: Sequence[Detection]) -> Optional[Detection]:
        if self.locked_target is None:
            return None

        matches = [
            det for det in detections
            if detection_boxes_match(
                self.locked_target,
                det,
                self.match_distance_ratio,
                self.min_match_distance,
                self.size_ratio_min,
                self.size_ratio_max,
            )
        ]
        if not matches:
            return None

        lx, ly = self.locked_target.center
        return min(matches, key=lambda det: math.hypot(det.center[0] - lx, det.center[1] - ly))
