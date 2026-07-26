# L2 Design：运行流式策略 (`run-stream-policy`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“规范助手 Run/Stream 主链路的协议、策略模板与域路由行为”需要 `policy-template-routing`、`run-stream-protocol`、`run-sync-contract` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：规范助手 Run/Stream 主链路的协议、策略模板与域路由行为。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`policy-template-routing`](./policy-template-routing/spec.md)：定义“策略模板路由”的可观察主路径、失败语义及父能力交接。
- [`run-stream-protocol`](./run-stream-protocol/spec.md)：`run_started` 后必须先以 `process_replace` 建立过程快照；每个 `seq` 对同一 run。
- [`run-sync-contract`](./run-sync-contract/spec.md)：定义“运行同步契约”的可观察主路径、失败语义及父能力交接。

## 3. 端云与数据流

- 上游能力：[`assistant-run-learning`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 同步、SSE 与历史查询共用运行状态机
- 决策：同步、SSE 与历史查询共用运行状态机。
- 理由：规范助手 Run/Stream 主链路的协议、策略模板与域路由行为。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`policy-template-routing`](./policy-template-routing/spec.md)、[`run-stream-protocol`](./run-stream-protocol/spec.md)、[`run-sync-contract`](./run-sync-contract/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 指标区分首事件延迟、终态延迟、取消成功率、重放结果和策略版本。
- 策略版本支持按配置灰度和回滚，单个 run 生命周期内不得切换版本。
