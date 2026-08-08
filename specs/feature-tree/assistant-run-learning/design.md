# L1 Design：助手运行与学习闭环 (`assistant-run-learning`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：让小趣以 active Skill package 为用户能力单元，以 `AssistantRun` 为唯一执行聚合，通过渐进上下文、受控 Tool/Connector、持久长任务和安全 Presentation 扩展垂类，同时保持业务事实归所属领域所有。

## 2. 领域模型与所有权

- authoritative ownership：拥有 `SkillPackageRelease`、Catalog、UserSetting、Consent、Subscription、SurfacePlacement、`AssistantSession`、`AssistantRun`、运行证据、Presentation、助手策略发布和助手学习事实的生命周期与写入决定权。
- execution ownership：`AssistantSession` 只持有会话生命周期与摘要；`AssistantRun` 唯一持有 Goal、RunItem journal、TaskGraph、ContextSnapshot、Tool receipt、Checkpoint、Presentation 与完成门。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- cross-domain proposal boundary：`ProfileUpdateProposal`、`Persona`、应用审计与回滚事实归 user-service 的用户身份画像领域所有；助手只通过该聚合的公开 command/event 提交可审核来源，不复制状态机、receipt、outbox 或存储。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。
- 非本域对象：Gathering/GatheringPlan/Conversation/Circle/Post/Persona/Connector 连接与凭证仍由所属 L1/服务拥有；助手只保留 provenance、artifactRef、receiptRef 和运行时快照。

## 3. 上下文边界与协作

- [`JNY-007 / SCN-015`](../spec.md#scn-015) — 在“小趣作为会话成员参与消息”中，按共享 Placement 路由 active package，并创建或续接 AssistantSession 与 AssistantRun。
- [`JNY-009 / SCN-017`](../spec.md#scn-017) — 在“内容与页面上下文感知问答”中，消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁。
- [`JNY-009 / SCN-018`](../spec.md#scn-018) — 在“群聊话题理解与会话内回复”中，消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁。
- [`JNY-009 / SCN-019`](../spec.md#scn-019) — 在“搜索 handoff 与统一 grounding”中，消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁。
- [`JNY-009 / SCN-020`](../spec.md#scn-020) — 在“小趣主动订阅与用户/会话投递”中，消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁。
- [`JNY-009 / SCN-034`](../spec.md#scn-034) — 以独立对象交付 Skill 发现、设置、授权、主动订阅、共享 Placement 和运行活动。
- [`JNY-013 / SCN-030`](../spec.md#scn-030) — 以 `travel_companion` 组合 Gathering/GatheringPlan、Chat、Content 与 Public Web 上下文，生成可确认计划提案。
- [`JNY-013 / SCN-031`](../spec.md#scn-031) — 以标准 Trigger→Run 管线解释 Revision diff、风险、下一步和讲解，并按可见范围投递。
- [`JNY-013 / SCN-032`](../spec.md#scn-032) — 建议 Experience reference 归属并用安全 Presentation 展示统一时间线/地图。
- [`JNY-013 / SCN-033`](../spec.md#scn-033) — 生成可编辑游记与分段分享提案，确认后续接所属领域 command。

## 4. 架构与数据流

- [`assistant-runtime-foundation`](./assistant-runtime-foundation/spec.md)：承载助手域业务对象运行基座：`AssistantSession`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询。
- [`learning-event-feedback-injection`](./learning-event-feedback-injection/spec.md)：统一学习事件上报、反馈聚合与运行时上下文注入链路。
- [`profile-proposal-apply-loop`](./profile-proposal-apply-loop/spec.md)：定义画像提案从生成、确认/拒绝到应用落档的完整闭环。
- [`run-stream-policy`](./run-stream-policy/spec.md)：规范助手 Run/Stream 主链路的协议、策略模板与域路由行为。
- [`skill-product-integration-platform`](./skill-product-integration-platform/spec.md)：把 active package、用户设置、Consent、主动 Subscription、共享 Placement、Domain Reader 和 Connector grant 组合为用户可理解的 Skill 生命周期。
- [`world-class-trinity-experience-baseline`](./world-class-trinity-experience-baseline/spec.md)：以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与显式偏好回注，提供可持续扩展且可回退的小趣体验。
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

<a id="dec-002"></a>
### DEC-002 Skill 资产发布与业务事实访问单轨
- 决策：源码资产只由 publisher 读取并生成不可变 Skill package；生产 Catalog、Router、Context、Prompt、Capability、Presentation 与 Evaluation 只解析 active release，Run 冻结 digest。业务事实只通过 Descriptor 指向的公开 Reader/command/event 访问。
- 理由：运行时文件扫描、巨型 profile 资产和 Skill 专用分支会让激活、回滚、恢复、权限和评测各自拥有不同真相；Skill 直接访问领域存储又会复制业务模型。
- 被否决方案：生产扫描 Manifest、内置 catalog 硬编码、每个 Skill 增加 Go/Dart 路由、Skill 持有 Connector credential 或 GatheringPlan/Post 副本。
- 约束与影响：新增普通 Skill 只能增加签名资产，新增领域事实能力只增加 Reader Adapter，新增外部协议只在 Integration Service 增加 Connector Adapter。权限在每个 Run 安全边界重新求交，被撤销能力立即失效。
- 关联要求：`REQ-003`
- 关联能力：[`skill-product-integration-platform`](./skill-product-integration-platform/spec.md)、[`world-class-trinity-experience-baseline`](./world-class-trinity-experience-baseline/spec.md)

## 6. 质量与运行约束

- consent 查询失败必须 fail-closed。
- prompt、skill 和 policy 使用可审计版本；grounding 与主动投递使用独立配置开关。
- 指标至少区分 run 终态、取消延迟、工具失败、授权拒绝和恢复失败。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
