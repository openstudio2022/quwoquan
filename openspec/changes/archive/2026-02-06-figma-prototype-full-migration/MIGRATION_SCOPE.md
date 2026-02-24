# Figma 原型全量迁移 - 范围与原型源码映射

**原则**：无任何折扣，全部按 **趣我圈2026/src** 下对应 TSX/React 源码迁移。布局、样式、路由、交互、角色/状态差异均需与原型代码一致。

---

## 一、发现页（Discovery）

| 范围 | 原型源码 | 说明 |
|------|----------|------|
| 发现页整体 | `Home.tsx` → `DiscoveryFeed.tsx` | 发现频道容器与 Tab 结构 |
| Tab：微趣/美图/视频/文章 | `DiscoveryFeed.tsx`（CATEGORIES: moment=微趣, photo=美图, video=视频, article=文章） | 与 TSX 常量一致，注意「美图」非「图片」 |
| 微趣流 | `DiscoveryFeed.tsx`（activeType===moment 时的 discoveryData） + `DiscoveryItem.tsx` | 微趣卡片、转发引用、媒体 |
| 美图/图片流 | `DiscoveryFeed.tsx`（photo） + `MasonryLayoutEngine.tsx` / 瀑布流 | 瀑布流布局与卡片 |
| 视频流 | `DiscoveryFeed.tsx`（video） + `VideoImmersionView.tsx` | 视频沉浸、剧场模式、onTheaterModeChange |
| 文章流 | `DiscoveryFeed.tsx`（article） + 文章卡片 | 文章列表与点击→文章详情 |
| 小趣悬浮球 | 发现页底部入口（见小趣章节） | 与原型位置、样式一致 |
| 点击作者/圈子/帖子 | `App.tsx` handleSelectAuthor, handleSelectCircle, handlePostClick | 作者主页、圈子主页、沉浸查看器/文章详情 |

---

## 二、圈子页（Circles）

| 范围 | 原型源码 | 说明 |
|------|----------|------|
| 圈子频道列表 | `CirclesFeed.tsx` | 兴趣维度、创建圈子 FAB |
| 圈子主页 | `CirclePageV2.tsx` | 单圈主页，支持 initialRole |
| 角色差异 | `CirclePageV2.tsx`（CircleRole: owner \| admin \| member \| visitor） | **管理员/圈主**：编辑圈子、管理中心；**用户/已加入**：已加入/关注圈子；**游客**：加入/关注按钮、准入规则（open/approval/invite） |
| 加入状态 | `CirclePageV2.tsx`（joinStatus: none \| pending \| joined） | 未加入、待审核、已加入的 UI 与按钮 |
| 3-Tab：创作/互动/生活 | `CirclePageV2.tsx`（TabType: works \| interaction \| lifestyle） | 与作者主页一致的 Tab 结构 |
| 创作子分类 | works + SubCategory（all/photo/video/article/…） | 全部/图片/视频/文章等 |
| 互动子分类 | interaction + likes/comments、received/sent | 赞/评论、Ta收到/Ta发出 |
| 生活子分类 | lifestyle + footprint/soul/taste/private | 足迹/书影音/味蕾/爱物 |
| 子频道/频道页 | `circle-tabs/`（FeaturedTab, GalleryTab, DiscussionTab, ChatTab, CollectionTab, MoreTab 等） | 若有「创作/讨论/生活/聊天」子频道，按 TSX 实现 |
| 统计与列表 | `CirclePageV2.tsx` + `AuthorStatsList.tsx`（members/groups/fans/likes） | 成员/群组/粉丝/获赞、点击打开列表 |
| 编辑/管理中心 | `CircleManagementModals.tsx`（EditCircleModal, CircleManagementCenter） | 圈主/管理员专用 |

---

## 三、创作页（Create）

