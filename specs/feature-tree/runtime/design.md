# L1 Design：runtime（统一运行时能力域） (`runtime`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：runtime 作为跨端云机制领域服务，治理共享 runtime 包和 integration-service 等独立机制 进程；部署边界不形成新的 L1，业务对象与 Vendor SDK 不得穿透。

## 2. 领域模型与所有权

- authoritative ownership：拥有跨服务运行机制的配置解析、错误信封、传输、缓存、投影、事件、观测、测试基础设施和发布编排契约；不拥有业务聚合事实。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- [`JNY-001 / SCN-004`](../spec.md#scn-004) — 在“欢迎、授权、商业登录、Persona 与原动作续接”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
- [`JNY-002 / SCN-005`](../spec.md#scn-005) — 在“原生首帧、Flutter 启动恢复与启动遥测”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
- [`JNY-004 / SCN-001`](../spec.md#scn-001) — 在“写文字创建、可靠发布与结果回流”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
- [`JNY-004 / SCN-002`](../spec.md#scn-002) — 在“照片创建、像素编辑、原图可靠上传与发布回流”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
- [`JNY-004 / SCN-003`](../spec.md#scn-003) — 在“视频创建、转码处理、发布与结果回流”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
- [`JNY-006 / SCN-006`](../spec.md#scn-006) — 在“全局无底栏页面边缘返回”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
- [`JNY-006 / SCN-021`](../spec.md#scn-021) — 在“沉浸式媒体浏览器边缘滑动返回”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。
- [`JNY-006 / SCN-022`](../spec.md#scn-022) — 在“主页边缘滑动退出保护”中，提供启动、导航、传输、外部 Provider、错误恢复和环境装配机制，不持有业务对象事实。

## 4. 架构与数据流

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
- [`runtime-governance`](./runtime-governance/spec.md)：提供统一服务治理策略引擎：timeout、retry、circuit-breaker、rate-limit、degrade。
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
- [`runtime-testinfra`](./runtime-testinfra/spec.md)：以物理目录扫描和运行报告提供三层测试证据，不维护路径登记或目录清单。
- [`system-architecture-and-engineering-guide`](./system-architecture-and-engineering-guide/spec.md)：领域服务对象优先目录、metadata 单轨、四环境配置、唯一运行拓扑、外部能力和三层测试治理。
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 composition root 显式选择
- 决策：composition root 显式选择。
- 理由：runtime 作为跨端云机制领域服务，治理共享 runtime 包和 integration-service 等独立机制 进程；部署边界不形成新的 L1，业务对象与 Vendor SDK 不得穿透。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 关联能力：[`deliver-deploy-prod-pipeline`](./deliver-deploy-prod-pipeline/spec.md)、[`development-workflow-governance`](./development-workflow-governance/spec.md)、[`native-edge-gesture-navigation`](./native-edge-gesture-navigation/spec.md)、[`runtime-agentpack`](./runtime-agentpack/spec.md)、[`runtime-assistant`](./runtime-assistant/spec.md)、[`runtime-client-foundation`](./runtime-client-foundation/spec.md)、[`runtime-codegen`](./runtime-codegen/spec.md)、[`runtime-config`](./runtime-config/spec.md)、[`runtime-context`](./runtime-context/spec.md)、[`runtime-control-plane-foundation`](./runtime-control-plane-foundation/spec.md)、[`runtime-data-engineering`](./runtime-data-engineering/spec.md)、[`runtime-errors`](./runtime-errors/spec.md)、[`runtime-eventstore`](./runtime-eventstore/spec.md)、[`runtime-experiments`](./runtime-experiments/spec.md)、[`runtime-external-integration`](./runtime-external-integration/spec.md)、[`runtime-governance`](./runtime-governance/spec.md)、[`runtime-http`](./runtime-http/spec.md)、[`runtime-interceptor`](./runtime-interceptor/spec.md)、[`runtime-learning`](./runtime-learning/spec.md)、[`runtime-media`](./runtime-media/spec.md)、[`runtime-messaging`](./runtime-messaging/spec.md)、[`runtime-observability`](./runtime-observability/spec.md)、[`runtime-projector`](./runtime-projector/spec.md)、[`runtime-recommendation`](./runtime-recommendation/spec.md)、[`runtime-redis`](./runtime-redis/spec.md)、[`runtime-rpc`](./runtime-rpc/spec.md)、[`runtime-skill`](./runtime-skill/spec.md)、[`runtime-streaming`](./runtime-streaming/spec.md)、[`runtime-test-pyramid`](./runtime-test-pyramid/spec.md)、[`runtime-testinfra`](./runtime-testinfra/spec.md)、[`system-architecture-and-engineering-guide`](./system-architecture-and-engineering-guide/spec.md)

## 6. 质量与运行约束

- 环境和 rollout stage 是证据维度。任何商用外部能力缺 Gamma Port 对等替身证据、Prod 真实 Adapter 证据、观测或回滚均不能准出。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
