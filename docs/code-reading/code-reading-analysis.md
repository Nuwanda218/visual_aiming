# 视觉辅助瞄准系统源码阅读分析

## 理解验证状态

| 核心概念 | 自我解释 | 理解为什么 | 应用迁移 | 状态 |
| --- | --- | --- | --- | --- |
| 单一运行时架构 | 已梳理入口到 runner | 已确认复用原因 | 可迁移到新输入/输出 | 已掌握 |
| ModularPipeline | 已拆成检测、选择、瞄点、预测、控制 | 已确认每阶段职责 | 可替换算法或后端 | 已掌握 |
| 安全输出边界 | 已确认默认 null output | 已确认真实鼠标双开关 | 可安全增加输出 | 已掌握 |
| 配置映射 | 已确认旧 flat config 到 dataclass | 已确认兼容目的 | 可继续迁移配置结构 | 基本掌握 |
| 测试约束 | 已反向阅读架构和核心测试 | 已确认边界测试意图 | 可作为改动护栏 | 已掌握 |

## 项目完整地图

### 完整目录树

```text
.
├─ main.py                         # CLI 入口
├─ config.json                     # 运行配置，当前工作区已有未提交修改
├─ requirements.txt                # ultralytics/opencv/mss/pynput
├─ README.md                       # 当前运行架构说明
├─ models/                         # 模型文件
├─ scripts/                        # 构建、诊断、回放、鼠标增益探测脚本
├─ docs/                           # 设计文档、历史计划、调试流程
├─ packaging/                      # PyInstaller spec
├─ src/visual_aiming/
│  ├─ app/                         # realtime/replay/video_test/log_analyzer 组合层
│  ├─ core/                        # RuntimeRunner、ModularPipeline、schema、metrics
│  ├─ algorithms/                  # 目标选择、瞄点、预测、相对控制
│  ├─ adapters/                    # detector/frame_source/output 外部适配器
│  ├─ ports/                       # Protocol 接口边界
│  ├─ config/                      # dataclass schema 与旧配置映射
│  ├─ actions/                     # GUI、可视化、底层鼠标控制等旧/工具层
│  ├─ common/                      # Windows 鼠标发送、路径、计时工具
│  └─ vision/                      # 旧 YOLO 检测、截图能力
└─ tests/                          # 单一运行时架构测试
```

### 文件清单（分类）

| 类别 | 代表文件 | 职责摘要 |
| --- | --- | --- |
| 入口 | `main.py` | 解析 CLI，选择运行模式，加载配置，分发到 app 层 |
| 运行时核心 | `core/runtime_runner.py` | 从 FrameSource 读取帧，调用 pipeline，通知 observer，负责关闭资源 |
| 业务核心 | `core/pipeline.py` | 单帧处理链路：检测、选目标、算瞄点、预测、控制、输出、诊断 |
| 数据模型 | `core/schemas.py` | FramePacket、Detection、SelectedTarget、PipelineTickResult 等中间状态 |
| 算法 | `algorithms/*.py` | 可独立测试的目标选择、瞄点策略、alpha-beta 预测、相对控制 |
| 外部适配 | `adapters/**` | YOLO、屏幕/视频输入、null/log/win_mouse 输出 |
| 配置 | `config/schema.py`, `config/loader.py` | 模块化配置 dataclass 与旧 flat JSON 字段映射 |
| 诊断 | `core/metrics.py`, `app/log_analyzer.py` | JSONL 写入、摘要、日志统计报告 |
| 测试 | `tests/test_*.py` | 架构边界、pipeline、算法、输出安全、CLI 模式、诊断分析 |

### 入口文件 + 核心调用链

```text
main.py
  parse_args()
  main()
    choose_runtime_mode(args)
      ANALYZE_LOG     -> app.log_analyzer.analyze_jsonl + format_report
      VIDEO_TEST      -> app.video_test.run_video_test()
      MODULAR_REPLAY  -> _run_modular() -> app.replay.run_video_file()
      MODULAR_REALTIME-> _run_modular() -> app.realtime.run_realtime()

run_realtime()/run_replay()
  create frame source
  create_pipeline()
    create_ultralytics_detector()
    create_output_backend()
    optional JsonlDiagnostics
    ModularPipeline(config, detector, output, diagnostics)
  RuntimeRunner(frame_source, pipeline).run()
    while frame_source.read():
      pipeline.tick(frame, now)
```

核心处理链路：

