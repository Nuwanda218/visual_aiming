from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    """V2 最小配置集合，只保留当前运行链路真正需要的参数。"""

    model_path: str = "models/best.pt"
    confidence: float = 0.5
    iou: float = 0.45
    device: str = "auto"
    image_width: int = 410
    image_height: int = 315
