# V2 项目文档

## 设计文档（docs/design/）

| 文档 | 内容 |
|------|------|
| [architecture.md](design/architecture.md) | 六层架构设计（interaction / runtime / capture / perception / actuation / shared） |
| [protocol-v1.md](design/protocol-v1.md) | 层间协议 v1（Frame / Detection / Command + 四个 Port 接口） |
| [roadmap.md](design/roadmap.md) | 优化路线图（阶段总结 + 后续方向 + 最终目标） |

## 实施计划（docs/plans/）

### 第一阶段：架构搭建（已完成 ✅）

| 文档 | 内容 |
|------|------|
| [phase1-plan1-shared.md](plans/phase1-plan1-shared.md) | shared 共享模型层（schemas + ports + config） |
| [phase1-plan2-pipeline-stages.md](plans/phase1-plan2-pipeline-stages.md) | 流水线三级（capture + perception + actuation） |
| [phase1-plan3-runtime-interaction.md](plans/phase1-plan3-runtime-interaction.md) | 编排 + 交互 + 入口（runtime + interaction + main_v2.py） |

### 第二阶段：控制算法优化（进行中）

| 文档 | 内容 |
|------|------|
| [phase2-control-optimization.md](plans/phase2-control-optimization.md) | P5 Kalman 平滑 + P6 目标追踪 + P7 切换过渡 |
