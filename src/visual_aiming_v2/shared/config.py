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
