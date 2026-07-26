# L2 Design：实时通信网关 (`realtime-gateway`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“提供有状态的双向实时会话、重连与投递确认”需要 `realtime-channel-delivery` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：提供有状态的双向实时会话、重连与投递确认。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`realtime-channel-delivery`](./realtime-channel-delivery/spec.md)：连接状态必须由 Redis 支撑多节点查询；网关只消费 owner 事件，不直接写业务 MongoDB。

## 3. 端云与数据流

- 上游能力：[`gateway-orchestrator-foundation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 自适应传输状态机在 gateway 层统一管理，业务服务无感知
- 决策：自适应传输状态机在 gateway 层统一管理，业务服务无感知。
- 理由：提供有状态的双向实时会话、重连与投递确认。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`realtime-channel-delivery`](./realtime-channel-delivery/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 连接状态存入 Redis 以支持多节点在线查询；网关不得以进程内状态作为集群真相源。
- 指标至少区分连接数、重连、投递确认、重放、积压、跨节点路由失败和外部渠道失败。
- 外部渠道通过 `ChannelAdapter` SPI 接入；运营配置推送不与业务消息共用未声明的帧语义。
- 四环境装配只引用服务自身环境入口与 external/platform workload，不维护人工拓扑注册表。
