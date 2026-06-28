# V2 Plan 3 — runtime 编排层 + interaction 交互层 + 入口

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 runtime/（Pipeline + run 循环）和 interaction/（CLI），创建 main_v2.py 入口，使 V2 成为可从命令行运行的完整程序。

**Architecture:** runtime 按协议 v1 第 4 条调用各级接口驱动流水线。interaction 解析 CLI 参数 + 读取 config.json，组装组件传给 runtime。main_v2.py 是唯一入口。TickResult 作为可选调试记录实现。

**Tech Stack:** Python 3.10+, `unittest`, `argparse`, `json`

**前置条件：** Plan 1（shared/）和 Plan 2（capture/ + perception/ + actuation/）已完成。

---

## Target File Structure

```
src/visual_aiming_v2/
  runtime/
    __init__.py                   (已存在)
    pipeline.py                   (新建 — Pipeline 类)
    runner.py                     (新建 — run 函数)

  interaction/
    __init__.py                   (已存在)
    cli.py                        (新建 — parse_args + main)

main_v2.py                        (新建 — 项目根目录入口)

tests/
  test_v2_runtime.py              (新建)
  test_v2_cli.py                  (新建)
```

---

## Task 1: runtime/pipeline.py — 单帧处理管道

**Files:**
- Create: `src/visual_aiming_v2/runtime/pipeline.py`
- Create: `tests/test_v2_runtime.py`

- [ ] **Step 1: 写 Pipeline 测试**

创建 `tests/test_v2_runtime.py`：

```python
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.shared.schemas import Detection, Frame
from visual_aiming_v2.shared.config import Config
from visual_aiming_v2.capture.sources import MemoryCapture
from visual_aiming_v2.perception.detectors import StaticDetector
from visual_aiming_v2.actuation.targeting import Actuator
from visual_aiming_v2.actuation.outputs import LogOutput
from visual_aiming_v2.runtime.pipeline import Pipeline


class PipelineTests(unittest.TestCase):
    def _make_pipeline(self, detections, image_size=200):
        config = Config(image_width=image_size, image_height=image_size)
        return Pipeline(
            detector=StaticDetector(detections),
            actuator=Actuator(config),
            output=LogOutput(),
        )

    def test_noop_when_no_detections(self):
        pipeline = self._make_pipeline([])
        frame = Frame(image="img", sequence=0, timestamp=0.0)

        result = pipeline.tick(frame)

        self.assertEqual(result.command.mode, "none")
        self.assertEqual(result.command.reason, "no_target")

    def test_selects_nearest_and_produces_relative_command(self):
        far = Detection(x=200, y=200, w=20, h=20, confidence=0.9)
        near = Detection(x=92, y=82, w=20, h=20, confidence=0.8)
        pipeline = self._make_pipeline([far, near])
        frame = Frame(image="img", sequence=1, timestamp=0.1)

        result = pipeline.tick(frame)

        self.assertEqual(result.command.mode, "relative")
        self.assertEqual(result.command.dx, 2)
        self.assertEqual(result.command.dy, -8)

    def test_output_receives_command(self):
        det = Detection(x=110, y=95, w=10, h=10, confidence=0.9)
        pipeline = self._make_pipeline([det])
        frame = Frame(image="img", sequence=0, timestamp=0.0)

        pipeline.tick(frame)

        self.assertEqual(len(pipeline.output.commands), 1)

    def test_tick_result_contains_detections(self):
        d1 = Detection(x=10, y=10, w=10, h=10, confidence=0.5)
        d2 = Detection(x=50, y=50, w=10, h=10, confidence=0.6)
        pipeline = self._make_pipeline([d1, d2])
        frame = Frame(image="img", sequence=0, timestamp=0.0)

        result = pipeline.tick(frame)

        self.assertEqual(len(result.detections), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_v2_runtime -v
```

Expected: FAIL with `ModuleNotFoundError`。

- [ ] **Step 3: 先在 shared/schemas.py 添加 TickResult**

TickResult 是 pipeline.tick() 的返回值，属于层间数据结构，放在 shared/schemas.py。

在 `src/visual_aiming_v2/shared/schemas.py` 末尾追加：

```python
@dataclass
class TickResult:
    frame: Frame
    detections: Sequence[Detection]
    selected: Optional[Detection]
    command: Command
```

同时在文件顶部的 import 中添加 `Optional` 和 `Sequence`：

```python
from typing import Any, Optional, Sequence, Tuple
```

- [ ] **Step 4: 实现 pipeline.py**

创建 `src/visual_aiming_v2/runtime/pipeline.py`：

