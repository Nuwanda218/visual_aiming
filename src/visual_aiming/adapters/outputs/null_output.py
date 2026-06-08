from __future__ import annotations

from visual_aiming.core.schemas import ControlCommand, PipelineTickResult


class NullOutput:
    name = "null"

    def apply(self, command: ControlCommand, result: PipelineTickResult) -> None:
        return None

    def close(self) -> None:
        return None
