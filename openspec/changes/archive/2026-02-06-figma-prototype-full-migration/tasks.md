# Figma 原型全量迁移 - 任务列表（1:1 复制）

**准则**：严格按 **趣我圈2026/src** 对应 TSX 源码 **1:1 复制**，不得省略、改写或凭文档实现。布局、样式、数据结构、交互、路由须与原型代码一致。**每个页面的 mock 数据也须 1:1 从对应 TSX 复制**（条数、字段与原型一致），统一放在 `lib/data/mock/prototype_mock_data.dart` 并注明来源 TSX。完整映射见 [MIGRATION_SCOPE.md](./MIGRATION_SCOPE.md)。

---

## 一、发现页（1:1 复制 Home.tsx → DiscoveryFeed.tsx）

- [x] **D1** 发现页 Tab：1:1 复制 `DiscoveryFeed.tsx` 的 `CATEGORIES`（id: moment/photo/video/article，label: **微趣/美图/视频/文章**），顶部胶囊样式（rounded-full、px4 py1、text-[13px] font-black）、视频模式下选中样式（bg-white/20 text-white）
- [x] **D2** 发现页 Header：1:1 复制布局（左侧占位 w-8、中间 Tab 胶囊组、右侧搜索按钮）；视频模式时 header 渐变（from-black/60 to-transparent）、非视频时白/暗底+backdrop-blur+border-b；视频模式下点击切换 UI 显隐时调用 onTheaterModeChange
- [x] **D3** 发现页容器：视频模式整页 bg-black，非视频 bg-white/dark:bg-neutral-950；内容区 flex-1 overflow-hidden，AnimatePresence mode="wait" 切换
- [x] **D4** 微趣流：1:1 复制 `DiscoveryFeed.tsx` 中 activeType===moment 的 `discoveryData` 四条数据，用 `RecommendFeed` 等价渲染；卡片 1:1 复制 `MomentPost.tsx`（头像、timeAgo、source、content、转发引用 quotedPost、媒体 media、点赞/评论/分享）
- [x] **D5** 美图流：1:1 复制 photo 的 `discoveryData`，用 `MasonryLayoutEngine` 等价（maxColumns=2, gap=8, minColumnWidth=140），每项用 `DiscoveryItem.tsx` 等价（缩略图、多图数字角标、视频 Play 角标）
- [x] **D6** 视频流：1:1 复制 `VideoImmersionView.tsx` 接入，onBack 回切到 moment，onToggleUI 控制 header 显隐并 onTheaterModeChange
- [x] **D7** 文章流：1:1 复制 activeType===article 的 `discoveryData`，用 `RecommendFeed` + `ArticleCard.tsx` 等价
- [x] **D8** 发现页底部小趣悬浮球及点击行为与原型一致

---

## 二、圈子页（1:1 复制 CirclesFeed.tsx + CirclePageV2.tsx）

- [x] **C1** 圈子频道列表 1:1 复制 CirclesFeed（DiscoveryView：CATEGORY_CONFIG 维度、RecommendedCirclesSection、ActivityCard、SubCategoryBar、瀑布流、创建圈子 FAB）
- [x] **C2** 圈子主页 1:1 复制 CirclePageV2（initialRole: owner|admin|member|visitor），角色差异：owner/admin 显示「编辑圈子」「管理中心」；member 显示已加入/关注；visitor 显示加入/关注、准入规则、joinStatus
- [x] **C3** 圈子主页 3-Tab 创作/互动/生活、子分类、网格/列表、统计列表弹层、EditCircleModal/CircleManagementCenter 占位 1:1 复制

---

## 三、创作流程（1:1 复制 CreateEntrySheet.tsx + CreatePage.tsx）

- [x] **CR1** 创作入口：点击底部「创作」直接进入创作全页（/create），默认发微趣；入口抽屉 CreateEntrySheet 可选保留供其他场景，六入口 1:1 复制（微趣 照片/文字/视频、作品 图片/文章/视频）
- [x] **CR2** 创作页为全页形态，四 Tab **微趣/美图/视频/文章**（文案与图一一致），默认 Tab 为微趣、标题为「发微趣」；草稿箱、退出确认、10 秒自动保存、hasContent 判断 1:1 复制 CreatePage
- [x] **CR3** 微趣/美图/视频/文章各编辑器 1:1 复制 MomentEditorCard、PhotoWorkEditor、VideoEditorCard、ArticleEditorCard 等（卡片结构+完整字段），含图片编辑（/create/edit-image）、所在位置、提醒谁看、谁可以看（默认公开）等全部操作

---

## 四、趣聊（1:1 复制 MessagePage、MessagesList、ContactsList）

- [x] **M1** 一级 Tab 趣聊/同好、二级 Tab 与 subTabsMap 一致（全部/@我/未读/密信、全部/圈子/好友/群聊）、滚动显隐二级 Tab、小趣会话置顶、onAssistantClick→/xiaoqu
- [x] **M2** 聊天详情、消息气泡、输入栏、长按菜单 1:1 复制（ChatDetailPage 已接入 /chat/:id）
- [x] **M3** 聊天详情/聊天信息/发起群聊 UI 细节与语义 token 对齐（见 specs/chat/spec.md「实现细节与 UI 规范」）

---

## 五、我的主页（1:1 复制 MyProfilePage.tsx）

- [x] **P1** 创作/互动/生活 Tab、子分类、设置入口（与 AuthorProfile 结构一致，MyProfilePage 已实现）
- [x] **P2** 身份/分身切换 PersonaSwitcher、小趣管理入口图标 1:1 复制（主账号▼+管理分身、设置/小趣入口已接入）

---

## 六、作者主页与圈子主页

- [x] **A1** 作者主页已按 AuthorProfile.tsx 迁移
- [x] **A2** 圈子主页见 C2/C3（已实现）

---

## 七、小趣（1:1 复制 AQuHomePage、AQuManagementPage 及各入口）

- [x] **X1** 趣聊内小趣会话置顶、点击→/xiaoqu（AQuHomePage 占位）；发现页悬浮球已有
- [x] **X2** AQuHomePage（记忆/待办/技能）、AQuManagementPage 1:1 复制（已接入 /xiaoqu、/xiaoqu/management）

---

## 八、浏览器与评论（1:1 复制）

- [x] **V1** ImmersiveMediaViewer（小趣入口）、ArticleDetailView、CommentsPage（模态）、PostActionSheet 及点赞/收藏同步 1:1 复制

---

## 九、联调

- [x] **L1** 关键路径与原型一致；无硬编码；以 TSX 逐页对照无折扣（全量路由与点击已串联）