```text
FramePacket
  -> detector.detect(frame)
  -> TargetSelector.select(detections, roi_center)
  -> AimStrategy.measure(selected.detection, roi_offset, crosshair)
  -> AlphaBetaPredictor.update(aim, mode, now)
  -> RelativeController.update(predicted_error, active, dt)
  -> output_backend.apply(command, result)
  -> diagnostics.write(result)
```

## 1. 快速概览

这是一个基于 YOLOv8 的实时视觉辅助瞄准实验项目。当前代码已经从旧式耦合运行逻辑收敛到单一 runtime：实时屏幕、视频回放、交互式视频测试都复用 `RuntimeRunner + ModularPipeline`，区别只在输入源、输出后端、调试观察层。

项目规模约 109 个文件，其中 Python 文件 82 个。核心代码集中在 `src/visual_aiming/core`、`algorithms`、`adapters`、`app`，测试集中在 `tests`。依赖为 `ultralytics==8.4.41`、`opencv-python==4.13.0.92`、`mss==10.2.0`、`pynput==1.8.1`。

## 2. 背景与动机（3 个 WHY）

### 问题本质

要解决的问题是把实时画面中的目标检测结果转换为安全、可控、可诊断的相对鼠标移动命令。不写这层统一 pipeline，实时模式、视频模式、调试模式会各自复制检测、选择、控制逻辑，导致行为分叉，调参和修 bug 无法复用。

### 方案选择

选择 `RuntimeRunner + ModularPipeline` 的原因是它把“循环读取帧”和“单帧业务处理”拆开。这样输入源可以是屏幕、视频、数组测试帧，输出可以是 null、log、真实鼠标，但核心算法只需维护一份。替代方案是每个 app 自己写完整 loop，但测试已经明确禁止回到旧 runtime 路径，并用架构边界测试防止 core 反向依赖 app/adapters/vision。

### 应用场景

适用场景是需要高频、低延迟、可调试的视觉控制实验：实时屏幕 ROI、离线视频回放、人工视频测试。它不适合直接作为无保护的真实鼠标自动控制程序，因为项目刻意把真实鼠标输出放在显式开关后面，默认 `NullOutput` 避免误移动。

## 3. 核心概念网络

### 核心概念清单

**FramePacket**：单帧输入载体，包含图像、序号、时间戳、ROI 偏移、ROI 尺寸、准星坐标和运行模式。需要它是因为 pipeline 不应该知道帧来自屏幕还是视频，所有输入差异都在 frame source 中归一化。

**RuntimeRunner**：通用循环器，只负责读帧、调用 pipeline、通知 observer、关闭资源。这样做的原因是 replay 和 realtime 的差异不应该污染单帧处理逻辑；runner 越薄，测试和替换越容易。

**ModularPipeline**：核心单帧处理单元。它依次执行检测、目标选择、瞄点、预测、控制、输出和诊断，是项目最值得优先深读的文件。

**TargetSelector**：在多个 detection 中选择当前目标。它把 class 偏好、距离、置信度、连续性、切换惩罚合成一个分数，避免目标在相近候选之间频繁跳变。

**AlphaBetaPredictor**：对瞄点做轻量预测和短时保持。需要它是因为检测可能短暂丢帧或目标移动，直接使用瞬时 detection 会抖动；alpha-beta 比卡尔曼滤波更简单，参数也更直观。

**RelativeController**：把屏幕误差转换为相对移动 dx/dy。它处理 deadzone、速度增益、减速半径、加速度平滑、单帧最大步长和亚像素累积。

**OutputBackend**：输出边界。默认 null，log 只记录命令，win_mouse 只有显式启用才发送真实鼠标输入。

### 概念关系矩阵

| 关系类型 | 概念 A | 概念 B | WHY 这样关联 |
| --- | --- | --- | --- |
| 顺序 | FrameSource | RuntimeRunner | runner 只消费抽象 read/close，不关心来源 |
| 顺序 | RuntimeRunner | ModularPipeline | runner 管循环，pipeline 管单帧业务 |
| 组合 | ModularPipeline | algorithms | 算法类独立，便于单元测试和替换 |
| 边界 | ModularPipeline | OutputBackend | 输出行为可替换，真实鼠标被安全隔离 |
| 诊断 | PipelineTickResult | JsonlDiagnostics | 每阶段中间状态都进入结果，便于日志反查 |
| 约束 | tests | architecture layers | 测试锁定依赖方向，防止核心层重新耦合外部实现 |

## 4. 算法与理论

### 目标评分选择

