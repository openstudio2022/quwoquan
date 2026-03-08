# L3 圈子主页端云一体化交付 — 设计方案

## 设计动因

解决 spec.md 中 6 个结构性问题：布局粗糙(F1)、创作Tab缺二级分类(F2)、状态管理缺失(F3)、DTO缺类型安全(F4)、板块无降级(F5)、云侧Feed未完成(F7)。同时完成 explore 阶段遗留的 6 个澄清项分析。

## 上游输入评审

- spec.md F1~F9 清晰，约束明确（ProfileShell 一致性、CreationSubTab 枚举共享、verify_dart_semantic.py 零违规）。
- acceptance.yaml A1~A10 可测，每条有明确判定方式和测试层映射。
- 无阻断项。metadata（fields.yaml/service.yaml/storage.yaml/events.yaml/errors.yaml）全部已存在且完备。

## Explore 遗留澄清项分析

### C1: GetCircleFeed 投影实现状态

**结论：纯 stub，需本次实现。**

`circle_service.go` 的 `GetCircleFeed` 直接返回空切片，注释说明"生产环境应委托 content-service"。

**设计决策**：本次在 circle-service 内部实现轻量 Feed 查询（查询 circles 集合中 circleId 关联帖子），不引入跨服务调用。当帖子量增长到需要投影模型时，再迁移到 `circle_feed.yaml` 定义的 ReadModel。

### C2: memberCount 并发一致性

**结论：已使用 `$inc` 原子操作，无需修改。**

`MongoCircleStore.IncrementMemberCount` 使用 `$inc` + `$set updatedAt`，JoinCircle 和 LeaveCircle 都通过此方法操作。并发安全。

### C3: 对象存储预签名 URL

**结论：Stub，CreateFile 不生成 presigned URL。**

`file_service.go` 设置了 `ObjectKey`（`circleID/objectID/name`）但不生成上传 URL。注释说明需 S3 SDK。

**设计决策**：本次 out-of-scope（spec 已排除）。文件上传功能已有端侧 UI 和云侧 CRUD，presigned URL 集成归 circle-collaboration-tools L2。端侧文件列表展示和元数据操作不受影响。

### C4: 推荐排序逻辑

**结论：`recommendFor` 参数已从 HTTP 传到 store，但 store 未使用。**

`MongoCircleStore.List` 中 `opts.RecommendFor` 完全未参与查询或排序。

**设计决策**：本次 out-of-scope（spec 已排除推荐算法修改）。归 L3 resonance-discovery。

### C5: Redis 缓存实现

**结论：完整 cache-aside 模式，已在 main.go 中接入。**

FindByID 先查 Redis（TTL 600s），miss 则查 MongoDB 并回填。Update/Archive/IncrementMemberCount/UpdateStorageUsed/UpdateSections 成功后 Del key。main.go 条件启用（有 REDIS_ADDR 则启用）。无需修改。

### C6: 事件发布

**结论：CircleMemberJoined/Left 已正确发布。**

使用 `publishEvent` 统一方法，payload 含 circleId/userId/role。默认 `noopPublisher`，需通过 `WithEventPublisher` 注入真实实现。integration/prod 环境需确保注入。

## 对标输入分析

### 内部对标：ProfileShell

| 维度 | 借鉴点 | 适用边界 |
|------|--------|----------|
| 布局骨架 | `NestedScrollView` + `SliverAppBar` + `SliverPersistentHeader` | 直接复用 |
| 下拉拉伸 | `_springDampedOffset` 弹簧阻尼 | 参数一致 |
| 吸顶过渡 | `AnimatedOpacity` 头像 + 名称 | 直接复用 |
| 状态管理 | `ChangeNotifierProvider.family` + 不可变 State | 直接复用模式 |
| 创作 Tab | `CreationSubTab`（全部/微趣/图片/视频/文字）+ 横向 SubTab | 枚举共享 |

### 外部对标

