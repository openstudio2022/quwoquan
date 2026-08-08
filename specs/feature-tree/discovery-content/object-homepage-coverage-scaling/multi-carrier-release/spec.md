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
- 四个 execution 必须从同一 reviewed named main branch、commit、source digest 与 entity catalog digest 并行运行，单一载体失败不得覆盖其他载体工作包，也不得阻止其他载体已合格对象发布。
- `task execute --stage submit-only|campaign-run|campaign-freeze|campaign-lane-run|campaign-finalize|review-only` 是唯一 campaign 门面；单 controller 可用 `campaign-run`，四复制会话必须先由 `campaign-freeze` 等齐四份 immutable submission 并冻结唯一 plan、只读 capsule 与 `planDigest`，再由每个 `campaign-lane-run` 独占一路 claim，最后由 `campaign-finalize` 只聚合 create-once receipt。collision、branch/commit/source/catalog mismatch、重复 claim、主工作树漂移或超时均 fail closed。
- submission-only attempt 只能在无 plan/report/runtime/execution 证据时由 `reconcile-submissions` 收口。
- 已冻结 campaign 若四个 claim 在 author/review/publish 前 terminal failed，只有在四个 execution root 已经受 GC protection 合法清理且 source identity 确实漂移后，才允许 `reconcile-failed-campaign` 写 create-once supersession。
- claim 后若已产生 execution 证据，不得清理或改写该证据。
- 四个 terminal execution 必须分别写入当前源码可复核的 create-once supersession receipt，再由 campaign reconciliation 精确绑定四份 receipt、原 plan/report/runtime/claim/submission 与已变化的 source identity。
- 下一序列逐 lane 声明 `retryOf` 并精确引用 reconciliation receipt。任一进程仍存活、lease 未释放、execution receipt 缺失或字节漂移均 fail closed。
- controller 为四个 lane 建立同一 content-addressed、只读 source/executor capsule，并为每条 lane 分配独立 execution root、queue namespace 与 staging prefix；四 lane 并发 review，每条 lane 按自身 review 结果独立进入 publish，不得因任一 lane 失败而整批 abort，也不得为每条 lane 复制完整 Git object store。
- 四路 workload target 均低于 homepage/article/image/video `100/100/100/10` 的低规模 campaign 可继续使用专属 ReliableTask MongoStore/RedisReadyIndex 与 controller 冻结的 digest-bound worker binary，但不生成或消费规模验证 runtime observer 证据；worker 子进程只验证 binary ref/digest，不得冒充 lane observer。达到或超过该四路 target 的规模验证 campaign 必须同时验证 plan/generation/fence/lane/process-bound observer context，禁止由低规模路径降级或复用。
- lane 终态独立记录为 `published`（`qualified >= quota`）、`partial`（`0 < qualified < quota` 且已合格对象已发布）或 `blocked`（`qualified == 0` 或 review/publish 失败）；campaign 终态为聚合视图：`succeeded`（四路均达标）、`succeeded_partial`（至少一路发布了合格对象）、`blocked`（无任何可发布合格对象）。
- `quota` 是里程碑累计目标，不是发布许可条件；`partial` lane 必须发布全部已合格对象，并将 shortfall 写入 typed evidence，不得因未达 quota 丢弃合格对象。
- 若存在 discard，每个 discard 必须具备非空 `objectRef` 与 typed `issues`，且 `selected == qualified + discarded`；不得要求真实批次必须存在 discard 才准出。
- article/image/video 的 canonical Post manifest 必须显式声明 `contentIdentity=work`；schema、promotion 与 importer 任一层发现缺失或非 `work` 均阻断该对象，禁止由消费者默认补值。
- campaign report 必须保留 named main branch、status、phase、run generation/fencing、heartbeat、review/publish return code、source capsule/execution-root ref、qualified/finalized count 与 cleanup 终态；报告是运行回执，不得成为新的内容或 release 真相源。
- 复制会话的 carrier claim 必须绑定 campaign/run generation/fencing、carrier、execution、只读 source capsule 与独立 execution root；同一 carrier 同一 generation 只能存在一个有效 claim，过期或跨 generation owner 不得 finalize。
- carrier finalize 必须绑定对应 claim、对象级 review/rights/provenance 证据与 publish receipt，并满足 `finalized == qualified >= 1`；同 digest 重放幂等，token、generation、source 或对象闭包漂移 fail closed。未达 quota、存在 shortfall 或存在带 typed issues 的 discard 均不阻止其余全部合格对象 finalize。
- 复制会话低规模准出（COPY_READY）要求四路各 `finalized == qualified >= 1`、receipt/cleanup 闭合；日常 canonical publish 不以 quota 阻断，但 M100/M1000/M10000 promotion 必须满足本 milestone 的累计唯一对象数量硬门和 `shortfallCount=0`。

