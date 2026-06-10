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
    insight_codes = _insight_codes(bottleneck, detector_stats, wait_stats)

    return {
        "path": str(Path(path)),
        "samples": samples,
        "detection_rate_pct": _rate(detection_frames, samples),
        "target_lost_rate_pct": _rate(target_lost, samples),
        "relative_command_rate_pct": _rate(relative_commands, samples),
        "target_switches": target_switches,
        "predicted_state_counts": _counts(rows, ("predicted", "state")),
        "selected_reason_counts": _counts(rows, ("selected", "reason")),
        "command_reason_counts": _counts(rows, ("command", "reason")),
        "detector_latency_ms": detector_stats,
        "pipeline_latency_ms": _stats(_numbers(rows, ("pipeline_latency_ms",))),
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
    lines = [
        f"日志: {report['path']}",
        f"样本数: {report['samples']}",
        f"检测命中率: {report['detection_rate_pct']:.1f}%",
        f"目标丢失率: {report['target_lost_rate_pct']:.1f}%",
        f"目标切换: {report['target_switches']}",
        f"相对指令率: {report['relative_command_rate_pct']:.1f}%",
        f"检测延迟: p50={_fmt(detector.get('p50'))}ms p95={_fmt(detector.get('p95'))}ms p99={_fmt(detector.get('p99'))}ms",
        f"显示 FPS: avg={_fmt(display_fps.get('avg'))} p50={_fmt(display_fps.get('p50'))}",
        f"帧处理耗时: p50={_fmt(frame_work.get('p50'))}ms p95={_fmt(frame_work.get('p95'))}ms",
        f"等待时间: p50={_fmt(wait.get('p50'))}ms p95={_fmt(wait.get('p95'))}ms",
        f"主要瓶颈: {report['bottleneck']}",
        f"结论: {', '.join(report['insight_codes']) or 'none'}",
    ]
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
