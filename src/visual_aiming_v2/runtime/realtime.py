"""运行编排层 — 实时运行循环（方案 B：单线程 + 跳帧检测）。"""
from __future__ import annotations

import time
from typing import Callable, Optional

from visual_aiming_v2.shared.ports import ActuationPort, CapturePort, DetectorPort, OutputPort
from visual_aiming_v2.shared.schemas import TickResult


def run_realtime(
    capture: CapturePort,
    detector: DetectorPort,
    actuator: ActuationPort,
    output: OutputPort,
    hotkey,
    detect_fps: float = 30.0,
    on_tick: Optional[Callable] = None,
) -> None:
    """实时运行循环：热键激活时截屏→检测→控制→鼠标输出。

    方案 B — 单线程 + 跳帧检测：
    - 每帧都截屏和输出鼠标（~2ms，高频平滑）
    - 按 detect_fps 频率决定是否跑 YOLO（~10ms，低频节省 GPU）
    - FpsController 在跳帧时用速度状态继续平滑输出
    """
    detect_interval = 1.0 / max(1.0, detect_fps)
    last_detect_time = 0.0
    detections = []
    selected = None
    tick_count = 0

    print(f"[实时模式] 已启动 | 检测频率: {detect_fps}fps | 等待热键激活...")

    try:
        while not hotkey.should_exit:
            if not hotkey.is_active:
                # 空闲状态：不截屏、不检测、不动鼠标
                time.sleep(0.01)
                detections = []
                selected = None
                continue

            # 激活状态：截屏
            frame = capture.read()
            if frame is None:
                continue

            # 按频率决定是否跑 YOLO 检测
            now = time.perf_counter()
            if now - last_detect_time >= detect_interval:
                detections = list(detector.detect(frame.image))
                last_detect_time = now

            # 每帧都跑控制
            command = actuator.process(detections)
            output.apply(command)

            # 可视化回调
            if on_tick is not None:
                tracker = getattr(actuator, "tracker", None)
                selected = getattr(tracker, "locked_target", None) if tracker is not None else None

                result = TickResult(
                    frame=frame,
                    detections=detections,
                    selected=selected,
                    command=command,
                )
                should_continue = on_tick(frame, result)
                if should_continue is False:
                    break

            tick_count += 1

    finally:
        capture.close()
        output.close()
        print(f"\n[实时模式] 已退出 | 总处理帧数: {tick_count}")
