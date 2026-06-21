# L1 Capability: global-search-experience

## 节点定位

- `L1_domain_service`: `global-search-experience`

该节点是 App 内统一搜索入口、两段式搜索建议、独立网络结果页、搜索记录与“小趣搜” assistant 结果的唯一能力归属。
它不再挂靠 `discovery-content`，也不再沿用 `chat-conversation/contact-and-session-governance/contact-search-index*` 这类记录节点。

## 背景与动机

当前搜索能力存在四个结构性问题：

1. 入口分散：首页、聊天、群组、助手的搜索入口不一致，且绝大多数页面没有统一全局搜索入口。
2. 壳层失真：现有 `GlobalSearchSheet` 仍是原型态，本质是本地 mock 数据过滤，没有形成可商用的全屏全局搜索体验。
3. 领域边界漂移：最新 UX 已冻结“联系人直达会话”，但记录文档仍混用联系人、社交关系与用户主页搜索，导致 contract 挂载混乱。
4. 记录节点失效：旧的 chat 搜索节点只覆盖联系人局部能力，无法承接内容、群组、聊天记录、网络结果页与 `小趣搜` assistant 结果统一入口。

本次 PRD 的目标，是把“全局搜索”从记录局部能力中抽离，升级为独立一级能力域，并把首页与搜索中的用户词统一收口为 `群组`。

## 2026-03-27 基线扩展

在既有两段式全局搜索体验基线之上，本轮 baseline 额外冻结以下能力边界：

1. 产品与页面层只允许一个 canonical 搜索接口：`search(request)`；搜索建议与正式结果共用同一套 contract，只用 `mode=suggest|result` 区分。
2. 可搜索对象必须挂到统一的 object taxonomy 下，不再以 `searchContacts`、`searchMessages`、`searchHomepages` 这类产品语义接口作为长期真相源。
3. `chat.contact`、`chat.conversation`、`chat.message` 冻结为 `local_only` 搜索对象；聊天相关搜索不再把云侧搜索接口作为产品主路径。
4. `circle.group` 冻结为 `hybrid_remote_fallback_local`：云侧优先，云侧失败或返回 0 结果时回退端侧本地全量结果。
5. 云侧搜索方案纳入本 L1 范围：写模型继续按业务域存储，搜索读路径走独立 read model / projection，并冻结读写分离、多读切片、每切片独立弹性与高并发成本控制原则。
6. 未来允许引入更高性能的统一搜索读库，但该读库只作为可替换的搜索读侧实现，不作为本期统一迁移业务主存储的承诺。
7. canonical `search(request)` 必须同时具备页面消费接口与 AI agent 检索 tool 接口兼容性；接口形态应尽量接近 web search：以单个 `query` 关键词串作为主输入，辅以少量 typed 条件，便于模型做“主题拆分 -> 关键词检索 -> 汇总回答”。
8. 同一接口必须既能召回 `web.document`，也能召回趣我圈内的内容、关系、群组与实体对象；`objectTypes`、filters、sort hints、limit 等条件允许由 AI 模型生成，但必须受 metadata typed schema、allowlist 与资源边界约束。

## 2026-06-15 架构决定：独立 search-service + 专用 ES/OpenSearch 集群

本节为最新冻结决定。凡与上文/本 L1 下属 L2、L3 中“本期不新增统一 `/v1/search`”“不指定搜索引擎/向量库”“统一高性能读库不在本期落地”等表述冲突处，一律以本节为准（零历史兼容、单一真相源、当前按未上线处理）。

1. 统一搜索读库本期落地为**专用 ES/OpenSearch 集群**（复用 `quwoquan_service/runtime/search/es`），作为派生读模型，**不承担业务主存储**真相源。
2. 新建**独立可部署 `search-service`**（`domain=search`，经 `/qwq-extend new-service` 脚手架创建），承载 canonical `search(request)` 的云侧统一入口 `POST /v1/search`（`mode=suggest|result`）与 `POST /v1/search/feedback`，复用 `runtime/search.Retrieve` 作为唯一跨类型排序真相源。
3. 召回后端：**ES 为主、native store 为透明回退**（`FallbackBackend`，Primary=ES，Fallback=native），对所有调用方透明；ES 故障整体降级 native，不阻塞主路径。
4. 各域（`content/entity/circle/user/integration`）数据经统一 indexer 灌入同一 ES 索引 `quwoquan_objects`；原各域 `/v1/.../search` 只读路由保留为 indexer 数据源/内部回退，**不再作为 App 主搜索路径**。
5. 部署：alpha/beta/gamma/prod 四环境声明专用搜索 ES 集群与 `search-service` 进程，`beta=gamma=prod` 拓扑逐字一致。
6. 不变量：canonical contract 与 object taxonomy 不变；ES 仅替换读侧实现；私有对象（`chat.*`）仍 `local_only`，绝不上云做跨用户召回。

