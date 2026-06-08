from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Optional

from visual_aiming.core.schemas import ControlCommand, PipelineTickResult

# 内存中最多保留的命令数量
_MAX_COMMANDS = 10_000


class LogOutput:
    name = "log"

    def __init__(self, path: Optional[str] = None, max_commands: int = _MAX_COMMANDS) -> None:
        self.path = Path(path) if path else None
        self.commands: deque[ControlCommand] = deque(maxlen=max_commands)
        self._handle = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a", encoding="utf-8")

    def apply(self, command: ControlCommand, result: PipelineTickResult) -> None:
        self.commands.append(command)
        if self._handle is not None:
            self._handle.write(f"{result.sequence},{command.mode},{command.dx},{command.dy},{command.reason}\n")
            self._handle.flush()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
