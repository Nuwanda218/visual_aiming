"""交互接入层 — OpenCV 调参窗口，实时预览各层参数效果。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


class CaptureTuner:
    """capture 层调参窗口：实时预览 ROI 裁切范围和准星位置。

    操作：
        拖动滑块   实时调整 ROI 宽度/高度和准星偏移
        ← →       切换视频帧
        S          保存当前参数到 config.json
        Q / ESC    退出
    """

    WINDOW_NAME = "V2 Capture Tuner"

    def __init__(self, video_path: str, config_path: str = "config.json") -> None:
        self.video_path = video_path
        self.config_path = config_path

        # 打开视频
        self.capture = cv2.VideoCapture(video_path)
        if not self.capture.isOpened():
            raise FileNotFoundError(f"无法打开视频: {video_path}")

        self.video_w = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.video_h = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))

        # 当前帧
        self._current_frame: Optional[np.ndarray] = None
        self._frame_index = 0

        # 可调参数（初始值来自 config.json 或默认值）
        file_config = self._load_config_file()
        self.roi_w = int(file_config.get("image_width", 410))
        self.roi_h = int(file_config.get("image_height", 315))
        self.offset_x = int(file_config.get("crosshair_offset_x", 0))
        self.offset_y = int(file_config.get("crosshair_offset_y", 0))

    def run(self) -> None:
        """主循环：显示窗口，处理输入。"""
        # 全屏显示，不缩放画面，确保 ROI 框位置精确
        cv2.namedWindow(self.WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(self.WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        # 创建滑块
        cv2.createTrackbar("ROI W", self.WINDOW_NAME, self.roi_w, self.video_w, self._on_roi_w)
        cv2.createTrackbar("ROI H", self.WINDOW_NAME, self.roi_h, self.video_h, self._on_roi_h)
        cv2.createTrackbar("Cross X", self.WINDOW_NAME, self.offset_x + 200, 400, self._on_offset_x)
        cv2.createTrackbar("Cross Y", self.WINDOW_NAME, self.offset_y + 200, 400, self._on_offset_y)

        # 读取第一帧
        self._read_frame(0)

        print(f"[Capture Tuner] 视频: {self.video_path}")
        print(f"[Capture Tuner] 分辨率: {self.video_w}×{self.video_h} | 总帧数: {self.total_frames}")
        print(f"[Capture Tuner] 操作: ← → 切换帧 | S 保存参数 | Q/ESC 退出")

        while True:
            self._render()

            # waitKeyEx 获取完整键值，兼容 Windows 方向键
            key = cv2.waitKeyEx(30)
            if key in (ord("q"), ord("Q"), 27):  # Q / ESC
                break
            elif key in (ord("s"), ord("S")):
                self._save_config()
            elif key in (0x270000, 2555904, 83):  # → 右箭头（Windows / Linux）
                self._read_frame(min(self._frame_index + 1, self.total_frames - 1))
            elif key in (0x250000, 2424832, 81):  # ← 左箭头（Windows / Linux）
                self._read_frame(max(self._frame_index - 1, 0))

            # 检查窗口是否被关闭
            if cv2.getWindowProperty(self.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break

        self.capture.release()
        cv2.destroyAllWindows()

    def _on_roi_w(self, val: int) -> None:
        self.roi_w = max(100, val)

    def _on_roi_h(self, val: int) -> None:
        self.roi_h = max(100, val)

    def _on_offset_x(self, val: int) -> None:
        # trackbar 范围 0~400，映射到 -200~+200
        self.offset_x = val - 200

    def _on_offset_y(self, val: int) -> None:
        self.offset_y = val - 200

    def _read_frame(self, index: int) -> None:
        """跳转到指定帧并读取。"""
        self.capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self.capture.read()
        if ok:
            self._current_frame = frame
            self._frame_index = index

    def _render(self) -> None:
        """在原始帧上绘制 ROI 框和准星，然后显示。"""
        if self._current_frame is None:
            return

        display = self._current_frame.copy()

        # 计算 ROI 区域（以画面中心为基准，不超出画面边界）
        roi_w = min(self.roi_w, self.video_w)
        roi_h = min(self.roi_h, self.video_h)
        roi_left = (self.video_w - roi_w) // 2
        roi_top = (self.video_h - roi_h) // 2

        # 绘制 ROI 矩形框（绿色）
        cv2.rectangle(
            display,
            (roi_left, roi_top),
            (roi_left + roi_w, roi_top + roi_h),
            (0, 255, 0), 2,
        )

        # 计算准星位置（ROI 中心 + 偏移）
        crosshair_x = roi_left + roi_w // 2 + self.offset_x
        crosshair_y = roi_top + roi_h // 2 + self.offset_y

        # 绘制准星十字线（蓝色）
        cv2.drawMarker(
            display,
            (crosshair_x, crosshair_y),
            (255, 180, 0), cv2.MARKER_CROSS, 30, 2,
        )

        # ROI 区域外半透明遮罩（让 ROI 范围更直观）
        overlay = display.copy()
        # 上方遮罩
        cv2.rectangle(overlay, (0, 0), (self.video_w, roi_top), (0, 0, 0), -1)
        # 下方遮罩
        cv2.rectangle(overlay, (0, roi_top + roi_h), (self.video_w, self.video_h), (0, 0, 0), -1)
        # 左侧遮罩
        cv2.rectangle(overlay, (0, roi_top), (roi_left, roi_top + roi_h), (0, 0, 0), -1)
        # 右侧遮罩
        cv2.rectangle(overlay, (roi_left + roi_w, roi_top), (self.video_w, roi_top + roi_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.4, display, 0.6, 0, display)

        # OSD 信息（左上角）
        osd_lines = [
            f"Frame: {self._frame_index}/{self.total_frames}",
            f"Video: {self.video_w}x{self.video_h}",
            f"ROI: {roi_w}x{roi_h} at ({roi_left},{roi_top})",
            f"Crosshair: ({crosshair_x},{crosshair_y}) offset=({self.offset_x},{self.offset_y})",
            "S=Save  Q=Quit  Arrows=Navigate",
        ]
        for i, line in enumerate(osd_lines):
            y = 24 + i * 22
            cv2.putText(display, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(display, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

        cv2.imshow(self.WINDOW_NAME, display)

    def _save_config(self) -> None:
        """把当前参数保存到 config.json。"""
        config_path = Path(self.config_path)

        # 读取现有配置（保留其他字段）
        existing = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = {}

        # 更新 capture 层参数
        existing["image_width"] = self.roi_w
        existing["image_height"] = self.roi_h
        existing["crosshair_offset_x"] = self.offset_x
        existing["crosshair_offset_y"] = self.offset_y

        config_path.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[Capture Tuner] 已保存: ROI={self.roi_w}x{self.roi_h} offset=({self.offset_x},{self.offset_y})")

    def _load_config_file(self) -> dict:
        """读取 config.json 的现有值。"""
        config_path = Path(self.config_path)
        if not config_path.exists():
            return {}
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
