# 个人主页全面重构（我的 + 他人主页统一化）

> 2026-06-14 高保统一落地补充
>
> 本阶段以“四类主页高保统一落地”为当前执行口径：用户主页与我的主页首屏统一为
> `身份区 -> CTA -> 交集 -> 影响力 -> Tab -> 内容流`。首屏 CTA 固定为他人主页
> `关注 / 私信`、我的主页 `管理分身 / 编辑资料`；浏览历史收敛到一级 `足迹` Tab。
> Profile 一级 Tab 当前收敛为 `记录 / 互动 / 足迹`，圈子作为统计数字与粉丝/关注同层进入
> 统计详情页，不再占据主页一级 Tab；作品二级只保留
> `全部 / 图片 / 视频 / 文字`，其中底层类型仍为 `article`，展示筛选用“文字”。
> “文章”只用于正式内容类型或详情语境，“长文”只用于编辑创作语境。
>
> 交集表达以用户可解释语言为准：他人主页为 `我与TA的交集`，我的主页为 `我的连接`；
> 影响模块为 `TA的影响力` / `我的影响力`，均采用纵向列表；可点击文字、一级 Tab 选中态与
> 「查看全部」弱入口使用克制蓝色阶，类型图标使用非品牌蓝低饱和语义色。

> 版本口径冻结（V5，参见 specs/changelog/CR-20260531-027）：本 spec 为 `profile-homepage-redesign` 能力的**唯一冻结口径**。本次 V5 在历史 `profile-commercial-readiness`（已上线收窄子集）基础上**全量补全**，并明确以下三处与历史口径的差异，**不向后兼容旧实现**：
>
> 1. **一级 Tab 收敛为 3 个**：`[记录 | 互动 | 足迹]`；`圈子`作为统计数字进入`粉丝 / 关注 / 圈子`三 Tab 详情页，`足迹`承载浏览历史列表。
> 2. **profile 内容形式只有三类**：文章 / 图片 / 视频（均为 `contentIdentity=work` 作品）。**profile 不存在「微趣」概念**；`moment/micro`（点滴微动态）是 content/discovery 域的独立活跃概念，不进 profile 创作 Tab。历史 spec/commercial-readiness 中创作含「微趣」的表述在 V5 一律废止。
> 3. **交集卡为真闭环**：`我与TA的交集` 卡由 tag-service `shared-tags` 真实倒排数据驱动（`object_tag_index` 打标管道），统一到 `IntersectionReason`；历史 `resonance`（共鸣）旧链路全部删除，不保留。

## 背景与动机

当前个人主页存在严重的体验和工程质量问题：

1. **代码重复**：`my_profile_page.dart`（1546行）与 `author_profile_page.dart`（2539行）存在 80%+ 重复代码（背景图拉伸、头像、统计行、Tab 框架），但数据源、操作按钮不同，维护成本高且易产生不一致。
2. **Tab 结构与发现页脱节**：发现页使用 `[微趣, 作品]` 双轨道，个人主页使用 `[创作, 互动, 生活]`，内容分类语义不统一，用户在发现页看到的分类无法在主页上找到对应。
3. **圈子入口层级不清**：个人主页同时存在圈子 Tab 与统计数字语义，用户需要在统计层直接进入已加入圈子列表。
4. **目录结构违规**：`my_profile_page` 仍在 `lib/features/profile/`，未按领域规范迁移到 `lib/ui/user/`。
5. **编码质量低下**：大量硬编码间距（`16.w`, `50.h`, `140.w`）、非语义颜色引用、中文硬编码文案，违反设计系统规范。
6. **数据源割裂**：`my_profile_page` 使用 `_generateMockPosts()` 硬编码假数据，而 `author_profile_page` 已接入 `userProfileRepositoryProvider`。
7. **零测试覆盖**：user 域没有任何 L1a/L1b/L1c 测试。
8. **端云 DTO 缺失**：用户域无 codegen 生成的类型化 DTO（`user_profile_dto.g.dart`），端侧仍使用手写 User model。

## 目标用户

- 所有趣我圈用户（查看自己的主页、管理创作内容、查看已加入圈子）
- 其他用户（浏览他人主页、关注互动、查看共同交集）

## 功能范围

### F1: ProfileShell 统一组件

将我的主页和他人主页的 80%+ 共性 UI 抽取为统一的 `ProfileShell` 组件，通过 `ProfileMode.mine / ProfileMode.other` 枚举切换差异区域：

