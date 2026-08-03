# L2 Design：共同旅行全生命周期 (`collaborative-trip-lifecycle`)

> 对应规格：[L2 spec](./spec.md)
>
> 设计触发原因：五个 Story 共享 Trip current Revision、成员权限、跨域引用、投影、隐私和事件恢复边界。

## 1. 背景、目标与非目标

- 背景：计划、群聊、Gathering、随拍和内容分享目前是分散事实，无法形成可追溯共同经历。
- 设计目标：以一个 Trip aggregate 和不可变 Revision 支撑行前、行中、行后，并让外部对象保持各自 ownership。
- 非目标：复制地点/内容/成员详情，或让 Travel Service 承担 AI 推理、通知调度与 Connector 调用。

## 2. Story 协作与状态流

- 状态 owner：TripPlan 只拥有 lifecycle 与 currentRevisionRef；TripMembership、TripPlanPlacement、Moment、Template 与 GuideAssignment 均由自己的对象 Facade 和 store 拥有，并以 TripRef 关联。
- 并发边界：结构/计划变化以 expected revision CAS，成员/放置/ Moment 分别以对象 version 与 source version 并行推进，Template 与 GuideAssignment 分别维护 revision。
- 幂等边界：每个 command receipt、outbox event、跨域 inbox 和 projection source version 唯一。
- 一致性窗口：当前 Revision 与 outbox 同事务；Timeline/Map/Assistant trigger/Content draft 最终一致并可从事件重建。

## 3. 端云与数据流

- App 责任：编辑提案、显示 diff、确认动作、离线只读缓存和 semantic rendering；不决定 current Revision。
- Metadata/contract：Travel 对象 contracts 拥有 wire、operation、event、error、storage；跨服务只引用共享 schema。
- Service/Data/Ops 责任：Travel service 提供 Object Facade、store、outbox、projection worker、环境入口与观测；数据管线不发布用户 Trip。
- 缓存或投影：Timeline/Map 可删除重建，任何 projection miss 不得返回业务空成功。
- 外部依赖：Place/Content/Media/User/Chat/Circle Reader，Assistant Trigger，以及地图/日历 typed capability。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 计划、成员/放置、Moment 和跨域分享采用不同一致性边界

- 决策：计划变更锁定 Trip current Revision。成员与共享放置分别由 `TripMembership`、`TripPlanPlacement` 聚合管理，Moment 按 Trip/Item 追加；ShareSnapshot 冻结明确范围和来源版本后再请求 Content draft。
- 理由：把协作成员、多个群圈放置和随拍塞进一个大文档会放大冲突与媒体写入成本；完全失去 TripRef/source version 又无法证明分享和提醒对应哪个计划版本。
- 被否决方案：单文档覆盖、事件流无 current pointer、由 App 合并、复制 Post/Media 内容。
- 影响 Story：[`trip-plan-revision`](./trip-plan-revision/spec.md)、[`trip-placement-collaboration`](./trip-placement-collaboration/spec.md)、[`trip-moment-content-link`](./trip-moment-content-link/spec.md)、[`trip-shared-timeline`](./trip-shared-timeline/spec.md)
- 关联要求：`REQ-001`、`REQ-002`
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败：revision 冲突、引用失效、outbox/consumer 延迟、权限变化、隐私裁剪拒绝。
- 检测：CAS/unique/source-version、dead-letter、projection lag、privacy denial metric。
- 可见结果：刷新 diff、重新确认、稍后重试或移除失效引用；不丢当前计划。
- 恢复：从 aggregate/event 重放 projection 和下游 inbox，重复 command 返回同一 receipt。
- 禁止 fallback：last-write-wins 覆盖、空 projection 冒充无内容、手工 seed、跨域直写。

## 6. 质量与观测

- SLO 分别跟踪 command、event relay、projection freshness、提醒产生和 share snapshot；不得以一个“Trip success”掩盖阶段失败。
- App 离线只读明确标记 freshness；恢复联网后以 canonical revision 合并，不上传本地覆盖快照。
- 旅行结束后按 retention policy 处理敏感粗位置和成员可见性，公开分享使用不可变裁剪规则 digest。
