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

## P6：目标追踪 + 切换迟滞

### 目标

给检测目标分配稳定的 ID，防止在多目标间不必要地切换。

### 原理

**IOU 匹配：** 计算前一帧选中目标的 bbox 与当前帧每个检测框的交叉比（Intersection over Union）。IOU 最高且超过阈值的认为是"同一个目标"。

```
帧 N:   选中目标 bbox = (100, 80, 45, 60)
帧 N+1: 检测框 A = (102, 82, 43, 58)  IOU = 0.85 → 同一个目标 ✓
         检测框 B = (300, 200, 50, 70)  IOU = 0.00 → 不同目标
```

**切换迟滞：** 即使新目标距离更近，也不立刻切换。新目标必须"好很多"才触发。

```
当前锁定目标 A: 距离准星 80px
新候选目标 B:   距离准星 60px
hysteresis = 30px

切换条件: B 的距离 < A 的距离 - hysteresis
60 < 80 - 30 = 50?  → 否，不切换，继续瞄 A

如果 B 距离 = 40px:
40 < 50?  → 是，切换到 B
```

### 实现

新建 `actuation/tracker.py`：

```python
class TargetTracker:
    """目标追踪器：IOU 匹配 + 切换迟滞。"""

    def __init__(self, iou_threshold=0.3, switch_hysteresis=30.0, switch_cooldown=10):
        self.locked_target: Detection | None = None  # 当前锁定目标
        self.locked_frames = 0                       # 已锁定帧数
        self.cooldown_remaining = 0                  # 切换冷却计数

    def update(self, detections, crosshair, head_label, person_label) -> Detection | None:
        """输入检测结果，输出应该瞄准的目标（带粘性）。"""
        if not detections:
            self.locked_target = None
            return None

        best = select_target(detections, crosshair, head_label, person_label)

        # 没有锁定目标 → 直接锁定
        if self.locked_target is None:
            self.locked_target = best
            return best

        # 在当前帧找到与锁定目标 IOU 最高的匹配
        matched = self._find_iou_match(detections)

        if matched is not None:
            # 锁定目标还在 → 继续瞄它（除非新目标好很多）
            if self._should_switch(matched, best, crosshair):
                self.locked_target = best
                self.cooldown_remaining = self.switch_cooldown
                return best
            self.locked_target = matched  # 更新 bbox（位置可能变了）
            return matched
        else:
            # 锁定目标丢了 → 切换到最佳目标
            self.locked_target = best
            return best

    def _find_iou_match(self, detections) -> Detection | None:
        """在当前帧检测中找到与锁定目标 IOU 最高的。"""

    def _should_switch(self, current_match, new_best, crosshair) -> bool:
        """判断是否应该从当前目标切换到新目标。"""

    def _compute_iou(self, a: Detection, b: Detection) -> float:
        """计算两个检测框的 IOU。"""
```

修改 `Actuator.process()`，在 `select_target()` 之前插入 tracker：

```python
def process(self, detections):
    # P6: 目标追踪 + 切换迟滞
    selected = self.tracker.update(detections, self.crosshair, ...)  # ← 替代 select_target()

    aim_point = compute_aim_point(selected, ...)
    aim_point = self.smoother.smooth(aim_point)  # P5
    error = compute_error(aim_point, self.crosshair)
    ...
```

### 配置参数

```python
# shared/config.py 新增
tracker_iou_threshold: float = 0.3      # IOU 低于此值认为目标丢失
tracker_switch_hysteresis: float = 30.0  # 切换门槛（像素距离差）
tracker_switch_cooldown: int = 10        # 切换后冷却帧数
```

### 测试用例

```python
def test_tracker_keeps_same_target_with_iou():
    """高 IOU 匹配时应该保持锁定同一目标。"""

def test_tracker_does_not_switch_without_significant_advantage():
    """新目标略近不应触发切换。"""

def test_tracker_switches_when_much_better():
    """新目标明显更近时应触发切换。"""

def test_tracker_switches_when_target_lost():
    """锁定目标从检测中消失时应切换到新目标。"""

def test_tracker_cooldown_prevents_rapid_switching():
    """切换冷却期内不应再次切换。"""

def test_iou_computation():
    """IOU 计算的正确性。"""
```

