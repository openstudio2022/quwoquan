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
- 首屏模块顺序为身份区、CTA、交集、影响力、Tab、双列内容流；不再首屏展示粉丝/浏览/点赞数据面板。
- 他人主页模块命名为我与TA的交集、TA的影响力；我的主页模块命名为我的交集、我的影响力（禁止「我的连接」：与交集域收件箱口径冲突，见 [`intersection-unified-experience` REQ-005](../../object-homepage-network/intersection-unified-experience/spec.md#req-005)）。
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
- 首屏必须具备 skeleton、下拉刷新、cursor 分页、分页尾部 loading、inline retry、owner/other 分型空态、private/blocked 权限卡；`viewerContext.canViewFullProfile=false` 时直接命中权限态，不渲染假列表。
- 方向切换固定放在互动二级控制行右侧：`[收到的 | 我发起的]`；不得叠放在一级 `记录 / 互动 / 足迹` Tab 行。
- 一级 Tab `footprint` 由 codegen `profile_tabs`（`user/account/user_account/ui_config.yaml`）驱动，端侧不得硬编码 Tab id/文案。
- `ListFollowers / ListFollowing / ListUserCircles` 一律支持 `query + cursor + limit`；统计详情页搜索必须走云侧当前 subject 范围过滤，不接受单页本地 `contains` 伪搜索。
- 统一到底部导航「小趣」入口，减少操作按钮行的视觉拥挤
- 我的与他人主页必须完成交集卡点击、归因上报与跳转；`记录/互动/足迹` 可切换，足迹在他人主页不可见并遵守可见性过滤。
- 交集卡 `onReasonTap` 上报 `BehaviorEvent.intersectionDimension/intersectionTagRefs`（统一归因，废止旧 `reasonType` 闭集）。

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
- THEN 首屏模块顺序为身份区、CTA、交集、影响力、Tab、双列内容流；不再首屏展示粉丝/浏览/点赞数据面板。
- THEN 他人主页模块命名为我与TA的交集、TA的影响力；我的主页模块命名为我的交集、我的影响力。
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

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 账号封禁状态流缺少生产者与跨域级联

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：账号封禁无法可靠阻断下游写入并向 App 投影可恢复状态。
- 完成判定：相关缺口消失，目标节点的要求与可观察验收通过。

<a id="open-003"></a>
### OPEN-003 ProfileShell 统一组件 + 一级 3 Tab（codegen 驱动）mine/other 差异

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：mine/other 共用 ProfileShell（ObjectPageShell 壳层），差异区（操作按钮/工具栏/可见性/交集卡）按模式正确切换。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 创作 SubTab/可见性、统计详情、互动内容与端云数据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：创作 SubTab（全部/图片/视频/文字）+ 可见性过滤（mine 含私密、other 仅公开）正确。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 我与TA的交集卡真闭环 + 行为归因 + resonance 零残留

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：other 主页交集卡经 objectSharedReasonsProvider → sharedTags → IntersectionReason 渲染；无交集展示稳定空态。
- 完成判定：`SIT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-006"></a>
### OPEN-006 我的交集 / 我的影响力一流水准 UX 与接口扩展准出

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：主页 slogan、我的交集、我的影响力不再引入暖金棕第二主调；蓝色仅用于 CTA、一级 Tab 选中态、可点击文字与弱入口，类型图标使用非品牌蓝低饱和语义色阶。
- 完成判定：`SIT-005` 对应行为满足且真实测试 `spec_ref` 有效

- 依赖：behavior/intersection 事件归因与 content/user projection。
