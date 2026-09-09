# L2 Design：对象主页与多载体供给 (`object-homepage-coverage-scaling`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“可复用实体主页与多载体内容供给、发布和环境消费闭环”需要 `multi-carrier-release` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：可复用实体主页与多载体内容供给、发布和环境消费闭环。
- 设计目标：宿主 AI 原生串行或并发执行 producer 六步（init → acquire → author → review → publish → release），跨会话只以三份 create-once seal receipts 与业务产物交接。
- 设计目标：内容运营者的 typed intent 在写入 execution 事实前经过 preview 与显式确认，并只编译到现有 carrier demand。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`work-request-compilation`](./work-request-compilation/spec.md)：上游 confirmed intent 收敛为现役逐载体 demand，确认前零 execution 事实；旧 handoff/WorkRequest/envelope schema 已删除。
- [`on-demand-content-pool-admission`](./on-demand-content-pool-admission/spec.md)：消费 confirmed carrier demand 与只冻结目标对象身份的 immutable candidate bindings；来源选择、字节取得、质量判断、创作与独立审核均在 execution 内完成，再由 AI 逐 approved 对象进入 canonical 池。
- [`source-discovery-scale-reliability`](./source-discovery-scale-reliability/spec.md)：来源发现由宿主 AI 原生串行或并发执行，仓内 scheduler/worker/slot/heartbeat 控制面属于硬删除范围。
- [`canonical-content-identity-recovery`](./canonical-content-identity-recovery/spec.md)：invalid canonical identity 的显式治理属于独立 owner，不参与内容生产编排。
- [`multi-carrier-release`](./multi-carrier-release/spec.md)：每个发布对象必须闭合 creator、tag、entity、media 与 source 引用，运行 receipt 只能写入输出目录、不得回写静态真相源；canonical 池之后的 immutable release handoff 由 producer 拥有；环境与 App 消费由下游环境 owner 只读 handoff 后独立拥有。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 四载体共享实体目录并由宿主 AI 执行唯一六步 Skill
- 决策：homepage、article、image、video 从同一 canonical entity catalog 形成彼此独立的 immutable execution；唯一 producer 流程是宿主 AI 直接执行 `.agents/skills/content-production/SKILL.md` 的六步，并在 `release finalize -> END`。已退役编排与兼容读写必须在生产源码、schema、control plane、正向测试与 active specs 中物理归零，具体 token 只由反向门禁维护。
- 边界：producer 代码仅做 `task init`、`task acquire`（按 AI 点名的 URL 机械取得字节/license/作者/probe/poster）、`task seal`（自行校验硬事实并 create-once 写三份 receipt，review seal 补齐 content_review 机械字段）、单对象 publish 与 `release finalize`。来源是否切题、选材、创作、review 判断、verdict、typed issues、approved 对象、cohort/milestone、文章结构与作者人设均由宿主 AI 显式决定；后继只来自 Skill 固定顺序。既有 ship I/O 属下游环境 owner，不是 producer stage。
- 失败恢复：按 receipt 找首个未闭合步骤继续；receipt blocked 后新建 execution，不在原 execution rewind 或迁移旧状态。
- 可测试面：local_contract 锁定零旧 import/CLI/schema/reference、seal receipt create-once、AI 显式结果与单对象原子 IO；api_integration 证明四载体可由宿主直接执行。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：`GWT-020`

<a id="dec-022"></a>
### DEC-022 candidate 只冻结对象身份，source 与 review 在 execution 内单轨形成

