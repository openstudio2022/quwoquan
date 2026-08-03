# L3 Story：行程共享放置与协作治理 (`trip-placement-collaboration`)

> 所属能力：[共同旅行全生命周期](../spec.md)
>
> Journey / Scenario：[`JNY-013 / SCN-030`](../../../spec.md#scn-030)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为群主、圈主或领队，我希望一个群/圈可同时组织多个行程和活动，并让成员清楚自己能提议、确认或查看什么，从而避免小趣改错行程和群内权限混乱。

## 2. 范围与非目标

### In Scope

- TripMembership、角色、邀请/离开、Conversation/Circle Placement、多 Trip 消歧和 Gathering typed link。

### Out of Scope

- Chat/Circle/Gathering 成员真相、关系等级或有偿组织服务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Placement 与成员权限必须显式且来源可追溯

- 一个 Trip 可有多个 Placement，一个共享场景可放置多个 Trip/Gathering；每个 Placement 必须记录来源、状态和 revision。
- Assistant 或 App 只有在目标引用唯一时才能执行 Trip command；否则必须先列出候选并消歧。
- Travel 成员角色不得复制 Chat/Circle 名册；来源成员失效时通过 source-version event 收敛权限。

## 4. 契约引用

- object / projection：`travel.TripMembership`、`travel.TripPlanPlacement`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 同群多 Trip 不会误路由写入

- GIVEN 同一 Conversation 放置两个 active Trip 和一个 Gathering，用户未显式引用目标。
- WHEN 用户要求“小趣把晚餐改到八点”。
- THEN 系统返回可理解的 Trip 候选并等待选择，任何 Trip current Revision 均不变化。
- AND 用户选定后只对目标 Trip 执行权限与 revision 检查，其他对象不产生事件。

## 6. 依赖

- 前置要求：Conversation/Circle/Gathering typed reference 和主体权限可读。
- 上游事实：共享场景挂载、来源成员事件、用户选择。
- 下游结果：Assistant routing context、Trip command reachability 与共享卡片。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 多 Placement 与共享场景消歧尚未贯通

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：缺跨域 event、管理员挂载界面和多 Trip 消歧 UAT；Travel Placement 对象、CAS、隐私边界，以及使用 delegated Persona 验证 Conversation/Circle 成员与管理员身份、精确 sourceVersion 的 typed authority 已落地。
- 完成判定：`GWT-001` 具有 Travel/Chat/Circle local_contract、api_integration 和 AppRoot 共同旅行 user_acceptance 直接 `spec_ref`。
- 依赖：Chat/Circle/Gathering source event、跨服务 API integration 与 Assistant Context Reader。
