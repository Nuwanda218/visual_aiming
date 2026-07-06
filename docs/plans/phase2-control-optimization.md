# V2 第二阶段实施计划 — 控制算法优化

## 背景

第一阶段已完成六层架构搭建和基础瞄准功能。实际测试中发现两个核心问题：
1. 同一目标的瞄准点在帧间抖动（检测框尺寸每帧不同）
2. 多目标时没有切换逻辑，瞄准点可能在目标间反复跳

本计划通过三个优化逐步叠加解决这两个问题，全部在 actuation 层内部完成。

## 当前 actuation 层数据流

```
Actuator.process(detections):
    select_target()      → 选一个目标（有头选头）
    compute_aim_point()  → 算瞄准点（带偏置）
    compute_error()      → 算误差向量
    FpsController.update() → 速度平滑输出
    → Command(dx, dy)
```

优化后的数据流：

```
Actuator.process(detections):
    TargetTracker.update()    → 目标 ID 追踪 + 切换迟滞   [P6 新增]
    select_target()           → 选一个目标（有头选头）
    compute_aim_point()       → 算原始瞄准点
    AimSmoother.smooth()      → Kalman 平滑 + 切换过渡    [P5+P7 新增]
    compute_error()           → 算误差向量
    FpsController.update()    → 速度平滑输出
    → Command(dx, dy)
```

## 涉及文件

| 文件 | 操作 | 内容 |
|------|------|------|
| `actuation/aim_filter.py` | P5 新建 / P7 修改 | AimSmoother：Kalman 滤波平滑 + 切换过渡 |
| `actuation/tracker.py` | P6 新建 | TargetTracker：IOU 匹配 + 目标 ID + 切换迟滞 |
| `actuation/targeting.py` | P5/P6/P7 修改 | Actuator 整合新组件 |
| `shared/config.py` | P5/P6/P7 修改 | 新增配置参数 |
| `shared/schemas.py` | P6 修改 | Detection 可选增加 track_id 字段 |
| `tests/test_v2_actuation.py` | P5/P6/P7 修改 | 新增测试 |

---

## P5：瞄准点 Kalman 平滑

### 目标

消除帧间检测框尺寸变化导致的瞄准点抖动。即使 YOLO 每帧给出略有不同的 bbox，瞄准点也应该平稳移动。

### 原理

Kalman 滤波器维护一个状态估计 `[x, y, vx, vy]`（位置 + 速度），每帧：
1. **预测**：用上一帧的速度推算本帧位置
2. **更新**：用新的检测瞄准点修正预测

如果新观测值和预测值很接近（正常抖动），修正很小 → 输出平滑。
如果新观测值偏离很大（目标真的在动），修正较大 → 快速跟上。

```
帧 N:   原始瞄准点 (150, 102)  → Kalman 输出 (150, 101)
帧 N+1: 原始瞄准点 (148, 105)  → Kalman 输出 (149, 102)   ← 抖动被吸收
帧 N+2: 原始瞄准点 (152, 100)  → Kalman 输出 (150, 101)   ← 稳定
帧 N+3: 原始瞄准点 (200, 150)  → Kalman 输出 (185, 135)   ← 目标真的在动，快速跟上
```

### 实现

新建 `actuation/aim_filter.py`：

```python
class AimSmoother:
    """瞄准点 Kalman 平滑器。"""

    def __init__(self, process_noise=0.1, measurement_noise=1.0, hold_frames=5):
        ...
        # 状态: [x, y, vx, vy]
        # Kalman 矩阵: F(状态转移), H(观测), Q(过程噪声), R(观测噪声), P(协方差)

    def smooth(self, raw_point: tuple[int,int] | None) -> tuple[int,int] | None:
        """输入原始瞄准点，输出平滑后的瞄准点。"""
        if raw_point is None:
            # 目标丢失：用速度继续预测，hold_frames 帧后放弃
            return self._predict_hold()
        # 正常更新：Kalman predict → update
        return self._kalman_update(raw_point)

    def reset(self):
        """目标切换时重置滤波器。"""
```

修改 `Actuator.process()`，在 `compute_aim_point()` 之后、`compute_error()` 之前插入：

```python
aim_point = compute_aim_point(selected, ...)
aim_point = self.smoother.smooth(aim_point)    # ← P5 新增
error = compute_error(aim_point, self.crosshair)
```

### 配置参数

```python
# shared/config.py 新增
smooth_process_noise: float = 0.1       # 过程噪声（越大越跟手）
smooth_measurement_noise: float = 1.0   # 观测噪声（越大越平滑）
smooth_hold_frames: int = 5             # 目标丢失后继续预测帧数
```

### 测试用例

```python
def test_smoother_reduces_jitter():
    """相同位置附近的微小抖动应被吸收。"""
    smoother = AimSmoother()
    points = [(100,100), (102,98), (99,101), (101,100), (100,99)]
    results = [smoother.smooth(p) for p in points]
    # 输出应该比输入更集中在 (100,100) 附近

def test_smoother_follows_real_movement():
    """目标真的在移动时，平滑后的点应该跟上。"""
    smoother = AimSmoother()
    for i in range(10):
        smoother.smooth((100 + i*10, 100))
    result = smoother.smooth((200, 100))
    # 最终输出应该接近 (200, 100)

def test_smoother_holds_on_target_lost():
    """目标丢失后应继续预测几帧。"""
    smoother = AimSmoother(hold_frames=3)
    smoother.smooth((100, 100))
    smoother.smooth((110, 100))  # 向右移动
    result = smoother.smooth(None)  # 丢失
    assert result is not None  # 应该继续预测
```

