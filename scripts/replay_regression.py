from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.evaluate_diagnostics import EvaluationResult, evaluate_file
from visual_aiming.app.replay import run_video_file
from visual_aiming.config.loader import load_modular_config


@dataclass(frozen=True)
class ReplayCase:
    name: str
    video: Path
    min_visible_detection_rate: float | None = None
    max_empty_false_positive_rate: float | None = None
    max_target_switches: int | None = None


def load_manifest(path: str | Path) -> list[ReplayCase]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = []
    for item in data.get("cases", []):
        cases.append(ReplayCase(
            name=str(item["name"]),
            video=Path(item["video"]),
            min_visible_detection_rate=item.get("min_visible_detection_rate"),
            max_empty_false_positive_rate=item.get("max_empty_false_positive_rate"),
            max_target_switches=item.get("max_target_switches"),
        ))
    return cases


def replay_video_to_log(video: Path, diagnostics_path: Path) -> None:
    config = load_modular_config("config.json")
    config.output.backend = "null"
    config.output.enable_real_mouse = False
    config.diagnostics.enabled = True
    config.diagnostics.jsonl_path = str(diagnostics_path)
    run_video_file(config, str(video))


def run_case(
    case: ReplayCase,
    output_dir: Path,
    replay=replay_video_to_log,
    evaluate=evaluate_file,
) -> EvaluationResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_path = output_dir / f"{case.name}.jsonl"
    replay(case.video, diagnostics_path)
    return evaluate(
        diagnostics_path,
        min_visible_detection_rate=case.min_visible_detection_rate,
        max_empty_false_positive_rate=case.max_empty_false_positive_rate,
        max_target_switches=case.max_target_switches,
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run a video replay regression manifest")
    parser.add_argument("manifest")
    parser.add_argument("--output-dir", default="logs/replay_regression")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    cases = load_manifest(args.manifest)
    output_dir = Path(args.output_dir)
    failed = 0
    for case in cases:
        result = run_case(case, output_dir)
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {case.name}")
        for failure in result.failures:
            print(f"- {failure}")
        if not result.passed:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
