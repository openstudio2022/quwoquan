# L3 Story：共同时间线、地图、日历与回顾 (`trip-shared-timeline`)

> 所属能力：[共同旅行全生命周期](../spec.md)
>
> Journey / Scenario：[`JNY-013 / SCN-032`](../../../spec.md#scn-032)、[`SCN-033`](../../../spec.md#scn-033)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为组织者、参与者或爱分享的用户，我希望同一旅行能按时间线和地图回看，也能便捷分享整段、某天、某点、路线或随拍集合，从而不用手工重新整理七天素材。

## 2. 范围与非目标

### In Scope

- 从 Gathering Outcome、GatheringPlan current/历史 Revision、typed item 与 Experience/Content references 生成 Timeline/Map projection。
- Calendar 导出/提醒 capability、route segment 安全语义、分段分享 scope、隐私裁剪、LocalPostDraft 请求与来源引用。
- legacy TripTimelineView/TripMapView/TripShareSnapshot 到目标投影与 Content draft source 的历史 crosswalk。

### Out of Scope

- 地图 Provider 参数、任意 URL/scheme、自动发布、连续轨迹和内容编辑器实现。
- 独立 Travel Timeline/Map 页面真相、ShareSnapshot aggregate、Provider 成功伪造或旧 `travel.*` route/surface fallback。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 时间线、地图、日历与回顾必须源于同一目标事实

- Timeline 和 Map 必须以同一 Gathering、Plan Revision、typed item、Experience 与 Content reference 投影；离线时明确 freshness。
- 分享/回顾请求必须冻结 scope、source Revision/reference 与隐私策略 digest，支持整段、单日、单点、路线和 Experience 集合，但不创建 Travel-owned ShareSnapshot。
- Calendar 只消费 canonical schedule/Plan reference；设备、OAuth Connector 或 Provider unavailable 时返回结构化终态，不改变 Gathering 或 Plan。
- 公开输出必须服务端移除私人住宿细节、联系方式、成员名单和实时精确位置；生成 LocalPostDraft 后仍需用户确认发布。
- legacy Timeline/Map/ShareSnapshot ID 只用于审计 crosswalk，不进入 production route、projection key 或 Content command。

## 4. 契约引用

- current target：Circle Gathering/Plan/Experience projection、Chat Board section、Content LocalPostDraft/Post reference 与 Integration typed Map/Calendar intent。
- Presentation：只使用 active Assistant safe semantic presentation 与 canonical owner route，不使用已删除的 `travel.timeline`、`travel.map`。
- historical crosswalk：`TripTimelineView/TripMapView -> Gathering Plan/Experience projection`，`TripShareSnapshot -> immutable draft source refs + privacy policy digest`。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 七日 Gathering 可分段回顾且隐私一致

- GIVEN 已形成 Outcome 的七日 Gathering 含 Plan Revision 变化、Experience、Post reference、住宿和参与者信息。
- WHEN 用户分别生成完整、第一天、单个地点和路线分享，并请求游记草稿。
- THEN 每个 draft source 绑定同一可追溯 Gathering/Plan source version，只包含所选范围，Board、Timeline/Map 与草稿引用一致。
- AND 公开结果不含禁止字段，未知 `route_map` 的旧客户端降级为地点顺序列表和静态摘要，不白屏、不崩溃。
- AND 只有 Content owner 返回 `published` receipt 后，目标 owner 才按 scope 以稳定幂等键建立 Gathering/Plan item/Experience 与 Post reference；待审核、拒绝或 continuation 失败不得提前删除草稿，进程重启后继续同一来源引用。

## 6. 依赖

- 前置要求：Gathering/Plan/Experience projector、Content LocalPostDraft command、Integration Map/Calendar capability 与 Assistant Presentation renderer 可用。
- 上游事实：Gathering Outcome、Plan Revision/item、Experience/Content reference 与分享范围。
- 下游结果：Chat Board/owner 页面、分享落地、回顾草稿与传播归因。
- 父级设计：`DEC-001`、`DEC-002`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Board 时间线/地图/日历/回顾尚未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Chat Board 中的 Timeline/Map/Calendar/回顾 production Remote、Circle Experience projection、真实地图/日历 Provider/Connector、Content draft/share continuation、离线恢复与隐私裁剪的跨域 API integration；旧 Travel Timeline/Map 页面与 ShareSnapshot runtime 已退役，不能作为当前实现。
- 完成判定：`GWT-001` 由目标 owner local_contract、Circle/Chat/Content/Integration 跨域 api_integration、Flutter golden/a11y 和 Android/iPhone user_acceptance 直接覆盖；Provider unavailable 结构化降级，published 前零关联，公开禁止字段为零。
- 依赖：Chat Board、Circle Plan/Experience projector、Content draft/share、Assistant safe Presentation、Integration Map/Calendar Provider 与 App production Remote。
