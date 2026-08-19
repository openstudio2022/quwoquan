# L3 Story：多载体内容与主页发布 (`multi-carrier-release`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-008 / SCN-014`](../../../spec.md#scn-014)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容运营者，我希望文章、图片、视频和主页对象以独立 execution 分别调度和生产，同时共享冻结实体目录与 release 边界，从而能分别恢复失败并复核来源、媒体、实体与环境消费是否闭合。

## 2. 范围与非目标

### In Scope

- 四个 carrier execution 共享不含运行身份的 canonical entity catalog digest，各自冻结 target set、quota 与终态。
- 各载体复用同一创建、审核、promotion 和 ship 生命周期。
- article lane 在冻结 target set 之前完成实体级来源预筛，并把候选级拒绝原因聚合为实体级单一首要失败原因。
- Research 与 Commercial 共用 acquisition、semantic、review 和 canonical pool；只在 immutable release build 时按逐对象 `usageScope` 与全部 entity/post 资产的商用权利闭包选择不同子集，不建立第二套 commercial workflow、pool 或 semantic queue。
- 批次级/跨载体聚合门只作目标与统计；四载体共用 acquisition/rights/distribution admission，research 只放宽未验证的分发权利，不放宽访问控制、内容安全、隐私、未成年人、恶意文件、去重、实体相关性、质量或可播放性。

### Out of Scope

- 为不同地区或载体维护第二套发布目录与运行台账。
- 绕过登录、付费墙、验证码、访问控制、DRM 或平台技术限制取得素材。
- 直接生成图片或视频，或将 deterministic image-sequence 冒充已取得的可播放视频。
- 改变 homepage、image 或 video 既有的供给与来源判定机制：article 实体级来源预筛由本 Story 约束，image/video 继续由 immutable acquisition manifest/receipt 的 exact pair 冻结 workUnit（见 `REQ-001` 与 `GWT-006`）。
- article 来源预筛的匹配置信度、最小正文字数与探测预算的具体数值（见 `OPEN-004`）。
- 来源发现阶段存活心跳的间隔与判定过期的阈值的具体数值（见 `OPEN-005`）。
- 冻结期多样性准入的每实体累计上限与 Top-N 上限数值：阈值由多样性策略的既有 owner 单点拥有，本 Story 只消费其准入结论，并约束该结论的归属、呈现与批次级零合格归因。

## 3. 行为要求

### REQ-001 多载体统一发布边界

