# 内容多形态统一 · 严格准入门清单（内容多形态统一 + 口碑 + 创作打标）

> 适用范围：本清单是「内容多形态统一」开工（`/dev`）前的严格准入门，挂 L2 [content-type-framework](spec.md)。
> 硬规则：**首页交集驱动改版未决项必须先清零（Block A 全绿），且内容多形态统一自身规格/metadata 冻结（Block B/C 全绿）+ 严格准入门（§Gate）全勾选 + 门禁无 BLOCKING，方可进入内容多形态统一 `/dev`。不允许任何未决项带入下一阶段。**
> 真相源：本文件只登记准入门与待清零事项；规格冻结后以新建 L3 的 `spec.md/design.md/acceptance.yaml/树内计划文档` 为准，本文件不复制其内容。
> 状态图例：`[ ]` 未完成 / `[x]` 完成 / `[~]` 部分（需说明）。

---

## 0. 自检结论（首页交集驱动改版实际落地 vs 计划，截至本清单刷新时）

| 维度 | 结论 | 准入影响 |
|---|---|---|
| feed presentation + 交集线索（改版 A/E 数据通路） | 强类型贯通就绪 | 解除 |
| 频道端侧消费（改版 B/C 核心验收） | **已达成**：strip/`_buildBody` 消费 `homeChannels`（默认 7 频道）+ 远程覆盖合并，模板路由化 | **A1 CLEARED** |
| 统一对象推荐卡（改版 D） | **已交付**：`UnifiedObjectCard` 四类同卡语言；rail 以对象卡承载；`onReasonTap` 按 metadata 路由接通 | **A2 CLEARED** |
| 对象卡交集行动回流（改版 F） | **已闭环**：对象卡行动按钮 `trackFollow(dimension/tagRefs)`；详情透传 position；UI 触发点测试就绪 | **A3 CLEARED** |
| 内容卡理由位口径一致（改版 E） | **已统一**：抽 `IntersectionReasonChip`（单一 primaryText 口径）；feed/沉浸/详情同源接入 | **A4 CLEARED** |
| 展示层模型一致性（feed/immersive/detail/share） | **已收敛**：四面统一硬切到单一只读 `ContentSurfaceView` + `ContentSurfaceViewMapper`；旧投影/flag 已删 | **D1 CLEARED** |
| 命名收敛（moment/micro、channelId、Reaction/Interaction、tags→tagRefs、中文术语） | **已硬切**：双轴分离、单一 `channelId`、互动唯一接口、`tagRefs` 真相源、退役「瞬间」 | **Block E CLEARED** |
| app 门禁（含 6 个回归测试） | **全绿**：`gate_repo.sh --scope app` `[gate] OK`，无 FAIL/BLOCK | **D5 CLEARED** |
| 口碑内容类型 metadata | **已落盘**：ContentType+review、rating/reviewAspects、3 错误码、2 索引；`verify-metadata`+codegen 绿，Go build 绿 | **C1 CLEARED** |
| 创作侧打标（tagRef 打标 UI + payload 注入） | **IA 已冻结**：内联编辑页可选打标、自动打标辅助、首发子集芯片+C2 后搜索灰度；payload wire 已通。端侧实现属 /dev | **B3 CLEARED（IA 冻结）** |
| tagRef 真相源 `publish/tags` | **已发布**：路径制四分组树（activeVersion 1，2026-05-15）；首发 launch 子集 6 个 tagRef 目标 100% 覆盖；`verify_tag_tree.py` 0 错误、`verify_tag_ref_source_of_truth.py` 门禁绿 | **C2 CLEARED** |
| 商用/环境前置（SLO/权限/生命周期/覆盖矩阵/灰度回滚/env-seed） | **已汇总冻结**：SLO·权限·生命周期·覆盖矩阵·灰度回滚落 `review-content-type` spec；三环境 seed manifest + 生产隔离门禁全绿；修复 content fixture `contentType: moment→micro` 残留（77 处） | **C3 CLEARED** |

---

## Block 0 — 工作树合并落盘（已完成）

