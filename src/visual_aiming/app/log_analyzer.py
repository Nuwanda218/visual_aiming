from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable, Optional


def analyze_jsonl(path: str | Path) -> dict:
    rows = list(_read_records(Path(path)))
    samples = len(rows)
    detection_frames = sum(1 for row in rows if row.get("detections"))
    target_lost = sum(1 for row in rows if _nested(row, "predicted", "state") == "lost")
    relative_commands = sum(1 for row in rows if _nested(row, "command", "mode") == "relative")
    nonzero_commands = sum(1 for row in rows if _has_nonzero_command(row))
    target_switches = sum(1 for row in rows if bool(_nested(row, "selected", "switched")))

    breakdown = {
        "detect": _numbers(rows, ("latency_breakdown", "detect_ms")),
        "select": _numbers(rows, ("latency_breakdown", "select_ms")),
        "aim": _numbers(rows, ("latency_breakdown", "aim_ms")),
        "predict": _numbers(rows, ("latency_breakdown", "predict_ms")),
        "control": _numbers(rows, ("latency_breakdown", "control_ms")),
    }
    bottleneck = _dominant_stage(breakdown)
    detector_stats = _stats(_numbers(rows, ("detector_latency_ms",)))
    display_fps_stats = _stats(_numbers(rows, ("telemetry", "display_fps")))
    frame_work_stats = _stats(_numbers(rows, ("telemetry", "frame_work_ms")))
    wait_stats = _stats(_numbers(rows, ("telemetry", "wait_ms")))
    selected_center_jump_events = _selected_center_jump_events(rows)
    selected_center_jump_stats = _stats([event["distance_px"] for event in selected_center_jump_events])
    command_magnitudes = _command_magnitudes(rows)
    nonzero_command_magnitudes = [value for value in command_magnitudes if value != 0.0]
    insight_codes = _insight_codes(bottleneck, detector_stats, wait_stats)
    detection_output_rate_pct = _rate(detection_frames, samples)

    return {
        "path": str(Path(path)),
        "samples": samples,
        "detection_output_rate_pct": detection_output_rate_pct,
        "detection_rate_pct": detection_output_rate_pct,
        "target_lost_rate_pct": _rate(target_lost, samples),
        "relative_command_rate_pct": _rate(relative_commands, samples),
        "nonzero_command_rate_pct": _rate(nonzero_commands, samples),
        "target_switches": target_switches,
        "continuity": _continuity(rows),
        "problem_segments": _problem_segments(rows),
        "annotation_quality": _annotation_quality(rows),
        "predicted_state_counts": _counts(rows, ("predicted", "state")),
        "selected_reason_counts": _counts(rows, ("selected", "reason")),
        "command_reason_counts": _counts(rows, ("command", "reason")),
        "detector_latency_ms": detector_stats,
        "pipeline_latency_ms": _stats(_numbers(rows, ("pipeline_latency_ms",))),
        "selected_center_jump_px": selected_center_jump_stats,
        "largest_selected_center_jump": _largest_jump(selected_center_jump_events),
        "command_magnitude_px": _stats(command_magnitudes),
        "nonzero_command_magnitude_px": _stats(nonzero_command_magnitudes),
        "display_fps": display_fps_stats,
        "frame_work_ms": frame_work_stats,
        "wait_ms": wait_stats,
        "latency_breakdown_ms": {name: _stats(values) for name, values in breakdown.items()},
        "bottleneck": bottleneck,
        "insight_codes": insight_codes,
    }


def format_report(report: dict) -> str:
    detector = report["detector_latency_ms"] or {}
    display_fps = report["display_fps"] or {}
    frame_work = report["frame_work_ms"] or {}
    wait = report["wait_ms"] or {}
    detection_output_rate_pct = report.get("detection_output_rate_pct")
    if detection_output_rate_pct is None:
        detection_output_rate_pct = report["detection_rate_pct"]
    lines = [
        f"日志: {report['path']}",
        f"样本数: {report['samples']}",
        f"检测输出率: {detection_output_rate_pct:.1f}%",
        f"目标丢失率: {report['target_lost_rate_pct']:.1f}%",
        f"目标切换: {report['target_switches']}",
        f"相对指令率: {report['relative_command_rate_pct']:.1f}%",
        f"非零指令率: {report['nonzero_command_rate_pct']:.1f}%",
        f"指令幅度: {_format_jump_stats(report.get('command_magnitude_px'))}",
        f"非零指令幅度: {_format_jump_stats(report.get('nonzero_command_magnitude_px'))}",
        _format_continuity(report.get("continuity") or {}),
        f"异常段: {_format_problem_segments(report.get('problem_segments') or {})}",
        f"预测状态: {_format_counts(report.get('predicted_state_counts') or {})}",
        f"选择原因: {_format_counts(report.get('selected_reason_counts') or {})}",
        f"命令原因: {_format_counts(report.get('command_reason_counts') or {})}",
        f"目标中心跳变: {_format_jump_stats(report.get('selected_center_jump_px'))}",
        f"最大目标跳变: {_format_largest_jump(report.get('largest_selected_center_jump'))}",
        f"检测延迟: p50={_fmt(detector.get('p50'))}ms p95={_fmt(detector.get('p95'))}ms p99={_fmt(detector.get('p99'))}ms",
        f"显示 FPS: avg={_fmt(display_fps.get('avg'))} p50={_fmt(display_fps.get('p50'))}",
        f"帧处理耗时: p50={_fmt(frame_work.get('p50'))}ms p95={_fmt(frame_work.get('p95'))}ms",
        f"等待时间: p50={_fmt(wait.get('p50'))}ms p95={_fmt(wait.get('p95'))}ms",
        f"主要瓶颈: {report['bottleneck']}",
        f"结论: {', '.join(report['insight_codes']) or 'none'}",
    ]
    annotation_lines = _format_annotation_quality(report.get("annotation_quality"))
    if annotation_lines:
        lines[3:3] = annotation_lines
    return "\n".join(lines)


