# Algorithm Debug Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the whole pipeline before real mouse control by making replay diagnostics repeatable, target selection less jumpy, short target loss less destructive, and tuning/debug output easier to interpret.

**Architecture:** Keep one runtime path: `FrameSource -> RuntimeRunner -> ModularPipeline -> OutputBackend`. This plan only changes pipeline-side behavior and diagnostics before actual Windows mouse output. Mouse angular mapping remains deferred to `docs/superpowers/plans/2026-06-13-mouse-angular-control.md`.

**Tech Stack:** Python `unittest`, existing `ModularPipeline`, `log_analyzer`, JSONL diagnostics, current config schema, existing video replay and video-test apps.

---

## Scope

This phase improves the part of the project that can be verified without moving the real mouse:

```text
video/screen frame -> detector -> target selector -> aim point -> predictor -> relative command -> diagnostics
```

It deliberately does not implement:

- game angular mouse mapping
- per-game sensitivity profiles
- TensorRT / ONNX acceleration
- multi-detector abstraction work
- C++/Rust/Go rewrite

Those belong to later phases after the Python algorithm behavior is measurable.

## Current Context

Relevant current files:

- `src/visual_aiming/core/runtime_runner.py` - single runtime loop.
- `src/visual_aiming/core/pipeline.py` - modular aiming pipeline.
- `src/visual_aiming/algorithms/target_selection.py` - target choice and sticky target behavior.
- `src/visual_aiming/algorithms/prediction.py` - short-term prediction and lost state.
- `src/visual_aiming/algorithms/control.py` - relative command generation.
- `src/visual_aiming/app/log_analyzer.py` - JSONL diagnostics analyzer.
- `src/visual_aiming/app/video_test.py` - interactive video debug runner.
- `src/visual_aiming/app/replay.py` - video replay runner.
- `src/visual_aiming/config/schema.py` - modular grouped config.
- `src/visual_aiming/actions/config_window.py` - human-facing tuning controls.
- `tests/test_modular_pipeline.py` - pipeline behavior tests.
- `tests/test_modular_algorithms.py` - algorithm unit tests.
- `tests/test_modular_apps.py` - diagnostics and app tests.

## Success Criteria

- Diagnostic reports distinguish detection output rate from annotated visible-target detection quality.
- Replay logs produce stable summary metrics and optional threshold failures.
- Target selection switches less often when two candidates have similar scores.
- Short gaps in detection produce a deliberate held/predicted state instead of immediate destructive loss.
- Parameter UI exposes a small common set first and keeps advanced settings available.
- Every behavior change has a failing test first and a focused verification command.
- `config.json` remains local-only and is not required for test success.

---

## Task 1: Diagnostics Evaluation Command

**Files:**
- Create: `scripts/evaluate_diagnostics.py`
- Modify: `tests/test_modular_apps.py`
- Modify: `docs/debug-workflow.md`

- [x] **Step 1: Write failing tests for threshold evaluation**

Add this test class to `tests/test_modular_apps.py` near the log analyzer tests:

```python
class DiagnosticsEvaluationCliTest(unittest.TestCase):
    def test_evaluate_diagnostics_returns_zero_when_thresholds_pass(self):
        from scripts.evaluate_diagnostics import evaluate_file

        rows = [
            {"target_visible": True, "detections": [{"class_id": 0}], "predicted": {"state": "tracking"}, "command": {"mode": "relative", "dx": 2, "dy": 0}},
            {"target_visible": True, "detections": [{"class_id": 0}], "predicted": {"state": "tracking"}, "command": {"mode": "relative", "dx": 1, "dy": 1}},
            {"target_visible": False, "detections": [], "predicted": {"state": "lost"}, "command": {"mode": "none", "dx": 0, "dy": 0}},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            result = evaluate_file(
                path,
                min_visible_detection_rate=90.0,
                max_empty_false_positive_rate=1.0,
                max_target_switches=0,
            )

        self.assertTrue(result.passed)
        self.assertEqual(result.failures, [])

    def test_evaluate_diagnostics_reports_threshold_failures(self):
        from scripts.evaluate_diagnostics import evaluate_file

        rows = [
            {"target_visible": True, "detections": [], "selected": {"switched": True}, "predicted": {"state": "lost"}, "command": {"mode": "none"}},
            {"target_visible": False, "detections": [{"class_id": 0}], "selected": {"switched": True}, "predicted": {"state": "tracking"}, "command": {"mode": "relative", "dx": 3, "dy": 0}},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            result = evaluate_file(
                path,
                min_visible_detection_rate=90.0,
                max_empty_false_positive_rate=1.0,
                max_target_switches=0,
            )

        self.assertFalse(result.passed)
        self.assertIn("visible_target_detection_rate_pct 0.0 < 90.0", result.failures)
        self.assertIn("empty_scene_false_positive_rate_pct 100.0 > 1.0", result.failures)
        self.assertIn("target_switches 2 > 0", result.failures)
```

