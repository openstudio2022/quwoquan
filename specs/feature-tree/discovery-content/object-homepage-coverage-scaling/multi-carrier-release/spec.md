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
- `task execute --stage submit-only|campaign-run|review-only` 是唯一 campaign 门面；controller 等齐四份 immutable submission 后才冻结唯一 plan 与 `planDigest`，collision、branch/commit/source/catalog mismatch、主工作树漂移或超时均 fail closed。
- controller 为四个 lane 建立同一 frozen commit 的 detached disposable clone，四 lane 并发 review；每条 lane 按自身 review 结果独立进入 publish，不得因任一 lane 失败而整批 abort。
- lane 终态独立记录为 `published`（`qualified >= quota`）、`partial`（`0 < qualified < quota` 且已合格对象已发布）或 `blocked`（`qualified == 0` 或 review/publish 失败）；campaign 终态为聚合视图：`succeeded`（四路均达标）、`succeeded_partial`（至少一路发布了合格对象）、`blocked`（无任何可发布合格对象）。
- `quota` 是里程碑累计目标，不是发布许可条件；`partial` lane 必须发布全部已合格对象，并将 shortfall 写入 typed evidence，不得因未达 quota 丢弃合格对象。
- 若存在 discard，每个 discard 必须具备非空 `objectRef` 与 typed `issues`，且 `selected == qualified + discarded`；不得要求真实批次必须存在 discard 才准出。
- article/image/video 的 canonical Post manifest 必须显式声明 `contentIdentity=work`；schema、promotion 与 importer 任一层发现缺失或非 `work` 均阻断该对象，禁止由消费者默认补值。
- campaign report 必须保留 named main branch、status、phase、review/publish return code、clone ref、qualified/finalized count 与 cleanup 终态；报告是运行回执，不得成为新的内容或 release 真相源。
- 复制会话准出（COPY_READY）可要求每路达到约定 quota/count 证明，但不得阻止未达复制门的合格内容发布。

### REQ-002 生命周期与统一素材 admission

- 受治理配置唯一声明 `productLifecycleState=research|commercial` 与同值 `releaseClass`；环境名、临时环境变量或 fixture 不得推断该状态。
- 每个实体头像/主页媒体、文章图、图片作品与视频资产都必须记录 `acquisitionStatus`、`rightsStatus=verified|unverified|restricted|unknown`、`authorizationRequired`、`distributionDecision=research_allowed|commercial_allowed|blocked` 以及 `sourceUrl/platform/creator/capturedAt/contentSha256/license/termsUrl/authorizationProof/rightsIssues`。
- `research` 允许已取得且权利状态为 verified/unverified/unknown 的资产，restricted、未取得、生成素材或缺来源/权利缺口字段仍阻断；`commercial` 只允许 verified 且具有商业授权证据的 `commercial_allowed`。
- research immutable release 必须冻结权利状态计数、精确 authorization-required asset IDs、四载体 `researchAcceptedCount`、逐来源 assets funnel 和 `containsUnverifiedAssets`；未授权资产不得计入 `commercialAcceptedCount` 或生成 commercial readiness。

### REQ-003 专业图片、文章配图与热门视频

- research 图片检索目录版本化，按 category/entity/season/style/viewpoint/popularity 展开，Pinterest 为第一发现源、图虫为补充；只允许公开直链、平台支持接口或人工提供文件，不新增规避访问控制的抓取器。
- CLI 与 receipt 对每个 `displayName/provider` 输出 `planned/discovered/downloaded/accepted/rejectedAssetCount` 及 verified/unverified/restricted/unknown 计数；下载成功不得把 rights 状态升级为 verified。
- 文章图片只来自同一 article sourceUnit，至少封面与正文图；批次 illustrated rate 不低于 90%，text-only 不高于 10%。
- 视频候选记录 play/like/comment/share/favorite 与 observedAt，并只在同平台、同主题、同时间桶内按 percentile 排序；缺指标必须标为不可参与热度排序，不得补零伪装。只有公开可取得、可解码、可播放、无 DRM、未绕过访问控制且通过安全/相关性门的真实视频文件可进入 research release。

