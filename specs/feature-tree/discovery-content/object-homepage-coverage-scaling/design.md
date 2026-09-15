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
- 语义主体：来源选择与相关性、创作、结构、作者人设与 review 的唯一主体是直接执行 Skill 的宿主 Cursor/Codex Agent。仓内只做 deterministic init、acquire、seal、原子 publish 与 release finalize；不得新增 resolver、projector、runner、controller、queue、语义调度或业务完成 registry、SDK、自动恢复或 actor projection。`DEC-046` 允许的最小 SQLite 只保存具名 shard 占用与预算预留硬事实。
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
- 一次性输入：受治理 cutover 只接受覆盖全部活跃对象的精确清单，绑定 before identity/digest、依赖 refs、证据、转换或归档动作与 after 预期。转换缺证据、重复身份、漏对象、依赖未决或同时选择互斥动作均阻断；清单不是新生产队列。
- 迁移：证据充分才保留逻辑身份及资产顺序，受测契约转换产生新版本与新摘要；原始作者、许可、来源及 review 事实不被补造。payload drift 与权利记录无效须分别验证实际证据，不能只刷新摘要或填写 passed。普通 publisher 不接受旧 schema 或特殊覆盖参数。
- 单对象事实修正：复用 `release object-transaction` 治理入口与现有 package 的 `inputPayloadDigest`，绑定 fresh execution、target、expected version/payload、reason 与本次来源/成品输入，不建立授权 token 或第二台账；授权由宿主点名确认。builder 内部版本默认 1，治理只传 expected + 1，普通 publish CLI 不接收覆盖/版本参数。新 execution 重新 acquire/author/独立 review，不用 passed execution 的 retryOf，也不改旧 source/review。
- 修正一致性：共同内容仓写锁覆盖 before 实际摘要/版本、身份守恒、新审核校验、locator 分配及既有 audit/apply。新包与 record 在 staging 一次生成，新增版本而不重写旧树；任一前置漂移零 pool 写。exact replay 同时复验原输入绑定、包/record/review 与当前新版本，不能只看旧 apply receipt。失败沿既有事务证据显式处理，不自动修复；命名 local_contract 以真实对象 fixture 验证 `canonical-content-identity-recovery` 的 `REQ-002/GWT-004`，运行指标为新版本/ref/摘要与 idempotent 结果，实际运营与下游证据另取。
- 归档与资格：不能验证的对象及未闭合依赖只归档，不进入新合格池；不得以目标数量补造资格或把归档当作重审通过。归档原件与被任一保留作品、release、review 或审计引用的媒体继续受保护。
- 原子性：替换仍在运行的旧根时，在既有 staging/delta/锁/校验边界验证完整新池，以 expected-before CAS 切换；失败保持旧状态。旧根已退出运行且正式独立仓已有成品时，转换后的完整新包按显式清单先依赖后引用，复用单对象 audit/apply（或受测包重放入口）顺序新增；每包原子可见，错误包不写入，已成功包不撤销。宿主依原回执恢复，不建批次事务或全批回滚系统，不另作对象激活。禁止整池 reset、交换含 Git 的仓根或旁路 legacy 池；新包、引用闭包及保护集通过后才按授权清理旧链，不提前宣称完成。
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
- 决策：一个 execution 的 `4.draft` 全部对象由一个真实 author actor 会话负责，该作者即本 execution 主会话，自主认领整批并执行获准的 init/acquire/author seal；一个 execution 的 `5.review` 全部对象由另一个自主认领的真实 reviewer actor 会话负责并自行 review seal。二者必须是不同 session/runId，可为同一 model family；宿主派发出的真实独立会话可担任该 execution 主会话，不再由另一主会话代理全部机械命令。不同 execution 可由宿主原生并行，仓库不提供 runner、fleet、语义 claim、模型路由、worker queue、actor projection 或自动恢复；`DEC-046` 的协作 claim 只校验归属/容量硬事实，不推进 execution，也不授予 actor 身份。
- actor 真相源：`002-4.draft` receipt 的 actor/invocation 就是该 execution 的真实 author，`003-5.review` receipt 的 actor/invocation 就是其真实 reviewer；对象业务产物不复制 actor，代码也不从对象投影、聚合或补写 actor。
- 交接：producer 跨会话只读三份 seal receipts、业务 result refs 与 immutable release handoff。作者整批 seal 后直交独立 QA，有容量即续领；QA 整批 seal 后直交获准总监发布，退回项直达作者，不等待其他 execution 齐套。后继由 Skill 固定，代码不得解释 receipt 推进流程；环境 facts 属下游 owner，不参与 producer 恢复。
- 失败恢复：未 seal 的步骤仅在原真实 actor 可核验时由同一会话续写部分产物；无法保持归属则保留原件并阻断。receipt blocked 新建 execution。不得换作者覆盖后冒充同一执行。任何旧 sequence、checkpoint 或 execution-state projection 均不迁移。
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
- 摄影图片与视频的地点关联：image/video主体与可选地点身份分离，无确证地点时不产生entityRefs或主主页锚点，复用现有题材或摄影标签与公共可空字段；完整身份则校验全部依赖，半填一律拒绝。homepage与article身份规则不扩大，无物种主页、假地点、第五载体或placeMode状态机。无地点不改变review/source/media/去重和里程碑计数；离线投影不得按entityRefs首项假定必有地点。
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
- 原作隔离：四载体共用sourceWork记录原生身份、实际取得证据及范围、有序媒体使用项；来源响应、机械摘录与宿主识别分开，不从生成的source.md冒称原网页。图片字节只持有一份资产身份，cover/inline/gallery/poster/reference是使用关系；组图members数组及正文锚点记录原序与位置，未采用页面图标不进入成品闭包，不定义DOM/通用AST或站点模式registry。
- 渲染隔离：审核成品继续使用manifest、Markdown及有序媒体，公开目标投影归下游分发构建并绑定目标契约、投影实现与配置摘要。复用现有release/export物化，不新增转换服务；原站变化不改既有成品，目标renderer变化不刷新旧source/review。来源事实、成品采用事实和公开署名只校验同层字节及引用，禁止跨阶段全等比较导致默认值污染旧记录。
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