- 对象边界：immutable candidate binding 只冻结目标对象身份、carrier、canonical coverage target 与 candidate identity；它不携带或要求 task-init 前 source/media admission、acquisition、rights 或 semantic verdict。`acquire` 由宿主 Cursor/Codex Agent 点名来源 URL 与相关性理由，脚本取得 bytes、登记 source refs 与媒体 CAS/hard facts；语义保留与结构组织由 AI 在 author 时直接完成，不存在 2.quality/3.compose 产物。
- 单一产物：`4.draft` 每对象只有载体主产物 `page.md|draft.article.md|image_work.json|video_script.json`；author actor/invocation 与产物 exact ref/digest 只由 `002-4.draft` seal receipt 冻结，不再写 `draft_meta.json`、`author_self_check.json` 或 `agent_result_envelope.json`。`5.review` 每对象只有 `content_review.json`，统一承载 `approved|rejected`、简短 dimensions/blockingIssues 与逐资产 rights 结论；reviewer actor/invocation 及该文件 exact ref/digest 只由 `003-5.review` seal receipt 冻结，机械字段由 seal 补齐，不再建立独立 review receipt 或镜像 verdict。
- 固定时序：唯一顺序为 `identity-only candidate binding -> task init -> acquire(1.download/) -> author(4.draft/) -> review(5.review/) -> publish -> release finalize`。acquisition/probe/digest/MIME/license 是 acquire 的机械硬事实；rights hard facts 在取得时保留，逐资产使用裁决只在独立 `content_review.json` 单写。
- 语义主体：来源选择与相关性、创作、结构、作者人设与 review 的唯一主体是直接执行 Skill 的宿主 Cursor/Codex Agent。仓内只做 deterministic init、acquire、seal、原子 publish 与 release finalize；不得新增 resolver、projector、runner、controller、queue、registry、SDK、自动恢复或 actor projection。
- 失败恢复：source/ref/digest 或 step-wide identity/integrity 漂移时当前步骤 blocked；逐对象 approved/rejected 可混合，短缺写入 stage result artifact/typed issue，通用 receipt 仍只有 `pass|blocked`，只有零 approved 或 stage-wide identity/integrity failure 才 blocked。blocked 后用新 execution 重试，不改写旧 receipt。
- 可测试面：local_contract 证明 candidate binding 不要求 source admission，`002-4.draft`/`003-5.review` receipts 各自冻结真实 actor 与唯一业务产物 exact refs，publish 只消费 `content_review.json` 的 approved 对象；api_integration 从 identity-only Image/Video candidate 跑通 download→review→publish 并覆盖 identity/digest drift。
- 被否决方案：task-init 前 media admission；source-scoped semantic review；独立 review receipt 作为第二 authority；三份 draft 元数据镜像；四份 review/attestation 镜像；对象级 actor projection；仓内语义执行器或自动恢复。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-001`、`REQ-002` 与 [`work-request-compilation`](./work-request-compilation/spec.md) 的 `REQ-001`
- 影响 Story：[`on-demand-content-pool-admission`](./on-demand-content-pool-admission/spec.md) 的 identity-only candidate binding 与发布准入
- 关联验收：[`on-demand-content-pool-admission`](./on-demand-content-pool-admission/spec.md) 的 `GWT-004`

<a id="dec-023"></a>
### DEC-023 invalid canonical 由唯一 repair process manager 按三个证据谓词收敛

- 对象边界：canonical Homepage/Content 与 append-only pool ledger 继续拥有 payload 和版本。`CanonicalIdentityRepair` 是独立 process manager，只拥有 invalid identity 的诊断快照、immutable evidence binding、resolution 与进度，不复制 canonical payload。terminal 是 append-only identity fact，不伪造新 content version。
- 唯一 Query：`CanonicalIdentityStateQuery` 返回互斥的 `absent|admitted_current|invalid_record_repairable|invalid_payload_rebuildable|invalid_unrepairable|terminated`，并携带最深层 error、唯一治理 action 与 optimistic snapshot token。release/publish readback 必须读取同一 query，不得把 `DATA.POOL.PAYLOAD_DIGEST_DRIFT` 改写为 generic not-admitted。
- 三个确定谓词：fresh evidence 证明 current bytes 仍是同一逻辑版本时只能进入 `invalid_record_repairable`。fresh immutable author/review/rights evidence 证明 current bytes 是新 payload 时只能进入 `invalid_payload_rebuildable`。两类 evidence 均不成立时只能进入 `invalid_unrepairable`。缺 evidence 或两类同时成立均 typed blocked，不由调用方猜测。
- 唯一 Command：`ResolveInvalidCanonicalIdentityCommand` 按 query token 只接受对应的 `record_repair|payload_rebuild|terminate`。release/publish query 均无 canonical 写权限。`record_repair` 保持 `contentVersion`、追加 `recordSequence + 1`。`payload_rebuild` 原子写入 `contentVersion + 1` 与 `recordSequence + 1`。`terminate` 保持 `contentVersion`、推进 `recordSequence` 并冻结 terminal reason。
- 消费语义：只有 `admitted_current` 可进入 release cohort。三个 invalid 状态不得因 manifest 存在而静默过滤，也不得进入 semantic dispatch；必须返回唯一治理 action。`terminated` 保持可读治理终态，后续新供给使用新 stable identity；不得建立 scheduler/backlog/自动 recovery 状态。
- 失败恢复与回滚：resolution 只在隔离 staging 构建，payload、ledger append 与 effective-current 切换全有或全无。任一摘要、identity、sequence、query token 或写入冲突保持原 invalid 状态且零半可见版本。完成后的 record/payload/terminal fact 都不倒写，后续纠正只能以新 evidence 启动新 case；terminated identity 不复活，后续供给必须选择新 stable identity。
- 可观察面与 SLO：`actionless_invalid_identity_total` 与 `invalid_identity_semantic_dispatch_total` 必须恒为 0，同 identity effective-current 数只能是 0 或 1，三个读取面的 state/error/action 逐项相等。每个 repair case 全量记录 resolution、duration、evidence digest 与 terminal reason，保留期跟随 canonical 引用保护。
- 可测试面：local_contract 覆盖完整状态转移、三谓词互斥、optimistic conflict、两个版本号规则、terminal 零新版本与三 reader 同源。api_integration 必须先通过真实 canonical application command 创建有效状态，再经 canonical storage adapter 暴露的 test-only fault-injection port 在存储边界制造 payload digest drift；禁止直接写 manifest、ledger 或 fixture seed。随后注入三种互斥 evidence，断言首轮保留原 error 与唯一 command，repair/rebuild 后只有一个 current，terminal 分支零新内容版本且退出 backlog。reliability 在 staging、ledger append、current switch 三个故障点注入失败并断言旧状态不变。
- 被否决方案：manifest-only 判已消费。折叠深层错误。放宽 payload digest。原地覆盖 payload/record。repair/terminate 两套 CLI。用空 backlog或删除文件表达 termination。
- 关联要求：[`canonical-content-identity-recovery`](./canonical-content-identity-recovery/spec.md) 的 `REQ-001` 与 [`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-001`
- 影响 Story：[`canonical-content-identity-recovery`](./canonical-content-identity-recovery/spec.md) 的 canonical 显式治理与 release/publish readback
- 关联验收：[`canonical-content-identity-recovery`](./canonical-content-identity-recovery/spec.md) 的 `GWT-001`

<a id="dec-026"></a>
### DEC-026 approved 对象直接进入 canonical 单对象事务
- 对象边界：只有通过独立 AI review 的对象可进入 canonical admission；publish AI 每次显式提交一个对象 package，single-object transaction 是唯一原子与幂等写单位。不存在 execution 级 batch writer 或发布 process manager。
- 结果单义：transaction 内核只返回可验证的 `applied|replayed|conflict` 硬事实；对象业务 `published|blocked` 与 typed issues 由 AI 在 stage CLOSE 提交。
- exact replay：同一 package 重放不增加 pool record，漂移在写前 conflict；单对象失败不撤销其它对象。
- 可测试面：local_contract 覆盖 review binding、逐对象原子性、replay、失败隔离和 legacy 路径不可达。
- 关联要求：[`on-demand-content-pool-admission`](./on-demand-content-pool-admission/spec.md) 的 `REQ-002`
- 影响 Story：[`on-demand-content-pool-admission`](./on-demand-content-pool-admission/spec.md)
- 关联验收：[`on-demand-content-pool-admission`](./on-demand-content-pool-admission/spec.md) 的 `GWT-005`

<a id="dec-027"></a>
### DEC-027 publish 由 AI 对 approved 对象逐个调用单对象事务
- 决策：`5.review` 独立 AI 对每对象只写一份 `content_review.json`，其中统一给出 `approved|rejected`、简短 dimensions/blockingIssues 与逐资产 rights 结论；publish AI 只对 `approved` 对象逐个准备最终 package 并调用 `DEC-026` canonical single-object transaction。不存在独立 review receipt、镜像 verdict、`publish-execution`、drain/process manager 或 execution 级发布编排。
- 单轨约束：transaction core 只重验对象 package、review/rights/source/media exact facts 并执行原子 IO，不感知宿主、模型或阶段状态。
- 失败语义：单对象失败零半可见，且不撤销其它成功对象；AI 在 CLOSE 中如实提交 typed issues。release 只消费 AI 显式 cohort，禁止 all-publishable。
- 可测试面：local_contract 覆盖逐对象资格、幂等、失败隔离与零 legacy publish reference；api_integration 跑通 approved object 到 canonical。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-007`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-020`

<a id="dec-028"></a>
### DEC-028 execution 内 author/reviewer 单会话，跨 execution 由宿主原生并行
- 决策：一个 execution 的 `4.draft` 全部对象由一个真实 author actor 会话负责，一个 execution 的 `5.review` 全部对象由另一个真实 reviewer actor 会话负责；二者必须是不同 session/runId，可为同一 model family。不同 execution 可由宿主原生并行，仓库不提供 runner、fleet、claim、模型路由、worker queue、actor projection 或自动恢复。
- actor 真相源：`002-4.draft` receipt 的 actor/invocation 就是该 execution 的真实 author，`003-5.review` receipt 的 actor/invocation 就是其真实 reviewer；对象业务产物不复制 actor，代码也不从对象投影、聚合或补写 actor。
- 交接：producer 跨会话只读三份 seal receipts、业务 result refs 与 immutable release handoff。后继由 Skill 固定，代码不得解释 receipt 推进流程；环境 facts 属下游 owner，不参与 producer 恢复。
- 失败恢复：未 seal 的步骤由一个真实 actor 会话完整重做；receipt blocked 新建 execution。任何旧 sequence、checkpoint 或 execution-state projection 均不迁移。
- 可测试面：静态检查锁定零旧控制面与 actor projection，行为测试锁定 author/reviewer actor 不同、各步骤每 execution 单一 actor、create-once receipts 与并发单对象原子 IO。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-006`、`REQ-007`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-020`

<a id="dec-029"></a>
### DEC-029 规模里程碑累计复用 canonical 对象与原始 producer proof
- 决策：M1、M10、M100、M1000 按 `cumulative_unique_finalized_objects` 计数。达到更高级别时可复用已 finalized 的 canonical 对象，以及该对象首次产出时的原 execution、publish transaction 与九阶段 receipt proof；不得为复用对象伪造新 execution 或新九阶段 receipts。
- 每级交付：每个里程碑仍必须形成自己的完整、显式、create-once cohort、immutable release 与 producer handoff，并逐对象绑定原始 producer proof。新级别至少新增足量唯一 finalized 对象使累计值达标，cohort 不得靠重复 identity padding。达标判据是四载体计数不低于该级目标，release header 分别冻结实际 `counts` 与 `milestoneTargets`；`objectRefs` 排序、canonical 字节化与 `expectedCarrierCounts` 派生由 finalize 机械完成，AI 只声明对象集合与 milestone。
- 边界：handoff 只冻结 producer facts；不携带 UAT sample authority、import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback facts。
- 可测试面：同一对象跨相邻里程碑的 canonical identity、原 execution/publish proof refs/digests 保持不变；各级 cohort/release/handoff identity 不同且完整；重复对象不增加累计值。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-008`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-034`

<a id="dec-041"></a>
### DEC-041 默认单一发布消费链、权利只记录、环境差异由配置表达

- 决策：producer 与 Data/Service/App/Ops 消费默认只有一条链，不拥有发布类别、运行类别或命名消费轨道。删除 `releaseClass`、`productLifecycleState` 以及以 `readinessPhase` 为载体的类别选择，连同 CLI 参数、enum、默认值、结果和指纹投影一并去除，不替换成另一常量标签。具体字段闭集由 Data release schemas、Service contracts 与共享 App launch metadata 拥有，按 authoring source → verify/codegen → 实现和测试推进；跨 owner 实现缺口由 [`multi-carrier-release` OPEN-024](./multi-carrier-release/spec.md#open-024) 承接。
- 配置边界：environment/target、endpoint、TLS、Provider、网络与数据隔离、能力探针、观测和 doctor 要求由环境 owner 显式配置并绑定运行配置身份；业务与内容层不按环境名分出另一链路。相同 release 在不同环境保持同一内容身份和媒体字节，配置不反向写入 producer release/cohort/handoff。`apply`、`activate`、`verify`、`rollback` 与 `replay` 是动作及其前驱关系，不是类别；完整 integration/release 验证独立消费显式 Exit，普通 managed/content-live 启动不强制该恢复证据。
- 权利边界：acquire 机械派生逐资产 `rightsStatus`（白名单 license → verified；其它可读 license → unverified 并写 `rightsIssues`；不可读 → unknown）并保留权利六字段；publish 事务与 release build 只把这些取值当作记录事实写入 `rights.json`、pool record 与 header 计数，不据此拒绝对象。对象级词汇（`distributionDecision: research_allowed|commercial_allowed|blocked`、`publicationAdmission`、pool `usageScope`）保持现有取值——它们是已冻结在 canonical 字节中的权利事实，改名等于重写 372 个对象的 `payloadDigest`。
- 媒体交付：release 只物化 canonical 公开媒体引用，导入投影按同一媒体契约声明公开访问。当前非商用开发验证阶段，四入口与媒体直链统一开放，不基于缺少授权记录隐藏或拒绝，不新增运营审批/放行开关；权利计数与精确资产事实原样保留，商用前的可见性治理由 [`multi-carrier-release` OPEN-026](./multi-carrier-release/spec.md#open-026) 承接，不回写 producer。
- 下游边界：release 绑定、active identity、managed preparation 与 preflight 不读写类别，通过现有内容 API 消费，公开内容允许普通 guest 读取；删除按内容类别设立的身份、会话、attestation、readback 与媒体隔离，不设置成功别名或 dual-read。普通 JWT/OTP、原图 view/save 权限与额度、签名授权和环境访问控制继续由原 owner 约束，不通过公开内容验收取消。
- 失败与恢复：旧类别字段或参数不进入现役严格契约；不得通过补值、改摘要或降级投影把已封存旧 release 冒充新契约。需要新候选时由 producer 在保留原对象和 rights bytes 的前提下重新生成 release/handoff。跨 release、环境、activation/verify 或 lease 的身份错绑仍 fail closed，恢复只消费 exact 前驱，不改写既有结果。
- 可测试观察面：local_contract 证明无类别默认调用、真实权利保留、旧选择器与专用路由拒绝、环境配置及缓存身份隔离；api_integration 对同一 active release 的四入口与公开 GET/HEAD/Range 媒体字节读回，覆盖授权记录缺失但不触发开发期隐藏。编译/安装/启动、runtime health 与双端用户可见结果分别形成新证据，旧命名类别测试不代表当前验收。
- 门禁精简：AI 手写面只保留语义字段——init 的 executionId/carrier/familyRef 与逐 target 身份、acquire 的来源申报（`sourceUrl/directUrl/license/licenseUrl/creator/relevance`、水印三字段，可选 `sha1` 与只记录的 `discoverySignals`）、author 的唯一 carrier 产物、review 的 `decision/blockingIssues/advisories`（可选只记录的 `qualityScores/qualityNotes`）、finalize 的 `objectRefs/milestone`。`entityCatalogDigest/candidateCount/status/quota`、canonical 字节化、`assetRights` 逐资产转录、`dimensions`、`objectRefs` 排序与 `expectedCarrierCounts` 全由脚本派生。region、creatorProfileId、homepage 百科主源在 init/author seal 逐对象校验，不留到 publish；author seal 对违规对象只记 typed issue 退轮而不阻断整个 execution，review 覆盖集合以 author seal 的 resultRefs 为准。评分与热度信号只透传不判否（[`multi-carrier-release` REQ-018](./multi-carrier-release/spec.md#req-018)）；里程碑 `cohort.json`/`producer_release_handoff.json` 由 finalize 同步复制到受版本控制的 `quwoquan_data/reference/releases/<releaseId>/`，输出根仍是 `handoff-verify` 的唯一读取位置。
- 输出边界：媒体字节在 execution、object-transaction 包与 release payload 中一律以 content library 硬链接引用，不再产生独立拷贝；图片/视频来源不再落 `snapshot.bin`（摘要已在 `meta.rawSha256`）；随体媒体根（`QWQ_CARRIED_MEDIA_ROOT`，默认仓外 XDG 数据目录 `quwoquan/golden_media`）与 content library 是两处独立的仓外 durable 副本、互为备份、都不进版本库；library 可由 `rehydrate_media_holdings` 从随体根重建，`verify publish-closure` 对 canonical 引用的每个媒体摘要检查两处至少一处可达并在缺失时附 `sourceUrl`。
- 被否决方案：把多类别缩成单一枚举值、把标签改名为 default、在配置中继续选择内容类别、保留成功别名或 dual-read——均未删除类别维度；重写已封存对象级权利词汇——破坏 immutable 对象身份；删除普通认证、原图授权或环境观测——扩大了公开交付裁决。
- 可测试面：local_contract 覆盖 header/cohort/attestation 无类别字段、媒体只产 canonical 公开引用、非 verified 资产可 publish 且 header 计数正确、cohort 计数 ≥ 目标通过而 < 目标 fail closed、seal 机械补齐 assetRights 与 author seal 的三项前移校验、execution 与 release 中媒体 link count > 1。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-002`、`REQ-008`、`REQ-018`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-002`、`GWT-020`、`GWT-034`、`GWT-038`

<a id="dec-031"></a>
### DEC-031 发布媒体公开交付，普通原图授权保持独立

- 决策：release 构建与各域 importer 只按 canonical 媒体契约物化公开引用，不按发布类别或环境名决定媒体形态。内容、Creator 与对象主页投影携带相同 release authority 的稳定资产身份，不能从 URL 或 CAS 存储路径反推业务身份。
- 授权边界：普通原图继续由 OriginalAccessQuota owner 校验 ready image、Post named visibility、已验签身份与 view/save 额度，再调用既有 grant operation。发布内容的公开读取不依赖原图 grant，不建立类别专属身份、扩大授权媒体闭集或新增签发 operation。
- 边缘安全：通用签名交付仍由 `quwoquan_service/runtime/media` 单点拥有验签协议，各环境 adapter 只消费其 verifier 和显式 secret reference。缺签名、篡改、过期或缺失 verifier 均 fail closed；公开 slice 不套用原图授权。验签 p99 附加延迟预算保持不高于 1ms，不引入外部 IO。
- 恢复：App 的通用原图授权复用 [`DEC-033`](#dec-033) 的单飞、稳定身份与单次换签；授权失败不得以公开 fallback 绕过普通原图权限。内容公开媒体失败按原媒体错误语义返回，不创建第二条发布消费链。
- 理由与被否决方案：公开内容与普通原图权限属于不同业务目的；以 release 类别代替资产权限会重建分轨，以统一开放为由删除验签或额度则越过授权边界。
- 可测试面：local_contract 证明公开 release 引用、原图身份/权限/额度与失败边界；api_integration 分别证明公开 GET/HEAD/Range 可读和通用签名 URL 的篡改、到期拒绝，二者证据不互相替代。
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的下游媒体消费。
- 关联要求与验收：[`REQ-002`](./multi-carrier-release/spec.md#req-002)、[`GWT-002`](./multi-carrier-release/spec.md#gwt-002)、[`GWT-032`](./multi-carrier-release/spec.md#gwt-032)。

<a id="dec-032"></a>
### DEC-032 默认内容消费复用普通身份与现有公开 API

- 决策：feed、search、recommendation 与 direct/object route 消费同一 active release，公开内容以普通 guest 身份可读，不要求内容类别专属 role、白名单 session 或身份 attestation。删除专属签发、readback、guard 分支及其路由，不提供成功别名。
- 身份 owner：user-service 继续拥有普通登录、OTP、JWT 与 refresh；operation guard 继续按 canonical security contract 验证账号权限，内容 query 不重新解释签名或发行 session。需要登录的用户操作与普通原图授权不因 guest 内容可读而变成匿名操作。
- 环境与缓存：target、trust、session scope 和网络边界由显式环境配置与已验证身份约束；App 缓存保留 environment/account/persona/sourceOwner/release tuple，切换时清理在途与缓存，不以内容类别或 JWT 专属 audience 新增分区。
- 失败恢复：无 active release 返回 canonical 空态，权限拒绝与依赖 unavailable 保持各自 typed 结果，不伪装成类别不可见或普通空列表；恢复沿原登录、激活与 query owner 执行，不补写事实。公开消费 readback 的 exact release identity、4×4 覆盖与 raw create-once evidence 不弱化。
- 理由与被否决方案：既有公开 API 足以承载内容消费；增加专用 API、通过 header 自选内容权限或仅重命名专属身份都会形成第二链路。统一公开不取消普通认证或环境访问控制。
- 可测试面：local_contract 覆盖 guest 可见、普通登录权限保留、旧路由缺席、跨环境与缓存错绑拒绝；api_integration 证明四入口同一 active identity 且真实 rights 不被抹除。环境事实与设备 UAT 单独产生，不由本地合同推定。
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的默认内容消费。
- 关联要求与验收：[`REQ-002`](./multi-carrier-release/spec.md#req-002)、[`GWT-002`](./multi-carrier-release/spec.md#gwt-002)、[`GWT-016`](./multi-carrier-release/spec.md#gwt-016)。

<a id="dec-033"></a>
### DEC-033 App 私有媒体消费收敛为 typed 交付绑定加单一异步 grant 协调器

- 决策：App 对私有媒体的全部消费行为由一条统一边界承载，页面与设计系统组件不各自实现——
  - 交付形态显式声明：`quwoquan_service/contracts/metadata/_shared/types.yaml` 新增共享 enum `MediaDeliveryAccessMode`（`public`、`signed_grant`），content post、user persona/creator、entity homepage 三路 App 可见投影为每条媒体引用携带 `accessMode` 与 release authority 的资产标识。App 依 typed 声明分流，禁止从 CAS 前缀、URL 形态或 query 参数推断交付形态——服务端存储布局不进入 App 认知面。
  - 资产标识契约补齐：feed 投影为逐条媒体（含逐图、video 主媒体与 poster）与作者头像携带资产标识；`PersonaProfileView` 补 `avatarAssetId`；`HomepageIntroduction` 的 cover 补配对资产标识；detail 投影既有 `mediaAssetIds` 与 `mediaItems` 必须被 App 映射保留而非丢弃。禁止以 `postId`、`personaId` 等对象标识冒充媒体资产标识，view mapper 收敛为单一实现。
  - 双 resolver 边界：既有 `MediaDeliveryResolver` 保持纯同步 public-slice 解析并继续拒绝 CAS 与签名 query；`accessMode=signed_grant` 的引用交由新增的异步私有媒体交付协调器（application 层 typed port）处理——按资产标识调用既有 `ReserveOriginalImageAccessGrant` 客户端，校验响应 `mediaId` 与请求资产标识一致、URL 属注入媒体 origin、签名 query 完整、到期时间与响应 TTL 一致后输出已验证交付引用。签名 URL 不经过 public resolver 与 CDN 变体处理器。
  - 缓存与在途身份：图片解码缓存、磁盘缓存、视频下载缓存、在途合并与负缓存统一使用稳定资产身份（媒体类别、资产标识、版本、variant），签名 query 不参与任何缓存键；签名 URL 只存在于短期 provider 状态，不写回业务 DTO、持久缓存文档或遥测。
  - 失败恢复单义：grant 在到期安全窗内先换签再交给网络层；签名字节 GET 首次 401/403 只失效当前资产的当前 grant、重新换取一次并重试一次，再失败即呈现 canonical 失败态停止，禁止循环；404 才进入稳定资产负缓存；登出、persona 切换与 active release 切换时清空 grant 缓存。同一资产并发请求单飞，未过期 grant 复用。
  - surface 接入：feed 卡片、文章正文与封面、图片与视频沉浸页、各头像 surface、对象主页 hero 与 introduction assets 全部只向统一图片/视频原子传 typed 交付绑定；grant 调用、校验、缓存、刷新与失败恢复只存在于协调器一处。既有「查看原图」手动动作同样委托该协调器，不保留第二套 grant 缓存。
  - 观测面：私有媒体消费的最小 SLI 为 grant 换取延迟（沿用 operation 契约 `latency_p95_ms=800` 预算）、grant cache 命中率（稳态目标 ≥ 80%，单飞与未过期复用生效的机械结果）与 `original_access_rate_limited` 计数（稳态应为 0，非零即触发 policy owner calibration 复核）；三者全部由既有 `content_media_original_access_request` 指标与 audit 事实派生，不新增指标或可写台账。
- 理由：私有媒体的授权、时效与缓存语义与公开 slice 结构不同，放宽同步 public resolver 会把「未授权私有引用」与「已授权交付 URL」混为一种状态，且签名 `t`（到期秒）与既有视频帧 `t`（毫秒）语义冲突。资产标识是业务身份、CAS key 是字节身份，多资产可共享同一字节，从路径反推标识不成立，标识必须随 canonical 投影下发。签名随 TTL 轮换，以完整 URL 为缓存键会造成解码缓存失效、磁盘重复下载与在途不合并的缓存风暴。
- 被否决方案：放宽 `MediaDeliveryResolver` 接受 CAS 与签名 query——混淆授权状态并引入 query 语义冲突。App 判断 CAS 前缀——成为 Go、Python、边缘配置之后的第四份路径字面量。从 CAS 路径反推资产标识、以对象标识冒充资产标识、维护本地路径到标识的字典——字节身份与业务身份混淆。逐页面接入 grant——生命周期语义散布成多份实现。签名 URL 作缓存键并配缓存失效补偿——治理成本高于稳定身份。
- 可测试面：App local_contract 按消费边界覆盖——
  - public resolver 继续拒绝 CAS 与签名 URL。
  - 协调器对空资产标识、响应标识漂移、错误 origin、缺签名与已过期 grant 均 fail closed。
  - 同资产并发只发起一次换取、安全窗内复用、到期先换签，首次 401/403 单次换签重试且二次失败停止。
  - 不同签名同资产命中同一缓存键，不同资产或版本不碰撞。
  - feed、detail、头像、主页投影的资产标识与 accessMode 在场断言，以及上述各 surface 的 Widget 消费断言。
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 App 消费面（OPEN-015）
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-016`、`GWT-020.t3`

