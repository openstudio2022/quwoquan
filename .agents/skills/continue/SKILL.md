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

## 执行

1. 重建 HEAD/status、目标 diff、untracked、writer、plan/todo 和证据时效。
2. 未完 todo 继续原工作流；上轮已收口时进入 `plan-next`；无可靠上下文时先 `explore`。
3. 只编排被选工作流，不自建另一套 PRE/POST/Reviewer/验证逻辑。过期证据由所属工作流复跑。

## 完成证据

报告采用的恢复分支、已恢复工作流的当前产物/证据、剩余 todo 与首个 typed blocker。被编排 Skill 自己的完成证据仍是唯一准据。

## 失败与停止

恢复身份不唯一、指纹过期、持久交接断链或发现未授权 writer 时 `GATE_BLOCK`，先 explore/重建证据；不运行 reset/clean/kill 推测恢复。

## 条件性交接

普通续跑沿用原 Skill 的简短交付。只有仍会跨会话、多人并行、环境/发布或外部阻断时，更新持久交接的身份、进度、指纹和唯一恢复动作。
