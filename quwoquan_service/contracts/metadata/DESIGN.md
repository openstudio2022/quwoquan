# 领域元数据与 ContractGraph 设计

## 1. 设计边界

元数据描述业务语义，不承担资产登记。物理路径是对象身份来源；compiler 扫描目录构建 ContractGraph，生成 transport、DTO、错误码、投影类型和覆盖报告。

```text
metadata YAML ──strict load──> typed AST ──validate──> ContractGraph
                                                       ├── OpenAPI
                                                       ├── Go/Dart/Python contracts
                                                       ├── operation/reader/slice descriptors
                                                       └── coverage/readiness evidence
```

任何 generator 都不得重新解释原始 YAML，也不得从旧 OpenAPI 反向恢复语义。

## 2. 对象身份

对象根路径固定为所属服务内：

```text
services/<service>/contracts/<bounded-context>/<business-object>/
```

由此得到：

```text
metadata_domain = services/<service>/contracts/domain.yaml
bounded_context = <domain>.<bounded-context>
business_object = <domain>.<business-object>
object_kind = object.yaml.kind
```

同一 `<domain>.<business-object>` 不得位于多个 context。需要消歧时重命名业务对象，不增加 alias、重复 ID 或注册表。

源码采用相同组织轴：

```text
services/<service>/internal/<context>/<object>/<layer>/...
```

service 只表达源码和部署所有权，不进入对象业务标识。

## 3. 对象类型

独立对象只允许六种 kind：

| kind | compiler 必须验证的语义 |
|---|---|
| `aggregate_root` | command owner、事务边界、并发策略、必要 outbox |
| `append_only_fact` | append sink、幂等/去重、禁止 update/delete |
| `process_manager` | 长流程编排器（saga）：`process_facade` 命令面、`checkpoint` 进度、状态机与补偿、`domain`+`application`+`infrastructure` 三层齐全 |
| `projection` | named Reader/Slice、禁止业务 command |
| `external_reference` | 本地非权威、禁止本地生命周期写入 |
| `runtime_session` | session owner、租约/fencing/TTL/终止语义 |

`owned_entity`、`value_object` 是聚合成员语义，只能写在聚合根 `object.yaml.members`。它们不拥有独立目录、Store、Repository 或公开 Facade。

### 3.1 `process_manager` 与相邻 kind 的判定边界

`process_manager` 与 `aggregate_root` 的区别不是「是否有状态」，而是**状态的性质**：聚合根拥有一份业务事实的权威快照，`process_manager` 拥有一台跨若干步骤推进的状态机，因而必须同时声明补偿、超时与取消语义，进度由 `checkpoint` 而不是聚合版本表达。判据是：对象是否存在「未完成中间态 + 失败后需要补偿或恢复」这对语义。若有，它是 saga；若只是状态字段的合法迁移，它仍是聚合根。

`process_manager` 与 `runtime_session` 的区别是**存储 seam 的持久性**：session 是租约/TTL 驱动的易失运行时状态，过期即消失且不需要补偿；saga 的 checkpoint 是持久权威记录，进程重启后必须能从中恢复推进。因此 `runtime_session` 的 `storage_role` 是 `runtime`，`process_manager` 与 `aggregate_root` 同为 `authoritative`。

下列四个「带生命周期状态机」的对象是 `process_manager` 的边界候选，经判定**保持 `aggregate_root` 不变**。共同判据：它们的状态迁移是一份业务事实自身的合法演进，失败即终态，没有需要补偿的已提交外部副作用，也没有「从 checkpoint 续跑」的恢复语义。

| 对象 | 保持的 kind | 保持原判的理由 |
|---|---|---|
| `content.MediaUploadSession` | `aggregate_root` | 只有 `pending -> completed\|aborted` 一次性迁移，且由 TTL 兜底作废；`aborted` 是终态而不是补偿动作，不存在中断后续跑。 |
| `user.AccountSession` | `aggregate_root` | 凭据轮换是单步 CAS（`active -> rotated\|revoked\|expired`），吊销即不可恢复；rotation lineage 是审计血缘而不是流程 checkpoint。 |
| `assistant.AssistantSession` | `aggregate_root` | 会话只承载身份、摘要与「至多一个 active run」的约束；被编排的长流程是 `assistant.assistant_run`，状态机与补偿都归 run 拥有。 |
| `rtc.CallSession` | `aggregate_root` | 通话状态机由实时信令与参与者事件驱动，收尾是终止并落一条通话记录；不存在超时补偿或失败重放。 |

