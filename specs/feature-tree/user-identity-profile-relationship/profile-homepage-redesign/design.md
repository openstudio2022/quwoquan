# 个人主页全面重构 — 设计方案

## 设计动因

当前两个主页页面（`my_profile_page.dart` 1546行 + `author_profile_page.dart` 2539行）存在 80%+ 结构重复，但在数据源、操作按钮、Tab 子内容、可见性逻辑上各自为战。探索阶段识别的 8 个问题（P1~P8）全部需要在本次设计中解决。

核心矛盾：两个页面共享同一套 UI 骨架（背景拉伸、头像、统计行、Tab 框架），但差异散布在每个组件内部，导致改动一处必须同步两处，且极易遗漏。

## 上游输入评审

| 维度 | 评审结论 |
|------|---------|
| spec.md | F1~F11 功能范围清晰，边界（O1~O8）明确 |
| acceptance.yaml | A1~A12 覆盖全部功能点，每条均有测试层映射 |
| 阻断项 | **无**。metadata `fields.yaml` 已有 `followerCount/followingCount/postCount`，缺少 `circleCount/likeCount` 需补充；`ui_config.yaml` 缺少 `profileTabs` 需新建 |

## 对标输入分析

### 抖音个人主页

| 维度 | 抖音做法 | 借鉴 | 适用边界 |
|------|---------|------|---------|
| Tab 切换 | SliverAppBar + TabBar 悬浮吸顶 | **借鉴** | 滚动时 Tab 固定在顶部，用户始终能切换 |
| 公开/私密过滤 | 点击已选中的「作品」Tab 弹出 popup 筛选 | **借鉴** | 交互自然，不占额外空间 |
| 网格布局 | 3列等宽 9:16 封面 | 部分借鉴 | 创作 Tab 用 2列瀑布流（与发现页一致），保持内容形态多样性 |
| 吸顶用户名 | 上滑后 AppBar 显示用户名 + 小头像 | **借鉴** | 上下文保持，用户知道在谁的主页 |
| 2级触达 | Tab + 内容列表 | **借鉴** | 高效 |
| 收藏/喜欢分离 | 与作品平级 Tab | 不借鉴 | 收纳到互动 Tab 子维度，避免一级 Tab 过多 |

### 内部对标

| 组件 | 对标点 | 复用方式 |
|------|--------|---------|
| `CenteredScrollableTabBar` | Tab 导航组件（发现页已用） | 直接复用，创作 SubTab 使用 `leftAlignedCompactMode` |
| `ContentUIConfig.discoveryTabs` | contentType 枚举 | 创作 SubTab id 对齐 discoveryTabs 的 contentType |
| `CircleRepository.listCircles` | 圈子查询 | 扩展为 `listUserCircles(userId)` |

---

## 方案对比

### 方案 A：ProfileShell 统一组件（组合模式）

**核心思路**：一个 `ProfileShell` ConsumerStatefulWidget，通过 `ProfileMode` 枚举控制所有差异分支。共享 UI 骨架，差异区域（操作按钮、可见性过滤、顶栏）通过条件判断或策略对象注入。

```
ProfileShell(mode: ProfileMode.mine, userId: ...)
  ├── _ProfileHeader（背景拉伸 + 头像 + 用户信息 + 统计行）
  ├── _ProfileActionBar（mode 决定按钮组）
  ├── _ProfileTabNavigation（一级 Tab + SliverAppBar 吸顶）
  └── _ProfileTabContent（TabBarView）
       ├── ProfileCreationsTab（SubTab + 可见性过滤）
       ├── ProfileCirclesTab（圈子卡片列表）
       ├── ProfileInteractionTab（赞/评论 + 方向）
       └── ProfileLifestyleTab（生活子分类）
```

**优点**：
- 复用率最高，UI 改动只需改一处
- 组合优于继承，Tab 内容可独立测试
- 差异明确收敛到 `ProfileMode` 一个维度

**缺点**：
- `ProfileShell` 可能因条件分支过多变得复杂
- 需要精心设计 Provider 注入，避免 mine/other 数据混淆

**适用条件**：mine/other 差异可收敛到有限维度（操作按钮、可见性、顶栏），当前分析只有 5 个差异点

---

### 方案 B：抽象基类继承模式

