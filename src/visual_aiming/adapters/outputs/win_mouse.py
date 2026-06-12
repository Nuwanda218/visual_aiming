from __future__ import annotations

from typing import Callable, Optional

from visual_aiming.common.mouse_sender import (
    INPUT,
    INPUT_MOUSE,
    MOUSEEVENTF_MOVE,
    MOUSEINPUT,
    create_mouse_sender,
    get_cursor_pos,
    send_relative_move_sendinput,
    send_relative_move_setcursor,
    set_cursor_pos,
)
from visual_aiming.core.schemas import ControlCommand, PipelineTickResult


send_relative_move = send_relative_move_setcursor


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