## 2026-06-16 商用闭环（已落地事实 + 商用需求口径）

本节把搜索商用主链路已落地的事实纳入正式规格，并统一商用需求口径，作为后续各 spec 与 acceptance 改写的依据。凡与上文旧口径（如把 `integration.location_poi` 当统一 result 对象、把分域搜索接口当 App 主路径）冲突处，以本节为准。

### 已落地主链路（来自 backlog 已验证证据）

1. 独立可部署 `search-service`（`domain=search`，`POST /v1/search`、`POST /v1/search/feedback`，端口 18095）已实例化进 local-gamma，ES-enabled，经网关真实冒烟 200，返回信封含 `requestId / rankingVersion / experimentBucket` 与 hit 级 `rankReasons / rankPosition`；feedback 返回 202（R-S03/R-S06-S）。
2. 各域灌数完成（R-S05a~e）：`content.post / entity.homepage / circle.circle / circle.group / user.profile` 经统一 indexer 灌入 `quwoquan_objects`；新增第一方地点对象 `location.place`（复用 geo 维度，与 `entity.homepage` 互斥单源）。
3. App remote `/v1/search` 接线完成（R-S06）：`RemoteSearchRepository` 走 `CloudHttpClient` + codegen path，透传 `rankReasons / rankPosition / coverWidth / coverHeight / connectionState / intersectionReason / relatedTerms`，`searchRepositoryProvider` 按数据源切换。
4. 反馈/热力/排序完成（R-S07）：`FeedbackSink / QueryLogSink`、`queryheat` term-heat 派生读模型 `rm_search_term_heat`(TTL 86400)、排序透明化、SLO/告警/AB 切桶。
5. 搜索信号注入推荐 Feed 完成（R-S07-5，local_contract + 真实 Redis 双服务 api_integration 已证明）：search → Redis Stream `events.search.recommendation_signals` → content-service consumer → `rm_recommend_feature` → FeatureStore → RuleScorer；线上 AB 收益显著性与真集群差异为长稳观察项，不再作为链路闭环缺口。

### 商用需求口径（统一真相源）

- **两段式数据边界**：`suggest` 阶段做本地快速检索（`chat.contact / chat.conversation / chat.message`、`circle.group` 本地命名空间），即时返回；`result` 阶段的**最终结果只来自云侧**——`content.post`、`entity.homepage`、`location.place`、相关搜索词、小趣（assistant）。本地对象不进入 `result` 最终结果集。
- **反馈推荐闭环**：查询日志 / term-heat 既参与搜索结果页排序（R-S07，已闭环），也经 Redis 注入推荐 Feed 排序（R-S07-5，待真实 Redis 双服务 api_integration）。
- **性能 / 稳定 / 准确**：`suggest` 本地即时；`result` 首批分组 P95 ≤ 1.5s；单域降级不阻塞整页；召回 ES 主 + native 透明回退；敏感 query 阻断；相关性排序透明化（`rankReasons / rankPosition / rankingVersion / experimentBucket`）。

### 商用完整功能规格（2026-06-16 `/plan-review` 刷新）

本段把微信 / 小红书式两段搜索体验、Apple HIG 的即时反馈与可恢复交互，以及 Elastic/OpenSearch 业界性能实践落成硬规格。任何后续 `/dev` 不得用局部实现或 demo fallback 替代本段合同。

#### A. 两阶段检索与结果合成合同