`TargetSelector._score_fast()` 计算总分：class 60%、距离 30%、置信度 10%，再加连续性奖励和类别切换惩罚。分数越低越优。这个方案适合实时场景，因为它是 O(n log n) 排序，候选框数量通常较小，计算成本低于检测本身。

选择这种启发式而不是跟踪器 ID 或复杂多目标跟踪，是因为当前 YOLO 适配器只提供 detection，不提供稳定 ID。启发式足够解释、调参成本低，并且测试覆盖了“优先 head”“sticky 延迟小切换”“明显更好才切换”等行为。

### Alpha-Beta 预测

`AlphaBetaPredictor` 使用位置和速度状态。新 measurement 到来时，先按上次位置和速度预测，再用 residual 更新位置和速度；没有 measurement 时，在 hold window 内输出 held 预测，超时后 lost。复杂度 O(1)。

选择 alpha-beta 的原因是它比卡尔曼滤波少矩阵建模，适合本项目这种低维、实时、调参频繁的控制链路。退化场景是目标跳变、时钟回退或检测误配，所以代码用 `reset_distance`、`raw_dt < 0`、`hold_ms` 做保护。

### 相对控制

`RelativeController` 基于误差距离计算目标速度，再用加速度参数平滑到当前速度，最后按 dt 和 output_gain 转为相对移动。deadzone 防止小误差抖动，decel_radius 让接近目标时减速，max_step 限制单帧移动幅度，subpixel 保存舍入残差。

这个控制器不是物理完整 PID，而是更直接的速度型控制。优势是参数少、输出有硬限制、便于解释；代价是游戏内视角和屏幕像素之间仍需要单独增益校准，README 也提示鼠标控制分为 pipeline 命令和 Windows 输出两层。

## 5. 设计模式

### Ports and Adapters

应用位置：`ports/`、`adapters/`、`core/pipeline.py`、`app/realtime.py`。

core 通过协议/轻量接口接收 detector、output、diagnostics，不直接依赖 YOLO、OpenCV、mss 或 Windows API。这样做可以让算法和 pipeline 在测试里使用 fake detector、fake output，也能让 replay 使用视频源而 realtime 使用屏幕源。不这样拆，测试会被真实屏幕、模型和鼠标环境绑死。

### Strategy / Component Composition

应用位置：`TargetSelector`、`AimStrategy`、`AlphaBetaPredictor`、`RelativeController`。

pipeline 并不把所有算法写在一个函数里，而是在初始化时组合多个小组件。好处是每个组件都有独立状态和测试边界；坏处是要追踪完整行为时需要跨文件阅读。

### Safe Default

应用位置：`OutputConfig`、`create_output_backend()`、`WinMouseOutput`。

默认 `backend=null` 且 `enable_real_mouse=False`。即使用户选择 `win_mouse`，没有显式 real mouse 开关也会回落到 `NullOutput`。这是项目最重要的安全设计之一，测试也直接覆盖了这一点。

## 6. 关键代码深度解析

### 核心片段清单（6A）

| 编号 | 片段名称 | 所在文件 | 优先级 | 识别理由 |
| --- | --- | --- | --- | --- |
| #1 | `ModularPipeline.tick` | `src/visual_aiming/core/pipeline.py:65` | 高 | 单帧处理主流程，连接所有算法和输出 |
| #2 | `TargetSelector.select/_score_fast` | `src/visual_aiming/algorithms/target_selection.py:18` | 高 | 多目标选择和防跳变核心逻辑 |
| #3 | `AlphaBetaPredictor.update` | `src/visual_aiming/algorithms/prediction.py:22` | 高 | 目标预测、保持、丢失状态的来源 |
| #4 | `RelativeController.update` | `src/visual_aiming/algorithms/control.py:27` | 高 | 把误差转换为相对鼠标命令 |
| #5 | `create_output_backend/WinMouseOutput.apply` | `adapters/outputs/*` | 高 | 真实鼠标安全边界 |
| #6 | `RuntimeRunner.run_once/run` | `src/visual_aiming/core/runtime_runner.py` | 中 | 统一实时/回放循环 |

### 片段 #1：`ModularPipeline.tick`

位置：`src/visual_aiming/core/pipeline.py:65-132`。

一句话核心：把一个 `FramePacket` 转换成完整 `PipelineTickResult`，并把控制命令交给输出和诊断后端。

执行流程：

```text
frame + mode
  -> inactive? reset + noop result
  -> detector.detect
  -> selector.select
  -> aim_strategy.measure
  -> predictor.update
  -> controller.update or no_target
  -> _build_result
  -> _publish(output + diagnostics)
```

