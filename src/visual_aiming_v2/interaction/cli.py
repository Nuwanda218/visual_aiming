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
    return parser.parse_args(argv)


def load_config_file(path: str) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    from visual_aiming_v2.actuation.outputs import LogOutput, NullOutput
    from visual_aiming_v2.actuation.targeting import Actuator
    from visual_aiming_v2.capture.sources import VideoFileCapture
    from visual_aiming_v2.perception.detectors import YoloDetector
    from visual_aiming_v2.runtime.runner import run
    from visual_aiming_v2.shared.config import Config

    file_config = load_config_file(args.config)
    config = Config(
        model_path=args.model or file_config.get("model_path", "models/best.pt"),
        confidence=float(file_config.get("confidence", 0.5)),
        iou=float(file_config.get("iou", 0.45)),
        device=str(file_config.get("device", "auto")),
        image_width=int(file_config.get("image_width", 410)),
        image_height=int(file_config.get("image_height", 315)),
    )

    capture = VideoFileCapture(args.video)
    detector = YoloDetector(config)
    actuator = Actuator(config)
    output = LogOutput() if args.output == "log" else NullOutput()
    max_frames = args.max_frames if args.max_frames > 0 else None

    results = run(capture=capture, detector=detector, actuator=actuator, output=output, max_frames=max_frames)
    print(f"[V2] 处理完成: {len(results)} 帧")
    return 0
