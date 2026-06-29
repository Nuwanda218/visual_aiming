from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

Point = Tuple[int, int]


@dataclass(slots=True)
class Frame:
    image: Any
    sequence: int
    timestamp: float


@dataclass(slots=True)
class Detection:
    x: int
    y: int
    w: int
    h: int
    confidence: float
    label: str = "unknown"

    @property
    def center(self) -> Point:
        return (self.x + self.w // 2, self.y + self.h // 2)


@dataclass(slots=True)
class Command:
    dx: int = 0
    dy: int = 0
    mode: str = "none"
    reason: str = "noop"

    @classmethod
    def noop(cls, reason: str) -> Command:
        return cls(dx=0, dy=0, mode="none", reason=reason)
