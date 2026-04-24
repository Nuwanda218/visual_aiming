# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from ultralytics import YOLO

from resource_path import resource_path

BBox = Tuple[int, int, int, int]


@dataclass
class DetectedTarget:
    """Detection result in ROI coordinates: (x, y, width, height)."""

    bbox: BBox
    confidence: float = 0.0

    @property
    def x(self) -> int:
        return self.bbox[0]

    @property
    def y(self) -> int:
        return self.bbox[1]

    @property
    def w(self) -> int:
        return self.bbox[2]

    @property
    def h(self) -> int:
        return self.bbox[3]

    @property
    def center_x(self) -> int:
        return self.x + self.w // 2

    @property
    def center_y(self) -> int:
        return self.y + self.h // 2

    @property
    def aspect_ratio(self) -> float:
        return self.h / self.w if self.w > 0 else 0.0

    @property
    def area(self) -> int:
        return self.w * self.h


class TargetDetector:
    """
    YOLOv8 detector.

    Backward-compatible class API:
        TargetDetector().detect(frame, config, roi_center=None) -> DetectedTarget | None

    Simple module API:
        detection.detect(frame, config) -> (xc, yc, w, h) | None
    """

    def __init__(self):
        self.model = None
        self.model_path = None
        self.device = None
        self.frame_count = 0
        self.last_result: Optional[DetectedTarget] = None

    def set_debug(self, enabled: bool):
        # Kept for compatibility. Debug drawing is handled by DebugVisualizer.
        return None

    def load_model(self, model_path: str, device: str = "cpu"):
        resolved_path = resource_path(model_path)
        print(f"[YOLO] 加载模型: {resolved_path} | device={device}")
        self.model = YOLO(resolved_path)
        self.model.to(device)
        self.model_path = model_path
        self.device = device
        print("[YOLO] 模型加载完成")

    def detect(
        self,
        frame_bgr: np.ndarray,
        config,
        roi_center: Optional[Tuple[int, int]] = None,
    ) -> Optional[DetectedTarget]:
        if frame_bgr is None:
            return None

        self._ensure_model(config)

        self.frame_count += 1
        skip_frames = max(0, int(getattr(config, "yolo_skip_frames", 0)))
        if skip_frames > 0 and self.last_result is not None:
            if (self.frame_count - 1) % (skip_frames + 1) != 0:
                return self.last_result

        conf_threshold = float(getattr(config, "yolo_conf_threshold", 0.5))
        iou_threshold = float(getattr(config, "yolo_iou_threshold", 0.45))

        try:
            results = self.model(
                frame_bgr,
                conf=conf_threshold,
                iou=iou_threshold,
                verbose=False,
            )
        except Exception as exc:
            print(f"[YOLO] 推理失败: {exc}")
            self.last_result = None
            return None

        boxes = results[0].boxes if results else None
        if boxes is None or len(boxes) == 0:
            self.last_result = None
            return None

        if roi_center is None:
            h, w = frame_bgr.shape[:2]
            roi_center = (w // 2, h // 2)

        best_target = self._select_best_box(boxes, roi_center)
        self.last_result = best_target
        return best_target

    def detect_bbox(
        self,
        frame_bgr: np.ndarray,
        config,
        roi_center: Optional[Tuple[int, int]] = None,
    ) -> Optional[BBox]:
        target = self.detect(frame_bgr, config, roi_center)
        return target.bbox if target is not None else None

    def _ensure_model(self, config):
        model_path = getattr(config, "yolo_model_path", "models/best.pt")
        device = getattr(config, "yolo_device", "cpu")
        if self.model is None or self.model_path != model_path or self.device != device:
            self.load_model(model_path, device)

    def _select_best_box(self, boxes, roi_center: Tuple[int, int]) -> Optional[DetectedTarget]:
        roi_cx, roi_cy = roi_center
        best_target = None
        best_score = None

        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].detach().cpu().numpy().tolist()
            x = max(0, int(round(x1)))
            y = max(0, int(round(y1)))
            w = max(0, int(round(x2 - x1)))
            h = max(0, int(round(y2 - y1)))
            if w <= 0 or h <= 0:
                continue

            confidence = float(box.conf[0].detach().cpu().item())
            cx = x + w // 2
            cy = y + h // 2
            distance_sq = (cx - roi_cx) ** 2 + (cy - roi_cy) ** 2

            # Prefer the target nearest to the ROI center, then higher confidence.
            score = (distance_sq, -confidence)
            if best_score is None or score < best_score:
                best_score = score
                best_target = DetectedTarget((x, y, w, h), confidence)

        return best_target


_default_detector = TargetDetector()


def detect(frame_bgr: np.ndarray, config) -> Optional[BBox]:
    """Simple public interface: return (x, y, width, height) in ROI coordinates."""
    return _default_detector.detect_bbox(frame_bgr, config)
