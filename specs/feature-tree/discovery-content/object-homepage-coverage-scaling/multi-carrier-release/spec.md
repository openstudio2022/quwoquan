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
- 经确认的请求沿既有 execute、逐 task 终态、pool/review/promotion、immutable release、环境 import/activate/readback 与 App CaseResult 单轨推进；任一步失败停在可恢复的 typed 终态。

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
- 将 Data 的 `homepage` 载体解释为 App micro；本 Story 的四个消费 surface 固定为 entity homepage 对象主页、article 文章、image 图片与 video 视频。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多载体统一发布边界

- 每个发布对象必须闭合 creator、tag、entity、media 与 source 引用；运行 receipt 只能写入输出目录，不得回写静态真相源。
- homepage、article、image、video 不以彼此的 execution 或 publish 结果作为运行前置；post 只依赖可解析的 canonical entity identity。
- 已绑定有效 calibration receipt 的 active execution 必须从同一不可变 source-definition capsule、execution bundle 与 entity catalog digest 形成彼此独立、可分别调度的 workload。调度器可按当时可用容量串行或重叠运行，任一时刻不要求全部 active workload 同时运行。达到并发上限、固定四 lane 同时运行、固定数量的同时 workspace 或 capacity soak 观测结果均不得作为 submission、dispatch、对象准入或 promotion 前置。缺失有效 calibration receipt 则在 execution policy 冻结前 typed blocked。单一载体失败不得覆盖其他载体工作包，也不得阻止其他载体已合格对象发布。capsule 封存后不得再用 live worktree 漂移否定该 execution。
- `task execute --stage submit-only|campaign-run|campaign-freeze|campaign-lane-run|campaign-finalize|review-only` 是唯一 campaign 门面；单 controller 可用 `campaign-run`，复制会话必须先由 `campaign-freeze` 等齐本次显式 active workload 的 immutable submission 并冻结唯一 plan、只读 capsule 与 `planDigest`，再由每个 `campaign-lane-run` 独占一路 claim，最后由 `campaign-finalize` 只聚合实际 active workload 的 create-once receipt。collision、branch/commit/source/catalog mismatch、重复 claim、主工作树漂移或超时均 fail closed。
- submission-only attempt 只能在无 plan/report/runtime/execution 证据时由 `reconcile-submissions` 收口。
- 已冻结 campaign 若全部 active claim 在 author/review/publish 前 terminal failed，只有在对应 active execution root 已经受 GC protection 合法清理且 source identity 确实漂移后，才允许 `reconcile-failed-campaign` 写 create-once supersession。
- claim 后若已产生 execution 证据，不得清理或改写该证据。
- 每个 terminal active execution 必须分别写入当前源码可复核的 create-once supersession receipt，再由 campaign reconciliation 精确绑定这些 receipt、原 plan/report/runtime/claim/submission 与已变化的 source identity。
- 下一序列逐 lane 声明 `retryOf` 并精确引用 reconciliation receipt。任一进程仍存活、lease 未释放、execution receipt 缺失或字节漂移均 fail closed。
- independent review 已完成 Provider journal、却因 controller 中断只留下 schema-valid pending response 时，不得把 pending 改写或冒充旧 `reviewer_result`。只有 sole pending response 与 sole 未绑定的 finished Grok reviewer work unit 可由独立 create-once interruption reconciliation receipt 精确绑定 campaign/capsule/execution/journal/response 全部摘要；新 `retryOf` 必须同时消费该 receipt 与其余对象已绑定的 final reviewer result，只纳入 failed refs，并把 typed issues 注入对应实体的新对象重写。前驱 qualified 对象不得进入 retry scope。
- controller 为本次 active workload 建立同一 content-addressed、只读 source/executor capsule，并为每条 active lane 分配独立 execution root、queue namespace 与 staging prefix；active workload 独立调度，review 可串行或重叠执行，每条 lane 按自身 review 结果独立进入 publish，不得因任一 lane 失败而整批 abort，也不得为每条 lane 复制完整 Git object store。共享 canonical publish 继续由对象事务锁保持单写者，最终 Manifest/release 必须精确验证全部被选对象及引用闭包。
- semantic author/reviewer 只消费 create-once 本地 journal 与只读 source capsule。Provider/model、凭据、runtime、网络与真实 startup 是启动该 semantic task 的 preflight；execution 已绑定有效 calibration receipt 后，soak、workspace smoke、effective concurrency 与 resource samples 只诊断实际容量，不得改变 task dispatch、对象准入或 promotion。缺 receipt 的 measurement-only bootstrap 不是内容 task dispatch，不能生成 author/reviewer、pool-delivery 或 publish 成功事实。review 通过后才生成 immutable pool-delivery intent，ReliableTask 与 generation/fence/worker binary 仅负责 intent 的幂等交付。transport 不可用时对象保持 `deliveryPending`，不得撤销 review、重复调用 semantic Provider 或阻塞其它 lane。
- 每个实际启动的 semantic task 必须逐项写入 create-once typed 终态结果；排队、尚未启动、capacity sample 或 workspace sample 均不得合并成 task 成功或失败，也不得替代实际 task 结果。
- lane 终态独立记录为 `published`（`qualified >= quota`）、`partial`（`0 < qualified < quota` 且已合格对象已发布）或 `blocked`（`qualified == 0` 或 review/publish 失败）；campaign 终态为聚合视图：`succeeded`（全部 active workload 均达标）、`succeeded_partial`（至少一路发布了合格对象）、`blocked`（无任何可发布合格对象）。
- `quota` 是里程碑累计目标，不是发布许可条件；`partial` lane 必须发布全部已合格对象，并将 shortfall 写入 typed evidence，不得因未达 quota 丢弃合格对象。
- image/video 请求的 `quota` 是内容对象下限，`count`、`targetNames` 与 `coverageTargets` 只是唯一实体候选/覆盖范围，三者不得比较或互相改写。每个已接受外部媒体资产必须从 immutable manifest/receipt exact pair 冻结独立 `workUnit`（至少绑定 receipt、asset、content digest 与唯一 canonical coverage target）。同一实体的多个资产分别生成多个 brief/content object。无法唯一映射实体的单资产形成 typed exclusion，其他 workUnit 继续；`0 < qualified < quota` 为 partial，只有零合格对象才 blocked。
- 若存在 discard，每个 discard 必须具备非空 `objectRef` 与 typed `issues`，且 `selected == qualified + discarded`；不得要求真实批次必须存在 discard 才准出。
- article/image/video 的 canonical Post manifest 必须显式声明 `contentIdentity=work`；schema、promotion 与 importer 任一层发现缺失或非 `work` 均阻断该对象，禁止由消费者默认补值。
- 新增 canonical Post 必须显式携带稳定 `contentId`、递增 `version`、`sourceType=data`、`variantPurpose`、`admission.processResult/qualityResult/usageScope` 与 `status`。只有 `completed + passed + active` 可被 ReleaseManifest 选择。
- 统一池 reader 只接受显式 create-once pool record。缺 admission、稳定 `contentId/contentVersion`、完整 `sourceAttribution` 或 source identity 的历史对象按对象排除，不得在读取时从 review、路径或当前 source identity 推导。payload drift 的互斥状态与三种恢复 command 由 [`canonical-content-identity-recovery`](../canonical-content-identity-recovery/spec.md) 拥有，本 Story 的 release 选择只消费其裁决结论。
- 环境定向 Manifest 从同一 pool 生成固定载体/作者轮转顺序并按 Alpha 2,100、Beta 10k、Gamma 100k 截取稳定 Post 前缀，Homepage 不计 Post cap；环境无关 M100/M1000 Research Manifest 精确冻结 cohort 并可由四环境消费。相同 `contentId` 在同一 manifest 只出现一个版本，有供给且容量允许时 article/image/video 必须同时出现。
- campaign report 必须保留 named main branch、status、phase、run generation/fencing、heartbeat、review/publish return code、source capsule/execution-root ref、qualified/finalized count 与 cleanup 终态；报告是运行回执，不得成为新的内容或 release 真相源。
- 复制会话的 carrier claim 必须绑定 campaign/run generation/fencing、carrier、execution、只读 source capsule 与独立 execution root；同一 carrier 同一 generation 只能存在一个有效 claim，过期或跨 generation owner 不得 finalize。
- carrier finalize 必须绑定对应 claim、对象级 review/rights/provenance 证据与 publish receipt，并满足 `finalized == qualified >= 1`；同 digest 重放幂等，token、generation、source 或对象闭包漂移 fail closed。未达 quota、存在 shortfall 或存在带 typed issues 的 discard 均不阻止其余全部合格对象 finalize。
- 每个生成批次只按对象记录过程完成、质量和授权范围；合格对象立即追加到统一池，批次未达 quota、存在 shortfall 或其他对象失败均不阻断已合格对象。M100/M1000/M10000 只按累计唯一对象数量判断是否达标，均为数量下限而不是停止生产或准入的上限。
- M1000 sourcing 以请求冻结的完整行政区域 frontier 为产品范围：穷举所选区域全部市、区、县与可识别 POI，合格对象即使显著超过 1000 也全部准入。不得设置单一区县、单一实体类型、Provider 或 creator 数量/比例上限。
- M10000 将同一 frontier 先推广到全国，再扩海外，国内外只共享一套 canonical geo/entity/source contract。

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
### REQ-004 四环境 research 隔离、商用切换与规模门

