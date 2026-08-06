# L3 Story：Gathering 旅行计划与不可变修订 (`trip-plan-revision`)

> 所属能力：[共同旅行全生命周期](../spec.md)
>
> Journey / Scenario：[`JNY-013 / SCN-030`](../../../spec.md#scn-030)、[`SCN-031`](../../../spec.md#scn-031)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为旅行组织者，我希望把吃玩住行安排保存为可共同查看且每次变化都有明确差异的计划，从而不再依赖翻群消息或担心成员看到旧版本。

## 2. 范围与非目标

### In Scope

- 在既有 Gathering 上按需创建唯一 GatheringPlan。
- GatheringPlanRevision、typed item、proposal/Host commit、CAS、幂等、diff、历史读取与计划级影响确认引用。
- legacy TripPlan/TripPlanRevision/TripPlanItem 到 GatheringPlan/Revision/typed item 的历史 crosswalk。

### Out of Scope

- 预订支付、外部价格保证、通知投递和 AI 文本生成。
- Gathering 的 Host、Participation、日程、lifecycle、Outcome 与 conversation，以及独立 Trip root、Travel 页面或 Travel Facade。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 GatheringPlan 创建与推进必须原子、可追溯

- 同一 Gathering 最多一个 Plan；创建必须产生首个不可变 Revision，后续变更以 expected Plan version、base Revision digest 和幂等键提交。
- Revision 必须记录结构化 diff、来源与受影响 Participation/计划项 canonical reference；Plan 不复制 Gathering 标题、日程、Host、成员、lifecycle、Outcome 或会话。
- 未确认提议、冲突、权限拒绝或持久化失败不得推进 current Revision。

<a id="req-002"></a>
### REQ-002 计划读取必须从 Gathering/Board 上下文进入

- App 只通过 canonical Gathering reference 从活动群聊 Board 或 Gathering 详情读取 GatheringPlan current Revision/历史 Slice，不维护“我的 Trip”目录或本地计划真相。
- Board 摘要只组合进入计划所需的 current Revision、item 摘要、更新时间与 capability 状态；完整 Host、Participation、日程和 lifecycle 继续来自 Gathering owner。
- 无权、已退出、已取消/完成或引用失效时 fail-closed；离线缓存必须标 freshness，恢复后以 owner current Revision 收敛。

## 4. 契约引用

- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering_plan/object.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering_plan/operations.yaml`
- current target：`GatheringPlan`、`GatheringPlanRevision` 与 typed PlanItem。
- historical crosswalk：`TripPlan/TripPlanRevision/TripPlanItem -> Gathering + GatheringPlan/Revision/typed item`；legacy ID 只存在于迁移 receipt。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多参与者并发修订只产生一个当前版本

- GIVEN 一个已发布 Gathering 的 Plan 当前为 revision N，两名有效参与者基于 N 提议不同变化且 Host 有 commit 权限。
- WHEN Host 先后 commit 两个提议。
- THEN 首个成功产生 N+1 与 typed diff，第二个收到 revision conflict 和刷新动作；重试基于 N+1 后才能产生 N+2。
- AND 每个成功 revision 只发布一个可重放变化事件，失败不发布成功事实。

<a id="gwt-002"></a>
### GWT-002 Board 只展示目标 Gathering 的当前计划

- GIVEN 同一账号可访问多个 Gathering，当前 activity room 明确绑定其中一个，且其他 Gathering 也有 Plan。
- WHEN 用户从该 room 的 Board 打开计划并翻阅 Revision history。
- THEN 只返回目标 Gathering 的唯一 Plan、current Revision 与稳定分页历史，非法 cursor 或失效 authority fail-closed。
- AND 响应不混入其他 Gathering 的计划或成员私密事实，App cache 与群消息都不能覆盖 owner current Revision。

## 6. 依赖

- 前置要求：Gathering delegated owner port、Persona 权限、Place/Entity 引用与 GatheringPlan store/event publication 可用。
- 上游事实：用户确认的结构化计划或变更提议。
- 下游结果：Chat Board、Timeline/Map、Assistant trigger 与提醒消费的 revision event。
- 父级设计：`DEC-001`、`DEC-002`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 GatheringPlan production Remote 与 Board 验收未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 Circle 的 GatheringPlan target contracts/runtime 与 Mongo API 不能替代用户体验；不存在可复用的旧 Travel 页面或 generated Facade。尚缺实现：App production Remote、Chat Board 读写、可恢复 durable consumer 与并发 diff/冲突展示。尚缺验收证据：Chat/Assistant 跨域 API integration 和 Android/iPhone 结果。
- 完成判定：`GWT-001`、`GWT-002` 由 Circle object local_contract、真实 Mongo 与 Chat/Assistant 跨域 api_integration、Android/iPhone user_acceptance 直接覆盖；同一 Plan revision/digest 在 owner、Board 与 Assistant 一致，且 event publication/retry/checkpoint 可恢复。
- 依赖：Circle GatheringPlan production Remote、Gathering delegated owner port、Chat Board 与 Assistant consumer。
