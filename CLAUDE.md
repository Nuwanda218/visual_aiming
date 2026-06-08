# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于 YOLOv8 的实时视觉辅助瞄准实验项目。核心流程：固定 ROI 截图 → YOLOv8 目标检测 → 类别感知瞄点计算 → 目标追踪预测 → FPS 风格速度控制 → 鼠标相对位移输出。

## 运行命令

```bash
python main.py              # 启动程序（自动请求管理员权限）
python main.py --modular --video path/to/video.mp4 --output null             # 安全视频回放，不移动鼠标
python main.py --modular --video path/to/video.mp4 --output log --diagnostics tests/logs/run.jsonl
python main.py --modular --output win_mouse --real-mouse                    # 显式允许真实鼠标输出
python -m pytest tests/     # 运行所有测试
python tests/test_detector_device.py    # 运行单个测试文件
pip install -r requirements.txt         # 安装依赖
```

## 架构

入口文件 `main.py` 仅做两件事：将 `src/` 加入 `sys.path`，然后调用 `visual_aiming.core.runtime.main()`。传入 `--modular` 时进入新模块化运行时。

新模块化算法运行时将输入源、检测器、目标选择、瞄点、预测、控制器和输出后端分离；默认输出为 NullOutput，不会移动真实鼠标。

**包结构 (`src/visual_aiming/`)：**

| 层 | 目录 | 职责 |
|---|---|---|
| 核心 | `core/` | 主循环、管道、瞄点计算、目标追踪、检测调度、节流、状态机 |
| 视觉 | `vision/` | YOLOv8 检测、屏幕截图、后台截图线程 |
| 动作 | `actions/` | 鼠标控制（FPS 伺服）、键盘/鼠标热键监听、调试可视化、配置 UI |
| 公共 | `common/` | 精确延时、资源路径解析、打印节流 |

**关键设计决策：**
- **服务容器** (`core/runtime_services.py`): `RuntimeServices.create()` 集中构建所有依赖，`RuntimeServices` 是持有所有模块实例的扁平 dataclass。避免全局变量。
- **视觉/控制频率分离**: `capture_fps` 控制截图频率，`detect_fps` 控制 YOLO 推理频率，`servo_loop_hz` (240Hz) 控制鼠标输出频率。鼠标端以独立伺服线程按高频采样最新目标并平滑输出，不会每次检测都硬跳一次。
- **数据流**: `CaptureWorker`（后台线程截图）→ 主循环 (120 FPS) → `DetectionScheduler` 判断是否检测 → `TargetDetector` YOLO 推理 → `RuntimePipeline` 处理检测结果 → `AimCalculator` 计算瞄点 → `TargetTracker` EMA 速度预测 → `MouseController` 伺服线程输出。
- **`RuntimePipeline`** 是连接检测与控制的桥梁：负责在无新检测时复用最近瞄点，在 firing 状态下可选冻结追踪器预测，在追踪器有近期轨迹时外推预测。
- **`DetectedTarget`** (dataclass in `vision/detection.py`) 是检测结果的标准数据载体，包含 bbox、confidence、class_id、class_name。
- **`ControlTarget`** (dataclass in `core/schemas.py`) 是从管道输出到鼠标控制器的标准接口，包含 target 坐标、crosshair 位置、是否有测量值、是否激活。
- **配置** (`config.py`): `Config` 是 dataclass，所有字段有默认值。`config.load(path)` 从 JSON 文件覆盖字段。配置在运行时通过 `getattr(config, key, default)` 读取，支持热更新（config_window UI 自动保存到 `config.json`）。
- **`WakeUpModule`** (`actions/input_listener.py`): 通过 pynput 监听全局热键。激活条件：同时按住 Shift + 右键然后按左键。退出：Ctrl+Q。

**两个鼠标控制模式位于 `actions/mouse_control.py`：**
1. **FPS 风格相对移动**（默认）: 独立伺服线程按 `servo_loop_hz` 运行，使用加速度限制的速度模型，支持减速/制动区域，子像素累积。
2. **绝对模式** (`mouse_absolute_mode_enabled`): 直接移动光标到目标位置。

`actions/visual_servo.py` 还包含一个更复杂的 `VisualServoLoop`（Alpha-Beta 滤波器 + PD 控制器），当前未被 MouseController 使用，但作为伺服控制算法的参考实现保留。

## 目标检测

`TargetDetector` (`vision/detection.py`) 是 YOLOv8 的封装。模型懒加载，`yolo_device=auto` 时优先 CUDA，不可用时回退 CPU，`yolo_half` 仅在 CUDA 下启用。模型路径通过 `common/resource_path.py` 解析，兼容 PyInstaller 打包（`sys._MEIPASS`）和开发环境。

目标选择 (`_select_best_box`) 使用基于距离、置信度、类别的线性评分，支持粘性选择机制防止目标频繁切换。

## 测试

测试使用 `unittest`，位于 `tests/`。每个测试文件自行将 `src/` 加入 `sys.path`（不依赖 pytest 配置）。运行方式：`python tests/test_xxx.py`。
