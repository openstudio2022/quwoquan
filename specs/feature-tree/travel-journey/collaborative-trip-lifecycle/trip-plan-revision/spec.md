# L3 Story：旅行计划与不可变修订 (`trip-plan-revision`)

> 所属能力：[共同旅行全生命周期](../spec.md)
>
> Journey / Scenario：[`JNY-013 / SCN-030`](../../../spec.md#scn-030)、[`SCN-031`](../../../spec.md#scn-031)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为旅行组织者，我希望把吃玩住行安排保存为可共同查看且每次变化都有明确差异的计划，从而不再依赖翻群消息或担心成员看到旧版本。

## 2. 范围与非目标

### In Scope

- TripPlan 创建、生命周期、Revision、Day/Item、角色权限、变更提议/确认、diff 与影响范围。

### Out of Scope

- 预订支付、外部价格保证、通知投递和 AI 文本生成。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 计划创建与推进必须原子、可追溯

- 创建 Trip 必须产生首个不可变 Revision；后续变更以 expected revision 和幂等键提交。
- Revision 必须记录变更原因、严重等级、结构化 diff 与受影响成员/计划项引用。
- 未确认提议、冲突、权限拒绝或持久化失败不得推进 current Revision。

<a id="req-002"></a>
### REQ-002 我的行程必须由 owner-scoped Reader 分页提供

- App 不得用本地缓存、群消息或 Placement 拼出“我的行程”；只读取 `TripPlanReader` 的 organizer-scoped named Slice。
- 列表按 `updatedAt + tripId` 稳定 keyset 分页，可按生命周期状态筛选，每页有明确上限。
- 返回摘要只含进入当前行程所需的标题、状态、日期、当前 Revision、计划项数量和更新时间，不泄漏其他组织者的 Trip 或成员信息。

## 4. 契约引用

- object / projection：`travel.TripPlan`、`travel.TripPlanRevision`、`travel.TripPlanItem`、`travel.TripMembership`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多成员并发修订只产生一个当前版本

- GIVEN Trip 当前为 revision N，两名成员基于 N 提议不同变化且组织者有确认权限。
- WHEN 组织者先后确认两个提议。
- THEN 首个成功产生 N+1 与 typed diff，第二个收到 revision conflict 和刷新动作；重试基于 N+1 后才能产生 N+2。
- AND 每个成功 revision 只发布一个可重放变化事件，失败不发布成功事实。

<a id="gwt-002"></a>
### GWT-002 组织者只看到自己的稳定分页行程列表

- GIVEN 同一环境存在该 Persona 和其他 Persona 创建的多个 Trip，且更新时间可能相同。
- WHEN 该 Persona 按状态和有限 page size 连续读取“我的行程”。
- THEN 每个自有 Trip 只出现一次，顺序由 `updatedAt + tripId` 稳定决定，cursor 非法时 fail-closed。
- AND 响应不含其他 Persona 的 Trip、成员名单或私密行程内容，App 点击摘要后再进入当前 Revision 时间线。

## 6. 依赖

- 前置要求：Persona 权限、Place/Entity 引用与 Trip store/outbox 可用。
- 上游事实：用户确认的结构化计划或变更提议。
- 下游结果：Timeline/Map、Assistant trigger、共享 card 的 revision event。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 TripPlan/Revision 尚未完成 App 与真实环境验收

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺并发 Revision 的双版对比/合并体验、真实 Mongo API integration 执行、环境激活回读和真机证据；App 已接通组织者分页目录、空白/模板 Trip 创建、安排新增/改名/删除、变更原因/重要级与冻结 CAS/幂等重试，canonical contracts、独立 Revision、aggregate/store、事务 outbox 与恢复投影已落地。
- 完成判定：`GWT-001/GWT-002` 具有 object local_contract、Mongo 真实 api_integration 与 App user_acceptance 直接 `spec_ref`。
- 依赖：Travel service 与 generated Facade。
