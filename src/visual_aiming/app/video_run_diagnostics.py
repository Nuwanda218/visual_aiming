from __future__ import annotations

from pathlib import Path


def build_video_log_path(video_path: str, *, timestamp: str, log_dir: Path = Path("logs")) -> Path:
    log_dir.mkdir(exist_ok=True)
    video_name = Path(video_path).stem
    return log_dir / f"video_test_{video_name}_{timestamp}.jsonl"


def format_summary_lines(summary: dict, *, jsonl_path: Path) -> list[str]:
    return [
        "",
        "=" * 50,
        "[视频测试] 完成 - 诊断摘要:",
        f"  处理帧数: {summary['samples']}",
        f"  空指令帧: {summary['noop_commands']}",
        f"  目标丢失: {summary['target_lost']}",
        f"  目标切换: {summary['target_switches']}",
        f"  平均控制幅度: {summary['avg_command_magnitude']:.2f}",
        f"  最大控制幅度: {summary['max_command_magnitude']:.2f}",
        f"  最大检测延迟: {summary['max_detector_latency_ms']:.1f}ms",
        f"  最大管道延迟: {summary['max_pipeline_latency_ms']:.1f}ms",
        f"  日志路径: {jsonl_path}",
    ]
