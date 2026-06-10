from __future__ import annotations

from visual_aiming.adapters.detectors.factory import create_ultralytics_detector
from visual_aiming.adapters.outputs.factory import create_output_backend
from visual_aiming.config.schema import ModularConfig
from visual_aiming.core.metrics import JsonlDiagnostics
from visual_aiming.core.pipeline import ModularPipeline


def create_pipeline(config: ModularConfig, frame_source=None, detector=None, output_backend=None, diagnostics=None) -> ModularPipeline:
    detector = detector or create_ultralytics_detector(config.detector)
    output_backend = output_backend or create_output_backend(config.output)
    if diagnostics is None and config.diagnostics.enabled and config.diagnostics.jsonl_path:
        diagnostics = JsonlDiagnostics(config.diagnostics.jsonl_path, config.diagnostics.summary_path or None)
    return ModularPipeline(config, detector, output_backend, diagnostics)
