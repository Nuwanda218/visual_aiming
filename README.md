# visual-assisted-aiming

这是一个基于 YOLOv8 的实时视觉辅助瞄准实验项目。当前主链路是：

```text
固定 ROI 截图 -> YOLOv8 head/person 检测 -> 类别感知瞄点计算 -> FPS 风格速度控制 -> 鼠标相对位移输出
```

项目仍处于快速迭代阶段，当前重点是目标选择稳定性、瞄点平滑、长按持续吸附、定点射击控制和 GPU 推理性能。

## 目录结构

```text
.
├── main.py                       # 稳定启动入口，负责把 src 加入 import path 并调用 visual_aiming.app
├── config.json                   # 本地运行配置，配置窗口会自动写回这里
├── requirements.txt              # Python 运行依赖
├── README.md                     # 项目说明和当前结构导览
├── models/
│   └── best.pt                   # YOLOv8 训练权重
├── src/
│   └── visual_aiming/
│       ├── __init__.py
│       ├── app.py                # 兼容入口，转发到 core.runtime.main()
│       ├── config.py             # Config dataclass，保存所有默认参数
│       ├── core/                 # 中间接口模块：主程序、调度、瞄点处理、目标预测
│       │   ├── runtime.py        # 当前主运行循环，串起视觉模块和操作模块
│       │   ├── aim_calculator.py # 检测框到屏幕瞄点的映射、平滑、开火锁点
│       │   ├── target_tracker.py # 轻量目标速度预测：差分速度、EMA、反向重置
│       │   ├── detect_scheduler.py # 检测频率调度：普通/开火/空闲节奏
│       │   └── throttle.py       # 时间节流工具，控制部分检测节奏
│       ├── vision/               # 视觉模块：截图、YOLO 推理、检测结果输出
│       │   ├── screen_capture.py # 同步 ROI 截图实现
│       │   ├── capture_worker.py # 独立截图线程，缓存最新 ROI 帧
│       │   └── detection.py      # YOLOv8 加载、推理、目标选择和检测结果缓存
│       ├── actions/              # 操作模块：鼠标、键鼠状态、调试 UI
│       │   ├── input_listener.py # 键鼠状态监听：Shift/右键/左键/Ctrl+Q
│       │   ├── mouse_control.py  # FPS 风格鼠标控制、相对位移输出、绝对移动测试模式
│       │   ├── debug_visualizer.py # OpenCV 调试窗口，显示检测框和瞄点
│       │   ├── config_window.py  # Tkinter 运行时参数窗口，修改后自动保存 config.json
│       │   └── visual_servo.py   # 旧视觉伺服控制器，当前保留作参考/回退
│       └── common/               # 通用工具
│           ├── timing.py         # 精确 sleep 工具
│           ├── resource_path.py  # 资源路径辅助，兼容打包环境
│           └── utils.py          # 通用工具，目前主要是限频打印
├── scripts/
│   └── build_exe.py              # PyInstaller 构建脚本
├── packaging/
│   └── aim_assist.spec           # PyInstaller spec 文件
└── docs/
    └── PROJECT_STRUCTURE.md      # 简版项目结构说明
```

更详细的文件说明见 [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)。

`test.py` 是本地未跟踪测试文件，不属于正式项目结构。

## 运行

先确认 VSCode/Python 解释器指向项目虚拟环境：

```powershell
.\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"
```

启动：

```powershell
python .\main.py
```

程序需要管理员权限。当前 `main.py` 会在非管理员启动时自动请求提权。

## 关键配置

主要参数在 `config.json`：

- `yolo_device`: `auto` 时优先使用 CUDA
- `yolo_imgsz`: YOLO 推理尺寸
- `aim_target_preference`: 越接近 `1.0` 越偏向 head，越接近 `0.0` 越偏向 person
- `target_stickiness`: 目标连续性权重，降低多目标快速切换
- `capture_thread_enabled`: 启用独立截图线程
- `runtime_poll_fps`: 主状态轮询/目标喂给频率
- `detect_fps`: 主检测循环频率，和 `capture_fps` 分开调
- `firing_detect_fps`: 开火时检测频率
- `idle_detect_fps`: 已激活但未开火时的空闲检测频率
- `detect_only_new_frames`: 只对新的截图帧做推理，避免重复跑同一帧
- `tracker_*`: 轻量目标速度预测参数
- `fps_*`: 鼠标速度状态、加速度、减速半径和近场刹车参数
- `servo_output_gain` / `servo_step_limit` / `servo_loop_hz`: 最终鼠标输出和控制线程参数
- `mouse_absolute_mode_enabled`: 绝对移动测试模式，直接把系统鼠标移到瞄准点，用于排查瞄点坐标问题
- `servo_overshoot_guard_*`: 近距离防越界输出限制，减少左右/上下摆动
- `firing_*`: 开火时的锁点、微动死区和跟随参数
- `debug_enabled`: 调试窗口开关
- `config_ui_enabled`: 运行时参数面板开关

## 当前架构

当前代码已经按三层结构拆分：视觉模块、核心接口模块、操作模块。核心调度集中在 `src/visual_aiming/core/runtime.py`。

