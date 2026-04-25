# visual-assisted-aiming

这是一个基于 YOLOv8 的实时视觉辅助瞄准实验项目。当前主链路是：

```text
固定 ROI 截图 -> YOLOv8 head/person 检测 -> 类别感知瞄点计算 -> 视觉伺服控制 -> 鼠标相对位移输出
```

项目仍处于快速迭代阶段，当前重点是目标选择稳定性、瞄点平滑、长按持续吸附、动态视角补偿和 GPU 推理性能。

## 目录结构

```text
.
├── main.py                    # 兼容启动入口，导入 src/visual_aiming/app.py
├── src/visual_aiming/         # 核心运行代码
├── models/                    # YOLO 模型权重
├── tools/                     # 调试/数据辅助工具
├── scripts/                   # 构建与维护脚本
├── docs/                      # 结构和设计说明
├── packaging/                 # 打包相关配置
├── config.json                # 本地运行配置
└── requirements.txt           # Python 运行依赖
```

更详细的文件说明见 [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md)。

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
- `detect_fps`: 主检测循环频率，和 `capture_fps` 分开调
- `detect_only_new_frames`: 只对新的截图帧做推理，避免重复跑同一帧
- `tracker_*`: 轻量目标速度预测参数
- `servo_*`: 视觉伺服控制参数
- `view_compensation_*`: 根据已发送鼠标位移修正旧瞄点的动态视角补偿
- `debug_enabled`: 调试窗口开关

## 当前架构

- `src/visual_aiming/detection.py`
  加载 YOLOv8，按 `head/person` 类别和目标连续性选择目标。

- `src/visual_aiming/capture_worker.py`
  独立截图线程，缓存最新 ROI 帧，避免截图阻塞检测主循环。

- `src/visual_aiming/target_tracker.py`
  轻量速度预测器，使用位置差分、EMA、反向急停重置和小速度清零。

- `src/visual_aiming/timing.py`
  短间隔精确 sleep 工具，用于截图线程和伺服线程。

- `src/visual_aiming/aim_calculator.py`
  将检测框映射为屏幕瞄点，并对大幅跳变做额外平滑。

- `src/visual_aiming/visual_servo.py`
  视觉伺服控制核心，包含位置/速度估计、近远场速度曲线、近场制动和丢测量后的 coast/lost 状态。

- `src/visual_aiming/mouse_control.py`
  独立高频鼠标控制线程，持续消费最新瞄点并发送相对鼠标位移。

- `src/visual_aiming/recoil.py`
  负责静态压枪曲线和动态视角补偿。

## 维护建议

重构后优先保持根目录 `main.py` 兼容入口不变。后续如果继续拆分，建议按功能边界拆：

- 感知层：截图、检测、目标选择
- 瞄点层：类别映射、平滑、目标锁定
- 控制层：伺服、鼠标输出、补偿
- 工具层：数据集、调参、打包
