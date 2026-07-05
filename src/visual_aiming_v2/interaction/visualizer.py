"""交互接入层 — 流水线运行时可视化窗口。"""
from __future__ import annotations

import time
from typing import Optional

import cv2
import numpy as np

from visual_aiming_v2.shared.schemas import Command, Detection, TickResult


# 类别颜色映射
_COLORS = {
    "head": (0, 255, 0),      # 绿色
    "person": (0, 200, 200),   # 黄色
}
_DEFAULT_COLOR = (180, 180, 180)  # 灰色（未知类别）
_SELECTED_COLOR = (255, 255, 255) # 白色（选中目标加粗框）
_AIM_COLOR = (0, 0, 255)          # 红色（瞄准点）
_CROSSHAIR_COLOR = (255, 180, 0)  # 蓝色（准星）
_ARROW_COLOR = (255, 0, 255)      # 品红（控制箭头）


class Visualizer:
    """流水线运行时可视化：在 OpenCV 窗口中实时叠加检测结果和控制信息。"""

    WINDOW_NAME = "V2 Visual Debug"

    def __init__(self, crosshair: tuple[int, int], total_frames: int = 0) -> None:
        self.crosshair = crosshair
        self.total_frames = total_frames
        self._fps_times: list[float] = []
        self._paused = False

        cv2.namedWindow(self.WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(self.WINDOW_NAME, cv2.WND_PROP_TOPMOST, 1)

    def update(self, frame_image: np.ndarray, result: TickResult) -> bool:
        """绘制一帧叠加层并显示。返回 False 表示用户退出。"""
        # 计算 FPS
        now = time.perf_counter()
        self._fps_times.append(now)
        # 只保留最近 60 帧用于计算
        self._fps_times = [t for t in self._fps_times if now - t < 1.0]
        fps = len(self._fps_times)

        display = frame_image.copy()

        # 绘制检测框
        self._draw_detections(display, result.detections, result.selected)

        # 绘制准星
        cx, cy = self.crosshair
        cv2.drawMarker(display, (cx, cy), _CROSSHAIR_COLOR, cv2.MARKER_CROSS, 24, 2)

        # 绘制瞄准点和控制箭头
        if result.selected is not None:
            ax, ay = result.selected.center
            cv2.circle(display, (ax, ay), 5, _AIM_COLOR, -1)

            # 控制箭头（从准星指向瞄准点）
            cmd = result.command
            if cmd.mode == "relative" and (cmd.dx != 0 or cmd.dy != 0):
                scale = 3.0
                end_x = int(cx + cmd.dx * scale)
                end_y = int(cy + cmd.dy * scale)
                cv2.arrowedLine(display, (cx, cy), (end_x, end_y), _ARROW_COLOR, 2, tipLength=0.3)

        # OSD 信息
        self._draw_osd(display, result, fps)

        cv2.imshow(self.WINDOW_NAME, display)

        # 按键处理
        return self._handle_keys()

    def close(self) -> None:
        cv2.destroyAllWindows()

    def _draw_detections(
        self,
        image: np.ndarray,
        detections: list[Detection],
        selected: Optional[Detection],
    ) -> None:
        """绘制所有检测框，选中目标加粗。"""
        for det in detections:
            color = _COLORS.get(det.label, _DEFAULT_COLOR)
            thickness = 2

            # 选中目标加粗白色框
            is_selected = selected is not None and det is selected
            if is_selected:
                cv2.rectangle(
                    image,
                    (det.x - 1, det.y - 1),
                    (det.x + det.w + 1, det.y + det.h + 1),
                    _SELECTED_COLOR, 3,
                )

            # 检测框
            cv2.rectangle(image, (det.x, det.y), (det.x + det.w, det.y + det.h), color, thickness)

            # 标签 + 置信度
            label = f"{det.label} {det.confidence:.2f}"
            cv2.putText(image, label, (det.x, max(12, det.y - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    def _draw_osd(self, image: np.ndarray, result: TickResult, fps: int) -> None:
        """左上角 OSD 信息。"""
        cmd = result.command
        if self.total_frames > 0:
            frame_str = f"Frame: {result.frame.sequence}/{self.total_frames}"
        else:
            frame_str = f"Frame: {result.frame.sequence}"

        lines = [
            f"{frame_str} | FPS: {fps} | Det: {len(result.detections)} | "
            f"dx={cmd.dx} dy={cmd.dy} ({cmd.reason})",
        ]
        if self._paused:
            lines.append("PAUSED (Space to resume)")

        for i, line in enumerate(lines):
            y = 22 + i * 22
            cv2.putText(image, line, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(image, line, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    def _handle_keys(self) -> bool:
        """处理按键，返回 False 表示退出。"""
        wait_ms = 1 if not self._paused else 30
        key = cv2.waitKeyEx(wait_ms)

        if key in (ord("q"), ord("Q"), 27):  # Q / ESC
            return False
        elif key == ord(" "):  # Space 暂停/继续
            self._paused = not self._paused
            while self._paused:
                key2 = cv2.waitKeyEx(30)
                if key2 in (ord("q"), ord("Q"), 27):
                    return False
                elif key2 == ord(" "):
                    self._paused = False
                    break
                # 窗口被关闭
                if cv2.getWindowProperty(self.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                    return False

        # 窗口被关闭
        if cv2.getWindowProperty(self.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            return False

        return True
