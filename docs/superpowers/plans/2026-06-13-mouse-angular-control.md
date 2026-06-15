# Mouse Angular Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ad-hoc screen-pixel-to-mouse-output tuning with an explicit, testable mapping from screen pixel error to game-view angular error to mouse input counts.

**Architecture:** Keep target detection, target selection, prediction, and controller state separate from output mapping. Add a pure mapper that converts screen-space error into angular error and then into SendInput counts. Integrate it behind configuration so the current pixel-based behavior remains the default until calibrated.

**Tech Stack:** Python standard library, `math`, existing `unittest` test suite, existing legacy `MouseController`, existing modular `RelativeController`, existing `mouse_gain_probe.py` and `mouse_diagnostics` logs.

---

## Current Facts And Decisions

These facts came from manual testing and recent logs. Do not re-litigate them without new evidence:

- `sendinput` works on the desktop and can move the mouse inside the game when run with sufficient privileges.
- The old feeling that "the mouse does not move" was partly caused by the game interpreting mouse input as camera rotation, not desktop pixel movement.
- Desktop cursor delta and in-game view delta are not the same unit.
- The correct mental model is:

```text
screen target offset px
-> angular error relative to camera view
-> mouse input counts
-> game camera rotates on a sphere
-> new projection changes screen target offset
```

- Short-term scalar gain can still be useful, but it must not be confused with the controller algorithm itself.
- Mouse work is intentionally paused until this plan is selected for implementation. Continue non-mouse work unless the user asks to execute this plan.

## Non-Goals

- Do not change detection, target selection, or prediction in this plan.
- Do not add anti-cheat bypasses or kernel/input-driver methods.
- Do not assume one universal game sensitivity formula.
- Do not remove the current pixel controller until angular mode is tested and comparable.

## File Structure

- Create: `src/visual_aiming/algorithms/input_mapping.py`
  - Pure functions/classes for pixel error -> angular error -> mouse counts.
  - No Windows API calls.
- Modify: `src/visual_aiming/config/schema.py`
  - Add modular mapper config fields.
- Modify: `src/visual_aiming/config/loader.py`
  - Map legacy flat `config.json` keys into modular mapper config.
- Modify: `src/visual_aiming/config/__init__.py`
  - Add legacy runtime config keys for angular mapping.
- Modify: `src/visual_aiming/algorithms/control.py`
  - Allow `RelativeController` to optionally pass pixel error through the mapper before servo integration.
- Modify: `src/visual_aiming/actions/mouse_control.py`
  - Use the same mapper in legacy realtime control when angular mapping is enabled.
- Modify: `src/visual_aiming/actions/config_window.py`
  - Expose mapping mode and calibration values under `输出测试` or a dedicated `高级-输入映射` section.
- Modify: `scripts/mouse_gain_probe.py`
  - Add optional repeated calibration sequences for X/Y counts.
- Modify: `docs/debug-workflow.md`
  - Document calibration workflow and how to interpret results.
- Test: `tests/test_input_mapping.py`
  - Unit tests for projection math and count conversion.
- Test: `tests/test_modular_algorithms.py`
  - Controller integration tests.
- Test: `tests/test_mouse_control.py`
  - Legacy controller integration tests.
- Test: `tests/test_config_window_sections.py`
  - UI exposure tests.
- Test: `tests/test_modular_schemas_config.py`
  - Config loader mapping tests.

---

### Task 1: Add Pure Angular Input Mapper

**Files:**
- Create: `src/visual_aiming/algorithms/input_mapping.py`
- Test: `tests/test_input_mapping.py`

- [ ] **Step 1: Write failing tests for pixel-to-angle conversion**

Create `tests/test_input_mapping.py`:

```python
import math
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


class InputMappingTest(unittest.TestCase):
    def test_pixel_error_to_angle_uses_camera_projection(self):
        from visual_aiming.algorithms.input_mapping import ProjectionConfig, pixel_error_to_degrees

        config = ProjectionConfig(width_px=1920, height_px=1080, horizontal_fov_deg=90.0)

        angle_x, angle_y = pixel_error_to_degrees((960.0, 0.0), config)

        self.assertAlmostEqual(angle_x, 45.0, places=3)
        self.assertAlmostEqual(angle_y, 0.0, places=3)

    def test_vertical_fov_is_derived_from_aspect_ratio(self):
        from visual_aiming.algorithms.input_mapping import ProjectionConfig, pixel_error_to_degrees

        config = ProjectionConfig(width_px=1920, height_px=1080, horizontal_fov_deg=90.0)

        _angle_x, angle_y = pixel_error_to_degrees((0.0, 540.0), config)

        expected_vertical_fov = math.degrees(2.0 * math.atan(math.tan(math.radians(90.0) / 2.0) * 1080 / 1920))
        self.assertAlmostEqual(angle_y, expected_vertical_fov / 2.0, places=3)

    def test_degrees_to_counts_applies_axis_calibration(self):
        from visual_aiming.algorithms.input_mapping import MouseCalibration, degrees_to_counts

        calibration = MouseCalibration(counts_per_degree_x=12.0, counts_per_degree_y=16.0)

        dx, dy = degrees_to_counts((2.5, -1.25), calibration)

        self.assertEqual((dx, dy), (30, -20))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_input_mapping -v
```

Expected: FAIL with `ModuleNotFoundError` for `visual_aiming.algorithms.input_mapping`.

- [ ] **Step 3: Implement pure mapper**

Create `src/visual_aiming/algorithms/input_mapping.py`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

Vector = Tuple[float, float]


@dataclass(frozen=True)
class ProjectionConfig:
    width_px: int
    height_px: int
    horizontal_fov_deg: float
    vertical_fov_deg: float | None = None


@dataclass(frozen=True)
class MouseCalibration:
    counts_per_degree_x: float = 1.0
    counts_per_degree_y: float = 1.0


def vertical_fov_from_horizontal(horizontal_fov_deg: float, width_px: int, height_px: int) -> float:
    half_h = math.radians(horizontal_fov_deg) / 2.0
    half_v = math.atan(math.tan(half_h) * float(height_px) / float(width_px))
    return math.degrees(half_v * 2.0)


def focal_px_from_fov(size_px: int, fov_deg: float) -> float:
    return float(size_px) / (2.0 * math.tan(math.radians(fov_deg) / 2.0))


def pixel_error_to_degrees(error_px: Vector, config: ProjectionConfig) -> Vector:
    horizontal_fov = max(1.0, min(179.0, float(config.horizontal_fov_deg)))
    vertical_fov = config.vertical_fov_deg
    if vertical_fov is None:
        vertical_fov = vertical_fov_from_horizontal(horizontal_fov, config.width_px, config.height_px)
    vertical_fov = max(1.0, min(179.0, float(vertical_fov)))

    focal_x = focal_px_from_fov(config.width_px, horizontal_fov)
    focal_y = focal_px_from_fov(config.height_px, vertical_fov)

    angle_x = math.degrees(math.atan(float(error_px[0]) / focal_x))
    angle_y = math.degrees(math.atan(float(error_px[1]) / focal_y))
    return (angle_x, angle_y)


def degrees_to_counts(angle_deg: Vector, calibration: MouseCalibration) -> tuple[int, int]:
    dx = int(round(float(angle_deg[0]) * float(calibration.counts_per_degree_x)))
    dy = int(round(float(angle_deg[1]) * float(calibration.counts_per_degree_y)))
    return (dx, dy)


class AngularInputMapper:
    def __init__(self, projection: ProjectionConfig, calibration: MouseCalibration) -> None:
        self.projection = projection
        self.calibration = calibration

    def map_error(self, error_px: Vector) -> tuple[int, int]:
        angle = pixel_error_to_degrees(error_px, self.projection)
        return degrees_to_counts(angle, self.calibration)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_input_mapping -v
