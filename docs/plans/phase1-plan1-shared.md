# V2 Plan 1 — shared 共享模型层

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立六层目录骨架，实现 shared/ 层（schemas + ports + config），为所有业务层提供公共数据结构和协议接口。

**Architecture:** shared/ 是整个 V2 的地基，定义层间通信的数据结构（Frame、Detection、Command）和协议接口（CapturePort、DetectorPort、ActuationPort、OutputPort）。现有 `visual_aiming_v2/schemas.py` 需要迁移到 `shared/schemas.py` 并按协议 v1 调整字段（去掉 crosshair）。其他五层目录先建空占位。

**Tech Stack:** Python 3.10+, `unittest`, `dataclasses`, `typing.Protocol`

**参考文档：** `docs/v2-architecture.md`, `docs/v2-protocol-v1.md`

---

## Target File Structure

```
src/visual_aiming_v2/
  __init__.py                     (修改)
  shared/
    __init__.py                   (新建)
    schemas.py                    (新建 — 按协议 v1 重写，不是简单迁移)
    ports.py                      (新建)
    config.py                     (新建)
  capture/__init__.py             (新建 — 空占位)
  perception/__init__.py          (新建 — 空占位)
  actuation/__init__.py           (新建 — 空占位)
  runtime/__init__.py             (新建 — 空占位)
  interaction/__init__.py         (新建 — 空占位)

tests/test_v2_schemas.py          (修改 — import 路径 + 新测试)
```

删除：`src/visual_aiming_v2/schemas.py`（旧文件）

---

## Task 1: 创建六层目录骨架 + 迁移并重写 schemas

**Files:**
- Create: `src/visual_aiming_v2/shared/__init__.py`
- Create: `src/visual_aiming_v2/shared/schemas.py`
- Create: `src/visual_aiming_v2/capture/__init__.py`
- Create: `src/visual_aiming_v2/perception/__init__.py`
- Create: `src/visual_aiming_v2/actuation/__init__.py`
- Create: `src/visual_aiming_v2/runtime/__init__.py`
- Create: `src/visual_aiming_v2/interaction/__init__.py`
- Modify: `src/visual_aiming_v2/__init__.py`
- Delete: `src/visual_aiming_v2/schemas.py`
- Modify: `tests/test_v2_schemas.py`

- [ ] **Step 1: 重写测试文件，按协议 v1 设计用例**

注意：协议 v1 的 Frame 不带 crosshair，Detection 无变化，Command 无变化。TickResult 是可选调试记录，暂不放在 schemas 里。

修改 `tests/test_v2_schemas.py`：

```python
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from visual_aiming_v2.shared.schemas import Command, Detection, Frame


class FrameTests(unittest.TestCase):
    def test_frame_holds_image_sequence_timestamp(self):
        frame = Frame(image="fake_image", sequence=0, timestamp=1.5)

        self.assertEqual(frame.image, "fake_image")
        self.assertEqual(frame.sequence, 0)
        self.assertEqual(frame.timestamp, 1.5)


class DetectionTests(unittest.TestCase):
    def test_center_computed_from_bbox(self):
        det = Detection(x=10, y=20, w=30, h=40, confidence=0.75, label="head")

        self.assertEqual(det.center, (25, 40))

    def test_defaults(self):
        det = Detection(x=0, y=0, w=10, h=10, confidence=0.5)

        self.assertEqual(det.label, "unknown")


class CommandTests(unittest.TestCase):
    def test_noop_factory(self):
        cmd = Command.noop("no_target")

        self.assertEqual(cmd.dx, 0)
        self.assertEqual(cmd.dy, 0)
        self.assertEqual(cmd.mode, "none")
        self.assertEqual(cmd.reason, "no_target")

    def test_relative_command(self):
        cmd = Command(dx=5, dy=-3, mode="relative", reason="tracking")

        self.assertEqual(cmd.dx, 5)
        self.assertEqual(cmd.dy, -3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_v2_schemas -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'visual_aiming_v2.shared'`。

- [ ] **Step 3: 创建六层目录的 `__init__.py`**

创建 `src/visual_aiming_v2/shared/__init__.py`：

```python
"""共享模型层 — 数据结构、协议接口、配置。"""
```

创建 `src/visual_aiming_v2/capture/__init__.py`：

```python
"""图像获取层 — 帧获取与预处理。"""
```

创建 `src/visual_aiming_v2/perception/__init__.py`：

```python
"""视觉感知层 — 目标检测。"""
```

创建 `src/visual_aiming_v2/actuation/__init__.py`：

```python
"""控制执行层 — 目标选择、瞄点计算、指令生成。"""
```

创建 `src/visual_aiming_v2/runtime/__init__.py`：

```python
"""运行编排层 — 流水线驱动与生命周期管理。"""
```

创建 `src/visual_aiming_v2/interaction/__init__.py`：

```python
"""交互接入层 — 用户入口与配置。"""
```

修改 `src/visual_aiming_v2/__init__.py`：

```python
"""V2 视觉瞄准运行时 — 六层架构: interaction / runtime / capture / perception / actuation + shared。"""
```

- [ ] **Step 4: 实现 shared/schemas.py（按协议 v1）**

创建 `src/visual_aiming_v2/shared/schemas.py`：

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

Point = Tuple[int, int]


@dataclass(slots=True)
class Frame:
    image: Any
    sequence: int
    timestamp: float


