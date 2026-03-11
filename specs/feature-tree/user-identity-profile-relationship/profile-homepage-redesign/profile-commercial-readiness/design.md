# 个人主页商用就绪 — 设计方案

## 设计动因

PRD 识别的 8 条验收项（A1~A8）需在现有 ProfileShell 基础上进行增量改造，不推翻已有架构。核心矛盾：我的主页从未加载 userData、统计页与 Repository 脱节、Tab 与子内容需按商用规格调整。

## 上游输入评审

| 维度 | 评审结论 |
|------|---------|
| spec.md | F1~F8 功能范围清晰，O1~O4 边界明确 |
| acceptance.yaml | A1~A8 覆盖全部验收点，T1~T4 映射完整 |
| 阻断项 | **无**。`UserProfileRepository` 已有 `listFollowing/listFollowers/listUserCircles/getUserStats`；互动接口需新增；`currentUserId` Mock 可先用 `ChatMockData.currentUserProfileId` |

## 对标输入分析

### 内部对标

| 组件 | 对标点 | 复用方式 |
|------|--------|---------|
| `circles_page.dart` | `SliverMasonryGrid.count` 瀑布流宫格 | 创作 Tab 改用 `SliverMasonryGrid` 实现不等高布局 |
| `ProfileShell` | TabController、NestedScrollView、弹簧阻尼 | 保留架构，调整 Tab 数量、背景高度、统计行 |
| `UserProfileRepository` | listFollowing/listFollowers/listUserCircles | ProfileStatsPage 对接，去掉硬编码 |
| `CircleCard` | 当前 16:9 大图 | 新增 `CircleCompactCard`（头像+名称+创作数） |

---

## 方案对比

### 方案 A：在 ProfileShell 内注入 loadUser（推荐）

**核心思路**：`ProfileShell` 在 `mode == mine` 且 `userData == null` 时，于 `initState`/`didChangeDependencies` 调用 `userDataProvider.notifier.loadUser(currentUserId)`。`currentUserId` 由 Provider 提供：Mock 用 `'user_001'`，Remote 用 auth 或占位。

**优点**：
- 改动集中，不新建页面
- 与现有 `userDataProvider` 兼容
- 进入我的主页即触发加载，displayName/background 自动更新

**缺点**：
- ProfileShell 承担「我的主页初始化」职责，略增耦合

### 方案 B：MyProfilePage 内触发 loadUser

**核心思路**：`MyProfilePage` 使用 `ConsumerStatefulWidget`，在 `initState` 或 `ref.listen` 中调用 `loadUser(currentUserId)`，再传 `userId` 给 ProfileShell。

**优点**：
- 职责清晰：入口页负责数据准备
- ProfileShell 保持「纯展示 + userId」

**缺点**：
- 需确定 `currentUserId` 来源；若 MyProfilePage 先于 auth 构建，可能无 ID

### 选型决策

**选定方案 B（MyProfilePage 触发）**，并新增 `currentUserIdProvider`：
- Mock：`currentUserIdProvider` 返回 `ChatMockData.currentUserProfileId`（`'user_001'`）
- Remote：返回 `authRepository.currentUserId` 或占位（auth 未就绪时可复用 mock ID）
- `MyProfilePage` 挂载时 `ref.read(userDataProvider.notifier).loadUser(currentUserId)`，再将 `userId` 传 ProfileShell

**理由**：入口页负责「当前用户」语义，ProfileShell 保持通用；`currentUserIdProvider` 可随 auth 演进扩展。

---

## 关键设计决策

### KD1: currentUserIdProvider

```dart
// lib/core/providers/app_providers.dart
final currentUserIdProvider = Provider<String>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    // TODO: auth 就绪后改为 ref.watch(authRepositoryProvider).currentUserId
    return ChatMockData.currentUserProfileId;
  }
  return ChatMockData.currentUserProfileId;
});
```

Mock/Remote 过渡期均返回 `'user_001'`，保证我的主页可验证。auth 就绪后替换为真实 currentUserId。

### KD2: 我的主页加载流程

