# -*- coding: utf-8 -*-
"""Detector adapters."""

__all__ = ["UltralyticsYoloDetector"]


def __getattr__(name: str):
    if name == "UltralyticsYoloDetector":
        from visual_aiming.adapters.detectors.ultralytics_yolo import UltralyticsYoloDetector
        return UltralyticsYoloDetector
    raise AttributeError(f"module 'visual_aiming.adapters.detectors' has no attribute {name!r}")
