# 路由与用户旅程设计

本文档基于对趣我圈2026 原型 (`App.tsx`、`MessagePage.tsx`、`CreateEntrySheet.tsx` 等) 与 quwoquan_app 现有路由 (`app_router.dart`、`home_page.dart`、`bottom_navigation.dart`) 的详细分析，定义 Flutter 迁移的目标路由架构、叠加层层级与关键用户旅程。

---

## 1. 原型路由模型概览

### 1.1 趣我圈2026 的导航结构

原型采用**状态驱动 + 全屏/半屏叠加**，无 URL 路由：

| 层级 | 内容 | 实现方式 |
|------|------|----------|
| 根层 | 欢迎页 | `showWelcome` → `WelcomeScreen` (z-1000) |
| 主框架 | 五大频道 | `currentPage` → Home / CirclesFeed / MessagePage / MyProfilePage |
| 底部导航 | 5 项 | 发现、圈子、创作、趣聊、我的；创作为 `isModalTrigger` |
| 叠加层 | 作者/圈子/文章/查看器/评论/ActionSheet/创作 | 布尔状态 + AnimatePresence |

### 1.2 五大频道与底部导航映射

| 底部导航项 | 原型 `navItems` id | 对应页面组件 | 行为 |
|------------|-------------------|--------------|------|
| 发现 | home | Home → DiscoveryFeed | 切换 `currentPage` |
| 圈子 | circles | CirclesFeed | 同上 |
| 创作 | create | — | `isModalTrigger`: 不切换页，打开创作入口/编辑器 |
| 趣聊 | messages | MessagePage | 切换 `currentPage` |
| 我的 | profile | MyProfilePage | 切换 `currentPage` |

**重要**：创作入口点击时，原型当前实现为**直接打开 CreatePage** (`setShowEditor(true)`, `setEditorMode('moment')`)，**未**打开 CreateEntrySheet。但设计规范与 create-flow spec 要求先展示创作入口抽屉（微趣/作品 6 入口），再进入对应编辑器。迁移时需修正为该流程。

### 1.3 Flutter 现状与目标差异

| 项目 | 当前 quwoquan_app | 目标（与原型/设计对齐） |
|------|-------------------|-------------------------|
| 底部导航 | 首页、发现、创建、聊天、我的 (5 项) | 发现、圈子、创作、趣聊、我的 (5 项) |
| 首页 | HomePage = 发现内容 (following/recommended/images/video/articles/moments) | 发现频道 = DiscoveryFeed（推荐 + 图片/视频/文章） |
| 路由 | go_router: `/`, `/my-profile`, `/user/:username`, `/media-viewer/:category/:index`, `/video-viewer/:index` | 主框架 + 叠加层（Overlay/Route），需支持状态传递 |
| 圈子频道 | 无 | 需新增 CirclesFeed |
| 趣聊频道 | 无 | 需新增 MessagePage |
| 创作 | 点击无行为 | 先打开 CreateEntrySheet，再进入 CreatePage |

---

## 2. 叠加层层级 (Z-Index) 规范

基于 App.tsx 与 MessagePage 的 z-index 使用，统一约定 Flutter 迁移的层级（数值越大越靠前）：

| 层级值 | 用途 | 原型对应 | 动效 |
|--------|------|----------|------|
| 0 | 主框架（底部导航 + 当前频道） | 主容器 | — |
| 50 | 底部导航栏 | `z-50` | 随滚动隐藏时 `y` 动画 |
| 100 | 作者主页、圈子主页 | `z-[100]` | 右滑入 `x: 100% → 0` |
| 120 | 创作页（CreatePage） | `z-[120]` | 底部滑入 `y: 100% → 0` |
| 130 | 文章详情 | `z-[130]` | 右滑入 |
| 150 | 沉浸式媒体查看器 | `z-[150]` | 渐显 `opacity` |
| 160 | 评论页 | `z-[160]` | 底部滑入 |
| 170 | 创作入口抽屉 (CreateEntrySheet) | 原型未使用，建议新增 | 底部滑入，maxHeight 67vh |
| 180 | PostActionSheet | BaseActionSheet 内部 z-[9999]，建议统一 | 底部滑入 |
| 1000 | 欢迎页 | `z-[1000]` | 渐隐 + 上移 |
| 3000 | 小趣首页 (AQuHomePage，在 MessagePage 内) | `z-[3000]` | 右滑入 |
| 3100 | 小趣管理页 (AQuManagementPage) | `z-[3100]` | 右滑入 |

