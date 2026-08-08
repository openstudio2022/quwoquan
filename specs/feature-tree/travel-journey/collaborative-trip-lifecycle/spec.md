# L2 Business Capability：Gathering 共同旅行全生命周期 (`collaborative-trip-lifecycle`)

> 所属领域：[共同旅行旅程](../spec.md)
>
> 设计归属：[`本层 design.md`](./design.md)

## 1. 能力目标

把多人多日 Gathering 组合成可共同修订、可在活动群聊 Board 协作、可行中服务、可按 Experience 沉淀并可回顾分享的旅行体验，同时用 target-only crosswalk 治理已静态退役 Trip 对象的历史数据处置。

## 2. 范围与非目标

### In Scope

- Circle-owned GatheringPlan、不可变 GatheringPlanRevision 与 typed item。
- Chat activity room/Board 中的明确 Gathering/Plan reference 与多目标消歧。
- Gathering/Plan item 上的 Experience、Post、MediaAsset、Place/Route canonical reference。
- Timeline/Map/Calendar projection、隐私裁剪、Content LocalPostDraft 请求，以及模板来源、任务 assignee 与专业署名引用。
- legacy TripPlan/Revision/Membership/Placement/Moment/ShareSnapshot/Template/GuideAssignment 到当前 owner 的 target-only 历史 crosswalk、环境 inventory 与签名迁移 receipt。

### Out of Scope

- 预订、支付、导游撮合交易、连续轨迹与应急调度。
- Assistant 推理、外部 Provider 与 Connector；由 [`assistant-run-learning`](../../assistant-run-learning/spec.md) 和 [`runtime`](../../runtime/spec.md) 负责。
- 独立 Trip aggregate、Travel runtime、Travel App 页面、Travel Facade、Travel store 或兼容读取。

## 3. Journey / Scenario 贡献