### 验证

- `--visual`：观察红色瞄准点是否不再抖动
- 对比：暂时关闭 smoother（`smooth_process_noise=999`），看差异

---

## P6：目标锁定 + 被动切换

### 目标

锁定当前瞄准的目标，只要它还在就不切换。只有当锁定目标从检测中消失时，才被动切换到下一个最近的目标。

### 原理

**不做主动切换。** 不管有没有更近的新目标出现，只要当前锁定目标还能被 IOU 匹配到，就一直瞄它。

```
帧 N:   ROI 内有 A(远) B(近)
        → 首次选择：锁定 B（最近的）

帧 N+1: ROI 内有 A(远) B(近) C(更近)
        → B 的 IOU 匹配成功 → 继续瞄 B（忽略更近的 C）

帧 N+2: ROI 内有 A(远) C(更近)，B 消失了
        → B 的 IOU 匹配失败 → 释放锁定 → 选最近的 C → 锁定 C
```

**IOU 匹配判断"同一个目标"：** 计算锁定目标上一帧 bbox 与当前帧每个检测框的交叉比。IOU 最高且超过阈值的认为是同一个目标。

```
帧 N:   锁定目标 bbox = (100, 80, 45, 60)
帧 N+1: 检测框 A = (102, 82, 43, 58)  IOU = 0.85 → 同一个目标 ✓
         检测框 B = (300, 200, 50, 70)  IOU = 0.00 → 不同目标
```

### 实现

新建 `actuation/tracker.py`：

```python
class TargetTracker:
    """目标锁定器：锁定当前目标，只在目标消失时被动切换。"""

    def __init__(self, iou_threshold=0.3):
        self.locked_target: Detection | None = None  # 当前锁定的目标
        self.locked_frames = 0                       # 已锁定帧数

    def update(self, detections, crosshair, head_label, person_label) -> Detection | None:
        """每帧调用：返回应该瞄准的目标。"""
        if not detections:
            self.locked_target = None
            self.locked_frames = 0
            return None

        # 有锁定目标 → 用 IOU 在当前帧找它
        if self.locked_target is not None:
            matched = self._find_iou_match(detections)
            if matched is not None:
                # 找到了 → 继续瞄它（更新 bbox 为当前帧的位置）
                self.locked_target = matched
                self.locked_frames += 1
                return matched
            # 找不到了 → 释放锁定，往下走选新目标

        # 没有锁定目标（首次 / 目标消失）→ 选离准星最近的，锁定
        best = select_target(detections, crosshair, head_label, person_label)
        self.locked_target = best
        self.locked_frames = 1
        return best

    def reset(self):
        """热键停用时重置。"""
        self.locked_target = None
        self.locked_frames = 0

    def _find_iou_match(self, detections) -> Detection | None:
        """在当前帧检测中找到与锁定目标 IOU 最高的匹配。"""
        best_iou = 0.0
        best_match = None
        for det in detections:
            iou = self._compute_iou(self.locked_target, det)
            if iou > best_iou:
                best_iou = iou
                best_match = det
        if best_iou >= self.iou_threshold:
            return best_match
        return None

    def _compute_iou(self, a: Detection, b: Detection) -> float:
        """计算两个检测框的 IOU。"""
        x1 = max(a.x, b.x)
        y1 = max(a.y, b.y)
        x2 = min(a.x + a.w, b.x + b.w)
        y2 = min(a.y + a.h, b.y + b.h)
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = a.w * a.h
        area_b = b.w * b.h
        union = area_a + area_b - intersection
        return intersection / union if union > 0 else 0.0
```

修改 `Actuator.process()`，用 tracker 替代 select_target：

```python
def process(self, detections):
    # P6: 目标锁定（只在目标消失时被动切换）
    selected = self.tracker.update(detections, self.crosshair, ...)

    if selected is None:
        return Command.noop("no_target")

    aim_point = compute_aim_point(selected, ...)
    aim_point = self.smoother.smooth(aim_point)  # P5
    error = compute_error(aim_point, self.crosshair)
    ...
```

### 配置参数

```python
# shared/config.py 新增
tracker_iou_threshold: float = 0.3   # IOU 低于此值认为目标消失
```

只有一个参数。不需要 hysteresis 和 cooldown——因为不做主动切换。

### 测试用例

```python
def test_locks_nearest_target_initially():
    """首次应锁定离准星最近的目标。"""

def test_keeps_locked_target_when_iou_matches():
    """锁定目标位置略有变化但 IOU 足够时，应继续瞄它。"""

def test_ignores_closer_new_target():
    """有更近的新目标出现时，只要锁定目标还在就不切换。"""

def test_switches_when_locked_target_disappears():
    """锁定目标从检测中消失时，应切换到下一个最近的。"""

def test_switches_to_none_when_all_targets_gone():
    """所有目标都消失时，返回 None。"""

def test_iou_computation():
    """IOU 计算正确性：完全重合=1，完全不重合=0，部分重合在0~1之间。"""
```

