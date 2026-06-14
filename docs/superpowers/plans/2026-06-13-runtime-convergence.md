# Runtime Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make legacy realtime runtime and modular replay/video-test runtime converge onto shared contracts, shared diagnostics, and eventually one realtime composition path without changing mouse angular-control behavior in this phase.

**Architecture:** Keep the current legacy realtime loop working while extracting shared data contracts and reusable services. Migrate behavior from the outside inward: first document and test boundaries, then unify output/config/diagnostics, then introduce a modular realtime runner behind an explicit flag, and only after parity tests pass switch the default path. This avoids a full rewrite and prevents video-test behavior from drifting away from real realtime behavior.

**Tech Stack:** Python, `unittest`, existing `visual_aiming` package, current YOLO detector adapter, current screenshot/capture services, current mouse sender abstraction.

---

## Current Situation

This is not a live resource conflict. In normal use, old and new runtimes do not run at the same time.

Current route map:

- `python main.py` calls `visual_aiming.core.runtime.main()` and uses the legacy realtime loop.
- `python main.py --video-test` calls `visual_aiming.app.video_test.run_video_test()` and uses modular video diagnostics.
- `python main.py --modular --video <file>` calls `visual_aiming.app.replay.run_video_file()` and uses `ModularPipeline`.
- `python main.py --modular` without `--video` currently falls back to the legacy realtime loop.

The real problem is duplicated behavior:

- Legacy realtime uses `RuntimePipeline`, `RuntimeServices`, and `MouseController`.
- Modular replay/video paths use `ModularPipeline`, modular adapters, `RelativeController`, and output backends.
- Some behavior is already converging, especially mouse output through `src/visual_aiming/common/mouse_sender.py`.
- Some behavior is still split, especially realtime orchestration, config mapping, diagnostic event shape, and control-stage data models.

## Non-Goals

- Do not implement angular mouse control here. That is covered by `docs/superpowers/plans/2026-06-13-mouse-angular-control.md`.
- Do not directly port the whole realtime loop in one edit.
- Do not delete `RuntimePipeline` until modular realtime has parity tests and manual validation.
- Do not stage, reset, or rewrite `config.json`; it is user-local runtime state.

## File Structure

Create:

- `docs/runtime-convergence.md`: human-readable map of old/new runtime routes, shared contracts, migration status, and manual validation notes.
- `src/visual_aiming/core/runtime_modes.py`: pure entrypoint routing helpers and mode names.
- `src/visual_aiming/core/realtime_composition.py`: modular realtime service composition, initially behind explicit opt-in.
- `tests/test_runtime_modes.py`: tests for CLI/runtime routing decisions.
- `tests/test_realtime_composition.py`: tests for modular realtime composition using fakes.
- `tests/test_runtime_convergence_contracts.py`: tests that legacy and modular paths emit compatible diagnostic/control contract fields.

Modify:

- `main.py`: route through `runtime_modes.py` so mode choice is explicit and testable.
- `src/visual_aiming/core/runtime.py`: keep legacy runtime, but expose small reusable pieces if needed; avoid adding more algorithm logic here.
- `src/visual_aiming/core/runtime_services.py`: expose service construction boundaries clearly enough for tests and future modular reuse.
- `src/visual_aiming/core/pipeline.py`: add compatibility helpers only if they reduce duplication with modular contracts.
- `src/visual_aiming/core/modular_pipeline.py`: align diagnostic/control event fields with legacy where possible.
- `src/visual_aiming/config/loader.py`: centralize legacy-to-modular config conversion instead of scattered ad hoc mapping.
- `src/visual_aiming/app/replay.py`: keep using modular pipeline, but consume shared diagnostic schema if introduced.
- `src/visual_aiming/app/video_test.py`: keep video-test UI behavior, but use shared diagnostics/output event formatting.
- `tests/test_runtime_pipeline.py`, `tests/test_modular_pipeline.py`, `tests/test_modular_apps.py`: extend with parity tests rather than replacing existing tests.

