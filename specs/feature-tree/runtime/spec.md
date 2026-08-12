# L1 Domain Service：runtime（统一运行时能力域） (`runtime`)

> 一句话定位：runtime 作为跨端云机制领域服务，治理共享 runtime 包和 integration-service 等独立机制 进程；部署边界不形成新的 L1，业务对象与 Vendor SDK 不得穿透。

## 1. 目标与用户价值

runtime 作为跨端云机制领域服务，治理共享 runtime 包和 integration-service 等独立机制 进程；部署边界不形成新的 L1，业务对象与 Vendor SDK 不得穿透。

## 2. 领域边界

### 本领域拥有

- 拥有跨服务运行机制的配置解析、错误信封、传输、缓存、投影、事件、观测、测试基础设施和发布编排契约；不拥有业务聚合事实。
- 只能通过本领域公开 command 修改其拥有事实。

### 本领域不拥有

- 不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 不复制 metadata 中的字段、path、错误码和 wire 语义。

### 上下游协作

- 上游：AppRoot Journey 与公开输入事实。
- 下游：直接 L2 能力以及协作 L1 的公开结果。
- 跨域写入：目标领域公开 command；禁止直写目标存储。
- 跨域读取：目标领域公开 query/projection。

## 3. Journey / Scenario 职责

