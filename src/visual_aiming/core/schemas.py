from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

Point = Tuple[int, int]
Vector = Tuple[float, float]
BBox = Tuple[int, int, int, int]


@dataclass(frozen=True)
class RuntimeMode:
    active: bool = False
    firing: bool = False


@dataclass
class RuntimeTelemetry:
    wait_ms: float = 0.0
    frame_work_ms: float = 0.0
    display_fps: float = 0.0
    source_fps: float = 0.0
    active: bool = False


@dataclass
class FramePacket:
    frame: np.ndarray
    timestamp: float
    sequence: int
    roi_offset: Point
    roi_size: Point
    crosshair: Point
    source: str
    mode: RuntimeMode = field(default_factory=RuntimeMode)
    telemetry: Optional[RuntimeTelemetry] = None


@dataclass(slots=True)
class Detection:
    bbox: BBox
    confidence: float = 0.0
    class_id: Optional[int] = None
    class_name: str = "unknown"

    @property
    def x(self) -> int:
        return self.bbox[0]

    @property
    def y(self) -> int:
        return self.bbox[1]

    @property
    def w(self) -> int:
        return self.bbox[2]

    @property
    def h(self) -> int:
        return self.bbox[3]

    @property
    def center(self) -> Point:
        return (self.bbox[0] + self.bbox[2] // 2, self.bbox[1] + self.bbox[3] // 2)


@dataclass
class DetectionPacket:
    sequence: int
    detections: List[Detection]
    latency_ms: float
    detector_name: str
    fresh: bool = True


@dataclass
class SelectedTarget:
    detection: Optional[Detection]
    score: float
    score_parts: Dict[str, float] = field(default_factory=dict)
    switched: bool = False
    reason: str = "none"


@dataclass
class AimMeasurement:
    point: Optional[Point]
    crosshair: Point
    error: Vector
    valid: bool


@dataclass
class PredictedAim:
    point: Optional[Point]
    velocity: Vector
    confidence: float
    state: str


@dataclass
class ControlCommand:
    dx: int = 0
    dy: int = 0
    mode: str = "none"
    limited: bool = False
    reason: str = "inactive"

    @property
    def is_noop(self) -> bool:
        return self.dx == 0 and self.dy == 0 and self.mode in {"none", "relative"}


@dataclass
class LatencyBreakdown:
    detect_ms: float = 0.0
    select_ms: float = 0.0
    aim_ms: float = 0.0
    predict_ms: float = 0.0
    control_ms: float = 0.0
    total_ms: float = 0.0


@dataclass
class PipelineTickResult:
    sequence: int
    timestamp: float
    mode: RuntimeMode
    detections: DetectionPacket
    selected: SelectedTarget
    aim: AimMeasurement
    predicted: PredictedAim
    command: ControlCommand
    output_backend: str
    pipeline_latency_ms: float
    latency_breakdown: LatencyBreakdown = field(default_factory=LatencyBreakdown)
    telemetry: Optional[RuntimeTelemetry] = None