### 启动层

- `main.py`: 兼容启动入口。正常运行时从这里启动。
- `src/visual_aiming/app.py`: 兼容入口，转发到 `core.runtime.main()`。
- `src/visual_aiming/core/runtime.py`: 当前真正的程序主体。负责管理员权限检查、加载配置、初始化各模块、运行主循环和退出清理。
- `src/visual_aiming/config.py`: 默认配置定义。
- `config.json`: 当前本地实际运行配置。程序启动时读取，配置窗口修改后写回。
- `src/visual_aiming/actions/config_window.py`: 运行时配置面板，负责把参数实时写入 `Config` 对象并自动保存。

### 视觉模块

视觉模块只负责“看见什么”，不直接控制鼠标。

- `src/visual_aiming/vision/screen_capture.py`: 同步截图实现。
- `src/visual_aiming/vision/capture_worker.py`: 独立截图线程。主循环只读取最新帧，减少截图阻塞。
- `src/visual_aiming/vision/detection.py`: YOLOv8 模型加载与推理。它把 ROI 图像变成目标框，并根据 `head/person`、置信度、目标粘性选择当前目标。
- `models/best.pt`: 当前 YOLO 模型权重。

### 核心接口模块

核心接口模块是主程序所在层，负责接收视觉模块输出，计算瞄点和控制目标，再把操作指令交给操作模块。

- `src/visual_aiming/core/runtime.py`: 运行时调度中心，连接视觉模块和操作模块。
- `src/visual_aiming/core/detect_scheduler.py`: 检测调度器，根据 active/firing/idle 状态决定什么时候跑 YOLO。
- `src/visual_aiming/core/throttle.py`: 额外节流工具，避免检测过密。
- `src/visual_aiming/core/aim_calculator.py`: 把检测框转成屏幕坐标瞄点。这里处理 `head/person` 的瞄准倾向、平滑、大跳变切换、开火锁点、微动死区。
- `src/visual_aiming/core/target_tracker.py`: 目标速度预测器。使用位置差分、EMA、小速度清零和反向重置，减少目标短暂丢失或移动时的跳变。

### 操作模块

操作模块只负责“实际做什么”，包括读取设备输入、鼠标输出、调试显示和配置窗口。

- `src/visual_aiming/actions/input_listener.py`: 监听热键和鼠标状态。当前激活逻辑是 `Shift + 右键`，左键表示开火。
- `src/visual_aiming/actions/mouse_control.py`: 当前主要鼠标控制模块。默认用 FPS 风格速度控制，把瞄点相对准星的误差转成鼠标相对位移。也支持 `mouse_absolute_mode_enabled`，直接把系统鼠标移动到瞄点，用于排查瞄点坐标是否正确。
- `src/visual_aiming/actions/debug_visualizer.py`: 调试窗口，显示当前 ROI、检测框和瞄点。
- `src/visual_aiming/actions/config_window.py`: 运行时配置面板。
- `src/visual_aiming/actions/visual_servo.py`: 旧视觉伺服控制器。当前主链路不直接使用，保留用于参考或回退。

### 通用模块

- `src/visual_aiming/common/timing.py`: 高精度 sleep。
- `src/visual_aiming/common/utils.py`: 限频打印等小工具。
- `src/visual_aiming/common/resource_path.py`: 资源路径辅助，主要服务打包场景。
- `scripts/build_exe.py` / `packaging/aim_assist.spec`: 打包相关文件。

## 运行时数据流

当前主循环可以按这条链路理解：

```text
main.py
  -> core.runtime.main()
  -> Config.load(config.json)
  -> WakeUpModule 监听激活/开火状态
  -> CaptureWorker 持续截图固定 ROI
  -> DetectionScheduler 决定是否执行检测
  -> TargetDetector.detect(frame)
  -> AimPointCalculator.calculate(target)
  -> TargetTracker.update/predict()
  -> MouseController.update_target()
  -> mouse_event 相对位移输出
```

开调试窗口时，检测框和瞄点会同时传给：

```text
DebugVisualizer.update(frame, bbox, aim_point, crosshair)
```

## 当前状态与重构切入点

现在已经完成了第一步文件结构拆分，但 `core/runtime.py` 内部仍然是一个较大的主循环。后续重构时，建议继续保持外部行为不变，只把核心层内部职责拆细：

- `RuntimeState`: active/firing/last_aim/last_capture_seq 等运行状态
- `RuntimeServices`: detector/capture/mouse/debug/config_ui 等模块实例
- `Pipeline`: 视觉输出 -> 瞄点 -> 操作指令
- `schemas.py`: DetectionResult/AimPoint/ControlCommand 等数据结构

## 维护建议

重构后优先保持根目录 `main.py` 兼容入口不变。后续如果继续拆分，建议按功能边界拆：

- 视觉模块：截图、检测、目标选择
- 核心接口模块：类别映射、平滑、目标锁定、调度状态
- 操作模块：鼠标输出、调试窗口、配置窗口
- 工具层：数据集、调参、打包
