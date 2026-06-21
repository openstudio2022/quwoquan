# L3 Scenario: review-content-type

## 节点定位

- `L1_domain_service`: `discovery-content`
- `L2_business_capability`: `content-type-framework`
- `L3_story`: `review-content-type`

本场景在统一内容契约（单一 `Post` 聚合 + 单一只读 `ContentSurfaceView`）之上，引入**口碑（review）内容类型**。建模选型已冻结为 **方案 A：`ContentType` 新增枚举值 `review`**——口碑是「带评分 + 强 POI 实体绑定的内容类型」，复用现有 publish 写链路、推荐召回管线与统一展示模型；POI 维度的星级聚合作为**读侧投影/读模型**单独建模，不拆表、不新增第二套 model。

## 背景与动机

「交集」是产品北极星：用户因共同的地点/事物/标签产生连接。口碑（对 POI/景区/店铺/事物的评价）是交集最强的真实信号之一——它天然带 `entityRef`（POI）+ `tagRefs`（维度）+ 评分，既能进发现流被消费，又能沉淀为 POI 的口碑分。

若把口碑做成独立实体，会重新引入一套写链路、召回通道与展示模型，正是刚收敛掉的 R24 分叉债务。方案 A 让口碑作为 `Post` 的一个 `contentType`，最大化复用统一契约，新增的仅是评分字段族与 POI 聚合读模型。

## 目标用户与核心问题

- **写口碑的用户**：到访某 POI 后想留下评分 + 图文评价，并被同好看到、沉淀为该 POI 的口碑分。
- **看口碑的用户**：在发现流/POI 主页看到真实口碑与聚合星级，作为决策与交集连接依据。
- **核心问题**：让口碑以最小契约增量进入统一内容主链（发布/召回/展示/交集归因），同时提供可信的 POI 维度聚合（均分、计数、分布）。

## 范围（In Scope）

### F1. `ContentType` 新增枚举值 `review`
- `_shared/types.yaml` 的 `ContentType` 增加 `review`（值序：`[image, video, micro, article, review]`）。
- 端云 DTO/codegen 同步；`micro/image/video/article` 既有路径零行为变化。

### F2. 口碑字段族（条件必填）
- `rating`：整体评分，`int` 1–5，**当 `contentType==review` 时必填**，其余类型为空。
- `reviewAspects`：可选维度评分（如 环境/服务/性价比），`[]object`（`{aspectKey, score}`），缺省为空。
- POI 绑定复用既有 `primaryHomepageId/primaryHomepageType`（POI 主页）+ `entityRefs`（实体引用）+ `location/locationName`；**口碑要求至少绑定一个 POI（`primaryHomepageId` 必填）**。
- 图文正文复用 `body`/`mediaUrls`/`coverUrl`；标题 `title` 可选。

### F3. 口碑写链路（复用 publish，不新建端点）
- `CreatePost` / `UpdatePost`（draft）/ `PublishPost` 的 `writable_fields` 增加 `rating`、`reviewAspects`。
- 写校验：`contentType==review` 时 `rating∈[1,5]` 且 `primaryHomepageId` 非空；否则按既有内容校验。
- **一人一 POI 一评**：同一 `authorId` 对同一 `primaryHomepageId` 的有效（未删除）review 唯一；重复写入按「更新已有口碑」语义或拒绝（见 design 决策），由部分唯一索引保证。

### F4. POI 口碑聚合读模型（读侧投影）
- 新增读侧聚合：按 `primaryHomepageId`（POI）聚合其全部已发布 review 的 `ratingAverage` / `ratingCount` / `ratingDistribution[1..5]`。
- 聚合由 projector/读模型计算，**不在 `Post` 上写聚合字段**；POI 主页与发现流读取该聚合呈现星级。
- 删除/撤销口碑时聚合需补偿（重算或增量回滚）。

### F5. 统一展示接入（B2 冻结口径）
- 口碑在 `ContentSurfaceView` 上以 `contentType==review` 分支承载 `rating`/`reviewAspects`/POI 摘要，**不拆表、不新增第二套 model**，遵循 04-dart-polymorphism（按契约字段分支，禁 `is/as`）。

