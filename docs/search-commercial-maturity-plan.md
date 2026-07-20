# 搜索（M5）商用成熟度全面排查与规划

> 版本：2026-07-20（M5 专项会话产出）
> 审查主线：`业务目标 → 核心业务对象 → 对象关系 → 对象生命周期 → 用户旅程 → 功能能力 → 页面承载 → 交集差异化 → 运营指标 → 测试验证`
> 承接：`docs/functional_module_commercial_maturity_matrix.md` §14（M5）、`specs/feature-tree/global-search-experience/**`、`docs/outstanding_risks_backlog.md`「搜索体验 / 搜索端云一体」两节。
> 树绑定：Journey `cross-domain-search`（draft）；L1 `global-search-experience`；L2 `cross-domain-search-journey` + `search-provider-routing-and-storage-topology`（14 个 L3）。

---

## 0. 结论速览（必须回答的八个问题）

| # | 问题 | 结论 |
|---|---|---|
| 1 | 领域模型是否真正围绕业务对象建立 | **是**。search 域 `business_object_map.yaml` 登记 5 对象（1 聚合根 + 3 append-only fact + 1 projection），职责分离清晰；无聚合 Repository 回潮。 |
| 2 | 对象关系和生命周期是否合理 | **基本合理，两处跑偏**：`SearchIndexView` 的 tombstone→端侧 freshness 语义无页面表达；`RetrieveHit.connectionState/intersectionReason` 是登记在契约上的**死字段**（云侧无 attach 生产者）。 |
| 3 | 页面是否完整承载对象和用户旅程 | **旅程骨架完整**（入口→默认页→联想→结果→对象落地→反馈），但「用户/标签」两类对象无结果承载；交集 Tab 在 remote 下因死字段呈假空态。 |
| 4 | 哪些页面只是空壳或功能简陋 | 无空壳页。简陋点：结果页筛选仅内容类型一维；默认页「热门圈子/热门地点」为近似数据伪装热榜；结果页 Tab 标签硬编码中文。 |
| 5 | 哪些页面美观但对象已跑偏 | 交集 Tab（`search_network_results_page`）：UI 语义按 `connectionState` 闭集分组正确，但云侧从不产出该字段 → 页面语义正确而数据链路跑空。 |
| 6 | 哪些页面适度优化、哪些必须重构 | 见 §5：三页均**保留 + 中度收口**（P2/P3 → P4/P5），无需完全重构；新增 0 页，删除 0 页。 |
| 7 | 相比业界标杆还缺什么 | 动态筛选维度（小红书）、结果类型 Tab 的对象完备性（微信「账号」聚合）、修饰符/高级过滤（Slack）、无结果视图规范化（HIG）。见 §6。 |
| 8 | 交集如何形成不可复制的差异化 | 云侧**已有**统一交集真相源（content-service `IntersectionService`，`/content/intersections/object`）。搜索差异化 = 检索后 attach 交集事实（连接态 + primaryText 证据句）——是「接通」不是「新建」，见 §7。 |

**商用总评：D1 旅程骨架 P3、D2 契约 P3+（wire 漂移已修）、D3 视觉已核验（12 张双色截图，结构完整、默认页密度偏素，见 §1.4）、D4 性能仅 local 证据、D5 黄金指标未建、D6 App api_integration 为零。距商用 P4 的关键阻断项见 §8 工作包表。**

---

## 1. 阶段 0：真实运行核验（文档声称 vs 实际）

### 1.1 工作树可编译性（2026-07-20 实测）

| 声称 | 实测 | 裁定 |
|---|---|---|
| backlog「搜索功能链路本地已验证可用」（2026-06-16 口径） | **当前工作树 App 无法编译**，`flutter run`（alpha dart-defines，iPhone 15 模拟器）Xcode build 失败 | 环境性阻断（多为并发会话半迁移文件，非搜索域）：`lib/core/providers/app_providers.dart`（MD，被删未收尾）、`lib/cloud/services/user/{call,appearance}_settings_repository.dart`（D）、`article_reader_page_surfaces_blocks.dart`（未跟踪 part 断链）、`image_editor_operation_panel_controls.dart` 重复声明、`welcome_appearance.dart` 缺 token、`assistant_skill_center_sections.dart` 缺 getter |
| 搜索域自身可编译 | **一处真实断链**：`lib/core/services/remote_search_repository.dart` 重构半成品（构造签名已改 `remoteQuery` 单参、`_localFanout` 已去除，但缺 `search_models.dart` import → `SearchMode/SearchResolvedFrom` 未定义 3 个 error） | **本轮已修复**（补 import + 清理冗余 import），`dart analyze` 0 error。这是「搜索完全不可用」的搜索域内直接根因之一 |
| local_contract 全绿 | 首轮：network_results 33 用例 + location_landing 通过，`global_search_page_widget__local_contract_test.dart` 编译失败（跨会话断链外溢）。**二轮（2026-07-20 13:3x，修复 `app_providers.dart` 非法 part import 后）：搜索域 local_contract 53/53 全绿**（含 global_search 13 用例 + cloud/search 契约） | 三页 local_contract 证据全部有效且已复验 |
| 页面视觉 | **已核验**（2026-07-20 二轮）：user 域断链被并发会话收口 + 本轮修复 `app_providers.dart` 对 part 文件的非法 import 后，widget 截图 harness 12/12 通过，产出 6 场景 × 浅/深色共 12 张真实渲染 PNG（`.qwq_output/env/repo/runs/search-visual-audit/*.png`，含全字体家族与 CupertinoIcons 注册） | 视觉结论见 §1.4 与 §5.3；双色一致性良好，默认页视觉密度偏素是「简陋」观感主因 |

