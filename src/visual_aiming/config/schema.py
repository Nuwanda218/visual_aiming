from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

# Point 类型的唯一定义在 core/schemas.py，这里保持本地别名以避免循环导入
Point = Tuple[int, int]


@dataclass
class RuntimeConfig:
    poll_fps: float = 120.0
    detect_fps: float = 30.0
    idle_detect_fps: float = 8.0
    detect_only_new_frames: bool = True


@dataclass
class FrameSourceConfig:
    roi_size: Point = (410, 315)
    capture_fps: float = 30.0
    source: str = "screen"
    video_path: str = ""


@dataclass
class DetectorConfig:
    backend: str = "ultralytics"
    model_path: str = "models/best.pt"
    confidence: float = 0.5
    iou: float = 0.45
    device: str = "auto"
    half: bool = True
    imgsz: int = 416


@dataclass
class TargetSelectionConfig:
    head_class_id: int = 0
    person_class_id: int = 1
    target_preference: float = 0.85
    sticky_enabled: bool = True
    stickiness: float = 0.28
    history_radius: int = 120
    sticky_switch_margin: float = 0.08
    switch_margin: float = 0.08
    class_switch_penalty: float = 0.05


@dataclass
class AimConfig:
    head_bias: float = 0.25
    body_bias: float = 0.45


@dataclass
class PredictionConfig:
    alpha: float = 0.65
    beta: float = 0.20
    lead_time: float = 0.025
    reset_distance: float = 200.0
    max_hold_ms: float = 160.0
    firing_freeze: bool = True


@dataclass
class ControlConfig:
    deadzone: float = 2.0
    speed_gain: float = 42.0
    max_speed: float = 7200.0
    acceleration: float = 52.0
    decel_radius: float = 135.0
    near_speed_scale: float = 0.10
    max_step: int = 48
    output_gain: float = 1.0


@dataclass
class OutputConfig:
    backend: str = "null"
    enable_real_mouse: bool = False
    command_mode: str = "relative"
    mouse_method: str = "set_cursor"
    log_path: str = ""


@dataclass
class DiagnosticsConfig:
    enabled: bool = True
    jsonl_path: str = ""
    summary_path: str = ""


@dataclass
class ModularConfig:
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    frame: FrameSourceConfig = field(default_factory=FrameSourceConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    target_selection: TargetSelectionConfig = field(default_factory=TargetSelectionConfig)
    aim: AimConfig = field(default_factory=AimConfig)
    prediction: PredictionConfig = field(default_factory=PredictionConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    diagnostics: DiagnosticsConfig = field(default_factory=DiagnosticsConfig)
