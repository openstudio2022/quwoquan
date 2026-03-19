---
name: /design
id: design
category: Workflow
description: 设计基线（面向 Journey / Scenario，落实商用方案与 plan）
---

> SDD 主流程：explore → prd → **design** → dev → commit → deploy

## Design Gate

进入 `/design` 前必须确认：

- `spec.md` 已存在且稳定
- `acceptance.yaml` 已定义
- 已明确 `L1_capability / L2_journey / L3_scenario`
- 至少有 2 个方案可比较
- 已识别约束、依赖、测试策略
- 选定方案能够覆盖 metadata/codegen、字段或模型演进、数据迁移/回填、必要时双读双写、feature flag、观测、SLO 验证与回滚
- 若涉及小趣或私密内容，权限、撤销、保留模型已冻结
- `T1~T4` 证据矩阵已形成
- `plan.yaml` 已能表达切片顺序，且遵循 `metadata -> codegen -> 业务逻辑 -> 测试`
- 若涉及助手链路：已阅读 `quwoquan_app/personal_assistant/docs/PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`，并已识别对应的 Skill / Tool / Phase / 垂类场景文档

## 执行对象

`/design` 面向 `L2_journey` / `L3_scenario`，并产出其 `plan.yaml`。

## 产出

- `design.md`
- `plan.yaml`
- 对应 `CR` 修订
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
- `plan slice` 与 `T1~T4` 证据矩阵映射
- 未来演进

若涉及助手，还必须包含：

- 对三类核心文档的引用与符合性说明
- 本次变更的真相源映射
- 是否引入 runtime 兼容逻辑，以及退出条件
- 无垂类特判、无字符串硬编码、模板资产化的落实方式

## `plan.yaml` 要求

必须包含：

- `version`
- `node`
- `derived_from`
- `slices`

约束：

- `plan.yaml` 只承载稳定实施切片
- 每个 slice 必须包含 `acceptance_refs`
- 会话 todo 不得回写到 `plan.yaml`
- 顺序必须是 `metadata -> codegen -> 业务逻辑 -> 测试`

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
L3_scenario: <scenario>
plan slices: <N>
CR: <change-request>
下一步：/dev
```
