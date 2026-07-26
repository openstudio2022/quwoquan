# L1 Domain Service：助手运行与学习闭环 (`assistant-run-learning`)

> 一句话定位：让小趣在可追踪的运行与流式协议中执行策略，并从反馈形成可审计的学习和画像提案闭环。

## 1. 目标与用户价值

让用户获得可恢复、可解释且上下文一致的小趣回答；让平台以版本化策略、学习事件、反馈聚合和用户确认的画像提案持续改进助手行为。

## 2. 领域边界

### 本领域拥有

- 拥有 `AssistantConversation`、`AssistantRun`、流式事件、助手策略版本与助手学习事实的生命周期和写入决定权。
- 只能通过本领域公开 command 修改其拥有事实。

### 本领域不拥有

- 不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 不拥有 `ProfileUpdateProposal`、`Persona` 或其应用审计事实；这些事实由用户身份画像领域和 user-service 的公开聚合契约拥有，本领域只能提交来源证据或调用其公开 command。
- 不复制 metadata 中的字段、path、错误码和 wire 语义。

### 上下游协作

- 上游：AppRoot Journey 与公开输入事实。
- 下游：直接 L2 能力以及协作 L1 的公开结果。
- 跨域写入：目标领域公开 command；禁止直写目标存储。
- 跨域读取：目标领域公开 query/projection。

## 3. Journey / Scenario 职责

- [`JNY-007 / SCN-015`](../spec.md#scn-015)
  - 本领域负责：在“小趣作为会话成员参与消息”中，消费页面或会话上下文，创建或续接 AssistantConversation、Run 与 Turn，并执行授权、策略和订阅门禁。
  - 进入条件：`chat-conversation` 已交付其公开结果。
  - 交付给下游的结果：消费页面或会话上下文，创建或续接 AssistantConversation、Run 与 Turn，并执行授权、策略和订阅门禁，形成该场景中本领域负责的终态。
  - 不负责：不写入 Conversation、Post、UserAccount 或搜索索引事实。
- [`JNY-009 / SCN-017`](../spec.md#scn-017)
  - 本领域负责：在“内容与页面上下文感知问答”中，消费页面或会话上下文，创建或续接 AssistantConversation、Run 与 Turn，并执行授权、策略和订阅门禁。
  - 进入条件：用户发起“内容与页面上下文感知问答”且身份、输入与权限前置成立。
  - 交付给下游的结果：消费页面或会话上下文，创建或续接 AssistantConversation、Run 与 Turn，并执行授权、策略和订阅门禁，供 `runtime` 继续处理。
  - 不负责：不写入 Conversation、Post、UserAccount 或搜索索引事实。
- [`JNY-009 / SCN-018`](../spec.md#scn-018)
  - 本领域负责：在“群聊话题理解与会话内回复”中，消费页面或会话上下文，创建或续接 AssistantConversation、Run 与 Turn，并执行授权、策略和订阅门禁。
  - 进入条件：用户发起“群聊话题理解与会话内回复”且身份、输入与权限前置成立。
  - 交付给下游的结果：消费页面或会话上下文，创建或续接 AssistantConversation、Run 与 Turn，并执行授权、策略和订阅门禁，供 `chat-conversation` 继续处理。
  - 不负责：不写入 Conversation、Post、UserAccount 或搜索索引事实。
- [`JNY-009 / SCN-019`](../spec.md#scn-019)
  - 本领域负责：在“搜索 handoff 与统一 grounding”中，消费页面或会话上下文，创建或续接 AssistantConversation、Run 与 Turn，并执行授权、策略和订阅门禁。
  - 进入条件：用户发起“搜索 handoff 与统一 grounding”且身份、输入与权限前置成立。
  - 交付给下游的结果：消费页面或会话上下文，创建或续接 AssistantConversation、Run 与 Turn，并执行授权、策略和订阅门禁，供 `global-search-experience` 继续处理。
  - 不负责：不写入 Conversation、Post、UserAccount 或搜索索引事实。
- [`JNY-009 / SCN-020`](../spec.md#scn-020)
  - 本领域负责：在“小趣主动订阅与用户/会话投递”中，消费页面或会话上下文，创建或续接 AssistantConversation、Run 与 Turn，并执行授权、策略和订阅门禁。
  - 进入条件：用户发起“小趣主动订阅与用户/会话投递”且身份、输入与权限前置成立。
  - 交付给下游的结果：消费页面或会话上下文，创建或续接 AssistantConversation、Run 与 Turn，并执行授权、策略和订阅门禁，供 `chat-conversation` 继续处理。
  - 不负责：不写入 Conversation、Post、UserAccount 或搜索索引事实。

## 4. 业务能力

- [`assistant-runtime-foundation`](./assistant-runtime-foundation/spec.md)：承载助手域业务对象运行基座：`AssistantConversation`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询。
- [`learning-event-feedback-injection`](./learning-event-feedback-injection/spec.md)：统一学习事件上报、反馈聚合与运行时上下文注入链路。
- [`profile-proposal-apply-loop`](./profile-proposal-apply-loop/spec.md)：定义画像提案从生成、确认/拒绝到应用落档的完整闭环。
- [`run-stream-policy`](./run-stream-policy/spec.md)：规范助手 Run/Stream 主链路的协议、策略模板与域路由行为。
- [`world-class-trinity-experience-baseline`](./world-class-trinity-experience-baseline/spec.md)：以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注，提供可持续扩展且可回退的小趣体验。

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 assistant run learning 领域边界验收

- 领域边界、上下游依赖、工程映射和服务治理清晰。

<a id="req-002"></a>
### REQ-002 Run 请求与响应契约必须与端侧 personalassistant 协议兼容

- Run 请求与响应契约必须与端侧 personal_assistant 协议兼容。
- 学习事件、评分卡、反馈统计必须进入 metadata 驱动口径。
- 助手策略发布必须支持灰度与回滚。
- `learning-event-feedback-injection`（L2）：统一学习事件、反馈聚合、注入链路
- `learning-event-ingestion`（L3）：InteractionEvent / Scorecard 上报与统一事件桥接

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 assistant run learning 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。
- 禁止结果：不得绕过本领域公开 command/query/event 写入其拥有事实。

## 7. 工程归属

- App：`quwoquan_app/lib/ui/assistant`、`quwoquan_app/lib/cloud/services/assistant`
- Contracts：`quwoquan_service/services/assistant-service/contracts`、`quwoquan_service/services/recommendation-service/contracts`
- Service：`quwoquan_service/services/assistant-service`、`quwoquan_service/services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime`
- 测试：
  - `local_contract`：`quwoquan_service/services/assistant-service/tests`
  - `api_integration`：`quwoquan_service/services/assistant-service/tests`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 assistant run learning 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：领域边界、上下游依赖、工程映射和服务治理清晰。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效