- 每个发布对象必须闭合 creator、tag、entity、media 与 source 引用；运行 receipt 只能写入输出目录，不得回写静态真相源。
- homepage、article、image、video 不以彼此的 execution 或 publish 结果作为运行前置；post 只依赖可解析的 canonical entity identity。
- 本次请求中的 active execution 必须从同一不可变 source-definition capsule、execution bundle 与 entity catalog digest 形成彼此独立、可分别调度的 workload；调度器可按当时可用容量串行或重叠运行，任一时刻不要求全部 active workload 同时运行。固定四 lane 并发、固定 worker 数、固定数量的同时 workspace 或 capacity soak 结果均不得作为 submission、dispatch、对象准入或 promotion 前置。单一载体失败不得覆盖其他载体工作包，也不得阻止其他载体已合格对象发布。capsule 封存后不得再用 live worktree 漂移否定该 execution。
- `task execute --stage submit-only|campaign-run|campaign-freeze|campaign-lane-run|campaign-finalize|review-only` 是唯一 campaign 门面；单 controller 可用 `campaign-run`，复制会话必须先由 `campaign-freeze` 等齐本次显式 active workload 的 immutable submission 并冻结唯一 plan、只读 capsule 与 `planDigest`，再由每个 `campaign-lane-run` 独占一路 claim，最后由 `campaign-finalize` 只聚合实际 active workload 的 create-once receipt。collision、branch/commit/source/catalog mismatch、重复 claim、主工作树漂移或超时均 fail closed。
- submission-only attempt 只能在无 plan/report/runtime/execution 证据时由 `reconcile-submissions` 收口。
- 已冻结 campaign 若全部 active claim 在 author/review/publish 前 terminal failed，只有在对应 active execution root 已经受 GC protection 合法清理且 source identity 确实漂移后，才允许 `reconcile-failed-campaign` 写 create-once supersession。
- claim 后若已产生 execution 证据，不得清理或改写该证据。
- 每个 terminal active execution 必须分别写入当前源码可复核的 create-once supersession receipt，再由 campaign reconciliation 精确绑定这些 receipt、原 plan/report/runtime/claim/submission 与已变化的 source identity。
- 下一序列逐 lane 声明 `retryOf` 并精确引用 reconciliation receipt。任一进程仍存活、lease 未释放、execution receipt 缺失或字节漂移均 fail closed。
- independent review 已完成 Provider journal、却因 controller 中断只留下 schema-valid pending response 时，不得把 pending 改写或冒充旧 `reviewer_result`。只有 sole pending response 与 sole 未绑定的 finished Grok reviewer work unit 可由独立 create-once interruption reconciliation receipt 精确绑定 campaign/capsule/execution/journal/response 全部摘要；新 `retryOf` 必须同时消费该 receipt 与其余对象已绑定的 final reviewer result，只纳入 failed refs，并把 typed issues 注入对应实体的新对象重写。前驱 qualified 对象不得进入 retry scope。
- controller 为本次 active workload 建立同一 content-addressed、只读 source/executor capsule，并为每条 active lane 分配独立 execution root、queue namespace 与 staging prefix；active workload 独立调度，review 可串行或重叠执行，每条 lane 按自身 review 结果独立进入 publish，不得因任一 lane 失败而整批 abort，也不得为每条 lane 复制完整 Git object store。共享 canonical publish 继续由对象事务锁保持单写者，最终 Manifest/release 必须精确验证全部被选对象及引用闭包。
- semantic author/reviewer 只消费 create-once 本地 journal 与只读 source capsule。Provider/model、凭据、runtime、网络与真实 startup 是启动该 semantic task 的 preflight；soak、workspace smoke、effective concurrency 与 resource samples 只诊断实际容量，不得改变 task dispatch、对象准入或 promotion。review 通过后才生成 immutable pool-delivery intent，ReliableTask 与 generation/fence/worker binary 仅负责 intent 的幂等交付。transport 不可用时对象保持 `deliveryPending`，不得撤销 review、重复调用 semantic Provider 或阻塞其它 lane。
- 每个实际启动的 semantic task 必须逐项写入 create-once typed 终态结果；排队、尚未启动、capacity sample 或 workspace sample 均不得合并成 task 成功或失败，也不得替代实际 task 结果。
- lane 终态独立记录为 `published`（`qualified >= quota`）、`partial`（`0 < qualified < quota` 且已合格对象已发布）或 `blocked`（`qualified == 0` 或 review/publish 失败）；campaign 终态为聚合视图：`succeeded`（全部 active workload 均达标）、`succeeded_partial`（至少一路发布了合格对象）、`blocked`（无任何可发布合格对象）。
- `quota` 是里程碑累计目标，不是发布许可条件；`partial` lane 必须发布全部已合格对象，并将 shortfall 写入 typed evidence，不得因未达 quota 丢弃合格对象。
- image/video 请求的 `quota` 是内容对象下限，`count`、`targetNames` 与 `coverageTargets` 只是唯一实体候选/覆盖范围，三者不得比较或互相改写。每个已接受外部媒体资产必须从 immutable manifest/receipt exact pair 冻结独立 `workUnit`（至少绑定 receipt、asset、content digest 与唯一 canonical coverage target）。同一实体的多个资产分别生成多个 brief/content object。无法唯一映射实体的单资产形成 typed exclusion，其他 workUnit 继续；`0 < qualified < quota` 为 partial，只有零合格对象才 blocked。
- 若存在 discard，每个 discard 必须具备非空 `objectRef` 与 typed `issues`，且 `selected == qualified + discarded`；不得要求真实批次必须存在 discard 才准出。
- article/image/video 的 canonical Post manifest 必须显式声明 `contentIdentity=work`；schema、promotion 与 importer 任一层发现缺失或非 `work` 均阻断该对象，禁止由消费者默认补值。
- 新增 canonical Post 必须显式携带稳定 `contentId`、递增 `version`、`sourceType=data`、`variantPurpose`、`admission.processResult/qualityResult/usageScope` 与 `status`。只有 `completed + passed + active` 可被 ReleaseManifest 选择。
- 统一池 reader 只接受显式 create-once pool record。缺 admission、稳定 `contentId/contentVersion`、完整 `sourceAttribution` 或 source identity 的历史对象按对象排除，不得在读取时从 review、路径或当前 source identity 推导。可修复对象只能由 governed repair 基于 canonical bytes 与 fresh source evidence 追加新的 `recordSequence`，保持原 `contentVersion`。旧 record 与旧 task receipt 均不改写、不复用。
- 环境定向 Manifest 从同一 pool 生成固定载体/作者轮转顺序并按 Alpha 2,100、Beta 10k、Gamma 100k 截取稳定 Post 前缀，Homepage 不计 Post cap；环境无关 M100/M1000 Research Manifest 精确冻结 cohort 并可由四环境消费。相同 `contentId` 在同一 manifest 只出现一个版本，有供给且容量允许时 article/image/video 必须同时出现。
- campaign report 必须保留 named main branch、status、phase、run generation/fencing、heartbeat、review/publish return code、source capsule/execution-root ref、qualified/finalized count 与 cleanup 终态；报告是运行回执，不得成为新的内容或 release 真相源。
- 复制会话的 carrier claim 必须绑定 campaign/run generation/fencing、carrier、execution、只读 source capsule 与独立 execution root；同一 carrier 同一 generation 只能存在一个有效 claim，过期或跨 generation owner 不得 finalize。
- carrier finalize 必须绑定对应 claim、对象级 review/rights/provenance 证据与 publish receipt，并满足 `finalized == qualified >= 1`；同 digest 重放幂等，token、generation、source 或对象闭包漂移 fail closed。未达 quota、存在 shortfall 或存在带 typed issues 的 discard 均不阻止其余全部合格对象 finalize。
- 每个生成批次只按对象记录过程完成、质量和授权范围；合格对象立即追加到统一池，批次未达 quota、存在 shortfall 或其他对象失败均不阻断已合格对象。M100/M1000/M10000 只按累计唯一对象数量判断是否达标，均为数量下限而不是停止生产或准入的上限。
- M1000 sourcing 以请求冻结的完整行政区域 frontier 为产品范围：穷举所选区域全部市、区、县与可识别 POI，合格对象即使显著超过 1000 也全部准入。不得设置单一区县、单一实体类型、Provider 或 creator 数量/比例上限。
- M10000 将同一 frontier 先推广到全国，再扩海外，国内外只共享一套 canonical geo/entity/source contract。

### REQ-002 生命周期与统一素材 admission

- acquisition、semantic、review、canonical pool 与全局运行配置均不声明或推断 lifecycle/class。每次 immutable release build 必须显式选择 `research|commercial`，并在 create-once release header/attestation/activation 中冻结同值 `releaseClass/productLifecycleState`；环境名、临时环境变量或 fixture 不得推断该状态。
- 每个实体头像/主页媒体、文章图、图片作品与视频资产都必须记录 `acquisitionStatus`、`rightsStatus=verified|unverified|restricted|unknown`、`authorizationRequired`、`distributionDecision=research_allowed|commercial_allowed|blocked` 以及 `sourceUrl/platform/creator/capturedAt/contentSha256/license/termsUrl/authorizationProof/rightsIssues`。
- `research` 允许已取得且权利状态为 verified/unverified/unknown 的资产，restricted、未取得、生成素材或缺来源/权利缺口字段仍阻断；`commercial` 只允许 verified 且具有商业授权证据的 `commercial_allowed`。
- research immutable release 必须冻结权利状态计数、精确 authorization-required asset IDs、四载体 `researchAcceptedCount`、逐来源 assets funnel 和 `containsUnverifiedAssets`；未授权资产不得计入 `commercialAcceptedCount` 或生成 commercial readiness。

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

