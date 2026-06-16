from __future__ import annotations

import math
from typing import Iterable, Optional

from visual_aiming.config.schema import TargetSelectionConfig
from visual_aiming.core.schemas import Detection, Point, SelectedTarget


class TargetSelector:
    def __init__(self, config: TargetSelectionConfig) -> None:
        self.config = config
        self.previous: Optional[Detection] = None

    def reset(self) -> None:
        self.previous = None

    def select(self, detections: Iterable[Detection], roi_center: Point) -> SelectedTarget:
        candidates = list(detections)
        if not candidates:
            self.previous = None
            return SelectedTarget(detection=None, score=math.inf, reason="no_detections")

        cx_roi, cy_roi = roi_center
        max_distance = max(1.0, math.hypot(cx_roi, cy_roi))
        preference = max(0.0, min(1.0, self.config.target_preference))
        head_id = self.config.head_class_id
        person_id = self.config.person_class_id

        scored = [
            (self._score_fast(item, cx_roi, cy_roi, max_distance, preference, head_id, person_id), item)
            for item in candidates
        ]
        scored.sort(key=lambda pair: pair[0][0])
        best_parts, best = scored[0]

        sticky = self._sticky_candidate(scored)
        chosen = best
        chosen_parts = best_parts
        held_sticky = False
        if sticky is not None and self.config.sticky_enabled:
            sticky_parts, sticky_detection = sticky
            margin = max(0.0, float(getattr(self.config, "sticky_switch_margin", self.config.switch_margin)))
            if sticky_detection is not best and best_parts[0] + margin >= sticky_parts[0]:
                chosen = sticky_detection
                chosen_parts = sticky_parts
            held_sticky = chosen is sticky_detection

        switched = self.previous is not None and not held_sticky and chosen is not self.previous
        self.previous = chosen
        return SelectedTarget(
            detection=chosen,
            score=chosen_parts[0],
            score_parts=chosen_parts[1],
            switched=switched,
            reason="selected",
        )

    def _score_fast(
        self, detection: Detection, cx_roi: int, cy_roi: int,
        max_distance: float, preference: float, head_id: int, person_id: int,
    ) -> tuple[float, dict[str, float]]:
        """热路径评分——减少属性访问和函数调用"""
        bbox = detection.bbox
        cx = bbox[0] + bbox[2] // 2
        cy = bbox[1] + bbox[3] // 2
        dx = cx - cx_roi
        dy = cy - cy_roi
        distance_score = min(1.0, math.sqrt(dx * dx + dy * dy) / max_distance)
        confidence_score = 1.0 - max(0.0, min(1.0, detection.confidence))
        class_id = detection.class_id
        if class_id == head_id:
            class_score = 1.0 - preference
        elif class_id == person_id:
            class_score = preference
        else:
            class_score = 1.5
        continuity = self._continuity_bonus(detection)
        switch_penalty = self._class_switch_penalty(detection)
        total = class_score * 0.60 + distance_score * 0.30 + confidence_score * 0.10 - continuity + switch_penalty
        return total, {
            "class": class_score,
            "distance": distance_score,
            "confidence": confidence_score,
            "continuity": -continuity,
            "switch_penalty": switch_penalty,
        }

    def _continuity_bonus(self, detection: Detection) -> float:
        if self.previous is None:
            return 0.0
        radius = max(1, self.config.history_radius)
        distance_sq = self._distance_sq(detection, self.previous)
        if distance_sq > radius * radius:
            return 0.0
        normalized = min(1.0, distance_sq / float(radius * radius))
        return (1.0 - normalized) * max(0.0, min(1.0, self.config.stickiness))

    def _class_switch_penalty(self, detection: Detection) -> float:
        if self.previous is None:
            return 0.0
        if self.previous.class_id is None or detection.class_id is None:
            return 0.0
        if self.previous.class_id == detection.class_id:
            return 0.0
        return max(0.0, self.config.class_switch_penalty)

    def _sticky_candidate(self, scored: list[tuple[tuple[float, dict[str, float]], Detection]]):
        if self.previous is None:
            return None
        radius_sq = max(1, self.config.history_radius) ** 2
        near_previous = [item for item in scored if self._distance_sq(item[1], self.previous) <= radius_sq]
        if not near_previous:
            return None
        near_previous.sort(key=lambda item: (self._distance_sq(item[1], self.previous), item[0][0]))
        return near_previous[0]

    def _distance_sq(self, left: Detection, right: Detection) -> int:
        lx, ly = left.center
        rx, ry = right.center
        return (lx - rx) ** 2 + (ly - ry) ** 2
