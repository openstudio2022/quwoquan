# 小趣主动式私人助理云端优先跃迁规格

> 状态：M0 冻结候选
> 适用范围：小趣私人助理云端化、连续对话、主动式 Skill、端云流式协议、端侧上下文代理、统一应用消息通道
> 本目录记录文档已清理，本文件是 `docs/personal-assistant/` 下唯一评审入口。

## 1. 背景与核心结论

当前小趣已具备端侧 `AgentLoop`、`ReActRuntime`、`Skill`、`Tool`、`Replay` 等能力，但主动式体验要求小趣在用户不打开 App、多端并存、事件实时变化、趣聊/圈子需要分发的情况下稳定运行。端侧后台执行受 iOS/Android 限制，无法可靠承担长期调度、实时事件监听、多端去重、统一免打扰、审计和主动送达。

本轮架构调整的核心结论是：

**小趣主执行框架迁移为 Cloud-first Assistant Engine；端侧收敛为 Assistant UX Shell + Device Context Agent + Management Entry。**

进一步收敛后的业务建模原则是：

- 小趣的核心业务对象不是一次 `Run`，而是连续对话。
- 用户主动提问、系统主动触达、工具执行、端侧上下文补充都应落在同一个连续对话状态机内。
- 单次执行是 `AssistantTurn`，不是顶层业务对象的全部。
- 主动结果通知不应是助手私有送达对象，而应进入全 App 统一应用消息通道。
- Tool 概念对齐 Claude Code / OpenClaw 等业界实践：使用 `ToolUse`、`ToolResult`、权限确认和流式事件。

## 2. 产品目标

### 2.1 总目标

构建一个支持主动式体验的云端小趣引擎，让小趣从“用户问了才答”升级为“经授权后持续观察、判断、解释、触达、推动行动”的私人助理。

### 2.2 P0 主动式 Skill

P0 首批主动式能力包括：

1. **每日助手**
   - 覆盖生活、工作、学习。
   - 管理待办、日历、会议、作息、学习计划、复盘。
   - 形成早间计划、会前提醒、下午进度检查、晚间复盘。

2. **投资股票哨兵**
   - 关注股票、ETF、行业、公司、人物、主题。
   - 监测行情异动、消息面、财报、监管、并购、重大事件。
   - 输出信息提醒、风险解释和研究入口，不给确定性投资建议。

3. **出行旅程管家**
   - 绑定用户完整行程。
   - 持续关注天气、路况、景点拥堵、营业时间、沿途介绍、吃住行变化。
   - 在旅程中主动提醒和调整建议。

4. **新闻简报**
   - 支持早/中/晚摘要。
   - 基于用户关注的话题、人物、公司、圈子和内容兴趣。
   - 支持个人送达，后续扩展到趣聊群和圈子摘要。

## 3. 设计原则

### 3.1 Cloud-first

云端是主执行入口。凡是需要稳定运行、跨端一致、事件监听、定时触发、统一审计的能力，都必须放在云端。

云端优先承接：

- 模型调用。
- Skill routing。
- `AgentLoop`。
- `ReActRuntime`。
- 云端 Tool。
- 主动订阅。
- 调度与触发。
- 统一应用消息投递。
- 审计、频控、免打扰。

### 3.2 Conversation-first

小趣的主业务对象是连续对话，而不是孤立 run。

连续对话需要承载：

- 用户主动发起的问题。
- 系统主动触达后用户继续追问。
- 多轮上下文、记忆、槽位、当前目标和未完成事项。
- 云端执行状态。
- 端侧上下文请求与响应。
- `ToolUse` / `ToolResult`。
- 过程流和最终回答。

单次执行以 `AssistantTurn` 表示，挂在 `AssistantConversation` 下。主动式任务也必须生成一个 turn，从而能被用户继续追问、归档、复盘和审计。

### 3.3 Device-as-context-agent

端侧不是主执行引擎，而是设备侧上下文代理。

端侧负责：

- 采集位置、时区、网络、通知权限、前后台状态、设备状态。
- 在用户授权下提供日历、行程、本地环境摘要。
- 执行本机动作，例如打开页面、本地通知、系统分享。
- 呈现云端流式旅程和主动消息详情。

这里使用 `DeviceContext`，不使用单次快照作为核心概念。设备侧上下文不只是一次快照，也包括：

- 按授权持续更新的当前事实。
- 针对某次 turn 的即时补充。
- 端侧能力状态。
- 最近一次可用上下文。
- 上下文可用性、授权状态与最近一次可用事实。

### 3.4 Tool 云端优先，端云协调

不是所有 Tool 都在云端执行，但 Tool 编排权在云端。

- 网络搜索、新闻、行情、天气、地图路况、内容/圈子/聊天检索，优先云端。
- 位置、设备状态、通知权限、本地日历授权摘要，由端侧作为上下文提供。
- 打开页面、本地通知、系统分享等本机动作，由端侧执行。
- 出行、每日助手、会议准备等属于 Hybrid Tool，由云端编排，端侧补环境。

Tool 语义对齐业界 Agent 体系：

- `Tool` 是模型可调用能力。
- `ToolUse` 是一次结构化工具请求。
- `ToolResult` 是工具观察结果。
- 权限确认、输入校验、预算控制、错误映射属于 Tool runtime 边界。
- 端侧动作不是云端直接执行，而是云端产生 action proposal，由端侧确认并执行。

### 3.5 统一应用消息通道

主动结果通知不应是助手私有能力。需要建立全 App 统一端云消息通道，区别于手机原生 push。

该通道负责：

- App 内消息投递。
- 助手主动提醒。
- 聊天通知。
- 圈子/内容通知。
- 系统消息。
- 多通道协同送达。

通道可使用：

- WebSocket：App 活动时实时送达。
- Long polling：长时间不活跃或弱连接时降级。
- 原生 push：App 未启动或系统需要唤醒时使用。
- 站内 inbox：所有重要消息可追溯。

手机原生 push 是 transport 之一，不是业务消息本身。

### 3.6 业务对象简化

本阶段只定义最少核心对象，避免过早拆出复杂模型。

核心对象收敛为：

- `AssistantConversation`
- `AssistantTurn`
- `SkillSubscription`
- `DeviceContext`
- `ToolUse`
- `AppMessage`

其中：

- `AssistantConversation` 是连续对话主对象。
- `AssistantTurn` 是一次用户主动或系统主动交互。
- `SkillSubscription` 是主动式 Skill 配置。
- `DeviceContext` 是端侧上下文与能力状态。
- `Skill` 是面向用户、运营和执行三层复用的能力单元。
- `ToolUse` 是执行层的一次工具请求，对齐业界工具调用概念。
- `AppMessage` 是统一应用消息通道的业务消息。

免打扰、授权、风险、评分、使用量、触发器枚举等字段先不作为 M0 必选字段。它们进入后续策略或市场增强阶段，避免 M0 对象过重。

### 3.7 分类同源

Skill 分类不能单独设计，必须同源内容/圈子分类体系。

- 领域分类同源：`contracts/metadata/_shared/domain_taxonomy.yaml`
- 标签体系同源：`contracts/metadata/_shared/tag_taxonomy.yaml`
- Skill manifest / catalog 使用 `domainId`、`taxonomyRef`、`tagRefs`
- 不允许在 Skill 页面维护第二套“投资/出行/生活/学习”分类真相源。

## 4. 业界概念对齐

### 4.1 Skill 与 Tool 的三层定义

`Skill` 与 `Tool` 必须区分视角，避免把用户可管理的能力、运营可配置的商品/策略、模型执行时的工具调用混成一个对象。

`Skill` 是面向用户和业务运营的能力包装：

- 用户视角：用户能理解、订阅、配置、暂停、反馈的能力，例如“每日助手”“股票哨兵”“出行旅程管家”。
- 运营视角：平台可上架、推荐、分组、灰度、治理、配置提示词和风险边界的能力包。
- 执行视角：一次对话或主动触发时，Skill 为 Agent 提供任务目标、边界、状态机、Prompt 片段、可用工具策略和输出要求。

`Tool` 是执行层能力，不直接作为用户订阅对象：

- 用户通常不订阅“网络搜索工具”，而是订阅“股票哨兵”或“出行管家”。
- Tool 由 Agent 在执行 turn 时按策略调用。
- Tool 可以是云端工具、设备上下文工具、设备动作工具或混合工具。
- Tool 的核心执行对象是 `ToolUse`，结果回填为 `ToolResult`。

M0 只冻结 Skill/Tool 的边界，不急于定义评分、商业等级、使用量等市场字段。

### 4.2 Claude Code / OpenAI 对齐口径

Claude Code 类 Agent 体系的关键概念是：

- 会话是连续上下文，不是一次请求。
- 模型输出可以包含自然语言、工具请求和结构化中间事件。
- 工具请求使用标准 `tool_use` 语义。
- 工具执行结果使用标准 `tool_result` 语义回流模型。
- 工具执行前需要权限、预算和安全检查。
- 流式输出既包含文本增量，也包含工具和状态事件。

本规格对齐为：

- `AssistantConversation` 对齐连续会话。
- `AssistantTurn` 对齐一次用户或系统发起的交互轮次。
- `ToolUse` 对齐工具请求。
- `ToolResult` 作为 `ToolUse` 的结果部分，不单独顶层建模。
- `AssistantStreamEvent` 对齐流式事件信封。

业界通用工具流式阶段可抽象为：

- `message_start` / `turn_started`
- `content_delta` / `partial_answer`
- `tool_use_start`
- `tool_use_delta`
- `tool_use_ready`
- `tool_result`
- `message_delta`
- `message_stop` / `turn_completed`
- `error`

端云核心协议只保留抽象后的 `AssistantStreamEvent`，不直接暴露任何模型供应商或桥接方的私有事件名。

### 4.3 OpenClaw 对齐口径

OpenClaw 作为外部运行时/桥接方时，只能作为 provider adapter 的输入来源。无论它输出何种 vendor event，都必须先转换为统一 `AssistantStreamEvent`。

本规格不使用现有 OpenClaw 桥接事件名作为核心协议状态。目标是：

- OpenClaw / 小米模型 / 其他供应商输出都进入 `ModelProviderAdapter`。
- adapter 统一转换为 `AssistantStreamEvent`。
- 端侧只消费统一事件，不感知供应商协议。

### 4.4 对话体验指标

参考 Microsoft Copilot Studio、Google Assistant / Actions、主流 conversational UI 的分析体系，小趣必须从 M0 起预留可观测指标字段，后续用于持续改进体验。

核心指标分为六类：

- 参与度：会话数、活跃用户、主动入口点击率、主动消息打开率、连续追问率。
- 完成度：任务完成率、解决率、放弃率、升级人工/外部入口率。
- 效率：首 token 延迟、最终回答耗时、完成所需 turn 数、工具调用次数、设备上下文等待时间。
- 质量：答案有用率、groundedness、引用/证据覆盖率、工具失败率、fallback 率、重复追问率。
- 满意度：点赞/点踩、显式反馈、负反馈原因、会话后满意度。
- 主动体验：触达打开率、误报率、太频繁反馈率、静默忽略率、订阅留存率、取消订阅原因。

这些指标不作为独立业务对象进入 M0，但 `AssistantConversation`、`AssistantTurn`、`ToolUse`、`AppMessage` 必须保留可关联的 `traceId` / `eventId` / `sourceId`，确保后续可聚合分析。

## 5. 总体架构

### 5.1 云侧 Assistant Engine

云侧核心模块属于同一个 `assistant-service` 内部的功能组件，不在 M0 拆成多个独立微服务。拆独立服务会过早放大部署、事务、测试和观测复杂度；本阶段只要求模块边界清晰、接口可测、未来可拆。

云侧核心组件包括：

- `ConversationManager`
  - 管理连续对话、对话状态、活动 turn、记录 turn。
  - 承接用户主动交互和系统主动交互。

- `TurnRunner`
  - 创建用户主动 turn。
  - 创建系统主动 turn。
  - 管理 turn 状态、trace、artifacts、failure。

- `StreamProjector`
  - 提供用户主动发起时的流式输出。
  - 将云端执行事件转换为统一 `AssistantStreamEvent`。

- `AgentLoop`
  - 管理 turn 内回合推进、阶段状态、预算、重试、终止条件。

- `ReActRuntime`
  - 执行 `Reason -> Act -> Observe -> Assess -> Decide`。

- `SkillRuntime`
  - 加载 skill manifest、prompt asset、tool policy、dialogue 状态机。
  - 不写垂类业务逻辑。

- `ToolCoordinator`
  - 统一编排 Cloud Tool、Device Context Tool、Device Action Tool、Hybrid Tool。

- `ModelProviderAdapter`
  - 对接小米模型、OpenClaw 或其他模型供应商。
  - 将供应商 delta 转换为统一 stream event。

- `SkillSubscriptionService`
  - 管理主动式 skill 订阅。
  - M0 只保留最小配置，策略字段后续增强。

- `ProactiveScheduler`
  - 处理 cron、事件、阈值、冷却时间、每日上限。

- `AppMessageService`
  - 统一应用消息通道。
  - 协调 WebSocket、long polling、原生 push、站内 inbox。
  - M0 仅作为 `assistant-service` 内部适配组件验证契约；长期归属统一消息/通知基础能力。

- `AuditPolicyService`
  - 处理频控、免打扰、合规提示、金融免责声明、出行安全边界、审计日志。

### 5.2 端侧 Assistant Shell

端侧模块包括：

- `AssistantConversationPage`
  - 展示云端 stream journey。
  - 展示 partial answer、final answer、tool 状态、错误和继续追问。

- `AssistantSkillCenterPage`
  - 展示云端 Skill Catalog。
  - 管理我的订阅、推荐订阅、分类全量 Skill、搜索和排序。

- `SubscriptionManagement`
  - 创建、编辑、暂停、恢复、删除订阅。
  - 查看运行记录、触发原因和消息记录。

- `ConsentManagement`
  - 管理位置、日历、通知、设备状态、行程状态等授权。
  - 支持撤回、暂停、解释“为什么需要”。

- `DeviceContextAgent`
  - 维护设备侧上下文。
  - 上报当前可用事实。
  - 响应云端 Device Context Protocol 请求。

- `DeviceActionExecutor`
  - 执行打开页面、本地通知、分享、确认弹窗等本机动作。

- `AppMessageClient`
  - 接入统一应用消息通道。
  - App 活动时优先 WebSocket。
  - 弱连接或后台场景走 long polling / 原生 push / inbox。

### 5.3 端侧入口并行策略

实现阶段必须保持现有端侧“找小趣”入口不变，新增“找私助”入口承载云端优先架构验证。

策略：

- “找小趣”继续走当前端侧 `lib/assistant/` 引擎与现有页面链路，作为稳定回退入口。
- “找私助”走新的云端 `assistant-service`、统一 stream 协议、AppMessage、SkillSubscription 与 DeviceContext。
- 两个入口在 M4-M9 阶段并行存在，导航、埋点、实验分桶和反馈必须能区分来源。
- “找私助”完整通过 P0 Skill、主动消息、端云 stream、本地 fake mode、回归门禁后，才进入“找小趣”下线计划。
- 下线旧入口时不直接删除 `lib/assistant/`，先冻结为 current adapter / replay corpus 来源，再按功能模块迁移或归档。

验收要求：

- 新增“找私助”不得破坏现有“找小趣”路由、页面、会话和本地测试。
- 新入口必须使用云端 typed stream，不复用端侧 AgentLoop 推进主链路。
- 两个入口产生的观测事件必须带不同入口来源常量，常量来自 route / surface metadata。
- 用户可在测试期清楚识别当前使用的是“找小趣”还是“找私助”。

### 5.4 端云工程目录定义

工程目录遵守现有端云 DDD、metadata-first、Repository 三层模式与 runtime 统一能力约束。实际创建新服务目录必须通过 `/qwq-extend new-service`，禁止手动 `mkdir services/{name}`。

#### 5.4.1 Metadata 与 Codegen

```text
quwoquan_service/contracts/metadata/
├── assistant/
│   ├── assistant_conversation/
│   │   ├── entity.yaml
│   │   ├── fields.yaml
│   │   ├── service.yaml
│   │   ├── errors.yaml
│   │   └── tests/
│   ├── assistant_turn_envelope/
│   │   ├── schema.yaml
│   │   ├── service.yaml
│   │   ├── errors.yaml
│   │   └── tests/
│   ├── skill_subscription/
│   │   ├── entity.yaml
│   │   ├── fields.yaml
│   │   ├── service.yaml
│   │   ├── errors.yaml
│   │   └── tests/
│   ├── device_context/
│   │   ├── schema.yaml
│   │   ├── service.yaml
│   │   └── tests/
│   ├── tool_use/
│   │   ├── schema.yaml
│   │   ├── errors.yaml
│   │   └── tests/
│   ├── assistant_stream_event/
│   │   ├── schema.yaml
│   │   └── tests/
│   └── test_fixtures/
├── notification/
│   └── app_message/
│       ├── entity.yaml
│       ├── fields.yaml
│       ├── service.yaml
│       ├── errors.yaml
│       └── tests/
└── _shared/
    ├── domain_taxonomy.yaml
    ├── tag_taxonomy.yaml
    └── runtime_failure.yaml
```

要求：

- `assistant_*` 对象归属 assistant 域。
- `AppMessage` 归属统一 notification / message 基础域，不归 assistant 私有。
- `domain_taxonomy.yaml` 与 `tag_taxonomy.yaml` 是 Skill 分类唯一真相源。
- Dart/Go 产物分别输出到 `quwoquan_app/lib/cloud/runtime/generated/assistant/`、`quwoquan_app/lib/cloud/runtime/generated/notification/` 与 `quwoquan_service/generated/assistant/`、`quwoquan_service/generated/notification/`。

