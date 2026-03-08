# L2 圈子体验重构 — 设计方案

## 设计动因

解决 spec.md 中 R1 全部约束：领域标签孤立、发现效率低、圈子主页固化。本 L2 涵盖三个 L3：领域标签对齐、同频发现、主页重设计。

## 上游输入评审

- spec.md R1.1~R1.4 清晰，acceptance A3/A4/A9 可测。
- 依赖：`_shared/tag_taxonomy.yaml`（已有 circle_tags）、PA `domain_routing_catalog.json`（15 域）、`rec-model-service`（circle_discovery 场景已定义）。
- 无阻断项。

## 对标输入分析

| 对标 | 借鉴点 | 适用边界 |
|------|--------|----------|
| 小红书「话题/圈子」| 兴趣标签驱动推荐、二级分类 | 标签体系参考，不做电商 |
| Discord「Server Discovery」| 分类 + 推荐 + 搜索联合发现 | 发现机制参考 |
| 今日头条「频道管理」| 频道增删拖拽排序、分区推荐 | 已有 circles-channel-management-panel 特性 |

## 方案对比

### L3-1: domain-taxonomy-alignment

**方案 A（选定）**：`contracts/metadata/_shared/domain_taxonomy.yaml`

定义 16 个核心领域 ID，每个领域包含：id、label.zh/en、description、mode（content/service/tool）、circleChannelEnabled（是否作为圈子频道）、assistantDomainId（对应的助理域 ID）、priority、subCategories。codegen 生成 Go `DomainTag` 枚举 + Dart `DomainTaxonomy` 类。

圈子频道配置从硬编码 `circlesCategoryConfig` Map 迁移为 `DomainTaxonomy.circleChannels()` 查询。

PA `domain_routing_catalog.json` 中 domainId 映射到 taxonomy 的 assistantDomainId，保持 PA 内部路由逻辑不变。

**方案 B（备选）**：圈子侧独立配置 + 映射表。不选，理由见 L1 design.md D-1。

### L3-2: resonance-discovery

**方案 A（选定）**：rec-model-service 路由 + RuleScorer 降级

同频发现通过 `rec-model-service` 的 `circle_discovery` 场景实现：
1. 用户画像 `circle_participation` 维度（五维画像）聚合用户的领域权重向量。
2. 圈子 `recommend_feature` 字段（category, tags, memberCount, weeklyActiveCount）构成候选特征。
3. 推荐排序 = 兴趣匹配度（领域向量余弦相似度）× 活跃度衰减 × 热度因子。
4. 降级策略：rec-model-service 不可用时，Go CascadeScorer 回退到 RuleScorer（按 weeklyActiveCount + category 匹配）。

**方案 B（备选）**：纯规则排序。不选，因已有 rec-model 基础设施。

### L3-3: circle-homepage-redesign

**方案 A（选定）**：客户端板块注册 + 服务端开关（详见 L1 D-2）

Circle 实体新增 `sectionConfig` 字段（`List<CircleSectionConfig>`），每项含 sectionType（works/chat/storage/interaction/custom）、visible、order、customTitle。

端侧 `circle_detail_page.dart` 板块化：
```
CircleDetailPage
├── CircleHeader（封面 + 头像 + 描述 + 统计 + 操作按钮）
├── SectionTabBar（板块导航）
└── SectionContent（SliverList，按 sectionConfig 排序）
    ├── SectionWorks    ← 作品 feed（复用 content 域）
    ├── SectionChat     ← 群聊入口（最近消息 + 未读）
    ├── SectionStorage  ← 存储空间（文件列表）
    └── SectionInteraction ← 互动区（点赞/评论流）
```

每个 Section Widget 独立加载数据，内部 try/catch，失败显示内联错误卡 + 重试按钮。

圈子与助理联动：当用户在圈子详情页唤起助理时，PageContext 携带 `circleId` + `circleDomainId`（from taxonomy），助理路由层根据 `circleDomainId` 作为 pageTypeFallback 的候选域。

## 选型决策

| L3 | 选定方案 | 理由 |
|----|----------|------|
| domain-taxonomy-alignment | 集中式 taxonomy YAML | metadata-first、编译期安全、跨域一致 |
| resonance-discovery | rec-model + RuleScorer 降级 | 复用已有推荐基础设施 |
| circle-homepage-redesign | 客户端板块注册 + 服务端开关 | 移动端性能优先、渐进加载 |

## 关键设计决策

- **DK-1**：domain_taxonomy.yaml 放在 `_shared/` 而非 circle 域下，因为它是跨域共享资产。
- **DK-2**：圈子频道（Tab）与领域标签的关系是「领域标签是超集，圈子频道是其中 circleChannelEnabled=true 的子集」。
- **DK-3**：PA domainId 映射到 taxonomy 是 N:1 关系——多个 PA 域可映射到同一个 taxonomy 标签（如 travel_transport + travel_planning → travel）。
- **DK-4**：板块化不删除旧 3-Tab，而是将旧 Tab 映射到新 Section 类型：works → SectionWorks, interaction → SectionInteraction, lifestyle → SectionWorks（filter=lifestyle）。
- **DK-5**：同频发现的兴趣画像来自三个信号源：PA 交互领域频次（weight 0.4）、内容浏览标签（weight 0.3）、圈子参与历史（weight 0.3）。

## Story 与测试层映射

| L4 Story | T1 单元测试 | T2 集成测试 | T3 契约测试 | T4 E2E |
|----------|------------|------------|------------|--------|
| circle-domain-taxonomy-contract | taxonomy 枚举完整性、channel 过滤正确性 | 圈子+助理引用同一 taxonomy | codegen 产物与 YAML 一致 | — |
| circle-resonance-matching-contract | 排序算法单测（匹配度×热度）| rec-model API mock 集成 | — | 推荐相关度 ≥ 60% |
| circle-homepage-layout-contract | 板块渲染测试（各 Section Widget）| sectionConfig 加载 | — | 板块独立降级 |

## 未来演进

- **taxonomy 动态化**：当领域标签需运营动态调整时，从 YAML codegen 迁移为 API 下发。
- **个性化板块**：用户级板块偏好（不同于圈主配置的全局板块顺序）。
- **助理深度集成**：圈子内 AI 创作助手、自动内容总结、圈子日报生成。
