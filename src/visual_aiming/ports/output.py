from __future__ import annotations

from typing import Protocol

from visual_aiming.core.schemas import ControlCommand, PipelineTickResult


class OutputBackend(Protocol):
    name: str

    def apply(self, command: ControlCommand, result: PipelineTickResult) -> None:
        """Apply or record one control command."""
        ...

    def close(self) -> None:
        """Release resources held by the output backend."""
        ...
