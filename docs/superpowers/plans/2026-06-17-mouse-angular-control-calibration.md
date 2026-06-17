# Mouse Angular Control Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe, testable angular mouse mapping path so game-view movement is calibrated as camera rotation instead of desktop pixel distance.

**Architecture:** Keep detection, target selection, prediction, and diagnostics unchanged. Add a pure input-mapping module, wire it into the modular `RelativeController` behind a default-off config switch, expose calibration fields in the config window, and extend the probe script for repeatable in-game calibration. The current pixel-count output remains default until calibration is proven.

**Tech Stack:** Python standard library, `math`, `dataclasses`, existing `unittest` suite, current modular runtime (`ModularPipeline -> RelativeController -> OutputBackend`), existing `mouse_gain_probe.py`, existing `debug-workflow.md`.

---

## Current Facts And Decisions

- The project now has one runtime path. New mouse work must integrate through `src/visual_aiming/algorithms/control.py` and `src/visual_aiming/core/pipeline.py`, not through old duplicate runtime paths.
- `sendinput` can move the desktop cursor and can move the in-game view when permission is sufficient.
- Game input should be treated as camera rotation. A screen-space target error must be converted to angular error, then to mouse input counts.
- Pixel mode remains the default:

```text
error_px -> existing velocity controller -> relative mouse counts
```

- Angular mode is optional:

```text
error_px -> camera projection -> angle_deg -> calibrated SendInput counts
```

- This phase does not optimize detection accuracy or target selection. Those were stabilized in the previous phase.
- This phase does not enable real mouse output by default. Real output still requires `--real-mouse` and `modular_enable_real_mouse=true`.
- The old plan `docs/superpowers/plans/2026-06-13-mouse-angular-control.md` contains useful math, but its legacy `MouseController` task is obsolete and must not be executed.

## File Structure

- Create: `src/visual_aiming/algorithms/input_mapping.py`
  - Pure math for pixel error to angle and angle to mouse counts.
  - No imports from app, adapters, output backends, Windows APIs, or config loaders.
- Create: `tests/test_input_mapping.py`
  - Unit tests for projection math, vertical FOV derivation, count calibration, and mapper clamping.
- Modify: `src/visual_aiming/config/schema.py`
  - Add modular control mapping fields.
- Modify: `src/visual_aiming/config/loader.py`
  - Map flat `config.json` keys into modular `ControlConfig`.
- Modify: `src/visual_aiming/config/__init__.py`
  - Add legacy flat config fields so the existing config window can save calibration values.
- Modify: `src/visual_aiming/actions/config_window.py`
  - Expose mapping mode, FOV, and counts-per-degree fields under `输出测试`.
- Modify: `tests/test_modular_schemas_config.py`
  - Verify flat config mapping.
- Modify: `tests/test_config_window_sections.py`
  - Verify config window exposes calibration controls.
- Modify: `src/visual_aiming/algorithms/control.py`
  - Add optional angular mapping mode to `RelativeController`.
- Modify: `src/visual_aiming/core/pipeline.py`
  - Pass ROI size into `RelativeController`.
- Modify: `tests/test_modular_algorithms.py`
  - Verify angular mode in controller.
- Modify: `tests/test_modular_pipeline.py`
  - Verify pipeline creates controller with ROI-size-aware mapping.
- Modify: `scripts/mouse_gain_probe.py`
  - Add calibration sequence generation.
- Modify: `tests/test_mouse_gain_probe.py`
  - Verify calibration sequence behavior.
- Modify: `docs/debug-workflow.md`
  - Add manual angular calibration procedure and safe test commands.

---

## Task 1: Add Pure Angular Input Mapper

**Files:**
- Create: `src/visual_aiming/algorithms/input_mapping.py`
- Create: `tests/test_input_mapping.py`