#### 5.4.2 云侧 Runtime 公共目录

```text
quwoquan_service/runtime/
├── id/
│   ├── generator.go
│   ├── prefix_registry.go
│   └── idempotency.go
├── errors/
│   ├── runtime_failure.go
│   ├── response.go
│   └── mapper.go
├── clock/
│   ├── clock.go
│   └── fake_clock.go
├── stream/
│   ├── envelope.go
│   ├── sse.go
│   ├── websocket.go
│   └── resume_token.go
└── testing/
    ├── fixture_loader.go
    ├── roundtrip.go
    ├── fake_transport.go
    └── fake_model.go
```

要求：

- assistant-service 只能调用 runtime 能力，不得自建 ID、错误、时钟、stream envelope。
- `runtime/testinfra` 只放跨服务可复用测试替身；业务 fixture 放回对应 metadata `tests/` 或 `test_fixtures/`。
- runtime 能力先在 M1 落地，再进入 assistant-service 主链路。

#### 5.4.3 云侧 Assistant Service

```text
quwoquan_service/services/assistant-service/
├── cmd/api/main.go
├── internal/
│   ├── domain/
│   │   ├── conversation/
│   │   │   ├── conversation.go
│   │   │   ├── turn.go
│   │   │   ├── repository.go
│   │   │   └── events.go
│   │   ├── skill/
│   │   │   ├── subscription.go
│   │   │   ├── catalog.go
│   │   │   └── repository.go
│   │   └── tool/
│   │       ├── tool_use.go
│   │       ├── tool_result.go
│   │       └── registry.go
│   ├── application/
│   │   ├── conversation_service.go
│   │   ├── turn_runner.go
│   │   ├── stream_projector.go
│   │   ├── agent_loop.go
│   │   ├── react_runtime.go
│   │   ├── skill_runtime.go
│   │   ├── tool_coordinator.go
│   │   ├── subscription_service.go
│   │   └── proactive_scheduler.go
│   ├── adapters/
│   │   ├── http/
│   │   │   ├── conversation_handler.go
│   │   │   ├── turn_handler.go
│   │   │   ├── stream_handler.go
│   │   │   ├── subscription_handler.go
│   │   │   └── device_context_handler.go
│   │   ├── stream/
│   │   │   └── sse_adapter.go
│   │   └── mq/
│   │       └── proactive_trigger_consumer.go
│   └── infrastructure/
│       ├── persistence/
│       │   ├── conversation_repo.go
│       │   ├── turn_repo.go
│       │   └── subscription_repo.go
│       ├── model/
│       │   ├── provider_adapter.go
│       │   ├── fake_provider.go
│       │   └── xiaomi_provider.go
│       ├── tools/
│       │   ├── search_tool.go
│       │   ├── news_tool.go
│       │   ├── market_tool.go
│       │   ├── weather_tool.go
│       │   └── map_tool.go
│       ├── appmessage/
│       │   └── app_message_client.go
│       └── migration/
├── tests/
│   ├── testmain_test.go
│   ├── fixture_test.go
│   ├── conversation_contract_test.go
│   ├── stream_contract_test.go
│   ├── subscription_contract_test.go
│   └── tool_contract_test.go
├── configs/
│   ├── config.yaml
│   ├── alpha/config.yaml
│   ├── beta/config.yaml
│   ├── gamma/config.yaml
│   ├── prod-gray/config.yaml
│   └── prod/config.yaml
├── go.mod
└── Makefile
```

要求：

- `domain/` 只表达业务对象、状态机、领域事件和 Repository 接口。
- `application/` 负责用例编排、事务边界、AgentLoop、ReAct、SkillRuntime 与 ToolCoordinator。
- `adapters/` 只处理 HTTP、stream、MQ 边界，不直接访问数据库。
- `infrastructure/` 放模型供应商、外部工具、持久化、AppMessage 客户端等实现。
- `appmessage/` 在 M3-M9 可作为 adapter 存在；长期统一消息服务落地后只保留客户端，不拥有消息真相源。
- 配置目录与运行时环境一一对应：`APP_ENV=alpha|beta|gamma|prod-gray|prod` 只读取同名 `configs/{env}/config.yaml`，禁止通过旧 `local` / `integration` 目录做兼容映射。

#### 5.4.4 云侧统一消息服务目标目录

```text
quwoquan_service/services/notification-service/
├── cmd/api/main.go
├── internal/
│   ├── domain/
│   │   └── appmessage/
│   │       ├── app_message.go
│   │       ├── repository.go
│   │       └── events.go
│   ├── application/
│   │   ├── app_message_service.go
│   │   ├── delivery_service.go
│   │   └── inbox_service.go
│   ├── adapters/
│   │   ├── http/app_message_handler.go
│   │   ├── stream/ws_handler.go
│   │   └── mq/message_event_consumer.go
│   └── infrastructure/
│       ├── persistence/app_message_repo.go
│       ├── push/native_push_provider.go
│       ├── stream/ws_hub.go
│       └── polling/long_poll_store.go
└── tests/
```

要求：

- M3 可先不创建独立服务，但目录目标必须按统一消息域设计。
- assistant、chat、circle、content、system 都只能创建 `AppMessage`，不得直接选择 WebSocket、long polling 或原生 push。
- 如果仓库已有 notification 域服务，应优先扩展既有服务，不新增平行服务名。

#### 5.4.5 端侧云服务与 Runtime

```text
quwoquan_app/lib/cloud/
├── runtime/
│   ├── generated/
│   │   ├── assistant/
│   │   │   ├── assistant_conversation_dto.g.dart
│   │   │   ├── assistant_turn_envelope_dto.g.dart
│   │   │   ├── skill_subscription_dto.g.dart
│   │   │   ├── device_context_dto.g.dart
│   │   │   ├── tool_use_dto.g.dart
│   │   │   └── assistant_stream_event_dto.g.dart
│   │   └── notification/
│   │       └── app_message_dto.g.dart
│   ├── cloud_runtime_config.dart
│   ├── cloud_request_headers.dart
│   ├── cloud_response_decoder.dart
│   └── runtime_failure_mapper.dart
└── services/
    ├── assistant/
    │   ├── assistant_repository.dart
    │   ├── assistant_stream_client.dart
    │   └── mock/
    │       └── assistant_mock_data.dart
    └── notification/
        ├── app_message_repository.dart
        ├── app_message_stream_client.dart
        └── mock/
            └── app_message_mock_data.dart
```

要求：

- Repository 必须保持 Abstract / Mock / Remote 三层模式。
- Remote 必须使用 metadata 生成的 path、operation、surface 常量与统一 header builder。
- UI 不得 import `cloud/services/*/mock/`。
- `app_providers.dart` 注册 `assistantRepositoryProvider`、`appMessageRepositoryProvider` 与数据源切换。

#### 5.4.6 端侧 UI 与 Current 隔离

```text
quwoquan_app/lib/ui/assistant/
├── pages/
│   ├── assistant_tab_page.dart
│   ├── assistant_conversation_page.dart
│   ├── assistant_skill_center_page.dart
│   ├── assistant_management_page.dart
│   ├── find_personal_assistant_page.dart
│   └── personal_assistant_conversation_page.dart
├── providers/
│   ├── assistant_conversation_controller.dart
│   ├── personal_assistant_stream_controller.dart
│   ├── skill_subscription_controller.dart
│   └── app_message_controller.dart
├── widgets/
│   ├── message/
│   ├── skill/
│   └── app_message/
└── models/
    ├── assistant_journey_view_model.dart
    ├── skill_subscription_view_model.dart
    └── app_message_view_model.dart

quwoquan_app/lib/assistant/
└── current client-side engine remains during migration
```

要求：

- 现有“找小趣”页面继续复用 `assistant_conversation_page.dart` 与 `lib/assistant/` 旧链路。
- 新“找私助”页面使用 `personal_assistant_*` controller 和云端 Repository / stream client。
- 新页面如进入扫描范围，必须同步更新页面横向质量矩阵和 PR checklist。
- `lib/assistant/` 在迁移期只作为 current、本地 replay、对照测试来源；新主动式业务不得继续向其中新增主链路能力。

## 6. 核心业务对象

### 6.0 ID 与请求上下文

#### ID 生成机制

M0 要求所有核心对象使用 `runtime/id` 统一能力生成 ID：同一套算法、不同业务前缀。ID 生成不应由 assistant-service 自行实现，也不应散落在端侧或各业务服务中。

建议格式：

```text
{prefix}_{ulid}
```

前缀建议：

- `acv_`：`AssistantConversation`
- `atn_`：`AssistantTurn`
- `sub_`：`SkillSubscription`
- `dcx_`：`DeviceContext`
- `tu_`：`ToolUse`
- `msg_`：`AppMessage`

要求：

- ID 由服务端通过 `runtime/id` 生成，端侧临时草稿 ID 不得作为最终业务 ID。
- ULID 或等价有序随机 ID 必须全局唯一、可按时间大致排序。
- 不在 ID 中拼接 userId、skillId、日期等业务语义，避免泄露与迁移困难。
- 不同对象通过前缀区分，生成算法保持一致。
- 幂等创建接口必须支持 `clientRequestId` 或等价幂等键，但它不是业务主键。

#### ClientContext

`ClientContext` 不是业务对象，而是所有端云请求都应携带的公共请求上下文，用于统计、灰度、风控、排障和基础个性化。

M0 字段：

- `deviceId`
- `platform`
- `appVersion`
- `buildNumber`
- `locale`
- `timezone`
- `deviceBrand`
- `deviceModel`
- `region`
  - `country`
  - `province`
  - `city`

要求：

- `ClientContext` 随请求进入，不作为长期业务实体单独存储。
- `region` 使用省市等粗粒度地理信息，不包含精确坐标。
- 精确位置、日历、通知权限等需要用户授权的信息不放在 `ClientContext`，按需通过 `DeviceContext` 提供。
- 灰度与统计只依赖 `ClientContext` 的结构化字段，不解析 User-Agent 字符串。

### 6.1 AssistantConversation

表示一段连续小趣对话，是小趣最核心的业务对象。

M0 字段：

- `conversationId`
- `userId`
- `state`
  - `idle`
  - `running`
  - `paused`
  - `archived`
- `activeTurnId`
- `lastTurnId`
- `summary`
- `createdAt`
- `updatedAt`

边界：

- `AssistantConversation` 承载连续状态，不承载每次执行的大型产物。
- 用户主动发起和系统主动触达都必须进入 conversation。
- `state` 只表达对话整体是否可继续交互，不表达某次执行的细节等待态。
- 设备上下文等待、用户确认、工具执行等细节状态放在 `AssistantTurn.status`。

示例：

```json
{
  "conversationId": "acv_01HX7F4J9W8Q2Y6N3P0S5R1T2V",
  "userId": "u123",
  "state": "running",
  "activeTurnId": "atn_01HX7F4K3BQ2Y6N3P0S5R1T2W",
  "lastTurnId": "atn_01HX6Z9K7AQ2Y6N3P0S5R1T2X",
  "summary": "用户正在规划五一杭州出行，并开启天气与路况提醒。",
  "createdAt": "2026-04-28T14:10:00Z",
  "updatedAt": "2026-04-29T00:40:00Z"
}
```

填写要求：

- `conversationId` 必须稳定，可跨端恢复，不随单次 turn 改变。
- `state` 只能来自枚举，禁止由用户可见文本推断；M0 只保留对交互入口有直接影响的状态。
- `summary` 是结构化摘要的展示/召回辅助，可为空，不作为状态判断依据。
- 页面来源、当前页面状态、设备环境不放在 conversation 主体，放入 turn 请求的 `ClientContext` 或按需补充的 `DeviceContext`。

业务能力：

- 创建或恢复用户的连续助手对话。
- 记录当前活动 turn 和最近完成 turn。
- 为端侧提供可继续追问、暂停、归档的会话入口。
- 为系统主动触达提供可追溯的对话容器。

应用场景规则：

- 用户第一次打开助手时，可创建个人 `AssistantConversation`。
- 用户点开主动提醒时，必须进入对应 conversation，而不是创建孤立详情页。
- 群聊或圈子场景后续可创建绑定业务目标的 conversation，但 M0 可先覆盖个人 conversation。
- archived conversation 只读，不再接收新 turn。

接口：

- `POST /assistant/conversations`
- `GET /assistant/conversations/{conversationId}`
- `GET /assistant/conversations`
- `PATCH /assistant/conversations/{conversationId}`，仅允许更新 `state=archived`

### 6.2 AssistantTurn

表示连续对话中的一次交互轮次。

用户主动提问、系统主动提醒、订阅触发、群内小趣发言，都统一为 `AssistantTurn`。

M0 字段：

- `turnId`
- `conversationId`
- `turnType`
  - `user_initiated`
  - `proactive`
  - `system`
  - `replay`
- `status`
  - `created`
  - `running`
  - `waiting_user_confirmation`
  - `completed`
  - `failed`
  - `cancelled`
- `skillId`
- `domainId`
- `input`
- `trigger`
- `streamState`
- `failure`
- `traceId`
- `createdAt`
- `completedAt`

枚举定义：

- `turnType`
  - `user_initiated`：用户主动输入创建。
- `proactive`：订阅或定时触发创建；事件触发后续扩展。
  - `system`：系统内部治理、补偿或迁移创建。
  - `replay`：测试、回放或评估创建，不进入真实用户消息通道。
- `status`
  - `created`：turn 已创建但未开始执行。
  - `running`：云端正在执行 AgentLoop 或工具链路。
  - `waiting_user_confirmation`：云端等待用户确认本机动作或敏感操作。
  - `completed`：turn 已完成，可继续创建下一个 turn。
  - `failed`：turn 失败，`failure` 必须为 runtime failure。
  - `cancelled`：用户或系统取消，不能继续执行。

与 `AssistantConversation.state` 的关系：

- `AssistantConversation.state` 表达整段对话是否可交互。
- `AssistantTurn.status` 表达一次执行的细节阶段。
- 当 active turn 为 `running` / `waiting_user_confirmation` 时，conversation 通常为 `running`。
- 当 turn 进入 `completed` / `failed` / `cancelled` 后，conversation 可回到 `idle` 或保持 `paused` / `archived`。

边界：

- `AssistantTurn` 是执行轮次，不是连续对话本身。
- 主动提醒不是孤立通知，必须挂在某个 turn 上。
- 大型工具结果和证据进入 artifacts / references，不塞入 turn 主体。

示例：

```json
{
  "turnId": "atn_01HX7F4K3BQ2Y6N3P0S5R1T2W",
  "conversationId": "acv_01HX7F4J9W8Q2Y6N3P0S5R1T2V",
  "turnType": "proactive",
  "status": "running",
  "skillId": "travel.companion",
  "domainId": "travel",
  "input": {
    "kind": "trigger",
    "text": "景区拥堵与天气变化检查"
  },
  "trigger": {
    "type": "cron",
    "source": "skill_subscription",
    "subscriptionId": "sub_01HX7A1K3BQ2Y6N3P0S5R1T2Y"
  },
  "streamState": {
    "lastSeq": 12,
    "completed": false
  },
  "traceId": "trc_9f1",
  "createdAt": "2026-04-29T00:40:00Z"
}
```

填写要求：

- `turnType` 表达发起来源，不表达业务分类。
- `status` 驱动端云协同，禁止通过模型自然语言判断是否完成。
- `input` 与 `trigger` 必须结构化；自然语言只能作为字段值，不能作为控制协议。
- `failure` 必须是 runtime failure，不允许纯字符串。

业务能力：

- 承接用户主动输入或系统主动触发的一次交互。
- 驱动云端 AgentLoop、工具调用、设备上下文请求和最终回答。
- 产生可流式消费的 `AssistantStreamEvent`。
- 作为主动消息、工具结果、错误和审计的关联根。

应用场景规则：

- 用户发问创建 `user_initiated` turn。
- 订阅触发创建 `proactive` turn。
- 内部回放和测试创建 `replay` turn，但不得进入真实用户 inbox。
- turn 完成后可继续创建下一个 turn，不能复用已完成 turn 继续执行。

接口：

- `POST /assistant/conversations/{conversationId}/turns`
- `POST /assistant/conversations/{conversationId}/turn-streams`
- `GET /assistant/turns/{turnId}`
- `GET /assistant/turns/{turnId}/events`
- `PATCH /assistant/turns/{turnId}`，仅允许更新 `status=cancelled`

### 6.3 SkillSubscription

表示用户、群或圈子对某个 Skill 的一条主动订阅。

M0 字段：

- `subscriptionId`
- `owner`
  - `type`
  - `id`
- `createdByUserId`
- `skillId`
- `domainId`
- `tagRefs`
- `status`
  - `active`
  - `paused`
  - `needs_consent`
  - `archived`
- `searchQueryPlan`
- `trigger`
- `destination`
- `createdAt`
- `updatedAt`

边界：

- 订阅是一组可理解配置，不是简单 enabled 开关。
- M0 不把免打扰、授权、风险等策略项做成必选字段。
- 权限、风险、免打扰后续进入策略层或增强字段。
- 分类必须引用 taxonomy，不允许自由字符串。
- 用户可用自然语言描述关注主题，但服务端必须保存原文和结构化搜索关键词计划，后续执行只读结构化字段。
- 定时调度统一使用 `trigger`，不能为每类 Skill 自造一套 schedule 字段。

枚举定义：

- `owner.type`
  - `user`
  - `conversation`
  - `circle`
- `status`
  - `active`
  - `paused`
  - `needs_consent`
  - `archived`
- `trigger.type`
  - `cron`
- `destination.type`
  - `user`
  - `conversation`
  - `circle`

