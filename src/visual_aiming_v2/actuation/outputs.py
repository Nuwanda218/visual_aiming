"""控制执行层 — 输出后端。"""
from __future__ import annotations

from visual_aiming_v2.shared.schemas import Command


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
    """真实鼠标输出端：通过 SetCursorPos 移动系统鼠标。

    安全开关：必须显式传入 enable=True 才会真正移动鼠标。
    """

    def __init__(self, enable: bool = False) -> None:
        self._enable = enable
        if self._enable:
            from ctypes import POINTER, Structure, c_int, windll
            self._SetCursorPos = windll.user32.SetCursorPos

            class POINT(Structure):
                _fields_ = [("x", c_int), ("y", c_int)]

            self._GetCursorPos = windll.user32.GetCursorPos
            self._POINT = POINT
            self._POINTER = POINTER

    def apply(self, command: Command) -> None:
        if not self._enable:
            return
        if command.mode != "relative" or (command.dx == 0 and command.dy == 0):
            return
        # 获取当前鼠标位置，加上偏移量
        pt = self._POINT()
        self._GetCursorPos(self._POINTER(self._POINT)(pt))
        self._SetCursorPos(pt.x + command.dx, pt.y + command.dy)

    def close(self) -> None:
        pass
