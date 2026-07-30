# L3 Story：他人/我的主页交集重做 (`user-profile-intersection-redesign`)

> 所属能力：[`intersection-unified-experience`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览对象主页的用户，
我希望他人/我的主页二级过滤同一实现，
从而理解对象并继续探索其关系与内容。

## 2. 范围与非目标

### In Scope

- “他人/我的主页交集重做”的输入、可观察主路径、失败语义以及与父能力的交接。
- 公共头部：认证标识 + 摘要区挂载统计行（记录/粉丝/关注/获赞）。
- 一级 tab 内容改记录；二级过滤改最右侧过滤项/图标、去胶囊。
- 他人主页「我与TA的交集」/「TA打动的人」列表入口与去好友化。
- 我的主页「我的交集」/「我打动的人」列表入口与去好友化/去收藏；主标题固定为「我的交集」，时间窗口按用户节奏动态解释。
- 圈子主页、实体主页。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 他人/我的主页交集重做

- 他人/我的主页二级过滤同一实现。

<a id="req-002"></a>
### REQ-002 /我的主页二级过滤同一实现

- 他人/我的主页二级过滤同一实现。

<a id="req-003"></a>
### REQ-003 他人主页交集列表入口 GWT（S2a）

- 文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。

<a id="req-004"></a>
### REQ-004 我的主页交集与打动 GWT（S2b）

- 红点聚合进「查看更多」；主标题固定为「我的交集」，时间窗口不写死为“今日”。

<a id="req-005"></a>
### REQ-005 林墨「我的交集」旅行三元组 inbox 渲染 + lifecycle 单源显隐 GWT

- Widget 与契约测试必须直接证明 inbox 三元组渲染和 lifecycle 单源显隐过滤。
- 展示合同口径锚定父能力 [`REQ-007 Display Contract / §17`](../spec.md#display-contract)（历史文档曾称 WS-ACC §22.10，仓内无独立 WS-ACC 文件）。

<a id="req-006"></a>
### REQ-006 打动文案去好友化（认识了新朋友 → 建立了新连接），无收藏文案；他人/我的标题统一为 TA打动的人 / 我打动的人

- 打动文案去好友化（`认识了新朋友` → `建立了新连接`），无收藏文案；他人/我的标题统一为 `TA打动的人` / `我打动的人`。

## 4. 契约引用

- canonical：`user/profile/fields.yaml`
- canonical：`user/profile/ui_config.yaml`
- canonical：`content/content/post/projections/author_impact_item.yaml`
- canonical：`recommendation/recommendation/recommendation_model_release/projections/intersection_reason.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 他人/我的主页交集重做

- GIVEN 浏览对象主页的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“他人/我的主页交集重做”对应的公开行为。
- THEN 他人/我的主页二级过滤同一实现。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-003"></a>
### GWT-003 他人主页交集列表入口

- GIVEN 用户访问他人主页且存在可展示的交集。
- WHEN 用户打开交集或打动的人列表入口。
- THEN 文案与交集定义一致，且入口展示同一对象事实。

<a id="gwt-004"></a>
### GWT-004 我的主页交集与打动

- GIVEN 用户访问自己的主页。
- WHEN 用户查看交集、打动的人或更多入口。
- THEN 主标题为“我的交集”，红点聚合到“查看更多”，且时间窗口按用户节奏解释。

## 6. 依赖

- 前置要求：[`intersection-unified-experience`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 他人/我的主页交集重做 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“他人/我的主页交集重做”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
<a id="open-003"></a>
### OPEN-003 他人主页交集列表入口 GWT（S2a）

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 我的主页交集与打动 GWT（S2b）

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：红点聚合进「查看更多」；主标题固定为「我的交集」，时间窗口不写死为“今日”。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效。