**共享区域**：
- 背景图 + 下拉弹簧阻尼拉伸 + 回弹动效
- 头像 **靠左对齐**（非居中），侵入背景图区域 1/3（顶部 1/3 在背景区内，底部 2/3 在用户信息区内）
- 用户名与头像 **同行显示**（Row 布局），垂直对齐到头像下部 2/3 区域；**不显示 @username**
- bio、统计行、交集卡片、Tab 导航框架
- 滚动吸顶：上滑过头像/名字后，小头像+名字平滑过渡到顶部工具栏；继续上滑一级 Tab 吸顶
- 暗色模式全面支持：所有背景、前景、渐变、工具栏颜色通过语义 Token 切换

**mine 差异**：操作按钮 = [管理分身, 编辑资料]（等宽双按钮）；创作可见性含「私密」；顶栏 = [设置]
**other 差异**：操作按钮 = [关注/已关注, 私信]（等宽双按钮，与 mine 布局一致）；无「私密」；顶栏 = [返回, 更多]

### F2: 一级 Tab 与统计入口重新设计

一级 Tab：`[记录 | 互动 | 足迹]`，默认选中「记录」。一级 Tab 由 codegen `profile_tabs`（`user/user_profile/ui_config.yaml`）驱动，端侧不得硬编码 Tab id/文案；`足迹`为浏览历史入口，不再占用首屏 CTA。

命名语义：「创作」= 用户发布的全部原创**作品**（`contentIdentity=work`），内容形式为 文章 / 图片 / 视频 三类。**profile 不引入「微趣」(moment/micro) 概念**——点滴微动态属 content/discovery 域，profile 创作 Tab 不展示。

统计区统一为 `粉丝 / 关注 / 获赞 / 圈子` 四项，数字可点击：粉丝、关注、圈子进入统一统计详情页并默认落在对应一级 Tab；获赞进入现有互动 Tab 的点赞子维度，不新增第二条点赞列表。

### F3: 创作 Tab（二级分类 + 可见性过滤）

- 二级 SubTab：`[全部 | 图片 | 视频 | 文字]`
  - 与 `contentType` 对齐：`image(photo) / video / article`（三类作品形式，不含 moment）
  - SubTab 由 codegen `profile_tabs.creations.sub_tabs` 驱动
- 可见性过滤：点击已选中的「创作」Tab 弹出 popup
  - 我的主页：`[全部 | 公开 | 私密]`
  - 他人主页：`[全部 | 公开]`（无「私密」选项）
  - 私密作品封面叠加锁标
  - 选中非「全部」时，Tab 文字旁显示筛选指示器

### F4: 主页统计详情页（粉丝 / 关注 / 圈子）

- 统计详情页为主页统计行进入的**统一二级关系页**；单一路由保持 `/profile/stats?type=fans|following|circles&userId=...`，永久固定三 Tab，不新增第四个「获赞」Tab。
- 顶部 chrome 与资料编辑/设置页同源，使用 `SettingsInsetMemberPickerPageScaffold` 语义：leading 为 iOS chevron back，middle 为等宽 segmented selector `[粉丝 | 关注 | 圈子]`；正文区不得再放第二条 tab strip，不使用 underline 选中样式。
- 搜索条作为列表首块紧贴顶栏下方；粉丝/关注/圈子三页签分别独立记忆 `query / scroll offset / cursor / loaded items`，切回时恢复对应状态。
- 粉丝/关注列表统一为 `头像 + displayName + @handle + 关系/可见性辅助信息 + trailing 动作`；trailing 按钮完全由 `RelationshipCapability` 驱动，禁止页面本地拼 `isFollowing` 布尔。
- `following / mutual` 按钮点击进入 iOS action sheet，仅提供 `取消关注 / 发消息 / 取消`；`self / blocked / restricted` 行不显示或禁用关系动作。
- 圈子列表展示用户已加入的全部圈子（我的主页）或公开可见圈子（他人主页）；行结构为 `封面/头像 + 圈名 + 成员数/创作数 + 可见性 + chevron`，本期默认只做浏览与跳转，不伪造 membership 按钮。
- 首屏必须具备 skeleton、下拉刷新、cursor 分页、分页尾部 loading、inline retry、owner/other 分型空态、private/blocked 权限卡；`viewerContext.canViewFullProfile=false` 时直接命中权限态，不渲染假列表。

