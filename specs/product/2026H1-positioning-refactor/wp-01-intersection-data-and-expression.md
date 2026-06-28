# WP1 · 交集事实数据源与表达升级（云侧主导）

> 树归属：`object-homepage-network/intersection-unified-experience`（L2）+ `discovery-content/feed-orchestration-recommendation`
> 影响 Journey：`content-discovery-to-consumption`、`message-social-connection`
> 验收意图：contract + SIT；测试证据：T1 / T3
> 交集定义真相源：`specs/product/intersection-definition-and-application.md`

## 1. 背景与现状

- 交集架构已成型：5 维闭集 + 证据组 kind（开放字符串）+ 云侧 G2 文案产出（端只读直出 `primaryText/secondaryText/connectionSummary`）。
- 交集的完整产品词典、六个母表达边界、关系语言规则与 **kind 唯一注册表**（无兼容别名），统一以下文档为准：`specs/product/intersection-definition-and-application.md`。本 WP 只负责把对应事实与展示字段落成实现。
- 云侧真实数据源在 `quwoquan_service/services/content-service/internal/infrastructure/recommendation/intersection_source.go`（526 行），目前产出「互相关注/共同圈子/同校/同游/你关注的人正在看」等；丰富表达主要靠 mock/fixture。
- 缺口（详见概念文档 §20.3 词表；状态截至基线修正会话收口）：
  - 共同讨论（coCommented）真实数据源缺失（**未完成 → T2**）；
  - `共同关注的人` 只有「互关」判断（旧 kind `mutualFriend`），无真实第三方共同关注集合计算，且 `intersection_source.go` 的 kind 名未迁移到标准名 `sharedFollowees`（**未完成 → T1/T2**）；
  - 共同地点的 `followeeVisited` 仅存在于 mock（旧名 `friendVisited/contactVisited`）（**未完成 → T2/T4**）；
  - 共同校友只有标签级「同校」（保持，校友图谱后置）；
  - Go `evidenceKindRank` 已迁移到注册表标准名（已落地，基线修正）；`intersection_source.go`、`intersection_service_test.go`、Dart mock 种子与 fixtures 仍残留 `mutualFriend / friendVisited / friendInCircle` 等已退场 kind 名，需一次性迁移，**不保留兼容解析**（**未完成 → T1/T4**）。
- **favorite 全链路退场**：**已落地（基线修正）**——契约（FavoritePost/UnfavoritePost、favoriteCount/favorited 字段、favorite 行为信号）、云侧（handler、推荐特征、指标）、端侧（UI 入口、Repository、本地状态）已全量退场，grep 零残留（仅点赞心形图标 `Icons.favorite*` 豁免）；长期价值推荐信号改用足迹侧已有行为（完读 / 复访 / 转发），不引入新行为类型。本项在准出 grep 中保留为**防回归**项。
- **足迹只读契约**：**已落地（基线修正）**——`GET /v1/content/footprint` 已登记 `service.yaml` 与 `ui_surfaces.yaml`（route `myFootprint`），Go handler/路由与端侧 codegen 产物已生成；但端侧消费闭环（Repository 三层 + 足迹列表页）尚无消费者（**未完成 → T5**）。
- **端侧 kind 折叠债**：**已落地（基线修正）**——Dart 侧 `evidenceKindRank` 已移除，`EvidenceGroup` kind 为开放字符串，文案全部云侧直出（G2 达标）。
- **商用风险**：Go 真实 source 产出的 reason 经常缺 `displayName/avatarUrl/primaryText`，而端侧 spotlight 过滤条件是「缺 primaryText 不进展示窗」→ beta/gamma 真实环境 spotlight 大量空窗（**未完成 → T3**）。

## 2. 功能规格

### 2.1 六类表达全覆盖（事实优先）

按概念文档 §20.3 高层入口与 `specs/product/intersection-definition-and-application.md` 的完整词典逐项落地，全部为 `intersectionClass=fact`；**kind 只用注册表标准名，不实现任何兼容别名解析**：

