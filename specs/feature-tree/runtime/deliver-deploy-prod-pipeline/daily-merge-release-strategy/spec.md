# L3 Story：每日合并发布策略 (`daily-merge-release-strategy`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望 `dev1.0` 承接稳定集成、`main` 承接唯一发布，所有短期开发分支通过显式 PR 晋级并自动删除，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “每日合并发布策略”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 每日合并发布策略

- **分支策略**：本地与远端长期分支只允许 `dev1.0` 与 `main`；`dev1.0` 是集成真相源，`main` 是发布真相源，短期分支仅用于显式 PR，必须使用受控前缀并在合并后自动删除。

<a id="req-002"></a>
### REQ-002 集成、晋级与回同步准入

- **PR 合入规则**：正常开发只允许 `codex/* -> dev1.0`，发布晋级只允许 `dev1.0 -> main`；`codex/* -> main`、人工 `main -> dev1.0` 与任何其他边均 fail-closed。
- **回同步规则**：promotion 成功后，系统只能以 fast-forward 将 `main` backsync 到 `dev1.0`；不得产生 merge commit、历史改写或人工直推。
- **发布来源**：Prod source 只能是可达 `main` 的精确 Git SHA；`dev1.0` push 只产生集成证据，不得触发 Prod apply。
- **PR 门禁**：`main` 的 required checks 统一由 `03/04/05` 承担，其中 `04` 是 local-gamma preflight 主门禁、`05` 是本地 self-hosted alpha/beta Android+iOS 设备矩阵。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 每日合并发布策略

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“每日合并发布策略”对应的公开行为。
- THEN `dev1.0` 是唯一长期集成主干、`main` 是唯一长期发布主干，短期 PR 只沿 `codex/* -> dev1.0 -> main` 晋级且合入后删除，第三长期分支为零。
- AND promotion 成功后只有系统 fast-forward 可执行 `main -> dev1.0` backsync，Prod source 只能是可达 `main` 的精确 SHA；其余边返回 canonical failure 且不产生伪成功事实。

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
- 影响或价值：尚缺远端 auto-delete、PR/push/schedule required checks 等价性、promotion 后系统 fast-forward backsync，以及干净 clone 全量 WIP 复现的真实回执。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