**说明**：

- 作者/圈子/文章/评论为全屏叠加，右滑或底部滑入；查看器为全屏透明背景。
- 创作入口抽屉与 ActionSheet 为半屏，需在文章/评论/查看器之上，故取值 170、180。
- 小趣页面在 MessagePage 内嵌套，需高于主 App 所有叠加，故使用 3000+。

---

## 3. 路由架构建议（Flutter）

### 3.1 总体策略

采用 **ShellRoute + 叠加 Route/Overlay** 混合：

1. **ShellRoute**：包裹底部导航 + 当前频道页，保持主框架不重建。
2. **子路由**：`/`（发现）、`/circles`、`/chat`、`/profile` 对应四个频道；创作不占路由。
3. **叠加层**：作者、圈子、文章、查看器、评论、ActionSheet、创作入口、创作页，通过 `context.push()` 或 `Overlay` + 状态驱动实现。

### 3.2 建议路由表

| 路径 | 说明 | 实现方式 |
|------|------|----------|
| `/` | 发现频道 | ShellRoute 子路由 |
| `/circles` | 圈子频道 | ShellRoute 子路由 |
| `/chat` | 趣聊频道 | ShellRoute 子路由 |
| `/profile` | 我的主页 | ShellRoute 子路由 |
| `/user/:username` | 作者主页 | 全屏 push，右滑返回 |
| `/circle/:circleId` | 圈子主页 | 全屏 push，右滑返回 |
| `/post/:postId` (或 query) | 文章详情 | 全屏 push，右滑返回 |
| `/media-viewer` (query: postId, index) | 沉浸查看器 | 全屏 push |
| `/comments` (query: postId) | 评论页 | 全屏 push |

**创作流程**：不占路由，通过 Overlay 或 `showModalBottomSheet` + 自定义全屏页实现：点击创作 → 显示 CreateEntrySheet (Overlay/Modal) → 选择类型后 → 显示 CreatePage (全屏 Overlay 或 push 到临时 Route)。

### 3.3 状态传递

- **选中的 Post**：通过 `GoRouterState.extra` 或 Provider 传递。
- **initialMediaIndex**：查看器需知初始索引，通过 `extra` 或 query 传递。
- **editorMode**：创作页 initialTab，通过 CreateEntrySheet 回调设置。

---

## 4. 关键用户旅程

### 4.1 欢迎 → 主框架

```
[欢迎页] --onFinish--> [主框架 + 底部导航]
  - 欢迎页 z-1000，退出时 opacity + y 动画
  - 主框架渲染发现频道（currentPage=home）
```

### 4.2 底部导航切换

```
[发现] <--> [圈子] <--> [趣聊] <--> [我的]
  - 点击切换 currentPage，内容区切换对应页面
  - 创作：不切换 currentPage，打开创作入口抽屉（目标）或直接创作页（原型现状）
```

### 4.3 发现 → 作者/圈子/帖子

```
[发现] --点击作者--> [作者主页] (叠加 z-100)
[发现] --点击圈子--> [圈子主页] (叠加 z-100)
[发现] --点击图片/视频帖--> [沉浸查看器] (叠加 z-150)
[发现] --点击文章帖--> [文章详情] (叠加 z-130)
```

作者/圈子/文章 均由右向左滑入；查看器为渐显。

### 4.4 查看器 → 评论 / ActionSheet / 作者

```
[查看器] --点击评论--> [评论页] (叠加 z-160)
[查看器] --点击更多--> [PostActionSheet] (叠加 z-180)
[查看器] --点击作者--> [作者主页] (叠加 z-100)
```

