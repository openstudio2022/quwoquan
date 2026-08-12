# L3 Story：多载体内容与主页发布 (`multi-carrier-release`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-008 / SCN-014`](../../../spec.md#scn-014)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容运营者，我希望文章、图片、视频和主页对象以独立 execution 并行生产，同时共享冻结实体目录与 release 边界，从而能分别恢复失败并复核来源、媒体、实体与环境消费是否闭合。

## 2. 范围与非目标

### In Scope

- 四个 carrier execution 共享不含运行身份的 canonical entity catalog digest，各自冻结 target set、quota 与终态。
- 各载体复用同一创建、审核、promotion 和 ship 生命周期。
- 批次级/跨载体聚合门只作目标与统计；四载体共用 acquisition/rights/distribution admission，research 只放宽未验证的分发权利，不放宽访问控制、内容安全、隐私、未成年人、恶意文件、去重、实体相关性、质量或可播放性。

### Out of Scope

- 为不同地区或载体维护第二套发布目录与运行台账。
- 绕过登录、付费墙、验证码、访问控制、DRM 或平台技术限制取得素材。
- 直接生成图片或视频，或将 deterministic image-sequence 冒充已取得的可播放视频。

## 3. 行为要求

### REQ-001 多载体统一发布边界

- 每个发布对象必须闭合 creator、tag、entity、media 与 source 引用；运行 receipt 只能写入输出目录，不得回写静态真相源。
- homepage、article、image、video 不以彼此的 execution 或 publish 结果作为运行前置；post 只依赖可解析的 canonical entity identity。
- 四个 execution 必须从同一不可变 source-definition capsule、execution bundle 与 entity catalog digest 并行运行，单一载体失败不得覆盖其他载体工作包，也不得阻止其他载体已合格对象发布；capsule 封存后不得再用 live worktree 漂移否定该 execution。
- `task execute --stage submit-only|campaign-run|campaign-freeze|campaign-lane-run|campaign-finalize|review-only` 是唯一 campaign 门面；单 controller 可用 `campaign-run`，四复制会话必须先由 `campaign-freeze` 等齐四份 immutable submission 并冻结唯一 plan、只读 capsule 与 `planDigest`，再由每个 `campaign-lane-run` 独占一路 claim，最后由 `campaign-finalize` 只聚合 create-once receipt。collision、branch/commit/source/catalog mismatch、重复 claim、主工作树漂移或超时均 fail closed。
- submission-only attempt 只能在无 plan/report/runtime/execution 证据时由 `reconcile-submissions` 收口。
- 已冻结 campaign 若四个 claim 在 author/review/publish 前 terminal failed，只有在四个 execution root 已经受 GC protection 合法清理且 source identity 确实漂移后，才允许 `reconcile-failed-campaign` 写 create-once supersession。
- claim 后若已产生 execution 证据，不得清理或改写该证据。
- 四个 terminal execution 必须分别写入当前源码可复核的 create-once supersession receipt，再由 campaign reconciliation 精确绑定四份 receipt、原 plan/report/runtime/claim/submission 与已变化的 source identity。
- 下一序列逐 lane 声明 `retryOf` 并精确引用 reconciliation receipt。任一进程仍存活、lease 未释放、execution receipt 缺失或字节漂移均 fail closed。
- controller 为四个 lane 建立同一 content-addressed、只读 source/executor capsule，并为每条 lane 分配独立 execution root、queue namespace 与 staging prefix；四 lane 并发 review，每条 lane 按自身 review 结果独立进入 publish，不得因任一 lane 失败而整批 abort，也不得为每条 lane 复制完整 Git object store。
- semantic author/reviewer 只消费 create-once 本地 journal 与只读 source capsule。它的 preflight、并发与质量结论不依赖 Mongo、Redis 或任何环境。review 通过后才生成 immutable pool-delivery intent，ReliableTask 与 generation/fence/worker binary 仅负责 intent 的幂等交付。transport 不可用时对象保持 `deliveryPending`，不得撤销 review、重复调用 semantic Provider 或阻塞其它 lane。
- lane 终态独立记录为 `published`（`qualified >= quota`）、`partial`（`0 < qualified < quota` 且已合格对象已发布）或 `blocked`（`qualified == 0` 或 review/publish 失败）；campaign 终态为聚合视图：`succeeded`（四路均达标）、`succeeded_partial`（至少一路发布了合格对象）、`blocked`（无任何可发布合格对象）。
- `quota` 是里程碑累计目标，不是发布许可条件；`partial` lane 必须发布全部已合格对象，并将 shortfall 写入 typed evidence，不得因未达 quota 丢弃合格对象。
- 若存在 discard，每个 discard 必须具备非空 `objectRef` 与 typed `issues`，且 `selected == qualified + discarded`；不得要求真实批次必须存在 discard 才准出。
- article/image/video 的 canonical Post manifest 必须显式声明 `contentIdentity=work`；schema、promotion 与 importer 任一层发现缺失或非 `work` 均阻断该对象，禁止由消费者默认补值。
- 新增 canonical Post 必须显式携带稳定 `contentId`、递增 `version`、`sourceType=data`、`variantPurpose`、`admission.processResult/qualityResult/usageScope` 与 `status`。只有 `completed + passed + active` 可被 ReleaseManifest 选择。
- 统一池 reader 只接受显式 create-once pool record。缺 admission、稳定 `contentId/contentVersion`、完整 `sourceAttribution` 或 source identity 的历史对象按对象排除，不得在读取时从 review、路径或当前 source identity 推导。可修复对象只能由 governed repair 基于 canonical bytes 与 fresh source evidence 追加新的 `recordSequence`，保持原 `contentVersion`。旧 record 与旧 task receipt 均不改写、不复用。
- 环境定向 Manifest 从同一 pool 生成固定载体/作者轮转顺序并按 Alpha 2,100、Beta 10k、Gamma 100k 截取稳定 Post 前缀，Homepage 不计 Post cap；环境无关 M100/M1000 Research Manifest 精确冻结 cohort 并可由四环境消费。相同 `contentId` 在同一 manifest 只出现一个版本，有供给且容量允许时 article/image/video 必须同时出现。
- campaign report 必须保留 named main branch、status、phase、run generation/fencing、heartbeat、review/publish return code、source capsule/execution-root ref、qualified/finalized count 与 cleanup 终态；报告是运行回执，不得成为新的内容或 release 真相源。
- 复制会话的 carrier claim 必须绑定 campaign/run generation/fencing、carrier、execution、只读 source capsule 与独立 execution root；同一 carrier 同一 generation 只能存在一个有效 claim，过期或跨 generation owner 不得 finalize。
- carrier finalize 必须绑定对应 claim、对象级 review/rights/provenance 证据与 publish receipt，并满足 `finalized == qualified >= 1`；同 digest 重放幂等，token、generation、source 或对象闭包漂移 fail closed。未达 quota、存在 shortfall 或存在带 typed issues 的 discard 均不阻止其余全部合格对象 finalize。
- 每个生成批次只按对象记录过程完成、质量和授权范围；合格对象立即追加到统一池，批次未达 quota、存在 shortfall 或其他对象失败均不阻断已合格对象。M100/M1000/M10000 只按累计唯一对象数量判断是否达标，均为数量下限而不是停止生产或准入的上限。
- M1000 sourcing 以四川、浙江全量 frontier 为产品范围：穷举两省全部市、区、县与可识别 POI，合格对象即使显著超过 1000 也全部准入。不得设置单一区县、单一实体类型、Provider 或 creator 数量/比例上限。
- M10000 将同一 frontier 先推广到全国，再扩海外，国内外只共享一套 canonical geo/entity/source contract。

