# L3 Story：学习事件摄入 (`learning-event-ingestion`)

> 所属能力：[`learning-event-feedback-injection`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-015`](../../../spec.md#scn-015)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为使用小趣的用户或助手运营者，
我希望`queryTextDigest`（不得直接以原始敏感文本进入公开分析层），
从而获得可解释、可恢复且可持续改进的助手结果。

## 2. 范围与非目标

### In Scope

- “学习事件摄入”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 学习事件摄入

- `queryTextDigest`（不得直接以原始敏感文本进入公开分析层）。

<a id="req-002"></a>
### REQ-002 对下映射到统一 EventEnvelope、学习特征投影与运营分析视图

- 对下映射到统一 EventEnvelope、学习特征投影与运营分析视图。
- `queryTextDigest`（不得直接以原始敏感文本进入公开分析层）
- `InteractionEvent` 与 `Scorecard` 进入统一 `learning` 域，不再作为 Assistant 独有的孤立上报体系长期存在。
- `pageVisitId / surfaceId / routeId / experimentBucket` 必须在可用时进入学习事件 context，支撑页面、策略、实验与体验分析。
- 需要训练的字段与仅可统计字段必须显式分离，遵守字段分级与 `trainingEligible` 语义。
- 每个 InteractionEvent 与 Scorecard 必须拥有稳定幂等键。
- 端侧重试与云侧重放不得重复计入同一训练样本或统计样本。
- 事件上报成功率、字段完整性与策略注入命中率必须可复盘。
- 事件必须支持幂等与去重；字段策略遵从 metadata。
- 明文 PII、敏感 query、原始对话内容不得直接进入公开分析宽表。

<a id="req-003"></a>
### REQ-003 queryText、answerText、correctionText 等原始文本不得直接进入公开聚合层

- `queryText`、`answerText`、`correctionText` 等原始文本不得直接进入公开聚合层。
- 是否可进入训练必须由 `trainingEligible` 与字段分级共同决定。
- `PII_RESTRICTED`：仅受控链路可见，不得进入公开分析与默认训练。
- `PII_RESTRICTED` 字段默认不可训练。
- InteractionEvent 与 Scorecard 必须具备稳定幂等键、去重窗口与补数兼容策略。
- 同一 `eventId + eventVersion` 重放不得重复计数。
- 同一 `scorecardId` 重报不得重复进入训练样本。
- 端侧本地缓存重试、网络重放、批量补数必须保持口径一致。
- 学习事件可稳定进入统一事件与反馈基础设施。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 学习事件摄入

- GIVEN 已授权主体提交带稳定 eventId、schema version 与可信运行上下文的 InteractionEvent 或 Scorecard。
- WHEN 事件通过本领域公开 append contract 摄入。
- THEN 事实以 typed learning envelope 只追加一次，并保留可追溯的 page/surface/route/operation/experiment 与 training eligibility 语义。
- AND 同一 eventId 的幂等重放返回已确认结果，冲突版本、伪造主体或非法字段返回 canonical failure，且不产生成功事实或敏感原文分析副本。

## 6. 依赖

- 前置要求：[`learning-event-feedback-injection`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 学习事件摄入统一契约与运营闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 `eventVersion`、`pageVisitId`、`surfaceId`、`routeId`、`experimentBucket`、`trainingEligible` 的 metadata-owned 统一 learning 契约，以及跨域消费者和环境运营证据。Mongo API integration 已证明敏感原文不进入学习画像的公开聚合字段、稳定 eventId 幂等与 canonical failure。
- 完成判定：`GWT-001` 对应行为满足；InteractionEvent 与 Scorecard 进入 metadata-owned unified learning contract，字段分级、训练资格、重放幂等、跨域消费与四环境运营证据全部由真实测试和环境执行证明。