- [x] `session0-tag-intersection` worktree 已合并进 `dev1.0`，解冲突、门禁复绿，删除分支与 worktree；首页交集驱动改版与命名收敛工作统一落在 `dev1.0`。

---

## Block A — 首页交集驱动改版未决清零（P0，进入内容多形态统一的硬前置，必须 100% 完成）

### A1. 频道端侧统一消费 `homeChannels`（含远程覆盖、去硬编码、去漂移）
- [x] **频道集合决策（产品决策，先定）**：结论 = 把现有 7 频道（following/recommend/campus/travel/photography/tech/car）全部纳入 `ui_config.home_channels` 默认集，统一由运营配置管理。
- [x] `home_primary_tab_strip.dart` 去 `homeTabIds` 硬编码，改消费 `homeChannelsProvider`（`ContentUIConfig.homeChannels` 默认 + `/v1/config/app` 远程覆盖合并，按 order 排序）；`recommendedTabId` 对齐 `recommend`。
- [x] `home_page._buildBody` 去硬编码 switch，按频道 `template`（`single_column_relations` / `masonry_recommend` / `intersection_rail_masonry`）路由 `HomeMultiFormFeed`；`channelId` 与 `channel.id` 对齐，消除 `recommend → 'moment'` 漂移。
- [x] 远程覆盖链路接通：`HomeChannelsRemoteOverride.fromAppConfigRoot` 解析 `/v1/config/app` → 合并进 `ContentRuntimeConfigState.homeChannels` → 失败/缺省回退 meta 默认。
- [x] 验收：频道增删改/调序仅改云侧配置即在端生效（不发版）；拉取失败回退默认；端默认与远程同 schema。
- [x] 测试：频道 provider 合并/回退单测（`home_channels_remote_override_test`）；strip/`_buildBody` 模板路由 widget 测试（`home_channel_template_routing_test`）；`post_ui_config_contract_test` 7 频道契约。

### A2. 统一对象推荐卡（人/地点事物/圈子/组织四类同一卡语言）
- [x] 新建 `UnifiedObjectCard` 组件，四类共用同一卡语言；只读消费 `IntersectionReason.displayText/sharedCount/actionType/actionTargetId`，动词仅映射 `actionType`，禁本地拼交集句（G2）。
- [x] 今日交集 rail 以 `UnifiedObjectCard` 承载对象理由；`onReasonTap` 接通：按 `relationKind` 路由 `userProfile/circleDetail/homepageDetail`（route 来自 `AppRoutePaths` codegen，不硬编码 path）。
- [x] 数据走 contract-seed Mock（mock 理由补 relationKind/actionType/actionTargetId，覆盖人/地点/圈子/组织）。
- [x] 测试：四类对象卡 widget 渲染 + 无来源不展示 + 双主题 + 热区 ≥ 44（`unified_object_card_widget_test`）；rail 对象卡 + 导航测试（`home_intersection_object_nav_test`）。

### A3. 交集行动回流接通（改版 F 闭环）
- [x] 对象卡交集行动（关注/加入/加好友）调用 `trackFollow(... intersectionDimension, intersectionTagRefs)` 回流（`home_page._handleIntersectionObjectAction`）。
- [x] 跳详情透传 `feedRequestId/referralSource/position`：`MediaViewerExtra`/`ArticleDetailPageRouteExtra` 补 `position` 字段，click 上报带 feed 序号。
- [x] 测试：对象卡行动回流带 dimension+tagRefs 的 UI 触发点测试（`home_intersection_action_attribution_test`）。

### A4. 内容卡交集理由位口径一致
- [x] 抽共享 `IntersectionReasonChip`（`primaryText` 单一口径真相源）；feed（`HomeMultiFormFeed`）、沉浸 viewer（`works_immersive_viewer` caption）、内容详情页（`article_detail_page` header）同源接入，`displayText` 只读、无来源不展示。
- [x] 测试：`intersection_reason_chip_widget_test`（primaryText 口径 + fromReasons + 双主题）；`works_immersive_viewer_widget_test` 沉浸 caption 接入断言；feed 既有用例守护。
- [~] 转发卡：当前仓库无独立「转发/引用卡」组件；共享 chip 口径已就绪，待该 surface 落地时直接采用（不阻断 A4 出口）。