关键设计点是所有阶段都被计时并写入 `LatencyBreakdown`。这让后续日志分析能判断瓶颈在检测、选择、预测、控制还是等待。inactive 分支会 reset selector/predictor/controller，避免停用后继续沿用旧目标状态。

### 片段 #2：`TargetSelector.select`

位置：`src/visual_aiming/algorithms/target_selection.py:18-57`。

它先把 detections 转成列表，没有候选时返回 `no_detections` 并清空 previous。存在候选时，为每个 detection 计算 score，按 score 排序得到最佳目标；如果 sticky 目标仍在历史半径内，且新目标没有明显优于 sticky 目标，就保持旧目标。

这个设计解决的是目标抖动问题。YOLO 每帧输出可能略有变化，如果只选“当前最优”，准星会在相近框之间跳；sticky 机制牺牲一点瞬时最优，换取连续控制稳定性。

### 片段 #3：`AlphaBetaPredictor.update`

位置：`src/visual_aiming/algorithms/prediction.py:22-91`。

有有效 measurement 时接受测量，初始化或更新位置/速度；没有 measurement 时，如果仍在 `hold_ms` 内则输出 held 预测，否则 reset 并返回 lost。`firing_freeze` 会在开火状态冻结速度，避免射击瞬间继续推预测速度。

这层让 pipeline 能区分“真丢失”和“短暂缺帧”。测试里 `test_predictor_holds_recent_track_when_measurement_missing` 和 `test_predictor_reports_lost_after_hold_window` 明确验证了这个边界。

### 片段 #4：`RelativeController.update`

位置：`src/visual_aiming/algorithms/control.py:27-70`。

输入是预测点相对准星的误差，输出是相对移动 `dx/dy`。误差在 deadzone 内返回 noop；误差较大时根据距离和 speed_gain 得到目标速度；接近目标时用 near_speed_scale 减速；最后用 acceleration 平滑速度，并限制单帧 max_step。

subpixel 累积是一个重要细节。每帧移动必须是整数像素，但速度积分可能得到小数，直接 round 会长期丢失小位移；保存 `move_x - dx` 和 `move_y - dy` 能让小误差在后续帧累积出来。

### 片段 #5：输出安全边界

位置：`src/visual_aiming/adapters/outputs/factory.py`、`win_mouse.py`。

`create_output_backend()` 只有在 `backend == "win_mouse"` 且 `enable_real_mouse` 为真时才创建 `WinMouseOutput`。其他情况，包括只设置 `backend=win_mouse` 但未开 real mouse，都会返回 `NullOutput`。

这是项目的安全阀。真实鼠标输出还会在 `WinMouseOutput.apply()` 中再次检查 `enable_real_mouse`，并且只对 `command.mode == "relative"` 且 dx/dy 非零的命令调用 sender。

## 7. 测试用例分析

### 测试文件清单

| 测试文件 | 覆盖模块 | 重点 |
| --- | --- | --- |
| `test_architecture_boundaries.py` | 架构边界 | 禁止 core/algorithms/config 等层反向依赖 |
| `test_modular_pipeline.py` | pipeline | inactive、正常目标、偏移命令、无检测 |
| `test_modular_algorithms.py` | algorithms | 目标选择、sticky、瞄点、预测、控制 |
| `test_modular_outputs.py` | outputs/common mouse | null/log/win_mouse、安全开关、Windows 结构 |
| `test_modular_apps.py` | app/CLI/diagnostics | 输出工厂、replay runner、log analyzer、main parser |
| `test_runtime_runner.py` | RuntimeRunner | 读到 None 停止、observer、close |
| `test_runtime_modes.py` | mode selection | analyze_log、video_test、replay、默认实时优先级 |
| `test_modular_schemas_config.py` | schemas/config | 数据模型、旧配置映射、安全默认值 |

### 功能覆盖矩阵

| 核心功能 | 测试覆盖 | 覆盖率评估 |
| --- | --- | --- |
| CLI 模式选择 | 有 | 优先级清晰 |
| 单帧 pipeline | 有 | 覆盖主路径和 no target/inactive |
| 目标选择 | 有 | 覆盖 sticky 和切换阈值 |
| 预测保持/丢失 | 有 | 覆盖 held/lost |
| 相对控制 | 有 | 覆盖 deadzone 和 max_step |
| 真实鼠标安全 | 有 | 覆盖双开关和 sender 选择 |
| 外部 YOLO 实际推理 | 有限 | 多数为适配层/假对象测试，真实模型行为需手动或集成验证 |
| GUI video_test | 部分 | observer 和入口委托有测，完整 GUI 行为不适合纯单测 |