**核心思路**：`BaseProfilePage` 抽象类提供 UI 框架和模板方法，`MyProfilePage extends BaseProfilePage`、`OtherProfilePage extends BaseProfilePage` 各自重写差异方法。

```
abstract BaseProfilePage
  ├── buildActionButtons() → abstract
  ├── buildToolbar() → abstract
  ├── buildTabContent() → 通用
  └── buildHeader() → 通用
```

**优点**：
- 差异通过重写方法表达，类型安全
- 每个子类独立清晰

**缺点**：
- Flutter Widget 继承反模式（官方推荐组合）
- ConsumerStatefulWidget + TickerProvider + 继承 = mixin 地狱
- 共享状态（ScrollController、TabController）管理困难
- Tab 内容组件仍然需要条件判断

**适用条件**：差异维度多且互相正交时

---

### 方案 C：Builder 配置模式

**核心思路**：`ProfileBuilder` 接收 `ProfileConfig` 配置对象，声明式描述差异。

```dart
ProfileBuilder(
  config: ProfileConfig(
    mode: ProfileMode.mine,
    actionButtons: [...],
    visibilityOptions: [...],
    tabs: [...],
  ),
)
```

**优点**：
- 高度声明式，可序列化为后端配置
- 新增模式只需新增 Config

**缺点**：
- 过度抽象，当前只有 mine/other 两种模式
- Config 对象会随功能增长膨胀
- 调试困难，需要追踪 Config → 实际 Widget 映射

**适用条件**：模式 ≥3 种且配置驱动时

---

## 选型决策

**选定方案：方案 A — ProfileShell 统一组件（组合模式）**

**理由**：
1. 当前只有 mine/other 两种模式，5 个差异点（操作按钮、顶栏、可见性、交集文案、内容可见范围），组合模式足以收敛
2. Flutter 官方推荐组合优于继承
3. Tab 内容组件（Creations/Circles/Interaction/Lifestyle）独立提取后，每个可独立 Widget 测试
4. `CenteredScrollableTabBar` 已在发现页验证，直接复用
5. Provider 注入天然隔离数据（`profileStateProvider` family 按 userId 区分）

---

## 关键设计决策

### KD1: ProfileShell 组件架构

```
ProfileShell (ConsumerStatefulWidget, TickerProviderStateMixin)
│
├── 状态管理
│   ├── ScrollController _scrollController
│   ├── TabController _mainTabController (length: 4)
│   └── Provider: profileStateProvider(userId) → ProfileState
│
├── build()
│   └── AnnotatedRegion<SystemUiOverlayStyle>
│       └── Scaffold(extendBodyBehindAppBar: true)
│           └── NestedScrollView
│               ├── headerSliverBuilder
│               │   ├── SliverAppBar (expandedHeight: 背景+用户区)
│               │   │   ├── flexibleSpace: _ProfileHeader
│               │   │   │   ├── 背景图 + 弹簧阻尼下拉拉伸
│               │   │   │   ├── 头像（靠左，侵入背景 1/3）+ 用户名（同行 Row）+ bio
│               │   │   │   ├── _ProfileResonanceCard
│               │   │   │   ├── _ProfileStatsRow
│               │   │   │   └── _ProfileActionBar(mode)（等宽双按钮）
│               │   │   └── title: (collapsed时) 小头像 + 用户名（平滑过渡）
│               │   └── SliverPersistentHeader (Tab 导航, pinned: true)
│               │       └── CenteredScrollableTabBar (一级 Tab)
│               └── body: TabBarView
│                   ├── ProfileCreationsTab(mode, userId)
│                   ├── ProfileCirclesTab(mode, userId)
│                   ├── ProfileInteractionTab(mode, userId)
│                   └── ProfileLifestyleTab(mode, userId)
│
├── _ProfileHeader (独立 Widget)
│   └── Stack
│       ├── 背景图 (NetworkImage + scale 拉伸动效)
│       └── Column (用户信息区)
│
└── 入口
    ├── MyProfilePage → ProfileShell(mode: .mine, userId: currentUserId)
    └── AuthorProfilePage → ProfileShell(mode: .other, userId: widget.userId)
```

**决策**：使用 `NestedScrollView` + `SliverAppBar`（替代当前 `CustomScrollView` + 手动计算吸顶），原因：
- `NestedScrollView` 天然支持 header 折叠 + body TabBarView 滚动协调
- `SliverPersistentHeader(pinned: true)` 保证 Tab 吸顶
- 消除当前手动监听 `ScrollNotification` 判断 `_showStickyHeader` 的脆弱逻辑