## 4. 文件分工

`context.yaml` 只描述 bounded context；`object.yaml` 只描述对象种类、生命周期、规则和关系；`fields.yaml` 只描述字段；`operations.yaml` 只描述用例、transport 与端口；`storage.yaml`、`events.yaml`、`errors.yaml` 分别描述存储、事件和错误语义。

文件内不得重复路径身份、service、源码路径、DDD layer 或 readiness 结果。可从目录、入口、Kustomize 或测试运行推导的事实不进入 metadata。唯一测试路径例外是 `operations.yaml.readiness_cases[].runner_source_path`：它不是派生状态，而是当前 case 的受信 runner 身份，必须逐字绑定 receipt，且 loader 会验证对应文件内的精确 `spec_ref` 与 `readiness_case` 标记。

## 5. DDD 与 CQRS

依赖方向固定：

```text
adapters/inbound -> application -> domain
infrastructure --implements--> application/domain ports
generated --------------------> contract types only
```

- domain 不依赖 HTTP、数据库、消息中间件、配置框架或 transport DTO。
- application 组织用例与事务边界，核心业务规则留在 domain。
- command 只能修改 `aggregate_root`、`process_manager` 或 `runtime_session`；事实对象只允许 append。`process_manager` 的命令面是 `process_facade`，表达流程推进/取消/恢复，不是聚合状态写入。
- query 从 projection/read model 读取，不通过聚合仓储拼装复杂列表。
- infrastructure 只实现端口，不向 domain 暴露 SDK 类型。
- 禁止跨服务导入对方 `internal/**`。

## 6. Operation 编译

`operations.yaml` 中每个 operation 必须绑定：

- 稳定 operation ID 与 public/internal transport（如存在）；
- `application.kind`；
- command 恰好一个 `aggregate_owner`、`append_sink` 或 `lifecycle_owner`；session 单独绑定 `session_owner`；
- query 的 named `reader` 与 typed `slice`；
- HTTP 成功语义由 `response_body_kind`、`response_entity` 与可选 `success_status` 共同单轨表达：`ack` 只能是无 body 的 204，typed receipt 使用 `object/page` 与 200/201/202；WebSocket upgrade 固定协议 101，不声明 `success_status`；
- actor/auth、错误、可靠性及可观测策略；
- 实际需要的外部 capability/port（如存在）。

compiler 先解析所有对象，再解析关系和 operation；未解析引用、跨对象写 owner、projection command、事实 update/delete 或 owned child 直达均失败。

## 7. OpenAPI 与语言产物

域级 `openapi.yaml` 是生成快照，`operations.yaml api_routes` 是 transport 真相。生成器原子重建全部快照；missing、stale、orphan 任一状态都由门禁阻断。

OpenAPI、Go、Dart 和 Python 消费同一个 Graph hash。生成文件必须标记 `DO NOT EDIT`；手写代码只依赖生成契约，不复制 route、错误码、字段或枚举。

## 8. 配置与外部能力

- 每个服务的 `config/schema.yaml` 唯一定义配置键、默认值、约束、敏感性和 rollout 语义。
- `services/<service>/environments/{alpha,beta,gamma,prod}/config.yaml` 只保存 override、secret reference 和 external binding；环境之间禁止继承。
- package 阶段将 schema 默认值与单一环境差异渲染为 `<QWQ_DEPLOY_WORK_ROOT>/<env>/packages/services/<service>/config/config.yaml`，`CONFIG_VERSION` 由内容摘要派生。
- 公共资源和部署基线分别位于服务 `resources/`、`deploy/base/`；环境资源引用和部署差异位于同一 `environments/<env>` 入口。
- 对象声明外部 capability/port，服务环境入口选择真实 binding，Ops 只装配 external workload。conformance 结果按 evidence schema 保存，不维护 provider 或 assertion 注册表。

## 9. 测试与 readiness

测试物理路径与对象路径同构：

