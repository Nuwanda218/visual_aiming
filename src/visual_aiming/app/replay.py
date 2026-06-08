from __future__ import annotations

from typing import List, Optional

from visual_aiming.adapters.detectors.ultralytics_yolo import UltralyticsYoloDetector
from visual_aiming.adapters.frame_sources.video_file import VideoFileFrameSource
from visual_aiming.app.realtime import create_output_backend
from visual_aiming.config.schema import ModularConfig
from visual_aiming.core.metrics import JsonlDiagnostics
from visual_aiming.core.pipeline import ModularPipeline
from visual_aiming.core.schemas import PipelineTickResult


def run_replay(config: ModularConfig, frame_source, detector=None, output_backend=None, diagnostics=None) -> List[PipelineTickResult]:
    detector = detector or UltralyticsYoloDetector(config.detector)
    output_backend = output_backend or create_output_backend(config.output)
    if diagnostics is None and config.diagnostics.enabled and config.diagnostics.jsonl_path:
        diagnostics = JsonlDiagnostics(config.diagnostics.jsonl_path, config.diagnostics.summary_path or None)
    pipeline = ModularPipeline(config, detector, output_backend, diagnostics)
    results: List[PipelineTickResult] = []
    try:
        while True:
            frame = frame_source.read()
            if frame is None:
                break
            results.append(pipeline.tick(frame, now=frame.timestamp))
    finally:
        frame_source.close()
        output_backend.close()
        if diagnostics is not None:
            diagnostics.close()
    return results


def run_video_file(config: ModularConfig, video_path: str, roi_offset=(0, 0), crosshair=(0, 0)) -> List[PipelineTickResult]:
    source = VideoFileFrameSource(video_path, roi_offset=roi_offset, crosshair=crosshair)
    return run_replay(config, source)
