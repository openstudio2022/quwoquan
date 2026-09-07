# L3 Story：首页推荐交集重做 (`home-recommend-intersection-redesign`)

> 所属能力：[`intersection-unified-experience`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览对象主页的用户，
我希望spotlight 文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致，
从而理解对象并继续探索其关系与内容。

## 2. 范围与非目标

### In Scope

- “首页推荐交集重做”的输入、可观察主路径、失败语义以及与父能力的交接。
- feed 卡片（双列/单列）卡内唯一交集句。
- spotlight 模块单句主谓宾（替换主/副双句堆叠）。
- 交集句点击进对象页高亮归因保留。
- 频道集合调整。
- 云侧推荐排序 / 保鲜冷却。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 首页推荐交集重做

- feed 卡片（双列/单列）每个 Post 至多附着一条 display-ready 交集主句；主句只读云侧 `primaryText/primarySpans/displayBinding`，卡面不显示行动按钮、行动徽标或 `secondaryText`。
- 点击主句打开证据半屏：证据行只消费云侧下发的 typed 字段闭集，端不按本地优先级合并 `intersectionPoints`/`connectionSummary` 等异构字段拼装证据；半屏只显示共享 resolver 选出的一个可兑现 typed 下一步。
- 交集主句与回顾溯源标互斥占位；二者都没有时不占位。

<a id="req-002"></a>
### REQ-002 spotlight 文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致

- spotlight 文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。

## 4. 契约引用

- canonical：`content/content/post/projections/discovery_feed.yaml`
- canonical：`recommendation/recommendation/recommendation_feature_profile_view/projections/intersection_reason.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 首页推荐交集重做

- GIVEN 已登录用户打开首页 feed，且 Recommendation 为其物化了与当前 Post 锚点相关的交集 reason。
- WHEN feed 与 GetPost 投影该 Post。
- THEN 该 Post 至多附着一条通过展示合同的交集主句，feed 与详情页投影同源；不满足展示合同的候选不占用槽位。
- AND 点击主句打开的证据半屏只渲染云侧 typed 证据字段，行动只显示一个可兑现 typed 下一步。
- AND spotlight 文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`intersection-unified-experience`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

（当前无开放事项：证据行闭集 `evidenceRows`（`IntersectionEvidenceRow`）由 Content 水合出口按契约顺序实例化，端只按序渲染；spotlight 口径与证据半屏均已由 `GWT-001` 子句级测试绑定。）