## 8. 应用迁移场景

### 场景 1：新增另一种检测器

新增 detector 时，应实现与 `UltralyticsYoloDetector.detect(frame)` 等价的接口，返回 `DetectionPacket`。接入点在 `adapters/detectors/factory.py` 或更上层的 app 组合函数。不要让 core 直接 import 新 detector，否则会破坏架构边界测试。

### 场景 2：新增输出后端

新增输出如网络发送、录制、模拟器接口，应放在 `adapters/outputs/`，并扩展 `create_output_backend()`。如果输出会产生外部副作用，应模仿 `win_mouse` 的显式启用开关和测试方式，默认安全关闭。

### 场景 3：替换控制算法

可以在 `algorithms/control.py` 增加新控制器，或让 `ModularPipeline` 根据 config 选择不同 controller。需要保留 `ControlCommand` 输出协议，这样 output 层不需要知道控制算法细节。

## 9. 依赖关系与使用示例

### 外部库

| 依赖 | 用途 |
| --- | --- |
| `ultralytics` | YOLOv8 模型检测 |
| `opencv-python` | 视频文件读取、调试显示相关能力 |
| `mss` | 屏幕截图 |
| `pynput` | 输入监听相关能力 |
| Windows `ctypes` API | 真实鼠标 set cursor/sendinput |

### 使用示例

默认实时运行，不移动真实鼠标：

```powershell
.venv\Scripts\python.exe main.py
```

视频回放：

```powershell
.venv\Scripts\python.exe main.py --modular --video path\to\video.mp4 --output null
```

分析诊断日志：

```powershell
.venv\Scripts\python.exe main.py --analyze-log logs\run.jsonl
```

真实鼠标输出必须显式启用：

```powershell
.venv\Scripts\python.exe main.py --output win_mouse --real-mouse --mouse-method sendinput
```

## 10. 质量验证清单

- 已建立项目地图：入口、核心、算法、适配器、测试、文档已分类。
- 已确认核心调用链：`main.py -> app -> RuntimeRunner -> ModularPipeline -> output/diagnostics`。
- 已确认安全默认值：默认 `NullOutput`，真实鼠标需要 `--output win_mouse --real-mouse`。
- 已确认架构边界：测试禁止 core/algorithms/config 等层依赖外部实现层。
- 已确认主要风险：真实 YOLO/屏幕/GUI/鼠标行为依赖环境，单元测试主要覆盖抽象和假对象。
- 后续深读建议：优先深挖 `pipeline.py`、`target_selection.py`、`prediction.py`、`control.py`、`win_mouse.py`，再看 `video_test.py` 和 `log_analyzer.py`。


---

# 源码阅读扩展报告

## 11. 模块级地图

| 包 | 规模 | 角色 | 优先阅读文件 |
| --- | ---: | --- | --- |
| `core` | 10 files / 902 lines | 运行时核心、数据模型、诊断写入 | `pipeline.py`, `runtime_runner.py`, `schemas.py`, `metrics.py` |
| `algorithms` | 5 files / 340 lines | 纯算法组件，最容易单测和替换 | `target_selection.py`, `prediction.py`, `control.py`, `aim_point.py` |
| `adapters` | 12 files / 388 lines | 外部实现适配：YOLO、屏幕/视频、输出 | `detectors/ultralytics_yolo.py`, `frame_sources/*`, `outputs/factory.py` |
| `app` | 8 files / 979 lines | 运行组合层和用户入口行为 | `realtime.py`, `replay.py`, `video_test.py`, `log_analyzer.py` |
| `config` | 3 files / 334 lines | dataclass 配置和旧 JSON 字段映射 | `schema.py`, `loader.py` |
| `ports` | 5 files / 89 lines | Protocol 抽象边界 | 全部较小，可一次读完 |
| `vision` | 4 files / 532 lines | 旧 YOLO 检测和屏幕截图能力 | `detection.py`, `screen_capture.py` |
| `actions` | 6 files / 1358 lines | GUI、鼠标、旧视觉伺服/工具能力 | `config_window.py`, `mouse_control.py`, `visual_servo.py` |
| `common` | 5 files / 153 lines | Windows API、路径和计时工具 | `mouse_sender.py` |

索引文件：`docs/code-reading/code-reading-index.json`。它记录了 59 个源码模块、内部 import、类/函数符号和测试提及关系。模块摘要文件：`docs/code-reading/code-reading-module-summaries.json`。