- research activation 前，四环境分别证明身份白名单、匿名内容和媒体关闭、无公开 CDN/匿名 URL、分享/导出/索引关闭、内部 App 签名与研究态标识、媒体短期签名 URL 和访问审计；任一缺失立即 `GATE_BLOCK`。
- `appUatEnvelope` 从本 release 对象闭包投影并显式带 `releaseClass=research/productLifecycleState=research`，不可被 commercial package/activation/UAT 复用。
- Alpha/Beta/Gamma/Prod 必须分别生成 create-once `activationEnvelope`，精确绑定同一 `releaseId + manifestDigest + sourceIdentitySetDigest + releaseClass + productLifecycleState + appUatEnvelopeDigest`。每个 cohort 对象在 manifest 中保留自身 execution/source identity。环境按 Alpha→Beta→Gamma→Prod 依次激活，后续环境冻结前一环境同 release 的 passed activation/readback/App UAT receipt 字节摘要，同时仍生成本环境独立 import/readback 与 research isolation policy/proof。任一环境 receipt 不得替代另一环境，也不得把 Prod research activation提升为 commercial。
- 商用切换从同一 frozen canonical pool snapshot 构建新的 immutable Commercial release；Research 可选择 `research|commercial` 对象，Commercial 只选择逐对象 `usageScope=commercial` 且 entity/post 全部资产 `commercial_allowed` 的授权子集。两者绑定相同 `poolDigest`，source identity 使用各自被选对象的 scalar 或 set 闭包，不要求伪造新的 scalar source digest。未选坏对象形成 typed excluded，不拖垮其余合格对象。
- `qwq-data release commercial-transition` 只从同一 `poolDigest` 的 research/commercial 两个不同 immutable release、授权对象子集与四环境 cache/media/signed-URL 清理及未授权 readback=0 证据生成逐资产 create-once migration receipt；两 release 的 `releaseId` 与 payload 必须不同，不得修改旧 research release 或用手工布尔值替代环境证据。
- 日常 research release 不以规模数量作为发布许可。
- Content candidate 必须按 `prepared -> imported -> projected -> verified -> active` 单轨推进；逐阶段持久化脱敏 receipt，记录 duration、attempted/success count、checkpoint 与首个 typed blocker。只有 `verified` 可切换 active pointer，任一阶段失败保留 previous active 与已成功阶段事实。
- 三个累计规模 milestone 固定为 homepage/article/image/video：M100=`100/100/100/10`、M1000=`1000/1000/1000/100`、M10000=`10000/10000/10000/1000`。这些数字均为 promotion 下限；日常 publish 允许 partial，已合格对象超过下限时继续准入，不为凑整数截断 frontier。milestone promotion 必须逐路满足 `totalUniqueFinalizedCount >= targetCount` 且 `shortfallCount=0`。
- source-pool、oversampling、Provider、实际重叠时长、workspace/soak/resource samples 和恢复事实用于计划容量与定位瓶颈；execution 已绑定有效 calibration receipt 后，缺失、未运行或失败的附加诊断样本不得改变一个已完成、质量合格且在授权范围内对象的池准入、dispatch 或 milestone 结果。有效 receipt 本身缺失时 execution policy typed blocked，measurement-only bootstrap 只产容量证据且不参与对象准入、dispatch 或 milestone。
- 规模 promotion 只验证累计唯一对象数量、对象准入结果和所构建 ReleaseManifest 的引用闭包；精确重复不计数，缺引用对象留在池中等待修复，不阻断其他合格对象发布。
- 后继 milestone 只生成累计目标差额。前驱 promotion receipt 只记录 lineage，不作为新合格对象入池或当前 milestone 计数的前置门。M1000 的 source discovery/acquisition、semantic 与 review 可以在 M100 环境验收期间并行；M1000 promotion 前必须补足同一 M100 Research release 的 Alpha activation/readback 与 100 例 App UAT。该产品阶段门不撤销池中任何 M100 对象，也不冻结后继来源队列。
- promotion receipt 必须记录各 carrier 的 target、admitted、publishable、deliveryPending、selected、excluded 和 gap；illustrated、video popularity、automatic recovery、source mix、实际调度重叠、workspace/soak 与资源使用只作为诊断统计。
- M1000 与 M10000 的时间、Provider 容量和故障恢复样本用于计划和 SRE 评估；目标未按期完成时报告实际 gap，不撤销已经完成的池追加或已验证 Release。
- semantic author/reviewer 通过受治理 `cursor_sdk|codex_sdk` adapter 执行，Provider、model、model parameters、role、SDK/runtime digest 与 run/result digest 在 execution 冻结。受治理生产主选为 `cursor_grok`，exact model 与 parameters 由当前 runtime profile 声明并经 fresh preflight 实测准入，不在规格中另建版本常量。
- `cursor_auto` 只能在父 execution 已以允许的 typed provider/model failure 终止后，以新的 `retryOf` 显式选择。禁止 execution 中静默 fallback 或由 SDK Auto 首次路由替代 Grok 证据。execution 已绑定有效 calibration receipt 后，附加 capacity soak 未运行或未通过不得用下载数或框架测试冒充稳态容量，也不得撤销既有 task dispatch、合格对象发布或规模 promotion；有效 receipt 缺失时不得启动日常 task dispatch，只能进入 `GWT-019` 的 measurement-only bootstrap。
- 10 万级不是单一 promotion 事务：使用同一分片键持续生产，并以 1K/5K/10K immutable release waves 累计到不少于 100000 个合格对象；单 wave 或 named scale 仍是下限，不是总量上限。跨分片全局去重、checkpoint 恢复、dead-letter 隔离与连续 7 天无全局冻结的 soak 用于独立的 100K 稳态运行/SRE 结论，不是累计对象达到 M10000 或 100K 数量下限的 promotion 前置。

<a id="req-005"></a>
### REQ-005 已审核闭包采纳与 release identity incident

- `adopt-reviewed-closure` 是现有四 lane campaign/release 单轨上的一种身份收口方式，不是第二个 aggregator、第二套 publish 目录或手工 manifest 入口。它只能采纳一个已存在且不可变的 reviewed release 对象闭包，不重新生成、不改写正文/媒体/审核/权利事实，不修改上游 release。
- 采纳引用必须绑定精确 source release tuple `releaseId + payloadSha256 + canonicalMerkle + attestationFileSha256`，并对 release header、desired state、object index、media manifest、每个 review/rights evidence 和媒体公共切片逐文件复核摘要；任一字节、对象引用或媒体所有权漂移即 fail closed。
- 新的四个 adoption execution 必须共享唯一当前 `sourceDigest + entityCatalogDigest -> sourceRevision`，且 release 激活身份仍只允许一个 `sourceDigest`。上游历史 `sourceDigests/executionIds` 只能以冻结 provenance 留在 adoption receipt，不得被提升为新 release 的多 source active identity。
- 同一 `releaseId` 曾对应多个 payload/canonical identity 时，必须先生成 append-only、create-once identity incident；incident 按上述精确 tuple 保留每次观测的 attestation 与 execution closure，且所有受影响 execution 在 incident 未关闭前不得 discard 或 GC。仅 releaseId 相等、仅文件名相等或仅有历史口头记录都不构成可采纳证据。
- provenance 合同引入前已 create-once 的 incident 已全部完成一次性 CLI migration（迁移源 namespace 已清空，migration 器与其 schema 已退役）：迁移当时验证了原 incident 精确文件摘要、receipt digest、合同引入 commit/时间边界、旧 schema 闭集、同目录 snapshot 路径/文件摘要/attestation identity 与 execution closure，并把每个 snapshot 分类为 `original_file`，在独立 create-once namespace 留下 source-bound receipt 与当前 schema projection，原 incident/evidence 未被修改。GC/discard 仅在原文件仍逐字节匹配 migration receipt、projection 的观测 identity 与 execution closure 与原 incident 完全一致且 projection 通过当前 schema 全量校验时消费该 projection，否则继续 fail closed。

