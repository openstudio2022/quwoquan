# 设计方案：geo-content-trinity（实体–标签–图文数据工程）

## 设计动因

上游规格已冻结三件事：

1. 需要独立于研发主线的**数据工程运行工作流**
2. 需要把**目录候选层 / 实体层 / 标签层 / 图文层**拆开建模
3. 需要以四川旅游出行为首个真实端到端样例完成闭环

因此本设计阶段的核心，不是再讨论“要不要建数据工作流”，而是回答：

1. `data-*` 阶段命令如何对外呈现，并映射到现有 `crawl` 子命令
2. 目录、实体、标签、图文、元数据之间的读写关系如何固定
3. 四川目录构建、实体生成与图文链路如何形成可测可验收的最小闭环

配套资产：

- `[workflow.md](workflow.md)` — 显式阶段工作流
- `[command-matrix.md](command-matrix.md)` — 外部 `data-*` 命令与内部 `crawl` 原语映射
- `config/geo_catalog_config.sichuan.yaml`
- `config/entity_naming_rules.yaml`
- `config/geo_band_rules.sichuan.yaml`
- `quwoquan_data/schema/geo_catalog_row.schema.json`
- `quwoquan_data/schema/entity_catalog_row.schema.json`
- `quwoquan_data/schema/tag_catalog_row.schema.json`
- `quwoquan_data/schema/authority_pool_row.schema.json`
- `quwoquan_data/schema/source_pool_row.schema.json`

## 方案概览

### 方案 A：仅保留文档，不新增 `data-*` 包装命令

直接在文档里规定 `crawl *` 的阶段归属，不新增任何显式命令。

**优点**：

- 代码改动少
- 不需要维护额外命令层

**缺点**：

- 用户仍需记忆大量底层 `crawl` 子命令
- “数据阶段”的可见性和准出边界依旧模糊

### 方案 B：新增 `data-*` 阶段包装命令（本期选型）

对外暴露 `python3 quwoquan_data/scripts/cli.py data ...`，内部调用现有 `crawl` handlers。

**优点**：

- 外部流程清晰，便于阶段治理
- 可保留已有 `crawl` 子命令实现与测试资产
- 便于未来在 `data-*` 层挂阶段门禁与报告

**缺点**：

- 需要维护一层映射
- 若 `crawl` 子命令变化，需同步更新 data 层

## 选定方案

采用**方案 B**：

- 研发工作流继续定义与演进数据工程能力
- 数据运行工作流通过 `data-*` 显式命名
- 内部以 `workflow_ops.py` / `batch.py` 等现有 handlers 作为执行原语

## 阶段设计

### 1. `data explore`

**职责**：

- 收敛本轮范围、地域、实体类型子集、合规边界、已知权威源

**输入**：

- 用户 query / regions / entity_types
- 可选既有 `runtime/specs/*.yaml`

**输出**：

- `data_exploration_brief.md`（当前最小实现可先输出 JSON 摘要）

**门禁**：

- `DATA_EXPLORE_READY` 或 `GATE_BLOCK`

### 2. `data baseline`

**职责**：

- 冻结数据专题 `spec.md / design.md / acceptance.yaml`
- 冻结 `geo_catalog_config.yaml`、`entity_naming_rules.yaml`、**`geo_band_rules*.yaml`**（与 catalog 内 `geo_band_rules_path` 对应）

**输入**：

- 文档路径 / 配置路径
- 可选 `--geo-band-rules`：与 `--catalog-config` 同传时，CLI **强制**校验其解析路径与 `catalog.geo_band_rules_path` 一致

**输出**：

- 基线文件存在性确认

**门禁**：

- lint / schema 校验通过

### 3. `data build-entities-tags`

**职责**：

- 生成地理目录候选层
- 生成 `tag_catalog`
- 生成 `entity_catalog`
- 对酒店住宿专题，生成并校验 `Entity/地点/住宿`、`Topic/旅行/住宿` 与 `Format/内容角度` 的专项标签闭环