### 验证

- `--visual`：多目标场景下，白色加粗框应始终锁定同一个目标，不跳
- `--verbose`：TRACK 行显示 locked_frames 持续递增，target_id 不变

---

## P7：开枪时保持吸附（长远目标）

### 问题

游戏中枪械有后坐力，开枪时准星被强制上抬。当前的瞄准纠正会产生大幅鼠标移动来拉回准星，效果不佳。

### 方向

需要在开枪时补偿后坐力，使准星保持稳定。具体方案待 P5+P6 完成并实测后再设计。

---

## 执行顺序

```
P5 瞄准点 Kalman 平滑
    ↓  commit
P6 目标锁定 + 被动切换
    ↓  commit
```

P5 先让同一目标的瞄准点稳定，P6 再让多目标不乱切。P7 作为长远目标，待实测后决定方案。

## 后续方向（P5~P6 完成后）

| 方向 | 内容 |
|------|------|
| 调参系统 | 给所有新参数加到 OpenCV 调参窗口，运行时拖滑块实时调 |
| 数据分析 | JSONL 日志 + 分析报告（跟踪稳定性、切换频率、抖动量） |
| 武器适配 | 不同武器不同参数组（狙击高平滑、冲锋低平滑） |
| 模型升级 | 训练 YOLOv8s 或导出 TensorRT |
| 截屏优化 | 后台线程截屏或 DXcam 库 |

---

## 二阶段补充计划：V2 配置解耦 + 控制稳定性修正

### 背景

当前根目录 `config.json` 是 V1/V1 modular 的遗留配置，字段平铺且包含大量 V2 不使用的参数。V2 重构阶段如果继续读取该文件，会产生两个问题：

1. 用户调整旧字段时，V2 实际不生效，调参反馈不可靠。
2. V2 的控制、锁定、平滑参数和架构层级不匹配，后续维护成本高。

因此，第二阶段后续工作不再以兼容旧 `config.json` 为目标，而是为 `src/visual_aiming_v2/` 建立专用配置体系，再基于新配置修复当前实测问题：鼠标跟随慢、多目标抢准星、静止目标抖动。

### 目标

1. 新增 V2 专用配置文件，建议命名为 `config.v2.json`，避免污染和误读旧版 `config.json`。
2. 将 `shared/config.py` 从平铺 dataclass 重构为按架构层分组的嵌套 dataclass。
3. 更新 V2 各层只读取 V2 配置结构。
4. 在新配置体系上修复三类行为问题：
   - 鼠标移动速度太慢，跟不上移动目标。
   - 多目标同时存在时，锁定目标容易被其他目标抢走。
   - 静止目标存在帧间检测抖动，导致准星小幅晃动。

### 推荐配置结构

新增 `config.v2.json`：

```json
{
  "perception": {
    "model_path": "models/best.pt",
    "confidence": 0.5,
    "iou": 0.45,
    "device": "auto"
  },
  "capture": {
    "image_width": 410,
    "image_height": 315,
    "crosshair_offset_x": 0,
    "crosshair_offset_y": 0
  },
  "targeting": {
    "head_label": "head",
    "person_label": "person",
    "head_bias": 0.35,
    "body_bias": 0.25
  },
  "tracker": {
    "match_distance_ratio": 0.75,
    "min_match_distance": 18.0,
    "size_ratio_min": 0.55,
    "size_ratio_max": 1.8,
    "lost_frame_grace": 2
  },
  "smoothing": {
    "enabled": true,
    "alpha": 0.55,
    "jitter_radius": 2.0,
    "stable_frames": 2,
    "hold_frames": 3
  },
  "control": {
    "speed": 180.0,
    "acceleration": 0.45,
    "deadzone": 3.0,
    "near_radius": 80.0,
    "near_speed_scale": 0.35
  },
  "runtime": {
    "detect_fps": 30.0
  },
  "output": {
    "backend": "null"
  }
}
```

### 配置模型调整

修改 `src/visual_aiming_v2/shared/config.py`，建议拆成以下 dataclass：

| 配置类 | 职责 |
|------|------|
| `PerceptionConfig` | YOLO 模型、置信度、IOU、设备 |
| `CaptureConfig` | ROI 尺寸、准星偏移 |
| `TargetingConfig` | head/person 标签和瞄点偏置 |
| `TrackerConfig` | Detection 框匹配、尺寸比例校验、丢帧容忍 |
| `SmoothingConfig` | 待诊断确认；倾向 EMA/稳定窗口平滑、hold，避免与旧 Kalman 叠加 |
| `ControlConfig` | FPS 鼠标速度、加速度、死区、近距离减速 |
| `RuntimeConfig` | 实时检测频率等运行参数 |
| `OutputConfig` | 输出后端 |
| `Config` | 聚合以上配置块 |

### 涉及文件

