# -*- coding: utf-8 -*-
"""视频帧适配器：用视频帧替代截图输入，复用真实运行时管道。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.actions.debug_visualizer import DebugVisualizer
from visual_aiming.actions.mouse_control import MouseController, get_cursor_pos
from visual_aiming.common.utils import ThrottledPrinter
from visual_aiming.config import Config
from visual_aiming.core import runtime as runtime_core
from visual_aiming.core.aim_calculator import AimPointCalculator
from visual_aiming.core.detect_scheduler import DetectionScheduler
from visual_aiming.core.pipeline import RuntimePipeline
from visual_aiming.core.runtime_services import RuntimeServices
from visual_aiming.core.runtime_state import RuntimeState
from visual_aiming.core.throttle import Throttle
from visual_aiming.vision.detection import TargetDetector


Point = Tuple[int, int]


class VideoRunLogger:
    def __init__(self, log_dir: Path, run_name: Optional[str] = None) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        if run_name is None:
            run_name = time.strftime("video_test_%Y%m%d_%H%M%S")
        self.jsonl_path = self.log_dir / f"{run_name}.jsonl"
        self.summary_path = self.log_dir / f"{run_name}_summary.json"
        self.latest_summary_path = self.log_dir / "video_test_latest_summary.json"
        self._records = []
        self._handle = self.jsonl_path.open("w", encoding="utf-8")

    def write_event(self, event: dict) -> None:
        record = dict(event)
        self._records.append(record)
        self._handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._handle.flush()

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()
        summary = self._build_summary()
        payload = json.dumps(summary, ensure_ascii=False, indent=2)
        self.summary_path.write_text(payload, encoding="utf-8")
        self.latest_summary_path.write_text(payload, encoding="utf-8")

    def _build_summary(self) -> dict:
        samples = len(self._records)
        if samples == 0:
            return {
                "samples": 0,
                "fresh_ratio": 0.0,
                "measurement_ratio": 0.0,
                "avg_detect_latency_ms": 0.0,
                "max_detect_latency_ms": 0.0,
                "avg_target_error_after": None,
                "likely_bottleneck": "no_samples",
            }

        latencies = [float(item.get("detect_latency_ms", 0.0) or 0.0) for item in self._records]
        errors_after = [
            float(item["target_error_after"])
            for item in self._records
            if item.get("target_error_after") is not None
        ]
        fresh_count = sum(1 for item in self._records if bool(item.get("fresh", False)))
        measurement_count = sum(1 for item in self._records if bool(item.get("has_measurement", False)))
        avg_latency = sum(latencies) / samples
        fresh_ratio = fresh_count / samples
        measurement_ratio = measurement_count / samples
        avg_error_after = sum(errors_after) / len(errors_after) if errors_after else None
        return {
            "samples": samples,
            "fresh_ratio": fresh_ratio,
            "measurement_ratio": measurement_ratio,
            "avg_detect_latency_ms": avg_latency,
            "max_detect_latency_ms": max(latencies),
            "avg_target_error_after": avg_error_after,
            "likely_bottleneck": self._infer_bottleneck(avg_latency, fresh_ratio, measurement_ratio, avg_error_after),
            "jsonl_path": str(self.jsonl_path),
        }

    def _infer_bottleneck(
        self,
        avg_latency: float,
        fresh_ratio: float,
        measurement_ratio: float,
        avg_error_after: Optional[float],
    ) -> str:
        if avg_latency >= 33.0:
            return "detection_latency"
        if fresh_ratio < 0.5:
            return "low_fresh_detection"
        if measurement_ratio < 0.5:
            return "pipeline_measurement_gap"
        if avg_error_after is not None and avg_error_after > 20.0:
            return "mouse_tracking_error"
        return "no_obvious_bottleneck"


class VideoFrameAdapter:
    def __init__(self, screen_size: Point, roi_size: Point) -> None:
        self.screen_width, self.screen_height = screen_size
        self.roi_width, self.roi_height = roi_size
        self.crosshair = (self.screen_width // 2, self.screen_height // 2)
        self.roi_offset = (
            (self.screen_width - self.roi_width) // 2,
            (self.screen_height - self.roi_height) // 2,
        )

    def make_canvas(self, frame: np.ndarray) -> np.ndarray:
        canvas = np.zeros((self.screen_height, self.screen_width, 3), dtype=np.uint8)
        frame_h, frame_w = frame.shape[:2]
        if frame_w <= 0 or frame_h <= 0:
            return canvas

        scale = min(self.screen_width / frame_w, self.screen_height / frame_h)
        scaled_w = max(1, int(round(frame_w * scale)))
        scaled_h = max(1, int(round(frame_h * scale)))
        resized = cv2.resize(frame, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)
        left = (self.screen_width - scaled_w) // 2
        top = (self.screen_height - scaled_h) // 2
        canvas[top:top + scaled_h, left:left + scaled_w] = resized
        return canvas

    def crop_center_roi(self, canvas: np.ndarray) -> np.ndarray:
        left, top = self.roi_offset
        return canvas[top:top + self.roi_height, left:left + self.roi_width]


class PlaybackClock:
    def __init__(self, fps: float, total_frames: int) -> None:
        self.fps = max(1.0, float(fps or 30.0))
        self.total_frames = max(1, int(total_frames or 1))
        self.started_at = time.perf_counter()

    def reset(self) -> None:
        self.started_at = time.perf_counter()

    def elapsed(self) -> float:
        return time.perf_counter() - self.started_at

    def frame_index(self, elapsed_seconds: float) -> int:
        return int(elapsed_seconds * self.fps) % self.total_frames


@dataclass
class VideoRuntimeMode:
    active: bool = False
    firing: bool = False
    absolute_validation: bool = False

    def toggle_active(self) -> None:
        if self.active:
            self.active = False
            self.firing = False
        else:
            self.active = True
            self.firing = False

    def toggle_firing(self) -> None:
        if self.active and self.firing:
            self.firing = False
        else:
            self.active = True
            self.firing = True

    def toggle_absolute_validation(self) -> None:
        self.absolute_validation = not self.absolute_validation

    @property
    def status_label(self) -> str:
        if not self.active:
            return "PAUSED"
        return "ACTIVE+FIRING" if self.firing else "ACTIVE"

    @property
    def mouse_mode_label(self) -> str:
        return "absolute" if self.absolute_validation else "servo"


class VideoDiagnostics:
    def lines(
        self,
        mode: VideoRuntimeMode,
        display_fps: float,
        detect_fps: float,
        detection_latency_ms: float,
        target_bbox,
        aim_point,
        control_target,
        has_measurement: bool,
        target_is_fresh: bool,
    ) -> list[str]:
        return [
            f"Status: {mode.status_label}",
            f"Mouse mode: {mode.mouse_mode_label}",
            f"Display FPS: {display_fps:.1f}",
            f"Detect FPS: {detect_fps:.1f}",
            f"Detect latency: {detection_latency_ms:.1f} ms",
            f"Fresh: {target_is_fresh}",
            f"Measurement: {has_measurement}",
            f"Target: {target_bbox}",
            f"Aim: {aim_point}",
            f"Control target: {control_target}",
            "A: active | F: firing | M: mouse mode | Enter: firing | Q: quit",
        ]


class VideoWakeUp:
    def __init__(self, roi_offset: Point, crosshair: Point) -> None:
        self._active = False
        self._left_held = False
        self._roi_offset = roi_offset
        self._crosshair = crosshair

    def set_mode(self, active: bool, firing: bool) -> None:
        self._active = bool(active)
        self._left_held = bool(active and firing)

    def set_running(self, running: bool) -> None:
        self.set_mode(running, running)

    def get_active(self) -> bool:
        return self._active

    def get_left_held(self) -> bool:
        return self._left_held

    def get_crosshair(self) -> Point:
        return self._crosshair

    def get_roi_offset(self) -> Point:
        return self._roi_offset

    def should_exit(self) -> bool:
        return False

    def stop(self) -> None:
        return None


@dataclass
class VideoRuntimeServices:
    config: Config
    state: RuntimeState
    wakeup: VideoWakeUp
    detector: TargetDetector
    aim_calculator: AimPointCalculator
    mouse_controller: MouseController
    throttle: Throttle
    detect_scheduler: DetectionScheduler
    debug_printer: ThrottledPrinter
    debug_visualizer: DebugVisualizer
    pipeline: RuntimePipeline
    target_tracker: Optional[object]
    _latest_frame: Optional[np.ndarray] = None
    _latest_time: float = 0.0
    _latest_seq: int = 0

    def set_frame(self, frame: np.ndarray) -> None:
        self._latest_frame = frame
        self._latest_time = time.time()
        self._latest_seq += 1

    def get_frame(self):
        return self._latest_frame, self._latest_time, self._latest_seq

    def stop(self) -> None:
        self.mouse_controller.stop()
        self.debug_visualizer.close()
        cv2.destroyAllWindows()


class VideoTestController:
    def __init__(
        self,
        video_path: str,
        log_dir: Optional[Path] = None,
        duration_seconds: Optional[float] = None,
        mouse_enabled: bool = True,
        headless: bool = False,
    ) -> None:
        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")

        self.config = runtime_core._load_config(str(PROJECT_ROOT / "config.json"))
        self.duration_seconds = duration_seconds
        self.mouse_enabled = mouse_enabled
        self.headless = headless
        if not self.mouse_enabled:
            self.config.servo_thread_enabled = False
        self.screen_width, self.screen_height, _, _ = runtime_core._screen_geometry(self.config)
        self.frame_adapter = VideoFrameAdapter(
            screen_size=(self.screen_width, self.screen_height),
            roi_size=(int(self.config.roi_width), int(self.config.roi_height)),
        )
        self.roi_offset = self.frame_adapter.roi_offset
        self.crosshair = self.frame_adapter.crosshair
        self.services = self._create_video_services()
        self.running = False
        self.logger = VideoRunLogger(log_dir or (PROJECT_ROOT / "tests" / "logs"))
        self.mode = VideoRuntimeMode()
        self.diagnostics = VideoDiagnostics()
        self.last_detection_latency_ms = 0.0
        self.last_control_target = None
        self.last_has_measurement = False
        self.last_target_is_fresh = False
        self.last_aim_point = None
        self.display_frame_count = 0
        self.last_fps_time = time.perf_counter()
        self.display_fps = 0.0
        self.detect_count = 0
        self.last_detect_fps_time = time.perf_counter()
        self.detect_fps = 0.0

    def _create_video_services(self) -> VideoRuntimeServices:
        wakeup = VideoWakeUp(self.roi_offset, self.crosshair)

        detector = TargetDetector()
        detector.set_debug(True)

        aim_calculator = AimPointCalculator(self.config)
        aim_calculator.set_wakeup(wakeup)

        target_tracker = RuntimeServices._create_tracker(self.config)
        state = RuntimeState()
        pipeline = RuntimePipeline(
            config=self.config,
            aim_calculator=aim_calculator,
            tracker=target_tracker,
            state=state,
            fallback_point=get_cursor_pos,
        )

        mouse_controller = MouseController(self.config)
        throttle = Throttle(self.config)
        detect_scheduler = DetectionScheduler(self.config)
        debug_printer = ThrottledPrinter(0.5)
        debug_visualizer = DebugVisualizer(
            enabled=bool(getattr(self.config, "debug_enabled", False)),
            roi_size=(self.config.roi_width, self.config.roi_height),
            window_scale=getattr(self.config, "debug_window_scale", 1.6),
        )

        if getattr(self.config, "yolo_preload", False):
            detector.preload(self.config, (self.config.roi_height, self.config.roi_width, 3))

        return VideoRuntimeServices(
            config=self.config,
            state=state,
            wakeup=wakeup,
            detector=detector,
            aim_calculator=aim_calculator,
            mouse_controller=mouse_controller,
            throttle=throttle,
            detect_scheduler=detect_scheduler,
            debug_printer=debug_printer,
            debug_visualizer=debug_visualizer,
            pipeline=pipeline,
            target_tracker=target_tracker,
        )

    def run(self) -> None:
        self.running = True
        frame_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        video_fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 30.0)
        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
        playback = PlaybackClock(video_fps, total_frames)

        print("\n视频测试程序 - 全屏中心 ROI + RuntimePipeline 模式")
        print("=" * 60)
        print(f"视频: {self.video_path}")
        print(f"屏幕分辨率: {self.screen_width}x{self.screen_height}")
        print(f"中心 ROI: 左上角 {self.roi_offset}, 大小 {self.config.roi_width}x{self.config.roi_height}")
        print(f"视频尺寸: {frame_w}x{frame_h}, FPS: {video_fps:.2f}")
        print("按 A 切换 active-only，按 F/Enter 切换 active+firing，按 M 切换鼠标验证模式，按 Q 退出")
        print("=" * 60)

        if self.headless:
            self.mode.active = True
            self.mode.firing = True
            self.services.wakeup.set_mode(True, True)

        if not self.headless:
            cv2.namedWindow("Video Test", cv2.WINDOW_NORMAL)
            cv2.setWindowProperty("Video Test", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        try:
            while self.running:
                elapsed = playback.elapsed()
                if self.duration_seconds is not None and elapsed >= self.duration_seconds:
                    break
                frame_index = playback.frame_index(elapsed)
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ret, source_frame = self.cap.read()
                if not ret:
                    playback.reset()
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                canvas = self.frame_adapter.make_canvas(source_frame)
                roi_frame = self.frame_adapter.crop_center_roi(canvas)
                self.services.set_frame(roi_frame)

                self.services.wakeup.set_mode(self.mode.active, self.mode.firing)
                if self.mode.active:
                    if self.services.target_tracker is not None:
                        self.services.target_tracker.configure_from(self.config)
                    runtime_core._update_firing_state(self.services)
                    detect_started = time.perf_counter()
                    control = runtime_core._update_detection_and_control(self.config, self.services, active=True)
                    self.last_detection_latency_ms = (time.perf_counter() - detect_started) * 1000.0
                    self.last_control_target = control.target
                    self.last_has_measurement = control.has_measurement
                    self.last_target_is_fresh = bool(getattr(self.services.detector, "last_result_fresh", False))
                    self.last_aim_point = self.services.state.last_aim_base
                    if control.has_measurement:
                        self.detect_count += 1
                    cursor_before = get_cursor_pos() if self.mouse_enabled else None
                    self._apply_control(control)
                    cursor_after = get_cursor_pos() if self.mouse_enabled else cursor_before
                    self._write_log_event(frame_index, cursor_before, cursor_after)
                else:
                    self.last_control_target = None
                    self.last_has_measurement = False
                    self.last_target_is_fresh = False
                    self.last_aim_point = None
                    runtime_core._reset_inactive(self.services)

                if self.headless:
                    continue

                display = self._make_display_frame(canvas)
                cv2.imshow("Video Test", display)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key in (ord("a"), ord("A")):
                    self._toggle_active_only()
                if key in (ord("f"), ord("F"), 13):
                    self._toggle_firing()
                if key in (ord("m"), ord("M")):
                    self._toggle_mouse_mode()
        finally:
            self.running = False
            self.logger.close()
            print(f"日志文件: {self.logger.jsonl_path}")
            print(f"汇总文件: {self.logger.summary_path}")
            self.services.stop()
            self.cap.release()

    def _write_log_event(self, frame_index: int, cursor_before, cursor_after) -> None:
        target = self.services.detector.last_result
        event = {
            "t": time.time(),
            "video_frame_index": frame_index,
            "display_fps": self.display_fps,
            "detect_fps": self.detect_fps,
            "detect_latency_ms": self.last_detection_latency_ms,
            "active": self.mode.active,
            "firing": self.mode.firing,
            "mouse_mode": self.mode.mouse_mode_label,
            "fresh": self.last_target_is_fresh,
            "has_measurement": self.last_has_measurement,
            "target_bbox": target.bbox if target is not None else None,
            "target_confidence": getattr(target, "confidence", None) if target is not None else None,
            "target_class": getattr(target, "class_name", None) if target is not None else None,
            "aim_point": self.last_aim_point,
            "control_target": self.last_control_target,
            "crosshair": self.crosshair,
            "cursor_before": cursor_before,
            "cursor_after": cursor_after,
            "target_error_before": self._distance(cursor_before, self.last_control_target),
            "target_error_after": self._distance(cursor_after, self.last_control_target),
        }
        self.logger.write_event(event)

    def _distance(self, a, b) -> Optional[float]:
        if a is None or b is None:
            return None
        dx = float(a[0] - b[0])
        dy = float(a[1] - b[1])
        return (dx * dx + dy * dy) ** 0.5

    def _apply_control(self, control) -> None:
        if not self.mouse_enabled:
            return

        if self.mode.absolute_validation:
            if control.active and control.has_measurement and control.target is not None:
                self.services.mouse_controller._move_absolute(control.target)
            else:
                self.services.mouse_controller.update_target(
                    target_pos=None,
                    crosshair_pos=control.crosshair,
                    has_measurement=False,
                    active=control.active,
                )
            return

        self.services.mouse_controller.update_target(
            control.target,
            crosshair_pos=control.crosshair,
            has_measurement=control.has_measurement,
            active=control.active,
        )

    def _make_display_frame(self, canvas: np.ndarray) -> np.ndarray:
        display = canvas.copy()
        roi_left, roi_top = self.roi_offset
        roi_right = roi_left + int(self.config.roi_width)
        roi_bottom = roi_top + int(self.config.roi_height)
        cv2.rectangle(display, (roi_left, roi_top), (roi_right, roi_bottom), (255, 255, 0), 2)

        target = self.services.detector.last_result
        if target is not None:
            cv2.rectangle(
                display,
                (roi_left + target.x, roi_top + target.y),
                (roi_left + target.x + target.w, roi_top + target.y + target.h),
                (0, 255, 0),
                2,
            )

        aim_point = self.services.state.last_aim_base
        if aim_point is not None:
            cv2.circle(display, (int(aim_point[0]), int(aim_point[1])), 6, (0, 0, 255), -1)

        cv2.drawMarker(display, self.crosshair, (255, 255, 255), cv2.MARKER_CROSS, 24, 2)
        self._update_fps_counters()
        self._draw_diagnostics(display)
        return display

    def _update_fps_counters(self) -> None:
        now = time.perf_counter()
        self.display_frame_count += 1
        elapsed = now - self.last_fps_time
        if elapsed >= 0.5:
            self.display_fps = self.display_frame_count / elapsed
            self.display_frame_count = 0
            self.last_fps_time = now

        detect_elapsed = now - self.last_detect_fps_time
        if detect_elapsed >= 0.5:
            self.detect_fps = self.detect_count / detect_elapsed
            self.detect_count = 0
            self.last_detect_fps_time = now

    def _draw_diagnostics(self, display: np.ndarray) -> None:
        target = self.services.detector.last_result
        lines = self.diagnostics.lines(
            mode=self.mode,
            display_fps=self.display_fps,
            detect_fps=self.detect_fps,
            detection_latency_ms=self.last_detection_latency_ms,
            target_bbox=target.bbox if target is not None else None,
            aim_point=self.last_aim_point,
            control_target=self.last_control_target,
            has_measurement=self.last_has_measurement,
            target_is_fresh=self.last_target_is_fresh,
        )
        y = 32
        for line in lines:
            cv2.putText(display, line, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4)
            cv2.putText(display, line, (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1)
            y += 28

    def _toggle_active_only(self) -> None:
        self.mode.toggle_active()
        self.services.wakeup.set_mode(self.mode.active, self.mode.firing)
        if not self.mode.active:
            self._reset_inactive_control()
        print(f"\n状态切换: {self.mode.status_label}")

    def _toggle_firing(self) -> None:
        self.mode.toggle_firing()
        self.services.wakeup.set_mode(self.mode.active, self.mode.firing)
        print(f"\n状态切换: {self.mode.status_label}")

    def _toggle_mouse_mode(self) -> None:
        self.mode.toggle_absolute_validation()
        self.services.mouse_controller.reset()
        print(f"\n鼠标模式: {self.mode.mouse_mode_label}")

    def _reset_inactive_control(self) -> None:
        runtime_core._reset_inactive(self.services)
        self.services.mouse_controller.update_target(
            target_pos=None,
            crosshair_pos=self.crosshair,
            has_measurement=False,
            active=False,
        )
        self.last_control_target = None
        self.last_has_measurement = False
        self.last_target_is_fresh = False
        self.last_aim_point = None


def parse_args(argv: Optional[list[str]] = None):
    parser = argparse.ArgumentParser(description="运行视频测试并输出诊断日志")
    parser.add_argument("--video", help="视频文件路径；不提供时打开文件选择框")
    parser.add_argument("--duration", type=float, help="自动运行秒数，到时退出")
    parser.add_argument("--no-mouse", action="store_true", help="不移动鼠标，只记录日志")
    parser.add_argument("--log-dir", default=str(PROJECT_ROOT / "tests" / "logs"), help="日志输出目录")
    parser.add_argument("--headless", action="store_true", help="不打开窗口，自动 active+firing；需要 --video 和 --duration")
    return parser.parse_args(argv)


def choose_video_file() -> Optional[str]:
    root = tk.Tk()
    root.withdraw()
    try:
        return filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mov *.mkv *.flv"),
                ("所有文件", "*.*"),
            ],
        )
    finally:
        root.destroy()


if __name__ == "__main__":
    args = parse_args()
    print("\n视频测试程序")
    print("=" * 50)

    selected_video = args.video
    if not selected_video:
        print("正在打开文件选择对话框...")
        selected_video = choose_video_file()
    if not selected_video:
        print("用户取消选择")
        sys.exit(1)

    print(f"已选择: {Path(selected_video).name}")
    try:
        VideoTestController(
            selected_video,
            log_dir=Path(args.log_dir),
            duration_seconds=args.duration,
            mouse_enabled=not args.no_mouse,
            headless=args.headless,
        ).run()
    except Exception as exc:
        print(f"错误: {exc}")
        import traceback

        traceback.print_exc()