- [x] **Step 2: Run tests to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_apps.DiagnosticsEvaluationCliTest -v
```

Expected: fail because `scripts.evaluate_diagnostics` does not exist.

- [x] **Step 3: Implement the evaluator**

Create `scripts/evaluate_diagnostics.py`:

```python
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
```

- [x] **Step 4: Verify evaluator tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_apps.DiagnosticsEvaluationCliTest -v
```

Expected: 2 tests pass.

- [x] **Step 5: Document usage**

Add to `docs/debug-workflow.md`:

```markdown
### Evaluate a diagnostics run

```powershell
.venv\Scripts\python.exe scripts\evaluate_diagnostics.py logs\run.jsonl --min-visible-detection-rate 85 --max-empty-false-positive-rate 5 --max-target-switches 10
```

Use this only for annotated logs. Unannotated logs still show output rate and continuity, but cannot prove detection accuracy.
```

- [x] **Step 6: Verify task**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_apps.DiagnosticsEvaluationCliTest -v
.venv\Scripts\python.exe -m compileall -q scripts tests src main.py
git diff --check
```

- [x] **Step 7: Commit**

```powershell
git add scripts/evaluate_diagnostics.py tests/test_modular_apps.py docs/debug-workflow.md
git commit -m "添加诊断阈值评估工具"
```

Explain to user:

```text
Task 1 完成：现在可以把视频测试日志作为评估对象，带阈值判断可见目标检出率、空场景误检率和目标切换次数。它不再把普通检测输出率误叫成命中率。
```

---

## Task 2: Target Selection Stability

**Files:**
- Modify: `src/visual_aiming/config/schema.py`
- Modify: `src/visual_aiming/algorithms/target_selection.py`
- Modify: `tests/test_modular_algorithms.py`

- [x] **Step 1: Write failing tests for stronger hysteresis**

Add to `TargetSelectorTest` in `tests/test_modular_algorithms.py`:

```python
def test_switch_requires_meaningful_score_improvement(self):
    from visual_aiming.algorithms.target_selection import TargetSelector
    from visual_aiming.config.schema import TargetSelectionConfig
    from visual_aiming.core.schemas import Detection

    config = TargetSelectionConfig()
    config.sticky_enabled = True
    config.sticky_switch_margin = 0.35
    selector = TargetSelector(config)

    first = Detection((40, 40, 20, 20), confidence=0.90, class_id=0, class_name="head")
    close_competitor = Detection((45, 40, 20, 20), confidence=0.91, class_id=0, class_name="head")

    selected = selector.select([first], roi_center=(50, 50))
    next_selected = selector.select([close_competitor, first], roi_center=(50, 50))

    self.assertEqual(selected.detection.bbox, first.bbox)
    self.assertEqual(next_selected.detection.bbox, first.bbox)
    self.assertFalse(next_selected.switched)


def test_switches_when_new_target_is_clearly_better(self):
    from visual_aiming.algorithms.target_selection import TargetSelector
    from visual_aiming.config.schema import TargetSelectionConfig
    from visual_aiming.core.schemas import Detection

    config = TargetSelectionConfig()
    config.sticky_enabled = True
    config.sticky_switch_margin = 0.10
    selector = TargetSelector(config)

    old = Detection((10, 10, 20, 20), confidence=0.55, class_id=1, class_name="person")
    better = Detection((45, 40, 20, 20), confidence=0.99, class_id=0, class_name="head")

    selector.select([old], roi_center=(50, 50))
    selected = selector.select([better, old], roi_center=(50, 50))

    self.assertEqual(selected.detection.bbox, better.bbox)
    self.assertTrue(selected.switched)
```

- [x] **Step 2: Run tests to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_algorithms.TargetSelectorTest -v
```

Expected: at least the margin test fails because current switching behavior is not strict enough or config lacks `sticky_switch_margin`.

- [x] **Step 3: Add config field**

