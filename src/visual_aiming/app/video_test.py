# -*- coding: utf-8 -*-
"""交互式视频测试工具 — 完全复用正式管道，记录数据，真实移动鼠标。

用法：
    python main.py --video-test

操作：
    Space     开始/暂停（暂停时不检测不移鼠标）
    Q / ESC   退出并打印诊断摘要
    →         暂停时单帧前进
"""
from __future__ import annotations

import time
from pathlib import Path
from tkinter import Tk, filedialog
from typing import Optional

import cv2
import numpy as np

from visual_aiming.adapters.outputs.win_mouse import WinMouseOutput
from visual_aiming.app.timing import compute_active_wait_ms
from visual_aiming.app.video_overlay import build_osd_lines
from visual_aiming.config.loader import load_modular_config
from visual_aiming.config.schema import ModularConfig
from visual_aiming.core.metrics import JsonlDiagnostics
from visual_aiming.core.pipeline import ModularPipeline
from visual_aiming.core.schemas import (
    ControlCommand,
    FramePacket,
    PipelineTickResult,
    RuntimeMode,
    RuntimeTelemetry,
)
from visual_aiming.adapters.detectors.ultralytics_yolo import UltralyticsYoloDetector
from visual_aiming.vision.detection import TargetDetector


def _select_video_file() -> Optional[str]:
    """弹出文件选择对话框，返回选中的视频路径。"""
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        title="选择测试视频",
        filetypes=[
            ("视频文件", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv"),
            ("所有文件", "*.*"),
        ],
    )
    root.destroy()
    return path if path else None


