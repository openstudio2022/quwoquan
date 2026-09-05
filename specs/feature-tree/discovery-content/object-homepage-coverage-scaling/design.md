# L2 Design：对象主页与多载体供给 (`object-homepage-coverage-scaling`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“可复用实体主页与多载体内容供给、发布和环境消费闭环”需要 `multi-carrier-release` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：可复用实体主页与多载体内容供给、发布和环境消费闭环。
- 设计目标：宿主 AI 原生串行或并发执行 producer 九阶段，跨会话只以 create-once receipts 与业务产物交接。
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
### DEC-001 四载体共享实体目录并由宿主 AI 执行唯一九阶段 Skill
- 决策：homepage、article、image、video 从同一 canonical entity catalog 形成彼此独立的 immutable execution；唯一 producer 流程是宿主 AI 直接执行 `.agents/skills/content-production/SKILL.md` 的九阶段，并在 `release -> END`。已退役编排与兼容读写必须在生产源码、schema、control plane、正向测试与 active specs 中物理归零，具体 token 只由反向门禁维护。
- 边界：producer 代码仅做 task init、stage-open exact input freeze、stage-close receipt create-once、下载/CAS、schema/digest/ref/media hard facts、单对象 publish 与 explicit cohort immutable release I/O。来源、选材、创作、review、verdict、typed issues、approved 对象、cohort/milestone 与后继均由宿主 AI 显式决定；后继只来自 Skill 固定顺序。既有 ship I/O 属下游环境 owner，不是 producer stage。
- 失败恢复：OPEN 无 CLOSE 时重做同一冻结阶段；CLOSE blocked 后新建 execution，不在原 execution rewind 或迁移旧状态。
- 可测试面：local_contract 锁定零旧 import/CLI/schema/reference、OPEN/CLOSE create-once、AI 显式结果与单对象原子 IO；api_integration 证明四载体可由宿主直接执行。
- 关联要求：`REQ-001`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：`GWT-020`

<a id="dec-022"></a>
### DEC-022 candidate 只冻结对象身份，source 与 review 在 execution 内单轨形成

- 对象边界：immutable candidate binding 只冻结目标对象身份、carrier、canonical coverage target 与 candidate identity；它不携带或要求 task-init 前 source/media admission、acquisition、rights 或 semantic verdict。`sources` 由宿主 Cursor/Codex Agent 选择来源，`1.download` 才取得 bytes、登记 source refs 与媒体 CAS/hard facts，`2.quality` 作语义保留/淘汰，`3.compose` 组织创作输入。
- 单一产物：`4.draft` 每对象只有载体主产物 `page.md|draft.article.md|image_work.json|video_script.json`；author actor/invocation、自检以及 prompt/compose/draft exact ref/digest 只由 sequence-006 CLOSE receipt 冻结，不再写 `draft_meta.json`、`author_self_check.json` 或 `agent_result_envelope.json`。`5.review` 每对象只有 `content_review.json`，统一承载 `approved|rejected`、简短 dimensions/blockingIssues 与逐资产 rights 结论；reviewer actor/invocation 及该文件 exact ref/digest 只由 sequence-007 CLOSE receipt 冻结，不再建立独立 review receipt 或镜像 verdict。
- 固定时序：唯一顺序为 `identity-only candidate binding -> task init -> sources -> 1.download -> 2.quality -> 3.compose -> 4.draft -> 5.review -> canonical publish/release`。acquisition/probe/digest/MIME 是 `1.download` 的机械硬事实；semantic 保留属于 `2.quality`；rights hard facts在下载时保留，逐资产使用裁决只在独立 `content_review.json` 单写。
- 语义主体：来源选择、质量判断、compose、创作、自检与 review 的唯一主体是直接执行 Skill 的宿主 Cursor/Codex Agent。仓内只做 deterministic init、OPEN/CLOSE、atomic download/CAS、hard-fact verify 与原子 publish/release；不得新增 resolver、projector、runner、controller、queue、registry、SDK、自动恢复或 actor projection。
- 失败恢复：source/ref/digest 或 stage-wide identity/integrity 漂移时当前 stage blocked；逐对象 approved/rejected 可混合，短缺写入 stage result artifact/typed issue，通用 receipt 仍只有 `pass|blocked`，只有零 approved 或 stage-wide identity/integrity failure 才 blocked。blocked 后用新 execution 重试，不改写旧 receipt。
- 可测试面：local_contract 证明 candidate binding 不要求 source admission，sequence-006/007 receipts 各自冻结真实 actor 与唯一业务产物 exact refs，publish 只消费 `content_review.json` 的 approved 对象；api_integration 从 identity-only Image/Video candidate 跑通 download→review→publish 并覆盖 identity/digest drift。
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
- actor 真相源：sequence-006 receipt 的 actor/invocation 就是该 execution 的真实 author，sequence-007 receipt 的 actor/invocation 就是其真实 reviewer；对象业务产物不复制 actor，代码也不从对象投影、聚合或补写 actor。
- 交接：producer 跨会话只读 stage OPEN/CLOSE receipts、业务 result refs 与 immutable release handoff。后继由 Skill 固定，代码不得解释 receipt 推进流程；环境 facts 属下游 owner，不参与 producer 恢复。
- 失败恢复：OPEN 无 CLOSE 时由同一 stage 的一个真实 actor 会话基于冻结输入完整重做；CLOSE blocked 新建 execution。任何旧 sequence、checkpoint 或 execution-state projection 均不迁移。
- 可测试面：静态检查锁定零旧控制面与 actor projection，行为测试锁定 sequence-006/007 actor 不同、各 stage 每 execution 单一 actor、create-once receipts 与并发单对象原子 IO。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-006`、`REQ-007`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-020`

