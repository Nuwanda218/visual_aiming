# Python 模块化算法重构设计

日期：2026-06-06

## 背景

当前项目是基于 YOLOv8 的实时视觉辅助瞄准实验项目，现有流程大致为：固定 ROI 截图、YOLO 检测、类别感知瞄点计算、目标追踪预测、FPS 风格鼠标控制、相对/绝对鼠标输出。

现有代码已经有分层雏形，但核心问题是：运行时状态、检测调度、瞄点计算、目标追踪、鼠标控制、配置读取、视频测试之间的边界不够稳定。算法逻辑分散在多个模块中，导致调参、离线复现、替换算法和后续打包都比较困难。

本次重构的目标不是小修小补，而是为“算法重做”建立一套可实验、可验证、可迁移的 Python 模块化架构。

## 已确认方向

第一版仍以 Python 为主实现，不立即切换到 C#、Rust、C++ 或 Go。

原因：当前最重的依赖来自 YOLO / PyTorch / ultralytics / OpenCV，而不是 Python 语言本身。算法尚未稳定时直接换语言，会同时承担模型推理适配、Windows 输入输出、打包和算法重写的复杂度。

第一版只预留 ONNX / 其他语言迁移接口，不实现 ONNX detector。后续如果需要轻量化，可以将 YOLO 模型导出为 ONNX，并实现同一 Detector 接口。

## 第一版目标

第一版采用 Python 模块化重构，达成以下目标：

1. 实时运行和视频回放共用同一套核心 pipeline。
2. 检测器、输入源、控制算法、输出后端都可替换。
3. 算法模块从平台细节中解耦，不直接依赖 Win32 鼠标 API、Tkinter、OpenCV 窗口或实时截图。
4. 默认支持安全输出后端，不移动真实鼠标。
5. 真实鼠标输出必须通过配置显式启用。
6. 每帧输出诊断数据，用综合基线评估算法表现。
7. 保留 YOLO 检测能力作为第一版必须可用功能。

## 第一版非目标

以下能力第一版不优先恢复，可以在核心 pipeline 稳定后作为后续阶段实现：

1. Tkinter 配置窗口。
2. OpenCV 调试窗口。
3. PyInstaller 打包流程。
4. ONNX detector 真实推理实现。
5. 跨语言核心实现。

这些不是永久删除目标，而是为了避免第一版同时解决过多问题。

## 推荐架构

采用端口与适配器风格的 Python 模块化设计：

```text
FrameSource -> Detector -> TargetSelector -> AimStrategy -> Predictor -> Controller -> OutputBackend
```

其中：

- `FrameSource` 负责提供帧，可以来自实时截图或视频文件。
- `Detector` 负责从帧中产生检测结果。
- `TargetSelector` 负责从多个候选框中选择一个目标。
- `AimStrategy` 负责从目标框计算屏幕瞄点。
- `Predictor` 负责平滑、预测、丢帧保持和跳变重置。
- `Controller` 负责从准星误差生成控制命令。
- `OutputBackend` 负责执行控制命令，可以是空输出、日志输出或真实鼠标输出。
- `Diagnostics` / `Metrics` 负责记录每帧状态和算法指标。

## 建议目录结构

```text
src/visual_aiming/
  app/
    realtime.py
    replay.py

  core/
    pipeline.py
    schemas.py
    metrics.py
    clock.py

  ports/
    frame_source.py
    detector.py
    output.py
    diagnostics.py

  adapters/
    frame_sources/
      screen_capture.py
      video_file.py

    detectors/
      ultralytics_yolo.py

    outputs/
      null_output.py
      log_output.py
      win_mouse.py

  algorithms/
    target_selection.py
    aim_point.py
    prediction.py
    control.py

  config/
    schema.py
    loader.py
```

目录可以在实现计划中微调，但模块边界应保持稳定。

## 核心数据模型

建议建立清晰、轻量的数据结构，避免各模块传递任意对象或直接依赖 ultralytics 的 box 对象。