### F6. 召回与交集归因
- 口碑进入现有推荐召回管线（已消费 `tagRefs`/`entityRefs`/`contentType`/`location`）。
- 口碑的 `entityRefs`/`tagRefs` 参与 `IntersectionReason` 归因，POI 维度交集可还原。

## 验收映射（A1~An → 三层测试）

| 验收 | 描述 | 证据层 |
|---|---|---|
| A1 | `ContentType` 含 `review`，端云 DTO/codegen 一致，既有四类型零回归 | local_contract 契约 + local_contract |
| A2 | review 写校验：`rating∈[1,5]` 必填、`primaryHomepageId` 必填；非法被拒（结构化错误码） | local_contract 契约 + local_contract |
| A3 | 一人一 POI 一评：重复 review 按 design 决策（更新/拒绝），部分唯一索引生效 | local_contract + api_integration |
| A4 | POI 聚合读模型：均分/计数/分布正确；删除口碑后聚合补偿 | local_contract + api_integration |
| A5 | 统一展示：review 在 `ContentSurfaceView` 上 `contentType` 分支呈现评分/POI 摘要，四 surface 口径一致 | local_contract 投影 + local_contract |
| A6 | 召回与交集：review 进召回通道，`entityRefs/tagRefs` 交集归因可还原 | local_contract + api_integration |

## SLO / KPI

| 指标 | 门槛 |
|---|---|
| 口碑发布 P99 RT | 复用 publish 链路 SLO（≤ 既有 CreatePost P99） |
| POI 聚合读 P99 RT | ≤ 150ms（读模型/缓存命中） |
| 聚合一致性窗口 | 写后聚合可见 ≤ 5s（最终一致，projector 滞后窗口可观测） |
| 既有内容类型回归 | 0 |

## 权限边界与可见性

- 写：登录用户可对 POI 发布口碑；遵循统一内容可见性（`visibility`）与审核（`moderationStatus`）。
- 改：仅 draft 可改（复用 `UpdatePost`）；published 口碑不可变（与既有内容一致）。
- 删/撤销：作者可删除自己的口碑（复用 `DeletePost` 软删 + tombstone）；删除触发 POI 聚合补偿。
- POI 聚合为公开只读；个人口碑可见性受原内容 `visibility` 约束（仅自己可见的口碑不计入公开聚合）。

## 数据生命周期合同

- 创建：随 publish 落库，`contentType=review` + `rating` + POI 绑定。
- 编辑：draft 阶段可改 rating/aspects/正文；published 不可变。
- 删除/撤销：软删（`deletedAt`）+ tombstone；聚合即时补偿（重算或增量）。
- 保留：随 `Post` 生命周期；删除后不计入聚合，tombstone 用于 URL 提示。

## 覆盖矩阵（与既有 Story 关系）

- 与 `unified-presentation-model`：复用 `ContentSurfaceView`，仅加 `contentType==review` 分支，不新增 model。
- 与 `creation-mode-and-surface-ia-unification`：口碑发布入口归 content/entry 创作 IA（打标 + POI 选择，详见 B3）。
- 与 content `Post` 既有四类型：同表同 surface，零行为回归。

## 迁移 / 灰度 / 回滚

- 迁移：纯增量（新增枚举值 + 可空字段 + 部分唯一索引 + 读模型），向后兼容，无破坏性 schema 变更。
- 灰度：feature flag 控制口碑**发布入口曝光**与 POI 聚合展示；读路径对未知 `contentType` 安全降级。
- 回滚：关闭入口 flag 即停止新增口碑；已写入的 review 作为普通内容仍可读，聚合可停用。

## Out of Scope

- 不新建独立 `review` 实体 / repository / 端点（方案 A 否决 B）。
- 不在本轮做商家认领/官方回复/口碑运营后台。
- 不改 pageflip 受控文件。
- 创作侧打标 UI（tagRef + POI 选择）归 B3 `creation-tagging-ia`，本场景只保证 payload 注入契约就绪。

## 约束

- metadata-first：先改 `contracts/metadata/content/**` + `_shared/types.yaml`，再 `make verify-metadata` → codegen，再业务逻辑。
- 错误码经 `errors.yaml` codegen，不在业务代码硬编码口碑错误码/文案。
- 遵循 13-coding-discipline：R06 元数据驱动、R08 端云字段对齐、R24 单一 model、R04 去裸 Map。
- 统一展示分支遵循 04-dart-polymorphism（契约字段判别）。