示例：

```json
{
  "subscriptionId": "sub_01HX7A1K3BQ2Y6N3P0S5R1T2Y",
  "owner": {
    "type": "user",
    "id": "u123"
  },
  "createdByUserId": "u123",
  "skillId": "finance.stock_sentinel",
  "domainId": "finance",
  "tagRefs": ["topic_stock", "topic_company_news"],
  "status": "active",
  "searchQueryPlan": {
    "rawText": "帮我关注苹果和特斯拉的财报、监管和重大消息",
    "queries": [
      "AAPL earnings regulatory major news",
      "TSLA earnings regulatory major news",
      "苹果 特斯拉 财报 监管 重大消息"
    ]
  },
  "trigger": {
    "type": "cron",
    "cron": "0 21 * * *"
  },
  "destination": {
    "type": "user",
    "id": "u123"
  },
  "createdAt": "2026-04-29T00:10:00Z",
  "updatedAt": "2026-04-29T00:10:00Z"
}
```

填写要求：

- `skillId` 指向 Skill Catalog，不内嵌 Skill 定义。
- `domainId` / `tagRefs` 必须引用共享 taxonomy。
- `searchQueryPlan.rawText` 保留用户订阅时的自然语言原文。
- `searchQueryPlan.queries` 是模型或规则生成的检索关键词列表，M0 先采用搜索关键词方式，不建复杂实体体系。
- 后续触发判断只读 `searchQueryPlan.queries` 与 `trigger` 等结构化字段，不解析 `rawText`。
- `trigger.type` M0 仅支持 `cron`；事件触发在主动订阅调度阶段再扩展。
- `trigger.cron` 使用标准 cron-like 表达。
- `destination` 指向消息目标，不代表实际传输通道。

业务能力：

- 保存用户、群或圈子对一个 Skill 的主动订阅配置。
- 支持自然语言订阅意图到搜索关键词计划的转换。
- 为调度器提供最小 cron trigger。
- 为主动 turn 提供订阅来源和消息目标。

应用场景规则：

- 用户可以说“帮我每天晚上总结 AI 和芯片新闻”，系统保存原文并生成搜索关键词与 cron。
- 用户可以说“关注苹果和特斯拉重大消息”，系统保存原文并生成多条搜索关键词。
- `rawText` 只用于回显和重新解析，不用于运行时触发判断。
- 暂停订阅不删除记录 turn 和 AppMessage。

接口：

- `POST /assistant/skill-subscriptions`
- `GET /assistant/skill-subscriptions`
- `GET /assistant/skill-subscriptions/{subscriptionId}`
- `PATCH /assistant/skill-subscriptions/{subscriptionId}`
- `PATCH /assistant/skill-subscriptions/{subscriptionId}/status`

### 6.4 DeviceContext

表示设备侧可提供的上下文与能力状态。

M0 仅表达“端侧当前能按授权补充哪些动态上下文”。基础设备、应用版本、品牌、粗粒度地区等所有请求都需要的信息放在 `ClientContext`，不放在 `DeviceContext`。

M0 字段：

- `deviceContextId`
- `userId`
- `deviceId`
- `updatedAt`
- `capabilities`
- `facts`
  - `coarseLocation`
  - `surface`

针对某次 turn 的上下文补充使用 `DeviceContextResponse`，不需要另建顶层业务实体。

边界：

- 不上传全量隐私原文。
- 只传判断需要的事实。
- `capabilities` 只表达端侧是否可提供某类上下文，不表达复杂授权策略。
- 云端可以请求补充上下文，但不能假设端侧一定可用。
- 设备状态、网络状态、前后台状态、权限明细等字段不进入 M0，除非已有明确交互设计需要。

示例：

```json
{
  "deviceContextId": "dcx_01HX7F4M9W8Q2Y6N3P0S5R1T2Z",
  "userId": "u123",
  "deviceId": "d456",
  "updatedAt": "2026-04-29T00:42:00Z",
  "capabilities": ["surface", "coarse_location"],
  "facts": {
    "coarseLocation": {
      "country": "CN",
      "province": "浙江",
      "city": "杭州"
    },
    "surface": {
      "surfaceId": "assistant.home",
      "state": "visible"
    }
  }
}
```

填写要求：

- `facts` 只存最小事实，不存原始通讯录、日历正文、相册、聊天全文等隐私原文。
- `coarseLocation` 只表达粗粒度省市，不表达精确坐标。
- `surface` 只表达当前可见业务 surface，不记录 route 栈和 UI 细节状态。
- 云端使用前必须检查 `capabilities` 是否包含对应上下文。
- 缺失上下文应返回结构化 unavailable / denied / stale，而不是抛裸异常。

业务能力：

- 向云端报告当前请求可用的端侧动态上下文能力。
- 在 turn 执行期间响应云端补充上下文请求。
- 为出行、每日助手等场景提供粗粒度位置和当前 surface。

应用场景规则：

- `ClientContext` 随每个请求携带；`DeviceContext` 只在需要动态上下文时提供。
- 云端请求端侧上下文时必须给出 `capabilities` 和 `reason`。
- 端侧可以返回 denied / unavailable / stale，云端必须继续结构化降级。
- M0 不做持续后台定位，不做长期设备状态追踪。

接口：

- `POST /assistant/device-context`
- `POST /assistant/turns/{turnId}/device-context-response`

### 6.5 ToolUse

表示一次标准工具请求，对齐 Claude Code 等 Agent 体系的 `tool_use` 语义。

建议字段：

- `toolUseId`
- `turnId`
- `toolName`
- `placement`
  - `cloud`
  - `device_context`
  - `device_action`
  - `hybrid`
- `input`
- `status`
  - `requested`
  - `confirmed`
  - `running`
  - `succeeded`
  - `failed`
  - `cancelled`
- `requiresConfirmation`
- `result`
- `failure`
- `createdAt`
- `completedAt`

边界：

- `ToolUse` 是工具请求；`ToolResult` 是其结果，不单独作为顶层对象。
- Tool 编排由云端统一完成。
- 云端不能直接执行本机动作，只能下发 action proposal。
- Tool failure 必须统一映射为 runtime failure。

示例：

```json
{
  "toolUseId": "tu_001",
  "turnId": "atn_20260429_0001",
  "toolName": "web.search",
  "placement": "cloud",
  "input": {
    "query": "AAPL earnings latest regulatory news",
    "freshness": "day"
  },
  "status": "succeeded",
  "requiresConfirmation": false,
  "result": {
    "kind": "tool_result",
    "summary": "找到 3 条相关新闻。",
    "artifactRef": "art_web_search_001"
  },
  "createdAt": "2026-04-29T00:40:02Z",
  "completedAt": "2026-04-29T00:40:05Z"
}
```

填写要求：

- `toolName` 必须来自工具目录，不允许模型自由造工具名。
- `input` 必须符合该工具 schema。
- `placement=device_action` 时必须经过端侧确认或权限检查。
- `result` 中大内容只存引用，避免膨胀 turn。

业务能力：

- 表达模型请求调用某个工具的结构化意图。
- 记录工具执行状态、结果、失败和必要确认。
- 统一云端工具、端侧上下文工具、端侧动作工具。

应用场景规则：

- 网络搜索、新闻、行情等默认是 cloud tool。
- 端侧打开页面、本地通知等是 device action tool，必须先确认。
- 设备上下文补充可以作为 device context tool，也可以走 `DeviceContext` 协议；M0 优先走 `DeviceContext` 协议。
- 工具失败不能靠自然语言回填，必须形成 `ToolResult.failure`。

接口：

- `POST /assistant/turns/{turnId}/tool-uses`
- `POST /assistant/tool-uses/{toolUseId}/confirmations`
- `POST /assistant/tool-uses/{toolUseId}/result`
- `GET /assistant/tool-uses/{toolUseId}`

### 6.6 AppMessage

表示全 App 统一应用消息通道中的一条业务消息。

它不是助手私有送达对象，也不等于手机原生 push。原生 push、WebSocket、long polling 都只是投递方式。

服务归属：

- `AppMessage` 是 App 基础能力，不归助手私有。
- 长期应由统一消息/通知基础能力承接，优先评估并入已有 realtime gateway / notification 域；只有当现有域无法承接 inbox、ack、补偿拉取和多 transport 协调时，才通过 `/qwq-extend new-service` 创建独立 `app-message-service` 或 `notification-service`。
- M0 不要求立即创建独立微服务；可先在 `assistant-service` 内实现 adapter / contract fixture，用于验证助手主动消息的端云契约，但该 adapter 不拥有长期业务真相源。
- 一旦聊天、圈子、内容也接入该通道，必须从助手内部迁出到统一基础能力，避免助手服务变成全 App 通知中心。

建议字段：

- `messageId`
- `messageType`
  - `assistant`
  - `chat`
  - `circle`
  - `content`
  - `system`
- `source`
  - `assistant_turn`
  - `chat_message`
  - `circle_event`
  - `system_event`
- `sourceId`
- `destination`
  - `user`
  - `conversation`
  - `circle`
- `title`
- `summary`
- `target`
- `createdAt`
- `deliveredAt`

边界：

- 助手主动提醒写入 `AppMessage`。
- 聊天通知、圈子通知也写入 `AppMessage`。
- 手机原生 push 只负责唤醒或提示，不承载业务真相源。
- 用户点开消息后，由端侧统一消息路由分发到对应业务模块，不在消息中硬编码页面路径。

示例：

```json
{
  "messageId": "msg_001",
  "messageType": "assistant",
  "source": "assistant_turn",
  "sourceId": "atn_20260429_0001",
  "destination": {
    "type": "user",
    "id": "u123"
  },
  "title": "出行提醒",
  "summary": "你计划前往的景区 1 小时后可能拥堵，建议提前出发。",
  "target": {
    "targetType": "assistant_turn",
    "targetId": "atn_01HX7F4K3BQ2Y6N3P0S5R1T2W"
  },
  "createdAt": "2026-04-29T00:43:00Z"
}
```

填写要求：

- `source` / `sourceId` 是业务来源真相，必须可追溯。
- `destination` 是业务目标，不是传输方式。
- `target` 对齐端侧路由原则，只描述业务对象，不写页面 path。
- 端侧根据 `targetType` 查本地路由/处理器，类似 App Route metadata 的业务对象分发。
- 原生 push payload 只携带 `messageId` 和最小打开参数，完整内容从 AppMessage 拉取。

应用场景：

- 助手主动提醒：股票重大事件、出行提醒、每日助手复盘、新闻简报。
- 聊天消息通知：新消息、@我、群公告。
- 圈子通知：圈子活动、帖子互动、圈子摘要。
- 内容通知：评论、点赞、收藏、推荐摘要。
- 系统通知：账号、安全、治理、运营公告。

接口：

- `POST /app-messages`：由业务服务创建应用消息。
- `GET /app-messages`：按用户拉取站内消息列表。
- `GET /app-messages/{messageId}`：读取消息详情。
- `POST /app-messages/{messageId}/acks`：确认客户端已收到。
- `PATCH /app-messages/{messageId}/read-state`：标记已读。
- `GET /app-messages/stream`：活动态 WebSocket/SSE 消息流。

规则：

- 业务服务只创建 `AppMessage`，不直接控制 WebSocket、long polling、原生 push 的选择。
- 传输层根据用户在线状态、设备状态、系统能力选择 transport。
- 消息通道不理解助手业务细节，只按 `targetType` 分发。
- 每个业务模块必须注册自己支持的 `targetType`。

## 7. 对话状态驱动端云协同

端云协同由 `AssistantConversation.state` 和 `AssistantTurn.status` 共同驱动。

典型状态流：

```text
idle
-> running
-> waiting_user_confirmation
-> running
-> completed
```

端侧行为：

- `idle`：允许用户输入或管理订阅。
- `running`：展示云端 stream journey。
- `waiting_user_confirmation`：端侧展示确认面板，本机动作必须经确认。
- `completed`：展示最终答复，可继续追问。
- `paused` / `archived`：对话不可继续执行，但记录可查。

云端行为：

- 按状态推进 `AgentLoop`。
- 对高风险 action 发起 `user_confirmation_requested`。
- 对完成态产生最终 answer 或 `AppMessage`。

## 8. 核心协议

### 8.1 AssistantStreamEvent

端云流式交互统一事件信封。

建议字段：

- `schemaVersion`
- `conversationId`
- `turnId`
- `eventId`
- `eventType`
- `seq`
- `createdAt`
- `traceId`
- `payload`

事件类型：

- `conversation_state_changed`
- `turn_started`
- `understanding_updated`
- `journey_step_started`
- `journey_step_updated`
- `tool_use_requested`
- `tool_use_delta`
- `tool_result_received`
- `user_confirmation_requested`
- `partial_answer`
- `final_answer`
- `usage_updated`
- `turn_failed`
- `turn_completed`

要求：

- `seq` 在单个 turn stream 内递增。
- 端侧必须按 `turnId + seq` 去重。
- 错误必须使用 runtime failure，不返回裸字符串。
- 模型供应商 delta 不直接暴露给端侧。

### 8.2 用户主动 Turn Stream

端侧调用云端创建 turn 并消费流式输出。

接口建议：

- `POST /assistant/conversations/{conversationId}/turn-streams`
- `POST /assistant/turn-streams`，由云端自动创建或恢复 conversation。

请求包括：

- `userId`
- `conversationId`
- `input`
- `clientContext`
- `deviceContextRef`
- `preferredOutputMode`
- `traceHeaders`

响应：

- SSE 或 WebSocket。
- 事件格式为 `AssistantStreamEvent`。

验收要求：

- 用户主动提问必须走该协议。
- 端侧不推进本地 AgentLoop。
- 支持断线后根据 `turnId` 拉取记录 events。

### 8.3 Proactive Turn

系统主动触达先创建 `AssistantTurn`，再通过 `AppMessage` 投递。

内部链路：

```text
Trigger -> AssistantConversation -> AssistantTurn -> AppMessage -> WebSocket/LongPolling/NativePush/InApp
```

要求：

- 主动消息不要求端侧维持长连接。
- 主动 turn 完成后生成 `AppMessage`。
- 用户点开后能查看完整 journey、触发原因、证据和控制项。
- 主动消息必须能进入连续对话，用户可继续追问。

### 8.4 Device Context Protocol

端侧上下文同步协议。

接口建议：

- `POST /assistant/device-context`
- `POST /assistant/turns/{turnId}/device-context-response`

云端需要补充端侧上下文时，通过接口请求端侧返回 `DeviceContextResponse`。M0 不把设备上下文请求建模为 turn 状态。

请求字段包括：

- `requestId`
- `capabilities`
- `reason`
- `required`
- `expiresAt`

端侧响应：

- `granted`
- `denied`
- `unavailable`
- `stale`
- `deviceContextRef`

要求：

- 每次请求必须说明原因。
- 用户未授权时不能阻塞成不可解释状态。
- 高敏上下文必须最小化上传。

### 8.5 App Message Channel Protocol

统一应用消息通道协议。

接口建议：

- `GET /app-messages`
- `GET /app-messages/{messageId}`
- `POST /app-messages/{messageId}/acks`
- `PATCH /app-messages/{messageId}/read-state`
- `GET /app-messages/stream`，WebSocket 或 SSE。
- 原生 push payload 只携带 `messageId` 和最小 target 提示。

通道策略：

- App 活动：优先 WebSocket。
- WebSocket 不可用：退到 SSE 或 long polling。
- App 未启动或长期不活跃：通过原生 push 唤醒或提示。
- 所有重要消息落站内 inbox，可追溯、可补偿。

要求：

- 业务消息真相源是 `AppMessage`。
- 原生 push 不承载完整业务内容。
- 助手、聊天、圈子、内容都复用同一应用消息通道。

### 8.6 Provider Stream Adapter

云端内部模型供应商适配协议。

输入：

- 小米模型、OpenClaw 或其他模型的 token delta、tool call delta、reasoning delta、finish reason、usage、error。

输出：

- 统一 `AssistantStreamEvent`。

要求：

- 端侧不感知供应商协议。
- 切换模型不改变端云协议。
- usage、error、tool use 必须结构化。

## 9. Tool 端云分层规格

### 9.1 Cloud Tool

短期优先云端构建。

包括：

- 网络搜索。
- 新闻检索。
- 行情与财报。
- 天气。
- 地图路况。
- 内容检索。
- 圈子检索。
- 聊天检索。
- 知识库检索。

要求：

- 云端统一鉴权、缓存、重试、限流、审计。
- 主动式 Skill 只能依赖可云端稳定执行的 Tool 作为主路径。

### 9.2 Device Context Tool

端侧提供上下文，不负责业务执行。

包括：

- 位置可用性与粗粒度位置。
- 通知权限。
- 前后台状态。
- 网络状态。
- 设备状态。
- 本地日历授权摘要。
- 当前行程状态。

要求：

- 端侧主动上报或响应云端请求。
- 只上传最小事实。
- 用户可查看、暂停、撤回。

### 9.3 Device Action Tool

端侧执行本机动作。

包括：

- 打开页面。
- 本地通知。
- 系统分享。
- 本机确认弹窗。
- 跳转到设置或授权页。

要求：

- 云端只下发 action proposal。
- 端侧执行前做权限和用户确认。
- 执行结果回传云端。

### 9.4 Hybrid Tool

适用于出行、每日助手、会议准备等。

要求：

- 云端负责整体判断。
- 云端调用 Cloud Tool 获取外部事实。
- 端侧补充环境上下文。
- 最终建议由云端生成，端侧展示和执行动作。

## 10. Skill 分类与市场规格

### 10.1 分类同源

Skill 分类必须来自共享 taxonomy：

