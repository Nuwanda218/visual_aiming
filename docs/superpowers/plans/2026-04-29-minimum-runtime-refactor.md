# Minimum Runtime Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the runtime into clear three-layer boundaries while keeping `python main.py` fully runnable with YOLO, ROI capture, hotkeys, and real mouse movement.

**Architecture:** Keep `vision / core / actions`. Add pure core schemas, runtime state, services, and pipeline objects so high-frequency vision updates are separated from low-frequency mouse control sampling. Preserve existing detector and mouse algorithms unless a small adapter is needed.

**Tech Stack:** Python 3, stdlib `unittest`, YOLOv8 via `ultralytics`, OpenCV, MSS, pynput, Tkinter, Windows mouse APIs.

---

## File Structure

- Create `src/visual_aiming/core/schemas.py`: shared dataclasses for frame, detection, control, and debug state.
- Create `src/visual_aiming/core/runtime_state.py`: mutable runtime state and firing transition helpers.
- Create `src/visual_aiming/core/pipeline.py`: transform detector output into `ControlTarget`.
- Create `src/visual_aiming/core/runtime_services.py`: construct and clean up capture, detector, input, mouse, UI, debug, scheduler, and pipeline services.
- Modify `src/visual_aiming/core/runtime.py`: keep startup, loop timing, lifecycle, and shutdown only.
- Modify `src/visual_aiming/actions/config_window.py`: expose focused performance/GPU/control groups, including `yolo_device` and `yolo_half`.
- Create `tests/test_runtime_pipeline.py`: pure pipeline and state tests.
- Create `tests/test_config_window_sections.py`: config UI section coverage tests.
- Create `tests/test_detector_device.py`: CUDA/CPU device resolution tests without loading YOLO.

## Task 1: Add Core Schemas and State

**Files:**
- Create: `src/visual_aiming/core/schemas.py`
- Create: `src/visual_aiming/core/runtime_state.py`
- Test: `tests/test_runtime_pipeline.py`

- [ ] **Step 1: Write failing tests**

Create tests that import `RuntimeState`, call `reset_tracking_state()`, `update_firing()`, and verify state changes:

```python
import unittest

from visual_aiming.core.runtime_state import RuntimeState


class RuntimeStateTest(unittest.TestCase):
    def test_reset_tracking_state_clears_runtime_targets(self):
        state = RuntimeState(firing=True, last_aim_base=(10, 20), last_capture_seq=7)

        state.reset_tracking_state()

        self.assertFalse(state.firing)
        self.assertIsNone(state.last_aim_base)
        self.assertEqual(state.last_capture_seq, -1)

    def test_update_firing_reports_transitions(self):
        state = RuntimeState()

        self.assertEqual(state.update_firing(True), "started")
        self.assertTrue(state.firing)
        self.assertEqual(state.update_firing(True), "unchanged")
        self.assertEqual(state.update_firing(False), "stopped")
        self.assertFalse(state.firing)
```

- [ ] **Step 2: Run tests to verify red**

Run: `python -m unittest tests.test_runtime_pipeline -v`

Expected: import failure for `visual_aiming.core.runtime_state`.

- [ ] **Step 3: Implement minimal schemas and state**

Add dataclasses:

```python
@dataclass
class RuntimeState:
    firing: bool = False
    last_aim_base: Optional[Point] = None
    last_capture_seq: int = -1

    def reset_tracking_state(self) -> None: ...
    def update_firing(self, left_held: bool) -> str: ...
```

- [ ] **Step 4: Run tests to verify green**

Run: `python -m unittest tests.test_runtime_pipeline -v`

Expected: 2 tests pass.

## Task 2: Add Runtime Pipeline

**Files:**
- Modify: `tests/test_runtime_pipeline.py`
- Create: `src/visual_aiming/core/pipeline.py`

- [ ] **Step 1: Write failing pipeline tests**

Add tests using fake aim calculator and fake tracker:

```python
class FakeAimCalculator:
    def __init__(self, result):
        self.result = result

    def calculate(self, target, roi_left, roi_top):
        return self.result


class RuntimePipelineTest(unittest.TestCase):
    def test_inactive_pipeline_returns_empty_control(self):
        pipeline = RuntimePipeline(config=object(), aim_calculator=FakeAimCalculator((100, 100)), tracker=None)

        result = pipeline.process_detection(
            active=False,
            firing=False,
            target=object(),
            target_is_fresh=True,
            roi_offset=(0, 0),
            crosshair=(50, 50),
            now=1.0,
        )

        self.assertIsNone(result.control.target)
        self.assertFalse(result.control.has_measurement)

    def test_active_fresh_detection_returns_control_target(self):
        pipeline = RuntimePipeline(config=object(), aim_calculator=FakeAimCalculator((100, 100)), tracker=None)

        result = pipeline.process_detection(
            active=True,
            firing=False,
            target=object(),
            target_is_fresh=True,
            roi_offset=(0, 0),
            crosshair=(50, 50),
            now=1.0,
        )

        self.assertEqual(result.control.target, (100, 100))
        self.assertTrue(result.control.has_measurement)
```