### REQ-004 四环境 research 隔离、商用切换与规模门

- research activation 前，四环境分别证明身份白名单、匿名内容和媒体关闭、无公开 CDN/匿名 URL、分享/导出/索引关闭、内部 App 签名与研究态标识、媒体短期签名 URL 和访问审计；任一缺失立即 `GATE_BLOCK`。
- `appUatEnvelope` 从本 release 对象闭包投影并显式带 `releaseClass=research/productLifecycleState=research`，不可被 commercial package/activation/UAT 复用。
- 商用切换冻结新的 source digest 与 immutable commercial release，对 research 对象逐项替换/撤下/删除，清理缓存和签名 URL，验证四环境未授权 readback 为 0 后重新完成 Creator/attribution/article/image/video/Premium/discovery/rollback/replay/真机 UAT。
- `qwq-data release commercial-transition` 只从 research/commercial 两个不可变 release 与四环境 cache/media/signed-URL 清理及未授权 readback=0 证据生成逐资产 create-once migration receipt；不得修改旧 research release 或用手工布尔值替代环境证据。
- M100 要求四载体各 `researchAcceptedCount>=100`、跨 lane 写入与重复为 0、文章配图率至少 90%；`qwq-data release research-promote-scale` 还必须绑定同一 manifest digest、资源隔离与治理阈值以上的自动恢复率，才写 create-once M100 promotion receipt。M1000 只能消费该 receipt。Cursor semantic author 保持 `cursor_sdk/auto`，真实 capacity soak 未通过时不得用下载数或框架测试冒充内容稳产。

## 4. 契约引用

- release：`quwoquan_data/schema/release/release_header.schema.json`
- asset admission：`quwoquan_data/schema/release/release_asset_admission.schema.json`
- lifecycle policy：`quwoquan_data/schema/governance/content_distribution_policy.schema.json`
- environment readiness：`quwoquan_data/schema/release/environment_release_readiness.schema.json`
- research M100 promotion：`quwoquan_data/schema/release/research_scale_promotion.schema.json`
- commercial transition：`quwoquan_data/schema/release/commercial_transition.schema.json`
- ship：`quwoquan_data/schema/release/ship_report.schema.json`
- campaign report：`quwoquan_data/schema/execution/content_campaign_report.schema.json`
- lane receipt：`quwoquan_data/schema/execution/content_campaign_lane_receipt.schema.json`

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
- THEN 所有已创建 detached clone 均被清理。

<a id="gwt-002"></a>
### GWT-002 research release 可内部消费但不可冒充商用

- GIVEN 四载体对象共享同一 source revision/digest/entity catalog digest，研究素材已取得且完整记录来源与权利缺口。
- WHEN 生成并请求激活 `releaseClass=research` 的 immutable release。
- THEN unverified/unknown 可记为 `research_allowed`，restricted/未取得/生成/缺字段素材被阻断，文章配图率低于 90% 或视频不可播放同样阻断。
- THEN activation/readiness/App UAT receipt 绑定同一 `releaseId+manifestDigest+releaseClass+productLifecycleState`，匿名身份、公开媒体 URL、分享、导出或索引任一可用均 `GATE_BLOCK`。
- THEN commercial readiness 不存在，且任何未授权 asset ID 不得进入 `commercialAcceptedCount`。

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
- 影响或价值：当前尚无受保护白名单内部身份 adapter 的四环境 readback，现有匿名 guest verifier 明确不可作为 research 证据；Cursor `cursor_sdk/auto` capacity soak 也未通过，且现存文章批次为 text-only，不能形成 M100 research promotion receipt。
- 完成判定：`GWT-001/GWT-002` 有 local_contract、受保护身份 API integration 与四环境内部 App user_acceptance 直接证据；四载体各达 M100、文章配图率至少 90%，并产出同一 release 的 activation/readiness/App UAT receipt。
