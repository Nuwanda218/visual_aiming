from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

Point = Tuple[int, int]


@dataclass(slots=True)
class Frame:
    """capture 层向后传递的单帧数据包。"""

    image: Any
    sequence: int
    timestamp: float


@dataclass(slots=True)
class Detection:
    """perception 层输出的目标框，统一使用 x/y/w/h 表示矩形区域。"""

    x: int
    y: int
    w: int
    h: int
    confidence: float
    label: str = "unknown"

    @property
    def center(self) -> Point:
        """把左上角坐标转换为中心点，actuation 层用它计算瞄点误差。"""
        return (self.x + self.w // 2, self.y + self.h // 2)


@dataclass(slots=True)
class Command:
    """actuation 层输出给 output 层的控制指令。"""

    dx: int = 0
    dy: int = 0
    mode: str = "none"
    reason: str = "noop"

    @classmethod
    def noop(cls, reason: str) -> Command:
        return cls(dx=0, dy=0, mode="none", reason=reason)


@dataclass
class TickResult:
    """runtime 层单次 tick 的完整结果，便于测试、诊断和后续回放。"""

    frame: Frame
    detections: Sequence[Detection]
    selected: Optional[Detection]
    command: Command
    raw_aim: Optional[Point] = None
    smoothed_aim: Optional[Point] = None