## 设计决策（冻结）

> L3 故事的 design 细节并入本 spec（feature-tree 约定 L3 仅 `spec.md`+`acceptance.yaml`，design.md 属 L1/L2）。

### D1. 方案选型
- 选定 **A：`ContentType` 新增枚举值 `review`**；否决 B（独立实体），因 B 需再造写链路/召回/展示并最终仍要投影回 `ContentSurfaceView`，与 R24 收敛相悖。
- 硬约束：口碑特有语义（评分、POI 聚合、一人一 POI 一评）以「可空字段 + 条件校验 + 读侧投影」承载，不让 `Post`/`ContentSurfaceView` 膨胀出第二套结构。

### D2. metadata 增量
- `_shared/types.yaml`：`ContentType: [image, video, micro, article, review]`（末位追加，保序）。
- `content/post/fields.yaml`：`rating`(int, NULLABLE, recommend_feature)、`reviewAspects`([]object, NULLABLE)。
- `content/post/service.yaml`：`CreatePost`/`UpdatePost`/`PromotePostToWork` writable_fields 追加 `rating`、`reviewAspects`。
- POI 绑定复用 `primaryHomepageId`/`primaryHomepageType`/`entityRefs`/`location`，不新增 POI 字段。

### D3. 错误码（errors.yaml → codegen）
| code | 触发 |
|---|---|
| `CONTENT.USER.review_rating_required` | review 缺 rating 或越界 |
| `CONTENT.USER.review_poi_required` | review 缺 primaryHomepageId |
| `CONTENT.USER.review_duplicate_per_poi` | 同作者对同 POI 已有有效口碑 |

### D4. 存储与唯一约束（storage.yaml）
- `idx_posts_review_author_poi`：`{authorId:1, primaryHomepageId:1}`，`unique`，`partialFilterExpression: {contentType:"review", deletedAt:null}`。
- `idx_posts_review_poi`：`{primaryHomepageId:1, contentType:1, publishedAt:-1}`，`sparse`。

### D5. 一人一 POI 一评（与 published 不可变一致）
- 重复发布同 POI 口碑 → 拒绝（`duplicate_per_poi`）；改口碑需删除旧口碑（软删释放唯一槽）再发。
- draft 阶段可改 rating/aspects/正文；不引入 upsert 静默覆盖。

### D6. POI 口碑聚合读模型（读侧投影，不写 Post）
- 键 `primaryHomepageId`；量 `ratingAverage`/`ratingCount`/`ratingDistribution[1..5]`；仅统计 published+public+未删 review。
- projector/读模型计算（与 recommendation-projector 同层消费内容事件）；最终一致窗口 ≤5s 可观测；读 P99 ≤150ms。
- 删除/撤销触发增量回滚或重算；仅自己可见口碑不计入公开聚合；端侧经 entity/homepage 读路径取聚合，不在客户端自算。

### D7. 统一展示接入
- `ContentSurfaceView` 增加只读可选 `rating?`/`reviewAspects?`/`poiSummary?`，由 `ContentSurfaceViewMapper` 在 `contentType==review` 分支填充；四 surface 只读消费，分支用契约字段判别（禁 `is/as`）。

### D8. 实施顺序（slices：metadata → codegen → 业务逻辑 → 测试）
1. **S1 metadata**：types/fields/service/errors/storage → `make -C quwoquan_service verify-metadata`。
2. **S2 codegen**：`make codegen` + `make codegen-app`。
3. **S3 写校验**：review 写校验（rating/poi 必填、duplicate_per_poi）→ `make -C quwoquan_service test-contract`。
4. **S4 POI 聚合**：聚合读模型 + 删除补偿。
5. **S5 端侧分支**：`ContentSurfaceView` review 分支 + mapper。
6. **S6 召回/交集**：rating 进特征，entityRefs/tagRefs 交集归因覆盖 review。
7. **S7 四层测试**：`review_contract_test.go` / `review_aggregate_test.go` / `review_projection_contract_test.dart` → `gate_repo.sh --scope app` + `make gate-full`。
