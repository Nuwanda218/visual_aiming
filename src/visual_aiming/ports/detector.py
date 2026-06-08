from __future__ import annotations

from typing import Protocol

from visual_aiming.core.schemas import DetectionPacket, FramePacket


class Detector(Protocol):
    name: str

    def detect(self, frame: FramePacket) -> DetectionPacket:
        """Detect targets in a frame and return normalized detections."""
        ...