### REQ-004 四环境 research 隔离、商用切换与规模门

- research activation 前，四环境分别证明身份白名单、匿名内容和媒体关闭、无公开 CDN/匿名 URL、分享/导出/索引关闭、内部 App 签名与研究态标识、媒体短期签名 URL 和访问审计；任一缺失立即 `GATE_BLOCK`。
- `appUatEnvelope` 从本 release 对象闭包投影并显式带 `releaseClass=research/productLifecycleState=research`，不可被 commercial package/activation/UAT 复用。
- Alpha/Beta/Gamma/Prod 必须分别生成 create-once `activationEnvelope`，精确绑定同一 `releaseId + manifestDigest + sourceIdentitySetDigest + releaseClass + productLifecycleState + appUatEnvelopeDigest`。每个 cohort 对象在 manifest 中保留自身 execution/source identity。环境按 Alpha→Beta→Gamma→Prod 依次激活，后续环境冻结前一环境同 release 的 passed activation/readback/App UAT receipt 字节摘要，同时仍生成本环境独立 import/readback 与 research isolation policy/proof。任一环境 receipt 不得替代另一环境，也不得把 Prod research activation提升为 commercial。
- 商用切换从同一 frozen canonical pool snapshot 构建新的 immutable Commercial release；Research 可选择 `research|commercial` 对象，Commercial 只选择逐对象 `usageScope=commercial` 且 entity/post 全部资产 `commercial_allowed` 的授权子集。两者绑定相同 `poolDigest`，source identity 使用各自被选对象的 scalar 或 set 闭包，不要求伪造新的 scalar source digest。未选坏对象形成 typed excluded，不拖垮其余合格对象。
- `qwq-data release commercial-transition` 只从同一 `poolDigest` 的 research/commercial 两个不同 immutable release、授权对象子集与四环境 cache/media/signed-URL 清理及未授权 readback=0 证据生成逐资产 create-once migration receipt；两 release 的 `releaseId` 与 payload 必须不同，不得修改旧 research release 或用手工布尔值替代环境证据。
- 日常 research release 不以规模数量作为发布许可。
- Content candidate 必须按 `prepared -> imported -> projected -> verified -> active` 单轨推进；逐阶段持久化脱敏 receipt，记录 duration、attempted/success count、checkpoint 与首个 typed blocker。只有 `verified` 可切换 active pointer，任一阶段失败保留 previous active 与已成功阶段事实。
- 三个累计规模 milestone 固定为 homepage/article/image/video：M100=`100/100/100/10`、M1000=`1000/1000/1000/100`、M10000=`10000/10000/10000/1000`。这些数字均为 promotion 下限；日常 publish 允许 partial，已合格对象超过下限时继续准入，不为凑整数截断 frontier。milestone promotion 必须逐路满足 `totalUniqueFinalizedCount >= targetCount` 且 `shortfallCount=0`。
- source-pool、oversampling、Provider、实际重叠时长、workspace/soak/resource samples 和恢复事实用于计划容量与定位瓶颈；缺失、未运行或失败的诊断样本不得改变一个已完成、质量合格且在授权范围内对象的池准入、dispatch 或 milestone 结果。
- 规模 promotion 只验证累计唯一对象数量、对象准入结果和所构建 ReleaseManifest 的引用闭包；精确重复不计数，缺引用对象留在池中等待修复，不阻断其他合格对象发布。
- 后继 milestone 只生成累计目标差额。前驱 promotion receipt 只记录 lineage，不作为新合格对象入池或当前 milestone 计数的前置门。M1000 的 source discovery/acquisition、semantic 与 review 可以在 M100 环境验收期间并行；M1000 promotion 前必须补足同一 M100 Research release 的 Alpha activation/readback 与 100 例 App UAT。该产品阶段门不撤销池中任何 M100 对象，也不冻结后继来源队列。
- promotion receipt 必须记录各 carrier 的 target、admitted、publishable、deliveryPending、selected、excluded 和 gap；illustrated、video popularity、automatic recovery、source mix、实际调度重叠、workspace/soak 与资源使用只作为诊断统计。
- M1000 与 M10000 的时间、Provider 容量和故障恢复样本用于计划和 SRE 评估；目标未按期完成时报告实际 gap，不撤销已经完成的池追加或已验证 Release。
- semantic author/reviewer 通过受治理 `cursor_sdk|codex_sdk` adapter 执行，Provider、model、model parameters、role、SDK/runtime digest 与 run/result digest 在 execution 冻结。受治理生产主选为 `cursor_grok`，exact model 与 parameters 由当前 runtime profile 声明并经 fresh preflight 实测准入，不在规格中另建版本常量。
- `cursor_auto` 只能在父 execution 已以允许的 typed provider/model failure 终止后，以新的 `retryOf` 显式选择。禁止 execution 中静默 fallback 或由 SDK Auto 首次路由替代 Grok 证据。capacity soak 未运行或未通过时，不得用下载数或框架测试冒充已测得的稳态容量，但该诊断结论不得阻断 task dispatch、合格对象发布或规模 promotion。
- 10 万级不是单一 promotion 事务：使用同一分片键持续生产，并以 1K/5K/10K immutable release waves 累计到不少于 100000 个合格对象；单 wave 或 named scale 仍是下限，不是总量上限。跨分片全局去重、checkpoint 恢复、dead-letter 隔离与连续 7 天无全局冻结的 soak 用于独立的 100K 稳态运行/SRE 结论，不是累计对象达到 M10000 或 100K 数量下限的 promotion 前置。

### REQ-005 已审核闭包采纳与 release identity incident

