from __future__ import annotations

from visual_aiming_v2.shared.ports import ActuationPort, DetectorPort, OutputPort
from visual_aiming_v2.shared.schemas import Frame, TickResult


class Pipeline:
    def __init__(self, detector: DetectorPort, actuator: ActuationPort, output: OutputPort) -> None:
        self.detector = detector
        self.actuator = actuator
        self.output = output

    def tick(self, frame: Frame) -> TickResult:
        detections = list(self.detector.detect(frame.image))
        command = self.actuator.process(detections)
        self.output.apply(command)
        return TickResult(
            frame=frame,
            detections=detections,
            selected=None,
            command=command,
        )
