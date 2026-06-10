from __future__ import annotations

from visual_aiming.adapters.detectors.ultralytics_yolo import UltralyticsYoloDetector
from visual_aiming.config.schema import DetectorConfig
from visual_aiming.vision.detection import TargetDetector


def create_ultralytics_detector(config: DetectorConfig) -> UltralyticsYoloDetector:
    return UltralyticsYoloDetector(config, TargetDetector())
