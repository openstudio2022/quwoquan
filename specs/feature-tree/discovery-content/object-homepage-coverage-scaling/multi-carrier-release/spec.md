# L3 Story：多载体内容与主页发布 (`multi-carrier-release`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-008 / SCN-014`](../../../spec.md#scn-014)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容运营者，我希望文章、图片、视频和主页对象以独立 execution 分别生产，共享冻结实体目录与 release 边界，并把合格 Travel Research 对象作为 immutable producer handoff 交付；这样每个对象可按原始来源、创作、review 与 publish proof 复核并累计进入规模里程碑，而下游消费不改变 producer 完成事实。

## 2. 范围与非目标

### In Scope

- 四个 carrier execution 共享不含运行身份的 canonical entity catalog digest，各自冻结 target set、quota 与终态。
- 各载体复用同一 producer 创建、审核、publish 与 release 生命周期，并止于 immutable producer handoff；环境 import/activate/readback/UAT/EAF 仅为下游消费背景，不构成本 Story 的 producer 验收。
- 本 producer 只生成 Travel Research 内容与 `releaseClass=research` 的 immutable release/handoff；逐对象仍保留完整 rights/`usageScope` 事实，但 commercial release/readiness 不属于本 producer，也不据此建立第二 workflow、pool 或 semantic queue。
- 批次级/跨载体聚合门只作目标与统计；四载体共用 acquisition/rights/distribution admission，research 只放宽未验证的分发权利，不放宽访问控制、内容安全、隐私、未成年人、恶意文件、去重、实体相关性、质量或可播放性。
- 经确认的请求只由宿主 Cursor/Codex IDE/CLI Agent 直接执行 canonical content-production Skill；identity-only candidate-backed 工作包、producer 九阶段 receipts、approved object package、canonical pool 与 immutable release handoff 单轨推进。handoff 不携带 UAT/sample authority、import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback facts。

### Out of Scope

- 按需意图 preview 与 envelope 编译（归 [`work-request-compilation`](../work-request-compilation/spec.md)）。
- article 来源预筛、immutable candidate binding 与 canonical 池唯一写路径（归 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md)）；旧 media-work-unit execution schema 不在现役闭包。
- 来源发现的逐 target 计划、取得与 typed 结果（归 [`source-discovery-scale-reliability`](../source-discovery-scale-reliability/spec.md)）；宿主串并行不形成仓内调度、slot 或心跳控制面。
- invalid canonical identity 的修复裁决（归 [`canonical-content-identity-recovery`](../canonical-content-identity-recovery/spec.md)）。
- 为不同地区或载体维护第二套发布目录与运行台账。
- 绕过登录、付费墙、验证码、访问控制、DRM 或平台技术限制取得素材。
- 直接生成图片或视频，或将 deterministic image-sequence 冒充已取得的可播放视频。
- 改变 homepage、image 或 video 的真正来源、权利与质量硬判据；但其执行时点统一硬切为 candidate binding 仅冻结对象身份、`sources` 选来源、`1.download` 取得 bytes/CAS、`2.quality` 作语义保留。
- 冻结期多样性准入的每实体累计上限与 Top-N 上限数值：阈值由多样性策略的既有 owner 单点拥有，本 Story 只消费其准入结论，并约束该结论的归属、呈现与批次级零合格归因。
- 将 Data 的 `homepage` carrier 解释为 App micro。carrier 闭集固定为 `homepage|article|image|video`；App entry surface 与二维 UAT 矩阵属于下游消费规格，不构成 producer handoff 的内容或验收。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多载体宿主 execution 与 pool→release 单轨

- 每个发布对象必须闭合 creator、tag、entity、media、source、rights 与 independent review；`4.draft` 每对象只有一个 carrier 主产物，`5.review` 每对象只有一个 `content_review.json`。运行 receipt 只能写入 execution/output，不回写静态真相源。
- homepage、article、image、video 共享 canonical entity catalog，但各自拥有由 identity-only candidate bindings 初始化的 immutable execution。唯一语义与推进主体是直接执行 `.agents/skills/content-production/SKILL.md` 的宿主 Cursor/Codex IDE/CLI Agent；新任务不得调用或新增仓内 resolver/projector/runner/controller/queue/registry/SDK/自动恢复、`task execute`（含 plan-only）或 pool-dispatch。
- candidate binding 只冻结目标对象身份，不要求 task-init 前 source/media admission。中性 `task init` 原子创建三份输入后，宿主严格执行 producer 九阶段：`sources` 选择来源，`1.download` 取得 bytes/source refs/CAS 与机械 hard facts，`2.quality` 判断语义与保留，`3.compose` 决定结构，`4.draft` 创作，`5.review` 独立裁决；每阶段由 AI 在 `stage-open` 点名 input refs，DURING 直接写业务产物，POST 运行 verifier 与 self-check，最后由 `stage-close` create-once 冻结真实 actor、`pass|blocked`、typed issues、result refs 与 verifier facts。后继只由 Skill 固定；`release` 后固定 `END`。
- 一个 execution 的 `4.draft` 由一个真实 author actor 会话负责，其 actor/invocation、自检与 prompt/compose/draft exact refs/digests 只由 sequence-006 CLOSE receipt 冻结；`5.review` 由另一个真实 reviewer actor 会话负责，其 actor/invocation 与逐对象 `content_review.json` exact refs/digests 只由 sequence-007 CLOSE receipt 冻结。两者必须为不同 session/runId，可使用同一 model family；不建立对象级 actor projection。不同 execution 可由宿主原生并行，跨会话只认 receipts 与业务 result refs。
- 单载体失败不得覆盖其它工作包，也不得阻止其它载体已合格对象入池。approved/rejected 可混合，短缺由 stage result artifact/typed issue 表达，不给通用 receipt 增加 `partial`；只要至少一个 approved 对象且无 stage-wide identity/integrity failure，stage 可 `pass` 并保留 shortfall，只有零 approved 或 stage-wide identity/integrity failure 才 `blocked`。
- sequence-007 receipt 所绑定的 `content_review.json` 判定 approved 后，publish AI 对对象逐个调用 canonical 单对象事务；不存在独立 review receipt、drain/process manager 或 execution 级 publish。canonical object package + append-only pool record 是 producer 内部 publish→release 的持久事实；release ref/digest、explicit cohort ref/digest、milestone、carrier counts、content-pool handoff refs/digests、producer baseline revision 与复用对象的原 producer proof 组成唯一 immutable producer handoff。运行身份不进入 consumer identity、eligibility、release cohort 或 App DTO。
- release selection 只接受显式 create-once pool record、完整 admission/rights/sourceAttribution/content-library binding 与 canonical identity。逐对象失败只排除该对象，成功对象继续。content library 是媒体字节唯一 holder，release 只作 distribution materialization。
- 每个 execution 的 `approvedQuota`、candidate count 与 workUnitCount 三值分离；宿主并发能力不进入三值、对象判据或仓内配置。
- article/image/video Post manifest 必须显式 `contentIdentity=work`；新增对象必须有稳定 `contentId`、递增 `version`、`sourceType=data`、`variantPurpose`、`admission`、`usageScope` 与 `status`，只有 `completed + passed + active` 可被 release 选择。

<a id="req-002"></a>
### REQ-002 Travel Research 生命周期与统一素材 admission

