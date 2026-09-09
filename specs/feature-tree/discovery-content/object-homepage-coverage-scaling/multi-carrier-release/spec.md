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
- 本 producer 只生成单一 `releaseClass=production` 的 immutable release/handoff；逐对象保留完整 rights/`usageScope` 记录事实，但权利状态不构成 publish/release 阻断，research/commercial 双类别与 commercial readiness 都不存在，公众可见性由下游运营运行时配置决定，不据此建立第二 workflow、pool 或 semantic queue。
- 批次级/跨载体聚合门只作目标与统计；四载体共用 acquisition/rights/distribution 记录，权利只记录不阻断，但不放宽访问控制、内容安全、隐私、未成年人、恶意文件、去重、实体相关性、质量或可播放性。
- 经确认的请求只由宿主 Cursor/Codex IDE/CLI Agent 直接执行 canonical content-production Skill；identity-only candidate-backed 工作包、producer 六步（init → acquire → author → review → publish → release）的三份 seal receipts、approved object package、canonical pool 与 immutable release handoff 单轨推进。handoff 不携带 UAT/sample authority、import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback facts。

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

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多载体宿主 execution 与 pool→release 单轨

- 每个发布对象必须闭合 creator、tag、entity、media、source、rights 与 independent review；`4.draft` 每对象只有一个 carrier 主产物，`5.review` 每对象只有一个 `content_review.json`。运行 receipt 只能写入 execution/output，不回写静态真相源。
- homepage、article、image、video 共享 canonical entity catalog，但各自拥有由 identity-only candidate bindings 初始化的 immutable execution。唯一语义与推进主体是直接执行 `.agents/skills/content-production/SKILL.md` 的宿主 Cursor/Codex IDE/CLI Agent；新任务不得调用或新增仓内 resolver/projector/runner/controller/queue/registry/SDK/自动恢复、`task execute`（含 plan-only）或 pool-dispatch。
- candidate binding 只冻结目标对象身份，不要求 task-init 前 source/media admission。中性 `task init` 从一份 round spec 原子创建该轮全部 carrier execution 的三份输入后，宿主严格执行 producer 六步：`acquire` 由 AI 以宿主原生能力出网检索、取证并下载来源，再按 execution 提交一份零网络 ingest 清单，脚本只从本地字节机械派生 sha256/CAS/mime/probe/poster、按申报 license 派生 `rightsStatus`（物理目录 `1.download/`）；`author` 由 AI 直接创作每对象唯一 carrier 产物（`4.draft/`），标题、tagRefs、creatorProfileId 与选用资产由产物自身声明；`review` 由另一真实会话按 execution 提交一份判断输入，seal 机械扇出到逐对象 `5.review/content_review.json`。每步完成后由 `task seal` 自行校验硬事实（schema、引用、摘要、媒体字节、tagRefs、author≠reviewer）并 create-once 写 receipt `001-1.download`/`002-4.draft`/`003-5.review`；不存在 stage-open、宿主 verifierFacts、2.quality/3.compose 产物。`publish` 是单对象事务，`release finalize` 成功即 `END`。
- 一个 execution 的 `4.draft` 由一个真实 author actor 会话负责——可以是主会话，也可以是宿主派发的独立子 Agent 会话——其 actor/invocation 与产物 exact refs/digests 只由 `002-4.draft` seal receipt 冻结；`acquire` 的出网取证、下载与 ingest 清单可由主会话或该 author 完成，`001-1.download` 只冻结提交者 actor，不要求与 author 同一会话；该 seal 同样逐对象校验来源硬事实，ingest 失败或字节漂移的对象只以 typed issue 退出本 execution，至少一个对象取得来源即 `pass`，后续 `4.draft` 只校验 `001-1.download` resultRefs 中的对象。`002-4.draft` seal 逐对象校验产物硬事实（非空、tagRefs 解析、creatorProfileId 解析、homepage 百科主源）并一次报出全部违规：不合规对象只记 typed issue 并退出本 execution，至少一个合规产物即 `pass`，只有零合规产物或 stage-wide identity/integrity failure 才 `blocked`。`5.review` 由另一个真实 reviewer actor 会话负责，其判断输入的覆盖集合是 `002-4.draft` receipt 的 resultRefs 对象集合（退轮对象不需评审），其 actor/invocation 与逐对象 `content_review.json` exact refs/digests 只由 `003-5.review` seal receipt 冻结，review seal 负责把 execution 级判断输入扇出为逐对象文件并补齐机械字段（schema/stage/executionId/objectRef/draft 与 assetRights 权利转录）。两者必须为不同 session/runId，可使用同一 model family；同一 execution 同时至多一个 reviewer 调用，不同 execution 的 author 与 reviewer 可由宿主原生并行；不建立对象级 actor projection。跨会话只认 receipts 与业务 result refs。主会话拥有与用户的一次性约束澄清、全部机械命令、子 Agent 派发与轮次收官；澄清后由宿主自行规划并推进到终止条件（计数达标、候选前沿耗尽、连续零净增、用户中止或授权闸口），收官报告六段（目标 vs `pool-query` 计数、新增/复用、放弃清单、blocked execution 与首个 typed blocker、缺口、后继轮次的最小入口）且计数只从 `pool-query` 读；续跑交 `continue`/`plan-next`，不另立恢复轨或轮次台账。
- 单载体失败不得覆盖其它工作包，也不得阻止其它载体已合格对象入池。approved/rejected 可混合，短缺由 stage result artifact/typed issue 表达，不给通用 receipt 增加 `partial`；只要至少一个 approved 对象且无 stage-wide identity/integrity failure，stage 可 `pass` 并保留 shortfall，只有零 approved 或 stage-wide identity/integrity failure 才 `blocked`。
- `003-5.review` receipt 所绑定的 `content_review.json` 判定 approved 后，publish AI 对对象逐个调用 canonical 单对象事务（无 plan/apply 双跑）；不存在独立 review receipt、drain/process manager 或 execution 级 publish。canonical object package + append-only pool record 是 producer 内部 publish→release 的持久事实；release ref/digest、explicit cohort ref/digest、milestone、carrier counts、content-pool handoff refs/digests、producer baseline revision 与 producer contract digest 组成唯一 immutable producer handoff，handoff 以 canonical publish proof 为凭而不内嵌 execution receipt 链。运行身份不进入 consumer identity、eligibility、release cohort 或 App DTO。
- release selection 只接受显式 create-once pool record、完整 admission、随体来源/媒体与 canonical identity。逐对象失败只排除该对象，成功对象继续。content library 用于采集复用；最终对象包和 release 的完整消费不依赖原 execution 或 library 在场，release 仍只作分发物化。
- 每个 execution 的 `approvedQuota`、candidate count 与 workUnitCount 三值分离；宿主并发能力不进入三值、对象判据或仓内配置。
- article/image/video Post manifest 必须显式 `contentIdentity=work`；新增对象必须有稳定 `contentId`、递增 `version`、`sourceType=data`、`variantPurpose`、`admission`、`usageScope` 与 `status`，只有 `completed + passed + active` 可被 release 选择。