### 1.2 gamma-local 端云冒烟（2026-07-20 实测，search-service:19280 直连）

- `stackctl up --env gamma --skip-app` 首轮失败：entity-service `homepage_service.go` 与新增 `homepage_fixture.go` 符号重复（并发会话中途态，随后已在工作树消除）；重跑 `--workload content-release`（full workload 被 SLS secret 缺失 GATE_BLOCK，符合设计）镜像重建约 2.8h（amd64 模拟，R-S06-S-1 已知工件）。
- **真实冒烟结果**（ES 索引 1,755 docs，来自既往 backfill 卷）：

| 探针 | 结果 | 裁定 |
|---|---|---|
| `GET /healthz` | 200 `{"status":"ok","checks":{"elasticsearch":"ok"}}` | ✅ |
| `POST /search`（result，「西湖」） | **首轮 100% 503** `SEARCH.MIDDLEWARE.unavailable`——gamma config 无 `requestTimeoutMs` 覆盖，默认 800ms 被模拟 ES（单查询 1s+）全打穿；放宽后 200，5 hits（location+article+photo 混排）、`rankingVersion=search-v1`、`experimentBucket=control`、relatedTerms 有值，**耗时 3.16s（超 SLO P95 1.5s 两倍，本地工件）** | ⚠️ 已修 gamma config（四域+search 补 `requestTimeoutMs: 5000`）；印证「ES 慢 = 全量 503」的降级链路真实发生 |
| hit 信封 | `connectionState`/`intersectionReason` 键**从未出现**（omitempty + 无生产者） | 🔴 死字段实锤（§7） |
| `rankReasons` | wire 输出 `{"Code":"query_match","Label":"命中title","Weight":27.75}` **大写 Go 导出名**——`runtime/search/core.go` 的 `Reason/Evidence/Facet/DegradeSignal/Provenance/Citation` 全缺 json tag；App 契约包按小写 `label` 解码 → **排序理由/降级信号在 remote 端到端静默全丢** | 🔴 **本轮已修**（补小写 json tag + 注释；`go test ./runtime/search/... ./services/search-service/... ./services/assistant-service/.../tool` 全绿）。既往「R-S06 透传 rankReasons」验收从未在真实 wire 上成立。修复后容器内复验：`rankReasons[0]={"code":"query_match","label":"命中title","weight":27.75}` 小写 ✅，warm 查询 0.54s（首查 3.16s 为 ES 冷缓存）；热替换仅作运行时证据，不替代冷启动验收 |
| `POST /search/feedback` | 202 | ✅ |
| `GET /search/hot-queries?limit=5` | 200，真实 term-heat（由本轮 query log 重建） | ✅ |
| `GET/POST /search/recent` | 401 `SEARCH.USER.unauthorized`（`X-User-Id` 头不构成登录态，需网关注入真实身份） | ✅ fail-closed 正确；但说明 recent 面的端云证据必须走网关全链路，直连冒烟不计 |
| 空 query | 400 结构化 `invalid_argument` + recovery 语义 | ✅ |
| `POST /search`（suggest，「摄影」） | 200，0.63s，3 hits | ✅ |
| circle-service 启动 | **exit(1)**：`search index ensure failed: es timeout`——circle/entity/user 启动期 `EnsureIndex` 失败 `log.Fatalf`，而 content/search 是 WARN 继续；**启动期 ES 依赖语义跨域分裂**，ES 慢/重启窗口会把三个服务打成 crash loop | 🔴 环境性已修（timeout config）；语义统一进 WP-H |
| gamma-proxy（Caddy 网关）启动 | **Bind 0.0.0.0:19130 failed**：compose（HEAD 已入库）中 `object-storage`（minio 直出 TLS 边缘）与 `gamma-proxy` **双双声明宿主 19130**（端口 manifest 该槽属 `object-storage-edge`）；11 个业务服务全 healthy 但网关起不来 | 🔴 环境拓扑缺陷（`efc05dac1` 媒体交付收口引入，非搜索域）；修复归环境域（gamma-proxy ports 移除 object-storage-edge 槽或改经内网 alias 反代） |
| 经网关 `/search*` 全链路（替代验证，临时 Caddy 容器同网络 + 同一 Caddyfile + TLS/SNI `gamma-api.quwoquan-env.test`） | `POST /search`：冷查询 try1 503（ES >5s，typed fail-fast）→ try2 200（5.76s）→ try3 200（1.26s），hit 含小写 `rankReasons`、`rankingVersion=search-v1`；`/search/feedback` 202；`/search/hot-queries` 200（真实热力，含本轮冒烟词「西湖」）；**旧 `/v1/search` 404**（无版本 path 契约在网关层成立） | ✅ Caddy matcher→search-service 反代链路验证通过；冷查询超时波动属 R-S06-S-1 本地工件，真集群需以 measured 容量收口 |

- 历史证据核验：`R-S06-S`（2026-06-16 gamma 冒烟 15 checks）真实存在于 `.qwq_output/env/gamma/runs/**`。**但 2026-07-17 API path 去版本后，无版本 path 镜像冷启动验收（POST `/search` 为指定探针之一）仍未关闭**（挂 CR-20260717-109 衍生验收）。

### 1.4 页面视觉核验结论（12 张真实渲染截图，2026-07-20）

> 证据：`.qwq_output/env/repo/runs/search-visual-audit/{01..06}_*_{light,dark}.png`（iPhone 逻辑尺寸 390×844 @2x；contract-seeded 替身数据；字体/图标注册齐全）。

