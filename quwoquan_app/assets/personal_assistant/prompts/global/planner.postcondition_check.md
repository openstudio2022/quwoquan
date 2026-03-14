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
- `messageKind=progress` 或 `ask_user`
- 规划语义统一放在 `intentGraph`
- 缺少关键信息时，通过 `askUser` / `missingContextSlots` 表达
- 需要补检索时，通过 `toolPlan` 表达

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

