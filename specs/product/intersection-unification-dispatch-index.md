# 交集统一规格 · 并行会话 Dispatch Index

> 真相源：`specs/product/intersection-definition-and-application.md` §17–§18
> 状态：2026-06 规格收口完成；实现会话按本索引并行推进
> 计划追踪：`docs/intersection-unification-content.execution.planning.md`

---

## 1. 六场景矩阵（实现分工）

| ID | 场景 | L3 Story | 主要触达路径 | P0 判据 | 负责会话 |
|---|---|---|---|---|---|
| S1 | 首页推荐 | `home-recommend-intersection-redesign` | `lib/ui/discovery/**` | feed/spotlight 单句 primaryText | Session-A |
| S2a | 他人主页 | `user-profile-intersection-redesign` | `lib/ui/user/widgets/profile_*` | 为什么推荐TA 列表入口 | Session-B1 |
| S2b | 我的主页 | `user-profile-intersection-redesign` | `lib/ui/user/widgets/my_*` | 我的连接/影响力 | Session-B2 |
| S3 | 实体主页 | `entity-homepage-intersection-redesign` | `lib/ui/entity/**` | 我的交集 + 影响力 | Session-C |
| S4 | 圈子主页 | `circle-homepage-intersection-redesign` | `lib/ui/circle/**` | 我的交集 + 影响力 | Session-D |
| S5 | 全局搜索 | `search-intersection-consumption` | `lib/ui/search/**` | 交集 Tab + connectionState | Session-E |
| 横切 | 交集句统一 | `intersection-sentence-unification` | `lib/components/**/intersection_*` | G2 门禁 + Chip 单句 | Session-X（先行） |

---

## 2. Metadata 契约收口清单（已完成于规格会话）

- [x] `intersection_reason.yaml`：删除 `displayText` / `label` / `sharedCount`（2026-06-15 真正落地 metadata + codegen，此前仅文档声明）
- [x] `circle_impact_item.yaml`：`displayText` → `primaryText`（与 author_impact_item 对称收口）
- [x] `object_intersection.yaml`：`sourceRef` + `primaryText`；删 `shortLabel` / `evidenceLabel`
- [x] `object_intersection_evidence.yaml`：`sourceRef`；删 `evidenceLabel`
- [x] `object_page_bundle.yaml`：仅 `intersectionReasons` 单通道
- [x] `search_contract.yaml` + `search_objects.yaml`：`connectionState` + `intersectionReason` 子集
- [x] `PostSearchItemView`：补 `connectionState` + `intersectionReason`
- [x] 产品/特性树/术语表 §18–§20 引用刷新

---

## 3. 并行实现 Acceptance Checklist（每会话出口）

每个实现会话合入前必须勾选：

### 3.1 通用（全部会话）

- [ ] `make verify-metadata` 绿
- [ ] `make codegen` + `make codegen-app` 绿（metadata 变更后）
- [ ] 端侧无 `displayText` / `label` / `shortLabel` / `evidenceLabel` 消费交集结论句
- [ ] 无 primaryText 不占位、不造假
- [ ] alpha mock/fixtures 已补对应场景样本
- [ ] T2 widget 测试覆盖本场景 primaryText 单句断言
- [ ] G2 静态扫描：无 EvidenceGroup 本地拼句

### 3.2 Session-X 横切（建议最先）

- [ ] `IntersectionReasonChip` 仅消费 `primaryText`（删除 displayText 回退）
- [ ] 紧凑 surface 严格单句；列表入口允许 secondaryText
- [ ] `verify_*` 门禁更新（如有）

### 3.3 Session-A（S1 首页）

- [ ] `intersection_spotlight_module.dart` 去双句堆叠
- [ ] feed 卡唯一交集句
- [ ] `home_intersection_multiform_feed_widget_test.dart` 绿

### 3.4 Session-B1 / B2（S2 主页）

- [ ] 他人：为什么推荐TA + AuthorImpact 去好友化
- [ ] 我的：MyIntersectionInbox → 我的连接
- [ ] profile shell widget tests 绿

### 3.5 Session-C / D（S3/S4 对象页）

- [ ] ObjectIntersectionSection 单一真相源
- [ ] 记录流 PostPreviewCard 单句
- [ ] tab/过滤/metadata label_key 对齐

### 3.6 Session-E（S5 搜索）

- [ ] search hit 消费 connectionState 分组
- [ ] 交集 Tab primaryText 只读
- [ ] `global_search_page` / `search_network_results_page` tests 绿

---

## 4. 云侧并行（WP1 子序列，非本索引 App 会话）

| 任务 | 负责 | 阻塞 |
|---|---|---|
| T1 kind 标准化 | WP1 云侧 | beta spotlight |
| T2 六类真实数据源 | WP1 云侧 | gamma 空窗 |
| T3 空窗治理 primaryText/avatar | WP1 云侧 | 真实环境 |
| T4 fixtures/mock kind 迁移 | WP1 端云 | 全场景 mock |