- `adopt-reviewed-closure` 是现有四 lane campaign/release 单轨上的一种身份收口方式，不是第二个 aggregator、第二套 publish 目录或手工 manifest 入口。它只能采纳一个已存在且不可变的 reviewed release 对象闭包，不重新生成、不改写正文/媒体/审核/权利事实，不修改上游 release。
- 采纳引用必须绑定精确 source release tuple `releaseId + payloadSha256 + canonicalMerkle + attestationFileSha256`，并对 release header、desired state、object index、media manifest、每个 review/rights evidence 和媒体公共切片逐文件复核摘要；任一字节、对象引用或媒体所有权漂移即 fail closed。
- 新的四个 adoption execution 必须共享唯一当前 `sourceDigest + entityCatalogDigest -> sourceRevision`，且 release 激活身份仍只允许一个 `sourceDigest`。上游历史 `sourceDigests/executionIds` 只能以冻结 provenance 留在 adoption receipt，不得被提升为新 release 的多 source active identity。
- 同一 `releaseId` 曾对应多个 payload/canonical identity 时，必须先生成 append-only、create-once identity incident；incident 按上述精确 tuple 保留每次观测的 attestation 与 execution closure，且所有受影响 execution 在 incident 未关闭前不得 discard 或 GC。仅 releaseId 相等、仅文件名相等或仅有历史口头记录都不构成可采纳证据。
- provenance 合同引入前已 create-once 的 incident 已全部完成一次性 CLI migration（迁移源 namespace 已清空，migration 器与其 schema 已退役）：迁移当时验证了原 incident 精确文件摘要、receipt digest、合同引入 commit/时间边界、旧 schema 闭集、同目录 snapshot 路径/文件摘要/attestation identity 与 execution closure，并把每个 snapshot 分类为 `original_file`，在独立 create-once namespace 留下 source-bound receipt 与当前 schema projection，原 incident/evidence 未被修改。GC/discard 仅在原文件仍逐字节匹配 migration receipt、projection 的观测 identity 与 execution closure 与原 incident 完全一致且 projection 通过当前 schema 全量校验时消费该 projection，否则继续 fail closed。

### REQ-006 有界并发、绝对批次截止与可复核运行终态

- 并发上限只约束任一时刻可同时运行的 worker 进程数，不构成 submission、dispatch、对象准入或 promotion 的前置条件。达不到上限、只跑一路或全部串行完成都不改变任何对象的准入与发布结果。
- 来源发现阶段的 `autoResearchMaxConcurrentWorkers` 与 ReliableTask 交付阶段的 `fleetMaxConcurrentWorkers` 只能由 immutable execution policy 冻结。runtime profile、环境变量、命令行默认值与任何探针观测都不是合法来源。
- preflight capacity soak 与 workspace smoke 的 `effectiveConcurrency` 只描述探针当时的实际并行度，是诊断观测而不是生产上限；把它投影成上限即为非法来源，必须 fail closed。
- `local-apple-silicon + cursor_grok` 的容量来源是 create-once receipt `quwoquan_data/control_plane/_shared/capacity_calibration/m100-wave-soak-20260818-v4/receipt.json`（摘要 `sha256:653180ed007d37bd01644f5d19e27b406532cf026a701086a0e06b2beda744f0`）：`autoResearchMaxConcurrentWorkers=8`、`fleetMaxConcurrentWorkers=3`、`objectWallClockSeconds=660`、`completionGraceSeconds=60`。该自包含闭包绑定 100/100 零 429/auth/5xx/timeout/bridge-disconnect 的 `cursor_grok` probe、1.57GB RSS / 1118.5% CPU / 8 bridge 峰值、真实 fleet peak=3 与 20 个逐对象 timing；超出适用范围或任一 evidence ref/digest 漂移即 execution 冻结失败。
- `execution_state` 中 `managedAgentScheduler` 的 `promptCount` 是单个 managed checkpoint 内语义 Agent prompt 级调度的运行观测。它既不是资源上限，也不是 ReliableTask 的 worker 进程并行度，两个维度不得互相读取或互相推导，该对象也不得以 worker 词元命名任何 prompt 级观测。
- `approvedQuota`（对象下限）、`targetObjectCount`（本次冻结的工作单元数，也是派生 job 数）与并行上限是三个互不相同的语义，必须在执行策略中各自显式冻结。任一字段不得同时承载其中两个语义，`requiredWorkers` 不得继续由工作单元数或 quota 派生。
- 规模只改变 wave 数：job 数增长只增加 wave 数，不增加任一时刻同时运行的 worker 进程数。wave 数只由 job 数与冻结的并行上限决定，与 quota 无关。
- 并发上限不得导致任何已冻结工作单元被丢弃、跳过或与其他单元合并。每个工作单元必须获得独立 typed 终态，单个单元失败或超时只终结该单元，释放的额度立即由下一个待处理单元占用。
- 批次时间预算必须以绝对纪元时间 `fleetBatchDeadlineEpochSeconds` 冻结并持久化。进程重启、lease 续租与子进程重建只能注入 `max(0, fleetBatchDeadlineEpochSeconds - 当前时间)` 的剩余时间，不得重新注入完整批次预算或完整单对象超时窗口。
- 剩余时间为 0 时不得启动任何新 job，已在运行的 job 按单对象 wall-clock 上限收敛并写入 typed deadline 终态。单对象上限与批次剩余时间取更小者，需要更多时间只能由新的 `retryOf` 冻结新的绝对截止。
- ReliableTask fleet 运行回执必须同时携带 `fleetPeakConcurrentWorkers`、`fleetWaveCount` 与 `fleetBatchDeadlineEpochSeconds`，缺任一项即校验失败。实测峰值不得超过冻结上限，且只作观测，不得被回写成新的上限。
- `qualified == 0` 不再是单一 `blocked` 汇总值，必须携带唯一 typed 原因。原因闭集为七种：来源为空、来源访问被拒或网络不可达、批次截止耗尽、全部对象质量被拒、可续跑中断、全部对象因闭包超出单对象存储预算而在 publish 准入被拦下，以及 `在场可用` 集合非空但全部候选实体在 target set 冻结前的选择器准入被排除。七者互不合并，也不得退化为一个不带原因的汇总值。
- 原因值、观测阶段与运营动作是三个互相约束的闭集，任一原因进入时三者同批扩容，新原因不得借用语义不符的既有阶段或既有动作。观测阶段闭集为五种：来源发现、review、交付、publish 准入与 target set 冻结前的选择器准入。每个原因值只属于其中一个阶段，不得靠放宽某个原因的阶段取值范围让同一个原因同时归属两个阶段。「全部对象质量被拒」只由 review 观测，「全部对象超出单对象存储预算」只由 publish 准入观测，publish 准入的结论取不到前者。
- 「全部候选实体被选择器准入排除」只由 target set 冻结前的选择器准入观测。该阶段严格后置于实体级来源判定，只作用于已判为 `在场可用` 的实体，因此它取不到来源发现阶段的任何原因值，来源发现阶段也取不到它。
- 运营动作闭集为五种：续跑、修来源、重新冻结时间预算、缩减对象体量与扩大候选范围。缩减对象体量是超预算原因的唯一动作，指向按批次携带的对象级排除条目逐对象减少其引用的资产数、换掉单张超出预算的素材或把该对象拆成多个对象。它不是修来源——改来源闭集解决不了体量超标；它也不得被表述为调整预算数值，预算数值由既有门禁单点拥有，不由本终态改写。
- 扩大候选范围是准入零通过原因的唯一动作，指向扩大候选区域范围以取得尚未触及累计上限的实体，或按治理流程调整多样性策略。它不是修来源——被排除实体的来源全部可用，按修来源提示去改来源闭集解决不了准入零通过；它也不得被表述为调整多样性阈值数值，阈值数值由多样性策略的既有 owner 单点拥有，不由本终态改写。
- 可续跑中断必须给出精确可续跑 refs，其余六种原因必须给出不可续跑的判定依据。「全部候选实体被选择器准入排除」在该依据之外还必须给出逐实体的准入排除 refs，指向选择器在冻结选择证据上已声明的排除条目，缺该 refs 时该原因不成立。运营者只读运行回执即可决定续跑、修来源、重新冻结时间预算、缩减对象体量还是扩大候选范围，不需要读取运行日志。
- 批次级零合格原因的唯一写者是本 Story 的 lane 回执。媒体侧只产出对象级排除码，两层以引用衔接而不复制，媒体侧不得自建批次级原因值。批次级原因只在一个批次的全部对象都被拦下时成立，存在任一合格对象时该 lane 仍按合格对象数进入 `partial`。

