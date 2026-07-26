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

- ranking-signal-fusion spec 登记 intersection fact/affinity 权重入口。

<a id="req-002"></a>
### REQ-002 交集事实与亲和度权重入口

- ranking-signal-fusion spec 登记 intersection fact/affinity 权重入口。
- 无独立 intersection-only ranker 文档或 service.yaml。

<a id="req-003"></a>
### REQ-003 imaryText 由 Explain 管线产出，禁止 displayText/label hydrate 回退

- primaryText 由 Explain 管线产出，禁止 displayText/label hydrate 回退。
- 至少三个 §5.4 标准 kind 必须生成可读的主谓宾交集句，并保留可追踪事实来源。

<a id="req-004"></a>
### REQ-004 旅行 travel_photography 垂类三元组实例化 + 去桥接 codegen + hydration/打动真算 GWT（林墨 WS-ACC，§22.10/§23.4）

- Dart 验收必须直接覆盖 6 种 `objectKind`、7 种 lifecycle、落点、实名代表人与 span 单通道不变量。
- Go 测试必须直接覆盖 vertical、lifecycle 与 travel-impact 真算；端云门禁必须证明不存在桥接 registry。

<a id="req-005"></a>
### REQ-005 IntersectionService Explain 管线产出 primaryText（禁止 hydrate 回退 displayText）

- `IntersectionService` Explain 管线产出 primaryText（禁止 hydrate 回退 displayText）

## 4. 契约引用

- canonical：`recommendation/recommendation/recommendation_model_release/projections/recommend_feature.yaml`
- canonical：`recommendation/recommendation/recommendation_model_release/projections/intersection_reason.yaml`
- canonical：`recommendation/recommendation/recommendation_model_release/intersection_kind_registry.yaml`
- canonical：`recommendation/recommendation/recommendation_model_release/impact_help_type_registry.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 交集算法闭环（Feature / Ranking / Explain / Event）

- GIVEN 浏览对象主页的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“交集算法闭环（Feature / Ranking / Explain / Event）”对应的公开行为。
- THEN ranking-signal-fusion spec 登记 intersection fact/affinity 权重入口。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`intersection-unified-experience`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 交集算法闭环（Feature / Ranking / Explain / Event） 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“交集算法闭环（Feature / Ranking / Explain / Event）”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