---

### KD2: 一级 Tab 枚举与 contentType 对齐

```dart
enum ProfileTab {
  creations,    // 创作（含微趣+图片+视频+文字）
  circles,      // 圈子
  interaction,  // 互动
  lifestyle,    // 生活
}

enum CreationSubTab {
  all,       // 全部
  micro,     // 微趣 — 对齐 discoveryTabs contentType: micro
  image,     // 图片 — 对齐 discoveryTabs contentType: image
  video,     // 视频 — 对齐 discoveryTabs contentType: video
  article,   // 文字 — 对齐 discoveryTabs contentType: article
}

enum CreationVisibility {
  all,       // 全部
  public_,   // 公开
  private_,  // 私密（仅 mine 可见）
}
```

**一级 Tab label 来源**：`UITextConstants` 新增 `profileTabCreations / profileTabCircles / profileTabInteraction / profileTabLifestyle`。

**SubTab label 来源**：`UITextConstants` 新增或复用 `creationSubAll / creationSubMicro / creationSubImage / creationSubVideo / creationSubArticle`。

**contentType 语义对齐表**：

| 创作 SubTab | discoveryTabs id | contentType | label |
|------------|------------------|-------------|-------|
| all | — | — | 全部 |
| micro | moment | micro | 微趣 |
| image | photo | image | 图片 |
| video | video | video | 视频 |
| article | article | article | 文字 |

---

### KD3: 可见性过滤 Popup 交互

```
用户点击已选中的「创作」Tab
  │
  ▼
showMenu / OverlayEntry 弹出定位在 Tab 下方
  ├── [全部]  ← 默认选中
  ├── [公开]
  └── [私密]  ← 仅 mode==mine 时显示
  │
  ▼
选择后更新 _activeVisibility, 收起 popup
  │
  ▼
若 visibility != all → Tab 文字旁显示蓝色圆点指示器
```

**实现方式**：`PopupMenuButton` 或自定义 `OverlayEntry`。推荐自定义 `OverlayEntry`（精确定位在 Tab 下方，与抖音行为一致）。

**私密作品标识**：封面叠加半透明黑色遮罩 + 锁 icon（`Icons.lock_outline`），使用 `Stack` + `Positioned`。

---

### KD4: 圈子 Tab 数据源

**当前状态**：
- `CircleRepository` 有 `listCircles({category, domainId})` 但无 `listUserCircles(userId)` 方法
- `UserProfileRepository` 有 `listUserPosts / listUserWorks / listUserLifeItems` 但无圈子相关方法

**设计决策**：在 `UserProfileRepository` 新增 `listUserCircles(userId)` 方法，而非在 `CircleRepository` 添加。原因：
1. 「用户已加入的圈子」属于用户档案视图，归 UserProfile 域
2. 端侧 Repository 归属清晰：用户主页所有数据通过 `userProfileRepositoryProvider` 获取
3. 云侧可通过 user-service 查询 membership 表关联 circle，或调用 circle-service 内部 API

**数据结构**：

```dart
// UserProfileRepository 接口扩展
abstract class UserProfileRepository {
  // 现有
  Future<List<Map<String, dynamic>>> listUserPosts(String userId, {int limit = 20});
  Future<List<Map<String, dynamic>>> listUserWorks(String userId);
  Future<List<Map<String, dynamic>>> listUserLifeItems(String userId);

  // 新增
  Future<List<Map<String, dynamic>>> listUserCircles(String userId, {int limit = 50});
  Future<Map<String, dynamic>> getUserStats(String userId);
}
```

圈子卡片 DTO（Map 字段）：`id, name, coverUrl, memberCount`。

---

### KD5: ProfileState Provider 设计