1. **共同关注的人**：基于 `follow_edges` 计算双方共同关注的第三方集合（互关边优先），产出标准 kind `sharedFollowees`（替换旧 `mutualFriend/commonFollow`）；`primaryText` 形如「N位共同关注的人」，`intersectionPoints` 可枚举到具体的人（头像/名字）。
2. **共同圈子**：既有 `sharedCircle` 计算保持，措辞统一「共同加入N个圈子」/「共同圈子」。
3. **共同兴趣**：标签交集（共享 Topic tagRef）升级为事实级表达，`primaryText` 形如「都关注AI产品」；与 affinity 概率推荐严格区分。
4. **共同地点**：访问行为与 geoTagRef 交集源，`coVisitedEntity`（双方都去过/标记过同一地点或对象）与 `followeeVisited`（N位你关注的人去过，用于实体对象页，替换旧 `friendVisited/contactVisited`）真实化。
5. **共同校友**：identity 维度「同校」事实保持（entity tagRef），措辞统一「N位校友在这里」/「同校校友」；不引入校友图谱。
6. **共同讨论**（新）：评论/讨论参与交集，`coCommented`，「共同讨论过」/「都参与了××讨论」；内容维度交集的唯一一级母表达——内容上没有长期动作，交集叙事从「收藏行为」转向「连接关系」（如「来自AI产品圈」「2位校友正在讨论」）。

### 2.1.1 kind 标准化迁移 + favorite 退场

- Go `intersection_service.go` 的 `evidenceKindRank` 已迁移到注册表标准名（已落地，基线修正；未知 kind 落兜底 rank）；`intersection_source.go` 与测试、Dart mock 种子、contract fixtures 的 kind 取值迁移仍待完成（→ T1/T4）。
- 契约层删除 `FavoritePost/UnfavoritePost` API、`favoriteCount/favorited/favoritedAt` 字段、`favorite` 行为类型与相关索引/计数/投影 alias；端侧删除全部收藏入口与本地 save/bookmark 状态；不保留兼容路由、字段 alias 或灰度开关。**已落地（基线修正），准出保留防回归 grep。**
- 「以后再看」由足迹承载：只读契约 `GET /v1/content/footprint`（数据源=既有行为边，无新写路径）**已登记（基线修正）**，足迹**不产生交集**；端侧消费闭环 → T5。

### 2.2 文案与展示字段补全（空窗治理）

- `hydrateDisplayLanguage` 按 §20.3 词表统一产出 `primaryText`（结论句）与 `secondaryText`；任何进入 spotlight 候选的 reason 必须 `primaryText` 与（人=avatarUrl，物=对象头图）完备。
- `displayName/avatarUrl` 在 source 层补全（从 user/circle/entity 读模型回填），不得下发空值进候选窗。
- 排序保持 `evidenceKindRank`（人>物>地>内容>兴趣fact>recommended），kind 全部使用注册表标准名：`sharedFollowees`（人级最高）、`coCommented`（内容级）、`coVisitedEntity`（地点级）。

### 2.3 fixtures 与 seed

- contract fixtures（`contracts/metadata/content/test_fixtures/scenarios/`）补齐六类样本（每类至少 1 个 fact reason + 可枚举 points），并为 reason 的 `intersectionPoints` 铺 point 级 `sourceRef` 标准 kind（修复现状只有维度词的缺口）。
- alpha/beta seed manifest（`contracts/metadata/_shared/test_fixtures/app_{alpha,beta}_seed_manifest.json`）登记对应种子，使 beta 人工验收与 gamma 自动化都能看到六类表达。

## 2.5 剩余任务清单（T1~T6，含验收标准）

> 基线修正会话已交付 favorite 退场 / 足迹契约登记 / 端侧 kind 折叠债清理 / `hydrateDisplayLanguage` 框架。
> 以下为本 WP 剩余全部工作；T1~T4 为云侧/数据子序列（先行，阻塞 WP2 开发期与 beta 联调），T5 为足迹端侧子序列（可与 T1~T4 并行），T6 为对 WP3 的交接物。

### T1 云侧 kind 标准化收尾

- `intersection_source.go` 旧 `mutualFriend` 产出迁移到 `sharedFollowees`；`intersection_service_test.go` 5 处旧 kind 断言同步迁移。
- 验收：grep `mutualFriend|friendVisited|friendInCircle|coCollectedEntity` 云侧（`quwoquan_service/**`）零残留；`go test ./services/content-service/...` 绿。

### T2 六类真实数据源落地

- `sharedFollowees`（基于 `follow_edges` 的共同关注第三方集合计算）、`coCommented`（共同讨论）、`coVisitedEntity` / `followeeVisited`（共同地点真实化），全部 `intersectionClass=fact`；既有 `sharedCircle`、同校标签事实保持。
- 验收：contract 测试断言六类 kind 均能产出 + `primaryText` 符合词典口径 + `intersectionPoints` 非空可枚举（对应 §5 准出 1）。

