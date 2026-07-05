# V2 Plan 2 — 流水线三级：capture + perception + actuation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现流水线的三个处理级——capture（帧获取）、perception（目标检测）、actuation（控制指令生成），使它们各自可独立测试。

**Architecture:** 三级按协议 v1 通信：capture 输出 Frame，perception 接收 image 输出 `list[Detection]`，actuation 接收 detections 输出 Command。各级互不依赖，只依赖 shared/。每级包含一个正式实现和一个测试桩。

**Tech Stack:** Python 3.10+, `unittest`, `cv2`（VideoFileFrameSource）, `ultralytics`（YoloDetector，测试中不加载）

**前置条件：** Plan 1 已完成（shared/ 层就绪）。

---

## Target File Structure

```
src/visual_aiming_v2/
  capture/
    __init__.py                   (已存在)
    sources.py                    (新建 — MemoryCapture, VideoFileCapture)

  perception/
    __init__.py                   (已存在)
    detectors.py                  (新建 — StaticDetector, YoloDetector)

  actuation/
    __init__.py                   (已存在)
    targeting.py                  (新建 — select_nearest, compute_error, make_command)
    outputs.py                    (新建 — NullOutput, LogOutput)

tests/
  test_v2_capture.py              (新建)
  test_v2_perception.py           (新建)
  test_v2_actuation.py            (新建)
```

---

## Task 1: capture/sources.py — 帧源

**Files:**
- Create: `src/visual_aiming_v2/capture/sources.py`
- Create: `tests/test_v2_capture.py`

- [ ] **Step 1: 写 MemoryCapture 测试**

创建 `tests/test_v2_capture.py`：

```python
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.shared.schemas import Frame
from visual_aiming_v2.capture.sources import MemoryCapture


class MemoryCaptureTests(unittest.TestCase):
    def test_reads_all_frames_then_returns_none(self):
        frames = [
            Frame(image="a", sequence=0, timestamp=0.0),
            Frame(image="b", sequence=1, timestamp=0.1),
        ]
        source = MemoryCapture(frames)

        self.assertEqual(source.read(), frames[0])
        self.assertEqual(source.read(), frames[1])
        self.assertIsNone(source.read())

    def test_close_is_safe(self):
        source = MemoryCapture([])
        source.close()
        source.close()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_v2_capture -v
```

Expected: FAIL with `ModuleNotFoundError`。

- [ ] **Step 3: 实现 sources.py**

创建 `src/visual_aiming_v2/capture/sources.py`：

```python
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from visual_aiming_v2.shared.schemas import Frame


class MemoryCapture:
    def __init__(self, frames: Iterable[Frame]) -> None:
        self._frames = list(frames)
        self._index = 0

    def read(self) -> Optional[Frame]:
        if self._index >= len(self._frames):
            return None
        frame = self._frames[self._index]
        self._index += 1
        return frame

    def close(self) -> None:
        pass


class VideoFileCapture:
    def __init__(self, video_path: str | Path) -> None:
        import cv2

        self.path = Path(video_path)
        self.capture = cv2.VideoCapture(str(self.path))
        if not self.capture.isOpened():
            raise FileNotFoundError(f"无法打开视频: {self.path}")
        fps = self.capture.get(cv2.CAP_PROP_FPS)
        self._frame_dt = 1.0 / fps if fps and fps > 0 else 1.0 / 30.0
        self._sequence = 0

    def read(self) -> Optional[Frame]:
        ok, image = self.capture.read()
        if not ok:
            return None
        seq = self._sequence
        self._sequence += 1
        return Frame(image=image, sequence=seq, timestamp=seq * self._frame_dt)

    def close(self) -> None:
        self.capture.release()
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
python -m unittest tests.test_v2_capture -v
```

Expected: `Ran 2 tests` and `OK`。

- [ ] **Step 5: 提交**

```bash
git add src/visual_aiming_v2/capture/sources.py tests/test_v2_capture.py
git commit -m "feat(v2): 添加 capture/sources（MemoryCapture + VideoFileCapture）"
```

---

## Task 2: perception/detectors.py — 检测器

**Files:**
- Create: `src/visual_aiming_v2/perception/detectors.py`
- Create: `tests/test_v2_perception.py`

- [ ] **Step 1: 写检测器测试**

创建 `tests/test_v2_perception.py`：

```python
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.shared.schemas import Detection
from visual_aiming_v2.perception.detectors import StaticDetector, YoloDetector
from visual_aiming_v2.shared.config import Config


class StaticDetectorTests(unittest.TestCase):
    def test_returns_configured_detections(self):
        det = Detection(x=10, y=20, w=30, h=40, confidence=0.9, label="head")
        detector = StaticDetector([det])

        result = detector.detect("fake_image")

        self.assertEqual(result, [det])

    def test_returns_empty_when_none_configured(self):
        detector = StaticDetector([])

        self.assertEqual(detector.detect("fake_image"), [])


class YoloDetectorTests(unittest.TestCase):
    def test_accepts_config_and_lazy_loads(self):
        config = Config(model_path="nonexistent.pt")
        detector = YoloDetector(config)

        self.assertIsNone(detector._model)

    def test_detect_raises_when_model_not_found(self):
        config = Config(model_path="nonexistent.pt")
        detector = YoloDetector(config)

        with self.assertRaises(Exception):
            detector.detect("fake_image")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_v2_perception -v
```

