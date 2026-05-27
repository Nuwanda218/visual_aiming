# 视觉辅助瞄准系统

基于 YOLOv8 的实时视觉辅助瞄准实验项目。

## 📋 目录

- [项目概述](#项目概述)
- [核心架构](#核心架构)
- [模块详解](#模块详解)
- [配置参数说明](#配置参数说明)
- [运行指南](#运行指南)
- [技术选型](#技术选型)
- [潜在问题与优化建议](#潜在问题与优化建议)

---

## 🎯 项目概述

### 核心流程

```
固定 ROI 截图 → YOLOv8 目标检测 → 类别感知瞄点计算 → 目标追踪预测 → FPS 风格速度控制 → 鼠标相对位移输出
```

### 主要特性

| 特性 | 说明 |
|------|------|
| 实时检测 | 基于 YOLOv8 进行 head/person 检测 |
| 目标追踪 | EMA 速度预测，提升瞄准稳定性 |
| 智能瞄点 | 针对头部/人物的不同瞄点计算策略 |
| FPS 风格控制 | 使用独立伺服线程按低频平滑输出鼠标相对位移 |
| 状态机管理 | 激活/开火状态的精确控制 |
| 节流机制 | 时间/概率双重节流，防沉迷设计 |

---

## 🏗️ 核心架构

### 模块分层

```
┌─────────────────────────────────────────────────────────────────┐
│                        UI 层                                    │
│  config_window.py │ debug_visualizer.py                         │
├─────────────────────────────────────────────────────────────────┤
│                      控制层                                      │
│  mouse_control.py │ input_listener.py                           │
├─────────────────────────────────────────────────────────────────┤
│                      核心层                                      │
│  runtime.py │ pipeline.py │ aim_calculator.py │ target_tracker.py│
├─────────────────────────────────────────────────────────────────┤
│                      视觉层                                      │
│  detection.py │ capture_worker.py │ screen_capture.py           │
├─────────────────────────────────────────────────────────────────┤
│                      工具层                                      │
│  timing.py │ resource_path.py │ utils.py                        │
└─────────────────────────────────────────────────────────────────┘
```

### 数据流

```
【后台线程】CaptureWorker 截图
    ↓
【主循环】120 FPS 轮询
    ↓
DetectionScheduler 判断是否检测
    ↓
TargetDetector (YOLOv8) 推理
    ↓
RuntimePipeline 处理检测结果
    ↓
AimCalculator 计算瞄点
    ↓
TargetTracker 速度预测 / 复用最近瞄点
    ↓
MouseController 以 servo_loop_hz 采样并输出鼠标位移
```

---

## 📦 模块详解

### 1. 主程序入口 (`main.py`)

```python
def main():
    # 1. 检查管理员权限
    # 2. 加载配置
    # 3. 初始化服务
    # 4. 启动主循环
```

### 2. 运行时核心 (`core/runtime.py`)

**核心职责：**
- 主循环控制（120 FPS）
- 服务生命周期管理
- 状态转换协调

**关键函数：**
| 函数 | 作用 |
|------|------|
| `_run_loop()` | 主循环，协调所有模块 |
| `_update_detection_and_control()` | 检测与控制核心逻辑 |
| `_should_detect()` | 判断是否执行检测 |
| `_sleep_for_poll_interval()` | 精确延时，稳定帧率 |

### 3. 服务容器 (`core/runtime_services.py`)

**设计模式：服务容器（Service Container）**

统一管理所有模块实例，避免全局变量，便于测试和维护。

### 4. 处理管道 (`core/pipeline.py`)

**核心职责：** 连接检测、瞄点计算、目标追踪和控制目标发布

```python
def process_detection():
    # 1. 计算瞄点
    # 2. 更新追踪器
    # 3. 更新最新瞄点
    # 4. 生成 ControlTarget
```

### 5. 目标追踪器 (`core/target_tracker.py`)

**算法：指数移动平均（EMA）**

```
predicted_position = (1 - alpha) * history + alpha * current
```

**参数：**
- `tracker_smoothing_factor`: EMA 平滑系数（0.66）
- `tracker_prediction_time`: 预测时间窗口（0.025s）
- `tracker_stop_threshold`: 静止判定阈值（10像素）

### 6. 检测调度器 (`core/detect_scheduler.py`)

**状态频率控制：**

| 状态 | FPS | 配置项 |
|------|-----|--------|
| 普通激活 | 30 | `detect_fps` |
| 开火吸附 | 30 | `firing_detect_fps` |
| 空闲状态 | 8 | `idle_detect_fps` |

### 7. 节流器 (`core/throttle.py`)

**双重节流机制：**

1. **概率节流**：`adsorb_prob`（默认 0.8）控制每次吸附概率
2. **时间节流**：令牌桶算法，`cycle_duration` 周期内分配 `active_duration` 时间

### 8. 视觉检测 (`vision/detection.py`)

**YOLOv8 集成：**
- 懒加载模型
- `yolo_device=auto` 时优先使用 CUDA，CUDA 不可用时明确回退 CPU
- `yolo_half` 只在 CUDA 运行时启用
- 开发环境模型路径从项目根目录解析，例如 `models/best.pt`
- 支持跳帧复用（`yolo_skip_frames`）
- 置信度阈值过滤（`yolo_conf_threshold`）

**⚠️ 待优化项：**
- 目标选择机制（`_select_best_box`）：当前采用简单线性评分，后续计划引入卡尔曼滤波进行目标预测和多模态融合，提升跟踪稳定性和准确性。

### 9. 目标选择机制（待优化）

**当前实现：**
- 基于距离、置信度、类别的线性评分模型
- 粘性选择机制防止目标频繁切换
- 支持目标连续性约束

**后续优化方向：**
- 引入卡尔曼滤波进行目标位置预测
- 使用非线性评分函数（如高斯距离权重）
- 支持多目标管理和优先级动态调整
- 参考 DeepSORT 等先进跟踪算法

### 10. 截图线程 (`vision/capture_worker.py`)

**生产者-消费者模式：**
- 后台线程持续截图（`capture_fps`）
- 主循环按需获取最新帧
- 线程安全的帧缓存

### 11. 视觉与控制频率分离（当前 MVP）

**当前实现：**
- `capture_fps` 控制后台 ROI 截图频率
- `detect_fps`、`firing_detect_fps`、`idle_detect_fps` 控制 YOLO 推理频率
- `RuntimePipeline` 保存最近一次有效瞄点，并在没有新检测帧时提供可复用控制目标
- `MouseController` 独立线程按 `servo_loop_hz` 采样最新控制目标，负责平滑速度、减速和制动

**效果：**
- 视觉端可以按检测能力尽量高频更新
- 鼠标端不会每次检测都硬跳一次，而是按伺服频率连续输出
- 后续插件化可以把边界收敛为 `VisionPlugin.process(frame) -> DetectionState` 和 `OutputPlugin.apply(ControlTarget)`

**仍未实现：**
- 动态插件加载器
- TensorRT / ONNX Runtime 推理后端
- 多目标管理器或 DeepSORT 级别的长期 ID 跟踪

### 12. 鼠标控制 (`actions/mouse_control.py`)

**FPS 风格速度控制:**
- 距离感知速度曲线
- 近目标减速（`fps_decel_radius` / `fps_near_speed_scale`）
- 制动半径（`fps_brake_radius`）
- 输出步长限制（`servo_step_limit`）

---

## ⚙️ 配置参数说明

### 频率相关参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `runtime_poll_fps` | 120 | 主循环轮询频率 |
| `capture_fps` | 30 | 后台截图频率 |
| `detect_fps` | 30 | 普通状态检测频率 |
| `firing_detect_fps` | 30 | 开火状态检测频率 |
| `idle_detect_fps` | 8 | 空闲状态检测频率 |
| `servo_loop_hz` | 240 | 伺服控制频率 |
| `yolo_skip_frames` | 1 | 普通状态跳帧数 |
| `firing_yolo_skip_frames` | 0 | 开火状态跳帧数 |

### ROI 相关参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `roi_width` | 410 | 截图区域宽度 |
| `roi_height` | 315 | 截图区域高度 |

### 瞄点计算参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `head_bias` | 0.25 | 头部瞄点偏置（向上偏移） |
| `aim_deadzone` | 8 | 瞄点死区（像素） |

### 目标追踪参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `tracker_enabled` | true | 是否启用追踪器 |
| `tracker_prediction_time` | 0.025 | 预测时间（秒） |
| `tracker_smoothing_factor` | 0.66 | EMA 平滑系数 |
| `tracker_stop_threshold` | 10.0 | 静止判定阈值 |
| `tracker_reset_distance` | 200.0 | 追踪重置距离 |

### FPS 速度控制参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `fps_speed_gain` | 42.0 | 速度增益 |
| `fps_min_speed` | 0.0 | 最小速度 |
| `fps_max_speed` | 7200.0 | 最大速度 |
| `fps_decel_radius` | 135.0 | 减速半径 |
| `fps_brake_radius` | 90.0 | 制动半径 |
| `fps_brake` | 0.72 | 制动系数 |

### YOLO 相关参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `yolo_model_path` | models/best.pt | 模型路径，相对项目根目录 |
| `yolo_conf_threshold` | 0.5 | 置信度阈值 |
| `yolo_iou_threshold` | 0.45 | IOU 阈值 |
| `yolo_device` | auto | 推理设备 |
| `yolo_half` | true | 是否使用半精度 |
| `yolo_imgsz` | 416 | 推理图像尺寸 |

### 节流控制参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `adsorb_prob` | 0.8 | 吸附概率 |
| `cycle_duration` | 2.0 | 周期时长（秒） |
| `active_duration` | 0.5 | 活跃时长（秒） |
| `enable_time_throttle` | true | 是否启用时间节流 |

### 调试参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `debug_enabled` | false | 是否启用调试窗口 |
| `debug_log_enabled` | false | 是否启用调试日志 |
| `debug_window_scale` | 1.2 | 调试窗口缩放 |

---

## 🚀 运行指南

### 环境要求

- Python 3.8+
- Windows 10/11（需要管理员权限）
- 支持 CUDA 的 GPU（推荐）

### 依赖安装

```bash
pip install -r requirements.txt
```

### 运行命令

```bash
python main.py
```

**注意：程序会自动以管理员身份重启。**

### 使用方法

1. **激活辅助**：同时按住 `Shift + 右键`
2. **开始吸附**：按下 `左键`
3. **退出程序**：按 `Ctrl + Q`

---

## 🛠️ 技术选型

### 核心技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.8+ | 主开发语言 |
| YOLOv8 | ultralytics | 目标检测 |
| mss | latest | 屏幕截图 |
| numpy | latest | 图像处理 |
| OpenCV | latest | 调试可视化 |
| pynput / ctypes | latest / stdlib | 热键监听与 Windows 鼠标控制 |

### 设计模式

| 模式 | 应用场景 |
|------|----------|
| 服务容器 | RuntimeServices |
| 生产者-消费者 | CaptureWorker |
| 状态机 | RuntimeState |
| 策略模式 | 多种鼠标控制模式 |

---

## ⚠️ 潜在问题与优化建议

### 已知问题

1. **Windows 权限问题**：真实鼠标控制通常需要管理员权限
2. **CUDA 可用性**：`yolo_device=auto` 会优先 CUDA；没有 CUDA 时自动回退 CPU，性能会下降
3. **GPU 内存占用**：YOLOv8 模型加载占用显存，具体取决于模型和 `yolo_imgsz`
4. **高频负载**：提高 `capture_fps`、`detect_fps` 或 `servo_loop_hz` 会增加 CPU/GPU 占用
5. **插件化状态**：当前已经稳定三层边界，但还没有动态插件发现、加载和元数据管理

### 优化建议

1. **模型优化**：使用 TensorRT 或 ONNX Runtime 加速推理
2. **动态帧率**：根据 GPU 负载自动调整检测频率
3. **内存优化**：帧缓存采用循环缓冲区，避免内存泄漏
4. **多线程优化**：进一步分离截图、检测、控制和 UI 调度
5. **插件系统**：在当前 `vision / core / actions` 边界上增加 `VisionPlugin` 与 `OutputPlugin`

---

## 📝 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.0 | 2026-04 | 初始版本，YOLOv8 集成 |

---

## 📄 许可证

MIT License

---

*项目仍处于快速迭代阶段，欢迎提交 Issue 和 PR。*
