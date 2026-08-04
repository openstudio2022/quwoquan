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
- AssistantRun 创建时必须固化会话级与长期 active 事实快照，公开 Run 信封不得回显内部记忆内容。

<a id="req-002"></a>
### REQ-002 长会话按滚动摘要压缩且不丢目标

- 会话历史超过注入预算时必须以滚动摘要压缩，保留当前目标、已确认槽位与未完成事项。
- 不得以固定长度截断丢弃早期轮次的关键事实。
- 压缩结果必须可追溯到被压缩的轮次范围。
- 摘要必须以完成序列和版本 CAS 持久增量推进；重复完成、并发更新与服务重启不得重复压缩或遗失既有摘要。
- 只有完成态 AssistantRun 的事务 outbox 能推进摘要；失败、取消、群聊和圈子共享 surface 不得写入个人会话连续性。
- 摘要模型只处理被标记为不可信的会话文本并返回有界叙事；当前目标、已确认事实/槽位、待处理事项与轮次范围由服务端结构化合并和摘要预算校验保护，Hook 不得改写 canonical Run 完成条件或安全事实。
- 新 Run 创建时从所属 active AssistantSession 冻结当时的摘要快照；Run 恢复继续使用该快照，不在执行中追读可变 Session。

<a id="req-003"></a>
### REQ-003 记忆生效范围对用户可见

- 每条长期记忆必须可展示其来源与生效范围，使用户能判断它会在哪些场合影响回答。
- 记忆不得在其声明的生效范围之外注入。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_preference/operations.yaml`
- object：`quwoquan_service/services/assistant-service/contracts/_shared/assistant_preference_snapshot/schema.yaml`
- object：`quwoquan_service/services/assistant-service/contracts/_shared/context_continuity_policy/schema.yaml`
- object：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_session/fields.yaml`
- object：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_run/fields.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 陈述的稳定事实经确认后长期生效并可撤销

- GIVEN 用户在对话中陈述了一个稳定事实并确认记录
- WHEN 用户在后续新会话中提出相关问题
- THEN 该事实进入模型请求并影响回答
- THEN 用户遗忘该事实后运行时召回立即排除它
- THEN 撤销窗口内恢复后重新纳入，非所有者始终不可见
- THEN Run 快照随创建持久化但不通过公开信封泄漏

<a id="gwt-002"></a>
### GWT-002 长会话压缩后仍延续原目标

- GIVEN 一个会话的历史轮次已超过注入预算
- WHEN 用户就先前谈过的目标继续追问
- THEN 注入内容为滚动摘要且保留当前目标与已确认槽位
- THEN 早期轮次的关键事实未被固定长度截断丢弃
- THEN 压缩结果可追溯到被压缩的轮次范围
- THEN 并发 CAS 仅一个写入者成功，重启后继续复用同一持久摘要
- THEN 同一完成事件重放不再次调用摘要 Provider，群聊或圈子 Run 不产生个人摘要
- THEN 后续个人 Run 冻结注入该摘要，既有 Run 不因 Session 后续变化而漂移

## 6. 依赖

- 前置要求：[`world-class-trinity-experience-baseline`](../spec.md) 的范围、要求与 SIT。
- 上游事实：用户确认的记忆写入授权与既有 AssistantPreference 的撤销语义。
- 下游结果：本 Story 声明的 GWT 可观察结果，供上下文装配按渠道记忆范围消费。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
