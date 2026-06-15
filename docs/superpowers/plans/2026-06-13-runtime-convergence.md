# Single Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current modular video-test/replay logic the only runtime logic for the whole program, so testing and real use share the same pipeline and differ only by input source, output backend, and optional debug observers.

**Architecture:** The final program has one runtime runner: `FrameSource.read()` feeds `ModularPipeline.tick()`, pipeline results go to output and diagnostics, and optional observers render debug UI. Video test uses `VideoFileFrameSource`; realtime use uses `ScreenFrameSource`; mouse output is just one output backend. The old legacy realtime runtime remains only as a temporary fallback during migration and is deleted after realtime parity is verified.

**Tech Stack:** Python, `unittest`, existing `ModularPipeline`, existing frame-source adapters, existing output adapters, existing JSONL diagnostics and video debug UI.

---

## Corrected Direction

Previous direction was "make old and new runtime compatible." That is no longer the target.

The target is:

```text
one runtime runner
+ interchangeable input source
+ interchangeable output backend
+ optional debug observer
```

Expected final shape:

```text
Video test:
VideoFileFrameSource -> ModularPipeline -> Null/LogOutput -> VideoDebugObserver

Video replay:
VideoFileFrameSource -> ModularPipeline -> Null/LogOutput

Realtime:
ScreenFrameSource -> ModularPipeline -> WinMouseOutput/NullOutput -> optional diagnostics
```

The old runtime path:

```text
visual_aiming.core.runtime.main()
RuntimePipeline
MouseController realtime loop
```

is a migration source only. It should not remain as a parallel runtime after the new single runner can handle realtime input safely.

## Already Completed

These tasks were completed before this plan was corrected:

- [x] Runtime route audit document was created at `docs/runtime-convergence.md`.
- [x] `RuntimeMode` was added at `src/visual_aiming/core/runtime_modes.py`.
- [x] `main.py` route choice became testable.
- [x] `tests/test_runtime_modes.py` covers route choice.
- [x] Commit `ae14d16 明确新旧运行时路由` was pushed to `origin/main`.

These changes are still useful because explicit routing makes the migration safer. They are no longer the final architecture.

## Non-Goals

- Do not implement angular mouse control in this plan. That remains in `docs/superpowers/plans/2026-06-13-mouse-angular-control.md`.
- Do not tune detection quality here.
- Do not keep two runtime algorithms long-term.
- Do not move user-local `config.json` into commits.
- Do not make real mouse output the default for tests.

## File Structure

Create:

- `src/visual_aiming/core/runtime_runner.py`: the single reusable loop for video replay, video test, and realtime.
- `tests/test_runtime_runner.py`: fake-source/fake-pipeline/fake-output tests for the shared runner.
- `tests/test_single_runtime_apps.py`: app-level tests proving replay and realtime call the same runner.

Modify:

- `src/visual_aiming/app/replay.py`: use `RuntimeRunner` instead of owning its own loop.
- `src/visual_aiming/app/video_test.py`: keep UI behavior, but use the same runner step or observer hook instead of duplicating pipeline flow.
- `src/visual_aiming/app/realtime.py`: become the realtime composition for `ScreenFrameSource + ModularPipeline + Output`.
- `main.py`: route realtime through the modular realtime app after the safe migration gate is passed.
- `src/visual_aiming/core/pipeline.py`: keep `ModularPipeline`; later remove `RuntimePipeline` when no code imports it.
- `src/visual_aiming/core/runtime.py`: delete after realtime no longer calls it.
- `tests/test_runtime_pipeline.py`: delete or replace old-runtime tests after `RuntimePipeline` is removed.
- `docs/runtime-convergence.md`: update from "convergence" to "single runtime migration" status.

## Core Contract

The single runtime loop must use this contract:

```python
frame = frame_source.read()
if frame is None:
    stop
result = pipeline.tick(frame, now=clock())
observer.on_tick(frame, result)
```

Important details:

