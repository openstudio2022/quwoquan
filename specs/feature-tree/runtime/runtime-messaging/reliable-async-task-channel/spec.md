# L3 特性：reliable-async-task-channel

## 功能说明

`reliable-async-task-channel` 提供公共可靠异步任务通道，用于承载必须最终完成的后台同步、投影、聚合、fanout 和通知任务。它以数据库 Outbox 作为任务事实源，通过 dispatcher 将到期任务投递到执行队列，并通过 worker 的租约、幂等、重试、DLQ 与 Notification Outbox 保证最终一致性。

该能力不属于头像专用实现。群头像重算、群成员名册投影、inbox 投影、搜索索引刷新、用户头像传播和通知 fanout 均应通过同一通道接入。

本特性同时冻结模块化部署要求：每个领域服务由可组合 `RuntimeModule` 构成，`DeploymentPackage` 决定 onebox 或拆分包如何运行这些模块。`seed-box` 可以跨领域组合模块运行，但不得改变领域归属、事务边界或对外 API 契约。

## 核心目标

- 业务数据变更与任务请求必须同事务提交。
- 未到期任务保留在数据库事实表，由 dispatcher 按 `startAt <= now` 扫描后再投递到 ready 执行队列。
- Redis 或其它 MQ 只作为可重建的执行索引，不作为唯一事实源。
- 同一 `dedupeKey` 的 pending 任务可合并，并顺延 `startAt`，但不得超过 `maxDelayUntil`。
- worker 必须重新读取数据库最新状态，payload 只能携带版本提示。
- 任务结果与 `notification_outbox` 必须同事务提交。
- ACK 只能发生在结果事务提交之后；失败必须 retry 或进入 DLQ。
- 通知 fanout 必须可恢复，recipient 级 delivered/failed 去重账本保证部分失败只重试失败目标。
- 任务、模块、部署包、保留策略与限流策略必须通过 catalog 版本化治理，启动时不兼容即 fail-fast。
- onebox 与拆分 worker package 必须通过 `env + domain + module + shardId` 租约安全并存。

## 范围

### In Scope

- `runtime/reliabletask` 公共接口、模型、状态机和错误语义。
- `reliable_task_outbox`、`reliable_async_task`、`notification_outbox`、`reliable_task_dlq` 的字段、索引、TTL、归档与恢复约束。
- 事务性任务声明入口，业务服务不得直接写集合或直接 enqueue。
- 到期扫描 dispatcher、ready queue、consumer lease、ACK、Retry、DLQ、reclaim expired lease。
- 合并策略、幂等键、payload 白名单、RuntimeFailure 上下文。
- `RuntimeModule`、`ModuleCapability`、`DeploymentPackage`、`ProcessInstance` 的模块化部署契约。
- task catalog、module catalog、package catalog、retention policy、rate limit policy 与权限边界。
- alpha/beta/gamma/prod-gray/prod 的 onebox 与拆分部署实施路径。
- 所有现有领域服务的 module/catalog/config 处置；`chat` 首批完整接入，`user` 与 `content` 用于证明公共能力。
- `chat-service` 私有 group avatar scheduler/timer/local queue 到 reliable-task 的迁移与双链路关闭。
- T1-T4 自动化验证与故障注入用例。

### Out of Scope

- 具体群头像渲染算法。
- 具体 sync patch 协议字段扩展。
- 将 Python `rec-model-service` 并入 Go `seed-box`。
- 一次性实现所有领域的业务 worker；未完整接入的 domain 必须在 catalog/config 中显式声明禁用或延期。

## 业务约束

- 业务服务只能通过 runtime 暴露的受控 writer 在当前 repository transaction 中声明任务，例如 `ReliableTaskOutboxWriter.AddTask(ctx, tx, req)`。
- 业务服务不得 import Redis queue adapter，不得直接写 `reliable_task_outbox` 集合，不得绕过 task catalog。
- 每个 `taskType` 必须在 task catalog 中登记 payload 白名单、幂等键规则、合并策略、最大重试次数、RuntimeFailure 分类、通知策略、保留策略、限流策略与 worker module。
- payload 禁止存储易过期详情或大对象；必须以 `aggregateId`、版本号、revision、seq、hash hint 为主。
- `RuntimeFailure` 必须包含稳定错误码、`recovery.action`、`disruptionLevel` 和字符串化上下文。
- 同一 `aggregateId` 可通过 `partitionKey` 获得局部顺序；跨 aggregate 只承诺幂等最终一致，不承诺全局顺序。
- onebox 内多 domain module 共进程时，store、queue、client 和权限仍必须按 `domain/module` 作用域创建。
- deployment package 启动时必须校验 task/module/package catalog 版本兼容，不兼容必须 fail-fast。