def _read_records(path: Path) -> Iterable[dict]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line, parse_constant=reject_constant)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc


def _nested(row: dict, *keys: str):
    value = row
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _numbers(rows: list[dict], path: tuple[str, ...]) -> list[float]:
    values = []
    for row in rows:
        value = _nested(row, *path)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            values.append(float(value))
    return values


def _counts(rows: list[dict], path: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = _nested(row, *path)
        if value is None:
            continue
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _continuity(rows: list[dict]) -> dict[str, int]:
    return {
        "max_tracking_streak": _max_streak(rows, lambda row: _nested(row, "predicted", "state") == "tracking"),
        "max_lost_streak": _max_streak(rows, lambda row: _nested(row, "predicted", "state") == "lost"),
        "max_detection_streak": _max_streak(rows, lambda row: bool(row.get("detections"))),
        "max_no_detection_streak": _max_streak(rows, lambda row: not bool(row.get("detections"))),
        "max_relative_command_streak": _max_streak(rows, lambda row: _nested(row, "command", "mode") == "relative"),
        "max_nonzero_command_streak": _max_streak(rows, _has_nonzero_command),
    }


def _problem_segments(rows: list[dict]) -> dict[str, dict[str, int | None]]:
    return {
        "longest_no_detection": _longest_segment(rows, lambda row: not bool(row.get("detections"))),
        "longest_lost": _longest_segment(rows, lambda row: _nested(row, "predicted", "state") == "lost"),
        "longest_zero_command": _longest_segment(rows, lambda row: not _has_nonzero_command(row)),
    }


def _longest_segment(rows: list[dict], predicate) -> dict[str, int | None]:
    best_length = 0
    best_start_index: int | None = None
    best_end_index: int | None = None
    current_start_index: int | None = None
    current_length = 0

    for index, row in enumerate(rows):
        if predicate(row):
            if current_start_index is None:
                current_start_index = index
            current_length += 1
            if current_length > best_length:
                best_length = current_length
                best_start_index = current_start_index
                best_end_index = index
        else:
            current_start_index = None
            current_length = 0

    return {
        "length": best_length,
        "start_sequence": _row_sequence(rows, best_start_index),
        "end_sequence": _row_sequence(rows, best_end_index),
    }


def _row_sequence(rows: list[dict], index: int | None) -> int | None:
    if index is None or index < 0 or index >= len(rows):
        return None
    value = rows[index].get("sequence")
    return int(value) if isinstance(value, int) else index


def _max_streak(rows: list[dict], predicate) -> int:
    longest = 0
    current = 0
    for row in rows:
        if predicate(row):
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _annotation_quality(rows: list[dict]) -> Optional[dict]:
    target_visible_frames = 0
    target_detected_frames = 0
    empty_scene_frames = 0
    false_positive_frames = 0

    for row in rows:
        visible = _target_visibility(row)
        if visible is None:
            continue
        has_detection = bool(row.get("detections"))
        if visible:
            target_visible_frames += 1
            if has_detection:
                target_detected_frames += 1
        else:
            empty_scene_frames += 1
            if has_detection:
                false_positive_frames += 1

    if target_visible_frames == 0 and empty_scene_frames == 0:
        return None
    return {
        "target_visible_frames": target_visible_frames,
        "empty_scene_frames": empty_scene_frames,
        "visible_target_detection_rate_pct": _rate(target_detected_frames, target_visible_frames),
        "empty_scene_false_positive_rate_pct": _rate(false_positive_frames, empty_scene_frames),
    }


def _target_visibility(row: dict) -> Optional[bool]:
    for path in (
        ("target_visible",),
        ("enemy_visible",),
        ("annotations", "target_visible"),
        ("annotations", "enemy_visible"),
    ):
        value = _nested(row, *path)
        if isinstance(value, bool):
            return value
    return None


def _has_nonzero_command(row: dict) -> bool:
    dx = _nested(row, "command", "dx")
    dy = _nested(row, "command", "dy")
    return _is_nonzero_number(dx) or _is_nonzero_number(dy)


def _is_nonzero_number(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) != 0.0


def _selected_center_jumps(rows: list[dict]) -> list[float]:
    return [event["distance_px"] for event in _selected_center_jump_events(rows)]


def _command_magnitudes(rows: list[dict]) -> list[float]:
    magnitudes = []
    for row in rows:
        dx = _nested(row, "command", "dx")
        dy = _nested(row, "command", "dy")
        if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in (dx, dy)):
            continue
        magnitudes.append(round(math.hypot(float(dx), float(dy)), 2))
    return magnitudes


