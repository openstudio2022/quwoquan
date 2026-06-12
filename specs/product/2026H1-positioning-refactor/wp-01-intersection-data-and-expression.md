# WP1 · 交集事实数据源与表达升级（云侧主导）

> 树归属：`object-homepage-network/intersection-unified-experience`（L2）+ `discovery-content/feed-orchestration-recommendation`
> 影响 Journey：`content-discovery-to-consumption`、`message-social-connection`
> 验收意图：contract + SIT；测试证据：T1 / T3
> 交集定义真相源：`specs/product/intersection-definition-and-application.md`

## 1. 背景与现状

- 交集架构已成型：5 维闭集 + 证据组 kind（开放字符串）+ 云侧 G2 文案产出（端只读直出 `primaryText/secondaryText/connectionSummary`）。
- 交集的完整产品词典、七个母表达边界、关系语言规则与 standard kind / legacy alias 迁移规则，统一以下文档为准：`specs/product/intersection-definition-and-application.md`。本 WP 只负责把对应事实与展示字段落成实现。
- 云侧真实数据源在 `quwoquan_service/services/content-service/internal/infrastructure/recommendation/intersection_source.go`（526 行），目前产出「互相关注/共同圈子/同校/同游/你关注的人正在看」等；丰富表达主要靠 mock/fixture。
- 缺口（详见概念文档 §20.3 词表）：
  - 共同收藏（coFavorited）、共同讨论（coCommented）完全缺失；
  - `共同关注的人` 只有「互关」判断，无真实第三方共同关注集合计算；
  - 共同地点的 `followeeVisited/contactVisited` 仅存在于 mock；
  - 共同校友只有标签级「同校」（保持，校友图谱后置）。
- **商用风险**：Go 真实 source 产出的 reason 经常缺 `displayName/avatarUrl/primaryText`，而端侧 spotlight 过滤条件是「缺 primaryText 不进展示窗」→ beta/gamma 真实环境 spotlight 大量空窗。

## 2. 功能规格

### 2.1 七类表达全覆盖（事实优先）

按概念文档 §20.3 高层入口与 `specs/product/intersection-definition-and-application.md` 的完整词典逐项落地，全部为 `intersectionClass=fact`：

1. **共同关注的人**：基于 `follow_edges` 计算双方共同关注的第三方集合（互关边优先），产出标准 kind `sharedFollowees`（兼容 legacy alias `mutualFriend`）；`primaryText` 形如「N位共同关注的人」，`intersectionPoints` 可枚举到具体的人（头像/名字）。
2. **共同圈子**：既有 `sharedCircle` 计算保持，措辞统一「共同加入N个圈子」/「共同圈子」。
3. **共同兴趣**：标签交集（共享 Topic tagRef）升级为事实级表达，`primaryText` 形如「都关注AI产品」；与 affinity 概率推荐严格区分。
4. **共同地点**：新增 favorite/visit 行为与 geoTagRef 交集源，`coVisitedPlace`（双方都去过/标记过同一地点）与 `followeeVisited`（N位你关注的人去过，用于实体对象页）真实化。
5. **共同校友**：identity 维度「同校」事实保持（entity tagRef），措辞统一「N位校友在这里」/「同校校友」；不引入校友图谱。
6. **共同收藏**（新）：favorite 行为交集，`coFavorited`，「共同收藏」/「N位你关注的人收藏」。
7. **共同讨论**（新）：评论/讨论参与交集，`coCommented`，「共同讨论过」/「都参与了××讨论」。

### 2.2 文案与展示字段补全（空窗治理）

- `hydrateDisplayLanguage` 按 §20.3 词表统一产出 `primaryText`（结论句）与 `secondaryText`；任何进入 spotlight 候选的 reason 必须 `primaryText` 与（人=avatarUrl，物=对象头图）完备。
- `displayName/avatarUrl` 在 source 层补全（从 user/circle/entity 读模型回填），不得下发空值进候选窗。
- 排序保持 `evidenceKindRank`（人>物>地>内容>兴趣fact>recommended），新 kind 插入相应锚强度位置：`mutualFriend`（人级最高）、`coFavorited/coCommented`（内容级）、`coVisitedPlace`（地点级）。

### 2.3 fixtures 与 seed

- contract fixtures（`contracts/metadata/content/test_fixtures/scenarios/`）补齐七类样本（每类至少 1 个 fact reason + 可枚举 points）。
- alpha/beta seed manifest（`contracts/metadata/_shared/test_fixtures/app_{alpha,beta}_seed_manifest.json`）登记对应种子，使 beta 人工验收与 gamma 自动化都能看到七类表达。

## 3. 周边契约（冻结，不得变更）

- **不改** `intersection_reason.yaml` 字段形状与 5 维闭集；新 kind 只是证据组开放字符串的新值（可在 yaml description 补注记）。
- **不改** 交集 6 条 API 路由（`/v1/content/intersections/*`、`/v1/content/feed/intersections*`）。
- 端侧仅允许改 `quwoquan_app/lib/components/object_page/evidence_group.dart` 的 kind→排序/图标映射扩展——**注意该目录独占权在 WP3**：本包将所需映射（kind → rank/icon/维度短语）写成清单提交给 WP3 实现，或与 WP3 协调单文件例外（集成会话裁决，默认走清单交接）。

## 4. 改动范围

- `quwoquan_service/services/content-service/internal/infrastructure/recommendation/intersection_source.go`（新数据源 + 文案 + 字段补全）
- `quwoquan_service/services/content-service/internal/application/intersection_service.go`（kind 排序、保鲜、候选过滤）
- `quwoquan_service/services/content-service/internal/application/feed_intersection_mixer.go`（feed 理由混排消费新 kind）
- `contracts/metadata/content/test_fixtures/**`、`_shared/test_fixtures/app_{alpha,beta}_seed_manifest.json`
- `contracts/metadata/recommendation/rec_model/projections/intersection_reason.yaml`（仅 description 注记词表）
- 新增 Go 单测 / contract 测试

## 5. 准出要求

1. T1：contract 测试断言七类 kind 均能产出，且 `primaryText` 符合 §20.3 高层措辞与 `specs/product/intersection-definition-and-application.md` 的词典口径，`intersectionPoints` 非空可枚举。
2. T1：spotlight 候选完备性测试——进入候选窗的 reason `primaryText != '' && (avatarUrl != '' || objectKind 非 person 有头图)`。
3. T3：gamma 环境真实 API（`/v1/content/intersections/summary` 与 `/v1/content/feed/intersections`）返回 ≥5 类事实表达；spotlight 候选非空。
4. `bash agent_ops/gate/gate_repo.sh --scope service` 与 `--scope app` 全绿；`make verify-metadata` 绿。
5. 不得出现端侧本地拼装文案的回归（G2 契约测试保持绿）。

## 6. 验收标准（GWT 样例）

- Given 用户 A 与用户 B 都收藏过同一篇文章，When A 拉取 B 的交集 summary，Then 返回 `coFavorited` 证据组、`primaryText` 为「共同收藏」口径、points 含该文章。
- Given A 与 B 有 4 个共同关注的第三方用户，When 拉取交集，Then 返回标准 kind `sharedFollowees`（可兼容 legacy alias `mutualFriend`）、`primaryText=「4位共同关注的人」`、points 为 4 个具体用户。
- Given gamma 环境 seed 数据，When 拉取推荐频道 feed intersections，Then 候选窗内每条 reason 的 primaryText/头像完备，spotlight 不空窗。
- Given 某 reason 为 affinity，Then 其 `confidenceLabel` 为克制文案且不使用七类事实措辞。
