# L2 Business Capability：共同旅行全生命周期 (`collaborative-trip-lifecycle`)

> 所属领域：[共同旅行旅程](../spec.md)
>
> 设计归属：[`本层 design.md`](./design.md)

## 1. 能力目标

把多人旅行从一次性计划升级为可创建、共同修订、行中服务、随拍沉淀、地图回看、分段分享和模板复用的持续业务对象。

## 2. 范围与非目标

### In Scope

- Trip 计划/Revision/Item/成员与角色。
- Conversation/Circle 多 Placement、Gathering 引用、Moment/Post link、Timeline/Map、ShareSnapshot、Template 与 GuideAssignment。

### Out of Scope

- 预订、支付、导游撮合交易、连续轨迹与应急调度。
- Assistant 推理、外部 Provider 与 Connector；由 [`assistant-run-learning`](../../assistant-run-learning/spec.md) 和 [`runtime`](../../runtime/spec.md) 负责。

## 3. Journey / Scenario 贡献

- [`JNY-013 / SCN-030`](../../spec.md#scn-030)：接收确认的计划提案，输出 Trip/Revision/Item/Placement。
- [`JNY-013 / SCN-031`](../../spec.md#scn-031)：接收授权变更，输出不可变 Revision、diff 与影响事件；失败保持旧 current Revision。
- [`JNY-013 / SCN-032`](../../spec.md#scn-032)：接收 Moment/Post 引用和归属确认，输出 Timeline/Map；失效引用进入可恢复终态。
- [`JNY-013 / SCN-033`](../../spec.md#scn-033)：接收分享范围，输出隐私裁剪快照和 LocalPostDraft 请求；未确认不发布。

## 4. Story

- [`trip-plan-revision`](./trip-plan-revision/spec.md)：创建计划并以不可变 Revision 可靠推进当前事实。
- [`trip-placement-collaboration`](./trip-placement-collaboration/spec.md)：在群聊/圈子放置多个 Trip，并以成员角色治理共同提议与确认。
- [`trip-moment-content-link`](./trip-moment-content-link/spec.md)：把 Moment 与既有 Post/Media/Item 通过引用组织为共同经历。
- [`trip-shared-timeline`](./trip-shared-timeline/spec.md)：从同一事实生成时间线、地图、分段分享和游记来源。
- [`trip-guide-template-assignment`](./trip-guide-template-assignment/spec.md)：让领队、导游与本地专家复用模板、承担任务并保留署名边界。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 同一事实支持计划、现场与分享三阶段

- Trip lifecycle 必须覆盖 planning/active/completed/archived，并保持 current Revision、Moment 与 ShareSnapshot 的来源链。
- 不得因阶段变化复制 Trip 或创建第二聚合；归档后仍可回看，恢复活动必须形成显式 lifecycle command。

<a id="req-002"></a>
### REQ-002 并发、幂等、隐私与跨域收敛

- 所有写操作必须有主体、幂等键和 expected revision/source version；跨域调用通过 outbox/inbox 和公开 receipt 收敛。
- 公开分享、地图和群内投递按最小可见范围裁剪；个人 Connector、私人记忆和个人动作结果不进入共享事实。

## 6. 契约与依赖

- 上游能力：Chat/Circle/Gathering 上下文、Content/Media/Entity Reader、Assistant ActionProposal。
- 下游能力：Assistant Trigger/Context、Chat/Circle card、Content LocalPostDraft、App Travel 页面。
- 读取事实：只读公开 query/projection。
- 写入事实：Travel Facade 只写 Travel 对象；跨域写走目标 Facade。
- 一致性要求：Trip 聚合内强一致，跨域事件最终一致、可重放且不复制真相。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 多成员、多 Placement 的完整 Trip 收敛

- GIVEN 一个共享场景含多个 Trip/Gathering，成员角色和内容/地点引用有效。
- WHEN 组织者创建计划、两名成员并发提议、确认变更、追加 Moment 并生成分享。
- THEN current Revision 唯一且冲突提议不覆盖，Timeline/Map/ShareSnapshot 指向同一版本和引用，提醒、草稿请求与跨域投影幂等收敛。
- AND 公开结果不含敏感住宿、联系方式、成员名单或实时精确位置。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 共同旅行能力尚未形成端到端准出证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：缺贯穿 AppRoot 的共同旅行 user acceptance、Chat/Circle/Content/User 跨域闭环、真实存储 API integration 执行和环境/真机证据；本层五个 Story 的 Travel 运行时、typed Remote、页面/Coordinator 与 local_contract 已落地，但仍不能证明用户旅程可发布。
- 完成判定：`SIT-001` 在 local_contract、api_integration 与 AppRoot 共同旅行 user_acceptance 中直接引用并通过；同一候选完成 Alpha/Beta/Gamma 读写、事件重放、投影恢复和真机 UAT。
- 依赖：Travel service skeleton、Assistant travel_companion、跨域 Reader/command/event 与 App Travel surface。
