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
- 原因值、观测阶段与运营动作是三个互相约束的闭集，任一原因进入时三者同批扩容，新原因不得借用语义不符的既有阶段或既有动作。观测阶段闭集为五种：来源发现、review、交付、publish 准入与 target set 冻结前的选择器准入。每个原因值只属于其中一个阶段，不得靠放宽某个原因的阶段取值范围让同一个原因同时归属两个阶段。「全部对象质量被拒」只由 review 观测，「全部对象超出单对象存储预算」只由 publish 准入观测，publish 准入的结论取不到前者。
- 「全部候选实体被选择器准入排除」只由 target set 冻结前的选择器准入观测。该阶段严格后置于实体级来源判定，只作用于已判为 `在场可用` 的实体，因此它取不到来源发现阶段的任何原因值，来源发现阶段也取不到它。
- 运营动作闭集为五种：续跑、修来源、重新冻结时间预算、缩减对象体量与扩大候选范围。缩减对象体量是超预算原因的唯一动作，指向按批次携带的对象级排除条目逐对象减少其引用的资产数、换掉单张超出预算的素材或把该对象拆成多个对象。它不是修来源——改来源闭集解决不了体量超标；它也不得被表述为调整预算数值，预算数值由既有门禁单点拥有，不由本终态改写。
- 扩大候选范围是准入零通过原因的唯一动作，指向扩大候选区域范围以取得尚未触及累计上限的实体，或按治理流程调整多样性策略。它不是修来源——被排除实体的来源全部可用，按修来源提示去改来源闭集解决不了准入零通过；它也不得被表述为调整多样性阈值数值，阈值数值由多样性策略的既有 owner 单点拥有，不由本终态改写。
- 可续跑中断必须给出精确可续跑 refs，其余六种原因必须给出不可续跑的判定依据。「全部候选实体被选择器准入排除」在该依据之外还必须给出逐实体的准入排除 refs，指向选择器在冻结选择证据上已声明的排除条目，缺该 refs 时该原因不成立。运营者只读运行回执即可决定续跑、修来源、重新冻结时间预算、缩减对象体量还是扩大候选范围，不需要读取运行日志。
- 批次级零合格原因的唯一写者是本 Story 的 lane 回执。媒体侧只产出对象级排除码，两层以引用衔接而不复制，媒体侧不得自建批次级原因值。批次级原因只在一个批次的全部对象都被拦下时成立，存在任一合格对象时该 lane 仍按合格对象数进入 `partial`。

<a id="req-007"></a>
### REQ-007 确认后请求沿现有单轨推进到环境与 App 消费

- 确认后的完整用户路径固定为 `envelope -> task execute -> typed task terminal -> canonical pool/review/promotion -> immutable release -> Alpha import/activate -> API/media readback -> App CaseResult`。每一步只消费前一步的 immutable ref/digest，失败不得跳到后续步骤，也不得由旧 receipt 冒充本次完成。
- 意图 preview、confirmed handoff 与 envelope 编译由 [`work-request-compilation`](../work-request-compilation/spec.md) 拥有；canonical 池唯一写路径与结果五态由 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md) 拥有。本 REQ 只约束 canonical pool 之后的 release、环境与 App 消费闭环。

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

<a id="gwt-007"></a>
### GWT-007 回收窗口让 output 稳态占用收敛