<a id="req-006"></a>
### REQ-006 有界并发、绝对批次截止与可复核运行终态

- 有效 calibration receipt 已冻结进 execution policy 后，并发上限只约束任一时刻可同时运行的 worker 进程数，不再以“是否达到该上限”作为 submission、dispatch、对象准入或 promotion 的前置条件。达不到上限、只跑一路或全部串行完成都不改变任何对象的准入与发布结果；receipt 缺失或无效仍在 policy 冻结前 typed blocked。
- 来源发现阶段的 `autoResearchMaxConcurrentWorkers` 与 ReliableTask 交付阶段的 `fleetMaxConcurrentWorkers` 只能由 immutable execution policy 冻结。runtime profile、环境变量、命令行默认值与任何探针观测都不是合法来源。
- preflight capacity soak 与 workspace smoke 的 `effectiveConcurrency` 只描述探针当时的实际并行度，是诊断观测而不是生产上限；把它投影成上限即为非法来源，必须 fail closed。
- `local-apple-silicon + cursor_grok` 的容量值只能来自当前可读取、受版本控制且 create-once 的 calibration receipt。receipt 必须自包含 Provider probe、资源观测、真实 fleet peak、逐对象 timing 与适用范围；任一 evidence ref/digest 漂移即 execution 冻结失败。缺失或从未受版本控制的 receipt 不能继续授权任何并发、wall-clock 或 grace 数值，见 `OPEN-006`。
- `execution_state` 中 `managedAgentScheduler` 的 `promptCount` 是单个 managed checkpoint 内语义 Agent prompt 级调度的运行观测。它既不是资源上限，也不是 ReliableTask 的 worker 进程并行度，两个维度不得互相读取或互相推导，该对象也不得以 worker 词元命名任何 prompt 级观测。
- `approvedQuota`（对象下限）、`targetObjectCount`（本次冻结的工作单元数，也是派生 job 数）与并行上限是三个互不相同的语义，必须在执行策略中各自显式冻结。任一字段不得同时承载其中两个语义，`requiredWorkers` 不得继续由工作单元数或 quota 派生。
- 规模只改变 wave 数：job 数增长只增加 wave 数，不增加任一时刻同时运行的 worker 进程数。wave 数只由 job 数与冻结的并行上限决定，与 quota 无关。
- 并发上限不得导致任何已冻结工作单元被丢弃、跳过或与其他单元合并。每个工作单元必须获得独立 typed 终态，单个单元失败或超时只终结该单元，释放的额度立即由下一个待处理单元占用。
- 批次时间预算必须以绝对纪元时间 `fleetBatchDeadlineEpochSeconds` 冻结并持久化。进程重启、lease 续租与子进程重建只能注入 `max(0, fleetBatchDeadlineEpochSeconds - 当前时间)` 的剩余时间，不得重新注入完整批次预算或完整单对象超时窗口。
- 剩余时间为 0 时不得启动任何新 job，已在运行的 job 按单对象 wall-clock 上限收敛并写入 typed deadline 终态。单对象上限与批次剩余时间取更小者，需要更多时间只能由新的 `retryOf` 冻结新的绝对截止。
- ReliableTask fleet 运行回执必须同时携带 `fleetPeakConcurrentWorkers`、`fleetWaveCount` 与 `fleetBatchDeadlineEpochSeconds`，缺任一项即校验失败。实测峰值不得超过冻结上限，且只作观测，不得被回写成新的上限。
- `qualified == 0` 不再是单一 `blocked` 汇总值，必须携带唯一 typed 原因。原因闭集为七种：来源为空、来源访问被拒或网络不可达、批次截止耗尽、全部对象质量被拒、可续跑中断、全部对象因闭包超出单对象存储预算而在 publish 准入被拦下，以及 `在场可用` 集合非空但全部候选实体在 target set 冻结前的选择器准入被排除。七者互不合并，也不得退化为一个不带原因的汇总值。
- 原因值、观测阶段与运营动作是三个互相约束的闭集，任一原因进入时三者同批扩容，新原因不得借用语义不符的既有阶段或既有动作。观测阶段闭集为五种：来源发现、review、交付、publish 准入与 target set 冻结前的选择器准入。每个原因值同时绑定唯一观测阶段与唯一运营动作，因此运营者从原因值就能读出「谁观测到」与「下一步做什么」，不需要再做一次判断；不得靠放宽某个原因的阶段或动作取值范围让同一个原因同时归属两处。「全部对象质量被拒」只由 review 观测，「全部对象超出单对象存储预算」只由 publish 准入观测，publish 准入的结论取不到前者。
- 「全部候选实体被选择器准入排除」只由 target set 冻结前的选择器准入观测。该阶段严格后置于实体级来源判定，只作用于已判为 `在场可用` 的实体，因此它取不到来源发现阶段的任何原因值，来源发现阶段也取不到它。
- 运营动作闭集为五种：续跑、修来源、重新冻结时间预算、缩减对象体量与扩大候选范围。缩减对象体量是超预算原因的唯一动作，指向按批次携带的对象级排除条目逐对象减少其引用的资产数、换掉单张超出预算的素材或把该对象拆成多个对象。它不是修来源——改来源闭集解决不了体量超标；它也不得被表述为调整预算数值，预算数值由既有门禁单点拥有，不由本终态改写。
- 扩大候选范围是准入零通过原因的唯一动作，指向扩大候选区域范围以取得尚未触及累计上限的实体，或按治理流程调整多样性策略。它不是修来源——被排除实体的来源全部可用，按修来源提示去改来源闭集解决不了准入零通过；它也不得被表述为调整多样性阈值数值，阈值数值由多样性策略的既有 owner 单点拥有，不由本终态改写。
- 可续跑中断必须给出精确可续跑 refs，其余六种原因必须给出不可续跑的判定依据。「全部候选实体被选择器准入排除」在该依据之外还必须给出逐实体的准入排除 refs，指向选择器在冻结选择证据上已声明的排除条目，缺该 refs 时该原因不成立。运营者只读运行回执即可决定续跑、修来源、重新冻结时间预算、缩减对象体量还是扩大候选范围，不需要读取运行日志。
- 批次级零合格原因的唯一写者是本 Story 的 lane 回执。媒体侧只产出对象级排除码，两层以引用衔接而不复制，媒体侧不得自建批次级原因值。批次级原因只在一个批次的全部对象都被拦下时成立，存在任一合格对象时该 lane 仍按合格对象数进入 `partial`。
- 不可续跑的判定依据必须指向一份持久化的逐对象排除台账，并以相对 ref 与 `sha256` 摘要绑定该台账字节。台账只记录该 lane 已经做出的观测（该阶段判定过的对象数、准入通过数为零、逐对象排除码），不新增判定；依据缺台账或摘要不符时该原因不成立，写者判否而不落一个空摘要。
- 闭集之外的入站原因值、阶段值与动作值一律 fail closed：既不映射为任何既有原因，也不退化成不带原因的 `blocked` 汇总值。lane 回执、campaign 报告与 fleet 运行回执三层读到的是同一取值，任一层不得自建转换表或补默认值。

<a id="req-007"></a>
### REQ-007 确认后请求沿现有单轨推进到环境与 App 消费

- 确认后的完整用户路径固定为 `envelope -> task execute -> typed task terminal -> canonical pool/review/promotion -> immutable release -> Alpha import/activate -> API/media readback -> App CaseResult`。每一步只消费前一步的 immutable ref/digest，失败不得跳到后续步骤，也不得由旧 receipt 冒充本次完成。
- 意图 preview、confirmed handoff 与 envelope 编译由 [`work-request-compilation`](../work-request-compilation/spec.md) 拥有；canonical 池唯一写路径与结果五态由 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md) 拥有。本 REQ 只约束 canonical pool 之后的 release、环境与 App 消费闭环。

<a id="req-008"></a>
### REQ-008 生产与发布之间的只读交接判据

