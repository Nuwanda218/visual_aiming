from __future__ import annotations

from typing import Callable, Optional

from visual_aiming.adapters.detectors.ultralytics_yolo import UltralyticsYoloDetector
from visual_aiming.adapters.outputs.log_output import LogOutput
from visual_aiming.adapters.outputs.null_output import NullOutput
from visual_aiming.adapters.outputs.win_mouse import WinMouseOutput
from visual_aiming.config.schema import ModularConfig, OutputConfig
from visual_aiming.core.metrics import JsonlDiagnostics
from visual_aiming.core.pipeline import ModularPipeline


def create_output_backend(output_config: OutputConfig, mouse_sender: Optional[Callable[[int, int], None]] = None):
    if output_config.backend == "log":
        return LogOutput(output_config.log_path or None)
    if output_config.backend == "win_mouse" and output_config.enable_real_mouse:
        return WinMouseOutput(enable_real_mouse=True, sender=mouse_sender)
    return NullOutput()


def create_pipeline(config: ModularConfig, frame_source=None, detector=None, output_backend=None, diagnostics=None) -> ModularPipeline:
    detector = detector or UltralyticsYoloDetector(config.detector)
    output_backend = output_backend or create_output_backend(config.output)
    if diagnostics is None and config.diagnostics.enabled and config.diagnostics.jsonl_path:
        diagnostics = JsonlDiagnostics(config.diagnostics.jsonl_path, config.diagnostics.summary_path or None)
    return ModularPipeline(config, detector, output_backend, diagnostics)
