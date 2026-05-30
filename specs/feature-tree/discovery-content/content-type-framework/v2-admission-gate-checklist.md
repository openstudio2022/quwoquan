# V2 严格准入门清单（内容多形态统一 + 口碑 + 创作打标）

> 适用范围：本清单是 V2「内容多形态统一」开工（`/dev`）前的严格准入门，挂 L2 [content-type-framework](spec.md)。
> 硬规则：**V1 未决项必须先清零（Block A 全绿），且 V2 自身规格/metadata 冻结（Block B/C 全绿）+ 严格准入门（§Gate）全勾选 + 门禁无 BLOCKING，方可进入 V2 `/dev`。不允许任何未决项带入 V2。**
> 真相源：本文件只登记准入门与待清零事项；V2 规格冻结后以新建 L3 的 `spec.md/design.md/acceptance.yaml/plan.yaml` 为准，本文件不复制其内容。
> 状态图例：`[ ]` 未完成 / `[x]` 完成 / `[~]` 部分（需说明）。

---

## 0. 自检结论（V1 实际落地 vs 计划，截至本清单生成时）

| 维度 | 结论 | 准入影响 |
|---|---|---|
| feed presentation + 交集线索（V1-A/E 数据通路） | 强类型贯通就绪 | 解除 |
| 频道端侧消费（V1-B/C 核心验收） | **已达成**：strip/`_buildBody` 消费 `homeChannels`（默认 7 频道）+ 远程覆盖合并，模板路由化 | **A1 CLEARED** |
| 统一对象推荐卡（V1-D） | **已交付**：`UnifiedObjectCard` 四类同卡语言；rail 以对象卡承载；`onReasonTap` 按 metadata 路由接通 | **A2 CLEARED** |
| 对象卡交集行动回流（V1-F） | **已闭环**：对象卡行动按钮 `trackFollow(dimension/tagRefs)`；详情透传 position；UI 触发点测试就绪 | **A3 CLEARED** |
| 内容卡理由位口径一致（V1-E） | **已统一**：抽 `IntersectionReasonChip`（单一 primaryText 口径）；feed/沉浸/详情同源接入 | **A4 CLEARED** |
| 展示层模型一致性（feed/immersive/detail/share） | 四套消费模型不一致 | B2 债务（R24） |
| 口碑内容类型 metadata | 未设计 | C1 BLOCK |
| 创作侧打标（tagRef 打标 UI + payload 注入） | 缺失（wire 已支持，属「接通」） | B3 缺口 |
| tagRef 真相源 `publish/v1/tags` | 未发布（`quwoquan_data/publish/` 不存在） | C2 依赖 |

---

## Block A — V1 未决清零（P0，进入 V2 的硬前置，必须 100% 完成）

### A1. 频道端侧统一消费 `homeChannels`（含远程覆盖、去硬编码、去漂移）
- [x] **频道集合决策（产品决策，先定）**：结论 = 把现有 7 频道（following/recommend/campus/travel/photography/tech/car）全部纳入 `ui_config.home_channels` 默认集，统一由运营配置管理。
- [x] `home_primary_tab_strip.dart` 去 `homeTabIds` 硬编码，改消费 `homeChannelsProvider`（`ContentUIConfig.homeChannels` 默认 + `/v1/config/app` 远程覆盖合并，按 order 排序）；`recommendedTabId` 对齐 `recommend`。
- [x] `home_page._buildBody` 去硬编码 switch，按频道 `template`（`single_column_relations` / `masonry_recommend` / `intersection_rail_masonry`）路由 `MomentSocialFeed`；`feedTabId` 与 `channel.id` 对齐，消除 `recommend → 'moment'` 漂移。
- [x] 远程覆盖链路接通：`HomeChannelsRemoteOverride.fromAppConfigRoot` 解析 `/v1/config/app` → 合并进 `ContentRuntimeConfigState.homeChannels` → 失败/缺省回退 meta 默认。
- [x] 验收：频道增删改/调序仅改云侧配置即在端生效（不发版）；拉取失败回退默认；端默认与远程同 schema。
- [x] 测试：频道 provider 合并/回退单测（`home_channels_remote_override_test`）；strip/`_buildBody` 模板路由 widget 测试（`home_channel_template_routing_test`）；`post_ui_config_contract_test` 7 频道契约。

### A2. 统一对象推荐卡（人/地点事物/圈子/组织四类同一卡语言）
- [x] 新建 `UnifiedObjectCard` 组件，四类共用同一卡语言；只读消费 `IntersectionReason.displayText/sharedCount/actionType/actionTargetId`，动词仅映射 `actionType`，禁本地拼交集句（G2）。
- [x] 今日交集 rail 以 `UnifiedObjectCard` 承载对象理由；`onReasonTap` 接通：按 `relationKind` 路由 `userProfile/circleDetail/homepageDetail`（route 来自 `AppRoutePaths` codegen，不硬编码 path）。
- [x] 数据走 contract-seed Mock（mock 理由补 relationKind/actionType/actionTargetId，覆盖人/地点/圈子/组织）。
- [x] 测试：四类对象卡 widget 渲染 + 无来源不展示 + 双主题 + 热区 ≥ 44（`unified_object_card_widget_test`）；rail 对象卡 + 导航测试（`home_intersection_object_nav_test`）。