### REQ-002 生命周期与统一素材 admission

- 受治理配置唯一声明 `productLifecycleState=research|commercial` 与同值 `releaseClass`；环境名、临时环境变量或 fixture 不得推断该状态。
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
- 商用切换冻结新的 source digest 与 immutable commercial release，对 research 对象逐项替换/撤下/删除，清理缓存和签名 URL，验证四环境未授权 readback 为 0 后重新完成 Creator/attribution/article/image/video/Premium/discovery/rollback/replay/真机 UAT。
- `qwq-data release commercial-transition` 只从 research/commercial 两个不可变 release 与四环境 cache/media/signed-URL 清理及未授权 readback=0 证据生成逐资产 create-once migration receipt；不得修改旧 research release 或用手工布尔值替代环境证据。
- 日常 research release 不以规模数量作为发布许可。
- Content candidate 必须按 `prepared -> imported -> projected -> verified -> active` 单轨推进；逐阶段持久化脱敏 receipt，记录 duration、attempted/success count、checkpoint 与首个 typed blocker。只有 `verified` 可切换 active pointer，任一阶段失败保留 previous active 与已成功阶段事实。
- 三个累计规模 milestone 固定为 homepage/article/image/video：M100=`100/100/100/10`、M1000=`1000/1000/1000/100`、M10000=`10000/10000/10000/1000`。这些数字均为 promotion 下限；日常 publish 允许 partial，已合格对象超过下限时继续准入，不为凑整数截断 frontier。milestone promotion 必须逐路满足 `totalUniqueFinalizedCount >= targetCount` 且 `shortfallCount=0`。
- source-pool、oversampling、Provider、并行时长、资源和恢复事实用于计划容量与定位瓶颈；它们不得改变一个已完成、质量合格且在授权范围内对象的池准入结果。
- 规模 promotion 只验证累计唯一对象数量、对象准入结果和所构建 ReleaseManifest 的引用闭包；精确重复不计数，缺引用对象留在池中等待修复，不阻断其他合格对象发布。
- 后继 milestone 只生成累计目标差额。前驱 promotion receipt 只记录 lineage，不作为新合格对象入池或当前 milestone 计数的前置门。M1000 的 source discovery/acquisition、semantic 与 review 可以在 M100 环境验收期间并行；M1000 promotion 前必须补足同一 M100 Research release 的 Alpha activation/readback 与 100 例 App UAT。该产品阶段门不撤销池中任何 M100 对象，也不冻结后继来源队列。
- promotion receipt 必须记录各 carrier 的 target、admitted、publishable、deliveryPending、selected、excluded 和 gap；illustrated、video popularity、automatic recovery、source mix、并行时长与资源使用只作为统计。
- M1000 与 M10000 的时间、Provider 容量和故障恢复样本用于计划和 SRE 评估；目标未按期完成时报告实际 gap，不撤销已经完成的池追加或已验证 Release。
- semantic author/reviewer 通过受治理 `cursor_sdk|codex_sdk` adapter 执行，Provider、model、role、SDK/runtime digest 与 run/result digest 在 execution 冻结。受治理生产主选为 exact `cursor_grok/grok-4.5`。
- `cursor_auto` 只能在父 execution 已以允许的 typed provider/model failure 终止后，以新的 `retryOf` 显式选择。禁止 execution 中静默 fallback 或由 SDK Auto 首次路由替代 Grok 证据，真实 capacity soak 未通过时不得用下载数或框架测试冒充内容稳产。
- 10 万级不是单一 promotion 事务：使用同一分片键持续生产，并以 1K/5K/10K immutable release waves 累计到不少于 100000 个合格对象；单 wave 或 named scale 仍是下限，不是总量上限。达到 100K 稳产还须证明跨分片全局去重、checkpoint 恢复、dead-letter 隔离以及连续 7 天无全局冻结的 soak。

