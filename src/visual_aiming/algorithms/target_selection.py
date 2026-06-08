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

        scored = [(self._score(item, roi_center), item) for item in candidates]
        scored.sort(key=lambda pair: pair[0][0])
        best_parts, best = scored[0]

        sticky = self._sticky_candidate(scored)
        chosen = best
        chosen_parts = best_parts
        if sticky is not None:
            sticky_parts, sticky_detection = sticky
            if sticky_detection is not best and best_parts[0] + self.config.switch_margin >= sticky_parts[0]:
                chosen = sticky_detection
                chosen_parts = sticky_parts

        radius_sq = max(1, self.config.history_radius) ** 2
        switched = self.previous is not None and self._distance_sq(chosen, self.previous) > radius_sq
        self.previous = chosen
        return SelectedTarget(
            detection=chosen,
            score=chosen_parts[0],
            score_parts=chosen_parts[1],
            switched=switched,
            reason="selected",
        )

    def _score(self, detection: Detection, roi_center: Point) -> tuple[float, dict[str, float]]:
        cx, cy = detection.center
        distance = math.hypot(cx - roi_center[0], cy - roi_center[1])
        max_distance = max(1.0, math.hypot(roi_center[0], roi_center[1]))
        distance_score = min(1.0, distance / max_distance)
        confidence_score = 1.0 - max(0.0, min(1.0, detection.confidence))
        class_score = self._class_score(detection)
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

    def _class_score(self, detection: Detection) -> float:
        preference = max(0.0, min(1.0, self.config.target_preference))
        if detection.class_id == self.config.head_class_id:
            return 1.0 - preference
        if detection.class_id == self.config.person_class_id:
            return preference
        return 1.5

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