```text
services/<service>/tests/local_contract/<context>/<object>/...
services/<service>/tests/api_integration/<context>/<object>/...
quwoquan_app/test/user_acceptance/<domain>/<context>/<object>/...
quwoquan_app/test/user_acceptance/journeys/<journey>/...
quwoquan_ops/tests/acceptance/<environment_acceptance|rollback|replay>/<domain>/<context>/<object>/...
```

UAT/DOM/SIT/GWT 只在所属 feature-tree 节点定义。真实测试以 `spec_ref` 直接绑定验收锚点；runner 将锚点、实际测试、环境、制品摘要和结果关联。测试数、通过率和 readiness 全部由证据计算，禁止 tracked coverage map、手写状态或 exact-path 清单。

ContractGraph 的 `readinessEvidence` **只承载静态结构证据**，并按 producer 分侧：

- `service`：`domain`、`store`、`outbox`、`reader`、`transport`、`localContract`、`apiIntegration`；
- `app`：`domain`、`application`、`adapters`、`presentation`、`localContract`、`apiIntegration`、`userAcceptance`；
- `ops`：`environmentAcceptance`、`rollbackRunner`、`replayRunner`。

其中每个 artifact 严格只有 `{path, sha256}`；存储归属通过独立的 `StorageEvidence{storage, artifact}` 表达，不得把 owner/status/pass 塞回 artifact。静态 loader 只证明“实现 seam、测试入口或 runner 入口存在”，**不证明任何用例通过**。纯云对象允许 `app` 全空；App 各层是否必需由当前 `clientContract` 与页面物理 owner 派生。多对象页面的 `object_ids` 只表示 participant，不要求每个 participant 创建 presentation；只有 `source_path` 位于 `lib/service/<service>/<context>/<object>/presentation/**` 的对象是物理 owner。

所有执行结果独立进入 `ReadinessResultBundle`，不嵌入、不回写 ContractGraph。wire 不使用 `schemaVersion` 或版本信封；`generatedAt` 只标识 bundle 本身，绝不参与通过判定。`ReadinessCaseResult` 必须绑定 object/spec/case/producer/layer/target、当前 commit、ContractGraph source hash、当前部署的 `deploymentTarget`、`baselineId`、`packageDigest`、`configurationDigest`、`candidateManifestSha256`、candidate/release digest、environment/platform/device/provider、runner、时间区间及真实 receipt SHA256。ContractGraph source hash 由当前图 `sources` 中按 path 排序的 `path + NUL + sha256 + LF` 字节序列派生，evaluator 必须自行重算，禁止信任调用方传入的自述 hash。`failed`、`blocked`、`skipped`、旧 digest、未知 target、重复冲突和 receipt 字节不匹配一律 fail-closed。

每个对象的 `operations.yaml` 可声明 object-local `readiness_cases`；每个 case 必填 `runner_source_path`。职责与 target 是封闭组合：Service `local_contract/api_integration` 只能绑定本对象 operation 或 lifecycle object；App `local_contract/api_integration` 只能绑定 App-exposed operation；App `user_acceptance` 只能绑定 canonical page；Ops `environment_acceptance/rollback/replay` 只能绑定本对象。loader 将 operation/runtime entrypoint target 规范化为 fully-qualified ID，验证 feature-tree acceptance anchor、producer/layer/target 组合、对应的 canonical runner 路径、真实 regular test file，以及测试源码中的精确 `spec_ref: ...` / `readiness_case: ...` 注释标记，再把 runner source、契约 source 与精确 execution tuple 一并编译进 ContractGraph。evaluator 只消费 current ContractGraph 内这份 case policy，并要求受信 receipt 的 `runnerSourcePath` 与 authored path 逐字相等；同目录的另一测试也不能替代。未声明 case 合法地停在静态阶段，但动态 commercial closure 必须 fail-closed。

因此静态 `graph.Build` 的最高阶段只能是 `implemented`，`commercialReady` 恒为 false；动态 evaluator 以 current ContractGraph + current bundle + 受信 current snapshot/receipt resolver 生成独立 closure。operation target 必须归属该对象；page target 必须存在于当前图内嵌的 canonical `page_object_contract`，对象可以是页面 participant，或是从 object-shaped `source_path` 唯一派生的 physical owner，这两个角色分别计数；shell/design-system 页面不得伪造 object owner。object target 必须等于结果对象。Prod 必须绑定 `releaseDigest`，四环境验收必须绑定同一 candidate，页面 UAT、Provider、rollback 与 replay 只能由各自精确 case 关闭，不能由同对象任意 passed 结果顶替。