| 阶段 | 数据源 | 可出现对象 | 结果用途 | 禁止 |
|---|---|---|---|---|
| `suggest` 本地快速检索 | 端侧本地索引 / 本地缓存 / 最近搜索 | `chat.contact`、`chat.conversation`、`chat.message`、已加入/已关注/已互动的本地命名空间对象、推荐搜索词 | 输入过程即时反馈、直达已有对象、进入“搜索网络结果”入口 | 禁止把未连接云侧发现对象、图片/视频/长文正式结果塞入 suggest；禁止网络请求阻塞本地输入反馈 |
| `result` 云侧最终检索 | `search-service` + ES/OpenSearch 派生读库 + queryheat + assistant | `content.post`、`entity.homepage`、`location.place`、相关搜索词、`小趣` | 独立网络结果页正式结果与固定 Tab 展示 | 禁止把 `chat.*` 或任何本地-only 对象带入最终结果；禁止端侧 fallback 编造云侧空结果；禁止分域旧接口成为 App 主路径 |

合成规则：

1. **同一 query 的用户过程可以同时出现本地 suggest 和云侧 result，但二者只在 UI 旅程上衔接，不在最终结果集混合。** 点击“搜索网络结果”后，正式结果页只渲染云侧 `SearchResponse` 与 assistant 结果；上一页 offstage 的本地命中不参与结果页数据模型、排序或埋点对象列表。
2. **本地对象只贡献行为上下文，不贡献 result hit。** 端侧可以携带稳定 `sessionId / requestId / referralSource / feedRequestId` 用于归因与 AB 粘性，但不得把本地 `chat.*` hit 注入云侧排序或 result UI。
3. **云侧对象合并必须以稳定外部身份为准。** `objectType + objectId` 是去重与 tie-break 键；`location.place` 与 `entity.homepage` 互斥单源，同一地点已提升为 entity 时不得重复出现 location.place。
4. **相关搜索词是云侧结果的一部分。** remote 模式优先消费 `relatedTerms`；mock 模式仅作为 alpha 预览态派生，不得成为 beta/gamma/prod 的第二真相源。

#### B. 性能、稳定与弹性规格

| 链路 | 商用目标 | 业界实践吸收 |
|---|---|---|
| App suggest | 本地首批反馈肉眼即时；输入 debounce 不阻塞主线程；旧请求晚返回不得覆盖新 query | 本地索引/缓存优先，网络 result 与输入过程解耦；连续输入只保留最新 query |
| App result | `result` 首批可见 P95 ≤ 1.5s；弱网显示骨架/空态/错误态/降级态 | 请求超时、取消、乱序保护、重试入口、四态齐全 |
| search-service | 有 in-flight 上限、下游 timeout、typed 429/503、cache hit metric、degrade reason | 背压优先于雪崩；连接池/队列/超时有上限；异步 query log/Redis publish 不拖主路径 |
| ES/OpenSearch | 真集群 measured RPS/P95/P99、饱和点、shard/replica/refresh/bulk 阈值必须回填 | 避免 oversharding；单 shard 目标 10GB–50GB；至少约半内存留 filesystem cache；写入高峰提高 refresh_interval；禁深分页/脚本排序/无界 wildcard |
| Redis / 推荐信号 | Redis 失败不反压搜索；consumer lag 可观测；搜索词特征 freshness 可查询 | Redis publish best-effort；broker-side lag 指标；特征投影幂等 |

#### C. 准确性、可解释与可重复性规格

1. **排序稳定**：统一使用 `Score desc → Title asc → ObjectType/Target asc → ObjectID asc` 或等价稳定全序；ES 查询体必须显式稳定 sort/tie-break；多副本真集群使用稳定 `preference` 验证同 query 不跳变。
2. **相关性透明**：每个 hit 必须有可审计的 `rankReasons / rankPosition / matchedTerms / evidence`；`rankingVersion / experimentBucket / policyVersion / indexVersion` 用于解释合法变化。
3. **召回质量**：query normalization、字段权重、tag/entity 信号、term-heat boost、freshness boost 必须在同一 ranking pipeline 中合成，禁止 result 页另造排序。
4. **安全与权限**：敏感 query、未授权私有对象、跨账号本地索引必须 fail-closed；权限错误必须结构化，不得以空结果掩盖。

#### D. 搜索词热力与推荐闭环规格

1. `/v1/search` 成功后记录 query log（best-effort，不阻塞主路径）；`/v1/search/feedback` 记录点击/曝光/反馈。
2. `queryheat` 基于查询次数、点击、共现、时间衰减计算 `rm_search_term_heat`，TTL 与索引在 metadata/storage 中声明。
3. term-heat 同时用于搜索结果页排序和相关搜索词生成；`experimentBucket=control|term_heat` 必须可分桶查询。
4. 搜索信号经 Redis Stream 投影到 `rm_recommend_feature.userFeatures.searchTermAffinity`，并被 Feed scorer 消费；线上 AB 收益为发布后观察项，但链路可消费性必须在 api_integration/local_contract 中证明。