- `ModularPipeline.tick()` already owns output publishing through its output backend.
- The runner should not know about YOLO, mouse control, or video UI internals.
- Debug UI is an observer, not another runtime.
- Realtime and video tests must exercise the same `ModularPipeline.tick()` call path.

## Task 1: Runtime Runner Core

**Files:**
- Create: `src/visual_aiming/core/runtime_runner.py`
- Create: `tests/test_runtime_runner.py`

- [x] **Step 1: Write failing runner tests**

Create `tests/test_runtime_runner.py`:

```python
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.core.runtime_runner import RuntimeObserver, RuntimeRunner


class FakeFrameSource:
    def __init__(self, frames):
        self.frames = list(frames)
        self.closed = False

    def read(self):
        return self.frames.pop(0) if self.frames else None

    def close(self):
        self.closed = True


class FakePipeline:
    def __init__(self):
        self.frames = []

    def tick(self, frame, now=None):
        self.frames.append((frame, now))
        return {"frame": frame, "now": now}


class FakeObserver(RuntimeObserver):
    def __init__(self):
        self.events = []
        self.closed = False

    def on_tick(self, frame, result):
        self.events.append((frame, result))

    def close(self):
        self.closed = True


class RuntimeRunnerTests(unittest.TestCase):
    def test_run_until_source_returns_none(self):
        source = FakeFrameSource(["a", "b"])
        pipeline = FakePipeline()
        observer = FakeObserver()
        runner = RuntimeRunner(source, pipeline, observers=[observer], clock=lambda: 10.0)

        results = runner.run()

        self.assertEqual(results, [{"frame": "a", "now": 10.0}, {"frame": "b", "now": 10.0}])
        self.assertEqual(pipeline.frames, [("a", 10.0), ("b", 10.0)])
        self.assertEqual(observer.events, [("a", results[0]), ("b", results[1])])

    def test_run_once_returns_false_without_frame(self):
        source = FakeFrameSource([])
        pipeline = FakePipeline()
        runner = RuntimeRunner(source, pipeline, clock=lambda: 1.0)

        has_frame, result = runner.run_once()

        self.assertFalse(has_frame)
        self.assertIsNone(result)
        self.assertEqual(pipeline.frames, [])

    def test_close_closes_source_and_observer(self):
        source = FakeFrameSource([])
        pipeline = FakePipeline()
        observer = FakeObserver()
        runner = RuntimeRunner(source, pipeline, observers=[observer])

        runner.close()

        self.assertTrue(source.closed)
        self.assertTrue(observer.closed)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_runtime_runner -v
```

Expected: fail because `visual_aiming.core.runtime_runner` does not exist.

- [x] **Step 3: Implement runner**

Create `src/visual_aiming/core/runtime_runner.py`:

```python
from __future__ import annotations

import time
from typing import Callable, Iterable, Protocol


class RuntimeObserver(Protocol):
    def on_tick(self, frame, result) -> None:
        ...

    def close(self) -> None:
        ...


class RuntimeRunner:
    def __init__(
        self,
        frame_source,
        pipeline,
        observers: Iterable[RuntimeObserver] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.frame_source = frame_source
        self.pipeline = pipeline
        self.observers = list(observers or [])
        self.clock = clock or time.perf_counter

    def run_once(self):
        frame = self.frame_source.read()
        if frame is None:
            return False, None
        result = self.pipeline.tick(frame, now=self.clock())
        for observer in self.observers:
            observer.on_tick(frame, result)
        return True, result

    def run(self, max_frames: int | None = None):
        results = []
        while max_frames is None or len(results) < max_frames:
            has_frame, result = self.run_once()
            if not has_frame:
                break
            results.append(result)
        return results

    def close(self) -> None:
        for obj in [self.frame_source, *self.observers]:
            close = getattr(obj, "close", None)
            if close is not None:
                close()
```