### REQ-005 已审核闭包采纳与 release identity incident

- `adopt-reviewed-closure` 是现有四 lane campaign/release 单轨上的一种身份收口方式，不是第二个 aggregator、第二套 publish 目录或手工 manifest 入口。它只能采纳一个已存在且不可变的 reviewed release 对象闭包，不重新生成、不改写正文/媒体/审核/权利事实，不修改上游 release。
- 采纳引用必须绑定精确 source release tuple `releaseId + payloadSha256 + canonicalMerkle + attestationFileSha256`，并对 release header、desired state、object index、media manifest、每个 review/rights evidence 和媒体公共切片逐文件复核摘要；任一字节、对象引用或媒体所有权漂移即 fail closed。
- 新的四个 adoption execution 必须共享唯一当前 `sourceDigest + entityCatalogDigest -> sourceRevision`，且 release 激活身份仍只允许一个 `sourceDigest`。上游历史 `sourceDigests/executionIds` 只能以冻结 provenance 留在 adoption receipt，不得被提升为新 release 的多 source active identity。
- 同一 `releaseId` 曾对应多个 payload/canonical identity 时，必须先生成 append-only、create-once identity incident；incident 按上述精确 tuple 保留每次观测的 attestation 与 execution closure，且所有受影响 execution 在 incident 未关闭前不得 discard 或 GC。仅 releaseId 相等、仅文件名相等或仅有历史口头记录都不构成可采纳证据。
- 对 provenance 合同引入前已经 create-once 的 legacy incident，只允许 CLI migration 在验证原 incident 精确文件摘要、legacy receipt digest、合同引入 commit/时间边界、旧 schema 闭集、同目录 snapshot 路径/文件摘要/attestation identity 与 execution closure 后，将每个 snapshot 分类为 `original_file`。migration 不得修改原 incident/evidence，只能在独立 namespace 写 source-bound receipt 与当前 schema projection；GC/discard 仅在原文件仍逐字节匹配且 projection 全量复核通过时消费该 projection，否则继续 fail closed。

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
- reviewed closure adoption ref：`quwoquan_data/schema/execution/reviewed_closure_adoption_ref.schema.json`
- reviewed closure adoption receipt：`quwoquan_data/schema/execution/reviewed_closure_adoption_receipt.schema.json`
- release identity incident：`quwoquan_data/schema/release/release_identity_incident.schema.json`
- legacy incident migration：`quwoquan_data/schema/release/release_identity_incident_legacy_migration.schema.json`
- failed campaign reconciliation：`quwoquan_data/schema/execution/campaign_failed_execution_reconciliation_receipt.schema.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 独立载体并行且引用闭包后才允许 promotion

- GIVEN homepage、article、image、video 各有一个 immutable execution，并共享同一 named main branch、commit、source digest 与 entity catalog digest。
- WHEN 四个 execution 并行生产且操作者请求聚合并 promotion release。
- THEN post 不等待 homepage execution 或 publish，任一载体失败只保留在自身 evidence，其他载体已合格对象仍可 publish。
- THEN 仅从 entity identity、creator、tag、source 与媒体处置全部闭合的 approved 对象中选择 immutable cohort；悬挂引用只排除对应对象，足量有效 cohort 仍可 promotion。
- THEN 四个 review 子进程存在真实时间重叠；任一 lane 的 publish 不得早于该 lane 自身 review 终态，但不得等待其他 lane 的 review/publish 终态。
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

- GIVEN selected semantic Provider 的 preflight 与 capacity soak 均为 `ready=true`，四条 execution 各自冻结 semantic journal/source identity；pool delivery 另有受治理的 MongoStore/RedisReadyIndex generation、fence 与 worker bundle。
- WHEN 任意 Data 批次产生完成、质量合格且具备 Research 或 Commercial 授权范围的 Homepage、Article、Image 或 Video。
- THEN 每个合格对象立即幂等追加到统一池；失败、授权待定、重复或缺交付引用的对象分别报告，不撤销同批其他对象。
- THEN Mongo、Redis 或目标环境不可用时，source/compose/author/review 继续运行；reviewed 对象写入 delivery intent 并停止重复 semantic 调度，transport 恢复后按同一 digest exact-once drain。
- THEN 日常 Research Release 从 publishable 对象构建并可在未达到 milestone 时发布；Manifest 冻结后导入、Search、Recommendation、Homepage 和 Persona 数量必须全量一致。
- AND import 成功只到 `imported`；Search/Recommendation/Homepage/Tag/媒体与 Persona consumer 投影及 readback 全部 verified 后才可进入 `active`，失败 receipt 不得覆盖 previous active。
- THEN 累计唯一 publishable 达到 M100 `100/100/100/10` 时标记 M100 达标；M1000 与 M10000 分别只按 `1000/1000/1000/100` 和 `10000/10000/10000/1000` 判断，不依赖前驱 promotion、Provider、热度、恢复率或并行时长，超过下限的全部合格对象继续准入。
- THEN source-pool、Provider、资源、恢复、配图率和视频热度保留在同一报告的 statistics 中，任何变化都不得改变对象准入与 milestone 数量结果。
- THEN 同一批或同一环境中的个别对象失败只把该对象标为 excluded/deliveryPending；冻结 Manifest 后仍全量一致、失败候选不替换 previous verified release。
- THEN 有 20 个质量、Research 授权与交付闭包均合格的视频时，Alpha/Beta/Gamma 的稳定选择均包含全部 20 个，M100 的 10 个视频只是里程碑下限而非发布上限。

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
- 影响或价值：当前仍缺 production worker E2E、fresh Cursor preflight、足量专业来源池、真实四路累计数量与可证明物理主机的 remote executor，所以保持 `GATE_BLOCK`。
- 完成判定：`GWT-001/GWT-002/GWT-004` 有 local_contract 与真实 Content importer、Search、Recommendation、Homepage、Persona readback；依次达到 M100、M1000、M10000 的累计唯一数量并能从统一池构建和发布对应 immutable Research Release。
- 依赖：Data/Runtime/Service owner维护对象生成与池追加；Testing/Ops owner负责同一 Research Manifest 在 Alpha/Beta/Gamma/Prod 的独立 import/private-isolation/verify/activate/rollback/replay，Commercial 转换另立显式授权 release。Provider 与 remote executor 只影响生成吞吐和计划时间，不改变已合格对象准入。
