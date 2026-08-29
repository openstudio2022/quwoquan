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
- [`system-topology-and-networking`](./system-topology-and-networking/spec.md)：南北向公开入口（gateway/DNS/TLS/CDN）与东西向平面组网（子网四平面、端口块、east-west URL）的唯一叙事收口，字面值只引用环境 YAML 真相源。
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 四环境 App Remote composition 显式且唯一
- 决策：alpha/beta/gamma/prod 的 App 统一使用 production Remote composition；环境只选择 runtime package、endpoint、容量和 rollout stage。
- 理由：runtime 负责装配机制而不拥有业务事实；把环境名映射成 App 内 Mock 会绕过服务、数据 release、媒体与错误恢复主线。
- 被否决方案：Alpha runner/mock package、Mock/Remote 运行时开关、环境启动器或 UAT 注入 fixture、服务失败后返回本地合成成功。
- 约束与影响：第一方业务事实只经 canonical release importer 或所属领域公开 command；测试 double 只在 local_contract 测试树，第三方 local substitute 只在服务防腐层。
- 关联要求：`REQ-001`
- 关联能力：[`deliver-deploy-prod-pipeline`](./deliver-deploy-prod-pipeline/spec.md)、[`development-workflow-governance`](./development-workflow-governance/spec.md)、[`native-edge-gesture-navigation`](./native-edge-gesture-navigation/spec.md)、[`runtime-agentpack`](./runtime-agentpack/spec.md)、[`runtime-assistant`](./runtime-assistant/spec.md)、[`runtime-client-foundation`](./runtime-client-foundation/spec.md)、[`runtime-codegen`](./runtime-codegen/spec.md)、[`runtime-config`](./runtime-config/spec.md)、[`runtime-context`](./runtime-context/spec.md)、[`runtime-control-plane-foundation`](./runtime-control-plane-foundation/spec.md)、[`runtime-data-engineering`](./runtime-data-engineering/spec.md)、[`runtime-errors`](./runtime-errors/spec.md)、[`runtime-eventstore`](./runtime-eventstore/spec.md)、[`runtime-experiments`](./runtime-experiments/spec.md)、[`runtime-external-integration`](./runtime-external-integration/spec.md)、[`runtime-governance`](./runtime-governance/spec.md)、[`runtime-http`](./runtime-http/spec.md)、[`runtime-interceptor`](./runtime-interceptor/spec.md)、[`runtime-learning`](./runtime-learning/spec.md)、[`runtime-media`](./runtime-media/spec.md)、[`runtime-messaging`](./runtime-messaging/spec.md)、[`runtime-observability`](./runtime-observability/spec.md)、[`runtime-projector`](./runtime-projector/spec.md)、[`runtime-recommendation`](./runtime-recommendation/spec.md)、[`runtime-redis`](./runtime-redis/spec.md)、[`runtime-rpc`](./runtime-rpc/spec.md)、[`runtime-skill`](./runtime-skill/spec.md)、[`runtime-streaming`](./runtime-streaming/spec.md)、[`runtime-test-pyramid`](./runtime-test-pyramid/spec.md)、[`runtime-testinfra`](./runtime-testinfra/spec.md)、[`system-architecture-and-engineering-guide`](./system-architecture-and-engineering-guide/spec.md)

<a id="dec-002"></a>
### DEC-002 可执行字节按信任域构建且环境配置在装配期绑定

- 决策：同一受控 source capsule 先生成一个 `releaseTrainId`，再按 `nonprod/prod` 信任域构建不可变组件。Alpha、Beta、Gamma 引用同一 nonprod App 与同一 owner 的 nonprod Cloud digest，Prod 引用独立 prod digest。四环境继续各自生成配置、SecretRef、endpoint、拓扑和 activation receipt，并在 release composition 中与兼容的组件摘要组合。
- 决策：端侧由 `buildProfile` flavor/scheme 在原生构建图解析前绑定 application/bundle ID、签名、entitlements 与第三方 SDK 注册身份。环境名和 endpoint 只来自带 schema、签名、签发时间与 source digest 的 runtime config package。nonprod package 只允许 Alpha、Beta、Gamma，prod package 只允许 Prod，启动握手必须在进入业务 Shell 前验证 profile、environment、target、摘要和 staleness。
- 决策：云侧每个服务仍以四环境目录独立 author 配置，但配置与 artifact identity 由部署面挂载。external Provider binding 保留编译期防污染边界并按信任域固化，前提是 Alpha、Beta、Gamma 的 binding 声明先收敛为同一 nonprod 视图。`APP_ENV` 只校验已装配配置的环境身份，不选择 Adapter、数据源或策略。
- 决策：`prod-sim` 与 `prod-hosted` 同属 Prod 环境但拥有不同 target activation seal。prevalidate 与 rollout 只改变配置、authority receipt 或流量 activation，不重构同一组件字节。
- 理由：环境差异属于配置与运行事实，不属于 compiler identity。按环境重复编译会扩大过期组合并让每次验证绑定不同字节。信任域构建与环境装配分离既阻断非生产 Provider 或身份进入 Prod，又允许未变组件按真实 digest 复用。
- 被否决方案：按四环境重复编译、按渠道构建 APK、把 endpoint 或 rollout stage 写入字节、让 prod binary 读取 nonprod 配置、保留环境 flavor 与 profile flavor 双轨，以及以 cache/tag 冒充经过签名和 provenance 验证的组件。
- 失败恢复：profile、runtime config、签名、摘要、target、environment 或 staleness 任一不一致时 fail-closed。回滚只重新组合上一份已验证组件摘要与对应环境配置，不允许混搭信任域或把失败降级为空配置继续运行。
- 可测试观察面：local_contract 证明 Android/iOS 只有 nonprod/prod identity，Web 只有一个 build shard，Alpha/Beta/Gamma 引用相同 nonprod bytes digest。
- 可测试观察面：api_integration 证明同一 nonprod bytes 分别装配 Alpha 与 Gamma 配置后 endpoint 和数据隔离正确，错配或过期配置在业务 listener 前失败。
- 可测试观察面：user_acceptance 仍按 Alpha、Beta、Gamma、Prod 顺序回读 App、服务、配置和 activation identity，且 stage 或渠道变化不产生新组件。
- 影响能力：[`runtime-config`](./runtime-config/spec.md)、[`deliver-deploy-prod-pipeline`](./deliver-deploy-prod-pipeline/spec.md)、[`runtime-external-integration`](./runtime-external-integration/spec.md)

