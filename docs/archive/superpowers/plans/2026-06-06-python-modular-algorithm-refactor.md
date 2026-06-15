# Python Modular Algorithm Refactor Implementation Plan

> **Historical status (2026-06-09):** This document is an implementation plan record, not the current source of truth for module locations.
> The current implementation uses the `src/visual_aiming/app/` package and has removed the duplicate `src/visual_aiming/app.py` module.
> Detector and output construction now goes through `visual_aiming.adapters.detectors.factory` and `visual_aiming.adapters.outputs.factory`; older snippets below that instantiate `UltralyticsYoloDetector(config.detector)` or `WinMouseOutput` directly are preserved as historical plan text.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Python-first modular algorithm runtime where realtime screen input and offline replay share one pipeline with replaceable detector, algorithms, diagnostics, and output backends.

**Architecture:** Add a new modular slice beside the existing runtime, then migrate entrypoints to compose it. Core code owns dataclasses, pipeline orchestration, metrics, and pure algorithms; ports define Protocol boundaries; adapters wrap screen capture, video input, ultralytics YOLO, and mouse/log/null outputs. The default output is safe and does not move the mouse unless `OutputConfig.backend == "win_mouse"` and `enable_real_mouse == True`.

**Tech Stack:** Python 3, stdlib `unittest`, dataclasses, Protocols, NumPy, OpenCV for video source, MSS for realtime source, ultralytics YOLO via existing `TargetDetector`, Windows mouse APIs isolated in output adapter.

---

## Scope Check

The approved spec covers a first-version modular runtime, not UI restoration, PyInstaller packaging, ONNX implementation, or cross-language implementation. This plan implements the first-version runtime completely enough to run tests, run replay safely, and compose realtime mode with an explicit real-mouse opt-in. Config UI, debug windows, packaging, and ONNX detector implementation remain outside this plan by design.

## File Structure

Create focused modules instead of expanding existing large files:

- Create `src/visual_aiming/core/schemas.py`: replace the old small schema file with full dataclasses for frames, detections, target selection, aim, prediction, control, runtime state, and pipeline result.
- Create `src/visual_aiming/ports/frame_source.py`: `FrameSource` Protocol.
- Create `src/visual_aiming/ports/detector.py`: `Detector` Protocol.
- Create `src/visual_aiming/ports/output.py`: `OutputBackend` Protocol.
- Create `src/visual_aiming/ports/diagnostics.py`: `DiagnosticsSink` Protocol.
- Create `src/visual_aiming/config/schema.py`: grouped dataclass config used by the modular runtime.
- Create `src/visual_aiming/config/loader.py`: load legacy flat `config.json` into grouped config.
- Create `src/visual_aiming/algorithms/target_selection.py`: scoring and sticky target selection.
- Create `src/visual_aiming/algorithms/aim_point.py`: bbox-to-screen aim point strategy.
- Create `src/visual_aiming/algorithms/prediction.py`: alpha-beta predictor with lost/held/reset states.
- Create `src/visual_aiming/algorithms/control.py`: relative controller that emits `ControlCommand` only.
- Create `src/visual_aiming/core/pipeline.py`: pipeline orchestrator using ports and algorithms.
- Create `src/visual_aiming/core/metrics.py`: JSONL diagnostics and summary metrics.
- Create `src/visual_aiming/adapters/outputs/null_output.py`: safe no-op output.
- Create `src/visual_aiming/adapters/outputs/log_output.py`: in-memory/logging output for tests and replay.
- Create `src/visual_aiming/adapters/outputs/win_mouse.py`: Windows mouse output adapter.
- Create `src/visual_aiming/adapters/detectors/ultralytics_yolo.py`: adapter around existing `visual_aiming.vision.detection.TargetDetector`.
- Create `src/visual_aiming/adapters/frame_sources/video_file.py`: video replay frame source.
- Create `src/visual_aiming/adapters/frame_sources/screen_capture.py`: realtime screen frame source wrapper.
- Create `src/visual_aiming/app/replay.py`: safe replay entrypoint.
- Create `src/visual_aiming/app/realtime.py`: realtime entrypoint that defaults to non-real output.
- Modify `src/visual_aiming/app.py`: expose modular app helpers without breaking old imports.
- Modify `main.py`: keep current behavior unless `--modular` is provided; `--modular --real-mouse` enables real mouse output explicitly.
- Create tests:
  - `tests/test_modular_schemas_config.py`
  - `tests/test_modular_algorithms.py`
  - `tests/test_modular_outputs.py`
  - `tests/test_modular_pipeline.py`
  - `tests/test_modular_metrics.py`
  - `tests/test_modular_adapters.py`
  - `tests/test_modular_apps.py`

All tests should prepend `src/` to `sys.path`, matching existing test style.

## Task 1: Core Schemas and Ports

**Files:**
- Create/Replace: `src/visual_aiming/core/schemas.py`
- Create: `src/visual_aiming/ports/frame_source.py`
- Create: `src/visual_aiming/ports/detector.py`
- Create: `src/visual_aiming/ports/output.py`
- Create: `src/visual_aiming/ports/diagnostics.py`
- Test: `tests/test_modular_schemas_config.py`

- [ ] **Step 1: Write failing schema and port tests**

Create `tests/test_modular_schemas_config.py` with this content:

```python
import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


class ModularSchemasTest(unittest.TestCase):
    def test_frame_packet_carries_roi_and_crosshair(self):
        from visual_aiming.core.schemas import FramePacket, RuntimeMode

        frame = np.zeros((4, 6, 3), dtype=np.uint8)
        packet = FramePacket(
            frame=frame,
            timestamp=1.25,
            sequence=7,
            roi_offset=(10, 20),
            roi_size=(6, 4),
            crosshair=(13, 22),
            source="unit",
            mode=RuntimeMode(active=True, firing=False),
        )

        self.assertEqual(packet.sequence, 7)
        self.assertEqual(packet.roi_offset, (10, 20))
        self.assertEqual(packet.crosshair, (13, 22))
        self.assertTrue(packet.mode.active)
        self.assertFalse(packet.mode.firing)

    def test_pipeline_tick_result_preserves_intermediate_states(self):
        from visual_aiming.core.schemas import (
            AimMeasurement,
            ControlCommand,
            Detection,
            DetectionPacket,
            PipelineTickResult,
            PredictedAim,
            RuntimeMode,
            SelectedTarget,
        )

        detection = Detection(bbox=(1, 2, 10, 20), confidence=0.9, class_id=0, class_name="head")
        detections = DetectionPacket(sequence=1, detections=[detection], latency_ms=3.5, detector_name="fake", fresh=True)
        selected = SelectedTarget(detection=detection, score=0.1, score_parts={"distance": 0.1}, switched=False)
        aim = AimMeasurement(point=(100, 120), crosshair=(90, 120), error=(10.0, 0.0), valid=True)
        predicted = PredictedAim(point=(101, 120), velocity=(5.0, 0.0), confidence=0.8, state="tracking")
        command = ControlCommand(dx=4, dy=0, mode="relative", limited=False, reason="tracking")

        result = PipelineTickResult(
            sequence=1,
            timestamp=2.0,
            mode=RuntimeMode(active=True, firing=True),
            detections=detections,
            selected=selected,
            aim=aim,
            predicted=predicted,
            command=command,
            output_backend="null",
            pipeline_latency_ms=1.2,
        )

        self.assertEqual(result.detections.detections[0].class_name, "head")
        self.assertEqual(result.selected.score_parts["distance"], 0.1)
        self.assertEqual(result.command.dx, 4)
        self.assertEqual(result.mode.firing, True)

    def test_ports_are_importable(self):
        from visual_aiming.ports.detector import Detector
        from visual_aiming.ports.diagnostics import DiagnosticsSink
        from visual_aiming.ports.frame_source import FrameSource
        from visual_aiming.ports.output import OutputBackend

        self.assertIsNotNone(Detector)
        self.assertIsNotNone(DiagnosticsSink)
        self.assertIsNotNone(FrameSource)
        self.assertIsNotNone(OutputBackend)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_modular_schemas_config -v`

Expected: FAIL with an import error for at least one of `RuntimeMode`, `FramePacket`, or `visual_aiming.ports.detector`.

- [ ] **Step 3: Implement core schemas**

Replace `src/visual_aiming/core/schemas.py` with this content. It preserves the old `Point`, `BBox`, `ControlTarget`, and compatible names while adding the modular dataclasses.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

Point = Tuple[int, int]
Vector = Tuple[float, float]
BBox = Tuple[int, int, int, int]


@dataclass(frozen=True)
class RuntimeMode:
    active: bool = False
    firing: bool = False


@dataclass
class FramePacket:
    frame: np.ndarray
    timestamp: float
    sequence: int
    roi_offset: Point
    roi_size: Point
    crosshair: Point
    source: str
    mode: RuntimeMode = field(default_factory=RuntimeMode)