- `domainId` 指向 `domain_taxonomy.yaml`
- `tagRefs` 指向 `tag_taxonomy.yaml`
- 推荐理由可引用用户关注内容、圈子、话题、人物、行程、股票等。

### 10.2 Skill 页面 IA

端侧 Skill 页面重构为：

- 首页：搜索、我的订阅、推荐订阅、同源分类入口、热门 Skill。
- 我的订阅：运行中、暂停、待授权、异常。
- 推荐订阅：必须解释推荐原因。
- 分类全量：基于 taxonomy 展示和筛选。
- Skill 详情：能力、示例、权限说明、支持渠道。
- 订阅配置：关注对象、触发条件、送达方式、授权确认。

### 10.3 Skill Catalog M0 字段

M0 阶段只保留最小字段：

- `skillId`
- `displayName`
- `description`
- `domainId`
- `tagRefs`
- `examples`

市场评分、使用量、商业等级、触发器枚举、权限矩阵、风险等级等增强字段不进入 M0 必选范围，后续在 Skill Market 增强阶段补充。

## 11. M0 端云同源契约基线

M0 的目标不是实现完整云端助手，而是冻结后续所有实现必须遵守的端云契约、类型边界、状态机、错误模型和测试基线。

### 11.1 M0 冻结结论

当前仓库已有可复用基础：

- `contracts/metadata/assistant/assistant_turn/schema.yaml`
- `contracts/metadata/assistant/assistant_journey/schema.yaml`
- `contracts/metadata/assistant/run_artifacts/schema.yaml`
- `contracts/metadata/assistant/assistant_run/`
- `contracts/metadata/assistant/skill_consent/`
- `contracts/metadata/assistant/test_fixtures/`
- `quwoquan_app/lib/assistant/generated/`
- `quwoquan_service/generated/assistant/wirepoc/`

但它们还没有完整覆盖 M0 目标对象：

- `AssistantConversation`
- `AssistantTurn` 轮次信封
- `SkillSubscription`
- `DeviceContext`
- `ToolUse`
- `AppMessage`
- `AssistantStreamEvent`

其中需要特别区分：

- 现有 `assistant_turn/schema.yaml` 更接近模型回合输出契约，可作为 `AssistantTurn` 的结构化 payload 之一。
- M0 中的 `AssistantTurn` 是连续对话中的轮次信封，负责关联状态、输入、输出、工具、错误、stream、trace 和后续追问。
- 后续 metadata 落地时必须避免让“模型输出契约”和“对话轮次信封”混成一个对象。

### 11.2 强类型编码原则

M0 后所有新代码必须遵守以下原则：

- 禁止在业务编排层长期使用 `Map<String, dynamic>` / `dynamic` 作为状态载体。
- `Map` 只允许出现在 JSON 反序列化边界、fixture 读取边界和 codegen `fromJson` 内部。
- 反序列化后必须立即转换为 metadata/codegen 类型或明确的只读 view model。
- 禁止通过模型返回的自然语言文本做业务判断。
- 禁止通过 `contains`、`startsWith`、正则猜测模型意图、对话状态、工具调用、错误类型或最终答案类型。
- 模型必须输出结构化字段，代码只基于结构化字段推进状态。
- 用户可见话术来自 l10n、metadata、skill asset、prompt asset 或服务端结构化响应；禁止在业务逻辑里硬编码特定兜底话术。
- Tool 请求必须使用 `ToolUse`，Tool 结果必须使用 `ToolResult` 语义；禁止通过自然语言约定“模型说要调用某工具”。
- 对话状态必须由 `AssistantConversation.state` 和 `AssistantTurn.status` 驱动，不能由 UI 文本或模型文本推断。

允许的例外：

- codegen `fromJson` / `toJson`。
- 测试 fixture 构造。
- 明确标注的 current adapter，但 adapter 输出必须立刻转换为强类型契约。

### 11.3 模型主导与结构化执行原则

M0 后的执行链路必须遵守“模型主导、代码按结构化契约执行”：

1. 代码组装强类型上下文，生成模型输入。
2. 模型返回结构化输出，包括意图、下一步状态、工具请求、是否需要设备上下文、是否需要用户确认、最终回答。
3. 代码只读取结构化字段推进状态。
4. 如需工具，代码根据 `ToolUse` 调用工具并产生 `ToolResult`。
5. 如需端侧上下文，云端通过 Device Context Protocol 请求端侧返回 `DeviceContextResponse`。
6. 如需用户确认，云端发出 `user_confirmation_requested` 事件，端侧展示确认。
7. 最终回答通过 `final_answer` 结构化事件输出。

禁止路径：

- 根据模型自然语言里是否包含“我需要搜索”来调用搜索。
- 根据最终回答文本是否像 JSON 来决定是否隐藏或解析。
- 根据错误码字符串子串推导错误类型。
- 根据 UI 展示文案判断对话是否完成。

### 11.4 统一异常处理基线

M0 后所有端云边界错误必须统一为结构化 runtime failure。

要求：

- 云端服务边界使用 runtime errors / AppError 体系输出结构化错误。
- 端侧网络和云端错误统一映射为 `CloudException` / `RuntimeFailure`。
- `AssistantStreamEvent` 的失败事件必须携带结构化 `runtimeFailure`，禁止只携带 `errorMessage: string`。
- Tool 失败必须进入 `ToolResult.failure` 或 `ToolUse.failure`，并包含 runtime failure。
- Device context 拒绝、不可用、过期必须是结构化状态，不是异常字符串。
- App message 投递失败必须有结构化失败原因和可重试标记。
- 用户可见错误文案由错误码 metadata / l10n 映射，不在业务代码硬编码。

Runtime failure 至少包含：

- `code`
- `kind`
- `messageKey` 或可映射的 l10n key
- `recovery`
- `traceId`
- `context.attributes`

落实要求：

- M0 必须在 `contracts/metadata/assistant/**/errors.yaml` 或共享 runtime error metadata 中定义 assistant 相关错误码，禁止代码内新增错误码字符串。
- `assistant_stream_event` 的失败 payload 只能引用统一 `RuntimeFailure` 结构。
- `tool_use`、`device_context`、`app_message` 的失败字段必须复用同一 `RuntimeFailure` 结构。
- Dart/Go fixture 必须各包含一个 runtime failure 样例。
- 端侧展示文案通过错误码映射 l10n，不读取 `debugMessage` 作为用户文案。

### 11.5 M0 契约落地范围

M0 需要冻结以下 metadata 对象或 schema：

- `assistant_conversation`
  - 连续对话信封。
  - 定义 `state`、`activeTurnId`、`lastTurnId`、`summary`。

- `assistant_turn_envelope`
  - 对话轮次信封。
  - 关联现有 `assistant_turn` 输出契约、`assistant_journey`、`run_artifacts`、`ToolUse`、runtime failure。

- `skill_subscription`
  - 主动式 Skill 最小订阅配置。
  - 只包含 owner、skillId、domainId、tagRefs、status、searchQueryPlan、trigger、destination。

- `device_context`
  - 设备侧上下文与能力状态。
  - 定义 `capabilities` 与最小 `facts`。

- `tool_use`
  - 标准工具请求与结果。
  - 定义 `placement`、`status`、`input`、`result`、`failure`。

- `app_message`
  - 统一应用消息通道业务消息。
  - 支持 assistant、chat、circle、content、system。

- `assistant_stream_event`
  - 端云流式事件信封。
  - 支持 conversation state、turn、tool、device context、confirmation、answer、failure。

### 11.6 M0 反漂移约束

M0 冻结后，以下情况视为架构漂移：

- 新增端侧对象但没有 metadata 真相源。
- 云端和端侧分别定义同名 DTO。
- 新流式事件只在 Dart 或 Go 一侧出现。
- 用 `Map<String, dynamic>` 贯穿业务状态。
- 新增模型输出字段但没有 schema/codegen。
- 新增错误码但没有 `errors.yaml`。
- 新增 Skill 分类但没有引用共享 taxonomy。
- 新增主动消息但绕过 `AppMessage`。
- 新增工具调用但绕过 `ToolUse`。

### 11.7 M0 测试基线

M0 至少需要以下测试证据：

- T1：metadata verify 通过。
- T1：Dart codegen 产物生成并可编译。
- T1：Go wirepoc 或等价 Go 结构体 roundtrip 通过。
- T1：每个核心对象至少一个最小 JSON fixture。
- T1：`AssistantStreamEvent` 最小流 fixture 可被端侧和云侧解析。
- T1：runtime failure fixture 可被端侧和云侧解析。
- T2：端侧 stream projector 可基于 typed event 渲染最小 journey。
- T2：禁止弱类型和字符串判断的回归测试或静态扫描基线已定义。

## 12. 里程碑与验收标准

### M0：端云同源契约冻结

目标：冻结 M0 对象、协议、强类型边界、错误模型和 fixture，作为后续所有实现的唯一合同。

范围：

- 冻结核心对象：`AssistantConversation`、`AssistantTurn`、`SkillSubscription`、`DeviceContext`、`ToolUse`、`AppMessage`。
- 冻结 `ClientContext`、`AssistantStreamEvent`、Device Context Protocol、App Message Channel Protocol。
- 冻结 ID 前缀、状态枚举、trigger cron、target 分发模型。
- 定义 Dart/Go 共享 fixture 最小集。

验收标准：

- 文档中 M0 字段无未定义枚举、无临时自由字符串控制协议。
- 所有对象都能映射到 metadata/schema 任务。
- 强类型、禁止模型文本判断、统一 runtime failure 已写入 M0 准出。
- M1 可以直接按本章拆 metadata / codegen 任务。

### M1：Runtime 基础能力补齐

目标：在实现 assistant-service 前，先补齐跨服务可复用的 runtime 基础能力，避免 assistant 自建基础设施。

范围：

- `runtime/id`：统一 `{prefix}_{ulid}` 生成器、前缀注册、幂等键约束。
- `runtime/errors`：补齐 assistant/AppMessage/ToolUse 所需 RuntimeFailure 枚举映射与 fixture。
- `runtime/clock`：为 cron trigger、fake clock、测试调度提供统一时间源。
- `runtime/streaming`：在现有 SSE 基础上定义事件 envelope、seq、resume token 与测试传输替身；M1 不新增生产 WebSocket。
- `runtime/testinfra`：提供 fixture loader、fake transport、typed JSON roundtrip helper；fake clock 归属 `runtime/clock`。

验收标准：

- assistant 不直接实现 ID 生成、时钟、错误结构或 stream envelope。
- Dart/Go 均可消费 runtime ID/error/fixture 规则。
- fake clock 能在单测中稳定推进时间。
- runtime failure fixture 可被端侧和云侧解析。
- 新增 runtime 能力进入对应 `make test-contract` 或等价门禁。
- Go 侧结构化 RuntimeFailure 以 `runtime/failures` 为主；`runtime/errors` 作为 current HTTP `AppError` 边界继续通过 bridge 兼容。

### M2：Metadata / Codegen / Gate 基线

目标：把 M0 契约落到 metadata/codegen，并纳入本地门禁。

准入条件：

- M0 字段边界已冻结，新增字段必须回到 M0 评审。
- M1 中 `runtime/id`、`runtime/clock`、`runtime/streaming`、`runtime/testinfra` 至少具备最小接口或明确替身。
- `RuntimeFailure` 以 `runtime/failures` 为结构化来源，端云 fixture 不再使用裸字符串错误。
- 现有 `assistant_turn/schema.yaml` 保持模型输出契约定位，不被改造成对话轮次信封。

范围：

- 新增 assistant metadata schema：`assistant_conversation`、`assistant_turn_envelope`、`skill_subscription`、`device_context`、`tool_use`、`assistant_stream_event`。
- 新增 AppMessage 最小 schema。M2 可先以 assistant codegen/wirepoc 验证契约；M3 再迁入统一消息通道实现。
- 新增 M0 JSON fixture：每个核心对象至少一个最小样例，另有一条最小 stream 事件序列和一条 runtime failure 样例。
- 生成 Dart 类型；补 Go wirepoc 或等价 Go 类型 roundtrip。
- 增加弱类型 Map、字符串启发式判断、硬编码错误码的扫描或回归测试。

对象规格：

- `assistant_conversation`
  - 字段只覆盖连续对话信封：`conversationId`、`userId`、`state`、`activeTurnId`、`lastTurnId`、`summary`、`createdAt`、`updatedAt`。
  - 不承载消息列表、完整记忆、权限范围或 skill 配置。

- `assistant_turn_envelope`
  - 字段只覆盖轮次信封：`turnId`、`conversationId`、`turnType`、`status`、`skillId`、`domainId`、`input`、`trigger`、`streamState`、`failure`、`traceId`、`createdAt`、`completedAt`。
  - 可引用现有 `assistant_turn` 作为模型输出 payload，但不能复制其中大量推理字段。

- `skill_subscription`
  - M2 只支持 `trigger.type = cron`，不做事件触发、阈值、冷却、每日上限。
  - `searchQueryPlan` 只保留 `rawText` 与 `queries`。

- `device_context`
  - 只表达端侧当前可提供的 `capabilities` 与最小 `facts`。
  - 不做持续定位、权限矩阵、设备状态长记录。

- `tool_use`
  - 对齐 `ToolUse` / `ToolResult` 语义。
  - `failure` 必须复用 runtime failure 结构。

- `assistant_stream_event`
  - 统一端云流式事件信封，包含 `eventId`、`conversationId`、`turnId`、`seq`、`eventType`、`payload`、`runtimeFailure`、`createdAt`。
  - `payload` 只作为边界 JSON 容器；业务消费必须转成对应 typed 对象。

- `app_message`
  - M2 只冻结消息业务真相源最小字段：`messageId`、`messageType`、`source`、`sourceId`、`destination`、`title`、`summary`、`target`、`createdAt`、`deliveredAt`。
  - 不实现投递 transport、不做 inbox 策略、不做原生 push payload。

生成物：

- Dart 类型生成到 `quwoquan_app/lib/assistant/generated/contracts/` 或后续统一的 `quwoquan_app/lib/cloud/runtime/generated/assistant/`；M2 不手写 DTO。
- Go wirepoc 生成到 `quwoquan_service/generated/assistant/wirepoc/`，用于端云 fixture roundtrip。
- fixture 放在 `quwoquan_service/contracts/metadata/assistant/test_fixtures/`，AppMessage fixture 在 M2 可先随 assistant test fixture 验证，M3 再迁移到 notification 域测试。

验收标准：

- `make codegen-app` 生成端侧类型。
- Go/Dart 最小 fixture roundtrip 通过。
- 新增对象不需要手写第二套 DTO。
- M0 fixture 覆盖 runtime failure。
- 文档、metadata、fixture 三者字段一致。
- 新增 schema 不破坏现有端侧 `lib/assistant/` 旧链路 codegen。
- `assistant-service` 主链路、AppMessage transport、P0 Skill 业务逻辑仍不进入 M2。

任务拆解：

1. M2-S1：补规格与对象清单，确认 AppMessage 在 M2 的临时验证位置和 M3 的长期归属。
2. M2-S2：新增 M2 schema 与 fixture，保持现有 `assistant_turn` 语义不变。
3. M2-S3：扩展 assistant Dart codegen 与 Go wirepoc codegen。
4. M2-S4：新增 roundtrip 测试，覆盖最小 JSON、runtime failure、stream 事件序列。
5. M2-S5：运行 `verify-metadata`、`codegen-app`、wirepoc tests，并将结果写回集中验收证据。

### M3：统一应用消息通道基线

目标：先建立 `AppMessage` 基础能力，使助手主动消息不走私有通知路径。

准入条件：

- M1 已具备最小 `runtime/id`、`runtime/clock`、`runtime/streaming` 或等价替身。
- M2 已冻结 `app_message` 最小 schema 与 fixture。
- 现有 `notification/notification` 与 `realtime/connection` 已完成差距评估。

范围：

- 以现有 `notification/notification` 为 M3 AppMessage 的承载基础，优先扩展字段和接口，不另建助手私有消息对象。
- 以现有 `realtime/connection` 为投递通道基础，M3 只验证 typed stream / poll / fake transport，不实现完整 push 平台。
- 落地 `AppMessage` metadata、fixture、基础接口。
- M0/M3 过渡期可先在 `assistant-service` 内实现写入 adapter，但必须标明非长期归属。
- 明确 target 分发注册机制：`targetType -> handler`。
- 定义 create、list、detail、ack、read、unread-count、stream 的最小接口。
- fake transport 支持 WebSocket/SSE/long polling/native push 的测试替身。

字段收敛：

- `messageId` 对齐现有 `Notification._id`，对外统一暴露为 `messageId`。
- `messageType` 对齐现有 `Notification.type`，枚举至少覆盖 `assistant`、`chat`、`circle`、`content`、`system`。
- `destination` 在 M3 只支持 `user` destination；`conversation`、`circle` 留到 M10。
- `title`、`summary` 对齐现有 `title`、`body`，端侧展示不读取 transport payload。
- `target.targetType`、`target.targetId` 对齐现有 `targetType`、`targetId`。
- `read`、`readAt` 保留为 inbox 状态；`ack` 表达端侧已收到，不能替代已读。
- `deliveredAt` 可为空；M3 fake transport 可在测试中写入。

非目标：

- 不实现完整原生 push provider。
- 不实现跨设备复杂去重策略。
- 不实现 conversation / circle destination。
- 不实现主动订阅调度和 P0 Skill 内容生产。
- 不下线“找小趣”。

验收标准：

- 助手主动消息可写入 `AppMessage`。
- 端侧可根据 `targetType` 路由到业务处理器。
- 原生 push payload 不承载完整业务内容。
- fake transport 可稳定测试投递、ack、read。
- AppMessage 可迁移到统一消息/通知基础能力，不绑定助手内部模型。
- 现有通知列表、已读、未读数能力不回归。
- 端侧可通过 Repository mock/remote 两种模式读取 AppMessage。

