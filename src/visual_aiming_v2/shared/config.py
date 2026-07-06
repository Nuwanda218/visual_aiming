from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any, Mapping


@dataclass
class PerceptionConfig:
    """perception 层 — YOLO 检测器。"""

    model_path: str = "models/best.pt"
    confidence: float = 0.5
    iou: float = 0.45
    device: str = "auto"


@dataclass
class CaptureConfig:
    """capture 层 — ROI 裁切和准星偏移。"""

    image_width: int = 410
    image_height: int = 315
    crosshair_offset_x: int = 0
    crosshair_offset_y: int = 0


@dataclass
class TargetingConfig:
    """actuation 层 — 目标类别和瞄点偏置。"""

    head_label: str = "head"
    person_label: str = "person"
    head_bias: float = 0.35
    body_bias: float = 0.25


@dataclass
class TrackerConfig:
    """actuation 层 — Detection 框匹配锁定参数。"""

    match_distance_ratio: float = 0.75
    min_match_distance: float = 18.0
    size_ratio_min: float = 0.55
    size_ratio_max: float = 1.8
    lost_frame_grace: int = 2


@dataclass
class SmoothingConfig:
    """actuation 层 — 瞄点平滑参数。"""

    enabled: bool = True
    alpha: float = 0.55
    jitter_radius: float = 2.0
    stable_frames: int = 2
    hold_frames: int = 3


@dataclass
class ControlConfig:
    """actuation 层 — FPS 鼠标速度控制参数。"""

    speed: float = 180.0
    acceleration: float = 0.45
    deadzone: float = 3.0
    near_radius: float = 80.0
    near_speed_scale: float = 0.35


@dataclass
class RuntimeConfig:
    """runtime 层 — 主循环参数。"""

    detect_fps: float = 30.0


@dataclass
class OutputConfig:
    """output 层 — 输出后端。"""

    backend: str = "null"


@dataclass
class Config:
    """V2 配置根对象，按架构层分组，避免 V1 平铺字段污染。"""

    perception: PerceptionConfig = field(default_factory=PerceptionConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    targeting: TargetingConfig = field(default_factory=TargetingConfig)
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    smoothing: SmoothingConfig = field(default_factory=SmoothingConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


def config_to_mapping(config: Config) -> dict[str, Any]:
    """转换为可写入 config.v2.json 的嵌套 dict。"""

    return asdict(config)


def config_from_mapping(data: Mapping[str, Any]) -> Config:
    """从嵌套 dict 创建 Config，缺失字段使用默认值。"""

    config = Config()
    if not isinstance(data, Mapping):
        return config
    for item in fields(config):
        section_data = data.get(item.name)
        section = getattr(config, item.name)
        if isinstance(section_data, Mapping) and is_dataclass(section):
            _apply_section(section, section_data)
    return config


def _apply_section(section: object, values: Mapping[str, Any]) -> None:
    for item in fields(section):
        if item.name not in values:
            continue
        current = getattr(section, item.name)
        value = values[item.name]
        try:
            if isinstance(current, bool):
                value = bool(value)
            elif isinstance(current, int) and not isinstance(current, bool):
                value = int(value)
            elif isinstance(current, float):
                value = float(value)
            elif isinstance(current, str):
                value = str(value)
        except (TypeError, ValueError):
            continue
        setattr(section, item.name, value)