### F5: 互动 Tab

- 子维度：`[赞 | 评论]`
- 方向切换：`[收到 | 发出]`（我的主页）/ 仅 `[Ta收到]` 公开部分（他人主页）
- 互动列表：头像 + 用户名 + 互动内容摘要 + 时间

### F6: 足迹 Tab（浏览历史，仅本人可见）

- V5 收敛：历史「生活」一级 Tab（`[足迹 | 书影音 | 味蕾 | 爱物]` 基于 `UserLifeItem`）在 V5 **废止为 profile 一级 Tab**；`足迹`提升为独立一级 Tab，承载**浏览历史**（只读消费轨迹），不再依赖 `UserLifeItem`。
- 一级 Tab `footprint` 由 codegen `profile_tabs`（`user/user_profile/ui_config.yaml`）驱动，端侧不得硬编码 Tab id/文案。
- 隐私门控：`modes: [mine]`，**仅本人主页可见**；他人主页一级 Tab 仅 `记录 / 互动`，不出现足迹（浏览历史不对他人下发）。`ProfileShell` 按 `mode` 过滤一级 Tab，由 `UserProfileTabConfig.visibleInMode(mode)` 强约束。
- 数据源：复用既有浏览历史能力（`GET /v1/content/footprint`），**不新增后端 API、不读取 `UserLifeItem`**。
- 列表视图；所有文案语义化（`UITextConstants`/l10n），零硬编码中文。
- 废止历史孤儿 `ProfileLifestyleTab` 手写模型与脱离 ui_config 的 `LifestyleSubTab` 实现；`UserProfileUIConfig.lifestyleSubTabs` 在 V5 为空。
- 说明：`user/user_life_item`（书影音/味蕾/爱物）**保留为独立后端能力域**，但在 V5 **不作为 profile 一级 Tab 暴露**，避免在主页制造第二套 Tab 真相源。

### F7: 目录迁移与 features/ 清退

- `features/profile/*` 全部迁移到 `lib/ui/user/*`
- 更新 `app_router.dart` 路由指向
- 更新所有 import 路径
- 删除 `features/profile/` 目录

### F8: 端云 DTO 对齐

- 推进 `contracts/metadata/user/user_profile/fields.yaml` → `codegen-app` → `user_profile_dto.g.dart`
- 扩展 `UserProfileRepository`：新增 `listUserCircles()` / `getUserStats()`
- `ProfileSocialRelationRowWire` 补齐 `username / userHandle / profileVisibility / relationState / followedAt / relationshipCapability`，明确其语义为 **viewer -> row 主体** 的关系能力，而非主页主体对 row 的关系。
- `ListFollowers / ListFollowing / ListUserCircles` 一律支持 `query + cursor + limit`；统计详情页搜索必须走云侧当前 subject 范围过滤，不接受单页本地 `contains` 伪搜索。
- Mock 数据补齐圈子列表和统计数据

### F9: 私人助理入口移除

- 从我的主页操作按钮行移除「私人助理」入口
- 统一到底部导航「小趣」入口，减少操作按钮行的视觉拥挤

### F10: 视觉一致性与设计 Token 全面对齐

- 所有间距使用 `AppSpacing.*` 语义标签
- 所有颜色使用 `AppColorsFunctional.getColor()` / `AppColors.*`
- 所有字号使用 `AppTypography.*`
- 所有文案使用 `UITextConstants.*` 或 l10n
- Tab 导航与发现页、圈子页复用 `CenteredScrollableTabBar` 组件
- 可交互热区下限 44×44，主操作 48×48
- 深色模式全面适配：背景渐变、工具栏折叠态、分界区衔接、所有前景色均通过语义 Token 跟随暗色切换

### F11: 四层测试覆盖（三层测试）