- [x] **Step 4: Verify runner tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_runtime_runner -v
```

Expected: all tests pass.

- [x] **Step 5: Explain task result to user**

Explain:

```text
Task 1 完成：新增了唯一运行循环 RuntimeRunner。它不关心视频、屏幕、鼠标或 YOLO，只负责 frame_source.read() -> pipeline.tick() -> observer.on_tick()。这是后面让视频测试和实际运行复用同一逻辑的核心。
```

## Task 2: Replay Uses RuntimeRunner

**Files:**
- Modify: `src/visual_aiming/app/replay.py`
- Modify: `tests/test_modular_apps.py`
- Test: `tests/test_runtime_runner.py`

- [x] **Step 1: Add replay-level test**

Add this test to `tests/test_modular_apps.py`:

```python
    def test_replay_runner_uses_runtime_runner(self):
        from visual_aiming.app.replay import run_replay
        from visual_aiming.config.schema import ModularConfig

        class Source:
            def __init__(self):
                self.frames = ["one", "two"]

            def read(self):
                return self.frames.pop(0) if self.frames else None

        class Pipeline:
            def __init__(self):
                self.frames = []

            def tick(self, frame, now=None):
                self.frames.append(frame)
                return {"frame": frame}

        pipeline = Pipeline()
        results = run_replay(ModularConfig(), Source(), pipeline=pipeline)

        self.assertEqual(results, [{"frame": "one"}, {"frame": "two"}])
        self.assertEqual(pipeline.frames, ["one", "two"])
```

- [x] **Step 2: Run replay tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_apps -v
```

Expected: fail because `run_replay()` does not yet accept `pipeline=`.

- [x] **Step 3: Update replay implementation**

Modify `src/visual_aiming/app/replay.py` so `run_replay()` accepts an optional pipeline and delegates to `RuntimeRunner`:

```python
from visual_aiming.core.runtime_runner import RuntimeRunner


def run_replay(config, frame_source, detector=None, output_backend=None, diagnostics=None, pipeline=None):
    pipeline = pipeline or create_pipeline(
        config,
        detector=detector,
        output_backend=output_backend,
        diagnostics=diagnostics,
    )
    runner = RuntimeRunner(frame_source, pipeline)
    try:
        return runner.run()
    finally:
        runner.close()
```

Keep `run_video_file(config, video_path, roi_offset=(0, 0), crosshair=(0, 0))` calling `run_replay(config, source)`.

- [x] **Step 4: Verify replay tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_apps tests.test_runtime_runner -v
```

Expected: all tests pass.

- [x] **Step 5: Explain task result to user**

Explain:

```text
Task 2 完成：视频回放不再拥有自己的循环，而是调用 RuntimeRunner。视频回放现在已经走“唯一运行逻辑”的第一条路径。
```

## Task 3: Video Test Uses Runner Step

**Files:**
- Modify: `src/visual_aiming/app/video_test.py`
- Create or modify: `tests/test_video_test_runtime_runner.py`

- [x] **Step 1: Add video-test observer test**

Create `tests/test_video_test_runtime_runner.py`:

```python
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.app.video_test import VideoDebugObserver


class VideoDebugObserverTests(unittest.TestCase):
    def test_observer_records_latest_frame_and_result(self):
        observer = VideoDebugObserver()

        observer.on_tick("frame", {"seq": 1})

        self.assertEqual(observer.latest_frame, "frame")
        self.assertEqual(observer.latest_result, {"seq": 1})


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_video_test_runtime_runner -v
```

Expected: fail because `VideoDebugObserver` does not exist.

- [x] **Step 3: Add observer and route one-frame processing through runner**

In `src/visual_aiming/app/video_test.py`, add:

```python
class VideoDebugObserver:
    def __init__(self):
        self.latest_frame = None
        self.latest_result = None

    def on_tick(self, frame, result) -> None:
        self.latest_frame = frame
        self.latest_result = result

    def close(self) -> None:
        return None