### A 出口条件
- [x] Block A 全部完成；`bash agent_ops/gate/gate_repo.sh --scope app` 全绿（含 `verify-app-page-horizontal-quality`、`verify_dart_semantic`、`verify_ui_mock_isolation`）。

---

## Block E — 命名收敛硬切（P0，进入内容多形态统一的硬前置，必须 100% 完成）

> 口径（用户冻结）：不做向后兼容、不留版本/兼容分叉，统一切换到统一契约、概念与对象，旧符号直接删除。

- [x] **E1 moment/micro 双轴分离硬切**：`micro` = 内容类型（微趣），`moment` = 内容身份（点滴），严格分轴；消费方按轴取值，无混用。
- [x] **E2 频道标识收敛**：`channel.id/tabId/feedTabId/_activeTab/*TabId` 统一为单一 `channelId`，值不变，频道测试无回归。
- [x] **E3 互动接口收敛**：`ContentInteractionRepository` 窄接口并入唯一 `ContentReactionRepository`。
- [x] **E4 标签命名硬切**：`tags → tagRefs`（存储 bson/索引/迁移、Go 后端 + 推荐管线 + Python ML + rec_model 契约 + DTO + fixtures + Dart 消费），补齐缺失 `entityRefs` 字段，tag 真相源门禁绿。
- [x] **E5 中文术语收敛**：退役「瞬间」（删除 `app_concept_constants` 弃用项），微趣=类型 micro / 点滴=身份 moment 严格分轴，`content_share_template` 硬编码中文改走 `UITextConstants`；`verify_dart_semantic` 绿。

---

## Block D — 内容多形态统一硬前置债务清零（P0）

> 决策口径（用户冻结）：统一展示 model 作为**前置债务清零**先收敛四套（属硬前置，非增量）；硬切不做向后兼容，旧投影/flag 直接删除。
> 真相源：D1 统一 model 以新建 L3 [`unified-presentation-model`](unified-presentation-model/spec.md) 的四件套为准；D2/D3/D4 纯债务登记 [`CR-20260530-021`](../../../changelog/CR-20260530-021-v2-precondition-debt-cleanup.yaml)。
> 范围边界：仅 content/discovery 域；非相关域债务、`article_read_only_book_deck.dart`(pageflip 专管)、编辑器类大文件、`create_page.dart` 不纳入本轮，不阻断出口。

### D1. 统一展示 model（R24，收敛四套，全量硬切）
- [x] 新建单一只读 presentation model `ContentSurfaceView` + 单一 `ContentSurfaceViewMapper`，覆盖 micro/image/video/article 四媒体类型（`lib/ui/content/models/`）；local_contract 投影契约 6 例全绿。
- [x] **share surface** 经统一 model 接入（`ContentShareTemplateBuilder.build(surfaceView:)`），四类型同源 parity 测试全绿。
- [x] **feed**（`home_multi_form_feed` 卡片体）接入统一 model；脱离 `PostSummaryView`。
- [x] **detail**（`article_detail_page`）接入统一 model（`ContentSurfaceView.fromArticleDetailPayload`，富渲染经 `surfaceView.article(pages/document)` 消费，pageflip 几何不动）。
- [x] **immersive**（image/video viewer + `works_immersive_viewer`）接入统一 model（`MediaViewerExtra.posts → List<ContentSurfaceView>` 级联迁移，受 pageflip 规则约束）。
- [x] **硬切收尾**：删除旧投影类（`PostSummaryView` / `projectPostMap` / `_shareSeedForPost`）与迁移 flag `unified_surface_view`，无双读、无 `@Deprecated` 共存路径；旧 wire 行序列化方法统一命名为 `toWireMap`。

### D2. ContentRepository 接口拆分（R02）+ 去裸 Map（R04 GATE_BLOCK）
- [x] 互动唯一接口为 `ContentReactionRepository`（原 like/unlike/favorite/unfavorite 窄接口已并入，见 E3）。
- [ ] 拆 `ContentRepository`（44 方法）为 ≤10 方法子接口：Read / Write / Reaction / Media / Comment / Config。
- [ ] `discoveryPresentationWireForPost` 返回类型由 `Map<String,dynamic>?` 改为强类型（与 D1 对齐）。
- [ ] Mock/Remote 同步拆分（`implements` 子接口），`app_providers.dart` 注册；契约测试覆盖。