- [`JNY-013 / SCN-030`](../../spec.md#scn-030)：在既有 Gathering 上接收确认的计划提案，输出 GatheringPlan current Revision 与 typed item，并由 Board 呈现。
- [`JNY-013 / SCN-031`](../../spec.md#scn-031)：接收授权变更，输出不可变 Plan Revision、diff 与影响事件；失败保持旧 current Revision。
- [`JNY-013 / SCN-032`](../../spec.md#scn-032)：接收 Experience/Post/Media reference 和归属确认，输出同源 Timeline/Map；失效引用进入可恢复终态。
- [`JNY-013 / SCN-033`](../../spec.md#scn-033)：接收分享范围，输出隐私裁剪后的 canonical references 并请求 LocalPostDraft；未确认不发布。

## 4. Story

- [`trip-plan-revision`](./trip-plan-revision/spec.md)：以 GatheringPlan 和不可变 Revision 可靠推进当前计划。
- [`trip-placement-collaboration`](./trip-placement-collaboration/spec.md)：在 activity room/Board 使用明确 Gathering/Plan reference，并在多目标上下文中安全消歧。
- [`trip-moment-content-link`](./trip-moment-content-link/spec.md)：把 Experience 与既有 Post/Media/Plan item 通过 canonical reference 组织为共同经历。
- [`trip-shared-timeline`](./trip-shared-timeline/spec.md)：从 Gathering Outcome、Plan Revision 与 Experience references 生成时间线、地图、分段分享和回顾来源。
- [`trip-guide-template-assignment`](./trip-guide-template-assignment/spec.md)：让领队、导游与本地专家以计划来源、任务 item 和公开 Persona 引用复用经验并保留署名。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 单一 Gathering 事实支持计划、现场与分享三阶段

- Gathering 始终拥有 Host、Participation、准入、conversation、lifecycle 与 Outcome；旅行阶段只从这些事实和可选能力投影，不建立 Trip lifecycle。
- GatheringPlan current Revision、Experience references 与 Content 回顾来源必须可追溯到同一 Gathering；归档后只读历史仍从目标 owner 获取。

<a id="req-002"></a>
### REQ-002 并发、幂等、隐私与跨域收敛

- 所有写操作必须有主体、幂等键和 expected revision/source version；跨域调用通过 outbox/inbox 和公开 receipt 收敛。
- 公开分享、地图和群内投递按最小可见范围裁剪；个人 Connector、私人记忆和个人动作结果不进入共享事实。

<a id="req-003"></a>
### REQ-003 历史 Trip crosswalk 只用于 target-only 迁移与审计

- legacy TripPlan 与 lifecycle 映射到 Gathering + optional GatheringPlan；TripPlanRevision/Item 映射到 GatheringPlanRevision/typed item。
- TripMembership 映射到 GatheringParticipation 或 Organizer authority，TripPlanPlacement 映射到 Chat Board/card 中的 canonical Gathering/Plan reference；二者都不形成目标写对象。
- TripMoment/ContentLink/ShareSnapshot 映射到 Experience/Content references 与草稿来源；Template/GuideAssignment 映射到计划来源、task item assignee 和 User 公开专业声明。
- crosswalk 与签名 receipt 不得进入 production read/write mainline，不得恢复 Travel runtime、页面、Facade、store 或双读 fallback。
- 静态删除、合成快照测试与控制面协议通过均不得冒充环境历史数据迁移完成；每个环境必须以真实 source inventory、owner-command import、target readback 和 parity receipt 独立准出。

## 6. 契约与依赖

- 上游能力：Chat/Circle/Gathering 上下文、Content/Media/Entity Reader、Assistant ActionProposal。
- 下游能力：Assistant Trigger/Context、Chat activity Board/card、Content LocalPostDraft、Map/Calendar/Provider intent。
- 读取事实：只读公开 query/projection。
- 写入事实：只调用 Circle Gathering/GatheringPlan、Chat、Content 与 Integration 的目标 Facade；本领域无独立写 owner。
- 一致性要求：GatheringPlan current Revision 在 Circle owner 内原子推进，跨域事件最终一致、可重放且不复制真相。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 Gathering 旅行体验跨域收敛

- GIVEN 一个多人多日 Gathering 已绑定 activity room，成员权限和内容/地点引用有效，且会话上下文中可能出现多个 Gathering/Plan reference。
- WHEN 组织者启用 GatheringPlan、两名成员并发提议、Host 确认变更、参与者追加 Experience 并生成回顾草稿。
- THEN 只修改明确目标的 Plan，current Revision 唯一且冲突提议不覆盖；Board、Timeline/Map、提醒和 Content 草稿请求绑定同一 Gathering/Revision/reference 并幂等收敛。
- AND 公开结果不含敏感住宿、联系方式、成员名单或实时精确位置。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 Gathering 旅行体验跨域准出尚未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺实现：五个 Story 在同一 production Remote composition 中贯通 Circle owner、Assistant、Chat Board、Content/Media 与 Integration Provider/Connector；尚缺验收证据：可发布的跨域 API integration、durable event/投影恢复和 Android/iPhone 旅行体验。travel-service 生产主链已经静态退役，历史数据迁移由 `OPEN-002` 独立阻断。
- 完成判定：`SIT-001` 由目标 owner local_contract、真实跨域 api_integration 与 [AppRoot 双端共同旅行验收](../../spec.md#uat-012) 直接引用并通过；同一候选完成 Alpha/Beta/Gamma 读写、durable event 重放、Board/Timeline/Map 投影恢复、Provider unavailable 降级和 Android/iPhone UAT。
- 依赖：五个 L3 阻断 OPEN、Circle GatheringPlan production Remote、Assistant `travel_companion`、Chat Board、Content draft/media 与 Integration Provider/Connector。

<a id="open-002"></a>
### OPEN-002 四环境历史 Trip 数据处置与切流证据未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前仅有合成快照驱动的 mapping、parity、cutover 与 target-only rollback 控制面合同，尚无 alpha、beta、gamma、prod 真实历史对象全集的 owner-command import、目标 readback 和受保护切流证据。
- 完成判定：四环境逐一证明全部 legacy 类型的 sourceCount 守恒、目标 orphan/collision 为零、PII 原值零输出、parity 为 100%；切流永久关闭源 route/credential/image/config/write，Prod 的 target backup 与 target-only rollback 演练通过且不恢复源 runtime。
- 依赖：[`travel-journey OPEN-001`](../spec.md#open-001)、四环境源 inventory、目标 owner import/readback 和受保护审批。