| 场景 | 浅/深色观察 | 视觉裁定 |
|---|---|---|
| 01 默认页 | 历史两列 + 展开/删除管理位 + 「猜你想搜/热门圈子/热门地点」三分段 + 换一换；层次清楚、token 一致；深色对比度正常 | 结构达标但**视觉密度偏素**：纯文字两列、无热度徽标/排行视觉/封面元素，与小红书引导页的丰富度差距明显——这就是「界面简陋」观感的主要来源，P3 裁定成立 |
| 02 联想态 | 联系人（头像+命中高亮）与「搜索网络结果」直达行分区清晰；命中字符高亮蓝色正确 | 达标；直达行样式略平（纯文本行），可在 WP-K 精修 |
| 03 全部 Tab | 实体顶卡（名称/徽标/城市/计数/箭头）+ 双列 masonry 媒体卡（标题/摘要/作者/点赞、真实宽高比） | 结构达 P3+；无图时占位为灰块（本次用不可达 URL 验证降级占位成立） |
| 04 交集 Tab | 「已形成的连接」（connected 卡 + 连接态句）与「发现更多交集」两分组；深色卡面对比度良好 | **UI 完成度最高的一页**；但见 §7 修正——connected 地点卡的「你关注过」是端侧按 connectionState 固定翻译的动作句，非云侧事实文本，WP-J 需一并收口 |
| 05 空态 | 「全部 · 0 条结果 · 已连接优先，未连接按类别比例发现」摘要条 + 居中空文案 | 空态成立但**未回显查询词、无相关词/行动引导**（HIG content-unavailable 建议回显 query），进 WP-K |
| 06 location landing | 地点卡 + 临时徽标 + 说明 + 「提升为实体主页」CTA，结构完整 | 达标；正文在 harness 中字体回退失败呈方块为**测试环境 artifact**（真机走系统字体栈），不计缺陷 |

**双色一致性**：六场景深浅色均由语义 token 驱动，无反色错乱、无对比度事故。**视觉总评**：三页均确认「结构完整、装饰克制过头」——P2+/P3 评级维持，「简陋」观感的整改重心在默认页灵感区的信息丰富度（热度徽标、封面卡片化）与空态引导，归入 WP-K。

### 1.3 「已解决」条目需重开/降级清单

| 条目 | 原状态 | 复核裁定 |
|---|---|---|
| R-S06 App 接搜索 API | 已解决 | **部分重开**：RemoteSearchRepository 于本轮前处于编译断链；且其半重构把 `localFanout` 从构造中移除（suggest 委托改由 provider 层 `searchLocalFanoutProvider` 承载），T2/T3 需按新形态复验 |
| R-003/WP-C 交集单源消费 | 已解决 | **端侧成立、端到端不成立**：端只读 `connectionState/intersectionReason.primaryText` 正确，但云侧无生产者 → remote 全量落 `unconnected`，交集 Tab 实际无差异化内容（见 §7） |
| R-S06-S 端到端冒烟 | 已解决 | 有效但为**旧版本 path 证据**；无版本 path 冷启动复验未关闭（挂靠 CR-20260717-109 衍生验收） |
| R-S06-S-1 / R-S06-S-2 | 未解决 | 维持**发布阻断**不变 |

---

## 2. 阶段 1A：业务对象全景表

| 业务对象 | 用户价值 | 上下游对象 | 聚合/上下文 | 生命周期 | 页面承载 | API/服务 | 存储/事件 | 当前问题 |
|---|---|---|---|---|---|---|---|---|
| `SearchQuery`（append-only fact） | 检索意图与结果的事实记录，驱动热搜/推荐回流 | ←user.Persona（viewer）；→SearchFeedbackFact / SearchRecommendationSignalFact | search.Search（append_sink） | 追加不可变；TTL 由 storage.yaml 声明 | `/search` 提交、`/search/network` 消费 | `POST /search`（mode=suggest\|result，SLO P95 1.5s） | Mongo query log；`SearchQueryLogged` 旁路 | 无（链路健康） |
| `RecentSearchState`（聚合根） | 搜索历史跨端同步、可删除可清空 | ←user.Persona 1:1（cascade） | search.Search | `active → cleared`；version CAS + 幂等 receipt | 默认页历史区（两列五行/展开/管理删除） | `GET/POST/DELETE /search/recent`（4 operation） | Mongo `recent_search_state` + receipts | `recent_search_receipts` 未登记 storage.yaml；recent 路由无 Prometheus 指标 |
| `SearchFeedbackFact`（append-only fact） | impression/click/dwell/refine/zero_result/degrade 反馈事实 | ←SearchQuery（searchRequestId）；→8 类目标对象（tombstone 引用） | search.Search（经宿主 packet append） | 追加；90 天 TTL；语义键 `(searchRequestId,eventType,objectId)` 去重 | 结果页曝光/点击自动上报 | `POST /search/feedback`（202） | Mongo feedbackstore | 无 |
| `SearchRecommendationSignalFact` | 搜索词信号注入推荐 Feed | →recommendation `rm_recommend_feature.searchTermAffinity` | search.Search | 追加 | 无页面（后台回流，合理） | Redis Stream `events.search.recommendation_signals` | search-service 发布 / content-service 消费 | RuleScorer 消费已闭环；线上 AB 收益未度量（WP-F 长稳尾巴） |
| `SearchIndexView`（projection） | 统一跨域召回底座 | ←content.Post/entity.Homepage/circle.Circle/user.Profile/location.place 五域投影 | search.Search（读）×各域（写） | `投影 → 生效 → stale → tombstone → rebuild(backfill)` | 无独立页（合理）；**stale/tombstone 无端侧 freshness 表达（缺口）** | ES `quwoquan_objects`；各域 `searchindex/` projector + `cmd/search-backfill` | ES 索引 | tag 域未投影；freshness/tombstone 语义未回传结果页 |
| 热搜词 `TermHeat`（派生读模型） | 猜你想搜、相关搜索词 | ←SearchQuery/SearchFeedbackFact 挖掘 | search.Search | 周期 Rebuild（10min）+ TTL 86400s | 默认页「猜你想搜」批次轮换 | `GET /search/hot-queries`（SLO P95 500ms） | Mongo `rm_search_term_heat` | 无 |
| 关联：Post/User/Circle/Homepage/location.place | 检索目标对象 | hit.payload 承载最小投影 | 各自域 | 各自域 | 结果卡→各域详情页 | 点击落地各域路由 | — | **user 无独立结果 Tab；tag 完全缺席检索**（见 §4 缺口） |