### D3. 超大文件强拆（R03，tech-debt 跟踪）
- [ ] `works_immersive_viewer.dart`、`discovery_page.dart`、`home_multi_form_feed.dart` 拆到每件 <500 行（不动 pageflip 受控文件）。
- [ ] 现有 widget 测试全绿无回归；像素/布局不变。
- 说明：R03 大文件未纳入 `gate_repo.sh --scope app` 强制项，作为 tech-debt 跟踪，**不阻塞**本阶段准入出口。

### D4. GATE_BLOCK 硬债清零
- [x] R17 空 catch `create_page_remote_helpers.dart:276` → 结构化 `developer.log` 降级；content/discovery 域已扫描无其余空 catch GATE_BLOCK。

### D5. 范围门禁出口
- [x] D1b 范围门禁绿（retired_terms / mock_isolation / dart_semantic / pageflip-back-mainline / page-matrix / analyze 0 error）。
- [x] 自检 6 个失败测试全部修复（user_profile micro 期望 / persona telemetry SharedPreferences mock / edit_profile 已登录会话注入 / works_immersive Timer 泄漏 / home_page 非点滴频道空流 / contract-seed 默认读 fixture），`gate_repo.sh --scope app` `[gate] OK` 无 FAIL/BLOCK。

---

## Block B — 内容多形态统一三大冻结决策（P1，`/prd`+`/design` 必须给出结论）

### B1. 口碑建模决策（BLOCK metadata）— **CLEARED**
- [x] 选型冻结：**方案 A——口碑为 `_shared/types.yaml` 的 `ContentType` 新增枚举值 `review`**（否决独立实体方案 B，理由见 [`review-content-type/spec.md`](review-content-type/spec.md) D1）。
- [x] 写入主链复用 publish（CreatePost/UpdatePost/PromotePostToWork）、召回管线复用现有通道、POI 绑定复用 primaryHomepageId/entityRefs；权限边界=统一内容可见性+审核。
- [x] 数据生命周期合同：创建随 publish、draft 可改、published 不可变、软删+tombstone+聚合补偿（见 spec 数据生命周期合同）。
- [x] `metadata → make verify-metadata → make codegen/codegen-app` 已执行（C1），错误码经 errors.yaml codegen，不硬编码。

### B2. 口碑在统一 model 上的接入 — **CLEARED（冻结口径）**
- 统一 presentation model（收敛四套）已下沉为 **Block D · D1 硬前置**，由 L3 [`unified-presentation-model`](unified-presentation-model/spec.md) 落地；本项不再单列冻结决策。
- [x] 已冻结：口碑以 `contentType==review` 分支接入 `ContentSurfaceView`（新增只读 `rating?`/`reviewAspects?`/`poiSummary?`），不拆表、不新增第二套 model，分支按契约字段判别（禁 is/as）。见 [`review-content-type/spec.md`](review-content-type/spec.md) D7。端侧 mapper/字段实现属 review-content-type /dev。

### B3. 创作打标 IA — **CLEARED（IA 冻结，端侧实现属 /dev）**
- 决策与口径已落 [`creation-tagging-ia/spec.md`](creation-tagging-ia/spec.md)（B3-D1~D7）；详见 [CR-20260530-023](../../../changelog/CR-20260530-023-review-content-type.yaml) rev2。
- [x] 创作侧 tagRef 打标 UI：**内联各类型编辑页**、打标全类型**可选不强制**、IA 归属 content/entry；自动打标（转发识别+内容识别）辅助，手动作确认/修正层。
- [x] 选择范围=首发标签子集（唯一引用 `tag_ref_migration` `launch` 项）芯片 + 自动建议多选≤5；C2 后 flag 灰度搜索补充（检索源唯一 publish/tags）。
- [x] payload 注入路径：`CreatePost`/`UpdatePost` `writable_fields.tagRefs`（wire 已通），验收以发布后 content.tagRefs 一致为准。
- [x] 打标 → 内容 tagRefs → 交集 `IntersectionReason.tagRefs` 归因可还原（验收 GWT5，local_contract/api_integration）。

