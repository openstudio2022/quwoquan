# 交集契约冻结 checklist（Phase 0 → A–E 会话开工自检表）

> 配套真相源：[`intersection-definition-and-application.md`](intersection-definition-and-application.md) §20。
> 本表是「交集落地总路标」5 个独立会话（A 我的主页 / B 用户主页 / C 圈子主页 / D 实体主页 /
> E 首页推荐页）的开工基线。Phase 0 已冻结以下契约 + 约束，会话内**禁止**再改这些真相源结构
> （只消费，不重定义；如需扩展先回 Phase 0 流程）。

## 1. 冻结字段（端云单通道，禁止恢复第二通道）

- `IntersectionReason`：结论句唯一来源 `primaryText`；副句仅列表入口用 `secondaryText`；
  快照/追踪 id 唯一字段 `pointSummarySnapshotId`（**已删** `recommendationTraceId` 字段 + 别名）。
- `IntersectionPoint`：证据组结构化字段 `count / sampleText / sampleAvatarUrls / label / displayText` 唯一来源（端只读直出，禁本地拼结论句）。
- `IntersectionDimensionTally`：`briefText`（动态简报）+ `subtitleText`（证据摘要），端云已对齐。
- `IntersectionInboxSummary`：我的主页聚合，最多 3 维度可展开。
- kind（`sourceRef`）：机读真相源 `intersection_kind_registry.yaml`（27 kinds，含 valueTier/computability/...）。
- **统一交互子契约（§20.7，A–E 横切复用值对象）**：`IntersectionTarget`(objectId/objectKind/routeId) /
  `IntersectionTextSpan`(text/role/target) / `IntersectionVisual`(assetKind/imageUrl/displayName/target)。
  各 read_model 只附加旁挂：reason/impact 用 `primarySpans`、tally 用 `briefSpans`，证据样本统一 `sampleVisuals`。
  单通道不变量：`join(spans.text)==primaryText/briefText`（契约测试强制）；降级链 spans → primaryText → 隐藏。

## 2. 已删除项（零兼容，会话内不得引用）

- 端侧 `IntersectionReason.recommendationTraceId`（已收敛入 `pointSummarySnapshotId`）。
- reason 级 `displayText/label/sharedCount`（contract 已删；端 DTO 无此字段）。
- `ObjectIntersection` 独立 projection（对象页统一 `List<IntersectionReason>` + `IntersectionPoint`）。

## 3. 各 surface 数据 operation 与组件（会话归属）

| 会话 | surface | 数据 operation | 关键组件 |
|---|---|---|---|
| A | 我的主页 | `GetMyIntersectionSummary` / `ListMyIntersections` / `MarkIntersectionsVisited` | 我的连接 / 我的影响力 / 我的交集 inbox |
| B | 用户主页（他人/我的） | `GetObjectIntersections`(objectType=user) | 「为什么推荐TA」列表 + `IntersectionReasonChip` |
| C | 圈子主页 | `GetObjectIntersections`(objectType=circle) | 圈子交集列表 + 记录流单句 |
| D | 实体主页 | `GetObjectIntersections`(objectType=entity/homepage) | ObjectIntersectionSection + 记录流单句 |
| E | 首页推荐页 | （post 内附着，**删 spotlight 独立 API**） | post 内 `intersection_reason_chip`；移除 `intersection_spotlight_module` |

## 4. 全局 UI 约束（A–E 强制，详见 §20.4 / §20.7）

- [ ] 主谓宾一句话、先人后事；称谓统一「你们」。
- [ ] 交集句一律走 `primarySpans`（reason/impact）/ `briefSpans`（tally）+ **统一渲染器 `InteractiveIntersectionText`**；spans 缺省降级 `primaryText` 整行点击。
- [ ] 样本视觉一律走 `sampleVisuals` + **`IntersectionVisualCluster`**；按 `objectKind`/`assetKind` 选 avatar/circleAvatar/emblem/logo/coverImage，禁头像冒充非用户对象。
- [ ] 导航一律走 **`IntersectionTargetNavigator`**（消费 `IntersectionTarget.routeId`，禁 UI 硬编码 path）。
- [ ] R1/R2 kind 必带结构化 `sampleVisuals`。
- [ ] 名字/数字/整行点击优先级；下钻带 `intersectionId+sourceRef+dimension+objectKind+objectId`。
- [ ] 密度上限：feed chip ≤1 句、我的连接默认 3 条、对象页证据组一屏 ≤5 折叠。
- [ ] 降级链：spans → primaryText → 隐藏；具名样本 → 纯计数 → 维度母表达 → 隐藏；无 primaryText 不展示。

## 5. 入选门槛 / 红线（服务端，A–E 消费时假定已生效）

