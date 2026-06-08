from __future__ import annotations

import ctypes
from typing import Callable, Optional

from visual_aiming.core.schemas import ControlCommand, PipelineTickResult

MOUSEEVENTF_MOVE = 0x0001


def send_relative_move(dx: int, dy: int) -> None:
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, int(dx), int(dy), 0, 0)


class WinMouseOutput:
    name = "win_mouse"

    def __init__(self, enable_real_mouse: bool, sender: Optional[Callable[[int, int], None]] = None) -> None:
        self.enable_real_mouse = bool(enable_real_mouse)
        self.sender = sender or send_relative_move

    def apply(self, command: ControlCommand, result: PipelineTickResult) -> None:
        if not self.enable_real_mouse:
            return
        if command.mode != "relative":
            return
        if command.dx == 0 and command.dy == 0:
            return
        self.sender(command.dx, command.dy)

    def close(self) -> None:
        return None