@dataclass
class Detection:
    bbox: BBox
    confidence: float = 0.0
    class_id: Optional[int] = None
    class_name: str = "unknown"

    @property
    def x(self) -> int:
        return self.bbox[0]

    @property
    def y(self) -> int:
        return self.bbox[1]

    @property
    def w(self) -> int:
        return self.bbox[2]

    @property
    def h(self) -> int:
        return self.bbox[3]

    @property
    def center(self) -> Point:
        return (self.x + self.w // 2, self.y + self.h // 2)


@dataclass
class DetectionPacket:
    sequence: int
    detections: List[Detection]
    latency_ms: float
    detector_name: str
    fresh: bool = True


@dataclass
class SelectedTarget:
    detection: Optional[Detection]
    score: float
    score_parts: Dict[str, float] = field(default_factory=dict)
    switched: bool = False
    reason: str = "none"


@dataclass
class AimMeasurement:
    point: Optional[Point]
    crosshair: Point
    error: Vector
    valid: bool


@dataclass
class PredictedAim:
    point: Optional[Point]
    velocity: Vector
    confidence: float
    state: str


@dataclass
class ControlCommand:
    dx: int = 0
    dy: int = 0
    mode: str = "none"
    limited: bool = False
    reason: str = "inactive"

    @property
    def is_noop(self) -> bool:
        return self.dx == 0 and self.dy == 0 and self.mode in {"none", "relative"}


@dataclass
class PipelineTickResult:
    sequence: int
    timestamp: float
    mode: RuntimeMode
    detections: DetectionPacket
    selected: SelectedTarget
    aim: AimMeasurement
    predicted: PredictedAim
    command: ControlCommand
    output_backend: str
    pipeline_latency_ms: float


@dataclass
class VisionFrame:
    frame: np.ndarray
    timestamp: float
    sequence: int


@dataclass
class DetectionState:
    target: Optional[object]
    fresh: bool
    frame: Optional[np.ndarray] = None
    timestamp: float = 0.0
    sequence: int = -1


@dataclass
class ControlTarget:
    target: Optional[Point]
    crosshair: Optional[Point]
    has_measurement: bool
    active: bool


@dataclass
class PipelineResult:
    control: ControlTarget
    aim_point: Optional[Point]
    debug_bbox: Optional[BBox]
    used_tracker_prediction: bool = False
```

- [ ] **Step 4: Implement ports**

Create `src/visual_aiming/ports/frame_source.py`:

```python
from __future__ import annotations

from typing import Optional, Protocol

from visual_aiming.core.schemas import FramePacket


class FrameSource(Protocol):
    name: str

    def read(self) -> Optional[FramePacket]:
        """Return the next frame or None when no frame is currently available."""
        ...

    def close(self) -> None:
        """Release resources held by the source."""
        ...
```

Create `src/visual_aiming/ports/detector.py`:

```python
from __future__ import annotations

from typing import Protocol

from visual_aiming.core.schemas import DetectionPacket, FramePacket


class Detector(Protocol):
    name: str

    def detect(self, frame: FramePacket) -> DetectionPacket:
        """Detect targets in a frame and return normalized detections."""
        ...
```

Create `src/visual_aiming/ports/output.py`:

```python
from __future__ import annotations

from typing import Protocol

from visual_aiming.core.schemas import ControlCommand, PipelineTickResult


class OutputBackend(Protocol):
    name: str

    def apply(self, command: ControlCommand, result: PipelineTickResult) -> None:
        """Apply or record one control command."""
        ...

    def close(self) -> None:
        """Release resources held by the output backend."""
        ...
```

Create `src/visual_aiming/ports/diagnostics.py`:

```python
from __future__ import annotations

from typing import Protocol

from visual_aiming.core.schemas import PipelineTickResult


class DiagnosticsSink(Protocol):
    name: str

    def write(self, result: PipelineTickResult) -> None:
        """Record one pipeline tick."""
        ...

    def close(self) -> None:
        """Flush and release resources."""
        ...
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_modular_schemas_config -v`

Expected: PASS for the three tests in `ModularSchemasTest`.

- [ ] **Step 6: Commit**

```bash
git add src/visual_aiming/core/schemas.py src/visual_aiming/ports tests/test_modular_schemas_config.py
git commit -m "feat: add modular schemas and ports"
```

## Task 2: Grouped Runtime Config and Legacy Loader

**Files:**
- Create: `src/visual_aiming/config/schema.py`
- Create: `src/visual_aiming/config/loader.py`
- Modify: `tests/test_modular_schemas_config.py`

- [ ] **Step 1: Add failing config tests**

Append these tests to `tests/test_modular_schemas_config.py` before the `if __name__ == "__main__"` block:

```python
class ModularConfigTest(unittest.TestCase):
    def test_default_config_uses_safe_output(self):
        from visual_aiming.config.schema import ModularConfig

        config = ModularConfig()

        self.assertEqual(config.output.backend, "null")
        self.assertFalse(config.output.enable_real_mouse)
        self.assertEqual(config.detector.backend, "ultralytics")
        self.assertEqual(config.frame.roi_size, (410, 315))

    def test_legacy_flat_config_maps_to_grouped_config(self):
        from visual_aiming.config.loader import modular_config_from_mapping

        config = modular_config_from_mapping({
            "roi_width": 500,
            "roi_height": 300,
            "detect_fps": 20,
            "yolo_model_path": "models/custom.pt",
            "yolo_conf_threshold": 0.42,
            "yolo_head_class_id": 2,
            "yolo_person_class_id": 3,
            "aim_target_preference": 0.75,
            "head_bias": 0.2,
            "tracker_prediction_time": 0.05,
            "servo_deadzone": 3.0,
            "servo_step_limit": 12,
            "mouse_absolute_mode_enabled": True,
        })

        self.assertEqual(config.frame.roi_size, (500, 300))
        self.assertEqual(config.runtime.detect_fps, 20.0)
        self.assertEqual(config.detector.model_path, "models/custom.pt")
        self.assertEqual(config.detector.confidence, 0.42)
        self.assertEqual(config.target_selection.head_class_id, 2)
        self.assertEqual(config.target_selection.person_class_id, 3)
        self.assertEqual(config.aim.target_preference, 0.75)
        self.assertEqual(config.aim.head_bias, 0.2)
        self.assertEqual(config.prediction.lead_time, 0.05)
        self.assertEqual(config.control.deadzone, 3.0)
        self.assertEqual(config.control.max_step, 12)
        self.assertEqual(config.output.command_mode, "absolute")
        self.assertEqual(config.output.backend, "null")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_modular_schemas_config -v`

Expected: FAIL with import error for `visual_aiming.config.schema`.

- [ ] **Step 3: Implement grouped config dataclasses**

Create `src/visual_aiming/config/schema.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


Point = Tuple[int, int]


@dataclass
class RuntimeConfig:
    poll_fps: float = 120.0
    detect_fps: float = 30.0
    idle_detect_fps: float = 8.0
    detect_only_new_frames: bool = True


@dataclass
class FrameSourceConfig:
    roi_size: Point = (410, 315)
    capture_fps: float = 30.0
    source: str = "screen"
    video_path: str = ""


@dataclass
class DetectorConfig:
    backend: str = "ultralytics"
    model_path: str = "models/best.pt"
    confidence: float = 0.5
    iou: float = 0.45
    device: str = "auto"
    half: bool = True
    imgsz: int = 416


@dataclass
class TargetSelectionConfig:
    head_class_id: int = 0
    person_class_id: int = 1
    target_preference: float = 0.85
    stickiness: float = 0.28
    history_radius: int = 120
    switch_margin: float = 0.08
    class_switch_penalty: float = 0.05


@dataclass
class AimConfig:
    head_bias: float = 0.25
    body_bias: float = 0.45
    target_preference: float = 0.85


@dataclass
class PredictionConfig:
    alpha: float = 0.65
    beta: float = 0.20
    lead_time: float = 0.025
    reset_distance: float = 200.0
    max_hold_ms: float = 160.0
    firing_freeze: bool = True


@dataclass
class ControlConfig:
    deadzone: float = 2.0
    speed_gain: float = 42.0
    max_speed: float = 7200.0
    acceleration: float = 52.0
    decel_radius: float = 135.0
    near_speed_scale: float = 0.10
    max_step: int = 48
    output_gain: float = 1.0


@dataclass
class OutputConfig:
    backend: str = "null"
    enable_real_mouse: bool = False
    command_mode: str = "relative"
    log_path: str = ""


@dataclass
class DiagnosticsConfig:
    enabled: bool = True
    jsonl_path: str = ""
    summary_path: str = ""


@dataclass
class ModularConfig:
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    frame: FrameSourceConfig = field(default_factory=FrameSourceConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    target_selection: TargetSelectionConfig = field(default_factory=TargetSelectionConfig)
    aim: AimConfig = field(default_factory=AimConfig)
    prediction: PredictionConfig = field(default_factory=PredictionConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    diagnostics: DiagnosticsConfig = field(default_factory=DiagnosticsConfig)
```

- [ ] **Step 4: Implement legacy mapping loader**

Create `src/visual_aiming/config/loader.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from visual_aiming.config.schema import ModularConfig


def modular_config_from_mapping(data: Mapping[str, Any]) -> ModularConfig:
    config = ModularConfig()

    roi_width = int(data.get("roi_width", config.frame.roi_size[0]))
    roi_height = int(data.get("roi_height", config.frame.roi_size[1]))
    config.frame.roi_size = (roi_width, roi_height)
    config.frame.capture_fps = float(data.get("capture_fps", config.frame.capture_fps))

    config.runtime.poll_fps = float(data.get("runtime_poll_fps", config.runtime.poll_fps))
    config.runtime.detect_fps = float(data.get("detect_fps", config.runtime.detect_fps))
    config.runtime.idle_detect_fps = float(data.get("idle_detect_fps", config.runtime.idle_detect_fps))
    config.runtime.detect_only_new_frames = bool(data.get("detect_only_new_frames", config.runtime.detect_only_new_frames))

    config.detector.model_path = str(data.get("yolo_model_path", config.detector.model_path))
    config.detector.confidence = float(data.get("yolo_conf_threshold", config.detector.confidence))
    config.detector.iou = float(data.get("yolo_iou_threshold", config.detector.iou))
    config.detector.device = str(data.get("yolo_device", config.detector.device))
    config.detector.half = bool(data.get("yolo_half", config.detector.half))
    config.detector.imgsz = int(data.get("yolo_imgsz", config.detector.imgsz))

    config.target_selection.head_class_id = int(data.get("yolo_head_class_id", config.target_selection.head_class_id))
    config.target_selection.person_class_id = int(data.get("yolo_person_class_id", config.target_selection.person_class_id))
    config.target_selection.target_preference = float(data.get("aim_target_preference", config.target_selection.target_preference))
    config.target_selection.stickiness = float(data.get("target_stickiness", config.target_selection.stickiness))
    config.target_selection.history_radius = int(data.get("target_history_radius", config.target_selection.history_radius))
    config.target_selection.switch_margin = float(data.get("target_switch_margin", config.target_selection.switch_margin))
    config.target_selection.class_switch_penalty = float(data.get("target_class_switch_penalty", config.target_selection.class_switch_penalty))

    config.aim.head_bias = float(data.get("head_bias", config.aim.head_bias))
    config.aim.target_preference = float(data.get("aim_target_preference", config.aim.target_preference))

    config.prediction.alpha = float(data.get("tracker_smoothing_factor", config.prediction.alpha))
    config.prediction.lead_time = float(data.get("tracker_prediction_time", config.prediction.lead_time))
    config.prediction.reset_distance = float(data.get("tracker_reset_distance", config.prediction.reset_distance))
    config.prediction.max_hold_ms = float(data.get("tracker_max_prediction_ms", config.prediction.max_hold_ms))
    config.prediction.firing_freeze = bool(data.get("firing_disable_tracker_prediction", config.prediction.firing_freeze))

    config.control.deadzone = float(data.get("servo_deadzone", config.control.deadzone))
    config.control.speed_gain = float(data.get("fps_speed_gain", config.control.speed_gain))
    config.control.max_speed = float(data.get("fps_max_speed", config.control.max_speed))
    config.control.acceleration = float(data.get("fps_acceleration", config.control.acceleration))
    config.control.decel_radius = float(data.get("fps_decel_radius", config.control.decel_radius))
    config.control.near_speed_scale = float(data.get("fps_near_speed_scale", config.control.near_speed_scale))
    config.control.max_step = int(data.get("servo_step_limit", config.control.max_step))
    config.control.output_gain = float(data.get("servo_output_gain", config.control.output_gain))

    if bool(data.get("mouse_absolute_mode_enabled", False)):
        config.output.command_mode = "absolute"
    config.output.backend = str(data.get("modular_output_backend", config.output.backend))
    config.output.enable_real_mouse = bool(data.get("modular_enable_real_mouse", config.output.enable_real_mouse))
    config.output.log_path = str(data.get("modular_output_log_path", config.output.log_path))

    config.diagnostics.enabled = bool(data.get("modular_diagnostics_enabled", config.diagnostics.enabled))
    config.diagnostics.jsonl_path = str(data.get("modular_diagnostics_jsonl_path", config.diagnostics.jsonl_path))
    config.diagnostics.summary_path = str(data.get("modular_diagnostics_summary_path", config.diagnostics.summary_path))
    return config


def load_modular_config(path: str | Path) -> ModularConfig:
    config_path = Path(path)
    if not config_path.exists():
        return ModularConfig()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a JSON object: {config_path}")
    return modular_config_from_mapping(data)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_modular_schemas_config -v`

Expected: PASS for schema, port, and config tests.

- [ ] **Step 6: Commit**

```bash
git add src/visual_aiming/config/schema.py src/visual_aiming/config/loader.py tests/test_modular_schemas_config.py
git commit -m "feat: add grouped modular config"
```

## Task 3: Target Selection and Aim Strategy

**Files:**
- Create: `src/visual_aiming/algorithms/target_selection.py`
- Create: `src/visual_aiming/algorithms/aim_point.py`
- Test: `tests/test_modular_algorithms.py`

- [ ] **Step 1: Write failing algorithm tests**

Create `tests/test_modular_algorithms.py`:

```python
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.config.schema import AimConfig, PredictionConfig, ControlConfig, TargetSelectionConfig
from visual_aiming.core.schemas import AimMeasurement, Detection, RuntimeMode


class TargetSelectorTest(unittest.TestCase):
    def test_prefers_head_near_crosshair(self):
        from visual_aiming.algorithms.target_selection import TargetSelector

        selector = TargetSelector(TargetSelectionConfig(head_class_id=0, person_class_id=1, target_preference=0.85))
        detections = [
            Detection(bbox=(0, 0, 40, 80), confidence=0.95, class_id=1, class_name="person"),
            Detection(bbox=(95, 95, 20, 20), confidence=0.75, class_id=0, class_name="head"),
        ]

        selected = selector.select(detections, roi_center=(100, 100))

        self.assertIsNotNone(selected.detection)
        self.assertEqual(selected.detection.class_name, "head")
        self.assertEqual(selected.reason, "selected")
        self.assertIn("class", selected.score_parts)

    def test_sticky_target_delays_small_switches(self):
        from visual_aiming.algorithms.target_selection import TargetSelector

        selector = TargetSelector(TargetSelectionConfig(stickiness=0.5, history_radius=80, switch_margin=0.2))
        previous = Detection(bbox=(90, 90, 20, 20), confidence=0.8, class_id=0, class_name="head")
        selector.select([previous], roi_center=(100, 100))
        near_previous = Detection(bbox=(92, 92, 20, 20), confidence=0.7, class_id=0, class_name="head")
        slightly_better = Detection(bbox=(100, 100, 20, 20), confidence=0.71, class_id=0, class_name="head")

        selected = selector.select([slightly_better, near_previous], roi_center=(100, 100))

        self.assertEqual(selected.detection.bbox, near_previous.bbox)
        self.assertFalse(selected.switched)


class AimStrategyTest(unittest.TestCase):
    def test_head_aim_uses_head_bias_and_roi_offset(self):
        from visual_aiming.algorithms.aim_point import AimStrategy

        strategy = AimStrategy(AimConfig(head_bias=0.25), head_class_id=0)
        detection = Detection(bbox=(10, 20, 40, 80), confidence=1.0, class_id=0, class_name="head")

        measurement = strategy.measure(detection, roi_offset=(100, 200), crosshair=(150, 250))

        self.assertEqual(measurement.point, (130, 240))
        self.assertEqual(measurement.error, (-20.0, -10.0))
        self.assertTrue(measurement.valid)

    def test_missing_target_returns_invalid_measurement(self):
        from visual_aiming.algorithms.aim_point import AimStrategy

        strategy = AimStrategy(AimConfig(), head_class_id=0)

        measurement = strategy.measure(None, roi_offset=(100, 200), crosshair=(150, 250))

        self.assertIsNone(measurement.point)
        self.assertEqual(measurement.error, (0.0, 0.0))
        self.assertFalse(measurement.valid)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_modular_algorithms -v`

Expected: FAIL with import error for `visual_aiming.algorithms.target_selection`.

- [ ] **Step 3: Implement target selection**

Create `src/visual_aiming/algorithms/target_selection.py`:

```python
from __future__ import annotations

import math
from typing import Iterable, Optional

from visual_aiming.config.schema import TargetSelectionConfig
from visual_aiming.core.schemas import Detection, Point, SelectedTarget


class TargetSelector:
    def __init__(self, config: TargetSelectionConfig) -> None:
        self.config = config
        self.previous: Optional[Detection] = None

    def reset(self) -> None:
        self.previous = None

    def select(self, detections: Iterable[Detection], roi_center: Point) -> SelectedTarget:
        candidates = list(detections)
        if not candidates:
            self.previous = None
            return SelectedTarget(detection=None, score=math.inf, reason="no_detections")

        scored = [(self._score(item, roi_center), item) for item in candidates]
        scored.sort(key=lambda pair: pair[0][0])
        best_parts, best = scored[0]

        sticky = self._sticky_candidate(scored)
        chosen = best
        chosen_parts = best_parts
        if sticky is not None:
            sticky_parts, sticky_detection = sticky
            if sticky_detection is not best and best_parts[0] + self.config.switch_margin >= sticky_parts[0]:
                chosen = sticky_detection
                chosen_parts = sticky_parts

        switched = self.previous is not None and self._distance_sq(chosen, self.previous) > 0
        self.previous = chosen
        return SelectedTarget(
            detection=chosen,
            score=chosen_parts[0],
            score_parts=chosen_parts[1],
            switched=switched,
            reason="selected",
        )

    def _score(self, detection: Detection, roi_center: Point) -> tuple[float, dict[str, float]]:
        cx, cy = detection.center
        distance = math.hypot(cx - roi_center[0], cy - roi_center[1])
        max_distance = max(1.0, math.hypot(roi_center[0], roi_center[1]))
        distance_score = min(1.0, distance / max_distance)
        confidence_score = 1.0 - max(0.0, min(1.0, detection.confidence))
        class_score = self._class_score(detection)
        continuity = self._continuity_bonus(detection)
        switch_penalty = self._class_switch_penalty(detection)
        total = class_score * 0.60 + distance_score * 0.30 + confidence_score * 0.10 - continuity + switch_penalty
        return total, {
            "class": class_score,
            "distance": distance_score,
            "confidence": confidence_score,
            "continuity": -continuity,
            "switch_penalty": switch_penalty,
        }

    def _class_score(self, detection: Detection) -> float:
        preference = max(0.0, min(1.0, self.config.target_preference))
        if detection.class_id == self.config.head_class_id:
            return 1.0 - preference
        if detection.class_id == self.config.person_class_id:
            return preference
        return 1.5

    def _continuity_bonus(self, detection: Detection) -> float:
        if self.previous is None:
            return 0.0
        radius = max(1, self.config.history_radius)
        distance_sq = self._distance_sq(detection, self.previous)
        if distance_sq > radius * radius:
            return 0.0
        normalized = min(1.0, distance_sq / float(radius * radius))
        return (1.0 - normalized) * max(0.0, min(1.0, self.config.stickiness))

    def _class_switch_penalty(self, detection: Detection) -> float:
        if self.previous is None:
            return 0.0
        if self.previous.class_id is None or detection.class_id is None:
            return 0.0
        if self.previous.class_id == detection.class_id:
            return 0.0
        return max(0.0, self.config.class_switch_penalty)

    def _sticky_candidate(self, scored: list[tuple[tuple[float, dict[str, float]], Detection]]):
        if self.previous is None:
            return None
        radius_sq = max(1, self.config.history_radius) ** 2
        near_previous = [item for item in scored if self._distance_sq(item[1], self.previous) <= radius_sq]
        if not near_previous:
            return None
        near_previous.sort(key=lambda item: (self._distance_sq(item[1], self.previous), item[0][0]))
        return near_previous[0]

    def _distance_sq(self, left: Detection, right: Detection) -> int:
        lx, ly = left.center
        rx, ry = right.center
        return (lx - rx) ** 2 + (ly - ry) ** 2
```

- [ ] **Step 4: Implement aim strategy**

Create `src/visual_aiming/algorithms/aim_point.py`:

```python
from __future__ import annotations

from typing import Optional

from visual_aiming.config.schema import AimConfig
from visual_aiming.core.schemas import AimMeasurement, Detection, Point


class AimStrategy:
    def __init__(self, config: AimConfig, head_class_id: int) -> None:
        self.config = config
        self.head_class_id = head_class_id

    def measure(self, detection: Optional[Detection], roi_offset: Point, crosshair: Point) -> AimMeasurement:
        if detection is None:
            return AimMeasurement(point=None, crosshair=crosshair, error=(0.0, 0.0), valid=False)

        bias = self._vertical_bias(detection)
        roi_x = detection.x + detection.w // 2
        roi_y = detection.y + int(detection.h * bias)
        point = (roi_offset[0] + roi_x, roi_offset[1] + roi_y)
        error = (float(point[0] - crosshair[0]), float(point[1] - crosshair[1]))
        return AimMeasurement(point=point, crosshair=crosshair, error=error, valid=True)

    def _vertical_bias(self, detection: Detection) -> float:
        preference = max(0.0, min(1.0, self.config.target_preference))
        if detection.class_id == self.head_class_id or detection.class_name == "head":
            low_preference_bias = 0.62
            return 0.5 + (low_preference_bias - 0.5) * (1.0 - preference)
        return self.config.body_bias - (self.config.body_bias - self.config.head_bias) * preference
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_modular_algorithms -v`

Expected: PASS for target selection and aim strategy tests.

- [ ] **Step 6: Commit**

```bash
git add src/visual_aiming/algorithms/target_selection.py src/visual_aiming/algorithms/aim_point.py tests/test_modular_algorithms.py
git commit -m "feat: add modular target and aim algorithms"
```

## Task 4: Predictor and Controller Algorithms

**Files:**
- Create: `src/visual_aiming/algorithms/prediction.py`
- Create: `src/visual_aiming/algorithms/control.py`
- Modify: `tests/test_modular_algorithms.py`

- [ ] **Step 1: Add failing predictor and controller tests**

Append these tests to `tests/test_modular_algorithms.py` before the `if __name__ == "__main__"` block:

```python
class PredictorTest(unittest.TestCase):
    def test_predictor_tracks_velocity_and_predicts_forward(self):
        from visual_aiming.algorithms.prediction import AlphaBetaPredictor

        predictor = AlphaBetaPredictor(PredictionConfig(alpha=0.5, beta=0.25, lead_time=0.10))
        first = AimMeasurement(point=(100, 100), crosshair=(90, 100), error=(10.0, 0.0), valid=True)
        second = AimMeasurement(point=(110, 100), crosshair=(90, 100), error=(20.0, 0.0), valid=True)

        predictor.update(first, RuntimeMode(active=True, firing=False), now=1.0)
        predicted = predictor.update(second, RuntimeMode(active=True, firing=False), now=1.1)

        self.assertEqual(predicted.state, "tracking")
        self.assertGreater(predicted.point[0], 110)
        self.assertGreater(predicted.velocity[0], 0.0)

    def test_predictor_holds_recent_track_when_measurement_missing(self):
        from visual_aiming.algorithms.prediction import AlphaBetaPredictor

        predictor = AlphaBetaPredictor(PredictionConfig(max_hold_ms=200.0))
        measurement = AimMeasurement(point=(100, 100), crosshair=(90, 100), error=(10.0, 0.0), valid=True)
        missing = AimMeasurement(point=None, crosshair=(90, 100), error=(0.0, 0.0), valid=False)

        predictor.update(measurement, RuntimeMode(active=True, firing=False), now=1.0)
        predicted = predictor.update(missing, RuntimeMode(active=True, firing=False), now=1.1)

        self.assertEqual(predicted.state, "held")
        self.assertIsNotNone(predicted.point)


class ControllerTest(unittest.TestCase):
    def test_controller_returns_noop_inside_deadzone(self):
        from visual_aiming.algorithms.control import RelativeController

        controller = RelativeController(ControlConfig(deadzone=3.0))
        predicted = AimMeasurement(point=(101, 100), crosshair=(100, 100), error=(1.0, 0.0), valid=True)

        command = controller.update(predicted.error, active=True, dt=1 / 240)

        self.assertEqual(command.mode, "none")
        self.assertEqual((command.dx, command.dy), (0, 0))
        self.assertEqual(command.reason, "deadzone")

    def test_controller_limits_large_step(self):
        from visual_aiming.algorithms.control import RelativeController

        controller = RelativeController(ControlConfig(deadzone=0.0, speed_gain=1000.0, max_speed=100000.0, max_step=5))

        command = controller.update((100.0, 0.0), active=True, dt=1.0)

        self.assertEqual(command.mode, "relative")
        self.assertEqual(command.dx, 5)
        self.assertTrue(command.limited)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_modular_algorithms -v`

Expected: FAIL with import error for `visual_aiming.algorithms.prediction`.

- [ ] **Step 3: Implement alpha-beta predictor**

Create `src/visual_aiming/algorithms/prediction.py`:

```python
from __future__ import annotations

import math
from typing import Optional

from visual_aiming.config.schema import PredictionConfig
from visual_aiming.core.schemas import AimMeasurement, Point, PredictedAim, RuntimeMode


class AlphaBetaPredictor:
    def __init__(self, config: PredictionConfig) -> None:
        self.config = config
        self.position: Optional[tuple[float, float]] = None
        self.velocity = (0.0, 0.0)
        self.last_time: Optional[float] = None

    def reset(self) -> None:
        self.position = None
        self.velocity = (0.0, 0.0)
        self.last_time = None

    def update(self, measurement: AimMeasurement, mode: RuntimeMode, now: float) -> PredictedAim:
        if not mode.active:
            self.reset()
            return PredictedAim(point=None, velocity=(0.0, 0.0), confidence=0.0, state="inactive")

        if measurement.valid and measurement.point is not None:
            return self._accept_measurement(measurement.point, mode, now)
        return self._predict_without_measurement(now)

    def _accept_measurement(self, point: Point, mode: RuntimeMode, now: float) -> PredictedAim:
        x, y = float(point[0]), float(point[1])
        if self.position is None or self.last_time is None:
            self.position = (x, y)
            self.velocity = (0.0, 0.0)
            self.last_time = now
            return PredictedAim(point=point, velocity=self.velocity, confidence=1.0, state="tracking")

        dt = max(1e-4, min(now - self.last_time, 0.12))
        predicted_x = self.position[0] + self.velocity[0] * dt
        predicted_y = self.position[1] + self.velocity[1] * dt
        residual_x = x - predicted_x
        residual_y = y - predicted_y

        if self.config.reset_distance > 0 and math.hypot(residual_x, residual_y) >= self.config.reset_distance:
            self.position = (x, y)
            self.velocity = (0.0, 0.0)
            self.last_time = now
            return PredictedAim(point=point, velocity=self.velocity, confidence=1.0, state="reset")

        alpha = max(0.01, min(0.95, self.config.alpha))
        beta = max(0.0, min(0.80, self.config.beta))
        self.position = (predicted_x + alpha * residual_x, predicted_y + alpha * residual_y)
        if not (mode.firing and self.config.firing_freeze):
            self.velocity = (
                self.velocity[0] + beta * residual_x / dt,
                self.velocity[1] + beta * residual_y / dt,
            )
        else:
            self.velocity = (0.0, 0.0)
        self.last_time = now
        return self._prediction(now, "tracking", 1.0)

    def _predict_without_measurement(self, now: float) -> PredictedAim:
        if self.position is None or self.last_time is None:
            return PredictedAim(point=None, velocity=(0.0, 0.0), confidence=0.0, state="lost")
        age_ms = max(0.0, (now - self.last_time) * 1000.0)
        if age_ms > max(0.0, self.config.max_hold_ms):
            self.reset()
            return PredictedAim(point=None, velocity=(0.0, 0.0), confidence=0.0, state="lost")
        confidence = max(0.0, 1.0 - age_ms / max(1.0, self.config.max_hold_ms))
        prediction = self._prediction(now, "held", confidence)
        return prediction

    def _prediction(self, now: float, state: str, confidence: float) -> PredictedAim:
        if self.position is None:
            return PredictedAim(point=None, velocity=(0.0, 0.0), confidence=0.0, state="lost")
        elapsed = 0.0 if self.last_time is None else max(0.0, min(now - self.last_time, 0.12))
        lead = max(0.0, min(self.config.lead_time + elapsed, 0.15))
        x = self.position[0] + self.velocity[0] * lead
        y = self.position[1] + self.velocity[1] * lead
        return PredictedAim(point=(int(round(x)), int(round(y))), velocity=self.velocity, confidence=confidence, state=state)
```

- [ ] **Step 4: Implement relative controller**

Create `src/visual_aiming/algorithms/control.py`:

```python
from __future__ import annotations

import math

from visual_aiming.config.schema import ControlConfig
from visual_aiming.core.schemas import ControlCommand, Vector


class RelativeController:
    def __init__(self, config: ControlConfig) -> None:
        self.config = config
        self.velocity = (0.0, 0.0)
        self.subpixel = (0.0, 0.0)

    def reset(self) -> None:
        self.velocity = (0.0, 0.0)
        self.subpixel = (0.0, 0.0)

    def update(self, error: Vector, active: bool, dt: float) -> ControlCommand:
        if not active:
            self.reset()
            return ControlCommand(mode="none", reason="inactive")

        dt = max(0.0005, min(float(dt), 0.05))
        distance = math.hypot(error[0], error[1])
        if distance <= max(0.0, self.config.deadzone):
            self.reset()
            return ControlCommand(mode="none", reason="deadzone")

        target_speed = min(max(0.0, self.config.max_speed), distance * max(0.0, self.config.speed_gain))
        decel_radius = max(self.config.deadzone + 1.0, self.config.decel_radius)
        if distance < decel_radius:
            scale = max(0.01, min(1.0, self.config.near_speed_scale))
            ratio = max(0.0, min(1.0, distance / decel_radius))
            target_speed *= scale + (1.0 - scale) * ratio

        direction = (error[0] / distance, error[1] / distance)
        target_velocity = (direction[0] * target_speed, direction[1] * target_speed)
        alpha = max(0.0, min(1.0, self.config.acceleration * dt))
        self.velocity = (
            self.velocity[0] + (target_velocity[0] - self.velocity[0]) * alpha,
            self.velocity[1] + (target_velocity[1] - self.velocity[1]) * alpha,
        )

        move_x = self.velocity[0] * dt * self.config.output_gain + self.subpixel[0]
        move_y = self.velocity[1] * dt * self.config.output_gain + self.subpixel[1]
        limited = False
        max_step = max(1.0, float(self.config.max_step))
        length = math.hypot(move_x, move_y)
        if length > max_step:
            limited = True
            scale = max_step / length
            move_x *= scale
            move_y *= scale

        dx = int(round(move_x))
        dy = int(round(move_y))
        self.subpixel = (move_x - dx, move_y - dy)
        if dx == 0 and dy == 0:
            return ControlCommand(mode="relative", reason="subpixel")
        return ControlCommand(dx=dx, dy=dy, mode="relative", limited=limited, reason="tracking")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_modular_algorithms -v`

Expected: PASS for target selection, aim, predictor, and controller tests.

- [ ] **Step 6: Commit**

```bash
git add src/visual_aiming/algorithms/prediction.py src/visual_aiming/algorithms/control.py tests/test_modular_algorithms.py
git commit -m "feat: add modular prediction and control"
```

## Task 5: Safe Output Backends

**Files:**
- Create: `src/visual_aiming/adapters/outputs/null_output.py`
- Create: `src/visual_aiming/adapters/outputs/log_output.py`
- Create: `src/visual_aiming/adapters/outputs/win_mouse.py`
- Test: `tests/test_modular_outputs.py`

- [ ] **Step 1: Write failing output tests**

Create `tests/test_modular_outputs.py`:

```python
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.core.schemas import (
    AimMeasurement,
    ControlCommand,
    DetectionPacket,
    PipelineTickResult,
    PredictedAim,
    RuntimeMode,
    SelectedTarget,
)


def make_result(command=None):
    command = command or ControlCommand(dx=3, dy=4, mode="relative", reason="tracking")
    return PipelineTickResult(
        sequence=1,
        timestamp=1.0,
        mode=RuntimeMode(active=True, firing=False),
        detections=DetectionPacket(sequence=1, detections=[], latency_ms=0.0, detector_name="fake"),
        selected=SelectedTarget(detection=None, score=float("inf"), reason="no_detections"),
        aim=AimMeasurement(point=None, crosshair=(100, 100), error=(0.0, 0.0), valid=False),
        predicted=PredictedAim(point=None, velocity=(0.0, 0.0), confidence=0.0, state="lost"),
        command=command,
        output_backend="test",
        pipeline_latency_ms=0.0,
    )


class OutputBackendTest(unittest.TestCase):
    def test_null_output_records_nothing_and_does_not_raise(self):
        from visual_aiming.adapters.outputs.null_output import NullOutput

        output = NullOutput()
        output.apply(ControlCommand(dx=10, dy=10, mode="relative"), make_result())
        output.close()

        self.assertEqual(output.name, "null")

    def test_log_output_keeps_commands_in_memory(self):
        from visual_aiming.adapters.outputs.log_output import LogOutput

        output = LogOutput()
        result = make_result(ControlCommand(dx=5, dy=-2, mode="relative", reason="tracking"))

        output.apply(result.command, result)

        self.assertEqual(len(output.commands), 1)
        self.assertEqual(output.commands[0].dx, 5)
        self.assertEqual(output.commands[0].dy, -2)

    def test_win_mouse_requires_explicit_enable(self):
        from visual_aiming.adapters.outputs.win_mouse import WinMouseOutput

        calls = []
        output = WinMouseOutput(enable_real_mouse=False, sender=lambda dx, dy: calls.append((dx, dy)))
        result = make_result(ControlCommand(dx=7, dy=8, mode="relative", reason="tracking"))

        output.apply(result.command, result)

        self.assertEqual(calls, [])

    def test_win_mouse_sends_when_enabled(self):
        from visual_aiming.adapters.outputs.win_mouse import WinMouseOutput

        calls = []
        output = WinMouseOutput(enable_real_mouse=True, sender=lambda dx, dy: calls.append((dx, dy)))
        result = make_result(ControlCommand(dx=7, dy=8, mode="relative", reason="tracking"))

        output.apply(result.command, result)

        self.assertEqual(calls, [(7, 8)])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_modular_outputs -v`

Expected: FAIL with import error for `visual_aiming.adapters.outputs.null_output`.

- [ ] **Step 3: Implement NullOutput and LogOutput**

Create `src/visual_aiming/adapters/outputs/null_output.py`:

```python
from __future__ import annotations

from visual_aiming.core.schemas import ControlCommand, PipelineTickResult


class NullOutput:
    name = "null"

    def apply(self, command: ControlCommand, result: PipelineTickResult) -> None:
        return None

    def close(self) -> None:
        return None
```

Create `src/visual_aiming/adapters/outputs/log_output.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from visual_aiming.core.schemas import ControlCommand, PipelineTickResult


class LogOutput:
    name = "log"

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(path) if path else None
        self.commands: List[ControlCommand] = []
        self._handle = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.path.open("a", encoding="utf-8")

    def apply(self, command: ControlCommand, result: PipelineTickResult) -> None:
        self.commands.append(command)
        if self._handle is not None:
            self._handle.write(f"{result.sequence},{command.mode},{command.dx},{command.dy},{command.reason}\n")
            self._handle.flush()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
```

- [ ] **Step 4: Implement WinMouseOutput with explicit enable**

Create `src/visual_aiming/adapters/outputs/win_mouse.py`:

```python
from __future__ import annotations

import ctypes
from typing import Callable, Optional

from visual_aiming.core.schemas import ControlCommand, PipelineTickResult

MOUSEEVENTF_MOVE = 0x0001


def send_relative_move(dx: int, dy: int) -> None:
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, int(dx), int(dy), 0, 0)


class WinMouseOutput:
    name = "win_mouse"

    def __init__(self, enable_real_mouse: bool, sender: Optional[Callable[[int, int], None]] = None) -> None:
        self.enable_real_mouse = bool(enable_real_mouse)
        self.sender = sender or send_relative_move

    def apply(self, command: ControlCommand, result: PipelineTickResult) -> None:
        if not self.enable_real_mouse:
            return
        if command.mode != "relative":
            return
        if command.dx == 0 and command.dy == 0:
            return
        self.sender(command.dx, command.dy)

    def close(self) -> None:
        return None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_modular_outputs -v`

Expected: PASS for all output backend tests.

- [ ] **Step 6: Commit**

```bash
git add src/visual_aiming/adapters/outputs tests/test_modular_outputs.py
git commit -m "feat: add safe modular output backends"
```

## Task 6: Pipeline Orchestrator

**Files:**
- Replace: `src/visual_aiming/core/pipeline.py`
- Test: `tests/test_modular_pipeline.py`
- Re-run: `tests/test_runtime_pipeline.py`

- [ ] **Step 1: Write failing modular pipeline tests**

Create `tests/test_modular_pipeline.py`:

```python
import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.config.schema import ModularConfig
from visual_aiming.core.schemas import Detection, DetectionPacket, FramePacket, RuntimeMode


class FakeDetector:
    name = "fake"

    def __init__(self, detections):
        self.detections = detections

    def detect(self, frame):
        return DetectionPacket(
            sequence=frame.sequence,
            detections=list(self.detections),
            latency_ms=0.5,
            detector_name=self.name,
            fresh=True,
        )


class FakeOutput:
    name = "fake_output"

    def __init__(self):
        self.applied = []

    def apply(self, command, result):
        self.applied.append((command, result))

    def close(self):
        return None


class ModularPipelineTest(unittest.TestCase):
    def make_frame(self, active=True, firing=False):
        return FramePacket(
            frame=np.zeros((100, 100, 3), dtype=np.uint8),
            timestamp=1.0,
            sequence=1,
            roi_offset=(100, 200),
            roi_size=(100, 100),
            crosshair=(150, 250),
            source="unit",
            mode=RuntimeMode(active=active, firing=firing),
        )

    def test_inactive_tick_outputs_noop_without_detection(self):
        from visual_aiming.core.pipeline import ModularPipeline

        output = FakeOutput()
        pipeline = ModularPipeline(ModularConfig(), FakeDetector([Detection((40, 40, 20, 20), 1.0, 0, "head")]), output)

        result = pipeline.tick(self.make_frame(active=False), now=1.0)

        self.assertEqual(result.command.mode, "none")
        self.assertEqual(result.command.reason, "inactive")
        self.assertEqual(len(output.applied), 1)
        self.assertEqual(result.detections.detections, [])

    def test_active_tick_detects_selects_aims_predicts_controls_and_outputs(self):
        from visual_aiming.core.pipeline import ModularPipeline

        output = FakeOutput()
        config = ModularConfig()
        config.control.deadzone = 0.0
        config.control.max_step = 6
        detection = Detection(bbox=(40, 40, 20, 20), confidence=1.0, class_id=0, class_name="head")
        pipeline = ModularPipeline(config, FakeDetector([detection]), output)

        result = pipeline.tick(self.make_frame(active=True), now=1.0)

        self.assertEqual(result.selected.detection.bbox, detection.bbox)
        self.assertEqual(result.aim.point, (150, 250))
        self.assertEqual(result.predicted.point, (150, 250))
        self.assertEqual(result.command.mode, "none")
        self.assertEqual(result.command.reason, "deadzone")
        self.assertEqual(len(output.applied), 1)

    def test_active_tick_with_offset_target_emits_relative_command(self):
        from visual_aiming.core.pipeline import ModularPipeline

        output = FakeOutput()
        config = ModularConfig()
        config.control.deadzone = 0.0
        config.control.max_step = 6
        detection = Detection(bbox=(50, 40, 20, 20), confidence=1.0, class_id=0, class_name="head")
        pipeline = ModularPipeline(config, FakeDetector([detection]), output)

        result = pipeline.tick(self.make_frame(active=True), now=1.0)

        self.assertEqual(result.command.mode, "relative")
        self.assertGreater(result.command.dx, 0)
        self.assertEqual(len(output.applied), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_modular_pipeline -v`

Expected: FAIL with import error for `ModularPipeline` or method mismatch.

- [ ] **Step 3: Replace pipeline with modular pipeline plus compatibility RuntimePipeline**

Replace `src/visual_aiming/core/pipeline.py` with this content. It keeps the existing `RuntimePipeline` API at the bottom so current tests and runtime continue to import it.

```python
from __future__ import annotations

import time
from typing import Callable, Optional

from visual_aiming.algorithms.aim_point import AimStrategy
from visual_aiming.algorithms.control import RelativeController
from visual_aiming.algorithms.prediction import AlphaBetaPredictor
from visual_aiming.algorithms.target_selection import TargetSelector
from visual_aiming.config.schema import ModularConfig
from visual_aiming.core.runtime_state import RuntimeState
from visual_aiming.core.schemas import (
    AimMeasurement,
    ControlCommand,
    ControlTarget,
    DetectionPacket,
    PipelineResult,
    PipelineTickResult,
    Point,
    PredictedAim,
    RuntimeMode,
    SelectedTarget,
)


class ModularPipeline:
    def __init__(self, config: ModularConfig, detector, output_backend, diagnostics=None) -> None:
        self.config = config
        self.detector = detector
        self.output_backend = output_backend
        self.diagnostics = diagnostics
        self.selector = TargetSelector(config.target_selection)
        self.aim_strategy = AimStrategy(config.aim, config.target_selection.head_class_id)
        self.predictor = AlphaBetaPredictor(config.prediction)
        self.controller = RelativeController(config.control)

    def reset(self) -> None:
        self.selector.reset()
        self.predictor.reset()
        self.controller.reset()

    def tick(self, frame, now: Optional[float] = None) -> PipelineTickResult:
        started = time.perf_counter()
        now = frame.timestamp if now is None else now
        mode = frame.mode

        if not mode.active:
            self.reset()
            detections = DetectionPacket(frame.sequence, [], 0.0, getattr(self.detector, "name", "detector"), fresh=False)
            result = self._build_result(
                frame=frame,
                mode=mode,
                detections=detections,
                selected=SelectedTarget(detection=None, score=float("inf"), reason="inactive"),
                aim=AimMeasurement(point=None, crosshair=frame.crosshair, error=(0.0, 0.0), valid=False),
                predicted=PredictedAim(point=None, velocity=(0.0, 0.0), confidence=0.0, state="inactive"),
                command=ControlCommand(mode="none", reason="inactive"),
                started=started,
            )
            self._publish(result)
            return result

        detections = self.detector.detect(frame)
        roi_center = (frame.roi_size[0] // 2, frame.roi_size[1] // 2)
        selected = self.selector.select(detections.detections, roi_center=roi_center)
        aim = self.aim_strategy.measure(selected.detection, frame.roi_offset, frame.crosshair)
        predicted = self.predictor.update(aim, mode, now)
        error = self._error_from_prediction(predicted, frame.crosshair)
        command = self.controller.update(error, active=mode.active, dt=1.0 / max(1.0, self.config.runtime.poll_fps))
        result = self._build_result(frame, mode, detections, selected, aim, predicted, command, started)
        self._publish(result)
        return result

    def _error_from_prediction(self, predicted: PredictedAim, crosshair: Point) -> tuple[float, float]:
        if predicted.point is None:
            return (0.0, 0.0)
        return (float(predicted.point[0] - crosshair[0]), float(predicted.point[1] - crosshair[1]))

    def _build_result(self, frame, mode, detections, selected, aim, predicted, command, started) -> PipelineTickResult:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return PipelineTickResult(
            sequence=frame.sequence,
            timestamp=frame.timestamp,
            mode=mode,
            detections=detections,
            selected=selected,
            aim=aim,
            predicted=predicted,
            command=command,
            output_backend=getattr(self.output_backend, "name", "unknown"),
            pipeline_latency_ms=latency_ms,
        )

    def _publish(self, result: PipelineTickResult) -> None:
        self.output_backend.apply(result.command, result)
        if self.diagnostics is not None:
            self.diagnostics.write(result)


class RuntimePipeline:
    def __init__(
        self,
        config,
        aim_calculator,
        tracker=None,
        state: Optional[RuntimeState] = None,
        fallback_point: Optional[Callable[[], Point]] = None,
    ):
        self.config = config
        self.aim_calculator = aim_calculator
        self.tracker = tracker
        self.state = state or RuntimeState()
        self.fallback_point = fallback_point

    def reset(self) -> None:
        self.state.reset_tracking_state()
        if self.tracker is not None:
            self.tracker.reset()

    def current_control(self, active: bool, crosshair: Optional[Point]) -> ControlTarget:
        if not active:
            return ControlTarget(target=None, crosshair=crosshair, has_measurement=False, active=False)
        if self.state.last_aim_base is None:
            self.state.last_aim_base = self._fallback(crosshair)
        return ControlTarget(target=self.state.last_aim_base, crosshair=crosshair, has_measurement=False, active=True)

    def process_detection(self, active, firing, target, target_is_fresh, roi_offset, crosshair, now) -> PipelineResult:
        if not active:
            return PipelineResult(ControlTarget(None, crosshair, False, active), None, None)
        aim_base = None
        if roi_offset is not None:
            roi_left, roi_top = roi_offset
            raw_aim = self.aim_calculator.calculate(target, roi_left, roi_top)
            aim_base = raw_aim if target_is_fresh else None
            fresh_measurement = target_is_fresh and target is not None and aim_base is not None
            tracker_allowed = not (firing and bool(getattr(self.config, "firing_disable_tracker_prediction", True)))
            if fresh_measurement and self.tracker is not None and tracker_allowed:
                aim_base = self.tracker.update(aim_base, now)
            elif fresh_measurement and self.tracker is not None and not tracker_allowed:
                self.tracker.reset()
            self._update_last_aim(target, target_is_fresh, aim_base, firing, crosshair)

        base_target = aim_base
        used_tracker_prediction = False
        tracker_allowed = not (firing and bool(getattr(self.config, "firing_disable_tracker_prediction", True)))
        if base_target is None and self.tracker is not None and tracker_allowed and self.tracker.has_recent_track(now, float(getattr(self.config, "tracker_max_prediction_ms", 160.0))):
            base_target = self.tracker.predict(now)
            used_tracker_prediction = True
        if base_target is None and self.state.last_aim_base is not None:
            base_target = self.state.last_aim_base
        has_measurement = aim_base is not None
        if not has_measurement and used_tracker_prediction and bool(getattr(self.config, "tracker_prediction_as_measurement", True)):
            has_measurement = True
        control = ControlTarget(target=base_target, crosshair=crosshair, has_measurement=has_measurement, active=active)
        return PipelineResult(control=control, aim_point=aim_base, debug_bbox=getattr(target, "bbox", None) if target is not None else None, used_tracker_prediction=used_tracker_prediction)

    def _update_last_aim(self, target, target_is_fresh, aim_base, firing, crosshair) -> None:
        if target is not None and target_is_fresh:
            if aim_base is not None:
                self.state.last_aim_base = aim_base
            elif not self._hold_last_aim(firing):
                self.state.last_aim_base = self._fallback(crosshair)
            return
        if target is None:
            if aim_base is not None:
                self.state.last_aim_base = aim_base
            elif not self._hold_last_aim(firing):
                self.state.last_aim_base = self._fallback(crosshair)

    def _hold_last_aim(self, firing: bool) -> bool:
        return firing and bool(getattr(self.config, "firing_hold_last_aim", True)) and self.state.last_aim_base is not None

    def _fallback(self, crosshair: Optional[Point]) -> Optional[Point]:
        if crosshair is not None:
            return crosshair
        if self.fallback_point is not None:
            return self.fallback_point()
        return None
```

- [ ] **Step 4: Run modular and legacy pipeline tests**

Run: `python -m unittest tests.test_modular_pipeline tests.test_runtime_pipeline -v`

Expected: PASS. The modular tests validate new orchestration and existing runtime pipeline tests confirm compatibility.

- [ ] **Step 5: Commit**

```bash
git add src/visual_aiming/core/pipeline.py tests/test_modular_pipeline.py
git commit -m "feat: add modular pipeline orchestrator"
```

## Task 7: Diagnostics JSONL and Summary Metrics

**Files:**
- Create: `src/visual_aiming/core/metrics.py`
- Test: `tests/test_modular_metrics.py`

- [ ] **Step 1: Write failing metrics tests**

Create `tests/test_modular_metrics.py`:

```python
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tests.test_modular_outputs import make_result
from visual_aiming.core.schemas import ControlCommand


class DiagnosticsMetricsTest(unittest.TestCase):
    def test_jsonl_diagnostics_writes_records_and_summary(self):
        from visual_aiming.core.metrics import JsonlDiagnostics

        with tempfile.TemporaryDirectory() as tmp:
            jsonl = Path(tmp) / "run.jsonl"
            summary_path = Path(tmp) / "summary.json"
            diagnostics = JsonlDiagnostics(jsonl, summary_path)
            diagnostics.write(make_result(ControlCommand(dx=3, dy=4, mode="relative", reason="tracking")))
            diagnostics.write(make_result(ControlCommand(dx=0, dy=0, mode="none", reason="deadzone")))
            diagnostics.close()

            records = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["command"]["dx"], 3)
            self.assertEqual(summary["samples"], 2)
            self.assertEqual(summary["max_command_magnitude"], 5.0)
            self.assertEqual(summary["noop_commands"], 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_modular_metrics -v`

Expected: FAIL with import error for `visual_aiming.core.metrics`.

- [ ] **Step 3: Implement JSONL diagnostics**

Create `src/visual_aiming/core/metrics.py`:

```python
from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from visual_aiming.core.schemas import PipelineTickResult


class JsonlDiagnostics:
    name = "jsonl"

    def __init__(self, jsonl_path: str | Path, summary_path: Optional[str | Path] = None) -> None:
        self.jsonl_path = Path(jsonl_path)
        self.summary_path = Path(summary_path) if summary_path is not None else self.jsonl_path.with_suffix(".summary.json")
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.jsonl_path.open("w", encoding="utf-8")
        self.samples = 0
        self.noop_commands = 0
        self.max_command_magnitude = 0.0
        self.total_command_magnitude = 0.0
        self.target_lost = 0
        self.target_switches = 0
        self.max_detector_latency_ms = 0.0
        self.max_pipeline_latency_ms = 0.0

    def write(self, result: PipelineTickResult) -> None:
        record = self._record(result)
        self._handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._handle.flush()
        self._accumulate(result)

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()
        self.summary_path.write_text(json.dumps(self.summary(), ensure_ascii=False, indent=2), encoding="utf-8")

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_modular_metrics -v`

Expected: PASS for diagnostics metrics test.

- [ ] **Step 5: Commit**

```bash
git add src/visual_aiming/core/metrics.py tests/test_modular_metrics.py
git commit -m "feat: add modular diagnostics metrics"
```

## Task 8: Detector and Frame Source Adapters

**Files:**
- Create: `src/visual_aiming/adapters/detectors/ultralytics_yolo.py`
- Create: `src/visual_aiming/adapters/frame_sources/video_file.py`
- Create: `src/visual_aiming/adapters/frame_sources/screen_capture.py`
- Test: `tests/test_modular_adapters.py`

- [ ] **Step 1: Write failing adapter tests**

Create `tests/test_modular_adapters.py`:

```python
import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.config.schema import DetectorConfig, FrameSourceConfig
from visual_aiming.core.schemas import FramePacket, RuntimeMode


class LegacyDetectedTarget:
    def __init__(self):
        self.bbox = (1, 2, 3, 4)
        self.confidence = 0.9
        self.class_id = 0
        self.class_name = "head"


class FakeLegacyDetector:
    last_result_fresh = True

    def detect(self, frame, config, roi_center=None, firing=False):
        self.called_with = (frame, config, roi_center, firing)
        return LegacyDetectedTarget()


class AdapterTest(unittest.TestCase):
    def test_ultralytics_adapter_normalizes_legacy_detector_result(self):
        from visual_aiming.adapters.detectors.ultralytics_yolo import UltralyticsYoloDetector

        legacy = FakeLegacyDetector()
        adapter = UltralyticsYoloDetector(DetectorConfig(), legacy_detector=legacy)
        frame = FramePacket(
            frame=np.zeros((10, 20, 3), dtype=np.uint8),
            timestamp=1.0,
            sequence=5,
            roi_offset=(0, 0),
            roi_size=(20, 10),
            crosshair=(10, 5),
            source="unit",
            mode=RuntimeMode(active=True, firing=True),
        )

        packet = adapter.detect(frame)

        self.assertEqual(packet.sequence, 5)
        self.assertEqual(packet.detections[0].bbox, (1, 2, 3, 4))
        self.assertTrue(packet.fresh)
        self.assertEqual(legacy.called_with[2], (10, 5))
        self.assertTrue(legacy.called_with[3])

    def test_array_frame_source_emits_frame_packets_for_replay_tests(self):
        from visual_aiming.adapters.frame_sources.video_file import ArrayFrameSource

        frames = [np.zeros((4, 6, 3), dtype=np.uint8), np.ones((4, 6, 3), dtype=np.uint8)]
        source = ArrayFrameSource(frames, fps=20.0, roi_offset=(10, 20), crosshair=(13, 22), source="array")

        first = source.read()
        second = source.read()
        third = source.read()

        self.assertEqual(first.sequence, 0)
        self.assertEqual(first.timestamp, 0.0)
        self.assertEqual(second.sequence, 1)
        self.assertEqual(second.timestamp, 0.05)
        self.assertIsNone(third)

    def test_screen_frame_source_wraps_grabber(self):
        from visual_aiming.adapters.frame_sources.screen_capture import ScreenFrameSource

        calls = []
        def grabber():
            calls.append(True)
            return np.zeros((4, 6, 3), dtype=np.uint8)

        source = ScreenFrameSource(
            FrameSourceConfig(roi_size=(6, 4)),
            roi_offset=(10, 20),
            crosshair=(13, 22),
            grabber=grabber,
            clock=lambda: 12.5,
        )

        packet = source.read()

        self.assertEqual(packet.sequence, 0)
        self.assertEqual(packet.timestamp, 12.5)
        self.assertEqual(packet.roi_offset, (10, 20))
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_modular_adapters -v`

Expected: FAIL with import error for `visual_aiming.adapters.detectors.ultralytics_yolo`.

- [ ] **Step 3: Implement ultralytics detector adapter**

Create `src/visual_aiming/adapters/detectors/ultralytics_yolo.py`:

```python
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Optional

from visual_aiming.config.schema import DetectorConfig
from visual_aiming.core.schemas import Detection, DetectionPacket, FramePacket
from visual_aiming.vision.detection import TargetDetector


class UltralyticsYoloDetector:
    name = "ultralytics"

    def __init__(self, config: DetectorConfig, legacy_detector: Optional[TargetDetector] = None) -> None:
        self.config = config
        self.legacy_detector = legacy_detector or TargetDetector()

    def detect(self, frame: FramePacket) -> DetectionPacket:
        started = time.perf_counter()
        legacy_config = self._legacy_config()
        target = self.legacy_detector.detect(
            frame.frame,
            legacy_config,
            roi_center=(frame.roi_size[0] // 2, frame.roi_size[1] // 2),
            firing=frame.mode.firing,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        detections = []
        if target is not None:
            detections.append(Detection(
                bbox=target.bbox,
                confidence=float(getattr(target, "confidence", 0.0)),
                class_id=getattr(target, "class_id", None),
                class_name=str(getattr(target, "class_name", "unknown")),
            ))
        fresh = bool(getattr(self.legacy_detector, "last_result_fresh", True))
        return DetectionPacket(frame.sequence, detections, latency_ms, self.name, fresh=fresh)

    def _legacy_config(self):
        return SimpleNamespace(
            yolo_model_path=self.config.model_path,
            yolo_conf_threshold=self.config.confidence,
            yolo_iou_threshold=self.config.iou,
            yolo_device=self.config.device,
            yolo_half=self.config.half,
            yolo_imgsz=self.config.imgsz,
            yolo_head_class_id=0,
            yolo_person_class_id=1,
            target_stickiness=0.0,
            target_history_radius=1,
            target_switch_margin=0.0,
            target_class_switch_penalty=0.0,
            aim_target_preference=1.0,
            yolo_skip_frames=0,
            firing_yolo_skip_frames=0,
        )
```

- [ ] **Step 4: Implement replay and screen frame sources**

Create `src/visual_aiming/adapters/frame_sources/video_file.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np

from visual_aiming.core.schemas import FramePacket, Point, RuntimeMode


class ArrayFrameSource:
    name = "array"

    def __init__(self, frames: Iterable[np.ndarray], fps: float, roi_offset: Point, crosshair: Point, source: str = "array") -> None:
        self.frames = list(frames)
        self.fps = max(1.0, float(fps))
        self.roi_offset = roi_offset
        self.crosshair = crosshair
        self.source = source
        self.index = 0

    def read(self) -> Optional[FramePacket]:
        if self.index >= len(self.frames):
            return None
        frame = self.frames[self.index]
        sequence = self.index
        self.index += 1
        return FramePacket(
            frame=frame,
            timestamp=sequence / self.fps,
            sequence=sequence,
            roi_offset=self.roi_offset,
            roi_size=(frame.shape[1], frame.shape[0]),
            crosshair=self.crosshair,
            source=self.source,
            mode=RuntimeMode(active=True, firing=False),
        )

    def close(self) -> None:
        return None


class VideoFileFrameSource:
    name = "video_file"

    def __init__(self, path: str | Path, roi_offset: Point, crosshair: Point) -> None:
        self.path = str(path)
        self.capture = cv2.VideoCapture(self.path)
        if not self.capture.isOpened():
            raise FileNotFoundError(f"Cannot open video file: {self.path}")
        fps = self.capture.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and fps > 0 else 30.0
        self.roi_offset = roi_offset
        self.crosshair = crosshair
        self.sequence = 0

    def read(self) -> Optional[FramePacket]:
        ok, frame = self.capture.read()
        if not ok:
            return None
        sequence = self.sequence
        self.sequence += 1
        return FramePacket(
            frame=frame,
            timestamp=sequence / self.fps,
            sequence=sequence,
            roi_offset=self.roi_offset,
            roi_size=(frame.shape[1], frame.shape[0]),
            crosshair=self.crosshair,
            source=self.name,
            mode=RuntimeMode(active=True, firing=False),
        )

    def close(self) -> None:
        self.capture.release()
```

Create `src/visual_aiming/adapters/frame_sources/screen_capture.py`:

```python
from __future__ import annotations

import time
from typing import Callable, Optional

import numpy as np

from visual_aiming.config.schema import FrameSourceConfig
from visual_aiming.core.schemas import FramePacket, Point, RuntimeMode
from visual_aiming.vision.screen_capture import ScreenCapture


class ScreenFrameSource:
    name = "screen"

    def __init__(
        self,
        config: FrameSourceConfig,
        roi_offset: Point,
        crosshair: Point,
        grabber: Optional[Callable[[], Optional[np.ndarray]]] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self.roi_offset = roi_offset
        self.crosshair = crosshair
        self.grabber = grabber
        self.clock = clock
        self.sequence = 0
        self._screen_capture = None

    def read(self) -> Optional[FramePacket]:
        frame = self.grabber() if self.grabber is not None else self._grab_with_screen_capture()
        if frame is None:
            return None
        sequence = self.sequence
        self.sequence += 1
        return FramePacket(
            frame=frame,
            timestamp=self.clock(),
            sequence=sequence,
            roi_offset=self.roi_offset,
            roi_size=self.config.roi_size,
            crosshair=self.crosshair,
            source=self.name,
            mode=RuntimeMode(active=True, firing=False),
        )

    def _grab_with_screen_capture(self):
        if self._screen_capture is None:
            wakeup = _FixedGeometryWakeup(self.roi_offset)
            legacy_config = _LegacyFrameConfig(self.config.roi_size)
            self._screen_capture = ScreenCapture(legacy_config, wakeup)
        return self._screen_capture.grab()

    def close(self) -> None:
        if self._screen_capture is not None:
            self._screen_capture.close()
            self._screen_capture = None


class _FixedGeometryWakeup:
    def __init__(self, roi_offset: Point) -> None:
        self.roi_offset = roi_offset

    def get_roi_offset(self) -> Point:
        return self.roi_offset


class _LegacyFrameConfig:
    def __init__(self, roi_size: Point) -> None:
        self.roi_width = roi_size[0]
        self.roi_height = roi_size[1]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_modular_adapters -v`

Expected: PASS for detector and frame source adapter tests.

- [ ] **Step 6: Commit**

```bash
git add src/visual_aiming/adapters/detectors src/visual_aiming/adapters/frame_sources tests/test_modular_adapters.py
git commit -m "feat: add modular detector and frame sources"
```

## Task 9: Replay and Realtime App Composition

**Files:**
- Create: `src/visual_aiming/app/replay.py`
- Create: `src/visual_aiming/app/realtime.py`
- Modify: `src/visual_aiming/app.py`
- Test: `tests/test_modular_apps.py`

- [ ] **Step 1: Write failing app composition tests**

Create `tests/test_modular_apps.py`:

```python
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming.config.schema import ModularConfig


class ModularAppsTest(unittest.TestCase):
    def test_output_factory_defaults_to_null(self):
        from visual_aiming.app.realtime import create_output_backend

        config = ModularConfig()
        output = create_output_backend(config.output)

        self.assertEqual(output.name, "null")

    def test_output_factory_requires_real_mouse_flag(self):
        from visual_aiming.app.realtime import create_output_backend

        config = ModularConfig()
        config.output.backend = "win_mouse"
        config.output.enable_real_mouse = False

        output = create_output_backend(config.output)

        self.assertEqual(output.name, "null")

    def test_output_factory_returns_win_mouse_when_explicitly_enabled(self):
        from visual_aiming.app.realtime import create_output_backend

        config = ModularConfig()
        config.output.backend = "win_mouse"
        config.output.enable_real_mouse = True

        output = create_output_backend(config.output, mouse_sender=lambda dx, dy: None)

        self.assertEqual(output.name, "win_mouse")

    def test_replay_runner_processes_all_frames(self):
        import numpy as np
        from visual_aiming.adapters.frame_sources.video_file import ArrayFrameSource
        from visual_aiming.app.replay import run_replay
        from visual_aiming.core.schemas import DetectionPacket

        class EmptyDetector:
            name = "empty"
            def detect(self, frame):
                return DetectionPacket(frame.sequence, [], 0.0, self.name, fresh=True)

        frames = [np.zeros((4, 6, 3), dtype=np.uint8), np.zeros((4, 6, 3), dtype=np.uint8)]
        source = ArrayFrameSource(frames, fps=10.0, roi_offset=(0, 0), crosshair=(3, 2))

        results = run_replay(ModularConfig(), source, EmptyDetector())

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].sequence, 0)
        self.assertEqual(results[1].sequence, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_modular_apps -v`

Expected: FAIL with import error for `visual_aiming.app.realtime`.

- [ ] **Step 3: Implement realtime composition helpers**

Create `src/visual_aiming/app/realtime.py`:

```python
from __future__ import annotations

from typing import Callable, Optional

from visual_aiming.adapters.detectors.ultralytics_yolo import UltralyticsYoloDetector
from visual_aiming.adapters.outputs.log_output import LogOutput
from visual_aiming.adapters.outputs.null_output import NullOutput
from visual_aiming.adapters.outputs.win_mouse import WinMouseOutput
from visual_aiming.config.schema import ModularConfig, OutputConfig
from visual_aiming.core.metrics import JsonlDiagnostics
from visual_aiming.core.pipeline import ModularPipeline


def create_output_backend(output_config: OutputConfig, mouse_sender: Optional[Callable[[int, int], None]] = None):
    if output_config.backend == "log":
        return LogOutput(output_config.log_path or None)
    if output_config.backend == "win_mouse" and output_config.enable_real_mouse:
        return WinMouseOutput(enable_real_mouse=True, sender=mouse_sender)
    return NullOutput()


def create_pipeline(config: ModularConfig, frame_source=None, detector=None, output_backend=None, diagnostics=None) -> ModularPipeline:
    detector = detector or UltralyticsYoloDetector(config.detector)
    output_backend = output_backend or create_output_backend(config.output)
    if diagnostics is None and config.diagnostics.enabled and config.diagnostics.jsonl_path:
        diagnostics = JsonlDiagnostics(config.diagnostics.jsonl_path, config.diagnostics.summary_path or None)
    return ModularPipeline(config, detector, output_backend, diagnostics)
```

- [ ] **Step 4: Implement replay runner**

Create `src/visual_aiming/app/replay.py`:

```python
from __future__ import annotations

from typing import List, Optional

from visual_aiming.adapters.detectors.ultralytics_yolo import UltralyticsYoloDetector
from visual_aiming.adapters.frame_sources.video_file import VideoFileFrameSource
from visual_aiming.app.realtime import create_output_backend
from visual_aiming.config.schema import ModularConfig
from visual_aiming.core.metrics import JsonlDiagnostics
from visual_aiming.core.pipeline import ModularPipeline
from visual_aiming.core.schemas import PipelineTickResult


def run_replay(config: ModularConfig, frame_source, detector=None, output_backend=None, diagnostics=None) -> List[PipelineTickResult]:
    detector = detector or UltralyticsYoloDetector(config.detector)
    output_backend = output_backend or create_output_backend(config.output)
    if diagnostics is None and config.diagnostics.enabled and config.diagnostics.jsonl_path:
        diagnostics = JsonlDiagnostics(config.diagnostics.jsonl_path, config.diagnostics.summary_path or None)
    pipeline = ModularPipeline(config, detector, output_backend, diagnostics)
    results: List[PipelineTickResult] = []
    try:
        while True:
            frame = frame_source.read()
            if frame is None:
                break
            results.append(pipeline.tick(frame, now=frame.timestamp))
    finally:
        frame_source.close()
        output_backend.close()
        if diagnostics is not None:
            diagnostics.close()
    return results


def run_video_file(config: ModularConfig, video_path: str, roi_offset=(0, 0), crosshair=(0, 0)) -> List[PipelineTickResult]:
    source = VideoFileFrameSource(video_path, roi_offset=roi_offset, crosshair=crosshair)
    return run_replay(config, source)
```

- [ ] **Step 5: Modify app module to expose modular helpers**

If `src/visual_aiming/app.py` is empty or only contains legacy compatibility, set it to:

```python
from visual_aiming.app.realtime import create_output_backend, create_pipeline
from visual_aiming.app.replay import run_replay, run_video_file

__all__ = [
    "create_output_backend",
    "create_pipeline",
    "run_replay",
    "run_video_file",
]
```

If `src/visual_aiming/app.py` already contains code, keep the existing public symbols and add the imports above at the bottom with the same `__all__` names included.

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m unittest tests.test_modular_apps -v`

Expected: PASS for app composition and replay runner tests.

- [ ] **Step 7: Commit**

```bash
git add src/visual_aiming/app.py src/visual_aiming/app tests/test_modular_apps.py
git commit -m "feat: add modular app composition"
```

## Task 10: Modular CLI Entry Point and Verification

**Files:**
- Modify: `main.py`
- Test: `tests/test_modular_apps.py`

- [ ] **Step 1: Add failing CLI argument tests**

Append this test class to `tests/test_modular_apps.py` before the `if __name__ == "__main__"` block:

```python
class ModularCliTest(unittest.TestCase):
    def test_main_parser_accepts_modular_safe_flags(self):
        from main import parse_args

        args = parse_args(["--modular", "--video", "sample.mp4", "--output", "log", "--diagnostics", "run.jsonl"])

        self.assertTrue(args.modular)
        self.assertEqual(args.video, "sample.mp4")
        self.assertEqual(args.output, "log")
        self.assertEqual(args.diagnostics, "run.jsonl")
        self.assertFalse(args.real_mouse)

    def test_main_parser_accepts_explicit_real_mouse_flag(self):
        from main import parse_args

        args = parse_args(["--modular", "--real-mouse", "--output", "win_mouse"])

        self.assertTrue(args.modular)
        self.assertTrue(args.real_mouse)
        self.assertEqual(args.output, "win_mouse")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_modular_apps -v`

Expected: FAIL because `main.parse_args` does not exist.

- [ ] **Step 3: Modify `main.py` to route modular mode safely**

Update `main.py` so it contains this shape while preserving the existing legacy runtime path:

```python
# -*- coding: utf-8 -*-
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Visual aiming runtime")
    parser.add_argument("--modular", action="store_true", help="Run the new modular runtime")
    parser.add_argument("--video", default="", help="Run modular replay on a video file")
    parser.add_argument("--output", choices=["null", "log", "win_mouse"], default="null", help="Modular output backend")
    parser.add_argument("--real-mouse", action="store_true", help="Allow real mouse movement when --output win_mouse is selected")
    parser.add_argument("--diagnostics", default="", help="Write modular diagnostics JSONL to this path")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.modular:
        return _run_modular(args)
    from visual_aiming.core.runtime import main as legacy_main
    return legacy_main()


def _run_modular(args):
    from visual_aiming.config.loader import load_modular_config

    config = load_modular_config("config.json")
    config.output.backend = args.output
    config.output.enable_real_mouse = bool(args.real_mouse)
    config.diagnostics.jsonl_path = args.diagnostics
    if args.video:
        from visual_aiming.app.replay import run_video_file
        run_video_file(config, args.video)
        return 0
    from visual_aiming.core.runtime import main as legacy_main
    print("[modular] Realtime modular composition is available, but legacy realtime loop remains default until screen activation is migrated.")
    return legacy_main()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run modular app tests**

Run: `python -m unittest tests.test_modular_apps -v`

Expected: PASS for app composition and CLI parser tests.

- [ ] **Step 5: Run full test suite**

Run: `python -m unittest discover tests -v`

Expected: PASS for all tests that do not require a real YOLO model or hardware-only environment. If a pre-existing hardware/model test fails because the model file is absent, record the exact failing test and run the modular suite separately:

```bash
python -m unittest \
  tests.test_modular_schemas_config \
  tests.test_modular_algorithms \
  tests.test_modular_outputs \
  tests.test_modular_pipeline \
  tests.test_modular_metrics \
  tests.test_modular_adapters \
  tests.test_modular_apps \
  -v
```

Expected: PASS for all modular tests.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_modular_apps.py
git commit -m "feat: add safe modular cli entrypoint"
```

## Task 11: Final Documentation and Compatibility Check

**Files:**
- Modify: `docs/PROJECT_STRUCTURE.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Document the modular runtime structure**

In `docs/PROJECT_STRUCTURE.md`, add this section near the existing package overview:

```markdown
## Modular Algorithm Runtime

The first-version modular runtime lives beside the legacy realtime runtime. It is organized around replaceable ports:

```text
FrameSource -> Detector -> TargetSelector -> AimStrategy -> Predictor -> Controller -> OutputBackend
```

Realtime and replay modes are expected to share `visual_aiming.core.pipeline.ModularPipeline`. The default modular output backend is `NullOutput`, so modular runs do not move the mouse unless `--output win_mouse --real-mouse` is passed.

Key modules:

- `visual_aiming.core.schemas`: normalized frame, detection, aim, prediction, command, and tick-result dataclasses.
- `visual_aiming.ports`: Protocol boundaries for frame sources, detectors, outputs, and diagnostics.
- `visual_aiming.algorithms`: pure target selection, aim point, prediction, and control logic.
- `visual_aiming.adapters`: wrappers for screen/video input, ultralytics YOLO, and output backends.
- `visual_aiming.app.replay`: safe replay runner.
- `visual_aiming.app.realtime`: composition helpers for realtime mode.
```

- [ ] **Step 2: Document safe modular command examples**

In `CLAUDE.md`, add these commands under `运行命令`:

```bash
python main.py --modular --video path/to/video.mp4 --output null             # 安全视频回放，不移动鼠标
python main.py --modular --video path/to/video.mp4 --output log --diagnostics tests/logs/run.jsonl
python main.py --modular --output win_mouse --real-mouse                    # 显式允许真实鼠标输出
```

Also add one sentence to the architecture section:

```markdown
新模块化算法运行时将输入源、检测器、目标选择、瞄点、预测、控制器和输出后端分离；默认输出为 NullOutput，不会移动真实鼠标。
```

- [ ] **Step 3: Run documentation-safe import checks**

Run:

```bash
python -m py_compile \
  main.py \
  src/visual_aiming/core/schemas.py \
  src/visual_aiming/core/pipeline.py \
  src/visual_aiming/core/metrics.py \
  src/visual_aiming/algorithms/target_selection.py \
  src/visual_aiming/algorithms/aim_point.py \
  src/visual_aiming/algorithms/prediction.py \
  src/visual_aiming/algorithms/control.py
```

Expected: command exits 0.

- [ ] **Step 4: Run modular tests**

Run:

```bash
python -m unittest \
  tests.test_modular_schemas_config \
  tests.test_modular_algorithms \
  tests.test_modular_outputs \
  tests.test_modular_pipeline \
  tests.test_modular_metrics \
  tests.test_modular_adapters \
  tests.test_modular_apps \
  -v
```

Expected: PASS for all modular tests.

- [ ] **Step 5: Commit**

```bash
git add docs/PROJECT_STRUCTURE.md CLAUDE.md
git commit -m "docs: document modular runtime"
```

## Final Verification

- [ ] **Step 1: Show git status**

Run: `git status --short`

Expected: only user-owned pre-existing files remain modified, or the working tree is clean if implementation ran in an isolated worktree.

- [ ] **Step 2: Run modular test suite**

Run:

```bash
python -m unittest \
  tests.test_modular_schemas_config \
  tests.test_modular_algorithms \
  tests.test_modular_outputs \
  tests.test_modular_pipeline \
  tests.test_modular_metrics \
  tests.test_modular_adapters \
  tests.test_modular_apps \
  -v
```

Expected: PASS.

- [ ] **Step 3: Run compatibility tests**

Run: `python -m unittest tests.test_runtime_pipeline tests.test_detector_device tests.test_config_window_sections -v`

Expected: PASS. If a detector device test fails because environment-specific CUDA availability differs, capture the exact output and do not claim it passed.

- [ ] **Step 4: Confirm safe CLI parse**

Run: `python -c "import main; a=main.parse_args(['--modular','--video','x.mp4','--output','null']); print(a.modular, a.real_mouse, a.output)"`

Expected output includes: `True False null`.

- [ ] **Step 5: Confirm no real mouse output by default**

Run: `python -c "from visual_aiming.app.realtime import create_output_backend; from visual_aiming.config.schema import ModularConfig; c=ModularConfig(); print(create_output_backend(c.output).name)"`

Expected output: `null`.

## Plan Self-Review

Spec coverage:

- Shared realtime/replay pipeline: Tasks 6, 8, 9, and 10.
- Replaceable detector, source, algorithms, output: Tasks 1, 3, 4, 5, 8, and 9.
- Platform decoupling: Tasks 1, 5, and 6 keep algorithms free of Win32/OpenCV/Tkinter dependencies.
- Safe default output: Tasks 2, 5, 9, and 10.
- Explicit real mouse enable: Tasks 5, 9, and 10.
- Per-frame diagnostics and metrics: Task 7.
- YOLO capability retained: Task 8 wraps existing `TargetDetector`.
- ONNX migration interface: Task 1 Detector Protocol and Task 8 adapter boundary.
- Tests: Every task has red/green test steps where code behavior changes.

Placeholder scan:

- The plan does not use unfilled requirement markers.
- Every file creation step includes concrete code.
- Each test step includes an exact command and expected result.

Type consistency:

- `Detection`, `DetectionPacket`, `SelectedTarget`, `AimMeasurement`, `PredictedAim`, `ControlCommand`, and `PipelineTickResult` are defined in Task 1 and used consistently in later tasks.
- `ModularConfig` field names introduced in Task 2 match algorithm, pipeline, adapter, and app tasks.
- `ModularPipeline.tick(frame, now=None)` signature introduced in Task 6 matches app and tests in later tasks.