- [`JNY-001 / SCN-004`](../spec.md#scn-004)
  - 本领域负责：在“欢迎、授权、商业登录、Persona 与原动作续接”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：`user-identity-profile-relationship` 已交付其公开结果。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，形成该场景中本领域负责的终态。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。
- [`JNY-002 / SCN-005`](../spec.md#scn-005)
  - 本领域负责：在“原生首帧、Flutter 启动恢复与启动遥测”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：用户发起“原生首帧、Flutter 启动恢复与启动遥测”且身份、输入与权限前置成立。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，供 `product-ops-growth` 继续处理。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。
- [`JNY-004 / SCN-001`](../spec.md#scn-001)
  - 本领域负责：在“写文字创建、可靠发布与结果回流”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：`circle-community` 已交付其公开结果。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，供 `product-ops-growth` 继续处理。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。
- [`JNY-004 / SCN-002`](../spec.md#scn-002)
  - 本领域负责：在“照片创建、像素编辑、原图可靠上传与发布回流”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：`circle-community` 已交付其公开结果。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，供 `product-ops-growth` 继续处理。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。
- [`JNY-004 / SCN-003`](../spec.md#scn-003)
  - 本领域负责：在“视频创建、转码处理、发布与结果回流”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：`circle-community` 已交付其公开结果。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，供 `product-ops-growth` 继续处理。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。
- [`JNY-006 / SCN-006`](../spec.md#scn-006)
  - 本领域负责：在“全局无底栏页面边缘返回”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：用户发起“全局无底栏页面边缘返回”且身份、输入与权限前置成立。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，形成该场景中本领域负责的终态。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。
- [`JNY-006 / SCN-021`](../spec.md#scn-021)
  - 本领域负责：在“沉浸式媒体浏览器边缘滑动返回”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：用户发起“沉浸式媒体浏览器边缘滑动返回”且身份、输入与权限前置成立。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，供 `discovery-content` 继续处理。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。
- [`JNY-006 / SCN-022`](../spec.md#scn-022)
  - 本领域负责：在“主页边缘滑动退出保护”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：用户发起“主页边缘滑动退出保护”且身份、输入与权限前置成立。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，形成该场景中本领域负责的终态。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。
- [`JNY-007 / SCN-016`](../spec.md#scn-016)
  - 本领域负责：在“会话内音视频通话与离线来电可靠送达”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：`user-identity-profile-relationship` 已交付其公开结果。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，形成该场景中本领域负责的终态。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。
- [`JNY-009 / SCN-017`](../spec.md#scn-017)
  - 本领域负责：在“内容与页面上下文感知问答”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：`assistant-run-learning` 已交付其公开结果。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，供 `discovery-content` 继续处理。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。
- [`JNY-009 / SCN-018`](../spec.md#scn-018)
  - 本领域负责：在“群聊话题理解与会话内回复”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：`chat-conversation` 已交付其公开结果。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，形成该场景中本领域负责的终态。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。
- [`JNY-009 / SCN-020`](../spec.md#scn-020)
  - 本领域负责：在“小趣主动订阅与用户/会话投递”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：`chat-conversation` 已交付其公开结果。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，供 `user-identity-profile-relationship` 继续处理。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。
- [`JNY-010 / SCN-024`](../spec.md#scn-024)
  - 本领域负责：在“外链深链回流到 App 目标页”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：用户发起“外链深链回流到 App 目标页”且身份、输入与权限前置成立。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，形成该场景中本领域负责的终态。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。
- [`JNY-010 / SCN-025`](../spec.md#scn-025)
  - 本领域负责：在“公开 Web SEO 与安装转化”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
  - 进入条件：用户发起“公开 Web SEO 与安装转化”且身份、输入与权限前置成立。
  - 交付给下游的结果：提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实，供 `discovery-content` 继续处理。
  - 不负责：不推断或改写业务对象语义，不以 fallback 伪造业务成功。

- [`JNY-009 / SCN-034`](../spec.md#scn-034)
  - 本领域负责：提供 Connector/Provider/native continuation 的 typed capability、环境 Binding 与 conformance readiness。
  - 进入条件：目标 capability 在当前环境可用且授权成立。
  - 交付给下游的结果：结构化 readiness、invocation/native receipt 或可恢复 unavailable。
  - 不负责：不拥有 Skill/Run 或用户业务事实。
- [`JNY-013 / SCN-030`](../spec.md#scn-030)
  - 本领域负责：提供 Public Web、地图、日历/提醒和旅行外链的受控运行边界。
  - 进入条件：网络、Connector 和 surface policy 允许。
  - 交付给下游的结果：带来源/能力状态的 observation 或 receipt。
  - 不负责：不规划 GatheringPlan、不预订支付。
- [`JNY-013 / SCN-031`](../spec.md#scn-031)
  - 本领域负责：为主动提醒提供受管 Provider、后台执行与真实投递能力。
  - 进入条件：Trigger/Subscription 已由 Assistant 验证。
  - 交付给下游的结果：可追踪投递或结构化失败。
  - 不负责：不决定提醒内容和受众。

## 4. 业务能力

- [`deliver-deploy-prod-pipeline`](./deliver-deploy-prod-pipeline/spec.md)：以 `alpha-local`、`beta-local`、`gamma` 本地镜像和 `prod-hosted` 为环境边界，由 `stackctl` 与 GitHub Actions 统一完成打包、启动、健康检查、端云验证、灰度发布与回滚。
- [`development-workflow-governance`](./development-workflow-governance/spec.md)：让开发者、审核者和编程 Agent 使用同一套目录原生规格、动态上下文和可执行门禁完成需求理解、实现与验收。
- [`native-edge-gesture-navigation`](./native-edge-gesture-navigation/spec.md)：iOS/Android 边缘手势导航能力 SIT。
- [`runtime-agentpack`](./runtime-agentpack/spec.md)：按目标路径扫描目录与 Markdown，生成只读的最小规格上下文、特性树总览和 Git 增量影响报告；产物只写入 `.qwq_output`。
- [`runtime-assistant`](./runtime-assistant/spec.md)：SuggestedActionsGenerator：根据 PageContext + 内容分析 + 画像，按 8 种页面场景生成差异化建议操作。
- [`runtime-client-foundation`](./runtime-client-foundation/spec.md)：为 Flutter App 提供网络、缓存、本地化、日志、媒体与语义门禁等跨域基础能力
- [`runtime-codegen`](./runtime-codegen/spec.md)：将服务自治契约编译为一次性 ContractGraph 视图，并从统一 Source 生成端云产物。
- [`runtime-config`](./runtime-config/spec.md)：提供统一配置运行时能力，支持 env/file/secrets/config-center 多源读取与优先级合并。
- [`runtime-context`](./runtime-context/spec.md)：PageContext Manager：端侧上报 → 解析 → Redis 存储（支持 8 种页面场景，含 userActions 数组）。
- [`runtime-control-plane-foundation`](./runtime-control-plane-foundation/spec.md)：为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal`，统一门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口。
- [`runtime-data-engineering`](./runtime-data-engineering/spec.md)：`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入。
- [`runtime-errors`](./runtime-errors/spec.md)：提供统一错误码、错误对象、响应封装与 HTTP/RPC 状态映射。
- [`runtime-eventstore`](./runtime-eventstore/spec.md)：MongoDB events 集合持久化领域事件（aggregate_id, event_type, payload, timestamp, trace_id）。
- [`runtime-experiments`](./runtime-experiments/spec.md)：统一 runtime hash 分桶、推荐/搜索复用、实际流量归因及未绑定控制面 fail-closed。
- [`runtime-external-integration`](./runtime-external-integration/spec.md)：以能力专属 typed Port、Provider Adapter、构建期 BindingCompiler、统一 Conformance Suite、3×3 证据和双层 readiness 隔离第三方差异；integration-service 只是 runtime 治理的一种部署形态。
- [`runtime-governance`](./runtime-governance/spec.md)：提供统一服务治理装置：出站熔断、owner 侧并发背压、operation 准入负载摘除与 feature flag 判定。
- [`runtime-http`](./runtime-http/spec.md)：提供 HTTP server/client 运行时中间件管线与上下文传播封装。
- [`runtime-interceptor`](./runtime-interceptor/spec.md)：读链：api_exposure 字段过滤 → classification 脱敏（PII mask, SECRET drop）→ log_policy 日志记录。
- [`runtime-learning`](./runtime-learning/spec.md)：提供统一反馈事件、评分卡、评估记录与优化闭环版本化模型。
- [`runtime-media`](./runtime-media/spec.md)：四环境媒体交付、公开 slice key、播放器终态与防羊群验收。
- [`runtime-messaging`](./runtime-messaging/spec.md)：提供异步消息运行时语义层：envelope、schema、幂等、重试、死信与重放。
- [`runtime-observability`](./runtime-observability/spec.md)：提供统一观测内核：结构化日志、指标、追踪与导出适配。
- [`runtime-projector`](./runtime-projector/spec.md)：Projector 接口 + 事件消费框架（MQ consumer）。
- [`runtime-recommendation`](./runtime-recommendation/spec.md)：推荐运行时基础能力验收，覆盖 HotPath、SessionCache、Engine、Scorer、Rerank、降级与可观测。
- [`runtime-redis`](./runtime-redis/spec.md)：`runtime-redis` 提供跨服务一致的 Redis client、scene 连接池、健康检查和可观测机制。
- [`runtime-rpc`](./runtime-rpc/spec.md)：提供 gRPC/RPC 统一拦截器运行时能力，覆盖 metadata 传播、错误映射与治理策略接入。
- [`runtime-skill`](./runtime-skill/spec.md)：SkillRouter：根据 PageContext 场景 + 标签 → 匹配适用的 Skill。
- [`runtime-streaming`](./runtime-streaming/spec.md)：**SSEServer**：管理 SSE 连接（Connect/Push/Disconnect/Broadcast），按 userId 路由推送；支持 Last-Event-ID 续传。
- [`runtime-test-pyramid`](./runtime-test-pyramid/spec.md)：以 local_contract、api_integration、user_acceptance 形成唯一测试分层和环境证据模型。
- [`runtime-testinfra`](./runtime-testinfra/spec.md)：以 canonical 目录发现三层测试，以强类型请求按需准备隔离数据，并从真实执行、回读与清理生成证据。
- [`system-architecture-and-engineering-guide`](./system-architecture-and-engineering-guide/spec.md)：领域服务对象优先目录、metadata 单轨、四环境配置、唯一运行拓扑、外部能力和三层测试治理。

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 runtime 领域边界验收

- runtime L1、各 L2、共享 runtime 包、integration-service 和 quwoquan_ops 的工程映射清晰。
- integration-service 只作为 runtime 治理的独立机制进程，不登记为 integration L1。
- 外部 Provider 只经能力专属 typed Port 和显式 Adapter 装配；Alpha/Beta/Gamma required 验收绑定受管非生产租户的非内存 Provider，Prod 绑定正式生产租户，均无 Mock fallback。
- alpha/beta/gamma/prod 的 App 使用同一 production Remote composition；第一方业务数据只经 canonical immutable release importer 或所属领域公开 command 生效，环境启动与验证脚本不得注入 fixture。

<a id="req-002"></a>
### REQ-002 为所有云侧 **Go 服务**提供统一运行时能力，覆盖配置、错误、可观测、HTTP、RPC、消息、治理、实验与学习闭环

- 为所有云侧 **Go 服务**提供统一运行时能力，覆盖配置、错误、可观测、HTTP、RPC、消息、治理、实验与学习闭环。
- 目标是“服务只聚焦业务开发”，横切能力由 runtime 统一封装并复用。
- 业务服务不得重复实现横切基础能力，必须复用 runtime 子包。
- runtime 的契约、字段与元数据必须与 `quwoquan_service/contracts/*` 一致。
- runtime 变更必须遵循向后兼容与可回滚原则。
- 外部能力必须经能力专属 typed Port 与登记的 Provider Adapter；运行时不得扫描 metadata
- 日志/指标/追踪字段统一可检索

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 runtime 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：runtime L1、各 L2、共享 runtime 包、integration-service 和 quwoquan_ops 的工程映射清晰。
- integration-service 只作为 runtime 治理的独立机制进程，不登记为 integration L1。
- 外部 Provider 只经能力专属 typed Port 和显式 Adapter 装配；Alpha/Beta/Gamma required 验收绑定受管非生产租户的非内存 Provider，Prod 绑定正式生产租户，均无 Mock fallback。
- alpha/beta/gamma/prod 的 App composition 与第一方数据入口保持单轨；测试 double、环境 fixture 与第三方 substitute 均不得成为 App 业务成功事实。
- 禁止结果：domain/application 不依赖 adapters/infrastructure 或 Vendor SDK。
- 独立机制进程不拥有业务 aggregate，不复制业务对象真相源。
- 环境和 rollout stage 只作为三层测试证据维度。

## 7. 工程归属

- App：`quwoquan_app`（仅拥有 App 项目级构建与平台壳，不作为业务 domain fallback）、`quwoquan_app/lib/runtime`、`quwoquan_app/lib/design_system`、`quwoquan_app/lib/l10n`、`quwoquan_app/lib/service/integration_service`
- Metadata：`quwoquan_service/contracts/metadata/_shared`
- Metadata（协作引用，不用于代码归属）：`quwoquan_service/services/integration-service/contracts`
- Service：`quwoquan_service`（跨域基础设施、生成链与未被更具体 L1 路径认领的 Service 工程根）、`quwoquan_service/contracts`
- Service：`quwoquan_service/services/integration-service`（外部能力机制进程）
- Service（协作引用，不用于代码归属）：`quwoquan_service/runtime`、`quwoquan_ops`
- 测试：
  - `local_contract`：`quwoquan_service/runtime`、`quwoquan_app/test/local_contract/journeys/connector_management`
  - `api_integration`：`quwoquan_ops/tests`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`、`quwoquan_app/test/user_acceptance/journeys/app_startup`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：runtime L1、各 L2、共享 runtime 包、integration-service 和 quwoquan_ops 的工程映射清晰。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 Skill 发布生命周期

- 类型：`future_plan`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：当前只有 Skill 路由能力，尚无持久化的注册、审核、灰度、发布与归档生命周期。
- 完成判定：形成可观察的 Skill owner、发布状态机和回滚验收后，再建立独立 L2/L3。

<a id="open-003"></a>
### OPEN-003 业务对象 SLI 绑定

- 类型：`future_plan`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：现有 metrics/observability 能力尚未提供按业务对象与特性绑定 SLI 的正式契约。
- 完成判定：明确指标 owner、低基数约束和查询/告警消费方后，再建立独立 L2/L3。