receipt resolver 是动态信任边界：它必须校验真实 evidence/runner/environment attestation 后才返回 trusted receipt；单纯读取磁盘 JSON 永远不构成准出证据。receipt 必须复述 bundle 的 object/spec/case/target/hash/digest/deployment/environment/platform/device/provider/runner/time 身份，并以 `providerVerified` 证明 Provider identity 来自实际环境证明而不是静态配置名。UAT receipt 还必须绑定 `quwoquan_app/test/user_acceptance/<domain>/<context>/<object>/...` 或 `.../journeys/<journey>/...` 的 runner source，并显式证明 Remote composition、无 fixture、依赖已就绪与 `physicalDevice`；physical Android 与 physical iOS 是两个不可互相替代的 execution slot。环境验收、rollback、replay 同样禁止 fixture 或依赖未就绪的结果。

当前部署身份来自独立签名的 `CurrentSnapshot`：`deployments` 必须且只能包含 `alpha/beta/gamma/prod`，每个环境都给出上述五个 deployment 字段，四环境必须绑定同一 `packageDigest` 与 `candidateManifestSha256`。`PackageDigest`、`ConfigurationDigest`、`CandidateDigest`、`ReleaseDigest` 使用 `sha256:<64 lowercase hex>`；字段名明确为 `*Sha256` / `*Hash` 的值使用裸 64 位 lowercase hex，禁止两种格式双读。签名 snapshot、keyring、detached receipt signature、bundle、receipt、evidence 与五份 canonical readiness schema 全部执行 bounded regular-file/contained-root、重复 JSON key 拒绝及读前后 identity 校验；schema 目录或文件是 symlink、并发替换、未知字段、尾随文档均 fail-closed。

生产 evaluator CLI 必填 current graph、bundle、signed snapshot、snapshot/runner keyring、receipt/evidence root 与 `--metadata-dir`。它只在完整 commercial closure 时返回 `0`；结果合法但未闭合返回 `1`；输入、schema、签名、文件身份或信任链异常返回 `2`，三种路径均只输出一个 JSON 文档。调用它的 Python gate 只能负责进程隔离、timeout 与 JSON/exit-code 检查，不得复制 Go policy；exit `1/2`、timeout、非 JSON 或 TOCTOU 都必须保持 `GATE_BLOCK`。

### 9.1 事务性事件发布 seam 的必需性：按事件投递保证

发件箱存在的唯一理由是「状态已提交、事件却可能丢失」这一跨边界后果。所以要求不按 kind 一刀切，也不按「是否声明了事件」一刀切，而是按对象自己 `events.yaml` 里每条事件的 `delivery_semantics` **投递保证**派生（实现见 `internal/metadata/ast` 的 `ClassifyEventDelivery`）：

| 取值 | 语义 | 是否要求 seam |
|---|---|---|
| `not_published` | 事件留在聚合自己的存储里（自留事实或聚合 journal），读取方直接读 aggregate | 否 |
| `best_effort_ephemeral` | 语义上明确允许丢失的瞬时信号；持久真相由另一条事件承载，丢了由端侧重新拉取 | 否 |
| `transactional_outbox` | 与聚合状态同事务写入发件箱，由 relay 搬运出去 | 是 |
| `transactional_event_log` | 与聚合状态同事务追加到事务性事件表，可靠落地即完成义务，不需要搬运 | 是 |
| `durable_stream` | 直接追加进有留存的 durable stream，产出侧没有事务性发件箱 | 是 |
| `synchronous_call` | 跨边界同步调用 / 内部 HTTP 投递，声明了投递却没声明可靠机制 | 是 |

判定依据的三条原则，新增取值按此自判，不要按名字像不像猜：

