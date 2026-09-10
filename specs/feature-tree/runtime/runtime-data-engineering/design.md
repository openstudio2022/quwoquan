# L2 Design：运行时数据工程 (`runtime-data-engineering`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入”需要 `article-commercial-scale-closure`、`geo-content-trinity`、`image-commercial-scale-closure`、`video-commercial-scale-closure` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

四个历史 carrier Story 退役其 execution/pool/milestone/release/UAT 业务 ownership，只保留仍具跨域唯一价值的 consumer contract：

- [`article-commercial-scale-closure`](./article-commercial-scale-closure/spec.md)：文章 canonical closure 到 importer/query 的字段与 failure 语义。
- [`geo-content-trinity`](./geo-content-trinity/spec.md)：四载体共同引用闭包在 runtime consumer 的同 identity 对账。
- [`image-commercial-scale-closure`](./image-commercial-scale-closure/spec.md)：图片 asset disposition/generator 在 consumer wire 的 fail-closed。
- [`video-commercial-scale-closure`](./video-commercial-scale-closure/spec.md)：视频 attribution/media package 到 service/App 的无损投影。

execution、reviewed delivery、canonical pool、milestone 与 release build/handoff 业务规格归 [`discovery-content/object-homepage-coverage-scaling`](../../discovery-content/object-homepage-coverage-scaling/spec.md) 的 producer owner；promotion 与 UAT/acceptance 归下游环境 owner。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 runtime-data-engineering 只拥有 immutable release consumer 边界
- 决策：本节点不拥有数据任务 execution、pool、milestone、release build/handoff，也不拥有环境 promotion 或 UAT/acceptance；前者归 discovery producer owner，后者归下游环境 owner。runtime-data-engineering 只拥有 importer/outbox、Search/Recommendation/Homepage 与 App media projection 对公开 immutable release ref/digest 的消费边界。
- 理由：同一 release/UAT 事实存在两个 owner 会产生冲突 gate；runtime 的唯一跨域价值是确保消费者不改写、不猜测且同 identity readback。
- 被否决方案：在四个 carrier Story 重复环境晋级或 acceptance OPEN；由 runtime integration PASS 代替 discovery 的 fresh Gamma/device evidence。
- 失败恢复：上游 ref/digest 缺失或漂移时 consumer fail closed；恢复只在上游 owner 修复后重放 importer/query，不在本域补造 release/UAT。
- 可测试面：api_integration 绑定同一 immutable release 的 importer/outbox/query/readback；静态测试断言本节点无 execution/pool/milestone/release/UAT command owner。
- 关联要求：`REQ-001`、`REQ-002`
- 影响 Story：[`geo-content-trinity`](./geo-content-trinity/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 content library 与 pool/release 只作为上游只读事实
- 决策：content library sole-holder、canonical object package/pool record 与 immutable release 均由上游 owner 单写。本域只消费 media binding、manifest digest、access mode 与 object refs，不拥有 holder、selection seal、materialization rebuild 或 pool repair command。
- 理由：consumer 取得写权会让 sole-holder 与 release owner 分叉；跨域层只需验证 exact binding 并 fail closed。
- 被否决方案：从 runtime cache、旧 release、fixture 或 App 本地字节回填 canonical；从 SourcePool/execution/campaign/provider/model 推导 eligibility。
- 一致性与恢复：binding 不可达或 digest 漂移时 importer/query 整体或逐对象按公开契约阻断，owner bytes 不变；恢复后 exact replay。
- 可测试面：local_contract 锁定 consumer schema 白名单，api_integration 覆盖 binding 漂移与 exact replay。
- 关联要求：`REQ-001`、`REQ-002`
- 影响 Story：[`geo-content-trinity`](./geo-content-trinity/spec.md)
- 关联验收：`SIT-001`

<a id="dec-003"></a>
### DEC-003 Content active pointer 是跨域唯一可见性 fence
- 决策与 owner：active pointer 及 candidate 存储位于已验证 deployment target 的独立权威内，同 environment 的不同 target 不共享可变 pointer。activation 与 rollback operation 仍由下游环境 owner 发起（`REQ-002` 的 environment operation 语义不变）；Content 不选择 release，只在环境 owner 的 operation 内执行 owner-bound expected-current CAS 写 active pointer。immutable release tuple 固定为 `(environment, sourceOwner, releaseId, manifestDigest)`，是 Tag、Creator、Homepage、Content 四域 candidate 的唯一身份；pointer 在该 tuple 之上附带 CAS 成功时产生的单调 `revision`，`revision` 只标识 pointer 世代，不参与 candidate 身份，回滚到 previous release tuple 会产生新的更大 revision 而不复用旧值。上游 discovery owner 只交付 immutable release，Tag/Creator/Homepage 各自只 stage 与 release tuple 绑定的 immutable verified candidate，并返回 exact query receipt；stage、校验或 receipt 创建均不改变旧 live。Content 只在自身 Post/outbox candidate、其余三域 receipt、完整媒体闭包，以及首页/premium/必要详情所需 candidate-scoped Recommendation/Search 查询投影全部 exact ready 后 CAS pointer。查询准备通过 Content owner 的正式 lifecycle 准备边界驱动各域 owner，不直写派生库、不新增第二 active flag；尚无 typed 准备契约或完整 receipt 时阻断激活，而非把 CAS 后异步追平描述为无中断。四域及必要查询以一次读取的 active pointer pin 同一 candidate，CAS 一次暴露完整闭包。激活事件继续承担提交后通知/对账，但不作为首次可读的唯一准备触发。
- 理由：分域切换会混版本，CAS 后才准备推荐/精选又产生 fail-closed 空窗；将完整媒体、四域和必要查询预物化纳入同一准入屏障，在保留各 owner 单写与环境发起/Content CAS 分工的同时，让一次 pointer 切换暴露完整可读闭包。
- 被否决方案：Tag/Creator/Homepage 或推荐/精选各自 activation；stage 覆盖 live；CAS 后异步追平冒充无中断；直写索引/精选 seed；按 counts/latest/LKG 猜 active；revision 纳入 candidate 身份；Content 自选 release；下游 readback 回写 producer handoff；读取失败在线 fallback 到旧版本。
- 失败恢复与回滚：CAS 前任一 stage/校验/receipt 失败或 CAS conflict 均保持 previous pointer 与旧 live，candidate 可保留供诊断但不可见。Content CAS 已返回后，任一 fenced readback 超时、不可达或身份不一致都返回 typed `ambiguous`，不得自动重试 CAS、猜测成功或选择某域结果；环境 owner 必须先 query exact pointer（含当前 revision），再发起显式 rollback operation，由 Content 以 asserted current tuple+revision 作 expected-current CAS 回 previous fully verified release tuple 并生成新 revision，随后重做四域 fenced readback。rollback 冲突或 readback 失败继续 fail closed，不改 canonical、pool、content-library 或 producer bytes。
- 读会话与资源：页面、详情、分页及媒体会话固定同一内容版本；版本切换使旧 cursor 明确失效并重取第一页，不混旧 cursor/新对象/旧媒体。新旧不可变数据和媒体保留到活跃读引用与回滚窗口结束再 GC，不覆盖在播文件。
- 首次激活恢复：没有 previous 的准备失败保留无 active 状态；CAS 结果未知先 query exact pointer，不猜空或旧 release。确认新 pointer 已激活但 readback 失败时保持 ambiguous/阻断；仅在 canonical operation 支持并经授权时显式 CAS 到已验证 empty baseline，否则等待 owner 恢复，不伪造回滚成功。
- SLI/SLO 与告警：记录媒体闭包、四域及必要查询 ready、CAS conflict、fenced identity、ambiguous 与 rollback outcome；CAS 后 60 秒必须取得四域及 required 查询/媒体 exact fenced readback，否则告警并阻断；显式 rollback 后 5 分钟恢复 previous 完整闭包，否则持续阻断。这是目标，未测不称达成。
- 可测试 seam：Data 侧四域 receipt 的 exact-bytes evaluator 为 `quwoquan_data/scripts/content/release/environment/owner_local_staging_admission.py`，只消费显式 receipt ref+digest，不扫描 latest、不接受 import report 代替 candidate proof；local_contract 注入 stale/missing receipt、CAS race 与 readback timeout，证明 candidate immutable、stage 零 live mutation、CAS 只接受 release tuple 与 asserted revision 且 post-CAS failure 不会自动猜测或重试；api_integration 覆盖 previous→candidate→previous，断言 CAS 前旧 live 持续可读、CAS 后四域只见同 tuple、rollback 后 revision 单调递增，ambiguous 经显式 rollback 收敛且 owner bytes 不变。
- 关联要求：`REQ-002`、`REQ-004`
- 影响 Story：[`geo-content-trinity`](./geo-content-trinity/spec.md)
- 关联验收：`SIT-001`、`SIT-002`，并由 [`environment-topology-and-packaging GWT-007`](../runtime-config/environment-topology-and-packaging/spec.md#gwt-007) 验证 candidate 查询屏障、缺媒体/精选、CAS race、首次无 previous 与恢复时限；未设计完成的 typed 准备面及未测闭环登记该 Story OPEN-019，不以现有异步实现宣称通过。

<a id="dec-004"></a>
### DEC-004 image generator 由 Post manifest schema 单轨拥有
- 决策：Post manifest materializer 是 `generator` 的唯一写 owner，并只写 schema 已声明的 `agent`。image evidence pack 继续作为 execution/source/review 的内部 evidence，不成为第二个 generator 值；pool validator 与 release selector 只读通过 canonical schema 的 manifest。
- 理由：`generator` 表达交付 copy 的 authoring 身份，而 evidence pack 表达素材与审核证据。把两者塞进同一 wire 字段会让 schema、materializer 与 release reader 对对象身份产生分叉。
- 被否决方案：schema 增加 `image_evidence_pack`、reader 双读、warn-only 放行、按 carrier 推导默认值，或原地修补旧 manifest/receipt。
- 失败恢复：非 canonical generator 使单对象 typed excluded，不阻断同池其它对象；仅允许基于原 terminal evidence 的 replay/adopt 创建新 manifest，不重跑已闭合上游。
- 可测试观察面：Post manifest schema validation、image materialize 输出、provenance/pool record 与 release selection；对象级 local_contract 证明所有交付 manifest 为 `agent` 且不存在 compatibility fallback。
- 关联要求：[`image-commercial-scale-closure/REQ-004`](./image-commercial-scale-closure/spec.md#req-004)
- 影响 Story：[`image-commercial-scale-closure`](./image-commercial-scale-closure/spec.md)
- 关联验收：[`image-commercial-scale-closure/GWT-004`](./image-commercial-scale-closure/spec.md#gwt-004)

<a id="dec-005"></a>
### DEC-005 宿主 execution 只作为 discovery owner 的只读上游
- 决策：宿主 AI producer 九阶段、OPEN/CLOSE receipts、逐对象 publish 与显式 cohort release handoff 归 discovery producer owner；ship/environment facts 归下游环境 owner。本节点不定义 Skill、stage control、recovery 或执行状态投影，只允许 consumer diagnosis 通过公开 release/handoff/环境 operation ref 追溯。
- 理由：执行推进方式不是 runtime consumer 的业务事实；在本域再拥有一套会与 discovery 单轨分叉。
- 被否决方案：仓内 managed SDK/controller/campaign/runner/fleet/claim、stage-gate/semantic wrapper/reducer、runtime view 回写 execution，或由 importer/UAT 写业务 verdict。
- 失败恢复：execution 问题返回上游 typed ref；本域只能重跑自己的 importer/query，不创建 `retryOf` 内容 execution。
- 可测试面：静态 owner test 与 projection-only local_contract。
- 关联要求：`REQ-005`
- 影响 Story：[`geo-content-trinity`](./geo-content-trinity/spec.md)
- 关联验收：`SIT-003`

<a id="dec-006"></a>
### DEC-006 runtime 运营对象仅投影 consumer facts
- 决策：本域 View 只投影 importer/outbox/query/active pointer 与公开上游 release refs；无 command、Repository、checkpoint、独立 lifecycle 或 owner-fact 修复能力。
- 理由：跨 owner 查询可重建，持久 checkpoint 会成为第二状态台账。
- 被否决方案：View 写下一环境、acceptance、release selection 或 execution terminal。
- 恢复：缺 fact/digest drift 返回 typed incomplete/conflict，修 source fact 后重建。
- 可测试面：删除重建 exact 相同且 owner bytes 不变。
- 关联要求：`REQ-005`
- 影响 Story：[`geo-content-trinity`](./geo-content-trinity/spec.md)
- 关联验收：`SIT-003`

<a id="dec-007"></a>
### DEC-007 UAT runner 只消费 runtime readback，不拥有 acceptance
- 决策：sample plan、target binding、raw `ReadinessCaseResult` 与 `EnvironmentAcceptanceFact` 的 authority 继续由 discovery/metadata/Ops owner；runtime 只提供被 required runner 调用的 release-bound readback。
- 理由：readback producer 与 UAT result/acceptance writer 是不同 owner；本域 PASS 不能代替 registered physical device raw facts 或 Gamma acceptance。
- 被否决方案：把 verdict 写进 Data readiness、由 bundle/counts 推导 acceptance、从 runtime integration 触发上游内容生产。
- 失败恢复：readback 缺失或漂移只返回 typed blocker，不写 raw result/acceptance；由外层 runner 保留真实结果。
- 可测试面：local_contract 锁定 port 只读，api_integration 提供同 release/candidate readback。
- 关联要求：`REQ-006`
- 影响 Story：[`geo-content-trinity`](./geo-content-trinity/spec.md)
- 关联验收：`SIT-004`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本/bytes 冲突、锁冲突、环境 baseline 未收敛、inventory/holder 漂移、target 前置缺失、required raw result 缺失或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写 ship succeeded 或追加伪 `EnvironmentAcceptanceFact`。
- execution 恢复：写前失败保持 canonical 不变，terminal 只以新 `executionId + retryOf` 恢复。reset 后只按 terminal evidence replay/adopt。
- 环境恢复：追加新的 operation/readback/Exit/raw result facts 并重新求值，不改旧 execution/acceptance。
- materialization 恢复：只从 content library sole-holder exact rebuild。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写、compatibility shim、View Repository/checkpoint 或页面本地写副本。

## 6. 质量与观测

- 成本影响保持同量级：reset 只处理 canonical publish/inventory 元数据，replay 成本与被选 terminal execution 数量线性相关；release materialization 可重建，不引入 content library 之外的长期 media holder。
- reset 写阶段在取得锁后 60 秒内完成或 fail closed；环境从 empty baseline 恢复原 release 的目标为 5 分钟内完成。超时只产生失败 receipt，不放宽锁、holder protection 或 closure。
- SLI 直接读取 create-once reset/producer-stage receipt 与下游 ship receipt、empty/replay lifecycle、canonical identity state query、raw readiness result、target binding 与 acceptance fact 的完成状态和耗时；View 与 bundle 只做查询，不新增第二份状态台账。
- 内容生产启动不由 Runtime 决定；本域在正式 candidate 准备边界预物化 required 查询闭包，active pointer 改变后按 same digest 对账，不重新选择内容。既有消费缺口保留在本能力 OPEN-004/005/008；无中断准入的新设计与实证缺口由环境 Story OPEN-019 承接。
