# L3 Story：反馈摄入采样 (`feedback-ingestion-sampling`)

> 所属能力：[`feed-orchestration-recommendation`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望统一上报通道 `BehaviorReporter`：单一出口，消除双通道重复上报与 behaviors/ops 双写，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “反馈摄入采样”的输入、可观察主路径、失败语义以及与父能力的交接。
- 将历史双出口收敛为统一 BehaviorReporter 网络通道。
- 可见性阈值、端侧聚合采样、分级上报。
- clientEventId 幂等与 feedRequestId 归因闭环。
- 全事件携带 referralSource/position/channelId/rankingVersion/reasonVersion/recallPath/contentVertical/supplySource 归因字段（common_fields + P0+ attribution），served/impressed 双轨记账（阶段五）。
- P0 不实现离线训练样本生成、长期本地持久队列或平台级事件总线。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 反馈摄入采样

- 统一上报通道 `BehaviorReporter`：单一出口，消除双通道重复上报与 behaviors/ops 双写。

<a id="req-002"></a>
### REQ-002 统一上报通道 BehaviorReporter：单一出口，消除双通道重复上报与 behaviors/ops 双写

- 统一上报通道 `BehaviorReporter`：单一出口，消除双通道重复上报与 behaviors/ops 双写。
- 可见性判定：`impressed` 必须达「可见面积 + 停留」阈值，`visible` 仅本地或低采样，替换「build 即曝光」。
- 归因闭环：曝光携带 `feedRequestId`，点击复用同一 id（禁止重生），打通召回↔曝光↔互动漏斗。
- P0 不实现离线训练样本生成、长期本地持久队列或平台级事件总线；端侧统一上报和云侧 ingest 抗冲击已在 P0 最小集落地。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/redis_keyspace.yaml`
- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 反馈摄入采样

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“反馈摄入采样”对应的公开行为。
- THEN 统一上报通道 `BehaviorReporter`：单一出口，消除双通道重复上报与 behaviors/ops 双写。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`feed-orchestration-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 反馈摄入采样 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“反馈摄入采样”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