## Task 1: Boundary Audit Document

**Files:**
- Create: `docs/runtime-convergence.md`

- [x] **Step 1: Write runtime route table**

Create `docs/runtime-convergence.md` with this content:

```markdown
# Runtime Convergence

## Route Table

| Command | Runtime path | Pipeline | Mouse/control path | Status |
| --- | --- | --- | --- | --- |
| `python main.py` | `visual_aiming.core.runtime.main()` | `RuntimePipeline` | `MouseController` | Legacy realtime default |
| `python main.py --video-test` | `visual_aiming.app.video_test.run_video_test()` | Modular video path | Modular control/output diagnostics | Active debug path |
| `python main.py --modular --video <file>` | `visual_aiming.app.replay.run_video_file()` | `ModularPipeline` | Configured output backend | Active replay path |
| `python main.py --modular` | Falls back to `visual_aiming.core.runtime.main()` | `RuntimePipeline` | `MouseController` | Temporary fallback |

## Problem

There is no normal single-process fight between old and new runtimes. The risk is behavior drift: fixes verified in video replay may not affect live realtime, and live-only behavior may not be covered by modular tests.

## Convergence Rule

Move shared behavior into small modules first. Keep realtime behavior stable until each shared contract has tests.

## Migration Order

1. Route decisions become explicit and testable.
2. Diagnostics and control events use compatible field names.
3. Config conversion lives in one place.
4. Modular realtime composition exists behind an explicit flag.
5. Manual parity testing decides when default realtime can switch.

## Deferred

Mouse angular control is intentionally deferred to `docs/superpowers/plans/2026-06-13-mouse-angular-control.md`.
```

- [x] **Step 2: Verify no stale wording**

Run:

```powershell
.venv\Scripts\python.exe - <<'PY'
from pathlib import Path
p = Path("docs/runtime-convergence.md")
text = p.read_text(encoding="utf-8")
for word in ["未定占位", "待办占位", "争抢", "冲突导致"]:
    assert word not in text, word
assert "behavior drift" in text
assert "Mouse angular control" in text
print("runtime convergence doc ok")
PY
```

Expected:

```text
runtime convergence doc ok
```

- [x] **Step 3: Explain task result to user**

Explain:

```text
Task 1 完成：这一步没有改运行逻辑，只把新旧 runtime 的入口、当前状态、真实风险和迁移顺序写清楚。结论是当前不是资源争抢，而是行为分叉，需要逐步收敛。
```

## Task 2: Testable Runtime Mode Routing

**Files:**
- Create: `src/visual_aiming/core/runtime_modes.py`
- Create: `tests/test_runtime_modes.py`
- Modify: `main.py`

- [x] **Step 1: Write failing routing tests**

Create `tests/test_runtime_modes.py`:

```python
import argparse
import unittest

from visual_aiming.core.runtime_modes import RuntimeMode, choose_runtime_mode


class RuntimeModeTests(unittest.TestCase):
    def _args(self, **overrides):
        values = {
            "analyze_log": "",
            "video_test": False,
            "modular": False,
            "video": "",
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_analyze_log_wins(self):
        mode = choose_runtime_mode(self._args(analyze_log="logs/run.jsonl"))
        self.assertEqual(mode, RuntimeMode.ANALYZE_LOG)

    def test_video_test_wins_before_modular(self):
        mode = choose_runtime_mode(self._args(video_test=True, modular=True, video="a.mp4"))
        self.assertEqual(mode, RuntimeMode.VIDEO_TEST)

    def test_modular_video_replay(self):
        mode = choose_runtime_mode(self._args(modular=True, video="a.mp4"))
        self.assertEqual(mode, RuntimeMode.MODULAR_REPLAY)

    def test_modular_realtime_opt_in(self):
        mode = choose_runtime_mode(self._args(modular=True))
        self.assertEqual(mode, RuntimeMode.MODULAR_REALTIME)

    def test_default_legacy_realtime(self):
        mode = choose_runtime_mode(self._args())
        self.assertEqual(mode, RuntimeMode.LEGACY_REALTIME)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_runtime_modes -v
```