---

- [x] `author_impact_item.yaml`：`displayText` → `primaryText`
- [x] `object_intersection.yaml` / `object_intersection_evidence.yaml`：**已删除**（统一 IntersectionReason）
- [x] 搜索 **零过渡**：缺 connectionState 不展示交集 Tab
- [x] §19 算法闭环 spec：`intersection-algorithm-closure`

## 5. 用户决策项（已关闭 2026-06-15）

| 项 | 决策 |
|---|---|
| AuthorImpactItem | `primaryText` 单通道 |
| ObjectIntersection projection | **删除**，统一 IntersectionReason |
| 搜索 connectionState | **零过渡**，provider 未回灌则不展示 |
| 算法范围 | **本会话契约完备** + 实现会话落地 rec-model/fusion/explain |

---

## 6. v2 三层架构 · 五面应用定义（2026-06-18 新基线分工）

> 真相源：`intersection-definition-and-application.md` §21（端到端统一：采集 → 算法 → 投影）。
> 本轮交付端侧四槽视觉模型 + lifecycle 弱标 + 传播视图共享件 + Mock 原型；契约为「草案/未冻结」。
> 与第 1 节六场景一一对应（A=S2b、B=S2a、C=S3、D=S4、E=S1），五面是 v2 具象化展示口径。

### 6.1 五面 × 四槽/lifecycle/传播 应用矩阵（§21.5.4）

| 面 | 主表达 | 槽①类型图标 | 槽②句内头像 | 槽③对象封面 | 槽④lifecycle | 传播视图 | 落地路径 |
|---|---|---|---|---|---|---|---|
| A 我的主页 | 我的连接 + 我的影响力 | ✓ iconKey/dimension | ✓ 人名前 | ✓ 对象 | ✓ 分桶弱标(新/增强/重新活跃) | ✓ author_impact 路径节点 + 再传播 | `lib/ui/user/widgets/my_intersection_inbox_card.dart` / `author_impact_card.dart` |
| B 用户主页(他人) | 为什么推荐TA + TA的影响力 | ✓ | ✓ | ✓ | ✓ 证据组叠 | ○ TA 影响力 | `lib/components/object_page/intersection_entity.dart` / `object_page/**` |
| C 实体主页 | 我的交集 + 影响力 + 记录流单句 | ✓ | ○ | ✓ 封面缩略 | ○ | ✓ entity_impact | 复用 B 的 `IntersectionEntity` / ObjectIntersectionSection |
| D 圈子主页 | 我的交集 + 影响力 | ✓ | ✓ | ✓ | ○ | ✓ circle_impact 接统一三件套(解决 G4) | `lib/ui/circle/widgets/circle_shell_builders.dart` |
| E 首页 post | post 卡内单句 chip | ○ | ○ | — | 仅「新」红点 | — | post chip / `home_multi_form_feed`（紧凑面，不复活 spotlight） |

图例：✓ 本轮原型已接线；○ 数据具备时按同一组件渲染；— 该面不适用。

### 6.2 端侧共享件（A–E 唯一来源，禁各面分叉）

| 槽/视图 | 组件 | 真相源字段 |
|---|---|---|
| 槽① 类型图标 | `IntersectionTypeIcon` + `IntersectionIconResolver` | `iconKey` →（回退）`sourceRef` → `dimension` |
| 槽② 句内头像 | `InteractiveIntersectionText`（WidgetSpan 注入） | `IntersectionTextSpan.visual` |
| 槽③ 对象封面 | `IntersectionObjectCover` | `IntersectionReason.objectVisual` |
| 槽④ lifecycle 弱标 | `IntersectionLifecycleBadge` | `lifecycleState` / `strengthDelta` |
| 传播视图 | `IntersectionPropagationView` | `IntersectionPropagationPath` |
| 统一三件套(既有) | `InteractiveIntersectionText` / `IntersectionVisualCluster` / `IntersectionTargetNavigator` | `primarySpans` / `sampleVisuals` / `target` |

### 6.3 v2 出口自检（每面在正式 UI 落地会话补齐）

- [ ] 四槽组件只消费契约字段，禁页面硬编码 `switch(sourceRef)` 图标 / 本地拼结论句（G2）。
- [ ] `join(spans.text)==primaryText/briefText` 不变量在含槽②头像时仍成立（WidgetSpan 不贡献字符）。
- [ ] lifecycle 弱标不进结论句、不变蓝、不堆叠；紧凑面仅「新」。
- [ ] 传播视图只展示可证绝对计数 + 路径节点，禁百分比/漏斗/增长率；`reach/conversion` 不进 DTO。
- [ ] `coLiked`（赞）排序最末（T4）、禁请求期全量求交、`like` 图标仅无更高价值交集时露出。
- [ ] 端 widget 测试：`intersection_four_slot_primitives_test.dart` + `interactive_intersection_text_test.dart`（槽②不变量）绿。