### REQ-007 article 来源预筛准入与实体级首要失败原因

- 内容运营者在 article lane 冻结 target set 之前就能知道哪些实体存在可锚定的长文来源，因此工作单元不再被无来源实体占用；同一 quota 下 article 的累计下限达成得更快，而不是把 target set 砍小后更早收敛为 `partial`。
- article lane 必须在冻结 target set 之前完成实体级来源判定，不得只按主清单静态优先级排序、把来源可得性推迟到 auto_research 或 content_plan 才发现。homepage 与 video 的既有判定时点由各自路径拥有，本 REQ 不重复约束，也不要求 article 照搬 homepage 把整批拦下的处置。
- 每个候选实体的预筛结论必须是且只能是以下四态之一。四态互不塌陷，也不得塌陷为空值、空集合或零计数：
  - `在场可用`：允许来源闭集内至少有一个可合法取得、可读，且经实体锚定判定确属该实体的长文候选。
  - `在场不足`：判定已完成，候选可合法取得且可读，但未达门槛。必须再带唯一子原因区分「已锚定到本实体但正文篇幅不足」与「可读但未锚定到本实体」；前者的运营动作是换实体或按 calibration 调整篇幅门槛，后者是扩来源闭集或换实体。同一实体同时命中两个子原因时取前者，因为它已证明本实体的来源确实存在。
  - `缺席`：判定已完成，允许来源闭集内不存在可合法取得且可读的候选。必须再带唯一子原因区分「闭集内存在候选但不可合法取得或不可读」（含被 robots/服务条款、登录或验证墙、允许路径之外排除者）与「闭集内不存在候选」；前者的运营动作是修来源闭集，后者是换实体。
  - `探测失败`：判定未完成，包括网络不可达、超时、解析中断与探测预算在得出结论之前耗尽。