Expected: fail with `ModuleNotFoundError` for `visual_aiming.core.runtime_modes`.

- [x] **Step 3: Add runtime mode helper**

Create `src/visual_aiming/core/runtime_modes.py`:

```python
from __future__ import annotations

from enum import Enum


class RuntimeMode(str, Enum):
    ANALYZE_LOG = "analyze_log"
    VIDEO_TEST = "video_test"
    MODULAR_REPLAY = "modular_replay"
    MODULAR_REALTIME = "modular_realtime"
    LEGACY_REALTIME = "legacy_realtime"


def choose_runtime_mode(args) -> RuntimeMode:
    if getattr(args, "analyze_log", ""):
        return RuntimeMode.ANALYZE_LOG
    if getattr(args, "video_test", False):
        return RuntimeMode.VIDEO_TEST
    if getattr(args, "modular", False) and getattr(args, "video", ""):
        return RuntimeMode.MODULAR_REPLAY
    if getattr(args, "modular", False):
        return RuntimeMode.MODULAR_REALTIME
    return RuntimeMode.LEGACY_REALTIME
```

- [x] **Step 4: Route `main.py` through helper**

Modify `main.py` so `main(argv=None)` follows this structure:

```python
def main(argv=None):
    args = parse_args(argv)
    from visual_aiming.core.runtime_modes import RuntimeMode, choose_runtime_mode

    mode = choose_runtime_mode(args)
    if mode == RuntimeMode.ANALYZE_LOG:
        from visual_aiming.app.log_analyzer import analyze_jsonl, format_report

        print(format_report(analyze_jsonl(args.analyze_log)))
        return 0
    if mode == RuntimeMode.VIDEO_TEST:
        from visual_aiming.app.video_test import run_video_test

        return run_video_test()
    if mode in (RuntimeMode.MODULAR_REPLAY, RuntimeMode.MODULAR_REALTIME):
        return _run_modular(args, mode=mode)
    from visual_aiming.core.runtime import main as legacy_main

    return legacy_main()
```

Change `_run_modular` signature and keep temporary fallback explicit:

```python
def _run_modular(args, mode=None):
    from visual_aiming.config.loader import load_modular_config
    from visual_aiming.core.runtime_modes import RuntimeMode

    config = load_modular_config("config.json")
    config.output.backend = args.output
    config.output.real_mouse = args.real_mouse
    config.output.diagnostics_path = args.diagnostics or config.output.diagnostics_path

    if mode == RuntimeMode.MODULAR_REPLAY:
        from visual_aiming.app.replay import run_video_file

        return run_video_file(args.video, config)

    from visual_aiming.core.runtime import main as legacy_main

    print("[modular] Realtime modular composition is not default yet; falling back to legacy realtime loop.")
    return legacy_main()
```

- [x] **Step 5: Run routing tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_runtime_modes -v
```

Expected: all tests pass.

- [x] **Step 6: Run existing app tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_apps tests.test_runtime_pipeline -v
```

Expected: all tests pass.

- [x] **Step 7: Explain task result to user**

Explain:

```text
Task 2 完成：入口选择从 main.py 里的隐式 if 分支变成可测试的 RuntimeMode。运行行为基本不变，`--modular` 实时仍然回退旧 runtime，但现在这个临时状态被明确命名，后续迁移不会靠猜。
```

## Task 3: Shared Diagnostic Contract

**Files:**
- Create: `src/visual_aiming/core/diagnostic_events.py`
- Create: `tests/test_runtime_convergence_contracts.py`
- Modify: `src/visual_aiming/core/modular_pipeline.py`
- Modify: `src/visual_aiming/actions/mouse_control.py`

- [ ] **Step 1: Write failing diagnostic contract tests**

Create `tests/test_runtime_convergence_contracts.py`:

```python
import unittest

from visual_aiming.core.diagnostic_events import normalize_control_event


class DiagnosticContractTests(unittest.TestCase):
    def test_normalize_modular_control_event(self):
        event = normalize_control_event(
            {
                "seq": 12,
                "target_found": True,
                "target_lost": False,
                "command": {"dx": 3.5, "dy": -2.0},
                "output": {"backend": "null", "sent": True},
            }
        )

        self.assertEqual(event["seq"], 12)
        self.assertTrue(event["target_found"])
        self.assertFalse(event["target_lost"])
        self.assertEqual(event["command_dx"], 3.5)
        self.assertEqual(event["command_dy"], -2.0)
        self.assertEqual(event["output_backend"], "null")
        self.assertTrue(event["output_sent"])

    def test_normalize_legacy_mouse_diagnostics(self):
        event = normalize_control_event(
            {
                "seq": 5,
                "mouse_diagnostics": {
                    "last_command": [1, 2],
                    "sender": "sendinput",
                    "sent_moves": 4,
                    "zero_outputs": 1,
                },
            }
        )

        self.assertEqual(event["seq"], 5)
        self.assertEqual(event["command_dx"], 1)
        self.assertEqual(event["command_dy"], 2)
        self.assertEqual(event["output_backend"], "sendinput")
        self.assertTrue(event["output_sent"])
        self.assertEqual(event["sent_moves"], 4)
        self.assertEqual(event["zero_outputs"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_runtime_convergence_contracts -v
```

Expected: fail with `ModuleNotFoundError` for `visual_aiming.core.diagnostic_events`.

- [ ] **Step 3: Add diagnostic normalizer**

Create `src/visual_aiming/core/diagnostic_events.py`:

```python
from __future__ import annotations

from typing import Any


def _command_pair(value: Any) -> tuple[float, float]:
    if isinstance(value, dict):
        return float(value.get("dx", 0.0)), float(value.get("dy", 0.0))
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return float(value[0]), float(value[1])
    return 0.0, 0.0


def normalize_control_event(event: dict[str, Any]) -> dict[str, Any]:
    mouse = event.get("mouse_diagnostics") or {}
    command = event.get("command", mouse.get("last_command", (0.0, 0.0)))
    command_dx, command_dy = _command_pair(command)
    output = event.get("output") or {}
    sent_moves = int(mouse.get("sent_moves", 0))

    return {
        "seq": event.get("seq"),
        "target_found": bool(event.get("target_found", False)),
        "target_lost": bool(event.get("target_lost", False)),
        "command_dx": command_dx,
        "command_dy": command_dy,
        "output_backend": output.get("backend", mouse.get("sender", "")),
        "output_sent": bool(output.get("sent", sent_moves > 0)),
        "sent_moves": sent_moves,
        "zero_outputs": int(mouse.get("zero_outputs", 0)),
    }
```

- [ ] **Step 4: Use normalizer at log boundaries**

In `src/visual_aiming/core/modular_pipeline.py`, import:

```python
from .diagnostic_events import normalize_control_event
```

When emitting diagnostics, include:

```python
event["control_contract"] = normalize_control_event(event)
```

In `src/visual_aiming/actions/mouse_control.py`, wherever `mouse_diagnostics` is printed or attached, add normalized fields beside the raw diagnostics:

```python
from visual_aiming.core.diagnostic_events import normalize_control_event

event["control_contract"] = normalize_control_event(event)
```

If the legacy path only prints a dict and not a named `event`, wrap the existing dict before printing:

```python
payload = {"seq": seq, "mouse_diagnostics": diagnostics}
payload["control_contract"] = normalize_control_event(payload)
```

