from __future__ import annotations

from typing import List, Optional

from visual_aiming.adapters.frame_sources.video_file import VideoFileFrameSource
from visual_aiming.app.realtime import create_pipeline
from visual_aiming.config.schema import ModularConfig
from visual_aiming.core.runtime_runner import RuntimeRunner
from visual_aiming.core.schemas import PipelineTickResult


def run_replay(
    config: ModularConfig,
    frame_source,
    detector=None,
    output_backend=None,
    diagnostics=None,
    pipeline=None,
) -> List[PipelineTickResult]:
    """Run all frames from *frame_source* through the modular pipeline and return results."""
    pipeline = pipeline or create_pipeline(config, detector=detector, output_backend=output_backend, diagnostics=diagnostics)
    runner = RuntimeRunner(frame_source, pipeline, clock=lambda: None)
    try:
        results: List[PipelineTickResult] = runner.run()
    finally:
        runner.close()
        output = getattr(pipeline, "output_backend", None)
        if output is not None:
            output.close()
        pipeline_diagnostics = getattr(pipeline, "diagnostics", None)
        if pipeline_diagnostics is not None:
            pipeline_diagnostics.close()
    return results


def run_video_file(config: ModularConfig, video_path: str, roi_offset=(0, 0), crosshair=(0, 0)) -> List[PipelineTickResult]:
    """Convenience: replay a video file with default pipeline."""
    source = VideoFileFrameSource(video_path, roi_offset=roi_offset, crosshair=crosshair)
    return run_replay(config, source)
