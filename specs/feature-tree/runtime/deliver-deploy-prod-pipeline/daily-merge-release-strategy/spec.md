# L3 Story：每日合并发布策略 (`daily-merge-release-strategy`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望 `main` 成为唯一长期发布主干，所有短期迁移分支通过显式 PR 合入并自动删除，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “每日合并发布策略”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 每日合并发布策略

- **分支策略**：`main` 是唯一长期、本地与远端发布分支；短期分支仅用于显式 PR，必须使用受控前缀并在合并后自动删除。

<a id="req-002"></a>
### REQ-002 main 单主干与短期 PR 准入

- **分支策略**：禁止 `dev1.0` 或任何第二长期分支成为开发、发布或恢复真相源；短期 PR 分支必须从最新 `main` 创建，合入前证明干净 clone 可复现，合并后自动删除。
- **退役策略**：退役分支必须先创建只读 archive tag 与 Git bundle，证明全部有效 WIP 已进入 `main` 后再删除本地和远端 ref；archive 仅用于审计，不得重新成为运行分支。
- **PR 合入规则**：`main` 的 required checks 统一由 `03/04/05` 承担，其中 `04` 是 local-gamma preflight 主门禁、`05` 是本地 self-hosted alpha/beta Android+iOS 设备矩阵。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 每日合并发布策略

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“每日合并发布策略”对应的公开行为。
- THEN `main` 是唯一长期发布主干，短期 PR 分支使用受控前缀、合入后删除，退役分支只有不可变 archive 证据而没有活动 ref。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`deliver-deploy-prod-pipeline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 每日合并发布策略 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺远端仓库 auto-delete 配置、`dev1.0` archive tag/bundle、WIP 干净 clone 复现和本地/远端 ref 删除的真实回执。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
