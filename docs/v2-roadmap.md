# V2 后续优化路线图

## 阶段性总结

### 第一阶段：架构搭建（已完成 ✅）

从零搭建六层架构，实现最简可运行骨架。

| 里程碑 | 内容 |
|--------|------|
| Plan 1~3 | 六层架构（shared/capture/perception/actuation/runtime/interaction） |
| P0 | capture 层 ROI 裁切 + 调参窗口 |
| P1 | OpenCV 可视化调试窗口 |
| P2 | 瞄点选择（有头选头，无头选 person + 偏置） |
| P3 | FPS 鼠标控制（复用 main.py 的速度追随/减速/抖动） |
| P4 | 实时模式（热键激活 + 截屏 + 跳帧检测） |

**当前状态：** 基础瞄准和鼠标控制已可工作。但存在以下核心问题：
1. 目标切换时瞄准点瞬间跳变（没有切换逻辑）
2. 同一目标帧间检测框大小变化导致瞄准点抖动
3. 没有目标锁定/粘性机制

---

## 第二阶段：控制算法优化

**核心目标：** 解决瞄准点抖动和目标切换问题，让准星吸附效果平滑自然。

### 问题分析

当前瞄准点抖动有两个来源：

```
来源 1：帧间检测框尺寸变化
  Frame N:   head bbox = (100, 80, 45, 60)  → aim_y = 80 + 60*0.35 = 101
  Frame N+1: head bbox = (100, 82, 42, 55)  → aim_y = 82 + 55*0.35 = 101
  Frame N+2: head bbox = (98, 78, 50, 68)   → aim_y = 78 + 68*0.35 = 101
  ↑ 即使目标没动，检测框的抖动也会让瞄准点跳来跳去

来源 2：目标切换跳变
  Frame N:   选中目标 A (head, center=(150, 100))
  Frame N+1: 目标 B (person) 突然更近 → 切换到 B (center=(300, 250))
  ↑ 瞄准点瞬间跳 200 像素，鼠标猛甩
```

### 行业解决方案（调研总结）

经过调研 FPS 游戏瞄准辅助算法和目标追踪领域的最新实践，核心技术方案有三个层次：

**1. 瞄准点平滑（解决检测框抖动）**

使用 Kalman 滤波器对瞄准点进行帧间平滑：
- 状态向量 `[x, y, vx, vy]` — 位置 + 速度
- 新检测结果作为观测值更新状态
- 输出平滑后的位置估计，消除检测框尺寸抖动带来的瞄准点跳变
- 可同时提供短期预测（领先补偿），对移动目标提前一点