### A3. 交集行动回流接通（V1-F 闭环）
- [x] 对象卡交集行动（关注/加入/加好友）调用 `trackFollow(... intersectionDimension, intersectionTagRefs)` 回流（`home_page._handleIntersectionObjectAction`）。
- [x] 跳详情透传 `feedRequestId/referralSource/position`：`MediaViewerExtra`/`ArticleDetailPageRouteExtra` 补 `position` 字段，click 上报带 feed 序号。
- [x] 测试：对象卡行动回流带 dimension+tagRefs 的 UI 触发点测试（`home_intersection_action_attribution_test`）。

### A4. 内容卡交集理由位口径一致
- [x] 抽共享 `IntersectionReasonChip`（`primaryText` 单一口径真相源）；feed（`MomentSocialFeed`）、沉浸 viewer（`works_immersive_viewer` caption）、内容详情页（`article_detail_page` header）同源接入，`displayText` 只读、无来源不展示。
- [x] 测试：`intersection_reason_chip_widget_test`（primaryText 口径 + fromReasons + 双主题）；`works_immersive_viewer_widget_test` 沉浸 caption 接入断言；feed 既有用例守护。
- [~] 转发卡：当前仓库无独立「转发/引用卡」组件；共享 chip 口径已就绪，待该 surface 落地时直接采用（不阻断 A4 出口）。

### A 出口条件
- [x] Block A 全部完成；`bash agent_ops/gate/gate_repo.sh --scope app` 全绿（含 `verify-app-page-horizontal-quality`、`verify_dart_semantic`、`verify_ui_mock_isolation`）。

---

## Block D — V2 硬前置债务清零（P0，进入 V2 的硬前置，必须 100% 完成）

> 决策口径（用户冻结）：统一展示 model 作为**前置债务清零**先收敛四套（非 V2 增量）；R03 超大文件强拆 + R02 接口拆分作为**硬前置**。
> 真相源：D1 统一 model 以新建 L3 [`unified-presentation-model`](unified-presentation-model/spec.md) 的四件套为准；D2/D3/D4 纯债务登记 [`CR-20260530-021`](../../../changelog/CR-20260530-021-v2-precondition-debt-cleanup.yaml)。
> 范围边界：仅 content/discovery 域；非相关域债务、`article_read_only_book_deck.dart`(pageflip 专管)、编辑器类大文件、`create_page.dart` 不纳入本轮，不阻断出口。

### D1. 统一展示 model（R24，收敛四套）
- [x] 新建单一只读 presentation model `ContentSurfaceView` + 单一 `ContentSurfaceViewMapper`，覆盖 micro/image/video/article 四媒体类型（`lib/ui/content/models/`）；T1 投影契约 6 例全绿。
- [x] 迁移 flag `unified_surface_view`（metadata + codegen 默认 false，runtime 可覆盖）双读机制就绪、可单独回退。
- [x] **share surface** 经统一 model 接入（`ContentShareTemplateBuilder.build(surfaceView:)`），四类型与旧投影同源 parity 测试全绿。
- [ ] **feed**（`moment_social_feed` 卡片体）接入统一 model（与 D3 拆分同批）。
- [ ] **detail**（`article_detail_page`/`PostSummaryView`）接入统一 model。
- [ ] **immersive**（`works_immersive_viewer` 自拼 `Map`→`ArticleDetailView`）接入统一 model（受 pageflip 规则约束，与 D3 拆分同批，最后切）。
- [ ] 旧投影类（`PostSummaryView`/`_wireMapForPresentation`/share fallback）四 surface 全切并稳定后标 `@Deprecated`。

### D2. ContentRepository 接口拆分（R02）+ 去裸 Map（R04 GATE_BLOCK）
- [ ] 拆 `ContentRepository`（44 方法）为 ≤10 方法子接口：Read / Write / Reaction / Media / Comment / Config（Reaction 命名以避开既有窄接口 `ContentInteractionRepository`）。
- [ ] `discoveryPresentationWireForPost` 返回类型由 `Map<String,dynamic>?` 改为强类型（与 D1 对齐）。
- [ ] Mock/Remote 同步拆分（`implements` 子接口），`app_providers.dart` 注册；契约测试覆盖。

