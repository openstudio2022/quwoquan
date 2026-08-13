# L2 Business Capability：个人主页统一体验 (`profile-homepage-redesign`)

> 所属领域：[`user-identity-profile-relationship`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

统一个人主页的信息架构、状态模型与跨页面互动一致性

## 2. 范围与非目标

### In Scope

- ProfileShell mine/other 统一组件与差异区（头图/信息卡/统计/操作/工具栏）
- 一级 3 Tab（记录/互动/足迹）由 codegen profile_tabs 驱动，圈子作为统计数字进入详情页
- 创作 Tab 二级 SubTab（全部/图片/视频/文字，无微趣）+ 可见性过滤
- 统计区四项（粉丝/关注/获赞/圈子）可点击；粉丝/关注/圈子共用三 Tab 详情页，获赞进入互动-点赞
- 我与TA的交集卡真闭环（shared-tags 真数据 + object_tag_index 打标管道 + 归因）
- resonance 旧链路彻底删除并统一到 IntersectionReason
- 主页页面级埋点与 referralSource 归因
- 我的主页交集资产面：可行动交集分层与「可约」入口、「我的行动」公开行动入口与分组页、「共同经历」资产行（交集飞轮的主页沉淀面）

### Out of Scope

- edit_profile_page / persona_management_page 重写
- content/discovery 域 moment/micro 能力变更
- object_tag_index 事件驱动增量管道完整落地（仅离线批量回填）
- 三个源服务（user/content/circle）既有写路径重写

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-009`](../../spec.md#scn-009)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：统一个人主页的信息架构、状态模型与跨页面互动一致性，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-012 / SCN-010`](../../spec.md#scn-010)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：统一个人主页的信息架构、状态模型与跨页面互动一致性，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`career-interest-profile-editor`](./career-interest-profile-editor/spec.md)：职业与兴趣入口不依赖端侧完整枚举。
- [`owner-persona-homepage-unification`](./owner-persona-homepage-unification/spec.md)：统一 owner/Persona 主页，同时保持点赞、评论与浏览列表的既有行为。
- [`profile-commercial-readiness`](./profile-commercial-readiness/spec.md)：我的主页首屏展示真实档案与一致统计，production 仅经 generated Remote Facet，alpha/test 由隔离装配注入。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 ProfileShell 统一组件 + 一级 3 Tab（codegen 驱动）mine/other 差异

- mine/other 共用 ProfileShell（ObjectPageShell 壳层），差异区（操作按钮/工具栏/可见性/交集卡）按模式正确切换。
- 一级 Tab [记录|互动|足迹] 由 codegen profile_tabs 渲染，端侧无硬编码 Tab id/文案；足迹承载浏览历史入口，圈子不再作为主页一级 Tab。
- 创作内容形式仅 文章/图片/视频 三类，全链路无「微趣/moment」概念残留。

<a id="req-002"></a>
### REQ-002 创作 SubTab/可见性、统计详情、互动内容与端云数据

- 创作 SubTab（全部/图片/视频/文字）+ 可见性过滤（mine 含私密、other 仅公开）正确。
- 统计区展示粉丝、关注、获赞、圈子四项；粉丝/关注/圈子进入统一统计详情页并默认落在对应一级 Tab，获赞仍进入现有互动 Tab 的点赞子维度。
- 统计详情页顶部使用与设置/资料编辑同源的 inset chrome + `[粉丝|关注|圈子]` segmented selector，正文区无第二条 tab strip、无 underline 选中态。
- 统计详情页搜索走云侧 `query + cursor + limit`；三 Tab 独立记忆 query、scroll、cursor 与已加载结果，切换后恢复，不接受单页本地 `contains` 伪搜索。
- 粉丝/关注行消费 `ProfileSocialRelationRowViewData.relationshipCapability` 渲染动作矩阵
- 圈子行消费 `CircleDto` 渲染公开浏览卡片
- private/blocked/empty/pagination/error 状态齐备，无硬编码假数据与中文字面量。

<a id="req-003"></a>
### REQ-003 我与TA的交集卡真闭环 + 行为归因 + resonance 零残留

- other 主页交集卡经 objectSharedReasonsProvider → sharedTags → IntersectionReason 渲染；无交集展示稳定空态。
- gamma 真打 shared-tags 对已打标对象返回非空（object_tag_index 打标管道落地）。
- 交集卡 onReasonTap 上报 BehaviorEvent.intersectionDimension/intersectionTagRefs；MyProfilePage 曝光/停留埋点到位。
- resonance 旧链路（ResonancePage/路由/resonance_buddy_view_data/resonanceBuddyPreviewWireRows/myResonance）零残留。

<a id="req-004"></a>
### REQ-004 四类主页体系中的用户主页首屏高保统一

- 他人主页首屏 CTA 固定为关注和私信，我的主页首屏 CTA 固定为管理分身和编辑资料。
- 首屏模块顺序为身份区（含统计行与 CTA）、交集、行动与经历资产面（REQ-008）、打动、Tab、双列内容流；不再首屏展示旧版粉丝/浏览/点赞数据面板。
- 他人主页模块命名为我与TA的交集、TA打动的人。我的主页模块命名为我的交集、我打动的人（辐射他人统一用「打动」，旧「影响力」前台退场，禁止「我的连接」——口径见 [`intersection-unified-experience` REQ-005](../../object-homepage-network/intersection-unified-experience/spec.md#req-005)）。
- 作品二级筛选仅为全部、图片、视频、文字
- 底层 article 不改数据模型
- 圈子统计入口进入三 Tab 详情页。

<a id="req-005"></a>
### REQ-005 我的交集 / 我的影响力一流水准 UX 与接口扩展准出

- 主页 slogan、我的交集、我的影响力不再引入暖金棕第二主调；蓝色仅用于 CTA、一级 Tab 选中态、可点击文字与弱入口，类型图标使用非品牌蓝低饱和语义色阶。
- 我的交集与我的影响力卡片具备足够呼吸感；预览行与底部入口不渲染多余 chevron，可点击文字清晰但克制。
- 交集与影响力详情页使用与 ProfileStatsPage 一致的一级 segmented control，Tab 为 [交集|影响力]；从我的交集入口默认交集 Tab，从我的影响力入口默认影响力 Tab。
- 详情页完整实例化交集规格主要类型（关系/身份/内容/地点/兴趣及喜欢/分享/想去/同行等派生来源）与影响力主要类型（community/decision/relationship/knowledge/spread/audience），样例来自 contract fixture，不在 UI 编造。
- 交集接口维持 summary/list/visit 分离；列表接口必须支持 dimension/filter/sourceRef/timeBucket/cursor/limit 扩展参数，访问列表推进水位不得阻塞首屏渲染。
- 影响力接口维持 authorId 维度聚合读模型；GetAuthorImpact P95 ≤ 500ms，ListAuthorImpactEvidence 以 opaque cursor 分页，后续新增 helpType/action/tagRef 不需要改 UI 分支。
- 点赞、评论、分享、关注/联系人转化、进圈、内容/对象访问与助手引用统一聚合到作者影响事实；计数可以以稳定 impactId 下钻隐私安全的内容证据，App 只直出服务端结论与计数，不本地估算或拼装。
- 影响力面「成行力」：mine 模式在影响力卡下方消费四锚点社会证明读面（`GetGatheringSocialProof`，creator 锚点）渲染成形/经历两级诚实计数单行。成形为 0 或读取失败整行不渲染，端不估算、两级计数不互相冒充。

<a id="req-006"></a>
### REQ-006 职业与兴趣资料页标签同源、编辑保存与交集索引投影

- /profile/career-interests 独立页面从编辑资料页进入，页面结构为职业身份、我的标签、全部兴趣，不展示推荐标签。
- 职业通过 Audience/用户/职业 查询并保存单个叶子 tagRef；兴趣通过 Audience/用户/兴趣偏好 查询并保存有序叶子 tagRefs，最多 30 个、允许清空。
- 端侧在四环境通过 Remote ListTagChildren / ResolveTag / ValidateTagRefs 查询与校验；服务契约不接受 Topic/兴趣/*。
- user-service 拒绝非法根、分类父节点、职业多选与兴趣超限；保存成功后投影 object_tag_index 的 user 对象 tagRefs。
- alpha/beta/gamma/prod 均由 control_plane/governance/taxonomy 生成同一标签发布包；beta/gamma/prod 通过 tag import 与 object index import/backfill 灌入。

<a id="req-007"></a>
### REQ-007 统计详情页为主页统计行进入的**统一二级关系页**

- 统计详情页为主页统计行进入的**统一二级关系页**；单一路由保持 `/profile/stats?type=fans|following|circles&userId=...`，永久固定三 Tab，不新增第四个「获赞」Tab。
- 顶部 chrome 与资料编辑/设置页同源，使用 `SettingsInsetMemberPickerPageScaffold` 语义：leading 为 iOS chevron back，middle 为等宽 segmented selector `[粉丝 | 关注 | 圈子]`；正文区不得再放第二条 tab strip，不使用 underline 选中样式。
- 粉丝/关注列表统一为 `头像 + displayName + @handle + 关系/可见性辅助信息 + trailing 动作`；trailing 按钮完全由 `RelationshipCapability` 驱动，禁止页面本地拼 `isFollowing` 布尔。
- 首屏必须具备 skeleton、下拉刷新、cursor 分页、分页尾部 loading、inline retry、owner/other 分型空态、private/blocked 权限卡。`viewerContext.canViewFullProfile=false` 时直接命中权限态，不渲染假列表。账号封禁（suspension）的生产者、`active → suspended → active` 状态机与凭证/鉴权级联由 [`account-suspension-and-appeal-lifecycle`](../settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md) 承接，跨域执法级联由 [`account-moderation-and-appeal-enforcement`](../../product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md) 承接，主页域只消费 `viewerContext` 权限投影。
- 方向切换固定放在互动二级控制行右侧：`[收到的 | 我发起的]`；不得叠放在一级 `记录 / 互动 / 足迹` Tab 行。
- 一级 Tab `footprint` 由 codegen `profile_tabs`（`user/account/user_account/ui_config.yaml`）驱动，端侧不得硬编码 Tab id/文案。
- `ListFollowers / ListFollowing / ListUserCircles` 一律支持 `query + cursor + limit`；统计详情页搜索必须走云侧当前 subject 范围过滤，不接受单页本地 `contains` 伪搜索。
- 统一到底部导航「小趣」入口，减少操作按钮行的视觉拥挤
- 我的与他人主页必须完成交集卡点击、归因上报与跳转；`记录/互动/足迹` 可切换，足迹在他人主页不可见并遵守可见性过滤。
- 交集卡 `onReasonTap` 上报 `BehaviorEvent.intersectionDimension/intersectionTagRefs`（统一归因，废止旧 `reasonType` 闭集）。

<a id="req-008"></a>
### REQ-008 我的主页交集资产面（可行动分层、我的行动、共同经历）

- 我的交集详情页交集 Tab 将「可行动交集」（`actionHints` 非空且 `expiresAt` 为空或未到期的事实交集）置顶为「可约」分组。
- 「可约」分组内保持云侧下发顺序，端侧只做展示分层，不重排组内顺序、不本地拼句。
- 可行动行的主行动消费首个 `isPrimary` actionHint 经 `IntersectionTargetNavigator.openActionHint` 分发，未登记 dispatch fail-closed。
- 我的交集收件箱预览卡在存在可行动交集时于 summary strip 展示「可约 N」入口（N 为已拉取预览内可行动交集数，不伪造全量计数），点击进入详情页可约分组。无可行动交集时不渲染该入口。
- 我的主页摘要区（我的交集卡之后）新增「我的行动」入口：消费 `circle.gathering.ListMyHostedGatherings` host 本人私有读面（host 身份由服务端从受信 persona actor 解析，禁止代查他人）。
- 私有读面含 draft 与全部 audiencePolicy（invite-only / unlisted 的发起人视角不缺席）。无行动时折叠为单行入口文案，不渲染空列表、不占首屏空间。
- 「我的行动」独立页 `/profile/gatherings` 按卡片事实四分组：即将开始（published 且 temporalPhase 未到 ended）、草稿（draft）、已结束（completed 或 temporalPhase=ended）、已取消（cancelled）。
- 四分组只由云侧 `lifecycleStatus` 与 `temporalPhase` 派生，端不做时间推断、不推断"等回应/到场"等卡片不含的事实。行动卡直通 Gathering 详情。
- 我的主页摘要区新增「共同经历」资产行（仅 mine 模式）：消费 `ListMyIntersections(sourceRef=coExperiencedGathering, filter=fact)`，主句只读云侧 `primaryText`/`primarySpans` 直出。
- 「共同经历」资产行点击经 actionHints 进入行动详情共同经历区。无经历交集时整个区块不渲染（诚实空态=不渲染，不放鼓励文案硬广）。
- 影响力面「成行力」：mine 模式在影响力卡下方消费四锚点社会证明读面（`GetGatheringSocialProof`，creator 锚点）渲染单行事实计数（成形/经历两级诚实分级）。成形为 0 或读取失败整行不渲染，端不估算。
- 防卡死纪律：以上模块加载失败或缓慢均不阻塞主页首屏与滚动（骨架有界、错误态带 inline retry）。已读水位与埋点失败不阻断展示。
- 同屏最多一处交集模块的 UX 阶梯约束不被破坏（「我的行动」「共同经历」是行动/经历资产面，不是第二处交集推荐模块）。

## 6. 契约与依赖

- 上游能力：[`user-identity-profile-relationship`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。
- Gamma API 证据：`quwoquan_app/test/api_integration/service/content_service/content/post/author_impact_gamma__api_integration_test.dart`
- Gamma 真机证据：`quwoquan_app/test/user_acceptance/journeys/profile/profile_journey__user_acceptance_test.dart`

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 ProfileShell 统一组件 + 一级 3 Tab（codegen 驱动）mine/other 差异

- GIVEN 执行“ProfileShell 统一组件 + 一级 3 Tab（codegen 驱动）mine/other 差异”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“ProfileShell 统一组件 + 一级 3 Tab（codegen 驱动）mine/other 差异”对应动作。
- THEN mine/other 共用 ProfileShell（ObjectPageShell 壳层），差异区（操作按钮/工具栏/可见性/交集卡）按模式正确切换。
- THEN 一级 Tab [记录|互动|足迹] 由 codegen profile_tabs 渲染，端侧无硬编码 Tab id/文案；足迹承载浏览历史入口，圈子不再作为主页一级 Tab。
- THEN 创作内容形式仅 文章/图片/视频 三类，全链路无「微趣/moment」概念残留。

<a id="sit-002"></a>
### SIT-002 创作 SubTab/可见性、统计详情、互动内容与端云数据

- GIVEN 执行“创作 SubTab/可见性、统计详情、互动内容与端云数据”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“创作 SubTab/可见性、统计详情、互动内容与端云数据”对应动作。
- THEN 创作 SubTab（全部/图片/视频/文字）+ 可见性过滤（mine 含私密、other 仅公开）正确。
- THEN 统计区展示粉丝、关注、获赞、圈子四项；粉丝/关注/圈子进入统一统计详情页并默认落在对应一级 Tab，获赞仍进入现有互动 Tab 的点赞子维度。
- THEN 统计详情页顶部使用与设置/资料编辑同源的 inset chrome + `[粉丝|关注|圈子]` segmented selector，正文区无第二条 tab strip、无 underline 选中态。
- THEN 统计详情页搜索走云侧 `query + cursor + limit`；三 Tab 独立记忆 query、scroll、cursor 与已加载结果，切换后恢复，不接受单页本地 `contains` 伪搜索。
- THEN 粉丝/关注行消费 `ProfileSocialRelationRowViewData.relationshipCapability` 渲染动作矩阵
- AND 圈子行消费 `CircleDto` 渲染公开浏览卡片
- AND private/blocked/empty/pagination/error 状态齐备，无硬编码假数据与中文字面量。

<a id="sit-003"></a>
### SIT-003 我与TA的交集卡真闭环 + 行为归因 + resonance 零残留

- GIVEN 执行“我与TA的交集卡真闭环 + 行为归因 + resonance 零残留”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“我与TA的交集卡真闭环 + 行为归因 + resonance 零残留”对应动作。
- THEN other 主页交集卡经 objectSharedReasonsProvider → sharedTags → IntersectionReason 渲染；无交集展示稳定空态。
- THEN gamma 真打 shared-tags 对已打标对象返回非空（object_tag_index 打标管道落地）。
- THEN 交集卡 onReasonTap 上报 BehaviorEvent.intersectionDimension/intersectionTagRefs；MyProfilePage 曝光/停留埋点到位。
- THEN resonance 旧链路（ResonancePage/路由/resonance_buddy_view_data/resonanceBuddyPreviewWireRows/myResonance）零残留。

<a id="sit-004"></a>
### SIT-004 四类主页体系中的用户主页首屏高保统一

- GIVEN 执行“四类主页体系中的用户主页首屏高保统一”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“四类主页体系中的用户主页首屏高保统一”对应动作。
- THEN 他人主页首屏 CTA 固定为关注和私信，我的主页首屏 CTA 固定为管理分身和编辑资料。
- THEN 首屏模块顺序为身份区（含统计行与 CTA）、交集、行动与经历资产面、打动、Tab、双列内容流；不再首屏展示旧版粉丝/浏览/点赞数据面板。
- THEN 他人主页模块命名为我与TA的交集、TA打动的人；我的主页模块命名为我的交集、我打动的人。
- THEN 作品二级筛选仅为全部、图片、视频、文字
- AND 底层 article 不改数据模型
- AND 圈子统计入口进入三 Tab 详情页。

<a id="sit-005"></a>
### SIT-005 我的交集 / 我的影响力一流水准 UX 与接口扩展准出

- GIVEN 执行“我的交集 / 我的影响力一流水准 UX 与接口扩展准出”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“我的交集 / 我的影响力一流水准 UX 与接口扩展准出”对应动作。
- THEN 主页 slogan、我的交集、我的影响力不再引入暖金棕第二主调；蓝色仅用于 CTA、一级 Tab 选中态、可点击文字与弱入口，类型图标使用非品牌蓝低饱和语义色阶。
- THEN 我的交集与我的影响力卡片具备足够呼吸感；预览行与底部入口不渲染多余 chevron，可点击文字清晰但克制。
- THEN 交集与影响力详情页使用与 ProfileStatsPage 一致的一级 segmented control，Tab 为 [交集|影响力]；从我的交集入口默认交集 Tab，从我的影响力入口默认影响力 Tab。
- THEN 详情页完整实例化交集规格主要类型（关系/身份/内容/地点/兴趣及喜欢/分享/想去/同行等派生来源）与影响力主要类型（community/decision/relationship/knowledge/spread/audience），样例来自 contract fixture，不在 UI 编造。
- THEN 交集接口维持 summary/list/visit 分离；列表接口必须支持 dimension/filter/sourceRef/timeBucket/cursor/limit 扩展参数，访问列表推进水位不得阻塞首屏渲染。
- THEN 影响力接口维持 authorId 维度聚合读模型；GetAuthorImpact P95 ≤ 500ms，ListAuthorImpactEvidence 以 opaque cursor 分页，后续新增 helpType/action/tagRef 不需要改 UI 分支。
- THEN 支持的行为动作按 authorId 聚合，摘要计数与幂等证据总数一致，证据按 opaque cursor 稳定分页并且不泄露行为用户身份。
- THEN App 只读展示服务端下发的 primaryText、count 与证据，空证据不编造全量，不本地估算影响力。
- THEN 影响力面「成行力」行消费 creator 锚点社会证明成形/经历两级诚实计数，成形为 0 或读取失败整行不渲染，端不估算。
- AND Gamma-local 以 production Remote `AuthorImpactQuery` 回读 summary 与 evidence；验收种子只写
  `rm_author_impact_evidence`，不得回填已退役摘要集合制造卡片事实。

<a id="sit-006"></a>
### SIT-006 职业与兴趣资料页标签同源、编辑保存与交集索引投影

- GIVEN 执行“职业与兴趣资料页标签同源、编辑保存与交集索引投影”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“职业与兴趣资料页标签同源、编辑保存与交集索引投影”对应动作。
- THEN /profile/career-interests 独立页面从编辑资料页进入，页面结构为职业身份、我的标签、全部兴趣，不展示推荐标签。
- THEN 职业通过 Audience/用户/职业 查询并保存单个叶子 tagRef；兴趣通过 Audience/用户/兴趣偏好 查询并保存有序叶子 tagRefs，最多 30 个、允许清空。
- THEN 端侧在四环境通过 Remote ListTagChildren / ResolveTag / ValidateTagRefs 查询与校验；服务契约不接受 Topic/兴趣/*。
- THEN user-service 拒绝非法根、分类父节点、职业多选与兴趣超限；保存成功后投影 object_tag_index 的 user 对象 tagRefs。
- THEN alpha/beta/gamma/prod 均由 control_plane/governance/taxonomy 生成同一标签发布包；beta/gamma/prod 通过 tag import 与 object index import/backfill 灌入。

<a id="sit-008"></a>
### SIT-008 我的主页交集资产面（可行动分层、我的行动、共同经历）

- GIVEN 当前 persona 已登录，云侧交集读面与 Gathering 公开读面可用。
- WHEN 用户打开我的主页与我的交集详情页。
- THEN 详情页交集 Tab 的可行动交集（actionHints 非空且未过期）置顶为「可约」分组，组内顺序与云侧下发一致，主行动经 `IntersectionTargetNavigator.openActionHint` 分发。
- THEN 收件箱预览卡存在可行动交集时展示「可约 N」入口并可进入详情页可约分组，无可行动交集时不渲染该入口。
- THEN 我的主页「我的行动」入口消费 `ListMyHostedGatherings` host 本人私有读面（含 draft 与非公开行动），分组页按 lifecycleStatus × temporalPhase 四分组（即将开始/草稿/已结束/已取消），行动卡直通 Gathering 详情，无行动时折叠为单行入口。
- THEN 「共同经历」资产行消费 `ListMyIntersections(sourceRef=coExperiencedGathering)` 直出云侧主句，无经历交集时区块不渲染。
- THEN 影响力面「成行力」行消费 creator 锚点社会证明两级诚实计数，成形为 0 或读取失败不渲染。
- AND 任一模块读取失败均呈现可恢复错误态且不阻塞主页首屏，负例是读取失败不得伪造"暂无行动/暂无经历"空态。

## 8. 开放事项

<a id="open-005"></a>
### OPEN-005 交集卡 gamma 真打 shared-tags 证据待环境

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 gamma 真实环境证据——`SIT-003` 的「gamma 真打 shared-tags 对已打标对象返回非空」依赖 gamma-local 恢复（当前 startup Provider runtime identity is not current）；other 主页交集卡渲染/空态、onReasonTap 归因上报、resonance 零残留均已有 local_contract 覆盖。
- 完成判定：`SIT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-006"></a>
### OPEN-006 影响力 Gamma-local 回读证据待环境

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 gamma 真实环境证据——`SIT-005` 的「Gamma-local 以 production Remote `AuthorImpactQuery` 回读 summary 与 evidence」依赖 gamma-local 恢复；视觉基调、卡片呼吸感、详情页 segmented、fixture 实例化、接口扩展参数、成行力两级计数等子句均已有 local_contract 覆盖（author_impact_card/evidence_sheet、my_intersection_inbox、creator_flywheel_proof_row 套件与 `author_impact_gamma__api_integration_test.dart` runner 就位）。
- 完成判定：`SIT-005` 对应行为满足且真实测试 `spec_ref` 有效

- 依赖：behavior/intersection 事件归因与 content/user projection。

<a id="open-009"></a>
### OPEN-009 我的主页交集资产面 gamma 端云证据待环境编排

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 gamma 真实环境证据——`REQ-008` 的端侧实现与 `SIT-008` local_contract 层已闭合（可约分组/入口、我的行动私有读面四分组、共同经历资产行、成行力行均有 widget/domain/服务端契约测试 `spec_ref`），host 公开与私有读面的 App api_integration runner 与 `profile_journey` UAT 交集资产面断言段均已就位。执行入口为 `stackctl app-domain-api-integration --target gamma-local`（topology 投影注入，无手写 URL）。gamma-local 收口权已正式移交环境编排主线：三轮攻坚中 package 尝试均命中其 runtime 互斥锁，且观察到主线多轮 down→package→up→health 循环仍失败于同一根因（`startup Provider runtime identity is not current`，最新证据 `.qwq_output/env/gamma/runs/20260813T041624056444Z-*-health-gamma-local`）。attestation 输入已定位（`content-gamma-research-pool-20260811-001` + 回滚基线）。
- 目标：gamma 恢复后执行 `gathering_list_by_host_remote__api_integration_test.dart`（含 `ListMyHostedGatherings` 诚实空页断言）与 `profile_journey__user_acceptance_test.dart` 的交集资产面断言段（经历交集出现、资产行渲染、我的行动分组页回读）。
- 完成判定：`SIT-008` 的 api_integration 与 user_acceptance 层在 gamma 通过且真实测试 `spec_ref` 有效