## 12. 运行路径详解

### 12.1 默认实时路径

`python main.py` 默认进入 `RuntimeMode.MODULAR_REALTIME`。这点不是 README 推断，而是 `choose_runtime_mode()` 最后一行直接返回 `MODULAR_REALTIME`，测试 `test_default_modular_realtime` 锁定了这个行为。

实时路径创建 `ScreenFrameSource`，该 frame source 通过旧 `vision.screen_capture.ScreenCapture` 抓 ROI，并把 ROI offset、crosshair、runtime mode 放入 `FramePacket`。随后 `RuntimeRunner` 以循环方式调用 `pipeline.tick()`。输出默认来自 `create_output_backend(config.output)`，配置默认是 `null`。

### 12.2 视频回放路径

`python main.py --modular --video path` 进入 `MODULAR_REPLAY`。`run_video_file()` 创建 `VideoFileFrameSource`，用 OpenCV `VideoCapture` 一帧帧读取，直到 `read()` 返回 None。`run_replay()` 使用 `RuntimeRunner(..., clock=lambda: None)`，让 pipeline 默认用 frame timestamp，而不是墙钟。

这个路径适合稳定复现实验，因为输入视频和输出诊断可以固定。它也绕开屏幕捕获和实时等待，是调试算法变化的首选入口。

### 12.3 交互式视频测试路径

`--video-test` 进入 `app/video_test.py`。它先通过文件选择器选择视频，然后创建 `VideoTestRunner`。这个 runner 用 `VideoDebugObserver` 接收 runtime tick 结果，叠加 OSD、写诊断日志，并支持逐帧/播放控制。

注意：`video_test.py` 在运行时会把 config output 改成真实鼠标输出相关设置。真实执行风险取决于具体代码路径和配置，后续若要修改视频测试，必须重新核对 `config.output.enable_real_mouse` 的设置点，避免调试模式绕开默认安全策略。

### 12.4 日志分析路径

`--analyze-log logs/run.jsonl` 最高优先级进入 `app/log_analyzer.py`。分析器读取 JSONL 结果，统计检测输出率、目标丢失率、相对命令率、非零命令率、延迟分位数、目标连续段、异常段、目标中心跳变和命令幅度分布。

这些指标来自 `PipelineTickResult` 和 `LatencyBreakdown`。这解释了为什么 pipeline 不只返回命令，还要保留 detections、selected、aim、predicted、command、telemetry 等中间态：诊断需要完整链路，而不是只看最终 dx/dy。

## 13. 依赖方向与架构约束

架构边界测试给出的依赖方向如下：

```text
config       独立，不依赖 runtime 层
ports        独立协议，不依赖实现层
algorithms   可依赖 config/core schema，不依赖 app/adapters/vision/actions
core         可组合 algorithms/config schema，不依赖 app/adapters/vision/actions
adapters     依赖 ports/core/config 和外部库，不依赖 app/algorithms/actions
app          组合 core/adapters/config，避免直接依赖具体 output 实现
vision/actions 旧能力和底层工具层，主要通过 adapters/app 间接进入新 runtime
```

关键维护原则：修改 `core` 或 `algorithms` 时，不要 import `visual_aiming.vision`、`visual_aiming.actions`、`visual_aiming.app`、`visual_aiming.adapters`。如果需要外部能力，先定义协议或把实现放到 adapter。

## 14. 数据模型阅读

`core/schemas.py` 是理解系统的词典：

- `RuntimeMode`：当前帧是否 active、是否 firing。
- `FramePacket`：图像和几何上下文。
- `Detection`：标准化检测框，屏蔽 YOLO/旧 detector 差异。
- `DetectionPacket`：检测结果集合、检测耗时、detector 名、fresh 标记。
- `SelectedTarget`：选择结果、score、score_parts、是否 switched、reason。
- `AimMeasurement`：瞄点、准星、误差、valid。
- `PredictedAim`：预测点、速度、置信度、状态 tracking/held/lost/reset/inactive。
- `ControlCommand`：dx/dy、mode、limited、reason。
- `PipelineTickResult`：单帧完整结果，也是 diagnostics/log_analyzer 的数据源。

阅读时应先掌握这些模型，再读算法。否则容易把坐标系搞混：检测框坐标在 ROI 内，瞄点会加 `roi_offset` 转到屏幕坐标，误差再相对 `crosshair` 计算。

## 15. 配置系统详解