### result 阶段云侧对象 taxonomy（澄清）

`result` 阶段统一 result 对象**只含**：`content.post`、`entity.homepage`、`location.place`、相关搜索词、小趣（assistant）。其余约束：

- `chat.contact / chat.conversation / chat.message`：`local_only`，只在 `suggest` 本地命名空间出现，绝不进 `result` 云侧最终结果。
- `circle.group`：`hybrid_remote_fallback_local`，作为 suggest 本地命名空间与发现区消费对象，不作为 result 最终独立对象类目的新增项。
- `integration.location_poi`：澄清为**创作 / 附近场景的外部 gateway 数据源**（POI picker、发布定位、附近搜索），**不作为统一 result 对象**进入 canonical `/v1/search` 召回；第一方地点 result 对象由 `location.place` 承载（同一地点只出现一次，单一真相源）。

## 目标用户

- 需要从任一一级页面快速查找联系人、聊天记录、内容与群组结果的活跃用户。
- 习惯用微信式两段搜索体验完成“先联想、再进入网络结果页”的高频用户。
- 需要在站内搜索后继续查看“小趣搜” assistant 结果的用户。
- 需要在不增加额外学习成本的前提下统一维护搜索路由、埋点、请求上下文和结果编排的平台与前端团队。

## 能力边界

`global-search-experience` 负责：

- 全局搜索的全屏壳层、一级入口、默认上下文与返回路径。
- 两段式搜索体验：初始记录页、输入后的实时联想页、以及独立网络结果页。
- 联系人/聊天记录直达会话、网络结果进入独立结果页的统一跳转语义。
- 搜索里的 `群组` 结果类型，以及网络结果页内 `小趣搜 + 群组分类 facet` 的顶层组织。
- 搜索记录的本地存储与云端同步语义。
- 搜索页内的语音 ASR 到文本查询转换。
- “小趣搜” assistant 结果与引用跳转语义。
- 搜索相关 `route / surface / request_context` 的 metadata 真相源收口。
- canonical `search(request)` 接口、`mode=suggest|result`、`objectTypes` 与统一搜索结果模型。
- 可搜索对象的执行策略：`local_only / remote_only / hybrid_remote_fallback_local`。
- 本地聊天搜索生命周期、账号隔离与删除同步规则。
- 云侧搜索读模型、读写分离、多读切片、每切片独立弹性与高并发成本控制原则。
- 面向 AI agent 的 tool-facing search contract、typed filter schema 与模型可生成条件边界。
- 面向 AI 的 web-search-like query-first 检索语义，以及 `web.document + quwoquan objects` 的统一召回接口。

`global-search-experience` 不负责：

- 业务写模型的存储引擎迁移（写模型仍按业务域存储；ES 仅作派生搜索读库）。
- 低存储设备的精细阈值治理与自动淘汰策略。
- 助手 runtime / skill / prompt 的垂类逻辑改造；但 search contract 的 tool-facing 兼容性属于本 L1 范围。
- 密信账号分割、私密账号策略本身。
- 各业务详情页自身的页面内二级搜索。
- 面向用户新增“实体”作为新的搜索总类目。

## 关键 Journey

本 L1 当前冻结 2 个 `L2` 容器：

| L2 | 类型 | 说明 |
|---|---|---|
| `cross-domain-search-journey` | 用户旅程 | 从任一一级入口进入两段式全屏搜索，完成记录管理、实时联想、网络结果浏览、最近搜索同步与小趣搜 assistant 结果查看 |
| `search-provider-routing-and-storage-topology` | 治理 / 架构 | 冻结统一搜索 contract、对象 taxonomy、执行策略、fallback 语义、本地搜索生命周期与云侧搜索读模型弹性拓扑 |

## 领域服务与业务对象