| 文件 | 操作 | 内容 |
|------|------|------|
| `config.v2.json` | 新建 | V2 专用配置文件 |
| `src/visual_aiming_v2/shared/config.py` | 重构 | 嵌套 dataclass，替代平铺字段 |
| `src/visual_aiming_v2/interaction/cli.py` | 修改 | 默认读取 `config.v2.json`；解析嵌套配置；CLI 参数覆盖配置；新增 V2 调参入口 |
| `src/visual_aiming_v2/interaction/tuner.py` | 重构/扩展 | 从单一 CaptureTuner 扩展为精简 V2 配置界面，支持 capture/control/tracker/smoothing 必要参数 |
| `src/visual_aiming_v2/capture/sources.py` | 修改 | 使用 `config.capture.*` |
| `src/visual_aiming_v2/perception/detectors.py` | 修改 | 使用 `config.perception.*` |
| `src/visual_aiming_v2/actuation/targeting.py` | 修改 | 使用 `config.capture/targeting/tracker/smoothing/control`；目标切换时 reset smoother |
| `src/visual_aiming_v2/actuation/control.py` | 修改 | 让速度、加速度、死区、近距离减速参数来自 `ControlConfig` |
| `src/visual_aiming_v2/actuation/tracker.py` | 修改 | 增加中心距离匹配和丢帧容忍 |
| `src/visual_aiming_v2/actuation/aim_filter.py` | 修改 | 增加静止小抖动吸附机制 |
| `src/visual_aiming_v2/runtime/realtime.py` | 修改 | 使用 `config.runtime.detect_fps` |
| `tests/test_v2_schemas.py` | 修改 | 配置 dataclass 测试 |
| `tests/test_v2_cli.py` | 修改 | V2 配置文件加载与调参入口测试 |
| `tests/test_v2_actuation.py` | 修改 | 控制、锁定、平滑行为回归测试 |
| `tests/test_v2_config_tuner.py` | 新建 | 精简配置界面读写/参数映射测试 |

### V2 精简配置界面设计

#### 目标

V2 配置全量重构后，需要新增一个配置界面方便调参，但必须避免 V1 配置窗口的问题：字段过多、含义重叠、历史参数残留、用户不知道哪些参数真的生效。

本阶段配置界面只暴露“实测需要频繁调整且直接影响行为”的参数，不做全字段编辑器。

#### 界面原则

1. **只服务 V2**：只读写 `config.v2.json` 的嵌套结构，不读取旧 `config.json` 平铺字段。
2. **参数少而准**：每个滑块都必须能映射到当前 V2 运行链路中的真实字段。
3. **按问题分组**：围绕 ROI、速度、锁定、平滑四组，不复制 V1 的大量 servo/firing 遗留项。
4. **保留手写能力**：界面只负责常用数值调参；模型路径、输出后端等低频配置仍可手动编辑 JSON 或走 CLI。
5. **安全默认**：调参界面默认不移动真实鼠标，推荐配合 `--video --visual` 或 `--realtime --output log --visual` 使用。

#### 推荐暴露参数

| 分组 | 参数 | 用途 |
|------|------|------|
| Capture | `capture.image_width` / `capture.image_height` | 调整 ROI 尺寸 |
| Capture | `capture.crosshair_offset_x` / `capture.crosshair_offset_y` | 调整 ROI 内准星偏移 |
| Control | `control.speed` | 控制最大跟随速度/基础速度 |
| Control | `control.acceleration` | 控制速度追随快慢 |
| Control | `control.deadzone` | 控制静止误差死区 |
| Control | `control.near_radius` | 近距离减速半径 |
| Control | `control.near_speed_scale` | 近距离最低速度比例 |
| Tracker | `tracker.match_distance_ratio` | 以锁定框对角线比例计算允许中心距离 |
| Tracker | `tracker.min_match_distance` | 小框场景下的最小允许匹配距离 |
| Tracker | `tracker.size_ratio_min/max` | 判断是否同一框的尺寸变化范围 |
| Tracker | `tracker.lost_frame_grace` | 短暂漏检容忍帧数 |
| Smoothing | `smoothing.enabled` | 是否启用平滑器 |
| Smoothing | `smoothing.alpha` | 倾向 EMA 方案时的跟随系数 |
| Smoothing | `smoothing.jitter_radius` | 小幅检测噪声半径 |
| Smoothing | `smoothing.stable_frames` | 判定静止稳定所需连续帧数 |
| Smoothing | `smoothing.hold_frames` | 目标丢失后的保持帧数 |
| Runtime | `runtime.detect_fps` | 实时 YOLO 检测频率 |

#### 暂不进入配置界面的参数

| 参数类型 | 原因 |
|------|------|
| `perception.model_path` | 字符串路径不适合滑块，继续用 JSON/CLI |
| `perception.confidence` / `perception.iou` | 可以后续加入，但当前二阶段重点是控制稳定性 |
| `targeting.head_label` / `person_label` | 类别名低频变动，手动 JSON 更清晰 |
| `targeting.head_bias` / `body_bias` | 可后续加入；本轮先避免界面过载 |
| `output.backend` | 涉及安全输出，继续走 CLI 显式选择 |

#### 建议交互方式

沿用 OpenCV 窗口实现，不引入复杂 GUI 框架：