`config/schema.py` 是新模块化配置，按 runtime/frame/detector/target_selection/aim/prediction/control/output/diagnostics 分组。`config/loader.py` 负责把旧 `config.json` 的扁平字段映射进这些 dataclass。

重要字段：

| 分组 | 字段 | 作用 |
| --- | --- | --- |
| runtime | `poll_fps`, `detect_fps`, `idle_detect_fps` | 控制循环和检测节奏 |
| frame | `roi_size`, `capture_fps` | 屏幕捕获区域和帧率 |
| detector | `model_path`, `confidence`, `iou`, `device`, `half`, `imgsz` | YOLO 推理配置 |
| target_selection | `target_preference`, `sticky_enabled`, `history_radius`, `class_switch_penalty` | 目标选择稳定性 |
| aim | `head_bias`, `body_bias` | 框内垂直瞄点位置 |
| prediction | `alpha`, `beta`, `lead_time`, `reset_distance`, `hold_ms` | 预测和平滑 |
| control | `deadzone`, `speed_gain`, `max_speed`, `acceleration`, `decel_radius`, `max_step` | 相对控制输出 |
| output | `backend`, `enable_real_mouse`, `mouse_method` | 输出后端和真实鼠标开关 |
| diagnostics | `enabled`, `jsonl_path`, `summary_path` | 诊断写入 |

当前仓库的 `config.json` 已处于 modified 状态。阅读中没有修改它。后续如果要调参，应先保存当前差异，再明确是实验配置还是默认配置。

## 16. Adapter 与外部边界

### Detector Adapter

`adapters/detectors/ultralytics_yolo.py` 包装旧 `vision.detection.TargetDetector`。它把旧 detector 返回的单个 target 转成标准 `DetectionPacket`。如果旧 detector 没有输出，返回空 detections；如果有输出，则构造 `Detection`，保留 bbox、confidence、class_id、class_name。

这里是新旧架构的桥。新 pipeline 以为自己依赖标准 detector，实际 detector 内部仍复用旧 YOLO 类。这样迁移成本低，但也意味着 `vision/detection.py` 的行为会影响新 runtime。

### FrameSource Adapter

`ScreenFrameSource` 负责实时屏幕帧，`VideoFileFrameSource` 负责视频文件，`ArrayFrameSource` 主要服务测试。它们统一输出 `FramePacket`，这是 runtime 可复用的关键。

### Output Adapter

输出后端包括 `NullOutput`、`LogOutput`、`WinMouseOutput`。`NullOutput` 是默认安全后端；`LogOutput` 记录命令；`WinMouseOutput` 调用 `common.mouse_sender`，后者用 Windows `ctypes` 实现 `SetCursorPos` 或 `SendInput`。

修改输出层时必须保留两层保护：factory 层保护和 output apply 层保护。测试已经覆盖这两层。

## 17. Vision 与 Actions 旧能力层

`vision/detection.py` 是旧 YOLO 检测核心，负责模型加载、设备选择、推理、bbox 后处理等。新 adapter 仍依赖它，所以它不是死代码。它的复杂度主要来自外部模型和运行设备，而不是算法本身。

`vision/screen_capture.py` 和 `capture_worker.py` 提供屏幕截图能力。`ScreenFrameSource` 通过它们拿实时 ROI。

`actions/` 下有配置窗口、调试可视化、输入监听、鼠标控制、旧视觉伺服。它们不是新 modular pipeline 的核心，但仍可能被 GUI 和旧工具路径使用。`visual_servo.py` 包含另一套 alpha-beta/filter/relative servo 思路，阅读时应和 `algorithms/` 区分：当前 README 描述的主路径以 `algorithms + ModularPipeline` 为准。

## 18. 诊断系统

`JsonlDiagnostics.write(result)` 会把每帧结果转成 JSONL，关闭时写 summary。`_strict_jsonable` 会把非有限浮点转换为 None，避免 JSON 中出现 NaN/Infinity。

`log_analyzer.py` 做二次分析：

- 延迟：detector、pipeline、display fps、frame work、wait。
- 检测：检测输出率、可见目标检出率、空场景误检率。
- 目标：丢失率、切换数、最长追踪段、最大中心跳变。
- 命令：相对命令率、非零命令率、命令原因分布、命令幅度分位数。
- 异常段：连续无检测、连续丢失、连续零指令。

这套诊断适合在调参后比较行为变化。它也说明后续改算法时不能只看视觉效果，应该保存 JSONL 并跑 analyzer。

## 19. 测试反推的真实需求