### REQ-002 生命周期与统一素材 admission

- 受治理配置唯一声明 `productLifecycleState=research|commercial` 与同值 `releaseClass`；环境名、临时环境变量或 fixture 不得推断该状态。
- 每个实体头像/主页媒体、文章图、图片作品与视频资产都必须记录 `acquisitionStatus`、`rightsStatus=verified|unverified|restricted|unknown`、`authorizationRequired`、`distributionDecision=research_allowed|commercial_allowed|blocked` 以及 `sourceUrl/platform/creator/capturedAt/contentSha256/license/termsUrl/authorizationProof/rightsIssues`。
- `research` 允许已取得且权利状态为 verified/unverified/unknown 的资产，restricted、未取得、生成素材或缺来源/权利缺口字段仍阻断；`commercial` 只允许 verified 且具有商业授权证据的 `commercial_allowed`。
- research immutable release 必须冻结权利状态计数、精确 authorization-required asset IDs、四载体 `researchAcceptedCount`、逐来源 assets funnel 和 `containsUnverifiedAssets`；未授权资产不得计入 `commercialAcceptedCount` 或生成 commercial readiness。

### REQ-003 专业图片、文章配图与热门视频

- research 图片检索目录版本化，按 category/entity/season/style/viewpoint/popularity 展开，Pinterest 为第一发现源、图虫为补充；只允许公开直链、平台支持接口或人工提供文件，不新增规避访问控制的抓取器。
- CLI 与 receipt 对每个 `displayName/provider` 输出 `planned/discovered/downloaded/accepted/rejectedAssetCount` 及 verified/unverified/restricted/unknown 计数；下载成功不得把 rights 状态升级为 verified。
- 文章声明为 illustrated 时，图片只来自同一 article sourceUnit 且至少闭合封面与正文图；日常 release 如实记录 illustrated/text-only rate，而 M100 及以上 promotion 额外要求 illustrated rate 不低于 90%、text-only rate 不高于 10%。
- 视频候选保留 play/like/comment/share/favorite 的真实观测与观测时间，并只在同平台、同主题、同时间桶内按 percentile 排序。缺失项保持缺失并标明不可参与热度排序的原因，不得补零或生成虚假排名。
- 低规模验证允许 ranking-ineligible 视频进入日常 research release。M100 及以上 milestone 计数视频必须五项信号完整且具备可比 percentile。只有公开可取得、可解码、可播放、无 DRM、未绕过访问控制且通过安全/相关性门的真实视频文件可进入 research release。

### REQ-004 四环境 research 隔离、商用切换与规模门