### T3 空窗治理

- source 层从 user/circle/entity 读模型回填 `displayName/avatarUrl`，不得下发空值进候选窗；新增 spotlight 候选完备性 contract 测试（`primaryText` 非空 + 人=头像/物=头图完备）。
- 验收：gamma `/v1/content/intersections/summary` 返回 ≥5 类事实表达、spotlight 非空（对应 §5 准出 2/3）。

### T4 端侧 mock / fixtures 标准化

- 端侧 mock `intersection_repository.dart` 3 处旧 kind（`friendInCircle/friendVisited/mutualFriend`）迁移；`evidence_group.dart` 注释口径同步。
- contract fixtures 补齐六类样本（每类 ≥1 个 fact reason + point 级 `sourceRef` 标准 kind）；alpha/beta seed manifest 登记对应种子。
- 验收：grep 全仓旧 kind 零残留（词典退场清单章节豁免）；`make verify-metadata` 绿。

### T5 足迹端侧消费闭环（归属本 WP）

- `FootprintRepository` 三层（Abstract / Mock / Remote，遵守 R02 单接口 ≤10 方法）+ `app_providers.dart` 注册 + 我的页足迹 Tab 列表页（新页面文件落 `lib/ui/user/pages/`，页面矩阵登记 + 埋点 R20/R21）。
- 验收：T2 widget 测试（Mock 渲染足迹列表）+ T3 beta 真实数据渲染 + 「足迹不产生交集」反断言保持绿。

### T6 kind → rank/icon/维度短语映射清单（交接 WP3）

- 以本文档附录 A 为正式交接物，WP3 在 `evidence_group.dart` 实现端侧图标/排序扩展时只消费该清单，不自造映射。
- 验收：附录 A 与云侧 `evidenceKindRank` 一致（rank 数值同源）；WP3 实现后 contract 测试引用同一清单。

## 3. 周边契约（2026-06 交集统一收口后）

- **允许** `intersection_reason.yaml` / `object_intersection*.yaml` / `object_page_bundle.yaml` / `search_contract.yaml` 字段形状一次性收敛（零兼容）；以 `specs/product/intersection-definition-and-application.md` §18 为准。
- **不改** 交集 5 维闭集与 6 条 API 路由（`/v1/content/intersections/*`、`/v1/content/feed/intersections*`）。
- 端侧 `evidence_group.dart` kind→排序/图标映射扩展仍归 WP3，消费 WP1·T6 附录 A 清单。

## 4. 改动范围

- `quwoquan_service/services/content-service/internal/infrastructure/recommendation/intersection_source.go`（新数据源 + 文案 + 字段补全 + kind 标准名迁移）
- `quwoquan_service/services/content-service/internal/application/intersection/intersection_service.go`（`evidenceKindRank` 标准化、保鲜、候选过滤）
- `quwoquan_service/services/content-service/internal/application/feed/feed_intersection_mixer.go`（feed 理由混排消费新 kind）
- favorite 退场触达面：`contracts/metadata/content/post/{service,fields,behaviors,events,storage,aggregate,ui_config}.yaml`、`_shared/{request_context,types,redis_keyspace}.yaml`、5 个投影 yaml、`recommendation/rec_model/projections/learning_events.yaml`、`assistant/assistant_run/fields.yaml`；content-service handler/application/推荐管线；rec-model-service 与 `scripts/ml/**`；端侧（详见 WP 各包与词典退场清单）
- `contracts/metadata/content/test_fixtures/**`、`_shared/test_fixtures/app_{alpha,beta}_seed_manifest.json`
- `contracts/metadata/recommendation/rec_model/projections/intersection_reason.yaml`（字段收敛 + description 注记；见 §18 契约表）
- 足迹只读契约登记（`content/post/service.yaml` 或独立分区 + `_shared/ui_surfaces.yaml` route `myFootprint`）
- 新增 Go 单测 / contract 测试

## 5. 准出要求

