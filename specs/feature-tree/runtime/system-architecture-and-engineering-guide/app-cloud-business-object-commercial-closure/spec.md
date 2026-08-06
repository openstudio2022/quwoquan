# L3 Story：App Cloud 业务对象商用闭环 (`app-cloud-business-object-commercial-closure`)

> 所属能力：[`system-architecture-and-engineering-guide`](../spec.md)

> Journey / Scenario：AppRoot 当前全部 Journey；统一准出锚点为 [`REQ-009`](../../../spec.md#req-009)、[`REQ-010`](../../../spec.md#req-010) 与 [`UAT-009`](../../../spec.md#uat-009)。

> 设计归属：[L2 DEC-001](../design.md#dec-001)、[DEC-018](../design.md#dec-018) 与 [DEC-019](../design.md#dec-019)

## 1. 用户价值

作为维护端云契约的开发者，
我希望从服务本地 contracts 幂等生成并校验 App 与服务共用的业务对象合同，
从而避免手写类型和派生索引成为第二真相源。

## 2. 范围与非目标

### In Scope

- 服务本地 contracts 到 ContractGraph、服务端安全描述符、App typed client 与 generated manifest 的单一生成链。
- App 业务对象纵切、能力驱动层义务、页面 source owner/participants、依赖 DAG 与旧目录单轨退役。
- App Remote composition、服务端 operation/object guard、Cloud runtime 单轨和 test-only double 物理隔离。
- 当前全部 AppRoot Journey 的三层 CaseResult、四环境制品、Provider、SLO、灰度与回滚证据闭环。

### Out of Scope

- 通用 CRUD 框架、通用事件溯源、分布式事务或通用 Saga。
- 推荐、内容生产和 edge-media 内部算法。
- 父能力中由其他 Story 独立拥有的产品行为与领域事实。
- `commercial.targetStory` 指向其他节点的 blocked operation 的产品行为与商用证据闭环。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 App Cloud 业务对象商用闭环

- ContractGraph validate/generate/check 可在 clean checkout 幂等重生。

<a id="req-002"></a>
### REQ-002 App 只消费业务对象类型化 ContractGraph

- ContractGraph validate/generate/check 可在 clean checkout 幂等重生。
- canonical object 与 App-exposed operation coverage 均为 100%。

<a id="req-003"></a>
### REQ-003 服务端从可信 principal 执行 operation 与对象授权

- required operation 服务端 guard 覆盖率为 100%。
- 每个对象的身份拒绝错误由本对象 `errors.yaml` 唯一拥有并生成；禁止从兄弟对象借用通用错误码。
- RTC/Realtime、Chat/Content Media、Assistant consent、Behavior/Ops 的跨 actor 拒绝语义必须有直接负向测试证据。
- production 缺 JWT key/issuer/audience 时启动失败且不存在默认 secret。

<a id="req-004"></a>
### REQ-004 四环境 Remote 与 test-only double 物理隔离

- App 内 Mock 顶层类、fixture runtime loader、空 Remote 和 fallback 数量为 0。
- alpha/beta/gamma/prod dependency resolution、kernel/AOT/SBOM 与 Remote wiring 必须由可执行门禁直接证明。

<a id="req-005"></a>
### REQ-005 Runtime 对 deadline cancellation retry error telemetry 语义唯一

- Cloud 只有一条 context/config/transport/error/telemetry 执行链。
- Runtime import DAG、generated-client-only 与 `RuntimeFailure` 零旁路必须由可执行门禁直接证明。

<a id="req-006"></a>
### REQ-006 当前全部真实 Remote Scenario 完成商业准出

- local_contract、api_integration、user_acceptance 均有真实 CaseResult。
- retired/Mock/fixture/empty Remote/reverse import/dynamic skip/path-UAT 全部为 0。
- production AOT/SBOM、Web release、OHOS HAP、SLO、灰度和回滚证据绑定同一不可变候选。

<a id="req-007"></a>
### REQ-007 L3 Story 与 AppRoot 十条 Scenario 双向可追踪

- 父 L2 的 Story 列表与目录一致，AppRoot Scenario 与参与 L1 双向引用。
- 本 Story 只保留 `spec.md`，设计归属上收到 L2 DEC。
- 测试 `spec_ref` 必须指向现存 GWT/SIT/UAT 锚点。

<a id="req-008"></a>
### REQ-008 App application coordinator 只组合无需原子一致的少量 capability；稳定排序、统一权限或复用页面 Slice 由服务端 projection owner 提供

- App application coordinator 只组合无需原子一致的少量 capability；稳定排序、统一权限或复用页面 Slice 由服务端 projection owner 提供。
- command 仅在 metadata 声明幂等且具有 key 时允许重试。
- deadline 使用剩余预算并向 HTTP、数据库、对象存储和消息执行传播。
- 取消后不得继续产生副作用。

<a id="req-009"></a>
### REQ-009 blocked operation 的收口节点由 targetStory 唯一决定

- 每个 `commercial.status=blocked` 的 operation 只由其 `commercial.targetStory` 指向的节点拥有；本 Story 不代持其他节点的商用缺口。
- 本 Story 拥有的只有两类：领域模型治理类 gapId，以及 targetStory 指向本 Story 的同一候选四环境证据类 gapId。
- 领域模型治理类缺口靠对象与 operation 建模裁决关闭，四环境证据类缺口靠同一不可变候选上的真实环境、Provider 与 user_acceptance 回执关闭，两类不得互相替代。
- 缺真实四环境、Provider 或 user_acceptance 回执时，`commercial.status` 不得从 blocked 改为 ready，readiness 派生也不得把该 operation 计入 commercial-ready。

<a id="req-010"></a>
### REQ-010 App typed client 由 ui_surfaces 与 response_entity 单轨派生

- App typed client 的唯一真相源是 `quwoquan_service/contracts/metadata/_shared/ui_surfaces.yaml` 的 `surfaces[].operation_ids`，`clientContract` 的 dartImport、responseType 与 responseDecoder 由 ContractGraph 从 `response_entity` 派生。
- `operations.yaml` 禁止手写 `client_contract`，声明即以 `CONTRACT.APP_SURFACE.CLIENT_CONTRACT_SECOND_TRUTH` 阻断。
- `/internal/` 前缀且 principal 为 service 的服务间路由没有 `clientContract` 是设计正确结果，不计为缺口；App 不应持有 service scope token。
- 判断某对象读路径是否健全，看承载该读路径的 App 面 operation，该 operation 可能属于另一个域的对象。

<a id="req-011"></a>
### REQ-011 长连接 operation 用三个独立上限表达预算，标量超时由其派生

- `reliability.timeout_ms` 是一次请求从准入到响应完成的整体预算，只有存在「响应完成」瞬间的 operation 能声明它。
- 长连接没有该瞬间，声明流式 surface 的 operation 必须改为声明 `reliability.stream_budget`，其三个字段回答三个互不替代的问题：`handshake_ms` 约束「连接已被接受却一个字节都没产出」，`idle_ms` 约束「连接还在但生产方停止推进」，`max_duration_ms` 约束「连接再健康也要关闭」。
- 二者互斥：流式 operation 禁止书写 `timeout_ms`，其 descriptor 的 `timeout_ms` 由 `max_duration_ms` 单向派生，只服务于只理解单一数字的既有消费者；非流式 operation 禁止声明 `stream_budget`。
- `handshake_ms` 与 `idle_ms` 必须严格小于 `max_duration_ms`，否则该上限永远不可达，等于未声明。
- 心跳注释不得重置 `idle_ms`：停摆的生产方同样发心跳，把心跳计为推进会让空闲上限永不触发；持续产出 payload frame 的正常长 run 不受空闲上限影响。
- 三个上限必须从生成的 descriptor 派生并在传输层真实强制；`http.Server.WriteTimeout` 等每连接一次、不随 flush 刷新的传输值不得成为长连接的实际上限，服务器写上限按最宽 unary 预算取值。
- 触达空闲或总时长上限只关闭连接，不改变聚合状态、不合成终态事件；客户端凭 `streaming.resume_request_field` 续传。

<a id="req-012"></a>
### REQ-012 App 对象源码、页面与测试由同一 canonical 身份闭环

- App 业务源码只位于 `lib/<domain>/<context>/<object>/{domain,application,adapters,presentation}`，对象测试按同一 domain/context/object 身份位于三层测试树；业务文件无 owner、同优先级多 owner、旧业务大桶或兼容路径任一存在时均不得通过架构准出。
- 对象的 App 必需层由其 App-exposed operation、页面认领和端侧不变式决定，不能从云侧 kind 无条件生成，也不能以目录或占位文件存在反推能力已实现。
- 页面必须有唯一 source owner 并保留全部 participant object；多对象页面由 source owner 的 presentation 经 participant 的公开 application 边界组合，禁止直接引用兄弟对象私有层。
- production 依赖图只允许父级 DEC 声明的单向层关系，具体 adapter 只在唯一 `runtime/di` composition root 装配；barrel re-export、旧路径 shim、双轨 import 和 runtime fallback 数量为零。

## 4. 契约引用

- canonical：[`L2 DEC-001`](../design.md#dec-001)
- canonical：[`L2 DEC-018`](../design.md#dec-018)
- canonical：[`L2 DEC-019`](../design.md#dec-019)
- canonical：`quwoquan_service/contracts/metadata`
- canonical：`quwoquan_service/contracts/metadata/_schemas/context.schema.json`
- canonical：`quwoquan_service/contracts/metadata/_schemas/object.schema.json`
- canonical：`quwoquan_service/contracts/metadata/_schemas/operations.schema.json`
- canonical：`quwoquan_service/contracts/metadata/_schemas/contract_graph.schema.json`
- canonical：`quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml`
- canonical：`specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md`
- canonical：`quwoquan_service/runtime/auth`
- canonical：`quwoquan_ops/environments`
- canonical：本文件 `REQ-004`、`GWT-004` 与 `OPEN-004`
- canonical：`quwoquan_app/packages/quwoquan_cloud_contracts`
- canonical：`quwoquan_app/lib/<domain>/<context>/<object>`
- canonical：`quwoquan_app/lib/runtime/di`
- canonical：[`AppRoot REQ-009`](../../../spec.md#req-009)
- canonical：[`AppRoot REQ-010`](../../../spec.md#req-010)
- canonical：[`AppRoot UAT-009`](../../../spec.md#uat-009)
- canonical：`quwoquan_ops/environments/gamma/validation_suites.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 App Cloud 业务对象商用闭环

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“App Cloud 业务对象商用闭环”对应的公开行为。
- THEN ContractGraph validate/generate/check 可在 clean checkout 幂等重生。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 App 只消费业务对象类型化 ContractGraph

- GIVEN App 需要访问服务业务对象。
- WHEN 端侧生成并装配业务对象客户端。
- THEN canonical object 与 App-exposed operation coverage 均为 100%，且不保留手写业务类型副本。

<a id="gwt-003"></a>
### GWT-003 服务端从可信 principal 执行 operation 与对象授权

- GIVEN 请求携带可验证 principal 或缺失、过期、越权身份。
- WHEN 服务端执行业务 operation。
- THEN 仅可信 principal 可通过对应 guard，拒绝结果使用 canonical failure 且不产生业务写入。

<a id="gwt-004"></a>
### GWT-004 四环境 Remote 与 test-only double 物理隔离

- GIVEN 分别装配 alpha、beta、gamma、prod 运行入口与 local_contract。
- WHEN 构建依赖图、kernel/AOT 与 SBOM。
- THEN 四环境 artifact 只包含 Remote 和真实基础设施，typed double 仅存在 local_contract 测试树。

<a id="gwt-005"></a>
### GWT-005 Runtime 对 deadline cancellation retry error telemetry 语义唯一

- GIVEN Cloud 请求经过 context、config、transport、error 与 telemetry 链。
- WHEN 请求超时、取消、重试或失败。
- THEN 运行时只使用一条可追踪执行链，并按 canonical failure 和恢复语义结束。

<a id="gwt-006"></a>
### GWT-006 当前全部真实 Remote Scenario 完成商业准出

- GIVEN 同一不可变候选已部署到声明环境。
- WHEN 当前全部 AppRoot Remote Scenario 分别执行 local_contract、api_integration 与 user_acceptance。
- THEN 三层结果、制品摘要、SLO、灰度与回滚证据可关联到该唯一不可变候选。

<a id="gwt-007"></a>
### GWT-007 App 对象纵切与页面参与关系单轨准出

- GIVEN ContractGraph、所属 L1 工程归属、页面对象契约与 App production/test 树均来自同一受版本控制候选。
- WHEN 架构与测试治理按 domain/context/object 反向解析全部 App 业务文件、页面和测试。
- THEN 每个文件均有唯一对象或横切 owner，必需层与页面 source owner/participants 完整且没有占位层。
- AND 层间与跨对象依赖只经过公开边界和唯一 composition root，旧业务大桶、私有跨对象 import、barrel、shim、双轨路径与 compatibility fallback 均不存在。

## 6. 依赖

- 前置要求：[`system-architecture-and-engineering-guide`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)、[DEC-018](../design.md#dec-018) 与 [DEC-019](../design.md#dec-019)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 DDD/CQRS 业务对象架构硬门

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前 ContractGraph 已能生成对象 roster 与部分结构性 readiness evidence，但 App 仍处于旧业务大桶和对象纵切并存状态；存在无法精确归属的业务文件、对象必需层缺口、多对象页面 source owner/participants 未闭环、反向依赖与旧路径残留，因此文件存在和局部门禁绿灯均不能证明模型治理完成。
- 当前多卡口必须分别关闭：App 全文件唯一 owner 与精确目标路径、能力驱动层义务、页面 source owner/participants、层间与跨对象依赖 DAG、三层对象同构测试、对象级覆盖率、结构证据与 runner 结果证据分离，以及零 legacy residue/allowance/shim。
- readinessEvidence 的静态结构 packet 与动态 result/receipt 类型已存在不等于测试执行、四环境或用户验收已通过；对象级 readiness case、生产 runner、canonical snapshot authority 与当前 receipt 接入尚未完整闭环时，对象最多停在 implemented。
- 本 OPEN 只关闭领域模型与工程治理；`commercial.targetStory` 指向其他节点的产品行为、Provider、四环境和 UAT 缺口仍由其唯一目标节点关闭，不得在本 OPEN 内代持，也不得用目录迁移替代。
- canonical 对象与 context 集合只从同一 ContractGraph 候选实时派生，不维护固定数量、对象 registry、迁移清单或第二套 readiness 台账。
- 上述任一结构、依赖、测试、覆盖率或证据边界未闭环时，本 OPEN 不得删除，也不得声明 `MODEL_GOVERNANCE_READY`。
- 完成判定：`GWT-001` 与 `GWT-007` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-007"></a>
### OPEN-007 lifecycle 声明的投影缺源码存在性校验

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前没有门禁能证明 `object.yaml` 的 `lifecycle.source_events` 声明的投影确实有对应 projector 源码，按 `DEC-011` 去掉 projector 入口后，契约层与源码之间失去了原有绑定点。
- 声明存在而 projector 源码缺失时，对象仍会被计为 contract-ready，投影缺失只能在运行期由数据不一致暴露。
- 关闭方式是补一条 lifecycle 到 projector 源码的存在性校验，把声明的 `source_events` 与该对象 application 或 adapters 层的实际 projector 实现绑定。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 服务端从可信 principal 执行 operation 与对象授权

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺每个服务 production composition root 对 required operation 的 100% 挂载覆盖报告与同一候选环境拒绝回执；ContractGraph 已为全部 operation 生成 fail-closed descriptor，runtime guard 与重点跨 actor 负向测试已通过。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 四环境 Remote 与 test-only double 物理隔离

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺同一候选的 alpha/beta/gamma/prod dependency/kernel/AOT/SBOM、双端安装包与 UAT transitive import 回执；静态纯度、包依赖与 Remote 单轨门已通过。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-006"></a>
### OPEN-006 当前全部真实 Remote Scenario 完成商业准出

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺当前全部 AppRoot Journey 在同一候选上的 alpha/beta/gamma/prod 真实 user_acceptance、Provider、SLO、灰度与回滚 CaseResult；局部 local_contract 与 api_integration 已有直接证据，但 ContractGraph 仍有 blocked operation。
- targetStory 指向本 Story 的四环境证据类 gapId 为 NOTIFICATION_DELIVERY_JOB_GAMMA_PROVIDER、OPS_EVENT_RECORD_PROVIDER_EVIDENCE、REALTIME_CONNECTION_COMMERCIAL_EVIDENCE、CONTENT_PROFILE_INTERACTION_ENV_EVIDENCE、CONTENT_PROFILE_INTERACTION_READ_ENV_EVIDENCE、CONTENT_MEDIA_GAMMA_UAT、OUTBOUND_SHARE_FACT_GAMMA_UAT 与 ASSISTANT_TURN_VIEW_COMMERCIAL_EVIDENCE。
- 这一组属于同一候选四环境证据缺口，不属于领域模型治理缺口，关闭依据是真实环境、Provider 与 user_acceptance 回执，而不是重新建模。
- targetStory 指向 `user-connector-capability-gateway`、`four-environment-commercial-login-maturity`、`account-moderation-and-appeal-enforcement`、`account-suspension-and-appeal-lifecycle`、`session-preference-memory-control`、`shared-surface-skill-placement`、`bucketing-strategy-engine`、`realtime-call-media-infrastructure`、`circle-community-gathering-coordination`、`durable-agent-run-orchestration`、`adaptive-presentation-runtime` 与 travel-journey 各 Story 的 blocked operation 由这些节点各自拥有，本 OPEN 不代持其证据。
- 完成判定：`GWT-006` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-008"></a>
### OPEN-008 部分对象有类型化客户端但无页面消费证明

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：存在一批对象已由 ContractGraph 派生出端侧类型化客户端，却既未被任何页面在 `object_ids` 中认领，也没有任何页面 `query_slices` 指向，因此无法证明这些类型化客户端被真实页面消费。
- 判定负担在页面契约侧：要么由消费页面在 `quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml` 补认领或补读模型血缘，要么证明该对象的读路径由另一域的 App 面操作承载并据此撤下类型化客户端。
- 禁止用域粒度的 `data_owners` 做交叉证明；域粒度匹配会让任意对象都自动通过，等于作废该断言。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-009"></a>
### OPEN-009 WebSocket stream budget 已落源，等待唯一 fresh generated descriptor 验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前尚缺唯一 fresh generation 的 descriptor、lock 与 manifest 验收证据。Cloud source 与 runtime 已完成单轨切换：`realtime.connection.WebSocketUpgrade` 声明 `stream_budget` 为 `handshake_ms=5000`、`idle_ms=90000`、`max_duration_ms=1800000`，旧 `timeout_ms` 已删除。generated descriptor admission、`BudgetGuard` 与 hijack 后 connection deadline 均已有 source 与 focused realtime test checkpoint。
- 当前不再存在 WebSocket 预算表达或 runtime 强制缺口；尚缺的是由稳定 source 产生、可验收且未受并发写入污染的 descriptor、lock 与 manifest 结果证据。当前并发生成产物已被判定为 `INVALID_INTERMEDIATE`，不得据其接受任何生成结果。
- 关闭方式是等待 App、Cloud 与 codegen source writer 全部停写后，由唯一 generation owner 从稳定 source 双遍 fresh generate；尚缺的验收证据必须证明 WebSocket descriptor 精确携带三元组、第二遍零 diff，且 ContractGraph、OpenAPI、operation security、App lock 与 generated manifest 使用同一 source hash。
- 完成判定：`GWT-005` 的 source/runtime focused tests继续有效，且唯一 fresh generation 的 descriptor/lock/manifest 一致性门通过；在此之前本 OPEN 保持 `block`，不得把 source 完成包装为 generated 准出完成。

<a id="open-010"></a>
### OPEN-010 消费者身份与投递语义已建成，剩余的是反向边不证明运行时真收得到

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：仍无维度校验声明的消费关系是否真在运行。身份已随反向边机制变为可判定，但消费对象声明一条反向边只证明它写了这条边，不证明运行时 handler 真的收到该事件。
- 本条的前提已两次整体改变，读本条时必须以当前形态为准，不得沿用任一版旧断言。
- 第一版断言「11 个对象声明了消费者却无投递实现」经逐对象重验后不成立，真无投递零例。
- 第二版断言「`consumers:` 是自由字符串值位、混了可部署服务/进程内订阅组/stream 名/逻辑投影四种所指、故存在性不可判定」在当时成立，但该字段本身已被撤销：全部 `events.yaml` 的 `consumers:` 与 `producer:` 已删除，`events.schema.json` 两层 `additionalProperties: false` 直接拒绝该键，身份改由消费对象在 `lifecycle.source_events` 写完整 `event_ref` 的反向边承担，裁决见 DEC-021。
- 因此存在性已从不可判定退化为对象解析：反向边的值只能是对象 id，`object.schema.json` 用 `dependentRequired` 把 `source_events` 与 `event_consumers` 双向咬死，悬空引用在 compile 期即失败。同理，第二版列为关闭条件之二的「投递路径无声明区分」也已由 `events.yaml` 必填的 `delivery_semantics` 承担，`topic` 键明写它只是名字、不表达任何投递保证。
- 两条关闭条件既已分别由 DEC-021 与 `delivery_semantics` 满足，本条的范围随之收窄为可达性一项，不得再据本条主张身份或投递语义缺失。
- 残留项之二是 `no_consumer_reason` 仍是自由散文，无结构判据，因此「这个事件按设计不该有消费者」这一主张目前只能人读不能机验。
- 必须遵守一条纪律：不得为消红而撤反向边或改写 `no_consumer_reason`，声明可能是唯一记录该投影存在的地方；同理不得为已在工作的同步路径再建 relay，那会给同一投递建出第二条通路。
- 缺一种机制的调用痕迹不足以判定投递缺失，必须先枚举该领域实际在用的投递形态再逐个排除。全仓零 `.Watch(` 调用是该教训的原始出处：它只证明未使用 Mongo change stream 这一种机制，不证明消费者未被投递，而 `content.post` 的两个消费者当时都已由 outbox relay 正常服务。
- 由此还推翻过一条泛化，即凡能写消费者声明的位置都会复现投递缺失；该泛化不成立，因为消费者可能经声明之外的另一机制被正常服务。
- 按名扫描消费者不可靠这一教训必须保留，因为它同样适用于将来的可达性判据。`circle-member-count-projector` 的实体是 `quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/persistence/mongo_member_count_projector.go`，`profile-interaction-activity-projector` 的实体是 `quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/application/projectors.go`，两者都曾被按名探查判为零证据。
- 投递意图的结构信号是存储出现 `published_at` / `next_attempt_at` / `claim_until` / `leased_until` 等投递状态列，或存在针对这些列的 pending/ready/claimable 索引，但该信号只表达意图，不排除同一消费者另经同步路径已被服务。`credential_bindings_outbox` 是两侧各准备一半的实例，写入端有 `credential_binding/infrastructure/persistence/postgres_store.go` 与 `user_account/infrastructure/persistence/close_credentials.go` 两处而读取方为零。
- 该信号必须读实现侧真实建立的索引而不是契约声明的索引，`report_outbox` 曾声明过一条实现里建不出来的 unpublished 索引。
- 可达性判定必须使用结构判据而不是文件名或消费者名扫描，已知四类合法形态必须同时被接住。
- 形态一是投递实现复用其他对象的 relay 类型，`assistant_policy_rollout_outbox` 由 `policymessaging.NewOutboxRelay` 装配为后台 worker，对象目录下并没有 relay 文件。
- 形态二是投递由兄弟对象的读取承担，`media_upload_session_outbox` 被 `media_asset` 的 `ReadMediaOutboxAfter` 与 `media_projection_checkpoints` 一并消费。
- 形态三是跨服务协作由受信同步端口承担而完全不经发件箱，`circle.gathering` 的 `EnsureGroupConversation` 会话绑定即属此类；返回的 `conversationId` 由 Circle 原子提交，失败由 reconciler 重试。
- 形态四是投递由同进程领域端口直读承担，`assistant.skill_user_setting` 的 `assistant-run` 即属此类。
- 投递实现的结构信号是存在生产代码读取该存储并推进某个 checkpoint 或水位，或存在指向该消费者的同步端口调用，而不是存在名为 relay 的文件。判定还须覆盖非 Go 实现，`rec_model_release_outbox` 的存储层是 `mongo_release_store.py`，否则 Python 实现的存储永远产不出投递证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-011"></a>
### OPEN-011 privacy.yaml 是与真实脱敏强制并行的第二条声明源，两侧无派生关系也无对帐维度

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前同一个日志脱敏治理关注点由两条互不知晓的元数据管线各自表达，且没有任何维度让两者对帐，因此声明侧的合规承诺与实际生效的强制之间既可能过覆盖也可能欠覆盖。
- 本缺口的性质不是承诺完全没兑现，而是强制点存在于声明之外、声明与强制点之间没有派生关系，属禁止第二真相源的直接违例。
- 第一条声明来自 `quwoquan_service/services/content-service/contracts/content/post/privacy.yaml` 与 `quwoquan_service/services/user-service/contracts/account/user_account/privacy.yaml` 的 `app_log_policy`。当前 App codegen 没有对应 emitter 或运行时产物，字段级声明也未派生到实际 log catalog，因此本 OPEN 继续阻断；不存在可把声明误当成运行时强制的平行 App 实现。
- 第二条管线才是实际生效的那条，`quwoquan_app/lib/runtime/observability/generated/runtime_log_catalog.g.dart` 的 `forbiddenAttributeKeys` 含 `phone`、`email`、`ip`、`preciseLocation` 与 `sessionId`，`quwoquan_app/lib/runtime/observability/runtime_log_redactor.dart` 按该集合整键丢弃，并按值形态掩码手机号与邮箱。
- 另有一条手写强制同时在线，`quwoquan_app/lib/runtime/observability/app_log_redactor.dart` 的 `_sensitiveKeyTokens` 含 `phone`、`mobile` 与 `email`，已由 `quwoquan_app/lib/runtime/observability/app_log_service.dart` 接线，并有 `quwoquan_app/test/local_contract/runtime/observability/logging/app_log_redactor__security__local_contract_test.dart` 作为负例证据。
- 两条管线无派生关系已被三项独立事实确证，不再是推断。
- 其一，生效那条的唯一输入是全局清单，`quwoquan_service/contracts/metadata/_shared/runtime_observability.yaml` 的 `forbidden_attribute_keys` 是全仓唯一一处该键，由 `quwoquan_service/tools/codegen_observability_catalog/main.go` 产出到 Go 运行时 catalog、App 的 Dart catalog、`quwoquan_ops` 与 `quwoquan_data` 两份 Python catalog 以及运营门户的 TypeScript catalog 共 5 个目标，全程不读任何对象的 `privacy.yaml`。
- 其二，名为 `log_policy` 的键有两个，分属互不相通的两条管线：route 级的那个由 `quwoquan_service/internal/metadata/load/load.go` 放在 operation 的 `privacy` 子结构里，兄弟字段是 `error_codes`、`concurrency` 与 `telemetry`，产物进 `operation_contracts.g.dart`；字段级的那个在 `fields.yaml` 上，两者不是同一个键，都不通向真实强制点。
- 其三，声明侧内部现已建成一条对帐维度，但它对帐的是声明与声明，不是声明与强制。`fields.yaml` 的 `log_policy` 已由 `quwoquan_service/internal/metadata/load/governance.go` 载入 `ast.FieldDefinition.LogPolicy`，并由 `quwoquan_service/internal/metadata/validate/governance_privacy.go` 与 `privacy.yaml` 的 `app_log_policy` 做 classification 与严格性偏序比对，越界发 `CONTRACT.PRIVACY.LOG_POLICY_WIDENED`。该校验全程不读 `runtime_log_catalog` 与两条 redactor，因此本 OPEN 的主缺口——声明侧与强制侧之间无派生关系——不因它的存在而收窄。
- 本条早先援引过 `privacy.yaml` 描述虚假宣称 codegen 产出 Dart `UserPrivacyPolicy.sanitizeForLog()`，该虚假描述已被改写，援引作废。
- 覆盖形态是过覆盖与欠覆盖并存，`phone` 被上述两条 redactor 各覆盖一次，而同一份 YAML 声明的 `birthDate`、`region` 与 `bio` 没有任何覆盖。
- 字段级策略是真正未实现的部分，`city_level_only`、`strip_detail`、`truncate_chars` 的 200 与 100、`count_only` 与 `drop_if_gt_100chars` 都没有实现，两条 redactor 只做粗粒度整键丢弃与值形态掩码，无法表达按字段的截断与降精度。
- `data_lifecycle` 的 `deletion_cascade` 是同一形态的第二处，其中 `UserSettings` 与 `DeviceRegistration` 声明的 `hard_delete` 已由 `quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence/close_account_private.go` 的字面 `DELETE FROM user_settings` 与 `DELETE FROM user_devices` 精确实现。
- `credential_binding` 与 `persona` 曾同样声明 `hard_delete` 而实现是原地擦写，由此形成的声明、[账号注销 REQ-004](../../../user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#req-004) 与实现三方不一致已消解：两者现声明 `strategy: scrub`，描述逐条写明保留的行、被不可逆覆写的列与保留动因。裁决同时落到了机制上，`privacy.schema.json` 的 `strategy` 值域新增 `scrub` 并写明它与 `soft_delete` 合规姿态不同、不得互相替代，`governance_privacy.go` 要求选 `scrub` 必须给出 description。
- `MediaAsset` 声明的 `soft_delete_then_cdn_purge` 与 `cdn_purge_delay_hours: 24` 缺时序实现，现有实现形态是先持久化 artifact work 再标记删除，由 `PrepareMediaAssetArtifactCleanup` 与 `MarkMediaAssetArtifactsDeleted` 承担，没有任何按 24 小时延迟触发清理的调度。
- 与 [OPEN-010](#open-010) 同一条纪律适用且必须继续遵守：改声明必须有依据，涉及擦除权的策略不得为消除告警而径直改成与当前实现一致。上述 `scrub` 裁决之所以成立，是因为它同时给出了保留动因与不可逆覆写的列范围，并把该要求固化进 schema 与校验器，而不是单方面把声明改成实现的样子。
- 关闭需要两件事同时完成，缺任一件本 OPEN 不得删除。
- 关闭条件一是把声明与真实强制点收敛为单一真相源：字段级声明必须由运行时 log catalog 派生，不得恢复第二套 App emitter。
- 关闭条件二是补一条跨越声明侧与强制侧的对帐维度，使「声明存在而无对应强制」与「强制存在而声明未派生」两种漂移都不再隐形；已有的 `governance_privacy.go` 只在声明侧内部对帐，不满足本条。
- 新维度必须以声明与强制点之间的派生关系作为判据，不得以声明专用标识符是否出现在实现中作为判据，因为该类标识符本就只存在于声明侧，其缺失对强制是否存在没有证据力。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-012"></a>
### OPEN-012 事件载荷携带的 moderationStatus 未被 field_visibility 的消费者清单覆盖

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：当前 `content.post` 的 `field_visibility` 把 `moderationStatus` 的可见范围声明为 `platform-ops` 与 `content-service-internal`，但 `events.yaml` 把该字段放进 6 个事件载荷，其中多个具名消费者不属于这两者，声明与跨服务事实错配。
- 命中事件是 `PostSubmittedForReview`、`PostPublished`、`PostModerationRejected`、`PostUpdated`、`PostSettingsUpdated` 与 `PostPromotedToWork`，这些事件声明的消费者包含 `circle-service`、`recommendation-engine`、`search-service`、`entity-service`、`notification-service` 与 `feed-projection`。
- 跨服务读取是实际发生的事实，`quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/adapters/inbound/events/content_post_consumer.go` 以 `json:"moderationStatus"` 反序列化该字段，`quwoquan_service/services/recommendation-service/internal/recommendation/recommendation_candidate_index_view/adapters/inbound/stream/post_lifecycle_consumer.py` 读取并要求其等于 `approved` 才纳入候选。
- 本条与客户端 wire 无关，该字段对 App 的不可见已由三处强制共同保证，分别是 `PostDetailSlice` 的 `json:"-"` 标注、`projectPostForClient` 的显式删除，以及 `TestPost_ResponseShape_NoPrivateFields` 对响应形状的断言，因此本条严重性明确低于受限字段实际出网。
- 修向已裁定为声明写窄，不是实现写宽。判据是消费该字段的用途属安全关键而非便利：`post_lifecycle_consumer.py:118-121` 要求 `status == published` 且 `visibility == public` 且 `moderationStatus == approved` 三者同时成立才把帖子纳入推荐候选，摘掉该字段等于让推荐链路失去审核拦截，只能退化为逐帖回查 content-service 或干脆不校验。circle 侧的投放判定与搜索索引同形。
- 因此不得为了让声明成真而从事件载荷摘掉该字段或删减具名消费者，这与 [OPEN-010](#open-010) 的「改声明必须有依据，不得为消红而撤消费者」是同一条纪律。
- 裁定后剩余动作收窄为两件，其一是值域扩充：`quwoquan_service/contracts/metadata/_schemas/privacy.schema.json` 的 `fieldVisibility.visibility` 当前枚举只有 `never_expose`、`all`、`app`、`self`、`platform-ops`、`content-service-internal`、`user-service-internal` 七个，按服务逐个加值会让枚举随消费者数量线性膨胀，收敛为一个第一方服务内部类别则更耐久但更粗；该取舍需先出 DEC 再改 schema。其二是补一条维度，使事件载荷字段与 `field_visibility` 消费者清单之间的错配不再隐形。
- 相邻但未定性的一处：同一字段在 `fields.yaml` 标为 `classification: PUBLIC` 且 `api_exposure: read`，与 `privacy.yaml` 的受限可见范围并存。两者是否同一坐标轴尚无定义，定义清楚前不得据此断言任一侧为假。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-013"></a>
### OPEN-013 实现发射的错误码未经任何契约声明，平台默认拒绝边界的全部高频拒绝码都缺声明位

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前已定位的两处发射点共有 8 个错误码被真实发射却无任何契约声明，同方向的实测下界远高于此，因此每一次未登记路由、未认证与未授权拒绝都拿不到契约承诺的用户提示与恢复动作，而现有校验的输入方向决定了这类漂移永远不会被发现。
- 本条的规模必须按两层读，只修已定位的两处发射点不构成闭合。
- 第一层是已定位并可直接处置的两处发射点，去重后 8 个码，明细见下。
- 第二层是同方向的全量规模，现已由反向维度 `quwoquan_ops/gate/verify_emitted_error_code_declaration.py` 每次运行重新产出，当前输出是当前形态 0 个加解析盲点内手工枚举 3 个，合计 3 个未声明码。
- 该数字不需要引用任何一次性扫描结果，门禁自身在输出里打印两部分的并集与合计，因此不存在把某个子集误当上界的读法。
- 存量清单落在 `quwoquan_ops/policies/gates/emitted_error_code_declaration_baseline.yaml`，语义是只减不增，新增未声明码与新增解析盲点都直接 BLOCK。
- 该基线的结构本身就是本条所指结构性盲区的解，除 `codes:` 外另有 `unresolved_sites:` 段，专门登记 reason 经变量传入因而字面量扫描跨不过去的发射位，每条带 `attested_scope` 写明手工枚举所依据的搜索范围与 `emits` 列出该处发射的码。
- 盲点段内未声明的码只报告不阻断，理由是扫描器无法重新推导它们，把无法自动复核的手工事实做成阻断条件等于把门禁绑在会腐烂的台账上。
- 第一层那 8 个码中 5 个已处置：4 个 `GATEWAY.*` 拒绝码在 `quwoquan_service/services/api-edge/contracts/edge_security/operation_admission_decision/errors.yaml` 取得声明位，`OPS.SYSTEM.internal_error` 落进 `runtime_failure_codes.yaml`；剩余 3 个 `OPS.USER.*` 仍只在盲点手工侧登记，因为 product-ops 的按状态码合成 writer 尚未改造。
- 3 仍不是上界，门禁自身声明当前只覆盖 `rterr.NewCode` 家族与 helper 构造器两种形态。
- 未被覆盖的发射方式至少还有五类，分别是 `AppErrorFrom*` 生成构造器、完整错误码字面量、`go_const` 标识符、文件内局部构造器，以及领域 sentinel 加 handler 状态码映射，`quwoquan_app/**` 的端侧发射同样未扫。
- 已定位的发射点有两处，严重度差异很大，必须分开处置。
- 第一处是平台鉴权边界，`quwoquan_service/runtime/auth/operation_guard.go` 的 `writeOperationGuardError` 以 `rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, reason)` 构码，6 个调用点的 reason 恰好三个取值，未匹配路由得到 `route_not_found`，缺可信 principal 得到 `unauthorized`，拒绝全部调用方与未通过授权判定得到 `forbidden`。
- 同一文件的兄弟函数 `writeOperationRequestError` 经 `rterr.NewInvalidArgument(rterr.ModuleGateway, ...)` 再产出第四个码 `GATEWAY.USER.invalid_argument`，它同样有 3 个调用点。这四个码现已有声明位，落在 `api-edge` 新增对象 `edge_security/operation_admission_decision`，该对象是 `external_reference` 形态，承载 runtime 逐请求准入判定这一无 HTTP operation 的边界。
- 该边界由 `RequireGeneratedOperationAuthorization` 承担，是全平台默认拒绝边界而不是某个服务的局部实现，因此这四个码是全系统返回频次最高的一组错误。
- 契约侧 `GATEWAY.*` 只有 `quwoquan_service/services/api-edge/contracts/edge_security/rate_limit_bucket/errors.yaml` 声明的三个码，分别是 `GATEWAY.USER.rate_limited`、`GATEWAY.MIDDLEWARE.rate_limit_state_unavailable` 与 `GATEWAY.MIDDLEWARE.upstream_unavailable`，与上述四个拒绝码没有任何交集。
- `GATEWAY.USER.route_not_found` 已经在 `quwoquan_service/contracts/metadata/_control_plane/product/control_plane.yaml` 的注释里被当作既存行为引用，用来解释 ops 路由为何必须登记进 product plane 才不会被该码拒绝，这正是它必须拥有声明位的理由。
- 第二处是 product-ops-service 的局部形态，`quwoquan_service/services/product-ops-service/cmd/api/main.go` 的共享 `writeRuntimeError` 只按 HTTP 状态码合成 code，不查任何契约。
- 合成结果是 400 与 405 得到 `OPS.USER.invalid_argument`，401 得到 `GATEWAY.USER.unauthorized`，403 得到 `GATEWAY.USER.forbidden`，404 得到 `OPS.USER.route_not_found`，409 得到 `OPS.USER.conflict`，其余状态得到 `OPS.SYSTEM.internal_error`。
- 两处发射点共享 `GATEWAY.USER.unauthorized` 与 `GATEWAY.USER.forbidden`，因此去重后的未声明码总数是 8 个而不是两处相加的 10 个。
- 这 8 个码在两个声明源里的命中数原本均为 0，处置后只剩 3 个 `OPS.USER.*` 仍为 0。该判据成立是因为声明侧以完整点分串写 code，全串比对因此能直接证伪存在性，与只存在于声明侧的标识符不同。
- 现有校验看不见它的原因是方向问题，不是少了一个维度。
- `quwoquan_service/internal/metadata/validate/governance_error.go` 的两段循环分别从 `Governance.Objects` 的声明出发核对 `emitted_by.operations`，以及从 `Operations` 的 `error_codes` 出发核对声明是否绑定该 operation，两侧输入都是声明。
- 当一个码只存在于实现侧时，声明侧没有任何条目可供比对，它既不触发 `CONTRACT.ERROR.UNKNOWN_OPERATION_CODE` 也不触发 `CONTRACT.ERROR.MISSING_OPERATION_EMISSION`。
- 因此本条最需要泛化的结论是，现有错误码治理只回答「声明了是否实现」，从不回答「实现了是否声明」，反方向漂移属结构性盲区而非个别遗漏。
- 后果是端侧降级而不是崩溃。`quwoquan_app/lib/runtime/errors/ui_error_semantics.dart` 的每个域枚举都有 `unknown` 回退分支，未声明码会被解析成 `unknown` 并落入通用处理，丢掉契约本应提供的中英 `user_message`、`recovery_action` 与 l10n key。
- 该降级叠加平台鉴权边界的发射频次后不再只是治理漂移，而是全部鉴权拒绝都以通用回退文案呈现给用户，这是已经发生的用户可见后果，也是本条相对其余同形条目优先级更高的原因。该后果已消除：四个拒绝码取得声明位后，`writeOperationGuardError` 不再对四种 reason 共用一句「请求未获授权」，改为逐 reason 回写契约声明的 `user_message`，端侧经 wire `userMessage` 直接拿到。
- 两处发射点的处置范围不同。product-ops 那半是局部的，承接其共享 writer 的 `ErrorWriter` 注入机制全仓只有两个 handler 使用，分别是 `quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/adapters/inbound/http/handler.go` 与 `quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/adapters/inbound/http/handler.go`。
- 平台鉴权那半没有等价的收敛边界，它对所有经 `RequireGeneratedOperationAuthorization` 的服务生效，因此补声明位时必须先确定这四个码的归属对象，不能沿用 product-ops 的按对象补齐路径。
- 反方向维度已具备，因此关闭条件收敛为一件事，即按 `emitted_error_code_declaration_baseline.yaml` 逐条清零，把码补进所属对象的声明源并声明 `emitted_by`，或改用已声明码替代按状态码与按变量合成。
- 处置清单只以该基线为来源，不得另起清单，基线清空且 `unresolved_sites` 也清空时该文件与本 OPEN 一并删除。
- 清零顺序应先自动侧后盲点侧，因为盲点侧的码在形态扩展后会自动进入 `codes:` 段，届时才具备防回退能力。
- 自动侧已清零，`codes:` 段现为空并进入纯防回退状态；剩余关闭条件只有盲点侧的 3 个 `OPS.USER.*`，处置方向是把 product-ops 与 platform-ops 的按状态码合成 writer 改成逐分支字面量构码，再对 `invalid_argument` 与 `conflict` 定归属、把 `route_not_found` 收敛到已声明的 `GATEWAY.USER.route_not_found`。
- 新维度必须能枚举实现侧真实发射的 code，判据只能是构造点的结构识别，例如 `rterr.NewCode` 与 `NewAppError` 的实参组合，不能继续以声明清单作为唯一输入。
- 新维度还必须同时吃下两个声明源与两种 YAML 形态，这是本条最重要的判据约束，任何只认其中一种的实现都会直接产出假阳。
- 声明源有两个，一是各对象的 `errors.yaml`，二是 `quwoquan_service/contracts/runtime_errors/errors/runtime_failure_codes.yaml`，两者合计去重 682 个已声明码，其中后者贡献 28 个且以 `APP.*` 与 `CLOUD.*` 等运行时失败码为主。
- YAML 形态有两种，`errors.yaml` 里除块形态 `- code:` 外还有 88 条流形态 `- {code: ..., kind: ...}`，只匹配块形态会把这些码误判为未声明。
- 因此枚举已声明码必须走 YAML 解析而不是行级正则，判据是递归取出所有含 `code` 键的 mapping，这样两种形态与两个源都不会漏。
- 发射侧的解析同样不能停在字面量，reason 经函数参数或 switch 变量传入是已知的常见形态，新维度必须能跨过一层包装函数解析，否则会漏掉本条第一层那 8 个码。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-014"></a>
### OPEN-014 契约声明的错误码从不被发射，同位置选择性缺失是其强判据

- 类型：`capability_gap`
- 优先级：`P3`
- 准出影响：`track`
- 影响或价值：当前仍有一个已声明错误码从不被任何实现发射，声明因此成为无法兑现的承诺，而同一位置其余同族码都已逐字发射这一事实排除了改由其他机制发射的解释。
- 本条早先并列的 `RECOMMENDATION.SYSTEM.scoring_failed` 已不再成立，援引整体作废：`recommendation_model_release/adapters/inbound/http/scoring_router.py` 已定义 `SCORING_FAILED_CODE` 常量并在失败路径 `raise` 带结构化 `code` 的 500 响应，早先援引的 `score.py` 裸 `HTTPException` 路径也已不存在。
- 唯一剩余实例是 `CONTENT.USER.media_image_reprocess_version_conflict`，由 `quwoquan_service/services/content-service/contracts/media/media_image_reprocess_run/errors.yaml` 声明并被 4 个 operation 引用，codegen 已产出 `AppErrorFromMediaImageReprocessVersionConflict` 构造器，但 `quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/adapters/inbound/http/handler.go` 只调用了另外 4 个同族构造器，这一个零调用。
- 核查该码时不得把 `CONTENT.USER.version_conflict` 的大量发射点误当作它已被发射，两者分属不同对象、是不同的码，这是「同名不等于同一个键」在本条上的具体形态。
- 同位置选择性缺失是本条的判据来源，强于全仓搜不到该名字，因为同族 5 码中另外 4 码已在同一文件内逐字出现，说明该文件就是发射点，缺的这一条不可能改由别处以其他形式发射。
- 本条不覆盖只有名字级证据的候选，`domain_reader_unauthorized`、`skill_data_control_action_failed` 与 `event_projection_unavailable` 目前只有名字缺失这一项证据，不足以定性，补足同位置或结构判据后才可并入本条。
- 关闭方式是二选一，要么补齐发射点让声明兑现，要么按契约事实删除不再需要的声明，改声明必须有依据且不得为消除告警而径直删码。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-016"></a>
### OPEN-016 发件箱事件的线上身份没有声明位，契约事件名与线上类型串之间无派生关系

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：当前发件箱事件的线上身份是实现侧硬编码的点分字符串，契约的事件名与它之间没有任何派生关系，改名或敲错都不会被任何机制拦住，而消费者是按该字符串匹配的。
- 本条的缺口是机制缺失而不是实例统计，机制侧结论已在生成器侧核实，覆盖范围与未验部分见下。
- 契约侧的事件名是 PascalCase 的 `name:`，例如 `MediaAssetCreated` 声明于 `quwoquan_service/services/content-service/contracts/media/media_asset/events.yaml`。
- 实现侧的线上身份是点分小写串，例如 `content.media_asset.created`，它在全仓所有契约与元数据 YAML 中命中数为 0，因此该串没有任何声明位，只存在于实现。
- 转换实现是存在的，但它不构成派生关系：`quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/messaging/event_publisher.go` 里有一个把点分串映射到 PascalCase 并作为发布 eventType 的 switch，两侧都是硬编码字面量、都不从契约派生，`default` 分支只能报错而不能推导，因此改名或敲错仍然无人拦截。
- 仓内 5 个 camel 转 snake 工具的全部调用点都用于文件路径、storage 实体与表名、Go 标识符与 lifecycle 方法名，没有任何调用点把它用于事件类型串，因此该串的两侧对齐仍靠人工约定。
- 这一点是生成器侧的机制事实，与实例多少无关。
- 契约身份与线上身份是两个命名空间，核查时不得混为一谈：`media_asset/object.yaml` 的反向边写的是 `content.media_upload_session.MediaUploadCompleted`，它虽然也是点分串，但用的是契约身份，与本条说的线上身份串 `content.media_upload.completed` 不是同一个串。
- 生产端与消费端各自持有独立字面量，`quwoquan_service/services/content-service/internal/media/media_upload_session/application/use_cases.go` 在写入事件时内联该串，消费端 `media_asset/application/processing/worker.go` 用自己定义的常量比对，`media_asset/infrastructure/persistence/media_asset_creation.go` 又内联了第三份同样的串。
- 加上 `event_publisher.go` 里的第四处，同一对象内部已出现同串四处独立字面量，说明连对象内的单一常量收口都没有，跨包耦合完全依赖人工对齐。
- 仓内已存在可复用的声明位先例且先例已扩大：`client_ws_type` 现由 6 个对象声明，覆盖 chat 的 4 个对象加 `user_account` 与 `rtc/call_session`，并已 codegen 进 `generated/**/contract/event/events.go`，说明缺的不是概念而是发件箱这一面的对应字段。`user_account/events.yaml` 的 `UserAvatarUpdated` 至今没有该键，同文件的 `UserSyncHint` 有，是可直接照做的落点。
- 本条只在 `MediaAssetCreated`、`MediaUploadCompleted` 与 `UserAvatarUpdated` 三个事件上逐条核实过，普遍性未验，不得据本条推断全部事件都是该形态。
- 未验的原因是点分字面量里混杂文件名、队列名与权限名，无法按模式直接计数，例如 `reliabletask.user.avatar` 是队列名而不是事件类型。
- 因此规模属待定项，补维度前必须先能把事件类型串与其他点分串区分开，否则计数不可信。
- 关闭方式是为发件箱事件的线上身份建立声明位并使实现侧从其派生，可复用 `client_ws_type` 的形态，或按契约事实确认该身份不需要治理并写明理由。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-017"></a>
### OPEN-017 storage.yaml 的键集只对一个消费者建立了 schema 派生关系，其余消费者仍各自独立声明键子集

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：仍只有 `tools/codegen_storage` 的 reader 与 `quwoquan_service/contracts/metadata/_schemas/storage.schema.json` 建立了双向断言。顶层键集虽已由该 schema 关闭，其余解析同一文件的消费者仍各自独立声明键子集，因此「schema 认某键但某消费者不读」这一方向在该消费者上不可见，键集真相源只做到局部单一。
- 本条的缺口是派生关系缺失而不是实例统计，不得据本条推断当前存在未登记的键。
- 消费者不止三个，实测解析 `storage.yaml` 的位置至少有：`tools/codegen_storage/main.go` 的 `StorageYAML`、`internal/metadata/load/business_object_maps.go` 的 `storageDocument`、`internal/metadata/load/publication_evidence.go` 的函数内匿名 struct、`tools/verify_metadata/main.go` 的 `validateStorageEntities` 内匿名 struct、`quwoquan_ops/gate/verify_domain_model_storage_governance.py`、`quwoquan_ops/gate/verify_runtime_log_governance.py`、`quwoquan_app/scripts/runtime/observability/verify_ops_event_schema_completeness.py` 与 `verify_content_page_funnel_coverage.py`，以及若干 `local_contract` 测试。
- 已关闭的方向必须与残留方向分开读，否则会高估本条规模：schema 关门后「写了但 schema 不认」结构性消失，因为任何未登记顶层键在 `commercial` profile 下直接 `CONTRACT.SCHEMA.INVALID`；「读了但没人写」被结构性限制在 schema 键集之内，因为 schema 外的键永远不可能有声明。残留的只有「schema 认但某消费者不读」在 `codegen_storage` 以外没有表达位。
- 残留不可用反射消除的原因是消费者形态不齐：Python 侧是运行时 dict 取值，Go 侧有两处是函数内匿名 struct，均无法从包外枚举字段，静态提取只能靠变量名启发式，而本仓已有因弱判据产生假阳的先例，故不接受启发式扫描作为门禁判据。
- 顶层键集关门不覆盖子键值域，该层缺的是机制而不是实例：`redis_cache[].scene` 的实测取值现为 `realtime`、`rec`、`general`，与 `quwoquan_service/contracts/metadata/_shared/redis_keyspace.yaml` 的 `scene_routing.scenes` 完全一致，但两侧仍无派生关系也无断言，今天吻合不构成明天不漂的保证。本条早先援引的 `admission` 与 `assistant` 两个越界取值已不复存在，援引已作废，缺口本身不因此收窄。
- 本条早先还援引过 rtc 环铃超时的声明与实现各持一份 30/60 秒常量，该实例同样已消失：`services/rtc-service/contracts/rtc/call_session/storage.yaml` 不再声明 `lifecycle_timers.ring_timeout.thresholds`，`call_session_service.go` 改为经构造函数注入并校验 `RingTimeoutPolicy`，服务内不再有对应硬编码常量。
- 判定某个键无消费者时不得只看 Go struct tag，必须先枚举消费形态：Go struct tag、Python dict 取值、`generated/**`、`quwoquan_ops/**`、`quwoquan_app/**`，以及嵌套在别的键下的同名键。`idempotency` 是该判据的直接反例，它在 `object.yaml` 的 `lifecycle.idempotency` 与 operation 的 `reliability.idempotency` 下都真实存在且被读取，与 `storage.yaml` 顶层的同名键不是同一个键。
- 关闭方式是让每个消费者的键子集可由 schema 派生（reader 由 schema 生成）或被断言为 schema 键集的子集，形态可复用 `tools/codegen_storage` 已有的双向断言；子键值域至少需覆盖 `redis_cache[].scene` 与其 `scene_routing` 真相源。
- 完成判定：全部解析 `storage.yaml` 的消费者的键子集均可由 schema 派生或被门禁断言为其子集，且 `redis_cache[].scene` 与 `scene_routing.scenes` 之间建立同样的派生或断言关系。

<a id="open-018"></a>
### OPEN-018 storage.yaml 的 indexes 是大规模只写不读的声明，去留未裁决

- 类型：`capability_gap`
- 优先级：`P3`
- 准出影响：`track`
- 影响或价值：仍未裁决该字段是该派生实现还是该撤销。当前它既不驱动实现也不校验实现，读契约的人会把它当作索引真相源，而它不是。
- 规模事实可复现：以 `- name: idx` 与 `- name: uniq` 为判据，全仓 78 份 `storage.yaml` 共 463 条索引声明；放宽到含 `unique_constraints` 与 `search_indexes` 的更宽判据时数量更大，因此下述结论不依赖某个具体计数。
- 消费者只有一个且是生成器不是校验器：全仓读 `yaml:"indexes"` 的位置只有 `quwoquan_service/tools/codegen_storage/main.go` 的两处结构体字段，它把声明翻译成建索引代码，从不反过来核对实现是否与声明一致。
- 覆盖率与该唯一消费者的产出严重不匹配，绝大多数声明没有对应的生成产物，因此这些声明既未驱动任何实现，也未被任何实现回证。
- 本条与 [OPEN-017](#open-017) 不是同一件事：OPEN-017 说的是顶层键集在多个消费者之间缺派生关系，本条说的是 `indexes` 这一个键的取值本身无人回读。
- 不得据本条新建以「声明的索引是否存在」为判据的维度，仓内已就此裁决过：`quwoquan_service/internal/metadata/load/publication_evidence.go` 的投递判据明确不看契约声明的索引，并由 `publication_write_index__contract__local_contract_test.go:96` 的 `TestDeliveryJudgementFollowsProvisionedBehaviourNotDeclaredIndexes` 钉死。按名字比对还会撞上另一个已知失效形态，实现侧真实建立的索引大量与声明同义而不同名，按名判会产出成片假缺口。
- 若判定为撤销，形态与 `capabilities`（DEC-016）、`lifecycle.transitions`（DEC-020）一致，都是无消费者、无值域约束、取值已开始漂移的惰性声明。
- 若判定为派生，则必须是实现由声明生成或实现被断言为声明的语义等价物，判据只能是索引键集的语义等价而不是名字相等，且必须同时覆盖 Go 的 `SetName`、SQL 的 `CREATE INDEX` 与 Python 的 `create_index` 三种建立形态。
- 完成判定：出 DEC 明确撤销或派生二选一；若为派生，`indexes` 声明与实现之间建立由门禁保证的派生或等价断言关系。
