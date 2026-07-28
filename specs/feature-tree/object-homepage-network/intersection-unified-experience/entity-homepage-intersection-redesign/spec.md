# L3 Story：实体主页交集重做 (`entity-homepage-intersection-redesign`)

> 所属能力：[`intersection-unified-experience`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览对象主页的用户，
我希望无禁用术语外露，
从而理解对象并继续探索其关系与内容。

## 2. 范围与非目标

### In Scope

- “实体主页交集重做”的输入、可观察主路径、失败语义以及与父能力的交接。
- 我的交集卡标题统一为「我的交集」，渲染共享 ObjectIntersectionPreviewCard（objectBType=homepage、objectSharedReasonsProvider 单一真相源）：单列预览句 + 蓝锚点 + 查看全部。
- 打动卡新增，标题「这里打动的人」，IntersectionStatementCard + entityImpactProvider，逐条只读 EntityImpactItem，句内数字下钻影响明细，无事实不展示。
- 资料/关于入口不进入首屏核心模块，头部只保留一句话简介。
- 核心动作主按钮关注、次按钮改「发记录」；移除首屏常驻「想去·结伴」入口。
- 一级 tab 记录/讨论/相关圈子；记录流双列瀑布 + 卡内唯一交集句（封面→交集句→标题→作者→赞）。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 实体主页交集重做

- “实体主页交集重做”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 用术语外露

- 无禁用术语外露。

<a id="req-003"></a>
### REQ-003 过滤与用户主页同一实现模式

- 二级过滤与用户主页同一实现模式。

<a id="req-004"></a>
### REQ-004 不挂 4 列统计行

- 头部不挂 4 列统计行。

<a id="req-005"></a>
### REQ-005 主页所有者治理入口

- owner/认领/上报动作仅从右上角更多菜单触达。

<a id="req-006"></a>
### REQ-006 数据来自 Remote entityImpactProvider，无可枚举影响事实时整卡不展示，无主观营销

- 打动数据来自四环境同一 Remote entityImpactProvider 与 canonical release projection，无可枚举影响事实时整卡不展示，无主观营销语。

<a id="req-007"></a>
### REQ-007 我的交集卡：标题统一为「我的交集」，与我的主页同壳，渲染 ObjectIntersectionPreviewCard（共享积木，objectBType=homepage、objectSharedReasonsProvider 单一真相源）：单列预览句（蓝色可点击锚点）+ 弱入口「查看全部」

- 我的交集卡：标题统一为「我的交集」，与我的主页同壳，渲染 `ObjectIntersectionPreviewCard`（共享积木，objectBType=homepage、`objectSharedReasonsProvider` 单一真相源）：单列预览句（蓝色可点击锚点）+ 弱入口「查看全部」。
- 可见结论只读 `IntersectionReason.primaryText/primarySpans`，禁止用 `EvidenceGroup` 或 `intersectionPoints` 本地拼主句。
- 无真实交集时克制空态不占位。
- 记录流：双列瀑布 + `PostPreviewCard`
- 卡内统一为 封面 → 交集句（蓝锚点）→ 标题 → 作者 → 赞。
- 卡内唯一交集句。
- 数据来自 Remote `HomepageContentPreview.intersectionReasons`，四环境不得由端侧 fixture 拼装。
- 公开信息：用户侧 fallback overview 只保留口碑、位置、分类、年份、下线说明等用户语义；`统一对象键/对象页模板/来源/认领状态/灰度 cohort/主页管理` 仅能在 owner/admin 操作入口表达，不得进入公开 tab。

## 4. 契约引用

- canonical：`recommendation/recommendation/recommendation_model_release/projections/intersection_reason.yaml`
- canonical：`entity/entity_homepage/homepage/fields.yaml`
- canonical：`entity/entity_homepage/homepage/ui_config.yaml`
- canonical：`entity/entity_homepage/homepage/projections/homepage_related_group_summary.yaml`
- canonical：`entity/entity_homepage/homepage/projections/entity_impact_item.yaml`
- canonical：`entity/entity_homepage/homepage/projections/entity_impact_summary.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 实体主页交集重做

- GIVEN 浏览对象主页的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“实体主页交集重做”对应的公开行为。
- THEN 通过父能力公开契约交付“实体主页交集重做”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`intersection-unified-experience`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 实体主页交集重做 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“实体主页交集重做”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