**内部命令映射**：

- `build_geo_poi_catalog` / `build_sichuan_attractions_catalog.py`
- `merge_overpass_poi_catalog.py`
- `crawl tag-catalog-build`
- `crawl entity-catalog-build`

**输出**：

- `runtime/seed/*_catalog.ndjson`
- slice 报告
- `runtime/seed/tag_catalog/*.ndjson`
- `runtime/seed/entity_catalog/*.ndjson`

**门禁**：

- 国内 `label_zh` 覆盖率
- `entityId` 无重复
- `tagRefs` 可解析
- 目录行到实体行映射抽样通过
- 酒店住宿专题下，住宿实体必须至少引用一个 `Entity/地点/住宿/住宿业态/*` 叶子标签
- 酒店住宿专题下，实体若含 `设施服务`、`房型空间`、`档次等级` 等属性标签，不得替代 `住宿业态` 主标签

### 3-H. 酒店住宿专题标签设计

酒店住宿专题采用六轴正交模型，避免把业态、档次、功能、设施、房型与房源形态混放在同一兄弟层。

| 轴线 | 标签路径 | 语义 |
|---|---|---|
| 住宿业态 | `Entity/地点/住宿/住宿业态/*` | 酒店、民宿、青年旅舍、客栈、度假村等“是什么住宿设施” |
| 档次等级 | `Entity/地点/住宿/档次等级/*` | 豪华型/高端型/经济型/星级等等级口径 |
| 功能定位 | `Entity/地点/住宿/功能定位/*` | 商务、会议、度假、温泉、亲子、长住等用途 |
| 设施服务 | `Entity/地点/住宿/设施服务/*` | 早餐、停车、泳池、会议室、洗衣、充电桩等可筛选属性 |
| 房型空间 | `Entity/地点/住宿/房型空间/*` | 大床房、双床房、套房、家庭房、山景房、私汤房等 |
| 房源形态 | `Entity/地点/住宿/房源形态/*` | 整套房源、独立房间、合住房间、树屋、帐篷营地等 |

Topic 与 Format 配合方式：

- `Topic/旅行/住宿/*` 表达内容主题，例如 `出差住宿`、`商旅住宿`、`川西住宿`、`高原住宿`、`住宿避雷`、`住宿比价`。
- `Format/内容角度/*` 表达创作视角，例如 `酒店探店`、`住宿测评`、`住宿攻略`、`住宿避雷`。
- `Audience` 不因住宿新增并行维度；亲子、银发、消费能力、职业等由既有用户画像组合表达。

实体 materialize 规则：

1. 每个住宿实体至少一个 `住宿业态` 叶子；
2. 每个发布实体至少一个可信来源锚点；
3. 设施、房型、档次等标签只在有来源证据或内容证据时使用；
4. 四川住宿 posts 必须同时具备 entityRef、`Topic/旅行/住宿/*`、`Format/内容角度/*`；
5. 不满足锚点条件的酒店/民宿名称留在候选或待审桶，禁止直接发布。

### 4. `data download`

**职责**：

- 生成 crawl spec 与 instruction profile
- 生成 authority pool、source pool
- 完成内容发现 / hydrate

**内部命令映射**：

- `crawl instruction-build`
- `crawl entities-by-tag`
- `crawl spec-build`
- `crawl authority-sync`
- `crawl authority-review`
- `crawl pool-bootstrap`
- `crawl spec-discovery`
- `crawl fetch-source`
- `crawl content-discover`
- `crawl content-hydrate`

**输出**：

- `instruction_profile.json`
- `runtime/specs/*.yaml`
- `authority_pool.ndjson`
- `source_pool.ndjson`
- `pages/**/source.md`

**门禁**：

- `validate_crawl_spec`
- `article_topic_catalog_ref`（seed topic catalog）存在
- 进入 deep batch 前必须存在 `publishable_topic_catalog_ref` 或等价 publishable topic 产物
- hydrate 失败率低于阈值

