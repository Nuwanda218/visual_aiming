from __future__ import annotations

import time
from typing import Callable, Optional

import numpy as np

from visual_aiming.config.schema import FrameSourceConfig
from visual_aiming.core.schemas import FramePacket, Point, RuntimeMode


class ScreenFrameSource:
    name = "screen"

    def __init__(
        self,
        config: FrameSourceConfig,
        roi_offset: Point,
        crosshair: Point,
        grabber: Optional[Callable[[], Optional[np.ndarray]]] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self.roi_offset = roi_offset
        self.crosshair = crosshair
        self.grabber = grabber
        self.clock = clock
        self.sequence = 0
        self._screen_capture = None

    def read(self) -> Optional[FramePacket]:
        frame = self.grabber() if self.grabber is not None else self._grab_with_screen_capture()
        if frame is None:
            return None
        sequence = self.sequence
        self.sequence += 1
        return FramePacket(
            frame=frame,
            timestamp=self.clock(),
            sequence=sequence,
            roi_offset=self.roi_offset,
            roi_size=self.config.roi_size,
            crosshair=self.crosshair,
            source=self.name,
            mode=RuntimeMode(active=True, firing=False),
        )

    def _grab_with_screen_capture(self):
        if self._screen_capture is None:
            from visual_aiming.vision.screen_capture import ScreenCapture
            wakeup = _FixedGeometryWakeup(self.roi_offset)
            legacy_config = _LegacyFrameConfig(self.config.roi_size)
            self._screen_capture = ScreenCapture(legacy_config, wakeup)
        return self._screen_capture.grab()

    def close(self) -> None:
        if self._screen_capture is not None:
            self._screen_capture.close()
            self._screen_capture = None


class _FixedGeometryWakeup:
    def __init__(self, roi_offset: Point) -> None:
        self.roi_offset = roi_offset

    def get_roi_offset(self) -> Point:
        return self.roi_offset


class _LegacyFrameConfig:
    def __init__(self, roi_size: Point) -> None:
        self.roi_width = roi_size[0]
        self.roi_height = roi_size[1]
