# L3 Story：共同时间线、地图与分享 (`trip-shared-timeline`)

> 所属能力：[共同旅行全生命周期](../spec.md)
>
> Journey / Scenario：[`JNY-013 / SCN-032`](../../../spec.md#scn-032)、[`SCN-033`](../../../spec.md#scn-033)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为组织者、参与者或爱分享的用户，我希望同一旅行能按时间线和地图回看，也能便捷分享整段、某天、某点、路线或随拍集合，从而不用手工重新整理七天素材。

## 2. 范围与非目标

### In Scope

- Timeline/Map projection、route segment semantic、ShareSnapshot、隐私裁剪、LocalPostDraft 请求与来源引用。

### Out of Scope

- 地图 Provider 参数、任意 URL/scheme、自动发布、连续轨迹和内容编辑器实现。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 时间线、地图与分享必须源于同一冻结事实

- Timeline 和 Map 必须以同一 Trip Revision、Item、Moment、Revision event 与 Content link 投影；离线时明确 freshness。
- ShareSnapshot 必须冻结范围、source revision、引用与隐私策略 digest，支持 full/day/item/route/moment_collection 类型。
- 公开输出必须服务端移除私人住宿细节、联系方式、成员名单和实时精确位置；生成 LocalPostDraft 后仍需用户确认发布。

## 4. 契约引用

- object / projection：`travel.TripTimelineView`、`travel.TripMapView`、`travel.TripShareSnapshot`
- surface / route：`assistant.presentation.route_map`、`travel.timeline`、`travel.map`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 七日行程可分段分享且隐私一致

- GIVEN 已结束的七日 Trip 含 Revision 变化、Moment、Post link、住宿和成员信息。
- WHEN 用户分别生成完整、第一天、单个地点和路线分享，并请求游记草稿。
- THEN 每份快照绑定同一可追溯来源版本，只包含所选范围，Timeline/Map/草稿引用一致。
- AND 公开结果不含禁止字段，未知 `route_map` 的旧客户端降级为地点顺序列表和静态摘要，不白屏、不崩溃。
- AND 只有 Content owner 返回 `published` receipt 后，发布队列才按快照 scope 以稳定幂等键创建 Trip/Day/Item ContentLink；待审核、拒绝或 continuation 失败不得提前删除草稿，进程重启后继续同一来源引用。

## 6. 依赖

- 前置要求：Timeline/Map projector、Content LocalPostDraft command、Assistant Presentation renderer 可用。
- 上游事实：Trip/Revision/Item/Moment/Content link 与分享范围。
- 下游结果：App 页面、分享落地、游记草稿与传播归因。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 时间线/地图/分享尚未完整落地

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺实现：照片/视频素材装配。尚缺验收证据：真实跨域 API integration、Flutter golden/a11y 和 Android/iPhone 真机自适应。当前隐私 ShareSnapshot 已可确定性生成 Content 本地可编辑文章草稿并进入编辑器，私密快照不会携带公开实体引用；发布队列在 `published` receipt 后以不可变 snapshot reference 和稳定幂等键续接 TripPlanContentLink，失败保留草稿/任务并支持跨进程恢复。Timeline/Map projection、`route_map` 安全语义渲染、隐私 ShareSnapshot 与事件重放已落地。
- 完成判定：`GWT-001` 具有 local_contract/schema snapshot、跨域 api_integration、Flutter golden/a11y 和 Android/iPhone user_acceptance 直接 `spec_ref`。
- 依赖：Travel projector、Content draft/share、Assistant Presentation 与地图 typed intent。
