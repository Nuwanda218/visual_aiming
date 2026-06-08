from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np

from visual_aiming.core.schemas import FramePacket, Point, RuntimeMode


class ArrayFrameSource:
    name = "array"

    def __init__(self, frames: Iterable[np.ndarray], fps: float, roi_offset: Point, crosshair: Point, source: str = "array") -> None:
        self.frames = list(frames)
        self.fps = max(1.0, float(fps))
        self.roi_offset = roi_offset
        self.crosshair = crosshair
        self.source = source
        self.index = 0

    def read(self) -> Optional[FramePacket]:
        if self.index >= len(self.frames):
            return None
        frame = self.frames[self.index]
        sequence = self.index
        self.index += 1
        return FramePacket(
            frame=frame,
            timestamp=sequence / self.fps,
            sequence=sequence,
            roi_offset=self.roi_offset,
            roi_size=(frame.shape[1], frame.shape[0]),
            crosshair=self.crosshair,
            source=self.source,
            mode=RuntimeMode(active=True, firing=False),
        )

    def close(self) -> None:
        return None


class VideoFileFrameSource:
    name = "video_file"

    def __init__(self, path: str | Path, roi_offset: Point, crosshair: Point) -> None:
        self.path = str(path)
        self.capture = cv2.VideoCapture(self.path)
        if not self.capture.isOpened():
            raise FileNotFoundError(f"Cannot open video file: {self.path}")
        fps = self.capture.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and fps > 0 else 30.0
        self.roi_offset = roi_offset
        self.crosshair = crosshair
        self.sequence = 0

    def read(self) -> Optional[FramePacket]:
        ok, frame = self.capture.read()
        if not ok:
            return None
        sequence = self.sequence
        self.sequence += 1
        return FramePacket(
            frame=frame,
            timestamp=sequence / self.fps,
            sequence=sequence,
            roi_offset=self.roi_offset,
            roi_size=(frame.shape[1], frame.shape[0]),
            crosshair=self.crosshair,
            source=self.name,
            mode=RuntimeMode(active=True, firing=False),
        )

    def close(self) -> None:
        self.capture.release()
