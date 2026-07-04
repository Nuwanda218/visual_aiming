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
) -> list[TickResult]:
    pipeline = Pipeline(detector=detector, actuator=actuator, output=output)
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