- [ ] 数量门槛：≥1 可枚举可点击样本。
- [ ] 置信门槛：affinity < confidenceThreshold 不产出；affinity 永远排 fact 之后并标「推荐」。
- [ ] 真实性红线：fact 数字派生自真实证据点，禁推荐分/热度伪造。
- [ ] 隐私门槛：`commonContact` 先过可见性。
- [ ] 空态：无合格交集隐藏整块，禁占位假交集。

## 6. Phase 0 未关闭项（会话需注意的边界）

| 项 | 状态 | 对会话的影响 |
|---|---|---|
| feed API 删除（`GetFeedIntersections`/`ReportIntersectionExposure`） | 延后到**会话 E** | 会话 E 按 §20.6 清单删 API+spotlight UI，保留 `Feed()` 供 post-chip |
| Go reason 级 `Label/DisplayText/SharedCount` 移除（漂移 a） | 延后 | 不影响 A–E（端 DTO 已无）；属 Go 内部清理 |
| 4 operation `response_body` schema（漂移 e） | 延后 | 框架无该能力；端 Remote 已按 read_model 解析，不阻塞 |

## 7. 门禁

- `make verify`（含 `verify_intersection_kind_registry.py` 注册表↔Go 对齐）。
- `make codegen` / `make codegen-app`（端云产物与 metadata 一致）。
- `bash quwoquan_ops/gate/gate_repo.sh --scope app` / `--scope service`（受影响范围）。

## 8. v2 三层架构草案字段（**未冻结**，UI 原型评审通过后再冻结）

> 真相源 [`intersection-definition-and-application.md`](intersection-definition-and-application.md) §21；
> 这些字段本轮以「可迭代草案」形式 metadata-first 定义并 `codegen-app` 出端 DTO，供 Mock 原型消费，
> **允许随 A–E UI 原型反推调整**，定稿后并入第 1 节冻结清单。云侧本轮只生成结构、不实现真算。

- [ ] `intersection_kind_registry.yaml`：每 kind 增 `relationStrengthBase` / `interactionFrequencyKey` / `recencyHalfLifeDays` / `lifecycleApplicable` / `propagationRole`(source|bridge|sink|none) / `iconKey`；恢复 `coLiked`（active，§21.9 只翻赞不恢复收藏）。
- [ ] `intersection_reason.yaml`：增 `lifecycleState` / `previousStrength` / `strengthDelta` / `edgeWeight` / `iconKey` / `objectVisual`(IntersectionVisual?)。
- [ ] `intersection_text_span.yaml`：增 `visual`(IntersectionVisual?，槽②句内 inline 头像)；不变量仍 `join(spans.text)==primaryText`（WidgetSpan 不贡献字符）。
- [ ] `intersection_dimension_tally.yaml` / `intersection_inbox_summary.yaml`：增 `strengthenedCount` / `reactivatedCount`(+ summary `totalStrengthenedCount` / `totalReactivatedCount`) + `iconKey`。
- [ ] `author_impact_item.yaml`：增 `propagationPath` / `hopCount` / `secondarySpreadCount` / `iconKey`。
- [ ] `circle_impact_item.yaml`：补统一交互子契约（`impactId` / `primarySpans` / `sampleVisuals` / `countTarget` / `evidenceSnapshotId` / `countObjectKind`）+ `propagationPath` + `iconKey`（解决端 G4，与 author_impact 对称）。
- [ ] 新增 `intersection_propagation_path.yaml`（`pathKind` / `hopCount` / `secondarySpreadCount` / `summaryText` / `summaryTarget` / `nodes:[IntersectionVisual]`）。
- [ ] `policy.yaml` `intersection` 块：增 `graphWeights` / `lifecycleWeights` / `propagation` 配置位（数值真算后置，先给安全默认）。

### 8.1 端侧四槽视觉模型组件（§21.5.1，A–E 横切复用）

- 槽① 类型图标：`IntersectionTypeIcon` + `IntersectionIconResolver`（iconKey → sourceRef → dimension → 占位 降级链；禁页面硬编码 switch）。
- 槽② 句内 inline 头像：`InteractiveIntersectionText` 在 `IntersectionTextSpan.visual` 非空时注入 `WidgetSpan` 行内头像（不破坏文本不变量）。
- 槽③ 尾部对象封面：`IntersectionObjectCover`（消费 `IntersectionReason.objectVisual`，无图回退类型占位，可叠槽④ overlay）。
- 槽④ lifecycle 弱标：`IntersectionLifecycleBadge`（new→红点/「新」、strengthened→「增强 +N」、reactivated→「重新活跃」、stable/weakened→不渲染；不进结论句/不变蓝）。
- 传播视图：`IntersectionPropagationView`（消费 `IntersectionPropagationPath`，类型图标 + 云侧 `summaryText` + 路径节点簇 + 「再传播 N」；只展示可证绝对计数，禁百分比/漏斗）。