| 产品 | 借鉴点 | 不借鉴 | 适用边界 |
|------|--------|--------|----------|
| **即刻** | 弱社交压力加入机制（已实现）；重叠头像行展示活跃成员 | 仅两Tab；纯单列Feed | 轻量讨论圈适用，不适合多媒体创作 |
| **Discord** | 角色颜色标识；新人引导页概念 | 左右分栏；多频道层级；实时在线指示 | 信息架构思想（分区+角色），非具体交互 |
| **豆瓣** | 最新/最热/精华排序切换（创作Tab必需）；置顶帖机制；分区Tab ≤5 | 纯文本列表；100条/页分页 | 排序策略通用，展示形态需适配多媒体 |
| **小红书** | 双列瀑布流（创作Tab核心布局）；子Tab内容分类；封面+赞数卡片 | 三层自动聚类；纯推荐驱动 | 视觉内容布局最佳参考 |

### 综合吸收结论

| 区域 | 采纳方案 | 来源 |
|------|----------|------|
| 布局骨架 | NestedScrollView + SliverAppBar + 吸顶Tab | ProfileShell |
| 创作Tab内容 | 双列瀑布流网格 | 小红书 |
| 创作Tab子分类 | 横向SubTab（全部/微趣/图片/视频/文字） | ProfileCreationsTab + 小红书 |
| 创作Tab排序 | 最新/最热/精选（圈主/管理员可见） | 豆瓣 |
| 头部成员展示 | StatsRow 数字可点击（当前方案足够） | 各产品 |
| 角色区分 | ActionBar 按 CircleRole 区分操作 | Discord |

## 方案对比

### 方案 A（选定）：CircleShell 复用 ProfileShell 模式

**描述**：新建 `CircleShell` widget，复用 ProfileShell 的 `NestedScrollView` + `SliverAppBar` + `SliverPersistentHeader` 骨架。创作Tab 使用 `SectionCreations` 新组件（横向 SubTab + 瀑布流网格）。状态管理使用 `CircleStateNotifier` + `ChangeNotifierProvider.family`。

**优点**：
- 与 ProfileShell 交互完全一致，用户体验连贯
- 复用已验证的弹簧阻尼、吸顶、Tab 吸顶等代码模式
- 状态管理模式统一，维护成本低
- 创作Tab SubTab 枚举可共享 `CreationSubTab`

**缺点**：
- 重写量大（当前 CircleDetailPage 需要完全重建）
- Tab 数量动态（由 sectionConfig 驱动）而非固定 4 个，需要适配 `TabController` 动态 length

**适用条件**：圈子主页需要与作者主页同等品质时（当前需求正是如此）。

### 方案 B（备选）：最小修改 — 在现有 CustomScrollView 上修补

**描述**：保留现有 `CustomScrollView` 结构，仅将 Tab 改为 `SliverPersistentHeader` 吸顶，将 `setState` 改为 Notifier，将 Map 改为 DTO。不改布局骨架。

**优点**：
- 修改量小，风险低
- 不改整体 Widget 树结构

**缺点**：
- 无法实现下拉弹簧拉伸和吸顶过渡动画
- 与 ProfileShell 交互不一致，体验割裂
- `CustomScrollView` 下内嵌 Tab 切换需要大量 workaround
- 头部 `Transform.translate(offset: (0, -96))` hack 无法消除

**适用条件**：仅需修补性改进、不追求与 ProfileShell 一致性时。

### 方案 C（备选）：抽取通用 AppShell 基类

**描述**：从 ProfileShell 中抽取通用的 `AppShell` 基类（含 NestedScrollView + SliverAppBar + Tab 吸顶 + 下拉拉伸），ProfileShell 和 CircleShell 都继承。

**优点**：
- 最大程度复用，减少代码重复
- 未来新的详情页（如 Topic、Event）可直接继承

