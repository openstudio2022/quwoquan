# L3 Story：随拍与内容关联 (`trip-moment-content-link`)

> 所属能力：[共同旅行全生命周期](../spec.md)
>
> Journey / Scenario：[`JNY-013 / SCN-032`](../../../spec.md#scn-032)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为旅行参与者或创作者，我希望照片、视频、语音、文字和既有内容能低成本挂到正确的某天/某个行程点，从而共同时间线更丰满，内容也能在真实旅行中被查看和传播。

## 2. 范围与非目标

### In Scope

- TripMoment 追加/移动/删除、Trip/Day/Item 内容归属、Day/Item Moment 归属建议与确认、MediaAsset/Post/Place typed link、来源署名和可见范围。

### Out of Scope

- 媒体上传处理、Post 正文存储、自动公开发布和连续轨迹采集。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Moment 只保存引用且归属需用户可控

- Moment 必须引用 MediaAsset、Post 或内联文字/语音事实的 owner reference，并记录捕获时间、可选粗粒度位置、可见性和来源主体。
- 系统可根据时间与粗粒度地点建议 Day/Item，但自动建议不得直接变成公开或共享归属；用户确认、移动和删除都必须可追溯。
- 上游对象失效或不可见时保留安全占位与来源状态，不复制旧正文或媒体绕过权限。
- 完整行程游记必须以 Trip 级 ContentLink 回链；某日或某个点的分享分别使用 Day/Item 目标，禁止把整段行程伪装成第一天内容。

## 4. 契约引用

- object / projection：`travel.TripMoment`、`travel.TripPlanContentLink`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 用户确认后 Moment 与 Post 出现在正确 Item

- GIVEN 当前 Trip 某日有两个相近计划项，用户上传照片并选择一篇可见 Post。
- WHEN 系统提出归属候选且用户确认其中一个 Item。
- THEN Moment 和 Post link 各保存 canonical reference、来源主体与可见性，并只在目标 Item 的时间线/地图投影出现一次。
- AND 移动或删除后投影按 source version 收敛，Content/Media owner 事实不被修改。

## 6. 依赖

- 前置要求：MediaAsset/Post/TripItem Reader 与权限可用。
- 上游事实：上传 receipt、Post reference、时间/粗位置与用户确认。
- 下游结果：Timeline/Map、分享候选与内容采用归因。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Moment 与内容引用尚未完成跨域验收

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺的实现是 Travel 页面的真实照片/视频/语音 capture、带 canonical version 的可见 Post 选择入口、Trip 成员媒体交付授权和内容采用指标，因此共同时间线仍缺最关键的低成本内容入口。
- 当前已实现：Moment、ContentLink、成员归属、owner-scoped ready MediaAsset、公开 Post/Place Reader 和 Timeline/Map 投影已落地。App 已支持文字记录、个人待整理、当前 Item 间移动和删除，并冻结对象 version/source version 与重试 key。游记发布 continuation 只在 `published` receipt 后回写 ContentLink，失败不会删除草稿且可跨进程恢复。
- 尚缺的验收证据：Media/Post 意图虽已拒绝本地路径、CDN URL、裸 Post ID 和推测版本，但 Travel surface 仍缺 Media 上传授权与带 Post version 的 owner Reader；真实 API/media integration 和 Android/iPhone 真机收据均未完成。
- 完成判定：`GWT-001` 具有 Travel/Content local_contract、真实 API/media api_integration 与 Android/iPhone user_acceptance 直接 `spec_ref`。
- 依赖：Content/MediaAsset 跨服务 API integration 与 App capture flow。