<a id="req-002"></a>
### REQ-002 单一 production 生命周期与权利只记录

- acquisition、semantic、review 与 canonical pool 不从环境推断 lifecycle/class。本 producer 的 immutable release build 只有一个类别 `releaseClass=production`，并在 create-once producer release/header/handoff 冻结同值；环境名、临时环境变量、fixture 或下游状态不得改写。production release 的媒体按公开交付 slice 物化，不存在私有 CAS key 或短签交付分支。
- 每个实体头像/主页媒体、文章图、图片作品与视频资产保留 acquisition、真实 rightsStatus、authorizationRequired 及来源、作者、摘要、许可和证据事实，字段闭集只由 canonical schema 拥有。`rightsStatus` 按来源 license 机械派生：开放许可白名单为 verified，其它可读许可为 unverified 并记录原文，不可读为 unknown；新对象和新 release 只使用单一 production 记录契约，旧类别值不能作为当前合法输入。
- 权利只记录不阻断：acquire 不因 license 拒绝下载，publish 事务不因 `rightsStatus` 非 verified、`rightsIssues` 非空或 `distributionDecision=blocked` 拒绝对象，release build 只把 `restricted`/`blocked` 资产计入统计。未取得、生成素材、缺来源字段、不可播放视频与安全/隐私问题仍阻断。
- production immutable release 必须冻结权利状态计数、精确 authorization-required asset IDs、四载体 accepted 计数、逐来源 assets funnel 和 `containsUnverifiedAssets`，供下游运营运行时配置决定未授权内容是否对公众开放；该配置不属于本 producer。
- 访问政策只记录不阻断：每条 ingest 来源行可申报 `accessPolicy=open|robots_disallowed|tos_restricted`（来源站点 robots 与服务条款对自动访问的态度，由 AI 读站点声明后申报），acquire 原样透传到该 source unit 的 `meta.json` 与资产行，publish 事务转录到 canonical 资产记录，release header 把非 `open` 的资产汇总为 `accessRestrictedAssetIds`；缺席即缺席，不补 `open`，任何取值不改变 admission、pool eligibility 或 cohort。
- 水印只记录不阻断，且只由看过像素的 AI 申报：每个媒体资产携带 `watermarkStatus=absent|present|unknown`、`watermarkKind=none|author_signature|platform_logo|stock_agency|other|unknown` 与可选 `watermarkNote`，采集与投影代码只搬运，缺席只能记 `unknown`、不得假定 `absent`；作者签名与平台/图库标识分开记，因为运营结论相反（前者通常可用且不得抹去，后者往往指向非自由来源或预览件）。release admission 与 header 把 `present` 的资产汇总为 `watermarkedAssetIds`，与 `authorizationRequiredAssetIds` 并列供运营逐条审核。不去水印、不给发布物烧制水印。
- 采集代码无法核实、只能按 producer 政策统一申明的资产级记录常量唯一声明位是 `content_distribution.policy.yaml`；`derivedModifications` 写实际发生的降采样、转码与抽帧，空数组只能表示确实无修改。Data、Service、App、Ops 对来源归属和逐图说明消费同一契约，不丢水印或派生修改事实、不以 title 代替 caption；删除旧风险接受字段与按发布类别推断授权的条件分支。
- 当前池的旧记录只能通过 [`canonical-content-identity-recovery`](../canonical-content-identity-recovery/spec.md) 的显式转换或授权退役完成硬切；历史 receipt/release 原字节不改写，退出活跃 reader。声明侧先于 codegen，所有当前正向读写不得双读双写或隐式接受旧类别。

<a id="req-003"></a>
### REQ-003 站点、实体与 creator 深挖的文章、图片和视频来源

