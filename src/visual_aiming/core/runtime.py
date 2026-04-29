# -*- coding: utf-8 -*-
import ctypes
import sys
import time
from typing import Optional, Tuple

import mss

from ..config import Config
from ..common.timing import sleep_precise
from .runtime_services import RuntimeServices
from .schemas import ControlTarget


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def main():
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

    config_path = "config.json"
    config = _load_config(config_path)
    screen_width, screen_height, roi_offset, crosshair = _screen_geometry(config)

    services = None
    try:
        services = RuntimeServices.create(
            config=config,
            roi_offset=roi_offset,
            default_crosshair=crosshair,
            config_path=config_path,
        )
        _print_startup(config, screen_width, screen_height, roi_offset)
        _run_loop(config, services)
    finally:
        if services is not None:
            services.stop()
        print(f"[{time.strftime('%H:%M:%S')}] 程序已退出")


def _load_config(config_path: str) -> Config:
    config = Config()
    try:
        config.load(config_path)
        print(f"[{time.strftime('%H:%M:%S')}] 已加载配置文件 {config_path}")
    except FileNotFoundError:
        print(f"[{time.strftime('%H:%M:%S')}] 未找到 {config_path}，使用默认配置并保存")
        config.save(config_path)
    return config


def _screen_geometry(config: Config) -> Tuple[int, int, Tuple[int, int], Tuple[int, int]]:
    with mss.MSS() as sct:
        screen_width = sct.monitors[1]["width"]
        screen_height = sct.monitors[1]["height"]
    fixed_roi_left = (screen_width - config.roi_width) // 2
    fixed_roi_top = (screen_height - config.roi_height) // 2
    crosshair = (screen_width // 2, screen_height // 2)
    return screen_width, screen_height, (fixed_roi_left, fixed_roi_top), crosshair


def _print_startup(
    config: Config,
    screen_width: int,
    screen_height: int,
    roi_offset: Tuple[int, int],
) -> None:
    fixed_roi_left, fixed_roi_top = roi_offset
    print(f"[{time.strftime('%H:%M:%S')}] 屏幕分辨率: {screen_width}x{screen_height}")
    print(
        f"[{time.strftime('%H:%M:%S')}] 固定截图区域: "
        f"左上角({fixed_roi_left}, {fixed_roi_top}), 大小{config.roi_width}x{config.roi_height}"
    )
    print(f"[{time.strftime('%H:%M:%S')}] 程序已启动，按 Ctrl+Q 退出。")
    print("使用方法：同时按住 Shift+右键，然后按下左键 -> 辅助激活 -> 按住左键开始吸附")
    if bool(getattr(config, "debug_enabled", False)):
        print("调试窗口实时显示检测结果，按 ESC 可关闭调试窗口。")
    else:
        print("调试窗口已关闭，可在 config.json 中将 debug_enabled 设为 true。")


def _run_loop(config: Config, services: RuntimeServices) -> None:
    last_time = time.perf_counter()
    while not services.wakeup.should_exit():
        try:
            last_time = _sleep_for_poll_interval(config, last_time)
            active = services.wakeup.get_active()
            services.set_capture_active(active)
            if services.target_tracker is not None:
                services.target_tracker.configure_from(config)

            if not active:
                _reset_inactive(services)
                continue

            _update_firing_state(services)
            control = _update_detection_and_control(config, services, active)
            services.mouse_controller.update_target(
                control.target,
                crosshair_pos=control.crosshair,
                has_measurement=control.has_measurement,
                active=control.active,
            )
        except KeyboardInterrupt:
            print(f"[{time.strftime('%H:%M:%S')}] 检测到 Ctrl+C，但程序不会退出。请按 Ctrl+Q 退出。")
            continue
        except Exception as exc:
            print(f"[{time.strftime('%H:%M:%S')}] 运行时错误: {exc}")
            continue


def _sleep_for_poll_interval(config: Config, last_time: float) -> float:
    poll_interval = 1.0 / max(float(getattr(config, "runtime_poll_fps", 120)), 1.0)
    now_perf = time.perf_counter()
    sleep_time = poll_interval - (now_perf - last_time)
    if sleep_time > 0:
        sleep_precise(sleep_time)
    return time.perf_counter()


def _reset_inactive(services: RuntimeServices) -> None:
    services.pipeline.reset()
    services.detect_scheduler.reset()
    services.mouse_controller.reset()


def _update_firing_state(services: RuntimeServices) -> None:
    transition = services.state.update_firing(services.wakeup.get_left_held())
    if transition == "started":
        print(f"[{time.strftime('%H:%M:%S')}] 吸附开始")
    elif transition == "stopped":
        print(f"[{time.strftime('%H:%M:%S')}] 吸附停止")


def _update_detection_and_control(
    config: Config,
    services: RuntimeServices,
    active: bool,
) -> ControlTarget:
    crosshair = services.wakeup.get_crosshair()
    if not _should_detect(config, services, active, services.state.firing):
        return services.pipeline.current_control(active=active, crosshair=crosshair)

    frame, _, capture_seq = services.get_frame()
    if _is_reused_frame(config, services, frame, capture_seq):
        return services.pipeline.current_control(active=active, crosshair=crosshair)

    if frame is None:
        return services.pipeline.current_control(active=active, crosshair=crosshair)

    if capture_seq is not None:
        services.state.last_capture_seq = capture_seq

    roi_center = (config.roi_width // 2, config.roi_height // 2)
    target = services.detector.detect(frame, config, roi_center, firing=services.state.firing)
    target_is_fresh = bool(getattr(services.detector, "last_result_fresh", True))
    roi_offset = services.wakeup.get_roi_offset()
    result = services.pipeline.process_detection(
        active=active,
        firing=services.state.firing,
        target=target,
        target_is_fresh=target_is_fresh,
        roi_offset=roi_offset,
        crosshair=crosshair,
        now=time.time(),
    )
    _log_detection_debug(config, services, target, target_is_fresh, result.aim_point)
    _update_debug_window(services, frame, result.debug_bbox, result.aim_point, crosshair, roi_offset)
    return result.control


def _should_detect(
    config: Config,
    services: RuntimeServices,
    active: bool,
    firing: bool,
) -> bool:
    if not services.detect_scheduler.due(active, firing):
        return False
    services.detect_scheduler.mark()
    if firing and bool(getattr(config, "firing_bypass_throttle", True)):
        return True
    return services.throttle.allow()


def _is_reused_frame(
    config: Config,
    services: RuntimeServices,
    frame,
    capture_seq: Optional[int],
) -> bool:
    if frame is None:
        return False
    return (
        bool(getattr(config, "detect_only_new_frames", True))
        and capture_seq is not None
        and capture_seq == services.state.last_capture_seq
    )


def _log_detection_debug(
    config: Config,
    services: RuntimeServices,
    target,
    target_is_fresh: bool,
    aim_point,
) -> None:
    if not bool(getattr(config, "debug_log_enabled", False)):
        return
    if target is not None and target_is_fresh:
        services.debug_printer.print(
            "target_detected",
            f"[DEBUG] 检测到目标 class={target.class_name} "
            f"(id={target.class_id}) bbox={target.bbox} conf={target.confidence:.2f}",
        )
        if aim_point is not None:
            services.debug_printer.print("aim_point", f"[DEBUG] 瞄准点: {aim_point}")
        else:
            services.debug_printer.print("aim_none", "[DEBUG] aim_calc 返回 None")
    elif target is not None:
        services.debug_printer.print("target_reused", "[DEBUG] 跳帧复用旧检测框，不作为新测量")
    else:
        services.debug_printer.print("target_missing", "[DEBUG] 未检测到目标")


def _update_debug_window(
    services: RuntimeServices,
    frame,
    bbox,
    aim_point,
    crosshair,
    roi_offset: Optional[Tuple[int, int]],
) -> None:
    if roi_offset is None:
        return
    roi_left, roi_top = roi_offset
    services.debug_visualizer.update(frame, bbox, aim_point, crosshair, roi_left, roi_top)


if __name__ == "__main__":
    main()