class VideoTestRunner:
    """交互式视频测试：按帧播放 + 实时检测 + 真实鼠标控制 + 数据记录。"""

    WINDOW_NAME = "Video Test - 视频瞄准测试"

    def __init__(self, video_path: str, config: Optional[ModularConfig] = None) -> None:
        self.video_path = video_path
        self.config = config or load_modular_config("config.json")

        # 视频源
        self.capture = cv2.VideoCapture(video_path)
        if not self.capture.isOpened():
            raise FileNotFoundError(f"无法打开视频: {video_path}")
        self.fps = self.capture.get(cv2.CAP_PROP_FPS) or 30.0
        self.total_frames = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT))
        self.frame_w = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_h = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # ROI 居中裁切参数
        roi_w, roi_h = self.config.frame.roi_size
        self.roi_w = min(roi_w, self.frame_w)
        self.roi_h = min(roi_h, self.frame_h)
        self.roi_left = (self.frame_w - self.roi_w) // 2
        self.roi_top = (self.frame_h - self.roi_h) // 2
        self.roi_offset = (self.roi_left, self.roi_top)
        self.crosshair = (self.frame_w // 2, self.frame_h // 2)

        # 管道组件
        legacy_detector = TargetDetector()
        self.detector = UltralyticsYoloDetector(self.config.detector, legacy_detector)
        self.output_backend = WinMouseOutput(enable_real_mouse=True)

        # 诊断日志
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        video_name = Path(video_path).stem
        self.diagnostics = JsonlDiagnostics(
            log_dir / f"video_test_{video_name}_{timestamp}.jsonl"
        )

        # 管道
        self.pipeline = ModularPipeline(
            self.config,
            detector=self.detector,
            output_backend=self.output_backend,
            diagnostics=self.diagnostics,
        )

        # 状态
        self.active = False
        self.sequence = 0
        self.current_frame: Optional[np.ndarray] = None
        self.last_result: Optional[PipelineTickResult] = None
        self.last_frame_work_ms = 0.0
        self.last_wait_ms = 0
        self.display_fps = 0.0
        self._last_show_at: Optional[float] = None

    def run(self) -> None:
        """主循环。"""
        cv2.namedWindow(self.WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(self.WINDOW_NAME, cv2.WND_PROP_TOPMOST, 1)
        cv2.resizeWindow(self.WINDOW_NAME, min(1280, self.frame_w), min(720, self.frame_h))

        print(f"[视频测试] 已加载: {self.video_path}")
        print(f"[视频测试] 分辨率: {self.frame_w}x{self.frame_h} | FPS: {self.fps:.1f} | 总帧数: {self.total_frames}")
        print(f"[视频测试] ROI: ({self.roi_left},{self.roi_top}) {self.roi_w}x{self.roi_h}")
        print(f"[视频测试] 操作: Space=开始/暂停  Q/ESC=退出  →=单帧前进")
        print(f"[视频测试] 状态: 已暂停（按 Space 开始检测 + 鼠标吸附）")

        # 读取第一帧
        self._read_next_frame()
        self._warmup_detector()
        self._show_frame()

        try:
            while True:
                self.last_wait_ms = compute_active_wait_ms(self.fps, self.last_frame_work_ms) if self.active else 50
                key = cv2.waitKey(self.last_wait_ms) & 0xFF
                frame_started = time.perf_counter()

                if key in (ord("q"), ord("Q"), 27):  # Q / ESC
                    break
                elif key == ord(" "):  # Space
                    self.active = not self.active
                    if self.active:
                        print(f"[视频测试] ▶ 激活 — 开始检测 + 鼠标控制")
                    else:
                        print(f"[视频测试] ⏸ 暂停")
                        self.pipeline.reset()
                elif key == 83 and not self.active:  # → 右箭头 (OpenCV)
                    self._step_forward()
                    continue

                if self.active:
                    if not self._read_next_frame():
                        print(f"[视频测试] 视频结束")
                        break
                    self._tick()

                self._show_frame()
                if self.active:
                    self.last_frame_work_ms = (time.perf_counter() - frame_started) * 1000.0

                # 检查窗口是否被关闭
                if cv2.getWindowProperty(self.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                    break
        finally:
            self._shutdown()

    def _read_next_frame(self) -> bool:
        ok, frame = self.capture.read()
        if not ok:
            return False
        self.current_frame = frame
        self.sequence += 1
        return True

    def _step_forward(self) -> None:
        """暂停时单帧前进（不触发鼠标控制）。"""
        if self._read_next_frame():
            self._tick_passive()
            self._show_frame()

    def _tick(self) -> None:
        """激活状态：跑完整管道 + 真实鼠标移动。"""
        frame_packet = self._make_frame_packet(active=True)
        self.last_result = self.pipeline.tick(frame_packet, now=time.perf_counter())

    def _tick_passive(self) -> None:
        """暂停状态的单帧前进：检测但不移动鼠标。"""
        frame_packet = self._make_frame_packet(active=False)
        self.last_result = self.pipeline.tick(frame_packet, now=time.perf_counter())

    def _warmup_detector(self) -> None:
        if self.current_frame is None:
            return
        warmup = getattr(self.detector, "warmup", None)
        if warmup is None:
            return
        started = time.perf_counter()
        warmup((self.roi_h, self.roi_w, self.current_frame.shape[2]))
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        print(f"[视频测试] 模型预热完成: {elapsed_ms:.1f}ms")

    def _make_frame_packet(self, active: bool) -> FramePacket:
        roi_frame = self.current_frame[
            self.roi_top: self.roi_top + self.roi_h,
            self.roi_left: self.roi_left + self.roi_w,
        ]
        return FramePacket(
            frame=roi_frame,
            timestamp=self.sequence / self.fps,
            sequence=self.sequence,
            roi_offset=self.roi_offset,
            roi_size=(self.roi_w, self.roi_h),
            crosshair=self.crosshair,
            source="video_test",
            mode=RuntimeMode(active=active, firing=active),
            telemetry=RuntimeTelemetry(
                wait_ms=float(self.last_wait_ms),
                frame_work_ms=self.last_frame_work_ms,
                display_fps=self.display_fps,
                source_fps=self.fps,
                active=active,
            ),
        )

    def _show_frame(self) -> None:
        """绘制叠加层并显示。"""
        if self.current_frame is None:
            return

        display = self.current_frame.copy()
        h, w = display.shape[:2]

        # 绘制 ROI 区域边框
        cv2.rectangle(
            display,
            (self.roi_left, self.roi_top),
            (self.roi_left + self.roi_w, self.roi_top + self.roi_h),
            (128, 128, 128), 1,
        )

        # 绘制 crosshair
        cx, cy = self.crosshair
        cv2.drawMarker(display, (cx, cy), (255, 180, 0), cv2.MARKER_CROSS, 20, 2)

        if self.last_result is not None:
            result = self.last_result
            rl, rt = self.roi_left, self.roi_top

            # 检测框
            for det in result.detections.detections:
                x, y, bw, bh = det.bbox
                x1 = x + rl
                y1 = y + rt
                color = (0, 255, 0) if det.class_id == self.config.target_selection.head_class_id else (0, 200, 200)
                cv2.rectangle(display, (x1, y1), (x1 + bw, y1 + bh), color, 2)
                label = f"{det.class_name} {det.confidence:.2f}"
                cv2.putText(display, label, (x1, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

            # 瞄准点
            if result.aim.valid and result.aim.point:
                ax, ay = result.aim.point
                cv2.circle(display, (ax, ay), 5, (0, 0, 255), -1)
                cv2.putText(display, "AIM", (ax + 8, ay - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1, cv2.LINE_AA)

            # 预测点
            if result.predicted.point:
                px, py = result.predicted.point
                cv2.circle(display, (px, py), 4, (0, 255, 255), -1)
                cv2.putText(display, "PRED", (px + 8, py - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1, cv2.LINE_AA)

            # 控制向量箭头
            cmd = result.command
            if cmd.mode == "relative" and (cmd.dx != 0 or cmd.dy != 0):
                arrow_scale = 3.0
                end_x = int(cx + cmd.dx * arrow_scale)
                end_y = int(cy + cmd.dy * arrow_scale)
                cv2.arrowedLine(display, (cx, cy), (end_x, end_y), (255, 0, 255), 2, tipLength=0.3)

        else:
            result = None

        osd_lines = build_osd_lines(
            sequence=self.sequence,
            total_frames=self.total_frames,
            active=self.active,
            result=result,
            frame_work_ms=self.last_frame_work_ms,
            wait_ms=self.last_wait_ms,
            display_fps=self.display_fps,
        )

        # 绘制 OSD
        for i, line in enumerate(osd_lines):
            y = 24 + i * 22
            cv2.putText(display, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(display, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

        cv2.imshow(self.WINDOW_NAME, display)
        shown_at = time.perf_counter()
        if self._last_show_at is not None:
            elapsed = shown_at - self._last_show_at
            if elapsed > 0:
                instant_fps = 1.0 / elapsed
                self.display_fps = (
                    instant_fps
                    if self.display_fps <= 0.0
                    else self.display_fps * 0.85 + instant_fps * 0.15
                )
        self._last_show_at = shown_at

    def _shutdown(self) -> None:
        """清理资源，打印摘要。"""
        self.capture.release()
        self.output_backend.close()
        self.diagnostics.close()
        cv2.destroyAllWindows()

        summary = self.diagnostics.summary()
        print(f"\n{'='*50}")
        print(f"[视频测试] 完成 — 诊断摘要:")
        print(f"  处理帧数: {summary['samples']}")
        print(f"  空指令帧: {summary['noop_commands']}")
        print(f"  目标丢失: {summary['target_lost']}")
        print(f"  目标切换: {summary['target_switches']}")
        print(f"  平均控制幅度: {summary['avg_command_magnitude']:.2f}")
        print(f"  最大控制幅度: {summary['max_command_magnitude']:.2f}")
        print(f"  最大检测延迟: {summary['max_detector_latency_ms']:.1f}ms")
        print(f"  最大管道延迟: {summary['max_pipeline_latency_ms']:.1f}ms")
        print(f"  日志路径: {self.diagnostics.jsonl_path}")
        print(f"{'='*50}")


def run_video_test(config_path: str = "config.json") -> int:
    """入口函数：选择视频文件 → 运行交互测试。"""
    video_path = _select_video_file()
    if not video_path:
        print("[视频测试] 未选择文件，退出。")
        return 1

    config = load_modular_config(config_path)
    # 强制使用真实鼠标输出
    config.output.backend = "win_mouse"
    config.output.enable_real_mouse = True

    runner = VideoTestRunner(video_path, config)
    runner.run()
    return 0