关键数据类型：

- `FramePacket`
  - 图像帧
  - 时间戳
  - 帧序号
  - ROI 信息
  - 输入源名称

- `Detection`
  - bbox
  - confidence
  - class_id
  - class_name
  - detector-specific metadata 可选

- `DetectionPacket`
  - frame sequence
  - detections list
  - latency_ms
  - detector name
  - fresh flag

- `SelectedTarget`
  - selected detection
  - score
  - reason / score components
  - switched flag

- `AimMeasurement`
  - raw aim point
  - crosshair point
  - error vector
  - valid flag

- `PredictedAim`
  - predicted aim point
  - velocity estimate
  - confidence
  - tracking state

- `ControlCommand`
  - dx / dy
  - mode: relative / absolute / none
  - limited flag
  - reason

- `PipelineTickResult`
  - all intermediate states needed for logging and testing

这些结构要优先保持普通 Python dataclass / Protocol 兼容，方便未来迁移到 ONNX、C# 或 Rust 时复刻接口。

## 输入源设计

实时模式和视频模式只在输入源不同。

### 实时输入

`ScreenFrameSource` 负责：

- 根据 ROI 抓取屏幕帧。
- 提供帧序号和时间戳。
- 可选后台线程，但线程细节不进入核心 pipeline。

### 视频输入

`VideoFrameSource` 负责：

- 从视频文件读取帧。
- 将视频帧映射到与实时屏幕一致的画布/ROI 语义。
- 提供可重复的时间戳和帧序号。

视频回放不应该复制实时运行逻辑，而应该调用同一个 `Pipeline`。

## Detector 设计

第一版保留 ultralytics YOLO 检测能力，封装为 `UltralyticsYoloDetector`。

Detector 接口只暴露统一检测结果，不让后续算法直接依赖 ultralytics 内部对象。

第一版只预留 ONNX 迁移接口：

- 不实现 ONNX 推理。
- 不实现 YOLO ONNX 后处理。
- 不要求导出模型。
- 但 Detector 接口必须足够清晰，保证后续可以新增 `OnnxYoloDetector`。

## 算法模块设计

### TargetSelector

输入检测列表，输出选中目标。

职责：

- 类别偏好。
- 置信度评分。
- ROI / 准星距离评分。
- 目标粘性。
- 目标切换惩罚。
- 输出评分细节，便于日志解释。

### AimStrategy

输入选中目标和 ROI 信息，输出 raw aim point。

职责：

- 根据类别选择 bbox 内部瞄点。
- 支持头部/身体不同偏移。
- 完成 ROI 坐标到屏幕坐标转换。
- 不处理平滑、不处理 firing 状态、不处理鼠标输出。

### Predictor

输入 raw aim measurement，输出 predicted aim。

职责：

- 平滑。
- 速度估计。
- 短时丢帧保持。
- 跳变重置。
- 可配置 firing 时是否冻结或降低预测。

第一版可以从 alpha-beta 或 EMA + 速度预测中选择一种简单可解释实现，并通过日志评估。

### Controller

输入准星到 predicted aim 的误差，输出 `ControlCommand`。

职责：

- 死区。
- 加速度限制。
- 最大步长限制。
- 过冲保护。
- 输出平滑。
- 可解释的控制状态。

Controller 不直接移动鼠标，只生成命令。

## 输出后端设计

输出层实现 `OutputBackend` 接口。

第一版包含三类后端：

1. `NullOutput`
   - 什么也不做。
   - 作为默认后端。
   - 用于测试和安全运行。

2. `LogOutput`
   - 记录控制命令。
   - 不移动真实鼠标。
   - 用于视频回放和算法对比。

3. `WinMouseOutput`
   - 调用 Windows 鼠标 API。
   - 仅在配置显式启用时使用。
   - 与 Controller 解耦。

真实鼠标输出不应隐藏在算法或 pipeline 内部。