<a id="dec-003"></a>
### DEC-003 组网事实单轨叙事与供应商中立收敛

- 决策：南北向公开入口与东西向平面组网只有一套叙事（[`system-topology-and-networking`](./system-topology-and-networking/spec.md)）与唯一 YAML 真相源（`domain_governance.yaml`、各环境 `runtime.yaml`、`local_env_port_manifest.yaml`、`prod/access-isolation.yaml`）；公开入口只经 `runtime.yaml → target resolver → manifest` 唯一数据流生成，规格正文不复制 host、端口、CIDR、账号字面值。
- 决策：公网 DNS 收敛按记录类型划分所有权——地址类型与 zone 级授权类型由计划完全拥有，`TXT` 为共享类型只拥有自己声明的 `v=` 方法；权威写入只经供应商中立 provider 接口，DoH 证据必须来自独立于权威服务商的双公共解析器。
- 决策：`prod-hosted` 运维访问按 `edge / media / service / data` 四平面隔离，平面、账号与凭据投影事实只由 `prod/access-isolation.yaml` 拥有。
- 理由：组网事实曾散落在 L3 打包 Story 叙事与 ops 文档中，agent 与开发者需跨文件拼凑；字面值多处复制已产生第二真相源与维度清单漂移。
- 被否决方案：组网叙事继续留在 L3 打包 Story，导致叙事与装配耦合。
- 被否决方案：新建组网 L1（违反「部署边界不形成新 L1」）；在规格正文复制 YAML 字面值。
- 可测试观察面：domain governance / stackctl 既有门禁测试；L2 SIT 直绑证据由该 spec `OPEN-001` 承接。
- 影响能力：[`system-topology-and-networking`](./system-topology-and-networking/spec.md)、[`runtime-config`](./runtime-config/spec.md)、[`deliver-deploy-prod-pipeline`](./deliver-deploy-prod-pipeline/spec.md)

<a id="dec-004"></a>
### DEC-004 冷启动按最小 authority 闭包破环，业务 admission 不旁路

- 决策：当完整拓扑存在“业务服务 readiness 等待控制面事实、控制面 readiness 又等待该业务进程承载的 authority”循环时，环境编排只先拉起基础设施与 authority owner 进程，并消费 owner 已声明的精确内部 pre-admission 健康面；随后启动控制面、通过原公开鉴权 command 写入事实，最后进入完整拓扑 up。
- 决策：当前实验策略冷启动顺序固定为 `基础设施 -> service-core authority owner (--no-deps) -> service-core shallow /healthz -> product-ops (--no-deps) -> Product Ops 公开策略 command -> 完整业务栈`。`service-core` 容器 healthcheck 只探 liveness，用于证明全部 module 已完成 Build/Bind/Start；不得通过 Compose dependency graph 或 aggregate `/readyz` 等待策略事实，也不得为破环放宽 Product Ops 公共 operation、直写存储或注入服务私有策略。
- 理由：`service-core` 的 Search/Recommendation aggregate readiness 等待 `ExperimentPolicyActivated`，而 Product Ops 的账号安全 readiness 需要 `service-core` 内 UserAccount authority；只启动 Product Ops 会让其 admission 永久关闭，但不等待 owner 的 shallow health 又会把 module 构造失败误记为短暂竞态。
- 被否决方案：扩大 503 重试集合或无限延长 deadline、取消账号安全 readiness、把 Product Ops command 加入公共 pre-admission、数据库/Redis seed、以及先沿 Compose dependency graph 或 aggregate `/readyz` 等待完整业务 readiness。
- 失败恢复：authority owner 进程退出、内部健康面不可达、Product Ops admission 未开放或公开 command 失败时保留首个 typed blocker，逆序清理本 attempt；不得将部分容器或 package PASS 记为运行健康。
- 可测试观察面：local_contract 锁定上述顺序、`--no-deps` 破环与公开 command 单轨；真实环境验收绑定同一 candidate 的 package、startup attempt、policy receipt、strict health 和逆序 teardown。
- 影响能力：[`deliver-deploy-prod-pipeline`](./deliver-deploy-prod-pipeline/spec.md)、[`runtime-config`](./runtime-config/spec.md)、[`runtime-governance`](./runtime-governance/spec.md)

## 6. 质量与运行约束

- 环境和 rollout stage 是证据维度。任何商用外部能力缺 Gamma Port 对等替身证据、Prod 真实 Adapter 证据、观测或回滚均不能准出。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