### 5. `data process-content`

**职责**：

- 审核来源
- 图文加工
- 生成前复核

**内部命令映射**：

- `crawl content-review`
- `crawl compose-post`
- `crawl review-generated`

**输出**：

- 审核后 pool
- `compose_summary.json`
- `audit_summary.json`

**门禁**：

- content-review schema 正确
- 图文与实体锚点一致

### 6. `data publish`

**职责**：

- 发布 package
- 抽取 feedback
- 运行真实性与 package gate

**内部命令映射**：

- `crawl publish-approved`
- `crawl feedback-extract`
- `crawl feedback-verify`
- `quwoquan_data/scripts/verify/verify_quwoquan_data_source_authenticity.py`
- `quwoquan_data/scripts/verify/verify_quwoquan_data_post_packages.py`

**输出**：

- `publish/**`
- feedback ndjson
- verification report

**门禁**：

- authenticity / package 通过
- 若有回写，生成 diff 提案

## 实体准入：权威轨 vs 图文证据轨（R7）

本节冻结 **R7** 的操作语义，避免「百科说了算」与「贴文凑数」混在一套隐性规则里。

### 权威轨（authority_track）

**触发**：`baikeItem` 与/或 `wikiTitle`（及 acceptance 批准的白名单延伸锚点）**可解析且通过** `authority-sync` / 人工复核策略。  
**效果**：

- `entity_catalog` 中 `canonicalName` / `extensions.labelZh` **以权威页主标题 + 命名规则清洗**为准。
- **不要求** `≥2` 篇 post 才准入；post 仅用于丰富 `source_pool` 与话题覆盖。
- `authority_pool` 记录主锚 URL、抓取时间、许可/版权标注策略（见 `quwoquan_data/SPEC.md`）。

### 图文证据轨（post_evidence_track）

**触发**：权威主锚 **缺失** 或 **无法唯一绑定**（多义、消歧失败、仅有模糊昵称）。  
**硬准入条件**（同时满足）：

1. **≥2 篇「文章级」来源**，每篇均有可引用 `sourceUrl`、抓取/收录时间与平台标识。  
2. **独立性**：默认要求 **不同顶级域名**；若同域则须 **不同稿件 ID** 且内容非简单转载（可通过正文相似度/发布时间启发式；**最终可人工一票否决**）。  
3. **互证一致**：  
   - **主名**：至少一处使用相同或明确别名映射（如「甲」又名「乙」且两文各用一名但指向同一相对地标，须在 `aliases` 或证据表中说明）；**禁止**两名在省内指向不同区县且无法调和。  
   - **地理**：同属同一市州或县，或对「相对某国省道/某景区大门」的描述 **无相互矛盾**；若仅一篇写「甘孜某野海子」另一篇写「阿坝同音地名」，**视为冲突**，不准入实体表。  
   - **类型预期**：打卡地/观景台/秘境可在正文标签中体现；与 `entity_type_label_zh` 的映射允许多标签，但不得与「室内博物馆」类描述对同一 ID 同时声称矛盾物理类型（除非设计为复合 POI）。

**不足或冲突时**：行留在 **`catalog` 候选** 或 `evidence_pending` 桶，**禁止**进入可发布 `entity_catalog` / seed manifest，直至补足或人工决议。

### 目录候选 → 语义归并判定层

`catalog` 不是 publishable entity 的直写源。更严格地说，目录规则层也不是页面语义抽取器。目录候选在进入最终 publishable `entity_catalog` 前，必须先经过 **页面级 extraction / review / authority / escalate / compile / materialize** 主线；目录规则层仅允许做不会改变实体语义的噪声抑制与结构化准备。

### Agent / CLI 边界