- research activation 前，四环境分别证明身份白名单、匿名内容和媒体关闭、无公开 CDN/匿名 URL、分享/导出/索引关闭、内部 App 签名与研究态标识、媒体短期签名 URL 和访问审计；任一缺失立即 `GATE_BLOCK`。
- `appUatEnvelope` 从本 release 对象闭包投影并显式带 `releaseClass=research/productLifecycleState=research`，不可被 commercial package/activation/UAT 复用。
- 商用切换冻结新的 source digest 与 immutable commercial release，对 research 对象逐项替换/撤下/删除，清理缓存和签名 URL，验证四环境未授权 readback 为 0 后重新完成 Creator/attribution/article/image/video/Premium/discovery/rollback/replay/真机 UAT。
- `qwq-data release commercial-transition` 只从 research/commercial 两个不可变 release 与四环境 cache/media/signed-URL 清理及未授权 readback=0 证据生成逐资产 create-once migration receipt；不得修改旧 research release 或用手工布尔值替代环境证据。
- 日常 research release 不以规模数量作为发布许可。
- 三个累计规模 milestone 固定为 homepage/article/image/video：M100=`100/100/100/10`、M1000=`1000/1000/1000/100`、M10000=`10000/10000/10000/1000`。日常 publish 允许 partial，但 milestone promotion 必须逐路满足 `totalUniqueFinalizedCount >= targetCount` 且 `shortfallCount=0`。
- M100 及以上的四份 request envelope 必须共同绑定一个 create-once、同 source 三元组的 scale source-pool plan；plan 对每条 lane 的 source-ready 唯一候选数必须不少于该 execution 冻结的 oversampled `count`，且 sourceUnit/acquisition/rights/quality/playability evidence refs 在首次 claim 前仍逐字节匹配。缺 plan、跨 scale/identity、候选重复、证据缺失或 digest 漂移均返回 `DATA.SOURCE.POOL_SHORTFALL`，禁止在 author 阶段临时发现大批来源。
- 规模 promotion 必须证明四路均真实执行、所有合格对象均已发布、同一 source revision/digest/entity catalog、对象级 review/rights/provenance/安全/可播放/实体引用闭合、跨 lane 写入与重复为 0、60 分钟重叠、frozen observer、资源隔离与 receipt 引用完整。
- 后继 milestone 只新增差额，前驱 immutable release 对象通过 CAS/object refs 原样携带，且 `predecessorCarriedCount + newFinalizedCount = totalUniqueFinalizedCount`。
- M1000 精确消费 M100 promotion，M10000 精确消费 M1000 promotion；任一 release/manifest/source/catalog/receipt identity 漂移均阻断。
- promotion receipt 必须记录各 carrier 的 target/qualified/finalized/selected/discarded/shortfall，以及 object pass、illustrated、video popularity availability/coverage、automatic recovery、first pass、discard 与 quota attainment 的清晰分子、分母和 rate。M100 及以上的 video popularity 与 automatic recovery 是晋级硬门，不能以统计或 non-blocking 状态绕过。
- M100/M1000/M10000 分别至少形成 20/50/100 个 recovery-eligible 故障样本，自动恢复率不低于 95%；fault evidence 的 campaign/run/generation/fence/source identity、完整性与 typed outcome 必须逐项闭合。
- M1000 必须在 72 小时预算内完成；M10000 从 M1000 promotion 起算必须在 7 天预算内完成。若按前驱实测速率计算的 Cursor 容量不足，返回 typed capacity blocker 并保留 checkpoint，禁止静默换 Provider 或降低目标。
- semantic author/reviewer 通过受治理 `cursor_sdk|codex_sdk` adapter 执行，Provider、model、role、SDK/runtime digest 与 run/result digest 在 execution 冻结；默认 Codex Terra 承担 author/reviewer、Codex Sol 承担分层抽样校准，Cursor `auto` 仅在自身 capacity receipt 通过后可显式选择。Provider/model 变化必须创建 `retryOf`，禁止 execution 中静默 fallback，真实 capacity soak 未通过时不得用下载数或框架测试冒充内容稳产。

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
- THEN 仅当全部 approved 对象的 entity identity、creator、tag、source 与媒体处置闭合时生成 immutable release；任一悬挂引用使整次 promotion 失败。
- THEN 四个 review 子进程存在真实时间重叠；任一 lane 的 publish 不得早于该 lane 自身 review 终态，但不得等待其他 lane 的 review/publish 终态。
- THEN 某 lane `0 < qualified < quota` 时终态为 `partial`，已合格对象已 finalize，shortfall 有 typed evidence；`qualified == 0` 时该 lane 为 `blocked`。
- THEN 全批次零 discard 仍允许成功终态；若存在 discard，则每个 discard 必须有非空 `objectRef` 与 typed `issues`。
- THEN mismatch、submission collision、主工作树 drift 或等待 timeout 留下 blocked report。
- THEN lane 级 review/publish 失败只阻塞该 lane。
- THEN source capsule 只创建一次且四个 execution root 相互隔离；终态后临时 staging 被清理，受 release/retry/evidence 引用的对象保持可达。
- THEN carrier claim 只允许匹配 generation/fencing 的 owner finalize；同 digest 重放幂等，陈旧 claim、跨 lane root 或 source capsule 漂移均被拒绝。

<a id="gwt-002"></a>
### GWT-002 research release 可内部消费但不可冒充商用

- GIVEN 四载体对象共享同一 source revision/digest/entity catalog digest，研究素材已取得且完整记录来源与权利缺口。
- WHEN 生成并请求激活 `releaseClass=research` 的 immutable release。
- THEN unverified/unknown 可记为 `research_allowed`，restricted/未取得/生成/缺字段素材与不可播放视频被阻断；文章批次配图率只写入统计，单篇 illustrated 声明的同源封面/正文图闭包仍是对象硬门。
- THEN activation/readiness/App UAT receipt 绑定同一 `releaseId+manifestDigest+releaseClass+productLifecycleState`，匿名身份、公开媒体 URL、分享、导出或索引任一可用均 `GATE_BLOCK`。
- THEN commercial readiness 不存在，且任何未授权 asset ID 不得进入 `commercialAcceptedCount`。