Expected: FAIL with `ModuleNotFoundError`。

- [ ] **Step 3: 实现 detectors.py**

注意：协议 v1 规定 `detect(image)` 接收 image（不是 Frame），返回 `list[Detection]`。

创建 `src/visual_aiming_v2/perception/detectors.py`：

```python
from __future__ import annotations

from typing import Sequence

from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.shared.schemas import Detection


class StaticDetector:
    def __init__(self, detections: Sequence[Detection]) -> None:
        self._detections = list(detections)

    def detect(self, image) -> list[Detection]:
        return list(self._detections)


class YoloDetector:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._model = None

    def detect(self, image) -> list[Detection]:
        if self._model is None:
            self._load_model()
        results = self._model(
            image,
            conf=self.config.confidence,
            iou=self.config.iou,
            verbose=False,
        )
        detections: list[Detection] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                xyxy = box.xyxy[0].tolist()
                x1, y1, x2, y2 = [int(round(v)) for v in xyxy]
                conf = float(box.conf[0]) if box.conf is not None else 0.0
                cls_id = int(box.cls[0]) if getattr(box, "cls", None) is not None else -1
                names = getattr(self._model, "names", {})
                label = names.get(cls_id, "unknown") if isinstance(names, dict) else "unknown"
                detections.append(Detection(
                    x=x1, y=y1,
                    w=max(0, x2 - x1), h=max(0, y2 - y1),
                    confidence=conf, label=label,
                ))
        return detections

    def _load_model(self) -> None:
        from ultralytics import YOLO

        self._model = YOLO(self.config.model_path)
        if self.config.device != "auto":
            self._model.to(self.config.device)
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
python -m unittest tests.test_v2_perception -v
```

Expected: `Ran 4 tests` and `OK`。

- [ ] **Step 5: 提交**

```bash
git add src/visual_aiming_v2/perception/detectors.py tests/test_v2_perception.py
git commit -m "feat(v2): 添加 perception/detectors（StaticDetector + YoloDetector）"
```

---

## Task 3: actuation/targeting.py — 目标选择 + 瞄点 + 指令

**Files:**
- Create: `src/visual_aiming_v2/actuation/targeting.py`
- Create: `tests/test_v2_actuation.py`

- [ ] **Step 1: 写 actuation 测试**

注意：协议 v1 规定 actuation 的接口是 `process(detections) → Command`。`select_nearest`、`compute_error` 是内部实现，同时测试。准星由配置决定（`image_width // 2, image_height // 2`）。

创建 `tests/test_v2_actuation.py`：

```python
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.shared.schemas import Command, Detection
from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.actuation.targeting import Actuator, select_nearest, compute_error


class SelectNearestTests(unittest.TestCase):
    def test_returns_none_when_empty(self):
        self.assertIsNone(select_nearest([], crosshair=(100, 100)))

    def test_returns_single(self):
        det = Detection(x=90, y=90, w=20, h=20, confidence=0.9)
        self.assertEqual(select_nearest([det], crosshair=(100, 100)), det)

    def test_selects_closest(self):
        far = Detection(x=200, y=200, w=20, h=20, confidence=0.9)
        near = Detection(x=92, y=95, w=10, h=10, confidence=0.7)

        self.assertEqual(select_nearest([far, near], crosshair=(100, 100)), near)


class ComputeErrorTests(unittest.TestCase):
    def test_centered_returns_zero(self):
        det = Detection(x=95, y=95, w=10, h=10, confidence=0.9)
        self.assertEqual(compute_error(det, crosshair=(100, 100)), (0, 0))

    def test_right_of_crosshair(self):
        det = Detection(x=110, y=95, w=10, h=10, confidence=0.9)
        self.assertEqual(compute_error(det, crosshair=(100, 100)), (15, 0))

    def test_above_crosshair(self):
        det = Detection(x=95, y=75, w=10, h=10, confidence=0.9)
        self.assertEqual(compute_error(det, crosshair=(100, 100)), (0, -20))


class ActuatorTests(unittest.TestCase):
    def test_process_returns_noop_when_no_detections(self):
        actuator = Actuator(Config(image_width=200, image_height=200))

        cmd = actuator.process([])

        self.assertEqual(cmd.mode, "none")
        self.assertEqual(cmd.reason, "no_target")

    def test_process_returns_relative_command(self):
        actuator = Actuator(Config(image_width=200, image_height=200))
        det = Detection(x=110, y=85, w=10, h=10, confidence=0.9)

        cmd = actuator.process([det])

        self.assertEqual(cmd.dx, 15)
        self.assertEqual(cmd.dy, -10)
        self.assertEqual(cmd.mode, "relative")

    def test_process_returns_on_target_when_centered(self):
        actuator = Actuator(Config(image_width=200, image_height=200))
        det = Detection(x=95, y=95, w=10, h=10, confidence=0.9)

        cmd = actuator.process([det])

        self.assertEqual(cmd.mode, "none")
        self.assertEqual(cmd.reason, "on_target")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_v2_actuation -v
```

