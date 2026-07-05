"""运行时诊断日志 — 格式化输出每帧各层的输入输出数据。"""
from __future__ import annotations

import math
from typing import Optional, Sequence

from visual_aiming_v2.shared.schemas import Command, Detection, Frame


class DiagnosticLogger:
    """可选的诊断日志器，按帧打印各层输入输出。"""

    def __init__(self, total_frames: int = 0, source_name: str = "video") -> None:
        self.total_frames = total_frames  # 总帧数（0 表示未知）
        self.source_name = source_name    # 数据源名称

    def log_frame(
        self,
        *,
        frame: Frame,
        image_shape: tuple,
        detections: Sequence[Detection],
        crosshair: tuple[int, int],
        selected: Optional[Detection],
        selected_index: Optional[int],
        selected_distance: Optional[float],
        command: Command,
        output_name: str,
        pipeline_ms: float,
    ) -> None:
        """格式化并打印一帧的完整诊断信息。"""
        # diagnostics 只观察数据，不反向影响 pipeline 的决策结果。
        lines: list[str] = []

        # 帧头（双线框）
        lines.append("")
        lines.append(self._frame_header(frame.sequence, frame.timestamp, pipeline_ms))

        # capture 层
        lines.append("")
        lines.append("  capture ──────────────────────────────────────────────────────")
        lines.append(f"    INPUT   source={self.source_name}  frame_index={frame.sequence}")
        h, w, c = image_shape
        lines.append(f"    OUTPUT  image={h}×{w}×{c}  sequence={frame.sequence}  timestamp={frame.timestamp:.3f}")
        lines.append("")
        lines.append(f"        ▼ Frame(image={h}×{w}×{c}, sequence={frame.sequence}, timestamp={frame.timestamp:.3f})")

        # perception 层
        lines.append("")
        lines.append("  perception ───────────────────────────────────────────────────")
        lines.append(f"    INPUT   image={h}×{w}×{c}")
        lines.append(f"    OUTPUT  {len(detections)} detections")
        for i, det in enumerate(detections):
            cx, cy = det.center
            lines.append(
                f"            #{i}  label={det.label:<8s} x={det.x:<4d} y={det.y:<4d} "
                f"w={det.w:<4d} h={det.h:<4d} conf={det.confidence:.2f}  center=({cx},{cy})"
            )
        lines.append("")
        lines.append(f"        ▼ [Detection × {len(detections)}]")

        # actuation 层
        lines.append("")
        lines.append("  actuation ────────────────────────────────────────────────────")
        lines.append(f"    INPUT   detections={len(detections)}  crosshair={crosshair}")
        if selected is not None and selected_index is not None:
            sx, sy = selected.center
            dist_str = f"{selected_distance:.1f}px" if selected_distance is not None else "?"
            lines.append(f"    SELECT  #{selected_index} {selected.label}  center=({sx},{sy})  distance={dist_str}")
            dx, dy = command.dx, command.dy
            lines.append(f"    AIM     target=({sx},{sy}) - crosshair={crosshair} = error({dx}, {dy})")
        else:
            lines.append("    SELECT  None（无目标）")
        lines.append(f"    OUTPUT  Command(dx={command.dx}, dy={command.dy}, mode={command.mode}, reason={command.reason})")
        lines.append("")
        lines.append(f"        ▼ Command(dx={command.dx}, dy={command.dy})")

        # output 层
        lines.append("")
        lines.append("  output ───────────────────────────────────────────────────────")
        lines.append(f"    INPUT   Command(dx={command.dx}, dy={command.dy}, mode={command.mode}, reason={command.reason})")
        lines.append(f"    TARGET  {output_name} → 已记录")
        lines.append("")

        print("\n".join(lines))

    def _frame_header(self, sequence: int, timestamp: float, pipeline_ms: float) -> str:
        """生成帧头双线框。"""
        if self.total_frames > 0:
            frame_info = f"Frame #{sequence} / {self.total_frames}"
        else:
            frame_info = f"Frame #{sequence}"
        content = f"  {frame_info}  │  timestamp: {timestamp:.3f}s  │  pipeline: {pipeline_ms:.1f}ms  "
        width = max(len(content) + 2, 65)
        content = content.ljust(width - 2)

        top = "┏" + "━" * (width - 2) + "┓"
        mid = "┃" + content + "┃"
        bot = "┗" + "━" * (width - 2) + "┛"
        return f"{top}\n{mid}\n{bot}"
