# V2 后续优化路线图

## 当前状态

六层架构已搭建完毕，基础流水线可端到端运行，逐帧诊断日志和 capture 层 ROI 裁切已完成。

**已完成：**
- ✅ Plan 1~3：六层架构搭建
- ✅ P0：capture 层 ROI 裁切 + 调参窗口
- ✅ `--verbose` 逐帧诊断日志

---

## P1：可视化调试窗口（实时流水线可视化）

**问题：** 运行流水线时只有终端文字日志，无法直观看到检测效果和控制方向。后续的瞄点选择和鼠标控制都需要可视化才能有效调试。

**目标：** 在流水线运行时打开 OpenCV 窗口，每帧画面上实时叠加显示检测结果和控制信息。

**窗口设计：**
```
┌──────────────────────────────────────────────────┐
│                                                    │
│    [绿色框] 检测到的目标 (head)                      │
│    [黄色框] 检测到的目标 (person)                     │
│    [红色圆点] 瞄准点                                 │
│    [蓝色十字] 准星位置                               │
│    [品红箭头] 控制方向 (dx, dy)                      │
│                                                    │
├──────────────────────────────────────────────────┤
│  Frame: 42/5400 | FPS: 95.2 | Det: 2 | 8.3ms     │  ← OSD 信息栏
└──────────────────────────────────────────────────┘
```

**绘制元素：**

| 元素 | 颜色 | 说明 |
|------|------|------|
| 检测框 (head) | 绿色 | 绘制 bbox + 标签 + 置信度 |
| 检测框 (person) | 黄色 | 同上，颜色区分类别 |
| 选中目标框 | 白色加粗 | 被 actuation 选中的目标，加粗边框突出 |
| 瞄准点 | 红色圆点 | actuation 计算出的瞄准位置 |
| 准星 | 蓝色十字线 | 画面中心 + 偏移 |
| 控制箭头 | 品红色 | 从准星指向瞄准点，长度按 dx/dy 缩放 |
| OSD 信息 | 白色文字 | 帧号、FPS、检测数量、管道延迟 |

**操作按键：**

| 键 | 功能 |
|---|---|
| Space | 暂停/继续播放 |
| Q / ESC | 退出 |

**CLI 入口：**
```
python main_v2.py --video test.mp4 --visual
python main_v2.py --video test.mp4 --visual --verbose   ← 同时看画面和终端日志
```

**修改/新增文件：**

| 文件 | 操作 | 内容 |
|------|------|------|
| `interaction/visualizer.py` | 新建 | OpenCV 可视化渲染器（接收 TickResult，绘制叠加层） |
| `runtime/pipeline.py` | 修改 | tick() 返回的 TickResult 需要携带 selected 目标信息 |
| `interaction/cli.py` | 修改 | 添加 `--visual` 参数，创建可视化观察者 |
| `runtime/runner.py` | 修改 | 支持可选的帧回调（每帧通知可视化器） |

**架构边界检查：**
- 可视化渲染 → interaction 层（对接用户）✓
- runner 通过回调通知，不直接依赖可视化实现 ✓
- capture / perception / actuation 不需要任何修改 ✓

**与 P0 调参窗口的区别：**
- P0 调参窗口：静态帧预览，手动切帧，调整参数
- P1 可视化窗口：流水线运行时实时播放，展示检测和控制效果

---

## P2：瞄点选择策略 — 有头选头，无头选 person

**问题：** actuation 当前只按距离选最近目标，不区分 head 和 person 类别。同时瞄准点直接使用 detection center，对 person 框来说瞄的是躯干中心。

**目标：** 合并原 P1（类别偏好）和 P2（瞄点偏置）为一个完整的瞄点策略。

**选择规则：**
```
1. 优先选 head（距离准星最近的 head）
2. 没有 head 时选 person（距离准星最近的 person）
3. head 的瞄准点 = 检测框中心偏上（head_bias，默认 0.35）
4. person 的瞄准点 = 检测框顶部偏下（body_bias，默认 0.25），估算头部位置
```

**修改/新增文件：**

