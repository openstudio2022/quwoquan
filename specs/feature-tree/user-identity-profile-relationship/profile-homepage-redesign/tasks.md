# 个人主页全面重构 — 任务列表

## 当前交付任务

### S7: 目录迁移（先行，消除技术债务）

- [ ] T01: [迁移] 将 `lib/features/profile/pages/edit_profile_page.dart` 移动到 `lib/ui/user/pages/edit_profile_page.dart`
- [ ] T02: [迁移] 将 `lib/features/profile/pages/persona_management_page.dart` 移动到 `lib/ui/user/pages/persona_management_page.dart`
- [ ] T03: [迁移] 将 `lib/features/profile/pages/resonance_page.dart` 移动到 `lib/ui/user/pages/resonance_page.dart`
- [ ] T04: [迁移] 将 `lib/features/profile/pages/profile_stats_page.dart` 移动到 `lib/ui/user/pages/profile_stats_page.dart`
- [ ] T05: [路由] 更新 `app_router.dart`：`/profile/edit`、`/profile/personas`、`/profile/resonance`、`/profile/stats` 指向新路径
- [ ] T06: [清理] 更新所有 import 引用（全局搜索 `features/profile`）
- [ ] T07: [清理] 删除 `lib/features/profile/` 目录
- [ ] T08: [验证] `flutter analyze` 零新增错误

### S1: metadata + codegen 基线

- [ ] T09: [metadata] 在 `contracts/metadata/user/user_profile/fields.yaml` 新增 `circleCount: int` 和 `likeCount: int` 字段
- [ ] T10: [metadata] 在 `contracts/metadata/content/post/ui_config.yaml` 新增 `profile_tabs` 配置节：
  ```yaml
  profile_tabs:
    - id: creations
      label_key: profile_tab_creations
      order: 0
      sub_tabs:
        - id: all
          label_key: creation_sub_all
          content_type: null
          order: 0
        - id: micro
          label_key: creation_sub_micro
          content_type: micro
          order: 1
        - id: image
          label_key: creation_sub_image
          content_type: image
          order: 2
        - id: video
          label_key: creation_sub_video
          content_type: video
          order: 3
        - id: article
          label_key: creation_sub_article
          content_type: article
          order: 4
    - id: circles
      label_key: profile_tab_circles
      order: 1
    - id: interaction
      label_key: profile_tab_interaction
      order: 2
    - id: lifestyle
      label_key: profile_tab_lifestyle
      order: 3
  ```
- [ ] T11: [metadata] 在 `contracts/metadata/social/circle/service.yaml` 新增 API 声明：
  ```yaml
  - method: GET
    path: /v1/user/{userId}/circles
    operation: ListUserCircles
    description: 查询用户已加入的圈子列表
    params:
      - name: userId
        in: path
        required: true
      - name: limit
        in: query
        default: 50
    response: CircleSummaryList
  ```
- [ ] T12: [codegen] 执行 `make verify-metadata && make codegen && make codegen-app`

### S2: ProfileShell 核心框架

- [ ] T13: [model] 创建 `lib/ui/user/models/profile_mode.dart`：`ProfileMode { mine, other }` 枚举
- [ ] T14: [model] 创建 `lib/ui/user/models/profile_tab.dart`：`ProfileTab / CreationSubTab / CreationVisibility` 枚举
- [ ] T15: [provider] 创建 `lib/ui/user/providers/profile_state_provider.dart`：ProfileState + ProfileNotifier（family by userId）
- [ ] T16: [widget] 创建 `lib/ui/user/widgets/profile_header.dart`：背景图拉伸 + 头像 + 用户名 + bio
- [ ] T17: [widget] 创建 `lib/ui/user/widgets/profile_stats_row.dart`：统计行（关注/圈子/粉丝/获赞），数字可点击跳转
- [ ] T18: [widget] 创建 `lib/ui/user/widgets/profile_action_bar.dart`：mine=[编辑资料, 分身管理] / other=[关注, 消息]
- [ ] T19: [widget] 创建 `lib/ui/user/widgets/profile_resonance_card.dart`：交集/共鸣卡片
- [ ] T20: [widget] 创建 `lib/ui/user/widgets/profile_shell.dart`：NestedScrollView + SliverAppBar + SliverPersistentHeader + TabBarView 主框架
- [ ] T21: [page] 重写 `lib/ui/user/pages/my_profile_page.dart`：入口 Widget，构造 `ProfileShell(mode: .mine, userId: currentUserId)`
- [ ] T22: [page] 重写 `lib/ui/user/pages/other_profile_page.dart`（替换 `author_profile_page.dart`）：入口 Widget，构造 `ProfileShell(mode: .other, userId: widget.userId)`
- [ ] T23: [路由] 更新 `app_router.dart`：`/profile` → `MyProfilePage`（新）、`/user/:username` → `OtherProfilePage`（新）

