"""交互接入层 — CLI 参数解析与组件组装。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V2 视觉瞄准运行时")
    parser.add_argument("--video", required=True, help="视频文件路径")
    parser.add_argument("--model", default="models/best.pt", help="YOLO 模型路径")
    parser.add_argument("--output", choices=["null", "log"], default="null", help="输出后端")
    parser.add_argument("--max-frames", type=int, default=0, help="最多处理帧数，0 表示全部")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    parser.add_argument("--verbose", action="store_true", help="启用逐帧诊断日志输出")
    return parser.parse_args(argv)


def load_config_file(path: str) -> dict:
    """读取 config.json，不存在则返回空字典。"""
    config_path = Path(path)
    if not config_path.exists():
        return {}
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # 真实运行依赖在 main 内部导入，避免 parse_args/load_config_file 的测试加载重依赖。
    from visual_aiming_v2.actuation.outputs import LogOutput, NullOutput
    from visual_aiming_v2.actuation.targeting import Actuator
    from visual_aiming_v2.capture.sources import VideoFileCapture
    from visual_aiming_v2.perception.detectors import YoloDetector
    from visual_aiming_v2.runtime.runner import run
    from visual_aiming_v2.shared.config import Config

    # 合并配置：命令行参数 > config.json 默认值
    file_config = load_config_file(args.config)
    config = Config(
        model_path=args.model or file_config.get("model_path", "models/best.pt"),
        confidence=float(file_config.get("confidence", 0.5)),
        iou=float(file_config.get("iou", 0.45)),
        device=str(file_config.get("device", "auto")),
        image_width=int(file_config.get("image_width", 410)),
        image_height=int(file_config.get("image_height", 315)),
    )

    # 组装各层组件
    capture = VideoFileCapture(args.video)
    detector = YoloDetector(config)
    actuator = Actuator(config)
    # 初始阶段只允许 null/log 两种安全输出，真实鼠标输出应在后续任务显式加入。
    output = LogOutput() if args.output == "log" else NullOutput()
    max_frames = args.max_frames if args.max_frames > 0 else None

    # 诊断日志（--verbose 开启）
    diagnostics = None
    if args.verbose:
        from visual_aiming_v2.runtime.diagnostics import DiagnosticLogger
        import cv2
        # 获取视频总帧数用于显示进度
        cap = cv2.VideoCapture(args.video)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        diagnostics = DiagnosticLogger(total_frames=total, source_name="video")

    # 启动运行
    results = run(
        capture=capture,
        detector=detector,
        actuator=actuator,
        output=output,
        max_frames=max_frames,
        diagnostics=diagnostics,
    )
    print(f"\n[V2] 处理完成: {len(results)} 帧")
    return 0