| 范围 | 原型源码 | 说明 |
|------|----------|------|
| 创作入口抽屉 | `CreateEntrySheet.tsx` | 微趣三入口（照片/文字/视频）、作品三入口（图片/文章/视频） |
| 创作页容器 | `CreatePage.tsx` | 四 Tab：moment \| photo \| video \| article |
| 微趣创作 | `CreatePage.tsx`（initialTab=moment）+ `MomentEditorCard.tsx`、QuickNote* | 微趣编辑器与数据 |
| 图片创作 | `CreatePage.tsx`（photo）+ `UnifiedImagePostCard.tsx`、`PhotoWorkEditor.tsx`、`ImageEditor` | 图片编辑、裁剪、滤镜等 |
| 视频创作 | `CreatePage.tsx`（video）+ `VideoEditorCard.tsx`、`WorkVideoEditor.tsx` | 视频编辑与封面 |
| 文章创作 | `CreatePage.tsx`（article）+ `ArticleEditorCard.tsx`、article/* | 标题、正文、封面 |
| 草稿/退出/自动保存 | `CreatePage.tsx`（showDraftsList, showExitConfirm, savedDrafts, localStorage, hasContent） | 草稿列表、退出确认、自动保存行为 |

---

## 四、趣聊页（Messages）

| 范围 | 原型源码 | 说明 |
|------|----------|------|
| 趣聊频道 | `MessagePage.tsx` | 一级 Tab：趣聊 / 同好 |
| 二级 Tab | `MessagePage.tsx`（subTabsMap: 趣聊→全部/@我/未读/密信；同好→全部/圈子/好友/群聊） | 胶囊样式、滚动显隐 |
| 会话列表 | `messages/MessagesList.tsx` | 列表项、小趣会话、onAssistantClick |
| 小趣入口（趣聊内） | `MessagesList.tsx`（onAssistantClick）→ `AQuHomePage` | 星火/小趣头像点击打开小趣主页 |
| 联系人/同好 | `messages/ContactsList.tsx` | 同好 Tab 内容；字母分割行样式与发起群聊一致（浅色背景、fgSecondary、AppTypography.sm） |
| 聊天详情 | `ChatPage.tsx` 或 messages 内聊天 UI | 气泡、输入栏、更多面板（与 CHAT_FEATURES 一致）；输入栏无占位符、无 Scan Text、图标与输入框等高、全语义 token |
| 聊天信息 | 设置/群信息页 | 可滚动到底、成员 4 行+「更多成员」、添加成员按钮矩形与头像等高、开关未选浅色/选中蓝底白钮 |
| 发起群聊/选人 | 相关同好列表、选人 Sheet | 字母分割行与同好列表一致；选择框缩小（Transform.scale 0.82）、WidgetStateProperty |
| 消息长按菜单 | 聊天气泡长按：转发、多选、复制、撤回、删除 | 与原型一致 |

---

## 五、我的主页（My Profile）

| 范围 | 原型源码 | 说明 |
|------|----------|------|
| 我的主页 | `MyProfilePage.tsx` | 创作/互动/生活 Tab、设置、小趣入口 |
| 创作子分类 | 全部/图片/视频/文章 | 与作者主页一致 |
| 生活子分类 | 足迹/书影音/味蕾/爱物 | 与作者主页一致 |
| 身份/分身切换 | `PersonaSwitcher.tsx`、`PersonaSwitcherCompact.tsx`、AuthContext | 分身列表、切换、私密分身验证 |
| 网格/列表切换 | `MyProfilePage.tsx` 内 worksViewMode / lifestyleViewMode | 与作者主页一致 |
| 设置入口 | 顶部或侧边设置图标 | 进入 SettingsPage |
| 小趣入口（我的页） | `MyProfilePage.tsx`（小趣管理图标）→ `AQuManagementPage` | 纯图片无蓝底、点击打开小趣管理 |

---

## 六、浏览器（Viewers）及入口

| 范围 | 原型源码 | 说明 |
|------|----------|------|
| 文章浏览器 | `ArticleDetailView.tsx` | 标题、正文、媒体、工具栏、小趣入口、作者吸顶 |
| 文章入口 | 发现/圈子/作者主页中文章卡片点击 | `App.tsx` handlePostClick(post.type===article) → showArticleDetail |
| 图片/媒体浏览器 | `ImmersiveMediaViewer.tsx` + HeaderBar + BottomBar | 全屏、左右点赞/收藏/评论/分享、中心小趣入口、关闭手势 |
| 图片/视频入口 | 发现/圈子/卡片点击非文章帖 | handlePostClick → showViewer、initialMediaIndex |
| 作者浏览器/作者主页 | `AuthorProfile.tsx` | 已按 TSX 迁移；入口：发现/圈子/帖子头像或昵称 |

---

## 七、主页（Profiles）汇总

| 主页 | 原型源码 | 入口 |
|------|----------|------|
| 作者主页 | `AuthorProfile.tsx` | 发现/圈子/帖子中作者、查看器内作者 |
| 圈子主页 | `CirclePageV2.tsx` | 发现/圈子列表中圈子、帖子中圈子 |
| 我的主页 | `MyProfilePage.tsx` | 底部导航「我的」 |
| 小趣主页 | `AQuHomePage.tsx` | 趣聊内小趣入口、悬浮球、工具栏中心（见下） |

---

## 八、小趣（AQu）头像与所有入口

| 入口位置 | 原型源码 | 行为 |
|----------|----------|------|
| 发现页底部悬浮球 | 原型中发现页底部小趣悬浮球组件 | 点击→小趣主页或半屏面板（55–60vh） |
| 沉浸式媒体查看器工具栏中心 | `ImmersiveMediaViewerHeaderBar.tsx` 或 `ImmersiveMediaViewerBottomBar.tsx`（小趣头像/星火） | 点击→小趣相关（与 TSX 一致） |
| 文章详情页工具栏 | `article/UniversalArticleLayout.tsx`（alt="小趣"） | 小趣入口 |
| 趣聊列表小趣会话 | `MessagesList.tsx`（小趣私人助理会话、onAssistantClick） | 点击「助理主页」→ AQuHomePage |
| 我的主页小趣管理入口 | `MyProfilePage.tsx`（小趣图标） | 点击→ AQuManagementPage |
| 设置内小趣 | `SettingsPage.tsx`（若有） | 与小趣管理/数据相关 |
| 小趣头像与视觉 | 原型中小趣头像/星火图标资源与尺寸 | 各入口统一使用同一头像/图标 |

**小趣页面**：
- `AQuHomePage.tsx`：小趣私人助理主页（记忆/待办/技能 Tab、onManageClick→管理）
- `AQuManagementPage.tsx`：小趣管理（数据、删除行为数据等）

---

## 九、评论与帖子操作

| 范围 | 原型源码 | 说明 |
|------|----------|------|
| 评论视图 | `CommentsPage.tsx` | 从帖子/查看器进入、评论列表、发表框 |
| 帖子操作 | `PostActionSheet.tsx`、ActionSheet 配置 | 点赞、收藏、分享、更多；更多→ActionSheet 选项与 Figma 一致 |
| 点赞/收藏状态同步 | `App.tsx`（likedPosts, savedPosts, getPostLikesCount, getPostBookmarksCount） | 卡片与查看器间共享状态 |

---

## 十、路由与叠加顺序（与 App.tsx 一致）

- 欢迎 z-1000 → 主框架 → 作者/圈子 z-100 → 创作页 z-120 → 文章详情 z-130 → 沉浸查看器 z-150 → 评论 z-160 → ActionSheet → 创作入口抽屉 → 小趣（MessagePage 内 z-3000/3100）
- 所有进入方式（作者/圈子/文章/查看器/评论/ActionSheet/创作/小趣）均按原型代码的 state 与回调实现，不得省略或合并。

---

**校验**：每完成一项，以对应 TSX 文件为基准逐屏/逐交互对照，与原型代码不一致即视为未完成。