<a id="dec-047"></a>
### DEC-047 核心诊断是 ship verify 的不可提升用途

- 决策：不新增 runner、fact 或 schema；在现有 `ship verify` 增加显式 `core-diagnostic` purpose，并复用同一 admission、apply→activate、四 owner receipt、runtime candidate binding 与现役 consumer verifier。诊断只另写 run 内普通 report，正式 `environment_release_result` 与 readiness schema 不扩展。
- feature/owner：六项选择闭集固定为 identity、feed/detail、search/recommendation、image/video Range、post write/readback、chat write/readback。Data 只执行前四项并如实投影后两项 `not_executed`；Ops/App 只汇总自身真实执行结果，不把 Data 未执行改写成通过。
- 安全与恢复：诊断永远不可提升、不写 readiness；Prod 额外要求 prevalidate instance、isolated data mode 与 prod-hosted candidate。任一 selected Data case 缺失或失败写 failed report/result 并保留首错；正式 purpose 完全沿现有 M10/Beta/Exit/premium 门。
- 关联要求与验收：[`multi-carrier-release REQ-023`](./multi-carrier-release/spec.md#req-023)、[`GWT-046`](./multi-carrier-release/spec.md#gwt-046)。

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

- 决策与 owner：canonical 内容在源码工作树平级独立 Git 仓；仓元数据除 schema 标识外只有 `repositoryId` 与 `layoutVersion`，实际工程契约摘要仅由 handoff 绑定。仓不是源码 worktree、submodule 或 symlink。Data owns 包/locator/记录，Service 只从 manifest 读取稳定身份，Ops 只物化 exact release。源码 worktree discovery 按 repository 身份区分，不使用目录名忽略规则。
- 目录：地域实体在自身领域下依已核实行政链、已有主类型、分区、名称、组内条目管理；posts 按 carrier、主分类、分区、名称、组内条目管理。具体路径语法与容量阈值唯一归 Data schema/policy。行政链可缺区县、可为直辖市/省直管县/境外真实层级；主归属只有一个，其他地域保留 ref。地域适用性显式，当前不实现非地点 producer。
- 分配：非空类始终从首分区开始，只用条目数与随体逻辑字节两个指标。已有同名组原地追加、不拆组；新组在容量允许者中取最低归一化负载，平分按编号，无合适者才开新分区。超大组只报告例外，无跨地域均衡、后台重分区、第三种统计阈值或 per-partition authority；inventory 可重建。
- 身份：逻辑 entityRef/实体 ID/作品 ID 在 init 冻结，目录末级数字只表示组内条目、允许空洞且不复用，不猜版本。名称/地域/类型整理属于显式 locator 变更；包内摘要不含外层 locator，release 复用既有引用定位，不新增 objectPath 表。同物新版本沿用身份并递增内容版本，新包字节不可借纯移动刷新旧审核证据。
- 并发与原子性：共同内容根的锁定位不依赖各源码 OUTPUT_ROOT；单对象临时包验证后原子可见，publish、整组整理与内容 Git ref 更新共享串行边界。缺根、错仓、名称/路径冲突 typed 阻断；只枚举声明对象根，Git、repository metadata 与 releases 不计入 inventory。execution/receipts 物理根不随 publish 重构变化。
- handoff：继续仅有 cohort/handoff 两份 terminal 事实，create-or-same 保存到内容仓；handoff 仅新增 `repositoryId`，工程 baseline/实际契约摘要沿用既有字段，所选对象与 exact 内容快照复用既有 release/object query digests，不另加 objectPath 表、`contentRevision` 或 `layoutVersion`，不要求内容提交或双提交。重建须保存固定时间和 exact build 输入，历史 bundle 不清理为试验对象。
- 理由与被否决方案：地域便于人工管理，但存储位置不应决定业务身份。否决路径哈希/按名取首项、日期轮次树、跨包媒体借用、分区 mapping authority、自动 rebalance、错误根 fallback、源码提交冒充内容快照。
- 失败恢复/回滚：沿用 `DEC-023` 的全量 before、独立备份、保护集与 expected-before staging；不交换包含 Git 的仓根。准备不授予搬迁/删除/init/clone/commit/push/环境激活权限，各动作分别确认；失败保持原对象与审计，不声称一个 lane 配置已切全局。
- 观测与可测试面：现有 DataRoot/inventory/object-transaction 短 local_contract 验真实行政链/Unicode/分区边界与跨 worktree 共锁；身份与 importer 测试验 ref/ID/主页 ID 守恒。仅输出该事务容量例外、首个 typed blocker、before/after 摘要，无新健康服务或全池日常重哈希。
- 关联要求：L2 `REQ-004`；[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-008`、`REQ-019`；[`canonical-content-identity-recovery`](./canonical-content-identity-recovery/spec.md) 的 `REQ-002`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)、[`canonical-content-identity-recovery`](./canonical-content-identity-recovery/spec.md)
- 关联验收：前者 `GWT-040`、`GWT-041`，后者 `GWT-002`、`GWT-003`；准出缺口由各 Story OPEN 承接。

<a id="dec-043"></a>
### DEC-043 发布闭包严格，运行实体引用与媒体失败局部降级

- 决策与 owner：producer 在 exact release 构建检查显式内部 ref，运行正文使用名称快照，用户点击才调用既有目标详情 API。Entity owns 可见性/权限，Content importer 复用既有 exact 主页映射，App 复用错误展示与媒体缓存；不扩展 runtime 的 active pointer fence 或添加跨服务强一致协议。
- 实体引用：文章 mention 从同一 Entity 映射生成而不是新增 hp 哈希公式，映射缺失呈普通文字；同名异地不得串跳。非文章保持可读 label/结构化关联，不新增通用富文本、引用卡片或 article-only GraphQL 扩展。内部语法不得泄露物理路径；没有系统实体的外部名称不捏造 ref。App 当前对缺映射 styled mention 的整段纯文本降级存在样式保真限制，作为已知不阻断限制跟踪，不据此宣称用户批准全部风险或真实消费验收已完成。
- 运行一致性：普通实体下线不级联下线作品、删原文、借用媒体或改历史 release；已知不可用可隐藏链接，不知道时不为去链接额外 query。点击后服从原 403/404/410 或 Data 历史 offline View 的公开契约并允许返回，弱一致不绕过权限。严重治理删除仍走原命令，不成为地点下线副作用。
- 媒体：包内资产相对引用在 release 物化为摘要交付键，环境 URL 经既有 endpoint/resolver 生成；实际上传摘要及 Range/MIME/readback 先于激活。正文/封面坏图局部占位，图集保留坏页位置仍可滑动，视频有界失败保留 poster/caption，poster/字幕失败不阻断可用视频，源站失效不影响随体成品。
- 缓存与恢复：只修既有图集实际 provider 接负缓存、视频 cache hit 不续 TTL/不重复启动恢复；网络新失败、成功与用户显式重试仍按原 owner 处理。已知永久缺失不自动重试。无逐实体请求、逐媒体 HEAD、引用状态 TTL、缓存广播、后台修复或周期巡检。
- 理由与被否决方案：关联是导航增强而非正文可用性依赖，媒体故障不应清空作品；否决实体下线反向遍历全池/级联重写、补充健康注册表、用无效链接伪装可导航、以 importer 单测冒充真实 UAT。
- 可测试面与观测：真实 Entity→Content importer→typed query 证明 mention 映射；App 现有错误/图集/视频短 local_contract 验单图失败可翻页、缓存跨实例复用及原 TTL 不延长。每屏请求数不随引用数线性增加，重试受原预算限制；授权环境再验证实体下线返回和视频 Range。失败只报原 typed 局部结果，不新增 SLO/报警体系。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-021`、L2 `REQ-004`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)，Runtime/Service/App 消费边界只引用原 owner contracts。
- 关联验收：`GWT-042`，缺口保留在 `OPEN-028`，不进入 producer END。

<a id="dec-048"></a>
### DEC-048 视频与图片共享消费者题材，观看价值复用已有角度叶子

- 决策：浏览与发现按用户想看的主体组织，不按拍摄或剪辑步骤组织。图片与视频共用同一套题材 `tagRefs`；不新增 Intent 轴、视频分类树或第二套入口 ID 表。
- 边界：`tagRefs` 优先主体，其次可核验事件或行为，再按需加入已声明消费的观看价值叶子、有据地点或季节与少量可见观感。时长、画幅、音轨、器材与制作步骤保留在各自媒体或来源事实，不充当大众兴趣。Audience 画像不从作品或观看行为推断。
- 消费：在线消费只读取 taxonomy 节点已声明的 `consumedBy`（`recall`/`scorer`/`intersection`/`search_facet`）。未声明采集与消费的 Format 内容角度只作 authoring 提示，不构成本 Story 合同入口。召回解释使用题材匹配，排序仍走既有行为与特征投影，不手写固定权重。跨载体可共享主题，载体偏好独立。文章复用同一批题材叶子，阅读问题映射现有旅行/攻略/科普叶子，不新增地貌、营造或体裁目录。
- 执行边界：拍摄参数叶子可继续服务 EXIF 通道；视频作者不把它们选作大众兴趣。seal 只校验 `tagRefs` 能解析到既有定义，不新增视频专用拒绝规则。
- 失败恢复：半填地点拒绝并沿用 [`GWT-046`](./multi-carrier-release/spec.md#gwt-046)。未知物种或行为只选用已有可证叶子，不另建回退合同。缺失观看价值不得用制作参数或空目录替代。
- 被否决方案：按载体复制雪山或求偶等叶子；新建观赏或风景欣赏目录；把画幅、FPV、器材参数补成大众分类；从标题拟人词推断求偶或用户身份；把展示分组写成 Data 入口权威。
- 可测试面：local_contract 绑定已声明 `consumedBy` 的共享叶子存在、禁止重复近义路径、查询解析到这些叶子；真实视频 author 与独立 review 读回 `tagRefs`。推荐效果由下游行为证据独立验收。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-003`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-047`、[`GWT-048`](./multi-carrier-release/spec.md#gwt-048)

<a id="dec-049"></a>
### DEC-049 四类岗位自主整批生产与最小协作事实

- 决策与理由：团队保持模板、deployment binding、当次授权/运行事实三层，Bot 名片或聊天不是执行 authority。模板只声明创作总监、创作者、独立 QA、电脑管家四类岗位，作者/QA 可有多个实例；人数、并发与账号部署不是固定七人组织。总监一次确认方向和预算、唯一发布并主动保流，作者作为本人 execution 主会话自领整批并 init/acquire/author seal，QA 自领整批并 review seal，管家只管获准工具资源。去掉代跑全部 CLI、逐题审批和全组齐套屏障，减少等待而不削弱独立审核、归属或人类授权。
- 对象与状态：既有协作单元 `(deploymentId, generation, globalIteration, shardName)` 与 `available|claimed|draining|blocked|closed` 保持不变，`shardName` 显式、稳定、绑定不重叠范围，不从 actor/PID/path 推导；generation/iteration 变化不可迁移旧 nonce。一个 deployment 至多一个 active shard，其内多个作者持有不重叠 execution/target scope，每 execution 一个 author、一个独立 reviewer；不得增 deployment 绕上限，不新增业务语义状态机。
- command/query 与一致性：复用 coordination 的单个 SQLite 短事务 CAS 核当前 actor、角色、execution/target 集合、generation、预算与在制容量后建立归属；同批多抢只有一个 winner，失败不留占用。作者最多两个未闭合、其中最多一个创作，送审/审核/待发布都占用；只从正式 receipts/publish proof 的 exact 绑定机械核验调用方声明的容量与释放条件，不据此选择后继或签发完成。全部有效对象 publish/readback 成功或契约明确终止且在飞写者已核才可释放，unknown 不释放；该 readback 仅为本地 canonical 事务身份/字节读回，下游 import/环境/App/API 验收不进入容量释放条件；释放/重放复用 expected state/generation/nonce，漂移零写。参数只在 Story `REQ-022` 一处拥有，不再加待审票据或多层配额。
- 共享事实与写权限：现有任务输入/报告单写总监在用户授权内确认的方向、预算、权限、实际版本及生效范围；四类角色均可读占用、来源媒体、receipts、QA、publish proof 和异常裁定，凭证/令牌/无关隐私除外。变更先保存后通知，下一次认领/提交核当前版本，越权或版本/必要事实不可读只阻断受影响动作。作者、QA、总监、管家写 scope 独立，共享可读不授予他人写权限；在飞 actor/授权不追溯重写，紧急撤权在真实写点拒绝，不靠群消息或私聊决定。
- 存储与事件边界：只复用现有任务输入/报告、coordination 归属硬事实、execution receipts/对象 proof/checkpoint；库保存 actor/execution/target/generation、角色 scope、预算引用与占用审计，不保存第二阶段状态、completed 清单或后继。正常通知仅作者整批→QA、QA 整批结果→总监，带 exact refs/digests 与下一动作，不把消息作为事件 authority。库损坏/缺失 fail closed，可经明确人工重建协作边界但不伪造历史 claim；不增看板服务、常驻扫描器、消息代理、自动派单器或 Envelope。
- 总监保流与 SLO：在宿主触发能力已证时约每 10 分钟低成本增量检查，已知失败下一可执行检查即处理；两次无法解释等待或超过实测正常周期时核原生状态并定向询问。首次发现异常即在现有 checkpoint 记录 owner/下一动作/下次检查，下一检查仍未解决则明确修复、终态接续、工程/用户升级或 blocked，不仅催问。只运行单个非重入检查，Routine 另获授权，缺自动唤醒即人工唤醒并标未实现无人值守；不每 tick 建新总监或生产调用，不把 10/20 分钟作取消 TTL。
- 失败恢复与回滚：普通输入错由本人按既有契约修正，同类确定性错误再次发生停止盲重试；已知终止先核 native 终态、receipts、原 actor/授权，由唯一 owner 按 retryOf 接续。unknown/额度耗尽保留 scope 和证据，只冻结冲突写，其他健康批继续；全局资源耗尽或 QA 全失效可暂停新增，用户为最终接管人。回退只能停止新增、保全原件并在可信安全交接点按有效授权接续，不取消未知调用、改旧 receipt 或恢复旧权限兼容层。
- A/B/C 初始化：A 新建复用匹配实例按授权补缺，B 先证无在飞/待接管后原位更新，C 逐单元保留 scope/actor/receipts/版本至安全交接点再更新角色；新任务遵循同一新规则，不等全队同步或重派 unknown。三场景都核实际活动根、工具/媒体链、全员同版本和总监检查能力并从受支持宿主读回；初始化零生产/Routine/清理，缺管理或状态读取工具交人工清单并 blocked，源码/简介更新不等于活跃 Bot 生效。
- 共享资源与清理：总监在用户总授权内调预算与已验证并发，管家在单独工具/环境授权内保障资源，不代管选题或发布；唯一收官者仍是获准总监。共同 publish flock 只保护同锁域单对象事务，不是跨机器 claim。后继只读审计前任 transition/nonce/receipts/产物/预算释放，清理仅限本 generation+claim 明确创建且非保护集、另获清理授权的临时字节；前任归属或终态不明保留 blocked，不以检查、TTL 或 successor 身份取得清理权。
- 模型边界：岗位手册表达专业能力与质量优先，不控制产品模型路由。平台不披露实际模型时标未知，不采信 Bot 自报模型名，不把猜测写入 seal；“明确未知”只关闭误报风险，不关闭按岗模型选择能力。
- 里程碑：十团队按同一全局 iteration 做有界小轮并不能替代 producer 计数；M100000 只在 homepage/article/image/video 各 `100000` 个累计唯一 finalized 对象形成 full explicit cohort、独立 immutable release 与 handoff 后成立。预算、轮次、team/shard/claim 数或媒体文件数均非替代指标。
- 失败恢复：复建默认只读待命。部分产物保全遵循原 actor/session 规则；宿主中断不从聊天、Routine、TTL、mtime 或 daemon inflight 推断完成。原子 release 仅释放协作 claim，不修改 receipt/pool；generation/nonce 冲突、预算不足、前任清理不明或 SQLite 不可用均 fail closed。
- 被否决方案：独立 QA 继续由创作者临时互审；新建 Grok 第二套 Skill、语义调度器、业务完成 registry、跨账号消息桥或模型路由服务；用 SQLite 行推进 producer；TTL 抢占；后继自动清理前任；把 Canvas 当正式规格；用 Duplicate 冒充跨账号 Share。
- 建议量边界：Story `REQ-026` 拥有 1:2:3:4 与最高 50 倍的非配额规划语义，不新增计数 policy、逐实体配额或停线判据；主页身份唯一，原作拆图/换版本不增数，正式 M 档保持现有政策，不以建议量覆盖里程碑。
- 可测试面：既有 coordination store/runtime 的并发事务与真实 task/canonical handler 写点是 local_contract seam，锁定批次/review 单 winner、两批且一创作、完整 target、独立 reviewer、同 deployment 非总监发布拒绝、缺围栏/旧代/撤权零写、幂等释放、unknown 不释放及无第二状态机。手册契约测试绑定四类岗位/共享版本/A/B/C/保流规则；原生工具缺失不能靠文本断言证明行为。
- 观测与准出：以同质量、载体、冷热缓存条件的真实有界试点逐级验证两作者、四作者、两 QA，报告净 eligible 产速、周期、WIP、最老未闭合项、首审/返工和单位合格成本，无 native 时间标未测。慢批与异常注入须证明健康批能继续、总监下一检查有裁定，零旧代/越权正式写；local_contract、真实 Bot 生效、真实生产净增各自举证，单账号缺口由 `OPEN-035` 阻断。未来十团队宿主、外盘与 M100000 仍由 `OPEN-034` 独立保持开放，单账号自主生产增量不包含多账号/VM 扩容。
- 多实例部署：客户端隔离只拥有 profile 生命周期，不拥有 producer 调度。每个实例绑定官方 App exact 版本/签名、独立本机 profile/data/output/workspace 根、一个 account identity ref 和一个 deployment；profile 不承载 token 的治理副本，manifest 只写 redacted 状态。深链、通知、Squirrel 更新、Keychain 与 Computer Use helper 按共享风险处理，双实例期间不更新，登录需要时单实例完成。
- 写围栏接线：单账号多作者与多实例团队的真实 task/canonical 写入口均消费显式 DB path 与 `WriteFenceToken`，先持本机协调写者 gate，再在 SQLite `BEGIN IMMEDIATE` 短事务核 deployment/generation、actor/角色、execution/target occupancy、有效授权及容量，结束事务后才执行受 gate 保护的业务与 execution/publish flock。普通写者共享 gate，不同 execution 可重叠；release/block/recover/任务版本变更等控制变更持独占 gate，等待已有写者离开再短 CAS。锁序固定为协调 gate → SQLite 短事务（关闭）→ execution/publish 锁；禁止业务锁内反取协调 gate 或持 DB 事务等待业务锁。控制变更和业务共同采用同一 gate，锁只用于本机，不作为跨 VM 文件系统保证；缺失、blocked、stale 或越权在业务写前失败，不能因遗漏环境变量进入无保护分支。SQLite 只机械校验正式证据绑定，不据 receipt 选择下一步；全局收官 deployment 加获准总监 actor 是独立发布授权，不由同 deployment 或 claim 派生。
- 扩容与回滚：2 -> 5 -> 10 每级独立取得账号/cloud computer、daemon、路径、外盘、锁竞争、预算和断线负例证据。任一串号、跨根写、helper/端口冲突、旧代写成功或更新替换在飞 App 时停止新增、保留 claim/证据并阻断冲突写；只在已核原生终态与明确关闭授权内关闭新增实例，不强停 unknown，不因回滚伪造 handoff。保留 profile 与证据，不自动释放或删除。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-001`、`REQ-006`、`REQ-007`、`REQ-008`、`REQ-022`、`REQ-023`、`REQ-024`、`REQ-025`、`REQ-026`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-009`、`GWT-010`、`GWT-049`、`GWT-050`、`GWT-051`、`GWT-052`、`GWT-053`、`GWT-054`、`GWT-055`、`GWT-056`、`GWT-057`、`GWT-058`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 后续动作由调用方显式选择；失败对象本身只保留 code/message/ref/origin 诊断。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。
- 宿主中断：会话预算耗尽只停止宿主继续操作；Data 不写 deadline/job terminal。尚无 create-once receipt 的步骤由可核验的原 actor 按同一冻结输入续做，既有 receipt 与已合格对象不受影响。
- 重入路径：未 seal 且原 actor 可核验时续写部分产物；无法保持归属则保留原件并阻断。receipt blocked 后只能以新 `executionId + retryOf` 消费显式业务 refs。

## 6. 质量与观测

- 记录 operation、终态、延迟与 canonical error；特有阈值由 spec 和运行配置约束。
- 宿主可在仓外记录会话数、并行重叠、elapsed 与成本等诊断；这些诊断不进入 Data receipt、准入、publish、milestone 或下一次 execution authority。
- Data 只保留逐 target source result、三份 seal receipts 与业务 result refs；不生成宿主调度、容量、heartbeat、截止或自动 calibration 报告。

<a id="dec-045"></a>
### DEC-045 内容池工作台以只读发布快照和独立离线台账运行

- 决策与对象边界：[`content-pool-workbench`](./content-pool-workbench/spec.md) 是生产结束后的本地 query + 离线人工 command 边界。query 从 canonical publish root 的当前显式快照动态发现 `contentFormId`，读侧不维护形态闭集；已注册形态交给专用 renderer，未注册形态交给保真中性 fallback，且 renderer 缺失/失败只形成局部 typed 结果。renderer registry 只决定呈现能力，不解释 canonical 字段、不改对象资格，也不把未知值映射成已知形态。
- 工作台源码布局：Data 本地工作台的版本化前端属于既有 `quwoquan_data/control_plane/content_workbench/portal/` 治理控制面子树；不得在 `quwoquan_data/` 新建 `portal` 根层目录，也不得并入线上 Ops Portal。
- 快照与刷新：进程启动时从只读 publish root 构造单个不可变内存快照，索引只持有筛选、身份、来源 descriptor 与证据 metadata，不常驻加载来源正文。全部 query 读取一次快照引用并返回其 `readToken`，不得跨请求阶段重新取 current。`POST /api/refresh` 是唯一刷新 command，以进程内 single-flight 合并/拒绝并发构建；构建在隔离对象中完成闭包和摘要校验后，以一次指针原子交换发布。构建或校验失败保留旧快照继续服务，不暴露半成品、不清空索引、不隐式扫描兜底；回滚就是继续持有交换前快照并显式重试 refresh。
- 存储与权限：canonical publish root 永远只读，工作台不得尝试 chmod、修复、回填或创建旁车。所有人工结论、候选、索引和临时文件只在显式 `QWQ_CONTENT_WORKBENCH_ROOT` 的文件台账中；该根必须与 publish root、源码工作树互不包含且不相等，缺失或重叠即 fail closed，无旧路径 fallback、数据库、dual-write 或在线写。读模型以 snapshot identity 绑定数字、列表、详情与来源证据；并发写期间允许返回携带该 identity 的 `stale_read`，不得伪称最新。
- command、一致性与幂等：写命令只创建精确版本人工 `qualified|unqualified` 结论或 R1/R2 离线候选；unqualified 的 changes + targetState 是原子前置条件，新候选固定待复审且不继承父版本结论。业务幂等键绑定对象、精确父/目标版本和 canonical business-bytes digest；同键同字节 replay，同键异字节 typed conflict。工作根使用单写锁，先在同一文件系统写临时文件并完整校验，再 atomic rename；锁失败或 rename 前崩溃零可见，rename 后重启按账本 readback，遗留临时文件可在不改已提交记录的前提下清理。回滚是停止使用或删除尚未被提交为可见记录的临时文件，不改 canonical R0 或历史台账。
- 来源身份与采用关系：来源唯一身份来自包内 `sources/<unit>/source.json`；详情只把 manifest 的 `citedSourceRefs`、source refs 与 attribution 明确绑定到该 identity 的来源标记为 adopted，不按 URL host、排序或文件存在猜测采用关系。每个 descriptor 暴露 source unit、title/platform、nullable canonical URL、source use mode、rights clue、fetched time、evidence state、adopted 与逐项 evidence metadata；缺失、损坏与未采用分别保真。来源正文仅在点名 evidence API 时按 descriptor 惰性打开并校验 sha256/bytes；Markdown 作为冻结 Markdown 呈现，其他文本 raw 保真，截断显式标记。外部当前源站只以经过 HTTPS 校验的安全新窗口链接提供并加 `noopener,noreferrer`，禁止 iframe、服务端代理或把当前网页作为冻结证据。
- 技术栈与复用：工作台沿用 Data Portal 与 Ops Portal 已有 React/TypeScript/Vite 工具链，并抽取/复用不含 Data 业务规则或 Ops 运行语义的中性 shared UI 源码（布局、分面、树、视口壳、状态展示）；业务 adapter 分属各自 owner，不通过复制组件形成两套行为。UI 与本地接口由一个 loopback-only、同 origin 的本地启动入口提供，不配置远端 CORS、数据库、消息系统、scheduler 或 worker。
- 发布隔离：workbench 的入口、依赖与静态产物明确排除于 prod image、route、部署清单和环境准出；本地接口不暴露 publish/promote/release/activate/import/deploy operation。离线候选没有发布资格，后续若需入池必须离开本工作台并重新进入原 producer/review/publish owner，本文不新增发布路径。
- 恢复、观测与测试 seam：仅观察 snapshot identity、refresh single-flight/构建/原子交换终态、renderer known/fallback、query count/list 集合摘要、ledger command 终态、锁/冲突/atomic write 结果与本地启动地址，不建事件平台、历史趋势或告警服务。local_contract 以 fixture/fault injection 验不可变快照、成功/失败 refresh、动态形态、集合一致、来源 adopted binding、证据惰性读取、锁/幂等/rename 与根隔离；api_integration 以真实 canonical 格式和本地同源进程验 readback、多来源 Markdown/raw/缺损证据及安全外链；user_acceptance 验证三视口、来源/生产 review、返工待复审及无发布动作。性能证据必须由已启动且索引预热、页面已加载的真实浏览器采集固定交互 30 个有效样本，nearest-rank p95 取排序后第 29 个且不高于 3000ms；安装、构建、启动、预热、显式 refresh 和 warm interaction 分开报告，不以任一上游 PASS 代替其它层。
- 契约边界：`quwoquan_data/schema/governance/content_workbench/` 下的 `workbench_filter.schema.json`、`read_models.schema.json`、`offline_review.schema.json`、`offline_candidate.schema.json`、`local_api.schema.json` 与 `operations.json` 是字段、path、operation、error wire 的唯一 authoring sources；实现是本地工作台工具，只证明离线浏览与复核边界，不授予或扩大任何发布准出资格。
- 理由与被否决方案：文件台账足以承载单机少量离线复核，数据库、事件平台、任务调度和在线回写会扩大运行与恢复面；让 publish root 可写会混淆 canonical producer authority；为当前四载体硬编码 renderer 闭集会阻断未来动态形态；把工作台放入 prod 会把离线工具变成未治理在线服务，均否决。
- 关联要求：[`content-pool-workbench`](./content-pool-workbench/spec.md) 的 `REQ-001`、`REQ-002`、`REQ-003`、`REQ-004`、`REQ-005`
- 影响 Story：[`content-pool-workbench`](./content-pool-workbench/spec.md)
- 关联验收：[`GWT-001`](./content-pool-workbench/spec.md#gwt-001)、[`GWT-002`](./content-pool-workbench/spec.md#gwt-002)、[`GWT-003`](./content-pool-workbench/spec.md#gwt-003)、[`GWT-004`](./content-pool-workbench/spec.md#gwt-004)、[`GWT-005`](./content-pool-workbench/spec.md#gwt-005)、[`GWT-006`](./content-pool-workbench/spec.md#gwt-006)


<a id="dec-046"></a>
### DEC-046 producer 与跨端共享统一语义内容协议

- 决策与 owner：`content-type-framework DEC-003` 拥有 semantic document 节点、HTML/Markdown mapping type、表格分类、protocol version triplet 与 object revision tuple 语义；本层只拥有来源取得、homepage/article author-review、canonical package/release 与工作台诊断交接。homepage、article、Service、Web、Android、iOS 和工作台必须引用同一 semantic document 的两组 exact bindings，不建立移动端模板、端专属正文或 renderer 派生 authority。
- 协议版本：`schemaVersion`、`dialectVersion`、`canonicalizationVersion` 分别版本化 AST envelope/字段、Markdown grammar/节点映射、canonical bytes/digest。producer、release 和 reader 在解释节点前校验 triplet 与 required capabilities；unknown schema/dialect major、canonicalization mismatch 或 required capability missing typed fail closed。minor compatibility 只能由 canonical contract 明示，不能靠忽略字段、人工决定或 renderer fallback 扩大。
- 对象 revision：`contentRevision`、`sourceRevision`、`layoutRevision` 分别绑定作者业务字节、采用来源 exact evidence、同一节点树的一套受治理跨端布局规则，并 create-once 组成已存在 object tuple。publish/release/consumer 必须同时整体引用 protocol triplet 与 object tuple；两组正交，任一组漂移、缺失或 latest-by-dimension 拼接 fail closed，均不能替代另一组。纯布局变化不能制造新内容或文章身份，来源升级不能静默覆盖旧证据。
- 来源映射：Markdown 与 HTML 是 mapping type 而不是 carrier/content type。Wikipedia acquisition 必须对同一 page revision 同时冻结 wikitext 与 Parsoid HTML 及摘要；wikitext 提供模板/表格/链接源语义，Parsoid 提供对齐结构，两者共同映射一个 sourceRevision。revision 交叉、只能读取 latest 或摘要漂移时不进入 author。其它 HTML/Markdown 来源同样绑定 exact bytes/revision 后映射。
- 语义与布局：节点 identity、父子关系、阅读顺序、媒体/caption、mention 与 table classification 在 mapper 一次形成。data table 跨端保留同一 header/cell/caption/accessibility order，窄屏只应用同一 `layoutRevision` 的统一响应式规则；layout table 按同一受治理顺序线性化。不同 viewport 只可改变尺寸、换行、滚动或该统一线性化，不得选择不同节点集合、内容结构或阅读顺序；renderer registry 只能决定组件呈现，不能重分类、改节点或把 fallback 写回 canonical。
- homepage 与 article：homepage 仅允许对 licensed 主源作 faithful adaptation，保持实体范围、事实限定、归因与信息层级；结构调整和补充必须可回到 exact source anchors。Article 资格要求独立问题/路线/时间窗口/受众任务或多来源论证；单实体百科只改标题、措辞、章节或 `publishAngle` 仍是同一语义对象，不能创建第二文章。contentId、publishAngle 与 layoutRevision 都不得规避该判定。
- disposition 与人工决定：mapper、author self-check 和 independent review 把不可映射、来源漂移、布局歧义、非忠实 adaptation 与文章不独立形成 typed disposition，绑定 object/node/source anchor、输入 protocol triplet 与 object tuple。自动流程不得默认处理需人工决定项；人工只能选择修订 content、替换 source revision、选择受治理 layout revision 或放弃，并 create-once 记录理由。继续生产必须形成新 object tuple 并重新 review；若协议规则改变还必须绑定受支持的新 protocol triplet。人工决定本身不签发 approval，也不能豁免协议兼容门。
- 工作台边界：保留用户已有 [`DEC-045`](#dec-045) 的只读 canonical 快照与独立离线台账。工作台可以诊断 mapping、节点、revision、表格分类与 disposition，并记录离线人工建议；不得拥有 mapper、faithfulness/independence 判定、canonical mutation、review 或 publish command。其 renderer failure 仍只是局部显示失败，不能改变对象语义或资格。
- 失败恢复与回滚：新协议按 authoring contract → mapper/producer → Service reader → clients 单轨硬切，不 dual-read/dual-write。失败保持旧 protocol triplet、object tuple、review、package/release 原字节可读；恢复通过受支持 protocol triplet、显式新 object revision/new review，不改历史。回滚代码/布局规则只重新选择已封存、协议兼容且两组绑定完整的对象，不临时拼接版本。
- 观测与测试 seam：local_contract 覆盖 exact wikitext+Parsoid revision、mapping、table 分类、两组版本正交推进、unknown schema/dialect major、canonicalization mismatch、required capability missing、disposition 与工作台根隔离；api_integration 覆盖 acquire→author→review→publish→Service exact protocol/object bindings；Web/Android/iOS/user_acceptance 在多 viewport 逐节点验证同内容结构、阅读顺序与 data/layout table。观测只记录 exact protocol triplet、object tuple、mapping/disposition typed result 和 renderer 局部结果，不建第二 semantic ledger。
- 被否决方案：移动端模板与“有据整理”自由改写、按 `publishAngle` 复制单实体百科文章、只存 rendered HTML、wikitext/Parsoid latest 混配、protocol/object 两组版本混淆或各维 latest 拼装、每端重新判断表格、工作台人工标记直接变更 publish eligibility。
- 关联要求：[`on-demand-content-pool-admission REQ-005`](./on-demand-content-pool-admission/spec.md#req-005)、[`multi-carrier-release REQ-003`](./multi-carrier-release/spec.md#req-003)、[`REQ-022`](./multi-carrier-release/spec.md#req-022)、[`markdown-article-kernel REQ-006`](../content-type-framework/markdown-article-kernel/spec.md#req-006)
- 影响 Story：[`on-demand-content-pool-admission`](./on-demand-content-pool-admission/spec.md)、[`multi-carrier-release`](./multi-carrier-release/spec.md)、[`content-pool-workbench`](./content-pool-workbench/spec.md)
- 关联验收：[`on-demand-content-pool-admission GWT-007`](./on-demand-content-pool-admission/spec.md#gwt-007)、[`multi-carrier-release GWT-045`](./multi-carrier-release/spec.md#gwt-045)、[`markdown-article-kernel GWT-005`](../content-type-framework/markdown-article-kernel/spec.md#gwt-005)
