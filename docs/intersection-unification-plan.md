# 交集统一规格收口 · 执行计划

> 最后更新：2026-06-15  
> Dispatch 索引：`specs/product/intersection-unification-dispatch-index.md`

## 规格收口阶段（本会话）

- [x] 查证圈子/实体/用户/搜索/首页最新代码与 metadata 现状
- [x] 刷新 `intersection-definition-and-application.md`（六场景矩阵、§18 G2/P0/P1、§19 架构愿景）
- [x] 刷新 `00_PRODUCT_CONCEPT_SYSTEM.md` §20、`00_GLOBAL_TERMINOLOGY.md` §18
- [x] 刷新 `2026H1-positioning-refactor/00-overview.md` + `wp-01` 字段冻结解除
- [x] metadata 契约破坏性收敛（intersection_reason / object_intersection / bundle / search / PostSearchItemView）
- [x] L2 `intersection-unified-experience` spec/design/acceptance
- [x] L3 stories 刷新 + 新增 `search-intersection-consumption`
- [x] global-search G2 过渡约束对齐
- [x] dispatch index + acceptance checklist
- [x] `tree_index.yaml` 登记 search-intersection-consumption
- [x] `make verify-metadata` 绿（quwoquan_service）
- [x] `make codegen` 绿
- [x] `make codegen-app` 绿（含 PostSearchItemView connectionState/intersectionReason）

## 验证证据

| 命令 | 结果 | 备注 |
|---|---|---|
| `make -C quwoquan_service verify-metadata` | ✅ PASS | 72 aggregates, 110 enums |
| `make -C quwoquan_service codegen` | ✅ PASS | |
| `make -C quwoquan_service codegen-app` | ✅ PASS | 含 codegen 模板补 PostSearchItemView 字段 |

## 契约真正落地补订（2026-06-15 续 · 规格会话补完）

> 背景：dispatch §2 此前把「intersection_reason 删 displayText/label/sharedCount」标记为已完成，但 metadata
> 实际未删（字段、`displayText` 的「兼容展示文案」description 仍在）。本轮真正落地零兼容收口。

- [x] `intersection_reason.yaml`：物理删除 `displayText` / `label` / `sharedCount` 三字段 + description 补零兼容收口说明
- [x] `circle_impact_item.yaml`：`displayText` → `primaryText`（与 author_impact_item 对称，影响结论句单通道）；§18.1 收口表补此行
- [x] `author_impact_summary.yaml` / `circle_impact_summary.yaml`：description 取 `primaryText` 渲染（措辞对齐）
- [x] 删除残留 codegen 产物 `object_intersection.g.dart` / `object_intersection_evidence.g.dart`（yaml 已删，codegen 不清理孤儿）
- [x] `object_page_bundle.g.dart` 重生成（去 `intersections` 第二通道，仅 `intersectionReasons`）
- [x] `IntersectionPoint` 按 §18.1 收口表**保留**结构化字段（count/sampleText/sampleAvatarUrls/displayText/label 为云侧下发证据组名词，端只读，非 reason 级结论句）
- [x] `make verify-metadata` / `make codegen` / `make codegen-app` 复跑绿；生成 DTO 验证无 displayText/label/sharedCount

### 实现层移交并行会话（本会话 A 边界外）

契约收口导致端云实现层编译破损，按 dispatch §3（端侧 Session-A~E/X）/ §4（WP1 云侧）移交：

| 区域 | 破损/待办 | 归属 |
|---|---|---|
| `entity_repository.dart` | 删 `object_intersection*.g.dart` import | Session-C |
| `entity_object_page_bundle_mock.dart` | 删 `intersections:` + `_mockObjectIntersections`；mock 构造去 `label/sharedCount/displayText`，改 `primaryText` | Session-C |
| `evidence_group.dart` | `fromReason` fallback 去 `reason.displayText/label/sharedCount`，改 `primaryText/secondaryText` | Session-X |
| 六场景 UI | spotlight/feed/profile/entity/circle/search 去 `IntersectionReason.displayText/label/sharedCount` 消费 | Session-A~E |
| `circle_impact` 端侧 | `CircleImpactItem.displayText` → `primaryText` 消费 | Session-D |
| Go `IntersectionService` / `intersection_source.go` | 产出 `primaryText`（Explain 管线），去 displayText/label/sharedCount | WP1 云侧 |
| fixtures `content_scenarios*.json` / `entity_scenarios.json` | `displayText`→`primaryText`、kind 标准化迁移 | WP1 端云（§4 T4） |
| widget/contract 测试 | primaryText 单句断言、去 displayText 断言 | 各场景会话 |

