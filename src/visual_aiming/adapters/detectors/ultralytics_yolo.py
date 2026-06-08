from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Optional

from visual_aiming.config.schema import DetectorConfig
from visual_aiming.core.schemas import Detection, DetectionPacket, FramePacket


class UltralyticsYoloDetector:
    name = "ultralytics"

    def __init__(self, config: DetectorConfig, legacy_detector) -> None:
        if legacy_detector is None:
            raise ValueError("UltralyticsYoloDetector requires a legacy_detector instance, got None")
        self.config = config
        self.legacy_detector = legacy_detector

    def detect(self, frame: FramePacket) -> DetectionPacket:
        started = time.perf_counter()
        legacy_config = self._legacy_config()
        target = self.legacy_detector.detect(
            frame.frame,
            legacy_config,
            roi_center=(frame.roi_size[0] // 2, frame.roi_size[1] // 2),
            firing=frame.mode.firing,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        detections = []
        if target is not None:
            detections.append(Detection(
                bbox=target.bbox,
                confidence=float(getattr(target, "confidence", 0.0)),
                class_id=getattr(target, "class_id", None),
                class_name=str(getattr(target, "class_name", "unknown")),
            ))
        fresh = bool(getattr(self.legacy_detector, "last_result_fresh", True))
        return DetectionPacket(frame.sequence, detections, latency_ms, self.name, fresh=fresh)

    def _legacy_config(self):
        return SimpleNamespace(
            yolo_model_path=self.config.model_path,
            yolo_conf_threshold=self.config.confidence,
            yolo_iou_threshold=self.config.iou,
            yolo_device=self.config.device,
            yolo_half=self.config.half,
            yolo_imgsz=self.config.imgsz,
            yolo_head_class_id=0,
            yolo_person_class_id=1,
            target_stickiness=0.0,
            target_history_radius=1,
            target_switch_margin=0.0,
            target_class_switch_penalty=0.0,
            aim_target_preference=1.0,
            yolo_skip_frames=0,
            firing_yolo_skip_frames=0,
        )