- 实体口径是「用户感兴趣、愿意去的一切地方」：景区景点、秘境、网红打卡地、古镇、露营地、温泉、观景台、徒步节点、探险探秘地，不限 A 级评定，不设数量上限；实体类型只从 taxonomy `Entity/地点/*` 现有叶子中选取。homepage 主源必须是百科闭集成员：zh.wikipedia 或头条百科（`www.baike.com`，`sourceKind=toutiao_baike`），百度百科对非浏览器访问返回反爬挑战页，属技术性规避，不在闭集。实体发现以携程景点榜（热度分、点评数、「必打卡」标签、类型筛选）、zh.wikipedia 分层类目（5A/4A/3A、一级博物馆、历史文化名镇名村、国家级自然保护区、各省文保单位）与 AI 按地域给出的秘境名单为前沿，逐条以百科页存在与正文厚度核验。
- Article 的主来源可以是同一实体条目以不同 `publishAngle` 切入，也可以是主题条目页；事实参考可追加携程游记/攻略与景点榜、新闻旅游频道（新华网、中国新闻网）、政府与文旅厅/景区官网公告、磨房户外线路帖、zh.wikivoyage 以及页面为服务端渲染的其它公开旅行 UGC（马蜂窝按 `accessPolicy=robots_disallowed` 记录），全部按 `factual_reference_only` 登记——AI 只取事实、路线、费用与贴士并亲笔原创，不搬运来源表达，来源 URL 全部进入 `sourceUrls`。Article 分类必须覆盖 `摄影`；摄影文章与攻略、游记等使用同一 Post/Article 契约与质量准入，不创建第二套载体。
- Image 来源矩阵按「综合平台 → 垂类、创作者批量优先」运行：Wikimedia Commons（高产上传者 `allimages&aiuser` 全集与 Quality/Featured/Valued 类目）、Openverse API（Flickr CC 与 Commons 聚合，无 key）、Flickr 官方 API（有 key 时 `people.getPublicPhotos`/`photos.search` CC 筛选）、iNaturalist API（research-grade 且 CC 的自然观察，供自然保护区实体）、图虫（`/rest/tags/<标签>/posts` 与 `/rest/sites/<摄影师>/posts` 对合规 UA 直出 JSON，CDN 原图可下载；版权保留 → `unverified`）、Pinterest（用户/画板 RSS 与检索作发现，`i.pinimg.com/236x/<hash>` 改写为 `/originals/<hash>` 取原图；转载物、原始权利未知 → `unknown`）、头条百科标注 `CC BY-SA` 的自有图片、Unsplash/Pexels/Pixabay 官方 API（自有免费许可 → `unverified`）、archive.org/Europeana 等公有领域历史影像。每个资产的 `sourceUrl`、`creator`、原始资产 `directUrl`、取得方式与 `license`/`licenseUrl` 必须回到作品页、平台条款页或官方 API；500px 只作发现。
- Video 来源矩阵按「切题实景、可落实体、热度作排序、频道/UP 主批量」运行：Wikimedia Commons 视频类目与 `filetype:video` 全文检索、YouTube（无 key 时经 `yt-dlp` 以 `ytsearch` 发现、频道 `/videos` 批量并读取单条 `license`/互动指标，只下载 Creative Commons 条目；有 Data API v3 key 时以 `videoLicense=creativeCommon` 发现）、Bilibili（经 `yt-dlp` 拉 UP 主全集与逐条元数据；版权保留 → `unverified`）、Dailymotion API（`unverified`）、archive.org 与 Vimeo CC、Pexels/Pixabay 空镜。频道/上传者/UP 主全集是批量发现入口，入池仍逐条按实体落点、相关性与负面主题过滤；无法取得逐作品来源证据时只保留本次命中。
- 热点信号（携程热度/点评数、维基 pageviews、Flickr interestingness/faves、YouTube/Bilibili views/likes/comments、图虫 favorites/views、创作者粉丝数）与逐载体候选级质量筛选（百科正文厚度与结构化事实、游记长度与实用信息项数与时效、图片分辨率与主体切题与水印类型与长宽比、视频时长与清晰度与实景比例）只作候选排序与可重放的候选级放弃判据，不是 execution 内的门禁，也不落台账。来源层级 `sourceTier`（S1 精选/S2 高产可信创作者/S3 其它开放许可/S4 非白名单许可）与创作者层级 `creatorTier` 同样只记录进 `discoverySignals`，供评分校准回归，不作门。
- 访问合规只区分两类。**技术性规避**仍然禁止：所有站点、搜索和 creator shard 只允许公开直链、平台公开接口、RSS 或人工提供文件，不得规避登录墙、付费墙、验证码、访问控制、DRM 或反爬挑战页（小红书、抖音、快手、西瓜、知乎、微信公众号、穷游 503、去哪儿挑战页、美篇 SPA 等不进入任何自动化路径）。**robots 与服务条款限制只记录、不阻断入池**：新增站点前先读其 robots 与服务条款，并把结论作为每条来源行与每个资产的 `accessPolicy` 事实记录（闭集 `open|robots_disallowed|tos_restricted`，缺席不视为 `open`）；`Disallow: /` 或 ToS 限制自动访问的站点（Pinterest、i.pinimg.com、图虫、Bilibili、YouTube 下载、马蜂窝）照常入池，acquire 原样透传到 `meta.json` 与资产行，release header 汇总 `accessRestrictedAssetIds`。版权保留或权利未知的来源一律入池：`license` 逐字写作品页或平台条款原文（如「图虫用户协议（版权保留）」「Pinterest 服务条款（转载物，原始权利未知）」），脚本按白名单派生 `rightsStatus=unverified|unknown` 与 `authorizationRequired=true`，进入 header 的 `authorizationRequiredAssetIds` 与 `containsUnverifiedAssets`，caption 标注作者与来源链接；这些资产是否对公众可见与后续开发由运营策略决定，不由 Data 侧拒绝。来源侧出网由宿主 AI 点名 exact URL/查询后，以通用工具或 content-production Skill 内的单阶段机械工具执行；Skill `scripts/` 与 `carriers/<carrier>/sources/` 可负责有界请求、来源原文提取、下载与输入构造，不负责选择来源、相关性、评分、review、verdict、后继或恢复。Data `content/source`、`content/execution` 与 `core` 保持零来源网络。API key 只存在于本机环境而不进仓库；使用声明产品与联系方式的合规 User-Agent，同站串行、遵守 Crawl-delay、429/503 停止本次来源请求；多会话预算由宿主协调，不按会话数放大。单来源的 typed failure 只阻断自身，不阻断同 carrier 其他来源。
- CLI 与 receipt 对每个 `displayName/provider` 输出 `planned/discovered/downloaded/accepted/rejectedAssetCount` 及 verified/unverified/restricted/unknown 计数；下载成功不得把 rights 状态升级为 verified。
- 文章有图即 illustrated：只要求至少一张可追溯授权来源的图片并把首图派生为唯一封面，配图张数不设下限，一张图与多张图同样合法；无图即 text_only。封面与正文图可来自不同的可追溯授权来源。illustrated/text-only rate 只作为供给统计，不参与对象准入或规模晋级。
- 视频候选保留 play/like/comment/share/favorite 的真实观测与观测时间，并只在同平台、同主题、同时间桶内按 percentile 排序。缺失项保持缺失并标明不可参与热度排序的原因，不得补零或生成虚假排名。
- ranking-ineligible 视频可以进入 production release；热度信号完整度和 percentile 只作为推荐与供给统计。只有公开可取得、可解码、可播放、无 DRM、未绕过访问控制且通过安全/相关性门的真实视频文件可进入 production release。
- 视频来源字节超过载体预算或容器/编码不在发布闭集（`video/mp4|video/webm`）时，ingest 在下载截面用 ffmpeg 转码为 H.264 mp4 派生体（目标 720p、约 16 MiB，硬上限为载体预算），按派生体重新登记 sha256/mime/尺寸/时长，写 `derivativeBinding` 保留源体摘要，poster 从派生体抽帧；每档都装不进才判否。四载体的来源发现与选材由 AI 按上述来源矩阵决定，Skill 工具只展开显式查询并保留来源证据；发现快照只放 `.qwq_output/data/local/workspace/**`。快照可重新取得不代表外部网页或 AI 判断能逐字节复现，已冻结执行输入不得被其他轮次覆盖。
- homepage 与 article 的百科来源必须同时从可见正文与结构化信息区取证不可变结构化事实。`source.md` 由 AI 以通用工具把来源正文与信息区原文落盘（维基 API extract 与信息框 wikitext、头条百科页内结构化 JSON 展平、游记页 HTML→text），再由 AI 亲笔附上「信息区取证」段；不要求 AI 逐字转写正文。信息区的字段名与取值只在语义一致时采信，字段名指向的受治理字段与解析出的取值类型不一致时该候选事实作废，不落入其它字段。

- 原生多图作品以来源命名空间与原生作品身份分组，一个作品对应一个 image target，选中的资产保留来源顺序与逐资产权利；部分选择必须显式，不按图片数量拆成多个作品。仅同作者或同日期不足以合并跨页面作品。author 的逐资产说明按 Data author schema 表达，投影到既有 `assets[].caption`，不得改变总 caption、消费字段或已发布字节；同名资产必须能在同一对象内唯一投影。
- homepage 按移动端模板有据整理，维基优先作骨架，头条百科只补同实体缺失事实；无维基可用另一闭集百科。主源须核对名称、类型与行政区；空章节、冲突或无时效依据的票价不补写。多百科产物显式声明本对象已取得的主源，source catalog、实体头与正文归属使用同一选择，不依赖 source unit 排序；模板、长度与评分只作 advisory。

<a id="req-006"></a>
### REQ-006 零仓内编排与 legacy 硬删除