### D3. 超大文件强拆（R03，V2 必碰三件）
- [ ] `works_immersive_viewer.dart`(3030)、`discovery_page.dart`(2393)、`moment_social_feed.dart`(1692) 拆到每件 <500 行（不动 pageflip 受控文件）。
- [ ] 现有 widget 测试全绿无回归；像素/布局不变。

### D4. GATE_BLOCK 硬债清零
- [x] R17 空 catch `create_page_remote_helpers.dart:276` → 结构化 `developer.log` 降级；content/discovery 域已扫描无其余空 catch GATE_BLOCK。

### D 出口条件
- [ ] Block D 全部 `[x]`；`bash agent_ops/gate/gate_repo.sh --scope app`、`verify_dart_semantic`、`verify_ui_mock_isolation`、`verify-app-page-horizontal-quality` 全绿，无 BLOCKING。

---

## Block B — V2 三大冻结决策（P1，`/prd`+`/design` 必须给出结论）

### B1. 口碑建模决策（BLOCK metadata）
- [ ] 选型冻结：口碑为 `_shared/types.yaml` 的 `ContentType` 新增枚举值，**还是**独立 `review` 实体绑定 entity/homepage(POI)。
- [ ] 二选一各自的写入主链、推荐召回通道、与 POI/entity 绑定、权限边界。
- [ ] 数据生命周期合同：创建/编辑/删除/撤销时效、保留策略。
- [ ] `metadata → make verify-metadata → make codegen/codegen-app`，不在业务代码硬编码口碑类型/字段/错误码。

### B2. 展示 model 统一方案（债务 R24，收敛单一 presentation model）
- 统一 presentation model（收敛四套：feed 裸 DTO / immersive DTO+本地自拼 / detail `PostSummaryView` / share 独立模板）已下沉为 **Block D · D1 硬前置**，由 L3 [`unified-presentation-model`](unified-presentation-model/spec.md) 落地；本项不再单列冻结决策。
- [ ] 本项 V2 增量仅冻结「口碑类型在统一 model 上的接入」：随 B1 选型，以 `contentType` 分支接入 `ContentSurfaceView`，不拆表、不新增第二套 model。

### B3. 创作打标 IA（缺口：打标 UI + payload 注入）
- [ ] 创作侧 tagRef 打标 UI 入口、选择范围（首发标签子集）、IA 归属（content/entry）。
- [ ] `buildCreatePostPayloadMap` / `PublishSettings.toPayloadFields()` 注入路径制 tagRef，端到端接通（wire 已支持）。
- [ ] 打标 → 内容 tagRefs → 交集 `IntersectionReason.tagRefs` 归因可还原。

---

## Block C — 依赖与商用/环境前置（冻结时同步确认）

- [ ] **C1 口碑 metadata 设计完成**并通过 `make verify-metadata` + codegen。
- [ ] **C2 tagRef 真相源 `publish/v1/tags` 发布**；确认 V2 首发标签子集覆盖（对照 `_shared/tag_ref_migration.yaml` 的 deferred 项）。
- [ ] benchmark / SLO·KPI / 弱网·并发·容量目标。
- [ ] 权限边界、可见性、删除撤销时效（口碑、私密内容）。
- [ ] 覆盖矩阵与优先级（与既有 Story 冲突在 `spec.md` 先声明）。
- [ ] 迁移灰度回滚（feature flag + 观测 + 回滚演练）。
- [ ] `path / operation / surface / route / decoder context` 唯一真相源（metadata），UI/Router 不维护第二套规则表。
- [ ] env-seed：`contracts/metadata/**/test_fixtures` + `app_{alpha,beta,gamma}_seed_manifest.json` 先补，再实现 alpha mock / beta·gamma remote。

---

## Gate — 严格准入门（全部满足方可触发 V2 `/dev`）

1. [x] **Block A 全绿**（V1 无任何未决项；A 出口条件门禁通过）。
2. [ ] **Block B 三决策冻结**：B1/B2/B3 均有明确结论并落 `spec.md/design.md`。
3. [ ] **Block C 依赖与前置全绿**：C1 口碑 metadata + C2 tagRef 真相源发布 + 商用/env-seed 前置确认。
4. [ ] V2 自身 `spec.md + acceptance.yaml + design.md + plan.yaml + CR` 冻结。
5. [ ] `make gate-full`（或等价全量门禁）无 BLOCKING。

> 任一未勾选 → 维持「不可开工」，回到对应 Block 补齐。**严禁以「先进 V2 再补」方式带入未决项。**

---

## 挂载与执行顺序

- 挂载：V2 在 L2 [content-type-framework](spec.md) 下**新建 L3**（如 `unified-presentation-model` / `review-content-type` / `creation-tagging-ia`），不新建平行 L2。
- 顺序：**Block A 清零（P0）** → Block B `/prd`+`/design` 冻结（含 A1 频道集合决策已定为前提）→ Block C 口碑 metadata + tagRef 发布 → Gate 全绿 → V2 `/dev`。
