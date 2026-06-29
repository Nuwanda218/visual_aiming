from __future__ import annotations

from typing import Optional, Protocol, Sequence

from visual_aiming_v2.shared.schemas import Command, Detection, Frame


class CapturePort(Protocol):
    def read(self) -> Optional[Frame]: ...
    def close(self) -> None: ...


class DetectorPort(Protocol):
    def detect(self, image) -> Sequence[Detection]: ...


class ActuationPort(Protocol):
    def process(self, detections: Sequence[Detection]) -> Command: ...


class OutputPort(Protocol):
    def apply(self, command: Command) -> None: ...
    def close(self) -> None: ...
