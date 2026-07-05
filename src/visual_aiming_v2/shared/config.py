from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    """V2 最小配置集合，只保留当前运行链路真正需要的参数。"""

    # perception 层 — YOLO 检测器
    model_path: str = "models/best.pt"
    confidence: float = 0.5
    iou: float = 0.45
    device: str = "auto"

    # capture 层 — ROI 裁切尺寸
    image_width: int = 410
    image_height: int = 315

    # actuation 层 — 准星偏移（相对于 ROI 中心）
    crosshair_offset_x: int = 0
    crosshair_offset_y: int = 0

    # actuation 层 — 瞄点选择
    head_label: str = "head"       # head 类别标签名
    person_label: str = "person"   # person 类别标签名
    head_bias: float = 0.35        # head 框瞄准点垂直偏置（0=顶部, 0.5=中心, 1=底部）
    body_bias: float = 0.25        # person 框瞄准点垂直偏置（偏上估算头部位置）

    # actuation 层 — FPS 鼠标控制
    control_speed: float = 100.0        # 移动速度
    control_acceleration: float = 0.3   # 速度追随系数（0~1，越大越跟手）
    control_jitter: float = 0.5         # 抖动强度（模拟人手微颤）
    control_deadzone: float = 0.1       # 误差死区（像素）