**缺点**：
- ProfileShell 已有大量使用者（ProfilePage、OtherProfilePage），抽取基类可能引入回归风险
- Profile 和 Circle 的头部内容差异大（Profile 有 ResonanceCard，Circle 有 sectionConfig 动态Tab），基类抽象层次不好定
- 过度抽象可能导致继承层次过深

**适用条件**：当有 3+ 个详情页需要同样骨架时再考虑。

## 选型决策

**选定方案 A**：CircleShell 复用 ProfileShell 模式。

**理由**：
1. 用户明确要求"参考作者主页的交互体验重新设计"
2. ProfileShell 模式已验证成熟
3. 方案 B 无法满足体验一致性要求
4. 方案 C 过度抽象，Profile 修改风险不可控
5. 未来如确实需要抽取基类，可从 CircleShell + ProfileShell 的共同模式中提取（方案 A 不阻塞方案 C 演进）

## 关键设计决策

### DK-1: Tab 动态 length（已定，不变）

CircleShell 的 Tab 数量由 `sectionConfig` 驱动，而非 ProfileShell 的固定 4 Tab。`TabController` 的 `length` 在 `initState` 时从 `circleData.sectionConfig` 的可见板块数计算。默认（无 sectionConfig 时）展示 2 Tab：创作 + 互动。

### DK-2: "创作"Tab 取代"作品"Tab（已定，不变）

- sectionType `works` 的显示标签从 `UITextConstants.circleWorksTab` 更改为 `UITextConstants.circleCreationsTab`（新增常量）
- 内部 sectionType 枚举值保持 `works` 不变（兼容已有 sectionConfig 数据），仅改 UI 标签
- 创作Tab内部使用 `CreationSubTab` 枚举，与 ProfileCreationsTab 完全一致

### DK-3: 创作 Tab 排序策略（已定）

| 排序 | 逻辑 | 可见性 |
|------|------|--------|
| 最新 | `createdAt DESC` | 全员 |
| 最热 | `likeCount + commentCount DESC` | 全员 |
| 精选 | `featuredAt IS NOT NULL`, `featuredAt DESC` | 全员 |

默认排序：成员/访客看「最新」；圈主/管理员看「最新」但额外显示排序切换控件。

### DK-4: CircleState 字段设计（已定）

```dart
class CircleState {
  final String circleId;
  final CircleDto? circleData;
  final CircleRole role;
  final String joinStatus;       // none | pending | joined
  final bool isFollowed;
  final String activeTabType;    // works | chat | storage | interaction
  final CreationSubTab activeSubTab;
  final CreationSortMode sortMode; // latest | hot | featured
  final bool isLoading;
  final String? error;
  final List<PostBaseDto> creations;
  final List<CircleMemberDto> members;
  final List<CircleFileDto> files;
  final Map<String, dynamic> stats;
  // + copyWith
}
```

### DK-5: Circle DTO 结构（已定）

遵循 content 域的 DTO 模式：手写 base 类，字段与 `fields.yaml` 一致。

```
lib/cloud/runtime/generated/circle/
├── circle_dtos.dart           # barrel export
├── circle_dto.dart            # CircleDto（手写，对应 fields.yaml Circle）
├── circle_member_dto.dart     # CircleMemberDto
├── circle_file_dto.dart       # CircleFileDto
└── circle_section_config_dto.dart  # CircleSectionConfigDto（嵌入文档）
```

每个 DTO 提供 `fromMap(Map<String, dynamic> m)` 工厂构造和 `toMap()` 方法。Repository 在 Mock/Remote 实现中统一调用 `CircleDto.fromMap(jsonMap)` 转换。

### DK-6: GetCircleFeed 云侧实现策略（已定）

在 circle-service 内部通过 content-service 的 `ListPosts(circleIds=[circleId])` 或直接查询共享 MongoDB（如果同进程）获取帖子。

实现方案：
1. seed-box 进程（integration/prod）中 circle 和 content 同进程 → 直接复用 content 的 MongoDB 连接查 posts 集合
2. 独立 circle-service 进程（dev）→ HTTP 调用 content-service API

