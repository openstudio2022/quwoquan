---
name: /design
id: design
category: Workflow
description: 设计基线（面向 L3_story，落实商用方案与任务）
---

> SDD 主流程：explore → prd → **design** → dev → commit → deploy

## Design Gate

进入 `/design` 前必须确认：

- `spec.md` 已存在且稳定
- `acceptance.yaml` 已定义
- 已明确 `L1_capability / L2_feature / L3_story`
- 至少有 2 个方案可比较
- 已识别约束、依赖、测试策略
- 选定方案能够覆盖 metadata/codegen、字段或模型演进、数据迁移/回填、必要时双读双写、feature flag、观测、SLO 验证与回滚
- 若涉及小趣或私密内容，权限、撤销、保留模型已冻结
- `T1~T4` 证据矩阵已形成
- `tasks.md` 顺序明确，且遵循 `metadata -> codegen -> 业务逻辑 -> 测试`

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
- metadata/codegen 方案
- 字段演进、迁移/回填、必要时双读双写方案
- feature flag、观测、SLO 验证与回滚方案
- TDD / ATDD 策略
- `Task` 与 `T1~T4` 证据矩阵映射
- 未来演进

## `tasks.md` 要求

必须包含：

- 当前交付任务
- 搁置任务（带规划）
- 未来演进任务

约束：

- `tasks.md` 只承载 `Task`
- 顺序必须是 `metadata -> codegen -> 业务逻辑 -> 测试`
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