- [ ] **Step 1: Write failing tests for projection and calibration math**

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
        from visual_aiming.algorithms.input_mapping import ProjectionConfig, pixel_error_to_degrees, vertical_fov_from_horizontal

        config = ProjectionConfig(width_px=1920, height_px=1080, horizontal_fov_deg=90.0, vertical_fov_deg=0.0)
        expected_vertical_fov = vertical_fov_from_horizontal(90.0, 1920, 1080)

        _angle_x, angle_y = pixel_error_to_degrees((0.0, 540.0), config)

        self.assertAlmostEqual(angle_y, expected_vertical_fov / 2.0, places=3)

    def test_degrees_to_counts_applies_axis_calibration(self):
        from visual_aiming.algorithms.input_mapping import MouseCalibration, degrees_to_counts

        calibration = MouseCalibration(counts_per_degree_x=12.0, counts_per_degree_y=16.0)

        dx, dy = degrees_to_counts((2.5, -1.25), calibration)

        self.assertEqual((dx, dy), (30, -20))

    def test_mapper_clamps_output_counts(self):
        from visual_aiming.algorithms.input_mapping import AngularInputMapper, MouseCalibration, ProjectionConfig

        mapper = AngularInputMapper(
            ProjectionConfig(width_px=1920, height_px=1080, horizontal_fov_deg=90.0),
            MouseCalibration(counts_per_degree_x=100.0, counts_per_degree_y=100.0, max_counts=200),
        )

        dx, dy = mapper.map_error((960.0, 540.0))

        self.assertEqual(math.hypot(dx, dy), 200.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_input_mapping -v
```

Expected: fail with `ModuleNotFoundError: No module named 'visual_aiming.algorithms.input_mapping'`.

- [ ] **Step 3: Implement pure mapper**

Create `src/visual_aiming/algorithms/input_mapping.py`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass

Vector = tuple[float, float]


@dataclass(frozen=True)
class ProjectionConfig:
    width_px: int
    height_px: int
    horizontal_fov_deg: float
    vertical_fov_deg: float = 0.0


@dataclass(frozen=True)
class MouseCalibration:
    counts_per_degree_x: float = 1.0
    counts_per_degree_y: float = 1.0
    max_counts: int = 0


def vertical_fov_from_horizontal(horizontal_fov_deg: float, width_px: int, height_px: int) -> float:
    horizontal = math.radians(max(1e-6, min(179.0, float(horizontal_fov_deg))))
    aspect = max(1e-6, float(width_px) / max(1.0, float(height_px)))
    vertical = 2.0 * math.atan(math.tan(horizontal / 2.0) / aspect)
    return math.degrees(vertical)


def focal_px_from_fov(size_px: int, fov_deg: float) -> float:
    fov = math.radians(max(1e-6, min(179.0, float(fov_deg))))
    return float(size_px) / (2.0 * math.tan(fov / 2.0))


def pixel_error_to_degrees(error_px: Vector, config: ProjectionConfig) -> Vector:
    width = max(1, int(config.width_px))
    height = max(1, int(config.height_px))
    horizontal_fov = max(1e-6, min(179.0, float(config.horizontal_fov_deg)))
    vertical_fov = float(config.vertical_fov_deg)
    if vertical_fov <= 0.0:
        vertical_fov = vertical_fov_from_horizontal(horizontal_fov, width, height)
    vertical_fov = max(1e-6, min(179.0, vertical_fov))
    focal_x = focal_px_from_fov(width, horizontal_fov)
    focal_y = focal_px_from_fov(height, vertical_fov)
    angle_x = math.degrees(math.atan(float(error_px[0]) / focal_x))
    angle_y = math.degrees(math.atan(float(error_px[1]) / focal_y))
    return (angle_x, angle_y)


def degrees_to_counts(angle_deg: Vector, calibration: MouseCalibration) -> tuple[int, int]:
    dx = int(round(float(angle_deg[0]) * float(calibration.counts_per_degree_x)))
    dy = int(round(float(angle_deg[1]) * float(calibration.counts_per_degree_y)))
    return _clamp_counts(dx, dy, calibration.max_counts)


def _clamp_counts(dx: int, dy: int, max_counts: int) -> tuple[int, int]:
    limit = int(max(0, max_counts))
    if limit <= 0:
        return (dx, dy)
    magnitude = math.hypot(dx, dy)
    if magnitude <= float(limit) or magnitude <= 0.0:
        return (dx, dy)
    scale = float(limit) / magnitude
    return (int(round(dx * scale)), int(round(dy * scale)))


class AngularInputMapper:
    def __init__(self, projection: ProjectionConfig, calibration: MouseCalibration) -> None:
        self.projection = projection
        self.calibration = calibration

    def map_error(self, error_px: Vector) -> tuple[int, int]:
        angle = pixel_error_to_degrees(error_px, self.projection)
        return degrees_to_counts(angle, self.calibration)
```

- [ ] **Step 4: Verify mapper tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_input_mapping -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/visual_aiming/algorithms/input_mapping.py tests/test_input_mapping.py
git commit -m "添加角度输入映射"
```

Explain to user:

```text
Task 1 完成：新增纯数学输入映射模块，可以把屏幕误差换算成视角角度，再按每度输入量转换成鼠标 counts。它不接触真实鼠标，也不改变当前默认控制行为。
```

---

## Task 2: Add Modular And Flat Config Fields

**Files:**
- Modify: `src/visual_aiming/config/schema.py`
- Modify: `src/visual_aiming/config/loader.py`
- Modify: `src/visual_aiming/config/__init__.py`
- Modify: `tests/test_modular_schemas_config.py`

- [ ] **Step 1: Write failing config mapping assertions**

Modify `tests/test_modular_schemas_config.py` inside `ModularConfigTest.test_legacy_flat_config_maps_to_grouped_config`. Add these keys to the mapping literal:

```python
            "mouse_input_mapping_mode": "angular",
            "mouse_horizontal_fov_deg": 103.0,
            "mouse_vertical_fov_deg": 0.0,
            "mouse_counts_per_degree_x": 14.5,
            "mouse_counts_per_degree_y": 18.0,
            "mouse_mapping_max_counts": 240,
```

Add these assertions after existing control assertions:

```python
        self.assertEqual(config.control.input_mapping_mode, "angular")
        self.assertEqual(config.control.horizontal_fov_deg, 103.0)
        self.assertEqual(config.control.vertical_fov_deg, 0.0)
        self.assertEqual(config.control.counts_per_degree_x, 14.5)
        self.assertEqual(config.control.counts_per_degree_y, 18.0)
        self.assertEqual(config.control.mapping_max_counts, 240)
```

- [ ] **Step 2: Run config test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_schemas_config.ModularConfigTest.test_legacy_flat_config_maps_to_grouped_config -v
```

Expected: fail with `AttributeError` for `input_mapping_mode`.

- [ ] **Step 3: Add modular config fields**

Modify `src/visual_aiming/config/schema.py`, extending `ControlConfig`:

```python
    input_mapping_mode: str = "pixel"
    horizontal_fov_deg: float = 90.0
    vertical_fov_deg: float = 0.0
    counts_per_degree_x: float = 1.0
    counts_per_degree_y: float = 1.0
    mapping_max_counts: int = 0
```

- [ ] **Step 4: Map flat config keys**

Modify `src/visual_aiming/config/loader.py`, after `config.control.output_gain` mapping:

```python
    config.control.input_mapping_mode = str(data.get("mouse_input_mapping_mode", config.control.input_mapping_mode))
    config.control.horizontal_fov_deg = float(data.get("mouse_horizontal_fov_deg", config.control.horizontal_fov_deg))
    config.control.vertical_fov_deg = float(data.get("mouse_vertical_fov_deg", config.control.vertical_fov_deg))
    config.control.counts_per_degree_x = float(data.get("mouse_counts_per_degree_x", config.control.counts_per_degree_x))
    config.control.counts_per_degree_y = float(data.get("mouse_counts_per_degree_y", config.control.counts_per_degree_y))
    config.control.mapping_max_counts = int(data.get("mouse_mapping_max_counts", config.control.mapping_max_counts))
```

- [ ] **Step 5: Add flat config fields for UI persistence**

Modify `src/visual_aiming/config/__init__.py`, near existing mouse fields:

```python
    mouse_input_mapping_mode: str = "pixel"
    mouse_horizontal_fov_deg: float = 90.0
    mouse_vertical_fov_deg: float = 0.0
    mouse_counts_per_degree_x: float = 1.0
    mouse_counts_per_degree_y: float = 1.0
    mouse_mapping_max_counts: int = 0
```

- [ ] **Step 6: Verify config mapping**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_schemas_config.ModularConfigTest.test_legacy_flat_config_maps_to_grouped_config -v
```

Expected: test passes.

- [ ] **Step 7: Commit**

Run:

```powershell
git add src/visual_aiming/config/schema.py src/visual_aiming/config/loader.py src/visual_aiming/config/__init__.py tests/test_modular_schemas_config.py
git commit -m "添加角度映射配置"
```

Explain to user:

```text
Task 2 完成：配置中新增角度映射模式、FOV、每度输入量和输出上限，默认仍是 pixel 模式，不会影响现有运行效果。
```

---

## Task 3: Expose Calibration Controls In Config Window

**Files:**
- Modify: `src/visual_aiming/actions/config_window.py`
- Modify: `tests/test_config_window_sections.py`

- [ ] **Step 1: Write failing UI exposure test**

Add to `tests/test_config_window_sections.py`:

```python
    def test_output_test_section_exposes_input_mapping_controls(self):
        sections = ConfigWindow(object(), "config.json")._sections()
        output_keys = {item.key for item in dict(sections)["输出测试"]}

        for key in {
            "mouse_input_mapping_mode",
            "mouse_horizontal_fov_deg",
            "mouse_counts_per_degree_x",
            "mouse_counts_per_degree_y",
            "mouse_mapping_max_counts",
        }:
            self.assertIn(key, output_keys)
```

- [ ] **Step 2: Run UI test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_config_window_sections.ConfigWindowSectionsTest.test_output_test_section_exposes_input_mapping_controls -v
```

Expected: fail because `mouse_input_mapping_mode` is not in the `输出测试` section.

- [ ] **Step 3: Add config window controls**

Modify `src/visual_aiming/actions/config_window.py`. In the `输出测试` section, after `ChoiceSpec("mouse_method", ...)`, add:

```python
                    ChoiceSpec("mouse_input_mapping_mode", "输入映射", ("pixel", "angular"), "pixel 保持当前像素控制；angular 按 FOV 把屏幕误差换算成视角角度。"),
                    ParamSpec("mouse_horizontal_fov_deg", "水平 FOV", 60, 130, 1, "游戏水平视野角。angular 模式使用。"),
                    ParamSpec("mouse_vertical_fov_deg", "垂直 FOV", 0, 120, 1, "0 表示按水平 FOV 和画面比例自动推导。"),
                    ParamSpec("mouse_counts_per_degree_x", "水平每度输入量", 0.1, 80, 0.1, "视角水平转动 1 度需要的 SendInput 输入量。"),
                    ParamSpec("mouse_counts_per_degree_y", "垂直每度输入量", 0.1, 80, 0.1, "视角垂直转动 1 度需要的 SendInput 输入量。"),
                    ParamSpec("mouse_mapping_max_counts", "映射单步上限", 0, 500, 5, "angular 模式下单次输出最大 counts；0 表示不限制。", int),
```

- [ ] **Step 4: Verify config window tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_config_window_sections -v
```

Expected: all config window section tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/visual_aiming/actions/config_window.py tests/test_config_window_sections.py
git commit -m "暴露角度映射调试参数"
```

Explain to user:

```text
Task 3 完成：配置窗口可以调整输入映射模式、FOV、水平/垂直每度输入量和单步上限，但默认仍是 pixel 模式。
```

---

## Task 4: Integrate Angular Mapper Into Modular Controller

**Files:**
- Modify: `src/visual_aiming/algorithms/control.py`
- Modify: `src/visual_aiming/core/pipeline.py`
- Modify: `tests/test_modular_algorithms.py`
- Modify: `tests/test_modular_pipeline.py`

- [ ] **Step 1: Write failing controller test**

Add to `ControllerTest` in `tests/test_modular_algorithms.py`:

```python
    def test_controller_uses_angular_mapping_when_enabled(self):
        from visual_aiming.algorithms.control import RelativeController

        config = ControlConfig(
            deadzone=0.0,
            input_mapping_mode="angular",
            horizontal_fov_deg=90.0,
            vertical_fov_deg=0.0,
            counts_per_degree_x=10.0,
            counts_per_degree_y=10.0,
            mapping_max_counts=0,
        )
        controller = RelativeController(config, roi_size=(1920, 1080))

        command = controller.update((960.0, 0.0), active=True, dt=1 / 120)

        self.assertEqual(command.mode, "relative")
        self.assertEqual(command.reason, "angular")
        self.assertEqual((command.dx, command.dy), (450, 0))
```

- [ ] **Step 2: Run controller test to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_algorithms.ControllerTest.test_controller_uses_angular_mapping_when_enabled -v
```

Expected: fail because `RelativeController.__init__` does not accept `roi_size` or does not support angular mode.

- [ ] **Step 3: Implement angular mode in controller**

Modify `src/visual_aiming/algorithms/control.py`:

Add import:

```python
from visual_aiming.algorithms.input_mapping import AngularInputMapper, MouseCalibration, ProjectionConfig
```

Change constructor signature and mapper setup:

```python
    def __init__(self, config: ControlConfig, roi_size: tuple[int, int] = (410, 315)) -> None:
        self.config = config
        self.velocity = (0.0, 0.0)
        self.subpixel = (0.0, 0.0)
        self._deadzone = max(0.0, config.deadzone)
        self._max_speed = max(1.0, config.max_speed)
        self._acceleration = max(1.0, config.acceleration)
        self._decel_radius = max(config.deadzone + 1.0, config.decel_radius)
        self._near_speed_scale = max(0.0, min(1.0, config.near_speed_scale))
        self._max_step = max(1, config.max_step)
        self._output_gain = config.output_gain
        self._input_mapping_mode = str(getattr(config, "input_mapping_mode", "pixel")).lower()
        self._input_mapper = self._create_input_mapper(config, roi_size)
```

Add helper:

```python
    def _create_input_mapper(self, config: ControlConfig, roi_size: tuple[int, int]):
        if str(getattr(config, "input_mapping_mode", "pixel")).lower() != "angular":
            return None
        width, height = roi_size
        return AngularInputMapper(
            ProjectionConfig(
                width_px=max(1, int(width)),
                height_px=max(1, int(height)),
                horizontal_fov_deg=float(getattr(config, "horizontal_fov_deg", 90.0)),
                vertical_fov_deg=float(getattr(config, "vertical_fov_deg", 0.0)),
            ),
            MouseCalibration(
                counts_per_degree_x=float(getattr(config, "counts_per_degree_x", 1.0)),
                counts_per_degree_y=float(getattr(config, "counts_per_degree_y", 1.0)),
                max_counts=int(getattr(config, "mapping_max_counts", 0)),
            ),
        )
```

At the start of `update`, after deadzone check and before velocity-state logic, add:

```python
        if self._input_mapper is not None:
            dx, dy = self._input_mapper.map_error((ex, ey))
            if dx == 0 and dy == 0:
                return ControlCommand(mode="relative", reason="subpixel")
            return ControlCommand(dx=dx, dy=dy, mode="relative", reason="angular")
```

- [ ] **Step 4: Pass ROI size from pipeline**

Modify `src/visual_aiming/core/pipeline.py` constructor:

```python
        self.controller = RelativeController(config.control, roi_size=config.frame.roi_size)
```

- [ ] **Step 5: Add pipeline construction test**

Add to `tests/test_modular_pipeline.py`:

```python
    def test_pipeline_passes_roi_size_to_angular_controller(self):
        from visual_aiming.core.pipeline import ModularPipeline

        output = FakeOutput()
        config = ModularConfig()
        config.frame.roi_size = (1920, 1080)
        config.control.deadzone = 0.0
        config.control.input_mapping_mode = "angular"
        config.control.horizontal_fov_deg = 90.0
        config.control.counts_per_degree_x = 10.0
        config.control.counts_per_degree_y = 10.0
        detection = Detection(bbox=(1000, 530, 20, 20), confidence=1.0, class_id=0, class_name="head")
        pipeline = ModularPipeline(config, FakeDetector([detection]), output)

        result = pipeline.tick(self.make_frame(active=True), now=1.0)

        self.assertEqual(result.command.reason, "angular")
        self.assertNotEqual((result.command.dx, result.command.dy), (0, 0))
```

- [ ] **Step 6: Verify controller and pipeline tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_modular_algorithms.ControllerTest tests.test_modular_pipeline -v
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add src/visual_aiming/algorithms/control.py src/visual_aiming/core/pipeline.py tests/test_modular_algorithms.py tests/test_modular_pipeline.py
git commit -m "接入模块化角度控制模式"
```

Explain to user:

```text
Task 4 完成：模块化控制器新增 angular 模式，可以按 ROI/FOV 把目标误差转换为 SendInput counts；默认 pixel 模式不变。
```

---

## Task 5: Extend Mouse Probe For Calibration Sequences

**Files:**
- Modify: `scripts/mouse_gain_probe.py`
- Modify: `tests/test_mouse_gain_probe.py`

- [ ] **Step 1: Write failing probe sequence tests**

Add to `tests/test_mouse_gain_probe.py`:

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

- [ ] **Step 2: Run probe tests to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_mouse_gain_probe -v
```

Expected: fail because `build_calibration_sequence` does not exist.

- [ ] **Step 3: Add calibration sequence helper**

Modify `scripts/mouse_gain_probe.py`. Add:

```python
def build_calibration_sequence(axis: str, base: int, multipliers: List[int]) -> List[Move]:
    normalized = (axis or "x").strip().lower()
    if normalized not in {"x", "y"}:
        raise ValueError(f"unsupported calibration axis: {axis}")
    moves: List[Move] = []
    for multiplier in multipliers:
        delta = int(base) * int(multiplier)
        if normalized == "x":
            moves.append((delta, 0))
        else:
            moves.append((0, delta))
    return moves
```

- [ ] **Step 4: Add optional CLI flags**

In `scripts/mouse_gain_probe.py`, add to `ProbeArgs`:

```python
    calibration_axis: str = ""
    calibration_base: int = 0
    calibration_multipliers: str = ""
```

In `parse_args`, add:

```python
    parser.add_argument("--calibration-axis", choices=["x", "y"], default="")
    parser.add_argument("--calibration-base", type=int, default=0)
    parser.add_argument("--calibration-multipliers", default="")
```

And include these fields in the returned `ProbeArgs`.

In `run_probe`, replace:

```python
    sequence = build_move_sequence(args.dx, args.dy, args.count)
```

with:

```python
    if args.calibration_axis and args.calibration_base > 0 and args.calibration_multipliers:
        multipliers = [int(item.strip()) for item in args.calibration_multipliers.split(",") if item.strip()]
        sequence = build_calibration_sequence(args.calibration_axis, args.calibration_base, multipliers)
    else:
        sequence = build_move_sequence(args.dx, args.dy, args.count)
```

- [ ] **Step 5: Verify probe tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_mouse_gain_probe -v
```

Expected: all probe tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add scripts/mouse_gain_probe.py tests/test_mouse_gain_probe.py
git commit -m "扩展鼠标校准探针"
```

Explain to user:

```text
Task 5 完成：鼠标探针可以生成固定倍率的 X/Y 轴校准序列，便于在游戏内观察同一组输入 counts 对应多少视角旋转。
```

---

## Task 6: Document Safe Manual Calibration Workflow

**Files:**
- Modify: `docs/debug-workflow.md`

- [ ] **Step 1: Add manual calibration instructions**

Add this section to `docs/debug-workflow.md`:

```markdown
## Angular Mouse Calibration

Keep `mouse_input_mapping_mode` set to `pixel` until calibration values are measured.

1. Start the game and enter a repeatable training scene.
2. Run the probe from an administrator shell:

```powershell
.venv\Scripts\python.exe scripts\mouse_gain_probe.py --backend sendinput --calibration-axis x --calibration-base 80 --calibration-multipliers 1,2,4 --delay 2 --interval 1
.venv\Scripts\python.exe scripts\mouse_gain_probe.py --backend sendinput --calibration-axis y --calibration-base 80 --calibration-multipliers 1,2,4 --delay 2 --interval 1
```

3. For each movement, record approximate view rotation in degrees.
4. Compute counts per degree:

```text
counts_per_degree = sent_counts / observed_degrees
```

5. Set `mouse_counts_per_degree_x` and `mouse_counts_per_degree_y`.
6. Set `mouse_horizontal_fov_deg` to the in-game horizontal FOV.
7. Set `mouse_mapping_max_counts` to a conservative limit such as `80`.
8. Switch `mouse_input_mapping_mode` to `angular`.
9. Run `python main.py --video-test` first. Then run live only with `--real-mouse` after the video-test command magnitudes look reasonable.

If the game changes sensitivity, FOV, DPI scaling, raw input, or scoped/unscoped state, repeat calibration.
```

- [ ] **Step 2: Verify docs diff has no whitespace errors**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 3: Commit**

Run:

```powershell
git add docs/debug-workflow.md
git commit -m "记录角度鼠标校准流程"
```

Explain to user:

```text
Task 6 完成：文档写明了从 SendInput 探针到 counts-per-degree 参数的校准流程，并要求先视频测试、后真实鼠标输出。
```

---

## Task 7: Phase Verification And Handoff

**Files:**
- Modify: this plan file only if checkbox tracking is used during execution.

- [ ] **Step 1: Run full targeted verification**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_input_mapping tests.test_modular_algorithms tests.test_modular_pipeline tests.test_modular_schemas_config tests.test_config_window_sections tests.test_mouse_gain_probe tests.test_modular_outputs -v
.venv\Scripts\python.exe -m compileall -q src tests scripts main.py
git diff --check
```

Expected:

- Input mapping tests pass.
- Controller and pipeline tests pass.
- Config and config-window tests pass.
- Probe and output tests pass.
- Compile check has no output.
- Diff check has no whitespace errors.

- [ ] **Step 2: Run safety scan**

Run:

```powershell
rg "MouseController\\(|legacy_main\\b|RuntimePipeline\\b|visual_aiming\\.core\\.runtime\\b" main.py src tests
```

Expected: no legacy runtime matches. `MouseController(` matches only if remaining tests intentionally cover legacy compatibility; this phase must not add new `MouseController` integration code.

- [ ] **Step 3: Commit final plan checkbox update**

If this plan file has been edited to mark task checkboxes, run:

```powershell
git add docs/superpowers/plans/2026-06-17-mouse-angular-control-calibration.md
git commit -m "完成角度鼠标控制阶段"
```

Explain to user:

```text
Task 7 完成：角度鼠标控制阶段完成。当前默认行为仍安全保持 pixel 模式；angular 模式需要手动校准 FOV 和每度输入量后启用。
```

---

## Commit Guidance

Commit per task. Do not include `config.json` unless the user explicitly asks to commit local tuning values.

## Push Guidance

Do not push automatically. Push only when the user says network is good and asks to push.

## Self-Review

- Spec coverage: This plan covers pure angular math, config persistence, config window exposure, modular controller integration, probe-based calibration, documentation, and verification.
- Runtime alignment: The plan only integrates with the current modular runtime and explicitly avoids executing the obsolete legacy controller task from the older plan.
- Safety: Real mouse output remains gated by existing `enable_real_mouse` behavior and `--real-mouse`; angular mode remains default-off.
- Placeholder scan: No task depends on an unspecified function or file. Every new function, config field, and command is named in the task where it is introduced.