```

Then replace direct per-frame `pipeline.tick(...)` calls with `RuntimeRunner(..., observers=[debug_observer]).run_once()` where video-test processes frames. Preserve existing overlay, keyboard, delay, and diagnostics behavior.

- [x] **Step 4: Verify video-test tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_video_test_runtime_runner tests.test_modular_apps -v
```

Expected: all tests pass.

- [x] **Step 5: Explain task result to user**

Explain:

```text
Task 3 完成：视频测试仍然保留调试界面，但帧处理不再是独立逻辑。它通过 RuntimeRunner 走和回放、实时相同的 frame -> pipeline.tick 路径。
```

## Task 4: Realtime Uses Same Runner

**Files:**
- Modify: `src/visual_aiming/app/realtime.py`
- Create: `tests/test_single_runtime_apps.py`
- Modify: `main.py`

- [x] **Step 1: Add realtime app test**

Create `tests/test_single_runtime_apps.py`:

```python
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.app.realtime import run_realtime
from visual_aiming.config.schema import ModularConfig


class Source:
    def __init__(self):
        self.frames = ["frame"]

    def read(self):
        return self.frames.pop(0) if self.frames else None


class Pipeline:
    def __init__(self):
        self.frames = []

    def tick(self, frame, now=None):
        self.frames.append(frame)
        return {"frame": frame}


class SingleRuntimeAppsTests(unittest.TestCase):
    def test_realtime_uses_same_runner_contract(self):
        pipeline = Pipeline()
        results = run_realtime(ModularConfig(), frame_source=Source(), pipeline=pipeline, max_frames=1)

        self.assertEqual(results, [{"frame": "frame"}])
        self.assertEqual(pipeline.frames, ["frame"])


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_single_runtime_apps -v
```

Expected: fail because `run_realtime()` is missing or does not accept `frame_source`, `pipeline`, and `max_frames`.

- [x] **Step 3: Implement realtime composition through RuntimeRunner**

Modify `src/visual_aiming/app/realtime.py`:

```python
from visual_aiming.adapters.frame_sources.screen_capture import ScreenFrameSource
from visual_aiming.core.runtime_runner import RuntimeRunner


def run_realtime(config, frame_source=None, detector=None, output_backend=None, diagnostics=None, pipeline=None, max_frames=None):
    frame_source = frame_source or ScreenFrameSource(config.frame)
    pipeline = pipeline or create_pipeline(
        config,
        frame_source=frame_source,
        detector=detector,
        output_backend=output_backend,
        diagnostics=diagnostics,
    )
    runner = RuntimeRunner(frame_source, pipeline)
    try:
        return runner.run(max_frames=max_frames)
    finally:
        runner.close()
```

Keep `create_pipeline()` and `create_output_backend()` behavior unchanged.

- [x] **Step 4: Route experimental modular realtime to this function**

In `main.py`, keep default behavior unchanged for this task, but when `RuntimeMode.MODULAR_REALTIME` is selected, call `run_realtime(config)` only under an explicit safe flag if that flag already exists. If no safe flag exists yet, keep legacy fallback and finish this task with tests only.

- [x] **Step 5: Verify realtime app tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_single_runtime_apps tests.test_modular_apps tests.test_runtime_modes -v
```

Expected: all tests pass.

- [x] **Step 6: Explain task result to user**

Explain:

```text
Task 4 完成：实时运行也有了同一套 RuntimeRunner 入口。到这里，视频回放、视频测试、实时运行都可以共享同一个运行循环；默认入口是否切换留到手动验证后决定。
```

## Task 5: Safe Default Switch to Single Runtime

**Files:**
- Modify: `main.py`
- Modify: `docs/runtime-convergence.md`
- Modify: `tests/test_runtime_modes.py`
- Modify: `tests/test_single_runtime_apps.py`

- [x] **Step 1: Add route expectation test**

Update `tests/test_runtime_modes.py` so default mode expectation becomes modular realtime:

```python
    def test_default_realtime_uses_modular_runtime(self):
        mode = choose_runtime_mode(self._args())
        self.assertEqual(mode, RuntimeMode.MODULAR_REALTIME)