### S6: 一级 Tab 导航

- [ ] T24: [widget] 在 `profile_shell.dart` 中集成 `CenteredScrollableTabBar`（一级 Tab [创作|圈子|互动|生活]）
- [ ] T25: [交互] 实现 Tab 切换联动 `TabBarView`，默认选中「创作」
- [ ] T26: [交互] 实现点击已选中「创作」Tab 弹出可见性过滤 popup（`creation_visibility_popup.dart`）

### S3: 创作 Tab

- [ ] T27: [widget] 创建 `lib/ui/user/widgets/profile_creations_tab.dart`：二级 SubTab [全部|微趣|图片|视频|文字]
- [ ] T28: [widget] 创建 `lib/ui/user/widgets/creation_visibility_popup.dart`：可见性过滤 popup
- [ ] T29: [provider] 创建 `lib/ui/user/providers/profile_creations_provider.dart`：按 SubTab + Visibility 过滤查询
- [ ] T30: [交互] SubTab 切换时重新查询对应 contentType 的创作列表
- [ ] T31: [交互] Visibility 过滤选中后：Tab 旁显示蓝色圆点指示器；私密作品封面叠加锁标
- [ ] T32: [Repository] `UserProfileRepository` 扩展 `listUserPosts` 参数：新增 `contentType` 和 `visibility` 可选过滤

### S4: 圈子 Tab

- [ ] T33: [widget] 创建 `lib/ui/user/widgets/profile_circles_tab.dart`：垂直列表
- [ ] T34: [widget] 创建 `lib/ui/user/widgets/circle_card.dart`：封面 (16:9) + 圈子名
- [ ] T35: [Repository] `UserProfileRepository` 新增 `listUserCircles(userId)` + Mock 实现
- [ ] T36: [交互] 点击圈子卡片 → `context.push('/circle/${circleId}')`
- [ ] T37: [空态] mine: 「还没加入圈子」+ 探索按钮 / other: 「Ta 还没加入圈子」

### S5: 互动 Tab + 生活 Tab

- [ ] T38: [widget] 创建 `lib/ui/user/widgets/profile_interaction_tab.dart`：子维度 [赞|评论] + mine 方向切换 [收到|发出]
- [ ] T39: [widget] 创建 `lib/ui/user/widgets/profile_lifestyle_tab.dart`：子分类 [足迹|书影音|味蕾|爱物] + 视图切换
- [ ] T40: [Repository] `UserProfileRepository` 新增 `getUserStats(userId)` + Mock 实现
- [ ] T41: [空态] 互动/生活各子分类的空态文案

### S8: 视觉审计 + 测试覆盖

- [ ] T42: [审计] 执行 `python3 quwoquan_app/scripts/runtime/verify_dart_semantic.py` 确认零新增硬编码违规
- [ ] T43: [文案] 在 `UITextConstants` 新增所有 profile 相关文案常量
- [ ] T44: [测试-L1a] 创建 `test/cloud/user/user_profile_dto_contract_test.dart`：DTO schema 断言（含 circleCount, likeCount）
- [ ] T45: [测试-L1b] 创建 `test/ui/user/widgets/profile_shell_test.dart`：mine/other 模式渲染差异
- [ ] T46: [测试-L1b] 创建 `test/ui/user/widgets/profile_creations_tab_test.dart`：SubTab 切换 + Visibility 过滤
- [ ] T47: [测试-L1b] 创建 `test/ui/user/widgets/profile_circles_tab_test.dart`：卡片渲染 + 空态 + 跳转
- [ ] T48: [测试-L1b] 创建 `test/ui/user/widgets/profile_interaction_tab_test.dart`：子维度 + 方向切换
- [ ] T49: [测试-L1b] 创建 `test/ui/user/widgets/profile_stats_row_test.dart`：统计数字渲染 + 点击跳转
- [ ] T50: [测试-L1c] 创建 `test/ui/user/journey/my_profile_journey_test.dart`：打开→Tab切换→过滤→返回
- [ ] T51: [测试-L1c] 创建 `test/ui/user/journey/other_profile_journey_test.dart`：打开→关注→Tab→圈子跳转
- [ ] T52: [验证] `flutter test test/ui/user/ test/cloud/user/` 全部通过