```python
from __future__ import annotations

from visual_aiming_v2.shared.ports import ActuationPort, DetectorPort, OutputPort
from visual_aiming_v2.shared.schemas import Frame, TickResult


class Pipeline:
    def __init__(self, detector: DetectorPort, actuator: ActuationPort, output: OutputPort) -> None:
        self.detector = detector
        self.actuator = actuator
        self.output = output

    def tick(self, frame: Frame) -> TickResult:
        detections = list(self.detector.detect(frame.image))
        command = self.actuator.process(detections)
        self.output.apply(command)
        return TickResult(
            frame=frame,
            detections=detections,
            selected=None,
            command=command,
        )
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```powershell
python -m unittest tests.test_v2_runtime -v
```

Expected: `Ran 4 tests` and `OK`。

- [ ] **Step 6: 提交**

```bash
git add src/visual_aiming_v2/shared/schemas.py src/visual_aiming_v2/runtime/pipeline.py tests/test_v2_runtime.py
git commit -m "feat(v2): 添加 runtime/pipeline + TickResult"
```

---

## Task 2: runtime/runner.py — 运行循环

**Files:**
- Create: `src/visual_aiming_v2/runtime/runner.py`
- Modify: `tests/test_v2_runtime.py`

- [ ] **Step 1: 写 runner 测试**

在 `tests/test_v2_runtime.py` 中追加：

```python
from visual_aiming_v2.runtime.runner import run


class RunnerTests(unittest.TestCase):
    def test_processes_all_frames(self):
        frames = [
            Frame(image="a", sequence=0, timestamp=0.0),
            Frame(image="b", sequence=1, timestamp=0.1),
            Frame(image="c", sequence=2, timestamp=0.2),
        ]
        config = Config(image_width=200, image_height=200)
        output = LogOutput()

        results = run(
            capture=MemoryCapture(frames),
            detector=StaticDetector([Detection(x=10, y=10, w=10, h=10, confidence=0.9)]),
            actuator=Actuator(config),
            output=output,
        )

        self.assertEqual(len(results), 3)
        self.assertEqual(len(output.commands), 3)

    def test_max_frames_limits_processing(self):
        frames = [Frame(image=f"f{i}", sequence=i, timestamp=i * 0.1) for i in range(10)]
        config = Config(image_width=200, image_height=200)

        results = run(
            capture=MemoryCapture(frames),
            detector=StaticDetector([]),
            actuator=Actuator(config),
            output=LogOutput(),
            max_frames=3,
        )

        self.assertEqual(len(results), 3)

    def test_closes_capture_and_output(self):
        close_log = []
        capture = MemoryCapture([])
        output = LogOutput()
        orig_cap_close = capture.close
        orig_out_close = output.close
        capture.close = lambda: (close_log.append("capture"), orig_cap_close())
        output.close = lambda: (close_log.append("output"), orig_out_close())
        config = Config(image_width=200, image_height=200)

        run(capture=capture, detector=StaticDetector([]), actuator=Actuator(config), output=output)

        self.assertIn("capture", close_log)
        self.assertIn("output", close_log)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_v2_runtime.RunnerTests -v
```

Expected: FAIL with `ModuleNotFoundError`。

- [ ] **Step 3: 实现 runner.py（按协议 v1 第 5 条）**

创建 `src/visual_aiming_v2/runtime/runner.py`：

```python
from __future__ import annotations

from visual_aiming_v2.runtime.pipeline import Pipeline
from visual_aiming_v2.shared.ports import ActuationPort, CapturePort, DetectorPort, OutputPort
from visual_aiming_v2.shared.schemas import TickResult


def run(
    capture: CapturePort,
    detector: DetectorPort,
    actuator: ActuationPort,
    output: OutputPort,
    max_frames: int | None = None,
) -> list[TickResult]:
    pipeline = Pipeline(detector=detector, actuator=actuator, output=output)
    results: list[TickResult] = []
    try:
        while max_frames is None or len(results) < max_frames:
            frame = capture.read()
            if frame is None:
                break
            results.append(pipeline.tick(frame))
    finally:
        capture.close()
        output.close()
    return results
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
python -m unittest tests.test_v2_runtime -v
```

Expected: `Ran 7 tests` and `OK`。

- [ ] **Step 5: 提交**

```bash
git add src/visual_aiming_v2/runtime/runner.py tests/test_v2_runtime.py
git commit -m "feat(v2): 添加 runtime/runner 运行循环"
```

---

## Task 3: interaction/cli.py + main_v2.py

**Files:**
- Create: `src/visual_aiming_v2/interaction/cli.py`
- Create: `main_v2.py`
- Create: `tests/test_v2_cli.py`

- [ ] **Step 1: 写 CLI 测试**

创建 `tests/test_v2_cli.py`：

```python
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.interaction.cli import parse_args


class ParseArgsTests(unittest.TestCase):
    def test_requires_video(self):
        with self.assertRaises(SystemExit):
            parse_args([])

    def test_parses_video(self):
        args = parse_args(["--video", "sample.mp4"])
        self.assertEqual(args.video, "sample.mp4")

    def test_defaults(self):
        args = parse_args(["--video", "v.mp4"])
        self.assertEqual(args.output, "null")
        self.assertEqual(args.model, "models/best.pt")
        self.assertEqual(args.max_frames, 0)

    def test_all_options(self):
        args = parse_args(["--video", "v.mp4", "--model", "m.pt", "--output", "log", "--max-frames", "50"])
        self.assertEqual(args.model, "m.pt")
        self.assertEqual(args.output, "log")
        self.assertEqual(args.max_frames, 50)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_v2_cli -v