**契约与端侧接线核验**：7/7 operation（search query 3 + recent 4）在 `contracts/metadata/search/**/service.yaml` 声明 → `quwoquan_cloud_contracts/lib/src/search/` 四个契约文件 → `lib/cloud/remote/search/` 三个 Remote adapter（hot_query/recent_search/search_feedback）+ `RemoteSearchRepository`（canonical search）→ `app_providers_operations.dart` / `app_providers_client_sync.dart` 实装；零硬编码 path。错误码 8 个（query 4 + recent 4）经 codegen 生成 `search_errors.g.dart`。

## 3. 阶段 1B：对象关系与聚合边界审查

- **关系正确性**：SearchFeedbackFact→目标对象采用 `(target, objectId)` 弱引用 + `on_delete: tombstone`，与「读模型不反向持有业务对象」原则一致。RecentSearchState→Persona 1:1 cascade 合理（账号注销级联清史）。
- **无第二真相源**：旧 `tag_repository_remote` 式硬编码 path 在 search 域不存在；suggest 本地对象（chat contact/conversation）与 result 云侧对象物理隔离（PR-SR-01 硬规格 + negative finder 测试），「过程合并」不混排。
- **一处概念双轨风险（收敛中）**：`AppSearchRepository`（本地扇出 composite，1,921 行 5 文件）同时承担 alpha mock 组合与 remote suggest 扇出。其静默 `catch (_)` 10 处（cloud_sections 5、local_sections 3、主文件 2）违反 R17；`Map<String, dynamic>` payload 穿透违反 R04（`SearchHitPayloadWireMap` 是薄封装而非 typed sealed）。
- **交集字段归属裁定**：`RetrieveHit.connectionState/intersectionReason` 注释声明「由 search-service 从统一交集真相源 attach，端侧禁止合成」——方向正确，但 attach 阶段**未实现**（`rg` 全仓无赋值方）。交集真相源实际存在于 content-service `IntersectionService`（`Summary/List/Feed/ObjectIntersections`，`/content/intersections/object`），primaryText 云端生成、不可展示 reason 云端淘汰。**关系修复路径 = search-service 检索后按 viewer×hit 调 ObjectIntersections（或投影侧预 join），不是在 search 域新建交集模型。**

## 4. 阶段 1C：核心对象生命周期状态机

**SearchIndexView**（关键缺口所在）：

```
[各域对象发布/更新] → projector upsert（写时，fan-out 末位，失败只告警）
      → [生效 indexed] → 查询可召回
      → [stale]（源对象更新未及时投影 / ES 重启窗口）
      → [tombstone]（unpublish/delete/ineligible → projector delete）
      → [rebuild]（cmd/search-backfill 全量，EnsureIndex→List→Bulk）
```

逐状态核对：生效/删除有 projector 测试；**stale 与 tombstone 无端侧表达**——结果页可能短暂展示已删除/已下线对象，点击落地 404 时无「结果已失效」语义（当前只有各域详情页自己的错误态）。商用要求：结果点击落地失败时回搜索页给出 typed「该结果已失效」反馈并上报 `zero_result/degrade` 反馈事实（D1 缺口，进 WP-K）。

**RecentSearchState**：`active（upsert/delete，version CAS）→ cleared（clear all）`；幂等 receipt 防重放；页面承载完整（历史区管理态删除/清空）；游客态本地缓存 + 登录态云端真相源 + 本地补写回流（`search_coordinator.dart` hydrate 逻辑）。唯一残留：清空后 receipts 集合的 TTL 登记缺失（运维审计缺口）。

**SearchQuery/SearchFeedbackFact**：追加型，无状态迁移，页面自动上报，健康。

---

## 5. 阶段 2：对象—功能—页面双向矩阵与成熟度评级

### 5.1 页面→对象反查矩阵