| 层 | 职责 | 禁止 |
|---|---|---|
| CLI / 数据脚本 | 抓取页面、hydrate、准备 normalization input、校验 output schema、compile/materialize、topic 物化与 gate、生成编程助手任务清单 | 用名称启发式直接替代页面实体抽取与最终主子判定 |
| 编程助手 | 读取 `source.md` / 阶段 input JSON，提取 `mainEntityCandidates`、`memberCandidates`、`aliasCandidates`、图片语义判定，并把结构化结果写回 `results/<stage>/*.json` | 绕过 schema 直接写 publish package |
| 目录规则层 | 仅处理会污染编程助手输入的坏样本：纯符号、空白名、损坏页面、明显非内容对象 | 把 `孔雀`、`过厅`、`龙泉山观景台` 这类样本直接在脚本层定死为最终实体结论 |

### Seed topic vs publishable topic

- `article_topic_catalog_ref`：seed topic catalog，仅服务 `download/spec-discovery/content-hydrate`，允许包含“待编程助手判定”的候选 topic。
- `publishable_topic_catalog_ref`：publishable topic catalog，仅服务 `process-content/publish` 深链路，必须来自 normalization/materialize 后的顶层实体。
- 任何 `topic_{entityId}` 形式的 synthetic topic 都不得进入 `publishable_topic_catalog_ref`。

`catalog` 进入最终实体层前，必须先经过一层可审计的语义判定：

| 判定 | 含义 | publishable 行为 |
|------|------|------------------|
| `standalone` | 候选本身就是独立主实体 | 进入顶层 `entity_catalog` |
| `member` | 候选明确属于某个主实体 | 不再生成顶层实体；写入根实体 `extensions.members` |
| `alias` | 候选仅为主实体别名/曾用称呼/规范化异形 | 不再生成顶层实体；写入根实体 `aliases` |
| `parallel_entity` | 与根主题相近但不构成从属，需保留独立主体 | 允许独立进入顶层 `entity_catalog`，同时保留语义决策记录 |
| `reject` | 名称、类型或来源不成立 | 从 publishable 实体层剔除 |
| `pending_review` | 存在成员/并列信号，但证据不足或缺根实体 | 仅保留在候选/待审制品，不得静默升格 |

该层的最终真相源应来自 normalization materialize 产物；`semantic_cluster_candidates.ndjson` 与 `semantic_cluster_pending.ndjson` 仅作为候选与追溯制品，不得再直接充当省级全量 publishable topics 的真相源。

### 聚类线索与最小信号集

候选层至少保留以下可复用线索，避免后续反复重打 Overpass 或退化为“按名字猜”：

- `source_type` / `source_id`：正式来源键，不再只依赖临时 `_source`
- `center_lat` / `center_lon`：几何中心提示
- `ordinal`：编号成员序号，如 `2号`
- `parent_name_hint`：候选上游给出的潜在父实体提示
- `cluster_hints`：轻量语义信号，如 `numbered_member`、`paren_viewpoint_member`
- `admission_track_hint` / `evidence_article_urls`（候选阶段可选）：指示更可能走权威轨还是图文证据轨

### 首批自动判定规则（保守策略）

- 编号成员：`1号/2号`、`一号/二号`、`No.1/No.2`
- 典型成员后缀：`观景台`、`关楼`、`别墅`、`公馆`、`旧址`
- 主体后缀：`景区`、`古镇`、`庄园`、`旧址群`、`基地`
- 品牌化观景体系：同区划 + 同主题 headword 的 `之凤/之恋/之龙` 等命名
- 显式别名/并列 hint：若候选层提供 `alias_of_*` / `parallel_*` 之类提示，可直接落到 `alias` / `parallel_entity`

### 固定回归族群（四川语义样本）

以下样本族群是语义归并的固定 fixture，不得回退为“目录行即实体行”：

1. `刘氏庄园 / 刘文彩公馆 / 刘文成公馆 / 刘文昭公馆 / 刘文渊公馆`
   期望：`刘氏庄园` 为主实体，其余为 `member`
2. `成都大熊猫繁育研究基地 / 大熊猫1-7号别墅`
   期望：基地为主实体，别墅为编号 `member`
