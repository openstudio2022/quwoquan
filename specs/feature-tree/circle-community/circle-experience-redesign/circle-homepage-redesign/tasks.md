# L3 圈子主页端云一体化交付 — 任务列表

## 当前交付任务

### Phase 1: DTO 类型化（metadata 已存在 → 手写 DTO）

- [ ] T1: [DTO] 创建 `lib/cloud/runtime/generated/circle/circle_dto.dart`（CircleDto，字段与 fields.yaml Circle 一致）
- [ ] T2: [DTO] 创建 `circle_member_dto.dart` / `circle_file_dto.dart` / `circle_section_config_dto.dart`
- [ ] T3: [DTO] 创建 `circle_dtos.dart` barrel export
- [ ] T4: [Repository] CircleRepository 返回类型从 Map 迁移到 DTO（Abstract + Mock + Remote 三层）
- [ ] T5: [测试-T1] circle_dto_contract_test.dart：DTO fromMap/toMap 与 fields.yaml 字段一致

### Phase 2: 状态管理

- [ ] T6: [models] 创建 `lib/ui/circle/models/circle_tab.dart`（CircleSectionTab 枚举 + CreationSortMode 枚举）
- [ ] T7: [providers] 创建 `CircleState`（不可变 + copyWith）+ `CircleStateNotifier`（ChangeNotifier）
- [ ] T8: [providers] 注册 `circleStateProvider = ChangeNotifierProvider.family<CircleStateNotifier, String>`
- [ ] T9: [测试-T1] circle_state_notifier_test.dart：状态切换、数据加载、异常处理

### Phase 3: CircleShell 布局重构

- [ ] T10: [widgets] 创建 `CircleHeader`（头像 + 圈名 + 描述 + 标签）
- [ ] T11: [widgets] 创建 `CircleStatsRow`（成员/群聊/粉丝/获赞，可点击跳转统计页）
- [ ] T12: [widgets] 创建 `CircleActionBar`（按 CircleRole 区分：owner/admin → 编辑+管理；member/visitor → 关注+加入）
- [ ] T13: [widgets] 创建 `CircleShell`（NestedScrollView + SliverAppBar + 下拉弹簧拉伸 + 吸顶过渡 + 动态Tab）
- [ ] T14: [测试-T2] circle_shell_test.dart / circle_header_test.dart

### Phase 4: "创作"Tab（对标 ProfileCreationsTab）

- [ ] T15: [constants] 新增 `UITextConstants.circleCreationsTab`（"创作"），替换 `circleWorksTab`（"作品"）
- [ ] T16: [widgets] 创建 `SectionCreations`：横向 SubTab（复用 CreationSubTab）+ 排序控件（最新/最热/精选）+ 视图切换（网格/列表，仅 owner/admin）
- [ ] T17: [widgets] SectionCreations 内容区：双列瀑布流网格（默认）+ 单列卡片（列表模式）
- [ ] T18: [测试-T2] section_creations_test.dart
- [ ] T19: [测试-T3] circle_creations_tab_journey_test.dart（SubTab切换 + 排序切换 + 空态）

### Phase 5: 其他板块重构

- [ ] T20: [widgets] 重构 SectionChat（群聊入口 + 未读标记 + 独立 loading/error）
- [ ] T21: [widgets] 重构 SectionStorage（容量条 + 文件列表 + 独立 loading/error）
- [ ] T22: [widgets] 重构 SectionInteraction（互动流 + 独立 loading/error）
- [ ] T23: [测试-T2] section_independent_loading_test.dart（各板块独立降级验证）

### Phase 6: 整合 & Mock 依赖解除

- [ ] T24: [pages] 重建 CircleDetailPage 使用 CircleShell + CircleStateNotifier
- [ ] T25: [pages] 移除 CircleMockData 直接 import，全部走 Provider
- [ ] T26: [测试-T1] circle_repository_contract_test.dart 扩充：21 方法 + 异常 + Remote URL 断言
- [ ] T27: [测试-T3] circle_join_leave_journey_test.dart（加入退出 + 角色切换）

### Phase 7: 云侧 Feed 补全

- [ ] T28: [云侧] GetCircleFeed 从 stub 升级为完整实现（查询帖子 + cursor 分页 + sort）
- [ ] T29: [云侧-测试] circle_feed_contract_test.go（分页、排序、空 feed、精选置顶）

### Phase 8: 门禁 & 部署

- [ ] T30: [门禁] verify_dart_semantic.py 对 ui/circle/ 零新增违规
- [ ] T31: [门禁] flutter analyze quwoquan_app/lib/ui/circle/ 零 error
- [ ] T32: [门禁] make test-contract -C services/circle-service 通过
- [ ] T33: [部署] integration 环境 seed-box 验证圈子核心 API 端到端可用

## 搁置任务

- [ ] presigned URL 文件上传（重启条件：circle-collaboration-tools L2 启动）
- [ ] 推荐排序 recommendFor 集成（重启条件：resonance-discovery L3 启动）
- [ ] 事件发布者真实注入确认（重启条件：integration 环境事件总线就绪）
- [ ] 创作 Tab 置顶区展示（重启条件：产品确认置顶展示规格）

## 未来演进任务

- [ ] 通用 AppShell 基类抽取（触发条件：第 3 个详情页需求确认）
- [ ] GetCircleFeed 投影模型迁移（触发条件：单圈子帖子量 > 10K）
- [ ] 瀑布流虚拟化（触发条件：性能测试发现长列表卡顿）