评论与 ActionSheet 从底部滑入；作者主页右滑入。需注意：从查看器打开作者时，查看器仍在底层，作者叠加在上。

### 4.5 创作流程（目标，按 spec）

```
[任意频道] --点击创作--> [CreateEntrySheet] (叠加 z-170)
  - 展示微趣（照片/文字/视频）与作品（图片/文章/视频）六入口
[CreateEntrySheet] --选择某一入口--> [CreatePage] (叠加 z-120)
  - 关闭抽屉，全屏展示创作页，initialTab 对应所选类型
[CreatePage] --关闭--> 回到原频道
```

### 4.6 趣聊 → 小趣

```
[趣聊 MessagePage] --点击小趣入口--> [AQuHomePage] (叠加 z-3000)
[AQuHomePage] --点击管理--> [AQuManagementPage] (叠加 z-3100)
[AQuManagementPage] --返回--> [AQuHomePage]
[AQuHomePage] --返回--> [MessagePage]
```

小趣为 MessagePage 内部叠加，不经过全局路由。

### 4.7 底部导航显隐

原型中底部导航在以下情况隐藏：

- `showWelcome`、`showAuthorProfile`、`showCircleProfile`、`showEditor`、`showViewer`、`showComments`、`showArticleDetail` 任一为 true 时隐藏。
- 视频沉浸模式下 `isBottomNavHidden` 为 true 时，通过 `y` 动画下移隐藏。

迁移时需在 Flutter 中复现相同逻辑。

---

## 5. 趣聊频道内部结构（MessagePage）

### 5.1 一级 Tab

| Tab 名称（原型） | 含义 | 对应 spec |
|------------------|------|-----------|
| 趣聊 | 消息/会话 | 消息 |
| 同好 | 通讯录/联系人 | 通讯 |

chat spec 中称为「消息」与「通讯」，与原型「趣聊」「同好」为同一层级，仅命名差异，迁移时与 Figma 保持一致。

### 5.2 二级 Tab

| 一级 Tab | 二级 Tab（原型） |
|----------|------------------|
| 趣聊 | 全部、@我、未读、密信 |
| 同好 | 全部、圈子、好友、群聊 |

### 5.3 小趣入口

- 消息列表内 `onAssistantClick` → `setShowAQuHome(true)` 打开 AQuHomePage。
- 小趣首页有管理入口 → AQuManagementPage。

---

## 6. 实现检查清单

- [ ] 底部导航顺序与文案：发现、圈子、创作、趣聊、我的
- [ ] 创作点击 → 先 CreateEntrySheet，再 CreatePage（与 spec 一致）
- [ ] 作者/圈子/文章/查看器/评论/ActionSheet 的叠加顺序与动效符合上述 z-index 表
- [ ] 欢迎页、底部导航显隐逻辑与原型一致
- [ ] 趣聊一级 Tab（趣聊/同好）、二级 Tab 与列表行为与 MessagePage 一致
- [ ] 小趣入口、AQuHomePage、AQuManagementPage 在 MessagePage 内正确叠加
- [ ] 所有路由与叠加使用语义 token，无硬编码

---

## 7. 参考代码位置

| 内容 | 原型路径 | Flutter 路径 |
|------|----------|--------------|
| 主 App 与叠加 | `趣我圈2026/src/App.tsx` | `lib/app/`, `lib/main.dart` |
| 路由配置 | — | `lib/app/navigation/app_router.dart` |
| 底部导航 | App.tsx 内联 | `lib/components/bottom_navigation.dart` |
| 首页/发现 | `Home.tsx` → `DiscoveryFeed.tsx` | `lib/features/home/pages/home_page.dart` |
| 创作入口 | `CreateEntrySheet.tsx` | 待实现 |
| 趣聊 | `MessagePage.tsx` | 待实现 |
| 小趣 | `AQuHomePage`, `AQuManagementPage` | 待实现 |