- acquisition、semantic、review 与 canonical pool 不从环境推断 lifecycle/class。本 producer 的 immutable release build 必须显式且只能选择 `releaseClass=research`，并在 create-once producer release/header/handoff 冻结同值；环境名、临时环境变量、fixture 或下游状态不得改写。
- 每个实体头像/主页媒体、文章图、图片作品与视频资产都必须记录 `acquisitionStatus`、`rightsStatus=verified|unverified|restricted|unknown`、`authorizationRequired`、`distributionDecision=research_allowed|commercial_allowed|blocked` 以及 `sourceUrl/platform/creator/capturedAt/contentSha256/license/termsUrl/authorizationProof/rightsIssues`，以保留真实 rights hard facts。
- Research 允许已取得且权利状态为 verified/unverified/unknown 的资产，restricted、未取得、生成素材或缺来源/权利缺口字段仍阻断；`commercial_allowed` 只是一项来源/权利事实，不授权本 producer 生成 commercial release/readiness。
- Research immutable release 必须冻结权利状态计数、精确 authorization-required asset IDs、四载体 `researchAcceptedCount`、逐来源 assets funnel 和 `containsUnverifiedAssets`；commercial release/readiness out of scope。

<a id="req-003"></a>
### REQ-003 站点、实体与 creator 深挖的文章、图片和视频来源

- Article 来源按 `著名旅游站点的站点级发现 -> 实体强相关主题搜索补充 -> 命中 creator 的公开作品分页` 顺序运行。站点级发现优先消费公开 sitemap、列表、专题、分页或官方 API；实体搜索只接受攻略、游记、玩法、避坑、出行或摄影等旅行强相关命中。每一篇作品独立执行实体/地理/旅行意图、内容安全、重复与质量判断，creator 主页不可访问时才使用搜索索引补全公开结果，不得据此宣称抓全作者全集。
- Article 分类必须覆盖 `摄影`；摄影文章与攻略、游记等使用同一 Post/Article 契约与质量准入，不创建第二套载体。
- research 图片检索目录版本化，按 category/entity/season/style/viewpoint/popularity 展开。图片来源按 `专业图库/摄影社区站点级发现 -> 实体或摄影主题搜索 -> 命中摄影师的公开作品分页` 运行；Wikipedia/MediaWiki entity media 只作实体相关补充，不作为长期专业图库主来源。搜索引擎只作 discovery，最终来源、creator、原始资产、取得方式、rights/license/terms 与时间证据必须回到作品页、官方 API 或受治理人工输入。
- 视频按 `canonical entity 强相关搜索 -> 视频命中 -> channel/creator stable id -> 作者公开视频分页` 运行；作者其他作品仍须逐条通过旅行/地点/摄影相关性与负面主题过滤。无法取得 stable creator id、公开分页或逐作品来源证据时只保留本次命中，不构造作者全集。
- creator 深挖 receipt 必须冻结 provider、stable creator id、query/list page、cursor/checkpoint、observedAt、可见结果范围与每作品判定；完整度只能表述为 `visible_public_results_at_observed_at`，禁止把搜索索引结果声称为平台全量。
- 所有站点、搜索和 creator shard 只允许公开直链、平台支持接口或人工提供文件，不新增规避登录、付费墙、验证码、访问控制、DRM 或 robots/服务条款限制的抓取器。单 Provider 或 shard 的 typed failure 只阻断自身，不阻断同 carrier 其他来源。
- CLI 与 receipt 对每个 `displayName/provider` 输出 `planned/discovered/downloaded/accepted/rejectedAssetCount` 及 verified/unverified/restricted/unknown 计数；下载成功不得把 rights 状态升级为 verified。
- 文章声明为 illustrated 时必须闭合封面与正文图及各自来源；封面与正文图可来自不同的可追溯授权来源。illustrated/text-only rate 只作为供给统计，不参与对象准入或规模晋级。
- 视频候选保留 play/like/comment/share/favorite 的真实观测与观测时间，并只在同平台、同主题、同时间桶内按 percentile 排序。缺失项保持缺失并标明不可参与热度排序的原因，不得补零或生成虚假排名。
- ranking-ineligible 视频可以进入 research release；热度信号完整度和 percentile 只作为推荐与供给统计。只有公开可取得、可解码、可播放、无 DRM、未绕过访问控制且通过安全/相关性门的真实视频文件可进入 research release。
- homepage 与 article 的百科来源必须同时从可见正文与结构化信息区取证不可变结构化事实。信息区的字段名与取值只在语义一致时采信，字段名指向的受治理字段与解析出的取值类型不一致时该候选事实作废，不落入其它字段。

<a id="req-006"></a>
### REQ-006 零仓内编排与 legacy 硬删除

- 旧 managed SDK/provider、agent/controller/queue/campaign/recovery、runner/fleet/lane claim、stage-gate registry、semantic prepare/record wrapper、自动恢复与 execution-state reducer 必须物理删除；禁止 shim、dual-read、retired-path fallback 或 sequence-017 兼容。
- 删除是本 contract-reset 的已批准架构决定，不以 `GWT-034`、`OPEN-006`、stable-production proof、旧 proof、任何 App/API UAT 或 terminal retry evidence 为前置授权。
- 宿主并发、模型选择、截止与会话重启是宿主原生能力，只能作为外部诊断，不进入仓库业务对象、producer handoff 或下游 promotion。
- 每个 stage 的 verdict、typed issues 与 result refs 由宿主 AI 显式提交；代码只执行 OPEN input freeze、CLOSE create-once 与窄 IO/verifier，不建立第二终态 writer。

<a id="req-007"></a>
### REQ-007 confirmed demand 沿 producer 九阶段推进到 immutable handoff