1. T1：contract 测试断言六类 kind 均能产出，且 `primaryText` 符合 §20.3 高层措辞与 `specs/product/intersection-definition-and-application.md` 的词典口径，`intersectionPoints` 非空可枚举。
2. T1：spotlight 候选完备性测试——进入候选窗的 reason `primaryText != '' && (avatarUrl != '' || objectKind 非 person 有头图)`。
3. T3：gamma 环境真实 API（`/v1/content/intersections/summary` 与 `/v1/content/feed/intersections`）返回 ≥5 类事实表达；spotlight 候选非空。
4. `bash agent_ops/gate/gate_repo.sh --scope service` 与 `--scope app` 全绿；`make verify-metadata` 绿。
5. 不得出现端侧本地拼装文案的回归（G2 契约测试保持绿）。
6. grep 验收：
   - **防回归**（基线修正已达成）：契约/云侧/端侧 `favorite|FavoritePost|coFavorited|coFollowedContent` 零残留（词典退场清单章节与点赞心形图标 `Icons.favorite*` 豁免）。
   - **待达成**（T1/T4）：全仓 `mutualFriend|friendVisited|friendInCircle|coCollectedEntity` 零残留（词典退场清单章节豁免）。
7. T5 足迹端侧闭环：足迹列表页 widget 测试绿 + 页面矩阵/埋点登记齐备 +「足迹不产生交集」反断言保持绿。

## 6. 验收标准（GWT 样例）

- Given A 与 B 有 4 个共同关注的第三方用户，When 拉取交集，Then 返回标准 kind `sharedFollowees`、`primaryText=「4位共同关注的人」`、points 为 4 个具体用户。
- Given 用户 A 与用户 B 都在同一篇文章下评论过，When A 拉取 B 的交集 summary，Then 返回标准 kind `coCommented` 证据组、`primaryText` 为「共同讨论」口径、points 含该讨论上下文。
- Given gamma 环境 seed 数据，When 拉取推荐频道 feed intersections，Then 候选窗内每条 reason 的 primaryText/头像完备，spotlight 不空窗。
- Given 某 reason 为 affinity，Then 其 `confidenceLabel` 为克制文案且不使用六类事实措辞。
- Given 用户 A 看过/赞过某篇内容（足迹记录），When 任何其他用户拉取与 A 的交集，Then 不产生任何基于足迹的交集 reason（足迹私有、不进 SharedFact）。
- Given 任意客户端请求 `POST /v1/content/posts/{postId}/favorite`，Then 返回 404（路由已删除，无兼容路由）。

## 附录 A · kind → rank / icon / 维度短语映射清单（T6，交接 WP3）

> 真相源：云侧 `contracts/metadata/recommendation/rec_model/intersection_kind_registry.yaml` + 生成表 `internal/generated/intersection_kind_table.go`（rank 数值同源）+ 交集词典 §5.4 唯一注册表。
> 端侧约束（G2）：本清单**只用于展示层降级**（排序分组与 fallback 图标选择）；文案一律消费云侧 `primaryText/secondaryText/displayText`，端侧不得依据 kind 做语义分支或本地拼装文案；未知 kind 必须优雅降级（落「未知」行，不崩溃、不过滤）。

| rank | 维度短语 | kind（注册表标准名） | fallback 图标语义 |
|---|---|---|---|
| 10 | 人 | `sharedFollowees` `commonFollower` `commonContact` `followeeInObject` `followeeVisited` `followeeViewing` `followeeDiscussedThis` | 人形（person） |
| 20 | 事物 | `coMemberCircle` `sharedCircle` `sameCompany` `sameTeam` `sameIndustry` `sharedEntityAttention` `coWishlistedEntity` | 圈子/组织（circle） |
| 30 | 地点 | `coVisitedEntity` | 地点（place） |
| 40 | 内容 | `coCommented` `coSharedContent` `coCreatedContent` `sharedDiscussion` | 对话气泡（discussion） |
| 50 | 身份 | `sameSchool` `sameDepartment` `sameMajor` `sameCohort` `alumni` `alumniHere` `colleagueHere` | 学校/徽章（school） |
| 60 | 兴趣 fact | `sharedTagSample` | 标签（tag） |
| 500 | 未知（兜底） | 任何未列出的 kind | 链接（link，缺省 fallback） |
| 900 | 推荐（概率） | `pointClass == recommended`（与 kind 无关） | 不加事实图标，用克制推荐样式 |

- 排序：rank 越小越靠前；同 rank 内按云侧返回顺序，端侧不重排。
- 图标列仅描述「语义槽位」，具体 icon 资源由 WP3 在 `evidence_group.dart` 选定；person/circle/place 等 objectKind 闭集图标与既有 `intersection_entity.dart` 降级逻辑保持一致。
- 同源防漂移：云侧契约测试 `TestEvidenceKindRank_MatchesWP1AppendixA`（`intersection_service_test.go`）逐项断言本清单 rank 数值与 `evidenceKindRank` 一致；改任一侧必须同步另一侧。