- 旧 managed SDK/provider、agent/controller/queue/campaign/recovery、runner/fleet/lane claim、stage-gate registry、semantic prepare/record wrapper、自动恢复与 execution-state reducer 必须物理删除；禁止 shim、dual-read、retired-path fallback 或 sequence-017 兼容。
- 删除是本 contract-reset 的已批准架构决定，不以 `GWT-034`、`OPEN-006`、stable-production proof、旧 proof、任何 App/API UAT 或 terminal retry evidence 为前置授权。
- 宿主并发、模型选择、截止与会话重启是宿主原生能力，只能作为外部诊断，不进入仓库业务对象、producer handoff 或下游 promotion。
- 每个 stage 的 verdict、typed issues 与 result refs 由宿主 AI 显式提交；代码只执行 OPEN input freeze、CLOSE create-once 与窄 IO/verifier，不建立第二终态 writer。
- 单阶段批量不是编排：`task init` 一次建一轮多个 execution、`task acquire` 一次 ingest 一个 execution 的多个 target、`task seal --stage 5.review` 从一份 execution 级判断输入扇出到逐对象文件，都只在一个阶段内对显式输入做无状态、无恢复、无跨阶段推进的展开；逐 target 结果独立报告，单 target 失败不影响同批其余。凡跨阶段推进、读取 receipt 决定下一步、重试或恢复，都属被禁的 runner/controller。

<a id="req-017"></a>
### REQ-017 工具与宿主 AI 的职责边界只按可伪造性划分

- 归工具的判据只有一条：同样字节换任何执行者必须得到同样结果，且结果不可伪造。闭集为：从字节算 sha256 并按来源声明的 sha1 交叉校验、mime/尺寸/时长探测、按载体预算降采样与转码、抽 poster、content library CAS 与硬链接、create-once source unit 与 receipt、schema 校验、单对象原子事务、canonical 序列化与 merkle、cohort 规范化与 handoff、`pool-query` 只读口径、随体闭包比对。
- 归宿主 AI 的判据只有一条：需要理解语义或看见内容才能得出结论。闭集为：与用户澄清约束、制定与推进规划、并行派发子 Agent、检索与选题、点名来源与相关性、读来源页取权利事实、下载字节、看图判水印与相关性、写 `source.md` 与四类 carrier 产物、评审判断、cohort 与 milestone。这些语义判断与流程推进以宿主原生能力（检索、读页、终端、看图、子 Agent、规划）和既有通用 Skill（`continue`/`plan-next`/`review`/`commit`）完成，不在仓内再实现一遍。下载、提取原文、构造输入等机械部分可由宿主调用 Skill 内工具执行；工具不得选择 approved 对象、伪造 actor 或自动调用下一阶段。
- 来源可达与权利事实的取证方式随之改变：「来源 `https://` 可检索」由 AI 申报的 `sourceUrl`/`directUrl` 形状与来源声明的 `sha1` 对本地字节的交叉校验共同成立，不再由脚本出网验证；license 原文与 `licenseUrl` 必须逐字抄自来源文件页，`rightsStatus` 仍由「申报 license 字符串 → 开放许可白名单」纯函数派生，AI 不直接给出 `rightsStatus`。这是取证方式的显式降级：可审计性从「机器取自 API」变为「AI 申报 + 本地字节自证 + 人可按 `sourceUrl` 复核」。
- 过程状态不建第二真相源：「已存在什么」只读 `release pool-query`，「在飞 execution 到哪一步」只读 `_shared/receipts/`，本会话在飞状态只活在宿主 todos；候选级放弃靠可重放判据（条目缺失、消歧义、正文过薄、水印类型、相关性）在再次选题时自然重现，不落台账；人工裁决过的例外写入 `OPEN-###`。

<a id="req-018"></a>
### REQ-018 质量评分与热度信号只记录不门禁

- 每个载体拥有一套由 Skill reference 声明的多维质量评分（整数 1–5，维度名为闭集，各载体六维），由 reviewer 会话在评审时逐对象申报为 `content_review.json` 的可选 `qualityScores{维度: 分}` 与可选 `qualityNotes`；`task seal --stage 5.review` 只做 schema 校验与逐对象透传，publish 事务原样写入 canonical 对象包。评分缺席合法，缺席不得由脚本补零或推断。
- 来源热度信号（携程热度/点评数、维基 pageviews、Flickr interestingness/faves、YouTube viewCount 等）由 AI 在 ingest 清单的来源行以可选 `discoverySignals{信号名: 数值}` 申报，acquire 只透传到该 source unit 的 `meta.json`。
- 两类记录都不参与任何判否：不改变 `decision`、不进入 publish/release admission、不进入 cohort 选择、不由脚本聚合成第二状态源；reject 理由仍只有关键论断缺证据、安全/隐私、素材不相关或不可播放三类。
- 评分体系是草案：横向校准由 AI 对已绑定独立内容仓中的审核原件只读抽样完成，修订只发生在 Skill reference 的维度锚点与候选级筛选阈值，不改门禁与 schema 闭集之外的字段；仓位置与布局不参与评分事实。

<a id="req-007"></a>
### REQ-007 confirmed demand 沿 producer 六步推进到 immutable handoff

