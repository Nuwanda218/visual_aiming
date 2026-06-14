from __future__ import annotations

from visual_aiming.adapters.detectors.factory import create_ultralytics_detector
from visual_aiming.adapters.frame_sources.screen_capture import ScreenFrameSource
from visual_aiming.adapters.outputs.factory import create_output_backend
from visual_aiming.config.schema import ModularConfig
from visual_aiming.core.metrics import JsonlDiagnostics
from visual_aiming.core.pipeline import ModularPipeline
from visual_aiming.core.runtime_runner import RuntimeRunner


def create_pipeline(config: ModularConfig, frame_source=None, detector=None, output_backend=None, diagnostics=None) -> ModularPipeline:
    detector = detector or create_ultralytics_detector(config.detector)
    output_backend = output_backend or create_output_backend(config.output)
    if diagnostics is None and config.diagnostics.enabled and config.diagnostics.jsonl_path:
        diagnostics = JsonlDiagnostics(config.diagnostics.jsonl_path, config.diagnostics.summary_path or None)
    return ModularPipeline(config, detector, output_backend, diagnostics)


def create_screen_frame_source(config: ModularConfig) -> ScreenFrameSource:
    roi_w, roi_h = config.frame.roi_size
    return ScreenFrameSource(
        config.frame,
        roi_offset=(0, 0),
        crosshair=(roi_w // 2, roi_h // 2),
    )


def run_realtime(
    config: ModularConfig,
    frame_source=None,
    detector=None,
    output_backend=None,
    diagnostics=None,
    pipeline=None,
    max_frames=None,
):
    frame_source = frame_source or create_screen_frame_source(config)
    pipeline = pipeline or create_pipeline(
        config,
        frame_source=frame_source,
        detector=detector,
        output_backend=output_backend,
        diagnostics=diagnostics,
    )
    runner = RuntimeRunner(frame_source, pipeline)
    try:
        return runner.run(max_frames=max_frames)
    finally:
        runner.close()
        output = getattr(pipeline, "output_backend", None)
        if output is not None:
            output.close()
        pipeline_diagnostics = getattr(pipeline, "diagnostics", None)
        if pipeline_diagnostics is not None:
            pipeline_diagnostics.close()
