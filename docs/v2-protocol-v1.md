# V2 层间协议 v1

**版本：** v1
**状态：** 初始版本
**对应架构：** docs/v2-architecture.md

---

## 协议 1：capture → perception

capture 完成图像获取和预处理后，输出 Frame 交给 perception。

**Frame 数据结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `image` | numpy ndarray | 预处理完毕的图像，可直接用于检测 |
| `sequence` | int | 帧序号 |
| `timestamp` | float | 帧获取时间戳 |

**约定：**
- Frame 不携带准星位置，准星默认是画面正中心
- 图像尺寸在初始化时通过配置确定，每帧保持一致

---

## 协议 2：perception → actuation

perception 完成检测后，输出 `list[Detection]` 交给 actuation。

**Detection 数据结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `x` | int | 检测框左上角 x（相对于 Frame.image 坐标系） |
| `y` | int | 检测框左上角 y |
| `w` | int | 检测框宽度 |
| `h` | int | 检测框高度 |
| `confidence` | float | 置信度 |
| `label` | str | 类别名称（如 "head"、"person"） |

**约定：**
- Detection 不携带帧上下文或准星信息
- actuation 从自身配置获取图像尺寸和准星位置

---

## 协议 3：actuation → 输出后端

actuation 完成控制计算后，输出 Command 交给输出后端。

**Command 数据结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `dx` | int | 水平相对位移 |
| `dy` | int | 垂直相对位移 |
| `mode` | str | 指令类型："relative" 有效指令，"none" 无操作 |
| `reason` | str | 原因："tracking"、"no_target"、"on_target" 等 |

**约定：**
- 输出后端只看 Command，不需要任何上游信息

---

## 协议 4：runtime ↔ 流水线各级

runtime 通过统一接口驱动流水线各级：

| 组件 | 接口 |
|------|------|
| capture | `read() → Frame \| None`、`close()` |
| perception | `detect(image) → list[Detection]` |
| actuation | `process(detections) → Command` |
| output | `apply(command)`、`close()` |

**约定：**
- `read()` 返回 None 表示数据源结束
- runtime 不关心各级内部实现，只通过上述接口交互
- TickResult（可选）：runtime 可将每帧中间结果打包用于调试，此功能设计为可开关

---

## 协议 5：interaction → runtime

interaction 组装好各层组件实例后，传给 runtime 启动运行。

```
runtime.run(
    capture    = <capture 实例>,
    perception = <perception 实例>,
    actuation  = <actuation 实例>,
    output     = <output 实例>,
)
```

**约定：**
- runtime 不关心组件怎么创建，只要求它们实现协议 4 定义的接口
