# -*- coding: utf-8 -*-
import sys
import time
import ctypes
import mss
import cv2
from mouse_control import get_cursor_pos

from config import Config
from input_listener import WakeUpModule
from screen_capture import ScreenCapture
from detection import TargetDetector
from aim_calculator import AimPointCalculator
from mouse_control import MouseController
from throttle import Throttle
from recoil import RecoilCompensator
from debug_visualizer import DebugVisualizer

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
    sys.exit()

def main():
    config = Config()
    try:
        config.load("config.json")
        print(f"[{time.strftime('%H:%M:%S')}] 已加载配置文件 config.json")
    except FileNotFoundError:
        print(f"[{time.strftime('%H:%M:%S')}] 未找到 config.json，使用默认配置并保存")
        config.save("config.json")

    with mss.mss() as sct:
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

    screen = ScreenCapture(config, wakeup)
    detector = TargetDetector()
    detector.set_debug(True)
    aim_calc = AimPointCalculator(config)
    aim_calc.set_wakeup(wakeup)
    mouse_ctrl = MouseController(config)
    throttle = Throttle(config)

    recoil_comp = None
    if config.recoil_enabled:
        recoil_comp = RecoilCompensator(config.recoil_profile_path)
    else:
        print("[压枪] 压枪已禁用")

    roi_center = (config.roi_width // 2, config.roi_height // 2)
    debug_viz = DebugVisualizer(enabled=True, roi_size=(config.roi_width, config.roi_height))

    print(f"[{time.strftime('%H:%M:%S')}] 程序已启动，按 Ctrl+Q 退出。")
    print("使用方法：同时按住 Shift+右键，然后按下左键 -> 辅助激活 -> 按住左键开始压枪和吸附")
    print("调试窗口实时显示检测结果，按 ESC 可关闭调试窗口。")

    frame_interval = 1.0 / config.capture_fps
    last_time = time.time()
    firing = False
    firing_start_time = 0.0
    last_aim_base = None

    while not wakeup.should_exit():
        try:
            now = time.time()
            sleep_time = frame_interval - (now - last_time)
            if sleep_time > 0:
                time.sleep(sleep_time)
            last_time = time.time()

            active = wakeup.get_active()
            if not active:
                if firing:
                    firing = False
                    if recoil_comp:
                        recoil_comp.stop_firing()
                continue

            left_held = wakeup.get_left_held()
            if left_held and not firing:
                firing = True
                firing_start_time = time.time()
                if recoil_comp:
                    recoil_comp.start_firing(firing_start_time)
                print(f"[{time.strftime('%H:%M:%S')}] 压枪开始")
            elif not left_held and firing:
                firing = False
                if recoil_comp:
                    recoil_comp.stop_firing()
                print(f"[{time.strftime('%H:%M:%S')}] 压枪停止")

            if throttle.allow():
                frame = screen.grab()
                if frame is not None:
                    target = detector.detect(frame, config, roi_center)
                    roi_offset = wakeup.get_roi_offset()
                    calibrate_point = wakeup.get_crosshair()
                    aim_base = None

                    if roi_offset is not None and calibrate_point is not None:
                        roi_left, roi_top = roi_offset
                        aim_base = aim_calc.calculate(target, roi_left, roi_top)

                        if target is not None:
                            print(f"[DEBUG] 检测到目标 bbox={target.bbox} conf={target.confidence:.2f}")
                            if aim_base is not None:
                                last_aim_base = aim_base
                                print(f"[DEBUG] 瞄准点: {aim_base}")
                            else:
                                print(f"[DEBUG] aim_calc 返回 None")
                                cross = wakeup.get_crosshair()
                                last_aim_base = cross if cross else get_cursor_pos()
                        else:
                            print(f"[DEBUG] 未检测到目标")
                            if aim_base is not None:
                                last_aim_base = aim_base
                                print(f"[DEBUG] 沿用锁定瞄准点: {aim_base}")
                            else:
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

            comp = (0, 0)
            if firing and recoil_comp:
                comp = recoil_comp.get_current_offset(time.time())

            target_pos = (last_aim_base[0] + comp[0], last_aim_base[1] + comp[1])
            mouse_ctrl.move_towards(target_pos)

        except KeyboardInterrupt:
            print(f"[{time.strftime('%H:%M:%S')}] 检测到 Ctrl+C，但程序不会退出。请按 Ctrl+Q 退出。")
            continue
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] 运行时错误: {e}")
            continue

    wakeup.stop()
    cv2.destroyAllWindows()
    print(f"[{time.strftime('%H:%M:%S')}] 程序已退出")

if __name__ == "__main__":
    main()
