from __future__ import annotations

from typing import List, Optional

from visual_aiming.adapters.frame_sources.video_file import VideoFileFrameSource
from visual_aiming.app.realtime import create_pipeline
from visual_aiming.config.schema import ModularConfig
from visual_aiming.core.schemas import PipelineTickResult


def run_replay(config: ModularConfig, frame_source, detector=None, output_backend=None, diagnostics=None) -> List[PipelineTickResult]:
    """Run all frames from *frame_source* through the modular pipeline and return results."""
    pipeline = create_pipeline(config, detector=detector, output_backend=output_backend, diagnostics=diagnostics)
    results: List[PipelineTickResult] = []
    try:
        while True:
            frame = frame_source.read()
            if frame is None:
                break
            results.append(pipeline.tick(frame, now=frame.timestamp))
    finally:
        frame_source.close()
        pipeline.output_backend.close()
        if pipeline.diagnostics is not None:
            pipeline.diagnostics.close()
    return results


def run_video_file(config: ModularConfig, video_path: str, roi_offset=(0, 0), crosshair=(0, 0)) -> List[PipelineTickResult]:
    """Convenience: replay a video file with default pipeline."""
    source = VideoFileFrameSource(video_path, roi_offset=roi_offset, crosshair=crosshair)
    return run_replay(config, source)
