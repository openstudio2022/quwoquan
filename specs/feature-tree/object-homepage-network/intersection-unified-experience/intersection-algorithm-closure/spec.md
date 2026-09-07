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
- recommend_feature socialFeatures.intersection。
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

## 4. 契约引用

- canonical：`recommendation/recommendation/recommendation_model_release/projections/recommend_feature.yaml`
- canonical：`recommendation/recommendation/recommendation_feature_profile_view/projections/intersection_reason.yaml`
- canonical：`recommendation/recommendation/recommendation_model_release/intersection_kind_registry.yaml`
- canonical：`recommendation/recommendation/recommendation_model_release/impact_help_type_registry.yaml`

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
