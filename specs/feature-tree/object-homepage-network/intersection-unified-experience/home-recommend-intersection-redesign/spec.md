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

- spotlight 文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。

<a id="req-002"></a>
### REQ-002 spotlight 文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致

- spotlight 文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。

## 4. 契约引用

- canonical：`content/content/post/projections/discovery_feed.yaml`
- canonical：`recommendation/recommendation/recommendation_feature_profile_view/projections/intersection_reason.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 首页推荐交集重做

- GIVEN 浏览对象主页的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“首页推荐交集重做”对应的公开行为。
- THEN spotlight 文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`intersection-unified-experience`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 首页推荐交集重做 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“首页推荐交集重做”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
