from __future__ import annotations

from typing import Protocol

from visual_aiming.core.schemas import PipelineTickResult


class DiagnosticsSink(Protocol):
    name: str

    def write(self, result: PipelineTickResult) -> None:
        """Record one pipeline tick."""
        ...

    def close(self) -> None:
        """Flush and release resources."""
        ...