3. `剑门关风景区 / 剑门关关楼`
   期望：至少给出显式 `member` 或 `parallel_entity` 判定，禁止无说明平铺
4. `同济大学工学院旧址 / 同济大学理学院(旧址) / 国立同济大学医学院旧址`
   期望：缺根实体或证据不足时进入 `pending_review`，不得静默升格
5. `贡嘎之凤(一号冰川观景台) / 贡嘎之恋(二号冰川观景台) / 贡嘎之龙(大冰瀑布观景台)`
   期望：进入同一观景体系簇；缺根实体时至少 `pending_review`

### 误归并防线

- 语义归并不是文本相似度去重；名字像、不代表主体相同。
- 自动规则只能覆盖高确定性模式；一旦缺主实体、缺权威页、缺双文章互证或存在地理冲突，默认 `pending_review`。
- `pending_review` 是产品化真相，不是临时垃圾桶；后续人工补证或 normalization 回放必须可追溯。

### 推荐扩展字段（`entity_catalog.extensions`，JSON Schema 允许 `additionalProperties`）

| 字段 | 说明 |
|------|------|
| `admissionTrack` | `authority` \| `authority_plus_post` \| `post_evidence` |
| `authorityBaikeUrl` / `authorityWikiUrl` | 与 `baikeItem` / `wikiTitle` 同源，便于审计 |
| `evidenceArticleUrls` | 图文证据轨至少 2 条 URL，有序 |
| `evidenceIndependenceNotes` | 简述为何算独立来源（脚本或审核备注） |
| `conflictCheckStatus` | `pass` \| `pending` \| `fail` |
| `undevelopedOrWildAccess` | bool，供 UI/文案做安全提示，不代替产品侧免责声明 |
| `members` | 语义归并后挂载到主实体的成员列表 |

**MVP 诚实说明**：`conflictCheckStatus` 可先以 **人工抽检 + 结构化表单** 为主；启发式仅作辅助，不得静默覆盖 fail。

### 景点全集子类（与 spec R7 对齐）

本设计将「全集」拆解为可追溯子类（**不要求**任一子类独占 OSM 标签；可多轨召回 + 语义类型）：

- **旅游景区**：已定级或未入名录但具旅游接待属性的区域点位；名录与 OSM **均为召回源之一**，缺一不否认实体存在，仅以准入轨决定能否进 publishable。
- **史迹 / 遗址**：`historic=` 允许的 monument / archaeological_site / ruins / building / castle / fort 等与公众游览相关的historic 对象。
- **网红打卡地 / 秘境小众**：名称启发式（见 `entity_naming_rules.check_in_hotspot` / `hidden_gem`）、UGC **post 聚类** 与 **百科缺失**高度相关；默认 **post_evidence_track**，补锚后可升 **authority_track**。
- **观景台**：与 OSM `tourism=viewpoint` 及 `geo_catalog_config` 过滤对齐。

共通规则：**打卡地 / 网红点 / 小众秘境** 百科缺失概率高；**未开发 / 野生可达** 须在候选或实体扩展中打标（`undevelopedOrWildAccess`），并遵守合规展示边界。

## 图文规模与精品子集

- **目标**：每实体 **20～100** 篇可 hydrate 的攻略/游记/日记/摄影向图文（合规前提下上限尽量用尽）。  
- **精品约 30%**：在 `process-content` 后打 `contentTier: curated` 或等价字段；**首选**同一 rubric 下的**规则分 top 约 30%**（可加：长度、图片数、可追溯来源层级、去重后信息增益等）。编程助手或 Cursor Agent 会话可对逐篇产出 `contentScore` 与短理由并落盘，但须 **版本化**（模型/prompt/script id），以便复跑对齐。  
- **人工抽检**：可选；建议默认随机抽检全量条目约 **1%**，并对**规则分末段**加权抽检以覆盖「看似通过但语义弱」的边界稿；不写死为 Gate0。

## 数据制品与读写关系

### 目录候选层