```

Keep a separate escape hatch test:

```python
    def test_legacy_realtime_escape_hatch(self):
        mode = choose_runtime_mode(self._args(legacy_runtime=True))
        self.assertEqual(mode, RuntimeMode.LEGACY_REALTIME)
```

- [x] **Step 2: Run test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_runtime_modes -v
```

Expected: fail because default still returns `LEGACY_REALTIME` and parser/args do not yet include `legacy_runtime`.

- [x] **Step 3: Add temporary legacy escape hatch**

In `main.py`, add parser flag:

```python
parser.add_argument("--legacy-runtime", action="store_true", help="Temporary fallback to the old realtime runtime")
```

In `src/visual_aiming/core/runtime_modes.py`, update `choose_runtime_mode()`:

```python
if getattr(args, "legacy_runtime", False):
    return RuntimeMode.LEGACY_REALTIME
```

Change the final default:

```python
return RuntimeMode.MODULAR_REALTIME
```

- [x] **Step 4: Route default realtime to `run_realtime(config)`**

In `main.py`, let `RuntimeMode.MODULAR_REALTIME` call `_run_modular(args, mode=mode)`.

In `_run_modular`, replace legacy fallback with:

```python
if mode == RuntimeMode.MODULAR_REALTIME:
    from visual_aiming.app.realtime import run_realtime

    run_realtime(config)
    return 0
```

Keep `RuntimeMode.LEGACY_REALTIME` using `visual_aiming.core.runtime.main()` through the `--legacy-runtime` escape hatch.

- [x] **Step 5: Verify default route tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_runtime_modes tests.test_single_runtime_apps tests.test_modular_apps -v
```

Expected: all tests pass.

- [x] **Step 6: Manual safety check**

Run safe non-mouse commands first:

```powershell
.venv\Scripts\python.exe main.py --modular --video path\to\sample.mp4 --output null
.venv\Scripts\python.exe main.py --output null
```

Expected:

- Video replay processes frames without real mouse output.
- Realtime starts with `NullOutput` unless config or CLI explicitly enables real mouse output.

- [x] **Step 7: Explain task result to user**

Explain:

```text
Task 5 完成：默认实时入口已经切到模块化单 runtime。旧 runtime 只剩 --legacy-runtime 逃生入口，下一阶段验证通过后删除。
```

## Task 6: Delete Legacy Runtime Path

**Files:**
- Delete: `src/visual_aiming/core/runtime.py`
- Delete: `src/visual_aiming/core/runtime_services.py`
- Delete: `src/visual_aiming/core/runtime_state.py`
- Delete or reduce: `tests/test_runtime_pipeline.py`
- Modify: `src/visual_aiming/core/pipeline.py`
- Modify: `src/visual_aiming/core/schemas.py`
- Modify: `src/visual_aiming/core/runtime_modes.py`
- Modify: `src/visual_aiming/core/__init__.py`
- Modify: `main.py`
- Modify: `docs/runtime-convergence.md`

- [x] **Step 1: Search legacy references**

Run:

```powershell
rg "visual_aiming.core.runtime|RuntimePipeline|--legacy-runtime|legacy_main" main.py src tests docs
```

Expected: references remain only in the old files and tests scheduled for deletion.

- [x] **Step 2: Delete old runtime file**

Delete `src/visual_aiming/core/runtime.py`.

- [x] **Step 3: Remove `RuntimePipeline` if no production code imports it**

In `src/visual_aiming/core/pipeline.py`, delete the `RuntimePipeline` class only after `rg "RuntimePipeline" src tests` shows it is no longer used by production code.

- [x] **Step 4: Remove legacy escape hatch**

In `main.py`, remove `--legacy-runtime`.

In `src/visual_aiming/core/runtime_modes.py`, remove `LEGACY_REALTIME` if no tests or production code need it.

- [x] **Step 5: Replace old tests**

Delete old-runtime tests that only validate `RuntimePipeline`.

Keep tests that validate shared schemas, `ModularPipeline`, adapters, output safety, and `RuntimeRunner`.

- [x] **Step 6: Verify no legacy references**

Run:

```powershell
rg "visual_aiming.core.runtime|RuntimePipeline|legacy_main|LEGACY_REALTIME" main.py src tests docs
```

Expected: no production references. Documentation may mention the removed path only in a migration note.

- [x] **Step 7: Run full verification**

Run:

```powershell
.venv\Scripts\python.exe -m unittest discover tests -v
.venv\Scripts\python.exe -m compileall -q src tests scripts main.py
git diff --check
```

Expected:

- `unittest` passes.
- `compileall` returns no output.
- `git diff --check` returns no whitespace errors.

- [x] **Step 8: Explain task result to user**

Explain:

```text
Task 6 完成：旧实时 runtime 已删除，程序只剩一套运行逻辑。视频测试、视频回放、实时运行都通过 RuntimeRunner + ModularPipeline，只替换输入源、输出端和调试观察层。
```

## Task 7: Repository Cleanup After Single Runtime

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`
- Modify or archive: `docs/runtime-convergence.md`
- Delete after audit: generated artifacts, old root scripts, obsolete docs, obsolete tests, obsolete packaging output, obsolete IDE files