- `缺席` 与 `探测失败` 的分界是「判定已完成且结论确定」与「判定未完成」，二者不得互相冒充：未完成的判定不得报告为确定缺席，确定缺席也不得表述为可续跑中断。`探测失败` 必须给出精确可续跑 refs，`在场不足` 与 `缺席` 必须给出不可续跑的判定依据。
- 同一实体的多个候选归并为实体终态时按 `在场可用` → `探测失败` → `在场不足` → `缺席` 取先者：只要存在一个合格候选即 `在场可用`；没有合格候选但仍有候选未得出结论时不得先行宣告 `在场不足` 或 `缺席`。
- 预筛的每个非成功终态必须以 typed 且运营者可直接读取的形式呈现，运营者只读该终态即可决定续跑、修来源闭集还是换实体；进程退出码、异常字符串与运行日志都不是合法呈现面。预筛在 execution spec 冻结之前终止时同样适用，lane 终态为 `published` 或 `partial` 时 `探测失败` 实体的可续跑 refs 也必须留在同一呈现面，不因该 lane 已发布而丢弃。
- 预筛是准入过滤，不是产量保证。`在场可用` 数少于 quota 时必须触发既有补采轮次补充候选并重新预筛，不得静默下调 quota，也不得用未通过预筛的实体 padding 工作单元。补采预算耗尽后仍不足时，lane 以 `在场可用` 经冻结期准入后的实际集合继续执行并按 `REQ-001` 进入 `partial`；只有该集合为零才 `blocked`。
- 上一条的 `blocked` 有两种成因不同的零，必须分别携带对应证据，不得互相冒充。零 `在场可用` 的那种携带本 REQ 的实体级首要原因。`在场可用` 非空而经冻结期准入后为零的那种携带准入侧的逐实体排除证据，并按 `REQ-006` 取「全部候选实体被选择器准入排除」这一原因；此时实体级首要原因聚合全部为 `在场可用`，用它冒充会把运营者指向一个没有问题的来源。
- 冻结期准入是选择器在冻结工作单元时的决定，只作用于已判为 `在场可用` 的实体，其出局不改变该实体的四态取值，也不计入本 REQ 的候选级或实体级拒绝计量。本 REQ 的四态保持四个值，不因此新增第五态，也不在四态旁挂表达是否被选中的状态位。
- 预筛与补采发生在 selection 阶段、早于 `REQ-006` 冻结 `targetObjectCount`。预筛只改变进入冻结的候选集合，不改变 `REQ-006` 的三值分离与并行上限语义。
- 实体级预筛终态是「该实体是否还能被重新探测」的唯一权威面，`REQ-006` 的 fleet 级零合格原因只归因「本批次是否还能续跑」。两者层级不同、不得互相推导或互相替代：fleet 级把来源访问被拒或网络不可达判为本批次不可续跑（需要新的 `retryOf`），并不表示实体级 `探测失败` 的实体不可再被探测；实体级的可续跑 refs 正是该 `retryOf` 的输入。
- 每个候选实体只有一个首要失败原因，实体不得同时挂多个并列首要原因，也不得只留下无法回到具体实体的计数。候选级与页面级的细粒度拒绝原因必须聚合到实体级，且聚合后能按下列四类分别量化：`缺席` 为「无可合法取得来源」，`在场不足` 的两个子原因分别为「抓到但正文篇幅不足」与「抓到但不是本实体」，`探测失败` 为「判定未完成」单独计量、不并入前三类。
- 候选级拒绝原因的闭集由其 owner 节点维护。owner 新增一类拒绝原因时必须同时归入本 REQ 的四态之一及其子原因；尚未归类的原因必须使该候选所属实体以 `探测失败` fail closed 并点名该未归类原因，不得静默归入 `缺席` 或 `在场不足` 而污染已完成判定的三类计量，也不得被丢弃。
- 同一实体在来源预筛、auto_research 与 content_plan 三个阶段的 ready 判定必须可按实体逐一对齐。任一阶段 ready 数下降时，必须能精确列出在该阶段出局的是哪些实体及其首要原因，不得只保留两个互不可对账的阶段计数。
- 站点与 provider 级抓取准入、候选级相关性判定的闭集及其不可变审计证据，以及 workload receipt 的 target/selected/qualified/finalized/discarded/shortfall 计数口径，由 `specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md` 的 `REQ-003` 与 `REQ-004` 拥有。本 REQ 只消费其逐候选判定结果做实体级聚合与准入，不复制该闭集，也不建立第二套来源台账。

### REQ-008 来源发现阶段运行中的存活与进度可判定

- 来源发现阶段在尚未终止时必须可判定存活与进度：阶段进程必须按执行策略冻结的心跳间隔持续写入运行中进度面，写入时机独立于任何单个实体是否得出终态。只在实体终态时写一次不满足本要求——单个实体的来源发现耗时可以远大于任何可接受的存活判定间隔，此时运营者读到的是一段与「进程已死」无法区分的静默。
- 该判定不得依赖进程外旁证。连接数、CPU 占用、进程是否仍在进程表内、进度文件 mtime 猜测与日志尾部都不是合法判定面；运营者只读该进度面即可区分「仍在推进」「已停止推进」「已终止」，不需要另行取证。
- 进度面必须携带足以定位当前工作的阶段身份与进度事实：本次冻结的候选实体总数、已得出终态的实体数、仍在运行的实体身份，以及最近一次心跳的时刻。「尚未有任何实体得出终态」是在场为空——总数已知、完成数为 0 且阶段状态为运行中；它不得与「阶段已死」或「进度面缺席」表述为同一种结果。
- 超出冻结阈值仍未推进必须是 typed 过期状态，并区分「阶段仍在运行但未按间隔心跳」与「阶段已终止且不会再心跳」两个结论。进度面缺席、不可读或缺必需字段同样是 typed 失败，不得塌陷为进度为零、不得默认判为存活，也不得静默沿用上一份快照冒充当前事实；阶段终止时最后一次心跳的事实必须保留，不得被清零或覆盖为空。
- 心跳只表达存活与进度，不表达吞吐承诺。心跳中的 elapsed、已完成实体数与每分钟实体数与 `GWT-008` 的阶段报告同源，只是当次运行事实，不得被表述为已测得的稳态吞吐或容量结论，也不得改变 dispatch、对象准入、publish、finalize 与 milestone 结果。
- 本 REQ 与 `REQ-006` 的分工：`REQ-006` 约束任一时刻可同时运行的 worker 上限、批次绝对截止，以及阶段终止之后运行回执的可复核性与零合格 typed 原因；本 REQ 只约束阶段仍在运行期间的存活与进度可判定性。两者不得互相推导——心跳仍在推进不表示批次剩余时间未耗尽，剩余时间未耗尽也不表示阶段仍存活。心跳也不得被写回运行回执充当第二套容量或截止结论。
- ReliableTask 交付阶段不在本 REQ 范围内：它的静默窗口已由 `REQ-006` 的单对象 wall-clock 上限与逐工作单元 typed 终态限定，不重复约束。
- 心跳间隔与判定过期的阈值不在本层冻结，见 `OPEN-005`；在其冻结之前，以「文件最近被写过」推断存活不成立。

## 4. 契约引用

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

<a id="gwt-006"></a>
### GWT-006 media quota 按内容对象执行并隔离逐资产失败

- GIVEN 一个 image/video workload 的 `quota` 大于唯一实体数，且 immutable acquisition receipts 接受了同一实体下的多个不同资产。
- WHEN materialization 从 capsule 已验证的 manifest/receipt exact pair 投影 source selection 与 content plan。
- THEN `targetObjectCount` 等于可映射 accepted assets 数，`targetEntityCount` 等于唯一 canonical coverage target 数；`approvedQuota` 保留请求对象下限，不得按实体数静默降低。
- THEN 每个 workUnit 精确绑定一个 receipt/asset/content digest 与一个 canonical coverage target，并只生成一个具有相同 `workUnitId` 的 brief/content object；同一实体允许多个 workUnit。
- THEN 无关实体不得 padding；无法映射或歧义的单资产写 typed exclusion，局部 source/safety 失败只形成该 workUnit shortfall。仍有至少一个真实对象时继续 partial，零对象才 blocked。