- 生产会话的完成判据是只读预检全绿，不是 `pool-inspect` 的 publishable 计数。`pool-inspect` 的 post 侧 publishable 不运行引用闭包、媒体 CAS 与物理字节一致性、rights snapshot 与跨 post 媒体冲突判定，milestone 选择器自报的 publishable 也在任何对象进入闭包前就完成计数，两者都会高于真实可选中数。
- `release pool-precheck` 必须复用 `pool-build` 的同一判据链且不写任何 release 产物，覆盖候选发现、delivery issue、版本去重、`candidate_closure`、跨 post 媒体 identity 与 slice 冲突、重选循环、standalone entity 闭包与 milestone 预算。禁止为预检建立第二套判据实现。
- 预检必须区分「经完整判据链得出」与「全池被拒后逐对象重放得出」两种排除来源，并为每个被排除对象给出 typed code。判定为不通过是结构化结论，不是预检自身失败。
- canonical 不变式：canonical 对象只存 `objectKey`、`sha256` 与 `assetId` 私有 CAS 引用，禁止写入 `publicSliceKey`。公共切片键只能是 release 构建期派生物，使已入池对象在媒体交付形态变化时可原地复用。

<a id="req-009"></a>
### REQ-009 媒体字节的双归属是 publish 的前置而非后续补救

- canonical 对象引用的每份媒体字节必须同时落入两处才允许对象达到 approved：内容库负责运行期解析，受版本控制随体负责可重建性。任一处失败，publish 事务失败关闭，对象不得落地。
- 内容库按契约落在工作树之外且不可从版本控制重建，因此只入库的对象是「在产出机器上 approved、在任何其他检出上不可交付」。该状态的暴露点是数月后的 release 构建报告摘要缺失，此时能解释它的 execution 证据已被回收，故不接受「先 approved 再补字节」的时序。
- 随体只覆盖 canonical 引用的子集，不是内容库的镜像：原始素材与中间产物仍只在库内。随体根是发布事务的写入目标，必须可被测试隔离，否则一次测试运行的字节会被当成生产资产提交。
- 干净检出的判据是 `rehydrate_media_holdings` 零 `unresolved_no_reference_bytes`；随体缺字节即门禁红，不得降级为告警。

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

## 4. 契约引用

- media processing policy：`quwoquan_data/schema/content/media_processing_policy.schema.json`
- release：`quwoquan_data/schema/release/release_header.schema.json`
- asset admission：`quwoquan_data/schema/release/release_asset_admission.schema.json`
- lifecycle policy：`quwoquan_data/schema/governance/content_distribution_policy.schema.json`
- environment readiness：`quwoquan_data/schema/release/environment_release_readiness.schema.json`
- research scale promotion：`quwoquan_data/schema/release/research_scale_promotion.schema.json`
- commercial transition：`quwoquan_data/schema/release/commercial_transition.schema.json`
- ship：`quwoquan_data/schema/release/ship_report.schema.json`
- campaign report：`quwoquan_data/schema/execution/content_campaign_report.schema.json`
- lane receipt：`quwoquan_data/schema/execution/content_campaign_lane_receipt.schema.json`
- 零合格原因共享值对象：`quwoquan_data/schema/_common/zero_qualified_reason.schema.json`
- 零合格不可续跑判定依据：`quwoquan_data/schema/execution/zero_qualified_basis_evidence.schema.json`
- reviewed closure adoption ref：`quwoquan_data/schema/execution/reviewed_closure_adoption_ref.schema.json`
- reviewed closure adoption receipt：`quwoquan_data/schema/execution/reviewed_closure_adoption_receipt.schema.json`
- release identity incident：`quwoquan_data/schema/release/release_identity_incident.schema.json`
- failed campaign reconciliation：`quwoquan_data/schema/execution/campaign_failed_execution_reconciliation_receipt.schema.json`
- interrupted review reconciliation / retry feedback：`quwoquan_data/schema/execution/campaign_review_interruption_reconciliation_receipt.schema.json`、`quwoquan_data/schema/execution/retry_review_feedback.schema.json`
- media workload object：`quwoquan_data/schema/execution/media_work_unit.schema.json`
- execution capacity policy：`quwoquan_data/schema/execution/execution_spec.schema.json`
- ReliableTask fleet 运行回执：`quwoquan_data/schema/release/reliabletask_fleet_report.schema.json`
- managed agent scheduler 观测：`quwoquan_data/schema/execution/execution_state.schema.json`

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
- THEN 四环境各自的 activation/readiness/App UAT receipt 绑定同一 `releaseId+manifestDigest+sourceIdentitySetDigest+releaseClass+productLifecycleState+appUatEnvelopeDigest`，逐环境绑定独立 import/readback 与 research isolation policy/proof，并按 Alpha→Beta→Gamma→Prod 冻结前一环境 passed receipt；匿名身份、公开媒体 URL、分享、导出或索引任一可用均 `GATE_BLOCK`。
- THEN commercial readiness 不存在，且任何未授权 asset ID 不得进入 `commercialAcceptedCount`。


<a id="gwt-003"></a>
### GWT-003 历史 reviewed closure 只能经精确身份采纳进入当前单 source campaign

- GIVEN 一个不可变 source release 已闭合 homepage/article/image/video、creator/tag/entity/media、review 与 rights，且同一 releaseId 的历史 identity collision 已以 append-only incident 记录。
- WHEN 使用现有 campaign 边界请求 `adopt-reviewed-closure`。
- THEN adoption ref 与 receipt 同时绑定精确 source release tuple、incident digest、payload/object/media/review/rights 闭包和全部上游 execution/source provenance，任一 digest、ref、字节或归属不一致即 `GATE_BLOCK`。
- THEN homepage/article/image/video 各得到一个新 execution，对象引用精确覆盖 source desired state，正文、媒体、review 和 rights 业务 payload 不变，当前 campaign/release header 只携带一个可活动 source identity。
- THEN identity incident 中的 `protectedExecutionIds` 精确等于全部观测 identity 的 execution closure，incident 存在时 discard/GC 保持 fail closed；重放同一 adoption 只能读取同 digest receipt，不得覆盖或变造历史证据。

<a id="gwt-004"></a>
### GWT-004 独立 semantic journal、池交付与规模晋级

- GIVEN selected semantic Provider/model 的凭据、runtime、网络与真实 startup preflight 为 `ready=true`，本次 active execution 各自冻结 semantic journal/source identity；pool delivery 另有受治理的 MongoStore/RedisReadyIndex generation、fence 与 worker bundle。capacity soak、workspace smoke、effective concurrency 与 resource samples 可以未运行、不可用或失败，且只形成诊断事实。
- WHEN 任意 Data 批次产生完成、质量合格且具备 Research 或 Commercial 授权范围的 Homepage、Article、Image 或 Video。
- THEN 每个合格对象立即幂等追加到统一池；失败、授权待定、重复或缺交付引用的对象分别报告，不撤销同批其他对象。
- THEN 每个实际启动的 task 分别形成 create-once typed 终态结果，campaign 只聚合这些结果；排队项、未启动项和诊断 sample 不得冒充 task 终态。
- THEN Mongo、Redis 或目标环境不可用时，source/compose/author/review 继续运行；reviewed 对象写入 delivery intent 并停止重复 semantic 调度，transport 恢复后按同一 digest exact-once drain。
- THEN 日常 Research Release 从 publishable 对象构建并可在未达到 milestone 时发布；Manifest 冻结后导入、Search、Recommendation、Homepage 和 Persona 数量必须全量一致。
- AND import 成功只到 `imported`；Search/Recommendation/Homepage/Tag/媒体与 Persona consumer 投影及 readback 全部 verified 后才可进入 `active`，失败 receipt 不得覆盖 previous active。
- THEN 累计唯一 publishable 达到 M100 `100/100/100/10` 时标记 M100 达标；M1000 与 M10000 分别只按 `1000/1000/1000/100` 和 `10000/10000/10000/1000` 判断，不依赖前驱 promotion、Provider、热度、恢复率或并行时长，超过下限的全部合格对象继续准入。
- THEN source-pool、Provider、workspace/soak/resource samples、实际调度重叠、恢复、配图率和视频热度保留在同一报告的 statistics 中，任何变化都不得改变 dispatch、对象准入与 milestone 数量结果。
- THEN 同一批或同一环境中的个别对象失败只把该对象标为 excluded/deliveryPending；冻结 Manifest 后仍全量一致、失败候选不替换 previous verified release。
- THEN 有 20 个质量、Research 授权与交付闭包均合格的视频时，Alpha/Beta/Gamma 的稳定选择均包含全部 20 个，M100 的 10 个视频只是里程碑下限而非发布上限。

<a id="gwt-007"></a>
### GWT-007 回收窗口让 output 稳态占用收敛

