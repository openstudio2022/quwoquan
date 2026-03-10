---
name: /design
id: design
category: Workflow
description: 设计基线（面向 L3_story，产出 Task）
---

> SDD 主流程：explore → prd → **design** → dev → commit → deploy

## Design Gate

进入 `/design` 前必须确认：

- `spec.md` 已存在且稳定
- `acceptance.yaml` 已定义
- 已明确 `L1_capability / L2_feature / L3_story`
- 已识别约束、依赖、测试策略
- 至少有 2 个方案可比较

## 执行对象

`/design` 面向 `L3_story`，并产出其 Task 执行清单。

## 产出

- `design.md`
- `tasks.md`
- metadata / codegen 基线（如有）

## `design.md` 要求

必须包含：

- 设计动因
- 上游输入评审
- 对标输入分析
- 方案对比
- 选型决策
- 关键设计决策
- TDD / ATDD 策略
- `Task` 与测试层映射
- 未来演进

## `tasks.md` 要求

必须包含：

- 当前交付任务
- 搁置任务（带规划）
- 未来演进任务

约束：

- `tasks.md` 只承载 `Task`
- 不得把任务重新建成树层级

## G1

如涉及 metadata/codegen，执行真实可用命令：

```bash
make -C quwoquan_service verify-metadata
make codegen
make codegen-app
```

## 结束输出

```text
设计基线完成：<feature-path>
L3_story: <story>
Task 数量：<N>
下一步：/dev
```
