"""交互接入层 — V2 OpenCV 调参窗口。"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from visual_aiming_v2.shared.config import Config, config_from_mapping, config_to_mapping


class V2ConfigTunerState:
    """V2 配置调参状态：只读写 config.v2.json 的嵌套结构。"""

    def __init__(self, config: Config) -> None:
        self.config = copy.deepcopy(config)
        self._original = copy.deepcopy(config)

    @classmethod
    def load(cls, path: str | Path) -> "V2ConfigTunerState":
        config_path = Path(path)
        if not config_path.exists():
            return cls(Config())
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        return cls(config_from_mapping(data if isinstance(data, dict) else {}))

    def set_value(self, dotted_path: str, value: Any) -> None:
        section_name, field_name = dotted_path.split(".", 1)
        section = getattr(self.config, section_name)
        current = getattr(section, field_name)
        if isinstance(current, bool):
            value = bool(value)
        elif isinstance(current, int) and not isinstance(current, bool):
            value = int(value)
        elif isinstance(current, float):
            value = float(value)
        elif isinstance(current, str):
            value = str(value)
        setattr(section, field_name, value)

    def get_value(self, dotted_path: str) -> Any:
        section_name, field_name = dotted_path.split(".", 1)
        return getattr(getattr(self.config, section_name), field_name)

    def reset(self) -> None:
        self.config = copy.deepcopy(self._original)

    def save(self, path: str | Path) -> None:
        config_path = Path(path)
        config_path.write_text(
            json.dumps(config_to_mapping(self.config), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._original = copy.deepcopy(self.config)


class CaptureTuner:
    """capture 层调参窗口：实时预览 ROI 裁切范围和准星位置。"""

    WINDOW_NAME = "V2 Capture Tuner"

    def __init__(self, video_path: str, config_path: str = "config.v2.json") -> None:
        self.video_path = video_path
        self.config_path = config_path
        self.state = V2ConfigTunerState.load(config_path)

        self.capture = cv2.VideoCapture(video_path)
        if not self.capture.isOpened():
            raise FileNotFoundError(f"无法打开视频: {video_path}")

        self.video_w = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.video_h = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))
        self._current_frame: Optional[np.ndarray] = None
        self._frame_index = 0

    @property
    def roi_w(self) -> int:
        return int(self.state.config.capture.image_width)

    @property
    def roi_h(self) -> int:
        return int(self.state.config.capture.image_height)

    @property
    def offset_x(self) -> int:
        return int(self.state.config.capture.crosshair_offset_x)

    @property
    def offset_y(self) -> int:
        return int(self.state.config.capture.crosshair_offset_y)

    def run(self) -> None:
        cv2.namedWindow(self.WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(self.WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.createTrackbar("ROI W", self.WINDOW_NAME, self.roi_w, self.video_w, self._on_roi_w)
        cv2.createTrackbar("ROI H", self.WINDOW_NAME, self.roi_h, self.video_h, self._on_roi_h)
        cv2.createTrackbar("Cross X", self.WINDOW_NAME, self.offset_x + 200, 400, self._on_offset_x)
        cv2.createTrackbar("Cross Y", self.WINDOW_NAME, self.offset_y + 200, 400, self._on_offset_y)
        self._read_frame(0)
        print(f"[Capture Tuner] 视频: {self.video_path}")
        print("[Capture Tuner] 操作: ← → 切换帧 | S 保存参数 | R 恢复 | Q/ESC 退出")

        while True:
            self._render()
            key = cv2.waitKeyEx(30)
            if key in (ord("q"), ord("Q"), 27):
                break
            if key in (ord("s"), ord("S")):
                self.state.save(self.config_path)
                print(f"[Capture Tuner] 已保存: {self.config_path}")
            elif key in (ord("r"), ord("R")):
                self.state.reset()
                self._sync_trackbars()
            elif key in (0x270000, 2555904, 83):
                self._read_frame(min(self._frame_index + 1, self.total_frames - 1))
            elif key in (0x250000, 2424832, 81):
                self._read_frame(max(self._frame_index - 1, 0))
            if cv2.getWindowProperty(self.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
        self.capture.release()
        cv2.destroyAllWindows()

    def _sync_trackbars(self) -> None:
        cv2.setTrackbarPos("ROI W", self.WINDOW_NAME, self.roi_w)
        cv2.setTrackbarPos("ROI H", self.WINDOW_NAME, self.roi_h)
        cv2.setTrackbarPos("Cross X", self.WINDOW_NAME, self.offset_x + 200)
        cv2.setTrackbarPos("Cross Y", self.WINDOW_NAME, self.offset_y + 200)

    def _on_roi_w(self, val: int) -> None:
        self.state.set_value("capture.image_width", max(100, val))

    def _on_roi_h(self, val: int) -> None:
        self.state.set_value("capture.image_height", max(100, val))

    def _on_offset_x(self, val: int) -> None:
        self.state.set_value("capture.crosshair_offset_x", val - 200)

    def _on_offset_y(self, val: int) -> None:
        self.state.set_value("capture.crosshair_offset_y", val - 200)

    def _read_frame(self, index: int) -> None:
        self.capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self.capture.read()
        if ok:
            self._current_frame = frame
            self._frame_index = index

    def _render(self) -> None:
        if self._current_frame is None:
            return
        display = self._current_frame.copy()
        roi_w = min(self.roi_w, self.video_w)
        roi_h = min(self.roi_h, self.video_h)
        roi_left = (self.video_w - roi_w) // 2
        roi_top = (self.video_h - roi_h) // 2
        cv2.rectangle(display, (roi_left, roi_top), (roi_left + roi_w, roi_top + roi_h), (0, 255, 0), 2)
        crosshair_x = roi_left + roi_w // 2 + self.offset_x
        crosshair_y = roi_top + roi_h // 2 + self.offset_y
        cv2.drawMarker(display, (crosshair_x, crosshair_y), (255, 180, 0), cv2.MARKER_CROSS, 30, 2)
        lines = [
            f"Frame: {self._frame_index}/{self.total_frames}",
            f"ROI: {roi_w}x{roi_h}",
            f"Crosshair offset=({self.offset_x},{self.offset_y})",
            "S=Save  R=Reset  Q=Quit  Arrows=Navigate",
        ]
        _draw_lines(display, lines)
        cv2.imshow(self.WINDOW_NAME, display)


class V2ConfigTuner(CaptureTuner):
    """V2 配置调参窗口：标签页式切换，点击标签按钮即可切换参数页。"""

    WINDOW_NAME = "V2 Config Tuner"

    TAB_HEIGHT = 40        # 标签栏高度
    TAB_WIDTH = 110        # 每个标签宽度
    TAB_GAP = 4            # 标签间距
    TAB_BAR_Y = 4          # 标签栏顶部

    PAGES = {
        1: ("Capture", [
            ("ROI W", "capture.image_width", 100, 1000, 1.0, 0),
            ("ROI H", "capture.image_height", 100, 1000, 1.0, 0),
            ("Cross X", "capture.crosshair_offset_x", -200, 200, 1.0, 200),
            ("Cross Y", "capture.crosshair_offset_y", -200, 200, 1.0, 200),
        ]),
        2: ("Control", [
            ("Speed", "control.speed", 1, 500, 1.0, 0),
            ("Accel x100", "control.acceleration", 1, 100, 100.0, 0),
            ("Deadzone", "control.deadzone", 0, 20, 1.0, 0),
            ("Near Radius", "control.near_radius", 1, 300, 1.0, 0),
            ("Near Scale x100", "control.near_speed_scale", 1, 100, 100.0, 0),
        ]),
        3: ("Tracker", [
            ("Match Ratio x100", "tracker.match_distance_ratio", 1, 200, 100.0, 0),
            ("Min Dist", "tracker.min_match_distance", 1, 100, 1.0, 0),
            ("Size Min x100", "tracker.size_ratio_min", 1, 200, 100.0, 0),
            ("Size Max x100", "tracker.size_ratio_max", 1, 300, 100.0, 0),
            ("Lost Grace", "tracker.lost_frame_grace", 0, 10, 1.0, 0),
        ]),
        4: ("Smoothing", [
            ("Enabled", "smoothing.enabled", 0, 1, 1.0, 0),
            ("Alpha x100", "smoothing.alpha", 1, 100, 100.0, 0),
            ("Jitter", "smoothing.jitter_radius", 0, 20, 1.0, 0),
            ("Stable Frames", "smoothing.stable_frames", 1, 10, 1.0, 0),
            ("Hold Frames", "smoothing.hold_frames", 0, 20, 1.0, 0),
        ]),
        5: ("Runtime", [
            ("Detect FPS", "runtime.detect_fps", 1, 120, 1.0, 0),
        ]),
        6: ("Perception", [
            ("Confidence x100", "perception.confidence", 1, 100, 100.0, 0),
            ("IOU x100", "perception.iou", 1, 100, 100.0, 0),
        ]),
        7: ("Targeting", [
            ("Head Bias x100", "targeting.head_bias", 1, 100, 100.0, 0),
            ("Body Bias x100", "targeting.body_bias", 1, 100, 100.0, 0),
        ]),
    }

    def __init__(self, video_path: str, config_path: str = "config.v2.json") -> None:
        super().__init__(video_path, config_path)
        self._page = 1
        self._tab_rects: list[tuple[int, int, int, int]] = []  # 各标签的 (x1,y1,x2,y2)

    def run(self) -> None:
        cv2.namedWindow(self.WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.WINDOW_NAME, 900, 650)
        cv2.setMouseCallback(self.WINDOW_NAME, self._on_mouse)
        self._create_page_trackbars()
        self._read_frame(0)
        print("[V2 Config Tuner] 点击标签切换 | S=保存 | R=恢复 | Q=退出")

        while True:
            self._render_config_page()
            key = cv2.waitKeyEx(30)
            if key in (ord("q"), ord("Q"), 27):
                break
            if key in (ord("s"), ord("S")):
                self.state.save(self.config_path)
                print(f"[V2 Config Tuner] 已保存: {self.config_path}")
            elif key in (ord("r"), ord("R")):
                self.state.reset()
                self._create_page_trackbars()
            if cv2.getWindowProperty(self.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
        self.capture.release()
        cv2.destroyAllWindows()

    def _on_mouse(self, event, x, y, flags, param) -> None:
        """鼠标点击标签按钮时切换页面。"""
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        for page, (x1, y1, x2, y2) in self._tab_rects:
            if x1 <= x <= x2 and y1 <= y <= y2:
                if page != self._page and page in self.PAGES:
                    self._page = page
                    self._create_page_trackbars()
                return

    def _create_page_trackbars(self) -> None:
        """销毁旧 trackbar 并重建当前页的 trackbar。"""
        cv2.destroyWindow(self.WINDOW_NAME)
        cv2.namedWindow(self.WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.WINDOW_NAME, 900, 650)
        cv2.setMouseCallback(self.WINDOW_NAME, self._on_mouse)
        for name, path, min_value, max_value, scale, offset in self.PAGES[self._page][1]:
            raw = self.state.get_value(path)
            if isinstance(raw, bool):
                pos = int(raw)
            else:
                pos = int(round(float(raw) * scale + offset))
            pos = max(0, min(int(max_value - min_value), pos - int(min_value)))
            cb = self._trackbar_callback(path, min_value, scale, offset)
            cv2.createTrackbar(name, self.WINDOW_NAME, pos, int(max_value - min_value), cb)

    def _trackbar_callback(self, path: str, min_value: float, scale: float, offset: float):
        def callback(pos: int) -> None:
            value = (pos + min_value - offset) / scale
            self.state.set_value(path, value)
        return callback

    def _render_config_page(self) -> None:
        """在视频预览上叠加标签栏和当前参数值。"""
        if self._current_frame is None:
            return
        display = self._current_frame.copy()

        # 标签栏背景（半透明叠加在视频顶部）
        overlay = display.copy()
        cv2.rectangle(overlay, (0, 0), (display.shape[1], self.TAB_HEIGHT + 8), (35, 35, 35), -1)
        cv2.addWeighted(overlay, 0.85, display, 0.15, 0, display)

        self._tab_rects = []
        x = 8
        for page_id in sorted(self.PAGES.keys()):
            title, _items = self.PAGES[page_id]
            if page_id == self._page:
                bg = (60, 130, 60)
                fg = (255, 255, 255)
            else:
                bg = (55, 55, 55)
                fg = (170, 170, 170)
            cv2.rectangle(display, (x, self.TAB_BAR_Y), (x + self.TAB_WIDTH, self.TAB_BAR_Y + self.TAB_HEIGHT), bg, -1)
            cv2.rectangle(display, (x, self.TAB_BAR_Y), (x + self.TAB_WIDTH, self.TAB_BAR_Y + self.TAB_HEIGHT), (90, 90, 90), 1)
            ts = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
            cv2.putText(display, title, (x + (self.TAB_WIDTH - ts[0]) // 2, self.TAB_BAR_Y + (self.TAB_HEIGHT + ts[1]) // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, fg, 1, cv2.LINE_AA)
            self._tab_rects.append((page_id, (x, self.TAB_BAR_Y, x + self.TAB_WIDTH, self.TAB_BAR_Y + self.TAB_HEIGHT)))
            x += self.TAB_WIDTH + self.TAB_GAP

        # 参数值
        _title, items = self.PAGES[self._page]
        y = self.TAB_BAR_Y + self.TAB_HEIGHT + 16
        for _name, path, _min, _max, _scale, _offset in items:
            value = self.state.get_value(path)
            val_str = f"{value:.3f}" if isinstance(value, float) else str(value)
            line = f"  {path} = {val_str}"
            cv2.putText(display, line, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(display, line, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 255, 200), 1, cv2.LINE_AA)
            y += 22

        # 底部提示
        cv2.putText(display, "Click tabs | S=Save  R=Reset  Q=Quit", (8, display.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(display, "Click tabs | S=Save  R=Reset  Q=Quit", (8, display.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)

        cv2.imshow(self.WINDOW_NAME, display)


def _draw_lines(image: np.ndarray, lines: list[str]) -> None:
    for i, line in enumerate(lines):
        y = 24 + i * 22
        cv2.putText(image, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(image, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
