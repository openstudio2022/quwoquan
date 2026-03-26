---
name: /baseline
id: baseline
category: Workflow
description: 规格与设计二合一基线（仅限需求明确且方案已收敛）
---

> SDD 快捷链路：explore → **baseline** → dev → commit → deploy
> 标准链路仍然是：explore → prd → design → dev → commit → deploy

## Baseline Gate

进入 `/baseline` 前必须同时确认：

- `/explore` 已完成，且已明确 `L1_capability / L2_journey / L3_scenario`
- `/prd` 的准入条件全部满足
- 需求边界、验收、商用约束已经足够稳定，不需要再单独经历一次规格冻结回合
- 方案已经明显收敛到现有模式或单一可行路径，不存在需要拆开评审的重大架构分叉
- 已能明确 metadata/codegen、字段或模型演进、迁移/回填、feature flag、观测、SLO 验证与回滚方案
- `T1~T4` 证据矩阵已形成
- `plan.yaml` 已能表达切片顺序，且遵循 `metadata -> codegen -> 业务逻辑 -> 测试`
- 若涉及助手链路：已阅读 `quwoquan_app/personal_assistant/docs/PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`，并明确本次需求不会通过 runtime 垂类特判或字符串硬编码落地

任一未满足：

```text
GATE_BLOCK（请退回标准链路：/prd → /design）
```

## 适用边界

适用：

- 需求非常明确，规格与设计可以在同一轮完成冻结
- 主要沿用现有架构模式，只做有限增量扩展
- 对标、权限、生命周期、灰度与回滚都已可直接落盘

不适用：

- 仍有明显方案分歧或需要多轮权衡
- 牵涉大范围架构调整、跨域改造或高风险迁移
- 规格尚未稳定，仍需先单独收口 `spec.md` / `acceptance.yaml`

## 执行对象

`/baseline` 在同一轮中完成 `L2_journey` / `L3_scenario` 的规格冻结、设计冻结与实施切片规划。

## 产出

- `spec.md`
- `acceptance.yaml`
- `design.md`
- `plan.yaml`
- `specs/changelog/CR-*.yaml`
- metadata / codegen 基线（如有）
- 商用基线：`SLO/KPI`、权限边界、生命周期、覆盖矩阵、迁移灰度回滚

## 执行顺序

固定顺序：

```text
1. 冻结 spec.md + acceptance.yaml + CR
2. 冻结 design.md + plan.yaml
3. 执行 metadata / codegen 基线化
4. 输出可直接进入 /dev 的 slices 与证据矩阵
```

若在第 2 步发现方案并未收敛：

```text
停止 baseline，拆回 /prd → /design
```

## `spec.md` 与 `acceptance.yaml`

要求与 `/prd` 一致，必须完整覆盖：

- 背景与动机、目标用户、功能范围、Out of Scope
- 约束、对标输入与吸收结论、角色分工
- 既有 Story 覆盖矩阵、数据生命周期合同、权限与分享边界
- 非功能目标、迁移灰度与回滚要求、验收重点
- `journey_acceptance` / `scenario_acceptance` 到 `T1~T4` 的映射

## `design.md` 与 `plan.yaml`

要求与 `/design` 一致，必须完整覆盖：

- 上游规格评审
- 方案对比与选型结论
- metadata/codegen 方案
- 字段演进、迁移/回填、必要时双读双写方案
- feature flag、观测、SLO 验证与回滚方案
- `T1~T4` 证据矩阵
- `plan slices`

## G0 + G1

如涉及 metadata/codegen，执行真实可用命令：

```bash
make -C quwoquan_service verify-metadata
make codegen
make codegen-app
```

## 结束输出

```text
规格与设计基线完成：<feature-path>
L1: <capability>
L2: <journey>
L3: <scenario>
plan slices: <N>
CR: <change-request>
下一步：/dev
```
