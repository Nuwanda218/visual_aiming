from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from visual_aiming_v2.shared.schemas import Frame


class MemoryCapture:
    def __init__(self, frames: Iterable[Frame]) -> None:
        self._frames = list(frames)
        self._index = 0

    def read(self) -> Optional[Frame]:
        if self._index >= len(self._frames):
            return None
        frame = self._frames[self._index]
        self._index += 1
        return frame

    def close(self) -> None:
        pass


class VideoFileCapture:
    def __init__(self, video_path: str | Path) -> None:
        import cv2

        self.path = Path(video_path)
        self.capture = cv2.VideoCapture(str(self.path))
        if not self.capture.isOpened():
            raise FileNotFoundError(f"无法打开视频: {self.path}")
        fps = self.capture.get(cv2.CAP_PROP_FPS)
        self._frame_dt = 1.0 / fps if fps and fps > 0 else 1.0 / 30.0
        self._sequence = 0

    def read(self) -> Optional[Frame]:
        ok, image = self.capture.read()
        if not ok:
            return None
        seq = self._sequence
        self._sequence += 1
        return Frame(image=image, sequence=seq, timestamp=seq * self._frame_dt)

    def close(self) -> None:
        self.capture.release()