<a id="gwt-007"></a>
### GWT-007 回收窗口让 output 稳态占用收敛

- GIVEN output 内同时存在被环境引用的 immutable release、带 `publish_ref` 的 task 证据、可重建缓存，以及历史 release 对已被回收 task 的引用。
- WHEN 执行 `release gc plan`。
- THEN 返回可执行回收计划：可重建派生物与超出保留窗口的过程产物列为可回收，发布证据与被环境引用的 release 列为受保护。
- THEN 历史 release 对已回收 task 的引用不使计划失败，而是以显式终态记录并保守保护其可达对象。
- THEN 连续多轮 campaign 后 output 稳态占用不随累计执行次数单调增长。

<a id="gwt-008"></a>
### GWT-008 来源发现并发有上限且不丢实体

- GIVEN 一个已冻结 execution 的执行策略把 `autoResearchMaxConcurrentWorkers` 冻结为 8，其 frozen target set 含 180 个实体，且单个实体的来源发现可被外部信号挂起与放行。
- WHEN 该 execution 进入来源发现阶段，一次性对全部 180 个实体排程。
- THEN 任一时刻处于运行中的来源发现 worker 数不超过 8，该峰值不随实体数增长。
- THEN 180 个实体全部得到逐实体终态，没有实体因为并发上限被丢弃、跳过或与其他实体合并。
- THEN 单个实体超时或失败只终结该实体，释放的额度立即被下一个待处理实体占用，其余实体继续跑到各自终态。
- THEN 阶段报告如实记录实测峰值并行数与冻结上限；elapsed 与每分钟实体数只是本次运行事实，不得被表述为已测得的稳态吞吐或容量结论。

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

<a id="gwt-012"></a>
### GWT-012 article 在冻结 target set 前完成来源预筛且四态不塌陷

- GIVEN 一个 article execution 的候选实体中分别存在六类实体：允许闭集内有可锚定长文来源、已锚定到本实体但正文篇幅不足、可读但未锚定到本实体、允许闭集内存在候选但不可合法取得或不可读（被 robots/服务条款、登录或验证墙、允许路径之外排除）、允许闭集内不存在候选、以及探测在得出结论之前被中断；另有一个实体同时含未达门槛候选与判定未完成候选，还有一个实体的候选携带闭集之外的未归类拒绝原因。
- WHEN 该 execution 进入 target set 冻结之前的来源预筛。
- THEN 前六类实体分别得到 `在场可用`、带「篇幅不足」子原因的 `在场不足`、带「不是本实体」子原因的 `在场不足`、带「不可取得」子原因的 `缺席`、带「无候选」子原因的 `缺席`、以及 `探测失败`；任一态都不表述为空值、空集合或零计数，未完成的判定也不被报告为确定缺席。
- THEN 混合候选的那个实体按归并优先级得到 `探测失败` 而不是 `在场不足`。
- THEN 携带未归类拒绝原因的那个实体以 `探测失败` fail closed 并点名该未归类原因，不被归入 `缺席` 或 `在场不足`。
- THEN 只有 `在场可用` 的实体进入冻结的工作单元，其余三态的实体不进入 auto_research、download 与 content_plan。
- THEN `探测失败` 携带精确可续跑 refs，`在场不足` 与 `缺席` 携带不可续跑的判定依据；`缺席` 的两个子原因分别指向修来源闭集与换实体，`在场不足` 的两个子原因分别指向调整篇幅门槛或换实体与扩来源闭集。
- THEN 每个非成功终态都能被运营者直接读取并据此决定续跑、修来源闭集或换实体；预筛在 execution spec 冻结之前终止时同样留下该终态，而不是只留下进程退出码或异常字符串。

<a id="gwt-013"></a>
### GWT-013 预筛不承诺规模且实体级首要原因可跨阶段对账

- GIVEN 一个 quota 为 N 的 article lane，其首轮候选经预筛后 `在场可用` 数小于 N，且补采轮次预算尚未耗尽。
- WHEN 该 lane 执行预筛与补采直到补采预算耗尽，并继续走到 auto_research 与 content_plan。
- THEN 补采按既有轮次机制补充候选并重新预筛；quota 不被静默下调，未通过预筛的实体不被 padding 进工作单元。
- THEN 补采耗尽后仍不足时，lane 以 `在场可用` 经冻结期准入后的实际集合继续执行并进入 `partial`；只有该集合为零才 `blocked`，且该 `blocked` 按两种零分别携带证据。
  零 `在场可用` 的那种携带实体级首要原因。`在场可用` 非空而经冻结期准入后为零的那种携带准入侧的逐实体排除证据与「全部候选实体被选择器准入排除」这一批次级原因，不以实体级首要原因冒充。
- THEN 每个出局实体只有一个首要失败原因，「无可合法取得来源」「抓到但正文篇幅不足」「抓到但不是本实体」「判定未完成」四类的分子、分母与占比可直接由实体级聚合算出，第四类单独计量而不并入前三类。
- THEN lane 终态为 `published` 或 `partial` 时，`探测失败` 实体的可续跑 refs 仍留在同一呈现面；实体级可续跑判定不被 fleet 级「本批次不可续跑」的归因覆盖。
- THEN 来源预筛、auto_research 与 content_plan 三个阶段的 ready 判定可按实体逐一对齐；任一阶段 ready 数下降时可精确列出出局实体及其首要原因，而不是只留下两个互不可对账的阶段计数。

<a id="gwt-014"></a>
### GWT-014 来源发现阶段运行中可判定存活且心跳不塌陷

