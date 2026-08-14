# L3 Story：持久 Agent Run 编排 (`durable-agent-run-orchestration`)

> 所属能力：[小趣统一体验](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)
>
> 设计归属：[L2 DEC-005](../design.md#dec-005)

## 1. 用户价值

作为发起深度研究或长任务的用户，我希望任务在断线和服务重启后仍可继续，并能查看进度、暂停、恢复、补充约束或取消，从而可靠获得通过完成条件验证的结果。

## 2. 范围与非目标

### In Scope

- 持久 Run 状态、RunItem journal、TaskGraph、Checkpoint、Reasoning Profile、控制命令和终态验证。
- 有界 Subagent、工具级联取消、SSE 重放与等待/完成通知。

### Out of Scope

- 向用户暴露模型原始思维链、无预算的无限自治或允许多个 Agent 直接并发修改共享状态。

## 3. 行为要求

### REQ-001 长任务不依赖连接或单实例存活

- Run 必须持久化目标、约束、完成条件、任务依赖、进度、证据、预算与 Checkpoint。
- Worker 中断后必须从同一 Run journal 恢复，不得创建第二条执行事实或重复副作用。
- 每个并行 Subagent 必须是同一 `AssistantRun.TaskGraph` 中可恢复的 child TaskNode；claim、lease、heartbeat、fencing token、attempt、幂等身份、结果 Artifact 与终态回执都由该 Run 的 CAS/journal 持有，禁止另建进程内或旁路子任务真相源。
- Manager 只能在所有 child TaskNode 已形成持久终态回执后综合；并行 Worker 只提交各自 TaskNode/RunItem，不得并发写共享可变聚合结果。

### REQ-002 用户可控制运行但不能改写历史

- 用户可暂停、恢复、调整目标、继续待确认工具或取消 Run；调整只在安全边界生效并保留审计。
- 取消必须级联到仍在执行的工具与 Subagent，清理完成后才能进入取消终态。

### REQ-003 完成必须通过验证

- Run 只有在冻结的 Definition of Done 通过 Verifier 后才能完成。
- 证据不足、预算耗尽、等待输入或外部依赖时必须进入相应等待或阻断状态，不得伪造成功。
- 公开事件只包含计划、进度、决策摘要、证据和恢复动作，不包含原始思维链。
- AgentLoop 生命周期在 `PrePlan`、`PostPlan`、`PreToolUse`、`PostToolUse`、`PreCompact`、`PostCompact`、`BeforeComplete`、`OnBlocked`、`OnStop` 统一调用有序 Hook；Hook 只接收有界决策数据，不接收模型原始思维链。
- Hook 转换后的工具名、输入、预算与确认语义必须重新通过 canonical Tool metadata 和运行时策略；Hook 阻止、要求确认或篡改受保护 Run 事实时必须 fail closed，不得绕过同意、工具权限或完成门。

## 4. 契约引用

- object / projection：`AssistantRun`、`AssistantRunItem`、`AssistantTaskGraph`、`AssistantRunCheckpoint`、`AssistantReasoningProfile`
- operation：`StartAssistantRun`、`GetAssistantRun`、`StreamAssistantRunEvents`、`PauseAssistantRun`、`ResumeAssistantRun`、`SteerAssistantRun`、`CancelAssistantRun`、`ApproveAssistantToolUse`、`SubmitDeviceActionReceipt`
- event / metric：`assistant_run_state_changed`、`assistant_run_checkpointed`、`assistant_run_recovered`、`assistant_run_completion_rejected`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 断线与重启恢复

- GIVEN 一个后台长任务已完成部分 Task 并写入 Checkpoint。
- WHEN App 断线且执行 Worker 重启后用户重新连接。
- THEN 同一 Run 从 journal 恢复并从正确序号重放事件。
- AND 已完成副作用不会重复执行。
- AND 已完成 Subagent 直接复用同一输入 digest 的终态回执；租约过期的未完成 Subagent 以更高 fencing token 和 attempt 接管，旧 Worker 不能再提交结果。

<a id="gwt-002"></a>
### GWT-002 调整与诚实完成

- GIVEN Run 正在执行且用户补充新的约束。
- WHEN 调整在下一个安全边界生效。
- THEN 后续 Task 使用新目标修订且历史证据不被改写。
- AND Verifier 未通过时 Run 不进入完成状态。
- AND 规划、工具、压缩与完成 Hook 均在真实 Worker/AgentLoop 安全边界调用，任一拒绝不会被误报为完成。

<a id="gwt-003"></a>
### GWT-003 级联取消

- GIVEN Run 有正在执行的工具和有界 Subagent。
- WHEN 用户取消 Run。
- THEN 子执行收到取消信号并停止产生新副作用。
- AND Run 在子执行清理完成后形成唯一取消终态。
- AND 被取消 child TaskNode 的旧 lease heartbeat/finish 均被 fencing 拒绝，不能在父 Run 终态后补写结果。

## 6. 依赖

- 前置要求：AssistantRun authoritative store、事件日志、Artifact Store 与 Tool Fabric 可用。
- 上游事实：用户目标、Reasoning Profile、Skill/Context 与 Provider capability。
- 下游结果：可恢复 Run、终态快照、通知与验收证据。
- 父级设计：`DEC-005`

## 7. 开放事项

### OPEN-001 双端真实后台恢复验收尚未闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺 Gamma 同 digest 跨实例恢复收据和 Android/iPhone 真机后台恢复收据，因此长任务不能进入商业准出。Alpha canonical 启动与 health 29/29 已取得（run `20260813T160518410673Z-d38bed3e0945497980753e19bcb051e5-health-alpha-local`）。
- 已完成实现：Mongo journal/CAS、durable queue、lease/heartbeat/fencing、Checkpoint、SSE replay、Pause/Resume/Steer/Cancel、Verifier 及工具/Subagent 级联取消已接入 composition root。canonical Run 是唯一公开 request/envelope。
- 已完成本地证据：定向跨 Worker、结构化失败 SSE、主动 Trigger 和 local contract 已有覆盖。current-source 真实 MongoDB 全包 API integration 已全量通过（19/19 包，收据 `.qwq_output/env/repo/runs/assistant-acceptance/assistant_service_api_integration_full_20260812.log`）。
- 尚缺验收证据：同一 candidate digest 的 Gamma 跨实例恢复收据，以及 Android/iPhone 受管真机后台、断网、杀进程恢复尚未取得。最近一次 Gamma 启动被并行 `beta-local` 操作锁与 Alpha 占用的 `workstation-commercial-runtime` 阻断（up run `20260813T165117596635Z-05f1f7ae24b149f187e67df4127e90fd-up-gamma`）。
- 契约状态：`PauseAssistantRun` / `ResumeAssistantRun` / `SteerAssistantRun` 在 `operations.yaml` 保持 `commercial.status: blocked`。当前没有跨实例恢复收据，因此不翻绿。`ApproveAssistantToolUse` / `SubmitDeviceActionReceipt` 继续由 tool-fabric OPEN-001 保持 blocked。
- 完成判定：`GWT-001`、`GWT-002` 与 `GWT-003` 在同一候选 baseline 上成立——先通过 current-source 真实 Mongo/Redis Assistant API integration，再启动受管 Remote 环境，执行 Android/iPhone 真机后台/断网/杀进程恢复与 pause/steer/cancel UAT，证明 30 秒内接管、5 秒内暂停确认、10 秒内取消收敛、唯一终态及 active tool/subagent 为 0。凭 Gamma 或 Alpha 跨实例恢复收据后，才把上述三条 durable op 改为 `commercial: ready`。