```
MyProfilePage.build()
  → currentUserId = ref.watch(currentUserIdProvider)
  → ref.read(userDataProvider.notifier).loadUser(currentUserId)  // 若 userData 为 null 或 userId 不匹配则加载
  → userId = userData?.id ?? currentUserId
  → ProfileShell(mode: mine, userId: userId, initial*: userData)
```

为避免重复加载，`UserDataNotifier.loadUser` 可在 `state?.id == userId` 时短路返回。

### KD3: 背景高度与拉伸

| 参数 | 当前 | 目标 |
|------|------|------|
| 默认高度 | `expandedHeight: 420` 硬编码 | `MediaQuery.sizeOf(context).height * 0.25 + kToolbarHeight` 或语义常量 |
| 最大拉伸 | `maxPull = screenHeight * 0.25` | `maxPull = min(screenHeight * 0.25, imageBottomOffset)`，即不超过图片底部 |
| 回弹 | 250ms | 保持 250ms，满足 ≤300ms |

实现：背景区域使用 `LayoutBuilder` 获取高度，`maxPull` 取 `min(screenHeight * 0.25, expandedHeight)`，避免拉伸超出可视图片底部。

### KD4: 统计行与 ProfileStatsPage

| 项目 | 当前 | 目标 |
|------|------|------|
| 顺序 | 关注、圈子、粉丝、获赞 | 圈子、关注、粉丝（无获赞） |
| 数据源 | 硬编码 `_users`、`_mockLikes` | `UserProfileRepository.listFollowing/listFollowers/listUserCircles` |
| 圈子 type | 无，点击 fallback 到默认 | 新增 `type=circles`，展示圈子列表 |
| 列表项点击 | 空 `onTap` | 用户卡片 → `context.push(userProfile)`；圈子卡片 → `context.push(circleDetail)` |

`ProfileStatsRow` 调整 items 顺序并移除 likeCount；`onStatTap` 传 `circles` 时路由到 `ProfileStatsPage(type: 'circles')`。  
`ProfileStatsPage` 改为 ConsumerWidget，`ref.watch(userProfileRepositoryProvider)`，根据 `type` 调用 `listFollowing`/`listFollowers`/`listUserCircles`，渲染对应卡片并支持点击跳转。

### KD5: 一级 Tab 精简

| 项目 | 当前 | 目标 |
|------|------|------|
| Tab 数量 | 4（创作、圈子、互动、生活） | 3（创作、圈子、互动） |
| TabController | `length: 4` | `length: 3` |
| 创作 Tab 点击 | 弹出可见性 popup | 无 popup，直接展示宫格 |

移除 `ProfileLifestyleTab` 的引用；删除生活 Tab 的 `Tab` 与 `TabBarView` 子项；移除创作 Tab 的可见性 popup 逻辑（`_openVisibilityPopup`、`_tabBarLayerLink` 等可删除或简化）。

### KD6: 创作 Tab 宫格布局

| 项目 | 当前 | 目标 |
|------|------|------|
| SubTab | 全部/微趣/图片/视频/文字 | 无 SubTab |
| 可见性 | 全部/公开/私密 popup | 无 |
| 布局 | `GridView` + `childAspectRatio: 0.8` 等高 | `SliverMasonryGrid.count` 不等高 |
| 分块 | 按 SubTab 过滤 | 按类型分块展示：微趣 | 图片 | 视频 | 文章 |

复用 `circles_page` 的 `SliverMasonryGrid.count(crossAxisCount: 2)`，按 `PostBaseDto.type` 分组展示四类内容。若 `listUserPosts` 已按 type 返回，可直接用；否则端侧分组过滤。

### KD7: 圈子 Tab 紧凑卡片

| 项目 | 当前 | 目标 |
|------|------|------|
| 卡片 | `CircleCard` 16:9 大图 | 头像 + 名称 + 创作数 |
| 数据 | `circle['coverUrl'], circle['name']` | 新增 `postCount` 或 `creationCount` |

