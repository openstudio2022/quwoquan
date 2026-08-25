---
name: plan-next
description: Close out a development round by reconciling the plan against real artifacts and adjudicating every gap as fix-now / OPEN / out-of-scope, then generate the next round's plan. Use when the user says 下一轮做什么, 计划复核, 闭环自检, or 这轮做完了吗.
metadata:
  kind: workflow
  command: /plan-next
---

# plan-next

先对整轮做**闭环复核**，再生成下一轮会话计划。顺序不能颠倒——
未经对账就规划下一轮，等于用新计划遮盖旧残量。五段执行契约见根 `AGENTS.md`。

## 触发

- 显式命令 `/plan-next`。
- 自然语言：下一轮做什么、计划复核、闭环自检、这轮做完了吗。

## 输入

- 各工作流最近一次通过的 POST 评审 HANDOFF（本轮尚未跑过 gate 时先补跑影响面 gate）。
- 当前会话计划（`.cursor/plans/*.plan.md` 或会话 todos）、Git diff、测试与 gate 证据。

## 角色

主会话扮演 **reconciler**（对账裁决者）：只对账、归因与裁决，不实现修复。

## 执行

自由度：中（五段顺序固定，裁决自由）。

把原计划条目**复制进回复逐项勾选对账**（checklist copy-in），顺序执行五段：

1. **计划对账** — 逐条对照真实产物（git diff、门禁输出、测试结果）判定四选一：
   `完成有证据 / 完成但证据弱 / 部分完成（写明范围裁剪理由与残量）/ 未完成`。
   **判据是达成意图，不是做了动作。** 证据必须指向具体命令输出或测试结果。
2. **并行任务归因** — 用 `git status` 区分本计划改动与并行会话改动。每个失败或红灯
   强制归因四选一：`本计划引入 / 并行会话中间态 / 存量债 / 环境 flaky`。
   归因必须有基线对照证据（HEAD 重跑、`git log --follow`、文件归属、复跑）。
   [MAY]「并行会话中间态」用最小 stash 对照取证：`git stash push -- <本轮文件>`
   后复跑门禁再 `git stash pop`（pathspec 只触碰本会话 scope 内文件），红灯仍在即失败预存。
   [MUST NOT] 无证据断言「与我无关」。列出双向交接项。
3. **环境与门禁健康** — 重跑影响面门禁确认归零。检查长期阻塞信号：
   `stackctl health/verify` 证据、连续多轮红且无 owner 的门禁、凭证或网络或容器依赖缺失。
   每项区分「本轮可修」与「登记 OPEN」。
4. **缺口与风险裁决** — 每个缺口先分「事实还是决策」：事实由 Git diff / gate / 测试证据
   取证；裁决性缺口按
   [explore/references/decision-tree-interview.md](../explore/references/decision-tree-interview.md)
   问用户。逐项三选一：`当前增量直接修复 / 写入最低 owner 节点 OPEN / 明确 Out of Scope`。
   OPEN 的完成判定必须引用验收锚点。受影响棘轮基线逐个列出当前值与收敛方向，只减不增。
   [MUST] 每个新发现问题先做泛化判定「孤例还是一类」；判为一类的必须系统性排查
   （全仓扫描 / gate 化 / 棘轮化）一次收敛并加防回潮锁，禁止单点修复后靠下一轮
   plan-next 兜底——这是 plan-next 自然收敛（而非无休止循环）的前提。
   [MUST NOT] 中央风险台账、changelog 或成熟度矩阵。
5. **闭环判定** — 按批次列：完成项与证据、未完成项与缺口、初始风险与现状的逐条对照、
   剩余阻断。判定三选一：`闭环 / 带残量闭环（棘轮与 OPEN 承接）/ GATE_BLOCK`。

随后生成下一轮计划：

1. 已解决事项删除 OPEN 并成为当前规格；未完成事项放最低 owner 节点 OPEN。
   [MUST NOT] 用下一轮计划遮盖未完成项。
2. 跑 `make feature-tree-overview` 与 `make feature-tree-change-report`。
3. 下一轮计划写在**当前会话**，含目标、规格增量、实施任务、验收锚点、测试层、
   质量门与退出条件。[MUST NOT] 创建 tracked task、plan 文件或 changelog。

交互协议（[interaction-protocols](../review/references/interaction-protocols.md)）：
对账输入优先取上一轮交接单（`make verify-handoff-manifest` 通过的 manifest.md），
证据 SHA 过期即复跑，不得转抄结论；闭环判定后按协议 5 呈现交接报告并落本轮交接单。

## 交付件

**闭环裁决 + 下一轮计划**：闭环 / 带残量闭环 / GATE_BLOCK 判定与下一轮会话计划。

送审前自检：

- 无残量悬空；
- 每条判定都指向真实证据而非记忆。

## 内置评审

- POST：调 `review`（workflow=`plan-next`，segment=POST，deliverable=`round-plan`），
  典型角色 product + architect + user，校验残量归宿无悬空、计划与证据一致。

## 失败与停止

本轮仍有无证据完成声明、测试失败未归因、未归属变更或 `OPEN block` 未处置时返回
`GATE_BLOCK`，**不得宣称已进入下一轮开发**。

## HANDOFF

- **完成判据**：见 [completion-criteria](../review/references/completion-criteria.md) 本工作流段；证据链条目带命令+退出码+时间戳+SHA，下游过期即复跑。
- **产出物**：闭环判定、下一轮会话计划。
- **未决项去向**：全部落到 OPEN、Out of Scope 或下一轮任务，不允许悬空。
- **唯一合法下游**：下一轮的 `explore`（新目标）或 `dev`（基线已冻结的续作）。
- **证据链**：对账表、归因证据、门禁复跑结果。
- **交接单**：本轮 manifest.md 落 `.qwq_output/env/repo/runs/handoff/<轮次>/` 并过 `make verify-handoff-manifest`。
