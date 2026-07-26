# L2 Design：Persona 与关系图谱 (`persona-follow-graph`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“本能力统一分身生命周期、公开身份、关系隔离与跨域透传”需要 `follow-relationship`、`persona-context-propagation`、`persona-management`、`persona-profile-subject-and-visibility`、`social-graph-read` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：本能力统一分身生命周期、公开身份、关系隔离与跨域透传。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`follow-relationship`](./follow-relationship/spec.md)：owner 不能作为默认 follow 主体参与社交关系建立。
- [`persona-context-propagation`](./persona-context-propagation/spec.md)：若页面允许显式选择分身，提交时必须以显式选择优先，并落库到 `personaId / profileSubjectId`。
- [`persona-management`](./persona-management/spec.md)：读取、更新、同步与激活 Persona，并在切换失败时保持原主体。
- [`persona-profile-subject-and-visibility`](./persona-profile-subject-and-visibility/spec.md)：外部展示必须使用 `ProfileSubject`，不能直接暴露可反推出同一用户多分身关系的内部字段。
- [`social-graph-read`](./social-graph-read/spec.md)：分页主键与排序必须围绕 `FollowEdge.createdAt` 或等价稳定游标。

## 3. 端云与数据流

- 上游能力：[`user-identity-profile-relationship`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 账号认证与 Persona 公开身份、关系网络分离
- 决策：账号认证与 Persona 公开身份、关系网络分离。
- 理由：本能力统一分身生命周期、公开身份、关系隔离与跨域透传。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`follow-relationship`](./follow-relationship/spec.md)、[`persona-context-propagation`](./persona-context-propagation/spec.md)、[`persona-management`](./persona-management/spec.md)、[`persona-profile-subject-and-visibility`](./persona-profile-subject-and-visibility/spec.md)、[`social-graph-read`](./social-graph-read/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 是非兼容统一升级。发布控制仅使用镜像/配置版本、环境准入和 prod rollout stage；不提供任何 persona 旧模型运行时开关，也不允许旧新双语义并行。
- feature flag、观测、SLO 验证与回滚方案。
- 数据重整 rehearsal、观测面板校验、整版回滚 rehearsal。
