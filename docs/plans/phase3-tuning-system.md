# 第三阶段实施计划 — 调参系统

## 背景

目前有 25 个可调参数分布在 9 个子类、6 个架构层中。已有 `--tune capture` 可视化 ROI 调参窗口和 `--tune config` 配置调参窗口，但调参体验还有提升空间。

## 目标

让每个可调参数都能在运行时实时调整并立即看到效果，降低调参门槛。

## 设计

### 调参窗口结构

基于现有 OpenCV 窗口系统，改为**标签页 + trackbar** 结构：

```
┌─────────────────────────────────────────────────┐
│  [capture] [perception] [targeting] [tracker]   │  ← 标签页切换
│  [smoothing] [control] [runtime]                 │
├─────────────────────────────────────────────────┤
│                                                  │
│              实时画面预览（可选显示）               │
│                                                  │
├─────────────────────────────────────────────────┤
│                                                  │
│  当前标签页的参数滑块区域                           │
│  ┌─────────────────────────────────────────┐    │
│  │ alpha          [========●======] 0.55   │    │
│  │ jitter_radius  [====●==========] 2.0    │    │
│  │ stable_frames  [==●============] 2      │    │
│  │ hold_frames    [===●===========] 3      │    │
│  └─────────────────────────────────────────┘    │
│                                                  │
│  [S] 保存  [R] 恢复默认  [Q] 退出               │
└─────────────────────────────────────────────────┘
```

### 实现方式

每个标签页对应一个配置子类（PerceptionConfig / ControlConfig 等）。
标签页内每个参数一条 trackbar。

**参数类型与 trackbar 映射：**

| 参数类型 | trackbar 实现 |
|---------|--------------|
| `int`（范围已知） | cv2.createTrackbar，直接映射 |
| `float`（0~1） | trackbar 0~100 映射为 0.0~1.0 |
| `float`（大范围，如 speed=180） | trackbar 0~200 映射为 0~400 |
| `str`（如 head_label） | 不设 trackbar，用文本输入 |
| `bool`（如 smoothing.enabled） | trackbar 0/1 切换 |

### 标签页规划

#### 标签 1：capture（已有，保持）

4 个参数：ROI 宽高、准星偏移。现有 CaptureTuner 功能完整，**不需要改动**。

#### 标签 2：perception

4 个参数：model_path（字符串，不设 trackbar）、confidence（0.05~0.95）、iou（0.1~0.9）、device（下拉选择）。

#### 标签 3：targeting

2 个参数：head_bias（0.05~0.50）、body_bias（0.05~0.50）。
head_label / person_label 是字符串，不设 trackbar。

#### 标签 4：tracker

5 个参数：match_distance_ratio（0.3~1.5）、min_match_distance（5~80）、size_ratio_min（0.2~1.0）、size_ratio_max（1.0~3.0）、lost_frame_grace（0~10）。

#### 标签 5：smoothing

4 个可调参数：enabled（0/1）、alpha（0.1~0.95）、jitter_radius（0~10）、stable_frames（0~8）、hold_frames（0~10）。

#### 标签 6：control

5 个参数：speed（20~500）、acceleration（0.05~0.95）、deadzone（0~15）、near_radius（10~300）、near_speed_scale（0.05~1.0）。

#### 标签 7：runtime

1 个参数：detect_fps（5~60）。

### 实时预览

调参窗口覆盖在视频画面上，openCV 画面同时显示：
- 当前配置下的检测框（如果正在跑检测）
- 选中目标的锁定状态
- 瞄准点和准星位置

这样调参时能立即看到参数变化对吸附效果的影响。

### 配置文件关联

- 启动时读取 `config.v2.json`
- 拖动 trackbar 时实时更新内存中的 Config 对象
- 按 S 保存当前所有标签页的参数到 `config.v2.json`
- 按 R 恢复为默认值
- 退出时提示是否保存

---

## 实施步骤

### S1：统一调参窗口框架

新建 `interaction/tuner_v2.py`，实现标签页式调参窗口基类。

每个标签页是一个函数，接收 Config 对象和 frame 图像，渲染 trackbar 并处理更新。

```python
def _tab_perception(config, frame):
    """渲染 perception 标签页的 trackbar。"""
    cv2.createTrackbar("confidence", win_name, ...)
    cv2.createTrackbar("iou", win_name, ...)
```

### S2：实现各标签页

按上述标签页规划逐个实现：

| 标签页 | 文件 | 参数数 |
|--------|------|--------|
| capture | 已有（CaptureTuner） | 4 |
| perception | 新增 | 2 (model_path 和 device 为文本) |
| targeting | 新增 | 2 |
| tracker | 新增 | 5 |
| smoothing | 新增 | 5 |
| control | 新增 | 5 |
| runtime | 新增 | 1 |

### S3：CLI 入口

```
python main_v2.py --tune all --video test.mp4    ← 打开完整调参窗口
python main_v2.py --tune control --video test.mp4 ← 只调控制参数
```

### S4：config.v2.json 自动生成

首次运行时如果没有 `config.v2.json`，自动用默认值生成一份，方便用户修改。

---

## 涉及文件

| 文件 | 操作 | 内容 |
|------|------|------|
| `interaction/tuner_v2.py` | 新建 | 标签页式调参窗口 |
| `interaction/cli.py` | 修改 | `--tune` 支持更多模式 |
| `docs/reference/config-parameters.md` | 已完成 | 参数手册 |

## 验证

- `python main_v2.py --tune all --video test.mp4` 打开完整调参窗口
- 切换标签页，拖动滑块，观察画面效果变化
- 按 S 保存，重新启动后参数保持一致
- 173 个已有测试不受影响