- local_contract: 契约/单测（UserProfile DTO、`profile_tabs` 收敛为 `记录/互动/足迹` 且 footprint 隐私门控、`IntersectionReason` 5 维度闭集、tag `shared-tags` 契约字段、`ObjectTagIndexWriter` upsert 幂等；`UserLifeItem` DTO 作为保留后端域单独契约测试，不作为 profile 一级 Tab）
- local_contract: Widget/Provider（ProfileShell mine/other 渲染、创作 SubTab 切换与可见性过滤、互动 Tab、足迹 Tab 隐私门控 mine 渲染/other 不渲染、交集卡 mine 不展示/other 有交集展示/无交集稳定空态、`ProfileActionBar` 五态、Mock 异常/边界）
- api_integration: 端云集成（gamma 真打 `shared-tags` 对已打标对象非空并映射成 `IntersectionReason`、ProfileInteractionActivities keyset 分页、relationship 五态；每条 api_integration 断言在 local_contract 有对应 Mock 断言）
- user_acceptance: 端到端旅程（我的/他人主页完整旅程、交集卡点击→归因上报→跳转、`记录/互动/足迹` 一级 Tab 切换、足迹他人主页不可见、可见性过滤）

### F12: 我与TA的交集卡（真闭环）

- `ProfileShell` other 模式渲染 `ObjectIntersectionCard`，数据经 `objectSharedReasonsProvider` → `TagRepository.sharedTags`（真打 `/v1/tag/shared-tags`）→ `IntersectionReason`。
- 云侧打通 `object_tag_index` 对象打标管道（tag-service 新增 `ObjectTagIndexWriter` + Mongo upsert + 离线批量导入工具），数据源为 `content/post.tagRefs`、`social/circle.tags`、`user/user_profile.interestTags`，使 gamma/prod 对真实对象出非空交集。
- 交集卡 `onReasonTap` 上报 `BehaviorEvent.intersectionDimension/intersectionTagRefs`（统一归因，废止旧 `reasonType` 闭集）。
- 无可解析交集时展示稳定空态（不造假、不隐藏模块）。

### F13: resonance 旧链路彻底清理（不兼容）

- 删除孤儿 `ResonancePage` + 路由 `/profile/resonance`（经 metadata 重生 `AppRoutePaths`）、`resonance_buddy_view_data.dart` + prototype 假数据、`UserProfileRepository.resonanceBuddyPreviewWireRows()` 抽象/Mock/Remote 三层、`myResonance` 文案 + l10n。
- 删除孤儿 `ProfileMomentsTab`（profile 无微趣）、孤儿枚举 `ProfileTab`、user 侧 `activeWorkFormat/setWorkFormat` 残留状态。
- 结构化 `profile_state_provider.dart` 空 catch（R17）。
- 「我的交集/共鸣」语义统一由 `IntersectionReason` + `ObjectIntersectionCard` 表达，不保留第二数据通路。

### F14: 职业与兴趣资料页（career-interest-profile-editor）

- 在“编辑资料”中新增独立 `职业与兴趣` 页面，路径 `/profile/career-interests`，页面结构固定为 `职业身份 / 我的标签 / 全部兴趣`，不再展示推荐标签。
- 职业与兴趣标签均以 `quwoquan_data/publish/tags` 为唯一真相源：职业使用 `Audience/用户/职业`，兴趣使用 `Audience/用户/兴趣偏好`；端侧通过 tag-service `ListTagChildren / ResolveTag / ValidateTagRefs` 查询与校验，不维护第二套枚举。
- 保存接口复用 `GET /v1/user/profile/edit-snapshot` 与 `PATCH /v1/user/profile`，字段为单选 `occupationTagRef` 与有序 `interestTagRefs`；兴趣最多 30 个、允许 0 个，重复输入去重保序。
- UX 对齐个人资料页 iOS 列表风格：顶部 `< 职业与兴趣 保存`，职业单行入口；职业选择采用“大类列表 -> 二级职业列表”的两级导航；我的标签默认可编辑但不展示操作说明文案，支持右上角 `×` 删除、长按拖拽排序与轻微摇曳；全部兴趣为轻量分类胶囊 Tab + 4 列文字标签网格，添加符号与文字必须有独立避让空间，添加后从全部兴趣隐藏。
- 保存成功后 user-service 将职业与兴趣 tagRefs 投影到 tag-service 约定的 `object_tag_index` `user` 对象索引，供 `shared-tags`、推荐解释与小趣助手偏好理解使用。
- 环境集成：alpha 使用同源 contract/mock fixture；beta/gamma 通过 tag import 与 object index import/backfill 灌入；prod 发布包包含同一标签树与幂等导入/回填入口。

## 不做什么（Out of Scope）