```

Expected: FAIL with `ModuleNotFoundError`。

- [ ] **Step 3: 实现 cli.py**

创建 `src/visual_aiming_v2/interaction/cli.py`：

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V2 视觉瞄准运行时")
    parser.add_argument("--video", required=True, help="视频文件路径")
    parser.add_argument("--model", default="models/best.pt", help="YOLO 模型路径")
    parser.add_argument("--output", choices=["null", "log"], default="null", help="输出后端")
    parser.add_argument("--max-frames", type=int, default=0, help="最多处理帧数，0 表示全部")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    return parser.parse_args(argv)


def load_config_file(path: str) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    from visual_aiming_v2.actuation.outputs import LogOutput, NullOutput
    from visual_aiming_v2.actuation.targeting import Actuator
    from visual_aiming_v2.capture.sources import VideoFileCapture
    from visual_aiming_v2.perception.detectors import YoloDetector
    from visual_aiming_v2.runtime.runner import run
    from visual_aiming_v2.shared.config import Config

    file_config = load_config_file(args.config)
    config = Config(
        model_path=args.model or file_config.get("model_path", "models/best.pt"),
        confidence=float(file_config.get("confidence", 0.5)),
        iou=float(file_config.get("iou", 0.45)),
        device=str(file_config.get("device", "auto")),
        image_width=int(file_config.get("image_width", 410)),
        image_height=int(file_config.get("image_height", 315)),
    )

    capture = VideoFileCapture(args.video)
    detector = YoloDetector(config)
    actuator = Actuator(config)
    output = LogOutput() if args.output == "log" else NullOutput()
    max_frames = args.max_frames if args.max_frames > 0 else None

    results = run(capture=capture, detector=detector, actuator=actuator, output=output, max_frames=max_frames)
    print(f"[V2] 处理完成: {len(results)} 帧")
    return 0
```

- [ ] **Step 4: 运行 CLI 测试确认通过**

Run:

```powershell
python -m unittest tests.test_v2_cli -v
```

Expected: `Ran 4 tests` and `OK`。

- [ ] **Step 5: 创建 main_v2.py**

创建 `main_v2.py`（项目根目录）：

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from visual_aiming_v2.interaction.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: 提交**

```bash
git add src/visual_aiming_v2/interaction/cli.py main_v2.py tests/test_v2_cli.py
git commit -m "feat(v2): 添加 interaction/cli + main_v2.py 入口"
```

---

## Task 4: 最终验证

- [ ] **Step 1: 运行全部 V2 测试**

Run:

```powershell
python -m unittest tests.test_v2_schemas tests.test_v2_capture tests.test_v2_perception tests.test_v2_actuation tests.test_v2_runtime tests.test_v2_cli -v
```

Expected: 全部通过。

- [ ] **Step 2: 运行全部 V1 + V2 测试**

Run:

```powershell
python -m unittest discover tests
```

Expected: V1 + V2 全部通过。

- [ ] **Step 3: 检查目录结构**

Run:

```powershell
find src/visual_aiming_v2 -name "*.py" | sort
```

Expected:

```
src/visual_aiming_v2/__init__.py
src/visual_aiming_v2/actuation/__init__.py
src/visual_aiming_v2/actuation/outputs.py
src/visual_aiming_v2/actuation/targeting.py
src/visual_aiming_v2/capture/__init__.py
src/visual_aiming_v2/capture/sources.py
src/visual_aiming_v2/interaction/__init__.py
src/visual_aiming_v2/interaction/cli.py
src/visual_aiming_v2/perception/__init__.py
src/visual_aiming_v2/perception/detectors.py
src/visual_aiming_v2/runtime/__init__.py
src/visual_aiming_v2/runtime/pipeline.py
src/visual_aiming_v2/runtime/runner.py
src/visual_aiming_v2/shared/__init__.py
src/visual_aiming_v2/shared/config.py
src/visual_aiming_v2/shared/ports.py
src/visual_aiming_v2/shared/schemas.py
```

共 17 个 Python 文件。

## Self-Review

- Spec coverage: 架构文档的 runtime 层和 interaction 层全部覆盖。协议 v1 第 4 条（runtime 调用各级接口）和第 5 条（interaction 传递组件实例）在 runner.py 和 cli.py 中实现。TickResult 作为可选调试记录在 schemas.py 中定义。
- Placeholder scan: 无 TBD/TODO。
- Type consistency: `Pipeline.__init__` 接收 `detector: DetectorPort, actuator: ActuationPort, output: OutputPort`。`run()` 参数名 `capture/detector/actuator/output` 与协议 v1 第 5 条一致。`pipeline.tick(frame)` 返回 `TickResult`。`cli.main()` 按 `Config → VideoFileCapture → YoloDetector → Actuator → Output → run()` 顺序组装。
