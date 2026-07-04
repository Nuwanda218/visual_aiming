"""运行编排层 — 循环驱动流水线。"""
from __future__ import annotations

from visual_aiming_v2.runtime.pipeline import Pipeline
from visual_aiming_v2.shared.ports import ActuationPort, CapturePort, DetectorPort, OutputPort
from visual_aiming_v2.shared.schemas import TickResult


def run(
    capture: CapturePort,
    detector: DetectorPort,
    actuator: ActuationPort,
    output: OutputPort,
    max_frames: int | None = None,
    diagnostics=None,  # 可选的 DiagnosticLogger 实例
) -> list[TickResult]:
    """驱动流水线循环，直到数据源结束或达到最大帧数。"""
    pipeline = Pipeline(detector=detector, actuator=actuator, output=output, diagnostics=diagnostics)
    results: list[TickResult] = []
    try:
        while max_frames is None or len(results) < max_frames:
            frame = capture.read()
            if frame is None:
                break
            results.append(pipeline.tick(frame))
    finally:
        capture.close()
        output.close()
    return results
