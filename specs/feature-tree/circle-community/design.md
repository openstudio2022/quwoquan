# L1 Design：圈子与群组社区 (`circle-community`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：让用户以清晰的圈子、组织节点与群组边界完成发现、加入、内容参与和成员协作，并保持圈子主页、默认群与共享主页之间的唯一关系语义。

## 2. 领域模型与所有权

- authoritative ownership：拥有 `Circle`、`CircleMembership`、圈子分区、圈内活动、圈子文件以及圈子与群单元绑定关系的生命周期与写入决定权。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- [`JNY-004 / SCN-001`](../spec.md#scn-001) — 在“写文字创建、可靠发布与结果回流”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-004 / SCN-002`](../spec.md#scn-002) — 在“照片创建、像素编辑、原图可靠上传与发布回流”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-004 / SCN-003`](../spec.md#scn-003) — 在“视频创建、转码处理、发布与结果回流”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-005 / SCN-011`](../spec.md#scn-011) — 在“全局搜索查询与筛选”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-007 / SCN-013`](../spec.md#scn-013) — 在“私建群、圈子群、组织节点群与主页相关群入口”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-008 / SCN-014`](../spec.md#scn-014) — 在“实体主页到圈子、组织节点、群单元与会话协作”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-010 / SCN-023`](../spec.md#scn-023) — 在“对象对外分享分发”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。
- [`JNY-011 / SCN-027`](../spec.md#scn-027) — 在“附近同趣·结伴同行·线下局”中，维护 Circle、CircleGroup、Membership 与内容放置关系，并公开加入、协作和群绑定结果。

## 4. 架构与数据流

- [`activity-member-governance`](./activity-member-governance/spec.md)：让圈子 owner 管理圈子生命周期与成员角色，并让成员以稳定分页读取圈内动态。
- [`circle-client-platform`](./circle-client-platform/spec.md)：统一圈子端侧领域模型、Repository 边界与页面状态
- [`circle-collaboration-tools`](./circle-collaboration-tools/spec.md)：以圈子或组织主页内的群为协作单元，统一交流、资料与公告
- [`circle-experience-redesign`](./circle-experience-redesign/spec.md)：按群组类型提供一致的发现、详情与协作入口
- [`circle-management-and-stats`](./circle-management-and-stats/spec.md)：为圈子治理与运营提供权限受控的处置、固定口径指标和可下钻运营视图。
- [`in-circle-recommendation-loop`](./in-circle-recommendation-loop/spec.md)：把圈内行为事实转为权限受控的候选排序，并将曝光与反馈归因回评估链路。
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

## 6. 质量与运行约束

- feature flag、观测、SLO 验证与回滚方案。
- 具体事物主档、采集、口碑模板和展示配置由共享主页与内容领域拥有，不在本领域复制。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
