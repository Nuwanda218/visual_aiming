from dataclasses import dataclass
from typing import Optional

from .schemas import Point


@dataclass
class RuntimeState:
    firing: bool = False
    last_aim_base: Optional[Point] = None
    last_capture_seq: int = -1

    def reset_tracking_state(self) -> None:
        self.firing = False
        self.last_aim_base = None
        self.last_capture_seq = -1

    def update_firing(self, left_held: bool) -> str:
        if left_held and not self.firing:
            self.firing = True
            return "started"
        if not left_held and self.firing:
            self.firing = False
            return "stopped"
        return "unchanged"

