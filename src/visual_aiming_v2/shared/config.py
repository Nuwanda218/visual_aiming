from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    model_path: str = "models/best.pt"
    confidence: float = 0.5
    iou: float = 0.45
    device: str = "auto"
    image_width: int = 410
    image_height: int = 315
