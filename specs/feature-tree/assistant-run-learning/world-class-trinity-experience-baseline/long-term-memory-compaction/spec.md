# L3 Story：事实型长期记忆与长会话压缩 (`long-term-memory-compaction`)

> 所属能力：[`world-class-trinity-experience-baseline`](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为长期使用小趣的用户，我希望它记住我说过的常用地点、家庭称谓、饮食禁忌和出行偏好，在长对话里也不忘记前面谈过的目标，并且这些记忆我随时可以查看、遗忘和恢复。

## 2. 范围与非目标

### In Scope

- 事实型长期记忆的记录、注入、遗忘与恢复
- 长会话历史的滚动摘要压缩
- 记忆来源与生效范围的用户可见性

### Out of Scope

- 向量记忆与语义相似度召回
- 隐式性格推断与未经用户确认的画像写入
- 文风类结构化偏好，归 [`session-preference-memory-control`](../session-preference-memory-control/spec.md)

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 事实型长期记忆可记录、注入并撤销

- 用户在对话中陈述的稳定事实必须在用户确认后才写入长期记忆，并在后续运行中注入。
- 长期记忆必须复用既有授权、遗忘与撤销窗口内恢复语义，非所有者不可见。
- 遗忘后运行时召回必须立即排除该事实，不得依赖缓存过期。

<a id="req-002"></a>
### REQ-002 长会话按滚动摘要压缩且不丢目标

- 会话历史超过注入预算时必须以滚动摘要压缩，保留当前目标、已确认槽位与未完成事项。
- 不得以固定长度截断丢弃早期轮次的关键事实。
- 压缩结果必须可追溯到被压缩的轮次范围。

<a id="req-003"></a>
### REQ-003 记忆生效范围对用户可见

- 每条长期记忆必须可展示其来源与生效范围，使用户能判断它会在哪些场合影响回答。
- 记忆不得在其声明的生效范围之外注入。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_preference_fact/operations.yaml`
- object：`quwoquan_service/services/assistant-service/contracts/_shared/preference_fact/schema.yaml`
- object：`quwoquan_service/services/assistant-service/contracts/_shared/context_continuity_policy/schema.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 陈述的稳定事实经确认后长期生效并可撤销

- GIVEN 用户在对话中陈述了一个稳定事实并确认记录
- WHEN 用户在后续新会话中提出相关问题
- THEN 该事实进入模型请求并影响回答
- THEN 用户遗忘该事实后运行时召回立即排除它
- THEN 撤销窗口内恢复后重新纳入，非所有者始终不可见

<a id="gwt-002"></a>
### GWT-002 长会话压缩后仍延续原目标

- GIVEN 一个会话的历史轮次已超过注入预算
- WHEN 用户就先前谈过的目标继续追问
- THEN 注入内容为滚动摘要且保留当前目标与已确认槽位
- THEN 早期轮次的关键事实未被固定长度截断丢弃
- THEN 压缩结果可追溯到被压缩的轮次范围

## 6. 依赖

- 前置要求：[`world-class-trinity-experience-baseline`](../spec.md) 的范围、要求与 SIT。
- 上游事实：用户确认的记忆写入授权与既有偏好事实的撤销语义。
- 下游结果：本 Story 声明的 GWT 可观察结果，供上下文装配按渠道记忆范围消费。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 事实型长期记忆与会话压缩尚未实现

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺事实型长期记忆与会话压缩。现有记忆只覆盖回答风格、长度、语气与语言四类文风偏好，无法承载常用地点、称谓、禁忌与出行偏好等稳定事实；会话历史按固定长度逐轮截断注入，长对话会丢失早期目标与已确认槽位。
- 完成判定：`GWT-001` 与 `GWT-002` 由真实测试直接 `spec_ref`。