| 领域 | 业务对象 | 本 L1 角色 |
|---|---|---|
| `content/post` | `Post`、`Comment`、文章/图片/视频/动态内容投影 | 作为内容结果来源 |
| `messages/conversation` | `Conversation`、`Message` | 作为消息与会话结果来源 |
| `social/circle` | `Circle`、`CircleSectionConfig`、分类投影 | 作为群组结果与群组分类 facet 的真相源 |
| `user/user_profile` + `user/follow_edge` | `UserProfile`、`ProfileSubject`、身份补充读模型 | 作为联系人身份补充与后续扩展来源 |
| `assistant/assistant_run` | `AssistantRun`、assistant 搜索结果/引用投影 | 作为网络结果页左侧 `小趣搜` tab 的结果来源，并承接后续 assistant continuation |
| `external/web_document` | `WebDocument`、网页标题/摘要/链接投影 | 作为 AI agent 与 assistant 回答中的外部网页召回来源 |
| `entity/homepage` | `Homepage`、主页摘要与主页搜索项投影 | 作为共享主页搜索对象与页面内 picker 搜索来源；已绑定 canonicalEntity 的地点由其承载 |
| `content/place_snapshot` | `location.place`（第一方地点快照，复用 geo 维度） | 作为 `result` 阶段第一方地点 result 对象；与 `entity.homepage` 互斥单源 |
| `integration/location` | `LocationPoi` | 仅作创作 / 附近场景的外部 gateway 数据源（POI picker、发布定位、附近搜索），不作为统一 result 对象 |
| `_shared` metadata | `app_routes`、`ui_surfaces`、`request_context` | 作为全局搜索路由、surface、page context 真相源 |
| `_shared/search` metadata | `SearchRequest`、`SearchResponse`、`SearchObjectType`、`SearchExecutionStrategy` | 作为统一搜索 contract、对象 taxonomy 与执行策略真相源 |

## 2026-06 搜索分组 UX 主线

搜索体验升级后，页面必须以「类别 × 连接状态 × 页面状态」作为 UX 真相源，而不是以旧的
`主页 / 消息 / 内容 / 群组分类 facet` 作为一级用户心智。

### 类别与连接状态

固定搜索类别为：

```text
交集｜圈子｜地点｜人｜图片｜视频｜长文
```

每个类别都必须拆成两类结果：

| 连接状态 | 定义 | 全部页展示规则 |
|---|---|---|
| 已连接 / 已互动 | 用户已经加入、关注、联系、讨论过，或对内容赞/评/转过 | 每个类别最多只出现一组，按固定顺序放在最前面的「已连接区」 |
| 未连接 / 未互动 | 用户尚未加入、关注、联系或互动，但与 query 匹配 | 进入「发现区」，按匹配池总量和相关度比例做多组混排，同一组内只放同类 |

已连接区固定顺序：

```text
聊天记录 → 联系人 → 已加入圈子 → 已关注地点 → 已关注的人 → 已互动内容
```

发现区可出现：

```text
交集 → 圈子 → 地点 → 人 → 图片 → 视频 → 长文
```

发现区不是一个大乱序列表。它必须满足：

1. 同类成组：每一组只展示一种类别。
2. 多组混排：未连接结果可出现多个同类组。
3. 比例编排：组出现频率接近各类别匹配池数量与相关度占比。
4. 无「查看更多」：用户继续下滑加载下一批组。

### 四类页面状态覆盖矩阵

每个搜索类别都必须覆盖以下四种状态：

| 类别 | 默认搜索页 | 输入过程中 | 全部 Tab | 指定类别 Tab |
|---|---|---|---|---|
| 交集 | `今日交集` 激发搜索，一行 4 个 | 不展示正式交集结果 | 作为发现区分组；已连接线索优先进入已连接区 | `交集` Tab：概览 + 推荐区 + 交集发现流 |
| 圈子 | `热门圈子`，三列 | 只展示 `已加入圈子` | 已加入圈子在已连接区只出现一组；未加入圈子按比例进入发现区多个分组 | 无单独圈子 Tab；圈子在 `交集` 与 `全部` 中消费 |
| 地点 | `热门地点`，三列；禁止使用实体/对象/主页等命名 | 只展示 `已关注地点` | 已关注地点在已连接区只出现一组；未关注地点按比例进入发现区多个分组 | 无单独地点 Tab；地点在 `交集` 与 `全部` 中消费 |
| 人 | `同趣的人`，头像在上、三行文字 | 展示 `联系人` 与 `已关注的人`，均为已连接/已关注对象 | 联系人、已关注的人在已连接区各只出现一组；未连接的人按比例进入发现区 | 无单独人 Tab；人在 `交集` 与 `全部` 中消费 |
| 图片 | 不展示正式图片结果 | 不展示图片结果 | 已互动图片进入已连接区的 `已互动内容`；未互动图片按比例进入发现区图片组 | `图片` Tab：双列瀑布流，不显示图片组标题 |
| 视频 | 不展示正式视频结果 | 不展示视频结果 | 已互动视频进入已连接区的 `已互动内容`；未互动视频按比例进入发现区视频组 | `视频` Tab：双列瀑布流，不显示视频组标题 |
| 长文 | 不展示正式长文结果 | 不展示长文结果 | 已互动长文进入已连接区的 `已互动内容`；未互动长文按比例进入发现区长文组 | `长文` Tab：单列阅读流，不显示长文组标题 |

