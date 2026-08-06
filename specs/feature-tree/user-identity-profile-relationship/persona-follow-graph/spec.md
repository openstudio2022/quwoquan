# L2 Business Capability：Persona 与关系图谱 (`persona-follow-graph`)

> 所属领域：[`user-identity-profile-relationship`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

本能力统一分身生命周期、公开身份、关系隔离与跨域透传。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“persona-follow-graph”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：本能力统一分身生命周期、公开身份、关系隔离与跨域透传，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-007 / SCN-012`](../../spec.md#scn-012)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：本能力统一分身生命周期、公开身份、关系隔离与跨域透传，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-007 / SCN-016`](../../spec.md#scn-016)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：本能力统一分身生命周期、公开身份、关系隔离与跨域透传，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
## 4. Story



- [`follow-relationship`](./follow-relationship/spec.md)：owner 不能作为默认 follow 主体参与社交关系建立。
- [`persona-context-propagation`](./persona-context-propagation/spec.md)：若页面允许显式选择分身，提交时必须以显式选择优先，并落库到 `personaId / profileSubjectId`。
- [`persona-management`](./persona-management/spec.md)：读取、更新、同步与激活 Persona，并在切换失败时保持原主体。
- [`persona-profile-subject-and-visibility`](./persona-profile-subject-and-visibility/spec.md)：外部展示必须使用 `ProfileSubject`，不能直接暴露可反推出同一用户多分身关系的内部字段。
- [`social-graph-read`](./social-graph-read/spec.md)：分页主键与排序必须围绕 `FollowEdge.createdAt` 或等价稳定游标。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 persona follow graph 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“本能力统一分身生命周期、公开身份、关系隔离与跨域透传”所定义的业务结果；失败终态必须可区分且不得伪造成功。
- PersonaRelationship 关注/拉黑命令具备服务端 CAS + 幂等 receipt + 事务 outbox；capability wire 端云 16 字段对齐。
- PersonaRelationship 是关系能力读模型的唯一事实所有者；主页、关系搜索与联系人发现统一嵌套 `user.persona_relationship.projection.relationship_capability_wire`，不得维护字段子集或第二 client projection。
- 关注、打招呼、会话、音视频通话与拉黑能力必须由 PersonaRelationship 内的唯一领域策略根据相同 viewer-target 事实推导；主页、关系搜索与联系人发现不得各自计算或改写动作矩阵。
- SubjectFollow 是主页/圈子/地点关注唯一真相源（entity.FollowHomepage 已退役），事件驱动 following_subjects 投影与 homepage follower 投影。
- FollowedSubjectVisitState 水位单调推进且 clientRequestId 重放安全；关注频道红点点击后跨会话不复现。
- 拉黑与打招呼用户旅程可逆：拉黑列表可查看/解除，收到的打招呼可回复/忽略，发出的 pending 请求可撤回；动作失败均有结构化反馈。

<a id="req-002"></a>
### REQ-002 若涉及 `path / operation / request_context / route / page_id`，必须按业务对象所在 metadata 目录定义，不允许在 App Repository、Router 或 assistant runtime 中再维护 override map

- 若涉及 `path / operation / request_context / route / page_id`，必须按业务对象所在 metadata 目录定义，不允许在 App Repository、Router 或 assistant runtime 中再维护 override map。
- 用户可见生命周期动作统一为“停用分身”，领域命令统一为 `retire`：
- 退役后禁止继续作为新动作主体，但永久保留 `personaId`、记录归因与内部审计链。
- 记录内容、评论、聊天消息与通知必须保留不可变作者快照，不因分身停用而改绑到 owner 或其它分身。
- 普通读接口不得返回 owner 与分身映射；审计与风控链路允许内部追踪。
- 主页壳层视觉、滚动吸顶、统一 Tab 结构与动效实现。
- 评论、聊天、圈子、邀请、助手链路不得出现身份串号；灰度期目标为 `0` 个 P0 串号事故。
- 分身切换、follow 写入、图谱读取和评论/聊天提交在弱网超时后必须保留“当前 active persona 未变 / 动作主体未确认”的明确语义。
- persona 上下文未确认时，关键动作必须阻断或要求重试，不允许在弱网场景静默回退到 owner。
- follower/following 分页重试不得跨 persona 串页或把旧 persona 的缓存结果回放到新 persona 上下文。

<a id="req-003"></a>
### REQ-003 关注主体写闭集与读并集分列，投影事件源只认真实 producer

- SubjectFollow 的写入闭集由对象内枚举 `SubjectFollowTargetKind` 拥有，取值为 homepage、circle 与 location，persona 之间的关注只归 PersonaRelationship。
- 关注频道读模型的并集值域由共享 `FollowSubjectKind` 拥有，取值为 persona、homepage、circle 与 location；读并集宽于写入闭集成立，收窄到写入闭集则会让端侧无法解析合法投影值。
- following_subject 投影的 `lifecycle.source_events` 只认真实 producer 发布的 `PersonaFollowStateChanged`、`SubjectFollowStateChanged`、`CircleMembershipJoined`、`CircleMembershipLeft`、`FollowedSubjectVisited` 与 `UserAccountClosed`。
- 主页关注复用 `SubjectFollowStateChanged`，不得再引入独立的主页关注事件名，也不得声明全仓没有 producer 的事件名。

<a id="req-004"></a>
### REQ-004 关注访问水位的投影投递只有 relay 一条主线

- 访问水位命令写入自身聚合后，对下游投影的推进只由 relay 主线承担，命令路径不再在同一次调用里尽力 apply 投影。
- 该投递是异步且至少一次的，投影消费方必须按幂等键收敛重复投递，不得假设恰好一次或与命令同步可见。
- 关注频道读模型允许在命令成功后短暂落后于水位事实，端侧不得把读模型尚未更新解释成命令失败或重发命令。

## 6. 契约与依赖

- 上游能力：[`user-identity-profile-relationship`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 persona follow graph 能力 SIT

- GIVEN 执行“persona follow graph 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“persona follow graph 能力”对应动作。
- THEN 直属 Story 共同交付“本能力统一分身生命周期、公开身份、关系隔离与跨域透传”，失败终态可区分且不产生伪成功事实。
- THEN PersonaRelationship 关注/拉黑命令具备服务端 CAS + 幂等 receipt + 事务 outbox；capability wire 端云 16 字段对齐。
- THEN 主页、关系搜索与联系人发现只消费 PersonaRelationship 所有的 canonical relationship capability wire，metadata 门禁拒绝任何重复 `dart_class` 或生成 `output_path`。
- THEN 对同一 viewer-target 的关系、打招呼会话与拉黑事实，所有公开 surface 返回由同一 PersonaRelationship 策略推导的 16 字段动作矩阵；自己、拉黑或被拉黑时所有关系动作 fail closed。
- THEN SubjectFollow 是主页/圈子/地点关注唯一真相源（entity.FollowHomepage 已退役），事件驱动 following_subjects 投影与 homepage follower 投影。
- THEN FollowedSubjectVisitState 水位单调推进且 clientRequestId 重放安全；关注频道红点点击后跨会话不复现。
- THEN 水位推进只经 relay 主线异步至少一次地到达投影，重复投递被幂等收敛，命令成功后读模型的短暂滞后不表现为失败。
- THEN 拉黑与打招呼用户旅程可逆：拉黑列表可查看/解除，收到的打招呼可回复/忽略，发出的 pending 请求可撤回；动作失败均有结构化反馈。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 persona follow graph 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：本能力统一分身生命周期、公开身份、关系隔离与跨域透传。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效