- GIVEN output 内同时存在被环境引用的 immutable release、带 `publish_ref` 的 task 证据、可重建缓存，以及历史 release 对已被回收 task 的引用。
- WHEN 执行 `release gc plan`。
- THEN 返回可执行回收计划：可重建派生物与超出保留窗口的过程产物列为可回收，发布证据与被环境引用的 release 列为受保护。
- THEN 历史 release 对已回收 task 的引用不使计划失败，而是以显式终态记录并保守保护其可达对象。
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
- 影响或价值：当前仍缺足量专业来源池、实际 task 的逐项终态与池交付证据、真实四路累计数量，以及 canonical pool → immutable release → environment consumer 的精确引用闭包，所以最终规模闭环保持 `GATE_BLOCK`；fresh soak、四个同时 workspace、固定并发或 remote executor 主机数量不属于该阻断。
- 完成判定：`GWT-001/GWT-002/GWT-004/GWT-016` 有 local_contract 与真实 Content importer、Search、Recommendation、Homepage、Persona readback。entity homepage→对象主页、article→文章 surface、image→图片 surface、video→视频 surface 分别形成同 release digest 的 App CaseResult，且 micro 明确不属于 Data homepage。依次达到 M100、M1000、M10000 的累计唯一数量并能从统一池构建和发布对应 immutable Research Release。
- 依赖：Data/Runtime/Service owner维护对象生成与池追加；Testing/Ops owner负责同一 Research Manifest 在 Alpha/Beta/Gamma/Prod 的独立 import/private-isolation/verify/activate/rollback/replay，Commercial 转换另立显式授权 release。Provider 与 remote executor 只影响生成吞吐和计划时间，不改变已合格对象准入。

<a id="open-002"></a>
### OPEN-002 回收器引用图完整性契约与 task 可回收规则互斥

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：`canonical_gc_reference_graph.schema.json` 以 `unresolvedReferenceCount: {"const": 0}` 与 `unresolvedReferences: {"const": []}` 要求引用图零未解析，而 immutable release 会引用 execution task，同一批 task 又被视为可回收过程产物。实测 254 个磁盘 task 下有 136 个被引用的 task 已永久不存在，破损引用源中 349 个文件位于 `data/releases/`：release immutable 不可修改、task 不可重建，因此 `release gc plan` 在存量 output 上永久 `GATE_BLOCK`，回收窗口机制形同虚设，稳态占用无法收敛。
- 完成判定：`GWT-007` 全部结果子句成立，由 local_contract 锁定「release → task 引用在 task 被回收后的合法终态」与相应保护语义。
- 依赖：Data owner 需在两条路线间裁决——让回收器报告未解析引用并保守保护被引用对象，或禁止回收任何被 release 引用的 task（后者使 task 树随发布数单调增长，与单对象存储预算冲突）。回收器侧已修复的可达性缺陷（可回收缓存引用、缺席证明字段与作用域、节点 kind 收敛、运行时冻结校验器职责归位、acquisition 命名空间）不在此阻断内。

<a id="open-006"></a>
### OPEN-006 受治理容量 calibration 无可自举的 M100 receipt

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前用于授权本机 `cursor_grok` 容量值的 receipt 字节不在受版本控制真相源中，无法复核其逐对象 timing、Provider probe 与资源证据。`task calibrate-capacity` 已接入 canonical CLI，但 producer 必须先消费 fresh M100 fleet report 与逐对象 execution state，而当前 execution policy 又必须先加载该 receipt 才能启动，恢复后的空工作区因此形成启动环。规格复述的旧数值不能反向合成 receipt，也不能继续授权 execution policy。
- 尚缺实现：需要一个不授权日常生产、只以冻结安全并发执行真实 M100 measurement 的 calibration bootstrap path。它必须产出 producer 所需 fleet/object timing，再由 `capacity_calibration_cli` 完成 100 次 Provider probe 与 create-once receipt。receipt 必须落到被 Git 跟踪的 create-once 路径，任何干净检出都能读取并校验同一字节。bootstrap 不得回退到默认容量常量、fixture 或历史 runtime profile。
- 尚缺验收证据：`test_repository_capacity_calibration_receipt_is_self_contained` 在干净检出上必然 `GATE_BLOCK`（receipt is missing）。禁止以手写 receipt 或改小断言的方式转绿——伪造的 receipt 不可能命中已冻结摘要，改断言等于放弃摘要绑定。
- 完成判定：`GWT-019.t1..t4` 从无 capacity receipt、无 execution output 的干净工作区开始。local_contract 证明 authority、composition 与状态机边界。api_integration 以真实 bootstrap 进程和受控 Provider state 证明只运行 measurement 且 canonical/release/environment 成功事实增量均为 0。live reliability soak 才在 `local-apple-silicon + cursor_grok` 上完成真实 M100 measurement 与每个候选并发档 100 次 probe。随后由 `capacity_calibration_cli` 产出并提交新 receipt，repository gate 在干净检出校验其摘要与 applicability，删除动态 skip，同步更新 `REQ-006` 与设计中的 calibrationId/摘要，并重新直接覆盖 `GWT-009.t4`、`GWT-010.t4` 与 `GWT-011.t2`。在此之前该容量来源保持 `GATE_BLOCK`，不得由默认常量、runtime profile 或探针观测替代。
- 依赖：先在 `design` 冻结 bootstrap 与日常 execution policy 的单向边界；需要真实 `cursor_grok` provider 额度与本机 fleet 资源完成 100 对象 soak，缺失证据不可由事故记录、规格文字或静态输入合成。