<a id="dec-029"></a>
### DEC-029 规模里程碑累计复用 canonical 对象与原始 producer proof
- 决策：M1、M10、M100、M1000 按 `cumulative_unique_finalized_objects` 计数。达到更高级别时可复用已 finalized 的 canonical 对象，以及该对象首次产出时的原 execution、publish transaction 与九阶段 receipt proof；不得为复用对象伪造新 execution 或新九阶段 receipts。
- 每级交付：每个里程碑仍必须形成自己的完整、显式、create-once cohort、immutable release 与 producer handoff，并逐对象绑定原始 producer proof。新级别至少新增足量唯一 finalized 对象使累计值达标，cohort 不得靠重复 identity padding。
- 边界：handoff 只冻结 travel Research producer facts；不携带 UAT sample authority、import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback facts。
- 可测试面：同一对象跨相邻里程碑的 canonical identity、原 execution/publish proof refs/digests 保持不变；各级 cohort/release/handoff identity 不同且完整；重复对象不增加累计值。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-008`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md)
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-034`

<a id="dec-031"></a>
### DEC-031 research release 媒体以 CAS objectKey 私有交付并走短签消费，commercial 保留公开切片

- 决策：媒体交付形态由 `releaseClass` 在 release 构建期分流，只改 research 分支——
  - release 构建期：`releaseClass=research` 时 `media_manifest.json` 的 assets 条目产 `privateObjectKey`（即 canonical CAS 形态 `media/objects/sha256/{aa}/{bb}/{hex64}{suffix}`），不产 `publicSliceKey`。payload 内媒体字节按该 key 布局。`commercial` 分支的 `publicSliceKey` 形态与既有链路完全不动。
  - 导入投影：环境导入按 `releaseClass` 分流。research 媒体字节按 `privateObjectKey` 同步到环境 media 根，post 文档的媒体引用字段存该相对 key（非绝对 URL、不含 `media/{kind}/s/` 路径段），使 content-service `DetectPublicCDNMediaBinding` 与 `DetectAnonymousMediaURL` 对 research 对象闭包均返回 `false`。
  - 消费期：复用 `ReserveOriginalImageAccessGrant` 这一条既有 grant operation，不新增 research 专用 operation 或续签 operation。普通会话保持 ready image、Post 可见性与 `view|save` 原图语义；研究会话只允许 `purpose=view`，可为当前 active Research release 闭包内的 ready `avatar|image|video` 资产签发短时 URL。两种准入在 OriginalAccessQuota application owner 内按已验签 principal 分流，不由 HTTP adapter、App 页面或路径形态猜测。契约现行 `grant_ttl_seconds=300` 与「viewer×asset×purpose×窗口」每资产独立额度保持不变；App 对同一资产单飞并复用未过期 grant，因此浏览负载不需要第二套配额池。
  - 授权链前提由导入落齐：三个 importer 的 App 可见投影为每条媒体引用显式携带 release authority 的 `assetId` 与共享 `MediaDeliveryAccessMode`；content importer 把全部 release 媒体（含 creator avatar 与 entity homepage introduction assets）幂等投影进 `media_assets` 并绑定 source release identity。普通原图准入继续读取 Post named visibility reader；研究态准入读取 active Research release membership。任一资产身份、release binding、处理终态或访问模式缺失均 fail closed，不从相对路径或 URL 反推。
