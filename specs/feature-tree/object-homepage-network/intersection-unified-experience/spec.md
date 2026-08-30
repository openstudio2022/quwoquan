# L2 Business Capability：交集统一体验与推荐 (`intersection-unified-experience`)

> 所属领域：[`object-homepage-network`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以统一的交集事实、置信度、保鲜期和展示契约驱动发现、对象主页、圈子、聊天、个人主页与助理场景

## 2. 范围与非目标

### In Scope

- 六场景（S1–S5 + 横切句型）primaryText 单句展示与 G2 门禁。
- 我的主页「我的交集」聚合入口：总数 + 最多 3 维度红点 + 自上次新增列表 + 打开清零。
- profile/entity/circle 三类主页移除 demo 问小趣 dock。
- 全局搜索交集 Tab 与 connectionState 分组消费 intersectionReason 子集。
- 首页与各频道（含校园、旅行）交集推荐卡重设计：去关注按钮、头像 + 名字 + 红计数。
- 实体主页与圈子主页的 gamma-local 真实 bundle、impact、related groups、object intersections 端云闭环。
- IntersectionReason 字段收敛、recommendation/intersection 域契约、viewer_object_intersection 读模型。
- 事实与概率分通道、保鲜期、跨会话推荐冷却窗口、曝光到转化漏斗埋点。

### Out of Scope

- 交易、支付、预约闭环。
- 第二套标签枚举或端侧拼接交集文案。
- following_subject 关注列表未读机制改造。

## 3. Journey / Scenario 贡献

- [`JNY-011 / SCN-026`](../../spec.md#scn-026)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：以统一的交集事实、置信度、保鲜期和展示契约驱动发现、对象主页、圈子、聊天、个人主页与助理场景，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`circle-homepage-intersection-redesign`](./circle-homepage-intersection-redesign/spec.md)：标题统一为「圈子打动的人」，文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。
- [`entity-homepage-intersection-redesign`](./entity-homepage-intersection-redesign/spec.md)：定义“实体主页交集重做”的可观察主路径、失败语义及父能力交接。
- [`home-recommend-intersection-redesign`](./home-recommend-intersection-redesign/spec.md)：spotlight 文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。
- [`intersection-algorithm-closure`](./intersection-algorithm-closure/spec.md)：ranking-signal-fusion spec 登记 intersection fact/affinity 权重入口。
- [`intersection-sentence-unification`](./intersection-sentence-unification/spec.md)：seed、服务响应与展示口径均与 `intersection_kind_registry.yaml` 及本 Story Display Contract 一致。
- [`object-homepage-gamma-real-data-closure`](./object-homepage-gamma-real-data-closure/spec.md)：metadata 与 compose 静态契约通过。
- [`user-profile-intersection-redesign`](./user-profile-intersection-redesign/spec.md)：他人/我的主页二级过滤同一实现。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 我的主页交集聚合入口与清零 SIT

- 我的主页展示交集总数与最多 3 个维度的变化红点/数字，超 3 维度可展开更多。
- 点击进入按维度分组列表页，展示自上次查看的新增交集。
- 打开列表即推进已读水位并清零红点，无需逐项查看详情。

<a id="req-002"></a>
### REQ-002 对象页交集卡与 demo dock 移除 SIT

- profile/entity/circle 三类主页不再出现问小趣 demo dock。
- 他人用户主页、实体主页、圈子主页展示事实交集卡，每条有可读证据。
- 圈子主页出现「你认识的人有 N 个在这」交集卡。

<a id="req-003"></a>
### REQ-003 首页与频道交集推荐重设计 SIT

- 首页交集卡去掉关注按钮，使用真实头像 + 名字 + 维度 chip + 安静共同点 chip。
- 模块头展示「N 位与你有交集」红数字；首页 ≤4 卡、频道 ≤3 卡。
- 校园、旅行频道出现频道专属交集推荐。
- travel 频道只消费 content metadata 生成的 `intersectionModulePolicy=spotlightSegment`，端侧不得维护频道专用 override。
- 事实交集明确证据，概率交集明确标注推荐，混排后统一排序。

<a id="req-004"></a>
### REQ-004 保鲜冷却与曝光转化漏斗 SIT

- 曝光未转化的交集对象在配置窗口（默认 14 天）内不再重复推荐。
- 事实交集带 computedAt/expiresAt，过期触发重算。
- 交集曝光、点击、转化、清零全链路携带 intersectionId/dimension/intersectionClass/cohort 进入行为管道。

<a id="req-005"></a>
### REQ-005 可行动交集与商用主轴 SIT

- 交集触点统一遵循产品主轴「别人帮你刷内容，我们帮你遇到对的人」；所有可见交集句只读云侧 primaryText/primarySpans/displayBinding，端不拼句，join(spans.text)==primaryText 不变量成立。
- 上下文 SVO 成立：explicit_link 必须有 typed object span；host_implicit/host_plain 必须由当前内容卡/视频书/搜索 hit/主页宿主对象证明，禁止可点击 self-target 和 reason 池随机附着。
- 主句禁止 raw stats、泛对象和旧术语：不出现 `2赞1评`、`这条记录`、`TA的内容`、`相关圈子`、`我的连接`。
- 前台用户维度收敛为「交集 / 打动」两词，入口统一「交集配对」、收件箱统一「我的交集」
- “今日”只保留为最小时间粒度的次级说明，辐射他人用「打动」
- 旧「兴趣配对 / 找同趣 / 今日同趣机会 / 影响力」前台退场，机器标识 `interest_match` / `impact` 保留。
- 七触点（视频书/首页内容卡/用户主页/我的主页/圈子主页/实体主页/交集配对 launcher）密度与行动重心符合 `REQ-006` 的七触点统一矩阵；四主页复用 ObjectIntersectionSection/ObjectIntersectionCard，不新增第四套抽象。
- C0 差异化切片「共同想去→约伴」用已有 coWishlistedEntity + 关注 + 交集信号触发 start_gathering；safetyGate 未满足时优雅降级为查看证据/进入对象，无登录死循环。
- 未同时具备真实 producer、当前契约和可兑现 handler 的候选或行动不得进入 canonical registry、API 响应与正式 UI；交集配对 launcher 不渲染伪候选。
- 北极星为可行动交集完成/关系形成（非 DAU），护栏反指标（骚扰率/拒绝率/举报率）与漏斗（曝光→证据展开→行动→完成→关系形成→回流）可观测。
- 垂类扩展只走 [L2 DEC-002](./design.md#dec-002) 的四件套（`vertical` 值 + `objectKind` + taxonomy 子树 + 事实生产者），禁止新增 kind / dimension / actionKey，禁止端侧垂类分支；同一批端侧断言在换垂类后无需改端侧代码。

<a id="req-006"></a>
### REQ-006 合并排序：事实优先（strength + 新鲜度），概率其次（score）；统一经过推荐窗口/冷却过滤

- 合并排序：事实优先（`strength` + 新鲜度），概率其次（`score`）；统一经过推荐窗口/冷却过滤。
- **七触点统一矩阵**（密度 + 行动重心，本条即唯一口径）：视频书底部单句 / 首页紧凑 chip / 用户主页证据组 / 我的主页收件箱 / 圈子主页证据卡 + 成员簇 / 实体主页证据卡 + 记录单句 / 交集配对 launcher（不产候选）。四主页表达仍复用 `ObjectIntersectionSection` / `ObjectIntersectionCard`，不新增第四套抽象。前台用户维度收敛为「交集 / 打动」、入口统一「交集配对」、收件箱统一「我的交集」；“今日”只作最小时间粒度的次级说明，机器标识 `interest_match` / `impact` 内部保留。
- 七触点端侧必须消费同一交集表达与对象页行动分发契约；云侧只下发 canonical `actionHint`。
- `IntersectionTargetNavigator.openActionHint` 只按当前生成闭集中的 `dispatch` 分发；navigate/assistant 的 login 等门不在交集组件拦截，导航到承接页由承接页复用既有 gate + `AuthContinuation` 续接（口径见 [`post-login-landing`](../../user-identity-profile-relationship/onboarding-and-identity-entry/post-login-landing/spec.md)），关注/加入/进入讨论/看共同来源等 login 门轻行动保持可见可点
- action dispatch 闭集仅为 `assistant/navigate/message/gathering`；未登记 dispatch 一律 fail-closed，死参数 gateResolver/gated 已移除（R26）
- `ObjectIntersectionPreviewCard` 只能是 `ObjectIntersectionSection` 的薄包装；`start_gathering` 和 `message_person` 只有在真实承接页与权限门成立时才可展示。
- `safetyGate`、moment 意图时态和行动阶梯以 metadata 模型为准，所有主页和交集入口必须消费同一模型。
- 端云真实数据准出由 [`object-homepage-gamma-real-data-closure`](./object-homepage-gamma-real-data-closure/spec.md) 负责。

<a id="req-007"></a>
<a id="display-contract"></a>
### REQ-007 交集展示合同（Display Contract / §17）

> 仓内锚点：本条即历史文档所称「intersection-definition §17 / Story Display Contract」的唯一规格落点。
> 实现真相源仍是 `intersection_kind_registry.yaml#statementTemplates` 与
> `intersection_reason.yaml` 的 `primaryText` / `primarySpans` / `primaryTextL10nKey` /
> `displayBinding`；本条只规定可观察合同，不复制模板正文。

- **§17.1 结论句结构**：事实通道主句 =「主语[关系限定 + 代表人 + 人数] + 谓语[行为动词] + 宾语[typed object 或宿主上下文]」。
- 模板与 l10nKey 唯一登记在 `statementTemplates.byKind`，云侧一次渲染同时产出 `primaryText` 与 `primarySpans`，`join(spans.text) == primaryText` 结构性成立。
- 端只读直出，禁止本地拼句或按 kind 硬编码中文谓语。
- **§17.2 句式层次**：紧凑 surface（首页内容卡 / spotlight / 视频书）严格单句、不展示副句。
- 列表入口（我的交集 / 为什么推荐TA / 打动）才允许至多一条灰色 `secondaryText`。
- **降级链**：具名对象 → 纯计数句（仅登记了 `counted` 的 kind）→ 隐藏。缺名时禁止造名或借邻近语义。
- **分通道诚实**：`intersectionClass=fact` 必须可向用户说明证据。`affinity` 必须带 `confidenceLabel` 等推荐标注，禁止把概率推荐伪装成事实关系。
- **垂类正交（§23.4）**：扩展只改 `vertical` + `objectKind` + taxonomy 子树 + 事实生产者，禁止独立垂类 kind 名。口径与 [DEC-002](./design.md#dec-002) 一致。

<a id="req-008"></a>
### REQ-008 商用诚实红线与冷启动供给闸门（原 P0）

- **到访语义**：`coVisitedEntity` 只能由可证到访事实（`post.visitedAt` + 地点同一性）产出，结论句说「都去过」。
- 浏览行为归 `sharedEntityAttention`（「也看过」），意图归 `coWishlistedEntity`（「都想去」），三者不得互相替代。
- **行动承诺一致**：`actionHint` 的按钮文案必须与当前 `dispatch` 真实可完成的副作用一致；未就绪行动不得进入 canonical registry 或响应。
- `greet_person` 在打招呼状态机未接通前不得承诺「打招呼」却只 `navigate` 到主页——要么改文案要么改 dispatch。
- **冷启动供给闸门**：`Feed` / `ListMyIntersections` / `ObjectIntersections` 三入口共用 `coldStartSupply`。
- 某 kind 的候选池去重对象数低于 `minDistinctObjectsByKind` 时整 kind 不下发，防止 N=1 语料下「人人都有交集」稀释信息量。
- 探针不可用时供给判定 fail-open；未进入 canonical registry 的 kind 永不生成或下发。

<a id="req-009"></a>
### REQ-009 交集飞轮：经历回流与社会证明（[DEC-003](./design.md#dec-003)/[DEC-004](./design.md#dec-004)）

- 经历交集 `coExperiencedGathering` 只由「同一 Gathering 双方 active Participation + 双方各自主动发布关联 `content.post.gatheringRef` 的公开内容」产出；时间到达、聊天频率、位置或单方声明不得触发。
- 结论句只说「一起参加过」；occurred 语义由 Gathering Outcome 独立承载，两者不得互换。
- 社会证明按四锚点事实计数（实体/内容/创作者/发起人），计数只来自「成形」（room ready + ≥2 有效参与者）与「经历」（≥2 参与者主动发布关联内容）两级，互不冒充；时间已过无内容只显示已结束，不进计数。
- 不做对人星级/评分；负面走举报/Block/安全终止通道。
- 创作者成行力沿溯源链（经历 Post → `gatheringRef` → Gathering `sourceRefs` → 原内容 → 创作者）派生；促成通知只携带计数与公开经历引用，不暴露未公开参与者身份。
- 产品与助手可行性文案只允许使用模型内可证事实（时限锚点、同城粒度、交集新鲜度）；禁止宣称「对方有空」（个人空闲不在任何模型内，`watch_availability` 是名额监听不是个人日程）。
- 牵线搭桥 UX 服从四层出现强度阶梯：L0 氛围（chip/单句/计数，可完全忽略）、L1 时刻（仅用户刚对相关对象做出动作时出现）、L2 目的地（收件箱/对象页全量）、L3 主动（仅助手周度速递一条通道）。任何页面首次呈现 ≤1 行主句 + 1 个主动作，同屏最多一处交集模块；禁止全屏交集弹窗、开屏推人、消息流自动插入与"附近的人"式交集列表。
- 经历沉淀读面与聚合区（现行）：`content.post.ListPostsByGathering` 只返回 public + published + 审核通过且作者主动写入 `gatheringRef` 的内容，作者删除或转私密即从聚合区消失。App 行动详情共同经历区按三态诚实渲染（≥2 名不同作者 → 共同经历聚合、仅 1 名 → 个人回顾、0 条且行动已结束 → 「行动时间已结束」），行动未结束且无内容不渲染；active 参与者从行动详情/Board 经「发布回顾」入口携带 `gatheringRef` 进入创作流，创作页展示可移除的关联上下文条，移除后 payload 不携带该字段。
- 想去即时反馈（现行 Aha 1）：详情态想去按钮只在作品锚定到 `wishlistHomepageTypes` 类型的 `primaryHomepageId` 时出现；想去成功后的反馈诚实两态——有对象交集点名共同人数并给查看入口，无交集只确认动作本身，禁止伪造社会证明。未登录点击经 `WishlistHomepageContinuation` 双目标续接。覆盖面（现行）：feed 卡与 works 沉浸统一 engagement bar 承载，文章形态从 feed 点开进同一 works 沉浸消费——想去入口与形态无关由同一锚点门控派生（文章形态有 widget 契约），不为单一形态另造第二入口。
- 四锚点社会证明（现行）：`GetGatheringSocialProof(anchorKind, objectId)` 按 organizer/entity/content/creator 四锚点返回发起/成形/经历三级诚实计数（成形=已发布且 ≥2 名 active 参与者，经历=成形且 ≥2 名参与者各自持有 active 公开回顾），计数由 recommendation 读时聚合派生、Content 只代理透传；展示面只用成形/经历两级（发起级仅发起人卡），零计数与读取失败一律不渲染，无内容的行动永远不进经历级（归属修订见 [DEC-004](./design.md#dec-004)）。
- 经历内容溯源标（现行，works 详情态）：回顾内容按 wire `gatheringRef` 显示「来自一次共同行动」进行动详情。种草内容按 content 锚点成形级 > 0 显示「他们从这条内容出发，一起去了」，经 `ListGatheringsBySource` 进成形行动详情；与交集陈述互斥占位（同屏最多一处），两者都不成立不渲染。
- 结束催回顾与双人邀约入口一致性（现行）：Gathering 完成且 outcome=occurred 时 Notification 向完成时冻结的每位 active 参与者投递一条幂等「发布回顾」催发（比例②的产品发动机，未确认发生不催、不骚扰），App 通知行回链行动详情的发布回顾入口并带 `gathering_flywheel` 打开埋点。「我的交集」收件箱可约主行动与他人主页同轨携带人对人上下文——人对人交集点「一起去」进入双人邀约预设（容量 2 + 邀请制 + 发布后自动邀请），入口一致性有 widget 正例。小趣 `intersection.read_mine` domain_reader 经 content `ListMyIntersections` 同读面绑定（delegated persona token、readiness 由真实 binding 决定、fail-closed 不建 fallback），被动通道可引用授权交集事实并接 `gathering.propose_create_draft` 起草。
- feed 种草溯源标裁决（不落实理由）：首页 feed 卡逐条渲染「他们从这条内容出发」需按 postId 查 content 锚点成形计数，现缺批量社会证明读面，逐卡单查即 N+1——不做；种草溯源保留在 works 沉浸详情（已有），feed 侧待批量读面另立后再议。
- 北极星漏斗读面（现行）：三比例（想去→成行、成形→双方回顾、促成→创作者续发）的分子分母唯一产出路径为 rec 内部读面 `GetRecommendationFlywheelFunnel`——时间窗必填，可选 `sourceObjectKind`/`sourceObjectId`/`capacityTier`（duo=容量 2 且邀请制、group=其余、旧事件缺字段归 unclassified 且被维度过滤排除）/`tagRef`（行动 content 来源的种草内容标签）切片。分子分母全部从域事实投影读时派生（想去=wishlist 事实、成形/经历复用四锚点两级、促成=幂等占位收据含冻结创作者名单、续发=收据 notifiedAt 后该创作者存在新 active 内容），空数据为零、有界扫描越界标 `truncated`、无预聚合缓存、读面不下发百分比。维度事实链：`GatheringPublished` 携带发布时冻结的 `maxParticipants`/`admissionPolicy`，`post_authors` 投影存 `tagRefs`。字典登记见 `analytics-metric-dictionary` REQ-003 `domain_fact_readface` 轨（互为引用）。不落实维度的裁决——gathering `topicRefs` 契约存在但创建页无输入控件当前采集率为零、`coarsePlaceLabel` 为必填自由文本聚合价值弱（地理镜头由来源实体承担），均不冒充维度，留待上线后按真实需求再议。

## 6. 契约与依赖

- 上游能力：[`object-homepage-network`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 我的主页交集聚合入口与清零 SIT

- GIVEN 执行“我的主页交集聚合入口与清零”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“我的主页交集聚合入口与清零”对应动作。
- THEN 我的主页展示交集总数与最多 3 个维度的变化红点/数字，超 3 维度可展开更多。
- THEN 点击进入按维度分组列表页，展示自上次查看的新增交集。
- THEN 打开列表即推进已读水位并清零红点，无需逐项查看详情。

<a id="sit-002"></a>
### SIT-002 对象页交集卡与 demo dock 移除 SIT

- GIVEN 执行“对象页交集卡与 demo dock 移除”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“对象页交集卡与 demo dock 移除”对应动作。
- THEN profile/entity/circle 三类主页不再出现问小趣 demo dock。
- THEN 他人用户主页、实体主页、圈子主页展示事实交集卡，每条有可读证据。
- THEN 圈子主页出现「你认识的人有 N 个在这」交集卡。

<a id="sit-003"></a>
### SIT-003 首页与频道交集推荐重设计 SIT

- GIVEN 执行“首页与频道交集推荐重设计”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“首页与频道交集推荐重设计”对应动作。
- THEN 首页交集卡去掉关注按钮，使用真实头像 + 名字 + 维度 chip + 安静共同点 chip。
- THEN 模块头展示「N 位与你有交集」红数字；首页 ≤4 卡、频道 ≤3 卡。
- THEN 校园、旅行频道出现频道专属交集推荐。
- THEN 事实交集明确证据，概率交集明确标注推荐，混排后统一排序。

<a id="sit-004"></a>
### SIT-004 保鲜冷却与曝光转化漏斗 SIT

- GIVEN 执行“保鲜冷却与曝光转化漏斗”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“保鲜冷却与曝光转化漏斗”对应动作。
- THEN 曝光未转化的交集对象在配置窗口（默认 14 天）内不再重复推荐。
- THEN 事实交集带 computedAt/expiresAt，过期触发重算。
- THEN 交集曝光、点击、转化、清零全链路携带 intersectionId/dimension/intersectionClass/cohort 进入行为管道。

<a id="sit-005"></a>
### SIT-005 可行动交集与商用主轴 SIT

- GIVEN 执行“可行动交集与商用主轴”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“可行动交集与商用主轴”对应动作。
- THEN 交集触点统一遵循产品主轴「别人帮你刷内容，我们帮你遇到对的人」；所有可见交集句只读云侧 primaryText/primarySpans/displayBinding，端不拼句，join(spans.text)==primaryText 不变量成立。
- THEN 上下文 SVO 成立：explicit_link 必须有 typed object span；host_implicit/host_plain 必须由当前内容卡/视频书/搜索 hit/主页宿主对象证明，禁止可点击 self-target 和 reason 池随机附着。
- THEN 主句禁止 raw stats、泛对象和旧术语：不出现 `2赞1评`、`这条记录`、`TA的内容`、`相关圈子`、`我的连接`。
- THEN 前台用户维度收敛为「交集 / 打动」两词，入口统一「交集配对」、收件箱统一「我的交集」
- AND “今日”只保留为最小时间粒度的次级说明，辐射他人用「打动」
- AND 旧「兴趣配对 / 找同趣 / 今日同趣机会 / 影响力」前台退场，机器标识 `interest_match` / `impact` 保留。
- THEN 七触点（视频书/首页内容卡/用户主页/我的主页/圈子主页/实体主页/交集配对 launcher）密度与行动重心符合 `REQ-006` 的七触点统一矩阵；四主页复用 ObjectIntersectionSection/ObjectIntersectionCard，不新增第四套抽象。
- THEN C0 差异化切片「共同想去→约伴」用已有 coWishlistedEntity + 关注 + 交集信号触发 start_gathering；safetyGate 未满足时优雅降级为查看证据/进入对象，无登录死循环。
- THEN 未同时具备真实 producer、当前契约和可兑现 handler 的候选或行动不进入 canonical registry、API 响应与正式 UI；交集配对 launcher 不渲染伪候选。
- THEN 北极星为可行动交集完成/关系形成（非 DAU），护栏反指标（骚扰率/拒绝率/举报率）与漏斗（曝光→证据展开→行动→完成→关系形成→回流）可观测。
- THEN 垂类扩展只走 [L2 DEC-002](./design.md#dec-002) 的四件套，`verticalExtensionContract` 的四条禁令由 `verify_intersection_kind_registry.py` 阻断，同一批端侧断言在换垂类后无需改端侧代码。

<a id="sit-006"></a>
### SIT-006 交集展示合同（Display Contract / §17）

- GIVEN 任一 fact kind 在 `statementTemplates.byKind` 有登记，且证据足以产出具名对象或 counted 降级句。
- WHEN 云侧 Explain 管线渲染该 reason。
- THEN `primaryText` 与 `primarySpans` 由同一模板产出，`join(spans.text) == primaryText`，并下发对应 `primaryTextL10nKey`。
- AND 紧凑 surface 不展示 `secondaryText`。
- AND affinity 带推荐标注。
- AND 未登记 kind 或证据不足时不下发展示句。

<a id="sit-007"></a>
### SIT-007 商用诚实红线与冷启动供给闸门

- GIVEN 浏览行为与声明到访行为同时存在于同一地点。
- WHEN 产出交集 reason。
- THEN 浏览只进 `sharedEntityAttention`，声明到访才进 `coVisitedEntity`，二者文案不得互换。
- AND `actionHint` 文案与 `dispatch` 承诺一致；供给低于阈值的 kind 在 Feed/List/ObjectIntersections 三入口均不下发。

<a id="sit-008"></a>
### SIT-008 经历回流与社会证明诚实分级

- GIVEN 两名用户在同一 Gathering 均持有 active Participation，行动时间已真实结束。
- WHEN 双方各自主动发布关联该 Gathering（`gatheringRef`）的公开内容。
- THEN 双方交集列表出现 `coExperiencedGathering`，主句为云侧「一起参加过」模板渲染；实体/内容/创作者/发起人四锚点计数经历级各 +1，创作者收到只含计数与公开经历引用的促成通知。
- AND 对照组：只有一方发布或双方均未发布时，不产出经历交集、不进经历级计数，行动详情只显示「行动时间已结束」。
- AND 全程不存在签到、强制完成确认、位置推断或对人评分入口。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 同趣匹配后端聚合与重行动风控

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：同趣匹配缺少可信后端聚合、对象授权、骚扰防护和可审计重行动门禁。
- 完成判定：`SIT-005` 的可观察验收通过，且重行动路径具备可信后端聚合、对象授权、骚扰防护与可审计门禁。

<a id="open-002"></a>
### OPEN-002 我的主页交集聚合入口与清零 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：我的主页展示交集总数与最多 3 个维度的变化红点/数字，超 3 维度可展开更多。
- 交集页（`user.my_intersections`、`intersection.object_list`）的验收数据供给：交集 inbox 是行为事实（`content.content_behavior_fact.ReportBehaviors`）经 recommendation 派生投影（`recommendation_feature_profile_view`）的跨服务异步结果，测试数据控制面不承诺确定性 provision；UAT 验收需在行为上报后按最终一致轮询交集投影，或将首访空态作为合法冷启动验收态。足迹页（`user.my_footprint`）不受此限——其写读闭环（`ReportBehaviors` → `GetMyFootprint`）同步于 content-service，由 typed capability 直接供数。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 对象页交集卡与 demo dock 移除 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：profile/entity/circle 三类主页不再出现问小趣 demo dock。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 首页与频道交集推荐重设计 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：首页交集卡去掉关注按钮，使用真实头像 + 名字 + 维度 chip + 安静共同点 chip。
- 完成判定：`SIT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 保鲜冷却与曝光转化漏斗 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：曝光未转化的交集对象在配置窗口（默认 14 天）内不再重复推荐。
- 完成判定：`SIT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-006"></a>
### OPEN-006 可行动交集与商用主轴 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：交集触点统一遵循产品主轴「别人帮你刷内容，我们帮你遇到对的人」；所有可见交集句只读云侧 primaryText/primarySpans/displayBinding，端不拼句，join(spans.text)==primaryText 不变量成立。
- 完成判定：`SIT-005` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-008"></a>
### OPEN-008 经历交集读面消费与端到端证据未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 user_acceptance 三环境全链证据——九步旅程 probe（`gathering_flywheel_journey_probe_ops_env`，双隔离 Actor 真实 API 走想去 → 交集 → 发起 → 加入 → 双方回顾 → 经历交集 → 四锚点 +1 → 无内容对照组 → 无关锚点归零）与 readiness case（`producer: ops`、target=object）已就绪，probe 支持双 Actor 来源二选一（`stackctl verify` ActorLease handoff 或 `--self-provision-instance-id` 经受管 OTP 通道幂等自建，均为真实非生产账号且 Prod 被底层拒绝）。probe 并已覆盖 organizer 锚点断言与场景二延伸步（1对1 邀约 invite → decline → 发起方婉拒回执 → 再邀 → accept 成行，经真实 AppMessage inbox 轮询回执）。执行尚缺健康的完整环境栈：本机 stackctl 锁与 Docker 被并行 gamma/alpha 交付连续占用（跨多小时十余次启动尝试均 GATE_BLOCK 或锁排他，run 报告在案）。期间已修复 candidate 快照内 `product_telemetry_alerts.yaml` 被 Docker 挂载残留污染为空目录的启动阻断。最近一次真实执行（20260813T16 UTC，report 在案）：并行 SkillPackage 自举修复后 alpha 栈 healthy，probe 经受管 OTP 自建双隔离 Actor 成功并通过前两步（社会证明基线、想去意图），第三步 person 对象交集读取在 rec 返回非空 200 后于 content 代理链稳定 500（`UNKNOWN.SYSTEM.internal_error`，同链路本地 local_contract 绿）——归因运行候选的 content-service 落后 HEAD（打包早于提交），含全部改动的新候选已重打包就绪（baselineId `aead64d5…`）；执行中还修复了会话库 send-otp 幂等键跨会话固定导致复开无新 OTP 的 probe 健壮性缺陷。窗口随后再次被并行交付占用（beta dev-session 构建、gamma 栈活跃、down 遇 compose 插值变量缺失），收敛后用新候选 up 即跑。北极星度量读面已先行闭合：三比例分子分母经 `GetRecommendationFlywheelFunnel`（时间窗必填 + 来源对象/capacityTier/tagRef 切片、越界 truncated、读时聚合无缓存）有 api_integration 精确正负例。创作者促成通知已闭合：recommendation 在经历级首次达成且溯源链回到创作者内容时经 `events.recommendation.intersections` 发布 `IntersectionFacilitationRecorded`（占位收据幂等、溯源链断/私密回顾不发布，api_integration 正负例），Notification 投影为内容维度通知并回链行动公开详情（Go 正负例），App 通知行按 gathering target 导航。feed 列表卡溯源标已接线：feed/detail 服务端投影输出 `gatheringRef`，feed 卡在无交集主句时渲染「来自一次共同行动」轻标进行动详情。
- 完成判定：`SIT-008` 的 user_acceptance 层在真实环境走完整圈（想去 → 发起 → 成行 → 双方回顾 → 经历交集出现），四锚点计数经历级 +1 且创作者促成通知可见。
- 依赖：`chat-conversation/intersection-native-messaging` OPEN-001 的 App 展示面。

<a id="open-007"></a>
### OPEN-007 旅游 POI / 实体主页经纬度语料回填

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：代码链路已接上 `Location` / GeoJSON / `filters.near`，但 canonical travel 实体坐标回填仍为 0/2899，`coPresentHere` / `nearbyAffinity` 与 near 检索无法在真实语料上成立。
- 完成判定：`quwoquan_data/reference/travel/entities/**` 坐标覆盖达到可商用阈值，且 gamma import receipt 证明 near 检索返回非空，使 `SIT-007` 的到访同一性判定与冷启动供给闸门在 `coPresentHere` / `nearbyAffinity` 上有真实语料可裁定。