<a id="open-008"></a>
### OPEN-008 零合格七原因与运营动作契约未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺零合格七原因及运营动作的 canonical 实现与验收证据。现有原因不足以表达 publish storage budget 与 selector admission 两类原因及其唯一阶段、缩减对象体量/扩大候选范围动作；仅补 spec_ref 会制造假绿。
- 尚缺实现：canonical schema 与生产消费者必须新增两类原因、唯一阶段与对应运营动作，并让未知值 fail closed。
- 尚缺验收证据：缺少七原因、阶段互斥、可续跑 refs 与六类不可续跑依据的直接 local_contract。
- 完成判定：canonical schema、生产消费者与 local_contract 直接覆盖 `GWT-011.t3`、`GWT-011.t4`，七个原因、唯一阶段、可续跑 refs 与六类不可续跑依据均单义且未知值 fail closed。
- 依赖：Data terminal-contract owner 先改唯一 schema，再更新消费者与测试；禁止双读旧值或默认映射为 generic blocked。

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

<a id="open-010"></a>
### OPEN-010 M100 语义波次与 semantic failover 的测试证据生态漂移

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：media source admission 硬门、`source_unit_meta` oneOf 收紧与 cursor_auto retry-only 语义收紧后，测试证据生态未同步重建，持续红的用例为：`test_semantic_wave_dispatch__carrier_selective__*` 9 例、`test_execution_manifest_fixture__identity__*::test_cursor_auto_manifest_first_use_freezes_exact_binding` 1 例、`test_base_draft_fidelity__behavior__functional__*` 中直调 `write_source_unit` 缺新必填 manifest 字段的 6 例、`test_campaign_scale_evidence__derived_session_binding__*::test_campaign_scale_evidence_rejects_auto_model_binding_at_manifest_contract`、`test_campaign_release__terminal_unpublished_partial_retry_selector__*::test_video_only_terminal_unpublished_retry_uses_active_root`、`test_scale_source_pool_homepage_article__catalog_projection_campaign_capsule__*::test_campaign_capsule_copies_only_selected_candidate_capsules_and_cas` 与 `test_scale_source_pool_homepage_article__catalog_projection_row_guard__*::test_projected_refs_are_physically_reverified_by_scale_validator`（fixture 缺 `mediaSourceAdmissionRef` receipt 或 image 候选字段）。生产代码路径本身 fail closed、语义正确；红的是测试替身生态，不阻塞 M1–M10 bounded 闭环。
- 尚缺实现：wave dispatch 与 scale source pool 相关测试的 image/video 候选需要按 `media_source_admission` 真实 writer 流程逐候选生成 accepted admission receipt（含 portable evidence 五件套与真实 contentSha256）。base draft 测试直调 `write_source_unit` 需补齐 `source_unit_meta` oneOf 新必填 manifest 字段；cursor_auto fixture 用例需改写为「非 retry 首用 fail closed + retryOf 场景冻结 exact binding」的新语义。
- 完成判定：绑定 `GWT-004` 的语义波次 dispatch 证据与本 OPEN 列举的全部红用例在不放宽任何生产校验的前提下转绿，且不引入共享可变 receipt 或跳过 admission 校验的测试后门。
- 依赖：`source-discovery-scale-reliability` 的来源发现证据契约保持不变；M100 governed 路径重启（`OPEN-006`）前完成即可。