In `src/visual_aiming/config/schema.py`, extend `TargetSelectionConfig`:

```python
sticky_switch_margin: float = 0.20
```

If legacy flat config mapping exists for target selection, map `target_sticky_switch_margin` into this field.

- [x] **Step 4: Implement margin logic**

In `src/visual_aiming/algorithms/target_selection.py`, apply the rule:

```python
if self._last_bbox is not None and self.config.sticky_enabled:
    sticky = self._find_sticky_candidate(candidates)
    if sticky is not None:
        best = candidates[0]
        margin = max(0.0, float(self.config.sticky_switch_margin))
        if best.detection.bbox != sticky.detection.bbox and best.score > sticky.score - margin:
            sticky.switched = False
            sticky.reason = "sticky_margin"
            self._last_bbox = sticky.detection.bbox
            return sticky
```

Adjust the comparison direction to match the current selector score contract. If lower score is better, require the new target score to be lower than sticky score by at least `margin`.

- [x] **Step 5: Verify selector behavior**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_algorithms.TargetSelectorTest -v
.venv\Scripts\python.exe -m unittest tests.test_modular_pipeline -v
```

Expected: selector tests and pipeline tests pass.

- [x] **Step 6: Commit**

```powershell
git add src/visual_aiming/config/schema.py src/visual_aiming/algorithms/target_selection.py tests/test_modular_algorithms.py
git commit -m "增强目标选择迟滞"
```

Explain to user:

```text
Task 2 完成：目标选择新增切换迟滞，小幅评分波动不会立刻切换目标；只有新目标明显更优才切换。
```

---

## Task 3: Short Loss Hold and Prediction State

**Files:**
- Modify: `src/visual_aiming/config/schema.py`
- Modify: `src/visual_aiming/algorithms/prediction.py`
- Modify: `tests/test_modular_algorithms.py`

- [ ] **Step 1: Write failing tests for short loss hold**

Add to `PredictorTest` in `tests/test_modular_algorithms.py`:

```python
def test_predictor_holds_recent_target_for_short_detection_gap(self):
    from visual_aiming.algorithms.prediction import AlphaBetaPredictor
    from visual_aiming.config.schema import PredictionConfig
    from visual_aiming.core.schemas import AimMeasurement, RuntimeMode

    config = PredictionConfig()
    config.hold_ms = 120.0
    predictor = AlphaBetaPredictor(config)

    measurement = AimMeasurement(point=(100, 100), crosshair=(50, 50), error=(50.0, 50.0), valid=True)
    missing = AimMeasurement(point=None, crosshair=(50, 50), error=(0.0, 0.0), valid=False)

    predictor.update(measurement, RuntimeMode(active=True, firing=False), now=1.0)
    held = predictor.update(missing, RuntimeMode(active=True, firing=False), now=1.05)

    self.assertEqual(held.state, "held")
    self.assertIsNotNone(held.point)
    self.assertGreater(held.confidence, 0.0)


def test_predictor_reports_lost_after_hold_window(self):
    from visual_aiming.algorithms.prediction import AlphaBetaPredictor
    from visual_aiming.config.schema import PredictionConfig
    from visual_aiming.core.schemas import AimMeasurement, RuntimeMode

    config = PredictionConfig()
    config.hold_ms = 120.0
    predictor = AlphaBetaPredictor(config)

    measurement = AimMeasurement(point=(100, 100), crosshair=(50, 50), error=(50.0, 50.0), valid=True)
    missing = AimMeasurement(point=None, crosshair=(50, 50), error=(0.0, 0.0), valid=False)

    predictor.update(measurement, RuntimeMode(active=True, firing=False), now=1.0)
    lost = predictor.update(missing, RuntimeMode(active=True, firing=False), now=1.30)

    self.assertEqual(lost.state, "lost")
    self.assertIsNone(lost.point)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_algorithms.PredictorTest -v
```

Expected: fail because `PredictionConfig.hold_ms` or `"held"` behavior is missing or incomplete.

- [ ] **Step 3: Add prediction config**

In `src/visual_aiming/config/schema.py`, extend `PredictionConfig`:

```python
hold_ms: float = 120.0
hold_confidence: float = 0.35
```

- [ ] **Step 4: Implement held state**

In `src/visual_aiming/algorithms/prediction.py`, when measurement is invalid but the last accepted point is recent:

```python
age_ms = (now - self._last_time) * 1000.0 if self._last_time is not None else float("inf")
if self._last_point is not None and age_ms <= max(0.0, float(self.config.hold_ms)):
    return PredictedAim(
        point=self._last_point,
        velocity=self._velocity,
        confidence=max(0.0, min(1.0, float(self.config.hold_confidence))),
        state="held",
    )
