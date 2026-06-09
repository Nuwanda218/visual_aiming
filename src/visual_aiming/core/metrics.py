from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from visual_aiming.core.schemas import PipelineTickResult


class JsonlDiagnostics:
    name = "jsonl"

    def __init__(self, jsonl_path: str | Path, summary_path: Optional[str | Path] = None, flush_interval: int = 16) -> None:
        self.jsonl_path = Path(jsonl_path)
        self.summary_path = Path(summary_path) if summary_path is not None else self.jsonl_path.with_suffix(".summary.json")
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.jsonl_path.open("w", encoding="utf-8")
        self._flush_interval = max(1, flush_interval)
        self._writes_since_flush = 0
        self.samples = 0
        self.noop_commands = 0
        self.max_command_magnitude = 0.0
        self.total_command_magnitude = 0.0
        self.target_lost = 0
        self.target_switches = 0
        self.max_detector_latency_ms = 0.0
        self.max_pipeline_latency_ms = 0.0

    def write(self, result: PipelineTickResult) -> None:
        record = _strict_jsonable(self._record(result))
        self._handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        self._writes_since_flush += 1
        if self._writes_since_flush >= self._flush_interval:
            self._handle.flush()
            self._writes_since_flush = 0
        self._accumulate(result)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        try:
            if hasattr(self, "_handle") and self._handle and not self._handle.closed:
                self._handle.close()
        except Exception:
            pass

    def close(self) -> None:
        if self._handle and not self._handle.closed:
            self._handle.close()
        summary = _strict_jsonable(self.summary())
        payload = json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)
        self.summary_path.write_text(payload, encoding="utf-8")

    def summary(self) -> dict:
        avg_command = self.total_command_magnitude / self.samples if self.samples else 0.0
        return {
            "samples": self.samples,
            "noop_commands": self.noop_commands,
            "target_lost": self.target_lost,
            "target_switches": self.target_switches,
            "avg_command_magnitude": avg_command,
            "max_command_magnitude": self.max_command_magnitude,
            "max_detector_latency_ms": self.max_detector_latency_ms,
            "max_pipeline_latency_ms": self.max_pipeline_latency_ms,
        }

    def _record(self, result: PipelineTickResult) -> dict:
        return {
            "sequence": result.sequence,
            "timestamp": result.timestamp,
            "mode": asdict(result.mode),
            "detections": [asdict(detection) for detection in result.detections.detections],
            "selected": asdict(result.selected),
            "aim": asdict(result.aim),
            "predicted": asdict(result.predicted),
            "command": asdict(result.command),
            "output_backend": result.output_backend,
            "detector_latency_ms": result.detections.latency_ms,
            "pipeline_latency_ms": result.pipeline_latency_ms,
            "latency_breakdown": asdict(result.latency_breakdown),
        }

    def _accumulate(self, result: PipelineTickResult) -> None:
        self.samples += 1
        magnitude = math.hypot(result.command.dx, result.command.dy)
        self.total_command_magnitude += magnitude
        self.max_command_magnitude = max(self.max_command_magnitude, magnitude)
        if result.command.is_noop:
            self.noop_commands += 1
        if result.predicted.state == "lost":
            self.target_lost += 1
        if result.selected.switched:
            self.target_switches += 1
        self.max_detector_latency_ms = max(self.max_detector_latency_ms, result.detections.latency_ms)
        self.max_pipeline_latency_ms = max(self.max_pipeline_latency_ms, result.pipeline_latency_ms)


def _strict_jsonable(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _strict_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_strict_jsonable(item) for item in value]
    return value