```dart
@freezed
class ProfileState with _$ProfileState {
  factory ProfileState({
    required String userId,
    required ProfileMode mode,
    @Default(ProfileTab.creations) ProfileTab activeTab,
    @Default(CreationSubTab.all) CreationSubTab activeSubTab,
    @Default(CreationVisibility.all) CreationVisibility activeVisibility,
    @Default(AsyncValue.loading()) AsyncValue<Map<String, dynamic>> userProfile,
    @Default(AsyncValue.loading()) AsyncValue<List<Map<String, dynamic>>> creations,
    @Default(AsyncValue.loading()) AsyncValue<List<Map<String, dynamic>>> circles,
    @Default(AsyncValue.loading()) AsyncValue<Map<String, dynamic>> stats,
    @Default(false) bool isFollowing,
  }) = _ProfileState;
}

// Family Provider，按 userId 隔离
final profileStateProvider = StateNotifierProvider.family<ProfileNotifier, ProfileState, String>(
  (ref, userId) => ProfileNotifier(ref, userId),
);
```

**数据加载策略**：
- `userProfile` + `stats`：进入页面时立即加载
- `creations`：默认 Tab，立即加载
- `circles`：切换到圈子 Tab 时懒加载（`_onTabChanged`）
- 下拉刷新：RefreshIndicator 绑定到 NestedScrollView body

---

### KD6: mine / other 差异矩阵

| 区域 | mine | other |
|------|------|-------|
| 顶栏左侧 | 无（或身份切换） | 返回按钮 |
| 顶栏右侧 | 设置 icon | 更多 icon（拉黑/举报/分享） |
| 操作按钮 | [编辑资料, 管理人设]（等宽双按钮） | [关注/已关注, 私信]（等宽双按钮，与 mine 布局一致） |
| 交集卡片文案 | 「本周有 N 位趣友与你有交集」 | 「你们有 N 个交集点」 |
| 创作可见性 | [全部, 公开, 私密] | [全部, 公开] |
| 私密作品 | 可见（带锁标） | 不可见 |
| 互动方向 | [收到, 发出] | 仅 Ta 收到（公开部分） |
| 圈子范围 | 全部已加入 | 仅公开可见圈子 |

---

### KD7: 目录结构（迁移后目标态）

```
lib/ui/user/
├── pages/
│   ├── my_profile_page.dart        # 入口：ProfileShell(mode: mine)
│   ├── other_profile_page.dart     # 入口：ProfileShell(mode: other)（重命名自 author_profile_page.dart）
│   ├── edit_profile_page.dart      # 迁移（不重写）
│   ├── persona_management_page.dart # 迁移（不重写）
│   ├── resonance_page.dart         # 迁移（不重写）
│   └── profile_stats_page.dart     # 迁移（不重写）
├── widgets/
│   ├── profile_shell.dart          # ProfileShell 核心组件
│   ├── profile_header.dart         # 背景 + 头像 + 用户信息
│   ├── profile_action_bar.dart     # 操作按钮行
│   ├── profile_stats_row.dart      # 统计行
│   ├── profile_resonance_card.dart # 交集/共鸣卡片
│   ├── profile_creations_tab.dart  # 创作 Tab 内容（SubTab + 过滤）
│   ├── profile_circles_tab.dart    # 圈子 Tab 内容
│   ├── profile_interaction_tab.dart # 互动 Tab 内容
│   ├── profile_lifestyle_tab.dart  # 生活 Tab 内容
│   ├── creation_visibility_popup.dart # 可见性过滤 popup
│   └── circle_card.dart            # 圈子卡片
├── providers/
│   ├── profile_state_provider.dart # ProfileState + Notifier
│   └── profile_creations_provider.dart # 创作内容 Provider（SubTab + Visibility 过滤）
└── models/
    ├── profile_mode.dart           # ProfileMode enum
    ├── profile_tab.dart            # ProfileTab / CreationSubTab / CreationVisibility enum
    └── profile_state.dart          # ProfileState freezed model
```

---

### KD8: 设计 Token 规划

本次重构所有视觉字面量必须语义化：

