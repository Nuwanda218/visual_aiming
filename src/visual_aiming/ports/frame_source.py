from __future__ import annotations

from typing import Optional, Protocol

from visual_aiming.core.schemas import FramePacket


class FrameSource(Protocol):
    name: str

    def read(self) -> Optional[FramePacket]:
        """Return the next frame or None when no frame is currently available."""
        ...

    def close(self) -> None:
        """Release resources held by the source."""
        ...
