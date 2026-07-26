# L3 Story：反馈聚合 (`feedback-aggregation`)

> 所属能力：[`learning-event-feedback-injection`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-015`](../../../spec.md#scn-015)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为使用小趣的用户或助手运营者，
我希望聚合结果必须可回放复算，口径固定可追溯，
从而获得可解释、可恢复且可持续改进的助手结果。

## 2. 范围与非目标

### In Scope

- “反馈聚合”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 反馈聚合

- “反馈聚合”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 聚合结果必须可回放复算，口径固定可追溯

- 聚合结果必须可回放复算，口径固定可追溯。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 反馈聚合

- GIVEN append-only learning facts 包含重复、迟到或不同到达顺序的合法事件。
- WHEN versioned projector 首次消费或从事实清空重建反馈聚合。
- THEN 同一事实集合产生相同 aggregate definition version、watermark 与统计结果，重复 eventId 不重复计数。
- AND projector 失败时保留上一个已提交 watermark，不发布半成功画像，读取方只消费同一 canonical projection。

## 6. 依赖

- 前置要求：[`learning-event-feedback-injection`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 可回放的版本化反馈聚合

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前画像计数在写入路径直接 `$inc`，缺少 event version、watermark、projection version 和 replay receipt，不能在迟到事件、重放或口径变更后可靠复算。
- 完成判定：append-only typed learning event 是唯一输入。versioned projector 以 eventId/eventVersion 幂等消费并保存 watermark 与 aggregate definition version。同一回放不重复计数、清空投影后可从事实重建，且 API/运营视图只读该投影。`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