从测试可以反推出项目最看重的需求：

1. 运行路径必须统一。测试禁止旧 runtime 文件复活，也验证 replay/realtime/video_test 走 `RuntimeRunner`。
2. 算法必须可独立测试。目标选择、瞄点、预测、控制都没有真实 YOLO 依赖。
3. 输出必须默认安全。`win_mouse` 需要显式 real mouse flag。
4. 日志语言和指标名称要准确。比如测试要求“检测输出率”，不允许误叫“检测命中率”。
5. 配置要兼容旧字段。`loader.py` 映射旧 flat config，并用测试固定行为。
6. 架构边界是硬约束。新增功能应先找正确层，而不是方便地跨层 import。

## 20. 风险与注意事项

| 风险 | 位置 | 说明 | 建议 |
| --- | --- | --- | --- |
| Python 版本 | 全项目 | 默认 `python` 是 3.8.6，不支持 `dataclass(slots=True)` | 使用 `D:\Python\python.exe` 或 Python >= 3.10/3.11 |
| 真实鼠标副作用 | `outputs/win_mouse.py`, `video_test.py` | 真实鼠标移动有外部副作用 | 保持默认 null；改动后跑输出安全测试 |
| 旧/新架构并存 | `vision/`, `actions/`, `adapters/` | 新 adapter 仍复用旧 detector/screen capture | 修改旧层时确认新 runtime 是否间接受影响 |
| 坐标系混淆 | `FramePacket`, `AimStrategy`, `Pipeline` | ROI 坐标、屏幕坐标、准星坐标混用风险高 | 写测试时明确 roi_offset/crosshair |
| 配置字段迁移 | `config/loader.py` | 旧 flat 字段和新 dataclass 字段并存 | 新字段要补 loader 和测试 |
| GUI 路径难单测 | `app/video_test.py`, `actions/config_window.py` | Tk/OpenCV 交互完整行为难自动化 | 用 observer/纯函数拆小单元测试 |
| 模型/设备差异 | `vision/detection.py` | YOLO、CUDA、half、device 影响运行 | 保留设备解析测试，真实运行前 warmup/诊断 |

## 21. 后续修改导航

| 想改什么 | 优先看 | 测试入口 |
| --- | --- | --- |
| 改目标选择策略 | `algorithms/target_selection.py` | `tests.test_modular_algorithms.TargetSelectorTest` |
| 改瞄点位置 | `algorithms/aim_point.py`, `config/schema.py` | `AimStrategyTest`, config 测试 |
| 改预测/保持 | `algorithms/prediction.py` | `PredictorTest`, pipeline lost/held 测试 |
| 改鼠标速度/手感 | `algorithms/control.py`, `common/mouse_sender.py` | `ControllerTest`, `test_modular_outputs` |
| 新增输出后端 | `adapters/outputs/factory.py` | `test_modular_outputs`, `test_modular_apps` |
| 新增检测器 | `adapters/detectors/` | adapter 测试 + pipeline fake detector 测试 |
| 改配置窗口 | `actions/config_window.py` | `test_config_window_sections.py` |
| 改视频调试 | `app/video_test.py`, `video_overlay.py` | `test_modular_apps`, `test_video_test_runtime_runner` |
| 改诊断报告 | `app/log_analyzer.py`, `core/metrics.py` | `test_modular_apps`, `test_modular_metrics` |
| 改架构依赖 | 多层 | 必跑 `test_architecture_boundaries.py` |

## 22. 建议阅读顺序

1. `core/schemas.py`：先掌握数据词典。
2. `main.py`、`core/runtime_modes.py`：确认入口分发。
3. `app/realtime.py`、`app/replay.py`：看运行组合。
4. `core/runtime_runner.py`：看循环抽象。
5. `core/pipeline.py`：看单帧主流程。
6. `algorithms/*.py`：逐个看目标选择、瞄点、预测、控制。
7. `adapters/*`：看外部边界。
8. `config/*`：看参数如何进系统。
9. `core/metrics.py`、`app/log_analyzer.py`：看如何评估行为。
10. `app/video_test.py`、`vision/*`、`actions/*`：最后看交互和旧能力层。

## 23. 本轮产物

- `docs/code-reading/code-reading-analysis.md`：源码阅读主文档。
- `docs/code-reading/code-reading-index.json`：模块索引、内部 import、测试提及关系。
- `docs/code-reading/code-reading-module-summaries.json`：大文件符号和流程摘要。

这三个文件共同构成后续继续分析或改代码的导航基础。