- GIVEN 一个已冻结 execution 进入来源发现阶段，其冻结的候选实体中至少有一个实体的来源发现耗时远大于冻结的心跳间隔，且该实体何时得出终态可由外部信号控制。
- WHEN 该阶段启动后运行到首个实体终态之前，运营者读取运行中进度面。
- THEN 首个心跳之后、首个实体终态之前，进度面仍按冻结间隔持续推进且最近心跳时刻随之前移；该判定不读取连接数、CPU 占用、进程表或文件 mtime 猜测。
- THEN 该时刻的进度面表述为「候选实体总数已知、已得出终态的实体数为 0、阶段状态为运行中」，并可读出仍在运行的实体身份；它不表述为进度缺席、阶段已终止或零计数失败。
- THEN 承载该阶段的进程被强制杀死后，进度面停止推进，超出冻结阈值时得到 typed 过期状态，且该状态区分「运行中未按间隔心跳」与「已终止不会再心跳」；最后一次心跳的事实仍可读，不被清零或覆盖为空。
- THEN 进度面缺席、不可读或缺必需字段时得到 typed 失败结果，不被读成进度为零，不被默认判为存活，也不被上一份快照冒充为当前事实。
- THEN 心跳中的 elapsed、已完成实体数与每分钟实体数只作为当次运行事实呈现，不表述为稳态吞吐或容量结论，也不改变 dispatch、对象准入、publish、finalize 与 milestone 结果。

## 6. 依赖

- 前置要求：父能力的 execution、review 与 release 契约。
- 上游事实：来源、目标集和审核结果。
- 下游结果：immutable release 或结构化阻断报告。
- 父级设计：`DEC-001`

## 7. 开放事项

### OPEN-001 多载体 research 环境消费与规模证据

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前仍缺足量专业来源池、实际 task 的逐项终态与池交付证据、真实四路累计数量，以及 canonical pool → immutable release → environment consumer 的精确引用闭包，所以最终规模闭环保持 `GATE_BLOCK`；fresh soak、四个同时 workspace、固定并发或 remote executor 主机数量不属于该阻断。
- 完成判定：`GWT-001/GWT-002/GWT-004` 有 local_contract 与真实 Content importer、Search、Recommendation、Homepage、Persona readback；依次达到 M100、M1000、M10000 的累计唯一数量并能从统一池构建和发布对应 immutable Research Release。
- 依赖：Data/Runtime/Service owner维护对象生成与池追加；Testing/Ops owner负责同一 Research Manifest 在 Alpha/Beta/Gamma/Prod 的独立 import/private-isolation/verify/activate/rollback/replay，Commercial 转换另立显式授权 release。Provider 与 remote executor 只影响生成吞吐和计划时间，不改变已合格对象准入。

### OPEN-002 回收器引用图完整性契约与 task 可回收规则互斥

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：`canonical_gc_reference_graph.schema.json` 以 `unresolvedReferenceCount: {"const": 0}` 与 `unresolvedReferences: {"const": []}` 要求引用图零未解析，而 immutable release 会引用 execution task，同一批 task 又被视为可回收过程产物。实测 254 个磁盘 task 下有 136 个被引用的 task 已永久不存在，破损引用源中 349 个文件位于 `data/releases/`：release immutable 不可修改、task 不可重建，因此 `release gc plan` 在存量 output 上永久 `GATE_BLOCK`，回收窗口机制形同虚设，稳态占用无法收敛。
- 完成判定：`GWT-007` 全部结果子句成立，由 local_contract 锁定「release → task 引用在 task 被回收后的合法终态」与相应保护语义。
- 依赖：Data owner 需在两条路线间裁决——让回收器报告未解析引用并保守保护被引用对象，或禁止回收任何被 release 引用的 task（后者使 task 树随发布数单调增长，与单对象存储预算冲突）。回收器侧已修复的可达性缺陷（可回收缓存引用、缺席证明字段与作用域、节点 kind 收敛、运行时冻结校验器职责归位、acquisition 命名空间）不在此阻断内。

### OPEN-004 article 来源预筛的判定阈值与探测预算 calibration

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：缺少 article target set 冻结前的来源预筛实现、四态契约与受治理阈值 receipt。现有 `confirmed|blocked` homepage 契约会把 `在场不足`、`缺席`、`探测失败` 塌陷成同一状态；现有 `matchConfidence`、成稿最小字数与首轮 `oversampleFactor` 也不是合法预筛阈值来源。
- 尚缺实现：实体锚定判定、最小正文门槛、单实体探测预算、补采重筛、四态聚合和三阶段逐实体对账尚未接入 article target selection。
- 尚缺验收证据：缺少受治理 provider-state 下拒绝、超时与探测预算耗尽的 api_integration，以及一次真实 execution 的 selection、auto_research、content_plan receipt 对账。
- 完成判定：`GWT-012` 与 `GWT-013` 的全部结果子句成立，且预筛阈值与探测预算来自 calibration receipt，而不是默认常量或从成稿质量门挪用的数值。
- 依赖：Data owner 先在可代表主清单冷门实体占比的样本上完成受治理预筛 calibration，再实现四态准入与补采。local_contract 覆盖四态、子原因、归并优先级、补采和两种零合格终态；api_integration 覆盖真实探测状态与三阶段对账；环境消费证据由 `OPEN-001` 承接。

### OPEN-005 来源发现阶段存活心跳的间隔与过期阈值 calibration

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：缺少独立于实体终态的来源发现心跳 writer、typed 存活读取面与受治理间隔/过期阈值。连接数、CPU、进程表、文件 mtime 与日志尾部均不能区分仍在推进、失去心跳和已经终止；容量 receipt 的并发与截止数值也不是合法存活阈值来源。
- 尚缺实现：运行中心跳、最近心跳保留、运行中未按间隔心跳、已终止不会再心跳、进度缺席/不可读/字段缺失的 typed 结果尚未进入统一进度面。
- 尚缺验收证据：缺少可控时钟 local_contract 和真实进程被强制杀死后的 api_integration，后者必须证明心跳停止、typed 过期与最后心跳事实保留。
- 完成判定：`GWT-014` 的全部结果子句成立，且心跳间隔与过期阈值来自 calibration receipt，而不是默认常量或从容量上限、单对象 wall-clock 挪用的数值。
- 依赖：Data owner 先在可代表主清单的样本上标定单实体耗时分布与心跳写入开销，再实现心跳读写面。local_contract 覆盖持续心跳、在场为空和 typed 失败；api_integration 覆盖真实进程终止后的过期判定；环境消费证据由 `OPEN-001` 承接。