- [ ] **Step 5: Run diagnostic tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_runtime_convergence_contracts tests.test_modular_pipeline tests.test_mouse_control -v
```

Expected: all tests pass.

- [ ] **Step 6: Explain task result to user**

Explain:

```text
Task 3 完成：没有改变算法，只给新旧路径的控制/鼠标诊断加了一层统一 contract。以后分析日志时可以看统一字段，不必每次区分这是旧 MouseController 还是新 ModularPipeline 输出。
```

## Task 4: Centralized Config Mapping

**Files:**
- Modify: `src/visual_aiming/config/loader.py`
- Modify: `src/visual_aiming/config/__init__.py`
- Create or extend: `tests/test_modular_schemas_config.py`

- [ ] **Step 1: Write config mapping tests**

Add to `tests/test_modular_schemas_config.py`:

```python
class ConfigMappingTests(unittest.TestCase):
    def test_modular_config_receives_mouse_output_fields(self):
        from visual_aiming.config import Config
        from visual_aiming.config.loader import legacy_to_modular_config

        legacy = Config()
        legacy.mouse_output_backend = "sendinput"
        legacy.mouse_real_output_enabled = True
        legacy.mouse_diagnostics_enabled = True

        modular = legacy_to_modular_config(legacy)

        self.assertEqual(modular.output.backend, "sendinput")
        self.assertTrue(modular.output.real_mouse)
        self.assertTrue(modular.output.mouse_diagnostics_enabled)

    def test_modular_config_receives_roi_fields(self):
        from visual_aiming.config import Config
        from visual_aiming.config.loader import legacy_to_modular_config

        legacy = Config()
        legacy.roi_size = 416
        legacy.roi_width = 320
        legacy.roi_height = 240

        modular = legacy_to_modular_config(legacy)

        self.assertEqual(modular.frame.roi_size, (320, 240))
```

If `Config` uses different exact field names, adjust only the field names to match `src/visual_aiming/config/__init__.py`; keep the assertion intent unchanged.

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_schemas_config -v
```

Expected: fail because `legacy_to_modular_config` does not yet provide all asserted fields.

- [ ] **Step 3: Implement one conversion function**

In `src/visual_aiming/config/loader.py`, add:

```python
def legacy_to_modular_config(legacy_config: Config) -> ModularConfig:
    modular = ModularConfig()
    roi_width = int(getattr(legacy_config, "roi_width", getattr(legacy_config, "roi_size", 640)))
    roi_height = int(getattr(legacy_config, "roi_height", getattr(legacy_config, "roi_size", 640)))
    modular.frame.roi_size = (roi_width, roi_height)
    modular.output.backend = getattr(legacy_config, "mouse_output_backend", modular.output.backend)
    modular.output.real_mouse = bool(getattr(legacy_config, "mouse_real_output_enabled", modular.output.real_mouse))
    modular.output.mouse_diagnostics_enabled = bool(
        getattr(legacy_config, "mouse_diagnostics_enabled", False)
    )
    return modular
```

Update `load_modular_config()` to use this function after loading the legacy config object, instead of duplicating field mapping inline.

- [ ] **Step 4: Run config tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_schemas_config tests.test_config_window_sections -v
```

Expected: all tests pass.

- [ ] **Step 5: Explain task result to user**

Explain:

```text
Task 4 完成：配置转换收敛到一个函数。后续新增参数时，只需要检查一个 legacy_to_modular_config 映射点，减少“调参窗口改了但模块化路径没吃到参数”的风险。
```

## Task 5: Modular Realtime Composition Behind Explicit Flag

**Files:**
- Create: `src/visual_aiming/core/realtime_composition.py`
- Create: `tests/test_realtime_composition.py`
- Modify: `main.py`

- [ ] **Step 1: Write composition tests with fakes**

Create `tests/test_realtime_composition.py`:

```python
import unittest

from visual_aiming.core.realtime_composition import RealtimeComposition, run_modular_realtime_once


class FakeFrameSource:
    def __init__(self):
        self.frames = ["frame"]

    def read(self):
        return self.frames.pop(0) if self.frames else None


class FakePipeline:
    def __init__(self):
        self.frames = []

    def process_frame(self, frame):
        self.frames.append(frame)
        return {"seq": len(self.frames), "target_found": False}