### S9: v2 布局修正 + 滚动交互升级（A1/A12/A13/A14 验收）

- [ ] T53: [widget] 重构 `profile_header.dart`：头像靠左 + 侵入背景 1/3 + 名字同行 Row + 去掉 @username
  - Stack + Positioned(top: -avatarRadius*2/3) 实现侵入
  - Row 布局：名字与头像同行，垂直对齐到头像下部 2/3
  - 头像外圈边框色使用 backgroundPrimary（暗色模式自适应）
- [ ] T54: [widget] 重构 `profile_action_bar.dart` other 模式：消息 IconButton → 等宽「私信」_ActionButton
  - other 模式布局与 mine 模式完全一致：`Expanded + SizedBox(sm) + Expanded`
  - 私信按钮：`_ActionButton(label: '私信', icon: Icons.chat_bubble_outline, ...)`
- [ ] T55: [widget] 重构 `profile_shell.dart` FlexibleSpaceBar 布局：适配头像侵入式 Stack
  - FlexibleSpaceBar.background 内的 Column 需要为 ProfileHeader 的 Stack/Positioned 留出空间
  - 用户信息区背景色与渐变遮罩终点色无缝衔接
- [ ] T56: [交互] 弹簧阻尼下拉拉伸：替换线性 `_pullOffset * 0.002` 为弹簧函数 `_springDampedOffset`
  - 从旧 `author_profile_page.dart:250-256` 移植弹簧阻尼算法
  - maxPull = 屏幕高度 * 0.25
  - 新增 `AnimationController _pullBackController(duration: 250ms)` 驱动回弹
- [ ] T57: [交互] 头像/名字吸顶过渡动画：交叉淡入淡出替代二元切换
  - 监听 scroll offset 计算折叠进度 `t` (0~1)
  - SliverAppBar.title 中小头像+名字使用 `Opacity(opacity: t)` 渐入
  - FlexibleSpaceBar.background 中大头像使用 `Opacity(opacity: 1-t)` 渐出
  - 过渡区间：从头像区开始折叠到完全折叠（约 100px 范围）
- [ ] T58: [暗色] 工具栏折叠态背景色跟随暗色模式
  - SliverAppBar.backgroundColor = `AppColorsFunctional.getColor(isDark, backgroundPrimary)`
  - 展开态：工具栏透明（背景图可见）→ 折叠态：工具栏使用 bg 实色
- [ ] T59: [暗色] 状态栏图标颜色动态切换
  - 展开态（背景图可见）: `Brightness.light`（白色图标）
  - 折叠态：根据 isDark 决定 `Brightness.light/dark`
- [ ] T60: [测试] 更新 `profile_shell_widget_test.dart`：验证头像侵入布局 + 等宽按钮 + 无 @username
- [ ] T61: [测试] 新增暗色模式渲染测试：验证暗色下颜色语义正确
- [ ] T62: [测试] 更新 Journey 测试：验证弹簧回弹动效 + Tab 吸顶行为
- [ ] T63: [验证] `flutter test test/ui/user/ test/cloud/user/` 全部通过

## 搁置任务（带规划）

- [ ] **Go 云侧 user-service GetUserProfile + ListUserCircles 实现**（重启条件：user-service 进入 dev 阶段；由 `user-identity-profile-relationship/auth-profile-snapshot` 节点承接）
- [ ] **Remote UserProfileRepository 真实 HTTP 对接**（重启条件：cloud API 部署到 integration 环境；由本节点 S1 story 的后续 task 承接）
- [ ] **Patrol E2E 测试（L4）**（重启条件：CI 环境 Patrol 配置就绪；当前 CI 尚未配置 Patrol runner）

## 未来演进任务

- [ ] **E1: 生活 Tab 后端分类 API**：当 content-service 支持 `lifeItemCategory` 参数后，升级 `listUserLifeItems` 端侧过滤为服务端过滤（design.md E2）
- [ ] **E2: profileTabs 动态配置**：将 `profile_tabs` 从 codegen 静态配置升级为 feature flag 动态控制，支持 A/B 测试（design.md E4）
- [ ] **E3: 更多主页模式**：扩展 `ProfileMode` 支持 merchant / creator 等认证主页类型（design.md E3）
- [ ] **E4: features/ 其他目录迁移**：`create → ui/content/entry`、`assistant → ui/assistant`、`settings → ui/settings`、`welcome → ui/welcome`（spec.md O7 标注，后续批次）
