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
- 对象交集列表只经 production Remote 读取 canonical `recommendation_feature_profile_view` 投影；页面只负责 typed 展示、导航与行为归因，不拥有或端侧拼装交集事实。
- 空结果与 Remote failure 必须可区分，失败提供可重试终态且不得回退到本地 reason、旧句子或无归因跳转。

<a id="req-004"></a>
### REQ-004 我的主页交集与打动 GWT（S2b）

- 红点聚合进「查看更多」；主标题固定为「我的交集」，时间窗口不写死为“今日”。
- “我的交集”列表按 production Remote 返回的事实、维度与时间桶展示，并在成功读取后经 `content.intersection_visit_state` 的公开写面推进访问水位。
- 访问水位或反馈写入失败不得隐藏已读到的交集事实或伪造红点已清零；页面保留可恢复状态并允许后续幂等重放。

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
- canonical：`recommendation/recommendation/recommendation_feature_profile_view/projections/intersection_reason.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 他人/我的主页交集重做

- GIVEN 浏览对象主页的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“他人/我的主页交集重做”对应的公开行为。
- THEN 他人/我的主页二级过滤同一实现。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-003"></a>
### GWT-003 他人主页交集列表入口

- GIVEN 用户访问他人主页且存在对当前 viewer 可见的 typed 交集，App 使用 production Remote composition。
- WHEN 用户打开对象交集列表、刷新结果或点击其中一条可行动交集。
- THEN 列表只展示 canonical projection 返回且满足 Display Contract 的事实与证据，不在端侧拼句、补 reason 或混入另一个对象的结果。
- THEN 点击只经 typed target 导航，并把同一 intersection attribution 写入公开行为入口；页面不写交集事实或目标对象状态。
- THEN 空结果呈现明确空态；Remote failure 保留对象上下文并提供重试，禁止回退到 fixture、旧缓存句子或无归因跳转。

<a id="gwt-004"></a>
### GWT-004 我的主页交集与打动

- GIVEN 已认证用户访问自己的主页，production Remote 返回可见交集、打动摘要与当前访问水位。
- WHEN 用户打开“我的交集”，按维度或时间桶查看列表，并触发访问水位或负反馈写入。
- THEN 主标题为“我的交集”，红点聚合到“查看更多”，时间窗口按用户节奏解释；列表只展示 Remote 返回且满足 Display Contract 的事实交集。
- THEN 维度筛选、时间桶与深链 intersection identity 保持同源，点击目标携带同一 attribution，不由页面把 object kind、dimension 或 route 拼成第二套事实。
- THEN 列表读取成功后才推进访问水位；水位或反馈写入失败不隐藏已读结果、不伪造红点清零，并保留遥测与后续幂等重放路径。
- THEN 列表 Remote failure 保留当前筛选和入口上下文并提供重试，不以空态、旧缓存或本地合成的打动事实降级。

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
- 影响或价值：尚缺同一 candidate 的 production Remote 双真机证据，不能由 Provider override、Widget 或列表源码存在证明对象事实、归因导航与失败恢复已闭合。
- 目标：对象交集列表只展示 canonical projection，typed target 与 attribution 同源，空态和 Remote failure 可区分且可恢复。
- 完成判定：`GWT-003` 每条结果在物理 Android 与物理 iPhone 上通过，且两类 ReadinessResultBundle 绑定同一 commit、ContractGraph、candidate、environment 与非内存 Provider。
- 依赖：真实 viewer/object 可见性、production Remote projection、行为写入与对象级 `user_acceptance` runner；skip 不计通过。

<a id="open-004"></a>
### OPEN-004 我的主页交集与打动 GWT（S2b）

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 production Remote 列表、访问水位、反馈和失败恢复的同 candidate 双真机 CaseResult；页面显示或本地状态变化不能证明服务端红点已单调收敛。
- 目标：红点聚合进“查看更多”，交集与打动事实来自 canonical projection，访问水位和反馈经公开写面幂等收敛，失败不丢失已确认结果。
- 完成判定：`GWT-004` 每条结果在物理 Android 与物理 iPhone 上通过，且两类 ReadinessResultBundle 绑定同一 commit、ContractGraph、candidate、environment 与非内存 Provider。
- 依赖：真实 persona、production Remote 列表与访问水位/行为写面、对象级 `user_acceptance` runner；Widget、fixture、模拟器或 skip 不计通过。
