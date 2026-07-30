# L2 Business Capability：运行时事件存储 (`runtime-eventstore`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

MongoDB events 集合持久化领域事件（aggregate_id, event_type, payload, timestamp, trace_id）。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“runtime-eventstore”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：MongoDB events 集合持久化领域事件（aggregate_id, event_type, payload, timestamp, trace_id）。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`event-persist-and-publish`](./event-persist-and-publish/spec.md)：事件必须包含 OTEL traceID。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime eventstore 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“MongoDB events 集合持久化领域事件（aggregate_id, event_type, payload, timestamp, trace_id）”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 事件 schema 必须与 events.yaml 定义一致

- 事件 schema 必须与 events.yaml 定义一致。
- 每个事件必须用 `payload_entity` 引用 canonical payload shape；outbox 事件必须至少声明一个 consumer，其他无 consumer 事件必须声明 `no_consumer_reason`，且 consumer 与 reason 不得同时存在。
- 事件 payload 必须遵循 fields.yaml 的 classification 策略。
- 事件必须包含 OTEL traceID。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime eventstore 能力 SIT

- GIVEN 执行“runtime eventstore 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime eventstore 能力”对应动作。
- THEN 直属 Story 共同交付“MongoDB events 集合持久化领域事件（aggregate_id, event_type, payload, timestamp, trace_id）”，失败终态可区分且不产生伪成功事实。
- THEN 任一事件缺失/悬空 `payload_entity`、outbox 无 consumer、无 consumer 且无 reason 或 consumer/reason 冲突时，metadata compiler 全局失败，不保留服务特例。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime eventstore 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：MongoDB events 集合持久化领域事件（aggregate_id, event_type, payload, timestamp, trace_id）。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
