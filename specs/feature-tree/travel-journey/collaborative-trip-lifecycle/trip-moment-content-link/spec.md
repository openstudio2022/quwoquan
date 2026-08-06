# L3 Story：旅行 Experience 与内容引用 (`trip-moment-content-link`)

> 所属能力：[共同旅行全生命周期](../spec.md)
>
> Journey / Scenario：[`JNY-013 / SCN-032`](../../../spec.md#scn-032)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为旅行参与者或创作者，我希望照片、视频、语音、文字和既有内容能低成本挂到正确的某天/某个行程点，从而共同时间线更丰满，内容也能在真实旅行中被查看和传播。

## 2. 范围与非目标

### In Scope

- Gathering/Plan item 下 Experience reference 的追加、移动、删除、归属建议与用户确认。
- MediaAsset/Post/Place/文字或语音 owner reference、来源署名、可见范围和 source version。
- legacy TripMoment/TripPlanContentLink 到 Experience/Content canonical reference 的历史 crosswalk。

### Out of Scope

- 媒体上传处理、Post 正文存储、自动公开发布和连续轨迹采集。
- 独立 Moment aggregate、Travel capture 页面、媒体字节复制或使用本地路径/CDN URL 代替 owner reference。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Experience 只保存引用且归属需用户可控

- Experience 必须引用 MediaAsset、Post、Place 或所属 owner 的文字/语音事实，并记录捕获时间、可选粗粒度位置、可见性、来源主体与 source version。
- 系统可根据时间与粗粒度地点建议 Plan item，但自动建议不得直接变成公开或共享归属；用户确认、移动和删除都必须可追溯。
- 上游对象失效或不可见时保留安全占位与来源状态，不复制旧正文或媒体绕过权限。
- 完整回顾必须引用 Gathering/Outcome；某日或某个点的分享分别引用 Plan Revision/item/Experience scope，禁止把整段旅行伪装成第一天内容。
- legacy Moment/ContentLink ID 只存在于迁移 receipt，不得成为 production query key 或写入目标。

## 4. 契约引用

- current target：Circle-owned Gathering/Plan Experience reference；Content-owned Post/MediaAsset/LocalPostDraft。
- canonical owner 边界：[`gathering-coordination`](../../../circle-community/gathering-coordination/spec.md)、[`discovery-content`](../../../discovery-content/spec.md)。
- historical crosswalk：`TripMoment -> Experience reference`，`TripPlanContentLink -> Gathering/Plan item/Experience 与 Content canonical reference`。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 用户确认后 Experience 与 Post 出现在正确计划项

- GIVEN 当前 GatheringPlan 某日有两个相近 item，用户持有 ready MediaAsset 并选择一篇有权查看的 Post。
- WHEN 系统提出归属候选且用户确认其中一个 Item。
- THEN Experience 和 Post link 各保存 canonical reference、source version、来源主体与可见性，并只在目标 item 的时间线/地图投影出现一次。
- AND 移动或删除后投影按 source version 收敛，Content/Media owner 事实不被修改。

## 6. 依赖

- 前置要求：MediaAsset/Post/GatheringPlan item Reader 与权限可用。
- 上游事实：上传 receipt、Post reference、时间/粗位置与用户确认。
- 下游结果：Timeline/Map、分享候选与内容采用归因。
- 父级设计：`DEC-001`、`DEC-002`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Experience reference 与内容链路尚未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Circle owner 的 Experience reference contract/runtime、Chat Board production Remote 入口、带 canonical version 的 Media/Post 选择、媒体授权、内容采用指标与真实 API/media integration；已删除的 Travel capture/Moment 页面不能作为当前证据。
- 完成判定：`GWT-001` 由 Circle/Content object local_contract、真实 API/media api_integration 与 Android/iPhone user_acceptance 直接覆盖；引用失效、权限变化、重放与离线恢复均不复制内容或产生重复 Experience。
- 依赖：Circle Experience owner contract、Content/MediaAsset Reader 与 command、Chat Board/App production Remote 和媒体 capture flow。
