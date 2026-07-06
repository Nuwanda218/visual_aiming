"""控制执行层 — 目标锁定器（IOU 匹配 + 被动切换）。

锁定当前瞄准的目标，只要它还在就不切换。
只有当锁定目标从检测中消失（IOU 匹配不上）时，才被动切换到下一个最近的目标。
"""
from __future__ import annotations

from typing import Optional, Sequence

from visual_aiming_v2.shared.schemas import Detection, Point


def compute_iou(a: Detection, b: Detection) -> float:
    """计算两个检测框的 IOU（交叉比）。"""
    x1 = max(a.x, b.x)
    y1 = max(a.y, b.y)
    x2 = min(a.x + a.w, b.x + b.w)
    y2 = min(a.y + a.h, b.y + b.h)
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = a.w * a.h
    area_b = b.w * b.h
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


class TargetTracker:
    """目标锁定器：锁定当前目标，只在目标消失时被动切换。

    不做主动切换——即使新目标更近，只要锁定目标还在就继续瞄它。
    """

    def __init__(self, iou_threshold: float = 0.3) -> None:
        self.iou_threshold = iou_threshold
        self.locked_target: Optional[Detection] = None
        self.locked_frames: int = 0

    def update(
        self,
        detections: Sequence[Detection],
        crosshair: Point,
        select_fn,
    ) -> Optional[Detection]:
        """每帧调用：返回应该瞄准的目标。

        参数:
            detections: 当前帧所有检测结果
            crosshair: 准星位置
            select_fn: 选择最佳目标的函数 (detections, crosshair) -> Detection | None
        """
        if not detections:
            self.locked_target = None
            self.locked_frames = 0
            return None

        # 有锁定目标 → 用 IOU 在当前帧找它
        if self.locked_target is not None:
            matched = self._find_iou_match(detections)
            if matched is not None:
                # 找到了 → 继续瞄它（更新 bbox 为当前帧位置）
                self.locked_target = matched
                self.locked_frames += 1
                return matched
            # 找不到了 → 释放锁定，往下走选新目标

        # 没有锁定目标（首次 / 目标消失）→ 用 select_fn 选最佳目标并锁定
        best = select_fn(detections, crosshair)
        self.locked_target = best
        self.locked_frames = 1
        return best

    def reset(self) -> None:
        """热键停用时重置。"""
        self.locked_target = None
        self.locked_frames = 0

    def _find_iou_match(self, detections: Sequence[Detection]) -> Optional[Detection]:
        """在当前帧检测中找到与锁定目标 IOU 最高的匹配。"""
        best_iou = 0.0
        best_match = None
        for det in detections:
            iou = compute_iou(self.locked_target, det)
            if iou > best_iou:
                best_iou = iou
                best_match = det
        if best_iou >= self.iou_threshold:
            return best_match
        return None
