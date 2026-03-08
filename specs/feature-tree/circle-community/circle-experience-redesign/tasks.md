# L2 圈子体验重构 — 任务列表

## 当前交付任务

### L3: domain-taxonomy-alignment

- [ ] T1: [metadata] 创建 `contracts/metadata/_shared/domain_taxonomy.yaml`，定义 16 个核心领域 ID（travel, local_life, health_wellness, tech, education, lifestyle, social_meet, culture_arts, automotive, finance, fortune, weather, calendar, work, shopping, policy）+ 属性（label.zh/en, circleChannelEnabled, assistantDomainId, subCategories）
- [ ] T2: [metadata] 更新 `_shared/tag_taxonomy.yaml` 的 circle_tags，增加 `domain_ref` 字段指向 taxonomy
- [ ] T3: [codegen] make verify-metadata && make codegen && make codegen-app（生成 Go DomainTag 枚举 + Dart DomainTaxonomy 类）
- [ ] T4: [业务逻辑-端侧] 将 `circlesCategoryConfig` 从硬编码 Map 迁移为 `DomainTaxonomy.circleChannels()` 驱动
- [ ] T5: [业务逻辑-端侧] 更新 PA `domain_routing_catalog.json`，每个 domain 增加 `taxonomyRef` 字段
- [ ] T6: [测试] 契约测试：taxonomy codegen 产物与 YAML 定义一致性

### L3: resonance-discovery

- [ ] T7: [metadata] 更新 `contracts/metadata/social/circle/service.yaml`，为 ListCircles 增加 `recommendFor` 查询参数
- [ ] T8: [业务逻辑-云侧] 实现 ListCircles 推荐排序：优先调用 rec-model-service（scenario=circle_discovery），失败降级到 RuleScorer（weeklyActiveCount + category 匹配）
- [ ] T9: [业务逻辑-云侧] 实现 RuleScorer：按 weeklyActiveCount DESC + category IN (用户活跃领域) 排序
- [ ] T10: [业务逻辑-端侧] circles_page.dart「推荐」频道调用 ListCircles(recommendFor=userId)
- [ ] T11: [测试] 契约测试：推荐 API 入参/出参与 service.yaml 一致
- [ ] T12: [测试] 离线评测脚本：验证推荐相关度 ≥ 60%

### L3: circle-homepage-redesign（端云一体化交付）

#### 基础设施 & DTO

- [ ] T13: [codegen] 生成 Circle DTO（CircleDto / CircleMemberDto / CircleFileDto / CircleSectionConfigDto），字段与 fields.yaml 一致
- [ ] T14: [业务逻辑-端侧] CircleRepository 返回类型从 Map<String, dynamic> 迁移到 DTO
- [ ] T15: [业务逻辑-端侧] 创建 CircleState（不可变 + copyWith）+ CircleStateNotifier（ChangeNotifier）+ circleStateProvider.family(circleId)

#### CircleShell 布局重构（对标 ProfileShell）

- [ ] T16: [业务逻辑-端侧] 创建 CircleShell（NestedScrollView + SliverAppBar + 下拉弹簧拉伸 + 吸顶过渡）
- [ ] T17: [业务逻辑-端侧] 创建 CircleHeader（头像 + 圈名 + 描述 + 标签）
- [ ] T18: [业务逻辑-端侧] 创建 CircleStatsRow（成员/群聊/粉丝/获赞，可点击）
- [ ] T19: [业务逻辑-端侧] 创建 CircleActionBar（按 CircleRole 区分：owner/admin → 编辑+管理；member/visitor → 关注+加入）

#### "创作"Tab（对标 ProfileCreationsTab）

- [ ] T20: [业务逻辑-端侧] 将"作品"Tab 重命名为"创作"，复用 CreationSubTab 枚举（全部/微趣/图片/视频/文字）
- [ ] T21: [业务逻辑-端侧] 实现 SectionCreations widget：横向 SubTab + 按 contentType 过滤圈子内帖子 + 网格展示
- [ ] T22: [业务逻辑-端侧] 圈主/管理员模式：额外显示排序控件（最新/最热/精选）和视图切换（网格/列表）

#### 其他板块

- [ ] T23: [业务逻辑-端侧] 重构 SectionChat widget（群聊入口 + 未读标记）
- [ ] T24: [业务逻辑-端侧] 重构 SectionStorage widget（容量 + 文件列表）
- [ ] T25: [业务逻辑-端侧] 重构 SectionInteraction widget（互动流：点赞/评论）
- [ ] T26: [业务逻辑-端侧] 各板块独立 loading/error 降级（内联错误卡 + 重试）

#### Mock 依赖解除 & 整合

- [ ] T27: [业务逻辑-端侧] CircleDetailPage 移除 CircleMockData 直接 import，全部走 Provider
- [ ] T28: [业务逻辑-端侧] 重建 CircleDetailPage 使用 CircleShell + CircleStateNotifier

#### 云侧补全

- [ ] T29: [业务逻辑-云侧] GetCircleFeed 从 stub 升级为完整实现（cursor 分页 + sort + featured 置顶）
- [ ] T30: [测试-云侧] circle_feed_contract_test.go（分页、排序、空 feed、精选置顶）

#### 四层测试

- [ ] T31: [测试-端侧-T1] circle_repository_contract_test.dart 扩充：21 方法 + 异常场景 + Remote URL 断言
- [ ] T32: [测试-端侧-T1] circle_dto_contract_test.dart：DTO 字段与 fields.yaml 一致性
- [ ] T33: [测试-端侧-T2] Widget 测试：CircleShell / CircleHeader / CircleStatsRow / CircleActionBar / SectionCreations
- [ ] T34: [测试-端侧-T3] Journey 测试：加入退出 + 创作 Tab 切换过滤 + 文件操作
- [ ] T35: [门禁] verify_dart_semantic.py 对 ui/circle/ 零新增违规 + flutter analyze 零 error
- [ ] T36: [部署] integration 环境 seed-box 验证圈子核心 API 端到端可用

## 搁置任务

- [ ] 个性化板块偏好（重启条件：用户级配置需求明确）
- [ ] taxonomy 动态化 API 下发（重启条件：运营需频繁调整领域标签）

## 未来演进任务

- [ ] 圈子内 AI 创作助手（与 assistant 域深度集成）
- [ ] 自动内容总结 / 圈子日报生成
- [ ] 板块类型扩展协议（支持第三方板块插件）
