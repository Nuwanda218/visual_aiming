from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from visual_aiming.app.log_analyzer import analyze_jsonl, format_report


@dataclass
class EvaluationResult:
    report: dict
    failures: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures


def evaluate_file(
    path: str | Path,
    min_visible_detection_rate: float | None = None,
    max_empty_false_positive_rate: float | None = None,
    max_target_switches: int | None = None,
) -> EvaluationResult:
    report = analyze_jsonl(path)
    failures: list[str] = []
    quality = report.get("annotation_quality") or {}

    if min_visible_detection_rate is not None:
        value = float(quality.get("visible_target_detection_rate_pct", 0.0))
        if value < min_visible_detection_rate:
            failures.append(f"visible_target_detection_rate_pct {value:.1f} < {min_visible_detection_rate:.1f}")

    if max_empty_false_positive_rate is not None:
        value = float(quality.get("empty_scene_false_positive_rate_pct", 0.0))
        if value > max_empty_false_positive_rate:
            failures.append(f"empty_scene_false_positive_rate_pct {value:.1f} > {max_empty_false_positive_rate:.1f}")

    if max_target_switches is not None:
        value = int(report.get("target_switches", 0))
        if value > max_target_switches:
            failures.append(f"target_switches {value} > {max_target_switches}")

    return EvaluationResult(report=report, failures=failures)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate a diagnostics JSONL file against simple thresholds")
    parser.add_argument("path")
    parser.add_argument("--min-visible-detection-rate", type=float)
    parser.add_argument("--max-empty-false-positive-rate", type=float)
    parser.add_argument("--max-target-switches", type=int)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    result = evaluate_file(
        args.path,
        min_visible_detection_rate=args.min_visible_detection_rate,
        max_empty_false_positive_rate=args.max_empty_false_positive_rate,
        max_target_switches=args.max_target_switches,
    )
    print(format_report(result.report))
    if result.failures:
        print("阈值失败:")
        for failure in result.failures:
            print(f"- {failure}")
        return 1
    print("阈值通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
