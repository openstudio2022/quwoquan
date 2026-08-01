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

### REQ-002 用户可控制运行但不能改写历史

- 用户可暂停、恢复、调整目标、继续待确认工具或取消 Run；调整只在安全边界生效并保留审计。
- 取消必须级联到仍在执行的工具与 Subagent，清理完成后才能进入取消终态。

### REQ-003 完成必须通过验证

- Run 只有在冻结的 Definition of Done 通过 Verifier 后才能完成。
- 证据不足、预算耗尽、等待输入或外部依赖时必须进入相应等待或阻断状态，不得伪造成功。
- 公开事件只包含计划、进度、决策摘要、证据和恢复动作，不包含原始思维链。

## 4. 契约引用

- object / projection：`AssistantRun`、`AssistantRunItem`、`AssistantTaskGraph`、`AssistantRunCheckpoint`、`AssistantReasoningProfile`
- operation：`StartAssistantRun`、`GetAssistantRun`、`StreamAssistantRunEvents`、`PauseAssistantRun`、`ResumeAssistantRun`、`SteerAssistantRun`、`CancelAssistantRun`、`ContinueAssistantToolUse`
- event / metric：`assistant_run_state_changed`、`assistant_run_checkpointed`、`assistant_run_recovered`、`assistant_run_completion_rejected`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 断线与重启恢复

- GIVEN 一个后台长任务已完成部分 Task 并写入 Checkpoint。
- WHEN App 断线且执行 Worker 重启后用户重新连接。
- THEN 同一 Run 从 journal 恢复并从正确序号重放事件。
- AND 已完成副作用不会重复执行。

<a id="gwt-002"></a>
### GWT-002 调整与诚实完成

- GIVEN Run 正在执行且用户补充新的约束。
- WHEN 调整在下一个安全边界生效。
- THEN 后续 Task 使用新目标修订且历史证据不被改写。
- AND Verifier 未通过时 Run 不进入完成状态。

<a id="gwt-003"></a>
### GWT-003 级联取消

- GIVEN Run 有正在执行的工具和有界 Subagent。
- WHEN 用户取消 Run。
- THEN 子执行收到取消信号并停止产生新副作用。
- AND Run 在子执行清理完成后形成唯一取消终态。

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
- 影响或价值：当前仍缺 `assistant_session` API integration 全包的 canonical Run wire 迁移、Assistant object-local API 证据归位、可启动的受管 Remote 环境，以及 Android/iPhone 真机上 App 退后台、断网、杀进程后的恢复收据。authoritative Mongo journal/CAS、durable queue、lease/heartbeat/fencing、Checkpoint、SSE journal replay、Pause/Resume/Steer/Cancel、Verifier 与工具/Subagent 级联取消已经接入 composition root；canonical Run 单一聚合、真实 Mongo/Redis 跨 Worker 接管、结构化失败 SSE 和主动 Trigger 的定向 API integration 已通过。旧全包仍有 pre-cutover `input/turnId/AssistantTurn` 假设，`verify-service-architecture` 也仍报告 Assistant object-local 证据缺口。本机仅发现 iOS simulator，受保护 Provider material 缺失使 Alpha 无法启动，因此不能把定向通过或已编译但跳过的 Patrol 当作 `GWT-001` 全面完成。
- 完成判定：先把 `assistant_session` API integration 全包迁移到 canonical Run request/envelope 并通过 Assistant object-local architecture gate；再在同一候选 baseline 上启动受管 Remote 环境，执行 Android/iPhone 真机后台/断网/杀进程恢复与 pause/steer/cancel UAT，证明 30 秒内接管、5 秒内暂停确认、10 秒内取消收敛、唯一终态及 active tool/subagent 为 0。
