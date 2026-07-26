# L3 Story：可靠异步任务渠道 (`reliable-async-task-channel`)

> 所属能力：[`runtime-messaging`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望同一 `dedupeKey` 的 pending 任务可合并，并顺延 `startAt`，但不得超过 `maxDelayUntil`，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “可靠异步任务渠道”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 可靠异步任务渠道

- 同一 `dedupeKey` 的 pending 任务可合并，并顺延 `startAt`，但不得超过 `maxDelayUntil`。

<a id="req-002"></a>
### REQ-002 业务数据变更与任务请求必须同事务提交

- 业务数据变更与任务请求必须同事务提交。
- 同一 `dedupeKey` 的 pending 任务可合并，并顺延 `startAt`，但不得超过 `maxDelayUntil`。
- worker 必须重新读取数据库最新状态，payload 只能携带版本提示。
- 任务结果与 `notification_outbox` 必须同事务提交。
- ACK 只能发生在结果事务提交之后；失败必须 retry 或进入 DLQ。
- 通知 fanout 必须可恢复，recipient 级 delivered/failed 去重账本保证部分失败只重试失败目标。
- 任务、模块、部署包、保留策略与限流策略必须通过 catalog 版本化治理，启动时不兼容即 fail-fast。
- onebox 与拆分 worker package 必须通过 `env + domain + module + shardId` 租约安全并存。
- 事务性任务声明入口，业务服务不得直接写集合或直接 enqueue。
- 一次性实现所有领域的业务 worker；未完整接入的 domain 必须在 catalog/config 中显式声明禁用或延期。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 可靠异步任务渠道

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“可靠异步任务渠道”对应的公开行为。
- THEN 同一 `dedupeKey` 的 pending 任务可合并，并顺延 `startAt`，但不得超过 `maxDelayUntil`。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`runtime-messaging`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 可靠异步任务渠道主路径尚未形成直接测试证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：`reliable-async-task-channel` 提供公共可靠异步任务通道，用于承载必须最终完成的后台同步、投影、聚合、fanout 和通知任务。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
