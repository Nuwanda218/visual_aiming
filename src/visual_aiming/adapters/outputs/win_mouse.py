from __future__ import annotations

import ctypes
import ctypes.wintypes
from typing import Callable, Optional

from visual_aiming.core.schemas import ControlCommand, PipelineTickResult

user32 = ctypes.windll.user32


def get_cursor_pos(user32=user32) -> tuple[int, int]:
    point = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return (int(point.x), int(point.y))


def set_cursor_pos(x: int, y: int, user32=user32) -> None:
    user32.SetCursorPos(int(x), int(y))


def send_relative_move(dx: int, dy: int, user32=user32) -> None:
    current_x, current_y = get_cursor_pos(user32)
    set_cursor_pos(current_x + int(dx), current_y + int(dy), user32)


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