- GIVEN output 内同时存在被环境引用的 immutable release、带 `publish_ref` 的 task 证据、可重建缓存，以及历史 release 对已被回收 task 的引用。
- WHEN 执行 `release gc plan`。
- THEN 返回可执行回收计划：可重建派生物与超出保留窗口的过程产物列为可回收，发布证据与被环境引用的 release 列为受保护。
- THEN 历史 release 对已回收 task 的引用不使计划失败，而是解析到该 execution 的不可变墓碑：计划以 `reclaimedExecutions` 逐条读出 `executionId`、闭集回收原因与墓碑 ref，墓碑本体登记为受保护证据且自身不可成为回收候选。
- THEN 「从未物化」与「曾物化后被回收」不合并为同一种缺席：同一 execution 上 reconciliation 缺席证明与墓碑并存时判否，已墓碑的 execution 重新出现在磁盘上时判否。
- THEN 连续多轮 campaign 后 output 稳态占用不随累计执行次数单调增长。

<a id="gwt-009"></a>
### GWT-009 对象下限、工作单元数与并行上限三值分离

- GIVEN 一个 scale 请求把对象下限冻结为 `approvedQuota=100`，把本次工作单元数冻结为 `targetObjectCount=180`，把交付并行上限冻结为 `fleetMaxConcurrentWorkers=8`。
- WHEN campaign 从该请求构建 immutable execution policy 并派生 ReliableTask job set。
- THEN 执行策略分别保留 100、180 与 8 三个值，没有任何字段同时承载其中两个语义。
- THEN 派生 job 数等于 180 而与对象下限 100 无关，任一时刻同时运行的 worker 进程数不超过 8。
- THEN 同一请求把 `approvedQuota` 提高到 1000 时并行上限仍为 8，只有 wave 数随 job 数变化。
- THEN 三值中任一项缺失即 fail closed，不得由另一项默认补齐，也不得回落到「worker 数等于工作单元数」的派生。

<a id="gwt-010"></a>
### GWT-010 批次绝对截止跨进程重启不续期

- GIVEN 一个已冻结 execution 的 `fleetBatchDeadlineEpochSeconds` 已持久化为绝对时间，且该批次已运行到只剩少量剩余时间。
- WHEN 承载该批次的 worker 进程被强制杀死，随后由同一 execution 重新拉起并重建其子进程执行环境。
- THEN 重启后注入的可用时间等于 `max(0, fleetBatchDeadlineEpochSeconds - 当前时间)`，不得重新注入完整批次预算或完整单对象超时窗口。
- THEN 剩余时间为 0 时不再启动任何新 job，已在运行的 job 按单对象 wall-clock 上限收敛并写入 typed deadline 终态。
- THEN 单对象 wall-clock 上限与批次剩余时间取更小者，重启、重试与 lease 续租都不得放大二者中的任何一个。
- THEN 绝对截止在 execution 冻结后不被任何恢复路径改写，需要更多时间只能由新的 `retryOf` 冻结新的绝对截止。

<a id="gwt-011"></a>
### GWT-011 fleet 运行回执可复核容量并给出可行动终态

- GIVEN 一个 execution 的 ReliableTask 交付阶段已终止，需要写入 fleet 运行回执。
- WHEN 回执按 canonical 契约写入并校验。
- THEN 回执必须同时携带 `fleetPeakConcurrentWorkers`、`fleetWaveCount` 与 `fleetBatchDeadlineEpochSeconds`，缺任一项校验失败且回执不成立。
- THEN 实测峰值不超过冻结的 `fleetMaxConcurrentWorkers`，wave 数与 job 数和冻结上限一致，绝对截止与执行策略中的冻结值相同。
- THEN 零合格对象时回执携带唯一 typed 原因，七种原因分别区分来源为空、来源访问被拒或网络不可达、批次截止耗尽、全部对象质量被拒、可续跑中断、全部对象因闭包超出单对象存储预算而在 publish 准入被拦下，以及 `在场可用` 集合非空但全部候选实体在 target set 冻结前的选择器准入被排除，不得把它们合并成同一个 `blocked` 汇总值。
  每个原因值只绑定一个观测阶段。「全部对象质量被拒」只能取到 review 阶段，「全部对象超出单对象存储预算」只能取到 publish 准入阶段，publish 准入的结论取不到前者，两者的阶段取值范围都不得被放宽。
  「全部候选实体被选择器准入排除」只能取到 target set 冻结前的选择器准入阶段。该阶段严格后置于实体级来源判定，它与来源发现阶段的原因值互相取不到，其阶段取值范围同样不得被放宽。
- THEN 可续跑中断给出精确可续跑 refs，其余六种原因给出不可续跑的判定依据，运营者只读回执即可决定续跑、修来源、重新冻结时间预算、缩减对象体量还是扩大候选范围。
  缩减对象体量只由超预算原因取到，它指向减少该对象引用的资产数、换掉单张超出预算的素材或把该对象拆成多个对象，不指向修来源，也不指向改写预算数值。
  扩大候选范围只由准入零通过原因取到，它指向扩大候选区域范围或按治理流程调整多样性策略，不指向修来源，也不指向改写多样性阈值数值。该原因在不可续跑依据之外还给出逐实体的准入排除 refs，指向选择器在冻结选择证据上已声明的排除条目。
- THEN 回执中的并发、wave 与时间观测只是运行事实，不改变对象准入、publish、finalize 与 milestone 结果。

<a id="gwt-016"></a>
### GWT-016 同一请求的四载体数量可逐 surface 闭环复核

- GIVEN 一个已确认请求为 homepage/article/image/video 分别声明正整数对象数量，且同一请求沿现有单轨形成 immutable Research release。
- WHEN Alpha 依次完成 import、projection/API/media verify、activate，并以 production Remote composition 运行 App CaseResult。
- THEN 每载体均满足 `selected = imported = projected = verified = readback = qualified`。`qualified >= requested` 表示该载体达标；`0 < qualified < requested` 表示 partial，`shortfall = requested - qualified`，已合格对象仍可见而不伪造成达标。
- THEN entity homepage 只在对象主页验收，article 只在文章 surface 验收，image 只在图片 surface 验收，video 只在视频 surface 验收；每个 surface 分别形成绑定同一 release digest 的 CaseResult，micro 不在本 Story 的载体或验收范围内。
- THEN import、projection 或 API/media verify 在 activate 前失败时 candidate 停在对应 typed 终态，previous active pointer 不变，且不生成本 candidate 的激活成功事实。
- THEN activate 后任一 surface CaseResult 失败时生成绑定本 candidate 与 previous active 的 rollback receipt，恢复 previous active pointer；receipt 可读出 rollback 起止时刻与 `durationMs <= 300000`，超过预算或 pointer 未恢复时终态为 canonical `rollback_failed` 而不是成功。本次失败 CaseResult 与其它 surface 的真实通过证据均保持可读，旧 release/receipt 不得替代本次失败项。

<a id="gwt-019"></a>
### GWT-019 空工作区只通过 measurement-only bootstrap 生成首份容量授权

- GIVEN `local-apple-silicon` 的干净工作区没有受版本控制的 capacity receipt、没有 execution output，且 fresh `cursor_grok` preflight 已通过。
- WHEN Data owner 启动 capacity calibration bootstrap。
- THEN bootstrap authority 固定为 measurement-only、单 worker、M100 exact measurement workload，不读取日常 runtime default 或历史 capacity 数值，也不创建 WorkRequest、content execution、author/reviewer、pool-delivery、canonical object、release 或环境成功事实。
- THEN bootstrap 为每个测量对象写独立 timing 终态，并生成 passed fleet report；任一对象、Provider、资源采样、deadline 或证据写入失败时输出 typed blocker，零 capacity receipt 可见，既有内容状态不变。
- THEN `capacity_calibration_cli` 只消费上述 fresh fleet/object timing，对候选并发执行每档 100 次真实 `cursor_grok` probe，并把 Provider/resource/fleet/timing closure 与 applicability 写入 create-once receipt；任一 ref/digest/host/provider 漂移均 fail closed。
- THEN receipt 提交为当前受版本控制真相源并通过无 skip 的摘要校验后，日常 execution policy 才能绑定它并启动；bootstrap authority 不能被日常 task、retry、promotion 或环境入口选择。

<a id="gwt-020"></a>
### GWT-020 receipt 协议 execution 十阶段生命周期可达 succeeded

