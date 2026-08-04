# L1 Domain Service：助手运行与学习闭环 (`assistant-run-learning`)

> 一句话定位：让小趣在可追踪的运行与流式协议中执行策略，并从反馈形成可审计的学习和画像提案闭环。

## 1. 目标与用户价值

让用户通过一个可发现、可设置、可授权、可挂载且可恢复的小趣获得上下文一致的持续服务；让平台以 active `SkillPackageRelease`、持久 `AssistantRun`、受控能力和可审计学习事实扩展垂类，而不为每个 Skill 增加运行时分支。

## 2. 领域边界

### 本领域拥有

- 拥有 `SkillPackageRelease`、`SkillCatalog`、`SkillUserSetting`、`SkillConsent`、`SkillSubscription`、`SkillSurfacePlacement`、`AssistantSession`、`AssistantRun`、运行证据、Presentation、助手策略发布与助手学习事实的生命周期和写入决定权。
- `AssistantSession` 只拥有会话生命周期与摘要；计划、RunItem、TaskGraph、Tool、Context、Checkpoint、Presentation 和完成验收只由 `AssistantRun` 拥有。
- 只能通过本领域公开 command 修改其拥有事实。

### 本领域不拥有

- 不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 不拥有 `ProfileUpdateProposal`、`Persona` 或其应用审计事实；这些事实由用户身份画像领域和 user-service 的公开聚合契约拥有，本领域只能提交来源证据或调用其公开 command。
- 不拥有 Trip、Conversation、Circle、Post、Entity 或 Connector credential/connection/invocation 事实；只通过所属领域的 typed Reader、command、event 或 capability gateway 使用。
- 不复制 metadata 中的字段、path、错误码和 wire 语义。

### 上下游协作

- 上游：AppRoot Journey 与公开输入事实。
- 下游：直接 L2 能力以及协作 L1 的公开结果。
- 跨域写入：目标领域公开 command；禁止直写目标存储。
- 跨域读取：目标领域公开 query/projection。

## 3. Journey / Scenario 职责