- producer 完整路径固定为 `confirmed carrier demand -> identity-only candidate-backed task init -> 宿主 Agent 九阶段 -> canonical object package + pool record -> explicit cohort immutable release handoff -> END`；旧控制面与任何消费阶段不在现役闭包。
- `task init` 的 deterministic 三文件原子初始化已实现并由 local contract 锁定；真实 confirmed demand 的宿主消费证据由 [`work-request-compilation` OPEN-001](../work-request-compilation/spec.md#open-001) 跟踪。每一步只消费前一步 immutable ref/digest，失败不得跳阶或用旧 receipt 冒充当前完成。
- producer release/handoff 不包含 UAT sample authority、environment consumer facts、import/activate/readback、App/API UAT、EAF、promotion 或 rollback。下游可只读 handoff 独立消费，但其成功、失败或未运行均不得生成 producer receipt、回写 execution 或改变 producer END。

<a id="req-008"></a>
### REQ-008 发布只消费显式 cohort

- release 只消费调用方显式提供且经 schema 验证的 exact cohort；不得扫描全池后隐式选择“全部可发布对象”。M1/M10/M100/M1000 按 `cumulative_unique_finalized_objects` 累计达标，每级都必须形成自己的 full explicit cohort、immutable release 与 producer handoff。
- build 在写入前逐对象重验 canonical identity、review、rights、source/media closure 与 content-library binding；任一对象失败只形成 typed exclusion，不改写 cohort 或其它对象。
- release identity、cohort digest 与 payload 一次冻结并 create-once；重放只接受逐字节相同结果，任何漂移 fail closed。更高级别可复用 canonical 对象及其首次 producer execution/publish proof，handoff 必须原样绑定该 proof，不伪造新的九阶段 receipts；重复 identity 不增加累计对象数。
- canonical 不变式：canonical 对象只存 `objectKey`、`sha256` 与 `assetId` 私有 CAS 引用，禁止写入 `publicSliceKey`。公共切片键只能是 release 构建期派生物，使已入池对象在媒体交付形态变化时可原地复用。

<a id="req-009"></a>
### REQ-009 内容库是媒体字节唯一 canonical holder

- content library 是 canonical 对象引用媒体字节的唯一 holder、durability owner 与 recovery source；canonical object transaction/pool record 只冻结 `objectKey`、`sha256`、`assetId` 与 library binding，不在 Git、execution output、release 或环境根建立第二份 canonical 字节归属。
- release 内媒体字节只是从 content library 派生并由 manifest digest 约束的 distribution materialization，用于目标环境交付；它不是第二 holder、durability 副本或 canonical recovery source。materialization 丢失时只能从同一 content library binding 重建，不得反向把 release bytes 提升为 canonical。
- publish、selection seal 与 release build 在读取 selected 或 rebuild-prior 媒体时，只要 content library 中 exact bytes 不可达、摘要不符或 binding 漂移就 fail closed。禁止回退到 Git 随体、旧 release、公共切片、测试 fixture 或 execution staging 补字节。
- 干净检出只证明 schema 与引用契约可复核，不证明媒体 durable；准出必须以 content library exact-byte readback 与本次 distribution materialization 对账为证据，任一缺失不得降级为告警。

<a id="req-010"></a>
### REQ-010 homepage 与三个 post 载体共享同一份准入判据

- homepage 走 receipt 协议 publish 的同一条链：sequence-007 `5.review` receipt pass、布局可发布、对象唯一 `content_review.json` 为 approved，之后经实体事务进入 canonical `entities/`。禁止为 homepage 建立第二套准入判据或 attestation。
- homepage 的对象身份是实体路径 `domain/type/name`，没有 `publishAngle`/`publishTitle`/`publishSeq` 这组发表坐标，因此目标集来自 execution 工作包内实际存在的实体对象，而不是 frozen target set 的投影；实体类型冲突是结构化错误而非静默去重。
- homepage 缺位会让 article 永久卡在引用闭包：article 可以先进池，但其 publishable 要求 `entityRefs` 指向的 homepage 已 admitted。因此 homepage 必须先行或与 article 同批。
- apply 模式下零对象晋级必须报错，不得以「promoted=0」的成功报告收尾。

<a id="req-011"></a>
### REQ-011 candidate identity 与 execution source evidence 各自单写

- homepage/article/image/video 的 immutable candidate binding 统一只携带目标对象身份、carrier、canonical coverage target 与 candidate identity；它不携带 capsule/admission receipt，也不要求 task-init 前 source/media evidence。
- `sources` 为每个 target 选择来源并写 source plan；`1.download` 才为实际取得结果写 source units/source refs、媒体 bytes/CAS、MIME/digest/probe 与 rights hard facts。candidate identity 与下载证据必须绑定同一 target，但两者不可互相冒充。
- source evidence 的显式输入构造与其后的 identity/digest 漂移比对只允许有一份实现；不得按载体恢复 capsule/admission 二分投影，也不得新增 resolver/projector 去补写 candidate。
- candidate 只冻结对象身份，无法唯一映射 target、identity 重复或 binding digest 漂移时 task init fail closed；来源缺失、取得失败或 bytes 漂移则在 `sources|1.download` 形成 target-scoped typed issue，不倒写 candidate。

<a id="req-012"></a>
### REQ-012 逐载体对象字节预算只有一处声明，判否在下载截面完成

- 逐载体单对象存储预算的数值是本 Story 的规格事实，唯一声明位为 `quwoquan_data/control_plane/_shared/media_processing.policy.yaml` 的 `objectStorageBudgetBytesByCarrier`。取值优先级固定为「具名载体档 → `default` 档」，两档都写在该文件内，因此任一生效值都能指回一处写下它的文件；`default` 缺席在 policy 装配期判否。下载截面与 publish 截面都经同一派生点取值，禁止任一侧另立常量或另设更宽的放行值。
- 「资产必须装进其载体的发布预算」是下载决策截面的不变量，并在 `1.download` 一次冻结。载体由来源单元自己声明的 research lane 决定；lane 缺席或落在闭集之外时该截面判否，不替它挑一个载体，因而也不替它挑一个预算。
- 超预算候选在该截面就地收敛：先按已声明交付档自宽到窄降采样，取第一个装进预算的档并按新字节身份重登记摘要与内容类型；每档都装不进、或派生体反而跌破像素门时给出 `DATA.MEDIA.ASSET_OVER_BUDGET` 并点名该资产。禁止把判否推迟到 publish——落在放行值与预算之间的资产会走完 `2.quality`→`5.review` 全部创作与评审成本，且一个超尺寸 homepage hero 会连带让引用该实体的已完成 article 因引用闭包不成立被 `DATA.POOL.REFERENCE_MISSING` 长期排除。
- 该不变量与 provider 无关：`pageImageRenditionWidth` 的服务端缩略图偏好只覆盖 `upload.wikimedia.org` 的 commons 非 thumb 路径，`pinterest`、`tuchong`、`openverse` 都没有对应路径，因此它是尽力而为的优选而不是预算不变量的实现手段。
- `sourceAssetMaxBytes` 是单次抓取的传输上限而不是准入判据：它只回答「愿意为一个候选花多少带宽」。源体允许大于对象预算，因为降采样需要先拿到源体。
- 资产的像素几何按交付端呈现的方向记录。EXIF Orientation 声明 90° 旋转时存储栅格的宽高与显示宽高互换，只读存储栅格会把一张横向全景图记成极端竖图，并使相关性判定、封面候选、有效交付宽度与字节预算全部按转置后的几何得出结论。重编码会丢弃 EXIF，因此派生体必须先旋转再编码。

<a id="req-013"></a>
### REQ-013 运营读模型只作 projection/query view

> 下列 `REQ-013` 至 `REQ-016` 保留为既有下游消费规格背景，由 Runtime/Service/App/Ops owner 实现与验收；它们不进入 content-production 九阶段、producer release/handoff 或 producer 完成条件。
早期消费场景中的 `Data-owned ReleaseUatSamplePlan` 仅表示下游 Data release consumer 契约的历史命名，不表示由 content-production producer 创建、携带或验收；该 sample plan 及其 UAT/EAF facts 均 downstream-owned。

- `ContentProductionTaskView`、`ContentItemVersionView`、`EnvironmentReleaseOrderView`、`ReviewDecisionTimeline`、`ReleaseSelectionView` 与 `TargetAcceptanceView` 均为无写权限的 projection/query view，不拥有 command、Repository、checkpoint、独立 ledger 或生命周期终态。
- `ContentProductionTaskView` 只投影现役 carrier demand/execution manifest/stage receipts；旧 WorkRequest schema 不构成依赖。`ContentItemVersionView` 只投影 canonical object transaction/pool record。`ReviewDecisionTimeline` 只投影上述 owner 已绑定的 review facts。`ReleaseSelectionView` 只投影 `ContentRelease` 及其 selection evidence。`TargetAcceptanceView` 只投影 per-environment operation/acceptance facts。`EnvironmentReleaseOrderView` 只读 Alpha/Beta/Gamma/Prod 四环境事实并排序，不推导、补写或推进任何环境状态。
- projection 缺失、延迟或重建不得改变 owner facts；query 发现 ref/digest 漂移时返回 typed blocked，不以本地 checkpoint、缓存行或最后一次成功值修复 owner。

<a id="req-014"></a>
### REQ-014 App 验收是 entry surface × carrier 二维矩阵且 raw 结果单写

- App 验收矩阵的 entry surface 轴固定为 `feed|search|recommendation|direct_or_object_route`，carrier 轴固定为 `homepage|article|image|video`。每个 cell 必须显式声明 `required|not_applicable`，并在 required 时给出 repo-relative 验收锚点引用与 runner；两轴不得合并或统称“四 surface”。
- raw canonical `ReadinessCaseResult` 是唯一 UAT 结果事实，逐 cell 绑定 target、release identity、runner、输入与真实观察。允许建立只读完整性 projection 检查 required cell 是否齐全，但该 projection 不得生成 verdict、promotion、write-back 或独立 UAT ledger。
- `EnvironmentAcceptanceFact` 直接绑定全部 required raw result refs 与 exact-byte digests，并验证它们属于同一 `TargetUatBinding` 与 release identity；缺失、重复、跨 release、digest 漂移或 `not_applicable` 无验收锚点引用均 fail closed，不由 counts 或完整性 projection 代填。

<a id="req-015"></a>
### REQ-015 入口面缺席、治理与回滚语义互不代偿

- 四个 entry surfaces 读取同一 active release identity。对象被 canonical owner 明确删除时，集合入口排除该对象，`direct_or_object_route` 才返回 canonical deleted 语义；空结果或环境没有 active release 必须保持 `no_active_release`/empty 语义，不得伪装成 deleted。
- `offline` 表示目标环境/operation 暂不可消费，保留 release/object identity 与 canonical recovery action，不得改写成 deleted 或 `no_active_release`。`retired` 是 `ContentRelease` 治理态，不直接成为 App wire；retire 后若没有 active pointer，入口面只呈现 `no_active_release`。
- rollback 或 replay 成功后，feed、search、recommendation、direct/object route 必须全部回到同一个 previous release identity；任一入口仍读失败 candidate、混合新旧 identity 或仅 counts 相等均为 `rollback_failed`，不得由缓存 projection 掩盖。

<a id="req-016"></a>
### REQ-016 Research 私有媒体按显式交付契约 fail closed

- 有效 Research projection 的每条媒体引用都必须携带 `accessMode` 与稳定媒体资产标识；`accessMode` 为 null/absent 只允许由明确声明的 previous-version public contract version 解释为 public。有效 Research/private projection 缺失该字段必须 fail closed，禁止按 URL、CAS key、环境名或字段缺席推断 public。
- progressive private MP4 通过已校验短签 URL 播放；边缘对每个 Range 请求重新验签。首次 401/403 只允许强制换签一次并从已确认播放位置恢复，二次失败停在 typed terminal，不循环、不回退公开 URL。
- private HLS 当前为 unsupported typed terminal 并 fail closed；它不得进入 progressive MP4 fallback，也不得阻断 progressive MP4 的 fresh UAT。其设计、实现与独立 UAT 由 [`OPEN-017`](#open-017) 承接。

## 4. 契约引用

- media processing policy：`quwoquan_data/schema/content/media_processing_policy.schema.json`
- release：`quwoquan_data/schema/release/release_header.schema.json`
- asset admission：`quwoquan_data/schema/release/release_asset_admission.schema.json`
- lifecycle policy：`quwoquan_data/schema/governance/content_distribution_policy.schema.json`
- environment readiness：`quwoquan_data/schema/release/environment_release_readiness.schema.json`
- commercial transition：`quwoquan_data/schema/release/commercial_transition.schema.json`
- 下游环境 ship report：`quwoquan_data/schema/release/ship_report.schema.json`（环境 owner 消费契约，非 producer stage）
- release identity incident：`quwoquan_data/schema/release/release_identity_incident.schema.json`
- stage receipt：`quwoquan_data/schema/execution/stage_receipt.schema.json`
- canonical pool record：`quwoquan_data/schema/release/pool_object_record.schema.json`
- UAT matrix cell binding：契约字段 `required|not_applicable`、repo-relative `spec_ref`、`runner`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 独立载体分别执行且引用闭包后形成 producer release

- GIVEN homepage、article、image、video 各有一个 immutable execution，并共享同一 source revision 与 entity catalog digest。
- WHEN 四个 execution 由宿主按当前会话能力分别执行，可串行或在不同 execution 间重叠生产，且操作者请求聚合 producer release。
- THEN post 不等待 homepage execution 或 publish，任一载体失败只保留在自身 evidence，其他载体已合格对象仍可 publish。
- THEN 仅从 entity identity、creator、tag、source 与媒体处置全部闭合且 `content_review.json` approved 的对象中选择 immutable cohort；悬挂引用只排除对应对象，足量有效 cohort 仍可 release。
- THEN 同一 execution 的 `4.draft` 只有一个 author actor 会话、`5.review` 只有另一个 reviewer actor 会话；不同 execution 是否重叠不影响 publish 或 release。任一 execution 的 publish 不得早于自身 sequence-007 review terminal，但不得等待其他 execution 的 review/publish terminal。
- THEN 某 execution `0 < approved < quota` 时 stage result artifact/typed issues 保留 shortfall，通用 receipt 仍为 `pass` 且全部 approved 对象 finalized；`approved == 0` 或 stage-wide identity/integrity failure 时才 `blocked`。
- THEN 全批次零 rejected 仍允许成功；若存在 rejected，则每个对象必须有非空 `objectRef` 与 `content_review.json` blockingIssues/typed issues。
- THEN 单 execution review/publish 失败只阻塞该 execution。
- THEN 四个 execution root 相互隔离；共享 canonical 只经逐对象原子事务，release 只读 AI 显式 cohort，环境是否消费不参与判定。

<a id="gwt-002"></a>
### GWT-002 research release 可内部消费但不可冒充商用

- GIVEN Alpha、Beta 或 Gamma 要为受控 Research release 申请内部消费身份。
- WHEN runtime materialization 冻结 target-scoped acceptance subject 与 canonical account identity，User 通过同一 subject 的公开 OTP/login 建立账号并 readback。
- THEN Research session authority 只接受该单一 target binding 的 account allowlist 并签发短时 attestation；空 allowlist、临时 TestData actor、数据库反查、旧 session 或 account/subject readback 漂移必须 fail closed，且 Prod 不启用该 authority。

- GIVEN 四载体对象共享同一 source revision/digest/entity catalog digest，研究素材已取得且完整记录来源与权利缺口。
- WHEN 生成并请求激活 `releaseClass=research` 的 immutable release。
- THEN unverified/unknown 可记为 `research_allowed`，restricted/未取得/生成/缺字段素材与不可播放视频被阻断；文章批次配图率只写入统计，单篇 illustrated 声明的同源封面/正文图闭包仍是对象硬门。
- THEN Data-owned `ReleaseUatSamplePlan` 绑定同一 `releaseId+manifestDigest+sourceIdentitySetDigest+releaseClass+productLifecycleState`；四环境各自的 activation/readiness 与 Ops `TargetUatBinding` exact-byte 绑定该 plan，本环境 `EnvironmentAcceptanceFact` 直接绑定 required raw `ReadinessCaseResult` refs/exact-byte digests、独立 import/readback 与 research isolation policy/proof，并按 Alpha→Beta→Gamma→Prod 绑定前一环境 fact 的 exact bytes；匿名身份、公开媒体 URL、分享、导出或索引任一可用均 `GATE_BLOCK`。
- THEN commercial readiness 不存在，且任何未授权 asset ID 不得进入 `commercialAcceptedCount`。

<a id="gwt-009"></a>
### GWT-009 宿主并发不改写数量与对象判据

- GIVEN 相同 confirmed demand、candidate set 与 quota，以不同宿主原生并发执行。
- WHEN 宿主 AI 产生 stage receipts 与逐对象 transaction facts。
- THEN quota、workUnitCount、对象 identity/eligibility 与显式 release cohort 相同；并发、elapsed、模型与会话数不写入业务 authority。
- THEN 仓库不保存宿主调度或容量 receipt，亦不据其自动推进或恢复。

<a id="gwt-010"></a>
### GWT-010 宿主中断不伪造阶段结论

- GIVEN 某 stage 已 OPEN 且宿主会话在 CLOSE 前中断。
- WHEN 新会话接手。
- THEN 新会话读取同一 OPEN exact inputs 并重做该 stage；代码不写假 verdict、next、deadline terminal 或 recovery state。
- THEN 已 CLOSE blocked 的 execution 不续跑，只能新建 execution；既有 receipts 与成功对象字节不变。

<a id="gwt-011"></a>
### GWT-011 AI 单写 stage verdict 与 typed issues

- GIVEN 一个 stage 无合格对象或 verifier 失败。
- WHEN AI 完成 POST 并调用 stage-close。
- THEN verdict、typed issues、result refs 与 verifier facts 由 AI 显式提交，内核仅重验并 create-once；不存在第二状态 writer。
- THEN pass 后继只按 Skill 固定顺序，receipt 不包含代码派生 nextAction/recovery stage。

<a id="gwt-016"></a>
### GWT-016 下游消费的数量与 entry surface × carrier 矩阵可闭环复核

> 本场景及 `GWT-026`、`GWT-028` 至 `GWT-033`、`GWT-035` 只验收下游 consumer/environment 行为，不构成 producer 准出；producer handoff 不拥有其中任何 sample、UAT、EAF、promotion 或 rollback 事实。

- GIVEN 一个已确认请求为 homepage/article/image/video 分别声明正整数对象数量，同一请求沿 producer 单轨形成 immutable Research release，且下游验收清单为 entry surface × carrier 二维矩阵。
- WHEN Alpha 依次完成 import、projection/API/media verify、activate，并由每个 required cell 的 repo-relative runner 执行 production Remote App UAT。
- THEN 每载体均满足 `selected = imported = projected = verified = readback = qualified`。`qualified >= requested` 表示该载体达标；`0 < qualified < requested` 表示 partial，`shortfall = requested - qualified`，已合格对象仍可见而不伪造成达标。
- THEN 16 个 cell 各自显式声明 `required|not_applicable`；required cell 具 repo-relative 验收锚点引用、runner 与绑定同一 release identity 的 raw `ReadinessCaseResult`，not_applicable cell 具可复核理由与验收锚点引用。carrier 与 entry surface 不互换，micro 不属于 carrier 轴。
- THEN import、projection 或 API/media verify 在 activate 前失败时 candidate 停在对应 typed 终态，previous active pointer 不变，且不生成本 candidate 的激活成功事实。
- THEN activate 后任一 required cell 失败时只记录 typed failed result；操作者显式执行 rollback 后，rollback/readback 必须证明四个 entry surfaces 全部恢复同一 previous release identity，`durationMs <= 300000`。超过预算、pointer 未恢复或任一 surface 混合 identity 时终态为 canonical `rollback_failed`，本次 raw 结果保持可读且旧 release/receipt 不得替代失败 cell。

<a id="gwt-020"></a>
### GWT-020 宿主 AI 九阶段沿 OPEN/DURING/POST/CLOSE 单轨闭合

- GIVEN 一个 identity-only candidate-backed execution 与 canonical Skill。
- WHEN 宿主 AI 依次执行 producer 九阶段，每阶段在 OPEN 点名 input refs，DURING 直接写业务产物，POST 逐条运行明确 verifier、完成 AI self-check 并提交 actor/verdict/typedIssues/resultRefs/verifierFacts，CLOSE 内核只重验并 create-once。
- THEN 不存在 stage-gate registry、semantic prepare/record、runner/fleet/lane claim、自动恢复、execution-state reducer 或代码派生 next；pass 后继只按 Skill 固定顺序，blocked 后新建 execution，OPEN 无 CLOSE重做同 stage。
- THEN candidate binding 只冻结目标对象身份；`sources` 选择来源，`1.download` 才生成 source units/source refs/bytes/CAS 与机械 hard facts，且不要求 `source.clean.md|source.layout.json|source.quality.json`；`2.quality` 判断语义与保留，`3.compose` 决定结构。
- THEN `4.draft` 每对象只写 `page.md|draft.article.md|image_work.json|video_script.json` 之一；sequence-006 receipt 冻结同一 execution 唯一真实 author actor/invocation、自检与 prompt/compose/draft exact refs/digests，不存在 draft meta/self-check/envelope 镜像产物。
- THEN `5.review` 由另一个真实 reviewer actor 会话执行，每对象只写 `content_review.json`，统一承载 `approved|rejected`、简短 dimensions/blockingIssues 与逐资产 rights 结论；sequence-007 receipt 冻结 reviewer actor/invocation 与 exact ref/digest，不存在 rubric/reviewer/media/attestation 镜像或独立 review receipt。author 与 reviewer 必须不同 session/runId，可为同一 model family。
- THEN approved/rejected 可混合；短缺由 stage result artifact/typed issue 表达且 receipt 仍为 `pass`，只有零 approved 或 stage-wide identity/integrity failure 才 `blocked`。
- THEN publish AI 对 approved 对象逐个调用单对象事务；release 消费 AI 显式 cohort/milestone 且禁止 all-publishable，并交付 release/cohort/content-pool exact refs/digests、四载体 counts、原 producer proofs 与 baseline revision；producer 随后固定到 `END`，环境消费不构成后继或完成条件。

<a id="gwt-022"></a>
### GWT-022 内容库唯一持有媒体且 release 只作分发物化

- GIVEN 一个 canonical transaction 引用 content library 中的 exact media binding，release build 需要物化其 distribution bytes。
- WHEN transaction apply、selection seal 与 release build 依次读取该媒体。
- THEN canonical/pool 只冻结 `objectKey`、`sha256`、`assetId` 与 library binding。
- THEN Git、execution output 与 release payload 均不登记为第二 canonical holder。
- THEN release materialization 的字节与 manifest digest 一致但只具 distribution 语义。
- THEN 删除 materialization 后只能从同一 content library binding 重建，不能从旧 release 反向修复 canonical。
- THEN selected 或 rebuild-prior 媒体在 content library 不可达、摘要不符或 binding 漂移时 transaction/build fail closed 且零部分 release 可见，不回退 Git 随体、public slice、fixture 或 staging。
- THEN 同一对象重放不增加 canonical holder。
- THEN content library exact bytes 不可达时，干净检出或 canonical 引用在场不得降级为可交付。
- THEN distribution materialization 与 manifest digest 对账失败时不得 activate，也不得覆盖 previous active。
- THEN 测试隔离只允许替换 content library adapter，不得把测试字节登记为生产 durability；测试结束后不得残留可被生产读取的 holder binding。

<a id="gwt-023"></a>
### GWT-023 homepage 与三载体均逐对象 publish

- GIVEN 一个冻结 homepage 载体、receipt 链已 `5.review` pass 的 execution。
- WHEN publish AI 对该 approved homepage 调用 canonical 单对象事务。
- THEN publish 分派到实体路径并给出逐对象发布判定，不再以「homepage 未接线」拒绝整个 execution。
- THEN 目标集来自 execution 内实际存在的实体对象，canonical ref 为 `domain/type/name`，无发表坐标投影；无实体对象时结构化失败。
- THEN `content_review.json` 为 rejected 的对象记为排除、缺冻结输入或 review identity/integrity 失败的对象记为阻断，两者语义不混用。
- THEN apply 模式下零对象晋级必须报错而非以成功报告收尾。

<a id="gwt-024"></a>
### GWT-024 candidate identity 与下载证据保持单一边界

- GIVEN 一个同时含 homepage/article/image/video identity-only candidates 的显式集合，task-init 前不存在 capsule/admission receipt。
- WHEN 构造 execution 输入并在 `sources` 与 `1.download` 形成来源计划和取得证据。
- THEN 每个 candidate 只携带对应目标对象身份、carrier、canonical coverage target 与 candidate identity；缺失、重复或摘要漂移在 task init fail closed，媒体候选不因缺少 pre-init source admission 被排除。
- THEN 每个 `1.download` source unit/source ref/CAS holding 绑定同一 target/candidate identity 与实际 bytes hard facts；来源或字节失败留在该 target 的 typed issue，不倒写 candidate，也不建立 capsule/admission 投影。
- THEN 显式输入构造与 identity/digest 漂移比对取自同一实现，任一处不得独立维护等价映射或新增 resolver/projector。
- THEN 本域契约判据的全部判据文件经交付门禁的分片矩阵执行，每个文件落进恰好一片；任一红片阻断汇总与候选 evidence，不以局部选择冒充全域覆盖。

<a id="gwt-025"></a>
### GWT-025 百科结构化信息区参与不可变事实取证

- GIVEN 一个百科来源，其票价、开放时间或官方网站只出现在结构化信息区，可见正文里没有对应表述。
- WHEN 为该实体准备 homepage 或 article 的 immutable source candidate。
- THEN 信息区里的受治理字段被解析为不可变结构化事实，该候选不再因缺少结构化事实被判短缺；多个受治理字段同时在场时按与可见正文一致的字段优先级取一条。
- THEN 字段名与取值语义不一致，或字段名不属于受治理集合时，该候选事实作废且不落入其它字段。
- THEN 信息区缺席时按可见正文的结论收敛，不因缺少信息区而额外失败。
- THEN 官方网站只接受安全传输协议地址，非安全地址视为无结构化事实。

<a id="gwt-026"></a>
### GWT-026 ship verify 隔离证据可复用且效度域受限

- GIVEN 同一 research release 在同一环境已有一次 PASS 的 isolation runtime proof，release 内容、manifest digest 与环境 runtime 策略快照均未变更。
- WHEN ship verify 以新 verify run 重入。
- THEN 最近一次 PASS proof 被复用并重绑目标 run，复用来源 run 标识写入证据本体，原 proof 文件字节不变；复用前 proof 全量重验（release 身份、manifest digest、policy 快照与 PASS 内容闭包）。
- THEN release 身份漂移、manifest digest 漂移、policy 快照漂移或 proof 观测时间超过 24 小时时效上限时拒绝复用，verify 收敛为 typed GATE_BLOCK 并要求重跑 isolation probe，被跳过候选不被修复或覆盖。

<a id="gwt-027"></a>
### GWT-027 载体字节预算单点声明且在下载截面完成判否

- GIVEN 一个 research lane 已声明的来源单元，其候选图片分别落在「预算内」「超预算但可降采样进预算」「超预算且每档都装不进」三种形态。
- WHEN 运行 `1.download` 截面的下载处置。
- THEN 预算内候选原样保留；可降采样候选被替换为第一个装进预算的已声明交付档，字节摘要、内容类型与像素几何按派生体重新登记，并在 funnel 里留下该派生记录。
- THEN 每档都装不进的候选在该截面即被判否，issue 为 `DATA.MEDIA.ASSET_OVER_BUDGET` 且点名该资产，funnel 丢弃原因为预算门；publish 期不再出现 `SINGLE_ASSET_OVER_BUDGET`。
- THEN 下载截面与 publish 截面对同一载体读到同一个预算值，且该值只能来自 `objectStorageBudgetBytesByCarrier`；任一侧不存在独立的预算常量。
- THEN research lane 缺席或落在闭集之外时该截面判否，不产生任何按默认预算放行的资产。
- THEN 一张 EXIF 声明 90° 旋转的横向全景图，其记录的宽高为显示几何而非存储栅格几何。

<a id="gwt-028"></a>
### GWT-028 Search 环境读回仅按 canonical operation 执行有界幂等重试

- GIVEN immutable release 的 Search 投影已完成，canonical `Search` operation 声明 `timeout_ms`、`retry_mode=idempotent` 与有限 `max_attempts`，首次读回返回 canonical Search 或 Gateway transport typed 错误及其 `retry` 恢复指令。
- WHEN environment release readiness 用同一不可变 Search request 核验目标 Post 或 Creator。
- THEN 每次物理请求受 `timeout_ms` 约束，全部尝试与 canonical 恢复等待共同受一个有限总 deadline 约束；恢复等待无法在剩余预算内完成时停止，不在 deadline 外补请求。
- THEN 尝试次数从 canonical operation contract 读取且不得超过 `max_attempts`；成功与失败 receipt 都以时序顺序保留每次 operation evidence，不用最后一次覆盖已发生的失败尝试。
- THEN `retry_mode` 非 `idempotent`、非 typed 错误、无 `retry` 恢复指令、4xx 或 HTTP 200 但目标缺席均不重试，不得把错误改写为合法空集。
- THEN 所有允许尝试均失败时，readiness 保留首次 typed blocker 的 canonical code、requestId 与 traceId，后续错误不得覆盖首因，也不得无限重试。

<a id="gwt-029"></a>
### GWT-029 六个运营视图只投影真实 owner facts

- GIVEN carrier demand/execution manifest/stage receipts、canonical object transaction/pool record、ContentRelease 与四环境 operation/acceptance facts 均已有 create-once evidence。
- WHEN 查询 `ContentProductionTaskView`、`ContentItemVersionView`、`EnvironmentReleaseOrderView`、`ReviewDecisionTimeline`、`ReleaseSelectionView` 与 `TargetAcceptanceView`，并重建 projection。
- THEN 六个 view 只由各自 owner refs/digests 确定性投影。
- THEN 六个 view 没有 command、Repository、checkpoint、独立 ledger 或 terminal writer。
- THEN 删除 projection 后重建结果逐字段相同且 owner bytes 不变。
- THEN `EnvironmentReleaseOrderView` 只读 Alpha/Beta/Gamma/Prod 四环境事实。
- THEN 缺环境、顺序冲突或 digest 漂移时返回 typed blocked。
- THEN typed blocked 不补写 acceptance，也不从环境名猜状态。
- THEN query 不以 projection cache 或最后一次成功值替代 owner refs/digests。

<a id="gwt-030"></a>
### GWT-030 EnvironmentAcceptanceFact 直接绑定 required raw UAT 结果

- GIVEN Data-owned `ReleaseUatSamplePlan` 已声明同一 release 的所有 required/not_applicable cell，Ops 已为该 target 的 required slots create-once `TargetUatBinding`，required runner 已分别产生 raw canonical `ReadinessCaseResult`。
- WHEN 构建该 target 的 `EnvironmentAcceptanceFact` 并执行完整性查询。
- THEN `EnvironmentAcceptanceFact` 直接列出全部 required raw refs 与 exact-byte digests；完整性查询只报告缺失、重复、跨 release 或漂移，不产生 verdict、promotion、write-back 或独立结果行。
- THEN 任一 required raw result 缺失/失败、digest 漂移、runner/验收锚点引用不匹配或 identity 不同，acceptance fail closed；counts、旧 receipt 与 projection cache 都不能代填。

<a id="gwt-031"></a>
### GWT-031 四入口对 deleted/offline/no-active 与 rollback 保持单义

- GIVEN feed、search、recommendation、direct/object route 读取同一 active release，分别构造对象 deleted、环境 offline、release retired 后无 active pointer，以及 candidate 失败后 rollback/replay 四种事实。
- WHEN 四入口执行 readback。
- THEN deleted 只由 canonical object owner 事实触发。
- THEN empty 或无 active release 保持 `no_active_release`/empty。
- THEN offline 保留 release/object identity 与 canonical recovery action。
- THEN retired 不直接成为 App wire，无 active pointer 时只呈现 `no_active_release`。
- THEN rollback/replay 后四入口全部返回 previous release identity。
- THEN 任一入口仍返回 failed candidate 时终态为 `rollback_failed`。
- THEN 任一入口混合新旧 identity 或只在 counts 上碰巧相等时终态为 `rollback_failed`。

<a id="gwt-032"></a>
### GWT-032 progressive private MP4 与 accessMode 在 Research 路径 fail closed

- GIVEN 有效 Research projection 含 progressive private MP4，媒体引用声明 `accessMode=signed_grant` 与稳定资产标识，另有字段缺失和 private HLS 负例。
- WHEN App 播放器发起初始请求、Range 请求并在当前位置收到首次 401/403。
- THEN 边缘逐 Range 重新验签；App 强制换签最多一次并从已确认位置恢复，二次 401/403 停在 typed terminal，播放位置不归零且不回退公开 URL。
- THEN 有效 Research/private 的 null/absent `accessMode` fail closed；只有显式 previous-version public contract version 可按 public 解释。private HLS 返回 unsupported typed terminal，不进入 MP4 fallback。

<a id="gwt-033"></a>
### GWT-033 future private HLS 按独立授权链可消费

- GIVEN 一份 future Research release 含 private HLS，媒体引用显式声明 access mode、稳定 asset identity，以及 manifest、segment 与 key 的授权边界。
- WHEN App 播放器请求 manifest、连续 segments 与 key，并跨授权 TTL 继续播放或恢复。
- THEN edge 对 manifest、每个 segment 与 key 分别执行受治理授权校验，未授权、过期或 identity 漂移均 fail closed。
- THEN TTL 过期后只沿 private HLS 的受治理换签路径恢复，保持已确认播放位置，不回退 progressive MP4 或 public URL。
- THEN 同一 release/asset identity 的 local contract、edge integration 与真实 App UAT 分别证明授权边界、过期恢复和可定位播放终态。

<a id="gwt-034"></a>
### GWT-034 四载体 producer 里程碑按累计唯一对象形成独立 handoff

- GIVEN 集中式架构禁令要求已退役编排、兼容读写和自动恢复在生产源码、schema、control plane、测试正例与 active specs 中物理归零；已有一组通过当前 Skill 生产并 finalized 的 canonical Travel Research 对象及其原 execution/publish proofs。
- WHEN 依次形成 M1、M10、M100、M1000，每级按 `cumulative_unique_finalized_objects` 选择 cohort、构建 immutable Research release 并物化 producer handoff。
- THEN 首次生产对象具完整九阶段 OPEN/CLOSE receipts、业务 result refs、verifier facts 与逐对象 publish proof；更高级别复用对象时原 execution/publish proof refs/digests 原样不变，不伪造新 execution 或新九阶段 receipts。
- THEN 每一级都有自己的 full explicit cohort、release identity 与 producer handoff，逐对象绑定 canonical identity 和原 producer proof；重复 identity 不增加累计值，新增唯一 finalized 对象使累计值分别达到该级下限。
- THEN producer handoff 不包含 `ReleaseUatSamplePlan`、sample authority、import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback facts；下游是否消费任一级 release 不参与本 GWT。
- THEN 此 GWT 只验收当前 Skill+AI Agent producer 架构；失败形成当前架构 typed blockers，不产生兼容或恢复旧轨的授权。

<a id="gwt-035"></a>
### GWT-035 environment promotion 与 API consumer 分支保持独立

- GIVEN 同一新架构后续需要 environment promotion。
- WHEN 下游环境 owner 使用 `acceptanceProfile=environment_promotion` 执行 ship。
- THEN target-bound App UAT raw facts、target binding、predecessor/promotion closure 按该分支显式闭合；`m1_api_consumer` 的 API facts 不冒充 App UAT，反之亦然。
- THEN promotion/规模验收不得回授旧控制面兼容 authority。

## 6. 依赖

- 前置要求：父能力的 execution、review 与 release 契约。
- 上游事实：来源、目标集和审核结果。
- 下游结果：immutable release 或结构化阻断报告。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-019"></a>
### OPEN-019 旧编排证据删除后的 producer 复合验收仍待重建

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前仍缺 identity-only candidate、宿主原生执行、中断重入、AI 单写 stage 语义、单一 draft/review artifact、content-library 后半段闭包、载体证据形态和百科结构化事实的现役 producer 验收证据；legacy-delete 删除的正向测试与历史 receipt 不得继续计数。
- 尚缺实现：无；本项不恢复已删除能力，只跟踪现役 producer 行为证据。
- 尚缺验收证据：上述 producer 行为均需由当前 Skill + AI Agent 路径重新绑定；Research 环境消费隔离、UAT 与 EAF 属下游 owner，不纳入本 OPEN。
- 完成判定：[`GWT-001`](#gwt-001)、[`GWT-009`](#gwt-009)、[`GWT-010`](#gwt-010)、[`GWT-011`](#gwt-011)、[`GWT-020`](#gwt-020)、[`GWT-022`](#gwt-022)、[`GWT-024`](#gwt-024) 与 [`GWT-025`](#gwt-025) 的 producer 子句由现役 local_contract/api_integration 逐条绑定；反向门禁本身不替代行为证据。
- 依赖：producer 只允许 task init/stage-open/close、atomic source/media I/O、机械 verifier、单对象 publish 与显式 cohort release；不得恢复已删除 API 补证据。

<a id="open-006"></a>
### OPEN-006 下游 M1→Alpha 消费 E2E 由环境 owner 独立跟踪

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：Alpha import/activate/readback、API/App UAT、EAF 与 rollback 仍可作为下游 release consumer 闭环，但它们不属于 content-production producer，也不阻断 producer release/handoff 完成。
- 保持禁令：旧 proof、fixture 或历史 receipt 均无新 execution authority；下游失败不得恢复兼容入口或回写 producer。
- 尚缺验收证据：若环境 owner 接手，需只读某个 immutable producer handoff 独立取得 Alpha consumer facts；不得要求 producer 创建 `ReleaseUatSamplePlan`、sample authority、EAF 或环境 receipt，也不得用环境证据代填 producer proof。
- 完成判定：由下游 owner 按 [`GWT-002`](#gwt-002) 与 [`GWT-035`](#gwt-035) 的有效消费验收证据关闭；本 Story 仅检查这些事实不进入 producer stage/result/handoff。`GWT-020`、`GWT-023` 与 `GWT-034` 的 producer 子句不依赖本 OPEN。
- 依赖：下游 Environment/Runtime/Service/App/Ops owner；无 producer 准出依赖。
- 遗留数据：旧 proof 或运行证据若因审计要求在仓外保留，只能离线只读，不得迁移为新 receipt、兼容接口或仓内正向引用。

<a id="open-012"></a>
### OPEN-012 新 OPEN/CLOSE 内核契约尚待实现验证

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：完整 OPEN/CLOSE 内核合同仍缺同一 revision 的零旧 import/reference 静态门与 targeted local_contract 联合验收；局部机制通过不得冒充 producer 九阶段闭环。删除旧 claim/runner/gate/reducer 行为测试；targeted local_contract 锁定 AI 点名 input refs 的 stage-open exact freeze、AI 显式 result/verifier facts 的 stage-close create-once、OPEN 无 CLOSE 重做，以及 blocked 后新 execution。
- 当前证据：stage-open/stage-close targeted local_contract 已绑定 [`GWT-020.t1`](#gwt-020) 与 [`GWT-020.t2`](#gwt-020) 的内核行为；这只证明局部机制，不等于 producer 九阶段/publish/release handoff 或下游环境消费的 fresh 复合 E2E。
- 状态语义：本项仅声明删除后的实现与证据要求，不表示一组局部测试已经证明完整执行闭环。不得保留旧实现作为过渡兼容。
- 完成判定：[`GWT-020.t1`](#gwt-020) 与 [`GWT-020.t2`](#gwt-020) 的 targeted local_contract 和零旧 import/reference 静态门在同一 revision 上均实际通过；producer 复合 E2E 由 [`OPEN-020`](#open-020) 跟踪，下游消费证据另由 [`OPEN-006`](#open-006) 跟踪。

<a id="open-020"></a>
### OPEN-020 producer 九阶段与累计里程碑 release handoff 证据待取得

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：authoring contract 已硬切，但仍需真实 Travel Research producer execution 证明 identity-only candidate、单一 draft/review artifact、逐对象 publish、累计 cohort release 与 terminal handoff 端到端成立。
- 已冻结语义：producer sequence 固定止于 sequence 009 `release` 并拒绝消费阶段；candidate binding 不要求 pre-init source admission；sequence-006/007 receipts 分别冻结 execution 级唯一 author/reviewer actor 与 invocation；`4.draft`/`5.review` 每对象各一份业务产物；approved/rejected 可混合且短缺不扩展 receipt verdict。
- 里程碑语义：M1/M10/M100/M1000 按 `cumulative_unique_finalized_objects` 计数，每级形成自己的 full explicit cohort、release 与 handoff；更高级别复用 canonical 对象及其原 execution/publish proof，不伪造新九阶段 receipts。任何旧 schema 字面上的额外 milestone 不扩大本 OPEN 的验收闭集。
- handoff 边界：handoff 严格绑定 release/cohort、排序 execution IDs、sequence-009 receipts、四载体 counts、逐对象 content-pool query、原 producer proofs、`producerBaselineRevision` 与 create-once identity；不包含 UAT sample authority、import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback facts。
- 尚缺验收证据：尚未取得一轮符合硬切后产物/actor 语义的真实 M1 producer E2E，也未证明后续规模级别复用原 proof 且按累计唯一对象形成独立 release/handoff。局部 schema/local_contract/静态 gate PASS 不替代此证据。
- 完成判定：[`GWT-020`](#gwt-020) 全部 producer 子句与 [`GWT-034`](#gwt-034) 由同一条可追溯 producer proof 链通过；M1 证明首次对象生产，后续各级证明累计唯一对象、原 proof 复用与独立 cohort/release/handoff。下游 Alpha 不参与关闭。
- 依赖：真实 provider、一个真实 author actor 会话、另一个真实 reviewer actor 会话、canonical publish 与 release/handoff；环境 CLI/实现不在依赖中。

<a id="open-015"></a>
### OPEN-015 progressive private MP4 只缺 fresh App UAT

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：只缺同一 runtime generation 的 fresh production Remote App UAT。Research 私有媒体的设计与实现已就位。progressive private MP4、图片/头像/对象主页/文章资产的 typed `accessMode` 分流、单飞短签、稳定资产缓存身份、Range 边缘逐请求复验，以及首次 401/403 强制换签最多一次并保持播放位置均已实现。二次失败 typed terminal 且不回退公开 URL。private HLS 不属于本 OPEN 的未完成实现，保持 unsupported/fail closed，并由 [`OPEN-017`](#open-017) 单独承接。
- 尚缺实现：无。有效 Research/private projection 的 `accessMode` 与稳定资产标识为必填；仅明确 previous-version public contract version 可把 null/absent 解释为 public，Research/private 缺失保持 fail closed。
- 尚缺验收证据：缺一轮绑定同一 Gamma `ReleaseUatSamplePlan`、registered physical-device `TargetUatBinding`、target/release/runtime generation 的 fresh `user_acceptance`：entry surface × carrier 矩阵全部 required cells 产生 raw `ReadinessCaseResult`，progressive private MP4 覆盖 Range 续播与一次 401/403 换签恢复，`EnvironmentAcceptanceFact` 直接绑定 required raw refs/exact-byte digests；旧公开 URL 断言、旧 receipt 或完整性 projection 不能替代。
- 完成判定：[`GWT-016`](#gwt-016)、[`GWT-030`](#gwt-030)、[`GWT-032`](#gwt-032) 的 local_contract/api_integration 前置证据均通过，并由 production Remote runner 取得上述 fresh raw UAT facts；除 fresh UAT 外不得再把已实现能力列为本 OPEN 的实现缺口。
- 依赖：Testing/Ops owner 负责 fresh runner、`TargetUatBinding` 与 `EnvironmentAcceptanceFact` 绑定；App/Service/Runtime owner 只需保持现有 `accessMode`、资产标识、Range 验签和单次换签字段/行为不漂移。private HLS 能力不阻断 progressive private MP4 验收。

<a id="open-016"></a>
### OPEN-016 超尺寸资产的 provider 无关性尚缺真实 provider 证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺真实 provider 上的观测。[`REQ-012`](#req-012) 的预算判否已在 `1.download` 截面成立并由 `local_contract` 覆盖，但覆盖用的超尺寸源体是本地编码构造的。`pageImageRenditionWidth` 的服务端缩略图偏好只命中 `upload.wikimedia.org` 的 commons 非 thumb 路径，因此「与 provider 无关」这一条在 `pinterest`、`tuchong`、`openverse` 上仍只有推断而无观测。
- 尚缺验收证据：一个 `api_integration` 以真实非 Wikimedia provider 的超尺寸资产走完 `1.download`，证明判否与降采样都不依赖服务端缩略图路径的存在。
- 完成判定：[`GWT-027`](#gwt-027) 的降采样与判否两条结果子句在至少一个无服务端缩略图路径的真实 provider 上有 `api_integration` 证据。
- 依赖：无外部阻断；预算声明位与判否边界已由 [`REQ-012`](#req-012) 冻结。

<a id="open-017"></a>
### OPEN-017 Research private HLS 尚未设计与实现

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺 private HLS 对 manifest/segment/key 授权、换签与播放位置恢复的独立设计；当前 contract 明确返回 unsupported typed terminal 并 fail closed，不回退 progressive MP4 或 public URL。该缺口不改变 progressive private MP4 已实现事实，也不阻断 [`OPEN-015`](#open-015) 的 fresh UAT。
- 尚缺实现：Service/Runtime/App owner 需冻结 private HLS 的资产/segment authority、边缘验签、TTL 过期恢复、缓存身份、失败终态与播放器接入；在设计完成前不得接入生产 Research release。
- 尚缺验收证据：local_contract 覆盖 manifest/segment/key authority 与 fail-closed，api_integration 覆盖边缘逐段授权和过期恢复，user_acceptance 覆盖不中断或可定位恢复的真实 private HLS 播放。
- 完成判定：[`GWT-033.t1`](#gwt-033)、[`GWT-033.t2`](#gwt-033) 与 [`GWT-033.t3`](#gwt-033) 对应 future private HLS 的独立设计决定与 canonical contracts 落地，private HLS 不再返回 [`GWT-032.t4`](#gwt-032) 的 unsupported terminal，且 local_contract/api_integration/user_acceptance 三层证据绑定同一 release/asset identity；完成前 current unsupported terminal 保持不变。
- 依赖：Service media contract、edge verifier、Runtime release projection 与 App player owner 联合接手；不得复用或放宽 progressive MP4 的单 URL 假设。

<a id="open-018"></a>
### OPEN-018 运营 projection 与四入口 identity 语义尚缺 runtime 闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺六个运营 view 的 projection-only composition，以及 feed/search/recommendation/direct-or-object-route 对 deleted/offline/no-active/retired/rollback-replay 的同 identity runtime 闭环。规格已冻结 owner 与禁止写回边界，但不得据此声称实现已支持。
- 尚缺实现：Runtime/Data/Service owner 需让六个 view 只从现役 carrier demand/execution manifest/stage receipts、canonical object transaction/pool record、ContentRelease 与 per-environment operation/acceptance facts 投影，并移除或拒绝任何 command、Repository、checkpoint、独立 ledger；四入口需显式携带/读回 active 或 previous release identity，retired 保持治理态而不进入 App wire。
- 尚缺验收证据：[`GWT-029.t1`](#gwt-029) 至 [`GWT-029.t7`](#gwt-029) 尚无任何子句级 local_contract 或 api_integration；[`GWT-031.t1`](#gwt-031) 至 [`GWT-031.t7`](#gwt-031) 尚无任何子句级 local_contract、四入口 release identity api_integration 或 rollback/replay user_acceptance。
- 完成判定：[`GWT-029.t1`](#gwt-029) 至 [`GWT-029.t7`](#gwt-029) 逐条由有效 contracts 的 local_contract/api_integration 绑定，且 projection 删除重建不改 owner bytes；[`GWT-031.t1`](#gwt-031) 至 [`GWT-031.t7`](#gwt-031) 逐条由同一 release identity 的 local_contract/api_integration/user_acceptance 绑定，且四入口 rollback/replay 后 previous release identity 一致率为 100%。
- 依赖：Runtime/Data/Service owner 冻结并实现字段与 query 事实；Testing/Ops owner 提供四入口真实 runner。不得以 projection cache、counts、旧 receipt 或页面文案关闭本 OPEN。