`catalog.ndjson` 是**实体候选目录层**，不是实体类型。建议字段：

- `topic_id`
- `raw_name`
- `normalized_name`
- `name`
- `label_zh`
- `label_en`
- `display_locale`
- `entity_type`
- `entity_type_label_zh`
- `province` / `prefecture` / `district`
- `source_type` / `source_id`
- `center_lat` / `center_lon`
- `ordinal`
- `parent_name_hint`
- `cluster_hints`
- `wiki_title`
- `baike_item`
- `tagRefs`
- `authority_status`
- `reject_reason`
- `admission_track_hint`（可选：`authority` / `post_evidence` / `mixed`）
- `evidence_article_urls`（候选阶段可选，升级实体时应与 entity 对齐）
- `undeveloped_or_wild_access`（候选阶段可选，用于下游安全提示）

### 实体层

`entity_catalog` 由 tree + catalog 合并：

- `entityId`
- `canonicalName`
- `entityType`
- `extensions.labelZh`
- `extensions.labelEn`
- `extensions.entityTypeLabelZh`
- `extensions.wikiTitle`
- `extensions.baikeItem`
- `tagRefs`

### 标签层

`tag_catalog` 来自 `runtime/trees/tags`：

- `tagId`
- `label`
- `tagType`
- `extensions.labelEn`

### 图文层

图文层以 `source_pool` / `publish` 为主：

- 标题、snippet、正文锚点必须回链实体 canonical 或 `label_zh`
- `content-review` 不得擅自生成第二套展示名

## 四川首个真实样例的最小闭环

首个样例使用四川旅游出行场景：

1. 生成四川地理目录候选层并过滤英文/符号/明显非景点候选
2. 生成实体与标签
3. 基于四川 spec 做下载 / hydrate
4. 完成图文加工
5. 发布并跑 authenticity / package gate

该闭环允许：

- 全量目录候选层 + 抽样深验证
- 或目录候选层全量、单 topic 受控深验证

只要验收中明确说明样本范围即可

## 县级下钻（Phase2）

本期不默认在全仓库 CI 中跑满县级 Overpass，但已提供可检入配置与枚举工具：

- 配置：`config/geo_catalog_config.sichuan.county.yaml`（`slice_admin_level: "6"` + 自 Overpass 导出的 `slices`）
- 枚举：`quwoquan_data/tools/geo/list_admin_slices_overpass.py`（刷新 `slices` 列表时 diff 后检入）
- 一键编排：`quwoquan_data/scripts/e2e/run_province_full_batch.sh`（泛化省级，默认四川）

设计上仍可：

- `scope.slice_admin_level` 切换到县级
- 离线链路可继续使用 `merge_overpass_poi_catalog.py`

县级下钻启用前必须同时冻结：

1. **请求预算**：单轮 Overpass 切片上限
2. **缓存策略**：切片响应是否落本地 cache
3. **离线合并**：多 JSON 经 merge 脚本再进入 catalog
4. **覆盖 KPI**：县级覆盖率与允许空切片比例

## 大规模 topic（spec 对齐）

当 catalog 规模进入大 topic 模式时：

- `spec-build` 在 `spec.extensions` 写入：
  - `topicCount`
  - `skipHydrateRecommended`
  - `largeTopicMode`
  - `suggestedBatchSize`
- 推荐策略：
  - `topicCount > 50`：默认建议 `--skip-hydrate`
  - `topicCount > 100`：按 topic 子集分批 download / process / publish
  - acceptance 中对 discovery / hydrate / publish KPI 分层

这样可以避免 `validate_crawl_spec` 通过，但实跑时 topic 规模与执行预算完全脱节。

## 风险与回滚

- `data-`* 只是包装层；如 wrapper 失效，可退回底层 `crawl *` 子命令执行
- 四川目录过滤策略如误杀，可通过输入 JSON / slice 报告回放诊断
- `wiki_expand` 行为必须有固定回归 topic，避免未来收紧/放松后无感漂移