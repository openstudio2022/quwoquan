# L3 Story：多载体内容与主页发布 (`multi-carrier-release`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-008 / SCN-014`](../../../spec.md#scn-014)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容运营者，我希望文章、图片、视频和主页对象以独立 execution 分别调度和生产，共享冻结实体目录与 release 边界，合格对象经 immutable release 分发到四环境并被 App 各 surface 消费，从而能分别恢复失败并复核来源、媒体、实体与环境消费是否闭合。

## 2. 范围与非目标

### In Scope

- 四个 carrier execution 共享不含运行身份的 canonical entity catalog digest，各自冻结 target set、quota 与终态。
- 各载体复用同一创建、审核、promotion 和 ship 生命周期。
- Research 与 Commercial 共用 acquisition、semantic、review 和 canonical pool；只在 immutable release build 时按逐对象 `usageScope` 与全部 entity/post 资产的商用权利闭包选择不同子集，不建立第二套 commercial workflow、pool 或 semantic queue。
- 批次级/跨载体聚合门只作目标与统计；四载体共用 acquisition/rights/distribution admission，research 只放宽未验证的分发权利，不放宽访问控制、内容安全、隐私、未成年人、恶意文件、去重、实体相关性、质量或可播放性。
- 经确认的请求只由宿主 Cursor/Codex IDE/CLI Agent 直接执行 canonical content-production Skill；candidate-backed 工作包、十阶段 receipt、reviewed delivery、canonical pool、immutable release、环境 import/activate/readback 与 raw `ReadinessCaseResult` 单轨推进，任一步失败停在可恢复的 typed 终态。

### Out of Scope

