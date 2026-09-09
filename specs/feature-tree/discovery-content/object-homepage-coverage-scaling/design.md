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
- 边界：producer 代码仅做 `task init`、`task acquire`（零网络 ingest 宿主已取得的字节与申报来源，派生摘要/probe/poster）、`task seal`（自行校验硬事实并 create-once 写三份 receipt，review seal 补齐 content_review 机械字段）、单对象 publish 与 `release finalize`。来源是否切题、选材、创作、review 判断、verdict、typed issues、approved 对象、cohort/milestone、文章结构与作者人设均由宿主 AI 显式决定；后继只来自 Skill 固定顺序。既有 ship I/O 属下游环境 owner，不是 producer stage。
- 失败恢复：按 receipt 找首个未闭合步骤继续；receipt blocked 后新建 execution，不在原 execution rewind 或迁移旧状态。
- 可测试面：local_contract 锁定零旧 import/CLI/schema/reference、seal receipt create-once、AI 显式结果与单对象原子 IO；api_integration 证明四载体可由宿主直接执行。
- Skill 工具边界：按 `carriers/<carrier>/` 聚合来源、选择 schema、加工规则与普通函数 adapter；共享入口只加载点名载体，来源网络限于 Skill，Data ingest/seal 保持零来源网络。工具只展开显式输入，不封装阶段推进或恢复；工作区按 shard/round/carrier 隔离，任务 execution/receipts 的既有根不迁移；canonical 内容仓独立定位按 `DEC-042`。
- 多源投影：image 以有序原生作品资产为单位，逐图 caption 只写入既有资产字段；重名目标文件按来源身份确定性消歧。homepage 的显式主源属于 author 输入，seal 校验本对象百科成员关系，catalog、实体头与归属共用选择，不依赖 source unit 排序。未声明的新可选字段不改变旧已发布对象读取含义。
- 回滚与观测：失败以当前阶段 typed 结果报告，宿主决定后继；不回写旧 receipt/pool，回退源码不迁移既有对象。来源失败与预览绑定通过离线 fixture 观察，运行审计在 execution 存续期间可回查，不建立新的 handoff actor authority。
- 关联要求：`REQ-001`、`REQ-003`、`REQ-017`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：`GWT-020`、`GWT-039`

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
### DEC-023 canonical 显式清单迁移或退役，完整校验后原子硬切