```

Use the existing internal field names in `AlphaBetaPredictor`; do not add duplicate state variables if equivalent fields already exist.

- [ ] **Step 5: Verify predictor and analyzer compatibility**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_algorithms.PredictorTest tests.test_modular_apps.ModularAppsTest -v
```

Expected: tests pass and log analyzer state counts include `"held"` naturally through existing counting logic.

- [ ] **Step 6: Commit**

```powershell
git add src/visual_aiming/config/schema.py src/visual_aiming/algorithms/prediction.py tests/test_modular_algorithms.py
git commit -m "增加短时目标保持状态"
```

Explain to user:

```text
Task 3 完成：短暂丢检测不会立即变成 lost，而是进入 held 状态，诊断日志能区分短时保持和真正丢失。
```

---

## Task 4: Loss Reason and Command Reason Reporting

**Files:**
- Modify: `src/visual_aiming/core/pipeline.py`
- Modify: `src/visual_aiming/core/schemas.py`
- Modify: `tests/test_modular_pipeline.py`
- Modify: `tests/test_modular_apps.py`

- [ ] **Step 1: Write failing pipeline telemetry test**

Add to `tests/test_modular_pipeline.py`:

```python
def test_lost_target_result_records_no_detection_reason(self):
    from visual_aiming.core.pipeline import ModularPipeline

    output = FakeOutput()
    config = ModularConfig()
    pipeline = ModularPipeline(config, FakeDetector([]), output)

    result = pipeline.tick(self.make_frame(active=True), now=1.0)

    self.assertEqual(result.selected.reason, "no_detections")
    self.assertIn(result.predicted.state, {"lost", "held"})
    self.assertIn(result.command.reason, {"no_target", "lost", "held", "deadzone"})
```

If `ControlCommand.reason` already reports a different valid reason, choose one stable vocabulary and update this expected set before implementation.

- [ ] **Step 2: Run pipeline test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_pipeline.ModularPipelineTest.test_lost_target_result_records_no_detection_reason -v
```

Expected: fail if reason vocabulary is missing, inconsistent, or too generic.

- [ ] **Step 3: Stabilize command reasons**

In `src/visual_aiming/core/pipeline.py`, ensure invalid prediction produces a no-target command reason before output:

```python
if predicted.point is None:
    command = ControlCommand(mode="none", reason="no_target")
else:
    error = self._error_from_prediction(predicted, frame.crosshair)
    command = self.controller.update(error, active=mode.active, dt=self._dt)
    if predicted.state == "held" and command.mode == "relative":
        command.reason = "held"
```

Keep controller-specific reasons such as `deadzone`, `subpixel`, and `limited` when they are more precise.

- [ ] **Step 4: Add analyzer report coverage**

In `tests/test_modular_apps.py`, add a small log analyzer assertion:

```python
def test_log_analyzer_reports_no_target_and_held_reasons(self):
    from visual_aiming.app.log_analyzer import analyze_jsonl

    rows = [
        {"detections": [], "selected": {"reason": "no_detections"}, "predicted": {"state": "held"}, "command": {"mode": "relative", "reason": "held", "dx": 1, "dy": 0}},
        {"detections": [], "selected": {"reason": "no_detections"}, "predicted": {"state": "lost"}, "command": {"mode": "none", "reason": "no_target", "dx": 0, "dy": 0}},
    ]

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "run.jsonl"
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

        report = analyze_jsonl(path)

    self.assertEqual(report["predicted_state_counts"], {"held": 1, "lost": 1})
    self.assertEqual(report["command_reason_counts"], {"held": 1, "no_target": 1})
```

- [ ] **Step 5: Verify task**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_pipeline tests.test_modular_apps -v
```

- [ ] **Step 6: Commit**

```powershell
git add src/visual_aiming/core/pipeline.py src/visual_aiming/core/schemas.py tests/test_modular_pipeline.py tests/test_modular_apps.py
git commit -m "规范目标丢失诊断原因"
```

Explain to user:

```text
Task 4 完成：日志可以更清楚区分 no_detections、held、lost 和 no_target，方便判断问题发生在检测、选择、预测还是控制输出。
```

---

## Task 5: Simplify Common Tuning Surface