### M4：Assistant Service Shell

目标：建立云端 `assistant-service` 外壳，先接管 conversation / turn / stream 的端云交互，不实现完整 AgentLoop。

范围：

- 创建或对齐 `assistant-service` 服务结构。
- 实现 conversation 创建/读取。
- 实现 turn 创建/读取。
- 实现 turn-streams：可返回 fake stream event。
- 端侧 remote entry 消费 typed stream event。
- 接入 runtime/id、runtime/errors、runtime/failures、runtime/streaming。

验收标准：

- App 可通过云端完成一次 fake 问答。
- 端侧只渲染 stream，不推进 AgentLoop。
- stream event 支持 seq 去重。
- `assistant-service` 进入 build / test-contract / gate。
- 本地 fake mode 不依赖真实模型。

### M5：端侧 Assistant 框架云侧等价迁移

目标：把端侧已验证的 `AgentLoop`、`ReActRuntime`、`SkillRuntime`、`ToolRuntime`、context / memory / template / projection / replay 主框架等价迁移到云端，让 `assistant-service` 能独立完成与端侧模拟器同等级的流式叙事、问题成答、journey、process timeline、runtime failure 与 replay 验证。

M5a 记录验证记录：

- 已完成的最小骨架验证只作为 `M5a`，证明云侧可以跑通 conversation -> turn -> stream -> AgentLoop -> ToolUse -> final answer。
- `TestAgentLoop_RunTurnStream_CompletesNarrativeAnswer`、`TestAgentLoop_RunTurnStream_ToolFailureReturnsRuntimeFailure`、`TestHandleTurnStream_M5AgentLoopEndToEnd`、`TestHandleTurnStream_M5ToolFailureReturnsRuntimeFailure` 已覆盖最小成功与失败链路。
- `M5a` 不等于 M5 准出；端侧完整框架未等价迁移前不得进入 M6。

准入条件：

- M4 的 conversation / turn / typed stream shell 已可运行。
- M5 主验收入口固定为 `POST /v1/assistant/turns/{turnId}/stream`。
- 旧 `POST /v1/assistant/runs` 与 `POST /v1/assistant/runs/stream` 只保留兼容，不作为 M5 准出主入口。
- “找小趣”旧入口不改；“找私助”只消费云侧 typed stream，不推进端侧 AgentLoop 主链路。

等价迁移能力矩阵：

| 端侧能力 | 云侧落点 | M5 准出证据 |
|---|---|---|
| `LocalAssistantEntry.runStream` | `application/entry` | 服务端 simulator 与 HTTP SSE 均输出 typed stream |
| `AssistantAgentLoop` 七阶段 | `application/orchestration` + `application/phases` | bootstrap / understand / retrieval-design / execution / evidence-digest / synthesis / finalize 顺序可断言 |
| `AssistantPipelineEngine` | `application/pipelines` | context、memory、domain route、template、answer gate 均进入 typed state |
| `ReactRuntime` | `application/reasoning` | planner、reflector、budget、replan、tool guard、assessor、truncator 均有 T2 测试 |
| `SkillLoader` / `SkillRouter` / `SkillExecutor` | `application/skill` + `infrastructure/assets` | 至少 3 个 skill fixture 可加载、路由、执行 |
| `AssistantToolRegistry` | `application/tool` + `infrastructure/tools` | 参数校验、输出校验、loop detection、retry/recovery、runtime failure 均可测 |
| `AssistantStreamingProjector` | `application/projection` | answer、trace、journey、timeline、completed、failed 事件均输出 |
| `AssistantJourneyProjector` | `application/projection` | replay fixture 可断言 journey stage |
| `AssistantProcessTimelineProjector` | `application/projection` | replay fixture 可断言 process timeline frame |
| `RunArtifacts` / replay trace | `domain/assistant` + simulator | 服务端 replay runner 输出 golden artifacts |
| `SwitchableAssistantLlmProvider` | `infrastructure/model` | fake provider 与 provider delta adapter 使用同一事件协议 |
| `DeviceContextAgent` 协同 | `application/context` + HTTP boundary | denied / unavailable / stale 可结构化降级 |
| observability / quality payload | `application/pipelines` | simulator 输出 observability payload，不依赖日志文本 |

M5 范围：

- 云端实现 `AssistantEngineFactory`，统一装配 model、skill、tool、context、template、memory、projection 与 fake/live profile。
- 云端实现七阶段 `PhaseOrchestrator`，每个 phase 输出 typed state、trace event 与 observability payload。
- 云端实现等价 `ReActRuntime`，支持 structured model delta、tool call delta、usage、finish reason、runtime failure、预算、重试、反思、replan 与终止条件。
- 云端实现 `SkillRuntime`，支持 `SKILL.md` / `.skill.yaml` manifest、tool-chain skill、knowledge QA skill、remotePreferred / hybrid 路由与 device action proposal。
- 云端实现 `ToolRegistry`，所有 `ToolUse` / `ToolResult` 全程结构化，禁止通过自然语言触发工具。
- 云端实现 stream / journey / process timeline / run artifacts / replay projection。
- 云端实现 simulator / replay runner，使用 fake model script、fake tool script、fake memory、fake device context 复现端侧模拟器级验证。

规范化事件序列：

- `conversation_state_changed`
- `turn_started`
- `understanding_updated`
- `journey_step_started`
- `journey_step_updated`
- `tool_use_requested`
- `tool_use_delta`
- `tool_result_received`
- `user_confirmation_requested`
- `partial_answer`
- `final_answer`
- `usage_updated`
- `turn_failed`
- `turn_completed`

兼容要求：

- HTTP SSE 可继续在 transport 层使用既有 `assistant.*` 事件名，但 payload 内 `AssistantStreamEvent.eventType` 必须使用上述规范化事件类型。
- `partial_answer` 与 `final_answer` 保留 `payload.text`，保证“找私助”Remote stream 可直接观察。
- 失败路径必须携带结构化 `runtimeFailure`，禁止只输出字符串错误。

验收标准：

- 云侧能独立运行端侧等价七阶段 AgentLoop。
- 云侧 simulator/replay runner 通过至少 3 类典型用例：直接问答、需要工具检索、工具失败降级。
- 云侧输出 answer、trace、journey、process timeline、run artifacts、runtime failure 与 observability payload。
- Skill manifest、tool registry、ReAct budget/replan/recovery 均有 T2 测试。
- Dart/Go 共享 replay fixture roundtrip 通过。
- “找私助”可观察完整云侧事件，“找小趣”旧入口无回归。
- 未完成项不得标记为 M6 后移；只能作为 M5 内后续子切片继续完成。

### M6：Tool Coordinator 与云端优先 Tool

目标：建立统一 Tool 编排，并优先云化可云化工具。

准入条件：

- M1 runtime 基础能力可用：`runtime/id`、`runtime/clock`、`runtime/streaming`、`runtime/failures`。
- M2 已生成 `ToolUse`、`AssistantStreamEvent`、`RuntimeFailure` 的 Dart/Go 契约与 fixture。
- M4/M5 已具备 `assistant-service` turn stream、AgentLoop、ReActRuntime、SkillRuntime 与 fake model 测试链路。
- “找私助”入口可消费云端 typed stream，“找小趣”旧入口保持不变。

范围：

- 定义 Tool catalog 与 ToolUse schema 绑定。
- Cloud Tool：M6 至少落地两个本地稳定 fake adapter，优先 `web_search` / `search` 与 `app_search`；新闻、行情、天气、地图可先进入 catalog 与 fixture，不依赖真实外部网络。
- Device Context：通过协议补充端侧上下文，不作为 turn 状态；M6 只定义 request/proposal 与 typed stream 事件，不做持续后台采集。
- Device Action：打开页面、本地通知、分享、确认等只由云端产生 action proposal，端侧确认后执行；M6 不允许云端直接执行本机动作。
- Planner 必须基于结构化模型输出、Skill `ToolPolicy` 与 Tool catalog 决策工具；禁止从自然语言文本推断工具调用。
- Tool failure 统一为 runtime failure。

非目标：

- 不做 M8 主动订阅调度。
- 不做 M9 P0 Skill 业务完整闭环。
- 不实现真实外部搜索、行情、天气供应商接入；真实 provider 进入后续 T3/T4 验收。
- 不下线“找小趣”旧入口。
- 不让端侧成为 Tool Coordinator，也不在端侧伪造云端工具结果。

Tool catalog 规则：

- Tool catalog 必须有唯一真相源，字段至少包括 `toolName`、`placement`、`inputSchema`、`outputSchema`、`requiresConfirmation`、`resilience`、`recovery`。
- 云侧 registry 必须从 catalog/metadata 映射出可执行工具元数据，不得长期只硬编码 `mock_search`。
- Skill `ToolPolicy.allowedTools` 是工具可用边界；模型结构化 `toolName` 只能在该边界内选择。
- `device_action` 工具必须 `requiresConfirmation = true`，执行前只产出 proposal。
- `device_context` 工具只请求上下文，不把 turn status 改成等待设备状态。

M6 事件要求：

- 工具请求输出 `tool_use_requested`。
- 工具成功输出 `tool_result_received`。
- 工具失败输出 `turn_failed` 或可恢复的 failure event，且携带 `runtimeFailure`。
- Device action proposal 输出 `user_confirmation_requested` 或等价 typed event，payload 必须包含 `ToolUse`。
- 所有事件继续通过 `AssistantStreamEvent` envelope 承载，transport 可继续使用现有 SSE 事件名。

验收标准：

- 云端可调用至少两个 Cloud Tool。
- ToolUse 输入输出均为强类型或 schema 校验对象。
- 云端不能越权执行本机动作。
- Tool failure 进入 ToolResult.failure。
- 不通过模型自然语言触发工具调用。
- 未注册工具、策略拒绝、缺少必填输入、输出不符合 schema、工具执行失败均映射为结构化 runtime failure。
- Replay fixture 至少覆盖：直接回答、cloud tool 成功、tool failure、device action proposal。
- `runner_test` 必须对 replay golden 的关键事件序列做断言，不能只验证事件非空。
- “找私助”可观察工具事件，“找小趣”旧入口无回归。

任务拆解：

1. M6-S1：刷新本规格，明确 M6 准入、非目标、Tool 分类、事件、验收和测试矩阵。
2. M6-S2：把 Tool catalog 映射到云侧 registry 元数据，至少包含 `mock_search`、`web_search`、`app_search`、`app_action`。
3. M6-S3：增强 ToolCoordinator，支持结构化 tool input、catalog placement、policy guard、confirmation proposal、runtime failure。
4. M6-S4：实现两个 cloud tool fake adapter，并保持本地测试不依赖真实外部网络。
5. M6-S5：实现 device action proposal 边界，确认逻辑只进入 stream/proposal，不在云端执行本机动作。
6. M6-S6：补齐 Tool registry、Coordinator、ReactRuntime、HTTP stream、replay golden 与 Dart contract 测试。
7. M6-S7：运行 `assistant-service` 相关 Go 测试、metadata/codegen 相关测试与必要端侧测试，回写验收证据。

### M7：端侧 Shell 与管理入口瘦身

目标：新增“找私助”入口，并让该入口从执行引擎收敛为 UX、上下文、管理和消息入口。

准入条件：

- M1-M6 的 runtime、metadata、assistant-service turn stream、AppMessage、ToolUse 基础能力已有可运行或可测试证据。
- 现有“找小趣”入口继续可用，`AssistantConversationPage` 与 `lib/assistant/` 端侧旧引擎不作为 M7 改造对象。
- “找私助”入口必须只消费云端 typed stream，不推进端侧 AgentLoop 主链路。
- 页面 route、surface、operation、request header 来源必须来自 metadata/codegen。

范围：

- 保留现有“找小趣”入口、路由和本地端侧引擎链路。
- 新增“找私助”入口、页面、Provider、Repository 与 stream client。
- 助手页展示云端 journey / final answer / runtime failure。
- 端侧提供 `ClientContext`。
- 按需提供 `DeviceContext`。
- Skill 中心展示云端 catalog 和订阅。
- AppMessageClient 接入消息列表、详情、stream。

非目标：

- 不下线“找小趣”入口。
- 不迁移 `AssistantHalfSheet` 到“找私助”。
- 不实现 M8 主动订阅调度。
- 不实现 P0 Skill 业务闭环。
- 不实现群聊/圈子 destination。

状态投影要求：

- `AssistantStreamEventWire.seq` 必须去重和按序消费。
- `partial_answer` 与 `final_answer` 只从 typed event payload 中读取展示文本，读取逻辑集中在 controller / projector，不散落在 UI。
- `turn_failed` 必须优先展示 `runtimeFailure` 映射文案，不展示裸 `debugMessage`。
- journey / tool / device context / confirmation 事件先以最小 typed timeline 展示，不能驱动端侧 AgentLoop。

管理入口要求：

- “找私助”页提供到 Skill Center 的入口。
- “找私助”页提供到 AppMessage / inbox 的最小入口或消息状态摘要。
- “找私助”页提供设备上下文用途说明和拒绝态提示。
- UI 只通过 `assistantRepositoryProvider`、`appMessageRepositoryProvider` 和对应 controller 取数，不直接 import mock。

验收标准：

- “找小趣”入口不回归，现有页面和测试继续可用。
- “找私助”入口可通过云端 fake stream 完成最小问答。
- 端侧不维护独立 skill 分类和订阅真相源。
- 端侧不基于模型文本判断状态。
- 端侧可通过 stub stream 测 journey 渲染。
- 用户能查看权限用途并拒绝上下文请求。
- 页面横向质量矩阵和 P2 清单与实际改动一致。
- `flutter test` 覆盖 mock stream 成功、runtime failure 失败、seq 去重和旧入口不回归。

任务拆解：

1. M7-S1：冻结本规格，明确准入、非目标、状态投影、管理入口和验收证据。
2. M7-S2：补齐“找私助” route / surface metadata 并生成端侧常量。
3. M7-S3：接入独立 route 与入口 UI，保持“找小趣”原链路不变。
4. M7-S4：收口 `PersonalAssistantStreamController`，集中处理 typed stream、runtime failure、seq 去重与 answer 投影。
5. M7-S5：接入 Skill/AppMessage/DeviceContext 最小管理入口。
6. M7-S6：补齐页面横向质量矩阵、P2 inventory、widget/provider 测试和最小门禁。

测试证据：

- T1：metadata/codegen 与页面矩阵检查通过。
- T2：controller/provider/widget 测试覆盖 success/failure/seq 去重。
- T3：RemoteAssistantRepository 可消费 assistant-service SSE fixture。
- T4：本地应用中“找小趣”与“找私助”并行入口均可识别，“找私助”可完成最小问答。

### M8：主动订阅与 Cron 调度中枢

目标：建立主动式小趣的最小可运行平台，M8 只支持 cron trigger，事件触发后续扩展。

准入条件：

- M1-M7 已具备进入 M8 的工程基础：runtime/id、runtime/clock、runtime/streaming、runtime/testinfra 可用。
- `assistant-service` 已支持 conversation、turn、typed stream、AppMessage 最小链路。
- 端侧“找私助”入口已存在，且“找小趣”入口保持不变。
- `SkillSubscription` M0/M2 schema 已存在，M8 只扩展 API、状态机、调度与端侧管理。

范围：

- 实现 `SkillSubscription` CRUD。
- 支持自然语言订阅转 `searchQueryPlan`。
- 支持 cron trigger + fake clock。
- cron 触发创建 proactive turn。
- 主动结果通过 `AppMessage` 投递。

状态机：

- `active`：订阅生效，可被 cron 调度。
- `paused`：用户暂停，不参与调度，记录 turn 与 AppMessage 保留。
- `archived`：用户归档，不参与调度，默认列表不展示。

M8 API：

- `GET /v1/assistant/skill-subscriptions`
- `POST /v1/assistant/skill-subscriptions`
- `GET /v1/assistant/skill-subscriptions/{subscriptionId}`
- `PATCH /v1/assistant/skill-subscriptions/{subscriptionId}/status`
- `POST /v1/assistant/skill-subscriptions/cron/tick`

M8 非目标：

- 不支持事件触发、阈值触发、冷却、每日上限。
- 不支持 conversation / circle destination。
- 不新增独立 scheduler worker 进程。
- 不下线“找小趣”入口。
- 不实现完整原生 push provider。

验收标准：

- 用户可创建、暂停、恢复、归档订阅。
- fake clock 可触发定时 turn。
- 主动 turn 生成 `AppMessage`。
- 用户点开消息可回到对应 conversation / turn。
- 多端不重复提醒。
- metadata、Go、Dart、fixture 字段一致。
- 端侧只通过 Provider / Repository 访问订阅，不直连 mock 数据。
- “找小趣”旧入口不回归。

测试证据：

- T1：metadata/codegen/fixture roundtrip 覆盖 `SkillSubscription`、cron due/not due、proactive AppMessage。
- T2：云侧 service 测试覆盖 CRUD、状态机、fake clock tick、幂等去重与 runtime failure。
- T2：端侧 Repository / Provider 测试覆盖列表、创建、暂停、恢复、归档与错误降级。
- T3：assistant-service contract test 覆盖 cron -> proactive turn -> AppMessage。
- T4：本地 fake mode 验证创建订阅、推进 fake clock、收到 AppMessage、点击回到“找私助” conversation / turn。

任务拆解：