```bash
python main_v2.py --tune config --video test.mp4 --config config.v2.json
```

窗口行为：

1. 默认显示视频帧、ROI、准星、检测框、选中目标、原始瞄点、平滑瞄点、控制箭头。
2. 使用分组页切换：`1=Capture`、`2=Control`、`3=Tracker`、`4=Smoothing`、`5=Runtime`。
3. 每页只显示该组滑块，避免一个窗口堆满所有参数。
4. `S` 保存到 `config.v2.json`。
5. `R` 恢复本次打开前的配置。
6. `Q/ESC` 退出。

#### 实施拆分

1. 第一轮只实现配置读写和滑块映射，不要求热更新真实运行中的对象。
2. 视频调参模式中，每次滑块变化后，用当前帧/当前检测结果重新跑一次 V2 actuation，观察目标锁定、平滑瞄点和控制输出变化。
3. 实时热更新放到后续方向，避免本轮引入线程安全和运行时状态同步复杂度。

### 执行顺序

#### Step 1：测试先行，锁定期望行为

新增/修改测试，先观察失败：

1. `tests/test_v2_cli.py`
   - 默认配置路径应为 `config.v2.json`。
   - 能读取嵌套 JSON 到 `Config`。
   - `--model` 应覆盖 `perception.model_path`。

2. `tests/test_v2_schemas.py`
   - `Config` 默认值应按 V2 分层结构存在。
   - `Config().control.speed`、`Config().tracker.match_distance_ratio` 等字段可访问。

3. `tests/test_v2_actuation.py`
   - `TargetTracker` 使用 Detection 框中心距离与尺寸比例确认是否同一目标。
   - `TargetTracker` 遇到短暂空检测时，不应立即让其他目标抢锁。
   - 静止抖动先用诊断测试定位根因，再决定是否替换 `AimSmoother`。
   - `FpsController` 的速度、加速度、近距离减速参数应可配置，且提高配置后输出更快。

#### Step 2：建立 V2 专用配置体系

1. 新建 `config.v2.json`。
2. 重构 `shared/config.py` 为嵌套配置。
3. 重写 `interaction/cli.py::_build_config()`：
   - 读取嵌套 JSON。
   - 缺失字段使用 dataclass 默认值。
   - CLI 参数只覆盖明确传入的字段。
4. 将 `--config` 默认值从 `config.json` 改为 `config.v2.json`。

#### Step 3：更新 V2 各层配置访问

将旧平铺访问：

```python
config.image_width
config.model_path
config.control_speed
config.tracker_iou_threshold
```

改为分层访问：

```python
config.capture.image_width
config.perception.model_path
config.control.speed
config.tracker.iou_threshold
```

#### Step 4：替换式重构目标锁定，修复多目标抢准星（详细实施计划）

##### 4.1 先删除/替换的旧机制

本步骤不做“在旧 IOU 锁定上继续叠加更多判断”的增量修改，避免多个机制同时影响目标选择。

计划先替换掉当前 `actuation/tracker.py` 中这套机制：

1. 删除 `compute_iou()` 及 `_find_iou_match()` 作为主判断路径。
2. 删除“IOU 阈值决定目标是否消失”的思路。
3. 删除 tracker 内对“框重叠程度”的依赖。
4. 保留 `TargetTracker` 这个职责类，但内部改为更简单的 Detection 框匹配逻辑。

原因：当前输入只有 YOLO `Detection`，没有稳定 track_id。判断是否同一目标时，直接使用检测框中心点距离和框尺寸变化，比 IOU 更直观、更容易调参，也更符合本阶段“锁住当前框，再锁头”的目标。

##### 4.2 新机制目标

新目标锁定只回答一个问题：**当前帧的哪个 Detection 最像上一帧锁定的 Detection？**

如果能找到，就继续锁它；找不到，才重新选择目标。

初始选择和被动切换仍复用 `select_target()`：

```text
首次 / 锁定目标确认消失 → select_target() → 锁定一个 Detection
已锁定 → 用 Detection 框相似度确认同一个框 → 继续锁定
```

##### 4.3 Detection 框匹配规则

用更简单的“中心距离 + 尺寸比例”替代 IOU：

1. 计算锁定框中心和候选框中心距离：
   - `center_distance = hypot(candidate.center - locked.center)`
2. 计算允许距离：
   - `allowed_distance = max(min_match_distance, locked_diag * match_distance_ratio)`
   - `locked_diag = hypot(locked.w, locked.h)`
3. 计算尺寸变化比例：
   - `width_ratio = candidate.w / locked.w`
   - `height_ratio = candidate.h / locked.h`
4. 候选框满足以下条件才认为是同一框：
   - `center_distance <= allowed_distance`
   - `size_ratio_min <= width_ratio <= size_ratio_max`
   - `size_ratio_min <= height_ratio <= size_ratio_max`
   - 可选：label 相同；如果 head/person 经常切换，再单独讨论，不在第一版叠加复杂逻辑。

建议配置改为：

```json
"tracker": {
  "match_distance_ratio": 0.75,
  "min_match_distance": 18.0,
  "size_ratio_min": 0.55,
  "size_ratio_max": 1.8,
  "lost_frame_grace": 2
}
```