| 页面/路由 | 用户目标 | 主对象 | 关联对象 | 核心功能 | 生命周期状态 | 上游入口 | 下游去向 | 完整性结论 |
|---|---|---|---|---|---|---|---|---|
| `/search`（global_search_page，默认+联想两态） | 发起检索、复用历史、获得灵感 | SearchQuery(suggest)、RecentSearchState、TermHeat | chat contact/conversation（本地 suggest）、Circle、Homepage | 历史（展开/管理/删/清）、猜你想搜（批次换一换）、热门圈子/地点、实时联想（防抖/取消/慢请求反馈）、语音入口 | recent active/cleared；suggest 即时 | 首页顶栏、发现页、interest_match launcher、assistant handoff | `/search/network`、chat 详情、circle 详情、homepage 详情 | **功能完整**；问题：热门圈子/地点伪热榜（circle.listCircles limit 9 / homepage searchHomepages 空 query 前 30 过滤，非热度真相源）；suggest 空态/错误态已具备 |
| `/search/network`（search_network_results_page，6 固定 Tab） | 跨域获取结果并行动 | SearchQuery(result)、SearchFeedbackFact | Post/Homepage/location.place/Circle group、AssistantSearch（小趣 Tab） | Tab：小趣/全部/交集/图片/视频/长文；实体顶卡、masonry 媒体流（真实封面比例）、相关搜索词、内容类型筛选、降级横幅、错误重试、每 generation 单次 canonical 调用 | query 提交→完成/部分失败/降级 | `/search` 提交、深链（旧 tab id 归一） | 内容详情、homepage、location landing、circle、suggestHomepage | **骨架完整**；问题：①交集 Tab 死字段假空态 ②user/tag 无结果承载 ③Tab 标签硬编码中文（`search_result_tab_spec.dart` L33-64 违反 R27/i18n）④筛选仅内容类型一维 |
| `/locations/{placeId}`（location_place_landing_page） | 理解临时地点并促成提升 | location.place（route extra 只读投影） | entity.Homepage（提升目标） | 临时地点卡、临时徽标、提升为实体主页 CTA（复用 suggestHomepage）、enter/promote_click 埋点 | 未提升=place / 已提升=homepage 单一真相源 | 结果页地点命中 | suggestHomepage 表单 | **按设计完整**（无独立后端 operation 是登记边界）；风险：route extra 透传即页面无深链自恢复能力（刷新/分享链路断） |
| 嵌入入口（顶栏搜索按钮、interest_match launcher、assistant handoff） | 进入搜索 | — | — | 曝光埋点 + `entrySurfaceId` 归因 | — | 首页/发现/加号面板 | `/search` | 完整（`referralSource=search` + `feedRequestId` 归因链 local_contract 已验） |

### 5.2 对象→页面正查（缺口视角）

| 对象/能力 | 应有承载 | 现状 | 裁定 |
|---|---|---|---|
| user.Profile 检索结果 | 结果页独立「用户」Tab 或全部 Tab 分区 | 云侧已投影可召回（user_search_projection），**端侧无 Tab、无分区渲染** | **GATE 缺口**（对象有定义无页面）→ WP-K |
| tag 检索 | 全部 Tab 标签分区或联想 chips | 云侧未投影 + 端侧无承载 | 需产品决策（tag 是导航器还是可检索对象）→ WP-K 决策项 |
| SearchIndexView stale/tombstone | 结果失效反馈 + freshness 语义 | 无 | D1 缺口 → WP-K |
| 交集事实 | 交集 Tab 连接分组 + 证据句 | UI 就绪、云侧 attach 缺失 | **GATE_BLOCK**（页面存在但无正确对象支撑）→ WP-J |
| 热榜（圈子/地点） | 默认页热门区 | 近似数据伪装（违反「不得把推荐/近似结果伪装成事实」） | GATE 缺口 → WP-I/WP-K（真热度读模型或改文案语义「发现圈子/地点」） |

### 5.3 页面成熟度评级与重构决策

> 视觉分已核验（§1.4，12 张双色真实渲染截图）；下列为功能/对象/旅程/视觉综合评级。

| 页面 | 预评级(矩阵) | 本轮复核（含视觉） | 决策 | 主要依据与补齐项 |
|---|---|---|---|---|
| `global_search_page` | P3 | **P3（确认）** | **保留 + 精修** | 功能面充分（历史/灵感/联想/取消/慢反馈），双色一致；视觉主诉=灵感区纯文字两列过素（截图 01），补：灵感区卡片化/热度徽标、热榜真相源或语义改名、联想直达行精修（截图 02）、global_search 测试链复验；目标 P4 |
| `search_network_results_page` | P2 | **P2+（确认）** | **保留 + 中度收口**（不做完全重构） | 33 用例功能骨架 + 降级/错误/归因达 P3 门槛，实体顶卡与 masonry 媒体流视觉成立（截图 03）、交集 Tab UI 完成度最高（截图 04）；压在 P2+ 的原因：交集死字段 + 端侧动作句、user/tag 缺席、Tab 硬编码、单维筛选、空态无 query 回显与引导（截图 05）；补齐 WP-J/WP-K 后到 P4，交集接通后冲 P5 |
| `location_place_landing_page` | P2 | **P3（上调）** | **保留 + 轻量精修** | R-S05e-1 后功能语义完整、测试 3 用例绿、卡片/徽标/CTA 结构完整（截图 06；正文方块为 harness 字体 artifact 不计缺陷）；补深链自恢复（placeId 反查快照或降级空态）；目标 P4 |

不新增页面、不合并页面、不删除页面；「用户 Tab」按 IA 决策放入全部 Tab 分区或第 7 个固定 Tab（推荐前者，见 §6 借鉴微信「账号」聚合但避免 Tab 膨胀）。

---

## 6. 阶段 3：业界标杆对比（检索日期 2026-07-20）

