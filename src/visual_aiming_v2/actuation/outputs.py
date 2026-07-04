from __future__ import annotations

from visual_aiming_v2.shared.schemas import Command


class NullOutput:
    def apply(self, command: Command) -> None:
        pass

    def close(self) -> None:
        pass


class LogOutput:
    def __init__(self) -> None:
        self.commands: list[Command] = []

    def apply(self, command: Command) -> None:
        self.commands.append(command)

    def close(self) -> None:
        pass