| 用途 | 当前硬编码 | 目标 Token |
|------|-----------|-----------|
| 头像半径 | `45.r` | `AppSpacing.xl + AppSpacing.sm` (40) 或新增 `AppSpacing.avatarLarge` |
| 头像边框 | `3.w` / `4.w` | `AppSpacing.intraGroupXs` (4) |
| 用户名字号 | `20.sp` | `AppTypography.xxl` (20) |
| bio 字号 | `14.sp` | `AppTypography.md` (14) |
| 统计数字字号 | `18.sp` / `22.sp` | `AppTypography.xl` (18) |
| 统计标签字号 | `14.sp` / `11.sp` | `AppTypography.sm` (12) |
| Tab 高度 | — | `AppSpacing.tabNavigationHeight` (48) |
| SubTab 高度 | — | `AppSpacing.subTabNavigationHeight` (44) |
| 容器内边距 | `16.w` | `AppSpacing.containerMd` (16) |
| 圆角（卡片） | `8.r` / `12` / `24.r` | `AppSpacing.borderRadius` (8) / `AppSpacing.largeBorderRadius` (12) |
| 最小热区 | — | `AppSpacing.minInteractiveSize` (44) |
| 颜色（Tab 未选中） | 各种硬编码 | `AppColorsFunctional.getColor(isDark, ColorType.tabUnselected)` |
| 颜色（前景主） | 各种硬编码 | `AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary)` |
| 颜色（前景次） | 各种硬编码 | `AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary)` |
| 颜色（背景主） | 各种硬编码 | `AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary)` |

---

### KD9: 端云 DTO 对齐方案

**当前状态**：`lib/cloud/runtime/generated/user/` 目录不存在，无 codegen 产物。

**目标**：
1. 补充 `contracts/metadata/user/user_profile/fields.yaml`：新增 `circleCount`、`likeCount` 字段
2. 新建 `contracts/metadata/content/post/ui_config.yaml` 中追加 `profile_tabs` 配置节
3. `make codegen-app` 生成 `user_profile_dto.g.dart`（含统计字段）

**metadata 变更清单**：

| 文件 | 变更 | 说明 |
|------|------|------|
| `user/user_profile/fields.yaml` | 新增 `circleCount: int`、`likeCount: int` | 统计字段补齐 |
| `content/post/ui_config.yaml` | 新增 `profile_tabs` 节 | 主页 Tab 配置元数据化 |
| `social/circle/service.yaml` | 新增 `GET /v1/user/{userId}/circles` | 用户已加入圈子 API 声明 |

---

## Story 与测试层映射

本 L2 特性按以下 L4 Story 分解（design 阶段确定 story 边界，tasks.md 细化工程步骤）：

| Story | 范围 | 主要验收项 | 测试层 |
|-------|------|-----------|--------|
| S1: metadata + codegen 基线 | fields.yaml / ui_config / service.yaml + codegen | A6 | T1(契约) |
| S2: ProfileShell 核心框架 | ProfileShell + Header + ActionBar + StatsRow | A1, A11, A12 | T1+T2+T4 |
| S3: 创作 Tab（SubTab + Visibility） | ProfileCreationsTab + popup | A3 | T1+T2+T4 |
| S4: 圈子 Tab | ProfileCirclesTab + CircleCard + Repository | A4 | T1+T2 |
| S5: 互动 Tab + 生活 Tab | Interaction + Lifestyle | A9, A10 | T2 |
| S6: 一级 Tab 导航 | CenteredScrollableTabBar 集成 + 默认选中 | A2 | T1+T2+T4 |
| S7: 目录迁移 | features/profile/ → ui/user/ + router 更新 | A5 | T1+T4 |
| S8: 视觉审计 + 测试覆盖 | Token 替换 + verify_dart_semantic + 测试补全 | A7, A8 | T1+T2 |

**推荐实施顺序**：S7 → S1 → S2 → S6 → S3 → S4 → S5 → S8

理由：先迁移目录清除技术债务，再建立 metadata/codegen 基线，然后从核心框架到 Tab 内容逐步构建。

---

## 适用场景与约束

### 适用场景

- 当前 mine/other 两种模式，差异维度有限（5个）
- Flutter Widget 组合模式
- Riverpod Provider family 状态隔离
- NestedScrollView + SliverAppBar 滚动协调

### 约束与局限性

- `NestedScrollView` 内层 `TabBarView` 在快速滑动时可能有滚动冲突，需要 `physics: NeverScrollableScrollPhysics()` 配合
- 圈子 Tab 目前走 Mock，Remote 实现依赖云侧 user-service API 就绪
- `ProfileState` freezed model 需要 build_runner 生成，增加构建时间
- 私密作品过滤依赖端侧 `listUserPosts` 的 `visibility` 参数，云侧 API 需支持

---

## 未来演进

### E1: 真实 API 对接

