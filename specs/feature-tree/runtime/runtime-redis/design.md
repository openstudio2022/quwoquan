# L2 Design：运行时 Redis (`runtime-redis`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“`runtime-redis` 提供跨服务一致的 Redis client、scene 连接池、健康检查和可观测机制”需要 `redis-scene-client` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：`runtime-redis` 提供跨服务一致的 Redis client、scene 连接池、健康检查和可观测机制。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`redis-scene-client`](./redis-scene-client/spec.md)：同一 scene 在同一环境必须解析到唯一连接与 prefix；prod 必需 scene 缺地址、凭据或健康状态时必须拒绝启动。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 统一 Router 与显式 scene
- 决策：统一 Router 与显式 scene。
- 理由：`runtime-redis` 提供跨服务一致的 Redis client、scene 连接池、健康检查和可观测机制。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`redis-scene-client`](./redis-scene-client/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 指标按 scene 和 command 记录次数、错误和延迟；健康检查覆盖全部必需 scene。
- 日志不得记录 secret、完整 key 值或用户敏感数据。
- local contract 可注入 fake client，真实集成证据必须连接目标环境 Redis。