- **O1**: 用户档案编辑页整体重构（`edit_profile_page.dart` 保持现有实现），但 `career-interest-profile-editor` 是明确例外：职业与兴趣从旧内嵌标签页升级为独立页面与端云标签闭环。
- **O2**: 分身管理页重构（`persona_management_page.dart` 保持现有实现）
- **O3**: 大范围重写统计详情页之外的数据契约；`profile_stats_page.dart` 仅升级为粉丝/关注/圈子三 Tab 容器，继续复用现有 Repository 与列表能力
- **O4**: 圈子推荐算法（圈子 Tab 仅展示已加入列表，不含推荐）
- **O5**: content/discovery 域的 moment/micro（点滴微动态）能力变更——profile 不引入微趣，但也不修改 content 域既有 moment 实现
- **O6**: 其他 features/ 目录迁移（create、assistant、settings、welcome 不在本次范围）
- **O7**: object_tag_index 的**事件驱动增量管道**完整落地（V5 落地 `ObjectTagIndexWriter` 接口 + 离线批量回填；MQ consumer / user `InterestTagsUpdated` 事件化作为收敛后续，见 CR-20260531-027）
- **O8**: user-service / content-service / circle-service 既有 Go 业务逻辑重写（V5 仅在 tag-service 内新增打标写能力 + 跨源读取回填，不改三个源服务的写路径）

> 说明：历史 spec 的 O3（resonance 仅迁移）、O8（Go 云侧不实现）在 V5 **已反转为范围内**（见 F12/F13），因为 V5 全量口径要求交集真闭环、resonance 清理。历史 O6「生活 Tab 不重构」在 V5 进一步**反转方向**：不再重做生活 Tab，而是**废止生活一级 Tab**，由 `足迹`（浏览历史，mine-only）取代为一级 Tab（见 F6）。

## 适用范围与约束

### 适用范围

- 端侧 Dart/Flutter 主页重构（`lib/ui/user/`）
- metadata 补齐与 codegen（`contracts/metadata/user/`、`lib/cloud/runtime/generated/user/`）
- 端侧 Repository 扩展（`lib/cloud/services/user/`）
- 四层测试建立（`test/ui/user/`）

### 约束

- **技术约束**：
  - DDD 分层：UI 通过 Provider 访问 Repository，禁止直接实例化 Mock/Remote
  - 所有新代码必须通过 `flutter analyze` + `verify_dart_semantic.py` 无新增违规
  - codegen 文件 `DO NOT EDIT` 禁止手改
  - ProfileShell 必须支持 Riverpod Provider 注入，不能用构造函数直接传 Repository
- **设计约束**：
  - Tab 导航语义必须与发现页、圈子页保持一致层级结构
  - 创作 SubTab 的 contentType 枚举必须与 `ContentUIConfig.discoveryTabs` 对齐
  - 可见性过滤的交互模式借鉴抖音（点击已选中 Tab 弹出过滤 popup）
- **不适用情形**：
  - Go 云侧 Handler 实现不在本 spec 范围
  - 端侧 Web/Desktop 适配（仅 mobile）
  - 足迹 Tab 复用既有浏览历史 API（`GET /v1/content/footprint`），不新增后端 API

## 对标输入与吸收结论

### 抖音个人主页

| 维度 | 抖音 | 借鉴 | 适用边界 |
|------|------|------|---------|
| 一级 Tab | [作品, 收藏, 喜欢] | 不借鉴 | 抖音纯视频，极简三栏；趣我圈多内容形态+圈子，需更丰富分类 |
| 公开/私密过滤 | 点击已选中 Tab 弹出筛选 | **借鉴** | 交互自然、不占额外空间，完全适用 |
| 私密标识 | 封面加锁标 | **借鉴** | 视觉清晰，用户认知成本低 |
| 网格布局 | 3列等比 | 部分借鉴 | 创作 Tab 用2列瀑布流（与发现页一致）；足迹 Tab 为浏览历史列表，非网格 |
| 2级触达 | 从4级优化到2级 | **借鉴** | Tab + SubTab = 2级，高效 |
| 收藏/喜欢独立 Tab | 与作品平级 | 不借鉴 | 收纳到互动 Tab 子维度，避免一级 Tab 过多 |

### 内部对标

- **发现页** `discovery_page.dart`：双轨道 `[微趣, 作品]`，Tab 组件 `CenteredScrollableTabBar`，contentType 枚举 → 创作 SubTab 对齐
- **圈子页** `circles_page.dart`：圈子卡片样式、分类导航 → 统计详情页的圈子列表复用

