# L3 Story：每日合并发布策略 (`daily-merge-release-strategy`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望支持 `dev1.0` 分支开发与 trunk development，但进入 `main` 统一走显式 PR，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “每日合并发布策略”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 每日合并发布策略

- **分支策略**：支持 `dev1.0` 分支开发与 trunk development，但进入 `main` 统一走显式 PR。

<a id="req-002"></a>
### REQ-002 dev1.0 开发分支与 main 显式 PR 准入

- **分支策略**：支持 `dev1.0` 分支开发与 trunk development，但进入 `main` 统一走显式 PR。
- **PR 合入规则**：`main` 的 required checks 统一由 `03/04/05` 承担，其中 `04` 是 local-gamma preflight 主门禁、`05` 是本地 self-hosted alpha/beta Android+iOS 设备矩阵。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 每日合并发布策略

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“每日合并发布策略”对应的公开行为。
- THEN **分支策略**：支持 `dev1.0` 分支开发与 trunk development，但进入 `main` 统一走显式 PR。
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
- 影响或价值：尚缺少能够证明“每日合并发布策略”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