- 理由：research activation 判据要求「无公开 CDN 与匿名 URL」「媒体短期签名 URL」「访问审计」三项同时成立，而身份链与短签契约已可用，缺的只是私有引用形态与投影分流。CAS objectKey 已经是 service 侧契约事实——Mongo `media_assets.objectKey` 存的就是它，signer 按它签发——所以复用它不引入新布局，签发链路零改动。canonical 对象本就以 `objectKey`+`sha256` 命名字节，release 只是保留而非派生。
- 网络层边缘守卫：私有媒体 URL 的签名真伪与绝对到期时间必须在字节交付边缘复算，签发方只生成签名、不能替交付方证明请求有效。验证算法与私有交付前缀由 `quwoquan_service/runtime/media` 的共享私有交付协议单点拥有，gamma Caddy 与 `local_media_origin` 只作为该 verifier 的 adapter，消费同一 secret reference，不复制算法或路径闭集。签名缺失、格式错误、摘要不匹配或 `t` 到期均 403，公开 slice 仍匿名。secret 或 verifier 缺失时私有路径整体 fail closed，不能退回“参数在场即放行”。性能预算：验签为 HMAC-SHA256 纯 CPU 复算、无外部 IO，单请求附加延迟预算 p99 ≤ 1ms；视频 Range 每段复算一次，不缓存放行判定。
- 边界裁决：App 私有媒体获取、过期重取、稳定缓存身份与各 surface 接入由 [`DEC-033`](#dec-033) 统一约束。现行每资产独立额度结合 App 单飞和未过期 grant 复用足以承载浏览，不新增批量 operation 或浏览级配额池；真实 UAT 若在 grant cache 正常命中时仍出现 429，才通过原 policy owner 的新 calibration 调整数值，不以第二套 rate limit 先行过度设计。
- 被否决方案：发明与 public 同构的 `media/{kind}/p/asset/...` 私有布局——signer 不认该前缀（需要扩签发契约），静态服务挂整根时该路径照样匿名可达，且与 `media_assets.objectKey` 既有私有引用形成第二套私有布局真相源。统一为 `sliceKey`+`sliceVisibility` 两字段并让 commercial 一起迁移——动了无关轨道，commercial 契约的删改属另一 Story。由环境名、CAS 前缀或 URL query 推断交付形态——环境不决定数据形态，路径识别会把各语言字面量变成新的真相源。新增专用 research 签发 operation、续签 operation、批量 operation 或配额池——既有 grant command 与每资产独立额度已覆盖签发、审计与浏览单飞，新增即第二真相源。只检查 `sign+t` 在场——攻击者可自行拼 query，无法证明请求由签发方授权。
- 可测试面：按证据层拆分——
  - local_contract 覆盖交付分流：`releaseClass=research` 的 manifest 产 `privateObjectKey` 且无 `publicSliceKey`，`commercial` 反之，两键同现或同缺即 schema 拒绝。
  - local_contract 覆盖私有 key 形态：不含 `media/{kind}/s/` 段且非绝对 URL（探针两项判定负例），并通过共享私有交付协议与 release schema 的同源断言。
  - local_contract 覆盖导入同步器：对 research manifest 按 `privateObjectKey` 同步、对 commercial 按 `publicSliceKey` 同步，形态与 header `releaseClass` 不符即 fail closed。
  - local_contract 覆盖 grant 准入：research principal 的 `save`、非 active release 资产、无 release membership 与非 ready 资产均拒绝；同资产同幂等键重放不续期，同一未过期 grant 在 App 只换取一次。
  - verifier 纯函数的签名与到期判定归 local_contract；边缘 adapter 的真实 HTTP 行为（缺签名、伪签名、篡改路径、篡改到期时间与过期签名均 403，合法未过期签名 GET/HEAD/Range 保留 200/206）归 research-isolation-probe 与 api_integration 层锚定，与 [`multi-carrier-release` OPEN-015](./multi-carrier-release/spec.md#open-015) 完成判定对齐。
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 research readiness 下游消费面
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-020.t3`

<a id="dec-032"></a>
### DEC-032 研究态身份是服务端签发的 principal role，能力面由 operation guard 按 role 闭集收敛

- 决策：研究身份由服务端事实承载，不由客户端自选请求头声明——
  - 身份签发：user-service 登录与 refresh 的 access token 签发单点在账号命中 research allowlist 时向 token `roles` 附加 `research`。allowlist 与 token 签发均为既有机制，不新增 operation。
  - 能力面收敛：operation guard 对已验签 principal 含 `research` role 的请求只放行研究能力闭集——ready 读操作（feed、detail、对象主页、公开 profile 及其同类只读投影）、`content.original_access_quota.ReserveOriginalImageAccessGrant`、`content.original_access_quota.GetOriginalImageAccessAudit`、`content.post.GetResearchReleaseReadback`、`user.account_session.IssueWhitelistedResearchSession`、`user.account_session.GetResearchSessionAttestation`；写操作、站外分享、导出与其余操作一律 403 fail closed。闭集常量归 `quwoquan_service/runtime/auth` 单一持有，收敛点在 `authorizeGeneratedOperation` 的边界判定之前，对 public 与 runtime 两种 operation 边界一致生效。
  - attestation 定位：`X-Research-Identity-Attestation` 只用于 readback 链路把请求精确绑定到已签发 research session，不再作为能力面判定依据；缺失该头不使任何请求脱离 role 收敛。
  - 匿名与非研究内容面：active release 为 research 时，release 承载内容的读面只对 research principal 在场；匿名与不含 `research` role 的认证请求在内容 query owner 单点收敛为 `no_active_release` 语义的缺席结果，不逐 handler 分散判定。
  - 正式 runtime 边界：research session 与 readback 操作维持 `CommercialStatus=blocked`，research 验收固定 target-bound mutable test-live；release class 只从 Data-owned `ReleaseUatSamplePlan` 绑定的 immutable release identity 读取，并由 Ops `TargetUatBinding` exact-byte 绑定到 target/runtime/package/config/platform/device/runner slot，不由环境名推断。正式 candidate 可承载 immutable research release 的数据面，但不得为研究验收整体切换到 runtime operation 边界。四环境正式 activation 残量归 [`multi-carrier-release` OPEN-001](./multi-carrier-release/spec.md#open-006)。
- 理由：header 由客户端自选携带时，研究账号省略该头即可回到普通能力面，隔离证据是自限性的而非强制；role 进 access token 后能力面判定与请求方意愿无关。runtime operation 边界（mutable test-live）按设计放行 `CommercialStatus=blocked` 的操作，研究态 deny 必须与部署边界无关。研究浏览验收需要 feed、detail、主页等真实读面，四操作白名单撑不起消费闭环，闭集必须显式扩到浏览读面。
- 被否决方案：保留客户端 header 作为能力面判定——可绕过，隔离不成立。在各业务 handler 内逐个拒绝——能力面散布多服务形成第二真相源且必然漏项。给 `OperationSecurityDescriptor` 增加 research 维度并走 contracts codegen——描述符矩阵为单一身份面扩列，成本与收益不匹配。为研究浏览新增专用读 operation——既有 ready 读操作已覆盖，全部读面复制一遍即第二真相源。
- 可测试面：local_contract 按身份链覆盖——
  - allowlist 命中账号登录后 token 含 `research` role。
  - research principal 访问闭集外操作 403，闭集内读操作与 grant 放行，无 role 请求不受收敛影响。
  - active research release 下匿名与非研究认证请求的 feed 与 detail 均为 `no_active_release` 缺席语义。
  - attestation 缺失不使 readback 之外的请求改变能力面。
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 research readiness 面
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-020.t3`

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
### DEC-034 isolation runtime proof 的效度域是 release 加策略快照加时效，不绑 verify run

- 决策：ship verify 的 research isolation runtime proof 效度域为 `releaseId + manifestDigest + runtime 策略快照（policyRef + policySha256）+ 24 小时时效上限`，不绑 `verifyRunId`。同一 release 的后续 verify run 复用最近一次未超龄 PASS proof：复用前全量重验（release 身份、digest、策略快照与 PASS 内容闭包），重绑当前 run-id、重算 checksum，并把复用来源 run 标识以 `reusedFromVerifyRunId` 写入证据本体——复用产物与本 run 实测在证据形态上单义可区分。原 proof 文件保持 create-once 字节不变，复用不级联（后续 run 仍锚定原始实测 proof）。
- 理由：proof 证明的是「该 release 在该环境策略下的隔离行为」，效度随 release 与策略走、不随 verify 编号走；绑 run-id 使每次 verify 重试都作废有效证据，实测一轮收敛耗 9 个 verify run、每次被迫重跑完整 probe，是发布链路重试成本最大的一处。时效上限承接环境运行栈重建的新鲜度风险：策略快照覆盖不了栈重建（down/up 后 runtime.yaml 字节可能不变），24 小时上限保证复用只发生在同一工作窗内，跨日重入强制重新实测。
- 被否决方案：保持绑 verifyRunId——重试成本结构性不可行（本条起因）。无时效无限复用——栈重建后旧 proof 冒充新观测，新鲜度失守。绑 startup attempt 或 compose digest 世代——需要 probe 侧扩运行时身份字段并动 proof schema 的采集面，成本高于时效上限且世代字段在 prod-hosted 形态下没有稳定对应物；若未来边缘配置纳入受版本控制策略面，应同批进入 proof 绑定。
- 约束与影响：复用判定失败的候选跳过不修复，全部候选失效时收敛为既有 `DATA.RESEARCH.RUNTIME_PROOF_INCOMPLETE` typed 阻断；发现路径把被跳过候选计数写入阻断诊断。下游环境 owner 的重试 SOP 与本效度域同源，不另设 producer 阶段或第二套复用条件。
- 可测试面：local_contract 覆盖复用正例（重绑 run-id、provenance 在场、原 proof 字节不变）、manifest 漂移拒绝、策略快照漂移拒绝、超龄拒绝与无候选 GATE_BLOCK 回退。
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 下游环境终态面
- 关联验收：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `GWT-026`

<a id="dec-040"></a>
### DEC-040 Research 私有视频以 progressive MP4 单签续播，private HLS 保持 unsupported

- 交付契约：当前 Research projection 每条媒体引用的 `accessMode` 与稳定资产标识必填；只有明确 previous-version public contract version 可把 null/absent 解释为 public。当前 Research/private 缺字段直接 typed blocked，不从 URL、CAS key、环境名或缺席推断。
- progressive MP4：App 私有视频原子只接收已校验短签交付引用，原生播放器发起 Range。edge verifier 对每个 Range 请求重新验签。首次 401/403 使当前 grant 失效，协调器强制换签最多一次，并以播放器已确认 position 恢复。二次失败进入 canonical typed terminal，禁止循环或 public fallback。
- private HLS：当前 contract 明确返回 unsupported typed terminal，manifest/segment/key 不进入 progressive MP4 fallback。HLS 的分片授权、key authority、TTL 恢复与播放器状态属于独立能力，由 [`multi-carrier-release` OPEN-017](./multi-carrier-release/spec.md#open-017) 关闭；它不阻断 progressive MP4 的 fresh UAT，也不能靠放宽 `accessMode` 绕过。
- 失败恢复与观测：Range 验签失败、换签次数、恢复前后 position 与 terminal code 由现有 grant/audit 和播放器 raw `ReadinessCaseResult` 派生，不新增播放 ledger。位置恢复允许播放器容器的受治理 seek tolerance，但 identity、asset、release 与换签上限必须精确；tolerance 数值归播放器 runtime contract owner，不在本设计复制。
- 理由：progressive MP4 是单媒体 URL 加 Range 的授权模型，现有 grant 与 edge verifier足够闭合；HLS 需要 manifest、segment、key 多资源授权，复用单 URL 假设会在分片处 fail open。把已实现 MP4 与未设计 HLS 放在同一个 OPEN 会错误地把 fresh UAT 缺口表述为实现缺口。
- 被否决方案：401/403 无限换签、换签后从零播放、回退 public URL、缺 `accessMode` 默认 public、private HLS 降级 progressive MP4、为每个 Range 向 App 暴露独立 grant command。
- 可测试面：`local_contract`（`spec_ref=GWT-032`）覆盖 contract-version 条件、单次换签和 HLS unsupported。`api_integration` 对真实 edge 执行 Range 与 401/403 恢复。`user_acceptance` 以 progressive private MP4 产生 fresh raw `ReadinessCaseResult` 并证明位置保持。
- 关联要求：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 `REQ-016`
- 影响 Story：[`multi-carrier-release`](./multi-carrier-release/spec.md) 的 Research 私有视频消费面
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
- Data 只保留逐 target source result、stage OPEN/CLOSE 与业务 result refs；不生成宿主调度、容量、heartbeat、截止或自动 calibration 报告。
