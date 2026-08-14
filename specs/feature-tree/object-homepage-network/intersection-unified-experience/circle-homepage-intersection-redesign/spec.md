# L3 Story：圈子主页交集重做 (`circle-homepage-intersection-redesign`)

> 所属能力：[`intersection-unified-experience`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览对象主页的用户，
我希望标题统一为「圈子打动的人」，文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致，
从而理解对象并继续探索其关系与内容。

## 2. 范围与非目标

### In Scope

- “圈子主页交集重做”的输入、可观察主路径、失败语义以及与父能力的交接。
- 我的交集卡标题统一为「我的交集」，渲染共享 ObjectIntersectionPreviewCard（objectBType=circle、objectSharedReasonsProvider）：单列预览句 + 蓝锚点 + 查看全部。
- 打动卡标题统一为「圈子打动的人」，AuthorImpactCard 同构、去好友化/去收藏，circleImpactProvider 单一真相源。
- 移除头部成员头像簇（你认识的人收敛进我的交集模块）；次按钮由私信改「进入讨论」（切讨论 tab）。
- 一级 tab 内容改记录；记录流去胶囊改右侧过滤、双列瀑布、卡内交集句。
- 头部 N 成员单计数；圈子独立头像字段由 Remote contract 与已物化 public avatar slice 提供，四环境不得端侧 mock。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 圈子主页交集重做

- 标题统一为「圈子打动的人」，文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。

<a id="req-002"></a>
### REQ-002 统一为「圈子打动的人」，文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致

- 标题统一为「圈子打动的人」，文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。

<a id="req-003"></a>
### REQ-003 过滤与用户主页同一实现模式

- 二级过滤与用户主页同一实现模式。

<a id="req-004"></a>
### REQ-004 不挂 4 列统计行、不挂成员头像簇

- 头部不挂 4 列统计行、不挂成员头像簇。

<a id="req-005"></a>
### REQ-005 圈子主页复用统一交集卡与可下钻事实

- 我的交集卡：标题统一为「我的交集」，与我的主页同壳，渲染共享 `ObjectIntersectionPreviewCard`（objectBType=circle、`objectSharedReasonsProvider` 单一真相源）：单列预览句（蓝色可点击锚点）+ 弱入口「查看全部」；可见结论只读 `IntersectionReason.primaryText/primarySpans`，禁止用 `EvidenceGroup` 或 `intersectionPoints` 本地拼主句。
- 打动卡：标题统一为「圈子打动的人」，`AuthorImpactCard` 同构（`IntersectionStatementCard` + `circleImpactProvider`），去好友化/去收藏。
- 句内数字可下钻来源明细。
- 无可枚举影响事实不展示。
- 清理：删除 `section_interaction`/`circle_stats_row` 死代码与硬编码中文字面量（统一语义 token）。

## 4. 契约引用

- canonical：`recommendation/recommendation/recommendation_feature_profile_view/projections/intersection_reason.yaml`
- canonical：`content/content/post/projections/author_impact_item.yaml`
- canonical：`circle/circle_management/circle/ui_config.yaml`
- canonical：`circle/circle_management/circle/fields.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 圈子主页交集重做

- GIVEN 浏览对象主页的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“圈子主页交集重做”对应的公开行为。
- THEN 标题统一为「圈子打动的人」，文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`intersection-unified-experience`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

（当前无开放事项：GWT-001 已由圈子壳层 widget 测试子句级绑定。）
