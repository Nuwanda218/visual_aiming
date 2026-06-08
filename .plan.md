# 视频交互测试工具 — 实现计划

## 目标

创建一个交互式视频测试工具：
1. 弹出文件选择对话框选择视频
2. 视频按帧播放，OpenCV 窗口实时绘制检测框 + 瞄准点 + 控制方向箭头
3. 按键控制：按 `Space` 开始/暂停检测+鼠标吸附，按 `Q` 退出
4. 完全复用正式行为的管道（ModularPipeline），真实移动鼠标
5. 同时记录完整 JSONL 诊断日志，方便后续优化

## 核心设计

一个新文件 `src/visual_aiming/app/video_test.py`，包含：

### VideoTestRunner 类

```
- 打开视频（tkinter filedialog 选文件）
- 创建 ModularPipeline（复用 create_pipeline）  
  - output_backend = WinMouseOutput(enable_real_mouse=True)
  - diagnostics = JsonlDiagnostics（自动命名到 logs/ 目录）
- OpenCV 窗口按帧播放：
  - 帧率控制：按视频原始 fps 节奏播放（cv2.waitKey 控制）
  - 每帧画面上叠加：检测框(绿)、瞄准点(红)、预测点(黄)、crosshair(蓝十字)、控制向量箭头(品红)
  - 左上角 OSD 显示：fps / 检测延迟 / 管道延迟 / 当前状态
- 状态机：
  - PAUSED（默认）：视频暂停在当前帧，不跑检测，不动鼠标
  - ACTIVE：视频播放，每帧跑 pipeline.tick()，真实移动鼠标
  - 按 Space 在 PAUSED ↔ ACTIVE 之间切换
  - 按 Q/ESC 退出
```

### 入口

在 `main.py` 添加 `--video-test` 参数，运行时弹出文件选择器然后启动交互窗口。

## 涉及文件

| 文件 | 操作 |
|------|------|
| `src/visual_aiming/app/video_test.py` | 新建 — 主逻辑 |
| `main.py` | 修改 — 添加 `--video-test` 参数入口 |

## 数据流

```
视频文件 → cv2.VideoCapture → 裁切 ROI → FramePacket
  → ModularPipeline.tick() → PipelineTickResult
    → WinMouseOutput.apply()（真实鼠标移动）
    → JsonlDiagnostics.write()（记录日志）
    → OpenCV 窗口绘制叠加层
```

## 键盘操作

| 键 | 行为 |
|----|------|
| Space | 切换 暂停/激活 |
| Q / ESC | 退出并打印摘要 |
| ← → | 暂停时单帧前进/后退 |