| 文件 | 操作 | 内容 |
|------|------|------|
| `actuation/targeting.py` | 修改 | select 逻辑改为有头选头；compute_error 加偏置 |
| `shared/config.py` | 修改 | 添加 head_bias / body_bias / head_label / person_label |
| `tests/test_v2_actuation.py` | 修改 | 添加类别选择和偏置的测试用例 |

**架构边界检查：**
- 目标选择 + 瞄点偏置 → actuation 层内部 ✓
- 偏置参数 → shared/config.py ✓
- 其他层不需要修改 ✓

**验证方式：**
- 单元测试：有 head 和 person 同时存在时优先选 head
- `--visual` 窗口：确认红色瞄准点在 head 框的偏上位置，而不是 center

---

## P3：鼠标控制逻辑 — 直接复用已有实现

**问题：** actuation 当前直接输出原始 dx/dy 误差作为 Command，没有速度模型。如果直接用这个值移动鼠标，会出现瞬间跳变、没有惯性、没有减速。

**方案：** 直接复用 `C:\Users\Nuwanda\Desktop\main.py` 中的 MouseController 逻辑，移植到 actuation 层。不重新设计控制算法。

**复用内容（来自 main.py 的 MouseController）：**
```python
def move_mouse_fps_style(self, target_x, target_y, speed):
    # 1. 计算当前鼠标到目标的距离和方向
    dx = target_x - current_x
    dy = target_y - current_y
    dist = distance(0, 0, dx, dy)

    # 2. 方向加微扰（模拟人手抖动）
    target_angle = math.atan2(dy, dx)
    angle_deviation = random.uniform(-0.3, 0.3) * deviation_factor
    perturbed_angle = target_angle + angle_deviation

    # 3. 速度追随（加速度平滑）
    target_vel_x = math.cos(perturbed_angle) * speed
    self.velocity_x += (target_vel_x - self.velocity_x) * self.acceleration

    # 4. 近距离减速（防止过冲）
    if dist < speed * 3:
        decel_factor = max(0.1, dist / (speed * 3))
        self.velocity_x *= decel_factor

    # 5. 加微抖动后移动鼠标
    self.set_mouse_position(jx, jy)
```

**移植方式：**
- 将 `move_mouse_fps_style()` 的核心逻辑封装为 `actuation/control.py` 中的 `FpsController` 类
- 保留原始的速度追随、减速、抖动逻辑，不做修改
- `Actuator.process()` 内部调用 `FpsController` 将原始误差转化为平滑移动量
- 真实鼠标输出通过 `WinMouseOutput`（使用 `SetCursorPos`，与原文件一致）

**修改/新增文件：**

| 文件 | 操作 | 内容 |
|------|------|------|
| `actuation/control.py` | 新建 | FpsController — 直接移植 main.py 的 move_mouse_fps_style 逻辑 |
| `actuation/targeting.py` | 修改 | Actuator 内部使用 FpsController |
| `actuation/outputs.py` | 修改 | 新增 WinMouseOutput（SetCursorPos，需安全开关） |
| `shared/config.py` | 修改 | 添加 speed / acceleration / jitter_intensity 参数 |
| `tests/test_v2_actuation.py` | 修改 | FpsController 单元测试 |

**架构边界检查：**
- 速度控制器 → actuation 层内部 ✓
- 鼠标输出 → actuation/outputs.py（OutputPort 实现）✓
- 其他层不需要修改 ✓

**验证方式：**
- 单元测试：验证减速、死区、速度上限行为
- `--visual` 窗口：观察控制箭头是否平滑、是否有减速效果
- 真实鼠标测试：`--output mouse`（需安全确认）

---

## 执行顺序

```
P1 可视化调试窗口    ← 先做，后续所有优化都靠它验证
    ↓
P2 瞄点选择策略      ← 有头选头，无头选 body + 偏置
    ↓
P3 鼠标控制逻辑      ← FPS 风格速度模型 + 真实鼠标输出
```

P1 是基础设施，P2 和 P3 都需要它来调试。

## 执行原则

- 每个优化项独立完成、独立测试、独立提交
- 修改前先用 `--verbose` 日志确认问题，修改后用 `--visual` 窗口验证效果
- 遵守架构边界：每个优化只影响对应的层，不跨层修改