当云侧 user-service 就绪后，Remote 实现替换 Mock：
- 触发条件：user-service API 全部部署到 integration 环境
- 变更范围：`RemoteUserProfileRepository` 实现
- 风险：无，架构预留了 Mock/Remote 切换

### E2: 生活 Tab 后端 API 升级

当前 `listUserLifeItems` 返回混合列表，未来按 `[足迹, 书影音, 味蕾, 爱物]` 分类查询：
- 触发条件：content-service 支持 `lifeItemCategory` 参数
- 变更范围：Repository 方法签名 + 端侧过滤逻辑

### E3: 更多个人主页模式

若未来需要「商家主页」「创作者认证主页」等，可将 `ProfileMode` 扩展为 `mine / other / merchant / creator`，差异矩阵扩展即可，架构无需重构。

### E4: profileTabs 后端动态配置

当前 `profile_tabs` 写死在 ui_config.yaml，未来可通过 feature flag 动态控制 Tab 顺序和可见性。

---

## 编码规范与设计 Token

见 KD8 设计 Token 规划表。额外约束：

- 所有 `Text` widget 必须使用 `AppTypography.*` 字号 + `AppTypography.*` 字重
- 所有 `EdgeInsets` 必须使用 `AppSpacing.*` 组合（如 `AppSpacing.containerMd`）
- 所有颜色必须使用 `AppColorsFunctional.getColor(isDark, ColorType.xxx)` 或 `AppColors.*`
- 所有文案必须使用 `UITextConstants.*` 或 `context.l10n.*`
- 可交互元素（按钮、Tab、统计数字）最小尺寸 `AppSpacing.minInteractiveSize` (44)
- `CenteredScrollableTabBar` 直接复用，禁止自建 Tab 组件

---

### KD10: 头像侵入布局（v2 修正）

**设计动因**：初版 ProfileHeader 采用居中 Column 布局（头像居中、名字在头像下方、显示 @username），与竞品主页和旧 AuthorProfile 实现的视觉语言不一致。v2 修正为侵入式靠左布局，更接近抖音/小红书风格。

**布局模型**：

```
┌────────────────────────────────────────────┐
│  BACKGROUND IMAGE (25vh + statusBar)       │
│  ┌───────┐                                 │
│  │ 1/3   │  ← 头像顶部 1/3 侵入背景区      │
════╡ avatar ╞═══════════════════════════════════
│  │       │  DisplayName       ← Row 同行   │
│  │ 2/3   │  bio text...       ← 名字下方   │
│  └───────┘                                 │
│  [交集卡片]                                 │
│  [统计行: 关注 圈子 粉丝 赞]                 │
│  [操作栏: 等宽双按钮]                        │
└────────────────────────────────────────────┘
```

**实现方式**：

```dart
// ProfileHeader 重构为 Stack + Positioned
Stack(
  clipBehavior: Clip.none,
  children: [
    // 信息区内容（padding-left 为头像直径+间距）
    Padding(
      padding: EdgeInsets.only(
        top: avatarRadius * 2/3 + AppSpacing.sm,
        left: avatarDiameter + AppSpacing.containerMd + AppSpacing.sm,
        right: AppSpacing.containerMd,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(displayName, style: ...),  // 无 @username
          if (bio != null) Text(bio, ...),
        ],
      ),
    ),
    // 头像（侵入背景 1/3）
    Positioned(
      top: -(avatarRadius * 2 / 3),  // 负偏移 = 头像直径的 1/3
      left: AppSpacing.containerMd,
      child: CircleAvatar(radius: avatarRadius, ...),
    ),
  ],
)
```

**关键参数**：
- 头像 radius: `AppSpacing.xl`（约 40pt，直径 80pt）
- 侵入偏移: `-avatarRadius * 2 / 3`（约 -27pt，即 1/3 直径侵入背景）
- 名字与头像垂直对齐到头像下部 2/3 区域
- 头像外圈白色边框: `AppSpacing.intraGroupXs`（4pt）

**暗色模式**：
- 头像外圈边框色: `backgroundPrimary`（暗色下自动变深色背景）
- 信息区背景: 渐变遮罩终点色 = `backgroundPrimary`（暗色下无断层）

---

### KD11: 多阶段滚动交互（v2 升级）

**设计动因**：初版使用 `innerBoxIsScrolled` 做二元头像切换（突然出现/消失），下拉拉伸为线性缩放无弹簧阻尼。v2 升级为连续状态机，对标抖音级滚动体验。