sort 参数映射：
- `latest` → `createdAt DESC`
- `hot` → `likeCount DESC`
- `featured` → `pinnedAt IS NOT NULL` 优先 + `featuredAt DESC`

### DK-7: 板块独立加载架构（已定）

每个 Section Widget 内部管理自己的 loading/error 状态，不依赖 CircleStateNotifier 的全局 isLoading。

```
CircleShell
└── TabBarView
    ├── SectionCreations  → ref.read(circleRepositoryProvider).getCircleFeed(...)
    ├── SectionChat       → 检查 circleData.conversationId 是否存在
    ├── SectionStorage    → ref.read(circleRepositoryProvider).listFiles(...)
    └── SectionInteraction → 本地互动列表（不需要额外 API）
```

失败降级：内联错误卡（图标 + 文案 + 重试按钮），使用 `AppColors.error` + `AppSpacing.interGroupMd` 间距。

### DK-8: 创作 Tab 视图切换（已定，仅圈主/管理员）

- 默认视图：双列瀑布流网格（`GridView.builder` 或 `SliverGrid`）
- 列表视图：单列卡片（封面左 + 标题/描述右 + 互动数）
- 切换按钮：仅 `CircleRole.owner` 或 `CircleRole.admin` 可见
- 状态存储在 `CircleState.viewMode`（grid | list）

## Story 与测试层映射

| Story（任务组） | A# | T1 契约 | T2 Widget | T3 Journey | T4 云侧 |
|------------------|-----|---------|-----------|------------|---------|
| DTO 类型化 | A4 | circle_dto_contract_test.dart | — | — | — |
| CircleStateNotifier | A3 | circle_state_notifier_test.dart | — | — | — |
| CircleShell 布局 | A1 | — | circle_shell_test.dart, circle_header_test.dart | — | — |
| 创作 Tab | A2 | — | section_creations_test.dart | circle_creations_tab_journey_test.dart | — |
| 板块独立降级 | A5 | — | section_independent_loading_test.dart | — | — |
| Mock 依赖解除 | A6 | circle_repository_contract_test.dart | — | — | — |
| 云侧 Feed | A7 | — | — | — | circle_feed_contract_test.go |
| 全量测试 | A8 | 21方法覆盖 | 5组件覆盖 | 3旅程覆盖 | 5+1文件通过 |
| 语义化 | A9 | verify_dart_semantic.py | — | — | — |
| 部署 | A10 | — | — | integration E2E | make test-contract |

## 未来演进

1. **通用 AppShell 基类抽取**：当第 3 个详情页（如 Topic/Event）需要同样骨架时，从 ProfileShell + CircleShell 中抽取共同模式。触发条件：新详情页需求确认。
2. **presigned URL 文件上传**：当需要真实文件上传时，集成 S3/OBS SDK 生成预签名 URL。触发条件：circle-collaboration-tools L2 启动。
3. **GetCircleFeed 投影模型**：当圈子内帖子量 > 10K 条时，从同步查询迁移到 `circle_feed.yaml` 定义的 ReadModel（事件驱动投影）。触发条件：单圈子帖子量突破阈值。
4. **推荐排序集成**：`recommendFor` 参数对接 rec-model-service。触发条件：L3 resonance-discovery 启动。
5. **创作 Tab 置顶区**：在瀑布流顶部展示圈主置顶的 N 条内容（视觉差异标识）。触发条件：产品确认置顶展示规格。

## 遗留带规划任务

- [ ] presigned URL 集成（重启条件：circle-collaboration-tools L2 启动）
- [ ] 推荐排序实现（重启条件：resonance-discovery L3 启动）
- [ ] 事件发布者注入确认（重启条件：integration 环境事件总线就绪）
- [ ] AppShell 基类抽取（重启条件：第 3 个详情页需求确认）