<a id="open-011"></a>
### OPEN-011 receipt 协议 execution 的 publish→ship 后缀不可达

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 receipt 协议 execution 在 `5.review` pass 后没有可执行的 publish 正向链，只能落 `verdict=blocked` receipt，execution 无法到达 `succeeded`，新协议因此覆盖不了发布后缀。`release pool-append` 只准入已在 canonical 的对象，`task drain-pool-delivery` 仅接受 `manual_required` 且 `lastFailedStage=publish` 的失败重放，退役编排层的 `task execute` 不属于本协议，三者都不能把 approved 对象物化并写入 canonical publish。`stage-contracts/publish.md` 的 PRE 引用 `verify execution-readiness`，而该门要求 execution 终态、`model_readiness.json` 与 `posts/<carrier>` 布局，语义属退役编排层。article 对象可被布局到 `entities/**` 而非 `posts/article/**`，`verify content-execution-layout` 与 `verify stage-artifacts` 均不拦截该漂移。
- 尚缺实现：receipt 协议下的 publish 原子链，即成品物化出对象根 `article.md`+`manifest.json`、canonical 写入与 pool 准入的单命令或冻结序列。publish 契约 PRE 判据需替换为适配 receipt 协议的门。article 归 `posts/article/**` 的布局约定需进入 layout 与 stage-artifacts 检查器并 fail closed。
- 尚缺验收证据：缺 `GWT-020.t1..t3` 的 local_contract 与真实 execution 后缀证据——publish 原子链幂等与失败终态、布局漂移被 `0.plan`/`1.download` 门拦截、ship 落 `next=END` receipt 后 `verify release-lifecycle` 与 `stackctl verify --env gamma` 通过。
- 完成判定：`GWT-020.t1..t3` 成立，一个真实 receipt 协议 execution 从 publish 走到 `ship` 落 `next=END` receipt 且 `execution_state.status=succeeded`。
- 依赖：Data owner 需裁决成品物化的写入责任段（`5.review` POST 或 publish DURING）与 canonical 写入 allowlist。publish 契约 PRE 修订属契约变更需过评审。退役编排层的 `execution-readiness` 门保持存量 campaign 路径不动。

<a id="open-012"></a>
### OPEN-012 receipt/claim 薄驱动层缺少行为级测试锚定

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：receipt/claim 驱动层的关键行为缺少直接测试或门禁，语义漂移只能靠人工发现。`task stage-record` 对 execution_state 的同步、`writing_pack` schema 校验失败路径、`lane-claim` 与 `stage-record` 的 CLI 退出码语义（0 成功、2 参数拒绝、3 冲突）均无独立 local_contract。`loop_driver.sh` 的超时终止只杀直接子进程而非进程组，宿主派生的孙进程可能残留；`--round-timeout` 配置大于 claim TTL 时执行者心跳过期形成双写窗口。stage 枚举在 CLI 与库常量各存一份。orchestration 与 handoff-protocol 文档所述判据与实现之间没有漂移门禁。
- 尚缺实现：进程组级超时终止、round timeout 与 claim TTL 的关系约束、stage 枚举收敛到单一真相源。
- 尚缺验收证据：上列各行为的 local_contract 或门禁，每项一测且不放宽生产语义。
- 完成判定：`GWT-020.t4..t5` 成立。
- 依赖：无外部阻断。