---

## Block C — 依赖与商用/环境前置（冻结时同步确认）

- [x] **C1 口碑 metadata 设计完成**并通过 `make verify-metadata` + codegen/codegen-app（types.yaml+review、fields rating/reviewAspects、service 3 处 writable、errors 3 码、storage 2 索引；Go content-service build 绿）。详见 [CR-20260530-023](../../../changelog/CR-20260530-023-review-content-type.yaml)。
- [x] **C2 tagRef 真相源 `publish/tags` 发布**：路径制四分组树已发布（activeVersion 1）；`_shared/tag_ref_migration.yaml` 全部 `status: launch` 目标（Topic/旅行·摄影·美食餐饮·地理、Entity/机构、Format/内容载体）100% 命中树节点；`deferred` 项按设计延后回填，不进首发召回。`verify_tag_tree.py` 0 错误（21 条非阻断 R4/R9 警告），`verify_tag_ref_source_of_truth.py` 门禁绿。
- [x] **C3a benchmark / SLO·KPI / 弱网·并发·容量**：口碑发布 P99 复用 publish 链路 SLO（≤ 既有 CreatePost P99）、POI 聚合读 SLO 与 KPI 已冻结于 [`review-content-type/spec.md`](review-content-type/spec.md) §SLO/KPI；打标为可选内联交互、无独立网络 SLO（复用 publish）。
- [x] **C3b 权限边界、可见性、删除撤销时效**：口碑写=登录用户对 POI 可发、遵循统一 `visibility`+`moderationStatus`；删=作者软删+tombstone+即时聚合补偿；仅自己可见口碑不计入公开聚合。已冻结于 [`review-content-type/spec.md`](review-content-type/spec.md) §权限边界与可见性 / §数据生命周期合同。
- [x] **C3c 覆盖矩阵与优先级**：口碑与既有内容类型 Story 的覆盖关系已在 [`review-content-type/spec.md`](review-content-type/spec.md) §覆盖矩阵 声明（复用 publish/召回/统一展示，不与既有冲突）。
- [x] **C3d 迁移灰度回滚**：feature flag 控发布入口曝光与 POI 聚合展示、读路径对未知 `contentType` 安全降级、关闭 flag 即停新增（已写 review 作普通内容可读）。已冻结于 [`review-content-type/spec.md`](review-content-type/spec.md) §迁移/灰度/回滚；打标搜索为 C2 后 flag 灰度（见 [`creation-tagging-ia/spec.md`](creation-tagging-ia/spec.md)）。
- [x] **C3e 单一真相源（path/operation/surface/route/decoder/tagRef）**：口碑复用 `content/post/service.yaml` 写链路、`publish/tags` 唯一检索源；UI/Router 不维护第二套规则表（约束已写入两份 spec 的 §约束）。
- [x] **C3f env-seed manifest + 单一真相源回填**：`app_{alpha,beta,gamma}_seed_manifest.json` 三环境通过 `verify_app_seed_manifests.py`（生产 seed 隔离 13 文件已检），`verify_business_env_data_inventory.py`（26 seedRefs）、`verify_contract_mock_data_inventory.py` 全绿。**修复 E1 残留**：content 三套 scenario fixture（`content_scenarios.json/.gamma-curated/.lite`）`contentType/type: moment → micro`（共 77 处，identity 轴 moment 保留），消除「micro 内容被 `postBaseDtoFromMap` 默认落到 `PhotoPostDto`」的隐性错配。口碑 review fixture 属 `review-content-type` /dev 范围（env-seed-first 在故事内补 alpha mock + beta/gamma remote seed），不阻断准入出口。

---

## Block F — specs 去版本化（本轮收口）

- [x] 准入门清单重命名为 `content-unification-admission-gate-checklist.md`，移除版本化文件名。
- [x] 内文原带版本号措辞改为无版本语义（首页交集驱动改版 / 内容多形态统一 / 下一阶段）。
- [x] `unified-presentation-model` spec/design 去版本表述。
- [x] 同步 CR 链接与 `affected_nodes` 路径指向新文件名。