def _selected_center_jump_events(rows: list[dict]) -> list[dict[str, float | int | None]]:
    jumps = []
    previous = None
    previous_sequence = None
    for row in rows:
        center = _selected_center(row)
        if center is None:
            continue
        if previous is not None:
            jumps.append({
                "distance_px": round(math.hypot(center[0] - previous[0], center[1] - previous[1]), 2),
                "from_sequence": previous_sequence,
                "to_sequence": _row_sequence([row], 0),
            })
        previous = center
        previous_sequence = _row_sequence([row], 0)
    return jumps


def _largest_jump(events: list[dict[str, float | int | None]]) -> Optional[dict]:
    if not events:
        return None
    return max(events, key=lambda event: float(event["distance_px"]))


def _selected_center(row: dict) -> tuple[float, float] | None:
    bbox = _nested(row, "selected", "detection", "bbox")
    if not isinstance(bbox, list) or len(bbox) < 4:
        return None
    x, y, width, height = bbox[:4]
    if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in (x, y, width, height)):
        return None
    return (float(x) + float(width) / 2.0, float(y) + float(height) / 2.0)


def _stats(values: list[float]) -> Optional[dict]:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "min": round(ordered[0], 2),
        "p50": round(_nearest_rank(ordered, 0.50), 2),
        "p90": round(_nearest_rank(ordered, 0.90), 2),
        "p95": round(_nearest_rank(ordered, 0.95), 2),
        "p99": round(_nearest_rank(ordered, 0.99), 2),
        "max": round(ordered[-1], 2),
        "avg": round(sum(ordered) / len(ordered), 2),
    }


def _nearest_rank(values: list[float], quantile: float) -> float:
    index = max(0, min(len(values) - 1, math.ceil(quantile * len(values)) - 1))
    return values[index]


def _rate(count: int, total: int) -> float:
    return round((count / total) * 100.0, 1) if total else 0.0


def _dominant_stage(breakdown: dict[str, list[float]]) -> str:
    averages = {
        name: sum(values) / len(values)
        for name, values in breakdown.items()
        if values
    }
    if not averages:
        return "unknown"
    return max(averages, key=averages.get)


def _insight_codes(bottleneck: str, detector: Optional[dict], wait: Optional[dict]) -> list[str]:
    insights = []
    if wait and wait.get("p95", 0.0) <= 1.5:
        insights.append("wait_not_bottleneck")
    if bottleneck == "detect":
        insights.append("detector_bottleneck")
    if detector and detector.get("p95", 0.0) > 0:
        if detector.get("max", 0.0) >= max(detector["p95"] * 3.0, detector["p95"] + 100.0):
            insights.append("latency_spike")
    return insights


def _fmt(value) -> str:
    return "n/a" if value is None else f"{float(value):.2f}"


def _format_continuity(continuity: dict) -> str:
    return (
        f"最长追踪段: {continuity.get('max_tracking_streak', 0)} | "
        f"最长丢失段: {continuity.get('max_lost_streak', 0)} | "
        f"最长无检测段: {continuity.get('max_no_detection_streak', 0)}"
    )


def _format_problem_segments(segments: dict) -> str:
    return ", ".join((
        f"无检测={_format_segment(segments.get('longest_no_detection') or {})}",
        f"丢失={_format_segment(segments.get('longest_lost') or {})}",
        f"零指令={_format_segment(segments.get('longest_zero_command') or {})}",
    ))


def _format_segment(segment: dict) -> str:
    length = segment.get("length", 0)
    start = segment.get("start_sequence")
    end = segment.get("end_sequence")
    if length <= 0 or start is None or end is None:
        return "0"
    return f"{length}(seq {start}-{end})"


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{key}={value}" for key, value in items)


def _format_annotation_quality(quality: Optional[dict]) -> list[str]:
    if not quality:
        return []
    return [
        (
            "可见目标检出率: "
            f"{quality['visible_target_detection_rate_pct']:.1f}% "
            f"({quality['target_visible_frames']} frames)"
        ),
        (
            "空场景误检率: "
            f"{quality['empty_scene_false_positive_rate_pct']:.1f}% "
            f"({quality['empty_scene_frames']} frames)"
        ),
    ]


def _format_jump_stats(stats: Optional[dict]) -> str:
    if not stats:
        return "n/a"
    return f"p50={_fmt(stats.get('p50'))}px p95={_fmt(stats.get('p95'))}px max={_fmt(stats.get('max'))}px"


def _format_largest_jump(event: Optional[dict]) -> str:
    if not event:
        return "n/a"
    return f"{_fmt(event.get('distance_px'))}px (seq {event.get('from_sequence')}->{event.get('to_sequence')})"
