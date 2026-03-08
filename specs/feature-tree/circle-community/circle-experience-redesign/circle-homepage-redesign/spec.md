# L3 规格：圈子主页端云一体化交付

## 背景与动机

圈子详情页（`CircleDetailPage`）当前体验远低于作者主页（`ProfileShell`）：

1. **布局粗糙**：使用 `CustomScrollView` + `SliverToBoxAdapter` 堆叠，无 Tab 吸顶、无下拉弹簧拉伸、无吸顶过渡动画，滚动后无法切换 Tab。
2. **状态管理缺失**：12 个 `setState` 变量分散在页面内，无 Riverpod Notifier，每次操作导致全页面重建。
3. **数据层不安全**：全部使用 `Map<String, dynamic>`，无类型化 DTO；详情页直接 import `CircleMockData`，Remote 模式下 fallback 仍走 Mock。
4. **"作品"Tab 命名和结构落后**：仅提供单一列表，无二级分类（全部/微趣/图片/视频/文字），无排序和视图切换，与作者主页的"创作"Tab 体验割裂。
5. **板块降级缺失**：Section 组件无独立 loading/error 状态，单板块失败会影响用户对其他板块的访问。
6. **云侧 Feed API 未完成**：`GetCircleFeed` 为 stub 状态。

## 目标用户

- **圈子成员 / 访客**：浏览圈子主页、查看创作内容、加入/退出圈子。
- **圈主 / 管理员**：管理圈子信息、配置板块、查看统计、置顶/精选帖子。
- **开发团队**：需要干净的状态管理和类型安全的数据层来高效迭代。

## 功能范围

### F1: CircleShell 布局重构（对标 ProfileShell）

- `NestedScrollView` + `SliverAppBar`（pinned），封面支持下拉弹簧拉伸。
- 吸顶时头像 + 圈名 `AnimatedOpacity` 渐现。
- Tab 栏使用 `SliverPersistentHeader`（pinned），滚动不消失。
- 组件拆分：`CircleShell` / `CircleHeader` / `CircleStatsRow` / `CircleActionBar`。

### F2: "创作"Tab 二级分类（对标 ProfileCreationsTab）

- 原"作品"（works）Tab 重命名为"创作"（creations）。
- 新增横向二级 SubTab：全部 / 微趣 / 图片 / 视频 / 文字。
- 复用 `CreationSubTab` 枚举，按 `contentType` 过滤圈子内帖子。
- 圈主/管理员模式下额外显示排序控件（最新/最热/精选）和视图切换（网格/列表）。

### F3: CircleStateNotifier 状态管理

- 创建 `CircleState`（不可变 + `copyWith`）+ `CircleStateNotifier`（`ChangeNotifier`）。
- 使用 `ChangeNotifierProvider.family<CircleStateNotifier, String>`，按 `circleId` 区分。
- 页面内 `setState` 变量归零，全部迁移到 Notifier。

### F4: Circle DTO 类型化

- 生成 `CircleDto` / `CircleMemberDto` / `CircleFileDto` / `CircleSectionConfigDto`。
- Repository 返回类型从 `Map<String, dynamic>` 迁移到 DTO。
- UI 层不再直接操作 `Map<String, dynamic>`。

### F5: 板块独立加载与降级

- 创作 / 群聊 / 网盘 / 互动 4 个板块各自独立加载。
- 单板块 loading/error 状态隔离，失败显示内联错误卡 + 重试按钮。
- 单板块加载失败不影响其他板块渲染。

### F6: Mock 依赖解除

- `CircleDetailPage` 不再直接 import `CircleMockData`。
- 所有数据通过 `circleRepositoryProvider` 注入。
- `appDataSourceModeProvider` 切换 mock/remote 对 UI 层完全透明。

### F7: 云侧 Feed API 补全

- `GetCircleFeed` 从 stub 升级为完整实现。
- 支持 `cursor` 分页 + `sort`（latest / hot / featured）。
- 契约测试覆盖。

