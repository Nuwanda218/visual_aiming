# -*- coding: utf-8 -*-
import sys
import time
import ctypes
import mss
import cv2
from ..actions.mouse_control import get_cursor_pos

from ..config import Config
from ..actions.input_listener import WakeUpModule
from ..vision.screen_capture import ScreenCapture
from ..vision.capture_worker import CaptureWorker
from ..vision.detection import TargetDetector
from .aim_calculator import AimPointCalculator
from ..actions.mouse_control import MouseController
from .throttle import Throttle
from ..actions.debug_visualizer import DebugVisualizer
from ..common.utils import ThrottledPrinter
from .target_tracker import TargetTracker
from ..common.timing import sleep_precise
from .detect_scheduler import DetectionScheduler
from ..actions.config_window import ConfigWindow

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def main():
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

    config = Config()
    try:
        config.load("config.json")
        print(f"[{time.strftime('%H:%M:%S')}] 已加载配置文件 config.json")
    except FileNotFoundError:
        print(f"[{time.strftime('%H:%M:%S')}] 未找到 config.json，使用默认配置并保存")
        config.save("config.json")

    with mss.MSS() as sct:
        screen_width = sct.monitors[1]["width"]
        screen_height = sct.monitors[1]["height"]
    fixed_roi_left = (screen_width - config.roi_width) // 2
    fixed_roi_top = (screen_height - config.roi_height) // 2
    print(f"[{time.strftime('%H:%M:%S')}] 屏幕分辨率: {screen_width}x{screen_height}")
    print(f"[{time.strftime('%H:%M:%S')}] 固定截图区域: 左上角({fixed_roi_left}, {fixed_roi_top}), 大小{config.roi_width}x{config.roi_height}")

    screen_center_x = screen_width // 2
    screen_center_y = screen_height // 2

    wakeup = WakeUpModule(config)
    wakeup.set_fixed_roi_offset((fixed_roi_left, fixed_roi_top))
    wakeup.set_default_crosshair(screen_center_x, screen_center_y)

    capture_worker = None
    screen = None
    if bool(getattr(config, "capture_thread_enabled", True)):
        capture_worker = CaptureWorker(config, wakeup)
        capture_worker.start()
    else:
        screen = ScreenCapture(config, wakeup)
    detector = TargetDetector()
    detector.set_debug(True)
    aim_calc = AimPointCalculator(config)
    aim_calc.set_wakeup(wakeup)
    target_tracker = None
    if bool(getattr(config, "tracker_enabled", True)):
        target_tracker = TargetTracker(
            smoothing_factor=float(getattr(config, "tracker_smoothing_factor", 0.66)),
            prediction_time=float(getattr(config, "tracker_prediction_time", 0.025)),
            stop_threshold=float(getattr(config, "tracker_stop_threshold", 10.0)),
            reset_distance=float(getattr(config, "tracker_reset_distance", 200.0)),
        )
    mouse_ctrl = MouseController(config)
    throttle = Throttle(config)
    detect_scheduler = DetectionScheduler(config)
    config_window = None
    if bool(getattr(config, "config_ui_enabled", True)):
        config_window = ConfigWindow(config, "config.json")
        config_window.start()

    roi_center = (config.roi_width // 2, config.roi_height // 2)
    debug_enabled = bool(getattr(config, "debug_enabled", False))
    debug_log_enabled = bool(getattr(config, "debug_log_enabled", False))
    debug_printer = ThrottledPrinter(0.5)
    debug_viz = DebugVisualizer(
        enabled=debug_enabled,
        roi_size=(config.roi_width, config.roi_height),
        window_scale=getattr(config, "debug_window_scale", 1.6),
    )
    if getattr(config, "yolo_preload", False):
        detector.preload(config, (config.roi_height, config.roi_width, 3))

    print(f"[{time.strftime('%H:%M:%S')}] 程序已启动，按 Ctrl+Q 退出。")
    print("使用方法：同时按住 Shift+右键，然后按下左键 -> 辅助激活 -> 按住左键开始吸附")
    if debug_enabled:
        print("调试窗口实时显示检测结果，按 ESC 可关闭调试窗口。")
    else:
        print("调试窗口已关闭，可在 config.json 中将 debug_enabled 设为 true。")

    poll_interval = 1.0 / max(float(getattr(config, "runtime_poll_fps", 120)), 1.0)
    last_time = time.perf_counter()
    firing = False
    last_aim_base = None
    last_capture_seq = -1
    firing_bypass_throttle = bool(getattr(config, "firing_bypass_throttle", True))
    firing_hold_last_aim = bool(getattr(config, "firing_hold_last_aim", True))
    detect_only_new_frames = bool(getattr(config, "detect_only_new_frames", True))

    while not wakeup.should_exit():
        try:
            now = time.time()
            now_perf = time.perf_counter()
            sleep_time = poll_interval - (now_perf - last_time)
            if sleep_time > 0:
                sleep_precise(sleep_time)
            last_time = time.perf_counter()
            now = time.time()

            active = wakeup.get_active()
            if target_tracker is not None:
                target_tracker.configure_from(config)
            if capture_worker is not None:
                capture_worker.set_active(active)
            if not active:
                if firing:
                    firing = False
                if target_tracker is not None:
                    target_tracker.reset()
                detect_scheduler.reset()
                last_capture_seq = -1
                mouse_ctrl.reset()
                continue

            left_held = wakeup.get_left_held()
            if left_held and not firing:
                firing = True
                print(f"[{time.strftime('%H:%M:%S')}] 吸附开始")
            elif not left_held and firing:
                firing = False
                print(f"[{time.strftime('%H:%M:%S')}] 吸附停止")

            should_detect = False
            if detect_scheduler.due(active, firing):
                detect_scheduler.mark()
                if firing and firing_bypass_throttle:
                    should_detect = True
                else:
                    should_detect = throttle.allow()

            aim_base = None
            if should_detect:
                capture_seq = None
                if capture_worker is not None:
                    frame, _, capture_seq = capture_worker.get_latest()
                    if (
                        detect_only_new_frames
                        and capture_seq == last_capture_seq
                    ):
                        frame = None
                else:
                    frame = screen.grab()
                if frame is not None:
                    if capture_seq is not None:
                        last_capture_seq = capture_seq
                    target = detector.detect(frame, config, roi_center, firing=firing)
                    target_is_fresh = bool(getattr(detector, "last_result_fresh", True))
                    roi_offset = wakeup.get_roi_offset()
                    calibrate_point = wakeup.get_crosshair()

                    if roi_offset is not None and calibrate_point is not None:
                        roi_left, roi_top = roi_offset
                        raw_aim_base = aim_calc.calculate(target, roi_left, roi_top)
                        aim_base = raw_aim_base if target_is_fresh else None
                        fresh_measurement = target_is_fresh and target is not None and aim_base is not None
                        tracker_allowed = not (
                            firing and bool(getattr(config, "firing_disable_tracker_prediction", True))
                        )
                        if fresh_measurement and target_tracker is not None and tracker_allowed:
                            aim_base = target_tracker.update(aim_base, time.time())
                        elif fresh_measurement and target_tracker is not None and not tracker_allowed:
                            target_tracker.reset()

                        if target is not None and target_is_fresh:
                            if debug_log_enabled:
                                debug_printer.print(
                                    "target_detected",
                                    f"[DEBUG] 检测到目标 class={target.class_name} "
                                    f"(id={target.class_id}) bbox={target.bbox} conf={target.confidence:.2f}",
                                )
                            if aim_base is not None:
                                last_aim_base = aim_base
                                if debug_log_enabled:
                                    debug_printer.print("aim_point", f"[DEBUG] 瞄准点: {aim_base}")
                            else:
                                if debug_log_enabled:
                                    debug_printer.print("aim_none", "[DEBUG] aim_calc 返回 None")
                                if not (firing and firing_hold_last_aim and last_aim_base is not None):
                                    cross = wakeup.get_crosshair()
                                    last_aim_base = cross if cross else get_cursor_pos()
                        elif target is not None:
                            if debug_log_enabled:
                                debug_printer.print("target_reused", "[DEBUG] 跳帧复用旧检测框，不作为新测量")
                        else:
                            if debug_log_enabled:
                                debug_printer.print("target_missing", "[DEBUG] 未检测到目标")
                            if aim_base is not None:
                                last_aim_base = aim_base
                                if debug_log_enabled:
                                    debug_printer.print("aim_locked", f"[DEBUG] 沿用锁定瞄准点: {aim_base}")
                            else:
                                if not (firing and firing_hold_last_aim and last_aim_base is not None):
                                    cross = wakeup.get_crosshair()
                                    last_aim_base = cross if cross else get_cursor_pos()

                        bbox_for_debug = target.bbox if target is not None else None
                        debug_viz.update(frame, bbox_for_debug, aim_base, calibrate_point, roi_left, roi_top)
                    else:
                        pass
                else:
                    if last_aim_base is None:
                        cross = wakeup.get_crosshair()
                        last_aim_base = cross if cross else get_cursor_pos()
            else:
                if last_aim_base is None:
                    cross = wakeup.get_crosshair()
                    last_aim_base = cross if cross else get_cursor_pos()

            base_target = aim_base
            used_tracker_prediction = False
            tracker_now = time.time()
            if (
                base_target is None
                and target_tracker is not None
                and not (firing and bool(getattr(config, "firing_disable_tracker_prediction", True)))
                and target_tracker.has_recent_track(
                    tracker_now,
                    float(getattr(config, "tracker_max_prediction_ms", 160.0)),
                )
            ):
                base_target = target_tracker.predict(tracker_now)
                used_tracker_prediction = True

            if base_target is None and last_aim_base is not None:
                base_target = last_aim_base

            control_target = None
            if base_target is not None:
                control_target = base_target

            has_measurement = aim_base is not None
            if (
                not has_measurement
                and used_tracker_prediction
                and bool(getattr(config, "tracker_prediction_as_measurement", True))
            ):
                has_measurement = True
            mouse_ctrl.update_target(
                control_target,
                crosshair_pos=wakeup.get_crosshair(),
                has_measurement=has_measurement,
                active=active,
            )

        except KeyboardInterrupt:
            print(f"[{time.strftime('%H:%M:%S')}] 检测到 Ctrl+C，但程序不会退出。请按 Ctrl+Q 退出。")
            continue
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] 运行时错误: {e}")
            continue

    mouse_ctrl.stop()
    if config_window is not None:
        config_window.stop()
    if capture_worker is not None:
        capture_worker.stop()
    elif screen is not None:
        screen.close()
    wakeup.stop()
    cv2.destroyAllWindows()
    print(f"[{time.strftime('%H:%M:%S')}] 程序已退出")

if __name__ == "__main__":
    main()