- [x] **Step 1: Generate cleanup inventory**

Run:

```powershell
.venv\Scripts\python.exe - <<'PY'
from pathlib import Path
root = Path(".")
skip = {".git", ".venv"}
entries = []
for path in sorted(root.iterdir(), key=lambda p: p.name.lower()):
    if path.name in skip:
        continue
    if path.is_dir():
        count = sum(1 for p in path.rglob("*") if p.is_file())
        entries.append((path.name + "/", "dir", count))
    else:
        entries.append((path.name, "file", 1))
for name, kind, count in entries:
    print(f"{kind:4} {count:5} {name}")
PY
```

Expected: a root-level inventory that includes generated folders such as `build/`, `dist/`, `logs/`, and root scripts such as `mouse.py` or `test.py` if they still exist.

- [x] **Step 2: Audit references before deletion**

Run:

```powershell
rg "mouse.py|test.py|RuntimePipeline|visual_aiming.core.runtime|build/|dist/|logs/" README.md docs src tests scripts packaging main.py
```

Expected:

- `RuntimePipeline` and `visual_aiming.core.runtime` have no production references after Task 6.
- `mouse.py` and `test.py` are either unreferenced or documented as obsolete.
- `build/`, `dist/`, and `logs/` are not required as tracked runtime inputs.

- [x] **Step 3: Remove generated artifacts from workspace**

Delete generated folders if they exist:

```powershell
Remove-Item -Recurse -Force -LiteralPath build, dist, logs, __pycache__ -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -Include *.pyc,*.pyo | Remove-Item -Force
```

Expected:

- Generated build output, runtime logs, and Python cache files are gone from the working tree.
- `.gitignore` still contains:

```text
__pycache__/
*.py[cod]
/logs/
build/
dist/
.idea/
.vscode/
```

- [x] **Step 4: Delete obsolete root scripts after reference audit**

If Step 2 shows no valid references, delete:

```powershell
Remove-Item -LiteralPath mouse.py, test.py -ErrorAction SilentlyContinue
```

If either file still has a valid purpose, move its useful code into `scripts/` or `tests/` first, then delete the root file.

Expected:

- Root directory keeps `main.py` as the only executable entry script.
- One-off experimental files no longer live at repository root.

- [x] **Step 5: Prune obsolete docs and plans**

Review `docs/superpowers/plans/` and `docs/superpowers/specs/`.

Keep:

- the current single-runtime plan
- the mouse angular-control plan
- design/spec files that describe still-valid architecture

