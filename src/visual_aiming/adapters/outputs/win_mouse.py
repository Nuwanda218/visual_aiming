from __future__ import annotations

import ctypes
import ctypes.wintypes
from typing import Callable, Optional

from visual_aiming.core.schemas import ControlCommand, PipelineTickResult

user32 = ctypes.windll.user32
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUT_VALUE(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("value", _INPUT_VALUE),
    ]


def get_cursor_pos(user32=user32) -> tuple[int, int]:
    point = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return (int(point.x), int(point.y))


def set_cursor_pos(x: int, y: int, user32=user32) -> None:
    user32.SetCursorPos(int(x), int(y))


def send_relative_move_setcursor(dx: int, dy: int, user32=user32) -> None:
    current_x, current_y = get_cursor_pos(user32)
    set_cursor_pos(current_x + int(dx), current_y + int(dy), user32)


def send_relative_move_sendinput(dx: int, dy: int, user32=user32) -> None:
    mouse_input = MOUSEINPUT(
        dx=int(dx),
        dy=int(dy),
        mouseData=0,
        dwFlags=MOUSEEVENTF_MOVE,
        time=0,
        dwExtraInfo=0,
    )
    inputs = (INPUT * 1)(INPUT(type=INPUT_MOUSE, value=_INPUT_VALUE(mi=mouse_input)))
    sent = user32.SendInput(1, inputs, ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError()


def create_mouse_sender(method: str = "set_cursor") -> Callable[[int, int], None]:
    normalized = method.strip().lower().replace("-", "_")
    if normalized in {"set_cursor", "setcursor", "cursor"}:
        return send_relative_move_setcursor
    if normalized in {"sendinput", "send_input"}:
        return send_relative_move_sendinput
    raise ValueError(f"unsupported mouse sender method: {method}")


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
