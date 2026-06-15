# Runtime README Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current MVP match the README promise: `python main.py` loads the YOLO model, captures the ROI, detects targets, keeps hotkey behavior, and drives real relative mouse movement while separating high-frequency vision from low-frequency smooth control.

**Architecture:** Keep the existing `vision / core / actions` layers. Do not add a plugin loader in this pass. Tighten boundaries so the later plugin shape can become `VisionPlugin.process(frame) -> DetectionState` and `OutputPlugin.apply(ControlTarget)` without another broad rewrite.

---

## File Structure

- Modify `src/visual_aiming/common/resource_path.py`: resolve development resources from the project root, not `src`.
- Modify `src/visual_aiming/vision/detection.py`: store and log the actual resolved model path; keep CUDA preference and CPU fallback explicit.
- Modify `src/visual_aiming/core/runtime.py`: keep detection scheduling and control target updates clear; avoid stale-frame detection when configured.
- Modify `src/visual_aiming/actions/mouse_control.py`: keep the sandbox-proven controller as production logic.
- Create `scripts/mouse_gain_probe.py`: provide the manual mouse delta probe required by the existing tests.
- Modify `README.md`: align docs with the current MVP and remaining limitations.
- Tests: `tests/test_detector_device.py`, `tests/test_mouse_gain_probe.py`, `tests/test_mouse_controller.py`, `tests/test_runtime_pipeline.py`.

## Task 1: Stabilize Resource and Model Path Resolution

**Files:**
- Modify: `src/visual_aiming/common/resource_path.py`
- Modify: `src/visual_aiming/vision/detection.py`
- Test: `tests/test_detector_device.py`

- [x] **Step 1: Add path tests**

Add tests that verify `resource_path("models/best.pt")` resolves under the project root in development and that `TargetDetector.load_model()` records the resolved path when YOLO is mocked.

- [x] **Step 2: Run tests red**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_detector_device -v`

Expected before implementation: development path may point under `src`.

- [x] **Step 3: Implement path resolution**

Use `Path(__file__).resolve().parents[3]` for development mode from `src/visual_aiming/common/resource_path.py`. Preserve `sys._MEIPASS` for packaged mode.

- [x] **Step 4: Run tests green**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_detector_device -v`

## Task 2: Restore Full Test Suite by Adding Mouse Gain Probe

**Files:**
- Create: `scripts/mouse_gain_probe.py`
- Test: `tests/test_mouse_gain_probe.py`

- [x] **Step 1: Use existing failing tests**

Current failing tests already define the API:

```python
build_move_sequence(dx, dy, count) -> list[tuple[int, int]]
ProbeArgs(dx, dy, count, delay, interval)
run_probe(args, sender, sleeper, cursor_reader, verify_cursor, printer)
select_sender(name)
```

- [x] **Step 2: Implement minimal probe**

Implement a small script that can be imported by tests and run manually from the command line. Supported backends should include at least `ctypes`; unknown backend raises `ValueError`.

- [x] **Step 3: Run tests green**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_mouse_gain_probe -v`

## Task 3: Tighten Vision-Control Frequency Boundary

**Files:**
- Modify: `src/visual_aiming/core/runtime.py`
- Modify if needed: `src/visual_aiming/core/pipeline.py`
- Test: `tests/test_runtime_pipeline.py`

- [x] **Step 1: Confirm stale-frame behavior with tests**

Add or update tests so inactive runtime produces no control target, fresh detection produces a control target, and `current_control()` can reuse the latest aim point for the low-frequency servo loop without requiring a new YOLO frame.

- [x] **Step 2: Keep runtime loop small**

Ensure runtime performs these steps only:

```text
read input state
fetch latest capture frame
run YOLO only when scheduler says so and frame is fresh enough
update pipeline latest target
publish latest control target to MouseController
update debug UI
sleep for poll interval
```

- [x] **Step 3: Run pipeline tests**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_runtime_pipeline -v`

## Task 4: Keep Sandbox Mouse Logic as Production Control

**Files:**
- Modify: `src/visual_aiming/actions/mouse_control.py`
- Test: `tests/test_mouse_controller.py`

- [x] **Step 1: Preserve sandbox parity tests**

Keep production `_compute_move()` matched to `tests/test_mouse_controller.py::compute_cursor_step` for the first-step movement.

- [x] **Step 2: Remove or neutralize obsolete behavior**

Do not reintroduce old overshoot guard, random angular jitter, or measurement blending unless explicitly wired to a current UI control and tested.

- [x] **Step 3: Run mouse tests**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_mouse_controller -v`

## Task 5: Align README and Config Surface

**Files:**
- Modify: `README.md`
- Inspect: `config.json`
- Inspect: `src/visual_aiming/actions/config_window.py`

- [x] **Step 1: Update README architecture**

Document the current MVP as high-frequency capture/detection updates plus independent servo-loop mouse output.

- [x] **Step 2: Update known limitations**

Replace stale “待优化” items with current status and remaining limitations: manual Windows/admin verification, CUDA availability, model path, and later plugin loader not implemented yet.

- [x] **Step 3: Keep config values compatible**

Do not remove existing config keys in this pass unless tests prove they are dead and removal is safe.

## Task 6: Final Verification

**Files:**
- All touched files

- [x] **Step 1: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_detector_device tests.test_mouse_gain_probe tests.test_mouse_controller tests.test_runtime_pipeline tests.test_config_window_sections -v
```

- [x] **Step 2: Run full tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

- [x] **Step 3: Compile**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall src tests scripts main.py
```

- [x] **Step 4: Import startup**

Run:

```powershell
.\.venv\Scripts\python.exe -c "import main; print(main.main.__module__)"
```

- [ ] **Step 5: Manual runtime checklist**

User runs:

```powershell
.\.venv\Scripts\python.exe main.py
```

Expected: model path exists, CUDA/CPU runtime logs appear, ROI capture starts, hotkeys toggle active state, and mouse movement follows detected targets.