## 领域服务接入范围

- `chat`：首批完整接入，覆盖 `chat.api`、`chat.task_outbox_dispatcher`、`chat.group_avatar_worker`、`chat.roster_projection_worker`、`chat.inbox_projection_worker`、`chat.notification_outbox_dispatcher`。
- `user`：接入头像传播与关系数据同步，覆盖 `user.api`、`user.task_outbox_dispatcher`、`user.avatar_propagation_worker`、`user.notification_outbox_dispatcher`。
- `content`：接入搜索/投影场景，覆盖 `content.api`、`content.task_outbox_dispatcher`、`content.search_index_worker`、`content.feed_projection_worker`。
- `circle`、`assistant`、`entity`、`integration`、`ops`：先完成 module/catalog/config 声明与门禁覆盖，业务 worker 按后续场景接入。
- `notification`：必须明确工程归属，提供 fanout、delivery retry、notification outbox dispatcher 模块。
- `rtc`、`realtime`、`media`、`turn`：默认作为基础设施模块纳入 catalog，不接业务 Outbox，除非后续实时通道任务单独设计。
- `recommendation`：保持 Python 独立进程，只纳入跨进程 catalog 引用与拓扑校验。

## 验收标准

### A1：可靠任务声明

给定业务服务在事务中变更业务数据并声明异步任务，当事务提交成功，则 `reliable_task_outbox` 必须持久化；当事务回滚，则业务数据与任务请求都不得存在。

### A2：到期投递

给定任务 `startAt` 晚于当前时间，当 dispatcher 扫描时，不得将任务提前放入 Redis/MQ；当 `startAt <= now`，dispatcher 才能投递到 ready 队列。

### A3：合并顺延

给定同一 `dedupeKey` 连续请求，当任务仍为 pending 且未到 `maxDelayUntil`，通道必须合并 payload 版本提示并更新 `startAt = min(now + delay, maxDelayUntil)`。

### A4：幂等与重复投递

给定 dispatcher 或 worker 因崩溃导致同一任务重复投递或重复执行，业务结果不得重复产生副作用，最终状态必须可达 `done` 或 `dead`。

### A5：结果提交与 ACK

给定 worker 完成计算，当结果写库或通知 Outbox 写入失败，则不得 ACK；当结果与通知 Outbox 同事务成功提交后，才能 ACK。

### A6：通知一致性

给定业务结果已提交，当通知 fanout 失败，业务结果不得回滚；notification outbox 必须可恢复，recipient 级账本必须保证只重试失败目标。

### A7：模块化部署一致性

给定同一环境存在 onebox 与拆分 worker package，当它们同时运行相同 domain/module 的任务时，必须通过 `env + domain + module + shardId` 租约安全竞争，不得重复产生有效副作用。

### A8：公共能力与门禁

至少一个非头像场景必须通过本通道完成 T3 验证；所有 domain 必须在 module catalog 和 config 中明确启用、禁用或延期；`make verify` 与 `make gate` 必须阻断 catalog/package/retention/permission/migration 漂移。

## 用例生成提示

- 生成事务用例时，必须覆盖提交成功、提交失败、提交后进程崩溃三类。
- 生成 dispatcher 用例时，必须覆盖未到期不投递、到期投递、投递成功但标记失败、dispatching lease timeout、shard lease 接管。
- 生成 worker 用例时，必须覆盖 claim 后崩溃、结果写库失败、结果写库成功但 ACK 失败、重复执行幂等、旧 lease token 不得 ACK 新租约。
- 生成合并用例时，必须覆盖 `pending` 合并、`processing` 不合并、`maxDelayUntil` 封顶。
- 生成通知用例时，必须覆盖全部成功、部分失败、全部失败、recipient 级去重、notification lease timeout。
- 生成模块化用例时，必须覆盖 alpha 单服务 all-in-one、beta seed-box、gamma 拆分包演练、prod-gray 灰度拆分、prod 默认 onebox。
- 生成治理用例时，必须覆盖 catalog 版本不兼容 fail-fast、权限越界阻断、retention policy 缺失、rate limit 生效、DLQ 人工恢复。