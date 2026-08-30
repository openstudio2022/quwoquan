---
name: continue
description: Resume and drive the development loop from wherever the session stopped - finish interrupted todos with their verification, or close a finished round via plan-next and enter the next one. Use when the user says 继续, 继续开发, 接着做, 续跑, 按规划实施, or 复盘后接着做, or when a session resumes after an interrupted todo run.
metadata:
  kind: workflow
  command: /continue
---

# continue

## 触发与输入

用于从中断位置续跑，或收口已完成轮次后进入下一轮。输入优先是当前 todo/plan、Git 字节、最近可验指纹和持久交接（如有），不以对话印象为证据。



自然语言触发与显式 Skill 调用同轨，字段、闭集与审计隔离只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.continue`：

- PRE：`progress_update` / `delivery_planning_authorization` / `engineering_delivery_owner`。

## 执行

1. 重建 HEAD/status、目标 diff、untracked、writer、plan/todo 和证据时效。
2. 未完 todo 继续原工作流；上轮已收口时进入 `plan-next`；无可靠上下文时先 `explore`。
3. 只编排被选工作流，不自建另一套 PRE/POST/Reviewer/验证逻辑。过期证据由所属工作流复跑。

- 执行中：`exception_escalation` / `agent_led_implementation` / `$route`。

`$route` 表示按当前决定责任动态路由；Skill 不复制 envelope schema，所有可见输出统一由 canonical projector 生成。

## 完成证据

报告采用的恢复分支、已恢复工作流的当前产物/证据、剩余 todo 与首个 typed blocker。被编排 Skill 自己的完成证据仍是唯一准据。

- POST：`completion_report` / `agent_led_implementation` / `$route`。

## 失败与停止

恢复身份不唯一、指纹过期、持久交接断链或发现未授权 writer 时 `GATE_BLOCK`，先 explore/重建证据；不运行 reset/clean/kill 推测恢复。

## 条件性交接

六类触发（跨会话未完成、多人并行、环境/发布、外部阻断、证据复用、用户显式要求）统一调用 canonical handoff producer；普通闭环不落持久交接。恢复只消费 fresh durable receipt 与 Objective/hosted readback；handoff 指纹 stale 时复跑所属 evidence，不转抄聊天记忆或旧摘要。