并从计划中移除 `iou_threshold` / `center_match_threshold` 这两个容易引导回旧 IOU 思路的字段。

##### 4.4 短暂漏检处理

空检测不立即清空锁定，但也不能把旧框当成新测量。

策略：

1. 当前帧无 detections：
   - `lost_frames += 1`
   - `has_measurement_this_frame = False`
   - 未超过 `lost_frame_grace`：保留 `locked_target` 作为锁定状态，但 `update()` 返回 None 给 Actuator，避免旧 bbox 继续参与瞄点测量。
   - 超过 `lost_frame_grace`：清空锁定。
2. 当前帧有 detections：
   - 如果有锁定目标，先尝试 Detection 框匹配。
   - 匹配成功：更新 `locked_target`，`has_measurement_this_frame=True`。
   - 匹配失败：释放旧锁定，调用 `select_target()` 被动选择新目标，`switched=True`。

##### 4.5 测试先行

在 `tests/test_v2_actuation.py` 中新增/替换测试，先观察失败：

1. `test_keeps_lock_when_detection_box_moves_within_match_distance`
   - A 框小幅移动/尺寸略变。
   - 同帧出现更靠近准星的 B。
   - 期望继续返回 A。

2. `test_switches_when_detection_box_moves_beyond_match_distance`
   - A 框下一帧距离上一锁定框明显过远。
   - 期望认为 A 已消失，并被动切换。

3. `test_rejects_match_when_box_size_changes_too_much`
   - 中心很近但尺寸比例异常，认为不是同一框。
   - 防止两个重叠目标或错误框误匹配。

4. `test_short_empty_detection_gap_does_not_steal_lock_on_reacquire`
   - A 锁定后空一帧。
   - A 再次在相近位置出现，同时 B 更近。
   - 未超过 `lost_frame_grace` 时继续锁 A。

5. `test_lost_gap_expires_then_reselects_best_target`
   - 空检测超过 grace 后重新选择。

##### 4.6 与 Actuator 的衔接

`TargetTracker` 提供清晰状态，而不是让多个机制隐式叠加：

```python
tracker.locked_target
tracker.has_measurement_this_frame
tracker.switched
tracker.lost_frames
```

`Actuator.process()` 规则：

1. `selected = tracker.update(...)`
2. 如果 `tracker.switched`：重置平滑器和控制器状态。
3. 如果 `selected is None`：本帧无测量，`raw_aim = None`。
4. 如果 `selected is not None`：用当前 detection 计算 raw aim。

##### 4.7 验收标准

- 目标锁定只由一套 Detection 框匹配规则决定，不再同时受 IOU、中心 fallback、其他迟滞规则叠加影响。
- 多目标同屏时，只要原检测框仍能匹配，就不主动切到更近目标。
- 短暂漏检后，原框回到附近时继续锁定。
- 目标确认消失后才被动切换。

#### Step 5：先诊断静止目标抖动根因，再决定是否重写平滑机制（详细实施计划）

##### 5.1 原则

静止时准星抖动不能先假设一定是 Kalman 不够强，也不能直接叠加“静止吸附”。必须先确认抖动来自哪一层，否则容易出现多个机制互相抵消，最终调不动。

本步骤先做诊断，再决定删除/替换哪些机制。

##### 5.2 可能根因列表

静止目标准星抖动可能来自以下不同层：

1. **YOLO 检测框抖动**
   - 静止目标每帧 bbox 的 `x/y/w/h` 有细碎变化。
   - `compute_aim_point()` 直接依赖 bbox，因此 raw aim 抖动。

2. **目标选择抖动**
   - 多个 detection 相邻时，当前锁定框判断不稳定。
   - 表面看是准星抖，实际是 selected target 在帧间变化。

3. **瞄点偏置造成的尺寸敏感**
   - `head_bias/body_bias` 使用 `detection.h * bias`。
   - bbox 高度小幅变化会直接导致 aim_y 小幅跳动。

4. **Kalman 速度项引入残余漂移**
   - 当前 `AimSmoother` 状态为 `[x, y, vx, vy]`。
   - 对静止目标来说，检测噪声可能被估计成速度，导致输出继续漂。

5. **控制器速度状态未及时归零**
   - `FpsController` 有内部 `velocity_x/y`。
   - 即便误差变小，如果没有进入 deadzone，速度状态仍可能输出微移动。

6. **可视化误判**
   - 当前 `Visualizer` 用 `cmd.dx/dy` 反推瞄准点：`crosshair + command`。
   - 在启用控制器时，`cmd` 是控制输出，不是实际 smoothed aim；这可能把“控制箭头变化”误看成“瞄点抖动”。

##### 5.3 先补诊断，不先加机制

在正式修复前，先完善诊断输出和测试观察点：

1. `Actuator` 已有：
   - `last_raw_aim`
   - `last_smoothed_aim`

2. 计划补充/确认：
   - `last_selected` 或通过 pipeline 的 `selected` 输出当前锁定 detection。
   - tracker 状态中输出：`locked_frames`、`lost_frames`、`switched`、`has_measurement_this_frame`。
   - control 状态中可观察：当前 error、velocity、是否 deadzone。

