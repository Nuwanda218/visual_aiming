from __future__ import annotations

import ctypes
import ctypes.wintypes
from typing import Callable

user32 = ctypes.WinDLL("user32", use_last_error=True)
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


try:
    user32.SendInput.argtypes = (ctypes.wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = ctypes.wintypes.UINT
    user32.GetCursorPos.argtypes = (ctypes.POINTER(ctypes.wintypes.POINT),)
    user32.GetCursorPos.restype = ctypes.wintypes.BOOL
    user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
    user32.SetCursorPos.restype = ctypes.wintypes.BOOL
except AttributeError:
    pass


def get_cursor_pos(user32=user32) -> tuple[int, int]:
    point = ctypes.wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError(ctypes.get_last_error())
    return (int(point.x), int(point.y))


def set_cursor_pos(x: int | float, y: int | float, user32=user32) -> None:
    if not user32.SetCursorPos(int(round(x)), int(round(y))):
        raise ctypes.WinError(ctypes.get_last_error())


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
        raise ctypes.WinError(ctypes.get_last_error())


def create_mouse_sender(method: str = "set_cursor") -> Callable[[int, int], None]:
    normalized = method.strip().lower().replace("-", "_")
    if normalized in {"set_cursor", "setcursor", "cursor"}:
        return send_relative_move_setcursor
    if normalized in {"sendinput", "send_input"}:
        return send_relative_move_sendinput
    raise ValueError(f"unsupported mouse sender method: {method}")
