# L3 Story：交集算法闭环（Feature / Ranking / Explain / Event） (`intersection-algorithm-closure`)

> 所属能力：[`intersection-unified-experience`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览对象主页的用户，
我希望看到由真实关系与行为事实生成、可解释且可行动的交集原因，
从而理解自己与对象的联系并选择可信下一步。

## 2. 范围与非目标

### In Scope

- “交集算法闭环（Feature / Ranking / Explain / Event）”的输入、可观察主路径、失败语义以及与父能力的交接。
- behaviors intersectionSourceRef + intersection_expand。
- Recommendation FeatureProfile 唯一在线画像中的交集事实与当前贡献；不恢复旧 recommend_feature 在线写轨。
- feature_registry intersection 特征。
- ranking-signal-fusion 交集信号对齐。
- Explain primaryText 产出归属。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 交集算法闭环（Feature / Ranking / Explain / Event）

- Feature 只消费 canonical 关系/行为事实，Ranking 只消费登记的 intersection signal，Explain 只产出可追踪的 `primaryText`，Event 只回写所属行为事实。四段不得互相补写状态或复制规则。

<a id="req-002"></a>
### REQ-002 交集事实与亲和度权重入口

- ranking-signal-fusion spec 登记 intersection fact/affinity 权重入口。
- 无独立 intersection-only ranker 文档或 service.yaml。

<a id="req-003"></a>
### REQ-003 primaryText 由 Explain 管线产出，禁止 displayText/label hydrate 回退

- primaryText 由 Explain 管线产出，禁止 displayText/label hydrate 回退。
- 至少三个 §5.4 标准 kind 必须生成可读的主谓宾交集句，并保留可追踪事实来源。

<a id="req-004"></a>
### REQ-004 垂类扩展契约实例化（零新 kind），以 travel_photography 为第一个实例

- 新增垂类只允许注册 `vertical` 值 + `objectKind`（必须映射到已有 homepage 类型或已有对象且 `routeId` 真实存在）+ 一棵 taxonomy 子树 + 一个事实生产者；禁止新增 kind、dimension、actionKey，禁止端侧出现任何垂类分支。契约与四条禁令登记在 `intersection_kind_registry.yaml` 的 `verticalExtensionContract`，由 `verify_intersection_kind_registry.py` 阻断。
- `travel_photography` 按该契约实例化且**零新 kind**：同地到访复用 `coVisitedEntity` / `followeeVisited`（生产者 = `post.visitedAt` + `geoTagRef`）。器材与参数只作作者可控披露、推荐解释和内容理解事实，光线进入画面氛围语义轴；后三者均不得自动生成交集句。
- 不可导航事实不得升格为交集：`objectKind=tag` 只有 `count` 角色且 `routeId` 为空，焦段 / 光线窗口 / 曝光参数做成交集句会产出不可导航主对象。
- `objectType`（开放词汇，每个垂类主页一个值）到 `objectKind`（闭集）的翻译只有一个真相源：`intersection_kind_registry.yaml` 的 `objectTypeBindings`；维度与兜底称谓由 `objectKinds[].dimension` / `.label` 声明。三者经 codegen 落成服务端 `generated.Intersection*` 查表与端侧 `intersectionObjectKindForObjectType`，服务端与端侧一律不得再写 `objectType` switch，也不得从 `objectId` 子串或 fixture 前缀反推类型。新增垂类只改注册表并重跑 codegen，不发 Go/Dart 版本。
- 未登记 `objectType` 查表落空串并降级为不可导航，禁止缺省当成人物；`HomepageType` 全集必须有 binding，由 `verify_homepage_type_contract.py` 阻断，结构与查表一致性由 `verify_intersection_kind_registry.py` 阻断。
- 同一批端侧断言在换垂类后无需改端侧代码：`IntersectionTargetNavigator` 只按生成的当前 `actionKeyMeta.dispatch` 闭集分发。
- Dart 验收必须直接覆盖 6 种 `objectKind`、7 种 lifecycle、落点、实名代表人与 span 单通道不变量。
- Go 测试必须直接覆盖 vertical、lifecycle 与 travel-impact 真算；端云门禁必须证明不存在桥接 registry。

<a id="req-005"></a>
### REQ-005 IntersectionService Explain 管线产出 primaryText（禁止 hydrate 回退 displayText）

- `IntersectionService` Explain 管线产出 primaryText（禁止 hydrate 回退 displayText）

<a id="req-006"></a>
### REQ-006 事实交集只消费当前有效贡献且保留独立来源

- 人物关系与共同点赞只从 User/Content 已确认 durable fact 派生到唯一在线 FeatureProfile；UI 点击、行为历史中的曾经点赞和 device 行为不能冒充当前 Persona 共同点赞。
- 取关、取赞或显式关系变化应撤销对应成员的当前贡献，包括原衰减贡献的剩余部分；不能固定减值、把取赞当 dislike，或为了撤当前态而改写合法历史训练事实。
- 同一业务事实的直接消费与行为转换不得重复贡献；重复/旧事件不能复活已撤成员。来源 owner、聚合身份、版本与重建代际分别保留，交集本地版本不是 User、Content、资料或统计的通用版本，不能跨来源比大小。
- no-op 的业务版本跳号合法，完整后态按本来源版本收敛；实际事件运输水位与聚合版本分离，不等待不存在的事件。当前证据与 Explain 必须可核验同一贡献来源。
- 展示前按当前隐私、block、对象生命周期与可导航资格过滤；已不可披露的成员不能因缓存、迟到投影或旧窗口出现在事实句中。证据不足或依赖不可用时明确受限/不可用，不以概率补成事实，也不造成功空集。

<a id="req-007"></a>
### REQ-007 大度数交集以有界成本返回真实口径

- 共同关注可按声明预算读取千级/万级出边集合或分批成员查询；共同粉丝、共同点赞及关注者行为不得全量装入千万级入边或同步向全部受影响用户 fanout。
- 单请求和单次物化均有条数、实际扫描、批次数、内存和总截止预算；返回条数限制不等于扫描有界。后台重算按来源水位与可恢复批次推进，不在每次交互扫描全图。
- 精确总数、top-K 与抽样结果严格按合同分型；有界裁剪的候选不冒充完整人数，超预算须可观察且可恢复。代表人与理由只来自当前有效、可披露的已验证证据。
- 1000/10000 出边与千万单目标入边的成本证据归 [performance-load-harness](../../../runtime/runtime-testinfra/performance-load-harness/spec.md#req-004)，具体业务读取预算由本域 owning operation/config 声明，不能以小数据测试或新增分片名称证明容量。

## 4. 契约引用

- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_feature_profile_view/object.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_feature_profile_view/fields.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_feature_profile_view/projections/intersection_reason.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/intersection_kind_registry.yaml`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/impact_help_type_registry.yaml`
- 来源只引用 `quwoquan_service/services/user-service/contracts/relationship/persona_relationship/events.yaml` 与 `quwoquan_service/services/content-service/contracts/content/content_reaction/events.yaml`；独立行为历史仍由 `quwoquan_service/services/content-service/contracts/content/content_behavior_fact/` 拥有。
- 贡献来源、独立版本、去重与预算结果的 wire 归上述 owner contract；未完成不得从历史 recommend_feature 声明回退或在本 Story 复制字段、事件 payload 与错误码。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 交集算法闭环（Feature / Ranking / Explain / Event）

- GIVEN 浏览对象主页的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“交集算法闭环（Feature / Ranking / Explain / Event）”对应的公开行为。
- THEN ranking-signal-fusion spec 登记 intersection fact/affinity 权重入口。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 宿主锚点语法与 objectType 翻译同一真相源

- GIVEN 交集 reason 携带 `subjectContext` 宿主锚点，且注册表已登记该锚点语法与 `objectTypeBindings`。
- WHEN 生产侧物化 reason、消费侧判定 reason 是否属于当前宿主对象。
- THEN 两侧都只查 codegen 产出的同一份锚点表，服务端与端侧都不存在第二份 `objectType`/锚点 switch。
- AND 未登记的锚点前缀 fail-closed 为「不属于当前宿主」，不按取值形态（如是否含冒号）反推类型。

<a id="gwt-003"></a>
### GWT-003 结果坍缩具备可计算阈值与回滚触发

- GIVEN 离线与在线评估已产出结果坍缩度量（作者重复率、话题熵、覆盖度等）。
- WHEN 某次候选或策略变更使坍缩度量越过登记阈值。
- THEN 评估门禁按可计算判据判为失败，并给出对应的回滚触发条件。
- AND 交集读面在同一 kind 内有 per-kind 上限与坍缩探测，统一排序口径不退化为组键字典序。

<a id="gwt-004"></a>
### GWT-004 当前共同贡献撤销且历史、版本与权限不混用

- GIVEN 两个有效 Persona 有同一对象的已确认贡献，另有 device 与合法行为历史，同一事实可重复或乱序到达。
- WHEN 一方取赞、取关或失去可披露资格，并重放旧事实及带合法跳号的新完整后态。
- THEN 对应当前共同贡献与事实句消失或受限，旧事件不复活，不新增 dislike；合法历史按合同保留，device 不替代 Persona。
- AND 来源分别可核验，资料或统计版本不覆盖关系/Reaction，no-op 不让消费者等待不存在事件，Explain 与评分引用同源有效证据。
- AND 当前贡献撤销、历史保留、自动收敛与用户可见受限结果必须分别可观察，前台不展示不能单独证明后台贡献已清理。

<a id="gwt-005"></a>
### GWT-005 大度数交集不以全图扫描或无界 fanout 换取成功

- GIVEN 受控容量数据覆盖 1000/10000 出边及千万级单目标入边，包含高 churn、无匹配与多热点主体。
- WHEN 查询共同关注、共同粉丝或共同点赞，并执行贡献变化与恢复重算。
- THEN 单次查询/物化的实际扫描、内存、批次和 deadline 均在声明预算内，或返回明确预算失败且可恢复；没有全入边装载、同步全用户 fanout 或无限补页。
- AND 精确人数与 top-K/抽样不混淆，返回理由来自当前可披露证据；隔离 storage benchmark 与环境公开 command/event 证据分开，后者不足时不得准出。
- AND 预算退出、可恢复续跑、实际读取与物化成本均可观察；少量用户界面展示不能代替目标基数下的容量结果。

## 6. 依赖

- 前置要求：[`intersection-unified-experience`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-002"></a>
### OPEN-002 travel_photography 地点与画面供给尚未形成真实闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺的实现与验收证据：生产 App 的地点/时间采集接线、canonical 旅行内容供给与真实非生产主体公开行为。`coVisitedEntity` / `followeeVisited` 已 active，但 `coldStartSupply` 要求 `post_declared_visit` 至少覆盖 5 个不同可导航对象。当前 canonical 三篇内容的 `visitedAt`、`geoTagRef` 与 `locationName` 全为空，真实供给仍为 0。作品画面相似性应进入推荐与内容理解，不为它新增不可导航交集 kind。器材与参数也不得因已有 EXIF 解析能力被提升为可见交集。
- 完成判定：`REQ-004` 的 travel_photography 零新 kind 实例化在真实供给上成立，且父级 L2 的到访同一性验收（`coPresentHere` / `nearbyAffinity`）有真实语料可裁定——至少 5 个不同可导航地点或 photo spot 经 canonical release 和真实非生产主体公开行为形成非零 `post_declared_visit` 供给，画面语义能进入推荐解释，器材/参数不出现在搜索筛选、Creator chip 或可见交集句中。

<a id="open-005"></a>
### OPEN-005 结果坍缩指标已计算但无可计算阈值与回滚判据

- 类型：`risk`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：`diversity_metrics.py` 已计算 `item_coverage` / `author_repeat_rate` / `topic_entropy` / `author_hhi` / `geo_coverage`，但 `evaluate_gate.py` 的 failures 判据只看 AUC/NDCG，在线护栏只看 CTR/engagement：坍缩有度量、无阈值、无回滚触发条件，回滚旋钮 `author_diversity_weight` 没有任何判据会拉动它。交集读面同一形态：单一 kind 可按 subject 快照全量展开，`strength`/`freshAt` 同值使 `REQ-006` 的排序键退化为组键字典序。触发时机是首次真实排序模型发布前；在此之前它是发布护栏缺口，不是当前交集读面的阻断。
- 完成判定：`GWT-003` 对应行为满足——坍缩度量在评估门禁中具备与 AUC 绝对下限同轨的可计算阈值与回滚触发条件，交集读面具备 per-kind 上限与坍缩探测，且有真实测试 `spec_ref` 覆盖。

<a id="open-003"></a>
### OPEN-003 route 与 photo_spot 已有 binding 但无派生来源

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：尚缺的实现与验收证据：`route` 与 `photo_spot` 的对象派生来源。二者虽已在 `intersection_kind_registry.yaml` 声明 binding，但路线应由同一用户 `declaredVisit` 的时序串联生成，大众拍照点应由同一实体下高频共现的画面标签与高互动作品聚合产生；两条派生都依赖 `OPEN-002` 的 `post_declared_visit` 供给先非零，在供给为 0 时建对象只会得到空集合。
- 完成判定：`GWT-001` 对应行为在 `route` 与 `photo_spot` 两类对象上成立——`post_declared_visit` 供给非零后，两类对象具备可复跑的派生任务与非空产出，且仍满足 `REQ-004` 的注册表与可导航性约束（拍照点不引入人工维护的机位库，也不产出器材与参数建议）。

<a id="open-006"></a>
### OPEN-006 当前贡献撤销与大度数有界交集尚缺合同和真实证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：[REQ-006](./spec.md#req-006)、[REQ-007](./spec.md#req-007) 所需原事实去重、独立来源版本、当前贡献撤销和有界查询尚无同候选全链运行证据；现有解释模板与历史行为投影不证明取赞后共同贡献消失或千万入边成本成立。
- 完成判定：[GWT-004](./spec.md#gwt-004)、[GWT-005](./spec.md#gwt-005) 的真实测试直接绑定完整 `spec_ref`，分别提供贡献/历史/权限 oracle、自动消费链与实际成本证据；来源 wire、预算终态及恢复先由 owning contract 冻结。证据缺席、skip 或只有小数据/替身时保持阻断，storage benchmark 不替代环境与真机证据。
- 依赖：[runtime-recommendation OPEN-002](../../../runtime/runtime-recommendation/spec.md#open-002) 的单轨事实消费；原 travel 供给及坍缩事项保持各自归属，不用本增量抵消。
