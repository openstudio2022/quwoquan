# L1 Design：助手运行与学习闭环 (`assistant-run-learning`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：让用户获得可恢复、可解释且上下文一致的小趣回答；让平台以 releaseDigest 内容寻址的不可变策略发布、学习事件、反馈聚合和用户确认的画像提案持续改进助手行为。

## 2. 领域模型与所有权

- authoritative ownership：拥有 `AssistantSession`、`AssistantRun`、流式事件、助手策略发布和助手学习事实的生命周期与写入决定权。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- cross-domain proposal boundary：`ProfileUpdateProposal`、`Persona`、应用审计与回滚事实归 user-service 的用户身份画像领域所有；助手只通过该聚合的公开 command/event 提交可审核来源，不复制状态机、receipt、outbox 或存储。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- [`JNY-007 / SCN-015`](../spec.md#scn-015) — 在“小趣作为会话成员参与消息”中，消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁。
- [`JNY-009 / SCN-017`](../spec.md#scn-017) — 在“内容与页面上下文感知问答”中，消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁。
- [`JNY-009 / SCN-018`](../spec.md#scn-018) — 在“群聊话题理解与会话内回复”中，消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁。
- [`JNY-009 / SCN-019`](../spec.md#scn-019) — 在“搜索 handoff 与统一 grounding”中，消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁。
- [`JNY-009 / SCN-020`](../spec.md#scn-020) — 在“小趣主动订阅与用户/会话投递”中，消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁。

## 4. 架构与数据流

- [`assistant-runtime-foundation`](./assistant-runtime-foundation/spec.md)：承载助手域业务对象运行基座：`AssistantSession`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询。
- [`learning-event-feedback-injection`](./learning-event-feedback-injection/spec.md)：统一学习事件上报、反馈聚合与运行时上下文注入链路。
- [`profile-proposal-apply-loop`](./profile-proposal-apply-loop/spec.md)：定义画像提案从生成、确认/拒绝到应用落档的完整闭环。
- [`run-stream-policy`](./run-stream-policy/spec.md)：规范助手 Run/Stream 主链路的协议、策略模板与域路由行为。
- [`world-class-trinity-experience-baseline`](./world-class-trinity-experience-baseline/spec.md)：以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注，提供可持续扩展且可回退的小趣体验。
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 运行状态是流式交付的唯一事实源
- 决策：运行状态是流式交付的唯一事实源。
- 理由：让用户获得可恢复、可解释且上下文一致的小趣回答；让平台以 releaseDigest 唯一标识策略内容，并通过 rollout revision 控制激活与回滚。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 关联能力：[`assistant-runtime-foundation`](./assistant-runtime-foundation/spec.md)、[`learning-event-feedback-injection`](./learning-event-feedback-injection/spec.md)、[`profile-proposal-apply-loop`](./profile-proposal-apply-loop/spec.md)、[`run-stream-policy`](./run-stream-policy/spec.md)、[`world-class-trinity-experience-baseline`](./world-class-trinity-experience-baseline/spec.md)

## 6. 质量与运行约束

- consent 查询失败必须 fail-closed。
- prompt、skill 和 policy 使用可审计版本；grounding 与主动投递使用独立配置开关。
- 指标至少区分 run 终态、取消延迟、工具失败、授权拒绝和恢复失败。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
