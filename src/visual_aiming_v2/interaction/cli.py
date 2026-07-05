"""交互接入层 — CLI 参数解析与组件组装。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V2 视觉瞄准运行时")
    parser.add_argument("--video", default="", help="视频文件路径（视频回放模式）")
    parser.add_argument("--realtime", action="store_true", help="实时截屏模式（热键激活）")
    parser.add_argument("--model", default="models/best.pt", help="YOLO 模型路径")
    parser.add_argument("--output", choices=["null", "log", "mouse"], default="null", help="输出后端（mouse 需确认安全）")
    parser.add_argument("--max-frames", type=int, default=0, help="最多处理帧数，0 表示全部")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    parser.add_argument("--verbose", action="store_true", help="启用逐帧诊断日志输出")
    parser.add_argument("--visual", action="store_true", help="启用 OpenCV 可视化调试窗口")
    parser.add_argument("--tune", choices=["capture"], default="", help="进入调参模式（目前支持 capture）")
    return parser.parse_args(argv)


def load_config_file(path: str) -> dict:
    """读取 config.json，不存在则返回空字典。"""
    config_path = Path(path)
    if not config_path.exists():
        return {}
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _build_config(args) -> "Config":
    """合并配置：命令行参数 > config.json 默认值。"""
    from visual_aiming_v2.shared.config import Config

    file_config = load_config_file(args.config)
    return Config(
        model_path=args.model or file_config.get("model_path", "models/best.pt"),
        confidence=float(file_config.get("confidence", 0.5)),
        iou=float(file_config.get("iou", 0.45)),
        device=str(file_config.get("device", "auto")),
        image_width=int(file_config.get("image_width", 410)),
        image_height=int(file_config.get("image_height", 315)),
        crosshair_offset_x=int(file_config.get("crosshair_offset_x", 0)),
        crosshair_offset_y=int(file_config.get("crosshair_offset_y", 0)),
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # 调参模式
    if args.tune == "capture":
        if not args.video:
            print("[错误] --tune capture 需要 --video 参数")
            return 1
        from visual_aiming_v2.interaction.tuner import CaptureTuner
        CaptureTuner(args.video, config_path=args.config).run()
        return 0

    # 实时模式
    if args.realtime:
        return _run_realtime(args)

    # 视频回放模式
    if args.video:
        return _run_video(args)

    print("[错误] 需要 --video 或 --realtime 参数")
    return 1


def _run_realtime(args) -> int:
    """实时截屏模式：热键激活，截屏→检测→控制→鼠标输出。"""
    from visual_aiming_v2.actuation.outputs import LogOutput, NullOutput, WinMouseOutput
    from visual_aiming_v2.actuation.targeting import Actuator
    from visual_aiming_v2.capture.sources import ScreenCapture
    from visual_aiming_v2.interaction.hotkey import HotkeyListener
    from visual_aiming_v2.perception.detectors import YoloDetector
    from visual_aiming_v2.runtime.realtime import run_realtime

    config = _build_config(args)

    capture = ScreenCapture(config)
    detector = YoloDetector(config)
    # 实时模式默认启用 FPS 控制器
    actuator = Actuator(config, use_controller=True)

    # 输出后端
    if args.output == "mouse":
        output = WinMouseOutput(enable=True)
    elif args.output == "log":
        output = LogOutput()
    else:
        output = NullOutput()

    # 热键监听
    hotkey = HotkeyListener()
    hotkey.start()

    # 可视化窗口（--visual 开启）
    on_tick = None
    if args.visual:
        from visual_aiming_v2.interaction.visualizer import Visualizer
        vis = Visualizer(crosshair=actuator.crosshair, total_frames=0)
        on_tick = lambda frame, result: vis.update(frame.image, result)

    try:
        run_realtime(
            capture=capture,
            detector=detector,
            actuator=actuator,
            output=output,
            hotkey=hotkey,
            on_tick=on_tick,
        )
    finally:
        hotkey.stop()

    return 0


def _run_video(args) -> int:
    """视频回放模式：逐帧处理视频文件。"""
    from visual_aiming_v2.actuation.outputs import LogOutput, NullOutput, WinMouseOutput
    from visual_aiming_v2.actuation.targeting import Actuator
    from visual_aiming_v2.capture.sources import VideoFileCapture
    from visual_aiming_v2.perception.detectors import YoloDetector
    from visual_aiming_v2.runtime.runner import run

    config = _build_config(args)

    capture = VideoFileCapture(args.video, config)
    detector = YoloDetector(config)
    use_mouse = args.output == "mouse"
    actuator = Actuator(config, use_controller=use_mouse)

    if use_mouse:
        output = WinMouseOutput(enable=True)
    elif args.output == "log":
        output = LogOutput()
    else:
        output = NullOutput()
    max_frames = args.max_frames if args.max_frames > 0 else None

    # 诊断日志
    diagnostics = None
    if args.verbose:
        from visual_aiming_v2.runtime.diagnostics import DiagnosticLogger
        diagnostics = DiagnosticLogger(total_frames=capture.total_frames, source_name="video")

    # 可视化窗口
    on_tick = None
    if args.visual:
        from visual_aiming_v2.interaction.visualizer import Visualizer
        vis = Visualizer(crosshair=actuator.crosshair, total_frames=capture.total_frames)
        on_tick = lambda frame, result: vis.update(frame.image, result)

    results = run(
        capture=capture,
        detector=detector,
        actuator=actuator,
        output=output,
        max_frames=max_frames,
        diagnostics=diagnostics,
        on_tick=on_tick,
    )
    print(f"\n[V2] 处理完成: {len(results)} 帧")
    return 0
