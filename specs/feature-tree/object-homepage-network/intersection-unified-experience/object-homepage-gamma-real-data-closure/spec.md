# L3 Story：对象主页 Gamma 真实数据闭环 (`object-homepage-gamma-real-data-closure`)

> 所属能力：[`intersection-unified-experience`](../spec.md)
>
> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览或维护对象主页的用户，我希望把圈子主页与实体主页从本地 UI 合格推进到 gamma-local 真实数据、真实服务、真实 App Remote、真实行为观测闭环，从而理解对象关系并完成受权限保护的操作。

## 2. 范围与非目标

### In Scope

- entity-service 与 circle-service 的 gamma-local compose/gateway/package/health/stackctl 闭环。
- 实体主页、圈子主页、相关圈子、影响摘要、对象交集、关注/加入状态的 metadata-first 端云契约闭环。
- api_integration 探针覆盖 homepage/circle/intersection/related groups/impact，并验证 primaryText 与 primarySpans。
- user_acceptance 覆盖推荐入口、搜索入口、我的主页入口、CTA、Tab、错误态和空态。
- 行为埋点与服务观测覆盖曝光、点击、证据、CTA、错误、空态和环境归因。

### Out of Scope

- 深排平台、premium pool、全量商业运营后台、支付或预约链路。
- 新增 homepage/circle 专属交集 API。
- prod rollout；本 Story 只到 gamma-local 与商用准入证据。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 gamma-local 拓扑、网关与健康检查闭环

- metadata 与 compose 静态契约通过。
- stackctl health 证明 gamma-local gateway 与 entity/circle 服务可访问。
- stackctl verify 覆盖 api_integration；Patrol runner 缺失时输出明确 user_acceptance 阻断证据。

<a id="req-002"></a>
### REQ-002 实体主页真实 bundle、简介、相关圈子与关注状态闭环

- homepage bundle、introduction、related-groups 均有 populated api_integration 结果。
- App Remote 页面不回退 Dart mock，且内部字段不外露。
- 关注状态刷新后在页面、服务响应和行为埋点中一致。

<a id="req-003"></a>
### REQ-003 圈子主页真实 detail、impact、成员、讨论与加入状态闭环

- circle list/detail/impact/feed/members 均有 populated api_integration 结果。
- App Remote 页面不回退 Dart mock，且加入状态刷新一致。
- 打动摘要只展示 primaryText 风格句，不自造“打动了谁”用户文案。

<a id="req-004"></a>
### REQ-004 对象交集理由的真实事实行契约

- homepage/circle object intersections 的 api_integration 覆盖鉴权、分页、spans、visuals、action hints 和空结果。
- objectType=homepage|circle 不退化为 interest/同好 等错误用户语义。
- feed/search/video-book host surface 的 reason target 必须等于当前业务对象，且不得通过 reason 池随机附着。
- App 本地合同断言 shared fact row、span 深链与旧链路禁用。

<a id="req-005"></a>
### REQ-005 行为归因、错误态、空态与推荐回流闭环

- 本地合同覆盖事件属性与禁止普通 click 降级。
- api_integration 覆盖服务日志、指标和错误码映射。
- user_acceptance 覆盖未登录、弱网、无理由、无记录、重试和探索 CTA。

<a id="req-006"></a>
### REQ-006 真实 API 探针：覆盖 `/homepages/{homepageId}/object-page-bundle`、`/introduction`、`/related-groups`、`/circles`、`/circles/{circleId}`、`/impact`、`/content/intersections/object`

- 真实 API 探针：覆盖 `/homepages/{homepageId}/object-page-bundle`、`/introduction`、`/related-groups`、`/circles`、`/circles/{circleId}`、`/impact`、`/content/intersections/object`；前台模块标题必须稳定映射为「这里打动的人 / 圈子打动的人」。
- App Remote 验收：实体/圈子页面在 remote/gamma 数据模式下消费同一契约，禁止回落到 Dart mock 或 UI 自造主句。
- 交集事实契约：商用可见理由只消费 `IntersectionReason.primaryText / primarySpans / sampleVisuals / representativeActor / objectVisual / lifecycleState / actionHints / iconKey`；`join(primarySpans.text) == primaryText` 必须可测。
- 实体主页正文主源闭集冻结为 `Wikipedia + 百度百科 + 搜狗百科 + 今日头条百科`
- 权威 rank 为 `0/1/2/2`。Wikidata、OSM、百科搜索只做候选发现
- Wikivoyage、360、官网、政府、门户、媒体、OTA 不得进入 source plan/source unit/writing pack/`primaryEvidenceRef`。
- 静态拓扑不是 404，也不是只在 compose 中存在；stackctl health 和 api_integration 探针必须证明可访问。
- App 页面不能用 mock、旧 `EvidenceGroup`、`intersectionPoints` 或本地拼句兜底真实推荐理由。
- 实体主页不能暴露“统一对象键、对象页模板、来源、灰度 cohort、主页管理”等运维字段。
- 圈子主页和实体主页的相关二级模块必须可点击、可刷新、可恢复，而不是静态展示。
- 错误态、空态、未登录、弱网、无理由、无记录都必须有恢复动作和埋点。
- 禁止：绕过 stackctl 手写第二套 curl base URL，或把 health 失败标成 endpoint 空结果。