1. M8-S1：冻结本规格，补齐 API、状态机、非目标与测试证据。
2. M8-S2：补 `SkillSubscription` service metadata、fixtures、Dart/Go codegen。
3. M8-S3：实现云侧订阅 CRUD、状态流转、store 与 HTTP handler。
4. M8-S4：实现 cron tick、fake clock、proactive turn、AppMessage 投递与幂等去重。
5. M8-S5：实现端侧订阅管理 Repository、Provider、UI 入口与 AppMessage 回跳。
6. M8-S6：补齐 T1-T4 测试与门禁证据。

### M9：P0 主动 Skill 落地

目标：用四个 P0 主动 Skill 验证平台闭环，把 M1-M8 的云端执行、cron 订阅、ToolUse、AppMessage 与“找私助”入口串成可验收业务体验。

准入条件：

- M1-M8 已具备可运行或可测试证据：runtime/id、runtime/clock、runtime/streaming、runtime/failures、metadata/codegen、assistant-service turn stream、ToolCoordinator、SkillSubscription、AppMessage、找私助入口。
- M8 已支持 `SkillSubscription` CRUD、`cron` tick、proactive turn、AppMessage 投递与端侧回跳。
- M9 不新增平台级 trigger、destination、transport 或后台 worker 能力。
- “找小趣”旧入口保持不变；M9 只增强“找私助”主动 Skill 体验。

范围：

- 每日助手。
- 新闻简报。
- 投资股票哨兵。
- 出行旅程管家。
- 四个 Skill 共用同一套 `SkillSubscription`、`AssistantConversation`、`AssistantTurn`、`AppMessage`。

M9 非目标：

- 不接入真实外部新闻、行情、天气、地图供应商作为主门禁依赖。
- 不支持事件触发、阈值触发、冷却、每日上限、群聊或圈子 destination。
- 不做自动交易、投资建议、订单操作、导航调度、支付或本机自动动作。
- 不下线“找小趣”入口。
- 不把四个 P0 Skill 做成独立业务服务；本阶段作为 `assistant-service` 内部 SkillRuntime / fake provider 验证。

四个 P0 Skill 最小规格：

- `daily_assistant`
  - 默认 cron：早间计划 `0 8 * * *`；晚间复盘可用另一条订阅表示。
  - 输入：用户关注的生活、工作、学习关键词。
  - 输出：今日计划、重点提醒、学习/作息建议、可追溯原因。
  - M9 fixture：待办、日程、学习计划、作息状态均为 fake facts。

- `news_briefing`
  - 默认 cron：`0 8 * * *`。
  - 输入：`searchQueryPlan.queries` 中的话题、人物、行业、地区。
  - 输出：摘要、来源要点、为什么提醒、继续追问建议。
  - M9 fixture：不依赖真实新闻网络，使用确定性新闻事实。

- `stock_sentinel`
  - 默认 cron：`0 9 * * *`。
  - 输入：股票代码、公司名、行业、消息面关键词。
  - 输出：重大信息摘要、可能影响维度、风险提示、非投资建议边界。
  - M9 fixture：模拟行情和重大消息；禁止输出买入/卖出/价格目标。

- `travel_journey_manager`
  - 默认 cron：`0 7 * * *`。
  - 输入：目的地、行程日期、交通、住宿、景点关键词。
  - 输出：天气/路况/拥堵/沿途说明摘要、风险提醒、可执行建议。
  - M9 fixture：模拟天气、交通、景点拥堵与沿途介绍；不执行订单或导航动作。

事件与消息规范：

- cron tick 命中订阅后创建 `turnType = proactive` 的 `AssistantTurn`。
- `AssistantTurn.skillId` 必须是四个 P0 Skill ID 之一。
- SkillRuntime 生成的主动结果必须包含 `why`、`evidence`、`nextActions` 三类结构化信息，写入 stream payload 或 AppMessage summary 可追溯字段。
- AppMessage 使用 `messageType = assistant`、`source = assistant_turn`、`target.targetType = assistant_turn`。
- 股票类 AppMessage summary 必须包含“非投资建议”或等价风险边界。
- 用户反馈只进入 M9 最小枚举：`useful`、`irrelevant`、`too_frequent`。

验收标准：

- 每日助手能生成早间计划和晚间复盘。
- 新闻简报能按时间主动送达。
- 股票哨兵能基于模拟重大信息摘要生成提醒，并附非投资建议边界。
- 出行管家能基于模拟天气、路况、拥堵摘要生成提醒。
- 每条主动提醒都能解释“为什么提醒我”。
- 用户可反馈有用、不相关、太频繁。
- 四个 Skill 都能从 `SkillSubscription` cron 触发，生成 proactive turn，再生成 AppMessage。
- 端侧“找私助”能展示四个 Skill 的订阅入口、主动消息、回跳 turn 与反馈入口。
- “找小趣”旧入口无回归。

测试证据：

- T1：metadata/codegen/fixture roundtrip 覆盖四个 P0 Skill 的订阅、proactive turn、AppMessage。
- T2：云侧 service 测试覆盖四个 Skill 的内容生成、解释原因、runtime failure 与风险边界。
- T2：端侧 Repository / Provider / Widget 测试覆盖订阅入口、消息回跳、反馈入口。
- T3：assistant-service contract test 覆盖 cron -> P0 Skill -> proactive turn -> AppMessage。
- T4：本地 fake mode 可演示四个 P0 Skill 端到端闭环。

任务拆解：

1. M9-S1：冻结本规格，补齐准入、非目标、四个 P0 Skill 最小规格、事件/消息规范和测试证据。
2. M9-S2：补四个 P0 Skill 的 metadata / fixture / replay 样例，保持 taxonomy 同源。
3. M9-S3：实现云侧 P0 Skill fake provider 与 SkillRuntime 分发，输出结构化 `why/evidence/nextActions`。
4. M9-S4：增强 cron proactive turn 生成逻辑，按 skillId 生成对应 AppMessage 标题、摘要、风险边界和回跳目标。
5. M9-S5：完善找私助端侧订阅入口、消息展示、回跳和反馈入口。
6. M9-S6：补齐 T1-T4 测试证据，必要时同步页面横向质量矩阵和 P2 inventory。

### M10：趣聊与圈子主动分发

目标：让主动式小趣从个人提醒扩展到趣聊群和圈子，让群成员与圈子成员在共同场景中接收可解释、可反馈、可治理的主动信息，形成 App 差异化。

准入条件：

- M1-M9 已具备可执行或可测试证据：runtime/id、runtime/clock、runtime/streaming、runtime/failures、metadata/codegen、assistant-service turn stream、ToolCoordinator、SkillSubscription、P0 Skill、AppMessage、找私助入口。
- M9 已支持四个 P0 Skill 从 `SkillSubscription` cron 触发，生成 proactive turn 与 AppMessage。
- chat-service 已具备 assistant 成员邀请、移除、群成员角色、消息发送、群消息列表与端侧 Repository 能力。
- circle-service 已具备圈子、成员、角色、圈子页展示与端侧 Repository 能力。
- “找小趣”旧入口保持不变；M10 只增强“找私助”主动分发与管理能力。

范围：

- 趣聊群分发：
  - 群主或管理员邀请小趣作为 assistant 成员进入群聊。
  - 群主或管理员创建 `destination.type = conversation` 的 `SkillSubscription`。
  - cron 命中后创建 `turnType = proactive` 的 `AssistantTurn`。
  - SkillRuntime 生成主动结果后，通过 chat-service 以 assistant 成员写入群消息。
  - 群成员可对该条主动消息反馈 `useful`、`irrelevant`、`too_frequent`。

- 圈子摘要卡片：
  - 圈主或管理员创建 `destination.type = circle` 的 `SkillSubscription`。
  - cron 命中后创建 `turnType = proactive` 的 `AssistantTurn`。
  - SkillRuntime 生成主动结果后创建 `AppMessage destination=circle`。
  - 端侧圈子页读取 circle-scoped AppMessage，展示摘要卡片或热点提醒。
  - M10 不创建圈子 feed 帖子，不影响内容域帖子生命周期。

- AppMessage 扩展：
  - `destination.type` 支持 `user`、`conversation`、`circle`。
  - `target.targetType` 支持 `assistant_turn`、`chat_message`、`circle_app_message`。
  - `messageType` 继续使用 `assistant`，不新增助手私有通知对象。

- 管理与反馈：
  - “找私助”或 Skill 管理入口支持查看个人、群聊、圈子订阅。
  - 管理员可暂停、恢复、归档群/圈订阅。
  - 反馈只进入后续策略输入，不删除记录消息，不自动变更订阅状态。

M10 非目标：

- 不实现事件触发、阈值触发、冷却、每日上限。
- 不接入真实原生 push provider 作为主门禁依赖。
- 不让圈子主动摘要写入 content feed 或创建帖子。
- 不实现复杂群内个性化分发；同一个群/圈先共享一条主动结果。
- 不做自动交易、支付、导航、下单、群管理自动操作。
- 不下线“找小趣”旧入口。

权限规则：

- 趣聊群订阅创建、暂停、恢复、归档仅允许 owner / admin。
- 圈子订阅创建、暂停、恢复、归档仅允许 owner / admin。
- 普通成员只能查看主动消息、打开详情、提交反馈。
- 小趣被移出群聊后，关联 conversation destination 订阅必须自动暂停或进入不可投递状态。
- 圈子被归档、成员无权访问或订阅目标不存在时，tick 必须返回结构化 runtime failure，不得静默成功。

业务对象规则：

- `SkillSubscription.owner.ownerType`：
  - `user`：个人订阅。
  - `conversation`：趣聊群订阅。
  - `circle`：圈子订阅。
- `SkillSubscription.destination.destinationType`：
  - `user`：个人 AppMessage。
  - `conversation`：群聊消息。
  - `circle`：圈子摘要卡片 AppMessage。
- `AssistantConversation`：
  - 群聊 proactive turn 可绑定一个 group-scoped assistant conversation，`summary` 包含群名或群场景摘要。
  - 圈子 proactive turn 可绑定一个 circle-scoped assistant conversation，`summary` 包含圈子名或圈子场景摘要。
- `AssistantTurn`：
  - `turnType = proactive`。
  - `trigger.type = cron`。
  - `skillId` 必须来自已启用 P0 Skill 或 M10 允许的群/圈 Skill catalog。
- `AppMessage`：
  - 圈子摘要使用 `messageType = assistant`、`source = assistant_turn`。
  - `destination.type = circle`、`destination.id = circleId`。
  - `target.targetType = circle_app_message`、`target.targetId = messageId` 或 `turnId`。

M10 API 规划：

- assistant-service：
  - `GET /v1/assistant/skill-subscriptions?ownerType=conversation&ownerId={conversationId}`
  - `GET /v1/assistant/skill-subscriptions?ownerType=circle&ownerId={circleId}`
  - `POST /v1/assistant/skill-subscriptions`
  - `PATCH /v1/assistant/skill-subscriptions/{subscriptionId}/status`
  - `POST /v1/assistant/skill-subscriptions/cron/tick`
  - `POST /v1/assistant/proactive-deliveries/{turnId}/feedback`

- chat-service：
  - 复用 `POST /v1/chat/conversations/{conversationId}/assistant` 邀请小趣。
  - 复用 `DELETE /v1/chat/conversations/{conversationId}/assistant` 移除小趣。
  - 复用 `POST /v1/chat/conversations/{conversationId}/messages` 写入 assistant 主动消息。
  - 如需服务间端口，assistant-service 通过 `ChatDeliveryPort.SendAssistantMessage` 调用，不直接写 chat 存储。

- circle-service / AppMessage：
  - `GET /v1/app-messages?destinationType=circle&destinationId={circleId}`
  - `POST /v1/app-messages/{messageId}/ack`
  - `POST /v1/app-messages/{messageId}/read`
  - 圈子页通过 Repository 读取 circle-scoped AppMessage，不直接读 assistant 内部状态。

事件与消息规范：

- cron tick 命中群/圈订阅后，先创建 proactive turn，再执行 SkillRuntime。
- `conversation` destination 成功时：
  - 输出 `proactive_delivery_started`。
  - 调用 chat adapter 写入群消息。
  - 输出 `proactive_delivery_completed`，payload 包含 `chatMessageId`、`conversationId`、`turnId`。
- `circle` destination 成功时：
  - 输出 `proactive_delivery_started`。
  - 创建 `AppMessage destination=circle`。
  - 输出 `proactive_delivery_completed`，payload 包含 `messageId`、`circleId`、`turnId`。
- 群消息和圈子卡片必须包含：
  - `skillId`
  - `subscriptionId`
  - `turnId`
  - `why`
  - `evidence`
  - `sourceSummary`
  - `nextActions`
- 失败路径必须携带 runtime failure：
  - 群无权限。
  - 小趣未在群内。
  - 圈子不存在或已归档。
  - destination 类型不支持。
  - chat/circle adapter 不可用。

契约与 codegen 规划：

- `contracts/metadata/assistant/skill_subscription/schema.yaml`
  - `owner.ownerType` 扩展并固定枚举：`user`、`conversation`、`circle`。
  - `destination.destinationType` 扩展并固定枚举：`user`、`conversation`、`circle`。
  - 新增 M10 fixture：`m10_skill_subscription_conversation_destination.json`、`m10_skill_subscription_circle_destination.json`、`m10_skill_subscription_destination_denied_failure.json`。

- `contracts/metadata/notification/app_message/schema.yaml`
  - `destination.type` 扩展并固定枚举：`user`、`conversation`、`circle`。
  - `target.targetType` 扩展并固定枚举：`assistant_turn`、`chat_message`、`circle_app_message`。
  - 新增 M10 fixture：`m10_app_message_circle_card.json`、`m10_app_message_chat_delivery_reference.json`。

- `contracts/metadata/assistant/assistant_stream_event/schema.yaml`
  - `eventType` 增加 `proactive_delivery_started`、`proactive_delivery_completed`、`proactive_delivery_failed`。
  - payload 必须携带 `destinationType`、`destinationId`、`subscriptionId`、`turnId`。

- `contracts/metadata/assistant/runtime_failure/schema.yaml` 或 assistant errors metadata
  - 增加 M10 错误码：`ASSISTANT.PERMISSION.destination_denied`、`ASSISTANT.DELIVERY.assistant_not_in_conversation`、`ASSISTANT.DELIVERY.circle_unavailable`、`ASSISTANT.DELIVERY.destination_unsupported`、`ASSISTANT.DELIVERY.adapter_unavailable`。

- Dart / Go 产物：
  - Dart 更新 `SkillSubscriptionWire`、`AppMessageWire`、`AssistantStreamEventWire`。
  - Go 更新 assistant-service domain/wirepoc 对应结构。
  - 端云 roundtrip fixture 必须覆盖 user / conversation / circle 三类 destination。

云侧工程落点：

- assistant-service domain：
  - `internal/domain/assistant/skill_subscription.go` 扩展 owner / destination 枚举校验。
  - `internal/domain/assistant/app_message.go` 扩展 destination / target 枚举。
  - 新增 proactive delivery 结果对象：`ProactiveDeliveryResult`，字段包含 `turnId`、`destinationType`、`destinationId`、`chatMessageId`、`appMessageId`、`runtimeFailure`。

- assistant-service application：
  - 新增 `proactive_delivery_router.go`：
    - `DeliverProactiveResult(ctx, turn, subscription, result)`。
    - user destination：复用现有 AppMessage 分支。
    - conversation destination：调用 `ChatDeliveryPort`。
    - circle destination：调用 `CircleAppMessagePort` 或现有 AppMessage store 的 circle scoped create/list。
  - 扩展 `skill_subscription_service.go`：
    - normalize 阶段允许 `destinationType = conversation | circle`。
    - cron tick 不再直接只创建 user AppMessage，改为调用 delivery router。
    - tick result 增加或内部记录 `CreatedChatMessageIDs`、`CreatedCircleMessageIDs`，对外可先在 fixture 中验证。

- assistant-service ports / adapters：
  - `ChatDeliveryPort.SendAssistantMessage(ctx, request)`：
    - 输入：`conversationId`、`turnId`、`subscriptionId`、`title`、`summary`、`why`、`evidence`、`nextActions`。
    - 输出：`chatMessageId`、`seq`。
    - 适配 chat-service `SendMessage`，`SenderId = assistant`，`Type = assistant_card` 或现有可承载卡片的消息类型。
  - `CircleAppMessagePort.CreateCircleCard(ctx, request)`：
    - 输入：`circleId`、`turnId`、`subscriptionId`、`title`、`summary`、`why`、`evidence`、`nextActions`。
    - 输出：`messageId`。
    - M10 默认落为 `AppMessage destination=circle`，不调用 content/circle feed 写帖接口。

- chat-service 协作边界：
  - 复用现有 `InviteAssistant` 与 `RemoveAssistant`。
  - 写群消息前必须确认 assistant 成员存在。
  - 群权限判断由 chat-service 或 adapter 调用 chat-service 查询完成，assistant-service 不直接读取 chat 存储。

- circle-service 协作边界：
  - 圈子存在性、归档状态、管理员权限由 circle-service 或 adapter 查询完成。
  - M10 只需要 circle-scoped AppMessage 展示，不新增 circle feed 业务对象。
  - 圈子 taxonomy、圈子频道和内容分类继续使用已有 metadata，不在 assistant 内部维护第二套分类。

端侧工程落点：

- `quwoquan_app/lib/cloud/services/assistant/assistant_repository.dart`
  - 扩展 `createSkillSubscription`，支持传入 `ownerType`、`ownerId`、`destinationType`、`destinationId`。
  - 扩展订阅列表查询，支持按 ownerType / ownerId 过滤。
  - 新增 proactive delivery feedback 方法：`submitProactiveDeliveryFeedback(turnId, feedbackType)`。

