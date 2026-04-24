# -*- coding: utf-8 -*-
from typing import Optional, Tuple

import cv2
import numpy as np

BBox = Tuple[int, int, int, int]
Point = Tuple[int, int]


class DebugVisualizer:
    """Draw ROI frame, detection bbox, aim point, and calibration crosshair."""

    def __init__(
        self,
        enabled: bool = True,
        window_name: str = "Debug - YOLO ROI",
        roi_size: Tuple[int, int] = (410, 315),
    ):
        self.enabled = enabled
        self.window_name = window_name
        self.window_created = False
        self.window_scale = 0.5
        self.roi_size = roi_size
        if self.enabled:
            self._create_window()

    def update(
        self,
        frame: np.ndarray,
        bbox: Optional[BBox],
        aim_point: Optional[Point],
        calibrate_point: Optional[Point],
        roi_left: int,
        roi_top: int,
    ):
        if not self.enabled or frame is None:
            return

        if not self.window_created:
            self._create_window()

        disp = frame.copy()
        h, w = disp.shape[:2]

        self._draw_roi_center(disp, w, h)
        self._draw_bbox(disp, bbox)
        self._draw_global_point(
            disp,
            aim_point,
            roi_left,
            roi_top,
            color=(0, 0, 255),
            radius=4,
            label="AIM",
        )
        self._draw_global_marker(
            disp,
            calibrate_point,
            roi_left,
            roi_top,
            color=(255, 0, 0),
            label="CROSSHAIR",
        )

        cv2.imshow(self.window_name, disp)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            self.close()

    def close(self):
        if self.window_created:
            cv2.destroyWindow(self.window_name)
        self.window_created = False
        self.enabled = False

    def _create_window(self):
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(self.window_name, cv2.WND_PROP_TOPMOST, 1)
        width = max(1, int(self.roi_size[0] * self.window_scale))
        height = max(1, int(self.roi_size[1] * self.window_scale))
        cv2.resizeWindow(self.window_name, width, height)
        cv2.moveWindow(self.window_name, 20, 60)
        self.window_created = True

    def _draw_roi_center(self, image: np.ndarray, width: int, height: int):
        cx = width // 2
        cy = height // 2
        cv2.drawMarker(image, (cx, cy), (255, 0, 0), cv2.MARKER_CROSS, 14, 1)

    def _draw_bbox(self, image: np.ndarray, bbox: Optional[BBox]):
        if bbox is None:
            return

        x, y, bw, bh = bbox
        x2 = x + bw
        y2 = y + bh
        cv2.rectangle(image, (x, y), (x2, y2), (0, 255, 0), 2)
        cv2.circle(image, (x + bw // 2, y + bh // 2), 3, (0, 255, 0), -1)
        cv2.putText(
            image,
            f"{bw}x{bh}",
            (x, max(15, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )

    def _draw_global_point(
        self,
        image: np.ndarray,
        point: Optional[Point],
        roi_left: int,
        roi_top: int,
        color: Tuple[int, int, int],
        radius: int,
        label: str,
    ):
        local_point = self._to_local(point, roi_left, roi_top, image)
        if local_point is None:
            return

        x, y = local_point
        cv2.circle(image, (x, y), radius, color, -1)
        cv2.putText(
            image,
            label,
            (x + 6, max(15, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    def _draw_global_marker(
        self,
        image: np.ndarray,
        point: Optional[Point],
        roi_left: int,
        roi_top: int,
        color: Tuple[int, int, int],
        label: str,
    ):
        local_point = self._to_local(point, roi_left, roi_top, image)
        if local_point is None:
            return

        x, y = local_point
        cv2.drawMarker(image, (x, y), color, cv2.MARKER_CROSS, 18, 2)
        cv2.putText(
            image,
            label,
            (x + 6, min(image.shape[0] - 8, y + 16)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    def _to_local(
        self,
        point: Optional[Point],
        roi_left: int,
        roi_top: int,
        image: np.ndarray,
    ) -> Optional[Point]:
        if point is None:
            return None

        h, w = image.shape[:2]
        x = int(point[0] - roi_left)
        y = int(point[1] - roi_top)
        if 0 <= x < w and 0 <= y < h:
            return (x, y)
        return None
