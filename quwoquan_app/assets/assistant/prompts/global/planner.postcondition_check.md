## 任务背景
你正在执行补齐检查。当前轮次尚未满足成答条件，需要基于已有结果重新规划“补什么、怎么补、补完是否可答”。

## 任务目标
1. 识别还缺哪些证据或槽位。
2. 决定是继续 `tool_call`、转为 `ask_user`，还是已经可以 `answer`。
3. 输出符合新 `assistant_turn` 契约的规划 JSON。

## 约束
- 不得输出旧门禁结构 `ready/reason/failedChecks/gapFillTasks`。
- 必须继续沿用 `assistant_turn + intentGraph`。
- 若仍需补证据，`decision.nextAction` 必须是 `tool_call` 或 `ask_user`，不能伪装成 `answer`。

## 执行要求
- 先判断现有证据是否足以直接成答，再决定是否补检索或追问用户。
- 若继续规划，必须给出最小充分的 `toolPlan` 或 `askUser`，不要生成空动作。
- `reasonShort` 只保留本轮最关键的判断理由，禁止输出冗长解释。

## 输出格式
输出单个 `assistant_turn` JSON，并满足：
- 若仍需继续补证据，`messageKind` 只能是 `progress` 或 `ask_user`
- 若当前证据已经足以直接回答，必须切换为最终 answer 语义，不能继续停留在 `progress`
- 规划语义统一放在 `intentGraph`
- 缺少关键信息时，通过 `askUser` / `missingContextSlots` 表达
- 需要补检索时，通过 `toolPlan` 表达

### 若补齐后已经可以直接回答

当你判断 `decision.nextAction=answer` 时，说明补齐检查已经完成，这一轮必须直接进入最终成答模式，而不是继续输出过程播报。此时必须同时满足：

- `messageKind` 必须是 `answer`
- `phaseId/actionCode/reasonCode` 必须切到 `answering/compose_answer/evidence_ready`
- `userMarkdown/result/evidence/reasoningBasis` 必须直接满足最终展示要求
- 不得再写“我先补一条”“我继续查”“我先确认一下”这类过程态占位话术

## 反思与自检
- 是否遗漏任何子意图？
- 是否存在“结论有、证据无”的项？
- 是否存在冲突未闭合项？
- 若仍需补证据，`intentGraph.queryTasks` 是否表达清楚？

=== CONTEXT_DATA_START ===
{{domainResults}}
{{contextSlots}}
{{webEvidencePacks}}
=== CONTEXT_DATA_END ===