- [ ] **Step 2: Run tests to verify red**

Run: `python -m unittest tests.test_runtime_pipeline -v`

Expected: import failure for `visual_aiming.core.pipeline`.

- [ ] **Step 3: Implement `RuntimePipeline`**

Move the pure target decision logic out of `runtime.py`: aim calculation, fresh measurement detection, tracker update/predict, last aim fallback, and `ControlTarget`.

- [ ] **Step 4: Run tests to verify green**

Run: `python -m unittest tests.test_runtime_pipeline -v`

Expected: pipeline and state tests pass.

## Task 3: Add Runtime Services

**Files:**
- Create: `src/visual_aiming/core/runtime_services.py`
- Modify: `src/visual_aiming/core/runtime.py`

- [ ] **Step 1: Implement service construction**

Create `RuntimeServices.create(config, config_path="config.json")` to build wakeup, capture worker or screen capture, detector, aim calculator, tracker, mouse controller, throttle, detection scheduler, config window, debug visualizer, and pipeline.

- [ ] **Step 2: Implement cleanup**

Create `RuntimeServices.stop()` that stops mouse controller, config window, capture worker or screen capture, wakeup listener, debug visualizer, and OpenCV windows in a stable order.

- [ ] **Step 3: Run import check**

Run: `python -c "from visual_aiming.core.runtime_services import RuntimeServices; print(RuntimeServices)"`

Expected: prints the class object without import errors.

## Task 4: Rewrite Runtime Loop Around Services and Pipeline

**Files:**
- Modify: `src/visual_aiming/core/runtime.py`

- [ ] **Step 1: Replace inline service setup**

Keep admin elevation, config load/save, monitor size calculation, and startup logs. Move object construction to `RuntimeServices.create()`.

- [ ] **Step 2: Replace inline target decision block**

Use `RuntimePipeline.process_detection()` when a new frame is detected. Feed the returned `ControlTarget` to `MouseController.update_target()`.

- [ ] **Step 3: Preserve behavior**

Keep existing active reset, firing start/stop logs, detection scheduler, throttle, debug visualizer update, and fallback to crosshair/cursor when no target exists.

- [ ] **Step 4: Run import check**

Run: `python -m py_compile main.py src/visual_aiming/core/runtime.py src/visual_aiming/core/pipeline.py src/visual_aiming/core/runtime_services.py`

Expected: command exits 0.

## Task 5: Focus Config UI Sections

**Files:**
- Modify: `src/visual_aiming/actions/config_window.py`
- Test: `tests/test_config_window_sections.py`

- [ ] **Step 1: Write failing section tests**

Test that `_sections()` includes `核心性能`, `模型/GPU`, `控制平滑`, and advanced groups, and exposes `yolo_device`, `yolo_half`, `servo_loop_hz`, `detect_fps`, and `capture_fps`.

- [ ] **Step 2: Run tests to verify red**

Run: `python -m unittest tests.test_config_window_sections -v`

Expected: fails because sections do not include `模型/GPU` and no editable `yolo_device`.

- [ ] **Step 3: Add string/choice UI support**

Add `ChoiceSpec` and `_add_choice_row()` with a `ttk.Combobox` for `yolo_device` values `auto`, `cuda`, and `cpu`. Keep `BoolSpec` for `yolo_half`.

- [ ] **Step 4: Reorder `_sections()`**

Expose focused groups first: `核心性能`, `模型/GPU`, `控制平滑`, `目标行为`, then keep detailed groups for advanced tuning.

- [ ] **Step 5: Run tests to verify green**

Run: `python -m unittest tests.test_config_window_sections -v`

Expected: tests pass.

## Task 6: Verify CUDA Device Resolution

**Files:**
- Test: `tests/test_detector_device.py`

- [ ] **Step 1: Write device resolution tests**

Patch `visual_aiming.vision.detection.torch.cuda.is_available` and assert:

- `auto` returns `cuda:0` when CUDA is available.
- `auto` returns `cpu` when CUDA is unavailable.
- `cuda` falls back to `cpu` when CUDA is unavailable.
- half precision only returns true on CUDA runtime.

- [ ] **Step 2: Run tests**

Run: `python -m unittest tests.test_detector_device -v`

Expected: tests pass because current detector already has this behavior.

## Task 7: Final Verification

**Files:**
- All modified source and tests.

- [ ] **Step 1: Run all unit tests**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 2: Compile source**

Run: `python -m compileall main.py src tests`

Expected: no syntax errors.

- [ ] **Step 3: Check git diff**

Run: `git diff --stat` and `git status --short`

Expected: only planned files changed plus the pre-existing untracked `test.py`.