- producer 完整路径固定为 `confirmed carrier demand -> identity-only candidate-backed task init -> acquire -> author -> review（三份 seal receipt）-> 逐对象 publish -> release finalize（explicit cohort immutable release + handoff）-> END`；旧控制面与任何消费阶段不在现役闭包。
- `task init` 的 deterministic 三文件原子初始化已实现并由 local contract 锁定；真实 confirmed demand 的宿主消费证据由 [`work-request-compilation` OPEN-001](../work-request-compilation/spec.md#open-001) 跟踪。每一步只消费前一步 immutable ref/digest，失败不得跳阶或用旧 receipt 冒充当前完成。
- producer release/handoff 不包含 UAT sample authority、environment consumer facts、import/activate/readback、App/API UAT、EAF、promotion 或 rollback。下游可只读 handoff 独立消费，但其成功、失败或未运行均不得生成 producer receipt、回写 execution 或改变 producer END。

<a id="req-008"></a>
### REQ-008 发布只消费显式 cohort

- release 只消费调用方显式提供且经 schema 验证的 exact cohort；不得扫描全池后隐式选择“全部可发布对象”。M1/M10/M100/M1000 按 `cumulative_unique_finalized_objects` 累计达标，每级都必须形成自己的 full explicit cohort、immutable release 与 producer handoff。达标判据是 cohort 四载体计数**不低于**里程碑目标，release header 分别冻结实际 `counts` 与 `milestoneTargets`；cohort 的 `objectRefs` 排序、canonical 字节化与 `expectedCarrierCounts` 派生由 finalize 机械完成，不要求调用方手工对齐。
- build 在写入前逐对象重验 canonical identity、review、rights 与随体 source/media closure；任一对象失败只形成 typed exclusion，不改写 cohort 或其它对象，不隐式修复包或依赖原 content library。
- release identity、cohort digest 与 payload 一次冻结并 create-once；重放只接受逐字节相同结果，任何漂移 fail closed。更高级别可复用 canonical 对象及其首次 producer execution/publish proof，handoff 以 canonical publish proof 为凭，不伪造新 receipts；重复 identity 不增加累计对象数。
- 里程碑 cohort 与 producer handoff 继续是仅有的两份 terminal 事实，由 finalize create-or-same 保存到独立内容仓的 release 边界；不另建 catalog、状态账本或副 handoff。现有 immutable bundle、旧 terminal 原件与运行审计不因迁仓删除或改写；可重建承诺必须覆盖固定时间、cohort 与 exact build 输入，并由实际重建验证支持。
- handoff 同时绑定工程 baseline/实际契约摘要及内容仓身份、所选稳定 ID/版本/包摘要与定位清单的 exact 快照；只有内容 commit 与实际字节匹配才记录 commit，不以源码提交冒充内容已提交，不新增双提交仪式。
- canonical 包按稳定资产身份绑定相对随体媒体与摘要；环境交付键只在 release 物化时派生，运行 URL 由既有 media endpoint 生成，不把本地路径或来源直链交给 App。包内摘要不包含外层地域/分区定位，定位清单包含它；改变包字节须新版本/摘要，纯移动不重做 review。

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
### REQ-016 Data 媒体只按单一 production 交付契约消费

- 新 Data projection 必须声明稳定资产身份与 public 交付模式，媒体从唯一 release manifest 绑定公开 slice；旧发布类别、私有 CAS 交付字段或缺失绑定均 fail closed，不按 URL、环境或缺席推断 public，也不保留 previous-version adapter。
- 视频时长、封面、资产顺序、摘要与来源说明从 importer 到 App 保持一致；Range 播放的真实验证独立于生产端测试，不以可探测文件替代可播放证据。
- 仅删除 Data release 专属 research feed、readback、role/whitelist/attestation 与 isolation 分支；跨业务共享的私有媒体、原图授权及 signed_grant 安全能力不在本 Story 的退役范围。

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
- 采用来源的 URL、原作者、时间、许可/授权/访问事实及必要证据在作品内聚；相同来源可在不同作品保留少量独立审计元数据，不建全球 source resolver。只保留真实、必要且被引用的证据，原始大下载非默认成品，生成的 manifest 副本不是第三方授权证明。
- 删除重复 asset/creator/tag 引用旁车及独立 source catalog/rights 投影，真实原件转入随体来源；消费者只从 manifest/source 生成公共 attribution，不再手工维护第二份事实。
- 独立 reviewer 的原结论与原始审核对象摘要保留，迁移只追加原件 binding，不把旧审核改成新审核。追加式 pool records 保留入池/退役事实并绑定包与 review 摘要，不复制完整 manifest/source；审核结论与入池状态不能相互替代。
- 单对象 publish 在同一内容仓共享锁下校验临时包并原子可见；所有源码工作树对共同根使用同一锁，不随各自 output root 漂移。仓 metadata 只承载身份、布局版本与契约摘要，不承载绝对路径、统计、active release 或凭据。

<a id="req-021"></a>
### REQ-021 稳定实体导航与媒体失败只做局部降级

> 本要求只冻结内容与引用边界；具体 query/wire 与 App 恢复动作由原 Service/App owner 拥有，不纳入 producer END。

- 实体引用使用稳定身份和名称快照，不用存储路径、分区或当前标题跳转。正文渲染不逐实体请求或 HEAD，用户点击时才由已有目标页执行权限/下线判断；普通实体下线不级联删除作品、原文或已采用媒体，不重写历史 release。
- 文章导入复用 Entity 的 exact 主页映射生成既有 mention 投影，不新增 ID 哈希规则；缺映射保留普通文字而非无动作链接。图集/视频 caption 与实体介绍保持可读名称，不扩建 article-only slice、通用富文本或引用卡片；内部语法不泄露路径。
- 正文/封面图失败保留文字和局部占位，图集坏一张保留顺序/页码且可继续滑动；视频失败保留可读 poster/caption 并结束有界尝试，已知不存在不自动重试；poster 或字幕单独失败不阻断可用视频。来源网页失效不影响随体成品。
- 复用当前正/负缓存与错误映射，图集实际加载共享负缓存，视频命中负缓存不续期或再次启动恢复；用户显式重试与成功清理仍服从原语义。不新增引用 TTL、逐图探活、健康注册表、自动修复、跨服务事务或缓存广播。

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
### GWT-002 production release 以公开交付形态被环境消费且权利只作记录

- GIVEN 四载体对象共享同一 source revision/digest/entity catalog digest，素材已取得且完整记录来源与权利事实（含 `unverified`/`unknown`/`restricted` 资产）。
- WHEN 生成 `releaseClass=production` 的 immutable release 并由下游环境导入。
- THEN release header/attestation/handoff 的 `releaseClass` 与 `productLifecycleState` 同为 `production`；`media_manifest.json` 每条资产只产 `publicSliceKey`，不产任何私有 CAS key；导入投影把每条媒体引用写为 `accessMode=public`。
- THEN 权利状态只进入 header 的权利计数、`authorizationRequiredAssetIds` 与 `containsUnverifiedAssets`，不排除任一对象；未取得、生成素材、缺来源字段与不可播放视频仍被阻断；文章批次配图率只写入统计，单篇 illustrated 文章只要求恰好一张封面且全部配图来源可追溯，配图张数不设下限。
- THEN 环境 readiness 以 fresh guest 证据闭合，不要求隔离证明、白名单账号或 attestation；Alpha/Beta/Gamma 的 Environment Ops scheduler request 绑定同一 exact integration candidate，Prod acceptance 另走 RC Qualification package acceptance、`ReleaseTagAdmissionFact`、`ProdActivationAdmissionFact` 与 hosted facts，不生成 Prod EAF。
- THEN 未授权内容是否对公众开放由运营运行时配置决定（[`OPEN-024`](#open-024)），该配置不回写 producer release、cohort 或 handoff。

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

- GIVEN 一个步骤无合格对象或硬事实不闭合。
- WHEN AI 调用 `task seal`。
- THEN actor 与 verdict 由 AI 显式提交，seal 自行校验硬事实并 create-once 写 receipt；不存在第二状态 writer。
- THEN pass 后继只按 Skill 固定顺序，receipt 不包含代码派生 nextAction/recovery stage。

<a id="gwt-016"></a>
### GWT-016 下游消费的数量与 entry surface × carrier 矩阵可闭环复核

> 本场景及 `GWT-028` 至 `GWT-033`、`GWT-035` 只验收下游 consumer/environment 行为，不构成 producer 准出；producer handoff 不拥有其中任何 sample、UAT、EAF、promotion 或 rollback 事实。

- GIVEN 一个已确认请求为 homepage/article/image/video 分别声明正整数对象数量，同一请求沿 producer 单轨形成 immutable production release，且下游验收清单为 entry surface × carrier 二维矩阵。
- WHEN Alpha 依次完成 import、projection/API/media verify、activate，并由每个 required cell 的 repo-relative runner 执行 production Remote App UAT。
- THEN 每载体均满足 `selected = imported = projected = verified = readback = qualified`。`qualified >= requested` 表示该载体达标；`0 < qualified < requested` 表示 partial，`shortfall = requested - qualified`，已合格对象仍可见而不伪造成达标。
- THEN 16 个 cell 各自显式声明 `required|not_applicable`；required cell 具 repo-relative 验收锚点引用、runner 与绑定同一 release identity 的 raw `ReadinessCaseResult`，not_applicable cell 具可复核理由与验收锚点引用。carrier 与 entry surface 不互换，micro 不属于 carrier 轴。
- THEN import、projection 或 API/media verify 在 activate 前失败时 candidate 停在对应 typed 终态，previous active pointer 不变，且不生成本 candidate 的激活成功事实。
- THEN activate 后任一 required cell 失败时只记录 typed failed result；操作者显式执行 rollback 后，rollback/readback 必须证明四个 entry surfaces 全部恢复同一 previous release identity，`durationMs <= 300000`。超过预算、pointer 未恢复或任一 surface 混合 identity 时终态为 canonical `rollback_failed`，本次 raw 结果保持可读且旧 release/receipt 不得替代失败 cell。

<a id="gwt-020"></a>
### GWT-020 宿主 AI 六步沿 acquire/author/review 三份 seal 单轨闭合

- GIVEN 一个 identity-only candidate-backed execution 与 canonical Skill。
- WHEN 宿主 AI 依次执行 acquire、author、review 三步，每步直接写业务产物后调用 `task seal` 提交真实 actor 与 verdict；seal 自行校验硬事实并 create-once 写 receipt。
- THEN 不存在 stage-open、宿主 verifierFacts、stage-gate registry、semantic prepare/record、runner/fleet/lane claim、自动恢复、execution-state reducer 或代码派生 next；pass 后继只按 Skill 固定顺序，blocked 后新建 execution。
- THEN candidate binding 只冻结目标对象身份，init 输入是一份 round spec（`executionId` 逐 carrier 给出，`familyRef` 缺省派生，逐 target 只写身份；homepage 的 `region` 在 init 即校验为现有行政区 tag），`entityCatalogDigest/candidateCount/status/quota` 等可派生字段不由 AI 手写，canonical 字节化由脚本完成；`acquire` 由 AI（主会话或该 execution 的 author）出网取得来源并按 execution 提交一份 ingest 清单（逐 target 的本地文件路径 + 申报的 `sourceUrl/directUrl/license/licenseUrl/creator/sha1/description/relevance` 与水印三字段，可选 `discoverySignals`；page 来源附 AI 以通用工具落盘并亲笔附取证段的 `source.md`），脚本零网络地从本地字节生成 source units/source refs/CAS、sha256、mime/probe/poster 硬事实，按申报 sha1 交叉校验字节，按申报 license 派生 `rightsStatus`，不阻断；超预算视频转码为 mp4 派生体；不存在 2.quality/3.compose 产物。
- THEN `author` 每对象只写 `page.md|draft.article.md|image_work.json|video_script.json` 之一，标题/tagRefs/creatorProfileId 由产物自身声明且 tagRefs 必须解析到 taxonomy、creatorProfileId 必须解析到 creator 注册表、homepage 必须至少一个百科 `page` 来源，三者均在 `002-4.draft` seal 逐对象校验而不是 publish；seal 一次报出全部对象的违规，违规对象只以 typed issue（含 `objectRef`）退出本 execution 且不进入 resultRefs，至少一个合规产物即 `pass`，零合规才 `blocked`；`4.draft` 目录允许存在草稿以外的文件；`002-4.draft` receipt 冻结同一 execution 唯一真实 author actor/invocation 与合规产物 exact refs/digests。
- THEN `review` 由另一个真实 reviewer actor 会话执行，按 execution 提交一份判断输入，覆盖集合恰为 `002-4.draft` receipt 的 resultRefs 对象集合，逐对象只含 `decision/blockingIssues/advisories`（可选 `safety`、逐资产 `assetRights[].issues`、只记录的 `qualityScores/qualityNotes`），只在证据缺失、安全隐私、素材不相关或不可播放时 reject，权利疑虑写入 advisories；`003-5.review` seal 把该输入机械扇出为逐对象 `content_review.json`，从对象实际引用的资产补齐 `assetRights`（缺省 approved）、缺省 `dimensions` 与 schema/stage/executionId/objectRef/draft 字段，原样透传 `qualityScores/qualityNotes`，并冻结 reviewer actor/invocation 与 exact ref/digest。author 与 reviewer 必须不同 session/runId，可为同一 model family，任一方可以是宿主派发的独立子 Agent 会话。
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
- THEN 目标唯一绑定冻结实体身份；canonical ref 不由物理路径推导，实体按已核实地域与同名组分配 locator；无实体对象、名称歧义或身份冲突时结构化失败。
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
### GWT-032 production 媒体身份与逐图说明无损消费

- GIVEN 新 production release 含有序多图作品和可播放视频，每条媒体有稳定资产标识、摘要及 public slice，多图具有不同 caption，另有旧类别和私有交付字段反例。
- WHEN importer、query decoder 与 App 消费同一 release manifest。
- THEN 来源归属、水印、派生修改、资产顺序与逐图 caption 保持一致，caption 不以 title 替代；App 图集展示逐图说明，视频 Range 播放有独立真实证据。
- THEN 旧类别、私有交付字段、缺身份及摘要漂移均拒绝，不自动适配或默认 public，不读冗余资产旁车。

<a id="gwt-033"></a>
### GWT-033 删除 Data 专属隔离不削弱共享媒体授权

- GIVEN Data release 已统一 production，另有无关业务仍使用原图授权与 signed_grant。
- WHEN 调用内容 feed/detail 与共享媒体授权边界。
- THEN Data 内容不要求 research session、白名单或 attestation，旧专属 operation/config 不再注册；未授权内容可见性仍由运营单点配置决定。
- THEN 无关业务的身份、配额、签名与到期校验保持原约束，非法请求仍拒绝，不因删除 Data 分支放宽共享权限。

<a id="gwt-034"></a>
### GWT-034 四载体 producer 里程碑按累计唯一对象形成独立 handoff

- GIVEN 集中式架构禁令要求已退役编排、兼容读写和自动恢复在生产源码、schema、control plane、测试正例与 active specs 中物理归零；已有一组通过当前 Skill 生产并 finalized 的 canonical 对象及其原 execution/publish proofs。
- WHEN 依次形成 M1、M10、M100、M1000，每级按 `cumulative_unique_finalized_objects` 选择 cohort、构建 immutable production release 并物化 producer handoff；cohort 四载体计数不低于该级目标即达标。
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
- THEN manifest 单写身份、正文引用、有序媒体与主体依赖，homepage/article 另有唯一最终正文而 image/video 无伪正文，来源事实与必要原件随体，完整复制后不依赖原 execution/library 消费。
- THEN 重复 refs/source catalog/rights 旁车不再读写，消费者只从唯一 manifest/source 投影归属，缺证据或非法引用 typed 拒绝。
- THEN 原 review 结论/审核对象摘要与 records 原件可复核，迁移只追加 binding/新版本事实而不伪造重新审核，旧 release/receipt 与已保护媒体保持原字节。
- THEN finalize 的现有 cohort/handoff 以 create-or-same 绑定内容仓身份、所选 ID/版本/包摘要与定位快照，无匹配内容 commit 不冒称已提交，不强制双提交或隐式补库。

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

## 6. 依赖

- 前置要求：父能力的 execution、review 与 release 契约。
- 上游事实：来源、目标集和审核结果。
- 下游结果：immutable release 或结构化阻断报告。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-026"></a>
### OPEN-026 载体工具重构与多源作品投影待验证

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺载体工具与多源投影的全部准出证据，离线回放不能证明外部来源持续可达、真实宿主渐进加载或消费者逐图说明展示。
- 尚缺实现与证据：来源工具、多图说明与同名投影、显式主页主源绑定及 acquire 后只读身份预检已有实现；Service→App 逐图 caption 映射已进入工作树，仍须以最终契约回归和 fresh runtime 展示证明，不把实现存在等同下游验收。
- 尚缺验收证据：[`GWT-039`](#gwt-039) 已有子句级 local_contract 绑定，上下文预算、Skill 手写源码分类、图片稳定引用/重复作品/身份漂移与主源投影回归已收敛；仍缺迁移后真实宿主小轮、跨层消费及当前候选正式准出证据，不能以离线回放替代。
- 完成判定：[`GWT-039`](#gwt-039) 子句级测试、现有 producer/consumer 合同回归、上下文与 Feature Tree 门禁在同一增量通过；旧配方与有效引用完成删除替换。
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
- 里程碑语义：M1/M10/M100/M1000 按 `cumulative_unique_finalized_objects` 计数，每级形成自己的 full explicit cohort、release 与 handoff；更高级别复用 canonical 对象及其 canonical publish proof，不伪造新 receipts。任何旧 schema 字面上的额外 milestone 不扩大本 OPEN 的验收闭集。
- handoff 边界：handoff 严格绑定 release/cohort、四载体 counts、逐对象 content-pool query（canonical publish proof）、`producerBaselineRevision`、`producerContractDigest` 与 create-once identity；不包含 UAT sample authority、import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback facts。
- 当前证据：六步路径已取得 M1/M10/M100 三级真实 producer E2E，均为 author 与 reviewer 不同会话、`release finalize` create-once handoff 且 `handoff-verify` 只读重放通过——M1 release `20260906--travel-research-m1--six-step-tangqi-001`（塘栖古镇 `1/1/1/1`，来源 zh.wikipedia + Commons）；M10 release `20260906--travel-research-m10--six-step-cumulative-001`（`10/10/10/2`，`producerBaselineRevision` `d5226a78acafc940887429d95515d1f611af4d75`，复用 M1 canonical 对象）；M100 release `20260906--travel-research-m100--six-step-cumulative-001`（`100/100/100/10` 共 310 对象，`producerBaselineRevision` `6f826e461128255e1bb4f2a585c96bc7152d657e`，从累计已发布 104/103/104/11 canonical 对象中显式选出，复用 M1/M10 对象与其 canonical publish proof，未伪造新 receipts）。
- 尚缺验收证据：M1000（不低于 `1000/1000/1000/100`；运营生产目标为四载体各 1000，视频超出底线的部分不改变里程碑判据，实体前沿按 [`REQ-003`](#req-003) 口径开放不设上限）按累计唯一对象形成独立 `releaseClass=production` cohort/release/handoff 的证据；历史 r03 `release pool-query` 曾记录 eligible 141/149/130/14（该计数只适用于当时契约，不是当前新 reader 的资格；当时已排除 [`OPEN-021`](#open-021) 实体闭包；零网络 ingest 契约下的真实轮次 `sichuan-r01`、`recover-r02`、`national-r03` 以子 Agent author 与独立 reviewer 走通，其中 `national-r03` 一轮四 execution 发布 24/24/20/5 个对象、含 5 个头条百科主源实体，每个 `content_review.json` 携带六维 `qualityScores`，1.download/4.draft 逐对象退轮各在真实 execution 中出现一次以上），当时里程碑缺口约 859/851/870/86。当前占位、缺失依赖与迁移后有效计数按 [`OPEN-021`](#open-021) 重算，不沿用历史数字。production 契约链路已由冒烟 release `20260906--travel-production-smoke--six-step-h06-001`（cohort 5/1/4/2 ≥ M1 目标，`releaseClass=production`，media_manifest 仅 `publicSliceKey`，`handoff-verify` 通过）证明可走通，含 Commons 超预算 webm 转码 mp4 的两条视频。M1/M10/M100 三级 release 以当时的 `releaseClass=research` 契约封存，作为不可变历史证据保留，不再按 production 契约重放 `handoff-verify`；后续 M1000 必须以新对象包契约累计覆盖全部合格对象；已有 production 冒烟 release 不因此被否认或改写。视频缺口的成因是发现方法（未沿 Commons `Videos from <地区>` 类目树检索）与 50 MiB 预算下缺少转码分支，已由 [`REQ-003`](#req-003) 转码子句承接。局部 schema/local_contract/静态 gate PASS 不替代此证据。
- 完成判定：[`GWT-020`](#gwt-020) 全部 producer 子句与 [`GWT-034`](#gwt-034) 由同一条可追溯 producer proof 链通过；M1 证明首次对象生产，后续各级证明累计唯一对象、原 proof 复用与独立 cohort/release/handoff。下游 Alpha 不参与关闭。
- 依赖：真实 provider、一个真实 author actor 会话、另一个真实 reviewer actor 会话、canonical publish 与 release/handoff；环境 CLI/实现不在依赖中。

<a id="open-015"></a>
### OPEN-015 单轨 production 图集与视频尚缺 fresh App 消费证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺新 caption、SourceAttribution 与公开媒体绑定在同一 release 的 fresh App 消费证据；Data 私有发布分支随单轨契约退役，不能以旧私有 MP4 UAT 或 previous-version adapter 代替验收。
- 尚缺实现与证据：完成 [`OPEN-024`](#open-024) 的消费者硬切后，在有明确授权的环境对同一 candidate/release/runtime 执行 API readback、App 图集切换/逐图说明与视频 Range 播放；Dart 修改后执行 hot reload/restart。环境、设备或 runner 不可用时保持 typed blocker。
- 完成判定：[`GWT-016`](#gwt-016)、[`GWT-030`](#gwt-030)、[`GWT-032`](#gwt-032) 的当前源码/契约测试与 fresh raw UAT 分层通过。Alpha 只证明 Alpha 消费，不能冒充 Gamma 或 EAF；后者仍按各自环境 owner 的独立契约验收。
- 依赖：新池与新 release、明确环境授权、Service/App/Testing/Ops owner；不恢复旧专属私有媒体路径。

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
### OPEN-017 Data 私有 HLS 承诺退出范围，退役证据待核验

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 Data 专属私有交付正向入口退役及共享授权不受影响的回归证据；单轨 production 不再需要专属私有 HLS，取消原 future 能力承诺，不伪称 HLS 已实现。
- 尚缺验收证据：随 [`OPEN-024`](#open-024) 验证 Data 专属私有交付正向入口与旧兼容分支均已删除，同时共享原图授权、签名与 unsupported HLS 仍 fail closed。
- 完成判定：[`GWT-033`](#gwt-033) 的退役和共享安全回归通过；不再要求实现本 Story 范围外的私有 HLS。
- 依赖：Service/App/Ops 当前 candidate 的精确静态与行为证据。

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
- 影响或价值：publish 截面的实体 schema 门（[`GWT-036`](#gwt-036)）只拦新投影，门落地前已发布的 canonical 实体仍缺合规处置；历史曾定位 7 个不合规样本（不是当前全池无效对象总数）：`地点/景区/成都熊猫基地西门` 的 `primarySource` 为 `sourceKind: encyclopedia_primary`，缺少 `policyRevision/canonicalUrl/snapshotHash/entityName/extractor/title/sourceUseMode` 与 `geoTagRef`，它被 M10/M100 cohort 的 5 篇 posts 以 `entityRefs` 引用，导致这两级 release 在 Alpha `homepage_import` fail closed（typed 证据为该 apply run 的 `result.json`，`failedStage=homepage_import`）；另 6 个门前 legacy 实体 `乐山大佛`、`峨眉山`、`成都大熊猫繁育研究基地`、`泸沽湖`、`海螺沟`、`青城山` 的 `sourceAttribution` 缺少 `derivedModifications` 且多出 `riskAcceptanceId`，当前不在任何 cohort。
- 尚缺实现与证据：按 [`canonical-content-identity-recovery`](../canonical-content-identity-recovery/spec.md) 对全部当前对象逐项冻结 before 身份、摘要、来源/review 与依赖，构造满足新契约的完整 staging；证据充分者迁移，不能证明者经精确授权连同无法修复的依赖退役删除。旧 excluded 只作历史诊断，取消“永不入 cohort 但保留活跃树”的终态。
- 当前盘点口径：snapshot 只计物理占位（含作者）；pool-query 的 objects 还包含展开的缺失依赖，occupied/invalid 与 absent 必须分开。新记录契约下旧计数不能用作当前 eligible，历史错误与本次错误分别保留；不得因记录词汇错误较早触发而假定原 payload/rights 问题已经修复。
- 完成判定：全量当前对象迁移或授权退役均有终态，活跃实体全部满足 [`GWT-036.t3`](#gwt-036)，没有旧结构、悬空依赖或永久 excluded；媒体与旧 release/receipt 原字节不变。新 release 在授权 Alpha 的 `homepage_import` closure 属独立消费证据，不以 producer 测试替代；不得手改摘要补 passed、放宽 schema 或在导入器加 fallback。
- 依赖：单轨 schema、受治理全池 cutover、精确删除授权与独立 review；Data ship 与 homepage 导入器只读新对象，不参与修正。

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
### OPEN-024 下游 research 隔离机制待物理删除并由运营可见性配置替代

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：producer 已收敛为单一 `releaseClass=production`（[`REQ-002`](#req-002)）。Service/App/Ops 的单轨实现尚未完成，工作树内已有公开媒体、来源署名、逐图 caption 与 authoring-source/codegen 改动，但不得把局部删除或生成校验当作整个消费者闭环。
- 尚缺实现：逐项完成 Data 专属 research feed/readback、role/whitelist/session/attestation、Ops isolation 命令/探针及四环境隔离配置的物理退役，正向调用与生成物零残留（[`REQ-016`](#req-016)、[`GWT-032`](#gwt-032)、[`GWT-033`](#gwt-033)）；保留共享原图授权、签名和非 Data 业务的有效安全能力。未授权内容的公众可见性仅由下游运营配置按真实权利事实决定，不回写 producer release、cohort 或 handoff；该行为仍需本次静态、local_contract/api_integration 与授权环境证据。
- 尚缺验收证据：全仓静态检查零 `releaseClass=research|commercial` 正向引用；四入口对 production release 的匿名可见性由运营配置单点决定并有 local_contract/api_integration 覆盖。
- 完成判定：[`GWT-002`](#gwt-002) 的公开交付子句由下游 local_contract/api_integration 绑定，[`OPEN-015`](#open-015)、[`OPEN-017`](#open-017) 随 research 私有媒体退役一并关闭或改写；不得以保留 research 分支作 fallback、dual-read 或环境名推断可见性关闭本 OPEN。
- 依赖：`lane/product-mainline`（Service/App）与 `lane/ops`（stackctl、环境 manifests）；Data 无准出依赖。

<a id="open-025"></a>
### OPEN-025 最小随体对象包与跨端单源消费尚未闭合

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺新随体对象包与跨端单源消费的完整证据。当前 Data/Service/Ops 已有 manifest 单源、production 与 cutover 成果，全部保留；不能把已有三旁车收敛视为随体媒体、来源原件、审核 binding 与独立仓 handoff 已完成。旧真实池仍须受治理转换，不以固定文件数验收或借精简丢失审计。
- 尚缺实现：按 [L2 DEC-031](../design.md#dec-031) 同步实体事实入 manifest、采用来源与必要证据随体、最终媒体完整复制及 records 收敛。旧 source catalog/rights/生成式 snapshot 的真实事实迁入 source，删除重复投影而保留第三方原件、review 原结论/对象摘要及历史 records；creator 身份/profile 仍独立。verify 与消费者必须只读，不再隐式恢复 library。
- 完成判定：[`GWT-041`](#gwt-041)、[`GWT-022`](#gwt-022)、[`GWT-023`](#gwt-023)、[`GWT-036`](#gwt-036) 与 [`GWT-038`](#gwt-038) 的改动子句在新闭集上由真实测试直接绑定；完整复制到无 execution/library 的目录仍可校验，来源缺失、媒体损坏与逃逸可区分；同一新 release 经唯一 reader 消费，旧 release/review/receipt 与保护媒体摘要不变。不以 dual-read/dual-write 或重算旧审核摘要关闭。
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
- 完成判定：[`GWT-042`](#gwt-042) 五条结果分别有真实 importer→typed query api_integration 与 App 局部失败/缓存 local_contract 绑定；授权环境的实体下线点击返回、单图失败可滑动及视频有界停止另有 fresh UAT，不以局部 PASS 关闭。
- 最小测试入口：Entity homepage importer、Content release importer 与既有 article mention Widget 测试；App `image_book_canvas`、`video_player_widget`、主页错误展示的现有短 local_contract，测试需直接绑定 `GWT-042.t1` 至 `t5`。Dart 改动按 App 规则热重载，未连设备保持未验证。
- 依赖：Service/App/Ops 原 owner 与明确环境授权；不是 producer handoff 的前置。
