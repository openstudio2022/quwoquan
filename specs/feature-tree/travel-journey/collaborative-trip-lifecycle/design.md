# L2 Design：Gathering 共同旅行全生命周期 (`collaborative-trip-lifecycle`)

> 对应规格：[L2 spec](./spec.md)
>
> 设计触发原因：五个 Story 共享 GatheringPlan current Revision、Gathering 权限、Chat Board、跨域引用、投影、隐私和事件恢复边界。

## 1. 背景、目标与非目标

- 背景：travel-service 与独立 Travel App surface 已退役；当前旅行体验必须在 Circle Gathering/GatheringPlan、Chat activity room/Board、Content/Media、Assistant 与 Integration 的既有 owner 边界内组合。
- 设计目标：以单一 Gathering 和可选 GatheringPlan current Revision 支撑行前、行中、行后，让 Experience、时间线、地图、日历和回顾只保存 canonical reference。
- 非目标：恢复 Trip aggregate、Travel runtime/页面/Facade/store，复制地点/内容/成员详情，或让本领域承担 AI 推理、通知调度与 Connector 调用。

## 2. Story 协作与状态流

- 状态 owner：Circle 的 Gathering 拥有活动与权限事实，GatheringPlan 只拥有 typed items、proposal、currentRevisionRef、不可变 history 与 plan-level acknowledgement refs；Chat 拥有 room/Board 所需 Conversation、Announcement 与 AssetIndex，Content 拥有 Post/Media/LocalPostDraft。
- 并发边界：计划 proposal/commit 以 expected Plan version 与 base Revision digest CAS；Experience/reference 写入绑定 owner source version，Gathering 权限在每次写入前重新裁决。
- 幂等边界：每个目标 owner command receipt、durable event/inbox 和 projection source version 唯一；Assistant 只提交经用户确认的 typed proposal。
- 一致性窗口：Plan current Revision 与 owner record 原子推进；Board、Timeline/Map、提醒与 Content draft 最终一致并从目标 owner event 重建。当前仅有 event log 的对象不得被描述为已具备 outbox。

## 3. 端云与数据流

- App 责任：在 activity room/Board 编辑提案、显示 diff、确认动作、呈现 Experience/Map/Calendar/回顾和离线 freshness；只访问目标 owner production Remote，不决定 current Revision。
- Metadata/contract：Circle/Chat/Content/Integration 各自 contracts 拥有 wire、operation、event、error 与 storage；本领域不建立 Travel contract。
- Service/Data/Ops 责任：目标 owner 提供 Object Facade、store、durable publication、projection 与观测；Ops 只保留已完成迁移的签名 crosswalk/receipt，不提供源 runtime。
- 缓存或投影：Board、Timeline/Map 与回顾来源可删除重建，任何 projection miss 不得返回业务空成功。
- 外部依赖：Place/Content/Media/User/Chat/Circle Reader、Assistant Trigger，以及地图/日历/Connector typed capability。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 计划、Board、Experience 与回顾采用目标 owner 边界

- 决策：计划变更锁定 GatheringPlan current Revision；成员资格始终读取 GatheringParticipation/Organizer authority，activity room/Board 使用 canonical Gathering/Plan reference，Experience 只关联 owner reference，回顾按明确 scope/source version 请求 Content draft。
- 理由：这些事实具有不同安全与一致性 owner；用独立 Trip、Placement、Moment 或 ShareSnapshot 聚合会重新复制活动、会话和内容边界，而失去 revision/source version 又无法证明提醒与分享对应哪个计划。
- 被否决方案：Trip/Gathering 双根、Travel Placement/Moment/ShareSnapshot 写对象、单文档覆盖、事件流无 current pointer、由 App 合并、复制 Post/Media 内容。
- 影响 Story：[`trip-plan-revision`](./trip-plan-revision/spec.md)、[`trip-placement-collaboration`](./trip-placement-collaboration/spec.md)、[`trip-moment-content-link`](./trip-moment-content-link/spec.md)、[`trip-shared-timeline`](./trip-shared-timeline/spec.md)
- 关联要求：`REQ-001`、`REQ-002`
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 legacy Trip 名称只保留文件 crosswalk

- 决策：现有五个 `trip-*` Story 路径为历史可追踪标识，正文只描述当前 Gathering 目标模型，并在各 Story 明确 legacy 对象到目标 owner 的 crosswalk。
- 理由：保留路径可维持 spec_ref 与迁移审计连续性，但把文件名误解为现行 Trip runtime 会重新建立第二真相源。
- 被否决方案：重建 Travel service 兼容层、保留旧 contract/route/surface、按旧对象维护双读页面，或另建 inventory/changelog。
- 影响 Story：本层五个 Story。
- 关联要求：`REQ-003`
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败：revision 冲突、引用失效、durable consumer 延迟、权限变化、Provider/Connector unavailable、隐私裁剪拒绝。
- 检测：CAS/unique/source-version、dead-letter、projection lag、privacy denial metric。
- 可见结果：刷新 diff、重新确认、稍后重试或移除失效引用；不丢当前计划。
- 恢复：从 Gathering/GatheringPlan/Experience owner event 重放 Board/Timeline/Map 与下游 inbox，重复 command 返回同一 receipt。
- 禁止 fallback：last-write-wins 覆盖、空 projection 冒充无内容、手工 seed、跨域直写、Travel cache/旧 contract/源服务读取。

## 6. 质量与观测

- SLO 分别跟踪 Plan command、event relay、Board/Timeline/Map freshness、提醒产生、Provider unavailable 与 Content draft；不得以一个“旅行成功”掩盖阶段失败。
- App 离线只读明确标记 freshness；恢复联网后以 canonical revision 合并，不上传本地覆盖快照。
- 旅行结束后按 retention policy 处理敏感粗位置和成员可见性，公开分享使用不可变裁剪规则 digest。
