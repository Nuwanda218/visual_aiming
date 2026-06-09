from __future__ import annotations

from typing import Optional

from visual_aiming.core.schemas import PipelineTickResult


def build_osd_lines(
    *,
    sequence: int,
    total_frames: int,
    active: bool,
    result: Optional[PipelineTickResult],
    frame_work_ms: float,
    wait_ms: int,
    display_fps: float,
) -> list[str]:
    if result is None:
        return [
            f"Frame: {sequence}/{total_frames}",
            f"Status: {'ACTIVE' if active else 'PAUSED'}",
            "Press Space to start",
        ]

    command = result.command
    return [
        f"Frame: {sequence}/{total_frames}",
        f"Status: {'ACTIVE' if active else 'PAUSED'}",
        f"Detections: {len(result.detections.detections)}",
        f"Det latency: {result.detections.latency_ms:.1f}ms",
        f"Pipeline: {result.pipeline_latency_ms:.1f}ms",
        f"Frame work: {frame_work_ms:.1f}ms | Wait: {wait_ms}ms",
        f"FPS: {display_fps:.1f}",
        f"Command: dx={command.dx} dy={command.dy} ({command.reason})",
    ]
