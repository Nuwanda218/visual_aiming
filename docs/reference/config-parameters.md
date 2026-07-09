# V2 配置参数手册

所有参数保存在 `config.v2.json`，按架构层分组。可以用 `--tune config` 调参窗口实时调整，也可以直接编辑配置文件。

## 速查表：遇到问题调哪个参数

| 问题 | 解决方案 |
|------|---------|
| 准星越过目标（冲过头） | 增大 `control.near_radius`，减小 `control.near_speed_scale` |
| 鼠标跟不上移动目标 | 增大 `control.speed` |
| 瞄准点停在目标上时抖动/微振 | 增大 `control.deadzone`，增大 `smoothing.jitter_radius` |
| 目标锁定容易丢失（跟丢） | 增大 `tracker.match_distance_ratio`，增大 `tracker.lost_frame_grace` |
| 目标锁在多个敌人间跳来跳去 | 减小 `tracker.match_distance_ratio` |
| 误检太多（凭空出现的目标） | 增大 `perception.confidence` |
| 鼠标感觉迟钝/不跟手 | 增大 `control.acceleration`，增大 `runtime.detect_fps` |
| head 框瞄准点太高（打头以上） | 增大 `targeting.head_bias` |
| person 框瞄准点太高 | 增大 `targeting.body_bias` |
| 同一目标有多个重叠检测框 | 减小 `perception.iou` |
| 静止时瞄准点仍微微抖动 | 减小 `smoothing.alpha`，增大 `smoothing.jitter_radius` |

---

## capture — 图像获取层

控制从屏幕截取画面的范围和准星位置。

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| `image_width` | int | 410 | 100-1000 | ROI 裁切宽度（像素）。越大覆盖越广但 YOLO 推理越慢 |
| `image_height` | int | 315 | 100-1000 | ROI 裁切高度。建议保持 4:3 或 16:9 比例 |
| `crosshair_offset_x` | int | 0 | -200~200 | 准星水平偏移，正值=右移，负值=左移 |
| `crosshair_offset_y` | int | 0 | -200~200 | 准星垂直偏移，正值=下移，负值=上移 |

使用 `--tune capture` 可以在全屏视频上拖动滑块可视化调整这些参数。

---

## perception — 视觉感知层（YOLO 检测器）

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| `model_path` | str | `models/best.pt` | - | YOLO 模型路径。换成 yolov8s.pt 精度更高但推理更慢 |
| `confidence` | float | 0.5 | 0.05-0.95 | 置信度阈值。低于此值的检测框被丢弃。误检多就调高 |
| `iou` | float | 0.45 | 0.1-0.9 | NMS 重叠框合并阈值。同一目标出现多个框就调低 |
| `device` | str | `auto` | - | 推理设备。`auto`=优先 CUDA，`cpu`=强制 CPU，`cuda:0`=指定 GPU |

---

## actuation → targeting — 瞄点偏置

决定对不同类别检测框从哪里取瞄准点。

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| `head_label` | str | `head` | - | head 的类别标签名，需与模型训练时一致 |
| `person_label` | str | `person` | - | person 的类别标签名 |
| `head_bias` | float | 0.35 | 0-1.0 | head 框的垂直瞄准偏置。0=框顶部，0.5=框中心。瞄高了就调大 |
| `body_bias` | float | 0.25 | 0-1.0 | person 框的垂直瞄准偏置。0=框顶部。瞄高了就调大 |

---

## actuation → tracker — 目标锁定

通过比较前后帧检测框的中心距离和大小比来判断是不是同一个人。
**锁定逻辑**：一旦锁定了某个目标，只要它还在就不会主动切换到更近的新目标。只有当锁定目标消失时才被动切换。

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| `match_distance_ratio` | float | 0.75 | 0.3-2.0 | 两帧间目标中心允许的最大移动距离 / 框对角线长度。低于此比认为同一目标。抢准星（锁不住）就调大 |
| `min_match_distance` | float | 18.0 | 1-100 | 中心移动小于此像素值直接判定为同一目标 |
| `size_ratio_min` | float | 0.55 | 0.2-1.0 | 新框面积 / 旧框面积的下限。低于此值认为不同目标 |
| `size_ratio_max` | float | 1.8 | 1.0-3.0 | 新框面积 / 旧框面积的上限。高于此值认为不同目标 |
| `lost_frame_grace` | int | 2 | 0-10 | 目标短暂消失多少帧内仍保持锁定。跟丢太快就调大 |

