# L2 Design：个人主页统一体验 (`profile-homepage-redesign`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“统一个人主页的信息架构、状态模型与跨页面互动一致性”需要 `career-interest-profile-editor`、`owner-persona-homepage-unification`、`profile-commercial-readiness` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：统一个人主页的信息架构、状态模型与跨页面互动一致性。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`career-interest-profile-editor`](./career-interest-profile-editor/spec.md)：职业与兴趣入口不依赖端侧完整枚举。
- [`owner-persona-homepage-unification`](./owner-persona-homepage-unification/spec.md)：统一 owner/Persona 主页，同时保持点赞、评论与浏览列表的既有行为。
- [`profile-commercial-readiness`](./profile-commercial-readiness/spec.md)：我的主页首屏展示真实档案与一致统计；alpha/beta/gamma/prod composition 只装配 Remote，对象级 typed double 仅存在 local_contract 测试树。

## 3. 端云与数据流

- 上游能力：[`user-identity-profile-relationship`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 主页壳只组合账号和 Persona 读模型，不复制身份事实
- 决策：主页壳只组合账号和 Persona 读模型，不复制身份事实。
- 理由：统一个人主页的信息架构、状态模型与跨页面互动一致性。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`career-interest-profile-editor`](./career-interest-profile-editor/spec.md)、[`owner-persona-homepage-unification`](./owner-persona-homepage-unification/spec.md)、[`profile-commercial-readiness`](./profile-commercial-readiness/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 主页交集资产面只消费既有公开读面，经历资产以经历交集事实直出
- 决策：我的主页交集资产面（可行动分层、我的行动、共同经历）只消费对象级 typed 读面。可行动分层消费 `IntersectionReason.actionHints/expiresAt` 做端侧展示分层，「我的行动」消费 `circle.gathering.ListMyHostedGatherings` host 本人私有读面（含 draft 与全部 audiencePolicy，host 身份由服务端从受信 persona 解析），「共同经历」资产行消费 `content.ListMyIntersections(sourceRef=coExperiencedGathering)` 的经历交集事实（云侧 `gathering_shared_experience` 物化器是唯一生产者）。
- 理由：`coExperiencedGathering` 交集是"我参与且双方已沉淀公开回顾"这一事实的唯一物化读模型。"我参与的行动"私有聚合读面不存在，端侧用 participation+`ListPostsByGathering` 组合聚合会重建第二真相源并放大读扇出。经历默认只在 mine 模式渲染（交集读面本就是 viewer 私有），他人主页公开经历展示延后到 disclosure 契约就绪。
- 被否决方案：端侧以 participation + `ListPostsByGathering` 组合推导"我的经历"、为资产区新造私有聚合契约、在 other 模式渲染经历资产区。
- 约束与影响：可行动分组内顺序保持云侧排序主权。「我的行动」私有读面授权边界固定为 host 本人（服务端 fail-closed，无 persona actor 拒绝），公开披露面 `ListGatheringsByHost` 保留给对象页等公开消费者；资产行主句只读云侧 primaryText，端不拼句。
- 关联要求：`REQ-008`
- 影响 Story：[`profile-commercial-readiness`](./profile-commercial-readiness/spec.md)
- 关联验收：`SIT-008`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 差异通过重写方法表达，类型安全。
- 方案 C：Builder 配置模式。
- `ProfileBuilder` 接收 `ProfileConfig` 配置对象，声明式描述差异。
- 高度声明式，可序列化为后端配置。