- 按需意图 preview 与 envelope 编译（归 [`work-request-compilation`](../work-request-compilation/spec.md)）。
- article 来源预筛、media workUnit 与 canonical 池唯一写路径（归 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md)）。
- 来源发现阶段的有界并发调度与运行中存活心跳（归 [`source-discovery-scale-reliability`](../source-discovery-scale-reliability/spec.md)）。
- invalid canonical identity 的修复裁决（归 [`canonical-content-identity-recovery`](../canonical-content-identity-recovery/spec.md)）。
- 为不同地区或载体维护第二套发布目录与运行台账。
- 绕过登录、付费墙、验证码、访问控制、DRM 或平台技术限制取得素材。
- 直接生成图片或视频，或将 deterministic image-sequence 冒充已取得的可播放视频。
- 改变 homepage、image 或 video 既有的供给与来源判定机制：image/video 继续由 immutable acquisition manifest/receipt 的 exact pair 冻结 workUnit（见 `REQ-001` 与 [`on-demand-content-pool-admission` GWT-003](../on-demand-content-pool-admission/spec.md#gwt-003)）。
- 冻结期多样性准入的每实体累计上限与 Top-N 上限数值：阈值由多样性策略的既有 owner 单点拥有，本 Story 只消费其准入结论，并约束该结论的归属、呈现与批次级零合格归因。
- 将 Data 的 `homepage` carrier 解释为 App micro，或把 carrier 轴与 App 入口面轴混称为“四 surface”。carrier 闭集固定为 `homepage|article|image|video`；entry surface 闭集固定为 `feed|search|recommendation|direct_or_object_route`，验收按二维矩阵声明。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多载体宿主 execution 与 pool→release 单轨

- 每个发布对象必须闭合 creator、tag、entity、media、source、rights 与 independent review；运行 receipt 只能写入 execution/output，不回写静态真相源。
- homepage、article、image、video 共享 canonical entity catalog，但各自拥有 candidate-backed immutable execution。唯一推进主体是直接执行 `.agents/skills/content-production/SKILL.md` 的宿主 Cursor/Codex IDE/CLI Agent；新任务不得调用仓内 Cursor/Codex SDK/provider agent/controller/queue/campaign/recovery、`task execute`（含 plan-only）或 pool-dispatch。
- candidate-backed work package 只由已实现的中性 `task init` 原子创建；它只写 `execution_manifest.json`、`0.plan/request.json`、`0.plan/target_set.json` 且零 stage 副作用。宿主随后严格推进 `0.plan -> sources -> 1.download -> 2.quality -> 3.compose -> 4.draft -> 5.review -> publish -> release -> ship`；每阶段先由 `task stage-open` 冻结 authority，再由 `task stage-gate` 执行 canonical machine gate，最后只由 `task stage-close` 派生 verdict/next 并写 create-once authority-bound receipt。
- 两个薄 runner 只负责启动/结束宿主进程、只读 receipt 与有限基础设施退避；不得选择 candidate、解释业务终态、调用 semantic provider、写 pool/release/environment 或建立 campaign/fleet 业务身份。active execution 可串行或重叠，固定并发、workspace smoke、capacity soak、calibration receipt 与 provider/model preflight 均不是 dispatch、对象准入或 promotion 前置。
- 单载体失败不得覆盖其它工作包，也不得阻止其它载体已合格对象入池。`quota` 是目标下限；`partial` 必须保留全部已合格对象并写 typed shortfall，零合格才 blocked。每个实际启动对象/阶段必须有 typed terminal，排队与诊断观测不得冒充结果。
- accepted independent review 后只生成 reviewed delivery intent，并经 drain → canonical 单对象事务追加。canonical object package + append-only pool record 是 producer→consumer 唯一持久交接事实；release owner 只读字段白名单 handoff query projection。SourcePool、execution/campaign/provider/model、semantic journal 与宿主 session 不进入 consumer identity、eligibility、release cohort 或 App DTO。
- release selection 只接受显式 create-once pool record、完整 admission/rights/sourceAttribution/content-library binding 与 canonical identity。逐对象失败只排除该对象，成功对象继续。content library 是媒体字节唯一 holder，release 只作 distribution materialization。
- 每个 lane 的 `approvedQuota`、candidate count 与 workUnitCount 三值分离；宿主 fleet 并发只是 runner 参数，不进入三值或对象判据。吞吐、成本、模型/provider 与实际重叠只作为事后诊断统计。
- article/image/video Post manifest 必须显式 `contentIdentity=work`；新增对象必须有稳定 `contentId`、递增 `version`、`sourceType=data`、`variantPurpose`、`admission`、`usageScope` 与 `status`，只有 `completed + passed + active` 可被 release 选择。


<a id="req-002"></a>
### REQ-002 生命周期与统一素材 admission

- acquisition、semantic、review、canonical pool 与全局运行配置均不声明或推断 lifecycle/class。每次 immutable release build 必须显式选择 `research|commercial`，并在 create-once release header/attestation/activation 中冻结同值 `releaseClass/productLifecycleState`；环境名、临时环境变量或 fixture 不得推断该状态。
- 每个实体头像/主页媒体、文章图、图片作品与视频资产都必须记录 `acquisitionStatus`、`rightsStatus=verified|unverified|restricted|unknown`、`authorizationRequired`、`distributionDecision=research_allowed|commercial_allowed|blocked` 以及 `sourceUrl/platform/creator/capturedAt/contentSha256/license/termsUrl/authorizationProof/rightsIssues`。
- `research` 允许已取得且权利状态为 verified/unverified/unknown 的资产，restricted、未取得、生成素材或缺来源/权利缺口字段仍阻断；`commercial` 只允许 verified 且具有商业授权证据的 `commercial_allowed`。
- research immutable release 必须冻结权利状态计数、精确 authorization-required asset IDs、四载体 `researchAcceptedCount`、逐来源 assets funnel 和 `containsUnverifiedAssets`；未授权资产不得计入 `commercialAcceptedCount` 或生成 commercial readiness。

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

<a id="req-004"></a>
### REQ-004 M100 Gamma E2E acceptance 与 M1000 零副作用 start gate

- Research activation 继续服从 Alpha→Beta→Gamma→Prod authority：每个环境独立 create-once activation/readiness/acceptance facts，后继环境在首个 mutation 前绑定前驱 `EnvironmentAcceptanceFact` exact bytes。Commercial 是另一个显式授权 release，不由环境名推导。
- 目标增量 M100 exact release 的 carrier profile 固定为 homepage/article/image/video=`100/100/100/10`。release owner 从 eligible pool 按冻结排序 exact 选择 deterministic cohort；累计 overshoot 保持入池但不扩大该 release。四载体 exact count、对象 identity/version、pool digest 与 source identity set 全部进入 release digest。
- M100 目标增量硬终点是：完成必要 Alpha/Beta 前序后，同一 Research release 在 Gamma 完成 import、API/media readback、private isolation、activation，Ops 将 candidate/package/config/provider 与已注册真实物理设备写入 `TargetUatBinding`，entry surface × carrier required cells 各自产生 fresh raw `ReadinessCaseResult`，最终 append Gamma `EnvironmentAcceptanceFact`。Prod activation、Commercial transition 与商业验收均 out of scope，不得替代或阻断该终点。
- 在 Gamma acceptance exact-byte closure 成立前，M1000 的 source discovery、acquisition、semantic、review、work package init、pool append 与其它生产副作用增量必须为 0；只允许 `ContentPoolHandoffQuery`/gap/candidate readiness 等只读查询。不得让 M1000 与 M100 acceptance 并行。
- gate 通过后，目标增量 M1000 只允许选择第一个 immutable candidate-backed slot，经中性 `task init` 后由宿主 Agent 推进到 `0.plan` pass、`next=sources` 即停止；不要求开始 sources，更不要求 M1000 全量 production/release/UAT。
- `ReleaseUatSamplePlan` 环境无关地冻结 M100 release 的 required cells 与 sample；`TargetUatBinding` 逐 target 绑定真实运行 tuple；raw `ReadinessCaseResult` 是唯一 UAT 结果事实；`EnvironmentAcceptanceFact` 直接绑定全部 required raw exact bytes。bundle、counts、旧 receipt、workflow success 或 projection verdict 均无晋级权。
- 任一 Gamma import/readback/UAT/device binding/acceptance 失败都保持 previous active，并按 environment owner 追加 rollback/readback facts；M1000 继续零副作用。M1000 首 slot init/0.plan 失败只保留自身 typed blocker，不改写 M100 acceptance。


<a id="req-005"></a>
### REQ-005 既存 reviewed closure 只作为只读迁移输入

- 既存 reviewed closure 只能由显式 adoption/migration command 精确绑定原 immutable tuple 与 review/rights closure，生成新的宿主 execution/canonical version；不得恢复 campaign 入口、改写旧 payload 或绕过 reviewed delivery/pool transaction。
- identity collision 必须先以 append-only incident 保留全部观测 bytes；任一 ref/digest 漂移 fail closed。


<a id="req-006"></a>
### REQ-006 宿主并发与运行观测不构成业务 authority

- `loop_driver.sh` 和 `fleet_dispatcher.sh` 是唯一允许保留的无业务判断薄 runner；并发上限只来自显式 runner 参数，且只约束同时启动的宿主执行器数。
- 新任务不得读取或生成 managed scheduler、ReliableTask fleet、capacity bootstrap/calibration、workspace/soak 或 provider/model preflight 来授权 execution、candidate、对象准入或 milestone。旧 wire/代码仅作为待退役存量，不是合法入口；其物理删除只能由 [`GWT-034`](#gwt-034) 的 current exact-evidence precheck 授权，删除后的 inventory=`retired` 只能在 post-delete gates 全部通过后写入。
- 每个 execution 与对象仍按 receipt 写真实 stage terminal；runner crash、宿主限流或 deadline 只停止未启动工作，不撤销已完成 review、pool record、release 或 acceptance facts。
- 运行报告可记录 execution 数、stage 分布、blocked code、elapsed 与实际宿主并行度；这些字段只用于人工评估后续 `--max-parallel`，不得自动回写业务配置或改变同一输入的对象结果。
- `qualified == 0` 必须携带单一 typed 原因、观测阶段、next action 与 evidence refs；该事实由观测 stage receipt 单写，release/pool/fleet view 只读投影，不建立 lane/campaign/fleet 多层枚举。


<a id="req-007"></a>
### REQ-007 confirmed demand 沿宿主十阶段推进到 Gamma acceptance

- 完整路径固定为 `confirmed handoff -> WorkRequest/carrier demand -> candidate-backed task init -> 宿主 Agent 十阶段 -> reviewed delivery -> canonical object package + pool record -> immutable M100 release -> Alpha/Beta 前序 -> Gamma import/readback/activate -> registered physical-device raw ReadinessCaseResult -> Gamma EnvironmentAcceptanceFact`。
- `task init` 的 deterministic 三文件原子初始化已实现并由 local contract 锁定；尚缺的是同一 confirmed demand 的真实宿主消费证据，由 [`work-request-compilation` OPEN-001](../work-request-compilation/spec.md#open-001) 跟踪。不得回退 `task execute`、pool-dispatch/campaign 或手写工作包；每一步只消费前一步 immutable ref/digest，失败不得跳阶或用旧 receipt 冒充当前完成。
- ship pass 仍是 execution `succeeded` 的唯一 writer；Gamma acceptance 与 M1000 start gate 是 release/environment 事实，均不得回写或重开 execution terminal。


<a id="req-008"></a>
### REQ-008 生产与发布之间的只读交接判据

- producer→release handoff 的完成判据是字段白名单 `ContentPoolHandoffQuery` 的全部判据通过，不是生产运行统计或 `pool-inspect` 的宽松 publishable 计数。`pool-inspect` 的 post 侧 publishable 不运行引用闭包、媒体 CAS 与物理字节一致性、rights snapshot 与跨 post 媒体冲突判定，milestone 选择器自报的 publishable 也在任何对象进入闭包前就完成计数，两者都会高于真实可选中数。
- `ContentPoolHandoffQuery`、`release pool-precheck` 与 pool inspection 全程只读，必须复用 `pool-build` 的同一判据链且不写 release、`SelectedSet`、`SelectionSeal`、checkpoint 或任何独立 ledger；它们只返回本次查询的候选、排除与 digest。SourcePool、execution/campaign/provider/model 字段不在 projection 白名单。
- `SelectedSet` 与 `SelectionSeal` 是 `ContentRelease` owner 的 create-once 技术 evidence，不是业务对象。它们只能由独立 seal/finalize 边界或 `pool-build` 的原子 PRE 在 release identity 已冻结后产生；precheck 不得写入、补齐或升级这些 evidence。build 必须重算并验证 selection digest，seal 漂移即 fail closed。
- 预检必须区分「经完整判据链得出」与「全池被拒后逐对象重放得出」两种排除来源，并为每个被排除对象给出 typed code。判定为不通过是结构化结论，不是预检自身失败。
- canonical 不变式：canonical 对象只存 `objectKey`、`sha256` 与 `assetId` 私有 CAS 引用，禁止写入 `publicSliceKey`。公共切片键只能是 release 构建期派生物，使已入池对象在媒体交付形态变化时可原地复用。

<a id="req-009"></a>
### REQ-009 内容库是媒体字节唯一 canonical holder

- content library 是 canonical 对象引用媒体字节的唯一 holder、durability owner 与 recovery source；canonical object transaction/pool record 只冻结 `objectKey`、`sha256`、`assetId` 与 library binding，不在 Git、execution output、release 或环境根建立第二份 canonical 字节归属。
- release 内媒体字节只是从 content library 派生并由 manifest digest 约束的 distribution materialization，用于目标环境交付；它不是第二 holder、durability 副本或 canonical recovery source。materialization 丢失时只能从同一 content library binding 重建，不得反向把 release bytes 提升为 canonical。
- publish、selection seal 与 release build 在读取 selected 或 rebuild-prior 媒体时，只要 content library 中 exact bytes 不可达、摘要不符或 binding 漂移就 fail closed。禁止回退到 Git 随体、旧 release、公共切片、测试 fixture 或 execution staging 补字节。
- 干净检出只证明 schema 与引用契约可复核，不证明媒体 durable；准出必须以 content library exact-byte readback 与本次 distribution materialization 对账为证据，任一缺失不得降级为告警。

<a id="req-010"></a>
### REQ-010 homepage 与三个 post 载体共享同一份准入判据

- homepage 走 receipt 协议 publish 的同一条链：receipt chain `5.review` pass、布局可发布、对象 attestation approved，之后经实体事务进入 canonical `entities/`。禁止为 homepage 建立第二套准入判据。
- homepage 的对象身份是实体路径 `domain/type/name`，没有 `publishAngle`/`publishTitle`/`publishSeq` 这组发表坐标，因此目标集来自 execution 工作包内实际存在的实体对象，而不是 frozen target set 的投影；实体类型冲突是结构化错误而非静默去重。
- homepage 缺位会让 article 永久卡在引用闭包：article 可以先进池，但其 publishable 要求 `entityRefs` 指向的 homepage 已 admitted。因此 homepage 必须先行或与 article 同批。
- apply 模式下零对象晋级必须报错，不得以「promoted=0」的成功报告收尾。

<a id="req-011"></a>
### REQ-011 候选的物理证据引用按载体二分，投影只有一份

- homepage/article 候选的物理证据是 source-ready capsule 套件，image/video 候选的物理证据是一份 media source admission receipt。两种形态互斥：池契约禁止媒体候选携带套件字段，也禁止 capsule 候选携带 admission 指针。
- 因此「候选的物理证据引用」是按载体解析的一个位置，不是一个固定键名。向全部载体索取 `sourceUnitRef` 会读到一个按契约缺席的键，其后果不是报错而是媒体载体整体退出编排——波次投影一路无声通过，直到绑定期才以 shortfall 出现，且现场已不指向缺失的那一步。
- 该投影只允许有一份实现：波次输入的构造与其后的漂移比对必须调用同一个函数。两处各写一份等价映射时，任何一处新增载体都会让另一处把正确的候选判成漂移。
- receipt 冻结铸出时的来源身份，因此引用它的候选必须与 receipt 同身份、同对象形态；测试装置自造候选时同样要真实铸出 receipt，只写指针的候选在计划构造期无声通过。

<a id="req-012"></a>
### REQ-012 逐载体对象字节预算只有一处声明，判否在下载截面完成

- 逐载体单对象存储预算的数值是本 Story 的规格事实，唯一声明位为 `quwoquan_data/control_plane/_shared/media_processing.policy.yaml` 的 `objectStorageBudgetBytesByCarrier`。取值优先级固定为「具名载体档 → `default` 档」，两档都写在该文件内，因此任一生效值都能指回一处写下它的文件；`default` 缺席在 policy 装配期判否。下载截面与 publish 截面都经同一派生点取值，禁止任一侧另立常量或另设更宽的放行值。
- 「资产必须装进其载体的发布预算」是下载决策截面的不变量，与 [`DEC-029`](../design.md#dec-029) 在 `1.download` 一次冻结处置的边界同源。载体由来源单元自己声明的 research lane 决定；lane 缺席或落在闭集之外时该截面判否，不替它挑一个载体，因而也不替它挑一个预算。
- 超预算候选在该截面就地收敛：先按已声明交付档自宽到窄降采样，取第一个装进预算的档并按新字节身份重登记摘要与内容类型；每档都装不进、或派生体反而跌破像素门时给出 `DATA.MEDIA.ASSET_OVER_BUDGET` 并点名该资产。禁止把判否推迟到 publish——落在放行值与预算之间的资产会走完 `2.quality`→`5.review` 全部创作与评审成本，且一个超尺寸 homepage hero 会连带让引用该实体的已完成 article 因引用闭包不成立被 `DATA.POOL.REFERENCE_MISSING` 长期排除。
- 该不变量与 provider 无关：`pageImageRenditionWidth` 的服务端缩略图偏好只覆盖 `upload.wikimedia.org` 的 commons 非 thumb 路径，`pinterest`、`tuchong`、`openverse` 都没有对应路径，因此它是尽力而为的优选而不是预算不变量的实现手段。
- `sourceAssetMaxBytes` 是单次抓取的传输上限而不是准入判据：它只回答「愿意为一个候选花多少带宽」。源体允许大于对象预算，因为降采样需要先拿到源体。
- 资产的像素几何按交付端呈现的方向记录。EXIF Orientation 声明 90° 旋转时存储栅格的宽高与显示宽高互换，只读存储栅格会把一张横向全景图记成极端竖图，并使相关性判定、封面候选、有效交付宽度与字节预算全部按转置后的几何得出结论。重编码会丢弃 EXIF，因此派生体必须先旋转再编码。

<a id="req-013"></a>
### REQ-013 运营读模型只作 projection/query view

- `ContentProductionTaskView`、`ContentItemVersionView`、`EnvironmentReleaseOrderView`、`ReviewDecisionTimeline`、`ReleaseSelectionView` 与 `TargetAcceptanceView` 均为无写权限的 projection/query view，不拥有 command、Repository、checkpoint、独立 ledger 或生命周期终态。
- `ContentProductionTaskView` 只投影 WorkRequest/Execution。`ContentItemVersionView` 只投影 canonical object transaction/pool record。`ReviewDecisionTimeline` 只投影上述 owner 已绑定的 review facts。`ReleaseSelectionView` 只投影 `ContentRelease` 及其 selection evidence。`TargetAcceptanceView` 只投影 per-environment operation/acceptance facts。`EnvironmentReleaseOrderView` 只读 Alpha/Beta/Gamma/Prod 四环境事实并排序，不推导、补写或推进任何环境状态。
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

- 有效 Research projection 的每条媒体引用都必须携带 `accessMode` 与稳定媒体资产标识；`accessMode` 为 null/absent 只允许由明确声明的 legacy-public contract version 解释为 public。有效 Research/private projection 缺失该字段必须 fail closed，禁止按 URL、CAS key、环境名或字段缺席推断 public。
- progressive private MP4 通过已校验短签 URL 播放；边缘对每个 Range 请求重新验签。首次 401/403 只允许强制换签一次并从已确认播放位置恢复，二次失败停在 typed terminal，不循环、不回退公开 URL。
- private HLS 当前为 unsupported typed terminal 并 fail closed；它不得进入 progressive MP4 fallback，也不得阻断 progressive MP4 的 fresh UAT。其设计、实现与独立 UAT 由 [`OPEN-017`](#open-017) 承接。

## 4. 契约引用

- media processing policy：`quwoquan_data/schema/content/media_processing_policy.schema.json`
- release：`quwoquan_data/schema/release/release_header.schema.json`
- asset admission：`quwoquan_data/schema/release/release_asset_admission.schema.json`
- lifecycle policy：`quwoquan_data/schema/governance/content_distribution_policy.schema.json`
- environment readiness：`quwoquan_data/schema/release/environment_release_readiness.schema.json`
- research scale promotion：`quwoquan_data/schema/release/research_scale_promotion.schema.json`
- commercial transition：`quwoquan_data/schema/release/commercial_transition.schema.json`
- ship：`quwoquan_data/schema/release/ship_report.schema.json`
- 零合格原因共享值对象：`quwoquan_data/schema/_common/zero_qualified_reason.schema.json`
- 零合格不可续跑判定依据：`quwoquan_data/schema/execution/zero_qualified_basis_evidence.schema.json`
- reviewed closure adoption ref：`quwoquan_data/schema/execution/reviewed_closure_adoption_ref.schema.json`
- reviewed closure adoption receipt：`quwoquan_data/schema/execution/reviewed_closure_adoption_receipt.schema.json`
- release identity incident：`quwoquan_data/schema/release/release_identity_incident.schema.json`
- media workload object：`quwoquan_data/schema/execution/media_work_unit.schema.json`
- stage receipt：`quwoquan_data/schema/execution/stage_receipt.schema.json`
- canonical pool record：`quwoquan_data/schema/release/pool_object_record.schema.json`
- UAT matrix cell binding：契约字段 `required|not_applicable`、repo-relative `spec_ref`、`runner`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 独立载体分别调度且引用闭包后才允许 promotion

- GIVEN homepage、article、image、video 各有一个 immutable execution，并共享同一 named main branch、commit、source digest 与 entity catalog digest。
- WHEN 四个 execution 按可用容量分别调度，可串行或重叠生产，且操作者请求聚合并 promotion release。
- THEN post 不等待 homepage execution 或 publish，任一载体失败只保留在自身 evidence，其他载体已合格对象仍可 publish。
- THEN 仅从 entity identity、creator、tag、source 与媒体处置全部闭合的 approved 对象中选择 immutable cohort；悬挂引用只排除对应对象，足量有效 cohort 仍可 promotion。
- THEN 实际发生的 review 调度与时间重叠如实记录；零重叠不阻断 dispatch、publish 或 promotion。任一 lane 的 publish 不得早于该 lane 自身 review 终态，但不得等待其他 lane 的 review/publish 终态。
- THEN 某 lane `0 < qualified < quota` 时终态为 `partial`，已合格对象已 finalize，shortfall 有 typed evidence；`qualified == 0` 时该 lane 为 `blocked`。
- THEN 全批次零 discard 仍允许成功终态；若存在 discard，则每个 discard 必须有非空 `objectRef` 与 typed `issues`。
- THEN mismatch、submission collision、主工作树 drift 或等待 timeout 留下 blocked report。
- THEN lane 级 review/publish 失败只阻塞该 lane。
- THEN source capsule 只创建一次且四个 execution root 相互隔离；终态后临时 staging 被清理，受 release/retry/evidence 引用的对象保持可达。
- THEN carrier claim 只允许匹配 generation/fencing 的 owner finalize；同 digest 重放幂等，陈旧 claim、跨 lane root 或 source capsule 漂移均被拒绝。

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


<a id="gwt-003"></a>
### GWT-003 既存 reviewed closure 只经显式迁移进入宿主单轨

- GIVEN 一个不可变 source release 已闭合四载体 review/rights 且 identity collision 已记录。
- WHEN 显式 adoption/migration 精确绑定 source tuple。
- THEN 新宿主 execution/canonical version 保留业务 payload 与 provenance，旧 bytes 不变；任一漂移 `GATE_BLOCK`，且不创建 campaign/run/fence 或第二发布目录。
- THEN 迁移兼容期仍可验证既存 reviewed closure 的全部上游 execution/source provenance，但这些字段只作只读 provenance，不取得新任务 execution authority。

<a id="gwt-004"></a>
### GWT-004 M100 exact release 完成 Gamma E2E 后才启动 M1000 首 slot

- GIVEN canonical pool 已具 homepage/article/image/video 至少 `100/100/100/10` 个 eligible 对象，且同一 Research release 的 exact deterministic cohort 已冻结。
- WHEN 该 release 按 Alpha→Beta→Gamma 的必要前序推进，并尝试在不同时间点启动 M1000。
- THEN M100 release 精确包含 `100/100/100/10`，overshoot 不进入 cohort；content library binding、pool record、manifest 与 distribution bytes exact closure。
- THEN Gamma 前必须完成 import、API/media readback、private isolation 与 activation；`TargetUatBinding` 绑定 registered physical device、candidate/package/config/provider，entry surface × carrier required cells 各自产生 fresh raw `ReadinessCaseResult`，Gamma `EnvironmentAcceptanceFact` 直接绑定 exact bytes。
- THEN Gamma acceptance 之前，对 M1000 source/acquisition/semantic/review/task-init/pool 的生产副作用计数均为 0，只读 query 可以返回 gap/candidate readiness。
- THEN Gamma acceptance 之后，只选择第一个 candidate-backed M1000 slot，`task init` 原子建立工作包，宿主 Agent 只推进到 `0.plan` pass 且 `next=sources` 后停止；未开始 sources，未产生 M1000 reviewed delivery、pool record 或 release。
- THEN 任一 Gamma required evidence 失败或漂移时 previous active 保持不变、M1000 仍零副作用；Prod/Commercial evidence 缺失不阻断目标增量 Gamma 终点，也不得冒充目标增量完成。


<a id="gwt-007"></a>
### GWT-007 回收窗口让 output 稳态占用收敛

- GIVEN output 内同时存在被环境引用的 immutable release、带 `publish_ref` 的 task 证据、可重建缓存，以及既存 release 对已被回收 task 的引用。
- WHEN 执行 `release gc plan`。
- THEN 返回可执行回收计划：可重建派生物与超出保留窗口的过程产物列为可回收，发布证据与被环境引用的 release 列为受保护。
- THEN 既存 release 对已回收 task 的引用不使计划失败，而是解析到该 execution 的不可变墓碑：计划以 `reclaimedExecutions` 逐条读出 `executionId`、闭集回收原因与墓碑 ref，墓碑本体登记为受保护证据且自身不可成为回收候选。
- THEN 「从未物化」与「曾物化后被回收」不合并为同一种缺席：同一 execution 上 reconciliation 缺席证明与墓碑并存时判否，已墓碑的 execution 重新出现在磁盘上时判否。
- THEN 连续多轮宿主 execution 后 output 稳态占用不随累计执行次数单调增长。

<a id="gwt-009"></a>
### GWT-009 宿主并发不改写数量与对象判据

- GIVEN 相同 confirmed demand、candidate set 与 quota，以 `--max-parallel=1` 和更高值分别调度。
- WHEN 宿主 execution 产生 stage receipts。
- THEN quota、workUnitCount、对象 identity/eligibility 与 release selection 逐项相同；只允许 elapsed/actual concurrency 等诊断不同。
- THEN `approvedQuota`、`targetObjectCount` 与历史 `fleetMaxConcurrentWorkers` 三值仍可从存量 execution policy 分别读出。
- THEN 存量 job 数只由 `targetObjectCount` 派生，且不因 quota 改变。
- THEN 提高 quota 不改存量冻结并行值；在宿主新轨该字段不作为 authority。
- THEN 三值缺失的存量 managed execution 继续 fail closed，不由宿主 runner 参数补齐。

<a id="gwt-010"></a>
### GWT-010 runner 截止不续期也不撤销既有事实

- GIVEN fleet 显式绝对截止且已有部分 execution 完成 reviewed delivery。
- WHEN dispatcher 重启且截止归零。
- THEN 不启动新 slot，已完成 pool records 与 receipts 字节不变；运行中 execution 以真实 typed terminal 收敛，不写假结果。
- THEN 存量 managed execution 重启后注入的时间不超过绝对截止剩余值。
- THEN 剩余时间为 0 时不再启动新 managed job。
- THEN 单对象上限与批次剩余时间取更小者。
- THEN 存量绝对截止在 execution 冻结后不可改写；该兼容断言不授权新任务使用 managed 轨。

<a id="gwt-011"></a>
### GWT-011 stage receipt 单写零合格终态

- GIVEN 一个 execution 零合格。
- WHEN 观测 stage 写终态并由运营查询读取。
- THEN 单一 typed 原因、阶段、next action 与 evidence refs 只写在 canonical stage receipt；不存在 campaign/ReliableTask/fleet 第二枚举或终态 writer。
- THEN 存量 fleet 回执的并发、wave 与 deadline 字段仍通过原 schema。
- THEN 实测峰值不超过存量冻结上限，观测不回写。
- THEN 存量零合格七类原因保持各自唯一观测阶段，并由新宿主查询只读映射到 canonical stage reason。
- THEN 可续跑 refs 与不可续跑依据保持互斥且 next action 可执行。
- THEN 以上存量兼容证据只服务退役安全，不建立 campaign/ReliableTask/fleet 第二终态 writer。

<a id="gwt-016"></a>
### GWT-016 同一请求的数量与 entry surface × carrier 矩阵可闭环复核

- GIVEN 一个已确认请求为 homepage/article/image/video 分别声明正整数对象数量，同一请求沿现有单轨形成 immutable Research release，且验收清单为 entry surface × carrier 二维矩阵。
- WHEN Alpha 依次完成 import、projection/API/media verify、activate，并由每个 required cell 的 repo-relative runner 执行 production Remote App UAT。
- THEN 每载体均满足 `selected = imported = projected = verified = readback = qualified`。`qualified >= requested` 表示该载体达标；`0 < qualified < requested` 表示 partial，`shortfall = requested - qualified`，已合格对象仍可见而不伪造成达标。
- THEN 16 个 cell 各自显式声明 `required|not_applicable`；required cell 具 repo-relative 验收锚点引用、runner 与绑定同一 release identity 的 raw `ReadinessCaseResult`，not_applicable cell 具可复核理由与验收锚点引用。carrier 与 entry surface 不互换，micro 不属于 carrier 轴。
- THEN import、projection 或 API/media verify 在 activate 前失败时 candidate 停在对应 typed 终态，previous active pointer 不变，且不生成本 candidate 的激活成功事实。
- THEN activate 后任一 required cell 失败时生成绑定本 candidate 与 previous active 的 rollback receipt；rollback/readback 证明四个 entry surfaces 全部恢复同一 previous release identity，`durationMs <= 300000`。超过预算、pointer 未恢复或任一 surface 混合 identity 时终态为 canonical `rollback_failed`，本次 raw 结果保持可读且旧 release/receipt 不得替代失败 cell。

<a id="gwt-019"></a>
### GWT-019 宿主单轨不需要 capacity bootstrap

- GIVEN 干净工作区没有 SDK key/model preflight、capacity receipt 或 managed runtime。
- WHEN 已有 confirmed demand 与 immutable candidate binding。
- THEN 初始化资格只取决于 `task init` 合同；capacity/bootstrap/SDK/provider preflight 均不被读取，吞吐只能由运行后 receipts 事后评估。
- THEN 存量 bootstrap authority 仍固定为 measurement-only，不能创建业务成功事实。
- THEN 存量测量对象与 fleet report 失败时零 capacity receipt 可见。
- THEN 存量 calibration CLI 只消费其原 measurement closure。
- THEN 存量 tracked receipt 的摘要/applicability gate 继续保护存量 execution。
- THEN bootstrap 不得被 WorkRequest、retry、promotion 或环境入口选择。
- THEN bootstrap 输出不进入 consumer identity、pool eligibility 或 App DTO。
- THEN 新宿主 `task init` 不读取 bootstrap state。
- THEN 删除旧轨前存量 receipt 仍 create-once、不可手改。
- THEN 以上兼容子句只保护退役窗口，不恢复 managed capacity 为新任务合法入口。

<a id="gwt-020"></a>
### GWT-020 宿主 execution 十阶段生命周期可达 succeeded

- GIVEN 一个 candidate-backed 单 article execution 由宿主 Agent 按 canonical Skill 阶段表推进，每阶段依次执行 `task stage-open`、适用时的 canonical semantic prepare/record、`task stage-gate` 与 `task stage-close`，authority 文档与 close receipt 链是进度唯一真相源。
- WHEN `5.review` pass 后 execution 进入 publish → release → ship 后缀。
- THEN publish 阶段存在宿主单轨下的正向原子链：成品物化（对象根 `article.md` + `manifest.json`）与 approved 对象写入 canonical publish 由单命令或冻结序列完成，其 PRE/POST 判据不依赖退役编排层的 `verify execution-readiness` 或 `model_readiness.json`。
- THEN article 对象布局归 `posts/article/**`；布局漂移在 `0.plan`/`1.download` 即被 `verify content-execution-layout` fail closed 拦截，`verify stage-artifacts --through` 在每个阶段截面都能发现全部对象。
- THEN ship 的 `task stage-close` 只有在 machine gate 与 acceptance exact closure 均通过时才写 `verdict=pass,next=END` receipt，receipt reducer 随后唯一导出 `execution_state.status=succeeded`；pool readback、release readback、projection 或完整性查询都不能写 terminal。`verify release-lifecycle` 与 `stackctl verify --env gamma` 通过，receipt 链完整覆盖十阶段并保留逐阶段 authority/actor 证据，允许多宿主接手。
- THEN authority 边界可独立测试：`stage-open` create-once 冻结 workflow/前驱 closure，`stage-gate` 冻结 canonical argv、真实 exit 与 artifact exact bytes，`stage-close` 只从 open/gate/typed issues 派生 verdict/next 并同步只读 execution projection；三命令的 CLI 退出码 0/2/3 语义冻结，stage 枚举只有单一真相源。
- THEN `loop_driver.sh` 超时按进程组终止宿主子进程，claim 获取与释放只属执行者会话，驱动只做只读预检；`fleet_dispatcher.sh` 只起收 loop 进程。两者均无 candidate 选择、campaign/pool-dispatch、capacity authority 或业务重试。

<a id="gwt-021"></a>
### GWT-021 只读预检与 pool-build 的选中集一致且不写任何产物

- GIVEN 一个同时含已准入对象与被排除对象的 canonical 池。
- WHEN 运行 `release pool-precheck --milestone M100`。
- THEN 预检报出的可选中集与同一池上 `pool-build` 真实判据链的选中集逐条一致，每个被排除对象带 typed code，且预检运行前后 publish 树逐字节不变。
- THEN 整池被拒时预检仍逐对象给出选择器层与闭包层的排除原因并标注排除来源，不塌陷为单条聚合错误。
- THEN 预检报出的真实可选中计数不高于 milestone 选择器自报的 publishable 计数，两者不一致时以预检为交接判据。
- THEN 载体目标与缺口由 milestone 策略派生，预检不自带第二份载体或配额常量。
- THEN 预检前后 `SelectedSet`、`SelectionSeal`、release tree 与 pool tree 逐字节不变。
- THEN 独立 seal/finalize 或 build 原子 PRE 才能为已冻结 release identity 写 create-once selection evidence。
- THEN build 重算与 selection evidence 不一致时 fail closed。
- THEN precheck 不得补齐或升级 selection evidence，也不得推进 release identity。
- THEN seal/finalize 或 build 写入失败时不留下部分 `SelectedSet`、`SelectionSeal` 或 release payload。

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
### GWT-023 homepage 经 receipt 协议 publish 与三载体同链

- GIVEN 一个冻结 homepage 载体、receipt 链已 `5.review` pass 的 execution。
- WHEN 运行 `release publish-execution`。
- THEN publish 分派到实体路径并给出逐对象发布判定，不再以「homepage 未接线」拒绝整个 execution。
- THEN 目标集来自 execution 内实际存在的实体对象，canonical ref 为 `domain/type/name`，无发表坐标投影；无实体对象时结构化失败。
- THEN attestation 非 approved 的对象记为排除、缺冻结输入的对象记为阻断，两者语义不混用。
- THEN apply 模式下零对象晋级必须报错而非以成功报告收尾。

<a id="gwt-024"></a>
### GWT-024 载体证据形态与 data 契约测试段的可依赖性

- GIVEN 一个同时含 homepage/article capsule 候选与 image/video admission 候选的 source-ready 池。
- WHEN 构造波次输入、做投影漂移比对并派发。
- THEN 每个候选按其载体携带且只携带对应的物理证据引用，媒体候选不因被索取 capsule 键而退出编排；投影与漂移比对取自同一实现，任一处不得独立维护等价映射。
- THEN 媒体候选引用的 admission receipt 真实在场且与该候选同身份同对象形态；只有指针没有 receipt 的候选在池校验期即失败，不得在计划构造期无声通过。
- THEN 本域契约判据的全部判据文件经交付门禁的分片矩阵执行，每个文件落进恰好一片，新增文件无需登记任何分片清单即被纳入。
- THEN 任一红片阻断交付门禁汇总与候选证据；提交门禁覆盖不到的横切影响面显式登记延后项，不以局部选择冒充全域覆盖。

<a id="gwt-025"></a>
### GWT-025 百科结构化信息区参与不可变事实取证

- GIVEN 一个百科来源，其票价、开放时间或官方网站只出现在结构化信息区，可见正文里没有对应表述。
- WHEN 为该实体准备 homepage 或 article 的 source-ready 候选。
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

- GIVEN WorkRequest/Execution、canonical object transaction/pool record、ContentRelease 与四环境 operation/acceptance facts 均已有 create-once evidence。
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
- THEN 有效 Research/private 的 null/absent `accessMode` fail closed；只有显式 legacy-public contract version 可按 public 解释。private HLS 返回 unsupported typed terminal，不进入 MP4 fallback。

<a id="gwt-033"></a>
### GWT-033 future private HLS 按独立授权链可消费

- GIVEN 一份 future Research release 含 private HLS，媒体引用显式声明 access mode、稳定 asset identity，以及 manifest、segment 与 key 的授权边界。
- WHEN App 播放器请求 manifest、连续 segments 与 key，并跨授权 TTL 继续播放或恢复。
- THEN edge 对 manifest、每个 segment 与 key 分别执行受治理授权校验，未授权、过期或 identity 漂移均 fail closed。
- THEN TTL 过期后只沿 private HLS 的受治理换签路径恢复，保持已确认播放位置，不回退 progressive MP4 或 public URL。
- THEN 同一 release/asset identity 的 local contract、edge integration 与真实 App UAT 分别证明授权边界、过期恢复和可定位播放终态。

<a id="gwt-034"></a>
### GWT-034 pre-delete 准入绑定 static verify、public CLI live-import 与单份 Alpha M1 API 消费证明

- GIVEN retirement inventory 已由单独治理动作进入 `operationally_retired`，旧家族仍物理在场但不再可达；调用方显式绑定 current operational fingerprint 下的一份真实四载体 M1 proof、一次 canonical Data static-all verify receipt 与一次 public CLI live-import receipt 的 exact ref/digest，不发现 latest、不在 evaluator 内运行命令或生产内容。
- WHEN 只读 `stable-production-proof` 求值该单份 M1，并由 `legacy-retirement-precheck` 对三类 exact evidence 汇总准入。
- THEN static verify receipt 必须证明 `python3 quwoquan_data/scripts/cli.py verify all` 在同一 current operational fingerprint 上全绿；precheck 重验 receipt exact bytes、command identity、source fingerprint 与通过终态，不接受调用时现场执行、调用方自报 boolean、stdout 文本或旧 receipt。
- THEN public CLI live-import receipt 必须来自 fresh 隔离解释器：按 canonical public CLI command-module 清单逐个 import 全部模块后，`sys.modules` 中不存在 `content.execution.agent|queue|controller|recovery|campaign` 任一模块及其子模块；receipt exact 绑定被导入模块清单、解释器/source fingerprint 与上述零加载结果，任一漏导入、旧家族命中或摘要漂移均 fail closed。
- THEN 单份 M1 恰含 homepage/article/image/video 四个彼此独立的 canonical 单载体 execution；每个 demand quota、candidate count、target count 与 workUnitCount 均为 1，十阶段 authority-bound receipt 完整有序、ship close 唯一导出 `succeeded`，canonical publish/pool 各交付一个本载体目标。
- THEN M1 绑定一份 `milestone=null`、homepage/article/image/video=`1/1/1/1` 的 immutable Research release；该 release 在 Alpha 以同一 `releaseId + importRunId + verifyRunId` 完成 import/readback/activation，并形成 canonical `EnvironmentAcceptanceFact`，其 `acceptanceProfile=m1_api_consumer` 直接绑定 16 个 fresh API 集成 consumer entry×carrier readback `ReadinessCaseResult` exact bytes。该 profile 的字段与非 promotion 边界只由环境 owner [`REQ-005/006`](../../../runtime/runtime-config/environment-topology-and-packaging/spec.md#req-006) 定义；proof 不得伪造 `TargetUatBinding`、App 用户验收结果、物理设备或 promotion predecessor。
- THEN `operationally_retired + current static verify exact PASS + current public CLI live-import zero + current passing single M1/Alpha API acceptance` 足以令 precheck 返回 physical-delete `eligible`。三份独立 proof、registered physical-device 16-cell UAT 与至少一次真实 `retryOf` 仅属于 [`OPEN-020`](#open-020) 的 M100 放量置信，不再参与本 precheck，也不阻塞旧轨物理删除。
- THEN passing proof 只授权后续独立 physical-delete 增量，不替代 M100 Gamma acceptance、不启动 M1000，也不充当 post-delete package/runtime zero evidence。inventory=`retired` 只能在无 dual-read/shim 的物理删除完成且受影响门禁、post-delete package/runtime zero 与 minimal production probe 全部通过后写入。

<a id="gwt-035"></a>
### GWT-035 M100 放量置信独立于 legacy physical-delete authority

- GIVEN 同一 operational fingerprint 上存在三份 identity 独立的四载体 M1 proof，每份各自绑定独立 Research release 与普通 `acceptanceProfile=environment_promotion` 的 canonical nonprod EnvironmentAcceptanceFact。
- WHEN 只读 M100 scale-confidence evaluator 求值三份 exact evidence。
- THEN 三份 proof 的 unitId、四组 executionId、releaseId 与 acceptance factId 两两独立；每份 fact 由环境 owner 的普通 promotion validator 直接闭合 registered physical-device 16-cell required raw App `ReadinessCaseResult`，不得用 `m1_api_consumer`、API integration、模拟器或共享 acceptance 冒充。
- THEN 三份合计至少一个 execution 的 `retryOf` exact 指向真实 failed terminal predecessor 且前驱 manifest/state bytes 在场；非 terminal、同 identity、缺 exact predecessor 或自报 retry 均不计数。
- THEN 全部证据 current 且通过时只产生 M100 scale-confidence PASS；任一缺失只保持 [`OPEN-020`](#open-020) 未关闭，不改变 [`GWT-034`](#gwt-034) 的 legacy physical-delete eligible/blocked 裁定，不替代 M100 Gamma acceptance，也不启动 M1000。

## 6. 依赖

- 前置要求：父能力的 execution、review 与 release 契约。
- 上游事实：来源、目标集和审核结果。
- 下游结果：immutable release 或结构化阻断报告。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 M100 Gamma E2E 与 M1000 start evidence 尚缺

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺同一 current M100 exact `100/100/100/10` Research release 的 Gamma import/readback、registered physical device required raw UAT 与 Gamma acceptance，也缺 gate 通过后 M1000 首个 candidate-backed slot 到 `0.plan pass -> sources` 的新鲜证据，因此目标增量闭环保持 `GATE_BLOCK`。capacity soak、固定并发、SDK/provider preflight 与 Prod/Commercial 均不属于完成条件。
- 完成判定：[`GWT-001`](#gwt-001)、[`GWT-002`](#gwt-002)、[`GWT-009`](#gwt-009)、[`GWT-010`](#gwt-010)、[`GWT-011`](#gwt-011) 与 [`GWT-019`](#gwt-019) 的尚未直接绑定子句均保留为本次迁移 evidence gap；`GWT-004` 直接绑定 M100 exact release、必要 Alpha/Beta predecessor、Gamma import/readback/private isolation/activation、registered physical device required raw `ReadinessCaseResult`、Gamma `EnvironmentAcceptanceFact` 与 M1000 pre-gate mutation=0；gate 后首 slot 只到 `0.plan pass -> sources`。
- 依赖：上游需补足真实 M100 pool；Testing/Ops 负责必要 Alpha/Beta 前序、Gamma environment/device evidence；`task init` 已实现，真实 confirmed-demand 消费证据由 [`work-request-compilation` OPEN-001](../work-request-compilation/spec.md#open-001) 跟踪。Prod/Commercial out of scope。

<a id="open-002"></a>
### OPEN-002 acquisition receipt 永久缺席使回收计划仍不可执行

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍有一类引用没有合法终态，回收窗口因此仍未真正打开。`release -> task` 引用已由 [`DEC-035`](../design.md#dec-035) 的不可变墓碑裁定并落地，存量 output 的 11 个永久缺席 execution 已由 `release gc backfill-tombstones` 补齐终态，治理证据面已由 [`DEC-036`](../design.md#dec-036) 收敛，`release gc plan` 因此不再在 execution 引用与运行时包 payload 上判否。剩下的是 acquisition receipt：两份 rights 证据引用的 receipt 已永久不在磁盘上（`data/local/workspace/source-acquisition/receipts/be9dabf1….json` 4 处、`video/receipts/491bd7f6….json` 2 处），回收器在 `DATA.GC.REFERENCE_MISSING` 上仍然 `GATE_BLOCK`，稳态占用仍未开始收敛。
- 尚缺实现：acquisition receipt 的缺席终态尚无承载物。它不能直接套用 execution 墓碑：acquisition receipt 记录的是权利来源事实，把它的永久消失自动标成终态会抹掉一个真实的合规信号，因此需要先判定「rights 证据引用的 receipt 永久缺席」是可接受终态还是权利证据缺口。
- 尚缺验收证据：缺 `GWT-007.t1` 与 `GWT-007.t3` 在真实存量 output 上的一次可执行 `release gc plan` 与 apply，以及连续多轮宿主 execution 后稳态占用不单调增长的实测。`GWT-007.t2` 与「两种缺席不合并」已由 `test_canonical_gc_execution_tombstone__reclaimed_terminal_state__contract__local_contract_test` 覆盖。
- 完成判定：acquisition receipt 缺席的终态归属落为显式裁决并有 local_contract 锁定，随后 `release gc plan` 与 `release gc apply` 在真实存量 output 上各成功一次，且 `GWT-007.t3` 取得多轮实测。
- 依赖：权利证据侧 owner 判定 rights 证据引用的 acquisition receipt 永久缺席是否可接受；`GWT-007.t3` 依赖真实放量窗口。

<a id="open-006"></a>
### OPEN-006 旧编排物理删除待按轻量 precheck 实施

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：managed SDK/provider agent/controller/queue/campaign/recovery、ReliableTask 与 capacity bootstrap 已 operationally retired 但仍物理在场，尚缺轻量 precheck 实现与后续无 shim 物理删除。删除 authority 已由 [`GWT-034`](#gwt-034) 收敛为 current static verify exact PASS、public CLI live-import zero、一份真实四载体 M1 与 Alpha `m1_api_consumer` EnvironmentAcceptanceFact；旧三份 proof、physical-device UAT 与 `retryOf` 不再阻塞删除。
- 尚缺实现：现有 proof request/result/precheck 仍承载旧三份 physical-UAT 形状，需改为只读消费上述三类 exact evidence，并复用环境 owner 的同一 EnvironmentAcceptanceFact schema/validator profile 分支。precheck eligible 后仍需无 shim 原子删除旧五家族及其专属 wire/codegen/topology/tests，并执行 post-delete package/runtime zero gate；本 Story 不拥有或复制 EnvironmentAcceptanceFact 字段 schema。
- 尚缺验收证据：同一 current operational fingerprint 上的一次 canonical `verify all` exact PASS receipt、一次逐个 import 全部 public CLI command modules 后旧五家族及子模块 `sys.modules` 零加载的 exact receipt、一份真实四载体 M1，以及同 release/importRunId/verifyRunId 的 Alpha import/readback/activation 与 16 个 fresh API integration consumer readback CaseResult 所形成的 `m1_api_consumer` fact。fixture/local contract 只能证明 evaluator，不能冒充这些 fresh evidence。
- 完成判定：[`GWT-020`](#gwt-020) 的 stage-open/gate/close 十阶段 terminal 与 [`GWT-034`](#gwt-034) 全部由真实 exact-byte evidence满足，inventory=`operationally_retired` 且 current precheck=eligible 后，另开删除增量无 dual-read/shim 原子删除旧家族；受影响 gate、post-delete public CLI/package/runtime zero 与 minimal production probe 全绿后才写 inventory=`retired`。M1 API profile 不替代 M100/Alpha promotion 或 physical UAT。
- 依赖：Alpha 真实 import/readback/activation 与 API integration runner、停量窗口；不依赖 registered physical device、三份 proof 或 terminal `retryOf`，不得用旧 receipt、测试 fixture或 post-delete 零证据倒填 pre-delete proof。

<a id="open-020"></a>
### OPEN-020 M100 放量置信仍缺三份独立 proof、真机 UAT 与 retry 恢复样本

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：三份独立四载体 M1、registered physical-device 16-cell raw UAT 与真实 terminal `retryOf` 仍可提高 M100 放量置信，但这些证据不再具有 legacy physical-delete authority，也不得反向阻塞 [`OPEN-006`](#open-006) 的轻量 precheck 与删除。
- 尚缺验收证据：同一 operational fingerprint 上三份 identity 独立的四载体 M1 proof；每份绑定独立 Research release 与普通 `acceptanceProfile=environment_promotion` 的 nonprod canonical EnvironmentAcceptanceFact，直接闭合 registered physical-device required raw `ReadinessCaseResult`；三份合计至少一个 execution 真实恢复 failed terminal predecessor 并 exact 绑定 `retryOf`。
- 完成判定：[`GWT-035`](#gwt-035) 由真实 exact-byte evidence 满足：三份 proof 的 unit/release/execution/acceptance identities 两两独立，physical-device required cells 由环境 owner 的普通 promotion 语义验证，至少一次 terminal retry 恢复成立，且全部 evidence 保持 current exact-byte closure。该结论只关闭 M100 scale-confidence gap，不替代 M100 Gamma acceptance、不启动 M1000，也不改变已完成或待执行的 legacy physical-delete verdict。
- 依赖：M100 放量窗口、registered physical devices 与 canonical environment-promotion UAT authority；不依赖旧家族继续物理在场。

<a id="open-009"></a>
### OPEN-009 confirmed 请求的 M100 Gamma 消费后缀尚未闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：目标 M100 exact immutable release、Gamma import/readback 与 entry surface × carrier required cells 尚未绑定同一 confirmed WorkRequest/compile receipt 身份，因此仍不能证明一份意图沿宿主单轨闭环到目标增量 Gamma acceptance。编译前缀由 [`work-request-compilation`](../work-request-compilation/spec.md) 的 `OPEN-001` 承接，入池段由 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md) 的 `OPEN-004` 承接。
- 尚缺实现：无新增 release/UAT wire 缺口；缺的是目标 `task init` 与同一 identity 的真实链路运行。
- 尚缺验收证据：同一 immutable M100 candidate 的 `ReleaseUatSamplePlan`、必要 predecessor、Gamma import/readback、registered physical device `TargetUatBinding`、required raw `ReadinessCaseResult`、Gamma `EnvironmentAcceptanceFact` exact-byte binding 与失败 rollback receipt。
- 完成判定：`GWT-016.t1`、`GWT-016.t3` 由 release/import/projection/verify/readback api_integration 覆盖，`GWT-016.t2`、`GWT-016.t4` 与 `GWT-030` 由 production Remote user_acceptance 的 required matrix cells、raw `ReadinessCaseResult`、直接绑定它们的 `EnvironmentAcceptanceFact` 与 rollback receipt 覆盖。
- 依赖：上游编译与入池 OPEN 先行关闭，再沿 canonical pool 与 immutable Research release 形成 `GWT-016/GWT-030` 的 Data-owned `ReleaseUatSamplePlan`、import/readback、Ops `TargetUatBinding`、required raw `ReadinessCaseResult` 与 `EnvironmentAcceptanceFact`；在这些新鲜证据形成前不得用 local_contract、fixture、完整性 projection 或旧 receipt 关闭本 OPEN。

<a id="open-012"></a>
### OPEN-012 receipt/claim 薄驱动层缺少行为级测试锚定

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：receipt/claim 驱动层的关键行为缺少直接测试或门禁，语义漂移只能靠人工发现。`task stage-close` 的 receipt reducer 同步、`writing_pack` schema 校验失败路径、`lane-claim` 与 `stage-open/gate/close` 的 CLI 退出码语义（0 成功、2 参数拒绝、3 冲突）均无独立 local_contract。orchestration 与 handoff-protocol 文档所述判据与实现之间没有漂移门禁。
  三项驱动层实现缺口已清偿：`loop_driver.sh` 的单轮 hard timeout 改为终止整个会话进程组（`set -m` 建组、`kill -9 -$pid` 杀组），宿主派生的孙进程不再残留；`--round-timeout` 与 claim TTL 的关系由 `task lane-claim --check --round-timeout-seconds` 在驱动启动时判定，超出「TTL 减安全余量」即退出码 64，两者关系不再靠默认值巧合成立；十阶段 stage 闭集收敛到 `core.control_types.ReceiptStage`，`RECEIPT_STAGES`、`OBJECT_STAGES`、工作包目录闭集、`stage_artifact_contract.STAGES` 与 `verify --through` 的 CLI choices 全部由它派生。
- 尚缺实现：`task stage-close` 的 receipt reducer 同步、`writing_pack` 校验失败路径与 stage authority CLI 退出码语义仍无独立 local_contract；orchestration/handoff-protocol 的文档-实现漂移门禁仍缺。
- 尚缺验收证据：上列剩余各行为的 local_contract 或门禁，每项一测且不放宽生产语义。
- 完成判定：`GWT-020.t4..t5` 成立。
- 依赖：无外部阻断。

<a id="open-015"></a>
### OPEN-015 progressive private MP4 只缺 fresh App UAT

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：只缺同一 runtime generation 的 fresh production Remote App UAT。Research 私有媒体的设计与实现已就位。progressive private MP4、图片/头像/对象主页/文章资产的 typed `accessMode` 分流、单飞短签、稳定资产缓存身份、Range 边缘逐请求复验，以及首次 401/403 强制换签最多一次并保持播放位置均已实现。二次失败 typed terminal 且不回退公开 URL。private HLS 不属于本 OPEN 的未完成实现，保持 unsupported/fail closed，并由 [`OPEN-017`](#open-017) 单独承接。
- 尚缺实现：无。有效 Research/private projection 的 `accessMode` 与稳定资产标识为必填；仅明确 legacy-public contract version 可把 null/absent 解释为 public，Research/private 缺失保持 fail closed。
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
- 尚缺实现：Runtime/Data/Service owner 需让六个 view 只从 WorkRequest/Execution、canonical object transaction/pool record、ContentRelease 与 per-environment operation/acceptance facts 投影，并移除或拒绝任何 command、Repository、checkpoint、独立 ledger；四入口需显式携带/读回 active 或 previous release identity，retired 保持治理态而不进入 App wire。
- 尚缺验收证据：[`GWT-029.t1`](#gwt-029) 至 [`GWT-029.t7`](#gwt-029) 尚无任何子句级 local_contract 或 api_integration；[`GWT-031.t1`](#gwt-031) 至 [`GWT-031.t7`](#gwt-031) 尚无任何子句级 local_contract、四入口 release identity api_integration 或 rollback/replay user_acceptance。
- 完成判定：[`GWT-029.t1`](#gwt-029) 至 [`GWT-029.t7`](#gwt-029) 逐条由有效 contracts 的 local_contract/api_integration 绑定，且 projection 删除重建不改 owner bytes；[`GWT-031.t1`](#gwt-031) 至 [`GWT-031.t7`](#gwt-031) 逐条由同一 release identity 的 local_contract/api_integration/user_acceptance 绑定，且四入口 rollback/replay 后 previous release identity 一致率为 100%。
- 依赖：Runtime/Data/Service owner 冻结并实现字段与 query 事实；Testing/Ops owner 提供四入口真实 runner。不得以 projection cache、counts、旧 receipt 或页面文案关闭本 OPEN。

<a id="open-019"></a>
### OPEN-019 content library sole-holder 与 release selection seal 尚缺实现闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺 content library 唯一 canonical holder、release distribution materialization 非 durability、precheck 零写入和 release owner create-once `SelectedSet`/`SelectionSeal` 的实现硬切与真实 readback；不能把旧 Git 随体或 precheck 行为视为闭合。
- 尚缺实现：Data/Runtime owner 需删除 Git 随体 canonical holder/recovery 语义，使 selected/rebuild-prior media 缺失严格 fail closed；`pool-precheck`/inspection composition 去除全部 writer，seal/finalize 或 `pool-build` 原子 PRE 成为 selection evidence 唯一写边界。
- 尚缺验收证据：现有真实测试只绑定 [`GWT-021.t1`](#gwt-021) 至 [`GWT-021.t5`](#gwt-021)，[`GWT-021.t6`](#gwt-021) 至 [`GWT-021.t10`](#gwt-021) 尚无子句级测试。现有真实测试只绑定 [`GWT-022.t1`](#gwt-022) 至 [`GWT-022.t6`](#gwt-022)，[`GWT-022.t7`](#gwt-022) 至 [`GWT-022.t10`](#gwt-022) 尚无子句级测试。
- 完成判定：保持 [`GWT-021.t1`](#gwt-021) 至 [`GWT-021.t5`](#gwt-021) 与 [`GWT-022.t1`](#gwt-022) 至 [`GWT-022.t6`](#gwt-022) 的既有测试绑定，并为 [`GWT-021.t6`](#gwt-021) 至 [`GWT-021.t10`](#gwt-021) 和 [`GWT-022.t7`](#gwt-022) 至 [`GWT-022.t10`](#gwt-022) 逐条补齐职责匹配的 local_contract/api_integration；届时 precheck 前后 owner bytes 不变，content library 不可达负例零新 release 可见，materialization 仅能由同一 canonical binding 重建。
- 依赖：Data content library、canonical transaction、release builder 与 Runtime distribution owner 联合接手；不得以干净检出、旧 release bytes、fixture 或 warnings 关闭本 OPEN。