- GIVEN 一个 receipt 协议 execution（单 article lane）按 SKILL.md 阶段表推进，每阶段 POST 以 `task stage-record` 落 create-once receipt，`_shared/receipts/` 链是进度唯一真相源。
- WHEN `5.review` pass 后 execution 进入 publish → release → ship 后缀。
- THEN publish 阶段存在 receipt 协议下的正向原子链：成品物化（对象根 `article.md` + `manifest.json`）与 approved 对象写入 canonical publish 由单命令或冻结序列完成，其 PRE/POST 判据不依赖退役编排层的 `verify execution-readiness` 或 `model_readiness.json`。
- THEN article 对象布局归 `posts/article/**`；布局漂移在 `0.plan`/`1.download` 即被 `verify content-execution-layout` fail closed 拦截，`verify stage-artifacts --through` 在每个阶段截面都能发现全部对象。
- THEN ship 落 `next=END` receipt 后 `execution_state.status=succeeded` 且该 receipt 是 succeeded 的唯一合法来源，`verify release-lifecycle` 与 `stackctl verify --env gamma` 通过。receipt 链完整覆盖十阶段并保留逐阶段 `actor.host/actor.session` 证据，允许多宿主接手。
- THEN 驱动层保持薄 IO 契约：`task stage-record` 同步 execution_state 有独立可测断言，`lane-claim` 与 `stage-record` 的 CLI 退出码 0/2/3 语义冻结，stage 枚举只有单一真相源。
- THEN `loop_driver.sh` 超时按进程组终止宿主子进程，claim 获取与释放只属执行者会话，驱动只做 `--check` 只读预检且 round timeout 不得越过 claim TTL 形成双写窗口。

<a id="gwt-021"></a>
### GWT-021 只读预检与 pool-build 的选中集一致且不写任何产物

- GIVEN 一个同时含已准入对象与被排除对象的 canonical 池。
- WHEN 运行 `release pool-precheck --milestone M100`。
- THEN 预检报出的可选中集与同一池上 `pool-build` 真实判据链的选中集逐条一致，每个被排除对象带 typed code，且预检运行前后 publish 树逐字节不变。
- THEN 整池被拒时预检仍逐对象给出选择器层与闭包层的排除原因并标注排除来源，不塌陷为单条聚合错误。
- THEN 预检报出的真实可选中计数不高于 milestone 选择器自报的 publishable 计数，两者不一致时以预检为交接判据。
- THEN 载体目标与缺口由 milestone 策略派生，预检不自带第二份载体或配额常量。

<a id="gwt-022"></a>
### GWT-022 publish 对媒体字节双归属 fail closed

- GIVEN 一个引用媒体字节的对象事务包。
- WHEN 事务 apply 完成。
- THEN 该字节既可经内容库按摘要解析，也存在于受版本控制随体，且随体内容与 canonical 文档冻结的摘要一致。
- THEN 随体不可写时事务失败关闭且 canonical 树未出现该对象，不产生 approved 但不可交付的中间态。
- THEN 字节与声明摘要不符时拒绝随体，且失败不留下部分写入的残留。
- THEN 同一对象重复提交不增加随体条目，随体根可由环境重定向从而在测试中隔离。

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
- THEN 最近一次 PASS proof 被复用并重绑当前 run，复用来源 run 标识写入证据本体，原 proof 文件字节不变；复用前 proof 全量重验（release 身份、manifest digest、policy 快照与 PASS 内容闭包）。
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

## 6. 依赖