<a id="dec-034"></a>
### DEC-034 环境证据按显式配置与当前身份消费

- 决策：内容链不创建类别专属隔离 proof、签发器或验收相位。环境安全、网络隔离、内容/媒体探针、观测和 doctor 由各自现役 owner 按显式环境配置执行；readiness 与环境资格只消费这些 owner 的 exact evidence，不在 producer 加第二套证明流程。
- 一致性与恢复：结果绑定实际 target、release、runtime/config identity 与 canonical evidence refs；原始结果保持 create-once。缺失、过期或身份漂移保留 typed blocker，不能补值、改写旧证明或由最近一次通过替代当前 required evidence。复用资格与时效只由原证据 owner 契约决定。
- 理由与被否决方案：删除类别不等于删除必要观测；把环境检查换成一个固定内容标签、复制旧隔离证明或把所有环境要求一律删掉，都不能证明当前环境状态。
- 可测试面：local_contract 覆盖同配置证据绑定、跨 target/release/config 错绑拒绝及旧专属证明缺席；api_integration 覆盖实际环境探针与 readback。完整 EAF named closure 仍独立校验。
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的下游环境证据。
- 关联要求与验收：[`REQ-002`](./multi-carrier-release/spec.md#req-002)、[`GWT-002`](./multi-carrier-release/spec.md#gwt-002)、[`GWT-030`](./multi-carrier-release/spec.md#gwt-030)。

<a id="dec-040"></a>
### DEC-040 typed 媒体契约与有界播放恢复不依赖类别

- 交付契约：媒体投影按现役 canonical contract 显式携带访问模式与稳定资产标识，缺失即 typed blocked，不从 URL、CAS key、环境名或缺席推断。默认 release 只公开交付；通用受权媒体能力不是另一 release 类别，不得作为内容公开读取的前置。
- progressive MP4：App 私有视频原子只接收已校验短签交付引用，原生播放器发起 Range。edge verifier 对每个 Range 请求重新验签。首次 401/403 使当前 grant 失效，协调器强制换签最多一次，并以播放器已确认 position 恢复。二次失败进入 canonical typed terminal，禁止循环或 public fallback。
- private HLS：当前 contract 明确返回 unsupported typed terminal，manifest/segment/key 不进入 progressive MP4 fallback。HLS 的分片授权、key authority、TTL 恢复与播放器状态属于独立能力，由 [`multi-carrier-release` OPEN-017](./multi-carrier-release/spec.md#open-017) 关闭；它不阻断 progressive MP4 的 fresh UAT，也不能靠放宽 `accessMode` 绕过。
- 失败恢复与观测：Range 验签失败、换签次数、恢复前后 position 与 terminal code 由现有 grant/audit 和播放器 raw `ReadinessCaseResult` 派生，不新增播放 ledger。位置恢复允许播放器容器的受治理 seek tolerance，但 identity、asset、release 与换签上限必须精确；tolerance 数值归播放器 runtime contract owner，不在本设计复制。
- 理由：progressive MP4 是单媒体 URL 加 Range 的授权模型，现有 grant 与 edge verifier足够闭合；HLS 需要 manifest、segment、key 多资源授权，复用单 URL 假设会在分片处 fail open。把已实现 MP4 与未设计 HLS 放在同一个 OPEN 会错误地把 fresh UAT 缺口表述为实现缺口。
- 被否决方案：401/403 无限换签、换签后从零播放、回退 public URL、缺 `accessMode` 默认 public、private HLS 降级 progressive MP4、为每个 Range 向 App 暴露独立 grant command。
- 可测试面：`local_contract`（`spec_ref=GWT-032`）覆盖显式交付绑定、普通授权能力下的单次换签和 HLS unsupported。`api_integration` 对真实 edge 执行 Range 与 401/403 恢复。`user_acceptance` 以 progressive private MP4 产生 fresh raw `ReadinessCaseResult` 并证明位置保持。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-016`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的媒体契约与有界恢复面
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-032`，开放项为 [`OPEN-015`](./multi-carrier-release/spec.md#open-015) 与 [`OPEN-017`](./multi-carrier-release/spec.md#open-017)

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 后续动作由调用方显式选择；失败对象本身只保留 code/message/ref/origin 诊断。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。
- 宿主中断：会话预算耗尽只停止宿主继续操作；Data 不写 deadline/job terminal。已 OPEN 未 CLOSE 的阶段由新会话按同一冻结输入重做，既有 create-once receipt 与已合格对象不受影响。
- 重入路径：OPEN 无 CLOSE 时重做同一 stage；CLOSE blocked 后只能以新 `executionId + retryOf` 消费显式业务 refs。

## 6. 质量与观测

- 记录 operation、终态、延迟与 canonical error；特有阈值由 spec 和运行配置约束。
- 宿主可在仓外记录会话数、并行重叠、elapsed 与成本等诊断；这些诊断不进入 Data receipt、准入、publish、milestone 或下一次 execution authority。
- Data 只保留逐 target source result、三份 seal receipts 与业务 result refs；不生成宿主调度、容量、heartbeat、截止或自动 calibration 报告。