1. **只问投递保证，不问 consumer。** consumer 归属在别的服务手里，把本对象的可靠性义务挂在别人是否订阅上会产生远距离作用——别的服务加一条订阅就能让这个对象悄悄变红，撤掉又变绿，而本对象什么都没改。零消费者的 `transactional_event_log` 审计日志同样要被可靠追加。
2. **豁免只给「事件根本不跨边界」。** `synchronous_call` 声明了跨边界投递却没声明可靠机制，仍归要求侧，缺口如实暴露；要豁免必须先在契约里把语义改成自留，而不是靠 readiness 放水。反过来，为 `not_published` / `best_effort_ephemeral` 建发件箱与 relay，只会造出永远没有下游的空转 relay，同样是为门禁写代码。
3. **值域由 schema 强制，不靠规则侧兜底。** 这个字段的前身 `channel` 没有值域：229 条事件写出 25 种取值，同时混装投递机制、6 处 `outbox` 笔误和 12 种 topic 名，另有 3 条连键都没有。当时只能让规则对未知取值与缺键 fail-safe 到要求侧，并把触发原因当独立缺口渲染出来——那是**补偿手段，不是设计**。拆分后 `delivery_semantics` 由 `_schemas/events.schema.json` 的 enum + required 强制，topic 名归自由字符串 `topic`，`channel` 被 schema 明确拒绝（`"channel": false`），不留并存过渡态；两类补偿维度随之关闭。`ClassifyEventDelivery` 仍对未知取值 fail-safe 到要求侧，防的是绕过 schema 的调用路径，不是可发生的契约状态。

`delivery_semantics` 与 `topic` 是两件事，不得再合回一个字段：前者是**保证**，判定 seam 必需性与 consumer 义务；后者只是**传输地址**，不表达任何保证。同一个 topic 上可以有不同保证的事件，同一种保证可以落在不同 topic 上，`events.user.account` 这种取值过去两头都占，结果两头都判不准。`client_ws_type` 又是第三条轴，只决定客户端 WebSocket wire type；它既不是 event identity，也不是 topic。

`topic` 是**可选**的，缺省表示「契约没有给这条事件命名传输地址」，不表示没有投递。它单值，因此不能当路由表用：同一 outbox 被多条独立 checkpoint relay 扇出时，事件可以不写 topic，具体 relay 的地址归运行配置与 adapter；禁止挑其中一路填成全部。

事件与 consumer 的唯一身份和唯一 authored edge 是：

```text
event_ref    = <producer objectId>.<events[].name>
consumer_ref = <consumer objectId>
edge         = consumer object.yaml lifecycle.source_events[]
```

`events[].name` 只写 PascalCase 本地名；`event_ref` 由对象路径派生，不写 producer/service/topic。消费对象必须在 `source_events` 写完整 `event_ref`；compiler 反向生成 `event_ref -> consumer_ref[]`，禁止 name-only 推断、producer-side `consumers`、顶层 `consumption/subscriptions` 或中央 consumer registry。

`wire_event_type` 是第四条独立轴，只存在于 `delivery_semantics: transactional_outbox` 的事件，精确表示 relay 写入消息 envelope 的 `eventType` / `eventName` 值。它不等于 `event_ref`，也不得从 PascalCase `name`、`topic` 或 `client_ws_type` 猜测：例如 Report 事件的生产 wire 保留完整对象前缀，MediaUploadSession 的生产 wire 保留点分值，而绝大多数对象使用 PascalCase wire。schema 强制每条 outbox 事件声明该值且非 outbox 事件不得携带；validator 强制全图唯一。两条 Go 事件常量生成链都从该字段发射常量值，producer 与 consumer 只消费生成常量，不得再各自维护点分/短名字符串。生成窗口之前无法引用尚不存在的对象常量时，该 runtime 硬切保持显式 source blocker，不得以双读或 alias 过渡。

`lifecycle.event_consumers[]` 只声明对象内真实 handler 的 `name/kind/facet/method/idempotency`，不得重复事件列表，也不得被编译成 operation target。HTTP `api_routes` 与 `runtime_entrypoints` 仍按 DEC-011 互斥；有 HTTP 的消费对象由 object-target readiness case 验证真实 handler，只有完全没有 HTTP 入口的对象才保留唯一 typed `runtime_entrypoints`，其事件边仍只读取 lifecycle。
对象自有 lifecycle consumer 的受控恢复 HTTP 命令使用 `application.lifecycle_owner`；它不得伪装成 `aggregate_owner` 或 `append_sink`，且 owner 必须是当前对象并声明 `lifecycle.source_events` 与 `lifecycle.event_consumers`。