- 前置要求：父能力的 execution、review 与 release 契约。
- 上游事实：来源、目标集和审核结果。
- 下游结果：immutable release 或结构化阻断报告。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 多载体 research 环境消费与规模证据

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前仍缺足量专业来源池、真实四路累计数量达到规模里程碑，以及四 surface 的 App 端 CaseResult，所以最终规模闭环保持 `GATE_BLOCK`。单 release 尺度的链路不属于该阻断：canonical pool → immutable release → environment consumer 的精确引用闭包、execution 逐项终态与池交付证据已由 receipt 协议 execution 走通（`GWT-020`），App 消费面缺口由 [`OPEN-015`](#open-015) 承载；fresh soak、四个同时 workspace、固定并发或 remote executor 主机数量也不属于该阻断。
- 完成判定：`GWT-001/GWT-002/GWT-004/GWT-016` 有 local_contract 与真实 Content importer、Search、Recommendation、Homepage、Persona readback。entity homepage→对象主页、article→文章 surface、image→图片 surface、video→视频 surface 分别形成同 release digest 的 App CaseResult，且 micro 明确不属于 Data homepage。依次达到 M100、M1000、M10000 的累计唯一数量并能从统一池构建和发布对应 immutable Research Release。
- 依赖：Data/Runtime/Service owner维护对象生成与池追加；Testing/Ops owner负责同一 Research Manifest 在 Alpha/Beta/Gamma/Prod 的独立 import/private-isolation/verify/activate/rollback/replay，Commercial 转换另立显式授权 release。Provider 与 remote executor 只影响生成吞吐和计划时间，不改变已合格对象准入。

<a id="open-002"></a>
### OPEN-002 acquisition receipt 永久缺席使回收计划仍不可执行

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍有一类引用没有合法终态，回收窗口因此仍未真正打开。`release -> task` 引用已由 [`DEC-035`](../design.md#dec-035) 的不可变墓碑裁定并落地，存量 output 的 11 个永久缺席 execution 已由 `release gc backfill-tombstones` 补齐终态，治理证据面已由 [`DEC-036`](../design.md#dec-036) 收敛，`release gc plan` 因此不再在 execution 引用与运行时包 payload 上判否。剩下的是 acquisition receipt：两份 rights 证据引用的 receipt 已永久不在磁盘上（`data/local/workspace/source-acquisition/receipts/be9dabf1….json` 4 处、`video/receipts/491bd7f6….json` 2 处），回收器在 `DATA.GC.REFERENCE_MISSING` 上仍然 `GATE_BLOCK`，稳态占用仍未开始收敛。
- 尚缺实现：acquisition receipt 的缺席终态尚无承载物。它不能直接套用 execution 墓碑：acquisition receipt 记录的是权利来源事实，把它的永久消失自动标成终态会抹掉一个真实的合规信号，因此需要先判定「rights 证据引用的 receipt 永久缺席」是可接受终态还是权利证据缺口。
- 尚缺验收证据：缺 `GWT-007.t1` 与 `GWT-007.t3` 在真实存量 output 上的一次可执行 `release gc plan` 与 apply，以及连续多轮 campaign 后稳态占用不单调增长的实测。`GWT-007.t2` 与「两种缺席不合并」已由 `test_canonical_gc_execution_tombstone__reclaimed_terminal_state__contract__local_contract_test` 覆盖。
- 完成判定：acquisition receipt 缺席的终态归属落为显式裁决并有 local_contract 锁定，随后 `release gc plan` 与 `release gc apply` 在真实存量 output 上各成功一次，且 `GWT-007.t3` 取得多轮实测。
- 依赖：权利证据侧 owner 判定 rights 证据引用的 acquisition receipt 永久缺席是否可接受；`GWT-007.t3` 依赖真实放量窗口。

<a id="open-006"></a>
### OPEN-006 受治理容量 calibration 无可自举的 M100 receipt

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前用于授权本机 `cursor_grok` 容量值的 receipt 字节不在受版本控制真相源中，无法复核其逐对象 timing、Provider probe 与资源证据。measurement-only bootstrap path 已实现并已锁边界（authority 固定 `measurement_only`、单 worker、M100 workload、只读自己的 measurement safety policy、create-once 状态机、不写任何 publish/release/环境成功事实），但它还没有在真实 Provider 上跑过一次，因此 execution policy 仍无 receipt 可绑定。规格复述的旧数值不能反向合成 receipt，也不能继续授权 execution policy。
- 尚缺实现：无。bootstrap path、`capacity_calibration_cli` 与 create-once receipt 写入链均已在场，缺的只是它们在真实资源上的一次运行输出。
- 尚缺验收证据：只剩三项需要外部资源的实测。一是在 `local-apple-silicon + cursor_grok` 上完成一次真实 M100 measurement soak。二是对每个候选并发档执行 100 次真实 `cursor_grok` probe。三是把 `capacity_calibration_cli` 产出的 receipt 提交为受版本控制真相源。`test_repository_capacity_calibration_receipt_is_self_contained` 在干净检出上因此必然 `GATE_BLOCK`（receipt is missing）。禁止以手写 receipt 或改小断言的方式转绿——伪造的 receipt 不可能命中已冻结摘要，改断言等于放弃摘要绑定。
- 完成判定：`GWT-019.t1..t4` 的 authority、composition 与状态机边界已由 `test_capacity_bootstrap__measurement_only__contract__local_contract_test` 覆盖，「真实 bootstrap 进程只推进 measurement 且 canonical/release/environment 成功事实增量均为 0」已由 `test_capacity_bootstrap_cli__measurement_only__contract__api_integration_test` 覆盖。剩下由 live reliability soak 完成真实 M100 measurement 与每档 100 次 probe，随后由 `capacity_calibration_cli` 产出并提交新 receipt，repository gate 在干净检出校验其摘要与 applicability，删除动态 skip，同步更新 `REQ-006` 与设计中的 calibrationId/摘要，并重新直接覆盖 `GWT-009.t4`、`GWT-010.t4` 与 `GWT-011.t2`。在此之前该容量来源保持 `GATE_BLOCK`，不得由默认常量、runtime profile 或探针观测替代。
- 依赖：bootstrap 与日常 execution policy 的单向边界已冻结并有测试守，剩余依赖全在外部资源侧。推进本 OPEN 的前置条件有三条：真实 `cursor_grok` provider 额度可用且 fresh preflight 通过。本机 fleet 资源可支撑 100 对象单 worker soak 跑到 measurement 终态。干净工作区无受版本控制 capacity receipt 且无 execution output。三者任一不满足时本 OPEN 不可推进，缺失证据不可由事故记录、规格文字、受控输入或 fixture 合成。

<a id="open-009"></a>
### OPEN-009 confirmed 请求的 release、环境与 App 消费后缀尚未闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 immutable release、环境 import/readback 与四个 App surface 尚未绑定同一 confirmed WorkRequest/compile receipt 身份，因此仍不能证明一份意图的四载体数量沿现有单轨闭环到环境与 App 消费。编译前缀由 [`work-request-compilation`](../work-request-compilation/spec.md) 的 `OPEN-001` 承接，入池段由 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md) 的 `OPEN-004` 承接。
- 尚缺实现：真实 confirmed 请求入池后的对象尚未沿 canonical pool、immutable Research release 与环境 import/readback/App CaseResult 消费链贯穿同一 identity。
- 尚缺验收证据：缺少 `GWT-016.t1..t4` 绑定同一 immutable candidate 的 release/import/readback、四 surface production Remote CaseResult 与失败 rollback receipt。
- 完成判定：`GWT-016.t1`、`GWT-016.t3` 由 release/import/projection/verify/readback api_integration 覆盖，`GWT-016.t2`、`GWT-016.t4` 由 production Remote user_acceptance 的四个独立 App CaseResult 与 rollback receipt 覆盖。
- 依赖：上游编译与入池 OPEN 先行关闭，再沿 canonical pool 与 immutable Research release 形成 `GWT-016` 的 import/readback/App CaseResult；在这些新鲜证据形成前不得用 local_contract、fixture 或旧 receipt 关闭本 OPEN。

<a id="open-012"></a>
### OPEN-012 receipt/claim 薄驱动层缺少行为级测试锚定

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：receipt/claim 驱动层的关键行为缺少直接测试或门禁，语义漂移只能靠人工发现。`task stage-record` 对 execution_state 的同步、`writing_pack` schema 校验失败路径、`lane-claim` 与 `stage-record` 的 CLI 退出码语义（0 成功、2 参数拒绝、3 冲突）均无独立 local_contract。orchestration 与 handoff-protocol 文档所述判据与实现之间没有漂移门禁。
  三项驱动层实现缺口已清偿：`loop_driver.sh` 的单轮 hard timeout 改为终止整个会话进程组（`set -m` 建组、`kill -9 -$pid` 杀组），宿主派生的孙进程不再残留；`--round-timeout` 与 claim TTL 的关系由 `task lane-claim --check --round-timeout-seconds` 在驱动启动时判定，超出「TTL 减安全余量」即退出码 64，两者关系不再靠默认值巧合成立；十阶段 stage 闭集收敛到 `core.control_types.ReceiptStage`，`RECEIPT_STAGES`、`OBJECT_STAGES`、工作包目录闭集、`stage_artifact_contract.STAGES` 与 `verify --through` 的 CLI choices 全部由它派生。
- 尚缺实现：`task stage-record` 的 execution_state 同步、`writing_pack` 校验失败路径与 CLI 退出码语义仍无独立 local_contract；orchestration/handoff-protocol 的文档-实现漂移门禁仍缺。
- 尚缺验收证据：上列剩余各行为的 local_contract 或门禁，每项一测且不放宽生产语义。
- 完成判定：`GWT-020.t4..t5` 成立。
- 依赖：无外部阻断。

<a id="open-015"></a>
### OPEN-015 research release 私有媒体的 App 消费面与正式 runtime 验收未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍未闭合 App 消费面与正式 runtime 验收面，缺口使 research release
  只能被 API 层消费核验，不能被 App 端用户面消费。数据侧私有媒体交付链——release
  payload 按 `releaseClass` 分流 `privateObjectKey`、三个 importer 存相对 CAS key、
  静态媒体源对私有前缀拒绝匿名 GET、消费期短签签发与 research 会话操作白名单——由
  [`DEC-031`](../design.md#dec-031) 与 [`DEC-032`](../design.md#dec-032) 承载并有
  probe 真实 HTTP 证据。
- 识别现场：`20260825-homepage-m1-first` 在 gamma 的 `research-isolation-probe` 全段
  PASS 且 research readiness receipt passed，但同环境 `stackctl verify --kind all
  --profile integration` 的 health user availability 在 `device_bound` 层缺 consumer
  lease receipt、在 `content_live_passed` 层缺 App 内容 UAT receipt。
- 尚缺实现：
  - App 私有媒体消费边界（[`DEC-033`](../design.md#dec-033) 承载）核心已落地：
    统一异步 grant 协调器承载单飞合并、TTL 安全窗复用、typed 失败与单次
    强制换签 refresh；缓存身份不含签名 query；`SignedGrantImage` 桥接原子
    与 feed 图/封面、作者头像、persona 头像、对象主页 introduction 四路
    surface 的 typed `accessMode` 分流接入完成。分流判据已收敛为唯一入口
    `MediaDeliveryImage`，四种输入形态各自独立判否：私有交付且资产身份在场
    走短签；声明私有却缺资产身份落判否终态而不回退公开 URL；`public` 与
    契约缺席走公开候选；渲染取值整体缺席落缺席终态。判否终态带恢复动作，
    自动换签仍限一次，用户可点击重试，调用方分流契约误用则不给恢复动作。
    视频封面三个渲染点（占位、延迟、失败覆盖层）与沉浸文本 moment 背景已
    接入该入口；视频封面的资产身份改取 `coverAssetId`，旧实现取视频自身
    `mediaAssetId` 并以 post 标识兜底的行为已被测试锁定禁止。
    首页信息流的单图、九宫格、多图轮播、视频卡静态封面与视频卡播放态封面
    原先各自手写一次 `isSignedGrant ? 私有 : 公开`，已全部收口到该入口，
    「什么算私有」不再有第二真相源；其中视频卡静态封面原本回落裸 URL，
    与同函数内已算出的 typed 绑定构成同一封面两套取值，私有封面会在
    未播放时空图，已一并修正。
    收口面由 `media_delivery_typed_binding_lock` 防回潮：公开图片原子只允许
    作为 typed 入口的 `publicBuilder`/`readyBuilder` 分流回调出现，已 typed 化的
    组件 API 不得重新暴露裸 URL 入参，两种回潮形态各自判否并有注入式反向验证。
    文章图侧的换签与渲染已解耦：私有原子新增换签成功后的渲染委托，文章图组件
    新增短签单候选直传入口且以稳定资产身份为缓存键，因此私有文章图仍走文章自有
    的静默占位阈值、延迟指示与失败重试，不会出现「公开图与私有图两套观感」。
    视频本体的私有播放通道已就位：播放器取址收敛为「公开 canonical 交付引用」
    与「已校验短签交付」两种 typed 形态且互斥在场，私有路走渐进式 MP4 单签 URL，
    分段 Range 由原生播放器发起、交付边缘按段复算签名，因此不需要逐段换签；
    播放失败触发一次强制换签，重试仍败停在判否而不循环。私有路不参与 HLS 候选
    升级——HLS 需要分片各自带签名，属未决设计，触发条件为「release 出现 HLS
    私有视频时」，在此之前私有 HLS 保持显式判否。视频交付引用以 post 标识冒充
    媒体资产标识的旧行为已按封面侧同一禁令锁定。
    原先未接入的三处图片消费点已全部收口。沉浸全屏图书的页序从 `List<String>`
    改为 typed 交付绑定：私有页经协调器换签后短签地址单候选直传，不进入公开候选
    推导也不经 CDN 变体改写签名；声明私有却缺资产身份落显式判否而不回退公开
    URL；既有「查看原图」直连调用改为委托协调器，短签校验因此对该路同样生效。
    文章图侧走 contracts-first：`PostArticleAsset` 声明 `accessMode`，import 侧
    `articleAssetManifest` 与 `mediaItems` 两条独立路径按 release header 的
    `releaseClass` 同一单点映射逐项打标——只打其中一条会让文章内嵌图在 research
    相位没有任何交付声明；App 侧一路透传到内嵌图消费点并保住文章自有的加载体验。对象主页 detail hero
    同样走 contracts-first：`homepage_detail_view` 补 `coverAssetId` 与
    `coverAccessMode`，服务端复用 introduction 的同一 cover 配对规则，App 侧
    hero 的三个渲染位（身份图、紧凑工具栏头像、背景层）共用同一绑定推导。
    收口口径为全消费面而非按清单枚举的若干 surface。枚举清单本身就是遗漏源：
    它只盯已收口的文件，新增或从未被想起的消费点不在册，漏接在门禁上不会红。
    防回潮锁因此是全仓扫描 `media_delivery_consumer_sweep`，扫 `quwoquan_app/lib`
    全部直连公开渲染原子的位置，每一处都必须落到待收口基线或带理由豁免之一，
    不在册即判否。首扫 110 处，其中 61 处待收口、49 处按设计不消费 release 交付；
    基线现为零，未登记新增与册子腐化两种漂移各有注入式反向验证。
    经 typed 入口接线的消费面覆盖：共享预览骨架四件与其作品 Tab、record 卡与
    圈子创作网格调用点；关注流文章卡封面与作者头像；文章全屏图书 DI 入口与
    环绕排版内嵌图；沉浸栏作者头像；对象主页 introduction 横滑资产与主页选择器；
    搜索结果卡、搜索建议、灵感卡与 flat 卡缩略；互动 Tab 预览图。搜索族与互动
    预览走 contracts-first：`CanonicalSearchContentHit`、`OwnerSearchHit`、
    `HomepageSearchItemView`、gateway `searchPage` 项与 `ProfileInteractionActivity`
    分别补 typed 交付声明，服务端按与封面同源的配对规则组装，索引写入侧同步
    投影 `coverAssetId` 与 `coverAccessMode`。手写 `isSignedGrant ? 私有 : 公开`
    的三元分派同样收敛到唯一入口，覆盖首页关注流作者头像、对象主页 introduction
    cover 与横滑资产、persona 头像三处；它们功能正确，但把判据复制成了副本。
    经证据判定不属 release 交付因而落豁免的面包括：圈子域封面与成员头像，其值
    由 `CreateCircle` 用户命令写入；persona 背景，release creator 导入只写 avatar；
    交集视觉，其取值为 persona avatar 与静态 icon 注册表；video timeline sprite，
    由媒体处理管线产出且 manifest 强制 public slice；评论附件与评论者头像，
    release payload 不含 comments；chat 与 RTC 的会话媒体、成员头像；编辑器与
    上传本地预览。`contentPreview` 亦经三重证据判定不由 release 导入填充：导入器
    无该字段、release payload 无该字段、写端口只暴露 `UpsertReviewSummary`，
    因此不加一个永远为 null 的契约字段。
    一处不一致尚未处理：统一搜索的 ES 索引与读模型不投影 `coverUrl`，而 entity
    侧 `SearchHomepages` API 投影它，因此同一个主页在两条搜索路径上封面能力不同。
    该差异不构成私有媒体漏接，因为统一搜索的主页命中根本不渲染封面；收敛触发
    条件为「统一搜索要展示主页封面时」。
  - 交付绑定契约缺口已闭合：三路 App 投影均保留 `MediaDeliveryAccessMode`
    与逐媒体资产标识，content importer 的 `mediaItems` 键漂移已修正，
    `assetId` 以对象标识冒充媒体资产标识的旧行为已被测试锁定禁止。
  - research 相位的 App 证据 wiring：`content_live_passed` 的回执查找已修正——一次
    UAT 可绑定多个 target 故其聚合回执落 repo 级 runs 根，消费方原先只扫环境根使
    该层结构上不可达，现两根同扫且代际判据仍由回执内 runtimeBindings 与
    startupAttemptId 决定。research 相位的探针语义亦已对齐：匿名内容面收敛为
    `no_active_release` 空页后不再被判为内容缺失，probe 按服务端 `transient`/`retry`
    恢复指令重试并把被吸收的抖动留痕在回执里。lease 字段位置不一致已修：Patrol
    分支原先只把 lease 留在 `runs[].evidence.consumerLease`，而聚合器从
    `runs[].consumerLeaseId` 顶层标量收集，于是聚合回执的 `consumerLeaseIds`
    恒为空、`device_bound` 的 lease 子集判定永远不成立，且失败信息看起来像设备侧
    问题会把排查方向带偏；现 Patrol 分支按 direct-flutter-run 分支同一个键填充，
    聚合器仍只认一处，有 local_contract 锚定。lease 判据冲突已裁决并落地：该层
    核验的是「lease 曾在本代际有效」，因此释放 lease 改为写 `released` 状态并保留
    回执（互斥由状态承担，代际证据由保留的三个 digest 承担），而不是删文件；
    `released` 不计入占用故不阻塞其他消费方抢占，超过最大寿命按 stale 处理；
    `device_bound` 接受 `released` 且代际匹配的 lease，跨代际 released 仍判否。
    剩余一项：既有 UAT 断言假定公开媒体 URL，须在消费面接线完成后按 typed 绑定
    改写，否则断言与实现不匹配。
  - Patrol test host 的启动前提未就位，由
    [`OPEN-007`](../../../runtime/runtime-config/environment-topology-and-packaging/spec.md#open-007)
    承载：test host 拿不到 runtime config package 因而页面 suite 停在启动失败，
    `content_live_passed` 在该缺口闭合前无法产出。同环境下生产 App 的
    `direct-flutter-run` 已连续四次以 `external_runtime_package` 到达 `routerShell`
    安全终态，故该阻断属 UAT 宿主基础设施而非被验收的私有媒体消费面。
  - 运维加固面（[`DEC-031`](../design.md#dec-031) 委托）已落地：边缘 HMAC 复算由
    共享 verifier 加 local_media_origin/gamma Caddy forward_auth adapter 承载；
    research isolation probe 扩展为 15 操作，对签发返回的 release 真实私有 key
    追加伪签名、篡改到期负例与 Range 逐段复算探针；真过期负例由 Go/Python
    共享 parity 向量在 local_contract 层锚定。剩余为 gamma integration 全量
    profile 的实跑证据：15 操作 research isolation 已在 gamma 实跑 PASS，
    release-bound feed readback 在匿名收敛修复后亦已实跑通过，尚缺一次三者
    同代际的完整 verify run。
  - 私有视频的端侧播放通道待设计先行：图片可以「换签一次拿到地址再渲染」，
    视频不能——播放时长常超过短签 TTL，且 HLS 每个分片各自需要签名。因此
    需要先决定两件事再实现：TTL 到期时如何在不丢失播放位置的前提下换签，
    以及分片签名由端侧逐个换签还是由边缘按会话授权。设计未定前端侧保持
    显式判否，不以公开地址代播。
- 尚缺验收证据：`stackctl verify --env gamma --kind all --profile integration` 无失败项
  （含 `device_bound` 与 `content_live_passed` 层），以及 App 对 research release
  四路媒体、创作者头像与对象主页 introduction assets 的短签消费 CaseResult，
  surface 覆盖对齐 `GWT-016` 的 per-surface 验收锚点。
- 完成判定：App 在 research 相位可经短签消费四路媒体、创作者头像与对象主页
  introduction assets 并产出内容 UAT receipt，`GWT-020.t3` 的
  `stackctl verify --env gamma` 子句在 integration profile 下整体成立。

<a id="open-016"></a>
### OPEN-016 超尺寸资产的 provider 无关性尚缺真实 provider 证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺真实 provider 上的观测。[`REQ-012`](#req-012) 的预算判否已在 `1.download` 截面成立并由 `local_contract` 覆盖，但覆盖用的超尺寸源体是本地编码构造的。`pageImageRenditionWidth` 的服务端缩略图偏好只命中 `upload.wikimedia.org` 的 commons 非 thumb 路径，因此「与 provider 无关」这一条在 `pinterest`、`tuchong`、`openverse` 上仍只有推断而无观测。
- 尚缺验收证据：一个 `api_integration` 以真实非 Wikimedia provider 的超尺寸资产走完 `1.download`，证明判否与降采样都不依赖服务端缩略图路径的存在。
- 完成判定：[`GWT-027`](#gwt-027) 的降采样与判否两条结果子句在至少一个无服务端缩略图路径的真实 provider 上有 `api_integration` 证据。
- 依赖：无外部阻断；预算声明位与判否边界已由 [`REQ-012`](#req-012) 冻结。
