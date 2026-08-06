# L1 Design：圈子与群组社区 (`circle-community`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：在保持 Circle、组织节点与群组边界清晰的同时，用一个 Circle-owned Gathering 承接内容驱动的 1:1、多人和多日行动，并与 Chat、Content、Recommendation、User 的事实所有权严格分离。

## 2. 领域模型与所有权

- authoritative ownership：拥有 `Circle`、`CircleMembership`、圈子分区、圈子文件以及圈子与群单元绑定关系；同时拥有 `Gathering`、root-owned `GatheringParticipation`、`GatheringRevision`、`GatheringOutcome`、Host/Organizer authority binding、容量/准入与 room binding state 的生命周期和写入决定权。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：Chat 的 Conversation/ConversationMembership/Message/Announcement，Content 的 Post/Media/Report，Recommendation 的候选排序，以及 User 的 Follow/mutual/Block；跨域协作必须使用 owner 公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- [`JNY-004 / SCN-001`](../spec.md#scn-001) — 在“写文字创建、可靠发布与结果回流”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-004 / SCN-002`](../spec.md#scn-002) — 在“照片创建、像素编辑、原图可靠上传与发布回流”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-004 / SCN-003`](../spec.md#scn-003) — 在“视频创建、转码处理、发布与结果回流”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-005 / SCN-011`](../spec.md#scn-011) — 在“全局搜索查询与筛选”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-007 / SCN-013`](../spec.md#scn-013) — 在“私建群、圈子群、组织节点群与主页相关群入口”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-008 / SCN-014`](../spec.md#scn-014) — 在“实体主页到圈子、组织节点、群单元与会话协作”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-010 / SCN-023`](../spec.md#scn-023) — 在“对象对外分享分发”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-011 / SCN-027`](../spec.md#scn-027) — 从内容、C 位、主页或会话来源创建并发布 room-ready Gathering，维护 Host、Participation、Revision、Outcome 与准入/容量，向 Chat 投影 room access，向 Content 提供回顾引用；Participation 不自动改变关系。

## 4. 架构与数据流

- [`activity-member-governance`](./activity-member-governance/spec.md)：让圈子 owner 管理圈子生命周期与成员角色，并让成员以稳定分页读取圈内动态。
- [`circle-client-platform`](./circle-client-platform/spec.md)：统一圈子端侧领域模型、Repository 边界与页面状态
- [`circle-collaboration-tools`](./circle-collaboration-tools/spec.md)：以圈子或组织主页内的群为协作单元，统一交流、资料与公告
- [`circle-experience-redesign`](./circle-experience-redesign/spec.md)：按群组类型提供一致的发现、详情与协作入口
- [`circle-management-and-stats`](./circle-management-and-stats/spec.md)：为圈子治理与运营提供权限受控的处置、固定口径指标和可下钻运营视图。
- [`gathering-coordination`](./gathering-coordination/spec.md)：以单一 Gathering 组合 lifecycle、Participation、Host、room+board、Outcome 与安全边界。
- [`in-circle-recommendation-loop`](./in-circle-recommendation-loop/spec.md)：把圈内行为事实转为权限受控的候选排序，并将曝光与反馈归因回评估链路。
- Gathering 主数据流为 `Content source ref -> Circle draft -> Chat ensure contextual room -> Circle publish/public projection -> Circle admission/Participation -> Chat membership -> Board projection -> Circle Outcome -> Content confirmed recap`；每一步只提交 owner 事实并以 receipt/outbox 收敛。
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 全局入口统一叫 群组
- 决策：全局入口统一叫 群组。
- 理由：让用户以清晰的圈子、组织节点与群组边界完成发现、加入、内容参与和成员协作，并保持圈子主页、默认群与共享主页之间的唯一关系语义。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 关联能力：[`activity-member-governance`](./activity-member-governance/spec.md)、[`circle-client-platform`](./circle-client-platform/spec.md)、[`circle-collaboration-tools`](./circle-collaboration-tools/spec.md)、[`circle-experience-redesign`](./circle-experience-redesign/spec.md)、[`circle-management-and-stats`](./circle-management-and-stats/spec.md)、[`in-circle-recommendation-loop`](./in-circle-recommendation-loop/spec.md)

<a id="dec-002"></a>
### DEC-002 圈子候选资格与发现排序由 circle-service 单轨拥有

- 决策：`circle-service` 以 `CircleDiscoveryFeed` 作为圈子发现候选的唯一读模型；`Circle.status/visibility` 决定候选资格，`memberCount/weeklyActiveCount` 决定当前规则排序，Circle 生命周期、成员和行为投影提交后必须失效发现缓存。
- 理由：候选资格依赖 Circle、CircleMembership 和 CircleBehaviorFact 的权威事实；留在同一领域可在公开查询前统一执行权限、归档下线、成员排除和稳定游标，不制造第二套圈子状态。
- 被否决方案：由 `recommendation-service` 复制 Circle 生命周期事件并维护独立圈子候选库；这会让归档、可见性和成员权限出现第二真相源。
- 约束与影响：`recommendation-platform` 可对 circle-service 提供的合格候选做模型评分、训练和评估，但不得拥有候选资格或回写圈子事实。
- 关联要求：`REQ-002`
- 关联能力：[`in-circle-recommendation-loop`](./in-circle-recommendation-loop/spec.md)

<a id="dec-003"></a>
### DEC-003 Gathering 及 root-owned Participation 由 Circle 单轨拥有

- 决策：Circle 以 Gathering root 同时拥有 Host/Organizer binding、Participation、Revision、容量/准入、生命周期、Outcome 与 room binding state；每个 Persona 在同一 Gathering 下只有一条 Participation，邀请、申请和公开加入通过专用 command 改变该记录。
- 理由：准入、席位、重大变更确认、取消与完成必须在同一 owner 不变量中裁决；拆成 Application、Invitation、Membership、Reservation 或交给 Chat 会产生并发超员和状态漂移。
- 被否决方案：按 1:1、多人、旅行复制聚合，或由 ConversationMembership 充当 Participation。
- 被否决方案：开放通用状态写，或把 full/in_progress 持久化为第二生命周期。
- 约束与影响：Organizer authority 与 Participation 分离；参加活动的 organizer 也必须占用一个 Participation 席位。GatheringRevision 与可选 Plan revision 分离，occurred 必须有独立参与证据。
- 关联要求：`REQ-004`、`REQ-005`
- 关联能力：[`gathering-coordination`](./gathering-coordination/spec.md)

<a id="dec-004"></a>
### DEC-004 Chat 是活动主壳但不是 Gathering owner

- 决策：每个可发布 Gathering 恰有一个 Chat contextual Conversation；有效 Participation 与 Organizer authority 分别投影 participant/admin membership。Board 是 Circle、Chat 与可选能力公开投影的 typed 组合，不建立 Workspace。
- 理由：即时消息、Announcement、已读、附件索引和通话应复用 Chat 可靠主线，而活动准入、容量、取消和 Outcome 不能迁入消息域。
- 被否决方案：发布后临时裸建群、capacity=2 改用普通 direct、活动工作区聚合、Board 写入第二份活动或消息状态。
- 约束与影响：room ready 是 Publish 前置；投影延迟显示可恢复等待态。退出、移除、Block、取消和安全终止通过 owner event 收敛访问，回滚不得恢复裸建群。
- 关联要求：`REQ-005`
- 关联协作能力：[`gathering-coordination`](./gathering-coordination/spec.md)

## 6. 质量与运行约束

- 观测至少覆盖公开详情可用率、响应到 room access 延迟、准入冲突/超员、room/board projection lag、重大变更确认、取消/Outcome、撤权与 Content 回流；metric ID、标签和 retention 只引用所属 contracts。
- 30 天窗口内公开详情成功率目标不低于 99.9%，响应成功到 room access 与撤权收敛 P95 不超过 10 秒，Board 新鲜度 P95 不超过 60 秒，并发超员和未授权 room access 必须为零。
- 生命周期、安全、准入写与撤权 100% 审计；普通读 trace 按受治理采样，默认在线 trace 保留 30 天、聚合漏斗保留 13 个月，安全证据遵循 owner retention。
- 10 分钟窗口成功率低于 99%、projection lag 或撤权 P95 超过 60 秒、任何超员/未授权访问立即告警。
- 创建、公开发现、准入、room/board、Outcome/回流分别受独立 feature flag 控制；Circle 值班负责人是总 rollback owner，Chat 与 Content 值班负责人分别负责投影与回流子链。回滚关闭新写/曝光，不删除既有对象、不启用双读或 Mock。
- 具体事物主档、采集、口碑模板和展示配置由共享主页与内容领域拥有，不在本领域复制。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