---

## actuation → smoothing — 瞄准点平滑

使用 EMA（指数移动平均）滤波器消除帧间检测框尺寸变化带来的瞄准点抖动。

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| `enabled` | bool | true | - | 是否启用平滑。关闭后瞄准点使用原始值 |
| `alpha` | float | 0.55 | 0.05-0.95 | EMA 系数：0=完全不跟手（极平滑），1=完全跟手（无平滑）。静止瞄准点抖动就调小，移动目标跟不上就调大 |
| `jitter_radius` | float | 2.0 | 0-20 | 瞄准点变化小于此值视为抖动并忽略。静止抖动就调大 |
| `stable_frames` | int | 2 | 1-10 | 连续多少帧变化在抖动半径内才认为目标静止，之后强化平滑 |
| `hold_frames` | int | 3 | 0-20 | 目标丢失后继续用最后位置预测的帧数 |

---

## actuation → control — 鼠标速度控制

FPS 风格的鼠标速度模型：距离越远移动越快，越近越慢，靠近目标时自动减速以防过冲。

**控制流程：**
```
瞄准误差（像素）
    ↓
如果误差 < deadzone → 停止不动
    ↓
目标速度 = 误差 × 速度系数（上限为 speed）
如果误差 < near_radius → 目标速度 *= near_speed_scale（减速）
    ↓
速度平滑追随目标速度（acceleration 系数）
    ↓
近距离额外减速刹车
    ↓
× output_scale（游戏灵敏度匹配）
    ↓
SendInput 鼠标移动
```

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| `speed` | float | 180.0 | 20-500 | 基础移动速度。跟不上移动目标就调大 |
| `acceleration` | float | 0.45 | 0.05-0.95 | 速度追随系数。越小越平滑（感觉迟钝），越大越跟手（可能有微振） |
| `deadzone` | float | 3.0 | 0-15 | 误差死区。瞄准点与准星距离小于此值不再移动。微振就调大 |
| `near_radius` | float | 80.0 | 10-300 | 进入此距离后开始减速。**过冲就调大**（让减速更早开始） |
| `near_speed_scale` | float | 0.35 | 0.01-1.0 | 近距离速度倍率。越小越稳。**过冲就调小**（建议试 0.05~0.10） |
| `output_scale` | float | 1.0 | 0.1-3.0 | 输出倍率。用于匹配不同游戏的鼠标灵敏度。可用校准工具测量 |

### 如何校准 output_scale

```powershell
python scripts/test_mouse_calibrate.py        # 发送 dx=100，3 秒后执行
python scripts/test_mouse_calibrate.py 200     # 自定义 dx 值
```

1. 进游戏训练场，准星对准一个参考点
2. Alt-Tab 运行脚本，切回游戏
3. 3 秒倒计时后鼠标自动移动 100 单位
4. 目测准星在游戏画面中偏移了多少像素
5. **output_scale = 游戏像素偏移量 / 100**

例如偏移了 79 像素，output_scale = 0.79。如果用 200 测试偏移了 158 像素，也是 0.79。

---

## runtime — 运行编排层

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| `detect_fps` | float | 30.0 | 5-120 | YOLO 每秒检测次数。越高反应越快但 GPU 占用越高。30 是推荐平衡值 |

---

## output — 输出层

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `backend` | str | `null` | `null`=不输出，`log`=内存记录指令，`mouse`=SendInput 真实鼠标移动 |

`backend` 通过 CLI `--output` 参数设置，不需要在配置文件中手动修改。