### 固定 Tab

点击搜索后的正式结果页固定 Tab 为：

```text
小趣｜全部｜交集｜图片｜视频｜长文
```

默认进入 `全部`。`小趣` 是单独结果页，不参与默认页，不参与 `全部` 的分组混排。

### connectionState 零过渡约束（G2 对齐，GATE_BLOCK）

**禁止**端侧推断 `connectionState` 或本地拼装 `primaryText`；禁止用 UI 规则生成第二套 search contract 字段。

| 条件 | 行为 |
|---|---|
| hit 含 `connectionState` + `intersectionReason.primaryText` | 正常进入已连接区 / 发现区 / 交集 Tab |
| hit 缺 `connectionState` 或缺 `intersectionReason.primaryText` | **不进入**交集 Tab、不进入发现区交集 lead 分组、不占位不造假 |
| 搜索首页「今日交集」 | 仅展示 provider 已回灌完整交集字段的 mock/remote hit；无字段则隐藏该行 |

alpha 阶段由 **mock/remote provider 回灌** 完整字段，不得用客户端推断顶替服务端缺口。

## 功能范围

### In Scope

- 新建独立 `L1_domain_service`，承接全局搜索全部产品与文档治理。
- 全屏搜索首页初始态：搜索框、最近搜索、今日交集、热门圈子、热门地点、同趣的人。
- 输入后的实时联想页：严格按 `联系人 / 聊天记录 / 已加入圈子 / 已关注地点 / 已关注的人 / 推荐搜索词` 六段组织；无命中分组隐藏。
- 输入过程中只定位已有对象；未连接圈子、未关注地点、未连接的人，以及图片/视频/长文正式结果不得出现。
- 独立网络结果页：顶部保留搜索框，顶部固定 tab 为 `小趣 / 全部 / 交集 / 图片 / 视频 / 长文`。
- `全部` Tab 分为已连接区与发现区；已连接每类只出现一组，发现区同类成组、按比例混排、无查看更多。
- `交集` Tab 展示交集概览、交集推荐区和交集发现流，每张卡必须展示交集原因。
- `图片 / 视频 / 长文` Tab 只展示对应内容消费流，不再显示同名组标题。
- 记录搜索同步：本地存储 + 云端同步，用户手动清除前持续保留。
- 语音入口：只做 ASR 转搜索词。
- 统一 object taxonomy：`web.document`、`chat.contact`、`chat.conversation`、`chat.message`、`circle.group`、`circle.circle`、`content.post`、`entity.homepage`、`user.profile`、`location.place`。`result` 阶段云侧最终结果只含 `content.post / entity.homepage / location.place / 相关搜索词 / 小趣`（详见「2026-06-16 商用闭环」）；`integration.location_poi` 仅作创作 / 附近场景的外部 gateway 数据源，不作为统一 result 对象。
- 聊天对象端侧本地搜索与 `circle.group` 云优先 / 本地 fallback 搜索。
- 云侧搜索读模型、读写分离、多读切片、独立弹性与缓存/降级成本原则。
- 统一 search contract 生成 App / cloud client / AI agent tool 共用 schema，避免端云与 agent 维护第二套搜索接口。
- 统一搜索 contract 采用 query-first 的 web-search-like 形态，优先让 AI 生成关键词串和少量简单条件，而不是复杂嵌套 DSL。

### Out of Scope

- AI 结果进入联想页分组混排。
- 语音语义理解、语音直达助手推理。
- 密信按账号隔离的后续扩展。
- 独立 `channel` 主实体与新领域服务。
- 业务主存储向 ES 迁移（ES 仅作派生搜索读库，业务写模型不迁移）。

## 约束与适用边界

