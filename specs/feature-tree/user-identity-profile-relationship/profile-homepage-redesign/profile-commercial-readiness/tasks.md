# 个人主页商用就绪 — 任务列表

## 当前交付任务

### 组 1：我的主页数据加载（A1）

- [x] T01: [Provider] 新增 `currentUserIdProvider`：Mock/Remote 均返回 `ChatMockData.currentUserProfileId`，位置 `app_providers.dart`
- [x] T02: [Page] `MyProfilePage` 改为 `ConsumerStatefulWidget`，挂载时 `ref.read(userDataProvider.notifier).loadUser(ref.read(currentUserIdProvider))`，`userId` 使用 `currentUserId`（userData 兜底）
- [x] T03: [测试] `test/ui/user/pages/my_profile_page_test.dart`：mock currentUserIdProvider，验证进入后 displayName 非 "me"、avatar/background 展示

### 组 2：背景高度与拉伸（A2）

- [x] T04: [Widget] `profile_shell.dart`：`expandedHeight` 改为 `MediaQuery.sizeOf(context).height * 0.25 + kToolbarHeight`（或 `AppSpacing` 语义常量）
- [x] T05: [Widget] `profile_shell.dart`：`maxPull` 限制为 `min(screenHeight * 0.25, expandedHeight)`，确保不超过图片底部；保持弹簧阻尼与 250ms 回弹
- [x] T06: [Mock] 确认 `MockUserProfileRepository._defaultProfile` / `getUserProfile` 对 `user_001` 等 ID 返回有效 `backgroundUrl`

### 组 3：统计行与 ProfileStatsPage（A3）

- [x] T07: [Widget] `profile_stats_row.dart`：顺序改为 圈子、关注、粉丝；移除获赞；label 使用 `UITextConstants`
- [x] T08: [Widget] `profile_stats_row.dart`：`stats` 字段顺序与 `onStatTap` 的 type 一一对应（circleCount/followingCount/followerCount）
- [x] T09: [Page] `profile_stats_page.dart`：改为 ConsumerWidget，根据 `type` 调用 `listUserCircles`/`listFollowing`/`listFollowers`，移除硬编码 `_users`/`_mockLikes`
- [x] T10: [Page] `profile_stats_page.dart`：`type=circles` 时展示圈子列表（头像+名称+创作数），点击进 `circle_detail`；`type=following|fans` 时展示用户列表，点击进 `user_profile`
- [x] T11: [Metadata] 若 `listUserCircles` 返回结构需含 `postCount`，在 mock 中补充；Remote 暂可缺省
- [x] T12: [测试] `profile_stats_page_test.dart`：mock Repository，验证圈子/关注/粉丝列表渲染及点击跳转

### 组 4：一级 Tab 精简（A4）

- [x] T13: [Widget] `profile_shell.dart`：`_tabLabels` 改为 `['创作', '圈子', '互动']`，`TabController(length: 3)`
- [x] T14: [Widget] `profile_shell.dart`：移除 `ProfileLifestyleTab`，`TabBarView` 仅 3 个子项
- [x] T15: [Widget] `profile_shell.dart`：移除创作 Tab 的可见性 popup 逻辑（`_openVisibilityPopup`、`_tabBarLayerLink`、`CreationVisibilityPopup` 相关）

### 组 5：创作 Tab 宫格（A5）

- [x] T16: [Widget] `profile_creations_tab.dart`：移除 SubTab 行与可见性 popup 引用
- [x] T17: [Widget] `profile_creations_tab.dart`：改用 `SliverMasonryGrid.count(crossAxisCount: 2)` 替代 `GridView`，按 type 分块展示 微趣、图片、视频、文章
- [x] T18: [Widget] `profile_creations_tab.dart`：每种创作格式支持宫格卡片（复用或抽取 `_DiscoveryPostCard` 风格）
- [x] T19: [测试] `profile_creations_tab_test.dart`：验证无 SubTab、四类分块、MasonryGrid 布局

### 组 6：圈子 Tab 紧凑卡片（A6）

- [x] T20: [Widget] 新增 `circle_compact_card.dart`：头像（或封面缩略图）+ 名称 + 创作数，横向布局
- [x] T21: [Widget] `profile_circles_tab.dart`：用 `CircleCompactCard` 替换 `CircleCard`，传入 `postCount`（mock 从 circle map 取）
- [x] T22: [Mock] `MockUserProfileRepository.listUserCircles` 返回项增加 `postCount` 字段

### 组 7：互动 Tab（A7）

- [x] T23: [Repository] `UserProfileRepository` 新增 `listUserInteractionReceived(userId)`、`listUserInteractionSent(userId)` 方法声明
- [x] T24: [Mock] `MockUserProfileRepository` 实现上述方法，返回 mock 互动列表（userId, nickname, avatarUrl, contentType, targetTitle, createdAt）
- [x] T25: [Widget] `profile_interaction_tab.dart`：子维度改为「收到 | 发出」，根据 `profileNotifier.state.interactionDirection` 调用对应 Repository 方法，渲染列表
- [x] T26: [Widget] `profile_state_provider.dart`：`interactionDirection` 已存在，确保与 UI 联动；列表头像可点击进用户主页

### 组 8：用户名字可设置（A8）

- [x] T27: [Page] `edit_profile_page.dart`：保存成功后调用 `ref.read(userDataProvider.notifier).loadUser(currentUserId)` 或 `ref.invalidate(userDataProvider)`
- [x] T28: [测试] Journey：进入我的主页 → 编辑资料 → 修改昵称 → 保存 → 返回 → 验证主页展示新昵称

### 组 9：收口与验证

- [x] T29: [审计] 执行 `verify_dart_semantic.py`，新增文案使用 `UITextConstants`/l10n
- [x] T30: [测试] `flutter test test/ui/user/ test/cloud/` 全部通过
- [x] T31: [验证] `make build`、`make gate` 或 `make gate-full` 通过

---

## 搁置任务（带规划）

- [ ] **互动 API 云侧实现**：`listUserInteractionReceived`/`listUserInteractionSent` 的 HTTP 路由与 Handler（重启条件：user-service 或 interaction-service 进入 dev 阶段）
- [ ] **currentUserId 从 auth 获取**：`currentUserIdProvider` 改为 `ref.watch(authRepositoryProvider).currentUserId`（重启条件：auth 登录态就绪）
- [ ] **metadata 互动契约**：在 `service.yaml` 声明互动 API 路由，经 codegen 生成（可与云侧实现同步进行）

---

## 未来演进任务

- [ ] **E1**：圈子 `postCount` 若由云端计算，补充 `fields.yaml` / DTO
- [ ] **E2**：创作 Tab 与发现页共享 MasonryGrid 组件，抽取通用 `PostGridCard`
- [ ] **E3**：ProfileStatsPage 列表项支持分页加载（cursor/limit）
