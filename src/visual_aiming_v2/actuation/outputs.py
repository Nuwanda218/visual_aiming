"""控制执行层 — 输出后端。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes

from visual_aiming_v2.shared.schemas import Command

# ---- Win32 鼠标输入结构（SendInput 方式） ----

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_INPUT_MOUSE = 0
_MOUSEEVENTF_MOVE = 0x0001
_ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _INPUT_VALUE(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("value", _INPUT_VALUE),
    ]


try:
    _user32.SendInput.argtypes = (ctypes.wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
    _user32.SendInput.restype = ctypes.wintypes.UINT
except AttributeError:
    pass


def _send_relative_move(dx: int, dy: int) -> None:
    """通过 SendInput 发送相对鼠标移动事件，兼容 Raw Input 游戏。"""
    mouse_input = _MOUSEINPUT(
        dx=int(dx), dy=int(dy), mouseData=0,
        dwFlags=_MOUSEEVENTF_MOVE, time=0, dwExtraInfo=0,
    )
    inp = (_INPUT * 1)(_INPUT(type=_INPUT_MOUSE, value=_INPUT_VALUE(mi=mouse_input)))
    sent = _user32.SendInput(1, inp, ctypes.sizeof(_INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


# ---- 输出后端 ----


class NullOutput:
    """安全输出端：接收 Command 但不产生任何副作用。"""

    def apply(self, command: Command) -> None:
        pass

    def close(self) -> None:
        pass


class LogOutput:
    """记录输出端：用于测试和调试，保留每次生成的 Command。"""

    def __init__(self) -> None:
        self.commands: list[Command] = []

    def apply(self, command: Command) -> None:
        self.commands.append(command)

    def close(self) -> None:
        pass


class WinMouseOutput:
    """真实鼠标输出端：通过 SendInput 发送相对鼠标移动事件。

    使用 SendInput + MOUSEEVENTF_MOVE 发送相对位移，
    比 SetCursorPos 兼容性更好（支持 Raw Input 游戏）。
    安全开关：必须显式传入 enable=True 才会真正移动鼠标。
    """

    def __init__(self, enable: bool = False) -> None:
        self._enable = enable

    def apply(self, command: Command) -> None:
        if not self._enable:
            return
        if command.mode != "relative" or (command.dx == 0 and command.dy == 0):
            return
        _send_relative_move(command.dx, command.dy)

    def close(self) -> None:
        pass