- [`JNY-007 / SCN-015`](../spec.md#scn-015)
  - 本领域负责：在“小趣作为会话成员参与消息”中，消费页面或会话上下文，创建或续接 AssistantSession 与 AssistantRun，并执行 active Skill、共享 Placement、授权、策略和订阅门禁。
  - 进入条件：`chat-conversation` 已交付其公开结果。
  - 交付给下游的结果：消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁，形成该场景中本领域负责的终态。
  - 不负责：不写入 Conversation、Post、UserAccount 或搜索索引事实。
- [`JNY-009 / SCN-017`](../spec.md#scn-017)
  - 本领域负责：在“内容与页面上下文感知问答”中，消费页面或会话上下文，创建或续接 AssistantSession 与 AssistantRun，并执行 active Skill、上下文、授权和工具门禁。
  - 进入条件：用户发起“内容与页面上下文感知问答”且身份、输入与权限前置成立。
  - 交付给下游的结果：消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁，供 `runtime` 继续处理。
  - 不负责：不写入 Conversation、Post、UserAccount 或搜索索引事实。
- [`JNY-009 / SCN-018`](../spec.md#scn-018)
  - 本领域负责：在“群聊话题理解与会话内回复”中，按共享 Placement 路由一个小趣可用的多个共享安全 Skill，并创建或续接 AssistantRun。
  - 进入条件：用户发起“群聊话题理解与会话内回复”且身份、输入与权限前置成立。
  - 交付给下游的结果：消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁，供 `chat-conversation` 继续处理。
  - 不负责：不写入 Conversation、Post、UserAccount 或搜索索引事实。
- [`JNY-009 / SCN-019`](../spec.md#scn-019)
  - 本领域负责：在“搜索 handoff 与统一 grounding”中，按需加载 Skill 与 Reader，通过来源账本形成可引用的 Context/Evidence，再由 AssistantRun 交付结果。
  - 进入条件：用户发起“搜索 handoff 与统一 grounding”且身份、输入与权限前置成立。
  - 交付给下游的结果：消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁，供 `global-search-experience` 继续处理。
  - 不负责：不写入 Conversation、Post、UserAccount 或搜索索引事实。
- [`JNY-009 / SCN-020`](../spec.md#scn-020)
  - 本领域负责：在“小趣主动订阅与用户/会话投递”中，把 Trigger 转为标准 AssistantRun，并执行 consent、频控、静默、去重、共享投递和审计门禁。
  - 进入条件：用户发起“小趣主动订阅与用户/会话投递”且身份、输入与权限前置成立。
  - 交付给下游的结果：消费页面或会话上下文，创建或续接 AssistantSession、Run 与 Turn，并执行授权、策略和订阅门禁，供 `chat-conversation` 继续处理。
  - 不负责：不写入 Conversation、Post、UserAccount 或搜索索引事实。

- [`JNY-009 / SCN-034`](../spec.md#scn-034)
  - 本领域负责：交付 Skill 发现、详情、设置、授权、主动订阅、共享 Placement 与运行活动的统一用户生命周期。
  - 进入条件：调用方拥有可见账号或共享场景管理员身份，且目标 SkillPackageRelease 已激活。
  - 交付给下游的结果：用户设置、Consent、Subscription 或 Placement 事实，以及冻结 active package digest 的 AssistantRun。
  - 不负责：不保存 Connector 凭证，不修改 Chat/Circle 成员或其他领域事实。
- [`JNY-013 / SCN-030`](../spec.md#scn-030)
  - 本领域负责：由 `travel_companion` 渐进读取群聊、内容、Trip 与公网证据，生成结构化计划提案并通过 Travel command 确认。
  - 进入条件：目标共享场景、参与主体和可见范围有效；目标 Trip 不明确时先完成消歧。
  - 交付给下游的结果：带 package digest、证据和 ActionProposal 的 AssistantRun；确认后只持有 Travel receipt 引用。
  - 不负责：不拥有 Trip 或发布内容。
- [`JNY-013 / SCN-031`](../spec.md#scn-031)
  - 本领域负责：把 Trip Revision、天气交通风险和临近事项 Trigger 转成标准 Run，完成差异说明、导游讲解和相关成员投递。
  - 进入条件：Trigger、Subscription/Placement、Consent 与领域可见性均有效。
  - 交付给下游的结果：去重的共享提醒、带引用讲解或私密个人 ActionProposal。
  - 不负责：不决定 Trip Revision，不泄露个人 Connector 或记忆。
- [`JNY-013 / SCN-032`](../spec.md#scn-032)
  - 本领域负责：建议 Moment 的 Day/Item 归属并以安全语义 Presentation 展示时间线和地图。
  - 进入条件：Moment、Trip 与候选 Item 对当前主体可见。
  - 交付给下游的结果：归属建议或经确认的 Travel command receipt；不复制 MediaAsset/Post。
  - 不负责：不持有媒体或内容事实。
- [`JNY-013 / SCN-033`](../spec.md#scn-033)
  - 本领域负责：按实际 Trip 时间线生成可编辑 LocalPostDraft 提案和分段分享 Presentation，并在用户确认后续接所属领域 command。
  - 进入条件：Trip 已结束或用户显式选择生成范围，且隐私裁剪策略通过。
  - 交付给下游的结果：草稿/分享提案、引用与续接 receipt。
  - 不负责：不自动发布、不维护关系状态。

## 4. 业务能力

- [`assistant-runtime-foundation`](./assistant-runtime-foundation/spec.md)：承载助手域业务对象运行基座：`AssistantSession`/`AssistantTurn` 会话与轮次持久化、`SkillSubscription` 主动订阅、`SkillConsent` 敏感能力授权门控、入口个性化与个人数据查询。
- [`learning-event-feedback-injection`](./learning-event-feedback-injection/spec.md)：统一学习事件上报、反馈聚合与运行时上下文注入链路。
- [`profile-proposal-apply-loop`](./profile-proposal-apply-loop/spec.md)：定义画像提案从生成、确认/拒绝到应用落档的完整闭环。
- [`run-stream-policy`](./run-stream-policy/spec.md)：规范助手 Run/Stream 主链路的协议、策略模板与域路由行为。
- [`skill-product-integration-platform`](./skill-product-integration-platform/spec.md)：交付 active Skill package 驱动的目录、个人设置、Consent、主动 Subscription、共享 Placement、Domain Reader 与 Connector grant 用户生命周期。
- [`world-class-trinity-experience-baseline`](./world-class-trinity-experience-baseline/spec.md)：以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与显式偏好回注，提供可持续扩展且可回退的小趣体验。

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 assistant run learning 领域边界验收

- 领域边界、上下游依赖、工程映射和服务治理清晰。

<a id="req-002"></a>
### REQ-002 Run 请求与响应契约必须与端侧 personalassistant 协议兼容

- Run 请求与响应契约必须与端侧 personal_assistant 协议兼容。
- `AssistantLearningFact`（用户反馈、交互结果与服务评分）及其反馈统计必须进入 metadata 驱动口径。
- 助手策略发布必须支持灰度与回滚。
- `learning-event-feedback-injection`（L2）：统一学习事件、反馈聚合、注入链路
- `learning-event-ingestion`（L3）：`AppendAssistantLearningFact` 单轨追加与统一事件桥接

<a id="req-003"></a>
### REQ-003 Skill、上下文、能力与展示必须由 active package 单轨驱动

- 生产 Catalog、Router、Context、Prompt、Tool Policy、Presentation 与 Evaluation 只能消费当前 active `SkillPackageRelease`，Run 启动后冻结其 digest。
- 源码 Manifest/Profile 文件只允许由 publisher 构建 package，不得由生产请求路径扫描；恢复旧 Run 继续解析其冻结 digest。
- Skill 能力集合必须是 package allowlist、平台策略、surface policy、用户 Consent、Connector grant 与运行时可用性的交集。
- 新增只使用既有 Reader/Tool/Presentation node 的官方 Skill 时，不得修改 AgentLoop、Go/Dart 路由或 Flutter 节点注册表。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 assistant run learning 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。
- 禁止结果：不得绕过本领域公开 command/query/event 写入其拥有事实。

<a id="dom-002"></a>
### DOM-002 Skill 用户生命周期与运行时单轨

- 条件：官方 Skill package 已 stage 并激活，用户或共享场景发起响应式、主动式或恢复执行。
- 可观察结果：Catalog、Setting、Consent、Subscription、Placement 与 Run 分别表达自己的事实，且 Run 可追溯到唯一 package digest、Context/Tool 许可交集和 PresentationDocument。
- 禁止结果：不得扫描源码资产、把 Subscription/Consent 当启用开关、让 Chat Membership 绑定单一 Skill、读取共享场景中的个人记忆/Connector，或为 Skill 增加专用 AgentLoop/Flutter 分支。

## 7. 工程归属

- App：`quwoquan_app/lib/ui/assistant`、`quwoquan_app/lib/cloud/services/assistant`
- Contracts：`quwoquan_service/services/assistant-service/contracts`、`quwoquan_service/services/recommendation-service/contracts`、`quwoquan_service/services/user-service/contracts/persona_management/profile_update_proposal`
- Service：`quwoquan_service/services/assistant-service`、`quwoquan_service/services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime`、`quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal`
- 测试：
  - `local_contract`：`quwoquan_service/services/assistant-service/tests`、`quwoquan_service/services/user-service/tests/local_contract/persona_management/profile_update_proposal`
  - `api_integration`：`quwoquan_service/services/assistant-service/tests`、`quwoquan_service/services/user-service/tests/api_integration/account/user_account/profile_update_proposal_store__api_integration_test.go`
  - `user_acceptance`：`quwoquan_app/test/user_acceptance`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 assistant run learning 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺正式 Provider、真环境 UAT、完整领域 Reader/Connector grant 和 Skill Center 用户旅程。生产 Catalog/Router/Run 已统一读取 active/frozen package，源码扫描仅存在于 builder/test；Setting、Consent、Subscription 与 Placement 已由独立对象和运行时许可交集分轨，但 App 仍未完整消费 Setting/Placement。
- 完成判定：`DOM-001`、`DOM-002` 对应行为均有对象 local_contract、跨对象 api_integration 与 App user_acceptance 直接 `spec_ref`；同一候选完成 Alpha/Beta/Gamma active package、后台恢复和隐私 readback，Prod 另行绑定正式 Provider、灰度与回滚。