validate 层的 consumer 义务以反向索引和投递语义精确判定：

- `transactional_outbox` 必须至少有一条反向 consumer edge（`CONTRACT.EVENT.OUTBOX_WITHOUT_CONSUMER`）。发件箱与 relay 的全部存在理由就是把事件交给别人，没有收件人的 relay 是没接完的线。
- `transactional_event_log` 与「有具名 consumer」互斥（`CONTRACT.EVENT.EVENT_LOG_WITH_CONSUMER`），这是第 9.2 节那条互斥在事件侧的执行。
- 任意事件零反向边时必须给出 `no_consumer_reason`；有边时必须删掉它。理由不能豁免上一条 outbox 义务，只让缺边原因可见。

旧实现以 `strings.Contains(channel, "outbox")` 判投递义务，再相信 producer 文件里的自由字符串 consumer。前者让 topic 字样改变保证，后者无法定位 consuming object/runtime entrypoint。当前实现同时删除这两条推断轨：保证只看受控枚举，consumer 只看可解析的完整反向边。

seam 的**识别**同样按结构事实，且不绑定命名：`transactional_outbox` 与 `event_store` 是同一义务的两种实现形态，所以除了 outbox 命名的声明/SQL 之外，还承认「与聚合状态同事务提交的事件表追加」——判据是**追加走事务句柄**（函数持有 `pgx.Tx` / `*sql.Tx` / `mongo.SessionContext` 这类事务类型的参数或局部变量，或变量由 `BeginTx` / `WithTransaction` 取得），并且同一函数里出现 journal 关系名形状的字面量或针对它的 SQL。持有句柄意味着这段追加要么随该事务提交、要么随它回滚。**不承认标识符里出现 `event` 一词**——那等于把 token 匹配换个词重来。

有命令的聚合必须在 `events.yaml` 里显式表态（声明事件或写下 `events: []`）；连文件都不存在等于既没声明也没否认，由同一门禁报 `contract.domain_events_undeclared`，不得静默跳过发件箱要求。

静态 compiler 不得把源码或测试文件“存在”解释成测试通过——这条红线不因结构性证据可派生而松动：结构性证据的字段名、门禁文案与报告都必须以“入口存在”表述，禁止出现“已验证 / 已通过”的措辞。

**结构性证据本身也必须由结构事实派生，禁止关键词命中充当证据。**「文件里出现过某个词」不是 seam 存在的证明：注释、TODO 与错误文案都能包含该词，甚至可能是一句**否认**（曾经 `user.authentication_challenge` 因为注释写着“本对象不制造纸面 outbox”而被判定为有发件箱）。因此判定依据只能是编译器/解释器看得见的结构：

- 层证据（`service.domain/store/reader/transport` 与 `app.domain/application/adapters/presentation`）来自对象实现根下真实存在的 production 源文件，测试文件、测试替身与 fixture 一律排除。
- `outbox` 是唯一没有专属层目录的 seam，只能在文件内部识别，判定依据限定为：Go AST 里的标识符与 import 路径（注释不进 AST，字符串字面量不是标识符）；字符串字面量只有在整体是一个表/集合名形状的 token，或是一条针对 outbox 关系的 SQL DDL/DML 时才算（`INSERT INTO x_outbox(...)` 算，`"outbox event is not aligned"` 不算）；Python 侧对应地剥掉注释与字符串后再判定标识符，字面量按同一套 SQL/表名规则判定。
- `page` 来自 `_shared/page_object_contract.yaml` 的认领与端侧页面文件求交；`appClient`、三层测试入口来自对象化目录下真实存在的文件。

新增或放宽任何一类结构性证据的识别方式时，必须同时补一条能失败的负例测试：把「注释里提到」「TODO 里提到」「错误文案里提到」钉成不成立。

结构性证据以 `--repo-root` 为基准解析物理路径（metadata 视图只含 YAML，不含源码与测试），缺 `--repo-root` 时 `qwq-contract` 必须 fail-closed 报错，禁止静默产出 `readinessEvidencePackets=0` 让“规则未接线”看起来像“证据还没到”。派生期缺证据是正常结果：记为无证据并由 `objectReadiness.missing` 如实暴露，禁止 fail-fast，禁止占位证据。