**Files:**
- Modify: `src/visual_aiming/actions/config_window.py`
- Modify: `tests/test_config_window_sections.py`
- Modify: `docs/debug-workflow.md`

- [ ] **Step 1: Write failing UI-section test**

In `tests/test_config_window_sections.py`, add:

```python
def test_common_tuning_keeps_only_high_value_controls(self):
    from visual_aiming.actions.config_window import ConfigWindow

    sections = ConfigWindow.section_specs()
    common = next(section for section in sections if section.title == "常用调参")
    keys = [item.key for item in common.items]

    self.assertLessEqual(len(keys), 10)
    self.assertIn("yolo_conf_threshold", keys)
    self.assertIn("head_bias", keys)
    self.assertIn("aim_deadzone", keys)
    self.assertIn("sticky_switch_margin", keys)
    self.assertIn("hold_ms", keys)
    self.assertNotIn("tracker_prediction_time", keys)
```

Use the actual section title if current code names it differently.

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_config_window_sections -v
```

Expected: fail until new algorithm parameters are exposed in the common section and low-frequency advanced parameters are moved out.

- [ ] **Step 3: Update section specs**

In `src/visual_aiming/actions/config_window.py`, keep common controls focused:

```python
NumberSpec("yolo_conf_threshold", "检测置信度", 0.05, 0.95, 0.01, "越高越少误检，越低越容易检出。"),
NumberSpec("head_bias", "头部瞄点偏置", 0.0, 0.8, 0.01, "控制瞄点在框内向上的比例。"),
NumberSpec("aim_deadzone", "控制死区", 0, 50, 1, "小误差不输出控制命令。"),
NumberSpec("sticky_switch_margin", "切换迟滞", 0.0, 1.0, 0.01, "越高越不容易切换目标。"),
NumberSpec("hold_ms", "短时保持", 0, 300, 10, "检测短暂丢失时继续保持目标的时间。"),
BoolSpec("mouse_diagnostics_enabled", "输出诊断日志", "打印鼠标输出链路摘要。"),
```

Move rare controls into advanced sections instead of deleting their config fields.

- [ ] **Step 4: Update docs**

In `docs/debug-workflow.md`, add:

```markdown
### Recommended tuning order

1. Adjust `检测置信度` until obvious false positives are controlled.
2. Adjust `切换迟滞` when targets switch too often.
3. Adjust `短时保持` when short detection gaps produce unstable commands.
4. Adjust `控制死区` only after target selection and prediction are stable.
```

- [ ] **Step 5: Verify task**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_config_window_sections -v
.venv\Scripts\python.exe -m compileall -q src tests
```

- [ ] **Step 6: Commit**

```powershell
git add src/visual_aiming/actions/config_window.py tests/test_config_window_sections.py docs/debug-workflow.md
git commit -m "简化常用调参界面"
```

Explain to user:

```text
Task 5 完成：常用调参只保留检测、瞄点、目标切换、短时保持、死区和诊断这些高频项，其他参数仍在高级区。
```

---

## Task 6: Replay Regression Suite

**Files:**
- Create: `scripts/replay_regression.py`
- Create: `tests/test_replay_regression.py`
- Modify: `docs/debug-workflow.md`

- [ ] **Step 1: Write failing tests for suite manifest parsing**

Create `tests/test_replay_regression.py`:

```python
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class ReplayRegressionTest(unittest.TestCase):
    def test_load_manifest_reads_video_cases(self):
        from scripts.replay_regression import load_manifest

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps({
                "cases": [
                    {
                        "name": "sample",
                        "video": "data/sample.mp4",
                        "min_visible_detection_rate": 80.0,
                        "max_empty_false_positive_rate": 5.0,
                        "max_target_switches": 12,
                    }
                ]
            }), encoding="utf-8")

            cases = load_manifest(path)

        self.assertEqual(cases[0].name, "sample")
        self.assertEqual(cases[0].video, Path("data/sample.mp4"))
        self.assertEqual(cases[0].max_target_switches, 12)

    def test_run_case_replays_and_evaluates_generated_log(self):
        from scripts.replay_regression import ReplayCase, run_case

        calls = []

        def fake_replay(video, diagnostics_path):
            calls.append(("replay", video, diagnostics_path))
            diagnostics_path.write_text(
                json.dumps({"target_visible": True, "detections": [{"class_id": 0}], "selected": {"switched": False}}) + "\n",
                encoding="utf-8",
            )

        def fake_evaluate(path, min_visible_detection_rate, max_empty_false_positive_rate, max_target_switches):
            calls.append(("evaluate", path, min_visible_detection_rate, max_empty_false_positive_rate, max_target_switches))
            return type("Result", (), {"passed": True, "failures": []})()

        with tempfile.TemporaryDirectory() as tmp:
            case = ReplayCase(
                name="sample",
                video=Path("data/sample.mp4"),
                min_visible_detection_rate=80.0,
                max_empty_false_positive_rate=5.0,
                max_target_switches=12,
            )
            result = run_case(case, Path(tmp), replay=fake_replay, evaluate=fake_evaluate)

        self.assertTrue(result.passed)
        self.assertEqual(calls[0][0], "replay")
        self.assertEqual(calls[0][1], Path("data/sample.mp4"))
        self.assertEqual(calls[1][0], "evaluate")
        self.assertEqual(calls[1][2:], (80.0, 5.0, 12))
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_replay_regression -v
```