- `quwoquan_app/lib/cloud/services/chat/chat_repository_api.dart`
  - 复用 `inviteAssistant` / `removeAssistant`。
  - 如端侧需要群订阅管理入口，优先通过 assistant repository 创建 subscription，不在 chat repository 内创建助手订阅。

- `quwoquan_app/lib/cloud/services/notification/` 或现有 AppMessage repository
  - 扩展 `listAppMessages(destinationType: 'circle', destinationId: circleId)`。
  - 圈子页只读取 AppMessage DTO，不读取 assistant-service 内部 turn 状态。

- `quwoquan_app/lib/ui/assistant/`
  - “找私助”管理页新增群/圈订阅列表、创建、暂停、恢复、归档入口。
  - 订阅配置页必须展示目标类型：个人、群聊、圈子。
  - 反馈入口复用 M9 的 `useful`、`irrelevant`、`too_frequent`。

- `quwoquan_app/lib/ui/chat/`
  - 群设置页或小趣入口展示“邀请小趣”和“群 Skill 订阅”入口。
  - 群消息中渲染 assistant 主动消息卡片，展示 `why`、`evidence`、来源与反馈。
  - 普通成员只能反馈，不能编辑群订阅。

- `quwoquan_app/lib/ui/circle/`
  - 圈子页展示 circle-scoped AppMessage 摘要卡片或热点提醒。
  - 圈子管理入口展示圈子 Skill 订阅管理。
  - 不创建帖子、不复用内容发布流程、不绕过 taxonomy。

- Provider 与 Mock 隔离：
  - UI 只能通过 `assistantRepositoryProvider`、`chatRepositoryProvider`、`circleRepositoryProvider`、`appMessageRepositoryProvider` 取数。
  - `lib/ui/**` 禁止 import `cloud/services/*/mock/`。
  - 新增或改动页面时同步页面横向质量矩阵、P2 inventory 和 PR checklist。

验收标准：

- 群管理员能邀请小趣并绑定 skill。
- cron 能触发 conversation destination 订阅，主动消息能以 assistant 成员写入群聊。
- 群内消息带触发原因、来源、证据和回跳目标。
- 群成员可反馈有用、不相关、太频繁。
- 圈子管理员能创建 circle destination 订阅。
- cron 能触发 circle destination 订阅，圈子页能展示 AppMessage 摘要卡片或热点提醒。
- 圈子摘要不绕过内容/圈子 taxonomy。
- AppMessage 不退回助手私有通知；chat/circle 不直接控制底层 transport。
- `SkillSubscription`、`AppMessage`、`AssistantTurn` 的 conversation / circle destination 字段在 metadata、Go、Dart、fixture 中一致。
- “找私助”完成 M10 主链路，“找小趣”旧入口无回归。

测试证据：

- T1：metadata/codegen/fixture roundtrip 覆盖 `SkillSubscription destination=conversation`、`SkillSubscription destination=circle`、`AppMessage destination=circle`、proactive delivery failure。
- T2：assistant-service service 测试覆盖 user/conversation/circle delivery routing、chat adapter success/failure、circle AppMessage success/failure。
- T2：chat-service contract 测试覆盖 assistant 成员已存在、未邀请、管理员权限、assistant 主动消息写入。
- T2：端侧 Repository / Provider 测试覆盖群订阅、圈子订阅、圈子卡片读取、反馈入口和错误降级。
- T3：assistant-service contract test 覆盖 cron -> proactive turn -> chat message。
- T3：assistant-service contract test 覆盖 cron -> proactive turn -> circle AppMessage。
- T4：本地 fake mode 可演示群聊收到小趣主动消息、圈子页展示摘要卡片、用户反馈。

建议测试文件：

- `quwoquan_service/services/assistant-service/internal/application/proactive_delivery_router_test.go`
- `quwoquan_service/services/assistant-service/internal/application/skill_subscription_m10_test.go`
- `quwoquan_service/services/chat-service/tests/assistant_proactive_message_contract_test.go`
- `quwoquan_service/services/circle-service/tests/circle_app_message_contract_test.go`
- `quwoquan_app/test/ui/assistant/personal_assistant_m10_subscription_test.dart`
- `quwoquan_app/test/ui/chat/assistant_group_subscription_test.dart`
- `quwoquan_app/test/ui/circle/circle_app_message_card_test.dart`

门禁命令：

```bash
make -C quwoquan_service verify-metadata
make codegen
make codegen-app
make -C quwoquan_service build
make -C quwoquan_service test-contract
make verify-app-page-horizontal-quality
make verify-app-mock-isolation
make gate
```

准出要求：

- T1-T3 必须进入高频门禁或等价 CI。
- T4 fake mode 作为人工集中验收证据，不依赖真实外部模型、新闻、行情、天气或 push。
- 若新增页面或改动扫描范围内页面，必须同步页面横向质量矩阵与 PR checklist。
- 任何失败路径不得只返回字符串错误，必须映射 runtime failure。

任务拆解：

1. M10-S1：冻结本规格，补齐准入、范围、非目标、权限、delivery、API、事件、验收与测试证据。
2. M10-S2：扩展 metadata/codegen/fixture，覆盖 conversation / circle destination、M10 failure、AppMessage circle card。
3. M10-S3：扩展 assistant-service `SkillSubscription` normalize 与 cron tick，支持 owner / destination 为 conversation、circle。
4. M10-S4：新增 proactive delivery router，拆分 user AppMessage、conversation chat message、circle AppMessage 三条分支。
5. M10-S5：新增 chat delivery port / adapter，复用 chat-service assistant member 与 message send 能力。
6. M10-S6：新增 circle AppMessage 查询与端侧圈子摘要卡片展示入口，不创建 feed post。
7. M10-S7：完善找私助端侧群/圈订阅管理、反馈入口、错误降级与页面横向质量矩阵。
8. M10-S8：补齐 T1-T4 测试证据，运行对应 metadata/codegen、service tests、app tests 与门禁。

M10 自检与冻结状态：

- 规格覆盖：已覆盖准入条件、目标、范围、非目标、权限规则、业务对象规则、API、事件、消息规范、验收标准、测试证据、建议测试文件、门禁命令与任务拆解。
- 契约覆盖：已明确 `SkillSubscription`、`AppMessage`、`AssistantStreamEvent`、runtime failure、Dart/Go codegen 与 M10 fixtures 的扩展范围。
- 云侧覆盖：已明确 assistant-service proactive delivery router、chat delivery port、circle AppMessage port、chat-service / circle-service 协作边界。
- 端侧覆盖：已明确找私助管理入口、趣聊群订阅入口、圈子摘要卡片、反馈入口、Provider / Mock 隔离和页面横向质量要求。
- 记录文档：`docs/personal-assistant/` 保持 `README.md` 为唯一评审入口，旧文档不再作为规格真相源。
- 验证状态：本小节冻结的是 M10 规格与验收规划；M10-S2 到 M10-S8 的代码实现、metadata/codegen、T1-T4 测试和门禁需要在开发实施阶段执行后，才能进入 M11。
- 准出结论：可以进入 M10 开发实施；不能跳过 M10 实施直接进入 M11。

### M11：测试与门禁收口

目标：保证云端化后仍能快速本地开发、稳定集中验收，并按 `alpha → beta → gamma → prod-gray → prod` 完成“找私助”端云验证与“找小趣”旧入口无回归验证。

准入条件：

- M1-M10 的 metadata/codegen、runtime、assistant-service、AppMessage、ToolCoordinator、端侧双入口、主动订阅和 P0 Skill 代码已合入。
- `quwoquan_app/lib/ui/assistant/pages/assistant_tab_page.dart` 同时保留“找小趣”和“找私助”入口。
- “找小趣”仍走旧端侧 `lib/assistant/` 主链路；“找私助”走云端 `assistant-service`、typed stream、AppMessage 与 SkillSubscription。
- alpha/beta 本地开发环境允许启动网关、assistant-service、Flutter 模拟器，不依赖真实外部模型、真实股票行情、真实天气或真实 push；gamma 进入云侧类生产集成验证。

范围：

- `assistant-service` 纳入 `make build`。
- `assistant-service` 纳入 `make test-contract`。
- `assistant-service` 纳入 `make gate`。
- 建立 alpha fixture / single-service mode、beta local e2e mode、gamma cloud integration mode。
- 建立 replay corpus。
- 建立 fake clock、fake app message channel、fake model provider。
- 建立股票、天气、行程规划三条 user-initiated beta 本地端云验证场景，并可复用于 gamma 云侧集成。
- 建立“找小趣”旧入口流式叙事和答案生成的同步回归。
- 建立模拟器本地 IP、`dart-define`、服务启动顺序和验收证据规范。

非目标：

- M11 不新增 M1-M10 之外的新业务能力。
- M11 不接入真实投资行情、真实天气供应商、真实导航路况或真实原生 push。
- M11 不下线“找小趣”入口，只验证并行期无回归。
- gamma live eval 不进入高频门禁，只作为人工集中验收补充证据。

验证模式：

- 端侧 alpha simulator mode：
  - iPad/iOS Simulator 启动 App，注入 `APP_RUNTIME_ENV=alpha` 与 `APP_DATA_SOURCE=mock`。
  - 只验证端侧入口、Provider、mock/stub stream、找小趣回归和页面渲染，不启动真实云服务。
  - mock repository 必须从 `contracts/metadata/assistant/test_fixtures/scenarios/assistant_scenarios.json` 读取云侧应返回的数据；禁止在 UI 或测试里临时拼问题、答案和事件期望。
  - 必须覆盖“找小趣”入口存在、“找私助”入口存在、找私助 stub stream 渲染、返回找小趣后旧入口仍可用。
  - 属于 T2 高频门禁，可用 Widget / Provider 测试自动化，也可在模拟器手工补截图证据。

- 云侧 alpha single-service mode：
  - 单个 `assistant-service` 使用 `APP_ENV=alpha` 启动或通过 Go HTTP handler / application 测试验证。
  - 配置只来自 `configs/default/config.yaml` 与 `configs/alpha/config.yaml`，禁止读取旧 `local` / `integration` 目录。
  - 使用 metadata fixture、SSE golden、replay corpus、fake model、fake tool、fake clock、fake app message。
  - application / HTTP handler 测试必须加载同一份 scenario fixture；alpha 单服务可使用内存 store，但也必须显式 reset + seed。
  - 不启动 Flutter App，不接入真实外部模型或真实供应商。
  - typed stream 必须包含递增 `seq` 与 `turn_started`、`tool_use_requested`、`tool_result_received`、`final_answer`。

- beta local e2e mode：
  - 启动本地网关、assistant-service 和必要本地依赖。
  - Flutter 使用 `APP_RUNTIME_ENV=beta`、`APP_DATA_SOURCE=remote` 与 `CLOUD_GATEWAY_BASE_URL` 连接本地网关。
  - 每次 beta 测试前云侧必须执行 reset + seed，将 scenario `seedRefs` 初始化到自己的数据库、内存 store 或测试容器；端侧只能通过 remote repository 操作初始化后的云侧数据。
  - 用模拟器完成“找私助”三条场景和“找小趣”旧入口回归。

- gamma cloud integration mode：
  - 云侧部署 assistant-service / gateway / AppMessage 相关组件，使用 `APP_ENV=gamma` 和版本化配置。
  - 端侧使用 `APP_RUNTIME_ENV=gamma` 与 gamma 网关完成同一组三场景验证。
  - gamma 使用与 beta 完全相同的 scenario/seed artifact，差异只允许来自网关、认证、部署配置和观测链路；不得复制一套 gamma 专用问题或期望。
  - 可选择性接入真实模型或外部供应商；失败必须记录风险、回退策略和是否阻断进入 `prod-gray`。

M11 环境验收流转：

```text
alpha：端侧 simulator mock/stub + 云侧 single-service
  → beta：本地网关 + 本地 assistant-service + 模拟器端云联调
  → gamma：云侧集成部署 + 同场景验收
  → prod-gray：生产灰度，只验证开关、观测、回滚和小流量
  → prod：全量开放
```

其中既有端侧 mock / stub 测试统一归入端侧 alpha；`assistant-service` 单实例与 HTTP handler typed stream 统一归入云侧 alpha；本地模拟器连本机 Go 服务的端云协同归入 beta；云侧部署后再验收的同一组三场景归入 gamma。

端云数据驱动契约：

- 测试场景唯一真相源：`quwoquan_service/contracts/metadata/assistant/test_fixtures/scenarios/assistant_scenarios.json`。
- `scenario` 定义用户操作、期望答案片段、期望 stream event；`seed` 定义云侧服务测试前需要加载的数据。
- `APP_RUNTIME_ENV=alpha` 默认端侧使用 mock repository；`APP_RUNTIME_ENV=beta|gamma` 默认端侧使用 remote repository。`APP_DATA_SOURCE` 可显式覆盖，但必须与环境契约一致。
- 找私助和技能管理均必须走同一套 scenario/seed 机制；后续新增端云功能也必须先定义 fixture，再接入 alpha mock 与 beta/gamma remote 验证。
- `prod-gray` / `prod` 不使用测试 fixture，不做 reset + seed，使用真实用户数据和正式灰度/生产治理。

alpha 验收证据模板：

```text
env: alpha
side: app | cloud
simulator: iPad / iOS version（端侧 alpha 必填）
command: <flutter test / flutter run / go test / go run>
data_source: mock | fixture | single-service
entry: 找小趣 | 找私助 | assistant-service
question: <用户问题或 fixture 名称>
turnId: <如有>
stream_events: [turn_started, tool_use_requested, tool_result_received, final_answer]
result: pass | fail
notes: <失败、fallback 或截图位置>
```

beta 验收证据模板：

```text
env: beta
simulator: iPad / iOS version
gateway: http://127.0.0.1:18080
assistant_service: APP_ENV=beta :18087
scenario_id: <stock_sentinel_basic | weather_trip_basic | travel_journey_basic>
seed_refs: <assistant_p0_core>
turnId: <真实返回>
stream_events: [turn_started, tool_use_requested, tool_result_received, final_answer]
final_answer_keywords: <重大消息/非投资建议 | 天气/建议 | 路况/拥堵>
current_xiaoqu_regression: pass | fail
result: pass | fail
notes: <截图、日志、fallback>
```

alpha / beta 本地开发环境配置：

- 端侧网关唯一入口来自 `quwoquan_app/lib/cloud/runtime/cloud_runtime_config.dart` 的 `CLOUD_GATEWAY_BASE_URL`。
- 端侧运行环境来自 `APP_RUNTIME_ENV`，默认 `alpha`。
- 默认网关为 `http://127.0.0.1:18080`。
- assistant-service 在 `APP_ENV=alpha|beta` 下读取同名配置目录，HTTP 监听 `:18087`。
- iOS Simulator 可使用宿主机 `127.0.0.1`。
- Android Emulator 访问宿主机时使用 `10.0.2.2`，或使用宿主机局域网 IP。
- beta 本地端云验证必须显式注入：

```bash
--dart-define=APP_RUNTIME_ENV=beta
--dart-define=APP_DATA_SOURCE=remote
--dart-define=CLOUD_GATEWAY_BASE_URL=http://127.0.0.1:18080
```

Android Emulator 示例：

```bash
--dart-define=APP_RUNTIME_ENV=beta
--dart-define=APP_DATA_SOURCE=remote
--dart-define=CLOUD_GATEWAY_BASE_URL=http://10.0.2.2:18080
```

本地联调 Runbook：

0. alpha 预验证：

```bash
# 端侧 alpha：只验证模拟器 UI + mock/stub，不启动云服务。
flutter run \
  --dart-define=APP_RUNTIME_ENV=alpha \
  --dart-define=APP_DATA_SOURCE=mock

# 云侧 alpha：只验证 assistant-service 单实例。
cd quwoquan_service/services/assistant-service
APP_ENV=alpha go test ./internal/application ./internal/adapters/http -count=1
```

1. 启动本地依赖：

```bash
make -C quwoquan_service dev
```

若本机未安装 Docker，M11 自动验收允许 `assistant-service/configs/beta/config.yaml` 使用内存 Postgres/Mongo/Redis fallback；该模式仍验证 App → beta gateway → assistant-service 的真实 HTTP typed stream 链路，只是不验证外部存储。

2. 启动 assistant-service：

```bash
cd quwoquan_service/services/assistant-service
APP_ENV=beta go run ./cmd/api
```

服务会按 `APP_ENV=beta` 合并 `configs/default/config.yaml` 与 `configs/beta/config.yaml`。

3. 启动本地网关：

```bash
python3 scripts/dev_assistant_beta_gateway.py \
  --listen-host 127.0.0.1 \
  --listen-port 18080 \
  --upstream-host 127.0.0.1 \
  --upstream-port 18087
```

网关必须监听 `CLOUD_GATEWAY_BASE_URL` 指向的 host:port，并转发 `/v1/assistant/*` 与 `/v1/app-messages/*` 到 assistant-service `:18087`。该脚本只用于 M11 beta 本地验证，不代表正式 gateway/orchestrator 实现。

4. iOS Simulator 启动 App：

```bash
flutter run \
  --dart-define=APP_RUNTIME_ENV=beta \
  --dart-define=APP_DATA_SOURCE=remote \
  --dart-define=CLOUD_GATEWAY_BASE_URL=http://127.0.0.1:18080
```

5. Android Emulator 启动 App：

```bash
flutter run \
  --dart-define=APP_RUNTIME_ENV=beta \
  --dart-define=APP_DATA_SOURCE=remote \
  --dart-define=CLOUD_GATEWAY_BASE_URL=http://10.0.2.2:18080
```

6. 验收顺序：

