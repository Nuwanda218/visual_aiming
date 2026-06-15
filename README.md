# 视觉辅助瞄准系统

基于 YOLOv8 的实时视觉辅助瞄准实验项目。当前架构已经收敛为一套运行逻辑：实时屏幕、视频回放和交互式视频调试都复用 `RuntimeRunner + ModularPipeline`，只替换输入源、输出后端和调试观察层。

## Current Runtime

```text
FrameSource -> RuntimeRunner -> ModularPipeline -> OutputBackend
                                |
                                +-> Diagnostics
```

核心处理链路：

```text
帧输入 -> YOLO 检测 -> 目标选择 -> 瞄点计算 -> 预测/保持 -> 相对控制命令 -> 输出后端
```

三种入口使用同一套 pipeline：

| 命令 | 输入源 | 输出 |
| --- | --- | --- |
| `python main.py` | 实时屏幕 ROI | 配置指定后端，默认安全空输出 |
| `python main.py --modular --video path\to\video.mp4` | 视频文件 | 配置指定后端 |
| `python main.py --video-test` | 文件选择器选中的视频 | 调试窗口、诊断日志、配置指定后端 |

## Project Layout

- `main.py` - CLI entrypoint.
- `src/visual_aiming/core/runtime_runner.py` - single runtime loop.
- `src/visual_aiming/core/pipeline.py` - modular aiming pipeline.
- `src/visual_aiming/adapters/frame_sources/` - screen and video input sources.
- `src/visual_aiming/adapters/outputs/` - null, log, and mouse outputs.
- `src/visual_aiming/app/` - realtime, replay, video-test compositions.
- `scripts/` - diagnostic and calibration utilities.
- `tests/` - unit tests for the single runtime architecture.

主要目录：

```text
src/visual_aiming/
  app/                    # 运行组合：realtime / replay / video_test
  core/                   # RuntimeRunner、ModularPipeline、通用数据模型
  algorithms/             # 目标选择、瞄点、预测、控制算法
  adapters/
    detectors/            # YOLO 适配器
    frame_sources/        # 屏幕和视频输入源
    outputs/              # null / log / Windows mouse 输出
  ports/                  # 输入、检测、输出、诊断端口协议
  config/                 # 配置 schema 和加载逻辑
  actions/                # 配置窗口、调试窗口、鼠标底层控制工具
  vision/                 # 兼容现有 YOLO / 截图能力的视觉模块
```

## Features

| Feature | Description |
| --- | --- |
| Single runtime | 实时、回放、视频测试共用 `RuntimeRunner` 和 `ModularPipeline` |
| Replaceable input | 支持屏幕截图源和视频文件源 |
| Replaceable output | 默认 `null` 安全输出，也支持日志和 Windows 鼠标输出 |
| YOLO adapter | 复用现有 YOLOv8 检测能力，并归一化为模块化检测数据 |
| Diagnostics | 可写 JSONL 日志并用内置分析器统计延迟、命令和目标连续性 |
| Safe mouse gate | 真实鼠标输出必须显式启用 |

## Setup

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果没有虚拟环境，可以先创建：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Usage

实时运行，默认不会移动真实鼠标：

```powershell
.venv\Scripts\python.exe main.py
```

视频回放：

```powershell
.venv\Scripts\python.exe main.py --modular --video path\to\video.mp4 --output null
```

交互式视频调试：

```powershell
.venv\Scripts\python.exe main.py --video-test
```

分析诊断日志：

```powershell
.venv\Scripts\python.exe main.py --analyze-log logs\run.jsonl
```

显式启用真实鼠标输出：

```powershell
.venv\Scripts\python.exe main.py --output win_mouse --real-mouse --mouse-method sendinput
```

## Mouse Calibration

鼠标控制分为两层：

- pipeline 输出的是屏幕坐标误差和相对控制命令。
- Windows 输出后端负责把命令转换为实际鼠标输入。

游戏内视角移动不是简单屏幕像素移动。后续角度控制、游戏灵敏度和 SendInput 增益校准计划见：

```text
docs/superpowers/plans/2026-06-13-mouse-angular-control.md
```

当前探针工具：

```powershell
.venv\Scripts\python.exe scripts\mouse_gain_probe.py --backend sendinput --dx 80 --dy 0 --count 2 --delay 2
```

## Development

运行测试：

```powershell
.venv\Scripts\python.exe -m unittest discover tests -v
```

编译检查：

```powershell
.venv\Scripts\python.exe -m compileall -q src tests scripts main.py
```

旧的实时运行路径已经删除。新增功能应接入现有单运行流程，优先复用：

- `FrameSource` 提供输入帧。
- `ModularPipeline.tick()` 处理算法。
- `OutputBackend.apply()` 执行输出。
- `Diagnostics.write()` 记录诊断。

## Notes

- `models/best.pt` 是默认模型路径。
- `config.json` 是本地运行配置，不应随手提交个人调参结果。
- `build/`、`dist/`、`logs/`、`.vscode/`、`.idea/` 和 Python 缓存都应保持为生成物或本地环境文件。