Expected: fail because `scripts.replay_regression` does not exist.

- [ ] **Step 3: Implement manifest loader**

Create `scripts/replay_regression.py`:

```python
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
```

- [ ] **Step 4: Verify task**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_replay_regression -v
.venv\Scripts\python.exe -m compileall -q scripts tests
```

- [ ] **Step 5: Document manifest format**

Add to `docs/debug-workflow.md`:

```markdown
### Replay regression manifest

```json
{
  "cases": [
    {
      "name": "sample",
      "video": "data/sample.mp4",
      "min_visible_detection_rate": 80.0,
      "max_empty_false_positive_rate": 5.0,
      "max_target_switches": 12
    }
  ]
}
```

Start with one short representative video before adding more cases. The command writes JSONL files under `logs/replay_regression/` and evaluates each case with its thresholds.
```

- [ ] **Step 6: Commit**

```powershell
git add scripts/replay_regression.py tests/test_replay_regression.py docs/debug-workflow.md
git commit -m "添加回放回归清单"
```

Explain to user:

```text
Task 6 完成：项目有了视频回归清单和执行入口，可以把手动测试视频逐步变成可重复评估的回归集。
```

---

## Task 7: Phase Verification and Handoff

**Files:**
- Modify: `docs/debug-workflow.md`
- Modify: this plan file

- [ ] **Step 1: Run full verification**

Run:

```powershell
.venv\Scripts\python.exe -m unittest discover tests -v
.venv\Scripts\python.exe -m compileall -q src tests scripts main.py
git diff --check
rg "visual_aiming\.core\.runtime\b|RuntimePipeline\b|legacy_main\b" main.py src tests
```

Expected:

- All tests pass.
- Compile check has no output.
- Diff check has no whitespace errors.
- Legacy runtime scan has no matches.

- [ ] **Step 2: Collect manual test instructions**

Add to `docs/debug-workflow.md`:

```markdown
### Manual phase check

1. Run `python main.py --video-test`.
2. Use a short video with visible enemies and empty-scene sections.
3. Save the generated JSONL log.
4. Run `python main.py --analyze-log logs\name.jsonl`.
5. If the log has annotations, run `python scripts\evaluate_diagnostics.py logs\name.jsonl --min-visible-detection-rate 80 --max-empty-false-positive-rate 10 --max-target-switches 20`.
6. Do not enable real mouse output during this phase unless the task explicitly says so.
```

- [ ] **Step 3: Commit phase wrap-up**

```powershell
git add docs/debug-workflow.md docs/superpowers/plans/2026-06-15-algorithm-debug-stabilization.md
git commit -m "完善算法调试稳定化计划"
```

Explain to user:

```text
Task 7 完成：算法调试稳定化阶段完成，下一步可以转入鼠标角度控制计划；在此之前已有可重复日志评估、目标稳定性、短时保持和常用调参入口。
```

---

## Commit Guidance

Commit per task. Do not include `config.json` unless the user explicitly asks to commit local tuning values.

Suggested commit sequence:

```powershell
git commit -m "添加诊断阈值评估工具"
git commit -m "增强目标选择迟滞"
git commit -m "增加短时目标保持状态"
git commit -m "规范目标丢失诊断原因"
git commit -m "简化常用调参界面"
git commit -m "添加回放回归清单"
git commit -m "完善算法调试稳定化计划"
```

Push only when requested or when a full phase is complete and the user confirms network is available.