Archive or delete documents that only describe removed legacy runtime behavior. If a document has useful historical context, move it under:

```text
docs/archive/
```

Expected:

- Active docs describe the current single-runtime architecture.
- Historical docs are not mixed with active implementation plans.

- [x] **Step 6: Prune obsolete tests**

Run:

```powershell
rg "RuntimePipeline|visual_aiming.core.runtime|MouseController realtime loop|legacy runtime" tests
```

Delete tests that only validate deleted runtime internals.

Keep tests that validate:

- `RuntimeRunner`
- `ModularPipeline`
- frame-source adapters
- output adapters
- config schema
- video-test diagnostics
- mouse sender/output safety

Expected: tests exercise the single runtime architecture rather than deleted legacy internals.

- [x] **Step 7: Update README root layout**

Update `README.md` with the post-cleanup layout:

```markdown
## Project Layout

- `main.py` - CLI entrypoint.
- `src/visual_aiming/core/runtime_runner.py` - single runtime loop.
- `src/visual_aiming/core/pipeline.py` - modular aiming pipeline.
- `src/visual_aiming/adapters/frame_sources/` - screen and video input sources.
- `src/visual_aiming/adapters/outputs/` - null, log, and mouse outputs.
- `src/visual_aiming/app/` - realtime, replay, video-test compositions.
- `scripts/` - diagnostic and calibration utilities.
- `tests/` - unit tests for the single runtime architecture.
```

Expected: README no longer describes removed legacy runtime files as active architecture.

- [x] **Step 8: Verify cleanup**

Run:

```powershell
git status --short
.venv\Scripts\python.exe -m unittest discover tests -v
.venv\Scripts\python.exe -m compileall -q src tests scripts main.py
git diff --check
rg "visual_aiming.core.runtime|RuntimePipeline|legacy_main" main.py src tests
```

Expected:

- `git status --short` shows intended deletions/updates only.
- Test suite passes.
- Compile check passes.
- Whitespace check passes.
- Legacy runtime symbols are absent from production and test code.

- [x] **Step 9: Explain task result to user**

Explain:

```text
Task 7 完成：仓库完成统一 runtime 后清理。生成物、旧根目录脚本、过时文档、过时测试和打包输出已经删除或归档；README 描述现在的单运行流程结构。保留模型、用户配置和仍有引用的有效测试资产。
```

## Commit Guidance

Commit by phase:

```powershell
git add src/visual_aiming/core/runtime_runner.py tests/test_runtime_runner.py
git commit -m "新增统一运行循环"

git add src/visual_aiming/app/replay.py src/visual_aiming/app/video_test.py tests/test_modular_apps.py tests/test_video_test_runtime_runner.py
git commit -m "让视频路径复用统一运行循环"

git add src/visual_aiming/app/realtime.py tests/test_single_runtime_apps.py main.py src/visual_aiming/core/runtime_modes.py
git commit -m "让实时路径复用统一运行循环"

git add main.py src/visual_aiming/core/runtime_modes.py docs/runtime-convergence.md tests/test_runtime_modes.py
git commit -m "切换默认入口到统一运行逻辑"

git add -A src/visual_aiming/core tests docs main.py
git commit -m "删除旧实时运行路径"

git add -A .gitignore README.md docs tests src scripts packaging main.py mouse.py test.py
git commit -m "清理统一运行逻辑后的冗余文件"
```

Do not include `config.json` unless the user explicitly requests it.

## Final Verification

Before reporting the full migration complete, run:

```powershell
.venv\Scripts\python.exe -m unittest discover tests -v
.venv\Scripts\python.exe -m compileall -q src tests scripts main.py
git diff --check
rg "visual_aiming.core.runtime|RuntimePipeline|legacy_main" main.py src tests
```

Expected:

- Test suite passes.
- Compile check passes.
- Whitespace check passes.
- Legacy runtime symbols are absent from production code.
- Root directory contains only active project files, with generated output ignored or removed.