- 先打开“找小趣”，发送一个普通问题，确认流式叙事和最终答案正常。
- 再打开“找私助”，依次执行股票、天气、行程规划三条问题。
- 每条问题记录：模拟器平台、`CLOUD_GATEWAY_BASE_URL`、turnId、stream event 序列、最终答案、失败或 fallback 信息。
- 如本地网关不可用，先回到 alpha fixture / single-service mode，不能用真实外网结果替代 M11 beta 本地证据。

设备矩阵自动验证：

```bash
python3 scripts/run_assistant_device_matrix.py --env alpha,beta
```

- runner 使用 `flutter devices --machine` 自动枚举所有可用 mobile 设备，不写死模拟器 UDID。
- 每个可用模拟器 / 真机都会分别执行 alpha 与 beta；若同时有手机和平板，两类屏幕都必须通过。
- 测试不会固定 `setSurfaceSize`，而是通过 `VALIDATION_SCREEN_CLASS=phone|tablet|any` 在真实设备逻辑尺寸下验证自适应。
- beta 阶段由 runner 自动清理 `18080/18087`、启动 `APP_ENV=beta go run ./cmd/api` 与 `scripts/dev_assistant_beta_gateway.py`，健康检查通过后再逐设备执行。
- iOS Simulator 默认使用 `http://127.0.0.1:18080`；Android Emulator 使用 `http://10.0.2.2:18080`；真机如无法访问宿主机 loopback，可通过 `--gateway-base-url` 指定局域网地址。
- 结构化证据输出到 `tmp/assistant_device_matrix_report.json`，包含设备、环境、屏幕类别、命令、耗时、状态、失败摘要和 beta 服务日志路径。

三条本地端云验收场景：

- 股票：
  - 入口：模拟器打开“找私助”。
  - 用户问题：`帮我看一下比亚迪今天有哪些重大消息，会不会影响我关注的股票？`
  - 云侧：走本地 assistant-service，使用 fake web_search / market fixture。
  - 验收：typed stream 包含 turn started、tool requested、tool completed、final answer；最终答案包含重大消息摘要和“非投资建议”边界。

- 天气：
  - 入口：模拟器打开“找私助”。
  - 用户问题：`下午去西湖，天气和出行有什么要注意？`
  - 云侧：走本地 assistant-service，使用 fake weather / web_search fixture。
  - 验收：typed stream 包含工具观察；最终答案包含天气变化、出行建议和可追问提示。

- 行程规划：
  - 入口：模拟器打开“找私助”。
  - 用户问题：`明天杭州一日游，帮我结合天气、路况和景点拥堵规划一下。`
  - 云侧：走本地 assistant-service，使用 fake travel / weather / traffic / poi fixture。
  - 验收：typed stream 包含工具观察；最终答案覆盖吃住行或行程节奏、天气、路况、景点拥堵和调整建议。

beta 手工场景记录表：

| 场景 | 问题 | 必须事件 | 答案关键词 | 记录项 |
|------|------|----------|------------|--------|
| 股票 | `帮我看一下比亚迪今天有哪些重大消息，会不会影响我关注的股票？` | `turn_started`、`tool_use_requested`、`tool_result_received`、`final_answer` | `重大消息`、`非投资建议` | simulator、gateway、turnId、event seq、截图 |
| 天气 | `下午去西湖，天气和出行有什么要注意？` | 同上 | `天气`、`建议` | simulator、gateway、turnId、event seq、截图 |
| 行程规划 | `明天杭州一日游，帮我结合天气、路况和景点拥堵规划一下。` | 同上 | `路况`、`拥堵` | simulator、gateway、turnId、event seq、截图 |

本轮 beta T4 证据登记：

| 场景 | 状态 | 说明 |
|------|------|------|
| 股票 | 自动通过 | iPad Simulator beta remote 测试通过，答案包含 `重大消息`、`非投资建议` |
| 天气 | 自动通过 | iPad Simulator beta remote 测试通过，答案包含 `天气`、`建议` |
| 行程规划 | 自动通过 | iPad Simulator beta remote 测试通过，答案包含 `路况`、`拥堵` |

“找小趣”同步回归：

- 模拟器保持现有“找小趣”入口可用。
- 验证旧入口仍能发起问题、展示流式叙事、生成最终答案。
- 验证“找私助”新增 remote stream 不改变“找小趣”的 local pipeline、路由、Provider 和记录会话展示。
- 自动化测试至少覆盖 tab 切换、旧入口存在、找私助入口存在、找私助 stub stream 渲染。

测试证据：

- T1：metadata verify、Dart/Go fixture roundtrip、SSE golden 解码、runtime failure fixture。
- T2：端侧 alpha stub stream journey 测试、“找小趣”旧入口回归测试；云侧 alpha fake model / fake tool / fake clock / fake AppMessage 测试。
- T3：beta local e2e mode 下 assistant-service 通过 `APP_ENV=beta` 启动并服务 typed stream；本地网关可转发到 assistant-service。
- T4：beta 模拟器完成股票、天气、行程规划三条“找私助”端云验证，并同步完成“找小趣”旧入口流式叙事和答案生成验证；gamma 云侧集成验证通过后才可进入 `prod-gray`。

M11-S2 状态核对：

- `quwoquan_service/Makefile` 的 `build` 已调用 `services/assistant-service build`。
- `quwoquan_service/Makefile` 的 `test-unit` 与 `test-contract` 已调用 `services/assistant-service test`。
- `quwoquan_service/scripts/gate.sh` 必须显式运行 `services/assistant-service` 测试；若未覆盖，M11-S3 必须补齐。

### 12.7 M12 云侧能力补齐：端侧流式水准对齐

M12 目标不是直接开始 21 个 skill 比拼，而是先让云侧 `AgentLoop + ReAct + Skill + Tool + Stream` 达到可公平比对的能力基线。端侧现有“找小趣”流式叙事水准作为体验基线：用户应看到处理完成状态、处理/检索/耗时摘要、阶段性过程说明、检索依据与最终答案；多轮追问应复用上一轮上下文。

范围：

- 云侧 runtime 覆盖 21 个 domain skill 的 catalog / routing / tool policy 基础能力。
- 云侧 ReAct 支持多轮 loop、tool budget、observation assessment、replan 与 stop reason。
- 云侧 SSE 输出可被端侧 transcript 直接消费的过程叙事事件，不要求端侧维护第二套语义。
- 第一阶段 tool parity 覆盖 `web_search`、`search`、`web_fetch`、`app_search`、`memory_search` 与 Device Action proposal。
- beta 必须用天气、股票、出行三类多轮场景验证；低于 8/10 分需定位并修复后重跑。

非目标：

- M12 不接入真实金融交易、真实医疗诊断或直接端侧动作执行。
- M12 不下线“找小趣”入口。
- M12 不要求完成 21 个 skill 全量评分；全量比拼在云侧基线达标后进入下一阶段。

能力验收：

| 能力 | 必须满足 | 阻断条件 |
|------|----------|----------|
| ReAct loop | `maxIterations`、`maxToolCalls`、`toolHistory`、`stopReason`、`replanReason` 可观测 | 工具无结果仍直接 final answer |
| 流式叙事 | 输出 `assistant.plan.updated`、`assistant.search_query.generated`、`assistant.observation.assessed`、`assistant.replan.requested`、`assistant.answer.delta/final` | 只输出最终整段答案 |
| Skill 扩展 | 21 个 domain skill 在云侧 catalog/router 可见；天气、股票、出行能选中对应 skill | 三场景落入 `general_qa` |
| Tool parity | beta 三场景 tool result 带 query、provider、references/results、coverage/confidence/freshness | 未实现工具静默 fallback 到 mock |
| 检索设计 | 每个 beta 场景至少生成 1 条结构化 search plan | 只把原始问题塞给工具 |
| 多轮上下文 | 追问能复用上一轮地点、标的或行程主题 | 追问丢失上下文 |

评分口径（10 分）：

- 流式叙事完整度 3 分：过程卡片、检索过程、replan 说明、分段答案。
- 答案正确性与可用性 3 分：事实、建议、结构化表达和场景贴合。
- Skill/tool 执行一致性 2 分：选 skill 正确、tool 调用成功、证据可追溯。
- 多轮上下文能力 1 分：追问能复用上一轮地点、标的或行程。
- 稳定性与错误处理 1 分：RuntimeFailure、降级和恢复策略清晰。

beta 三场景最低答案边界：

| 场景 | Skill | 必须包含 |
|------|-------|----------|
| 天气 | `weather` 或 `travel_journey_manager` | 地点、日期、天气趋势、穿衣/出行建议 |
| 股票 | `finance_consumer` 或 `stock_sentinel` | 重大消息摘要、事实来源、风险提示、非投资建议 |
| 出行 | `travel_planning` 或 `travel_journey_manager` | 天气、路况或拥堵、景点节奏、调整建议 |
- `quwoquan_service/services/assistant-service/configs/alpha/config.yaml` 与 `configs/beta/config.yaml` 已分别定义本地 HTTP `:18087` 与本地 Postgres / Mongo / Redis。
- `quwoquan_app/lib/cloud/runtime/cloud_runtime_config.dart` 已定义 `APP_RUNTIME_ENV` 与 `CLOUD_GATEWAY_BASE_URL`，默认 `alpha` 与 `http://127.0.0.1:18080`。
- `quwoquan_app/lib/ui/assistant/pages/assistant_tab_page.dart` 已存在“找小趣”和“找私助”两个入口。
- `quwoquan_app/lib/core/providers/app_providers.dart` 已注册 `assistantRepositoryProvider` 与 `appMessageRepositoryProvider`，可通过 `APP_DATA_SOURCE=remote` 切换到 Remote。
- `quwoquan_service/contracts/metadata/assistant/test_fixtures/` 已提供 replay 与 SSE fixture 基础，M11 只补三场景 user-initiated 验收覆盖。

门禁命令：

```bash
make -C quwoquan_service build
make -C quwoquan_service test-contract
make -C quwoquan_service gate
flutter test test/assistant/assistant_cloud_stream_fixture_test.dart
flutter test test/ui/assistant/personal_assistant_stream_controller_test.dart
flutter test test/ui/assistant/personal_assistant_conversation_page_widget_test.dart
flutter test test/ui/assistant/pages/assistant_tab_page_widget_test.dart
```

验收标准：

- 不依赖真实模型即可跑核心契约测试。
- 云端 stream 协议有稳定 fixture。
- 主动订阅可用 fake clock 稳定测试。
- 端侧 alpha UI 可用 stub stream 测 journey 渲染。
- 云侧 alpha `assistant-service` 可用 fake tool 输出 typed stream。
- app message channel 可用 fake transport 稳定测试。
- `assistant-service` 被 `make build`、`make test-contract` 和 `make gate` 覆盖。
- beta 模拟器上“找私助”可通过本地 IP 完成股票、天气、行程规划三条端云链路。
- gamma 云侧集成环境可复用同一组三场景完成类生产验证。
- 模拟器上“找小趣”旧入口的流式叙事和答案生成无回归。
- gamma live eval 不进入高频门禁，只作为验收证据。
- 每个里程碑都能提供测试证据。

任务拆解：

1. M11-S1：冻结本规格，补齐验证模式、本地 IP、三场景、找小趣回归、证据矩阵。
2. M11-S2：核对 M1-M10 完成状态，形成 build/test/gate、fixture、双入口、本地配置状态清单。
3. M11-S3：将 assistant-service 纳入 `make gate`，补齐 SSE golden、replay、fake model、fake clock、fake AppMessage 高频门禁。
4. M11-S4：补齐股票、天气、行程规划三条 user-initiated turn 的云侧 alpha fake/single-service 测试。
5. M11-S5：补齐端侧 alpha 找私助 stub stream UI journey 测试和找小趣旧入口回归测试。
6. M11-S6：补齐 beta 本地开发 runbook：网关、assistant-service、模拟器 IP、`dart-define`、启动顺序和排错。
7. M11-S7：执行 beta 模拟器 T4 验收，记录股票、天气、行程规划三条找私助链路和找小趣旧入口证据。
8. M11-S8：执行 gamma 云侧集成验收，记录同一组三场景的网关、turnId、stream event 和回退策略。

本轮执行证据：

- 通过：`go test ./... -count=1`（目录：`quwoquan_service/services/assistant-service`）。
- 通过：`go test ./internal/adapters/http ./internal/application -count=1`，覆盖 M11 股票、天气、行程规划 user-initiated HTTP typed stream。
- 通过：`flutter test test/ui/assistant/personal_assistant_stream_controller_test.dart test/assistant/assistant_cloud_stream_fixture_test.dart test/ui/assistant/pages/assistant_tab_page_widget_test.dart`。
- 通过：iPad Pro (12.9-inch) Simulator 自动 alpha 验证：`flutter test test/common/assistant/assistant_environment_smoke_test.dart -d EAF3A223-E742-433D-B116-A152DCC7FF84 --dart-define=APP_RUNTIME_ENV=alpha --dart-define=APP_DATA_SOURCE=mock`。
- 通过：iPad Pro (12.9-inch) Simulator 自动 beta 验证：先启动 `APP_ENV=beta go run ./cmd/api` 与 `python3 scripts/dev_assistant_beta_gateway.py --listen-port 18080 --upstream-port 18087`，再执行 `flutter test test/common/assistant/assistant_environment_smoke_test.dart -d EAF3A223-E742-433D-B116-A152DCC7FF84 --dart-define=APP_RUNTIME_ENV=beta --dart-define=APP_DATA_SOURCE=remote --dart-define=CLOUD_GATEWAY_BASE_URL=http://127.0.0.1:18080`，覆盖股票、天气、行程规划三条找私助问题与找小趣回归。
- 修复：beta 首次自动验证发现 SSE 在观测中间件包装下因 `http.Flusher` 缺失返回 503，已改为无 `Flusher` 时仍输出完整 SSE 帧。
- 通过：`make -C quwoquan_service build`。
- 通过：`make verify-app-page-horizontal-quality`。
- 通过：IDE lint 检查，覆盖本次修改的 Dart / Go / shell 文件。
- 未完全通过：`make -C quwoquan_service test-contract`，assistant-service 段通过，失败点在 user-service 本地数据库重复键（`uq_invite_idempotent`、`uq_personas_active`），属于本地数据状态问题。
- 未完全通过：根目录 `make gate` 已清理 `apps/ops-portal/.test-dist` 后继续执行，但失败点在既有 Dart analyzer/generated contract 问题（`assistant_replay_case.g.dart` 缺少 `conversationId` / `turnId` 必填参数等），不是本次 M11 改动引入。
- 说明：本轮已用 iPad Simulator 自动证据覆盖端侧 alpha、云侧 alpha 与 beta 本地端云链路；本机无 `docker` 命令，beta 本地服务使用内存 Postgres/Mongo/Redis fallback，不覆盖外部存储连通性；gamma 云侧集成证据仍需在部署可用后补齐。

## 13. M0 冻结检查清单

M0 冻结前必须完成：

- [ ] `AssistantConversation`、`AssistantTurn`、`SkillSubscription`、`DeviceContext`、`ToolUse`、`AppMessage` 已进入 metadata。
- [ ] `AssistantStreamEvent` envelope 已进入 metadata。
- [ ] 连续对话状态机已定义，端云协同由 conversation state / turn status 驱动。
- [ ] 用户主动 turn 与主动触发 turn 共用同一 turn model。
- [ ] 主动消息进入 `AppMessage`，不再使用助手私有送达对象。
- [ ] Device context 不叫 snapshot，且只定义最小设备侧上下文事实。
- [ ] Tool 术语统一为 `ToolUse` / `ToolResult`，对齐业界 Agent 语义。
- [ ] Tool placement 枚举覆盖 `cloud`、`device_context`、`device_action`、`hybrid`。
- [ ] Skill 分类字段只引用 `domain_taxonomy.yaml` / `tag_taxonomy.yaml`。
- [ ] Skill catalog M0 字段已简化，不包含评分、使用量、tier、risk 等增强字段。
- [ ] Dart/Go 共享 fixture 已定义。
- [ ] Runtime failure 结构与现有 runtime error cutover 对齐。
- [ ] 弱类型 Map、字符串启发式判断、硬编码兜底话术已被 M0 静态检查或回归测试覆盖。
- [ ] 后续 M1 可基于 M0 契约补齐 runtime/id、runtime/errors、runtime/failures、runtime/clock、runtime/streaming 与 testinfra 测试基础。
- [ ] 实现策略已明确：现有“找小趣”入口保持不变，新增“找私助”入口并行验证，验收完成后再规划旧入口下线。

## 14. 集中验收总标准

最终集中验收时，必须回答“是”的问题：

- 云端是否已经成为小趣主执行入口？
- 小趣主业务对象是否已经从孤立 run 收敛为连续 conversation？
- 端侧是否已经瘦身为 UX、管理、设备上下文、消息送达？
- 用户主动对话是否走统一流式协议？
- 主动触达是否进入 `AssistantConversation + AssistantTurn + AppMessage`？
- Tool 是否完成云端优先、端侧上下文代理的分层？
- Tool 术语是否对齐 `ToolUse` / `ToolResult`，没有自造调用模型？
- Skill 分类是否同源内容/圈子 taxonomy？
- P0 四个主动 Skill 是否共用同一套订阅、触发、消息通道平台？
- 统一应用消息通道是否可支持助手、聊天、圈子、内容与系统消息？
- 本地测试是否足够快，不依赖真实模型也能验证主链路？
- 云端服务是否进入 build、test-contract、gate？
- “找私助”是否已经完整通过云端主链路验收，且“找小趣”旧入口在并行期无回归？
- 用户是否能理解、暂停、撤销、追溯小趣的主动行为？

只要以上成立，本次架构调整就完成了从“端侧聊天助手”到“云端主动私人助理平台”的核心跃迁。