## 4. 契约引用

- canonical：`surface/objectType/objectId/reasonId/targetType/targetId/env`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 gamma-local 拓扑、网关与健康检查闭环

- GIVEN entity-service 和 circle-service 已在 docker-compose.gamma-local.yaml、Caddyfile、port profile 与 package 流程中声明。
- WHEN 运行 metadata verify、compose config、stackctl health 与 stackctl verify。
- THEN gateway 可通过 gamma-local public base 访问 entity/circle/content/user 相关端点。
- THEN health 不再因为 404、路由缺失、TLS EOF 或服务未启动而失败。

<a id="gwt-002"></a>
### GWT-002 实体主页真实 bundle、简介、相关圈子与关注状态闭环

- GIVEN gamma-local seed 创建可发布的 homepage，并具备 viewer 关系、简介、缩略图、关注状态、相关圈子。
- WHEN App Remote repository 请求 homepage object-page-bundle、introduction、related-groups，并刷新关注状态。
- THEN 实体主页 Header、CTA、我的交集、这里打动的人、记录、讨论、相关圈子均来自真实服务。
- THEN 公开页面不展示统一对象键、模板、内部 sourceRefs/primaryEvidenceRef、灰度 cohort、主页管理等内部字段；仅展示可安全打开的四百科 canonical HTTPS 来源卡。

<a id="gwt-003"></a>
### GWT-003 圈子主页真实 detail、impact、成员、讨论与加入状态闭环

- GIVEN gamma-local seed 创建可访问圈子，并具备成员头像簇、加入状态、影响摘要、记录与讨论。
- WHEN App Remote repository 请求 circle list/detail/impact/feed/members，并执行 join/leave 状态刷新。
- THEN 圈子主页 Header、CTA、我的交集、圈子打动的人、记录、讨论、成员均来自真实服务。
- THEN 圈子头像独立于封面，封面只作为兜底；记录卡最多展示一条推荐理由。

<a id="gwt-004"></a>
### GWT-004 对象交集理由的真实事实行契约

- GIVEN homepage 和 circle 都有可校验 viewer relation、sample visuals、span target 与 action hints。
- WHEN 请求 /content/intersections/object?objectType=homepage|circle&objectId={id}。
- THEN 每条商用可见理由有 primaryText、primarySpans、target、reasonId、iconKey 或可解析 icon。
- THEN join(primarySpans.text) == primaryText；无 primaryText 的理由不渲染。
- THEN displayBinding 与 surface 一致：独立列表为 explicit_link 且有 typed object；对象页/内容卡为 host_implicit 或 host_plain 时不得出现可点击 self-target。
- THEN 主句禁止 raw stats、泛对象和旧术语：不出现 `2赞1评`、`这条记录`、`TA的内容`、`相关圈子`、`我的连接`。
- THEN App 不再通过 EvidenceGroup、intersectionPoints 或本地模板拼主句。

<a id="gwt-005"></a>
### GWT-005 行为归因、错误态、空态与推荐回流闭环

- GIVEN 用户从推荐、搜索、我的主页交集入口进入对象主页。
- WHEN 用户浏览理由、点击 span、展开证据、关注/加入/私信、切换 Tab、点击记录，或遇到错误/空态。
- THEN 所有事件具备 surface、objectType、objectId、reasonId、targetType、targetId、env 归因。
- THEN 服务端 health、错误码、延迟、空结果、鉴权失败与 App RuntimeFailure/CloudException 映射同源。

## 6. 依赖

- 前置要求：[`intersection-unified-experience`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 gamma-local 拓扑、网关与健康检查闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：metadata 与 compose 静态契约通过。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 实体主页真实 bundle、简介、相关圈子与关注状态闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：homepage bundle、introduction、related-groups 均有 populated api_integration 结果。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 圈子主页真实 detail、impact、成员、讨论与加入状态闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：circle list/detail/impact/feed/members 均有 populated api_integration 结果。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 对象交集理由的真实事实行契约

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：homepage/circle object intersections 的 api_integration 覆盖鉴权、分页、spans、visuals、action hints 和空结果。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-005"></a>
### OPEN-005 行为归因、错误态、空态与推荐回流闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：本地合同覆盖事件属性与禁止普通 click 降级。
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效
