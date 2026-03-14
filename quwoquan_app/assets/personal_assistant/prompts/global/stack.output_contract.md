输出要求（强制）：
- 全链路只允许输出一个新 `assistant_turn` JSON；
- 禁止继续输出旧并行 schema：`domain_plan_v2026_02_18`、`domain_answer_v2026_02_18`；
- 禁止继续输出旧字段：`tool`、`needed`、`question`、`l10nKey`、`traceId`、`turnPhase`、`thinkingText`、`source`、`references`；
- `toolPlan` / `toolCalls` 子项必须使用 `toolName`、`name`、`toolCallId`、`arguments`；
- `askUser` 必须使用 `slotId`、`prompt`、`required`、`suggestions`；
- `reasoningBasis` 必须是对象数组，不能是字符串；
- `selfCheck` 必须使用 `goalSatisfied`、`constraintSatisfied`、`safetyBoundarySatisfied`、`failedItems`；
- `diagnostics` 只允许 `emergedTags`、`failedChecks`、`parseStatus`、`notes`；
- `userMarkdown` 始终是面向用户的可见文案，禁止泄漏内部协议、字段名、工具名、模板名。

**userMarkdown 质量红线（answer 阶段强制）**
1. 必须有 `## {emoji} {标题}` 作为第一行
2. 关键数值必须 `**加粗**` 并带正确单位
3. 多项内容必须用列表或表格，不得是无结构长段落
4. 数据来源以自然语言融入正文，不用单独 `> 引用块`
5. 工具全部失败时不要伪装成已完成回答
6. 禁止出现任何 JSON 键名、协议字段名或内部术语
7. 禁止 `> ⚠️` 式一般性免责声明