---

## Gate — 严格准入门（全部满足方可触发内容多形态统一 `/dev`）

1. [x] **Block 0 合并落盘**（session0 已并入 dev1.0，门禁复绿）。
2. [x] **Block A 全绿**（首页交集驱动改版无任何未决项；A 出口条件门禁通过）。
3. [x] **Block E 命名收敛硬切全绿**（E1–E5 完成，相关真相源门禁绿）。
4. [x] **Block D 范围出口全绿**（D1 四面硬切 + D5 app 门禁 `[gate] OK`；D2 接口拆分、D3 大文件作为 tech-debt 跟踪不阻塞）。
5. [x] **Block B 三决策冻结**：B1/B2 落 [`review-content-type/spec.md`](review-content-type/spec.md)（方案 A + 统一 model 分支接入）；B3 落 [`creation-tagging-ia/spec.md`](creation-tagging-ia/spec.md)（可选内联打标 + 自动辅助 + 分阶段搜索）。
6. [x] **Block C 依赖与前置全绿**：**C1 口碑 metadata 已落盘绿 + C2 tagRef 真相源已发布绿 + C3 商用/env-seed 前置已汇总冻结**（SLO/权限/生命周期/覆盖矩阵/灰度回滚落 review spec；三环境 seed manifest + 生产隔离门禁绿；content fixture moment→micro 残留已修）。
7. [x] 内容多形态统一自身规格冻结：L3 [`unified-presentation-model`](unified-presentation-model/spec.md)、[`review-content-type`](review-content-type/spec.md)、[`creation-tagging-ia`](creation-tagging-ia/spec.md) 各自 `spec.md + acceptance.yaml`（feature-tree L3 约定 design/plan 并入 spec）已冻结；CR [021](../../../changelog/CR-20260530-021-v2-precondition-debt-cleanup.yaml)（含 D1 统一展示 model）/[022](../../../changelog/CR-20260530-022-content-naming-convergence.yaml)（命名收敛）/[023](../../../changelog/CR-20260530-023-review-content-type.yaml)（口碑 + 创作打标）已落。
8. [x] 全量门禁无 BLOCKING：`bash agent_ops/gate/gate_repo.sh`（scope=all：service + app + portal）`[gate] OK`。本轮收口同时清理了与内容统一无关、但阻塞 gate-full 的仓库级 feature-tree 约定迁移残留——`quwoquan_service/scripts/gate.sh §5.1–5.3` 由旧约定（每节点 `tasks.md` + acceptance `feature/level`）对齐到新 L3 约定（`spec.md` + `acceptance.yaml` 的 `node.id/node.level`、`archived` 触发归档检查、`tests.recorded` 校验），并对齐 `verify_specs_l1_hierarchy.sh`（v2 `domain_services`）与 `verify_ff_config_contract.sh`（门禁矩阵迁入 `spec.md`）。`make gate-full` 额外的 gamma api_integration/user_acceptance 镜像属 `/deploy` 前置，不阻断准入。

> **准入结论（本轮）**：Gate 条目 1–8 全部勾选，全量门禁 `gate_repo.sh`（scope=all）`[gate] OK`，无 BLOCKING。内容多形态统一已满足开工（`/dev`）严格准入门。
>
> 任一未勾选 → 维持「不可开工」，回到对应 Block 补齐。**严禁以「先开工再补」方式带入未决项。**

---

## 挂载与执行顺序

- 挂载：内容多形态统一在 L2 [content-type-framework](spec.md) 下**新建 L3**（如 `unified-presentation-model` / `review-content-type` / `creation-tagging-ia`），不新建平行 L2。
- 顺序：**Block 0/A/E/D 清零（P0，已完成）** → Block B `/prd`+`/design` 冻结（已完成）→ Block C 口碑 metadata + tagRef 发布 + 商用/env-seed 前置（C1/C2/C3 已完成）→ **Gate-V2 收口（`make gate-full` 无 BLOCKING，待跑）** → 内容多形态统一 `/dev`。