**5 阶段状态机**（由 `scrollOffset` 驱动）：

| 阶段 | scrollOffset 范围 | 视觉表现 |
|------|------------------|---------|
| 0 (overscroll) | < 0 | 背景图弹簧阻尼放大，松手回弹 ≤ 300ms |
| 1 (初始) | = 0 | 完全展开：背景 + 大头像 + 信息区 + Tab |
| 2 (过渡) | 0 ~ threshold_A | 背景折叠，头像/名字渐入工具栏（交叉淡入淡出） |
| 3 (Tab 吸顶) | ≈ threshold_A | 工具栏显示小头像+名字，一级 Tab 吸顶 |
| 4 (深度滚动) | >> threshold_A | 双层吸顶固定，二级 Tab 跟随内容滚动 |

**方案对比（头像过渡动画）**：

| 方案 | 优点 | 缺点 | 选型 |
|------|------|------|------|
| A: 基于 scrollOffset 手动插值 | 完全可控 | 状态管理复杂 | — |
| B: 自定义 FlexibleSpaceBar | 与 Sliver 协议一致 | 实现极复杂 | — |
| **C: 两层交叉淡入淡出** | 实现相对简单、足够好 | 不是"同一头像在移动" | **选定** |

**选定方案 C 理由**：
1. 大头像在 `FlexibleSpaceBar.background` 中随折叠自然消失（opacity 由框架控制）
2. 小头像在 `SliverAppBar.title` 中随 `innerBoxIsScrolled` 出现
3. 增加过渡期间的 opacity 渐变（使用 `AnimatedOpacity` 或基于 scroll 监听手动设 opacity）
4. 视觉效果已足够好（抖音也是交叉淡入而非像素级移动）
5. 与 NestedScrollView 完全兼容，无需自定义 Sliver

**弹簧阻尼下拉拉伸**：从旧 `author_profile_page.dart` 移植弹簧函数：

```dart
double _springDampedOffset(double raw, double maxPull) {
  if (raw <= 0 || maxPull <= 0) return 0;
  final damping = maxPull / 1.2;
  return (maxPull * (1 - exp(-raw / damping))).clamp(0, maxPull);
}
```

- maxPull = 屏幕高度 * 0.25
- 背景图: `Transform.scale(1 + springOffset / backgroundHeight / 2)`
- 松手回弹: `AnimationController(duration: 250ms)` + `CurvedAnimation(Curves.easeOut)`

**双层吸顶**：

```
┌── SliverAppBar (pinned: true) ──────────────┐
│  collapsedHeight: kToolbarHeight             │
│  title: (collapsed时) 小头像 + 名字          │
├── SliverPersistentHeader (pinned: true) ────┤
│  一级 Tab: [创作 | 圈子 | 互动 | 生活]       │
└─────────────────────────────────────────────┘
```

两个 pinned sliver 构成复合吸顶头，NestedScrollView 自动处理回拉时的 outer/inner 滚动交接。

---

### KD12: 暗色模式语义背景（v2 新增）

**设计动因**：头像侵入布局在背景图与信息区之间创建了视觉分界线，暗色模式下这条分界线的颜色过渡必须无断层。

**颜色过渡链**：

```
背景图区域
  └── 渐变遮罩: [transparent → bg.withAlpha(0.6) → bg]
      └── bg = AppColorsFunctional.getColor(isDark, backgroundPrimary)
          ├── 亮色: #FFFFFF
          └── 暗色: #1A1A1A

信息区背景
  └── bg（与渐变终点色一致，无断层）

工具栏折叠态
  └── backgroundColor: bg（与信息区一致）
  └── foregroundColor: fg = getColor(isDark, foregroundPrimary)

头像外圈
  └── borderColor: bg（与信息区背景融合）
```

**状态栏适配**：
- 展开态（背景图可见）: `statusBarIconBrightness: Brightness.light`（白色图标）
- 折叠态（亮色模式）: `statusBarIconBrightness: Brightness.dark`
- 折叠态（暗色模式）: `statusBarIconBrightness: Brightness.light`
- 通过 `ScrollNotification` 监听折叠进度，动态切换 `SystemUiOverlayStyle`

---

## 存量带规划任务

见 tasks.md 「搁置任务」和「未来演进任务」章节。