3. 修正可视化含义：
   - 红点应显示 `last_smoothed_aim`。
   - 控制箭头单独显示 `Command(dx, dy)`。
   - 不再用 `crosshair + cmd.dx/dy` 伪装成瞄点。

##### 5.4 诊断测试/实验

先建立以下最小实验，再判断根因：

1. **固定同一 detection，不抖 bbox**
   - 连续输入完全相同的 Detection。
   - 期望 raw aim、smoothed aim、command 都稳定。
   - 如果仍抖，问题在 smoother 或 controller。

2. **固定同一目标，bbox 轻微抖动**
   - 只让 `x/y/w/h` 在 ±1~2 像素内变化。
   - 观察 raw aim 抖动量、smoothed aim 抖动量、command 输出量。
   - 用于判断是否需要替换 Kalman 或调整 aim 计算。

3. **禁用 controller，仅观察 smoothed aim**
   - `Actuator(use_controller=False)`。
   - 如果 smoothed aim 稳但真实鼠标抖，问题在 controller。

4. **启用 controller，输入稳定 smoothed aim**
   - 直接测试 `FpsController` 对小误差的输出。
   - 判断 deadzone 和 velocity reset 是否足够。

5. **多目标静止场景**
   - 两个静止 detection 同时存在。
   - 观察 selected 是否变化。
   - 如果 selected 变化，先修 tracker，不修 smoother。

##### 5.5 替换式修复候选

根据诊断结果，只选择对应修复，不叠加全部机制：

| 根因 | 处理方式 |
|------|------|
| selected target 在变 | 优先完成 Step 4，替换目标锁定机制 |
| raw aim 因 bbox 高度变化抖 | 调整 `compute_aim_point()`，减少对 h 变化的敏感性，或在 detection 级做框平滑 |
| Kalman 速度项制造漂移 | 删除当前 4 维 Kalman，替换为更简单的 EMA/稳定窗口平滑 |
| controller 小误差仍输出 | 调整 `FpsController` deadzone/reset，不改 smoother |
| 只是 Visualizer 显示错误 | 修正可视化，不改控制算法 |

##### 5.6 当前倾向方案（待诊断确认）

如果诊断确认抖动主要来自 bbox 的小幅检测噪声，优先考虑替换当前 `AimSmoother`，而不是在 Kalman 上继续叠加更多状态。

候选替代方案：

```text
输入 raw aim
  ↓
如果与上次稳定点距离 <= jitter_radius，累计 stable_frames，输出稳定点
如果超过 jitter_radius，认为目标移动，用 EMA 向新点追随
目标丢失时 hold 上次稳定点 N 帧
```

这样比 `[x,y,vx,vy]` Kalman 更容易调参，也更符合当前阶段需求：

- 静止时稳；
- 移动时跟；
- 参数少；
- 不引入速度估计漂移。

建议配置改为：

```json
"smoothing": {
  "enabled": true,
  "alpha": 0.55,
  "jitter_radius": 2.0,
  "stable_frames": 2,
  "hold_frames": 3
}
```

同时从计划中删除/替换旧的：

```text
process_noise
measurement_noise
stationary_radius
stationary_frames
```

是否真的替换 Kalman，必须等诊断实验确认。

##### 5.7 目标切换 reset

无论最终选择 Kalman 还是 EMA 稳定窗口，目标切换时都必须 reset 平滑器：

1. tracker 判断发生切换。
2. `Actuator` 调用 `smoother.reset()`。
3. 新目标第一帧瞄点直接初始化，不被旧目标状态拖拽。

##### 5.8 验收标准

- 能通过诊断区分：检测框抖、目标选择抖、平滑器漂、控制器输出抖、可视化误判。
- 只修确认的根因，不把所有候选机制全部叠加。
- 如果替换平滑器，应删除旧 Kalman 机制，避免 Kalman + EMA + 静止吸附多套机制同时影响结果。

#### Step 6：修复鼠标移动偏慢（详细实施计划）

##### 6.1 目标

当前 `FpsController` 默认速度偏保守，而且使用 `speed * 3` 作为硬编码近距离减速范围。在 ROI 尺寸不大的情况下，大多数目标都处于减速区，导致移动目标跟随慢。

本步骤目标：让控制器速度参数可解释、可调，并通过 V2 配置界面快速调参。

##### 6.2 测试先行

在 `tests/test_v2_actuation.py` 中新增测试，先观察失败：

1. `test_controller_uses_configured_near_radius_instead_of_speed_multiplier`
   - 设置 `near_radius` 为较小值。
   - 输入中等距离误差。
   - 期望不再因为 `speed * 3` 被过早减速。

2. `test_controller_higher_speed_and_acceleration_outputs_larger_step`
   - 对比低速配置和高速配置。
   - 同样误差输入下，高速配置输出 dx 更大。

3. `test_controller_deadzone_suppresses_small_stationary_error`
   - 输入小于 `deadzone` 的误差。
   - 期望输出 `(0,0)` 且速度状态 reset。

##### 6.3 控制器参数调整

修改 `actuation/control.py::FpsController`，构造参数改为：