| 标杆产品 | 对标页面/旅程 | 功能完整性 | 信息架构 | 关键交互 | 异常恢复 | 可借鉴原则 | 不适合照搬 |
|---|---|---|---|---|---|---|---|
| 微信搜一搜（来源：woshipm.com/share/6223968、36kr.com/p/1722443333633、cloud.tencent.com.cn/developer/news/2193286） | 全局搜索入口 + 结果分类页 | 公众号/朋友圈/文章/百科/音乐/小程序/问答/视频 10 类卡片分组；2025 起「账号」一级聚合公众号/服务号/小程序/视频号 | 社交语境个性化：同一 query 因个人关系链不同而结果不同 | 指定范围搜索（朋友圈/公众号/小程序…）；可定制页面 | 分域卡片独立降级 | ①同类对象聚合成一个可理解分组（「账号」≈趣我圈「用户+主页」候选思路）②关系链个性化排序与我们的交集 attach 同构 ③搜索直达服务闭环 | 十类分组体量依赖微信生态密度；AI 问答 Tab 我们已有小趣 Tab，不重复造 |
| 小红书搜索（来源：lanlanwork.com/blog/?post=10291、uisdc.com/hunter/0221498556、news.qq.com/rain/a/20240722A05WI400） | 引导页（历史+猜你想搜+搜索发现）+ 结果页（综合/用户/商品 Tab + 笔记类型筛选） | 结果页 Tab + **随关键词动态变化的二级筛选**（搜「订婚流程」出地域筛选、搜「送亲」出要素筛选） | 双列 masonry 与我们的媒体流同构 | 筛选条自动适配 query 语义 | 空结果给相关词引导 | ①**动态筛选维度**是我们单维内容类型筛选的直接升级方向（地点/圈子/时间维按 query 适配）②「用户」独立 Tab 证明人的检索是社区标配 ③引导页排行榜化 | 商品/电商 Tab 无对应场景；热词运营策略明确不复制（已登记禁止合成热榜） |
| Slack 搜索（来源：slack.com/help/articles/202528808、slack.com/blog/productivity/shrinking-the-haystack） | 统一搜索 + Messages/Files/People/Channels Tab + Filters/modifiers | `in:/from:/has:/before:` 修饰符 + 侧栏过滤器双轨；结果类型 Tab 完备 | 过滤器与修饰符互为镜像（可点选=可键入） | 结果上下文（跳转到消息所在会话位置） | 权限内可见性严格（搜不到无权限内容） | ①「可点选筛选 ⇄ 可键入修饰符」镜像设计（远期）②People/Channels 独立 Tab 再次印证 user 承载缺口 ③权限过滤在召回层做而非 UI 遮罩（我们 ES 查询过滤同构，需保持） | 企业级修饰符语法首发不需要；我们无 Files 域 |
| Apple HIG / WWDC26「Design intuitive search experiences」（来源：developer.apple.com/videos/play/wwdc2026/292、HIG Search fields） | 系统级搜索交互规范 | 聚焦即出最近搜索（inline）+ 预测联想（区分用户输入与补全部分）+ scope bar 轻量过滤 | 搜索可作为 Tab 常驻；建议数量克制让结果居前 | 联想即输即出，取消即时 | **无结果必须 content-unavailable 视图**（图标+标题+回显 query 便于发现 typo） | ①无结果视图回显 query（我们空态可加）②联想高亮区分输入/补全（精修项）③scope bar 优先于重型筛选④历史单条可滑删+全清（我们已具备） | tokens 交互对移动端中文输入收益低，暂不引入 |

综合结论：我们的两页架构 + 固定 Tab + 本地/云两阶段与标杆同构，**结构不落后**；差距集中在（a）对象完备性（user/tag）、（b）筛选维度动态化、（c）无结果/失效语义精细度、（d）交集个性化——(d) 恰是标杆无法复制的差异化空间（微信关系链个性化最接近，但其不做「为什么与你相关」的证据句外显）。

---

## 7. 阶段 4：交集驱动的差异化规划

**定位确认**：搜索 = 交集「核心承载」版块（成熟度矩阵 M5 口径）。交集必须是**可证实事实**（关系/共同圈子/共同实体/互动记录），禁止相似度推断伪装（`rankReasons` 才是推荐解释的位置，两者不得混同）。

**真相源决策（本轮裁定）**：
- 唯一真相源 = content-service `IntersectionService`（已有 `ObjectIntersections(viewerID, objectID, objectType, limit)` 读接口 + `/content/intersections/object` operation；primaryText 云端生成、不可展示 reason 云端淘汰、人级 reason 要求头像）。
- search-service 在 rank 后对 top-N hits 做 **intersection-attach**（viewer 已登录时，批量调 ObjectIntersections 或经共享 Reader 缓存），把 `connectionState`（connected/unconnected/intersection_lead 闭集）与 `intersectionReason{primaryText, intersectionId, dimension, class, sourceRef}` 写入 hit 信封——契约字段已在 `runtime/search/retrieve.go` 与 `_shared/search_contract.yaml` 预留，App 端消费链路已就绪并有 local_contract 断言。
- **若 WP-J 未落地前发版**：交集 Tab 必须降级为诚实态——隐藏 Tab 或显式「登录后查看你与结果的真实连接」空态，禁止维持现在的假空分组（GATE_BLOCK）。

**交集表达式**（遵守 `代表主体 + 数量/强度 + 行为/关系 + 对象 + 证据 + 行动`）：如「你和 **摄影圈小李** 同在 **光影摄影社**」→ 行动：打招呼/进圈子；「**3 位互关好友** 想去 **西湖**」→ 行动：查看想去名单/发起结伴。

### 交集规划矩阵