- 全局搜索必须遵循 `/.cursor/rules/07-ios-native-ux.mdc`，作为唯一允许的全屏全局浮层。
- `path / operation / surface / route / decoder context` 必须以 metadata 为唯一真相源。
- AI 模型只能生成 metadata schema 允许的 objectTypes、filters、sort hints 与 limit，不能生成自由 SQL / 脚本 / 任意执行表达式。
- `search(request)` 必须优先采用单一 `query` + 扁平 typed filters 的简单结构，不设计复杂布尔嵌套、脚本排序或图查询表达式，避免 AI 难以拆解。
- 当前两段式搜索首段“人”结果拆分为 `联系人` 与 `已关注的人`：联系人以直达会话为主，已关注的人以个人关系为主。
- 首页和搜索中的用户可见圈层词使用 `圈子` / `已加入圈子`，多人会话仍使用 `聊天记录` 或具体讨论名称。
- 圈子分类 facet 不再作为正式结果页一级 Tab；类别过滤必须服从固定 Tab 与分组规则。
- `小趣` 必须通过 assistant typed contract 提供真实结果，不能退回为字符串 handoff 占位。
- 本次按“一把上线”处理，不保留记录搜索节点并行治理。

## 对标输入与吸收结论

| 对标 | 借鉴点 | 本次吸收 |
|---|---|---|
| 微信搜索首页 | 全屏壳层、顶部搜索框、最近搜索、实时联想 | 吸收为两段式搜索基线 |
| 微信聊天/联系人搜索结果 | 联系人与聊天记录分段、页内展开更多 | 吸收为联想页结构与直达会话交互 |
| 微信内容搜索结果 | 内容结果与分类联合展示 | 吸收为独立网络结果页与群组分类 facet 联动 |

## 角色分工

| 角色 | 职责 |
|---|---|
| `global-search-experience` | 产品体验、全局壳层、两段式联想编排、记录与网络结果治理 |
| `search-provider-routing-and-storage-topology` | 统一搜索 contract、对象 taxonomy、provider routing、fallback 与云侧搜索存储弹性治理 |
| `content` | 提供内容搜索对象与结果跳转契约 |
| `messages` | 提供联系人/聊天记录结果对象与会话直达契约 |
| `user` | 提供用户身份补充信息与后续人关系扩展真相源 |
| `circle` | 提供群组结果与群组分类 facet 投影 |
| `entity` | 提供共享主页搜索对象与 picker 场景结果真相源 |
| `integration` | 提供位置搜索对象与外部 POI 查询能力 |
| `assistant` | 提供 `小趣搜` assistant 结果、摘要与引用 |
| `search-service` | 承载云侧统一 `POST /v1/search`、`POST /v1/search/feedback`；装配 ES 主 + native 回退后端，运行统一 indexer 灌数到 `quwoquan_objects` 索引 |
| `_shared` metadata | 承载路由、surface、request context、search contract 真相源 |

## 既有 Story 覆盖矩阵

| 记录节点或实现 | 处理方式 | 新归属 |
|---|---|---|
| `chat-conversation/contact-and-session-governance/contact-search-index` | 从特性树删除，不再保留 | `local-chat-search-contract` |
| `chat-conversation/contact-and-session-governance/contact-search-index--search-query-contract` | 从特性树删除，不再保留 | `local-chat-search-contract` + `multi-domain-result-composition` |
| 现有 `GlobalSearchSheet` 原型 | 保留为待替换实现，不再作为产品真相源 | `full-screen-search-shell-and-entry` |

## 数据生命周期合同

- 最近搜索记录为 `query + launch_context + category_context + timestamp` 的组合。
- 最近搜索同时落本地与云端；本期不冻结自动过期时间，用户主动清除前持续保留。
- `小趣搜` 复用当前全局搜索 query，不额外新增一套 AI query 记录模型；若用户继续进入 assistant 对话，对话内容保存在小趣私人助手会话中。
- 语音输入只生成文本搜索词，不额外保存原始音频作为搜索记录的一部分。
- 本地聊天搜索索引在用户登出后不清空，但必须按 owner / sub account 隔离；切换子账号不可读到其他子账号分区。
- 聊天消息撤回、删除或本地显式清理时，必须同步删除对应本地搜索索引项。
- 云端消息 TTL 与端侧本地长期保留可不一致；本期端侧生命周期以“用户主动删除”为主，精细生命周期与存储压力治理后续单独治理。

## 小趣 / 权限 / 分享边界