### 验证

- `--visual`：观察选中目标框（白色加粗）是否稳定，不在多个目标间跳
- `--verbose`：检查 SELECT 行的目标是否每帧一致

---

## P7：切换平滑过渡

### 目标

当 P6 决定切换目标时，瞄准点不瞬间跳到新位置，而是平滑过渡。

### 原理

切换发生时，AimSmoother 不重置，而是启动一个过渡期：

```
帧 N:   瞄准目标 A, aim = (150, 100)
帧 N+1: 切换到目标 B, 新 aim = (300, 200)

不用过渡（当前行为）：
  帧 N+1: 输出 (300, 200) ← 瞬间跳 200px

用过渡（P7）：
  帧 N+1: 输出 (165, 110)   ← 10% 过渡
  帧 N+2: 输出 (195, 130)   ← 30% 过渡
  帧 N+3: 输出 (240, 160)   ← 60% 过渡
  帧 N+4: 输出 (280, 185)   ← 85% 过渡
  帧 N+5: 输出 (300, 200)   ← 100% 过渡完成
```

过渡曲线用 smoothstep（先慢后快再慢）：

```python
def smoothstep(t):
    t = max(0, min(1, t))
    return t * t * (3 - 2 * t)
```

### 实现

在 `AimSmoother` 中增加过渡逻辑：

```python
class AimSmoother:
    def __init__(self, ..., transition_frames=8):
        self._transition_from = None   # 过渡起点
        self._transition_to = None     # 过渡终点
        self._transition_progress = 0  # 0~transition_frames
        self._transition_frames = transition_frames

    def start_transition(self, from_point, to_point):
        """P6 触发切换时调用。"""
        self._transition_from = from_point
        self._transition_to = to_point
        self._transition_progress = 0

    def smooth(self, raw_point):
        if self._transition_from is not None:
            # 过渡期间：插值
            ...
        # 正常 Kalman 平滑
        ...
```

### 配置参数

```python
# shared/config.py 新增
smooth_transition_frames: int = 8   # 切换过渡帧数（约 0.15 秒 @ 60fps）
```

### 测试用例

```python
def test_transition_interpolates_smoothly():
    """切换过渡应该从旧位置平滑移到新位置。"""
    smoother = AimSmoother(transition_frames=5)
    smoother.smooth((100, 100))
    smoother.start_transition((100, 100), (200, 200))
    results = [smoother.smooth((200, 200)) for _ in range(5)]
    # results 应该从 (100,100) 附近逐步逼近 (200,200)
    # 且中间值不超出 (100,100)-(200,200) 范围

def test_transition_uses_smoothstep_curve():
    """过渡曲线应该是先慢后快再慢。"""
```

### 验证

- `--visual`：切换目标时观察瞄准点是否平滑移动，而非瞬间跳变
- 对比：关闭过渡（`smooth_transition_frames=0`），看差异

---

## 执行顺序

```
P5 瞄准点 Kalman 平滑
    ↓  commit
P6 目标追踪 + 切换迟滞
    ↓  commit
P7 切换平滑过渡
    ↓  commit
```

三个按顺序做，每个独立 commit。P5 先让单目标稳定，P6 再让多目标不乱切，P7 最后让切换也平滑。

## 后续方向（P5~P7 完成后）

| 方向 | 内容 |
|------|------|
| 调参系统 | 给所有新参数加到 OpenCV 调参窗口，运行时拖滑块实时调 |
| 数据分析 | JSONL 日志 + 分析报告（跟踪稳定性、切换频率、抖动量） |
| 武器适配 | 不同武器不同参数组（狙击高平滑、冲锋低平滑） |
| 模型升级 | 训练 YOLOv8s 或导出 TensorRT |
| 截屏优化 | 后台线程截屏或 DXcam 库 |