`qwq-contract coverage` 只报告静态结构阶段：阶段分布互斥，`modeled`、`contractReady`、`implemented` 按前置关系累计，`commercialReady` 在静态图中恒为 0。动态 closure 另行报告商业准出；任何 operation 仍为 `commercial.status: blocked` 时，四环境或 UAT 结果都不得把对象提升为 commercial-ready。

### 9.2 发布归属的判别位：`storage.yaml` 的 `publication_role`

上节确定了「哪些对象**必须**有事务性事件发布 seam」，本节确定「**哪张存储**承担它」。这两问必须分开：前者由事件的投递语义派生，后者只能由存储自己声明。

之所以不能沿用存储名推断，是因为名字与角色不同构，且两个方向同时出错：`*_outbox_sequences` 这类只保存序列号的**配件**会被 `outbox` 子串误捕成发件箱，而 `skill_consent_events` 这类与聚合状态同事务提交的**事务性事件表**又完全捕不到。子串判据在这里既产假阳也产假阴，不存在把阈值调准的余地。因此 `publication_role` 是发布归属的唯一判别位：

| 取值 | 语义 | 判据 |
|---|---|---|
| `transactional_outbox` | 事件在此可靠落地，**并需要被搬运出去**：存在或应当存在 relay 推进投递 | 事件跨出聚合边界才算生效 |
| `transactional_event_log` | 事件在此可靠落地即完成义务，**不需要搬运** | 该存储上的事件**无具名消费者** |
| `publication_accessory` | 服务于发布但自身不承载事件：序列号、checkpoint、水位、去重表 | 删掉它发布会坏，但它里面没有事件 |
| `not_published` | 与事件发布无关的业务存储 | —— |

`transactional_event_log` 与「有具名消费者」互斥，**无例外**。有消费者却观察不到投递路径时，正确归属是 `transactional_outbox` 加一条 relay 缺失的实现缺口，不是把它标成 `event_log` 让义务凭声明消失——后者会把「投递断了」洗成「本来就不用投递」。

「无具名消费者」只由 compiler 反向索引 `len(consumersByEventRef[eventRef]) == 0` 判定，不再从 producer YAML 读取任何 consumer 列表。零消费者必须给出理由（`CONTRACT.EVENT.MISSING_NO_CONSUMER_REASON`），有消费者必须删掉理由（`CONTRACT.EVENT.STALE_NO_CONSUMER_REASON`）；任何绕过 compiler 直接读 YAML 的判定都属于第二真相源。

**与事件侧同源。** `events.yaml` 的 `delivery_semantics`（§9.1）与本节的 `publication_role` 对同一事实使用同一套词：`transactional_outbox`、`transactional_event_log`、`not_published` 三个值在两处含义完全一致，上面那条「`transactional_event_log` 与具名消费者互斥」在事件侧由 `CONTRACT.EVENT.EVENT_LOG_WITH_CONSUMER` 执行。差异只在两处，且都是**辖域**差异而非语义差异：`publication_accessory` 描述的是存储在发布链路里的位置，事件没有对应形态；`durable_stream` / `synchronous_call` / `best_effort_ephemeral` 描述的是不落在本服务事务性存储上的投递方式，存储没有对应形态。两个字段的粒度也不同——一张存储可以承载多条事件，事件侧是更细的真相，存储侧回答的是「哪张表承担」。

**未标注不等于不发布。** 未标注是可见缺口，由 `quwoquan_ops/gate/verify_object_evidence_closure.py` 报 `contract.storage_publication_role_unannotated`，不得默认落到 `not_published`——默认到豁免侧会让「忘了标」和「确实不发布」变成同一个结果，而这正是子串判据的老毛病换了个形式。同理，声明本身也只表达**意图**：标了 `transactional_outbox` 不代表 relay 存在，实现侧仍按上节的事务句柄判据独立取证，声明与实现的缺失是两个独立缺口维度。

## 10. 治理门面

`make verify-service-architecture` 是统一门面，内部组合 metadata、路径反向映射、DDD/CQRS、配置四环境、拓扑、外部能力和测试目录门禁。专项脚本是门面的内部实现，不形成第二套人工流程。

任何报告中的对象数量、kind 分布、operation 数量和 readiness 都必须由当前 Graph 或 runner 生成，不在文档手工维护。