参考：[SORT 目标追踪](https://arxiv.org/html/2509.18451v1) 使用 Kalman 滤波器 + 匈牙利算法做检测-追踪关联，在 260Hz 下实现实时追踪。[Bounding Box Stabilization](https://www.researchgate.net/publication/358558079_Bounding_Box_Stabilization_for_Visual_Object_Tracking_Using_Kalman_and_FIR_Filters) 专门研究了用 Kalman 和 FIR 滤波器稳定检测框。

**2. 目标粘性 / 切换迟滞（解决目标跳变）**

参考 [Configurable Aim Assist](https://www.moddb.com/mods/stalker-anomaly/addons/configurable-aim-assist) 和 [Blood Strike 瞄准辅助](https://news.bittopup.com/news/blood-strike-aim-assist-config-pro-settings-guide-2025)：
- **Switch Hysteresis（切换迟滞）：** 当前锁定目标有额外加分，新目标必须"明显更好"才触发切换
- **Target ID 追踪：** 用 IOU（交叉比）匹配前后帧的检测框，判断"这还是同一个目标吗"
- **切换冷却期：** 切换后短时间内不允许再次切换，防止在两个目标间反复跳

**3. 平滑过渡（解决切换时的跳变）**

参考 [Sticky Aim Assist System](https://docsbot.ai/prompts/technical/sticky-aim-assist-system) 和 [USPTO 瞄准辅助专利](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12151161)：
- 切换发生时不立刻跳到新目标，而是用平滑插值过渡
- 过渡时间约 0.15 秒（Smoothness=5 的典型值）
- 过渡曲线使用 ease-in-out（先慢后快再慢），避免机械感

### 实施计划

#### P5：瞄准点 Kalman 平滑

**目标：** 消除帧间检测框抖动导致的瞄准点跳变。

**实现方式：**
- 新建 `actuation/aim_filter.py`，实现 `AimSmoother` 类
- 内部用 Kalman 滤波器维护瞄准点状态 `[x, y, vx, vy]`
- 每帧接收原始瞄准点 → 输出平滑后的瞄准点
- 目标丢失时保持最后已知位置短暂预测（hold 机制）
- 目标 ID 变化（切换）时重置滤波器

**关键参数：**
| 参数 | 说明 | 默认值 |
|------|------|--------|
| process_noise | 过程噪声（越大越跟手，越小越平滑） | 0.1 |
| measurement_noise | 观测噪声（越大越平滑，越小越跟手） | 1.0 |
| hold_frames | 目标丢失后继续预测的帧数 | 5 |

**影响范围：** actuation 层内部。新增文件，修改 Actuator。

---

#### P6：目标追踪 + 切换迟滞

**目标：** 给每个检测目标分配 ID，实现粘性锁定和切换迟滞。

**实现方式：**
- 新建 `actuation/tracker.py`，实现 `TargetTracker` 类
- 用 IOU 匹配前后帧检测框，分配稳定的 target_id
- 当前锁定目标有 hysteresis 加分（比如 0.3），新目标得分必须超过 当前目标得分 + hysteresis 才切换
- 切换冷却期：切换后 N 帧内不允许再次切换

**关键参数：**
| 参数 | 说明 | 默认值 |
|------|------|--------|
| iou_threshold | IOU 低于此值认为是不同目标 | 0.3 |
| switch_hysteresis | 切换门槛（新目标必须好多少才切换） | 0.3 |
| switch_cooldown | 切换后冷却帧数 | 10 |

**影响范围：** actuation 层内部。

---

#### P7：切换平滑过渡

**目标：** 目标切换时瞄准点不瞬间跳变，而是平滑过渡。

**实现方式：**
- 在 `AimSmoother` 中增加切换过渡逻辑
- 检测到 target_id 变化时，启动 0.15 秒过渡
- 过渡期间瞄准点从旧位置平滑插值到新位置
- 使用 ease-in-out 曲线（smoothstep）避免机械感

**影响范围：** actuation/aim_filter.py 内部增强。

---

### 执行顺序

```
P5 瞄准点 Kalman 平滑    ← 先消除帧间抖动
    ↓
P6 目标追踪 + 切换迟滞   ← 稳定目标 ID，防止不必要切换
    ↓
P7 切换平滑过渡          ← 必要切换时平滑过渡
```

三个优化逐步叠加：P5 让同一目标的瞄准点稳定，P6 让目标不乱切，P7 让必要切换也不跳变。

### 验证方式

- `--visual` 窗口：观察红色瞄准点是否稳定（P5）、是否频繁跳目标（P6）、切换时是否平滑（P7）
- `--verbose` 日志：检查 SELECT 行的 target_id 变化频率
- 实时测试：`--realtime --output mouse --visual`，实际感受吸附效果

---

## 最终目标

**准星吸附效果：** 实时截屏检测敌人位置，平滑移动鼠标使准星吸附在敌人身上。

| 感受 | 由谁决定 | 怎么调 |
|------|---------|--------|
| 反应快慢 | runtime 检测频率 | detect_fps |
| 移动平滑度 | actuation FpsController | acceleration, speed |
| 瞄准点稳定性 | actuation AimSmoother (P5) | process_noise, measurement_noise |
| 目标锁定稳定性 | actuation TargetTracker (P6) | switch_hysteresis, cooldown |
| 切换自然度 | actuation 切换过渡 (P7) | transition_time |
| 是否过冲 | actuation 减速逻辑 | decel 参数 |
| 整体延迟 | runtime 主循环频率 | 主循环 fps |

各层独立可调，通过 `--visual` 窗口实时观察效果来迭代参数。

## 执行原则

- 每个优化项独立完成、独立测试、独立提交
- 修改前先用 `--verbose` 日志确认问题，修改后用 `--visual` 窗口验证效果
- 遵守架构边界：每个优化只影响对应的层，不跨层修改
- 所有新增算法都在 actuation 层内部，不改变层间协议
