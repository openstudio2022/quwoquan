# L3 Story：双轨渠道推荐引擎 (`dual-channel-recommendation-engine`)

> 所属能力：[`runtime-recommendation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望**SessionReader** 接口：统一读路径，HotPath / SessionCache 均实现，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “双轨渠道推荐引擎”的输入、可观察主路径、失败语义以及与父能力的交接。
- HotPath session 信号写入与读取。
- 多源召回、预排、过滤、特征组装、Rule/Remote/CascadeScorer、重排。
- 模型降级、召回源超时、负反馈过滤、多样性与冷启动。
- 首页 feed 页面体验和频道 IA。
- 深度排序模型平台轨、双塔 ANN、广告竞价。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 双轨渠道推荐引擎

- **SessionReader** 接口：统一读路径，HotPath / SessionCache 均实现。

<a id="req-002"></a>
### REQ-002 SessionReader 接口：统一读路径，HotPath / SessionCache 均实现

- **SessionReader** 接口：统一读路径，HotPath / SessionCache 均实现。
- **SignalProcessor** 接口：统一写路径，HotPath / BufferedHotPath 均实现。
- CascadeScorer 保证 ML 模型不可用时自动降级到 RuleScorer。

<a id="req-003"></a>
### REQ-003 必须HotPath + ColdPath + Engine 7 阶段管线的双通道推荐引擎验收，且失败时不得写入成功事实

- 系统必须HotPath + ColdPath + Engine 7 阶段管线的双通道推荐引擎验收，且失败时不得写入成功事实。

<a id="req-004"></a>
### REQ-004 ML 模型集成：ModelScorer 抽象统一打分接口；支持 RuleScorer 基线 / RemoteModelScorer 远程 ML / CascadeScorer 容灾降级

- **ML 模型集成**：ModelScorer 抽象统一打分接口；支持 RuleScorer 基线 / RemoteModelScorer 远程 ML / CascadeScorer 容灾降级。

## 4. 契约引用

- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/operations.yaml`
- canonical：`quwoquan_service/services/recommendation-service/config/schema.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 双轨渠道推荐引擎

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“双轨渠道推荐引擎”对应的公开行为。
- THEN **SessionReader** 接口：统一读路径，HotPath / SessionCache 均实现。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`runtime-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