Expected: FAIL with `ModuleNotFoundError`。

- [ ] **Step 3: 实现 targeting.py**

创建 `src/visual_aiming_v2/actuation/targeting.py`：

```python
from __future__ import annotations

import math
from typing import Optional, Sequence

from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.shared.schemas import Command, Detection, Point


def select_nearest(detections: Sequence[Detection], crosshair: Point) -> Optional[Detection]:
    if not detections:
        return None
    cx, cy = crosshair
    return min(detections, key=lambda d: math.hypot(d.center[0] - cx, d.center[1] - cy))


def compute_error(detection: Detection, crosshair: Point) -> tuple[int, int]:
    cx, cy = detection.center
    return (cx - crosshair[0], cy - crosshair[1])


class Actuator:
    def __init__(self, config: Config) -> None:
        self.crosshair = (config.image_width // 2, config.image_height // 2)

    def process(self, detections: Sequence[Detection]) -> Command:
        selected = select_nearest(detections, self.crosshair)
        if selected is None:
            return Command.noop("no_target")
        dx, dy = compute_error(selected, self.crosshair)
        if dx == 0 and dy == 0:
            return Command.noop("on_target")
        return Command(dx=dx, dy=dy, mode="relative", reason="tracking")
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
python -m unittest tests.test_v2_actuation -v
```

Expected: `Ran 9 tests` and `OK`。

- [ ] **Step 5: 提交**

```bash
git add src/visual_aiming_v2/actuation/targeting.py tests/test_v2_actuation.py
git commit -m "feat(v2): 添加 actuation/targeting（Actuator + select_nearest + compute_error）"
```

---

## Task 4: actuation/outputs.py — 输出后端

**Files:**
- Create: `src/visual_aiming_v2/actuation/outputs.py`
- Modify: `tests/test_v2_actuation.py`

- [ ] **Step 1: 写输出后端测试**

在 `tests/test_v2_actuation.py` 中追加：

```python
from visual_aiming_v2.actuation.outputs import LogOutput, NullOutput


class NullOutputTests(unittest.TestCase):
    def test_apply_does_nothing(self):
        output = NullOutput()
        output.apply(Command.noop("test"))
        output.close()


class LogOutputTests(unittest.TestCase):
    def test_records_commands(self):
        output = LogOutput()
        cmd = Command(dx=3, dy=-2, mode="relative", reason="tracking")

        output.apply(cmd)

        self.assertEqual(len(output.commands), 1)
        self.assertEqual(output.commands[0].dx, 3)

    def test_close_is_safe(self):
        output = LogOutput()
        output.close()
        output.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_v2_actuation.NullOutputTests -v
```

Expected: FAIL with `ModuleNotFoundError`。

- [ ] **Step 3: 实现 outputs.py**

注意：协议 v1 规定 `apply(command)`，只接收 Command，不接收 TickResult。

创建 `src/visual_aiming_v2/actuation/outputs.py`：

```python
from __future__ import annotations

from visual_aiming_v2.shared.schemas import Command


class NullOutput:
    def apply(self, command: Command) -> None:
        pass

    def close(self) -> None:
        pass


class LogOutput:
    def __init__(self) -> None:
        self.commands: list[Command] = []

    def apply(self, command: Command) -> None:
        self.commands.append(command)

    def close(self) -> None:
        pass
```

- [ ] **Step 4: 运行全部 actuation 测试**

Run:

```powershell
python -m unittest tests.test_v2_actuation -v
```

Expected: `Ran 12 tests` and `OK`。

- [ ] **Step 5: 运行全部测试确认无影响**

Run:

```powershell
python -m unittest discover tests
```

Expected: 全部通过。

- [ ] **Step 6: 提交**

```bash
git add src/visual_aiming_v2/actuation/outputs.py tests/test_v2_actuation.py
git commit -m "feat(v2): 添加 actuation/outputs（NullOutput + LogOutput）"
```

---

## Self-Review

- Spec coverage: 架构文档的 capture/perception/actuation 三层全部覆盖。协议 v1 的 `read()→Frame`、`detect(image)→list[Detection]`、`process(detections)→Command`、`apply(command)` 签名在实现和测试中一致。
- Placeholder scan: 无 TBD/TODO。
- Type consistency: `MemoryCapture.read()` 返回 `Frame | None`，`StaticDetector.detect(image)` 接收 image 返回 `list[Detection]`，`Actuator.process(detections)` 返回 `Command`，`NullOutput.apply(command)` 只接收 Command。全部与协议 v1 一致。`Actuator` 从 `Config.image_width/image_height` 计算准星，与架构约定一致。