- 对象边界：canonical 对象与 pool record 拥有身份、版本和 payload；现有身份 query、有限 record supersession 与对象事务原语继续复用。不建立 repair process manager、长期 case 队列或九阶段 recovery，也不宣称已有完整 Homepage 修复 CLI。
- 只读判定：`CanonicalIdentityStateQuery` 与 pool query 区分身份不存在、当前有效及存在但无效，保留最深层 typed error、exact objectRef、依赖与当前摘要；不得把 invalid 静默当作已完成或可重新创建。
- 一次性输入：受治理 cutover 只接受覆盖全部活跃对象的精确清单，绑定 before identity/digest、依赖 refs、证据、迁移或删除动作与 after 预期。缺证据、重复身份、漏对象、依赖未决或同时选择互斥动作均阻断；清单不是新生产队列。
- 迁移：证据充分才保留逻辑身份及资产顺序，受测契约转换产生新版本与新摘要；原始作者、许可、来源及 review 事实不被补造。payload drift 与权利记录无效须分别验证实际证据，不能只刷新摘要或填写 passed。普通 publisher 不接受旧 schema 或特殊覆盖参数。
- 退役：不能证明有效的对象及无法修复的依赖经精确删除授权后退出活跃树；终态写入受保护迁移证据，不靠 excluded 或 OPEN 永久保留旧运行对象。删除对象不意味着删除被任一新池、保留 release 或审计引用的媒体。
- 原子性：在既有 staging/delta/锁/校验边界构造并验证完整新池，再以 expected-before 摘要 CAS 激活。阶段失败或并发写入保持旧状态，禁止部分可见树、整池 reset 和旁路 legacy 池；切换完成后旧树退出活跃路径并按精确保护集清理。
- 历史与运行隔离：旧 Git、receipt、release、rollback 与环境绑定保护集保持原字节；新 reader 不接受旧 release 作为激活输入。历史复核按原提交或制品离线运行，迁移专用旧解析器不进入普通 reader，完成后撤下；不保留在线双读双写。
- 验收：真实对象事务构造输入，经存储边界 fault injection 制造 drift，验证全对象清单闭包、证据不足拒绝、版本/身份/媒体保护、并发 CAS 和 staging/current-switch 故障恢复。输出逐对象结果与 before/after 摘要，不以改计数或重算旧证据冒充成功。
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
- 决策：M1、M10、M100、M1000 按 `cumulative_unique_finalized_objects` 计数。达到更高级别时可复用已 finalized 的 canonical 对象，以及该对象首次产出时的原 execution、publish transaction 与三份 seal receipt proof；不得为复用对象伪造新 execution 或新 receipts。
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
- 权利边界：acquire 机械派生逐资产 `rightsStatus`（白名单 license → verified；其它可读 license → unverified 并写 `rightsIssues`；不可读 → unknown）并保留权利六字段；publish 事务与 release build 只把这些取值当作记录事实写入唯一 manifest 与包内 `sources/<unit>/source.json`，header 只派生计数，pool record 只绑定包与 review 摘要，不复制完整权利投影，不据此拒绝对象。对象级词汇（`distributionDecision: research_allowed|commercial_allowed|blocked`、`publicationAdmission`、pool `usageScope`）保持现有取值；删除类别不授权改名、刷新既有 `payloadDigest` 或重写旧对象身份。包格式转换按 `DEC-023` 生成新版本与摘要，原权利值及原 review 保留，不能以转换伪造重审。
- 媒体交付：release 只物化 canonical 公开媒体引用，导入投影按同一媒体契约声明公开访问。当前非商用开发验证阶段，四入口与媒体直链统一开放，不基于缺少授权记录隐藏或拒绝，不新增运营审批/放行开关；权利计数与精确资产事实原样保留，商用前的可见性治理由 [`multi-carrier-release` OPEN-026](./multi-carrier-release/spec.md#open-026) 承接，不回写 producer。
- 下游边界：release 绑定、active identity、managed preparation 与 preflight 不读写类别，通过现有内容 API 消费，公开内容允许普通 guest 读取；删除按内容类别设立的身份、会话、attestation、readback 与媒体隔离，不设置成功别名或 dual-read。普通 JWT/OTP、原图 view/save 权限与额度、签名授权和环境访问控制继续由原 owner 约束，不通过公开内容验收取消。
- 失败与恢复：旧类别字段或参数不进入现役严格契约；不得通过补值、改摘要或降级投影把已封存旧 release 冒充新契约。需要新候选时由 producer 在保留原对象和 rights bytes 的前提下重新生成 release/handoff。跨 release、环境、activation/verify 或 lease 的身份错绑仍 fail closed，恢复只消费 exact 前驱，不改写既有结果。
- 可测试观察面：local_contract 证明无类别默认调用、真实权利保留、旧选择器与专用路由拒绝、环境配置及缓存身份隔离；api_integration 对同一 active release 的四入口与公开 GET/HEAD/Range 媒体字节读回，覆盖授权记录缺失但不触发开发期隐藏。编译/安装/启动、runtime health 与双端用户可见结果分别形成新证据，旧命名类别测试不代表当前验收。
- 门禁精简：AI 手写面只保留语义字段——init 的 executionId/carrier/familyRef 与逐 target 身份、acquire 的来源申报（`sourceUrl/directUrl/license/licenseUrl/creator/relevance`、水印三字段，可选 `sha1` 与只记录的 `discoverySignals`）、author 的唯一 carrier 产物、review 的 `decision/blockingIssues/advisories`（可选只记录的 `qualityScores/qualityNotes`）、finalize 的 `objectRefs/milestone`。`entityCatalogDigest/candidateCount/status/quota`、canonical 字节化、`assetRights` 逐资产转录、`dimensions`、`objectRefs` 排序与 `expectedCarrierCounts` 全由脚本派生。region、creatorProfileId、homepage 百科主源在 init/author seal 逐对象校验，不留到 publish；author seal 对违规对象只记 typed issue 退轮而不阻断整个 execution，review 覆盖集合以 author seal 的 resultRefs 为准。评分与热度信号只透传不判否（[`multi-carrier-release` REQ-018](./multi-carrier-release/spec.md#req-018)）；里程碑两份 terminal 事实由 finalize create-or-same 保存到独立内容仓，绑定实际快照且只读验证，遵循 `DEC-042`，历史副本保持原字节。
- 输出边界：content library 用于 acquisition 复用；最终对象包持有实际交付媒体，完整复制不依赖 library，独立 golden media 保护副本继续保留。硬链接只是复用优化，不证明独立备份；同卷完整副本不证明抗卷损坏，缺异卷/远端恢复证据时如实未建立。来源只携带真实必要证据，生成式 snapshot 不冒充第三方证明；verify/consumer 均只读，对包内缺失字节 fail closed，恢复必须显式执行，不隐式回填库或借其它 holder 代偿。包与耐久性分别遵循 `DEC-044` 和 L2 `REQ-003`。
- 被否决方案：把多类别缩成单一枚举值、把标签改名为 default、在配置中继续选择内容类别、保留成功别名或 dual-read——均未删除类别维度；重写已封存对象级权利词汇——破坏 immutable 对象身份；删除普通认证、原图授权或环境观测——扩大了公开交付裁决。
- 可测试面：local_contract 覆盖 header/cohort/attestation 无类别字段、媒体只产 canonical 公开引用、非 verified 资产可 publish 且 header 计数正确、cohort 计数 ≥ 目标通过而 < 目标 fail closed、seal 机械补齐 assetRights 与 author seal 的三项前移校验、完整包脱离 execution/library 可校验、媒体/来源缺失与摘要漂移分别拒绝；hardlink 优化不作为耐久性判据。
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

<a id="dec-044"></a>
### DEC-044 Data 媒体交付只读取单一 manifest

- 决策：按 [`DEC-041`](#dec-041) 无类别默认公开交付；importer、媒体同步和 query 读取统一 manifest 的稳定资产身份、摘要、顺序与 caption，不读冗余资产旁车或旧私有交付字段。
- 对象包：manifest 单写对象身份、版本、标题/caption、实体事实、正文引用、creator/tag/entity 依赖及有序媒体，实体头并入 manifest。homepage/article 只另存最终正文，image/video 无伪正文/脚本草稿；final media 的相对引用与 exact 字节随体，完整复制不依赖 execution/library，不跨包 symlink。creator 仍是共享业务主体，独立 profile/avatar 不强行同构。
- 来源与审计：采用来源的事实由包内 `sources/<unit>/source.json` 单写，必要证据在该 sources 单元局部拥有，不建全球 resolver；跨作品允许少量来源元数据复制。删除 `asset.refs.json`、`creator.refs.json`、`tag.refs.json`、`source_catalog.json`、`rights.json` 与生成式 `rights_snapshots` 的重复投影，真正的第三方原件进入 sources 并保持可追溯，生成 manifest 副本不算授权证据。公共 attribution 从唯一 manifest/source 派生。
- review/record：独立 reviewer 原结论与原审核对象摘要保持原件，迁移追加 binding 而非伪造重审；现有追加式入池/退役事实收敛到 records，只绑定包/review 摘要而不复制完整 manifest/source。审核与入池是不同事实，不能删其一。旧字节转换只经 `DEC-023`，普通 reader 不接受旧旁车兜底。
- 理由与被否决方案：减少的是重复 authority 而不是真实证据；否决继续三旁车之外再留一套 source/rights 镜像、无媒体的不可独立包、按文件数删除 review/record、由 consumer 缓存回写 canonical。
- 失败恢复与观测：原子包事务报告 exact 引用的来源缺失、媒体缺失、摘要漂移或越界；失败不产生部分成功包，不改已通过 review/历史 release。显式恢复在隔离目标从独立副本验摘要，verify 不产生写入；实际恢复/备份证据与源码测试分层。
- 边界：Data 不再绑定专用身份、短签或隔离探针；共享媒体签名、到期及 Range 验签仍由原 owner 维护，不因删除 Data 路径放宽无关业务权限。旧 release 仅作隔离历史审计，不接受在线兼容激活。
- 可测试面：现有单对象事务/闭包测试完整复制四载体包到无原 execution/library 的目录，验证媒体、来源、review binding 与 records；Service importer/Ops materialize 验单源与 exact 摘要，旧交付反例和共享授权负例仍拒绝。普通 publish 只对本包重验，不为每次发布全池重算媒体摘要。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-009`、`REQ-020`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：`GWT-022`、`GWT-043`、`GWT-044`、`GWT-041`；未完成由 `OPEN-025` 跟踪


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

- 决策：内容链不创建类别专属隔离 proof、签发器或验收相位。环境安全、网络隔离、内容/媒体探针、观测和 doctor 由各自现役 owner 按显式环境配置执行；readiness 与环境资格只消费这些 owner 的 exact evidence，不在 producer 加第二套证明流程。旧专属隔离证明的生成、复用与探针入口退出当前输入，旧证明只保留原字节历史审计，不重绑为当前成功；退役与新消费证据由 [`OPEN-024`](./multi-carrier-release/spec.md#open-024) 承接。
- 一致性与恢复：结果绑定实际 target、release、runtime/config identity 与 canonical evidence refs；原始结果保持 create-once。缺失、过期或身份漂移保留 typed blocker，不能补值、改写旧证明或由最近一次通过替代当前 required evidence。复用资格与时效只由原证据 owner 契约决定。
- 理由与被否决方案：删除类别不等于删除必要观测；把环境检查换成一个固定内容标签、复制旧隔离证明或把所有环境要求一律删掉，都不能证明当前环境状态。
- 可测试面：local_contract 覆盖同配置证据绑定、跨 target/release/config 错绑拒绝及旧专属证明缺席；api_integration 覆盖实际环境探针与 readback。完整 EAF named closure 仍独立校验。
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的下游环境证据。
- 关联要求与验收：[`REQ-002`](./multi-carrier-release/spec.md#req-002)、[`GWT-002`](./multi-carrier-release/spec.md#gwt-002)、[`GWT-030`](./multi-carrier-release/spec.md#gwt-030)。

<a id="dec-040"></a>
### DEC-040 typed 媒体契约与有界播放恢复不依赖类别

- 交付契约：媒体投影按现役 canonical contract 显式携带访问模式与稳定资产标识，缺失即 typed blocked，不从 URL、CAS key、环境名或缺席推断。默认 release 只公开交付；通用受权媒体能力不是另一 release 类别，不得作为内容公开读取的前置。Data 旧版本缺字段适配与专属私有视频路径退役；稳定资产身份、poster、顺序与逐图 caption 从唯一 manifest 到 App 保持同义，caption 不取代作品 title。
- 消费证据：本地 decoder/importer 测试只证明字段映射；公开视频 Range 播放、图集切换与逐图说明由授权环境和真实 App 另行验证，不拿 poster、源端 PASS 或旧私有媒体 UAT 替代，按 [`GWT-043`](./multi-carrier-release/spec.md#gwt-043) 验收并由 [`OPEN-015`](./multi-carrier-release/spec.md#open-015) 承接缺口。
- progressive MP4：App 私有视频原子只接收已校验短签交付引用，原生播放器发起 Range。edge verifier 对每个 Range 请求重新验签。首次 401/403 使当前 grant 失效，协调器强制换签最多一次，并以播放器已确认 position 恢复。二次失败进入 canonical typed terminal，禁止循环或 public fallback。
- private HLS：当前 contract 明确返回 unsupported typed terminal，manifest/segment/key 不进入 progressive MP4 fallback。HLS 的分片授权、key authority、TTL 恢复与播放器状态属于独立能力，由 [`multi-carrier-release` OPEN-017](./multi-carrier-release/spec.md#open-017) 关闭；它不阻断 progressive MP4 的 fresh UAT，也不能靠放宽 `accessMode` 绕过。
- 失败恢复与观测：Range 验签失败、换签次数、恢复前后 position 与 terminal code 由现有 grant/audit 和播放器 raw `ReadinessCaseResult` 派生，不新增播放 ledger。位置恢复允许播放器容器的受治理 seek tolerance，但 identity、asset、release 与换签上限必须精确；tolerance 数值归播放器 runtime contract owner，不在本设计复制。
- 理由：progressive MP4 是单媒体 URL 加 Range 的授权模型，现有 grant 与 edge verifier足够闭合；HLS 需要 manifest、segment、key 多资源授权，复用单 URL 假设会在分片处 fail open。把已实现 MP4 与未设计 HLS 放在同一个 OPEN 会错误地把 fresh UAT 缺口表述为实现缺口。
- 被否决方案：401/403 无限换签、换签后从零播放、回退 public URL、缺 `accessMode` 默认 public、private HLS 降级 progressive MP4、为每个 Range 向 App 暴露独立 grant command。
- 可测试面：`local_contract`（`spec_ref=GWT-032`）覆盖显式交付绑定、普通授权能力下的单次换签和 HLS unsupported。`api_integration` 对真实 edge 执行 Range 与 401/403 恢复。`user_acceptance` 以 progressive private MP4 产生 fresh raw `ReadinessCaseResult` 并证明位置保持。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-016`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的媒体契约与有界恢复面
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-032`，开放项为 [`OPEN-015`](./multi-carrier-release/spec.md#open-015) 与 [`OPEN-017`](./multi-carrier-release/spec.md#open-017)

<a id="dec-042"></a>
### DEC-042 独立内容仓拥有物理定位，身份与包摘要不随目录变化

- 决策与 owner：canonical 内容在源码工作树平级独立 Git 仓，由仓身份/布局版本/实际工程契约摘要绑定；仓不是源码 worktree、submodule 或 symlink。Data owns 包/locator/记录，Service 只从 manifest 读取稳定身份，Ops 只物化 exact release。源码 worktree discovery 按 repository 身份区分，不使用目录名忽略规则。
- 目录：地域实体在自身领域下依已核实行政链、已有主类型、分区、名称、组内条目管理；posts 按 carrier、主分类、分区、名称、组内条目管理。具体路径语法与容量阈值唯一归 Data schema/policy。行政链可缺区县、可为直辖市/省直管县/境外真实层级；主归属只有一个，其他地域保留 ref。地域适用性显式，当前不实现非地点 producer。
- 分配：非空类始终从首分区开始，只用条目数与随体逻辑字节两个指标。已有同名组原地追加、不拆组；新组在容量允许者中取最低归一化负载，平分按编号，无合适者才开新分区。超大组只报告例外，无跨地域均衡、后台重分区、第三种统计阈值或 per-partition authority；inventory 可重建。
- 身份：逻辑 entityRef/实体 ID/作品 ID 在 init 冻结，目录末级数字只表示组内条目、允许空洞且不复用，不猜版本。名称/地域/类型整理属于显式 locator 变更；包内摘要不含外层 locator，release 定位清单包含 locator。同物新版本沿用身份并递增内容版本，新包字节不可借纯移动刷新旧审核证据。
- 并发与原子性：共同内容根的锁定位不依赖各源码 OUTPUT_ROOT；单对象临时包验证后原子可见，publish、整组整理与内容 Git ref 更新共享串行边界。缺根、错仓、名称/路径冲突 typed 阻断；只枚举声明对象根，Git、repository metadata 与 releases 不计入 inventory。execution/receipts 物理根不随 publish 重构变化。
- handoff：继续仅有 cohort/handoff 两份 terminal 事实，create-or-same 保存到内容仓，绑定工程 baseline/契约摘要与所选 ID/版本/包摘要/定位的 exact 内容快照。内容 commit 只有与字节匹配才记录；不增加必须先后提交两次的仪式。重建须保存固定时间和 exact build 输入，历史 bundle 不清理为试验对象。
- 理由与被否决方案：地域便于人工管理，但存储位置不应决定业务身份。否决路径哈希/按名取首项、日期轮次树、跨包媒体借用、分区 mapping authority、自动 rebalance、错误根 fallback、源码提交冒充内容快照。
- 失败恢复/回滚：沿用 `DEC-023` 的全量 before、独立备份、保护集与 expected-before staging；不交换包含 Git 的仓根。准备不授予搬迁/删除/init/clone/commit/push/环境激活权限，各动作分别确认；失败保持原对象与审计，不声称一个 lane 配置已切全局。
- 观测与可测试面：现有 DataRoot/inventory/object-transaction 短 local_contract 验真实行政链/Unicode/分区边界与跨 worktree 共锁；身份与 importer 测试验 ref/ID/主页 ID 守恒。仅输出该事务容量例外、首个 typed blocker、before/after 摘要，无新健康服务或全池日常重哈希。
- 关联要求：L2 `REQ-004`；[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-008`、`REQ-019`；[`canonical-content-identity-recovery`](./canonical-content-identity-recovery/spec.md) 的 `REQ-002`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)、[`canonical-content-identity-recovery`](./canonical-content-identity-recovery/spec.md)
- 关联验收：前者 `GWT-040`、`GWT-041`，后者 `GWT-002`、`GWT-003`；准出缺口由各 Story OPEN 承接。

<a id="dec-043"></a>
### DEC-043 发布闭包严格，运行实体引用与媒体失败局部降级

- 决策与 owner：producer 在 exact release 构建检查显式内部 ref，运行正文使用名称快照，用户点击才调用既有目标详情 API。Entity owns 可见性/权限，Content importer 复用既有 exact 主页映射，App 复用错误展示与媒体缓存；不扩展 runtime 的 active pointer fence 或添加跨服务强一致协议。
- 实体引用：文章 mention 从同一 Entity 映射生成而不是新增 hp 哈希公式，映射缺失呈普通文字；同名异地不得串跳。非文章保持可读 label/结构化关联，不新增通用富文本、引用卡片或 article-only GraphQL 扩展。内部语法不得泄露物理路径；没有系统实体的外部名称不捏造 ref。
- 运行一致性：普通实体下线不级联下线作品、删原文、借用媒体或改历史 release；已知不可用可隐藏链接，不知道时不为去链接额外 query。点击后服从原 403/404/410 或 Data 历史 offline View 的公开契约并允许返回，弱一致不绕过权限。严重治理删除仍走原命令，不成为地点下线副作用。
- 媒体：包内资产相对引用在 release 物化为摘要交付键，环境 URL 经既有 endpoint/resolver 生成；实际上传摘要及 Range/MIME/readback 先于激活。正文/封面坏图局部占位，图集保留坏页位置仍可滑动，视频有界失败保留 poster/caption，poster/字幕失败不阻断可用视频，源站失效不影响随体成品。
- 缓存与恢复：只修既有图集实际 provider 接负缓存、视频 cache hit 不续 TTL/不重复启动恢复；网络新失败、成功与用户显式重试仍按原 owner 处理。已知永久缺失不自动重试。无逐实体请求、逐媒体 HEAD、引用状态 TTL、缓存广播、后台修复或周期巡检。
- 理由与被否决方案：关联是导航增强而非正文可用性依赖，媒体故障不应清空作品；否决实体下线反向遍历全池/级联重写、补充健康注册表、用无效链接伪装可导航、以 importer 单测冒充真实 UAT。
- 可测试面与观测：真实 Entity→Content importer→typed query 证明 mention 映射；App 现有错误/图集/视频短 local_contract 验单图失败可翻页、缓存跨实例复用及原 TTL 不延长。每屏请求数不随引用数线性增加，重试受原预算限制；授权环境再验证实体下线返回和视频 Range。失败只报原 typed 局部结果，不新增 SLO/报警体系。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-021`、L2 `REQ-004`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)，Runtime/Service/App 消费边界只引用原 owner contracts。
- 关联验收：`GWT-042`，缺口保留在 `OPEN-028`，不进入 producer END。

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