---

## v2 三层架构新基线（2026-06-18 · 端到端统一：采集 → 算法 → 投影）

> 真相源 §21（`intersection-definition-and-application.md`）；CR `CR-20260618-045-intersection-three-layer-architecture-baseline`。
> 本轮重心：先讲清原理与端到端模型 → 补全端侧展示统一要求 → Mock 驱动敲定五面 UI 原型 → 性能/容量弹性；
> 契约以「草案/未冻结」metadata-first 定义并 `codegen-app` 出端 DTO；**云侧算法/采集/Remote 全部后置**。

### 本轮完成

- [x] §21 端到端统一模型原理（采集→算法→投影 + Graph/Lifecycle/Propagation/Projection 四属性 + 统一血缘）写入定义文档 + L2 spec/design。
- [x] §21.5 端侧展示统一要求：四槽视觉模型 + iconKey 语义闭集 + 每 surface 密度上限 + 降级链 + 五面矩阵。
- [x] §21.7 性能与容量弹性：冷热三档（热/温/冷）、采集弹性、降级开关分级、coLiked 高频红线；云侧物化/批算后置。
- [x] §21.9 赞红线翻转：`coLiked` 恢复为 T4 最低权重轻量交集（只翻赞、不恢复收藏）；kind registry `status=active`，门禁 `verify_intersection_kind_registry.py` 绿。
- [x] 草案契约（metadata-first）：kind_registry Graph 元数据 + reason/text_span/tally/inbox/author_impact/circle_impact lifecycle/iconKey/objectVisual/visual 字段 + 新增 `intersection_propagation_path.yaml` + policy `graphWeights/lifecycleWeights/propagation` 配置位。
- [x] `make verify-metadata` → `make codegen-app` 出端 DTO（Go 结构生成、逻辑不实现）。
- [x] 端侧四槽共享件：`IntersectionTypeIcon`/`IntersectionIconResolver`（槽①）、`InteractiveIntersectionText` 句内头像（槽②）、`IntersectionObjectCover`（槽③）、`IntersectionLifecycleBadge`（槽④）、`IntersectionPropagationView`（传播）。
- [x] circle_impact 卡接统一三件套 + 传播视图（解决端 G4）；my_home 四槽样板；`IntersectionEntity` 弱标真相源切换为服务端 `lifecycleState`。
- [x] Mock/fixture 补 lifecycle/传播/inline 头像样本（`content_scenarios.json` / `circle_repository_mock.dart` / `intersection_repository.dart`）。
- [x] 端 widget 测试：`intersection_four_slot_primitives_test.dart`（槽①/③/④ + 传播视图）+ `interactive_intersection_text_test.dart`（槽②不变量）+ 既有交集套件回归绿。
- [x] 文档同步：dispatch-index §6 五面应用定义、freeze-checklist §8 v2 草案字段、本计划、CR-045。

### 验证证据

| 命令 | 结果 | 备注 |
|---|---|---|
| `flutter test test/components/object_page/intersection_four_slot_primitives_test.dart …interactive_intersection_text_test.dart` | ✅ 27 passed | 四槽原子件 + 槽②不变量 |
| `flutter test`（author_impact / my_intersection_inbox / circle_shell / profile shell / journeys / intersection contract） | ✅ PASS | 受影响既有套件无回归 |

### 明确后置（本轮不做，里程碑：UI 原型评审通过 → 冻结契约 → 再开工）

- 云侧数据源采集实现、`intersection_service` / `intersection_source` / `author_impact_store` / `circle_service` 真算与填充。
- Remote 真实数据；Lifecycle 状态机（需过往强度时间序列）/ 多跳 Propagation / Graph 加权真算 / Selection 数值化。
- `coLiked` 预投影/采样（禁请求期全量求交）。
- 风险登记见 `docs/outstanding_risks_backlog.md`（经用户确认后）。