### F8: 四层测试覆盖

- T1（契约层）：Repository 21 方法 + 异常场景、Remote URL/Header 断言。
- T2（Widget 层）：CircleShell / CircleHeader / CircleStatsRow / CircleActionBar / 创作 Tab。
- T3（Journey 层）：加入退出圈子、创作 Tab 切换过滤、文件上传。
- T4（云侧契约）：现有 5 文件通过 + Feed 补充。

### F9: 部署就绪

- integration 环境 seed-box 部署后，圈子核心 API 端到端可用。
- 语义化审计（`verify_dart_semantic.py`）对 `ui/circle/` 零新增违规。

## 不做什么（Out of Scope）

- **不改推荐算法**：`ListCircles?recommendFor` 的排序逻辑归 L3 resonance-discovery，本 L3 不涉及。
- **不改领域标签体系**：domain_taxonomy.yaml 归 L3 domain-taxonomy-alignment。
- **不改助理引擎**：圈子与助理联动（PageContext 携带 domainId）归 L3 独立 story。
- **不改频道管理面板**：circles_page.dart 的频道管理归 runtime/circles-channel-management-panel。
- **不改圈子列表页**：circles_page.dart 布局重构不在本 L3 范围。
- **不做板块拖拽排序 UI**：UpdateCircleSections API 已就绪，但管理入口的拖拽排序 UI 归 circle-management-and-stats。
- **不做实时 WebSocket 推送**：成员变更实时推送归 realtime-gateway 特性。

## 约束

- CircleShell 必须与 ProfileShell 保持交互一致性（吸顶行为、下拉拉伸参数、Tab 栏高度）。
- "创作"Tab 的 SubTab 枚举必须与 ProfileCreationsTab 的 `CreationSubTab` 保持一致。
- DTO 必须由 metadata `fields.yaml` 驱动（codegen 或手写 base + codegen 子类）。
- 所有视觉字面量必须使用 `AppTypography` / `AppSpacing` / `AppColors`，`verify_dart_semantic.py` 零违规。
- 不得引入功能退化：现有路由路径（`/circle/:id`）、板块配置（`sectionConfig`）、角色逻辑（owner/admin/member/visitor）保持不变。

## 对标输入与吸收结论

### 内部对标：ProfileShell（作者主页）

| 维度 | 借鉴点 | 适用边界 |
|------|--------|----------|
| 布局骨架 | `NestedScrollView` + `SliverAppBar` + `SliverPersistentHeader` | 直接复用模式 |
| 下拉拉伸 | `_springDampedOffset` 弹簧阻尼 | 参数一致 |
| 吸顶过渡 | `AnimatedOpacity` 头像 + 名称 | 直接复用 |
| 状态管理 | `ChangeNotifierProvider.family` + 不可变 State | 直接复用模式 |
| 创作 Tab | `CreationSubTab`（全部/微趣/图片/视频/文字）+ 横向 SubTab | 枚举共享，组件复用 |
| 组件拆分 | Header / StatsRow / ActionBar 独立 Widget | 命名对齐（Circle 前缀） |

### 外部对标（待 /design 阶段深入分析）

- 即刻圈子：圈子主页信息密度、加入/退出社交压力设计。
- Discord Server：频道管理深度、角色权限展示。
- 豆瓣小组：内容排序策略、精华帖展示。
- 小红书话题：二级分类 + 瀑布流 + 互动。

## 验收重点

与 `acceptance.yaml` A1~A10 对应：
- 布局重构品质（A1）
- 创作 Tab 完整性（A2）
- 状态管理规范性（A3）
- DTO 类型安全（A4）
- 板块降级可靠性（A5）
- Mock 依赖解除（A6）
- 云侧 Feed 完成度（A7）
- 四层测试覆盖率（A8）
- 语义化审计（A9）
- 部署就绪（A10）