- 当前账号或当前登录子账号可见范围内的对象，都允许出现在搜索结果中。
- 本期不在账号内部再做更细权限裁剪；后续密信通过账号分割解决。
- `小趣搜` 仅存在于独立网络结果页左侧 tab，不进入联系人/聊天记录实时联想分组。
- 本期不引入搜索结果对外分享链路。

## 非功能目标

### SLO / KPI

- 搜索页打开即时完成，最近搜索与初始壳层优先可见。
- `suggest` 本地快速检索首批反馈肉眼即时，不等待云侧 result；本地索引/缓存异常时回落最近搜索与推荐词，不阻断输入。
- `result` 云侧正式结果首批分组 P95 ≤ 1.5s；P99、错误率、降级率、Redis lag、index freshness 以 `search_slo.yaml#load_model` 为唯一目标来源。
- 单域失败不阻塞其它分组返回；ES/Redis/search-service 故障必须表现为 typed degrade / best-effort / 快速失败，而不是挂起或雪崩。
- 搜索主路径完成率目标 > 95%。
- 结果点击进入详情成功率 > 99%；搜索后推荐特征投影 freshness 与 Feed 消费命中率可查询。
- 同一 viewer/session/query/filter 在同一 `rankingVersion / policyVersion / indexVersion` 下 TopN 不无故跳变；重复查询 golden diff 必须 0 跳变，真集群多副本需验证稳定 `preference`。

### 弱网 / 并发 / 容量

- 默认按移动弱网场景设计。
- 一次综合搜索最多 fan-out 到 `content / user-social / messages / circle` 四个域。
- 首屏各分组只返回少量结果，更多结果通过二跳页面承接。
- `suggest` 模式优先 lexical-only，避免在最高 QPS 路径默认启用 semantic/vector 成本。
- 云侧搜索读路径必须与业务写路径分离，不允许长期直接扫描主业务集合承担高并发搜索流量。
- 搜索读模型按 objectType 拆分，多读切片支持独立副本数、独立缓存、独立限流与独立弹性。
- `circle.group` 允许在云侧失败或 0 结果时回退端侧本地全量结果，并以降级态承接，不阻塞整页。
- tool-facing contract 必须保持 typed、可审计、幂等读语义与资源上限，便于 AI agent 安全调用。
- AI 在 assistant 问答中应能多次调用同一检索 tool，分别生成网页关键词和站内关键词；接口设计必须支持“小而简单的多次查询”优于“一次巨大复杂查询”。
- 真集群商用前必须完成 measured 容量校准：shard/replica/data node、heap/page cache、refresh_interval、bulk batch、search threadpool/circuit breaker、最大稳定 RPS 与扩容阈值，不得用 local-gamma 单节点模拟结果替代。
- 查询成本必须受控：禁止高并发 result 默认使用无界 wildcard、深分页、脚本排序、默认昂贵 fuzziness 或大聚合；所有 objectTypes/filter/limit 受 metadata allowlist 约束。
- 缓存分层必须明确：App 本地 suggest cache、search-service 热 query / relatedTerms cache、ES request/query cache、filesystem cache 各自有命中指标与失效边界。

## 迁移、灰度与回滚要求

- 本期不保留记录节点并行治理，也不做双轨兼容方案。
- 发布方式为整体验收后一把上线。
- 如出现搜索不可用、首批结果时延持续超标或崩溃率异常升高，回滚粒度为整体验收回退到旧搜索实现或整版发布回滚。
- 商用发布必须先通过 stackctl gamma/prod-sim 验证、故障/回滚演练、config release 版本绑定与全量 gate；`search-service` module、metadata、App remote/codegen、部署配置和 backlog 必须纳入版本控制，干净检出可复现。

## 验收重点

1. 全局搜索成为独立一级能力，而非内容或聊天的附属能力。
2. 搜索首页初始态、联想态、网络结果页、小趣搜结果与记录管理在同一 Journey 内完成收口。
3. “联系人直达会话”和“群组分类 facet tab” 的对象边界冻结，不再模糊挂靠旧节点。
4. 记录搜索节点从特性树统一清理，不再保留平行旧路径。
5. 两阶段搜索合同可测：suggest 本地对象即时可见，result 只渲染云侧最终结果，本地对象不进入正式结果页。
6. 性能、稳定、准确、可重复、热力推荐闭环和回滚证据齐全；R-S06-S-1/2/3 backlog 未闭合前不得宣称商用上线。