class FakeOutput:
    def __init__(self):
        self.events = []

    def send(self, event):
        self.events.append(event)


class RealtimeCompositionTests(unittest.TestCase):
    def test_run_once_processes_frame_and_output(self):
        source = FakeFrameSource()
        pipeline = FakePipeline()
        output = FakeOutput()
        composition = RealtimeComposition(source, pipeline, output)

        result = run_modular_realtime_once(composition)

        self.assertTrue(result)
        self.assertEqual(pipeline.frames, ["frame"])
        self.assertEqual(output.events, [{"seq": 1, "target_found": False}])

    def test_run_once_stops_when_no_frame(self):
        source = FakeFrameSource()
        source.frames.clear()
        pipeline = FakePipeline()
        output = FakeOutput()
        composition = RealtimeComposition(source, pipeline, output)

        result = run_modular_realtime_once(composition)

        self.assertFalse(result)
        self.assertEqual(pipeline.frames, [])
        self.assertEqual(output.events, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_realtime_composition -v
```

Expected: fail with `ModuleNotFoundError` for `visual_aiming.core.realtime_composition`.

- [ ] **Step 3: Add composition shell**

Create `src/visual_aiming/core/realtime_composition.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class FrameSource(Protocol):
    def read(self):
        ...


class Pipeline(Protocol):
    def process_frame(self, frame):
        ...


class Output(Protocol):
    def send(self, event) -> None:
        ...


@dataclass
class RealtimeComposition:
    frame_source: FrameSource
    pipeline: Pipeline
    output: Output


def run_modular_realtime_once(composition: RealtimeComposition) -> bool:
    frame = composition.frame_source.read()
    if frame is None:
        return False
    event = composition.pipeline.process_frame(frame)
    composition.output.send(event)
    return True
```

- [ ] **Step 4: Wire `main.py --modular --realtime-experimental`**

Add an explicit parser flag:

```python
parser.add_argument(
    "--realtime-experimental",
    action="store_true",
    help="Run experimental modular realtime composition instead of legacy realtime fallback",
)
```

In `_run_modular`, before falling back to legacy:

```python
if mode == RuntimeMode.MODULAR_REALTIME and getattr(args, "realtime_experimental", False):
    from visual_aiming.app.realtime import run_realtime

    return run_realtime(config)
```

Keep the fallback unchanged when `--realtime-experimental` is absent.

- [ ] **Step 5: Run composition and route tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_realtime_composition tests.test_runtime_modes tests.test_modular_apps -v
```

Expected: all tests pass.

- [ ] **Step 6: Explain task result to user**

Explain:

```text
Task 5 完成：模块化实时路径有了显式实验入口，但默认实时路径仍然不变。这样可以开始做真实运行对照测试，同时不会破坏当前可用流程。
```

## Task 6: Parity Checklist and Manual Validation Script

**Files:**
- Modify: `docs/runtime-convergence.md`
- Create: `scripts/runtime_parity_check.py`
- Create: `tests/test_runtime_parity_check.py`

- [ ] **Step 1: Add manual parity checklist**

Append to `docs/runtime-convergence.md`:

```markdown
## Manual Parity Checklist

Run these checks before making modular realtime the default:

1. `python main.py` starts legacy realtime as before.
2. `python main.py --video-test` still opens video test and writes JSONL diagnostics.
3. `python main.py --modular --video <file> --output null` processes replay without moving mouse.
4. `python main.py --modular --realtime-experimental --output null` starts modular realtime without real mouse output.
5. The same config file maps ROI, output backend, and diagnostics fields into both runtime families.
6. Logs contain `control_contract` fields for control/mouse-output analysis.

Do not switch defaults until all six checks pass on the developer machine.
```

- [ ] **Step 2: Write parity script tests**

Create `tests/test_runtime_parity_check.py`:

```python
import unittest

from scripts.runtime_parity_check import check_log_contract


class RuntimeParityCheckTests(unittest.TestCase):
    def test_log_contract_accepts_control_contract(self):
        rows = [
            {"seq": 1, "control_contract": {"command_dx": 0, "command_dy": 0}},
            {"seq": 2, "control_contract": {"command_dx": 1, "command_dy": -1}},
        ]

        result = check_log_contract(rows)

        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["missing_control_contract"], 0)

    def test_log_contract_counts_missing_contract(self):
        rows = [{"seq": 1}, {"seq": 2, "control_contract": {}}]

        result = check_log_contract(rows)

        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["missing_control_contract"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_runtime_parity_check -v
```

Expected: fail because `scripts.runtime_parity_check` does not exist.

- [ ] **Step 4: Add parity script**

Create `scripts/runtime_parity_check.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_jsonl(path: str | Path) -> list[dict]:
    rows = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def check_log_contract(rows: list[dict]) -> dict[str, int]:
    missing = sum(1 for row in rows if "control_contract" not in row)
    return {"rows": len(rows), "missing_control_contract": missing}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check runtime convergence diagnostics contract")
    parser.add_argument("jsonl", help="Diagnostics JSONL path")
    args = parser.parse_args(argv)
    result = check_log_contract(load_jsonl(args.jsonl))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["missing_control_contract"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run parity script tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_runtime_parity_check -v
```

Expected: all tests pass.

- [ ] **Step 6: Explain task result to user**

Explain:

```text
Task 6 完成：这一步给 runtime 收敛增加了手动验收清单和日志 contract 检查脚本。以后每次迁移实时路径，都可以先用这个脚本确认日志是否还能被统一分析。
```

## Task 7: Default Switch Decision Gate

**Files:**
- Modify: `docs/runtime-convergence.md`
- Modify only after manual approval: `main.py`

- [ ] **Step 1: Add decision gate**

Append to `docs/runtime-convergence.md`:

```markdown
## Default Switch Gate

Only switch `python main.py` from legacy realtime to modular realtime after:

- Unit tests pass.
- `--video-test` remains usable.
- `--modular --video` replay remains usable.
- `--modular --realtime-experimental --output null` has been manually tested.
- Mouse output remains disabled unless explicitly enabled.
- User confirms modular realtime behavior is at least as good as legacy realtime.

Until then, legacy realtime remains the default.
```

- [ ] **Step 2: Stop and ask for user review**

Do not change the default runtime in this task. Ask the user to review `docs/runtime-convergence.md` and decide whether to schedule the default switch as a later phase.

Explain:

```text
Task 7 完成：默认切换条件已经写入文档，但没有切换默认入口。当前策略是先实验、再验证、最后才决定是否把 `python main.py` 改成模块化实时路径。
```

## Final Verification

After all approved tasks in this plan are implemented, run:

```powershell
.venv\Scripts\python.exe -m unittest discover tests -v
.venv\Scripts\python.exe -m compileall -q src tests scripts main.py
git diff --check
```

Expected:

- `unittest` passes.
- `compileall` returns no output.
- `git diff --check` returns no whitespace errors.

## Commit Guidance

Commit by phase, not every tiny step. Recommended commits:

```powershell
git add docs/runtime-convergence.md src/visual_aiming/core/runtime_modes.py tests/test_runtime_modes.py main.py
git commit -m "明确新旧运行时路由"

git add src/visual_aiming/core/diagnostic_events.py src/visual_aiming/core/modular_pipeline.py src/visual_aiming/actions/mouse_control.py tests/test_runtime_convergence_contracts.py
git commit -m "统一运行时诊断契约"

git add src/visual_aiming/config/loader.py src/visual_aiming/config/__init__.py tests/test_modular_schemas_config.py
git commit -m "集中运行时配置映射"

git add src/visual_aiming/core/realtime_composition.py scripts/runtime_parity_check.py tests/test_realtime_composition.py tests/test_runtime_parity_check.py docs/runtime-convergence.md main.py
git commit -m "加入模块化实时实验入口"
```

Do not include `config.json` unless the user explicitly requests it.