```

Expected: PASS.

---

### Task 2: Add Configuration For Mapping Mode

**Files:**
- Modify: `src/visual_aiming/config/schema.py`
- Modify: `src/visual_aiming/config/loader.py`
- Modify: `src/visual_aiming/config/__init__.py`
- Test: `tests/test_modular_schemas_config.py`

- [ ] **Step 1: Write failing config tests**

In `tests/test_modular_schemas_config.py`, add assertions to `test_default_config_uses_safe_output`:

```python
self.assertEqual(config.control.input_mapping_mode, "pixel")
self.assertEqual(config.control.horizontal_fov_deg, 90.0)
self.assertEqual(config.control.counts_per_degree_x, 1.0)
self.assertEqual(config.control.counts_per_degree_y, 1.0)
```

In `test_legacy_flat_config_maps_to_grouped_config`, add input data:

```python
"mouse_input_mapping_mode": "angular",
"mouse_horizontal_fov_deg": 103.0,
"mouse_counts_per_degree_x": 14.5,
"mouse_counts_per_degree_y": 18.0,
```

Then add assertions:

```python
self.assertEqual(config.control.input_mapping_mode, "angular")
self.assertEqual(config.control.horizontal_fov_deg, 103.0)
self.assertEqual(config.control.counts_per_degree_x, 14.5)
self.assertEqual(config.control.counts_per_degree_y, 18.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_schemas_config -v
```

Expected: FAIL because `ControlConfig` has no mapping fields.

- [ ] **Step 3: Add modular config fields**

In `src/visual_aiming/config/schema.py`, extend `ControlConfig`:

```python
input_mapping_mode: str = "pixel"
horizontal_fov_deg: float = 90.0
vertical_fov_deg: float = 0.0
counts_per_degree_x: float = 1.0
counts_per_degree_y: float = 1.0
```

Use `vertical_fov_deg=0.0` to mean "derive from horizontal FOV and aspect ratio".

- [ ] **Step 4: Add legacy config defaults**

In `src/visual_aiming/config/__init__.py`, add fields near mouse settings:

```python
mouse_input_mapping_mode: str = "pixel"
mouse_horizontal_fov_deg: float = 90.0
mouse_vertical_fov_deg: float = 0.0
mouse_counts_per_degree_x: float = 1.0
mouse_counts_per_degree_y: float = 1.0
```

- [ ] **Step 5: Map flat config into modular config**

In `src/visual_aiming/config/loader.py`, after control gain mapping, add:

```python
config.control.input_mapping_mode = str(data.get("mouse_input_mapping_mode", config.control.input_mapping_mode))
config.control.horizontal_fov_deg = float(data.get("mouse_horizontal_fov_deg", config.control.horizontal_fov_deg))
config.control.vertical_fov_deg = float(data.get("mouse_vertical_fov_deg", config.control.vertical_fov_deg))
config.control.counts_per_degree_x = float(data.get("mouse_counts_per_degree_x", config.control.counts_per_degree_x))
config.control.counts_per_degree_y = float(data.get("mouse_counts_per_degree_y", config.control.counts_per_degree_y))
```

- [ ] **Step 6: Run tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_schemas_config -v
```

Expected: PASS.

---

### Task 3: Integrate Mapper Into Modular RelativeController

**Files:**
- Modify: `src/visual_aiming/algorithms/control.py`
- Test: `tests/test_modular_algorithms.py`

- [ ] **Step 1: Write failing controller tests**

In `tests/test_modular_algorithms.py`, add:

```python
def test_controller_uses_angular_mapping_when_enabled(self):
    from visual_aiming.algorithms.control import RelativeController
    from visual_aiming.config.schema import ControlConfig

    config = ControlConfig(
        deadzone=0.0,
        speed_gain=1.0,
        max_speed=10000.0,
        acceleration=1000.0,
        decel_radius=1.0,
        near_speed_scale=1.0,
        max_step=10000,
        output_gain=1.0,
        input_mapping_mode="angular",
        horizontal_fov_deg=90.0,
        counts_per_degree_x=10.0,
        counts_per_degree_y=10.0,
    )
    controller = RelativeController(config, roi_size=(1920, 1080))

    command = controller.update((960.0, 0.0), active=True, dt=1.0)

    self.assertEqual(command.mode, "relative")
    self.assertEqual(command.reason, "tracking")
    self.assertEqual(command.dx, 450)
    self.assertEqual(command.dy, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_algorithms -v
```

Expected: FAIL because `RelativeController.__init__` does not accept `roi_size` and does not use angular mapping.

- [ ] **Step 3: Update controller constructor**

In `src/visual_aiming/algorithms/control.py`, import mapper types:

```python
from visual_aiming.algorithms.input_mapping import AngularInputMapper, MouseCalibration, ProjectionConfig
```

Change constructor:

```python
def __init__(self, config: ControlConfig, roi_size: tuple[int, int] = (410, 315)) -> None:
```

Add:

```python
self._input_mapping_mode = str(getattr(config, "input_mapping_mode", "pixel")).lower()
self._input_mapper = None
if self._input_mapping_mode == "angular":
    vertical = getattr(config, "vertical_fov_deg", 0.0)
    self._input_mapper = AngularInputMapper(
        ProjectionConfig(
            width_px=int(roi_size[0]),
            height_px=int(roi_size[1]),
            horizontal_fov_deg=float(config.horizontal_fov_deg),
            vertical_fov_deg=float(vertical) if vertical > 0 else None,
        ),
        MouseCalibration(
            counts_per_degree_x=float(config.counts_per_degree_x),
            counts_per_degree_y=float(config.counts_per_degree_y),
        ),
    )
```

- [ ] **Step 4: Apply mapping before servo integration**

At the start of `update`, after active/deadzone checks and before `target_speed` calculation:

```python
if self._input_mapper is not None:
    dx, dy = self._input_mapper.map_error((ex, ey))
    if dx == 0 and dy == 0:
        return ControlCommand(mode="relative", reason="subpixel")
    return ControlCommand(dx=dx, dy=dy, mode="relative", reason="tracking")
```

This keeps angular mode intentionally direct in the first implementation. Reintroduce smoothing only in a separate follow-up plan after calibration logs show stable counts-per-degree values.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_algorithms -v
```

Expected: PASS.

---

### Task 4: Integrate Mapper Into Legacy MouseController

**Files:**
- Modify: `src/visual_aiming/actions/mouse_control.py`
- Test: `tests/test_mouse_control.py`

- [ ] **Step 1: Write failing legacy tests**

In `tests/test_mouse_control.py`, add:

```python
class AngularConfig(Config):
    mouse_input_mapping_mode = "angular"
    mouse_horizontal_fov_deg = 90.0
    mouse_vertical_fov_deg = 0.0
    mouse_counts_per_degree_x = 10.0
    mouse_counts_per_degree_y = 10.0
    roi_width = 1920
    roi_height = 1080


def test_legacy_controller_uses_angular_mapping_when_enabled(self):
    from visual_aiming.actions.mouse_control import MouseController

    sent = []
    controller = MouseController(AngularConfig(), move_sender=lambda dx, dy: sent.append((dx, dy)))
    controller.printer = None

    controller.move_towards(target_pos=(1060, 540), crosshair_pos=(100, 540), has_measurement=True, active=True)

    self.assertEqual(sent, [(450, 0)])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_mouse_control -v
```

Expected: FAIL because legacy controller ignores angular mapping.

- [ ] **Step 3: Initialize optional mapper**

In `src/visual_aiming/actions/mouse_control.py`, import mapper types:

```python
from ..algorithms.input_mapping import AngularInputMapper, MouseCalibration, ProjectionConfig
```

In `MouseController.__init__`, add:

```python
self.input_mapper = self._create_input_mapper()
```

Add method:

```python
def _create_input_mapper(self):
    mode = str(getattr(self.config, "mouse_input_mapping_mode", "pixel")).lower()
    if mode != "angular":
        return None
    vertical = float(getattr(self.config, "mouse_vertical_fov_deg", 0.0))
    return AngularInputMapper(
        ProjectionConfig(
            width_px=int(getattr(self.config, "roi_width", 410)),
            height_px=int(getattr(self.config, "roi_height", 315)),
            horizontal_fov_deg=float(getattr(self.config, "mouse_horizontal_fov_deg", 90.0)),
            vertical_fov_deg=vertical if vertical > 0 else None,
        ),
        MouseCalibration(
            counts_per_degree_x=float(getattr(self.config, "mouse_counts_per_degree_x", 1.0)),
            counts_per_degree_y=float(getattr(self.config, "mouse_counts_per_degree_y", 1.0)),
        ),
    )
```

- [ ] **Step 4: Use mapper in controller step**

In `_run_controller_step`, after `if not self.has_error: return`, add:

```python
if self.input_mapper is not None:
    send_x, send_y = self.input_mapper.map_error((self.error_x, self.error_y))
    if send_x == 0 and send_y == 0:
        self._record_zero_output()
        return
    self.move_sender(send_x, send_y)
    self._record_sent(send_x, send_y, dt)
    self._print_diagnostics()
    self._apply_output_feedback(send_x, send_y, dt)
    return
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_mouse_control -v
```

Expected: PASS.

---

### Task 5: Expose Calibration In Config Window

**Files:**
- Modify: `src/visual_aiming/actions/config_window.py`
- Test: `tests/test_config_window_sections.py`

- [ ] **Step 1: Write failing UI exposure test**

In `tests/test_config_window_sections.py`, add:

```python
def test_input_mapping_controls_are_exposed(self):
    sections = ConfigWindow(object(), "config.json")._sections()
    keys = {item.key for _name, items in sections for item in items}

    for key in [
        "mouse_input_mapping_mode",
        "mouse_horizontal_fov_deg",
        "mouse_counts_per_degree_x",
        "mouse_counts_per_degree_y",
    ]:
        self.assertIn(key, keys)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_config_window_sections -v
```

Expected: FAIL because the UI does not expose mapping controls.

- [ ] **Step 3: Add UI controls**

In `src/visual_aiming/actions/config_window.py`, add these to `输出测试` after `mouse_method`:

```python
ChoiceSpec("mouse_input_mapping_mode", "输入映射", ("pixel", "angular"), "pixel 保持当前像素控制；angular 按 FOV 把屏幕误差换算成视角角度。"),
ParamSpec("mouse_horizontal_fov_deg", "水平 FOV", 60, 130, 1, "游戏水平视野角。angular 模式使用。"),
ParamSpec("mouse_counts_per_degree_x", "水平每度输入量", 0.1, 80, 0.1, "视角水平转动 1 度需要的 SendInput 输入量。"),
ParamSpec("mouse_counts_per_degree_y", "垂直每度输入量", 0.1, 80, 0.1, "视角垂直转动 1 度需要的 SendInput 输入量。"),
```

- [ ] **Step 4: Run UI tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_config_window_sections -v
```

Expected: PASS.

---

### Task 6: Extend Probe For Calibration Runs

**Files:**
- Modify: `scripts/mouse_gain_probe.py`
- Test: `tests/test_mouse_gain_probe.py`
- Modify: `docs/debug-workflow.md`

- [ ] **Step 1: Write failing tests for calibration sequence**

In `tests/test_mouse_gain_probe.py`, add:

```python
def test_build_calibration_sequence_scales_requested_delta(self):
    probe = load_probe_module()

    sequence = probe.build_calibration_sequence(axis="x", base=80, multipliers=[1, 2, 4])

    self.assertEqual(sequence, [(80, 0), (160, 0), (320, 0)])

def test_build_calibration_sequence_supports_y_axis(self):
    probe = load_probe_module()

    sequence = probe.build_calibration_sequence(axis="y", base=50, multipliers=[1, 3])

    self.assertEqual(sequence, [(0, 50), (0, 150)])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_mouse_gain_probe -v
```

Expected: FAIL because `build_calibration_sequence` does not exist.

- [ ] **Step 3: Implement calibration sequence helper**

In `scripts/mouse_gain_probe.py`, add:

```python
def build_calibration_sequence(axis: str, base: int, multipliers: List[int]) -> List[Move]:
    normalized = axis.strip().lower()
    if normalized not in {"x", "y"}:
        raise ValueError(f"unsupported calibration axis: {axis}")
    moves = []
    for multiplier in multipliers:
        delta = int(base) * int(multiplier)
        moves.append((delta, 0) if normalized == "x" else (0, delta))
    return moves
```

- [ ] **Step 4: Document manual calibration**

In `docs/debug-workflow.md`, add:

```markdown
### Manual Angular Calibration

Use the probe in an admin shell:

```powershell
.venv\Scripts\python.exe scripts\mouse_gain_probe.py --backend sendinput --dx 80 --dy 0 --count 1 --delay 2
.venv\Scripts\python.exe scripts\mouse_gain_probe.py --backend sendinput --dx 160 --dy 0 --count 1 --delay 2
.venv\Scripts\python.exe scripts\mouse_gain_probe.py --backend sendinput --dx 0 --dy 80 --count 1 --delay 2
```

Record how far the crosshair moves in the game. Convert that observation to approximate `counts_per_degree_x` and `counts_per_degree_y`. Keep `mouse_input_mapping_mode="pixel"` until both axes have stable calibration values.
```

- [ ] **Step 5: Run probe tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_mouse_gain_probe -v
```

Expected: PASS.

---

### Task 7: Verification And Commit

**Files:**
- All files touched by Tasks 1-6.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_input_mapping tests.test_modular_algorithms tests.test_mouse_control tests.test_config_window_sections tests.test_modular_schemas_config tests.test_mouse_gain_probe -v
```

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run:

```powershell
.venv\Scripts\python.exe -m unittest discover tests -v
```

Expected: PASS.

- [ ] **Step 3: Run compile check**

Run:

```powershell
.venv\Scripts\python.exe -m compileall -q src tests scripts main.py
```

Expected: exit code `0`.

- [ ] **Step 4: Run diff check**

Run:

```powershell
git diff --check
```

Expected: exit code `0`; CRLF warnings are acceptable.

- [ ] **Step 5: Commit**

Do not stage `config.json`.

Run:

```powershell
git add src/visual_aiming/algorithms/input_mapping.py src/visual_aiming/algorithms/control.py src/visual_aiming/actions/mouse_control.py src/visual_aiming/actions/config_window.py src/visual_aiming/config/schema.py src/visual_aiming/config/loader.py src/visual_aiming/config/__init__.py scripts/mouse_gain_probe.py docs/debug-workflow.md tests/test_input_mapping.py tests/test_modular_algorithms.py tests/test_mouse_control.py tests/test_config_window_sections.py tests/test_modular_schemas_config.py tests/test_mouse_gain_probe.py
git commit -m "实现鼠标角度输入映射计划"
```

Expected: one Chinese commit containing only code, tests, and docs for angular mapping.

---

## Self-Review

- Spec coverage: The plan covers pure angular math, config, modular controller, legacy controller, UI exposure, probe calibration, docs, and verification.
- Red-flag scan: No `TBD`, `TODO`, or open-ended "add tests" steps remain.
- Type consistency: `ProjectionConfig`, `MouseCalibration`, `AngularInputMapper`, `input_mapping_mode`, `horizontal_fov_deg`, `vertical_fov_deg`, `counts_per_degree_x`, and `counts_per_degree_y` are consistently named across tasks.
- Scope control: This plan intentionally does not modify detection, target selection, or prediction.
