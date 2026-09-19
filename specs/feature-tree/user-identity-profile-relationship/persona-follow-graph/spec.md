# L2 Business Capability：Persona 与关系图谱 (`persona-follow-graph`)

> 所属领域：[`user-identity-profile-relationship`](../spec.md)
>
> 设计引用：[本层 design.md](./design.md)

## 1. 能力目标

本能力统一分身生命周期、公开身份、关系隔离与跨域透传。

## 2. 范围与非目标

### In Scope

- 组合普通 Persona 的安全创建与恢复、不可变公开身份、人物关注及系统主动关注限额。
- 普通 Persona 与已发布 Creator 的目标解析、关系命令的真实确认与有限期限恢复、双向图读取和 Persona 级统计。
- 公开资料/统计/候选缓存与私有关系事实分离，在同一权限和版本边界下供主页、发现和联系人入口消费。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。
- ContentReaction 写入、推荐排序、Data 发布激活与 Chat 会话事务；本能力仅通过其公开契约协作。
- 将 Creator 变为登录主体、全量替换合法 ID/Pair 摘要、跨数据库分布式配额、千万粉丝同步 fanout 与长期双写兼容。

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
- PersonaRelationship 关注/拉黑命令由唯一版本仲裁、幂等 receipt 与事务 outbox 保证事实一致；capability 保留现役动作矩阵并按 canonical contract 承接关系及协作来源的版本/有效性，不以历史字段数量限制协议演进。
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

<a id="req-005"></a>
### REQ-005 身份、关注确认与图读取组合时不串主体、不伪造完成

- Persona 创建返回的实际身份是后续关系输入；Account 已提交而 Persona 未完成时不宣称主体就绪，解析尚未完成的别名或 Creator 映射不能代替可关注身份。
- 关注命令的权限、当前系统限额、前置版本、有限有效期与回执构成同一接纳边界；所有 surface 保留待确认，确定回执才推进本主体已确认事实，不以缓存当前值推断历史提交。
- 列表、社交统计和后续能力各经 owning reader 组合：Persona 与 owner 统计不混用，权限读取不消费普通缓存陈旧宽限，普通缓存的有效寿命也不能因回放或故障切换续长。
- 身份创建、目标完整性、命令仲裁与限额由 [Persona 管理](./persona-management/spec.md#req-006) 和 [关注关系](./follow-relationship/spec.md#req-007) 独立验收；有界图读取与缓存由 [社交图谱读取](./social-graph-read/spec.md#req-005) 独立验收。本层只约束组合，不另建协议、统计或完成台账。

## 6. 契约与依赖

- 上游能力：[`user-identity-profile-relationship`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：[DEC-002](./design.md#dec-002) 至 [DEC-010](./design.md#dec-010) 明确目标身份、创建恢复、Pair、命令终结、限额、读取、统计、缓存与端侧确认；跨 owner 不宣称一个不存在的全局事务。
- canonical contracts：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/`、`quwoquan_service/services/user-service/contracts/persona_management/persona/`、`quwoquan_service/services/user-service/contracts/account/user_account/`、`quwoquan_service/services/user-service/contracts/profile_projection/creator_runtime_profile/`。
- 系统限制与资源预算只由 `quwoquan_service/services/user-service/config/schema.yaml` 及现役环境配置激活，能力规格不复制 wire schema 或配置发布接口。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 persona follow graph 能力 SIT

- GIVEN 执行“persona follow graph 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“persona follow graph 能力”对应动作。
- THEN 直属 Story 共同交付“本能力统一分身生命周期、公开身份、关系隔离与跨域透传”，失败终态可区分且不产生伪成功事实。
- THEN PersonaRelationship 关注/拉黑命令具备版本仲裁、幂等 receipt 与事务 outbox；capability 端云由同一 canonical contract 生成，保留现役动作矩阵并按来源表达版本和有效性。
- THEN 主页、关系搜索与联系人发现只消费 PersonaRelationship 所有的 canonical relationship capability wire，metadata 门禁拒绝任何重复 `dart_class` 或生成 `output_path`。
- THEN 对同一 viewer-target 的关系、打招呼会话与拉黑事实，所有公开 surface 返回由同一 PersonaRelationship 策略推导的动作矩阵；自己、拉黑或被拉黑时所有关系动作 fail closed，Creator 被关注不获得登录主体或聊天能力。
- THEN SubjectFollow 是主页/圈子/地点关注唯一真相源（entity.FollowHomepage 已退役），事件驱动 following_subjects 投影与 homepage follower 投影。
- THEN FollowedSubjectVisitState 水位单调推进且 clientRequestId 重放安全；关注频道红点点击后跨会话不复现。
- THEN 水位推进只经 relay 主线异步至少一次地到达投影，重复投递被幂等收敛，命令成功后读模型的短暂滞后不表现为失败。
- THEN 拉黑与打招呼用户旅程可逆：拉黑列表可查看/解除，收到的打招呼可回复/忽略，发出的 pending 请求可撤回；动作失败均有结构化反馈。
- THEN 实际创建身份、普通 Persona/Creator 目标、命令回执与当前图读取可串联核对；未决、超限、旧依据及权威故障不会被跨页面或缓存包装为成功，公开统计不串 Persona，具体正确性与容量结果分别由直属 Story 验收证明。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 persona follow graph 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺能证明直属 Story 在同一候选下组合交付身份、确认关系、公开读面与跨域权限的完整 SIT 证据；单条旧 CAS/receipt 测试不证明新增命令依据、Creator 资格与统计缓存边界。
- 完成判定：`SIT-001` 对应组合行为满足且真实测试 `spec_ref` 有效；最低节点的 [Persona 管理 OPEN-001](./persona-management/spec.md#open-001)、[关注关系 OPEN-002](./follow-relationship/spec.md#open-002)、[社交图谱读取 OPEN-002](./social-graph-read/spec.md#open-002) 分别承担新增能力及合同/测试缺口，不以本层跟踪项替代其准出阻断。
