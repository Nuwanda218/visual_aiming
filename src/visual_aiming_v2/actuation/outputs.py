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
