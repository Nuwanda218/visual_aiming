from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from visual_aiming.core.schemas import ControlCommand, PipelineTickResult


class LogOutput:
    name = "log"

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(path) if path else None
        self.commands: List[ControlCommand] = []
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