| 页面/场景 | 主对象 | 是否需要交集 | 交集证据 | 用户价值 | 表达方式 | 用户行动 | 冷启动方案 | 指标 |
|---|---|---|---|---|---|---|---|---|
| 结果页·交集 Tab | 全类型 hit | 核心承载 | connectionState + primaryText（互关/同圈/共同实体/互动事实） | 决策（值得连接谁）+ 行动 | 「已形成的连接」「值得探索的连接」两分组 + 证据句 | 打招呼/关注/加入/进入对象 | 无交集→「探索」分组只按对象热度，显式说明「暂无共同连接」；引导关注/加圈形成首个交集 | 交集句曝光→行动率（黄金指标3） |
| 结果页·全部 Tab 实体顶卡 | entity.Homepage | 场景增强 | 与该实体的 follow/visit/共同关注人数 | 解释（为何置顶）+ 决策 | 顶卡副行一句 primaryText | 关注/想去/进主页 | 无交集不显示副行（不留空壳） | 顶卡点击率分交集有无对比 |
| 默认页·猜你想搜 | TermHeat | 无需承载 | —（全局热度即事实） | 发现 | 现状保留 | 提交检索 | — | 灵感采纳率 |
| 默认页·热门圈子/地点 | Circle/Homepage | 场景增强（远期） | 「N 位好友在玩」需真实关系统计 | 发现+决策 | 先收口伪热榜（WP-I），交集增强推迟到真热度读模型之后 | 进圈/进主页 | 无关系数据回退纯热度 | 区块点击率 |
| location landing | location.place | 场景增强 | 想去/去过的互关好友 | 决策（是否提升/前往） | 证据句（有则显） | 提升为主页/发内容 | 无则只显临时卡 | 提升转化率 |
| 小趣 Tab | AssistantSearch | 无需承载 | —（AI 摘要保持公开线索定位） | 解释 | 现状 | 继续追问 | — | 摘要满意度 |

**禁止事项执行核验（2026-07-20 视觉核验后修正）**：端侧交集「拼装句」已删除（R-003/R-008 证据有效），但截图 04 暴露一处残留——「已形成的连接」分组对 `connectionState=connected` 的地点卡**无条件**贴端侧固定动作句（`searchFollowedReason`「你关注过」，圈子=「你已加入」，内容=「你互动过」，见 `search_network_results_page_state_helpers.dart` L251-284）。当前 connected 判定来源单一时勉强成立，但这是「状态→动作句」的端侧翻译：一旦云侧 connected 的成因多样化（关注/想去/发过内容提及），端侧句子即为错误陈述。WP-J 收口时「已形成的连接」卡的动作句也必须改读云侧事实文本（primaryText 或专用 connectionReason 字段），端侧只保留分组不生成语句。本规划不新增任何「与你相关」模糊标签；`ObjectIntersections` 天然只回 viewer 有权看的 reason（隐私边界云端裁决）。

---

## 8. 阶段 5：商用收口工作包（/dev 唯一清单增量）

> 编号衔接 `search-provider-routing-and-storage-topology/spec.md` WP 台账；WP-E/WP-G 维持既有登记（真集群容量 R-S06-S-1、写时长稳 R-S06-S-2 为发布阻断）。每包按 `local_contract / api_integration / user_acceptance` 三层声明证据。

| WP | 目标 | 关键改动 | 三层证据 | 优先级 |
|---|---|---|---|---|
| **WP-H 可用性与工程收口** | 消除「不可用」直接根因 | ①RemoteSearchRepository 断链修复（**本轮已完成**）+ provider 形态回归测试 ②wire 契约 json tag 修复（**本轮已完成**：`Reason/Evidence/Facet/DegradeSignal/Provenance/Citation` 小写化）+ 补「wire 字段小写」contract 测试防回归 ③ES 超时配置（**本轮已完成** gamma 四域+search `requestTimeoutMs: 5000`）+ 启动期 `EnsureIndex` 失败语义跨域统一（circle/entity/user `Fatalf` vs content/search WARN，二选一并全域对齐）④`search-service` recent 路由补 Prometheus 指标 ⑤`recent_search_receipts` 登记 storage.yaml ⑥手写路由改走 codegen descriptor ⑦`AppSearchRepository` 10 处静默 catch 结构化 + payload typed 化 ⑧修复 global_search 测试链（chat reexports 断链随并发会话收敛后复验） | local_contract：repository/provider 契约测试 + wire 小写断言；api_integration：`/search` 200 + rankReasons 小写透传 + `/search/recent` 指标断言；user_acceptance：默认页历史旅程复验 | P0（阻断） |
| **WP-I 环境数据 env-seed-first** | beta/gamma 搜什么都有 | ①search 域 `test_fixtures/scenarios` 扩充 + beta/gamma seed manifest 登记可检索对象集（内容/圈子/主页/用户/地点）与热搜词 seed ②`e2e.yaml` 引用不存在的 `search_query_remote.dart` 修正 ③热门圈子/地点：接真热度读模型（circle/entity 域各自 weekly_active 排序 Reader）或文案降级为「发现圈子/地点」 | local_contract：fixture parity；api_integration：gamma seed 后 `/search` 非空断言；user_acceptance：beta 人工验收「搜得到」 | P0（阻断） |
| **WP-J 交集 attach（差异化核心）** | 死字段变真字段 | ①search-service application 增 intersection-attach 阶段（登录 viewer × top-N hits 批量 `ObjectIntersections`，超时降级不阻塞主路径）②`connectionState` 闭集映射 ③未登录/无交集诚实空态文案 ④「已形成的连接」卡端侧固定动作句（你关注过/你已加入/你互动过）改读云侧事实文本，端侧只分组不生成语句（§7 修正项）⑤若延期：交集 Tab 降级开关 | local_contract：attach 单测（含降级）+ App 消费既有断言复用；api_integration：双服务真实交集数据断言；user_acceptance：交集 Tab 旅程（有/无交集两态） | P0（差异化阻断） |
| **WP-K 对象完备与语义收口** | 对象—页面双向闭环 + 「简陋」观感整改 | ①user 结果承载（全部 Tab「用户」分区，复用 user_search_projection）②tag 检索产品决策（进/不进统一索引，记录 CR）③结果失效反馈（落地 404 → 回搜索页 typed 提示 + degrade 反馈上报）④Tab 标签迁 `UITextConstants`/l10n ⑤动态筛选二期设计（借鉴小红书，先地点/圈子两维）⑥无结果视图回显 query + 相关词/行动引导（HIG，截图 05 依据）⑦默认页灵感区视觉丰富度：热门圈子/地点卡片化 + 热度徽标 + 封面（截图 01 依据）⑧联想直达行样式精修（截图 02 依据） | local_contract：Tab/分区/失效态 widget 测试；api_integration：user 对象召回断言；user_acceptance：跨对象旅程更新 + 视觉截图回归 | P1 |
| **WP-L 观测与黄金指标** | D5 从页面埋点升级到对象漏斗 | ①埋点 catalog（`ops/event_record/event_catalog.yaml`）metadata-first 增 search 专有事件（query_submit/result_impression/result_click/refine/zero_result）②三黄金指标落 SLS+大盘：有效搜索成功率（非空且有点击/停留）、提交→首个可操作结果 P95、结果→有效行动率 ③delivery-gate/pre-release-gate 增搜索专项 job（冒烟 `/search` 探针） | local_contract：事件契约测试；api_integration：指标可读断言；user_acceptance：漏斗对账演练 | P1 |
| **WP-E/WP-G（沿用）** | 发布准出 | 真集群容量校准（R-S06-S-1）、写时增量长稳（R-S06-S-2）、App api_integration 从零补齐（Remote 契约 × gamma 真栈）、无版本 path 冷启动衍生验收（CR-20260717-109 探针含 POST /search）、6 个 pending GWT 补录 | 按既有登记 | P0（发布前） |

