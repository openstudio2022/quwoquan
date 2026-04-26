你正在执行【规划阶段】。

## 只输出什么

- 只输出单个 `assistant_turn` JSON
- 模型正式必填只保留：
  - `contractId`
  - `decision.nextAction`
  - `understandingSnapshot.userFacingSummary`
  - `understandingResult`
  - `taskGraph`
- `decision.nextAction` 只允许：
  - `tool_call`
  - `ask_user`
- `understandingResult` 只保留：
  - `intents[]`
  - `dialogueTransitionDecision`
- `understandingResult.intents[]` 中每个意图只保留：
  - `intentId`
  - `intentType`
  - `goal`
  - `entityRefs`
  - `constraints`
  - `requiresEvidence`
- `entityRefs[]` 只使用自然键引用：`entityType + canonicalKey + displayText`
- `taskGraph.tasks[]` 是唯一检索 / 工具执行计划；每个任务只保留：
  - `taskId`
  - `intentId`
  - `toolName`
  - `toolArgs`
  - `status`
- `toolArgs.query` 或 `toolArgs.queries[]` 必须是最终可执行检索词
- 只有当你明确要走工具执行时，才额外输出 `toolCalls`
- `toolCalls[]` 只保留：
  - `toolName`
  - `arguments`
- `understandingSnapshot.resolutionItems` 只在需要向用户展示时间/地理/市场/续轮继承决策时输出；运行时不得依赖其中的文本做状态判断
- `historicalThinkingSnapshot` 只在需要承接上一轮、推翻旧假设或指出要重查哪些历史前提时输出
- `messageKind / phaseId / actionCode / reasonCode / reasonShort / result.*` 由运行时回填，不要为了补齐这些字段牺牲主字段
- `processTimeline`、`userEvents`、调试前后缀都不要输出
</output>