@dataclass(slots=True)
class Detection:
    x: int
    y: int
    w: int
    h: int
    confidence: float
    label: str = "unknown"

    @property
    def center(self) -> Point:
        return (self.x + self.w // 2, self.y + self.h // 2)


@dataclass(slots=True)
class Command:
    dx: int = 0
    dy: int = 0
    mode: str = "none"
    reason: str = "noop"

    @classmethod
    def noop(cls, reason: str) -> Command:
        return cls(dx=0, dy=0, mode="none", reason=reason)
```

- [ ] **Step 5: 删除旧 schemas.py**

删除 `src/visual_aiming_v2/schemas.py`。

- [ ] **Step 6: 运行测试确认通过**

Run:

```powershell
python -m unittest tests.test_v2_schemas -v
```

Expected: `Ran 4 tests` and `OK`。

- [ ] **Step 7: 提交**

```bash
git rm src/visual_aiming_v2/schemas.py
git add src/visual_aiming_v2/ tests/test_v2_schemas.py
git commit -m "refactor(v2): 建立六层目录骨架，按协议 v1 重写 shared/schemas"
```

---

## Task 2: shared/ports.py — 协议接口

**Files:**
- Create: `src/visual_aiming_v2/shared/ports.py`
- Modify: `tests/test_v2_schemas.py`

- [ ] **Step 1: 写 ports 测试**

在 `tests/test_v2_schemas.py` 中追加：

```python
from visual_aiming_v2.shared.ports import ActuationPort, CapturePort, DetectorPort, OutputPort


class PortsTests(unittest.TestCase):
    def test_all_ports_importable(self):
        self.assertIsNotNone(CapturePort)
        self.assertIsNotNone(DetectorPort)
        self.assertIsNotNone(ActuationPort)
        self.assertIsNotNone(OutputPort)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_v2_schemas.PortsTests -v
```

Expected: FAIL with `ModuleNotFoundError`。

- [ ] **Step 3: 实现 ports.py（按协议 v1 第 4 条）**

创建 `src/visual_aiming_v2/shared/ports.py`：

```python
from __future__ import annotations

from typing import Optional, Protocol, Sequence

from visual_aiming_v2.shared.schemas import Command, Detection, Frame


class CapturePort(Protocol):
    def read(self) -> Optional[Frame]: ...
    def close(self) -> None: ...


class DetectorPort(Protocol):
    def detect(self, image) -> Sequence[Detection]: ...


class ActuationPort(Protocol):
    def process(self, detections: Sequence[Detection]) -> Command: ...


class OutputPort(Protocol):
    def apply(self, command: Command) -> None: ...
    def close(self) -> None: ...
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```powershell
python -m unittest tests.test_v2_schemas -v
```

Expected: `Ran 5 tests` and `OK`。

- [ ] **Step 5: 提交**

```bash
git add src/visual_aiming_v2/shared/ports.py tests/test_v2_schemas.py
git commit -m "feat(v2): 添加 shared/ports 协议接口（CapturePort/DetectorPort/ActuationPort/OutputPort）"
```

---

## Task 3: shared/config.py — 极简配置

**Files:**
- Create: `src/visual_aiming_v2/shared/config.py`
- Modify: `tests/test_v2_schemas.py`

- [ ] **Step 1: 写 config 测试**

在 `tests/test_v2_schemas.py` 中追加：

```python
from visual_aiming_v2.shared.config import Config


class ConfigTests(unittest.TestCase):
    def test_defaults(self):
        config = Config()

        self.assertEqual(config.model_path, "models/best.pt")
        self.assertEqual(config.confidence, 0.5)
        self.assertEqual(config.device, "auto")
        self.assertGreater(config.image_width, 0)
        self.assertGreater(config.image_height, 0)

    def test_overrides(self):
        config = Config(model_path="custom.pt", confidence=0.8, device="cpu")

        self.assertEqual(config.model_path, "custom.pt")
        self.assertEqual(config.confidence, 0.8)
        self.assertEqual(config.device, "cpu")
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
python -m unittest tests.test_v2_schemas.ConfigTests -v
```

Expected: FAIL with `ModuleNotFoundError`。

- [ ] **Step 3: 实现 config.py**

创建 `src/visual_aiming_v2/shared/config.py`：

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    model_path: str = "models/best.pt"
    confidence: float = 0.5
    iou: float = 0.45
    device: str = "auto"
    image_width: int = 410
    image_height: int = 315
```

- [ ] **Step 4: 运行全部测试确认通过**

Run:

```powershell
python -m unittest tests.test_v2_schemas -v
```

Expected: `Ran 7 tests` and `OK`。

- [ ] **Step 5: 运行 V1 测试确认无影响**

Run:

```powershell
python -m unittest discover tests
```

Expected: V1 + V2 全部通过。

- [ ] **Step 6: 提交**

```bash
git add src/visual_aiming_v2/shared/config.py tests/test_v2_schemas.py
git commit -m "feat(v2): 添加 shared/config 极简配置"
```

---

## Self-Review

- Spec coverage: 架构文档的 shared/ 层、目录结构、协议 v1 的 Frame/Detection/Command/四个 Port 全部覆盖。
- Placeholder scan: 无 TBD/TODO。所有步骤含完整代码。
- Type consistency: `Frame(image, sequence, timestamp)` 不带 crosshair，与协议 v1 一致。Port 名称 `CapturePort/DetectorPort/ActuationPort/OutputPort` 与协议 v1 的接口签名一致（`read()`, `detect(image)`, `process(detections)`, `apply(command)`）。Config 包含 `image_width/image_height`，对应架构约定"图像尺寸是配置信息"。