## 商用基线（V5 冻结）

### SLO / KPI

| 指标 | 目标 | 说明 |
|---|---|---|
| 主页首屏 TTI | P95 ≤ 1.5s（缓存命中 ≤ 600ms） | 进入 `/profile`、`/user/:id` 到首屏可交互 |
| 背景拉伸回弹 | ≤ 300ms 无掉帧 | 弹簧阻尼回弹 |
| Tab 切换响应 | P95 ≤ 200ms | 一级/二级 Tab |
| 交集卡解析 | shared-tags 请求 P95 ≤ 500ms | 失败/空集时展示稳定空态、不阻塞首屏 |
| 交集卡曝光率（KPI） | other 主页交集卡曝光占比可观测 | 北极星「交集」可见度 |
| 交集行动转化（KPI） | 交集卡点击→关注/私信转化可归因 | 经 `intersectionDimension/intersectionTagRefs` |

### 权限边界

- mine：可见全部内容（含私密创作）、编辑资料、管理分身、设置入口。
- other：仅可见公开内容；私密创作不下发；互动 Tab 仅「Ta 收到」公开部分；无编辑/管理入口。
- 交集卡仅 other 模式展示，且 shared-tags 仅基于双方公开可计算的 tagRef 倒排，不泄露对方私密信号。
- relationship 五态由 `follow_edge` 能力位驱动，含 `isBlocked/isBlockedBy` 时按规则禁用关注/私信/通话。

### 数据生命周期

- `UserLifeItem`：用户主动创建/编辑/删除；删除即从列表移除（无软删保留承诺）。
- `occupationTagRef / interestTags`：声明式用户职业与兴趣，用户可改；变更后经 user-service 写时投影或离线 backfill 刷新 `object_tag_index`，标签定义只来自 tag-service 导入产物。
- `object_tag_index`：派生倒排数据，源对象删除/改标后由回填管道幂等 upsert 修正；非权威真相，可重建。
- 行为归因事件（`BehaviorEvent`）：按现有 behavior 域保留策略与 TTL，不在本 spec 新增留存承诺。

### 灰度与回滚

- 灰度：交集卡真数据依赖 gamma/prod `object_tag_index` 打标产物；打标产物缺失时交集卡自动空兜底（契约正确、不报错），可独立于打标管道先行发布前端。
- 一级 Tab / 创作 SubTab 由 codegen `profile_tabs` 驱动，支持配置层灰度（feature flag 留存口子）。
- 回滚：V5 不向后兼容旧 resonance 实现；回滚以 git revert 整切片为单位（S2 云侧打标、S3-S5 端侧）；打标管道回滚仅影响交集卡数据（退化为空兜底），不影响主页其余功能。

### 观测方案

- 主页页面级埋点：`MyProfilePage`/`OtherProfilePage` 曝光、停留；Tab 切换、内容曝光归因（R20）。
- 交集卡：曝光、`onReasonTap` 点击、解析空集率、shared-tags 请求耗时/失败率。
- 云侧：tag-service `shared-tags` 请求量、命中非空率、P50/P95 延迟；打标管道导入对象数/tagRef 覆盖率。
- referralSource：进入主页与从主页跳出均透传来源，保证归因链不断（R21）。

## 验收重点

核心维度（详见 acceptance.yaml）：
1. ProfileShell 统一组件 mine/other 差异正确
2. 一级 Tab 结构 [记录|互动|足迹] 渲染与交互（codegen 驱动），圈子降为统计数字
3. 创作（记录）Tab 二级分类（图片/视频/文字，无微趣）与可见性过滤
4. 圈子统计详情页展示已加入圈子卡片与跳转（圈子非一级 Tab）
5. 足迹 Tab：浏览历史只读列表 + 隐私门控（`modes: [mine]`，他人主页不可见）+ 零硬编码
6. 端云 DTO codegen 对齐（含 `UserProfile` DTO；`UserLifeItem` 域保留为独立后端能力，不作为 profile 一级 Tab）
7. 我与TA的交集卡真闭环（shared-tags 真数据 + 归因）
8. resonance 旧链路零残留
9. 四层测试覆盖（三层测试）
10. 视觉一致性：零硬编码，全语义 Token
11. SLO/KPI、权限、生命周期、灰度回滚、观测达成
