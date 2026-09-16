# L3 Story：多载体内容与主页发布 (`multi-carrier-release`)

> 所属能力：[对象主页覆盖扩展](../spec.md)
>
> Journey / Scenario：[`JNY-008 / SCN-014`](../../../spec.md#scn-014)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容运营者，我希望文章、图片、视频和主页对象以独立 execution 分别生产，共享冻结实体目录与 release 边界，并把质量合格的对象作为 immutable producer handoff 交付；这样每个对象可按原始来源、创作、review 与 publish proof 复核并累计进入规模里程碑，权利信息只作为记录事实随对象保留，而下游消费与公众可见性不改变 producer 完成事实。

## 2. 范围与非目标

### In Scope

- 四个 carrier execution 共享不含运行身份的 canonical entity catalog digest，各自冻结 target set、quota 与终态。
- 各载体复用同一 producer 创建、审核、publish 与 release 生命周期，并止于 immutable producer handoff；环境 import/activate/readback/UAT/EAF 仅为下游消费背景，不构成本 Story 的 producer 验收。
- 本 producer 默认只有一套 immutable release/handoff，不要求或声明发布类别、运行类别或命名消费轨道；逐对象只保留真实 rights facts，不保留对象级 research/commercial 分类维，且权利状态不构成 publish/release 阻断。公众可见性按 `REQ-002` 的开发验证统一开放裁定执行，环境差异只由环境配置表达，不据此建立第二 workflow、pool 或 semantic queue。
- 批次级/跨载体聚合门只作目标与统计；四载体共用 acquisition/rights/distribution 记录，权利只记录不阻断，但不放宽访问控制、内容安全、隐私、未成年人、恶意文件、去重、实体相关性、质量或可播放性。
- 经确认的请求只由宿主 Cursor/Codex IDE/CLI Agent 直接执行 canonical content-production Skill；identity-only candidate-backed 工作包、producer 六步（init → acquire → author → review → publish → release）的三份 seal receipts、approved object package、canonical pool 与 immutable release handoff 单轨推进。handoff 不携带 UAT/sample authority、import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback facts。
- 可复制内容团队模板、账号部署绑定与当次任务授权分层；每团队采用创作总监、创作者、独立 QA、电脑管家四类岗位，创作者与 QA 可有多个独立实例，不设固定七人上限或载体组长；总监承担唯一发布与保流责任，独立 QA 不由创作者临时兼任。初始化核对角色、共享有效任务版本与知识入口，不启动生产。轮换接管保持唯一写者；分片并行仅在对象范围不相交且宿主前提已证时启用。十团队放量只消费显式具名分片与当前全局轮次，不因账号、Bot 或进程在线自动获得工作。

### Out of Scope

- 按需意图 preview 与 envelope 编译（归 [`work-request-compilation`](../work-request-compilation/spec.md)）。
- article 来源预筛、immutable candidate binding 与 canonical 池唯一写路径（归 [`on-demand-content-pool-admission`](../on-demand-content-pool-admission/spec.md)）；旧 media-work-unit execution schema 不在现役闭包。
- 来源发现的逐 target 计划、取得与 typed 结果（归 [`source-discovery-scale-reliability`](../source-discovery-scale-reliability/spec.md)）；宿主串并行不形成仓内调度、slot 或心跳控制面。
- invalid canonical identity 的修复裁决（归 [`canonical-content-identity-recovery`](../canonical-content-identity-recovery/spec.md)）。
- 为不同地区或载体维护第二套发布目录与运行台账。
- 绕过登录、付费墙、验证码、访问控制、DRM 或平台技术限制取得素材。
- 直接生成图片或视频，或将 deterministic image-sequence 冒充已取得的可播放视频。
- 改变 homepage、image 或 video 的真正来源、权利与质量硬判据；但其执行时点统一硬切为 candidate binding 仅冻结对象身份、`acquire` 由 AI 出网取得来源后以零网络 ingest 清单交脚本机械派生 bytes/CAS/probe 事实，相关性、水印与保留由 AI 直接判断。
- 冻结期多样性准入的每实体累计上限与 Top-N 上限数值：阈值由多样性策略的既有 owner 单点拥有，本 Story 只消费其准入结论，并约束该结论的归属、呈现与批次级零合格归因。
- 将 Data 的 `homepage` carrier 解释为 App micro。carrier 闭集固定为 `homepage|article|image|video`；App entry surface 与二维 UAT 矩阵属于下游消费规格，不构成 producer handoff 的内容或验收。
- 切 Grok 账号、创建或删除 Bot、启停 Routine、正式生产、跨账号消息桥、仓内模型路由或第二套生产 Skill。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多载体宿主 execution 与 pool→release 单轨

- 每个发布对象必须闭合 creator、tag、entity、media、source、rights 与 independent review；`4.draft` 每对象只有一个 carrier 主产物，`5.review` 每对象只有一个 `content_review.json`。运行 receipt 只能写入 execution/output，不回写静态真相源。
- execution 的 `targetRef` 是稳定物理过程 locator，不是 canonical 业务身份或内容版本；不得通过给 process ref 补 `/1` 或其它版本后缀来制造对象身份。task init 必须为每个 target 冻结 immutable target descriptor，使该 process locator 唯一映射到 canonical logical entityRef/entityId 与独立的 canonical content version；descriptor、candidate/source/package identity 及其摘要共同绑定这份映射。映射缺失、歧义、重复或任一摘要/版本漂移必须在任何 execution、review、publish 或 pool 写入前 typed fail closed。映射的数据形态、字段与错误码只由 Data schema owner 定义，本文不复制 wire。
- homepage、article、image、video 共享 canonical entity catalog，但各自拥有由 identity-only candidate bindings 初始化的 immutable execution。唯一语义与推进主体是直接执行 `.agents/skills/content-production/SKILL.md` 的宿主 AI Agent（包括 Cursor/Codex IDE/CLI 与 Grok Bot，均使用同一 Skill）；新任务不得调用或新增仓内 resolver/projector/runner/controller/queue/语义调度或业务完成 registry/SDK/自动恢复、`task execute`（含 plan-only）或 pool-dispatch。只保存具名分片占用与资源预留硬事实的最小本地 SQLite 协作库按 `REQ-022` 例外允许。
- candidate binding 只冻结目标对象身份，不要求 task-init 前 source/media admission。中性 `task init` 从一份 round spec 原子创建该轮全部 carrier execution 的三份输入后，宿主严格执行 producer 六步：`acquire` 由 AI 以宿主原生能力出网检索、取证并下载来源，再按 execution 提交一份零网络 ingest 清单，脚本只从本地字节机械派生 sha256/CAS/mime/probe/poster、按申报 license 派生 `rightsStatus`（物理目录 `1.download/`）；`author` 由 AI 直接创作每对象唯一 carrier 产物（`4.draft/`），标题、tagRefs、creatorProfileId 与选用资产由产物自身声明；`review` 由另一真实会话按 execution 提交一份判断输入，seal 机械扇出到逐对象 `5.review/content_review.json`。每步完成后由 `task seal` 自行校验硬事实（schema、引用、摘要、媒体字节、tagRefs、author≠reviewer）并 create-once 写 receipt `001-1.download`/`002-4.draft`/`003-5.review`；不存在 stage-open、宿主 verifierFacts、2.quality/3.compose 产物。`publish` 是单对象事务，`release finalize` 成功即 `END`。
- 一个 execution 由一个真实 author actor 主会话完整负责获准的 init、来源取证、下载、ingest 与 author seal，不保留另一会话代跑的双轨；`4.draft` 的 actor/invocation 与产物 exact refs/digests 由 `002-4.draft` seal receipt 冻结，`001-1.download` 记录同一作者会话的真实提交 invocation，不以主子会话切换替代本人责任或绕过容量；该 seal 同样逐对象校验来源硬事实，ingest 失败或字节漂移的对象只以 typed issue 退出本 execution，至少一个对象取得来源即 `pass`，后续 `4.draft` 只校验 `001-1.download` resultRefs 中的对象。`002-4.draft` seal 逐对象校验产物硬事实（非空、tagRefs 解析、creatorProfileId 解析、homepage 百科主源）并一次报出全部违规：不合规对象只记 typed issue 并退出本 execution，至少一个合规产物即 `pass`，只有零合规产物或 stage-wide identity/integrity failure 才 `blocked`。`5.review` 由另一个真实 reviewer actor 会话负责，其判断输入的覆盖集合是 `002-4.draft` receipt 的 resultRefs 对象集合（退轮对象不需评审），其 actor/invocation 与逐对象 `content_review.json` exact refs/digests 只由 `003-5.review` seal receipt 冻结，review seal 负责把 execution 级判断输入扇出为逐对象文件并补齐机械字段（schema/stage/executionId/objectRef/draft 与 assetRights 权利转录）。两者必须为不同 session/runId，可使用同一 model family；同一 execution 同时至多一个 reviewer 调用，不同 execution 的 author 与 reviewer 可由宿主原生并行；不建立对象级 actor projection。跨会话只认 receipts 与业务 result refs。团队按 `REQ-022` 分配命令职责：总监在用户一次性授权内确认方向与预算并唯一收官；每位作者就是本人 execution 的主会话，自领整批并执行获准的 init/acquire/author seal，独立 QA 自领整批并执行 review seal，不由总监代理全部机械命令。澄清后各角色沿共享任务版本在本人 scope 自主推进到终止条件（计数达标、候选前沿耗尽、连续零净增、用户中止或授权闸口），收官报告六段（目标 vs `pool-query` 计数、新增/复用、放弃清单、blocked execution 与首个 typed blocker、缺口、后继轮次的最小入口）且计数只从 `pool-query` 读；续跑交 `continue`/`plan-next`，不另立恢复轨或轮次台账。
- 单载体失败不得覆盖其它工作包，也不得阻止其它载体已合格对象入池。approved/rejected 可混合，短缺由 stage result artifact/typed issue 表达，不给通用 receipt 增加 `partial`；只要至少一个 approved 对象且无 stage-wide identity/integrity failure，stage 可 `pass` 并保留 shortfall，只有零 approved 或 stage-wide identity/integrity failure 才 `blocked`。
- `003-5.review` receipt 所绑定的 `content_review.json` 判定 approved 后，publish AI 对对象逐个调用 canonical 单对象事务（无 plan/apply 双跑）；不存在独立 review receipt、drain/process manager 或 execution 级 publish。canonical object package + append-only pool record 是 producer 内部 publish→release 的持久事实；release ref/digest、explicit cohort ref/digest、milestone、carrier counts、content-pool handoff refs/digests、producer baseline revision 与 producer contract digest 组成唯一 immutable producer handoff，handoff 以 canonical publish proof 为凭而不内嵌 execution receipt 链。运行身份不进入 consumer identity、eligibility、release cohort 或 App DTO。
- release selection 只接受显式 create-once pool record、完整 admission、随体来源/媒体与 canonical identity。逐对象失败只排除该对象，成功对象继续。content library 用于采集复用；最终对象包和 release 的完整消费不依赖原 execution 或 library 在场，release 仍只作分发物化。
- 每个 execution 的 `approvedQuota`、candidate count 与 workUnitCount 三值分离；宿主并发能力不进入三值、对象判据或仓内配置。
- article/image/video Post manifest 必须显式 `contentIdentity=work`；新增对象必须有稳定 `contentId`、递增 `version`、`sourceType=data`、`admission` 与 `status`，只有 `completed + passed + active` 可被 release 选择；对象级 `variantPurpose` 与 pool `usageScope=research|commercial` 不进入现役 schema/writer/reader。资产条目的 `usageScope=internal_reference|app_publish|editorial` 属于媒体用途，不是对象分类维，继续保留。

<a id="req-002"></a>
### REQ-002 默认单一发布消费链与权利只记录

- acquisition、semantic、review、canonical pool、发布和消费默认沿同一链路推进，不存在发布类别、运行类别或命名消费轨道，也不以常量标签替代这些维度。immutable release 与 producer handoff 不携带环境策略；环境差异只由环境 owner 的显式配置表达，切换环境不要求重新分类、构建内容或改写已封存字节。导入、激活、验证和回滚仍是独立生命周期动作，不是类别。媒体按公开交付 slice 物化，不存在按发布类别分流的私有交付。
- 每个实体头像/主页媒体、文章图、图片作品与视频资产都必须记录 `acquisitionStatus`、`rightsStatus=verified|unverified|restricted|unknown`、`commercialAuthorizationStatus`、`authorizationRequired`、`authorizationProof`、`license`、`termsUrl`、水印事实、`accessPolicy` 以及 `sourceUrl/platform/creator/capturedAt/contentSha256/rightsIssues`，以保留真实 rights hard facts。`rightsStatus` 由 acquire 按来源 license 机械派生：开放许可白名单（CC0/CC BY/CC BY-SA/PD）为 `verified`，其它可读 license 为 `unverified` 且 `rightsIssues` 写明 license 原文，license 不可读为 `unknown`。新对象与现役 schema/writer/reader 不再携带 `distributionDecision`、`publicationAdmission`、对象级 pool `usageScope=research|commercial` 或 `variantPurpose=commercial_variant`；不得以 `production`、`default` 或其它单值替代这些分类维。
- 权利只记录不阻断：acquire 不因 license 拒绝下载，publish 事务不因 `rightsStatus` 非 verified、`rightsIssues` 非空或缺少商用授权拒绝对象，release build 只按现役权利事实派生统计，不再读取旧分类值。未取得、生成素材、缺来源字段、不可播放视频与安全/隐私问题仍阻断。
- immutable release 必须冻结权利状态计数、精确 authorization-required asset IDs、四载体 accepted 计数、逐来源 assets funnel 和 `containsUnverifiedAssets`，供下游只读消费，不以公开展示倒推权利已验证。当前非商用开发验证阶段，四环境使用同一消费链并统一开放：四入口与公开媒体直链不因缺少授权记录而隐藏或拒绝，不新增运营审批或放行开关；既有认证、账号权限、内容安全、隐私、恶意文件与环境访问边界不因此取消。商用前的运营可见性治理由 [`OPEN-026`](#open-026) 承接，不是本阶段开发验收或 producer 完成的前置。
- 访问政策只记录不阻断：每条 ingest 来源行可申报 `accessPolicy=open|robots_disallowed|tos_restricted`（来源站点 robots 与服务条款对自动访问的态度，由 AI 读站点声明后申报），acquire 原样透传到该 source unit 的 `meta.json` 与资产行，publish 事务转录到 canonical 资产记录，release header 把非 `open` 的资产汇总为 `accessRestrictedAssetIds`；缺席即缺席，不补 `open`，任何取值不改变 admission、pool eligibility 或 cohort。
- 水印只记录不阻断，且只由看过像素的 AI 申报：每个媒体资产携带 `watermarkStatus=absent|present|unknown`、`watermarkKind=none|author_signature|platform_logo|stock_agency|other|unknown` 与可选 `watermarkNote`，采集与投影代码只搬运，缺席只能记 `unknown`、不得假定 `absent`；作者签名与平台/图库标识分开记，因为运营结论相反（前者通常可用且不得抹去，后者往往指向非自由来源或预览件）。release admission 与 header 把 `present` 的资产汇总为 `watermarkedAssetIds`，与 `authorizationRequiredAssetIds` 并列供运营逐条审核。不去水印、不给发布物烧制水印。
- 采集代码无法核实、只能按 producer 政策统一申明的资产级记录常量唯一声明位是 `content_distribution.policy.yaml`；`derivedModifications` 写实际发生的降采样、转码与抽帧，空数组只能表示确实无修改。Data、Service、App、Ops 对来源归属和逐图说明消费同一契约，不丢水印或派生修改事实、不以 title 代替 caption；删除旧风险接受字段与按发布类别推断授权的条件分支。
- 删除 `releaseClass`、`productLifecycleState`、`readinessPhase` 及其参数、枚举、默认值、指纹投影与专用 research 身份，范围覆盖 Data/Service/App/Ops，不以 Data-only 或单一 production 常量代替无类别。对象级 `distributionDecision`、`publicationAdmission`、pool `usageScope=research|commercial` 与 `variantPurpose=commercial_variant` 同步从新对象及现役 schema/writer/reader 退役；历史 canonical/release/review 原件不原地改写，只经 current cutover/new version 产生无旧分类的 current terminal。资产用途 `usageScope=internal_reference|app_publish|editorial` 保持独立合法语义。
- 包布局和重复旁车的转换只通过 [`canonical-content-identity-recovery`](../canonical-content-identity-recovery/spec.md) 的显式新版本或授权退役完成；保留原权利值、原 review 结论/对象摘要与历史 record，历史 receipt/release 原字节不改写且只离线审计。声明侧先于 codegen，当前正向读写不得双读双写或隐式接受旧 release 类别；格式转换不等于取得授权或重新审核。

<a id="req-003"></a>
### REQ-003 站点、实体与 creator 深挖的文章、图片和视频来源

- 实体口径是「用户感兴趣、愿意去的一切地方」：景区景点、秘境、网红打卡地、古镇、露营地、温泉、观景台、徒步节点、探险探秘地，不限 A 级评定，不设数量上限；实体类型只从 taxonomy `Entity/地点/*` 现有叶子中选取。homepage 主源必须是百科闭集成员：zh.wikipedia 或头条百科（`www.baike.com`，`sourceKind=toutiao_baike`），百度百科对非浏览器访问返回反爬挑战页，属技术性规避，不在闭集。实体发现以携程景点榜（热度分、点评数、「必打卡」标签、类型筛选）、zh.wikipedia 分层类目（5A/4A/3A、一级博物馆、历史文化名镇名村、国家级自然保护区、各省文保单位）与 AI 按地域给出的秘境名单为前沿，逐条以百科页存在与正文厚度核验。
- Article 必须拥有可成立的独立主题与读者价值。单实体百科条目仅改标题、措辞、章节顺序、叙述角度或 `publishAngle`，仍是同一语义对象，不得成立为第二篇独立文章；`publishAngle` 只能描述已经由不同问题、路线、时间窗口、受众任务或多来源论证证明独立的文章，不能制造新身份。主题条目页可作为主来源；事实参考可追加携程游记/攻略与景点榜、新闻旅游频道（新华网、中国新闻网）、政府与文旅厅/景区官网公告、磨房户外线路帖、zh.wikivoyage 以及页面为服务端渲染的其它公开旅行 UGC（马蜂窝按 `accessPolicy=robots_disallowed` 记录），全部按 `factual_reference_only` 登记——AI 只取事实、路线、费用与贴士并亲笔原创，不搬运来源表达，来源 URL 全部进入 `sourceUrls`。Article 分类必须覆盖 `摄影`；摄影文章与攻略、游记等使用同一 Post/Article 契约与质量准入，不创建第二套载体。
- Image 来源矩阵按「综合平台 → 垂类、创作者批量优先」运行：Wikimedia Commons（高产上传者 `allimages&aiuser` 全集与 Quality/Featured/Valued 类目）、Openverse API（Flickr CC 与 Commons 聚合，无 key）、Flickr 官方 API（有 key 时 `people.getPublicPhotos`/`photos.search` CC 筛选）、iNaturalist API（research-grade 且 CC 的自然观察，供自然保护区实体）、图虫（`/rest/tags/<标签>/posts` 与 `/rest/sites/<摄影师>/posts` 对合规 UA 直出 JSON，CDN 原图可下载；版权保留 → `unverified`）、Pinterest（用户/画板 RSS 与检索作发现，`i.pinimg.com/236x/<hash>` 改写为 `/originals/<hash>` 取原图；转载物、原始权利未知 → `unknown`）、头条百科标注 `CC BY-SA` 的自有图片、Unsplash/Pexels/Pixabay 官方 API（自有免费许可 → `unverified`）、archive.org/Europeana 等公有领域历史影像。每个资产的 `sourceUrl`、`creator`、原始资产 `directUrl`、取得方式与 `license`/`licenseUrl` 必须回到作品页、平台条款页或官方 API；500px 只作发现。
- Video 来源矩阵按「切题实景、可落实体、热度作排序、频道/UP 主批量」运行：Wikimedia Commons 视频类目与 `filetype:video` 全文检索、YouTube（无 key 时经 `yt-dlp` 以 `ytsearch` 发现、频道 `/videos` 批量并读取单条 `license`/互动指标，只下载 Creative Commons 条目；有 Data API v3 key 时以 `videoLicense=creativeCommon` 发现）、Bilibili（经 `yt-dlp` 拉 UP 主全集与逐条元数据；版权保留 → `unverified`）、Dailymotion API（`unverified`）、archive.org 与 Vimeo CC、Pexels/Pixabay 空镜。频道/上传者/UP 主全集是批量发现入口，入池仍逐条按实体落点、相关性与负面主题过滤；无法取得逐作品来源证据时只保留本次命中。
- 热点信号（携程热度/点评数、维基 pageviews、Flickr interestingness/faves、YouTube/Bilibili views/likes/comments、图虫 favorites/views、创作者粉丝数）与逐载体候选级质量筛选（百科正文厚度与结构化事实、游记长度与实用信息项数与时效、图片分辨率与主体切题与水印类型与长宽比、视频时长与清晰度与实景比例）只作候选排序与可重放的候选级放弃判据，不是 execution 内的门禁，也不落台账。来源层级 `sourceTier`（S1 精选/S2 高产可信创作者/S3 其它开放许可/S4 非白名单许可）与创作者层级 `creatorTier` 同样只记录进 `discoverySignals`，供评分校准回归，不作门。
- 访问合规只区分两类。**技术性规避**仍然禁止：所有站点、搜索和 creator shard 只允许公开直链、平台公开接口、RSS 或人工提供文件，不得规避登录墙、付费墙、验证码、访问控制、DRM 或反爬挑战页（小红书、抖音、快手、西瓜、知乎、微信公众号、穷游 503、去哪儿挑战页、美篇 SPA 等不进入任何自动化路径）。**robots 与服务条款限制只记录、不阻断入池**：新增站点前先读其 robots 与服务条款，并把结论作为每条来源行与每个资产的 `accessPolicy` 事实记录（闭集 `open|robots_disallowed|tos_restricted`，缺席不视为 `open`）；`Disallow: /` 或 ToS 限制自动访问的站点（Pinterest、i.pinimg.com、图虫、Bilibili、YouTube 下载、马蜂窝）照常入池，acquire 原样透传到 `meta.json` 与资产行，release header 汇总 `accessRestrictedAssetIds`。版权保留或权利未知的来源一律入池：`license` 逐字写作品页或平台条款原文（如「图虫用户协议（版权保留）」「Pinterest 服务条款（转载物，原始权利未知）」），脚本按白名单派生 `rightsStatus=unverified|unknown` 与 `authorizationRequired=true`，进入 header 的 `authorizationRequiredAssetIds` 与 `containsUnverifiedAssets`，caption 标注作者与来源链接；这些资产的当前开发期可见性按 `REQ-002` 统一开放，商用策略由 `OPEN-026` 跟踪，不由 Data 侧拒绝。来源侧出网由宿主 AI 点名 exact URL/查询后，以通用工具或 content-production Skill 内的单阶段机械工具执行；Skill `scripts/` 与 `carriers/<carrier>/sources/` 可负责有界请求、来源原文提取、下载与输入构造，不负责选择来源、相关性、评分、review、verdict、后继或恢复。Data `content/source`、`content/execution` 与 `core` 保持零来源网络。API key 只存在于本机环境而不进仓库；使用声明产品与联系方式的合规 User-Agent，同站串行、遵守 Crawl-delay、429/503 停止本次来源请求；多会话预算由宿主协调，不按会话数放大。单来源的 typed failure 只阻断自身，不阻断同 carrier 其他来源。
- 实体口径是「用户感兴趣、愿意去的一切地方」：景区景点、秘境、网红打卡地、古镇、露营地、温泉、观景台、徒步节点、探险探秘地，不限 A 级评定，不设数量上限；实体类型只从 taxonomy `Entity/地点/*` 现有叶子中选取。homepage 主源顺序为 Wikipedia（`zh.wikipedia.org`）第一、百度百科（`baike.baidu.com`）第二、头条百科（`www.baike.com`）第三，与既有 homepage source registry 的 authorityRank/probeOrder 一致。顺序不替代实体消歧和实际正文核验；前一来源缺条目、信息不足或无法合法取得时记录实际原因后采用下一来源。百度百科进入主源闭集不代表可自动抓取，遇登录/验证码/反爬挑战仍停止，来源页可见性与合法原文取得分别举证。实体发现以携程景点榜（热度分、点评数、「必打卡」标签、类型筛选）、zh.wikipedia 分层类目（5A/4A/3A、一级博物馆、历史文化名镇名村、国家级自然保护区、各省文保单位）与 AI 按地域给出的秘境名单为前沿，逐条以百科页存在与正文厚度核验。
- Article、image、video 均将专业类与综合类平台作为同等优先来源，不按分类或名单先后排名；百科和 Commons 仅作明确需要的补充，不因工具方便而默认采用。来源相关性、原作证据、合法取得及质量各自核验，不以网站多样性代替质量。
- Article 从读者问题出发，旅行/摄影专业平台与综合内容平台的实质正文同等优先，百科只补身份历史；不将百科年代、地址或面积拆句套标题当独立文章。事实参考可采用携程游记/攻略与景点榜、新闻旅游频道（新华网、中国新闻网）、政府与文旅厅/景区官网公告、磨房户外线路帖、zh.wikivoyage 以及页面为服务端渲染的其它公开旅行 UGC（马蜂窝按 `accessPolicy=robots_disallowed` 记录），全部按 `factual_reference_only` 登记——AI 只取事实、路线、费用与贴士并亲笔原创，不搬运来源表达，来源 URL 全部进入 `sourceUrls`。Article 分类必须覆盖 `摄影`；摄影文章与攻略、游记等使用同一 Post/Article 契约与质量准入，不创建第二套载体。
- Image 来源按专业/综合同等优先、摄影师/原生作品有界发现运行；图库可包含图虫、Pinterest、500px、Flickr、1x、摄影师原站、Unsplash/Pexels/Pixabay及商业图库，名单不代表已实现下载或授权。以下为历史工具能力说明，不是检索优先级：Wikimedia Commons（高产上传者 `allimages&aiuser` 全集与 Quality/Featured/Valued 类目）、Openverse API（Flickr CC 与 Commons 聚合，无 key）、Flickr 官方 API（有 key 时 `people.getPublicPhotos`/`photos.search` CC 筛选）、iNaturalist API（research-grade 且 CC 的自然观察，供自然保护区实体）、图虫（`/rest/tags/<标签>/posts` 与 `/rest/sites/<摄影师>/posts` 对合规 UA 直出 JSON，CDN 原图可下载；版权保留 → `unverified`）、Pinterest（用户/画板 RSS 与检索作发现，`i.pinimg.com/236x/<hash>` 改写为 `/originals/<hash>` 取原图；转载物、原始权利未知 → `unknown`）、头条百科标注 `CC BY-SA` 的自有图片、Unsplash/Pexels/Pixabay 官方 API（自有免费许可 → `unverified`）、archive.org/Europeana 等公有领域历史影像。每个资产的 `sourceUrl`、`creator`、原始资产 `directUrl`、取得方式与 `license`/`licenseUrl` 必须回到作品页、平台条款页或官方 API；500px 只作发现。旅行与自然生态摄影图片在拍摄地点未核实时允许显式无地点关联，不创建虚构地点或物种主页；地点身份字段要么完整声明并通过依赖校验，要么全部不声明，与摄影视频共用同一规则。
- Video 专业来源与综合平台同等优先，公开发现覆盖抖音、快手、TikTok、Facebook、腾讯视频、百度视频、YouTube、Bilibili、Vimeo、Dailymotion与专业素材库；逐站区分发现、详情和原件实际可用性。百度视频等聚合入口须追溯实际作品页，不把发现站、CDN或许可页算原作来源。按「切题实景、地点有据才关联、热度作排序、频道/UP 主有界发现」运行，以下历史能力说明不是优先级或自动取得保证：Wikimedia Commons 视频类目与 `filetype:video` 全文检索、YouTube（无 key 时经 `yt-dlp` 以 `ytsearch` 发现、频道 `/videos` 批量并读取单条 `license`/互动指标，只下载 Creative Commons 条目；有 Data API v3 key 时以 `videoLicense=creativeCommon` 发现）、Bilibili（经 `yt-dlp` 拉 UP 主全集与逐条元数据；版权保留 → `unverified`）、Dailymotion API（`unverified`）、archive.org 与 Vimeo CC、Pexels/Pixabay 空镜。频道/上传者/UP 主全集是批量发现入口，入池逐条按实际主体、相关性与负面主题过滤；无法取得逐作品来源证据时只保留本次命中。摄影视频使用既有摄影主题标签，拍摄地点未核实时允许显式无地点关联，不创建虚构地点或物种主页。地点身份字段要么完整声明并通过依赖校验，要么全部不声明；缺地点不改变视频的来源、媒体、独立审核与去重判据。homepage与article原身份要求保持不变；image与video共用可选地点规则。
- 视频与图片共用题材 `tagRefs`，不按载体复制目录。作者按可见主体、可核验场景或行为选择已有叶子：自然风光、动物行为、城市天际线或夜景等题材与图片相同。正式消费只使用已声明 `consumedBy` 的叶子；未声明采集与消费的 Format 内容角度只作创作提示。器材、光圈、快门、ISO、构图术语和制作流程不得作为大众兴趣 `tagRefs`。地点与季节只在有据时选择。不新增 Intent 轴、视频分类树、观赏或风景欣赏目录、展示入口 ID 表，也不手写固定排序权重。昆虫、两栖动物、淡水鱼等类型叶子仅在真实作品需要且现有定义无法覆盖时补入 Entity，不得借用爬行动物或海洋生物。人口画像不从画面或观看行为推断；标签存在不宣称推荐排序已生效。
- 文章复用同一批共享题材叶子，并用现有旅行主题、出行约束与 Format 内容角度叶子表达阅读问题；不新增地貌/营造细分、散文/随笔/访谈体裁、六个发现根或 Intent 轴。展示入口映射现有 tags。Data seal 解析定义文件；在线 `ValidateTagRefs` 仍只接受 active release 的无子节点叶子。人口画像不从文章推断。
- 热点信号（携程热度/点评数、维基 pageviews、Flickr interestingness/faves、YouTube/Bilibili views/likes/comments、图虫 favorites/views、创作者粉丝数）与逐载体候选级质量筛选（百科正文厚度与结构化事实、游记长度与实用信息项数与时效、图片分辨率与主体切题与水印类型与长宽比、视频时长与清晰度与实景比例）只作候选排序与可重放的候选级放弃判据，不是 execution 内的门禁，也不落台账。既有来源层级 `sourceTier` 与创作者层级 `creatorTier` 只作为实际取得的历史指标记录进 `discoverySignals`，不从平台类型、开放许可或工具章节顺序生成优先级，不用层级覆盖专业/综合同等优先，也不作准入门。
- 访问合规只区分两类。**技术性规避**仍然禁止：所有站点、搜索和 creator shard 只允许公开直链、平台公开接口、RSS 或人工提供文件，不得规避登录墙、付费墙、验证码、访问控制、DRM 或反爬挑战页（包括小红书、抖音、快手、西瓜、知乎、微信公众号等遇到的挑战；穷游 503、去哪儿挑战页、美篇 SPA 等实际失败同样按边界停止）。这些平台的公开检索线索可登记，不代表详情或原件已经取得，不能从公开搜索摘要绕过受限原页。**robots 与服务条款限制只记录、不阻断入池**：新增站点前先读其 robots 与服务条款，并把结论作为每条来源行与每个资产的 `accessPolicy` 事实记录（闭集 `open|robots_disallowed|tos_restricted`，缺席不视为 `open`）；`Disallow: /` 或 ToS 限制自动访问的站点（Pinterest、i.pinimg.com、图虫、Bilibili、YouTube 下载、马蜂窝）照常入池，acquire 原样透传到 `meta.json` 与资产行，release header 汇总 `accessRestrictedAssetIds`。版权保留或权利未知的来源一律入池：`license` 逐字写作品页或平台条款原文（如「图虫用户协议（版权保留）」「Pinterest 服务条款（转载物，原始权利未知）」），脚本按白名单派生 `rightsStatus=unverified|unknown` 与 `authorizationRequired=true`，进入 header 的 `authorizationRequiredAssetIds` 与 `containsUnverifiedAssets`，caption 标注作者与来源链接；这些资产的当前开发期可见性按 `REQ-002` 统一开放，商用策略由 `OPEN-026` 跟踪，不由 Data 侧拒绝。来源侧出网由宿主 AI 点名 exact URL/查询后，以通用工具或 content-production Skill 内的单阶段机械工具执行；Skill `scripts/` 与 `carriers/<carrier>/sources/` 可负责有界请求、来源原文提取、下载与输入构造，不负责选择来源、相关性、评分、review、verdict、后继或恢复。Data `content/source`、`content/execution` 与 `core` 保持零来源网络。API key 只存在于本机环境而不进仓库；使用声明产品与联系方式的合规 User-Agent，同站串行、遵守 Crawl-delay、429/503 停止本次来源请求；多会话预算由宿主协调，不按会话数放大。单来源的 typed failure 只阻断自身，不阻断同 carrier 其他来源。
- CLI 与 receipt 对每个 `displayName/provider` 输出 `planned/discovered/downloaded/accepted/rejectedAssetCount` 及 verified/unverified/restricted/unknown 计数；下载成功不得把 rights 状态升级为 verified。
- 文章有图即 illustrated：只要求至少一张可追溯授权来源的图片并把首图派生为唯一封面，配图张数不设下限，一张图与多张图同样合法；无图即 text_only。封面与正文图可来自不同的可追溯授权来源。illustrated/text-only rate 只作为供给统计，不参与对象准入或规模晋级。
- 视频候选保留 play/like/comment/share/favorite 的真实观测与观测时间，并只在同平台、同主题、同时间桶内按 percentile 排序。缺失项保持缺失并标明不可参与热度排序的原因，不得补零或生成虚假排名。
- ranking-ineligible 视频可以进入 release；热度信号完整度和 percentile 只作为推荐与供给统计。只有公开可取得、可解码、可播放、无 DRM、未绕过访问控制且通过安全/相关性门的真实视频文件可进入 release。
- 视频来源字节超过载体预算或容器/编码不在发布闭集（`video/mp4|video/webm`）时，ingest 在下载截面用 ffmpeg 转码为 H.264 mp4 派生体（目标 720p、约 16 MiB，硬上限为载体预算），按派生体重新登记 sha256/mime/尺寸/时长，写 `derivativeBinding` 保留源体摘要，poster 从派生体抽帧；每档都装不进才判否。四载体的来源发现与选材由 AI 按上述来源矩阵决定，Skill 工具只展开显式查询并保留来源证据；发现快照只放 `.qwq_output/data/local/workspace/**`。快照可重新取得不代表外部网页或 AI 判断能逐字节复现，已冻结执行输入不得被其他轮次覆盖。
- homepage 与 article 的百科来源必须同时从可见正文与结构化信息区取证不可变结构化事实。Wikipedia 证据必须冻结 exact page/revision identity，并取得该同一 revision 的 wikitext 与 Parsoid HTML；两者的 revision 不一致、任一方漂移或只能取得 latest 时 fail closed，不得把不同 revision 拼成一份来源。wikitext 保留模板、表格与链接的源语义，Parsoid HTML 提供与该 revision 对齐的结构化映射输入；二者共同映射到同一 semantic document/source revision，不互相冒充。其它百科同样冻结其可提供的 exact revision/bytes。`source.md` 由 AI 以通用工具把来源正文与信息区原文落盘（Wikipedia exact wikitext + Parsoid HTML、头条百科页内结构化 JSON 展平、游记页 HTML→text），再由 AI 亲笔附上「信息区取证」段；不要求 AI 逐字转写正文。信息区的字段名与取值只在语义一致时采信，字段名指向的受治理字段与解析出的取值类型不一致时该候选事实作废，不落入其它字段。

- 原生多图作品以来源命名空间与原生作品身份分组，一个作品对应一个 image target，选中的资产保留来源顺序与逐资产权利；部分选择必须显式，不按图片数量拆成多个作品。仅同作者或同日期不足以合并跨页面作品。author 的逐资产说明按 Data author schema 表达，投影到既有 `assets[].caption`，不得改变总 caption、消费字段或已发布字节；同名资产必须能在同一对象内唯一投影。
- homepage 是对已获许可百科来源的 faithful adaptation，不是「移动端模板、有据整理」或自由改写：必须保留主源的实体范围、关键事实、限定条件、归因、信息层级与可验证语义，只允许为统一 semantic document 做必要的结构映射、去除站点 chrome、可访问布局与有据补充。维基优先作主源，头条百科只补同实体缺失事实；无维基可用另一闭集百科。任何删改若改变事实含义、把不确定写成确定、合并冲突来源或脱离许可要求，必须 typed 判否或进入人工 disposition。主源须核对名称、类型与行政区；空章节、冲突或无时效依据的票价不补写。多百科产物显式声明本对象已取得的主源，source binding、唯一 manifest 与正文归属使用同一选择，不依赖 source unit 排序；视口、长度与评分只作布局/advisory，不生成端专属正文。
- homepage 按移动端模板有据整理，主源按 Wikipedia、百度百科、头条百科的顺序选择，缺失事实可用已取得的同实体来源交叉核实，不能以历史取证失败排除一个合规主源，也不绕过实际访问限制。主源须核对名称、类型与行政区；空章节、冲突或无时效依据的票价不补写。多百科产物显式声明本对象已取得的主源，source catalog、实体头与正文归属使用同一选择，不依赖 source unit 排序；模板、长度与评分只作 advisory。

<a id="req-006"></a>
### REQ-006 零仓内编排与 legacy 硬删除

- 旧 managed SDK/provider、agent/controller/queue/campaign/recovery、runner/fleet、语义 lane claim、stage-gate/业务完成 registry、semantic prepare/record wrapper、自动恢复与 execution-state reducer 必须物理删除；禁止 shim、dual-read、retired-path fallback 或 sequence-017 兼容。`REQ-022` 的最小本地 SQLite 协作事实库只做具名分片 CAS 占用、资源预留与释放审计，不在本禁令中；一旦它解释 receipt 选择后继、签发业务完成或自动恢复，即越界为被禁控制面；按 `REQ-022` 对归属/容量所需正式证据作机械核验不产生第二业务 authority。
- 删除是本 contract-reset 的已批准架构决定，不以 `GWT-034`、`OPEN-006`、stable-production proof、旧 proof、任何 App/API UAT 或 terminal retry evidence 为前置授权。
- 宿主并发、模型选择、截止与会话重启是宿主原生能力，只能作为外部诊断，不进入仓库业务对象、producer handoff 或下游 promotion。
- 每个 stage 的 verdict、typed issues 与 result refs 由宿主 AI 显式提交；代码只执行冻结输入上的 create-once seal 与窄 IO/verifier，不建立第二终态 writer。
- 单阶段批量不是编排：`task init` 一次建一轮多个 execution、`task acquire` 一次 ingest 一个 execution 的多个 target、`task seal --stage 5.review` 从一份 execution 级判断输入扇出到逐对象文件，都只在一个阶段内对显式输入做无状态、无恢复、无跨阶段推进的展开；逐 target 结果独立报告，单 target 失败不影响同批其余。凡跨阶段推进、读取 receipt 决定下一步、重试或恢复，都属被禁的 runner/controller。

<a id="req-017"></a>
### REQ-017 工具与宿主 AI 的职责边界只按可伪造性划分

- 归工具的判据只有一条：同样字节换任何执行者必须得到同样结果，且结果不可伪造。闭集为：从字节算 sha256 并按来源声明的 sha1 交叉校验、mime/尺寸/时长探测、按载体预算降采样与转码、抽 poster、content library CAS 与硬链接、create-once source unit 与 receipt、schema 校验、单对象原子事务、canonical 序列化与 merkle、cohort 规范化与 handoff、`pool-query` 只读口径、随体闭包比对。
- 归宿主 AI 的判据只有一条：需要理解语义或看见内容才能得出结论。闭集为：与用户澄清约束、制定与推进规划、并行派发子 Agent、检索与选题、点名来源与相关性、读来源页取权利事实、下载字节、看图判水印与相关性、写 `source.md` 与四类 carrier 产物、评审判断、cohort 与 milestone。这些语义判断与流程推进以宿主原生能力（检索、读页、终端、看图、子 Agent、规划）和既有通用 Skill（`continue`/`plan-next`/`review`/`commit`）完成，不在仓内再实现一遍。下载、提取原文、构造输入等机械部分可由宿主调用 Skill 内工具执行；工具不得选择 approved 对象、伪造 actor 或自动调用下一阶段。
- 来源可达与权利事实的取证方式随之改变：「来源 `https://` 可检索」由 AI 申报的 `sourceUrl`/`directUrl` 形状与来源声明的 `sha1` 对本地字节的交叉校验共同成立，不再由脚本出网验证；license 原文与 `licenseUrl` 必须逐字抄自来源文件页，`rightsStatus` 仍由「申报 license 字符串 → 开放许可白名单」纯函数派生，AI 不直接给出 `rightsStatus`。这是取证方式的显式降级：可审计性从「机器取自 API」变为「AI 申报 + 本地字节自证 + 人可按 `sourceUrl` 复核」。
- 过程状态不建第二语义真相源：「已存在什么」只读 `release pool-query`，「在飞 execution 到哪一步」只读 `_shared/receipts/`，业务完成只认 receipts/resultRefs/publish proof/handoff；候选级放弃靠可重放判据（条目缺失、消歧义、正文过薄、水印类型、相关性）在再次选题时自然重现，不落台账；人工裁决过的例外写入 `OPEN-###`。`REQ-022` 允许的 SQLite 只记录协作占用硬事实，不能回答 execution 到哪一步或对象是否完成。

<a id="req-018"></a>
### REQ-018 质量评分与热度信号只记录不门禁

- 每个载体拥有一套由 Skill reference 声明的多维质量评分（整数 1–5，维度名为闭集，各载体六维），由 reviewer 会话在评审时逐对象申报为 `content_review.json` 的可选 `qualityScores{维度: 分}` 与可选 `qualityNotes`；`task seal --stage 5.review` 只做 schema 校验与逐对象透传，publish 事务原样写入 canonical 对象包。评分缺席合法，缺席不得由脚本补零或推断。
- 来源热度信号（携程热度/点评数、维基 pageviews、Flickr interestingness/faves、YouTube viewCount 等）由 AI 在 ingest 清单的来源行以可选 `discoverySignals{信号名: 数值}` 申报，acquire 只透传到该 source unit 的 `meta.json`。
- 两类记录都不参与任何判否：不改变 `decision`、不进入 publish/release admission、不进入 cohort 选择、不由脚本聚合成第二状态源；reject 判据包括事实论断缺少必要证据或与已取得证据矛盾、安全/隐私、素材不相关或不可播放。可验证的地点、主体、人数、音轨等文案与媒体矛盾须明确引用原句及相反证据，交作者纠正，不能仅以低分/advisory 放行；一般审美、片长、风格及权利状态仍按既有记录边界处理，不增设分数硬门。必需的来源/当前草稿或媒体观察未完成时报告 blocked，不以省略某项评分代替审核完成；这些判断由真实独立 QA 作出，不交脚本分类。
- 评分体系是草案：横向校准由 AI 对已绑定独立内容仓中的审核原件只读抽样完成，修订只发生在 Skill reference 的维度锚点与候选级筛选阈值，不改门禁与 schema 闭集之外的字段；仓位置与布局不参与评分事实。

<a id="req-007"></a>
### REQ-007 confirmed demand 沿 producer 六步推进到 immutable handoff

- producer 完整路径固定为 `confirmed carrier demand -> identity-only candidate-backed task init -> acquire -> author -> review（三份 seal receipt）-> 逐对象 publish -> release finalize（explicit cohort immutable release + handoff）-> END`；旧控制面与任何消费阶段不在现役闭包。
- `task init` 的 deterministic 三文件原子初始化已实现并由 local contract 锁定；真实 confirmed demand 的宿主消费证据由 [`work-request-compilation` OPEN-001](../work-request-compilation/spec.md#open-001) 跟踪。每一步只消费前一步 immutable ref/digest，失败不得跳阶或用旧 receipt 冒充当前完成。
- 正常职责链为作者完整生产与自检后整批直交独立 QA，QA 判断后直交总监按原授权发布；退回直接通知作者。自检不增加预审阶段，总监不内容复审，finalize 只在正式交付点执行。已知阻塞直接由相应责任人处理，原任务负责人跟进、总监兜底无人承接与跨角色冲突；仅在既有 report/checkpoint 留阻塞事实、解阻责任人、下一动作与下次检查，不新增审批岗、报表或调度状态。
- producer release/handoff 不包含 UAT sample authority、environment consumer facts、import/activate/readback、App/API UAT、EAF、promotion 或 rollback。下游可只读 handoff 独立消费，但其成功、失败或未运行均不得生成 producer receipt、回写 execution 或改变 producer END。

<a id="req-008"></a>
### REQ-008 发布只消费显式 cohort

- release 只消费调用方显式提供且经 schema 验证的 exact cohort；不得扫描全池后隐式选择“全部可发布对象”。M1/M10/M100/M1000/M10000/M100000 按 `cumulative_unique_finalized_objects` 累计达标，每级都必须形成自己的 full explicit cohort、immutable release 与 producer handoff。M100000 的 `milestoneTargets` 固定为 homepage/article/image/video 各 `100000`，不得沿用较低视频底线或以媒体张数替代 video/image 唯一作品数。达标判据是 cohort 四载体计数**不低于**里程碑目标，release header 分别冻结实际 `counts` 与 `milestoneTargets`；cohort 的 `objectRefs` 排序、canonical 字节化与 `expectedCarrierCounts` 派生由 finalize 机械完成，不要求调用方手工对齐。
- build 在写入前逐对象重验 canonical identity、review、rights 与随体 source/media closure；任一对象失败只形成 typed exclusion，不改写 cohort 或其它对象，不隐式修复包或依赖原 content library。
- release identity、cohort digest 与 payload 一次冻结并 create-once；重放只接受逐字节相同结果，任何漂移 fail closed。更高级别可复用 canonical 对象及其首次 producer execution/publish proof，handoff 以 canonical publish proof 为凭，不伪造新 receipts；重复 identity 不增加累计对象数。
- 里程碑 cohort 与 producer handoff 继续是仅有的两份 terminal 事实，由 finalize create-or-same 保存到独立内容仓的 release 边界；不另建 catalog、状态账本或副 handoff。现有 immutable bundle、旧 terminal 原件与运行审计不因迁仓删除或改写；可重建承诺必须覆盖固定时间、cohort 与 exact build 输入，并由实际重建验证支持。
- handoff 仅新增内容仓 `repositoryId`，继续绑定工程 baseline/实际契约摘要，并复用既有 release 与逐对象 query digests 固定所选对象及内容快照；不另加 objectPath 表、`contentRevision` 或 `layoutVersion`，不增加内容提交或双提交门槛。
- canonical 包按稳定资产身份绑定相对随体媒体与摘要；环境交付键只在 release 物化时派生，运行 URL 由既有 media endpoint 生成，不把本地路径或来源直链交给 App。包内摘要不包含外层地域/分区定位，release 复用既有引用定位；改变包字节须新版本/摘要，纯移动不重做 review。

<a id="req-009"></a>
### REQ-009 最终媒体随作品交付，内容库只负责采集复用

- 四载体最终包携带全部实际交付图片、视频、poster 与真实存在的字幕，并在唯一 manifest 声明 exact 相对引用；不为迁目录重新编码、不伪造字幕、不跨包 symlink。普通完整复制后可校验与消费，不要求原 execution/library。
- content library 可去重采集字节，视频/poster 稳定资产引用继续按已有唯一性契约复用；物理拷贝不是新资产身份。对象、来源与独立 review 仍由同一事务核验，不因复用字节签发新作品资格。
- 发布包媒体、独立 golden media 备份与 release 分发物化职责分离。普通 Git 不跟踪媒体，硬链接及忽略规则不是独立备份；已被任一保留作品/release 引用的摘要不得清理。同卷双副本与异卷/远端耐久性的证明分开报告。
- publish、selection 与 build 对 exact 包中缺失媒体、摘要/大小不符或引用逃逸 fail closed；verify 与消费不隐式下载、补库或借旧 release 代偿。恢复是显式操作，优先验证独立副本，不承诺来源站能复原同一派生字节。
- 部署先校验所选摘要与实际交付对象一致，再由既有环境流程激活；媒体内容改变生成新交付键，旧字节按现有 release 保留规则保护，不原地覆写同 URL。干净元数据检出不是完整包、更不是环境可访问或耐久性证据。

<a id="req-010"></a>
### REQ-010 homepage 与三个 post 载体共享同一份准入判据

- homepage 走 receipt 协议 publish 的同一条链：`003-5.review` seal receipt pass、布局可发布、对象唯一 `content_review.json` 为 approved，之后经实体事务进入 canonical `entities/`。禁止为 homepage 建立第二套准入判据或 attestation。
- homepage 的逻辑身份从 init 起显式冻结，不是 `domain/type/name` 等磁盘路径；既有 entityRef 作为 opaque 身份保留。实体和 post 都可在同名组内分配发布条目，目录条目号不表示版本。目标必须唯一绑定冻结身份，不能按名称取首项；实体分类或身份冲突返回结构化失败而非静默去重。
- article 可在 homepage 完成前独立生产/入池，但新 release 中显式内部实体依赖必须由 exact cohort 闭合；文本中无系统实体的外部名称保持普通文字，不捏造引用。运行实体下线不改变已发布文章资格或历史 release。
- homepage 的结构化实体事实并入唯一 manifest，结构及百科主源判据只由 `quwoquan_data/schema/publish/entity.schema.json` 与对象 manifest 契约拥有，不保留第二实体头。当前地点对象的主地域必须来自已核实行政区标签，缺失或冲突在写盘前 fail closed，证实只到市/省则保留真实层级。
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
- 「资产必须装进其载体的发布预算」是下载决策截面的不变量，并在 `1.download` 一次冻结。载体由来源单元自己声明的 carrier 决定；carrier 缺席或落在闭集之外时该截面判否，不替它挑一个载体，因而也不替它挑一个预算。
- 超预算候选在该截面就地收敛：先按已声明交付档自宽到窄降采样，取第一个装进预算的档并按新字节身份重登记摘要与内容类型；每档都装不进、或派生体反而跌破像素门时给出 `DATA.MEDIA.ASSET_OVER_BUDGET` 并点名该资产。禁止把判否推迟到 publish——落在放行值与预算之间的资产会走完 `2.quality`→`5.review` 全部创作与评审成本，且一个超尺寸 homepage hero 会连带让引用该实体的已完成 article 因引用闭包不成立被 `DATA.POOL.REFERENCE_MISSING` 长期排除。
- 该不变量与 provider 无关：`pageImageRenditionWidth` 的服务端缩略图偏好只覆盖 `upload.wikimedia.org` 的 commons 非 thumb 路径，`pinterest`、`tuchong`、`openverse` 都没有对应路径，因此它是尽力而为的优选而不是预算不变量的实现手段。
- `sourceAssetMaxBytes` 是单次抓取的传输上限而不是准入判据：它只回答「愿意为一个候选花多少带宽」。源体允许大于对象预算，因为降采样需要先拿到源体。
- 资产的像素几何按交付端呈现的方向记录。EXIF Orientation 声明 90° 旋转时存储栅格的宽高与显示宽高互换，只读存储栅格会把一张横向全景图记成极端竖图，并使相关性判定、封面候选、有效交付宽度与字节预算全部按转置后的几何得出结论。重编码会丢弃 EXIF，因此派生体必须先旋转再编码。
- 源栅格愿意解码的像素上限是同一文件的 `maxSourcePixels`，且不得低于 `maxPublishableImagePixels`。图像解码库自带的解压炸弹阈值必须对齐到该值，否则全景接片会在策略允许范围内被库先行判否，形成策略文件里看不见的第二阈值；超过 `maxSourcePixels` 的源以 typed `pixel_limit_exceeded` 判否而不是运行时告警。派生对 JPEG 源在解码前按目标交付宽度请求不小于目标的最小缩放档（`draft`），全幅栅格不进内存，其后只做收尾缩放；非 JPEG 编码没有这条捷径，仍在 `maxSourcePixels` 内整幅解码。像素数超过 `maxPublishableImagePixels` 但字节在预算内的源同样在下载截面降采样，入池存储体的像素永不超过发布上限。全景图仍按宽度派生交付档并如实记录 `width/height`，极端长宽比在消费端如何呈现归 App owner。

<a id="req-013"></a>
### REQ-013 运营读模型只作 projection/query view

> 下列 `REQ-013` 至 `REQ-016` 保留为既有下游消费规格背景，由 Runtime/Service/App/Ops owner 实现与验收；它们不进入 content-production 六步、producer release/handoff 或 producer 完成条件。
早期消费场景中的 `Data-owned ReleaseUatSamplePlan` 仅表示下游 Data release consumer 契约的历史命名，不表示由 content-production producer 创建、携带或验收；该 sample plan 及其 UAT/EAF facts 均 downstream-owned。

- `ContentProductionTaskView`、`ContentItemVersionView`、`EnvironmentReleaseOrderView`、`ReviewDecisionTimeline`、`ReleaseSelectionView` 与 `TargetAcceptanceView` 均为无写权限的 projection/query view，不拥有 command、Repository、checkpoint、独立 ledger 或生命周期终态。
- `ContentProductionTaskView` 只投影现役 carrier demand/execution manifest/stage receipts；旧 WorkRequest schema 不构成依赖。`ContentItemVersionView` 只投影 canonical object transaction/pool record。`ReviewDecisionTimeline` 只投影上述 owner 已绑定的 review facts。`ReleaseSelectionView` 只投影 `ContentRelease` 及其 selection evidence。`TargetAcceptanceView` 只投影 Alpha/Beta/Gamma operation/EAF v2 与 Prod activation/hosted facts。`EnvironmentReleaseOrderView` 只读 Alpha/Beta/Gamma EAF v2 和 Prod `ReleaseTagAdmissionFact`/`ProdActivationAdmissionFact`/hosted lifecycle facts并排序，不推导、补写或推进任何环境状态。
- projection 缺失、延迟或重建不得改变 owner facts；query 发现 ref/digest 漂移时返回 typed blocked，不以本地 checkpoint、缓存行或最后一次成功值修复 owner。

<a id="req-014"></a>
### REQ-014 App 验收是 entry surface × carrier 二维矩阵且 raw 结果单写

- App 验收矩阵的 entry surface 轴固定为 `feed|search|recommendation|direct_or_object_route`，carrier 轴固定为 `homepage|article|image|video`。每个 cell 必须显式声明 `required|not_applicable`，并在 required 时给出 repo-relative 验收锚点引用与 runner；两轴不得合并或统称“四 surface”。
- raw canonical `ReadinessCaseResult` 是唯一 UAT 结果事实，逐 cell 绑定 target、release identity、runner、输入与真实观察。允许建立只读完整性 projection 检查 required cell 是否齐全，但该 projection 不得生成 verdict、promotion、write-back 或独立 UAT ledger。
- Environment Ops scheduler 签发的 `EnvironmentAcceptanceFact` v2 以 `caseResultRefs` 直接绑定全部 required raw result refs 与 exact-byte digests，并验证其 environment、candidate 与 canonical profile 一致；缺失、重复、跨 candidate、digest 漂移或 `not_applicable` 无验收锚点引用均 fail closed，不由 counts 或完整性 projection 代填。Data-owned sample plan 与 CaseResult 可保留 release identity，但 EAF v2 自身不复制 Data release identity或 consumer binding。

<a id="req-015"></a>
### REQ-015 入口面缺席、治理与回滚语义互不代偿

- 四个 entry surfaces 读取同一 active release identity。对象被 canonical owner 明确删除时，集合入口排除该对象，`direct_or_object_route` 才返回 canonical deleted 语义；空结果或环境没有 active release 必须保持 `no_active_release`/empty 语义，不得伪装成 deleted。
- `offline` 表示目标环境/operation 暂不可消费，保留 release/object identity 与 canonical recovery action，不得改写成 deleted 或 `no_active_release`。`retired` 是 `ContentRelease` 治理态，不直接成为 App wire；retire 后若没有 active pointer，入口面只呈现 `no_active_release`。
- rollback 或 replay 成功后，feed、search、recommendation、direct/object route 必须全部回到同一个 previous release identity；任一入口仍读失败 candidate、混合新旧 identity 或仅 counts 相等均为 `rollback_failed`，不得由缓存 projection 掩盖。

<a id="req-016"></a>
### REQ-016 媒体按显式交付契约消费并有界恢复

- 默认 release 的媒体按 [`REQ-002`](#req-002) 公开交付，不要求专属身份或命名消费轨道。每条引用携带 canonical 媒体契约的稳定资产身份与明确交付方式；缺失或错绑保持 typed failure，禁止按 URL、CAS key、环境名或字段缺席推断 public。普通原图授权与通用受权媒体能力仍由原 owner 契约约束，不构成另一内容 release 类别。
- progressive private MP4 通过已校验短签 URL 播放；边缘对每个 Range 请求重新验签。首次 401/403 只允许强制换签一次并从已确认播放位置恢复，二次失败停在 typed terminal，不循环、不回退公开 URL。
- private HLS 当前为 unsupported typed terminal 并 fail closed；它不得进入 progressive MP4 fallback，也不得阻断 progressive MP4 的 fresh UAT。其设计、实现与独立 UAT 由 [`OPEN-017`](#open-017) 承接。
- 新 Data projection 从唯一 release manifest 绑定公开 slice；旧发布类别、Data 专属私有 CAS 交付字段或缺失绑定均 fail closed，不保留 previous-version adapter。
- 视频时长、封面、资产顺序、摘要与来源说明从 importer 到 App 保持一致；Range 播放的真实验证独立于生产端测试，不以可探测文件替代可播放证据。
- 发布与消费链的 research 专属 feed、readback、role/whitelist/session/attestation 与 isolation 分支在 Data/Service/App/Ops 全部退役；普通 JWT/OTP、跨业务共享的私有媒体、原图 view/save 配额及 signed_grant 安全能力不在退役范围。

<a id="req-023"></a>
### REQ-023 核心可用性诊断复用 Data ship consumer

- `ship verify --verification-purpose core-diagnostic` 只消费同一 immutable release、prepared apply、completed activate、四 owner candidate/fenced readback 与 exact runtime candidate data-plane binding；不得省略、猜测或重建其中任一前驱。它是 Gamma 与 Prod prevalidate 的不可提升诊断，不写 `release-readiness.json`、EAF、promotion、lifecycle 或其它 readiness fact。
- feature 选择只允许 `identity|feed-detail|search-recommendation|image-video-range|post-write-readback|chat-write-readback`。Data 复用当前 post/homepage/media/search/recommendation consumer verifier，只拥有前四项；后两项明确记为 `not_executed` 并交 Ops/App 汇总，不在 Data 内创建账号或业务写操作。未选择项也逐项记为 `not_executed`；任一由 Data 拥有且被选择的 required case 缺失或失败，诊断失败。
- 诊断报告恒为 `nonPromotable=true`、`releaseEligibility=GATE_BLOCK`、`readinessWritten=false`，逐项只允许 `passed|failed|not_executed`。不要求 M10、前一环境 readiness、lifecycle Exit 或 premium stream，除非调用方显式选择其对应现役正式能力；默认 `ship verify` 行为完全不变，正式 readiness 对 M10、Beta 前驱、Exit 与 premium 的既有拒绝不得弱化。
- Prod 只允许 `deployment-instance=prevalidate`、`data-mode=isolated` 且 runtime candidate target 为 `prod-hosted`；正式 Prod deployment instance、external/production binding 或无法证明隔离的输入在 consumer 请求前拒绝。Gamma 仍消费当前 `gamma-local` exact candidate binding。

<a id="req-019"></a>
### REQ-019 独立发布仓按真实地域与同名组管理

- 内容仓与源码工作树平级且身份显式绑定，错误或缺失根必须阻断，绝不 fallback。它不是源码 clone/worktree、submodule 或 symlink；工程 worktree 发现按仓身份区分，不按宽泛目录名忽略。
- 地域实体依领域、已核实主行政链、现有主类型、分区、规范名称、组内条目定位；默认国家/省/市/区县，但缺区县、直辖市、省直管县与境外均服从真实标签层级，不补未知层或凭坐标猜归属。跨区域实体只有一个主落点，其他地域保持可查询引用。
- 地域适用性显式声明，不以领域不为地点或地域字段是否非空猜测。当前仅生产既有地点类型，非地域领域只预留已有领域/主类型结构，不实现非地点 producer。posts 只按载体/主分类/分区/名称/条目管理，不再复制地域树。
- 每个非空分类从第一个分区开始；仅以条目数和随体逻辑字节分配。已有同名组留原分区、不可拆；新组选容得下的最低归一化负载分区，平分按编号，没有合适分区才新开。超大组报告容量例外，不自动迁移或跨地域均衡；inventory 可重建，不新增分区 authority 或后台任务。
- 同名范围是同一领域/行政归属/主类型，posts 为同载体/主分类；名称遵循统一 Unicode 与空白规范。大小写等价、非法字符、穿越与长度碰撞显式拒绝，不静默合并。组内条目为不复用的正整数、允许空洞，与稳定身份及内容版本分离。

<a id="req-020"></a>
### REQ-020 单一 manifest 与真实审计原件构成最小对象包

- manifest 是对象身份、版本、分类、标题/caption、实体事实、正文和有序媒体/业务依赖的唯一结构化发布事实；homepage/article 另有唯一最终正文，image/video 不制造伪正文或携带脚本草稿。字段与文件语法由 canonical schema 拥有，不为整齐重命名既有业务 ID。
- 采用来源的 URL、原作者、时间、许可/授权/访问事实由包内 `sources/<unit>/source.json` 单写，必要证据在同一来源单元内聚；相同来源可在不同作品保留少量独立审计元数据，不建全球 source resolver。只保留真实、必要且被引用的证据，原始大下载非默认成品，生成的 manifest 副本不是第三方授权证明。
- 删除重复 asset/creator/tag 引用旁车及独立 source catalog/rights 投影，真实原件转入随体来源；消费者只从 manifest/source 生成公共 attribution，不再手工维护第二份事实。
- 四载体采用同一版本化原作记录，沿候选、取得与随体来源保留原生作品身份、原页面与已核实原作地址、实际响应/摘录/取得凭据、取得范围与有序采用关系。响应完整不等于原作完整，未知或局部取得须显式声明；未保存原字节不得只凭摘要声称可恢复。
- 原作记录只保存内容区域的媒体使用项与证据定位，不复制DOM或全文AST。原生组图成员保留相对原序，封面、正文配图、视频poster及参考链接按用途引用；同一资产多处使用不重复计作品。图标、广告、推荐图等未采用媒体不进入成品或分发闭包；内容主题确实涉及标志时可由宿主有据采用，不按尺寸/扩展名推断。
- 原始来源、审核成品和目标渲染投影分别绑定，不要求跨阶段署名对象全等。新渲染版本由下游分发构建从固定成品生成，不能反写来源、媒体或review；目标不支持的必要媒体关系明确阻断该投影，不静默丢图、改序或夹带未选图片。来源变化只更新取得/识别适配，普通消费不回原站解析。
- 独立 reviewer 的原结论与原始审核对象摘要保留，迁移只追加原件 binding，不把旧审核改成新审核。追加式 pool records 保留入池/退役事实并绑定包与 review 摘要，不复制完整 manifest/source；审核结论与入池状态不能相互替代。
- 单对象 publish 在同一内容仓共享锁下校验临时包并原子可见；所有源码工作树对共同根使用同一锁，不随各自 output root 漂移。仓 metadata 除 schema 标识外只承载 `repositoryId` 与 `layoutVersion`，不保存 `producerContractDigest`、绝对路径、统计、active release 或凭据；实际工程契约摘要仅由 handoff 绑定。

<a id="req-021"></a>
### REQ-021 稳定实体导航与媒体失败只做局部降级

> 本要求只冻结内容与引用边界；具体 query/wire 与 App 恢复动作由原 Service/App owner 拥有，不纳入 producer END。

- 实体引用使用稳定身份和名称快照，不用存储路径、分区或当前标题跳转。正文渲染不逐实体请求或 HEAD，用户点击时才由已有目标页执行权限/下线判断；普通实体下线不级联删除作品、原文或已采用媒体，不重写历史 release。
- 文章导入复用 Entity 的 exact 主页映射生成既有 mention 投影，不新增 ID 哈希规则；缺映射保留普通文字而非无动作链接。图集/视频 caption 与实体介绍保持可读名称，不扩建 article-only slice、通用富文本或引用卡片；内部语法不泄露路径。
- 正文/封面图失败保留文字和局部占位，图集坏一张保留顺序/页码且可继续滑动；视频失败保留可读 poster/caption 并结束有界尝试，已知不存在不自动重试；poster 或字幕单独失败不阻断可用视频。来源网页失效不影响随体成品。
- 复用当前正/负缓存与错误映射，图集实际加载共享负缓存，视频命中负缓存不续期或再次启动恢复；用户显式重试与成功清理仍服从原语义。不新增引用 TTL、逐图探活、健康注册表、自动修复、跨服务事务或缓存广播。

<a id="req-022"></a>
### REQ-022 release 交付同一 semantic document、协议版本与对象 revision

- homepage/article 的 producer package 与 release 必须同时引用同一 canonical semantic document 的 protocol version triplet `(schemaVersion, dialectVersion, canonicalizationVersion)` 与 object revision tuple `(contentRevision, sourceRevision, layoutRevision)`；前者版本化 AST envelope/字段、Markdown grammar/节点映射和 canonical bytes/digest，后者版本化对象内容、采用来源和统一布局规则。两组正交且不可互相替代。Service/Web/Android/iOS/工作台只投影这一节点树，端别、视口、入口面与环境不得选择另一份正文。
- Markdown 与 HTML 仅是来源 mapping type，映射结果共享节点身份、阅读顺序、媒体/caption、mention 与表格分类。表格统一分类为 data/layout：data table 跨端保持同一表头、单元格与可访问顺序，layout table 按同一线性化布局；移动端不得另建模板或重新分类。`layoutRevision` 只版本化这一套跨端统一规则，不同 viewport 不得选择不同节点集合、内容结构或阅读顺序。
- producer、release 与 reader 必须在解释节点前验证 protocol triplet、canonical digest 和 required capabilities；unknown `schemaVersion`/`dialectVersion` major、`canonicalizationVersion` mismatch 或 required capability missing 均 typed fail closed，不由 object revision、人工 disposition 或 renderer fallback 代偿。
- Wikipedia source revision 必须把 exact revision 的 wikitext 与 Parsoid HTML 共同绑定到 sourceRevision；homepage faithful adaptation 和 article 独立性由 author self-check 与 independent review 对 exact tuple 裁决。只改标题/角度的单实体百科文章 typed rejected，不得以新 `publishAngle`、contentId 或 layoutRevision 绕过。
- mapping/adaptation/independence 的 diagnostic 与 disposition 随对象保留并可由工作台只读展示；工作台与端 renderer 都不拥有人工 approval、semantic mutation 或 publish eligibility。人工决定后的继续生产必须产生新 tuple 并重新 review。

<a id="req-028"></a>
### REQ-028 四类岗位、多实例与具名分片协作事实边界

- 可复制团队模板只保存创作总监、创作者、独立 QA、电脑管家四类岗位、职责、必读引用、工作关系、禁止动作与复建核对方法，不含账号、Bot UUID、凭证、活动任务、旧授权或旧执行身份。岗位与人数分离：保留唯一总监和管家职责，四载体作者按每载体 2–4 个执行槽设计，QA 从 1–2 个独立会话验证起，实际启用量由总预算与实测吞吐决定，不设七人上限、不承诺十六作者满载、不增设载体组长。独立 QA 不得创作或修改其审核 execution，岗位不可临时互换给本人作品过审。账号部署绑定只证明配置，不签发业务身份或工作完成。
- 总监在用户授权内一次确认当次方向、候选/来源边界、载体预算与并发份额、停止条件及发布权限，保存到全员可读的现有任务输入/报告；不得扩大人类授权，也不逐题批准开工或转发正常交接。总监是本团队唯一发布与收官责任人，直接消费 approved 对象，执行获准的 publish/readback 与正式 milestone finalize/Git；只做机械发布检查，不重审内容、不代写草稿或代签 QA。缺发布授权时保留待发布并一次报告用户，不另设发布经理。
- 每位作者就是本人 execution 主会话，在已授权候选、来源与预算内自主选题、查重、原子取得小批 scope、取证、下载、创作、自检及 init/acquire/author seal；补取证、未封存输入修正、缩批或普通候选替换在既有契约允许范围内自主决定，不改冻结 target/已封存集合，不手写 receipt、不自审、不 publish。全部有效对象完成 author seal 后整批直接交 QA，有容量即续领，不等其他作者或整组作品齐套。
- QA 自主原子取得已 author seal 且无人持有的 review scope，每人一次只审一批，不同 QA 可并行审不同 execution；整批覆盖恰为 author receipt 的有效 resultRefs，逐作品核事实和真实媒体（图片看原图，视频看画面并听音轨），机械批量校验不替代判断。QA 只写本人 review 输入并自行 review seal，直接交总监并通知需处理退回项的作者；优先处理等待较久的合格已就绪批，长视频按真实工作量安排，不挑短件或等总监派下一批。
- 管家负责实际活动根、媒体可读性、磁盘、网络/站点故障、下载转码压力与证据保存，在已有工具/环境授权内给受影响人员可执行信息；不参与选题、审核或发布，不要求每次下载先请示。越权修复交工程 owner/用户，无精确授权不清理、迁移活动目录或停止他人进程。
- 按模板初始化后默认只读待命。核对四类岗位、多实例成员和共享信息，不等于启动 acquire/author/review/publish/release，也不启用 Routine。十团队 deployment 仍只表示部署集合；单账号自主生产增量只优化一个账号，多账号与 VM 扩容暂停，未来须另行授权与举证，不以更多 Bot 代替有效产出。Bot 角色、平台 `creatorProfileId`、来源原作者与宿主 `sessionId`/`runId` 互不代替，岗位简介不构成技术权限隔离或模型路由。
- 每个可认领单元必须显式冻结 `shardName`、正整数 `globalIteration`、`deploymentId` 与单调 `generation`；唯一键为 `(deploymentId, generation, globalIteration, shardName)`。`shardName` 是稳定、非空、不可变的业务可读名称并绑定不重叠对象范围，不从团队号、账号、Bot、session、PID 或目录临时推导；同名分片跨 generation/iteration 是新单元，旧 claim 不得复用。协作状态闭集为 `available|claimed|draining|blocked|closed`，不得以聊天、文件 mtime、inflight 或 receipt 缺席补造状态。
- 仅在用户已授权的 `globalIteration`、有效 deployment/generation、具名 shard、团队部署绑定、独立 QA 容量以及站点请求/模型/下载转码/随体与保护副本峰值预算均已显式预留时，宿主可自动 CAS 认领 `available -> claimed`；自动认领只选择既有 `available` 分片，不创建轮次、不扩大对象范围/预算/发布/清理授权，也不读取业务结果决定下一片。预算不足保持 `available` 或进入显式 `blocked`，不得先认领后透支。
- 协作事实只落在既有本机单文件 SQLite coordination 入口，保存具名分片归属、actor/execution/target 集合、generation、claim nonce、角色写 scope、预留预算引用、时间戳与 append-only 占用审计。一个小批只有一个 author，一个 review scope 只有一个独立 reviewer；同一短事务原子核验归属与在制容量，同批多抢仅一个 winner，失败者自行选另一已授权未领批。init 成功、群内认领消息或团队级 shard claim 均不自动证明作者级独占。只消费已冻结授权 target；滚动候选扩入须由同一既有入口明确支持且不改旧冻结集合，能力未证不宣称动态抢领可用。
- 每作者最多两个未闭合小批，其中最多一个正在创作；送审、审核中、待发布都计入未闭合，只有本批有效对象全部成功 publish/readback，或按现有契约明确终止且核完在飞写者，才释放该端到端名额。此处 readback 仅指本地 canonical 单对象发布事务的 exact 字节/身份读回，不要求下游 import、环境或 App/API 验收来释放生产名额。unknown 不释放；无发布授权只做有界试点，不把 review 通过当已发布腾名额。两批是单账号自主生产增量统一起始参数，调整只由总监依据实测端到端吞吐及资源余量在同一规则处确认，不叠加创作/待审/发布令牌或多层配额账本。
- 该库不新增 execution/review/publish/release 语义状态机，不解释 receipts 选择后继、签发业务完成或自动恢复；容量核验只读取正式事实及其 exact 绑定来验证调用方申报的占用/释放条件，不持久化第二套阶段状态或 completed 清单。`release pool-query`、三份 receipts、resultRefs、逐对象 publish proof 与 handoff 仍是各自唯一业务事实；SQLite 丢失可由明确人工重新建立协作边界，但不得由业务产物反推并补写旧 claim。消息、checkpoint 与只读汇总不是第二台账。
- 协作 release 必须对 exact 唯一键与 claim nonce 作单事务 compare-and-set，`claimed|draining -> available|blocked|closed` 由调用方显式给出；相同释放输入重放返回同一结果，nonce/generation/state 漂移零写。失联、十分钟无写入、TTL 到期、进程退出、账号切换或 `inflight=0` 均不得抢占、释放或转移 claim；终态未知则保留原 scope/证据，只冻结冲突正式写，其他安全划出的已授权任务可继续，不把观察结束伪造终态。
- 每轮先冻结有效 deployment/generation/iteration、具名 shard 与总预算，核原生在飞写者及前任交接后才在获准范围内认领。一个 deployment 仍至多一个 active shard，多个作者在该 shard 内持有不重叠 execution；不得创建额外 deployment 绕门。运行期增量检查按 `REQ-024`，不设每轮全团队十分钟零生产或整组齐套屏障。停止条件到达后先 `draining`、闭合本片在飞写与报告，再显式释放；预计耗时、轮次结束或建议比例均不证明业务完成。
- 后继团队认领前必须只读审计前任的 exact transition、claim nonce、receipts、产物与预算释放；后继只能清理自己 generation/claim 明确创建且不在保护集中的临时字节，不能清理、覆盖、seal、release 或接管前任未确认终止的产物。前任清理缺失或归属不明时后继报告 `blocked`，由原 owner/全局协调者在独立清理授权下处置。共同 publish 锁仍只串行化单对象事务，不是跨机器 claim。
- Grok 桌面多实例只采用同一官方签名 App 加每账号独立空 `profileRoot`/`SAND_USER_DATA_DIR`/`SAND_DATA_ROOT`；`instanceId -> profileRoot -> dataRoot -> deploymentId -> accountIdentityRef` 一对一且路径互不为父子，不复制已登录 profile、不修改 App/Bundle ID/daemon/relay。该内部入口按客户端 exact 版本与签名准入，升级后回到 `PROFILE_REVALIDATION_REQUIRED`；深链、系统通知、更新器、Keychain 与 Computer Use helper 不视为已隔离。
- 实例准入状态按 `PROFILE_ISOLATED -> ACCOUNT_VERIFIED -> LOCAL_EXEC_VERIFIED -> PRODUCTION_ELIGIBLE` 单向举证；窗口或 PID 存在最多证明进程启动。每 deployment 必须绑定同一账号身份引用、四类岗位及实际实例、独立 QA、共享 coordination DB identity、独立 execution/output/workspace 根与资源预留引用；同一 deployment 在同一 iteration 至多持有一个 active shard。稳定协作身份为 `shardId`，可读 `name` 仅展示且重命名不改变 claim/generation/target occupancy。
- 团队自主生产的每个 `task init/acquire/seal`、`publish-object` 与 `finalize` 有限写入必须携带 current coordination DB 与 generation write-fence 输入，并在真实业务写点核角色、actor、exact execution/target scope 与有效授权；长期有限调用由本机共享写者 gate 保护，释放/撤权等控制变更取对应独占 gate；不同小批可并行，SQLite 仅在 gate 内做短事务核验，不覆盖媒体处理等完整业务调用。锁序由 design 固定，禁止持有 SQLite 事务等待其他进程的长期 execution/publish 锁；同片换代必须等待受保护写者离开，不能解锁后裸写。单账号多作者同样不能省略围栏，缺失/失效时拒绝，不因环境变量遗漏回退无保护生产。只有显式指定的收官 deployment 内获准总监 actor 可执行 canonical publish/finalize/Git，producer 或同 deployment 的其他 actor 不因 claim 获得这些授权；同站总限流、桌面冲突与原生模型并发仍受真实宿主能力限制。
- 扩容准入逐级为 2、5、10 个真实账号实例；每级均重新证明 profile/data root、账号与 cloud computer、local daemon/gateway、外盘 UUID、共享 SQLite、独立 execution 根、预算、同片唯一 winner、旧代零写、断线不抢占与唯一收官。上一级证据不得替代下一级；十实例在线不关闭 M100000。

<a id="req-029"></a>
### REQ-029 全员共享同一有效任务版本，角色分别写入

- 总监确认的方向、目标、已授权动作、费用/站点/存储预算与份额、停止条件及版本/生效范围只落在一份现有任务输入/报告；已有授权直接引用，普通选题不重新请示，扩大人类授权仍由用户决定。全员可读预算余量、任务占用、前序 receipts、来源/媒体、QA 结果、publish proof、阻断与恢复裁定；总监、作者、QA、管家事实访问平等，凭证、令牌与无关隐私不共享。
- 可读不等于可写：作者、QA、总监与管家各写本人获准 scope，不能篡改他人输入、sealed bytes 或业务事实。已确认变更先保存再通知全队，受影响角色在下次认领/提交核对当前有效版本；在飞任务不追溯改变 actor/授权，紧急撤权由真实写围栏拒绝，不依赖群消息已读。
- 正常路径仅作者整批→QA、QA 整批结果→总监两次关键交接；一次给齐 execution、前序 receipt/ref/digest、来源媒体路径、允许 scope、下一动作、风险与授权引用，只 @需行动的人，作者不等待“收到”才续领。通知缺失从原事实核对，未回复不重派，不私聊保存唯一决定或要求全员确认。
- 当前必要事实不可读、版本过期或写权限缺失时暂停受影响正式动作并报告缺口，其他健康任务继续；不以旧记忆、Bot 简介或复制出的 completed 清单代偿，不新建看板服务、消息代理、管理平台、Envelope 或授权文件体系。

<a id="req-024"></a>
### REQ-024 总监增量检查主动保流，未知调用不抢占

- 运行期总监约每 10 分钟做一次低成本增量检查：合格空闲人员未续领、author seal 批无人接审、approved 未发布、资源阻断及调用明确终止后无人接续；不全池重扫、不要求全员同时汇报。已知失败、授权缺口与身份/完整性异常立即报告，在下一可执行检查处理，不等整点。
- 连续两次检查仍有无法解释等待，或超过同载体/阶段实测正常周期时，核原生状态并向责任人定向询问。长视频/转码仍在运行则按实测预期安排检查，10/20 分钟不是取消或 TTL 抢占门槛；无 native 时间不编造等待时长。
- 首次异常在现有 checkpoint 写问题、owner、下一动作与下次检查时间；下一检查仍未解释/解决时必须裁定授权内修复、确认终态后接续、交工程 owner、请用户决策或有 owner 的 blocked 等待，不只重复催问。普通未封存输入错误由本人修正，同类确定性错误再次发生即停止盲重试并一次升级；QA/发布拥堵只在预算内调已验证并发，不能取消审核或放宽名额堆稿。
- 调用明确终止后核原生终态、receipts、原 actor/授权，按原 retryOf/恢复契约由唯一 owner 接续；已封存成果复用，不冒用旧 actor。unknown、失联或额度耗尽保留原 scope，只冻结冲突正式写；缺可信终态/隔离授权就报告 blocked，请用户裁决，不取消未知调用制造周转。一个慢批只占所属作者容量；全局资源真实耗尽或 QA 全失效可暂停新增，不承诺无限不停工。
- 检查只用实际支持的原生通知/Routine/状态读取能力，单个非重入检查，不每 tick 新建总监或生产调用；初始化不自动启 Routine，启用需授权。无自动唤醒能力则明确需要人工唤醒，不签发无人值守通过。一次授权明确用户为最终接管人；总监失联时各角色保存本人 checkpoint，管家能通知即直接告知用户，不假定同账号仍有预算写最后交接，也不承诺未落盘推理可恢复。
- 同一个原生检查约每 10 分钟低成本核异常，并在每个整点对上个 `Asia/Shanghai` 完整小时只向已核目标群发送一次摘要，不另建小时调度器。逐载体分列有效 author 整批交付、QA approved/rejected/blocked、首次入池唯一对象、eligible 净变化和最老待审/待发布项；内容修订、恢复资格、身份归并及退出不计首次新增。图片或视频首次入池或净变化为零必须给出证据支持的原因、owner、下一动作和下次检查；连续两个完整小时为零或同一阻断未解时，总监须裁定授权内解阻/缩批、工程升级、用户决定或有理由 blocked，不只催促。
- 首次无基线、读取失败、事件范围不完整、Mac 不可达均报告 `unknown` 而非零；迟到事件按原小时补报并标补报时间。以目标群、时区和完整小时键幂等去重，重复 tick 不重复发送；发送失败保留原生失败回执并在恢复后补报。10分钟检查复用点名 receipts/review/apply proof，池全量查询仅在约定校准点执行并记录查询区间，不以来源统计或约4分钟全池扫描充当业务状态机。

<a id="req-025"></a>
### REQ-025 A/B/C 初始化安全收敛为同一团队规则

- A 新建：复用匹配 Bot，按授权并发补缺，核四类岗位/成员、实际工具/媒体链、原生身份、活动根与手册版本；只证明配置，不自动认领、生产、启 Routine 或清理。
- B 已有空闲：先证明无在飞或待接管任务，再原位更新岗位、唯一发布责任及总监检查触发路径；不删历史、不建重复 Bot、不继承无效旧授权。空载核验与共享版本读回后，另按生产授权启动。
- C 已有任务或 unknown：逐工作单元保留旧 scope/actor/receipts/版本，原调用保持身份至安全交接点再更新该角色，新任务遵守同一新规则；不等待全队同步切换，不改旧 receipt，不并行重派。unknown 保留对应范围、阻断及责任人，安全切换不建立长期旧权限兼容层。
- 三场景均通过宿主受支持入口更新并重新读回全角色共享信息可达性、同一有效任务版本和实际生效配置；仅文件或简介已改不等于活跃 Bot 已生效。缺 Grok 管理或原生调用读取工具时，交精确人工清单并保留外部阻断，不擅改客户端/relay。

<a id="req-026"></a>
### REQ-026 建议比例与放大边界不替代正式里程碑

- 主页:文章:图片作品:视频作品的 1:2:3:4 仅为整体建议，不是逐实体配额、阶段门或停止线。热门实体有据多作，冷门实体可只有主页；热度无证据标 unknown，媒体无可靠地点不捏造关联。同一实体始终只有一个稳定主页身份，主页扩量来自更多真实实体；原作拆图、换标题或换版本不增加唯一作品数。
- 各载体建议量可按价值最高扩展至基础建议的 50 倍，仅为用户确认的规划边界，不是生产量承诺、费用或发布授权。K=10000 对应 10000/20000/30000/40000 只作初始参考，实际阶段目标、可自主追加范围、费用/站点/存储预算、发布权限与停止条件取自有效人类授权；总监只能在内调整份额，达到建议比例本身不停止或拒收。
- 正式 M1000/M10000/M100000 数字只读 `content_distribution.policy.yaml`，不被建议比例或放大倍数替代；M100000 仍需四载体各至少十万累计唯一 finalized 对象与独立 release/handoff。基础工具通过、真实团队生效、净 eligible 产量提升与正式里程碑分别举证，不能互相替代。

<a id="req-027"></a>
### REQ-027 有界来源统计只读既有内容事实

- Skill 只读统计消费调用方点名的同一根、同一阶段对象/执行范围，不默认全库扫描、不出网、不触发生产、不写 receipt 或第二完成台账。默认标准输出，报告可由调用方保存于既有可删除运行输出。
- 按稳定对象身份消除版本重复，原作身份明确时消除同原作重复；同作品同网站计一次，图集多张图、视频poster、转码或新版本不增加作品数。无法核实跨平台原作关系时标未知，不凭标题相似或所有URL猜身份。
- 作品页网站按 sourceUrl 等明确来源字段核定；发现平台、作品页、可证原作网站分列。CDN/许可页不计内容源，百科参考列表不等于实际采用；原始响应的溯源线索与结构化字段矛盾留待核，不由统计改写身份。
- 每网站给唯一作品覆盖数/总范围作品数，以及作品-网站去重关联数/全部有效关联数的构成占比；前者合计可超过100%，后者在有来源关联时合计100%。空范围不除零；缺来源/无法解析单列，不能从总作品分母悄悄排除。来源统计不证明质量、当前eligible或原生审核生效。

<a id="req-030"></a>
### REQ-030 legacy sealed release 只经受治理重物化进入 current schema

- 本能力是一次性、显式调用的 current-schema 重物化边界，仅用于让既有 canonical approved 对象在 handoff schema 演进后继续形成可供 Alpha 消费的新候选。它不得让普通 reader、`release finalize` 或 `handoff-verify` 接受 legacy schema，不得修改、补字段或替换任何历史 handoff、cohort、release、review、publish proof、execution 或 receipt。
- 输入闭集为 source release root 与 source repository identity evidence、source `releaseId`、source handoff exact digest、source cohort exact digest、不同且全新的 target `releaseId`、target milestone，以及 current producer baseline。允许解析旧对象级 `research|commercial` 分类值的 schema 闭集精确为 `quwoquan_data/schema/release/legacy_release_cohort_v1.schema.json` 与 `quwoquan_data/schema/release/legacy_content_pool_handoff_query_v1.schema.json`，只用于读取 sealed source 并重物化 current output；不得按目录、`legacy*` 名称或宽 allowlist 扩张。unknown、缺失或闭集外版本一律在写入前 typed fail closed；普通 reader、`release finalize`、`handoff-verify`、current schema、candidate 与 rollback/recovery current terminal 均不得接受或携带旧分类。字段、枚举、path、operation、错误码及 canonical bytes 规则只由 Data canonical schema authoring source 定义，本文不复制 wire。
- legacy wire 缺少 `sourceRepositoryId` 时，必须由与 source terminal 摘要绑定、可独立验真的 source repository evidence 提供 source repository identity。不得从 target current repository、当前环境默认值、目录名或调用方自报值代填。source repository identity unknown、evidence 缺失或 digest 漂移时不得签发 current terminal。
- source release/handoff/cohort 必须已 sealed 且 identities、exact digests、source repository evidence 与 root binding 相互一致。重物化从 source sealed membership 取得对象身份集合，再对 canonical pool 执行 fresh readback，逐对象重验当前 identity、package、原 `content_review` 与 canonical publish proof。任一成员、review、proof、包或来源摘要漂移均在发布 target 前阻断，不得复制旧 counts、entries、摘要或 tree digest 冒充当前结果。
- current-schema output release、cohort 与 handoff 必须由 fresh readback 的当前 canonical bytes 确定性重建，重新计算 artifact entries、counts、object/query bindings 与 `treeDigest`，并在 lineage 中绑定 source repository evidence、source release、handoff、cohort identities 及 exact digests。lineage 的具体字段落点只引用并要求 Data canonical schema authoring source。原 `content_review` bytes 与原 canonical publish proof 保持不变，不生成 reviewer、attestation、execution、stage receipt、publish receipt 或其它未发生事实。
- producer 成功还必须把 current cohort 与 handoff terminal copy 以 create-or-same 保存到独立 publish 仓 `releases/<newReleaseId>/`。output release 是构建产物，单独存在不得冒充 producer terminal。publish terminal copy 与 output 对应 bytes/digests 必须 exact 一致并分别 readback。若 output 与 publish 跨根无法单事务，则顺序固定为先完成不可提升的 output candidate，再 create-once 写 publish terminal，只有两根 readback 全部闭合才返回成功。任一步失败不得签发半闭合成功，恢复只允许 exact replay。
- 该 command 不是普通 claim-batch，不创建或迁移 execution，也不得 claim/rebind legacy execution，不需要 batch nonces。它允许在真实用户授权下取得 migration-only iteration/shard claim，claim 的 target scope 必须覆盖 legacy cohort 全部 target refs。每次写入仍须同时验证真实 user authorization ref、唯一获准 director、global closer、current coordination generation、output/publish/library/carried 四根绑定、formal task context 与 exact write fence。
- formal task context 必须由现役 schema/入口绑定真实 `confirmationRef`、`confirmedBy` 与只允许本动作的 `allowedActions=repackage`。手写任意 JSON、未绑定文件、调用方自报 digest 或环境变量拼装不得成为正式 authority。现役完整 deployment 必须复用真实已授权 roster，不得为通过 generic registration 伪造固定七角色、占位 actor 或无关人员。若需要 director-only migration deployment 而现役 authoring source/入口尚不支持，则保持工程 gap。
- migration-only claim、task 与 fence 不授予忽略并发的权限。执行前必须核验现役 native writer 与 release lock，不得用 coordination DB 为空、无 batch row 或无 execution 推断没有其它写者。跨 iteration target occupancy、native writer 冲突、release lock 冲突、非 director、非 global closer、stale generation、四根漂移、task 漂移、缺 fence 或 fence 未 exact 覆盖 cohort 均在任何业务写入前 fail closed。
- target 采用 staging 与 create-once。same target identity、same frozen input 与 exact same bytes 为 exact replay。target 已存在但任一输入绑定或输出/publish terminal 字节不同则 typed conflict。staging、验证、output publish、publish terminal write 或任一 readback 故障均不得被报告为成功。source terminal tree 的 before/after digest 必须相同，existing execution 的 actor、generation、receipts 与 release binding 也必须不变。
- 旧 source 与已成功的新 output/publish terminal 均 immutable。成功后不提供删除新 release 的普通 rollback，失败或取消只可清理尚未发布且未被保护集引用的 staging。成功结果如不再采用，只能走现有受治理 retirement 与保护集。缺少该能力时继续保留，不得 `rm`、覆写或借 rollback 清理。
- candidate 与 rollback/recovery 本来就是两个彼此不同、且均不同于 source 的全新 release identities，不是“删除 candidate”的 rollback。失败保留 source、previous active/current output 与任何已成功 terminal。恢复只能重放完全相同输入，或显式选择另一全新 `releaseId` 重新构建。观测只报告 source/new identities、exact digests、双根 readback 与首个 typed blocker，不新增 ledger、双读、兼容 reader、自动迁移队列或后台修复。

## 4. 契约引用

- canonical entity/identity：`quwoquan_data/schema/publish/entity.schema.json`
- canonical post/manifest：`quwoquan_data/schema/content/post_manifest.schema.json`
- release handoff：`quwoquan_data/schema/release/producer_release_handoff.schema.json`
- 对象包、来源、仓身份与目录语法：`quwoquan_data/schema/publish/`（由 Data authoring source 单点定义；未完成由 `OPEN-025`、`OPEN-027` 跟踪）
- 下游 mention 与目标可见性：`quwoquan_service/services/content-service/contracts/`、`quwoquan_service/services/entity-service/contracts/`
- media processing policy：`quwoquan_data/schema/content/media_processing_policy.schema.json`
- release：`quwoquan_data/schema/release/release_header.schema.json`
- asset admission：`quwoquan_data/schema/release/release_asset_admission.schema.json`
- lifecycle policy：`quwoquan_data/schema/governance/content_distribution_policy.schema.json`
- environment readiness：`quwoquan_data/schema/release/environment_release_readiness.schema.json`
- 下游环境 ship report：`quwoquan_data/schema/release/ship_report.schema.json`（环境 owner 消费契约，非 producer stage）
- release identity incident：`quwoquan_data/schema/release/release_identity_incident.schema.json`
- stage receipt：`quwoquan_data/schema/execution/stage_receipt.schema.json`
- canonical pool record：`quwoquan_data/schema/release/pool_object_record.schema.json`
- UAT matrix cell binding：契约字段 `required|not_applicable`、repo-relative `spec_ref`、`runner`
- 团队岗位与 Grok 重建：`.agents/skills/content-production/references/team.md`、`.agents/skills/content-production/references/grok-team-rebuild.md`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 独立载体分别执行且引用闭包后形成 producer release

- GIVEN homepage、article、image、video 各有一个 immutable execution，并共享同一 source revision 与 entity catalog digest。
- WHEN 四个 execution 由宿主按当前会话能力分别执行，可串行或在不同 execution 间重叠生产，且操作者请求聚合 producer release。
- THEN post 不等待 homepage execution 或 publish，任一载体失败只保留在自身 evidence，其他载体已合格对象仍可 publish。
- THEN 仅从 entity identity、creator、tag、source 与媒体处置全部闭合且 `content_review.json` approved 的对象中选择 immutable cohort；悬挂引用只排除对应对象，足量有效 cohort 仍可 release。
- THEN 同一 execution 的 `4.draft` 只有一个 author actor 会话、`5.review` 只有另一个 reviewer actor 会话；不同 execution 是否重叠不影响 publish 或 release。任一 execution 的 publish 不得早于自身 `003-5.review` seal，但不得等待其他 execution 的 review/publish terminal。
- THEN 某 execution `0 < approved < quota` 时 stage result artifact/typed issues 保留 shortfall，通用 receipt 仍为 `pass` 且全部 approved 对象 finalized；`approved == 0` 或 stage-wide identity/integrity failure 时才 `blocked`。
- THEN 全批次零 rejected 仍允许成功；若存在 rejected，则每个对象必须有非空 `objectRef` 与 `content_review.json` blockingIssues/typed issues。
- THEN 单 execution review/publish 失败只阻塞该 execution。
- THEN 四个 execution root 相互隔离；共享 canonical 只经逐对象原子事务，release 只读 AI 显式 cohort，环境是否消费不参与判定。

<a id="gwt-002"></a>
### GWT-002 默认发布消费链公开交付且权利只作记录

- GIVEN 四载体对象共享同一 source revision/digest/entity catalog digest，素材已取得且完整记录来源与权利事实（含 `unverified`/`unknown`/`restricted` 资产）。
- WHEN 不选择任何类别生成 immutable release，并由下游环境按自身配置导入和消费。
- THEN 发布、导入、激活和消费不携带或要求类别选择；同一 immutable release 在不同环境保持相同内容身份与媒体字节，环境差异只由显式环境配置生效；每条媒体引用均可按同一公开交付契约读取。
- THEN 权利状态只进入 header 的权利计数、`authorizationRequiredAssetIds` 与 `containsUnverifiedAssets`，不排除任一对象；未取得、生成素材、缺来源字段与不可播放视频仍被阻断；文章批次配图率只写入统计，单篇 illustrated 文章只要求恰好一张封面且全部配图来源可追溯，配图张数不设下限。
- THEN 环境 readiness 以 fresh guest 证据闭合，不要求隔离证明、白名单账号或 attestation；Alpha/Beta/Gamma 的 Environment Ops scheduler request 绑定同一 exact integration candidate，Prod acceptance 另走 RC Qualification package acceptance、`ReleaseTagAdmissionFact`、`ProdActivationAdmissionFact` 与 hosted facts，不生成 Prod EAF。
- THEN 当前非商用开发验证中，四入口与公开媒体 GET/HEAD/Range 不因缺少授权记录而隐藏或拒绝；权利记录与其他认证/环境访问边界仍保留，不新增运营放行开关，不回写 producer release、cohort 或 handoff。类别参数和命名消费轨道不得作为兼容入口，也不得改用另一固定标签；商用治理只由 [`OPEN-026`](#open-026) 跟踪。

<a id="gwt-009"></a>
### GWT-009 宿主并发不改写数量与对象判据

- GIVEN 相同 confirmed demand、candidate set 与 quota，以不同宿主原生并发执行。
- WHEN 宿主 AI 产生 stage receipts 与逐对象 transaction facts。
- THEN quota、workUnitCount、对象 identity/eligibility 与显式 release cohort 相同；并发、elapsed、模型与会话数不写入业务 authority。
- THEN 仓库不保存宿主调度或容量 receipt，亦不据其自动推进或恢复。
- THEN 未证明两账号同时保持受支持本机连接时只启用轮换，不把单次调用内站点间隔或本机 flock 当作跨账号锁。

<a id="gwt-010"></a>
### GWT-010 宿主中断不伪造阶段结论

- GIVEN 某步尚无 create-once receipt，或已有部分草稿但原调用终态未核。
- WHEN 新会话接手同一 execution。
- THEN 新会话只读取同一冻结输入与已有 receipts。未 seal 步骤仅在原真实 actor 可核验时续写部分产物。代码不写假 verdict、next、deadline terminal 或 recovery state。
- THEN receipt 已 blocked 的 execution 不续跑，只能新建 execution。既有 receipts 与成功对象字节不变。
- THEN 轮换接管时原写者停止同片新增。新写者在读回三份 receipts 与产物并接受责任后才写入。

<a id="gwt-011"></a>
### GWT-011 AI 单写 stage verdict 与 typed issues

- GIVEN 一个步骤无合格对象或硬事实不闭合。
- WHEN AI 调用 `task seal`。
- THEN actor 与 verdict 由 AI 显式提交，seal 自行校验硬事实并 create-once 写 receipt；不存在第二状态 writer。
- THEN pass 后继只按 Skill 固定顺序，receipt 不包含代码派生 nextAction/recovery stage。

<a id="gwt-016"></a>
### GWT-016 下游消费的数量与 entry surface × carrier 矩阵可闭环复核

> 本场景及 `GWT-028` 至 `GWT-033`、`GWT-035`、`GWT-043`、`GWT-044` 只验收下游 consumer/environment 行为，不构成 producer 准出；producer handoff 不拥有其中任何 sample、UAT、EAF、promotion 或 rollback 事实。

- GIVEN 一个已确认请求为 homepage/article/image/video 分别声明正整数对象数量，同一请求沿 producer 单轨形成 immutable release，且下游验收清单为 entry surface × carrier 二维矩阵。
- WHEN Alpha 依次完成 import、projection/API/media verify、activate，并由每个 required cell 的 repo-relative runner 执行 fresh Remote App UAT。
- THEN 每载体均满足 `selected = imported = projected = verified = readback = qualified`。`qualified >= requested` 表示该载体达标；`0 < qualified < requested` 表示 partial，`shortfall = requested - qualified`，已合格对象仍可见而不伪造成达标。
- THEN 16 个 cell 各自显式声明 `required|not_applicable`；required cell 具 repo-relative 验收锚点引用、runner 与绑定同一 release identity 的 raw `ReadinessCaseResult`，not_applicable cell 具可复核理由与验收锚点引用。carrier 与 entry surface 不互换，micro 不属于 carrier 轴。
- THEN import、projection 或 API/media verify 在 activate 前失败时 candidate 停在对应 typed 终态，previous active pointer 不变，且不生成本 candidate 的激活成功事实。
- THEN activate 后任一 required cell 失败时只记录 typed failed result；操作者显式执行 rollback 后，rollback/readback 必须证明四个 entry surfaces 全部恢复同一 previous release identity，`durationMs <= 300000`。超过预算、pointer 未恢复或任一 surface 混合 identity 时终态为 canonical `rollback_failed`，本次 raw 结果保持可读且旧 release/receipt 不得替代失败 cell。

<a id="gwt-020"></a>
### GWT-020 宿主 AI 六步沿 acquire/author/review 三份 seal 单轨闭合

- GIVEN 一个 identity-only candidate-backed execution 与 canonical Skill；task init 已为每个稳定 process `targetRef` 冻结 immutable target descriptor，唯一映射到 canonical logical entity identity 与独立 content version，且未给 process ref 拼接版本后缀。
- WHEN 宿主 AI 依次执行 acquire、author、review 三步，每步直接写业务产物后调用 `task seal` 提交真实 actor 与 verdict；seal 自行校验硬事实并 create-once 写 receipt。
- THEN 不存在 stage-open、宿主 verifierFacts、stage-gate/业务完成 registry、semantic prepare/record、runner/fleet/语义 lane claim、自动恢复、execution-state reducer 或代码派生 next；pass 后继只按 Skill 固定顺序，blocked 后新建 execution。
- THEN candidate binding 只冻结目标对象身份，init 输入是一份 round spec（`executionId` 逐 carrier 给出，`familyRef` 缺省派生，逐 target 只写身份；homepage 的 `region` 在 init 即校验为现有行政区 tag），并由同一次 task-init 冻结 process `targetRef`→canonical logical entity identity + content version 的 immutable descriptor mapping；`entityCatalogDigest/candidateCount/status/quota` 等可派生字段不由 AI 手写，canonical 字节化由脚本完成；`acquire` 由 AI（主会话或该 execution 的 author）出网取得来源并按 execution 提交一份 ingest 清单（逐 target 的本地文件路径 + 申报的 `sourceUrl/directUrl/license/licenseUrl/creator/sha1/description/relevance` 与水印三字段，可选 `discoverySignals`；page 来源附 AI 以通用工具落盘并亲笔附取证段的 `source.md`），脚本零网络地从本地字节生成 source units/source refs/CAS、sha256、mime/probe/poster 硬事实，按申报 sha1 交叉校验字节，按申报 license 派生 `rightsStatus`，不阻断；超预算视频转码为 mp4 派生体；source/package identity 必须绑定同一 mapping 摘要，映射缺失或漂移在 seal 写 receipt 前 typed fail closed；不存在 2.quality/3.compose 产物。
- THEN `author` 每对象只写 `page.md|draft.article.md|image_work.json|video_script.json` 之一，标题/tagRefs/creatorProfileId 由产物自身声明且 tagRefs 必须解析到 taxonomy、creatorProfileId 必须解析到 creator 注册表、homepage 必须至少一个百科 `page` 来源，三者均在 `002-4.draft` seal 逐对象校验而不是 publish；seal 一次报出全部对象的违规，违规对象只以 typed issue（含 `objectRef`）退出本 execution 且不进入 resultRefs，至少一个合规产物即 `pass`，零合规才 `blocked`；`4.draft` 目录允许存在草稿以外的文件；`002-4.draft` receipt 冻结同一 execution 唯一真实 author actor/invocation 与合规产物 exact refs/digests。
- THEN `review` 由另一个真实 reviewer actor 会话执行，按 execution 提交一份判断输入，覆盖集合恰为 `002-4.draft` receipt 的 resultRefs 对象集合，逐对象只含 `decision/blockingIssues/advisories`（可选 `safety`、逐资产 `assetRights[].issues`、只记录的 `qualityScores/qualityNotes`），只在证据缺失、安全隐私、素材不相关或不可播放时 reject，权利疑虑写入 advisories；`003-5.review` seal 把该输入机械扇出为逐对象 `content_review.json`，从对象实际引用的资产补齐 `assetRights`（缺省 approved）、缺省 `dimensions` 与 schema/stage/executionId/objectRef/draft 字段，原样透传 `qualityScores/qualityNotes`，并冻结 reviewer actor/invocation 与 exact ref/digest。review 文件物理路径继续按稳定 process ref 定位，但 `content_review.objectRef` 与 disposition 必须绑定 descriptor 所指 canonical target；review 的 objectRevision.contentRevision、descriptor version、manifest version 与 pool record contentVersion 必须一致，任一缺失或漂移在 review/publish 写入前 typed fail closed。author 与 reviewer 必须不同 session/runId，可为同一 model family，任一方可以是宿主派发的独立子 Agent 会话。
- THEN approved/rejected 可混合；短缺由 stage result artifact/typed issue 表达且 receipt 仍为 `pass`，只有零 approved 或 stage-wide identity/integrity failure 才 `blocked`。
- THEN publish AI 对 approved 对象逐个调用同一原子事务，权利状态只记录；作品携带 final media/source/review 与 records，不依赖原 library 消费。release 消费 AI 显式 cohort/milestone、禁止 all-publishable，四载体计数不低于目标即达标；finalize 交付现有两份 terminal 事实，绑定工程 baseline/契约摘要与独立内容仓 exact 快照，不冒称已提交或已具异卷备份；producer 固定到 `END`，环境消费不构成后继或完成条件。

<a id="gwt-022"></a>
### GWT-022 随体媒体独立校验且 release 只作分发物化

- GIVEN 一个通过原子事务生成的完整对象包及显式 cohort，manifest 绑定随体 final media，原 execution/library 不可用。
- WHEN 完整复制对象后执行只读闭包验证与 release 物化，并分别注入媒体缺失、损坏和非法引用。
- THEN manifest 中的稳定资产身份、相对媒体引用、摘要与大小精确对应包内实际字节；pool record 只绑定包摘要而不复制资产事实。
- THEN 完整作品不依赖 execution/library 或跨包 symlink；仅检出 Git 元数据不能声称得到完整媒体包。
- THEN release 分发字节与所选 manifest 摘要一致，实际格式、资产顺序、poster 与真实字幕绑定不因搬目录变化。
- THEN 物化结果可由同一完整包及冻结 build 输入重建；verify 与消费者不下载、补库或借旧 release 修复。
- THEN selected 媒体缺失、损坏或引用逃逸使 transaction/build typed fail closed，零部分成功 release 可见且不刷新旧 receipt。
- THEN 相同包重放不增加身份、版本或 pool record；跨作品复用相同摘要不授予新作品资格。
- THEN 库不可用但完整包可读不构成失败；包字节缺失则即使元数据在场也不可交付，独立备份的恢复须显式执行并验证摘要。
- THEN 实际部署对象与所选摘要对账失败时不得 activate 或覆盖 previous active，运行 URL 不含本地路径和来源站直链。
- THEN 隔离测试副本不登记为生产备份；同卷拷贝或硬链接不证明异卷耐久性，未验证部分如实保留。

<a id="gwt-023"></a>
### GWT-023 homepage 与三载体均逐对象 publish

- GIVEN 一个冻结 homepage 载体、receipt 链已 `5.review` pass 的 execution。
- WHEN publish AI 对该 approved homepage 调用 canonical 单对象事务。
- THEN publish 分派到实体路径并给出逐对象发布判定，不再以「homepage 未接线」拒绝整个 execution。
- THEN 目标唯一绑定冻结实体身份；canonical ref 不由物理路径或 process `targetRef` 推导，process ref 不追加 `/1`。publish 只消费 immutable descriptor 冻结的 process→canonical logical identity + content version mapping，实体按已核实地域与同名组分配 locator；mapping 缺失/漂移、无实体对象、名称歧义或身份冲突时均在写 canonical object/pool record 前结构化失败。
- THEN `content_review.json` 为 rejected 的对象记为排除、缺冻结输入或 review identity/integrity 失败的对象记为阻断，两者语义不混用。
- THEN apply 模式下零对象晋级必须报错而非以成功报告收尾。
- THEN revision 保持原 process ref 与 canonical entity identity 稳定，只递增独立 content version；新 descriptor、review objectRevision、manifest 与 pool record 对该版本一致。same-input replay 只可收敛到同一 mapping/bytes，handoff 只引用 canonical identity/version 与现役 publish proof而不把 process ref 变成业务 identity；历史 sealed bytes 不重写，current reader/writer 不 alias 旧 process ref。

<a id="gwt-024"></a>
### GWT-024 candidate identity 与下载证据保持单一边界

- GIVEN 一个同时含 homepage/article/image/video identity-only candidates 的显式集合，task-init 前不存在 capsule/admission receipt。
- WHEN 构造 execution 输入并在 `sources` 与 `1.download` 形成来源计划和取得证据。
- THEN 每个 candidate 只携带对应目标对象身份、carrier、canonical coverage target 与 candidate identity；task init 同时冻结 target descriptor 及 process→canonical logical identity + content version mapping，source/package identity 绑定其摘要。映射或摘要缺失、重复、歧义或漂移在任何 seal/publish 写入前 typed fail closed，媒体候选不因缺少 pre-init source admission 被排除。
- THEN 每个 `1.download` source unit/source ref/CAS holding 绑定同一 target/candidate identity 与实际 bytes hard facts；来源或字节失败留在该 target 的 typed issue，不倒写 candidate，也不建立 capsule/admission 投影。
- THEN 显式输入构造与 identity/version/digest 漂移比对取自同一实现，task-init→seal→publish、revision、replay 与 handoff 测试均须绑定同一 descriptor mapping；任一处不得独立维护等价映射或新增 resolver/projector，current 单轨不得 alias 旧 process ref，历史 sealed bytes 不得重写。
- THEN 本域契约判据的全部判据文件经交付门禁的分片矩阵执行，每个文件落进恰好一片；任一红片阻断汇总与候选 evidence，不以局部选择冒充全域覆盖。

<a id="gwt-025"></a>
### GWT-025 百科结构化信息区参与不可变事实取证

- GIVEN 一个百科来源，其票价、开放时间或官方网站只出现在结构化信息区，可见正文里没有对应表述。
- WHEN 为该实体准备 homepage 或 article 的 immutable source candidate。
- THEN 信息区里的受治理字段被解析为不可变结构化事实，该候选不再因缺少结构化事实被判短缺；多个受治理字段同时在场时按与可见正文一致的字段优先级取一条。
- THEN 字段名与取值语义不一致，或字段名不属于受治理集合时，该候选事实作废且不落入其它字段。
- THEN 信息区缺席时按可见正文的结论收敛，不因缺少信息区而额外失败。
- THEN 官方网站只接受安全传输协议地址，非安全地址视为无结构化事实。

<a id="gwt-027"></a>
### GWT-027 载体字节预算单点声明且在下载截面完成判否

- GIVEN 一个 carrier 已声明的来源单元，其候选图片分别落在「预算内」「超预算但可降采样进预算」「超预算且每档都装不进」三种形态。
- WHEN 运行 `1.download` 截面的下载处置。
- THEN 预算内候选原样保留；可降采样候选被替换为第一个装进预算的已声明交付档，字节摘要、内容类型与像素几何按派生体重新登记，并在 funnel 里留下该派生记录。
- THEN 每档都装不进的候选在该截面即被判否，issue 为 `DATA.MEDIA.ASSET_OVER_BUDGET` 且点名该资产，funnel 丢弃原因为预算门；publish 期不再出现 `SINGLE_ASSET_OVER_BUDGET`。
- THEN 下载截面与 publish 截面对同一载体读到同一个预算值，且该值只能来自 `objectStorageBudgetBytesByCarrier`；任一侧不存在独立的预算常量。
- THEN carrier 缺席或落在闭集之外时该截面判否，不产生任何按默认预算放行的资产。
- THEN 一张 EXIF 声明 90° 旋转的横向全景图，其记录的宽高为显示几何而非存储栅格几何。
- THEN 源栅格像素上限只在 `media_processing.policy.yaml` 的 `maxSourcePixels` 声明一次且不低于 `maxPublishableImagePixels`；解码库的解压炸弹阈值与它相等；一张像素数落在解码库默认阈值与 `maxSourcePixels` 之间的全景接片能被探测并派生出交付档，超过 `maxSourcePixels` 的源返回 typed `pixel_limit_exceeded` 且不发运行时告警。
- THEN 派生 JPEG 源时解码栅格的宽度小于源宽度且不小于目标交付宽度，交付档几何与整幅路径一致；像素数超过 `maxPublishableImagePixels` 但字节在预算内的候选在下载截面被替换为已声明交付档并登记 `resize` 派生记录，入池存储体像素不超过发布上限。

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

- GIVEN carrier demand/execution manifest/stage receipts、canonical object transaction/pool record、ContentRelease、Alpha/Beta/Gamma operation/EAF v2 与 Prod admission/hosted lifecycle facts 均已有 create-once evidence。
- WHEN 查询 `ContentProductionTaskView`、`ContentItemVersionView`、`EnvironmentReleaseOrderView`、`ReviewDecisionTimeline`、`ReleaseSelectionView` 与 `TargetAcceptanceView`，并重建 projection。
- THEN 六个 view 只由各自 owner refs/digests 确定性投影。
- THEN 六个 view 没有 command、Repository、checkpoint、独立 ledger 或 terminal writer。
- THEN 删除 projection 后重建结果逐字段相同且 owner bytes 不变。
- THEN `EnvironmentReleaseOrderView` 只读 Alpha/Beta/Gamma EAF v2 与 Prod `ReleaseTagAdmissionFact`、`ProdActivationAdmissionFact` 和 hosted lifecycle facts，不把四者投影成同一种 acceptance。
- THEN 缺环境、顺序冲突或 digest 漂移时返回 typed blocked。
- THEN typed blocked 不补写 acceptance，也不从环境名猜状态。
- THEN query 不以 projection cache 或最后一次成功值替代 owner refs/digests。

<a id="gwt-030"></a>
### GWT-030 EnvironmentAcceptanceFact v2 由 scheduler 绑定完整 closure

- GIVEN Data-owned `ReleaseUatSamplePlan` 已声明同一 release 的所有 required/not_applicable cell，required runner 已分别产生绑定同一 exact integration candidate 的 raw canonical `ReadinessCaseResult`，且 Environment Ops 为同 candidate 建立 target scheduler request。
- WHEN Environment Ops scheduler 请求签发该 Alpha/Beta/Gamma target 的 `EnvironmentAcceptanceFact` v2 并执行完整性查询。
- THEN EAF 的 `caseResultRefs` 直接列出全部 required raw refs 与 exact-byte digests，并同时精确绑定 `candidate`、`impactPlanDigest`、`runtimeIdentity`、`dataLifecycle`、`providerReadiness`、`observabilityReadiness`、`inspectEvidence`、`doctorEvidence`、`cleanupEvidence`、`leaseClosureEvidence`、环境 predecessor、有效期、`nonPromotable` 与 DSSE signer；profile 只允许 `smoke|integration|release`。
- THEN 任一 required raw result 或 named closure 缺失/失败、digest 漂移、runner/验收锚点引用不匹配、candidate/profile/predecessor 不同或签名无效时 acceptance fail closed；counts、旧 receipt 与 projection cache 都不能代填。Data 不调用 EAF writer；retired EAF profile、Data release identity、raw-result 聚合、consumer binding 与 Prod 属性均不在 v2 字段闭集中。

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
### GWT-032 显式媒体契约与有界恢复不依赖发布类别

- GIVEN 默认 release 的公开媒体及普通授权能力下合法的 progressive private MP4，媒体引用声明各自明确的访问方式与稳定资产标识，另有字段缺失和 private HLS 负例；输入不包含发布类别或命名消费轨道。
- WHEN App 播放器发起初始请求、Range 请求并在当前位置收到首次 401/403。
- THEN 边缘逐 Range 重新验签；App 强制换签最多一次并从已确认位置恢复，二次 401/403 停在 typed terminal，播放位置不归零且不回退公开 URL。
- THEN 公开媒体无需换签即可按同一身份读取；受权媒体的 null/absent 访问方式或错误资产身份 fail closed，不因类别缺席而降级为 public。private HLS 返回 unsupported typed terminal，不进入 MP4 fallback。

<a id="gwt-043"></a>
### GWT-043 公开媒体身份与逐图说明无损消费

- GIVEN 新的无类别 release 含有序多图作品和可播放视频，每条媒体有稳定资产标识、摘要及 public slice，多图具有不同 caption，另有旧类别和 Data 专属私有交付字段反例。
- WHEN importer、query decoder 与 App 消费同一 release manifest。
- THEN 来源归属、水印、派生修改、资产顺序与逐图 caption 保持一致，caption 不以 title 替代；App 图集展示逐图说明，视频 Range 播放有独立真实证据。
- THEN 旧类别、Data 专属私有交付字段、缺身份及摘要漂移均拒绝，不自动适配或默认 public，不读冗余资产旁车。

<a id="gwt-033"></a>
### GWT-033 future private HLS 按独立授权链可消费

- GIVEN 普通授权能力下 future private HLS，媒体引用显式声明 access mode、稳定 asset identity，以及 manifest、segment 与 key 的授权边界；它不是另一 release 类别或默认公开内容的前置。
- WHEN App 播放器请求 manifest、连续 segments 与 key，并跨授权 TTL 继续播放或恢复。
- THEN edge 对 manifest、每个 segment 与 key 分别执行受治理授权校验，未授权、过期或 identity 漂移均 fail closed。
- THEN TTL 过期后只沿 private HLS 的受治理换签路径恢复，保持已确认播放位置，不回退 progressive MP4 或 public URL。
- THEN 同一 release/asset identity 的 local contract、edge integration 与真实 App UAT 分别证明授权边界、过期恢复和可定位播放终态。

<a id="gwt-044"></a>
### GWT-044 删除专属研究身份不削弱普通认证与共享媒体授权

- GIVEN Data/Service/App/Ops 按无类别默认链消费同一 release，另有普通登录、原图授权与 signed_grant 业务。
- WHEN 普通 guest 调用内容 feed/detail，另行调用普通身份与共享媒体授权边界。
- THEN 公开内容不要求 research session、白名单或 attestation，旧专属 operation/config 不再注册；当前开发期不因缺少授权记录隐藏或拒绝，商用治理由 `OPEN-026` 跟踪，不新增本阶段运营开关。
- THEN 普通 JWT/OTP、原图 view/save 配额、签名与到期校验保持原约束，非法请求仍拒绝，不因删除专属分支放宽共享权限。

<a id="gwt-046"></a>
### GWT-046 Gamma/Prod prevalidate 核心诊断不可提升

- GIVEN 同一 release 已有 exact prepared apply、completed activate、candidate/fenced readback 与未漂移 runtime candidate data-plane binding。
- WHEN Gamma 或隔离的 Prod prevalidate 选择核心 feature 运行 `ship verify --verification-purpose core-diagnostic`。
- THEN Data 复用现役 guest identity、feed/detail、search/recommendation 与 image/video Range consumer verifier，报告六项闭集的 `passed|failed|not_executed`，并恒写 `nonPromotable=true`、`releaseEligibility=GATE_BLOCK`、`readinessWritten=false`；不写 `release-readiness.json`。
- THEN 缺 selected Data required case、candidate/apply/activate/binding 漂移、Prod 非 prevalidate、Prod 非 isolated 或正式 Prod 输入均 fail closed；默认 formal verify 仍要求原 M10/Beta predecessor/lifecycle Exit/premium closure。

<a id="gwt-034"></a>
### GWT-034 四载体 producer 里程碑按累计唯一对象形成独立 handoff

- GIVEN 集中式架构禁令要求已退役编排、兼容读写和自动恢复在生产源码、schema、control plane、测试正例与 active specs 中物理归零；已有一组通过当前 Skill 生产并 finalized 的 canonical 对象及其原 execution/publish proofs。
- WHEN 依次形成 M1、M10、M100、M1000，每级按 `cumulative_unique_finalized_objects` 选择 cohort、构建 immutable release 并物化 producer handoff；cohort 四载体计数不低于该级目标即达标。
- THEN 首次生产对象具完整三份 seal receipts 与逐对象 publish proof；更高级别复用对象时 canonical publish proof 原样不变，不伪造新 execution 或新 receipts；凡已完成 canonical publish 且 review approved 的对象都可进入 cohort。
- THEN 每一级都有自己的 full explicit cohort、release identity 与 producer handoff，逐对象绑定 canonical identity 和原 producer proof；重复 identity 不增加累计值，新增唯一 finalized 对象使累计值分别达到该级下限。
- THEN producer handoff 不包含 `ReleaseUatSamplePlan`、sample authority、import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback facts；下游是否消费任一级 release 不参与本 GWT。
- THEN 此 GWT 只验收当前 Skill+AI Agent producer 架构；失败形成当前架构 typed blockers，不产生兼容或恢复旧轨的授权。

<a id="gwt-035"></a>
### GWT-035 Data ship 与 Environment Ops acceptance 单向交接

- GIVEN 同一新架构需要在 Data ship 交付后形成 Alpha/Beta/Gamma acceptance。
- WHEN Data 产出 apply/import/readback/health 与 raw CaseResult，并把同 candidate scheduler request 交给 Environment Ops。
- THEN Data result refs 不含 EAF；Environment Ops scheduler 独占签发完整 v2 EAF，canonical profile 只为 `smoke|integration|release`，前驱只按 Alpha→Beta→Gamma exact EAF 链闭合。`m1_api_consumer` intent 不冒充 EAF profile，也不省略任何 named closure。
- THEN Prod 不创建 EAF；Prod acceptance 只消费 RC Qualification 的 package/provider/UAT/supply-chain `QualificationFact`、stable `ReleaseTagAdmissionFact`、`ProdActivationAdmissionFact` 与 hosted rollout/readback/soak facts。任何 acceptance 都不得回授 legacy 删除 authority或引入 sequence-017/旧控制面兼容。

<a id="gwt-036"></a>
### GWT-036 homepage 结构化事实在 publish 截面按唯一 schema fail closed

- GIVEN 一个 review approved 的地点 homepage 对象，实体事务准备从冻结身份与真实来源投影唯一 manifest。
- WHEN canonical 单对象事务执行 homepage 最终面投影。
- THEN 未核实主地域或归属冲突时对象结构化失败；只证实到省/市的对象保留该真实行政链，不虚构区县。
- THEN 主来源不满足 publish entity schema 的百科闭集与取证约束时对象结构化失败，不留给下游 importer 发现。
- THEN 结构化实体事实按 publish entity/manifest 契约校验后仅写入 manifest，不生成第二实体头，consumer 不从目录猜身份。

<a id="gwt-037"></a>
### GWT-037 来源侧零出网：ingest 只从本地字节与申报事实派生硬事实

- GIVEN 宿主 AI 已用通用工具取得一个 target 的来源文件到本地，并写好该 execution 的 ingest 清单（每 target 一组本地文件路径与申报的 `sourceUrl/directUrl/license/licenseUrl/creator/sha1/description/relevance` 与水印三字段，可选 `discoverySignals`；page 来源附 AI 落盘并附取证段的 `source.md`）。
- WHEN 在无网络的环境下对该 execution 运行 `task acquire --input <ingest.json>`。
- THEN 命令成功写出 source units、`1.download/source_refs.json`、content library CAS 引用、sha256、mime/尺寸/时长与 poster，全过程零网络调用；`quwoquan_data/scripts/content/source/**` 与 `core/**` 不存在任何 HTTP/socket 出网点，静态门只对环境侧 `public_api_client.py` 放行。
- THEN 申报 `sha1` 与本地字节不符时该 target 以 typed issue 失败，同批其余 target 照常完成；申报权利字段任一缺失时该 target 以 typed issue 失败，不以缺省值补齐。
- THEN `rightsStatus` 只由申报 license 字符串经开放许可白名单纯函数派生，ingest 清单中出现 `rightsStatus` 字段即 schema 拒绝；`watermarkStatus/watermarkKind/watermarkNote` 原样转录到资产行与 rights 行，缺省不得为 `absent`；release admission 把 `present` 的资产汇总为 `watermarkedAssetIds` 且不据此排除任何对象。
- THEN 同一 ingest 清单重放得到逐字节相同的 source unit 与 source refs；不同 execution 的相同来源文件在 content library 只持有一份字节。
- THEN `sourceUrl` host 为 `www.baike.com` 的 page 来源登记为 `sourceClass=encyclopedia`、`sourceId=toutiao_baike`，homepage 事务据此投影 `sourceKind=toutiao_baike`/`extractor=toutiao_baike_html`/`policyRevision=encyclopedia-primary` 并通过 publish entity schema；`discoverySignals` 原样进入该 source unit 的 `meta.json`，不进入任何判否。
- THEN 来源行申报的 `accessPolicy` 原样进入该 source unit 的 `meta.json` 与资产行且闭集之外的取值被 schema 拒绝；未申报的来源行其 `meta.json` 与资产行不含该字段且不被补为 `open`；publish 事务把资产行的 `accessPolicy` 转录到 canonical 资产记录，release header 把取值非 `open` 的资产汇总为 `accessRestrictedAssetIds` 且不据此排除任何对象。
- THEN 宿主用 yt-dlp 合并的本地视频可声明 `directUrl=null`，但必须提供真实元数据摘要与选中格式列表；acquire 保留取得事实及 null 直链，资产署名回指作品页，不把作品页伪装成下载直链。图片、缺合并事实或非法元数据摘要仍被 schema 拒绝。
- THEN page 可显式申报既有 `extractor` 方法，acquire 原样冻结到 source meta，homepage 主源与来源目录采用该事实；宿主读取网页正文的 `html_text` 不因 Wikipedia 域名变成 `wikipedia_api`。该字段不改变百科闭集或主源资格；未申报时保持既有站点方法约定，已冻结 source unit 的方法不得通过重放改写。

<a id="gwt-038"></a>
### GWT-038 4.draft 逐对象短缺、质量评分透传与里程碑事实版本化

- GIVEN 一个 execution 的 `4.draft` 中同时存在合规产物、tagRef 不在 taxonomy 的产物与空产物；reviewer 的判断输入对部分对象附带 `qualityScores`（六维 1–5）与 `qualityNotes`，对其余对象不附带。
- WHEN 依次运行 `task seal --stage 4.draft`、`task seal --stage 5.review`、逐对象 `release publish-object` 与 `release finalize`。
- THEN `002-4.draft` receipt 为 `pass`，resultRefs 只含合规产物，`typedIssues` 逐条点名违规对象与原因码，两条违规同时报出而不是只报首个；零合规产物时 receipt 为 `blocked`。
- THEN `5.review` 判断输入的覆盖集合必须恰为 `002-4.draft` resultRefs 的对象集合：多出退轮对象或漏评合规对象均 fail closed；退轮对象没有 `content_review.json`，publish 对其结构化拒绝。
- THEN 附带评分的对象其 `content_review.json` 原样含 `qualityScores/qualityNotes`，未附带的对象不含该字段且不被补零；`qualityScores` 的维度名或分值超出闭集时 schema 拒绝；评分取值不改变 `decision`、admission、pool eligibility 或 cohort。
- THEN `release finalize` 将现有 cohort/handoff 保存到独立内容仓，所选对象/版本/包摘要与定位快照绑定实际字节。
- THEN 两份 terminal 事实按 create-or-same 重放，相同接受而漂移拒绝，旧原件不被覆盖。
- THEN `handoff-verify` 只读 exact release 输入，不隐式从历史副本修复输出，不要求新增两次提交，也不把未匹配的内容 commit 当作实际快照。

<a id="gwt-039"></a>
### GWT-039 载体工具隔离与原生作品分组

- GIVEN image 来源返回同作品两张同描述图片，homepage 来源包含同实体维基骨架、百科补充与一个同名人物反例。
- WHEN 宿主调用点名载体的 Skill 工具并通过现有 init、acquire、author seal 与 publish 投影。
- THEN 一个原生作品产生一个 target 与有序多资产，逐图说明按资产身份无损经过 manifest、importer、API decoder 与 App 展示，同名文件不覆盖；未知说明引用或别名冲突在 author 校验拒绝，未声明逐图说明时不伪造该字段。
- THEN homepage 显式主源只能引用本对象已取得的百科来源，源列表置换不改变该选择，catalog、实体头与归属一致；同名人物反例供 AI 消歧，空章节与长度只产生 advisory，不替 AI 判断实体正确性；其 author schema 不依赖 image 私有字段。
- THEN 只加载被点名载体/来源；读取候选、原始响应、底稿或下载缓存前即验证载体归属，跨载体相同身份可独立取得但不可搬用私有证据。候选跨页重叠按原生身份及 revision 合并，同身份内容冲突拒绝，不能因响应位置不同生成第二作品。
- THEN 预览优先使用摘要核验后的本载体原件，远程缩略图仅用于显式发现模式；按身份与摘要复用并标明实际尺寸及来源，重排不串图，分页释放内存，图片像素只服从既有 Data 政策。
- THEN 宿主显式给出页数、频道条数与传输预算；下载有界分块并增量计算摘要。普通单资产失败不取消后续独立资产，限流或挑战停止该站点但不取消其他站点；聚合结果真实报告部分失败，不自动生成 approved。
- THEN 原始响应先 create-or-same 留存再解析，坏响应亦可追溯；selection 可凭精确证据补充或纠正逐资产作者及许可而不覆盖原始上传账号和响应，混合许可不被来源级声明掩盖。
- THEN author 前检查 canonical 身份占用、资格与依赖，invalid 不当作 absent 或已完成；发布前重验引用闭包及作品唯一性。同轮 homepage 失败不使其依赖帖子冒充 eligible。
- THEN 原始来源、选择与下载事实分离，reviewer 只写现有 execution 级 seal 判断输入，CLI 单写逐对象 review；不新增 actor authority、执行台账、seal/publish 包装或第二调度器。

<a id="gwt-040"></a>
### GWT-040 真实行政链与简单容量分区不改变对象语义

- GIVEN 普通区县、仅证实到市、直辖市、跨区域地点及 posts，另有同名组、Unicode 冲突与缺失仓身份反例。
- WHEN 初始化显式身份并在独立内容仓按已声明容量发布，重复发布已有组并使新组超过当前分区容量。
- THEN 地点只在主地域真实层级/现有类型下有一个落点，其他地域仍可查询。posts 不按地域复制，非地点 producer 未扩建。
- THEN 仓身份缺失/不符与名称冲突阻断，不猜行政层级、不静默合并名称或回退旧根。
- THEN 非空分类始终带首分区，已有组不拆不搬，新组仅按条目数与逻辑字节选可容纳的最低归一化负载分区，平分按编号、无容量才开新区，超大组只报告例外。
- THEN 删除可重建 inventory 后对象与同名组原分区归属不丢，普通 publish 不自动跨地域均衡。

<a id="gwt-041"></a>
### GWT-041 精简对象包保留真实来源、审核与入池事实

- GIVEN 四载体独立审核后的对象包含采用来源、真实证据与最终媒体，另有旧审核原件和追加式 pool records。
- WHEN 同一单对象事务生成新包、复制到无原 execution/library 的目录并由 importer 消费，另注入来源缺失、引用逃逸或第二份矛盾投影。
- THEN manifest 单写身份、正文引用、有序媒体与主体依赖，homepage/article 另有唯一最终正文而 image/video 无伪正文，来源事实与必要原件随体，完整复制后不依赖原 execution/library 消费；正文图片按已验证资产身份同步投影到包内媒体路径，只替换引用位置，不改写文字或原审核，未知或歧义图片引用阻断。
- THEN 重复 refs/source catalog/rights 旁车不再读写，消费者只从唯一 manifest/source 投影归属，缺证据或非法引用 typed 拒绝。
- THEN 原 review 结论/审核对象摘要与 records 原件可复核，迁移只追加 binding/新版本事实而不伪造重新审核，旧 release/receipt 与已保护媒体保持原字节。
- THEN finalize 的现有 cohort/handoff 以 create-or-same 保存，handoff 仅新增 `repositoryId`，工程 baseline/实际契约摘要与既有 release/object query digests 绑定 exact 快照；无新增 objectPath 表、`contentRevision` 或 `layoutVersion`，不要求内容提交或双提交，不隐式补库。

<a id="gwt-060"></a>
### GWT-060 摄影图片与视频无地点时仍可保存和分发

- GIVEN 有真实来源、媒体和独立审核的摄影图片或视频未确认拍摄地点，另有完整地点身份作品和半填身份反例。
- WHEN 沿相同init、取得、创作、审核、publish、显式cohort及离线投影处理。
- THEN 无地点作品保留题材或摄影标签和空实体关联，不填假地点；公共投影省略可选主页锚点，作品和媒体可被消费。
- THEN 有地点作品继续严格校验实体闭包；半填身份、伪造依赖、来源/媒体漂移与重复作品均拒绝，不因无地点跳过审核或完整性。
- THEN homepage与article原身份约束不变；image与video共用同一可选地点规则；未知地点不推断省市区；重放不新增作品，四载体里程碑计数保持唯一对象语义。

<a id="gwt-047"></a>
### GWT-047 视频兴趣标签按消费者题材与观看价值解析

- GIVEN 图片与视频可引用同一批已声明 `consumedBy` 的自然风光、动物行为、城市题材叶子，以及已声明消费的摄影教程叶子。
- WHEN 作者为日照金山、燕鸥求偶、古镇夜景、海边旅行与摄影学习选择 `tagRefs`。
- THEN 上述查询解析到已声明 `consumedBy` 的共享题材或摄影教程叶子，描述不含光圈、快门、ISO 或构图术语。
- THEN 不存在视频专用重复题材路径，也不存在观赏、风景欣赏、昆虫、两栖动物或淡水鱼空目录。
- THEN Topic 一级目录共 39 个，其中 36 个有本层定义可作为 `tagRefs`；场景、时间、地理是含后代的目录根，不是本层可选标签；雪山定义覆盖冰川用语。

<a id="gwt-048"></a>
### GWT-048 文章发现查询复用现有标签，不扩地貌营造体裁目录

- GIVEN 图片与视频已声明 `consumedBy` 的共享题材叶子存在，文章可引用同一批题材及现有旅行/攻略/科普叶子。
- WHEN 读者查询南迦巴瓦日照金山、燕鸥求偶、周末古镇公共交通、陈家祠观看、带长辈游园与住宿比较。
- THEN 上述查询解析到已有 Topic、Entity 或 Format 定义，不新建 Intent 轴或文章分类树。
- THEN 不存在冰川地貌至民居营造等拟增主题叶子，也不存在散文、随笔、访谈体裁叶子；`Topic/历史文化/建筑艺术` 保持无子标签定义。
- THEN `Format/内容角度` 描述不硬编码视角个数；现有 15 个角度父节点仍可解析。

<a id="gwt-061"></a>
### GWT-061 原作证据与媒体用途在渲染变化时保持隔离

- GIVEN 已保存真实响应或明确摘录的原生多图作品、图文页、转载预览与视频，内容区包含封面、配图、参考链接，页面另含未采用图标及推荐图。
- WHEN 宿主明确原作范围与有序采用项，经零网络取得、审核成品保存及目标分发投影，再改变目标渲染实现并注入缺图、错序、证据漂移或未知用途。
- THEN 四载体引用同一原作记录定义，真实原响应/摘录/凭据的类型、摘要和取得范围贯通；部分或未知范围不被改为完整，原作身份与采用成员能回查证据。
- THEN 同一原生图集只保存一个作品并保留原序，封面可引用同资产而不重复轮播；正文配图位置与说明、视频poster关系和参考链接保持对应，未采用图标/推荐媒体不进入交付闭包。
- THEN 缺字节、重复成员、断开引用与证据漂移明确拒绝；改变目标投影不改变原来源、成品及review摘要，无法表达的必要结构不静默平铺或丢弃，原站不可访问不影响已完整保存的成品消费。

<a id="gwt-042"></a>
### GWT-042 实体失效与媒体故障不破坏已可读作品

> 下游边界验收，不是 producer 完成条件。

- GIVEN 一个真实导入的文章引用两个同名异地实体，另有图集和视频；目标页分别返回正常、永久下线、权限拒绝或带 offline 状态的历史 View，媒体包含局部失败。
- WHEN typed query 读回后渲染并点击实体，滑动图集、播放视频及重复 rebuild；原来源网站不可达。
- THEN 文章 mention 使用既有 Entity exact 映射指向正确主页，缺映射呈普通文字，非文章保持 label 而不泄露内部路径。
- THEN 渲染不按引用数增加请求，点击服从原目标可见性与返回，普通下线不改作品、原文或已采用媒体。
- THEN 封面/正文图局部占位且保留文字，图集坏页保留顺序/页码并可继续滑动，来源站失效不影响随体成品。
- THEN 视频失败保留可用 poster/caption 并有界停止，已知永久缺失不自动重试，poster/字幕单独失败不阻断可用视频。
- THEN 图集加载跨实例复用既有负缓存，视频缓存命中不延长原 TTL 或重新触发恢复，无逐实体/逐图探活或后台自动修复。

<a id="gwt-045"></a>
### GWT-045 百科 exact revision、faithful adaptation 与文章独立性同轨验收

- GIVEN 同一 Wikipedia 页面两个 revision 的 wikitext/Parsoid HTML 交叉组合、一个忠实 homepage adaptation、一个改变限定语义的 homepage 改写、两篇只改标题/`publishAngle` 的单实体百科文章，以及 unknown schema/dialect major、canonicalization mismatch、required capability missing 四类协议兼容输入。
- WHEN producer 映射 semantic document、执行 author self-check、independent review、publish 并由多端读取。
- THEN 只有同一 exact revision 的 wikitext + Parsoid HTML 可形成 sourceRevision；交叉 revision 与 latest 漂移 typed fail closed，旧 sourceRevision 仍可精确读回。每个对象同时携带独立的 protocol triplet 与 object tuple，任一组不能从另一组推导或省略。
- THEN unknown schema major、unknown dialect major、canonicalization mismatch 与 required capability missing 分别 typed fail closed，且 object tuple 有效、人工选择或 renderer fallback 均不能代偿。
- THEN faithful homepage 在各端及不同 viewport 保持同一节点集合、内容结构、事实、归因、表格分类和阅读顺序；`layoutRevision` 只改变同一统一规则允许的尺寸、换行、滚动或线性化，改变限定语义的版本产生可定位 disposition 且不进入 publish。
- THEN 两篇单实体百科改标题/角度的候选被判为同一语义对象，第二篇不能以新 publishAngle、contentId 或 layoutRevision 取得独立文章资格；真正独立的问题/路线/时间窗口或多来源论证候选才可进入新文章 review。
- THEN 工作台可展示上述 exact tuple、diagnostic 与人工建议，但不能改变判定；人工修订必须生成新 tuple 并重新 review 后才可能发布。
<a id="gwt-049"></a>
### GWT-049 团队模板可私有复建且初始化不启动生产

- GIVEN 一份无账号身份的四类岗位模板与可粘贴简介已写入 content-production 手册，创作者/QA 可有多个实例，独立 QA 为常设职责。
- WHEN 运营者按该模板在另一账号核对角色、群成员与知识引用。
- THEN 模板不含 Bot UUID、账号凭证或旧 runId。
- THEN 初始化话术声明不启动生产、不启用 Routine。
- THEN 重复按同一模板核对时不要求新建重复角色。

<a id="gwt-050"></a>
### GWT-050 岗位资质不构成已绑定高能力模型的证明

- GIVEN 岗位手册要求总监与创作者按行业顶级专业标准工作。
- WHEN 当前宿主公开能力不提供模型选择器。
- THEN 写入专家资质不得被解释为已绑定更高能力模型。
- THEN 团队不得宣称已满足严格高能力模型匹配并全面无人值守接管。

<a id="gwt-051"></a>
### GWT-051 多账号分片并行在宿主前提未证时保持阻断

- GIVEN 两个账号绑定同一 Skill 版本与同一 canonical 内容仓。
- WHEN 运营者请求分片并行。
- THEN 未取得同时本机连接与不重叠对象范围证据时并行保持阻断。
- THEN 轮换模式下旧队停止同片新增，原调用终态、在飞写者与 exact release 已核后，新队才可认领；10 分钟检查不构成全队暂停窗，失联或 TTL 到期不构成抢占依据，unknown 只冻结冲突范围。

<a id="gwt-052"></a>
### GWT-052 具名分片在授权轮次内原子认领并安全释放

- GIVEN 当前 `deploymentId/generation/globalIteration` 已冻结对象范围不重叠的具名 shard，四类岗位及实例 deployment、独立 QA、总预算及逐 shard 预留均有效；另有 generation 漂移、预算不足、旧 nonce、失联与前任清理未明反例。
- WHEN 宿主核实在飞写者与前任交接后，在已授权范围对 `available` shard 原子认领，生产停止后进入 `draining` 并以 exact claim nonce 显式释放，同时重放同一释放。
- THEN 每个唯一键至多一个 `claimed` winner；只在已授权 iteration 与预留预算内发生 `available -> claimed`，自动认领不创建 shard/iteration、不选择候选、不解释 receipts 选择后继或签发完成、不扩大 publish 或清理授权。SQLite transition 与预算引用可审计，但删除该库不改变任何对象、execution、review、publish、release 或 handoff 事实。
- THEN exact 释放与同输入重放得到同一终态，错误 nonce/generation/state 零写；失联、十分钟无写入、TTL 到期、进程退出或账号切换均保持原 claim，不触发抢占。观察结束仍未知、预算不足或前任清理归属不明时 shard 显式 `blocked`。
- THEN 后继只读审计前任 transition/receipts/产物/预算释放后才可认领，只清理本 claim 明确创建且不受保护的临时字节；前任未确认终止的产物、canonical pool、handoff、library/golden/随体媒体与外盘副本均不被后继清理。
- THEN M100000 只有显式 cohort 的 homepage/article/image/video 各至少 `100000` 个累计唯一 finalized 对象并形成独立 release/handoff 时达标；十团队数量、claim 数、轮次数或媒体文件数都不能代替该计数。

<a id="gwt-053"></a>
### GWT-053 作者与独立 QA 自主整批交接，慢批不形成屏障

- GIVEN 同一已授权图片目标 100 作品已拆为 20 个五作品 execution，至少两作者与两独立 QA 有可读相同任务版本、有效归属与预算，其中一作者或 QA 的慢批仍在原生运行。
- WHEN 作者各自完成本人 execution init/acquire/author seal，整批直接交接，QA 自主领取不同已就绪批并自行 review seal，总监消费已 approved 对象。
- THEN 每 execution 只有一个 author 主会话和另一个 reviewer；QA 覆盖恰为 author receipt 的有效 resultRefs，多出或漏评拒绝，不自审、不改已封存稿，图片原图与视频画面/音轨有真实核查证据。
- THEN 正常路径只有作者整批→QA、QA 整批结果→总监两次关键交接，普通选题/开工/续领不经总监逐项批准，作者无须等消息确认；同 execution 不能有多个 reviewer 同时写入。
- THEN 独立快批可 seal/publish/readback 并在容量允许时跨已授权窗口续领，不等慢作者/慢 QA 或 100 作品齐套；95 个合格只能报 95，失败替补不得超出授权候选/补量范围。
- THEN 总监唯一执行获准 publish/finalize/Git，只核机械发布条件，不重审内容或代跑所有作者/QA 命令；未获发布授权时保留待发布，不能伪造成功或靠 review 通过释放容量。

<a id="gwt-054"></a>
### GWT-054 原子归属、在制上限与真实写围栏共同拒绝越界

- GIVEN 同一 deployment 的一个 active shard 内有多个不重叠 execution，同批/同 review scope 存在竞争认领，某作者已有两批未闭合且一批正在创作；另有缺围栏、旧 generation、跨 actor/target 与非总监发布反例。
- WHEN 并发认领作者/review scope、申请续领或关闭批次，并调用真实 init/acquire/seal/publish/finalize 写入口。
- THEN 归属与容量在同一短事务原子核验，同一小批和 review scope 各至多一个 winner；每作者最多两个未闭合且最多一个创作，失败认领无残留占用，不能靠新 deployment 或 init 成功绕过。
- THEN 送审、审核中和待发布仍占端到端名额，只有全部有效对象成功 publish/readback 或按契约明确终止且核完在飞写者才释放；unknown、TTL、退出登录或 review 通过不释放，重复关闭幂等，漂移零写。
- THEN 缺失/失效围栏、旧代、错 actor/target、作者写 review 或非总监 publish/finalize 均在正式业务写前拒绝，包含省略环境变量的负例；其他不冲突合法 scope 仍可写，同站和全局资源预算不因增加 Bot 放大。
- THEN coordination 只保存归属/预算硬事实并机械核验正式证据绑定，不持久化另一阶段状态或完成清单，不解释 receipt 选择后继、自动恢复或授予 actor；删除协作库不改变 receipt、对象、publish proof 与 handoff。

<a id="gwt-055"></a>
### GWT-055 共享有效任务版本与角色写 scope 分离

- GIVEN 总监已在用户授权内确认方向、预算和生效范围并保存当前任务版本，四类角色均具各自写 scope；另有权限缺失、旧版本和紧急撤权负例。
- WHEN 全角色读回任务、占用、资源预算、receipts、QA/publish 证据和异常裁定，再认领、提交或执行正式写。
- THEN 所有角色读到同一有效版本及必要证据，不依赖总监私聊转述；普通范围内决策自主，扩大人类授权仍拒绝或请求用户，凭证/令牌/无关隐私不可读。
- THEN 全员可读不授予他人 scope 写权；过期版本、当前必要事实不可读、越权或撤权在受影响正式动作前阻断，其他健康任务继续，不以消息已读、旧记忆或缺省授权代偿。
- THEN 确认变更先保存再通知，受影响角色下次认领/提交核新版本，在飞 actor/历史授权不追溯改写；无真实总监确认与四角色读回时只报告仓库规则/本地测试，不宣称团队重组已生效。

<a id="gwt-056"></a>
### GWT-056 总监主动检查有裁定，unknown 不抢占

- GIVEN 原生宿主提供已核实的通知/状态读取/检查触发能力，或明确缺少自动唤醒；注入普通输入失败、已知终止、unknown、无人接审、发布积压、检查失效及额度耗尽。
- WHEN 总监按约 10 分钟增量检查，异常立即报告，连续两次无法解释等待或超过实测正常周期时定向核状态。
- THEN 首次发现记录问题、owner、下一动作与下次检查；下一检查仍未解决/解释时形成授权内修复、终态接续、工程升级、用户裁定或有 owner 的 blocked，不只重复催问，不全池重扫或全员同步汇报。
- THEN 同类确定性输入错误再次发生停止盲重试，长视频/转码按实际预期保持运行，10/20 分钟不作取消门槛；已知终止恢复只由唯一 owner 按既有契约接续，已封存字节和真实 actor 保留。
- THEN unknown/账号或总监额度耗尽保留原 claim 和证据，只冻结冲突写，安全独立任务可继续；不以 TTL/mtime/进程退出抢占，不保证未知调用已恢复或无预算仍能最后交接，必要时由用户接管。
- THEN 检查单个非重入且不启动新生产调用，Routine 需独立授权；无原生唤醒则明确人工唤醒并保留阻断，只证明识别/通知不得报告恢复或无人值守通过，无 native 时间不填等待数据。
- THEN 同一检查按 `Asia/Shanghai` 每个完整小时键最多发送一次上一小时群报；重复 tick 不重发，迟到事件带补报时间归入原小时，群发送失败保留原生失败回执。无基线、Mac 不可达、读取失败或事件范围不完整均为 unknown 而非零。
- THEN 群报逐载体分列 author、QA 三种终态、首次入池、eligible 净变化及最老积压；修订、恢复资格、身份归并和退出不冒充新增。图片/视频任一零增量即附原因、owner、下一动作和下次检查，连续两完整小时仍为零或阻断未解必须形成解阻/缩批、工程升级、用户裁定或有 owner 的 blocked。

<a id="gwt-057"></a>
### GWT-057 A/B/C 重组保护在飞身份且读回实际生效

- GIVEN 团队分别处于 A 新建、B 已证实空闲、C 有任务或 unknown，且已明确宿主支持入口与必要授权。
- WHEN 按同一四类岗位规则配置或原位更新，核共享版本、角色/工具/媒体链、活动根及总监检查触发，并从实际宿主读回。
- THEN A 复用匹配 Bot 按授权补缺，B 先证无在飞/待接管再原位更新；均不自动生产、认领、启 Routine 或清理，不删历史或继承无效授权。
- THEN C 逐单元保留旧 scope/actor/receipts/版本，安全交接点后更新，新任务用同一新规则，不等全队同时切换、不改旧 receipt/冒名 seal/并行重派；unknown 保持范围与 owner，不留长期旧权限兼容层。
- THEN 三场景均读回四类角色可访问同一有效任务版本与真实生效配置；缺 Grok 管理、原生状态或更新接口时输出精确人工清单并 blocked，文件/简介修改不冒充活跃团队已更新。

<a id="gwt-058"></a>
### GWT-058 建议比例不判否，提效只报告真实唯一产出

- GIVEN 1:2:3:4 基础建议、最高 50 倍规划边界及明确总预算/目标/停止条件，存在热门实体多作品、冷门仅主页、无地点媒体和同原作拆图/改标题/新版本反例。
- WHEN 作者自主选题、比例已超额后继续获准生产，并用当前 pool/proof 与真实原生时间和成本比较有限试点。
- THEN 建议比例超额不拒收或停止，50 倍不授予费用/发布/扩候选权限；无热度证据标 unknown，无地点不造实体，同一实体只有一个稳定主页，扩主页来自更多真实实体。
- THEN 拆图/改标题/换版本不增加唯一计数，正式 M1000/M10000 数字保持现有 policy，M100000 仍需四载体各至少 100000 唯一 finalized 对象与独立 release/handoff。
- THEN 在同质量、载体和冷热缓存条件报告净 eligible 产速、周期、WIP、最老未闭合项、首审/返工与每合格对象成本，缺 native 时间就标未测，不预承诺翻倍；两作者、四作者与两 QA 的真实有界试点分别举证，规则测试、Bot 生效、生产净增和正式里程碑不互相代偿。

<a id="gwt-059"></a>
### GWT-059 来源指导与只读网站占比不代替质量验收

- GIVEN 点名的四载体来源样本，包括百科主页、专业/综合来源作品、同原作多图、多源文章、重复对象版本、无来源及CDN/许可URL。
- WHEN 创作者按来源指导选材，并在同根同阶段的明确对象范围执行只读网站统计。
- THEN 主页按 Wikipedia→百度百科→头条百科选择；其他三载体专业/综合同等优先，源码模块顺序不构成检索排名。未验证的平台能力、受限访问和原作关联不得伪称已取得。
- THEN 每对象每网站仅计一次，保留网站覆盖率和来源关联构成占比的不同分母；零对象与缺失来源不伪造百分比，图集/派生/重复版本不膨胀作品数。
- THEN 发现平台、作品页来源和原站沿革分开；聚合页、CDN、许可页、百科尾部引用不冒充实际采用网站；来源字段矛盾只报告，不隐式修复。
- THEN 统计默认无写入、无网络、无调度或完成裁定；样本仅代表所选范围，未看像素/完整视频音轨不能报告视觉或视听通过，低质量approved样本不得被包装成优质成果。
- THEN 宿主单阶段命令保留每次候选实际退出码，混合失败不抹去已成功资产、不登记余项为成功；视频同源小组首错停止，未执行项显式报告，由宿主决定下一动作，不自动重试。观察调用不捎带新生产，定位只读已知准确路径或有界范围；聚合探测的正常退出不代表所有候选成功。
- THEN 必需观察缺失保持 blocked；有声媒体未核听不得通过省略 audio_fit 获得 approved。已确认文案与真实媒体/来源矛盾由 QA 点名原句及证据交作者纠正，不只记 advisory；风格/片长/低分本身不成为拒绝门。QA 不改稿，总监不代审，封存历史不被该纠偏覆盖。

<a id="gwt-062"></a>
### GWT-062 legacy sealed release 受治理重物化为不同 current-schema handoff

- GIVEN 一个 source root、摘要绑定的独立 source repository identity evidence 与 legacy sealed release/cohort/handoff 相互匹配，source schema 位于 Data authoring source 明示支持的 legacy 闭集，membership 对象及原 `content_review`、canonical publish proof 均可 fresh readback。
- GIVEN 操作者提供不同且全新的 target `releaseId`、milestone、current producer baseline，以及现役入口绑定的真实 user authorization、完整真实 deployment、migration-only iteration/shard claim、唯一 director/global closer、current generation、四根 binding 与 exact cohort fence。
- WHEN 通过 `CLI -> governed_repackage_call -> fenced_governed_repackage` 执行一次性 current-schema repackage，并对 source、authority、并发锁、output candidate、publish terminal 与 readback 边界注入故障。
<a id="gwt-062.t1"></a>
- THEN 从 source sealed membership 与 canonical pool fresh readback 确定性重建 current-schema output release/cohort/handoff，重新计算 artifact entries、counts、object/query bindings 与 `treeDigest`，新 lineage 精确绑定 source repository evidence、release、handoff 与 cohort identities/digests。
<a id="gwt-062.t2"></a>
- THEN 独立 publish 仓 `releases/<newReleaseId>/` create-or-same 保存与 output current cohort/handoff exact bytes/digests 一致的 terminal copy，只有 output 与 publish 双 readback 均闭合才返回 producer success，output release 单独存在不构成 terminal success。
<a id="gwt-062.t3"></a>
- THEN 跨根写入固定先形成不可提升的 output candidate再写 create-once publish terminal，任一步失败或 readback 不一致都不签发成功，exact replay 可以从半闭合边界安全收敛到同一双根 bytes。
<a id="gwt-062.t4"></a>
- THEN unknown legacy schema、缺失或漂移的 source repository evidence、从 target repository 代填 source identity，以及 source repository identity unknown 均在写前 typed fail closed，普通 reader、finalize 与 verify 仍拒绝 legacy schema。
<a id="gwt-062.t5"></a>
- THEN source handoff/cohort/release digest drift 或 membership drift 分别保留首个 typed blocker并使新 terminal 不成功，旧 counts、entries 或 tree digest 即使表面可复制也不能代替 current canonicalization。
<a id="gwt-062.t6"></a>
- THEN canonical pool/package、原 review bytes 或 publish proof 任一 fresh readback 漂移均阻断，新 terminal 不成功且原 review/proof bytes 不变。
<a id="gwt-062.t7"></a>
- THEN current output/publish terminal 不含新 reviewer、attestation、execution、stage receipt 或 publish receipt，legacy execution 与 existing execution 的 actor、generation、receipts、release binding before/after 完全相同。
<a id="gwt-062.t8"></a>
- THEN target 不存在时经 staging 完整校验后 create-once，same target 加 same frozen input 加 exact same output/publish bytes 为 replay，已有 target 任一绑定或字节不同为 typed conflict。
<a id="gwt-062.t9"></a>
- THEN staging write、canonicalization、完整性校验、output publish、publish terminal write 或任一 readback fault 均不得报告成功或暴露可提升的半闭合 terminal，source terminal tree before/after digest 完全相同。
<a id="gwt-062.t10"></a>
- THEN authority 链实测拒绝非 director、非 global closer、stale generation、四根 drift、task digest/context drift、无真实 `confirmationRef`/`confirmedBy`、`allowedActions` 不含唯一 `repackage` 以及 fence 未 exact 覆盖 cohort，手写任意 JSON 不获得 authority。
<a id="gwt-062.t11"></a>
- THEN 真实已授权完整 deployment 可执行 migration-only claim，generic registration 不得靠伪造七角色或占位 actor通过，若 director-only migration deployment 尚无现役 schema/入口则保持 typed engineering gap。
<a id="gwt-062.t12"></a>
- THEN migration-only iteration/shard claim 覆盖 legacy cohort target refs且不创建 batch scope，unset `QWQ_CONTENT_BATCH_NONCES` 仍成功，legacy/existing execution 不被 claim 或 rebind。
<a id="gwt-062.t13"></a>
- THEN coordination DB 为空或无 batch row不代表无其它写者，跨 iteration target occupancy、现役 native writer 或 release lock 冲突均在业务写前 fail closed。
<a id="gwt-062.t14"></a>
- THEN 失败或取消只清理未发布 staging，source 与成功 output/publish terminal 保持 immutable。成功结果不再采用时仅经现有受治理 retirement/保护集处置且能力缺失时继续保留，不以 `rm` 或删除 candidate 作为 rollback。recovery 只允许 same-input exact replay或使用另一个不同于 source/candidate 的全新 rollback/recovery release identity，结果只报告 source/new identities、digests、双根 readback 与首个 blocker且不建立 ledger、dual-read 或 legacy fallback。
## 6. 依赖

- 前置要求：父能力的 execution、review 与 release 契约。
- 上游事实：来源、目标集和审核结果。
- 下游结果：immutable release 或结构化阻断报告。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-037"></a>
### OPEN-037 视频消费者标签的真实作品读回与推荐效果待验证

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺真实视频 `tagRefs` 经 author、独立 review、publish 与下游检索或推荐的读回证据，也尚缺排序质量证据。
- 尚缺实现：未声明 `collectionChannel`/`consumedBy` 的 Format 内容角度若要进入正式消费，须由 taxonomy owner 补声明；本增量不改那些共享定义。
- 尚缺验收证据：[`GWT-047`](#gwt-047) 的真实视频读回、跨载体同一题材召回、负反馈边界与授权环境消费；标签存在或 `consumedBy` 声明不替代上述证据。
- 完成判定：[`GWT-047`](#gwt-047) 由真实视频 author、独立 review 与 publish 读回绑定，搜索命中与推荐效果分别由对应 owner 举证。
- 依赖：本节点 [`GWT-047`](#gwt-047) 映射合同；下游 Tag、Search、Feed 与 Environment Ops scheduler。

<a id="open-031"></a>
### OPEN-031 文章标签到 tag-service/App 的环境消费待验证

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：文章发现查询的静态映射与 Data seal 解析已可本地验证，尚缺同一 release 经 tag-service 导入、`ValidateTagRefs` 叶子校验与 App 既有 chips/search 的授权环境读回。
- 尚缺实现：无新页面或新分类树；Format 内容角度未声明 `consumedBy` 时仍只作创作提示。
- 尚缺验收证据：[`GWT-048`](#gwt-048) 的 tag-service 导入查询、active leaf 拒绝父节点、以及 App 既有入口命中/误匹配；静态目录存在不替代检索与推荐效果。
- 完成判定：[`GWT-048.t1`](#gwt-048) 至 [`GWT-048.t5`](#gwt-048) 的静态映射由 Data local_contract 绑定；tag-service 导入、`ValidateTagRefs` 叶子校验与 App 既有 chips/search 读回由对应 owner 在授权环境举证。搜索命中与推荐效果不由本 OPEN 的静态测试关闭。
- 依赖：本节点 [`GWT-048`](#gwt-048)；下游 Tag、Search、Feed 与 Environment Ops scheduler。

<a id="open-029"></a>
### OPEN-029 载体工具重构与多源作品投影待验证

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺载体工具与多源投影的全部准出证据，离线回放不能证明外部来源持续可达、真实宿主渐进加载或消费者逐图说明展示。
- 尚缺实现与证据：来源工具、多图说明与同名投影、显式主页主源绑定及 acquire 后只读身份预检已有实现；Service→App 逐图 caption 映射已进入工作树，仍须以最终契约回归和 fresh runtime 展示证明，不把实现存在等同下游验收。
- 尚缺验收证据：[`GWT-039`](#gwt-039) 已有子句级 local_contract 绑定，上下文预算、Skill 手写源码分类、图片稳定引用/重复作品/身份漂移与主源投影回归已收敛；仍缺迁移后真实宿主小轮、跨层消费及当前候选正式准出证据，不能以离线回放替代。
- 尚缺验收证据：摄影图片与视频无地点路径的 [`GWT-060`](#gwt-060) 须由Data输入、发布/分发与离线投影的联合测试绑定；现有公共可空主页字段不单独证明生产链已经支持。
- 完成判定：[`GWT-060`](#gwt-060)、[`GWT-061`](#gwt-061) 与 [`GWT-039`](#gwt-039) 子句级测试、现有 producer/consumer 合同回归、上下文与 Feature Tree 门禁在同一增量通过；旧配方与有效引用完成删除替换。
- 依赖：Data author schema、既有 canonical 包与 actor 契约；对象包瘦身继续由 [`OPEN-025`](#open-025) 拥有。

<a id="open-019"></a>
### OPEN-019 旧编排证据删除后的 producer 复合验收仍待重建

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前仍缺 identity-only candidate、宿主原生执行、中断重入、AI 单写 stage 语义、单一 draft/review artifact、content-library 后半段闭包、载体证据形态和百科结构化事实的现役 producer 验收证据；legacy-delete 删除的正向测试与历史 receipt 不得继续计数。
- 尚缺实现：无；本项不恢复已删除能力，只跟踪现役 producer 行为证据。
- 尚缺验收证据：上述 producer 行为均需由当前 Skill + AI Agent 路径重新绑定；production 环境消费、UAT 与 EAF 属下游 owner，不纳入本 OPEN。
- 完成判定：[`GWT-001`](#gwt-001)、[`GWT-009`](#gwt-009)、[`GWT-010`](#gwt-010)、[`GWT-011`](#gwt-011)、[`GWT-020`](#gwt-020)、[`GWT-022`](#gwt-022)、[`GWT-024`](#gwt-024) 与 [`GWT-025`](#gwt-025) 的 producer 子句由现役 local_contract/api_integration 逐条绑定；反向门禁本身不替代行为证据。
- 依赖：producer 只允许 task init/acquire/seal、单对象 publish 与 release finalize；不得恢复已删除 API 补证据。

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
### OPEN-012 seal 内核契约的复合验证

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：seal 内核（三份 receipt 连续前缀、review 机械字段补齐、author≠reviewer、资产摘要漂移拒绝）已由 `quwoquan_data/tests/local_contract/execution/test_six_step_seal__kernel__contract__local_contract_test.py` 锁定，但仍缺同一 revision 上零旧 import/reference 静态门与该 local_contract 联合通过的记录，以及 M10 及以上多 target execution 的 seal 复合验证证据；局部机制通过不得冒充 producer 六步闭环。
- 当前证据：seal targeted local_contract 已绑定 [`GWT-020.t1`](#gwt-020) 与 [`GWT-020.t2`](#gwt-020) 的内核行为；这只证明局部机制，不等于 producer 六步/publish/release handoff 或下游环境消费的 fresh 复合 E2E。
- 尚缺实现：无；seal 内核已落地，本项只跟踪复合验证证据。
- 尚缺验收证据：同一 revision 上零旧 import/reference 静态门与 seal targeted local_contract 联合通过的记录，以及 M10 及以上规模下多 target execution 的 seal 复合验证。
- 状态语义：本项仅声明删除后的实现与证据要求，不表示一组局部测试已经证明完整执行闭环。不得保留旧实现作为过渡兼容。
- 完成判定：[`GWT-020.t1`](#gwt-020) 与 [`GWT-020.t2`](#gwt-020) 的 targeted local_contract 和零旧 import/reference 静态门在同一 revision 上均实际通过；producer 复合 E2E 由 [`OPEN-020`](#open-020) 跟踪，下游消费证据另由 [`OPEN-006`](#open-006) 跟踪。

<a id="open-020"></a>
### OPEN-020 producer 六步与累计里程碑 release handoff 证据待取得

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：authoring contract 已硬切，但仍需真实 producer execution 证明 identity-only candidate、单一 draft/review artifact、逐对象 publish、累计 cohort release 与 terminal handoff 端到端成立。
- 已冻结语义：producer 六步止于 `release finalize` 并拒绝消费阶段；candidate binding 不要求 pre-init source admission；`002-4.draft`/`003-5.review` receipts 分别冻结 execution 级唯一 author/reviewer actor 与 invocation；`4.draft`/`5.review` 每对象各一份业务产物；approved/rejected 可混合且短缺不扩展 receipt verdict。
- legacy sealed release 重物化语义已由 [`REQ-030`](#req-030)、[`GWT-062`](#gwt-062) 与父设计 `DEC-050` 冻结。Data current-schema schema/command、output→publish terminal 双根 readback、source repository evidence、正式 task authority、migration-only claim、真实 roster、native writer/release lock 排他与受治理 retention 尚未整体闭合；现有实现/测试残留、手写 task JSON 或 output release 均不得冒充完成。
- authority 实现缺口：现役入口必须由 schema 绑定真实 `confirmationRef`、`confirmedBy`、唯一 `allowedActions=repackage` 与 user authorization ref；需证明复用真实已授权完整 deployment 而不伪造七角色，若需要 director-only migration deployment 则须先补 canonical authoring source/入口。migration-only iteration/shard claim 应覆盖全部 legacy cohort refs、不使用 batch nonces、不 claim/rebind execution，并在 DB 为空时仍核现役 native writer、跨 iteration occupancy 与 release lock。
- terminal/lineage/retention 缺口：publish 仓 `releases/<newReleaseId>/` 尚须 create-or-same 保存与 output exact 一致的 current cohort/handoff，并以 output candidate→publish terminal→双 readback 作为成功边界。legacy wire 无 repositoryId 时须取得摘要绑定的独立 source repository evidence，不得以 target repository 代填。成功 source/new terminal 均保留 immutable，只允许清理未发布 staging，后续不用的成功 release 只能经现有 retirement/保护集处置。
- 尚缺验收证据：[`GWT-062.t1`](#gwt-062) 至 [`GWT-062.t14`](#gwt-062) 须逐项由 Data current implementation 的 local_contract/api_integration `spec_ref` 与实际运行绑定，覆盖 deterministic rebuild/lineage、双根 terminal/readback、unknown source repository、source/pool/review/proof drift、无伪造事实、create-once replay/conflict、fault injection、完整 authority/task/roster、unset batch nonces、existing execution 未 rebind、跨 iteration/native writer/release lock 冲突及 retention/recovery。历史 handoff、当前 schema fixture 或局部测试通过均不关闭该缺口。
- 里程碑语义：M1/M10/M100/M1000 按 `cumulative_unique_finalized_objects` 计数，每级形成自己的 full explicit cohort、release 与 handoff；更高级别复用 canonical 对象及其 canonical publish proof，不伪造新 receipts。运营生产目标为四载体各 1000、再各 10000（图片按唯一原作计）；正式 policy 视频底线仍为 M1000=`100`、M10000=`1000`，超出底线的视频不改变 milestone 判据，也不因底线达标提前停止运营目标。任何旧 schema 字面上的额外 milestone 不扩大本 OPEN 的验收闭集。
- handoff 边界：handoff 严格绑定 release/cohort、四载体 counts、逐对象 content-pool query（canonical publish proof）、`producerBaselineRevision`、`producerContractDigest`、`repositoryId` 与 create-once identity；不包含 UAT sample authority、import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback facts。
- 当前证据：六步路径已取得 M1/M10/M100 三级真实 producer E2E，均为 author 与 reviewer 不同会话、`release finalize` create-once handoff 且 `handoff-verify` 只读重放通过——M1 release `20260906--travel-research-m1--six-step-tangqi-001`（塘栖古镇 `1/1/1/1`，来源 zh.wikipedia + Commons）；M10 release `20260906--travel-research-m10--six-step-cumulative-001`（`10/10/10/2`，`producerBaselineRevision` `d5226a78acafc940887429d95515d1f611af4d75`，复用 M1 canonical 对象）；M100 release `20260906--travel-research-m100--six-step-cumulative-001`（`100/100/100/10` 共 310 对象，`producerBaselineRevision` `6f826e461128255e1bb4f2a585c96bc7152d657e`，从累计已发布 104/103/104/11 canonical 对象中显式选出，复用 M1/M10 对象与其 canonical publish proof，未伪造新 receipts）。
- 尚缺验收证据：M1000（不低于 `1000/1000/1000/100`；运营生产目标为四载体各 1000，视频超出底线的部分不改变里程碑判据，实体前沿按 [`REQ-003`](#req-003) 口径开放不设上限）按累计唯一对象形成独立、无类别选择的 cohort/release/handoff 的证据；历史 r03 `release pool-query` 曾记录 eligible 141/149/130/14（该计数只适用于当时契约，不是当前新 reader 的资格；当时已排除 [`OPEN-021`](#open-021) 实体闭包；零网络 ingest 契约下的真实轮次 `sichuan-r01`、`recover-r02`、`national-r03` 以子 Agent author 与独立 reviewer 走通，其中 `national-r03` 一轮四 execution 发布 24/24/20/5 个对象、含 5 个头条百科主源实体，每个 `content_review.json` 携带六维 `qualityScores`，1.download/4.draft 逐对象退轮各在真实 execution 中出现一次以上），当时里程碑缺口约 859/851/870/86。当前占位、缺失依赖与迁移后有效计数按 [`OPEN-021`](#open-021) 重算，不沿用历史数字。已封存冒烟 release `20260906--travel-production-smoke--six-step-h06-001`（cohort 5/1/4/2 ≥ M1 目标，media_manifest 仅 `publicSliceKey`，原契约 `handoff-verify` 通过，含 Commons 超预算 webm 转码 mp4 的两条视频）及 M1/M10/M100 三级 release 只证明各自封存契约，既有通过事实、原始字节与身份保留；它们不能证明 [`REQ-002`](#req-002) 的无类别默认链路，也不得改摘要或补字段后冒充现役 handoff。无类别 release/handoff 须重新生成并通过当前 `handoff-verify`，M1000 按新对象包契约累计覆盖全部合格唯一对象。视频缺口的成因是发现方法（未沿 Commons `Videos from <地区>` 类目树检索）与 50 MiB 预算下缺少转码分支，已由 [`REQ-003`](#req-003) 转码子句承接。局部 schema/local_contract/静态 gate PASS 不替代此证据。
- 完成判定：[`GWT-020`](#gwt-020) 全部 producer 子句与 [`GWT-034`](#gwt-034) 由同一条可追溯 producer proof 链通过；M1 证明首次对象生产，后续各级证明累计唯一对象、原 proof 复用与独立 cohort/release/handoff。legacy repackage 另须 [`GWT-062.t1`](#gwt-062) 至 [`GWT-062.t14`](#gwt-062) 全部具当前实现的子句级证据，且真实 source legacy handoff、不同新 identity 的 output release 与 publish current terminal exact 共存并 readback，source tree digest 和 existing execution 均不变。下游 Alpha 不参与关闭。
- 依赖：真实 provider、一个真实 author actor 会话、另一个真实 reviewer actor 会话、canonical publish 与 release/handoff；环境 CLI/实现不在依赖中。

<a id="open-015"></a>
### OPEN-015 默认公开媒体链、图集与视频尚缺 fresh App UAT

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺无类别发布消费链在同一 runtime generation 的 fresh Remote App UAT。公开图片、头像、对象主页、文章和视频应从同一 active release 消费，包含新 caption、SourceAttribution 与公开媒体绑定；类别专属身份、旧私有 MP4 UAT 或 previous-version adapter 均不能证明 [`REQ-002`](#req-002) 的默认公开行为。
- 尚缺实现：按 [`OPEN-024`](#open-024) 完成跨 owner 无类别契约和消费迁移，保留稳定资产身份、普通原图权限、缓存隔离与有界媒体恢复；不把 private HLS 引入默认 release。
- 尚缺验收证据：同 candidate/target/release/runtime generation 的 entry surface × carrier required cells 全部产生 raw `ReadinessCaseResult`，公开媒体 GET/HEAD/Range 与视频续播不依赖专属身份或换签，普通原图授权边界另行验证。环境 scheduler 按自身现役契约绑定 raw refs/digests 与完整 named closure，旧命名轨道 receipt 或完整性 projection 不能替代。
- 完成判定：[`GWT-002`](#gwt-002)、[`GWT-016`](#gwt-016)、[`GWT-030`](#gwt-030)、[`GWT-032`](#gwt-032)、[`GWT-043`](#gwt-043) 的现役前置合同与 API 证据通过，fresh Remote App UAT 证明默认公开消费、相同内容身份与保留的普通权限；未取得原始现场事实不得关闭。
- 依赖：App/Service/Runtime 的无类别迁移，Testing/Ops 的 fresh runner 与完整环境证据；[`OPEN-017`](#open-017) 的独立媒体能力不阻断本 OPEN。
- 图集与视频证据：在明确授权的环境以同一 candidate/release/runtime 的 API readback、App 图集切换/逐图说明与视频 Range 播放绑定 [`GWT-043`](#gwt-043)；Dart 修改后执行 hot reload/restart。环境、设备或 runner 不可用时保持 typed blocker；Alpha 只证明 Alpha 消费，不能冒充 Gamma 或 EAF，源码/契约与 fresh raw UAT 分层报告。

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
### OPEN-017 通用 private HLS 尚未设计与实现

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺 private HLS 对 manifest/segment/key 授权、换签与播放位置恢复的独立设计；当前 contract 明确返回 unsupported typed terminal 并 fail closed，不回退 progressive MP4 或 public URL。该缺口不改变 progressive private MP4 已实现事实，也不阻断 [`OPEN-015`](#open-015) 的 fresh UAT。
- 尚缺实现：Service/Runtime/App owner 需冻结 private HLS 的资产/segment authority、边缘验签、TTL 过期恢复、缓存身份、失败终态与播放器接入；在设计完成前保持 unsupported，不设类别专属 release，也不扩入默认公开内容消费链。
- 尚缺验收证据：local_contract 覆盖 manifest/segment/key authority 与 fail-closed，api_integration 覆盖边缘逐段授权和过期恢复，user_acceptance 覆盖不中断或可定位恢复的真实 private HLS 播放。
- 完成判定：[`GWT-033.t1`](#gwt-033)、[`GWT-033.t2`](#gwt-033) 与 [`GWT-033.t3`](#gwt-033) 对应 future private HLS 的独立设计决定与 canonical contracts 落地，private HLS 不再返回 [`GWT-032.t2`](#gwt-032) 的 unsupported terminal，且 local_contract/api_integration/user_acceptance 三层证据绑定同一 release/asset identity；完成前 current unsupported terminal 保持不变。
- 依赖：Service media contract、edge verifier、Runtime release projection 与 App player owner 联合接手；不得复用或放宽 progressive MP4 的单 URL 假设。
- 退役边界：默认公开 release 不承诺专属私有 HLS，也不恢复类别专属私有交付入口。该入口及旧兼容分支的退役、共享原图/签名安全回归由 [`OPEN-024`](#open-024) 按 [`GWT-044`](#gwt-044) 验证；不能据此取消或包装关闭尚未实现的通用 HLS 缺口。

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

<a id="open-021"></a>
### OPEN-021 存量 canonical 实体头不满足 publish entity schema

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：publish 截面的实体 schema 门（[`GWT-036`](#gwt-036)）只拦新投影，门落地前已发布的 canonical 实体仍缺合规处置；既有样本曾缺百科来源身份、地理引用或派生修改字段，依赖这些对象的 cohort 在 `homepage_import` fail closed。具体对象、数量及 exact apply 结果属于运行盘点证据，不在通用规格冻结任务实例；历史样本不等于当前全池无效对象总数。
- 尚缺实现与证据：按 [`canonical-content-identity-recovery`](../canonical-content-identity-recovery/spec.md) 的事务与保护边界对全部当前对象逐项冻结 before 身份、摘要、来源/review 与依赖，构造满足新契约的完整 staging；仅转换可验证对象，未验证对象及未闭合依赖只归档，不进入新合格池，不以目标数量补造资格。旧 excluded 只作历史诊断，不作为当前资格。
- 当前盘点口径：snapshot 只计物理占位（含作者）；pool-query 的 objects 还包含展开的缺失依赖，occupied/invalid 与 absent 必须分开。新包契约下旧计数不能用作当前 eligible，历史错误与本次错误分别保留；合法的原对象级权利词汇不因删除类别而成为错误，也不得因某项先触发的记录错误掩盖原 payload/rights 问题。迁移保留逻辑身份、原权利值与原 review，只对受治理包格式转换生成新版本/摘要。
- 完成判定：全量当前对象均有可验证转换或仅归档终态，活跃实体全部满足 [`GWT-036.t3`](#gwt-036)，没有旧结构、悬空依赖或永久 excluded；转换后完成新包、引用闭包及保护集验证才按精确授权清理旧链，媒体与既有 release/review/receipt 原字节不变，未取得证据不宣称完成。新 release 在授权 Alpha 的 `homepage_import` closure 属独立消费证据，不以 producer 测试替代；不得手改摘要补 passed、放宽 schema 或在导入器加 fallback。
- 依赖：单轨 schema、受治理全池 cutover、精确删除授权与真实独立 review；Data ship 与 homepage 导入器只读新对象，不参与修正。

<a id="open-022"></a>
### OPEN-022 Content CAS 之后 fenced readback 失败且无 previous release 时 Data ship 缺少收敛路径

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：`ship activate` 在 Content CAS 已返回、四域 fenced readback 任一失败时按设计进入 `ambiguous`，但 Data 侧只有两条后续操作且都无法收敛首个 release 的失败：重跑 `ship activate` 以 fresh pre-query 作 expected-current，pointer 已在目标 tuple 时 Content 端按 predecessor 语义判 CAS conflict 而不是 exact replay；`ship rollback` 要求一个 distinct 的 `--from` tuple 与 prepared 目标，pointer 之前为空时不存在可回退的 previous release。Alpha 首次真实 activate 即命中此路径：Content CAS 成功（revision 1、3 posts/6 media/3 outbox），Tag/Creator/Homepage fenced readback 通过，Content 自身 fenced readback 因评估器把 candidate staging `projectionVersion` 与 pointer activation `projectionVersion` 当作同一值而失败（typed 证据为该 activate run 的 `result.json`，`failedStage=owner_fenced_readback`）；评估器已修正，但环境只能靠 alpha-local 可重建状态整体重置来恢复，Beta/Gamma/Prod 没有等价手段。
- 尚缺实现：`ambiguous` 之后的显式收敛操作，二选一由 runtime-data-engineering `DEC-003` owner 裁定：以原 activate run 的 pre receipt 作 exact predecessor 的 replay-only fenced readback，或允许 rollback 到 empty predecessor 并生成新 revision；两者都必须只消费显式 receipt ref+digest，不猜测、不自动重试 CAS。
- 尚缺验收证据：local_contract 注入"CAS 成功、任一域 fenced readback 失败、pointer 之前为空"的序列，证明收敛操作只在 exact predecessor 证据在场时执行且 owner bytes 不变；api_integration 覆盖收敛后四域 readback 同 tuple。
- 完成判定：[`GWT-035`](#gwt-035) 的 Data ship 交付面下，上述序列在 Alpha 真实运行一次并得到 `completed` 的 activate 或 rollback 结果，且 `ship verify` 可消费该结果；不得以重置环境状态、手改 pointer 或放宽 fenced readback 判据关闭本 OPEN。
- 依赖：runtime-data-engineering `DEC-003`（fence 与 rollback 语义 owner）；content-service release-control 的 replay/rollback 契约。

<a id="open-023"></a>
### OPEN-023 `ReleaseUatSamplePlan` 无 owner 产出，下游 verify/精选池/bind/UAT 对现役 release 全部不可达

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：producer cutover 把 `ReleaseUatSamplePlan` 从 release build 移除（`aggregate_release_uat.py` 已无调用者），[`REQ-013`](#req-013) 注明该 sample plan 为 downstream-owned；但下游没有任何 owner 创建它，而 Ops 消费面仍要求 immutable release 头携带 `samplePlanRef=uat/sample_plan.json` 与 `samplePlanDigest` 并从 payload 内读取 exact bytes：`stackctl premium-pool --launch-policy release-import`（空池首次激活）、`stackctl dev-session bind-content`（test-live content binding）与 `app-content-uat`/managed preflight 均在此 fail closed。`ship verify` 对全部 readiness phase 要求 `premium_stream` release-bound 非空读回，而精选池只能经 release-import 自举，于是任何现役六步 release（M1/M10/M100）都无法取得 `release-readiness.json`，`bind-content`、受管 `flutter run` 与 App UAT 随之不可达。Alpha 真实证据：M1 `ship activate` 已 `completed`（Content CAS revision 1，四域 fenced readback 通过，discovery/typed/homepage_recommend feed 均读回 release posts），`ship verify --readiness-phase research` 在 `post_api_verification` 以 "premium_stream feed does not expose any release-bound postId" 阻断；`premium-pool release-import` 以 "release UAT sample plan binding is invalid" 阻断；managed prepare 以 `release_active` 无 research readiness receipt 阻断。immutable payload 由 producer 封存，下游按定义不能再向其中写入 `uat/sample_plan.json`，因此现有消费契约与 REQ-013 的 owner 声明互斥。
- 尚缺实现：由 design 裁定 sample plan 的唯一 owner 与落点（downstream-owned artifact 以 `releaseId+manifestDigest` 绑定、置于环境 run evidence 或 candidate 私有 projection，而非 immutable payload），并按契约→codegen→实现顺序改 `app_content_uat_plan.load_release_uat_sample_plan` 及其三处消费者；或反向裁定 producer 重新携带 sample plan 并回退 REQ-013 注记。两者都不得以放宽 `premium_stream` 判据、跳过 sample plan 校验或手写 header 字段实现。
- 尚缺验收证据：同一现役 release 在 Alpha 真实取得 `premium-pool` 首次激活收据、`ship verify` 的 `release-readiness.json`、`bind-content` 成功与受管 `flutter run` 到达 attach；local_contract 证明 sample plan 缺失、digest 漂移与跨 release 搬运均 fail closed。
- 完成判定：[`GWT-035`](#gwt-035) 的 Data ship 交付面下，上述 Alpha 证据链在同一 alpha-local generation 内闭合，且 `health`/`content-readiness` 的 `release_active` 通过；不得以环境重置、fixture sample plan 或旧 release 的 receipt 关闭本 OPEN。
- 依赖：runtime-config `environment-topology-and-packaging` GWT-004（精选池首次激活与 UAT sample plan 消费 owner）；`OPEN-019`/`OPEN-020` 的 producer 复合验收重建。

<a id="open-024"></a>
### OPEN-024 发布与消费链尚未去除类别维度

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：[`REQ-002`](#req-002) 的无类别默认链路尚未实现。Data/Service/App/Ops 的契约、结果、内容绑定和就绪校验仍携带类别字段或常量标签，部分专用身份、读回和私有交付分支尚存；只改成单一枚举值不能满足无类别契约，尚缺跨 owner 的实现及当前验收证据。
- 尚缺实现：各 owner 按 authoring source、派生产物、实现与测试顺序删除发布类别、运行类别和命名消费轨道，连同参数、字段、枚举、指纹投影、专用身份及路由分支一起收敛；不得填入另一固定标签或增加 dual-read。环境差异只由环境配置表达，保留精确 release/activation/readiness/lease 绑定、普通认证、安全与环境边界。导入、激活、验证、回滚仍是生命周期动作；完整发布验证独立要求 Exit，普通内容启动不以回滚演练为前置。已封存 release/cohort/handoff 与逐对象真实 rights 字节不回写，新契约证据须重新产生。
- 尚缺验收证据：默认无类别输入可闭合 producer 与下游消费，类别选择参数和字段不能恢复旧轨；同一 release 在四环境仅按环境配置执行且内容身份不变。四入口及公开媒体直链不因缺少授权记录受阻，普通权限、跨 release/环境/lease 错绑仍拒绝；local_contract/api_integration 与 managed/raw/direct 现场证据分别取得，不复用单一命名类别的既有通过结果。
- 完成判定：[`GWT-002`](#gwt-002) 的默认单链路、环境配置隔离与公开交付结果，以及 [`GWT-044`](#gwt-044) 的专属身份/路由/隔离退役与普通权限保留，均由对应 owner 的静态、local_contract/api_integration 和授权环境证据绑定；[`OPEN-015`](#open-015) 的 fresh 消费和 [`OPEN-017`](#open-017) 的通用 HLS 缺口分别保留，不随旧专属路径删除一并关闭。已有公开媒体、来源署名与逐图 caption 实现仍须 [`GWT-043`](#gwt-043) 的当前证据，不得通过兼容分支或环境名推断内容类别关闭本 OPEN。
- 依赖：Data 发布契约与 producer owner、`lane/product-mainline`（Service/App）、`lane/ops`（消费控制面和环境配置）；不把下游运行证据加入 producer 完成条件。

<a id="open-026"></a>
### OPEN-026 商用前补齐未授权内容公众可见性治理

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前非商用开发验证按 [`REQ-002`](#req-002) 统一开放，公开可读取不等于取得商用授权；素材的真实权利记录必须持续保留。
- 尚缺实现：商用前由下游内容与运营 owner 冻结公众可见性、授权证据、撤回与审计策略，四入口和媒体直链共享同一决定；不得改写 immutable producer facts 或恢复 release 双类别。
- 尚缺验收证据：商用策略冻结后的 local_contract/api_integration 与真实入口、媒体直链联动验证；本 OPEN 不要求本阶段部署运营放行机制，也不阻断开发验证。
- 完成判定：[`GWT-002`](#gwt-002) 的权利事实保留与开发期公开交付继续成立；商用策略由其唯一 owner 增补可测试验收并生效，授权缺失、撤回和已授权三类结果有一致读回；不以开发期匿名可读推断授权通过。
- 依赖：下游内容可见性与运营策略 owner；商用启用须另行获得用户裁定，本次不包含实际 Prod 部署授权。

<a id="open-025"></a>
### OPEN-025 最小随体对象包与跨端单源消费尚未闭合

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺新随体对象包与跨端单源消费的完整证据。当前 Data/Service/Ops 已有 manifest 单源、公开媒体与 cutover 成果，有效部分保留；单一 production 类别不属于当前无类别目标，不能据此恢复类别或改写对象级权利词汇。不能把已有三旁车收敛视为随体媒体、来源原件、审核 binding 与独立仓 handoff 已完成。旧真实池仍须受治理转换，不以固定文件数验收或借精简丢失审计。
- 尚缺实现：按 [L2 DEC-044](../design.md#dec-044) 同步实体事实入 manifest、采用来源在 `sources/<unit>/source.json` 单写并携带必要证据、最终媒体完整复制及 records 收敛。旧 source catalog/rights/生成式 snapshot 的真实事实迁入 source，删除重复投影而保留第三方原件、review 原结论/对象摘要及历史 records；creator 身份/profile 仍独立。verify 与消费者必须只读，不再隐式恢复 library。
- 完成判定：[`GWT-045`](#gwt-045)、[`GWT-041`](#gwt-041)、[`GWT-022`](#gwt-022)、[`GWT-023`](#gwt-023)、[`GWT-036`](#gwt-036) 与 [`GWT-038`](#gwt-038) 的改动子句在新闭集上由真实测试直接绑定；完整复制到无 execution/library 的目录仍可校验，来源缺失、媒体损坏与逃逸可区分；同一新 release 经唯一 reader 消费，旧 release/review/receipt 与保护媒体摘要不变。不以 dual-read/dual-write 或重算旧审核摘要关闭。
- 尚缺验收证据：[`GWT-045.t1`](#gwt-045) 至 [`GWT-045.t6`](#gwt-045) 尚缺子句级绑定与真实生产证据。候选到ingest尚未完整携带原响应、原生作品身份和成员范围；需用共用sourceWork与实际证据引用绑定四载体，证明媒体用途、组图原序、正文位置及未采用媒体排除。既有多图schema或Alpha导出通过不替代原作取得和目标投影变化的隔离证据，不要求补造旧成品缺失原始记录。
- 最小测试入口：`quwoquan_data/tests/local_contract/release/test_publish_fail_closed__carried_media__contract__local_contract_test.py`、`test_homepage_entity_projection__publish_schema_gate__contract__local_contract_test.py` 及现有对象事务/release handoff 测试；先增加 `GWT-041.t1` 至 `t4` 的包级证明，再由 Service importer/Ops materialize 的短 api_integration 验单源。旧 sole-holder 断言须改验新语义，历史 PASS 不算新证据。
- 依赖：Data schema/producer、Service importer、Ops delivery 的各 exact path owner；实际存量迁移、删除与内容仓初始化分别授权，归身份恢复 Story 的 `OPEN-001`。

<a id="open-027"></a>
### OPEN-027 地域布局与共享内容仓写入边界待验证

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺新地域布局与共根锁的行为证据。新目录与容量规则已冻结，仍需证明根身份 fail closed、真实行政链、同名组分配与跨源码工作树共锁，不因目录整齐丢身份或虚构地域；不表示独立内容仓已初始化或迁移。
- 尚缺实现：locator/显式身份读取、仓身份枚举、只按条目数和逻辑字节的分区分配及共享锁。执行工作包原物理布局不变，非地点只预留结构，无新 producer 或后台均衡。
- 完成判定：[`GWT-040`](#gwt-040) 全部子句由现有 DataRoot/canonical inventory/object-transaction 的最短 local_contract 直接绑定；跨工作树共根并发只允许一个胜者，缺根/错仓不回退。
- 依赖：Data layout/publish schema、路径/事务 owner；同名身份守恒由身份恢复 Story 的 `GWT-002` 和 `OPEN-002` 验收，实际切换不由此项授权。

<a id="open-028"></a>
### OPEN-028 稳定 mention 投影与局部媒体失败尚缺真实消费证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺稳定 mention 与局部失败的真实消费证据。现有图片占位、负缓存与主页下线展示继续复用；真实文章 importer 是否填充 exact 主页映射、图集是否接入负缓存、视频 cache hit 是否不续 TTL 尚须当前候选证明，手填 mention 的 Widget 测试不足以证明生产链。
- 尚缺实现：复用 Entity 映射完成 Content 文章投影，缺映射去掉链接外观；仅修图集与视频既有缓存接线，不扩建非文章引用 UI、通用富文本或健康框架。目标权限与 ordinary offline/historical View 仍由原 owner 处理。
- 已知不阻断限制：App 对缺映射 styled mention 当前会整段降级为纯文本，样式保真尚不完整；仅此限制不阻断本次收敛，不表示用户批准全部风险，也不代替下述真实消费证据或关闭本 OPEN。
- 完成判定：[`GWT-042`](#gwt-042) 五条结果分别有真实 importer→typed query api_integration 与 App 局部失败/缓存 local_contract 绑定；授权环境的实体下线点击返回、单图失败可滑动及视频有界停止另有 fresh UAT，不以局部 PASS 关闭。
- 最小测试入口：Entity homepage importer、Content release importer 与既有 article mention Widget 测试；App `image_book_canvas`、`video_player_widget`、主页错误展示的现有短 local_contract，测试需直接绑定 `GWT-042.t1` 至 `t5`。Dart 改动按 App 规则热重载，未连设备保持未验证。
- 依赖：Service/App/Ops 原 owner 与明确环境授权；不是 producer handoff 的前置。

<a id="open-030"></a>
### OPEN-030 统一语义协议的 producer 到跨端闭环待实现

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：[`REQ-022`](#req-022) 已消除移动端模板、同实体百科换 `publishAngle` 与跨 revision 拼接，并区分 protocol version triplet 与 object revision tuple，但 exact wikitext+Parsoid acquisition、semantic mapper、双版本绑定、faithful adaptation/文章独立性 review 和跨端 reader 尚无同 revision 完整证据。
- 完成判定：Data canonical contracts、acquire/author/review/publish、Service projection、Web/Android/iOS renderer 与工作台 query 对同一对象逐节点、逐 protocol version、逐 object revision 对账并通过 [`GWT-045`](#gwt-045)；unknown schema/dialect major、canonicalization mismatch、required capability missing、交叉 source revision、非忠实改写、同实体换角度、viewport 内容结构分叉、端专属模板和工作台越权写入均有 fail-closed 反例。
- 依赖：`content-type-framework` 的 [`DEC-003`](../../content-type-framework/design.md#dec-003) 与 `markdown-article-kernel` 的 [`OPEN-002`](../../content-type-framework/markdown-article-kernel/spec.md#open-002)，以及本层 `DEC-046`。
<a id="open-032"></a>
### OPEN-032 宿主不提供模型选择器时无法兑现按岗锁定高能力模型

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：总监与创作者必须按行业顶级专业标准配置与验收，但当前已核实的 Grok 公开文档写明由 Cursor 管理模型选择、无模型选择器。写入专家人设不能证明实际调用已升档，也不能作为无人值守接管的依据。
- 尚缺实现：不伪造 model 参数，不改 relay/客户端/账号路由。若受支持入口将来允许选择模型或推理档，按岗位任务评测选择高能力配置并读取实际生效结果。
- 完成判定：只有受支持入口可选择目标模型/推理档、读回实际生效身份，并以岗位任务评测证明满足要求时才可关闭。[`GWT-050`](#gwt-050) 的“明确未知”只证明诚实披露与安全降级，不能关闭模型选择能力；样本通过也只证明该样本表现，不证明模型已锁定。
- 依赖：宿主产品能力与用户确认的执行端。不得暗中恢复 Cursor 生产或新建模型路由服务。

<a id="open-033"></a>
### OPEN-033 双账号同时本机连接与分片并行尚未证明

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺两账号同时保持受支持本机连接、切号是否切断另一账号调用、以及不重叠分片写入的证据。多账号复制会放大重复选材、共享磁盘与发布锁冲突。当前 Fetcher 间隔只约束单次调用，内容仓 flock 只覆盖同一锁域进程，不是跨机器分布式锁。
- 尚缺实现与证据：当前 0.47.0 包内存在 `--user-data-dir`/`SAND_USER_DATA_DIR` 隔离入口但未形成公开产品承诺；须按 exact 版本/签名以两个空 profile 和独立 data/output 根证明两账号同时连接、退出/重启互不切断、daemon/gateway/Computer Use 不串接，并在 generation fence 已接入真实写点后证明两队读取同一 coordination DB 与同一 canonical 锁。不能证明时只启用轮换。
- 尚缺验收证据：P0 单实例基线、P1 双实例只读 30–60 分钟、P2 双实例沙箱写、P3 唯一收官正式小轮的分层读回；账号串号、cloud computer 重合、固定端口/Computer Use 冲突、跨根 credential 删除或旧代写成功任一发生即回退单实例。轮换路径可先于并行单独举证。
- 完成判定：[`GWT-051`](#gwt-051) 由真实双账号连接读回与不重叠分片写入证据关闭。轮换路径可先于并行单独举证。
- 依赖：受支持本机执行端与用户授权的切号试验。不改 daemon/relay 规避账号隔离。

<a id="open-034"></a>
### OPEN-034 十团队具名分片协作与 M100000 真实闭环尚未取得

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：[`REQ-022`](#req-022) 与 [`GWT-052`](#gwt-052) 保留具名 shard、全局 iteration、deployment/generation、既有协作状态、预算预留、原子幂等释放及后继清理边界；岗位按四类、多实例收敛，检查改为总监增量保流而非全队十分钟停产。当前规格、已有 SQLite 或局部测试不证明十团队宿主连接、真实内容生产或 M100000 已成立，单账号自主生产增量暂停跨账号/VM 扩容，不关闭原目标缺口。
- 尚缺实现与证据：既有 coordination 只承担 claim/预算硬事实，作者/review 原子归属与真实写围栏增量由 [`OPEN-035`](#open-035) 单独跟踪；禁止语义调度、业务完成 writer、TTL 抢占与自动清理。未来授权的多团队仍须同步四类岗位及实际实例，独立 QA 不得降回临时互审。
- 尚缺验收证据：可控时钟/并发 local_contract 覆盖既有状态闭集、唯一 winner、generation/nonce 漂移、幂等释放、失联不抢占和 SQLite 删除不改业务事实；真实宿主验证十团队 deployment/连接与独立 QA；生产小轮验证原生在飞状态、预算预留和后继只审计不清理前任；独立外盘验证随体/保护副本容量、摘要、挂载身份与恢复。单账号自主生产通过不代替这些证据。
- 完成判定：[`GWT-052`](#gwt-052) 的 local_contract 与真实宿主/生产小轮/外盘证据在同一有效 generation 分层通过，且最终 M100000 cohort/release/handoff 读回四载体分别不少于 `100000` 个累计唯一 finalized 对象。任一宿主、生产授权、外盘或 M100000 事实缺失均保持阻断，不能以 SQLite 行数、团队数、历史 M1/M10/M100/M1000/M10000 或计划文本关闭。
- 依赖：受支持的真实多团队宿主、用户明确生产与 publish/finalize 授权、唯一 canonical 内容仓、足额 provider/模型/磁盘预算及经用户确认的独立外盘；本次规格冻结不签发这些授权。

<a id="open-036"></a>
### OPEN-036 多源检索指导的 policy 对齐与真实媒体复核待完成

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺专业/综合同级优先与既有 imageProviderPriority policy 的一致性验证，该policy及schema由其他活跃writer占用，用户明确要求不覆盖并先完成技能及统计；新平台来源名单不证明实际下载或合法授权。当前registry/schema已支持百度百科且authorityRank位于第二，但在线来源能力仍需实证。
- 尚缺验收证据：点名样本发现百科拆句、摄影标签证据不足、生产指令进入正文、旧视频审核未读当前草稿或未实听音轨仍 approved，事实矛盾仅记 advisory；媒体观察与活动根仍需逐批证实。存量 b01f/b01h/b01j 只做点名复核与获准安全修订，不能回填旧 receipt 或以新批成功关闭历史缺口。
- 来源投影缺口：article-r108 雁荡山对象包含声明为徒步主源的 Meet99 与百科补充，文本 attribution 却优先选百科；须由来源投影 owner 核实际选择及显式归属，不以百科存在自动决定文章主源，不把单源许可外推为整个多源作品授权。先冻结字段/归属契约与负例再修改投影，所需代码 scope 独立确认；不改历史对象包或新增来源管理岗。历史作品不自动修订，统计不外推全库，协调内核不由此扩展。
- 完成判定：[`GWT-059`](#gwt-059) 的只读计数/去重/缺失/路径边界测试通过，并由policy owner完成同级优先对齐，实际受支持平台与点名媒体复核有证据；源码工具PASS不替代真实视听或平台可用性。

<a id="open-035"></a>
### OPEN-035 单账号自主整批生产的真实工具、团队生效与净增证据待取得

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：[`REQ-022`](#req-022) 至 [`REQ-026`](#req-026) 已冻结四类岗位、自主整批交接、两批且一创作、共享有效版本、总监主动保流与 A/B/C 安全重组；尚缺作者级独占与完整真实写围栏的实现验收，以及活跃 Bot 生效、原生唤醒和有效产出提升的真实证据，规格和手册一致不能代替这些缺口。
- 实现边界：coordination 与真实 CLI 已接入角色数组、任务摘要/根绑定、author/reviewer 小批原子归属及角色写入核验；容量按已登记的 host/session 聚合，exact run 继续绑定产物，换 run 不产生独立名额；空正文沿 acquire 内核逐 target 报错而非整批拒绝。本地回归覆盖不能证明原生身份认证、OS 权限隔离或直接调用 Python 内核不能绕过。显式任务确认引用不是 Grok 总监真实确认凭证，同 OS 用户仍不能仅靠应用内校验获得安全隔离。
- 尚缺实现与证据：当前源码的 producer callable 已移出 SQLite 写事务，由 deployment/shard 与 execution 门保护业务；不能继续将 SQLite 长事务当作现役停滞根因。慢 acquire/媒体派生、撤权竞争和跨批不阻塞仍须该工程 owner 绑定当前字节及测试/原生证据确认，已有测试定义不等于对应源码指纹的运行证据；门实现的变更和验证由工程 owner 独立负责。handler 预读后内核再次读取输入，exact bytes 消费与校验后修改负例尚缺。缺可信原生终态证明时，全批 blocked/unknown 名额仍保留，不能以 caller 布尔值放行。混合 pass review 的明确 rejected 对象经审核原件与 blockingIssues 校验后退轮，全部 approved 对象仍须 exact publish proof 闭合；该路径已由本地真实 seal/publish 测试覆盖，不代表原生终止恢复已实现。历史 cohort 对象可能不在当前 claim，累计 finalize 的历史 proof 授权与成功路径尚未闭合。
- 使用限制：新 CLI 对缺少绑定的调用拒绝，不等于已经完成活跃团队安全切换；旧单值角色不静默迁移。须先从受支持入口核实际活动根、旧写者、显式四根/任务版本绑定与所需授权，再启用新调用。不得以源码已改推断当前 Grok 已配置或依此改动正式根。
- 本机执行阻断：已有进程证据显示个别 shell 在业务执行前等待快照管道输入；尚缺当前 Grok 应用与可维护启动器源码/owner绑定。旧编译备份中的 write/end 与 exit 后 close watchdog 不证明该输入等待根因，不能据累计无时间日志归因数据库锁、代理或全队容量耗尽。需启动器 owner 用合成快照隔离复现后修复，不在内容 Skill 新建执行器、不修改旧 bundle、不以重启或取消安全校验代偿。
- 外部阻断：仍需支持的 Grok 团队管理/原生调用状态/通知或 Routine 接口、真实总监确认、全角色共享事实和同版本读回，以及实际活动根/媒体链核实。工具不可用交精确人工清单；无自动唤醒不得宣称无人值守，文件或简介更新不得宣称运行配置已生效，unknown 不因该重组被终止或重派。
- 尚缺生产证据：在明确费用/站点/存储及生产发布授权内，先两作者再四作者、至少两独立 QA 并行不同批；用 100 图片作品拆小批证明慢批不阻塞健康批、容量边界与连续续领，并注入普通失败、已知终止、unknown、待审/发布积压、总监检查失效和额度耗尽。无发布授权只到 review 且停在端到端名额边界，不以局部 PASS 代替完整发布。
- 完成判定：[`GWT-053`](#gwt-053)、[`GWT-054`](#gwt-054)、[`GWT-055`](#gwt-055)、[`GWT-056`](#gwt-056)、[`GWT-057`](#gwt-057)、[`GWT-058`](#gwt-058) 的 local_contract、真实宿主读回与真实有界生产证据分层闭合；共享版本/越权/旧代零写、每次异常有 owner 和下一检查裁定均可复核，并在同质量/载体/冷热缓存条件取得净 eligible 产速、周期、WIP、最老项、返工和单位成本的真实对比。缺 native 时间不编等待，只有通知不报恢复，不预承诺翻倍。
- 依赖与不代偿：需要用户有效授权、受支持原生工具、实际活动根和真实角色会话。`OPEN-020` 的 producer 里程碑、`OPEN-032` 的模型选择、`OPEN-033` 的双账号连接和 `OPEN-034` 的十团队/M100000 保持原缺口，不因单账号自主生产增量单账号规则或测试通过关闭；本 OPEN 关闭也不等于正式 M100000 达标。
