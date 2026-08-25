---
name: continue
description: Resume and drive the development loop from wherever the session stopped - finish interrupted todos with their verification, or close a finished round via plan-next and enter the next one. Use when the user says 继续, 继续开发, 接着做, 续跑, 按规划实施, or 复盘后接着做, or when a session resumes after an interrupted todo run.
metadata:
  kind: workflow
  command: /continue
---

# continue

从会话停下的地方继续推进：中断的续完，收口的开下一轮。本工作流只做模式判定与
工作流编排，不自带领域判断——领域语义全部由被续跑的工作流拥有。
五段执行契约见根 `AGENTS.md`。

## 触发

- 显式命令 `/continue`。
- 自然语言：继续、继续开发、接着做、续跑、按规划实施、复盘后接着做。
- 会话在 todo 执行中断后恢复，且用户意图是把剩余工作做完。

## 输入

按优先级取第一个存在的：

1. 当前会话的 todo 状态与已有验证结果（中断续跑）。
2. 上一轮工作流的 HANDOFF（收口后开新轮）。
3. 既有计划文档（规格就绪、尚未开工）。

三者皆无说明没有可续的东西，回 `explore` 从 RESOLVE 开始，不要凭记忆虚构进度。

## 角色

主会话扮演 **resumer**（续跑驱动者）：判定当前处于哪种模式，把控制权交给对应工作流，
并保证推进不中断、汇报不粉饰。

## 执行

自由度：低（模式判定三选一，判定后即移交）。

- **A 中断续跑**：先审视 todo 完成情况、全部待办与已有验证结果，再从第一个未完成项
  继续。已完成且有验证证据的不重启不重做；受阻项尽可能往前推进后如实报告阻塞点。
- **B 上一轮已收口**：先走 `plan-next` 做闭环复核，再以其 HANDOFF 作为下一轮
  RESOLVE 的输入进入新一轮。
- **C 规格就绪、尚未开工**：确认父链、验收意图与 OPEN 后直接进入 `dev`。

判定依据是输入段的证据（todo 状态、HANDOFF、计划），不是对话印象；拿不准时先做
最小取证（`git status`、gate 输出、计划文件）再判。

交互协议（[interaction-protocols](../review/references/interaction-protocols.md)）：
模式 B 消费上一轮交接单时证据 SHA 过期即复跑，不得转抄结论；续跑中同样执行
协议 4 的三级裁决与协议 3 的漂移升版。

## 交付件

**推进结果与诚实汇报**：已完成事项、未完成事项、验证结果、阻塞点四段齐全。

送审前自检：每个「已完成」都有验证证据而非记忆；未完成项与阻塞点无一遗漏；
没有把受阻项包装成完成。

## 内置评审

本工作流不自派 reviewer：被编排的 `dev` / `plan-next` 等工作流各自的 PRE 与 POST
评审即本次证据，`continue` 只消费其结论，不重复评审、不绕过评审。

## 失败与停止

- [MUST NOT] 中途停住等用户催促；受阻也要推进到当前证据允许的最远处再报告。
- [MUST NOT] 偷懒、跳过验证或只做一半；todo 未清空且未受阻时不得收口。
- 测试失败或环境阻断先归因四选一（本计划引入 / 并行会话中间态 / 存量债 / 环境 flaky）
  再报告一次真实原因，不循环重述计划。
- [MUST NOT] 创建中央 backlog、任务台账、changelog 或状态矩阵；长期信息只进
  spec / design / metadata / code / test。

## HANDOFF

- **完成判据**：见 [completion-criteria](../review/references/completion-criteria.md) 本工作流段；证据链条目带命令+退出码+时间戳+SHA，下游过期即复跑。
- **产出物**：推进结果与诚实汇报；模式 B/C 下附被移交工作流的 HANDOFF。
- **未决项去向**：未完成项留在会话 todo 或转最低可关闭节点的 `OPEN-###`，不允许悬空。
- **唯一合法下游**：被续跑的工作流本身（A 为原工作流、B 为 `plan-next` 及新一轮、
  C 为 `dev`）；全部收口时报告给用户。
- **证据链**：todo 对账结果、已跑 gate/测试输出、阻塞点原文。
- **交接单**：收口轮次落 `.qwq_output/env/repo/runs/handoff/<轮次>/manifest.md` 并过 `make verify-handoff-manifest`。