**验收顺序**：WP-H → WP-I →（并行 WP-J / WP-K）→ WP-L → WP-E/G 准出。所有 pending GWT（full-screen-search-shell-and-entry 2、search-intersection-consumption 2、circle-facet/local-chat/recent-sync/circle-group-hybrid/local-lifecycle/routing-policy/taxonomy 各 1）在对应 WP 关闭时同步补 recorded。

---

## 9. 六维度结论

| 维度 | 现状 | 商用差距 | 承接 WP |
|---|---|---|---|
| D1 功能与旅程 | 两页+落地页旅程骨架完整、部分失败/降级/取消语义齐备 | user/tag 对象缺承载；结果失效无反馈；热榜伪装 | WP-I/K |
| D2 DDD 与 metadata | 5 对象单轨、7 operation codegen、零硬编码 path | 死字段（交集）、receipts 未登记、手写路由 | WP-H/J |
| D3 UX 与页面 | token 化良好（`_SearchTokens` 四级字体/三级颜色）；**视觉未核验** | Tab 硬编码中文；双色/真机核验缺失；无结果视图可精修 | WP-K + 视觉复验 |
| D4 非功能 | 服务侧背压/缓存/可重复性已冻结；local 压测 NO-GO 结论在案 | 真集群 measured 缺失（发布阻断）；App 侧搜索页 TTI 无口径 | WP-E/G |
| D5 可观测与运营 | 服务 SLO 8 SLI + 告警 6 条 + 推荐回流闭环；页面曝光/停留/归因链有 local 证据 | 无 search 专有事件目录；三黄金指标无落点；发布门禁无搜索 job | WP-L |
| D6 测试 | 服务 local_contract ~23 + api_integration ~25；App local_contract 33+；UA journey recorded | **App api_integration = 0**；global_search 测试链断（外部）；对象状态机（index stale/tombstone）无测试 | WP-H/K + WP-E/G |

## 10. 剩余风险与 backlog 同步

- 维持未关闭：R-S06-S-1（真集群容量，发布阻断）、R-S06-S-2（写时长稳）、无版本 path 冷启动衍生验收（挂 R-LOGIN 条目）、WP-F 线上 AB 收益长稳尾巴。
- 本轮新识别（待用户确认后登记 backlog，遵守 16 号军规）：
  1. **交集 attach 缺失**（死契约字段 → 假空态交集 Tab）：事项/原因/影响见 §7；建议登记为 R-S08。
  2. **工作树跨会话断链使 App 不可构建**：`app_providers.dart` 等文件半迁移（非搜索域根因，搜索域内 RemoteSearchRepository 断链本轮已修）；建议按会话协调机制处理而非搜索 backlog。
  3. **beta/gamma 搜索 seed 缺失**：环境内无可检索种子数据；建议登记为 R-S09。
- 本轮代码改动（全部为排查中确认的断链/契约 bug 修复）：
  1. `quwoquan_app/lib/core/services/remote_search_repository.dart`：补 `search_models.dart` import、清 2 个冗余 import；`dart analyze` 0 error。
  2. `quwoquan_service/runtime/search/core.go`：`Reason/Evidence/Facet/DegradeSignal/Provenance/Citation` 补小写 json tag（端云契约漂移，remote 下排序理由/降级信号静默全丢的根因）；`go vet` + `go test ./runtime/search/... ./services/search-service/... ./services/assistant-service/internal/application/tool/...` 全绿；wire 输出经 marshal + 容器内热替换 + 经网关三重验证小写。
  3. `quwoquan_service/services/{search,circle,entity,user,content}-service/configs/gamma/config.yaml`：ES 段补 `requestTimeoutMs: 5000`（gamma-local 模拟 ES 慢导致 100% 503 / circle-service crash 的环境性修复）。
  4. `quwoquan_app/lib/core/providers/app_providers.dart`：修复对 `user_profile_repository_{contract,remote}.dart` 两个 `part of` 文件的非法 import（并发 user 域拆分半成品），改 import 宿主库——这是视觉核验编译链的最后阻断点。
  5. 临时视觉 harness `quwoquan_app/test/visual_probe_search_capture_test.dart` 已完成使命并删除；最终版源码归档 `.qwq_output/env/repo/runs/search-visual-audit/visual_probe_search_capture_test.dart.txt`（12 张截图同目录）。
