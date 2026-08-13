# L3 Story：App Cloud 业务对象商用闭环 (`app-cloud-business-object-commercial-closure`)

> 所属能力：[`system-architecture-and-engineering-guide`](../spec.md)

> Journey / Scenario：AppRoot 当前全部 Journey；统一准出锚点为 [`REQ-009`](../../../spec.md#req-009)、[`REQ-010`](../../../spec.md#req-010) 与 [`UAT-009`](../../../spec.md#uat-009)。

> 设计归属：[L2 DEC-001](../design.md#dec-001)、[DEC-018](../design.md#dec-018)、[DEC-019](../design.md#dec-019) 与 [DEC-024](../design.md#dec-024)

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
- 所有 production 错误发射必须动态解析到 canonical 声明；Go、Dart、Swift 与 Python 的字面量、生成构造器、常量、局部 helper 和 sentinel 映射均进入同一反向门禁，未声明码与不可解析发射点保持为 0，禁止基线或人工证明豁免。
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
- 每个 `clientContract` 必须有唯一真实消费身份：页面消费由 `object_ids` 与 `query_slices/command_operations` 证明，非页面后台/runtime 消费由 `runtime_execution` 的 object、operation、production path 与 symbol 证明；仅有 generated adapter/DI 不算消费，页面 participant 与 runtime execution 双轨登记必须阻断。

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

- App 业务源码只位于 `lib/service/<service>/<context>/<object>/{domain,application,adapters,presentation}`，对象测试按同一 service/context/object 身份位于 `test/<layer>/service/<service>/<context>/<object>`；业务文件无 owner、同优先级多 owner、旧业务大桶或兼容路径任一存在时均不得通过架构准出。
- 对象的 App 必需层由其 App-exposed operation、页面认领和端侧不变式决定，不能从云侧 kind 无条件生成，也不能以目录或占位文件存在反推能力已实现。
- 页面必须有唯一 source owner 并保留全部 participant object；多对象页面由 source owner 的 presentation 经 participant 的公开 application 边界组合，禁止直接引用兄弟对象私有层。
- production 依赖图只允许父级 DEC 声明的单向层关系，具体 adapter 只在唯一 `runtime/di` composition root 装配；barrel re-export、旧路径 shim、双轨 import 和 runtime fallback 数量为零。

<a id="req-013"></a>
### REQ-013 对象级隐私、事件线上身份与存储合同必须由 authoring source 单轨派生并反向校验

- 对象 `privacy.yaml` 必须派生五端字段策略 catalog；Go 与 App 运行时按 operation 所属 object 应用 `allow/drop/mask/truncate/count/drop_if_gt`，不得保留手写敏感键表或另一套字段策略。
- `first_party_service_internal` 是第一方服务内部字段的 canonical 可见性。事件 payload 与 lifecycle consumer 的字段可见性必须逐字段闭合；`content.post.moderationStatus` 只允许第一方服务内部和 platform ops 消费，App wire 继续不可见。
- `transactional_outbox` 的 `wire_event_type` 必须由 owning event 声明、全局唯一并生成 producer/consumer 常量；production 并行字面量必须在唯一 fresh generation 后硬切清零。
- 每个 authored lifecycle consumer 必须从 owning object 的 `application/` 或 `adapters/` 唯一绑定真实 production facet/method 与 source path/SHA；`content.media_asset.ProcessMediaOutbox` 由同一生产 `MediaProcessingHandler.process` 消费并复用 durable lease、checkpoint、重放与健康检查，禁止 marker handler、对象 allowlist 或未进入生产组合的壳实现。
- Go、App 与 Ops 的全部 production/governance storage consumer 必须经 `storagecontract.Decode` 或其 strict JSON view 读取 object-local `storage.yaml`；timeout、nonzero、empty、nonJSON、stderr、keyset drift 与 source TOCTOU 均 fail-closed，Python 直接解析 authoring YAML 或本地键表 fallback 必须为零。
- `storage.yaml.indexes` 必须与 production create/query/unique guard 的键、顺序、唯一性与 partial predicate 语义等价；声明未建立、建立未使用或仅名字相等均不得通过。
- authoring source、生成器模板和静态门通过只证明机制实现；generated catalog、运行时消费与结果证据必须绑定同一稳定 source hash。

## 4. 契约引用

- canonical：[`L2 DEC-001`](../design.md#dec-001)
- canonical：[`L2 DEC-018`](../design.md#dec-018)
- canonical：[`L2 DEC-019`](../design.md#dec-019)
- canonical：[`L2 DEC-024`](../design.md#dec-024)
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
- canonical：`quwoquan_app/lib/service/<service>/<context>/<object>`
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
- WHEN 架构与测试治理按 service/context/object 反向解析全部 App 业务文件、页面和测试。
- THEN 每个文件均有唯一对象或横切 owner，必需层与页面 source owner/participants 完整且没有占位层。
- AND 层间与跨对象依赖只经过公开边界和唯一 composition root，旧业务大桶、私有跨对象 import、barrel、shim、双轨路径与 compatibility fallback 均不存在。

## 6. 依赖

- 前置要求：[`system-architecture-and-engineering-guide`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)、[DEC-018](../design.md#dec-018)、[DEC-019](../design.md#dec-019) 与 [DEC-024](../design.md#dec-024)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 静态对象架构已闭合，等待逐 operation 测试、覆盖率与结果证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺全部 App-exposed operation 的职责匹配 local_contract/api_integration、页面与 Journey 的 production user_acceptance、fresh 对象覆盖率及可信 ResultBundle；静态目录和架构门已闭合，但这些结果证据未齐时仍不能声明 `MODEL_GOVERNANCE_READY`。
- 当前 App 业务源码已单轨位于 service/context/object 纵切，唯一 owner、能力驱动层义务、页面 source owner/participants、R1-R5 依赖规则、test layout、no-fake、object path map 与 full analyze 均通过；不得恢复旧业务大桶、跨对象 private import、barrel、shim、fallback 或用 baseline 吸收违规。
- 剩余 operation/test 缺口必须从冻结后的 current ContractGraph 动态派生。每个 case 只在 owning object 的 `operations.yaml#readiness_cases` authoring，并与 runner 内 exact `spec_ref`、`readiness_case` 及真实 operation 调用一一闭合；仅有测试文件、marker 或 typed double 不构成 readiness。
- coverage 必须从同一 Graph/source hash 上全部绿色测试 fresh 采集到对象 owner，stale lcov、无主源码、不可测对象或手填 baseline 均 fail-closed；ResultBundle 还必须绑定同一 commit、Graph、candidate、environment、Provider、device 与 artifact/receipt identity。
- readinessEvidence 的静态结构 packet 与动态 result/receipt 类型已存在不等于测试执行、四环境或用户验收已通过；可信结果未完整闭环时对象最多停在 implemented。
- 本 OPEN 只关闭领域模型与工程治理；`commercial.targetStory` 指向其他节点的产品行为、Provider、四环境和 UAT 缺口仍由其唯一目标节点关闭，不得在本 OPEN 内代持，也不得用目录迁移替代。
- canonical 对象与 context 集合只从同一 ContractGraph 候选实时派生，不维护固定数量、对象 registry、迁移清单或第二套 readiness 台账。
- 上述任一结构、依赖、测试、覆盖率或证据边界未闭环时，本 OPEN 不得删除，也不得声明 `MODEL_GOVERNANCE_READY`。
- 完成判定：`GWT-001` 与 `GWT-007` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 服务端从可信 principal 执行 operation 与对象授权

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：仍缺从冻结 fresh ContractGraph 动态派生的「每个 required operation → production route/composition → exactly-one guard」全覆盖报告，以及同一候选环境的 401/403/404 与零写入拒绝回执；source descriptor/guard 机制与重点负向测试已通过，但 checked-in generated descriptor 仍不可作为 fresh 覆盖证明。
- 完成判定：`GWT-003` 的结果子句由真实测试或可执行门 `spec_ref` 绑定，且证据同时包含冻结 fresh ContractGraph 动态派生的 required operation 全覆盖报告与同一候选环境的 401/403/404 零写入拒绝回执；checked-in generated descriptor 不计。

<a id="open-004"></a>
### OPEN-004 四环境 Remote 与 test-only double 物理隔离

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：仍缺同一候选的 alpha/beta/gamma/prod dependency/kernel/AOT/SBOM、双端安装包与 UAT transitive import 回执；静态纯度、包依赖与 Remote 单轨门已通过。
- 完成判定：`GWT-004` 的结果子句由真实测试或可执行门 `spec_ref` 绑定，且证据包含同一候选四环境的 dependency graph、kernel/AOT reachability、SBOM 与双端安装包回执，其中 Mock/fixture/Noop 计数为 0。

<a id="open-006"></a>
### OPEN-006 当前全部真实 Remote Scenario 完成商业准出

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：仍缺当前全部 AppRoot Journey 在同一候选上的 alpha/beta/gamma/prod 真实 user_acceptance、Provider、SLO、灰度与回滚 CaseResult；局部 local_contract/api_integration authoring 与静态 implemented 状态不等于结果已执行，当前 dynamic readiness 仍非 commercial-ready。
- 本 Story 只拥有冻结 fresh Graph 中 `commercial.targetStory` 指向本 Story 的真实结果缺口，精确对象、operation 与 gapId 必须动态派生，不在规格固化名单或复制第二台账。
- `targetStory` 指向其他最低可关闭 Story 的 blocked operation 仍由其所属节点独占，当前 OPEN 不代持其 Provider、外部批准、产品行为或 UAT 证据。
- 完成判定：`GWT-006` 的结果子句由真实测试 `spec_ref` 绑定，且冻结 fresh Graph 中 `commercial.targetStory` 指向本 Story 的 gap 动态派生数为 0——即全部 AppRoot Journey 在同一候选取得 alpha/beta/gamma/prod 真实 user_acceptance、Provider、SLO、灰度与回滚 CaseResult。

<a id="open-010"></a>
### OPEN-010 lifecycle consumer 已唯一绑定生产实现，仍缺逐边运行时可达回执

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：仍缺把每条 lifecycle edge 的 producer event identity、delivery semantics、目标 consumer facet/method、幂等键、checkpoint/receipt 与真实运行终态绑定到同一结果证据；source implementation path/SHA 唯一只证明方法存在，不证明该事件已实际到达并被正确处理。
- consumer identity 已由 `lifecycle.source_events/event_consumers` 反向边唯一表达，schema 强制 implementation path/SHA，`delivery_semantics` 也已成为 producer 合同；本 OPEN 不再声称身份、实现存在性或投递语义 authoring 缺失。
- api_integration/ResultBundle 必须逐 edge 证明 producer 写入、真实 delivery、目标 facet/method 执行、idempotency replay、checkpoint/receipt 推进，以及 retry/DLQ 或同步失败的最终恢复状态；仅 publicationDelivery、outbox 被读取、索引存在或方法名扫描均不足以通过。
- 同步端口、同进程投影、跨服务 relay 与异步 outbox 可采用不同执行形态，但每条 edge 只能有一条 canonical 路径；不得为消红新建第二 relay、撤掉真实反向边或用对象 allowlist 替代结果证据。
- `no_consumer_reason` 必须收敛为可校验的受控 reason class，不能继续用自由散文代替「按设计无消费者」的机器可判定事实。
- `content.media_asset` 已由生产 `MediaProcessingHandler.process` 闭合 source implementation；本 OPEN 只追踪同一 edge 的真实投递、重放与 checkpoint/receipt 结果，不重复代持已关闭的 source 缺口。
- 完成判定：`GWT-001` 对应行为满足；current roster 每条 lifecycle edge 都有绑定同一 candidate/Graph 的真实 api_integration 或 ResultBundle，且 producer、consumer、idempotency、checkpoint/receipt 与 retry/DLQ 终态可逐边审计。

<a id="open-016"></a>
### OPEN-016 发件箱线上身份已落 authoring 与 generator，等待 Data 与 production literal 单轨切换

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：尚缺 Data wire authoring、唯一 fresh constants 与 production literal 硬切；非冻结对象的 `transactional_outbox` 事件已由 `events.yaml.wire_event_type` 唯一 authoring，schema、metadata loader/validator、两个 Go emitter 与 Python generator source 均已完成。
- 当前非冻结 authoring 通过唯一性与 delivery-semantics 门；缺 `wire_event_type`、非 outbox 误写或两个事件共享同一线上身份都会 fail-closed。
- 尚未完成的是物理单轨切换：唯一 fresh generation 尚未产出受验收的常量树，production producer/consumer 仍有历史线上身份字面量；生成后必须按 owner 常量硬切并把同义 raw literal 清零，禁止复制常量或保留 fallback。
- `content.media_asset` 的四条 wire authoring 仍处于 Data `WAIT_CONTENT`，不得在冻结期间补写或以旧 receipt/旧 generated 替代。
- 关闭条件是 Data 明确解冻并补齐其 authoring，随后从同一稳定 source hash 双遍生成常量，端云/Python production literal 全部切到 canonical owner，漂移门和 focused emitter/runtime tests 全部通过。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-018"></a>
### OPEN-018 storage index 语义已零缺口，等待 dead-letter 环境迁移与受控恢复发现

- 类型：`capability_gap`
- 优先级：`P3`
- 准出影响：`track`
- 影响或价值：尚缺实现：canonical controlled replay/discovery 尚未通过公开 owner 边界形成可执行恢复能力。尚缺验收证据：alpha/beta/gamma/prod 尚无同一候选绑定的旧索引迁移、备份与 hosted readback receipt。严格语义 index 门已按 [L2 DEC-024](../design.md#dec-024) 同时核验声明、production create 与 production use，并按键、顺序、唯一性和 partial predicate 的语义等价判定。当前 live 派生结果已无 usage 缺口，不在规格固化易漂移的聚合计数。
- `content.media_asset` 的 media-processing dead-letter 当前只有按事件身份幂等隔离的生产写入，没有按 consumer/time 或 aggregate/time 的生产查询、排序或聚合，因此两条二级索引已从 canonical storage 和创建路径删除；不得为恢复旧索引或消除门禁制造伪查询。
- 对象级 quiesced migration 已能幂等删除已部署 Mongo 中遗留的两条二级索引并回读验证事实不丢失，但 alpha/beta/gamma/prod 尚无同一候选绑定的迁移执行、备份与 hosted readback receipt，不能仅凭源码或真实 Mongo 测试宣称环境完成。
- canonical controlled replay/discovery 尚未实现；索引退役只消除无消费者的写放大，不等于已提供 dead-letter 枚举、审计或恢复命令。后续若准入该能力，必须先定义 object-owned query/command、权限和恢复语义，再按真实访问模式声明索引。
- 已撤出的 `assistant.skill_trigger_delivery` INVALID_INTERMEDIATE 不得计入统计、基线或准出；未来若重新准入，必须同批完成三层实现与全部索引 create/use。
- 关闭条件是严格 storage index governance 在同一稳定 source hash 上保持零缺口，四环境完成受控旧索引迁移与事实 readback，并由 canonical replay/discovery 通过公开 owner 边界形成真实恢复结果；不得添加 allowance、baseline、启动期随意删除或伪查询。
- 完成判定：`GWT-001` 对应行为满足，四环境迁移 receipt 与 focused production/API tests 证明旧索引清零、dead-letter 事实保留且受控恢复可达。