新增 `CircleCompactCard`：`Row` 布局，左侧 `CircleAvatar`（或方形缩略图），右侧 `Column(name, postCount)`。  
`listUserCircles` 的 mock 需包含 `postCount`；若 metadata 未定义，可先由 mock 端侧追加。

### KD8: 互动 Tab 数据源

| 项目 | 当前 | 目标 |
|------|------|------|
| 数据 | 无，空态 | Repository 接口 + Mock |
| 子维度 | 赞、评论 | 收到、发出 |

接口设计（二选一）：

- **A**：`listUserInteractionReceived(userId)`、`listUserInteractionSent(userId)` 分别返回收到的赞/评论、发出的赞/评论列表。
- **B**：`listUserInteractions(userId, {direction: 'received'|'sent'})` 单接口 + 参数。

选 **A**，与「收到/发出」语义一一对应。  
Mock：返回 `[{userId, nickname, avatarUrl, contentType, targetTitle, createdAt}]` 等字段。  
metadata：在 `user/user_profile/service.yaml` 或新建 `interaction` 相关 service 声明路由；本 Story 可先仅端侧 Mock，契约占位。

### KD9: 用户名字可设置

编辑资料页已存在，`updateProfile` 会写回云端/Mock。关键：编辑成功后需刷新 `userDataProvider`，以便返回我的主页时展示新昵称。  
实现：`EditProfilePage` 保存成功后调用 `ref.read(userDataProvider.notifier).loadUser(currentUserId)`，或使用 `invalidate(userDataProvider)` 触发重载。

---

## TDD / ATDD 策略

| 验收项 | 测试层 | 策略 |
|--------|--------|------|
| A1 | T2, T3 | Widget：mock currentUserIdProvider，验证 MyProfilePage 进入后 displayName 非 "me"；Journey：打开我的主页 → 检查昵称与头像 |
| A2 | T2, T4 | Widget：mock 背景 URL，验证默认高度 ≈ 1/4；T4 真机验证拉伸与回弹 |
| A3 | T1, T2, T3 | 契约：Repository 方法签名；Widget：ProfileStatsPage 渲染圈子/关注/粉丝列表；Journey：点击统计 → 列表与跳转 |
| A4 | T1, T2 | 契约：profile_tabs 含 3 项；Widget：TabBar 仅 3 个 Tab |
| A5 | T2 | Widget：创作 Tab 无 SubTab，使用 MasonryGrid，四类分块 |
| A6 | T2 | Widget：圈子 Tab 使用 CircleCompactCard |
| A7 | T1, T2 | 契约：listUserInteraction* 接口；Widget：互动 Tab 收到/发出切换与列表 |
| A8 | T2, T3 | Widget：编辑后 userData 更新；Journey：编辑昵称 → 返回 → 验证展示 |

---

## Task 与测试层映射

| Task 组 | 验收项 | 测试层 | 说明 |
|---------|--------|--------|------|
| T01–T03 | A1 | T2, T3 | currentUserIdProvider + MyProfilePage loadUser |
| T04–T06 | A2 | T2, T4 | 背景高度语义化、拉伸边界、回弹 |
| T07–T12 | A3 | T1, T2, T3 | 统计行顺序、ProfileStatsPage 对接、circles 列表 |
| T13–T15 | A4 | T1, T2 | 去掉生活 Tab、TabController 改为 3 |
| T16–T19 | A5 | T2 | 创作 Tab 宫格、去 SubTab、MasonryGrid |
| T20–T22 | A6 | T2 | CircleCompactCard、圈子 Tab |
| T23–T26 | A7 | T1, T2 | 互动接口 + Mock、互动 Tab |
| T27–T28 | A8 | T2, T3 | 编辑后刷新 userData |
| T29–T31 | 全部 | T1–T4 | 语义审计、测试回填、gate |

---

## 未来演进

- **E1**：auth 就绪后，`currentUserIdProvider` 改为从 `authRepository` 读取。
- **E2**：互动 API 云侧实现后，Remote 对接 `listUserInteractionReceived/Sent`。
- **E3**：圈子 `postCount` 若云端计算，metadata 补充字段后 codegen。