```python
speed: float = 180.0
acceleration: float = 0.45
deadzone: float = 3.0
near_radius: float = 80.0
near_speed_scale: float = 0.35
```

其中：

- `speed`：目标速度标尺，越大越快。
- `acceleration`：速度追随系数，越大越跟手。
- `deadzone`：误差小于该值时停止输出。
- `near_radius`：进入近距离减速的半径，不再由 `speed * 3` 隐式决定。
- `near_speed_scale`：近距离保留的最低速度比例。

##### 6.4 更新速度计算公式

保留当前“方向 + 速度追随”的简单模型，不引入 V1 大量 servo 参数。

推荐逻辑：

```python
dist = hypot(error_x, error_y)
if dist < deadzone:
    reset()
    return (0, 0)

scale = 1.0
if dist < near_radius:
    ratio = dist / near_radius
    scale = near_speed_scale + (1.0 - near_speed_scale) * ratio

target_speed = speed * scale
velocity += (target_velocity - velocity) * acceleration
return round(velocity)
```

后续如果仍慢，再考虑增加 `speed_gain` 或 `max_step`，但本轮不引入，避免变成 V1 式冗余控制器。

##### 6.5 Actuator 接入

在 `actuation/targeting.py` 中创建 controller 时，使用：

```python
FpsController(
    speed=config.control.speed,
    acceleration=config.control.acceleration,
    deadzone=config.control.deadzone,
    near_radius=config.control.near_radius,
    near_speed_scale=config.control.near_speed_scale,
)
```

##### 6.6 配置界面接入

在 V2 配置界面的 Control 页暴露：

- `speed`
- `acceleration`
- `deadzone`
- `near_radius`
- `near_speed_scale`

不暴露 V1 的 `servo_kp`、`servo_kd`、`servo_curve`、`fps_brake`、`servo_output_gain` 等历史参数。

##### 6.7 验收标准

- 默认配置比当前 `speed=100/acceleration=0.3` 更跟手。
- 调大 `control.speed` 或 `control.acceleration` 后，输出变化可通过测试和可视化观察到。
- 近距离减速由 `near_radius` 明确控制，不再被 `speed * 3` 隐式放大。
- 控制器仍保持简单、可解释，不引入 V1 冗余参数。

### Commit 拆分要求

本阶段执行时按 3 个 commit 拆分，避免一次提交混入过多机制，也方便回退和单独验证：

1. **Commit 1：Step 1~3**
   - 覆盖：测试先行、V2 专用配置体系、V2 配置界面基础、各层配置访问迁移。
   - 不在此 commit 中改变目标锁定和平滑策略的核心行为。
   - 建议提交信息：`refactor(v2): 建立专用配置与精简调参入口`

2. **Commit 2：Step 4**
   - 覆盖：删除/替换旧 IOU 目标锁定机制，改为 Detection 框中心距离 + 尺寸比例匹配。
   - 不在此 commit 中修静止抖动和平滑器。
   - 建议提交信息：`refactor(v2): 用 detection 框匹配替换 IOU 目标锁定`

3. **Commit 3：Step 5~6**
   - 覆盖：先诊断静止抖动根因，再按确认结果替换/调整平滑机制；同时修正 FPS 控制器速度和近距离减速配置。
   - 如诊断发现 Step 5 不需要改平滑器，则 commit 内容只包含诊断、可视化修正和 Step 6 控制器调整。
   - 建议提交信息：`fix(v2): 诊断静止抖动并优化控制响应`

每个 commit 前都要运行对应定向测试；最终第三个 commit 后再运行 V2 相关测试集合。

### 验证方式

#### 自动化测试

```bash
python -m unittest tests.test_v2_schemas -v
python -m unittest tests.test_v2_cli -v
python -m unittest tests.test_v2_actuation -v
python -m unittest tests.test_v2_runtime -v
```

必要时运行全量：

```bash
python -m unittest discover tests -v
```

#### 手动验证

安全视频回放：

```bash
python main_v2.py --video test.mp4 --output null --visual --config config.v2.json
```

实时安全日志输出：

```bash
python main_v2.py --realtime --output log --visual --config config.v2.json
```

观察重点：

1. 多目标同屏时，白色选中框不应频繁跳目标。
2. 静止目标附近，红色/平滑瞄点不应细碎抖动。
3. 移动目标横移时，鼠标输出应明显比当前默认配置更跟手。
4. 修改 `config.v2.json` 中 `control`、`tracker`、`smoothing` 参数后，行为应立即按配置变化。

### 注意事项

1. 本补充计划只针对 `src/visual_aiming_v2/`，不再修改 V1/V1 modular 配置逻辑。
2. 根目录旧 `config.json` 暂时保留，避免破坏旧运行链路。
3. V2 默认使用 `config.v2.json`，后续 V2 稳定后再考虑替换正式配置名。
4. 先完成配置解耦，再修控制稳定性；否则调参反馈仍不可靠。
5. 实现时优先“删除旧机制并替换为单一新机制”，避免 Kalman、静止吸附、IOU、中心距离、控制 deadzone 等多套机制同时叠加导致调参不可解释。
6. 静止抖动必须先通过诊断确认根因，再选择修复路径；不能先假设是平滑器问题。