## 配置设计

第一版建议将当前扁平 `Config` 分组，减少到处 `getattr(config, key, default)` 的情况。

建议配置分组：

- `RuntimeConfig`
- `FrameSourceConfig`
- `DetectorConfig`
- `TargetSelectionConfig`
- `AimConfig`
- `PredictionConfig`
- `ControlConfig`
- `OutputConfig`
- `DiagnosticsConfig`

第一版可以继续从 `config.json` 加载，但内部应转换为分组 dataclass。旧字段兼容可以作为迁移步骤处理。

## 诊断与指标

因为成功标准是“综合基线”，第一版需要优先建立可重复评估能力。

视频回放和实时模式都应该能输出 JSONL 诊断日志。每帧记录：

- frame sequence
- timestamp
- detections
- selected target
- target switch flag
- raw aim
- predicted aim
- crosshair
- error distance
- control command
- output backend
- active / firing 状态
- detector latency
- pipeline latency
- target lost 状态

建议统计指标：

- 平均误差。
- 最大误差。
- 目标丢失次数。
- 目标切换次数。
- 输出命令平均幅度。
- 输出命令最大幅度。
- 输出平滑度。
- 过冲次数。
- 稳定时间。
- 检测延迟。

这些指标用于比较不同预测器和控制器，而不是凭主观感觉调参。

## Runtime 设计

`app/realtime.py` 和 `app/replay.py` 负责装配不同依赖。

核心 pipeline 不关心自己处于实时模式还是视频模式。

实时模式：

```text
ScreenFrameSource + UltralyticsYoloDetector + Pipeline + WinMouseOutput 或 LogOutput
```

视频模式：

```text
VideoFrameSource + UltralyticsYoloDetector + Pipeline + NullOutput 或 LogOutput
```

运行状态如 active / firing / exit signal 应作为输入状态传入 pipeline tick，而不是由算法模块直接读取 pynput listener。

## 测试策略

第一版测试应优先覆盖接口和算法行为。

建议测试：

1. `TargetSelector` 的评分和粘性选择。
2. `AimStrategy` 的 bbox 到屏幕坐标转换。
3. `Predictor` 的平滑、跳变重置、丢帧保持。
4. `Controller` 的死区、限速、过冲保护、输出限制。
5. `Pipeline` 在无检测、有检测、丢帧、目标切换、inactive、firing 下的行为。
6. `VideoFrameSource` 的 ROI/crosshair 映射。
7. `NullOutput` 和 `LogOutput` 不移动真实鼠标。

不要求第一版用真实鼠标输出作为自动测试条件。

## 迁移原则

实现时遵循以下原则：

1. 先建立新结构，再逐步迁移旧能力。
2. 不让算法模块依赖平台 API。
3. 不让 detector 直接控制目标选择策略。
4. 不让视频测试复制 runtime 逻辑。
5. 不让真实鼠标输出作为默认行为。
6. 不在第一版同时解决 UI、打包、ONNX 和跨语言问题。
7. 每一步都用测试和日志验证。

## 后续阶段

核心 pipeline 稳定后，可以依次进行：

1. 恢复或重做配置 UI。
2. 恢复 OpenCV 调试可视化。
3. 增加 ONNX detector。
4. 优化打包流程。
5. 将核心算法迁移到 C# / Rust / C++，如果确实需要。

## 验收标准

第一版重构完成后，应满足：

1. 可以用实时截图运行同一套 pipeline。
2. 可以用视频文件运行同一套 pipeline。
3. 默认输出后端不移动真实鼠标。
4. 显式配置后可以启用真实鼠标输出。
5. YOLO 检测能力可用。
6. 视频回放可以生成 JSONL 日志和汇总指标。
7. 至少有一组算法单元测试和 pipeline 测试通过。
8. 算法模块可以在不修改输入源和输出后端的情况下替换。
9. Detector 接口可以支持未来新增 ONNX 实现。
