from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


Point = Tuple[int, int]
BBox = Tuple[int, int, int, int]


@dataclass
class VisionFrame:
    frame: np.ndarray
    timestamp: float
    sequence: int


@dataclass
class DetectionState:
    target: Optional[object]
    fresh: bool
    frame: Optional[np.ndarray] = None
    timestamp: float = 0.0
    sequence: int = -1


@dataclass
class ControlTarget:
    target: Optional[Point]
    crosshair: Optional[Point]
    has_measurement: bool
    active: bool


@dataclass
class PipelineResult:
    control: ControlTarget
    aim_point: Optional[Point]
    debug_bbox: Optional[BBox]
    used_tracker_prediction: bool = False