<a id="gwt-003"></a>
### GWT-003 历史 reviewed closure 只能经精确身份采纳进入当前单 source campaign

- GIVEN 一个不可变 source release 已闭合 homepage/article/image/video、creator/tag/entity/media、review 与 rights，且同一 releaseId 的历史 identity collision 已以 append-only incident 记录。
- WHEN 使用现有 campaign 边界请求 `adopt-reviewed-closure`。
- THEN adoption ref 与 receipt 同时绑定精确 source release tuple、incident digest、payload/object/media/review/rights 闭包和全部上游 execution/source provenance，任一 digest、ref、字节或归属不一致即 `GATE_BLOCK`。
- THEN homepage/article/image/video 各得到一个新 execution，对象引用精确覆盖 source desired state，正文、媒体、review 和 rights 业务 payload 不变，当前 campaign/release header 只携带一个可活动 source identity。
- THEN identity incident 中的 `protectedExecutionIds` 精确等于全部观测 identity 的 execution closure，incident 存在时 discard/GC 保持 fail closed；重放同一 adoption 只能读取同 digest receipt，不得覆盖或变造历史证据。

<a id="gwt-004"></a>
### GWT-004 ReliableTask 实测证据与规模验证到扩展规模晋级

- GIVEN selected semantic Provider 的 preflight 与 capacity soak 均为 `ready=true`，四条 execution envelope 已冻结相同 campaign/run/generation/fencing/source identity，Runtime owner 提供受治理的只读 MongoStore 与 RedisReadyIndex observer。
- WHEN 四 lane 在 ReliableTask 上重叠运行至少 60 分钟、每 lane 完成至少 10 个真实 semantic job，并由 frozen observer 记录队列、资源与恢复事实。
- THEN observer evidence 必须精确绑定四条 frozen execution envelope，跨 execution/generation/source 读取立即失败；Data 禁止用 local object-job mirror、环境变量或手工样本替代 live queue/job/resource/recovery evidence。
- THEN 无重复发布、丢对象或跨 lane 写入，并通过 controller/worker/总 RSS、临时工作集、terminal cleanup、queue age 与 heartbeat 资源门；automatic recovery 只按 recovered/eligible 记录，零分母显式记为未执行，不参与 promotion 判定。
- THEN 只有四路累计唯一 finalized 达到 M100 `100/100/100/10`、shortfall=0、文章配图与视频热度硬门通过后，才可创建新的 immutable research release 与 create-once M100 promotion receipt。
- THEN M1000 只新增到累计 `1000/1000/1000/100` 的差额并精确消费 M100 identity；M10000 再新增到累计 `10000/10000/10000/1000` 的差额并精确消费 M1000 identity，任一级未达数量或时间预算不得晋级。
- THEN M100/M1000/M10000 的四个 envelope、submission、execution policy 与 runtime observer 精确携带同一 source-pool plan digest；任一 lane 的冻结 pool candidateCount 小于该 lane oversampled count，或任一 evidence ref 在 claim 前不存在/摘要漂移，均不得派发 Cursor author job。

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
- 影响或价值：受治理 MongoStore+RedisReadyIndex observer、stage-scoped immutable job-set 与 Data/Service digest wire 已进入源码；当前阻断转为 production worker E2E、fresh Cursor preflight、足量专业来源池、三档累计 promotion 合同与真实四路数量未闭合。在这些证据缺失时保持 `GATE_BLOCK`。
- 完成判定：`GWT-001/GWT-002/GWT-004` 有 local_contract 与真实 Mongo+Redis/Cursor API integration。四 lane 同身份重叠至少 60 分钟，无重复/跨 lane 并通过资源和恢复预算；依次生成达到实际数量硬门的 M100、M1000、M10000 immutable research release 与 create-once promotion，最终 M10000 在 7 天预算内完成。
- 依赖：Data/Runtime/Service owner共同维护 governed ReliableTask wire；Testing/Ops owner负责四环境 identity/readback/rollback/replay，不由 Data 修改 stackctl 或环境。
