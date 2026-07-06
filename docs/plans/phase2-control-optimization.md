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
